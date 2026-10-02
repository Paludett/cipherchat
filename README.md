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

Ele testa a conexão de dentro da rede do compose (aceita), se a porta 5432 do banco
está publicada no host (não deve estar) e a conexão de um container em outra rede
docker (sem resposta).

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

## Rate limit

`backend/app/ratelimit.py`, com slowapi e contadores em memória (zeram ao reiniciar e valem
para um único processo uvicorn).

| Onde | Limite | Chave |
|------|--------|-------|
| `/auth/register`, `/auth/login`, `/auth/mfa/*` | 5/min por rota | `sub` do JWT, senão IP |
| Demais rotas HTTP | 60/min | `sub` do JWT, senão IP |
| WebSocket `/ws` | 20 mensagens/s por conexão | conexão |
| Login | 5 falhas em 15 min bloqueiam por 15 min | username + IP |

- A chave usa o `sub` só se a assinatura do JWT (de acesso ou de MFA) for válida. Assim um
  token forjado com outro `sub` não escapa do limite, cai no IP.
- Excesso no HTTP → `429 rate_limited` com `Retry-After` (tamanho da janela; 900 s no
  bloqueio de login). O CORS expõe o header para o frontend mostrar o tempo de espera.
- Bloqueio de login: conta os `login_failed` do par username + IP na `audit_log` e é checado
  antes da senha, então nem a senha certa entra desse IP durante o bloqueio. Ser por par
  impede que um atacante trave a conta do dono, que entra normalmente de outro IP. Vale
  também para username inexistente, sem revelar se a conta existe.
- WebSocket: o 1º excesso recebe `{"type": "error", "error": {"code": "rate_limited"}}` e a
  mensagem é descartada; a reincidência fecha com `1008`, reason `rate_limited` (o frontend
  usa o reason para reconectar em vez de deslogar).

Os testes zeram o limiter antes de cada teste (`backend/tests/conftest.py`), pois todos saem
do mesmo IP.

## Logs de auditoria

`backend/app/logger.py` grava uma linha JSON por evento em `backend/logs/audit.log`
(`RotatingFileHandler`, 5 MB × 5 arquivos; caminho muda com `LOG_FILE`) e também no stdout
(`docker compose logs backend`).

| Pergunta | Campo |
|----------|-------|
| Quem | `actor` (id do usuário), `ip` |
| O quê | `event_type` |
| Quando | `timestamp` (UTC, ISO-8601) |
| Onde | `endpoint` (método + path, sem query string), `target` |
| Resultado | `status`, `alert` |

Eventos:

- `log_event()` (`app/audit.py`) grava na tabela `audit_log` **e** no arquivo: `login_success`,
  `login_failed`, `login_mfa_pending`, `mfa_setup`, `mfa_activate_failed`, `mfa_activated`,
  `mfa_verified`, `mfa_verify_failed`, `mfa_recovered`, `mfa_recover_failed`, `key_changed`, `ws_connect`, `ws_disconnect`.
- `rate_limited` (só arquivo, `WARNING`): todo 429 no HTTP e todo excesso no WebSocket,
  com `ip`, `endpoint` e, no WebSocket, `actor`. Não vai para a `audit_log` para um ataque
  não virar um INSERT por requisição bloqueada.
- `message_routed` (só arquivo): `actor` = remetente, `target` = destinatário, `msg_id` e
  `status` (`delivered`, `offline` ou `invalid`).
- `http_request` (middleware em `app/main.py`, toda requisição HTTP):
  - 401/403 → `CRITICAL`, `alert: "access_denied"`
  - 404 → `WARNING`, `alert: "reconnaissance"` (varredura de rotas)
  - 429 → `WARNING`, `alert: "rate_limited"`
  - resto → `INFO`

Exemplo:

```json
{"timestamp": "2026-10-01T18:04:55.643968+00:00", "level": "CRITICAL", "event_type": "http_request", "ip": "127.0.0.1", "endpoint": "GET /users/me", "status": 401, "alert": "access_denied"}
{"timestamp": "2026-10-01T18:04:56.520638+00:00", "level": "INFO", "event_type": "message_routed", "actor": "c835bd10-060b-4345-bf61-b0c7f5b948a5", "target": "dbc36a2a-6ba5-41e2-9432-d6ef4a6d0491", "status": "delivered", "msg_id": "bc23bdfc-e2e0-49f6-964b-77c6f9892aa4"}
```

**Nunca logar:** senha (nem a tentada no login falho), JWT (de acesso ou de MFA), chave
privada, segredo TOTP, backup codes, e o conteúdo cifrado das mensagens (`encrypted_key`,
`iv`, `ciphertext`). Por isso o middleware não registra headers nem query string. Os testes
em `backend/tests/test_logging.py` checam que senha, token e conteúdo cifrado não aparecem
nas linhas.

### Triggers

Mudanças em `users` e `public_keys` são auditadas pelo próprio banco (migration `0004`), sem
depender da aplicação lembrar de logar:

- `INSERT`/`UPDATE`/`DELETE` disparam `audit_trigger()`, que grava na `audit_log` com
  `action` = `<tabela>_<operação>` (ex.: `users_update`), `target_id` = id da linha e
  `details = {"old": ..., "new": ..., "db_user": ...}` (`db_user` = role que conectou).
- `password_hash` e `totp_secret` são removidos antes de gravar.
- A função é `SECURITY DEFINER` (roda como `db_admin`) com `search_path` fixo.
- `actor` fica nulo: o banco não sabe qual usuário da app fez a mudança.
- A `app_api` só tem `SELECT`/`INSERT` na `audit_log`, então não consegue editar nem apagar
  o que o trigger gravou (append-only).

Testes em `backend/tests/test_audit_triggers.py`.
