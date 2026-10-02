import logging
import os

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.errors import ApiError, api_error_handler, error_response, validation_error_handler
from app import ws
from app.logger import logger
from app.routes import admin, auth, keys, users

DATABASE_URL = os.environ["DATABASE_URL"]
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", "65536"))

app = FastAPI(title="E2EE Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Status que viram alerta
ALERTAS = {
    401: (logging.CRITICAL, "access_denied"),
    403: (logging.CRITICAL, "access_denied"),
    404: (logging.WARNING, "reconnaissance"),
    429: (logging.WARNING, "rate_limited"),
}


@app.middleware("http")
async def limitar_body(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        tamanho = request.headers.get("content-length")
        if tamanho is None or not tamanho.isdigit() or int(tamanho) > MAX_BODY_BYTES:
            return error_response(413, "payload_too_large", "Corpo da requisição muito grande.")
    return await call_next(request)


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
