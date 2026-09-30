"""
Schemas de entrada e saida da API, separados dos models ORM (Mass Assignment)

Entrada: extra="forbid", campo nao previsto (ex.: role no registro) é rejeitado
Saida: so os campos declarados aqui saem na resposta, password_hash e totp_secret
nao existem em nenhum schema de saida
"""
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# Tipos com tamanho maximo, reaproveitados pelos schemas de entrada
Username = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_]{3,32}$")]
# 72 e o limite do bcrypt. O minimo fica em security.validate_password (weak_password)
Password = Annotated[str, Field(max_length=72)]
TotpCode = Annotated[str, Field(pattern=r"^[0-9]{6}$")]
# Exibido como xxxxx-xxxxx, o hifen é opcional
BackupCode = Annotated[str, Field(pattern=r"^[a-z0-9]{5}-?[a-z0-9]{5}$")]
# SPKI RSA-2048 em base64 tem ~392 chars
PublicKeyBase64 = Annotated[str, Field(max_length=1024)]
Role = Literal["user", "admin"]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    # Permite Schema.model_validate(objeto_orm)
    model_config = ConfigDict(from_attributes=True)


# ---------- Entrada ----------

class UserCreate(Entrada):
    # role, is_active e totp_* nunca vem do cliente
    username: Username
    password: Password


class LoginRequest(Entrada):
    username: Username
    password: Password


class MfaCodeRequest(Entrada):
    code: TotpCode


class MfaRecoverRequest(Entrada):
    backup_code: BackupCode


class PublicKeyUpdate(Entrada):
    public_key: PublicKeyBase64


class AdminUserUpdate(Entrada):
    is_active: bool | None = None
    role: Role | None = None


# ---------- Saida ----------

class UserOut(Saida):
    id: uuid.UUID
    username: str
    role: Role


class TokenOut(Saida):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class LoginOut(TokenOut):
    mfa_required: Literal[False] = False


class LoginMfaOut(Saida):
    mfa_required: Literal[True] = True
    mfa_token: str
    expires_in: int


class MfaSetupOut(Saida):
    secret: str
    otpauth_uri: str


class BackupCodesOut(Saida):
    backup_codes: list[str]


class UserMeOut(Saida):
    id: uuid.UUID
    username: str
    role: Role
    mfa_enabled: bool
    fingerprint: str | None


class OnlineUserOut(Saida):
    # Sem role, /users/* nao devolve papel de outros usuarios
    id: uuid.UUID
    username: str
    fingerprint: str | None


class FingerprintOut(Saida):
    fingerprint: str


class PublicKeyOut(Saida):
    user_id: uuid.UUID
    username: str
    public_key: str
    fingerprint: str


class AdminUserOut(Saida):
    id: uuid.UUID
    username: str
    role: Role
    is_active: bool
    # No model a coluna se chama totp_enabled
    mfa_enabled: bool = Field(validation_alias="totp_enabled")
    created_at: datetime


class AdminUserPage(Saida):
    items: list[AdminUserOut]
    total: int


class AdminUserUpdatedOut(Saida):
    id: uuid.UUID
    username: str
    role: Role
    is_active: bool
