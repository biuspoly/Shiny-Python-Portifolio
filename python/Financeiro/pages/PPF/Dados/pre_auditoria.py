from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from operator import itemgetter
from typing import NamedTuple

import polars as pl
from lxml import etree

from core import fabricas, xml_fiscal
from core.config import chave_revenda
from core.config_arquivo import carregar_json

from .capitulos_ncm import nome_do_capitulo

REGRAS = {
    "nota_nao_encontrada": ("Nota", "atenção", "Nota não encontrada nas notas que o governo mandou para a empresa"),
    "nota_de_outra_empresa": ("Nota", "erro", "Nota emitida para outra empresa"),
    "nota_cancelada": ("Nota", "erro", "Nota cancelada no governo"),
    "valor_maior_que_a_nota": ("Nota", "erro", "Título com valor maior que o da nota"),
    "numero_da_nfse_cortado": ("Nota", "atenção", "Número da nota de serviço cortado pelo fim no ERP"),
    "valor_diferente_da_parcela": ("Nota", "atenção", "Valor do título diferente das parcelas da nota"),
    "vencimento_diferente_da_parcela": ("Nota", "atenção", "Vencimento do título diferente da parcela da nota"),
    "pdf_de_outra_nota": ("Arquivo", "erro", "O PDF da pasta é de outra nota"),
    "pdf_de_outro_fornecedor": ("Arquivo", "erro", "O PDF da pasta é nota de outro fornecedor"),
    "arquivo_e_rps": ("Arquivo", "atenção", "O arquivo da pasta é um RPS, não a nota"),
    "arquivo_sem_nota": ("Arquivo", "atenção", "Nenhum arquivo da pasta parece ser a nota"),
    "pdf_com_chave_invalida": ("Arquivo", "atenção", "A chave de acesso do PDF da pasta tem o dígito errado"),
    "chave_fora_da_sefaz": ("Arquivo", "erro", "A SEFAZ não conhece a chave do PDF da pasta"),
    "pdf_de_outro_mes": ("Arquivo", "atenção", "A nota do PDF da pasta é de outro mês"),
    "pdf_sem_o_cnpj_da_empresa": ("Arquivo", "atenção", "O PDF da pasta não cita o CNPJ da empresa"),
    "fornecedor_inapto": ("Fornecedor", "erro", "Inscrição estadual do fornecedor não habilitada na SEFAZ"),
    "fornecedor_irregular_na_receita": ("Fornecedor", "erro", "CNPJ do fornecedor não está ativo na Receita Federal"),
    "fornecedor_sem_historico": ("Fornecedor", "atenção", "Fornecedor sem nenhum pagamento anterior"),
    "ja_pago": ("Repetição", "erro", "Documento já pago, com o mesmo valor e vencimento"),
    "titulo_repetido": ("Repetição", "erro", "O mesmo documento está em outro título em aberto"),
    "nota_com_o_mesmo_conteudo": (
        "Repetição",
        "atenção",
        "Outra nota do fornecedor, de número diferente, com os mesmos itens e o mesmo valor",
    ),
    "contrato_ja_pago": ("Repetição", "erro", "Parcela de contrato que parece já paga por outro título"),
    "contrato_informado_antes": (
        "Repetição",
        "atenção",
        "Arquivo do contrato já informado na pasta de um dia antes do vencimento",
    ),
    "despesa_fora_do_costume": ("Classificação", "atenção", "Despesa diferente da que este fornecedor costuma ter"),
    "centro_de_custo_fora_do_costume": (
        "Classificação",
        "atenção",
        "Centro de custo diferente do que este fornecedor costuma ter",
    ),
    "valor_acima_do_normal": ("Valor", "atenção", "Valor acima do normal para esta despesa"),
    "gasto_do_mes_acima_do_normal": ("Valor", "atenção", "Gasto do mês com esta despesa acima do normal"),
    "preco_subiu": ("Valor", "atenção", "Preço de item subiu desde a última compra"),
    "descricao_generica": ("Descrição", "atenção", "Descrição do serviço genérica ou curta demais"),
    "sem_assinatura": ("Aprovação", "atenção", "Sem a assinatura de aprovação no app"),
    "item_fora_da_natureza": ("Classificação", "atenção", "Item destoa da natureza da nota"),
    "despesa_fora_da_natureza": ("Classificação", "atenção", "Despesa diferente da que notas deste tipo costumam ter"),
    "rps_sem_nfse": ("Arquivo", "atenção", "RPS sem a nota de serviço correspondente no governo"),
    "ja_pago_em_outro_vencimento": ("Repetição", "atenção", "Documento já pago, com o mesmo valor e outro vencimento"),
}
REGRAS_A_LIGAR = ("item_fora_da_natureza", "despesa_fora_da_natureza", "rps_pela_nfse", "ja_pago_em_outro_vencimento")
GRUPOS = ["Nota", "Arquivo", "Fornecedor", "Repetição", "Classificação", "Valor", "Descrição", "Aprovação"]

ESQUEMA = {
    "CNPJ_REV": pl.Utf8,
    "revenda": pl.Utf8,
    "id_unico": pl.Utf8,
    "vencimento": pl.Date,
    "documento": pl.Utf8,
    "fornecedor": pl.Utf8,
    "fornecedor_cnpj": pl.Utf8,
    "valor": pl.Float64,
    "codigo_despesa": pl.Int64,
    "regra": pl.Utf8,
    "grupo": pl.Utf8,
    "gravidade": pl.Utf8,
    "descricao": pl.Utf8,
    "detalhe": pl.Utf8,
    "gerado_em": pl.Datetime,
}
ESQUEMA_DOS_CONFERIDOS = {"CNPJ_REV": pl.Utf8, "id_unico": pl.Utf8, "gerado_em": pl.Datetime}

CHAVE_NO_TEXTO = re.compile(r"(?<!\d)((?:\d(?:[ .]|[ \t]*\r?\n[^\d\r\n]{0,3})?){43}\d)(?!\d)")
MODELOS_DE_NOTA_A_PAGAR = {"55", "57", "67"}
CODIGOS_DE_UF = {
    "11",
    "12",
    "13",
    "14",
    "15",
    "16",
    "17",
    "21",
    "22",
    "23",
    "24",
    "25",
    "26",
    "27",
    "28",
    "29",
    "31",
    "32",
    "33",
    "35",
    "41",
    "42",
    "43",
    "50",
    "51",
    "52",
    "53",
}
SINAIS_DE_NOTA = re.compile(
    r"danfe|dacte|documento auxiliar d[ao] (nota|conhecimento)|nota fiscal de servic"
    r"|nota fiscal eletronica|nota fiscal fatura|\bnfs-?e\b|conhecimento de transporte"
    r"|chave de acesso"
)
SINAIS_DE_RPS = re.compile(r"recibo provisorio de servic")
CNPJ_NO_TEXTO = re.compile(r"(?<![\d./-])(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?![\d./-])")
VALOR_NO_TEXTO = re.compile(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})*,\d{2})(?![\d,])")
ESPECIES_COM_CHAVE_DE_44 = {"NFE", "NF", "NFF", "CTE", "CT", "CTR"}
MODELO_CONSULTADO_NA_SEFAZ = "55"
TAGS_DA_DESCRICAO_DO_SERVICO = ("xDescServ", "Discriminacao", "discriminacao")
MINIMO_DE_TEXTO_LIDO = 180
MAXIMO_DE_PARCELAS_IGUAIS = 24
PALAVRAS_QUE_NAO_DIZEM_O_FORNECEDOR = {
    "LTDA",
    "EIRELI",
    "COMERCIO",
    "COMERCIAL",
    "SERVICO",
    "SERVICOS",
    "INDUSTRIA",
    "BEBIDAS",
    "ALIMENTOS",
    "DISTRIBUIDORA",
    "EMPRESA",
    "BANCO",
    "FATURA",
    "BOLETO",
    "CONTRATO",
    "NOTA",
    "FISCAL",
    "PARCELA",
    "GERADO",
}


class DadosDaRevenda(NamedTuple):
    titulos: pl.DataFrame
    abertos: pl.DataFrame
    pagos: pl.DataFrame
    notas: list[dict]
    notas_de_outras_empresas: list[dict]
    notas_desvinculadas: set[tuple[str, str]]
    ligacoes: dict[str, dict]
    parcelas_por_chave: dict[str, list[dict]]
    leituras_por_id: dict[str, dict]
    apontamentos_do_fiscal: pl.DataFrame
    descricoes_por_id: dict[str, str]
    assinados: set[str]
    nomes_das_despesas: dict[int, str]
    nomes_dos_centros: dict[int, str]
    empresas_da_revenda: list[str] = []
    situacao_na_sefaz_por_chave: dict[str, dict] = {}
    irregulares_na_receita: dict[str, dict] = {}
    notas_dos_pagos: dict[str, dict] = {}
    itens_por_chave: dict[str, list[dict]] = {}
    conteudo_por_chave: dict[str, str] = {}
    arquivos_de_contrato_por_id: dict[str, list[dict]] = {}
    cnpjs_pagos_no_control: set[str] | None = None


def regra_ligada(configuracao: dict, nome_da_regra: str) -> bool:
    return (configuracao.get("regras_a_ligar") or {}).get(nome_da_regra) is True


def configuracao_lida() -> dict:
    return carregar_json("pre_auditoria", {}) or {}


def configuracao_da_revenda(revenda: str, configuracao_do_arquivo: dict | None = None) -> dict:
    configuracao_do_arquivo = configuracao_do_arquivo if configuracao_do_arquivo is not None else configuracao_lida()
    configuracao_juntada = dict(configuracao_do_arquivo.get("padrao") or {})
    for nome_da_revenda, excecao_da_revenda in (configuracao_do_arquivo.get("por_revenda") or {}).items():
        if str(nome_da_revenda).startswith("_") or chave_revenda(nome_da_revenda) != chave_revenda(revenda):
            continue
        for nome_da_opcao, valor_da_revenda in excecao_da_revenda.items():
            if isinstance(valor_da_revenda, dict) and isinstance(configuracao_juntada.get(nome_da_opcao), dict):
                configuracao_juntada[nome_da_opcao] = {**configuracao_juntada[nome_da_opcao], **valor_da_revenda}
            else:
                configuracao_juntada[nome_da_opcao] = valor_da_revenda
    return configuracao_juntada


def empresas_no_fiscal(revenda: str, configuracao_da_revenda_lida: dict) -> list[str]:
    proprias = configuracao_da_revenda_lida.get("empresas_no_fiscal") or []
    if proprias:
        return [so_digitos_do_cnpj(cnpj) for cnpj in proprias]
    return xml_fiscal.empresas_da_revenda(revenda)


def reais(valor) -> str:
    quantia = float(valor or 0)
    quantia_com_milhar = f"{abs(quantia):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"{'-' if quantia < 0 else ''}R$ {quantia_com_milhar}"


def data_br(dia) -> str:
    return dia.strftime("%d/%m/%Y") if dia else "-"


def so_digitos_do_cnpj(valor) -> str:
    digitos_do_cnpj = re.sub(r"\D", "", str(valor or ""))
    return digitos_do_cnpj.zfill(14) if digitos_do_cnpj else ""


def cnpj_formatado(valor) -> str:
    cnpj = so_digitos_do_cnpj(valor)
    if len(cnpj) != 14:
        return cnpj
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def texto_normalizado(texto) -> str:
    sem_acento = "".join(
        letra for letra in unicodedata.normalize("NFKD", str(texto or "")) if not unicodedata.combining(letra)
    )
    return re.sub(r"\s+", " ", sem_acento.casefold()).strip()


def chave_valida(chave: str) -> bool:
    if len(chave) != 44 or not chave.isdigit():
        return False
    soma_ponderada = sum(int(digito) * peso for digito, peso in zip(reversed(chave[:43]), [2, 3, 4, 5, 6, 7, 8, 9] * 6))
    digito_calculado = 11 - soma_ponderada % 11
    digito_esperado = 0 if digito_calculado >= 10 else digito_calculado
    return digito_esperado == int(chave[43]) and chave[20:22] in MODELOS_DE_NOTA_A_PAGAR


def tem_desenho_de_chave(chave: str) -> bool:
    return (
        len(chave) == 44
        and chave.isdigit()
        and chave[:2] in CODIGOS_DE_UF
        and "01" <= chave[4:6] <= "12"
        and chave[20:22] in MODELOS_DE_NOTA_A_PAGAR
    )


def chaves_do_texto(texto: str) -> list[str]:
    chaves_encontradas = []
    for trecho_achado in CHAVE_NO_TEXTO.finditer(texto or ""):
        chave = re.sub(r"\D", "", trecho_achado.group(1))
        if (
            chave_valida(chave)
            and tem_desenho_de_chave(chave)
            and cnpj_valido(chave[6:20])
            and chave not in chaves_encontradas
        ):
            chaves_encontradas.append(chave)
    return chaves_encontradas


def chaves_com_o_digito_errado(texto: str) -> list[str]:
    chaves_erradas = []
    for trecho_achado in CHAVE_NO_TEXTO.finditer(texto or ""):
        chave = re.sub(r"\D", "", trecho_achado.group(1))
        if (
            tem_desenho_de_chave(chave)
            and cnpj_valido(chave[6:20])
            and not chave_valida(chave)
            and chave not in chaves_erradas
        ):
            chaves_erradas.append(chave)
    return chaves_erradas


def cnpj_valido(cnpj: str) -> bool:
    if len(cnpj) != 14 or not cnpj.isdigit() or len(set(cnpj)) == 1:
        return False
    for tamanho in (12, 13):
        pesos = list(range(tamanho - 7, 1, -1)) + list(range(9, 1, -1))
        soma_ponderada = sum(int(digito) * peso for digito, peso in zip(cnpj[:tamanho], pesos))
        resto = soma_ponderada % 11
        if int(cnpj[tamanho]) != (0 if resto < 2 else 11 - resto):
            return False
    return True


def cnpjs_do_texto(texto: str) -> list[str]:
    cnpjs_encontrados = []
    for trecho_achado in CNPJ_NO_TEXTO.finditer(texto or ""):
        cnpj = re.sub(r"\D", "", trecho_achado.group(1))
        if cnpj_valido(cnpj) and cnpj not in cnpjs_encontrados:
            cnpjs_encontrados.append(cnpj)
    return cnpjs_encontrados


def valores_do_texto(texto: str) -> list[float]:
    valores_encontrados = []
    for trecho_achado in VALOR_NO_TEXTO.finditer(texto or ""):
        valor = round(float(trecho_achado.group(1).replace(".", "").replace(",", ".")), 2)
        if valor not in valores_encontrados:
            valores_encontrados.append(valor)
    return valores_encontrados


def leitura_do_texto(texto: str) -> dict:
    texto_sem_acento = texto_normalizado(texto)
    return {
        "tem_texto": len(texto_sem_acento) >= MINIMO_DE_TEXTO_LIDO,
        "chaves": chaves_do_texto(texto),
        "chaves_erradas": chaves_com_o_digito_errado(texto),
        "cnpjs": cnpjs_do_texto(texto),
        "parece_nota": bool(SINAIS_DE_NOTA.search(texto_sem_acento)),
        "parece_rps": bool(SINAIS_DE_RPS.search(texto_sem_acento)),
        "lido_por_ocr": False,
    }


def leitura_do_ocr(texto_do_ocr: str) -> dict:
    return {
        "tem_texto": False,
        "chaves": chaves_do_texto(texto_do_ocr),
        "chaves_erradas": [],
        "cnpjs": [],
        "parece_nota": False,
        "parece_rps": False,
        "lido_por_ocr": True,
    }


def juntar_sem_repetir(leituras_dos_pdfs: list[dict], campo: str) -> list[str]:
    juntos = []
    for leitura_do_pdf in leituras_dos_pdfs:
        for valor_lido in leitura_do_pdf.get(campo) or []:
            if valor_lido not in juntos:
                juntos.append(valor_lido)
    return juntos


def juntar_leituras(leituras_dos_pdfs: list[dict]) -> dict:
    return {
        "tem_texto": any(leitura_do_pdf["tem_texto"] for leitura_do_pdf in leituras_dos_pdfs),
        "chaves": juntar_sem_repetir(leituras_dos_pdfs, "chaves"),
        "chaves_erradas": juntar_sem_repetir(leituras_dos_pdfs, "chaves_erradas"),
        "cnpjs": juntar_sem_repetir(leituras_dos_pdfs, "cnpjs"),
        "parece_nota": any(leitura_do_pdf["parece_nota"] for leitura_do_pdf in leituras_dos_pdfs),
        "parece_rps": any(leitura_do_pdf["parece_rps"] for leitura_do_pdf in leituras_dos_pdfs),
        "lido_por_ocr": any(leitura_do_pdf.get("lido_por_ocr") for leitura_do_pdf in leituras_dos_pdfs),
    }


def descricao_do_servico(xml: str) -> str:
    try:
        raiz_do_xml = etree.fromstring(xml.encode("utf-8"))
    except etree.XMLSyntaxError:
        return ""
    for tag_do_xml in raiz_do_xml.iter():
        if isinstance(tag_do_xml.tag, str) and etree.QName(tag_do_xml).localname in TAGS_DA_DESCRICAO_DO_SERVICO:
            return (tag_do_xml.text or "").strip()
    return ""


def descricao_e_generica(descricao: str, frases_genericas: list[str], minimo_de_letras: int) -> bool:
    descricao_sem_as_frases = texto_normalizado(descricao)
    frases_da_maior_para_a_menor = sorted(
        (texto_normalizado(frase) for frase in frases_genericas), key=len, reverse=True
    )
    for frase_generica in frases_da_maior_para_a_menor:
        descricao_sem_as_frases = re.sub(r"\b" + re.escape(frase_generica) + r"\b", " ", descricao_sem_as_frases)
    return len(re.findall(r"[a-z]", descricao_sem_as_frases)) < minimo_de_letras


def expressao_da_especie() -> pl.Expr:
    return (
        pl.col("num_doc_normalizado")
        .cast(pl.Utf8)
        .str.to_uppercase()
        .str.replace_all(r"[^A-Z0-9]", "")
        .str.extract(r"^([A-Z]+)\d+$", 1)
        .alias("especie")
    )


def expressao_do_numero_do_documento() -> pl.Expr:
    return (
        pl.col("num_doc_normalizado")
        .cast(pl.Utf8)
        .str.replace_all(r"\D", "")
        .str.strip_chars_start("0")
        .alias("numero_do_documento")
    )


def com_a_especie(titulos_do_erp: pl.DataFrame) -> pl.DataFrame:
    return titulos_do_erp.with_columns(expressao_da_especie(), expressao_do_numero_do_documento())


def abertos_que_entram(contas_a_pagar: pl.DataFrame) -> pl.DataFrame:
    nome_do_fornecedor = pl.coalesce(
        pl.col("razao_social").cast(pl.Utf8), pl.col("FORNECEDOR").cast(pl.Utf8)
    ).fill_null("")
    return contas_a_pagar.filter(
        (pl.col("entrada_manual").cast(pl.Utf8).fill_null("Não") != "Sim")
        & (pl.col("pagou").cast(pl.Utf8).fill_null("Não") != "Sim")
        & pl.col("no_erp").cast(pl.Boolean, strict=False).fill_null(True)
    ).with_columns(
        pl.col("cnpj").cast(pl.Utf8).str.replace_all(r"\D", "").str.zfill(14),
        pl.col("id_unico").cast(pl.Utf8),
        nome_do_fornecedor.alias("fornecedor"),
        expressao_da_especie(),
        expressao_do_numero_do_documento(),
    )


def titulos_da_janela(abertos: pl.DataFrame, hoje: date, dias_atras: int | None, dias_a_frente: int) -> pl.DataFrame:
    ultimo_vencimento = pl.lit(hoje).cast(pl.Date) + pl.duration(days=dias_a_frente)
    if dias_atras is None:
        return abertos.filter(pl.col("data_vencimento") <= ultimo_vencimento)
    primeiro_vencimento = pl.lit(hoje).cast(pl.Date) - pl.duration(days=dias_atras)
    return abertos.filter(pl.col("data_vencimento").is_between(primeiro_vencimento, ultimo_vencimento))


def apontamento(id_unico: str, codigo_da_regra: str, detalhe: str = "") -> dict:
    return {"id_unico": id_unico, "regra": codigo_da_regra, "detalhe": detalhe}


def titulos_para_casar(titulos: pl.DataFrame) -> list[dict]:
    return titulos.select(
        "id_unico", "num_doc_normalizado", "cnpj", pl.col("valor_original").alias("valor"), "data_vencimento"
    ).to_dicts()


def emissao_da_nota(nota: dict) -> date:
    return nota["emissao"] or date.min


def nota_desvinculada(id_unico: str, nota: dict, notas_desvinculadas: set[tuple[str, str]]) -> bool:
    return (id_unico, str(nota.get("chave") or "")) in notas_desvinculadas or (
        id_unico,
        str(nota.get("arquivo") or ""),
    ) in notas_desvinculadas


def ligacoes_dos_titulos(
    titulos: pl.DataFrame, notas: list[dict], notas_desvinculadas: set[tuple[str, str]]
) -> dict[str, dict]:
    indice_dos_titulos = xml_fiscal.indice_de_titulos(titulos_para_casar(titulos))
    ligacoes = {}
    for nota in sorted(notas, key=emissao_da_nota):
        if nota["cancelada"]:
            continue
        for titulo in xml_fiscal.titulos_do_documento(nota, indice_dos_titulos):
            if not nota_desvinculada(titulo["id_unico"], nota, notas_desvinculadas):
                ligacoes[titulo["id_unico"]] = nota
    return ligacoes


def notas_por_emitente_e_numero(notas: list[dict]) -> dict[tuple[str, str], list[dict]]:
    indice_das_notas: dict[tuple[str, str], list[dict]] = {}
    for nota in notas:
        for forma_do_numero in xml_fiscal.formas_do_numero(nota["numero"]):
            indice_das_notas.setdefault((nota["emitente_cnpj"], forma_do_numero), []).append(nota)
    return indice_das_notas


def nota_cabe_no_titulo(titulo: dict, nota: dict) -> bool:
    valor_do_titulo = float(titulo["valor_original"] or 0)
    if nota["valor"] and valor_do_titulo > float(nota["valor"]) + 0.05:
        return False
    vencimento_do_titulo, emissao = titulo["data_vencimento"], nota["emissao"]
    return not (vencimento_do_titulo and emissao and vencimento_do_titulo < emissao - timedelta(days=1))


def notas_com_o_numero_do_titulo(
    titulo: dict, indice_das_notas: dict[tuple[str, str], list[dict]], notas_desvinculadas: set[tuple[str, str]]
) -> list[dict]:
    especie_e_numeros = xml_fiscal.numeros_do_titulo(titulo["num_doc_normalizado"])
    if not especie_e_numeros:
        return []
    achadas = []
    for numero in especie_e_numeros[1]:
        for nota in indice_das_notas.get((titulo["cnpj"], numero), []):
            if nota not in achadas and not nota_desvinculada(titulo["id_unico"], nota, notas_desvinculadas):
                achadas.append(nota)
    return achadas


def notas_do_titulo(
    titulo: dict, indice_das_notas: dict[tuple[str, str], list[dict]], notas_desvinculadas: set[tuple[str, str]]
) -> list[dict]:
    return [
        nota
        for nota in notas_com_o_numero_do_titulo(titulo, indice_das_notas, notas_desvinculadas)
        if nota_cabe_no_titulo(titulo, nota)
    ]


def notas_menores_que_o_titulo(
    titulo: dict,
    indice_das_notas: dict[tuple[str, str], list[dict]],
    notas_desvinculadas: set[tuple[str, str]],
    dias_entre_a_nota_e_o_titulo: int,
) -> list[dict]:
    emissao_do_titulo = titulo["data_emissao"]
    if emissao_do_titulo is None:
        return []
    valor_do_titulo = float(titulo["valor_original"] or 0)
    menores = []
    for nota in notas_com_o_numero_do_titulo(titulo, indice_das_notas, notas_desvinculadas):
        if (
            not nota["cancelada"]
            and nota["valor"]
            and nota["emissao"]
            and abs((nota["emissao"] - emissao_do_titulo).days) <= dias_entre_a_nota_e_o_titulo
            and valor_do_titulo > float(nota["valor"]) + 0.05
        ):
            menores.append(nota)
    return menores


class NotaDeNumeroCortado(NamedTuple):
    nota: dict
    numero_no_padrao: str
    cortado_pelo_comeco: bool


def nota_de_numero_cortado(
    titulo: dict,
    notas_do_emitente: list[dict],
    notas_desvinculadas: set[tuple[str, str]],
    dias_entre_a_nota_e_o_titulo: int,
) -> NotaDeNumeroCortado | None:
    documento = re.sub(r"[^A-Z0-9]", "", str(titulo.get("num_doc_normalizado") or "").upper())
    numero_e_parcela = re.fullmatch(r"NFS(\d{7})(\d{2})", documento)
    emissao_do_titulo, valor_do_titulo = titulo.get("data_emissao"), titulo.get("valor_original")
    if not numero_e_parcela or emissao_do_titulo is None or not valor_do_titulo:
        return None
    sete_digitos_no_control, parcela = numero_e_parcela.groups()
    notas_que_casam = []
    for nota in notas_do_emitente:
        numero_da_nota = str(nota.get("numero") or "")
        if (
            nota.get("tipo") != "NFS"
            or nota.get("cancelada")
            or not re.fullmatch(r"\d{9}", numero_da_nota)
            or not nota.get("emissao")
            or nota.get("valor") is None
            or abs(float(nota["valor"]) - float(valor_do_titulo)) > 0.05
            or abs((nota["emissao"] - emissao_do_titulo).days) > dias_entre_a_nota_e_o_titulo
            or nota_desvinculada(titulo["id_unico"], nota, notas_desvinculadas)
        ):
            continue
        if sete_digitos_no_control in (numero_da_nota[:7], numero_da_nota[-7:]):
            notas_que_casam.append(
                NotaDeNumeroCortado(
                    nota, f"NFS{numero_da_nota[:7]}{parcela}", sete_digitos_no_control == numero_da_nota[:7]
                )
            )
    return notas_que_casam[0] if len(notas_que_casam) == 1 else None


def periodo_das_notas(notas: list[dict], dias_de_espera: int) -> tuple[date, date] | None:
    emissoes_das_notas = [nota["emissao"] for nota in notas if nota["emissao"]]
    if not emissoes_das_notas:
        return None
    return min(emissoes_das_notas), max(emissoes_das_notas) - timedelta(days=dias_de_espera)


def regras_da_nota(
    dados_da_revenda: DadosDaRevenda,
    especies_de_nota: list[str],
    dias_de_espera: int,
    dias_entre_a_nota_e_o_titulo: int,
) -> list[dict]:
    apontamentos = []
    if not dados_da_revenda.notas:
        return apontamentos
    indice_das_notas_da_revenda = notas_por_emitente_e_numero(dados_da_revenda.notas)
    indice_das_notas_de_outras_empresas = notas_por_emitente_e_numero(dados_da_revenda.notas_de_outras_empresas)
    notas_de_cada_emitente: dict[str, list[dict]] = {}
    for nota in dados_da_revenda.notas:
        notas_de_cada_emitente.setdefault(nota["emitente_cnpj"], []).append(nota)
    periodo = periodo_das_notas(dados_da_revenda.notas, dias_de_espera)
    for titulo in dados_da_revenda.titulos.iter_rows(named=True):
        id_unico = titulo["id_unico"]
        if id_unico in dados_da_revenda.ligacoes:
            continue
        notas_da_revenda = notas_do_titulo(titulo, indice_das_notas_da_revenda, dados_da_revenda.notas_desvinculadas)
        if any(not nota["cancelada"] for nota in notas_da_revenda):
            continue
        if notas_da_revenda:
            nota_cancelada = notas_da_revenda[0]
            detalhe = f"nota {nota_cancelada['numero']}, chave {nota_cancelada['chave']}"
            if nota_cancelada.get("cancelada_em"):
                detalhe += f", cancelada em {data_br(nota_cancelada['cancelada_em'])}"
            apontamentos.append(apontamento(id_unico, "nota_cancelada", detalhe))
            continue
        nota_cortada = nota_de_numero_cortado(
            titulo,
            notas_de_cada_emitente.get(titulo["cnpj"], []),
            dados_da_revenda.notas_desvinculadas,
            dias_entre_a_nota_e_o_titulo,
        )
        if nota_cortada:
            if not nota_cortada.cortado_pelo_comeco:
                apontamentos.append(
                    apontamento(
                        id_unico,
                        "numero_da_nfse_cortado",
                        f"nota {nota_cortada.nota['numero']}; no ERP {titulo['num_doc']} ficou o fim do número; "
                        f"com o começo, como nos outros: {nota_cortada.numero_no_padrao}",
                    )
                )
            continue
        notas_menores = notas_menores_que_o_titulo(
            titulo, indice_das_notas_da_revenda, dados_da_revenda.notas_desvinculadas, dias_entre_a_nota_e_o_titulo
        )
        if notas_menores:
            nota_menor = notas_menores[0]
            diferenca = float(titulo["valor_original"] or 0) - float(nota_menor["valor"])
            apontamentos.append(
                apontamento(
                    id_unico,
                    "valor_maior_que_a_nota",
                    f"título {reais(titulo['valor_original'])}; nota {nota_menor['numero']} de {reais(nota_menor['valor'])}, "
                    f"emitida em {data_br(nota_menor['emissao'])} ({reais(diferenca)} a mais)",
                )
            )
            continue
        if titulo["especie"] not in set(especies_de_nota):
            continue
        notas_de_outra_empresa = [
            nota
            for nota in notas_do_titulo(
                titulo, indice_das_notas_de_outras_empresas, dados_da_revenda.notas_desvinculadas
            )
            if not nota["cancelada"]
        ]
        if notas_de_outra_empresa:
            nota_de_outra_empresa = notas_de_outra_empresa[0]
            apontamentos.append(
                apontamento(
                    id_unico,
                    "nota_de_outra_empresa",
                    f"nota {nota_de_outra_empresa['numero']} emitida para o CNPJ {cnpj_formatado(nota_de_outra_empresa['empresa'])}",
                )
            )
            continue
        emissao_do_titulo = titulo["data_emissao"]
        if periodo is None or emissao_do_titulo is None or not (periodo[0] <= emissao_do_titulo <= periodo[1]):
            continue
        detalhe = f"procurada nas notas recebidas de {data_br(periodo[0])} a {data_br(periodo[1])}"
        leitura_dos_pdfs = dados_da_revenda.leituras_por_id.get(id_unico)
        if leitura_dos_pdfs and leitura_dos_pdfs["chaves"]:
            detalhe += "; a chave do PDF da pasta também não está entre elas"
            situacoes_das_chaves = [
                (dados_da_revenda.situacao_na_sefaz_por_chave.get(chave) or {}).get("situacao")
                for chave in leitura_dos_pdfs["chaves"]
            ]
            if "autorizada" in situacoes_das_chaves:
                detalhe += ", mas a SEFAZ confirma que ela existe: a nota não chegou para a empresa (pode estar em nome de outra)"
        apontamentos.append(apontamento(id_unico, "nota_nao_encontrada", detalhe))
    return apontamentos


def parcelas_iguais(valor_do_titulo: float, valor_da_nota: float, tolerancia_valor: float) -> bool:
    for numero_de_partes in range(2, MAXIMO_DE_PARCELAS_IGUAIS + 1):
        if abs(valor_da_nota / numero_de_partes - valor_do_titulo) <= tolerancia_valor:
            return True
    return False


def regras_das_parcelas(dados_da_revenda: DadosDaRevenda, tolerancia_valor: float, tolerancia_dias: int) -> list[dict]:
    apontamentos = []
    for titulo in dados_da_revenda.titulos.iter_rows(named=True):
        id_unico = titulo["id_unico"]
        nota_ligada = dados_da_revenda.ligacoes.get(id_unico)
        if not nota_ligada or nota_ligada["tipo"] != "NFE":
            continue
        parcelas_da_nota = dados_da_revenda.parcelas_por_chave.get(nota_ligada["chave"]) or []
        if not parcelas_da_nota:
            continue
        valor_do_titulo = float(titulo["valor_original"] or 0)
        soma_das_parcelas = sum(parcela["valor"] for parcela in parcelas_da_nota)
        if len(parcelas_da_nota) > 1 and abs(valor_do_titulo - soma_das_parcelas) <= tolerancia_valor:
            continue
        parcelas_do_mesmo_valor = [
            parcela for parcela in parcelas_da_nota if abs(parcela["valor"] - valor_do_titulo) <= tolerancia_valor
        ]
        if not parcelas_do_mesmo_valor:
            if parcelas_iguais(valor_do_titulo, soma_das_parcelas, tolerancia_valor) or any(
                parcelas_iguais(valor_do_titulo, parcela["valor"], tolerancia_valor) for parcela in parcelas_da_nota
            ):
                continue
            valores_das_parcelas = ", ".join(reais(parcela["valor"]) for parcela in parcelas_da_nota[:6])
            if len(parcelas_da_nota) > 6:
                valores_das_parcelas += f" e mais {len(parcelas_da_nota) - 6}"
            apontamentos.append(
                apontamento(
                    id_unico,
                    "valor_diferente_da_parcela",
                    f"título {reais(valor_do_titulo)}; parcelas da nota: {valores_das_parcelas}",
                )
            )
            continue
        vencimento_do_titulo = titulo["data_vencimento"]
        vencimento_bate = any(
            parcela["vencimento"] and abs((parcela["vencimento"] - vencimento_do_titulo).days) <= tolerancia_dias
            for parcela in parcelas_do_mesmo_valor
        )
        if vencimento_do_titulo and not vencimento_bate:
            vencimentos_na_nota = ", ".join(data_br(parcela["vencimento"]) for parcela in parcelas_do_mesmo_valor[:3])
            apontamentos.append(
                apontamento(
                    id_unico,
                    "vencimento_diferente_da_parcela",
                    f"título vence {data_br(vencimento_do_titulo)}; a parcela de {reais(valor_do_titulo)} "
                    f"na nota vence {vencimentos_na_nota}",
                )
            )
    return apontamentos


def descrever_chaves(chaves: list[str]) -> str:
    notas_descritas = [f"nota {int(chave[25:34])} do CNPJ {cnpj_formatado(chave[6:20])}" for chave in chaves[:2]]
    if len(chaves) > 2:
        notas_descritas.append(f"e mais {len(chaves) - 2}")
    return ", ".join(notas_descritas)


def chave_com_o_numero_do_titulo(titulo: dict, chaves: list[str]) -> str | None:
    especie_e_numeros = xml_fiscal.numeros_do_titulo(titulo["num_doc_normalizado"])
    if not especie_e_numeros:
        return None
    for chave in chaves:
        if str(int(chave[25:34])) in especie_e_numeros[1]:
            return chave
    return None


def meses_de_diferenca(chave: str, dia) -> int | None:
    if dia is None:
        return None
    ano_da_chave, mes_da_chave = 2000 + int(chave[2:4]), int(chave[4:6])
    return abs((dia.year - ano_da_chave) * 12 + dia.month - mes_da_chave)


def chaves_do_fornecedor(titulo: dict, chaves: list[str]) -> list[str]:
    raiz_do_fornecedor = titulo["cnpj"][:8]
    return [chave for chave in chaves if chave[6:14] == raiz_do_fornecedor]


def regras_do_pdf_sem_xml(titulo: dict, leitura_dos_pdfs: dict, dados_da_revenda: DadosDaRevenda) -> list[dict]:
    apontamentos = []
    id_unico = titulo["id_unico"]
    chaves_do_pdf = leitura_dos_pdfs["chaves"]
    if chaves_do_pdf:
        chaves_deste_fornecedor = chaves_do_fornecedor(titulo, chaves_do_pdf)
        if not chaves_deste_fornecedor:
            return [apontamento(id_unico, "pdf_de_outro_fornecedor", f"PDF: {descrever_chaves(chaves_do_pdf)}")]
        if titulo["especie"] in ESPECIES_COM_CHAVE_DE_44:
            chave_do_titulo = chave_com_o_numero_do_titulo(titulo, chaves_deste_fornecedor)
            if chave_do_titulo is None:
                return [
                    apontamento(
                        id_unico,
                        "pdf_de_outra_nota",
                        f"PDF: {descrever_chaves(chaves_deste_fornecedor)}; título: {titulo['num_doc']}",
                    )
                ]
            meses = meses_de_diferenca(chave_do_titulo, titulo["data_emissao"])
            if meses is not None and meses > 1:
                apontamentos.append(
                    apontamento(
                        id_unico,
                        "pdf_de_outro_mes",
                        f"a chave é de {chave_do_titulo[4:6]}/20{chave_do_titulo[2:4]}; título emitido em {data_br(titulo['data_emissao'])}",
                    )
                )
            na_sefaz = dados_da_revenda.situacao_na_sefaz_por_chave.get(chave_do_titulo) or {}
            if na_sefaz.get("situacao") == "nao_existe":
                apontamentos.append(
                    apontamento(
                        id_unico,
                        "chave_fora_da_sefaz",
                        f"{chave_do_titulo}: {na_sefaz.get('motivo') or 'não consta na SEFAZ'}",
                    )
                )
            elif na_sefaz.get("situacao") in ("cancelada", "denegada"):
                apontamentos.append(
                    apontamento(
                        id_unico,
                        "nota_cancelada",
                        f"pela chave do PDF, na SEFAZ: {na_sefaz['situacao']} ({chave_do_titulo})",
                    )
                )
    else:
        chaves_erradas = leitura_dos_pdfs.get("chaves_erradas") or []
        if chaves_erradas and leitura_dos_pdfs["parece_nota"]:
            apontamentos.append(apontamento(id_unico, "pdf_com_chave_invalida", f"PDF: {chaves_erradas[0]}"))
    cnpjs_do_pdf = leitura_dos_pdfs.get("cnpjs") or []
    empresas = set(dados_da_revenda.empresas_da_revenda)
    if leitura_dos_pdfs["parece_nota"] and cnpjs_do_pdf and empresas and not empresas & set(cnpjs_do_pdf):
        cnpjs_descritos = ", ".join(cnpj_formatado(cnpj) for cnpj in cnpjs_do_pdf[:3])
        apontamentos.append(apontamento(id_unico, "pdf_sem_o_cnpj_da_empresa", f"CNPJ no PDF: {cnpjs_descritos}"))
    return apontamentos


def descrever_nfse(nota: dict) -> str:
    return f"nº {nota['numero']}, emitida em {data_br(nota['emissao'])}, {reais(nota['valor'])}"


def nfse_do_rps(
    titulo: dict,
    notas: list[dict],
    notas_desvinculadas: set[tuple[str, str]],
    tolerancia_valor: float,
    dias_entre_a_nota_e_o_titulo: int,
) -> list[dict]:
    emissao_do_titulo, valor_do_titulo = titulo.get("data_emissao"), titulo.get("valor_original")
    if emissao_do_titulo is None or not valor_do_titulo:
        return []
    candidatas = []
    for nota in notas:
        if nota.get("tipo") != "NFS" or nota["emitente_cnpj"] != titulo["cnpj"] or nota.get("cancelada"):
            continue
        valores_da_nota = [float(valor) for valor in (nota.get("valor"), nota.get("valor_servico")) if valor]
        if (
            not nota.get("emissao")
            or not any(abs(valor - float(valor_do_titulo)) <= tolerancia_valor for valor in valores_da_nota)
            or abs((nota["emissao"] - emissao_do_titulo).days) > dias_entre_a_nota_e_o_titulo
            or nota_desvinculada(titulo["id_unico"], nota, notas_desvinculadas)
        ):
            continue
        candidatas.append(nota)
    return candidatas


def arquivo_e_so_o_rps(leitura_dos_pdfs: dict) -> bool:
    return bool(
        leitura_dos_pdfs["tem_texto"]
        and leitura_dos_pdfs["parece_rps"]
        and not leitura_dos_pdfs["parece_nota"]
        and not leitura_dos_pdfs["chaves"]
        and not leitura_dos_pdfs.get("chaves_erradas")
    )


def nfse_dos_rps(
    dados_da_revenda: DadosDaRevenda,
    especies_de_nota: list[str],
    tolerancia_valor: float,
    dias_entre_a_nota_e_o_titulo: int,
) -> dict[str, list[dict]]:
    candidatas_por_id = {}
    for titulo in dados_da_revenda.titulos.iter_rows(named=True):
        leitura_dos_pdfs = dados_da_revenda.leituras_por_id.get(titulo["id_unico"])
        if (
            not leitura_dos_pdfs
            or titulo["id_unico"] in dados_da_revenda.ligacoes
            or titulo["especie"] not in set(especies_de_nota)
            or not arquivo_e_so_o_rps(leitura_dos_pdfs)
        ):
            continue
        candidatas_por_id[titulo["id_unico"]] = nfse_do_rps(
            titulo,
            dados_da_revenda.notas,
            dados_da_revenda.notas_desvinculadas,
            tolerancia_valor,
            dias_entre_a_nota_e_o_titulo,
        )
    return candidatas_por_id


def apontamento_do_rps(id_unico: str, candidatas: list[dict], dias_entre_a_nota_e_o_titulo: int) -> dict:
    if len(candidatas) == 1:
        return apontamento(
            id_unico,
            "arquivo_e_rps",
            f"a NFS-e correspondente existe no governo ({descrever_nfse(candidatas[0])}): pôr a nota no lugar do RPS",
        )
    if candidatas:
        numeros = ", ".join(str(nota["numero"]) for nota in candidatas[:4])
        return apontamento(
            id_unico,
            "arquivo_e_rps",
            f"{len(candidatas)} NFS-e deste prestador com o valor do título, perto da emissão: {numeros}",
        )
    return apontamento(
        id_unico,
        "rps_sem_nfse",
        f"nenhuma NFS-e deste prestador com o valor do título, emitida até {dias_entre_a_nota_e_o_titulo} dias "
        "dele, nas notas que o governo mandou (a prefeitura que não manda ao sistema nacional não aparece)",
    )


def regras_do_arquivo(
    dados_da_revenda: DadosDaRevenda,
    especies_de_nota: list[str],
    nfse_dos_rps_achadas: dict[str, list[dict]] | None = None,
    dias_entre_a_nota_e_o_titulo: int = 0,
) -> list[dict]:
    apontamentos = []
    for titulo in dados_da_revenda.titulos.iter_rows(named=True):
        id_unico = titulo["id_unico"]
        leitura_dos_pdfs = dados_da_revenda.leituras_por_id.get(id_unico)
        if not leitura_dos_pdfs:
            continue
        chaves_do_pdf = leitura_dos_pdfs["chaves"]
        nota_ligada = dados_da_revenda.ligacoes.get(id_unico)
        if nota_ligada:
            chave_do_governo = str(nota_ligada.get("chave") or "")
            if chaves_do_pdf and len(chave_do_governo) == 44 and chave_do_governo not in chaves_do_pdf:
                apontamentos.append(
                    apontamento(
                        id_unico,
                        "pdf_de_outra_nota",
                        f"PDF: {descrever_chaves(chaves_do_pdf)}; governo: nota {nota_ligada['numero']}",
                    )
                )
            elif (
                nfse_dos_rps_achadas is not None
                and nota_ligada["tipo"] == "NFS"
                and leitura_dos_pdfs["parece_rps"]
                and not leitura_dos_pdfs["parece_nota"]
            ):
                apontamentos.append(
                    apontamento(
                        id_unico,
                        "arquivo_e_rps",
                        f"a NFS-e do título existe no governo ({descrever_nfse(nota_ligada)}): pôr a nota no lugar do RPS",
                    )
                )
            continue
        apontamentos += regras_do_pdf_sem_xml(titulo, leitura_dos_pdfs, dados_da_revenda)
        if (
            chaves_do_pdf
            or leitura_dos_pdfs.get("chaves_erradas")
            or titulo["especie"] not in set(especies_de_nota)
            or not leitura_dos_pdfs["tem_texto"]
            or leitura_dos_pdfs["parece_nota"]
        ):
            continue
        if leitura_dos_pdfs["parece_rps"] and nfse_dos_rps_achadas is not None:
            apontamentos.append(
                apontamento_do_rps(id_unico, nfse_dos_rps_achadas.get(id_unico) or [], dias_entre_a_nota_e_o_titulo)
            )
        elif leitura_dos_pdfs["parece_rps"]:
            apontamentos.append(apontamento(id_unico, "arquivo_e_rps"))
        else:
            apontamentos.append(
                apontamento(
                    id_unico,
                    "arquivo_sem_nota",
                    "sem chave de acesso e sem cara de nota (pode ser só o boleto ou a fatura)",
                )
            )
    return apontamentos


def chaves_para_a_sefaz(dados_da_revenda: DadosDaRevenda) -> list[str]:
    chaves = []
    for titulo in dados_da_revenda.titulos.sort("data_vencimento").iter_rows(named=True):
        leitura_dos_pdfs = dados_da_revenda.leituras_por_id.get(titulo["id_unico"])
        if (
            titulo["id_unico"] in dados_da_revenda.ligacoes
            or not leitura_dos_pdfs
            or titulo["especie"] not in ESPECIES_COM_CHAVE_DE_44
        ):
            continue
        chave_do_titulo = chave_com_o_numero_do_titulo(titulo, chaves_do_fornecedor(titulo, leitura_dos_pdfs["chaves"]))
        if chave_do_titulo and chave_do_titulo[20:22] == MODELO_CONSULTADO_NA_SEFAZ and chave_do_titulo not in chaves:
            chaves.append(chave_do_titulo)
    return chaves


def situacao_inapta_por_cnpj(apontamentos_do_fiscal: pl.DataFrame) -> dict[str, str]:
    if apontamentos_do_fiscal.is_empty():
        return {}
    fornecedores_inaptos = (
        apontamentos_do_fiscal.filter(pl.col("regra") == "fornecedor_inapto")
        .sort("emissao", descending=True)
        .unique("emitente_cnpj", keep="first")
    )
    return {
        so_digitos_do_cnpj(fornecedor_inapto["emitente_cnpj"]): str(fornecedor_inapto["agora"] or "")
        for fornecedor_inapto in fornecedores_inaptos.iter_rows(named=True)
    }


def detalhe_da_receita(irregular_na_receita: dict) -> str:
    detalhe = f"Receita: {irregular_na_receita['situacao']}"
    if irregular_na_receita.get("data_situacao"):
        detalhe += f" desde {data_br(irregular_na_receita['data_situacao'])}"
    motivo = irregular_na_receita.get("motivo_situacao")
    if motivo and texto_normalizado(motivo) != "sem motivo":
        detalhe += f" ({motivo})"
    return detalhe


def regras_do_fornecedor(dados_da_revenda: DadosDaRevenda) -> list[dict]:
    apontamentos = []
    situacao_por_cnpj = situacao_inapta_por_cnpj(dados_da_revenda.apontamentos_do_fiscal)
    pagos = dados_da_revenda.pagos
    cnpjs_com_pagamento = set(pagos["cnpj"].to_list()) if not pagos.is_empty() else set()
    inicio_do_historico = pagos["data_vencimento"].min() if not pagos.is_empty() else None
    pagos_no_control = dados_da_revenda.cnpjs_pagos_no_control
    if pagos_no_control:
        cnpjs_com_pagamento |= pagos_no_control
        detalhe_sem_historico = "nenhum pagamento a este CNPJ em toda a história do ERP"
    else:
        detalhe_sem_historico = (
            f"nenhum pagamento a este CNPJ com vencimento desde {data_br(inicio_do_historico)} (o histórico do app)"
        )
    for titulo in dados_da_revenda.titulos.iter_rows(named=True):
        if titulo["cnpj"] in situacao_por_cnpj:
            apontamentos.append(
                apontamento(titulo["id_unico"], "fornecedor_inapto", f"SEFAZ: {situacao_por_cnpj[titulo['cnpj']]}")
            )
        irregular_na_receita = dados_da_revenda.irregulares_na_receita.get(titulo["cnpj"])
        if irregular_na_receita:
            apontamentos.append(
                apontamento(
                    titulo["id_unico"], "fornecedor_irregular_na_receita", detalhe_da_receita(irregular_na_receita)
                )
            )
        if (inicio_do_historico is not None or pagos_no_control) and titulo["cnpj"] not in cnpjs_com_pagamento:
            apontamentos.append(apontamento(titulo["id_unico"], "fornecedor_sem_historico", detalhe_sem_historico))
    return apontamentos


def regras_de_repeticao(
    dados_da_revenda: DadosDaRevenda, tolerancia_valor: float, outro_vencimento: bool = False
) -> list[dict]:
    apontamentos = []
    titulos_com_numero = dados_da_revenda.titulos.filter(pl.col("numero_do_documento").fill_null("") != "")
    if not dados_da_revenda.pagos.is_empty():
        pagos_para_comparar = dados_da_revenda.pagos.select(
            "cnpj",
            "numero_do_documento",
            "data_vencimento",
            "valor_pago",
            "data_pagamento",
            pl.col("id_unico").cast(pl.Utf8).alias("id_do_pago"),
        )
        titulos_ja_pagos = (
            titulos_com_numero.join(
                pagos_para_comparar, on=["cnpj", "numero_do_documento", "data_vencimento"], how="inner"
            )
            .filter(
                (pl.col("id_unico") != pl.col("id_do_pago"))
                & ((pl.col("valor_pago") - pl.col("valor_original")).abs() <= tolerancia_valor)
            )
            .sort("data_pagamento")
            .unique("id_unico", keep="first")
        )
        for titulo_ja_pago in titulos_ja_pagos.iter_rows(named=True):
            apontamentos.append(
                apontamento(
                    titulo_ja_pago["id_unico"],
                    "ja_pago",
                    f"pago em {data_br(titulo_ja_pago['data_pagamento'])} ({reais(titulo_ja_pago['valor_pago'])})",
                )
            )
        if outro_vencimento:
            pagos_em_outro_vencimento = (
                titulos_com_numero.filter(~pl.col("id_unico").is_in(titulos_ja_pagos["id_unico"].to_list()))
                .join(
                    pagos_para_comparar.rename({"data_vencimento": "vencimento_do_pago"}),
                    on=["cnpj", "numero_do_documento"],
                    how="inner",
                )
                .filter(
                    (pl.col("id_unico") != pl.col("id_do_pago"))
                    & (pl.col("vencimento_do_pago") != pl.col("data_vencimento"))
                    & ((pl.col("valor_pago") - pl.col("valor_original")).abs() <= tolerancia_valor)
                )
                .sort("data_pagamento")
                .unique("id_unico", keep="first")
            )
            for titulo_ja_pago in pagos_em_outro_vencimento.iter_rows(named=True):
                apontamentos.append(
                    apontamento(
                        titulo_ja_pago["id_unico"],
                        "ja_pago_em_outro_vencimento",
                        f"pago em {data_br(titulo_ja_pago['data_pagamento'])} ({reais(titulo_ja_pago['valor_pago'])}), "
                        f"com vencimento {data_br(titulo_ja_pago['vencimento_do_pago'])}",
                    )
                )
    abertos_para_comparar = dados_da_revenda.abertos.select(
        "cnpj",
        "numero_do_documento",
        pl.col("id_unico").alias("id_do_outro"),
        pl.col("num_doc").cast(pl.Utf8).alias("outro_documento"),
        pl.col("data_vencimento").alias("outro_vencimento"),
        pl.col("valor_original").alias("outro_valor"),
    )
    titulos_repetidos = (
        titulos_com_numero.join(abertos_para_comparar, on=["cnpj", "numero_do_documento"], how="inner")
        .filter(
            (pl.col("id_unico") != pl.col("id_do_outro"))
            & ((pl.col("outro_valor") - pl.col("valor_original")).abs() <= tolerancia_valor)
        )
        .sort("outro_vencimento")
        .unique("id_unico", keep="first")
    )
    for titulo_repetido in titulos_repetidos.iter_rows(named=True):
        apontamentos.append(
            apontamento(
                titulo_repetido["id_unico"],
                "titulo_repetido",
                f"também em aberto: {titulo_repetido['outro_documento']}, vencimento {data_br(titulo_repetido['outro_vencimento'])}",
            )
        )
    return apontamentos


def documento_legivel(documento) -> str:
    return " ".join(str(documento or "").split())


def palavras_do_nome(texto) -> set[str]:
    return set(re.findall(r"[A-Z]{4,}", texto_normalizado(texto).upper())) - PALAVRAS_QUE_NAO_DIZEM_O_FORNECEDOR


def nome_cita_o_fornecedor(nome_do_arquivo: str, palavras_do_fornecedor: set[str]) -> bool:
    return bool(palavras_do_nome(nome_do_arquivo) & palavras_do_fornecedor)


def titulos_de_contrato(titulos: pl.DataFrame, especies_de_contrato: list[str]) -> pl.DataFrame:
    if titulos.is_empty() or not especies_de_contrato:
        return titulos.clear()
    especie_do_titulo = pl.col("especie").fill_null("")
    return titulos.filter(
        pl.any_horizontal(
            [
                especie_do_titulo.str.starts_with(str(especie_de_contrato).upper())
                for especie_de_contrato in especies_de_contrato
            ]
        )
    )


def expressao_da_serie() -> pl.Expr:
    digitos_sem_a_parcela = (
        pl.col("num_doc_normalizado")
        .cast(pl.Utf8)
        .fill_null("")
        .str.replace_all(r"\D", "")
        .str.replace(r"\d{1,2}$", "")
    )
    return pl.concat_str([pl.col("especie").fill_null(""), digitos_sem_a_parcela]).alias("serie")


def periodo_em_dias(vencimentos: list[date]) -> int | None:
    distintos = sorted(set(vencimentos))
    if len(distintos) < 2:
        return None
    intervalos = sorted((depois - antes).days for antes, depois in zip(distintos, distintos[1:]))
    return intervalos[len(intervalos) // 2]


def vencimentos_dos_contratos(
    dados_da_revenda: DadosDaRevenda, especies_de_contrato: list[str]
) -> dict[str, list[tuple]]:
    parcelas_por_cnpj: dict[str, list[tuple]] = {}
    for contratos, coluna_do_valor in (
        (titulos_de_contrato(dados_da_revenda.abertos, especies_de_contrato), "valor_original"),
        (titulos_de_contrato(dados_da_revenda.pagos, especies_de_contrato), "valor_pago"),
    ):
        if contratos.is_empty():
            continue
        for cnpj, valor, vencimento in contratos.select(
            "cnpj", pl.col(coluna_do_valor).cast(pl.Float64), "data_vencimento"
        ).iter_rows():
            if valor is not None and vencimento is not None:
                parcelas_por_cnpj.setdefault(cnpj, []).append((valor, vencimento))
    return parcelas_por_cnpj


def regra_do_contrato_ja_pago(
    dados_da_revenda: DadosDaRevenda,
    especies_de_contrato: list[str],
    dias_antes: int,
    dias_depois: int,
    tolerancia_valor: float,
) -> list[dict]:
    contratos = titulos_de_contrato(dados_da_revenda.titulos, especies_de_contrato)
    pagos = dados_da_revenda.pagos
    if contratos.is_empty() or pagos.is_empty():
        return []
    coluna_do_documento = "num_doc" if "num_doc" in pagos.columns else "num_doc_normalizado"
    pagos_para_comparar = pagos.with_columns(expressao_da_serie()).select(
        "cnpj",
        pl.col("id_unico").cast(pl.Utf8).alias("id_do_pago"),
        pl.col("serie").alias("serie_do_pago"),
        pl.col(coluna_do_documento).cast(pl.Utf8).alias("documento_do_pago"),
        pl.col("valor_pago").cast(pl.Float64).alias("valor_do_pago"),
        pl.col("data_pagamento").alias("dia_do_pago"),
        pl.coalesce("data_vencimento", "data_pagamento").alias("vencimento_do_pago"),
    )
    contratos_para_comparar = contratos.with_columns(expressao_da_serie()).select(
        "id_unico", "cnpj", "serie", pl.col("valor_original").cast(pl.Float64), "data_vencimento"
    )
    primeiro_dia = pl.col("data_vencimento") - pl.duration(days=dias_antes)
    ultimo_dia = pl.col("data_vencimento") + pl.duration(days=dias_depois)
    candidatos = (
        contratos_para_comparar.join(pagos_para_comparar, on="cnpj", how="inner")
        .filter(
            (pl.col("id_do_pago") != pl.col("id_unico"))
            & (pl.col("serie_do_pago") != pl.col("serie"))
            & ((pl.col("valor_do_pago") - pl.col("valor_original")).abs() <= tolerancia_valor)
            & pl.col("vencimento_do_pago").is_between(primeiro_dia, ultimo_dia)
        )
        .with_columns(
            (pl.col("vencimento_do_pago") - pl.col("data_vencimento")).dt.total_days().abs().alias("distancia")
        )
        .sort(["id_unico", "distancia"])
    )
    if candidatos.is_empty():
        return []
    parcelas_por_cnpj = vencimentos_dos_contratos(dados_da_revenda, especies_de_contrato)
    apontamentos, ids_apontados = [], set()
    for candidato in candidatos.iter_rows(named=True):
        if candidato["id_unico"] in ids_apontados:
            continue
        vencimentos_do_contrato = [
            vencimento
            for valor, vencimento in parcelas_por_cnpj.get(candidato["cnpj"], [])
            if abs(valor - candidato["valor_original"]) <= tolerancia_valor
        ]
        periodo = periodo_em_dias(vencimentos_do_contrato)
        if periodo is not None and candidato["distancia"] * 2 >= periodo:
            continue
        ids_apontados.add(candidato["id_unico"])
        apontamentos.append(
            apontamento(
                candidato["id_unico"],
                "contrato_ja_pago",
                f"{documento_legivel(candidato['documento_do_pago'])} pago em {data_br(candidato['dia_do_pago'])} "
                f"({reais(candidato['valor_do_pago'])})",
            )
        )
    return apontamentos


def descrever_arquivo_de_contrato(arquivo_do_contrato: dict) -> str:
    descricao = f"{arquivo_do_contrato['nome']}, na pasta de {data_br(arquivo_do_contrato['dia'])}"
    if arquivo_do_contrato.get("ligado_a"):
        descricao += f", ligado a {', '.join(arquivo_do_contrato['ligado_a'])}"
    return descricao


def regra_do_contrato_informado_antes(dados_da_revenda: DadosDaRevenda, especies_de_contrato: list[str]) -> list[dict]:
    contratos = titulos_de_contrato(dados_da_revenda.titulos, especies_de_contrato)
    apontamentos = []
    for id_unico in contratos["id_unico"].to_list():
        arquivos_do_contrato = dados_da_revenda.arquivos_de_contrato_por_id.get(id_unico) or []
        if arquivos_do_contrato:
            apontamentos.append(
                apontamento(
                    id_unico,
                    "contrato_informado_antes",
                    "; ".join(
                        descrever_arquivo_de_contrato(arquivo_do_contrato)
                        for arquivo_do_contrato in arquivos_do_contrato[:3]
                    ),
                )
            )
    return apontamentos


def conteudo_por_chave(itens: pl.DataFrame) -> dict[str, str]:
    if itens.is_empty():
        return {}
    linhas = itens.select(
        "chave",
        pl.concat_str(
            [
                pl.col("cprod").cast(pl.Utf8).fill_null(""),
                pl.col("ucom").cast(pl.Utf8).fill_null(""),
                pl.col("qcom").cast(pl.Float64).round(4).cast(pl.Utf8).fill_null(""),
                pl.col("vuncom").cast(pl.Float64).round(6).cast(pl.Utf8).fill_null(""),
            ],
            separator="|",
        ).alias("linha"),
    )
    por_nota = linhas.group_by("chave").agg(pl.col("linha").sort().str.join(";").alias("conteudo"))
    return dict(zip(por_nota["chave"].to_list(), por_nota["conteudo"].to_list()))


def pares_de_notas_gemeas(
    notas_do_fornecedor: list[dict], conteudo: dict[str, str], dias_entre_as_notas: int, tolerancia_valor: float
) -> list[tuple[dict, dict]]:
    por_conteudo: dict[str, list[dict]] = {}
    for nota in notas_do_fornecedor:
        por_conteudo.setdefault(conteudo[nota["chave"]], []).append(nota)
    pares = []
    for notas_iguais in por_conteudo.values():
        em_ordem = sorted(notas_iguais, key=itemgetter("emissao"))
        for posicao, nota in enumerate(em_ordem):
            for outra in em_ordem[posicao + 1 :]:
                if (outra["emissao"] - nota["emissao"]).days > dias_entre_as_notas:
                    break
                if outra["numero"] != nota["numero"] and abs(outra["valor"] - nota["valor"]) <= tolerancia_valor:
                    pares.append((nota, outra))
    return pares


def a_gemea_mais_perto(nota: dict, pares_com_a_nota: list[tuple[dict, dict]]) -> dict:
    outras = [
        mais_nova if mais_velha["chave"] == nota["chave"] else mais_velha for mais_velha, mais_nova in pares_com_a_nota
    ]
    escolhida = outras[0]
    for outra in outras[1:]:
        if abs((outra["emissao"] - nota["emissao"]).days) < abs((escolhida["emissao"] - nota["emissao"]).days):
            escolhida = outra
    return escolhida


def regra_da_nota_gemea(dados_da_revenda: DadosDaRevenda, opcoes: dict, tolerancia_valor: float) -> list[dict]:
    conteudo = dados_da_revenda.conteudo_por_chave
    if not conteudo or not dados_da_revenda.ligacoes:
        return []
    dias_entre_as_notas = int(opcoes.get("dias_entre_as_notas", 7))
    dias_do_costume = int(opcoes.get("dias_do_costume", 180))
    notas_por_fornecedor: dict[tuple[str, str], list[dict]] = {}
    for nota in dados_da_revenda.notas:
        if nota["tipo"] == "NFE" and not nota["cancelada"] and nota["emissao"] and conteudo.get(nota["chave"]):
            notas_por_fornecedor.setdefault((nota["empresa"], nota["emitente_cnpj"]), []).append(nota)
    fornecedor_do_titulo = dict(
        zip(dados_da_revenda.titulos["id_unico"].to_list(), dados_da_revenda.titulos["fornecedor"].to_list())
    )
    pares_por_fornecedor: dict[tuple[str, str], list[tuple[dict, dict]]] = {}
    apontamentos = []
    for id_unico, nota in dados_da_revenda.ligacoes.items():
        if nota["tipo"] != "NFE" or not nota.get("emissao") or not conteudo.get(nota["chave"]):
            continue
        if fabricas.fabrica_do_fornecedor(fornecedor_do_titulo.get(id_unico)):
            continue
        do_fornecedor = (nota["empresa"], nota["emitente_cnpj"])
        if do_fornecedor not in pares_por_fornecedor:
            pares_por_fornecedor[do_fornecedor] = pares_de_notas_gemeas(
                notas_por_fornecedor.get(do_fornecedor, []), conteudo, dias_entre_as_notas, tolerancia_valor
            )
        pares = pares_por_fornecedor[do_fornecedor]
        pares_com_a_nota = [par for par in pares if nota["chave"] in (par[0]["chave"], par[1]["chave"])]
        if not pares_com_a_nota:
            continue
        chaves_deste_grupo = {nota_do_par["chave"] for par in pares_com_a_nota for nota_do_par in par}
        inicio_do_grupo = min(nota_do_par["emissao"] for par in pares_com_a_nota for nota_do_par in par)
        tem_costume = any(
            par[0]["chave"] not in chaves_deste_grupo
            and par[1]["chave"] not in chaves_deste_grupo
            and inicio_do_grupo - timedelta(days=dias_do_costume) <= par[1]["emissao"] < inicio_do_grupo
            for par in pares
        )
        if tem_costume:
            continue
        gemea = a_gemea_mais_perto(nota, pares_com_a_nota)
        detalhe = f"NF-e {gemea['numero']} de {data_br(gemea['emissao'])}: os mesmos itens e o mesmo valor ({reais(gemea['valor'])})"
        outras_gemeas = len(chaves_deste_grupo) - 2
        if outras_gemeas > 0:
            detalhe += f", e mais {outras_gemeas} nota(s) iguais"
        apontamentos.append(apontamento(id_unico, "nota_com_o_mesmo_conteudo", detalhe))
    return apontamentos


def costume_por_fornecedor(pagos: pl.DataFrame, coluna_comparada: str) -> dict[tuple[str, str], tuple]:
    if pagos.is_empty():
        return {}
    vezes_por_codigo = (
        pagos.filter(pl.col(coluna_comparada).is_not_null()).group_by("cnpj", "especie", coluna_comparada).len("vezes")
    )
    pagamentos_por_fornecedor = vezes_por_codigo.group_by("cnpj", "especie").agg(
        pl.col("vezes").sum().alias("pagamentos")
    )
    codigo_mais_comum = (
        vezes_por_codigo.sort(["vezes", coluna_comparada], descending=[True, False])
        .unique(["cnpj", "especie"], keep="first")
        .join(pagamentos_por_fornecedor, on=["cnpj", "especie"])
    )
    return {
        (costume_do_fornecedor["cnpj"], costume_do_fornecedor["especie"]): (
            costume_do_fornecedor[coluna_comparada],
            costume_do_fornecedor["vezes"],
            costume_do_fornecedor["pagamentos"],
        )
        for costume_do_fornecedor in codigo_mais_comum.iter_rows(named=True)
    }


def regras_de_costume(dados_da_revenda: DadosDaRevenda, historico_minimo: int, parcela_minima: float) -> list[dict]:
    apontamentos = []
    colunas_comparadas = (
        ("codigo_despesa", "despesa_fora_do_costume", dados_da_revenda.nomes_das_despesas),
        ("centro_custo", "centro_de_custo_fora_do_costume", dados_da_revenda.nomes_dos_centros),
    )
    for coluna_comparada, codigo_da_regra, nomes_dos_codigos in colunas_comparadas:
        costume_por_cnpj_e_especie = costume_por_fornecedor(dados_da_revenda.pagos, coluna_comparada)
        for titulo in dados_da_revenda.titulos.iter_rows(named=True):
            costume_do_fornecedor = costume_por_cnpj_e_especie.get((titulo["cnpj"], titulo["especie"]))
            codigo_do_titulo = titulo[coluna_comparada]
            if not costume_do_fornecedor or codigo_do_titulo is None:
                continue
            codigo_de_costume, vezes, pagamentos = costume_do_fornecedor
            if (
                pagamentos < historico_minimo
                or vezes / pagamentos < parcela_minima
                or codigo_do_titulo == codigo_de_costume
            ):
                continue
            nome_de_costume = nomes_dos_codigos.get(codigo_de_costume, "")
            nome_do_titulo = nomes_dos_codigos.get(codigo_do_titulo, "")
            apontamentos.append(
                apontamento(
                    titulo["id_unico"],
                    codigo_da_regra,
                    f"costuma ser {codigo_de_costume} {nome_de_costume} ({vezes} de {pagamentos} pagamentos); "
                    f"agora {codigo_do_titulo} {nome_do_titulo}".replace("  ", " ").strip(),
                )
            )
    return apontamentos


def capitulo_do_ncm(ncm) -> str:
    digitos = re.sub(r"\D", "", str(ncm or ""))
    return digitos[:2] if len(digitos) >= 2 else ""


def valor_por_capitulo(itens: list[dict]) -> dict[str, float]:
    valores: dict[str, float] = {}
    for item in itens:
        capitulo = capitulo_do_ncm(item.get("ncm"))
        if capitulo:
            valores[capitulo] = valores.get(capitulo, 0.0) + float(item.get("vprod") or 0)
    return valores


def capitulo_de_maior_valor(valores_por_capitulo: dict[str, float]) -> str:
    return sorted(valores_por_capitulo.items(), key=itemgetter(1), reverse=True)[0][0]


def natureza_da_nota(nota: dict, itens_por_chave: dict[str, list[dict]]) -> str | None:
    if nota.get("tipo") == "NFE":
        valores_por_capitulo = valor_por_capitulo(itens_por_chave.get(nota["chave"]) or [])
        return f"NCM {capitulo_de_maior_valor(valores_por_capitulo)}" if valores_por_capitulo else None
    if nota.get("tipo") == "NFS" and nota.get("codigo_servico"):
        return f"servico {nota['codigo_servico']}"
    return None


def descrever_natureza(natureza: str) -> str:
    tipo, codigo = natureza.split(" ", 1)
    if tipo == "NCM":
        return f"{nome_do_capitulo(codigo)} (capítulo {codigo} do NCM)"
    return f"serviço de código {codigo}"


class PerfilDasNotasPagas(NamedTuple):
    notas_por_despesa: dict
    capitulos_por_despesa: dict
    despesas_por_natureza: dict


def perfil_das_notas_pagas(dados_da_revenda: DadosDaRevenda) -> PerfilDasNotasPagas:
    pagos = dados_da_revenda.pagos
    despesa_do_pago = (
        dict(zip(pagos["id_unico"].cast(pl.Utf8).to_list(), pagos["codigo_despesa"].to_list()))
        if not pagos.is_empty()
        else {}
    )
    nota_e_despesa_por_chave: dict[str, tuple[dict, int]] = {}
    for id_do_pago, nota in dados_da_revenda.notas_dos_pagos.items():
        despesa = despesa_do_pago.get(id_do_pago)
        if despesa:
            nota_e_despesa_por_chave[nota["chave"]] = (nota, despesa)
    notas_por_despesa: dict = {}
    capitulos_por_despesa: dict = {}
    despesas_por_natureza: dict = {}
    for chave, (nota, despesa) in nota_e_despesa_por_chave.items():
        natureza = natureza_da_nota(nota, dados_da_revenda.itens_por_chave)
        if natureza is None:
            continue
        despesas_da_natureza = despesas_por_natureza.setdefault(natureza, {})
        despesas_da_natureza[despesa] = despesas_da_natureza.get(despesa, 0) + 1
        if nota["tipo"] != "NFE":
            continue
        notas_por_despesa[despesa] = notas_por_despesa.get(despesa, 0) + 1
        capitulos_da_despesa = capitulos_por_despesa.setdefault(despesa, {})
        for capitulo in valor_por_capitulo(dados_da_revenda.itens_por_chave.get(chave) or []):
            capitulos_da_despesa[capitulo] = capitulos_da_despesa.get(capitulo, 0) + 1
    return PerfilDasNotasPagas(notas_por_despesa, capitulos_por_despesa, despesas_por_natureza)


def nome_da_despesa(codigo, nomes_das_despesas: dict) -> str:
    return f"{codigo} {nomes_das_despesas.get(codigo, '')}".strip()


def item_fora_da_natureza(
    titulo: dict, nota: dict, perfil: PerfilDasNotasPagas, dados_da_revenda: DadosDaRevenda, opcoes_da_natureza: dict
) -> dict | None:
    despesa = titulo["codigo_despesa"]
    itens = dados_da_revenda.itens_por_chave.get(nota["chave"]) or []
    notas_da_despesa = perfil.notas_por_despesa.get(despesa, 0)
    if not itens or notas_da_despesa < int(opcoes_da_natureza.get("notas_minimas_da_despesa", 10)):
        return None
    capitulos_da_despesa = perfil.capitulos_por_despesa.get(despesa) or {}
    itens_fora = [
        item
        for item in itens
        if capitulo_do_ncm(item.get("ncm")) and not capitulos_da_despesa.get(capitulo_do_ncm(item.get("ncm")))
    ]
    if not itens_fora or len(itens_fora) == len(itens):
        return None
    valores_por_capitulo = valor_por_capitulo(itens)
    capitulo = capitulo_de_maior_valor(valores_por_capitulo)
    parte_do_valor = valores_por_capitulo[capitulo] / (sum(valores_por_capitulo.values()) or 1)
    maximo_no_detalhe = int(opcoes_da_natureza.get("itens_no_detalhe", 3))
    itens_descritos = "; ".join(
        f"{str(item.get('xprod') or '').strip()} {reais(item.get('vprod'))} (NCM {item.get('ncm')})"
        for item in itens_fora[:maximo_no_detalhe]
    )
    if len(itens_fora) > maximo_no_detalhe:
        itens_descritos += f"; e mais {len(itens_fora) - maximo_no_detalhe} item(ns)"
    return apontamento(
        titulo["id_unico"],
        "item_fora_da_natureza",
        f"natureza da nota: {descrever_natureza(f'NCM {capitulo}')}, {parte_do_valor:.0%} do valor; fora do que a "
        f"despesa {nome_da_despesa(despesa, dados_da_revenda.nomes_das_despesas)} comprou em {notas_da_despesa} notas: "
        f"{itens_descritos}",
    )


def despesa_fora_da_natureza(
    titulo: dict, nota: dict, perfil: PerfilDasNotasPagas, dados_da_revenda: DadosDaRevenda, opcoes_da_natureza: dict
) -> dict | None:
    despesa = titulo["codigo_despesa"]
    natureza = natureza_da_nota(nota, dados_da_revenda.itens_por_chave)
    despesas_da_natureza = perfil.despesas_por_natureza.get(natureza) if natureza else None
    if not despesas_da_natureza or despesas_da_natureza.get(despesa):
        return None
    total_de_notas = sum(despesas_da_natureza.values())
    despesa_de_costume, vezes = sorted(despesas_da_natureza.items(), key=itemgetter(1), reverse=True)[0]
    if total_de_notas < int(opcoes_da_natureza.get("notas_minimas_da_natureza", 5)) or vezes / total_de_notas < float(
        opcoes_da_natureza.get("parcela_minima", 0.8)
    ):
        return None
    nomes = dados_da_revenda.nomes_das_despesas
    return apontamento(
        titulo["id_unico"],
        "despesa_fora_da_natureza",
        f"notas de {descrever_natureza(natureza)} costumam ir para {nome_da_despesa(despesa_de_costume, nomes)} "
        f"({vezes} de {total_de_notas} notas pagas); esta foi para {nome_da_despesa(despesa, nomes)}",
    )


def regras_da_natureza(
    dados_da_revenda: DadosDaRevenda, opcoes_da_natureza: dict, itens_ligada: bool, despesa_ligada: bool
) -> list[dict]:
    if not (itens_ligada or despesa_ligada) or not dados_da_revenda.notas_dos_pagos:
        return []
    perfil = perfil_das_notas_pagas(dados_da_revenda)
    apontamentos = []
    for titulo in dados_da_revenda.titulos.iter_rows(named=True):
        nota = dados_da_revenda.ligacoes.get(titulo["id_unico"])
        if not nota or not titulo["codigo_despesa"]:
            continue
        achados = []
        if itens_ligada and nota["tipo"] == "NFE":
            achados.append(item_fora_da_natureza(titulo, nota, perfil, dados_da_revenda, opcoes_da_natureza))
        if despesa_ligada:
            achados.append(despesa_fora_da_natureza(titulo, nota, perfil, dados_da_revenda, opcoes_da_natureza))
        apontamentos += [achado for achado in achados if achado is not None]
    return apontamentos


def fator_da_despesa(opcoes_da_regra: dict, codigo_despesa, nome_do_fator_padrao: str) -> float:
    fatores_por_despesa = opcoes_da_regra.get("fator_por_despesa") or {}
    return float(fatores_por_despesa.get(str(codigo_despesa), opcoes_da_regra[nome_do_fator_padrao]))


def gastos_por_mes(pagos: pl.DataFrame, abertos: pl.DataFrame) -> pl.DataFrame:
    ids_dos_pagos = pagos["id_unico"].cast(pl.Utf8).to_list() if not pagos.is_empty() else []
    gastos_dos_pagos = pagos.select("codigo_despesa", pl.col("valor_pago").alias("gasto"), "data_vencimento")
    gastos_dos_abertos = abertos.filter(~pl.col("id_unico").is_in(ids_dos_pagos)).select(
        "codigo_despesa", pl.col("valor_original").alias("gasto"), "data_vencimento"
    )
    return (
        pl.concat([gastos_dos_pagos, gastos_dos_abertos], how="vertical_relaxed")
        .filter(pl.col("data_vencimento").is_not_null())
        .with_columns(pl.col("data_vencimento").dt.truncate("1mo").alias("mes"))
        .group_by("codigo_despesa", "mes")
        .agg(pl.col("gasto").sum())
    )


def primeiro_dia_do_mes_seguinte(dia: date) -> date:
    return date(dia.year + dia.month // 12, dia.month % 12 + 1, 1)


def meses_entre(primeiro: date, depois_do_ultimo: date) -> list[date]:
    primeiros_dias = []
    mes = date(primeiro.year, primeiro.month, 1)
    while mes < depois_do_ultimo:
        primeiros_dias.append(mes)
        mes = primeiro_dia_do_mes_seguinte(mes)
    return primeiros_dias


def expressoes_da_parcela_no_formato() -> list[pl.Expr]:
    numero_do_titulo = pl.col("num_doc").cast(pl.Utf8).fill_null("")
    no_formato = (numero_do_titulo.str.len_chars() == 12) & numero_do_titulo.str.slice(10, 2).str.contains(r"^\d\d$")
    return [
        pl.when(no_formato)
        .then(numero_do_titulo.str.slice(0, 10).str.replace_all(" ", ""))
        .otherwise(None)
        .alias("documento_sem_a_parcela"),
        pl.when(no_formato)
        .then(numero_do_titulo.str.slice(10, 2).cast(pl.Int64, strict=False))
        .otherwise(None)
        .alias("parcela"),
    ]


def parcelas_de_compra_ja_paga(titulos: pl.DataFrame, pagos: pl.DataFrame, fracao_minima: float | None) -> set[str]:
    if (
        fracao_minima is None
        or titulos.is_empty()
        or pagos.is_empty()
        or "num_doc" not in titulos.columns
        or "num_doc" not in pagos.columns
    ):
        return set()
    titulos_no_formato = (
        titulos.with_columns(expressoes_da_parcela_no_formato())
        .filter(pl.col("parcela").is_not_null())
        .select(pl.col("id_unico").cast(pl.Utf8), "cnpj", "documento_sem_a_parcela", "parcela", "valor_original")
    )
    parcelas_pagas = (
        pagos.with_columns(expressoes_da_parcela_no_formato())
        .filter(pl.col("parcela").is_not_null())
        .select("cnpj", "documento_sem_a_parcela", pl.col("parcela").alias("parcela_paga"), "valor_pago")
    )
    com_a_anterior_paga = titulos_no_formato.join(
        parcelas_pagas, on=["cnpj", "documento_sem_a_parcela"], how="inner"
    ).filter(
        (pl.col("parcela_paga") < pl.col("parcela"))
        & (pl.col("valor_pago") >= pl.col("valor_original") * float(fracao_minima))
    )
    return set(com_a_anterior_paga["id_unico"].to_list())


def regras_de_valor(
    dados_da_revenda: DadosDaRevenda,
    especies_de_nota: list[str],
    opcoes_de_valor: dict,
    opcoes_do_mes: dict,
    despesas_vigiadas: set[str],
) -> list[dict]:
    apontamentos = []
    so_de_nota = pl.col("especie").is_in(list(especies_de_nota))
    pagos_de_nota = (
        dados_da_revenda.pagos.filter(so_de_nota) if not dados_da_revenda.pagos.is_empty() else dados_da_revenda.pagos
    )
    if pagos_de_nota.is_empty():
        return apontamentos
    titulos_de_nota = dados_da_revenda.titulos.filter(so_de_nota)
    compra_ja_paga = parcelas_de_compra_ja_paga(
        titulos_de_nota, dados_da_revenda.pagos, opcoes_de_valor.get("parcela_anterior_paga")
    )
    pagamentos_por_despesa = pagos_de_nota.group_by("codigo_despesa").agg(
        pl.len().alias("pagamentos"), pl.col("valor_pago").median().alias("mediana")
    )
    historico_por_despesa = {
        historico["codigo_despesa"]: historico for historico in pagamentos_por_despesa.iter_rows(named=True)
    }
    for titulo in titulos_de_nota.iter_rows(named=True):
        if str(titulo["id_unico"]) in compra_ja_paga:
            continue
        historico_da_despesa = historico_por_despesa.get(titulo["codigo_despesa"])
        valor_do_titulo = float(titulo["valor_original"] or 0)
        if not historico_da_despesa or historico_da_despesa["pagamentos"] < int(opcoes_de_valor["historico_minimo"]):
            continue
        fator_da_regra = fator_da_despesa(opcoes_de_valor, titulo["codigo_despesa"], "fator_sobre_a_mediana")
        despesa_vigiada = str(titulo["codigo_despesa"]) in despesas_vigiadas
        valor_minimo = 0.0 if despesa_vigiada else float(opcoes_de_valor["valor_minimo"])
        if valor_do_titulo >= valor_minimo and valor_do_titulo > historico_da_despesa["mediana"] * fator_da_regra:
            apontamentos.append(
                apontamento(
                    titulo["id_unico"],
                    "valor_acima_do_normal",
                    f"{reais(valor_do_titulo)}; o normal desta despesa é {reais(historico_da_despesa['mediana'])} "
                    f"(mediana de {historico_da_despesa['pagamentos']} pagamentos){' — despesa vigiada' if despesa_vigiada else ''}",
                )
            )

    gastos_mensais = gastos_por_mes(pagos_de_nota, dados_da_revenda.abertos.filter(so_de_nota))
    gasto_por_despesa_e_mes = {
        (gasto_mensal["codigo_despesa"], gasto_mensal["mes"]): gasto_mensal["gasto"]
        for gasto_mensal in gastos_mensais.iter_rows(named=True)
    }
    inicio_do_historico = pagos_de_nota["data_vencimento"].min()
    if inicio_do_historico.day == 1:
        primeiro_mes_inteiro = inicio_do_historico
    else:
        primeiro_mes_inteiro = primeiro_dia_do_mes_seguinte(inicio_do_historico)
    for titulo in titulos_de_nota.iter_rows(named=True):
        vencimento_do_titulo = titulo["data_vencimento"]
        mes_do_titulo = date(vencimento_do_titulo.year, vencimento_do_titulo.month, 1)
        meses_anteriores = meses_entre(primeiro_mes_inteiro, mes_do_titulo)
        if len(meses_anteriores) < int(opcoes_do_mes["meses_minimos"]):
            continue
        codigo_despesa = titulo["codigo_despesa"]
        gasto_do_mes = gasto_por_despesa_e_mes.get((codigo_despesa, mes_do_titulo), 0.0)
        media_dos_meses = sum(
            gasto_por_despesa_e_mes.get((codigo_despesa, mes), 0.0) for mes in meses_anteriores
        ) / len(meses_anteriores)
        fator_da_regra = fator_da_despesa(opcoes_do_mes, codigo_despesa, "fator_sobre_a_media")
        despesa_vigiada = str(codigo_despesa) in despesas_vigiadas
        gasto_minimo = 0.0 if despesa_vigiada else float(opcoes_do_mes["gasto_minimo"])
        if gasto_do_mes < gasto_minimo or gasto_do_mes <= media_dos_meses * fator_da_regra:
            continue
        if media_dos_meses > 0:
            comparacao_com_a_media = f"média de {len(meses_anteriores)} meses: {reais(media_dos_meses)}"
        else:
            comparacao_com_a_media = f"nenhum gasto nos {len(meses_anteriores)} meses anteriores"
        apontamentos.append(
            apontamento(
                titulo["id_unico"],
                "gasto_do_mes_acima_do_normal",
                f"{mes_do_titulo:%m/%Y}: {reais(gasto_do_mes)}; {comparacao_com_a_media}{' — despesa vigiada' if despesa_vigiada else ''}",
            )
        )
    return apontamentos


def regra_do_preco(dados_da_revenda: DadosDaRevenda) -> list[dict]:
    apontamentos = []
    if dados_da_revenda.apontamentos_do_fiscal.is_empty():
        return apontamentos
    precos_que_subiram = dados_da_revenda.apontamentos_do_fiscal.filter(pl.col("regra") == "preco_subiu").sort(
        "valor", descending=True
    )
    itens_que_subiram_por_chave: dict[str, list[dict]] = {}
    for preco_que_subiu in precos_que_subiram.iter_rows(named=True):
        itens_que_subiram_por_chave.setdefault(preco_que_subiu["chave"], []).append(preco_que_subiu)
    for titulo in dados_da_revenda.titulos.iter_rows(named=True):
        nota_ligada = dados_da_revenda.ligacoes.get(titulo["id_unico"])
        itens_que_subiram = itens_que_subiram_por_chave.get(nota_ligada["chave"]) if nota_ligada else None
        if not itens_que_subiram:
            continue
        item_de_maior_valor = itens_que_subiram[0]
        detalhe = f"{item_de_maior_valor['xprod']}: {item_de_maior_valor['antes']} → {item_de_maior_valor['agora']}"
        if len(itens_que_subiram) > 1:
            detalhe += f" e mais {len(itens_que_subiram) - 1} item(ns)"
        apontamentos.append(apontamento(titulo["id_unico"], "preco_subiu", detalhe))
    return apontamentos


def regra_da_descricao(dados_da_revenda: DadosDaRevenda, opcoes_da_descricao: dict) -> list[dict]:
    apontamentos = []
    for titulo in dados_da_revenda.titulos.iter_rows(named=True):
        if titulo["id_unico"] not in dados_da_revenda.descricoes_por_id:
            continue
        descricao_da_nota = dados_da_revenda.descricoes_por_id[titulo["id_unico"]]
        if not descricao_da_nota:
            apontamentos.append(
                apontamento(titulo["id_unico"], "descricao_generica", "a nota não tem descrição do serviço")
            )
        elif descricao_e_generica(
            descricao_da_nota,
            opcoes_da_descricao.get("frases_genericas") or [],
            int(opcoes_da_descricao.get("minimo_de_letras", 0)),
        ):
            apontamentos.append(apontamento(titulo["id_unico"], "descricao_generica", f"“{descricao_da_nota[:120]}”"))
    return apontamentos


def assinatura_dispensada(titulo: dict, dispensa: dict) -> bool:
    if str(titulo.get("codigo_despesa")) in {str(codigo) for codigo in dispensa.get("despesas") or []}:
        return True
    if dispensa.get("fabrica_que_dispensa_a_auditoria"):
        fabrica = fabricas.fabrica_do_fornecedor(titulo.get("fornecedor"))
        return bool(fabrica and fabrica.get("dispensa_auditoria"))
    return False


def regra_da_assinatura(
    dados_da_revenda: DadosDaRevenda, assinatura_ligada: bool, dispensa: dict | None = None
) -> list[dict]:
    if not assinatura_ligada:
        return []
    return [
        apontamento(titulo["id_unico"], "sem_assinatura")
        for titulo in dados_da_revenda.titulos.iter_rows(named=True)
        if titulo["id_unico"] not in dados_da_revenda.assinados and not assinatura_dispensada(titulo, dispensa or {})
    ]


def titulos_conferidos(titulos: pl.DataFrame, gerado_em: datetime) -> pl.DataFrame:
    if titulos.is_empty():
        return pl.DataFrame(schema=ESQUEMA_DOS_CONFERIDOS)
    return titulos.select(
        pl.col("CNPJ_REV").cast(pl.Utf8),
        pl.col("id_unico").cast(pl.Utf8),
        pl.lit(gerado_em).cast(pl.Datetime).alias("gerado_em"),
    )


def montar(
    revenda: str, dados_da_revenda: DadosDaRevenda, configuracao: dict, gerado_em: datetime | None = None
) -> pl.DataFrame:
    gerado_em = gerado_em or datetime.now().replace(microsecond=0)
    if dados_da_revenda.titulos.is_empty():
        return pl.DataFrame(schema=ESQUEMA)
    especies_de_nota = list(configuracao.get("especies_de_nota") or [])
    tolerancia_valor = float(configuracao.get("tolerancia_valor", 0.05))
    opcoes_de_costume = configuracao.get("costume") or {}
    despesas_vigiadas = {str(codigo) for codigo in configuracao.get("despesas_vigiadas") or []}
    dias_entre_a_nota_e_o_titulo = int(configuracao.get("dias_entre_a_nota_e_o_titulo", 0))
    opcoes_dos_contratos = configuracao.get("contratos") or {}
    especies_de_contrato = list(opcoes_dos_contratos.get("especies") or [])
    nfse_dos_rps_achadas = None
    if regra_ligada(configuracao, "rps_pela_nfse"):
        nfse_dos_rps_achadas = nfse_dos_rps(
            dados_da_revenda, especies_de_nota, tolerancia_valor, dias_entre_a_nota_e_o_titulo
        )
    apontamentos = (
        regras_da_nota(
            dados_da_revenda,
            especies_de_nota,
            int(configuracao.get("dias_de_espera_da_nota", 0)),
            dias_entre_a_nota_e_o_titulo,
        )
        + regras_das_parcelas(
            dados_da_revenda, tolerancia_valor, int(configuracao.get("tolerancia_dias_vencimento", 0))
        )
        + regras_do_arquivo(dados_da_revenda, especies_de_nota, nfse_dos_rps_achadas, dias_entre_a_nota_e_o_titulo)
        + regras_do_fornecedor(dados_da_revenda)
        + regras_de_repeticao(
            dados_da_revenda, tolerancia_valor, regra_ligada(configuracao, "ja_pago_em_outro_vencimento")
        )
        + regra_da_nota_gemea(dados_da_revenda, configuracao.get("nota_gemea") or {}, tolerancia_valor)
        + regra_do_contrato_ja_pago(
            dados_da_revenda,
            especies_de_contrato,
            int(opcoes_dos_contratos.get("dias_antes", 20)),
            int(opcoes_dos_contratos.get("dias_depois", 10)),
            tolerancia_valor,
        )
        + regra_do_contrato_informado_antes(dados_da_revenda, especies_de_contrato)
        + regras_de_costume(
            dados_da_revenda,
            int(opcoes_de_costume.get("historico_minimo", 5)),
            float(opcoes_de_costume.get("parcela_minima", 0.8)),
        )
        + regras_da_natureza(
            dados_da_revenda,
            configuracao.get("natureza") or {},
            regra_ligada(configuracao, "item_fora_da_natureza"),
            regra_ligada(configuracao, "despesa_fora_da_natureza"),
        )
        + regras_de_valor(
            dados_da_revenda,
            especies_de_nota,
            configuracao.get("valor") or {},
            configuracao.get("mes") or {},
            despesas_vigiadas,
        )
        + regra_do_preco(dados_da_revenda)
        + regra_da_descricao(dados_da_revenda, configuracao.get("descricao") or {})
        + regra_da_assinatura(
            dados_da_revenda, bool(configuracao.get("assinatura")), configuracao.get("assinatura_dispensada")
        )
    )
    if nfse_dos_rps_achadas:
        rps_com_a_nfse = {id_unico for id_unico, candidatas in nfse_dos_rps_achadas.items() if len(candidatas) == 1}
        apontamentos = [
            apontamento_feito
            for apontamento_feito in apontamentos
            if not (
                apontamento_feito["regra"] == "nota_nao_encontrada" and apontamento_feito["id_unico"] in rps_com_a_nfse
            )
        ]
    regras_desligadas = set(configuracao.get("regras_desligadas") or [])
    apontamentos = [
        apontamento_feito for apontamento_feito in apontamentos if apontamento_feito["regra"] not in regras_desligadas
    ]
    if not apontamentos:
        return pl.DataFrame(schema=ESQUEMA)
    textos_das_regras = pl.DataFrame(
        [
            {"regra": codigo, "grupo": grupo, "gravidade": gravidade, "descricao": texto}
            for codigo, (grupo, gravidade, texto) in REGRAS.items()
        ]
    )
    colunas_do_titulo = dados_da_revenda.titulos.select(
        "CNPJ_REV",
        pl.lit(revenda).alias("revenda"),
        "id_unico",
        pl.col("data_vencimento").alias("vencimento"),
        pl.col("num_doc").cast(pl.Utf8).alias("documento"),
        "fornecedor",
        pl.col("cnpj").alias("fornecedor_cnpj"),
        pl.col("valor_original").alias("valor"),
        pl.col("codigo_despesa").cast(pl.Int64),
    )
    ordem_dos_grupos = {grupo: posicao for posicao, grupo in enumerate(GRUPOS)}
    apontamentos_completos = (
        pl.DataFrame(apontamentos, schema={"id_unico": pl.Utf8, "regra": pl.Utf8, "detalhe": pl.Utf8})
        .join(colunas_do_titulo, on="id_unico", how="inner")
        .join(textos_das_regras, on="regra", how="left")
        .with_columns(
            pl.lit(gerado_em).cast(pl.Datetime).alias("gerado_em"),
            pl.col("grupo").replace_strict(ordem_dos_grupos, default=99).alias("ordem_do_grupo"),
        )
    )
    return apontamentos_completos.sort(["vencimento", "documento", "ordem_do_grupo", "regra"]).select(
        [pl.col(nome_da_coluna).cast(tipo_da_coluna) for nome_da_coluna, tipo_da_coluna in ESQUEMA.items()]
    )
