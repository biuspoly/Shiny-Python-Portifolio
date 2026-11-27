"""Carteira de clientes: uma linha por cliente, lida do cache tb_carteira (dados fictícios).

O resto do Comercial conta por produto; aqui a pergunta é a oposta: o que a revenda tem com cada cliente,
somando tudo. Faturamento do mês e de 12 meses lado a lado (cada um com a sua devolução), o markup de
12 meses e a última compra.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

PASTA_PARQUET = Path(__file__).parents[3] / "data" / "bd_comercial"
ARQUIVO = PASTA_PARQUET / "tb_carteira.parquet"
DIAS_PARADO = 90

SITUACOES = {
    "todos": "Todos",
    "ativos": "Só ativos",
    "compraram_mes": "Compraram no mês",
    "ativos_sem_mes": "Ativos sem comprar no mês",
    "parados": f"Ativos parados há {DIAS_PARADO}+ dias",
}

_cache: dict[float, pl.DataFrame] = {}


def tabela() -> pl.DataFrame:
    versao = ARQUIVO.stat().st_mtime
    if versao not in _cache:
        _cache.clear()
        df = pl.from_arrow(pq.read_table(ARQUIVO))
        _cache[versao] = df.with_columns(
            (pl.col("CODCLI").cast(pl.String) + " - " + pl.col("CLIENTE")).alias("CODIGO_NOME")
        )
    return _cache[versao]


def opcoes(coluna: str) -> list[str]:
    return sorted(tabela()[coluna].drop_nulls().unique().to_list())


def _limite_parado() -> date:
    return date.today() - timedelta(days=DIAS_PARADO)


def filtrar(vendedores, canais, cidades, situacao: str, busca: str) -> pl.DataFrame:
    df = tabela()
    for coluna, valores in (("VEN", vendedores), ("CANAL", canais), ("CIDADE", cidades)):
        if valores:
            df = df.filter(pl.col(coluna).is_in(list(valores)))
    if situacao == "ativos":
        df = df.filter(pl.col("ATIVO"))
    elif situacao == "compraram_mes":
        df = df.filter(pl.col("FAT_MES") > 0)
    elif situacao == "ativos_sem_mes":
        df = df.filter(pl.col("ATIVO") & (pl.col("FAT_MES") == 0))
    elif situacao == "parados":
        df = df.filter(pl.col("ATIVO") & (pl.col("ULTIMA_COMPRA") < _limite_parado()))
    busca = (busca or "").strip().upper()
    if busca:
        df = df.filter(pl.col("CODIGO_NOME").str.to_uppercase().str.contains(busca, literal=True))
    return df


def resumo(df: pl.DataFrame) -> dict:
    soma = df.select(pl.col("FAT_MES", "DEV_MES", "FAT_12M", "DEV_12M", "CMV_12M").sum()).row(0, named=True)
    ativos = int(df["ATIVO"].sum())
    parados = df.filter(pl.col("ATIVO") & (pl.col("ULTIMA_COMPRA") < _limite_parado())).height
    venda_bruta_mes = soma["FAT_MES"] + soma["DEV_MES"]
    return {
        **soma,
        "CLIENTES": df.height,
        "ATIVOS": ativos,
        "COMPRARAM_MES": df.filter(pl.col("FAT_MES") > 0).height,
        "COMPRARAM_12M": df.filter(pl.col("FAT_12M") > 0).height,
        "PCT_DEV_MES": soma["DEV_MES"] / venda_bruta_mes if venda_bruta_mes else None,
        "PCT_MKP_12M": soma["FAT_12M"] / soma["CMV_12M"] - 1 if soma["CMV_12M"] else None,
        "PARADOS": parados,
        "PCT_PARADOS": parados / ativos if ativos else None,
        "LIMITE_PARADO": _limite_parado(),
    }
