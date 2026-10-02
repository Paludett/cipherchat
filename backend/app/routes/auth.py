import uuid
from datetime import datetime, timezone

import pyotp
from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import security
from app.audit import log_event
from app.db import get_db
from app.deps import get_current_user, get_mfa_pending, nao_autenticado
from app.errors import ApiError
from app.models import RevokedToken, User
from app.ratelimit import BLOQUEIO_MINUTOS, LIMITE_AUTH, limite_excedido, limiter, login_bloqueado
from app.schemas import (
    BackupCodesOut,
    LoginMfaOut,
    LoginOut,
    LoginRequest,
    MfaCodeRequest,
    MfaRecoverRequest,
    MfaSetupOut,
    TokenOut,
    UserCreate,
    UserOut,
)
from app.tokens import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    MFA_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_mfa_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201, response_model=UserOut)
@limiter.limit(LIMITE_AUTH)
def register(body: UserCreate, request: Request, db: Session = Depends(get_db)):
    # Nao faz login, o frontend chama /auth/login em seguida
    try:
        user_id = security.create_user(db, body.username, body.password)
        db.commit()
    except ValueError:
        raise ApiError(400, "weak_password", "A senha deve ter pelo menos 8 caracteres.")
    except IntegrityError:
        raise ApiError(409, "username_taken", "Nome de usuário indisponível.")
    return db.get(User, user_id)


@router.post("/login", response_model=LoginOut | LoginMfaOut)
@limiter.limit(LIMITE_AUTH)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None

    if login_bloqueado(db, body.username, ip):
        return limite_excedido(request, BLOQUEIO_MINUTOS * 60)

    user_id = security.check_password(db, body.username, body.password)

    # Mesma resposta para usuario inexistente e senha errada
    if user_id is None:
        log_event(db, "login_failed", ip, details={
            "username": body.username, "reason": "invalid_credentials",
        })
        raise ApiError(401, "invalid_credentials", "Usuário ou senha inválidos.")

    user = db.get(User, user_id)

    # So chega aqui quem acertou a senha, entao nao vaza se o usuario existe
    if not user.is_active:
        log_event(db, "login_failed", ip, actor=user.id, details={
            "username": user.username, "reason": "account_disabled",
        })
        raise ApiError(403, "account_disabled", "Conta desativada.")

    # MFA ativo: devolve so o token parcial
    if user.totp_enabled:
        log_event(db, "login_mfa_pending", ip, actor=user.id)
        return LoginMfaOut(
            mfa_token=create_mfa_token(user),
            expires_in=MFA_TOKEN_EXPIRE_MINUTES * 60,
        )

    log_event(db, "login_success", ip, actor=user.id)
    return LoginOut(
        access_token=create_access_token(user),
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/mfa/setup", response_model=MfaSetupOut)
@limiter.limit(LIMITE_AUTH)
def mfa_setup(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else None

    if user.totp_enabled:
        raise ApiError(409, "mfa_already_enabled", "MFA já está ativo.")

    secret = pyotp.random_base32()
    security.set_totp_secret(db, user.id, secret)
    db.commit()
    log_event(db, "mfa_setup", ip, actor=user.id)

    uri = pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name=security.TOTP_ISSUER)
    return MfaSetupOut(secret=secret, otpauth_uri=uri)


@router.post("/mfa/activate", response_model=BackupCodesOut)
@limiter.limit(LIMITE_AUTH)
def mfa_activate(
    body: MfaCodeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else None
    secret = security.get_totp_secret(db, user.id)

    if user.totp_enabled or secret is None:
        raise ApiError(409, "mfa_not_pending", "Nenhum MFA aguardando ativação.")

    if not pyotp.TOTP(secret).verify(body.code, valid_window=1):
        log_event(db, "mfa_activate_failed", ip, actor=user.id)
        raise ApiError(401, "invalid_mfa_code", "Código inválido.")

    user.totp_enabled = True
    codes = security.create_backup_codes(db, user.id)
    db.commit()
    log_event(db, "mfa_activated", ip, actor=user.id)
    return BackupCodesOut(backup_codes=codes)


def _finish_mfa_login(db: Session, user: User, claims: dict, ip: str | None, action: str) -> TokenOut:
    db.add(RevokedToken(
        jti=uuid.UUID(claims["jti"]),
        expires_at=datetime.fromtimestamp(claims["exp"], timezone.utc),
    ))
    try:
        db.commit()
    except IntegrityError: 
        db.rollback()
        raise nao_autenticado()
    log_event(db, action, ip, actor=user.id)
    return TokenOut(
        access_token=create_access_token(user),
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/mfa/verify", response_model=TokenOut)
@limiter.limit(LIMITE_AUTH)
def mfa_verify(
    body: MfaCodeRequest,
    request: Request,
    pending: tuple[User, dict] = Depends(get_mfa_pending),
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else None
    user, claims = pending
    secret = security.get_totp_secret(db, user.id)

    if not pyotp.TOTP(secret).verify(body.code, valid_window=1):
        log_event(db, "mfa_verify_failed", ip, actor=user.id, details={"reason": "invalid_code"})
        raise ApiError(401, "invalid_mfa_code", "Código inválido.")

    return _finish_mfa_login(db, user, claims, ip, "mfa_verified")


@router.post("/mfa/recover", response_model=TokenOut)
@limiter.limit(LIMITE_AUTH)
def mfa_recover(
    body: MfaRecoverRequest,
    request: Request,
    pending: tuple[User, dict] = Depends(get_mfa_pending),
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else None
    user, claims = pending

    if not security.use_backup_code(db, user.id, body.backup_code):
        log_event(db, "mfa_recover_failed", ip, actor=user.id, details={"reason": "invalid_backup_code"})
        raise ApiError(401, "invalid_mfa_code", "Código inválido.")
    user.totp_enabled = False
    user.totp_secret = None
    return _finish_mfa_login(db, user, claims, ip, "mfa_recovered")
