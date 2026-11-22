import asyncio
from urllib.parse import parse_qs

import pandas as pd
from faicons import icon_svg
from shiny import module, reactive, render, ui

from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.visibilidade import pagina_visivel

from .Dados import dados_comodato as d
from .Dados import tabela_comodato as ti

_LARGURA_SALDO = {
    "Nome": 150,
    "Recolha Ano": 110,
    "Empréstimo Ano": 110,
    "Saldo Ano": 100,
    "Recolha Mês": 110,
    "Empréstimo Mês": 110,
    "Saldo Mês": 100,
    "Status PLP": 100,
    "Status Doc": 100,
    "Caixa 1L": 90,
    "Caixa 300": 90,
    "Caixa 600ml": 90,
    "Total MAR 600": 110,
    "Caixa MAR 600": 110,
    "Bônus MAR 600": 110,
}

_IMAGEM_CABECALHO_SALDO = {
    "Caixa 1L": "107522",
    "Caixa 300": "152597",
    "Total MAR 600": "215209",
    "Caixa MAR 600": "215209",
    "Bônus MAR 600": "215209",
    "Caixa 600ml": "107522",
}


def _css_imagem_cabecalho(selector: str, colunas: list[str]) -> str:
    regras = []
    for posicao, coluna in enumerate(colunas, start=1):
        codigo = _IMAGEM_CABECALHO_SALDO.get(coluna)
        if not codigo:
            continue
        regras.append(
            f"{selector} table thead th:nth-child({posicao}) {{"
            f' background-image: url("img/produtos/{codigo}.svg");'
            " background-repeat: no-repeat; background-size: 26px 26px;"
            " background-position: 4px center; padding-left: 32px !important; }"
        )
    return "\n".join(regras)


@module.ui
def comodatos_saldo_ui():
    return ui.div(
        ui.card(
            ui.div(
                ui.div(
                    ui.input_selectize(
                        "produto",
                        "Produto",
                        choices={},
                        multiple=True,
                        options={
                            "placeholder": "Todos",
                            "dropdownParent": "body",
                            "dropdownClass": "selectize-dropdown comod-selectize-dropdown",
                            "hideSelected": False,
                            "plugins": ["remove_button"],
                        },
                    ),
                    class_="filtro-comod",
                ),
                ui.div(
                    ui.input_selectize(
                        "mes",
                        "Mês",
                        choices=d.listar_meses_disponiveis(),
                        selected="Mês Atual",
                        multiple=False,
                        options={
                            "dropdownParent": "body",
                            "dropdownClass": "selectize-dropdown comod-selectize-dropdown",
                        },
                    ),
                    class_="filtro-comod",
                ),
                ui.input_action_button(
                    "limpar",
                    None,
                    icon=icon_svg("eraser", a11y="deco"),
                    class_="btn-primary btn-limpar-comod",
                    title="Limpar filtros",
                ),
                class_="filtros-comod",
            ),
        ),
        ui.card(
            ui.card_header("Saldo Revendas"),
            ui.output_ui("corpo_tabela_saldo"),
        ),
        class_="comodatos-modulo",
    )


@module.server
def comodatos_saldo_server(input, output, session, valor_navset: str, versao_cache):
    def revenda_atual() -> str | None:
        query_string = session.clientdata.url_search()
        valores = parse_qs(query_string.lstrip("?")).get("REVENDA")
        if valores:
            return valores[0]
        # Portfólio: sem a URL do portal, vale a revenda escolhida no cabeçalho.
        raiz = session.root_scope().input
        return (raiz.revenda_escolhida() if "revenda_escolhida" in raiz else "Natal") or None

    @reactive.calc
    async def produtos_geral() -> list:
        return await asyncio.to_thread(d.produtos_livro_fiscal)

    @reactive.effect
    async def _atualiza_opcoes_produto():
        if not pagina_visivel(session, valor_navset):
            return
        if input.produto():
            return
        produtos = await produtos_geral()
        if produtos.height == 0:
            return
        opcoes = {
            row["PRODUTO"]: f"{row['PRODUTO']} - {row['PRODUTO_GENERICO']}"
            for row in produtos.unique(subset=["PRODUTO"]).iter_rows(named=True)
        }
        ui.update_selectize("produto", choices=opcoes, session=session)

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar_filtros():
        ui.update_selectize("produto", selected=[], session=session)
        ui.update_selectize("mes", selected="Mês Atual", session=session)

    @reactive.calc
    async def saldo() -> list:
        versao_cache()
        produtos_filtro = list(input.produto()) if input.produto() else None
        return await asyncio.to_thread(d.saldo_geral, input.mes(), produtos_filtro, revenda_atual())

    @reactive.calc
    async def tabela_saldo_pronta():
        tabela = await saldo()
        if tabela.height == 0:
            return pd.DataFrame(), []
        return await asyncio.to_thread(ti.construir_saldo_df, tabela)

    @render.ui
    async def corpo_tabela_saldo():
        pandas_df, _estilos = await tabela_saldo_pronta()
        if pandas_df.empty:
            return ui.p("Sem dados para os filtros selecionados.")
        return ui.div(
            ui.output_ui("css_largura_tabela_saldo"),
            ui.output_data_frame("tabela_saldo"),
            class_="comod-tabela tabela-resize",
        )

    @render.data_frame
    async def tabela_saldo():
        pandas_df, estilos = await tabela_saldo_pronta()
        return render.DataTable(
            pandas_df, styles=estilos, height="58vh", summary=False, filters=False, selection_mode="none"
        )

    @render.ui
    async def css_largura_tabela_saldo():
        pandas_df, _estilos = await tabela_saldo_pronta()
        larguras = [ColunaLargura(c, _LARGURA_SALDO.get(c, 100)) for c in pandas_df.columns]
        return ui.tags.style(
            gerar_css_larguras(f"#{session.ns('tabela_saldo')}", larguras)
            + _css_imagem_cabecalho(f"#{session.ns('tabela_saldo')}", list(pandas_df.columns))
        )


def pag_comodatos_saldo_ui():
    return comodatos_saldo_ui("comod_saldo")


def pag_comodatos_saldo_server(versao_cache):
    comodatos_saldo_server("comod_saldo", valor_navset="comod_vas", versao_cache=versao_cache)
