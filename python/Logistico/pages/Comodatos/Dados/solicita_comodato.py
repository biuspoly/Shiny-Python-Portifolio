from datetime import date, timedelta

import polars as pl
from dateutil.relativedelta import relativedelta

from . import banco_memoria as bm

bm_tabela = "comod_solicitado_bruto"

DIAS_PRAZO_ANUAL = 365
MESES_PRAZO_MENSAL = 1
PRAZO_ANUAL = "1 ano"

_COLUNAS = (
    "REVENDA",
    "CLIENTE",
    "CNPJ",
    "USUARIO",
    "PRODUTO",
    "CODCOMP",
    "UNIDADE",
    "QTD",
    "PRECO",
    "TIPO",
    "TAB_CEV",
    "VEN",
    "ENDERECO",
    "CONTATO",
    "PTO_REF",
    "DIA_VISIT",
    "SEQ",
    "CEP",
    "FONE",
    "DATA",
    "VENC",
    "PRAZO",
)
_SQL_INSERT = "INSERT INTO tb_comod_solicitado ({}) VALUES ({})".format(
    ", ".join(_COLUNAS), ", ".join(f":{coluna}" for coluna in _COLUNAS)
)

_SQL_SOMA = (
    "UPDATE tb_comod_solicitado SET QTD = QTD + :qtd WHERE "
    "REVENDA = :revenda AND CLIENTE = :cliente AND CODCOMP = :codcomp AND "
    "PRODUTO = :produto AND PRAZO = :prazo AND TIPO = :tipo AND DATA = :data AND "
    "PRE_PED IS NULL ORDER BY VENC DESC LIMIT 1"
)

CHAVES_SOLICITACAO = ("REVENDA", "CLIENTE", "DATA", "PRAZO", "TIPO")

_SQL_DELETE = (
    "DELETE FROM tb_comod_solicitado WHERE "
    "REVENDA = :revenda AND CLIENTE = :cliente AND PRODUTO = :produto AND "
    "DATA = :data AND TIPO = :tipo AND PRAZO = :prazo AND PRE_PED IS NULL"
)
_SQL_DELETE_SOLICITACAO = (
    "DELETE FROM tb_comod_solicitado WHERE "
    + " AND ".join(f"{coluna} = :{coluna.lower()}" for coluna in CHAVES_SOLICITACAO)
    + " AND PRE_PED IS NULL"
)


def _inteiro(valor) -> int:
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return 0


def _decimal(valor) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def montar_linha(
    cliente: str,
    usuario: str,
    item: str,
    cod_prod: str,
    unidade,
    qtd,
    preco,
    tab_cev: str,
    revenda: str,
    endereco: str,
    contato: str,
    pto_ref: str,
    dia_visit: str,
    seq: str,
    cep: str,
    fone: str,
    cnpj: str,
    ven: str,
    prazo: str,
    tipo: str,
) -> dict:
    hoje = date.today()
    venc = (
        hoje + timedelta(days=DIAS_PRAZO_ANUAL)
        if prazo == PRAZO_ANUAL
        else hoje + relativedelta(months=MESES_PRAZO_MENSAL)
    )
    return {
        "REVENDA": revenda,
        "CLIENTE": cliente,
        "CNPJ": cnpj,
        "USUARIO": usuario,
        "PRODUTO": item,
        "CODCOMP": cod_prod,
        "UNIDADE": _inteiro(unidade),
        "QTD": _inteiro(qtd),
        "PRECO": _decimal(preco),
        "TIPO": tipo,
        "TAB_CEV": tab_cev,
        "VEN": ven,
        "ENDERECO": endereco,
        "CONTATO": contato,
        "PTO_REF": pto_ref,
        "DIA_VISIT": dia_visit,
        "SEQ": seq,
        "CEP": cep,
        "FONE": fone,
        "DATA": hoje.strftime("%Y%m%d"),
        "VENC": venc.strftime("%Y%m%d"),
        "PRAZO": prazo,
    }


def solicita_comodato(linhas: list[dict], somar: list[dict] | None = None, executar: bool = False) -> tuple[int, int]:
    """Portfólio: as mesmas regras do INSERT e do UPDATE de soma, gravadas no .parquet (banco_memoria)."""
    somar = somar or []
    if not linhas and not somar:
        return 0, 0
    base = bm.ler(bm_tabela)
    if linhas:
        novas = pl.DataFrame([{**{c: linha.get(c) for c in _COLUNAS}, "PRE_PED": None} for linha in linhas])
        base = pl.concat([base, novas], how="diagonal_relaxed") if base.height else novas
    somadas = 0
    for pedido in somar:
        alvo = bm.condicao(
            {
                "REVENDA": pedido["revenda"],
                "CLIENTE": pedido["cliente"],
                "CODCOMP": pedido["codcomp"],
                "PRODUTO": pedido["produto"],
                "PRAZO": pedido["prazo"],
                "TIPO": pedido["tipo"],
                "DATA": pedido["data"],
                "PRE_PED": None,
            }
        )
        indexada = base.with_row_index("_i")
        if indexada.filter(alvo).height:
            primeira = indexada.filter(alvo).sort("VENC", descending=True)["_i"][0]
            base = indexada.with_columns(
                pl.when(pl.col("_i") == primeira)
                .then(pl.col("QTD") + int(pedido["qtd"]))
                .otherwise(pl.col("QTD"))
                .alias("QTD")
            ).drop("_i")
            somadas += 1
    bm.gravar(bm_tabela, base)
    return len(linhas), somadas


def retira_comodato(
    revenda: str, cliente: str, produto: str, emissao: str, tipo: str, prazo: str, executar: bool = False
) -> int:
    base = bm.ler(bm_tabela)
    alvo = bm.condicao(
        {
            "REVENDA": revenda,
            "CLIENTE": cliente,
            "PRODUTO": produto,
            "DATA": emissao,
            "TIPO": tipo,
            "PRAZO": prazo,
            "PRE_PED": None,
        }
    )
    bm.gravar(bm_tabela, base.filter(~alvo))
    return base.filter(alvo).height


def retira_solicitacao(revenda: str, cliente: str, emissao: str, prazo: str, tipo: str, executar: bool = False) -> int:
    base = bm.ler(bm_tabela)
    alvo = bm.condicao(
        {"REVENDA": revenda, "CLIENTE": cliente, "DATA": emissao, "PRAZO": prazo, "TIPO": tipo, "PRE_PED": None}
    )
    bm.gravar(bm_tabela, base.filter(~alvo))
    return base.filter(alvo).height
