"""Clientes: a carteira, uma linha por cliente (versão enxuta da tela de produção, com dados fictícios)."""

from __future__ import annotations

from datetime import date

import pandas as pd
from faicons import icon_svg
from shiny import module, reactive, render, ui

from core.carregamento import com_carregamento
from core.numeros import moeda, numero, percentual
from pages.Diario_Venda.Dados.cores_diario_venda import COR_ALERTA, label_mes_str

from .Dados import dados_clientes as d

_ALERTA = {"color": COR_ALERTA, "font-weight": "600"}
_LIMIAR_DEVOLUCAO = 0.05  # devolução acima de 5% do faturamento fica em vermelho
_COLUNAS = [
    ("CODCLI", "Código"),
    ("CLIENTE", "Cliente"),
    ("VEN", "Vendedor"),
    ("CANAL", "Canal"),
    ("CIDADE", "Cidade"),
    ("FAT_MES", "Fat.\nmês"),
    ("DEV_MES", "Devol.\nmês"),
    ("FAT_12M", "Fat.\n12 meses"),
    ("DEV_12M", "Devol.\n12 meses"),
    ("PCT_MKP", "% Markup\n12 meses"),
    ("MESES", "Meses com\ncompra (de 12)"),
    ("ULTIMA", "Última\ncompra"),
]
_COLUNAS_CHAVE = ("FAT_MES", "FAT_12M")
# Largura de cada coluna (px), na ordem acima: sem isto a grade dá a mesma largura a todas e corta o fim.
_LARGURAS = [70, 220, 75, 100, 150, 100, 85, 110, 95, 85, 95, 90]
_A_ESQUERDA = (2, 5)  # Cliente e Cidade


def pag_clientes_ui():
    return com_carregamento(clientes_ui("clientes"))


def pag_clientes_server():
    clientes_server("clientes")


@module.ui
def clientes_ui():
    opcoes = {"dropdownParent": "body", "dropdownClass": "selectize-dropdown dv-selectize-dropdown"}
    multiplo = {**opcoes, "placeholder": "Todos", "plugins": ["remove_button"]}
    return ui.div(
        ui.card(
            ui.div(
                ui.div(ui.input_selectize("ven", "Vendedor", [], multiple=True, options=multiplo), class_="filtro-dv"),
                ui.div(ui.input_selectize("canal", "Canal", [], multiple=True, options=multiplo), class_="filtro-dv"),
                ui.div(ui.input_selectize("cidade", "Cidade", [], multiple=True, options=multiplo), class_="filtro-dv"),
                ui.div(
                    ui.input_selectize("situacao", "Situação", d.SITUACOES, selected="todos", options=opcoes),
                    class_="filtro-dv filtro-dv-largo",
                ),
                ui.div(
                    ui.input_text("busca", "Cliente", placeholder="código ou nome"), class_="filtro-dv filtro-dv-largo"
                ),
                ui.input_action_button(
                    "limpar", None, icon=icon_svg("eraser", a11y="deco"), class_="btn-primary btn-limpar-dv"
                ),
                class_="filtros-dv",
            ),
        ),
        ui.output_ui("cartoes"),
        ui.card(
            ui.card_header(ui.output_text("titulo_tabela")),
            ui.div(ui.output_data_frame("tabela"), class_="dv-tabela"),
            ui.tags.style(_css_tabela()),
            ui.div(
                ui.span(class_="dv-legenda-alerta"),
                f"devolução acima de {percentual(_LIMIAR_DEVOLUCAO, 0)} do faturamento, ou ativo parado há "
                f"{d.DIAS_PARADO}+ dias",
                ui.span(class_="dv-legenda-chave"),
                "faturamento do mês e de 12 meses",
                class_="dv-legenda",
            ),
        ),
        class_="dv-modulo",
    )


def _css_tabela() -> str:
    seletor = "#clientes-tabela"
    chave = [i for i, (c, _) in enumerate(_COLUNAS, start=1) if c in _COLUNAS_CHAVE]
    return "\n".join(
        [
            ", ".join(f"{seletor} table thead th:nth-child({i})" for i in chave)
            + " { background-color: #E6F0FA !important; color: #0B4A85 !important; }",
            ", ".join(f"{seletor} table tbody td:nth-child({i})" for i in chave) + " { background-color: #F5F9FD; }",
            *[
                f"{seletor} table th:nth-child({i}), {seletor} table td:nth-child({i}) {{ width: {px}px !important; }}"
                for i, px in enumerate(_LARGURAS, start=1)
            ],
            ", ".join(f"{seletor} table th:nth-child({i}), {seletor} table td:nth-child({i})" for i in _A_ESQUERDA)
            + " { text-align: left !important; }",
            ".dv-modulo .filtros-dv .filtro-dv-largo { grid-column: span 2; }",
        ]
    )


def _cartao(titulo, valor, sub=None, classe_sub="kpi-delta-neutro", destaque=False):
    return ui.div(
        ui.div(titulo, class_="dv-kpi-titulo"),
        ui.div(valor, class_="dv-kpi-valor"),
        ui.span(sub or "", class_=f"kpi-delta {classe_sub}"),
        class_="dv-kpi dv-kpi-destaque" if destaque else "dv-kpi",
    )


@module.server
def clientes_server(input, output, session):
    @reactive.effect
    def _opcoes():
        ui.update_selectize("ven", choices=d.opcoes("VEN"), selected=[])
        ui.update_selectize("canal", choices=d.opcoes("CANAL"), selected=[])
        ui.update_selectize("cidade", choices=d.opcoes("CIDADE"), selected=[])

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar():
        for campo in ("ven", "canal", "cidade"):
            ui.update_selectize(campo, selected=[])
        ui.update_selectize("situacao", selected="todos")
        ui.update_text("busca", value="")

    @reactive.calc
    def recorte():
        return d.filtrar(input.ven(), input.canal(), input.cidade(), input.situacao() or "todos", input.busca())

    @render.ui
    def cartoes():
        df = recorte()
        r = d.resumo(df)
        rot_mes = label_mes_str(date.today().strftime("%Y%m"))
        return ui.div(
            _cartao("Clientes", numero(r["CLIENTES"]), f"{numero(r['ATIVOS'])} ativos"),
            _cartao(
                f"Faturamento {rot_mes}",
                moeda(r["FAT_MES"], 0),
                f"{numero(r['COMPRARAM_MES'])} clientes compraram",
                destaque=True,
            ),
            _cartao("Faturamento 12 meses", moeda(r["FAT_12M"], 0), f"{numero(r['COMPRARAM_12M'])} compraram"),
            _cartao(
                f"Devolução {rot_mes}",
                moeda(r["DEV_MES"], 0),
                f"{percentual(r['PCT_DEV_MES'], 2)} da venda bruta do mês",
                "kpi-delta-neg" if (r["PCT_DEV_MES"] or 0) > _LIMIAR_DEVOLUCAO else "kpi-delta-neutro",
            ),
            _cartao("Markup 12 meses", percentual(r["PCT_MKP_12M"]), f"{moeda(r['FAT_12M'] - r['CMV_12M'], 0)}"),
            _cartao(
                f"Ativos parados {d.DIAS_PARADO}+ dias",
                numero(r["PARADOS"]),
                f"{percentual(r['PCT_PARADOS'])} dos ativos",
                "kpi-delta-neg" if r["PARADOS"] else "kpi-delta-neutro",
            ),
            class_="dv-kpis",
        )

    @render.text
    def titulo_tabela():
        return f"Carteira de clientes ({numero(recorte().height)})"

    @render.data_frame
    def tabela():
        df = recorte()
        limite = d.resumo(df)["LIMITE_PARADO"]
        rotulos = dict(_COLUNAS)
        linhas, estilos = [], []
        for i, c in enumerate(df.iter_rows(named=True)):
            linhas.append(
                {
                    "CODCLI": str(c["CODCLI"]),
                    "CLIENTE": c["CLIENTE"],
                    "VEN": c["VEN"],
                    "CANAL": c["CANAL"],
                    "CIDADE": c["CIDADE"],
                    "FAT_MES": numero(c["FAT_MES"], 2) if c["FAT_MES"] else "",
                    "DEV_MES": numero(c["DEV_MES"], 2) if c["DEV_MES"] else "",
                    "FAT_12M": numero(c["FAT_12M"], 2) if c["FAT_12M"] else "",
                    "DEV_12M": numero(c["DEV_12M"], 2) if c["DEV_12M"] else "",
                    "PCT_MKP": percentual(c["FAT_12M"] / c["CMV_12M"] - 1) if c["CMV_12M"] else "",
                    "MESES": str(c["MESES_COMPRANDO"]),
                    "ULTIMA": c["ULTIMA_COMPRA"].strftime("%d/%m/%Y") if c["ULTIMA_COMPRA"] else "",
                }
            )
            for fat, dev in (("FAT_MES", "DEV_MES"), ("FAT_12M", "DEV_12M")):
                if c[fat] and c[dev] / (c[fat] + c[dev]) > _LIMIAR_DEVOLUCAO:
                    estilos.append({"rows": [i], "cols": [rotulos[dev]], "style": _ALERTA})
            if c["ATIVO"] and c["ULTIMA_COMPRA"] and c["ULTIMA_COMPRA"] < limite:
                estilos.append({"rows": [i], "cols": [rotulos["ULTIMA"]], "style": _ALERTA})
        tabela_pd = pd.DataFrame(linhas, columns=[c for c, _ in _COLUNAS]).rename(columns=rotulos)
        return render.DataTable(tabela_pd, styles=estilos, height="600px", summary=False, filters=False)
