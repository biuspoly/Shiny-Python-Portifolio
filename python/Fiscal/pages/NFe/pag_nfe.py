"""NF-e recebidas: a lista com a etapa de cada nota e, ao escolher uma, os itens e o XML."""

from __future__ import annotations

import pandas as pd
import polars as pl
from faicons import icon_svg
from shiny import module, reactive, render, ui

from core import notas as n
from core.carregamento import com_carregamento
from core.cores import ALERTA
from core.numeros import moeda, numero
from core.tela import OPCOES_MULTIPLO, OPCOES_SELECTIZE, cartao, css_tabela, legenda, selo_etapa

DIAS_ALERTA = 5
_PENDENTES = ("Recebida", "Manifestada")
_COLUNAS = [
    "Emissão",
    "Número",
    "Emitente",
    "UF",
    "Tipo",
    "CFOP entrada",
    "Valor",
    "Manifestação",
    "Etapa",
    "Parada há",
]
_LARGURAS = [95, 75, 250, 40, 150, 80, 110, 170, 105, 80]


def pag_nfe_ui():
    return com_carregamento(nfe_ui("nfe"))


def pag_nfe_server():
    nfe_server("nfe")


@module.ui
def nfe_ui():
    return ui.div(
        ui.card(
            ui.div(
                ui.div(
                    ui.input_selectize("mes", "Mês de emissão", choices={}, options=OPCOES_SELECTIZE),
                    class_="filtro-dv",
                ),
                ui.div(
                    ui.input_selectize("tipo", "Tipo", [], multiple=True, options=OPCOES_MULTIPLO), class_="filtro-dv"
                ),
                ui.div(
                    ui.input_selectize("etapa", "Etapa", [], multiple=True, options=OPCOES_MULTIPLO), class_="filtro-dv"
                ),
                ui.div(
                    ui.input_text("busca", "Procurar", placeholder="número, chave ou emitente"),
                    class_="filtro-dv filtro-dv-largo",
                ),
                class_="filtros-dv",
            ),
            ui.tags.style(".dv-modulo .filtros-dv .filtro-dv-largo { grid-column: span 2; }"),
        ),
        ui.output_ui("cartoes"),
        ui.card(
            ui.card_header(ui.output_text("titulo")),
            ui.div(ui.output_data_frame("tabela"), class_="dv-tabela"),
            ui.tags.style(css_tabela("#nfe-tabela", _LARGURAS, chave=(7, 9), esquerda=(3, 5, 8))),
            legenda(
                ui.span(class_="dv-legenda-alerta"),
                f"pendente há mais de {DIAS_ALERTA} dias",
                ui.span("escolha uma linha para ver os itens e o XML", class_="dv-legenda-dica"),
            ),
        ),
        ui.output_ui("detalhe"),
        class_="dv-modulo",
    )


@module.server
def nfe_server(input, output, session):
    @reactive.effect
    def _opcoes():
        meses = n.meses()
        ui.update_selectize("mes", choices=meses, selected=next(iter(meses)))
        ui.update_selectize("tipo", choices=sorted(n.nfe()["TIPO"].unique().to_list()), selected=[])
        ui.update_selectize("etapa", choices=["Recebida", "Manifestada", "Escriturada", "Recusada"], selected=[])

    @reactive.calc
    def recorte() -> pl.DataFrame:
        df = n.nfe()
        if input.mes():
            df = df.filter(pl.col("MES") == input.mes())
        if input.tipo():
            df = df.filter(pl.col("TIPO").is_in(list(input.tipo())))
        if input.etapa():
            df = df.filter(pl.col("ETAPA").is_in(list(input.etapa())))
        busca = (input.busca() or "").strip().upper()
        if busca:
            df = df.filter(
                pl.col("CHAVE").str.contains(busca, literal=True)
                | pl.col("NUMERO").cast(pl.String).str.contains(busca, literal=True)
                | pl.col("EMIT_NOME").str.contains(busca, literal=True)
            )
        return df.sort("EMISSAO", descending=True)

    @render.ui
    def cartoes():
        df = recorte()
        pendentes = df.filter(pl.col("ETAPA").is_in(_PENDENTES))
        return ui.div(
            cartao("Notas", numero(df.height), moeda(df["V_NF"].sum(), 0)),
            cartao("Valor dos produtos", moeda(df["V_PROD"].sum(), 0), f"{numero(df['N_ITENS'].sum())} itens"),
            cartao("ICMS destacado", moeda(df["V_ICMS"].sum(), 0), f"ST: {moeda(df['V_ST'].sum(), 0)}"),
            cartao(
                "Pendentes",
                numero(pendentes.height),
                moeda(pendentes["V_NF"].sum(), 0),
                "kpi-delta-neg" if pendentes.height else "kpi-delta-neutro",
                destaque=True,
            ),
            class_="dv-kpis",
        )

    @render.text
    def titulo():
        return f"NF-e recebidas ({numero(recorte().height)})"

    @render.data_frame
    def tabela():
        df = recorte()
        linhas, estilos = [], []
        for i, r in enumerate(df.iter_rows(named=True)):
            dias = n.dias_parado(r["EMISSAO"]) if r["ETAPA"] in _PENDENTES else None
            linhas.append(
                [
                    r["EMISSAO"].strftime("%d/%m/%Y"),
                    str(r["NUMERO"]),
                    r["EMIT_NOME"],
                    r["EMIT_UF"],
                    r["TIPO"],
                    r["CFOP_ENTRADA"],
                    numero(r["V_NF"], 2),
                    r["MANIFESTACAO"],
                    selo_etapa(r["ETAPA"]),
                    n.texto_dias(dias) if dias is not None else "",
                ]
            )
            if dias is not None and dias > DIAS_ALERTA:
                estilos.append({"rows": [i], "cols": ["Parada há"], "style": ALERTA})
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
        r = n.nfe().filter(pl.col("CHAVE") == chave).row(0, named=True)
        campos = [
            ("Emitente", f"{r['EMIT_NOME']} · {n.cnpj_formatado(r['EMIT_CNPJ'])}"),
            ("Origem", f"{r['EMIT_MUNICIPIO']}/{r['EMIT_UF']}"),
            ("Emissão", r["EMISSAO"].strftime("%d/%m/%Y %H:%M")),
            ("Natureza da entrada", f"{r['CFOP_ENTRADA']} · {r['NATUREZA']}"),
            ("Manifestação", r["MANIFESTACAO"]),
            ("Escriturada em", r["ESCRITURADA_EM"].strftime("%d/%m/%Y") if r["ESCRITURADA_EM"] else "—"),
            ("Valor da nota", moeda(r["V_NF"])),
            ("ICMS / ST", f"{moeda(r['V_ICMS'])} / {moeda(r['V_ST'])}"),
        ]
        return ui.card(
            ui.card_header(ui.span(f"NF-e {r['NUMERO']} · série {r['SERIE']}  "), selo_etapa(r["ETAPA"])),
            ui.div(
                ui.span("Chave de acesso: "), ui.span(n.chave_formatada(chave), class_="fs-chave"), class_="fs-dica"
            ),
            ui.div(*[ui.div(ui.tags.b(rotulo), valor) for rotulo, valor in campos], class_="fs-detalhe"),
            ui.div(
                ui.input_action_button(
                    "ver_xml", "Ver XML", icon=icon_svg("code"), class_="btn-sm btn-outline-primary"
                ),
                ui.download_button(
                    "baixar_xml", "Baixar XML", icon=icon_svg("download"), class_="btn-sm btn-outline-primary"
                ),
                class_="fs-acoes",
            ),
            ui.div(ui.output_data_frame("itens"), class_="dv-tabela"),
            ui.tags.style(
                css_tabela("#nfe-itens", [60, 280, 90, 55, 55, 80, 100, 110, 90, 90], chave=(8,), esquerda=(2,))
            ),
        )

    @render.data_frame
    def itens():
        chave = chave_escolhida()
        if chave is None:
            return None
        df = n.itens().filter(pl.col("CHAVE") == chave).sort("N_ITEM")
        tabela_itens = pd.DataFrame(
            [
                [
                    i["CODIGO"],
                    i["DESCRICAO"],
                    i["NCM"],
                    i["CFOP"],
                    i["UNIDADE"],
                    numero(i["QTD"]),
                    numero(i["V_UNIT"], 2),
                    numero(i["V_PROD"], 2),
                    numero(i["V_ICMS"], 2),
                    numero(i["V_ST"], 2),
                ]
                for i in df.iter_rows(named=True)
            ],
            columns=["Código", "Produto", "NCM", "CFOP", "Un.", "Qtd.", "V. unit.", "V. produtos", "ICMS", "ICMS ST"],
        )
        return render.DataTable(tabela_itens, height=None, summary=False, filters=False)

    @reactive.effect
    @reactive.event(input.ver_xml)
    def _ver_xml():
        chave = chave_escolhida()
        if chave is None:
            return
        ui.modal_show(
            ui.modal(
                ui.tags.pre(n.xml_indentado(n.xml_nfe(chave)), class_="fs-xml"),
                title=f"XML da NF-e {chave}",
                size="xl",
                easy_close=True,
                footer=ui.modal_button("Fechar"),
            )
        )

    @render.download(filename=lambda: f"NFe{chave_escolhida()}.xml")
    def baixar_xml():
        yield n.xml_nfe(chave_escolhida())
