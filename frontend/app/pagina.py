"""La página del comparativo, construida con NiceGUI.

Cada visitante tiene su propia instancia de `Comparativo` (estado por pestaña
del navegador). Los datos llegan siempre por HTTP a través de `ClienteApi`; si
la API no responde se muestra un aviso con «Reintentar» y la página sigue viva.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial

from nicegui import events, ui

from app.cliente import ClienteApi, ErrorApi
from app.modelos import Ejecucion, SeccionDetalle, SeccionResumen
from app.presentacion import (
    ATAJOS,
    COLOR_VEREDICTO,
    Accion,
    accion_para_tecla,
    filas_historial,
    paneles,
    resumen_sincronizacion,
    texto_ejecucion,
)

# F1 (ayuda), F2 y F5 (recargar) son del navegador: se anulan para que lleguen
# como atajos de la aplicación. `ui.keyboard` sigue recibiendo el evento.
EVITAR_ATAJOS_DEL_NAVEGADOR = """
<script>
document.addEventListener("keydown", (e) => {
  if (["F1", "F2", "F5"].includes(e.key)) e.preventDefault();
});
</script>
"""

SALIDA_INICIAL = "Pulsa F5 (o «Ejecutar») para ejecutar esta celda y ver su salida real."
PESTANA_SALIDA = "Salida"
COLUMNAS_HISTORIAL = [
    {"name": "fecha", "label": "Fecha", "field": "fecha", "align": "left"},
    {"name": "resultado", "label": "Resultado", "field": "resultado", "align": "left"},
    {"name": "codigo", "label": "Código", "field": "codigo"},
    {"name": "duracion", "label": "Duración", "field": "duracion"},
]
COLUMNAS_RESUMEN = [
    {"name": "imperativo", "label": "Patrón imperativo", "field": "imperativo", "align": "left"},
    {
        "name": "declarativo",
        "label": "Equivalente declarativo",
        "field": "declarativo",
        "align": "left",
    },
]


class Comparativo:
    """Estado y vista de una sesión de navegador."""

    def __init__(self, cliente: ClienteApi) -> None:
        self.cliente = cliente
        self.secciones: list[SeccionResumen] = []
        self.total = 0
        self.actual: SeccionDetalle | None = None
        self.salida = SALIDA_INICIAL
        self.ejecuciones: list[Ejecucion] = []
        self.aviso: str | None = None
        self.consulta = ""

    # -- construcción --

    async def montar(self) -> None:
        ui.add_head_html(EVITAR_ATAJOS_DEL_NAVEGADOR)
        ui.keyboard(on_key=self._al_pulsar)

        with ui.header().classes("items-center gap-1 bg-grey-10"):
            ui.label("Imperativo vs. declarativo").classes("text-lg font-bold mr-4")
            ui.space()
            # (texto, icono, atajo, acción, marca para localizarlo en los tests)
            botones = (
                ("Introducción", "menu_book", "F1", self.mostrar_introduccion, "introduccion"),
                ("Resumen", "table_chart", "F2", self.mostrar_resumen, "resumen"),
                ("Sincronizar", "sync", None, self.sincronizar, "sincronizar"),
                ("Ejecutar", "play_arrow", "F5", self.ejecutar_seccion, "ejecutar"),
                ("Ejecutar todo", "fast_forward", "Ctrl+F5", self.ejecutar_todo, "ejecutar-todo"),
            )
            for texto, icono, atajo, accion, marca in botones:
                self._boton(texto, icono, atajo, accion, marca)

        with ui.left_drawer(value=True, bordered=True).classes("p-2").props("width=320"):
            ui.label("EJERCICIOS").classes("text-xs font-bold text-grey-7")
            self.filtro = (
                ui.input(placeholder="Filtrar  ( / )", on_change=self._al_filtrar)
                .props("dense outlined clearable debounce=250")
                .classes("w-full")
            )
            self.lista()

        self.vista_aviso()
        self.detalle()
        await self.recargar()

    @staticmethod
    def _boton(
        texto: str,
        icono: str,
        atajo: str | None,
        accion: Callable[[], Awaitable[None]],
        marca: str,
    ) -> None:
        boton = (
            ui.button(texto, icon=icono, on_click=accion)
            .props("flat color=white no-caps")
            .mark(marca)
        )
        if atajo:
            boton.tooltip(atajo)

    # -- vistas refrescables --

    @ui.refreshable_method
    def vista_aviso(self) -> None:
        if self.aviso is None:
            return
        with ui.row().classes("w-full items-center gap-2 p-3 bg-red-1 text-red-10 rounded"):
            ui.icon("cloud_off")
            ui.label(self.aviso).classes("grow")
            ui.button("Reintentar", on_click=self.recargar).props("flat color=red-10").mark(
                "reintentar"
            )

    @ui.refreshable_method
    def lista(self) -> None:
        if self.consulta:
            ui.label(f"{len(self.secciones)} de {self.total} ejercicios").classes(
                "text-xs text-grey-7"
            )
        with ui.list().props("dense separator").classes("w-full"):
            for seccion in self.secciones:
                activa = self.actual is not None and self.actual.numero == seccion.numero
                with (
                    # `partial` y no `lambda n=...`: NiceGUI pasa el evento a
                    # cualquier parámetro que encuentre en la firma.
                    ui.item(on_click=partial(self.seleccionar, seccion.numero))
                    .props("clickable")
                    .classes("bg-blue-1" if activa else "")
                    .mark(f"seccion-{seccion.numero}")
                ):
                    with ui.item_section():
                        ui.item_label(seccion.etiqueta)
                    with ui.item_section().props("side"):
                        ui.icon("circle", size="xs", color=COLOR_VEREDICTO[seccion.veredicto.tipo])

    @ui.refreshable_method
    def detalle(self) -> None:
        seccion = self.actual
        if seccion is None:
            ui.label("Elige un ejercicio de la lista.").classes("text-grey-7")
            return

        ui.label(seccion.etiqueta).classes("text-xl font-bold")
        with ui.row().classes("items-center gap-2"):
            ui.badge(seccion.veredicto.tipo.value, color=COLOR_VEREDICTO[seccion.veredicto.tipo])
            ui.label(seccion.veredicto.mensaje).classes("text-sm")

        with ui.row().classes("w-full no-wrap gap-4 items-stretch"):
            for titulo, color, metricas, codigo in paneles(seccion):
                with ui.card().classes("w-1/2 min-w-0"):
                    ui.label(titulo).classes(f"font-bold text-{color}")
                    ui.label(metricas).classes("text-xs text-grey-7")
                    ui.code(codigo).classes("w-full text-sm")

        with ui.tabs().classes("w-full").props("align=left no-caps") as pestanas:
            por_que = ui.tab("Por qué")
            referencia = ui.tab("Referencia")
            comprobacion = ui.tab("Comprobación")
            salida = ui.tab(PESTANA_SALIDA)
            historial = ui.tab("Historial")
        with ui.tab_panels(pestanas, value=por_que).classes("w-full") as self.paneles:
            with ui.tab_panel(por_que):
                ui.markdown(seccion.explicacion or "_(la celda no trae explicación)_")
            with ui.tab_panel(referencia):
                ui.label(seccion.referencia or "(la celda no trae referencia)").classes(
                    "font-mono text-sm whitespace-pre-wrap"
                )
            with ui.tab_panel(comprobacion):
                ui.code(seccion.epilogo or "# la celda no imprime nada").classes("w-full")
            with ui.tab_panel(salida):
                self.vista_salida()
            with ui.tab_panel(historial):
                self.vista_historial()

    @ui.refreshable_method
    def vista_salida(self) -> None:
        ui.label(self.salida).classes("font-mono text-sm whitespace-pre-wrap")

    @ui.refreshable_method
    def vista_historial(self) -> None:
        if not self.ejecuciones:
            ui.label("Todavía no se ha ejecutado esta sección.").classes("text-grey-7")
            return
        ui.table(columns=COLUMNAS_HISTORIAL, rows=filas_historial(self.ejecuciones), row_key="id")

    # -- datos --

    def _avisar(self, error: ErrorApi) -> None:
        self.aviso = error.mensaje
        self.vista_aviso.refresh()
        ui.notify(error.mensaje, type="negative")

    def _limpiar_aviso(self) -> None:
        if self.aviso is not None:
            self.aviso = None
            self.vista_aviso.refresh()

    async def recargar(self) -> None:
        """Vuelve a pedir la lista y la sección actual (o la primera)."""
        try:
            lista = await self.cliente.listar(self.consulta)
        except ErrorApi as error:
            self._avisar(error)
            return
        self._limpiar_aviso()
        self.secciones, self.total = lista.secciones, lista.total
        numero = (
            self.actual.numero if self.actual else next((s.numero for s in self.secciones), None)
        )
        if numero is not None:
            await self.seleccionar(numero)
        else:
            self.lista.refresh()

    async def seleccionar(self, numero: int) -> None:
        try:
            self.actual = await self.cliente.seccion(numero)
            self.ejecuciones = await self.cliente.historial(numero)
        except ErrorApi as error:
            self._avisar(error)
            return
        self.salida = SALIDA_INICIAL
        self.lista.refresh()
        self.detalle.refresh()

    async def _al_filtrar(self, evento: events.ValueChangeEventArguments) -> None:
        self.consulta = (evento.value or "").strip()
        try:
            lista = await self.cliente.listar(self.consulta)
        except ErrorApi as error:
            self._avisar(error)
            return
        self.secciones, self.total = lista.secciones, lista.total
        self.lista.refresh()

    # -- acciones --

    async def _mostrar_ejecucion(
        self, aviso: str, ejecutar: Callable[[], Awaitable[Ejecucion]]
    ) -> Ejecucion | None:
        self.paneles.set_value(PESTANA_SALIDA)
        self.salida = aviso
        self.vista_salida.refresh()
        try:
            ejecucion = await ejecutar()
        except ErrorApi as error:
            self.salida = f"No se pudo ejecutar: {error.mensaje}"
            self.vista_salida.refresh()
            self._avisar(error)
            return None
        self.salida = texto_ejecucion(ejecucion)
        self.vista_salida.refresh()
        return ejecucion

    async def ejecutar_seccion(self) -> None:
        if self.actual is None:
            return
        numero = self.actual.numero
        ejecucion = await self._mostrar_ejecucion(
            f"Ejecutando «{self.actual.titulo}»…", partial(self.cliente.ejecutar_seccion, numero)
        )
        if ejecucion is not None:
            self.ejecuciones = [ejecucion, *self.ejecuciones]
            self.vista_historial.refresh()

    async def ejecutar_todo(self) -> None:
        if self.actual is None:
            return
        await self._mostrar_ejecucion(
            "Ejecutando el notebook completo y comprobando equivalencias…",
            self.cliente.ejecutar_cuaderno,
        )

    async def sincronizar(self) -> None:
        try:
            resultado = await self.cliente.sincronizar()
        except ErrorApi as error:
            self._avisar(error)
            return
        ui.notify(resumen_sincronizacion(resultado), type="positive")
        await self.recargar()

    async def mostrar_introduccion(self) -> None:
        try:
            cuaderno = await self.cliente.cuaderno()
        except ErrorApi as error:
            self._avisar(error)
            return
        with ui.dialog() as dialogo, ui.card().classes("w-[860px] max-w-full"):
            ui.markdown(cuaderno.intro)
            ui.separator()
            ui.label("Atajos de teclado").classes("font-bold")
            for tecla, descripcion in ATAJOS:
                ui.label(f"{tecla} — {descripcion}").classes("text-sm")
            ui.button("Cerrar", on_click=dialogo.close).props("flat")
        dialogo.open()

    async def mostrar_resumen(self) -> None:
        try:
            cuaderno = await self.cliente.cuaderno()
        except ErrorApi as error:
            self._avisar(error)
            return
        with ui.dialog() as dialogo, ui.card().classes("w-[960px] max-w-full"):
            ui.label("Resumen: qué reemplaza a qué").classes("text-lg font-bold")
            ui.table(
                columns=COLUMNAS_RESUMEN,
                rows=[fila.model_dump() for fila in cuaderno.resumen],
                row_key="imperativo",
            ).classes("w-full")
            if cuaderno.nota_final:
                ui.markdown(cuaderno.nota_final).classes("text-sm text-grey-8")
            ui.button("Cerrar", on_click=dialogo.close).props("flat")
        dialogo.open()

    async def _al_pulsar(self, evento: events.KeyEventArguments) -> None:
        if not evento.action.keydown or evento.action.repeat:
            return
        match accion_para_tecla(evento.key.name, ctrl=evento.modifiers.ctrl):
            case Accion.INTRODUCCION:
                await self.mostrar_introduccion()
            case Accion.RESUMEN:
                await self.mostrar_resumen()
            case Accion.EJECUTAR:
                await self.ejecutar_seccion()
            case Accion.EJECUTAR_TODO:
                await self.ejecutar_todo()
            case Accion.FILTRAR:
                self.filtro.run_method("focus")
            case Accion.LIMPIAR_FILTRO:
                self.filtro.set_value("")
            case None:
                pass


async def construir(cliente: ClienteApi) -> Comparativo:
    """Monta la página completa en el contexto del cliente NiceGUI actual."""
    comparativo = Comparativo(cliente)
    await comparativo.montar()
    return comparativo
