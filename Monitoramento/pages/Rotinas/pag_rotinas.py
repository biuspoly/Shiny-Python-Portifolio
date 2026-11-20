from datetime import timedelta

import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.formato import numero, pct
from core.graficos import grafico
from core.layout import cartao, filtros, kpi, linha_kpis
from pages.Rotinas.Dados import dados_rotinas as dados

_STATUS = list(cores.STATUS)


@module.ui
def rotinas_ui():
    return ui.div(
        filtros(
            ui.input_select(
                "dias",
                "Período",
                {"14": "Últimas 14 noites", "30": "Últimas 30 noites", "45": "Últimas 45 noites"},
                selected="30",
            )
        ),
        ui.output_ui("kpis"),
        cartao(
            "Rotinas da madrugada",
            ui.output_ui("mapa"),
            ui.div(
                "Às 3h os dados de cada app são refeitos, uma rotina depois da outra. Cada quadrado é uma "
                "noite de uma rotina.",
                class_="legenda",
            ),
        ),
        cartao("Resumo por rotina", ui.output_data_frame("tabela")),
    )


@module.server
def rotinas_server(input, output, session):
    @reactive.calc
    def base() -> pl.DataFrame:
        return dados.rodadas(int(input.dias()))

    @render.ui
    def kpis():
        df = base()
        ultima_noite = df.filter(pl.col("noite") == df["noite"].max())
        falhas = ultima_noite.filter(pl.col("status") != "Sucesso")
        fim = ultima_noite.sort("inicio").row(-1, named=True)
        return linha_kpis(
            kpi(
                "Execuções com sucesso",
                pct((df["status"] == "Sucesso").mean()),
                f"{numero(df.height)} execuções",
                cores.POSITIVO,
            ),
            kpi(
                "Última noite",
                "Sem falha" if falhas.is_empty() else f"{falhas.height} com falha",
                ", ".join(falhas["rotina"].to_list()) or "todas as rotinas rodaram",
                cores.POSITIVO if falhas.is_empty() else cores.NEGATIVO,
            ),
            kpi(
                "Terminou às",
                (fim["inicio"] + timedelta(minutes=fim["minutos"])).strftime("%H:%M"),
                "a última rotina da noite",
            ),
            kpi(
                "Tempo total médio",
                f"{numero(df.group_by('noite').agg(pl.col('minutos').sum())['minutos'].mean(), 1)} min",
                "por noite",
            ),
        )

    @render.ui
    def mapa():
        df = base()
        noites = sorted(df["noite"].unique().to_list())
        rotinas = df.select("rotina").unique(maintain_order=True)["rotina"].to_list()
        return grafico(
            {
                "tooltip": {
                    "formatter": "js:function (p) { return p.data[3] + '<br>' + p.name + ': ' + p.data[4]"
                    " + ' (' + p.data[5].toLocaleString('pt-BR') + ' min)'; }"
                },
                "grid": {"left": 190, "right": 20, "top": 10, "bottom": 60},
                "xAxis": {"type": "category", "data": [n.strftime("%d/%m") for n in noites]},
                "yAxis": {"type": "category", "data": rotinas, "inverse": True},
                "visualMap": {
                    "type": "piecewise",
                    "dimension": 2,
                    "orient": "horizontal",
                    "left": "center",
                    "bottom": 0,
                    "pieces": [{"value": i, "label": s, "color": cores.STATUS[s]} for i, s in enumerate(_STATUS)],
                },
                "series": [
                    {
                        "type": "heatmap",
                        "itemStyle": {"borderColor": "#fff", "borderWidth": 2, "borderRadius": 3},
                        "data": [
                            [
                                noites.index(r["noite"]),
                                rotinas.index(r["rotina"]),
                                _STATUS.index(r["status"]),
                                r["rotina"],
                                r["status"],
                                r["minutos"],
                            ]
                            for r in df.iter_rows(named=True)
                        ],
                    }
                ],
            },
            altura="40vh",
        )

    @render.data_frame
    def tabela():
        r = dados.resumo(base())
        idx = r.with_row_index()
        estilos = [
            {"rows": linhas, "cols": [6], "style": {"color": cor, "font-weight": "700"}}
            for s, cor in cores.STATUS.items()
            if (linhas := idx.filter(pl.col("ultimo_status") == s)["index"].to_list())
        ]
        return render.DataGrid(
            pl.DataFrame(
                {
                    "Rotina": r["rotina"],
                    "App": r["app"],
                    "Sucesso": [pct(v) for v in r["sucesso"]],
                    "Duração média": [f"{numero(v, 1)} min" for v in r["duracao_media"]],
                    "Mais demorada": [f"{numero(v, 1)} min" for v in r["duracao_max"]],
                    "Última duração": [f"{numero(v, 1)} min" for v in r["ultima_duracao"]],
                    "Último status": r["ultimo_status"],
                    "Linhas gravadas": [numero(v) for v in r["ultimas_linhas"]],
                }
            ),
            styles=estilos,
            width="100%",
            height="auto",
            summary=False,
        )
