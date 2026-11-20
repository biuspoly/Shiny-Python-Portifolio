import io

import polars as pl
from faicons import icon_svg
from shiny import module, reactive, render, req, ui

from core import cores
from core.dados import ler
from core.formato import mes_curto, moeda, numero, pct
from core.graficos import MOEDA_BR, NUMERO_BR, eixo_valor, grafico
from core.layout import cartao, filtros, kpi, linha_kpis
from pages.Clientes.Dados import dados_carteira as dados

_COR_SITUACAO = {"Ativo": "#087F5B", "Em risco": "#D9730D", "Inativo": "#B3262D"}


@module.ui
def carteira_ui():
    filiais = sorted(ler("equipe")["filial"].unique().to_list())
    canais = sorted(ler("clientes")["canal"].unique().to_list())
    return ui.div(
        filtros(
            ui.input_select("filial", "Filial", {"": "Todas", **{f: f for f in filiais}}),
            ui.input_selectize("vendedor", "Vendedor", [], multiple=True, options={"placeholder": "Todos"}),
            ui.input_selectize("canal", "Canal", canais, multiple=True, options={"placeholder": "Todos"}),
            ui.input_selectize(
                "situacao", "Situação", dados.SITUACOES, multiple=True, options={"placeholder": "Todas"}
            ),
            ui.input_text("busca", "Cliente", placeholder="Nome ou código"),
            limpar_id="limpar",
        ),
        ui.output_ui("kpis"),
        ui.layout_columns(
            cartao(
                "Carteira de Clientes",
                ui.output_data_frame("tabela"),
                ui.div("Clique num cliente para ver o histórico dele ao lado.", class_="legenda"),
                ferramentas=ui.download_button(
                    "exportar", None, icon=icon_svg("file-csv"), class_="btn-exportar", title="Exportar CSV"
                ),
            ),
            ui.div(
                cartao("Histórico do cliente (12 meses)", ui.output_ui("historico")),
                cartao("Faturamento 12 meses por canal", ui.output_ui("por_canal")),
            ),
            col_widths=(8, 4),
        ),
    )


@module.server
def carteira_server(input, output, session):
    base = dados.carteira()

    @reactive.effect
    def _vendedores():
        eq = ler("equipe")
        if input.filial():
            eq = eq.filter(pl.col("filial") == input.filial())
        nomes = eq.sort("cod_vendedor")["vendedor"].to_list()
        with reactive.isolate():
            atual = [v for v in input.vendedor() if v in nomes]
        ui.update_selectize("vendedor", choices=nomes, selected=atual)

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar():
        ui.update_select("filial", selected="")
        for campo in ("vendedor", "canal", "situacao"):
            ui.update_selectize(campo, selected=[])
        ui.update_text("busca", value="")

    @reactive.calc
    def filtrada() -> pl.DataFrame:
        df = base
        if input.filial():
            df = df.filter(pl.col("filial") == input.filial())
        if input.vendedor():
            df = df.filter(pl.col("vendedor").is_in(list(input.vendedor())))
        if input.canal():
            df = df.filter(pl.col("canal").is_in(list(input.canal())))
        if input.situacao():
            df = df.filter(pl.col("situacao").is_in(list(input.situacao())))
        texto = input.busca().strip().upper()
        if texto:
            df = df.filter(
                pl.col("cliente").str.contains(texto, literal=True)
                | pl.col("cod_cliente").cast(pl.String).str.starts_with(texto)
            )
        return df

    @render.ui
    def kpis():
        df = filtrada()
        contagem = dict(df.group_by("situacao").len().iter_rows())

        total = df.height or 1
        return linha_kpis(
            kpi("Clientes na carteira", numero(df.height)),
            *[
                kpi(s, numero(contagem.get(s, 0)), pct(contagem.get(s, 0) / total), _COR_SITUACAO[s])
                for s in dados.SITUACOES
            ],
            kpi(
                "Faturamento 12 meses",
                moeda(df["fat_12m"].sum(), 0),
                f"Markup {pct(df['fat_12m'].sum() / df['custo_12m'].sum() - 1 if df['custo_12m'].sum() else None)}",
            ),
        )

    def _exibir(df: pl.DataFrame) -> pl.DataFrame:
        return df.select(
            pl.col("cod_cliente").alias("Código"),
            pl.col("cliente").alias("Cliente"),
            pl.col("canal").alias("Canal"),
            pl.col("cidade").alias("Cidade"),
            pl.col("vendedor").alias("Vendedor"),
            pl.col("ultima_compra")
            .map_elements(lambda d: mes_curto(d) if d else "-", return_dtype=pl.String)
            .alias("Últ. compra"),
            pl.col("situacao").alias("Situação"),
            pl.col("meses_com_compra").alias("Meses c/ compra"),
            pl.col("hl_12m").map_elements(lambda v: numero(v, 1), return_dtype=pl.String).alias("HL 12m"),
            pl.col("fat_12m").map_elements(lambda v: moeda(v, 0), return_dtype=pl.String).alias("Fat. 12m"),
            pl.col("markup_12m").map_elements(pct, return_dtype=pl.String).alias("Markup 12m"),
            pl.col("saldo_markup_12m")
            .map_elements(lambda v: moeda(v, 0), return_dtype=pl.String)
            .alias("Saldo markup 12m"),
        )

    @render.data_frame
    def tabela():
        df = filtrada()
        estilos = [
            {
                "rows": df.with_row_index().filter(pl.col("situacao") == s)["index"].to_list(),
                "cols": [6],
                "style": {"color": cor, "font-weight": "700"},
            }
            for s, cor in _COR_SITUACAO.items()
        ]
        return render.DataGrid(
            _exibir(df),
            selection_mode="row",
            styles=estilos,
            width="100%",
            height="60vh",
            summary="Mostrando {start} a {end} de {total} clientes",
        )

    @reactive.calc
    def cliente_escolhido() -> dict | None:
        linhas = tabela.cell_selection()["rows"]
        if not linhas:
            return None
        return filtrada().row(linhas[0], named=True)

    @render.ui
    def historico():
        c = cliente_escolhido()
        if c is None:
            return ui.div("Nenhum cliente escolhido.", class_="legenda")
        h = dados.historico(c["cod_cliente"])
        return ui.div(
            ui.div(ui.strong(c["cliente"]), f" · {c['canal']} · {c['cidade']}", class_="legenda"),
            grafico(
                {
                    "tooltip": {"trigger": "axis", "valueFormatter": NUMERO_BR},
                    "grid": {"left": 45, "right": 15, "top": 25, "bottom": 30},
                    "xAxis": {"type": "category", "data": [mes_curto(m) for m in h["mes"]]},
                    "yAxis": eixo_valor("HL"),
                    "series": [
                        {
                            "type": "bar",
                            "name": "HL",
                            "data": [round(v, 2) for v in h["hl"]],
                            "itemStyle": {"color": cores.SERIES[0], "borderRadius": [4, 4, 0, 0]},
                        }
                    ],
                },
                altura="28vh",
            ),
        )

    @render.ui
    def por_canal():
        df = filtrada().group_by("canal").agg(pl.col("fat_12m").sum()).sort("fat_12m", descending=True)
        return grafico(
            {
                "tooltip": {"trigger": "item", "valueFormatter": MOEDA_BR},
                "legend": {"bottom": 0},
                "series": [
                    {
                        "type": "pie",
                        "radius": ["40%", "64%"],
                        "center": ["50%", "42%"],
                        "itemStyle": {"borderColor": "#fff", "borderWidth": 2},
                        "label": {
                            "formatter": "js:function (p) { return p.percent.toLocaleString('pt-BR', "
                            "{maximumFractionDigits: 1}) + '%'; }"
                        },
                        "data": [{"name": c, "value": round(v, 2)} for c, v in df.iter_rows()],
                    }
                ],
                "color": cores.SERIES,
            },
            altura="30vh",
        )

    @render.download_button(filename="carteira_clientes.csv")
    def exportar():
        arquivo = io.StringIO()
        req(not filtrada().is_empty())
        _exibir(filtrada()).write_csv(arquivo, separator=";")
        yield arquivo.getvalue().encode("utf-8-sig")
