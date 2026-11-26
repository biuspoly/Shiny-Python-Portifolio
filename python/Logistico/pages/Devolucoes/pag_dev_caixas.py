import asyncio
from datetime import datetime
from urllib.parse import parse_qs

import polars as pl
from faicons import icon_svg
from pyecharts import options as opts
from pyecharts.charts import Bar
from shiny import module, reactive, render, ui

from core.atualizacao import obter_atualizacao
from core.cabecalho_dev import valuebox_cabecalho
from core.cores import DESTAQUE
from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.pyecharts_shiny import renderizar
from core.visibilidade import pagina_visivel

from .Dados import dados_devolucao as d
from .Dados import tabela_devolucao as ti

COLUNA_VENDA = "QTD"
COLUNA_DEV = "DEVOLUCAO_CX"
ROTULO_VENDA = "Qtd Cx"
ROTULO_DEV = "Qtd Cx Dv"

FILTROS = [
    ("data_pedido", "Data do pedido", "DATA_VENDA"),
    ("data_romaneio", "Data do romaneio", "DATA_BAIXA_ROM"),
    ("data_entrega", "Data de entrega", "DTA_ENTREGA"),
    ("revenda", "Revenda", "GRUPO_REV"),
]

_LARGURA_TABELA = {
    "Cod": 80,
    "Produto": 200,
    "Nome": 160,
    "Fantasia": 180,
    "Qtd Cx": 90,
    "Qtd Cx Dv": 100,
    "Num de pedidos": 110,
    "Taxa de retorno": 110,
}


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


def _formatar_numero(valor: float) -> str:
    inteiro = f"{valor:,.0f}"
    return inteiro.replace(",", "_").replace(".", ",").replace("_", ".")


@module.ui
def dev_caixas_ui():
    return ui.div(
        ui.card(
            ui.div(
                _filtro_ui("mes", "Mês", choices=d.listar_meses_disponiveis(), selected=["Mês Atual"]),
                _filtro_ui("data_pedido", "Data do pedido", choices={}),
                _filtro_ui("data_romaneio", "Data do romaneio", choices={}),
                _filtro_ui("data_entrega", "Data de entrega", choices={}),
                _filtro_ui("revenda", "Revenda", choices=[]),
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
            ui.card(ui.card_header("Devolução mensal"), ui.output_ui("grafico_mensal")),
            ui.card(ui.card_header("Produto"), ui.output_ui("corpo_tabela_produto")),
        ),
        ui.layout_columns(
            ui.card(ui.card_header("Motorista"), ui.output_ui("corpo_tabela_motorista")),
            ui.card(ui.card_header("Vendedor"), ui.output_ui("corpo_tabela_vendedor")),
            ui.card(ui.card_header("Cliente"), ui.output_ui("corpo_tabela_cliente")),
        ),
        class_="dev-modulo",
    )


@module.server
def dev_caixas_server(input, output, session, resumo_cabecalho):
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

    @reactive.calc
    async def mensal_filtrada() -> pl.DataFrame:
        mensal = await asyncio.to_thread(d.geral_cx_mensal, revenda_atual())
        if mensal.height == 0:
            return mensal
        valores = input.revenda()
        if valores:
            mensal = mensal.filter(pl.col("GRUPO_REV").is_in(list(valores)))
        return mensal

    @reactive.effect
    async def _atualiza_opcoes_filtro():
        if not pagina_visivel(session, "dev_cx"):
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

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar_filtros():
        ui.update_selectize("data_pedido", selected=[], session=session)
        ui.update_selectize("data_romaneio", selected=[], session=session)
        ui.update_selectize("data_entrega", selected=[], session=session)
        ui.update_selectize("revenda", selected=[], session=session)
        ui.update_selectize("mes", selected=["Mês Atual"], session=session)

    @reactive.effect
    async def _publica_cabecalho():
        if not pagina_visivel(session, "dev_cx"):
            return
        base = await base_filtrada()
        if base.height == 0:
            resumo_cabecalho.set(None)
            return
        vendas = base[COLUNA_VENDA].sum() or 0
        devolucoes = base[COLUNA_DEV].sum() or 0
        retorno = (devolucoes / vendas) if vendas else None
        texto_retorno = "-" if retorno is None else f"{retorno * 100:.2f}%".replace(".", ",")
        momento = obter_atualizacao(
            d.PASTA_PARQUET, *[f"tb_vend_dev_{cnpj}_atual" for cnpj in d.cnpjs_da_revenda(revenda_atual())]
        )
        resumo_cabecalho.set(
            {
                "cards": [
                    valuebox_cabecalho(ROTULO_VENDA, _formatar_numero(vendas)),
                    valuebox_cabecalho(ROTULO_DEV, _formatar_numero(devolucoes)),
                    valuebox_cabecalho("Tx retorno (Fin)", texto_retorno, None),
                ],
                "atualizado_em": momento,
            }
        )

    @render.ui
    async def grafico_mensal():
        mensal = await mensal_filtrada()
        if mensal.height == 0:
            return ui.HTML(renderizar(Bar()))
        dados = (
            mensal.group_by("MES")
            .agg(pl.col("Devolução").sum())
            .with_columns(pl.col("MES").str.to_date("%Y%m", strict=False).alias("Mês"))
            .sort("Mês")
        )
        categorias = [data.strftime("%m/%Y") for data in dados["Mês"].to_list()]
        valores = [round(v, 2) for v in dados["Devolução"].to_list()]
        chart = (
            Bar()
            .add_xaxis(categorias)
            .add_yaxis(
                "Devolução",
                valores,
                label_opts=opts.LabelOpts(is_show=False),
                itemstyle_opts=opts.ItemStyleOpts(color=DESTAQUE),
            )
            .set_global_opts(
                tooltip_opts=opts.TooltipOpts(trigger="axis"),
                legend_opts=opts.LegendOpts(is_show=False),
            )
        )
        return ui.HTML(renderizar(chart))

    @reactive.calc
    async def tabela_produto_pronta():
        base = await base_filtrada()
        base = base.with_columns(pl.col("CODR").cast(pl.Int64))
        tabela = await asyncio.to_thread(
            ti.tabela_grupo,
            base,
            "CODR",
            "PRODUTO",
            "Produto",
            COLUNA_VENDA,
            COLUNA_DEV,
            ROTULO_VENDA,
            ROTULO_DEV,
            True,
        )
        return await asyncio.to_thread(ti.construir_grupo_df, tabela, [])

    @render.ui
    async def corpo_tabela_produto():
        base = await base_filtrada()
        if base.height == 0:
            return ui.p("Sem dados para os filtros selecionados.")
        return ui.div(
            ui.output_ui("css_largura_tabela_produto"),
            ui.output_data_frame("tabela_produto"),
            class_="dev-tabela tabela-resize",
        )

    @render.data_frame
    async def tabela_produto():
        pandas_df = await tabela_produto_pronta()
        return render.DataTable(pandas_df, height="320px", summary=False, filters=False, selection_mode="none")

    @render.ui
    async def css_largura_tabela_produto():
        pandas_df = await tabela_produto_pronta()
        larguras = [ColunaLargura(c, _LARGURA_TABELA.get(c, 100)) for c in pandas_df.columns]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_produto')}", larguras))

    @reactive.calc
    async def tabela_motorista_pronta():
        base = await base_filtrada()
        tabela = await asyncio.to_thread(
            ti.tabela_grupo,
            base,
            "MOT",
            "NOME_MOT",
            "Nome",
            COLUNA_VENDA,
            COLUNA_DEV,
            ROTULO_VENDA,
            ROTULO_DEV,
            True,
        )
        return await asyncio.to_thread(ti.construir_grupo_df, tabela, [])

    @render.ui
    async def corpo_tabela_motorista():
        base = await base_filtrada()
        if base.height == 0:
            return ui.p("Sem dados para os filtros selecionados.")
        return ui.div(
            ui.output_ui("css_largura_tabela_motorista"),
            ui.output_data_frame("tabela_motorista"),
            class_="dev-tabela tabela-resize",
        )

    @render.data_frame
    async def tabela_motorista():
        pandas_df = await tabela_motorista_pronta()
        return render.DataTable(pandas_df, height="320px", summary=False, filters=False, selection_mode="none")

    @render.ui
    async def css_largura_tabela_motorista():
        pandas_df = await tabela_motorista_pronta()
        larguras = [ColunaLargura(c, _LARGURA_TABELA.get(c, 100)) for c in pandas_df.columns]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_motorista')}", larguras))

    @reactive.calc
    async def tabela_vendedor_pronta():
        base = await base_filtrada()
        tabela = await asyncio.to_thread(
            ti.tabela_grupo,
            base,
            "COD_VEN",
            "NOME_VEN",
            "Nome",
            COLUNA_VENDA,
            COLUNA_DEV,
            ROTULO_VENDA,
            ROTULO_DEV,
            True,
        )
        return await asyncio.to_thread(ti.construir_grupo_df, tabela, [])

    @render.ui
    async def corpo_tabela_vendedor():
        base = await base_filtrada()
        if base.height == 0:
            return ui.p("Sem dados para os filtros selecionados.")
        return ui.div(
            ui.output_ui("css_largura_tabela_vendedor"),
            ui.output_data_frame("tabela_vendedor"),
            class_="dev-tabela tabela-resize",
        )

    @render.data_frame
    async def tabela_vendedor():
        pandas_df = await tabela_vendedor_pronta()
        return render.DataTable(pandas_df, height="320px", summary=False, filters=False, selection_mode="none")

    @render.ui
    async def css_largura_tabela_vendedor():
        pandas_df = await tabela_vendedor_pronta()
        larguras = [ColunaLargura(c, _LARGURA_TABELA.get(c, 100)) for c in pandas_df.columns]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_vendedor')}", larguras))

    @reactive.calc
    async def tabela_cliente_pronta():
        base = await base_filtrada()
        base = base.with_columns(pl.col("CLI").cast(pl.Utf8))
        tabela = await asyncio.to_thread(
            ti.tabela_grupo,
            base,
            "CLI",
            "FANTASIA",
            "Fantasia",
            COLUNA_VENDA,
            COLUNA_DEV,
            ROTULO_VENDA,
            ROTULO_DEV,
            True,
        )
        return await asyncio.to_thread(ti.construir_grupo_df, tabela, [])

    @render.ui
    async def corpo_tabela_cliente():
        base = await base_filtrada()
        if base.height == 0:
            return ui.p("Sem dados para os filtros selecionados.")
        return ui.div(
            ui.output_ui("css_largura_tabela_cliente"),
            ui.output_data_frame("tabela_cliente"),
            class_="dev-tabela tabela-resize",
        )

    @render.data_frame
    async def tabela_cliente():
        pandas_df = await tabela_cliente_pronta()
        return render.DataTable(pandas_df, height="320px", summary=False, filters=False, selection_mode="none")

    @render.ui
    async def css_largura_tabela_cliente():
        pandas_df = await tabela_cliente_pronta()
        larguras = [ColunaLargura(c, _LARGURA_TABELA.get(c, 100)) for c in pandas_df.columns]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_cliente')}", larguras))


def pag_dev_caixas_ui():
    return dev_caixas_ui("dev_caixas")


def pag_dev_caixas_server(resumo_cabecalho):
    dev_caixas_server("dev_caixas", resumo_cabecalho=resumo_cabecalho)
