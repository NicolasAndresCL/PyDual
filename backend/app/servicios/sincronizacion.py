"""Caso de uso: reimportar el notebook a la base de datos."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.errores import NotebookNoDisponible
from app.core.parser import parsear_cuaderno
from app.data.repositorio import Repositorio, ResultadoSincronizacion

logger = logging.getLogger(__name__)


def leer_notebook(ruta: Path) -> str:
    try:
        return ruta.read_text(encoding="utf-8")
    except OSError as error:
        raise NotebookNoDisponible(
            f"No se pudo leer el notebook: {error.strerror or error}", ruta=str(ruta)
        ) from error


def sincronizar(sesion: Session, ruta: Path) -> ResultadoSincronizacion:
    """Lee, parsea y guarda el notebook en una única transacción.

    El parseo ocurre **antes** de tocar la BD: si el notebook está roto se lanza
    `CuadernoInvalido` y no se ha escrito nada. Si falla la escritura, el
    `rollback` deja la BD como estaba. Repetirla sin cambios no escribe nada.
    """
    cuaderno = parsear_cuaderno(leer_notebook(ruta))
    resultado = Repositorio(sesion).sincronizar(cuaderno)
    sesion.commit()
    plan = resultado.plan
    logger.info(
        "Sincronización: %d nuevas, %d actualizadas, %d sin cambios, %d eliminadas.",
        len(plan.crear),
        len(plan.actualizar),
        len(plan.sin_cambios),
        len(plan.eliminar),
    )
    return resultado
