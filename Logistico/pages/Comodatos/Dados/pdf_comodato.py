from __future__ import annotations

import datetime as dt
import re
import unicodedata
from pathlib import Path

from fpdf import FPDF

MARGEM_MM = 20.0
LARGURA_A4_MM = 210.0
LARGURA_UTIL_MM = LARGURA_A4_MM - 2 * MARGEM_MM

CINZA_LINHA = 230

_ALTURA_LINHA_CABECALHO = 5.6
_ALTURA_LINHA_TEXTO = 4.6


def _latin1(texto) -> str:
    valor = "" if texto is None else str(texto)
    try:
        valor.encode("latin-1")
        return valor
    except UnicodeEncodeError:
        sem_acento = unicodedata.normalize("NFKD", valor)
        limpo = "".join(c for c in sem_acento if not unicodedata.combining(c))
        return limpo.encode("latin-1", errors="replace").decode("latin-1")


def _data(valor) -> str:
    try:
        return dt.datetime.strptime(str(valor).strip(), "%Y%m%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return _latin1(valor)


def _dinheiro(valor) -> str:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        numero = 0.0
    texto = f"{numero:,.2f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _codigo_e_descricao(produto) -> tuple[str, str]:
    partes = str(produto or "").split(" - ", 1)
    return (partes[0], partes[1]) if len(partes) == 2 else (partes[0], "")


class _Documento(FPDF):
    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Times", "", 9)
        self.cell(0, 10, str(self.page_no()), align="C")


def _linha_moldura(pdf: FPDF, partes: list[tuple[str, str]], *, centralizado: bool = False) -> None:
    altura = _ALTURA_LINHA_CABECALHO
    y = pdf.get_y()
    pdf.set_font("Times", "", 10)
    pdf.set_x(MARGEM_MM)
    pdf.cell(LARGURA_UTIL_MM, altura, "", border="LR")

    if centralizado:
        texto_total = " ".join(f"{r} {v}".strip() for r, v in partes)
        pdf.set_xy(MARGEM_MM, y)
        pdf.set_font("Times", "B", 10)
        pdf.cell(LARGURA_UTIL_MM, altura, _latin1(texto_total), align="C")
        pdf.set_y(y + altura)
        return

    esquerda = MARGEM_MM + 1.5
    direita = MARGEM_MM + LARGURA_UTIL_MM - 1.5

    def largura_par(rotulo: str, valor: str) -> float:
        pdf.set_font("Times", "B", 10)
        largura = pdf.get_string_width(_latin1(rotulo)) + 1
        pdf.set_font("Times", "", 10)
        return largura + pdf.get_string_width(_latin1(valor))

    posicoes: list[float] = []
    for indice, (rotulo, valor) in enumerate(partes):
        if indice == 0:
            posicoes.append(esquerda)
        elif indice == len(partes) - 1:
            posicoes.append(max(esquerda, direita - largura_par(rotulo, valor)))
        else:
            largura = largura_par(rotulo, valor)
            posicoes.append(esquerda + (LARGURA_UTIL_MM - largura) / 2)

    for indice, (rotulo, valor) in enumerate(partes):
        x = posicoes[indice]
        limite = (posicoes[indice + 1] - 2) if indice + 1 < len(posicoes) else direita
        pdf.set_xy(x, y)
        pdf.set_font("Times", "B", 10)
        largura_rotulo = pdf.get_string_width(_latin1(rotulo)) + 1
        pdf.cell(largura_rotulo, altura, _latin1(rotulo))
        pdf.set_font("Times", "", 10)
        disponivel = max(0.0, limite - (x + largura_rotulo))
        pdf.cell(disponivel, altura, _cortar(pdf, _latin1(valor), disponivel))
    pdf.set_y(y + altura)


def _cortar(pdf: FPDF, texto: str, largura: float) -> str:
    if largura <= 0 or pdf.get_string_width(texto) <= largura + 0.6:
        return texto
    reticencias = pdf.get_string_width("...")
    cortado = texto
    while cortado and pdf.get_string_width(cortado) + reticencias > largura:
        cortado = cortado[:-1]
    return (cortado + "...") if cortado else ""


def _traco_horizontal(pdf: FPDF) -> None:
    y = pdf.get_y()
    pdf.line(MARGEM_MM, y, MARGEM_MM + LARGURA_UTIL_MM, y)


def _regua_central(pdf: FPDF, largura: float = 80.0) -> None:
    pdf.ln(3)
    y = pdf.get_y()
    x = MARGEM_MM + (LARGURA_UTIL_MM - largura) / 2
    pdf.line(x, y, x + largura, y)
    pdf.ln(4)


def _paragrafo(pdf: FPDF, texto: str, *, tamanho: float = 10, negrito_em: list[str] | None = None) -> None:
    pdf.set_font("Times", "", tamanho)
    if not negrito_em:
        pdf.set_x(MARGEM_MM)
        pdf.multi_cell(LARGURA_UTIL_MM, _ALTURA_LINHA_TEXTO, _latin1(texto), align="J")
        return
    pdf.set_x(MARGEM_MM)
    restante = texto
    for pedaco in negrito_em:
        antes, _, restante = restante.partition(pedaco)
        pdf.set_font("Times", "", tamanho)
        pdf.write(_ALTURA_LINHA_TEXTO, _latin1(antes))
        pdf.set_font("Times", "B", tamanho)
        sobra = pdf.w - pdf.r_margin - pdf.get_x()
        if pdf.get_string_width(_latin1(pedaco)) > sobra:
            pdf.ln(_ALTURA_LINHA_TEXTO)
            pdf.set_x(MARGEM_MM)
        pdf.write(_ALTURA_LINHA_TEXTO, _latin1(pedaco))
    pdf.set_font("Times", "", tamanho)
    pdf.write(_ALTURA_LINHA_TEXTO, _latin1(restante))
    pdf.ln(_ALTURA_LINHA_TEXTO)


def _tabela_produtos(pdf: FPDF, produtos: list[dict]) -> float:
    larguras = [22.0, 78.0, 16.0, 27.0, 27.0]
    cabecalhos = ["Código", "Descrição", "Qtd.", "Valor Unit.", "Valor Total"]
    alinhamentos = ["C", "L", "C", "R", "R"]
    largura_tabela = sum(larguras)
    inicio_x = MARGEM_MM + (LARGURA_UTIL_MM - largura_tabela) / 2

    y = pdf.get_y()
    pdf.set_line_width(0.4)
    pdf.line(inicio_x, y, inicio_x + largura_tabela, y)
    pdf.set_line_width(0.2)
    pdf.ln(1)

    pdf.set_x(inicio_x)
    pdf.set_font("Times", "B", 10)
    for largura, titulo, alinhamento in zip(larguras, cabecalhos, alinhamentos):
        pdf.cell(largura, 6, _latin1(titulo), align=alinhamento)
    pdf.ln(6)
    pdf.line(inicio_x, pdf.get_y(), inicio_x + largura_tabela, pdf.get_y())
    pdf.ln(0.5)

    total = 0.0
    pdf.set_font("Times", "", 10)
    for indice, produto in enumerate(produtos):
        codigo, descricao = _codigo_e_descricao(produto.get("PRODUTO"))
        try:
            quantidade = float(produto.get("QTD") or 0)
        except (TypeError, ValueError):
            quantidade = 0.0
        try:
            preco = float(produto.get("PRECO") or 0)
        except (TypeError, ValueError):
            preco = 0.0
        valor_linha = preco * quantidade
        total += valor_linha

        pinta = (indice % 2) == 0
        if pinta:
            pdf.set_fill_color(CINZA_LINHA, CINZA_LINHA, CINZA_LINHA)
        pdf.set_x(inicio_x)
        quantidade_texto = str(int(quantidade)) if quantidade == int(quantidade) else str(quantidade)
        celulas = [codigo, descricao, quantidade_texto, _dinheiro(preco), _dinheiro(valor_linha)]
        for largura, valor, alinhamento in zip(larguras, celulas, alinhamentos):
            pdf.cell(largura, 6, _latin1(valor), align=alinhamento, fill=pinta)
        pdf.ln(6)

    pdf.set_line_width(0.4)
    pdf.line(inicio_x, pdf.get_y(), inicio_x + largura_tabela, pdf.get_y())
    pdf.set_line_width(0.2)
    return total


def _linhas_assinatura(pdf: FPDF, pares: list[tuple[str, str]]) -> None:
    metade = LARGURA_UTIL_MM / 2
    for esquerda, direita in pares:
        y = pdf.get_y()
        pdf.set_font("Times", "B", 10)
        pdf.set_xy(MARGEM_MM, y)
        pdf.cell(metade, 5, _latin1(esquerda))
        if direita:
            pdf.set_xy(MARGEM_MM + metade, y)
            pdf.cell(metade, 5, _latin1(direita))
        pdf.ln(6)
        y = pdf.get_y()
        if esquerda:
            pdf.line(MARGEM_MM, y, MARGEM_MM + metade - 8, y)
        if direita:
            pdf.line(MARGEM_MM + metade, y, MARGEM_MM + LARGURA_UTIL_MM - 8, y)
        pdf.ln(6)


def gerar_pdf(dados: dict, pasta_saida: Path) -> Path:
    cliente = str(dados.get("cliente") or "")
    achado_codigo = re.match(r"^[^\s-]+", cliente)
    codigo_cliente = achado_codigo.group(0) if achado_codigo else ""
    achado_nome = re.search(r"(?<=-\s).*", cliente)
    comodataria = achado_nome.group(0) if achado_nome else ""

    municipio = str(dados.get("municipio") or "")
    uf = str(dados.get("uf") or "")
    cidade_uf = f"{municipio} - {uf}".upper()

    pdf = _Documento(orientation="P", unit="mm", format="A4")
    pdf.set_margins(MARGEM_MM, MARGEM_MM, MARGEM_MM)
    pdf.set_auto_page_break(auto=True, margin=MARGEM_MM)
    pdf.set_line_width(0.2)
    pdf.add_page()
    pdf.set_font("Times", "", 10)

    topo = pdf.get_y()
    _traco_horizontal(pdf)
    _linha_moldura(
        pdf, [("TERMO DE RESPONSABILIDADE POR EMPRÉSTIMO - N°:", str(dados.get("ncev") or ""))], centralizado=True
    )
    _linha_moldura(pdf, [("TIPO DE COMODATO: 02 - CIRCULAR/EVENTO", "")], centralizado=True)
    _traco_horizontal(pdf)
    _linha_moldura(pdf, [("COMODATANTE:", str(dados.get("razao_social") or ""))])
    endereco_comodatante = (
        f"{dados.get('logradouro') or ''} {dados.get('numero') or ''} - "
        f"{dados.get('bairro') or ''} - {municipio} - {uf}"
    )
    _linha_moldura(pdf, [("END.:", endereco_comodatante), ("CEP:", str(dados.get("cep") or ""))])
    _linha_moldura(pdf, [("CNPJ:", str(dados.get("cnpj_rev_documento") or dados.get("cnpj_rev") or ""))])
    _traco_horizontal(pdf)
    _linha_moldura(pdf, [("COMODATÁRIA:", comodataria), ("CÓDIGO:", codigo_cliente)])
    _linha_moldura(pdf, [("DIA VIS.:", str(dados.get("dia_visit") or "")), ("SEQ.:", str(dados.get("seq") or ""))])
    _linha_moldura(
        pdf, [("END.:", str(dados.get("endereco") or "")), ("CEP:", str(dados.get("cep_comodataria") or ""))]
    )
    _linha_moldura(pdf, [("CNPJ/CPF:", str(dados.get("cnpj") or ""))])
    _linha_moldura(pdf, [("FONE:", str(dados.get("fone") or "")), ("CONTATO:", str(dados.get("contato") or ""))])
    _linha_moldura(
        pdf,
        [
            ("N.F.:", f"{dados.get('nf') or ''}/ {dados.get('nf_serie') or ''}"),
            ("PEDIDO:", str(dados.get("nped") or "")),
            ("ROMANEIO:", str(dados.get("rom") or "")),
        ],
    )
    _linha_moldura(pdf, [("VENDEDOR:", str(dados.get("ven") or "")), ("MOTORISTA:", str(dados.get("mot") or ""))])
    _linha_moldura(pdf, [("PONTO DE REFERÊNCIA:", str(dados.get("pto_ref") or ""))])
    _traco_horizontal(pdf)
    _linha_moldura(
        pdf,
        [
            ("EMISSÃO:", _data(dados.get("emissao"))),
            ("VENCIMENTO:", _data(dados.get("vencimento"))),
            ("RECOLHIMENTO:", "___/___/___"),
        ],
    )
    _traco_horizontal(pdf)
    pdf.line(MARGEM_MM, topo, MARGEM_MM + LARGURA_UTIL_MM, topo)

    _regua_central(pdf)

    _paragrafo(pdf, DECLARACAO)
    pdf.ln(3)
    _paragrafo(pdf, LGPD, tamanho=9.5)
    pdf.ln(2)
    email_revenda = str(dados.get("email_revenda") or "NAO INFORMADO").upper()
    _paragrafo(pdf, COMODATARIA_LGPD.format(email=email_revenda), tamanho=9.5, negrito_em=[email_revenda])
    pdf.ln(2)
    _paragrafo(pdf, FORO_MINUSCULO.format(cidade=cidade_uf), tamanho=9.5, negrito_em=[cidade_uf])
    _regua_central(pdf)

    pdf.add_page()
    pdf.ln(4)
    total = _tabela_produtos(pdf, dados.get("produtos") or [])
    pdf.ln(6)
    pdf.set_font("Times", "B", 11)
    pdf.set_x(MARGEM_MM)
    pdf.cell(LARGURA_UTIL_MM, 6, _latin1(f"VALOR TOTAL: R$ {_dinheiro(total)}"), align="R")
    pdf.ln(8)
    _regua_central(pdf)

    pdf.ln(2)
    _paragrafo(pdf, FORO_MAIUSCULO.format(cidade=cidade_uf), negrito_em=[cidade_uf])
    pdf.ln(2)
    pdf.set_font("Times", "B", 10)
    pdf.set_x(MARGEM_MM)
    rotulo_obs = "OBS: COMPROMISSO DE NEGOCIAÇÃO E COMPRA MÍNIMA:"
    pdf.cell(pdf.get_string_width(_latin1(rotulo_obs)) + 2, 6, _latin1(rotulo_obs))
    y_obs = pdf.get_y() + 5
    pdf.line(pdf.get_x(), y_obs, pdf.get_x() + 55, y_obs)
    pdf.ln(14)

    pdf.set_font("Times", "", 10)
    pdf.set_x(MARGEM_MM)
    pdf.cell(
        LARGURA_UTIL_MM, 6, _latin1(f"{municipio.upper()} , ________ DE ___________________ DE 2.0_____"), align="R"
    )
    pdf.ln(14)

    _linhas_assinatura(pdf, [("NOME POR EXTENSO:", "ASS. DA COMODATARIA:")])
    pdf.ln(1)
    _linhas_assinatura(pdf, [("", "DOCTO. DE IDENTIDADE:")])
    pdf.ln(4)
    _linhas_assinatura(pdf, [("TESTEMUNHA (1):", "TESTEMUNHA (2):")])
    pdf.ln(4)

    pdf.set_font("Times", "B", 10)
    pdf.set_x(MARGEM_MM)
    rotulo_ativo = "NÚMERO DO ATIVO:"
    pdf.cell(pdf.get_string_width(_latin1(rotulo_ativo)) + 2, 6, _latin1(rotulo_ativo))
    y_ativo = pdf.get_y() + 5
    pdf.line(pdf.get_x(), y_ativo, pdf.get_x() + 55, y_ativo)

    pasta_saida.mkdir(parents=True, exist_ok=True)
    nome = f"{dados.get('cnpj_rev')}_{codigo_cliente.rjust(8, '0')}_{dados.get('ncev')}.PDF"
    caminho = pasta_saida / nome
    pdf.output(str(caminho))
    return caminho


DECLARACAO = (
    "DECLARO PARA TODOS OS FINS E EFEITOS LEGAIS E DE DIREITO, QUE SE ENCONTRAM SOB MINHA GUARDA E "
    "RESPONSABILIDADE AS MERCADORIAS ABAIXO DISCRIMINADAS, QUE ME FOI CEDIDO PELA COMODANTE; O QUAL "
    "ME COMPROMETO A DEVOLVER, EM QUALQUER TEMPO, ASSIM QUE ME FOR SOLICITADO EM PERFEITAS CONDIÇÕES "
    "DE USO. NO CASO DE PERDA, DANO OU EXTRAVIO TOTAL OU PARCIAL, COMPROMETO-ME A REEMBOLSAR A "
    "COMODANTE, O TOTAL DAS MERCADORIAS PERDIDAS, EXTRAVIADAS OU DANIFICADAS FICANDO ESTA DESDE JÁ "
    "AUTORIZADA A EMITIR A RESPECTIVA NOTA FISCAL DE VENDA DAS MESMAS AOS PREÇOS DA SUA TABELA "
    "VIGENTE À DATA DE EMISSÃO DA NOTA FISCAL E A CORRESPONDENTE DUPLICATA À VISTA. CASO A COMODANTE "
    "TENHA QUE RECORRER A JUÍZO PARA EXECUÇÃO DO PRESENTE DECLARO QUE ARCAREI COM TODAS AS DESPESAS "
    "JUDICIAIS E ADVOCATÍCIAS DEVIDAS."
)
LGPD = (
    "A COMODANTE declara que as informações aqui coletadas serão tratadas de acordo com a Política "
    "de Privacidade e com todas as leis, regras e regulamentos aplicáveis aos dados pessoais, "
    "incluindo, mas não se limitando à Lei nº 13.709/2018 - Lei Geral de Proteção de Dados Pessoais "
    "(LGPD) e regulamentações emanadas pela Autoridade Nacional de Proteção de Dados (ANPD)."
)
COMODATARIA_LGPD = (
    "A COMODATARIA, por sua vez, declara ter lido e estar de acordo com a Política de Privacidade da "
    "COMODANTE. Caso ainda restem dúvidas com relação ao tratamento de dados pessoais aqui coletados "
    "solicitamos que envie e-mail para {email}."
)
FORO_MINUSCULO = (
    "Fica eleito o Foro da Comarca de {cidade}, para dirimir qualquer litígio decorrente do presente "
    "Termo Aditivo que não possa ser resolvido por meio amigável, com expressa renúncia a qualquer "
    "outro, por mais privilegiado que seja."
)
FORO_MAIUSCULO = (
    "FICA ELEITO O FORO DE {cidade}, PARA DIRIMIR AS DÚVIDAS OU QUESTÕES ADVINDAS DO PRESENTE TERMO "
    "DE RESPONSABILIDADE COM RENÚNCIA DE QUALQUER OUTRO."
)
