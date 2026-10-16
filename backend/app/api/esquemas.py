"""Esquemas pydantic de la API (lo que viaja por HTTP)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.metricas import Metricas
from app.core.veredicto import TipoVeredicto, Veredicto, veredicto
from app.data.modelos import Cuaderno, Ejecucion, Seccion
from app.data.repositorio import ResultadoSincronizacion


class MetricasEsquema(BaseModel):
    lineas: int
    efectivas: int
    caracteres: int
    texto: str

    @classmethod
    def de(cls, codigo: str) -> MetricasEsquema:
        metricas = Metricas.de(codigo)
        return cls(
            lineas=metricas.lineas,
            efectivas=metricas.efectivas,
            caracteres=metricas.caracteres,
            texto=metricas.texto,
        )


class VeredictoEsquema(BaseModel):
    tipo: TipoVeredicto
    ahorro_pct: float | None
    efectivas_imperativo: int
    efectivas_declarativo: int
    mensaje: str

    @classmethod
    def de(cls, valor: Veredicto) -> VeredictoEsquema:
        return cls(
            tipo=valor.tipo,
            ahorro_pct=valor.ahorro_pct,
            efectivas_imperativo=valor.efectivas_imperativo,
            efectivas_declarativo=valor.efectivas_declarativo,
            mensaje=valor.mensaje,
        )


class SeccionResumen(BaseModel):
    numero: int
    titulo: str
    etiqueta: str
    metricas_imperativo: MetricasEsquema
    metricas_declarativo: MetricasEsquema
    veredicto: VeredictoEsquema

    @classmethod
    def de(cls, seccion: Seccion) -> SeccionResumen:
        return cls(
            numero=seccion.numero,
            titulo=seccion.titulo,
            etiqueta=seccion.etiqueta,
            metricas_imperativo=MetricasEsquema.de(seccion.imperativo),
            metricas_declarativo=MetricasEsquema.de(seccion.declarativo),
            veredicto=VeredictoEsquema.de(veredicto(seccion.imperativo, seccion.declarativo)),
        )


class SeccionDetalle(SeccionResumen):
    explicacion: str
    referencia: str
    imperativo: str
    declarativo: str
    epilogo: str
    hash_contenido: str
    creada_en: datetime
    actualizada_en: datetime

    @classmethod
    def de(cls, seccion: Seccion) -> SeccionDetalle:
        return cls(
            **SeccionResumen.de(seccion).model_dump(),
            explicacion=seccion.explicacion,
            referencia=seccion.referencia,
            imperativo=seccion.imperativo,
            declarativo=seccion.declarativo,
            epilogo=seccion.epilogo,
            hash_contenido=seccion.hash_contenido,
            creada_en=seccion.creada_en,
            actualizada_en=seccion.actualizada_en,
        )


class ListaSecciones(BaseModel):
    total: int
    visibles: int
    consulta: str | None
    secciones: list[SeccionResumen]


class FilaResumenEsquema(BaseModel):
    imperativo: str
    declarativo: str


class CuadernoEsquema(BaseModel):
    intro: str
    resumen: list[FilaResumenEsquema]
    nota_final: str
    total_secciones: int
    actualizado_en: datetime

    @classmethod
    def de(cls, cuaderno: Cuaderno, total_secciones: int) -> CuadernoEsquema:
        return cls(
            intro=cuaderno.intro,
            resumen=[
                FilaResumenEsquema(imperativo=imp, declarativo=dec) for imp, dec in cuaderno.resumen
            ],
            nota_final=cuaderno.nota_final,
            total_secciones=total_secciones,
            actualizado_en=cuaderno.actualizada_en,
        )


class SincronizacionEsquema(BaseModel):
    creadas: list[int]
    actualizadas: list[int]
    sin_cambios: list[int]
    eliminadas: list[int]
    cuaderno_actualizado: bool
    hubo_cambios: bool

    @classmethod
    def de(cls, resultado: ResultadoSincronizacion) -> SincronizacionEsquema:
        plan = resultado.plan
        return cls(
            creadas=list(plan.crear),
            actualizadas=list(plan.actualizar),
            sin_cambios=list(plan.sin_cambios),
            eliminadas=list(plan.eliminar),
            cuaderno_actualizado=resultado.cuaderno_actualizado,
            hubo_cambios=plan.hay_cambios or resultado.cuaderno_actualizado,
        )


class EjecucionEsquema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seccion: int | None
    salida: str
    codigo_salida: int | None
    duracion_ms: int
    ok: bool
    creada_en: datetime

    @classmethod
    def de(cls, ejecucion: Ejecucion, numero_seccion: int | None) -> EjecucionEsquema:
        return cls(
            id=ejecucion.id,
            seccion=numero_seccion,
            salida=ejecucion.salida,
            codigo_salida=ejecucion.codigo_salida,
            duracion_ms=ejecucion.duracion_ms,
            ok=ejecucion.ok,
            creada_en=ejecucion.creada_en,
        )


class SaludEsquema(BaseModel):
    estado: str
    base_de_datos: str
