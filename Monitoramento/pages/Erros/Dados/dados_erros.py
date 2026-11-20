from datetime import timedelta

import polars as pl

from core.dados import data_base, ler


def erros(dias: int, apps: list[str]) -> pl.DataFrame:
    df = ler("erros").filter(pl.col("momento").dt.date() > data_base() - timedelta(days=dias))
    return df.filter(pl.col("app").is_in(apps)) if apps else df


def agrupados(df: pl.DataFrame) -> pl.DataFrame:
    """Um erro por mensagem: quantas vezes, quantas pessoas e quando foi a última."""
    return (
        df.group_by("app", "pagina", "mensagem")
        .agg(
            pl.len().alias("vezes"),
            pl.col("login").n_unique().alias("pessoas"),
            pl.col("momento").min().alias("primeira"),
            pl.col("momento").max().alias("ultima"),
        )
        .sort("vezes", descending=True)
    )
