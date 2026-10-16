"""Rutas HTTP. Finas: validan, delegan en servicios/repositorio y serializan.

Ninguna ruta acepta código en el cuerpo: solo se ejecuta lo que ya está
guardado (una sección por número o el cuaderno completo).
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request

from app.api.dependencias import ConfigDep, RepositorioDep, SesionDep
from app.api.esquemas import (
    CuadernoEsquema,
    EjecucionEsquema,
    ListaSecciones,
    SeccionDetalle,
    SeccionResumen,
    SincronizacionEsquema,
)
from app.core.filtro import filtrar
from app.servicios.ejecucion import ejecutar_cuaderno, ejecutar_seccion
from app.servicios.sincronizacion import sincronizar

router = APIRouter(prefix="/api/v1", tags=["comparativo"])

NumeroSeccion = Annotated[int, Path(ge=1, description="Número del ejercicio (1, 2, ...).")]
Limite = Annotated[int | None, Query(ge=1, le=500, description="Máximo de ejecuciones.")]
Consulta = Annotated[str | None, Query(max_length=200, description="Texto a buscar.")]


@router.get("/secciones")
def listar_secciones(repositorio: RepositorioDep, q: Consulta = None) -> ListaSecciones:
    """Secciones con sus métricas. `q` filtra sin distinguir mayúsculas ni tildes."""
    todas = repositorio.listar_secciones()
    visibles = filtrar(todas, q)
    return ListaSecciones(
        total=len(todas),
        visibles=len(visibles),
        consulta=q,
        secciones=[SeccionResumen.de(seccion) for seccion in visibles],
    )


@router.get("/secciones/{numero}")
def detalle_seccion(numero: NumeroSeccion, repositorio: RepositorioDep) -> SeccionDetalle:
    """Sección completa: ambas mitades, explicación, referencia, epílogo y veredicto."""
    return SeccionDetalle.de(repositorio.obtener_seccion(numero))


@router.get("/cuaderno")
def cuaderno(repositorio: RepositorioDep) -> CuadernoEsquema:
    """Introducción y tabla resumen «qué reemplaza a qué»."""
    return CuadernoEsquema.de(repositorio.obtener_cuaderno(), repositorio.contar_secciones())


@router.post("/sincronizacion")
def sincronizacion(request: Request, sesion: SesionDep, config: ConfigDep) -> SincronizacionEsquema:
    """Reimporta el notebook. Idempotente y transaccional."""
    with request.app.state.cerrojo_sincronizacion:
        return SincronizacionEsquema.de(sincronizar(sesion, config.notebook_ruta))


@router.post("/secciones/{numero}/ejecuciones", status_code=HTTPStatus.CREATED)
def ejecutar_una_seccion(
    numero: NumeroSeccion, sesion: SesionDep, config: ConfigDep
) -> EjecucionEsquema:
    """Ejecuta la celda guardada (más el preludio de imports) y guarda el resultado."""
    ejecucion = ejecutar_seccion(sesion, numero, config.tiempo_limite_ejecucion_s)
    return EjecucionEsquema.de(ejecucion, numero)


@router.get("/secciones/{numero}/ejecuciones")
def historial_seccion(
    numero: NumeroSeccion, repositorio: RepositorioDep, config: ConfigDep, limite: Limite = None
) -> list[EjecucionEsquema]:
    """Ejecuciones de la sección, de la más reciente a la más antigua."""
    seccion = repositorio.obtener_seccion(numero)
    return [
        EjecucionEsquema.de(ejecucion, numero)
        for ejecucion in repositorio.historial(seccion.id, limite or config.limite_historial)
    ]


@router.post("/cuaderno/ejecuciones", status_code=HTTPStatus.CREATED)
def ejecutar_todo(sesion: SesionDep, config: ConfigDep) -> EjecucionEsquema:
    """Ejecuta el notebook completo, incluida la comprobación final de equivalencias."""
    return EjecucionEsquema.de(ejecutar_cuaderno(sesion, config.tiempo_limite_ejecucion_s), None)


@router.get("/cuaderno/ejecuciones")
def historial_cuaderno(
    repositorio: RepositorioDep, config: ConfigDep, limite: Limite = None
) -> list[EjecucionEsquema]:
    """Ejecuciones del cuaderno completo, de la más reciente a la más antigua."""
    return [
        EjecucionEsquema.de(ejecucion, None)
        for ejecucion in repositorio.historial(None, limite or config.limite_historial)
    ]
