"""Fiscal: as notas que a revenda recebe, do XML ao livro de entradas (dados fictícios).

No sistema real, este app substituiu o Qive (antigo Arquivei): a coleta das NF-e e CT-e direto da Receita, a
manifestação, a conferência e a escrituração ficaram em casa. Foi essa troca que deu origem ao RNFe, o pacote
de R para NF-e. Aqui está a versão enxuta, com quatro telas: Painel, NF-e, CT-e e Escrituração.
"""

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
from core.config import NOME_APP  # noqa: E402
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
from core.notas import PASTA as PASTA_NOTAS  # noqa: E402
from core.tela import CSS_FISCAL  # noqa: E402
from pages.CTe.pag_cte import pag_cte_server, pag_cte_ui  # noqa: E402
from pages.Escrituracao.pag_escrituracao import pag_escrituracao_server, pag_escrituracao_ui  # noqa: E402
from pages.NFe.pag_nfe import pag_nfe_server, pag_nfe_ui  # noqa: E402
from pages.Painel.pag_painel import pag_painel_server, pag_painel_ui  # noqa: E402

PASTA_APP = Path(__file__).parent
CSS_ESTILO = (PASTA_APP / "www" / "css" / "style.css").read_text(encoding="utf-8")
CSS_INICIAL = (PASTA_APP / "www" / "css" / "inicial.css").read_text(encoding="utf-8")

TABELA_DA_PAGINA = {"pnl": "nfe_recebidas", "nfe": "nfe_recebidas", "cte": "cte_recebidos", "esc": "nfe_recebidas"}

_PAGINAS = [
    ("pnl", "bt_painel", "Painel", "gauge-high"),
    ("nfe", "bt_nfe", "NF-e recebidas", "file-invoice"),
    ("cte", "bt_cte", "CT-e recebidos", "truck"),
    ("esc", "bt_escrituracao", "Escrituração", "book"),
]


def _menu() -> list:
    return [
        ui.input_action_button(botao, rotulo, icon=icon_svg(icone), class_="selecionado" if valor == "pnl" else None)
        for valor, botao, rotulo, icone in _PAGINAS
    ]


app_ui = ui.page_sidebar(
    ui.sidebar(_menu(), gap="10px", padding="50px 0 0 0", width="200px", open={"desktop": "open", "mobile": "closed"}),
    ui.navset_hidden(
        ui.nav_panel(None, pag_painel_ui(), value="pnl"),
        ui.nav_panel(None, pag_nfe_ui(), value="nfe"),
        ui.nav_panel(None, pag_cte_ui(), value="cte"),
        ui.nav_panel(None, pag_escrituracao_ui(), value="esc"),
        id="conteudo_tabs",
        selected="pnl",
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
    ui.tags.style(CSS_FISCAL),
    ui.tags.script(src=forca_style("js/sidebar.js")),
    ui.tags.script(src=forca_style("js/custom.js")),
    ui.tags.script(src=forca_style("js/echarts.min.js")),
    title=ui.div(
        ui.tags.img(src="img/logo_ficticia.svg", height="40vh"),
        ui.div(ui.output_ui("valuebox_atualizacao"), class_="cabecalho-app-direita"),
        class_="cabecalho-app",
    ),
    # Flatly já compilado: o Shinylive não tem o libsass que o tema usaria na hora.
    theme=PASTA_APP / "www" / "css" / "flatly.min.css",
    window_title=NOME_APP,
)


def server(input, output, session):
    pag_painel_server()
    pag_nfe_server()
    pag_cte_server()
    pag_escrituracao_server()

    @render.ui
    def valuebox_atualizacao():
        aba = input.conteudo_tabs() if "conteudo_tabs" in input else "pnl"
        return cartao_atualizacao(obter_atualizacao(PASTA_NOTAS, TABELA_DA_PAGINA.get(aba, "nfe_recebidas")), DESTAQUE)

    def _navegar(botao: str, valor: str):
        @reactive.effect
        @reactive.event(input[botao])
        def _():
            ui.update_navset("conteudo_tabs", selected=valor)

    for valor, botao, _rotulo, _icone in _PAGINAS:
        _navegar(botao, valor)


app = App(app_ui, server, static_assets=PASTA_APP / "www")
