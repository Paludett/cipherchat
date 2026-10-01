import hashlib

import pytest
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from app import tokens
from tests.test_auth import client, db, novo_username, user  # noqa: F401 (fixtures)
from tests.test_keys import b64, nova_chave, outro, put_chave  # noqa: F401 (fixtures)
from tests.test_rbac import assert_401, forjar_token


def conectar(token: str | None):
    # O token vai em Sec-WebSocket-Protocol, "bearer, <token>", nunca na URL
    subprotocols = ["bearer", token] if token else []
    return client.websocket_connect("/ws", subprotocols=subprotocols)


def online_para(observador_id) -> list[dict]:
    resp = client.get("/users/online", headers={"Authorization": f"Bearer {forjar_token(observador_id)}"})
    assert resp.status_code == 200
    return resp.json()


def assert_fechado_com_1008(token: str | None):
    with pytest.raises(WebSocketDisconnect) as erro:
        with conectar(token) as ws:
            ws.receive_text()
    assert erro.value.code == 1008


def acoes_no_audit(db, user_id) -> list[str]:
    linhas = db.execute(
        text(
            "SELECT action FROM audit_log "
            "WHERE actor = :id AND action IN ('ws_connect', 'ws_disconnect') ORDER BY occurred_at"
        ),
        {"id": user_id},
    )
    return [linha.action for linha in linhas]


def test_sem_token_fecha_com_1008():
    assert_fechado_com_1008(None)


def test_token_adulterado_fecha_com_1008(user):
    _, user_id = user
    assert_fechado_com_1008(forjar_token(user_id) + "x")


def test_token_de_mfa_fecha_com_1008(user):
    _, user_id = user
    token_mfa = forjar_token(user_id, scope="mfa_pending", aud=tokens.MFA_AUDIENCE)
    assert_fechado_com_1008(token_mfa)


def test_online_sem_token_devolve_401():
    assert_401(client.get("/users/online"))


def test_conectado_aparece_em_online_com_id_username_e_fingerprint(user, outro):
    username, user_id = user
    _, outro_id = outro
    der = nova_chave()
    put_chave(user_id, {"public_key": b64(der)})

    with conectar(forjar_token(user_id)):
        assert online_para(outro_id) == [
            {"id": str(user_id), "username": username, "fingerprint": hashlib.sha256(der).hexdigest()}
        ]


def test_online_sem_chave_publicada_devolve_fingerprint_null(user, outro):
    _, user_id = user
    _, outro_id = outro
    with conectar(forjar_token(user_id)):
        assert online_para(outro_id)[0]["fingerprint"] is None


def test_online_nao_lista_o_proprio_usuario(user):
    _, user_id = user
    with conectar(forjar_token(user_id)):
        assert online_para(user_id) == []


def test_desconectado_some_de_online(user, outro):
    _, user_id = user
    _, outro_id = outro
    with conectar(forjar_token(user_id)):
        pass
    assert online_para(outro_id) == []


def test_connect_e_disconnect_vao_para_audit_log_sem_token(user, db):
    _, user_id = user
    token = forjar_token(user_id)
    with conectar(token):
        pass

    assert acoes_no_audit(db, user_id) == ["ws_connect", "ws_disconnect"]
    detalhes = db.execute(
        text("SELECT details::text FROM audit_log WHERE actor = :id AND action LIKE 'ws_%'"),
        {"id": user_id},
    ).scalars()
    assert all(token not in (d or "") for d in detalhes)


def test_segunda_conexao_derruba_a_primeira_e_continua_online(user, outro):
    _, user_id = user
    _, outro_id = outro
    token = forjar_token(user_id)

    with conectar(token) as primeira:
        with conectar(token):
            with pytest.raises(WebSocketDisconnect):
                primeira.receive_text()
            assert [u["id"] for u in online_para(outro_id)] == [str(user_id)]
