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
