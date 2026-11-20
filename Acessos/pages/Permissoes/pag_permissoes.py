import polars as pl
from faicons import icon_svg
from shiny import module, reactive, render, ui

from core import cores
from core.dados import ler
from core.layout import cartao, filtros
from pages.Permissoes.Dados import dados_permissoes as dados


@module.ui
def permissoes_ui():
    areas = sorted(ler("usuarios")["area"].unique().to_list())
    return ui.div(
        filtros(
            ui.input_select("app", "App", list(cores.APPS)),
            ui.input_selectize("area", "Área", areas, multiple=True, options={"placeholder": "Todas"}),
            ui.input_switch("so_ativos", "Só pessoas ativas", value=True),
        ),
        ui.layout_columns(
            cartao(
                "Quem vê cada página",
                ui.output_data_frame("matriz"),
                ui.div("Clique numa pessoa para mudar o acesso dela.", class_="legenda"),
            ),
            cartao("Acesso da pessoa", ui.output_ui("formulario")),
            col_widths=(8, 4),
        ),
    )


@module.server
def permissoes_server(input, output, session):
    permissoes = reactive.value(ler("permissoes"))

    @reactive.calc
    def base() -> pl.DataFrame:
        return dados.matriz(input.app(), permissoes.get(), list(input.area()), input.so_ativos())

    @render.data_frame
    def matriz():
        df = base()
        colunas = dados.paginas(input.app())
        exibir = df.select(
            pl.col("nome").alias("Pessoa"),
            pl.col("papel").alias("Papel"),
            *[pl.when(pl.col(c)).then(pl.lit(dados.MARCA)).otherwise(pl.lit("")).alias(c) for c in colunas],
        )
        cor = cores.APPS[input.app()]
        estilos = [
            {
                "rows": linhas,
                "cols": [2 + i],
                "style": {"background-color": f"{cor}22", "color": cor, "font-weight": "700", "font-size": "1rem"},
            }
            for i, c in enumerate(colunas)
            if (linhas := df.with_row_index().filter(pl.col(c))["index"].to_list())
        ]
        return render.DataGrid(
            exibir,
            selection_mode="row",
            styles=estilos,
            width="100%",
            height="62vh",
            summary="Mostrando {start} a {end} de {total} pessoas",
        )

    @reactive.calc
    def pessoa() -> dict | None:
        linhas = matriz.cell_selection()["rows"]
        return base().row(linhas[0], named=True) if linhas else None

    @render.ui
    def formulario():
        p = pessoa()
        if p is None:
            return ui.div("Ninguém escolhido.", class_="legenda")
        colunas = dados.paginas(input.app())
        return ui.div(
            ui.div(ui.strong(p["nome"]), f" · {p['papel']}", class_="legenda"),
            ui.input_checkbox_group(
                "paginas", f"Páginas do {input.app()}", colunas, selected=[c for c in colunas if p[c]]
            ),
            ui.input_action_button("salvar", "Salvar", icon=icon_svg("floppy-disk"), class_="btn-cartao"),
            ui.div("Simulação: a mudança vale só para esta aba.", class_="legenda"),
        )

    @reactive.effect
    @reactive.event(input.salvar)
    def _salvar():
        p = pessoa()
        if p is None:
            return
        app = input.app()
        outras = permissoes.get().filter(~((pl.col("login") == p["login"]) & (pl.col("app") == app)))
        novas = pl.DataFrame(
            {"login": p["login"], "app": app, "pagina": list(input.paginas())},
            schema={"login": pl.String, "app": pl.String, "pagina": pl.String},
        )
        permissoes.set(pl.concat([outras, novas]))
        ui.notification_show(f"Acesso de {p['nome']} ao {app} salvo (simulação).", type="message")
