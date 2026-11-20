from datetime import date

import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.dados import ler
from core.formato import mes_curto, moeda, numero, pct
from core.graficos import grafico
from core.layout import cartao, filtros, kpi, linha_kpis
from pages.Markup.Dados import dados_markup as dados

# Abaixo do mínimo pinta de vermelho; acima do bom, de verde.
MARKUP_MINIMO = 0.28
MARKUP_BOM = 0.40


@module.ui
def markup_ui():
    filiais = sorted(ler("equipe")["filial"].unique().to_list())
    prod = ler("produtos")
    return ui.div(
        filtros(
            ui.input_select("mes", "Mês", {m.isoformat(): mes_curto(m) for m in dados.meses()}),
            ui.input_select("filial", "Filial", {"": "Todas", **{f: f for f in filiais}}),
            ui.input_selectize(
                "categoria",
                "Categoria",
                sorted(prod["categoria"].unique().to_list()),
                multiple=True,
                options={"placeholder": "Todas"},
            ),
            ui.input_selectize(
                "marca",
                "Marca",
                sorted(prod["marca"].unique().to_list()),
                multiple=True,
                options={"placeholder": "Todas"},
            ),
            limpar_id="limpar",
        ),
        ui.output_ui("kpis"),
        cartao(
            "Markup por produto",
            ui.output_data_frame("tabela"),
            ui.div(
                f"Markup = faturamento ÷ custo - 1. Vermelho abaixo de {pct(MARKUP_MINIMO, 0)}, "
                f"verde a partir de {pct(MARKUP_BOM, 0)}. Variação em pontos percentuais sobre o mês anterior.",
                class_="legenda",
            ),
        ),
        ui.layout_columns(
            cartao("Volume × markup (tamanho = saldo)", ui.output_ui("dispersao")),
            cartao("Markup por categoria", ui.output_ui("categorias")),
            col_widths=(7, 5),
        ),
    )


@module.server
def markup_server(input, output, session):
    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar():
        ui.update_select("filial", selected="")
        ui.update_selectize("categoria", selected=[])
        ui.update_selectize("marca", selected=[])

    @reactive.calc
    def base() -> pl.DataFrame:
        return dados.por_produto(
            date.fromisoformat(input.mes()), input.filial() or None, list(input.categoria()), list(input.marca())
        )

    @render.ui
    def kpis():
        df = base()
        if df.is_empty():
            return ui.div()
        fat, custo = df["faturamento"].sum(), df["custo"].sum()
        melhor = df.sort("markup", descending=True).row(0, named=True)
        pior = df.sort("markup").row(0, named=True)

        return linha_kpis(
            kpi("Markup médio", pct(fat / custo - 1), f"{numero(df['caixas'].sum())} caixas"),
            kpi("Saldo de markup", moeda(fat - custo, 0), f"sobre {moeda(fat, 0)} faturados"),
            kpi("Maior markup", pct(melhor["markup"]), melhor["produto"]),
            kpi("Menor markup", pct(pior["markup"]), pior["produto"]),
        )

    @render.data_frame
    def tabela():
        df = base()
        exibir = pl.DataFrame(
            {
                "Produto": df["produto"],
                "Marca": df["marca"],
                "Categoria": df["categoria"],
                "Caixas": [numero(v) for v in df["caixas"]],
                "Preço médio": [moeda(v) for v in df["preco_medio"]],
                "Custo médio": [moeda(v) for v in df["custo_medio"]],
                "Markup": [pct(v) for v in df["markup"]],
                "Var. (p.p.)": [numero(v * 100, 1) if v is not None else "" for v in df["variacao_pp"]],
                "Saldo": [moeda(v, 0) for v in df["saldo"]],
                "Part. fat.": [pct(v) for v in df["participacao"]],
            }
        )
        estilos = []
        for i, linha in enumerate(df.iter_rows(named=True)):
            estilos.append(
                {
                    "rows": [i],
                    "cols": [1],
                    "style": {"background-color": linha["cor_marca"], "color": "#fff", "font-weight": "600"},
                }
            )
            cor = (
                cores.NEGATIVO
                if linha["markup"] < MARKUP_MINIMO
                else cores.POSITIVO
                if linha["markup"] >= MARKUP_BOM
                else None
            )
            if cor:
                estilos.append({"rows": [i], "cols": [6], "style": {"color": cor, "font-weight": "700"}})
            if linha["variacao_pp"] is not None:
                estilos.append(
                    {
                        "rows": [i],
                        "cols": [7],
                        "style": {"color": cores.POSITIVO if linha["variacao_pp"] >= 0 else cores.NEGATIVO},
                    }
                )
        return render.DataGrid(exibir, styles=estilos, width="100%", height="auto", summary=False)

    @render.ui
    def dispersao():
        df = base()
        maior = df["saldo"].max() or 1
        return grafico(
            {
                "tooltip": {
                    "formatter": "js:function (p) { return p.data[3] + '<br>Caixas: ' + "
                    "p.data[0].toLocaleString('pt-BR') + '<br>Markup: ' + p.data[1].toLocaleString('pt-BR') + '%'; }"
                },
                "grid": {"left": 55, "right": 25, "top": 30, "bottom": 40},
                "xAxis": {"type": "value", "name": "Caixas", "nameLocation": "middle", "nameGap": 25, "scale": True},
                "yAxis": {"type": "value", "name": "Markup %", "scale": True},
                "series": [
                    {
                        "type": "scatter",
                        "data": [
                            {
                                "value": [r["caixas"], round(r["markup"] * 100, 1), r["saldo"], r["produto"]],
                                "symbolSize": 10 + 40 * (r["saldo"] / maior),
                                "itemStyle": {"color": r["cor_marca"], "opacity": 0.85},
                            }
                            for r in df.iter_rows(named=True)
                        ],
                        "markLine": {
                            "silent": True,
                            "symbol": "none",
                            "lineStyle": {"color": cores.NEGATIVO, "type": "dashed"},
                            "data": [{"yAxis": MARKUP_MINIMO * 100}],
                            "label": {"formatter": "mínimo"},
                        },
                    }
                ],
            }
        )

    @render.ui
    def categorias():
        cat = dados.por_categoria(base())
        return grafico(
            {
                "tooltip": {
                    "trigger": "axis",
                    "valueFormatter": "js:function (v) { return v.toLocaleString('pt-BR') + '%'; }",
                },
                "grid": {"left": 110, "right": 40, "top": 20, "bottom": 30},
                "xAxis": {"type": "value", "axisLabel": {"formatter": "{value}%"}},
                "yAxis": {"type": "category", "data": cat["categoria"].to_list(), "inverse": True},
                "series": [
                    {
                        "type": "bar",
                        "name": "Markup",
                        "data": [round(v * 100, 1) for v in cat["markup"]],
                        "label": {"show": True, "position": "right", "formatter": "{c}%"},
                        "itemStyle": {"color": cores.SERIES[0], "borderRadius": [0, 4, 4, 0]},
                    }
                ],
            }
        )
