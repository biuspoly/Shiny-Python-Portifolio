import asyncio
import io
from datetime import date

from faicons import icon_svg
from pyecharts import options as opts
from pyecharts.charts import Bar, Line
from shiny import module, reactive, render, ui

from core.compat import para_pandas
from core.cores import ACESSO_ATENCAO, ACESSO_ATIVO, ACESSO_INATIVO, ACESSO_NUNCA, DESTAQUE
from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.pyecharts_shiny import renderizar
from core.tabela_paginada import TabelaPaginada
from pages.Visao_Geral.Dados.dados_visao_geral import (
    kpis_acesso,
    tendencia_acessos,
    ultimo_acesso_usuario,
)

INTERVALO_ATUALIZACAO_S = 60

_RÓTULOS = {
    "login": "Login",
    "nome": "Nome",
    "cargo": "Cargo",
    "revenda": "Revenda",
    "ultimo_acesso": "Último Acesso",
    "acessos_30d": "Acessos (30d)",
    "dias_inativo": "Dias Sem Acesso",
}

_ORDEM_COLUNAS_TABELA = ["Login", "Nome", "Cargo", "Revenda", "Último Acesso", "Acessos (30d)", "Dias Sem Acesso"]
_LARGURA_POR_COLUNA = {
    "Login": 140,
    "Nome": 200,
    "Cargo": 160,
    "Revenda": 160,
    "Último Acesso": 160,
    "Acessos (30d)": 120,
    "Dias Sem Acesso": 140,
}


def _carregar_tudo() -> dict:
    return {
        "kpis": kpis_acesso(),
        "tendencia": tendencia_acessos(),
        "ultimo": ultimo_acesso_usuario(),
    }


@module.ui
def pag_visao_geral_ui() -> ui.Tag:
    return ui.div(
        ui.output_ui("kpis"),
        ui.card(
            ui.card_header("Tendência de Acessos — últimos 30 dias"),
            ui.output_ui("grafico_tendencia"),
            class_="my-4",
        ),
        ui.card(
            ui.card_header(
                ui.div(
                    ui.span("Último Acesso por Usuário"),
                    ui.download_button(
                        "exportar",
                        None,
                        icon=icon_svg("download", a11y="deco"),
                        class_="btn-exportar-acessos ms-auto",
                    ),
                    class_="d-flex justify-content-between align-items-center",
                ),
            ),
            ui.div(ui.output_data_frame("tabela"), class_="tabela-resize"),
            ui.output_ui("controles_tabela"),
            ui.output_ui("css_largura_tabela"),
        ),
        class_="acessos-modulo",
    )


@module.server
def pag_visao_geral_server(input, output, session):
    @reactive.calc
    async def dados():
        reactive.invalidate_later(INTERVALO_ATUALIZACAO_S)
        return await asyncio.to_thread(_carregar_tudo)

    @render.ui
    async def kpis():
        k = (await dados())["kpis"]
        return ui.layout_columns(
            ui.value_box(
                "Usuários Ativos",
                k["total_usuarios"],
                showcase=icon_svg("users"),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#fff"),
            ),
            ui.value_box(
                "Painéis Ativos",
                k["total_paineis"],
                showcase=icon_svg("desktop"),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#fff"),
            ),
            ui.value_box(
                "Acessos (7 dias)",
                k["acessos_7_dias"],
                showcase=icon_svg("right-to-bracket"),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#fff"),
            ),
            ui.value_box(
                "Usuários Ativos (7 dias)",
                k["usuarios_ativos_7_dias"],
                showcase=icon_svg("user-check"),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#fff"),
            ),
        )

    @render.ui
    async def grafico_tendencia():
        df = (await dados())["tendencia"]
        if df.height == 0:
            return ui.p("Sem dados no período.")

        datas = [d.strftime("%d/%m") for d in df["data"].to_list()]
        total = df["total_acessos"].to_list()
        distintos = df["usuarios_distintos"].to_list()

        bar = (
            Bar()
            .add_xaxis(datas)
            .add_yaxis("Total de acessos", total, color=DESTAQUE, z=1)
            .extend_axis(yaxis=opts.AxisOpts(name="Usuários únicos", position="right"))
            .set_global_opts(
                xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)),
                yaxis_opts=opts.AxisOpts(name="Total acessos"),
                tooltip_opts=opts.TooltipOpts(trigger="axis"),
                legend_opts=opts.LegendOpts(pos_top="0%"),
            )
        )
        linha = Line().add_xaxis(datas).add_yaxis("Usuários únicos", distintos, yaxis_index=1, color="#E74C3C", z=2)
        return ui.HTML(renderizar(bar.overlap(linha), altura="300px"))

    paginador = TabelaPaginada("pag_ultimo_acesso", input, session)

    async def _tabela_pronta():
        df = (await dados())["ultimo"].rename(_RÓTULOS)
        pandas_df = df.with_columns(
            df["Último Acesso"].dt.strftime("%d/%m/%Y %H:%M").fill_null(""),
        ).pipe(para_pandas)

        estilos = []
        for posicao, dias in enumerate(df["Dias Sem Acesso"].to_list()):
            if dias is None:
                cor = ACESSO_NUNCA
            elif dias > 30:
                cor = ACESSO_INATIVO
            elif dias > 7:
                cor = ACESSO_ATENCAO
            else:
                cor = ACESSO_ATIVO
            estilos.append(
                {
                    "rows": [posicao],
                    "cols": ["Dias Sem Acesso"],
                    "style": {"color": cor, "font-weight": "bold"},
                }
            )
        return pandas_df, estilos

    @render.data_frame
    async def tabela():
        pandas_df, estilos = await _tabela_pronta()
        fatia, estilos_fatia = paginador.fatiar_com_estilos(pandas_df, estilos)
        return render.DataTable(
            fatia,
            styles=estilos_fatia,
            height="50vh",
            summary=False,
            filters=False,
            selection_mode="none",
        )

    @render.ui
    async def controles_tabela():
        pandas_df, _ = await _tabela_pronta()
        return paginador.controles(len(pandas_df))

    @render.ui
    async def css_largura_tabela():
        larguras = [ColunaLargura(c, _LARGURA_POR_COLUNA[c]) for c in _ORDEM_COLUNAS_TABELA]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela')}", larguras))

    @render.download_button(filename=lambda: f"ultimo-acesso-{date.today().isoformat()}.xlsx")
    async def exportar():
        pandas_df, _ = await _tabela_pronta()
        buffer = io.BytesIO()
        pandas_df.to_excel(buffer, index=False, engine="openpyxl")
        yield buffer.getvalue()
