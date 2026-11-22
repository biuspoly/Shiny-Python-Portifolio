from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

import polars as pl
from loguru import logger

from core import cache, cfop, exportar, formato, revendas, sped, sped_gerar
from core.config import empresas
from core.config_arquivo import carregar_json

PASTA_DO_FINANCEIRO = Path(__file__).resolve().parents[4] / "Acompanhamento Financeiro" / "data"

IMPOSTOS = ("BASE_ICMS", "ICMS", "ISENTAS", "OUTRAS", "ICMS_ST", "IPI", "PIS", "COFINS")
LIVROS = {"E": "Entradas", "S": "Saídas"}
MESES_LADO_A_LADO = 12
NOMES_DOS_MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
NOMES_NA_PLANILHA = {
    "VALOR": "Valor contábil",
    "BASE_ICMS": "Base de cálculo do ICMS",
    "ICMS": "ICMS",
    "ISENTAS": "Isentas ou não tributadas",
    "OUTRAS": "Outras",
    "ICMS_ST": "ICMS-ST",
    "IPI": "IPI",
}
LIVROS_VAZIOS = {
    "LIVRO": pl.Utf8,
    "MES": pl.Utf8,
    "CFOP": pl.Utf8,
    "VALOR": pl.Float64,
    **{imposto: pl.Float64 for imposto in IMPOSTOS},
}
PARTES_DA_RECEITA = {
    "vendas": ("S", "Vendas"),
    "devolucao_de_compra": ("S", "Devolução de compra"),
    "devolucao_de_venda": ("E", "Devolução de venda"),
    "compras": ("E", "Compras"),
    "combustiveis": ("E", "Combustíveis e lubrificantes"),
}
PARTES_DA_BONIFICACAO = {"entrada": ("E", "Bonificação recebida"), "saida": ("S", "Bonificação dada")}
PARTES_DA_DEDUCAO = {"alugueis_pj": "Aluguéis PJ", "energia_eletrica": "Energia elétrica"}
AGRUPAMENTOS = {"cfop": "Por CFOP", "operacao": "Por operação"}


def configuracao() -> dict:
    lido = carregar_json("apuracao", {})
    return {
        "cfops": lido.get("cfops") or {},
        "receita_bruta": {
            parte: [str(codigo_do_cfop) for codigo_do_cfop in (lido.get("receita_bruta") or {}).get(parte) or []]
            for parte in PARTES_DA_RECEITA
        },
        "bonificacoes": {
            parte: [str(codigo_do_cfop) for codigo_do_cfop in (lido.get("bonificacoes") or {}).get(parte) or []]
            for parte in PARTES_DA_BONIFICACAO
        },
        "deducoes_por_despesa": {
            parte: [
                int(codigo_da_despesa)
                for codigo_da_despesa in (lido.get("deducoes_por_despesa") or {}).get(parte) or []
            ]
            for parte in PARTES_DA_DEDUCAO
        },
        "aliquotas_dos_outros_creditos": {
            tributo: (lido.get("aliquotas_dos_outros_creditos") or {}).get(tributo) for tributo in ("pis", "cofins")
        },
        "antecipado_por_despesa": [
            int(codigo_da_despesa) for codigo_da_despesa in lido.get("antecipado_por_despesa") or []
        ],
    }


def nome_da_operacao(codigo_do_cfop: str) -> str:
    do_config = configuracao()["cfops"].get(str(codigo_do_cfop)) or {}
    return do_config.get("resumo") or cfop.descricao(codigo_do_cfop)


def grupo_da_operacao(codigo_do_cfop: str) -> str:
    do_config = configuracao()["cfops"].get(str(codigo_do_cfop)) or {}
    return do_config.get("operacao") or nome_da_operacao(codigo_do_cfop) or str(codigo_do_cfop)


def livros_da_empresa(cnpj: str) -> pl.DataFrame:
    if not cnpj:
        return pl.DataFrame(schema=LIVROS_VAZIOS)
    lidos = cache.filtrado(
        "faturamento",
        (pl.col("EMITENTE") == cnpj) & (pl.col("CANCELADA") == 0),
        so=["LIVRO", "MES", "CFOP", "VALOR", *IMPOSTOS],
    )
    if lidos.is_empty():
        return pl.DataFrame(schema=LIVROS_VAZIOS)
    impostos_que_faltam = [
        pl.lit(None, dtype=pl.Float64).alias(imposto) for imposto in IMPOSTOS if imposto not in lidos.columns
    ]
    return lidos.with_columns(impostos_que_faltam).select(
        pl.col("LIVRO").cast(pl.Utf8),
        pl.col("MES").cast(pl.Utf8),
        pl.col("CFOP").cast(pl.Utf8),
        pl.col("VALOR").cast(pl.Float64),
        *[pl.col(imposto).cast(pl.Float64) for imposto in IMPOSTOS],
    )


def meses_com_livro(livros: pl.DataFrame) -> list[str]:
    if livros.is_empty():
        return []
    return sorted(livros["MES"].unique().to_list(), reverse=True)


def rotulo_mes(mes: str) -> str:
    return f"{mes[5:7]}/{mes[:4]}" if len(mes or "") == 7 else "-"


def rotulo_curto(mes: str) -> str:
    return f"{NOMES_DOS_MESES[int(mes[5:7]) - 1]}/{mes[2:4]}"


def tem_impostos(livros: pl.DataFrame, mes: str) -> bool:
    linhas_do_mes = livros.filter(pl.col("MES") == mes)
    return not linhas_do_mes.is_empty() and linhas_do_mes["ICMS"].null_count() < linhas_do_mes.height


def por_cfop(livros: pl.DataFrame, mes: str, livro: str) -> pl.DataFrame:
    linhas_do_livro = livros.filter((pl.col("MES") == mes) & (pl.col("LIVRO") == livro))
    somado = linhas_do_livro.group_by("CFOP").agg(
        pl.col("VALOR").sum(), *[pl.col(imposto).sum() for imposto in IMPOSTOS]
    )
    return somado.sort("CFOP")


def por_operacao(livro_por_cfop: pl.DataFrame) -> pl.DataFrame:
    if livro_por_cfop.is_empty():
        return livro_por_cfop.with_columns(pl.lit("").alias("OPERACAO"), pl.lit("").alias("CFOPS"))
    com_o_grupo = livro_por_cfop.with_columns(
        pl.col("CFOP").map_elements(grupo_da_operacao, return_dtype=pl.Utf8).alias("OPERACAO")
    )
    somado = com_o_grupo.group_by("OPERACAO").agg(
        pl.col("CFOP").sort().str.join(", ").alias("CFOPS"),
        pl.col("VALOR").sum(),
        *[pl.col(imposto).sum() for imposto in IMPOSTOS],
    )
    return somado.sort(["VALOR", "OPERACAO"], descending=[True, False])


def _total_da_coluna(livro_por_cfop: pl.DataFrame, coluna: str) -> float:
    if livro_por_cfop.is_empty():
        return 0.0
    return round(float(livro_por_cfop[coluna].sum() or 0), 2)


def apuracao(entradas: pl.DataFrame, saidas: pl.DataFrame) -> dict:
    debito = _total_da_coluna(saidas, "ICMS")
    credito = _total_da_coluna(entradas, "ICMS")
    saldo = round(debito - credito, 2)
    resumo = {
        "debito": debito,
        "credito": credito,
        "saldo": 0.0 if saldo == 0 else saldo,
        "cfops_entradas": entradas.height,
        "cfops_saidas": saidas.height,
    }
    for coluna in ("VALOR", "ICMS_ST", "IPI"):
        resumo[f"{coluna.lower()}_entradas"] = _total_da_coluna(entradas, coluna)
        resumo[f"{coluna.lower()}_saidas"] = _total_da_coluna(saidas, coluna)
    return resumo


TIPOS_DE_AJUSTE_NA_TELA = (
    "outros_debitos",
    "estornos_de_credito",
    "outros_creditos",
    "estornos_de_debito",
    "deducoes",
    "debitos_especiais",
)


def apuracao_do_sped(cnpj: str, mes: str) -> dict | None:
    if not cnpj or len(mes or "") != 7:
        return None
    arquivo_da_ficha = sped.raiz() / cnpj / "gerados" / f"{mes}.json"
    if not arquivo_da_ficha.exists():
        return None
    try:
        ficha = json.loads(arquivo_da_ficha.read_text(encoding="utf-8"))
        resumo = ficha["resumo"]
        ajustes_por_tipo = {tipo: 0.0 for tipo in TIPOS_DE_AJUSTE_NA_TELA}
        for ajuste in resumo.get("ajustes") or []:
            tipo = sped_gerar.TIPO_DO_AJUSTE.get(str(ajuste["codigo"])[3:4], "outros_debitos")
            ajustes_por_tipo[tipo] = round(ajustes_por_tipo[tipo] + float(ajuste["valor"]), 2)
        return {
            "gerado_em": str(ficha.get("gerado_em") or ""),
            "debitos": float(resumo["debitos"]),
            "creditos": float(resumo["creditos"]),
            "saldo_credor_anterior": float(ficha.get("saldo_credor_anterior") or 0),
            "a_recolher": float(resumo["a_recolher"]),
            "saldo_credor": float(resumo["saldo_credor"]),
            "ajustes": list(resumo.get("ajustes") or []),
            "ajustes_por_tipo": ajustes_por_tipo,
        }
    except Exception as exc:
        logger.warning(f"Apuracao: a ficha do SPED gerado {arquivo_da_ficha} -- {exc}")
        return None


def nome_do_tipo_de_ajuste(tipo: str) -> str:
    nome = sped_gerar.NOME_DO_TIPO_DE_AJUSTE.get(tipo, tipo)
    return nome[:1].upper() + nome[1:]


def texto_do_sped(apuracao_oficial: dict | None) -> str:
    if apuracao_oficial is None:
        return "-"
    if apuracao_oficial["saldo_credor"]:
        return f"credor {formato.moeda(apuracao_oficial['saldo_credor'])}"
    return formato.moeda(apuracao_oficial["a_recolher"])


def janela(ate: str, quantos: int = MESES_LADO_A_LADO) -> list[str]:
    ano, mes = int(ate[:4]), int(ate[5:7])
    meses_da_janela = []
    for _ in range(quantos):
        meses_da_janela.append(f"{ano:04d}-{mes:02d}")
        ano, mes = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
    return meses_da_janela[::-1]


def mes_a_mes(livros: pl.DataFrame, ate: str) -> pl.DataFrame:
    if len(ate or "") != 7:
        return pl.DataFrame(schema={"mes": pl.Utf8})
    meses_da_janela = pl.DataFrame({"mes": janela(ate)})
    somas_do_mes = (
        livros.filter(pl.col("MES").is_in(meses_da_janela["mes"].to_list()))
        .group_by("MES")
        .agg(
            pl.col("VALOR").filter(pl.col("LIVRO") == "E").sum().alias("entradas"),
            pl.col("VALOR").filter(pl.col("LIVRO") == "S").sum().alias("saidas"),
            pl.col("ICMS").filter(pl.col("LIVRO") == "E").sum().alias("credito"),
            pl.col("ICMS").filter(pl.col("LIVRO") == "S").sum().alias("debito"),
            pl.col("ICMS").is_not_null().any().alias("com_impostos"),
        )
        .rename({"MES": "mes"})
    )
    com_os_meses = meses_da_janela.join(somas_do_mes, on="mes", how="left").with_columns(
        pl.col("entradas").fill_null(0.0), pl.col("saidas").fill_null(0.0), pl.col("com_impostos").fill_null(False)
    )
    sem_movimento = (pl.col("entradas") == 0) & (pl.col("saidas") == 0)
    imposto_conhecido = pl.col("com_impostos") | sem_movimento
    return (
        com_os_meses.with_columns(
            pl.when(imposto_conhecido).then(pl.col("credito").fill_null(0.0)).alias("credito"),
            pl.when(imposto_conhecido).then(pl.col("debito").fill_null(0.0)).alias("debito"),
        )
        .with_columns((pl.col("debito") - pl.col("credito")).round(2).alias("saldo"))
        .with_columns(pl.col("saldo").abs().alias("saldo_sem_sinal"))
        .drop("com_impostos")
    )


def _valor_dos_cfops_por_mes(livros: pl.DataFrame, ate: str, partes: dict[str, tuple[str, list[str]]]) -> pl.DataFrame:
    if len(ate or "") != 7:
        return pl.DataFrame(schema={"mes": pl.Utf8, **{parte: pl.Float64 for parte in partes}})
    meses_da_janela = pl.DataFrame({"mes": janela(ate)})
    linhas_da_janela = livros.filter(pl.col("MES").is_in(meses_da_janela["mes"].to_list()))
    somas_das_partes = [
        pl.col("VALOR").filter((pl.col("LIVRO") == livro) & pl.col("CFOP").is_in(cfops)).sum().alias(parte)
        for parte, (livro, cfops) in partes.items()
    ]
    somas_do_mes = linhas_da_janela.group_by("MES").agg(somas_das_partes).rename({"MES": "mes"})
    return meses_da_janela.join(somas_do_mes, on="mes", how="left").with_columns(
        [pl.col(parte).fill_null(0.0).round(2) for parte in partes]
    )


def bonificacoes_mes_a_mes(livros: pl.DataFrame, ate: str) -> pl.DataFrame:
    listas = configuracao()["bonificacoes"]
    partes = {parte: (livro, listas[parte]) for parte, (livro, _nome) in PARTES_DA_BONIFICACAO.items()}
    return _valor_dos_cfops_por_mes(livros, ate, partes)


def receita_bruta_mes_a_mes(livros: pl.DataFrame, ate: str) -> pl.DataFrame:
    listas = configuracao()["receita_bruta"]
    partes = {parte: (livro, listas[parte]) for parte, (livro, _nome) in PARTES_DA_RECEITA.items()}
    por_mes = _valor_dos_cfops_por_mes(livros, ate, partes)
    return por_mes.with_columns((pl.col("vendas") + pl.col("devolucao_de_compra")).round(2).alias("receita_bruta"))


def _credito_sobre(soma_que_da_credito: pl.Expr, aliquota_em_porcento) -> pl.Expr:
    if aliquota_em_porcento is None:
        return pl.lit(None, dtype=pl.Float64)
    return (soma_que_da_credito * float(aliquota_em_porcento) / 100).round(2)


def receita_e_deducoes_mes_a_mes(
    receita_por_mes: pl.DataFrame, deducoes_do_mes: pl.DataFrame, pis_cofins: pl.DataFrame | None = None
) -> pl.DataFrame:
    aliquotas = configuracao()["aliquotas_dos_outros_creditos"]
    do_livro_item_a_item = (
        pis_cofins.select("mes", "vendas_isentas", "base_de_calculo")
        if pis_cofins is not None
        else pl.DataFrame(schema={"mes": pl.Utf8, "vendas_isentas": pl.Float64, "base_de_calculo": pl.Float64})
    )
    com_as_deducoes = receita_por_mes.join(deducoes_do_mes, on="mes", how="left").join(
        do_livro_item_a_item, on="mes", how="left"
    )
    soma_que_da_credito = pl.col("alugueis_pj") + pl.col("energia_eletrica") + pl.col("combustiveis")
    return com_as_deducoes.with_columns(
        (pl.col("compras") + soma_que_da_credito).round(2).alias("total_deducoes"),
        _credito_sobre(soma_que_da_credito, aliquotas["pis"]).alias("outros_creditos_pis"),
        _credito_sobre(soma_que_da_credito, aliquotas["cofins"]).alias("outros_creditos_cofins"),
    )


ITENS_POR_MES = "livro_itens"
ANOTACOES_DOS_ITENS = f"{ITENS_POR_MES}/_meses"
COLUNAS_LIDAS_DOS_ITENS = [
    "LIVRO",
    "DATA",
    "NUMERO",
    "SERIE",
    "CHAVE",
    "CNPJ_PARTICIPANTE",
    "CFOP",
    "CODRED",
    "QUANTIDADE",
    "QUANTIDADE_AVULSA",
    "VALOR",
    "FRETE",
    "BASE_ICMS",
    "ALIQ_ICMS",
    "ICMS",
    "ICMS_ST",
    "IPI",
    "CST_PIS",
    "BASE_PIS",
    "ALIQ_PIS",
    "PIS",
    "CST_COFINS",
    "BASE_COFINS",
    "ALIQ_COFINS",
    "COFINS",
    "CANCELADA",
    "CNPJ_REV",
    "DESCRICAO",
]
LIVROS_DOS_ITENS = {"": "Entradas e saídas", "E": "Entradas", "S": "Saídas"}
CST_SEM_CONTRIBUICAO = (4, 5, 6, 7, 8, 9)


def revenda_da_empresa(cnpj_da_empresa: str) -> str | None:
    empresa = _empresa_do_config(cnpj_da_empresa)
    revenda = revendas.por_nome(empresa["control"]) if empresa and empresa.get("control") else None
    return revenda.cnpj if revenda else None


def meses_com_itens(cnpj_da_empresa: str) -> set[str]:
    cnpj_da_revenda = revenda_da_empresa(cnpj_da_empresa)
    if not cnpj_da_revenda:
        return set()
    lidos = cache.filtrado(ANOTACOES_DOS_ITENS, pl.col("CNPJ_REV") == cnpj_da_revenda, so=["MES"])
    return set(lidos["MES"].to_list()) if not lidos.is_empty() else set()


def itens_do_mes(cnpj_da_empresa: str, mes: str) -> pl.DataFrame:
    if not cnpj_da_empresa or len(mes or "") != 7:
        return pl.DataFrame(schema={coluna: pl.Utf8 for coluna in COLUNAS_LIDAS_DOS_ITENS})
    arquivo = f"{ITENS_POR_MES}/{mes}"
    no_arquivo = set(cache.colunas(arquivo))
    lidos = cache.filtrado(
        arquivo,
        pl.col("EMITENTE") == cnpj_da_empresa,
        so=[coluna for coluna in COLUNAS_LIDAS_DOS_ITENS if coluna in no_arquivo],
    )
    if lidos.is_empty() and not lidos.columns:
        return pl.DataFrame(schema={coluna: pl.Utf8 for coluna in COLUNAS_LIDAS_DOS_ITENS})
    return lidos.with_columns(
        [pl.lit(None, dtype=pl.Utf8).alias(coluna) for coluna in COLUNAS_LIDAS_DOS_ITENS if coluna not in lidos.columns]
    )


def _nomes_do_cadastro(arquivo: str, revendas_dos_itens: list[str], nome: str) -> pl.DataFrame:
    cadastro = cache.ler(arquivo)
    if not {"CNPJ_REV", "CNPJ_CPF", "RAZAO"} <= set(cadastro.columns):
        return pl.DataFrame(schema={"CNPJ_REV": pl.Utf8, "CNPJ_PARTICIPANTE": pl.Int64, nome: pl.Utf8})
    return (
        cadastro.filter(pl.col("CNPJ_REV").is_in(revendas_dos_itens))
        .select(
            "CNPJ_REV",
            pl.col("CNPJ_CPF").cast(pl.Int64).alias("CNPJ_PARTICIPANTE"),
            pl.col("RAZAO").cast(pl.Utf8).str.strip_chars().alias(nome),
        )
        .filter(pl.col(nome).fill_null("") != "")
        .unique(subset=["CNPJ_REV", "CNPJ_PARTICIPANTE"], keep="first")
    )


def com_os_nomes(itens: pl.DataFrame) -> pl.DataFrame:
    if itens.is_empty():
        return itens.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("PRODUTO"), pl.lit(None, dtype=pl.Utf8).alias("NOME")
        )
    revendas_dos_itens = itens["CNPJ_REV"].unique().to_list()
    produtos = cache.ler("control_produtos")
    produtos = (
        produtos.filter(pl.col("CNPJ_REV").is_in(revendas_dos_itens))
        .select("CNPJ_REV", pl.col("CODRED").cast(pl.Int64), pl.col("PRODUTO").cast(pl.Utf8))
        .unique(subset=["CNPJ_REV", "CODRED"], keep="first")
        if {"CNPJ_REV", "CODRED", "PRODUTO"} <= set(produtos.columns)
        else pl.DataFrame(schema={"CNPJ_REV": pl.Utf8, "CODRED": pl.Int64, "PRODUTO": pl.Utf8})
    )
    com_os_cadastros = (
        itens.with_columns(pl.col("CODRED").cast(pl.Int64), pl.col("CNPJ_PARTICIPANTE").cast(pl.Int64))
        .join(produtos, on=["CNPJ_REV", "CODRED"], how="left")
        .join(
            _nomes_do_cadastro("control_fornecedores", revendas_dos_itens, "NOME_FORNECEDOR"),
            on=["CNPJ_REV", "CNPJ_PARTICIPANTE"],
            how="left",
        )
        .join(
            _nomes_do_cadastro("control_clientes", revendas_dos_itens, "NOME_CLIENTE"),
            on=["CNPJ_REV", "CNPJ_PARTICIPANTE"],
            how="left",
        )
    )
    return com_os_cadastros.with_columns(
        pl.coalesce("PRODUTO", pl.col("DESCRICAO").cast(pl.Utf8)).alias("PRODUTO"),
        pl.when(pl.col("LIVRO") == "E")
        .then(pl.coalesce("NOME_FORNECEDOR", "NOME_CLIENTE"))
        .otherwise(pl.coalesce("NOME_CLIENTE", "NOME_FORNECEDOR"))
        .alias("NOME"),
    ).drop("NOME_FORNECEDOR", "NOME_CLIENTE")


def documento_do_participante(numero) -> str:
    if not numero:
        return "-"
    cnpj, cpf = sped_gerar.documento(numero)
    return formato.cnpj(cnpj or cpf)


def opcoes_cfop_dos_itens(itens: pl.DataFrame, livro: str) -> dict[str, str]:
    if itens.is_empty():
        return {}
    do_livro = itens.filter(pl.col("LIVRO") == livro) if livro else itens
    opcoes = {}
    for codigo in sorted(do_livro["CFOP"].drop_nulls().unique()):
        nome = nome_da_operacao(codigo)
        opcoes[codigo] = f"{codigo} - {nome}" if nome else codigo
    return opcoes


NOMES_DOS_CST = {
    1: "Alíquota básica",
    2: "Alíquota diferenciada",
    3: "Alíquota por unidade",
    4: "Monofásica, revenda a alíquota zero",
    5: "Substituição tributária",
    6: "Alíquota zero",
    7: "Isenta",
    8: "Sem incidência",
    9: "Suspensão",
    49: "Outras saídas",
    **{codigo: "Com direito a crédito" for codigo in range(50, 57)},
    **{codigo: "Crédito presumido" for codigo in range(60, 68)},
    70: "Aquisição sem direito a crédito",
    71: "Aquisição com isenção",
    72: "Aquisição com suspensão",
    73: "Aquisição a alíquota zero",
    74: "Aquisição sem incidência",
    75: "Aquisição por substituição tributária",
    98: "Outras entradas",
    99: "Outras operações",
}
SITUACOES_DOS_ITENS = {"": "Todas", "validas": "Sem as canceladas", "canceladas": "Só as canceladas"}


def _texto_do_cst() -> pl.Expr:
    return pl.col("CST_PIS").cast(pl.Int64, strict=False).cast(pl.Utf8).str.zfill(2)


def _texto_da_aliquota() -> pl.Expr:
    return pl.col("ALIQ_ICMS").cast(pl.Float64).fill_null(0).round(2).cast(pl.Utf8)


def opcoes_produto_dos_itens(itens: pl.DataFrame) -> dict[str, str]:
    if itens.is_empty():
        return {}
    produtos = (
        itens.select(
            pl.col("CODRED").cast(pl.Utf8).alias("codigo"), pl.col("PRODUTO").fill_null("(sem cadastro)").alias("nome")
        )
        .drop_nulls("codigo")
        .unique("codigo")
        .sort("nome", "codigo")
    )
    return {codigo: f"{codigo} - {nome}" for codigo, nome in produtos.iter_rows()}


def opcoes_participante_dos_itens(itens: pl.DataFrame) -> dict[str, str]:
    if itens.is_empty():
        return {}
    participantes = (
        itens.select(
            pl.col("CNPJ_PARTICIPANTE").cast(pl.Utf8).alias("numero"),
            pl.col("NOME").fill_null("(sem cadastro)").alias("nome"),
        )
        .filter(pl.col("numero").fill_null("0") != "0")
        .unique("numero")
        .sort("nome", "numero")
    )
    return {numero: f"{nome} ({documento_do_participante(int(numero))})" for numero, nome in participantes.iter_rows()}


def opcoes_cst_dos_itens(itens: pl.DataFrame) -> dict[str, str]:
    if itens.is_empty():
        return {}
    codigos = sorted(itens.select(_texto_do_cst().alias("cst")).drop_nulls()["cst"].unique().to_list())
    return {codigo: f"{codigo} - {NOMES_DOS_CST.get(int(codigo), 'outro')}" for codigo in codigos}


def opcoes_aliquota_dos_itens(itens: pl.DataFrame) -> dict[str, str]:
    if itens.is_empty():
        return {}
    aliquotas = sorted(itens.select(_texto_da_aliquota().alias("aliquota"))["aliquota"].unique().to_list(), key=float)
    return {aliquota: _percentual(float(aliquota)) for aliquota in aliquotas}


def itens_filtrados(
    itens_com_nomes: pl.DataFrame,
    livro: str = "",
    cfops: list[str] | None = None,
    busca: str = "",
    produtos: list[str] | None = None,
    participantes: list[str] | None = None,
    csts: list[str] | None = None,
    aliquotas: list[str] | None = None,
    situacao: str = "",
    de=None,
    ate=None,
) -> pl.DataFrame:
    filtrados = itens_com_nomes
    if livro:
        filtrados = filtrados.filter(pl.col("LIVRO") == livro)
    if cfops:
        filtrados = filtrados.filter(pl.col("CFOP").is_in(list(cfops)))
    if produtos:
        filtrados = filtrados.filter(pl.col("CODRED").cast(pl.Utf8).is_in(list(produtos)))
    if participantes:
        filtrados = filtrados.filter(pl.col("CNPJ_PARTICIPANTE").cast(pl.Utf8).is_in(list(participantes)))
    if csts:
        filtrados = filtrados.filter(_texto_do_cst().is_in(list(csts)))
    if aliquotas:
        filtrados = filtrados.filter(_texto_da_aliquota().is_in(list(aliquotas)))
    if situacao == "validas":
        filtrados = filtrados.filter(pl.col("CANCELADA") == 0)
    elif situacao == "canceladas":
        filtrados = filtrados.filter(pl.col("CANCELADA") == 1)
    if de:
        filtrados = filtrados.filter(pl.col("DATA") >= de)
    if ate:
        filtrados = filtrados.filter(pl.col("DATA") <= ate)
    procurado = (busca or "").strip().lower()
    if procurado and not filtrados.is_empty():
        digitos = "".join(caractere for caractere in procurado if caractere.isdigit())
        condicao = (
            pl.col("NUMERO").cast(pl.Utf8).str.contains(procurado, literal=True)
            | pl.col("CHAVE").fill_null("").str.contains(procurado, literal=True)
            | pl.col("CODRED").cast(pl.Utf8).str.contains(procurado, literal=True)
            | pl.col("PRODUTO").fill_null("").str.to_lowercase().str.contains(procurado, literal=True)
            | pl.col("NOME").fill_null("").str.to_lowercase().str.contains(procurado, literal=True)
        )
        if digitos:
            condicao = condicao | pl.col("CNPJ_PARTICIPANTE").cast(pl.Utf8).str.contains(
                digitos.lstrip("0") or "0", literal=True
            )
        filtrados = filtrados.filter(condicao)
    return filtrados.sort(["DATA", "NUMERO", "CFOP"], descending=[True, True, False], nulls_last=True)


def resumo_dos_itens(itens: pl.DataFrame) -> dict:
    validos = itens.filter(pl.col("CANCELADA") == 0) if not itens.is_empty() else itens
    if validos.is_empty():
        return {"itens": 0, "notas": 0, "valor": 0.0, "icms": 0.0, "pis": 0.0, "cofins": 0.0}
    return {
        "itens": validos.height,
        "notas": validos.select(pl.struct("LIVRO", "NUMERO", "CNPJ_PARTICIPANTE").n_unique()).item(),
        "valor": round(float(validos["VALOR"].sum() or 0), 2),
        "icms": round(float(validos["ICMS"].sum() or 0), 2),
        "pis": round(float(validos["PIS"].sum() or 0), 2),
        "cofins": round(float(validos["COFINS"].sum() or 0), 2),
    }


def _percentual(valor) -> str:
    return "-" if valor is None else f"{float(valor):.2f}%".replace(".", ",")


def _quantidade(valor) -> str:
    if valor is None:
        return "-"
    return f"{float(valor):,.3f}".rstrip("0").rstrip(".").replace(",", "_").replace(".", ",").replace("_", ".")


def _cst(valor) -> str:
    return "-" if valor is None else f"{int(valor):02d}"


COLUNAS_DOS_ITENS = {
    "Livro": (pl.col("LIVRO").replace_strict({"E": "Entrada", "S": "Saída"}, default="-"),) * 2,
    "Data": (formato.coluna_data("DATA"), pl.col("DATA")),
    "Nota": (pl.col("NUMERO").cast(pl.Utf8), pl.col("NUMERO")),
    "Série": (pl.col("SERIE").fill_null(""),) * 2,
    "Participante": (pl.col("NOME").fill_null("-"),) * 2,
    "CNPJ/CPF": (pl.col("CNPJ_PARTICIPANTE").map_elements(documento_do_participante, return_dtype=pl.Utf8),) * 2,
    "CFOP": (pl.col("CFOP"),) * 2,
    "Produto": (pl.format("{} - {}", pl.col("CODRED"), pl.col("PRODUTO").fill_null("(sem cadastro)")),) * 2,
    "Quantidade": (pl.col("QUANTIDADE").map_elements(_quantidade, return_dtype=pl.Utf8), pl.col("QUANTIDADE")),
    "Avulsas": (
        pl.col("QUANTIDADE_AVULSA").map_elements(_quantidade, return_dtype=pl.Utf8),
        pl.col("QUANTIDADE_AVULSA"),
    ),
    "Valor": (formato.coluna_moeda("VALOR"), pl.col("VALOR")),
    "Base do ICMS": (formato.coluna_moeda("BASE_ICMS"), pl.col("BASE_ICMS")),
    "Alíquota do ICMS": (pl.col("ALIQ_ICMS").map_elements(_percentual, return_dtype=pl.Utf8), pl.col("ALIQ_ICMS")),
    "ICMS": (formato.coluna_moeda("ICMS"), pl.col("ICMS")),
    "ICMS-ST": (formato.coluna_moeda("ICMS_ST"), pl.col("ICMS_ST")),
    "IPI": (formato.coluna_moeda("IPI"), pl.col("IPI")),
    "Frete": (formato.coluna_moeda("FRETE"), pl.col("FRETE")),
    "CST do PIS": (pl.col("CST_PIS").map_elements(_cst, return_dtype=pl.Utf8),) * 2,
    "Base do PIS": (formato.coluna_moeda("BASE_PIS"), pl.col("BASE_PIS")),
    "Alíquota do PIS": (pl.col("ALIQ_PIS").map_elements(_percentual, return_dtype=pl.Utf8), pl.col("ALIQ_PIS")),
    "PIS": (formato.coluna_moeda("PIS"), pl.col("PIS")),
    "CST da COFINS": (pl.col("CST_COFINS").map_elements(_cst, return_dtype=pl.Utf8),) * 2,
    "Base da COFINS": (formato.coluna_moeda("BASE_COFINS"), pl.col("BASE_COFINS")),
    "Alíquota da COFINS": (
        pl.col("ALIQ_COFINS").map_elements(_percentual, return_dtype=pl.Utf8),
        pl.col("ALIQ_COFINS"),
    ),
    "COFINS": (formato.coluna_moeda("COFINS"), pl.col("COFINS")),
    "Chave": (pl.col("CHAVE").fill_null(""),) * 2,
    "Cancelada": (pl.when(pl.col("CANCELADA") == 1).then(pl.lit("Sim")).otherwise(pl.lit("")),) * 2,
}
PADRAO_DOS_ITENS = [
    "Livro",
    "Data",
    "Nota",
    "Participante",
    "CFOP",
    "Produto",
    "Quantidade",
    "Valor",
    "Base do ICMS",
    "ICMS",
    "PIS",
    "COFINS",
]
ORDEM_DOS_ITENS = {
    "Data": (("DATA",), False, True),
    "Nota": (("NUMERO",), True, True),
    "Participante": (("NOME",), False, False),
    "CFOP": (("CFOP",), False, False),
    "Produto": (("PRODUTO",), False, False),
    "Quantidade": (("QUANTIDADE",), True, True),
    **{
        nome: ((coluna,), True, True)
        for nome, coluna in (
            ("Valor", "VALOR"),
            ("Base do ICMS", "BASE_ICMS"),
            ("ICMS", "ICMS"),
            ("ICMS-ST", "ICMS_ST"),
            ("IPI", "IPI"),
            ("Frete", "FRETE"),
            ("Base do PIS", "BASE_PIS"),
            ("PIS", "PIS"),
            ("Base da COFINS", "BASE_COFINS"),
            ("COFINS", "COFINS"),
        )
    },
}


def _colunas_escolhidas(colunas: list[str] | None) -> list[str]:
    escolhidas = [nome for nome in COLUNAS_DOS_ITENS if nome in (colunas if colunas is not None else PADRAO_DOS_ITENS)]
    return escolhidas or PADRAO_DOS_ITENS


def na_tela_itens(pagina: pl.DataFrame, colunas: list[str] | None) -> pl.DataFrame:
    return pagina.select([COLUNAS_DOS_ITENS[nome][0].alias(nome) for nome in _colunas_escolhidas(colunas)])


def tabela_planilha_itens(itens: pl.DataFrame) -> pl.DataFrame:
    if itens.is_empty():
        return pl.DataFrame(schema={nome: pl.Utf8 for nome in COLUNAS_DOS_ITENS})
    return itens.select([COLUNAS_DOS_ITENS[nome][1].alias(nome) for nome in COLUNAS_DOS_ITENS])


def planilha_itens(itens: pl.DataFrame, mes: str, colunas: list[str] | None = None) -> bytes:
    return exportar.excel(tabela_planilha_itens(itens), _nome_da_aba(f"Livro {rotulo_mes(mes)}"), colunas)


def pis_cofins_mes_a_mes(cnpj_da_empresa: str, ate: str) -> pl.DataFrame:
    colunas = ("vendas_isentas", "base_de_calculo", "debito_pis", "credito_pis", "debito_cofins", "credito_cofins")
    if len(ate or "") != 7:
        return pl.DataFrame(schema={"mes": pl.Utf8, **{coluna: pl.Float64 for coluna in colunas}})
    vendas = configuracao()["receita_bruta"]["vendas"]
    lidos = meses_com_itens(cnpj_da_empresa)
    linhas = []
    for mes in janela(ate):
        if mes not in lidos:
            linhas.append({"mes": mes, **{coluna: None for coluna in colunas}})
            continue
        itens = cache.filtrado(
            f"{ITENS_POR_MES}/{mes}",
            (pl.col("EMITENTE") == cnpj_da_empresa) & (pl.col("CANCELADA") == 0),
            so=["LIVRO", "CFOP", "VALOR", "CST_PIS", "BASE_PIS", "PIS", "COFINS"],
        )
        if itens.is_empty():
            linhas.append({"mes": mes, **{coluna: 0.0 for coluna in colunas}})
            continue
        saida, entrada = pl.col("LIVRO") == "S", pl.col("LIVRO") == "E"
        somas = itens.select(
            pl.col("VALOR")
            .filter(saida & pl.col("CFOP").is_in(vendas) & pl.col("CST_PIS").is_in(CST_SEM_CONTRIBUICAO))
            .sum()
            .alias("vendas_isentas"),
            pl.col("BASE_PIS").filter(saida).sum().alias("base_de_calculo"),
            pl.col("PIS").filter(saida).sum().alias("debito_pis"),
            pl.col("PIS").filter(entrada).sum().alias("credito_pis"),
            pl.col("COFINS").filter(saida).sum().alias("debito_cofins"),
            pl.col("COFINS").filter(entrada).sum().alias("credito_cofins"),
        ).row(0, named=True)
        linhas.append({"mes": mes, **{coluna: round(float(somas[coluna] or 0), 2) for coluna in colunas}})
    return pl.DataFrame(linhas, schema={"mes": pl.Utf8, **{coluna: pl.Float64 for coluna in colunas}})


def apuracao_pis_cofins(receita_e_deducoes: pl.DataFrame, pis_cofins: pl.DataFrame) -> pl.DataFrame:
    juntos = receita_e_deducoes.select("mes", "compras", "outros_creditos_pis", "outros_creditos_cofins").join(
        pis_cofins, on="mes", how="left"
    )
    creditos = (
        pl.col("credito_pis")
        + pl.col("credito_cofins")
        + pl.col("outros_creditos_pis")
        + pl.col("outros_creditos_cofins")
    )
    return juntos.with_columns(
        (pl.col("debito_pis") - pl.col("credito_pis") - pl.col("outros_creditos_pis")).round(2).alias("saldo_pis"),
        (pl.col("debito_cofins") - pl.col("credito_cofins") - pl.col("outros_creditos_cofins"))
        .round(2)
        .alias("saldo_cofins"),
        (pl.col("compras") - creditos).round(2).alias("cmv"),
    )


def texto_do_saldo(saldo) -> str:
    if saldo is None:
        return "-"
    return f"credor {formato.moeda(-saldo)}" if saldo < 0 else formato.moeda(saldo)


COLUNAS_DA_APURACAO_PIS_COFINS = {
    "credito_pis": "Crédito de PIS",
    "outros_creditos_pis": "Outros créditos de PIS",
    "debito_pis": "Débito de PIS",
    "saldo_pis": "PIS do mês",
    "credito_cofins": "Crédito de COFINS",
    "outros_creditos_cofins": "Outros créditos de COFINS",
    "debito_cofins": "Débito de COFINS",
    "saldo_cofins": "COFINS do mês",
    "cmv": "CMV",
}
SALDOS_DO_MES = ("saldo_pis", "saldo_cofins")
ORDEM_DA_APURACAO_PIS_COFINS = {
    "Mês": (("mes",), False, True),
    **{nome: ((coluna,), True, True) for coluna, nome in COLUNAS_DA_APURACAO_PIS_COFINS.items()},
}


def na_tela_apuracao_pis_cofins(apuracao_do_mes: pl.DataFrame) -> pl.DataFrame:
    if apuracao_do_mes.is_empty():
        return pl.DataFrame({"Sem livro nos meses.": []})
    linha_do_total = {"mes": "Total"}
    for coluna in COLUNAS_DA_APURACAO_PIS_COFINS:
        valores_da_coluna = apuracao_do_mes[coluna]
        linha_do_total[coluna] = None if valores_da_coluna.null_count() else round(float(valores_da_coluna.sum()), 2)
    linhas_na_tela = []
    for linha in [*apuracao_do_mes.iter_rows(named=True), linha_do_total]:
        linha_na_tela = {"Mês": "Total" if linha["mes"] == "Total" else rotulo_mes(linha["mes"])}
        for coluna, nome in COLUNAS_DA_APURACAO_PIS_COFINS.items():
            linha_na_tela[nome] = (
                texto_do_saldo(linha[coluna]) if coluna in SALDOS_DO_MES else _moeda_ou_traco(linha[coluna])
            )
        linhas_na_tela.append(linha_na_tela)
    return pl.DataFrame(linhas_na_tela)


def tabela_planilha_apuracao_pis_cofins(apuracao_do_mes: pl.DataFrame) -> pl.DataFrame:
    if apuracao_do_mes.is_empty():
        return pl.DataFrame(schema={"Mês": pl.Utf8})
    return apuracao_do_mes.select(
        pl.col("mes").map_elements(rotulo_mes, return_dtype=pl.Utf8).alias("Mês"),
        *[pl.col(coluna).alias(nome) for coluna, nome in COLUNAS_DA_APURACAO_PIS_COFINS.items()],
    )


def planilha_apuracao_pis_cofins(apuracao_do_mes: pl.DataFrame, ate: str, colunas: list[str] | None = None) -> bytes:
    return exportar.excel(
        tabela_planilha_apuracao_pis_cofins(apuracao_do_mes),
        _nome_da_aba(f"PIS e COFINS até {rotulo_mes(ate)}"),
        colunas,
    )


TITULOS_VAZIOS = {
    "data_vencimento": pl.Date,
    "data_pagamento": pl.Date,
    "codigo_despesa": pl.Int64,
    "valor_pago": pl.Float64,
    "fornecedor": pl.Utf8,
    "documento": pl.Utf8,
}


def _empresa_do_config(cnpj_da_empresa: str) -> dict | None:
    return next((empresa for empresa in empresas() if empresa["cnpj"] == cnpj_da_empresa), None)


def origem_das_despesas(cnpj_da_empresa: str) -> tuple[Path, str] | None:
    empresa = _empresa_do_config(cnpj_da_empresa)
    if empresa is None:
        return None
    # No original, as despesas e os títulos pagos vêm do cache do Financeiro. No portfólio cada app
    # é um pacote à parte no navegador: sem essa origem, as visões de despesas ficam vazias.
    return None


def titulos_pagos_da_empresa(cnpj_da_empresa: str) -> pl.DataFrame:
    origem = origem_das_despesas(cnpj_da_empresa)
    if origem is None:
        return pl.DataFrame(schema=TITULOS_VAZIOS)
    pasta, cnpj_da_revenda = origem
    arquivo_dos_pagos = pasta / "titulos_pagos.parquet"
    if not arquivo_dos_pagos.exists():
        return pl.DataFrame(schema=TITULOS_VAZIOS)
    colunas = pl.read_parquet_schema(arquivo_dos_pagos)
    nome_do_fornecedor = next((coluna for coluna in ("razao_social", "FORNECEDOR") if coluna in colunas), None)
    return (
        pl.scan_parquet(arquivo_dos_pagos)
        .filter((pl.col("CNPJ_REV") == cnpj_da_revenda) & pl.col("data_pagamento").is_not_null())
        .select(
            "data_vencimento",
            "data_pagamento",
            "codigo_despesa",
            pl.col("valor_pago").cast(pl.Float64),
            (
                pl.col(nome_do_fornecedor).cast(pl.Utf8).str.strip_chars()
                if nome_do_fornecedor
                else pl.lit(None, dtype=pl.Utf8)
            ).alias("fornecedor"),
            (
                pl.col("num_doc").cast(pl.Utf8).str.strip_chars()
                if "num_doc" in colunas
                else pl.lit(None, dtype=pl.Utf8)
            ).alias("documento"),
        )
        .collect()
    )


def nomes_das_despesas(cnpj_da_empresa: str) -> pl.DataFrame:
    vazio = pl.DataFrame(schema={"codigo_despesa": pl.Int64, "descricao_despesa": pl.Utf8})
    origem = origem_das_despesas(cnpj_da_empresa)
    if origem is None or not (origem[0] / "cod_despesa.parquet").exists():
        return vazio
    pasta, cnpj_da_revenda = origem
    return (
        pl.read_parquet(pasta / "cod_despesa.parquet", columns=["CNPJ_REV", "codigo_despesa", "descricao_despesa"])
        .filter(pl.col("CNPJ_REV") == cnpj_da_revenda)
        .select("codigo_despesa", "descricao_despesa")
        .unique(subset="codigo_despesa", keep="first")
    )


def _nome_da_despesa() -> pl.Expr:
    return (
        pl.when(pl.col("codigo_despesa").is_null())
        .then(pl.lit("Sem despesa no título"))
        .otherwise(
            pl.format(
                "{} - {}",
                pl.col("codigo_despesa"),
                pl.col("descricao_despesa").fill_null("(sem nome no cadastro)").str.strip_chars(),
            )
        )
    )


def opcoes_despesa(titulos_pagos: pl.DataFrame, cnpj_da_empresa: str) -> dict[str, str]:
    codigos = titulos_pagos.select(pl.col("codigo_despesa")).drop_nulls().unique()
    if codigos.is_empty():
        return {}
    com_o_nome = codigos.join(nomes_das_despesas(cnpj_da_empresa), on="codigo_despesa", how="left").sort(
        "codigo_despesa"
    )
    return dict(
        zip(
            com_o_nome["codigo_despesa"].cast(pl.Utf8).to_list(),
            com_o_nome.select(_nome_da_despesa().alias("nome"))["nome"].to_list(),
        )
    )


def das_despesas_escolhidas(titulos_pagos: pl.DataFrame, despesas: list[str] | None) -> pl.DataFrame:
    if not despesas:
        return titulos_pagos
    return titulos_pagos.filter(pl.col("codigo_despesa").cast(pl.Utf8).is_in(list(despesas)))


def opcoes_fornecedor(titulos_pagos: pl.DataFrame) -> dict[str, str]:
    nomes = titulos_pagos.select(pl.col("fornecedor").str.strip_chars()).drop_nulls()["fornecedor"].unique().sort()
    return {nome: nome for nome in nomes.to_list() if nome}


def dos_fornecedores_escolhidos(titulos_pagos: pl.DataFrame, fornecedores: list[str] | None) -> pl.DataFrame:
    if not fornecedores:
        return titulos_pagos
    return titulos_pagos.filter(pl.col("fornecedor").str.strip_chars().is_in(list(fornecedores)))


def titulos_do_periodo(titulos_pagos: pl.DataFrame, cnpj_da_empresa: str, de, ate) -> pl.DataFrame:
    vazia = pl.DataFrame(
        schema={
            "data_pagamento": pl.Date,
            "data_vencimento": pl.Date,
            "despesa": pl.Utf8,
            "fornecedor": pl.Utf8,
            "documento": pl.Utf8,
            "valor": pl.Float64,
        }
    )
    if titulos_pagos.is_empty() or not de or not ate:
        return vazia
    do_periodo = titulos_pagos.filter(pl.col("data_pagamento").is_between(de, ate))
    if do_periodo.is_empty():
        return vazia
    return (
        do_periodo.join(nomes_das_despesas(cnpj_da_empresa), on="codigo_despesa", how="left")
        .select(
            "data_pagamento",
            "data_vencimento",
            _nome_da_despesa().alias("despesa"),
            "fornecedor",
            "documento",
            pl.col("valor_pago").round(2).alias("valor"),
        )
        .sort(["data_pagamento", "valor"], descending=[True, True])
    )


COLUNAS_DOS_TITULOS = {
    "Pagamento": (formato.coluna_data("data_pagamento"), pl.col("data_pagamento")),
    "Vencimento": (formato.coluna_data("data_vencimento"), pl.col("data_vencimento")),
    "Despesa": (pl.col("despesa"),) * 2,
    "Fornecedor": (pl.col("fornecedor").fill_null("-"),) * 2,
    "Documento": (pl.col("documento").fill_null("-"),) * 2,
    "Valor": (formato.coluna_moeda("valor"), pl.col("valor")),
}
ORDEM_DOS_TITULOS = {
    "Pagamento": (("data_pagamento",), False, True),
    "Vencimento": (("data_vencimento",), False, True),
    "Despesa": (("despesa",), False, False),
    "Fornecedor": (("fornecedor",), False, False),
    "Valor": (("valor",), True, True),
}


def na_tela_titulos(pagina: pl.DataFrame) -> pl.DataFrame:
    return pagina.select([na_tela.alias(nome) for nome, (na_tela, _na_planilha) in COLUNAS_DOS_TITULOS.items()])


def tabela_planilha_titulos(titulos: pl.DataFrame) -> pl.DataFrame:
    if titulos.is_empty():
        return pl.DataFrame(schema={nome: pl.Utf8 for nome in COLUNAS_DOS_TITULOS})
    return titulos.select([na_planilha.alias(nome) for nome, (_na_tela, na_planilha) in COLUNAS_DOS_TITULOS.items()])


def planilha_titulos(titulos: pl.DataFrame, de, ate, colunas: list[str] | None = None) -> bytes:
    return exportar.excel(
        tabela_planilha_titulos(titulos), _nome_da_aba(f"Pagos {de:%d-%m-%Y} a {ate:%d-%m-%Y}"), colunas
    )


def primeiro_e_ultimo_dia(mes: str) -> tuple[date | None, date | None]:
    if len(mes or "") != 7:
        return None, None
    ano, numero = int(mes[:4]), int(mes[5:7])
    seguinte = date(ano + numero // 12, numero % 12 + 1, 1)
    return date(ano, numero, 1), seguinte - timedelta(days=1)


def meses_guardados(titulos_pagos: pl.DataFrame, ate: str) -> list[str]:
    if titulos_pagos.is_empty() or len(ate or "") != 7:
        return []
    primeiro_vencimento, ultimo_pagamento = (
        titulos_pagos["data_vencimento"].min(),
        titulos_pagos["data_pagamento"].max(),
    )
    if primeiro_vencimento is None or ultimo_pagamento is None:
        return []
    return [mes for mes in janela(ate) if f"{primeiro_vencimento:%Y-%m}" <= mes <= f"{ultimo_pagamento:%Y-%m}"]


def despesas_pagas(
    titulos_pagos: pl.DataFrame,
    cnpj_da_empresa: str,
    ate: str,
    despesas: list[str] | None = None,
    fornecedores: list[str] | None = None,
) -> pl.DataFrame:
    vazia = pl.DataFrame(schema={"mes": pl.Utf8, "despesa": pl.Utf8, "valor": pl.Float64})
    meses_da_janela = meses_guardados(titulos_pagos, ate)
    origem = origem_das_despesas(cnpj_da_empresa)
    if not meses_da_janela or origem is None:
        return vazia
    pagos = (
        dos_fornecedores_escolhidos(das_despesas_escolhidas(titulos_pagos, despesas), fornecedores)
        .select(
            pl.col("data_pagamento").dt.strftime("%Y-%m").alias("mes"),
            pl.col("codigo_despesa"),
            pl.col("valor_pago").alias("valor"),
        )
        .filter(pl.col("mes").is_in(meses_da_janela))
        .group_by("mes", "codigo_despesa")
        .agg(pl.col("valor").sum())
    )
    if pagos.is_empty():
        return vazia
    com_o_nome = pagos.join(nomes_das_despesas(cnpj_da_empresa), on="codigo_despesa", how="left")
    return com_o_nome.select("mes", _nome_da_despesa().alias("despesa"), pl.col("valor").round(2))


def deducoes_pagas(titulos_pagos: pl.DataFrame, cnpj_da_empresa: str, ate: str) -> pl.DataFrame:
    if len(ate or "") != 7:
        return pl.DataFrame(schema={"mes": pl.Utf8, **{parte: pl.Float64 for parte in PARTES_DA_DEDUCAO}})
    empresa = _empresa_do_config(cnpj_da_empresa)
    meses_com_titulos = meses_guardados(titulos_pagos, ate) if empresa and empresa.get("control") else []
    codigos_de_cada_parte = configuracao()["deducoes_por_despesa"]
    partes_com_codigos = [parte for parte in PARTES_DA_DEDUCAO if codigos_de_cada_parte[parte]]
    pagos_no_mes = (
        titulos_pagos.with_columns(pl.col("data_pagamento").dt.strftime("%Y-%m").alias("mes"))
        .filter(pl.col("mes").is_in(meses_com_titulos))
        .group_by("mes")
        .agg(
            *[
                pl.col("valor_pago")
                .filter(pl.col("codigo_despesa").is_in(codigos_de_cada_parte[parte]))
                .sum()
                .alias(parte)
                for parte in partes_com_codigos
            ]
        )
    )
    com_os_meses = pl.DataFrame({"mes": janela(ate)}).join(pagos_no_mes, on="mes", how="left")
    mes_com_titulos = pl.col("mes").is_in(meses_com_titulos)
    return com_os_meses.select(
        "mes",
        *[
            (
                pl.when(mes_com_titulos).then(pl.col(parte).fill_null(0.0).round(2))
                if parte in partes_com_codigos
                else pl.lit(None, dtype=pl.Float64)
            ).alias(parte)
            for parte in PARTES_DA_DEDUCAO
        ],
    )


def antecipado_pago(titulos_pagos: pl.DataFrame, cnpj_da_empresa: str, ate: str) -> pl.DataFrame:
    vazio = pl.DataFrame(schema={"mes": pl.Utf8, "antecipado": pl.Float64})
    codigos = configuracao()["antecipado_por_despesa"]
    if len(ate or "") != 7:
        return vazio
    empresa = _empresa_do_config(cnpj_da_empresa)
    meses_com_titulos = meses_guardados(titulos_pagos, ate) if codigos and empresa and empresa.get("control") else []
    pagos_no_mes = (
        titulos_pagos.filter(pl.col("codigo_despesa").is_in(codigos))
        .with_columns(pl.col("data_pagamento").dt.strftime("%Y-%m").alias("mes"))
        .group_by("mes")
        .agg(pl.col("valor_pago").sum().alias("antecipado"))
    )
    return (
        pl.DataFrame({"mes": janela(ate)})
        .join(pagos_no_mes, on="mes", how="left")
        .select(
            "mes",
            pl.when(pl.col("mes").is_in(meses_com_titulos))
            .then(pl.col("antecipado").fill_null(0.0).round(2))
            .alias("antecipado"),
        )
    )


def com_o_antecipado(meses_lado_a_lado: pl.DataFrame, antecipado: pl.DataFrame) -> pl.DataFrame:
    if meses_lado_a_lado.is_empty():
        return meses_lado_a_lado.with_columns(pl.lit(None, dtype=pl.Float64).alias("antecipado"))
    return meses_lado_a_lado.join(antecipado, on="mes", how="left")


def despesas_por_mes(despesas: pl.DataFrame) -> pl.DataFrame:
    if despesas.is_empty():
        return pl.DataFrame(schema={"despesa": pl.Utf8})
    meses = sorted(despesas["mes"].unique().to_list())
    por_mes = despesas.pivot(on="mes", index="despesa", values="valor", aggregate_function="sum")
    por_mes = por_mes.select("despesa", *[pl.col(mes).fill_null(0.0) for mes in meses])
    return por_mes.with_columns(pl.sum_horizontal(meses).round(2).alias("total")).sort(
        ["total", "despesa"], descending=[True, False]
    )


def na_tela_despesas(despesas_na_tabela: pl.DataFrame) -> pl.DataFrame:
    if despesas_na_tabela.is_empty():
        return pl.DataFrame({"Sem despesa paga nos meses que o Financeiro guarda.": []})
    colunas_de_valor = [coluna for coluna in despesas_na_tabela.columns if coluna != "despesa"]
    linha_do_total = despesas_na_tabela.select(
        pl.lit("Total").alias("despesa"), *[pl.col(coluna).sum() for coluna in colunas_de_valor]
    )
    com_o_total = pl.concat([despesas_na_tabela, linha_do_total], how="vertical_relaxed")
    nomes_na_tela = {coluna: "Total" if coluna == "total" else rotulo_mes(coluna) for coluna in colunas_de_valor}
    return com_o_total.select(
        pl.col("despesa").alias("Despesa"),
        *[
            pl.col(coluna).map_elements(formato.moeda, return_dtype=pl.Utf8).alias(nomes_na_tela[coluna])
            for coluna in colunas_de_valor
        ],
    )


def tabela_planilha_despesas(despesas_na_tabela: pl.DataFrame) -> pl.DataFrame:
    if despesas_na_tabela.is_empty():
        return pl.DataFrame(schema={"Despesa": pl.Utf8})
    colunas_de_valor = [coluna for coluna in despesas_na_tabela.columns if coluna != "despesa"]
    return despesas_na_tabela.select(
        pl.col("despesa").alias("Despesa"),
        *[
            pl.col(coluna).round(2).alias("Total" if coluna == "total" else rotulo_mes(coluna))
            for coluna in colunas_de_valor
        ],
    )


def planilha_despesas(despesas_na_tabela: pl.DataFrame, ate: str, colunas: list[str] | None = None) -> bytes:
    return exportar.excel(
        tabela_planilha_despesas(despesas_na_tabela), _nome_da_aba(f"Despesas até {rotulo_mes(ate)}"), colunas
    )


def _moeda_ou_traco(valor) -> str:
    return formato.moeda(valor) if valor is not None else "-"


def com_o_nome_da_operacao(livro_por_cfop: pl.DataFrame) -> pl.DataFrame:
    return livro_por_cfop.with_columns(
        pl.col("CFOP").map_elements(nome_da_operacao, return_dtype=pl.Utf8).alias("NOME")
    )


def na_tela_cfop(livro_por_cfop: pl.DataFrame, com_impostos: bool) -> pl.DataFrame:
    if livro_por_cfop.is_empty():
        return pl.DataFrame({"Nada neste livro no mês.": []})
    com_os_nomes = livro_por_cfop if "NOME" in livro_por_cfop.columns else com_o_nome_da_operacao(livro_por_cfop)
    linha_do_total = com_os_nomes.select(
        pl.lit("Total").alias("CFOP"),
        pl.lit("").alias("NOME"),
        pl.col("VALOR").sum(),
        pl.col("BASE_ICMS").sum(),
        pl.col("ICMS").sum(),
    )
    com_o_total = pl.concat(
        [com_os_nomes.select("CFOP", "NOME", "VALOR", "BASE_ICMS", "ICMS"), linha_do_total], how="vertical_relaxed"
    )
    linhas_na_tela = []
    for codigo_do_cfop, nome_da_operacao_do_cfop, valor_contabil, base_de_calculo, icms in com_o_total.iter_rows():
        linhas_na_tela.append(
            {
                "CFOP": codigo_do_cfop,
                "Operação": nome_da_operacao_do_cfop,
                "Valor contábil": formato.moeda(valor_contabil),
                "Base de cálculo": _moeda_ou_traco(base_de_calculo) if com_impostos else "-",
                "ICMS": _moeda_ou_traco(icms) if com_impostos else "-",
            }
        )
    return pl.DataFrame(linhas_na_tela)


def na_tela_operacao(livro_por_operacao: pl.DataFrame, com_impostos: bool) -> pl.DataFrame:
    if livro_por_operacao.is_empty():
        return pl.DataFrame({"Nada neste livro no mês.": []})
    linha_do_total = livro_por_operacao.select(
        pl.lit("Total").alias("OPERACAO"),
        pl.lit("").alias("CFOPS"),
        pl.col("VALOR").sum(),
        pl.col("BASE_ICMS").sum(),
        pl.col("ICMS").sum(),
    )
    com_o_total = pl.concat(
        [livro_por_operacao.select("OPERACAO", "CFOPS", "VALOR", "BASE_ICMS", "ICMS"), linha_do_total],
        how="vertical_relaxed",
    )
    linhas_na_tela = []
    for operacao, cfops_do_grupo, valor_contabil, base_de_calculo, icms in com_o_total.iter_rows():
        linhas_na_tela.append(
            {
                "Operação": operacao,
                "CFOPs": cfops_do_grupo,
                "Valor contábil": formato.moeda(valor_contabil),
                "Base de cálculo": _moeda_ou_traco(base_de_calculo) if com_impostos else "-",
                "ICMS": _moeda_ou_traco(icms) if com_impostos else "-",
            }
        )
    return pl.DataFrame(linhas_na_tela)


def situacao_do_saldo(saldo) -> str:
    if saldo is None:
        return "-"
    if saldo == 0:
        return "zerado"
    return "a recolher" if saldo > 0 else "credor"


def na_tela_meses(meses_lado_a_lado: pl.DataFrame, cnpj: str = "") -> pl.DataFrame:
    if meses_lado_a_lado.is_empty():
        return pl.DataFrame({"Sem livro nos meses.": []})
    if "antecipado" not in meses_lado_a_lado.columns:
        meses_lado_a_lado = meses_lado_a_lado.with_columns(pl.lit(None, dtype=pl.Float64).alias("antecipado"))
    linhas_na_tela = []
    for mes, entradas, saidas, credito, antecipado, debito, saldo in meses_lado_a_lado.select(
        "mes", "entradas", "saidas", "credito", "antecipado", "debito", "saldo"
    ).iter_rows():
        linhas_na_tela.append(
            {
                "Mês": rotulo_mes(mes),
                "Entradas": formato.moeda(entradas),
                "Saídas": formato.moeda(saidas),
                "Crédito de ICMS": _moeda_ou_traco(credito),
                "Antecipado pago": _moeda_ou_traco(antecipado),
                "Débito de ICMS": _moeda_ou_traco(debito),
                "Saldo": _moeda_ou_traco(abs(saldo) if saldo is not None else None),
                "Situação": situacao_do_saldo(saldo),
                "No SPED gerado": texto_do_sped(apuracao_do_sped(cnpj, mes)),
            }
        )
    return pl.DataFrame(linhas_na_tela)


COLUNAS_DA_RECEITA = {
    "vendas": "Vendas",
    "devolucao_de_compra": "Devolução de compra",
    "receita_bruta": "Receita bruta",
    "devolucao_de_venda": "Devolução de venda",
    "vendas_isentas": "Vendas isentas",
    "base_de_calculo": "Base de cálculo",
    "compras": "Compras",
    **PARTES_DA_DEDUCAO,
    "combustiveis": "Combustíveis e lubrificantes",
    "total_deducoes": "Total de deduções",
    "outros_creditos_pis": "Outros créditos de PIS",
    "outros_creditos_cofins": "Outros créditos de COFINS",
}

_VALORES_DO_LIVRO = {
    "Valor contábil": (("VALOR",), True, True),
    "Base de cálculo": (("BASE_ICMS",), True, True),
    "ICMS": (("ICMS",), True, True),
}
ORDEM_DO_LIVRO = {
    "CFOP": (("CFOP",), False, False),
    "Operação": (("NOME", "OPERACAO"), False, False),
    "CFOPs": (("CFOPS",), False, False),
    **_VALORES_DO_LIVRO,
}
ORDEM_DOS_MESES = {
    "Mês": (("mes",), False, True),
    "Entradas": (("entradas",), True, True),
    "Saídas": (("saidas",), True, True),
    "Crédito de ICMS": (("credito",), True, True),
    "Antecipado pago": (("antecipado",), True, True),
    "Débito de ICMS": (("debito",), True, True),
    "Saldo": (("saldo_sem_sinal",), True, True),
}
ORDEM_DA_RECEITA = {
    "Mês": (("mes",), False, True),
    **{nome: ((coluna,), True, True) for coluna, nome in COLUNAS_DA_RECEITA.items()},
}
ORDEM_DAS_DESPESAS = {
    "Despesa": (("despesa",), False, False),
    "Total": (("total",), True, True),
    **{rotulo_mes(mes): ((mes,), True, True) for mes in janela("2039-12", 240)},
}


def _com_o_total(receita_e_deducoes: pl.DataFrame) -> pl.DataFrame:
    linha_do_total = {"mes": "Total"}
    for coluna in COLUNAS_DA_RECEITA:
        valores_da_coluna = receita_e_deducoes[coluna]
        linha_do_total[coluna] = None if valores_da_coluna.null_count() else round(float(valores_da_coluna.sum()), 2)
    total = pl.DataFrame(
        [linha_do_total], schema={"mes": pl.Utf8, **{coluna: pl.Float64 for coluna in COLUNAS_DA_RECEITA}}
    )
    return pl.concat([receita_e_deducoes.select("mes", *COLUNAS_DA_RECEITA), total], how="vertical_relaxed")


def na_tela_receita(receita_e_deducoes: pl.DataFrame) -> pl.DataFrame:
    if receita_e_deducoes.is_empty():
        return pl.DataFrame({"Sem livro nos meses.": []})
    linhas_na_tela = []
    for linha in _com_o_total(receita_e_deducoes).iter_rows(named=True):
        linha_na_tela = {"Mês": "Total" if linha["mes"] == "Total" else rotulo_mes(linha["mes"])}
        for coluna, nome in COLUNAS_DA_RECEITA.items():
            linha_na_tela[nome] = _moeda_ou_traco(linha[coluna])
        linhas_na_tela.append(linha_na_tela)
    return pl.DataFrame(linhas_na_tela)


def _nome_na_planilha(codigo_do_cfop: str) -> str:
    return "" if codigo_do_cfop == "Total" else nome_da_operacao(codigo_do_cfop)


def _grupo_na_planilha(codigo_do_cfop: str) -> str:
    return "" if codigo_do_cfop == "Total" else grupo_da_operacao(codigo_do_cfop)


def tabela_planilha(livros: pl.DataFrame, mes: str) -> pl.DataFrame:
    livros_com_total = []
    for livro, nome_do_livro in LIVROS.items():
        livro_por_cfop = por_cfop(livros, mes, livro)
        if livro_por_cfop.is_empty():
            continue
        linha_do_total = livro_por_cfop.select(
            pl.lit("Total").alias("CFOP"), pl.col("VALOR").sum(), *[pl.col(imposto).sum() for imposto in IMPOSTOS]
        )
        livros_com_total.append(
            pl.concat([livro_por_cfop, linha_do_total], how="vertical_relaxed").with_columns(
                pl.lit(nome_do_livro).alias("Livro")
            )
        )
    if not livros_com_total:
        return pl.DataFrame(schema={"Livro": pl.Utf8, "CFOP": pl.Utf8})
    return pl.concat(livros_com_total, how="vertical_relaxed").select(
        "Livro",
        "CFOP",
        pl.col("CFOP").map_elements(_nome_na_planilha, return_dtype=pl.Utf8).alias("Operação"),
        pl.col("CFOP").map_elements(_grupo_na_planilha, return_dtype=pl.Utf8).alias("Grupo"),
        *[pl.col(coluna).round(2).alias(nome) for coluna, nome in NOMES_NA_PLANILHA.items()],
    )


def _nome_da_aba(texto: str) -> str:
    return re.sub(r"[\[\]:*?/\\]", "-", texto)[:31]


def planilha(livros: pl.DataFrame, mes: str, colunas: list[str] | None = None) -> bytes:
    return exportar.excel(tabela_planilha(livros, mes), _nome_da_aba(f"Apuração {rotulo_mes(mes)}"), colunas)


def tabela_planilha_receita(receita_e_deducoes: pl.DataFrame) -> pl.DataFrame:
    if receita_e_deducoes.is_empty():
        return pl.DataFrame(schema={"Mês": pl.Utf8})
    return receita_e_deducoes.select(
        pl.col("mes").map_elements(rotulo_mes, return_dtype=pl.Utf8).alias("Mês"),
        *[pl.col(coluna).alias(nome) for coluna, nome in COLUNAS_DA_RECEITA.items()],
    )


def planilha_receita(receita_e_deducoes: pl.DataFrame, ate: str, colunas: list[str] | None = None) -> bytes:
    return exportar.excel(
        tabela_planilha_receita(receita_e_deducoes), _nome_da_aba(f"Receita e deduções até {rotulo_mes(ate)}"), colunas
    )
