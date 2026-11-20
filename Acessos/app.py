import sys
from pathlib import Path

from shiny import App, render, ui

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:  # no Shinylive a saída é a do navegador, sem reconfigure
    pass

from core.dados import data_base  # noqa: E402
from core.layout import Item, ligar_menu, mini_valuebox, pagina_app  # noqa: E402
from pages.Historico.pag_historico import historico_server, historico_ui  # noqa: E402
from pages.Permissoes.pag_permissoes import permissoes_server, permissoes_ui  # noqa: E402
from pages.Visao_Geral.pag_visao_geral import visao_geral_server, visao_geral_ui  # noqa: E402

PASTA_APP = Path(__file__).parent

MENU = [
    Item("visao", "Visão Geral", "gauge-high"),
    Item("permissoes", "Permissões", "user-lock"),
    Item("historico", "Histórico", "clock-rotate-left"),
]

PAINEIS = {
    "visao": visao_geral_ui("visao"),
    "permissoes": permissoes_ui("permissoes"),
    "historico": historico_ui("historico"),
}

app_ui = pagina_app("Acessos", MENU, PAINEIS, direita=ui.output_ui("cabecalho"))


def server(input, output, session):
    ligar_menu(input, MENU)
    visao_geral_server("visao")
    permissoes_server("permissoes")
    historico_server("historico")

    @render.ui
    def cabecalho():
        return mini_valuebox("Dados de", data_base().strftime("%d/%m/%Y"))


app = App(app_ui, server, static_assets=PASTA_APP / "www")
