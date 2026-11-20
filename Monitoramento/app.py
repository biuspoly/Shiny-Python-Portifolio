import sys
from pathlib import Path

from shiny import App, render, ui

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:  # no Shinylive a saída é a do navegador, sem reconfigure
    pass

from core.dados import data_base  # noqa: E402
from core.layout import Item, ligar_menu, mini_valuebox, pagina_app  # noqa: E402
from pages.Erros.pag_erros import erros_server, erros_ui  # noqa: E402
from pages.Rotinas.pag_rotinas import rotinas_server, rotinas_ui  # noqa: E402
from pages.Usuarios.pag_usuarios import usuarios_server, usuarios_ui  # noqa: E402
from pages.Visao_Geral.pag_visao_geral import visao_geral_server, visao_geral_ui  # noqa: E402

PASTA_APP = Path(__file__).parent

MENU = [
    Item("visao", "Visão Geral", "gauge-high"),
    Item("usuarios", "Usuários", "users"),
    Item("rotinas", "Rotinas", "clock-rotate-left"),
    Item("erros", "Erros", "triangle-exclamation"),
]

PAINEIS = {
    "visao": visao_geral_ui("visao"),
    "usuarios": usuarios_ui("usuarios"),
    "rotinas": rotinas_ui("rotinas"),
    "erros": erros_ui("erros"),
}

app_ui = pagina_app("Monitoramento", MENU, PAINEIS, direita=ui.output_ui("cabecalho"))


def server(input, output, session):
    ligar_menu(input, MENU)
    visao_geral_server("visao")
    usuarios_server("usuarios")
    rotinas_server("rotinas")
    erros_server("erros")

    @render.ui
    def cabecalho():
        return mini_valuebox("Dados de", data_base().strftime("%d/%m/%Y"))


app = App(app_ui, server, static_assets=PASTA_APP / "www")
