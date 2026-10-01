"""triggers de auditoria em users e public_keys

Todo INSERT/UPDATE/DELETE nessas tabelas grava uma linha na audit_log com a
linha antiga e a nova em details, sem password_hash e totp_secret
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# tabela -> coluna que vira o target_id
TABLES = {"users": "id", "public_keys": "user_id"}


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION audit_trigger() RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public  -- evita sequestro de funcoes/tabelas via search_path
        AS $$
        DECLARE
            -- Segredos nunca vao para a auditoria
            old_row jsonb := to_jsonb(OLD) - 'password_hash' - 'totp_secret';
            new_row jsonb := to_jsonb(NEW) - 'password_hash' - 'totp_secret';
        BEGIN
            INSERT INTO audit_log (action, target_table, target_id, details)
            VALUES (
                TG_TABLE_NAME || '_' || lower(TG_OP),  -- ex: users_insert
                TG_TABLE_NAME,
                (coalesce(new_row, old_row) ->> TG_ARGV[0])::uuid,
                -- session_user e a role que conectou 
                jsonb_build_object('old', old_row, 'new', new_row, 'db_user', session_user)
            );
            RETURN NULL;  
        END
        $$
    """)

    for table, id_column in TABLES.items():
        op.execute(f"""
            CREATE TRIGGER {table}_audit
            AFTER INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION audit_trigger('{id_column}')
        """)


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TRIGGER {table}_audit ON {table}")
    op.execute("DROP FUNCTION audit_trigger()")
