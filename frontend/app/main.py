"""Punto de entrada del frontend NiceGUI (puerto 8080).

python -m app.main
"""

from __future__ import annotations

from nicegui import app, ui

from app.cliente import ClienteApi
from app.config import ConfiguracionUI, obtener_configuracion
from app.pagina import construir


def registrar(config: ConfiguracionUI) -> None:
    """Registra la página y el endpoint de salud del propio frontend."""

    @ui.page("/", title="Imperativo vs. declarativo")
    async def inicio() -> None:
        await construir(ClienteApi(config.api_url, config.tiempo_espera_api_s))

    @app.get("/healthz")
    def salud() -> dict[str, str]:
        # Sano = el servidor de la UI atiende. Que la API esté viva lo vigila
        # su propio healthcheck; la página ya avisa si no responde.
        return {"estado": "ok"}


def main() -> None:  # pragma: no cover - arranca el servidor real
    config = obtener_configuracion()
    registrar(config)
    ui.run(
        host=config.ui_host,
        port=config.ui_puerto,
        title="Imperativo vs. declarativo",
        reload=False,
        show=False,
        dark=None,
        language="es",
        show_welcome_message=False,
    )


if __name__ in {"__main__", "__mp_main__"}:  # pragma: no cover
    main()
