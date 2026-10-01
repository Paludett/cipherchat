import time
import uuid

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import security
from app.db import SessionLocal
from app.main import app

SENHA = "senha-forte-123"


async def app_com_ip(scope, receive, send):
    scope["client"] = ("127.0.0.1", 50000)
    await app(scope, receive, send)


client = TestClient(app_com_ip)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def user(db):
    username = "u_" + uuid.uuid4().hex[:10]
    user_id = security.create_user(db, username, SENHA)
    db.commit()
    token = client.post(
        "/auth/login", json={"username": username, "password": SENHA}
    ).json()["access_token"]
    yield username, user_id, {"Authorization": f"Bearer {token}"}
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    db.commit()


def totp_enabled(db, user_id) -> bool:
    return db.execute(
        text("SELECT totp_enabled FROM users WHERE id = :id"), {"id": user_id}
    ).scalar_one()


def eventos(db, user_id) -> list[str]:
    return db.execute(
        text("SELECT action FROM audit_log WHERE actor = :id ORDER BY occurred_at"),
        {"id": user_id},
    ).scalars().all()


def setup(headers) -> str:
    return client.post("/auth/mfa/setup", headers=headers).json()["secret"]


def activate(headers, code: str):
    return client.post("/auth/mfa/activate", headers=headers, json={"code": code})


# ---------- Setup (fase 1) ----------

def test_setup_devolve_uri_e_nao_ativa(db, user):
    username, user_id, headers = user
    resp = client.post("/auth/mfa/setup", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["otpauth_uri"].startswith(f"otpauth://totp/ChatSeguro:{username}?")
    assert f"secret={body['secret']}" in body["otpauth_uri"]
    assert "issuer=ChatSeguro" in body["otpauth_uri"]
    assert totp_enabled(db, user_id) is False


def test_setup_guarda_segredo_cifrado(db, user):
    _, user_id, headers = user
    secret = setup(headers)
    guardado = db.execute(
        text("SELECT totp_secret FROM users WHERE id = :id"), {"id": user_id}
    ).scalar_one()
    assert secret.encode() not in guardado
    assert security.get_totp_secret(db, user_id) == secret


def test_setup_sem_token_e_401():
    assert client.post("/auth/mfa/setup").status_code == 401


def test_setup_com_mfa_ativo_e_409(db, user):
    _, _, headers = user
    secret = setup(headers)
    activate(headers, pyotp.TOTP(secret).now())
    resp = client.post("/auth/mfa/setup", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "mfa_already_enabled"


# ---------- Activate (fase 2) ----------

def test_activate_sem_setup_e_409(user):
    _, _, headers = user
    resp = activate(headers, "123456")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "mfa_not_pending"


def test_activate_com_codigo_errado_nao_ativa(db, user):
    _, user_id, headers = user
    secret = setup(headers)
    errado = pyotp.TOTP(secret).at(time.time() + 300)
    resp = activate(headers, errado)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_mfa_code"
    assert totp_enabled(db, user_id) is False


def test_activate_com_codigo_certo_ativa_e_devolve_backup_codes(db, user):
    _, user_id, headers = user
    secret = setup(headers)
    resp = activate(headers, pyotp.TOTP(secret).now())
    assert resp.status_code == 200
    codes = resp.json()["backup_codes"]
    assert len(codes) == 10
    assert all(len(c) == 11 and c[5] == "-" for c in codes)
    assert totp_enabled(db, user_id) is True


def test_activate_aceita_codigo_da_janela_anterior(db, user):
    # valid_window=1 tolera o drift de relogio
    _, user_id, headers = user
    secret = setup(headers)
    anterior = pyotp.TOTP(secret).at(time.time() - 30)
    assert activate(headers, anterior).status_code == 200
    assert totp_enabled(db, user_id) is True


def test_activate_duas_vezes_e_409(user):
    _, _, headers = user
    secret = setup(headers)
    activate(headers, pyotp.TOTP(secret).now())
    resp = activate(headers, pyotp.TOTP(secret).now())
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "mfa_not_pending"


def test_backup_codes_so_hash_no_banco(db, user):
    _, user_id, headers = user
    secret = setup(headers)
    codes = activate(headers, pyotp.TOTP(secret).now()).json()["backup_codes"]
    hashes = db.execute(
        text("SELECT code_hash FROM backup_codes WHERE user_id = :id"), {"id": user_id}
    ).scalars().all()
    assert len(hashes) == 10
    assert all(h.startswith("$2") for h in hashes)
    for code in codes:
        assert code not in hashes
        assert code.replace("-", "") not in hashes


def test_reativar_apaga_backup_codes_antigos(db, user):
    _, user_id, headers = user
    secret = setup(headers)
    antigos = activate(headers, pyotp.TOTP(secret).now()).json()["backup_codes"]
    # Simula o recover, que desliga o MFA
    db.execute(text("UPDATE users SET totp_enabled = false WHERE id = :id"), {"id": user_id})
    db.commit()

    secret = setup(headers)
    activate(headers, pyotp.TOTP(secret).now())
    total = db.execute(
        text("SELECT count(*) FROM backup_codes WHERE user_id = :id"), {"id": user_id}
    ).scalar_one()
    assert total == 10
    assert security.use_backup_code(db, user_id, antigos[0]) is False


# ---------- Auditoria ----------

def test_setup_e_activate_sao_auditados(db, user):
    _, user_id, headers = user
    secret = setup(headers)
    activate(headers, pyotp.TOTP(secret).at(time.time() + 300))
    activate(headers, pyotp.TOTP(secret).now())
    assert eventos(db, user_id)[-3:] == ["mfa_setup", "mfa_activate_failed", "mfa_activated"]
