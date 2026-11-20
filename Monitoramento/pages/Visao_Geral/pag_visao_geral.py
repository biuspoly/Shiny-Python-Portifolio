from datetime import timedelta

import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.dados import data_base, ler
from core.formato import numero
from core.graficos import grafico
from core.layout import cartao, filtros, kpi, linha_kpis
from pages.Visao_Geral.Dados import dados_visao_geral as dados

PERIODOS = {"7": "Últimos 7 dias", "30": "Últimos 30 dias", "60": "Últimos 60 dias"}


@module.ui
def visao_geral_ui():
    return ui.div(
        filtros(ui.input_select("periodo", "Período", PERIODOS, selected="30")),
        ui.output_ui("kpis"),
        ui.layout_columns(
            cartao("Sessões por dia e app", ui.output_ui("grafico_dia")),
            cartao("Horário de uso", ui.output_ui("grafico_hora")),
            col_widths=(8, 4),
        ),
        cartao("Páginas mais usadas", ui.output_data_frame("paginas")),
    )


@module.server
def visao_geral_server(input, output, session):
    @reactive.calc
    def base() -> pl.DataFrame:
        return dados.sessoes(int(input.periodo()))

    @render.ui
    def kpis():
        df = base()
        hoje = df.filter(pl.col("dia") == data_base())
        rotinas = ler("rotinas").filter(pl.col("inicio").dt.date() == data_base())
        falhas = rotinas.filter(pl.col("status") != "Sucesso").height
        erros = ler("erros").filter(pl.col("momento").dt.date() > data_base() - timedelta(days=7)).height
        return linha_kpis(
            kpi("Sessões hoje", numero(hoje.height), f"{numero(hoje['login'].n_unique())} pessoas até agora"),
            kpi("Usuários no período", numero(df["login"].n_unique()), f"{numero(df.height)} sessões"),
            kpi("Tempo médio", f"{numero(df['minutos'].mean() or 0, 1)} min", "por sessão"),
            kpi(
                "Rotinas desta madrugada",
                f"{rotinas.height - falhas} de {rotinas.height}",
                "sem falha",
                cores.NEGATIVO if falhas else cores.POSITIVO,
            ),
            kpi("Erros em 7 dias", numero(erros), "registrados pelas telas", cores.ALERTA if erros else None),
        )

    @render.ui
    def grafico_dia():
        d = dados.por_dia_app(base())
        apps = [a for a in cores.APPS if a in d.columns]
        return grafico(
            {
                "tooltip": {"trigger": "axis"},
                "legend": {"top": 0},
                "grid": {"left": 40, "right": 20, "top": 40, "bottom": 30},
                "xAxis": {"type": "category", "data": [x.strftime("%d/%m") for x in d["dia"]]},
                "yAxis": {"type": "value", "minInterval": 1},
                "series": [
                    {
                        "name": a,
                        "type": "bar",
                        "stack": "s",
                        "data": d[a].to_list(),
                        "itemStyle": {"color": cores.APPS[a]},
                    }
                    for a in apps
                ],
            }
        )

    @render.ui
    def grafico_hora():
        h = dados.por_hora(base())
        return grafico(
            {
                "tooltip": {"trigger": "axis"},
                "grid": {"left": 40, "right": 10, "top": 20, "bottom": 30},
                "xAxis": {"type": "category", "data": [f"{x}h" for x in h["hora"]]},
                "yAxis": {"type": "value"},
                "series": [
                    {
                        "type": "bar",
                        "name": "Sessões",
                        "data": h["len"].to_list(),
                        "itemStyle": {"color": cores.SERIES[1], "borderRadius": [4, 4, 0, 0]},
                    }
                ],
            }
        )

    @render.data_frame
    def paginas():
        p = dados.paginas_mais_usadas(base())
        return render.DataGrid(
            pl.DataFrame(
                {
                    "Página": p["pagina"],
                    "App": p["app"],
                    "Sessões": [numero(v) for v in p["sessoes"]],
                    "Pessoas": [numero(v) for v in p["usuarios"]],
                    "Horas de uso": [numero(v / 60, 1) for v in p["minutos"]],
                }
            ),
            width="100%",
            height="auto",
            summary=False,
        )
