"""Parser del notebook: de texto JSON a `CuadernoParseado`. Sin I/O.

Es la reescritura declarativa de `cargar()` de la v1 (`comparativo.py`) y
respeta el mismo contrato de marcadores:

- una celda markdown con título (`## 7. Lo que sea`) y explicación, seguida de
- una celda de código con el bloque de referencia entre tres líneas `# ===`,
  el marcador `# --- Imperativo ---`, el marcador `# --- Declarativo ---` y los
  `print(...)` de comprobación (el epílogo).

La v1 recorre las celdas con un bucle y variables de estado («título
pendiente»). Aquí la misma regla se expresa como datos: cada celda de código es
un ejercicio si y solo si la celda relevante inmediatamente anterior es un
markdown de título. `tests/test_paridad_v1.py` garantiza que ambos parsers
producen exactamente las mismas secciones.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum, auto
from itertools import pairwise
from typing import Any

from app.core.errores import CuadernoInvalido
from app.core.modelos import CuadernoParseado, FilaResumen, SeccionParseada

# El notebook marca cada mitad con un comentario de una línea. Se admite texto
# extra después de los dos puntos ("# --- Imperativo: cómo ---").
MARCA_IMPERATIVO = re.compile(r"^#\s*-{2,}\s*(Imperativo[^-]*?)\s*-{2,}\s*$", re.M)
MARCA_DECLARATIVO = re.compile(r"^#\s*-{2,}\s*(Declarativo[^-]*?)\s*-{2,}\s*$", re.M)
SEPARADOR_REFERENCIA = "# ==="
# Se compara contra el título ya normalizado sin tildes, por eso va sin acento.
TITULO_REFERENCIA = "METODOS Y CONSTRUCCIONES USADOS EN ESTA CELDA"
INICIO_EPILOGO = re.compile(r"^print\(", re.M)
TITULO_MARKDOWN = re.compile(r"^#{1,6}\s*(.+?)\s*$", re.M)
NUMERO_DE_TITULO = re.compile(r"^\d+\.\s*")

_SIN_TILDES = str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU")


class Rol(Enum):
    """Qué papel juega cada celda relevante dentro del notebook."""

    IGNORADA = auto()  # markdown vacío antes de la introducción
    INTRO = auto()
    TITULO = auto()  # markdown que abre un ejercicio
    RESUMEN = auto()  # markdown con la tabla «qué reemplaza a qué»
    CODIGO = auto()


@dataclass(frozen=True)
class Celda:
    rol: Rol
    texto: str


_CENTINELA = Celda(Rol.IGNORADA, "")


# --- Utilidades de texto ----------------------------------------------------


def sin_tildes(texto: str) -> str:
    """Normaliza solo lo necesario para comparar con o sin tildes (como la v1)."""
    return texto.translate(_SIN_TILDES)


def _texto(celda: dict[str, Any]) -> str:
    """Devuelve el `source` de una celda como un único str."""
    fuente = celda.get("source", "")
    return fuente if isinstance(fuente, str) else "".join(fuente)


def titulo_markdown(texto: str) -> str:
    """Primer encabezado del markdown, sin el número de ejercicio."""
    encabezado = TITULO_MARKDOWN.search(texto)
    return NUMERO_DE_TITULO.sub("", encabezado.group(1) if encabezado else "")


def _cuerpo_markdown(texto: str) -> str:
    return TITULO_MARKDOWN.sub("", texto, count=1).strip()


def _es_resumen(texto: str) -> bool:
    return sin_tildes(titulo_markdown(texto)).lower().startswith("resumen")


# --- Partes de una sección --------------------------------------------------


def _limpiar_referencia(bloque: str) -> str:
    """Convierte el bloque de comentarios de referencia en texto legible."""
    sin_almohadilla = (
        re.sub(r"^#\s?", "", linea)
        for linea in bloque.splitlines()
        if not linea.startswith(SEPARADOR_REFERENCIA)
    )
    return "\n".join(
        linea for linea in sin_almohadilla if sin_tildes(linea).strip() != TITULO_REFERENCIA
    ).strip("\n")


def separar_referencia(fuente: str) -> tuple[str, str]:
    """Separa el bloque de referencia del código ejecutable de la celda."""
    lineas = fuente.splitlines()
    separadores = [i for i, linea in enumerate(lineas) if linea.startswith(SEPARADOR_REFERENCIA)]
    match separadores:
        case [primero, _, corte, *_]:
            referencia = _limpiar_referencia("\n".join(lineas[primero : corte + 1]))
            return referencia, "\n".join(lineas[corte + 1 :]).strip("\n")
        case _:
            return "", fuente


def partir_declarativo(resto: str) -> tuple[str, str]:
    """Separa el código declarativo del epílogo que imprime la comparación.

    El epílogo arranca en el primer `print(` de nivel cero: de ahí en adelante
    la celda ya no enseña un enfoque, solo demuestra que ambos coinciden.
    """
    match INICIO_EPILOGO.search(resto):
        case None:
            return resto.strip("\n"), ""
        case coincidencia:
            corte = coincidencia.start()
            return resto[:corte].strip("\n"), resto[corte:].strip("\n")


def parsear_seccion(numero: int, titulo: str, explicacion: str, fuente: str) -> SeccionParseada:
    """Parte una celda de código en referencia, imperativo, declarativo y epílogo."""
    referencia, cuerpo = separar_referencia(fuente)
    imperativa = MARCA_IMPERATIVO.search(cuerpo)
    declarativa = MARCA_DECLARATIVO.search(cuerpo)
    if imperativa is None or declarativa is None:
        raise CuadernoInvalido(
            f"La sección {numero} no tiene las dos marcas.", seccion=numero, titulo=titulo
        )
    if imperativa.start() > declarativa.start():
        raise CuadernoInvalido(
            f"La sección {numero} tiene las marcas invertidas.", seccion=numero, titulo=titulo
        )
    declarativo, epilogo = partir_declarativo(cuerpo[declarativa.end() :])
    return SeccionParseada(
        numero=numero,
        titulo=titulo,
        explicacion=explicacion.strip(),
        referencia=referencia,
        imperativo=cuerpo[imperativa.end() : declarativa.start()].strip("\n"),
        declarativo=declarativo,
        epilogo=epilogo,
        fuente=fuente,
    )


def _celdas_de_fila(linea: str) -> list[str]:
    return [celda.strip() for celda in linea.strip().strip("|").split("|")]


def parsear_tabla_markdown(markdown: str) -> tuple[FilaResumen, ...]:
    """Extrae las filas de la tabla de dos columnas del resumen (sin encabezado)."""
    filas = tuple(
        FilaResumen(celdas[0].replace("`", ""), celdas[1].replace("`", ""))
        for celdas in (
            _celdas_de_fila(linea)
            for linea in markdown.splitlines()
            if linea.strip().startswith("|")
        )
        if len(celdas) == 2 and not set(celdas[0]) <= {"-", ":"}
    )
    return filas[1:]


def _nota_final(markdown: str) -> str:
    return "\n".join(
        linea
        for linea in markdown.splitlines()
        if not linea.strip().startswith("|") and not TITULO_MARKDOWN.fullmatch(linea)
    ).strip()


# --- Cuaderno completo ------------------------------------------------------


def _leer_celdas(texto: str) -> list[dict[str, Any]]:
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as error:
        raise CuadernoInvalido(
            "El notebook no es JSON válido.", linea=error.lineno, columna=error.colno
        ) from error
    match datos:
        case {"cells": list(celdas)}:
            return [celda for celda in celdas if isinstance(celda, dict)]
        case _:
            raise CuadernoInvalido("El notebook no tiene una lista de celdas («cells»).")


def _clasificar(celdas: list[dict[str, Any]]) -> tuple[Celda, ...]:
    """Asigna un rol a cada celda relevante y descarta el resto.

    Se descartan, igual que en la v1, las celdas de código vacías y las que no
    son ni markdown ni código: no abren ni cierran ningún ejercicio.
    """
    relevantes = [
        (celda["cell_type"], _texto(celda))
        for celda in celdas
        if celda.get("cell_type") == "markdown"
        or (celda.get("cell_type") == "code" and _texto(celda).strip())
    ]
    indice_intro = next(
        (i for i, (tipo, texto) in enumerate(relevantes) if tipo == "markdown" and texto.strip()),
        len(relevantes),
    )

    def rol(indice: int, tipo: str, texto: str) -> Rol:
        match tipo:
            case "code":
                return Rol.CODIGO
            case _ if indice < indice_intro:
                return Rol.IGNORADA
            case _ if indice == indice_intro:
                return Rol.INTRO
            case _ if _es_resumen(texto):
                return Rol.RESUMEN
            case _:
                return Rol.TITULO

    return tuple(Celda(rol(i, tipo, texto), texto) for i, (tipo, texto) in enumerate(relevantes))


def _abre_ejercicio(celda: Celda) -> bool:
    return celda.rol is Rol.TITULO and bool(titulo_markdown(celda.texto))


def parsear_cuaderno(texto: str) -> CuadernoParseado:
    """Convierte el JSON del notebook en un `CuadernoParseado`.

    Lanza `CuadernoInvalido` (con el número de sección cuando aplica) si el
    notebook no respeta el contrato.
    """
    celdas = _clasificar(_leer_celdas(texto))
    # Cada celda de código, emparejada con la celda relevante que la precede.
    pares = [
        (previa, actual)
        for previa, actual in pairwise((_CENTINELA, *celdas))
        if actual.rol is Rol.CODIGO
    ]
    ejercicios = [(previa, actual) for previa, actual in pares if _abre_ejercicio(previa)]

    secciones = tuple(
        parsear_seccion(
            numero,
            titulo_markdown(markdown.texto),
            _cuerpo_markdown(markdown.texto),
            codigo.texto,
        )
        for numero, (markdown, codigo) in enumerate(ejercicios, start=1)
    )
    if not secciones:
        raise CuadernoInvalido("El notebook no contiene secciones comparables.")

    resumen = next((c.texto for c in reversed(celdas) if c.rol is Rol.RESUMEN), "")
    return CuadernoParseado(
        intro=next((c.texto.strip() for c in celdas if c.rol is Rol.INTRO), ""),
        preludio=next(
            (codigo.texto for previa, codigo in pares if not _abre_ejercicio(previa)), ""
        ),
        secciones=secciones,
        resumen=parsear_tabla_markdown(resumen),
        nota_final=_nota_final(resumen),
        fuentes=tuple(codigo.texto for _, codigo in pares),
    )
