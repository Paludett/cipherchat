import logging

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.ratelimit import BLOQUEIO_MINUTOS, MAX_FALHAS_LOGIN, WS_MSGS_POR_SEGUNDO, limiter
from tests.test_auth import SENHA, client, db, login, novo_username, user  # noqa: F401 (fixtures)
from tests.test_logging import eventos
from tests.test_rbac import forjar_token
from tests.test_ws import conectar


def assert_429(resp, retry_after: str):
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited"
    assert resp.headers["Retry-After"] == retry_after


# ---------- HTTP ----------

def test_sexto_registro_no_minuto_devolve_429():
    for _ in range(5):
        client.post("/auth/register", json={"username": novo_username(), "password": "curta"})
    resp = client.post("/auth/register", json={"username": novo_username(), "password": "curta"})
    assert_429(resp, "60")


def test_api_geral_aceita_60_por_minuto_e_bloqueia_a_61a(user):
    _, user_id = user
    headers = {"Authorization": f"Bearer {forjar_token(user_id)}"}
    for _ in range(60):
        assert client.get("/users/me", headers=headers).status_code == 200
    assert_429(client.get("/users/me", headers=headers), "60")


def test_limite_geral_e_por_usuario_e_nao_por_ip(user):
    # IP esgotado nao afeta um usuario autenticado no mesmo IP
    _, user_id = user
    outro_headers = {"Authorization": f"Bearer {forjar_token(user_id)}"}
    for _ in range(60):
        client.get("/health")
    assert client.get("/health").status_code == 429
    assert client.get("/users/me", headers=outro_headers).status_code == 200


def test_429_gera_evento_rate_limited_no_log(caplog):
    for _ in range(6):
        client.post("/auth/register", json={"username": novo_username(), "password": "curta"})
    [r] = eventos(caplog, "rate_limited")
    assert r.levelno == logging.WARNING
    assert r.endpoint == "POST /auth/register"


# ---------- Bloqueio de login ----------

def test_bloqueio_apos_falhas_recusa_ate_a_senha_certa(user):
    username, _ = user
    for _ in range(MAX_FALHAS_LOGIN):
        assert login(username, "senha-errada").status_code == 401
    limiter.reset()
    assert_429(login(username, SENHA), str(BLOQUEIO_MINUTOS * 60))


def test_bloqueio_e_por_username(user):
    username, _ = user
    for _ in range(MAX_FALHAS_LOGIN):
        login(username, "senha-errada")
    limiter.reset()
    assert login(novo_username(), "senha-errada").status_code == 401


async def app_com_outro_ip(scope, receive, send):
    scope["client"] = ("10.0.0.2", 50000)
    await app(scope, receive, send)


def test_bloqueio_nao_afeta_o_dono_em_outro_ip(user):
    username, _ = user
    for _ in range(MAX_FALHAS_LOGIN):
        login(username, "senha-errada")  # atacante em 127.0.0.1
    resp = TestClient(app_com_outro_ip).post("/auth/login", json={"username": username, "password": SENHA})
    assert resp.status_code == 200


# ---------- WebSocket ----------

def test_ws_excesso_gera_erro_e_reincidencia_desconecta(monkeypatch, user):
    _, user_id = user
    monkeypatch.setattr("app.ws.monotonic", lambda: 0.0)  
    with pytest.raises(WebSocketDisconnect) as erro:
        with conectar(forjar_token(user_id)) as ws:
            for _ in range(WS_MSGS_POR_SEGUNDO):
                ws.send_text("{}")
            ws.send_text("{}")  
            respostas = [ws.receive_json() for _ in range(WS_MSGS_POR_SEGUNDO + 1)]
            assert respostas[-1]["error"]["code"] == "rate_limited"
            ws.send_text("{}") 
            ws.receive_text()
    assert erro.value.code == 1008
    assert erro.value.reason == "rate_limited"
