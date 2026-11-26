from __future__ import annotations

import asyncio
from datetime import date
from urllib.parse import parse_qs

import pandas as pd
import polars as pl
from faicons import icon_svg
from loguru import logger
from shiny import module, reactive, render, ui

from core.cabecalho_dias import resumo_dias
from core.carregamento import com_carregamento
from core.config import REVENDA_PADRAO
from core.visibilidade import pagina_visivel

from .Dados import dados_diario_venda as d
from .Dados import tabela_diario_venda as t
from .Dados import tooltip_diario_venda as tt

_BASE_TODOS = "__todos__"


_MOSTRAR_BASE = False


def pag_diario_venda_ui():
    return com_carregamento(diario_venda_ui("diario_venda"))


def pag_diario_venda_server(versao_cache=None, resumo_cabecalho_dias=None):
    diario_venda_server("diario_venda", versao_cache=versao_cache, resumo_cabecalho_dias=resumo_cabecalho_dias)


@module.ui
def diario_venda_ui():

    return ui.div(
        ui.card(
            ui.div(
                ui.div(
                    ui.input_selectize(
                        "mes_dv",
                        "Mês",
                        choices={},
                        options={"dropdownParent": "body", "dropdownClass": "selectize-dropdown dv-selectize-dropdown"},
                    ),
                    class_="filtro-dv",
                ),
                ui.output_ui("ga_ven_dv_ui"),
                ui.input_action_button(
                    "limpar",
                    None,
                    icon=icon_svg("eraser", a11y="deco"),
                    class_="btn-primary btn-limpar-dv",
                    title="Limpar filtros",
                ),
                class_="filtros-dv",
            ),
        ),
        ui.output_ui("kpis_dv"),
        ui.navset_card_underline(
            ui.nav_panel(
                "Categorias",
                ui.output_ui("tabela_categorias_wrap"),
                ui.output_ui("css_cabecalho_categorias"),
                ui.div(
                    ui.span(class_="dv-legenda-alerta"),
                    "abaixo do ano anterior ou da meta",
                    ui.span(class_="dv-legenda-chave"),
                    "colunas principais do mês",
                    ui.span("passe o mouse com o histórico ativo para ver a evolução", class_="dv-legenda-dica"),
                    class_="dv-legenda",
                ),
                value="categorias",
            ),
            ui.nav_panel(
                "Produto / Família",
                ui.div(
                    ui.div(ui.output_data_frame("tabela_familia"), class_="dv-tabela-corpo"),
                    ui.div(ui.output_data_frame("tabela_familia_total"), class_="dv-tabela-rodape"),
                    class_="dv-tabela dv-tabela-com-rodape",
                ),
                ui.output_ui("css_cabecalho_familia"),
                value="familia",
            ),
            ui.nav_panel(
                "Outros volumes",
                ui.div(
                    ui.div(ui.output_data_frame("tabela_outros"), class_="dv-tabela-corpo"),
                    ui.div(ui.output_data_frame("tabela_outros_total"), class_="dv-tabela-rodape"),
                    class_="dv-tabela dv-tabela-com-rodape",
                ),
                ui.output_ui("css_cabecalho_outros"),
                value="outros",
            ),
            ui.nav_spacer(),
            ui.nav_control(
                ui.div(
                    ui.div(
                        ui.input_switch(
                            "familia_modo",
                            ui.TagList(ui.span("UMB", class_="dv-switch-off"), ui.span("HL", class_="dv-switch-on")),
                            value=False,
                        ),
                        class_="dv-switch-hl",
                        title="Unidade das tabelas de produto: UMB ou hectolitro",
                    ),
                    ui.output_ui("bt_meta_abp_ui"),
                    ui.output_ui("bt_meta_ano_ui"),
                    ui.output_ui("bt_toggle_historico_ui"),
                    class_="dv-card-toolbar",
                )
            ),
            id="aba_dv",
            selected="categorias",
        ),
        ui.div(
            ui.output_ui("painel_tooltip_grafico"),
            id="dv_tooltip_panel",
            class_="dv-tooltip-panel",
            onmouseenter="window.dvTooltipCancelarOcultar && window.dvTooltipCancelarOcultar()",
            onmouseleave="window.dvTooltipOcultar && window.dvTooltipOcultar()",
        ),
        class_="dv-modulo",
    )


@module.server
def diario_venda_server(input, output, session, versao_cache=None, resumo_cabecalho_dias=None):
    def _versao_cache() -> None:

        if versao_cache is not None:
            versao_cache()

    @reactive.calc
    def revenda_atual() -> str | None:
        query_string = session.clientdata.url_search()
        valores = parse_qs(query_string.lstrip("?")).get("REVENDA")
        return valores[0] if valores else REVENDA_PADRAO

    @reactive.calc
    def eh_grupo() -> bool:
        revenda = revenda_atual()
        return bool(revenda) and "GRUPO" in revenda

    @reactive.calc
    async def bases_foco():
        revenda = revenda_atual()
        if not revenda or eh_grupo():
            return {}
        return await asyncio.to_thread(d.bases_foco_dv, revenda)

    def _base_marcada() -> str | None:

        if "base_dv" not in input or input.base_dv() in (None, "", _BASE_TODOS):
            return None
        return input.base_dv()

    _opcoes_enviadas: dict[str, tuple] = {}

    @render.ui
    async def ga_ven_dv_ui():
        _opcoes_enviadas.clear()
        if eh_grupo():
            return None

        opcoes_selectize = {
            "placeholder": "Todos",
            "dropdownParent": "body",
            "dropdownClass": "selectize-dropdown dv-selectize-dropdown",
            "hideSelected": False,
            "plugins": ["remove_button"],
        }
        filtros = []

        bases = await bases_foco() if _MOSTRAR_BASE else ()
        if bases:
            opcoes_base = {k: v for k, v in opcoes_selectize.items() if k != "plugins"}
            filtros.append(
                ui.div(
                    ui.input_selectize(
                        "base_dv",
                        "Base",
                        choices={_BASE_TODOS: "Todos", **{b: b for b in sorted(bases)}},
                        selected=_BASE_TODOS,
                        multiple=False,
                        options=opcoes_base,
                    ),
                    class_="filtro-dv",
                )
            )
        filtros.extend(
            [
                ui.div(
                    ui.input_selectize("ga_dv", "Gerente de Área", choices=[], multiple=True, options=opcoes_selectize),
                    class_="filtro-dv",
                ),
                ui.div(
                    ui.input_selectize("ven_dv", "Vendedor", choices=[], multiple=True, options=opcoes_selectize),
                    class_="filtro-dv",
                ),
            ]
        )
        return ui.TagList(*filtros)

    @reactive.calc
    async def filtros_pairs():
        revenda = revenda_atual()
        if not revenda or eh_grupo():
            return None

        return await asyncio.to_thread(d.filtros_ga_ven_dv, revenda, _base_marcada())

    @reactive.effect
    async def _atualiza_opcoes_mes():
        if not pagina_visivel(session, "ven"):
            return
        revenda = revenda_atual()
        if not revenda:
            return
        meses = await asyncio.to_thread(d.meses_disponiveis_dv, revenda)

        opcoes = {mes: rotulo for rotulo, mes in meses.items()}
        atual = input.mes_dv() if "mes_dv" in input else None
        selecionado = atual if atual in opcoes else next(iter(opcoes), None)
        ui.update_selectize("mes_dv", choices=opcoes, selected=selecionado, session=session)

    @reactive.effect
    async def _crossfilter_filtros():
        if eh_grupo():
            return

        ga_atual = tuple(input.ga_dv() or ())
        ven_atual = tuple(input.ven_dv() or ())
        filtros = await filtros_pairs()
        if filtros is None:
            return
        pairs = filtros["pairs"]

        ga_sel = tuple(g for g in ga_atual if g in filtros["ga"])

        if ga_sel:
            ven_choices = sorted(set(pairs.filter(pairs["GA"].is_in(list(ga_sel)))["VEN"].to_list()))
        else:
            ven_choices = filtros["ven"]
        ven_sel = tuple(v for v in ven_atual if v in ven_choices)

        if ven_sel:
            ga_choices = sorted(set(pairs.filter(pairs["VEN"].is_in(list(ven_sel)))["GA"].to_list()) | set(ga_sel))
        else:
            ga_choices = filtros["ga"]

        ven_choices, ga_choices = tuple(ven_choices), tuple(ga_choices)
        if ven_choices != _opcoes_enviadas.get("ven") or ven_sel != ven_atual:
            ui.update_selectize("ven_dv", choices=list(ven_choices), selected=list(ven_sel), session=session)
            _opcoes_enviadas["ven"] = ven_choices
        if ga_choices != _opcoes_enviadas.get("ga") or ga_sel != ga_atual:
            ui.update_selectize("ga_dv", choices=list(ga_choices), selected=list(ga_sel), session=session)
            _opcoes_enviadas["ga"] = ga_choices

    @reactive.effect
    @reactive.event(input.limpar)
    async def _limpar_filtros():
        revenda = revenda_atual()
        if not revenda:
            return
        meses = await asyncio.to_thread(d.meses_disponiveis_dv, revenda)
        ui.update_selectize("mes_dv", selected=next(iter(meses.values()), None), session=session)
        if not eh_grupo():
            if "base_dv" in input:
                ui.update_selectize("base_dv", selected=_BASE_TODOS, session=session)
            ui.update_selectize("ga_dv", selected=[], session=session)
            ui.update_selectize("ven_dv", selected=[], session=session)

    def _ga_ven_atuais() -> tuple[list[str] | None, list[str] | None]:
        ga = list(input.ga_dv()) if "ga_dv" in input and input.ga_dv() else None
        ven = list(input.ven_dv()) if "ven_dv" in input and input.ven_dv() else None

        return ga, ven

    @reactive.calc
    async def dados_rv():
        revenda = revenda_atual()
        mes = input.mes_dv()
        if not revenda or not mes:
            return None
        _versao_cache()
        ga, ven = _ga_ven_atuais()
        return await asyncio.to_thread(d.categorias_dv, revenda, mes, ven=ven, ga=ga, rev=None, base=_base_marcada())

    @reactive.calc
    async def dados_familia_rv():
        revenda = revenda_atual()
        mes = input.mes_dv()
        if not revenda or not mes:
            return None
        _versao_cache()
        ga, ven = _ga_ven_atuais()
        return await asyncio.to_thread(d.familia_dv, revenda, mes, ven=ven, ga=ga, rev=None, base=_base_marcada())

    @reactive.calc
    async def dados_outros_rv():
        revenda = revenda_atual()
        mes = input.mes_dv()
        if not revenda or not mes:
            return None
        ga, ven = _ga_ven_atuais()
        return await asyncio.to_thread(
            d.outros_volumes_dv, revenda, mes, ven=ven, ga=ga, rev=None, base=_base_marcada()
        )

    @reactive.calc
    async def _info_dias_uteis():
        revenda = revenda_atual()
        mes = input.mes_dv()
        if not revenda or not mes:
            return None
        return await asyncio.to_thread(d.info_dias_uteis_dv, revenda, mes)

    @reactive.effect
    async def _publica_dias():
        if resumo_cabecalho_dias is None or not pagina_visivel(session, "ven"):
            return
        try:
            info = await _info_dias_uteis()
        except Exception as exc:
            logger.warning(f"Diario de Venda: dias uteis nao foram pro cabecalho -- {exc}")
            return
        info = info or {}
        resumo_cabecalho_dias.set(resumo_dias("ven", info.get("DIAS_UTEIS"), info.get("DIAS_UTEIS_ATUAL")))

    @render.ui
    async def kpis_dv():
        tabela = await dados_rv()
        if tabela is None or tabela.height == 0:
            return None
        total = tabela.filter(pl.col("CATEGORIA") == "VOLUME TOTAL")
        if total.height == 0:
            return None
        return t.cartoes_resumo_dv(total.row(0, named=True), input.mes_dv())

    @render.ui
    def tabela_categorias_wrap():
        return ui.div(ui.output_data_frame("tabela_categorias"), class_="dv-tabela dv-tabela-inteira")

    @reactive.calc
    async def tabela_categorias_construida():
        tabela = await dados_rv()
        if tabela is None or tabela.height == 0:
            return pd.DataFrame(), [], ""
        return t.construir_categorias_df(
            tabela, mostrar_meta_fab=eh_grupo(), mes=input.mes_dv(), seletor_base=f"#{session.ns('tabela_categorias')}"
        )

    @render.data_frame
    async def tabela_categorias():
        pandas_df, estilos, _ = await tabela_categorias_construida()

        return render.DataTable(pandas_df, styles=estilos, height=None, summary=False, filters=False)

    @render.ui
    async def css_cabecalho_categorias():
        _, _, css = await tabela_categorias_construida()
        return ui.tags.style(css) if css else None

    @reactive.calc
    async def tabela_familia_construida():
        tabela = await dados_familia_rv()
        if tabela is None or tabela.height == 0:
            return pd.DataFrame(), [], pd.DataFrame(), [], ""
        modo_hl = bool(input.familia_modo())
        return t.construir_familia_df(
            tabela,
            modo_hl=modo_hl,
            mostrar_meta_fab=eh_grupo(),
            mes=input.mes_dv(),
            seletor_base=f"#{session.ns('tabela_familia')}",
            seletor_base_total=f"#{session.ns('tabela_familia_total')}",
        )

    @render.data_frame
    async def tabela_familia():
        pandas_df, estilos, _, _, _ = await tabela_familia_construida()
        return render.DataTable(pandas_df, styles=estilos, height="560px", summary=False, filters=False)

    @render.data_frame
    async def tabela_familia_total():
        _, _, pandas_total_df, estilos_total, _ = await tabela_familia_construida()
        return render.DataTable(pandas_total_df, styles=estilos_total, height=None, summary=False, filters=False)

    @render.ui
    async def css_cabecalho_familia():
        _, _, _, _, css = await tabela_familia_construida()
        return ui.tags.style(css) if css else None

    @reactive.calc
    async def tabela_outros_construida():
        tabela = await dados_outros_rv()
        if tabela is None or tabela.height == 0:
            return pd.DataFrame(), [], pd.DataFrame(), [], ""
        modo_hl = bool(input.familia_modo())
        return t.construir_outros_df(
            tabela,
            modo_hl=modo_hl,
            mostrar_meta_fab=eh_grupo(),
            mes=input.mes_dv(),
            seletor_base=f"#{session.ns('tabela_outros')}",
            seletor_base_total=f"#{session.ns('tabela_outros_total')}",
        )

    @render.data_frame
    async def tabela_outros():
        pandas_df, estilos, _, _, _ = await tabela_outros_construida()
        # Altura só a necessária: com poucos produtos a tabela não deixa um vazio embaixo.
        altura = None if len(pandas_df) <= 15 else "480px"
        return render.DataTable(pandas_df, styles=estilos, height=altura, summary=False, filters=False)

    @render.data_frame
    async def tabela_outros_total():
        _, _, pandas_total_df, estilos_total, _ = await tabela_outros_construida()
        return render.DataTable(pandas_total_df, styles=estilos_total, height=None, summary=False, filters=False)

    @render.ui
    async def css_cabecalho_outros():
        _, _, _, _, css = await tabela_outros_construida()
        return ui.tags.style(css) if css else None

    historico_ativado = reactive.value(False, name="historico_ativado")
    grafico_tooltip_ativo = reactive.value(None, name="grafico_tooltip_ativo")

    @reactive.effect
    @reactive.event(input.bt_toggle_historico)
    async def _toggle_historico():
        novo_estado = not historico_ativado()
        historico_ativado.set(novo_estado)

        await session.send_custom_message("dvHistoricoAtivo", {"ativo": novo_estado})

    @render.ui
    def bt_toggle_historico_ui():
        ativo = historico_ativado()
        return ui.input_action_button(
            "bt_toggle_historico",
            "Histórico ligado" if ativo else "Histórico",
            icon=icon_svg("chart-line"),
            class_="btn-sm btn-historico-ativo" if ativo else "btn-sm btn-historico-inativo",
            title="Mostra a evolução ao passar o mouse na tendência e na cobertura",
        )

    @render.ui
    def painel_tooltip_grafico():
        grafico = grafico_tooltip_ativo()
        return ui.HTML(grafico) if grafico else None

    async def _titulo_produto(codred: str) -> str:

        for base_rv in (dados_familia_rv, dados_outros_rv):
            base = await base_rv()
            if base is not None and base.height:
                linhas = base.filter(pl.col("CODRED").cast(pl.Utf8) == codred)
                if linhas.height:
                    return linhas["PRODUTO"][0]
        return codred

    @reactive.effect
    @reactive.event(input.dv_categoria_hover, ignore_none=True)
    async def _hover_categoria():
        tabela = await dados_rv()
        if tabela is None or tabela.height == 0:
            return
        categoria = input.dv_categoria_hover()
        linhas = tabela.filter(pl.col("CATEGORIA") == categoria)
        if linhas.height == 0:
            return
        nivel = linhas["NIVEL"][0]
        ga, ven = _ga_ven_atuais()
        grafico = await asyncio.to_thread(
            tt.historico_tend_categ, revenda_atual(), categoria, nivel, ga, ven, None, _base_marcada()
        )
        if grafico:
            grafico_tooltip_ativo.set(grafico)

    @reactive.effect
    @reactive.event(input.dv_cob_categoria_hover, ignore_none=True)
    async def _hover_cob_categoria():
        categoria = input.dv_cob_categoria_hover()
        ga, ven = _ga_ven_atuais()
        grafico = await asyncio.to_thread(
            tt.historico_cob_categ, revenda_atual(), categoria, ga, ven, None, _base_marcada()
        )
        if grafico:
            grafico_tooltip_ativo.set(grafico)

    @reactive.effect
    @reactive.event(input.dv_indicador_hover, ignore_none=True)
    async def _hover_indicador():
        indicador = input.dv_indicador_hover()
        ga, ven = _ga_ven_atuais()
        grafico = await asyncio.to_thread(
            tt.historico_indicador, revenda_atual(), indicador, None, ga, ven, _base_marcada()
        )
        if grafico:
            grafico_tooltip_ativo.set(grafico)

    @reactive.effect
    @reactive.event(input.dv_fat_hover, ignore_none=True)
    async def _hover_fat():
        categoria = input.dv_fat_hover()
        canal = categoria[len("FATURAMENTO ") :] if categoria.startswith("FATURAMENTO ") else categoria
        ga, ven = _ga_ven_atuais()
        grafico = await asyncio.to_thread(
            tt.historico_fat, revenda_atual(), canal, categoria, None, ga, ven, _base_marcada()
        )
        if grafico:
            grafico_tooltip_ativo.set(grafico)

    @reactive.effect
    @reactive.event(input.familia_prod_hover, ignore_none=True)
    async def _hover_familia_prod():
        codred = input.familia_prod_hover()
        unidade = "HL" if bool(input.familia_modo()) else "UMB"
        titulo = await _titulo_produto(codred)
        ga, ven = _ga_ven_atuais()
        grafico = await asyncio.to_thread(
            tt.historico_tend_familia,
            revenda_atual(),
            codred,
            None,
            titulo,
            unidade,
            input.mes_dv(),
            None,
            base=_base_marcada(),
            ga=ga,
            ven=ven,
        )
        if grafico:
            grafico_tooltip_ativo.set(grafico)

    @reactive.effect
    @reactive.event(input.familia_cob_hover, ignore_none=True)
    async def _hover_familia_cob():
        codred = input.familia_cob_hover()
        titulo = await _titulo_produto(codred)
        ga, ven = _ga_ven_atuais()
        grafico = await asyncio.to_thread(
            tt.historico_cob_familia, revenda_atual(), codred, titulo, None, _base_marcada(), ga, ven
        )
        if grafico:
            grafico_tooltip_ativo.set(grafico)

    @render.ui
    def bt_meta_ano_ui():
        if not eh_grupo():
            return None
        return ui.input_action_button(
            "bt_meta_ano", "Meta Ano", icon=icon_svg("bullseye", a11y="deco"), class_="btn-sm btn-outline-primary"
        )

    @reactive.effect
    @reactive.event(input.bt_meta_ano)
    async def _abre_meta_ano():
        revenda = revenda_atual()
        tabela = await asyncio.to_thread(d.meta_ano_dv, revenda) if revenda else None
        conteudo = (
            ui.TagList(
                ui.div(ui.output_data_frame("tabela_meta_ano"), class_="dv-tabela dv-tabela-bordas"),
                ui.output_ui("css_larguras_meta_ano"),
            )
            if tabela is not None and tabela.height > 0
            else ui.p("Sem dado disponível.")
        )
        ui.modal_show(
            ui.modal(
                conteudo,
                title="Meta do Ano",
                size="lg",
                easy_close=True,
                footer=ui.modal_button("Fechar", icon=icon_svg("xmark")),
            )
        )

    @reactive.calc
    async def tabela_meta_ano_construida():
        revenda = revenda_atual()
        tabela = await asyncio.to_thread(d.meta_ano_dv, revenda) if revenda else None
        if tabela is None or tabela.height == 0:
            return pd.DataFrame(), [], ""
        hoje = date.today()
        return t.construir_meta_ano_df(
            tabela, ano_atual=hoje.year, mes_atual=hoje.month, seletor_base=f"#{session.ns('tabela_meta_ano')}"
        )

    @render.data_frame
    async def tabela_meta_ano():
        pandas_df, estilos, _ = await tabela_meta_ano_construida()

        return render.DataTable(pandas_df, styles=estilos, height=None, summary=False, filters=False)

    @render.ui
    async def css_larguras_meta_ano():
        _, _, css = await tabela_meta_ano_construida()
        return ui.tags.style(css) if css else None

    @render.ui
    def bt_meta_abp_ui():
        if not eh_grupo():
            return None
        return ui.input_action_button(
            "bt_meta_abp", "Meta ABP", icon=icon_svg("bullseye", a11y="deco"), class_="btn-sm btn-outline-primary"
        )

    @reactive.calc
    def tipo_meta_abp_atual() -> str:
        if "meta_abp_tipo" in input and input.meta_abp_tipo():
            return "Volume"
        return "Cobertura"

    @reactive.effect
    @reactive.event(input.bt_meta_abp)
    async def _abre_meta_abp():
        revenda = revenda_atual()

        tabela = await asyncio.to_thread(d.meta_abp_dv, revenda) if revenda else None
        conteudo = (
            ui.TagList(
                ui.div(ui.output_data_frame("tabela_meta_abp"), class_="dv-tabela"),
                ui.output_ui("css_larguras_meta_abp"),
            )
            if tabela is not None and tabela.height > 0
            else ui.p("Sem dado disponível (tabela de meta ABP não encontrada no banco local).")
        )
        titulo = ui.div(
            ui.span(f"Meta ABP {date.today().year}"),
            ui.div(
                ui.input_switch(
                    "meta_abp_tipo",
                    ui.TagList(ui.span("Cobertura", class_="dv-switch-off"), ui.span("Volume", class_="dv-switch-on")),
                    value=False,
                ),
                class_="dv-switch-hl",
            ),
            class_="meta-abp-modal-title",
        )
        ui.modal_show(
            ui.modal(
                conteudo,
                title=titulo,
                size="xl",
                easy_close=True,
                footer=ui.modal_button("Fechar", icon=icon_svg("xmark")),
            )
        )

    @reactive.calc
    async def tabela_meta_abp_construida():
        revenda = revenda_atual()
        tipo = tipo_meta_abp_atual()
        tabela = await asyncio.to_thread(d.meta_abp_dv, revenda, tipo=tipo) if revenda else None
        if tabela is None or tabela.height == 0:
            return pd.DataFrame(), [], ""
        hoje = date.today()
        return t.construir_meta_abp_df(
            tabela,
            ano_atual=hoje.year,
            mes_atual=hoje.month,
            seletor_base=f"#{session.ns('tabela_meta_abp')}",
            tipo=tipo,
        )

    @render.data_frame
    async def tabela_meta_abp():
        pandas_df, estilos, _ = await tabela_meta_abp_construida()

        return render.DataTable(pandas_df, styles=estilos, width="100%", height=None, summary=False, filters=False)

    @render.ui
    async def css_larguras_meta_abp():
        _, _, css = await tabela_meta_abp_construida()
        return ui.tags.style(css) if css else None
