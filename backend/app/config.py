"""Configuración tipada desde variables de entorno (pydantic-settings).

Nada sensible tiene valor por defecto: sin `DATABASE_URL` ni `NOTEBOOK_RUTA`
la aplicación no arranca, en vez de arrancar contra una base equivocada.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracion(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    database_url: str = Field(description="URL de SQLAlchemy de la base de datos.")
    notebook_ruta: Path = Field(description="Ruta del notebook que es la fuente de verdad.")
    tiempo_limite_ejecucion_s: int = Field(default=60, gt=0, le=600)
    sincronizar_al_arrancar: bool = True
    limite_historial: int = Field(default=50, gt=0, le=500)
    nivel_log: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("database_url")
    @classmethod
    def _con_driver_psycopg(cls, valor: str) -> str:
        """Acepta `postgres://` y `postgresql://` y fuerza el driver psycopg v3."""
        esquema, separador, resto = valor.partition("://")
        match esquema:
            case "postgres" | "postgresql":
                return f"postgresql+psycopg{separador}{resto}"
            case _:
                return valor


@lru_cache
def obtener_configuracion() -> Configuracion:
    return Configuracion()  # type: ignore[call-arg]  # los campos vienen del entorno
