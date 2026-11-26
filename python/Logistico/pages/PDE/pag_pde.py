import asyncio
import io
from datetime import date
from urllib.parse import parse_qs

import pandas as pd
import polars as pl
from faicons import icon_svg
from loguru import logger
from shiny import module, reactive, render, ui

from core.aviso import corpo_aviso
from core.compat import para_pandas
from core.cores import PDE_COLUNA_DESTAQUE
from core.crossfilter import usar_crossfilter
from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.tabela_paginada import TabelaPaginada
from core.visibilidade import pagina_visivel

from .Dados import dados_pde as d
from .Dados import informar_pde as ip
from .Dados import tabela_pde as ti

VALOR_NAVSET = "pde"

FILTROS = [
    ("empresa", "Revenda", "EMPRESA", 2),
    ("placa", "Placa", "PLACA", 1),
    ("motorista", "Motorista", "MOTORISTA", 2),
    ("rota", "Rota", "ROTA", 2),
]

_LARGURA_PDE = {
    "Empresa": 110,
    "Romaneio": 100,
    "Data\nSaída": 90,
    "Hora\nSaída": 75,
    "Dias de\nrota": 65,
    "Placa": 85,
    "Motorista": 150,
    "Ajudante 1": 120,
    "Ajudante 2": 120,
    "Rota": 130,
    "Obs": 150,
    "Peso\nMax": 80,
    "Peso\nRom": 80,
    "% Util": 70,
    "Qtd\nEnt": 65,
    "Qtd\nNf": 65,
    "Fat Saída": 110,
    "Qtd\nDev": 65,
    "Fat Dev": 100,
    "% Dev": 70,
    "Data\nChegada": 90,
    "Hora\nChegada": 80,
    "Km\nSaída": 80,
    "Km\nChegada": 85,
    "Km\nRodados": 85,
}

ALTURA_TABELA = "46vh"

CAMPOS_FORMULARIO = [
    ("hr_saida", "Hora de saída", "HR_SAIDA", "HH:MM", 2),
    ("hr_chegada", "Hora de chegada", "HR_FIM", "HH:MM", 2),
    ("km_saida", "Km de saída", "KM_INI", "", 2),
    ("km_chegada", "Km de chegada", "KM_FIM", "", 2),
    ("ajudante1", "Ajudante 1", "AJUDANTE_1", "Opcional", 2),
    ("ajudante2", "Ajudante 2", "AJUDANTE_2", "Opcional", 2),
    ("obs", "Observação", "OBS", "Opcional", 4),
]


def _filtro_ui(id_filtro: str, rotulo: str, colunas: int, estilo_extra: str = "") -> ui.Tag:
    return ui.div(
        ui.input_selectize(
            id_filtro,
            rotulo,
            choices=[],
            multiple=True,
            options={
                "placeholder": "Todos",
                "dropdownParent": "body",
                "dropdownClass": "selectize-dropdown pde-selectize-dropdown",
                "hideSelected": False,
                "plugins": ["remove_button"],
            },
        ),
        class_="filtro-pde",
        style=f"grid-column: span {colunas};{estilo_extra}",
    )


def _campo_ui(id_campo: str, rotulo: str, dica: str, colunas: int) -> ui.Tag:
    return ui.div(
        ui.input_text(id_campo, rotulo, placeholder=dica),
        class_="campo-pde",
        style=f"grid-column: span {colunas};",
    )


def _mostra_filtro_revenda(revenda: str | None) -> bool:
    return not revenda


@module.ui
def pde_ui(revenda: str | None = None):
    esconde_revenda = "" if _mostra_filtro_revenda(revenda) else " display: none;"
    return ui.div(
        ui.card(
            ui.div(
                ui.div(
                    ui.input_selectize(
                        "data",
                        "Data de saída",
                        choices=[],
                        multiple=True,
                        options={
                            "placeholder": "Todas",
                            "dropdownParent": "body",
                            "dropdownClass": "selectize-dropdown pde-selectize-dropdown",
                            "hideSelected": False,
                            "plugins": ["remove_button"],
                        },
                    ),
                    class_="filtro-pde",
                    style="grid-column: span 2;",
                ),
                *[_filtro_ui(i, r, c, esconde_revenda if i == "empresa" else "") for i, r, _coluna, c in FILTROS],
                ui.input_action_button(
                    "limpar",
                    None,
                    icon=icon_svg("eraser", a11y="deco"),
                    class_="btn-primary btn-limpar-pde",
                    title="Limpar filtros",
                ),
                class_="filtros-pde",
            ),
        ),
        ui.card(
            ui.card_header("Informar dados da entrega"),
            ui.div(
                ui.div(
                    ui.input_selectize(
                        "romaneio",
                        "Romaneio",
                        choices=[],
                        options={
                            "dropdownParent": "body",
                            "dropdownClass": "selectize-dropdown pde-selectize-dropdown",
                        },
                    ),
                    class_="campo-pde",
                    style="grid-column: span 3;",
                ),
                *[_campo_ui(i, r, dica, c) for i, r, _coluna, dica, c in CAMPOS_FORMULARIO],
                ui.div(
                    ui.input_action_button(
                        "gravar",
                        "Gravar",
                        class_="btn-primary btn-gravar-pde",
                    ),
                    class_="campo-pde campo-pde-botao",
                    style="grid-column: span 3;",
                ),
                class_="formulario-pde",
            ),
            ui.output_ui("aviso_formulario"),
        ),
        ui.card(
            ui.card_header(
                ui.div(
                    ui.span("Planilha de Entregas"),
                    ui.download_button(
                        "exportar",
                        None,
                        icon=icon_svg("file-excel", a11y="deco"),
                        class_="btn-exportar-pde ms-auto",
                        title="Baixar em Excel o que está filtrado",
                    ),
                    class_="d-flex align-items-center w-100",
                )
            ),
            ui.output_ui("corpo_tabela"),
        ),
        class_="pde-modulo",
    )


@module.server
def pde_server(input, output, session):
    versao = reactive.value(0, name="versao_pde")
    ultimo_resultado = reactive.value(None, name="ultimo_resultado_pde")

    @reactive.calc
    def revenda_atual() -> str | None:
        query_string = session.clientdata.url_search()
        valores = parse_qs(query_string.lstrip("?")).get("REVENDA")
        return valores[0] if valores else None

    @reactive.calc
    async def base_revenda() -> pl.DataFrame:
        versao()
        base = await asyncio.to_thread(d.carregar_pde)
        return d.janela_recente(d.filtrar_por_revenda(base, revenda_atual()))

    @reactive.calc
    async def base_filtrada() -> pl.DataFrame:
        base = await base_revenda()
        if base.is_empty():
            return base
        datas = input.data() if "data" in input else ()
        if datas:
            base = base.filter(pl.col("DT_SAIDA").is_in([int(v) for v in datas]))
        for id_filtro, _rotulo, coluna, _colunas in FILTROS:
            valores = input[id_filtro]()
            if valores:
                base = base.filter(pl.col(coluna).is_in(list(valores)))
        return base

    usar_crossfilter(
        input,
        session,
        [(i, coluna) for i, _r, coluna, _c in FILTROS],
        base_filtrada,
        valor_navset=VALOR_NAVSET,
    )

    _ultimas_datas: dict[str, dict] = {}

    @reactive.effect
    async def _atualiza_datas():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        datas = d.datas_disponiveis(await base_revenda())
        rotulos = {str(v): ti.data_aaaammdd(v) for v in datas}
        if _ultimas_datas.get("opcoes") == rotulos:
            return
        _ultimas_datas["opcoes"] = rotulos
        with reactive.isolate():
            atuais = [v for v in (input.data() if "data" in input else ()) if v in rotulos]
        selecionadas = atuais or ([next(iter(rotulos))] if rotulos else [])
        ui.update_selectize("data", choices=rotulos, selected=selecionadas, session=session)

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar_filtros():
        for id_filtro, _rotulo, _coluna, _colunas in FILTROS:
            ui.update_selectize(id_filtro, selected=[], session=session)

    _ultimos_romaneios: dict[str, dict] = {}

    @reactive.effect
    async def _atualiza_romaneios():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        escolhas = d.romaneios_para_editar(await base_filtrada())
        rotulos = {
            chave: ti.rotulo_romaneio_editar(dados["romaneio"], dados["placa"], dados["dt_saida"])
            for chave, dados in escolhas.items()
        }
        if _ultimos_romaneios.get("opcoes") == rotulos:
            return
        _ultimos_romaneios["opcoes"] = rotulos
        with reactive.isolate():
            atual = input.romaneio() if "romaneio" in input else None
        selecionado = atual if atual in rotulos else (next(iter(rotulos), None))
        ui.update_selectize("romaneio", choices=rotulos, selected=selecionado, session=session)

    @reactive.effect
    async def _preencher_formulario():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        chave = input.romaneio() if "romaneio" in input else None
        linha = d.linha_do_romaneio(await base_revenda(), chave)
        for id_campo, _rotulo, coluna, _dica, _colunas in CAMPOS_FORMULARIO:
            valor = "" if linha is None else linha.get(coluna)
            texto = "" if valor in (None, 0, "00:00") else str(valor).strip()
            ui.update_text(id_campo, value=texto, session=session)

    @reactive.effect
    @reactive.event(input.gravar)
    async def _gravar():
        chave = input.romaneio() if "romaneio" in input else None
        linha = d.linha_do_romaneio(await base_revenda(), chave)
        if linha is None:
            ultimo_resultado.set(("error", "Escolha um romaneio antes de gravar."))
            return
        valores = {coluna: input[id_campo]() for id_campo, _rotulo, coluna, _dica, _colunas in CAMPOS_FORMULARIO}
        try:
            alteradas = await asyncio.to_thread(ip.gravar, linha["CNPJ_EMP"], linha["ROMANEIO"], valores)
        except ValueError as erro:
            ultimo_resultado.set(("warning", str(erro)))
            return
        except Exception:
            logger.exception(f"PDE: falha ao gravar o romaneio {linha['ROMANEIO']}")
            ultimo_resultado.set(("error", "Não foi possível gravar. Tente novamente."))
            return

        if alteradas == 0:
            ultimo_resultado.set(("warning", "Nenhuma linha foi alterada -- o romaneio não está mais na planilha."))
            return
        try:
            await asyncio.to_thread(ip.regravar_parquet)
        except Exception:
            logger.exception("PDE: falha ao regravar o cache depois de gravar")
            ultimo_resultado.set(("warning", "Dados gravados, mas a tela só vai mostrar na próxima atualização."))
            versao.set(versao() + 1)
            return
        ultimo_resultado.set(("success", f"Romaneio {linha['ROMANEIO']} atualizado."))
        versao.set(versao() + 1)

    @render.ui
    def aviso_formulario():
        resultado = ultimo_resultado()
        if resultado is None:
            return None
        tipo, texto = resultado
        return ui.div(corpo_aviso(texto, tipo=tipo), class_=f"aviso-pde aviso-pde-{tipo}")

    paginador = TabelaPaginada("pag_pde", input, session)

    @reactive.calc
    async def tabela_pronta() -> pd.DataFrame:
        return await asyncio.to_thread(ti.construir_df, await base_filtrada())

    @render.ui
    async def corpo_tabela():
        if (await base_filtrada()).is_empty():
            return ui.p("Sem dados para os filtros selecionados.")
        return ui.div(
            ui.output_ui("css_largura"),
            ui.output_data_frame("tabela"),
            ui.output_ui("controles"),
            id=session.ns("resize_pde"),
            class_="pde-tabela tabela-resize",
        )

    @render.data_frame
    async def tabela():
        pandas_df = await tabela_pronta()
        fatia = paginador.fatiar(pandas_df)
        return render.DataTable(
            fatia,
            styles=ti.estilos_destaque(fatia, PDE_COLUNA_DESTAQUE),
            height=ALTURA_TABELA,
            summary=False,
            filters=False,
            selection_mode="none",
        )

    @render.ui
    async def controles():
        return paginador.controles(len(await tabela_pronta()))

    @render.ui
    async def css_largura():
        pandas_df = await tabela_pronta()
        larguras = [ColunaLargura(c, _LARGURA_PDE.get(c, 100)) for c in pandas_df.columns]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela')}", larguras))

    @reactive.effect
    async def _reinicia_pagina():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        await base_filtrada()
        paginador.reiniciar()

    @render.download_button(filename=lambda: f"pde-{date.today().isoformat()}.xlsx")
    async def exportar():
        base = await base_filtrada()
        buffer = io.BytesIO()
        await asyncio.to_thread(_gravar_excel, base, buffer)
        yield buffer.getvalue()


def _gravar_excel(base: pl.DataFrame, buffer) -> None:
    colunas = [c for c in ti.COLUNAS if c in base.columns]
    tabela = (
        base.select(colunas).sort(["DT_SAIDA", "ROMANEIO"], descending=[True, False], nulls_last=True)
        if colunas
        else base
    )
    pandas_df = para_pandas(tabela).rename(columns={c: ti.rotulo_uma_linha(c) for c in tabela.columns})
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pandas_df.to_excel(writer, index=False)


def pag_pde_ui(revenda: str | None = None):
    return pde_ui("pde", revenda=revenda)


def pag_pde_server():
    pde_server("pde")
