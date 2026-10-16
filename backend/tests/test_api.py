"""API de punta a punta con TestClient (contra SQLite o el Postgres del CI)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from app import main as modulo_main
from app.api import rutas
from app.config import Configuracion
from app.main import crear_app
from tests.conftest import celda, codigo_seccion, notebook, notebook_minimo


def _error(respuesta: Response) -> dict:
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"error"}
    assert set(cuerpo["error"]) == {"codigo", "mensaje", "detalle"}
    return cuerpo["error"]


# --- Salud ------------------------------------------------------------------


def test_healthz_toca_la_base_de_datos(cliente: TestClient) -> None:
    respuesta = cliente.get("/healthz")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok", "base_de_datos": "ok"}


def test_healthz_503_si_la_base_no_responde(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def caida(_motor: Engine) -> bool:
        raise OperationalError("SELECT 1", {}, Exception("conexión rechazada"))

    monkeypatch.setattr(modulo_main, "responde", caida)
    respuesta = cliente.get("/healthz")
    assert respuesta.status_code == 503
    assert _error(respuesta)["codigo"] == "base_de_datos_no_disponible"


# --- Lectura ----------------------------------------------------------------


def test_lista_las_20_secciones_con_metricas(cliente_sincronizado: TestClient) -> None:
    cuerpo = cliente_sincronizado.get("/api/v1/secciones").json()

    assert (cuerpo["total"], cuerpo["visibles"], cuerpo["consulta"]) == (20, 20, None)
    primera = cuerpo["secciones"][0]
    assert primera["etiqueta"] == " 1. List comprehension"
    assert primera["metricas_imperativo"]["efectivas"] == 3
    assert primera["metricas_declarativo"]["efectivas"] == 1
    assert primera["veredicto"]["tipo"] == "ahorra"


def test_filtro_sin_tildes_ni_mayusculas(cliente_sincronizado: TestClient) -> None:
    cuerpo = cliente_sincronizado.get("/api/v1/secciones", params={"q": "EVALUACION"}).json()
    assert cuerpo["visibles"] >= 1
    assert "Generator expression (evaluación perezosa)" in [
        s["titulo"] for s in cuerpo["secciones"]
    ]
    assert cuerpo["total"] == 20


def test_filtro_sin_resultados(cliente_sincronizado: TestClient) -> None:
    cuerpo = cliente_sincronizado.get("/api/v1/secciones", params={"q": "zzz-nada"}).json()
    assert (cuerpo["visibles"], cuerpo["secciones"]) == (0, [])


def test_detalle_con_veredicto(cliente_sincronizado: TestClient) -> None:
    cuerpo = cliente_sincronizado.get("/api/v1/secciones/16").json()
    assert cuerpo["numero"] == 16
    assert cuerpo["veredicto"]["tipo"] == "ocupa_mas"
    assert cuerpo["imperativo"] and cuerpo["declarativo"] and cuerpo["referencia"]
    assert len(cuerpo["hash_contenido"]) == 64


def test_cuaderno_intro_y_resumen(cliente_sincronizado: TestClient) -> None:
    cuerpo = cliente_sincronizado.get("/api/v1/cuaderno").json()
    assert cuerpo["intro"].startswith("# Python declarativo vs. imperativo")
    assert len(cuerpo["resumen"]) == 21
    assert cuerpo["total_secciones"] == 20


def test_cuaderno_sin_sincronizar_da_409(cliente: TestClient) -> None:
    respuesta = cliente.get("/api/v1/cuaderno")
    assert respuesta.status_code == 409
    assert _error(respuesta)["codigo"] == "cuaderno_no_sincronizado"


# --- Contrato de error ------------------------------------------------------


def test_seccion_inexistente_404_con_contrato(cliente_sincronizado: TestClient) -> None:
    respuesta = cliente_sincronizado.get("/api/v1/secciones/99")
    assert respuesta.status_code == 404
    assert _error(respuesta) == {
        "codigo": "seccion_no_encontrada",
        "mensaje": "No existe la sección 99.",
        "detalle": {"seccion": 99},
    }


@pytest.mark.parametrize(
    "ruta", ["/api/v1/secciones/0", "/api/v1/secciones/abc", "/api/v1/secciones?q=" + "x" * 201]
)
def test_errores_de_validacion_normalizados(cliente: TestClient, ruta: str) -> None:
    respuesta = cliente.get(ruta)
    assert respuesta.status_code == 422
    error = _error(respuesta)
    assert error["codigo"] == "validacion"
    assert error["detalle"]["errores"][0]["campo"].startswith(("path", "query"))


def test_ruta_desconocida_tambien_usa_el_contrato(cliente: TestClient) -> None:
    respuesta = cliente.get("/api/v1/no-existe")
    assert respuesta.status_code == 404
    assert _error(respuesta)["codigo"] == "not_found"


def test_metodo_no_permitido(cliente: TestClient) -> None:
    respuesta = cliente.delete("/api/v1/secciones")
    assert respuesta.status_code == 405
    assert _error(respuesta)["codigo"] == "method_not_allowed"


def test_error_inesperado_500_generico(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def rota(*_: object) -> None:
        raise RuntimeError("detalle interno que no debe filtrarse")

    monkeypatch.setattr(rutas, "filtrar", rota)
    with TestClient(app, raise_server_exceptions=False) as cliente:
        respuesta = cliente.get("/api/v1/secciones")

    assert respuesta.status_code == 500
    assert _error(respuesta) == {
        "codigo": "error_interno",
        "mensaje": "Error interno del servidor.",
        "detalle": {},
    }
    assert "detalle interno" in caplog.text  # queda en el log, no en la respuesta


# --- Sincronización ---------------------------------------------------------


def test_sincronizacion_es_idempotente(cliente: TestClient) -> None:
    primera = cliente.post("/api/v1/sincronizacion").json()
    segunda = cliente.post("/api/v1/sincronizacion").json()

    assert primera["creadas"] == list(range(1, 21))
    assert primera["hubo_cambios"] and primera["cuaderno_actualizado"]
    assert segunda == {
        "creadas": [],
        "actualizadas": [],
        "sin_cambios": list(range(1, 21)),
        "eliminadas": [],
        "cuaderno_actualizado": False,
        "hubo_cambios": False,
    }


def _app_con_notebook(
    motor: Engine, configuracion: Callable[..., Configuracion], ruta: Path
) -> FastAPI:
    return crear_app(configuracion(notebook_ruta=ruta), motor=motor)


def test_sincronizacion_refleja_cambios_y_borra_sobrantes(
    motor: Engine, configuracion: Callable[..., Configuracion], tmp_path: Path
) -> None:
    ruta = tmp_path / "cuaderno.ipynb"
    ruta.write_text(notebook_minimo(3), encoding="utf-8")
    with TestClient(_app_con_notebook(motor, configuracion, ruta)) as cliente:
        assert cliente.post("/api/v1/sincronizacion").json()["creadas"] == [1, 2, 3]
        cliente.post("/api/v1/secciones/3/ejecuciones")

        ruta.write_text(notebook_minimo(2).replace("Ejercicio 2", "Ejercicio dos"), "utf-8")
        cuerpo = cliente.post("/api/v1/sincronizacion").json()

        assert (cuerpo["actualizadas"], cuerpo["sin_cambios"], cuerpo["eliminadas"]) == (
            [2],
            [1],
            [3],
        )
        assert cliente.get("/api/v1/secciones/2").json()["titulo"] == "Ejercicio dos"
        assert cliente.get("/api/v1/secciones/3").status_code == 404


def test_notebook_roto_da_422_con_numero_y_no_toca_la_bd(
    motor: Engine, configuracion: Callable[..., Configuracion], tmp_path: Path
) -> None:
    ruta = tmp_path / "cuaderno.ipynb"
    ruta.write_text(notebook_minimo(2), encoding="utf-8")
    with TestClient(_app_con_notebook(motor, configuracion, ruta)) as cliente:
        cliente.post("/api/v1/sincronizacion")
        antes = cliente.get("/api/v1/secciones").json()

        roto = notebook(
            celda("markdown", "# Intro"),
            celda("markdown", "## 1. Bien"),
            celda("code", codigo_seccion(declarativo="otra_cosa = 1")),
            celda("markdown", "## 2. Rota"),
            celda("code", "# --- Imperativo ---\nsin marca declarativa"),
        )
        ruta.write_text(roto, encoding="utf-8")
        respuesta = cliente.post("/api/v1/sincronizacion")

        assert respuesta.status_code == 422
        error = _error(respuesta)
        assert error["codigo"] == "cuaderno_invalido"
        assert error["detalle"] == {"seccion": 2, "titulo": "Rota"}
        assert cliente.get("/api/v1/secciones").json() == antes


def test_notebook_ausente_da_503(
    motor: Engine, configuracion: Callable[..., Configuracion], tmp_path: Path
) -> None:
    app = _app_con_notebook(motor, configuracion, tmp_path / "no-existe.ipynb")
    with TestClient(app) as cliente:
        respuesta = cliente.post("/api/v1/sincronizacion")
    assert respuesta.status_code == 503
    assert _error(respuesta)["codigo"] == "notebook_no_disponible"


# --- Arranque ---------------------------------------------------------------


def test_al_arrancar_sincroniza_si_la_tabla_esta_vacia(
    motor: Engine, configuracion: Callable[..., Configuracion]
) -> None:
    app = crear_app(configuracion(sincronizar_al_arrancar=True), motor=motor)
    with TestClient(app) as cliente:
        assert cliente.get("/api/v1/secciones").json()["total"] == 20
    # Segundo arranque con datos: no vuelve a sincronizar (no hay nada que hacer).
    with TestClient(crear_app(configuracion(sincronizar_al_arrancar=True), motor=motor)) as c:
        assert c.get("/api/v1/secciones").json()["total"] == 20


def test_arranca_aunque_el_notebook_falte(
    motor: Engine,
    configuracion: Callable[..., Configuracion],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = configuracion(sincronizar_al_arrancar=True, notebook_ruta=tmp_path / "x.ipynb")
    with TestClient(crear_app(config, motor=motor)) as cliente:
        assert cliente.get("/healthz").status_code == 200
        assert cliente.get("/api/v1/secciones").json()["total"] == 0
    assert "No se pudo sincronizar al arrancar" in caplog.text


# --- Ejecución --------------------------------------------------------------


def test_ejecutar_seccion_persiste_y_aparece_en_el_historial(
    cliente_sincronizado: TestClient,
) -> None:
    respuesta = cliente_sincronizado.post("/api/v1/secciones/1/ejecuciones")
    assert respuesta.status_code == 201
    ejecucion = respuesta.json()
    assert ejecucion["ok"] is True
    assert ejecucion["codigo_salida"] == 0
    assert ejecucion["seccion"] == 1
    assert "iguales    : True" in ejecucion["salida"]

    cliente_sincronizado.post("/api/v1/secciones/1/ejecuciones")
    historial = cliente_sincronizado.get("/api/v1/secciones/1/ejecuciones").json()
    assert len(historial) == 2
    assert historial[0]["id"] > historial[1]["id"]  # la más reciente primero
    limitado = cliente_sincronizado.get("/api/v1/secciones/1/ejecuciones", params={"limite": 1})
    assert len(limitado.json()) == 1
    assert cliente_sincronizado.get("/api/v1/secciones/2/ejecuciones").json() == []


def test_el_cuerpo_de_la_peticion_se_ignora(cliente_sincronizado: TestClient) -> None:
    """Seguridad: aunque alguien mande código, se ejecuta la sección guardada."""
    respuesta = cliente_sincronizado.post(
        "/api/v1/secciones/1/ejecuciones", json={"codigo": 'print("inyectado")'}
    )
    assert respuesta.status_code == 201
    assert "inyectado" not in respuesta.json()["salida"]


def test_ejecutar_seccion_inexistente(cliente_sincronizado: TestClient) -> None:
    respuesta = cliente_sincronizado.post("/api/v1/secciones/99/ejecuciones")
    assert respuesta.status_code == 404
    assert cliente_sincronizado.get("/api/v1/secciones/99/ejecuciones").status_code == 404


def test_ejecutar_cuaderno_completo(cliente_sincronizado: TestClient) -> None:
    respuesta = cliente_sincronizado.post("/api/v1/cuaderno/ejecuciones")
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert (cuerpo["ok"], cuerpo["seccion"]) == (True, None)
    assert "Todo equivalente: True" in cuerpo["salida"]

    historial = cliente_sincronizado.get("/api/v1/cuaderno/ejecuciones").json()
    assert [e["id"] for e in historial] == [cuerpo["id"]]


def test_ejecutar_cuaderno_sin_sincronizar_da_409(cliente: TestClient) -> None:
    assert cliente.post("/api/v1/cuaderno/ejecuciones").status_code == 409
