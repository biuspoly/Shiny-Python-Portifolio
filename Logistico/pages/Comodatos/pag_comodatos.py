import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.dados import ler
from core.formato import moeda, numero, pct
from core.graficos import grafico
from core.layout import cartao, filtros, kpi, linha_kpis
from pages.Comodatos.Dados import dados_comodatos as dados

_COR_SITUACAO = {
    "Ativo": cores.POSITIVO,
    "Contrato vencido": cores.ALERTA,
    "Recolha pedida": cores.NEGATIVO,
    "Recolhido": cores.NEUTRO,
}


@module.ui
def comodatos_ui():
    c = ler("comodatos")
    return ui.div(
        filtros(
            ui.input_select("filial", "Filial", {"": "Todas", **{f: f for f in sorted(c["filial"].unique())}}),
            ui.input_selectize(
                "equipamento",
                "Equipamento",
                sorted(c["equipamento"].unique().to_list()),
                multiple=True,
                options={"placeholder": "Todos"},
            ),
            ui.input_selectize(
                "situacao",
                "Situação",
                dados.SITUACOES,
                multiple=True,
                selected=dados.EM_CAMPO,
                options={"placeholder": "Todas"},
            ),
            ui.input_text("busca", "Cliente ou patrimônio", placeholder="Nome, código ou PT-"),
            limpar_id="limpar",
        ),
        ui.output_ui("kpis"),
        ui.layout_columns(
            cartao(
                "Equipamentos em comodato",
                ui.output_data_frame("tabela"),
                ui.div(
                    f"Sem visita: mais de {dados.DIAS_SEM_VISITA} dias desde a última visita do vendedor.",
                    class_="legenda",
                ),
            ),
            cartao("Por equipamento e situação", ui.output_ui("grafico_situacao")),
            col_widths=(8, 4),
        ),
    )


@module.server
def comodatos_server(input, output, session):
    base = dados.comodatos()

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar():
        ui.update_select("filial", selected="")
        ui.update_selectize("equipamento", selected=[])
        ui.update_selectize("situacao", selected=dados.EM_CAMPO)
        ui.update_text("busca", value="")

    @reactive.calc
    def filtrada() -> pl.DataFrame:
        df = base
        if input.filial():
            df = df.filter(pl.col("filial") == input.filial())
        if input.equipamento():
            df = df.filter(pl.col("equipamento").is_in(list(input.equipamento())))
        if input.situacao():
            df = df.filter(pl.col("situacao").is_in(list(input.situacao())))
        texto = input.busca().strip().upper()
        if texto:
            df = df.filter(
                pl.col("cliente").str.contains(texto, literal=True)
                | pl.col("patrimonio").str.contains(texto, literal=True)
                | pl.col("cod_cliente").cast(pl.String).str.starts_with(texto)
            )
        return df

    @render.ui
    def kpis():
        df = filtrada()
        campo = df.filter(pl.col("situacao").is_in(dados.EM_CAMPO))
        sem_visita = campo.filter(pl.col("dias_sem_visita") > dados.DIAS_SEM_VISITA).height
        conta = dict(df.group_by("situacao").len().iter_rows())
        return linha_kpis(
            kpi("Em campo", numero(campo.height), f"{numero(campo['cod_cliente'].n_unique())} clientes"),
            kpi("Valor patrimonial", moeda(campo["valor"].sum(), 0), "equipamentos em campo"),
            kpi(
                "Contratos vencidos",
                numero(conta.get("Contrato vencido", 0)),
                "renovar ou recolher",
                _COR_SITUACAO["Contrato vencido"],
            ),
            kpi(
                "Recolhas pedidas",
                numero(conta.get("Recolha pedida", 0)),
                "cliente parou de comprar",
                _COR_SITUACAO["Recolha pedida"],
            ),
            kpi(
                "Sem visita", numero(sem_visita), pct(sem_visita / campo.height if campo.height else None) + " do campo"
            ),
        )

    @render.data_frame
    def tabela():
        df = filtrada()
        exibir = pl.DataFrame(
            {
                "Patrimônio": df["patrimonio"],
                "Equipamento": df["equipamento"],
                "Cliente": df["cliente"],
                "Cidade": df["cidade"],
                "Instalado em": [d.strftime("%d/%m/%Y") for d in df["instalado_em"]],
                "Vencimento": [d.strftime("%d/%m/%Y") for d in df["vencimento_contrato"]],
                "Situação": df["situacao"],
                "Dias sem visita": df["dias_sem_visita"].cast(pl.String),
                "Valor": [moeda(v, 0) for v in df["valor"]],
            }
        )
        indices = df.with_row_index()
        estilos = [
            {"rows": linhas, "cols": [6], "style": {"color": cor, "font-weight": "700"}}
            for s, cor in _COR_SITUACAO.items()
            if (linhas := indices.filter(pl.col("situacao") == s)["index"].to_list())
        ]
        atrasadas = indices.filter(pl.col("dias_sem_visita") > dados.DIAS_SEM_VISITA)["index"].to_list()
        if atrasadas:
            estilos.append({"rows": atrasadas, "cols": [7], "style": {"color": cores.NEGATIVO, "font-weight": "700"}})
        return render.DataGrid(
            exibir,
            width="100%",
            height="62vh",
            summary="Mostrando {start} a {end} de {total} equipamentos",
            styles=estilos,
        )

    @render.ui
    def grafico_situacao():
        tab = dados.por_equipamento(filtrada())
        situacoes = [s for s in dados.SITUACOES if s in tab.columns]
        return grafico(
            {
                "tooltip": {"trigger": "axis"},
                "legend": {"bottom": 0},
                "grid": {"left": 150, "right": 20, "top": 10, "bottom": 60},
                "xAxis": {"type": "value"},
                "yAxis": {"type": "category", "data": tab["equipamento"].to_list()},
                "series": [
                    {
                        "name": s,
                        "type": "bar",
                        "stack": "t",
                        "data": tab[s].to_list(),
                        "itemStyle": {"color": _COR_SITUACAO[s]},
                    }
                    for s in situacoes
                ],
            },
            altura="62vh",
        )
