"""Markup por produto (versão enxuta da tela de produção, com dados fictícios).

Responde, para o mês escolhido: quanto se faturou, quanto aquilo custou (CMV), qual foi o markup real e
quanto se teria ganho seguindo o markup sugerido de cada produto. O vermelho marca quem vendeu abaixo dele.
"""

from __future__ import annotations

import pandas as pd
from faicons import icon_svg
from shiny import module, reactive, render, ui

from core.carregamento import com_carregamento
from core.numeros import moeda, numero, percentual
from pages.Diario_Venda.Dados.cores_diario_venda import COR_ALERTA, label_mes_str

from .Dados import dados_markup as d

_ALERTA = {"color": COR_ALERTA, "font-weight": "600"}
_COLUNAS = [
    ("PRODUTO", "Produto"),
    ("MARCA", "Marca"),
    ("QTD", "Qtd.\n(cx)"),
    ("FAT", "Faturamento"),
    ("PESO", "Peso no\nfaturamento"),
    ("CMV", "CMV"),
    ("PRECO_REAL", "Preço\nreal"),
    ("PRECO_SUG", "Preço\nsugerido"),
    ("PCT_MKP", "% Markup\nreal"),
    ("PCT_SUG", "% Markup\nsugerido"),
    ("SALDO", "Saldo\n(real - sugerido)"),
]
# Largura de cada coluna (px), na ordem acima: sem isto a grade dá a mesma largura a todas e corta o fim.
_LARGURAS = [230, 90, 70, 110, 90, 110, 80, 80, 90, 90, 120]
_COLUNAS_CHAVE = ("PCT_MKP", "SALDO")


def pag_markup_ui():
    return com_carregamento(markup_ui("markup"))


def pag_markup_server():
    markup_server("markup")


@module.ui
def markup_ui():
    opcoes = {"dropdownParent": "body", "dropdownClass": "selectize-dropdown dv-selectize-dropdown"}
    return ui.div(
        ui.card(
            ui.div(
                ui.div(ui.input_selectize("mes", "Mês", choices={}, options=opcoes), class_="filtro-dv"),
                ui.div(
                    ui.input_selectize(
                        "marca",
                        "Marca",
                        choices=[],
                        multiple=True,
                        options={**opcoes, "placeholder": "Todas", "plugins": ["remove_button"]},
                    ),
                    class_="filtro-dv",
                ),
                ui.input_action_button(
                    "limpar", None, icon=icon_svg("eraser", a11y="deco"), class_="btn-primary btn-limpar-dv"
                ),
                class_="filtros-dv",
            ),
        ),
        ui.output_ui("cartoes"),
        ui.card(
            ui.card_header("Markup por produto"),
            ui.div(ui.output_data_frame("tabela"), class_="dv-tabela"),
            ui.tags.style(_css_tabela()),
            ui.div(
                ui.span(class_="dv-legenda-alerta"),
                "vendeu abaixo do markup sugerido",
                ui.span(class_="dv-legenda-chave"),
                "colunas principais",
                ui.span(
                    "markup = faturamento ÷ CMV − 1; o sugerido usa o mesmo CMV, para os dois serem comparáveis",
                    class_="dv-legenda-dica",
                ),
                class_="dv-legenda",
            ),
        ),
        class_="dv-modulo",
    )


def _css_tabela() -> str:
    seletor = "#markup-tabela"
    chave = [i for i, (c, _) in enumerate(_COLUNAS, start=1) if c in _COLUNAS_CHAVE]
    regras = [
        ", ".join(f"{seletor} table thead th:nth-child({i})" for i in chave)
        + " { background-color: #E6F0FA !important; color: #0B4A85 !important; }",
        ", ".join(f"{seletor} table tbody td:nth-child({i})" for i in chave) + " { background-color: #F5F9FD; }",
        *[
            f"{seletor} table th:nth-child({i}), {seletor} table td:nth-child({i}) {{ width: {px}px !important; }}"
            for i, px in enumerate(_LARGURAS, start=1)
        ],
    ]
    return "\n".join(regras)


def _cartao(titulo, valor, sub=None, classe_sub="kpi-delta-neutro", destaque=False):
    return ui.div(
        ui.div(titulo, class_="dv-kpi-titulo"),
        ui.div(valor, class_="dv-kpi-valor"),
        ui.span(sub or "", class_=f"kpi-delta {classe_sub}"),
        class_="dv-kpi dv-kpi-destaque" if destaque else "dv-kpi",
    )


@module.server
def markup_server(input, output, session):
    @reactive.effect
    def _opcoes():
        meses = d.meses()
        ui.update_selectize("mes", choices={m: label_mes_str(m) for m in meses}, selected=meses[0])
        ui.update_selectize("marca", choices=d.marcas(), selected=[])

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar():
        ui.update_selectize("mes", selected=d.meses()[0])
        ui.update_selectize("marca", selected=[])

    @reactive.calc
    def recorte():
        if not input.mes():
            return None
        return d.filtrar(input.mes(), list(input.marca() or []))

    @render.ui
    def cartoes():
        df = recorte()
        if df is None or df.height == 0:
            return None
        r = d.resumo(df)
        abaixo = r["PCT_MKP"] is not None and r["PCT_SUG"] is not None and r["PCT_MKP"] < r["PCT_SUG"]
        return ui.div(
            _cartao("Faturamento", moeda(r["FAT"], 0), f"{numero(r['QTD'])} caixas"),
            _cartao("CMV", moeda(r["CMV"], 0), "custo do que foi vendido"),
            _cartao(
                "Markup real",
                percentual(r["PCT_MKP"]),
                f"{moeda(r['MKP'], 0)} sobre o CMV",
                "kpi-delta-neg" if abaixo else "kpi-delta-pos",
                destaque=True,
            ),
            _cartao("Markup sugerido", percentual(r["PCT_SUG"]), f"faturaria {moeda(r['FAT_SUG'], 0)}"),
            _cartao(
                "Saldo do markup",
                moeda(r["SALDO"], 0),
                "abaixo do sugerido" if r["SALDO"] < 0 else "acima do sugerido",
                "kpi-delta-neg" if r["SALDO"] < 0 else "kpi-delta-pos",
            ),
            class_="dv-kpis",
        )

    @render.data_frame
    def tabela():
        df = recorte()
        if df is None or df.height == 0:
            return render.DataTable(pd.DataFrame())
        prod = d.por_produto(df)
        linhas, estilos = [], []
        for i, p in enumerate(prod.iter_rows(named=True)):
            linhas.append(
                {
                    "PRODUTO": p["PRODUTO"],
                    "MARCA": p["MARCA"],
                    "QTD": numero(p["QTD"]),
                    "FAT": numero(p["FAT"], 2),
                    "PESO": percentual(p["PESO"]),
                    "CMV": numero(p["CMV"], 2),
                    "PRECO_REAL": numero(p["PRECO_REAL"], 2),
                    "PRECO_SUG": numero(p["PRECO_SUG"], 2),
                    "PCT_MKP": percentual(p["PCT_MKP"]),
                    "PCT_SUG": percentual(p["PCT_SUG"]),
                    "SALDO": numero(p["SALDO"], 2),
                }
            )
            if p["SALDO"] < 0:
                rotulos = dict(_COLUNAS)
                estilos.append({"rows": [i], "cols": [rotulos["PCT_MKP"], rotulos["SALDO"]], "style": _ALERTA})
        tabela_pd = pd.DataFrame(linhas, columns=[c for c, _ in _COLUNAS]).rename(columns=dict(_COLUNAS))
        return render.DataTable(tabela_pd, styles=estilos, height="560px", summary=False, filters=False)
