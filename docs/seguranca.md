# Defesas da aplicação

## Limites contra DoS

Todos configuráveis no `.env` (valores padrão em [variaveis.md](variaveis.md#limites-contra-dos)).

| Limite | Variável | Onde | Ao estourar |
|--------|----------|------|-------------|
| Body HTTP | `MAX_BODY_BYTES` | middleware `limitar_body` (`main.py`) | `413 payload_too_large`; POST/PUT/PATCH sem `Content-Length` também |
| Frame WebSocket | `MAX_WS_FRAME_BYTES` | `ws.py` + `uvicorn --ws-max-size` | fecha com **1009** |
| WS por usuário | fixo em 1 | `ws.py` | nova conexão fecha com **1008** reason `already_connected`, a antiga continua (frontend mostra "aberto em outra aba" e tenta de novo) |
| WS no total | `MAX_WS_TOTAL` | `ws.py` | fecha com **1008** reason `server_full` (frontend reconecta) |
| Tamanho de página | `MAX_PAGE_SIZE` | dependency `paginar` (`deps.py`) | `400 validation_error` |
| Pool da API | `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT` | `db.py` | request espera até `DB_POOL_TIMEOUT` s por conexão |
| Conexões da role | `APP_API_CONNECTION_LIMIT` | `02_roles.sql` | Postgres recusa a conexão |
| Query lenta | `APP_API_STATEMENT_TIMEOUT` | `02_roles.sql` | Postgres cancela a query |

`DB_POOL_SIZE + DB_MAX_OVERFLOW` precisa ficar abaixo de `APP_API_CONNECTION_LIMIT`
(sobra para o `/health`). `MAX_WS_FRAME_BYTES` precisa ser maior que o maior envelope
válido (ciphertext de 64 KiB vira ~87 KB em base64).

Os dois limites da role vêm do `.env` pelo `\getenv` no init script: só valem em volume
novo, e o `.env` precisa ter as variáveis antes do `docker compose down -v`, senão o
script falha.

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

## Sessão no frontend

O token de acesso fica só em memória (React context, `frontend/src/auth.tsx`). Trade-off:
recarregar a página desloga o usuário (sem refresh token nesta versão), mas nenhum script
injetado (XSS) consegue ler o token de `localStorage`/`sessionStorage`. O logout descarta o token local e chama
`POST /auth/logout`, que grava o `jti` na `revoked_tokens`. A partir daí o token é recusado (401)
no REST e no handshake do `/ws`. Uma conexão WebSocket já aberta não é derrubada pelo logout,
mas o frontend a fecha ao sair.

## Senhas, TOTP e backup codes

Tudo via pgcrypto, em `backend/app/security.py`:

- Senha: `crypt(senha, gen_salt('bf', 12))`. Login compara `password_hash = crypt(senha_digitada, password_hash)`, nunca descriptografa.
- `totp_secret`: `pgp_sym_encrypt` com a chave `TOTP_ENCRYPTION_KEY` (só vem do `.env`).
- Backup codes: só o hash bcrypt fica no banco.

Mais detalhes do pgcrypto em [banco.md](banco.md#pgcrypto).
