from datetime import timedelta

import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.dados import data_base, ler
from core.layout import cartao, filtros


@module.ui
def historico_ui():
    hoje = data_base()
    return ui.div(
        filtros(
            ui.input_date_range(
                "periodo",
                "Período",
                start=hoje - timedelta(days=90),
                end=hoje,
                format="dd/mm/yyyy",
                language="pt-BR",
                separator="até",
            ),
            ui.input_selectize("acao", "Ação", list(cores.ACOES), multiple=True, options={"placeholder": "Todas"}),
            ui.input_text("busca", "Pessoa", placeholder="Login de quem recebeu ou de quem fez"),
        ),
        cartao("Histórico de alterações de acesso", ui.output_data_frame("tabela")),
    )


@module.server
def historico_server(input, output, session):
    nomes = dict(ler("usuarios").select("login", "nome").iter_rows())

    @reactive.calc
    def base() -> pl.DataFrame:
        inicio, fim = input.periodo()
        df = ler("historico").filter(pl.col("momento").dt.date().is_between(inicio, fim))
        if input.acao():
            df = df.filter(pl.col("acao").is_in(list(input.acao())))
        texto = input.busca().strip().lower()
        if texto:
            df = df.filter(
                pl.col("login").str.contains(texto, literal=True)
                | pl.col("feito_por").str.contains(texto, literal=True)
            )
        return df

    @render.data_frame
    def tabela():
        df = base()
        idx = df.with_row_index()
        estilos = [
            {"rows": linhas, "cols": [1], "style": {"color": cor, "font-weight": "700"}}
            for a, cor in cores.ACOES.items()
            if (linhas := idx.filter(pl.col("acao") == a)["index"].to_list())
        ]
        return render.DataGrid(
            pl.DataFrame(
                {
                    "Quando": [d.strftime("%d/%m/%Y %H:%M") for d in df["momento"]],
                    "Ação": df["acao"],
                    "Pessoa": [nomes.get(x, x) for x in df["login"]],
                    "App": df["app"],
                    "Página": df["pagina"],
                    "Feito por": [nomes.get(x, x) for x in df["feito_por"]],
                }
            ),
            styles=estilos,
            width="100%",
            height="68vh",
            summary="Mostrando {start} a {end} de {total} alterações",
        )
