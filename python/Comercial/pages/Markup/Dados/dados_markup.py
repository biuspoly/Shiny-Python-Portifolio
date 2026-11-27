"""Markup por produto: leitura do cache tb_markup e as contas da tela.

A tabela guarda só grandezas que se somam (quantidade, faturamento, CMV e faturamento sugerido). Toda medida
da tela é uma soma dessas colunas ou uma divisão entre duas somas, então qualquer filtro dá o número certo:
- markup real   = faturamento - CMV            (% sobre o CMV)
- markup sugerido = faturamento sugerido - CMV (% sobre o mesmo CMV, para os dois serem comparáveis)
- saldo         = faturamento - faturamento sugerido (negativo: vendeu abaixo do sugerido)
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

PASTA_PARQUET = Path(__file__).parents[3] / "data" / "bd_comercial"
ARQUIVO = PASTA_PARQUET / "tb_markup.parquet"

_cache: dict[float, pl.DataFrame] = {}


def tabela() -> pl.DataFrame:
    """O cache inteiro (lido pelo pyarrow: o polars do navegador não lê Parquet direto)."""
    versao = ARQUIVO.stat().st_mtime
    if versao not in _cache:
        _cache.clear()
        _cache[versao] = pl.from_arrow(pq.read_table(ARQUIVO))
    return _cache[versao]


def meses() -> list[str]:
    return sorted(tabela()["MES"].unique().to_list(), reverse=True)


def marcas() -> list[str]:
    return sorted(tabela()["MARCA"].unique().to_list())


def filtrar(mes: str, marcas_sel: list[str] | None) -> pl.DataFrame:
    df = tabela().filter(pl.col("MES") == mes)
    if marcas_sel:
        df = df.filter(pl.col("MARCA").is_in(marcas_sel))
    return df


def resumo(df: pl.DataFrame) -> dict:
    soma = df.select(pl.col("QTD", "FAT", "CMV", "FAT_SUG").sum()).row(0, named=True)
    cmv = soma["CMV"] or 0.0
    return {
        **soma,
        "MKP": soma["FAT"] - cmv,
        "PCT_MKP": (soma["FAT"] / cmv - 1) if cmv else None,
        "PCT_SUG": (soma["FAT_SUG"] / cmv - 1) if cmv else None,
        "SALDO": soma["FAT"] - soma["FAT_SUG"],
    }


def por_produto(df: pl.DataFrame) -> pl.DataFrame:
    total = df["FAT"].sum() or 1.0
    return (
        df.group_by("CODRED", "PRODUTO", "MARCA")
        .agg(pl.col("QTD", "FAT", "CMV", "FAT_SUG").sum())
        .with_columns(
            (pl.col("FAT") / total).alias("PESO"),
            (pl.col("FAT") / pl.col("QTD")).alias("PRECO_REAL"),
            (pl.col("FAT_SUG") / pl.col("QTD")).alias("PRECO_SUG"),
            (pl.col("FAT") / pl.col("CMV") - 1).alias("PCT_MKP"),
            (pl.col("FAT_SUG") / pl.col("CMV") - 1).alias("PCT_SUG"),
            (pl.col("FAT") - pl.col("FAT_SUG")).alias("SALDO"),
        )
        .sort("FAT", descending=True)
    )
