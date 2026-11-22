from __future__ import annotations

import asyncio
import io
from datetime import date
from urllib.parse import parse_qs

import pandas as pd
from faicons import icon_svg
from loguru import logger
from shiny import module, reactive, render, ui

from core import cores
from core.carregamento import com_carregamento
from core.config import REVENDA_PADRAO
from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.tabela_paginada import TabelaPaginada
from core.visibilidade import pagina_visivel

from .Dados import dados_curva_abc as d

_FILTROS = {
    "canal": "CANAL",
    "porte": "PORTE",
    "cidade": "CIDADE",
    "cliente": "CLIENTE",
    "produto": "PRODUTO_GENERICO",
    "tipo_doc": "TIPO_DOC",
}


def pag_curva_abc_ui(_revenda: str | None):
    return com_carregamento(curva_abc_ui("curva_abc"))


def pag_curva_abc_server(versao_cache=None):
    curva_abc_server("curva_abc", versao_cache=versao_cache)


@module.ui
def curva_abc_ui():
    def filtro(id_: str, rotulo: str, *, multiple: bool = True):
        opcoes = {"dropdownParent": "body", "dropdownClass": "selectize-dropdown dv-selectize-dropdown"}
        if multiple:
            opcoes.update({"placeholder": "Todos", "plugins": ["remove_button"]})
        return ui.div(
            ui.input_selectize(id_, rotulo, choices={}, multiple=multiple, options=opcoes),
            class_="filtro-dv",
        )

    return ui.div(
        ui.card(
            ui.div(
                filtro("top", "Top", multiple=False),
                filtro("canal", "Canal"),
                filtro("porte", "Classificação"),
                filtro("cidade", "Cidade"),
                filtro("cliente", "Cliente"),
                filtro("produto", "Produto"),
                filtro("tipo_doc", "Tipo Doc"),
                filtro("mes", "Mês", multiple=False),
                ui.input_action_button(
                    "limpar", None, icon=icon_svg("eraser"), title="Limpar filtros", class_="btn-primary btn-limpar-dv"
                ),
                class_="filtros-dv filtros-curva-abc",
            )
        ),
        ui.output_ui("mensagem"),
        ui.div(
            ui.output_ui("card_hl"),
            ui.output_ui("card_faturamento"),
            ui.output_ui("card_qtd"),
            class_="cards-curva-abc",
        ),
        ui.card(
            ui.card_header(
                ui.div(
                    ui.span("Curva ABC - Clientes"),
                    ui.download_button(
                        "baixar", None, icon=icon_svg("file-excel"), title="Baixar Excel", class_="btn-success"
                    ),
                    class_="d-flex justify-content-between align-items-center w-100",
                )
            ),
            ui.div(ui.output_data_frame("tabela"), class_="dv-tabela tabela-curva-abc tabela-resize"),
            ui.output_ui("controles"),
            ui.output_ui("css_largura_tabela"),
        ),
        class_="dv-modulo painel-curva-abc",
    )


def _selecionados(valor) -> tuple[str, ...]:
    if valor in (None, ""):
        return ()
    if isinstance(valor, str):
        return (valor,)
    return tuple(valor)


def _numero(valor: float, casas: int = 2) -> str:
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


@module.server
def curva_abc_server(input, output, session, versao_cache=None):
    def _versao_cache() -> None:
        if versao_cache is not None:
            versao_cache()

    erro = reactive.value(None, name="erro")
    paginador = TabelaPaginada("tabela", input, session)

    @reactive.calc
    def revenda_atual():
        valores = parse_qs(session.clientdata.url_search().lstrip("?")).get("REVENDA")
        return valores[0] if valores else REVENDA_PADRAO

    @reactive.effect
    async def _carrega_meses():
        if not pagina_visivel(session, "cabc"):
            return
        try:
            meses = await asyncio.to_thread(d.meses_disponiveis, revenda_atual())
            nomes = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
            escolhas = {m: f"{nomes[int(m[-2:]) - 1]}/{m[:4]}" if len(m) == 6 else m for m in meses}
            ui.update_selectize("mes", choices=escolhas, selected=meses[0] if meses else None)
            ui.update_selectize(
                "top",
                choices={
                    "0": "Todos",
                    "10": "10 maiores",
                    "25": "25 maiores",
                    "50": "50 maiores",
                    "100": "100 maiores",
                },
                selected="0",
            )
            erro.set(None if meses else "Nenhum mês disponível para a revenda selecionada.")
        except Exception:
            logger.exception("Falha ao carregar meses da Curva ABC")
            erro.set("Não foi possível consultar a Curva ABC. Verifique a conexão com o banco local.")

    @reactive.calc
    async def dados_base():
        _versao_cache()
        if not pagina_visivel(session, "cabc") or not input.mes():
            return pd.DataFrame()
        try:
            resultado = await asyncio.to_thread(d.consulta, revenda_atual(), input.mes())
            erro.set(None)
            return resultado
        except Exception:
            logger.exception("Falha ao consultar Curva ABC")
            erro.set("Não foi possível consultar os dados do mês selecionado.")
            return pd.DataFrame()

    @reactive.effect
    async def _atualiza_filtros():
        if not pagina_visivel(session, "cabc"):
            return
        dados = await dados_base()
        if dados.empty:
            return
        for input_id, coluna in _FILTROS.items():
            atuais = _selecionados(input[input_id]()) if input_id in input else ()
            opcoes = sorted(str(v) for v in dados[coluna].dropna().unique()) if coluna in dados else []
            ui.update_selectize(input_id, choices=opcoes, selected=[v for v in atuais if v in opcoes])

    @reactive.calc
    async def dados_filtrados():
        _versao_cache()
        resultado = (await dados_base()).copy()
        if resultado.empty:
            return resultado
        top = input.top() if "top" in input else "0"
        if top not in (None, "", "0"):
            resultado = resultado[pd.to_numeric(resultado["ORDEM"], errors="coerce") <= int(top)]
        for input_id, coluna in _FILTROS.items():
            valores = _selecionados(input[input_id]()) if input_id in input else ()
            if valores and coluna in resultado:
                resultado = resultado[resultado[coluna].astype(str).isin(valores)]
        return resultado.reset_index(drop=True)

    @reactive.effect
    async def _reiniciar_pagina():
        if not pagina_visivel(session, "cabc"):
            return
        await dados_filtrados()
        paginador.reiniciar()

    @reactive.effect
    @reactive.event(input.limpar)
    async def _limpar():
        ui.update_selectize("top", selected="0")
        for input_id in _FILTROS:
            ui.update_selectize(input_id, selected=[])
        try:
            meses = await asyncio.to_thread(d.meses_disponiveis, revenda_atual())
            if meses:
                ui.update_selectize("mes", selected=meses[0])
        except Exception:
            logger.exception("Falha ao atualizar os filtros da Curva ABC")
            erro.set("Não foi possível atualizar os filtros.")

    @render.ui
    def mensagem():
        return ui.div(erro(), class_="alert alert-danger") if erro() else None

    def _card(titulo: str, valor: str, icone: str):
        return ui.value_box(
            titulo,
            valor,
            showcase=icon_svg(icone),
            theme=ui.value_box_theme(bg=cores.CARD_FUNDO_CLARO, fg=cores.CARD_TEXTO_ESCURO),
            class_="card-dias-uteis",
        )

    @render.ui
    async def card_hl():
        dados = await dados_base()
        total = pd.to_numeric(dados.get("HL", pd.Series(dtype=float)), errors="coerce").sum()
        return _card("Total HL", _numero(total), "droplet")

    @render.ui
    async def card_faturamento():
        dados = await dados_base()
        total = pd.to_numeric(dados.get("FATURAMENTO", pd.Series(dtype=float)), errors="coerce").sum()
        return _card("Total Faturamento", f"R$ {_numero(total)}", "money-bill-wave")

    @render.ui
    async def card_qtd():
        dados = await dados_base()
        total = pd.to_numeric(dados.get("QTD_TOTAL", pd.Series(dtype=float)), errors="coerce").sum()
        return _card("Total Qtd (UMB)", _numero(total), "boxes-stacked")

    _COLUNAS_TABELA = [
        "ORDEM",
        "CODCLI",
        "NOME",
        "TIPO_DOC",
        "CIDADE",
        "PORTE",
        "CANAL",
        "VEN",
        "SUBORDINACAO",
        "DIAS_PRAZO",
        "CODRED",
        "PRODUTO_GENERICO",
        "HL",
        "VALOR_VENDA",
        "VALOR_DEVOLUCAO",
        "QTD_TOTAL",
        "QTD_DEVOLUCAO",
        "PERC_INDIVIDUAL",
        "PERC_ACUMULADO",
    ]
    _NOMES_TABELA = {
        "ORDEM": "#",
        "CODCLI": "Cód. Cliente",
        "NOME": "Razão Social",
        "TIPO_DOC": "Tipo",
        "CIDADE": "Cidade",
        "PORTE": "Classificação",
        "CANAL": "Canal",
        "VEN": "Vendedor",
        "SUBORDINACAO": "GA",
        "DIAS_PRAZO": "Prazo",
        "CODRED": "Cód. Produto",
        "PRODUTO_GENERICO": "Produto",
        "HL": "HL",
        "FATURAMENTO": "Faturamento",
        "VALOR_VENDA": "Venda (R$)",
        "VALOR_DEVOLUCAO": "Devolução (R$)",
        "QTD_TOTAL": "Qtd (UMB)",
        "QTD_DEVOLUCAO": "Devolução (UMB)",
        "PERC_INDIVIDUAL": "% Individual",
        "PERC_ACUMULADO": "% Acumulado",
    }

    def _colunas_visiveis(base: pd.DataFrame) -> list[str]:
        colunas = _COLUNAS_TABELA
        if "VALOR_VENDA" not in base or base["VALOR_VENDA"].isna().any():
            colunas = [c for c in _COLUNAS_TABELA if c != "VALOR_DEVOLUCAO"]
            colunas[colunas.index("VALOR_VENDA")] = "FATURAMENTO"
        return [c for c in colunas if c in base]

    _LARGURA_POR_COLUNA = {
        "ORDEM": 60,
        "CODCLI": 100,
        "NOME": 300,
        "TIPO_DOC": 80,
        "CIDADE": 130,
        "PORTE": 130,
        "CANAL": 120,
        "VEN": 110,
        "SUBORDINACAO": 90,
        "DIAS_PRAZO": 90,
        "CODRED": 110,
        "PRODUTO_GENERICO": 280,
        "HL": 90,
        "FATURAMENTO": 140,
        "VALOR_VENDA": 140,
        "VALOR_DEVOLUCAO": 140,
        "QTD_TOTAL": 110,
        "QTD_DEVOLUCAO": 130,
        "PERC_INDIVIDUAL": 110,
        "PERC_ACUMULADO": 110,
    }

    def _formatar_pagina(pagina: pd.DataFrame, colunas: list[str]) -> pd.DataFrame:
        resultado = pagina[colunas].copy() if colunas else pd.DataFrame()
        for coluna in ("HL", "QTD_TOTAL", "QTD_DEVOLUCAO"):
            if coluna in resultado:
                resultado[coluna] = pd.to_numeric(resultado[coluna], errors="coerce").map(
                    lambda v: "" if pd.isna(v) else _numero(v)
                )
        for coluna in ("FATURAMENTO", "VALOR_VENDA", "VALOR_DEVOLUCAO"):
            if coluna in resultado:
                resultado[coluna] = pd.to_numeric(resultado[coluna], errors="coerce").map(
                    lambda v: "" if pd.isna(v) else f"R$ {_numero(v)}"
                )
        for coluna in ("PERC_INDIVIDUAL", "PERC_ACUMULADO"):
            if coluna in resultado:
                resultado[coluna] = pd.to_numeric(resultado[coluna], errors="coerce").map(
                    lambda v: "" if pd.isna(v) else f"{_numero(v)}%"
                )
        return resultado.rename(columns=_NOMES_TABELA)

    @render.data_frame
    async def tabela():
        dados = await dados_filtrados()
        inicio, fim = paginador.janela(len(dados))
        pagina = dados.iloc[inicio:fim].reset_index(drop=True)
        colunas = [c for c in _colunas_visiveis(await dados_base()) if c in pagina]
        return render.DataTable(
            _formatar_pagina(pagina, colunas),
            height="58vh",
            summary=False,
            filters=False,
            selection_mode="none",
        )

    @render.ui
    async def controles():
        return paginador.controles(len(await dados_filtrados()))

    @render.ui
    async def css_largura_tabela():
        dados = await dados_filtrados()
        colunas = [c for c in _colunas_visiveis(await dados_base()) if c in dados.columns]
        larguras = [ColunaLargura(c, _LARGURA_POR_COLUNA.get(c, 100)) for c in colunas]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela')}", larguras))

    @render.download_button(filename=lambda: f"curva-abc-{date.today().isoformat()}.xlsx")
    async def baixar():
        buffer = io.BytesIO()
        dados = await dados_filtrados()
        await asyncio.to_thread(dados.to_excel, buffer, index=False, engine="openpyxl")
        yield buffer.getvalue()
