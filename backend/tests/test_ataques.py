"""Suite de ataques: cada teste simula um ataque e confere que a API se defende.

Roda tudo:        pytest tests/test_ataques.py
Casos principais: pytest -m attacks -v
"""
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from sqlalchemy import text

from tests.test_auth import SENHA, client, db, login, novo_username, user  # noqa: F401 (fixtures)
from tests.test_keys import b64, get_chave, nova_chave, outro, put_chave  # noqa: F401 (fixtures)
from tests.test_rate_limit import assert_429
from tests.test_rbac import assert_401, forjar_token, get


# ---------- Injecao SQL ----------

@pytest.mark.attacks
@pytest.mark.parametrize("payload", ["' OR '1'='1' --", "admin'--", "'; DROP TABLE users; --"])
def test_sqli_no_login_nao_tem_efeito(db, user, payload):
    username, _ = user
    total_antes = db.execute(text("SELECT count(*) FROM users")).scalar_one()
    senha_errada = login(username, "senha-errada")

    # Como username, a validacao do schema barra antes de chegar ao banco
    assert login(payload, SENHA).status_code == 400
    # Como senha, chega ao banco como parametro e vira so uma senha errada
    resp = login(username, payload)
    assert resp.status_code == 401
    assert resp.json() == senha_errada.json()

    assert db.execute(text("SELECT count(*) FROM users")).scalar_one() == total_antes


# ---------- BOLA ----------

@pytest.mark.attacks
def test_bola_a_nao_altera_recurso_de_b(user, outro):
    _, a_id = user
    _, b_id = outro
    chave_b = b64(nova_chave())
    put_chave(b_id, {"public_key": chave_b})

    # A tenta apontar para B pelo body e pela URL
    assert put_chave(a_id, {"public_key": b64(nova_chave()), "user_id": str(b_id)}).status_code == 400
    resp = client.put(f"/keys/{b_id}", json={"public_key": b64(nova_chave())},
                      headers={"Authorization": f"Bearer {forjar_token(a_id)}"})
    assert resp.status_code == 405

    assert get_chave(b_id, token_de=a_id).json()["public_key"] == chave_b


# ---------- Mass Assignment ----------

@pytest.mark.attacks
@pytest.mark.parametrize("extra", [{"role": "admin"}, {"is_active": False}])
def test_mass_assignment_no_registro(extra):
    resp = client.post("/auth/register", json={"username": novo_username(), "password": SENHA, **extra})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


def test_registro_normal_sempre_cria_role_user(db):
    username = novo_username()
    assert client.post("/auth/register", json={"username": username, "password": SENHA}).status_code == 201
    role = db.execute(text("SELECT role FROM users WHERE username = :u"), {"u": username}).scalar_one()
    assert role == "user"
    db.execute(text("DELETE FROM users WHERE username = :u"), {"u": username})
    db.commit()


# ---------- JWT ----------

@pytest.mark.attacks
def test_jwt_adulterado_e_recusado(user):
    _, user_id = user
    header, _, assinatura = forjar_token(user_id).split(".")
    # Payload trocado para role=admin, assinatura original
    payload = forjar_token(user_id, role="admin").split(".")[1]
    assert_401(get("/admin/users", f"{header}.{payload}.{assinatura}"))


def test_jwt_expirado_e_recusado(user):
    _, user_id = user
    expirado = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert_401(get("/users/me", forjar_token(user_id, exp=expirado)))


def test_jwt_com_issuer_errado_e_recusado(user):
    _, user_id = user
    assert_401(get("/users/me", forjar_token(user_id, iss="outro-emissor")))


def test_jwt_com_audience_errada_e_recusado(user):
    _, user_id = user
    assert_401(get("/users/me", forjar_token(user_id, aud="outra-audiencia")))


# ---------- Rate limit ----------

@pytest.mark.attacks
def test_rate_limit_devolve_429():
    for _ in range(5):
        client.post("/auth/register", json={"username": novo_username(), "password": "curta"})
    resp = client.post("/auth/register", json={"username": novo_username(), "password": "curta"})
    assert_429(resp, "60")


# ---------- MFA obrigatorio ----------

def test_com_mfa_ativo_a_senha_sozinha_nao_da_acesso(user):
    username, _ = user
    headers = {"Authorization": f"Bearer {login(username).json()['access_token']}"}
    secret = client.post("/auth/mfa/setup", headers=headers).json()["secret"]
    client.post("/auth/mfa/activate", headers=headers, json={"code": pyotp.TOTP(secret).now()})

    # O login so devolve token parcial, que nao abre rota protegida
    token_parcial = login(username).json()["mfa_token"]
    assert_401(get("/users/me", token_parcial))


# ---------- Escalada de privilegio ----------

def test_user_comum_em_rota_de_admin_devolve_403(user):
    _, user_id = user
    resp = get("/admin/users", forjar_token(user_id))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"
