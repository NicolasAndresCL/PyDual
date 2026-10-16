"""Dependencias de FastAPI: configuración y sesión por petición."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import Configuracion
from app.data.repositorio import Repositorio


def obtener_config(request: Request) -> Configuracion:
    return request.app.state.configuracion


def obtener_sesion(request: Request) -> Iterator[Session]:
    """Una sesión por petición. Al cerrarse sin `commit`, se descarta todo."""
    with request.app.state.fabrica_sesiones() as sesion:
        yield sesion


def obtener_repositorio(sesion: Annotated[Session, Depends(obtener_sesion)]) -> Repositorio:
    return Repositorio(sesion)


ConfigDep = Annotated[Configuracion, Depends(obtener_config)]
SesionDep = Annotated[Session, Depends(obtener_sesion)]
RepositorioDep = Annotated[Repositorio, Depends(obtener_repositorio)]
