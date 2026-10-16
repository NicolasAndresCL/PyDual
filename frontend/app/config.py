"""Configuración del frontend desde variables de entorno (pydantic-settings)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfiguracionUI(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    api_url: str = Field(description="URL base de la API, p. ej. http://api:8000.")
    # Debe superar el límite de ejecución de la API (60 s): si no, «Ejecutar
    # todo» cortaría la espera antes de que la API conteste.
    tiempo_espera_api_s: float = Field(default=90, gt=0)
    ui_host: str = Field(default="127.0.0.1", description="Interfaz de escucha.")
    ui_puerto: int = Field(default=8080, gt=0, lt=65536)


@lru_cache
def obtener_configuracion() -> ConfiguracionUI:
    return ConfiguracionUI()  # type: ignore[call-arg]  # los campos vienen del entorno
