"""Métricas, veredicto, filtro, modelos de valor y errores: lógica pura."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from app.core.errores import (
    BaseDeDatosNoDisponible,
    CuadernoNoSincronizado,
    ErrorDeDominio,
    NotebookNoDisponible,
    SeccionNoEncontrada,
)
from app.core.filtro import coincide, filtrar, normalizar
from app.core.metricas import Metricas, lineas_efectivas, reduccion
from app.core.modelos import (
    CuadernoParseado,
    FilaResumen,
    SeccionParseada,
    huella,
    planificar_sincronizacion,
)
from app.core.veredicto import TipoVeredicto, veredicto


def _seccion(numero: int = 1, **cambios: str) -> SeccionParseada:
    base = SeccionParseada(
        numero=numero,
        titulo="Generator expression (evaluación perezosa)",
        explicacion="Con paréntesis no se construye la lista.",
        referencia="sum(iterable)",
        imperativo="total = 0\nfor x in datos:\n    total += x",
        declarativo="total = sum(x for x in datos)",
        epilogo="print(total)",
        fuente="...",
    )
    return replace(base, **cambios)


# --- Métricas ---------------------------------------------------------------


def test_lineas_efectivas_ignora_vacias_y_comentarios() -> None:
    assert lineas_efectivas("a = 1\n\n   # comentario\n  b = 2  # en línea\n") == 2
    assert lineas_efectivas("") == 0


@pytest.mark.parametrize(
    ("imperativo", "declarativo", "esperado"),
    [("a\nb\nc\nd", "a", 75.0), ("a", "a\nb", -100.0), ("# solo comentario", "a", None)],
)
def test_reduccion(imperativo: str, declarativo: str, esperado: float | None) -> None:
    assert reduccion(imperativo, declarativo) == esperado


def test_metricas_de_un_bloque() -> None:
    metricas = Metricas.de("a = 1\n\n# c\nb = 2")
    assert metricas == Metricas(lineas=4, efectivas=2, caracteres=16)
    assert metricas.texto == "4 líneas · 2 efectivas · 16 caracteres"


# --- Veredicto --------------------------------------------------------------


def test_veredicto_cuando_lo_declarativo_ahorra() -> None:
    resultado = veredicto("a\nb\nc", "a")
    assert resultado.tipo is TipoVeredicto.AHORRA
    assert resultado.ahorro_pct == 66.7
    assert resultado.mensaje == (
        "3 líneas efectivas imperativas frente a 1 declarativas: "
        "lo declarativo ahorra un 67 % de código."
    )


def test_veredicto_cuando_lo_declarativo_ocupa_mas() -> None:
    resultado = veredicto("a", "a\nb")
    assert resultado.tipo is TipoVeredicto.OCUPA_MAS
    assert resultado.ahorro_pct == -100.0
    assert "ocupa un 100 % más" in resultado.mensaje
    assert "estructura" in resultado.mensaje


def test_veredicto_sin_datos() -> None:
    resultado = veredicto("", "a")
    assert (resultado.tipo, resultado.ahorro_pct) == (TipoVeredicto.SIN_DATOS, None)
    assert resultado.mensaje == "Sin líneas efectivas que comparar."


def test_veredicto_empate_cuenta_como_ahorro_cero() -> None:
    resultado = veredicto("a", "b")
    assert (resultado.tipo, resultado.ahorro_pct) == (TipoVeredicto.AHORRA, 0.0)


# --- Filtro -----------------------------------------------------------------


@pytest.mark.parametrize(
    "consulta",
    ["", "   ", "EVALUACION", "evaluación", "paréntesis", "SUM(", "total +=", "  perezosa "],
)
def test_coincide_sin_mayusculas_ni_tildes_en_todos_los_campos(consulta: str) -> None:
    assert coincide(_seccion(), consulta)


def test_no_coincide_si_no_aparece() -> None:
    assert not coincide(_seccion(), "pattern matching")


def test_filtrar_conserva_el_orden_y_acepta_none() -> None:
    secciones = (_seccion(1), _seccion(2, titulo="zip y enumerate", explicacion="", referencia=""))
    assert filtrar(secciones, None) == secciones
    assert filtrar(secciones, "ZIP") == (secciones[1],)
    assert filtrar(secciones, "no existe") == ()


def test_normalizar() -> None:
    assert normalizar("  Árbol ÚTIL ") == "arbol util"


# --- Modelos de valor -------------------------------------------------------


def test_los_modelos_son_inmutables() -> None:
    with pytest.raises(FrozenInstanceError):
        _seccion().titulo = "otro"  # type: ignore[misc]


def test_hash_de_seccion_cambia_con_el_contenido_y_es_estable() -> None:
    assert _seccion().hash_contenido == _seccion().hash_contenido
    assert _seccion().hash_contenido != _seccion(imperativo="otro").hash_contenido
    assert len(_seccion().hash_contenido) == 64
    assert _seccion(7).etiqueta == " 7. Generator expression (evaluación perezosa)"


def test_hash_de_cuaderno() -> None:
    cuaderno = CuadernoParseado("i", "p", (_seccion(),), (FilaResumen("a", "b"),), "n", ("f",))
    assert cuaderno.hash_contenido == replace(cuaderno, secciones=()).hash_contenido
    assert cuaderno.hash_contenido != replace(cuaderno, intro="otra").hash_contenido
    assert huella({"b": 1, "a": "ñ"}) == huella({"a": "ñ", "b": 1})


def test_plan_de_sincronizacion() -> None:
    nuevas = (_seccion(1), _seccion(2, titulo="cambiado"), _seccion(3))
    existentes = {1: _seccion(1).hash_contenido, 2: _seccion(2).hash_contenido, 9: "x"}

    plan = planificar_sincronizacion(existentes, nuevas)

    assert (plan.crear, plan.actualizar, plan.sin_cambios, plan.eliminar) == (
        (3,),
        (2,),
        (1,),
        (9,),
    )
    assert plan.hay_cambios


def test_plan_sin_cambios_es_idempotente() -> None:
    nuevas = (_seccion(1), _seccion(2))
    plan = planificar_sincronizacion({s.numero: s.hash_contenido for s in nuevas}, nuevas)
    assert plan.sin_cambios == (1, 2)
    assert not plan.hay_cambios


# --- Errores ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("tipo", "codigo", "status"),
    [
        (ErrorDeDominio, "error_de_dominio", 400),
        (NotebookNoDisponible, "notebook_no_disponible", 503),
        (SeccionNoEncontrada, "seccion_no_encontrada", 404),
        (CuadernoNoSincronizado, "cuaderno_no_sincronizado", 409),
        (BaseDeDatosNoDisponible, "base_de_datos_no_disponible", 503),
    ],
)
def test_errores_de_dominio_saben_presentarse(
    tipo: type[ErrorDeDominio], codigo: str, status: int
) -> None:
    error = tipo()
    assert (error.codigo, error.http_status) == (codigo, status)
    assert error.mensaje == tipo.mensaje_por_defecto == str(error)
    assert error.detalle() == {}


def test_detalle_es_una_copia() -> None:
    error = SeccionNoEncontrada("No existe la 99.", seccion=99)
    error.detalle()["seccion"] = 0
    assert error.detalle() == {"seccion": 99}
    assert error.mensaje == "No existe la 99."
