from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import security
from app.audit import log_event
from app.db import get_db
from app.errors import ApiError
from app.models import User
from app.schemas import LoginMfaOut, LoginOut, LoginRequest, UserCreate, UserOut
from app.tokens import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    MFA_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_mfa_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201, response_model=UserOut)
def register(body: UserCreate, db: Session = Depends(get_db)):
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
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
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
