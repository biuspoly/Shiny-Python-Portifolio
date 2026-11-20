import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.formato import numero, pct
from core.graficos import grafico
from core.layout import cartao, filtros, kpi, linha_kpis
from pages.Farol.Dados import dados_farol as dados


@module.ui
def farol_ui():
    return ui.div(
        filtros(
            ui.input_select(
                "dias",
                "Período",
                {"15": "Últimos 15 dias", "30": "Últimos 30 dias", "45": "Últimos 45 dias"},
                selected="30",
            )
        ),
        ui.output_ui("kpis"),
        cartao(
            "Farol de fechamento de caixa",
            ui.output_ui("mapa_calor"),
            ui.div(
                "Cada quadrado é um dia de movimento da filial, pintado pelo atraso entre o dia e o "
                "fechamento do caixa dele.",
                class_="legenda",
            ),
        ),
        cartao("Resumo por filial", ui.output_data_frame("tabela")),
    )


@module.server
def farol_server(input, output, session):
    @reactive.calc
    def base() -> pl.DataFrame:
        return dados.fechamentos(int(input.dias()))

    @render.ui
    def kpis():
        df = base()
        aberto = df.filter(pl.col("atraso") < 0)
        n_filiais = aberto["filial"].n_unique()
        return linha_kpis(
            kpi(
                "Fechados no dia",
                pct((df["atraso"] == 0).mean()),
                f"{numero(df.height)} dias de movimento",
                cores.POSITIVO,
            ),
            kpi(
                "Atraso médio",
                f"{numero(df.filter(pl.col('atraso') >= 0)['atraso'].mean() or 0, 1)} dias",
                "entre o movimento e o fechamento",
            ),
            kpi(
                "Caixas em aberto",
                numero(aberto.height),
                f"em {numero(n_filiais)} {'filial' if n_filiais == 1 else 'filiais'}",
                cores.NEGATIVO if aberto.height else None,
            ),
        )

    @render.ui
    def mapa_calor():
        df = base()
        filiais = sorted(df["filial"].unique().to_list())
        datas = sorted(df["data"].unique().to_list())
        pos_data = {d: i for i, d in enumerate(datas)}
        pos_filial = {f: i for i, f in enumerate(filiais)}
        return grafico(
            {
                "tooltip": {
                    "formatter": "js:function (p) { var a = p.data[3]; return p.data[4] + '<br>' + p.name + ': ' + "
                    "(a < 0 ? 'em aberto' : a === 0 ? 'fechado no dia' : 'fechado com ' + a + "
                    "(a === 1 ? ' dia' : ' dias') + ' de atraso'); }"
                },
                "grid": {"left": 150, "right": 20, "top": 10, "bottom": 70},
                "xAxis": {
                    "type": "category",
                    "data": [d.strftime("%d/%m") for d in datas],
                    "splitArea": {"show": True},
                },
                "yAxis": {"type": "category", "data": filiais, "splitArea": {"show": True}},
                "visualMap": {
                    "type": "piecewise",
                    "dimension": 2,
                    "orient": "horizontal",
                    "left": "center",
                    "bottom": 0,
                    "pieces": [
                        {"value": i, "label": rotulo, "color": cor} for i, (_, rotulo, cor) in enumerate(dados.FAIXAS)
                    ],
                },
                "series": [
                    {
                        "type": "heatmap",
                        "data": [
                            [pos_data[r["data"]], pos_filial[r["filial"]], r["faixa"], r["atraso"], r["filial"]]
                            for r in df.iter_rows(named=True)
                        ],
                        "itemStyle": {"borderColor": "#fff", "borderWidth": 2, "borderRadius": 3},
                    }
                ],
            },
            altura="34vh",
        )

    @render.data_frame
    def tabela():
        r = dados.resumo(base())
        return render.DataGrid(
            pl.DataFrame(
                {
                    "Filial": r["filial"],
                    "Fechados no dia": [pct(v) for v in r["no_dia"]],
                    "Atraso médio (dias)": [numero(v or 0, 1) for v in r["atraso_medio"]],
                    "Dias em aberto": r["em_aberto"].cast(pl.String),
                    "Aberto desde": [d.strftime("%d/%m/%Y") if d else "-" for d in r["aberto_desde"]],
                }
            ),
            width="100%",
            height="auto",
            summary=False,
        )
