"""Un único contrato de error para toda la API.

    {"error": {"codigo": "...", "mensaje": "...", "detalle": {...}}}

Los errores de dominio se registran con `warning` (son casos de negocio
previstos); cualquier otra excepción con `exception` (traza completa), y al
cliente solo le llega un mensaje genérico.
"""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)


def respuesta_error(
    status: int, codigo: str, mensaje: str, detalle: dict[str, Any] | None = None
) -> JSONResponse:
    cuerpo = {"error": {"codigo": codigo, "mensaje": mensaje, "detalle": detalle or {}}}
    return JSONResponse(status_code=status, content=jsonable_encoder(cuerpo))


def _campo(ubicacion: tuple[Any, ...]) -> str:
    return ".".join(map(str, ubicacion))


async def manejar_error(request: Request, error: Exception) -> JSONResponse:
    """El único handler: traduce cualquier excepción al contrato de error."""
    ruta = f"{request.method} {request.url.path}"
    match error:
        case ErrorDeDominio():
            logger.warning("%s -> %s: %s", ruta, error.codigo, error.mensaje)
            return respuesta_error(error.http_status, error.codigo, error.mensaje, error.detalle())
        case RequestValidationError():
            errores = [
                {"campo": _campo(e["loc"]), "mensaje": e["msg"], "tipo": e["type"]}
                for e in error.errors()
            ]
            logger.warning("%s -> validación: %s", ruta, errores)
            return respuesta_error(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "validacion",
                "La petición no es válida.",
                {"errores": errores},
            )
        case StarletteHTTPException(status_code=status):
            logger.warning("%s -> HTTP %d", ruta, status)
            frase = HTTPStatus(status).phrase
            return respuesta_error(status, frase.lower().replace(" ", "_"), str(error.detail))
        case _:
            logger.exception("%s -> error no controlado", ruta, exc_info=error)
            return respuesta_error(
                HTTPStatus.INTERNAL_SERVER_ERROR, "error_interno", "Error interno del servidor."
            )


def registrar_manejadores(app: FastAPI) -> None:
    for tipo in (ErrorDeDominio, RequestValidationError, StarletteHTTPException, Exception):
        app.add_exception_handler(tipo, manejar_error)
