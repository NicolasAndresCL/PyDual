"""Decisiones de presentación como funciones puras (sin NiceGUI): testeables."""

from __future__ import annotations

from enum import Enum, auto

from app.modelos import Ejecucion, SeccionDetalle, Sincronizacion, TipoVeredicto


class Accion(Enum):
    INTRODUCCION = auto()
    RESUMEN = auto()
    EJECUTAR = auto()
    EJECUTAR_TODO = auto()
    FILTRAR = auto()
    LIMPIAR_FILTRO = auto()


# Atajos equivalentes a los de la v1. Ctrl+F es la búsqueda del navegador, así
# que el filtro se enfoca con «/» (convención de GitHub, YouTube, etc.).
ATAJOS = (
    ("F1", "Introducción del notebook"),
    ("F2", "Tabla resumen: qué reemplaza a qué"),
    ("F5", "Ejecutar la sección actual"),
    ("Ctrl+F5", "Ejecutar el notebook completo"),
    ("/", "Ir al filtro"),
    ("Esc", "Limpiar el filtro"),
)

COLOR_VEREDICTO = {
    TipoVeredicto.AHORRA: "positive",
    TipoVeredicto.OCUPA_MAS: "warning",
    TipoVeredicto.SIN_DATOS: "grey",
}


def accion_para_tecla(tecla: str, *, ctrl: bool) -> Accion | None:
    match tecla, ctrl:
        case "F1", _:
            return Accion.INTRODUCCION
        case "F2", _:
            return Accion.RESUMEN
        case "F5", True:
            return Accion.EJECUTAR_TODO
        case "F5", False:
            return Accion.EJECUTAR
        case "/", False:
            return Accion.FILTRAR
        case "Escape", _:
            return Accion.LIMPIAR_FILTRO
        case _:
            return None


def paneles(seccion: SeccionDetalle) -> tuple[tuple[str, str, str, str], ...]:
    """(título, color, métricas, código) de los dos paneles, en orden."""
    return (
        (
            "IMPERATIVO · el CÓMO, paso a paso",
            "orange-8",
            seccion.metricas_imperativo.texto,
            seccion.imperativo,
        ),
        (
            "DECLARATIVO · el QUÉ, como intención",
            "teal-6",
            seccion.metricas_declarativo.texto,
            seccion.declarativo,
        ),
    )


def texto_ejecucion(ejecucion: Ejecucion) -> str:
    """Cabecera de estado + salida, como se muestra en la pestaña Salida."""
    estado = (
        "correcta"
        if ejecucion.ok
        else "interrumpida por tiempo"
        if ejecucion.codigo_salida is None
        else f"con error (código {ejecucion.codigo_salida})"
    )
    return f"# Ejecución {estado} en {ejecucion.duracion_ms} ms\n\n{ejecucion.salida}"


def filas_historial(ejecuciones: list[Ejecucion]) -> list[dict[str, str | int]]:
    return [
        {
            "id": e.id,
            "fecha": e.creada_en.strftime("%Y-%m-%d %H:%M:%S"),
            "resultado": "✔ correcta" if e.ok else "✖ fallida",
            "codigo": "—" if e.codigo_salida is None else str(e.codigo_salida),
            "duracion": f"{e.duracion_ms} ms",
        }
        for e in ejecuciones
    ]


def resumen_sincronizacion(sincronizacion: Sincronizacion) -> str:
    if not sincronizacion.hubo_cambios:
        return f"Sin cambios: {len(sincronizacion.sin_cambios)} secciones al día."
    partes = (
        (len(sincronizacion.creadas), "nuevas"),
        (len(sincronizacion.actualizadas), "actualizadas"),
        (len(sincronizacion.eliminadas), "eliminadas"),
        (len(sincronizacion.sin_cambios), "sin cambios"),
    )
    return "Sincronizado: " + ", ".join(f"{n} {texto}" for n, texto in partes if n) + "."
