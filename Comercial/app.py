import sys
from pathlib import Path

from faicons import icon_svg
from shiny import App, reactive, render, ui

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:  # no Shinylive a saída é a do navegador, sem reconfigure
    pass

from core.atualizacao import cartao_atualizacao, obter_atualizacao  # noqa: E402
from core.config import CNPJ_PADRAO, NOME_APP, NOME_PORTFOLIO  # noqa: E402
from core.cores import (  # noqa: E402
    CARD_CABECALHO_BG,
    CARD_CABECALHO_TEXTO,
    CARD_FUNDO_CLARO,
    CARD_TEXTO_ESCURO,
    DESTAQUE,
    INPUTS_BG,
    SIDEBAR_BG,
    TEXTO,
    TEXTO_INPUTS,
)
from core.forca_style import forca_style  # noqa: E402
from pages.Curva_ABC.pag_curva_abc import pag_curva_abc_server, pag_curva_abc_ui  # noqa: E402
from pages.Diario_Venda.pag_diario_venda import pag_diario_venda_server, pag_diario_venda_ui  # noqa: E402
from pages.Mapa_Comercial import pag_mapa_comercial_server, pag_mapa_comercial_ui  # noqa: E402

PASTA_APP = Path(__file__).parent
PASTA_BD_COMERCIAL = PASTA_APP / "data" / "bd_comercial"

# CSS embutido na página (não por <link>): mesmo desenho do app original.
CSS_ESTILO = (PASTA_APP / "www" / "css" / "style.css").read_text(encoding="utf-8")
CSS_INICIAL = (PASTA_APP / "www" / "css" / "inicial.css").read_text(encoding="utf-8")

# Tabela que diz o "Atualizado em" de cada página.
TABELA_DA_PAGINA = {
    "ven": "tb_diario_venda",
    "cabc": f"tb_curva_abc_{CNPJ_PADRAO}_atual",
    "mco": "tb_mapa_pot",
}


def _menu() -> list:
    return [
        ui.input_action_button("bt_diario_venda", "Diário de Vendas", icon=icon_svg("house"), class_="selecionado"),
        ui.input_action_button("bt_curva_abc", "Curva ABC", icon=icon_svg("chart-line")),
        ui.input_action_button("bt_mapa_comercial", "Mapa Comercial", icon=icon_svg("map-location-dot")),
    ]


app_ui = ui.page_sidebar(
    ui.sidebar(
        _menu(),
        gap="10px",
        padding="50px 0 0 0",
        width="200px",
        open={"desktop": "open", "mobile": "closed"},
    ),
    ui.navset_hidden(
        ui.nav_panel(None, pag_diario_venda_ui(), value="ven"),
        ui.nav_panel(None, pag_curva_abc_ui(None), value="cabc"),
        ui.nav_panel(None, pag_mapa_comercial_ui(), value="mco"),
        id="conteudo_tabs",
        selected="ven",
    ),
    ui.head_content(ui.tags.style(CSS_INICIAL)),
    ui.tags.style(f"""
        :root {{
            --cor-sidebar: {SIDEBAR_BG};
            --cor-destaque: {DESTAQUE};
            --cor-texto-sidebar: {TEXTO};
            --bs-primary: {SIDEBAR_BG};
            --bs-body-color: {TEXTO_INPUTS};
            --bs-body-bg: {INPUTS_BG};
            --bs-card-bg: {INPUTS_BG};
            --card-fundo-claro: {CARD_FUNDO_CLARO};
            --card-texto-escuro: {CARD_TEXTO_ESCURO};
            --card-cabecalho-bg: {CARD_CABECALHO_BG};
            --card-cabecalho-texto: {CARD_CABECALHO_TEXTO};
        }}
    """),
    ui.tags.style(CSS_ESTILO),
    ui.tags.script(src=forca_style("js/sidebar.js")),
    ui.tags.script(src=forca_style("js/custom.js")),
    ui.tags.script(src=forca_style("js/tabela_resize.js")),
    ui.tags.script(src=forca_style("js/tabela_ordem.js")),
    ui.tags.script(src=forca_style("js/cabecalho_grupo.js")),
    ui.tags.script(src=forca_style("js/echarts.min.js")),
    ui.tags.script(src=forca_style("js/diario_venda.js")),
    title=ui.div(
        ui.div(
            ui.tags.img(src="img/marca.svg", alt=""),
            ui.tags.b(f"{NOME_APP} - {NOME_PORTFOLIO}"),
            class_="cabecalho-marca",
        ),
        ui.div(
            ui.output_ui("cabecalho_dias"),
            ui.output_ui("valuebox_atualizacao"),
            class_="cabecalho-app-direita",
        ),
        class_="cabecalho-app",
    ),
    # Flatly já compilado: o Shinylive não tem o libsass que o tema usaria na hora.
    theme=PASTA_APP / "www" / "css" / "flatly.min.css",
    window_title=NOME_APP,
)


def server(input, output, session):
    versao_cache = reactive.value(0, name="versao_cache")
    resumo_cabecalho_dias = reactive.value(None, name="resumo_cabecalho_dias")
    pag_diario_venda_server(versao_cache, resumo_cabecalho_dias)
    pag_curva_abc_server(versao_cache)
    # O mapa só monta na 1ª visita à página (é a consulta mais pesada).
    mapa_comercial_solicitado = reactive.value(0, name="mapa_comercial_solicitado")
    pag_mapa_comercial_server(mapa_comercial_solicitado, versao_cache)

    @render.ui
    def cabecalho_dias():
        aba_atual = input.conteudo_tabs() if "conteudo_tabs" in input else None
        resumo = resumo_cabecalho_dias()
        if not resumo or aba_atual is None or resumo["aba"] != aba_atual:
            return None
        return ui.div(*resumo["cards"], class_="cabecalho-dias")

    @render.ui
    def valuebox_atualizacao():
        aba_atual = input.conteudo_tabs() if "conteudo_tabs" in input else None
        tabela = TABELA_DA_PAGINA.get(aba_atual)
        if tabela is None:
            return None
        return cartao_atualizacao(obter_atualizacao(PASTA_BD_COMERCIAL, tabela), DESTAQUE)

    @reactive.effect
    @reactive.event(input.bt_diario_venda)
    def _():
        ui.update_navset("conteudo_tabs", selected="ven")

    @reactive.effect
    @reactive.event(input.bt_curva_abc)
    def _():
        ui.update_navset("conteudo_tabs", selected="cabc")

    @reactive.effect
    @reactive.event(input.bt_mapa_comercial)
    def _():
        mapa_comercial_solicitado.set(mapa_comercial_solicitado() + 1)
        ui.update_navset("conteudo_tabs", selected="mco")


app = App(app_ui, server, static_assets=PASTA_APP / "www")
