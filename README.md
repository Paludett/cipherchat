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

Para provar que o banco só é acessível pela rede interna (com o compose rodando):

```bash
./db/check_network.sh
```

Ele testa a conexão de dentro da rede do compose (aceita), do host na porta 5432
(recusada) e de um container em outra rede docker (sem resposta).

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

## Senhas, TOTP e backup codes

Tudo via pgcrypto, em `backend/app/security.py`:

- Senha: `crypt(senha, gen_salt('bf', 12))`. Login compara `password_hash = crypt(senha_digitada, password_hash)`, nunca descriptografa.
- `totp_secret`: `pgp_sym_encrypt` com a chave `TOTP_ENCRYPTION_KEY` (so vem do `.env`).
- Backup codes: so o hash bcrypt fica no banco.

Testes (com o `db` no ar):

```bash
docker compose up -d --wait db
docker compose run --rm --no-deps backend pytest tests
```

## Sessão no frontend

O token de acesso fica só em memória (React context, `frontend/src/auth.tsx`). Trade-off:
recarregar a página desloga o usuário (sem refresh token nesta versão), mas nenhum script
injetado (XSS) consegue ler o token de `localStorage`/`sessionStorage`. O logout chama
`POST /auth/logout` (revoga o `jti`) e descarta o token local.

Ao adicionar dependência no frontend, rebuild: `docker compose up --build`
(o `node_modules` do container fica em volume anônimo, use `docker compose down` se não atualizar).
