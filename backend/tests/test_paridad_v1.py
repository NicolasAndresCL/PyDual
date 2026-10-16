"""Paridad strangler-fig: el parser v2 reproduce exactamente a `cargar()` de la v1.

Mientras la v1 (`comparativo.py`, tkinter) siga viva, este test es el que
permite tocar el parser v2 sin miedo: cualquier divergencia sobre el notebook
rompe aquí.

La v1 NO forma parte de este repositorio: vive en el directorio padre del
proyecto de estudio (`ejercicios_practicos/`). Se busca en `$COMPARATIVO_V1` o,
si no está definida, en `../comparativo.py` respecto a la raíz del repo.

- Si el archivo no existe (clon aislado, CI), el test se OMITE con el motivo a la
  vista; el CI corre pytest con `-rs` para que el skip salga en el log.
- Si existe pero no se puede importar (p. ej. falta tkinter), el test FALLA: ahí
  sí hay algo roto que no debe esconderse.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app.core.parser import parsear_cuaderno
from tests.conftest import NOTEBOOK_REAL, RAIZ_REPO

CAMPOS = ("numero", "titulo", "explicacion", "referencia", "imperativo", "declarativo", "epilogo")


RUTA_V1 = Path(os.environ.get("COMPARATIVO_V1", RAIZ_REPO.parent / "comparativo.py"))


def _cargar_v1() -> ModuleType:
    ruta = RUTA_V1
    if not ruta.is_file():
        pytest.skip(f"v1 no disponible en {ruta}: paridad solo verificable junto a la v1")
    especificacion = importlib.util.spec_from_file_location("comparativo_v1", ruta)
    if especificacion is None or especificacion.loader is None:
        pytest.fail(f"No se encontró la v1 en {ruta}")
    modulo = importlib.util.module_from_spec(especificacion)
    # `@dataclass` busca el módulo de la clase en `sys.modules` para resolver las
    # anotaciones: sin registrarlo antes, `exec_module` revienta con AttributeError.
    sys.modules[especificacion.name] = modulo
    try:
        especificacion.loader.exec_module(modulo)
    except ImportError as error:  # típicamente: falta tkinter en el intérprete
        pytest.fail(f"No se pudo importar la v1 ({error}); instala tkinter, no lo saltes.")
    return modulo


@pytest.fixture(scope="module")
def ambos() -> tuple[object, object]:
    v1 = _cargar_v1()
    return v1.cargar(Path(NOTEBOOK_REAL)), parsear_cuaderno(NOTEBOOK_REAL.read_text("utf-8"))


def test_mismo_numero_de_secciones(ambos: tuple) -> None:
    viejo, nuevo = ambos
    assert len(nuevo.secciones) == len(viejo.secciones) == 20


def test_cada_seccion_es_identica_campo_a_campo(ambos: tuple) -> None:
    viejo, nuevo = ambos
    diferencias = [
        (s_nueva.numero, campo)
        for s_vieja, s_nueva in zip(viejo.secciones, nuevo.secciones, strict=True)
        for campo in CAMPOS
        # La v1 llama `intro` a lo que la v2 llama `explicacion`.
        if getattr(s_vieja, "intro" if campo == "explicacion" else campo) != getattr(s_nueva, campo)
    ]
    assert diferencias == []


def test_la_celda_ejecutable_es_la_misma(ambos: tuple) -> None:
    viejo, nuevo = ambos
    assert [s.fuente for s in viejo.secciones] == [s.fuente for s in nuevo.secciones]


def test_metadatos_del_cuaderno_identicos(ambos: tuple) -> None:
    viejo, nuevo = ambos
    assert nuevo.intro == viejo.intro
    assert nuevo.preludio == viejo.preludio
    assert [(f.imperativo, f.declarativo) for f in nuevo.resumen] == list(viejo.resumen)
    assert nuevo.nota_final == viejo.nota_final
    assert nuevo.fuentes == viejo.fuentes
