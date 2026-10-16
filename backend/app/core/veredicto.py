"""Veredicto de la comparación imperativo/declarativo. Sin I/O."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.core.metricas import lineas_efectivas, reduccion


class TipoVeredicto(StrEnum):
    AHORRA = "ahorra"
    OCUPA_MAS = "ocupa_mas"
    SIN_DATOS = "sin_datos"


@dataclass(frozen=True)
class Veredicto:
    tipo: TipoVeredicto
    ahorro_pct: float | None
    efectivas_imperativo: int
    efectivas_declarativo: int
    mensaje: str


def veredicto(imperativo: str, declarativo: str) -> Veredicto:
    """Resume en una frase qué se gana (o no) al pasar a lo declarativo."""
    imperativas = lineas_efectivas(imperativo)
    declarativas = lineas_efectivas(declarativo)
    ahorro = reduccion(imperativo, declarativo)
    cabecera = f"{imperativas} líneas efectivas imperativas frente a {declarativas} declarativas: "

    match ahorro:
        case None:
            tipo, mensaje = TipoVeredicto.SIN_DATOS, "Sin líneas efectivas que comparar."
        case float() if ahorro >= 0:
            tipo = TipoVeredicto.AHORRA
            mensaje = f"{cabecera}lo declarativo ahorra un {ahorro:.0f} % de código."
        case _:
            tipo = TipoVeredicto.OCUPA_MAS
            mensaje = (
                f"{cabecera}lo declarativo ocupa un {abs(ahorro):.0f} % más. Aquí no se "
                "gana en brevedad sino en estructura: cada pieza queda nombrada, "
                "reutilizable y testeable por separado."
            )
    return Veredicto(
        tipo=tipo,
        ahorro_pct=None if ahorro is None else round(ahorro, 1),
        efectivas_imperativo=imperativas,
        efectivas_declarativo=declarativas,
        mensaje=mensaje,
    )
