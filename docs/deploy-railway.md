# Deploy no Railway

Três serviços no mesmo projeto, todos do mesmo repo, com deploy automático a cada push na
`main`. Cada um builda o próprio Dockerfile:

| Serviço | Root directory | Watch paths | Domínio público | Volume |
|---------|----------------|-------------|-----------------|--------|
| `db` | `/db` | `/db/**` | **nenhum** | `/var/lib/postgresql/data` |
| `backend` | `/backend` | `/backend/**` | sim | — |
| `frontend` | `/frontend` | `/frontend/**` | sim | — |

- `db`: `db/Dockerfile` embute o mesmo `pg_hba.conf`, os scripts de `db/init/` e o
  scram-sha-256 usados no compose (no Railway não dá para montar arquivos). Sem domínio
  público nem TCP proxy, o Postgres só é alcançável pela rede privada (`db.railway.internal`).
  O `pg_hba.conf` continua como segunda camada.
- `backend`: o CMD do Dockerfile roda `alembic upgrade head` e sobe o uvicorn na `$PORT`
  com os mesmos limites do compose. Configure restart *On Failure*: no primeiro deploy ele
  pode subir antes do banco.
- `frontend`: o Dockerfile é multi-stage. O compose usa o estágio `dev`; o Railway builda o
  último, que serve o `dist/` com Caddy (`frontend/Caddyfile`, rotas do react-router caem no
  `index.html`).

Localmente, mudanças em `db/pg_hba.conf` ou `db/init/` agora pedem `docker compose up --build`.

## Variáveis

Gere senhas e segredos **novos** (não reaproveite os do `.env` local) com
`python -c "import secrets; print(secrets.token_urlsafe(32))"`, que também são seguros
dentro das URLs de conexão. `${{servico.VAR}}` é a sintaxe de referência do Railway.

`db`:

```
POSTGRES_DB=cipherchat
POSTGRES_USER=app
POSTGRES_PASSWORD=...
DB_ADMIN_PASSWORD=...
APP_API_PASSWORD=...
AUDITOR_PASSWORD=...
APP_API_CONNECTION_LIMIT=20
APP_API_STATEMENT_TIMEOUT=5s
# O volume vem com lost+found e o initdb recusa diretório não vazio
PGDATA=/var/lib/postgresql/data/pgdata
```

`backend`:

```
DATABASE_URL=postgresql://app_api:${{db.APP_API_PASSWORD}}@${{db.RAILWAY_PRIVATE_DOMAIN}}:5432/${{db.POSTGRES_DB}}
MIGRATION_DATABASE_URL=postgresql://db_admin:${{db.DB_ADMIN_PASSWORD}}@${{db.RAILWAY_PRIVATE_DOMAIN}}:5432/${{db.POSTGRES_DB}}
JWT_SECRET=...
TOTP_ENCRYPTION_KEY=...
ADMIN_USERNAME=admin
ADMIN_PASSWORD=...
AMBIENTE=PROD
CORS_ORIGINS=https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}
# IPs do proxy do Railway em que o uvicorn confia para ler X-Forwarded-For
FORWARDED_ALLOW_IPS=...
```

Os limites contra DoS (`MAX_*`, `DB_POOL_*`) usam os padrões do código se não forem definidos.

`frontend` (entram no bundle durante o build, como `ARG` do Dockerfile):

```
VITE_API_URL=https://${{backend.RAILWAY_PUBLIC_DOMAIN}}
VITE_WS_URL=wss://${{backend.RAILWAY_PUBLIC_DOMAIN}}/ws
```

## Depois do primeiro deploy

Admin inicial, uma vez:

```bash
railway ssh --service backend
python -m app.seed
```

No Railway só o stdout persiste (`railway logs --service backend`); o `logs/audit.log` do
container some a cada deploy. A tabela `audit_log` fica no volume do banco.

**A validar no primeiro deploy:**

- [ ] o backend conecta no `db` pela regra `samenet` do `pg_hba.conf` (a rede privada do
  Railway pode não cair na mesma sub-rede; nesse caso, adicionar uma linha com a faixa
  privada logo abaixo da `samenet`)
- [ ] `FORWARDED_ALLOW_IPS`: o `ip` do `audit_log` é o do cliente, não o do proxy, e um
  `X-Forwarded-For` forjado pelo cliente não troca o IP (senão o rate limit por IP é burlado)
- [ ] fluxo completo: registro, MFA, chat via `wss`
