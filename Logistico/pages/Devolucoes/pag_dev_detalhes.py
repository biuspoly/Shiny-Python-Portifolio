import asyncio
import io
from datetime import date, datetime
from urllib.parse import parse_qs

import pandas as pd
import polars as pl
from faicons import icon_svg
from pyecharts import options as opts
from pyecharts.charts import Line
from shiny import module, reactive, render, ui

from core.atualizacao import obter_atualizacao
from core.cabecalho_dev import valuebox_cabecalho
from core.compat import para_pandas
from core.cores import DESTAQUE, DEV_RETORNO_NEGATIVO, DEV_RETORNO_POSITIVO
from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.pyecharts_shiny import renderizar
from core.tabela_paginada import TabelaPaginada
from core.visibilidade import pagina_visivel

from .Dados import dados_devolucao as d
from .Dados import tabela_devolucao as ti

FILTROS_TEXTO = [
    ("revenda", "Revenda", "GRUPO_REV"),
    ("cidade", "Cidade", "CIDADE_UF"),
    ("cod_ped", "Cod Pedido", "COD_PED"),
    ("cod_ven", "Cod Vendedores", "COD_VENDEDOR"),
    ("cod_mot", "Cod Motoristas", "COD_MOTORISTA"),
    ("cod_cli", "Cod Clientes", "COD_CLIENTE"),
    ("retorno", "Devolução", "Retorno"),
    ("motivo", "Motivo", "VDCADDEV_DESCR"),
]
FILTROS_DIA = [
    ("data_pedido", "Data do pedido", "DATA_VENDA"),
    ("data_romaneio", "Data do romaneio", "DATA_BAIXA_ROM"),
    ("data_entrega", "Data de entrega", "DTA_ENTREGA"),
]
FILTROS_DATA_FIM = [
    ("ult_compra", "Últ compra", "ULT_COMPRA"),
]
FILTROS_DATA = FILTROS_DIA + FILTROS_DATA_FIM
FILTROS_TODOS = FILTROS_TEXTO + FILTROS_DATA

_LARGURA_TABELA = {
    "Data do pedido": 100,
    "Revenda": 100,
    "Vendas": 100,
    "Devolução": 100,
    "Num de pedidos": 110,
    "Pedidos devolvidos": 120,
    "Taxa de retorno": 110,
    "Data de devolução": 100,
    "Cod Pedido": 100,
    "Vendedor": 160,
    "Motorista": 160,
    "Cliente": 180,
    "Cidade - Cli": 130,
    "Últ compra": 100,
    "Nfe": 90,
    "Motivo": 160,
    "Devolução (Ped)": 110,
    "Comodato": 90,
    "Taxa de retorno (Ped)": 130,
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


def _tabela_consolidada(base: pl.DataFrame) -> pl.DataFrame:
    return (
        base.group_by(["DATA_VENDA", "Empresa", "GRUPO_REV"])
        .agg(
            pl.col("VALOR VENDA").sum().alias("Vendas"),
            pl.col("VALOR DEVOLUCAO").sum().alias("Devolução"),
            pl.col("COD_PED").n_unique().alias("Num de pedidos"),
            pl.col("COD_PED").filter(pl.col("VALOR DEVOLUCAO") > 0).n_unique().alias("Pedidos devolvidos"),
        )
        .with_columns(
            pl.when(pl.col("Vendas") == 0)
            .then(pl.lit(0.0))
            .otherwise(pl.col("Devolução") / pl.col("Vendas") * 100)
            .alias("Taxa de retorno")
        )
        .rename({"DATA_VENDA": "Data do pedido", "GRUPO_REV": "Revenda"})
        .drop("Empresa")
        .sort("Data do pedido", descending=True)
    )


def _tabela_consolidada_agrupada(base: pl.DataFrame, expandidas: frozenset[str]) -> pl.DataFrame:
    detalhe = _tabela_consolidada(base)
    if detalhe.height == 0:
        return detalhe.with_columns(pl.lit(True).alias("_grupo"))

    colunas = detalhe.columns
    grupo = (
        detalhe.group_by("Data do pedido", maintain_order=True)
        .agg(
            pl.col("Revenda").n_unique().alias("_n_revendas"),
            pl.col("Vendas").sum(),
            pl.col("Devolução").sum(),
            pl.col("Num de pedidos").sum(),
            pl.col("Pedidos devolvidos").sum(),
        )
        .with_columns(
            pl.when(pl.col("Vendas") == 0)
            .then(pl.lit(0.0))
            .otherwise(pl.col("Devolução") / pl.col("Vendas") * 100)
            .alias("Taxa de retorno"),
            (pl.lit("Total de revendas: ") + pl.col("_n_revendas").cast(pl.Utf8)).alias("Revenda"),
        )
        .select(colunas)
        .sort("Data do pedido", descending=True)
    )
    detalhe = detalhe.with_columns(pl.lit(False).alias("_grupo"))

    partes = []
    for data in grupo["Data do pedido"]:
        expandido = data in expandidas
        rotulo_data = f"{'▾' if expandido else '▸'} {_rotulo_data(data)}"
        partes.append(
            grupo.filter(pl.col("Data do pedido") == data).with_columns(
                pl.lit(rotulo_data).alias("Data do pedido"),
                pl.lit(True).alias("_grupo"),
                pl.lit(data).alias("_data_bruta"),
            )
        )
        if expandido:
            partes.append(
                detalhe.filter(pl.col("Data do pedido") == data)
                .with_columns(pl.lit("").alias("Data do pedido"), pl.lit(data).alias("_data_bruta"))
                .sort("Devolução", descending=True)
            )
    return pl.concat(partes, how="vertical")


def _tabela_detalhada(base: pl.DataFrame) -> pl.DataFrame:
    base = base.with_columns(
        pl.concat_str([pl.col("COD_VEN"), pl.lit(" - "), d.so_primeira_maiuscula("NOME_VEN")]).alias("Vendedor"),
        pl.concat_str([pl.col("MOT"), pl.lit(" - "), d.so_primeira_maiuscula("NOME_MOT")]).alias("Motorista"),
        pl.concat_str([pl.col("CLI").cast(pl.Utf8), pl.lit(" - "), d.so_primeira_maiuscula("FANTASIA")]).alias(
            "Cliente"
        ),
        d.so_primeira_maiuscula("CIDADE").alias("Cidade - Cli"),
    )
    tabela = (
        base.group_by(
            [
                "DATA_DEV",
                "DATA_VENDA",
                "GRUPO_REV",
                "CHAVE_VDI",
                "COD_PED",
                "Vendedor",
                "Motorista",
                "Cliente",
                "Cidade - Cli",
                "ULT_COMPRA",
                "NF_VENDA",
                "VDCADDEV_DESCR",
                "taxa_media_dev",
                "vdi_dev",
                "Comodato cliente",
            ]
        )
        .agg(pl.col("VALOR DEVOLUCAO").sum().alias("Devolução"))
        .rename(
            {
                "DATA_DEV": "Data de devolução",
                "DATA_VENDA": "Data do pedido",
                "GRUPO_REV": "Revenda",
                "COD_PED": "Cod Pedido",
                "VDCADDEV_DESCR": "Motivo",
                "vdi_dev": "Devolução (Ped)",
                "Comodato cliente": "Comodato",
                "ULT_COMPRA": "Últ compra",
                "NF_VENDA": "Nfe",
            }
        )
    )
    tabela = tabela.with_columns(
        (pl.col("taxa_media_dev").round(4).cast(pl.Utf8) + pl.lit("%")).alias("Taxa de retorno (Ped)")
    ).drop("taxa_media_dev")
    return tabela.sort("Data do pedido", descending=True)


@module.ui
def dev_detalhes_ui():
    return ui.div(
        ui.card(
            ui.div(
                _filtro_ui("mes", "Mês", choices=d.listar_meses_disponiveis(), selected=["Mês Atual"]),
                *[_filtro_ui(id_filtro, rotulo, choices={}) for id_filtro, rotulo, _coluna in FILTROS_DIA],
                *[_filtro_ui(id_filtro, rotulo) for id_filtro, rotulo, _coluna in FILTROS_TEXTO],
                *[_filtro_ui(id_filtro, rotulo, choices={}) for id_filtro, rotulo, _coluna in FILTROS_DATA_FIM],
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
        ui.card(
            ui.card_header(
                ui.div(
                    ui.output_text("titulo_tabela", inline=True),
                    ui.div(ui.input_switch("detalhado", None, value=False), class_="dev-switch-detalhado"),
                    ui.download_button(
                        "exportar",
                        None,
                        icon=icon_svg("download", a11y="deco"),
                        class_="btn-exportar-dev ms-auto",
                        title="Baixar tabela em Excel",
                    ),
                    class_="d-flex align-items-center gap-4 w-100",
                )
            ),
            ui.output_ui("corpo_tabela"),
        ),
        ui.card(
            ui.card_header("Devolução diária"),
            ui.output_ui("grafico_diario"),
        ),
        class_="dev-modulo dev-modulo-detalhes",
    )


@module.server
def dev_detalhes_server(input, output, session, resumo_cabecalho):
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
        for id_filtro, _rotulo, coluna in FILTROS_TODOS:
            valores = input[id_filtro]()
            if valores:
                base = base.filter(pl.col(coluna).cast(pl.Utf8).is_in(list(valores)))
        return base

    @reactive.effect
    async def _atualiza_opcoes_filtro():
        if not pagina_visivel(session, "dev_det"):
            return
        base = await dev_geral()
        for id_filtro, _rotulo, coluna in FILTROS_TEXTO:
            if not input[id_filtro]():
                opcoes = sorted(v for v in base[coluna].unique().to_list() if v is not None) if base.height else []
                ui.update_selectize(id_filtro, choices=[str(v) for v in opcoes], session=session, server=True)
        for id_filtro, _rotulo, coluna in FILTROS_DATA:
            if not input[id_filtro]():
                valores = sorted(v for v in base[coluna].unique().to_list() if v is not None) if base.height else []
                ui.update_selectize(
                    id_filtro,
                    choices={v: _rotulo_data(v) for v in valores},
                    session=session,
                    server=True,
                )

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar_filtros():
        ui.update_selectize("mes", selected=["Mês Atual"], session=session)
        for id_filtro, _rotulo, _coluna in FILTROS_TODOS:
            ui.update_selectize(id_filtro, selected=[], session=session)

    @render.text
    def titulo_tabela():
        return "Dados detalhados" if input.detalhado() else "Dados consolidados"

    @reactive.effect
    async def _publica_cabecalho():
        if not pagina_visivel(session, "dev_det"):
            return
        base = await base_filtrada()
        if base.height == 0:
            resumo_cabecalho.set(None)
            return
        vendas = base["VALOR VENDA"].sum() or 0
        devolucoes = base["VALOR DEVOLUCAO"].sum() or 0
        retorno = (devolucoes / vendas) if vendas else None
        cor = DEV_RETORNO_POSITIVO if retorno is None or retorno <= 0.02 else DEV_RETORNO_NEGATIVO
        texto = "-" if retorno is None else f"{retorno * 100:.2f}%".replace(".", ",")
        momento = obter_atualizacao(
            d.PASTA_PARQUET, *[f"tb_vend_dev_{cnpj}_atual" for cnpj in d.cnpjs_da_revenda(revenda_atual())]
        )
        resumo_cabecalho.set(
            {
                "cards": [valuebox_cabecalho("Tx retorno (Fin)", texto, cor)],
                "atualizado_em": momento,
            }
        )

    datas_expandidas = reactive.value(frozenset[str](), name="datas_expandidas")

    @reactive.calc
    async def tabela_ativa() -> pl.DataFrame:
        base = await base_filtrada()
        if base.height == 0:
            return base
        if input.detalhado():
            return await asyncio.to_thread(_tabela_detalhada, base)
        return await asyncio.to_thread(_tabela_consolidada_agrupada, base, datas_expandidas())

    paginador_tabela = TabelaPaginada("pag_tabela", input, session)

    @reactive.calc
    async def pagina_bruta() -> pl.DataFrame:
        ativa = await tabela_ativa()
        if ativa.height == 0:
            return ativa
        inicio, fim = paginador_tabela.janela(ativa.height)
        return ativa.slice(inicio, fim - inicio)

    @reactive.calc
    async def tabela_pronta() -> tuple[pd.DataFrame, list[dict]]:
        fatia = await pagina_bruta()
        if fatia.height == 0:
            return pd.DataFrame(), []
        if input.detalhado():
            df = await asyncio.to_thread(ti.construir_detalhada_df, fatia)
            return df, []
        return await asyncio.to_thread(ti.construir_consolidada_df, fatia)

    @render.ui
    async def corpo_tabela():
        total = (await tabela_ativa()).height
        if total == 0:
            return ui.p("Sem dados para os filtros selecionados.")
        return ui.div(
            ui.output_ui("css_largura_tabela"),
            ui.output_data_frame("tabela"),
            ui.output_ui("controles_tabela"),
            class_="dev-tabela dev-tabela-detalhes tabela-resize",
        )

    @render.ui
    async def css_largura_tabela():
        pandas_df, _estilos = await tabela_pronta()
        larguras = [ColunaLargura(c, _LARGURA_TABELA.get(c, 100)) for c in pandas_df.columns]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela')}", larguras))

    @render.data_frame
    async def tabela():
        pandas_df, estilos = await tabela_pronta()
        return render.DataTable(
            pandas_df,
            styles=estilos,
            height="50vh",
            summary=False,
            filters=False,
            selection_mode="none",
        )

    @reactive.effect
    @reactive.event(input.clique_grupo_data)
    def _alterna_grupo_data():
        data_bruta = input.clique_grupo_data()
        atual = set(datas_expandidas())
        if data_bruta in atual:
            atual.discard(data_bruta)
        else:
            atual.add(data_bruta)
        datas_expandidas.set(frozenset(atual))

    @render.ui
    async def controles_tabela():
        total = (await tabela_ativa()).height
        return paginador_tabela.controles(total)

    @reactive.effect
    async def _reinicia_pagina_tabela():
        if not pagina_visivel(session, "dev_det"):
            return
        await tabela_ativa()
        input.detalhado()
        paginador_tabela.reiniciar()

    @render.ui
    async def grafico_diario():
        base = await base_filtrada()
        if base.height == 0:
            return ui.HTML(renderizar(Line()))
        diario = (
            base.group_by("DATA_VENDA")
            .agg(pl.col("VALOR DEVOLUCAO").sum().alias("Devolução"))
            .with_columns(pl.col("DATA_VENDA").str.to_date("%Y%m%d", strict=False).alias("Data"))
            .sort("Data")
        )
        categorias = [data.strftime("%d/%m/%Y") for data in diario["Data"].to_list()]
        valores = [round(v, 2) for v in diario["Devolução"].to_list()]
        chart = (
            Line()
            .add_xaxis(categorias)
            .add_yaxis(
                "Devolução",
                valores,
                symbol="circle",
                symbol_size=6,
                label_opts=opts.LabelOpts(is_show=False),
                linestyle_opts=opts.LineStyleOpts(color=DESTAQUE),
                itemstyle_opts=opts.ItemStyleOpts(color=DESTAQUE),
            )
            .set_global_opts(
                tooltip_opts=opts.TooltipOpts(trigger="axis"),
                legend_opts=opts.LegendOpts(is_show=False),
                xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)),
            )
        )
        return ui.HTML(renderizar(chart))

    @render.download_button(filename=lambda: f"devolucao-{date.today().isoformat()}.xlsx")
    async def exportar():
        ativa = await tabela_ativa()
        buffer = io.BytesIO()
        await asyncio.to_thread(para_pandas(ativa).to_excel, buffer, index=False, engine="openpyxl")
        yield buffer.getvalue()


def pag_dev_detalhes_ui():
    return dev_detalhes_ui("dev_detalhes")


def pag_dev_detalhes_server(resumo_cabecalho):
    dev_detalhes_server("dev_detalhes", resumo_cabecalho=resumo_cabecalho)
