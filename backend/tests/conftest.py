"""Fixtures comunes.

Base de datos: SQLite en memoria por defecto. Si el entorno trae un
`DATABASE_URL` (el job `test-postgres` del CI), se usa esa base real; en ese
caso el esquema lo crea `alembic upgrade head` antes de lanzar pytest y aquí
`create_all` no hace nada.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session

from app.config import Configuracion
from app.data.db import crear_fabrica, crear_motor
from app.data.modelos import Base, Cuaderno, Ejecucion, Seccion
from app.main import crear_app

RAIZ_REPO = Path(__file__).resolve().parents[2]
NOTEBOOK_REAL = RAIZ_REPO / "datos" / "python_declarativo.ipynb"
URL_POR_DEFECTO = "sqlite+pysqlite:///:memory:"


def _url() -> str:
    return Configuracion.model_validate(
        {"database_url": os.environ.get("DATABASE_URL", URL_POR_DEFECTO), "notebook_ruta": "."}
    ).database_url


@pytest.fixture(scope="session")
def motor() -> Iterator[Engine]:
    motor = crear_motor(_url())
    Base.metadata.create_all(motor)
    yield motor
    motor.dispose()


def _vaciar(motor: Engine) -> None:
    with motor.begin() as conexion:
        for modelo in (Ejecucion, Seccion, Cuaderno):
            conexion.execute(delete(modelo))


@pytest.fixture(autouse=True)
def _base_limpia(request: pytest.FixtureRequest) -> Iterator[None]:
    """Cada test que usa la base de datos empieza y termina con las tablas vacías.

    Antes y después: con Postgres la base sobrevive entre corridas, y un test
    abortado a medias no debe contaminar al siguiente.
    """
    if "motor" not in request.fixturenames:
        yield
        return
    motor: Engine = request.getfixturevalue("motor")
    _vaciar(motor)
    yield
    _vaciar(motor)


@pytest.fixture
def sesion(motor: Engine) -> Iterator[Session]:
    with crear_fabrica(motor)() as sesion:
        yield sesion


@pytest.fixture
def configuracion() -> Callable[..., Configuracion]:
    """Fábrica de configuraciones de test (sin leer ningún `.env`)."""

    def construir(**cambios: Any) -> Configuracion:
        valores = {
            "database_url": _url(),
            "notebook_ruta": NOTEBOOK_REAL,
            "sincronizar_al_arrancar": False,
            "tiempo_limite_ejecucion_s": 60,
        } | cambios
        return Configuracion(_env_file=None, **valores)  # type: ignore[call-arg]

    return construir


@pytest.fixture
def app(motor: Engine, configuracion: Callable[..., Configuracion]) -> FastAPI:
    return crear_app(configuracion(), motor=motor)


@pytest.fixture
def cliente(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as cliente:
        yield cliente


@pytest.fixture
def cliente_sincronizado(cliente: TestClient) -> TestClient:
    respuesta = cliente.post("/api/v1/sincronizacion")
    assert respuesta.status_code == 200, respuesta.text
    return cliente


# --- Notebooks sintéticos ---------------------------------------------------


def celda(tipo: str, texto: str | list[str]) -> dict[str, Any]:
    return {"cell_type": tipo, "metadata": {}, "source": texto}


def codigo_seccion(
    imperativo: str = "x = []\nfor i in range(3):\n    x.append(i)",
    declarativo: str = "y = list(range(3))",
    epilogo: str = 'print("iguales:", x == y)',
    referencia: bool = True,
) -> str:
    bloque = (
        "# ====\n# MÉTODOS Y CONSTRUCCIONES USADOS EN ESTA CELDA\n# ====\n"
        "# range(n)\n#     Secuencia perezosa.\n# ====\n"
        if referencia
        else ""
    )
    return (
        f"{bloque}# --- Imperativo ---\n{imperativo}\n\n"
        f"# --- Declarativo ---\n{declarativo}\n\n{epilogo}\n"
    )


def notebook(*celdas: dict[str, Any]) -> str:
    return json.dumps({"cells": list(celdas), "nbformat": 4, "nbformat_minor": 5})


def notebook_minimo(secciones: int = 2) -> str:
    """Intro, preludio, `secciones` ejercicios y la tabla resumen."""
    ejercicios = [
        celda_
        for n in range(1, secciones + 1)
        for celda_ in (
            celda("markdown", f"## {n}. Ejercicio {n}\n\nExplicación del ejercicio {n}."),
            celda("code", codigo_seccion(declarativo=f"y = list(range(3))  # {n}")),
        )
    ]
    return notebook(
        celda("markdown", "# Título\n\nIntroducción del cuaderno."),
        celda("code", 'import sys\nprint("Python", sys.version.split()[0])'),
        *ejercicios,
        celda(
            "markdown",
            "## Resumen\n\n| Imperativo | Declarativo |\n|---|---|\n"
            "| `for` + `append` | comprehension |\n\nNota final.",
        ),
        celda("code", 'print("fin")'),
    )
