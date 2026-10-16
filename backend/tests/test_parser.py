"""Parser del notebook: contrato de marcadores y casos límite."""

from __future__ import annotations

import pytest

from app.core.errores import CuadernoInvalido
from app.core.modelos import FilaResumen
from app.core.parser import (
    parsear_cuaderno,
    parsear_seccion,
    parsear_tabla_markdown,
    partir_declarativo,
    separar_referencia,
    sin_tildes,
    titulo_markdown,
)
from tests.conftest import celda, codigo_seccion, notebook, notebook_minimo


def test_notebook_minimo_produce_secciones_intro_preludio_y_resumen() -> None:
    cuaderno = parsear_cuaderno(notebook_minimo(secciones=3))

    assert [s.numero for s in cuaderno.secciones] == [1, 2, 3]
    assert [s.titulo for s in cuaderno.secciones] == ["Ejercicio 1", "Ejercicio 2", "Ejercicio 3"]
    assert cuaderno.intro == "# Título\n\nIntroducción del cuaderno."
    assert cuaderno.preludio.startswith("import sys")
    assert cuaderno.resumen == (FilaResumen("for + append", "comprehension"),)
    assert cuaderno.nota_final == "Nota final."
    # Preludio + 3 ejercicios + celda final de comprobación.
    assert len(cuaderno.fuentes) == 5


def test_seccion_partida_en_sus_cuatro_piezas() -> None:
    seccion = parsear_cuaderno(notebook_minimo(1)).secciones[0]

    assert seccion.explicacion == "Explicación del ejercicio 1."
    assert seccion.referencia == "range(n)\n    Secuencia perezosa."
    assert seccion.imperativo == "x = []\nfor i in range(3):\n    x.append(i)"
    assert seccion.declarativo == "y = list(range(3))  # 1"
    assert seccion.epilogo == 'print("iguales:", x == y)'
    assert seccion.etiqueta == " 1. Ejercicio 1"


def test_source_como_lista_de_lineas_equivale_a_str() -> None:
    como_lista = notebook(
        celda("markdown", ["# Intro\n", "texto"]),
        celda("markdown", ["## 1. Uno\n", "\n", "Por qué."]),
        celda("code", codigo_seccion().splitlines(keepends=True)),
    )
    assert parsear_cuaderno(como_lista).secciones[0].titulo == "Uno"


def test_celdas_vacias_raw_y_markdown_en_blanco_no_alteran_el_emparejamiento() -> None:
    texto = notebook(
        celda("markdown", "   "),  # en blanco antes de la intro: se ignora
        celda("markdown", "# Intro"),
        celda("raw", "lo que sea"),
        celda("markdown", "## 1. Uno"),
        celda("code", "   \n"),  # código vacío: no consume el título
        celda("raw", "otra"),
        celda("code", codigo_seccion()),
        "no es un dict",  # type: ignore[arg-type]
    )
    cuaderno = parsear_cuaderno(texto)

    assert cuaderno.intro == "# Intro"
    assert [s.titulo for s in cuaderno.secciones] == ["Uno"]
    assert cuaderno.preludio == ""


def test_codigo_sin_markdown_previo_es_preludio_y_no_ejercicio() -> None:
    texto = notebook(
        celda("markdown", "# Intro"),
        celda("code", "import os"),
        celda("code", "import sys"),
        celda("markdown", "## 1. Uno"),
        celda("code", codigo_seccion()),
        celda("code", "print('suelta')"),
    )
    cuaderno = parsear_cuaderno(texto)

    assert cuaderno.preludio == "import os"
    assert len(cuaderno.secciones) == 1
    assert cuaderno.fuentes[-1] == "print('suelta')"


def test_markdown_sin_encabezado_o_solo_numero_no_abre_ejercicio() -> None:
    texto = notebook(
        celda("markdown", "# Intro"),
        celda("markdown", "texto sin encabezado"),
        celda("code", "a = 1"),
        celda("markdown", "## 7."),
        celda("code", "b = 2"),
        celda("markdown", "## 1. Uno"),
        celda("code", codigo_seccion()),
    )
    cuaderno = parsear_cuaderno(texto)

    assert [s.titulo for s in cuaderno.secciones] == ["Uno"]
    assert cuaderno.preludio == "a = 1"


def test_resumen_con_tilde_y_sin_numero_se_reconoce() -> None:
    texto = notebook(
        celda("markdown", "# Intro"),
        celda("markdown", "## 1. Uno"),
        celda("code", codigo_seccion()),
        celda("markdown", "## Résumen\n|a|b|\n|-|-|\n|c|d|"),
        celda("markdown", "## Resúmen final\n|a|b|\n|-|-|\n|e|f|"),
    )
    # Las tildes no impiden reconocerlo; si hay varias, gana la última (como la v1).
    assert parsear_cuaderno(texto).resumen == (FilaResumen("e", "f"),)


def test_sin_tabla_resumen_queda_vacio() -> None:
    cuaderno = parsear_cuaderno(
        notebook(
            celda("markdown", "# Intro"),
            celda("markdown", "## 1. Uno"),
            celda("code", codigo_seccion(referencia=False)),
        )
    )
    assert cuaderno.resumen == ()
    assert cuaderno.nota_final == ""
    assert cuaderno.secciones[0].referencia == ""


@pytest.mark.parametrize(
    ("texto", "mensaje"),
    [
        ("{no es json", "no es JSON válido"),
        ("[]", "lista de celdas"),
        ('{"cells": "x"}', "lista de celdas"),
        (notebook(celda("markdown", "# Solo intro")), "no contiene secciones"),
    ],
)
def test_notebooks_invalidos_lanzan_error_de_dominio(texto: str, mensaje: str) -> None:
    with pytest.raises(CuadernoInvalido, match=mensaje) as error:
        parsear_cuaderno(texto)
    assert error.value.http_status == 422


def test_json_roto_informa_linea_y_columna() -> None:
    with pytest.raises(CuadernoInvalido) as error:
        parsear_cuaderno('{\n  "cells": [,]\n}')
    assert error.value.detalle() == {"linea": 2, "columna": 13}


@pytest.mark.parametrize(
    ("fuente", "mensaje"),
    [
        ("# --- Imperativo ---\nx = 1", "no tiene las dos marcas"),
        ("# --- Declarativo ---\nx = 1", "no tiene las dos marcas"),
        ("# --- Declarativo ---\ny\n# --- Imperativo ---\nx", "marcas invertidas"),
    ],
)
def test_seccion_rota_informa_su_numero(fuente: str, mensaje: str) -> None:
    texto = notebook(
        celda("markdown", "# Intro"),
        celda("markdown", "## 1. Bien"),
        celda("code", codigo_seccion()),
        celda("markdown", "## 2. Rota"),
        celda("code", fuente),
    )
    with pytest.raises(CuadernoInvalido, match=mensaje) as error:
        parsear_cuaderno(texto)
    assert error.value.detalle() == {"seccion": 2, "titulo": "Rota"}


def test_marcas_admiten_texto_extra() -> None:
    fuente = "# --- Imperativo: cómo ---\na = 1\n# --- Declarativo: qué ---\nb = 1"
    seccion = parsear_seccion(1, "t", "e", fuente)
    assert (seccion.imperativo, seccion.declarativo, seccion.epilogo) == ("a = 1", "b = 1", "")


def test_separar_referencia_sin_tres_separadores_devuelve_todo_como_codigo() -> None:
    fuente = "# ====\n# algo\n# ====\nx = 1"
    assert separar_referencia(fuente) == ("", fuente)


def test_separar_referencia_quita_el_titulo_con_o_sin_tildes() -> None:
    fuente = "# ===\n# METODOS Y CONSTRUCCIONES USADOS EN ESTA CELDA\n# ===\n#len(x)\n# ===\ncodigo"
    assert separar_referencia(fuente) == ("len(x)", "codigo")


def test_partir_declarativo_corta_en_el_primer_print_de_nivel_cero() -> None:
    resto = "\nfor x in y:\n    print(x)\nz = 1\nprint(z)\nprint(2)\n"
    assert partir_declarativo(resto) == ("for x in y:\n    print(x)\nz = 1", "print(z)\nprint(2)")


def test_tabla_markdown_ignora_separadores_y_filas_de_otro_ancho() -> None:
    markdown = "| A | B |\n|:--|--:|\n| `x` | `y` |\n| 1 | 2 | 3 |\ntexto\n| p | q |"
    assert parsear_tabla_markdown(markdown) == (FilaResumen("x", "y"), FilaResumen("p", "q"))
    assert parsear_tabla_markdown("sin tabla") == ()


def test_utilidades_de_texto() -> None:
    assert sin_tildes("Éxito á í ó ú ñ") == "Exito a i o u ñ"
    assert titulo_markdown("texto\n### 12. Título  \nmás") == "Título"
    assert titulo_markdown("sin encabezado") == ""
