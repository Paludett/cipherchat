# Testes

## Backend

Rodam contra o Postgres real do compose (roles, `pg_hba.conf`, migrations), então o `db`
precisa estar no ar:

```bash
docker compose up -d --wait db
docker compose run --rm --no-deps backend pytest tests
```

Suíte de ataques (SQLi, BOLA, Mass Assignment, JWT, rate limit, MFA, RBAC) em
`backend/tests/test_ataques.py`. Os casos de referência levam `@pytest.mark.attacks`:

```bash
docker compose run --rm --no-deps backend pytest tests/test_ataques.py     # todos
docker compose run --rm --no-deps backend pytest -m attacks -v             # só os de referência
```

Os testes zeram o rate limiter antes de cada teste (`backend/tests/conftest.py`), pois todos
saem do mesmo IP.

## Frontend

Vitest (inclui `src/crypto.test.ts`, que cifra e decifra envelopes com AAD):

```bash
docker compose exec frontend npm test
# ou fora do container
cd frontend && npm ci && npm test
```

## CI (`.github/workflows/devsecops.yml`)

Roda em todo PR e push na `main`:

| Job | O quê |
|-----|-------|
| `sast-bandit` | Bandit no backend, falha em severidade média ou alta |
| `sca-python` | `pip-audit` no `backend/requirements.txt` |
| `sca-node` | `npm audit` no frontend |
| `test-backend` | pytest contra o Postgres do compose, com `.env` de senhas aleatórias |
| `test-frontend` | vitest + build (`tsc` + `vite`) |
