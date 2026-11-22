import sys
from pathlib import Path

from faicons import icon_svg
from shiny import App, reactive, ui

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:  # no Shinylive a saída é a do navegador, sem reconfigure
    pass

from core.cores import DESTAQUE, INPUTS_BG, SIDEBAR_BG, TEXTO, TEXTO_ESCURO, TEXTO_INPUTS  # noqa: E402
from core.forca_style import forca_style  # noqa: E402
from pages.Historico_Acessos.pag_hist_acessos import pag_hist_acessos_server, pag_hist_acessos_ui  # noqa: E402
from pages.Permissoes.pag_permissoes import pag_permissoes_server, pag_permissoes_ui  # noqa: E402
from pages.Visao_Geral.pag_visao_geral import pag_visao_geral_server, pag_visao_geral_ui  # noqa: E402

TITULO_APP = "Acompanhamento de Acessos - Portfólio Marlon Amaral"
PASTA_APP = Path(__file__).parent

# CSS embutido na página (não por <link>): mesmo desenho do app original.
CSS_ESTILO = (PASTA_APP / "www" / "css" / "style.css").read_text(encoding="utf-8")
CSS_INICIAL = (PASTA_APP / "www" / "css" / "inicial.css").read_text(encoding="utf-8")

# Botão do menu -> painel que ele abre.
MENU = {"link_pag_permissoes": "permissoes", "link_pag_visao_geral": "vgeral", "link_pag_hist_acessos": "histacessos"}

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.accordion(
            ui.accordion_panel(
                "Usuários",
                ui.input_action_button(
                    "link_pag_permissoes", "Acesso por painel", icon=icon_svg("lock"), class_="selecionado"
                ),
                icon=icon_svg("users-gear"),
            ),
            open="Usuários",
        ),
        ui.input_action_button("link_pag_visao_geral", "Visão Geral", icon=icon_svg("chart-line")),
        ui.input_action_button("link_pag_hist_acessos", "Histórico de Acessos", icon=icon_svg("list")),
        gap="10px",
        padding="50px 0 0 0",
        width="200px",
        open={"desktop": "open", "mobile": "closed"},
    ),
    ui.navset_hidden(
        ui.nav_panel(None, pag_permissoes_ui("permissoes"), value="permissoes"),
        ui.nav_panel(None, pag_visao_geral_ui("vgeral"), value="vgeral"),
        ui.nav_panel(None, pag_hist_acessos_ui("histacessos"), value="histacessos"),
        id="conteudo_tabs",
        selected="permissoes",
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
            --acessos-texto-escuro: {TEXTO_ESCURO};
        }}
    """),
    ui.tags.style(CSS_ESTILO),
    ui.busy_indicators.options(spinner_color=DESTAQUE),
    ui.tags.script(src=forca_style("js/echarts.min.js")),
    ui.tags.script(src=forca_style("js/sidebar.js")),
    ui.tags.script(src=forca_style("js/acessos.js")),
    ui.tags.script(src=forca_style("js/custom.js")),
    ui.tags.script(src=forca_style("js/tabela_resize.js")),
    title=TITULO_APP,
    # Flatly já compilado: o Shinylive não tem o libsass que o tema usaria na hora.
    theme=PASTA_APP / "www" / "css" / "flatly.min.css",
    window_title=TITULO_APP,
)


def server(input, output, session):
    pag_permissoes_server("permissoes")
    pag_visao_geral_server("vgeral")
    pag_hist_acessos_server("histacessos")

    def _ligar_botao(botao: str, painel: str) -> None:
        @reactive.effect
        @reactive.event(input[botao])
        def _():
            ui.update_navset("conteudo_tabs", selected=painel)

    for botao, painel in MENU.items():
        _ligar_botao(botao, painel)


app = App(app_ui, server, static_assets=PASTA_APP / "www")
