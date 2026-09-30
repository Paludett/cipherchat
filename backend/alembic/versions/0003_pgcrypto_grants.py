"""EXECUTE nas funcoes do pgcrypto para app_api

O login usa crypt() e gen_salt(), o totp_secret usa pgp_sym_encrypt()/decrypt().
O grant explicito deixa registrado que a role precisa dessas funcoes.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCTIONS = (
    "crypt(text, text)",
    "gen_salt(text, integer)",
    "pgp_sym_encrypt(text, text)",
    "pgp_sym_decrypt(bytea, text)",
)


def upgrade() -> None:
    for fn in FUNCTIONS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO app_api")


def downgrade() -> None:
    for fn in FUNCTIONS:
        op.execute(f"REVOKE EXECUTE ON FUNCTION {fn} FROM app_api")
