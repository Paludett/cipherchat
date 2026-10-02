import os

from sqlalchemy import text

from app.deps import MAX_PAGE_SIZE
from app.main import MAX_BODY_BYTES
from tests.test_auth import client, db, user  # noqa: F401 (fixtures)
from tests.test_rbac import forjar_token


def assert_413(resp):
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "payload_too_large"


# ---------- Body HTTP ----------

def test_body_acima_do_limite_devolve_413():
    corpo = b"x" * (MAX_BODY_BYTES + 1)
    resp = client.post("/auth/login", content=corpo, headers={"Content-Type": "application/json"})
    assert_413(resp)


def test_body_sem_content_length_devolve_413():
    def pedacos():
        yield b'{"username": "a", "password": "b"}'

    resp = client.post("/auth/login", content=pedacos(), headers={"Content-Type": "application/json"})
    assert_413(resp)


def test_body_dentro_do_limite_passa(user):
    username, _ = user
    resp = client.post("/auth/login", json={"username": username, "password": "senha-errada"})
    assert resp.status_code == 401


# ---------- Paginacao ----------

def admin_token(db, user_id) -> str:
    db.execute(text("UPDATE users SET role = 'admin' WHERE id = :id"), {"id": user_id})
    db.commit()
    return forjar_token(user_id)


def test_limit_acima_do_maximo_e_recusado(db, user):
    _, user_id = user
    headers = {"Authorization": f"Bearer {admin_token(db, user_id)}"}
    resp = client.get(f"/admin/users?limit={MAX_PAGE_SIZE + 1}", headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


def test_offset_negativo_e_recusado(db, user):
    _, user_id = user
    headers = {"Authorization": f"Bearer {admin_token(db, user_id)}"}
    assert client.get("/admin/users?offset=-1", headers=headers).status_code == 400


# ---------- Postgres ----------

def test_role_app_api_tem_statement_timeout(db):
    esperado = os.getenv("APP_API_STATEMENT_TIMEOUT", "5s")
    assert db.execute(text("SHOW statement_timeout")).scalar() == esperado


def test_role_app_api_tem_connection_limit(db):
    esperado = int(os.getenv("APP_API_CONNECTION_LIMIT", "20"))
    limite = db.execute(text("SELECT rolconnlimit FROM pg_roles WHERE rolname = 'app_api'")).scalar()
    assert limite == esperado
