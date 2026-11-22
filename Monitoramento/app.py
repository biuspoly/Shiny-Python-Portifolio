import asyncio
import sys
from pathlib import Path

import polars as pl
from faicons import icon_svg
from loguru import logger
from shiny import App, reactive, ui

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:  # no Shinylive a saída é a do navegador, sem reconfigure
    pass

from core.config import FONTES_LOG, TITULO_APP  # noqa: E402
from core.cores import DESTAQUE, INPUTS_BG, SIDEBAR_BG, TEXTO, TEXTO_ESCURO, TEXTO_INPUTS  # noqa: E402
from core.forca_style import forca_style  # noqa: E402
from core.leitura_logs import atualizar, ler_erros  # noqa: E402
from pages.pag_desempenho import pag_desempenho_server, pag_desempenho_ui  # noqa: E402
from pages.pag_erros import pag_erros_server, pag_erros_ui  # noqa: E402
from pages.pag_pipelines import pag_pipelines_server, pag_pipelines_ui  # noqa: E402
from pages.pag_usuarios import pag_usuarios_server, pag_usuarios_ui  # noqa: E402
from pages.pag_visao_geral import pag_visao_geral_server, pag_visao_geral_ui  # noqa: E402

INTERVALO_VIGIA_ERROS_S = 20

PASTA_APP = Path(__file__).parent

# CSS embutido na página (não por <link>): mesmo desenho do app original.
CSS_ESTILO = (PASTA_APP / "www" / "css" / "style.css").read_text(encoding="utf-8")
CSS_INICIAL = (PASTA_APP / "www" / "css" / "inicial.css").read_text(encoding="utf-8")

PAGINAS = [
    ("vgeral", "bt_visao_geral", "Visão Geral", "gauge"),
    ("usuarios", "bt_usuarios", "Usuários", "users"),
    ("erros", "bt_erros", "Erros", "triangle-exclamation"),
    ("desempenho", "bt_desempenho", "Desempenho", "stopwatch"),
    ("pipelines", "bt_pipelines", "Pipelines", "gears"),
]

app_ui = ui.page_sidebar(
    ui.sidebar(
        *[
            ui.input_action_button(
                id_botao, rotulo, icon=icon_svg(icone), class_="selecionado" if valor == "vgeral" else None
            )
            for valor, id_botao, rotulo, icone in PAGINAS
        ],
        gap="10px",
        padding="50px 0 0 0",
        width="200px",
        open={"desktop": "open", "mobile": "closed"},
    ),
    ui.navset_hidden(
        ui.nav_panel(None, pag_visao_geral_ui("vgeral"), value="vgeral"),
        ui.nav_panel(None, pag_usuarios_ui("usuarios"), value="usuarios"),
        ui.nav_panel(None, pag_erros_ui("erros"), value="erros"),
        ui.nav_panel(None, pag_desempenho_ui("desempenho"), value="desempenho"),
        ui.nav_panel(None, pag_pipelines_ui("pipelines"), value="pipelines"),
        id="conteudo_tabs",
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
            --mon-texto-escuro: {TEXTO_ESCURO};
        }}
    """),
    ui.tags.style(CSS_ESTILO),
    ui.tags.script(src=forca_style("js/echarts.min.js")),
    ui.tags.script(src=forca_style("js/custom.js")),
    ui.tags.script(src=forca_style("js/tabela_resize.js")),
    title=ui.div(ui.tags.img(src="img/marca.svg", alt=""), ui.tags.b(TITULO_APP), class_="cabecalho-marca"),
    # Flatly já compilado: o Shinylive não tem o libsass que o tema usaria na hora.
    theme=PASTA_APP / "www" / "css" / "flatly.min.css",
    window_title=TITULO_APP,
)


def server(input, output, session):
    pag_visao_geral_server("vgeral")
    pag_usuarios_server("usuarios")
    pag_erros_server("erros")
    pag_desempenho_server("desempenho")
    pag_pipelines_server("pipelines")

    # Erro novo em algum app: aviso flutuante (www/js/custom.js), com qualquer tela aberta.
    _erros_vistos: dict[str, object] = {"marca": None}

    @reactive.effect
    async def _vigiar_erros():
        reactive.invalidate_later(INTERVALO_VIGIA_ERROS_S)
        try:
            await asyncio.to_thread(atualizar, FONTES_LOG)
            base = await asyncio.to_thread(ler_erros)
        except Exception as exc:
            logger.warning(f"Vigia de erros: nao deu pra ler os logs -- {exc}")
            return
        if base.is_empty():
            return
        recente = base.row(0, named=True)
        marca = (recente.get("timestamp"), recente.get("app"), recente.get("mensagem"))
        anterior = _erros_vistos["marca"]
        _erros_vistos["marca"] = marca
        if anterior is None or marca == anterior:
            return
        novos = base.filter(pl.col("timestamp") > (anterior[0] or "")).height or 1
        await session.send_custom_message(
            "avisoErroNovo",
            {
                "app": recente.get("app") or "?",
                "onde": (recente.get("onde") or "").strip(),
                "mensagem": (recente.get("mensagem") or "").strip()[:180],
                "quantos": novos,
            },
        )

    for valor, id_botao, _, _ in PAGINAS:

        def _troca(valor=valor, id_botao=id_botao):
            @reactive.effect
            @reactive.event(input[id_botao])
            def _():
                ui.update_navset("conteudo_tabs", selected=valor)

        _troca()


app = App(app_ui, server, static_assets=PASTA_APP / "www")
