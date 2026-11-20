import sys
from pathlib import Path

from shiny import App, render, ui

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:  # no Shinylive a saída é a do navegador, sem reconfigure
    pass

from core.dados import data_base  # noqa: E402
from core.layout import Grupo, Item, ligar_menu, mini_valuebox, pagina_app  # noqa: E402
from pages.Documentos.pag_documentos import documentos_server, documentos_ui  # noqa: E402
from pages.Escrituracao.pag_escrituracao import escrituracao_server, escrituracao_ui  # noqa: E402
from pages.Manifestacao.pag_manifestacao import manifestacao_server, manifestacao_ui  # noqa: E402
from pages.Painel.pag_painel import painel_server, painel_ui  # noqa: E402

PASTA_APP = Path(__file__).parent

MENU = [
    Item("painel", "Painel", "gauge-high"),
    Item("documentos", "Documentos", "file-invoice"),
    Grupo(
        "Conferência",
        "list-check",
        [
            Item("manifestacao", "Manifestação", "stamp"),
            Item("escrituracao", "Escrituração", "book"),
        ],
    ),
]

PAINEIS = {
    "painel": painel_ui("painel"),
    "documentos": documentos_ui("documentos"),
    "manifestacao": manifestacao_ui("manifestacao"),
    "escrituracao": escrituracao_ui("escrituracao"),
}

app_ui = pagina_app("Fiscal", MENU, PAINEIS, direita=ui.output_ui("cabecalho"))


def server(input, output, session):
    ligar_menu(input, MENU)
    painel_server("painel")
    documentos_server("documentos")
    manifestacao_server("manifestacao")
    escrituracao_server("escrituracao")

    @render.ui
    def cabecalho():
        return mini_valuebox("Dados de", data_base().strftime("%d/%m/%Y"))


app = App(app_ui, server, static_assets=PASTA_APP / "www")
