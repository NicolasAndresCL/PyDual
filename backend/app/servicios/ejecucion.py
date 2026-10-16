"""Ejecución de código del notebook en un subproceso aislado.

Seguridad: este módulo solo recibe código que sale de la base de datos (una
sección guardada o el cuaderno completo). La API no expone ninguna ruta que
acepte código en el cuerpo de la petición.
"""

from __future__ import annotations

import os
import subprocess  # noqa: S404 - es el propósito del módulo
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.data.modelos import Ejecucion
from app.data.repositorio import Repositorio

# Variables que el subproceso hereda. Todo lo demás (DATABASE_URL incluida) se
# queda fuera: el código del notebook no tiene por qué ver credenciales.
VARIABLES_HEREDADAS = frozenset({"PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "LANG"})


@dataclass(frozen=True)
class ResultadoEjecucion:
    salida: str
    codigo_salida: int | None  # None = se agotó el tiempo
    duracion_ms: int

    @property
    def ok(self) -> bool:
        return self.codigo_salida == 0


def entorno_minimo(entorno: dict[str, str]) -> dict[str, str]:
    """Filtra el entorno del proceso padre a lo imprescindible."""
    return {
        clave: valor for clave, valor in entorno.items() if clave.upper() in VARIABLES_HEREDADAS
    } | {"PYTHONIOENCODING": "utf-8"}


def _combinar(stdout: str, stderr: str) -> str:
    salida = "\n".join(flujo for flujo in (stdout, stderr) if flujo).strip()
    return salida or "[la celda no imprimió nada]"


def ejecutar(codigo: str, tiempo_limite_s: int) -> ResultadoEjecucion:
    """Ejecuta `codigo` con el intérprete actual y devuelve salida, código y duración.

    El código va a un archivo temporal y no a `python -c`: el notebook completo
    pasa de 40 KB y en Windows la línea de comandos se corta en 32 KB
    (WinError 206). El directorio de trabajo es uno temporal y desechable.
    """
    with tempfile.TemporaryDirectory(prefix="comparativo_") as directorio:
        guion = Path(directorio) / "celda.py"
        guion.write_text(codigo, encoding="utf-8")
        inicio = time.perf_counter()
        try:
            proceso = subprocess.run(  # noqa: S603 - código guardado, no recibido por HTTP
                [sys.executable, "-I", "-X", "utf8", str(guion)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=tiempo_limite_s,
                cwd=directorio,
                env=entorno_minimo(dict(os.environ)),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ResultadoEjecucion(
                salida=f"[tiempo agotado: más de {tiempo_limite_s} s]",
                codigo_salida=None,
                duracion_ms=_milisegundos_desde(inicio),
            )
    return ResultadoEjecucion(
        salida=_combinar(proceso.stdout, proceso.stderr),
        codigo_salida=proceso.returncode,
        duracion_ms=_milisegundos_desde(inicio),
    )


def _milisegundos_desde(inicio: float) -> int:
    return round((time.perf_counter() - inicio) * 1000)


# --- Casos de uso: ejecutar lo guardado y registrar el resultado -------------


def _ejecutar_y_registrar(
    sesion: Session, codigo: str, seccion_id: int | None, tiempo_limite_s: int
) -> Ejecucion:
    # Se cierra la transacción de lectura antes de lanzar el subproceso: así la
    # conexión vuelve al pool durante los segundos que tarde la celda.
    sesion.rollback()
    resultado = ejecutar(codigo, tiempo_limite_s)
    ejecucion = Repositorio(sesion).registrar_ejecucion(
        seccion_id=seccion_id,
        salida=resultado.salida,
        codigo_salida=resultado.codigo_salida,
        duracion_ms=resultado.duracion_ms,
        ok=resultado.ok,
    )
    sesion.commit()
    return ejecucion


def ejecutar_seccion(sesion: Session, numero: int, tiempo_limite_s: int) -> Ejecucion:
    """Ejecuta el preludio de imports más la celda completa de la sección."""
    repositorio = Repositorio(sesion)
    seccion = repositorio.obtener_seccion(numero)
    codigo = f"{repositorio.obtener_cuaderno().preludio}\n\n{seccion.fuente}"
    return _ejecutar_y_registrar(sesion, codigo, seccion.id, tiempo_limite_s)


def ejecutar_cuaderno(sesion: Session, tiempo_limite_s: int) -> Ejecucion:
    """Ejecuta todas las celdas de código en orden, incluida la comprobación final."""
    codigo = "\n\n".join(Repositorio(sesion).obtener_cuaderno().fuentes)
    return _ejecutar_y_registrar(sesion, codigo, None, tiempo_limite_s)
