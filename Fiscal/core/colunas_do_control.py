from __future__ import annotations

import polars as pl

PRODUTOS = {
    "VDPRDPRD_CODR": "CODRED",
    "VDPRDPRD_DESCR": "PRODUTO",
    "VDPRDPRD_CFAM": "FAMILIA",
    "VDPRDPRD_NRO": "NRO_FAMILIA",
    "VDPRDPRD_UNID": "COD_UNIDADE",
    "VDPRDPRD_QTDUN": "UNIDADE",
    "VDPRDPRD_CODCIA2": "COD_PROD_FORN",
    "VDPRDPRD_CODCIA3": "COD_PROD_FORN_2",
    "VDPRDPRD_CANCSN": "CANCELADO",
    "VDPRDPRD_INCLDT": "DATA_INCLUSAO",
    "VDPRDPRD_INCLHR": "HORA_INCLUSAO",
    "VDPRDPRD_CODBARRA": "COD_BARRAS",
    "VDPRDPRD_EAN_UNI_FRAC": "EAN_UNIDADE_FRACIONADA",
    "VDPRDPRD_EAN_CXA_COMP": "EAN_CAIXA_COMPLETA",
    "VDPRDPRD_EAN_CAP_SIMP": "EAN_CAPA_SIMPLES",
    "VDPRDPRD_TPPRD": "TIPO_PRODUTO",
    "VDPRDPRD_GRPPRD": "GRUPO_PRODUTO",
    "VDPRDPRD_GRPGER": "GRUPO_GERENCIAL",
    "VDPRDPRD_GRUPO": "GRUPO_FISCAL",
}

NATUREZAS = {
    "VDNOPNAT_NOP": "NATUREZA",
    "VDNOPNAT_DESCRRED": "DESCRICAO",
    "VDNOPNAT_INTEST": "INTEGRA_ESTOQUE",
    "VDNOPNAT_INTRECEB": "GERA_TITULO",
    "VDNOPNAT_TRIBICMS": "CREDITO_ICMS",
    "VDNOPNAT_PIS": "CREDITO_PIS_COFINS",
    "VDNOPNAT_NATOPFRE2": "CFOP",
}

DESPESAS = {
    "GEGENDES_COD": "CODIGO",
    "GEGENDES_CODR": "CODRED",
}

FORNECEDORES = {
    "PGCADFOR_CGC": "CNPJ_CPF",
    "PGCADFOR_CODRED": "CODIGO",
    "PGCADFOR_RAZAO": "RAZAO",
    "PGCADFOR_SIGLA": "SIGLA",
    "PGCADFOR_INATIVO": "INATIVO",
    "PGCADFOR_TPFOR": "TIPO_FORNECEDOR",
    "PGCADFOR_CRE": "CONTA_CONTABIL",
    "PGCADFOR_DESP": "DESPESA",
    "PGCADFOR_CCUSTO": "CENTRO_CUSTO",
    "PGCADFOR_EST": "UF",
    "PGCADFOR_MUN": "CIDADE",
    "PGCADFOR_CPG": "CPG",
    "PGCADFOR_TIPOEMPR": "TIPO_EMPRESA",
}

DE_PARA_PRODUTO = {
    "LFINDPRO_CGC": "CNPJ_FORN",
    "LFINDPRO_CODPRD_FORN": "COD_PROD_FORN",
    "LFINDPRO_CODRED_CTR": "CODRED",
    "LFINDPRO_FAT_CONV_COMPRA": "FATOR",
    "LFINDPRO_CANCSN": "CANCELADO",
    "LFINDPRO_INCLDT": "DATA_INCLUSAO",
    "LFINDPRO_INCLSIGLA": "SIGLA",
}

DE_PARA_CFOP = {
    "LFINDCFO_CFOP_DE": "CFOP_DE",
    "LFINDCFO_CGC": "CNPJ_FORN",
    "LFINDCFO_CFOP_PARA": "CFOP_PARA",
    "LFINDCFO_CODR_PROD": "CODRED",
    "LFINDCFO_CODNAT": "NATUREZA",
    "LFINDCFO_CODOCO": "OCORRENCIA",
    "LFINDCFO_CANCSN": "CANCELADO",
    "LFINDCFO_INCLDT": "DATA_INCLUSAO",
    "LFINDCFO_INCLSIGLA": "SIGLA",
    "LFINDCFO_CODNAT_DEV": "NATUREZA_DEVOLUCAO",
    "LFINDCFO_CODOCO_BRODEF": "OCORRENCIA_BRODEF",
    "LFINDCFO_CTE": "CTE",
    "LFINDCFO_NF_MANUAL": "NF_MANUAL",
    "LFINDCFO_CODOCO_NF_MANUAL": "OCORRENCIA_NF_MANUAL",
    "LFINDCFO_LEITURA_APTR2009": "LEITURA_APTR2009",
    "LFINDCFO_RECALC_PIS_COF": "RECALCULA_PIS_COFINS",
}

NOTAS_DE_ORIGEM = {
    "LFMENRSL_CHAVE_NFE": "CHAVE_NFE",
    "LFMENRSL_NF": "NUMERO",
    "LFMENRSL_SER": "SERIE",
    "LFMENRSL_MODELO": "MODELO",
    "LFMENRSL_COD_CLI_FOR": "CODCLI",
    "LFMENRSL_ANOE": "ANO_EMISSAO",
    "LFMENRSL_MESE": "MES_EMISSAO",
    "LFMENRSL_DIAE": "DIA_EMISSAO",
    "LFMENRSL_VALOR": "VALOR",
    "LFMENRSL_CANCSN": "CANCELADA",
    "LFMENRSL_CFISC_4": "CFOP",
}

LIVRO_ITENS = {
    "LFMENPFM_ENSAI": "ENTRADA_SAIDA",
    "LFMENPFM_NF": "NUMERO",
    "LFMENPFM_SER": "SERIE",
    "LFMENPFM_CGCEMI9": "CNPJ_PARTICIPANTE",
    "LFMENPFM_CFISC": "CFOP_INICIO",
    "LFMENPFM_CFISC_D": "CFOP_DIGITO",
    "LFMENPFM_NBM": "ITEM",
    "LFMENPFM_CODPRDR": "CODRED",
    "LFMENPFM_QTD": "QUANTIDADE",
    "LFMENPFM_QTDS": "QUANTIDADE_AVULSA",
    "LFMENPFM_PRECO": "VALOR",
    "LFMENPFM_DESCTO": "DESCONTO",
    "LFMENPFM_VLRFRETE": "FRETE",
    "LFMENPFM_BASEICM": "BASE_ICMS",
    "LFMENPFM_ALIQICM": "ALIQ_ICMS",
    "LFMENPFM_VALICM": "ICMS",
    "LFMENPFM_BASEICMR": "BASE_ICMS_ST",
    "LFMENPFM_VALICMR": "ICMS_ST",
    "LFMENPFM_VLRIPI": "IPI",
    "LFMENPFM_CST_PIS": "CST_PIS",
    "LFMENPFM_BC_PIS": "BASE_PIS",
    "LFMENPFM_ALIQ_PIS": "ALIQ_PIS",
    "LFMENPFM_PIS_RECUP": "PIS",
    "LFMENPFM_CST_COFINS": "CST_COFINS",
    "LFMENPFM_BC_COF": "BASE_COFINS",
    "LFMENPFM_ALIQ_COF": "ALIQ_COFINS",
    "LFMENPFM_COFINS_RECUP": "COFINS",
    "LFMENPFM_CANCSN": "ITEM_CANCELADO",
}
CAPA_DA_SAIDA = {
    "LFMENRSL_NF": "NUMERO",
    "LFMENRSL_SER": "SERIE",
    "LFMENRSL_CHAVE_NFE": "CHAVE",
    "LFMENRSL_MODELO": "MODELO",
    "LFMENRSL_ANOE": "ANO_EMISSAO",
    "LFMENRSL_MESE": "MES_EMISSAO",
    "LFMENRSL_DIAE": "DIA_EMISSAO",
    "LFMENRSL_CANCSN": "CANCELADA",
}
CAPA_DA_ENTRADA = {
    "LFMENREL_NUMNF": "NUMERO",
    "LFMENREL_CGCEMI9": "CNPJ_PARTICIPANTE",
    "LFMENREL_CHAVE_NFE": "CHAVE",
    "LFMENREL_MODELO": "MODELO",
    "LFMENREL_DTE": "DATA_ENTRADA",
    "LFMENREL_CANCSN": "CANCELADA",
}

COLUNAS: dict[str, dict[str, str]] = {
    "produtos": PRODUTOS,
    "naturezas": NATUREZAS,
    "despesas": DESPESAS,
    "fornecedores": FORNECEDORES,
    "de_para_produto": DE_PARA_PRODUTO,
    "de_para_cfop": DE_PARA_CFOP,
    "notas_de_origem": NOTAS_DE_ORIGEM,
    "livro_itens": LIVRO_ITENS,
}


def com_os_nomes(mapa: dict[str, str], lido: pl.DataFrame) -> pl.DataFrame:
    return lido.select([pl.col(coluna).alias(nome) for coluna, nome in mapa.items() if coluna in lido.columns])


def legiveis(coleta: str, lido: pl.DataFrame) -> pl.DataFrame:
    return com_os_nomes(COLUNAS[coleta], lido)


def do_control(coleta: str, registros: list[dict]) -> list[dict]:
    volta = {nome: coluna for coluna, nome in COLUNAS[coleta].items()}
    return [{volta.get(chave, chave): valor for chave, valor in registro.items()} for registro in registros]


def nome_do_campo(coluna: str) -> str | None:
    return PRODUTOS.get(f"VDPRDPRD_{coluna}")


NOMES_ANTIGOS: dict[str, dict[str, str]] = {
    "tb_produtos": {
        "CODR": "CODRED",
        "DESCR": "PRODUTO",
        "UNID": "COD_UNIDADE",
        "QTDUN": "UNIDADE",
        "CFAM": "FAMILIA",
        "NRO": "NRO_FAMILIA",
        "CANCSN": "CANCELADO",
        "CODCIA2": "COD_PROD_FORN",
        "CODCIA3": "COD_PROD_FORN_2",
        "INCLDT": "DATA_INCLUSAO",
        "INCLHR": "HORA_INCLUSAO",
        "TPPRD": "TIPO_PRODUTO",
        "GRPPRD": "GRUPO_PRODUTO",
        "GRPGER": "GRUPO_GERENCIAL",
        "GRUPO": "GRUPO_FISCAL",
    },
    "tb_naturezas": {
        "NOP": "NATUREZA",
        "INTEST": "INTEGRA_ESTOQUE",
        "INTRECEB": "GERA_TITULO",
        "TRIBICMS": "CREDITO_ICMS",
        "PIS": "CREDITO_PIS_COFINS",
    },
    "tb_fornecedores": {
        "CGC": "CNPJ_CPF",
        "TPFOR": "TIPO_FORNECEDOR",
        "CRE": "CONTA_CONTABIL",
        "DESP": "DESPESA",
        "CCUSTO": "CENTRO_CUSTO",
        "EST": "UF",
        "MUN": "CIDADE",
        "TIPOEMPR": "TIPO_EMPRESA",
    },
    "tb_de_para_produto": {
        "CGC": "CNPJ_FORN",
        "CPROD": "COD_PROD_FORN",
        "PRODUTO": "CODRED",
        "INCLDT": "DATA_INCLUSAO",
    },
    "tb_de_para_cfop": {"CFOP": "CFOP_DE", "CGC": "CNPJ_FORN", "CODR_PROD": "CODRED", "INCLDT": "DATA_INCLUSAO"},
    "tb_clientes": {"CGC": "CNPJ_CPF", "CODIGO": "CODCLI"},
    "tb_notas_de_origem": {"CLIENTE": "CODCLI", "CLIENTE_CGC": "CNPJ_CLIENTE"},
}
TABELA_DO_PARQUET = {
    "control_produtos": "tb_produtos",
    "control_naturezas": "tb_naturezas",
    "control_fornecedores": "tb_fornecedores",
    "control_de_para_produto": "tb_de_para_produto",
    "control_de_para_cfop": "tb_de_para_cfop",
    "control_clientes": "tb_clientes",
    "notas_de_origem": "tb_notas_de_origem",
}


def com_os_nomes_novos(parquet: str, tabela: pl.DataFrame) -> pl.DataFrame:
    tabela_do_fiscal = TABELA_DO_PARQUET.get(parquet)
    if tabela_do_fiscal is None:
        return tabela
    for antiga, nova in NOMES_ANTIGOS[tabela_do_fiscal].items():
        if antiga not in tabela.columns:
            continue
        if nova in tabela.columns:
            completada = pl.coalesce(pl.col(nova), pl.col(antiga).cast(tabela.schema[nova], strict=False))
            tabela = tabela.with_columns(completada.alias(nova)).drop(antiga)
        else:
            tabela = tabela.rename({antiga: nova})
    return tabela
