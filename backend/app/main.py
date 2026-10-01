import os

import psycopg
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.errors import ApiError, api_error_handler, validation_error_handler
from app import ws
from app.routes import admin, auth, keys, users

DATABASE_URL = os.environ["DATABASE_URL"]
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

app = FastAPI(title="E2EE Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
