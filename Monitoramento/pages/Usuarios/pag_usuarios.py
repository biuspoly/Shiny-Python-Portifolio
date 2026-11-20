import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.dados import ler
from core.formato import numero
from core.graficos import grafico
from core.layout import cartao, filtros
from pages.Usuarios.Dados import dados_usuarios as dados

PERIODOS = {"7": "Últimos 7 dias", "30": "Últimos 30 dias", "60": "Últimos 60 dias"}


@module.ui
def usuarios_ui():
    areas = sorted(ler("usuarios")["area"].unique().to_list())
    return ui.div(
        filtros(
            ui.input_select("periodo", "Período", PERIODOS, selected="30"),
            ui.input_selectize("area", "Área", areas, multiple=True, options={"placeholder": "Todas"}),
            ui.input_switch("so_ativos", "Só usuários ativos", value=True),
        ),
        ui.layout_columns(
            cartao(
                "Quem usa os painéis",
                ui.output_data_frame("tabela"),
                ui.div("Clique numa pessoa para ver a atividade dela.", class_="legenda"),
            ),
            cartao("Atividade por dia", ui.output_ui("titulo"), ui.output_ui("grafico_pessoa")),
            col_widths=(7, 5),
        ),
    )


@module.server
def usuarios_server(input, output, session):
    @reactive.calc
    def base() -> pl.DataFrame:
        df = dados.resumo(int(input.periodo()))
        if input.area():
            df = df.filter(pl.col("area").is_in(list(input.area())))
        if input.so_ativos():
            df = df.filter(pl.col("ativo"))
        return df

    @render.data_frame
    def tabela():
        df = base()
        return render.DataGrid(
            pl.DataFrame(
                {
                    "Pessoa": df["nome"],
                    "Login": df["login"],
                    "Área": df["area"],
                    "Filial": df["filial"],
                    "Sessões": [numero(v) for v in df["sessoes"]],
                    "Horas": [numero(v / 60, 1) for v in df["minutos"]],
                    "Última visita": [d.strftime("%d/%m/%Y %H:%M") if d else "-" for d in df["ultima"]],
                    "Apps": df["apps"].fill_null("-"),
                }
            ),
            selection_mode="row",
            width="100%",
            height="65vh",
            summary="Mostrando {start} a {end} de {total} pessoas",
        )

    @reactive.calc
    def escolhido() -> dict | None:
        linhas = tabela.cell_selection()["rows"]
        return base().row(linhas[0], named=True) if linhas else None

    @render.ui
    def titulo():
        p = escolhido()
        if p is None:
            return ui.div("Ninguém escolhido.", class_="legenda")
        return ui.div(ui.strong(p["nome"]), f" · {p['area']} · {p['filial']}", class_="legenda")

    @render.ui
    def grafico_pessoa():
        p = escolhido()
        if p is None:
            return ui.div()
        a = dados.atividade(p["login"], int(input.periodo()))
        return grafico(
            {
                "tooltip": {"trigger": "axis"},
                "legend": {"top": 0},
                "grid": {"left": 40, "right": 40, "top": 40, "bottom": 30},
                "xAxis": {"type": "category", "data": [x.strftime("%d/%m") for x in a["dia"]]},
                "yAxis": [{"type": "value", "minInterval": 1, "name": "Sessões"}, {"type": "value", "name": "Min"}],
                "series": [
                    {
                        "name": "Sessões",
                        "type": "bar",
                        "data": a["sessoes"].to_list(),
                        "itemStyle": {"color": cores.SERIES[0], "borderRadius": [4, 4, 0, 0]},
                    },
                    {
                        "name": "Minutos",
                        "type": "line",
                        "yAxisIndex": 1,
                        "smooth": True,
                        "data": [round(v) for v in a["minutos"]],
                        "itemStyle": {"color": cores.SERIES[1]},
                    },
                ],
            },
            altura="55vh",
        )
