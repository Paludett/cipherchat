"""
WebSocket /ws e registro de quem esta online

O JWT viaja em Sec-WebSocket-Protocol ("bearer, <token>")
assim o token nao aparece na URL, nem nos logs de acesso do uvicorn
"""
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.audit import log_event
from app.db import SessionLocal
from app.deps import authenticate
from app.errors import ApiError

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
        # So remove se ainda for esta conexao, a antiga nao apaga a nova
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


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    token = token_do_handshake(ws)
    # O accept vem antes do close, pois fechar antes vira 403 HTTP e o navegador veria 1006, nao 1008
    await ws.accept(subprotocol="bearer" if token else None)
    user_id = autenticar(token)
    if user_id is None:
        await ws.close(code=1008)
        return

    await manager.connect(user_id, ws)
    registrar("ws_connect", ws, user_id)
    try:
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, RuntimeError):
        # RuntimeError, o servidor fechou esta conexao ao aceitar uma mais nova do mesmo usuario
        pass
    finally:
        manager.disconnect(user_id, ws)
        registrar("ws_disconnect", ws, user_id)
