import importlib
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import ProgrammingError
from starlette.websockets import WebSocketDisconnect

from app import main
from app import ws as ws_module
from app.routes import users
from tests.test_auth import app_com_ip, client, db, user  # noqa: F401 (fixtures)
from tests.test_rbac import forjar_token
from tests.test_ws import conectar

client_500 = TestClient(app_com_ip, raise_server_exceptions=False)


def assert_erro(resp, status: int, code: str):
    assert resp.status_code == status
    erro = resp.json()["error"]
    assert erro["code"] == code
    assert set(erro) == {"code", "message"}


# ---------- HTTPException ----------

def test_rota_inexistente_404_no_formato_do_contrato():
    assert_erro(client.get("/nao-existe"), 404, "not_found")


def test_metodo_errado_405_no_formato_do_contrato():
    assert_erro(client.delete("/health"), 405, "method_not_allowed")


def test_chave_inexistente_404_e_nao_200_com_corpo_nulo(user):
    _, user_id = user
    resp = client.get(f"/keys/{uuid.uuid4()}", headers={"Authorization": f"Bearer {forjar_token(user_id)}"})
    assert_erro(resp, 404, "not_found")


# ---------- 500 ----------

@pytest.mark.parametrize("erro", [
    ProgrammingError("SELECT * FROM users WHERE senha = 'x'", {}, Exception("/app/app/db.py")),
    RuntimeError("falha em /app/app/routes/users.py"),
])
def test_500_nao_vaza_detalhe_interno(user, monkeypatch, caplog, erro):
    _, user_id = user

    def explode():
        raise erro
    monkeypatch.setattr(users.manager, "online_ids", explode)

    resp = client_500.get("/users/online", headers={"Authorization": f"Bearer {forjar_token(user_id)}"})

    assert_erro(resp, 500, "internal_error")
    for vazamento in ("SELECT", "/app/", "Traceback", type(erro).__name__):
        assert vazamento not in resp.text
    registro = next(r for r in caplog.records if r.getMessage() == "internal_error")
    assert registro.exc_info[1] is erro


# ---------- WebSocket ----------

def test_erro_no_websocket_fecha_1011_e_servidor_continua(user, monkeypatch, caplog):
    _, user_id = user

    async def explode(*args):
        raise ValueError("bug em /app/app/ws.py")
    monkeypatch.setattr(ws_module, "repassar_mensagem", explode)

    with conectar(forjar_token(user_id)) as ws:
        ws.send_text("{}")
        with pytest.raises(WebSocketDisconnect) as erro:
            ws.receive_text()
    assert erro.value.code == 1011
    assert erro.value.reason == "internal_error"
    assert any(r.getMessage() == "internal_error" and r.exc_info for r in caplog.records)

    assert user_id not in ws_module.manager.active
    assert client.get("/health").status_code == 200


# ---------- Swagger em producao ----------

@pytest.fixture
def app_prod(monkeypatch):
    monkeypatch.setenv("AMBIENTE", "PROD")
    yield TestClient(importlib.reload(main).app)
    monkeypatch.delenv("AMBIENTE")
    importlib.reload(main)


@pytest.mark.parametrize("rota", ["/docs", "/redoc", "/openapi.json"])
def test_docs_desligados_em_prod(app_prod, rota):
    assert_erro(app_prod.get(rota), 404, "not_found")


@pytest.mark.parametrize("rota", ["/docs", "/redoc", "/openapi.json"])
def test_docs_ligados_fora_de_prod(rota):
    assert client.get(rota).status_code == 200
