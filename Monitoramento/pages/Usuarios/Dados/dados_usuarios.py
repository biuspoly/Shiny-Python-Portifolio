from datetime import timedelta

import polars as pl

from core.dados import data_base, ler


def resumo(dias: int) -> pl.DataFrame:
    inicio = data_base() - timedelta(days=dias)
    s = ler("sessoes").filter(pl.col("inicio").dt.date() > inicio)
    uso = s.group_by("login").agg(
        pl.len().alias("sessoes"),
        pl.col("minutos").sum(),
        pl.col("inicio").max().alias("ultima"),
        pl.col("app").unique().sort().str.join(", ").alias("apps"),
    )
    return (
        ler("usuarios")
        .join(uso, on="login", how="left")
        .with_columns(pl.col("sessoes").fill_null(0), pl.col("minutos").fill_null(0.0))
        .sort("sessoes", descending=True)
    )


def atividade(login: str, dias: int) -> pl.DataFrame:
    inicio = data_base() - timedelta(days=dias)
    return (
        ler("sessoes")
        .filter(pl.col("login") == login, pl.col("inicio").dt.date() > inicio)
        .group_by(pl.col("inicio").dt.date().alias("dia"))
        .agg(pl.len().alias("sessoes"), pl.col("minutos").sum())
        .sort("dia")
    )
