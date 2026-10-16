"""Filtro de secciones por texto libre. Mismo criterio que `_coincide` de la v1.

Busca en título, explicación, código de ambas mitades y referencia, sin
distinguir mayúsculas ni tildes. Se hace en Python y no con `ILIKE` porque
SQL no sabe ignorar tildes de forma portable (SQLite en tests, Postgres en
producción) y son 20 filas.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from app.core.parser import sin_tildes


class Buscable(Protocol):
    """Lo mínimo que necesita el filtro. Lo cumplen el ORM y `SeccionParseada`."""

    @property
    def titulo(self) -> str: ...
    @property
    def explicacion(self) -> str: ...
    @property
    def imperativo(self) -> str: ...
    @property
    def declarativo(self) -> str: ...
    @property
    def referencia(self) -> str: ...


def normalizar(texto: str) -> str:
    return sin_tildes(texto).lower().strip()


def coincide(seccion: Buscable, consulta: str) -> bool:
    """`True` si la consulta (ya normalizada o no) aparece en algún campo."""
    patron = normalizar(consulta)
    campos = (
        seccion.titulo,
        seccion.explicacion,
        seccion.imperativo,
        seccion.declarativo,
        seccion.referencia,
    )
    return not patron or any(patron in sin_tildes(campo).lower() for campo in campos)


def filtrar[T: Buscable](secciones: Iterable[T], consulta: str | None) -> tuple[T, ...]:
    return tuple(seccion for seccion in secciones if coincide(seccion, consulta or ""))
