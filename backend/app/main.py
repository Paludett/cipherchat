import logging
import os

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.errors import ApiError, api_error_handler, validation_error_handler
from app import ws
from app.logger import logger
from app.ratelimit import limiter, rate_limit_handler
from app.routes import admin, auth, keys, users

DATABASE_URL = os.environ["DATABASE_URL"]
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

app = FastAPI(title="E2EE Chat API")
app.state.limiter = limiter

app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

# Status que viram alerta
ALERTAS = {
    401: (logging.CRITICAL, "access_denied"),
    403: (logging.CRITICAL, "access_denied"),
    404: (logging.WARNING, "reconnaissance"),
    429: (logging.WARNING, "rate_limited"),
}


@app.middleware("http")
async def auditar_requisicao(request: Request, call_next):
    response = await call_next(request)
    nivel, alerta = ALERTAS.get(response.status_code, (logging.INFO, None))
    logger.log(nivel, "http_request", extra={
        "ip": request.client.host if request.client else None,
        "endpoint": f"{request.method} {request.url.path}",
        "status": response.status_code,
        "alert": alerta,
    })
    return response


app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(keys.router)
app.include_router(admin.router)
app.include_router(ws.router)


@app.get("/health")
def health():
    # Checa a API e a conexao com o Postgres
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        db = "up"
    except Exception:
        db = "down"
    return {"api": "up", "db": db}
