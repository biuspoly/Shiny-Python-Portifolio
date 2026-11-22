from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

from .pdf_comodato import (
    CINZA_LINHA,
    LARGURA_UTIL_MM,
    MARGEM_MM,
    _Documento,
    _latin1,
    _linhas_assinatura,
    _paragrafo,
    _regua_central,
)


def _titulo_emoldurado(pdf: FPDF, texto: str) -> None:
    pdf.set_font("Times", "B", 12)
    largura = pdf.get_string_width(_latin1(texto)) + 6
    pdf.set_x(MARGEM_MM)
    pdf.cell(largura, 8, _latin1(texto), border=1, align="C")
    pdf.ln(10)


def _tabela_itens(pdf: FPDF, itens: list[dict]) -> None:
    larguras = [28.0, 100.0, 20.0]
    alinhamentos = ["L", "L", "R"]
    largura_tabela = sum(larguras)
    inicio_x = MARGEM_MM + (LARGURA_UTIL_MM - largura_tabela) / 2

    pdf.set_line_width(0.4)
    pdf.line(inicio_x, pdf.get_y(), inicio_x + largura_tabela, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(1)

    pdf.set_x(inicio_x)
    pdf.set_font("Times", "B", 10)
    for largura, titulo, alinhamento in zip(larguras, ("Código", "Descrição", "Qtd."), alinhamentos):
        pdf.cell(largura, 6, _latin1(titulo), align=alinhamento)
    pdf.ln(6)
    pdf.line(inicio_x, pdf.get_y(), inicio_x + largura_tabela, pdf.get_y())
    pdf.ln(0.5)

    pdf.set_font("Times", "", 10)
    for indice, item in enumerate(itens):
        pinta = (indice % 2) == 0
        if pinta:
            pdf.set_fill_color(CINZA_LINHA, CINZA_LINHA, CINZA_LINHA)
        pdf.set_x(inicio_x)
        celulas = (
            str(item.get("codigo") or ""),
            str(item.get("descricao") or ""),
            _quantidade(item.get("qtd")),
        )
        for largura, valor, alinhamento in zip(larguras, celulas, alinhamentos):
            pdf.cell(largura, 6, _latin1(valor), align=alinhamento, fill=pinta)
        pdf.ln(6)

    pdf.set_line_width(0.4)
    pdf.line(inicio_x, pdf.get_y(), inicio_x + largura_tabela, pdf.get_y())
    pdf.set_line_width(0.2)


def _quantidade(valor) -> str:
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        return str(valor or "")
    texto = f"{numero:,.0f}" if numero == int(numero) else f"{numero:,.2f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def gerar_pdf(dados: dict, pasta_saida: Path) -> Path:
    def campo(chave: str) -> str:
        valor = str(dados.get(chave) or "").strip()
        return valor or "NÃO INFORMADO"

    pdf = _Documento(orientation="P", unit="mm", format="A4")
    pdf.set_margins(MARGEM_MM, MARGEM_MM, MARGEM_MM)
    pdf.set_auto_page_break(auto=True, margin=MARGEM_MM)
    pdf.set_line_width(0.2)
    pdf.add_page()

    _titulo_emoldurado(pdf, "DISTRATO DE CONTRATO DE COMODATO")
    _regua_central(pdf)

    comodatante, comodataria = campo("comodatante"), campo("comodataria")
    _paragrafo(
        pdf,
        f"Por este instrumento particular, {comodatante}, sociedade limitada, inscrita no CNPJ"
        f" sob o nº {campo('cnpj_comodatante')}, com sede na {campo('end_comodatante')}, CEP"
        f" {campo('cep_comodatante')}, neste ato representada por integrante de seu departamento"
        f" administrativo, e, {comodataria}, inscrita no CNPJ/CPF sob o nº"
        f" {campo('cnpj_comodataria')}, com sede na {campo('end_comodataria')}, CEP"
        f" {campo('cep_comodataria')}, doravante denominada simplesmente COMODATÁRIA, têm entre"
        " si, justo e contratado, o que segue:",
        negrito_em=[comodatante, comodataria, "COMODATÁRIA"],
    )

    pdf.ln(4)
    _clausula(pdf, "CLÁUSULA PRIMEIRA")
    _paragrafo(
        pdf,
        "As partes firmaram entre si, em ____ de __________ de 2.0____, o Termo de"
        f" Responsabilidade por Empréstimo - Contrato de Comodato nº {campo('ncev')}, ocasião em"
        " que pactuaram o empréstimo dos seguintes bens:",
        negrito_em=[f"Termo de Responsabilidade por Empréstimo - Contrato de Comodato nº {campo('ncev')}"],
    )
    pdf.ln(3)
    _tabela_itens(pdf, dados.get("itens") or [])
    pdf.ln(6)

    _clausula(pdf, "CLÁUSULA SEGUNDA")
    _paragrafo(
        pdf,
        "Não havendo mais interesse por parte das Contratantes em manter referido contrato de"
        " comodato, resolveram, de comum acordo, rescindi-lo nesta data.",
    )
    pdf.ln(4)

    _clausula(pdf, "CLÁUSULA TERCEIRA")
    _paragrafo(
        pdf,
        "A COMODATÁRIA restitui a(o) COMODATANTE todos os bens dados em comodato nas condições"
        " primitivas em que os recebeu.",
    )
    pdf.ln(2)
    _paragrafo(
        pdf,
        "Por meio do presente Distrato, as partes rescindem o contrato de comodato firmado, não"
        " podendo nada mais reclamar em juízo ou fora dele, dando assim, plena, geral e"
        " irrevogável quitação acerca do contrato de comodato em comento. E, assim, por estarem"
        " justos e contratados, assinam o presente instrumento em 02 (duas) vias de igual teor e"
        " forma, na presença de 02 (duas) testemunhas igualmente abaixo assinadas.",
    )

    pdf.ln(9)
    pdf.set_font("Times", "", 10)
    pdf.set_x(MARGEM_MM)
    pdf.cell(
        LARGURA_UTIL_MM, 6, _latin1(f"{campo('cidade').upper()} , ______ DE ___________________ DE 2.0_____"), align="R"
    )
    pdf.ln(10)

    _linhas_assinatura(pdf, [("COMODATANTE:", "ASS. DA COMODATÁRIA:")])
    pdf.ln(4)
    _linhas_assinatura(pdf, [("TESTEMUNHA (1):", "TESTEMUNHA (2):")])
    pdf.ln(2)

    pdf.set_font("Times", "B", 10)
    pdf.set_x(MARGEM_MM)
    rotulo = "NÚMERO DO ATIVO:"
    pdf.cell(pdf.get_string_width(_latin1(rotulo)) + 2, 6, _latin1(rotulo))
    y = pdf.get_y() + 5
    pdf.line(pdf.get_x(), y, pdf.get_x() + 55, y)

    pasta_saida.mkdir(parents=True, exist_ok=True)
    caminho = pasta_saida / nome_arquivo(dados)
    pdf.output(str(caminho))
    return caminho


def _clausula(pdf: FPDF, titulo: str) -> None:
    pdf.set_font("Times", "B", 10)
    pdf.set_x(MARGEM_MM)
    pdf.cell(LARGURA_UTIL_MM, 6, _latin1(titulo))
    pdf.ln(7)


def nome_arquivo(dados: dict) -> str:
    cliente = str(dados.get("comodataria") or dados.get("codcli") or "cliente")
    limpo = "".join(c if (c.isalnum() or c in " -_") else "_" for c in cliente).strip()
    return f"DISTRATO_{limpo or 'cliente'}_{dados.get('ncev') or ''}.pdf"
