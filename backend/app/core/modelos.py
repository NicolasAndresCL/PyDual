"""Tipos de valor del dominio: inmutables y sin I/O.

Son el contrato entre el parser (que los produce a partir del texto del
notebook) y el resto de capas (que los guardan, filtran o muestran).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, fields


@dataclass(frozen=True)
class FilaResumen:
    """Una fila de la tabla «qué reemplaza a qué» del final del notebook."""

    imperativo: str
    declarativo: str


@dataclass(frozen=True)
class SeccionParseada:
    """Un ejercicio del notebook, ya partido en sus dos mitades."""

    numero: int
    titulo: str
    explicacion: str
    referencia: str
    imperativo: str
    declarativo: str
    epilogo: str
    fuente: str

    @property
    def etiqueta(self) -> str:
        return f"{self.numero:>2}. {self.titulo}"

    @property
    def hash_contenido(self) -> str:
        """Huella del contenido: si no cambia, la sincronización no reescribe la fila."""
        contenido = {campo.name: getattr(self, campo.name) for campo in fields(self)}
        return huella(contenido)


@dataclass(frozen=True)
class CuadernoParseado:
    """El notebook completo, listo para persistir."""

    intro: str
    preludio: str
    secciones: tuple[SeccionParseada, ...]
    resumen: tuple[FilaResumen, ...]
    nota_final: str
    fuentes: tuple[str, ...]

    @property
    def hash_contenido(self) -> str:
        """Huella de los metadatos del cuaderno (las secciones llevan la suya)."""
        return huella(
            {
                "intro": self.intro,
                "preludio": self.preludio,
                "resumen": [asdict(fila) for fila in self.resumen],
                "nota_final": self.nota_final,
                "fuentes": list(self.fuentes),
            }
        )


@dataclass(frozen=True)
class PlanSincronizacion:
    """Qué hay que hacer con cada número de sección para reflejar el notebook."""

    crear: tuple[int, ...]
    actualizar: tuple[int, ...]
    sin_cambios: tuple[int, ...]
    eliminar: tuple[int, ...]

    @property
    def hay_cambios(self) -> bool:
        return any((self.crear, self.actualizar, self.eliminar))


def huella(contenido: object) -> str:
    """SHA-256 estable de una estructura serializable a JSON."""
    serializado = json.dumps(contenido, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def planificar_sincronizacion(
    existentes: dict[int, str], nuevas: tuple[SeccionParseada, ...]
) -> PlanSincronizacion:
    """Compara las huellas guardadas (`numero -> hash`) con las recién parseadas.

    Función pura: decide qué cambia sin tocar la base de datos, así la regla de
    idempotencia se prueba sin motor de por medio.
    """
    numeros_nuevos = {seccion.numero for seccion in nuevas}
    return PlanSincronizacion(
        crear=tuple(s.numero for s in nuevas if s.numero not in existentes),
        actualizar=tuple(
            s.numero
            for s in nuevas
            if s.numero in existentes and existentes[s.numero] != s.hash_contenido
        ),
        sin_cambios=tuple(s.numero for s in nuevas if existentes.get(s.numero) == s.hash_contenido),
        eliminar=tuple(sorted(set(existentes) - numeros_nuevos)),
    )
