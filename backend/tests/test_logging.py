import json
import logging
import uuid
from datetime import datetime, timedelta

from app.logger import JSONFormatter
from tests.test_auth import SENHA, client, db, login, user  # noqa: F401 (fixtures)
from tests.test_keys import outro  # noqa: F401 (fixture)
from tests.test_rbac import forjar_token
from tests.test_ws import conectar, envelope


def eventos(caplog, nome: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "audit" and r.getMessage() == nome]


def linhas_json(caplog) -> str:
    # Texto do que iria para o arquivo, para checar que nenhum segredo aparece
    return "\n".join(JSONFormatter().format(r) for r in caplog.records if r.name == "audit")


# ---------- JSONFormatter ----------

def test_formatter_gera_json_com_timestamp_utc():
    actor = uuid.uuid4()
    record = logging.LogRecord("audit", logging.INFO, __file__, 1, "login_success", None, None)
    record.actor = actor
    record.ip = "127.0.0.1"

    linha = json.loads(JSONFormatter().format(record))

    assert linha["event_type"] == "login_success"
    assert linha["level"] == "INFO"
    assert linha["actor"] == str(actor)
    assert linha["ip"] == "127.0.0.1"
    assert datetime.fromisoformat(linha["timestamp"]).utcoffset() == timedelta(0)
    # Campo que nao veio fica fora da linha
    assert "target" not in linha


# ---------- Middleware ----------

def test_sem_token_gera_alerta_critico(caplog):
    client.get("/users/me")
    [r] = eventos(caplog, "http_request")
    assert r.levelno == logging.CRITICAL
    assert r.alert == "access_denied"
    assert r.status == 401
    assert r.endpoint == "GET /users/me"
    assert r.ip == "127.0.0.1"


def test_papel_insuficiente_gera_alerta_critico(caplog, user):
    _, user_id = user
    client.get("/admin/users", headers={"Authorization": f"Bearer {forjar_token(user_id)}"})
    [r] = eventos(caplog, "http_request")
    assert r.levelno == logging.CRITICAL
    assert r.alert == "access_denied"
    assert r.status == 403


def test_rota_inexistente_gera_alerta_de_reconhecimento(caplog):
    client.get("/wp-admin")
    [r] = eventos(caplog, "http_request")
    assert r.levelno == logging.WARNING
    assert r.alert == "reconnaissance"
    assert r.status == 404


def test_requisicao_normal_e_info_sem_alerta(caplog):
    client.get("/health")
    [r] = eventos(caplog, "http_request")
    assert r.levelno == logging.INFO
    assert r.status == 200
    assert "alert" not in json.loads(JSONFormatter().format(r))


def test_endpoint_nao_inclui_query_string(caplog):
    client.get("/users/me?token=segredo-na-url")
    [r] = eventos(caplog, "http_request")
    assert r.endpoint == "GET /users/me"
    assert "segredo-na-url" not in linhas_json(caplog)


# ---------- Eventos de autenticacao ----------

def test_login_ok_vai_para_o_log_sem_senha_nem_token(caplog, user):
    username, user_id = user
    token = login(username).json()["access_token"]

    [r] = eventos(caplog, "login_success")
    assert r.actor == user_id
    assert r.ip == "127.0.0.1"
    texto = linhas_json(caplog)
    assert SENHA not in texto
    assert token not in texto


def test_login_falho_vai_para_o_log_sem_a_senha_tentada(caplog, user):
    username, _ = user
    login(username, "senha-errada-xyz")

    [r] = eventos(caplog, "login_failed")
    assert r.details["username"] == username
    assert "senha-errada-xyz" not in linhas_json(caplog)


def test_connect_e_disconnect_do_ws_vao_para_o_log(caplog, user):
    _, user_id = user
    with conectar(forjar_token(user_id)):
        pass
    assert [r.actor for r in eventos(caplog, "ws_connect")] == [user_id]
    assert [r.actor for r in eventos(caplog, "ws_disconnect")] == [user_id]


# ---------- Mensagens do /ws ----------

def test_mensagem_roteada_loga_so_metadados(caplog, user, outro):
    _, user_id = user
    _, outro_id = outro
    with conectar(forjar_token(outro_id)) as destino, conectar(forjar_token(user_id)) as origem:
        enviado = envelope(outro_id)
        origem.send_json(enviado)
        destino.receive_json()
        origem.receive_json()

    [r] = eventos(caplog, "message_routed")
    assert r.actor == user_id
    assert r.target == outro_id
    assert str(r.msg_id) == enviado["msg_id"]
    assert r.status == "delivered"
    texto = linhas_json(caplog)
    for campo in ("encrypted_key", "iv", "ciphertext"):
        assert enviado[campo] not in texto


def test_mensagem_para_offline_loga_status_offline(caplog, user, outro):
    _, user_id = user
    _, outro_id = outro
    with conectar(forjar_token(user_id)) as origem:
        origem.send_json(envelope(outro_id))
        origem.receive_json()

    [r] = eventos(caplog, "message_routed")
    assert r.status == "offline"
    assert r.target == outro_id


def test_envelope_invalido_loga_status_invalid(caplog, user):
    _, user_id = user
    with conectar(forjar_token(user_id)) as origem:
        origem.send_text("isso nao e json")
        origem.receive_json()

    [r] = eventos(caplog, "message_routed")
    assert r.status == "invalid"
    assert r.actor == user_id
