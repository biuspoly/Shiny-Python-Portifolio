import pandas as pd
from faicons import icon_svg
from shiny import module, reactive, render, ui

from core.compat import para_pandas
from core.config import FONTES_LOG
from core.cores import DESTAQUE, STATUS_FORA_DO_AR
from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.leitura_logs import atualizar, ler_erros
from core.visibilidade import pagina_visivel

INTERVALO_ATUALIZACAO_S = 30

COLUNAS = {
    "timestamp": "Quando",
    "app": "App",
    "nivel": "Nível",
    "origem": "Origem",
    "onde": "Onde",
    "mensagem": "Mensagem",
}
ORDEM = ["app", "timestamp", "nivel", "origem", "onde", "mensagem"]
_LARGURA = {"app": 110, "timestamp": 180, "nivel": 90, "origem": 110, "onde": 220, "mensagem": 420}

ROTULO_ORIGEM = {
    "shiny": "Renderização",
    "dados": "Acesso a dados",
    "pipeline": "Script/pipeline",
    "medir_tempo": "Função medida",
    "sessao": "Sessão",
    "log": "Aviso da página",
}


@module.ui
def pag_erros_ui():
    return ui.div(
        ui.output_ui("cards"),
        ui.card(
            ui.card_header("Erros recentes (clique numa linha para ver o detalhe)"),
            ui.output_ui("css_largura"),
            ui.div(ui.output_data_frame("tabela"), id="grupo-tabela-erros", class_="tabela-resize"),
            class_="my-4",
        ),
        ui.output_ui("detalhe"),
        class_="pagina-monitoramento",
    )


@module.server
def pag_erros_server(input, output, session, valor_navset: str = "erros"):
    escolhido = reactive.value(None, name="escolhido")

    @reactive.calc
    def base_erros() -> pd.DataFrame:
        reactive.invalidate_later(INTERVALO_ATUALIZACAO_S)
        if not pagina_visivel(session, valor_navset):
            return pd.DataFrame()
        atualizar(FONTES_LOG)
        base = ler_erros()
        if base.height == 0:
            return pd.DataFrame()
        pandas_df = base.pipe(para_pandas)
        pandas_df["origem"] = pandas_df["origem"].map(lambda o: ROTULO_ORIGEM.get(o, o))
        return pandas_df

    @render.ui
    def cards():
        base = base_erros()
        renderizacao = int((base["origem"] == "Renderização").sum()) if not base.empty else 0
        dados = int((base["origem"] == "Acesso a dados").sum()) if not base.empty else 0
        return ui.layout_columns(
            ui.value_box(
                "Erros hoje",
                str(len(base)),
                showcase=icon_svg("triangle-exclamation"),
                theme=ui.value_box_theme(
                    bg=STATUS_FORA_DO_AR if len(base) else DESTAQUE,
                    fg="#1a1a1a" if len(base) else "#FFF",
                ),
            ),
            ui.value_box(
                "Em renderização",
                str(renderizacao),
                showcase=icon_svg("window-maximize"),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#FFF"),
            ),
            ui.value_box(
                "Em acesso a dados",
                str(dados),
                showcase=icon_svg("database"),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#FFF"),
            ),
        )

    @render.data_frame
    def tabela():
        base = base_erros()
        if base.empty:
            return render.DataTable(
                pd.DataFrame({"Aviso": ["Nenhum erro registrado hoje"]}),
                summary=False,
                filters=False,
                selection_mode="none",
            )
        return render.DataTable(
            base[ORDEM].rename(columns=COLUNAS),
            height="38vh",
            summary=False,
            filters=False,
            selection_mode="row",
        )

    @reactive.effect
    def _guardar_escolhido():
        try:
            linhas = tabela.cell_selection()["rows"]
        except Exception:
            return
        if not linhas:
            return
        base = base_erros()
        if base.empty or linhas[0] >= len(base):
            return
        escolhido.set(base.iloc[linhas[0]].to_dict())

    @render.ui
    def detalhe():
        erro = escolhido()
        if not erro:
            return None
        pilha = (erro.get("detalhe") or "").strip() or "Sem traceback registrado para este erro."
        return ui.card(
            ui.card_header(f"{erro['app']} -- {erro.get('onde') or erro['origem']} -- {erro['timestamp']}"),
            ui.p(erro.get("mensagem") or "", class_="fw-bold"),
            ui.tags.pre(pilha, class_="mon-traceback"),
        )

    @render.ui
    def css_largura():
        larguras = [ColunaLargura(c, _LARGURA[c]) for c in ORDEM]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela')}", larguras))
