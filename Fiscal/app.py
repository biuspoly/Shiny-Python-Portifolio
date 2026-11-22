import sys
from pathlib import Path
from urllib.parse import parse_qs

from faicons import icon_svg
from shiny import App, reactive, render, ui

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:  # no Shinylive a saída é a do navegador, sem reconfigure
    pass

from core.atualizacao import cartao_atualizacao, obter_atualizacao  # noqa: E402
from core.cache import PASTA as PASTA_CACHE  # noqa: E402
from core.carregamento import com_carregamento  # noqa: E402
from core.config import NOME_APP, NOME_PORTFOLIO, USUARIO_PORTFOLIO  # noqa: E402
from core.cores import (  # noqa: E402
    BTN_CANCELAR,
    BTN_CANCELAR_HOVER,
    BTN_CONFIRMAR,
    BTN_CONFIRMAR_HOVER,
    CLARO,
    DESTAQUE,
    FUNDO,
    INPUTS_BG,
    MAIS_CLARO,
    SIDEBAR_BG,
    TABELA_CABECALHO_BG,
    TABELA_CABECALHO_TEXTO,
    TABELA_FUNDO_CLARO,
    TABELA_TEXTO_ESCURO,
    TEXTO,
    TEXTO_INPUTS,
)
from core.forca_style import forca_style  # noqa: E402
from pages import PAGINAS  # noqa: E402

PASTA_APP = Path(__file__).parent

# CSS embutido na página (não por <link>): mesmo desenho do app original.
CSS_ESTILO = (PASTA_APP / "www" / "css" / "style.css").read_text(encoding="utf-8")
CSS_INICIAL = (PASTA_APP / "www" / "css" / "inicial.css").read_text(encoding="utf-8")

# (código, rótulo, ícone do faicons, grupo do menu). A ordem é a do menu.
MENU = [
    ("apu", "Apuração", "scale-balanced", "Análises"),
    ("fat", "Faturamento", "file-invoice-dollar", "Relatórios"),
]
ICONE_DO_GRUPO = {"Análises": "chart-line", "Relatórios": "print"}
PRIMEIRA = MENU[0][0]

# Tabelas de onde sai o "Atualizado em" de cada tela.
MAPA_ATUALIZACAO_ABA = {"apu": ("faturamento",), "fat": ("faturamento",)}


def _menu() -> list:
    botoes, grupo_atual, itens = [], None, []

    def fechar_grupo():
        nonlocal itens
        if itens:
            icone = ICONE_DO_GRUPO.get(grupo_atual)
            botoes.append(
                ui.accordion(
                    ui.accordion_panel(grupo_atual, *itens, **({"icon": icon_svg(icone)} if icone else {})),
                    open=any(item.attrs.get("id") == f"link_{PRIMEIRA}" for item in itens),
                )
            )
        itens = []

    for codigo, rotulo, icone, grupo in MENU:
        botao = ui.input_action_button(
            f"link_{codigo}",
            rotulo,
            icon=icon_svg(icone, a11y="deco"),
            class_="selecionado" if codigo == PRIMEIRA else None,
        )
        if grupo != grupo_atual:
            fechar_grupo()
            grupo_atual = grupo
        (botoes if grupo is None else itens).append(botao)
    fechar_grupo()
    return botoes


app_ui = ui.page_sidebar(
    ui.sidebar(
        _menu(), gap="12px", padding="50px 10px 0 10px", width="240px", open={"desktop": "open", "mobile": "closed"}
    ),
    ui.navset_hidden(
        *[ui.nav_panel(None, com_carregamento(PAGINAS[codigo][0](None)), value=codigo) for codigo, *_ in MENU],
        id="conteudo_tabs",
        selected=PRIMEIRA,
    ),
    ui.head_content(ui.tags.style(CSS_INICIAL)),
    ui.tags.style(f"""
        :root {{
            --cor-sidebar: {SIDEBAR_BG};
            --cor-destaque: {DESTAQUE};
            --cor-texto-sidebar: {TEXTO};
            --cor-claro: {CLARO};
            --cor-mais-claro: {MAIS_CLARO};
            --cor-fundo: {FUNDO};
            --bs-primary: {SIDEBAR_BG};
            --bs-body-color: {TEXTO_INPUTS};
            --bs-body-bg: {INPUTS_BG};
            --bs-card-bg: {INPUTS_BG};
            --tabela-fundo-claro: {TABELA_FUNDO_CLARO};
            --tabela-texto-escuro: {TABELA_TEXTO_ESCURO};
            --tabela-cabecalho-bg: {TABELA_CABECALHO_BG};
            --tabela-cabecalho-texto: {TABELA_CABECALHO_TEXTO};
            --btn-confirmar: {BTN_CONFIRMAR};
            --btn-confirmar-escuro: {BTN_CONFIRMAR_HOVER};
            --btn-cancelar: {BTN_CANCELAR};
            --btn-cancelar-escuro: {BTN_CANCELAR_HOVER};
        }}
    """),
    ui.tags.style(CSS_ESTILO),
    ui.busy_indicators.options(spinner_color=DESTAQUE),
    ui.tags.script(src=forca_style("js/sidebar.js")),
    ui.tags.script(src=forca_style("js/custom.js")),
    ui.tags.script(src=forca_style("js/marcar.js")),
    ui.tags.script(src=forca_style("js/tabela_ordem.js")),
    ui.tags.script(src=forca_style("js/acao_linha.js")),
    ui.tags.script(src=forca_style("js/echarts.min.js")),
    title=ui.div(
        ui.tags.b(f"{NOME_APP} - {NOME_PORTFOLIO}", class_="cabecalho-app-nome"),
        ui.div(ui.output_ui("valuebox_atualizacao"), class_="cabecalho-app-direita"),
        class_="cabecalho-app",
    ),
    # Flatly já compilado: o Shinylive não tem o libsass que o tema usaria na hora.
    theme=PASTA_APP / "www" / "css" / "flatly.min.css",
    window_title=NOME_APP,
)


def server(input, output, session):
    @reactive.calc
    def revenda_atual() -> str | None:
        valores = parse_qs(session.clientdata.url_search().lstrip("?")).get("REVENDA")
        return valores[0] if valores else None

    usuario_atual = reactive.value(USUARIO_PORTFOLIO)
    versao_cache = reactive.value(0)
    for codigo, *_ in MENU:
        PAGINAS[codigo][1](revenda_atual, usuario_atual, versao_cache)

    @render.ui
    def valuebox_atualizacao():
        aba = input.conteudo_tabs() if "conteudo_tabs" in input else None
        tabelas = MAPA_ATUALIZACAO_ABA.get(aba)
        if not tabelas:
            return None
        return cartao_atualizacao(obter_atualizacao(PASTA_CACHE, *tabelas), DESTAQUE)

    def _ligar_botao(codigo: str) -> None:
        @reactive.effect
        @reactive.event(input[f"link_{codigo}"])
        def _():
            ui.update_navset("conteudo_tabs", selected=codigo)

    for codigo, *_ in MENU:
        _ligar_botao(codigo)


app = App(app_ui, server, static_assets=PASTA_APP / "www")
