from datetime import timedelta

import polars as pl
from shiny import module, render, ui

from core import cores
from core.dados import data_base, ler
from core.formato import numero
from core.graficos import grafico
from core.layout import cartao, kpi, linha_kpis
from pages.Visao_Geral.Dados import dados_visao_geral as dados


@module.ui
def visao_geral_ui():
    return ui.div(
        ui.output_ui("kpis"),
        ui.layout_columns(
            cartao("Pessoas com acesso, por app", ui.output_ui("grafico_app")),
            cartao("Papéis", ui.output_data_frame("papeis")),
            col_widths=(6, 6),
        ),
        cartao(
            "Acesso amplo (12 páginas ou mais)",
            ui.output_data_frame("amplo"),
            ui.div("Quem enxerga muita coisa é o primeiro a revisar quando alguém muda de função.", class_="legenda"),
        ),
    )


@module.server
def visao_geral_server(input, output, session):
    @render.ui
    def kpis():
        u = ler("usuarios")
        h = ler("historico")
        ultimos_30 = h.filter(pl.col("momento").dt.date() > data_base() - timedelta(days=30))
        return linha_kpis(
            kpi(
                "Pessoas ativas", numero(u["ativo"].sum()), f"{numero((~u['ativo']).sum())} desativadas", cores.POSITIVO
            ),
            kpi("Papéis", numero(u["papel"].n_unique()), "grupos de permissão"),
            kpi(
                "Páginas protegidas",
                numero(ler("paginas").height),
                f"em {numero(ler('paginas')['app'].n_unique())} apps",
            ),
            kpi(
                "Alterações em 30 dias",
                numero(ultimos_30.height),
                f"{numero((ultimos_30['acao'] != 'Concedeu').sum())} retiradas ou desativações",
                cores.ALERTA,
            ),
        )

    @render.ui
    def grafico_app():
        a = dados.usuarios_por_app()
        return grafico(
            {
                "tooltip": {"trigger": "axis"},
                "grid": {"left": 90, "right": 40, "top": 10, "bottom": 25},
                "xAxis": {"type": "value", "minInterval": 1},
                "yAxis": {"type": "category", "data": a["app"].to_list(), "inverse": True},
                "series": [
                    {
                        "type": "bar",
                        "name": "Pessoas",
                        "label": {"show": True, "position": "right"},
                        "data": [
                            {"value": v, "itemStyle": {"color": cores.APPS[app], "borderRadius": [0, 4, 4, 0]}}
                            for app, v in a.iter_rows()
                        ],
                    }
                ],
            },
            altura="30vh",
        )

    @render.data_frame
    def papeis():
        p = dados.por_papel()
        return render.DataGrid(
            pl.DataFrame(
                {
                    "Papel": p["papel"],
                    "Pessoas": p["pessoas"].cast(pl.String),
                    "Ativas": p["ativas"].cast(pl.String),
                    "Páginas em média": [numero(v or 0, 1) for v in p["media_paginas"]],
                }
            ),
            width="100%",
            height="auto",
            summary=False,
        )

    @render.data_frame
    def amplo():
        a = dados.acesso_amplo()
        return render.DataGrid(
            pl.DataFrame(
                {
                    "Pessoa": a["nome"],
                    "Login": a["login"],
                    "Papel": a["papel"],
                    "Filial": a["filial"],
                    "Apps": a["apps"].cast(pl.String),
                    "Páginas": a["paginas"].cast(pl.String),
                }
            ),
            width="100%",
            height="auto",
            summary=False,
        )
