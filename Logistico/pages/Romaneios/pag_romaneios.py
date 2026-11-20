from datetime import date

import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.dados import ler
from core.formato import moeda, numero, pct
from core.layout import cartao, filtros, kpi, linha_kpis
from pages.Romaneios.Dados import dados_romaneios as dados

_COR_STATUS = {
    "Entregue": cores.POSITIVO,
    "Pendente": cores.ALERTA,
    "Devolvida": cores.NEGATIVO,
    "Devolvida parcial": cores.NEGATIVO,
}


@module.ui
def romaneios_ui():
    dias = dados.datas()
    filiais = sorted(ler("entregas")["filial"].unique().to_list())
    return ui.div(
        filtros(
            ui.input_date(
                "dia", "Data", value=dias[0], min=dias[-1], max=dias[0], format="dd/mm/yyyy", language="pt-BR"
            ),
            ui.input_select("filial", "Filial", {"": "Todas", **{f: f for f in filiais}}),
        ),
        ui.output_ui("kpis"),
        ui.layout_columns(
            cartao(
                "Romaneios do dia",
                ui.output_data_frame("tabela"),
                ui.div("Clique num romaneio para ver as notas dele.", class_="legenda"),
            ),
            cartao("Notas do romaneio", ui.output_ui("titulo_notas"), ui.output_data_frame("notas")),
            col_widths=(7, 5),
        ),
    )


@module.server
def romaneios_server(input, output, session):
    @reactive.calc
    def dia() -> date:
        return input.dia() or dados.datas()[0]

    @reactive.calc
    def do_dia() -> pl.DataFrame:
        return dados.entregas(dia(), input.filial() or None)

    @reactive.calc
    def romaneios() -> pl.DataFrame:
        return dados.por_romaneio(do_dia())

    @render.ui
    def kpis():
        df = do_dia()
        if df.is_empty():
            return ui.div("Sem romaneios nesta data.", class_="legenda")
        entregues = (df["status"] == "Entregue").sum()
        pendentes = (df["status"] == "Pendente").sum()
        atrasadas = dados.pendentes_anteriores(dia(), input.filial() or None).height
        return linha_kpis(
            kpi("Romaneios", numero(df["romaneio"].n_unique()), f"{numero(df['placa'].n_unique())} veículos na rua"),
            kpi("Entregas", numero(df.height), moeda(df["valor"].sum(), 0)),
            kpi("Entregues", pct(entregues / df.height), f"{numero(entregues)} notas", cores.POSITIVO),
            kpi("Pendentes", numero(pendentes), f"+ {numero(atrasadas)} de dias anteriores", cores.ALERTA),
            kpi(
                "Devolvido",
                moeda(df["valor_devolvido"].sum(), 0),
                pct(df["valor_devolvido"].sum() / df["valor"].sum()) + " do valor",
                cores.NEGATIVO,
            ),
        )

    @render.data_frame
    def tabela():
        r = romaneios()
        exibir = pl.DataFrame(
            {
                "Romaneio": r["romaneio"].cast(pl.String),
                "Placa": r["placa"],
                "Motorista": r["motorista"],
                "Entregas": r["entregas"].cast(pl.String),
                "Entregues": r["entregues"].cast(pl.String),
                "Pendentes": r["pendentes"].cast(pl.String),
                "Devolvidas": r["devolvidas"].cast(pl.String),
                "Valor": [moeda(v, 0) for v in r["valor"]],
                "Concluído": [pct(v, 0) for v in r["concluido"]],
            }
        )
        idx = r.with_row_index()
        estilos = []
        for linhas, cor in (
            (idx.filter(pl.col("concluido") < 0.5)["index"].to_list(), cores.NEGATIVO),
            (idx.filter(pl.col("concluido").is_between(0.5, 0.999))["index"].to_list(), cores.ALERTA),
            (idx.filter(pl.col("concluido") >= 0.999)["index"].to_list(), cores.POSITIVO),
        ):
            if linhas:
                estilos.append({"rows": linhas, "cols": [8], "style": {"color": cor, "font-weight": "700"}})
        return render.DataGrid(
            exibir,
            selection_mode="row",
            styles=estilos,
            width="100%",
            height="58vh",
            summary="Mostrando {start} a {end} de {total} romaneios",
        )

    @reactive.calc
    def romaneio_escolhido() -> int | None:
        linhas = tabela.cell_selection()["rows"]
        return romaneios()["romaneio"][linhas[0]] if linhas else None

    @render.ui
    def titulo_notas():
        num = romaneio_escolhido()
        if num is None:
            return ui.div("Nenhum romaneio escolhido.", class_="legenda")
        linha = romaneios().filter(pl.col("romaneio") == num).row(0, named=True)
        return ui.div(ui.strong(f"Romaneio {num}"), f" · {linha['placa']} · {linha['motorista']}", class_="legenda")

    @render.data_frame
    def notas():
        num = romaneio_escolhido()
        df = do_dia().filter(pl.col("romaneio") == num) if num else do_dia().head(0)
        exibir = pl.DataFrame(
            {
                "Nota": df["nota"].cast(pl.String),
                "Cliente": df["cliente"],
                "Cidade": df["cidade"],
                "Valor": [moeda(v) for v in df["valor"]],
                "Status": df["status"],
                "Motivo": df["motivo"].fill_null(""),
            }
        )
        idx = df.with_row_index()
        estilos = [
            {"rows": linhas, "cols": [4], "style": {"color": cor, "font-weight": "700"}}
            for s, cor in _COR_STATUS.items()
            if (linhas := idx.filter(pl.col("status") == s)["index"].to_list())
        ]
        return render.DataGrid(exibir, styles=estilos, width="100%", height="54vh", summary=False)
