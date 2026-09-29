# E2EE Chat

Monorepo do trabalho de Segurança.

```
backend/    FastAPI (API, WebSocket, JWT, MFA)
frontend/   React + Vite + TypeScript (criptografia no cliente)
db/         pg_hba.conf e scripts SQL de inicialização
```

## Subindo

```bash
cp .env.example .env     # ajuste as senhas e o JWT_SECRET
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend:  http://localhost:8000/health

O Postgres **não** publica porta no host, só é possivel acessa-lo pela rede interna do
compose. Para abrir um psql use:

```bash
docker compose exec -e PGPASSWORD="$POSTGRES_PASSWORD" db psql -U app -d e2ee_chat
```

o `pg_hba.conf` exige senha até pelo socket local, por isso temos que usar o `PGPASSWORD`

Os scripts de `db/init/` rodam apenas na primeira criação do volume. Para
reaplicá-los, primeiro use `docker compose down -v`.

## Migrations

As tabelas são criadas pelo Alembic (`backend/alembic/versions/`), e o backend roda
`alembic upgrade head` sozinho ao subir. `db/init/` só habilita a extensão `pgcrypto` e cria as roles.
Os models SQLAlchemy ficam em `backend/app/models.py`.

```bash
docker compose exec backend alembic upgrade head      # aplica
docker compose exec backend alembic downgrade base    # desfaz tudo
docker compose exec backend alembic revision -m "..." # nova migration
```

Se o volume foi criado antes das migrations (quando `db/init` ainda criava `users`),
rode `docker compose down -v` uma vez.

## Roles do banco

Criadas em `db/init/02_roles.sql` (senhas vêm do `.env`); os GRANTs por tabela estão
na migration `0002`.

| Role | Uso | Privilégios |
|------|-----|-------------|
| `db_admin` | migrations (`MIGRATION_DATABASE_URL`) | dono do schema, único com DDL |
| `app_api` | backend (`DATABASE_URL`) | SELECT/INSERT/UPDATE/DELETE em `users`, `public_keys`, `backup_codes`; SELECT/INSERT em `audit_log`; SELECT/INSERT/DELETE em `revoked_tokens` |
| `auditor` | opcional | SELECT em `audit_log` |

Nenhuma é superuser nem `BYPASSRLS`, e o `PUBLIC` não tem acesso ao schema `public`.
`app_api` tem `CONNECTION LIMIT 20`.

Para mostrar o que a `app_api` não consegue fazer (DROP, UPDATE no `audit_log`,
`COPY ... TO PROGRAM`):

```bash
docker compose exec -e PGPASSWORD="$APP_API_PASSWORD" db \
    psql -U app_api -d e2ee_chat -f /demo_app_api.sql
```

Volumes criados antes das roles precisam de `docker compose down -v`.
