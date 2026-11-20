from datetime import date

import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.formato import mes_curto, moeda, numero, pct
from core.graficos import grafico
from core.layout import cartao, filtros
from pages.Mapa_Comercial.Dados import dados_mapa_comercial as dados


def _formatar(indicador: str, valor: float) -> str:
    if indicador == "faturamento":
        return moeda(valor, 0)
    if indicador == "cobertura":
        return pct(valor)
    return numero(valor, 1 if indicador == "hl" else 0)


@module.ui
def mapa_comercial_ui():
    return ui.div(
        filtros(
            ui.input_select("filial", "Filial", list(dados.filiais())),
            ui.input_select("mes", "Mês", {m.isoformat(): mes_curto(m) for m in dados.meses()}),
            ui.input_radio_buttons("indicador", "Indicador", dados.INDICADORES, inline=True),
        ),
        ui.layout_columns(
            cartao(
                "Mapa Comercial",
                ui.output_ui("mapa"),
                ui.div("Malha municipal do IBGE. Cidades em cinza não têm cliente na carteira.", class_="legenda"),
            ),
            cartao("Cidades", ui.output_data_frame("ranking")),
            col_widths=(8, 4),
        ),
    )


@module.server
def mapa_comercial_server(input, output, session):
    @reactive.calc
    def base() -> pl.DataFrame:
        return dados.por_cidade(input.filial(), date.fromisoformat(input.mes()))

    @render.ui
    def mapa():
        uf = dados.filiais()[input.filial()]
        ind = input.indicador()
        df = base()
        # A capital vende muito mais que o resto: com a escala até o máximo, o
        # interior inteiro ficaria da mesma cor clara. Até o percentil 90, a
        # capital satura e as outras cidades se diferenciam.
        positivos = df.filter(pl.col(ind) > 0)[ind]
        teto = positivos.quantile(0.9) if positivos.len() else 1
        formatado = {r["cod_ibge"]: _formatar(ind, r[ind]) for r in df.iter_rows(named=True)}
        return grafico(
            {
                "tooltip": {
                    "trigger": "item",
                    "formatter": "js:function (p) { return p.data ? '<b>' + p.data.cidade + '</b><br>' + p.data.texto"
                    " + '<br>Carteira: ' + p.data.carteira + ' clientes' : 'Sem clientes'; }",
                },
                "visualMap": {
                    "min": 0,
                    "max": teto,
                    "calculable": True,
                    "inRange": {"color": cores.RAMPA},
                    "left": 10,
                    "bottom": 10,
                    "text": ["maior", "menor"],
                    "formatter": "js:function (v) { return Math.round(v).toLocaleString('pt-BR'); }"
                    if ind != "cobertura"
                    else "js:function (v) { return (v * 100).toFixed(0) + '%'; }",
                },
                "series": [
                    {
                        "type": "map",
                        "map": uf,
                        "nameProperty": "codarea",
                        "roam": True,
                        "layoutCenter": ["55%", "50%"],
                        "layoutSize": "98%",
                        "itemStyle": {"areaColor": "#e9ecef", "borderColor": "#fff", "borderWidth": 0.6},
                        "emphasis": {"label": {"show": False}, "itemStyle": {"areaColor": cores.SERIES[3]}},
                        "select": {"disabled": True},
                        "data": [
                            {
                                "name": str(r["cod_ibge"]),
                                "value": r[ind],
                                "cidade": r["cidade"],
                                "texto": f"{dados.INDICADORES[ind]}: {formatado[r['cod_ibge']]}",
                                "carteira": r["carteira"],
                            }
                            for r in df.iter_rows(named=True)
                        ],
                    }
                ],
            },
            altura="68vh",
            mapas={uf: f"geo/{uf}.json"},
        )

    @render.data_frame
    def ranking():
        ind = input.indicador()
        df = base().sort(ind, descending=True)
        return render.DataGrid(
            pl.DataFrame(
                {
                    "Cidade": df["cidade"],
                    dados.INDICADORES[ind]: [_formatar(ind, v) for v in df[ind]],
                    "Carteira": [numero(v) for v in df["carteira"]],
                }
            ),
            width="100%",
            height="68vh",
            summary=False,
        )
