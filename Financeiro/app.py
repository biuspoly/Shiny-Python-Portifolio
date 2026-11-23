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
from core.config import NOME_APP, REVENDAS_CNPJ  # noqa: E402
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
from pages.PPF.pag_dados_manuais import pag_dados_manuais_server, pag_dados_manuais_ui  # noqa: E402
from pages.PPF.pag_diario import pag_diario_cabecalho, pag_diario_server, pag_diario_ui  # noqa: E402
from pages.PPF.pag_pagamentos import pag_pagamentos_server, pag_pagamentos_ui  # noqa: E402

PASTA_APP = Path(__file__).parent
GRUPO_TODAS = "TODAS AS REVENDAS"

# CSS embutido na página (não por <link>): mesmo desenho do app original.
CSS_ESTILO = (PASTA_APP / "www" / "css" / "style.css").read_text(encoding="utf-8")
CSS_INICIAL = (PASTA_APP / "www" / "css" / "inicial.css").read_text(encoding="utf-8")

# (código, rótulo, ícone, grupo). A ordem é a do menu; item com grupo vira accordion junto com os
# seguintes do mesmo grupo. Ícone terminado em ".svg" é imagem de www/img; o resto, nome do faicons.
MENU = [
    ("ppf", "Diário Financeiro", "img/ppf/composicao_black.svg", "Diário Financeiro"),
    ("ppf_pag", "Pagamentos", "img/ppf/pagamentos.svg", "Diário Financeiro"),
    ("ppf_man", "Dados Manuais", "img/ppf/dados_manuais.svg", "Diário Financeiro"),
    ("ppf_xtr", "Extratos", "file-invoice-dollar", None),
    # Fluxo Financeiro divide o ícone com o Fluxo da fábrica, como no original.
    ("flx", "Fluxo Financeiro", "img/ppf/fluxo_fabrica.svg", None),
    ("emp", "Empréstimos", "img/ppf/receber.svg", None),
    ("jur", "Juros", "percent", None),
]
ICONE_DO_GRUPO = {"Diário Financeiro": "img/ppf/composicao_black.svg"}
# O grupo cujo cabeçalho é a própria página: o clique nele abre o Diário.
PAGINA_DO_GRUPO = {"Diário Financeiro": "ppf"}
ROTULO_ATUALIZAR = "Atualizar 🗘"
PRIMEIRA = MENU[0][0]

# Tabelas de onde sai o "Atualizado em" de cada tela (vale a mais recente).
MAPA_ATUALIZACAO_ABA = {
    "ppf": ("contas_pagar", "extratos_bancos", "composicao"),
    "ppf_pag": ("contas_pagar", "titulos_pagos", "extrato_banco"),
    "ppf_man": ("dados_manuais",),
    "flx": ("extratos_fabricas_tabela", "emprestimos_revendas"),
    "emp": ("contas_pagar", "titulos_pagos_emprestimos"),
    "jur": ("contas_pagar",),
}

PAINEIS = {
    "ppf": lambda: com_carregamento(pag_diario_ui(None)),
    "ppf_pag": lambda: com_carregamento(pag_pagamentos_ui(None)),
    "ppf_man": lambda: com_carregamento(pag_dados_manuais_ui(None)),
    "flx": lambda: com_carregamento(pag_fluxo_ui(None)),
    "emp": lambda: com_carregamento(pag_emprestimos_ui(None)),
    "jur": lambda: com_carregamento(pag_juros_ui(None)),
    # Sem carregamento: a tela nasce vazia e só consulta quando se gera os dados.
    "ppf_xtr": lambda: pag_extrato_ui(None),
}
CABECALHOS = {"ppf": pag_diario_cabecalho, "flx": pag_fluxo_cabecalho}


def _icone(nome: str):
    if nome.endswith(".svg"):
        return ui.tags.img(src=nome, class_="menu-icone", alt="")
    return icon_svg(nome, a11y="deco")


def _menu() -> list:
    botoes, itens, grupo_atual = [], [], None

    def fechar_grupo():
        if not itens:
            return
        pagina = f"link_{PAGINA_DO_GRUPO[grupo_atual]}" if grupo_atual in PAGINA_DO_GRUPO else None
        ids = {item.attrs.get("id") for item in itens}
        icone = ICONE_DO_GRUPO.get(grupo_atual)
        botoes.append(
            ui.accordion(
                ui.accordion_panel(grupo_atual, *itens, **({"icon": _icone(icone)} if icone else {})),
                open=pagina not in ids and f"link_{PRIMEIRA}" in ids,
                **({"data-pagina-do-grupo": pagina} if pagina in ids else {}),
            )
        )
        itens.clear()

    for codigo, rotulo, icone, grupo in MENU:
        botao = ui.input_action_button(
            f"link_{codigo}",
            rotulo,
            icon=_icone(icone),
            class_="selecionado" if codigo == PRIMEIRA else None,
            hidden=PAGINA_DO_GRUPO.get(grupo) == codigo,
        )
        if grupo != grupo_atual:
            fechar_grupo()
            grupo_atual = grupo
        (botoes if grupo is None else itens).append(botao)
        if codigo == "ppf":
            # "Contas a Pagar" é um item, não página: abre o Diário rolado até a seção.
            itens.append(
                ui.input_action_button("link_ppf_contas", "Contas a Pagar", icon=_icone("img/ppf/contas_pagar.svg"))
            )
    fechar_grupo()
    return botoes


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
        ui.tags.img(src="img/logo_ficticia.svg", height="40vh"),
        # O nome da tela ao lado do título, num navset que troca junto com o conteúdo.
        ui.navset_hidden(
            *[
                ui.nav_panel(None, ui.span(rotulo, class_="cabecalho-app-titulo"), value=codigo)
                for codigo, rotulo, *_ in MENU
            ],
            id="titulo_tabs",
            selected=PRIMEIRA,
        ),
        ui.div(
            # No original a revenda vem da URL (?REVENDA=), escolhida no portal; aqui, desta caixa.
            ui.div(
                ui.input_select(
                    "revenda_escolhida",
                    None,
                    {GRUPO_TODAS: "Todas as revendas", **{nome: nome for nome in REVENDAS_CNPJ}},
                    selected=GRUPO_TODAS,
                ),
                class_="cabecalho-revenda",
                title="Revenda",
            ),
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
        if valores:
            return valores[0]
        return input.revenda_escolhida() or GRUPO_TODAS

    sinal_do_fluxo = pag_fluxo_server(revenda_atual)
    pag_emprestimos_server(revenda_atual)
    pag_juros_server(revenda_atual)
    pag_diario_server(revenda_atual)
    pag_pagamentos_server(revenda_atual)
    pag_dados_manuais_server(revenda_atual)
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

    @reactive.effect
    @reactive.event(input.link_ppf_contas)
    async def _ir_para_contas_pagar():
        for navset in ("conteudo_tabs", "titulo_tabs", "cabecalho_tabs"):
            ui.update_navset(navset, selected="ppf")
        await session.send_custom_message("rolarAte", {"id": "diario-secao_contas_pagar"})

    @reactive.effect
    @reactive.event(input.link_ppf)
    async def _diario_no_topo():
        await session.send_custom_message("rolarAte", {"id": "diario-secao_diario"})


app = App(app_ui, server, static_assets=PASTA_APP / "www")
