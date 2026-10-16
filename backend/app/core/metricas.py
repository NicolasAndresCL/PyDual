"""Métricas de un bloque de código. Funciones puras, mismo criterio que la v1."""

from __future__ import annotations

from dataclasses import dataclass


def lineas_efectivas(codigo: str) -> int:
    """Cuenta líneas de código: sin vacías y sin comentarios."""
    return sum(
        1 for linea in map(str.strip, codigo.splitlines()) if linea and not linea.startswith("#")
    )


def reduccion(imperativo: str, declarativo: str) -> float | None:
    """Porcentaje de líneas efectivas que ahorra la versión declarativa.

    `None` si la versión imperativa no tiene líneas efectivas (no hay base).
    """
    base = lineas_efectivas(imperativo)
    return None if base == 0 else (base - lineas_efectivas(declarativo)) / base * 100


@dataclass(frozen=True)
class Metricas:
    """Tamaño de un bloque de código."""

    lineas: int
    efectivas: int
    caracteres: int

    @classmethod
    def de(cls, codigo: str) -> Metricas:
        return cls(
            lineas=len(codigo.splitlines()),
            efectivas=lineas_efectivas(codigo),
            caracteres=len(codigo),
        )

    @property
    def texto(self) -> str:
        return f"{self.lineas} líneas · {self.efectivas} efectivas · {self.caracteres} caracteres"
