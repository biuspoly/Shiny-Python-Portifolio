import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.dados import ler
from core.formato import mes_curto, moeda, numero
from core.graficos import MOEDA_BR, MOEDA_CURTA, eixo_valor, grafico
from core.layout import cartao, filtros, kpi, linha_kpis
from pages.Frotas.Dados import dados_frotas as dados

_COR_DOC = {"Pago": cores.POSITIVO, "A vencer": cores.ALERTA, "Vencido": cores.NEGATIVO}


@module.ui
def frotas_ui():
    veic = ler("veiculos")
    return ui.div(
        filtros(
            ui.input_select("filial", "Filial", {"": "Todas", **{f: f for f in sorted(veic["filial"].unique())}}),
            ui.input_selectize(
                "tipo", "Tipo", sorted(veic["tipo"].unique().to_list()), multiple=True, options={"placeholder": "Todos"}
            ),
            ui.input_select("situacao", "Situação", {"": "Todas", "pendente": "Com pendência", "regular": "Regular"}),
            ui.input_text("placa", "Placa", placeholder="ABC1D23"),
            limpar_id="limpar",
        ),
        ui.output_ui("kpis"),
        cartao(
            "Veículos",
            ui.output_data_frame("tabela"),
            ui.div(
                "Custo e km do mês anterior (combustível + manutenção). Clique num veículo para ver as multas dele.",
                class_="legenda",
            ),
        ),
        ui.layout_columns(
            cartao("Custo da frota nos últimos 13 meses", ui.output_ui("grafico_custo")),
            cartao(
                "Multas",
                ui.output_data_frame("tabela_multas"),
                ferramentas=ui.input_switch("so_abertas", "Só em aberto", value=True),
            ),
            col_widths=(7, 5),
        ),
    )


@module.server
def frotas_server(input, output, session):
    base = dados.veiculos()

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar():
        ui.update_select("filial", selected="")
        ui.update_selectize("tipo", selected=[])
        ui.update_select("situacao", selected="")
        ui.update_text("placa", value="")

    @reactive.calc
    def filtrada() -> pl.DataFrame:
        df = base
        if input.filial():
            df = df.filter(pl.col("filial") == input.filial())
        if input.tipo():
            df = df.filter(pl.col("tipo").is_in(list(input.tipo())))
        if input.situacao():
            df = df.filter(pl.col("pendente") == (input.situacao() == "pendente"))
        if input.placa().strip():
            df = df.filter(pl.col("placa").str.contains(input.placa().strip().upper(), literal=True))
        return df

    @render.ui
    def kpis():
        df = filtrada()
        km, custo = df["km"].sum(), df["custo"].sum()
        return linha_kpis(
            kpi("Veículos", numero(df.height), f"Idade média {numero(df['idade'].mean() or 0, 1)} anos"),
            kpi("Com pendência", numero(df["pendente"].sum()), "multa aberta ou documento vencido", cores.NEGATIVO),
            kpi("Multas em aberto", moeda(df["valor_multas"].sum()), f"{numero(df['multas_abertas'].sum())} autuações"),
            kpi(
                "IPVA vencido",
                numero((df["ipva"] == "Vencido").sum()),
                f"Licenciamento vencido: {numero((df['licenciamento'] == 'Vencido').sum())}",
            ),
            kpi("Custo por km", moeda(custo / km if km else None), f"{numero(km)} km no mês anterior"),
        )

    @render.data_frame
    def tabela():
        df = filtrada()
        exibir = pl.DataFrame(
            {
                "Placa": df["placa"],
                "Tipo": df["tipo"],
                "Modelo": df["modelo"],
                "Ano": df["ano"].cast(pl.String),
                "Filial": df["filial"],
                "Motorista": df["motorista"],
                "Km": [numero(v) for v in df["km"]],
                "R$/km": [moeda(v) for v in df["custo_km"]],
                "Multas": df["multas_abertas"].cast(pl.String),
                "Valor multas": [moeda(v) if v else "-" for v in df["valor_multas"]],
                "IPVA": df["ipva"],
                "Licenciamento": df["licenciamento"],
            }
        )
        estilos = []
        for col, nome in ((10, "ipva"), (11, "licenciamento")):
            for situacao, cor in _COR_DOC.items():
                linhas = df.with_row_index().filter(pl.col(nome) == situacao)["index"].to_list()
                if linhas:
                    estilos.append({"rows": linhas, "cols": [col], "style": {"color": cor, "font-weight": "700"}})
        com_multa = df.with_row_index().filter(pl.col("multas_abertas") > 0)["index"].to_list()
        if com_multa:
            estilos.append(
                {"rows": com_multa, "cols": [8, 9], "style": {"color": cores.NEGATIVO, "font-weight": "700"}}
            )
        return render.DataGrid(
            exibir,
            selection_mode="row",
            styles=estilos,
            width="100%",
            height="45vh",
            summary="Mostrando {start} a {end} de {total} veículos",
        )

    @reactive.calc
    def placas_escolhidas() -> list[str]:
        linhas = tabela.cell_selection()["rows"]
        df = filtrada()
        return [df["placa"][i] for i in linhas] if linhas else df["placa"].to_list()

    @render.ui
    def grafico_custo():
        c = dados.custo_mensal(filtrada()["placa"].to_list())
        return grafico(
            {
                "tooltip": {"trigger": "axis", "valueFormatter": MOEDA_BR},
                "legend": {"top": 0},
                "grid": {"left": 70, "right": 50, "top": 40, "bottom": 30},
                "xAxis": {"type": "category", "data": [mes_curto(m) for m in c["mes"]]},
                "yAxis": [eixo_valor("R$", MOEDA_CURTA), eixo_valor("R$/km", scale=True)],
                "series": [
                    {
                        "name": "Combustível",
                        "type": "bar",
                        "stack": "c",
                        "data": [round(v) for v in c["custo_combustivel"]],
                        "itemStyle": {"color": cores.SERIES[0]},
                    },
                    {
                        "name": "Manutenção",
                        "type": "bar",
                        "stack": "c",
                        "data": [round(v) for v in c["custo_manutencao"]],
                        "itemStyle": {"color": cores.SERIES[3], "borderRadius": [4, 4, 0, 0]},
                    },
                    {
                        "name": "R$/km",
                        "type": "line",
                        "yAxisIndex": 1,
                        "smooth": True,
                        "data": [
                            round((a + b) / k, 2) if k else None
                            for a, b, k in zip(c["custo_combustivel"], c["custo_manutencao"], c["km"])
                        ],
                        "itemStyle": {"color": cores.SERIES[4]},
                    },
                ],
            }
        )

    @render.data_frame
    def tabela_multas():
        m = dados.multas(placas_escolhidas(), input.so_abertas())
        return render.DataGrid(
            pl.DataFrame(
                {
                    "Placa": m["placa"],
                    "Data": [d.strftime("%d/%m/%Y") for d in m["data"]],
                    "Infração": m["infracao"],
                    "Valor": [moeda(v) for v in m["valor"]],
                    "Pontos": m["pontos"].cast(pl.String),
                    "Situação": m["situacao"],
                }
            ),
            width="100%",
            height="38vh",
            summary=False,
        )
