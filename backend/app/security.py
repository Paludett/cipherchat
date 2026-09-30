"""
Senhas, TOTP e backup codes via pgcrypto.

O hash e a cifra acontecem dentro do banco, a senha viaja so como parametro
bind e nunca e gravada nem logada em texto claro. Senha nunca e descriptografada,
o login compara crypt(senha_digitada, hash_gravado) com o hash gravado.
"""
import os
import secrets
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

BCRYPT_COST = 12
MIN_PASSWORD_LENGTH = 8
BACKUP_CODES_COUNT = 10
BACKUP_CODE_LENGTH = 10
BACKUP_CODE_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"

# Chave do pgp_sym_encrypt, so vem do ambiente
TOTP_ENCRYPTION_KEY = os.environ["TOTP_ENCRYPTION_KEY"]


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError("weak_password")


def create_user(db: Session, username: str, password: str) -> uuid.UUID:
    validate_password(password)
    return db.execute(
        text(
            "INSERT INTO users (username, password_hash) "
            "VALUES (:username, crypt(:password, gen_salt('bf', :cost))) "
            "RETURNING id"
        ),
        {"username": username, "password": password, "cost": BCRYPT_COST},
    ).scalar_one()


def check_password(db: Session, username: str, password: str) -> uuid.UUID | None:
    # crypt(senha, hash) reaproveita o salt do hash gravado
    return db.execute(
        text(
            "SELECT id FROM users "
            "WHERE username = :username AND password_hash = crypt(:password, password_hash)"
        ),
        {"username": username, "password": password},
    ).scalar_one_or_none()


def set_totp_secret(db: Session, user_id: uuid.UUID, secret: str) -> None:
    db.execute(
        text("UPDATE users SET totp_secret = pgp_sym_encrypt(:secret, :key) WHERE id = :id"),
        {"secret": secret, "key": TOTP_ENCRYPTION_KEY, "id": user_id},
    )


def get_totp_secret(db: Session, user_id: uuid.UUID) -> str | None:
    return db.execute(
        text("SELECT pgp_sym_decrypt(totp_secret, :key) FROM users WHERE id = :id"),
        {"key": TOTP_ENCRYPTION_KEY, "id": user_id},
    ).scalar_one_or_none()


def create_backup_codes(db: Session, user_id: uuid.UUID) -> list[str]:
    """Grava so o hash bcrypt. Os codigos em texto claro sao devolvidos uma unica vez."""
    codes = [
        "".join(secrets.choice(BACKUP_CODE_ALPHABET) for _ in range(BACKUP_CODE_LENGTH))
        for _ in range(BACKUP_CODES_COUNT)
    ]
    for code in codes:
        db.execute(
            text(
                "INSERT INTO backup_codes (user_id, code_hash) "
                "VALUES (:user_id, crypt(:code, gen_salt('bf', :cost)))"
            ),
            {"user_id": user_id, "code": code, "cost": BCRYPT_COST},
        )
    return codes


def use_backup_code(db: Session, user_id: uuid.UUID, code: str) -> bool:
    # Um update so confere o hash e marca como usado, sem corrida entre requests
    used = db.execute(
        text(
            "UPDATE backup_codes SET used_at = now() "
            "WHERE user_id = :user_id AND used_at IS NULL "
            "AND code_hash = crypt(:code, code_hash) "
            "RETURNING id"
        ),
        {"user_id": user_id, "code": code.replace("-", "")},
    ).first()
    return used is not None
