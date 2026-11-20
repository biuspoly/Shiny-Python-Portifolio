import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.dados import ler
from core.formato import mes_curto, moeda, numero, pct
from core.graficos import grafico
from core.layout import cartao, filtros, kpi, linha_kpis
from pages.Escrituracao.Dados import dados_escrituracao as dados


@module.ui
def escrituracao_ui():
    filiais = sorted(ler("documentos")["destinatario"].unique().to_list())
    return ui.div(
        filtros(
            ui.input_select("filial", "Filial", {"": "Todas", **{f: f for f in filiais}}),
            ui.input_selectize(
                "tipo", "Tipo", ["NF-e", "CT-e", "NFS-e"], multiple=True, options={"placeholder": "Todos"}
            ),
        ),
        ui.output_ui("kpis"),
        ui.layout_columns(
            cartao("Escrituração por filial e mês", ui.output_ui("grafico_filial")),
            cartao("Pendências por motivo", ui.output_ui("grafico_motivo")),
            col_widths=(7, 5),
        ),
        cartao("Documentos sem escrituração", ui.output_data_frame("pendentes")),
    )


@module.server
def escrituracao_server(input, output, session):
    base = dados.documentos()

    @reactive.calc
    def filtrada() -> pl.DataFrame:
        df = base
        if input.filial():
            df = df.filter(pl.col("destinatario") == input.filial())
        if input.tipo():
            df = df.filter(pl.col("tipo").is_in(list(input.tipo())))
        return df

    @render.ui
    def kpis():
        df = filtrada()
        pend = df.filter(~pl.col("escriturada"))
        return linha_kpis(
            kpi(
                "Escriturados",
                pct(df["escriturada"].mean()),
                f"{numero(df['escriturada'].sum())} documentos",
                cores.POSITIVO,
            ),
            kpi("Pendentes", numero(pend.height), moeda(pend["valor"].sum(), 0), cores.NEGATIVO),
            kpi(
                "Mais antigo pendente",
                f"{numero(pend['dias_parada'].max() or 0)} dias",
                "desde o recebimento",
                cores.ALERTA,
            ),
            kpi(
                "Tempo médio para escriturar",
                f"{numero(df['dias_para_escriturar'].mean() or 0, 1)} dias",
                "do recebimento ao lançamento",
            ),
        )

    @render.ui
    def grafico_filial():
        d = dados.por_filial_mes(filtrada())
        meses = sorted(d["mes"].unique().to_list())
        filiais = sorted(d["destinatario"].unique().to_list())
        return grafico(
            {
                "tooltip": {
                    "trigger": "axis",
                    "valueFormatter": "js:function (v) { return v == null ? '-' : v.toLocaleString('pt-BR') + '%'; }",
                },
                "legend": {"top": 0},
                "grid": {"left": 45, "right": 20, "top": 40, "bottom": 30},
                "xAxis": {"type": "category", "data": [mes_curto(m) for m in meses]},
                "yAxis": {"type": "value", "max": 100, "axisLabel": {"formatter": "{value}%"}},
                "series": [
                    {
                        "name": f.replace("Atlântida ", ""),
                        "type": "line",
                        "smooth": True,
                        "itemStyle": {"color": cores.SERIES[i % len(cores.SERIES)]},
                        "data": [
                            round(v * 100, 1) if v is not None else None
                            for v in d.filter(pl.col("destinatario") == f).join(
                                pl.DataFrame({"mes": meses}), on="mes", how="right"
                            )["percentual"]
                        ],
                    }
                    for i, f in enumerate(filiais)
                ],
            }
        )

    @render.ui
    def grafico_motivo():
        m = filtrada().filter(~pl.col("escriturada")).group_by("pendencia").len().sort("len", descending=True)
        return grafico(
            {
                "tooltip": {"trigger": "axis"},
                "grid": {"left": 200, "right": 40, "top": 10, "bottom": 25},
                "xAxis": {"type": "value", "minInterval": 1},
                "yAxis": {"type": "category", "data": m["pendencia"].to_list(), "inverse": True},
                "series": [
                    {
                        "type": "bar",
                        "name": "Documentos",
                        "data": m["len"].to_list(),
                        "label": {"show": True, "position": "right"},
                        "itemStyle": {"color": cores.SERIES[1], "borderRadius": [0, 4, 4, 0]},
                    }
                ],
            }
        )

    @render.data_frame
    def pendentes():
        p = filtrada().filter(~pl.col("escriturada")).sort("dias_parada", descending=True)
        idx = p.with_row_index()
        atrasados = idx.filter(pl.col("dias_parada") > 7)["index"].to_list()
        return render.DataGrid(
            pl.DataFrame(
                {
                    "Tipo": p["tipo"],
                    "Número": p["numero"].cast(pl.String),
                    "Emitente": p["emitente"],
                    "Destinatário": p["destinatario"],
                    "Recebida em": [d.strftime("%d/%m/%Y") for d in p["recebida_em"]],
                    "Dias parada": p["dias_parada"].cast(pl.String),
                    "Valor": [moeda(v) for v in p["valor"]],
                    "Pendência": p["pendencia"],
                }
            ),
            styles=[{"rows": atrasados, "cols": [5], "style": {"color": cores.NEGATIVO, "font-weight": "700"}}]
            if atrasados
            else [],
            width="100%",
            height="40vh",
            summary="Mostrando {start} a {end} de {total} documentos",
        )
