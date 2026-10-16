"""Lo que el frontend espera recibir de la API.

Es un subconjunto deliberado de los esquemas del backend: si la API añade
campos, el frontend no se rompe (pydantic los ignora); si quita uno que se usa
aquí, el error aparece al validar la respuesta y no a mitad de pintar la página.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class TipoVeredicto(StrEnum):
    AHORRA = "ahorra"
    OCUPA_MAS = "ocupa_mas"
    SIN_DATOS = "sin_datos"


class Metricas(BaseModel):
    lineas: int
    efectivas: int
    caracteres: int
    texto: str


class Veredicto(BaseModel):
    tipo: TipoVeredicto
    ahorro_pct: float | None
    mensaje: str


class SeccionResumen(BaseModel):
    numero: int
    titulo: str
    etiqueta: str
    metricas_imperativo: Metricas
    metricas_declarativo: Metricas
    veredicto: Veredicto


class SeccionDetalle(SeccionResumen):
    explicacion: str
    referencia: str
    imperativo: str
    declarativo: str
    epilogo: str


class ListaSecciones(BaseModel):
    total: int
    visibles: int
    secciones: list[SeccionResumen]


class FilaResumen(BaseModel):
    imperativo: str
    declarativo: str


class Cuaderno(BaseModel):
    intro: str
    resumen: list[FilaResumen]
    nota_final: str
    total_secciones: int


class Ejecucion(BaseModel):
    id: int
    seccion: int | None
    salida: str
    codigo_salida: int | None
    duracion_ms: int
    ok: bool
    creada_en: datetime


class Sincronizacion(BaseModel):
    creadas: list[int]
    actualizadas: list[int]
    sin_cambios: list[int]
    eliminadas: list[int]
    hubo_cambios: bool
