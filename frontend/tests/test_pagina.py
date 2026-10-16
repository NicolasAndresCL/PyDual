"""Smoke tests de la página con el `User` simulado de NiceGUI (sin navegador)."""

from __future__ import annotations

from typing import Any

from nicegui import ui
from nicegui.testing import User

from app.cliente import ClienteApi
from app.config import ConfiguracionUI
from app.main import registrar
from app.pagina import Comparativo, construir
from tests.conftest import ApiFalsa

ESTADO: dict[str, Comparativo] = {}


def _registrar(ruta: str, cliente: ClienteApi) -> None:
    @ui.page(ruta)
    async def _pagina() -> None:
        ESTADO[ruta] = await construir(cliente)


def _tecla(nombre: str, *, ctrl: bool = False, accion: str = "keydown") -> dict[str, Any]:
    """Los mismos argumentos que emite `keyboard.js` en el navegador."""
    return {
        "action": accion,
        "altKey": False,
        "ctrlKey": ctrl,
        "shiftKey": False,
        "metaKey": False,
        "code": nombre,
        "key": nombre,
        "location": 0,
        "repeat": False,
    }


async def test_la_pagina_se_construye_con_la_primera_seccion(
    user: User, cliente_falso: ClienteApi
) -> None:
    _registrar("/", cliente_falso)
    await user.open("/")

    await user.should_see(" 1. List comprehension")
    await user.should_see("IMPERATIVO · el CÓMO, paso a paso")
    await user.should_see("DECLARATIVO · el QUÉ, como intención")
    await user.should_see("ahorra un 67 %")
    await user.should_see("3 líneas · 3 efectivas · 30 caracteres")
    await user.should_see("Por qué")
    await user.should_see("Historial")


async def test_seleccionar_otra_seccion(user: User, cliente_falso: ClienteApi) -> None:
    _registrar("/seleccion", cliente_falso)
    await user.open("/seleccion")

    user.find(marker="seccion-2").click()
    await user.should_see("Explicación de **Generator expression")
    assert ESTADO["/seleccion"].actual is not None
    assert ESTADO["/seleccion"].actual.numero == 2


async def test_ejecutar_seccion_muestra_salida_e_historial(
    user: User, cliente_falso: ClienteApi, api: ApiFalsa
) -> None:
    _registrar("/ejecutar", cliente_falso)
    await user.open("/ejecutar")

    user.find(marker="ejecutar").click()
    await user.should_see("# Ejecución correcta en 42 ms\n\niguales: True")
    assert "POST /api/v1/secciones/1/ejecuciones" in api.peticiones
    assert [e.id for e in ESTADO["/ejecutar"].ejecuciones] == [1]


async def test_ejecutar_todo(user: User, cliente_falso: ClienteApi, api: ApiFalsa) -> None:
    _registrar("/todo", cliente_falso)
    await user.open("/todo")

    user.find(marker="ejecutar-todo").click()
    await user.should_see("# Ejecución correcta en 42 ms\n\niguales: True")
    assert "POST /api/v1/cuaderno/ejecuciones" in api.peticiones


async def test_filtro_consulta_a_la_api(user: User, cliente_falso: ClienteApi) -> None:
    _registrar("/filtro", cliente_falso)
    await user.open("/filtro")

    user.find(ui.input).type("generator")
    await user.should_see("1 de 2 ejercicios")
    # La lista se filtra; la sección abierta sigue abierta (como en la v1).
    await user.should_not_see(kind=ui.item_label, content="List comprehension")
    await user.should_see(kind=ui.item_label, content="Generator expression")


async def test_dialogos_de_introduccion_y_resumen(user: User, cliente_falso: ClienteApi) -> None:
    _registrar("/dialogos", cliente_falso)
    await user.open("/dialogos")

    user.find(marker="introduccion").click()
    await user.should_see("Introducción falsa.")
    await user.should_see("F1 — Introducción del notebook")

    user.find(marker="resumen").click()
    await user.should_see("Resumen: qué reemplaza a qué")
    await user.should_see("Nota final falsa.")


async def test_sincronizar_notifica_el_resultado(
    user: User, cliente_falso: ClienteApi, api: ApiFalsa
) -> None:
    _registrar("/sincronizar", cliente_falso)
    await user.open("/sincronizar")

    user.find(marker="sincronizar").click()
    await user.should_see("Sin cambios: 2 secciones al día.")
    assert "POST /api/v1/sincronizacion" in api.peticiones


async def test_atajos_de_teclado(user: User, cliente_falso: ClienteApi, api: ApiFalsa) -> None:
    _registrar("/teclado", cliente_falso)
    await user.open("/teclado")
    teclado = user.find(ui.keyboard)

    teclado.trigger("key", _tecla("F5"))
    await user.should_see("# Ejecución correcta en 42 ms")
    teclado.trigger("key", _tecla("F5", ctrl=True))
    teclado.trigger("key", _tecla("F1"))
    await user.should_see("Introducción falsa.")
    teclado.trigger("key", _tecla("F2"))
    await user.should_see("Nota final falsa.")
    teclado.trigger("key", _tecla("/"))
    teclado.trigger("key", _tecla("Escape"))
    teclado.trigger("key", _tecla("x"))
    teclado.trigger("key", _tecla("F5", accion="keyup"))  # se ignora

    await user.should_see("Ejecución correcta")
    assert api.peticiones.count("POST /api/v1/cuaderno/ejecuciones") == 1


async def test_api_caida_muestra_aviso_y_no_revienta(user: User, cliente_caido: ClienteApi) -> None:
    _registrar("/caida", cliente_caido)
    await user.open("/caida")

    await user.should_see("No se pudo conectar con la API (http://api.test).")
    await user.should_see("Reintentar")
    await user.should_see("Elige un ejercicio de la lista.")

    # Ninguna acción revienta con la API caída: todas acaban en el aviso.
    for marca in ("introduccion", "resumen", "sincronizar", "ejecutar", "reintentar"):
        user.find(marker=marca).click()
    await user.should_see("Reintentar")


async def test_registrar_monta_pagina_y_healthz(user: User) -> None:
    registrar(ConfiguracionUI(_env_file=None, api_url="http://127.0.0.1:9"))  # type: ignore[call-arg]

    respuesta = await user.http_client.get("/healthz")
    assert respuesta.json() == {"estado": "ok"}

    await user.open("/")
    await user.should_see("No se pudo conectar con la API")


async def test_la_api_cae_a_mitad_de_sesion_y_vuelve(
    user: User, cliente_falso: ClienteApi, api: ApiFalsa
) -> None:
    _registrar("/intermitente", cliente_falso)
    await user.open("/intermitente")
    await user.should_see(" 1. List comprehension")

    api.caida = True
    user.find(marker="ejecutar").click()
    await user.should_see("No se pudo ejecutar: No se pudo conectar con la API")
    user.find(marker="seccion-2").click()
    user.find(ui.input).type("gen")
    await user.should_see("Reintentar")
    assert ESTADO["/intermitente"].actual.numero == 1  # la vista no se rompió

    api.caida = False
    user.find(marker="reintentar").click()
    await user.should_not_see("Reintentar")


async def test_sin_secciones_la_pagina_queda_vacia(
    user: User, cliente_falso: ClienteApi, api: ApiFalsa
) -> None:
    api.secciones = []
    _registrar("/vacia", cliente_falso)
    await user.open("/vacia")

    await user.should_see("Elige un ejercicio de la lista.")
    user.find(marker="ejecutar-todo").click()  # sin sección abierta no hace nada
    assert "POST /api/v1/cuaderno/ejecuciones" not in api.peticiones
