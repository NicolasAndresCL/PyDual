"""Punto de entrada de la API.

    uvicorn app.main:crear_app --factory --port 8000

Se usa una fábrica (y no un `app` global) para que importar el módulo no exija
tener el entorno configurado: los tests construyen la app con su propia
configuración.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.api.errores import registrar_manejadores
from app.api.esquemas import SaludEsquema
from app.api.rutas import router
from app.config import Configuracion, obtener_configuracion
from app.core.errores import BaseDeDatosNoDisponible, ErrorDeDominio
from app.data.db import crear_fabrica, crear_motor, responde
from app.data.repositorio import Repositorio
from app.servicios.sincronizacion import sincronizar

logger = logging.getLogger(__name__)


def sincronizar_si_vacia(app: FastAPI) -> None:
    """Primera carga: si no hay secciones, importa el notebook.

    Si falla (notebook ausente o roto) la API arranca igual y lo registra: la
    sincronización se puede relanzar con `POST /api/v1/sincronizacion`.
    """
    with app.state.fabrica_sesiones() as sesion:
        if Repositorio(sesion).contar_secciones():
            return
        try:
            sincronizar(sesion, app.state.configuracion.notebook_ruta)
        except ErrorDeDominio as error:
            logger.warning("No se pudo sincronizar al arrancar: %s", error.mensaje)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    if app.state.configuracion.sincronizar_al_arrancar:
        sincronizar_si_vacia(app)
    yield
    if app.state.motor_propio:
        app.state.motor.dispose()


def crear_app(configuracion: Configuracion | None = None, motor: Engine | None = None) -> FastAPI:
    """Construye la app. `motor` permite a los tests compartir su base de datos."""
    config = configuracion or obtener_configuracion()
    logging.basicConfig(
        level=config.nivel_log, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    app = FastAPI(
        title="Comparativo imperativo vs. declarativo",
        version="2.0.0",
        lifespan=ciclo_de_vida,
    )
    app.state.configuracion = config
    # Un motor inyectado es de quien lo creó: la app no lo cierra al apagarse.
    app.state.motor_propio = motor is None
    app.state.motor = motor or crear_motor(config.database_url)
    app.state.fabrica_sesiones = crear_fabrica(app.state.motor)
    app.state.cerrojo_sincronizacion = threading.Lock()

    registrar_manejadores(app)
    app.include_router(router)

    @app.get("/healthz", tags=["salud"])
    def salud() -> SaludEsquema:
        """Sana solo si la base de datos responde a `SELECT 1`; si no, 503."""
        try:
            responde(app.state.motor)
        except SQLAlchemyError as error:
            raise BaseDeDatosNoDisponible() from error
        return SaludEsquema(estado="ok", base_de_datos="ok")

    return app
