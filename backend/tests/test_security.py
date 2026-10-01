import uuid

import pytest
from sqlalchemy import text

from app import security
from app.db import SessionLocal


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def user(db):
    username = "u_" + uuid.uuid4().hex[:10]
    user_id = security.create_user(db, username, "senha-forte-123")
    db.commit()
    yield username, user_id
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    db.commit()


def test_senha_curta_e_rejeitada():
    with pytest.raises(ValueError, match="weak_password"):
        security.validate_password("curta")


def test_senha_valida_passa():
    security.validate_password("12345678")


def test_senha_nao_fica_em_texto_claro(db, user):
    username, _ = user
    hash_ = db.execute(
        text("SELECT password_hash FROM users WHERE username = :u"), {"u": username}
    ).scalar_one()
    assert "senha-forte-123" not in hash_
    assert hash_.startswith("$2a$12$")  # bcrypt, cost 12


def test_salt_e_por_usuario(db, user):
    outro = "u_" + uuid.uuid4().hex[:10]
    outro_id = security.create_user(db, outro, "senha-forte-123")
    hashes = db.execute(
        text("SELECT password_hash FROM users WHERE id = ANY(:ids)"),
        {"ids": [user[1], outro_id]},
    ).scalars().all()
    db.rollback()
    assert hashes[0] != hashes[1]


def test_login_com_senha_correta(db, user):
    username, user_id = user
    assert security.check_password(db, username, "senha-forte-123") == user_id


def test_login_com_senha_errada(db, user):
    username, _ = user
    assert security.check_password(db, username, "outra-senha") is None


def test_login_com_usuario_inexistente(db):
    assert security.check_password(db, "nao_existe", "senha-forte-123") is None


def test_totp_secret_fica_cifrado(db, user):
    _, user_id = user
    security.set_totp_secret(db, user_id, "JBSWY3DPEHPK3PXP")
    raw = db.execute(
        text("SELECT totp_secret FROM users WHERE id = :id"), {"id": user_id}
    ).scalar_one()
    assert b"JBSWY3DPEHPK3PXP" not in bytes(raw)
    assert security.get_totp_secret(db, user_id) == "JBSWY3DPEHPK3PXP"


def test_backup_codes_so_hash_no_banco(db, user):
    _, user_id = user
    codes = security.create_backup_codes(db, user_id)
    assert len(codes) == 10
    hashes = db.execute(
        text("SELECT code_hash FROM backup_codes WHERE user_id = :id"), {"id": user_id}
    ).scalars().all()
    assert len(hashes) == 10
    assert all(h.startswith("$2a$") for h in hashes)
    assert not set(codes) & set(hashes)


def test_backup_code_e_de_uso_unico(db, user):
    _, user_id = user
    code = security.create_backup_codes(db, user_id)[0]
    assert security.use_backup_code(db, user_id, code) is True
    assert security.use_backup_code(db, user_id, code) is False


def test_backup_code_ignora_hifen(db, user):
    _, user_id = user
    code = security.create_backup_codes(db, user_id)[0]
    assert code[5] == "-"
    assert security.use_backup_code(db, user_id, code.replace("-", "")) is True


def test_backup_code_invalido(db, user):
    _, user_id = user
    security.create_backup_codes(db, user_id)
    assert security.use_backup_code(db, user_id, "aaaaaaaaaa") is False


@pytest.mark.parametrize("funcao", [
    "crypt(text, text)",
    "gen_salt(text, integer)",
    "pgp_sym_encrypt(text, text)",
    "pgp_sym_decrypt(bytea, text)",
])
def test_app_api_tem_execute_no_pgcrypto(db, funcao):
    assert db.execute(
        text("SELECT has_function_privilege('app_api', :f, 'EXECUTE')"), {"f": funcao}
    ).scalar_one()
