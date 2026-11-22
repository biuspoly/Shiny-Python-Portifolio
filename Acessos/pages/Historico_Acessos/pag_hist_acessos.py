import asyncio
import io
from datetime import date

import polars as pl
from faicons import icon_svg
from pyecharts import options as opts
from pyecharts.charts import Line
from shiny import module, reactive, render, ui

from core.compat import para_pandas
from core.cores import DESTAQUE, SIDEBAR_BG
from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.pyecharts_shiny import renderizar
from core.tabela_paginada import TabelaPaginada
from core.visibilidade import pagina_visivel
from pages.Historico_Acessos.Dados.dados_hist_acessos import acesso_dash

INTERVALO_PADRAO_S = 30

_RÓTULOS = {"login": "Login", "dataAcesso": "Acesso", "Painel": "Painel", "Revenda": "Revenda"}

_ORDEM_COLUNAS_TABELA = ["id", "Login", "Acesso", "Painel", "Revenda"]
_LARGURA_POR_COLUNA = {
    "id": 70,
    "Login": 140,
    "Acesso": 170,
    "Painel": 180,
    "Revenda": 160,
}


@module.ui
def pag_hist_acessos_ui() -> ui.Tag:
    return ui.div(
        ui.card(
            ui.div(
                ui.div(
                    ui.input_numeric("intervalo", "Intervalo (s)", value=INTERVALO_PADRAO_S, min=5, step=5),
                    class_="filtro-acessos",
                    style="grid-column: span 2",
                ),
                ui.div(
                    ui.input_selectize(
                        "filtro_painel",
                        "Painel",
                        choices=[],
                        multiple=True,
                        options={
                            "hideSelected": False,
                            "dropdownParent": "body",
                            "dropdownClass": "acessos-selectize-dropdown",
                        },
                    ),
                    class_="filtro-acessos",
                    style="grid-column: span 4",
                ),
                ui.div(
                    ui.input_selectize(
                        "filtro_usuario",
                        "Usuário",
                        choices=[],
                        multiple=True,
                        options={
                            "hideSelected": False,
                            "dropdownParent": "body",
                            "dropdownClass": "acessos-selectize-dropdown",
                        },
                    ),
                    class_="filtro-acessos",
                    style="grid-column: span 4",
                ),
                class_="filtros-acessos",
            ),
            class_="my-4",
        ),
        ui.card(
            ui.card_header("Acessos por hora"),
            ui.output_ui("grafico_hora"),
            class_="my-4",
        ),
        ui.card(
            ui.card_header(
                ui.div(
                    ui.span("Detalhes — últimos 7 dias"),
                    ui.download_button(
                        "exportar",
                        None,
                        icon=icon_svg("download", a11y="deco"),
                        class_="btn-exportar-acessos ms-auto",
                    ),
                    class_="d-flex justify-content-between align-items-center",
                ),
            ),
            ui.div(ui.output_data_frame("tabela"), class_="tabela-resize"),
            ui.output_ui("controles_tabela"),
            ui.output_ui("css_largura_tabela"),
        ),
        class_="acessos-modulo",
    )


@module.server
def pag_hist_acessos_server(input, output, session):
    @reactive.calc
    async def base_geral() -> pl.DataFrame:
        reactive.invalidate_later(max(5, input.intervalo() or INTERVALO_PADRAO_S))
        return await asyncio.to_thread(acesso_dash)

    @reactive.effect
    async def _popula_filtros():
        if not pagina_visivel(session, "histacessos"):
            return
        try:
            df = await base_geral()
        except Exception:
            return
        if not input.filtro_painel():
            ui.update_selectize("filtro_painel", choices=sorted(df["Painel"].unique().to_list()))
        if not input.filtro_usuario():
            ui.update_selectize("filtro_usuario", choices=sorted(df["login"].unique().to_list()))

    @reactive.calc
    async def base_filtrada() -> pl.DataFrame:
        df = await base_geral()
        if input.filtro_painel():
            df = df.filter(pl.col("Painel").is_in(input.filtro_painel()))
        if input.filtro_usuario():
            df = df.filter(pl.col("login").is_in(input.filtro_usuario()))
        return df

    @render.ui
    async def grafico_hora():
        df = await base_filtrada()
        if df.height == 0:
            return ui.p("Sem dados no período.")

        agregado = (
            df.with_columns(pl.col("dataAcesso").dt.truncate("1h").alias("hora"))
            .group_by("hora")
            .agg(pl.len().alias("num_acessos"))
            .sort("hora")
        )
        horas = [h.strftime("%d/%m %H:%M") for h in agregado["hora"].to_list()]
        valores = agregado["num_acessos"].to_list()

        linha = (
            Line()
            .add_xaxis(horas)
            .add_yaxis(
                "Acessos por hora",
                valores,
                color=SIDEBAR_BG,
                areastyle_opts=opts.AreaStyleOpts(opacity=0.4, color=DESTAQUE),
                is_symbol_show=True,
            )
            .set_global_opts(
                xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)),
                tooltip_opts=opts.TooltipOpts(trigger="axis"),
                legend_opts=opts.LegendOpts(is_show=False),
            )
        )
        return ui.HTML(renderizar(linha, altura="280px"))

    paginador = TabelaPaginada("pag_hist_acessos", input, session, tamanho_padrao=100)

    async def _tabela_pronta():
        df = (await base_filtrada()).sort("dataAcesso", descending=True).rename(_RÓTULOS)
        pandas_df = df.with_columns(
            df["Acesso"].dt.strftime("%d/%m/%Y %H:%M:%S"),
        ).pipe(para_pandas)
        return pandas_df

    @render.data_frame
    async def tabela():
        pandas_df = await _tabela_pronta()
        fatia = paginador.fatiar(pandas_df)
        return render.DataTable(fatia, height="55vh", summary=False, filters=False, selection_mode="none")

    @render.ui
    async def controles_tabela():
        return paginador.controles(len(await _tabela_pronta()))

    @render.ui
    async def css_largura_tabela():
        larguras = [ColunaLargura(c, _LARGURA_POR_COLUNA[c]) for c in _ORDEM_COLUNAS_TABELA]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela')}", larguras))

    @render.download_button(filename=lambda: f"log-acessos-{date.today().isoformat()}.xlsx")
    async def exportar():
        buffer = io.BytesIO()
        (await _tabela_pronta()).to_excel(buffer, index=False, engine="openpyxl")
        yield buffer.getvalue()
