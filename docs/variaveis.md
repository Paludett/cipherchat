# Variáveis de ambiente

Todas ficam no `.env` da raiz (modelo em [`.env.example`](../.env.example)), lido pelos três
serviços do compose via `env_file`. No Railway cada serviço tem as suas (ver
[deploy-railway.md](deploy-railway.md#variáveis)).

Gere senhas e segredos com:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

`token_urlsafe` só usa `A-Z a-z 0-9 - _`, então o valor pode ir direto nas URLs de conexão.

> **Atenção:** as senhas das roles aparecem duas vezes. `APP_API_PASSWORD` precisa ser a
> mesma que está dentro de `DATABASE_URL`, e `DB_ADMIN_PASSWORD` a mesma de
> `MIGRATION_DATABASE_URL`. Se divergirem, o backend não conecta.

## Banco (`db`)

| Variável | Obrigatória | Padrão | Uso |
|----------|:-----------:|--------|-----|
| `POSTGRES_DB` | sim | — | Nome do banco (`e2ee_chat`) |
| `POSTGRES_USER` | sim | — | Superusuário de bootstrap, só o initdb usa. O backend nunca conecta com ele |
| `POSTGRES_PASSWORD` | sim | — | Senha do superusuário |
| `DB_ADMIN_PASSWORD` | sim | — | Role `db_admin` (dona do schema, roda as migrations) |
| `APP_API_PASSWORD` | sim | — | Role `app_api` (a API, só DML) |
| `AUDITOR_PASSWORD` | sim | — | Role `auditor` (só lê `audit_log`) |
| `APP_API_CONNECTION_LIMIT` | sim | — | `CONNECTION LIMIT` da `app_api` |
| `APP_API_STATEMENT_TIMEOUT` | sim | — | `statement_timeout` da `app_api` (ex.: `5s`) |

Essas variáveis são lidas por `db/init/02_roles.sql` (`\getenv`) **só na primeira criação do
volume**. Mudou alguma depois? `docker compose down -v` e sobe de novo (apaga os dados).

## Backend

| Variável | Obrigatória | Padrão | Uso |
|----------|:-----------:|--------|-----|
| `DATABASE_URL` | sim | — | Conexão da API como `app_api` |
| `MIGRATION_DATABASE_URL` | sim | — | Conexão do Alembic como `db_admin` |
| `JWT_SECRET` | sim | — | Assina os JWT (HS256). Use 48+ bytes aleatórios |
| `JWT_ISSUER` | não | `e2ee-chat` | Claim `iss` |
| `JWT_AUDIENCE` | não | `e2ee-chat-web` | Claim `aud` do token de acesso |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | não | `15` | Validade do token de acesso |
| `TOTP_ENCRYPTION_KEY` | sim | — | Chave do `pgp_sym_encrypt` que cifra o `totp_secret`. Trocar depois invalida todo MFA já ativado |
| `ADMIN_USERNAME` | só no seed | — | Admin inicial criado por `python -m app.seed` |
| `ADMIN_PASSWORD` | só no seed | — | Senha do admin inicial (mín. 8 caracteres) |
| `AMBIENTE` | não | `DEV` | `PROD` desliga `/docs`, `/redoc` e `/openapi.json` (404) |
| `CORS_ORIGINS` | não | `http://localhost:5173` | Origens aceitas, separadas por vírgula |
| `LOG_FILE` | não | `logs/audit.log` | Arquivo do log JSON de auditoria |
| `FORWARDED_ALLOW_IPS` | só atrás de proxy | — | IPs do proxy em que o uvicorn confia para ler `X-Forwarded-For` |

### Limites contra DoS

Explicação de cada um em [seguranca.md](seguranca.md#limites-contra-dos).

| Variável | Padrão |
|----------|--------|
| `MAX_BODY_BYTES` | `65536` |
| `MAX_WS_FRAME_BYTES` | `131072` |
| `MAX_WS_TOTAL` | `100` |
| `MAX_PAGE_SIZE` | `100` |
| `DB_POOL_SIZE` | `5` |
| `DB_MAX_OVERFLOW` | `5` |
| `DB_POOL_TIMEOUT` | `10` |

`DB_POOL_SIZE + DB_MAX_OVERFLOW` precisa ficar abaixo de `APP_API_CONNECTION_LIMIT`.

## Frontend

| Variável | Padrão | Uso |
|----------|--------|-----|
| `VITE_API_URL` | `http://localhost:8000` | Base REST |
| `VITE_WS_URL` | `ws://localhost:8000/ws` | WebSocket |

Entram no bundle em tempo de build (no Railway, como `ARG` do Dockerfile). Mudou? Rebuild.
São públicas: nunca coloque segredo em variável `VITE_*`.
