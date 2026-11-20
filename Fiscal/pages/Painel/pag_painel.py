from datetime import date

import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.dados import ler
from core.formato import mes_curto, moeda, numero
from core.graficos import MOEDA_BR, grafico
from core.layout import cartao, filtros, kpi, linha_kpis
from pages.Painel.Dados import dados_painel as dados


@module.ui
def painel_ui():
    filiais = sorted(ler("documentos")["destinatario"].unique().to_list())
    return ui.div(
        filtros(
            ui.input_select("mes", "Mês de emissão", {m.isoformat(): mes_curto(m) for m in dados.meses()}),
            ui.input_select("filial", "Filial", {"": "Todas", **{f: f for f in filiais}}),
        ),
        ui.output_ui("kpis"),
        ui.layout_columns(
            cartao("Documentos recebidos por dia", ui.output_ui("grafico_dia")),
            cartao("Valor por tipo", ui.output_ui("grafico_tipo")),
            col_widths=(8, 4),
        ),
    )


@module.server
def painel_server(input, output, session):
    @reactive.calc
    def base() -> pl.DataFrame:
        return dados.do_mes(date.fromisoformat(input.mes()), input.filial() or None)

    @render.ui
    def kpis():
        df = base()
        conta = dict(df.group_by("tipo").len().iter_rows())
        filial = input.filial() or None
        pendentes = dados.pendentes_escrituracao(filial)
        return linha_kpis(
            kpi(
                "NF-e recebidas",
                numero(conta.get("NF-e", 0)),
                moeda(df.filter(pl.col("tipo") == "NF-e")["valor"].sum(), 0),
                cores.TIPOS["NF-e"],
            ),
            kpi("CT-e recebidos", numero(conta.get("CT-e", 0)), "frete das compras", cores.TIPOS["CT-e"]),
            kpi("NFS-e recebidas", numero(conta.get("NFS-e", 0)), "serviços tomados", cores.TIPOS["NFS-e"]),
            kpi("A manifestar", numero(dados.a_manifestar(filial)), "NF-e sem confirmação da operação", cores.ALERTA),
            kpi("Sem escrituração", numero(pendentes.height), moeda(pendentes["valor"].sum(), 0), cores.NEGATIVO),
        )

    @render.ui
    def grafico_dia():
        d = dados.por_dia(base())
        tipos = [t for t in cores.TIPOS if t in d.columns]
        return grafico(
            {
                "tooltip": {"trigger": "axis"},
                "legend": {"top": 0},
                "grid": {"left": 40, "right": 20, "top": 40, "bottom": 30},
                "xAxis": {"type": "category", "data": [x.strftime("%d/%m") for x in d["recebida_em"]]},
                "yAxis": {"type": "value", "minInterval": 1},
                "series": [
                    {
                        "name": t,
                        "type": "bar",
                        "stack": "d",
                        "data": d[t].to_list(),
                        "itemStyle": {"color": cores.TIPOS[t]},
                    }
                    for t in tipos
                ],
            }
        )

    @render.ui
    def grafico_tipo():
        v = base().group_by("tipo").agg(pl.col("valor").sum())
        return grafico(
            {
                "tooltip": {"trigger": "item", "valueFormatter": MOEDA_BR},
                "legend": {"bottom": 0},
                "series": [
                    {
                        "type": "pie",
                        "radius": ["40%", "65%"],
                        "center": ["50%", "45%"],
                        "itemStyle": {"borderColor": "#fff", "borderWidth": 2},
                        "label": {
                            "formatter": "js:function (p) { return p.percent.toLocaleString('pt-BR', "
                            "{maximumFractionDigits: 1}) + '%'; }"
                        },
                        "data": [
                            {"name": t, "value": round(x, 2), "itemStyle": {"color": cores.TIPOS[t]}}
                            for t, x in v.iter_rows()
                        ],
                    }
                ],
            }
        )
