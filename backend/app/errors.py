"""
Erros da API no formato do contrato: {"error": {"code", "message"}}
"""
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.logger import logger

HTTP_ERRORS = {
    404: ("not_found", "Recurso não encontrado."),
    405: ("method_not_allowed", "Método não permitido."),
}


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message)


def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Substitui o 422 padrao, que ecoa o valor enviado (ex.: a senha) no campo "input"
    # Aqui so sai o nome dos campos invalidos, nunca o valor
    fields = sorted({str(err["loc"][-1]) for err in exc.errors()})
    return error_response(400, "validation_error", "Campos inválidos: " + ", ".join(fields))


def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code, message = HTTP_ERRORS.get(exc.status_code, ("http_error", "Erro na requisição."))
    return error_response(exc.status_code, code, message)


def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Vale para SQLAlchemyError e qualquer Exception: stacktrace so no log, cliente recebe 500 generico
    logger.error("internal_error", exc_info=exc, extra={
        "ip": request.client.host if request.client else None,
        "endpoint": f"{request.method} {request.url.path}",
        "status": 500,
    })
    return error_response(500, "internal_error", "Erro interno do servidor.")
