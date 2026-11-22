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
from core.carregamento import com_carregamento  # noqa: E402
from core.config import NOME_APP, NOME_PORTFOLIO  # noqa: E402
from core.cores import (  # noqa: E402
    DESTAQUE,
    FROTA_CABECALHO_BG,
    FROTA_CABECALHO_TEXTO,
    FROTA_FUNDO_CLARO,
    FROTA_TEXTO_ESCURO,
    INPUTS_BG,
    SIDEBAR_BG,
    TEXTO,
    TEXTO_INPUTS,
)
from core.forca_style import forca_style  # noqa: E402
from pages.Devolucoes import (  # noqa: E402
    pag_dev_caixas_server,
    pag_dev_caixas_ui,
    pag_dev_detalhes_server,
    pag_dev_detalhes_ui,
    pag_dev_devolucoes_server,
    pag_dev_devolucoes_ui,
    pag_dev_graficos_server,
    pag_dev_graficos_ui,
)
from pages.Frotas import (  # noqa: E402
    pag_frotas_entrada_server,
    pag_frotas_entrada_ui,
    pag_frotas_saida_server,
    pag_frotas_saida_ui,
    pag_frotas_server,
    pag_frotas_ui,
)
from pages.Frotas.Dados.dados_frota import data_ultima_execucao as data_frota  # noqa: E402
from pages.PDE import pag_pde_server, pag_pde_ui  # noqa: E402
from pages.PDE.Dados.dados_pde import PASTA_PARQUET as PASTA_PDE  # noqa: E402

PASTA_APP = Path(__file__).parent

# CSS embutido na página (não por <link>): mesmo desenho do app original.
CSS_ESTILO = (PASTA_APP / "www" / "css" / "style.css").read_text(encoding="utf-8")
CSS_INICIAL = (PASTA_APP / "www" / "css" / "inicial.css").read_text(encoding="utf-8")

# Página -> (pasta, tabelas) do cartão "Atualizado em" (Devoluções monta o próprio).
MAPA_ATUALIZACAO = {"pde": (PASTA_PDE, ("tb_pde",))}

TABS_DEVOLUCOES = {"dev_det", "dev_cx", "dev_dev", "dev_graf"}
TABS_FROTAS = {"fro", "fro_ent", "fro_sai"}
# A consulta dos veículos roda a cada duas semanas: o cartão só fica vermelho depois disso.
DIAS_TOLERANCIA_FROTA = 30

# Botão do menu -> painel que ele abre.
MENU = {
    "link_pag_frota": "fro",
    "link_pag_fro_ent": "fro_ent",
    "link_pag_fro_sai": "fro_sai",
    "link_pag_pde": "pde",
    "link_pag_dev_det": "dev_det",
    "link_pag_dev_cx": "dev_cx",
    "link_pag_dev_dev": "dev_dev",
    "link_pag_dev_graf": "dev_graf",
}


def _menu() -> list:
    return [
        ui.accordion(
            ui.accordion_panel(
                "Frota",
                ui.input_action_button("link_pag_frota", "Geral", icon=icon_svg("car"), class_="selecionado"),
                ui.input_action_button("link_pag_fro_ent", "Entrada de veículos", icon=icon_svg("right-to-bracket")),
                ui.input_action_button("link_pag_fro_sai", "Saída de veículos", icon=icon_svg("right-from-bracket")),
                icon=icon_svg("truck"),
            ),
            open=True,
        ),
        ui.input_action_button("link_pag_pde", "PDE", icon=icon_svg("table")),
        ui.accordion(
            ui.accordion_panel(
                "Devoluções",
                ui.input_action_button("link_pag_dev_det", "Detalhes", icon=icon_svg("file-lines")),
                ui.input_action_button("link_pag_dev_cx", "Caixas", icon=icon_svg("box")),
                ui.input_action_button("link_pag_dev_dev", "Devoluções", icon=icon_svg("money-bill")),
                ui.input_action_button("link_pag_dev_graf", "Gráficos", icon=icon_svg("chart-column")),
                icon=icon_svg("rotate-left"),
            ),
            open=False,
        ),
    ]


app_ui = ui.page_sidebar(
    ui.sidebar(
        _menu(),
        gap="10px",
        padding="50px 0 0 0",
        width="220px",
        open={"desktop": "open", "mobile": "closed"},
    ),
    ui.navset_hidden(
        ui.nav_panel(None, com_carregamento(pag_frotas_ui()), value="fro"),
        ui.nav_panel(None, com_carregamento(pag_frotas_entrada_ui()), value="fro_ent"),
        ui.nav_panel(None, com_carregamento(pag_frotas_saida_ui()), value="fro_sai"),
        ui.nav_panel(None, com_carregamento(pag_pde_ui()), value="pde"),
        ui.nav_panel(None, com_carregamento(pag_dev_detalhes_ui()), value="dev_det"),
        ui.nav_panel(None, com_carregamento(pag_dev_caixas_ui()), value="dev_cx"),
        ui.nav_panel(None, com_carregamento(pag_dev_devolucoes_ui()), value="dev_dev"),
        ui.nav_panel(None, com_carregamento(pag_dev_graficos_ui()), value="dev_graf"),
        id="conteudo_tabs",
        selected="fro",
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
            --frota-fundo-claro: {FROTA_FUNDO_CLARO};
            --frota-texto-escuro: {FROTA_TEXTO_ESCURO};
            --frota-cabecalho-bg: {FROTA_CABECALHO_BG};
            --frota-cabecalho-texto: {FROTA_CABECALHO_TEXTO};
        }}
    """),
    ui.tags.style(CSS_ESTILO),
    ui.busy_indicators.options(spinner_color=DESTAQUE),
    ui.tags.script(src=forca_style("js/echarts.min.js")),
    ui.tags.script(src=forca_style("js/sidebar.js")),
    ui.tags.script(src=forca_style("js/frota.js")),
    ui.tags.script(src=forca_style("js/pde.js")),
    ui.tags.script(src=forca_style("js/devolucoes.js")),
    ui.tags.script(src=forca_style("js/tabela_resize.js")),
    ui.tags.script(src=forca_style("js/custom.js")),
    title=ui.div(
        ui.div(
            ui.tags.img(src="img/marca.svg", alt=""),
            ui.tags.b(f"{NOME_APP} - {NOME_PORTFOLIO}"),
            class_="cabecalho-marca",
        ),
        ui.output_ui("valuebox_atualizacao"),
        class_="cabecalho-app",
    ),
    # Flatly já compilado: o Shinylive não tem o libsass que o tema usaria na hora.
    theme=PASTA_APP / "www" / "css" / "flatly.min.css",
    window_title=NOME_APP,
)


def server(input, output, session):
    resumo_cabecalho_dev = reactive.value(None, name="resumo_cabecalho_dev")
    pag_frotas_server()
    pag_frotas_entrada_server()
    pag_frotas_saida_server()
    pag_pde_server()
    pag_dev_detalhes_server(resumo_cabecalho_dev)
    pag_dev_caixas_server(resumo_cabecalho_dev)
    pag_dev_devolucoes_server(resumo_cabecalho_dev)
    pag_dev_graficos_server(resumo_cabecalho_dev)

    @render.ui
    def valuebox_atualizacao():
        aba_atual = input.conteudo_tabs() if "conteudo_tabs" in input else None
        if aba_atual in TABS_DEVOLUCOES:
            resumo = resumo_cabecalho_dev()
            if resumo is None:
                return None
            return ui.div(
                *resumo["cards"],
                cartao_atualizacao(resumo["atualizado_em"], DESTAQUE),
                class_="cabecalho-resumo-dev",
            )
        if aba_atual in TABS_FROTAS:
            return cartao_atualizacao(data_frota(), DESTAQUE, DIAS_TOLERANCIA_FROTA)
        alvo = MAPA_ATUALIZACAO.get(aba_atual)
        if alvo is None:
            return None
        pasta, nomes = alvo
        return cartao_atualizacao(obter_atualizacao(pasta, *nomes), DESTAQUE)

    def _ligar_botao(botao: str, painel: str) -> None:
        @reactive.effect
        @reactive.event(input[botao])
        def _():
            ui.update_navset("conteudo_tabs", selected=painel)

    for botao, painel in MENU.items():
        _ligar_botao(botao, painel)


app = App(app_ui, server, static_assets=PASTA_APP / "www")
