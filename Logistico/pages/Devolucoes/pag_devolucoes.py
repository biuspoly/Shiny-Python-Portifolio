import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.dados import ler
from core.formato import moeda, numero, pct
from core.graficos import MOEDA_BR, MOEDA_CURTA, eixo_valor, grafico
from core.layout import cartao, filtros, kpi, linha_kpis
from pages.Devolucoes.Dados import dados_devolucoes as dados


@module.ui
def devolucoes_ui():
    e = ler("entregas")
    return ui.div(
        filtros(
            ui.input_select("periodo", "Período", dados.PERIODOS, selected="30"),
            ui.input_select("filial", "Filial", {"": "Todas", **{f: f for f in sorted(e["filial"].unique())}}),
            ui.input_selectize(
                "motivo",
                "Motivo",
                sorted(e["motivo"].drop_nulls().unique().to_list()),
                multiple=True,
                options={"placeholder": "Todos"},
            ),
            limpar_id="limpar",
        ),
        ui.output_ui("kpis"),
        ui.layout_columns(
            cartao("Devolução por motivo", ui.output_ui("grafico_motivo")),
            cartao("Índice de devolução por dia", ui.output_ui("grafico_dia")),
            col_widths=(5, 7),
        ),
        cartao(
            "Clientes com devolução",
            ui.output_data_frame("clientes"),
            ui.div("Índice = valor devolvido ÷ valor faturado ao cliente no período.", class_="legenda"),
        ),
    )


@module.server
def devolucoes_server(input, output, session):
    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar():
        ui.update_select("periodo", selected="30")
        ui.update_select("filial", selected="")
        ui.update_selectize("motivo", selected=[])

    @reactive.calc
    def base() -> pl.DataFrame:
        return dados.periodo(int(input.periodo()), input.filial() or None, list(input.motivo()))

    @render.ui
    def kpis():
        df = base()
        devolvido, faturado = df["valor_devolvido"].sum(), df["valor"].sum()
        motivos = dados.por_motivo(df)
        principal = motivos.row(0, named=True) if motivos.height else None
        return linha_kpis(
            kpi("Valor devolvido", moeda(devolvido, 0), f"de {moeda(faturado, 0)} entregues", cores.NEGATIVO),
            kpi("Índice de devolução", pct(devolvido / faturado if faturado else None, 2)),
            kpi("Notas com devolução", numero((df["valor_devolvido"] > 0).sum()), f"de {numero(df.height)} notas"),
            kpi(
                "Principal motivo",
                principal["motivo"] if principal else "-",
                moeda(principal["valor_devolvido"], 0) if principal else "",
            ),
        )

    @render.ui
    def grafico_motivo():
        m = dados.por_motivo(base())
        return grafico(
            {
                "tooltip": {"trigger": "axis", "valueFormatter": MOEDA_BR},
                "grid": {"left": 190, "right": 70, "top": 10, "bottom": 25},
                "xAxis": eixo_valor("", MOEDA_CURTA),
                "yAxis": {"type": "category", "data": m["motivo"].to_list(), "inverse": True},
                "series": [
                    {
                        "type": "bar",
                        "name": "Devolvido",
                        "data": [round(v) for v in m["valor_devolvido"]],
                        "itemStyle": {"color": cores.SERIES[1], "borderRadius": [0, 4, 4, 0]},
                        "label": {
                            "show": True,
                            "position": "right",
                            "formatter": "js:function (p) { return p.value.toLocaleString('pt-BR'); }",
                        },
                    }
                ],
            },
            altura="34vh",
        )

    @render.ui
    def grafico_dia():
        d = dados.por_dia(base())
        media = d["valor_devolvido"].sum() / d["valor"].sum() if d["valor"].sum() else 0
        return grafico(
            {
                "tooltip": {
                    "trigger": "axis",
                    "valueFormatter": "js:function (v) { return v.toLocaleString('pt-BR') + '%'; }",
                },
                "grid": {"left": 50, "right": 20, "top": 20, "bottom": 30},
                "xAxis": {"type": "category", "data": [x.strftime("%d/%m") for x in d["data"]]},
                "yAxis": {"type": "value", "axisLabel": {"formatter": "{value}%"}},
                "series": [
                    {
                        "type": "line",
                        "name": "Índice",
                        "smooth": True,
                        "areaStyle": {"opacity": 0.15},
                        "data": [round(v * 100, 2) for v in d["indice"]],
                        "itemStyle": {"color": cores.SERIES[0]},
                        "markLine": {
                            "symbol": "none",
                            "data": [{"yAxis": round(media * 100, 2)}],
                            "lineStyle": {"color": cores.NEGATIVO, "type": "dashed"},
                            "label": {"formatter": "média", "position": "insideEndTop"},
                        },
                    }
                ],
            },
            altura="34vh",
        )

    @render.data_frame
    def clientes():
        c = dados.por_cliente(base())
        return render.DataGrid(
            pl.DataFrame(
                {
                    "Cliente": c["cliente"],
                    "Cidade": c["cidade"],
                    "Faturado": [moeda(v, 0) for v in c["faturado"]],
                    "Devolvido": [moeda(v, 0) for v in c["devolvido"]],
                    "Índice": [pct(v) for v in c["indice"]],
                    "Notas devolvidas": c["notas_devolvidas"].cast(pl.String),
                    "Motivo mais comum": c["motivo_mais_comum"],
                }
            ),
            width="100%",
            height="40vh",
            summary="Mostrando {start} a {end} de {total} clientes",
        )
