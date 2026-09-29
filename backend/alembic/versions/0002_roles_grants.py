"""grants por tabela para app_api e auditor

As roles sao criadas em db/init/02_roles.sql. Aqui ficam so os GRANTs, porque
as tabelas so existem depois da migration 0001.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # CRUD completo nas tabelas de negocio
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON users, public_keys, backup_codes TO app_api")

    # Log de auditoria e append-only: sem UPDATE nem DELETE
    op.execute("GRANT SELECT, INSERT ON audit_log TO app_api")
    op.execute("GRANT SELECT ON audit_log TO auditor")

    # Denylist de tokens: registra o jti, consulta e limpa os expirados
    op.execute("GRANT SELECT, INSERT, DELETE ON revoked_tokens TO app_api")


def downgrade() -> None:
    op.execute("REVOKE ALL ON revoked_tokens FROM app_api")
    op.execute("REVOKE ALL ON audit_log FROM app_api, auditor")
    op.execute("REVOKE ALL ON users, public_keys, backup_codes FROM app_api")
