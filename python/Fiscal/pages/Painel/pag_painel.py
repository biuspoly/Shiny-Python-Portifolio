"""Painel: o que chegou no mês e o que está pendente (de manifestar e de escriturar)."""

from __future__ import annotations

import pandas as pd
import polars as pl
from pyecharts import options as opts
from pyecharts.charts import Bar
from shiny import module, reactive, render, ui

from core import notas as n
from core.carregamento import com_carregamento
from core.cores import ALERTA, CORES_ETAPA
from core.numeros import moeda, numero, percentual
from core.pyecharts_shiny import renderizar
from core.tela import OPCOES_SELECTIZE, cartao, css_tabela, legenda

DIAS_ALERTA = 5  # pendência com mais de 5 dias fica em vermelho
_ETAPAS = ["Escriturada", "Manifestada", "Recebida", "Recusada"]


def pag_painel_ui():
    return com_carregamento(painel_ui("painel"))


def pag_painel_server():
    painel_server("painel")


@module.ui
def painel_ui():
    return ui.div(
        ui.card(
            ui.div(
                ui.div(
                    ui.input_selectize("mes", "Mês de emissão", choices={}, options=OPCOES_SELECTIZE),
                    class_="filtro-dv",
                ),
                class_="filtros-dv",
            )
        ),
        ui.output_ui("cartoes"),
        ui.layout_columns(
            ui.card(ui.card_header("NF-e recebidas por dia, pela etapa"), ui.output_ui("grafico")),
            ui.card(
                ui.card_header("Pendências por fornecedor (todos os meses)"),
                ui.div(ui.output_data_frame("pendencias"), class_="dv-tabela"),
                ui.tags.style(css_tabela("#painel-pendencias", [230, 70, 110, 80], chave=(2,), esquerda=(1,))),
                legenda(ui.span(class_="dv-legenda-alerta"), f"pendência mais antiga que {DIAS_ALERTA} dias"),
            ),
            col_widths=(7, 5),
        ),
        class_="dv-modulo",
    )


@module.server
def painel_server(input, output, session):
    @reactive.effect
    def _opcoes():
        meses = n.meses()
        ui.update_selectize("mes", choices=meses, selected=next(iter(meses)))

    @reactive.calc
    def notas_mes() -> pl.DataFrame:
        return n.nfe().filter(pl.col("MES") == input.mes()) if input.mes() else n.nfe().head(0)

    @render.ui
    def cartoes():
        df = notas_mes()
        if df.height == 0:
            return None
        ctes = n.cte().filter(pl.col("MES") == input.mes())
        conta = {e: df.filter(pl.col("ETAPA") == e) for e in _ETAPAS}
        pendentes = pl.concat([conta["Recebida"], conta["Manifestada"]])
        mais_antiga = max((n.dias_parado(d) for d in pendentes["EMISSAO"]), default=0)
        return ui.div(
            cartao("NF-e recebidas", numero(df.height), moeda(df["V_NF"].sum(), 0)),
            cartao(
                "A manifestar",
                numero(conta["Recebida"].height),
                "só com ciência ou sem manifestação",
                "kpi-delta-neg" if conta["Recebida"].height else "kpi-delta-neutro",
            ),
            cartao(
                "A escriturar",
                numero(pendentes.height),
                f"a mais antiga há {mais_antiga} dias" if pendentes.height else "nada pendente",
                "kpi-delta-neg" if mais_antiga > DIAS_ALERTA else "kpi-delta-neutro",
                destaque=True,
            ),
            cartao(
                "Escrituradas",
                numero(conta["Escriturada"].height),
                f"{percentual(conta['Escriturada'].height / df.height)} das recebidas",
                "kpi-delta-pos",
            ),
            cartao("CT-e recebidos", numero(ctes.height), f"frete de {moeda(ctes['V_PREST'].sum(), 0)}"),
            cartao(
                "Recusadas",
                numero(conta["Recusada"].height),
                "desconhecimento ou operação não realizada",
                "kpi-delta-neg" if conta["Recusada"].height else "kpi-delta-neutro",
            ),
            class_="dv-kpis",
        )

    @render.ui
    def grafico():
        df = notas_mes()
        if df.height == 0:
            return None
        por_dia = df.with_columns(pl.col("EMISSAO").dt.strftime("%d").alias("DIA")).group_by("DIA", "ETAPA").len()
        dias = sorted(por_dia["DIA"].unique().to_list())
        barras = Bar(init_opts=opts.InitOpts(bg_color="transparent")).add_xaxis(dias)
        for etapa in _ETAPAS:
            valores = dict(por_dia.filter(pl.col("ETAPA") == etapa).select("DIA", "len").iter_rows())
            barras.add_yaxis(
                etapa,
                [valores.get(d, 0) for d in dias],
                stack="etapa",
                itemstyle_opts=opts.ItemStyleOpts(color=CORES_ETAPA[etapa]),
                label_opts=opts.LabelOpts(is_show=False),
            )
        barras.set_global_opts(
            legend_opts=opts.LegendOpts(pos_top="0"),
            tooltip_opts=opts.TooltipOpts(trigger="axis"),
            yaxis_opts=opts.AxisOpts(name="notas", splitline_opts=opts.SplitLineOpts(is_show=True)),
            xaxis_opts=opts.AxisOpts(name="dia"),
        )
        return ui.HTML(renderizar(barras, altura="330px"))

    @render.data_frame
    def pendencias():
        df = n.nfe().filter(pl.col("ETAPA").is_in(["Recebida", "Manifestada"]))
        if df.height == 0:
            return render.DataTable(pd.DataFrame({"": ["Nada pendente."]}))
        agrupado = (
            df.group_by("EMIT_NOME")
            .agg(
                pl.len().alias("QTD"), pl.col("V_NF").sum().alias("VALOR"), pl.col("EMISSAO").min().alias("MAIS_ANTIGA")
            )
            .sort("MAIS_ANTIGA")
        )
        linhas, estilos = [], []
        for i, p in enumerate(agrupado.iter_rows(named=True)):
            dias = n.dias_parado(p["MAIS_ANTIGA"])
            linhas.append(
                {
                    "Fornecedor": p["EMIT_NOME"],
                    "Notas": numero(p["QTD"]),
                    "Valor": numero(p["VALOR"], 2),
                    "Mais antiga": n.texto_dias(dias),
                }
            )
            if dias > DIAS_ALERTA:
                estilos.append({"rows": [i], "cols": ["Mais antiga"], "style": ALERTA})
        return render.DataTable(pd.DataFrame(linhas), styles=estilos, height="330px", summary=False, filters=False)
