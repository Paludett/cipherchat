"""
WebSocket /ws e registro de quem esta online
"""
import uuid
from time import monotonic

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.audit import log_event
from app.db import SessionLocal
from app.deps import authenticate
from app.errors import ApiError
from app.logger import logger
from app.ratelimit import WS_MSGS_POR_SEGUNDO
from app.schemas import MessageIn

router = APIRouter()


class ConnectionManager:
    """Uma conexao ativa por usuario (user_id -> WebSocket)."""

    def __init__(self) -> None:
        self.active: dict[uuid.UUID, WebSocket] = {}

    async def connect(self, user_id: uuid.UUID, ws: WebSocket) -> None:
        antiga = self.active.get(user_id)
        self.active[user_id] = ws
        if antiga:
            await antiga.close()

    def disconnect(self, user_id: uuid.UUID, ws: WebSocket) -> None:
        if self.active.get(user_id) is ws:
            del self.active[user_id]

    def online_ids(self) -> list[uuid.UUID]:
        return list(self.active)


manager = ConnectionManager()


class LimiteMensagens:
    def __init__(self) -> None:
        self.segundo = 0
        self.contagem = 0

    def permite(self) -> bool:
        agora = int(monotonic())
        if agora != self.segundo:
            self.segundo, self.contagem = agora, 0
        self.contagem += 1
        return self.contagem <= WS_MSGS_POR_SEGUNDO


def token_do_handshake(ws: WebSocket) -> str | None:
    subprotocols = ws.scope["subprotocols"]
    if len(subprotocols) == 2 and subprotocols[0] == "bearer":
        return subprotocols[1]
    return None


def autenticar(token: str | None) -> uuid.UUID | None:
    if token is None:
        return None
    with SessionLocal() as db:
        try:
            return authenticate(db, token).id
        except ApiError:
            return None


def registrar(action: str, ws: WebSocket, user_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        log_event(db, action, ws.client.host, actor=user_id)


def registrar_mensagem(remetente: uuid.UUID, status: str, envelope: MessageIn | None = None) -> None:
    # So metadados, nunca encrypted_key, iv ou ciphertext
    logger.info("message_routed", extra={
        "actor": remetente,
        "target": envelope.to if envelope else None,
        "msg_id": envelope.msg_id if envelope else None,
        "status": status,
    })


async def enviar_erro(ws: WebSocket, code: str, message: str, msg_id: uuid.UUID | None = None) -> None:
    erro = {"type": "error", "error": {"code": code, "message": message}}
    if msg_id:
        erro["msg_id"] = str(msg_id)
    await ws.send_json(erro)


async def repassar_mensagem(ws: WebSocket, remetente: uuid.UUID, texto: str) -> None:
    try:
        envelope = MessageIn.model_validate_json(texto)
    except ValidationError:
        registrar_mensagem(remetente, "invalid")
        await enviar_erro(ws, "validation_error", "Envelope inválido.")
        return
    if envelope.to == remetente:
        registrar_mensagem(remetente, "invalid", envelope)
        await enviar_erro(ws, "validation_error", "Destinatário inválido.", envelope.msg_id)
        return

    try:
        destino = manager.active[envelope.to]
        await destino.send_json({**envelope.model_dump(mode="json"), "from": str(remetente)})
    except (KeyError, WebSocketDisconnect, RuntimeError):
        registrar_mensagem(remetente, "offline", envelope)
        await enviar_erro(ws, "offline", "Destinatário offline.", envelope.msg_id)
        return
    registrar_mensagem(remetente, "delivered", envelope)
    await ws.send_json({"type": "sent", "msg_id": str(envelope.msg_id)})


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    token = token_do_handshake(ws)
    await ws.accept(subprotocol="bearer" if token else None)
    user_id = autenticar(token)
    if user_id is None:
        await ws.close(code=1008)
        return

    await manager.connect(user_id, ws)
    registrar("ws_connect", ws, user_id)
    limite = LimiteMensagens()
    ja_avisado = False
    try:
        while True:
            texto = await ws.receive_text()
            if limite.permite():
                await repassar_mensagem(ws, user_id, texto)
                continue

            logger.warning("rate_limited", extra={"actor": user_id, "ip": ws.client.host, "endpoint": "WS /ws"})
            if ja_avisado:
                await ws.close(code=1008, reason="rate_limited")
                break
            ja_avisado = True
            await enviar_erro(ws, "rate_limited", "Muitas mensagens. Aguarde um momento.")
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        manager.disconnect(user_id, ws)
        registrar("ws_disconnect", ws, user_id)
