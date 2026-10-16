"""Cliente HTTP, presentación y configuración: sin NiceGUI de por medio."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import ValidationError

from app.cliente import ClienteApi, ErrorApi
from app.config import ConfiguracionUI, obtener_configuracion
from app.modelos import Ejecucion, Sincronizacion
from app.presentacion import (
    Accion,
    accion_para_tecla,
    filas_historial,
    resumen_sincronizacion,
    texto_ejecucion,
)
from tests.conftest import ApiFalsa

ConCliente = Callable[[Callable[[httpx.Request], httpx.Response]], ClienteApi]
TODAS_LAS_INTERFACES = "0.0.0.0"  # noqa: S104 - es lo que usa el contenedor


# --- Cliente ----------------------------------------------------------------


async def test_cliente_recorre_todos_los_endpoints(
    cliente_falso: ClienteApi, api: ApiFalsa
) -> None:
    assert (await cliente_falso.listar()).total == 2
    assert (await cliente_falso.listar("  generator ")).visibles == 1
    assert (await cliente_falso.seccion(2)).titulo.startswith("Generator")
    assert (await cliente_falso.cuaderno()).total_secciones == 2
    assert not (await cliente_falso.sincronizar()).hubo_cambios
    assert (await cliente_falso.ejecutar_seccion(1)).ok
    assert (await cliente_falso.ejecutar_cuaderno()).seccion is None
    assert [e.id for e in await cliente_falso.historial(1)] == [1]
    assert api.peticiones[0] == "GET /api/v1/secciones"


async def test_error_de_la_api_conserva_codigo_y_mensaje(cliente_falso: ClienteApi) -> None:
    with pytest.raises(ErrorApi) as error:
        await cliente_falso.seccion(99)
    assert (error.value.codigo, error.value.mensaje, error.value.status) == (
        "no_encontrado",
        "No existe.",
        404,
    )


async def test_api_caida(cliente_caido: ClienteApi) -> None:
    with pytest.raises(ErrorApi, match="No se pudo conectar") as error:
        await cliente_caido.listar()
    assert error.value.codigo == "api_no_disponible"


async def test_tiempo_agotado(cliente_con: ConCliente) -> None:
    def lento(peticion: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("lento", request=peticion)

    with pytest.raises(ErrorApi, match="tardó demasiado") as error:
        await cliente_con(lento).ejecutar_cuaderno()
    assert error.value.codigo == "tiempo_agotado"


@pytest.mark.parametrize(
    "respuesta",
    [httpx.Response(502, text="Bad Gateway"), httpx.Response(500, json={"otra": "cosa"})],
)
async def test_error_sin_contrato(cliente_con: ConCliente, respuesta: httpx.Response) -> None:
    with pytest.raises(ErrorApi, match=f"La API respondió {respuesta.status_code}") as error:
        await cliente_con(lambda _: respuesta).cuaderno()
    assert error.value.codigo == "respuesta_inesperada"


async def test_formato_inesperado(cliente_con: ConCliente) -> None:
    cliente = cliente_con(lambda _: httpx.Response(200, json=[{"id": "no es int"}]))
    with pytest.raises(ErrorApi, match="formato inesperado"):
        await cliente.historial(1)
    cliente = cliente_con(lambda _: httpx.Response(200, json={"total": 1}))
    with pytest.raises(ErrorApi, match="formato inesperado"):
        await cliente.listar()


def test_url_base_sin_barra_final() -> None:
    assert ClienteApi("http://api:8000/", 5).url_base == "http://api:8000"


# --- Presentación -----------------------------------------------------------


@pytest.mark.parametrize(
    ("tecla", "ctrl", "accion"),
    [
        ("F1", False, Accion.INTRODUCCION),
        ("F2", True, Accion.RESUMEN),
        ("F5", False, Accion.EJECUTAR),
        ("F5", True, Accion.EJECUTAR_TODO),
        ("/", False, Accion.FILTRAR),
        ("/", True, None),
        ("Escape", False, Accion.LIMPIAR_FILTRO),
        ("a", False, None),
    ],
)
def test_atajos(tecla: str, ctrl: bool, accion: Accion | None) -> None:
    assert accion_para_tecla(tecla, ctrl=ctrl) is accion


def _ejecucion(ok: bool, codigo: int | None) -> Ejecucion:
    return Ejecucion(
        id=7,
        seccion=1,
        salida="hola",
        codigo_salida=codigo,
        duracion_ms=12,
        ok=ok,
        creada_en=datetime(2026, 10, 15, 9, 30, 5, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("ok", "codigo", "estado"),
    [
        (True, 0, "correcta"),
        (False, None, "interrumpida por tiempo"),
        (False, 1, "con error (código 1)"),
    ],
)
def test_texto_ejecucion(ok: bool, codigo: int | None, estado: str) -> None:
    assert texto_ejecucion(_ejecucion(ok, codigo)) == f"# Ejecución {estado} en 12 ms\n\nhola"


def test_filas_historial() -> None:
    comunes = {"id": 7, "fecha": "2026-10-15 09:30:05", "duracion": "12 ms"}
    assert filas_historial([_ejecucion(True, 0), _ejecucion(False, None)]) == [
        comunes | {"resultado": "✔ correcta", "codigo": "0"},
        comunes | {"resultado": "✖ fallida", "codigo": "—"},
    ]


def test_resumen_sincronizacion() -> None:
    sin_cambios = Sincronizacion(
        creadas=[], actualizadas=[], sin_cambios=[1, 2], eliminadas=[], hubo_cambios=False
    )
    con_cambios = Sincronizacion(
        creadas=[3], actualizadas=[], sin_cambios=[1, 2], eliminadas=[4, 5], hubo_cambios=True
    )
    assert resumen_sincronizacion(sin_cambios) == "Sin cambios: 2 secciones al día."
    assert resumen_sincronizacion(con_cambios) == (
        "Sincronizado: 1 nuevas, 2 eliminadas, 2 sin cambios."
    )


# --- Configuración ----------------------------------------------------------


def test_configuracion_desde_el_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_URL", "http://api:8000")
    monkeypatch.setenv("UI_HOST", TODAS_LAS_INTERFACES)
    obtener_configuracion.cache_clear()
    try:
        config = obtener_configuracion()
    finally:
        obtener_configuracion.cache_clear()
    assert (config.api_url, config.ui_host, config.ui_puerto) == (
        "http://api:8000",
        TODAS_LAS_INTERFACES,
        8080,
    )
    assert config.tiempo_espera_api_s > 60


def test_sin_api_url_no_arranca(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API_URL", raising=False)
    with pytest.raises(ValidationError, match="api_url"):
        ConfiguracionUI(_env_file=None)  # type: ignore[call-arg]
