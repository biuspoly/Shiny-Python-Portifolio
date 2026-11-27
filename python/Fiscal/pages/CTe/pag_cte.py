"""CT-e recebidos: o frete de cada carga e as NF-e que ele transporta."""

from __future__ import annotations

import pandas as pd
import polars as pl
from faicons import icon_svg
from shiny import module, reactive, render, ui

from core import notas as n
from core.carregamento import com_carregamento
from core.cores import ALERTA
from core.numeros import moeda, numero, percentual
from core.tela import OPCOES_MULTIPLO, OPCOES_SELECTIZE, cartao, css_tabela, legenda, selo_etapa

LIMITE_FRETE = 0.028  # frete acima de 2,8% do valor da carga fica em vermelho
_COLUNAS = [
    "Emissão",
    "Número",
    "Transportadora",
    "Trajeto",
    "NF-e",
    "Valor da carga",
    "Frete",
    "% frete",
    "ICMS",
    "Etapa",
]
_LARGURAS = [95, 75, 250, 170, 55, 120, 100, 75, 90, 105]


def pag_cte_ui():
    return com_carregamento(cte_ui("cte"))


def pag_cte_server():
    cte_server("cte")


@module.ui
def cte_ui():
    return ui.div(
        ui.card(
            ui.div(
                ui.div(
                    ui.input_selectize("mes", "Mês de emissão", choices={}, options=OPCOES_SELECTIZE),
                    class_="filtro-dv",
                ),
                ui.div(
                    ui.input_selectize("transportadora", "Transportadora", [], multiple=True, options=OPCOES_MULTIPLO),
                    class_="filtro-dv filtro-dv-largo",
                ),
                ui.div(
                    ui.input_selectize("etapa", "Etapa", [], multiple=True, options=OPCOES_MULTIPLO), class_="filtro-dv"
                ),
                class_="filtros-dv",
            ),
            ui.tags.style(".dv-modulo .filtros-dv .filtro-dv-largo { grid-column: span 2; }"),
        ),
        ui.output_ui("cartoes"),
        ui.card(
            ui.card_header(ui.output_text("titulo")),
            ui.div(ui.output_data_frame("tabela"), class_="dv-tabela"),
            ui.tags.style(css_tabela("#cte-tabela", _LARGURAS, chave=(7, 8), esquerda=(3, 4))),
            legenda(
                ui.span(class_="dv-legenda-alerta"),
                f"frete acima de {percentual(LIMITE_FRETE)} da carga",
                ui.span("escolha uma linha para ver as NF-e da carga e o XML", class_="dv-legenda-dica"),
            ),
        ),
        ui.output_ui("detalhe"),
        class_="dv-modulo",
    )


@module.server
def cte_server(input, output, session):
    @reactive.effect
    def _opcoes():
        meses = n.meses()
        ui.update_selectize("mes", choices=meses, selected=next(iter(meses)))
        ui.update_selectize("transportadora", choices=sorted(n.cte()["EMIT_NOME"].unique().to_list()), selected=[])
        ui.update_selectize("etapa", choices=["Recebido", "Escriturado", "Desacordo"], selected=[])

    @reactive.calc
    def recorte() -> pl.DataFrame:
        df = n.cte()
        if input.mes():
            df = df.filter(pl.col("MES") == input.mes())
        if input.transportadora():
            df = df.filter(pl.col("EMIT_NOME").is_in(list(input.transportadora())))
        if input.etapa():
            df = df.filter(pl.col("ETAPA").is_in(list(input.etapa())))
        return df.sort("EMISSAO", descending=True)

    @render.ui
    def cartoes():
        df = recorte()
        carga = df["V_CARGA"].sum()
        pct = df["V_PREST"].sum() / carga if carga else None
        return ui.div(
            cartao("CT-e", numero(df.height), f"{numero(df['N_NFE'].sum())} NF-e transportadas"),
            cartao("Frete", moeda(df["V_PREST"].sum(), 0), f"ICMS: {moeda(df['V_ICMS'].sum(), 0)}", destaque=True),
            cartao(
                "Frete sobre a carga",
                percentual(pct, 2),
                f"carga de {moeda(carga, 0)}",
                "kpi-delta-neg" if (pct or 0) > LIMITE_FRETE else "kpi-delta-neutro",
            ),
            cartao(
                "Desacordo",
                numero(df.filter(pl.col("ETAPA") == "Desacordo").height),
                "prestação de serviço em desacordo",
                "kpi-delta-neg" if df.filter(pl.col("ETAPA") == "Desacordo").height else "kpi-delta-neutro",
            ),
            class_="dv-kpis",
        )

    @render.text
    def titulo():
        return f"CT-e recebidos ({numero(recorte().height)})"

    @render.data_frame
    def tabela():
        linhas, estilos = [], []
        for i, c in enumerate(recorte().iter_rows(named=True)):
            pct = c["V_PREST"] / c["V_CARGA"] if c["V_CARGA"] else None
            linhas.append(
                [
                    c["EMISSAO"].strftime("%d/%m/%Y"),
                    str(c["NUMERO"]),
                    c["EMIT_NOME"],
                    f"{c['ORIGEM']} → {c['DESTINO']}",
                    str(c["N_NFE"]),
                    numero(c["V_CARGA"], 2),
                    numero(c["V_PREST"], 2),
                    percentual(pct, 2),
                    numero(c["V_ICMS"], 2),
                    selo_etapa(c["ETAPA"]),
                ]
            )
            if (pct or 0) > LIMITE_FRETE:
                estilos.append({"rows": [i], "cols": ["% frete"], "style": ALERTA})
        return render.DataTable(
            pd.DataFrame(linhas, columns=_COLUNAS),
            styles=estilos,
            height="480px",
            selection_mode="row",
            summary=False,
            filters=False,
        )

    @reactive.calc
    def chave_escolhida() -> str | None:
        linhas = tabela.cell_selection()["rows"]
        df = recorte()
        if not linhas or linhas[0] >= df.height:
            return None
        return df["CHAVE"][linhas[0]]

    @render.ui
    def detalhe():
        chave = chave_escolhida()
        if chave is None:
            return None
        c = n.cte().filter(pl.col("CHAVE") == chave).row(0, named=True)
        return ui.card(
            ui.card_header(ui.span(f"CT-e {c['NUMERO']} · {c['EMIT_NOME']}  "), selo_etapa(c["ETAPA"])),
            ui.div(
                ui.span("Chave de acesso: "), ui.span(n.chave_formatada(chave), class_="fs-chave"), class_="fs-dica"
            ),
            ui.div(
                ui.input_action_button(
                    "ver_xml", "Ver XML", icon=icon_svg("code"), class_="btn-sm btn-outline-primary"
                ),
                ui.download_button(
                    "baixar_xml", "Baixar XML", icon=icon_svg("download"), class_="btn-sm btn-outline-primary"
                ),
                class_="fs-acoes",
            ),
            ui.div(ui.output_data_frame("notas_da_carga"), class_="dv-tabela"),
            ui.tags.style(css_tabela("#cte-notas_da_carga", [95, 75, 280, 120, 105], chave=(4,), esquerda=(3,))),
        )

    @render.data_frame
    def notas_da_carga():
        chave = chave_escolhida()
        if chave is None:
            return None
        chaves = n.cte_nfe().filter(pl.col("CHAVE_CTE") == chave)["CHAVE_NFE"].to_list()
        df = n.nfe().filter(pl.col("CHAVE").is_in(chaves)).sort("EMISSAO")
        return render.DataTable(
            pd.DataFrame(
                [
                    [
                        r["EMISSAO"].strftime("%d/%m/%Y"),
                        str(r["NUMERO"]),
                        r["EMIT_NOME"],
                        numero(r["V_NF"], 2),
                        selo_etapa(r["ETAPA"]),
                    ]
                    for r in df.iter_rows(named=True)
                ],
                columns=["Emissão", "NF-e", "Emitente", "Valor", "Etapa da NF-e"],
            ),
            height=None,
            summary=False,
            filters=False,
        )

    @reactive.effect
    @reactive.event(input.ver_xml)
    def _ver_xml():
        chave = chave_escolhida()
        if chave is None:
            return
        ui.modal_show(
            ui.modal(
                ui.tags.pre(n.xml_indentado(n.xml_cte(chave)), class_="fs-xml"),
                title=f"XML do CT-e {chave}",
                size="xl",
                easy_close=True,
                footer=ui.modal_button("Fechar"),
            )
        )

    @render.download(filename=lambda: f"CTe{chave_escolhida()}.xml")
    def baixar_xml():
        yield n.xml_cte(chave_escolhida())
