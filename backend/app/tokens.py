"""
Emissao dos JWT (HS256, PyJWT)

Token de acesso: scope=access, aud=JWT_AUDIENCE, leva o role
Token parcial de MFA: scope=mfa_pending, aud propria, sem role, 5 min
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.models import User

JWT_ALGORITHM = "HS256"
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ISSUER = os.getenv("JWT_ISSUER", "cipherchat")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "cipherchat-web")
# token parcial nunca é passado como token de acesso
MFA_AUDIENCE = "cipherchat-mfa"

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
MFA_TOKEN_EXPIRE_MINUTES = 5


def _encode(claims: dict, audience: str, minutes: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        **claims,
        "iss": JWT_ISSUER,
        "aud": audience,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        # jti unico, usado na denylist do logout e no uso unico do token parcial
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_access_token(user: User) -> str:
    claims = {"sub": str(user.id), "role": user.role, "scope": "access"}
    return _encode(claims, JWT_AUDIENCE, ACCESS_TOKEN_EXPIRE_MINUTES)


def create_mfa_token(user: User) -> str:
    claims = {"sub": str(user.id), "scope": "mfa_pending"}
    return _encode(claims, MFA_AUDIENCE, MFA_TOKEN_EXPIRE_MINUTES)
