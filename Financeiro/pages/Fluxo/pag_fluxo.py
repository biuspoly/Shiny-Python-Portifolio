import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.dados import data_base
from core.formato import mes_curto, moeda, numero, pct
from core.graficos import MOEDA_BR, MOEDA_CURTA, eixo_valor, grafico
from core.layout import cartao, filtros, kpi, linha_kpis
from pages.Fluxo.Dados import dados_fluxo as dados

HORIZONTES = {"15": "Próximos 15 dias", "30": "Próximos 30 dias", "60": "Próximos 60 dias"}


@module.ui
def fluxo_ui():
    return ui.div(
        filtros(
            ui.input_select("conta", "Conta", {"": "Todas", **{c: c for c in dados.contas()}}),
            ui.input_select("horizonte", "Projeção", HORIZONTES, selected="30"),
        ),
        ui.output_ui("kpis"),
        ui.layout_columns(
            cartao(
                "Fluxo de caixa diário",
                ui.output_ui("grafico_fluxo"),
                ui.div(
                    "Até ontem, o realizado; de hoje em diante, recebimentos previstos e títulos em aberto "
                    "(o vencido sem pagamento entra hoje).",
                    class_="legenda",
                ),
            ),
            cartao(
                "Indicadores econômicos",
                ui.output_ui("indicadores"),
                ui.div("Dados reais do Banco Central (SGS), atualizados a cada geração.", class_="legenda"),
            ),
            col_widths=(9, 3),
        ),
    )


@module.server
def fluxo_server(input, output, session):
    @reactive.calc
    def base() -> pl.DataFrame:
        return dados.fluxo(input.conta() or None, int(input.horizonte()))

    @render.ui
    def kpis():
        df = base()
        futuro = df.filter(~pl.col("realizado"))
        saldo = dados.saldo_hoje(input.conta() or None)
        if futuro.is_empty():
            return ui.div()
        menor = futuro.sort("saldo").row(0, named=True)
        final = futuro["saldo"][-1]
        return linha_kpis(
            kpi(
                "Saldo em conta",
                moeda(saldo, 0),
                f"fechamento de {dados.ultimo_dia_util(data_base()).strftime('%d/%m')}",
            ),
            kpi(
                "Entradas previstas",
                moeda(futuro["entradas"].sum(), 0),
                HORIZONTES[input.horizonte()].lower(),
                cores.ENTRADA,
            ),
            kpi("Saídas previstas", moeda(futuro["saidas"].sum(), 0), "títulos a pagar", cores.SAIDA),
            kpi(
                "Saldo projetado",
                moeda(final, 0),
                f"em {futuro['data'][-1].strftime('%d/%m/%Y')}",
                cores.POSITIVO if final >= saldo else cores.ALERTA,
            ),
            kpi(
                "Menor saldo",
                moeda(menor["saldo"], 0),
                f"em {menor['data'].strftime('%d/%m/%Y')}",
                cores.NEGATIVO if menor["saldo"] < 0 else None,
            ),
        )

    @render.ui
    def grafico_fluxo():
        df = base()
        datas = [d.strftime("%d/%m") for d in df["data"]]
        realizado = df["realizado"].to_list()
        # O saldo vira duas séries para a projeção sair tracejada; o hoje fica nas duas para ligar a linha.
        corte = realizado.count(True)
        saldo = [round(v) for v in df["saldo"]]
        return grafico(
            {
                "tooltip": {"trigger": "axis", "valueFormatter": MOEDA_BR},
                "legend": {"top": 0},
                "grid": {"left": 80, "right": 80, "top": 40, "bottom": 30},
                "xAxis": {"type": "category", "data": datas},
                "yAxis": [eixo_valor("Movimento", MOEDA_CURTA), eixo_valor("Saldo", MOEDA_CURTA, scale=True)],
                "series": [
                    {
                        "name": "Entradas",
                        "type": "bar",
                        "stack": "m",
                        "data": [round(v) for v in df["entradas"]],
                        "itemStyle": {"color": cores.ENTRADA, "opacity": 0.85},
                    },
                    {
                        "name": "Saídas",
                        "type": "bar",
                        "stack": "m",
                        "data": [-round(v) for v in df["saidas"]],
                        "itemStyle": {"color": cores.SAIDA, "opacity": 0.85},
                    },
                    {
                        "name": "Saldo realizado",
                        "type": "line",
                        "yAxisIndex": 1,
                        "symbol": "none",
                        "data": saldo[:corte] + [None] * (len(saldo) - corte),
                        "lineStyle": {"width": 3},
                        "itemStyle": {"color": cores.SERIES[0]},
                    },
                    {
                        "name": "Saldo projetado",
                        "type": "line",
                        "yAxisIndex": 1,
                        "symbol": "none",
                        "data": [None] * max(corte - 1, 0) + saldo[max(corte - 1, 0) :],
                        "lineStyle": {"width": 3, "type": "dashed"},
                        "itemStyle": {"color": cores.SERIES[0]},
                    },
                ],
            },
            altura="52vh",
        )

    @render.ui
    def indicadores():
        ind = dados.indicadores()
        dolar = ind["dolar"]
        ultimo = dolar.row(-1, named=True) if dolar.height else None
        variacao = (dolar["dolar"][-1] / dolar["dolar"][0] - 1) if dolar.height > 1 else None
        return ui.div(
            ui.div(
                ui.div("Dólar (PTAX venda)", class_="kpi-titulo"),
                ui.div(f"R$ {numero(ultimo['dolar'], 4)}" if ultimo else "-", class_="kpi-valor"),
                ui.div(
                    f"{ultimo['data'].strftime('%d/%m/%Y')} · {pct(variacao)} em 90 dias" if ultimo else "",
                    class_="kpi-detalhe",
                ),
            ),
            grafico(
                {
                    "grid": {"left": 5, "right": 5, "top": 5, "bottom": 5},
                    "xAxis": {"type": "category", "show": False, "data": [d.isoformat() for d in dolar["data"]]},
                    "yAxis": {"type": "value", "show": False, "scale": True},
                    "tooltip": {"trigger": "axis"},
                    "series": [
                        {
                            "type": "line",
                            "symbol": "none",
                            "smooth": True,
                            "data": dolar["dolar"].to_list(),
                            "areaStyle": {"opacity": 0.12},
                            "itemStyle": {"color": cores.SERIES[0]},
                        }
                    ],
                },
                altura="12vh",
            ),
            ui.hr(),
            ui.div(
                ui.div("Selic meta", class_="kpi-titulo"),
                ui.div(f"{numero(ind['selic'], 2)}% a.a." if ind["selic"] else "-", class_="kpi-valor"),
                ui.div(
                    f"vigente em {ind['selic_data'].strftime('%d/%m/%Y')}" if ind["selic_data"] else "",
                    class_="kpi-detalhe",
                ),
            ),
            ui.hr(),
            ui.div(
                ui.div("IPCA 12 meses", class_="kpi-titulo"),
                ui.div(pct(ind["ipca_12m"], 2), class_="kpi-valor"),
                ui.div(f"até {mes_curto(ind['ipca_ate'])}" if ind["ipca_ate"] else "", class_="kpi-detalhe"),
            ),
        )
