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
from core.carregamento import com_carregamento  # noqa: E402
from core.config import NOME_APP, NOME_PORTFOLIO  # noqa: E402
from core.cores import (  # noqa: E402
    BTN_CANCELAR,
    BTN_CANCELAR_HOVER,
    BTN_CONFIRMAR,
    BTN_CONFIRMAR_HOVER,
    DESTAQUE,
    INPUTS_BG,
    ROXO_CLARO,
    ROXO_FUNDO,
    ROXO_MAIS_CLARO,
    SIDEBAR_BG,
    TABELA_CABECALHO_BG,
    TABELA_CABECALHO_TEXTO,
    TABELA_FUNDO_CLARO,
    TABELA_TEXTO_ESCURO,
    TEXTO,
    TEXTO_INPUTS,
)
from core.forca_style import forca_style  # noqa: E402
from pages.Emprestimos import pag_emprestimos_server, pag_emprestimos_ui  # noqa: E402
from pages.Extrato import pag_extrato_server, pag_extrato_ui  # noqa: E402
from pages.Fluxo_Financeiro import pag_fluxo_cabecalho, pag_fluxo_server, pag_fluxo_ui  # noqa: E402
from pages.Juros import pag_juros_server, pag_juros_ui  # noqa: E402
from pages.PPF.Dados.dados_ppf import PASTA_PARQUET  # noqa: E402

PASTA_APP = Path(__file__).parent

# CSS embutido na página (não por <link>): mesmo desenho do app original.
CSS_ESTILO = (PASTA_APP / "www" / "css" / "style.css").read_text(encoding="utf-8")
CSS_INICIAL = (PASTA_APP / "www" / "css" / "inicial.css").read_text(encoding="utf-8")

# (código, rótulo, ícone do faicons). A ordem é a do menu.
MENU = [
    ("flx", "Fluxo Financeiro", "money-bill-transfer"),
    ("emp", "Empréstimos", "hand-holding-dollar"),
    ("jur", "Juros", "percent"),
    ("ppf_xtr", "Extratos", "file-invoice-dollar"),
]
ROTULO_ATUALIZAR = "Atualizar 🗘"
PRIMEIRA = MENU[0][0]

# Tabelas de onde sai o "Atualizado em" de cada tela (vale a mais recente).
MAPA_ATUALIZACAO_ABA = {
    "flx": ("extratos_fabricas_tabela", "emprestimos_revendas"),
    "emp": ("contas_pagar", "titulos_pagos_emprestimos"),
    "jur": ("contas_pagar",),
}

PAINEIS = {
    "flx": lambda: com_carregamento(pag_fluxo_ui(None)),
    "emp": lambda: com_carregamento(pag_emprestimos_ui(None)),
    "jur": lambda: com_carregamento(pag_juros_ui(None)),
    # Sem carregamento: a tela nasce vazia e só consulta quando se gera os dados.
    "ppf_xtr": lambda: pag_extrato_ui(None),
}
CABECALHOS = {"flx": pag_fluxo_cabecalho}


def _menu() -> list:
    return [
        ui.input_action_button(
            f"link_{codigo}",
            rotulo,
            icon=icon_svg(icone, a11y="deco"),
            class_="selecionado" if codigo == PRIMEIRA else None,
        )
        for codigo, rotulo, icone in MENU
    ]


app_ui = ui.page_sidebar(
    ui.sidebar(
        _menu(),
        gap="12px",
        padding="50px 10px 0 10px",
        width="240px",
        open={"desktop": "open", "mobile": "closed"},
    ),
    ui.navset_hidden(
        *[ui.nav_panel(None, PAINEIS[codigo](), value=codigo) for codigo, *_ in MENU],
        id="conteudo_tabs",
        selected=PRIMEIRA,
    ),
    ui.head_content(ui.tags.style(CSS_INICIAL)),
    ui.tags.style(f"""
        :root {{
            --cor-sidebar: {SIDEBAR_BG};
            --cor-destaque: {DESTAQUE};
            --cor-texto-sidebar: {TEXTO};
            --cor-roxo-claro: {ROXO_CLARO};
            --cor-roxo-mais-claro: {ROXO_MAIS_CLARO};
            --cor-roxo-fundo: {ROXO_FUNDO};
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
    ui.tags.script(src=forca_style("js/ppf.js")),
    # O Fluxo Financeiro: Ctrl/Shift+clique marca a célula, dois cliques abrem o balão.
    ui.tags.script(src=forca_style("js/fluxo.js")),
    title=ui.div(
        ui.tags.b(f"{NOME_APP} - {NOME_PORTFOLIO}", class_="cabecalho-app-nome"),
        # O nome da tela ao lado do título, num navset que troca junto com o conteúdo.
        ui.navset_hidden(
            *[
                ui.nav_panel(None, ui.span(rotulo, class_="cabecalho-app-titulo"), value=codigo)
                for codigo, rotulo, _ in MENU
            ],
            id="titulo_tabs",
            selected=PRIMEIRA,
        ),
        ui.div(
            # A faixa própria de cada tela (no Fluxo: o botão Fábrica e o Histórico).
            ui.navset_hidden(
                *[
                    ui.nav_panel(None, CABECALHOS[codigo](None) if codigo in CABECALHOS else ui.div(), value=codigo)
                    for codigo, *_ in MENU
                ],
                id="cabecalho_tabs",
                selected=PRIMEIRA,
            ),
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
    @reactive.calc
    def revenda_atual() -> str | None:
        valores = parse_qs(session.clientdata.url_search().lstrip("?")).get("REVENDA")
        return valores[0] if valores else None

    sinal_do_fluxo = pag_fluxo_server(revenda_atual)
    pag_emprestimos_server(revenda_atual)
    pag_juros_server(revenda_atual)
    # O Atualizar do topo, na aba Extratos, é a consulta ao ERP; o estado volta para o cartão do topo.
    estado_extrato = reactive.value({})
    pag_extrato_server(
        revenda_atual,
        aba_atual=lambda: input.conteudo_tabs() if "conteudo_tabs" in input else None,
        atualizar=input.bt_atualizar_xtr,
        estado=estado_extrato,
    )

    @render.ui
    def valuebox_atualizacao():
        aba = input.conteudo_tabs() if "conteudo_tabs" in input else None
        if aba == "ppf_xtr":
            estado = estado_extrato()
            rodando = bool(estado.get("rodando"))
            botao = ui.input_action_button(
                "bt_atualizar_xtr",
                "Atualizando" if rodando else ROTULO_ATUALIZAR,
                class_="btn-atualizar-fin",
                title="Consultando o ERP..." if rodando else "Consultar o ERP agora",
                disabled=rodando,
            )
            return ui.div(botao, cartao_atualizacao(estado.get("consultado_em"), DESTAQUE), class_="cabecalho-fin")
        tabelas = MAPA_ATUALIZACAO_ABA.get(aba)
        if not tabelas:
            return None
        if aba == "flx":
            sinal_do_fluxo()
        return cartao_atualizacao(obter_atualizacao(PASTA_PARQUET, *tabelas), DESTAQUE)

    def _ligar_botao(codigo: str) -> None:
        @reactive.effect
        @reactive.event(input[f"link_{codigo}"])
        def _():
            for navset in ("conteudo_tabs", "titulo_tabs", "cabecalho_tabs"):
                ui.update_navset(navset, selected=codigo)

    for codigo, *_ in MENU:
        _ligar_botao(codigo)


app = App(app_ui, server, static_assets=PASTA_APP / "www")
