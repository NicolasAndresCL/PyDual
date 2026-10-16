"""Ejecución en subproceso: salida, códigos, timeout y entorno filtrado."""

from __future__ import annotations

import pytest

from app.servicios.ejecucion import ejecutar, entorno_minimo


def test_ejecucion_correcta_devuelve_salida_y_codigo_cero() -> None:
    resultado = ejecutar('print("hola, ñandú")', tiempo_limite_s=30)
    assert (resultado.salida, resultado.codigo_salida, resultado.ok) == ("hola, ñandú", 0, True)
    assert resultado.duracion_ms >= 0


def test_un_error_combina_stdout_y_stderr() -> None:
    resultado = ejecutar('print("antes")\nraise ValueError("mal")', tiempo_limite_s=30)
    assert not resultado.ok
    assert resultado.codigo_salida == 1
    assert resultado.salida.startswith("antes\n")
    assert "ValueError: mal" in resultado.salida


def test_sin_salida_lo_dice() -> None:
    assert ejecutar("x = 1", tiempo_limite_s=30).salida == "[la celda no imprimió nada]"


def test_tiempo_agotado() -> None:
    resultado = ejecutar("import time\ntime.sleep(10)", tiempo_limite_s=1)
    assert resultado.codigo_salida is None
    assert not resultado.ok
    assert resultado.salida == "[tiempo agotado: más de 1 s]"


def test_el_subproceso_no_ve_credenciales(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://usuario:secreto@db/app")
    codigo = 'import os\nprint(os.environ.get("DATABASE_URL", "sin credenciales"))'
    assert ejecutar(codigo, tiempo_limite_s=30).salida == "sin credenciales"


def test_entorno_minimo_conserva_solo_lo_imprescindible() -> None:
    entorno = {"PATH": "/bin", "SystemRoot": "C:\\Windows", "DATABASE_URL": "x", "HOME": "/h"}
    assert entorno_minimo(entorno) == {
        "PATH": "/bin",
        "SystemRoot": "C:\\Windows",
        "PYTHONIOENCODING": "utf-8",
    }
