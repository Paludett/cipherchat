import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from tests.test_auth import db, user  # noqa: F401 (fixtures)


def eventos(db, user_id):
    # Linhas que os triggers gravaram para esse usuario, da mais antiga para a mais nova
    return db.execute(
        text(
            "SELECT action, target_table, details FROM audit_log "
            "WHERE target_id = :id ORDER BY occurred_at, action"
        ),
        {"id": user_id},
    ).all()


def test_criar_usuario_gera_auditoria(db, user):
    username, user_id = user
    action, target_table, details = eventos(db, user_id)[0]
    assert action == "users_insert"
    assert target_table == "users"
    assert details["old"] is None
    assert details["new"]["username"] == username
    assert details["db_user"] == "app_api"


def test_atualizar_usuario_gera_auditoria(db, user):
    _, user_id = user
    db.execute(text("UPDATE users SET is_active = false WHERE id = :id"), {"id": user_id})
    db.commit()

    action, _, details = eventos(db, user_id)[-1]
    assert action == "users_update"
    assert details["old"]["is_active"] is True
    assert details["new"]["is_active"] is False


def test_remover_usuario_gera_auditoria(db, user):
    _, user_id = user
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    db.commit()

    action, _, details = eventos(db, user_id)[-1]
    assert action == "users_delete"
    assert details["old"]["id"] == str(user_id)
    assert details["new"] is None


def test_chave_publica_gera_auditoria(db, user):
    _, user_id = user
    db.execute(
        text("INSERT INTO public_keys (user_id, public_key, fingerprint) VALUES (:id, 'pk', 'fp')"),
        {"id": user_id},
    )
    db.commit()

    action, target_table, _ = eventos(db, user_id)[-1]
    assert action == "public_keys_insert"
    assert target_table == "public_keys"


def test_segredos_nunca_vao_para_auditoria(db, user):
    _, user_id = user
    db.execute(
        text("UPDATE users SET totp_secret = 'segredo'::bytea WHERE id = :id"), {"id": user_id}
    )
    db.commit()

    for _, _, details in eventos(db, user_id):
        for linha in (details["old"], details["new"]):
            if linha:
                assert "password_hash" not in linha
                assert "totp_secret" not in linha


@pytest.mark.parametrize("comando", [
    "UPDATE audit_log SET action = 'adulterado'",
    "DELETE FROM audit_log",
])
def test_app_api_nao_altera_auditoria(db, comando):
    with pytest.raises(ProgrammingError, match="permission denied"):
        db.execute(text(comando))
    db.rollback()
