"""
Dependencies de autenticacao e autorizacao das rotas protegidas

401 sempre igual (unauthenticated), sem dizer o motivo
403 forbidden so quando o token e valido e o papel e insuficiente
"""
import uuid

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ApiError
from app.models import RevokedToken, User
from app.tokens import JWT_ALGORITHM, JWT_AUDIENCE, JWT_ISSUER, JWT_SECRET, MFA_AUDIENCE

bearer = HTTPBearer(auto_error=False)


def nao_autenticado() -> ApiError:
    return ApiError(401, "unauthenticated", "Não autenticado.")


def authenticate(db: Session, token: str) -> User:
    """Valida o JWT de acesso e devolve o usuario. Usado pelo HTTP e pelo WebSocket"""
    try:
        claims = jwt.decode(
            token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE, issuer=JWT_ISSUER,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
        user_id = uuid.UUID(claims["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError):  # expirado, iss/aud errado, adulterado, sub invalido
        raise nao_autenticado()
    # token de MFA ja cai no aud errado, o scope e segunda barreira
    if claims.get("scope") != "access":
        raise nao_autenticado()
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise nao_autenticado()
    return user


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise nao_autenticado()
    return authenticate(db, creds.credentials)


def get_mfa_pending(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> tuple[User, dict]:
    if creds is None:
        raise nao_autenticado()
    try:
        claims = jwt.decode(
            creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM],
            audience=MFA_AUDIENCE, issuer=JWT_ISSUER,
            options={"require": ["exp", "iss", "aud", "sub", "jti"]},
        )
        user_id = uuid.UUID(claims["sub"])
        jti = uuid.UUID(claims["jti"])
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise nao_autenticado()
    if claims.get("scope") != "mfa_pending":
        raise nao_autenticado()
    if db.get(RevokedToken, jti) is not None:
        raise nao_autenticado()
    user = db.get(User, user_id)
    if user is None or not user.is_active or not user.totp_enabled:
        raise nao_autenticado()
    return user, claims


def require_role(role: str):
    # O role vem do banco, nao do claim: rebaixar um admin vale na hora
    def check(user: User = Depends(get_current_user)) -> User:
        if user.role != role:
            raise ApiError(403, "forbidden", "Permissão insuficiente.")
        return user
    return check
