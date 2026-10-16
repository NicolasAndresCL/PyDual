"""Configuración desde el entorno y comportamiento de la capa de datos."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.config import Configuracion, obtener_configuracion
from app.core.parser import parsear_cuaderno
from app.data.db import crear_motor, responde
from app.data.modelos import Ejecucion
from app.data.repositorio import Repositorio
from app.main import crear_app
from tests.conftest import notebook_minimo


@pytest.mark.parametrize(
    ("url", "esperada"),
    [
        ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("sqlite+pysqlite:///:memory:", "sqlite+pysqlite:///:memory:"),
    ],
)
def test_url_normalizada_al_driver_psycopg(url: str, esperada: str) -> None:
    config = Configuracion(_env_file=None, database_url=url, notebook_ruta=Path("x"))  # type: ignore[call-arg]
    assert config.database_url == esperada


def test_configuracion_desde_el_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/app")
    monkeypatch.setenv("NOTEBOOK_RUTA", "/datos/cuaderno.ipynb")
    monkeypatch.setenv("TIEMPO_LIMITE_EJECUCION_S", "15")
    obtener_configuracion.cache_clear()
    try:
        config = obtener_configuracion()
    finally:
        obtener_configuracion.cache_clear()
    assert config.notebook_ruta == Path("/datos/cuaderno.ipynb")
    assert config.tiempo_limite_ejecucion_s == 15


def test_sin_database_url_no_arranca(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        Configuracion(_env_file=None, notebook_ruta=Path("x"))  # type: ignore[call-arg]


def test_limites_de_la_configuracion() -> None:
    with pytest.raises(ValidationError):
        Configuracion(  # type: ignore[call-arg]
            _env_file=None, database_url="sqlite://", notebook_ruta=Path("x"), limite_historial=0
        )


def test_sqlite_en_archivo_activa_claves_foraneas(tmp_path: Path) -> None:
    motor = crear_motor(f"sqlite:///{(tmp_path / 'prueba.db').as_posix()}")
    try:
        assert responde(motor)
        with motor.connect() as conexion:
            assert conexion.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    finally:
        motor.dispose()


def test_borrar_una_seccion_borra_su_historial(sesion: Session) -> None:
    repositorio = Repositorio(sesion)
    repositorio.sincronizar(parsear_cuaderno(notebook_minimo(2)))
    seccion = repositorio.obtener_seccion(2)
    repositorio.registrar_ejecucion(
        seccion_id=seccion.id, salida="x", codigo_salida=0, duracion_ms=1, ok=True
    )
    sesion.commit()

    resultado = repositorio.sincronizar(parsear_cuaderno(notebook_minimo(1)))
    sesion.commit()

    assert resultado.plan.eliminar == (2,)
    assert sesion.scalars(select(Ejecucion)).all() == []


def test_el_esquema_tiene_las_tres_tablas(sesion: Session) -> None:
    tablas = set(inspect(sesion.get_bind()).get_table_names())
    assert {"seccion", "cuaderno", "ejecucion"} <= tablas


def test_motor_postgres_con_psycopg_v3_sin_conectar() -> None:
    motor = crear_motor("postgresql+psycopg://u:p@localhost:1/app")
    assert (motor.dialect.name, motor.dialect.driver) == ("postgresql", "psycopg")
    assert motor.pool._pre_ping  # noqa: SLF001 - detalle que importa: reconectar tras caídas


def test_la_app_crea_y_cierra_su_propio_motor(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'propia.db').as_posix()}"
    config = Configuracion(  # type: ignore[call-arg]
        _env_file=None, database_url=url, notebook_ruta=Path("x"), sincronizar_al_arrancar=False
    )
    app = crear_app(config)
    with TestClient(app) as cliente:
        assert cliente.get("/healthz").status_code == 200
    assert app.state.motor_propio
