import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from app import security, tokens
from app.db import SessionLocal
from app.main import app
from app.models import User

SENHA = "senha-forte-123"

async def app_com_ip(scope, receive, send):
    # O TestClient manda client="testclient", que nao cabe na coluna INET da audit_log
    scope["client"] = ("127.0.0.1", 50000)
    await app(scope, receive, send)


client = TestClient(app_com_ip)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def novo_username() -> str:
    return "u_" + uuid.uuid4().hex[:10]


@pytest.fixture
def user(db):
    username = novo_username()
    user_id = security.create_user(db, username, SENHA)
    db.commit()
    yield username, user_id
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    db.commit()


def login(username: str, password: str = SENHA):
    return client.post("/auth/login", json={"username": username, "password": password})


def decode(token: str, audience: str) -> dict:
    return jwt.decode(
        token, tokens.JWT_SECRET, algorithms=["HS256"],
        audience=audience, issuer=tokens.JWT_ISSUER,
    )


def ultimo_evento(db, username: str):
    return db.execute(
        text(
            "SELECT action, actor, details FROM audit_log "
            "WHERE details->>'username' = :u OR actor = (SELECT id FROM users WHERE username = :u) "
            "ORDER BY occurred_at DESC LIMIT 1"
        ),
        {"u": username},
    ).first()


# ---------- Registro ----------

def test_registro_cria_usuario_comum(db):
    username = novo_username()
    resp = client.post("/auth/register", json={"username": username, "password": SENHA})
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == username
    assert body["role"] == "user"
    assert set(body) == {"id", "username", "role"}
    db.execute(text("DELETE FROM users WHERE username = :u"), {"u": username})
    db.commit()


def test_registro_username_repetido(user):
    username, _ = user
    resp = client.post("/auth/register", json={"username": username, "password": SENHA})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "username_taken"


def test_registro_senha_fraca():
    resp = client.post("/auth/register", json={"username": novo_username(), "password": "curta"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "weak_password"


def test_campo_extra_no_registro_vira_400():
    resp = client.post("/auth/register", json={
        "username": novo_username(), "password": SENHA, "role": "admin",
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


# ---------- Login ----------

def test_login_sem_mfa_devolve_jwt_final(user):
    username, user_id = user
    resp = login(username)
    assert resp.status_code == 200
    body = resp.json()
    assert body["mfa_required"] is False
    assert body["expires_in"] == tokens.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    claims = decode(body["access_token"], tokens.JWT_AUDIENCE)
    assert claims["sub"] == str(user_id)
    assert claims["role"] == "user"
    assert claims["scope"] == "access"
    assert {"iat", "exp", "jti"} <= set(claims)


def test_login_com_mfa_devolve_token_parcial(db, user):
    username, user_id = user
    db.execute(text("UPDATE users SET totp_enabled = true WHERE id = :id"), {"id": user_id})
    db.commit()

    body = login(username).json()
    assert body["mfa_required"] is True
    assert "access_token" not in body

    claims = decode(body["mfa_token"], tokens.MFA_AUDIENCE)
    assert claims["scope"] == "mfa_pending"
    assert "role" not in claims


def test_token_parcial_nao_vale_como_token_de_acesso(db, user):
    username, user_id = user
    db.execute(text("UPDATE users SET totp_enabled = true WHERE id = :id"), {"id": user_id})
    db.commit()

    mfa_token = login(username).json()["mfa_token"]
    with pytest.raises(jwt.InvalidAudienceError):
        decode(mfa_token, tokens.JWT_AUDIENCE)


def test_senha_errada_e_usuario_inexistente_tem_mesma_resposta(user):
    username, _ = user
    senha_errada = login(username, "outra-senha")
    inexistente = login(novo_username())
    assert senha_errada.status_code == inexistente.status_code == 401
    assert senha_errada.json() == inexistente.json()
    assert senha_errada.json()["error"]["code"] == "invalid_credentials"


def test_erro_de_validacao_nao_ecoa_a_senha(user):
    username, _ = user
    senha_longa = "segredo-" + "x" * 80  # passa do limite de 72
    resp = login(username, senha_longa)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"
    assert "segredo-" not in resp.text


def test_usuario_inativo_nao_loga(db, user):
    username, user_id = user
    db.execute(text("UPDATE users SET is_active = false WHERE id = :id"), {"id": user_id})
    db.commit()

    resp = login(username)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "account_disabled"
    assert "access_token" not in resp.json()


def test_usuario_inativo_com_senha_errada_recebe_401_generico(db, user):
    username, user_id = user
    db.execute(text("UPDATE users SET is_active = false WHERE id = :id"), {"id": user_id})
    db.commit()

    assert login(username, "outra-senha").status_code == 401


# ---------- Auditoria ----------

def test_login_com_sucesso_e_auditado(db, user):
    username, user_id = user
    login(username)
    action, actor, _ = ultimo_evento(db, username)
    assert action == "login_success"
    assert actor == user_id


def test_login_com_falha_e_auditado(db, user):
    username, _ = user
    login(username, "outra-senha")
    action, actor, details = ultimo_evento(db, username)
    assert action == "login_failed"
    assert actor is None
    assert details == {"username": username, "reason": "invalid_credentials"}


def test_auditoria_nao_guarda_senha(db, user):
    username, _ = user
    login(username, "senha-secreta-errada")
    _, _, details = ultimo_evento(db, username)
    assert "senha-secreta-errada" not in str(details)


# ---------- Logout ----------

def logout(token: str):
    return client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})


def test_logout_revoga_o_token(user):
    username, _ = user
    token = login(username).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/users/me", headers=headers).status_code == 200

    assert logout(token).status_code == 204
    assert client.get("/users/me", headers=headers).status_code == 401


def test_logout_duas_vezes_com_o_mesmo_token_e_401(user):
    username, _ = user
    token = login(username).json()["access_token"]
    assert logout(token).status_code == 204
    assert logout(token).status_code == 401


def test_logout_nao_derruba_outras_sessoes(user):
    username, _ = user
    primeiro = login(username).json()["access_token"]
    segundo = login(username).json()["access_token"]
    assert logout(primeiro).status_code == 204
    assert client.get("/users/me", headers={"Authorization": f"Bearer {segundo}"}).status_code == 200


def test_logout_sem_token_e_401():
    assert client.post("/auth/logout").status_code == 401


def test_logout_com_token_parcial_de_mfa_e_401(db, user):
    _, user_id = user
    assert logout(tokens.create_mfa_token(db.get(User, user_id))).status_code == 401


def test_token_revogado_nao_abre_websocket(user):
    username, _ = user
    token = login(username).json()["access_token"]
    logout(token)
    with pytest.raises(WebSocketDisconnect) as erro:
        with client.websocket_connect("/ws", subprotocols=["bearer", token]) as ws:
            ws.receive_text()
    assert erro.value.code == 1008


def test_logout_e_auditado(db, user):
    username, _ = user
    logout(login(username).json()["access_token"])
    action, _, _ = ultimo_evento(db, username)
    assert action == "logout"
