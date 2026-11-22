import pandas as pd
import polars as pl
from faicons import icon_svg
from pyecharts import options as opts
from pyecharts.charts import Bar
from shiny import module, reactive, render, ui

from core.config import APPS_MONITORADOS, FONTES_LOG
from core.cores import DESTAQUE, STATUS_FORA_DO_AR, STATUS_NO_AR, TEXTO_ESCURO
from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.leitura_logs import atualizar, sessoes_por_hora
from core.pyecharts_shiny import renderizar
from core.status import consultar_todos
from core.visibilidade import pagina_visivel

INTERVALO_ATUALIZACAO_S = 15

COLUNAS = {
    "app": "App",
    "situacao": "Situação",
    "conectados": "Conectados",
    "no_ar_desde": "No ar há",
    "erros": "Erros hoje",
}
ORDEM = list(COLUNAS)
_LARGURA = {"app": 130, "situacao": 120, "conectados": 120, "no_ar_desde": 130, "erros": 110}


def _duracao(segundos) -> str:
    if segundos is None:
        return "-"
    horas, resto = divmod(int(segundos), 3600)
    minutos = resto // 60
    if horas:
        return f"{horas}h {minutos:02d}min"
    return f"{minutos}min"


@module.ui
def pag_visao_geral_ui():
    return ui.div(
        ui.output_ui("cards_status"),
        ui.card(
            ui.card_header("Situação dos aplicativos"),
            ui.output_ui("css_largura"),
            ui.div(ui.output_data_frame("tabela"), id="grupo-tabela-visao", class_="tabela-resize"),
            class_="my-4",
        ),
        ui.card(
            ui.card_header("Conexões abertas ao longo do dia (por hora)"),
            ui.output_ui("grafico_horas"),
        ),
        class_="pagina-monitoramento",
    )


@module.server
def pag_visao_geral_server(input, output, session, valor_navset: str = "vgeral"):
    @reactive.calc
    async def saude_dos_apps() -> list[dict]:
        reactive.invalidate_later(INTERVALO_ATUALIZACAO_S)
        if not pagina_visivel(session, valor_navset):
            return []
        return await consultar_todos(APPS_MONITORADOS)

    @reactive.calc
    def erros_por_app() -> dict:
        from core.leitura_logs import ler_erros

        atualizar(FONTES_LOG)
        base = ler_erros()
        if base.height == 0:
            return {}
        contagem = base.group_by("app").agg(pl.len().alias("n"))
        return dict(zip(contagem["app"], contagem["n"]))

    @render.ui
    async def cards_status():
        dados = await saude_dos_apps()
        if not dados:
            return None
        no_ar = sum(1 for d in dados if d["no_ar"])
        conectados = sum(d["sessoes_ativas"] or 0 for d in dados)
        pessoas = len({(d["nome"], s.get("usuario") or s["id"]) for d in dados for s in d["sessoes"]})
        return ui.layout_columns(
            ui.value_box(
                "Aplicativos no ar",
                f"{no_ar} de {len(dados)}",
                showcase=icon_svg("server"),
                theme=ui.value_box_theme(
                    bg=STATUS_NO_AR if no_ar == len(dados) else STATUS_FORA_DO_AR,
                    fg=TEXTO_ESCURO,
                ),
            ),
            ui.value_box(
                "Sessões conectadas agora",
                str(conectados),
                showcase=icon_svg("users"),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#FFF"),
            ),
            ui.value_box(
                "Pessoas diferentes",
                str(pessoas),
                showcase=icon_svg("user-check"),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#FFF"),
            ),
        )

    @render.data_frame
    async def tabela():
        dados = await saude_dos_apps()
        if not dados:
            return render.DataTable(
                pd.DataFrame({"Aviso": ["Consultando os aplicativos..."]}),
                summary=False,
                filters=False,
                selection_mode="none",
            )
        erros = erros_por_app()
        base = pd.DataFrame(
            [
                {
                    "app": d["nome"],
                    "situacao": "No ar" if d["no_ar"] else "Fora do ar",
                    "conectados": d["sessoes_ativas"] if d["sessoes_ativas"] is not None else "-",
                    "no_ar_desde": _duracao(d["uptime_s"]),
                    "erros": erros.get(d["nome"], 0),
                }
                for d in dados
            ]
        )
        estilos = [
            {
                "rows": [posicao],
                "cols": [ORDEM.index("situacao")],
                "style": {"background-color": STATUS_NO_AR if linha["situacao"] == "No ar" else STATUS_FORA_DO_AR},
            }
            for posicao, linha in base.iterrows()
        ]
        return render.DataTable(
            base.rename(columns=COLUNAS),
            styles=estilos,
            height="30vh",
            summary=False,
            filters=False,
            selection_mode="none",
        )

    @render.ui
    def css_largura():
        larguras = [ColunaLargura(c, _LARGURA[c]) for c in ORDEM]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela')}", larguras))

    @render.ui
    def grafico_horas():
        reactive.invalidate_later(INTERVALO_ATUALIZACAO_S)
        if not pagina_visivel(session, valor_navset):
            return None
        atualizar(FONTES_LOG)
        base = sessoes_por_hora()
        if base.height == 0:
            return ui.p("Nenhuma conexão registrada hoje ainda.", class_="text-muted")

        horas = sorted(base["hora"].unique().to_list())
        grafico = Bar()
        grafico.add_xaxis([f"{h}h" for h in horas])
        for nome in sorted(base["app"].unique().to_list()):
            do_app = base.filter(pl.col("app") == nome)
            por_hora = dict(zip(do_app["hora"], do_app["sessoes"]))
            grafico.add_yaxis(nome, [int(por_hora.get(h, 0)) for h in horas], stack="total")
        grafico.set_global_opts(
            tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="shadow"),
            legend_opts=opts.LegendOpts(pos_top="0%"),
            yaxis_opts=opts.AxisOpts(name="Sessões abertas"),
        )
        grafico.set_series_opts(label_opts=opts.LabelOpts(is_show=False))
        return ui.HTML(renderizar(grafico, altura="34vh"))
