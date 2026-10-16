"""Acceso a datos. La única capa que habla SQL (vía el ORM)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errores import CuadernoNoSincronizado, SeccionNoEncontrada
from app.core.modelos import (
    CuadernoParseado,
    PlanSincronizacion,
    SeccionParseada,
    planificar_sincronizacion,
)
from app.data.modelos import Cuaderno, Ejecucion, Seccion

ID_CUADERNO = 1
CAMPOS_SECCION = (
    "titulo",
    "explicacion",
    "referencia",
    "imperativo",
    "declarativo",
    "epilogo",
    "fuente",
)


@dataclass(frozen=True)
class ResultadoSincronizacion:
    plan: PlanSincronizacion
    cuaderno_actualizado: bool


def _campos(seccion: SeccionParseada) -> dict[str, str]:
    return {campo: getattr(seccion, campo) for campo in CAMPOS_SECCION} | {
        "hash_contenido": seccion.hash_contenido
    }


def _campos_cuaderno(cuaderno: CuadernoParseado) -> dict[str, object]:
    return {
        "intro": cuaderno.intro,
        "preludio": cuaderno.preludio,
        "resumen": [list(asdict(fila).values()) for fila in cuaderno.resumen],
        "nota_final": cuaderno.nota_final,
        "fuentes": list(cuaderno.fuentes),
        "hash_contenido": cuaderno.hash_contenido,
    }


class Repositorio:
    """Operaciones sobre secciones, cuaderno y ejecuciones en una sesión."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion

    # -- lectura --

    def contar_secciones(self) -> int:
        return self.sesion.scalar(select(func.count()).select_from(Seccion)) or 0

    def listar_secciones(self) -> Sequence[Seccion]:
        return self.sesion.scalars(select(Seccion).order_by(Seccion.numero)).all()

    def obtener_seccion(self, numero: int) -> Seccion:
        seccion = self.sesion.scalar(select(Seccion).where(Seccion.numero == numero))
        if seccion is None:
            raise SeccionNoEncontrada(f"No existe la sección {numero}.", seccion=numero)
        return seccion

    def obtener_cuaderno(self) -> Cuaderno:
        cuaderno = self.sesion.get(Cuaderno, ID_CUADERNO)
        if cuaderno is None:
            raise CuadernoNoSincronizado()
        return cuaderno

    def historial(self, seccion_id: int | None, limite: int) -> Sequence[Ejecucion]:
        """Últimas ejecuciones, de la más reciente a la más antigua."""
        filtro = (
            Ejecucion.seccion_id.is_(None)
            if seccion_id is None
            else (Ejecucion.seccion_id == seccion_id)
        )
        consulta = (
            select(Ejecucion)
            .where(filtro)
            .order_by(Ejecucion.creada_en.desc(), Ejecucion.id.desc())
            .limit(limite)
        )
        return self.sesion.scalars(consulta).all()

    # -- escritura --

    def sincronizar(self, cuaderno: CuadernoParseado) -> ResultadoSincronizacion:
        """Refleja el notebook en la BD: upsert por número y borrado de sobrantes.

        No hace `commit`: quien llama decide la transacción. Si algo falla a
        mitad, el `rollback` de la sesión deja la BD como estaba.
        """
        existentes = {s.numero: s for s in self.listar_secciones()}
        plan = planificar_sincronizacion(
            {numero: s.hash_contenido for numero, s in existentes.items()}, cuaderno.secciones
        )
        nuevas = {s.numero: s for s in cuaderno.secciones}

        self.sesion.add_all(
            Seccion(numero=numero, **_campos(nuevas[numero])) for numero in plan.crear
        )
        for numero in plan.actualizar:
            for campo, valor in _campos(nuevas[numero]).items():
                setattr(existentes[numero], campo, valor)
        for numero in plan.eliminar:
            self.sesion.delete(existentes[numero])

        actual = self.sesion.get(Cuaderno, ID_CUADERNO)
        campos_cuaderno = _campos_cuaderno(cuaderno)
        cuaderno_cambia = actual is None or actual.hash_contenido != cuaderno.hash_contenido
        match actual:
            case None:
                self.sesion.add(Cuaderno(id=ID_CUADERNO, **campos_cuaderno))
            case Cuaderno() if cuaderno_cambia:
                for campo, valor in campos_cuaderno.items():
                    setattr(actual, campo, valor)
        self.sesion.flush()
        return ResultadoSincronizacion(plan=plan, cuaderno_actualizado=cuaderno_cambia)

    def registrar_ejecucion(
        self,
        *,
        seccion_id: int | None,
        salida: str,
        codigo_salida: int | None,
        duracion_ms: int,
        ok: bool,
    ) -> Ejecucion:
        ejecucion = Ejecucion(
            seccion_id=seccion_id,
            salida=salida,
            codigo_salida=codigo_salida,
            duracion_ms=duracion_ms,
            ok=ok,
        )
        self.sesion.add(ejecucion)
        self.sesion.flush()
        self.sesion.refresh(ejecucion)
        return ejecucion
