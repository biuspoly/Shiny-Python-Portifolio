from datetime import date

import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.formato import mes_curto, moeda, numero, pct
from core.layout import cartao, filtros, kpi, linha_kpis
from pages.Conciliacao.Dados import dados_conciliacao as dados

_COR = {"Conciliado": cores.POSITIVO, "Só no banco": cores.NEGATIVO, "Só no ERP": cores.ALERTA}


@module.ui
def conciliacao_ui():
    return ui.div(
        filtros(
            ui.input_select("conta", "Conta", {"": "Todas", **{c: c for c in dados.contas()}}),
            ui.input_select("mes", "Mês", {m.isoformat(): mes_curto(m) for m in dados.meses()}),
            ui.input_selectize(
                "situacao",
                "Situação",
                dados.SITUACOES,
                multiple=True,
                selected=["Só no banco", "Só no ERP"],
                options={"placeholder": "Todas"},
            ),
        ),
        ui.output_ui("kpis"),
        ui.layout_columns(
            cartao(
                "Extrato × ERP",
                ui.output_data_frame("tabela"),
                ui.div(
                    "Casamento automático por conta, data e valor. Dois lançamentos iguais no mesmo dia "
                    "casam um a um, na ordem.",
                    class_="legenda",
                ),
            ),
            cartao(
                "Só no banco, por tipo",
                ui.output_data_frame("tipos"),
                ui.div("Tarifas, IOF e depósitos sem nota: precisam de lançamento manual no ERP.", class_="legenda"),
            ),
            col_widths=(8, 4),
        ),
    )


@module.server
def conciliacao_server(input, output, session):
    @reactive.calc
    def base() -> pl.DataFrame:
        return dados.conciliar(input.conta() or None, date.fromisoformat(input.mes()))

    @reactive.calc
    def filtrada() -> pl.DataFrame:
        df = base()
        return df.filter(pl.col("situacao").is_in(list(input.situacao()))) if input.situacao() else df

    @render.ui
    def kpis():
        df = base()
        conta = dict(df.group_by("situacao").len().iter_rows())
        valor = dict(df.group_by("situacao").agg(pl.col("valor").sum()).iter_rows())
        no_banco = df.filter(pl.col("descricao").is_not_null())
        no_erp = df.filter(pl.col("historico").is_not_null())
        conciliados = conta.get("Conciliado", 0)
        return linha_kpis(
            kpi("Lançamentos no banco", numero(no_banco.height), f"{numero(no_erp.height)} no ERP"),
            kpi(
                "Conciliados",
                pct(conciliados / no_banco.height if no_banco.height else None),
                f"{numero(conciliados)} casados",
                cores.POSITIVO,
            ),
            kpi("Só no banco", numero(conta.get("Só no banco", 0)), moeda(valor.get("Só no banco", 0)), cores.NEGATIVO),
            kpi("Só no ERP", numero(conta.get("Só no ERP", 0)), moeda(valor.get("Só no ERP", 0)), cores.ALERTA),
            kpi("Diferença de saldo", moeda(no_banco["valor"].sum() - no_erp["valor"].sum()), "banco - ERP no mês"),
        )

    @render.data_frame
    def tabela():
        df = filtrada()
        idx = df.with_row_index()
        estilos = [
            {"rows": linhas, "cols": [5], "style": {"color": cor, "font-weight": "700"}}
            for s, cor in _COR.items()
            if (linhas := idx.filter(pl.col("situacao") == s)["index"].to_list())
        ]
        negativos = idx.filter(pl.col("valor") < 0)["index"].to_list()
        if negativos:
            estilos.append({"rows": negativos, "cols": [4], "style": {"color": cores.NEGATIVO}})
        return render.DataGrid(
            pl.DataFrame(
                {
                    "Data": [d.strftime("%d/%m/%Y") for d in df["data"]],
                    "Conta": df["conta"],
                    "Extrato do banco": df["descricao"].fill_null("-"),
                    "Lançamento no ERP": df["historico"].fill_null("-"),
                    "Valor": [moeda(v) for v in df["valor"]],
                    "Situação": df["situacao"],
                }
            ),
            styles=estilos,
            width="100%",
            height="60vh",
            summary="Mostrando {start} a {end} de {total} lançamentos",
        )

    @render.data_frame
    def tipos():
        t = dados.pendencias_por_tipo(base())
        return render.DataGrid(
            pl.DataFrame({"Tipo": t["tipo"], "Qtd": t["qtd"].cast(pl.String), "Valor": [moeda(v) for v in t["valor"]]}),
            width="100%",
            height="auto",
            summary=False,
        )
