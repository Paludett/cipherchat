import hashlib
import uuid

import pytest
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from app import tokens
from app import ws as ws_module
from app.ws import manager
from tests.test_auth import client, db, novo_username, user  # noqa: F401 (fixtures)
from tests.test_keys import b64, nova_chave, outro, put_chave  # noqa: F401 (fixtures)
from tests.test_rbac import assert_401, forjar_token


def conectar(token: str | None):
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


def test_segunda_conexao_do_mesmo_usuario_e_recusada_e_primeira_continua(user, outro):
    _, user_id = user
    _, outro_id = outro
    token = forjar_token(user_id)

    with conectar(token) as primeira:
        assert_fechado_com_1008(token)

        # A primeira conexao continua viva e online
        primeira.send_json(envelope(outro_id))
        assert_erro(primeira, "offline")
        assert [u["id"] for u in online_para(outro_id)] == [str(user_id)]


def test_conexao_acima_do_limite_total_e_recusada(user, outro, monkeypatch):
    _, user_id = user
    _, outro_id = outro
    monkeypatch.setattr(ws_module, "MAX_WS_TOTAL", 1)

    with conectar(forjar_token(user_id)):
        assert_fechado_com_1008(forjar_token(outro_id))


def test_frame_acima_do_limite_fecha_com_1009(user):
    _, user_id = user
    with conectar(forjar_token(user_id)) as ws:
        ws.send_text("x" * (ws_module.MAX_WS_FRAME_BYTES + 1))
        with pytest.raises(WebSocketDisconnect) as erro:
            ws.receive_text()
    assert erro.value.code == 1009


# ---------- Mensagens ----------

def envelope(to, **campos) -> dict:
    return {
        "type": "message",
        "msg_id": str(uuid.uuid4()),
        "to": str(to),
        "encrypted_key": b64(b"k" * 256),
        "iv": b64(b"i" * 12),
        "ciphertext": b64(b"c" * 32),
        "sent_at": "2026-09-27T14:03:00Z",
        **campos,
    }


def assert_erro(ws, code: str, msg_id: str | None = None):
    resposta = ws.receive_json()
    assert resposta["type"] == "error"
    assert resposta["error"]["code"] == code
    if msg_id:
        assert resposta["msg_id"] == msg_id


def test_mensagem_entregue_com_from_do_token(user, outro):
    _, user_id = user
    _, outro_id = outro
    with conectar(forjar_token(outro_id)) as destino, conectar(forjar_token(user_id)) as origem:
        # from enviado pelo cliente e ignorado e sobrescrito com o sub do token
        enviado = envelope(outro_id, **{"from": str(outro_id)})
        origem.send_json(enviado)

        assert destino.receive_json() == {**enviado, "from": str(user_id)}
        assert origem.receive_json() == {"type": "sent", "msg_id": enviado["msg_id"]}


def test_destinatario_offline_devolve_erro_offline(user, outro):
    _, user_id = user
    _, outro_id = outro
    with conectar(forjar_token(user_id)) as origem:
        enviado = envelope(outro_id)
        origem.send_json(enviado)
        assert_erro(origem, "offline", enviado["msg_id"])


def test_destinatario_inexistente_tambem_e_offline(user):
    # Nao diferencia "nao existe" de "offline", assim nao revela quais ids existem
    _, user_id = user
    with conectar(forjar_token(user_id)) as origem:
        origem.send_json(envelope(uuid.uuid4()))
        assert_erro(origem, "offline")


@pytest.mark.parametrize(
    "campos",
    [
        {"encrypted_key": "nao e base64!"},
        {"encrypted_key": b64(b"k" * 255)},
        {"iv": b64(b"i" * 11)},
        {"iv": b64(b"i" * 13)},
        {"ciphertext": b64(b"c" * 15)},
        {"ciphertext": b64(b"c" * (64 * 1024 + 1))},
        {"msg_id": "nao-e-uuid"},
        {"sent_at": "x" * 100},
        {"type": "outro"},
        {"campo_extra": 1},
    ],
)
def test_envelope_invalido_devolve_validation_error(user, outro, campos):
    _, user_id = user
    _, outro_id = outro
    with conectar(forjar_token(outro_id)), conectar(forjar_token(user_id)) as origem:
        origem.send_json(envelope(outro_id, **campos))
        assert_erro(origem, "validation_error")


def test_mensagem_para_si_mesmo_devolve_validation_error(user):
    _, user_id = user
    with conectar(forjar_token(user_id)) as origem:
        origem.send_json(envelope(user_id))
        assert_erro(origem, "validation_error")


def test_json_invalido_devolve_erro_e_conexao_continua(user, outro):
    _, user_id = user
    _, outro_id = outro
    with conectar(forjar_token(outro_id)) as destino, conectar(forjar_token(user_id)) as origem:
        origem.send_text("isso nao e json")
        assert_erro(origem, "validation_error")

        enviado = envelope(outro_id)
        origem.send_json(enviado)
        assert destino.receive_json()["msg_id"] == enviado["msg_id"]


def test_conteudo_cifrado_nao_vai_para_audit_log(user, outro, db):
    _, user_id = user
    _, outro_id = outro
    enviado = envelope(outro_id, ciphertext=b64(b"segredo-cifrado" * 4))
    with conectar(forjar_token(outro_id)) as destino, conectar(forjar_token(user_id)) as origem:
        origem.send_json(enviado)
        destino.receive_json()

    detalhes = db.execute(text("SELECT coalesce(details::text, '') FROM audit_log")).scalars()
    for d in detalhes:
        for campo in ("encrypted_key", "iv", "ciphertext"):
            assert enviado[campo] not in d


def test_destinatario_que_cai_durante_envio_vira_offline_sem_derrubar_remetente(user, outro):
    _, user_id = user
    _, outro_id = outro

    class ConexaoFechada:
        async def send_json(self, _):
            raise RuntimeError("Cannot call send once a close message has been sent")

    with conectar(forjar_token(user_id)) as origem:
        manager.active[outro_id] = ConexaoFechada()
        try:
            enviado = envelope(outro_id)
            origem.send_json(enviado)
            assert_erro(origem, "offline", enviado["msg_id"])

            # Conexao do remetente continua viva
            origem.send_json(envelope(outro_id))
            assert_erro(origem, "offline")
        finally:
            manager.active.pop(outro_id, None)
