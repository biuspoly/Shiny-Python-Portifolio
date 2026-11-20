import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.formato import numero
from core.graficos import grafico
from core.layout import cartao, filtros
from pages.Erros.Dados import dados_erros as dados


@module.ui
def erros_ui():
    return ui.div(
        filtros(
            ui.input_select("dias", "Período", {"7": "Últimos 7 dias", "30": "Últimos 30 dias"}, selected="30"),
            ui.input_selectize("app", "App", list(cores.APPS), multiple=True, options={"placeholder": "Todos"}),
        ),
        ui.layout_columns(
            cartao("Erros por dia", ui.output_ui("grafico_dia")),
            cartao("Erros agrupados pela mensagem", ui.output_data_frame("agrupados")),
            col_widths=(5, 7),
        ),
        cartao("Ocorrências", ui.output_data_frame("ocorrencias")),
    )


@module.server
def erros_server(input, output, session):
    @reactive.calc
    def base() -> pl.DataFrame:
        return dados.erros(int(input.dias()), list(input.app()))

    @render.ui
    def grafico_dia():
        d = (
            base()
            .group_by(pl.col("momento").dt.date().alias("dia"), "app")
            .len()
            .pivot(on="app", index="dia", values="len")
            .fill_null(0)
            .sort("dia")
        )
        apps = [a for a in cores.APPS if a in d.columns]
        return grafico(
            {
                "tooltip": {"trigger": "axis"},
                "legend": {"top": 0},
                "grid": {"left": 35, "right": 15, "top": 40, "bottom": 30},
                "xAxis": {"type": "category", "data": [x.strftime("%d/%m") for x in d["dia"]]},
                "yAxis": {"type": "value", "minInterval": 1},
                "series": [
                    {
                        "name": a,
                        "type": "bar",
                        "stack": "e",
                        "data": d[a].to_list(),
                        "itemStyle": {"color": cores.APPS[a]},
                    }
                    for a in apps
                ],
            }
        )

    @render.data_frame
    def agrupados():
        g = dados.agrupados(base())
        return render.DataGrid(
            pl.DataFrame(
                {
                    "Mensagem": g["mensagem"],
                    "App": g["app"],
                    "Página": g["pagina"],
                    "Vezes": [numero(v) for v in g["vezes"]],
                    "Pessoas": [numero(v) for v in g["pessoas"]],
                    "Última": [d.strftime("%d/%m %H:%M") for d in g["ultima"]],
                }
            ),
            width="100%",
            height="auto",
            summary=False,
        )

    @render.data_frame
    def ocorrencias():
        o = base().sort("momento", descending=True)
        return render.DataGrid(
            pl.DataFrame(
                {
                    "Quando": [d.strftime("%d/%m/%Y %H:%M") for d in o["momento"]],
                    "App": o["app"],
                    "Página": o["pagina"],
                    "Mensagem": o["mensagem"],
                    "Login": o["login"],
                }
            ),
            width="100%",
            height="35vh",
            summary="Mostrando {start} a {end} de {total} ocorrências",
        )
