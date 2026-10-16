"""Excepciones de dominio.

Todas heredan de `ErrorDeDominio`, que sabe cómo presentarse por HTTP: un
código estable (para que el cliente decida sin parsear textos), el estado HTTP
y un mensaje legible. El único handler de la API (`api/errores.py`) las
convierte en `{"error": {"codigo", "mensaje", "detalle"}}`.

El módulo no importa nada de FastAPI: el dominio no sabe que existe una API.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, ClassVar


class ErrorDeDominio(Exception):
    """Raíz de los errores que la aplicación sabe explicar."""

    codigo: ClassVar[str] = "error_de_dominio"
    http_status: ClassVar[int] = HTTPStatus.BAD_REQUEST
    mensaje_por_defecto: ClassVar[str] = "La operación no se pudo completar."

    def __init__(self, mensaje: str | None = None, **detalle: Any) -> None:
        self.mensaje = mensaje or self.mensaje_por_defecto
        self._detalle = detalle
        super().__init__(self.mensaje)

    def detalle(self) -> dict[str, Any]:
        """Datos estructurados que acompañan al error (sin el mensaje)."""
        return dict(self._detalle)


class CuadernoInvalido(ErrorDeDominio):
    """El notebook no respeta el contrato de marcadores."""

    codigo = "cuaderno_invalido"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY
    mensaje_por_defecto = "El notebook no tiene la estructura esperada."


class NotebookNoDisponible(ErrorDeDominio):
    """El archivo del notebook no existe o no se puede leer."""

    codigo = "notebook_no_disponible"
    http_status = HTTPStatus.SERVICE_UNAVAILABLE
    mensaje_por_defecto = "No se pudo leer el notebook."


class SeccionNoEncontrada(ErrorDeDominio):
    """No hay ninguna sección guardada con ese número."""

    codigo = "seccion_no_encontrada"
    http_status = HTTPStatus.NOT_FOUND
    mensaje_por_defecto = "La sección no existe."


class CuadernoNoSincronizado(ErrorDeDominio):
    """Todavía no se ha importado el notebook a la base de datos."""

    codigo = "cuaderno_no_sincronizado"
    http_status = HTTPStatus.CONFLICT
    mensaje_por_defecto = (
        "El notebook aún no se ha sincronizado. Lanza POST /api/v1/sincronizacion."
    )


class BaseDeDatosNoDisponible(ErrorDeDominio):
    """La base de datos no responde."""

    codigo = "base_de_datos_no_disponible"
    http_status = HTTPStatus.SERVICE_UNAVAILABLE
    mensaje_por_defecto = "La base de datos no responde."
