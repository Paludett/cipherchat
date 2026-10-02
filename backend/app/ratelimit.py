"""
Rate limit (slowapi) e bloqueio temporario de login
"""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Session

from app.errors import error_response
from app.logger import logger
from app.models import AuditLog
from app.tokens import JWT_ALGORITHM, JWT_AUDIENCE, JWT_ISSUER, JWT_SECRET, MFA_AUDIENCE

LIMITE_AUTH = "5/minute"  # login, registro e MFA
LIMITE_GERAL = "60/minute"  # demais rotas
WS_MSGS_POR_SEGUNDO = 20

MAX_FALHAS_LOGIN = 5
BLOQUEIO_MINUTOS = 15


def chave_do_cliente(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            claims = jwt.decode(
                auth.removeprefix("Bearer "), JWT_SECRET, algorithms=[JWT_ALGORITHM],
                audience=[JWT_AUDIENCE, MFA_AUDIENCE], issuer=JWT_ISSUER,
            )
            return f"user:{claims['sub']}"
        except (jwt.InvalidTokenError, KeyError):
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=chave_do_cliente, default_limits=[LIMITE_GERAL])


def limite_excedido(request: Request, retry_after: int) -> JSONResponse:
    logger.warning("rate_limited", extra={
        "ip": get_remote_address(request),
        "endpoint": f"{request.method} {request.url.path}",
    })
    response = error_response(429, "rate_limited", "Muitas requisições. Tente novamente mais tarde.")
    response.headers["Retry-After"] = str(retry_after)
    return response


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    # Retry-After = tamanho da janela (5/minute -> 60s)
    return limite_excedido(request, exc.limit.limit.get_expiry())


def login_bloqueado(db: Session, username: str, ip: str | None) -> bool:
    desde = datetime.now(timezone.utc) - timedelta(minutes=BLOQUEIO_MINUTOS)
    falhas = db.scalar(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "login_failed",
            AuditLog.details["username"].astext == username,
            AuditLog.ip == cast(ip, INET),
            AuditLog.occurred_at >= desde,
        )
    )
    return falhas >= MAX_FALHAS_LOGIN
