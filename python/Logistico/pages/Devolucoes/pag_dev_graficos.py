import asyncio
from datetime import datetime
from urllib.parse import parse_qs

import polars as pl
from faicons import icon_svg
from pyecharts import options as opts
from pyecharts.charts import Bar
from pyecharts.commons.utils import JsCode
from shiny import module, reactive, render, ui

from core.atualizacao import obter_atualizacao
from core.cores import DESTAQUE
from core.pyecharts_shiny import renderizar
from core.visibilidade import pagina_visivel

from .Dados import dados_devolucao as d

FILTROS = [
    ("data_pedido", "Data do pedido", "DATA_VENDA"),
    ("data_romaneio", "Data do romaneio", "DATA_BAIXA_ROM"),
    ("data_entrega", "Data de entrega", "DTA_ENTREGA"),
    ("revenda", "Revenda", "GRUPO_REV"),
    ("cod_cli", "Cod Clientes", "COD_CLIENTE"),
]


def _rotulo_data(valor: str) -> str:
    return datetime.strptime(valor, "%Y%m%d").strftime("%d/%m/%Y")


def _filtro_ui(id_filtro: str, rotulo: str, choices=None, selected=None) -> ui.Tag:
    return ui.div(
        ui.input_selectize(
            id_filtro,
            rotulo,
            choices=choices if choices is not None else [],
            selected=selected,
            multiple=True,
            options={
                "placeholder": "Todos",
                "dropdownParent": "body",
                "dropdownClass": "selectize-dropdown dev-selectize-dropdown",
                "hideSelected": False,
                "plugins": ["remove_button"],
            },
        ),
        class_="filtro-dev",
    )


def _ranking(base: pl.DataFrame, coluna: str, top: int | None) -> pl.DataFrame:
    tabela = (
        base.filter(pl.col(coluna).is_not_null())
        .group_by(coluna)
        .agg(pl.col("VALOR DEVOLUCAO").sum().alias("Devolucao"))
        .filter(pl.col("Devolucao") > 0)
        .sort("Devolucao", descending=True)
    )
    if top:
        tabela = tabela.head(top)
    total = tabela["Devolucao"].sum() or 0
    return tabela.with_columns((pl.col("Devolucao") / total if total else pl.lit(0.0)).alias("Percentual"))


def _formatar_rotulo(devolucao: float, percentual: float) -> str:
    texto = "R$ {:,.2f} ({:.1f}%)".format(devolucao, percentual * 100)
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


ALTURA_PADRAO_GRAFICO_PX = 400

LARGURA_ROTULO_EIXO_PX = 170


def _grafico_ranking(tabela: pl.DataFrame, coluna: str) -> str:
    if tabela.height == 0:
        return renderizar(Bar())
    linhas = sorted(tabela.iter_rows(named=True), key=lambda linha: linha["Devolucao"])
    categorias = [str(linha[coluna]).strip() for linha in linhas]
    dados_serie = [
        {
            "value": round(linha["Devolucao"], 2),
            "rotulo": _formatar_rotulo(linha["Devolucao"], linha["Percentual"]),
        }
        for linha in linhas
    ]
    chart = (
        Bar()
        .add_xaxis(categorias)
        .add_yaxis(
            "Devolução",
            dados_serie,
            label_opts=opts.LabelOpts(
                is_show=True,
                position="right",
                formatter=JsCode("function (parametros) { return parametros.data.rotulo; }"),
            ),
            itemstyle_opts=opts.ItemStyleOpts(color=DESTAQUE),
        )
        .reversal_axis()
        .set_global_opts(
            tooltip_opts=opts.TooltipOpts(trigger="axis"),
            legend_opts=opts.LegendOpts(is_show=False),
            yaxis_opts=opts.AxisOpts(
                axislabel_opts=opts.LabelOpts(
                    interval=0,
                    text_width=LARGURA_ROTULO_EIXO_PX,
                    overflow="truncate",
                ),
            ),
        )
    )
    chart.options["grid"] = {"left": 8, "right": 150, "top": 20, "bottom": 30, "containLabel": True}
    altura_conteudo = max(ALTURA_PADRAO_GRAFICO_PX, 34 * len(categorias) + 60)
    grafico_html = renderizar(chart, altura=f"{altura_conteudo}px")
    return f'<div style="height: {ALTURA_PADRAO_GRAFICO_PX}px; overflow-y: auto;">{grafico_html}</div>'


@module.ui
def dev_graficos_ui():
    return ui.div(
        ui.card(
            ui.div(
                _filtro_ui("mes", "Mês", choices=d.listar_meses_disponiveis(), selected=["Mês Atual"]),
                _filtro_ui("data_pedido", "Data do pedido", choices={}),
                _filtro_ui("data_romaneio", "Data do romaneio", choices={}),
                _filtro_ui("data_entrega", "Data de entrega", choices={}),
                _filtro_ui("revenda", "Revenda", choices=[]),
                _filtro_ui("cod_cli", "Cod Clientes", choices=[]),
                ui.input_action_button(
                    "limpar",
                    None,
                    icon=icon_svg("eraser", a11y="deco"),
                    class_="btn-primary btn-limpar-dev",
                    title="Limpar filtros",
                ),
                class_="filtros-dev",
            ),
        ),
        ui.layout_columns(
            ui.card(
                ui.card_header("Top 10 ranking de devolução - Produto"),
                ui.output_ui("graf_rankprod"),
            ),
            ui.card(
                ui.card_header("Top 10 ranking de devolução - Cliente"),
                ui.output_ui("graf_rankcli"),
            ),
        ),
        ui.layout_columns(
            ui.card(ui.card_header("Ranking de devolução - Motorista"), ui.output_ui("graf_rankmot")),
            ui.card(ui.card_header("Ranking de devolução - Vendedor"), ui.output_ui("graf_rankven")),
            ui.card(ui.card_header("Top 10 ranking de devolução - Motivo"), ui.output_ui("graf_rankmotivo")),
        ),
        class_="dev-modulo",
    )


@module.server
def dev_graficos_server(input, output, session, resumo_cabecalho):
    @reactive.calc
    def revenda_atual() -> str | None:
        query_string = session.clientdata.url_search()
        valores = parse_qs(query_string.lstrip("?")).get("REVENDA")
        return valores[0] if valores else None

    @reactive.calc
    async def dev_geral() -> pl.DataFrame:
        meses = input.mes()
        if not meses:
            return pl.DataFrame()
        return await asyncio.to_thread(d.carregar_geral_dev, revenda_atual(), list(meses))

    @reactive.calc
    async def base_filtrada() -> pl.DataFrame:
        base = await dev_geral()
        if base.height == 0:
            return base
        for id_filtro, _rotulo, coluna in FILTROS:
            valores = input[id_filtro]()
            if valores:
                base = base.filter(pl.col(coluna).is_in(list(valores)))
        return base

    @reactive.effect
    async def _atualiza_opcoes_filtro():
        if not pagina_visivel(session, "dev_graf"):
            return
        base = await dev_geral()
        if not input.data_pedido():
            valores = sorted(v for v in base["DATA_VENDA"].unique().to_list() if v is not None) if base.height else []
            ui.update_selectize("data_pedido", choices={v: _rotulo_data(v) for v in valores}, session=session)
        if not input.data_romaneio():
            valores = (
                sorted(v for v in base["DATA_BAIXA_ROM"].unique().to_list() if v is not None) if base.height else []
            )
            ui.update_selectize("data_romaneio", choices={v: _rotulo_data(v) for v in valores}, session=session)
        if not input.data_entrega():
            valores = sorted(v for v in base["DTA_ENTREGA"].unique().to_list() if v is not None) if base.height else []
            ui.update_selectize("data_entrega", choices={v: _rotulo_data(v) for v in valores}, session=session)
        if not input.revenda():
            opcoes = sorted(v for v in base["GRUPO_REV"].unique().to_list() if v is not None) if base.height else []
            ui.update_selectize("revenda", choices=opcoes, session=session)
        if not input.cod_cli():
            opcoes = sorted(v for v in base["COD_CLIENTE"].unique().to_list() if v is not None) if base.height else []
            ui.update_selectize("cod_cli", choices=opcoes, session=session)

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar_filtros():
        ui.update_selectize("data_pedido", selected=[], session=session)
        ui.update_selectize("data_romaneio", selected=[], session=session)
        ui.update_selectize("data_entrega", selected=[], session=session)
        ui.update_selectize("revenda", selected=[], session=session)
        ui.update_selectize("cod_cli", selected=[], session=session)
        ui.update_selectize("mes", selected=["Mês Atual"], session=session)

    @reactive.effect
    def _publica_cabecalho():
        if not pagina_visivel(session, "dev_graf"):
            return
        momento = obter_atualizacao(
            d.PASTA_PARQUET, *[f"tb_vend_dev_{cnpj}_atual" for cnpj in d.cnpjs_da_revenda(revenda_atual())]
        )
        resumo_cabecalho.set({"cards": [], "atualizado_em": momento})

    def _montar_ranking(base: pl.DataFrame, coluna: str, top: int | None) -> str:
        return _grafico_ranking(_ranking(base, coluna, top), coluna)

    async def _ranking_ui(coluna: str, top: int | None):
        base = await base_filtrada()
        if coluna not in base.columns:
            return ui.p("Sem dados para os filtros selecionados.")
        html = await asyncio.to_thread(_montar_ranking, base, coluna, top)
        return ui.HTML(html)

    @render.ui
    async def graf_rankprod():
        return await _ranking_ui("PRODUTO_GENERICO", 10)

    @render.ui
    async def graf_rankcli():
        return await _ranking_ui("COD_CLIENTE", 10)

    @render.ui
    async def graf_rankmot():
        return await _ranking_ui("COD_MOTORISTA", None)

    @render.ui
    async def graf_rankven():
        return await _ranking_ui("COD_VENDEDOR", None)

    @render.ui
    async def graf_rankmotivo():
        return await _ranking_ui("VDCADDEV_DESCR", 10)


def pag_dev_graficos_ui():
    return dev_graficos_ui("dev_graficos")


def pag_dev_graficos_server(resumo_cabecalho):
    dev_graficos_server("dev_graficos", resumo_cabecalho=resumo_cabecalho)
