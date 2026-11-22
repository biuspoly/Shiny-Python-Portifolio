import asyncio
import hashlib
import io
import json
import os
import re
import shutil
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, quote

import polars as pl
import qrcode
import qrcode.image.svg
from faicons import icon_svg
from loguru import logger
from shiny import module, reactive, render, req, ui

from core import (
    arquivo_revenda,
    assinatura,
    fabricas,
    gravacao,
    juntar_pdf,
    manual_arquivo,
    pastas_da_sessao,
    planilha_fabrica,
    rede_documentos,
    trava_caixa,
)
from core import extrato_banco_pdf as fontes
from core import sincronia_financeiro as sincronia
from core.atualizacao import obter_atualizacao
from core.auth import identificar_usuario
from core.aviso import modal_aviso
from core.cartoes_banco import (
    cartao_banco,
    formatar_reais,
    grade_cartoes,
    linha_saldo,
)
from core.compat import para_pandas  # noqa: E402
from core.config import (
    CHAVE_EDITAR_RESPONSAVEIS,
    CHAVE_VER_GASTO_VEICULO,
    CHAVE_VER_PRE_AUDITORIA,
    adicionar_responsavel,
    chave_revenda,
    cnpjs_dos_carimbos,
    desconto_ate_da_nota,
    desconto_da_revenda,
    descontos_por_fornecedor,
    exige_auditoria_para_pagar,
    manual_com_vencimento_barrado,
    no_acesso_total,
    pode,
    quem_libera,
    remover_responsavel,
    secoes_de_direitos,
    so_contas_a_pagar_no_diario,
    travado_por_leitura,
)
from core.config_arquivo import carregar_json
from core.id_titulo import base_do, eh_parte
from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.revendas import nome_oficial
from core.secao import (
    ICONE_CONTAS_PAGAR,
    ICONE_DIARIO,
    ICONE_MARÉ,
    com_placeholder,
    titulo_secao,
)
from core.tabela_paginada import TabelaPaginada
from core.visibilidade import pagina_visivel
from pages.Operacao.Dados import dados_farol_999
from pages.Operacao.pag_envio_extratos import status_envio_do_dia

from .Dados import dados_anexos as an
from .Dados import dados_composicao as dc
from .Dados import dados_contas_pagar as cp
from .Dados import dados_ppf as d
from .Dados import pre_auditoria, pre_auditoria_999

FILTRO_COM_BUSCA = {
    "placeholder": "Todos",
    "plugins": ["clear_button", "restore_on_backspace"],
    "dropdownParent": "body",
    "dropdownClass": "selectize-dropdown ppf-filtro-dropdown",
}

VALOR_NAVSET = "ppf"
PASTA_CACHE = Path(__file__).parents[2] / "data" / "bd_financeiro"

_ALTURA_COMPOSICAO = None

LINHAS_COM_TETO = 50

LINHAS_INTERATIVAS = 100


PRIMEIRA_POSICAO_EXTRA = 10_000

MOTIVO_AGUARDA_AUDITORIA = "Aguardando auditoria: este título precisa ser auditado antes de você marcar o pagamento."


_EXCLAMACAO_DENTRO_DO_CIRCULO = (
    '<path transform="translate(217.6 102.4) scale(0.6)" d="M96 64c0-17.7-14.3-32-32-32S32 46.3 32 64V320c0 17.7 '
    '14.3 32 32 32s32-14.3 32-32V64zM64 480c22.1 0 40-17.9 40-40s-17.9-40-40-40s-40 17.9-40 40s17.9 40 40 40z"></path>'
)
ICONE_PRE_AUDITORIA_ATENCAO = ui.HTML(
    str(icon_svg("circle", style="regular", a11y="deco")).replace("</svg>", _EXCLAMACAO_DENTRO_DO_CIRCULO + "</svg>")
)
TEXTOS_DO_ESTADO_DA_PRE_AUDITORIA = {"erro": "com erro", "atencao": "pede atenção", "ok": "nada apontado"}
APONTAMENTOS_NO_RESUMO = 3


def _contagem(quantidade: int, singular: str, plural: str) -> str:
    return f"{quantidade} {singular if quantidade == 1 else plural}"


def _estado_da_pre_auditoria(pre_auditoria_do_titulo: d.PreAuditoriaDoTitulo) -> str:
    gravidades = {apontamento["gravidade"] for apontamento in pre_auditoria_do_titulo.apontamentos}
    if "erro" in gravidades:
        return "erro"
    if gravidades:
        return "atencao"
    return "ok"


def _icone_da_pre_auditoria(estado: str):
    if estado == "atencao":
        return ICONE_PRE_AUDITORIA_ATENCAO
    return icon_svg("circle-xmark" if estado == "erro" else "circle-check", style="regular", a11y="deco")


def _quando_conferido(pre_auditoria_do_titulo: d.PreAuditoriaDoTitulo) -> str:
    gerado_em = pre_auditoria_do_titulo.gerado_em
    return gerado_em.strftime("%d/%m/%Y %H:%M") if gerado_em else "-"


def _resumo_da_pre_auditoria(pre_auditoria_do_titulo: d.PreAuditoriaDoTitulo) -> ui.Tag:
    apontamentos = pre_auditoria_do_titulo.apontamentos
    if not apontamentos:
        o_que_foi_conferido = getattr(pre_auditoria_do_titulo, "conferido", "")
        return ui.div(
            ui.tags.strong("Pré-auditoria: nada apontado"),
            ui.div(f"Conferido em {_quando_conferido(pre_auditoria_do_titulo)}"),
            ui.div(f"Conferido: {o_que_foi_conferido}.") if o_que_foi_conferido else None,
            class_="ppf-pa-dica-texto",
        )
    erros = sum(1 for apontamento in apontamentos if apontamento["gravidade"] == "erro")
    atencoes = len(apontamentos) - erros
    contagens = [
        texto
        for texto in (
            _contagem(erros, "erro", "erros") if erros else "",
            _contagem(atencoes, "atenção", "atenções") if atencoes else "",
        )
        if texto
    ]
    primeiros = [ui.tags.li(apontamento["descricao"]) for apontamento in apontamentos[:APONTAMENTOS_NO_RESUMO]]
    if len(apontamentos) > APONTAMENTOS_NO_RESUMO:
        primeiros.append(ui.tags.li(f"e mais {len(apontamentos) - APONTAMENTOS_NO_RESUMO}"))
    return ui.div(
        ui.tags.strong(f"Pré-auditoria: {' e '.join(contagens)}"),
        ui.tags.ul(*primeiros),
        ui.div("Clique para ver os detalhes.", class_="ppf-pa-dica-clique"),
        class_="ppf-pa-dica-texto",
    )


def _linha_do_apontamento(apontamento: dict) -> ui.Tag:
    classe_da_gravidade = "ppf-pa-linha-erro" if apontamento["gravidade"] == "erro" else "ppf-pa-linha-atencao"
    return ui.tags.tr(
        ui.tags.td(apontamento["grupo"], class_="ppf-pa-grupo"),
        ui.tags.td(
            ui.div(apontamento["descricao"], class_="ppf-pa-descricao"),
            ui.div(apontamento["detalhe"], class_="ppf-pa-detalhe") if apontamento["detalhe"] else None,
        ),
        class_=classe_da_gravidade,
    )


def _corpo_da_pre_auditoria(pre_auditoria_do_titulo: d.PreAuditoriaDoTitulo) -> ui.TagList:
    apontamentos = pre_auditoria_do_titulo.apontamentos
    erros = sum(1 for apontamento in apontamentos if apontamento["gravidade"] == "erro")
    resumo = ui.div(
        ui.div(ui.span("Erros"), ui.tags.strong(str(erros), class_="ppf-pa-total-erro" if erros else None)),
        ui.div(
            ui.span("Atenções"),
            ui.tags.strong(
                str(len(apontamentos) - erros), class_="ppf-pa-total-atencao" if len(apontamentos) > erros else None
            ),
        ),
        ui.div(
            ui.span("Situação"),
            ui.tags.strong(TEXTOS_DO_ESTADO_DA_PRE_AUDITORIA[_estado_da_pre_auditoria(pre_auditoria_do_titulo)]),
        ),
        ui.div(ui.span("Conferido em"), ui.tags.strong(_quando_conferido(pre_auditoria_do_titulo))),
        class_="flx-balao-resumo",
    )
    o_que_foi_conferido = getattr(pre_auditoria_do_titulo, "conferido", "")
    if o_que_foi_conferido:
        resumo = ui.TagList(resumo, ui.div(f"Conferido: {o_que_foi_conferido}.", class_="ppf-pa-rodape"))
    if not apontamentos:
        lista = ui.div("Nenhum apontamento nesta conferência.", class_="flx-balao-vazio")
    else:
        lista = ui.div(
            ui.tags.table(
                ui.tags.thead(ui.tags.tr(ui.tags.th("Grupo"), ui.tags.th("Apontamento"))),
                ui.tags.tbody(*[_linha_do_apontamento(apontamento) for apontamento in apontamentos]),
                class_="flx-balao-tabela ppf-pa-tabela",
            ),
            class_="flx-balao-rolagem",
        )
    return ui.TagList(
        resumo,
        ui.div("Apontamentos", class_="flx-balao-secao"),
        lista,
        ui.div("A pré-auditoria só aponta: quem decide é a auditoria.", class_="ppf-pa-rodape"),
    )


def _dias_a_frente_da_pre_auditoria(revenda: str | None, ctx: dict) -> int:
    ja_lidos = ctx["dias_a_frente_por_revenda"]
    if revenda not in ja_lidos:
        ja_lidos[revenda] = int(pre_auditoria.configuracao_da_revenda(revenda or "").get("dias_a_frente") or 0)
    return ja_lidos[revenda]


def _motivo_sem_pre_auditoria(
    pagou: bool, entrada_manual: bool, fora_da_carga: bool, vencimento, ultimo_vencimento_da_janela: date
) -> str:
    if pagou:
        return "Título já pago."
    if entrada_manual:
        return "Lançamento manual: a pré-auditoria confere só os títulos do ERP."
    if fora_da_carga:
        return "O título saiu da última leitura do ERP (baixado ou excluído lá): a pré-auditoria não o confere."
    dia_do_vencimento = vencimento.date() if isinstance(vencimento, datetime) else vencimento
    if isinstance(dia_do_vencimento, date) and dia_do_vencimento > ultimo_vencimento_da_janela:
        return (
            f"Vence depois de {ultimo_vencimento_da_janela:%d/%m/%Y}: a pré-auditoria confere os vencidos e os que "
            "vencem nos próximos dias."
        )
    return "Ainda não conferido: entra no próximo Atualizar ou na conferência da madrugada."


def _pre_auditoria_nao_conferida(motivo: str) -> ui.Tag:
    icone_com_motivo = ui.tooltip(
        ui.span(icon_svg("circle-dot", style="regular", a11y="deco"), class_="ppf-pa-icone"),
        ui.div(ui.tags.strong("Pré-auditoria: não conferido"), ui.div(motivo), class_="ppf-pa-dica-texto"),
        placement="top",
        options={"customClass": "ppf-pa-dica", "trigger": "hover"},
    )
    return ui.tags.button(icone_com_motivo, type="button", tabindex="-1", class_="ppf-pa ppf-pa-nao-conferido")


def _pre_auditoria_da_linha(
    pre_auditoria_do_titulo: d.PreAuditoriaDoTitulo,
    rotulo_do_titulo: str,
    id_do_balao: str | None = None,
    entrada_de_fechar: str | None = None,
) -> ui.Tag:
    estado = _estado_da_pre_auditoria(pre_auditoria_do_titulo)
    icone_com_resumo = ui.tooltip(
        ui.span(_icone_da_pre_auditoria(estado), class_="ppf-pa-icone"),
        _resumo_da_pre_auditoria(pre_auditoria_do_titulo),
        placement="top",
        options={"customClass": "ppf-pa-dica", "trigger": "hover"},
    )
    gatilho = ui.tags.button(
        icone_com_resumo, type="button", tabindex="-1", class_=f"ppf-pa ppf-pa-{estado}", data_fechar=entrada_de_fechar
    )
    return ui.popover(
        gatilho,
        _corpo_da_pre_auditoria(pre_auditoria_do_titulo),
        title=f"Pré-auditoria | {rotulo_do_titulo}",
        id=id_do_balao,
        placement="auto",
        options={"customClass": "flx-balao ppf-pa-balao"},
    )


def _pre_auditoria_do_999(
    pre_auditorias_999: dict,
    revenda: str,
    dia,
    descricao: str,
    documento: str,
    arquivos_de_agora: list[str],
    rotulo: str,
    id_do_balao: str,
    entrada_de_fechar: str,
):
    if not arquivos_de_agora or dia is None:
        return None
    da_linha = pre_auditorias_999.get(manual_arquivo.chave_999(revenda, dia, descricao, documento))
    if not pre_auditoria_999.ainda_vale(da_linha, arquivos_de_agora):
        return _pre_auditoria_nao_conferida(
            "O anexo chegou depois da última conferência: ela roda logo depois do envio, no Atualizar e de madrugada."
        )
    return _pre_auditoria_da_linha(da_linha, rotulo, id_do_balao, entrada_de_fechar)


def _caminhao_do_gasto_com_veiculo(gasto: dict) -> ui.Tag | None:
    endereco = cp.link_das_despesas(gasto)
    if not endereco:
        return None
    link = ui.tags.a(
        ui.tags.img(src="img/ppf/caminhao.svg", class_="ppf-cel-anexo ppf-cel-veiculo", alt="Gasto com veículo"),
        href=endereco,
        target="_blank",
        rel="noopener",
        class_="ppf-olho-link ppf-veiculo-link",
    )
    return ui.tooltip(link, cp.texto_do_gasto_com_veiculo(gasto), placement="top", options={"trigger": "hover"})


LINHAS_MANUAIS = 60

COMPOSICAO_BASE = "#0b4b6f"
COMPOSICAO_SAIDA = "#B22222"

_ESTILO_NATUREZA = {
    "saida": {"color": COMPOSICAO_SAIDA, "font-weight": "bold"},
    "entrada": {"color": COMPOSICAO_BASE},
    "limite": {"color": COMPOSICAO_BASE},
    "parcial": {"color": COMPOSICAO_BASE},
    "total": {"color": COMPOSICAO_BASE},
}

SAIDAS_EM_DESTAQUE = {
    "devolucoes_emprestimos",
    "transf_outros_bancos_sai",
    "transf_matriz_filial_sai",
    "romaneio_pendente",
    "credito_mar_utilizado",
}

SALDOS_EM_NEGRITO = {"novo_saldo_liberado", "novo_saldo_com_especial", "saldo_final_liberado", "saldo_uso_especial"}
SALDOS_FINAIS = {"saldo_final_liberado", "saldo_uso_especial"}

_FUNDO_CREDITO_FABRICA = "#e8f5e9"


def _valor_mostrado(fatia: pl.DataFrame, i: int):
    cheio = fatia["_valor_cheio"][i] if "_valor_cheio" in fatia.columns else None
    return cheio if cheio is not None else fatia["_valor"][i]


def _legenda_da_parte(divisao: tuple | None) -> ui.Tag | None:
    if not divisao or not divisao[0]:
        return None
    quem, quando = divisao
    nome = cp.nome_legivel(quem)
    texto = f"Parte do rateio · dividido por {nome}"
    return ui.tooltip(
        ui.span(texto, class_="ppf-parte-rateio"),
        f"Título dividido por {nome}" + (f" em {quando:%d/%m/%Y às %H:%M}" if quando else ""),
        placement="top",
    )


_DESTAQUE = {"font-weight": "bold", "font-size": "1.05em"}
_DESTAQUE_SAIDA = {"color": "#B22222", "font-weight": "bold", "font-size": "1.05em"}

_FUNDO_ZEBRA = "rgba(0, 0, 0, 0.05)"

ITENS_ZERO_NO_CAIXA = {"saldo_final_liberado", "saldo_uso_especial"}

_LARGURA_ITEM_COMPOSICAO = 300
_LARGURA_BANCO_COMPOSICAO = 150

COLUNAS_CONTAS_PAGAR = [
    "Vencimento",
    "Fornecedor",
    "Tipo",
    "C. Custo",
    "Documento",
    "Tipo Doc",
    "Valor Original",
    "Valor Pago",
    "Juros",
    "Banco",
    "Assinar",
    "Auditoria",
    "Pagar",
    "Gestão",
]
_LARGURA_PAGAR = {
    "Vencimento": 110,
    "Fornecedor": 260,
    "Tipo": 150,
    "C. Custo": 90,
    "Documento": 140,
    "Tipo Doc": 130,
    "Valor Original": 130,
    "Valor Pago": 120,
    "Juros": 100,
    "Banco": 110,
    "Auditoria": 110,
    "Pagar": 90,
    "Gestão": 100,
}

COLUNAS_999 = ["Data", "Descrição", "Informativo ERP", "Valor", "Anexos"]


LINHAS_999_COM_ANEXO = 60
ARQUIVOS_999 = 20

CAMPOS_BATIDA_999 = (
    ("dinheiro_moeda", "DINHEIRO MOEDA"),
    ("oct", "OCT"),
    ("octs_nao_compensadas", "OCTs NAO COMPENSADAS"),
    ("vale", "VALE"),
    ("pix_provisorios", "PIX PROVISORIOS"),
    ("fazenda", "FAZENDA"),
)

PRIORIDADE_999 = [rotulo for _coluna, rotulo in CAMPOS_BATIDA_999]


def batida_do_dia(dia, *fontes: pl.DataFrame) -> dict | None:
    if dia is None:
        return None
    for fonte in fontes:
        if fonte is None or fonte.is_empty() or "data" not in fonte.columns:
            continue
        do_dia = fonte.filter(pl.col("data").cast(pl.Date, strict=False) == dia)
        if do_dia.height:
            linha = do_dia.tail(1).to_dicts()[0]
            if any(linha.get(c) not in (None, 0, 0.0) for c, _rotulo in CAMPOS_BATIDA_999):
                return linha
    return None


CAMPOS_MANUAL = [
    ("data_vencimento_manual", "Vencimento", "date", ""),
    ("num_doc_manual", "Documento", "text", "Nº doc"),
    ("tipo_doc_manual", "Tipo Doc", "text", "NFS, DAE..."),
    ("cnpj_manual", "CNPJ", "text", "00.000.000/0000-00"),
    ("razao_social_manual", "Fornecedor", "text", "Nome do fornecedor"),
    ("descricao_despesa_manual", "Tipo Fornecedor", "text", "Tipo Fornecedor"),
    ("valor_original_manual", "Valor", "text", "R$ 0,00"),
]


def _botao_submit(botao):
    botao.attrs["type"] = "submit"
    return botao


PERIODOS = {
    "hoje": "Hoje",
    "vencidos": "Vencidos",
    "a_vencer": "A Vencer",
}

FILTROS_TEXTO = [
    ("tipo", "Tipo", "descricao_despesa"),
    ("nome", "Nome", "FORNECEDOR"),
    ("documento", "Documento", "PGMOVMOV_NDUPL"),
    ("ccusto", "C. Custo", "CENTRO_CUSTO"),
]


def _reais(valor: float | None) -> str:
    return formatar_reais(valor)


def _desconto_ate(revenda: str | None, limites: dict, cnpj=None, valor=None) -> float:
    if revenda not in limites:
        limites[revenda] = (desconto_da_revenda(revenda)[0], descontos_por_fornecedor(revenda))
    desconto_ate, percentuais = limites[revenda]
    return float(desconto_ate_da_nota(desconto_ate, percentuais, cnpj, valor))


COLUNA_ITEM = "COMPOSIÇÃO FINANCEIRA"

_LINHAS_CARTAO = [
    ("Saldo", "saldo_final_liberado", False),
    ("Despesas", "total_despesas_sugeridas", True),
    ("Saldo com cheque especial", "saldo_uso_especial", False),
]


PERFIL_DO_ARQUIVO = {
    "bancos_extratos": "arquivo_banco",
    "batida_diaria": "arquivo_batida",
    "fabricas_extratos": "arquivo_fabrica",
    "fabricas_planilhas": "arquivo_fabrica",
}

TIPO_DE_ENVIO = {
    "bancos_extratos": "bancos",
    "batida_diaria": "batida_diaria",
    "fabricas_extratos": "fabrica",
    "fabricas_planilhas": "fabrica",
    "modelo_iv": "modelo_iv",
}


FUNDO_VENCE_HOJE = "#d4edda"
FUNDO_VENCIDO = "#fff3cd"
FUNDO_ENVIADA = "#f6f6f6"


def _celula_composicao(valor: float | None, *, mostra_zero: bool) -> str:
    if valor is None:
        return ""
    if valor == 0 and not mostra_zero:
        return ""
    return _reais(valor)


def _coluna_do_caixa(colunas: list[str], revenda: str | None = None) -> str | None:
    for coluna in colunas:
        if dc.chave_do_rotulo(coluna, revenda) == dc.CHAVE_CAIXA:
            return coluna
    return None


COR_FABRICA_USADO = "#B22222"
COR_FABRICA_SOBRA = "#2A6D69"


@module.ui
def diario_cabecalho(revenda: str | None = None):
    return ui.div(
        *[
            ui.div(
                ui.input_action_button(
                    f"abrir_{u.campo}",
                    u.rotulo,
                    icon=ui.tags.img(src=u.icone, class_="ppf-arquivo-icone", alt=""),
                    class_="ppf-arquivo-botao",
                ),
                class_="ppf-arquivo",
                title=u.dica,
            )
            for u in an.uploads_da_revenda(revenda)
        ],
        ui.div(
            ui.input_select("historico", "Histórico:", {"": "Atual"}),
            class_="ppf-filtro ppf-filtro-historico",
        ),
        class_="ppf-barra-topo",
    )


SECAO_DE_CIMA = "ppf-secao-de-cima"
ESTILO_SO_CONTAS_A_PAGAR = f".{SECAO_DE_CIMA} {{ display: none !important; }}"


@module.ui
def diario_ui(revenda: str | None = None):
    return ui.div(
        ui.output_ui("so_contas_a_pagar"),
        ui.card(
            ui.card_header(
                titulo_secao(
                    "Diário Financeiro",
                    icone=ICONE_DIARIO,
                    extras=[
                        ui.div(
                            ui.output_ui("alerta_extratos", inline=True),
                            ui.div(
                                ui.output_ui("verif_aguardando", inline=True),
                                ui.span(class_="ppf-verif-linha"),
                                ui.input_action_button(
                                    "step_financeiro",
                                    "Financeiro",
                                    class_="ppf-verif-etapa",
                                    disabled=True,
                                ),
                                ui.span(class_="ppf-verif-linha"),
                                ui.input_action_button(
                                    "step_diretoria",
                                    "Diretoria",
                                    class_="ppf-verif-etapa",
                                    disabled=True,
                                ),
                                class_="ppf-verificacao",
                            ),
                            class_="ppf-secao-direita ms-auto",
                        ),
                    ],
                )
            ),
            ui.output_ui("cards_bancos"),
            ui.div(
                ui.output_ui("tabela_composicao"),
                ui.input_action_button(
                    "toggle_999",
                    ui.output_ui("icone_999", inline=True),
                    class_="ppf-matriz-olho",
                    title="Ocultar / exibir a tabela do Banco 999",
                ),
                class_="ppf-matriz-com-olho",
            ),
            ui.div(
                ui.div(
                    ui.div(
                        ui.span("Σ Saldos Selecionados", class_="ppf-999-soma-titulo"),
                        ui.input_action_button(
                            "limpar_selecao",
                            None,
                            icon=icon_svg("eraser", a11y="deco"),
                            class_="btn btn-sm btn-link p-0",
                            title="Limpar seleção",
                        ),
                        class_="ppf-999-soma-cabecalho",
                    ),
                    ui.output_ui("card_soma"),
                    class_="ppf-999-soma",
                ),
                ui.div(
                    ui.div(
                        titulo_secao("Pagamentos Banco 999", emoji="\U0001f4b0"),
                        class_="ppf-999-cabecalho",
                    ),
                    ui.output_ui("corpo_tabela_999"),
                    class_="ppf-999-tabela",
                ),
                class_="ppf-999",
            ),
            ui.output_ui("bloco_vales"),
            id="secao_diario",
            class_=SECAO_DE_CIMA,
        ),
        ui.card(
            ui.card_header(titulo_secao("Entrada Manual de Pagamentos", emoji="\U0001f4b3")),
            ui.div(
                ui.output_ui("aviso_edicao_manual"),
                ui.tags.form(
                    ui.tags.table(
                        ui.tags.thead(
                            ui.tags.tr(
                                *[ui.tags.th(rotulo) for _c, rotulo, _t, _d in CAMPOS_MANUAL],
                                ui.tags.th("Ações"),
                            )
                        ),
                        ui.tags.tbody(
                            ui.tags.tr(
                                *[
                                    ui.tags.td(
                                        com_placeholder(
                                            ui.input_date(
                                                campo,
                                                None,
                                                value="",
                                                format="dd/mm/yyyy",
                                                language="pt-BR",
                                                weekstart=0,
                                            ),
                                            "dd/mm/aaaa",
                                        )
                                        if tipo == "date"
                                        else ui.input_text(campo, None, placeholder=dica),
                                        class_=f"ppf-manual-{campo}",
                                    )
                                    for campo, _rotulo, tipo, dica in CAMPOS_MANUAL
                                ],
                                ui.tags.td(
                                    ui.div(
                                        _botao_submit(
                                            ui.input_action_button(
                                                "gravar_manual",
                                                None,
                                                icon=icon_svg("paper-plane", a11y="deco"),
                                                class_="ppf-btn-enviar-tabela",
                                                title="Enviar",
                                            )
                                        ),
                                        ui.input_action_button(
                                            "limpar_manual",
                                            None,
                                            icon=icon_svg("eraser", a11y="deco"),
                                            class_="ppf-btn-limpar-tabela",
                                            title="Limpar",
                                        ),
                                        class_="ppf-manual-acoes",
                                    ),
                                ),
                            )
                        ),
                        class_="ppf-tabela-entrada-manual",
                    ),
                    method="dialog",
                ),
                class_="ppf-entrada-manual",
            ),
            ui.output_ui("tabela_manuais"),
            class_=f"ppf-card-leve {SECAO_DE_CIMA}",
        ),
        ui.card(
            ui.card_header(
                titulo_secao(
                    "Contas a Pagar",
                    icone=ICONE_CONTAS_PAGAR,
                    extras=[
                        ui.output_ui(
                            "alerta_pagar",
                            inline=True,
                            class_="ppf-alertas-pagar ms-auto",
                        ),
                        ui.div(
                            ui.input_switch("entradas_hoje", "Entradas hoje"),
                            class_="ppf-entradas-hoje",
                            title="Mostrar só os títulos que entraram hoje",
                        ),
                    ],
                )
            ),
            ui.div(
                ui.output_ui("cartoes_total_pagar"),
                ui.div(
                    ui.div(
                        ui.input_radio_buttons(
                            "periodo",
                            None,
                            PERIODOS,
                            selected="",
                            inline=True,
                        ),
                        class_="ppf-filtro ppf-filtro-periodo",
                    ),
                    ui.div(
                        com_placeholder(
                            ui.input_date_range(
                                "intervalo",
                                None,
                                start="",
                                end="",
                                format="dd/mm/yyyy",
                                separator=" até ",
                                language="pt-BR",
                                weekstart=0,
                            ),
                            "dd/mm/aaaa",
                        ),
                        class_="ppf-filtro ppf-filtro-datas",
                    ),
                    class_="ppf-grupo-filtros",
                ),
                ui.div(
                    *[
                        ui.div(
                            ui.input_selectize(id_filtro, f"{rotulo}:", {"": "Todos"}, options=FILTRO_COM_BUSCA),
                            class_=f"ppf-filtro ppf-filtro-inline ppf-filtro-{id_filtro}",
                        )
                        for id_filtro, rotulo, _coluna in FILTROS_TEXTO
                    ],
                    class_="ppf-grupo-filtros ppf-grupo-selects",
                ),
                ui.div(
                    ui.input_action_button(
                        "limpar",
                        "Limpar",
                        class_="ppf-btn-limpar",
                        title="Limpar filtros",
                    ),
                    ui.output_ui("botao_fabrica", class_="ppf-filtro-fabrica"),
                    class_="ppf-grupo-limpar",
                ),
                ui.div(
                    ui.div(
                        ui.input_switch("analise", "Análise"),
                        class_="ppf-acao ppf-acao-switch",
                    ),
                    ui.div(
                        ui.input_task_button(
                            "enviar",
                            icon_svg("paper-plane", a11y="deco"),
                            label_busy=None,
                            type="default",
                            class_="ppf-btn-discreto",
                            title="Enviar formulário",
                        ),
                        ui.div("Enviar", class_="ppf-acao-rotulo"),
                        class_="ppf-acao ppf-acao-enviar",
                    ),
                    ui.div(
                        ui.input_action_button(
                            "snapshot",
                            None,
                            icon=icon_svg("clock-rotate-left", a11y="deco"),
                            class_="ppf-btn-discreto",
                            title="Atualizar últimos snapshots",
                        ),
                        ui.div("SnapShot", class_="ppf-acao-rotulo"),
                        class_="ppf-acao",
                    ),
                    class_="ppf-grupo-acoes",
                ),
                class_="ppf-faixa-filtros",
            ),
            ui.output_ui("corpo_tabela_pagar"),
            id="secao_contas_pagar",
        ),
        class_="fin-modulo",
    )


def _incrementar(contador) -> None:
    with reactive.isolate():
        contador.set(contador() + 1)


def _linhas_por_pagina(revenda_atual) -> int:
    with reactive.isolate():
        revenda = revenda_atual() if callable(revenda_atual) else revenda_atual
    return d.linhas_por_pagina(revenda)


@module.server
def diario_server(input, output, session, revenda_atual=None, pedir_atualizacao=None, acompanhar_tarefa=None):
    paginador = TabelaPaginada(
        "pagar",
        input,
        session,
        tamanho_padrao=_linhas_por_pagina(revenda_atual),
    )

    def _revenda() -> str | None:
        return revenda_atual() if callable(revenda_atual) else revenda_atual

    overlay = gravacao.OVERLAY
    overlay_versao = reactive.value(0)

    marcacoes_versao = reactive.value(0)
    assinar_versao = reactive.value(0)

    manuais_versao = reactive.value(0)

    partes_versao = reactive.value(0)

    _manuais_atuais: dict = {}
    _manual_em_edicao = reactive.value(None)

    def _usuario() -> str:
        try:
            raiz = session.root_scope() if hasattr(session, "root_scope") else session
            quem, _script = identificar_usuario(raiz.http_conn)
            return (quem or "").strip() or "desconhecido"
        except Exception:
            return "desconhecido"

    def _pode(funcionalidade: str) -> bool:
        return pode(_usuario(), funcionalidade, _revenda())

    @render.ui
    def so_contas_a_pagar():
        if so_contas_a_pagar_no_diario(_usuario(), _revenda()):
            return ui.tags.style(ESTILO_SO_CONTAS_A_PAGAR)
        return None

    def _avisar(mensagem, tipo: str = "warning", titulo: str = "Aviso") -> None:
        ui.modal_show(modal_aviso(mensagem, titulo=titulo, tipo=tipo), session=session)

    recados_modal = reactive.value(())

    def _recado_no_modal(texto: str, tipo: str = "message") -> None:
        with reactive.isolate():
            atuais = recados_modal()
        recados_modal.set(atuais + ((texto, tipo),))

    def _limpar_recados() -> None:
        recados_modal.set(())

    @render.ui
    def recados_do_modal():
        itens = recados_modal()
        if not itens:
            return None
        simbolos = {"error": "\u2715", "warning": "!", "success": "\u2713", "message": "i"}
        return ui.div(
            *[
                ui.div(
                    ui.span(simbolos.get(tipo, "i"), class_="ppf-recado-icone"),
                    ui.span(texto),
                    class_=f"ppf-recado ppf-recado-{tipo}",
                )
                for texto, tipo in itens
            ],
            class_="ppf-recados",
        )

    def _slot_recados():
        return ui.output_ui(session.ns("recados_do_modal"))

    def _barrar(funcionalidade: str, no_modal: bool = False) -> bool:
        if _pode(funcionalidade):
            return False
        texto = "Você não tem permissão para isso. " + quem_libera(funcionalidade)
        if no_modal:
            _recado_no_modal(texto, "warning")
        else:
            _avisar(texto, titulo="Sem permissão")
        return True

    def _com_overlay(base: pl.DataFrame) -> pl.DataFrame:
        overlay_versao()
        if base.is_empty() or "_id" not in base.columns:
            return base

        excluidos = manual_arquivo.exclusoes()
        if excluidos or overlay.excluidos:
            atualizado = obter_atualizacao(
                pastas_da_sessao.pasta_dos_carimbos(PASTA_CACHE), "contas_pagar", cnpj=cnpjs_dos_carimbos(_revenda())
            )
            base = cp.sem_os_excluidos(
                base, excluidos, set(overlay.excluidos), atualizado, manual_arquivo.excluidos_fora_do_control()
            )
        if base.is_empty():
            return base

        em_historico = _dia_do_historico() is not None

        for (ident, tipo), quem in manual_arquivo.marcacoes_por_chave().items():
            coluna = f"_{tipo}"
            if coluna not in base.columns:
                continue
            if not em_historico:
                base = base.with_columns(
                    pl.when(pl.col("_id") == ident)
                    .then(pl.lit("Sim" if quem else "Não"))
                    .otherwise(pl.col(coluna).cast(pl.Utf8))
                    .alias(coluna)
                )
            autor = f"_{tipo}_user"
            if autor in base.columns:
                base = base.with_columns(
                    pl.when(pl.col("_id") == ident)
                    .then(pl.lit(quem))
                    .otherwise(pl.col(autor).cast(pl.Utf8))
                    .alias(autor)
                )
        copiadas = d.justificativas()
        if "_justificativa" in base.columns and {"id_unico", "texto"} <= set(copiadas.columns):
            mapa = (
                copiadas.select(
                    pl.col("id_unico").cast(pl.Utf8).alias("_id"), pl.col("texto").cast(pl.Utf8).alias("_just_antigo")
                )
                .filter(pl.col("_just_antigo").str.strip_chars() != "")
                .unique(subset=["_id"], keep="last")
            )
            base = (
                base.with_columns(pl.col("_id").cast(pl.Utf8))
                .join(mapa, on="_id", how="left", maintain_order="left")
                .with_columns(
                    pl.coalesce("_just_antigo", pl.col("_justificativa").cast(pl.Utf8)).alias("_justificativa")
                )
                .drop("_just_antigo")
            )
        do_arquivo = manual_arquivo.justificativas_por_titulo()
        if do_arquivo and "_justificativa" in base.columns:
            for ident, texto in do_arquivo.items():
                base = base.with_columns(
                    pl.when(pl.col("_id") == ident)
                    .then(pl.lit(texto or None))
                    .otherwise(pl.col("_justificativa").cast(pl.Utf8))
                    .alias("_justificativa")
                )

        if not em_historico and "_enviado" in base.columns:
            fila = d.pagamentos_manuais()
            na_fila = (
                set(fila.filter(pl.col("pagar").cast(pl.Utf8) == "Sim")["id_unico"].cast(pl.Utf8))
                if not fila.is_empty() and {"id_unico", "pagar"} <= set(fila.columns)
                else set()
            )
            enviados = (na_fila | set(manual_arquivo.enviados_em())) - manual_arquivo.fora_da_fila()
            base = base.with_columns(
                pl.when(pl.col("_id").is_in(list(enviados)))
                .then(pl.lit("Sim"))
                .otherwise(pl.lit("Não"))
                .alias("_enviado")
            )

        if not em_historico:
            editados = manual_arquivo.pagamentos_por_titulo()
            campos = (("_pago", "valor_pago"), ("_juros", "juros"), ("Banco", "banco"))
            for ident, valores in editados.items():
                for coluna, chave in campos:
                    if coluna not in base.columns:
                        continue
                    base = base.with_columns(
                        pl.when(pl.col("_id") == ident)
                        .then(pl.lit(valores[chave]))
                        .otherwise(pl.col(coluna))
                        .alias(coluna)
                    )

        herdadas = [c for c in ("_auditoria", "_auditoria_user", "_conselho", "_conselho_user") if c in base.columns]
        eh_parte_ = pl.col("_id").cast(pl.Utf8).str.contains(cp.SUFIXO_PARTE)
        if herdadas and base.filter(eh_parte_).height:
            do_titulo = (
                base.filter(~eh_parte_)
                .select(pl.col("_id").alias("_titulo"), *[pl.col(c).alias(f"_do_titulo{c}") for c in herdadas])
                .unique(subset=["_titulo"], keep="first")
            )
            base = (
                base.with_columns(pl.col("_id").cast(pl.Utf8).str.replace(cp.SUFIXO_PARTE, "").alias("_titulo"))
                .join(do_titulo, on="_titulo", how="left", maintain_order="left")
                .with_columns(
                    [pl.when(eh_parte_).then(pl.col(f"_do_titulo{c}")).otherwise(pl.col(c)).alias(c) for c in herdadas]
                )
                .drop(["_titulo", *[f"_do_titulo{c}" for c in herdadas]])
            )
        if not em_historico:
            base = _sem_o_pagar_na_gestao(base)
        return base

    def _sem_o_pagar_na_gestao(base: pl.DataFrame) -> pl.DataFrame:
        if not {"_id", "_conselho", "_pagar"} <= set(base.columns):
            return base
        preso = (pl.col("_conselho").cast(pl.Utf8) == "Sim") & (pl.col("_pagar").cast(pl.Utf8) == "Sim")
        if "_pagou" in base.columns:
            preso &= pl.col("_pagou").cast(pl.Utf8).fill_null("") != "Sim"
        presos = [ident for ident in base.filter(preso)["_id"].to_list() if ident]
        if not presos:
            return base
        tirados = []
        for ident in presos:
            try:
                manual_arquivo.desmarcar(ident, "pagar", _usuario())
                tirados.append(ident)
            except Exception as erro:
                logger.warning(f"Contas a Pagar: o Pagar de {ident}, na Gestao, nao saiu do arquivo -- {erro}")
        if not tirados:
            return base
        logger.info(f"Contas a Pagar: o Pagar de {len(tirados)} titulo(s) na Gestao saiu ({', '.join(tirados)})")
        na_lista = pl.col("_id").is_in(tirados)
        trocas = [pl.when(na_lista).then(pl.lit("Não")).otherwise(pl.col("_pagar").cast(pl.Utf8)).alias("_pagar")]
        if "_pagar_user" in base.columns:
            trocas.append(
                pl.when(na_lista)
                .then(pl.lit(None, pl.Utf8))
                .otherwise(pl.col("_pagar_user").cast(pl.Utf8))
                .alias("_pagar_user")
            )
        return base.with_columns(trocas)

    fabrica_ligada = reactive.value(False)

    @reactive.effect
    @reactive.event(input.filtro_fabrica)
    def _alternar_fabrica():
        fabrica_ligada.set(not fabrica_ligada())
        paginador.reiniciar()

    @reactive.calc
    async def extrato() -> pl.DataFrame:
        base = await asyncio.to_thread(d.extrato_banco)
        return d.filtrar_por_revenda(base, _revenda())

    @reactive.poll(cp.versao_das_liberadas, 10)
    def _liberadas_no_disco():
        return cp.versao_das_liberadas()

    @reactive.calc
    async def pagar_base() -> pl.DataFrame:
        overlay_versao()

        dia = _dia_do_historico()
        if dia is not None:
            lista = d.filtrar_por_revenda(await asyncio.to_thread(d.contas_pagar_do_retrato, dia), _revenda())
            quitados = d.filtrar_por_revenda(d.pagamentos_manuais(), _revenda())
            if not quitados.is_empty() and "pagou" in quitados.columns:
                quitados = quitados.filter(pl.col("pagou").cast(pl.Utf8).str.strip_chars() == "Sim")
            return await asyncio.to_thread(cp.do_snapshot, lista, await snapshots(), quitados, dia)

        base = await asyncio.to_thread(d.contas_pagar)
        base = d.filtrar_por_revenda(base, _revenda())
        _liberadas_no_disco()
        base = cp.sem_entradas_de_hoje(
            base, _pode("ver_entradas_de_hoje"), _so_entradas_de_hoje(), cp.entradas_de_hoje_liberadas()
        )
        base = await asyncio.to_thread(d.com_nome_fornecedor, base)
        base = d.com_centro_custo_abreviado(base, _revenda())
        return cp.com_manuais_pendentes(base, await manuais_prontos())

    @reactive.calc
    async def pagar_com_partes() -> pl.DataFrame:
        partes_versao()
        base = await pagar_base()
        if _dia_do_historico() is not None:
            return base
        return cp.com_partes(base)

    @reactive.calc
    async def pagar_filtrado() -> pl.DataFrame:
        return _filtrar_pagar(await pagar_com_partes())

    def _filtrar_pagar(base: pl.DataFrame, sem: str | None = None) -> pl.DataFrame:
        if base.is_empty():
            return base

        hoje = date.today()
        periodo = input.periodo()
        if "DATA" in base.columns:
            intervalo = input.intervalo()
            if intervalo and intervalo[0] and intervalo[1]:
                base = d.janela(base, intervalo[0], intervalo[1])
            elif periodo == "hoje":
                base = base.filter(pl.col("DATA").is_in(list(cp.datas_de_hoje(hoje))))
            elif periodo == "vencidos":
                teto = cp.dia_util_anterior(hoje)
                base = base.filter(pl.col("DATA") <= teto)
            elif periodo == "a_vencer":
                base = base.filter(pl.col("DATA") > hoje)

        for id_filtro, _rotulo, coluna in FILTROS_TEXTO:
            escolhido = input[id_filtro]()
            if escolhido and coluna in base.columns and coluna != sem:
                base = base.filter(pl.col(coluna).cast(pl.Utf8) == escolhido)

        fabrica = fabricas.fabrica_da_revenda(_revenda())
        if fabrica_ligada() and fabrica is not None and "FORNECEDOR" in base.columns:
            base = base.filter(fabricas.expressao_da_fabrica("FORNECEDOR", fabrica))
        return base

    _opcoes_enviadas: dict[str, dict] = {}

    @reactive.effect
    async def _preencher_filtros():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        completa = await pagar_com_partes()
        for id_filtro, _rotulo, coluna in FILTROS_TEXTO:
            try:
                base = _filtrar_pagar(completa, sem=coluna)
                valores = (
                    base[coluna].cast(pl.Utf8).drop_nulls().unique().sort().to_list() if not base.is_empty() else []
                )
            except Exception as exc:
                print(f'Contas a Pagar: coluna "{coluna}" nao encontrada -- {exc}')
                continue
            with reactive.isolate():
                escolhido = input[id_filtro]()
            opcoes = {"": "Todos", **{v: v for v in valores if v}}
            if _opcoes_enviadas.get(id_filtro) == opcoes:
                continue
            _opcoes_enviadas[id_filtro] = opcoes
            ui.update_selectize(
                id_filtro,
                choices=opcoes,
                selected=escolhido if escolhido in opcoes else "",
            )

    @reactive.effect(priority=-10)
    @reactive.event(input.periodo)
    def _radio_limpa_os_outros():
        if not input.periodo():
            return
        ui.update_date_range("intervalo", start="", end="")
        for id_filtro, _rotulo, _coluna in FILTROS_TEXTO:
            ui.update_selectize(id_filtro, selected="")

    @reactive.effect
    @reactive.event(input.limpar)
    async def _limpar_filtros():
        ui.update_radio_buttons("periodo", choices=PERIODOS, selected="", inline=True)
        ui.update_date_range("intervalo", start="", end="")
        for id_filtro, _rotulo, _coluna in FILTROS_TEXTO:
            ui.update_selectize(id_filtro, selected="")
        fabrica_ligada.set(False)
        paginador.reiniciar()

    @reactive.effect
    @reactive.event(input.limpar_selecao)
    def _limpar_selecao_composicao():
        celulas_somadas.set(frozenset())

    ETAPAS_VERIFICACAO = (("financeiro", "Financeiro"), ("diretoria", "Diretoria"))

    verificacao_versao = reactive.value(0)

    _erro_espelho_visto = {"texto": ""}

    @reactive.effect
    def _avisar_espelho_falhou():
        verificacao_versao()
        manuais_versao()
        overlay_versao()
        marcacoes_versao()
        assinar_versao()
        erro = manual_arquivo.ultimo_erro_banco()
        if erro == _erro_espelho_visto["texto"]:
            return
        _erro_espelho_visto["texto"] = erro
        if not erro:
            return
        _avisar(
            ui.TagList(
                ui.tags.b("A ação valeu, mas a cópia no banco falhou."),
                ui.tags.br(),
                ui.tags.span(erro[:160]),
                ui.tags.br(),
                ui.tags.span(
                    "Quando o banco voltar, rode scripts/refazer_manual.py para reenviar o que ficou só no arquivo.",
                    class_="small",
                ),
            ),
            titulo="Gravação",
        )

    def _dia_verificacao() -> date:
        return _dia_do_historico() or date.today()

    def _quem_verificou(etapa: str) -> str | None:
        verificacao_versao()
        dia, revenda = _dia_verificacao(), chave_revenda(_revenda())
        do_arquivo = manual_arquivo.verificacoes_por_dia()
        chave = (dia, revenda, etapa)
        if chave in do_arquivo:
            return do_arquivo[chave]
        base = d.verificacao_diaria() if hasattr(d, "verificacao_diaria") else None
        if base is None or base.is_empty():
            return None
        try:
            nomes = base["REVENDA"].unique().to_list()
            iguais = [n for n in nomes if chave_revenda(n) == revenda]
            linha = base.filter((pl.col("data").cast(pl.Date, strict=False) == dia) & (pl.col("REVENDA").is_in(iguais)))
        except Exception:
            return None
        if linha.is_empty():
            return None
        coluna_ok = "financeiro_ok" if etapa == "financeiro" else "diretoria_ok"
        coluna_por = "financeiro_por" if etapa == "financeiro" else "diretoria_por"
        if coluna_ok not in linha.columns or not linha[coluna_ok][0]:
            return None
        quem = linha[coluna_por][0] if coluna_por in linha.columns else None
        return str(quem) if quem else "desconhecido"

    def _verificacao(etapa: str):
        verificacao_versao()
        dia, revenda = _dia_verificacao(), chave_revenda(_revenda())
        do_arquivo = manual_arquivo.verificacoes_com_hora()
        if (dia, revenda, etapa) in do_arquivo:
            quem, quando = do_arquivo[(dia, revenda, etapa)]
            return (quem, quando) if quem else (None, None)
        quem = _quem_verificou(etapa)
        if not quem:
            return None, None
        coluna_em = "financeiro_em" if etapa == "financeiro" else "diretoria_em"
        quando = None
        try:
            base = d.verificacao_diaria()
            linha = base.filter(
                (pl.col("data").cast(pl.Date, strict=False) == dia)
                & pl.col("REVENDA").map_elements(chave_revenda, return_dtype=pl.Utf8).eq(revenda)
            )
            if linha.height and coluna_em in linha.columns:
                quando = linha[coluna_em][0]
        except Exception:
            quando = None
        return quem, quando

    PERMISSAO_ETAPA = {"financeiro": "processar_pagamento", "diretoria": "conselho_ppf"}

    @reactive.effect
    def _mostrar_verificacao():
        financeiro_feito = bool(_verificacao("financeiro")[0])
        historico = _dia_do_historico() is not None
        for chave, rotulo in ETAPAS_VERIFICACAO:
            quem, quando = _verificacao(chave)
            pode = _pode(PERMISSAO_ETAPA[chave]) and not historico
            if chave == "diretoria" and not financeiro_feito:
                pode = False
            dica = "Clique para desmarcar" if quem else f"Marcar verificação {chave}"
            ui.update_action_button(
                f"step_{chave}",
                label=ui.span(
                    ui.span(
                        icon_svg("check", a11y="deco") if quem else None,
                        class_="ppf-verif-ponto" + (" ppf-verif-feito" if quem else ""),
                    ),
                    ui.span(
                        rotulo,
                        ui.tags.small(
                            f"{cp.nome_legivel(quem)} \u00b7 {quando:%H:%M}" if quando else cp.nome_legivel(quem)
                        )
                        if quem
                        else None,
                        class_="ppf-verif-rotulo",
                    ),
                    title=dica,
                    class_="ppf-verif-dica",
                ),
                disabled=not pode,
            )

    @render.ui
    def verif_aguardando():
        feitas = all(_verificacao(chave)[0] for chave, _rotulo in ETAPAS_VERIFICACAO)
        return ui.span(
            ui.span(icon_svg("check", a11y="deco"), class_="ppf-verif-ponto ppf-verif-feito") if feitas else None,
            ui.span("Verificado" if feitas else "Aguardando", class_="ppf-verif-rotulo"),
            class_="ppf-verif-etapa ppf-verif-aguardando" + (" ppf-verif-verificado" if feitas else ""),
        )

    def _ligar_etapa(chave: str, rotulo: str) -> None:
        @reactive.effect
        @reactive.event(getattr(input, f"step_{chave}"))
        def _alternar():
            if _barrar(PERMISSAO_ETAPA[chave]):
                return
            if _dia_do_historico() is not None:
                _avisar(
                    "O Histórico é um retrato de um dia passado — a verificação diária vale para HOJE.",
                    titulo="Verificação diária",
                )
                return
            revenda = _revenda()
            if not revenda:
                return
            if chave == "diretoria" and not _verificacao("financeiro")[0]:
                _avisar(
                    "O Financeiro precisa ser verificado primeiro.",
                    titulo="Verificação diária",
                )
                return
            marcado = _quem_verificou(chave)
            try:
                manual_arquivo.verificar(
                    date.today(),
                    chave_revenda(revenda),
                    chave,
                    None if marcado else _usuario(),
                )
                _incrementar(verificacao_versao)
            except Exception as erro:
                _avisar(
                    f"Falhou ao gravar: {str(erro)[:200]}",
                    tipo="error",
                    titulo="Verificação diária",
                )

    for _chave, _rotulo in ETAPAS_VERIFICACAO:
        _ligar_etapa(_chave, _rotulo)

    @reactive.effect
    @reactive.event(input.enviar)
    async def _enviar():
        if _dia_do_historico() is not None:
            _avisar(
                "No Histórico a tabela é um retrato de um dia passado: não há o "
                'que enviar. Volte para "Atual" no cabeçalho.',
                titulo="Enviar",
            )
            return
        if _barrar("processar_pagamento"):
            return
        usuario = _usuario()
        base = await pagar_com_partes()
        itens, desfazer, de_outros, sem_auditoria, na_gestao = _itens_do_envio(
            base, usuario, await _bancos_da_revenda()
        )
        enviados: list = []
        desfeitos: list = []
        if itens or desfazer:
            try:
                enviados, desfeitos, partes_apagadas, datas = await asyncio.to_thread(
                    gravacao.enviar_pagamentos, itens, desfazer, usuario
                )
            except Exception as erro:
                _avisar(
                    f"O envio falhou e nada foi gravado: {str(erro)[:300]}",
                    tipo="error",
                    titulo="Enviar",
                )
                return
            agora = datetime.now()
            por_id = {item["id_unico"]: item for item in itens}
            try:
                editados = manual_arquivo.pagamentos_por_titulo()
                edicoes = [
                    {
                        "id_unico": ident,
                        "valor_pago": por_id[ident]["valor_pago"],
                        "juros": por_id[ident]["juros"],
                        "banco": por_id[ident]["banco"],
                        "data_pagamento": datas.get(ident) or por_id[ident]["data_pagamento"],
                        "enviado_em": agora,
                    }
                    for ident in enviados
                ] + [
                    {
                        "id_unico": ident,
                        "valor_pago": (editados.get(ident) or {}).get("valor_pago"),
                        "juros": (editados.get(ident) or {}).get("juros"),
                        "banco": (editados.get(ident) or {}).get("banco"),
                        "data_pagamento": None,
                        "enviado_em": None,
                    }
                    for ident in desfeitos
                ]
                await asyncio.to_thread(manual_arquivo.editar_pagamentos, edicoes, usuario)
                await asyncio.to_thread(manual_arquivo.anotar_fila, enviados, desfeitos, usuario)
                if partes_apagadas:
                    manual_arquivo.desfazer_partes(partes_apagadas, usuario)
                    _so_partes["pendente"] = True
                    _incrementar(partes_versao)
            except Exception as erro:
                _avisar(
                    "A fila foi gravada, mas a tela não conseguiu anotar o envio "
                    f"({str(erro)[:200]}). O próximo Atualizar acerta.",
                    tipo="warning",
                    titulo="Enviar",
                )
            _incrementar(marcacoes_versao)
            _incrementar(overlay_versao)

        partes = []
        if enviados:
            partes.append(
                f"{len(enviados)} pagamento{'s' if len(enviados) > 1 else ''} "
                f"enviado{'s' if len(enviados) > 1 else ''} para a fila."
            )
        if desfeitos:
            partes.append(f"{len(desfeitos)} desmarcado{'s' if len(desfeitos) > 1 else ''} saiu da fila.")
        if de_outros:
            partes.append(
                f"{len(de_outros)} marcado{'s' if len(de_outros) > 1 else ''} por "
                "outra pessoa não foi enviado — quem marcou é quem envia."
            )
        if sem_auditoria:
            partes.append(f"{len(sem_auditoria)} sem auditoria não foi enviado (precisa do visto de Auditoria antes).")
        if na_gestao:
            partes.append(
                f"{len(na_gestao)} marcado{'s' if len(na_gestao) > 1 else ''} na Gestão não foi "
                "enviado — a Gestão trava o pagamento até ser desmarcada."
            )
        if not partes:
            partes.append("Nenhum título marcado para Pagar por você.")
        await _pedir_retrato(" ".join(partes), titulo="Enviar")

    def _itens_do_envio(base: pl.DataFrame, usuario: str, bancos_da_revenda: dict):
        marcas = manual_arquivo.marcacoes_por_chave()
        editados = manual_arquivo.pagamentos_por_titulo()
        exige = exige_auditoria_para_pagar(usuario)
        do_cartao = dc.titulos_do_cartao()
        limites: dict = {}
        itens, desfazer, de_outros, sem_auditoria, na_gestao = [], [], [], [], []
        if base.is_empty() or "id_unico" not in base.columns:
            return itens, desfazer, de_outros, sem_auditoria, na_gestao
        da_base = {
            linha["id_unico"]: linha
            for linha in base.iter_rows(named=True)
            if linha.get("id_unico") and not eh_parte(linha["id_unico"])
        }
        for linha in base.iter_rows(named=True):
            ident = linha.get("id_unico")
            if not ident:
                continue
            if (ident, "pagar") in marcas:
                quem = marcas[(ident, "pagar")]
                if not quem:
                    desfazer.append(ident)
                    continue
            else:
                if str(linha.get("pagar") or "") != "Sim":
                    continue
                quem = str(linha.get("pagar_user") or "")
            if str(linha.get("pagou") or "") == "Sim":
                continue
            if quem and not cp.mesma_pessoa(quem, usuario):
                de_outros.append(ident)
                continue
            linha_base = da_base.get(base_do(ident))
            if exige and not cp.auditado(ident, linha, marcas, linha_base):
                sem_auditoria.append(ident)
                continue
            if cp.na_gestao(ident, linha, marcas, linha_base):
                na_gestao.append(ident)
                continue

            original = cp.float_ou_none(linha.get("PGMOVMOV_VALOR")) or 0.0
            edicao = editados.get(ident) or {}
            valor = edicao.get("valor_pago")
            juros_gravado = edicao.get("juros")
            if valor is None:
                valor = cp.float_ou_none(linha.get("valor_pago"))
                juros_gravado = cp.float_ou_none(linha.get("juros"))
            valor = (
                cp.valor_pago_exibido(
                    original,
                    valor,
                    juros_gravado,
                    linha.get("pagou"),
                    _desconto_ate(linha.get("REVENDA"), limites, linha.get("PGMOVMOV_CGC"), original),
                )
                or original
            )
            banco = (
                edicao.get("banco")
                or linha.get("banco")
                or dc.banco_do_cartao(ident, bancos_da_revenda, do_cartao)
                or _banco_padrao(bancos_da_revenda, linha.get("REVENDA"))
            )
            if (ident, "conselho") in marcas:
                conselho = "Sim" if marcas[(ident, "conselho")] else "Não"
            else:
                conselho = "Sim" if str(linha.get("conselho") or "") == "Sim" else "Não"
            itens.append(
                {
                    "id_unico": ident,
                    "valor_titulo": cp.float_ou_none(linha.get("valor_titulo")),
                    "revenda": linha.get("REVENDA"),
                    "valor_pago": round(float(valor), 2),
                    "juros": max(0.0, round(float(valor) - original, 2)),
                    "banco": banco,
                    "conselho": conselho,
                    "entrada_manual": "Sim" if str(linha.get("entrada_manual") or "") == "Sim" else "Não",
                    "data_pagamento": edicao.get("data_pagamento") or linha.get("data_pagamento") or date.today(),
                    "base": {
                        "data_vencimento": linha.get("DATA"),
                        "num_doc": linha.get("PGMOVMOV_NDUPL"),
                        "num_doc_normalizado": linha.get("num_doc_normalizado"),
                        "tipo_doc": linha.get("tipo_doc"),
                        "cnpj": linha.get("PGMOVMOV_CGC"),
                        "valor_original": original,
                        "razao_social": linha.get("FORNECEDOR"),
                        "descricao_despesa": linha.get("descricao_despesa"),
                    },
                }
            )
        return itens, desfazer, de_outros, sem_auditoria, na_gestao

    @reactive.effect
    @reactive.event(input.snapshot)
    async def _snapshot():
        await _pedir_retrato("", titulo="SnapShot")

    async def _pedir_retrato(recado: str, titulo: str = "SnapShot") -> None:
        revenda = _revenda()
        if not revenda:
            _avisar(
                "Sem revenda na URL — não dá para saber o que retratar.",
                titulo=titulo,
            )
            return
        if _barrar("processar_pagamento"):
            return
        try:
            id_tarefa = await asyncio.to_thread(sincronia.disparar, revenda, "retrato", _usuario())
        except Exception as erro:
            _avisar(
                f"{recado} O retrato do dia NÃO foi enfileirado: {str(erro)[:300]}".strip(),
                tipo="error",
                titulo=titulo,
            )
            return
        if not id_tarefa:  # portfólio: sem worker, o Histórico já traz os retratos dos dias anteriores
            _avisar(
                f"{recado} No portfólio o retrato do dia não é gravado: os dias anteriores já estão no Histórico.".strip(),
                tipo="success",
                titulo=titulo,
            )
            return
        if acompanhar_tarefa is not None and id_tarefa:
            acompanhar_tarefa(id_tarefa)
        if recado:
            _avisar(
                f"{recado} O retrato do dia está sendo gravado -- acompanhe pela barra no topo.",
                tipo="success",
                titulo=titulo,
            )

    def _guardar(campo: str, pasta: str, permissao: str = "upload_extrato") -> None:
        enviados = input[campo]()
        if not enviados:
            return
        _limpar_recados()
        if _barrar(permissao, no_modal=True):
            return
        destino = an.pasta_do_upload(pasta, nome_oficial(_revenda()) or _revenda())
        destino.mkdir(parents=True, exist_ok=True)
        guardados = []
        for arquivo in enviados:
            nome = Path(arquivo["name"]).name
            veredito = arquivo_revenda.avaliar(nome, arquivo["datapath"], _revenda())
            if not veredito.aceito:
                _recado_no_modal(f"“{nome}” recusado: {veredito.erro}", "error")
                continue
            if veredito.aviso:
                _recado_no_modal(f"“{nome}”: {veredito.aviso}", "warning")
            try:
                alvo = arquivo_revenda.destino_para_guardar(destino, veredito.nome)
                substituiu = alvo.exists()
                shutil.move(arquivo["datapath"], alvo)
                if substituiu:
                    _recado_no_modal(f"“{alvo.name}” já estava lá: foi substituído pelo novo.", "message")
                guardados.append(alvo.name)
                an.esquecer_listas()
                if alvo.suffix.lower() in (".xlsx", ".xlsm"):
                    leitura = planilha_fabrica.ler(alvo)
                    _recado_no_modal(
                        f"“{alvo.name}”: {planilha_fabrica.resumo(leitura)}",
                        "error" if leitura.erro else "message",
                    )
            except Exception as erro:
                _recado_no_modal(f"Não deu para guardar “{nome}”: {str(erro)[:120]}", "error")
        if guardados:
            try:
                manual_arquivo.registrar_envio(
                    nome_oficial(_revenda()) or (_revenda() or ""),
                    TIPO_DE_ENVIO.get(pasta, pasta),
                    _usuario(),
                )
            except Exception as erro:
                _recado_no_modal(
                    f"Arquivo guardado, mas o envio não foi registrado: {str(erro)[:120]}",
                    "warning",
                )
            perfil = PERFIL_DO_ARQUIVO.get(pasta)
            if perfil and pedir_atualizacao is not None:
                pedir_atualizacao(perfil)
            _recado_no_modal(
                f"{len(guardados)} arquivo(s) recebido(s). "
                + (
                    "A matriz está sendo atualizada com ele(s) agora -- acompanhe pela barra no "
                    "topo; não precisa clicar em Atualizar."
                    if perfil and pedir_atualizacao is not None
                    else "Arquivo guardado (o Modelo IV é só anexo, não muda número da tela)."
                    if pasta == "modelo_iv"
                    else "Os números da tela mudam no próximo Atualizar."
                ),
                "success",
            )

    uploads_mudaram = reactive.value(0)

    def _entregar_upload(request):
        from starlette.responses import FileResponse, PlainTextResponse, Response

        pasta = request.query_params.get("pasta", "")
        nome = request.query_params.get("nome", "")
        if pasta not in {u.pasta for u in an.UPLOADS}:
            return PlainTextResponse("pasta desconhecida", status_code=404)
        assunto = (carregar_json("arquivos").get("assunto_do_upload") or {}).get(pasta) or pasta
        candidatas = [*fontes.pastas(assunto), an.PASTA_UPLOADS / pasta]
        for destino in candidatas:
            base = Path(destino).resolve()
            alvo = (base / Path(nome).name).resolve()
            if alvo.is_relative_to(base) and alvo.is_file():
                tipo, como = an.como_mostrar(alvo.name)
                return FileResponse(
                    alvo,
                    media_type=tipo,
                    headers={"Content-Disposition": f'{como}; filename="{alvo.name}"'},
                )
        procurado = Path(nome).name
        for destino in candidatas:
            for zipado in sorted(Path(destino).glob("_arquivo_*.zip"), reverse=True):
                try:
                    with zipfile.ZipFile(zipado) as z:
                        dentro = next((i for i in z.infolist() if Path(i.filename).name == procurado), None)
                        if dentro is None:
                            continue
                        tipo, como = an.como_mostrar(procurado)
                        return Response(
                            z.read(dentro),
                            media_type=tipo,
                            headers={"Content-Disposition": f'{como}; filename="{procurado}"'},
                        )
                except (zipfile.BadZipFile, OSError):
                    continue
        return PlainTextResponse("arquivo não encontrado", status_code=404)

    url_upload = session.dynamic_route("ver_upload", _entregar_upload)
    _emenda = "&" if "?" in url_upload else "?"

    def _painel_upload(u: an.Upload):
        return ui.TagList(
            ui.div(
                ui.input_file(
                    session.ns(u.campo),
                    None,
                    button_label=ui.TagList(
                        ui.tags.img(src=u.icone, class_="ppf-arquivo-icone", alt=""),
                        f"Selecionar {'arquivos' if u.varios else 'arquivo'}",
                    ),
                    placeholder="Nenhum arquivo selecionado",
                    accept=u.aceita,
                    multiple=u.varios,
                    width="100%",
                ),
                class_="ppf-modal-arquivo",
            ),
            ui.h6(u.lista, class_="ppf-modal-lista-titulo"),
            ui.div(ui.output_ui(session.ns(f"lista_{u.campo}")), class_="ppf-modal-lista-slot"),
            ui.output_ui(session.ns(f"confirma_{u.campo}")),
        )

    def _modal_upload(u: an.Upload):
        formatos = an.variantes(u)
        if len(formatos) == 1:
            corpo = _painel_upload(u)
        else:
            corpo = ui.navset_tab(
                *[
                    ui.nav_panel(
                        ui.TagList(
                            ui.tags.img(src=f.icone, class_="ppf-arquivo-icone", alt=""),
                            f.aba or f.rotulo,
                        ),
                        ui.div(_painel_upload(f), class_="ppf-modal-aba"),
                    )
                    for f in formatos
                ],
                id=session.ns(f"aba_{u.grupo}"),
            )
        return ui.modal(
            _slot_recados(),
            corpo,
            title=u.titulo,
            easy_close=True,
            size="m",
            footer=ui.modal_button("Fechar", class_="btn btn-secondary"),
        )

    _delegados: list = []
    _delegados_async: list = []

    def _delegado(funcao):
        destino = _delegados_async if asyncio.iscoroutinefunction(funcao) else _delegados
        destino.append(funcao)
        return funcao

    ARQUIVOS_POR_LISTA = 30
    uploads_a_excluir = reactive.value(("", ()))
    _todos_vistos: dict = {}
    _listas_desenhadas: dict = {}

    def _ligar_lista(u: an.Upload) -> None:

        @output(id=f"lista_{u.campo}")
        @render.ui
        async def _lista():
            uploads_mudaram()
            arquivos = await asyncio.to_thread(an.arquivos_enviados, u.pasta, _revenda())
            _listas_desenhadas[u.campo] = arquivos
            if not arquivos:
                return ui.p(
                    "Nenhum arquivo enviado ainda.",
                    class_="ppf-modal-lista-vazia",
                )
            apagaveis = any(nosso for _n, _q, _r, nosso in arquivos[:ARQUIVOS_POR_LISTA])
            barra = (
                ui.div(
                    ui.input_checkbox(f"todos_{u.campo}", "Selecionar todos"),
                    ui.div(
                        ui.download_button(
                            f"baixar_sel_{u.campo}",
                            "Baixar selecionados",
                            icon=icon_svg("download"),
                            class_="ppf-modal-btn-baixar-sel",
                        ),
                        ui.input_action_button(
                            f"excluir_sel_{u.campo}",
                            ui.TagList(ui.tags.img(src="img/ppf/delete-icon.svg", alt=""), "Excluir selecionados"),
                            class_="ppf-modal-btn-excluir-sel",
                        ),
                        class_="ppf-modal-lista-barra-botoes",
                    ),
                    class_="ppf-modal-lista-barra",
                )
                if apagaveis
                else None
            )
            return ui.TagList(
                barra,
                ui.tags.ul(
                    *[
                        ui.tags.li(
                            ui.div(
                                ui.input_checkbox(f"sel_{u.campo}_{indice}", "")
                                if nosso and indice < ARQUIVOS_POR_LISTA
                                else None,
                                ui.tags.img(src=u.icone, class_="ppf-arquivo-icone", alt=""),
                                ui.span(nome, class_="ppf-modal-lista-nome"),
                                class_="ppf-modal-lista-arquivo",
                            ),
                            ui.div(
                                ui.span(quando, class_="ppf-modal-lista-data"),
                                ui.tags.a(
                                    ui.tags.img(src="img/ppf/view.svg", alt="Ver"),
                                    href=f"{url_upload}{_emenda}pasta={u.pasta}&nome={quote(nome)}",
                                    target="_blank",
                                    class_="ppf-modal-btn ppf-modal-btn-ver",
                                    title="Visualizar",
                                ),
                                ui.input_action_button(
                                    f"excluir_{u.campo}_{indice}",
                                    ui.tags.img(src="img/ppf/delete-icon.svg", alt="Excluir"),
                                    class_="ppf-modal-btn ppf-modal-btn-excluir",
                                    title="Excluir",
                                )
                                if nosso and indice < ARQUIVOS_POR_LISTA
                                else None
                                if nosso
                                else ui.span(
                                    "envio antigo",
                                    class_="ppf-modal-lista-data",
                                    title=(
                                        "Enviado pelo app antigo. O pipeline lê este "
                                        "arquivo, mas apagar só pelo app antigo."
                                    ),
                                ),
                                class_="ppf-modal-lista-acoes",
                            ),
                            class_="ppf-modal-lista-recente" if recente else None,
                        )
                        for indice, (nome, quando, recente, nosso) in enumerate(arquivos)
                    ],
                    class_="ppf-modal-lista",
                ),
            )

        @output(id=f"confirma_{u.campo}")
        @render.ui
        def _confirma():
            pasta, nomes = uploads_a_excluir()
            if pasta != u.pasta or not nomes:
                return None
            texto = f"Excluir “{nomes[0]}”?" if len(nomes) == 1 else f"Excluir os {len(nomes)} arquivos selecionados?"
            return ui.div(
                ui.span(texto),
                ui.input_action_button(f"confirmar_excl_{u.campo}", "Excluir", class_="btn btn-danger btn-sm"),
                ui.input_action_button(f"cancelar_excl_{u.campo}", "Cancelar", class_="btn btn-secondary btn-sm"),
                class_="ppf-modal-confirmar",
            )

        def _marcados() -> list[Path]:
            arquivos = _listas_desenhadas.get(u.campo, [])
            revenda = _revenda()
            caminhos = []
            for i, (nome, _q, _r, nosso) in enumerate(arquivos[:ARQUIVOS_POR_LISTA]):
                caixa = f"sel_{u.campo}_{i}"
                if not (nosso and caixa in input and input[caixa]()):
                    continue
                caminho = an.caminho_nosso(u.pasta, revenda, nome)
                if caminho is not None:
                    caminhos.append(caminho)
            return caminhos

        def _nome_do_baixar() -> str:
            return an.nome_do_download(_marcados(), f"{u.pasta}_{(_revenda() or '').replace(' ', '_')}")

        async def _baixar_selecionados():
            yield await asyncio.to_thread(an.conteudo_do_download, _marcados())

        _baixar_selecionados.__name__ = f"baixar_sel_{u.campo}"
        render.download(filename=_nome_do_baixar)(_baixar_selecionados)

        @_delegado
        def _marcar_todos():
            campo = f"todos_{u.campo}"
            if campo not in input:
                return
            marcado = bool(input[campo]())
            if _todos_vistos.get(u.campo) == marcado:
                return
            _todos_vistos[u.campo] = marcado
            arquivos = _listas_desenhadas.get(u.campo, [])
            for i, (_n, _q, _r, nosso) in enumerate(arquivos[:ARQUIVOS_POR_LISTA]):
                if nosso:
                    ui.update_checkbox(f"sel_{u.campo}_{i}", value=marcado)

        @_delegado
        def _pedir_selecionados():
            if not _clicou(f"excluir_sel_{u.campo}"):
                return
            arquivos = _listas_desenhadas.get(u.campo, [])
            with reactive.isolate():
                nomes = tuple(
                    nome
                    for i, (nome, _q, _r, nosso) in enumerate(arquivos[:ARQUIVOS_POR_LISTA])
                    if nosso and f"sel_{u.campo}_{i}" in input and input[f"sel_{u.campo}_{i}"]()
                )
            _limpar_recados()
            if not nomes:
                _recado_no_modal("Marque ao menos um arquivo para excluir.", "warning")
                return
            uploads_a_excluir.set((u.pasta, nomes))

        @_delegado
        def _responder():
            cancelou = _clicou(f"cancelar_excl_{u.campo}")
            confirmou = _clicou(f"confirmar_excl_{u.campo}")
            if cancelou:
                uploads_a_excluir.set(("", ()))
                return
            if not confirmou:
                return
            with reactive.isolate():
                pasta, nomes = uploads_a_excluir()
            if pasta != u.pasta or not nomes:
                return
            uploads_a_excluir.set(("", ()))
            _limpar_recados()
            if _barrar(u.permissao, no_modal=True):
                return
            apagados, falhas = [], []
            for nome in nomes:
                alvo = an.caminho_nosso(pasta, _revenda(), nome)
                if alvo is None:
                    falhas.append(f"{nome} (não encontrado)")
                    continue
                try:
                    alvo.unlink()
                    marca = alvo.with_suffix(alvo.suffix + ".done")
                    if marca.is_file():
                        marca.unlink()
                    apagados.append(nome)
                except Exception as erro:
                    falhas.append(f"{nome} ({str(erro)[:80]})")
            if apagados:
                an.esquecer_listas()
                _incrementar(uploads_mudaram)
                _recado_no_modal(
                    f"“{apagados[0]}” excluído." if len(apagados) == 1 else f"{len(apagados)} arquivos excluídos.",
                    "success",
                )
            if falhas:
                _recado_no_modal("Não deu para excluir: " + "; ".join(falhas), "error")

    for _u in an.UPLOADS:
        _ligar_lista(_u)

    def _ligar_excluir_upload(u: an.Upload, indice: int) -> None:
        campo = f"excluir_{u.campo}_{indice}"

        @_delegado
        def _pedir_exclusao():
            if not _clicou(campo):
                return
            arquivos = _listas_desenhadas.get(u.campo, [])
            if indice >= len(arquivos):
                return
            _limpar_recados()
            uploads_a_excluir.set((u.pasta, (arquivos[indice][0],)))

    for _u in an.UPLOADS:
        for _indice in range(ARQUIVOS_POR_LISTA):
            _ligar_excluir_upload(_u, _indice)

    def _ligar_upload(u: an.Upload) -> None:

        @reactive.effect
        @reactive.event(input[f"abrir_{u.campo}"])
        def _abrir():
            if trava_caixa.barrar(_usuario()):
                return
            if travado_por_leitura(_usuario(), u.permissao) and _barrar(u.permissao):
                return
            _limpar_recados()
            uploads_a_excluir.set(("", ()))
            ui.modal_show(_modal_upload(u))
            _incrementar(uploads_mudaram)

        @reactive.effect
        @reactive.event(input[u.campo])
        def _receber():
            _guardar(u.campo, u.pasta, u.permissao)
            _incrementar(uploads_mudaram)

    for _upload in an.UPLOADS:
        _ligar_upload(_upload)

    @reactive.poll(d.assinatura_dos_retratos, 15)
    def _retratos_no_disco():
        return d.assinatura_dos_retratos()

    @reactive.calc
    async def snapshots() -> pl.DataFrame:
        _retratos_no_disco()
        revenda = _revenda()
        return await asyncio.to_thread(lambda: d.filtrar_por_revenda(d.pagamentos_snapshot(), revenda))

    @reactive.effect
    def _preencher_historico():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        _retratos_no_disco()
        datas = d.datas_de_snapshot(d.filtrar_por_revenda(d.datas_com_retrato(), _revenda()))
        minima = _historico_minimo()
        if minima:
            datas = [dia for dia in datas if dia >= minima]
        opcoes = {"": "Atual"}
        if _pode_ver_historico():
            opcoes.update({dia.isoformat(): f"{dia:%d/%m/%Y}" for dia in datas})
        if _historico_enviado.get("opcoes") == opcoes:
            return
        primeira = "opcoes" not in _historico_enviado
        _historico_enviado["opcoes"] = opcoes
        with reactive.isolate():
            escolhido = input.historico()
        if primeira and not escolhido:
            da_url = _historico_da_url()
            if da_url in opcoes:
                escolhido = da_url
            elif da_url:
                session.on_flushed(_fechar_carregando, once=True)
        ui.update_select("historico", choices=opcoes, selected=escolhido if escolhido in opcoes else "")

    def _historico_da_url() -> str:
        raiz = session.root_scope() if hasattr(session, "root_scope") else session
        with reactive.isolate():
            busca = raiz.clientdata.url_search() or ""
        valores = parse_qs(busca.lstrip("?")).get("historico")
        return (valores[0] or "").strip() if valores else ""

    async def _fechar_carregando():
        await session.send_custom_message("fecharCarregandoHistorico", {})

    _historico_enviado: dict = {}
    _permissao_historico: dict = {}

    def _pode_ver_historico() -> bool:
        if "pode" not in _permissao_historico:
            _permissao_historico["pode"] = _pode("ver_historico")
        return _permissao_historico["pode"]

    def _historico_minimo() -> date | None:
        alvo = chave_revenda(nome_oficial(_revenda()) or _revenda() or "")
        for nome, dia in (carregar_json("parametros_financeiro").get("historico_data_minima") or {}).items():
            if not nome.startswith("_") and chave_revenda(nome) == alvo:
                try:
                    return date.fromisoformat(dia)
                except ValueError:
                    return None
        return None

    def _dia_do_historico() -> date | None:
        escolhido = (input.historico() or "").strip()
        if not escolhido or not _pode_ver_historico():
            return None
        try:
            return date.fromisoformat(escolhido)
        except ValueError:
            return None

    def _assinatura_de(*arquivos: Path) -> tuple:
        sinal = [date.today()]
        for arquivo in arquivos:
            try:
                sinal.append(arquivo.stat().st_mtime_ns)
            except OSError:
                sinal.append(0)
        return tuple(sinal)

    def _sinal_dos_envios() -> tuple:
        return _assinatura_de(
            manual_arquivo.caminho("envios_extratos"),
            PASTA_CACHE / "controle_envio_extratos.parquet",
            PASTA_CACHE / "_atualizacoes.json",
        )

    @reactive.poll(_sinal_dos_envios, 30)
    def _envios_no_disco():
        return _sinal_dos_envios()

    @render.ui
    async def alerta_extratos():
        uploads_mudaram()
        _envios_no_disco()
        revenda = nome_oficial(_revenda()) or (_revenda() or "")
        if not revenda or dc.eh_grupo(_revenda()):
            return None
        try:
            estado = await asyncio.to_thread(status_envio_do_dia, revenda, _dia_do_historico())
        except Exception as erro:
            print(f"Diário: status de envio dos extratos falhou -- {erro}")
            return None
        classe = {"no_prazo": "is-ok", "fora_prazo": "is-warning"}.get(estado["status"], "is-danger")
        faltando = estado["faltando"]
        if faltando:
            lista = faltando[0] if len(faltando) == 1 else ", ".join(faltando[:-1]) + " e " + faltando[-1]
            texto = ui.span(
                "Aguardando Envio do Extrato: " if len(faltando) == 1 else "Aguardando Envio dos Extratos: ",
                ui.span(lista, class_="ppf-extratos-faltando"),
                class_="ppf-extratos-texto",
            )
        else:
            texto = ui.span(estado["mensagem"], class_="ppf-extratos-texto")
        quando = obter_atualizacao(
            pastas_da_sessao.pasta_dos_carimbos(PASTA_CACHE), "composicao", cnpj=cnpjs_dos_carimbos(_revenda())
        )
        return ui.div(
            ui.span(class_="ppf-extratos-ponto", aria_hidden="true"),
            texto,
            *(
                [
                    ui.span("|", class_="ppf-extratos-separador", aria_hidden="true"),
                    ui.span(f"Atualizado em {quando:%d/%m/%Y %H:%M}", class_="ppf-extratos-atualizado"),
                ]
                if quando
                else []
            ),
            class_=f"ppf-extratos-alerta {classe}",
            role="status",
        )

    @render.ui
    async def cards_bancos():
        base = await composicao_base()
        parte = dc.da_revenda(base, _revenda())
        if parte.is_empty():
            dia = _dia_do_historico()
            return ui.p(
                f"Sem retrato da Composição em {dia:%d/%m/%Y}."
                if dia
                else "Sem composição no cache: rode scripts/atualiza_composicao.py."
            )
        if not dc.escopo_unico(parte):
            if not dc.eh_grupo(_revenda()):
                return ui.p(
                    "Os cartões de banco são de uma revenda ou de um grupo — escolha no menu.",
                    class_="text-muted small mb-0",
                )
            parte = dc.consolidar_grupo(parte)

        por_banco = {}
        for linha in parte.iter_rows(named=True):
            por_banco.setdefault(linha["BANCO"], {})[linha["CHAVE"]] = linha["VALOR"]

        for (chave_item, chave_banco_col), delta in (await ajuste_dados_manuais() or {}).items():
            if chave_banco_col in por_banco:
                atual = por_banco[chave_banco_col].get(chave_item)
                por_banco[chave_banco_col][chave_item] = (atual or 0.0) + delta

        ajuste = await ajuste_pendente()
        for chave_banco_col, delta in (ajuste or {}).items():
            valores_banco = por_banco.setdefault(chave_banco_col, {})
            for chave_item in ("total_despesas_sugeridas", "saldo_final_liberado", "saldo_uso_especial"):
                if chave_item == "saldo_final_liberado" and chave_banco_col in BANCOS_SEM_AJUSTE_NO_SALDO:
                    continue
                atual = valores_banco.get(chave_item)
                valores_banco[chave_item] = (atual or 0.0) + delta

        cartoes = []
        for banco in dc.bancos_para_lancar(parte):
            valores = dict(por_banco.get(banco, {}))
            cartoes.append(
                cartao_banco(
                    dc.rotulo_banco(banco, _revenda()),
                    [
                        linha_saldo(rotulo, valores.get(chave), sempre_saida=saida)
                        for rotulo, chave, saida in _LINHAS_CARTAO
                    ],
                    sem_extrato=valores.get(dc.ITEM_SALDO_LIBERADO) is None,
                )
            )
        return grade_cartoes(cartoes)

    @reactive.calc
    async def composicao_base() -> pl.DataFrame:
        _revenda()
        dia = _dia_do_historico()
        if dia is not None:
            try:
                return await asyncio.to_thread(dc.composicao_do_retrato, dia)
            except Exception as erro:
                print(f"Historico: a Composicao de {dia:%d/%m/%Y} falhou -- {type(erro).__name__}: {str(erro)[:200]}")
                return pl.DataFrame()
        return await asyncio.to_thread(dc.composicao)

    @reactive.calc
    async def matriz_composicao():
        return dc.matriz(await composicao_base(), _revenda())

    BANCOS_SEM_AJUSTE_NO_SALDO = {"bradesco_6", "bradesco_7", "bradesco_8"}

    @reactive.calc
    async def selecionados_pendentes() -> list[dict]:
        marcacoes_versao()
        if _dia_do_historico() is not None:
            return []

        marcas = manual_arquivo.marcacoes_por_chave()
        base = await pagar_com_partes()
        if base.is_empty():
            return []
        marcados = cp.marcados_para_pagar(base, marcas)
        if not marcados:
            return []
        da_base = {
            linha["id_unico"]: linha
            for linha in base.iter_rows(named=True)
            if linha.get("id_unico") and not eh_parte(linha["id_unico"])
        }
        editados = manual_arquivo.pagamentos_por_titulo()
        ja_contados = _pagamentos_ja_na_base()
        bancos_revenda = await _bancos_da_revenda()
        do_cartao = dc.titulos_do_cartao()
        limites: dict = {}
        selecionados: list[dict] = []
        for linha in base.iter_rows(named=True):
            ident = linha.get("id_unico")
            if not ident or ident not in marcados or ident in ja_contados:
                continue
            if cp.na_gestao(ident, linha, marcas, da_base.get(base_do(ident))):
                continue
            edicao = editados.get(ident) or {}
            rotulo = (
                edicao.get("banco")
                or linha.get("banco")
                or dc.banco_do_cartao(ident, bancos_revenda, do_cartao)
                or _banco_padrao(bancos_revenda, linha.get("REVENDA"))
            )
            pago = edicao.get("valor_pago") or linha.get("valor_pago")
            juros = edicao.get("juros") or linha.get("juros") or 0
            selecionados.append(
                {
                    "id": ident,
                    "chave": dc.chave_do_rotulo(rotulo, _revenda()),
                    "banco": rotulo,
                    "valor": cp.valor_pago_pendente(
                        linha.get("PGMOVMOV_VALOR") or 0,
                        pago,
                        juros,
                        linha.get("pagou") or "",
                        _desconto_ate(
                            linha.get("REVENDA"), limites, linha.get("PGMOVMOV_CGC"), linha.get("PGMOVMOV_VALOR")
                        ),
                    ),
                }
            )
        return selecionados

    @reactive.poll(dc.versao_dados_manuais, 3)
    def _dados_manuais_no_disco():
        return dc.versao_dados_manuais()

    @reactive.calc
    async def ajuste_dados_manuais() -> dict:
        _dados_manuais_no_disco()
        if _dia_do_historico() is not None:
            return {}
        base = await composicao_base()
        return await asyncio.to_thread(dc.ajuste_dos_dados_manuais, base, _revenda())

    @reactive.calc
    async def ajuste_pendente() -> dict:
        fora: dict[str, float] = {}
        for linha in await selecionados_pendentes():
            chave = linha["chave"]
            if not chave:
                continue
            fora[chave] = fora.get(chave, 0.0) - linha["valor"]
        return fora

    def _pagamentos_ja_na_base() -> set:
        try:
            base = d.filtrar_por_revenda(d.pagamentos_manuais(), _revenda())
        except Exception:
            return set()
        if base.is_empty() or "id_unico" not in base.columns:
            return set()
        pronto = pl.lit(False)
        for coluna in ("pagar", "pagou"):
            if coluna in base.columns:
                pronto = pronto | (pl.col(coluna) == "Sim")
        return set(base.filter(pronto)["id_unico"].to_list())

    celulas_somadas = reactive.value(frozenset())

    @reactive.effect
    @reactive.event(input.celula_composicao)
    async def _alternar_celula_composicao():
        pedido = input.celula_composicao() or {}
        tabela, _naturezas, chaves, _aj = await matriz_ajustada()
        try:
            linha, coluna = int(pedido.get("linha")), int(pedido.get("coluna"))
        except (TypeError, ValueError):
            return
        colunas = list(tabela.columns)
        if not (0 <= linha < len(chaves) and 0 <= coluna < len(colunas)):
            return
        if chaves[linha] not in SALDOS_FINAIS or colunas[coluna] == COLUNA_ITEM:
            return
        with reactive.isolate():
            atual = set(celulas_somadas())
        atual ^= {(chaves[linha], colunas[coluna])}
        celulas_somadas.set(frozenset(atual))

    @reactive.effect
    async def _destacar_celulas_composicao():
        somadas = celulas_somadas()
        tabela, _naturezas, chaves, _aj = await matriz_ajustada()
        colunas = list(tabela.columns)
        await session.send_custom_message(
            "ppfCelulasSomadas",
            {
                "grade": session.ns("grade_composicao"),
                "clique": session.ns("celula_composicao"),
                "somaveis": [i for i, chave in enumerate(chaves) if chave in SALDOS_FINAIS],
                "celulas": [[chaves.index(k), colunas.index(c)] for k, c in somadas if k in chaves and c in colunas],
            },
        )

    @reactive.calc
    async def matriz_ajustada():
        tabela, naturezas, chaves = await matriz_composicao()
        ajuste = await ajuste_pendente()
        manual = await ajuste_dados_manuais()
        if tabela.is_empty() or not (ajuste or manual):
            return tabela, naturezas, chaves, set()

        rotulo_para_chave = {}
        for coluna in tabela.columns:
            if coluna == COLUNA_ITEM:
                continue
            rotulo_para_chave[coluna] = dc.chave_do_rotulo(coluna, _revenda())

        ajustadas = set()
        for posicao, chave_item in enumerate(chaves):
            for coluna, chave_banco_col in rotulo_para_chave.items():
                delta = manual.get((chave_item, chave_banco_col), 0.0)
                if chave_item in ("total_despesas_sugeridas", "saldo_final_liberado", "saldo_uso_especial") and not (
                    chave_item == "saldo_final_liberado" and chave_banco_col in BANCOS_SEM_AJUSTE_NO_SALDO
                ):
                    delta += ajuste.get(chave_banco_col) or 0.0
                if not delta:
                    continue
                atual = tabela[coluna][posicao]
                novo = (atual or 0.0) + delta
                tabela = tabela.with_columns(
                    pl.when(pl.int_range(pl.len()) == posicao)
                    .then(pl.lit(novo))
                    .otherwise(pl.col(coluna))
                    .alias(coluna)
                )
                ajustadas.add((posicao, coluna))
        return tabela, naturezas, chaves, ajustadas

    _composicao_na_tela = {"assinatura": None}

    @render.ui
    async def tabela_composicao():
        _composicao_na_tela["assinatura"] = None
        tabela, _naturezas, _chaves = await matriz_composicao()
        if tabela.is_empty():
            base = await composicao_base()
            dia = _dia_do_historico()
            if dia is not None and dc.da_revenda(base, _revenda()).is_empty():
                return ui.p(f"Sem retrato da Composição em {dia:%d/%m/%Y}.")
            if not base.is_empty() and base["REVENDA"].n_unique() > 1:
                return ui.p(
                    "A Composição Financeira é de uma revenda por vez — ela é a "
                    "matriz item × banco de um dia. Abra a tela com a revenda na "
                    "URL (por exemplo ?REVENDA=NATAL)."
                )
            if dia is not None:
                return ui.p(f"Sem retrato da Composição em {dia:%d/%m/%Y}.")
            return ui.p("Composição Financeira sem dado no cache: rode scripts/atualiza_composicao.py.")
        return ui.div(
            ui.output_ui("css_largura_composicao"),
            ui.output_data_frame("grade_composicao"),
            class_="ppf-tabela-composicao ppf-tabela-inteira",
        )

    @render.data_frame
    async def grade_composicao():
        tabela, naturezas, chaves, ajustadas = await matriz_ajustada()
        colunas_valor = [c for c in tabela.columns if c != COLUNA_ITEM]
        coluna_caixa = _coluna_do_caixa(colunas_valor, _revenda())

        formatada = tabela.with_columns(
            [
                pl.Series(
                    coluna,
                    [
                        _celula_composicao(
                            tabela[coluna][posicao],
                            mostra_zero=(coluna == coluna_caixa and chave in ITENS_ZERO_NO_CAIXA),
                        )
                        for posicao, chave in enumerate(chaves)
                    ],
                    dtype=pl.Utf8,
                )
                for coluna in colunas_valor
            ]
        )

        fabrica = await credito_fabrica_faixa()
        celulas_fabrica: list[tuple[int, str, str]] = []
        if fabrica is not None and "credito_fabrica" in chaves:
            linha_fab = chaves.index("credito_fabrica")
            _credito, usado, sobra = fabrica
            com_valor = [n for n, c in enumerate(colunas_valor) if (v := tabela[c][linha_fab]) is not None and v != 0]
            inicio = (com_valor[-1] + 1) if com_valor else 0
            textos = [
                (f"Crédito Utilizado: {_reais(usado)}", COR_FABRICA_USADO),
                (f"Crédito Disponível: {_reais(sobra)}", COR_FABRICA_SOBRA),
            ]
            for passo, (texto, cor) in enumerate(textos):
                n = inicio + passo
                if n >= len(colunas_valor):
                    break
                coluna = colunas_valor[n]
                valores = formatada[coluna].to_list()
                valores[linha_fab] = texto
                formatada = formatada.with_columns(pl.Series(coluna, valores, dtype=pl.Utf8))
                celulas_fabrica.append((linha_fab, coluna, cor))

        estilos = []
        linha_estoque = 1 if chaves and chaves[0] == "credito_fabrica" else 0
        for posicao, chave in enumerate(chaves):
            no_dom = posicao + 1 + (1 if posicao >= linha_estoque else 0)
            if no_dom % 2 == 0:
                estilos.append({"rows": [posicao], "cols": None, "style": {"background-color": _FUNDO_ZEBRA}})
            if chave == "credito_fabrica":
                estilos.append({"rows": [posicao], "cols": None, "style": {"background-color": _FUNDO_CREDITO_FABRICA}})
            if chave in SAIDAS_EM_DESTAQUE:
                estilos.append({"rows": [posicao], "cols": [COLUNA_ITEM], "style": dict(_DESTAQUE_SAIDA)})
            destaque, saida = [], []
            for coluna in colunas_valor:
                valor = tabela[coluna][posicao]
                if valor is None or valor == 0:
                    if coluna == coluna_caixa and chave in ITENS_ZERO_NO_CAIXA:
                        destaque.append(coluna)
                    continue
                if chave in SAIDAS_EM_DESTAQUE or valor < 0:
                    saida.append(coluna)
                elif chave in SALDOS_EM_NEGRITO:
                    destaque.append(coluna)
            if saida:
                estilos.append({"rows": [posicao], "cols": saida, "style": dict(_DESTAQUE_SAIDA)})
            if destaque:
                estilos.append({"rows": [posicao], "cols": destaque, "style": dict(_DESTAQUE)})
        for linha_fab, coluna, cor in celulas_fabrica:
            estilos.append(
                {
                    "rows": [linha_fab],
                    "cols": [coluna],
                    "style": {"color": cor, "font-weight": "bold", "text-align": "left", "white-space": "nowrap"},
                }
            )

        assinatura = (tuple(formatada.columns), formatada.rows(), repr(estilos))
        if assinatura == _composicao_na_tela["assinatura"]:
            req(False, cancel_output=True)
        _composicao_na_tela["assinatura"] = assinatura

        return render.DataTable(
            formatada.pipe(para_pandas),
            styles=estilos,
            height=_ALTURA_COMPOSICAO,
            summary=False,
            filters=False,
            selection_mode="none",
        )

    @render.ui
    async def css_largura_composicao():
        tabela, _naturezas, chaves = await matriz_composicao()
        larguras = [
            ColunaLargura(
                c,
                _LARGURA_ITEM_COMPOSICAO if c == COLUNA_ITEM else _LARGURA_BANCO_COMPOSICAO,
            )
            for c in tabela.columns
        ]
        regras = [gerar_css_larguras(f"#{session.ns('grade_composicao')}", larguras)]

        alvo = "total_despesas_sugeridas"
        if alvo in chaves and not tabela.is_empty():
            abaixo = len(chaves) - chaves.index(alvo) - 1
            regras.append(".ppf-matriz-com-olho { --ppf-olho-abaixo: " + str(abaixo) + "; }")
            regras.append(
                f"#{session.ns('grade_composicao')} table tbody "
                f"tr:nth-child({chaves.index(alvo) + 1}) td:last-child "
                "{ padding-right: 22px !important; }"
            )
        else:
            regras.append(".ppf-matriz-com-olho .ppf-matriz-olho { display: none; }")
        return ui.tags.style("\n".join(regras))

    @render.ui
    async def card_soma():
        tabela, _naturezas, chaves, _aj = await matriz_ajustada()
        linhas = [(k, c) for k, c in celulas_somadas() if k in chaves and c in tabela.columns]
        total = 0.0
        for chave, coluna in linhas:
            valor = tabela[coluna][chaves.index(chave)]
            if valor is not None:
                total += float(valor)

        classe = "ppf-999-soma-valor"
        if not linhas:
            classe += " ppf-999-soma-vazia"
        elif total < 0:
            classe += " ppf-999-soma-negativo"
        return ui.TagList(
            ui.div(_reais(total), class_=classe),
            ui.div(f"{len(linhas)} selecionada(s)", class_="ppf-999-soma-meta"),
        )

    @reactive.calc
    async def despesas_fabrica_do_dia() -> float:
        total = 0.0

        base = await pagar_com_partes()
        if not base.is_empty() and "banco" in base.columns:
            hoje = date.today()
            recorte = base
            if "data_pagamento" in recorte.columns:
                recorte = recorte.filter(pl.col("data_pagamento").cast(pl.Date, strict=False) == hoje)
            for linha in recorte.iter_rows(named=True):
                if not cp.e_banco_fabrica(linha.get("banco")):
                    continue
                if str(linha.get("pagar") or "").strip().lower() != "sim":
                    continue
                if str(linha.get("pagou") or "").strip().lower() == "sim":
                    continue
                total += float(linha.get("valor_pago") or 0.0)

        for item in await selecionados_pendentes():
            if cp.e_banco_fabrica(item.get("banco")):
                total += float(item.get("valor") or 0.0)

        return abs(total)

    @reactive.calc
    async def credito_fabrica_faixa():
        tabela, _naturezas, chaves, _ajuste = await matriz_ajustada()
        if tabela.is_empty() or "credito_fabrica" not in chaves:
            return None
        linha = chaves.index("credito_fabrica")
        credito = 0.0
        tem_valor = False
        for coluna in tabela.columns:
            if coluna == COLUNA_ITEM:
                continue
            valor = tabela[coluna][linha]
            if valor is not None:
                credito += float(valor)
                tem_valor = True
        usado = await despesas_fabrica_do_dia()
        if not tem_valor and not usado:
            return None
        return credito, usado, credito - usado

    mostra_999 = reactive.value(True)

    @reactive.effect
    @reactive.event(input.toggle_999)
    def _alternar_999():
        mostra_999.set(not mostra_999())

    @render.ui
    def icone_999():
        return icon_svg("eye" if mostra_999() else "eye-slash", a11y="deco")

    @reactive.calc
    async def tabela_999_pronta():
        todo_extrato = await extrato()
        saldo_999, batida, geral = await asyncio.gather(
            asyncio.to_thread(d.saldo_banco_999),
            asyncio.to_thread(d.batida_diaria),
            asyncio.to_thread(d.batida_diaria_geral),
        )
        batida = d.filtrar_por_revenda(batida, _revenda())
        geral = d.filtrar_por_revenda(geral, _revenda())
        dia = d.data_referencia_999(
            todo_extrato,
            _dia_do_historico(),
            saldo_999=d.filtrar_por_revenda(saldo_999, _revenda()),
            batida=pl.concat([batida, geral], how="diagonal_relaxed"),
        )
        base = d.extrato_caixa_999(todo_extrato, dia)
        if base.is_empty():
            return _linhas_da_batida(dia, batida, geral)

        base = base.with_columns(pl.col("PGMOVBAN_HISTORICO").is_in(PRIORIDADE_999).alias("_PRIOR")).sort(
            ["_PRIOR", "DATA", "PGMOVBAN_VALORL"], descending=[False, True, False], nulls_last=True
        )

        revenda_linha = pl.col("REVENDA").cast(pl.Utf8) if "REVENDA" in base.columns else pl.lit(_revenda())
        pronta = base.select(
            pl.col("DATA").dt.strftime("%d/%m/%Y").fill_null("").alias("Data"),
            pl.col("PGMOVBAN_HISTORICO").fill_null("").alias("Descrição"),
            pl.col("PGMOVBAN_NRDOC_EXTENSO").fill_null("").alias("Informativo ERP"),
            pl.col("PGMOVBAN_VALORL").cast(pl.Float64, strict=False).alias("_valor"),
            pl.col("_PRIOR"),
            revenda_linha.alias("_REVENDA"),
        )

        return pl.concat([pronta, _linhas_da_batida(dia, batida, geral)], how="vertical_relaxed")

    def _linhas_da_batida(dia, batida: pl.DataFrame, geral: pl.DataFrame) -> pl.DataFrame:
        vazio = pl.DataFrame(
            schema={
                "Data": pl.Utf8,
                "Descrição": pl.Utf8,
                "Informativo ERP": pl.Utf8,
                "_valor": pl.Float64,
                "_PRIOR": pl.Boolean,
                "_REVENDA": pl.Utf8,
            }
        )
        linha = batida_do_dia(dia, batida, geral)
        if linha is None:
            return vazio
        registros = []
        for coluna, rotulo in CAMPOS_BATIDA_999:
            valor = linha.get(coluna)
            if valor is None or float(valor) == 0:
                continue
            registros.append(
                {
                    "Data": dia.strftime("%d/%m/%Y"),
                    "Descrição": rotulo,
                    "Informativo ERP": "",
                    "_valor": abs(float(valor)),
                    "_PRIOR": True,
                    "_REVENDA": _revenda(),
                }
            )
        if not registros:
            return vazio
        return pl.DataFrame(registros).select(vazio.columns)

    @render.ui
    async def corpo_tabela_999():
        if not mostra_999():
            return ui.div()
        pronta = await tabela_999_pronta()
        if pronta.is_empty():
            _linhas_999.clear()
            return ui.p("Sem lançamento no caixa 999.")
        anexos_999_mudaram()

        nomes_por_revenda: dict = {}
        _linhas_999.clear()
        corpo = []
        linhas = list(pronta.iter_rows(named=True))
        da_rede = await _comprovantes_da_rede_999(linhas)
        ve_a_pre_auditoria = _pode(CHAVE_VER_PRE_AUDITORIA)
        pre_auditorias_999 = await asyncio.to_thread(d.pre_auditoria_do_999) if ve_a_pre_auditoria else {}
        regras_do_farol = dados_farol_999.configuracao()
        for i, r in enumerate(linhas):
            revenda_linha = r.get("_REVENDA") or _revenda()
            if revenda_linha not in nomes_por_revenda:
                nomes_por_revenda[revenda_linha] = await asyncio.to_thread(gravacao.nomes_na_pasta_999, revenda_linha)
            data, desc, doc = r["Data"], r["Descrição"], r["Informativo ERP"]
            _linhas_999.append((data, desc, doc, revenda_linha))
            anexo = ui.div()
            pre_auditoria_da_linha = None
            if doc and i < LINHAS_999_COM_ANEXO:
                achados = gravacao.anexos_999(
                    revenda_linha,
                    data,
                    desc,
                    doc,
                    nomes=nomes_por_revenda[revenda_linha],
                )
                na_rede = None if achados else da_rede.get(i)
                if ve_a_pre_auditoria and not dados_farol_999.fica_de_fora(
                    desc, doc, regras_do_farol["fora_quando_contem"], regras_do_farol["descricoes_fora"]
                ):
                    arquivos_de_agora = [str(gravacao.pasta_999(revenda_linha) / nome) for nome in achados] + (
                        [str(na_rede[0])] if na_rede else []
                    )
                    pre_auditoria_da_linha = _pre_auditoria_do_999(
                        pre_auditorias_999,
                        revenda_linha,
                        _dia_999(data),
                        desc,
                        doc,
                        arquivos_de_agora,
                        f"{' '.join(str(desc).split())} — {' '.join(str(doc).split())}",
                        f"pa999_balao_{i}",
                        session.ns("pa_fechar_baloes"),
                    )
                anexo = ui.div(
                    ui.input_action_button(
                        f"anexo999_{i}",
                        ui.tags.img(src="img/ppf/file-upload-2.svg", alt="Anexar"),
                        class_="ppf-999-anexo-btn",
                        title="Anexar arquivo",
                    ),
                    ui.tags.a(
                        ui.tags.img(src="img/ppf/view.svg", alt="Visualizar"),
                        href=_url_anexos_999_juntos(data, desc, doc, revenda_linha),
                        target="_blank",
                        class_="ppf-999-anexo-ver",
                        title=f"Visualizar os {len(achados)} anexos juntos",
                    )
                    if len(achados) > 1
                    else ui.tags.a(
                        ui.tags.img(src="img/ppf/view.svg", alt="Visualizar"),
                        href=_url_anexo_999(revenda_linha, achados[0]),
                        target="_blank",
                        class_="ppf-999-anexo-ver",
                        title="Visualizar anexo",
                    )
                    if achados
                    else ui.tags.a(
                        ui.tags.img(src="img/ppf/view.svg", alt="Visualizar"),
                        href=_href_da_rede(na_rede[0]),
                        target="_blank",
                        class_="ppf-999-anexo-ver",
                        title=f"Comprovante da pasta do caixa ({na_rede[1]}): {Path(na_rede[0]).name}",
                    )
                    if na_rede
                    else None,
                    class_="ppf-999-anexo",
                )
            valor = r["_valor"]
            corpo.append(
                ui.tags.tr(
                    ui.tags.td(data, class_="ppf-999-data"),
                    ui.tags.td(desc, class_="ppf-999-desc"),
                    ui.tags.td(doc, class_="ppf-999-desc"),
                    ui.tags.td(
                        ui.span("R$", class_="ppf-999-moeda"),
                        ui.span(
                            "" if valor is None else _reais(abs(valor)).replace("R$", "").strip(),
                            class_="ppf-999-numero",
                        ),
                        class_="ppf-999-valor",
                    ),
                    ui.tags.td(anexo, class_="ppf-999-anexos"),
                    ui.tags.td(pre_auditoria_da_linha, class_="ppf-999-pre-auditoria") if ve_a_pre_auditoria else None,
                    class_="ppf-999-batida" if r["_PRIOR"] else "ppf-999-linha",
                )
            )
        return ui.div(
            ui.tags.table(
                ui.tags.thead(
                    ui.tags.tr(
                        *[ui.tags.th(c, class_="ppf-999-anexos" if c == "Anexos" else None) for c in COLUNAS_999],
                        ui.tags.th("", class_="ppf-999-pre-auditoria") if ve_a_pre_auditoria else None,
                    )
                ),
                ui.tags.tbody(*corpo),
                class_="ppf-tabela-999-html",
            ),
            class_="ppf-tabela-999 ppf-tabela-inteira",
        )

    _linhas_999: list = []
    linha_999_aberta = reactive.value(("", "", "", ""))
    anexos_999_mudaram = reactive.value(0)
    anexo_999_a_excluir = reactive.value("")

    def _entregar_anexo_999(request):
        from starlette.responses import FileResponse, PlainTextResponse

        revenda_linha = request.query_params.get("rev", "")
        nome = request.query_params.get("nome", "")
        if not nome or revenda_linha not in {r for *_x, r in _linhas_999}:
            return PlainTextResponse("anexo nao encontrado", status_code=404)
        pasta = gravacao.pasta_999(revenda_linha)
        alvo = (pasta / Path(nome).name).resolve()
        if not alvo.is_relative_to(pasta.resolve()) or not alvo.is_file():
            return PlainTextResponse("anexo nao encontrado", status_code=404)
        return FileResponse(
            alvo,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{alvo.name}"'},
        )

    url_anexo_999 = session.dynamic_route("ver_anexo_999", _entregar_anexo_999)
    _emenda_999 = "&" if "?" in url_anexo_999 else "?"

    def _url_anexo_999(revenda_linha: str, nome: str) -> str:
        return url_anexo_999 + _emenda_999 + "rev=" + quote(str(revenda_linha)) + "&nome=" + quote(nome)

    async def _entregar_anexos_999_juntos(request):
        from starlette.responses import FileResponse, PlainTextResponse

        chave = tuple(request.query_params.get(campo, "") for campo in ("data", "desc", "doc", "rev"))
        desenhadas = {tuple(str(parte or "") for parte in linha) for linha in _linhas_999}
        if chave not in desenhadas:
            return PlainTextResponse("anexo nao encontrado", status_code=404)
        data, desc, doc, revenda_linha = chave
        pasta = gravacao.pasta_999(revenda_linha)
        nomes = await asyncio.to_thread(gravacao.anexos_999, revenda_linha, data, desc, doc)
        try:
            juntado = await asyncio.to_thread(juntar_pdf.juntar, [pasta / Path(nome).name for nome in nomes])
        except ValueError:
            return PlainTextResponse("anexo nao encontrado", status_code=404)
        return FileResponse(
            juntado,
            media_type="application/pdf",
            filename=juntado.name,
            content_disposition_type="inline",
            headers={"Cache-Control": "no-store"},
        )

    url_anexos_999_juntos = session.dynamic_route("ver_anexos_999_juntos", _entregar_anexos_999_juntos)
    _emenda_999_juntos = "&" if "?" in url_anexos_999_juntos else "?"

    def _url_anexos_999_juntos(data, desc, doc, revenda_linha) -> str:
        return (
            url_anexos_999_juntos
            + _emenda_999_juntos
            + "data="
            + quote(str(data or ""))
            + "&desc="
            + quote(str(desc or ""))
            + "&doc="
            + quote(str(doc or ""))
            + "&rev="
            + quote(str(revenda_linha or ""))
        )

    _rede_999_lista: list = []

    def _dia_999(texto) -> date | None:
        try:
            return datetime.strptime(str(texto), "%d/%m/%Y").date()
        except (TypeError, ValueError):
            return None

    async def _comprovantes_da_rede_999(linhas: list[dict]) -> dict:
        manuais, do_atualizar = manual_arquivo.vinculos_999(), d.vinculos_999()
        saida, grupos, usados = {}, {}, set()
        for i, r in enumerate(linhas[:LINHAS_999_COM_ANEXO]):
            doc, dia = r["Informativo ERP"], _dia_999(r["Data"])
            if not doc or dia is None:
                continue
            revenda_linha = r.get("_REVENDA") or _revenda()
            chave = manual_arquivo.chave_999(revenda_linha, dia, r["Descrição"], doc)
            if chave in manuais:
                v = manuais[chave]
                saida[i] = (v["caminho"], f"vinculado por {cp.nome_legivel(v['vinculado_por'])}")
            elif chave in do_atualizar:
                v = do_atualizar[chave]
                saida[i] = (
                    v["caminho"],
                    "achado pelo conteúdo" if v.get("origem") == "conteudo" else "achado pelo nome",
                )
            else:
                grupos.setdefault((revenda_linha, dia), []).append((i, doc))
                continue
            usados.add(str(saida[i][0]))
        for (revenda_linha, dia), docs in grupos.items():
            try:
                arquivos, _onde = await asyncio.to_thread(rede_documentos.arquivos_do_caixa, revenda_linha, dia)
            except Exception as erro:
                print(f"Diario: pasta do caixa de {revenda_linha} em {dia} -- {erro}")
                continue
            livres = {
                a.nome: a
                for a in arquivos
                if str(a.caminho) not in usados and not rede_documentos.eh_backup_do_xml(a.nome)
            }
            for i, nome in rede_documentos.casar_caixa(docs, list(livres)).items():
                saida[i] = (str(livres[nome].caminho), "achado pelo nome")
        return saida

    @render.ui
    async def rede_999():
        anexos_999_mudaram()
        data, desc, doc, revenda_linha = linha_999_aberta()
        dia = _dia_999(data)
        if not doc or dia is None:
            return ui.div()
        try:
            arquivos, onde = await asyncio.to_thread(rede_documentos.arquivos_do_caixa, revenda_linha, dia)
            pastas, _onde = await asyncio.to_thread(rede_documentos.pastas_do_caixa, revenda_linha, dia)
        except Exception as erro:
            return ui.p("Não deu para ler a pasta do caixa: " + str(erro)[:120], class_="ppf-modal-lista-vazia")
        chave = manual_arquivo.chave_999(revenda_linha, dia, desc, doc)
        manual, do_atualizar = manual_arquivo.vinculos_999().get(chave), d.vinculos_999().get(chave)
        ligado = str(manual["caminho"]) if manual else None
        achado = str(do_atualizar["caminho"]) if do_atualizar and not manual else None
        arquivos = [a for a in arquivos if not rede_documentos.eh_backup_do_xml(a.nome)]
        ordem = sorted(
            arquivos,
            key=lambda a: (
                str(a.caminho) != ligado,
                str(a.caminho) != achado,
                not rede_documentos.casa_no_caixa(doc, a.nome),
                -rede_documentos.parecido_no_caixa(doc, a.nome),
                a.nome,
            ),
        )[:ARQUIVOS_999]
        _rede_999_lista[:] = [str(a.caminho) for a in ordem]
        rodape = ui.div(
            *[ui.div(ui.tags.code(str(p), class_="ppf-rede-caminho"), class_="ppf-rede-pasta") for p in pastas],
            ui.div(
                ui.tags.code(str(onde.caminho) if onde.caminho else "-", class_="ppf-rede-caminho", title=onde.motivo),
                class_="ppf-rede-pasta ppf-rede-pasta-falta",
            )
            if not pastas
            else None,
            ui.input_action_button(
                "rede999_reler",
                "Procurar de novo",
                class_="ppf-modal-btn ppf-modal-btn-tipo",
                title="A rede é lida com cache; isto força uma leitura nova",
            ),
            class_="ppf-rede-rodape",
        )
        if not onde.achou:
            return ui.div(ui.p(onde.motivo, class_="ppf-modal-lista-vazia"), rodape)
        if not ordem:
            return ui.div(ui.p("Nenhum PDF na pasta do caixa deste dia.", class_="ppf-modal-lista-vazia"), rodape)
        itens = []
        for i, a in enumerate(ordem):
            caminho = str(a.caminho)
            if caminho == ligado:
                selo = f"vinculado por {cp.nome_legivel(manual['vinculado_por'])}"
            elif caminho == achado:
                selo = "achado pelo conteúdo" if do_atualizar.get("origem") == "conteudo" else "achado pelo nome"
            elif not manual and not do_atualizar and rede_documentos.casa_no_caixa(doc, a.nome):
                selo = "achado pelo nome"
            elif rede_documentos.parecido_no_caixa(doc, a.nome) >= 0.5:
                selo = "parecido"
            else:
                selo = None
            itens.append(
                ui.tags.li(
                    ui.div(
                        ui.tags.img(src=an.ICONE_PDF, class_="ppf-arquivo-icone", alt=""),
                        ui.span(a.nome, class_="ppf-modal-lista-nome", title=caminho),
                        ui.span(selo, class_="ppf-modal-lista-tipo") if selo else None,
                        class_="ppf-modal-lista-arquivo",
                    ),
                    ui.div(
                        _olho_da_rede(caminho),
                        ui.input_action_button(
                            "rede999_desvincular",
                            "Desvincular",
                            class_="ppf-modal-btn ppf-modal-btn-tipo",
                            title="Tira o vínculo; o arquivo continua na rede",
                        )
                        if caminho == ligado
                        else ui.input_action_button(
                            f"rede999_vincular_{i}",
                            "Vincular",
                            class_="ppf-modal-btn ppf-modal-btn-tipo",
                            title="Aponta para o arquivo na rede, sem ocupar disco",
                        ),
                        class_="ppf-modal-lista-acoes",
                    ),
                )
            )
        return ui.div(ui.tags.ul(*itens, class_="ppf-modal-lista"), rodape)

    @_delegado
    def _vincular_999():
        clicados = [i for i in range(ARQUIVOS_999) if _clicou(f"rede999_vincular_{i}")]
        desvincular = _clicou("rede999_desvincular")
        if not clicados and not desvincular:
            return
        _limpar_recados()
        if _barrar("anexar_999", no_modal=True):
            return
        with reactive.isolate():
            data, desc, doc, revenda_linha = linha_999_aberta()
        dia = _dia_999(data)
        if not doc or dia is None:
            return
        caminho = None
        if clicados:
            if clicados[0] >= len(_rede_999_lista):
                return
            caminho = _rede_999_lista[clicados[0]]
        try:
            manual_arquivo.vincular_999(revenda_linha, dia, desc, doc, caminho, _usuario())
        except Exception as erro:
            _recado_no_modal("Não deu para vincular: " + str(erro)[:120], "error")
            return
        _incrementar(anexos_999_mudaram)
        if caminho and pedir_atualizacao is not None:
            pedir_atualizacao("pre_auditoria_999")
        _recado_no_modal(
            f"{Path(caminho).name} vinculado (o arquivo continua na rede)." if caminho else "Vínculo desfeito.",
            "success",
        )

    @reactive.effect
    @reactive.event(input.rede999_reler)
    async def _reler_999():
        data, _desc, doc, revenda_linha = linha_999_aberta()
        dia = _dia_999(data)
        if not doc or dia is None:
            return
        _limpar_recados()
        try:
            await asyncio.to_thread(rede_documentos.esquecer_caixa, revenda_linha, dia)
        except Exception as erro:
            _recado_no_modal("Não deu para reler a pasta: " + str(erro)[:120], "error")
            return
        _incrementar(anexos_999_mudaram)
        _recado_no_modal(f"Pasta do caixa de {dia:%d/%m/%Y} relida.", "success")

    def _modal_anexos_999(rotulo: str):
        return ui.modal(
            _slot_recados(),
            ui.p(rotulo, class_="fw-bold"),
            ui.div(
                ui.input_file(
                    session.ns("arq_999"),
                    None,
                    button_label=ui.TagList(
                        ui.tags.img(src="img/ppf/file-upload-2.svg", class_="ppf-arquivo-icone", alt=""),
                        "Selecionar arquivo PDF",
                    ),
                    placeholder="Nenhum arquivo selecionado",
                    accept=".pdf",
                    multiple=False,
                    width="100%",
                ),
                class_="ppf-modal-arquivo",
            ),
            ui.h6("Anexos existentes", class_="ppf-modal-lista-titulo"),
            ui.output_ui(session.ns("lista_anexos_999")),
            ui.h6("Na pasta do caixa (rede)", class_="ppf-modal-lista-titulo"),
            ui.output_ui(session.ns("rede_999")),
            title="Enviar Anexo - Pagamento",
            easy_close=True,
            footer=ui.modal_button("Fechar", class_="btn btn-secondary"),
        )

    @_delegado
    def _abrir_anexos_999():
        clicadas = [i for i in range(LINHAS_999_COM_ANEXO) if _clicou(f"anexo999_{i}")]
        for i in clicadas:
            if i >= len(_linhas_999):
                continue
            if _barrar("anexar_999"):
                return
            data, desc, doc, revenda_linha = _linhas_999[i]
            linha_999_aberta.set((data, desc, doc, revenda_linha))
            anexo_999_a_excluir.set("")
            _limpar_recados()
            ui.modal_show(_modal_anexos_999(f"{data} · {desc} · {doc}"))
            return

    @render.ui
    def lista_anexos_999():
        anexos_999_mudaram()
        data, desc, doc, revenda_linha = linha_999_aberta()
        if not doc:
            return ui.div()
        arquivos = gravacao.anexos_999(revenda_linha, data, desc, doc)
        if not arquivos:
            return ui.p("Nenhum anexo encontrado.", class_="ppf-modal-lista-vazia")
        pendente = anexo_999_a_excluir()
        itens = []
        for indice, nome in enumerate(arquivos[:ARQUIVOS_999]):
            acoes = [
                ui.tags.a(
                    ui.tags.img(src="img/ppf/view.svg", alt="Ver"),
                    href=_url_anexo_999(revenda_linha, nome),
                    target="_blank",
                    class_="ppf-modal-btn ppf-modal-btn-ver",
                    title="Visualizar",
                ),
                ui.input_action_button(
                    "excluir_999_" + str(indice),
                    ui.tags.img(src="img/ppf/delete-icon.svg", alt="Excluir"),
                    class_="ppf-modal-btn ppf-modal-btn-excluir",
                    title="Excluir anexo",
                ),
            ]
            itens.append(
                ui.tags.li(
                    ui.div(
                        ui.tags.img(src=an.ICONE_PDF, class_="ppf-arquivo-icone", alt=""),
                        ui.span(nome, class_="ppf-modal-lista-nome"),
                        class_="ppf-modal-lista-arquivo",
                    ),
                    ui.div(*acoes, class_="ppf-modal-lista-acoes"),
                )
            )
        confirmacao = None
        if pendente in arquivos:
            confirmacao = ui.div(
                ui.span(f"Tem certeza que deseja excluir {pendente}?"),
                ui.input_action_button(
                    "confirmar_excluir_999",
                    "Excluir",
                    class_="btn btn-danger btn-sm",
                ),
                ui.input_action_button(
                    "cancelar_excluir_999",
                    "Cancelar",
                    class_="btn btn-secondary btn-sm",
                ),
                class_="ppf-modal-confirmar",
            )
        return ui.TagList(ui.tags.ul(*itens, class_="ppf-modal-lista"), confirmacao)

    @_delegado
    def _pedir_exclusao_999():
        data, desc, doc, revenda_linha = linha_999_aberta()
        if not doc:
            return
        clicados = [indice for indice in range(ARQUIVOS_999) if _clicou("excluir_999_" + str(indice))]
        for indice in clicados:
            arquivos = gravacao.anexos_999(revenda_linha, data, desc, doc)
            if indice < len(arquivos):
                anexo_999_a_excluir.set(arquivos[indice])
            return

    @_delegado
    def _confirmar_exclusao_999():
        if _clicou("cancelar_excluir_999"):
            anexo_999_a_excluir.set("")
            return
        if not _clicou("confirmar_excluir_999"):
            return
        with reactive.isolate():
            nome = anexo_999_a_excluir()
            _data, _desc, _doc, revenda_linha = linha_999_aberta()
        if not nome:
            return
        _limpar_recados()
        if _barrar("anexar_999", no_modal=True):
            return
        anexo_999_a_excluir.set("")
        if gravacao.excluir_anexo_999(revenda_linha, nome):
            _incrementar(anexos_999_mudaram)
            _recado_no_modal("Anexo excluído.", "success")
        else:
            _recado_no_modal("Arquivo não encontrado.", "error")

    @reactive.effect
    @reactive.event(input.arq_999)
    def _receber_anexo_999():
        enviados = input.arq_999()
        data, desc, doc, revenda_linha = linha_999_aberta()
        if not enviados or not doc:
            return
        _limpar_recados()
        if _barrar("anexar_999", no_modal=True):
            return
        for arquivo in enviados:
            if not str(arquivo["name"]).lower().endswith(".pdf"):
                _recado_no_modal("Apenas arquivos PDF são permitidos.", "error")
                return
            try:
                gravacao.guardar_anexo_999(revenda_linha, data, desc, doc, arquivo["datapath"])
            except Exception as erro:
                _recado_no_modal("Não deu para anexar: " + str(erro)[:120], "error")
                return
        _incrementar(anexos_999_mudaram)
        if pedir_atualizacao is not None:
            pedir_atualizacao("pre_auditoria_999")
        _recado_no_modal("Anexo enviado com sucesso!", "success")

    _COLUNAS_VALES = (
        ("DATA_CAIXA", "Data Caixa", "data"),
        ("DATA", "Data Vale", "data"),
        ("DESCRICAO", "Descrição", "texto"),
        ("VALOR", "Valor", "valor"),
        ("RESPONSAVEL", "Responsável", "texto"),
    )
    _COLUNAS_MANUAIS = (
        ("data_vencimento", "Vencimento", "data"),
        ("razao_social", "Fornecedor", "texto"),
        ("num_doc", "Documento", "texto"),
        ("tipo_doc", "Tipo Doc", "texto"),
        ("cnpj", "CNPJ", "texto"),
        ("descricao_despesa", "Tipo Fornecedor", "texto"),
        ("valor_original", "Valor", "valor"),
    )
    ordem_vales = reactive.value(("DATA_CAIXA", False))
    ordem_manuais = reactive.value(("data_vencimento", False))

    def _na_ordem(base: pl.DataFrame, colunas: tuple, ordem: tuple) -> pl.DataFrame:
        coluna, desc = ordem
        tipo = {c: t for c, _r, t in colunas}[coluna]
        chave = (
            pl.col(coluna).cast(pl.Utf8).fill_null("").str.to_lowercase()
            if tipo == "texto"
            else pl.col(coluna).cast(pl.Float64, strict=False).fill_null(0)
            if tipo == "valor"
            else pl.col(coluna)
        )
        return base.sort(chave, descending=desc, nulls_last=desc, maintain_order=True)

    def _cabecalho_ordenavel(prefixo: str, colunas: tuple, ordem: tuple) -> list:
        coluna_ativa, desc = ordem
        celulas = []
        for k, (coluna, rotulo, _t) in enumerate(colunas):
            ativa = coluna == coluna_ativa
            seta = ("\u25bc" if desc else "\u25b2") if ativa else "\u21c5"
            celulas.append(
                ui.tags.th(
                    ui.input_action_link(
                        f"{prefixo}_{k}",
                        ui.TagList(rotulo, ui.span(seta, class_="ppf-ordem" + (" ativa" if ativa else ""))),
                    ),
                    class_="ppf-th-ordenar",
                )
            )
        return celulas

    def _ligar_ordem(prefixo: str, colunas: tuple, ordem) -> None:
        @_delegado
        def _ordenar():
            clicadas = [c for k, (c, _r, _t) in enumerate(colunas) if _clicou(f"{prefixo}_{k}")]
            if not clicadas:
                return
            with reactive.isolate():
                atual, desc = ordem()
            ordem.set((clicadas[0], not desc) if clicadas[0] == atual else (clicadas[0], False))

    _ligar_ordem("ord_vale", _COLUNAS_VALES, ordem_vales)
    _ligar_ordem("ord_man", _COLUNAS_MANUAIS, ordem_manuais)

    def _cabecalho_varias(prefixo: str, colunas: tuple, ordem: tuple) -> list:
        posicao = {coluna: (i, desc) for i, (coluna, desc) in enumerate(ordem)}
        celulas = []
        for k, (coluna, rotulo, _t) in enumerate(colunas):
            i, desc = posicao.get(coluna, (None, False))
            ativa = i is not None
            seta = ("▼" if desc else "▲") if ativa else "⇅"
            celulas.append(
                ui.tags.th(
                    ui.input_action_link(
                        f"{prefixo}_{k}",
                        ui.TagList(
                            rotulo,
                            ui.span(seta, class_="ppf-ordem" + (" ativa" if ativa else "")),
                            ui.span(str(i + 1), class_="ppf-ordem-n") if ativa and len(ordem) > 1 else None,
                        ),
                    ),
                    class_="ppf-th-ordenar",
                    title="Clique para ordenar; clicar em outra coluna desempata pela ordem dos cliques",
                )
            )
        return celulas

    def _ligar_ordem_varias(prefixo: str, colunas: tuple, ordem) -> None:
        @_delegado
        def _ordenar():
            clicadas = [c for k, (c, _r, _t) in enumerate(colunas) if _clicou(f"{prefixo}_{k}")]
            if not clicadas:
                return
            with reactive.isolate():
                atual = list(ordem())
            coluna = clicadas[0]
            posicao = next((i for i, (c, _d) in enumerate(atual) if c == coluna), None)
            if posicao is None:
                atual.append((coluna, False))
            elif not atual[posicao][1]:
                atual[posicao] = (coluna, True)
            else:
                del atual[posicao]
            ordem.set(tuple(atual))

    @reactive.calc
    async def vales_prontos() -> pl.DataFrame:
        base = await asyncio.to_thread(d.vales_provisorios)
        base = d.filtrar_por_revenda(base, _revenda())
        if base.is_empty():
            return base
        return base.sort("DATA", descending=True, nulls_last=True).select(
            "DATA_CAIXA", "DATA", "DESCRICAO", "VALOR", "RESPONSAVEL"
        )

    @render.ui
    async def bloco_vales():
        if not input.analise():
            return None
        return ui.card(
            ui.card_header(
                titulo_secao("Vales Provisórios", emoji="\U0001f4b5"),
                ui.download_button(
                    "baixar_vales",
                    None,
                    icon=icon_svg("file-excel", style="regular"),
                    title="Exportar para Excel",
                    class_="btn-sm ppf-vales-exportar",
                ),
                class_="ppf-999-cabecalho ppf-vales-cabecalho",
            ),
            await _tabela_vales(),
            fill=False,
            class_="ppf-bloco-vales",
        )

    async def _tabela_vales():
        base = await vales_prontos()
        if base.is_empty():
            return ui.p("Nenhum registro de vales provisórios encontrado.")
        base = _na_ordem(base, _COLUNAS_VALES, ordem_vales())

        def _dia(valor):
            return valor.strftime("%d/%m/%Y") if valor else ""

        total = base["VALOR"].cast(pl.Float64, strict=False).sum()
        return ui.div(
            ui.tags.table(
                ui.tags.colgroup(
                    *[
                        ui.tags.col(class_=f"ppf-vales-col-{c}")
                        for c in ("caixa", "vale", "descricao", "valor", "responsavel")
                    ]
                ),
                ui.tags.thead(ui.tags.tr(*_cabecalho_ordenavel("ord_vale", _COLUNAS_VALES, ordem_vales()))),
                ui.tags.tbody(
                    *[
                        ui.tags.tr(
                            ui.tags.td(_dia(r["DATA_CAIXA"]), class_="ppf-999-data"),
                            ui.tags.td(_dia(r["DATA"]), class_="ppf-999-data ppf-vales-data-vale"),
                            ui.tags.td(r["DESCRICAO"] or ""),
                            _celula_contabil(r["VALOR"]),
                            ui.tags.td(r["RESPONSAVEL"] or ""),
                        )
                        for r in base.iter_rows(named=True)
                    ]
                ),
                ui.tags.tfoot(
                    ui.tags.tr(
                        ui.tags.td(f"Total ({base.height} vale{'' if base.height == 1 else 's'})", colspan="3"),
                        _celula_contabil(total),
                        ui.tags.td(""),
                    )
                ),
                class_="ppf-tabela-999-html ppf-tabela-vales",
            ),
            class_="ppf-vales-rolagem",
        )

    @render.download(filename=lambda: f"vales_provisorios_{(_revenda() or '').replace(' ', '_')}.xlsx")
    async def baixar_vales():
        from openpyxl import Workbook
        from openpyxl.styles import Font

        base = await vales_prontos()
        if not base.is_empty():
            base = _na_ordem(base, _COLUNAS_VALES, ordem_vales())
        livro = Workbook()
        folha = livro.active
        folha.title = "Vales Provisórios"
        folha.append(["Data Caixa", "Data Vale", "Descrição", "Valor", "Responsável"])
        for linha in base.iter_rows():
            folha.append(list(linha))
        soma = round(float(base["VALOR"].fill_null(0).sum()), 2) if not base.is_empty() else 0.0
        folha.append([f"Total ({base.height} vales)", None, None, soma, None])
        for celula in folha[1] + folha[folha.max_row]:
            celula.font = Font(bold=True)
        for coluna, largura in zip("ABCDE", (12, 12, 70, 16, 24)):
            folha.column_dimensions[coluna].width = largura
        for linha in folha.iter_rows(min_row=2):
            linha[0].number_format = linha[1].number_format = "DD/MM/YYYY"
            linha[3].number_format = '"R$" #,##0.00'
        folha.freeze_panes = "A2"
        memoria = io.BytesIO()
        livro.save(memoria)
        yield memoria.getvalue()

    @reactive.calc
    async def manuais_prontos() -> pl.DataFrame:
        manuais_versao()
        colunas = [
            "id_unico",
            "data_vencimento",
            "num_doc",
            "num_doc_normalizado",
            "tipo_doc",
            "cnpj",
            "razao_social",
            "descricao_despesa",
            "valor_original",
        ]
        vazia = pl.DataFrame(
            schema={
                c: (pl.Date if c == "data_vencimento" else pl.Float64 if c == "valor_original" else pl.Utf8)
                for c in colunas
            }
        )

        def _so_as_colunas(tabela: pl.DataFrame) -> pl.DataFrame:
            return tabela.select(
                [
                    (
                        pl.col(c).cast(pl.Date, strict=False)
                        if c == "data_vencimento"
                        else pl.col(c).cast(pl.Float64, strict=False)
                        if c == "valor_original"
                        else pl.col(c).cast(pl.Utf8)
                    ).alias(c)
                    if c in tabela.columns
                    else pl.lit(None, dtype=vazia.schema[c]).alias(c)
                    for c in colunas
                ]
            )

        base = await asyncio.to_thread(d.pagamentos_manuais)
        if not base.is_empty():
            base = d.filtrar_por_revenda(base, _revenda())
        if not base.is_empty() and "entrada_manual" in base.columns:
            base = base.filter(pl.col("entrada_manual").cast(pl.Utf8).is_in(["Sim", "1", "S"]))
        else:
            base = base.head(0)
        base, do_arquivo = cp.manuais_em_aberto(
            base, manual_arquivo.entradas_manuais(_revenda()), manual_arquivo.titulos_excluidos()
        )
        partes = [_so_as_colunas(t) for t in (base, do_arquivo) if not t.is_empty()]

        if not partes:
            return vazia
        return pl.concat(partes, how="vertical_relaxed").sort("data_vencimento", descending=True, nulls_last=True)

    @reactive.calc
    async def manuais_ordenados() -> pl.DataFrame:
        base = await manuais_prontos()
        return base if base.is_empty() else _na_ordem(base, _COLUNAS_MANUAIS, ordem_manuais())

    @reactive.calc
    async def manuais_para_tela():
        base = await manuais_ordenados()
        if base.is_empty():
            return base.head(0).pipe(para_pandas)

        def _texto(coluna: str) -> pl.Expr:
            return pl.col(coluna).cast(pl.Utf8).fill_null("")

        return base.select(
            pl.col("data_vencimento").dt.strftime("%d/%m/%Y").fill_null("").alias("Vencimento"),
            _texto("razao_social").alias("Fornecedor"),
            _texto("num_doc").alias("Documento"),
            _texto("tipo_doc").alias("Tipo Doc"),
            _texto("cnpj").alias("CNPJ"),
            _texto("descricao_despesa").alias("Tipo Fornecedor"),
            pl.col("valor_original").map_elements(_reais, return_dtype=pl.Utf8).alias("Valor"),
        ).pipe(para_pandas)

    @render.ui
    async def tabela_manuais():
        crua = await manuais_ordenados()
        pronta = await manuais_para_tela()
        _manuais_atuais.clear()
        if not crua.is_empty():
            for posicao, ident in enumerate(crua["id_unico"].to_list()):
                _manuais_atuais[posicao] = ident
        if pronta.empty:
            return ui.p(
                "Nenhum pagamento manual em aberto nesta revenda.",
                class_="text-muted small mb-0",
            )
        pode_excluir_manual = _pode("excluir_pagamento_manual")
        em_edicao = (_manual_em_edicao() or {}).get("id")
        return ui.div(
            ui.div(
                ui.span("\u2705", class_="ppf-secao-emoji"),
                ui.span("Pagamentos Manuais", class_="ppf-manuais-titulo"),
                ui.span(f"{len(pronta)} em aberto", class_="ms-auto small text-muted"),
                class_="d-flex align-items-center gap-2 mt-2 mb-1",
            ),
            ui.tags.table(
                ui.tags.thead(
                    ui.tags.tr(
                        *_cabecalho_ordenavel("ord_man", _COLUNAS_MANUAIS, ordem_manuais()),
                        ui.tags.th("Ações"),
                    )
                ),
                ui.tags.tbody(
                    *[
                        ui.tags.tr(
                            *[
                                ui.tags.td(
                                    str(pronta.iloc[n][c]),
                                    class_="ppf-manual-valor" if c == "Valor" else None,
                                )
                                for c in pronta.columns
                            ],
                            ui.tags.td(
                                ui.input_action_button(
                                    f"man_excluir_{n}",
                                    icon_svg("trash", a11y="deco"),
                                    class_="ppf-btn-linha ppf-btn-lixeira",
                                    title=("Excluir pagamento manual" if pode_excluir_manual else "Sem permissão"),
                                    disabled=not pode_excluir_manual,
                                )
                                if n < LINHAS_MANUAIS
                                else "",
                                class_="text-center",
                            ),
                            data_linha=str(n),
                            title="Duplo clique para editar",
                            class_="ppf-manual-em-edicao" if _manuais_atuais.get(n) == em_edicao else None,
                        )
                        for n in range(len(pronta))
                    ]
                ),
                class_="ppf-tabela-manuais",
                data_input_editar=session.ns("editar_manual"),
            ),
            class_="ppf-tabela-inteira",
        )

    def _ligar_excluir_manual(posicao: int) -> None:
        @_delegado
        def _excluir():
            if not _clicou(f"man_excluir_{posicao}"):
                return
            if _barrar("excluir_pagamento_manual"):
                return
            ident = _manuais_atuais.get(posicao)
            if not ident:
                return
            _manual_a_excluir.set(ident)
            ui.modal_show(
                ui.modal(
                    ui.p("Deseja excluir este pagamento manual? Isso não pode ser desfeito."),
                    title="Pagamento manual",
                    easy_close=True,
                    footer=ui.div(
                        ui.input_action_button("confirmar_excluir_manual", "Excluir", class_="btn-danger"),
                        ui.modal_button("Cancelar"),
                    ),
                )
            )

    _manual_a_excluir = reactive.value("")

    @reactive.effect
    @reactive.event(input.confirmar_excluir_manual)
    def _confirmar_excluir_manual():
        ui.modal_remove()
        ident = _manual_a_excluir()
        _manual_a_excluir.set("")
        if not ident or _barrar("excluir_pagamento_manual"):
            return
        if (_manual_em_edicao() or {}).get("id") == ident:
            _limpar_campos_manual()
        if True:
            manual_arquivo.excluir_titulo(ident, _revenda() or "", _usuario())
            try:
                gravacao.excluir_pagamento_manual(ident)
            except Exception as erro:
                _avisar(
                    f"Tirado da lista, mas o banco recusou: {str(erro)[:200]}",
                    titulo="Pagamento manual",
                )
            else:
                _avisar(
                    "Pagamento manual excluído.",
                    tipo="success",
                    titulo="Pagamento manual",
                )
            _so_partes["pendente"] = True
            _incrementar(manuais_versao)
            _incrementar(overlay_versao)
            _incrementar(marcacoes_versao)

    for _linha_manual in range(LINHAS_MANUAIS):
        _ligar_excluir_manual(_linha_manual)

    def _lido_manual() -> dict:
        lido = {campo: input[campo]() for campo, _r, _t, _d in CAMPOS_MANUAL}
        if re.sub(r"\D", "", lido["cnpj_manual"] or "") in ("", "0" * 14, "0" * 11):
            lido["cnpj_manual"] = ""
        return lido

    def _recusa_da_edicao(ident: str) -> str | None:
        if ident in manual_arquivo.enviados_em():
            return "Este pagamento manual já foi enviado para pagamento."
        if any(str(parte).startswith(f"{ident}_clone") for parte in manual_arquivo.quem_dividiu()):
            return "Este pagamento manual foi dividido em partes."
        return None

    @reactive.effect
    @reactive.event(input.editar_manual)
    async def _editar_manual():
        if _barrar("lancar_pagamento_manual"):
            return
        try:
            ident = _manuais_atuais.get(int(input.editar_manual()))
            base = await manuais_ordenados()
            achadas = base.filter(pl.col("id_unico") == ident) if ident else base.head(0)
            if achadas.is_empty():
                return
            linha = achadas.row(0, named=True)
            recusa = _recusa_da_edicao(ident)
            if recusa:
                _avisar(f"{recusa} Para mudar, exclua e lance de novo.", titulo="Pagamento manual")
                return
            ui.update_date("data_vencimento_manual", value=linha["data_vencimento"])
            for campo, coluna in (
                ("num_doc_manual", "num_doc"),
                ("tipo_doc_manual", "tipo_doc"),
                ("cnpj_manual", "cnpj"),
                ("razao_social_manual", "razao_social"),
                ("descricao_despesa_manual", "descricao_despesa"),
            ):
                ui.update_text(campo, value=str(linha[coluna] or ""))
            ui.update_text(
                "valor_original_manual",
                value=_reais(linha["valor_original"]) if linha["valor_original"] is not None else "",
            )
            autor = manual_arquivo.ler("entradas_manuais").filter(pl.col("id_unico") == ident)
            _manual_em_edicao.set(
                {
                    "id": ident,
                    "vencimento": linha["data_vencimento"],
                    "rotulo": " · ".join(
                        t
                        for t in (
                            linha["data_vencimento"].strftime("%d/%m/%Y") if linha["data_vencimento"] else "",
                            str(linha["razao_social"] or ""),
                            _reais(linha["valor_original"]),
                        )
                        if t
                    ),
                    "lancado_por": autor["lancado_por"][0] if not autor.is_empty() else None,
                }
            )
        except Exception as erro:
            print(f"Pagamentos Manuais: editar -- {str(erro)[:200]}")

    @render.ui
    def aviso_edicao_manual():
        editando = _manual_em_edicao()
        if not editando:
            return None
        return ui.div(
            ui.tags.b("Editando o pagamento manual: "),
            editando["rotulo"],
            ui.span(" — Enviar grava a alteração; Limpar cancela.", class_="text-muted"),
            class_="ppf-manual-editando small",
        )

    def _recusa_do_vencimento(vencimento) -> str | None:
        editando = _manual_em_edicao()
        if editando and editando.get("vencimento") == vencimento:
            return None
        return manual_com_vencimento_barrado(_usuario(), _revenda(), vencimento)

    @reactive.effect
    @reactive.event(input.gravar_manual)
    def _gravar_manual():
        if _barrar("lancar_pagamento_manual"):
            return
        lido = _lido_manual()
        valor = cp.numero(lido["valor_original_manual"])
        if not lido["data_vencimento_manual"] or not (lido["valor_original_manual"] or "").strip():
            _avisar("Por favor, preencha data e valor", tipo="error", titulo="Pagamento manual")
            return
        if valor is None or valor <= 0:
            _avisar("Por favor, informe um valor válido para o pagamento", tipo="error", titulo="Pagamento manual")
            return
        recusa = _recusa_do_vencimento(lido["data_vencimento_manual"])
        if recusa:
            _avisar(recusa, tipo="error", titulo="Pagamento manual")
            return
        editando = _manual_em_edicao() is not None
        ui.modal_show(
            ui.modal(
                ui.p(
                    "Confirma a alteração deste pagamento manual?"
                    if editando
                    else "Confirma o envio deste pagamento manual?"
                ),
                title="Pagamento manual",
                easy_close=True,
                footer=ui.div(
                    ui.input_action_button("confirmar_manual", "Confirmar", class_="btn-primary"),
                    ui.modal_button("Cancelar"),
                ),
            )
        )

    @reactive.effect
    @reactive.event(input.confirmar_manual)
    def _confirmar_manual():
        ui.modal_remove()
        if _barrar("lancar_pagamento_manual"):
            return
        lido = _lido_manual()
        vencimento = lido["data_vencimento_manual"]
        valor = cp.numero(lido["valor_original_manual"])

        if not vencimento or valor is None:
            _avisar("Preencha data e valor!", tipo="error", titulo="Pagamento manual")
            return
        if valor <= 0:
            _avisar(
                "O valor deve ser maior que zero!",
                tipo="error",
                titulo="Pagamento manual",
            )
            return
        if vencimento < date.today() - timedelta(days=365):
            _avisar(
                "Data de vencimento muito antiga!",
                tipo="error",
                titulo="Pagamento manual",
            )
            return
        recusa = _recusa_do_vencimento(vencimento)
        if recusa:
            _avisar(recusa, tipo="error", titulo="Pagamento manual")
            return

        revenda = _revenda() or ""
        editando = _manual_em_edicao()
        if editando:
            _gravar_edicao_manual(editando, revenda, lido, vencimento, valor)
            return
        ident = gravacao.id_entrada_manual(
            revenda,
            vencimento,
            lido["num_doc_manual"],
            lido["cnpj_manual"],
            lido["razao_social_manual"],
            lido["tipo_doc_manual"],
            lido["descricao_despesa_manual"],
            valor,
            datetime.now(),
        )
        if manual_arquivo.id_ja_lancado(ident):
            _avisar(
                "Já existe um pagamento manual com os mesmos dados!",
                titulo="Pagamento manual",
            )
            return

        doc_norm = cp.documento_normalizado(lido["num_doc_manual"])
        try:
            manual_arquivo.lancar_entrada_manual(
                ident,
                revenda,
                data_vencimento=vencimento,
                num_doc=lido["num_doc_manual"],
                num_doc_normalizado=doc_norm,
                tipo_doc=lido["tipo_doc_manual"],
                cnpj=lido["cnpj_manual"],
                razao_social=lido["razao_social_manual"],
                descricao_despesa=lido["descricao_despesa_manual"],
                valor_original=valor,
                usuario=_usuario(),
            )
        except Exception as erro:
            _avisar(
                f"Falhou ao lançar: {str(erro)[:200]}",
                tipo="error",
                titulo="Pagamento manual",
            )
            return
        try:
            gravacao.lancar_pagamento_manual(
                ident,
                revenda,
                {
                    "data_vencimento": vencimento,
                    "num_doc": lido["num_doc_manual"] or None,
                    "num_doc_normalizado": doc_norm or None,
                    "tipo_doc": lido["tipo_doc_manual"] or None,
                    "cnpj": lido["cnpj_manual"] or None,
                    "razao_social": lido["razao_social_manual"] or None,
                    "descricao_despesa": lido["descricao_despesa_manual"] or None,
                    "valor_original": valor,
                },
            )
        except Exception as erro:
            _avisar(
                f"Lançado na tela, mas o banco recusou: {str(erro)[:200]}",
                titulo="Pagamento manual",
            )
        else:
            _avisar(
                f"Pagamento manual de {_reais(valor)} lançado.",
                tipo="success",
                titulo="Pagamento manual",
            )
        _limpar_campos_manual()
        _so_partes["pendente"] = True
        _incrementar(manuais_versao)
        _incrementar(overlay_versao)
        _incrementar(marcacoes_versao)

    def _gravar_edicao_manual(editando: dict, revenda: str, lido: dict, vencimento: date, valor: float) -> None:
        ident = editando["id"]
        recusa = _recusa_da_edicao(ident)
        if recusa:
            _avisar(f"{recusa} Para mudar, exclua e lance de novo.", titulo="Pagamento manual")
            return
        doc_norm = cp.documento_normalizado(lido["num_doc_manual"])
        campos = {
            "data_vencimento": vencimento,
            "num_doc": lido["num_doc_manual"] or None,
            "num_doc_normalizado": doc_norm or None,
            "tipo_doc": lido["tipo_doc_manual"] or None,
            "cnpj": lido["cnpj_manual"] or None,
            "razao_social": lido["razao_social_manual"] or None,
            "descricao_despesa": lido["descricao_despesa_manual"] or None,
            "valor_original": valor,
        }
        erro_banco = None
        try:
            gravacao.editar_pagamento_manual(ident, revenda, campos)
        except gravacao.EdicaoRecusada as motivo:
            _avisar(f"Não alterado: {motivo}. Para mudar, exclua e lance de novo.", titulo="Pagamento manual")
            return
        except Exception as erro:
            erro_banco = str(erro)[:200]
        try:
            manual_arquivo.lancar_entrada_manual(
                ident,
                revenda,
                **campos,
                usuario=editando.get("lancado_por") or _usuario(),
            )
        except Exception as erro:
            _avisar(f"Falhou ao alterar: {str(erro)[:200]}", tipo="error", titulo="Pagamento manual")
            return
        if erro_banco:
            _avisar(f"Alterado na tela, mas o banco recusou: {erro_banco}", titulo="Pagamento manual")
        else:
            _avisar(f"Pagamento manual alterado ({_reais(valor)}).", tipo="success", titulo="Pagamento manual")
        _limpar_campos_manual()
        _incrementar(manuais_versao)
        _incrementar(overlay_versao)
        _incrementar(marcacoes_versao)

    def _limpar_campos_manual():
        _manual_em_edicao.set(None)
        for campo, _rotulo, tipo, _dica in CAMPOS_MANUAL:
            if tipo == "text":
                ui.update_text(campo, value="")
            else:
                session.send_input_message(campo, {"value": None})

    @reactive.effect
    @reactive.event(input.limpar_manual)
    def _limpar_manual():
        _limpar_campos_manual()

    @render.ui
    async def cartoes_total_pagar():
        filtrado = await pagar_filtrado()
        total = 0.0 if filtrado.is_empty() else float(filtrado["PGMOVMOV_VALOR"].sum() or 0)
        enviados = manual_arquivo.enviados_em()
        marcou_em = {
            r["id_unico"]: r["marcado_em"] for r in manual_arquivo.marcacoes_do_tipo("pagar").iter_rows(named=True)
        }

        def _ja_enviado(ident) -> bool:
            enviado = enviados.get(ident)
            if enviado is None:
                return False
            return marcou_em.get(ident) is None or enviado >= marcou_em[ident]

        pendentes = [p for p in await selecionados_pendentes() if not _ja_enviado(p["id"])]
        marcados = len(pendentes)
        somado = sum(p["valor"] for p in pendentes)
        return ui.TagList(
            ui.div(
                ui.span(
                    f"{marcados} Selecionado{'' if marcados == 1 else 's'}",
                    class_="ppf-cartao-total-titulo",
                ),
                ui.span(_reais(somado), class_="ppf-cartao-total-valor"),
                class_="ppf-cartao-total",
            ),
            ui.div(
                ui.span(_nome_do_subtotal(), class_="ppf-cartao-total-titulo"),
                ui.span(_reais(total), class_="ppf-cartao-total-valor"),
                class_="ppf-cartao-total",
            ),
        )

    def _nome_do_subtotal() -> str:
        intervalo = input.intervalo()
        outros = bool(intervalo and (intervalo[0] or intervalo[1])) or any(
            input[i]() for i, _r, _c in FILTROS_TEXTO if i != "tipo"
        )
        if outros:
            return "Subtotal Geral"
        return {"hoje": "Subtotal Hoje", "vencidos": "Subtotal Vencidos", "a_vencer": "Subtotal a Vencer"}.get(
            input.periodo(), "Subtotal Geral"
        )

    def _sinal_dos_pendentes() -> tuple:
        return _assinatura_de(manual_arquivo.caminho("marcacoes"), manual_arquivo.caminho("pagamentos"))

    @reactive.poll(_sinal_dos_pendentes, 10)
    def _pendentes_no_disco():
        return _sinal_dos_pendentes()

    @render.ui
    async def alerta_pagar():
        marcacoes_versao()
        assinatura_versao()
        _pendentes_no_disco()
        alertas = []
        if _pode("assinar_ppf") and manual_arquivo.assinatura_de(_usuario()) is None:
            alertas.append(
                ui.input_action_button(
                    "assinatura_cadastrar",
                    "\u270d Cadastre sua assinatura",
                    class_="ppf-alerta-pagar ppf-alerta-assinatura",
                    title="Assine pelo celular com um QR code, ou envie uma foto da assinatura",
                )
            )
        if _pode(CHAVE_EDITAR_RESPONSAVEIS):
            alertas.append(
                ui.input_action_button(
                    "permissoes_abrir",
                    ui.TagList(icon_svg("user-gear", a11y="deco"), " Permiss\u00f5es"),
                    class_="ppf-alerta-pagar ppf-alerta-assinatura",
                    title="Quem pode cada coisa no Financeiro, por login",
                )
            )
        if no_acesso_total(_usuario()):
            alertas.append(
                ui.input_action_button(
                    "assinaturas_abrir",
                    ui.TagList(icon_svg("signature", a11y="deco"), " Assinaturas"),
                    class_="ppf-alerta-pagar ppf-alerta-assinatura",
                    title="Apagar a assinatura de alguém, para a pessoa cadastrar de novo",
                )
            )
        if _dia_do_historico() is not None:
            return ui.TagList(*alertas) if alertas else None
        base = await pagar_base()
        if base.is_empty() or "id_unico" not in base.columns:
            return ui.TagList(*alertas) if alertas else None
        hoje = date.today()
        usuario = _usuario()

        if _pode("processar_pagamento"):
            marcas = manual_arquivo.marcacoes_do_tipo("pagar")
            if not marcas.is_empty():
                ids_da_revenda = set(base["id_unico"].drop_nulls().to_list())
                enviados = manual_arquivo.enviados_em()
                ja_na_fila = _pagamentos_ja_na_base()
                pendentes = 0
                for linha in marcas.iter_rows(named=True):
                    quem, quando = linha["marcado_por"], linha["marcado_em"]
                    ident = linha["id_unico"]
                    if (
                        not quem
                        or ident not in ids_da_revenda
                        or not cp.mesma_pessoa(quem, usuario)
                        or quando is None
                        or quando.date() != hoje
                        or ident in ja_na_fila
                    ):
                        continue
                    enviado = enviados.get(ident)
                    if enviado is not None and enviado >= quando:
                        continue
                    pendentes += 1
                if pendentes:
                    alertas.append(
                        ui.div(
                            ui.span("!", class_="ppf-alerta-icone"),
                            ui.span(
                                f"Há {pendentes} pagamento{'s' if pendentes > 1 else ''} "
                                f"pendente{'s' if pendentes > 1 else ''} de envio."
                            ),
                            class_="ppf-alerta-pagar",
                            role="status",
                        )
                    )

        if _pode("auditar_ppf"):
            marcas_auditoria = {
                ident: quem
                for (ident, tipo), quem in manual_arquivo.marcacoes_por_chave().items()
                if tipo == "auditoria"
            }
            do_dia = base.filter(pl.col("DATA").is_in(list(cp.datas_de_hoje(hoje))))
            pendentes = 0
            for linha in do_dia.iter_rows(named=True):
                if str(linha.get("entrada_manual") or "") == "Sim":
                    continue
                if str(linha.get("pagou") or "") == "Sim":
                    continue
                ident = linha.get("id_unico")
                if ident in marcas_auditoria:
                    auditado = bool(marcas_auditoria[ident])
                else:
                    auditado = str(linha.get("auditoria") or "") == "Sim"
                if not auditado:
                    pendentes += 1
            if pendentes:
                rotulo = "documento pendente" if pendentes == 1 else "documentos pendentes"
                alertas.append(
                    ui.div(
                        ui.span("!", class_="ppf-alerta-icone"),
                        ui.span(f"Há {pendentes} {rotulo} de auditoria hoje."),
                        class_="ppf-alerta-pagar ppf-alerta-auditoria",
                        role="status",
                    )
                )
        return ui.TagList(*alertas) if alertas else None

    quadro_aberto = reactive.value(None)
    assinatura_versao = reactive.value(0)
    _foto_ja_lida: dict = {}

    def _endereco_do_quadro(token: str) -> str:
        base = os.getenv("ASSINATURA_URL_BASE", "").strip().rstrip("/")
        if not base:
            raiz = session.root_scope() if hasattr(session, "root_scope") else session
            with reactive.isolate():
                dados = raiz.clientdata
                porta = dados.url_port()
                base = (
                    f"{dados.url_protocol()}//{dados.url_hostname()}"
                    f"{':' + str(porta) if porta else ''}{dados.url_pathname().rstrip('/')}"
                )
        return f"{base}/assinatura/{token}"

    def _novo_quadro(usuario: str) -> None:
        quadro_aberto.set(
            {"url": _endereco_do_quadro(assinatura.novo_link(usuario)), "usuario": usuario, "criado_em": datetime.now()}
        )

    @_delegado
    def _abrir_cadastro_assinatura():
        try:
            if not _pode("assinar_ppf"):
                return
            if _clicou("assinatura_cadastrar"):
                _limpar_recados()
                _novo_quadro(_usuario())
                ui.modal_show(
                    ui.modal(
                        _slot_recados(),
                        ui.output_ui(session.ns("assinatura_corpo")),
                        title="Cadastrar assinatura",
                        easy_close=True,
                        size="m",
                        footer=ui.modal_button("Fechar", class_="btn btn-secondary"),
                    )
                )
            if _clicou("assinatura_refazer"):
                _limpar_recados()
                _novo_quadro(_usuario())
        except Exception as exc:
            _recado_no_modal(f"Não consegui abrir o cadastro da assinatura: {exc}", "error")

    @reactive.effect
    def _esperar_o_celular():
        aberto = quadro_aberto()
        if not aberto or not aberto["url"]:
            return
        try:
            reactive.invalidate_later(2)
            linha = manual_arquivo.assinatura_de(aberto["usuario"])
            if linha is not None and linha["cadastrado_em"] >= aberto["criado_em"]:
                quadro_aberto.set(None)
                _incrementar(assinatura_versao)
            elif datetime.now() - aberto["criado_em"] > timedelta(minutes=assinatura.VALIDADE_MINUTOS):
                quadro_aberto.set({**aberto, "url": ""})
        except Exception as exc:
            quadro_aberto.set(None)
            _recado_no_modal(f"Não consegui conferir a assinatura: {exc}", "error")

    @reactive.effect
    async def _foto_da_assinatura():
        if "assinatura_foto" not in input:
            return
        arquivos = input["assinatura_foto"]()
        if not arquivos or arquivos[0]["datapath"] == _foto_ja_lida.get("caminho"):
            return
        _foto_ja_lida["caminho"] = arquivos[0]["datapath"]
        with reactive.isolate():
            aberto = quadro_aberto()
        usuario = (aberto or {}).get("usuario") or _usuario()
        if not _pode("assinar_ppf"):
            return
        raiz = session.root_scope() if hasattr(session, "root_scope") else session
        try:
            bruto = Path(arquivos[0]["datapath"]).read_bytes()
            if len(bruto) > assinatura.TAMANHO_MAXIMO:
                raise ValueError("A foto passa de 8 MB. Mande uma menor.")
            png = await asyncio.to_thread(assinatura.limpar, bruto)
            await asyncio.to_thread(
                manual_arquivo.gravar_assinatura, usuario, png, "foto", assinatura.de_onde(raiz.http_conn)
            )
            quadro_aberto.set(None)
            _incrementar(assinatura_versao)
        except ValueError as exc:
            _recado_no_modal(str(exc), "warning")
        except Exception:
            _recado_no_modal("Não consegui ler essa foto. Tente outra imagem (JPG ou PNG).", "error")

    @render.ui
    def assinatura_corpo():
        assinatura_versao()
        aberto = quadro_aberto()
        if not aberto:
            linha = manual_arquivo.assinatura_de(_usuario())
            if linha is None:
                return ui.p("Nenhuma assinatura cadastrada.")
            return ui.div(
                ui.p("Assinatura cadastrada. É ela que vai nas aprovações feitas por você."),
                ui.tags.img(
                    src=assinatura.como_data_uri(linha["imagem"]), class_="ppf-assinatura-previa", alt="Sua assinatura"
                ),
                ui.input_action_button("assinatura_refazer", "Refazer", class_="btn btn-outline-secondary btn-sm"),
                class_="ppf-assinatura",
            )
        if not aberto["url"]:
            return ui.div(
                ui.p("O QR code venceu (vale 10 minutos)."),
                ui.input_action_button(
                    "assinatura_refazer", "Gerar outro QR code", class_="btn btn-outline-secondary btn-sm"
                ),
                class_="ppf-assinatura",
            )
        codigo = qrcode.QRCode(border=1, image_factory=qrcode.image.svg.SvgPathImage)
        codigo.add_data(aberto["url"])
        return ui.div(
            ui.div(ui.HTML(codigo.make_image().to_string(encoding="unicode")), class_="ppf-assinatura-qr"),
            ui.p(
                "Leia com a câmera do celular e assine com o dedo. "
                "O link vale 10 minutos e uma vez só; esta janela atualiza sozinha."
            ),
            ui.p(
                ui.tags.a("Abrir o quadro neste computador", href=aberto["url"], target="_blank", rel="noopener"),
                class_="small",
            ),
            ui.hr(),
            ui.p("Ou envie uma foto da assinatura feita em papel branco, com caneta escura:"),
            ui.input_file(
                "assinatura_foto",
                None,
                accept=["image/*"],
                multiple=False,
                button_label="Escolher foto",
                placeholder="Nenhuma foto escolhida",
                width="100%",
            ),
            class_="ppf-assinatura",
        )

    permissoes_versao = reactive.value(0)
    _logins_na_tela: dict = {}

    @_delegado
    def _abrir_permissoes():
        if not _clicou("permissoes_abrir") or not _pode(CHAVE_EDITAR_RESPONSAVEIS):
            return
        _limpar_recados()
        ui.modal_show(
            ui.modal(
                ui.p(
                    "Quem pode cada coisa no Financeiro, por login (nome.sobrenome). Vale no "
                    "próximo carregamento de página de quem entrar ou sair -- não precisa "
                    "reiniciar nada.",
                    class_="ppf-permissoes-texto",
                ),
                _slot_recados(),
                ui.div(ui.output_ui(session.ns("permissoes_corpo")), class_="ppf-permissoes-rolagem"),
                title="Permissões",
                easy_close=True,
                size="l",
                footer=ui.modal_button("Fechar", class_="btn btn-secondary"),
            )
        )

    @render.ui
    def permissoes_corpo():
        permissoes_versao()
        _logins_na_tela.clear()
        secoes = []
        for secao, itens in secoes_de_direitos():
            linhas = []
            for chave, frase, logins in itens:
                for posicao, login in enumerate(logins):
                    _logins_na_tela[(chave, posicao)] = login
                linhas.append(
                    ui.div(
                        ui.div(
                            ui.div(frase, class_="ppf-permissoes-frase"),
                            ui.div(chave, class_="ppf-permissoes-chave"),
                            class_="ppf-permissoes-rotulo",
                        ),
                        ui.div(
                            ui.div(
                                ui.input_text(f"perm_novo_{chave}", None, placeholder="nome.sobrenome"),
                                ui.input_action_button(
                                    f"perm_add_{chave}",
                                    None,
                                    icon=icon_svg("plus", a11y="deco"),
                                    class_="btn-sm ppf-permissoes-add",
                                    title="Acrescentar este login",
                                ),
                                class_="ppf-permissoes-entrada",
                            ),
                            ui.div(
                                *(
                                    [
                                        ui.span(
                                            "Todo mundo" if login == "*" else login,
                                            ui.input_action_button(
                                                f"perm_del_{chave}_{posicao}",
                                                None,
                                                icon=icon_svg("xmark", a11y="deco"),
                                                class_="ppf-permissoes-tirar",
                                                title=f"Tirar {login} desta lista",
                                            ),
                                            class_="ppf-permissoes-chip",
                                        )
                                        for posicao, login in enumerate(logins)
                                    ]
                                    or [ui.span("Ninguém liberado", class_="ppf-permissoes-vazio")]
                                ),
                                class_="ppf-permissoes-lista",
                            ),
                            class_="ppf-permissoes-valores",
                        ),
                        class_="ppf-permissoes-item",
                        **{"data-busca": " ".join([frase, chave, *logins])},
                    )
                )
            cabeca = (
                ui.div(
                    ui.span(secao),
                    ui.tags.input(
                        type="search",
                        class_="form-control form-control-sm ppf-permissoes-busca",
                        placeholder="Procurar permissão ou login",
                        **{"aria-label": "Procurar permissão ou login"},
                    ),
                    class_="ppf-permissoes-secao ppf-permissoes-secao-com-busca",
                )
                if not secoes
                else ui.div(secao, class_="ppf-permissoes-secao")
            )
            secoes.append(ui.div(cabeca, *linhas, class_="ppf-permissoes-grupo"))
        return ui.div(*secoes, class_="ppf-permissoes-corpo")

    @reactive.effect
    def _mexer_nas_permissoes():
        permissoes_versao()
        adicionar = remover = None
        for (chave, posicao), login in list(_logins_na_tela.items()):
            if _clicou(f"perm_del_{chave}_{posicao}"):
                remover = (chave, login)
        for _secao, itens in secoes_de_direitos():
            for chave, *_resto in itens:
                if _clicou(f"perm_add_{chave}"):
                    campo = f"perm_novo_{chave}"
                    with reactive.isolate():
                        adicionar = (chave, str(input[campo]() or "") if campo in input else "")
        if not adicionar and not remover:
            return
        if not _pode(CHAVE_EDITAR_RESPONSAVEIS):
            return
        _limpar_recados()
        try:
            if adicionar:
                resultado = adicionar_responsavel(*adicionar)
            else:
                resultado = remover_responsavel(*remover)
        except Exception as erro:
            print(f"Permissões: falha ao gravar -- {erro}")
            resultado = "erro"
        recado = {
            "login_invalido": ("Escreva o login como no exemplo: nome.sobrenome, sem espaço.", "warning"),
            "ja_existia": ("Esse login já estava nessa lista.", "warning"),
            "nao_estava": ("Esse login já não estava nessa lista.", "warning"),
            "erro": ("Não deu para gravar. Tente de novo.", "error"),
        }.get(resultado)
        if recado:
            _recado_no_modal(*recado)
        elif adicionar:
            ui.update_text(f"perm_novo_{adicionar[0]}", value="")
        _incrementar(permissoes_versao)

    _assinaturas_na_tela: dict = {}
    assinatura_a_apagar = reactive.value(None)

    @_delegado
    def _abrir_assinaturas():
        if not _clicou("assinaturas_abrir") or not no_acesso_total(_usuario()):
            return
        _limpar_recados()
        assinatura_a_apagar.set(None)
        ui.modal_show(
            ui.modal(
                ui.p(
                    "Quem já cadastrou a assinatura. Apagada, a pessoa volta a ver o aviso “Cadastre sua "
                    "assinatura” no Contas a Pagar e cadastra de novo. O que ela já assinou continua com a "
                    "assinatura de antes.",
                    class_="ppf-permissoes-texto",
                ),
                _slot_recados(),
                ui.div(ui.output_ui(session.ns("assinaturas_corpo")), class_="ppf-permissoes-rolagem"),
                title="Assinaturas",
                easy_close=True,
                size="l",
                footer=ui.modal_button("Fechar", class_="btn btn-secondary"),
            )
        )

    @render.ui
    def assinaturas_corpo():
        assinatura_versao()
        a_apagar = assinatura_a_apagar()
        _assinaturas_na_tela.clear()
        cadastradas = manual_arquivo.ler("assinaturas")
        if cadastradas.is_empty():
            return ui.p("Ninguém cadastrou assinatura ainda.", class_="ppf-permissoes-vazio")
        linhas = []
        for posicao, linha in enumerate(cadastradas.sort("usuario").iter_rows(named=True)):
            login = linha["usuario"]
            _assinaturas_na_tela[posicao] = login
            quando = linha["cadastrado_em"].strftime("%d/%m/%Y %H:%M") if linha["cadastrado_em"] else ""
            origem = {"celular": "pelo celular", "foto": "por foto"}.get(linha["origem"] or "", linha["origem"] or "")
            if a_apagar == login:
                acoes = ui.div(
                    ui.span("Apagar esta assinatura?", class_="ppf-assinaturas-pergunta"),
                    ui.input_action_button(f"assin_confirmar_{posicao}", "Apagar", class_="btn btn-danger btn-sm"),
                    ui.input_action_button(
                        f"assin_cancelar_{posicao}", "Cancelar", class_="btn btn-outline-secondary btn-sm"
                    ),
                    class_="ppf-assinaturas-acoes",
                )
            else:
                acoes = ui.div(
                    ui.input_action_button(
                        f"assin_apagar_{posicao}",
                        "Apagar",
                        icon=icon_svg("trash-can", a11y="deco"),
                        class_="btn btn-outline-danger btn-sm",
                        title=f"Apagar a assinatura de {login}",
                    ),
                    class_="ppf-assinaturas-acoes",
                )
            linhas.append(
                ui.div(
                    ui.div(
                        ui.div(login, class_="ppf-permissoes-frase"),
                        ui.div(f"Cadastrada {origem} em {quando}".strip(), class_="ppf-permissoes-chave"),
                        class_="ppf-permissoes-rotulo",
                    ),
                    ui.tags.img(
                        src=assinatura.como_data_uri(linha["imagem"]),
                        class_="ppf-assinatura-previa",
                        alt=f"Assinatura de {login}",
                    ),
                    acoes,
                    class_="ppf-permissoes-item ppf-assinaturas-item",
                )
            )
        return ui.div(*linhas, class_="ppf-permissoes-corpo")

    @reactive.effect
    def _mexer_nas_assinaturas():
        assinatura_versao()
        assinatura_a_apagar()
        pedida = confirmada = cancelada = None
        posicoes = max(manual_arquivo.ler("assinaturas").height, len(_assinaturas_na_tela)) + 5
        for posicao in range(posicoes):
            login = _assinaturas_na_tela.get(posicao)
            if _clicou(f"assin_apagar_{posicao}"):
                pedida = login
            if _clicou(f"assin_confirmar_{posicao}"):
                confirmada = login
            if _clicou(f"assin_cancelar_{posicao}"):
                cancelada = login
        if not (pedida or confirmada or cancelada):
            return
        if not no_acesso_total(_usuario()):
            return
        _limpar_recados()
        if confirmada:
            try:
                manual_arquivo.apagar_assinatura(confirmada)
                _recado_no_modal(
                    f"Assinatura de {confirmada} apagada. No próximo acesso ao Contas a Pagar, a pessoa "
                    "vê o aviso para cadastrar de novo.",
                    "success",
                )
            except Exception as erro:
                print(f"Assinaturas: falha ao apagar -- {erro}")
                _recado_no_modal("Não deu para apagar. Tente de novo.", "error")
            assinatura_a_apagar.set(None)
            _incrementar(assinatura_versao)
            return
        assinatura_a_apagar.set(None if cancelada else pedida)

    @render.ui
    def botao_fabrica():
        fabrica = fabricas.fabrica_da_revenda(_revenda())
        if fabrica is None:
            return None
        icone = fabrica.get("icone_filtro") or ICONE_MARÉ
        titulo = fabrica.get("titulo_filtro") or f"Filtrar só {fabrica['nome']}"
        return ui.input_action_button(
            "filtro_fabrica",
            ui.tags.img(src=icone, alt=titulo),
            class_="btn ppf-botao-fabrica" + (" ativo" if fabrica_ligada() else ""),
            title=titulo,
        )

    def _so_entradas_de_hoje() -> bool:
        try:
            return bool(input.entradas_hoje())
        except Exception:
            return False

    def _escopo_multiplo() -> bool:
        alvos = d.revendas_da_url(_revenda())
        return alvos is None or len(alvos) > 1

    _COLUNAS_ORDEM_PAGAR = (
        ("DATA", "Vencimento", "data"),
        ("FORNECEDOR", "Fornecedor", "texto"),
        ("descricao_despesa", "Tipo", "texto"),
        ("CENTRO_CUSTO", "C. Custo", "texto"),
        ("PGMOVMOV_NDUPL", "Documento", "texto"),
        ("tipo_doc", "Tipo Doc", "texto"),
        ("_valor_ordem", "Valor Original", "valor"),
    )
    ordem_pagar = reactive.value(())
    _ligar_ordem_varias("ord_pag", _COLUNAS_ORDEM_PAGAR, ordem_pagar)

    @reactive.effect
    @reactive.event(ordem_pagar, ignore_init=True)
    def _primeira_pagina_ao_ordenar():
        paginador.reiniciar()

    so_assinar = reactive.value(False)

    @_delegado
    def _filtro_so_assinar():
        if "pag_so_assinar" not in input:
            return
        ligado = bool(input.pag_so_assinar())
        with reactive.isolate():
            if ligado != so_assinar():
                so_assinar.set(ligado)

    @reactive.effect
    @reactive.event(so_assinar, ignore_init=True)
    def _primeira_pagina_ao_filtrar_assinar():
        paginador.reiniciar()

    def _so_os_de_assinar(base: pl.DataFrame, docs: dict) -> pl.DataFrame:
        return cp.para_assinar(base, docs, gravacao.titulo_sem_boleto, an.antigos_do_titulo)

    @reactive.calc
    async def pagar_pronto() -> pl.DataFrame:
        base = await pagar_filtrado()
        if base.is_empty():
            return base

        def _opcional(coluna: str, apelido: str, tipo=pl.Utf8) -> pl.Expr:
            if coluna in base.columns:
                return pl.col(coluna).cast(tipo, strict=False).alias(apelido)
            return pl.lit(None, dtype=tipo).alias(apelido)

        ident = pl.col("id_unico").cast(pl.Utf8) if "id_unico" in base.columns else pl.lit("", dtype=pl.Utf8)
        numero = ident.str.extract(r"_clone(\d+)$", 1).cast(pl.Int64, strict=False)
        vezes = ident.str.count_matches("_clone")
        base = base.with_columns(
            cp.ordem_por_fornecedor(),
            ident.str.replace(cp.SUFIXO_PARTE, "").alias("_grupo_ordem"),
            pl.when((vezes == 1) & numero.is_not_null()).then(numero).otherwise(vezes).alias("_parte_ordem"),
        ).with_columns(
            pl.col("PGMOVMOV_VALOR").cast(pl.Float64, strict=False).sum().over("_grupo_ordem").alias("_valor_ordem"),
        )
        chaves = ["DATA", cp.ORDEM_FORNECEDOR, "_valor_ordem", "_grupo_ordem", "_parte_ordem"]
        decrescente = [False, False, True, False, False]
        tipos = {c: t for c, _r, t in _COLUNAS_ORDEM_PAGAR}
        clicadas = [(coluna, desc) for coluna, desc in ordem_pagar() if coluna in base.columns]
        for i, (coluna, _desc) in enumerate(clicadas):
            tipo = tipos[coluna]
            chave = (
                pl.col(coluna).cast(pl.Utf8).fill_null("").str.to_lowercase()
                if tipo == "texto"
                else pl.col(coluna).cast(pl.Float64, strict=False)
                if tipo == "valor"
                else pl.col(coluna)
            )
            base = base.with_columns(chave.sort_by("_parte_ordem").first().over("_grupo_ordem").alias(f"_ordem_{i}"))
        if clicadas:
            chaves = [f"_ordem_{i}" for i in range(len(clicadas))] + chaves
            decrescente = [desc for _c, desc in clicadas] + decrescente
        return base.sort(
            chaves,
            descending=decrescente,
            nulls_last=True,
            maintain_order=True,
        ).select(
            pl.col("DATA").dt.strftime("%d/%m/%Y").fill_null("").alias("Vencimento"),
            pl.col("FORNECEDOR").fill_null("").alias("Fornecedor"),
            _opcional("descricao_despesa", "Tipo"),
            _opcional("CENTRO_CUSTO", "C. Custo").fill_null(""),
            pl.col("PGMOVMOV_NDUPL").fill_null("").alias("Documento"),
            _opcional("tipo_doc", "Tipo Doc"),
            pl.col("PGMOVMOV_VALOR").alias("_valor"),
            pl.col("DATA").alias("_dia"),
            _opcional("valor_pago", "_pago", pl.Float64),
            _opcional("juros", "_juros", pl.Float64),
            _opcional("banco", "Banco"),
            _opcional("assinar", "_assinar"),
            _opcional("auditoria", "_auditoria"),
            _opcional("pagar", "_pagar"),
            _opcional("pagar", "_enviado"),
            _opcional("conselho", "_conselho"),
            _opcional("REVENDA", "_revenda_linha"),
            _opcional("num_doc_normalizado", "_doc_norm"),
            _opcional("assinar_user", "_assinar_user"),
            _opcional("auditoria_user", "_auditoria_user"),
            _opcional("pagar_user", "_pagar_user"),
            _opcional("conselho_user", "_conselho_user"),
            pl.col("PGMOVMOV_CGC").fill_null("").alias("_cnpj"),
            _opcional("no_erp", "_no_erp", pl.Int64),
            _opcional("id_unico", "_id"),
            _opcional("justificativa", "_justificativa"),
            _opcional("pagou", "_pagou"),
            _opcional("entrada_manual", "_entrada_manual"),
            _opcional("lancado_por", "_lancado_por"),
            _opcional("alterado_por", "_alterado_por"),
            _opcional("valor_titulo", "_valor_titulo", pl.Float64),
            _opcional("_tem_partes", "_tem_partes", pl.Boolean),
            _opcional("valor_titulo_cheio", "_valor_cheio", pl.Float64),
        )

    _corpo_montado = {"sim": False}

    @render.ui
    async def corpo_tabela_pagar():
        if _corpo_montado["sim"]:
            req(False, cancel_output=True)
        _corpo_montado["sim"] = True
        return ui.div(
            ui.output_ui("tabela_pagar"),
            ui.output_ui("controles_tabela_pagar"),
            class_="ppf-tabela-pagar",
        )

    titulo_dos_anexos = reactive.value(("", "", None, ""))
    anexos_mudaram = reactive.value(0)

    url_anexo = session.dynamic_route("ver_anexo", an.entregar_anexo)

    url_anexo_antigo = session.dynamic_route("ver_anexo_antigo", an.entregar_anexo_antigo)
    _emenda_anexo = "&" if "?" in url_anexo else "?"

    def _documento_do_olho(ident: str, doc_norm: str, fornecedor: str) -> Path | None:
        return an.documento_do_olho(ident, doc_norm, fornecedor)

    _olhos_desenhados: dict = {}

    async def _entregar_olho(request):
        from starlette.responses import FileResponse, PlainTextResponse

        ident = request.query_params.get("id", "")
        desenhado = _olhos_desenhados.get(ident)
        if desenhado is None:
            return PlainTextResponse("arquivo nao encontrado", status_code=404)
        assinado = await asyncio.to_thread(gravacao.pdf_assinado, ident)
        original = await asyncio.to_thread(_documento_do_olho, ident, *desenhado)
        alvo = await asyncio.to_thread(an.documento_assinado_do_olho, original, assinado) if assinado else original
        if alvo is None or not await asyncio.to_thread(alvo.is_file):
            return PlainTextResponse("arquivo nao encontrado", status_code=404)
        nome = an.nome_do_olho(original, desenhado[0]) if original else alvo.name
        if assinado and original:
            nome = f"{Path(nome).stem} - assinado.pdf"
        tipo, como = an.como_mostrar(alvo.name)
        return FileResponse(
            alvo, media_type=tipo, filename=nome, content_disposition_type=como, headers={"Cache-Control": "no-store"}
        )

    url_olho = session.dynamic_route("ver_olho", _entregar_olho)
    _emenda_olho = "&" if "?" in url_olho else "?"

    _rede_desenhados: dict = {}

    async def _entregar_rede(request):
        from starlette.responses import FileResponse, PlainTextResponse

        caminho = _rede_desenhados.get(request.query_params.get("id", ""))
        alvo = await asyncio.to_thread(rede_documentos.caminho_atual, caminho) if caminho else None
        if alvo is None:
            return PlainTextResponse("arquivo nao encontrado", status_code=404)
        tipo, como = an.como_mostrar(alvo.name)
        return FileResponse(
            alvo,
            media_type=tipo,
            filename=alvo.name,
            content_disposition_type=como,
            headers={"Cache-Control": "no-store"},
        )

    url_rede = session.dynamic_route("ver_rede", _entregar_rede)
    _emenda_rede = "&" if "?" in url_rede else "?"

    def _href_da_rede(caminho: str) -> str:
        chave = hashlib.sha1(str(caminho).encode("utf-8")).hexdigest()[:16]
        _rede_desenhados[chave] = str(caminho)
        return url_rede + _emenda_rede + "id=" + chave

    def _olho_da_rede(caminho: str):
        return ui.tags.a(
            ui.tags.img(src="img/ppf/view.svg", alt="Ver"),
            href=_href_da_rede(caminho),
            target="_blank",
            class_="ppf-modal-btn ppf-modal-btn-ver",
            title="Visualizar PDF",
        )

    def _o_que_o_olho_abre(ident: str, doc_norm: str, fornecedor: str, ctx: dict, assinado: bool) -> str:
        base = base_do(ident)
        xml = cp.xml_conta(ident, doc_norm, fornecedor, ctx, an.antigos_do_titulo)
        quantos = (
            ctx.get("quantos_da_rede", {}).get(base, 0)
            + xml
            + (ident in ctx["com_vinculo"])
            + (ident in ctx["com_anexo"])
            + (doc_norm in ctx["docs_antigos"])
        )
        if quantos > 1:
            texto = "os arquivos vinculados ao título juntos, um abaixo do outro"
        elif xml:
            texto = "a nota fiscal montada do XML (Acompanhamento Fiscal)"
        elif base in ctx["abrir_rede"]:
            origem = cp.texto_do_vinculo(ctx["origem_rede"].get(base))
            texto = "o arquivo da rede" + (f" ({origem})" if origem else "")
        elif ident in ctx["com_vinculo"]:
            texto = "o arquivo da rede vinculado nesta tela"
        elif ident in ctx["com_anexo"]:
            texto = "o anexo enviado nesta tela"
        elif doc_norm in ctx["docs_antigos"]:
            texto = "o anexo enviado no sistema antigo"
        else:
            return ""
        return ("Abre a cópia assinada d" + texto[0] + texto[1:]) if assinado else "Abre " + texto

    def _pdf_para_abrir(ident: str, doc_norm: str, fornecedor: str, ctx: dict) -> str | None:
        if not cp.tem_arquivo_no_olho(ident, doc_norm, fornecedor, ctx, an.antigos_do_titulo):
            return None
        _olhos_desenhados[ident] = (doc_norm, fornecedor)
        return url_olho + _emenda_olho + "id=" + quote(str(ident))

    def _modal_anexos(rotulo: str):
        return ui.modal(
            _slot_recados(),
            ui.p(rotulo, class_="fw-bold ppf-modal-anexos-titulo"),
            ui.div(
                ui.input_file(
                    session.ns("arq_titulo"),
                    None,
                    button_label=ui.TagList(
                        ui.tags.img(src=an.ICONE_PDF, class_="ppf-arquivo-icone", alt=""),
                        "Selecionar PDF",
                    ),
                    placeholder="Nenhum arquivo selecionado",
                    accept=".pdf",
                    multiple=False,
                    width="100%",
                ),
                class_="ppf-modal-arquivo",
            ),
            ui.card(
                ui.card_header("Vinculados a este título"),
                ui.output_ui(session.ns("lista_anexos")),
                ui.card_footer(
                    "Os botões NF e FAT dizem se o arquivo enviado é a nota fiscal ou o boleto. "
                    "Título sem boleto aparece com o ícone do PIX na lista. A nota do XML só fica no título "
                    "sem o PDF da nota. Desvincular tira o arquivo só deste título; Vincular de novo desfaz.",
                    class_="text-muted small",
                ),
                class_="ppf-anexos-card",
            ),
            ui.card(
                ui.card_header(
                    ui.span(ui.tags.span("\U0001f4e1 ", aria_hidden="true"), "Na pasta da rede"),
                    ui.div(
                        ui.input_switch(session.ns("rede_tudo"), "Pasta inteira", value=_listar_tudo_agora()),
                        ui.input_action_button(
                            session.ns("rede_reler"),
                            "Procurar de novo",
                            class_="ppf-modal-btn ppf-modal-btn-tipo",
                        ),
                        class_="ppf-anexos-card-acoes",
                    ),
                    class_="ppf-anexos-card-topo",
                ),
                ui.output_ui(session.ns("rede_achados")),
                class_="ppf-anexos-card",
            ),
            title="Anexos do titulo",
            easy_close=True,
            footer=ui.modal_button("Fechar", class_="btn btn-secondary"),
        )

    def _com_balao(elemento, texto: str | None):
        return ui.tooltip(elemento, texto) if texto else elemento

    def _listar_tudo_agora() -> bool:
        with reactive.isolate():
            return rede_listar_tudo()

    def _selo_do_arquivo(tipo: str | None, origem: str | None = None, palpite: bool = False):
        boleto = str(tipo or "").upper() == "FATURA"
        if not boleto and str(tipo or "").upper() != "NF":
            return None
        return _com_balao(
            ui.span(
                ("Boleto" if boleto else "Nota fiscal") + ("?" if palpite else ""),
                class_="ppf-selo "
                + ("ppf-selo-boleto" if boleto else "ppf-selo-nota")
                + (" ppf-selo-palpite" if palpite else ""),
            ),
            origem,
        )

    def _selo_alerta(texto: str, detalhe: str | None = None):
        return _com_balao(ui.span(texto, class_="ppf-selo ppf-selo-alerta"), detalhe)

    _tipo_do_anexo = an.tipo_do_anexo

    def _selo_tipo(ident: str, nome: str):
        tipo, palpite = _tipo_do_anexo(ident, nome)
        if not palpite:
            return _selo_do_arquivo(tipo, "Declarado por quem anexou")
        return _selo_do_arquivo(tipo, "Deduzido do nome do arquivo — use NF ou FAT para confirmar", palpite=True)

    ARQUIVOS_REDE = 60

    rede_versao = reactive.value(0)
    rede_listar_tudo = reactive.value(False)

    @reactive.calc
    async def _da_rede():
        rede_versao()
        ident, _rotulo, venc, doc = titulo_dos_anexos()
        if not ident or venc is None:
            return [], None, []
        return await asyncio.to_thread(an.buscar_na_rede, _revenda(), venc, doc, rede_listar_tudo())

    def _chave_caminho(caminho) -> str:
        return str(caminho or "").replace("/", "\\").strip().lower()

    def _ligados_do_titulo(ident: str) -> dict:
        if not ident:
            return {}
        ligados = {_chave_caminho(v.get("caminho")): v for v in d.vinculos_de_fora(base_do(ident))}
        aqui = manual_arquivo.ler("vinculos")
        if not aqui.is_empty():
            for v in aqui.filter(pl.col("id_unico") == ident).to_dicts():
                ligados[_chave_caminho(v.get("caminho"))] = {**v, "origem": "aqui"}
        return ligados

    def _selo_ligado(origem: str | None):
        if origem is None:
            return None
        return _com_balao(ui.span("\u2713 já vinculado", class_="ppf-selo ppf-selo-ok"), origem or None)

    @render.ui
    async def rede_achados():
        anexos_mudaram()
        achados, onde, por_raiz = await _da_rede()
        ident = titulo_dos_anexos()[0]
        ligados = _ligados_do_titulo(ident)
        copiados = {a.name.lower() for a in gravacao.anexos_do_titulo(ident)} if ident else set()
        if onde is None:
            return ui.p(
                "Sem vencimento no titulo -- nao da para procurar na rede.",
                class_="ppf-modal-lista-vazia",
            )

        varias = len(por_raiz) > 1
        pastas = por_raiz or [("", onde)]
        rodape = ui.accordion(
            ui.accordion_panel(
                "Pastas onde o app procurou",
                *[
                    ui.div(
                        ui.span(rotulo, class_="ppf-rede-origem") if varias else None,
                        _com_balao(
                            ui.span(str(sug.caminho) if sug.caminho else "-", class_="ppf-rede-caminho"),
                            None if sug.achou else sug.motivo,
                        ),
                        class_="ppf-rede-pasta" + ("" if sug.achou else " ppf-rede-pasta-falta"),
                    )
                    for rotulo, sug in pastas
                ],
                value="pastas",
            ),
            open="pastas" if not all(sug.achou for _r, sug in pastas) else False,
            class_="ppf-rede-rodape",
        )
        if not any(sug.achou for _r, sug in por_raiz) and not onde.achou:
            return ui.div(ui.p(onde.motivo, class_="ppf-modal-lista-vazia"), rodape)
        raizes = [(rotulo, str(sug.caminho)) for rotulo, sug in por_raiz if sug.achou and sug.caminho]
        if not achados:
            return ui.div(
                ui.p(
                    "Nenhum arquivo casou com este documento nesta pasta.",
                    class_="ppf-modal-lista-vazia",
                ),
                rodape,
            )

        def _linha(i: int, a):
            ligado = ligados.get(_chave_caminho(a.caminho))
            origem = (
                _frase(cp.texto_do_vinculo(ligado))
                if ligado
                else "Copiado para dentro do app"
                if a.nome.lower() in copiados
                else None
            )
            return ui.tags.li(
                ui.div(
                    ui.tags.img(src=an.ICONE_PDF, class_="ppf-arquivo-icone", alt=""),
                    ui.span(a.nome, class_="ppf-modal-lista-nome", title=str(a.caminho)),
                    ui.span(next((r for r, c in raizes if str(a.caminho).startswith(c)), ""), class_="ppf-rede-origem")
                    if varias
                    else None,
                    _selo_ligado(origem),
                    class_="ppf-modal-lista-arquivo",
                ),
                ui.div(
                    _olho_da_rede(str(a.caminho)),
                    *(
                        []
                        if origem is not None
                        else [
                            ui.input_action_button(
                                "rede_vincular_" + str(i),
                                "Vincular",
                                class_="ppf-modal-btn ppf-modal-btn-tipo",
                                title="Aponta para o arquivo na rede, sem ocupar disco",
                            ),
                            ui.input_action_button(
                                "rede_copiar_" + str(i),
                                "Copiar",
                                class_="ppf-modal-btn ppf-modal-btn-tipo",
                                title="Traz uma cópia para dentro do app (ocupa disco)",
                            ),
                        ]
                    ),
                    class_="ppf-modal-lista-acoes",
                ),
            )

        fora = len(achados) - ARQUIVOS_REDE
        return ui.div(
            ui.tags.ul(*[_linha(i, a) for i, a in enumerate(achados[:ARQUIVOS_REDE])], class_="ppf-modal-lista"),
            ui.p(
                f"Mostrando os primeiros {ARQUIVOS_REDE} de {len(achados)} arquivos da pasta.",
                class_="ppf-modal-lista-vazia",
            )
            if fora > 0
            else None,
            rodape,
        )

    @reactive.effect
    @reactive.event(input.rede_tudo, ignore_init=True)
    def _rede_alternar():
        rede_listar_tudo.set(bool(input.rede_tudo()))

    @reactive.effect
    @reactive.event(input.rede_reler)
    async def _rede_reler():
        ident, _rotulo, venc, doc = titulo_dos_anexos()
        if not ident or venc is None:
            return
        _limpar_recados()
        revenda, tudo = _revenda(), rede_listar_tudo()

        def _reler():
            rede_documentos.esquecer(revenda, venc)
            return an.buscar_na_rede(revenda, venc, doc, tudo)

        try:
            achados, _onde, _por_raiz = await asyncio.to_thread(_reler)
        except Exception as erro:
            _recado_no_modal("Não deu para reler a pasta: " + str(erro)[:120], "error")
            return
        _incrementar(rede_versao)
        _recado_no_modal(
            f"Pasta do dia {venc:%d/%m/%Y} relida: {len(achados)} arquivo(s)"
            + ("." if tudo else " com o número do documento no nome."),
            "success",
        )

    def _ligar_copiar_rede(indice: int) -> None:
        @_delegado
        async def _copiar():
            if not _clicou("rede_copiar_" + str(indice)):
                return
            if _barrar("anexar_titulo", no_modal=True):
                return
            ident, _rotulo, venc, doc = titulo_dos_anexos()
            if not ident or venc is None:
                return
            achados, _onde, _por_raiz = await asyncio.to_thread(
                an.buscar_na_rede, _revenda(), venc, doc, rede_listar_tudo()
            )
            if indice >= len(achados):
                return
            arquivo = achados[indice]
            try:
                await asyncio.to_thread(
                    gravacao.guardar_anexo,
                    ident,
                    str(arquivo.caminho),
                    arquivo.nome,
                    False,
                )
            except Exception as erro:
                _recado_no_modal(
                    "Não deu para anexar " + arquivo.nome + ": " + str(erro)[:120],
                    "error",
                )
                return
            _incrementar(anexos_mudaram)
            _incrementar(overlay_versao)
            _recado_no_modal(arquivo.nome + " anexado ao título.", "success")

    def _ligar_vincular_rede(indice: int) -> None:
        @_delegado
        async def _vincular():
            if not _clicou("rede_vincular_" + str(indice)):
                return
            if _barrar("anexar_titulo", no_modal=True):
                return
            ident, _rotulo, venc, doc = titulo_dos_anexos()
            if not ident or venc is None:
                return
            achados, _onde, _por_raiz = await asyncio.to_thread(
                an.buscar_na_rede, _revenda(), venc, doc, rede_listar_tudo()
            )
            if indice >= len(achados):
                return
            arquivo = achados[indice]
            try:
                await asyncio.to_thread(manual_arquivo.vincular, ident, arquivo.caminho, _usuario())
            except Exception as erro:
                _recado_no_modal("Não deu para vincular: " + str(erro)[:120], "error")
                return
            _incrementar(anexos_mudaram)
            _incrementar(overlay_versao)
            _recado_no_modal(arquivo.nome + " vinculado (o arquivo continua na rede).", "success")

    for _i in range(ARQUIVOS_REDE):
        _ligar_copiar_rede(_i)
        _ligar_vincular_rede(_i)

    _ORDEM_DO_TIPO = {"NF": 0, "FATURA": 1}
    _tipo_do_vinculo = cp.tipo_do_vinculo

    def _ligar_desvincular(indice: int) -> None:
        @_delegado
        def _tirar():
            if not _clicou("desvincular_" + str(indice)):
                return
            if _barrar("anexar_titulo"):
                return
            ident, _rotulo, _venc, _doc = titulo_dos_anexos()
            atuais = manual_arquivo.vinculos_do_titulo(ident) if ident else []
            if indice >= len(atuais):
                return
            manual_arquivo.desvincular(ident, atuais[indice]["caminho"])
            _incrementar(anexos_mudaram)
            _incrementar(overlay_versao)
            _recado_no_modal("Vínculo removido. O arquivo continua na rede.", "success")

    for _i in range(ARQUIVOS_REDE):
        _ligar_desvincular(_i)

    _desvinculaveis: dict = {"itens": [], "desfeitos": []}
    DESVINCULAVEIS = 2 * ARQUIVOS_REDE
    _AO_DESVINCULAR = {
        "xml": (
            "Tira a nota do XML deste título. Ela continua no Fiscal, e a atualização não a liga de novo.",
            "Nota do XML desvinculada. Ela continua no Fiscal.",
        ),
        "rede": (
            "Tira o vínculo. O arquivo continua na rede, e a atualização não o liga de novo.",
            "Vínculo removido. O arquivo continua na rede.",
        ),
        "antigo": (
            "Tira este PDF do app anterior do título. O arquivo continua lá.",
            "Vínculo removido. O PDF continua no app anterior.",
        ),
    }

    def _botao_desvincular(origem: str, titulo: str, referencia, nome: str):
        k = len(_desvinculaveis["itens"])
        if k >= DESVINCULAVEIS or not referencia:
            return None
        _desvinculaveis["itens"].append((origem, titulo, str(referencia), nome))
        return ui.input_action_button(
            f"desvincular_fora_{k}",
            "Desvincular",
            class_="ppf-modal-btn ppf-modal-btn-tipo",
            title=_AO_DESVINCULAR[origem][0],
        )

    def _ligar_desvincular_fora(indice: int) -> None:
        @_delegado
        def _tirar():
            if not _clicou(f"desvincular_fora_{indice}"):
                return
            if _barrar("anexar_titulo", no_modal=True):
                return
            itens = _desvinculaveis["itens"]
            if indice >= len(itens):
                return
            origem, titulo, referencia, nome = itens[indice]
            manual_arquivo.desvincular_de_fora(titulo, origem, referencia, nome, _usuario())
            _incrementar(anexos_mudaram)
            _incrementar(overlay_versao)
            _recado_no_modal(_AO_DESVINCULAR[origem][1], "success")

    def _ligar_vincular_de_novo(indice: int) -> None:
        @_delegado
        def _voltar():
            if not _clicou(f"revincular_{indice}"):
                return
            if _barrar("anexar_titulo", no_modal=True):
                return
            desfeitos = _desvinculaveis["desfeitos"]
            if indice >= len(desfeitos):
                return
            linha = desfeitos[indice]
            manual_arquivo.vincular_de_novo(linha["id_unico"], linha["origem"], linha["referencia"], _usuario())
            _incrementar(anexos_mudaram)
            _incrementar(overlay_versao)
            ident, rotulo, _venc, doc = titulo_dos_anexos()
            fica_de_fora = linha["origem"] == "xml" and not an.xml_vale(ident, doc, rotulo.split(" — ")[0])
            _recado_no_modal(
                "Nota do XML de volta. Ela só aparece no título sem o PDF da nota."
                if fica_de_fora
                else "Vínculo de volta ao título.",
                "success",
            )

    for _i in range(DESVINCULAVEIS):
        _ligar_desvincular_fora(_i)
    for _i in range(ARQUIVOS_REDE):
        _ligar_vincular_de_novo(_i)

    def _itens_desvinculados(base: str) -> list:
        desfeitos = manual_arquivo.desvinculados_do_titulo(base)[:ARQUIVOS_REDE]
        _desvinculaveis["desfeitos"] = desfeitos
        linhas = []
        for k, linha in enumerate(desfeitos):
            quando = linha.get("desvinculado_em")
            quem = f"Desvinculado por {cp.nome_legivel(linha.get('desvinculado_por'))}" + (
                f" em {quando:%d/%m/%Y %H:%M}" if quando else ""
            )
            linhas.append(
                ui.tags.li(
                    ui.div(
                        ui.tags.img(src=an.ICONE_PDF, class_="ppf-arquivo-icone", alt=""),
                        _com_balao(
                            ui.span(linha.get("nome") or linha.get("referencia"), class_="ppf-modal-lista-nome"), quem
                        ),
                        class_="ppf-modal-lista-arquivo",
                    ),
                    ui.div(
                        ui.input_action_button(
                            f"revincular_{k}",
                            "Vincular de novo",
                            class_="ppf-modal-btn ppf-modal-btn-tipo",
                            title="Devolve o vínculo ao título",
                        ),
                        class_="ppf-modal-lista-acoes",
                    ),
                )
            )
        return linhas

    _xml_no_modal: dict = {}

    async def _entregar_xml(request):
        from starlette.responses import FileResponse, PlainTextResponse

        ident = request.query_params.get("id", "")
        pdf = await asyncio.to_thread(an.pdf_do_xml, ident) if ident and ident in _xml_no_modal.get("ids", ()) else None
        if pdf is None or not await asyncio.to_thread(pdf.is_file):
            return PlainTextResponse("arquivo nao encontrado", status_code=404)
        return FileResponse(
            pdf,
            media_type="application/pdf",
            filename=pdf.name,
            content_disposition_type="inline",
            headers={"Cache-Control": "no-store"},
        )

    url_xml = session.dynamic_route("ver_xml_titulo", _entregar_xml)

    @render.ui
    def lista_anexos():
        anexos_mudaram()
        _anexo_a_excluir()
        ident, _rotulo, _venc, _doc = titulo_dos_anexos()
        if not ident:
            return ui.div()
        fornecedor, base = _rotulo.split(" — ")[0], base_do(ident)
        _desvinculaveis["itens"] = []
        arquivos = gravacao.anexos_do_titulo(ident)
        vinculados = manual_arquivo.vinculos_do_titulo(ident)
        antigos_lista = an.antigos_do_titulo(ident, _doc, fornecedor) if _doc else []
        xmls = [
            (t, d.xml_do_titulo(t))
            for t in ([base] if an.xml_vale(ident, _doc, fornecedor) else []) + an.outras_notas_do_boleto(base)
        ]
        de_fora = d.vinculos_de_fora(base)
        itens = (
            _itens_de_fora(ident, xmls, de_fora)
            + _itens_do_titulo(ident, arquivos, vinculados)
            + _itens_antigos(ident, antigos_lista)
        )
        desfeitos = _itens_desvinculados(base)
        if not itens and not desfeitos:
            return ui.p("Nenhum arquivo vinculado.", class_="ppf-modal-lista-vazia")
        return ui.TagList(
            ui.tags.ul(*[li for _ordem, li in sorted(itens, key=lambda item: item[0])], class_="ppf-modal-lista")
            if itens
            else ui.p("Nenhum arquivo vinculado.", class_="ppf-modal-lista-vazia"),
            ui.div(
                ui.div("Desvinculados", class_="ppf-modal-lista-titulo"),
                ui.tags.ul(*desfeitos, class_="ppf-modal-lista ppf-modal-lista-desvinculados"),
                class_="ppf-modal-desvinculados",
            )
            if desfeitos
            else None,
        )

    def _frase(texto: str) -> str:
        return texto[:1].upper() + texto[1:]

    def _nome_do_xml(xml: dict) -> str:
        return " ".join(str(p) for p in (xml.get("tipo") or "Nota", xml.get("numero")) if p)

    def _origem_do_xml(xml: dict) -> str:
        return "vinculada pelo XML do Acompanhamento Fiscal: o CNPJ do fornecedor e o número do título" + (
            f" (chave {xml['chave']})" if xml.get("chave") else ""
        )

    def _itens_de_fora(ident: str, xmls: list, de_fora: list) -> list[tuple]:
        itens = []
        base = base_do(ident)
        _xml_no_modal["ids"] = {t for t, _x in xmls}
        for dono, xml in xmls:
            do_boleto = dono != base
            itens.append(
                (
                    _ORDEM_DO_TIPO["NF"],
                    ui.tags.li(
                        ui.div(
                            ui.tags.img(src=an.ICONE_PDF, class_="ppf-arquivo-icone", alt=""),
                            ui.span(
                                f"{_nome_do_xml(xml)} (XML)",
                                class_="ppf-modal-lista-nome",
                                title=Path(str(xml.get("arquivo") or "")).name or None,
                            ),
                            _selo_do_arquivo(
                                "NF",
                                _frase(_origem_do_xml(xml))
                                + (". É a outra nota que o mesmo boleto paga." if do_boleto else "."),
                            ),
                            class_="ppf-modal-lista-arquivo",
                        ),
                        ui.div(
                            ui.tags.a(
                                ui.tags.img(src="img/ppf/view.svg", alt="Ver"),
                                href=url_xml + ("&" if "?" in url_xml else "?") + "id=" + quote(dono),
                                target="_blank",
                                class_="ppf-modal-btn ppf-modal-btn-ver",
                                title="Visualizar",
                            ),
                            _botao_desvincular("xml", base, d.referencia_do_xml(xml), f"{_nome_do_xml(xml)} (XML)"),
                            class_="ppf-modal-lista-acoes",
                        ),
                    ),
                )
            )
        for v in de_fora[:ARQUIVOS_REDE]:
            origem = _frase(cp.texto_do_vinculo(v))
            texto_nome = v.get("nome") or Path(str(v.get("caminho") or "")).name
            tipo = _tipo_do_vinculo(v.get("tipo"), texto_nome)
            selo = _selo_do_arquivo(tipo, origem)
            nome = ui.span(texto_nome, class_="ppf-modal-lista-nome")
            itens.append(
                (
                    _ORDEM_DO_TIPO.get(tipo, 2),
                    ui.tags.li(
                        ui.div(
                            ui.tags.img(src=an.ICONE_PDF, class_="ppf-arquivo-icone", alt=""),
                            nome if selo else _com_balao(nome, origem),
                            selo,
                            None if v.get("existe") else _selo_alerta("não está mais na rede", v.get("caminho")),
                            class_="ppf-modal-lista-arquivo",
                        ),
                        ui.div(
                            _olho_da_rede(str(v["caminho"])) if v.get("existe") and v.get("caminho") else None,
                            _botao_desvincular("rede", base, v.get("caminho"), texto_nome),
                            class_="ppf-modal-lista-acoes",
                        ),
                    ),
                )
            )
        return itens

    def _itens_antigos(ident: str, antigos: list) -> list[tuple]:
        return [
            (
                2,
                ui.tags.li(
                    ui.div(
                        ui.tags.img(src=an.ICONE_PDF, class_="ppf-arquivo-icone", alt=""),
                        _com_balao(ui.span(a.name, class_="ppf-modal-lista-nome"), "Enviado pelo app anterior"),
                        class_="ppf-modal-lista-arquivo",
                    ),
                    ui.div(
                        ui.tags.a(
                            ui.tags.img(src="img/ppf/view.svg", alt="Ver"),
                            href=url_anexo_antigo + ("&" if "?" in url_anexo_antigo else "?") + "nome=" + quote(a.name),
                            target="_blank",
                            class_="ppf-modal-btn ppf-modal-btn-ver",
                            title="Visualizar",
                        ),
                        _botao_desvincular("antigo", base_do(ident), a.name, a.name),
                        class_="ppf-modal-lista-acoes",
                    ),
                ),
            )
            for a in antigos
        ]

    def _itens_do_titulo(ident: str, arquivos, vinculados) -> list[tuple]:
        pode_excluir_anexo = _pode("excluir_anexo_titulo")

        _AVISO_ESTADO = {"mudou": "mudou na rede", "sumiu": "não está mais na rede"}
        itens = []
        for i, v in enumerate(vinculados[:ARQUIVOS_REDE]):
            origem = _frase(cp.texto_do_vinculo({**v, "origem": "aqui"}))
            tipo = _tipo_do_vinculo(v.get("tipo"), v["nome"])
            selo = _selo_do_arquivo(tipo, origem)
            nome = ui.span(v["nome"], class_="ppf-modal-lista-nome")
            itens.append(
                (
                    _ORDEM_DO_TIPO.get(tipo, 2),
                    ui.tags.li(
                        ui.div(
                            ui.tags.img(src=an.ICONE_PDF, class_="ppf-arquivo-icone", alt=""),
                            nome if selo else _com_balao(nome, origem),
                            selo,
                            _selo_alerta(_AVISO_ESTADO[v["estado"]], v["caminho"])
                            if v["estado"] in _AVISO_ESTADO
                            else None,
                            class_="ppf-modal-lista-arquivo",
                        ),
                        ui.div(
                            _olho_da_rede(v["caminho"]) if v["estado"] != "sumiu" else None,
                            ui.input_action_button(
                                "desvincular_" + str(i),
                                "Desvincular",
                                class_="ppf-modal-btn ppf-modal-btn-tipo",
                                title="Tira o vínculo. O arquivo continua na rede.",
                            ),
                            class_="ppf-modal-lista-acoes",
                        ),
                    ),
                )
            )
        return itens + [
            (
                _ORDEM_DO_TIPO[_tipo_do_anexo(ident, a.name)[0]],
                ui.tags.li(
                    ui.div(
                        ui.tags.img(src=an.ICONE_PDF, class_="ppf-arquivo-icone", alt=""),
                        ui.span(a.name, class_="ppf-modal-lista-nome"),
                        _selo_tipo(ident, a.name),
                        class_="ppf-modal-lista-arquivo",
                    ),
                    ui.div(
                        ui.input_action_button(
                            "tipo_nf_" + str(indice),
                            "NF",
                            class_="ppf-modal-btn ppf-modal-btn-tipo",
                            title="Marcar como nota fiscal",
                        ),
                        ui.input_action_button(
                            "tipo_fat_" + str(indice),
                            "FAT",
                            class_="ppf-modal-btn ppf-modal-btn-tipo",
                            title="Marcar como boleto/fatura",
                        ),
                        ui.tags.a(
                            ui.tags.img(src="img/ppf/view.svg", alt="Ver"),
                            href=(url_anexo + _emenda_anexo + "id=" + quote(str(ident)) + "&nome=" + quote(a.name)),
                            target="_blank",
                            class_="ppf-modal-btn ppf-modal-btn-ver",
                            title="Visualizar",
                        ),
                        ui.input_action_button(
                            "excluir_anexo_" + str(indice),
                            ui.tags.img(src="img/ppf/delete-icon.svg", alt="Excluir"),
                            class_="ppf-modal-btn ppf-modal-btn-excluir",
                            title="Excluir anexo" if pode_excluir_anexo else "Sem permissão",
                            disabled=not pode_excluir_anexo,
                        )
                        if a.name != _anexo_a_excluir()
                        else ui.div(
                            ui.span(f"Excluir {a.name}?", class_="ppf-modal-lista-pergunta"),
                            ui.input_action_button(
                                "anexo_excluir_sim", "Sim", class_="ppf-modal-btn ppf-modal-btn-sim"
                            ),
                            ui.input_action_button(
                                "anexo_excluir_nao", "Não", class_="ppf-modal-btn ppf-modal-btn-tipo"
                            ),
                            class_="ppf-modal-lista-confirmar",
                        ),
                        class_="ppf-modal-lista-acoes",
                    ),
                ),
            )
            for indice, a in enumerate(arquivos)
        ]

    @reactive.effect
    @reactive.event(input.arq_titulo)
    def _receber_anexo():
        enviados = input.arq_titulo()
        ident, _rotulo, _venc, _doc = titulo_dos_anexos()
        if not enviados or not ident:
            return
        _limpar_recados()
        if _barrar("anexar_titulo", no_modal=True):
            return
        for arquivo in enviados:
            try:
                gravacao.guardar_anexo(ident, arquivo["datapath"], Path(arquivo["name"]).name)
            except Exception as erro:
                _recado_no_modal("Não deu para anexar: " + str(erro)[:120], "error")
                return
        _incrementar(anexos_mudaram)
        _incrementar(overlay_versao)
        _recado_no_modal("Anexo guardado.", "success")

    def _ligar_excluir_anexo(indice: int) -> None:
        @_delegado
        def _excluir():
            if not _clicou("excluir_anexo_" + str(indice)):
                return
            ident, _rotulo, _venc, _doc = titulo_dos_anexos()
            arquivos = gravacao.anexos_do_titulo(ident) if ident else []
            if indice >= len(arquivos):
                return
            if _barrar("excluir_anexo_titulo", no_modal=True):
                return
            _anexo_a_excluir.set(arquivos[indice].name)

    _anexo_a_excluir = reactive.value("")

    @_delegado
    def _confirmar_excluir_anexo():
        if not _clicou("anexo_excluir_sim"):
            return
        nome = _anexo_a_excluir()
        _anexo_a_excluir.set("")
        ident, _rotulo, _venc, _doc = titulo_dos_anexos()
        if not nome or not ident or _barrar("excluir_anexo_titulo", no_modal=True):
            return
        if gravacao.excluir_anexo(ident, nome):
            _incrementar(anexos_mudaram)
            _incrementar(overlay_versao)
            _recado_no_modal(nome + " excluído.", "success")

    @_delegado
    def _cancelar_excluir_anexo():
        if _clicou("anexo_excluir_nao"):
            _anexo_a_excluir.set("")

    def _ligar_tipo_anexo(indice: int) -> None:
        for sufixo, tipo in (("nf", "NF"), ("fat", "FATURA")):

            def _ligar(sufixo=sufixo, tipo=tipo):
                @_delegado
                def _marcar():
                    if not _clicou(f"tipo_{sufixo}_{indice}"):
                        return
                    if _barrar("anexar_titulo", no_modal=True):
                        return
                    ident, _rotulo, _venc, _doc = titulo_dos_anexos()
                    arquivos = gravacao.anexos_do_titulo(ident) if ident else []
                    if indice >= len(arquivos):
                        return
                    nome = arquivos[indice].name
                    atual = manual_arquivo.tipos_de_anexo().get((ident, nome))
                    novo = None if atual == tipo else tipo
                    try:
                        manual_arquivo.classificar_anexo(ident, nome, novo, _usuario())
                    except Exception as erro:
                        _recado_no_modal(f"Falhou ao marcar: {str(erro)[:120]}", "error")
                        return
                    _incrementar(anexos_mudaram)
                    _incrementar(overlay_versao)
                    _recado_no_modal(
                        f"{nome}: " + (f"marcado como {tipo}." if novo else "marca removida (volta ao palpite)."),
                        "success",
                    )

            _ligar()

    for _i in range(20):
        _ligar_excluir_anexo(_i)
        _ligar_tipo_anexo(_i)

    @reactive.effect
    def _botoes_das_listas():
        for funcao in _delegados:
            funcao()

    @reactive.effect
    async def _botoes_das_listas_async():
        for funcao in _delegados_async:
            await funcao()

    _cliques_acao: dict = {}

    def _clicou(nome: str) -> bool:
        if nome not in input:
            return False
        atual = input[nome]() or 0
        anterior = _cliques_acao.get(nome, 0)
        _cliques_acao[nome] = atual
        return atual > anterior

    _pagina_atual: dict = {}

    _lidos: dict = {}

    posicoes_extra = reactive.value(())
    _so_partes = {"pendente": False}
    _na_tela = {"ids": [], "pos": {}}
    _extra = {"proxima": PRIMEIRA_POSICAO_EXTRA, "posicoes": set(), "celula": {}}

    def _posicoes() -> list[int]:
        return [*range(LINHAS_INTERATIVAS), *posicoes_extra()]

    _geracao = {"n": 0}

    def _tabela_velha() -> bool:
        return "tabela_geracao" in input and input.tabela_geracao() != _geracao["n"]

    def _titulo_da_linha(posicao: int):
        return _pagina_atual.get(posicao)

    def _marcado_na_tela(posicao: int, tipo: str, linha: dict) -> bool:
        campo = f"vst_{tipo}_{posicao}"
        if campo in input:
            return bool(input[campo]())
        return bool(linha["marcado"][tipo])

    def _na_gestao_agora(posicao: int, linha: dict, marcas: dict) -> bool:
        if _marcado_na_tela(posicao, "conselho", linha):
            return True
        return cp.na_gestao(linha["id"], {"conselho": "Sim" if linha["marcado"]["conselho"] else "Não"}, marcas)

    def _estado_de(posicao: int, tipo: str, linha: dict, marcas: dict) -> bool:
        gravado, _quem = cp.visto_gravado(linha, tipo, marcas)
        if gravado != linha["marcado"][tipo]:
            return gravado
        return _marcado_na_tela(posicao, tipo, linha)

    def _desfazer_visto(posicao: int, tipo: str, linha: dict, motivo: str | None) -> None:
        campo = f"vst_{tipo}_{posicao}"
        _lidos[campo] = linha["marcado"][tipo]
        ui.update_checkbox(campo, value=linha["marcado"][tipo])
        if motivo:
            _avisar(motivo, titulo="Contas a Pagar")

    def _gravar_visto(linha: dict, tipo: str, marcado: bool) -> None:
        linha["marcado"][tipo] = marcado
        linha["quem"][tipo] = _usuario() if marcado else None
        alvo = base_do(linha["id"]) if tipo in ("auditoria", "conselho") else linha["id"]
        if marcado:
            manual_arquivo.marcar(alvo, tipo, _usuario())
        else:
            manual_arquivo.desmarcar(alvo, tipo, _usuario())

    async def _tratar_visto(posicao: int, tipo: str, marcado_agora: bool) -> None:
        linha = _titulo_da_linha(posicao)
        if linha is None or linha["marcado"][tipo] == marcado_agora:
            return
        chave = gravacao.PERMISSAO_VISTO[tipo]
        if not _pode(chave):
            _desfazer_visto(
                posicao,
                tipo,
                linha,
                "Você não tem permissão para isso. " + quem_libera(chave),
            )
            return
        marcas = manual_arquivo.marcacoes_por_chave()
        if tipo in ("auditoria", "pagar") and _na_gestao_agora(posicao, linha, marcas):
            _desfazer_visto(
                posicao,
                tipo,
                linha,
                "Este título está marcado em Gestão: Auditoria e Pagar ficam travados até a Gestão ser desmarcada.",
            )
            return
        if tipo == "pagar":
            if linha["pagou"]:
                _desfazer_visto(
                    posicao,
                    tipo,
                    linha,
                    "Este título já foi pago no ERP — o Pagar dele não muda mais.",
                )
                return
            if not linha["dispensa_auditoria"] and not _estado_de(posicao, "auditoria", linha, marcas):
                _desfazer_visto(posicao, tipo, linha, MOTIVO_AGUARDA_AUDITORIA)
                return
        alvo = base_do(linha["id"]) if tipo in ("auditoria", "conselho") else linha["id"]
        vencedor = manual_arquivo.primeira_marcacao(
            alvo, tipo, _usuario(), float(carregar_json("parametros_financeiro").get("primeira_marcacao_segundos") or 0)
        )
        if vencedor:
            gravado, quem = cp.visto_gravado(linha, tipo, manual_arquivo.marcacoes_por_chave())
            linha["marcado"][tipo], linha["quem"][tipo] = gravado, quem if gravado else None
            _lidos[f"vst_{tipo}_{posicao}"] = gravado
            await session.send_custom_message(
                "ppfVistos",
                [{"visto": f"{tipo}-{posicao}", "marcado": gravado, "quem": cp.nome_legivel(quem) if gravado else ""}],
            )
            _avisar(
                f"{cp.nome_legivel(vencedor[0])} mexeu neste visto há "
                f"{max(1, round(vencedor[1]))} s: vale a primeira marcação. Para mudar "
                "mesmo assim, clique de novo daqui a alguns segundos.",
                titulo="Contas a Pagar",
            )
            return
        copia = None
        if tipo == "assinar" and marcado_agora:
            usuario = _usuario()
            cadastro = manual_arquivo.assinatura_de(usuario)
            if cadastro is None:
                _desfazer_visto(
                    posicao,
                    tipo,
                    linha,
                    "Cadastre sua assinatura antes de assinar: o botão fica no alto de Contas a Pagar.",
                )
                return
            try:
                original = await asyncio.to_thread(
                    _documento_do_olho, linha["id"], linha["doc_norm"], linha["rotulo_linha"]
                )
                if original is None or original.suffix.lower() not in assinatura.EXTENSOES_ASSINAVEIS:
                    _desfazer_visto(posicao, tipo, linha, "Este título não tem PDF nem imagem para assinar.")
                    return
                copia = gravacao.novo_pdf_assinado(
                    linha["id"],
                    linha["revenda"] or _revenda(),
                    linha["vencimento"],
                    linha["documento_cru"],
                    linha["rotulo_linha"],
                )
                antiga = gravacao.pdf_assinado(linha["id"])
                await asyncio.to_thread(
                    assinatura.assinar_pdf,
                    original,
                    copia,
                    cadastro["imagem"],
                    cp.nome_legivel(usuario),
                    datetime.now(),
                )
                if antiga is not None and antiga != copia:
                    antiga.unlink(missing_ok=True)
            except Exception as erro:
                _desfazer_visto(posicao, tipo, linha, f"Não consegui assinar o PDF: {str(erro)[:200]}")
                return
        try:
            _gravar_visto(linha, tipo, marcado_agora)
            if tipo == "assinar" and not marcado_agora:
                antiga = gravacao.pdf_assinado(linha["id"])
                if antiga is not None:
                    antiga.unlink(missing_ok=True)
            if tipo == "conselho" and marcado_agora:
                if (
                    linha["marcado"]["auditoria"]
                    and cp.mesma_pessoa(linha["quem"]["auditoria"], _usuario())
                    and _pode(gravacao.PERMISSAO_VISTO["auditoria"])
                ):
                    _gravar_visto(linha, "auditoria", False)
                    _lidos[f"vst_auditoria_{posicao}"] = False
                    ui.update_checkbox(f"vst_auditoria_{posicao}", value=False)
                recados = []
                for outra_posicao, outra_linha in list(_pagina_atual.items()):
                    if (
                        base_do(outra_linha["id"]) != base_do(linha["id"])
                        or not outra_linha["marcado"]["pagar"]
                        or outra_linha["pagou"]
                    ):
                        continue
                    _gravar_visto(outra_linha, "pagar", False)
                    _lidos[f"vst_pagar_{outra_posicao}"] = False
                    recados.append({"visto": f"pagar-{outra_posicao}", "marcado": False, "quem": ""})
                if recados:
                    await session.send_custom_message("ppfVistos", recados)
            _incrementar(assinar_versao if tipo == "assinar" else marcacoes_versao)
        except Exception as erro:
            if copia is not None:
                copia.unlink(missing_ok=True)
            _avisar(
                f"Falhou ao gravar: {str(erro)[:200]}",
                tipo="error",
                titulo="Contas a Pagar",
            )

    @reactive.poll(cp.versao_das_marcacoes, 3)
    def _marcacoes_no_disco():
        return cp.versao_das_marcacoes()

    @reactive.effect
    async def _vistos_de_outras_sessoes():
        _marcacoes_no_disco()
        if _dia_do_historico() is not None:
            return
        marcas = manual_arquivo.marcacoes_por_chave()
        recados = []
        for posicao, linha in list(_pagina_atual.items()):
            for tipo in gravacao.TIPOS_VISTO:
                gravado, quem = cp.visto_gravado(linha, tipo, marcas)
                if gravado == linha["marcado"][tipo] and (not gravado or quem is None or quem == linha["quem"][tipo]):
                    continue
                linha["marcado"][tipo] = gravado
                linha["quem"][tipo] = quem if gravado else None
                _lidos[f"vst_{tipo}_{posicao}"] = gravado
                recados.append(
                    {"visto": f"{tipo}-{posicao}", "marcado": gravado, "quem": cp.nome_legivel(quem) if gravado else ""}
                )
        if recados:
            await session.send_custom_message("ppfVistos", recados)

    @reactive.effect
    async def _vistos_da_pagina():
        mudancas = []
        for posicao in _posicoes():
            for tipo in gravacao.TIPOS_VISTO:
                campo = f"vst_{tipo}_{posicao}"
                if campo not in input:
                    continue
                valor = bool(input[campo]())
                if _lidos.get(campo) == valor:
                    continue
                _lidos[campo] = valor
                mudancas.append((posicao, tipo, valor))
        if _tabela_velha():
            return
        for posicao, tipo, valor in mudancas:
            await _tratar_visto(posicao, tipo, valor)

    def _tratar_pagamento(posicao: int, texto_valor, banco_lido) -> None:
        linha = _titulo_da_linha(posicao)
        if linha is None:
            return
        valor = cp.numero(texto_valor)
        banco = (banco_lido or "").strip() or None
        juros = cp.juros_derivado(valor, linha.get("valor_original"))
        novo = {"valor_pago": valor, "juros": juros, "banco": banco}
        if linha.get("pagamento") == novo:
            return
        if _barrar("processar_pagamento"):
            return
        anterior = linha.get("pagamento")
        linha["pagamento"] = novo

        ident = linha["id"]
        atual = linha.get("valor_original")
        titulo = linha.get("valor_titulo") or atual
        eh_uma_parte = eh_parte(ident)
        vazio = valor is None or valor == 0
        revenda = linha.get("revenda") or _revenda() or ""
        desconto = (
            round(float(atual) - valor, 2)
            if valor
            and atual
            and 0 < round(float(atual) - valor, 2) <= _desconto_ate(revenda, {}, linha.get("cnpj"), atual) + 0.0001
            else 0.0
        )
        divide = bool(valor and atual and 0 < round(valor, 2) < round(float(atual), 2) and banco and not desconto)
        desfaz_parte = eh_uma_parte and vazio
        desfaz_tudo = bool(
            not eh_uma_parte
            and linha.get("tem_partes")
            and (vazio or (titulo and valor >= round(float(titulo), 2) - 0.005))
        )

        def voltar_campo(motivo: str) -> None:
            linha["pagamento"] = anterior
            if anterior and f"pg_valor_{posicao}" in input:
                ui.update_text(
                    f"pg_valor_{posicao}",
                    value=_reais(anterior["valor_pago"]) if anterior["valor_pago"] is not None else "",
                )
            _avisar(motivo, titulo="Contas a Pagar")

        if (divide or desfaz_parte or desfaz_tudo) and _dia_do_historico() is not None:
            voltar_campo(
                'No Histórico a tabela é um retrato: dividir o título, ou desfazer a divisão, é só em "Atual".'
            )
            return
        mudou_as_partes = False
        try:
            if divide:
                nova, resto = gravacao.dividir_parte(
                    ident,
                    revenda,
                    valor,
                    banco,
                    float(titulo or 0),
                    cp.base_do_titulo(linha),
                    cp.numeros_usados(base_do(ident)),
                )
                manual_arquivo.editar_pagamento(
                    nova,
                    resto,
                    None,
                    banco,
                    _usuario(),
                    valor_original=resto,
                )
                manual_arquivo.registrar_divisao(nova, _usuario())
                pagar_marcado, quem_marcou = cp.visto_gravado(linha, "pagar", manual_arquivo.marcacoes_por_chave())
                if pagar_marcado:
                    manual_arquivo.marcar(nova, "pagar", quem_marcou or linha["quem"].get("pagar") or _usuario())
                if eh_uma_parte:
                    manual_arquivo.editar_pagamento(
                        ident,
                        valor,
                        juros,
                        banco,
                        _usuario(),
                        valor_original=valor,
                    )
                else:
                    manual_arquivo.editar_pagamento(ident, valor, juros, banco, _usuario())
                mudou_as_partes = True
                _avisar(
                    f"Título dividido: {_reais(valor)} ficam nesta linha e "
                    f"{_reais(resto)} vão para a linha nova (\u29c9), no fim deste "
                    "título" + (", já marcada para pagar" if pagar_marcado else "") + " — escolha o banco dela.",
                    tipo="success",
                    titulo="Contas a Pagar",
                )
            elif desfaz_parte:
                recusa = _desfazer_uma_parte(ident)
                if recusa:
                    voltar_campo(recusa)
                    return
                mudou_as_partes = True
                _avisar("Parte desfeita: o valor dela voltou para o título.", tipo="success", titulo="Contas a Pagar")
            else:
                if desfaz_tudo:
                    apagadas, recusadas, _ = gravacao.desfazer_partes(base=ident, devolver_a_base=False)
                    if recusadas:
                        voltar_campo(
                            f"{len(recusadas)} parte(s) deste título já foram enviadas para pagar: a divisão fica."
                        )
                        return
                    manual_arquivo.desfazer_partes(apagadas, _usuario())
                    if vazio:
                        valor = round(float(titulo), 2)
                        if f"pg_valor_{posicao}" in input:
                            ui.update_text(f"pg_valor_{posicao}", value=_reais(valor))
                    juros = cp.juros_derivado(valor, titulo)
                    linha["pagamento"] = {"valor_pago": valor, "juros": juros, "banco": banco}
                    mudou_as_partes = True
                    _avisar(
                        "Divisão desfeita: o título voltou a uma linha só.", tipo="success", titulo="Contas a Pagar"
                    )
                gravacao.gravar_pagamento(
                    ident,
                    revenda,
                    valor_pago=valor,
                    juros=juros,
                    banco=banco,
                    base=cp.base_do_titulo(linha),
                )
                manual_arquivo.editar_pagamento(ident, valor, juros, banco, _usuario())
                if desconto:
                    _avisar(
                        f"{_reais(desconto)} a menos que o título: ele não é dividido, e a baixa no ERP leva "
                        "a diferença como desconto.",
                        tipo="message",
                        titulo="Contas a Pagar",
                    )
            _incrementar(marcacoes_versao)
            if mudou_as_partes:
                _so_partes["pendente"] = True
                _incrementar(partes_versao)
        except Exception as erro:
            _avisar(
                f"Falhou ao gravar: {str(erro)[:140]}",
                tipo="error",
                titulo="Contas a Pagar",
            )

    def _desfazer_uma_parte(ident: str) -> str | None:
        apagadas, recusadas, pago_da_base = gravacao.desfazer_partes([ident])
        if recusadas:
            return "Esta parte, ou o título dela, já foi enviado para pagar — a parte não sai mais daqui."
        manual_arquivo.desfazer_partes(apagadas, _usuario())
        dono = base_do(ident)
        if dono in pago_da_base:
            antes = manual_arquivo.pagamentos_por_titulo().get(dono) or {}
            manual_arquivo.editar_pagamento(
                dono,
                pago_da_base[dono],
                antes.get("juros"),
                antes.get("banco"),
                _usuario(),
            )
        return None

    def _pedir_exclusao_parte(posicao: int) -> None:
        if _barrar("processar_pagamento"):
            return
        linha = _titulo_da_linha(posicao)
        if linha is None or not eh_parte(linha["id"]):
            return
        if _dia_do_historico() is not None:
            _avisar('No Histórico a tabela é um retrato: excluir a parte é só em "Atual".', titulo="Contas a Pagar")
            return
        linha_da_acao.set(linha)
        ui.modal_show(
            ui.modal(
                ui.p(f"Excluir esta parte de “{linha['rotulo']}”?"),
                ui.p(
                    "O valor dela volta para o título, que fica com o valor original.", class_="text-muted small mb-0"
                ),
                title="Excluir parte do rateio",
                easy_close=True,
                footer=ui.TagList(
                    ui.modal_button("Cancelar", class_="btn btn-secondary"),
                    ui.input_action_button("confirmar_excluir_parte", "Excluir parte", class_="btn btn-danger"),
                ),
            )
        )

    @reactive.effect
    @reactive.event(input.confirmar_excluir_parte)
    def _excluir_parte():
        ui.modal_remove()
        if _barrar("processar_pagamento"):
            return
        linha = linha_da_acao()
        if linha is None or not eh_parte(linha["id"]):
            return
        try:
            recusa = _desfazer_uma_parte(linha["id"])
        except Exception as erro:
            _avisar(f"Falhou ao excluir a parte: {str(erro)[:140]}", tipo="error", titulo="Contas a Pagar")
            return
        if recusa:
            _avisar(recusa, titulo="Contas a Pagar")
            return
        _incrementar(marcacoes_versao)
        _so_partes["pendente"] = True
        _incrementar(partes_versao)
        _avisar("Parte excluída: o valor dela voltou para o título.", tipo="success", titulo="Contas a Pagar")

    @reactive.effect
    def _pagamentos_da_pagina():
        mudancas = []
        for posicao in _posicoes():
            campo_valor = f"pg_valor_{posicao}"
            campo_banco = f"pg_banco_{posicao}"
            if campo_valor not in input or campo_banco not in input:
                continue
            lido = (input[campo_valor](), input[campo_banco]())
            chave = f"pg_{posicao}"
            if _lidos.get(chave) == lido:
                continue
            _lidos[chave] = lido
            mudancas.append((posicao, lido))
        if _tabela_velha():
            return
        for posicao, (texto, banco) in mudancas:
            _tratar_pagamento(posicao, texto, banco)

    def _pode_editar_justificativa() -> bool:
        return _pode("justificar_ppf") and _dia_do_historico() is None

    def _autoria_justificativa(ident: str) -> dict | None:
        daqui = manual_arquivo.autoria_da_justificativa(ident)
        if daqui:
            return daqui
        try:
            base = d.justificativas()
            linha = base.filter(pl.col("id_unico") == ident) if not base.is_empty() else base
        except Exception:
            return None
        if linha.is_empty():
            return None
        r = linha.row(-1, named=True)
        return {c: r.get(c) for c in ("criado_por", "criado_em", "atualizado_por", "atualizado_em")}

    def _abrir_justificativa(posicao: int) -> None:
        linha = _titulo_da_linha(posicao)
        if linha is None:
            return
        linha_da_acao.set(linha)
        editar = _pode_editar_justificativa()
        dono = _autoria_justificativa(linha["id"])
        autoria = None
        if dono and dono["criado_por"] and dono["criado_em"]:
            texto_autoria = f"Criado por {cp.nome_legivel(dono['criado_por'])} em {dono['criado_em']:%d/%m/%Y %H:%M}"
            if dono["atualizado_por"] and dono["atualizado_em"] and dono["atualizado_em"] != dono["criado_em"]:
                texto_autoria += (
                    f" · Editado por {cp.nome_legivel(dono['atualizado_por'])} em "
                    f"{dono['atualizado_em']:%d/%m/%Y %H:%M}"
                )
            autoria = ui.p(texto_autoria, class_="text-muted small mb-1")
        area = ui.input_text_area(
            session.ns("texto_justificativa"),
            None,
            value=linha["justificativa"] or "",
            width="100%",
            height="140px",
            placeholder=("Por que este título está assim?" if editar else "Sem justificativa."),
        )
        for no in area.children:
            if getattr(no, "name", None) == "textarea":
                no.attrs["maxlength"] = "500"
                if not editar:
                    no.attrs["disabled"] = "disabled"
        ui.modal_show(
            ui.modal(
                ui.p(linha["rotulo"], class_="fw-bold"),
                autoria,
                area,
                ui.p(
                    "Texto vazio apaga a justificativa."
                    if editar
                    else "Somente visualização — edição restrita ao financeiro.",
                    class_="text-muted small mb-0",
                ),
                title="Justificativa do título",
                easy_close=True,
                footer=ui.TagList(
                    ui.modal_button("Cancelar", class_="btn btn-secondary"),
                    ui.input_action_button(
                        "gravar_justificativa",
                        "Gravar",
                        class_="btn btn-primary",
                    ),
                )
                if editar
                else ui.modal_button("Fechar", class_="btn btn-secondary"),
            )
        )

    def _abrir_anexos(posicao: int) -> None:
        if _barrar("anexar_titulo"):
            return
        linha = _titulo_da_linha(posicao)
        if linha is None:
            return
        titulo_dos_anexos.set(
            (
                linha["id"],
                linha["rotulo"],
                linha.get("vencimento"),
                linha.get("doc_norm") or "",
            )
        )
        _limpar_recados()
        ui.modal_show(_modal_anexos(linha["rotulo"]))

    def _pedir_exclusao_titulo(posicao: int) -> None:
        if _barrar("excluir_titulo"):
            return
        linha = _titulo_da_linha(posicao)
        if linha is None:
            return
        linha_da_acao.set(linha)
        ui.modal_show(
            ui.modal(
                ui.p(f"Tirar “{linha['rotulo']}” da lista?"),
                ui.p(
                    "O título sai da lista para todos até a próxima atualização "
                    "do Contas a Pagar: se ainda estiver em aberto no ERP, ele "
                    "volta, como no sistema antigo. O dado do ERP não é apagado.",
                    class_="text-muted small mb-0",
                ),
                title="Confirmar exclusão",
                easy_close=True,
                footer=ui.TagList(
                    ui.modal_button("Cancelar", class_="btn btn-secondary"),
                    ui.input_action_button(
                        "confirmar_excluir_titulo",
                        "Excluir",
                        class_="btn btn-danger",
                    ),
                ),
            )
        )

    @reactive.effect
    def _acoes_da_pagina():
        velha = _tabela_velha()
        for posicao in _posicoes():
            if _clicou(f"lin_just_{posicao}") and not velha:
                _abrir_justificativa(posicao)
            clicou_anexo = _clicou(f"lin_anexo_{posicao}")
            clicou_olho = _clicou(f"lin_olho_{posicao}")
            if (clicou_anexo or clicou_olho) and not velha:
                _abrir_anexos(posicao)
            if _clicou(f"lin_excluir_{posicao}") and not velha:
                _pedir_exclusao_titulo(posicao)
            if _clicou(f"lin_excluir_parte_{posicao}") and not velha:
                _pedir_exclusao_parte(posicao)

    @reactive.effect
    @reactive.event(input.anexo_fora)
    def _anexo_alem_das_interativas():
        posicao = _na_tela["pos"].get((input.anexo_fora() or {}).get("id"))
        if posicao is not None and not _tabela_velha():
            _abrir_anexos(posicao)

    linha_da_acao = reactive.value(None)

    @reactive.effect
    @reactive.event(input.gravar_justificativa)
    def _gravar_justificativa():
        ui.modal_remove()
        if _barrar("justificar_ppf"):
            return
        if _dia_do_historico() is not None:
            _avisar("No Histórico a justificativa é só para leitura.", titulo="Justificativa")
            return
        linha = linha_da_acao()
        if linha is None:
            return
        texto = (input.texto_justificativa() or "").strip()[:500]
        antiga = _autoria_justificativa(linha["id"]) or {}
        try:
            manual_arquivo.justificar(
                linha["id"],
                _revenda() or "",
                texto,
                _usuario(),
                criado=(antiga.get("criado_por"), antiga.get("criado_em")),
            )
            _incrementar(overlay_versao)
            _avisar(
                "Justificativa apagada." if not texto else "Justificativa gravada.",
                tipo="success",
                titulo="Justificativa",
            )
        except Exception as erro:
            _avisar(
                f"Falhou ao gravar: {str(erro)[:120]}",
                tipo="error",
                titulo="Justificativa",
            )

    @reactive.effect
    @reactive.event(input.confirmar_excluir_titulo)
    def _excluir_titulo():
        ui.modal_remove()
        if _barrar("excluir_titulo"):
            return
        linha = linha_da_acao()
        if linha is None:
            return
        try:
            manual_arquivo.excluir_titulo(
                linha["id"], _revenda() or "", _usuario(), fora_do_control=bool(linha.get("fora_do_control"))
            )
        except Exception as erro:
            _avisar(
                f"Falhou ao excluir: {str(erro)[:120]}",
                tipo="error",
                titulo="Excluir título",
            )
            return
        _incrementar(overlay_versao)
        _avisar(
            "Título fora da lista. O ERP não foi alterado.",
            tipo="success",
            titulo="Excluir título",
        )

    def _celula_texto(valor, classe=None):
        return ui.tags.td(str(valor if valor is not None else ""), class_=classe)

    def _celula_contabil(valor) -> ui.Tag:
        if valor is None:
            return ui.tags.td("", class_="ppf-cel-valor")
        texto = _reais(valor)
        negativo = texto.startswith("-")
        numero = texto.replace("-", "").replace("R$", "").strip()
        return ui.tags.td(
            ui.div(
                ui.span("R$", class_="ppf-moeda"),
                ui.span(("-" if negativo else "") + numero, class_="ppf-numero"),
                class_="ppf-valor-contabil",
            ),
            class_="ppf-cel-valor",
        )

    async def _bancos_da_revenda() -> dict:
        parte = dc.da_revenda(await composicao_base(), _revenda())
        bancos = {}
        for chave in dc.bancos_para_lancar(parte):
            bancos[dc.rotulo_banco(chave, None)] = dc.rotulo_banco(chave, _revenda())
        for extra in dc.destinos_extra_pagamento(_revenda()):
            bancos.setdefault(extra, extra)
        return bancos

    def _banco_padrao(bancos: dict, revenda: str | None = None) -> str:
        mapa = carregar_json("parametros_financeiro").get("banco_pagamento_por_revenda") or {}
        alvo = chave_revenda(revenda or _revenda())
        escolhido = next(
            (banco for nome, banco in mapa.items() if not str(nome).startswith("_") and chave_revenda(nome) == alvo),
            None,
        )
        if escolhido in bancos:
            return escolhido
        return next(iter(bancos), "")

    async def _pagos_recentes(cnpjs: set) -> dict:
        if not cnpjs:
            return {}
        pagos = await asyncio.to_thread(d.titulos_pagos)
        pagos = d.filtrar_por_revenda(pagos, _revenda())
        if pagos.is_empty() or "PGMOVBAI_CGC" not in pagos.columns:
            return {}
        pagos = (
            pagos.filter(pl.col("PGMOVBAI_CGC").is_in(list(cnpjs)))
            .sort("PGMOVBAI_DTP", descending=True, nulls_last=True)
            .group_by("PGMOVBAI_CGC", maintain_order=True)
            .head(3)
        )
        tem_banco = "banco" in pagos.columns
        recentes: dict = {}
        for linha in pagos.iter_rows(named=True):
            recentes.setdefault(linha["PGMOVBAI_CGC"], []).append(
                (
                    linha["DATA"].strftime("%d/%m/%Y") if linha.get("DATA") else "",
                    linha["PGMOVBAI_DTP"].strftime("%d/%m/%Y") if linha.get("PGMOVBAI_DTP") else "",
                    str(linha.get("PGMOVBAI_NDUPL") or ""),
                    float(linha.get("PGMOVBAI_VALOR") or 0),
                    str(linha.get("banco") or "") if tem_banco else "",
                )
            )
        return recentes

    def _tooltip_pagos(recentes: list | None) -> ui.Tag:
        if not recentes:
            corpo = ui.tags.em("Sem títulos pagos encontrados.")
        else:
            total = sum(r[3] for r in recentes)
            corpo = ui.tags.table(
                ui.tags.thead(
                    ui.tags.tr(*[ui.tags.th(t) for t in ("Vencimento", "Pagamento", "Documento", "Valor", "Banco")])
                ),
                ui.tags.tbody(
                    *[
                        ui.tags.tr(
                            ui.tags.td(venc),
                            ui.tags.td(pago),
                            ui.tags.td(doc),
                            ui.tags.td(_reais(valor)),
                            ui.tags.td(banco),
                        )
                        for venc, pago, doc, valor, banco in recentes
                    ]
                ),
                ui.tags.tfoot(
                    ui.tags.tr(
                        ui.tags.td("Total", class_="ppf-tooltip-total"),
                        ui.tags.td(),
                        ui.tags.td(),
                        ui.tags.td(_reais(total), class_="ppf-tooltip-total"),
                        ui.tags.td(),
                    )
                ),
            )
        return ui.div(
            ui.div("Pagamentos recentes", class_="ppf-tooltip-titulo"),
            corpo,
            class_="ppf-tooltip-pagos",
        )

    def _documentos_do_olho() -> dict:
        return an.documentos_do_olho()

    async def _contexto_da_tabela(fatia: pl.DataFrame, docs: dict | None = None) -> dict:
        permissao_visto = {tipo: _pode(chave) for tipo, chave in gravacao.PERMISSAO_VISTO.items()}
        assinatura_versao()
        bancos = await _bancos_da_revenda()
        return {
            "pode_justificar": _pode("justificar_ppf"),
            "pode_anexar": _pode("anexar_titulo"),
            "pode_excluir": _pode("excluir_titulo"),
            "pode_pagar": _pode("processar_pagamento"),
            "ver_quem_lancou": _pode("ver_quem_lancou"),
            "permissao_visto": permissao_visto,
            "sem_permissao": not any(permissao_visto.values()),
            "exige_auditoria": exige_auditoria_para_pagar(_usuario()),
            "tenho_assinatura": permissao_visto["assinar"] and manual_arquivo.assinatura_de(_usuario()) is not None,
            "revenda_dispensa": fabricas.dispensa_auditoria_na_revenda(_revenda()),
            "fabrica_da_revenda": fabricas.fabrica_da_revenda(_revenda()) or {},
            "eu": cp.nome_legivel(_usuario()),
            "bancos": bancos,
            "banco_padrao": _banco_padrao(bancos),
            "icones_dos_destinos": json.dumps(dc.icones_dos_destinos(), ensure_ascii=False),
            "bandeiras": dc.bandeiras_da_rede(),
            "do_cartao": dc.titulos_do_cartao(),
            "limites_de_desconto": {},
            "hoje": date.today(),
            "mostra_revenda": _escopo_multiplo() and "_revenda_linha" in fatia.columns,
            "recentes": (
                await _pagos_recentes(set(fatia["_cnpj"].drop_nulls().to_list())) if input.analise() else None
            ),
            "editados": manual_arquivo.pagamentos_por_titulo(),
            **(docs or _documentos_do_olho()),
            "origem_rede": d.origem_do_olho_da_rede(),
            "quantos_da_rede": d.quantos_da_rede_por_titulo(),
            "todas_fabricas": fabricas.fabricas(),
            "quem_dividiu": manual_arquivo.quem_dividiu(),
            "pre_auditoria": d.pre_auditoria_dos_titulos() if _pode(CHAVE_VER_PRE_AUDITORIA) else None,
            "gastos_veiculo": cp.gastos_com_veiculo() if _pode(CHAVE_VER_GASTO_VEICULO) else None,
            "dias_a_frente_por_revenda": {},
        }

    @reactive.effect
    @reactive.event(input.pa_fechar_baloes)
    def _fechar_baloes_da_pre_auditoria():
        for nome in (input.pa_fechar_baloes() or {}).get("ids") or []:
            if re.fullmatch(r"pa(?:999)?_balao_\d+", str(nome)):
                ui.update_popover(str(nome), show=False)

    def _linha_contas(fatia: pl.DataFrame, i: int, posicao: int, ligado: bool, ctx: dict, vence: str | None):
        bancos = ctx["bancos"]
        permissao_visto = ctx["permissao_visto"]
        recentes = ctx["recentes"]
        mostra_revenda = ctx["mostra_revenda"]
        ident = fatia["_id"][i]
        nome = str(fatia["Fornecedor"][i] or "")
        fabrica = fabricas.fabrica_do_fornecedor(nome, ctx["todas_fabricas"])
        realca = fabrica is not None and (
            fabrica.get("realce_em_toda_revenda") or fabrica["chave"] == ctx["fabrica_da_revenda"].get("chave")
        )
        pagou = str(fatia["_pagou"][i] or "") == "Sim"
        enviado = "_enviado" in fatia.columns and str(fatia["_enviado"][i] or "") == "Sim"
        entrada_manual = str(fatia["_entrada_manual"][i] or "") == "Sim"
        lancou = None
        if ctx["ver_quem_lancou"]:
            por = "Dash" if entrada_manual else fatia["_lancado_por"][i]
            alterou = fatia["_alterado_por"][i]
            lancou = f"Lançado por {por}" if por else "Sem registro no ERP"
            if alterou and alterou != por:
                lancou += f" · alterado por {alterou}"
        dispensa = not ctx["exige_auditoria"] and (
            entrada_manual or ctx["revenda_dispensa"] or bool(fabrica and fabrica.get("dispensa_auditoria"))
        )
        marcado = {tipo: str(fatia[f"_{tipo}"][i] or "") == "Sim" for tipo in gravacao.TIPOS_VISTO}
        quem = {
            tipo: cp.nome_legivel(fatia[f"_{tipo}_user"][i])
            if marcado[tipo] and f"_{tipo}_user" in fatia.columns
            else ""
            for tipo in gravacao.TIPOS_VISTO
        }

        valor_original = fatia["_valor"][i]
        revenda_da_linha = fatia["_revenda_linha"][i] if mostra_revenda else _revenda()
        exibido = cp.valor_pago_exibido(
            valor_original,
            fatia["_pago"][i],
            fatia["_juros"][i],
            fatia["_pagou"][i],
            _desconto_ate(revenda_da_linha, ctx["limites_de_desconto"], fatia["_cnpj"][i], valor_original),
        )
        texto_pago = _reais(exibido) if exibido is not None else ""
        banco_dado = str(fatia["Banco"][i]).strip() or None if fatia["Banco"][i] else None
        if banco_dado and banco_dado not in bancos:
            chave_dado = dc.chave_do_rotulo(banco_dado, _revenda())
            if chave_dado:
                banco_dado = dc.rotulo_banco(chave_dado, None)
        banco_exibido = (
            banco_dado
            or dc.banco_do_cartao(ident, bancos, ctx.get("do_cartao") or set())
            or (_banco_padrao(bancos, fatia["_revenda_linha"][i]) if mostra_revenda else ctx["banco_padrao"])
        )
        opcoes_banco = dict(bancos)
        if banco_exibido and banco_exibido not in opcoes_banco:
            opcoes_banco[banco_exibido] = banco_exibido

        retrato = None
        if ident:
            valor_mostrado = cp.numero(texto_pago)
            retrato = {
                "id": ident,
                "rotulo": f"{nome} — {fatia['Documento'][i]}",
                "justificativa": fatia["_justificativa"][i],
                "marcado": dict(marcado),
                "quem": {
                    tipo: fatia[f"_{tipo}_user"][i] if marcado[tipo] and f"_{tipo}_user" in fatia.columns else None
                    for tipo in gravacao.TIPOS_VISTO
                },
                "pagou": pagou,
                "dispensa_auditoria": dispensa,
                "fora_do_control": "_no_erp" in fatia.columns and fatia["_no_erp"][i] == 0,
                "rotulo_linha": nome,
                "vencimento": fatia["_dia"][i],
                "documento_cru": str(fatia["Documento"][i] or ""),
                "doc_norm": str(fatia["_doc_norm"][i] or "") if "_doc_norm" in fatia.columns else "",
                "descricao_despesa": (fatia["Tipo"][i] or None) if "Tipo" in fatia.columns else None,
                "tipo_doc": (fatia["Tipo Doc"][i] or None) if "Tipo Doc" in fatia.columns else None,
                "cnpj": str(fatia["_cnpj"][i] or ""),
                "revenda": fatia["_revenda_linha"][i] if "_revenda_linha" in fatia.columns else None,
                "valor_original": valor_original,
                "valor_titulo": fatia["_valor_titulo"][i],
                "tem_partes": bool(fatia["_tem_partes"][i]),
                "pagamento": {
                    "valor_pago": valor_mostrado,
                    "juros": cp.juros_derivado(valor_mostrado, valor_original),
                    "banco": banco_exibido or None,
                },
            }
        fora = "Página muito grande: use 50 ou 100 por página" if not ligado else None

        classes = []
        if vence == "hoje":
            classes.append("ppf-linha-hoje")
        elif vence == "vencida":
            classes.append("ppf-linha-vencida")
        if realca:
            classes.append("ppf-linha-fabrica")
        if enviado or pagou:
            classes.append("ppf-linha-enviada")
        if dispensa:
            classes.append("ppf-dispensa-auditoria")
        if cp.entrada_manual_em_azul(entrada_manual, vence):
            classes.append("ppf-linha-manual")

        eh_uma_parte = eh_parte(ident)
        pre_auditoria_dos_titulos = ctx.get("pre_auditoria")
        pre_auditoria_do_titulo = (
            pre_auditoria_dos_titulos.get(base_do(ident)) if pre_auditoria_dos_titulos and ident else None
        )
        icone_da_pre_auditoria = None
        if pre_auditoria_do_titulo is not None:
            icone_da_pre_auditoria = _pre_auditoria_da_linha(
                pre_auditoria_do_titulo,
                f"{nome} — {fatia['Documento'][i]}",
                f"pa_balao_{posicao}",
                session.ns("pa_fechar_baloes"),
            )
        elif pre_auditoria_dos_titulos is not None:
            fora_da_carga = "_no_erp" in fatia.columns and fatia["_no_erp"][i] == 0
            icone_da_pre_auditoria = _pre_auditoria_nao_conferida(
                _motivo_sem_pre_auditoria(
                    pagou,
                    entrada_manual,
                    fora_da_carga,
                    fatia["_dia"][i],
                    ctx["hoje"] + timedelta(days=_dias_a_frente_da_pre_auditoria(revenda_da_linha, ctx)),
                )
            )
        sem_boleto = cp.tipo_do_olho(
            ident, str(fatia["_doc_norm"][i] or ""), nome, ctx, gravacao.titulo_sem_boleto, an.antigos_do_titulo
        )
        olho = abrir = None
        bandeira = (ctx.get("bandeiras") or {}).get(base_do(ident)) if ident else None
        icone_destino = dc.icone_do_destino(banco_exibido, bandeira)
        icones_da_linha = (
            json.dumps(dc.icones_com_a_bandeira(bandeira), ensure_ascii=False)
            if bandeira
            else ctx["icones_dos_destinos"]
        )
        if sem_boleto is not None or icone_destino:
            titulo_olho = (
                "Nota sem boleto anexado — pagamento por Pix"
                if sem_boleto
                else "PDF salvo"
                if sem_boleto is not None
                else "Sem PDF salvo"
            )
            if icone_destino:
                no_cartao = f" ({bandeira.capitalize()})" if bandeira and dc.icone_da_bandeira(bandeira) else ""
                titulo_olho = f"Pagamento: {banco_exibido}{no_cartao}. {titulo_olho}"
            normal = ("img/ppf/pix-icon.svg" if sem_boleto else "img/ppf/view.svg") if sem_boleto is not None else ""
            icone = ui.tags.img(
                src=icone_destino or normal,
                class_="ppf-cel-anexo ppf-cel-olho"
                + (" ppf-cel-pix" if sem_boleto and not icone_destino else "")
                + (" ppf-cel-destino" if icone_destino else ""),
                alt="",
                data_icone_normal=normal,
                data_icones=icones_da_linha,
            )
            abrir = _pdf_para_abrir(ident, str(fatia["_doc_norm"][i] or ""), nome, ctx) if ident else None
            if abrir:
                abre = _o_que_o_olho_abre(
                    ident, str(fatia["_doc_norm"][i] or ""), nome, ctx, bool(marcado.get("assinar"))
                )
                titulo_olho = f"{titulo_olho}. {abre}" if abre else titulo_olho
            olho = (
                ui.tags.a(icone, href=abrir, target="_blank", rel="noopener", class_="ppf-olho-link", title=titulo_olho)
                if abrir
                else ui.input_action_button(
                    f"lin_olho_{posicao}",
                    icone,
                    class_="ppf-btn-linha ppf-btn-olho",
                    title=titulo_olho,
                    disabled=not ligado,
                )
            )
        cnpj = fatia["_cnpj"][i]
        gasto_com_veiculo = cp.gasto_com_veiculo_do_titulo(cnpj, fatia["_doc_norm"][i], ctx.get("gastos_veiculo"))

        celula_valor = _celula_contabil(_valor_mostrado(fatia, i))
        _extra["geracao"] = _extra.get("geracao", 0) + 1
        celula_valor.attrs["id"] = f"{session.ns('valor')}-{posicao}-{_extra['geracao']}"
        _extra["celula"][posicao] = celula_valor.attrs["id"]

        celulas = [
            *([_celula_texto(fatia["_revenda_linha"][i])] if mostra_revenda else []),
            _celula_texto(fatia["Vencimento"][i]),
            ui.tags.td(
                ui.span(nome, class_="ppf-fornecedor-nome"),
                ui.span(" \u29c9", title="Parte de título dividido") if eh_uma_parte else None,
                _legenda_da_parte(ctx["quem_dividiu"].get(ident)) if eh_uma_parte else None,
                _tooltip_pagos(recentes.get(cnpj)) if recentes is not None else None,
                class_="ppf-cel-fornecedor" + (" ppf-cel-fabrica" if realca else ""),
                style=f"color: {fabrica['cor_texto']};" if realca and fabrica.get("cor_texto") else None,
            ),
            _celula_texto(fatia["Tipo"][i]),
            _celula_texto(fatia["C. Custo"][i]),
            ui.tags.td(
                ui.div(
                    ui.span(str(fatia["Documento"][i] or ""), class_="ppf-doc-num", data_lancou=lancou),
                    ui.span(
                        ui.input_action_button(
                            f"lin_anexo_{posicao}",
                            ui.tags.img(src="img/ppf/file-upload-2.svg", class_="ppf-cel-anexo", alt=""),
                            class_="ppf-btn-linha ppf-btn-anexo",
                            title="Enviar/Substituir PDF" if ctx["pode_anexar"] else "Sem permissão",
                            disabled=not (ligado and ctx["pode_anexar"]),
                        )
                        if ligado or not ident
                        else ui.tags.button(
                            ui.tags.img(src="img/ppf/file-upload-2.svg", class_="ppf-cel-anexo", alt=""),
                            type="button",
                            class_="btn ppf-btn-linha ppf-btn-anexo ppf-btn-anexo-fora",
                            title="Enviar/Substituir PDF" if ctx["pode_anexar"] else "Sem permissão",
                            disabled=None if ctx["pode_anexar"] else "disabled",
                            data_id=ident,
                            data_entrada=session.ns("anexo_fora"),
                        ),
                        olho,
                        _caminhao_do_gasto_com_veiculo(gasto_com_veiculo) if gasto_com_veiculo else None,
                        class_="ppf-pdf-acoes",
                    ),
                    class_="ppf-doc-acoes",
                ),
            ),
            _celula_texto(fatia["Tipo Doc"][i]),
            celula_valor,
            ui.tags.td(
                ui.input_text(
                    f"pg_valor_{posicao}",
                    "",
                    value=texto_pago,
                    update_on="blur",
                )
                if ligado and ctx["pode_pagar"] and not pagou
                else ui.span(
                    texto_pago,
                    class_="ppf-campo-travado",
                ),
                class_="ppf-cel-valor ppf-cel-campo campo-reais",
            ),
            ui.tags.td(
                _reais(cp.juros_da_linha(fatia, i, ctx["editados"])),
                class_="ppf-cel-valor ppf-cel-juros",
                data_original=f"{float(valor_original or 0):.2f}",
            ),
            ui.tags.td(
                ui.input_select(
                    f"pg_banco_{posicao}",
                    "",
                    choices=opcoes_banco,
                    selected=banco_exibido,
                )
                if ligado and ctx["pode_pagar"] and not pagou
                else ui.span(
                    banco_exibido or "",
                    class_="ppf-campo-travado",
                ),
                class_="ppf-cel-campo",
            ),
        ]

        for tipo in gravacao.TIPOS_VISTO:
            interativo = ligado and permissao_visto[tipo]
            if tipo == "pagar" and pagou:
                interativo = False
            do_titulo = eh_uma_parte and tipo in ("auditoria", "conselho")
            if do_titulo:
                interativo = False
            motivo_assinar = None
            if tipo == "assinar" and not marcado["assinar"]:
                if abrir is None:
                    motivo_assinar = "Sem documento para assinar"
                elif permissao_visto["assinar"] and not ctx["tenho_assinatura"]:
                    motivo_assinar = "Cadastre sua assinatura para assinar"
                if motivo_assinar:
                    interativo = False
            if ctx["sem_permissao"]:
                dica = "Sem permissão"
            elif do_titulo:
                dica = "É a do título: marque na linha dele"
            elif motivo_assinar:
                dica = motivo_assinar
            elif marcado[tipo] and quem[tipo]:
                dica = f"Marcado por: {quem[tipo]}"
            elif tipo == "pagar" and ctx["exige_auditoria"] and permissao_visto["pagar"] and not marcado["auditoria"]:
                dica = MOTIVO_AGUARDA_AUDITORIA
            else:
                dica = fora
            celulas.append(
                ui.tags.td(
                    ui.div(
                        ui.input_checkbox(
                            f"vst_{tipo}_{posicao}",
                            "",
                            value=marcado[tipo],
                        )
                        if interativo
                        else ui.tags.input(
                            type="checkbox",
                            checked="checked" if marcado[tipo] else None,
                            disabled="disabled",
                            class_="ppf-visto-travado",
                        ),
                        icone_da_pre_auditoria if tipo == "auditoria" else None,
                        ui.input_action_button(
                            f"lin_just_{posicao}",
                            icon_svg("comment-dots", style="regular", a11y="deco"),
                            tabindex="-1",
                            class_="ppf-btn-linha ppf-btn-justif"
                            + (" tem-justificativa" if fatia["_justificativa"][i] else ""),
                            title=(
                                (
                                    f"Ver/Editar justificativa: {fatia['_justificativa'][i]}"
                                    if fatia["_justificativa"][i]
                                    else "Adicionar justificativa"
                                )
                                if ctx["pode_justificar"]
                                else (
                                    f"Ver justificativa: {fatia['_justificativa'][i]}"
                                    if fatia["_justificativa"][i]
                                    else "Ver justificativa"
                                )
                            ),
                            disabled=not ligado,
                        )
                        if tipo == "pagar"
                        else None,
                        ui.input_action_button(
                            f"lin_excluir_{posicao}",
                            icon_svg("trash", a11y="deco"),
                            class_="ppf-btn-linha ppf-btn-excluir",
                            title="Excluir título",
                        )
                        if (
                            tipo == "conselho"
                            and ligado
                            and ctx["pode_excluir"]
                            and not eh_uma_parte
                            and not entrada_manual
                        )
                        else None,
                        ui.input_action_button(
                            f"lin_excluir_parte_{posicao}",
                            icon_svg("trash", a11y="deco"),
                            class_="ppf-btn-linha ppf-btn-excluir ppf-btn-excluir-parte",
                            title="Excluir esta parte (o valor volta para o título)",
                        )
                        if tipo == "conselho" and eh_uma_parte and ligado and ctx["pode_pagar"]
                        else None,
                        class_="ppf-cel-controles",
                    ),
                    class_=f"ppf-cel-visto ppf-cel-{tipo}" + (" ppf-assinavel" if tipo == "assinar" and abrir else ""),
                    data_quem=quem[tipo],
                    data_eu=ctx["eu"],
                    data_visto=f"{tipo}-{posicao}",
                    title=dica,
                )
            )

        tr = ui.tags.tr(*celulas, class_=" ".join(classes) or None, data_id_unico=ident)
        return tr, retrato

    def _reiniciar_insercao() -> None:
        _na_tela["ids"], _na_tela["pos"] = [], {}
        _extra["posicoes"].clear()
        _extra["celula"].clear()
        posicoes_extra.set(())

    async def _so_as_linhas_que_mudaram(fatia: pl.DataFrame, ids: list) -> bool:
        velhos = _na_tela["ids"]
        if not velhos or not all(ids):
            return False
        novos_set, velhos_set = set(ids), set(velhos)
        if [x for x in velhos if x in novos_set] != [x for x in ids if x in velhos_set]:
            return False
        entram = [x for x in ids if x not in velhos_set]
        saem = [x for x in velhos if x not in novos_set]
        if len(entram) + len(saem) > 20:
            return False

        tabela = f"#{session.ns('tabela_pagar')}"
        for ident in saem:
            posicao = _na_tela["pos"].pop(ident, None)
            _pagina_atual.pop(posicao, None)
            _extra["posicoes"].discard(posicao)
            _extra["celula"].pop(posicao, None)
            ui.remove_ui(f'{tabela} tr[data-id-unico="{ident}"]', multiple=True)

        ctx = await _contexto_da_tabela(fatia)
        for k, ident in enumerate(ids):
            if ident in _na_tela["pos"]:
                continue
            posicao = _extra["proxima"]
            _extra["proxima"] += 1
            hoje_, vencidas_ = cp.vencimentos([fatia["_dia"][k]], ctx["hoje"])
            vence = "hoje" if hoje_ else "vencida" if vencidas_ else None
            tr, retrato = _linha_contas(fatia, k, posicao, True, ctx, vence)
            if k == 0:
                ui.insert_ui(tr, selector=f"{tabela} tbody", where="afterBegin")
            else:
                ui.insert_ui(tr, selector=f'{tabela} tr[data-id-unico="{ids[k - 1]}"]', where="afterEnd")
            if retrato is not None:
                _pagina_atual[posicao] = retrato
            _na_tela["pos"][ident] = posicao
            _extra["posicoes"].add(posicao)

        for k, ident in enumerate(ids):
            if ident in entram:
                continue
            posicao = _na_tela["pos"][ident]
            retrato = _pagina_atual.get(posicao)
            if retrato is None:
                continue
            valor = fatia["_valor"][k]
            retrato["valor_titulo"] = fatia["_valor_titulo"][k]
            retrato["tem_partes"] = bool(fatia["_tem_partes"][k])
            if retrato.get("valor_original") != valor:
                retrato["valor_original"] = valor
                antiga = _extra["celula"].get(posicao)
                if antiga:
                    celula = _celula_contabil(_valor_mostrado(fatia, k))
                    _extra["geracao"] = _extra.get("geracao", 0) + 1
                    celula.attrs["id"] = f"{session.ns('valor')}-{posicao}-{_extra['geracao']}"
                    ui.insert_ui(celula, selector=f"#{antiga}", where="afterEnd")
                    ui.remove_ui(f"#{antiga}")
                    _extra["celula"][posicao] = celula.attrs["id"]
            revenda_da_linha = fatia["_revenda_linha"][k] if ctx["mostra_revenda"] else _revenda()
            exibido = cp.valor_pago_exibido(
                valor,
                fatia["_pago"][k],
                fatia["_juros"][k],
                fatia["_pagou"][k],
                _desconto_ate(revenda_da_linha, ctx["limites_de_desconto"], fatia["_cnpj"][k], valor),
            )
            mostrado = cp.numero(_reais(exibido)) if exibido is not None else None
            pagamento = retrato["pagamento"]
            pagamento["juros"] = cp.juros_derivado(pagamento["valor_pago"], valor)
            if mostrado != pagamento["valor_pago"] and f"pg_valor_{posicao}" in input:
                pagamento["valor_pago"] = mostrado
                pagamento["juros"] = cp.juros_derivado(mostrado, valor)
                ui.update_text(f"pg_valor_{posicao}", value=_reais(mostrado) if mostrado is not None else "")

        _na_tela["ids"] = list(ids)
        posicoes_extra.set(tuple(sorted(_extra["posicoes"])))
        return True

    @render.ui
    async def tabela_pagar():
        base = _com_overlay(await pagar_pronto())
        so_partes, _so_partes["pendente"] = _so_partes["pendente"], False
        if base.is_empty():
            _reiniciar_insercao()
            return ui.p("Sem conta a pagar para os filtros selecionados.")
        filtro_assinar = so_assinar()
        docs = None
        if filtro_assinar:
            docs = _documentos_do_olho()
            base = _so_os_de_assinar(base, docs)
        inicio, fim = paginador.janela(base.height)
        fatia = base.slice(inicio, fim - inicio)
        ids = fatia["_id"].to_list()
        if so_partes and await _so_as_linhas_que_mudaram(fatia, ids):
            req(False, cancel_output=True)

        ctx = await _contexto_da_tabela(fatia, docs)
        vence_hoje, vencidas = cp.vencimentos(fatia["_dia"].to_list(), ctx["hoje"])
        vence_hoje, vencidas = set(vence_hoje), set(vencidas)

        _reiniciar_insercao()
        _pagina_atual.clear()
        _geracao["n"] += 1
        linhas = []
        for i in range(fatia.height):
            vence = "hoje" if i in vence_hoje else "vencida" if i in vencidas else None
            tr, retrato = _linha_contas(
                fatia,
                i,
                i,
                i < LINHAS_INTERATIVAS and bool(ids[i]),
                ctx,
                vence,
            )
            if retrato is not None:
                _pagina_atual[i] = retrato
            linhas.append(tr)
        _na_tela["ids"] = list(ids)
        _na_tela["pos"] = {ident: i for i, ident in enumerate(ids) if ident}

        ordenaveis = dict(
            zip(
                (r for _c, r, _t in _COLUNAS_ORDEM_PAGAR),
                _cabecalho_varias("ord_pag", _COLUNAS_ORDEM_PAGAR, ordem_pagar()),
            )
        )
        assinar = ui.tags.th(
            ui.div(
                ui.span("Assinar"),
                ui.input_checkbox("pag_so_assinar", "", value=filtro_assinar),
                class_="ppf-th-filtro",
            ),
            title="Mostrar só os títulos esperando a assinatura (a caixa vermelha)",
        )
        cabecalho = ui.tags.tr(
            ui.tags.th("Revenda") if _escopo_multiplo() else None,
            *[
                assinar if rotulo == "Assinar" else ordenaveis.get(rotulo) or ui.tags.th(rotulo)
                for rotulo in COLUNAS_CONTAS_PAGAR
            ],
        )
        if not linhas:
            linhas = [
                ui.tags.tr(
                    ui.tags.td(
                        "Nenhum título esperando a assinatura nos filtros selecionados.",
                        colspan=str(len(COLUNAS_CONTAS_PAGAR) + (1 if _escopo_multiplo() else 0)),
                        class_="text-muted px-2 py-3",
                    )
                )
            ]
        return ui.div(
            ui.tags.table(
                ui.tags.thead(cabecalho),
                ui.tags.tbody(*linhas),
                class_="ppf-tabela-pagar-html ppf-tabela-contas",
            ),
            ui.div(ui.input_numeric("tabela_geracao", None, value=_geracao["n"]), style="display:none"),
            class_="ppf-rolagem-pagar",
            style="max-height: none" if paginador.tamanho() > LINHAS_COM_TETO else None,
        )

    @render.ui
    async def controles_tabela_pagar():
        base = await pagar_pronto()
        if so_assinar() and not base.is_empty():
            base = _so_os_de_assinar(_com_overlay(base), _documentos_do_olho())
        return paginador.controles(base.height)

    @reactive.effect
    @reactive.event(paginador.pagina, ignore_init=True)
    async def _topo_ao_paginar():
        await session.send_custom_message("rolarAte", {"id": session.ns("secao_contas_pagar")})

    @reactive.effect
    @reactive.event(
        input.periodo,
        input.intervalo,
        input.tipo,
        input.nome,
        input.documento,
        input.historico,
    )
    def _voltar_pra_primeira_pagina():
        paginador.reiniciar()

    @reactive.effect(priority=1000)
    @reactive.event(input.historico, ignore_init=True)
    def _fechar_carregando_historico():
        inicio = time.monotonic()
        dia = (input.historico() or "").strip() or "Atual"
        revenda = _revenda()

        async def _fechar():
            await _fechar_carregando()
            segundos = time.monotonic() - inicio
            texto = f"Diario: Historico {dia} ({revenda}) desenhado em {segundos:.1f} s"
            (logger.warning if segundos > 10 else logger.info)(texto)

        session.on_flushed(_fechar, once=True)


def pag_diario_ui(revenda: str | None = None):
    return diario_ui("diario", revenda)


def pag_diario_cabecalho(revenda: str | None = None):
    return diario_cabecalho("diario", revenda)


def pag_diario_server(revenda_atual=None, pedir_atualizacao=None, acompanhar_tarefa=None):
    return diario_server(
        "diario", revenda_atual=revenda_atual, pedir_atualizacao=pedir_atualizacao, acompanhar_tarefa=acompanhar_tarefa
    )
