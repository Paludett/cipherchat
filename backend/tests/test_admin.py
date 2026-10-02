import os
import subprocess
import uuid

import pytest
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from app import security
from app.models import User
from tests.test_auth import SENHA, client, db, novo_username, user  # noqa: F401 (fixtures)
from tests.test_rbac import forjar_token
from tests.test_ws import conectar


@pytest.fixture
def admin(db):
    username = novo_username()
    admin_id = security.create_user(db, username, SENHA)
    db.execute(text("UPDATE users SET role = 'admin' WHERE id = :id"), {"id": admin_id})
    db.commit()
    yield admin_id
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": admin_id})
    db.commit()


def headers(user_id) -> dict:
    return {"Authorization": f"Bearer {forjar_token(user_id)}"}


def patch(admin_id, alvo_id, body: dict):
    return client.patch(f"/admin/users/{alvo_id}", json=body, headers=headers(admin_id))


def delete(admin_id, alvo_id):
    return client.delete(f"/admin/users/{alvo_id}", headers=headers(admin_id))


def ultima_acao_admin(db, admin_id):
    return db.execute(
        text("SELECT action, details FROM audit_log WHERE actor = :id ORDER BY occurred_at DESC LIMIT 1"),
        {"id": admin_id},
    ).first()


def assert_cannot_modify_self(resp):
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "cannot_modify_self"


# ---------- Autorizacao ----------

@pytest.mark.parametrize("metodo", ["get", "patch", "delete"])
def test_user_comum_recebe_403_em_toda_rota_admin(user, metodo):
    _, user_id = user
    rota = "/admin/users" if metodo == "get" else f"/admin/users/{user_id}"
    kwargs = {"json": {"role": "admin"}} if metodo == "patch" else {}
    resp = client.request(metodo.upper(), rota, headers=headers(user_id), **kwargs)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


# ---------- GET /admin/users ----------

def test_lista_usuarios_paginada(admin, user):
    resp = client.get("/admin/users?limit=1", headers=headers(admin))
    assert resp.status_code == 200
    corpo = resp.json()
    assert len(corpo["items"]) == 1
    assert corpo["total"] >= 2
    assert set(corpo["items"][0]) == {"id", "username", "role", "is_active", "mfa_enabled", "created_at"}


def test_offset_avanca_a_pagina(admin, user):
    pagina1 = client.get("/admin/users?limit=1&offset=0", headers=headers(admin)).json()["items"]
    pagina2 = client.get("/admin/users?limit=1&offset=1", headers=headers(admin)).json()["items"]
    assert pagina1[0]["id"] != pagina2[0]["id"]


# ---------- PATCH /admin/users/{id} ----------

def test_promove_usuario_a_admin(db, admin, user):
    username, user_id = user
    resp = patch(admin, user_id, {"role": "admin"})
    assert resp.status_code == 200
    assert resp.json() == {"id": str(user_id), "username": username, "role": "admin", "is_active": True}

    acao = ultima_acao_admin(db, admin)
    assert acao.action == "admin_user_updated"
    assert acao.details == {"target": str(user_id), "changes": {"role": "admin"}}


def test_desativa_usuario(db, admin, user):
    _, user_id = user
    resp = patch(admin, user_id, {"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
    assert db.get(User, user_id).is_active is False


def test_desativar_derruba_websocket_do_usuario(admin, user):
    _, user_id = user
    with pytest.raises(WebSocketDisconnect) as erro:
        with conectar(forjar_token(user_id)) as ws:
            assert patch(admin, user_id, {"is_active": False}).status_code == 200
            ws.receive_text()
    assert erro.value.code == 1008
    assert erro.value.reason == "account_disabled"


def test_patch_rejeita_campo_fora_do_schema(admin, user):
    _, user_id = user
    resp = patch(admin, user_id, {"username": "outro_nome"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


def test_patch_rejeita_role_invalido(admin, user):
    _, user_id = user
    assert patch(admin, user_id, {"role": "root"}).status_code == 400


def test_patch_com_null_nao_altera_campo(db, admin, user):
    _, user_id = user
    resp = patch(admin, user_id, {"is_active": None})
    assert resp.status_code == 200
    assert db.get(User, user_id).is_active is True


def test_patch_usuario_inexistente_devolve_404(admin):
    resp = patch(admin, uuid.uuid4(), {"is_active": False})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("body", [{"role": "user"}, {"is_active": False}])
def test_admin_nao_rebaixa_nem_desativa_a_si_mesmo(db, admin, body):
    assert_cannot_modify_self(patch(admin, admin, body))
    assert db.get(User, admin).role == "admin"
    assert db.get(User, admin).is_active is True
    assert ultima_acao_admin(db, admin).action == "admin_modify_self_denied"


# ---------- DELETE /admin/users/{id} ----------

def test_remove_usuario(db, admin, user):
    username, user_id = user
    resp = delete(admin, user_id)
    assert resp.status_code == 204
    assert db.get(User, user_id) is None

    acao = ultima_acao_admin(db, admin)
    assert acao.action == "admin_user_deleted"
    assert acao.details == {"target": str(user_id), "username": username}


def test_remover_derruba_websocket_do_usuario(admin, user):
    _, user_id = user
    with pytest.raises(WebSocketDisconnect) as erro:
        with conectar(forjar_token(user_id)) as ws:
            assert delete(admin, user_id).status_code == 204
            ws.receive_text()
    assert erro.value.code == 1008
    assert erro.value.reason == "account_disabled"


def test_delete_usuario_inexistente_devolve_404(admin):
    resp = delete(admin, uuid.uuid4())
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_admin_nao_remove_a_si_mesmo(db, admin):
    assert_cannot_modify_self(delete(admin, admin))
    assert db.get(User, admin) is not None


# ---------- Seed ----------

def rodar_seed(username: str, password: str = SENHA):
    env = {**os.environ, "ADMIN_USERNAME": username, "ADMIN_PASSWORD": password}
    return subprocess.run(["python", "-m", "app.seed"], env=env, capture_output=True, text=True)


def test_seed_cria_admin_e_e_idempotente(db):
    username = novo_username()
    try:
        primeira = rodar_seed(username)
        assert primeira.returncode == 0, primeira.stderr
        assert "criado" in primeira.stdout

        segunda = rodar_seed(username)
        assert segunda.returncode == 0, segunda.stderr
        assert "ja existe" in segunda.stdout

        role = db.execute(text("SELECT role FROM users WHERE username = :u"), {"u": username}).scalar_one()
        assert role == "admin"
    finally:
        db.execute(text("DELETE FROM users WHERE username = :u"), {"u": username})
        db.commit()


def test_seed_rejeita_senha_fraca(db):
    username = novo_username()
    resultado = rodar_seed(username, "curta")
    assert resultado.returncode != 0
    assert db.execute(text("SELECT 1 FROM users WHERE username = :u"), {"u": username}).first() is None
