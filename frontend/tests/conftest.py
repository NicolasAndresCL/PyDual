"""Fixtures del frontend: una API falsa servida con `httpx.MockTransport`.

El cliente real (`ClienteApi`) se usa tal cual; solo se sustituye el
transporte, así las pruebas recorren también la validación de respuestas.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from app.cliente import ClienteApi

pytest_plugins = ["nicegui.testing.user_plugin"]

URL_API = "http://api.test"


def _metricas(efectivas: int) -> dict[str, Any]:
    return {
        "lineas": efectivas,
        "efectivas": efectivas,
        "caracteres": efectivas * 10,
        "texto": f"{efectivas} líneas · {efectivas} efectivas · {efectivas * 10} caracteres",
    }


def seccion_falsa(numero: int, titulo: str) -> dict[str, Any]:
    return {
        "numero": numero,
        "titulo": titulo,
        "etiqueta": f"{numero:>2}. {titulo}",
        "metricas_imperativo": _metricas(3),
        "metricas_declarativo": _metricas(1),
        "veredicto": {
            "tipo": "ahorra",
            "ahorro_pct": 66.7,
            "mensaje": "3 líneas efectivas imperativas frente a 1 declarativas: ahorra un 67 %.",
        },
        "explicacion": f"Explicación de **{titulo}**.",
        "referencia": "sum(iterable)\n    Suma.",
        "imperativo": "total = 0\nfor x in datos:\n    total += x",
        "declarativo": "total = sum(datos)",
        "epilogo": 'print("iguales:", True)',
    }


@dataclass
class ApiFalsa:
    """Estado de la API simulada; los tests lo inspeccionan después."""

    secciones: list[dict[str, Any]] = field(
        default_factory=lambda: [
            seccion_falsa(1, "List comprehension"),
            seccion_falsa(2, "Generator expression (evaluación perezosa)"),
        ]
    )
    ejecuciones: list[dict[str, Any]] = field(default_factory=list)
    peticiones: list[str] = field(default_factory=list)
    caida: bool = False  # True = la API deja de responder a mitad de la sesión

    def _ejecucion(self, seccion: int | None) -> dict[str, Any]:
        ejecucion = {
            "id": len(self.ejecuciones) + 1,
            "seccion": seccion,
            "salida": "iguales: True",
            "codigo_salida": 0,
            "duracion_ms": 42,
            "ok": True,
            "creada_en": "2026-10-15T12:00:00Z",
        }
        self.ejecuciones.append(ejecucion)
        return ejecucion

    def _seccion(self, numero: int) -> dict[str, Any] | None:
        return next((s for s in self.secciones if s["numero"] == numero), None)

    def __call__(self, peticion: httpx.Request) -> httpx.Response:
        self.peticiones.append(f"{peticion.method} {peticion.url.path}")
        if self.caida:
            raise httpx.ConnectError("conexión rechazada", request=peticion)
        partes = peticion.url.path.strip("/").split("/")[2:]  # sin "api/v1"
        match peticion.method, partes:
            case "GET", ["secciones"]:
                consulta = peticion.url.params.get("q", "").lower()
                visibles = [s for s in self.secciones if consulta in s["titulo"].lower()]
                return httpx.Response(
                    200,
                    json={
                        "total": len(self.secciones),
                        "visibles": len(visibles),
                        "secciones": visibles,
                    },
                )
            case "GET", ["secciones", numero] if self._seccion(int(numero)):
                return httpx.Response(200, json=self._seccion(int(numero)))
            case "GET", ["secciones", numero, "ejecuciones"]:
                propias = [e for e in reversed(self.ejecuciones) if e["seccion"] == int(numero)]
                return httpx.Response(200, json=propias)
            case "POST", ["secciones", numero, "ejecuciones"]:
                return httpx.Response(201, json=self._ejecucion(int(numero)))
            case "POST", ["cuaderno", "ejecuciones"]:
                return httpx.Response(201, json=self._ejecucion(None))
            case "GET", ["cuaderno"]:
                return httpx.Response(
                    200,
                    json={
                        "intro": "# Python declarativo vs. imperativo\n\nIntroducción falsa.",
                        "resumen": [{"imperativo": "for + append", "declarativo": "comprehension"}],
                        "nota_final": "Nota final falsa.",
                        "total_secciones": len(self.secciones),
                    },
                )
            case "POST", ["sincronizacion"]:
                return httpx.Response(
                    200,
                    json={
                        "creadas": [],
                        "actualizadas": [],
                        "sin_cambios": [1, 2],
                        "eliminadas": [],
                        "hubo_cambios": False,
                    },
                )
            case _:
                return httpx.Response(
                    404,
                    json={
                        "error": {"codigo": "no_encontrado", "mensaje": "No existe.", "detalle": {}}
                    },
                )


@pytest.fixture
def api() -> ApiFalsa:
    return ApiFalsa()


@pytest.fixture
def cliente_falso(api: ApiFalsa) -> ClienteApi:
    return ClienteApi(URL_API, 5, transporte=httpx.MockTransport(api))


@pytest.fixture
def cliente_caido() -> ClienteApi:
    def rechazar(peticion: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("conexión rechazada", request=peticion)

    return ClienteApi(URL_API, 5, transporte=httpx.MockTransport(rechazar))


@pytest.fixture
def cliente_con() -> Callable[[Callable[[httpx.Request], httpx.Response]], ClienteApi]:
    """Cliente con un manejador a medida (respuestas raras, timeouts…)."""

    def construir(manejador: Callable[[httpx.Request], httpx.Response]) -> ClienteApi:
        return ClienteApi(URL_API, 5, transporte=httpx.MockTransport(manejador))

    return construir
