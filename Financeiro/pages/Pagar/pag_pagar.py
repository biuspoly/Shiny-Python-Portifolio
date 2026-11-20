import io

import polars as pl
from faicons import icon_svg
from shiny import module, reactive, render, req, ui

from core import cores
from core.dados import ler
from core.formato import moeda, numero
from core.graficos import MOEDA_BR, MOEDA_CURTA, eixo_valor, grafico
from core.layout import cartao, filtros, kpi, linha_kpis
from pages.Pagar.Dados import dados_pagar as dados

_COR = {
    "Vencido": cores.NEGATIVO,
    "Vence hoje": cores.ALERTA,
    "Próximos 7 dias": "#C9A227",
    "A vencer": cores.NEUTRO,
    "Pago": cores.POSITIVO,
}


@module.ui
def pagar_ui():
    t = ler("titulos_pagar")
    inicio, fim = dados.periodo_padrao()
    return ui.div(
        filtros(
            ui.input_date_range(
                "vencimento",
                "Vencimento",
                start=inicio,
                end=fim,
                format="dd/mm/yyyy",
                language="pt-BR",
                separator="até",
            ),
            ui.input_select("filial", "Filial", {"": "Todas", **{f: f for f in sorted(t["filial"].unique())}}),
            ui.input_selectize(
                "centro",
                "Centro de custo",
                sorted(t["centro_custo"].unique().to_list()),
                multiple=True,
                options={"placeholder": "Todos"},
            ),
            ui.input_selectize(
                "situacao", "Situação", dados.SITUACOES, multiple=True, options={"placeholder": "Todas"}
            ),
            ui.input_text("busca", "Fornecedor", placeholder="Nome ou nº do título"),
            limpar_id="limpar",
        ),
        ui.output_ui("kpis"),
        ui.layout_columns(
            cartao(
                "Títulos a pagar",
                ui.output_data_frame("tabela"),
                ferramentas=ui.download_button(
                    "exportar", None, icon=icon_svg("file-csv"), class_="btn-exportar", title="Exportar CSV"
                ),
            ),
            cartao("Por centro de custo", ui.output_ui("grafico_centro")),
            col_widths=(8, 4),
        ),
    )


@module.server
def pagar_server(input, output, session):
    base = dados.titulos()

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar():
        inicio, fim = dados.periodo_padrao()
        ui.update_date_range("vencimento", start=inicio, end=fim)
        ui.update_select("filial", selected="")
        ui.update_selectize("centro", selected=[])
        ui.update_selectize("situacao", selected=[])
        ui.update_text("busca", value="")

    @reactive.calc
    def filtrada() -> pl.DataFrame:
        inicio, fim = input.vencimento()
        df = base.filter(pl.col("vencimento").is_between(inicio, fim))
        if input.filial():
            df = df.filter(pl.col("filial") == input.filial())
        if input.centro():
            df = df.filter(pl.col("centro_custo").is_in(list(input.centro())))
        if input.situacao():
            df = df.filter(pl.col("situacao").is_in(list(input.situacao())))
        texto = input.busca().strip().upper()
        if texto:
            df = df.filter(
                pl.col("fornecedor").str.contains(texto, literal=True)
                | pl.col("titulo").cast(pl.String).str.starts_with(texto)
            )
        return df.sort("vencimento")

    @render.ui
    def kpis():
        df = filtrada()

        def soma(*situacoes):
            sel = df.filter(pl.col("situacao").is_in(situacoes))
            return moeda(sel["valor"].sum(), 0), f"{numero(sel.height)} títulos"

        return linha_kpis(
            kpi("Vencidos", *soma("Vencido"), cores.NEGATIVO),
            kpi("Vencem hoje", *soma("Vence hoje"), cores.ALERTA),
            kpi("Próximos 7 dias", *soma("Próximos 7 dias"), _COR["Próximos 7 dias"]),
            kpi("A vencer depois", *soma("A vencer")),
            kpi("Pagos no período", *soma("Pago"), cores.POSITIVO),
        )

    def _exibir(df: pl.DataFrame) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "Título": df["titulo"].cast(pl.String),
                "Fornecedor": df["fornecedor"],
                "Centro de custo": df["centro_custo"],
                "Filial": df["filial"],
                "Emissão": [d.strftime("%d/%m/%Y") for d in df["emissao"]],
                "Vencimento": [d.strftime("%d/%m/%Y") for d in df["vencimento"]],
                "Valor": [moeda(v) for v in df["valor"]],
                "Forma": df["forma"],
                "Situação": df["situacao"],
                "Pago em": [d.strftime("%d/%m/%Y") if d else "" for d in df["pago_em"]],
            }
        )

    @render.data_frame
    def tabela():
        df = filtrada()
        idx = df.with_row_index()
        estilos = [
            {"rows": linhas, "cols": [8], "style": {"color": cor, "font-weight": "700"}}
            for s, cor in _COR.items()
            if (linhas := idx.filter(pl.col("situacao") == s)["index"].to_list())
        ]
        return render.DataGrid(
            _exibir(df),
            styles=estilos,
            width="100%",
            height="60vh",
            summary="Mostrando {start} a {end} de {total} títulos",
        )

    @render.ui
    def grafico_centro():
        c = dados.por_centro(filtrada())
        return grafico(
            {
                "tooltip": {"trigger": "axis", "valueFormatter": MOEDA_BR},
                "legend": {"bottom": 0},
                "grid": {"left": 150, "right": 20, "top": 10, "bottom": 60},
                "xAxis": eixo_valor("", MOEDA_CURTA),
                "yAxis": {"type": "category", "data": c["centro_custo"].to_list(), "inverse": True},
                "series": [
                    {
                        "name": "Pago",
                        "type": "bar",
                        "stack": "t",
                        "data": [round(v) for v in c["pago"]],
                        "itemStyle": {"color": cores.POSITIVO},
                    },
                    {
                        "name": "Em aberto",
                        "type": "bar",
                        "stack": "t",
                        "data": [round(v) for v in c["aberto"]],
                        "itemStyle": {"color": cores.SERIES[0]},
                    },
                ],
            },
            altura="60vh",
        )

    @render.download_button(filename="titulos_a_pagar.csv")
    def exportar():
        req(not filtrada().is_empty())
        arquivo = io.StringIO()
        _exibir(filtrada()).write_csv(arquivo, separator=";")
        yield arquivo.getvalue().encode("utf-8-sig")
