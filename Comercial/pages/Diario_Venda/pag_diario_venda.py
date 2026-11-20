from datetime import date

import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.dados import data_base, ler
from core.formato import mes_curto, moeda, numero, pct
from core.graficos import NUMERO_BR, eixo_valor, grafico
from core.layout import cartao, filtros, kpi, linha_kpis
from pages.Diario_Venda.Dados import dados_diario_venda as dados

_NOME_MES = [
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]


def _escolhas_mes() -> dict[str, str]:
    return {m.isoformat(): f"{_NOME_MES[m.month - 1]}/{m.year}" for m in dados.meses_com_meta()}


@module.ui
def diario_venda_ui():
    filiais = sorted(ler("equipe")["filial"].unique().to_list())
    return ui.div(
        filtros(
            ui.input_select("mes", "Mês", _escolhas_mes()),
            ui.input_select("filial", "Filial", {"": "Todas", **{f: f for f in filiais}}),
            ui.input_selectize("gerente", "Gerente de Área", [], multiple=True, options={"placeholder": "Todos"}),
            ui.input_selectize("vendedor", "Vendedor", [], multiple=True, options={"placeholder": "Todos"}),
            limpar_id="limpar",
        ),
        ui.output_ui("kpis"),
        cartao(
            "Diário de Vendas - Categorias e Marcas (HL)",
            ui.output_data_frame("tabela"),
            ui.div(
                "Tendência = real ÷ dias úteis passados × dias úteis do mês. "
                "Cobertura = clientes que compraram no mês. Meta por categoria.",
                class_="legenda",
            ),
        ),
        ui.layout_columns(
            cartao("Venda por dia (HL)", ui.output_ui("grafico_dia")),
            cartao("Últimos 13 meses (HL)", ui.output_ui("grafico_meses")),
            col_widths=(6, 6),
        ),
    )


@module.server
def diario_venda_server(input, output, session):
    @reactive.effect
    def _gerentes_da_filial():
        eq = dados.equipe(input.filial() or None)
        with reactive.isolate():
            atual = [g for g in input.gerente() if g in eq["gerente"].to_list()]
        ui.update_selectize("gerente", choices=sorted(eq["gerente"].unique().to_list()), selected=atual)

    @reactive.effect
    def _vendedores_do_gerente():
        eq = dados.equipe(input.filial() or None)
        if input.gerente():
            eq = eq.filter(pl.col("gerente").is_in(list(input.gerente())))
        nomes = eq.sort("cod_vendedor")["vendedor"].to_list()
        with reactive.isolate():
            atual = [v for v in input.vendedor() if v in nomes]
        ui.update_selectize("vendedor", choices=nomes, selected=atual)

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar():
        ui.update_select("filial", selected="")
        ui.update_selectize("gerente", selected=[])
        ui.update_selectize("vendedor", selected=[])

    @reactive.calc
    def mes() -> date:
        return date.fromisoformat(input.mes())

    @reactive.calc
    def cods() -> list[int]:
        return dados.vendedores_escolhidos(input.filial() or None, list(input.gerente()), list(input.vendedor()))

    @reactive.calc
    def base() -> pl.DataFrame:
        return dados.tabela_categorias(mes(), cods())

    @render.ui
    def kpis():
        total = base().filter(pl.col("nivel") == "total")
        if total.is_empty():
            return ui.div()
        t = total.row(0, named=True)
        uteis, passados = dados.dias_uteis(mes())
        tend_meta = t["tend_meta"]
        classe = "bom" if (tend_meta or 0) >= 1 else "ruim"
        # Mês corrente ainda está pela metade: compara a tendência, não o realizado.
        variacao = (t["tend"] / t["m12"] - 1) if t["m12"] else None
        mes_atual = mes() == date(data_base().year, data_base().month, 1)

        return linha_kpis(
            kpi(
                "Volume realizado",
                f"{numero(t['real'])} HL",
                ui.span(
                    f"Tendência {pct(variacao)} vs {mes_curto(dados._mes_menos(mes(), 12))}",
                    class_="bom" if (variacao or 0) >= 0 else "ruim",
                )
                if variacao is not None
                else "",
            ),
            kpi(
                "Meta do mês",
                f"{numero(t['meta'])} HL",
                f"Dias úteis: {passados} de {uteis}" if mes_atual else "Mês fechado",
            ),
            kpi("Tendência / meta", pct(tend_meta), ui.span(f"Tendência de {numero(t['tend'])} HL", class_=classe)),
            kpi("Faturamento", moeda(t["fat"], 0), f"R$/HL {numero(t['rs_hl'], 2)}"),
            kpi("Cobertura", numero(t["cob"]), f"clientes ({numero(t['cob_m1'])} no mês anterior)"),
        )

    @render.data_frame
    def tabela():
        df = base()
        m = mes()
        cols = {
            "linha": "Principais Categorias",
            "m12": mes_curto(dados._mes_menos(m, 12)),
            "m2": mes_curto(dados._mes_menos(m, 2)),
            "m1": mes_curto(dados._mes_menos(m, 1)),
            "meta": "Meta",
            "real": f"Real {mes_curto(m)}",
            "tend": "Tend.",
            "tend_meta": "% Tend./Meta",
            "rs_hl": "R$/HL",
            "cob_m1": f"Cob. {mes_curto(dados._mes_menos(m, 1))}",
            "cob": f"Cob. {mes_curto(m)}",
            "fat": f"Fat. {mes_curto(m)}",
        }
        exibir = pl.DataFrame(
            {
                nome: [
                    (
                        v
                        if c == "linha"
                        else pct(v)
                        if c == "tend_meta"
                        else numero(v, 2)
                        if c == "rs_hl"
                        else moeda(v, 0)
                        if c == "fat"
                        else numero(v)
                    )
                    for v in df[c].to_list()
                ]
                for c, nome in cols.items()
            }
        )
        estilos = []
        for i, linha in enumerate(df.iter_rows(named=True)):
            if linha["nivel"] == "total":
                estilos.append({"rows": [i], "style": {"font-weight": "700", "background-color": "#eef6f2"}})
            elif linha["nivel"] == "categoria":
                estilos.append({"rows": [i], "style": {"background-color": "#f7f9f8"}})
            else:
                estilos.append(
                    {
                        "rows": [i],
                        "cols": [0],
                        "style": {"background-color": linha["cor_marca"], "color": "#fff", "font-weight": "600"},
                    }
                )
            if linha["tend_meta"] is not None:
                cor = cores.POSITIVO if linha["tend_meta"] >= 1 else cores.NEGATIVO
                estilos.append({"rows": [i], "cols": [7], "style": {"color": cor, "font-weight": "700"}})
        return render.DataGrid(exibir, styles=estilos, width="100%", height="auto", summary=False)

    @render.ui
    def grafico_dia():
        dia = dados.venda_por_dia(mes(), cods())
        if dia.is_empty():
            return ui.div("Venda por dia só existe para o mês corrente.", class_="legenda")
        meta = base().filter(pl.col("nivel") == "total")["meta"].item()
        uteis, _ = dados.dias_uteis(mes())
        ritmo = (meta or 0) / uteis if uteis else 0
        acumulado = dia["hl"].cum_sum().to_list()
        return grafico(
            {
                "tooltip": {"trigger": "axis", "valueFormatter": NUMERO_BR},
                "legend": {"top": 0},
                "grid": {"left": 50, "right": 50, "top": 40, "bottom": 30},
                "xAxis": {"type": "category", "data": [d.strftime("%d/%m") for d in dia["data"]]},
                "yAxis": [eixo_valor("Dia"), eixo_valor("Acumulado")],
                "series": [
                    {
                        "name": "HL no dia",
                        "type": "bar",
                        "data": [round(v, 1) for v in dia["hl"]],
                        "itemStyle": {"color": cores.SERIES[0], "borderRadius": [4, 4, 0, 0]},
                    },
                    {
                        "name": "Acumulado",
                        "type": "line",
                        "yAxisIndex": 1,
                        "smooth": True,
                        "data": [round(v, 1) for v in acumulado],
                        "itemStyle": {"color": cores.SERIES[3]},
                    },
                    {
                        "name": "Ritmo da meta",
                        "type": "line",
                        "yAxisIndex": 1,
                        "symbol": "none",
                        "lineStyle": {"type": "dashed"},
                        "itemStyle": {"color": cores.NEUTRO},
                        "data": [round(ritmo * (i + 1), 1) for i in range(len(acumulado))],
                    },
                ],
            }
        )

    @render.ui
    def grafico_meses():
        ev = dados.evolucao_mensal(mes(), cods())
        return grafico(
            {
                "tooltip": {"trigger": "axis", "valueFormatter": NUMERO_BR},
                "legend": {"top": 0},
                "grid": {"left": 55, "right": 55, "top": 40, "bottom": 30},
                "xAxis": {"type": "category", "data": [mes_curto(m) for m in ev["mes"]]},
                "yAxis": [eixo_valor("HL"), eixo_valor("R$/HL", scale=True)],
                "series": [
                    {
                        "name": "HL",
                        "type": "bar",
                        "data": [round(v, 1) for v in ev["hl"]],
                        "itemStyle": {"color": cores.SERIES[0], "borderRadius": [4, 4, 0, 0]},
                    },
                    {
                        "name": "R$/HL",
                        "type": "line",
                        "yAxisIndex": 1,
                        "smooth": True,
                        "data": [round(f / h, 2) if h else None for f, h in zip(ev["faturamento"], ev["hl"])],
                        "itemStyle": {"color": cores.SERIES[1]},
                    },
                ],
            }
        )
