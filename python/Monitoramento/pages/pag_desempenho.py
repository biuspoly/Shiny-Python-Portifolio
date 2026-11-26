import pandas as pd
from pyecharts import options as opts
from pyecharts.charts import Line
from shiny import module, reactive, render, ui

from core.compat import para_pandas
from core.config import FONTES_LOG
from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.leitura_logs import (
    atualizar,
    historico_por_hora,
    ler_dados,
    ler_execucao_reativa,
    ler_performance,
)
from core.pyecharts_shiny import renderizar
from core.visibilidade import pagina_visivel

INTERVALO_ATUALIZACAO_S = 30

DIAS_NO_GRAFICO = 7

LIMITE_MS_PADRAO = 2000
LIMITE_MS_DADOS = 1500

DESTAQUE_LINHA = {"background-color": "rgba(239, 181, 185, 0.5)"}

COLUNAS_DADOS = {
    "app": "App",
    "canal": "Canal",
    "fonte": "Fonte",
    "chamadas": "Chamadas",
    "media_ms": "Média (ms)",
    "max_ms": "Máx (ms)",
    "lentas": f"Lentas (>{LIMITE_MS_DADOS}ms)",
    "erros": "Erros",
}
ORDEM_DADOS = list(COLUNAS_DADOS)
_LARGURA_DADOS = {
    "app": 110,
    "canal": 100,
    "fonte": 220,
    "chamadas": 100,
    "media_ms": 110,
    "max_ms": 100,
    "lentas": 150,
    "erros": 90,
}

COLUNAS_LENTIDAO = {
    "app": "App",
    "pagina": "Página",
    "funcao": "Função",
    "chamadas": "Chamadas",
    "media_ms": "Média (ms)",
    "max_ms": "Máx (ms)",
    "lentas": f"Lentas (>{LIMITE_MS_PADRAO}ms)",
}
ORDEM_LENTIDAO = list(COLUNAS_LENTIDAO)
_LARGURA_LENTIDAO = {
    "app": 110,
    "pagina": 140,
    "funcao": 200,
    "chamadas": 100,
    "media_ms": 110,
    "max_ms": 100,
    "lentas": 160,
}

COLUNAS_REATIVA = {
    "app": "App",
    "nome": "Calc/Effect/Output",
    "chamadas": "Chamadas",
    "media_ms": "Média (ms)",
    "max_ms": "Máx (ms)",
    "erros": "Erros",
}
ORDEM_REATIVA = list(COLUNAS_REATIVA)
_LARGURA_REATIVA = {
    "app": 110,
    "nome": 300,
    "chamadas": 100,
    "media_ms": 110,
    "max_ms": 100,
    "erros": 90,
}


def _tabela_vazia(texto: str):
    return render.DataTable(
        pd.DataFrame({"Aviso": [texto]}),
        summary=False,
        filters=False,
        selection_mode="none",
    )


def _destacar(base: pd.DataFrame, colunas: list[str]) -> list[dict]:
    marcadores = [c for c in colunas if c in base.columns]
    return [
        {"rows": [posicao], "style": DESTAQUE_LINHA}
        for posicao, (_, linha) in enumerate(base.iterrows())
        if any(linha[c] > 0 for c in marcadores)
    ]


def _grafico_de_horas(horas: list[str], nome_eixo: str, ocultas: list[str] | None = None) -> Line:
    grafico = Line()
    grafico.add_xaxis([f"{h[8:10]}/{h[5:7]} {h[11:13]}h" for h in horas])
    grafico.set_global_opts(
        legend_opts=opts.LegendOpts(
            pos_top="0%",
            type_="scroll",
            textstyle_opts=opts.TextStyleOpts(font_size=10),
            selected_map={nome: False for nome in (ocultas or [])} or None,
        ),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, font_size=9)),
        yaxis_opts=opts.AxisOpts(
            name=nome_eixo,
            name_location="middle",
            name_gap=42,
            axislabel_opts=opts.LabelOpts(font_size=9),
        ),
    )
    return grafico


def _sem_historico():
    return ui.div(
        f"Sem histórico ainda — o gráfico enche sozinho conforme os apps rodam (mostra até {DIAS_NO_GRAFICO} dias).",
        class_="text-muted p-3",
    )


@module.ui
def pag_desempenho_ui():
    return ui.div(
        ui.card(
            ui.card_header(f"Tempo de resposta por hora (últimos {DIAS_NO_GRAFICO} dias)"),
            ui.output_ui("grafico_tempo"),
        ),
        ui.card(
            ui.card_header(f"Sessões abertas por hora (últimos {DIAS_NO_GRAFICO} dias)"),
            ui.output_ui("grafico_sessoes"),
        ),
        ui.card(
            ui.card_header("Acesso a dados (banco, parquet, DuckDB)"),
            ui.output_ui("css_largura_dados"),
            ui.div(ui.output_data_frame("tabela_dados"), id="grupo-tabela-dados", class_="tabela-resize"),
            class_="mb-4",
        ),
        ui.card(
            ui.card_header("Lentidão por página/função"),
            ui.output_ui("css_largura_lentidao"),
            ui.div(ui.output_data_frame("tabela_lentidao"), id="grupo-tabela-lentidao", class_="tabela-resize"),
            class_="mb-4",
        ),
        ui.card(
            ui.card_header("Execução reativa do Shiny (OpenTelemetry)"),
            ui.output_ui("css_largura_reativa"),
            ui.div(ui.output_data_frame("tabela_reativa"), id="grupo-tabela-reativa", class_="tabela-resize"),
        ),
        class_="pagina-monitoramento",
    )


@module.server
def pag_desempenho_server(input, output, session, valor_navset: str = "desempenho"):
    @reactive.calc
    def leitura():
        reactive.invalidate_later(INTERVALO_ATUALIZACAO_S)
        if not pagina_visivel(session, valor_navset):
            return None
        atualizar(FONTES_LOG)
        return (
            ler_dados(),
            ler_performance(),
            ler_execucao_reativa(),
            historico_por_hora(DIAS_NO_GRAFICO),
        )

    @reactive.calc
    def historico():
        pronto = leitura()
        if pronto is None or pronto[3].height == 0:
            return None
        base = pronto[3]
        return base["hora"].unique().sort().to_list(), base.rows(named=True)

    @render.ui
    def grafico_tempo():
        pronto = historico()
        if pronto is None:
            return _sem_historico()
        horas, linhas = pronto
        media = {(l["app"], l["hora"]): l["media_ms"] for l in linhas if l["chamadas"]}
        maximo = {(l["app"], l["hora"]): l["max_ms"] for l in linhas if l["chamadas"]}
        apps = sorted({l["app"] for l in linhas})
        grafico = _grafico_de_horas(horas, "ms", ocultas=[f"{app} (máx)" for app in apps])
        for app in apps:
            grafico.add_yaxis(
                f"{app} (média)",
                [media.get((app, h)) for h in horas],
                is_symbol_show=False,
                label_opts=opts.LabelOpts(is_show=False),
            )
        for app in apps:
            grafico.add_yaxis(
                f"{app} (máx)",
                [maximo.get((app, h)) for h in horas],
                is_symbol_show=False,
                label_opts=opts.LabelOpts(is_show=False),
            )
        return ui.HTML(renderizar(grafico, altura="34vh"))

    @render.ui
    def grafico_sessoes():
        pronto = historico()
        if pronto is None:
            return _sem_historico()
        horas, linhas = pronto
        sessoes = {(l["app"], l["hora"]): l["sessoes"] for l in linhas}
        grafico = _grafico_de_horas(horas, "sessões")
        for app in sorted({l["app"] for l in linhas}):
            grafico.add_yaxis(
                app,
                [sessoes.get((app, h), 0) for h in horas],
                is_symbol_show=False,
                label_opts=opts.LabelOpts(is_show=False),
            )
        return ui.HTML(renderizar(grafico, altura="34vh"))

    @render.data_frame
    def tabela_dados():
        pronto = leitura()
        if pronto is None or pronto[0].height == 0:
            return _tabela_vazia("Nenhum acesso a dados registrado ainda")
        base = pronto[0].pipe(para_pandas)
        return render.DataTable(
            base.rename(columns=COLUNAS_DADOS),
            styles=_destacar(base, ["lentas", "erros"]),
            height="32vh",
            summary=False,
            filters=False,
            selection_mode="none",
        )

    @render.data_frame
    def tabela_lentidao():
        pronto = leitura()
        if pronto is None or pronto[1].height == 0:
            return _tabela_vazia("Sem dados de performance registrados ainda")
        base = pronto[1].pipe(para_pandas)
        return render.DataTable(
            base.rename(columns=COLUNAS_LENTIDAO),
            styles=_destacar(base, ["lentas"]),
            height="32vh",
            summary=False,
            filters=False,
            selection_mode="none",
        )

    @render.data_frame
    def tabela_reativa():
        pronto = leitura()
        if pronto is None or pronto[2].height == 0:
            return _tabela_vazia("Sem dados de execução reativa registrados ainda")
        base = pronto[2].pipe(para_pandas)
        return render.DataTable(
            base.rename(columns=COLUNAS_REATIVA),
            styles=_destacar(base, ["erros"]),
            height="32vh",
            summary=False,
            filters=False,
            selection_mode="none",
        )

    @render.ui
    def css_largura_dados():
        larguras = [ColunaLargura(c, _LARGURA_DADOS[c]) for c in ORDEM_DADOS]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_dados')}", larguras))

    @render.ui
    def css_largura_lentidao():
        larguras = [ColunaLargura(c, _LARGURA_LENTIDAO[c]) for c in ORDEM_LENTIDAO]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_lentidao')}", larguras))

    @render.ui
    def css_largura_reativa():
        larguras = [ColunaLargura(c, _LARGURA_REATIVA[c]) for c in ORDEM_REATIVA]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_reativa')}", larguras))
