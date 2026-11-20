import polars as pl
from faicons import icon_svg
from shiny import module, reactive, render, ui

from core import cores
from core.formato import moeda, numero
from core.layout import cartao, filtros, kpi, linha_kpis
from pages.Manifestacao.Dados import dados_manifestacao as dados

_COR = {
    "Sem manifestação": cores.NEGATIVO,
    "Ciência": cores.ALERTA,
    "Confirmada": cores.POSITIVO,
    "Desconhecida": cores.NEUTRO,
    "Não realizada": cores.NEUTRO,
}


@module.ui
def manifestacao_ui():
    return ui.div(
        filtros(
            ui.input_selectize(
                "situacao",
                "Manifestação",
                dados.SITUACOES,
                multiple=True,
                selected=["Sem manifestação", "Ciência"],
                options={"placeholder": "Todas"},
            ),
            ui.input_text("busca", "Emitente", placeholder="Nome ou número da nota"),
        ),
        ui.output_ui("kpis"),
        cartao(
            "NF-e para manifestar",
            ui.output_data_frame("tabela"),
            ui.div(
                ui.input_action_button("confirmar", "Confirmar operação", icon=icon_svg("check"), class_="btn-cartao"),
                ui.input_action_button("desconhecer", "Desconhecer", icon=icon_svg("xmark"), class_="btn-cartao"),
                ui.span(
                    "Simulação: escolha notas na tabela (Ctrl/Shift para várias). Nada é enviado à SEFAZ, "
                    "e a escolha vale só para esta aba.",
                    class_="legenda",
                ),
                class_="acoes-tabela",
            ),
        ),
    )


@module.server
def manifestacao_server(input, output, session):
    base = dados.nfe_recebidas()
    # Manifestações feitas nesta aba: chave -> nova situação.
    feitas = reactive.value({})

    @reactive.calc
    def atual() -> pl.DataFrame:
        mudancas = feitas.get()
        if not mudancas:
            return base
        return base.with_columns(
            pl.col("chave").replace_strict(mudancas, default=pl.col("manifestacao")).alias("manifestacao")
        )

    @reactive.calc
    def filtrada() -> pl.DataFrame:
        df = atual()
        if input.situacao():
            df = df.filter(pl.col("manifestacao").is_in(list(input.situacao())))
        texto = input.busca().strip().upper()
        if texto:
            df = df.filter(
                pl.col("emitente").str.contains(texto, literal=True)
                | pl.col("numero").cast(pl.String).str.starts_with(texto)
            )
        return df

    def _manifestar(situacao: str) -> None:
        linhas = tabela.cell_selection()["rows"]
        if not linhas:
            ui.notification_show("Escolha ao menos uma nota na tabela.", type="warning")
            return
        chaves = [filtrada()["chave"][i] for i in linhas]
        feitas.set({**feitas.get(), **{c: situacao for c in chaves}})
        ui.notification_show(f"{len(chaves)} nota(s): {situacao.lower()} (simulação).", type="message")

    @reactive.effect
    @reactive.event(input.confirmar)
    def _confirmar():
        _manifestar("Confirmada")

    @reactive.effect
    @reactive.event(input.desconhecer)
    def _desconhecer():
        _manifestar("Desconhecida")

    @render.ui
    def kpis():
        df = atual()
        pendentes = df.filter(pl.col("manifestacao").is_in(["Sem manifestação", "Ciência"]))
        urgentes = pendentes.filter(pl.col("dias_restantes") <= 30)
        return linha_kpis(
            kpi(
                "Sem manifestação",
                numero((df["manifestacao"] == "Sem manifestação").sum()),
                "",
                _COR["Sem manifestação"],
            ),
            kpi(
                "Só com ciência", numero((df["manifestacao"] == "Ciência").sum()), "falta a conclusiva", _COR["Ciência"]
            ),
            kpi("Valor pendente", moeda(pendentes["valor"].sum(), 0), f"{numero(pendentes.height)} notas"),
            kpi(
                "Prazo em 30 dias",
                numero(urgentes.height),
                f"de {dados.PRAZO_DIAS} dias da emissão",
                cores.NEGATIVO if urgentes.height else None,
            ),
            kpi("Confirmadas", numero((df["manifestacao"] == "Confirmada").sum()), "", _COR["Confirmada"]),
        )

    @render.data_frame
    def tabela():
        df = filtrada()
        idx = df.with_row_index()
        estilos = [
            {"rows": linhas, "cols": [5], "style": {"color": cor, "font-weight": "700"}}
            for s, cor in _COR.items()
            if (linhas := idx.filter(pl.col("manifestacao") == s)["index"].to_list())
        ]
        return render.DataGrid(
            pl.DataFrame(
                {
                    "Número": df["numero"].cast(pl.String),
                    "Emitente": df["emitente"],
                    "Destinatário": df["destinatario"],
                    "Emissão": [d.strftime("%d/%m/%Y") for d in df["emissao"]],
                    "Valor": [moeda(v) for v in df["valor"]],
                    "Manifestação": df["manifestacao"],
                    "Prazo": [d.strftime("%d/%m/%Y") for d in df["prazo"]],
                    "Dias restantes": df["dias_restantes"].cast(pl.String),
                }
            ),
            selection_mode="rows",
            styles=estilos,
            width="100%",
            height="55vh",
            summary="Mostrando {start} a {end} de {total} notas",
        )
