# Logs de auditoria

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
  `mfa_verified`, `mfa_verify_failed`, `mfa_recovered`, `mfa_recover_failed`, `key_changed`, `ws_connect`, `ws_disconnect`,
  `admin_user_updated` (`details`: `target` e `changes`), `admin_user_deleted` (`target` e `username`)
  e `admin_modify_self_denied`. Nas ações admin o `actor` é o admin; o trigger de `users`
  guarda o antes/depois da linha.
- `rate_limited` (só arquivo, `WARNING`): todo 429 no HTTP e todo excesso no WebSocket,
  com `ip`, `endpoint` e, no WebSocket, `actor`. Não vai para a `audit_log` para um ataque
  não virar um INSERT por requisição bloqueada.
- `internal_error` (só arquivo, `ERROR`): erro não tratado no HTTP (500) ou no WebSocket
  (fecha com 1011), com o campo `stacktrace`. O cliente só recebe `internal_error` genérico,
  sem SQL, caminho ou stacktrace (handlers em `app/errors.py`).
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

## Triggers

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
