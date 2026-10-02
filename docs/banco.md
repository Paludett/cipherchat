# Banco de dados

PostgreSQL 16 (`db/Dockerfile`), autenticação `scram-sha-256` inclusive no socket local, e
regras de acesso em `db/pg_hba.conf`.

## O que roda quando

| Etapa | Quando | O quê |
|-------|--------|-------|
| `db/init/01_schema.sql` | só na 1ª criação do volume | `CREATE EXTENSION pgcrypto` |
| `db/init/02_roles.sql` | só na 1ª criação do volume | roles `db_admin`, `app_api`, `auditor` e permissões do schema |
| `alembic upgrade head` | toda vez que o backend sobe | tabelas, GRANTs por tabela, triggers |

Como `db/init/` só roda em volume novo, qualquer mudança nele (ou nas senhas das roles no
`.env`) pede:

```bash
docker compose down -v          # APAGA os dados do banco
docker compose up --build
```

## pgcrypto

Habilitado em `db/init/01_schema.sql`. Se o volume já existia antes, ou o banco foi criado por
fora (outro provedor), habilite na mão como superusuário:

```bash
docker compose exec -e PGPASSWORD="$POSTGRES_PASSWORD" db \
    psql -U app -d e2ee_chat -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
```

Conferir:

```bash
docker compose exec -e PGPASSWORD="$POSTGRES_PASSWORD" db \
    psql -U app -d e2ee_chat -c "\dx pgcrypto"
```

A migration `0003` dá à `app_api` o `EXECUTE` nas funções que ela usa. Uso em
`backend/app/security.py`:

- Senha: `crypt(senha, gen_salt('bf', 12))`. Login compara `password_hash = crypt(senha_digitada, password_hash)`, nunca descriptografa.
- `totp_secret`: `pgp_sym_encrypt` com a chave `TOTP_ENCRYPTION_KEY` (só vem do `.env`).
- Backup codes: só o hash bcrypt fica no banco.

## Acesso só pela rede interna

O Postgres **não** publica porta no host, só é possível acessá-lo pela rede interna do
compose. Para abrir um psql:

```bash
docker compose exec -e PGPASSWORD="$POSTGRES_PASSWORD" db psql -U app -d e2ee_chat
```

O `pg_hba.conf` exige senha até pelo socket local, por isso o `PGPASSWORD`.

Para provar que o banco só é acessível pela rede interna (com o compose rodando):

```bash
./db/check_network.sh
```

Ele testa a conexão de dentro da rede do compose (aceita), se a porta 5432 do banco está
publicada no host (não deve estar) e a conexão de um container em outra rede docker (sem
resposta).

## Migrations

As tabelas são criadas pelo Alembic (`backend/alembic/versions/`), e o backend roda
`alembic upgrade head` sozinho ao subir. Os models SQLAlchemy ficam em `backend/app/models.py`.

| Migration | Conteúdo |
|-----------|----------|
| `0001_initial_schema` | `users`, `public_keys`, `backup_codes`, `audit_log`, `revoked_tokens` |
| `0002_roles_grants` | GRANTs por tabela para `app_api` e `auditor` |
| `0003_pgcrypto_grants` | `EXECUTE` nas funções do pgcrypto |
| `0004_audit_triggers` | triggers de auditoria em `users` e `public_keys` |

```bash
docker compose exec backend alembic upgrade head      # aplica
docker compose exec backend alembic downgrade base    # desfaz tudo
docker compose exec backend alembic revision -m "..." # nova migration
```

Se o volume foi criado antes das migrations (quando `db/init` ainda criava `users`), rode
`docker compose down -v` uma vez.

## Roles

Criadas em `db/init/02_roles.sql` (senhas vêm do `.env`); os GRANTs por tabela estão na
migration `0002`.

| Role | Uso | Privilégios |
|------|-----|-------------|
| `db_admin` | migrations (`MIGRATION_DATABASE_URL`) | dono do schema, único com DDL |
| `app_api` | backend (`DATABASE_URL`) | SELECT/INSERT/UPDATE/DELETE em `users`, `public_keys`, `backup_codes`; SELECT/INSERT em `audit_log`; SELECT/INSERT/DELETE em `revoked_tokens` |
| `auditor` | opcional | SELECT em `audit_log` |

Nenhuma é superuser nem `BYPASSRLS`, e o `PUBLIC` não tem acesso ao schema `public`.
`app_api` tem `CONNECTION LIMIT` e `statement_timeout` vindos do `.env` (ver
[seguranca.md](seguranca.md#limites-contra-dos)).

Para mostrar o que a `app_api` não consegue fazer (DROP, UPDATE no `audit_log`,
`COPY ... TO PROGRAM`):

```bash
docker compose exec -e PGPASSWORD="$APP_API_PASSWORD" db \
    psql -U app_api -d e2ee_chat -f /demo_app_api.sql
```

Volumes criados antes das roles precisam de `docker compose down -v`.

## Admin inicial (seed)

O `/auth/register` sempre cria `role = user`. O primeiro admin vem de `backend/app/seed.py`,
que lê `ADMIN_USERNAME` e `ADMIN_PASSWORD` do `.env` e usa a mesma validação e hash do
registro:

```bash
docker compose exec backend python -m app.seed
```

| Saída | Significado |
|-------|-------------|
| `admin 'admin' criado` | ok |
| `admin 'admin' ja existe, nada feito` | idempotente, rodar de novo não muda nada |
| `senha fraca, minimo de 8 caracteres` | ajuste `ADMIN_PASSWORD` e rode de novo |

Os outros admins são promovidos por ele em `PATCH /admin/users/{id}` (tela Admin).
