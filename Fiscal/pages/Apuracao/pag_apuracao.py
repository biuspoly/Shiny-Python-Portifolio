from __future__ import annotations

from datetime import date

import polars as pl
from faicons import icon_svg
from loguru import logger
from pyecharts import options
from pyecharts.charts import Bar, Line
from pyecharts.commons.utils import JsCode
from shiny import module, reactive, render, ui
from shiny.types import SilentException

from core import colunas_do_usuario, exportar, formato, largura_colunas, opcoes_presentes, ordem_tabela
from core.config import cnpjs_da_url, empresas_da_url, erp_das_empresas
from core.cores import APURACAO_ESCURO, APURACAO_VERDE
from core.pyecharts_shiny import renderizar
from core.secao import titulo_secao
from core.tabela_paginada import TabelaPaginada
from core.visibilidade import pagina_visivel

from .Dados import dados_apuracao

VALOR_NAVSET = "apu"
UMA_ESCOLHIDA = {
    "plugins": ["restore_on_backspace"],
    "dropdownParent": "body",
    "dropdownClass": "selectize-dropdown ppf-filtro-dropdown",
}
FILTRO_VARIOS = {
    "plugins": {"remove_button": {"title": "Remover"}},
    "dropdownParent": "body",
    "dropdownClass": "selectize-dropdown ppf-filtro-dropdown",
}
# Sem "Despesas" no portfólio: no original ela lê o cache do Financeiro, outro pacote aqui.
SECOES = {"icms": "ICMS", "livro": "Livro fiscal", "pis_cofins": "PIS/COFINS"}


def _acao(controle: ui.Tag, rotulo: str) -> ui.Tag:
    return ui.div(controle, ui.div(rotulo, class_="ppf-acao-rotulo"), class_="ppf-acao")


def _cabecalho(titulo: str, icone: str, id_planilha: str, dica_da_planilha: str, *outras_acoes: ui.Tag) -> ui.Tag:
    acoes = ui.div(
        *outras_acoes,
        _acao(exportar.botao(id_planilha, dica_da_planilha), "Relatório"),
        class_="ppf-grupo-acoes ms-auto",
    )
    return ui.card_header(titulo_secao(titulo, icone=icone, extras=[acoes]))


def _colunas_do_livro() -> ui.Tag:
    return _acao(
        ui.popover(
            ui.input_action_button(
                "abrir_colunas",
                None,
                icon=icon_svg("table-columns", a11y="deco"),
                class_="ppf-btn-discreto",
                title="Escolher as colunas da lista",
            ),
            ui.div(
                ui.input_checkbox_group(
                    "colunas", None, list(dados_apuracao.COLUNAS_DOS_ITENS), selected=dados_apuracao.PADRAO_DOS_ITENS
                ),
                class_="fis-colunas",
            ),
            ui.div(ui.input_action_link("colunas_padrao", "Voltar ao padrão"), class_="fis-colunas-rodape"),
            title="Colunas da lista",
            placement="bottom",
            id="popover_colunas",
        ),
        "Colunas",
    )


def _caixa_da_tabela(id_tabela: str, colunas_que_ordenam: dict, classe: str = "") -> ui.Tag:
    return ui.div(
        ui.output_data_frame(id_tabela),
        class_=f"fis-tabela {ordem_tabela.CLASSE} {classe}".strip(),
        **ordem_tabela.atributos(colunas_que_ordenam),
    )


def _livro(id_tabela: str, titulo: str, icone: str, classe: str) -> ui.Tag:
    return ui.div(
        ui.div(icon_svg(icone, a11y="deco"), titulo, class_="fis-apu-titulo"),
        _caixa_da_tabela(id_tabela, dados_apuracao.ORDEM_DO_LIVRO),
        class_=f"fis-apu-livro {classe}",
    )


def _item(rotulo: str, valor: str, classe: str = "", detalhe: str | None = None) -> ui.Tag:
    return ui.div(
        ui.div(rotulo, class_="fis-apu-rotulo"),
        ui.div(valor, class_=f"fis-apu-valor {classe}".strip()),
        ui.div(detalhe, class_="fis-apu-sub") if detalhe else None,
        class_="fis-apu-item",
    )


def _linha_do_sped(rotulo: str, valor: float, classe: str = "") -> ui.Tag:
    return ui.div(ui.span(rotulo), ui.span(formato.moeda(valor), class_=classe), class_="fis-apu-linha")


def _bloco_do_sped(apuracao_oficial: dict | None) -> list[ui.Tag]:
    titulo = ui.div("No SPED gerado", class_="fis-apu-rotulo")
    if apuracao_oficial is None:
        return [
            titulo,
            ui.div(
                "Gere o SPED do mês na tela SPED x XML para ver os ajustes e o saldo credor anterior.",
                class_="fis-apu-sub fis-apu-quebra",
            ),
        ]
    ajustes = apuracao_oficial["ajustes_por_tipo"]
    linhas = [_linha_do_sped("Débitos", apuracao_oficial["debitos"])]
    for tipo in ("outros_debitos", "estornos_de_credito"):
        if ajustes[tipo]:
            linhas.append(_linha_do_sped(dados_apuracao.nome_do_tipo_de_ajuste(tipo), ajustes[tipo]))
    linhas.append(_linha_do_sped("Créditos", apuracao_oficial["creditos"]))
    for tipo in ("outros_creditos", "estornos_de_debito"):
        if ajustes[tipo]:
            linhas.append(_linha_do_sped(dados_apuracao.nome_do_tipo_de_ajuste(tipo), ajustes[tipo]))
    if apuracao_oficial["saldo_credor_anterior"]:
        linhas.append(_linha_do_sped("Saldo credor anterior", apuracao_oficial["saldo_credor_anterior"]))
    for tipo in ("deducoes", "debitos_especiais"):
        if ajustes[tipo]:
            linhas.append(_linha_do_sped(dados_apuracao.nome_do_tipo_de_ajuste(tipo), ajustes[tipo]))
    if apuracao_oficial["saldo_credor"]:
        resultado = _item(
            "Saldo credor a transportar", formato.moeda(apuracao_oficial["saldo_credor"]), "fis-apu-credito"
        )
    else:
        resultado = _item("ICMS a recolher", formato.moeda(apuracao_oficial["a_recolher"]), "fis-apu-debito")
    gerado_em = apuracao_oficial["gerado_em"]
    data_da_geracao = f"{gerado_em[8:10]}/{gerado_em[5:7]}/{gerado_em[:4]}" if len(gerado_em) >= 10 else ""
    return [
        titulo,
        ui.div(f"gerado em {data_da_geracao}", class_="fis-apu-sub") if data_da_geracao else None,
        *linhas,
        resultado,
    ]


def _cor_do_saldo(texto_do_saldo: str) -> str | None:
    if texto_do_saldo.startswith("credor"):
        return "verde"
    return "vermelho" if texto_do_saldo not in ("-", "R$ 0,00") else None


def _linha_do_total(linhas_na_tela: pl.DataFrame) -> list[dict]:
    if linhas_na_tela.is_empty() or linhas_na_tela.row(-1)[0] != "Total":
        return []
    return [{"location": "body", "rows": [linhas_na_tela.height - 1], "class": "fis-apu-total"}]


EIXO_EM_MILHOES = JsCode(
    "function (valor) { return (valor / 1000000).toLocaleString('pt-BR', {maximumFractionDigits: 1}) + ' mi'; }"
)
EIXO_EM_MIL = JsCode(
    "function (valor) { return (valor / 1000).toLocaleString('pt-BR', {maximumFractionDigits: 0}) + ' mil'; }"
)
DICA_EM_REAIS = JsCode(
    "function (valor) { return valor == null ? '-' : 'R$ ' + Number(valor).toLocaleString('pt-BR', "
    "{minimumFractionDigits: 2, maximumFractionDigits: 2}); }"
)
AREA_DO_GRAFICO = options.GridOpts(is_contain_label=True, pos_left="1%", pos_right="2%", pos_top="8%", pos_bottom="14%")


def _opcoes_comuns(grafico, dica: options.TooltipOpts, eixo: JsCode = EIXO_EM_MILHOES) -> None:
    grafico.set_global_opts(
        tooltip_opts=dica,
        legend_opts=options.LegendOpts(pos_bottom="0%"),
        yaxis_opts=options.AxisOpts(
            splitline_opts=options.SplitLineOpts(is_show=True), axislabel_opts=options.LabelOpts(formatter=eixo)
        ),
    )
    grafico.options["grid"] = AREA_DO_GRAFICO
    grafico.set_series_opts(label_opts=options.LabelOpts(is_show=False))


def _grafico_de_barras(
    meses: list[str], series: list[tuple[str, list, str]], eixo: JsCode = EIXO_EM_MILHOES
) -> ui.HTML:
    barras = Bar()
    barras.add_xaxis([dados_apuracao.rotulo_curto(mes) for mes in meses])
    for nome, valores, cor in series:
        barras.add_yaxis(nome, valores, color=cor)
    _opcoes_comuns(
        barras, options.TooltipOpts(trigger="axis", axis_pointer_type="shadow", value_formatter=DICA_EM_REAIS), eixo
    )
    return ui.HTML(renderizar(barras, altura="32vh"))


def _grafico_de_linhas(meses: list[str], series: list[tuple[str, list, str]]) -> ui.HTML:
    linhas = Line()
    linhas.add_xaxis([dados_apuracao.rotulo_curto(mes) for mes in meses])
    for nome, valores, cor in series:
        linhas.add_yaxis(
            nome,
            valores,
            color=cor,
            is_smooth=True,
            symbol_size=6,
            linestyle_opts=options.LineStyleOpts(width=2, color=cor),
        )
    _opcoes_comuns(linhas, options.TooltipOpts(trigger="axis", value_formatter=DICA_EM_REAIS))
    return ui.HTML(renderizar(linhas, altura="32vh"))


def _quadro_do_grafico(titulo: str, id_grafico: str) -> ui.Tag:
    return ui.div(ui.div(titulo, class_="fis-apu-grafico-titulo"), ui.output_ui(id_grafico), class_="fis-apu-grafico")


@module.ui
def apuracao_ui(revenda: str | None = None):
    varias_empresas = len(empresas_da_url(revenda)) > 1
    filtro_empresa = ui.input_selectize(
        "empresa", "Empresa", {}, width="100%", options={**UMA_ESCOLHIDA, "placeholder": ""}
    )
    filtro_mes = ui.input_selectize(
        "mes", "Mês", {"": "Sem livro"}, width="100%", options={**UMA_ESCOLHIDA, "placeholder": "Sem livro"}
    )
    if varias_empresas:
        linha_principal = ui.layout_columns(
            filtro_empresa, filtro_mes, col_widths=(4, 2), gap="0.5rem", class_="align-items-end"
        )
    else:
        linha_principal = ui.TagList(
            ui.div(filtro_empresa, class_="d-none"),
            ui.layout_columns(filtro_mes, col_widths=(2,), gap="0.5rem", class_="align-items-end"),
        )
    filtros_do_livro = ui.panel_conditional(
        "input.secao === 'livro'",
        ui.layout_columns(
            ui.input_date_range(
                "dias", "Período", format="dd/mm/yyyy", language="pt-BR", separator="até", weekstart=0, width="100%"
            ),
            ui.input_text("busca", "Busca", placeholder="Nota, chave, produto, participante ou CNPJ", width="100%"),
            col_widths=(4, 8),
            gap="0.5rem",
            class_="align-items-end",
        ),
        ui.accordion(
            ui.accordion_panel(
                "Filtros",
                ui.layout_columns(
                    ui.input_selectize(
                        "livro", "Livro", dados_apuracao.LIVROS_DOS_ITENS, width="100%", options=UMA_ESCOLHIDA
                    ),
                    ui.input_selectize(
                        "cfops",
                        "CFOP",
                        {},
                        multiple=True,
                        width="100%",
                        options={**FILTRO_VARIOS, "placeholder": "Todos"},
                    ),
                    ui.input_selectize(
                        "produtos",
                        "Produto",
                        {},
                        multiple=True,
                        width="100%",
                        options={**FILTRO_VARIOS, "placeholder": "Todos"},
                    ),
                    ui.input_selectize(
                        "participantes",
                        "Participante",
                        {},
                        multiple=True,
                        width="100%",
                        options={**FILTRO_VARIOS, "placeholder": "Todos"},
                    ),
                    col_widths=(2, 3, 4, 3),
                    gap="0.5rem",
                ),
                ui.layout_columns(
                    ui.input_selectize(
                        "csts",
                        "CST do PIS/COFINS",
                        {},
                        multiple=True,
                        width="100%",
                        options={**FILTRO_VARIOS, "placeholder": "Todos"},
                    ),
                    ui.input_selectize(
                        "aliquotas",
                        "Alíquota do ICMS",
                        {},
                        multiple=True,
                        width="100%",
                        options={**FILTRO_VARIOS, "placeholder": "Todas"},
                    ),
                    ui.input_selectize(
                        "situacao",
                        "Nota cancelada",
                        dados_apuracao.SITUACOES_DOS_ITENS,
                        width="100%",
                        options=UMA_ESCOLHIDA,
                    ),
                    col_widths=(5, 3, 4),
                    gap="0.5rem",
                ),
                icon=icon_svg("filter", a11y="deco"),
            ),
            open=False,
        ),
    )
    filtros_das_despesas = ui.panel_conditional(
        "input.secao === 'despesas'",
        ui.layout_columns(
            ui.input_date_range(
                "pagos",
                "Pagos entre",
                format="dd/mm/yyyy",
                language="pt-BR",
                separator="até",
                weekstart=0,
                width="100%",
            ),
            col_widths=(4,),
            gap="0.5rem",
            class_="align-items-end",
        ),
        ui.accordion(
            ui.accordion_panel(
                "Filtros",
                ui.layout_columns(
                    ui.input_selectize(
                        "despesas",
                        "Despesa",
                        {},
                        multiple=True,
                        width="100%",
                        options={**FILTRO_VARIOS, "placeholder": "Todas"},
                    ),
                    ui.input_selectize(
                        "fornecedores",
                        "Fornecedor",
                        {},
                        multiple=True,
                        width="100%",
                        options={**FILTRO_VARIOS, "placeholder": "Todos"},
                    ),
                    col_widths=(6, 6),
                    gap="0.5rem",
                ),
                icon=icon_svg("filter", a11y="deco"),
            ),
            open=False,
        ),
    )
    filtrando_por = ui.panel_conditional(
        "input.secao === 'livro' || input.secao === 'despesas'",
        ui.div(
            ui.output_ui("filtrando_por", inline=True),
            ui.input_action_button("limpar", "Limpar", class_="ppf-btn-limpar", title="Limpar os filtros da aba"),
            class_="d-flex flex-wrap align-items-center gap-2",
        ),
    )
    parte_do_livro = ui.card(
        _cabecalho(
            "Livro do mês, item a item",
            "list",
            "planilha_itens",
            "Os itens do livro do mês com os filtros, com todos os impostos: escolha as colunas e a ordem delas",
            _colunas_do_livro(),
        ),
        ui.output_ui("aviso_sem_itens"),
        ui.div(
            ui.output_data_frame("tabela_itens"),
            class_=f"fis-tabela {ordem_tabela.CLASSE}",
            **ordem_tabela.atributos(dados_apuracao.ORDEM_DOS_ITENS),
        ),
        ui.output_ui("paginacao_itens"),
        class_="fis-caixa-lista",
    )
    parte_do_icms = ui.TagList(
        ui.card(
            _cabecalho(
                "Livros do mês",
                "book-open",
                "planilha",
                "Os dois livros do mês por CFOP, com o grupo, isentas, outras, ICMS-ST e IPI: escolha as colunas "
                "e a ordem delas",
            ),
            ui.div(
                ui.div(
                    ui.input_radio_buttons("agrupar", None, dados_apuracao.AGRUPAMENTOS, selected="cfop", inline=True),
                    class_="fis-tipos fis-fila",
                ),
                class_="fis-barra",
            ),
            ui.output_ui("aviso_sem_impostos"),
            ui.layout_columns(
                _livro("tabela_entradas", "Entradas", "arrow-right-to-bracket", "fis-apu-entrada"),
                _livro("tabela_saidas", "Saídas", "arrow-right-from-bracket", "fis-apu-saida"),
                ui.div(ui.output_ui("resumo_do_icms"), class_="fis-apu-resumo"),
                col_widths={"sm": (12, 12, 12), "xl": (5, 5, 2)},
                gap="0.75rem",
                class_="fis-apu-grade",
            ),
            class_="fis-caixa-lista",
        ),
        ui.card(
            ui.card_header(titulo_secao("Mês a mês", icone="chart-column")),
            _caixa_da_tabela("tabela_meses", dados_apuracao.ORDEM_DOS_MESES),
            ui.layout_columns(
                _quadro_do_grafico("ICMS creditado x debitado", "grafico"),
                _quadro_do_grafico("Bonificações recebidas x dadas", "grafico_bonificacoes"),
                col_widths={"sm": (12, 12), "lg": (6, 6)},
                gap="0.75rem",
                class_="fis-apu-grade",
            ),
            class_="fis-caixa-lista",
        ),
    )
    parte_do_pis_cofins = ui.TagList(
        ui.card(
            _cabecalho(
                "Receita bruta e deduções, mês a mês",
                "sack-dollar",
                "planilha_receita",
                "A receita bruta e as deduções dos 12 meses: escolha as colunas e a ordem delas",
            ),
            _caixa_da_tabela("tabela_receita", dados_apuracao.ORDEM_DA_RECEITA, "fis-apu-receita"),
            ui.layout_columns(
                _quadro_do_grafico("Receita bruta x bonificação dada", "grafico_receita"),
                _quadro_do_grafico("Compras", "grafico_compras"),
                col_widths={"sm": (12, 12), "lg": (6, 6)},
                gap="0.75rem",
                class_="fis-apu-grade",
            ),
            class_="fis-caixa-lista",
        ),
        ui.card(
            _cabecalho(
                "Apuração do PIS e da COFINS, mês a mês",
                "scale-balanced",
                "planilha_pis_cofins",
                "O crédito, o débito, o saldo do mês e o CMV dos 12 meses: escolha as colunas e a ordem delas",
            ),
            _caixa_da_tabela("tabela_pis_cofins", dados_apuracao.ORDEM_DA_APURACAO_PIS_COFINS, "fis-apu-receita"),
            ui.layout_columns(
                _quadro_do_grafico("PIS e COFINS do mês", "grafico_pis_cofins"),
                _quadro_do_grafico("CMV", "grafico_cmv"),
                col_widths={"sm": (12, 12), "lg": (6, 6)},
                gap="0.75rem",
                class_="fis-apu-grade",
            ),
            class_="fis-caixa-lista",
        ),
    )
    parte_das_despesas = ui.TagList(
        ui.card(
            _cabecalho(
                "Despesas pagas, mês a mês",
                "receipt",
                "planilha_despesas",
                "As despesas pagas por mês: escolha as colunas e a ordem delas",
            ),
            _caixa_da_tabela("tabela_despesas", dados_apuracao.ORDEM_DAS_DESPESAS, "fis-apu-despesas"),
            class_="fis-caixa-lista",
        ),
        ui.card(
            _cabecalho(
                "Títulos pagos no período",
                "file-invoice-dollar",
                "planilha_titulos",
                "Os títulos pagos no período, um por linha: escolha as colunas e a ordem delas",
            ),
            ui.div(
                ui.output_data_frame("tabela_titulos"),
                class_=f"fis-tabela {ordem_tabela.CLASSE}",
                **ordem_tabela.atributos(dados_apuracao.ORDEM_DOS_TITULOS),
            ),
            ui.output_ui("paginacao_titulos"),
            class_="fis-caixa-lista",
        ),
    )
    return ui.div(
        ui.card(
            ui.card_header(titulo_secao("Apuração dos livros fiscais", icone="scale-balanced")),
            ui.div(
                ui.navset_underline(
                    *[ui.nav_panel(nome, value=codigo) for codigo, nome in SECOES.items()], id="secao", selected="icms"
                ),
                linha_principal,
                filtros_do_livro,
                filtros_das_despesas,
                ui.div(
                    filtrando_por,
                    ui.div(ui.output_ui("total_da_lista"), class_="ms-auto"),
                    class_="d-flex flex-wrap align-items-center justify-content-between gap-2",
                ),
                class_="fis-filtros",
            ),
            class_="fis-caixa-filtros",
        ),
        ui.panel_conditional("!input.secao || input.secao === 'icms'", parte_do_icms),
        ui.panel_conditional("input.secao === 'livro'", parte_do_livro),
        ui.panel_conditional("input.secao === 'pis_cofins'", parte_do_pis_cofins),
        ui.panel_conditional("input.secao === 'despesas'", parte_das_despesas),
        class_="fis-modulo fis-apu-pbi",
    )


@module.server
def apuracao_server(input, output, session, revenda_atual, usuario_atual=None, versao_cache=None):
    @reactive.calc
    def cnpjs() -> list[str]:
        return cnpjs_da_url(revenda_atual())

    @reactive.calc
    def erp_da_tela() -> str:
        empresa = input.empresa() or ""
        return erp_das_empresas([empresa] if empresa else cnpjs())

    @reactive.effect
    def _opcoes_empresa():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        try:
            empresas_da_tela = [empresa for empresa in empresas_da_url(revenda_atual()) if empresa["cnpj"] in cnpjs()]
            validas = [empresa["cnpj"] for empresa in empresas_da_tela]
            with reactive.isolate():
                escolhida = input.empresa() or ""
            ui.update_selectize(
                "empresa",
                choices={empresa["cnpj"]: empresa["nome"] for empresa in empresas_da_tela},
                selected=escolhida if escolhida in validas else next(iter(validas), ""),
            )
        except Exception as exc:
            logger.warning(f"Apuracao: opcoes de empresa -- {exc}")

    @reactive.calc
    def livros() -> pl.DataFrame:
        if versao_cache is not None:
            versao_cache()
        return dados_apuracao.livros_da_empresa(input.empresa() or "")

    @reactive.effect
    def _opcoes_mes():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        try:
            meses = dados_apuracao.meses_com_livro(livros())
            with reactive.isolate():
                escolhido = input.mes() or ""
            fechados = [mes for mes in meses if mes < f"{date.today():%Y-%m}"]
            selecionado = escolhido if escolhido in meses else next(iter(fechados or meses), "")
            opcoes = {mes: dados_apuracao.rotulo_mes(mes) for mes in meses} or {"": "Sem livro"}
            ui.update_selectize("mes", choices=opcoes, selected=selecionado)
        except Exception as exc:
            logger.warning(f"Apuracao: opcoes do mes -- {exc}")

    @reactive.calc
    def mes() -> str:
        escolhido = input.mes() or ""
        return escolhido if len(escolhido) == 7 else ""

    @reactive.calc
    def com_impostos() -> bool:
        return dados_apuracao.tem_impostos(livros(), mes())

    @reactive.calc
    def entradas_do_mes() -> pl.DataFrame:
        return dados_apuracao.por_cfop(livros(), mes(), "E")

    @reactive.calc
    def saidas_do_mes() -> pl.DataFrame:
        return dados_apuracao.por_cfop(livros(), mes(), "S")

    @reactive.calc
    def resumo() -> dict:
        return dados_apuracao.apuracao(entradas_do_mes(), saidas_do_mes())

    @reactive.calc
    def antecipado() -> pl.DataFrame:
        return dados_apuracao.antecipado_pago(titulos_pagos(), input.empresa() or "", mes())

    @reactive.calc
    def meses_lado_a_lado() -> pl.DataFrame:
        return dados_apuracao.com_o_antecipado(dados_apuracao.mes_a_mes(livros(), mes()), antecipado())

    def _antecipado_do_mes() -> ui.Tag:
        do_mes = antecipado().filter(pl.col("mes") == mes())
        valor = do_mes["antecipado"][0] if not do_mes.is_empty() else None
        return _item(
            "ICMS antecipado pago",
            formato.moeda(valor) if valor is not None else "-",
            detalhe="guias de fronteira, fora do saldo",
        )

    @reactive.calc
    def bonificacoes() -> pl.DataFrame:
        return dados_apuracao.bonificacoes_mes_a_mes(livros(), mes())

    @reactive.calc
    def receita_bruta() -> pl.DataFrame:
        return dados_apuracao.receita_bruta_mes_a_mes(livros(), mes())

    @reactive.calc
    def titulos_pagos() -> pl.DataFrame:
        if versao_cache is not None:
            versao_cache()
        return dados_apuracao.titulos_pagos_da_empresa(input.empresa() or "")

    @reactive.calc
    def despesas_escolhidas() -> list[str]:
        return list(input.despesas() or [])

    @reactive.calc
    def fornecedores_escolhidos() -> list[str]:
        return list(input.fornecedores() or [])

    @reactive.calc
    def despesas_na_tabela() -> pl.DataFrame:
        return dados_apuracao.despesas_por_mes(
            dados_apuracao.despesas_pagas(
                titulos_pagos(), input.empresa() or "", mes(), despesas_escolhidas(), fornecedores_escolhidos()
            )
        )

    @reactive.calc
    def pis_cofins() -> pl.DataFrame:
        if versao_cache is not None:
            versao_cache()
        return dados_apuracao.pis_cofins_mes_a_mes(input.empresa() or "", mes())

    @reactive.calc
    def receita_e_deducoes() -> pl.DataFrame:
        deducoes_do_mes = dados_apuracao.deducoes_pagas(titulos_pagos(), input.empresa() or "", mes())
        return dados_apuracao.receita_e_deducoes_mes_a_mes(receita_bruta(), deducoes_do_mes, pis_cofins())

    @reactive.calc
    def apuracao_pis_cofins() -> pl.DataFrame:
        return dados_apuracao.apuracao_pis_cofins(receita_e_deducoes(), pis_cofins())

    @render.ui
    def total_da_lista():
        if not mes():
            return None
        if input.secao() == "livro":
            numeros = dados_apuracao.resumo_dos_itens(itens_filtrados_sem_ordem())
            return ui.span(
                ui.span(f"{dados_apuracao.rotulo_mes(mes())}: "),
                ui.tags.strong(formato.inteiro(numeros["itens"])),
                ui.span(f" itens em {formato.inteiro(numeros['notas'])} notas · valor "),
                ui.tags.strong(formato.moeda(numeros["valor"])),
                ui.span(" · ICMS "),
                ui.tags.strong(formato.moeda(numeros["icms"])),
                ui.span(" · PIS "),
                ui.tags.strong(formato.moeda(numeros["pis"])),
                ui.span(" · COFINS "),
                ui.tags.strong(formato.moeda(numeros["cofins"])),
            )
        if input.secao() == "despesas":
            pagos_no_periodo = titulos_do_periodo_sem_ordem()
            de, ate = periodo_dos_titulos()
            return ui.span(
                ui.span(f"De {formato.data(de)} até {formato.data(ate)}: "),
                ui.tags.strong(formato.inteiro(pagos_no_periodo.height)),
                ui.span(" títulos pagos · "),
                ui.tags.strong(formato.moeda(round(float(pagos_no_periodo["valor"].sum() or 0), 2))),
            )
        resumo_do_mes = resumo()
        return ui.span(
            ui.span(f"{dados_apuracao.rotulo_mes(mes())}: entradas "),
            ui.tags.strong(formato.moeda(resumo_do_mes["valor_entradas"])),
            ui.span(f" ({resumo_do_mes['cfops_entradas']} CFOPs) · saídas "),
            ui.tags.strong(formato.moeda(resumo_do_mes["valor_saidas"])),
            ui.span(f" ({resumo_do_mes['cfops_saidas']} CFOPs)"),
        )

    @output(suspend_when_hidden=False)
    @render.ui
    def aviso_sem_impostos():
        if not mes() or com_impostos():
            return None
        return ui.p(
            icon_svg("triangle-exclamation", a11y="deco"),
            f" O livro deste mês foi lido do {erp_da_tela()} antes de trazer os impostos: use o "
            "Atualizar, no alto da tela, para trazer o ICMS.",
            class_="fis-op-alerta",
        )

    @output(suspend_when_hidden=False)
    @render.ui
    def resumo_do_icms():
        if not mes():
            return ui.div(_item("ICMS", "-"))
        bloco_do_sped = _bloco_do_sped(dados_apuracao.apuracao_do_sped(input.empresa() or "", mes()))
        if not com_impostos():
            return ui.div(
                _item("Débito de ICMS", "-"),
                _item("Crédito de ICMS", "-"),
                _antecipado_do_mes(),
                _item("Saldo", "-"),
                ui.div(class_="fis-apu-separador"),
                *bloco_do_sped,
            )
        resumo_do_mes = resumo()
        saldo = resumo_do_mes["saldo"]
        if saldo > 0:
            item_do_saldo = _item("ICMS a recolher no livro", formato.moeda(saldo), "fis-apu-debito")
        elif saldo < 0:
            item_do_saldo = _item("Saldo credor no livro", formato.moeda(-saldo), "fis-apu-credito")
        else:
            item_do_saldo = _item("Saldo no livro", formato.moeda(0))
        return ui.div(
            _item("Débito de ICMS", formato.moeda(resumo_do_mes["debito"]), detalhe="nas saídas"),
            _item("Crédito de ICMS", formato.moeda(resumo_do_mes["credito"]), detalhe="nas entradas"),
            _antecipado_do_mes(),
            ui.div(class_="fis-apu-separador"),
            item_do_saldo,
            ui.div(class_="fis-apu-separador"),
            *bloco_do_sped,
        )

    ordem_entradas = ordem_tabela.OrdemPorValor(
        "tabela_entradas", input, session, colunas=dados_apuracao.ORDEM_DO_LIVRO
    )
    ordem_saidas = ordem_tabela.OrdemPorValor("tabela_saidas", input, session, colunas=dados_apuracao.ORDEM_DO_LIVRO)
    ordem_meses = ordem_tabela.OrdemPorValor("tabela_meses", input, session, colunas=dados_apuracao.ORDEM_DOS_MESES)
    ordem_receita = ordem_tabela.OrdemPorValor(
        "tabela_receita", input, session, colunas=dados_apuracao.ORDEM_DA_RECEITA
    )
    ordem_despesas = ordem_tabela.OrdemPorValor(
        "tabela_despesas", input, session, colunas=dados_apuracao.ORDEM_DAS_DESPESAS
    )

    def _livro_na_tela(livro_por_cfop: pl.DataFrame, ordem: ordem_tabela.OrdemPorValor) -> render.DataGrid:
        if input.agrupar() == "operacao":
            por_grupo = ordem.ordenar(dados_apuracao.por_operacao(livro_por_cfop))
            linhas_na_tela = dados_apuracao.na_tela_operacao(por_grupo, com_impostos())
        else:
            por_cfop = ordem.ordenar(dados_apuracao.com_o_nome_da_operacao(livro_por_cfop))
            linhas_na_tela = dados_apuracao.na_tela_cfop(por_cfop, com_impostos())
        return largura_colunas.grade(
            linhas_na_tela, height="44vh", width="100%", summary=False, styles=_linha_do_total(linhas_na_tela)
        )

    @output(suspend_when_hidden=False)
    @render.data_frame
    def tabela_entradas():
        return _livro_na_tela(entradas_do_mes(), ordem_entradas)

    @output(suspend_when_hidden=False)
    @render.data_frame
    def tabela_saidas():
        return _livro_na_tela(saidas_do_mes(), ordem_saidas)

    def _nome_da_planilha() -> str:
        return f"apuracao_{input.empresa() or 'empresa'}_{mes() or ''}.xlsx"

    @render.download(filename=_nome_da_planilha)
    def planilha():
        yield dados_apuracao.planilha(livros(), mes(), colunas=janela_exportar.colunas("planilha"))

    @output(suspend_when_hidden=False)
    @render.data_frame
    def tabela_meses():
        linhas_na_tela = dados_apuracao.na_tela_meses(ordem_meses.ordenar(meses_lado_a_lado()), input.empresa() or "")
        cores_da_situacao = formato.estilos(
            linhas_na_tela, {"Situação": {"a recolher": "vermelho", "credor": "verde"}}, so_texto=("Situação",)
        )
        return largura_colunas.grade(
            linhas_na_tela, height="36vh", width="100%", summary=False, styles=cores_da_situacao
        )

    @output(suspend_when_hidden=False)
    @render.ui
    def grafico():
        meses = meses_lado_a_lado()
        if meses.is_empty():
            return None
        return _grafico_de_barras(
            meses["mes"].to_list(),
            [
                ("Crédito de ICMS", meses["credito"].round(2).to_list(), APURACAO_VERDE),
                ("Débito de ICMS", meses["debito"].round(2).to_list(), APURACAO_ESCURO),
            ],
        )

    @output(suspend_when_hidden=False)
    @render.ui
    def grafico_bonificacoes():
        por_mes = bonificacoes()
        if por_mes.is_empty():
            return None
        return _grafico_de_barras(
            por_mes["mes"].to_list(),
            [
                ("Bonificação recebida", por_mes["entrada"].to_list(), APURACAO_VERDE),
                ("Bonificação dada", por_mes["saida"].to_list(), APURACAO_ESCURO),
            ],
        )

    @output(suspend_when_hidden=False)
    @render.data_frame
    def tabela_receita():
        linhas_na_tela = dados_apuracao.na_tela_receita(ordem_receita.ordenar(receita_e_deducoes()))
        return largura_colunas.grade(
            linhas_na_tela, height="44vh", width="100%", summary=False, styles=_linha_do_total(linhas_na_tela)
        )

    @output(suspend_when_hidden=False)
    @render.ui
    def grafico_receita():
        por_mes, bonificacao = receita_bruta(), bonificacoes()
        if por_mes.is_empty():
            return None
        return _grafico_de_linhas(
            por_mes["mes"].to_list(),
            [
                ("Receita bruta", por_mes["receita_bruta"].to_list(), APURACAO_ESCURO),
                ("Bonificação dada", bonificacao["saida"].to_list(), APURACAO_VERDE),
            ],
        )

    @output(suspend_when_hidden=False)
    @render.ui
    def grafico_compras():
        por_mes = receita_bruta()
        if por_mes.is_empty():
            return None
        return _grafico_de_barras(
            por_mes["mes"].to_list(), [("Compras", por_mes["compras"].to_list(), APURACAO_ESCURO)]
        )

    def _nome_da_planilha_receita() -> str:
        return f"receita_bruta_{input.empresa() or 'empresa'}_ate_{mes() or ''}.xlsx"

    @render.download(filename=_nome_da_planilha_receita)
    def planilha_receita():
        yield dados_apuracao.planilha_receita(
            receita_e_deducoes(), mes(), colunas=janela_exportar.colunas("planilha_receita")
        )

    @output(suspend_when_hidden=False)
    @render.data_frame
    def tabela_despesas():
        linhas_na_tela = dados_apuracao.na_tela_despesas(ordem_despesas.ordenar(despesas_na_tabela()))
        return largura_colunas.grade(
            linhas_na_tela, height="60vh", width="100%", summary=False, styles=_linha_do_total(linhas_na_tela)
        )

    def _nome_da_planilha_despesas() -> str:
        return f"despesas_{input.empresa() or 'empresa'}_ate_{mes() or ''}.xlsx"

    @render.download(filename=_nome_da_planilha_despesas)
    def planilha_despesas():
        yield dados_apuracao.planilha_despesas(
            despesas_na_tabela(), mes(), colunas=janela_exportar.colunas("planilha_despesas")
        )

    @reactive.calc
    def meses_com_itens() -> set[str]:
        if versao_cache is not None:
            versao_cache()
        return dados_apuracao.meses_com_itens(input.empresa() or "")

    @reactive.calc
    def itens_do_mes() -> pl.DataFrame:
        if versao_cache is not None:
            versao_cache()
        return dados_apuracao.com_os_nomes(dados_apuracao.itens_do_mes(input.empresa() or "", mes()))

    def _opcoes_do_filtro(id_filtro: str, opcoes: dict[str, str], no_servidor: bool = False) -> None:
        with reactive.isolate():
            escolhidos = [codigo for codigo in (input[id_filtro]() or []) if codigo in opcoes]
        ui.update_selectize(id_filtro, choices=opcoes, selected=escolhidos, server=no_servidor)

    @reactive.effect
    def _opcoes_cfop():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        try:
            _opcoes_do_filtro("cfops", dados_apuracao.opcoes_cfop_dos_itens(itens_do_mes(), input.livro() or ""))
        except Exception as exc:
            logger.warning(f"Apuracao: opcoes de CFOP -- {exc}")

    @reactive.calc
    def opcoes_dos_itens() -> dict[str, dict[str, str]]:
        itens = itens_do_mes()
        return {
            "produtos": dados_apuracao.opcoes_produto_dos_itens(itens),
            "participantes": dados_apuracao.opcoes_participante_dos_itens(itens),
            "csts": dados_apuracao.opcoes_cst_dos_itens(itens),
            "aliquotas": dados_apuracao.opcoes_aliquota_dos_itens(itens),
        }

    @reactive.effect
    def _opcoes_dos_itens():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        try:
            for id_filtro, opcoes in opcoes_dos_itens().items():
                _opcoes_do_filtro(id_filtro, opcoes, no_servidor=id_filtro == "participantes")
        except Exception as exc:
            logger.warning(f"Apuracao: opcoes dos filtros do livro -- {exc}")

    mes_dos_periodos = {"dias": None, "pagos": None}

    def _periodo_do_mes(id_periodo: str, dentro_do_mes: bool) -> None:
        primeiro, ultimo = dados_apuracao.primeiro_e_ultimo_dia(mes())
        if primeiro is None or mes_dos_periodos[id_periodo] == mes():
            return
        with reactive.isolate():
            de, ate = input[id_periodo]() or (None, None)
        veio_do_endereco = (
            mes_dos_periodos[id_periodo] is None
            and de
            and ate
            and de <= ate
            and (de, ate) != (date.today(), date.today())
            and (not dentro_do_mes or primeiro <= de <= ate <= ultimo)
        )
        mes_dos_periodos[id_periodo] = mes()
        if veio_do_endereco:
            return
        if dentro_do_mes:
            ui.update_date_range(id_periodo, start=primeiro, end=ultimo, min=primeiro, max=ultimo)
        else:
            ui.update_date_range(id_periodo, start=primeiro, end=ultimo)

    @reactive.effect
    def _periodos_do_mes():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        try:
            mes()
            _periodo_do_mes("dias", dentro_do_mes=True)
            _periodo_do_mes("pagos", dentro_do_mes=False)
        except Exception as exc:
            logger.warning(f"Apuracao: o periodo do mes -- {exc}")

    @reactive.calc
    def periodo_do_livro() -> tuple:
        primeiro, ultimo = dados_apuracao.primeiro_e_ultimo_dia(mes())
        de, ate = input.dias() or (None, None)
        if primeiro is None or not de or not ate or not (primeiro <= de <= ate <= ultimo):
            return primeiro, ultimo
        return de, ate

    opcoes_mostradas: dict[str, list] = {}

    @reactive.effect
    def _opcoes_presentes_nos_filtros():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        try:
            de, ate = periodo_do_livro()
            itens = dados_apuracao.itens_filtrados(itens_do_mes(), de=de, ate=ate)
            livros = itens["LIVRO"].unique().to_list() if "LIVRO" in itens.columns else []
            situacoes = []
            if "CANCELADA" in itens.columns:
                canceladas = itens["CANCELADA"].cast(pl.Int64, strict=False).unique().to_list()
                situacoes = [situacao for situacao, valor in (("validas", 0), ("canceladas", 1)) if valor in canceladas]
            for id_filtro, fixas, valores in (
                ("livro", dados_apuracao.LIVROS_DOS_ITENS, livros),
                ("situacao", dados_apuracao.SITUACOES_DOS_ITENS, situacoes),
            ):
                novas = opcoes_presentes.opcoes(fixas, valores)
                if opcoes_mostradas.get(id_filtro) == list(novas):
                    continue
                opcoes_mostradas[id_filtro] = list(novas)
                with reactive.isolate():
                    escolhida = input[id_filtro]() or ""
                ui.update_selectize(
                    id_filtro, choices=novas, selected=opcoes_presentes.escolha_que_fica(escolhida, novas)
                )
        except Exception as exc:
            logger.warning(f"Apuracao: opcoes presentes nos filtros -- {exc}")

    @reactive.calc
    def itens_filtrados_sem_ordem() -> pl.DataFrame:
        de, ate = periodo_do_livro()
        return dados_apuracao.itens_filtrados(
            itens_do_mes(),
            input.livro() or "",
            list(input.cfops() or []),
            input.busca() or "",
            produtos=list(input.produtos() or []),
            participantes=list(input.participantes() or []),
            csts=list(input.csts() or []),
            aliquotas=list(input.aliquotas() or []),
            situacao=input.situacao() or "",
            de=de,
            ate=ate,
        )

    ordem_itens = ordem_tabela.OrdemPorValor("tabela_itens", input, session, colunas=dados_apuracao.ORDEM_DOS_ITENS)

    @reactive.calc
    def itens_filtrados() -> pl.DataFrame:
        return ordem_itens.ordenar(itens_filtrados_sem_ordem())

    paginador_itens = TabelaPaginada("tabela_itens", input, session)

    @reactive.effect
    def _itens_na_primeira_pagina():
        try:
            itens_filtrados()
            paginador_itens.reiniciar()
        except SilentException:
            return
        except Exception as exc:
            logger.warning(f"Apuracao: voltar a' primeira pagina do livro -- {exc}")

    @output(suspend_when_hidden=False)
    @render.ui
    def aviso_sem_itens():
        empresa = input.empresa() or ""
        if not mes() or not empresa or mes() in meses_com_itens():
            return None
        if dados_apuracao.revenda_da_empresa(empresa) is None:
            texto = " Esta empresa não tem livro fiscal no Fiscal."
        else:
            texto = (
                f" O livro item a item de {dados_apuracao.rotulo_mes(mes())} ainda não foi lido do {erp_da_tela()}. "
                "O Atualizar, no alto da tela, lê o mês corrente e o anterior; os outros vêm na leitura da "
                "madrugada."
            )
        return ui.p(icon_svg("triangle-exclamation", a11y="deco"), texto, class_="fis-op-alerta")

    @output(suspend_when_hidden=False)
    @render.data_frame
    def tabela_itens():
        pagina = paginador_itens.fatiar(itens_filtrados())
        if pagina.is_empty():
            return render.DataGrid(
                pl.DataFrame({"Nenhum item no livro do mês com os filtros escolhidos.": []}), height="10vh"
            )
        return largura_colunas.grade(
            dados_apuracao.na_tela_itens(pagina, list(input.colunas() or [])),
            height="56vh",
            width="100%",
            summary=False,
        )

    @output(suspend_when_hidden=False)
    @render.ui
    def paginacao_itens():
        total = itens_filtrados().height
        return paginador_itens.controles(total) if total else None

    @reactive.effect
    @reactive.event(input.colunas_padrao, ignore_init=True)
    def _colunas_padrao():
        try:
            ui.update_checkbox_group("colunas", selected=dados_apuracao.PADRAO_DOS_ITENS)
        except Exception as exc:
            logger.warning(f"Apuracao: colunas padrao -- {exc}")

    colunas_do_usuario.ColunasDaPessoa(input, VALOR_NAVSET, usuario_atual, dados_apuracao.PADRAO_DOS_ITENS)

    def _nome_da_planilha_itens() -> str:
        return f"livro_itens_{input.empresa() or 'empresa'}_{mes() or ''}.xlsx"

    @render.download(filename=_nome_da_planilha_itens)
    def planilha_itens():
        yield dados_apuracao.planilha_itens(itens_filtrados(), mes(), colunas=janela_exportar.colunas("planilha_itens"))

    ordem_pis_cofins = ordem_tabela.OrdemPorValor(
        "tabela_pis_cofins", input, session, colunas=dados_apuracao.ORDEM_DA_APURACAO_PIS_COFINS
    )

    @output(suspend_when_hidden=False)
    @render.data_frame
    def tabela_pis_cofins():
        linhas_na_tela = dados_apuracao.na_tela_apuracao_pis_cofins(ordem_pis_cofins.ordenar(apuracao_pis_cofins()))
        credor = formato.estilos(
            linhas_na_tela,
            {nome: _cor_do_saldo for nome in ("PIS do mês", "COFINS do mês")},
            so_texto=("PIS do mês", "COFINS do mês"),
        )
        return largura_colunas.grade(
            linhas_na_tela, height="44vh", width="100%", summary=False, styles=_linha_do_total(linhas_na_tela) + credor
        )

    @output(suspend_when_hidden=False)
    @render.ui
    def grafico_pis_cofins():
        por_mes = apuracao_pis_cofins()
        if por_mes.is_empty():
            return None
        return _grafico_de_barras(
            por_mes["mes"].to_list(),
            [
                ("PIS do mês", por_mes["saldo_pis"].to_list(), APURACAO_VERDE),
                ("COFINS do mês", por_mes["saldo_cofins"].to_list(), APURACAO_ESCURO),
            ],
            eixo=EIXO_EM_MIL,
        )

    @output(suspend_when_hidden=False)
    @render.ui
    def grafico_cmv():
        por_mes = apuracao_pis_cofins()
        if por_mes.is_empty():
            return None
        return _grafico_de_linhas(por_mes["mes"].to_list(), [("CMV", por_mes["cmv"].to_list(), APURACAO_ESCURO)])

    def _nome_da_planilha_pis_cofins() -> str:
        return f"pis_cofins_{input.empresa() or 'empresa'}_ate_{mes() or ''}.xlsx"

    @render.download(filename=_nome_da_planilha_pis_cofins)
    def planilha_pis_cofins():
        yield dados_apuracao.planilha_apuracao_pis_cofins(
            apuracao_pis_cofins(), mes(), colunas=janela_exportar.colunas("planilha_pis_cofins")
        )

    @reactive.effect
    def _opcoes_das_despesas():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        try:
            _opcoes_do_filtro("despesas", dados_apuracao.opcoes_despesa(titulos_pagos(), input.empresa() or ""))
            _opcoes_do_filtro("fornecedores", dados_apuracao.opcoes_fornecedor(titulos_pagos()), no_servidor=True)
        except Exception as exc:
            logger.warning(f"Apuracao: opcoes das despesas -- {exc}")

    @reactive.calc
    def periodo_dos_titulos() -> tuple:
        de, ate = input.pagos() or (None, None)
        if not de or not ate or de > ate:
            return dados_apuracao.primeiro_e_ultimo_dia(mes())
        return de, ate

    @reactive.calc
    def titulos_do_periodo_sem_ordem() -> pl.DataFrame:
        escolhidos = dados_apuracao.dos_fornecedores_escolhidos(
            dados_apuracao.das_despesas_escolhidas(titulos_pagos(), despesas_escolhidas()), fornecedores_escolhidos()
        )
        de, ate = periodo_dos_titulos()
        return dados_apuracao.titulos_do_periodo(escolhidos, input.empresa() or "", de, ate)

    ordem_titulos = ordem_tabela.OrdemPorValor(
        "tabela_titulos", input, session, colunas=dados_apuracao.ORDEM_DOS_TITULOS
    )

    @reactive.calc
    def titulos_do_periodo() -> pl.DataFrame:
        return ordem_titulos.ordenar(titulos_do_periodo_sem_ordem())

    paginador_titulos = TabelaPaginada("tabela_titulos", input, session)

    @reactive.effect
    def _titulos_na_primeira_pagina():
        try:
            titulos_do_periodo()
            paginador_titulos.reiniciar()
        except SilentException:
            return
        except Exception as exc:
            logger.warning(f"Apuracao: voltar a' primeira pagina dos titulos -- {exc}")

    @output(suspend_when_hidden=False)
    @render.data_frame
    def tabela_titulos():
        pagina = paginador_titulos.fatiar(titulos_do_periodo())
        if pagina.is_empty():
            return render.DataGrid(
                pl.DataFrame({"Nenhum título pago no período com os filtros escolhidos.": []}), height="10vh"
            )
        return largura_colunas.grade(dados_apuracao.na_tela_titulos(pagina), height="50vh", width="100%", summary=False)

    @output(suspend_when_hidden=False)
    @render.ui
    def paginacao_titulos():
        total = titulos_do_periodo().height
        return paginador_titulos.controles(total) if total else None

    def _nome_da_planilha_titulos() -> str:
        de, ate = periodo_dos_titulos()
        return (
            f"titulos_pagos_{input.empresa() or 'empresa'}_{de:%Y-%m-%d}_a_{ate:%Y-%m-%d}.xlsx"
            if de
            else "titulos.xlsx"
        )

    @render.download(filename=_nome_da_planilha_titulos)
    def planilha_titulos():
        de, ate = periodo_dos_titulos()
        yield dados_apuracao.planilha_titulos(
            titulos_do_periodo(), de, ate, colunas=janela_exportar.colunas("planilha_titulos")
        )

    FILTROS_DO_LIVRO = {
        "livro": "Livro",
        "cfops": "CFOP",
        "produtos": "Produto",
        "participantes": "Participante",
        "csts": "CST",
        "aliquotas": "Alíquota",
        "situacao": "Cancelada",
        "busca": "Busca",
    }
    FILTROS_DAS_DESPESAS = {"despesas": "Despesa", "fornecedores": "Fornecedor"}

    def _nomes_das_opcoes(id_filtro: str) -> dict[str, str]:
        if id_filtro in ("produtos", "participantes", "csts", "aliquotas"):
            return opcoes_dos_itens()[id_filtro]
        if id_filtro == "despesas":
            return dados_apuracao.opcoes_despesa(titulos_pagos(), input.empresa() or "")
        return {"livro": dados_apuracao.LIVROS_DOS_ITENS, "situacao": dados_apuracao.SITUACOES_DOS_ITENS}.get(
            id_filtro, {}
        )

    def _texto_do_escolhido(id_filtro: str, escolhido) -> str:
        nomes = _nomes_das_opcoes(id_filtro)
        if isinstance(escolhido, (list, tuple)):
            mostrados = ", ".join(nomes.get(str(valor), str(valor)) for valor in escolhido[:3])
            return mostrados + (f" e mais {len(escolhido) - 3}" if len(escolhido) > 3 else "")
        return nomes.get(str(escolhido), str(escolhido))

    @output(suspend_when_hidden=False)
    @render.ui
    def filtrando_por():
        filtros = FILTROS_DO_LIVRO if input.secao() == "livro" else FILTROS_DAS_DESPESAS
        etiquetas = []
        for id_filtro, nome in filtros.items():
            escolhido = input[id_filtro]()
            if escolhido:
                etiquetas.append(
                    ui.input_action_button(
                        f"tirar_{id_filtro}",
                        f"{nome}: {_texto_do_escolhido(id_filtro, escolhido)}",
                        icon=icon_svg("xmark", a11y="deco"),
                        class_="btn-sm btn-outline-secondary rounded-pill",
                        title="Tirar este filtro",
                    )
                )
        return ui.TagList(ui.tags.strong("Filtrando por:"), *etiquetas) if etiquetas else None

    @reactive.effect
    @reactive.event(input.tirar_livro)
    def _tirar_livro():
        ui.update_selectize("livro", selected="")

    @reactive.effect
    @reactive.event(input.tirar_cfops)
    def _tirar_cfops():
        ui.update_selectize("cfops", selected=[])

    @reactive.effect
    @reactive.event(input.tirar_produtos)
    def _tirar_produtos():
        ui.update_selectize("produtos", selected=[])

    @reactive.effect
    @reactive.event(input.tirar_participantes)
    def _tirar_participantes():
        ui.update_selectize("participantes", selected=[])

    @reactive.effect
    @reactive.event(input.tirar_csts)
    def _tirar_csts():
        ui.update_selectize("csts", selected=[])

    @reactive.effect
    @reactive.event(input.tirar_aliquotas)
    def _tirar_aliquotas():
        ui.update_selectize("aliquotas", selected=[])

    @reactive.effect
    @reactive.event(input.tirar_situacao)
    def _tirar_situacao():
        ui.update_selectize("situacao", selected="")

    @reactive.effect
    @reactive.event(input.tirar_busca)
    def _tirar_busca():
        ui.update_text("busca", value="")

    @reactive.effect
    @reactive.event(input.tirar_despesas)
    def _tirar_despesas():
        ui.update_selectize("despesas", selected=[])

    @reactive.effect
    @reactive.event(input.tirar_fornecedores)
    def _tirar_fornecedores():
        ui.update_selectize("fornecedores", selected=[])

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar():
        try:
            primeiro, ultimo = dados_apuracao.primeiro_e_ultimo_dia(mes())
            if input.secao() == "livro":
                for id_filtro in ("cfops", "produtos", "participantes", "csts", "aliquotas"):
                    ui.update_selectize(id_filtro, selected=[])
                ui.update_selectize("livro", selected="")
                ui.update_selectize("situacao", selected="")
                ui.update_text("busca", value="")
                if primeiro:
                    ui.update_date_range("dias", start=primeiro, end=ultimo)
            elif input.secao() == "despesas":
                ui.update_selectize("despesas", selected=[])
                ui.update_selectize("fornecedores", selected=[])
                if primeiro:
                    ui.update_date_range("pagos", start=primeiro, end=ultimo)
        except Exception as exc:
            logger.warning(f"Apuracao: limpar -- {exc}")

    def colunas_da_planilha() -> list[str]:
        return dados_apuracao.tabela_planilha(livros(), mes()).columns if mes() else []

    def colunas_da_planilha_receita() -> list[str]:
        return dados_apuracao.tabela_planilha_receita(receita_e_deducoes()).columns if mes() else []

    def colunas_da_planilha_despesas() -> list[str]:
        return dados_apuracao.tabela_planilha_despesas(despesas_na_tabela()).columns

    def colunas_da_planilha_itens() -> list[str]:
        return list(dados_apuracao.COLUNAS_DOS_ITENS)

    def colunas_da_planilha_pis_cofins() -> list[str]:
        return dados_apuracao.tabela_planilha_apuracao_pis_cofins(apuracao_pis_cofins()).columns if mes() else []

    def colunas_da_planilha_titulos() -> list[str]:
        return list(dados_apuracao.COLUNAS_DOS_TITULOS)

    janela_exportar = exportar.Exportar(
        input,
        {
            "planilha": ("Apuração", colunas_da_planilha),
            "planilha_receita": ("Receita bruta", colunas_da_planilha_receita),
            "planilha_despesas": ("Despesas", colunas_da_planilha_despesas),
            "planilha_itens": ("Livro item a item", colunas_da_planilha_itens),
            "planilha_pis_cofins": ("PIS e COFINS", colunas_da_planilha_pis_cofins),
            "planilha_titulos": ("Títulos pagos", colunas_da_planilha_titulos),
        },
    )


def pag_apuracao_ui(revenda: str | None = None):
    return apuracao_ui("apuracao", revenda)


def pag_apuracao_server(revenda_atual, usuario_atual=None, versao_cache=None):
    return apuracao_server(
        "apuracao", revenda_atual=revenda_atual, usuario_atual=usuario_atual, versao_cache=versao_cache
    )
