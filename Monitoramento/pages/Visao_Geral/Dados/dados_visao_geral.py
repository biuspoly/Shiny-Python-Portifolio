from datetime import timedelta

import polars as pl

from core.dados import data_base, ler


def sessoes(dias: int) -> pl.DataFrame:
    inicio = data_base() - timedelta(days=dias)
    return (
        ler("sessoes").filter(pl.col("inicio").dt.date() > inicio).with_columns(pl.col("inicio").dt.date().alias("dia"))
    )


def por_dia_app(df: pl.DataFrame) -> pl.DataFrame:
    return df.group_by("dia", "app").len().pivot(on="app", index="dia", values="len").fill_null(0).sort("dia")


def paginas_mais_usadas(df: pl.DataFrame, n: int = 10) -> pl.DataFrame:
    return (
        df.group_by("app", "pagina")
        .agg(pl.len().alias("sessoes"), pl.col("login").n_unique().alias("usuarios"), pl.col("minutos").sum())
        .sort("sessoes", descending=True)
        .head(n)
    )


def por_hora(df: pl.DataFrame) -> pl.DataFrame:
    return df.group_by(pl.col("inicio").dt.hour().alias("hora")).len().sort("hora")
