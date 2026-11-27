"""Pagina "Apuracao" (`apu`, grupo "Analises"): conferir o livro de entrada e o de saida do mes, no desenho do Power BI
"Apuracao Fiscal" (pedido do usuario, 17/11/2026: "replique o power bi [...] de maneira FACIL e INTUITIVA [...] e usar o
que ja temos").

Quatro subabas no menu (grupo "Apuracao", app.py::SECAO_DO_ITEM, o input.visao; pedido do usuario, 25/11/2026):
Entradas, Saidas e Resumo tem as abas ICMS, Livro fiscal, PIS/COFINS e Despesas (o input.secao), cada uma so' com o livro
da subaba (o Resumo, os dois; as Despesas nao entram nas Saidas); Graficos tem os graficos de todas. A caixa de filtros
(Empresa, uma, e Mes) e' a mesma; os filtros de uma aba so' aparecem nela.
* ICMS: o livro do mes por CFOP ou por operacao (um, o outro ou os dois lado a lado), com o valor contabil, a base e o
  ICMS (as colunas do Power BI), os valores do mes em mini cards a' direita do Agrupar e, no clique na linha, as notas
  dela.
* Livro fiscal: o livro do mes item a item (o IT do Control), com Livro, CFOP e Busca, paginado, Colunas e Relatorio.
* PIS/COFINS: a receita bruta e as deducoes dos 12 meses (vendas, devolucoes, vendas isentas e a base de calculo do livro
  item a item, compras, alugueis, energia, combustiveis, os outros creditos) e a apuracao do PIS e da COFINS (o credito
  e o debito dos itens, o saldo do mes, o CMV).
* Despesas: as despesas pagas mes a mes e os titulos pagos do mes, com o filtro Despesa.
Pedido do usuario (18/11/2026): o que o Power BI tinha e o Fiscal nao, so' se vier do Control ("ou fazemos algo novo
[...] ou nada"): o antecipado, os ajustes item a item e o credito de PIS/COFINS do mes anterior nao estao la'.

Le' `faturamento` e `livro_itens/<mes>` (scripts/atualiza_fiscal.py e atualiza_fiscal_parquet.py), os titulos pagos do
Financeiro e config/apuracao.json. As contas sao Dados/dados_apuracao.py.

Partes: Filtros, ICMS (o mes), Graficos, PIS/COFINS, Despesas, Livro fiscal, PIS/COFINS do livro item a item, titulos.
"""

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

from core import (
    colunas_do_usuario,
    detalhe_documento,
    exportar,
    formato,
    largura_colunas,
    opcoes_presentes,
    ordem_tabela,
)
from core.config import cnpjs_da_url, empresas_da_url, erp_das_empresas
from core.cores import APURACAO_ESCURO, APURACAO_VERDE
from core.pyecharts_shiny import renderizar
from core.secao import titulo_secao
from core.tabela_paginada import TabelaPaginada
from core.visibilidade import pagina_visivel

from .Dados import dados_apuracao

VALOR_NAVSET = "apu"
# Sempre uma escolhida (a empresa e o mes): sem o "x" de limpar.
UMA_ESCOLHIDA = {
    "plugins": ["restore_on_backspace"],
    "dropdownParent": "body",
    "dropdownClass": "selectize-dropdown ppf-filtro-dropdown",
}
# Varios de uma vez (o CFOP do livro, a despesa): o "x" em cada um.
FILTRO_VARIOS = {
    "plugins": {"remove_button": {"title": "Remover"}},
    "dropdownParent": "body",
    "dropdownClass": "selectize-dropdown ppf-filtro-dropdown",
}
# As subabas do menu (app.py::SECAO_DO_ITEM; pedido do usuario, 25/11/2026): o input.visao. Entradas, Saidas e Resumo
# tem as abas do alto (o input.secao), cada uma so' com o livro da subaba (o Resumo, os dois); os graficos ficam todos
# em Graficos.
VISOES = ("resumo", "entradas", "saidas", "graficos")
VISOES_DE_LIVRO = ("resumo", "entradas", "saidas")
LIVRO_DA_VISAO = {"entradas": "E", "saidas": "S"}
SECOES = {"icms": "ICMS", "livro": "Livro fiscal", "pis_cofins": "PIS/COFINS", "despesas": "Despesas"}
# As Despesas sao titulos pagos, o lado das entradas: nas Saidas a aba nao aparece.
SECOES_FORA_DA_VISAO = {"saidas": ("despesas",)}


def _acao(controle: ui.Tag, rotulo: str) -> ui.Tag:
    """Uma acao da faixa: o icone e o nome embaixo (o `.ppf-acao` do Financeiro)."""
    return ui.div(controle, ui.div(rotulo, class_="ppf-acao-rotulo"), class_="ppf-acao")


def _cabecalho(titulo: str, icone: str, id_planilha: str, dica_da_planilha: str, *outras_acoes: ui.Tag) -> ui.Tag:
    """O cabecalho da caixa: o titulo a' esquerda e as acoes dela a' direita, o Relatorio por ultimo."""
    acoes = ui.div(
        *outras_acoes,
        _acao(exportar.botao(id_planilha, dica_da_planilha), "Relatório"),
        class_="ppf-grupo-acoes ms-auto",
    )
    return ui.card_header(titulo_secao(titulo, icone=icone, extras=[acoes]))


def _colunas_do_livro() -> ui.Tag:
    """O Colunas da lista do livro item a item (o popover das outras listas do Fiscal)."""
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
    """A tabela com o clique no cabecalho ordenando pelos dados crus (core/ordem_tabela.py): o Total fica no fim."""
    return ui.div(
        ui.output_data_frame(id_tabela),
        class_=f"fis-tabela {ordem_tabela.CLASSE} {classe}".strip(),
        **ordem_tabela.atributos(colunas_que_ordenam),
    )


def _livro(id_tabela: str, titulo: str, icone: str, classe: str, id_das_notas: str, id_do_balao: str) -> ui.Tag:
    """Um livro do mes: a faixa colorida com o nome, a tabela por CFOP ou por operacao e o balao das notas da linha
    escolhida. O balao nasce num ponto invisivel que www/js/apuracao.js poe ao lado da linha clicada: o DataGrid nao
    aceita um ui.popover dentro da linha."""
    balao = ui.popover(
        ui.span(class_="fis-nt-ancora"),
        ui.output_ui(id_das_notas),
        id=id_do_balao,
        placement="right",
        options={"customClass": "fis-nt-balao"},
    )
    return ui.div(
        ui.div(icon_svg(icone, a11y="deco"), titulo, class_="fis-apu-titulo"),
        _caixa_da_tabela(id_tabela, dados_apuracao.ORDEM_DO_LIVRO),
        balao,
        class_=f"fis-apu-livro {classe}",
    )


# As notas da linha escolhida no livro do mes (pedido do usuário, 25/11/2026: "quando a gente clicasse no CFOP, abrisse
# as notas que compuseram esse CFOP"), num balao como o "Deve a" do Fluxo Financeiro (o usuario, 25/11/2026: "tem que
# ser um tooltip, nao um visual embaixo"): o resumo e os dias com as somas num `ui.accordion`. As notas de um dia vem
# do servidor so' quando ele abre (um CFOP de venda chega a 12 mil notas no mes).


def _em_reais(valor) -> ui.Tag:
    return ui.span(formato.moeda(valor) if valor else "-", class_="valor")


def _id_do_dia(prefixo: str, livro: str, dia: date) -> str:
    return f"{prefixo}_{livro}_{dia:%Y%m%d}"


def _dia_no_accordion(prefixo: str, livro: str, dia: dict) -> ui.Tag:
    """Um dia: o titulo com as somas (o clique abre e fecha) e o "Carregando" ate' as notas chegarem."""
    quantas = dia["NOTAS"]
    titulo = ui.div(
        ui.span(ui.span(icon_svg("angle-right", a11y="deco"), class_="fis-nt-seta"), formato.data(dia["DATA"])),
        ui.span(f"{formato.inteiro(quantas)} nota{'' if quantas == 1 else 's'}"),
        _em_reais(dia["VALOR"]),
        _em_reais(dia["BASE_ICMS"]),
        _em_reais(dia["ICMS"]),
        ui.span(),
        class_="fis-nt-linha",
    )
    return ui.accordion_panel(
        titulo,
        ui.div(
            ui.div("Carregando as notas...", class_="fis-nt-carregando"), id=_id_do_dia(prefixo, livro, dia["DATA"])
        ),
        value=dia["DATA"].isoformat(),
    )


def _link_da_nota(chave: str | None, arquivos: dict[str, str], url_pdf) -> ui.TagChild:
    """Como no balao do Fluxo Financeiro (pag_fluxo.py::_link_da_nota): com o XML no acervo, o PDF montado dele; so' com
    a chave de NF-e, a consulta do DANFE; senao "-"."""
    if chave and chave in arquivos:
        return ui.tags.a(
            icon_svg("file-pdf", a11y="deco"),
            href=url_pdf(chave, arquivos[chave]),
            target="_blank",
            rel="noopener noreferrer",
            title="Abrir o PDF da nota (montado do XML)",
            class_="fis-nt-pdf",
        )
    consulta = dados_apuracao.consulta_da_chave(chave)
    if consulta:
        # A nota que a propria empresa emitiu (as saidas e a entrada propria) nao esta' no acervo, que e' o que ela recebe.
        return ui.tags.a(
            icon_svg("up-right-from-square", a11y="deco"),
            href=consulta,
            target="_blank",
            rel="noopener noreferrer",
            title="Consultar DANFE",
            class_="fis-nt-consulta",
        )
    return "-"


def _linha_da_nota(nota: dict, link: ui.TagChild) -> ui.Tag:
    """Uma nota do dia: o numero e a serie, o participante (o documento na dica), as somas dos itens e o PDF."""
    serie = str(nota["SERIE"] or "").strip()
    documento = dados_apuracao.documento_do_participante(nota["CNPJ_PARTICIPANTE"])
    return ui.div(
        ui.span(
            f"{nota['NUMERO']}" + (f" (série {serie})" if serie else ""),
            title=f"Nota {nota['NUMERO']}" + (f", série {serie}" if serie else ""),
        ),
        ui.span(nota["NOME"] or documento, title=documento, class_="fis-nt-participante"),
        _em_reais(nota["VALOR"]),
        _em_reais(nota["BASE_ICMS"]),
        _em_reais(nota["ICMS"]),
        ui.span(link, class_="fis-nt-link"),
        class_="fis-nt-linha fis-nt-nota",
    )


def _titulo_das_notas(cfops: list[str], por_operacao: bool) -> str:
    if por_operacao:
        return f"{dados_apuracao.grupo_da_operacao(cfops[0])} | CFOP{'' if len(cfops) == 1 else 's'} {', '.join(cfops)}"
    return f"CFOP {cfops[0]} | {dados_apuracao.nome_da_operacao(cfops[0]) or 'sem nome'}"


def _painel_das_notas(
    cfops: list[str],
    por_operacao: bool,
    livro: str,
    notas: pl.DataFrame,
    valor_no_livro: float,
    prefixo: str,
    id_dos_dias: str,
    sem_itens: str | None,
) -> ui.Tag:
    """O conteudo do balao: o titulo (o X e' o do proprio balao), o resumo, os dias e a rolagem."""
    topo = ui.div(_titulo_das_notas(cfops, por_operacao), class_="fis-nt-topo")
    if sem_itens:
        return ui.div(topo, ui.div(sem_itens, class_="fis-nt-vazio"), class_="fis-nt")
    resumo = ui.div(
        *[
            ui.div(ui.span(nome), ui.tags.strong(valor))
            for nome, valor in (
                ("Notas", formato.inteiro(notas.height)),
                ("Valor contábil no livro", formato.moeda(valor_no_livro)),
                ("Valor dos itens", formato.moeda(round(float(notas["VALOR"].sum() or 0), 2))),
                ("ICMS das notas", formato.moeda(round(float(notas["ICMS"].sum() or 0), 2))),
            )
        ],
        class_="fis-nt-resumo",
    )
    if notas.is_empty():
        return ui.div(
            topo,
            resumo,
            ui.div("Nenhuma nota válida com este CFOP no livro item a item do mês.", class_="fis-nt-vazio"),
            class_="fis-nt",
        )
    dias = [
        _dia_no_accordion(prefixo, livro, dia) for dia in dados_apuracao.dias_das_notas(notas).iter_rows(named=True)
    ]
    cabecalho = ui.div(
        ui.span("Dia / nota"),
        ui.span("Participante"),
        ui.span("Valor dos itens", class_="valor"),
        ui.span("Base de cálculo", class_="valor"),
        ui.span("ICMS", class_="valor"),
        ui.span("NF", class_="fis-nt-link"),
        class_="fis-nt-linha fis-nt-cabecalho",
    )
    return ui.div(
        topo,
        resumo,
        ui.div("Notas por dia", class_="fis-nt-secao"),
        ui.div(
            cabecalho,
            ui.accordion(*dias, id=id_dos_dias, open=False, multiple=True, class_="fis-nt-dias"),
            class_="fis-nt-rolagem",
        ),
        class_="fis-nt",
    )


def _mini_card(rotulo: str, valor: str, classe: str = "", dica: ui.TagChild | None = None) -> ui.Tag:
    """Um mini card da linha do Agrupar (o lugar do antigo painel cinza; pedido do usuario, 25/11/2026: "os valores
    na mesma linha das opcoes Por CFOP e Por operacao, no lado direito, como mini cards"): o nome em cima, o valor
    embaixo e, quando ha', o detalhe no balao que o clique no cartao abre."""
    card = ui.div(
        ui.div(rotulo, class_="fis-apu-rotulo"),
        ui.div(valor, class_=f"fis-apu-valor {classe}".strip()),
        class_="fis-apu-mini",
    )
    return _no_balao(card, rotulo, dica)


def _no_balao(card: ui.Tag, rotulo: str, dica: ui.TagChild | None) -> ui.Tag:
    """O cartao com detalhe abre, no clique, um ui.popover no desenho do balao das notas do CFOP (o usuario, 26/11/2026:
    "esses tooltip nao, quero o bonitinho, popover")."""
    if dica is None:
        return card
    card.add_class("fis-apu-mini-com-balao")
    return ui.popover(
        card,
        ui.div(dica, class_="fis-apu-balao-corpo"),
        title=rotulo,
        placement="bottom",
        options={"customClass": "fis-apu-balao"},
    )


def _linha_do_par(nome: str, valor: str, classe: str) -> ui.Tag:
    """Uma linha do cartao duplo: o nome curto a' esquerda e o valor a' direita."""
    return ui.div(
        ui.span(nome, class_="fis-apu-par-nome"),
        ui.span(valor, class_=f"fis-apu-par-valor {classe}".strip()),
        class_="fis-apu-par",
    )


def _mini_card_duplo(
    rotulo: str, de_cima: tuple[str, str, str], de_baixo: tuple[str, str, str], dica: ui.TagChild | None = None
) -> ui.Tag:
    """O par entrada x saida num cartao so' (o usuario, 26/11/2026: "no resumo ficou com muito card; os que tem relacao
    entrada x saida, os dois valores no mesmo card, um abaixo do outro e um separador entre eles"): o nome em cima e,
    em cada linha, (o nome curto, o valor, a classe da cor)."""
    card = ui.div(
        ui.div(rotulo, class_="fis-apu-rotulo"),
        _linha_do_par(*de_cima),
        ui.div(class_="fis-apu-par-separador"),
        _linha_do_par(*de_baixo),
        class_="fis-apu-mini fis-apu-mini-duplo",
    )
    return _no_balao(card, rotulo, dica)


def _linha_do_sped(rotulo: str, valor: float) -> ui.Tag:
    """Uma linha do detalhe do SPED gerado: o nome a' esquerda e o valor a' direita."""
    return ui.div(ui.span(rotulo), ui.span(formato.moeda(valor)), class_="fis-apu-linha")


# Os ajustes da apuracao do SPED gerado em cartoes, como os do Power BI, com as linhas no balao em vez de trocar a tabela
# (o usuario, 26/11/2026: "clicar nos cards nao precisa trocar a tabela, e sim so' mostrar tooltip"). Cada subaba, os do
# livro dela.
AJUSTES_DA_VISAO = {
    "entradas": ("outros_creditos", "estornos_de_credito"),
    "saidas": ("outros_debitos", "estornos_de_debito"),
}
SEM_O_SPED = "Vem do SPED gerado: gere o SPED do mês na tela SPED x XML."


def _linhas_do_ajuste(tipo: str, apuracao_oficial: dict) -> list[ui.Tag]:
    """As linhas do E111 de um tipo (codigo e descricao a' esquerda, valor a' direita), para o balao."""
    return [
        ui.div(
            ui.span(f"{ajuste.get('codigo', '')} {ajuste.get('descricao', '')}".strip()),
            ui.span(formato.moeda(float(ajuste.get("valor") or 0))),
            class_="fis-apu-linha",
        )
        for ajuste in dados_apuracao.ajustes_do_tipo(apuracao_oficial, tipo)
    ]


def _mini_card_do_ajuste(tipo: str, apuracao_oficial: dict | None) -> ui.Tag:
    """Um tipo de ajuste do E111: a soma no cartao e cada linha (codigo, descricao, valor) no balao."""
    nome = dados_apuracao.nome_do_tipo_de_ajuste(tipo)
    if apuracao_oficial is None:
        return _mini_card(nome, "-", dica=SEM_O_SPED)
    linhas = _linhas_do_ajuste(tipo, apuracao_oficial)
    dica = (
        ui.div(*linhas, class_="fis-apu-detalhe-sped") if linhas else "Nenhum ajuste deste tipo no SPED gerado do mês."
    )
    return _mini_card(nome, formato.moeda(apuracao_oficial["ajustes_por_tipo"][tipo]), dica=dica)


# No Resumo, os ajustes em par: (nome do cartao, o de entrada, o de saida).
PARES_DE_AJUSTE = (
    ("Outros ajustes", "outros_creditos", "outros_debitos"),
    ("Estornos", "estornos_de_credito", "estornos_de_debito"),
)


def _mini_card_do_par_de_ajustes(
    rotulo: str, tipo_de_entrada: str, tipo_de_saida: str, apuracao_oficial: dict | None
) -> ui.Tag:
    """Os dois lados de um ajuste (o de credito em cima, o de debito embaixo) e, no balao, as linhas de cada um."""
    if apuracao_oficial is None:
        return _mini_card_duplo(rotulo, ("Créditos", "-", ""), ("Débitos", "-", ""), dica=SEM_O_SPED)
    por_tipo = apuracao_oficial["ajustes_por_tipo"]
    partes = []
    for tipo in (tipo_de_entrada, tipo_de_saida):
        partes.append(ui.div(dados_apuracao.nome_do_tipo_de_ajuste(tipo), class_="fis-apu-detalhe-titulo"))
        partes.extend(_linhas_do_ajuste(tipo, apuracao_oficial) or [ui.div("nenhum", class_="fis-apu-linha")])
    return _mini_card_duplo(
        rotulo,
        ("Créditos", formato.moeda(por_tipo[tipo_de_entrada]), ""),
        ("Débitos", formato.moeda(por_tipo[tipo_de_saida]), ""),
        dica=ui.div(*partes, class_="fis-apu-detalhe-sped"),
    )


def _mini_card_do_credor_anterior(apuracao_oficial: dict | None) -> ui.Tag:
    if apuracao_oficial is None:
        return _mini_card("Credor anterior", "-", dica=SEM_O_SPED)
    return _mini_card(
        "Credor anterior",
        formato.moeda(apuracao_oficial["saldo_credor_anterior"]),
        dica="O saldo credor do mês anterior que entrou na apuração do SPED gerado.",
    )


def _mini_card_do_sped(apuracao_oficial: dict | None) -> ui.Tag:
    """A apuracao oficial (o E110 do SPED gerado na tela SPED x XML): o resultado no card e, no balao, os debitos e os
    creditos com os ajustes que nao sao zero e o saldo credor anterior. Sem o SPED do mes, o aviso de onde gera-lo."""
    if apuracao_oficial is None:
        return _mini_card(
            "No SPED gerado",
            "-",
            dica="Gere o SPED do mês na tela SPED x XML para ver os ajustes e o saldo credor anterior.",
        )
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
    gerado_em = apuracao_oficial["gerado_em"]
    data_da_geracao = f"gerado em {gerado_em[8:10]}/{gerado_em[5:7]}/{gerado_em[:4]}" if len(gerado_em) >= 10 else ""
    detalhe = ui.div(ui.div(data_da_geracao) if data_da_geracao else None, *linhas, class_="fis-apu-detalhe-sped")
    if apuracao_oficial["saldo_credor"]:
        return _mini_card("SPED: credor", formato.moeda(apuracao_oficial["saldo_credor"]), "fis-apu-credito", detalhe)
    return _mini_card("SPED: a recolher", formato.moeda(apuracao_oficial["a_recolher"]), "fis-apu-debito", detalhe)


def _cor_do_saldo(texto_do_saldo: str) -> str | None:
    """O saldo do PIS e da COFINS do mes: credor em verde, a recolher em vermelho (as cores do saldo do ICMS)."""
    if texto_do_saldo.startswith("credor"):
        return "verde"
    return "vermelho" if texto_do_saldo not in ("-", "R$ 0,00") else None


def _linha_do_total(linhas_na_tela: pl.DataFrame) -> list[dict]:
    """A ultima linha (o Total) em negrito e congelada no pe' da tabela."""
    if linhas_na_tela.is_empty() or linhas_na_tela.row(-1)[0] != "Total":
        return []
    return [{"location": "body", "rows": [linhas_na_tela.height - 1], "class": "fis-apu-total"}]


# Os valores em reais no formato daqui: o eixo em milhoes ("2,5 mi") e a dica com os centavos ("R$ 1.234,56").
EIXO_EM_MILHOES = JsCode(
    "function (valor) { return (valor / 1000000).toLocaleString('pt-BR', {maximumFractionDigits: 1}) + ' mi'; }"
)
# O saldo do PIS e da COFINS do mes fica em dezenas de milhares: em milhoes, o eixo so' diria "0 mi".
EIXO_EM_MIL = JsCode(
    "function (valor) { return (valor / 1000).toLocaleString('pt-BR', {maximumFractionDigits: 0}) + ' mil'; }"
)
DICA_EM_REAIS = JsCode(
    "function (valor) { return valor == null ? '-' : 'R$ ' + Number(valor).toLocaleString('pt-BR', "
    "{minimumFractionDigits: 2, maximumFractionDigits: 2}); }"
)
# O rotulo do eixo sempre dentro do quadro (em tela estreita ele saia cortado a' esquerda) e a legenda embaixo.
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
    """Barras por mes, uma serie por (nome, valores, cor), no desenho do grafico do Painel."""
    barras = Bar()
    barras.add_xaxis([dados_apuracao.rotulo_curto(mes) for mes in meses])
    for nome, valores, cor in series:
        barras.add_yaxis(nome, valores, color=cor)
    _opcoes_comuns(
        barras, options.TooltipOpts(trigger="axis", axis_pointer_type="shadow", value_formatter=DICA_EM_REAIS), eixo
    )
    return ui.HTML(renderizar(barras, altura="32vh"))


def _grafico_de_linhas(meses: list[str], series: list[tuple[str, list, str]]) -> ui.HTML:
    """Linhas por mes, uma serie por (nome, valores, cor)."""
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


# UI --------------------------------------------------------------------------


@module.ui
def apuracao_ui(revenda: str | None = None, visao: str | None = None):
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
    # Os filtros que so' uma aba usa aparecem so' nela, no desenho das outras telas: o periodo e a Busca na linha, o
    # resto no Filtros (pedido do usuario, 18/11/2026: "nao deixou filtro/filtro suficiente ... adicione").
    filtros_do_livro = ui.panel_conditional(
        "input.visao !== 'graficos' && input.secao === 'livro'",
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
                    # O Livro so' no Resumo: nas Entradas e nas Saidas o livro e' o da subaba.
                    ui.panel_conditional(
                        "input.visao === 'resumo'",
                        ui.input_selectize(
                            "livro", "Livro", dados_apuracao.LIVROS_DOS_ITENS, width="100%", options=UMA_ESCOLHIDA
                        ),
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
        "input.visao !== 'graficos' && input.secao === 'despesas'",
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
    # O "Filtrando por" e o Limpar das abas com filtro proprio, a' esquerda do total.
    filtrando_por = ui.panel_conditional(
        "input.visao !== 'graficos' && (input.secao === 'livro' || input.secao === 'despesas')",
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
        # A lista tem a altura dela mesmo com poucas linhas (e o aviso do mes nao lido vai dentro dela): filtro nao mexe
        # no resto da pagina (o usuario, 26/11/2026: "quando eu mudo os filtros, algumas coisas se movimentam").
        ui.div(
            ui.output_data_frame("tabela_itens"),
            class_=f"fis-tabela fis-apu-lista-fixa {ordem_tabela.CLASSE}",
            **ordem_tabela.atributos(dados_apuracao.ORDEM_DOS_ITENS),
        ),
        ui.output_ui("paginacao_itens"),
        class_="fis-caixa-lista",
    )
    # A aba ICMS de Entradas, Saidas e Resumo: a mesma caixa, com um livro, o outro ou os dois lado a lado; os valores
    # do mes nos mini cards a' direita do Agrupar.
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
                # O aviso na mesma linha, entre o Agrupar e os cartoes: aparecer nao empurra as tabelas.
                ui.output_ui("aviso_sem_impostos", class_="fis-apu-aviso-na-linha"),
                ui.output_ui("mini_cards", class_="fis-apu-minis"),
                class_="fis-barra fis-apu-barra",
            ),
            ui.div(
                ui.panel_conditional(
                    "input.visao !== 'saidas'",
                    _livro(
                        "tabela_entradas",
                        "Entradas",
                        "arrow-right-to-bracket",
                        "fis-apu-entrada",
                        "notas_entradas",
                        "balao_E",
                    ),
                ),
                ui.panel_conditional(
                    "input.visao !== 'entradas'",
                    _livro(
                        "tabela_saidas",
                        "Saídas",
                        "arrow-right-from-bracket",
                        "fis-apu-saida",
                        "notas_saidas",
                        "balao_S",
                    ),
                ),
                class_="fis-apu-livros",
            ),
            class_="fis-caixa-lista",
        ),
    )
    parte_dos_graficos = ui.TagList(
        ui.card(
            ui.card_header(titulo_secao("ICMS, mês a mês", icone="chart-column")),
            ui.layout_columns(
                _quadro_do_grafico("ICMS creditado x debitado", "grafico"),
                _quadro_do_grafico("Bonificações recebidas x dadas", "grafico_bonificacoes"),
                col_widths={"sm": (12, 12), "lg": (6, 6)},
                gap="0.75rem",
                class_="fis-apu-grade",
            ),
            class_="fis-caixa-lista",
        ),
        ui.card(
            ui.card_header(titulo_secao("PIS/COFINS, mês a mês", icone="chart-line")),
            ui.layout_columns(
                _quadro_do_grafico("Receita bruta x bonificação dada", "grafico_receita"),
                _quadro_do_grafico("Compras", "grafico_compras"),
                _quadro_do_grafico("PIS e COFINS do mês", "grafico_pis_cofins"),
                _quadro_do_grafico("CMV", "grafico_cmv"),
                col_widths={"sm": (12, 12, 12, 12), "lg": (6, 6, 6, 6)},
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
                class_=f"fis-tabela fis-apu-lista-fixa {ordem_tabela.CLASSE}",
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
                # A subaba do menu e' o input.visao (app.py::SECAO_DO_ITEM); as abas do alto, o input.secao.
                ui.navset_hidden(
                    *[ui.nav_panel(None, value=codigo) for codigo in VISOES],
                    id="visao",
                    selected=visao if visao in VISOES else "resumo",
                ),
                ui.panel_conditional(
                    "input.visao !== 'graficos'",
                    ui.navset_underline(
                        *[ui.nav_panel(nome, value=codigo) for codigo, nome in SECOES.items()],
                        id="secao",
                        selected="icms",
                    ),
                ),
                linha_principal,
                filtros_do_livro,
                filtros_das_despesas,
                # A linha ja' nasce na altura das etiquetas do "Filtrando por": escolher um filtro nao empurra a pagina.
                ui.div(
                    filtrando_por,
                    ui.div(ui.output_ui("total_da_lista"), class_="ms-auto"),
                    class_="d-flex flex-wrap align-items-center justify-content-between gap-2 fis-apu-linha-filtros",
                ),
                class_="fis-qive",
            ),
            class_="fis-caixa-filtros",
        ),
        ui.panel_conditional("input.visao !== 'graficos' && (!input.secao || input.secao === 'icms')", parte_do_icms),
        ui.panel_conditional("input.visao === 'graficos'", parte_dos_graficos),
        ui.panel_conditional("input.visao !== 'graficos' && input.secao === 'livro'", parte_do_livro),
        ui.panel_conditional("input.visao !== 'graficos' && input.secao === 'pis_cofins'", parte_do_pis_cofins),
        ui.panel_conditional("input.visao !== 'graficos' && input.secao === 'despesas'", parte_das_despesas),
        # As cores do Power BI so' nesta tela (style.css, .fis-apu-pbi).
        class_="fis-modulo fis-apu-pbi",
    )


# Server ----------------------------------------------------------------------


@module.server
def apuracao_server(input, output, session, revenda_atual, usuario_atual=None, versao_cache=None):
    @reactive.calc
    def cnpjs() -> list[str]:
        """As empresas da URL (o recorte e' o filtro Empresa)."""
        return cnpjs_da_url(revenda_atual())

    @reactive.calc
    def erp_da_tela() -> str:
        """O sistema do livro da empresa escolhida (Control, WinThor): o nome nas mensagens."""
        empresa = input.empresa() or ""
        return erp_das_empresas([empresa] if empresa else cnpjs())

    # Filtros -----------------------------------------------------------------

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

    # Lido ao abrir a tela e no fim do Atualizar do cabecalho (versao_cache), no lugar, como nas irmas.
    @reactive.calc
    def livros() -> pl.DataFrame:
        if versao_cache is not None:
            versao_cache()
        return dados_apuracao.livros_da_empresa(input.empresa() or "")

    @reactive.effect
    def _opcoes_mes():
        """Os meses com livro, o mais novo primeiro; abre no ultimo mes fechado (o atual ainda corre)."""
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

    # O ICMS antecipado pago (os titulos do ICMS FRONTEIRA do Financeiro): a' parte, fora do saldo do livro.
    @reactive.calc
    def antecipado() -> pl.DataFrame:
        return dados_apuracao.antecipado_pago(titulos_pagos(), input.empresa() or "", mes())

    # O credito e o debito dos 12 meses: so' o grafico da subaba Graficos (a tabela Mes a mes saiu, pedido do usuario,
    # 26/11/2026).
    @reactive.calc
    def meses_lado_a_lado() -> pl.DataFrame:
        return dados_apuracao.mes_a_mes(livros(), mes())

    def _antecipado_do_mes() -> ui.Tag:
        """O mini card do antecipado: o pago no mes, ou o traco (sem os titulos do mes)."""
        do_mes = antecipado().filter(pl.col("mes") == mes())
        valor = do_mes["antecipado"][0] if not do_mes.is_empty() else None
        return _mini_card(
            "Antecipado pago",
            formato.moeda(valor) if valor is not None else "-",
            dica="As guias de fronteira pagas no mês, fora do saldo do livro.",
        )

    @reactive.calc
    def bonificacoes() -> pl.DataFrame:
        return dados_apuracao.bonificacoes_mes_a_mes(livros(), mes())

    @reactive.calc
    def receita_bruta() -> pl.DataFrame:
        return dados_apuracao.receita_bruta_mes_a_mes(livros(), mes())

    # Os titulos pagos do Financeiro, lidos uma vez para as despesas e para as deducoes do PIS/COFINS.
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

    # O PIS e a COFINS do livro item a item (12 meses), lidos uma vez para a receita, a apuracao e os graficos.
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

    # O livro de cada subaba (o usuario, 25/11/2026: "tudo separado por livro"): Entradas "E", Saidas "S"; no Resumo,
    # o do filtro Livro (os dois, ou o escolhido).
    @reactive.calc
    def livro_da_subaba() -> str:
        return LIVRO_DA_VISAO.get(input.visao(), "")

    @reactive.calc
    def livro_dos_itens() -> str:
        return livro_da_subaba() or input.livro() or ""

    @reactive.effect
    def _abas_da_subaba():
        """A aba que nao e' do livro da subaba (as Despesas nas Saidas) sai do alto; se era a aberta, volta ao ICMS."""
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        try:
            fora = SECOES_FORA_DA_VISAO.get(input.visao(), ())
            for secao in SECOES:
                ui.update_nav_panel("secao", secao, "hide" if secao in fora else "show")
            with reactive.isolate():
                if input.secao() in fora:
                    ui.update_navset("secao", selected="icms")
        except Exception as exc:
            logger.warning(f"Apuracao: abas da subaba -- {exc}")

    @render.ui
    def total_da_lista():
        """O movimento do mes em texto (sem cartoes, como nas outras telas): o valor contabil de cada livro; na aba do
        livro item a item, os itens da lista; na das despesas, os titulos pagos do mes."""
        visao = input.visao()
        if not mes() or visao not in VISOES_DE_LIVRO:
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
        entradas = ui.TagList(
            ui.span("entradas "),
            ui.tags.strong(formato.moeda(resumo_do_mes["valor_entradas"])),
            ui.span(f" ({resumo_do_mes['cfops_entradas']} CFOPs)"),
        )
        saidas = ui.TagList(
            ui.span("saídas "),
            ui.tags.strong(formato.moeda(resumo_do_mes["valor_saidas"])),
            ui.span(f" ({resumo_do_mes['cfops_saidas']} CFOPs)"),
        )
        partes = {"entradas": [entradas], "saidas": [saidas], "resumo": [entradas, ui.span(" · "), saidas]}
        return ui.span(ui.span(f"{dados_apuracao.rotulo_mes(mes())}: "), *partes[visao])

    # ICMS: o mes -------------------------------------------------------------
    # Recebe valor mesmo escondido: o F5 volta na aba guardada, e a tela de carregamento espera todo output da pagina.

    # Sem texto de explicacao nas abas (pedido do usuario, 17/11/2026: "horrivel esse comentario. nao precisa"): so' o
    # aviso que pede uma acao.
    @output(suspend_when_hidden=False)
    @render.ui
    def aviso_sem_impostos():
        """O livro do mes lido antes de os impostos chegarem: o aviso de usar o Atualizar."""
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
    def mini_cards():
        """Os valores do mes a' direita do Agrupar, so' os do livro da subaba (o usuario, 25/11/2026): o credito e os
        ajustes de credito do SPED gerado nas Entradas, o debito e os de debito nas Saidas; no Resumo, os dois, o
        antecipado, o saldo do livro, o SPED gerado, os quatro ajustes e o saldo credor anterior."""
        secao = input.visao()
        if secao not in VISOES_DE_LIVRO:
            return None
        tem_o_mes = bool(mes()) and com_impostos()
        resumo_do_mes = resumo() if tem_o_mes else {}
        credito = _mini_card(
            "Crédito de ICMS",
            formato.moeda(resumo_do_mes["credito"]) if tem_o_mes else "-",
            "fis-apu-credito" if tem_o_mes else "",
        )
        debito = _mini_card(
            "Débito de ICMS",
            formato.moeda(resumo_do_mes["debito"]) if tem_o_mes else "-",
            "fis-apu-debito" if tem_o_mes else "",
        )
        do_sped = dados_apuracao.apuracao_do_sped(input.empresa() or "", mes()) if mes() else None
        if secao == "entradas":
            return ui.TagList(credito, *[_mini_card_do_ajuste(tipo, do_sped) for tipo in AJUSTES_DA_VISAO[secao]])
        if secao == "saidas":
            return ui.TagList(debito, *[_mini_card_do_ajuste(tipo, do_sped) for tipo in AJUSTES_DA_VISAO[secao]])
        # O Resumo: os pares entrada x saida num cartao so', o credito em cima e o debito embaixo.
        icms = _mini_card_duplo(
            "ICMS do livro",
            (
                "Crédito",
                formato.moeda(resumo_do_mes["credito"]) if tem_o_mes else "-",
                "fis-apu-credito" if tem_o_mes else "",
            ),
            (
                "Débito",
                formato.moeda(resumo_do_mes["debito"]) if tem_o_mes else "-",
                "fis-apu-debito" if tem_o_mes else "",
            ),
        )
        saldo = resumo_do_mes.get("saldo", 0) if tem_o_mes else None
        if saldo is None:
            card_do_saldo = _mini_card("Saldo no livro", "-")
        elif saldo > 0:
            card_do_saldo = _mini_card("A recolher no livro", formato.moeda(saldo), "fis-apu-debito")
        elif saldo < 0:
            card_do_saldo = _mini_card("Credor no livro", formato.moeda(-saldo), "fis-apu-credito")
        else:
            card_do_saldo = _mini_card("Saldo no livro", formato.moeda(0))
        pares = [
            _mini_card_do_par_de_ajustes(rotulo, de_entrada, de_saida, do_sped)
            for rotulo, de_entrada, de_saida in PARES_DE_AJUSTE
        ]
        return ui.TagList(
            icms,
            _antecipado_do_mes() if mes() else _mini_card("Antecipado pago", "-"),
            card_do_saldo,
            _mini_card_do_sped(do_sped),
            *pares,
            _mini_card_do_credor_anterior(do_sped),
        )

    # A ordem escolhida no cabecalho de cada tabela (core/ordem_tabela.py, com as colunas de Dados/dados_apuracao.py).
    ordem_entradas = ordem_tabela.OrdemPorValor(
        "tabela_entradas", input, session, colunas=dados_apuracao.ORDEM_DO_LIVRO
    )
    ordem_saidas = ordem_tabela.OrdemPorValor("tabela_saidas", input, session, colunas=dados_apuracao.ORDEM_DO_LIVRO)
    ordem_receita = ordem_tabela.OrdemPorValor(
        "tabela_receita", input, session, colunas=dados_apuracao.ORDEM_DA_RECEITA
    )
    ordem_despesas = ordem_tabela.OrdemPorValor(
        "tabela_despesas", input, session, colunas=dados_apuracao.ORDEM_DAS_DESPESAS
    )

    def _linhas_do_livro(livro_por_cfop: pl.DataFrame, ordem: ordem_tabela.OrdemPorValor) -> pl.DataFrame:
        """O livro por CFOP ou pelo grupo, conforme o Agrupar, na ordem do cabecalho."""
        if input.agrupar() == "operacao":
            por_grupo = ordem.ordenar(dados_apuracao.por_operacao(livro_por_cfop))
            return dados_apuracao.na_tela_operacao(por_grupo, com_impostos())
        por_cfop = ordem.ordenar(dados_apuracao.com_o_nome_da_operacao(livro_por_cfop))
        return dados_apuracao.na_tela_cfop(por_cfop, com_impostos())

    @reactive.calc
    def linhas_entradas() -> pl.DataFrame:
        return _linhas_do_livro(entradas_do_mes(), ordem_entradas)

    @reactive.calc
    def linhas_saidas() -> pl.DataFrame:
        return _linhas_do_livro(saidas_do_mes(), ordem_saidas)

    # O clique na linha escolhe (a selecao do proprio componente) e abre as notas dela embaixo; o mesmo clique fecha.
    @output(suspend_when_hidden=False)
    @render.data_frame
    def tabela_entradas():
        linhas_na_tela = linhas_entradas()
        return largura_colunas.grade(
            linhas_na_tela,
            height="44vh",
            width="100%",
            summary=False,
            selection_mode="row",
            styles=_linha_do_total(linhas_na_tela),
        )

    @output(suspend_when_hidden=False)
    @render.data_frame
    def tabela_saidas():
        linhas_na_tela = linhas_saidas()
        return largura_colunas.grade(
            linhas_na_tela,
            height="44vh",
            width="100%",
            summary=False,
            selection_mode="row",
            styles=_linha_do_total(linhas_na_tela),
        )

    # As notas da linha escolhida -----------------------------------------------------------------------------------

    def _cfops_escolhidos(tabela, linhas_na_tela: pl.DataFrame) -> list[str]:
        try:
            escolhidas = list((tabela.cell_selection() or {}).get("rows") or [])
        except Exception:
            return []
        return dados_apuracao.cfops_da_linha(linhas_na_tela, escolhidas[0]) if escolhidas else []

    @reactive.calc
    def cfops_entradas() -> list[str]:
        return _cfops_escolhidos(tabela_entradas, linhas_entradas())

    @reactive.calc
    def cfops_saidas() -> list[str]:
        return _cfops_escolhidos(tabela_saidas, linhas_saidas())

    @reactive.calc
    def notas_das_entradas() -> pl.DataFrame:
        cfops = cfops_entradas()
        return dados_apuracao.notas_dos_cfops(itens_do_mes(), "E", cfops) if cfops else pl.DataFrame()

    @reactive.calc
    def notas_das_saidas() -> pl.DataFrame:
        cfops = cfops_saidas()
        return dados_apuracao.notas_dos_cfops(itens_do_mes(), "S", cfops) if cfops else pl.DataFrame()

    def _notas_na_tela(livro: str, cfops: list[str], livro_por_cfop: pl.DataFrame, notas_do_livro) -> ui.Tag | None:
        if not cfops:
            return None
        sem_itens = None
        if mes() not in meses_com_itens():
            sem_itens = (
                f"As notas vêm do livro item a item, e o de {dados_apuracao.rotulo_mes(mes())} ainda não foi "
                f"lido do {erp_da_tela()}."
            )
        notas = pl.DataFrame() if sem_itens else notas_do_livro()
        valor_no_livro = round(float(livro_por_cfop.filter(pl.col("CFOP").is_in(cfops))["VALOR"].sum() or 0), 2)
        dias_mostrados[livro] = set()
        with reactive.isolate():
            por_operacao = input.agrupar() == "operacao"
        return _painel_das_notas(
            cfops, por_operacao, livro, notas, valor_no_livro, session.ns("notas"), f"dias_{livro}", sem_itens
        )

    @output(suspend_when_hidden=False)
    @render.ui
    def notas_entradas():
        return _notas_na_tela("E", cfops_entradas(), entradas_do_mes(), notas_das_entradas)

    @output(suspend_when_hidden=False)
    @render.ui
    def notas_saidas():
        return _notas_na_tela("S", cfops_saidas(), saidas_do_mes(), notas_das_saidas)

    # Os dias do painel que ja' receberam as notas (o painel novo zera): abrir de novo nao manda de novo.
    dias_mostrados: dict[str, set[str]] = {"E": set(), "S": set()}
    # O PDF da nota montado do XML do acervo, a rota do "Ver" das outras telas: so' a chave que esta sessao mostrou.
    url_pdf_da_nota = detalhe_documento.rota_pdf(session, "pdf_nota_apuracao")

    def _mostrar_os_dias_abertos(livro: str, abertos, notas: pl.DataFrame) -> None:
        """Os dias que acabaram de abrir no accordion: as notas deles entram no lugar do "Carregando"."""
        for valor_do_dia in abertos or []:
            if valor_do_dia in dias_mostrados[livro]:
                continue
            dia = date.fromisoformat(str(valor_do_dia))
            dias_mostrados[livro].add(valor_do_dia)
            alvo = "#" + _id_do_dia(session.ns("notas"), livro, dia)
            do_dia = notas.filter(pl.col("DATA") == dia) if not notas.is_empty() else notas
            # O XML so' das chaves do dia: o indice do acervo e' lido filtrado, nunca inteiro.
            arquivos = dados_apuracao.xml_das_chaves(do_dia["CHAVE"].to_list() if "CHAVE" in do_dia.columns else [])
            ui.remove_ui(selector=f"{alvo} .fis-nt-carregando")
            ui.insert_ui(
                ui.TagList(
                    *[
                        _linha_da_nota(nota, _link_da_nota(nota.get("CHAVE"), arquivos, url_pdf_da_nota))
                        for nota in do_dia.iter_rows(named=True)
                    ]
                ),
                selector=alvo,
                where="beforeEnd",
            )

    @reactive.effect
    @reactive.event(input.dias_E)
    def _dias_abertos_das_entradas():
        try:
            _mostrar_os_dias_abertos("E", input.dias_E(), notas_das_entradas())
        except Exception as exc:
            logger.warning(f"Apuracao: as notas do dia nas entradas -- {exc}")

    @reactive.effect
    @reactive.event(input.dias_S)
    def _dias_abertos_das_saidas():
        try:
            _mostrar_os_dias_abertos("S", input.dias_S(), notas_das_saidas())
        except Exception as exc:
            logger.warning(f"Apuracao: as notas do dia nas saidas -- {exc}")

    # O balao abre com a linha escolhida e fecha sem ela; fechado pelo X dele (ou pelo Esc), a linha deixa de estar
    # escolhida, e o clique nela abre de novo.
    @reactive.effect
    def _balao_das_entradas():
        try:
            ui.update_popover("balao_E", show=bool(cfops_entradas()))
        except Exception as exc:
            logger.warning(f"Apuracao: balao das entradas -- {exc}")

    @reactive.effect
    def _balao_das_saidas():
        try:
            ui.update_popover("balao_S", show=bool(cfops_saidas()))
        except Exception as exc:
            logger.warning(f"Apuracao: balao das saidas -- {exc}")

    @reactive.effect
    @reactive.event(input.balao_E)
    async def _balao_das_entradas_fechado():
        try:
            with reactive.isolate():
                escolhida = bool(cfops_entradas())
            if not input.balao_E() and escolhida:
                await tabela_entradas.update_cell_selection(None)
        except Exception as exc:
            logger.warning(f"Apuracao: fechar o balao das entradas -- {exc}")

    @reactive.effect
    @reactive.event(input.balao_S)
    async def _balao_das_saidas_fechado():
        try:
            with reactive.isolate():
                escolhida = bool(cfops_saidas())
            if not input.balao_S() and escolhida:
                await tabela_saidas.update_cell_selection(None)
        except Exception as exc:
            logger.warning(f"Apuracao: fechar o balao das saidas -- {exc}")

    def _nome_da_planilha() -> str:
        return f"apuracao_{input.empresa() or 'empresa'}_{mes() or ''}.xlsx"

    @render.download(filename=_nome_da_planilha)
    def planilha():
        yield dados_apuracao.planilha(livros(), mes(), colunas=janela_exportar.colunas("planilha"))

    # Graficos: o ICMS mes a mes -----------------------------------------------

    @output(suspend_when_hidden=False)
    @render.ui
    def grafico():
        """O "ICMS creditado x debitado" do Power BI: uma barra de cada por mes."""
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
        """A "Evolucao das Bonificacoes" do Power BI: a recebida (entrada) e a dada (saida) de cada mes."""
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

    # PIS/COFINS --------------------------------------------------------------
    # A parte escondida atras da aba tambem recebe valor (a tela de carregamento espera todo output da pagina).

    @output(suspend_when_hidden=False)
    @render.data_frame
    def tabela_receita():
        linhas_na_tela = dados_apuracao.so_as_colunas_do_livro(
            dados_apuracao.na_tela_receita(ordem_receita.ordenar(receita_e_deducoes())),
            livro_da_subaba(),
            dados_apuracao.RECEITA_DO_LIVRO,
            dados_apuracao.COLUNAS_DA_RECEITA,
        )
        return largura_colunas.grade(
            linhas_na_tela, height="44vh", width="100%", summary=False, styles=_linha_do_total(linhas_na_tela)
        )

    @output(suspend_when_hidden=False)
    @render.ui
    def grafico_receita():
        """O "Receita Bruta vs Bonificacao" do Power BI."""
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
        """O "Evolucao do total de compras" do Power BI."""
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
            receita_e_deducoes(),
            mes(),
            colunas=janela_exportar.colunas("planilha_receita") or colunas_da_planilha_receita(),
        )

    # Despesas ----------------------------------------------------------------

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

    # O livro item a item (as paginas "Livro Fiscal" do Power BI) -------------------------------------------------
    # As saidas atras da aba recebem valor mesmo escondidas (a tela de carregamento espera todo output da pagina).

    @reactive.calc
    def meses_com_itens() -> set[str]:
        if versao_cache is not None:
            versao_cache()
        return dados_apuracao.meses_com_itens(input.empresa() or "")

    # Lido uma vez por empresa e mes (com os nomes do produto e do participante); os filtros trabalham sobre ele.
    @reactive.calc
    def itens_do_mes() -> pl.DataFrame:
        if versao_cache is not None:
            versao_cache()
        return dados_apuracao.com_os_nomes(dados_apuracao.itens_do_mes(input.empresa() or "", mes()))

    def _opcoes_do_filtro(id_filtro: str, opcoes: dict[str, str], no_servidor: bool = False) -> None:
        """As opcoes de um filtro de varios, mantendo os escolhidos que continuam nelas. `no_servidor`: a lista longa
        (os participantes do mes, milhares) fica no servidor, e o navegador pede so' o que a pessoa digita."""
        with reactive.isolate():
            escolhidos = [codigo for codigo in (input[id_filtro]() or []) if codigo in opcoes]
        ui.update_selectize(id_filtro, choices=opcoes, selected=escolhidos, server=no_servidor)

    @reactive.effect
    def _opcoes_cfop():
        """Os CFOPs dos itens do livro escolhido."""
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        try:
            _opcoes_do_filtro("cfops", dados_apuracao.opcoes_cfop_dos_itens(itens_do_mes(), livro_dos_itens()))
        except Exception as exc:
            logger.warning(f"Apuracao: opcoes de CFOP -- {exc}")

    # As opcoes dos filtros dos itens do mes, calculadas uma vez: os filtros e as etiquetas do "Filtrando por" usam.
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
        """Os produtos, os participantes, os CST e as aliquotas dos itens do mes."""
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        try:
            for id_filtro, opcoes in opcoes_dos_itens().items():
                _opcoes_do_filtro(id_filtro, opcoes, no_servidor=id_filtro == "participantes")
        except Exception as exc:
            logger.warning(f"Apuracao: opcoes dos filtros do livro -- {exc}")

    # O periodo de cada aba comeca no mes escolhido e volta a ele quando o mes muda; o que o F5 trouxe de volta (dentro
    # do mes, no livro) fica. Antes do primeiro mes, nada esta' marcado como do periodo.
    mes_dos_periodos = {"dias": None, "pagos": None}

    def _periodo_do_mes(id_periodo: str, dentro_do_mes: bool) -> None:
        primeiro, ultimo = dados_apuracao.primeiro_e_ultimo_dia(mes())
        if primeiro is None or mes_dos_periodos[id_periodo] == mes():
            return  # o mes nao mudou (a tela so' voltou a aparecer): fica o periodo escolhido
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
        """Os dias escolhidos, so' dentro do mes (antes do periodo seguir o mes, o mes inteiro)."""
        primeiro, ultimo = dados_apuracao.primeiro_e_ultimo_dia(mes())
        de, ate = input.dias() or (None, None)
        if primeiro is None or not de or not ate or not (primeiro <= de <= ate <= ultimo):
            return primeiro, ultimo
        return de, ate

    opcoes_mostradas: dict[str, list] = {}

    @reactive.effect
    def _opcoes_presentes_nos_filtros():
        """Livro e Nota cancelada so' com o que os itens do mes e dos dias tem (o usuario, 19/11/2026). "Sem as
        canceladas" e "So' as canceladas" saem da coluna CANCELADA (0 e 1), como no filtro."""
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
            livro_dos_itens(),
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

    # A lista pagina como as outras do Fiscal (core/tabela_paginada.py): o navegador recebe so' a pagina.
    paginador_itens = TabelaPaginada("tabela_itens", input, session)

    @reactive.effect
    def _itens_na_primeira_pagina():
        """Filtro novo (ou mes novo) volta para a pagina 1."""
        try:
            itens_filtrados()
            paginador_itens.reiniciar()
        except SilentException:
            return
        except Exception as exc:
            logger.warning(f"Apuracao: voltar a' primeira pagina do livro -- {exc}")

    def _sem_itens_do_mes() -> str | None:
        """O mes que ainda nao veio do Control item a item: onde ele vem (o texto vai dentro da lista vazia)."""
        empresa = input.empresa() or ""
        if not mes() or not empresa or mes() in meses_com_itens():
            return None
        if dados_apuracao.revenda_da_empresa(empresa) is None:
            return "Esta empresa não tem livro fiscal no Fiscal."
        return (
            f"O livro item a item de {dados_apuracao.rotulo_mes(mes())} ainda não foi lido do {erp_da_tela()}: o "
            "Atualizar, no alto da tela, lê o mês corrente e o anterior; os outros vêm na leitura da madrugada."
        )

    @output(suspend_when_hidden=False)
    @render.data_frame
    def tabela_itens():
        pagina = paginador_itens.fatiar(itens_filtrados())
        if pagina.is_empty():
            mensagem = _sem_itens_do_mes() or "Nenhum item no livro do mês com os filtros escolhidos."
            return render.DataGrid(pl.DataFrame({mensagem: []}), height="10vh")
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

    # A escolha das Colunas fica guardada por pessoa (core/colunas_do_usuario.py).
    colunas_do_usuario.ColunasDaPessoa(input, VALOR_NAVSET, usuario_atual, dados_apuracao.PADRAO_DOS_ITENS)

    def _nome_da_planilha_itens() -> str:
        return f"livro_itens_{input.empresa() or 'empresa'}_{mes() or ''}.xlsx"

    @render.download(filename=_nome_da_planilha_itens)
    def planilha_itens():
        yield dados_apuracao.planilha_itens(itens_filtrados(), mes(), colunas=janela_exportar.colunas("planilha_itens"))

    # PIS/COFINS: a apuracao do livro item a item ------------------------------------------------------------------

    ordem_pis_cofins = ordem_tabela.OrdemPorValor(
        "tabela_pis_cofins", input, session, colunas=dados_apuracao.ORDEM_DA_APURACAO_PIS_COFINS
    )

    @output(suspend_when_hidden=False)
    @render.data_frame
    def tabela_pis_cofins():
        linhas_na_tela = dados_apuracao.so_as_colunas_do_livro(
            dados_apuracao.na_tela_apuracao_pis_cofins(ordem_pis_cofins.ordenar(apuracao_pis_cofins())),
            livro_da_subaba(),
            dados_apuracao.APURACAO_PIS_COFINS_DO_LIVRO,
            dados_apuracao.COLUNAS_DA_APURACAO_PIS_COFINS,
        )
        saldos = tuple(nome for nome in ("PIS do mês", "COFINS do mês") if nome in linhas_na_tela.columns)
        credor = formato.estilos(linhas_na_tela, {nome: _cor_do_saldo for nome in saldos}, so_texto=saldos)
        return largura_colunas.grade(
            linhas_na_tela, height="44vh", width="100%", summary=False, styles=_linha_do_total(linhas_na_tela) + credor
        )

    @output(suspend_when_hidden=False)
    @render.ui
    def grafico_pis_cofins():
        """O "Evolucao de PIS a Recolher vs COFINS a Recolher" do Power BI, com o saldo do mes (sem o credito do mes
        anterior): acima de zero, a recolher; abaixo, credor."""
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
        """O "Evolucao do CMV" do Power BI."""
        por_mes = apuracao_pis_cofins()
        if por_mes.is_empty():
            return None
        return _grafico_de_linhas(por_mes["mes"].to_list(), [("CMV", por_mes["cmv"].to_list(), APURACAO_ESCURO)])

    def _nome_da_planilha_pis_cofins() -> str:
        return f"pis_cofins_{input.empresa() or 'empresa'}_ate_{mes() or ''}.xlsx"

    @render.download(filename=_nome_da_planilha_pis_cofins)
    def planilha_pis_cofins():
        yield dados_apuracao.planilha_apuracao_pis_cofins(
            apuracao_pis_cofins(),
            mes(),
            colunas=janela_exportar.colunas("planilha_pis_cofins") or colunas_da_planilha_pis_cofins(),
        )

    # Despesas: os filtros e os titulos do periodo -------------------------------------------------------------------

    @reactive.effect
    def _opcoes_das_despesas():
        """As despesas e os fornecedores dos titulos pagos da revenda."""
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        try:
            _opcoes_do_filtro("despesas", dados_apuracao.opcoes_despesa(titulos_pagos(), input.empresa() or ""))
            _opcoes_do_filtro("fornecedores", dados_apuracao.opcoes_fornecedor(titulos_pagos()), no_servidor=True)
        except Exception as exc:
            logger.warning(f"Apuracao: opcoes das despesas -- {exc}")

    @reactive.calc
    def periodo_dos_titulos() -> tuple:
        """Os dias de pagamento escolhidos; sem eles (antes de o periodo seguir o mes), o mes inteiro."""
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

    # O "Filtrando por" (as etiquetas que tiram cada filtro) e o Limpar das abas Livro fiscal e Despesas ---------------

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
        """O nome de cada opcao do filtro (o codigo -> o que a lista mostra)."""
        if id_filtro in ("produtos", "participantes", "csts", "aliquotas"):
            return opcoes_dos_itens()[id_filtro]
        if id_filtro == "despesas":
            return dados_apuracao.opcoes_despesa(titulos_pagos(), input.empresa() or "")
        return {"livro": dados_apuracao.LIVROS_DOS_ITENS, "situacao": dados_apuracao.SITUACOES_DOS_ITENS}.get(
            id_filtro, {}
        )

    def _texto_do_escolhido(id_filtro: str, escolhido) -> str:
        """O que a etiqueta mostra: os nomes escolhidos (os tres primeiros e quantos mais) ou o texto."""
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
            if id_filtro == "livro" and livro_da_subaba():
                continue  # nas Entradas e nas Saidas o livro e' o da subaba, sem o filtro
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
        """Volta os filtros da aba aberta ao comeco: nada escolhido e o periodo do mes inteiro."""
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

    # A janela Exportar (core/exportar.py): as colunas e a ordem delas antes de baixar.
    def colunas_da_planilha() -> list[str]:
        return dados_apuracao.tabela_planilha(livros(), mes()).columns if mes() else []

    # A planilha do PIS/COFINS com as colunas do livro da subaba, como a tabela.
    def colunas_da_planilha_receita() -> list[str]:
        if not mes():
            return []
        return dados_apuracao.so_as_colunas_do_livro(
            dados_apuracao.tabela_planilha_receita(receita_e_deducoes()),
            livro_da_subaba(),
            dados_apuracao.RECEITA_DO_LIVRO,
            dados_apuracao.COLUNAS_DA_RECEITA,
        ).columns

    def colunas_da_planilha_despesas() -> list[str]:
        return dados_apuracao.tabela_planilha_despesas(despesas_na_tabela()).columns

    def colunas_da_planilha_itens() -> list[str]:
        return list(dados_apuracao.COLUNAS_DOS_ITENS)

    def colunas_da_planilha_pis_cofins() -> list[str]:
        if not mes():
            return []
        return dados_apuracao.so_as_colunas_do_livro(
            dados_apuracao.tabela_planilha_apuracao_pis_cofins(apuracao_pis_cofins()),
            livro_da_subaba(),
            dados_apuracao.APURACAO_PIS_COFINS_DO_LIVRO,
            dados_apuracao.COLUNAS_DA_APURACAO_PIS_COFINS,
        ).columns

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


def pag_apuracao_ui(revenda: str | None = None, visao: str | None = None):
    return apuracao_ui("apuracao", revenda, visao)


def pag_apuracao_server(revenda_atual, usuario_atual=None, versao_cache=None):
    return apuracao_server(
        "apuracao", revenda_atual=revenda_atual, usuario_atual=usuario_atual, versao_cache=versao_cache
    )
