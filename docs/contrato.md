# Contrato Backend ↔ Frontend

- Base REST: `VITE_API_URL` (dev: `http://localhost:8000`)
- WebSocket: `VITE_WS_URL` (dev: `ws://localhost:8000/ws`)
- Todo corpo é JSON (`Content-Type: application/json`), UTF-8.
- Binário sempre em **base64 padrão** (RFC 4648 §4, com `=`), nunca base64url, exceto dentro do JWT.
- Datas em ISO 8601 UTC com `Z` (`2026-09-27T14:03:00Z`).
- IDs de usuário e de mensagem são UUID v4 em string (dificulta enumeração/BOLA).

---

## 1. Formato de erro

Toda resposta de erro (REST e WebSocket) usa o mesmo envelope:

```json
{ "error": { "code": "invalid_credentials", "message": "Usuário ou senha inválidos." } }
```

- `code`: estável, snake_case, o frontend faz `switch` nele.
- `message`: texto para humano, pode mudar. Nunca vaza detalhe interno (stack, SQL, caminhos, se o usuário existe). Stacktrace só no log do servidor.

| HTTP | `code` | Quando |
|------|--------|--------|
| 400 | `validation_error` | Corpo/parâmetro inválido (substitui o 422 padrão do FastAPI) |
| 400 | `weak_password` | Senha não atende a política mínima no registro |
| 401 | `unauthenticated` | Sem token, token malformado, assinatura/`iss`/`aud`/`scope` inválidos, expirado, revogado ou usuário inativo |
| 401 | `invalid_credentials` | Login com usuário ou senha errados (mesma resposta para os dois casos) |
| 401 | `invalid_mfa_code` | TOTP errado/já usado ou backup code inválido/já usado |
| 403 | `forbidden` | Token válido mas papel insuficiente (ex.: `user` em rota `admin`) |
| 403 | `account_disabled` | Login com senha correta mas `is_active = false` |
| 403 | `cannot_modify_self` | Admin tentando remover ou rebaixar a si mesmo |
| 404 | `not_found` | Recurso não existe (nunca 200 com corpo nulo) |
| 409 | `username_taken` | Registro com username já usado |
| 409 | `mfa_already_enabled` | Setup de MFA com MFA já ativo |
| 409 | `mfa_not_pending` | Ativação sem setup prévio |
| 413 | `payload_too_large` | Body acima do limite (`MAX_BODY_BYTES`) |
| 429 | `rate_limited` | Limite excedido. Resposta traz header `Retry-After` (segundos) |
| 500 | `internal_error` | Qualquer erro não tratado |

`/docs`, `/redoc` e `/openapi.json` retornam 404 quando `AMBIENTE=PROD`.

---

## 2. JWT

Assinado com **HS256** usando `JWT_SECRET` (PyJWT). Viaja em `Authorization: Bearer <token>` nas rotas REST.

### 2.1 Token de acesso (final)

```json
{
  "sub":   "3f6c1b8e-...-uuid-do-usuario",
  "role":  "user",
  "scope": "access",
  "iss":   "e2ee-chat",
  "aud":   "e2ee-chat-web",
  "iat":   1790000000,
  "exp":   1790000900,
  "jti":   "b1d2...-uuid-v4"
}
```

| Claim | Valor | Regra |
|-------|-------|-------|
| `sub` | `users.id` | Identifica o usuário |
| `role` | `user` \| `admin` | Autorização (ver coluna "Papel" na tabela de endpoints) |
| `scope` | `access` | Só `access` passa em rota protegida |
| `iss` | `JWT_ISSUER` (`e2ee-chat`) | **Validado**, diferente → 401 |
| `aud` | `JWT_AUDIENCE` (`e2ee-chat-web`) | **Validado**, diferente → 401 |
| `iat` | emissão | informativo |
| `exp` | `iat + ACCESS_TOKEN_EXPIRE_MINUTES` (15 min) | **Validado** |
| `jti` | UUID v4 | Usado para revogação no logout |

Validação no backend (`get_current_user`): algoritmo fixo em `["HS256"]` (rejeitar `none` e qualquer outro), exigir presença de todas as claims, validar `iss`, `aud`, `exp`, `scope == "access"`, `jti` fora da denylist e usuário existente com `is_active = true`. `require_role("admin")` checa `role` por cima disso.

### 2.2 Token parcial de MFA

Emitido só quando a senha está correta e o usuário tem MFA ativo. **Não acessa nenhuma rota protegida.**

```json
{
  "sub":   "uuid-do-usuario",
  "scope": "mfa_pending",
  "iss":   "e2ee-chat",
  "aud":   "e2ee-chat-mfa",
  "iat":   1790000000,
  "exp":   1790000300,
  "jti":   "uuid-v4"
}
```

- `scope = "mfa_pending"` e `aud` diferente (`e2ee-chat-mfa`): qualquer rota protegida rejeita com 401. Só `/auth/mfa/verify` e `/auth/mfa/recover` aceitam esse token.
- Sem `role`. Validade de **5 min**. Uso único: após verify/recover com sucesso o `jti` vai para a denylist.

### 2.3 Revogação

`POST /auth/logout` coloca o `jti` numa denylist até o `exp`. Tokens na denylist → 401 `unauthenticated`.

---

## 3. Chaves e criptografia (no cliente, Web Crypto API)

O servidor **nunca** vê chave privada, chave AES nem texto claro. Só armazena chave pública e repassa envelopes.

### 3.1 Par de chaves

- Algoritmo: **RSA-OAEP**, `modulusLength: 2048`, `publicExponent: 65537`, `hash: SHA-256`.
- Gerado no primeiro login no navegador e reaproveitado nos seguintes.
- Após o login o cliente compara o fingerprint local com o de `GET /users/me`. Sem chave local, gera par novo. Se o fingerprint local difere do servidor (outro navegador trocou a chave) ou é `null`, faz `PUT /keys/me` com a pública local (substitui a anterior). A privada local é mantida, então mensagens antigas desse navegador continuam legíveis.
- Chave pública exportada como `spki` (DER) → **base64**. É isso que vai para o servidor (`PUT /keys/me`).
- Chave privada fica no navegador (IndexedDB, por usuário, `extractable: false`). Nunca sai do cliente. Outro navegador = outra chave (limitação conhecida).

### 3.2 Fingerprint

`fingerprint = hex(SHA-256(bytes DER da SPKI))` em minúsculas, 64 caracteres.
Calculado sobre os **bytes** decodificados, não sobre a string base64. Servidor calcula e devolve; cliente **recalcula** a partir da chave recebida e compara (não confiar no valor do servidor). A UI mostra agrupado de 4 em 4 para verificação fora de banda e alerta se o fingerprint de um contato mudou desde a última conversa.

### 3.3 Envelope híbrido

Por mensagem:

1. Gera chave **AES-256-GCM** aleatória e `iv` de **12 bytes** aleatórios (novos a cada mensagem).
2. `ciphertext = AES-GCM(chave, iv, plaintext_utf8, additionalData = AAD)`: a tag de 16 bytes fica anexada ao fim do `ciphertext` (padrão Web Crypto).
3. `encrypted_key = RSA-OAEP(pública do destinatário, chave AES crua de 32 bytes)`.

**AAD** (amarra metadados ao ciphertext, impede o servidor de trocar remetente/destinatário/id):

```
AAD = utf8(`${msg_id}|${from}|${to}|${sent_at}`)
```

O remetente conhece o próprio `from` (é o `sub` do seu JWT). O destinatário monta o AAD com os campos recebidos; se alguém alterou qualquer um, a decifragem falha → "mensagem inválida", sem quebrar a app.

```json
{
  "type": "message",
  "msg_id": "9a1c...-uuid-v4",
  "to": "uuid-destinatario",
  "from": "uuid-remetente",
  "encrypted_key": "base64(256 bytes)",
  "iv": "base64(12 bytes)",
  "ciphertext": "base64(n + 16 bytes)",
  "sent_at": "2026-09-27T14:03:00Z"
}
```

| Campo | Quem preenche | Regra |
|-------|---------------|-------|
| `type` | cliente | sempre `"message"` |
| `msg_id` | cliente | UUID v4 novo por mensagem. Cliente descarta repetido (anti-replay) |
| `to` | cliente | `id` do destinatário |
| `from` | **servidor** | = `sub` do JWT da conexão. Se o cliente mandar, é **ignorado e sobrescrito** |
| `encrypted_key` | cliente | 256 bytes decodificado |
| `iv` | cliente | 12 bytes decodificado, nunca reutilizar |
| `ciphertext` | cliente | ≥ 16 bytes, máx. 64 KiB decodificado |
| `sent_at` | cliente | relógio do remetente, informativo (entra no AAD) |

`encrypted_key`, `iv` e `ciphertext` nunca vão para log, só metadados (`msg_id`, `from`, `to`, tamanhos).

Limitação conhecida: não há assinatura do remetente, então autenticidade depende do servidor preencher `from` corretamente. O AAD garante apenas que ninguém altera `from` **depois** que o remetente cifrou.

---

## 4. Endpoints REST

Papel: `—` = público, `user` = qualquer token de acesso válido, `admin` = `role == "admin"`, `mfa` = token parcial de MFA (`scope = mfa_pending`).

Listagens são paginadas: query `?limit=` (padrão 20, máx. 100) e `?offset=` (padrão 0); resposta `{items: [...], total}`.

| Método | Rota | Papel | Request | Response (sucesso) | Erros |
|--------|------|-------|---------|--------------------|-------|
| GET | `/health` | — | — | `200 {api, db}` | — |
| POST | `/auth/register` | — | `{username, password}` | `201 {id, username, role}` | 400, 400 `weak_password`, 409 `username_taken`, 429 |
| POST | `/auth/login` | — | `{username, password}` | `200` ver 5.1 | 400, 401 `invalid_credentials`, 403 `account_disabled`, 429 |
| POST | `/auth/mfa/verify` | mfa | `{code}` | `200 {access_token, token_type: "bearer", expires_in}` | 401 `unauthenticated`, 401 `invalid_mfa_code`, 429 |
| POST | `/auth/mfa/recover` | mfa | `{backup_code}` | `200 {access_token, token_type: "bearer", expires_in}` | 401 `unauthenticated`, 401 `invalid_mfa_code`, 429 |
| POST | `/auth/mfa/setup` | user | — | `200 {secret, otpauth_uri}` | 401, 409 `mfa_already_enabled` |
| POST | `/auth/mfa/activate` | user | `{code}` | `200 {backup_codes: [string × 10]}` | 400, 401, 401 `invalid_mfa_code`, 409 `mfa_not_pending` |
| POST | `/auth/logout` | user | — | `204` | 401 |
| GET | `/users/me` | user | — | `200 {id, username, role, mfa_enabled, fingerprint \| null}` | 401 |
| GET | `/users/online` | user | — | `200 [{id, username, fingerprint \| null}]` | 401 |
| PUT | `/keys/me` | user | `{public_key}` (SPKI base64) | `200 {fingerprint}` | 400, 401 |
| GET | `/keys/{user_id}` | user | — | `200 {user_id, username, public_key, fingerprint}` | 401, 404 |
| GET | `/admin/users` | admin | `?limit&offset` | `200 {items: [{id, username, role, is_active, mfa_enabled, created_at}], total}` | 401, 403 |
| PATCH | `/admin/users/{id}` | admin | `{is_active?, role?}` | `200 {id, username, role, is_active}` | 400, 401, 403, 403 `cannot_modify_self`, 404 |
| DELETE | `/admin/users/{id}` | admin | — | `204` | 401, 403, 403 `cannot_modify_self`, 404 |

Regras:
- Schemas Pydantic com `extra="forbid"` (campo não previsto → 400): protege contra mass assignment (ex.: mandar `role` no registro).
- `username`: 3–32 chars, `[a-zA-Z0-9_]`, único. `password`: mínimo 8 chars. Senha gravada com `crypt(senha, gen_salt('bf'))` (pgcrypto).
- `/auth/register` sempre cria com `role = "user"`. Admin inicial só via script de seed.
- `PUT /keys/me`: `user_id` vem **só do token**, nunca do body/URL. Não existe rota que altere a chave de outro usuário (BOLA). Chave validada: base64 válido, DER SPKI parseável, RSA de 2048 bits. Troca de chave é permitida, mas auditada; os contatos veem o alerta de fingerprint alterado (3.2).
- `/auth/register` não faz login: o frontend chama `/auth/login` em seguida.
- `GET /users/online` lista quem tem WebSocket conectado agora, **exceto o próprio usuário**. Carga inicial da lista; depois atualiza pelo evento `presence` (6.2).
- Backup codes: 10 códigos de 10 caracteres `[a-z0-9]`, exibidos como `xxxxx-xxxxx` (hífen ignorado na validação).
- `/auth/mfa/setup` gera secret TOTP (`pyotp.random_base32`), guarda cifrado com `totp_enabled=false` e devolve `otpauth_uri` (o frontend renderiza o QR). Chamar setup de novo antes de ativar gera novo secret.
- `/auth/mfa/activate` verifica o 1º código (prova de posse), liga `totp_enabled=true` e devolve **10 backup codes uma única vez**. No banco só o hash bcrypt.
- `/auth/mfa/recover`: backup code de uso único. Sucesso emite o JWT final e **desliga o MFA** (`totp_enabled=false`); o usuário precisa refazer setup + activate.
- TOTP: RFC 6238, SHA-1, 6 dígitos, período 30 s, `valid_window=1`. O mesmo código não é aceito duas vezes.
- `PATCH /admin/users/{id}`: só aceita `is_active` e `role` (`user` \| `admin`). Desativar derruba o WebSocket ativo do usuário.
- `/users/*` e `/keys/*` nunca devolvem `password_hash`, `totp_secret` nem `role` de outros.
- Todos os eventos de login, MFA, logout, troca de chave e ações admin são auditados.

---

## 5. Login em duas etapas

### 5.1 `POST /auth/login`

**MFA desativado** → token final direto:

```json
{ "mfa_required": false, "access_token": "<JWT acesso>", "token_type": "bearer", "expires_in": 900 }
```

**MFA ativo** → token parcial:

```json
{ "mfa_required": true, "mfa_token": "<JWT parcial>", "expires_in": 300 }
```

### 5.2 Fluxo

```
Cliente                                   Servidor
  | POST /auth/login {username,password}    |
  |---------------------------------------->| confere crypt()
  |   200 {mfa_required:true, mfa_token}    | emite JWT parcial (scope=mfa_pending, 5 min)
  |<----------------------------------------|
  | POST /auth/mfa/verify {code}            |
  | Authorization: Bearer <mfa_token>       |   (ou /auth/mfa/recover {backup_code})
  |---------------------------------------->| valida JWT parcial + TOTP
  |   200 {access_token, expires_in}        | revoga jti do parcial, emite JWT final
  |<----------------------------------------|
```

- Frontend guarda o `mfa_token` e o `access_token` só em memória, nunca em `localStorage`.
- `access_token` expirou → volta para o login (sem refresh token nesta versão).
- Rate limit: login, registro e MFA 5/min por IP e por usuário; API geral 60/min (chave = `sub` do JWT, fallback IP). Excesso → 429 com `Retry-After`.

---

## 6. WebSocket

URL: `VITE_WS_URL` (`ws://localhost:8000/ws`). Todas as mensagens são frames de texto JSON com campo `type`.

### 6.1 Autenticação no handshake

Browser não permite header `Authorization` no WebSocket, e token em query string vaza em log. Então o JWT vai na **primeira mensagem**:

1. Cliente abre `ws://.../ws` (servidor checa `Origin` contra `CORS_ORIGINS`; origem inválida → recusa o upgrade).
2. Cliente envia em até **5 s**:
   ```json
   { "type": "auth", "token": "<JWT acesso>" }
   ```
3. Servidor valida igual à REST (HS256, `iss`, `aud=e2ee-chat-web`, `scope=access`, `exp`, `jti` fora da denylist, usuário ativo).
   - OK → `{ "type": "auth_ok", "user_id": "<sub>" }` e registra o usuário como online.
   - Falha, timeout ou qualquer outra mensagem antes do `auth` → `{ "type": "error", "error": {"code": "unauthenticated", ...} }` e fecha com **1008**.
4. Token expira com a conexão aberta → servidor fecha com **1008**; cliente refaz login e reconecta.
5. Nova conexão do mesmo usuário acima do limite (`MAX_WS_PER_USER`) → recusada com **1008**.

### 6.2 Eventos

**Cliente → servidor**

| `type` | Payload | Efeito |
|--------|---------|--------|
| `auth` | `{token}` | ver 6.1 |
| `message` | envelope da seção 3.3 (sem `from`) | servidor valida, preenche `from` e entrega ao destinatário online |

**Servidor → cliente**

| `type` | Payload | Quando |
|--------|---------|--------|
| `auth_ok` | `{user_id}` | autenticação aceita |
| `message` | envelope completo (com `from`) | mensagem recebida |
| `sent` | `{msg_id}` | mensagem entregue ao destinatário (status "enviada") |
| `presence` | `{user_id, username, fingerprint \| null, online: bool}` | outro usuário conectou/desconectou (enviado a todos os conectados) |
| `error` | `{msg_id?, error: {code, message}}` | erro em um evento; conexão continua aberta (exceto 6.1 e rate limit) |

`code` extras no WebSocket:

| `code` | Quando |
|--------|--------|
| `validation_error` | envelope malformado, base64 inválido, tamanhos fora da regra, `to` igual ao próprio usuário |
| `offline` | destinatário não está conectado ou não existe (não diferencia, para não revelar quais ids existem). Mensagem **não** é guardada |
| `rate_limited` | mais de 20 mensagens/s por conexão. Reincidência → fecha com **1008** |

### 6.3 Entrega

- Só tempo real: servidor não guarda mensagens. Destinatário offline → erro `offline` ao remetente
- Histórico fica só no cliente.

### 6.4 Códigos de fechamento

| Código | Motivo |
|--------|--------|
| 1000 | Encerramento normal |
| 1008 | Não autenticado, token inválido/expirado, usuário desativado, conexões demais ou rate limit |
| 1009 | Frame acima do limite (`MAX_WS_FRAME_BYTES`) |
