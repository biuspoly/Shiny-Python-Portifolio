import sys
from pathlib import Path

from shiny import App, render, ui

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:  # no Shinylive a saída é a do navegador, sem reconfigure
    pass

from core.dados import data_base  # noqa: E402
from core.layout import Grupo, Item, ligar_menu, mini_valuebox, pagina_app  # noqa: E402
from pages.Comodatos.pag_comodatos import comodatos_server, comodatos_ui  # noqa: E402
from pages.Devolucoes.pag_devolucoes import devolucoes_server, devolucoes_ui  # noqa: E402
from pages.Frotas.pag_frotas import frotas_server, frotas_ui  # noqa: E402
from pages.Romaneios.pag_romaneios import romaneios_server, romaneios_ui  # noqa: E402

PASTA_APP = Path(__file__).parent

MENU = [
    Item("romaneios", "Romaneios", "route"),
    Item("devolucoes", "Devoluções", "rotate-left"),
    Item("frotas", "Frotas", "truck"),
    Grupo(
        "Comodatos",
        "handshake",
        [
            Item("comodatos", "Equipamentos", "snowflake"),
        ],
    ),
]

PAINEIS = {
    "romaneios": romaneios_ui("romaneios"),
    "devolucoes": devolucoes_ui("devolucoes"),
    "frotas": frotas_ui("frotas"),
    "comodatos": comodatos_ui("comodatos"),
}

app_ui = pagina_app("Logístico", MENU, PAINEIS, direita=ui.output_ui("cabecalho"))


def server(input, output, session):
    ligar_menu(input, MENU)
    romaneios_server("romaneios")
    devolucoes_server("devolucoes")
    frotas_server("frotas")
    comodatos_server("comodatos")

    @render.ui
    def cabecalho():
        return mini_valuebox("Dados de", data_base().strftime("%d/%m/%Y"))


app = App(app_ui, server, static_assets=PASTA_APP / "www")
