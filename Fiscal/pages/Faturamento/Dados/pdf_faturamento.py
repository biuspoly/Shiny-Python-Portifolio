from __future__ import annotations

from fpdf import FPDF

MARGEM = 12
LARGURA = 186
CINZA = (217, 217, 217)
COLUNA_PERIODO, COLUNA_MEIO = 52, 88


def _latin1(texto) -> str:
    return str(texto or "").encode("latin-1", "replace").decode("latin-1")


def _rotulo_e_valor(
    pdf: FPDF,
    x: float,
    rotulo: str,
    valor: str,
    largura_rotulo: float,
    largura_valor: float,
    negrito_valor: bool = False,
) -> None:
    pdf.set_xy(x, pdf.get_y())
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(largura_rotulo, 6, _latin1(rotulo))
    pdf.set_font("Helvetica", "B" if negrito_valor else "", 8)
    pdf.cell(largura_valor, 6, _latin1(valor))


def _quadro_empresa(pdf: FPDF, e: dict) -> None:
    x, topo = MARGEM, pdf.get_y()
    linhas = [
        [("Empresa:", e["razao"], 40, 146, True)],
        [("Endereço:", e["endereco"], 40, 78, False), ("Número:", e["numero"], 14, 54, False)],
        [
            ("CEP:", e["cep"], 40, 22, False),
            ("Bairro:", e["bairro"], 12, 44, False),
            ("Município:", e["municipio"], 17, 37, False),
            ("UF:", e["uf"], 6, 8, False),
        ],
        [
            ("CNPJ:", e["cnpj"], 40, 28, False),
            ("Inscrição Estadual:", e["ie"], 30, 34, False),
            ("Inscrição Municipal:", e["im"], 32, 22, False),
        ],
        [("Atividade Econômica:", e["atividade"], 40, 146, False)],
        [("Natureza Jurídica:", e["natureza_juridica"], 40, 146, False)],
    ]
    for linha in linhas:
        y, posicao = pdf.get_y(), x + 1
        for rotulo, valor, largura_rotulo, largura_valor, negrito in linha:
            pdf.set_y(y)
            _rotulo_e_valor(pdf, posicao, rotulo, valor, largura_rotulo, largura_valor, negrito)
            posicao += largura_rotulo + largura_valor
        pdf.set_y(y + 6)
    pdf.rect(x, topo, LARGURA, pdf.get_y() - topo + 2)
    pdf.set_y(pdf.get_y() + 2)


def _barra(pdf: FPDF, texto: str, alinhamento: str = "L") -> None:
    pdf.set_fill_color(*CINZA)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_x(MARGEM)
    pdf.cell(LARGURA, 5, _latin1(texto), border=1, align=alinhamento, fill=True, new_x="LMARGIN", new_y="NEXT")


def _relacao(pdf: FPDF, meses: list[tuple[str, str]], total: str) -> None:
    valor = LARGURA - COLUNA_PERIODO - COLUNA_MEIO
    pdf.set_x(MARGEM)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(LARGURA, 7, _latin1("Relação de Faturamento"), border="LR", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_fill_color(*CINZA)
    pdf.cell(COLUNA_PERIODO, 5, _latin1("Período"), border=1, align="C", fill=True)
    pdf.cell(COLUNA_MEIO, 5, "", border=1, fill=True)
    pdf.cell(valor, 5, "Faturamento (R$)", border=1, align="R", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(COLUNA_PERIODO, 2, "", border="LR")
    pdf.cell(COLUNA_MEIO, 2, "", border="LR")
    pdf.cell(valor, 2, "", border="LR", new_x="LMARGIN", new_y="NEXT")
    for periodo, faturado in meses:
        pdf.cell(COLUNA_PERIODO, 4.5, _latin1(periodo), border="LR", align="C")
        pdf.cell(COLUNA_MEIO, 4.5, "", border="LR")
        pdf.cell(valor, 4.5, _latin1(faturado), border="LR", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(COLUNA_PERIODO, 5, "Total", border=1, align="C")
    pdf.cell(COLUNA_MEIO, 5, "", border=1)
    pdf.cell(valor, 5, _latin1(total), border=1, align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(LARGURA, 6, "", border="LR", new_x="LMARGIN", new_y="NEXT")


def _assinaturas(pdf: FPDF, local_e_data: str, responsavel: dict, tecnico: dict) -> None:
    metade = LARGURA / 2
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(LARGURA, 0.6, "", border="LRT", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(LARGURA, 4.5, _latin1(local_e_data), border="LRT", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(metade, 5, _latin1("Responsável pela empresa"), border=1, align="C")
    pdf.cell(metade, 5, _latin1("Responsável Técnico"), border=1, align="C", new_x="LMARGIN", new_y="NEXT")
    topo = pdf.get_y()
    altura = 38
    pdf.rect(MARGEM, topo, metade, altura)
    pdf.rect(MARGEM + metade, topo, metade, altura)
    linha = topo + 19
    pdf.line(MARGEM + 1, linha, MARGEM + 70, linha)
    pdf.line(MARGEM + metade + 1, linha, MARGEM + metade + 70, linha)
    pdf.set_font("Helvetica", "", 8)
    for i, (esquerda, direita) in enumerate(
        (
            (f"Nome: {responsavel.get('nome', '')}", ("Nome", tecnico.get("nome", ""))),
            (f"CPF: {responsavel.get('cpf', '')}", ("CPF", tecnico.get("cpf", ""))),
            (f"RG: {responsavel.get('rg', '')}", ("CRC", tecnico.get("crc", ""))),
        )
    ):
        y = linha + 1.5 + i * 4.2
        pdf.set_xy(MARGEM + 1, y)
        pdf.cell(metade - 2, 4.2, _latin1(esquerda))
        pdf.set_xy(MARGEM + metade + 1, y)
        pdf.cell(16, 4.2, _latin1(direita[0]))
        pdf.cell(metade - 18, 4.2, _latin1(direita[1]))
    pdf.set_y(topo + altura)


def gerar(dados: dict) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(MARGEM, 12, MARGEM)
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.set_title("Demonstrativo de Faturamento")
    pdf.set_y(25)
    _barra(pdf, "DEMONSTRATIVO DE FATURAMENTO", "C")
    _quadro_empresa(pdf, dados["empresa"])
    _barra(pdf, "Descrição")
    _relacao(pdf, dados["meses"], dados["total"])
    _assinaturas(pdf, dados["local_e_data"], dados.get("responsavel") or {}, dados.get("tecnico") or {})
    return bytes(pdf.output())


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.stdout.reconfigure(encoding="utf-8")
    exemplo = {
        "empresa": {
            "razao": "EMPRESA DE EXEMPLO LTDA",
            "endereco": "RUA DE EXEMPLO",
            "numero": "100",
            "cep": "50.000-000",
            "bairro": "CENTRO",
            "municipio": "RECIFE",
            "uf": "PE",
            "cnpj": "00.000.000/0001-00",
            "ie": "000000000",
            "im": "",
            "atividade": "46.35-4-03 Comércio atacadista de bebidas",
            "natureza_juridica": "206-2",
        },
        "meses": [
            (f"mês {i}", f"{1000 * i:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")) for i in range(1, 13)
        ],
        "total": "78.000,00",
        "local_e_data": "Recife, 30 de outubro de 2026",
        "responsavel": {"nome": "Fulano de Tal", "cpf": "000.000.000-00", "rg": "0000000 SSP/PE"},
        "tecnico": {"nome": "Beltrana de Tal", "cpf": "000.000.000-00", "crc": "PE000000"},
    }
    destino = Path.cwd() / "demonstrativo_exemplo.pdf"
    destino.write_bytes(gerar(exemplo))
    print(f"gravado {destino} ({destino.stat().st_size} bytes)")
