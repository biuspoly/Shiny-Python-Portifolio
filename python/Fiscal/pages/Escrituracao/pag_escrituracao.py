"""Escrituração: o livro de entradas do mês por CFOP (NF-e e CT-e juntos) e o que ainda falta lançar."""

from __future__ import annotations

import pandas as pd
import polars as pl
from shiny import module, reactive, render, ui

from core import notas as n
from core.carregamento import com_carregamento
from core.cores import ALERTA
from core.numeros import moeda, numero, percentual
from core.tela import OPCOES_SELECTIZE, cartao, css_tabela, legenda, selo_etapa

DIAS_ALERTA = 5


def pag_escrituracao_ui():
    return com_carregamento(escrituracao_ui("escrituracao"))


def pag_escrituracao_server():
    escrituracao_server("escrituracao")


@module.ui
def escrituracao_ui():
    return ui.div(
        ui.card(
            ui.div(
                ui.div(
                    ui.input_selectize("mes", "Mês de emissão", choices={}, options=OPCOES_SELECTIZE),
                    class_="filtro-dv",
                ),
                class_="filtros-dv",
            )
        ),
        ui.output_ui("cartoes"),
        ui.card(
            ui.card_header("Livro de entradas por CFOP"),
            ui.div(ui.output_data_frame("livro"), class_="dv-tabela"),
            ui.tags.style(
                css_tabela("#escrituracao-livro", [70, 300, 70, 130, 130, 110, 110], chave=(4,), esquerda=(2,))
            ),
        ),
        ui.card(
            ui.card_header(ui.output_text("titulo_pendentes")),
            ui.div(ui.output_data_frame("pendentes"), class_="dv-tabela"),
            ui.tags.style(
                css_tabela("#escrituracao-pendentes", [60, 95, 75, 260, 80, 120, 105, 80], chave=(6,), esquerda=(4,))
            ),
            legenda(ui.span(class_="dv-legenda-alerta"), f"esperando há mais de {DIAS_ALERTA} dias"),
        ),
        class_="dv-modulo",
    )


@module.server
def escrituracao_server(input, output, session):
    @reactive.effect
    def _opcoes():
        meses = n.meses()
        ui.update_selectize("mes", choices=meses, selected=next(iter(meses)))

    @reactive.calc
    def documentos() -> pl.DataFrame:
        """NF-e e CT-e do mês numa tabela só, no formato do livro de entradas."""
        if not input.mes():
            return pl.DataFrame()
        nfe = (
            n.nfe()
            .filter(pl.col("MES") == input.mes())
            .select(
                pl.lit("NF-e").alias("DOC"),
                "EMISSAO",
                "NUMERO",
                "EMIT_NOME",
                "CFOP_ENTRADA",
                "NATUREZA",
                pl.col("V_NF").alias("VALOR"),
                "BASE_ICMS",
                "V_ICMS",
                "ETAPA",
                "ESCRITURADA_EM",
            )
        )
        cte = (
            n.cte()
            .filter(pl.col("MES") == input.mes())
            .select(
                pl.lit("CT-e").alias("DOC"),
                "EMISSAO",
                "NUMERO",
                "EMIT_NOME",
                "CFOP_ENTRADA",
                "NATUREZA",
                pl.col("V_PREST").alias("VALOR"),
                pl.col("V_PREST").alias("BASE_ICMS"),
                "V_ICMS",
                pl.col("ETAPA").replace(
                    {"Recebido": "Recebida", "Escriturado": "Escriturada", "Desacordo": "Recusada"}
                ),
                "ESCRITURADA_EM",
            )
        )
        return pl.concat([nfe, cte])

    @render.ui
    def cartoes():
        df = documentos()
        if df.height == 0:
            return None
        lancados = df.filter(pl.col("ETAPA") == "Escriturada")
        falta = df.filter(pl.col("ETAPA").is_in(["Recebida", "Manifestada"]))
        prazo = lancados.select((pl.col("ESCRITURADA_EM") - pl.col("EMISSAO")).dt.total_days().mean()).item()
        return ui.div(
            cartao("Documentos do mês", numero(df.height), moeda(df["VALOR"].sum(), 0)),
            cartao(
                "Escriturados",
                numero(lancados.height),
                f"{percentual(lancados.height / df.height)} dos documentos",
                "kpi-delta-pos",
                destaque=True,
            ),
            cartao(
                "Falta escriturar",
                numero(falta.height),
                moeda(falta["VALOR"].sum(), 0),
                "kpi-delta-neg" if falta.height else "kpi-delta-neutro",
            ),
            cartao(
                "ICMS nos lançados",
                moeda(lancados["V_ICMS"].sum(), 0),
                f"base de {moeda(lancados['BASE_ICMS'].sum(), 0)}",
            ),
            cartao("Prazo médio", f"{numero(prazo or 0, 1)} dias", "da emissão ao lançamento"),
            class_="dv-kpis",
        )

    @render.data_frame
    def livro():
        df = documentos()
        if df.height == 0:
            return None
        lancados = df.filter(pl.col("ETAPA") == "Escriturada")
        por_cfop = (
            lancados.group_by("CFOP_ENTRADA", "NATUREZA")
            .agg(pl.len().alias("DOCS"), pl.col("VALOR").sum(), pl.col("BASE_ICMS").sum(), pl.col("V_ICMS").sum())
            .sort("VALOR", descending=True)
        )
        total = lancados["VALOR"].sum() or 1.0
        linhas = [
            [
                r["CFOP_ENTRADA"],
                r["NATUREZA"],
                numero(r["DOCS"]),
                numero(r["VALOR"], 2),
                numero(r["BASE_ICMS"], 2),
                numero(r["V_ICMS"], 2),
                percentual(r["VALOR"] / total),
            ]
            for r in por_cfop.iter_rows(named=True)
        ]
        colunas = ["CFOP", "Natureza da entrada", "Docs", "Valor contábil", "Base ICMS", "ICMS", "Peso"]
        return render.DataTable(pd.DataFrame(linhas, columns=colunas), height=None, summary=False, filters=False)

    @reactive.calc
    def a_lancar() -> pl.DataFrame:
        df = documentos()
        if df.height == 0:
            return df
        return df.filter(pl.col("ETAPA").is_in(["Recebida", "Manifestada"])).sort("EMISSAO")

    @render.text
    def titulo_pendentes():
        return f"Falta escriturar ({numero(a_lancar().height)})"

    @render.data_frame
    def pendentes():
        df = a_lancar()
        if df.height == 0:
            return render.DataTable(pd.DataFrame({"": ["Tudo escriturado neste mês."]}))
        linhas, estilos = [], []
        for i, r in enumerate(df.iter_rows(named=True)):
            dias = n.dias_parado(r["EMISSAO"])
            linhas.append(
                [
                    r["DOC"],
                    r["EMISSAO"].strftime("%d/%m/%Y"),
                    str(r["NUMERO"]),
                    r["EMIT_NOME"],
                    r["CFOP_ENTRADA"],
                    numero(r["VALOR"], 2),
                    selo_etapa(r["ETAPA"]),
                    n.texto_dias(dias),
                ]
            )
            if dias > DIAS_ALERTA:
                estilos.append({"rows": [i], "cols": ["Esperando há"], "style": ALERTA})
        colunas = ["Doc.", "Emissão", "Número", "Emitente", "CFOP", "Valor", "Etapa", "Esperando há"]
        return render.DataTable(
            pd.DataFrame(linhas, columns=colunas), styles=estilos, height="400px", summary=False, filters=False
        )
