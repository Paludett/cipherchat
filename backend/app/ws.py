"""
WebSocket /ws e registro de quem esta online
"""
import os
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.audit import log_event
from app.db import SessionLocal
from app.deps import authenticate
from app.errors import ApiError
from app.logger import logger
from app.schemas import MessageIn

router = APIRouter()

MAX_WS_FRAME_BYTES = int(os.getenv("MAX_WS_FRAME_BYTES", "131072"))
MAX_WS_TOTAL = int(os.getenv("MAX_WS_TOTAL", "100"))


class ConnectionManager:
    """Uma conexao ativa por usuario (user_id -> WebSocket)."""

    def __init__(self) -> None:
        self.active: dict[uuid.UUID, WebSocket] = {}

    def lotado(self, user_id: uuid.UUID) -> bool:
        # Usuario ja conectado ou servidor no limite total, a nova conexao e recusada
        return user_id in self.active or len(self.active) >= MAX_WS_TOTAL

    def connect(self, user_id: uuid.UUID, ws: WebSocket) -> None:
        self.active[user_id] = ws

    def disconnect(self, user_id: uuid.UUID, ws: WebSocket) -> None:
        if self.active.get(user_id) is ws:
            del self.active[user_id]

    def online_ids(self) -> list[uuid.UUID]:
        return list(self.active)


manager = ConnectionManager()


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
    if user_id is None or manager.lotado(user_id):
        await ws.close(code=1008)
        return

    manager.connect(user_id, ws)
    registrar("ws_connect", ws, user_id)
    try:
        while True:
            texto = await ws.receive_text()
            if len(texto.encode()) > MAX_WS_FRAME_BYTES:
                await ws.close(code=1009)
                break
            await repassar_mensagem(ws, user_id, texto)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        manager.disconnect(user_id, ws)
        registrar("ws_disconnect", ws, user_id)
