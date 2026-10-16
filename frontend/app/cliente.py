"""Cliente HTTP de la API. Es la única vía del frontend hacia los datos.

Cualquier fallo (API caída, timeout, respuesta de error) se convierte en
`ErrorApi` con un mensaje legible: la página lo muestra como aviso en vez de
reventar.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.modelos import (
    Cuaderno,
    Ejecucion,
    ListaSecciones,
    SeccionDetalle,
    Sincronizacion,
)

_HISTORIAL = TypeAdapter(list[Ejecucion])


class ErrorApi(Exception):
    """La API no respondió o respondió con un error."""

    def __init__(self, mensaje: str, codigo: str = "api_no_disponible", status: int | None = None):
        self.mensaje = mensaje
        self.codigo = codigo
        self.status = status
        super().__init__(mensaje)


def _error_de_respuesta(respuesta: httpx.Response) -> ErrorApi:
    """Lee el contrato `{"error": {...}}`; si no viene, usa el estado HTTP."""
    try:
        error = respuesta.json()["error"]
        return ErrorApi(error["mensaje"], error["codigo"], respuesta.status_code)
    except (ValueError, KeyError, TypeError):
        return ErrorApi(
            f"La API respondió {respuesta.status_code}.",
            "respuesta_inesperada",
            respuesta.status_code,
        )


class ClienteApi:
    def __init__(
        self,
        url_base: str,
        tiempo_espera_s: float,
        transporte: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url_base = url_base.rstrip("/")
        self.tiempo_espera_s = tiempo_espera_s
        self._transporte = transporte  # inyectable: los tests usan httpx.MockTransport

    async def _pedir(self, metodo: str, ruta: str, **opciones: Any) -> Any:
        try:
            async with httpx.AsyncClient(
                base_url=self.url_base, timeout=self.tiempo_espera_s, transport=self._transporte
            ) as http:
                respuesta = await http.request(metodo, ruta, **opciones)
        except httpx.TimeoutException as error:
            raise ErrorApi("La API tardó demasiado en responder.", "tiempo_agotado") from error
        except httpx.HTTPError as error:
            raise ErrorApi(f"No se pudo conectar con la API ({self.url_base}).") from error
        if respuesta.is_error:
            raise _error_de_respuesta(respuesta)
        return respuesta.json()

    async def _modelo[M: BaseModel](self, tipo: type[M], metodo: str, ruta: str, **op: Any) -> M:
        datos = await self._pedir(metodo, ruta, **op)
        try:
            return tipo.model_validate(datos)
        except ValidationError as error:
            raise ErrorApi(
                "La API devolvió datos con un formato inesperado.", "respuesta_inesperada"
            ) from error

    async def listar(self, consulta: str = "") -> ListaSecciones:
        parametros = {"q": consulta.strip()} if consulta.strip() else {}
        return await self._modelo(ListaSecciones, "GET", "/api/v1/secciones", params=parametros)

    async def seccion(self, numero: int) -> SeccionDetalle:
        return await self._modelo(SeccionDetalle, "GET", f"/api/v1/secciones/{numero}")

    async def cuaderno(self) -> Cuaderno:
        return await self._modelo(Cuaderno, "GET", "/api/v1/cuaderno")

    async def sincronizar(self) -> Sincronizacion:
        return await self._modelo(Sincronizacion, "POST", "/api/v1/sincronizacion")

    async def ejecutar_seccion(self, numero: int) -> Ejecucion:
        return await self._modelo(Ejecucion, "POST", f"/api/v1/secciones/{numero}/ejecuciones")

    async def ejecutar_cuaderno(self) -> Ejecucion:
        return await self._modelo(Ejecucion, "POST", "/api/v1/cuaderno/ejecuciones")

    async def historial(self, numero: int) -> list[Ejecucion]:
        datos = await self._pedir("GET", f"/api/v1/secciones/{numero}/ejecuciones")
        try:
            return _HISTORIAL.validate_python(datos)
        except ValidationError as error:
            raise ErrorApi(
                "La API devolvió datos con un formato inesperado.", "respuesta_inesperada"
            ) from error
