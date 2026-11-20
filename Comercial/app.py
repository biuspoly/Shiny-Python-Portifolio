import sys
from pathlib import Path

from shiny import App, render, ui

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:  # no Shinylive a saída é a do navegador, sem reconfigure
    pass

from core.dados import data_base  # noqa: E402
from core.layout import Grupo, Item, ligar_menu, mini_valuebox, pagina_app  # noqa: E402
from pages.Clientes.pag_carteira import carteira_server, carteira_ui  # noqa: E402
from pages.Diario_Venda.pag_diario_venda import diario_venda_server, diario_venda_ui  # noqa: E402
from pages.Mapa_Comercial.pag_mapa_comercial import mapa_comercial_server, mapa_comercial_ui  # noqa: E402
from pages.Markup.pag_markup import markup_server, markup_ui  # noqa: E402

PASTA_APP = Path(__file__).parent

MENU = [
    Item("diario", "Diário de Vendas", "house"),
    Grupo(
        "Clientes",
        "users",
        [
            Item("carteira", "Carteira", "address-book"),
            Item("mapa", "Mapa Comercial", "map-location-dot"),
        ],
    ),
    Item("markup", "Markup", "tags"),
]

PAINEIS = {
    "diario": diario_venda_ui("diario"),
    "carteira": carteira_ui("carteira"),
    "mapa": mapa_comercial_ui("mapa"),
    "markup": markup_ui("markup"),
}

app_ui = pagina_app("Comercial", MENU, PAINEIS, direita=ui.output_ui("cabecalho"))


def server(input, output, session):
    ligar_menu(input, MENU)
    diario_venda_server("diario")
    carteira_server("carteira")
    mapa_comercial_server("mapa")
    markup_server("markup")

    @render.ui
    def cabecalho():
        return mini_valuebox("Dados de", data_base().strftime("%d/%m/%Y"))


app = App(app_ui, server, static_assets=PASTA_APP / "www")
