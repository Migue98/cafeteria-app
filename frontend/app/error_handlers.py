"""Respuestas HTTP seguras para errores del frontend."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings
from .security import security_headers


def invalid_request_id(request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "title": "Encabezado inválido",
            "status": 422,
            "detail": "X-Request-ID debe ser un UUID válido.",
            "code": "VALIDATION_ERROR",
            "trace_id": request.state.trace_id,
        },
    )


def install_error_handlers(application: FastAPI, settings: Settings) -> None:
    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            {
                "title": "Error interno",
                "status": 500,
                "code": "INTERNAL_ERROR",
                "detail": "No pudimos completar la solicitud. Intenta de nuevo.",
                "trace_id": getattr(request.state, "trace_id", None),
            },
            status_code=500,
            headers={
                **security_headers(settings),
                "Cache-Control": "private, no-store",
            },
        )
