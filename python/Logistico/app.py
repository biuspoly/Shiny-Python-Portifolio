import sys
from pathlib import Path

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
    COMODATO_BTN_CANCELAR,
    COMODATO_BTN_CANCELAR_HOVER,
    COMODATO_BTN_CONFIRMAR,
    COMODATO_BTN_CONFIRMAR_HOVER,
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
from pages.Comodatos import (  # noqa: E402
    pag_comodatos_saldo_server,
    pag_comodatos_saldo_ui,
    pag_comodatos_server,
    pag_comodatos_ui,
    pag_solicitacao_server,
    pag_solicitacao_ui,
)
from pages.Comodatos.Dados.dados_comodato import PASTA_PARQUET as PASTA_COMODATO  # noqa: E402
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
MAPA_ATUALIZACAO = {
    "pde": (PASTA_PDE, ("tb_pde",)),
    "comod_solic": (PASTA_COMODATO, ("clientes_inadimplentes_titulos_bruto", "comod_solicitado_bruto")),
    "comod_comod": (PASTA_COMODATO, ("comod_geral_bruto",)),
    "comod_vas": (PASTA_COMODATO, ("saldo_comodatos_geral_bruto", "saldo_livro_bruto")),
}
# Telas que escolhem a revenda no cabeçalho (no original, pelo ?REVENDA= da URL).
TABS_COMODATO = {"comod_solic", "comod_comod", "comod_vas"}
REVENDA_PADRAO_COMODATO = "Natal"

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
    "link_pag_comod_solic": "comod_solic",
    "link_pag_comod_comod": "comod_comod",
    "link_pag_comod_vas": "comod_vas",
}


def _icone(arquivo: str):
    # Mesmo markup do app original: imagem branca de www/img, não faicons.
    return ui.tags.img(src=f"img/{arquivo}", height="18em")


def _menu() -> list:
    return [
        ui.accordion(
            ui.accordion_panel(
                "Frota",
                ui.input_action_button("link_pag_frota", "Geral", icon=_icone("car-geral.png"), class_="selecionado"),
                ui.input_action_button("link_pag_fro_ent", "Entrada de veículos", icon=_icone("car-entrada.png")),
                ui.input_action_button("link_pag_fro_sai", "Saída de veículos", icon=_icone("car-saida.png")),
                icon=_icone("car-light.png"),
            ),
            open=True,
        ),
        ui.input_action_button("link_pag_pde", "PDE", icon=_icone("table-light.png")),
        ui.accordion(
            ui.accordion_panel(
                "Devoluções",
                ui.input_action_button("link_pag_dev_det", "Detalhes", icon=_icone("detalhe_pedido.png")),
                ui.input_action_button("link_pag_dev_cx", "Caixas", icon=_icone("box-light.png")),
                ui.input_action_button("link_pag_dev_dev", "Devoluções", icon=_icone("money-light.png")),
                ui.input_action_button("link_pag_dev_graf", "Gráficos", icon=_icone("graph-light.png")),
                icon=_icone("dev-light.png"),
            ),
            open=False,
        ),
        ui.accordion(
            ui.accordion_panel(
                "Comodatos",
                ui.input_action_button("link_pag_comod_solic", "Solicitação", icon=_icone("solicitacao_light.png")),
                ui.input_action_button("link_pag_comod_comod", "Comodatos", icon=_icone("comodatos_light.png")),
                ui.input_action_button("link_pag_comod_vas", "Vasilhames", icon=_icone("vasilhame-light.png")),
                icon=_icone("comodato.png"),
            ),
            open=False,
        ),
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
        ui.nav_panel(None, com_carregamento(pag_frotas_ui()), value="fro"),
        ui.nav_panel(None, com_carregamento(pag_frotas_entrada_ui()), value="fro_ent"),
        ui.nav_panel(None, com_carregamento(pag_frotas_saida_ui()), value="fro_sai"),
        ui.nav_panel(None, com_carregamento(pag_pde_ui()), value="pde"),
        ui.nav_panel(None, com_carregamento(pag_dev_detalhes_ui()), value="dev_det"),
        ui.nav_panel(None, com_carregamento(pag_dev_caixas_ui()), value="dev_cx"),
        ui.nav_panel(None, com_carregamento(pag_dev_devolucoes_ui()), value="dev_dev"),
        ui.nav_panel(None, com_carregamento(pag_dev_graficos_ui()), value="dev_graf"),
        ui.nav_panel(None, com_carregamento(pag_solicitacao_ui()), value="comod_solic"),
        ui.nav_panel(None, com_carregamento(pag_comodatos_ui()), value="comod_comod"),
        ui.nav_panel(None, com_carregamento(pag_comodatos_saldo_ui()), value="comod_vas"),
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
            --comod-confirmar: {COMODATO_BTN_CONFIRMAR};
            --comod-confirmar-escuro: {COMODATO_BTN_CONFIRMAR_HOVER};
            --comod-cancelar: {COMODATO_BTN_CANCELAR};
            --comod-cancelar-escuro: {COMODATO_BTN_CANCELAR_HOVER};
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
    ui.tags.script(src=forca_style("js/comodatos.js")),
    ui.tags.script(src=forca_style("js/marcar_todos.js")),
    ui.tags.script(src=forca_style("js/custom.js")),
    title=ui.div(
        ui.tags.img(src="img/logo_ficticia.svg", height="40vh"),
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
    versao_cache_comod = reactive.value(0, name="versao_cache_comod")
    pag_solicitacao_server(versao_cache_comod)
    pag_comodatos_server(versao_cache_comod)
    pag_comodatos_saldo_server(versao_cache_comod)

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
        cartao = cartao_atualizacao(obter_atualizacao(pasta, *nomes), DESTAQUE)
        if aba_atual not in TABS_COMODATO:
            return cartao
        with reactive.isolate():
            escolhida = input.revenda_escolhida() if "revenda_escolhida" in input else REVENDA_PADRAO_COMODATO
        revenda = ui.div(
            ui.input_select(
                "revenda_escolhida",
                None,
                {"": "Todas as revendas", **{n.title(): n.title() for n in REVENDAS_CNPJ}},
                selected=escolhida,
            ),
            class_="cabecalho-revenda",
            title="Revenda",
        )
        return ui.div(revenda, cartao, class_="cabecalho-comodato")

    def _ligar_botao(botao: str, painel: str) -> None:
        @reactive.effect
        @reactive.event(input[botao])
        def _():
            ui.update_navset("conteudo_tabs", selected=painel)

    for botao, painel in MENU.items():
        _ligar_botao(botao, painel)


# Os anexos do Comodato ficam em uploads/, servidos por URL como no original.
app = App(app_ui, server, static_assets={"/": PASTA_APP / "www", "/uploads": PASTA_APP / "uploads"})
