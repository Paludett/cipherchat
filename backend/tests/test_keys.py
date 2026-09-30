import base64
import hashlib

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from sqlalchemy import text

from app import security
from tests.test_auth import client, db, novo_username, ultimo_evento, user  # noqa: F401 (fixtures)
from tests.test_rbac import assert_401, forjar_token


def spki_der(chave_privada) -> bytes:
    return chave_privada.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def nova_chave(bits: int = 2048) -> bytes:
    return spki_der(rsa.generate_private_key(public_exponent=65537, key_size=bits))


def b64(der: bytes) -> str:
    return base64.b64encode(der).decode()


def put_chave(user_id, body: dict):
    return client.put("/keys/me", json=body, headers={"Authorization": f"Bearer {forjar_token(user_id)}"})


def get_chave(user_id, token_de):
    return client.get(f"/keys/{user_id}", headers={"Authorization": f"Bearer {forjar_token(token_de)}"})


@pytest.fixture
def outro(db):
    username = novo_username()
    user_id = security.create_user(db, username, "senha-forte-123")
    db.commit()
    yield username, user_id
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    db.commit()


def test_publica_chave_e_devolve_fingerprint(user):
    _, user_id = user
    der = nova_chave()
    resp = put_chave(user_id, {"public_key": b64(der)})
    assert resp.status_code == 200
    assert resp.json() == {"fingerprint": hashlib.sha256(der).hexdigest()}


def test_qualquer_autenticado_le_chave_de_outro(user, outro):
    username, user_id = user
    _, outro_id = outro
    der = nova_chave()
    put_chave(user_id, {"public_key": b64(der)})

    resp = get_chave(user_id, token_de=outro_id)
    assert resp.status_code == 200
    assert resp.json() == {
        "user_id": str(user_id),
        "username": username,
        "public_key": b64(der),
        "fingerprint": hashlib.sha256(der).hexdigest(),
    }


def test_ler_chave_sem_token_devolve_401(user):
    _, user_id = user
    assert_401(client.get(f"/keys/{user_id}"))


def test_usuario_sem_chave_devolve_404(user, outro):
    _, user_id = user
    _, outro_id = outro
    resp = get_chave(outro_id, token_de=user_id)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("public_key", [
    "nao e base64!",
    b64(b"bytes que nao sao DER"),
    b64(nova_chave(1024)),
    b64(spki_der(ec.generate_private_key(ec.SECP256R1()))),
])
def test_chave_invalida_devolve_400(user, public_key):
    _, user_id = user
    resp = put_chave(user_id, {"public_key": public_key})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


def test_usuario_a_nao_sobrescreve_chave_de_b(user, outro):
    _, a_id = user
    _, b_id = outro
    chave_b = b64(nova_chave())
    put_chave(b_id, {"public_key": chave_b})

    # user_id no body e rejeitado (extra="forbid")
    resp = put_chave(a_id, {"public_key": b64(nova_chave()), "user_id": str(b_id)})
    assert resp.status_code == 400
    # Nao existe rota com o id na URL
    resp = client.put(f"/keys/{b_id}", json={"public_key": b64(nova_chave())},
                      headers={"Authorization": f"Bearer {forjar_token(a_id)}"})
    assert resp.status_code == 405
    # PUT /keys/me de A so altera a chave de A
    assert put_chave(a_id, {"public_key": b64(nova_chave())}).status_code == 200

    assert get_chave(b_id, token_de=a_id).json()["public_key"] == chave_b


def test_troca_de_chave_e_auditada(db, user):
    username, user_id = user
    antiga = put_chave(user_id, {"public_key": b64(nova_chave())}).json()["fingerprint"]
    nova = put_chave(user_id, {"public_key": b64(nova_chave())}).json()["fingerprint"]

    action, actor, details = ultimo_evento(db, username)
    assert action == "key_changed"
    assert actor == user_id
    assert details == {"old_fingerprint": antiga, "new_fingerprint": nova}


def test_users_me_mostra_fingerprint(user):
    _, user_id = user
    headers = {"Authorization": f"Bearer {forjar_token(user_id)}"}
    assert client.get("/users/me", headers=headers).json()["fingerprint"] is None

    fingerprint = put_chave(user_id, {"public_key": b64(nova_chave())}).json()["fingerprint"]
    assert client.get("/users/me", headers=headers).json()["fingerprint"] == fingerprint
