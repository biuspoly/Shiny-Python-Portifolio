import sys
from pathlib import Path

from shiny import App, render, ui

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:  # no Shinylive a saída é a do navegador, sem reconfigure
    pass

from core.dados import data_base  # noqa: E402
from core.layout import Grupo, Item, ligar_menu, mini_valuebox, pagina_app  # noqa: E402
from pages.Conciliacao.pag_conciliacao import conciliacao_server, conciliacao_ui  # noqa: E402
from pages.Farol.pag_farol import farol_server, farol_ui  # noqa: E402
from pages.Fluxo.pag_fluxo import fluxo_server, fluxo_ui  # noqa: E402
from pages.Pagar.pag_pagar import pagar_server, pagar_ui  # noqa: E402

PASTA_APP = Path(__file__).parent

MENU = [
    Item("fluxo", "Fluxo de Caixa", "chart-line"),
    Item("pagar", "Contas a Pagar", "file-invoice-dollar"),
    Grupo(
        "Operação",
        "gears",
        [
            Item("conciliacao", "Conciliação", "scale-balanced"),
            Item("farol", "Farol de Caixa", "traffic-light"),
        ],
    ),
]

PAINEIS = {
    "fluxo": fluxo_ui("fluxo"),
    "pagar": pagar_ui("pagar"),
    "conciliacao": conciliacao_ui("conciliacao"),
    "farol": farol_ui("farol"),
}

app_ui = pagina_app("Financeiro", MENU, PAINEIS, direita=ui.output_ui("cabecalho"))


def server(input, output, session):
    ligar_menu(input, MENU)
    fluxo_server("fluxo")
    pagar_server("pagar")
    conciliacao_server("conciliacao")
    farol_server("farol")

    @render.ui
    def cabecalho():
        return mini_valuebox("Dados de", data_base().strftime("%d/%m/%Y"))


app = App(app_ui, server, static_assets=PASTA_APP / "www")
