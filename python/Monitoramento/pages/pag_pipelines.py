import pandas as pd
import polars as pl
from faicons import icon_svg
from shiny import module, reactive, render, ui

from core.compat import para_pandas
from core.config import FONTES_LOG
from core.cores import DESTAQUE, STATUS_FORA_DO_AR, STATUS_NO_AR, TEXTO_ESCURO
from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.leitura_logs import atualizar, ler_erros, ler_performance
from core.visibilidade import pagina_visivel

INTERVALO_ATUALIZACAO_S = 30

COLUNAS = {
    "funcao": "Pipeline",
    "execucoes": "Execuções",
    "media_s": "Duração média",
    "max_s": "Mais demorada",
    "falhas": "Falhas",
}
ORDEM = list(COLUNAS)
_LARGURA = {"funcao": 300, "execucoes": 120, "media_s": 150, "max_s": 150, "falhas": 100}

COLUNAS_FALHA = {"timestamp": "Quando", "onde": "Pipeline", "mensagem": "Erro"}
ORDEM_FALHA = ["timestamp", "onde", "mensagem"]
_LARGURA_FALHA = {"timestamp": 180, "onde": 240, "mensagem": 520}


def _segundos(ms: float) -> str:
    total = ms / 1000
    if total < 60:
        return f"{total:.1f}s"
    minutos, segundos = divmod(int(total), 60)
    return f"{minutos}min {segundos:02d}s"


@module.ui
def pag_pipelines_ui():
    return ui.div(
        ui.output_ui("cards"),
        ui.card(
            ui.card_header("Execuções de hoje"),
            ui.output_ui("css_largura"),
            ui.div(ui.output_data_frame("tabela"), id="grupo-tabela-pipelines", class_="tabela-resize"),
            class_="my-4",
        ),
        ui.card(
            ui.card_header("Falhas (clique para ver o detalhe)"),
            ui.output_ui("css_largura_falha"),
            ui.div(ui.output_data_frame("tabela_falhas"), id="grupo-tabela-falhas", class_="tabela-resize"),
        ),
        ui.output_ui("detalhe"),
        class_="pagina-monitoramento",
    )


@module.server
def pag_pipelines_server(input, output, session, valor_navset: str = "pipelines"):
    escolhido = reactive.value(None, name="escolhido")

    @reactive.calc
    def execucoes() -> pd.DataFrame:
        reactive.invalidate_later(INTERVALO_ATUALIZACAO_S)
        if not pagina_visivel(session, valor_navset):
            return pd.DataFrame()
        atualizar(FONTES_LOG)
        base = ler_performance().filter(pl.col("pagina") == "pipeline")
        if base.height == 0:
            return pd.DataFrame()
        return (
            base.select(
                pl.col("funcao"),
                pl.col("chamadas").alias("execucoes"),
                pl.col("media_ms"),
                pl.col("max_ms"),
                pl.col("lentas").alias("_ignorado"),
            )
            .pipe(para_pandas)
            .assign(
                media_s=lambda d: d["media_ms"].map(_segundos),
                max_s=lambda d: d["max_ms"].map(_segundos),
            )
        )

    @reactive.calc
    def falhas() -> pd.DataFrame:
        reactive.invalidate_later(INTERVALO_ATUALIZACAO_S)
        if not pagina_visivel(session, valor_navset):
            return pd.DataFrame()
        atualizar(FONTES_LOG)
        base = ler_erros()
        if base.height == 0:
            return pd.DataFrame()
        return base.filter(pl.col("origem") == "pipeline").pipe(para_pandas)

    @render.ui
    def cards():
        base = execucoes()
        quebradas = falhas()
        total = int(base["execucoes"].sum()) if not base.empty else 0
        return ui.layout_columns(
            ui.value_box(
                "Execuções hoje",
                str(total),
                showcase=icon_svg("gears"),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#FFF"),
            ),
            ui.value_box(
                "Pipelines diferentes",
                str(len(base)),
                showcase=icon_svg("diagram-project"),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#FFF"),
            ),
            ui.value_box(
                "Falhas",
                str(len(quebradas)),
                showcase=icon_svg("circle-xmark" if len(quebradas) else "circle-check"),
                theme=ui.value_box_theme(
                    bg=STATUS_FORA_DO_AR if len(quebradas) else STATUS_NO_AR,
                    fg=TEXTO_ESCURO,
                ),
            ),
        )

    @render.data_frame
    def tabela():
        base = execucoes()
        if base.empty:
            return render.DataTable(
                pd.DataFrame({"Aviso": ["Nenhum pipeline executado hoje"]}),
                summary=False,
                filters=False,
                selection_mode="none",
            )
        quebradas = falhas()
        por_pipeline = quebradas["onde"].value_counts().to_dict() if not quebradas.empty else {}
        base = base.assign(falhas=base["funcao"].map(lambda n: por_pipeline.get(n, 0)))
        estilos = [
            {"rows": [posicao], "style": {"background-color": "rgba(239, 181, 185, 0.5)"}}
            for posicao, (_, linha) in enumerate(base.iterrows())
            if linha["falhas"] > 0
        ]
        return render.DataTable(
            base[ORDEM].rename(columns=COLUNAS),
            styles=estilos,
            height="32vh",
            summary=False,
            filters=False,
            selection_mode="none",
        )

    @render.data_frame
    def tabela_falhas():
        base = falhas()
        if base.empty:
            return render.DataTable(
                pd.DataFrame({"Aviso": ["Nenhuma falha registrada hoje"]}),
                summary=False,
                filters=False,
                selection_mode="none",
            )
        return render.DataTable(
            base[ORDEM_FALHA].rename(columns=COLUNAS_FALHA),
            height="28vh",
            summary=False,
            filters=False,
            selection_mode="row",
        )

    @reactive.effect
    def _guardar_escolhido():
        try:
            linhas = tabela_falhas.cell_selection()["rows"]
        except Exception:
            return
        if not linhas:
            return
        base = falhas()
        if base.empty or linhas[0] >= len(base):
            return
        escolhido.set(base.iloc[linhas[0]].to_dict())

    @render.ui
    def detalhe():
        erro = escolhido()
        if not erro:
            return None
        pilha = (erro.get("detalhe") or "").strip() or "Sem traceback registrado."
        return ui.card(
            ui.card_header(f"{erro.get('onde')} -- {erro.get('timestamp')}"),
            ui.p(erro.get("mensagem") or "", class_="fw-bold"),
            ui.tags.pre(pilha, class_="mon-traceback"),
        )

    @render.ui
    def css_largura():
        larguras = [ColunaLargura(c, _LARGURA[c]) for c in ORDEM]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela')}", larguras))

    @render.ui
    def css_largura_falha():
        larguras = [ColunaLargura(c, _LARGURA_FALHA[c]) for c in ORDEM_FALHA]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_falhas')}", larguras))
