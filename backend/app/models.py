import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# UUID gerado no banco em vez de id sequencial, dificulta enumeracao (BOLA).
_uuid_pk = dict(primary_key=True, server_default=text("gen_random_uuid()"))


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="role_valid"),
        CheckConstraint("username ~ '^[A-Za-z0-9_]{3,32}$'", name="username_format"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # bcrypt via pgcrypto, crypt(senha, gen_salt('bf'))
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # Guardado cifrado (bytes), nunca em texto claro.
    totp_secret: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    public_key: Mapped["PublicKey | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    backup_codes: Mapped[list["BackupCode"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class PublicKey(Base):
    __tablename__ = "public_keys"

    # user_id como PK, uma chave por usuario, PUT /keys/me substitui a anterior
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    public_key: Mapped[str] = mapped_column(Text, nullable=False)  # SPKI DER em base64
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="public_key")


class BackupCode(Base):
    __tablename__ = "backup_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)  # so o hash bcrypt
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="backup_codes")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **_uuid_pk)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    # Sem FK, o registro precisa sobreviver a exclusao do usuario.
    actor: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_table: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    # Denylist de jti, logout e uso unico do token mfa_pending.
    jti: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    # Depois de expirado o token ja e rejeitado pelo exp, a linha pode ser apagada.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
