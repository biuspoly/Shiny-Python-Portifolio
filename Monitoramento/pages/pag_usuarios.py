import pandas as pd
import polars as pl
from faicons import icon_svg
from shiny import module, reactive, render, ui

from core.compat import para_pandas
from core.config import APPS_MONITORADOS, FONTES_LOG
from core.cores import DESTAQUE
from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.leitura_logs import atualizar, ler_sessoes
from core.status import consultar_todos
from core.visibilidade import pagina_visivel

INTERVALO_ATUALIZACAO_S = 15

COLUNAS_AGORA = {
    "app": "App",
    "usuario": "Usuário",
    "revenda": "Revenda",
    "pagina": "Página",
    "conectado_ha": "Conectado há",
    "sessao": "Sessão",
}
ORDEM_AGORA = list(COLUNAS_AGORA)
_LARGURA_AGORA = {
    "app": 120,
    "usuario": 180,
    "revenda": 180,
    "pagina": 200,
    "conectado_ha": 130,
    "sessao": 140,
}

COLUNAS_HOJE = {
    "timestamp": "Quando",
    "app": "App",
    "evento": "Evento",
    "usuario": "Usuário",
    "revenda": "Revenda",
    "sessao": "Sessão",
}
ORDEM_HOJE = ["app", "timestamp", "evento", "sessao", "revenda", "usuario"]
_LARGURA_HOJE = {"app": 110, "timestamp": 180, "evento": 100, "sessao": 130, "revenda": 160, "usuario": 160}


def _duracao(segundos: int) -> str:
    horas, resto = divmod(int(segundos), 3600)
    minutos, segs = divmod(resto, 60)
    if horas:
        return f"{horas}h {minutos:02d}min"
    if minutos:
        return f"{minutos}min"
    return f"{segs}s"


@module.ui
def pag_usuarios_ui():
    return ui.div(
        ui.output_ui("cards"),
        ui.card(
            ui.card_header("Conectados agora"),
            ui.output_ui("css_largura_agora"),
            ui.div(ui.output_data_frame("tabela_agora"), id="grupo-tabela-agora", class_="tabela-resize"),
            class_="my-4",
        ),
        ui.card(
            ui.card_header("Movimento de hoje (entradas e saídas)"),
            ui.output_ui("css_largura_hoje"),
            ui.div(ui.output_data_frame("tabela_hoje"), id="grupo-tabela-hoje", class_="tabela-resize"),
        ),
        class_="pagina-monitoramento",
    )


@module.server
def pag_usuarios_server(input, output, session, valor_navset: str = "usuarios"):
    @reactive.calc
    async def conectados() -> pd.DataFrame:
        reactive.invalidate_later(INTERVALO_ATUALIZACAO_S)
        if not pagina_visivel(session, valor_navset):
            return pd.DataFrame()
        linhas = [
            {
                "app": saude["nome"],
                "usuario": sessao.get("usuario") or "(não identificado)",
                "revenda": sessao.get("revenda") or "-",
                "pagina": sessao.get("pagina") or "-",
                "conectado_ha": _duracao(sessao.get("conectado_ha_s") or 0),
                "sessao": sessao.get("id") or "",
            }
            for saude in await consultar_todos(APPS_MONITORADOS)
            for sessao in saude["sessoes"]
        ]
        base = pd.DataFrame(linhas, columns=ORDEM_AGORA)
        if base.empty:
            return base
        return base.sort_values(["usuario", "revenda", "app", "pagina"], kind="stable").reset_index(drop=True)

    @render.ui
    async def cards():
        base = await conectados()
        pessoas = base["usuario"].nunique() if not base.empty else 0
        revendas = base.loc[base["revenda"] != "-", "revenda"].nunique() if not base.empty else 0
        if base.empty:
            multi = 0
        else:
            por_pessoa = base.groupby(["usuario", "revenda"])["pagina"].nunique()
            multi = int((por_pessoa > 1).sum())
        return ui.layout_columns(
            ui.value_box(
                "Sessões abertas",
                str(len(base)),
                showcase=icon_svg("users"),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#FFF"),
            ),
            ui.value_box(
                "Usuários diferentes",
                str(pessoas),
                showcase=icon_svg("user-check"),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#FFF"),
            ),
            ui.value_box(
                "Revendas diferentes",
                str(revendas),
                showcase=icon_svg("store"),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#FFF"),
            ),
            ui.value_box(
                "Em duas ou mais páginas",
                str(multi),
                showcase=icon_svg("clone"),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#FFF"),
            ),
        )

    @render.data_frame
    async def tabela_agora():
        base = await conectados()
        if base.empty:
            return render.DataTable(
                pd.DataFrame({"Aviso": ["Ninguém conectado neste momento"]}),
                summary=False,
                filters=False,
                selection_mode="none",
            )
        return render.DataTable(
            base.rename(columns=COLUNAS_AGORA),
            height="34vh",
            summary=False,
            filters=False,
            selection_mode="none",
        )

    @render.ui
    def css_largura_agora():
        larguras = [ColunaLargura(c, _LARGURA_AGORA[c]) for c in ORDEM_AGORA]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_agora')}", larguras))

    @reactive.calc
    def movimento() -> pl.DataFrame:
        reactive.invalidate_later(INTERVALO_ATUALIZACAO_S)
        if not pagina_visivel(session, valor_navset):
            return pl.DataFrame()
        atualizar(FONTES_LOG)
        return ler_sessoes()

    @render.data_frame
    def tabela_hoje():
        base = movimento()
        if base.height == 0:
            return render.DataTable(
                pd.DataFrame({"Aviso": ["Nenhuma entrada ou saída registrada hoje"]}),
                summary=False,
                filters=False,
                selection_mode="none",
            )
        pandas_df = base.select(ORDEM_HOJE).rename(COLUNAS_HOJE).pipe(para_pandas)
        return render.DataTable(
            pandas_df,
            height="34vh",
            summary=False,
            filters=False,
            selection_mode="none",
        )

    @render.ui
    def css_largura_hoje():
        larguras = [ColunaLargura(c, _LARGURA_HOJE[c]) for c in ORDEM_HOJE]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_hoje')}", larguras))
