from datetime import timedelta

import polars as pl

from core.dados import data_base, ler


def rodadas(dias: int) -> pl.DataFrame:
    inicio = data_base() - timedelta(days=dias)
    return (
        ler("rotinas")
        .filter(pl.col("inicio").dt.date() > inicio)
        .with_columns(pl.col("inicio").dt.date().alias("noite"))
    )


def resumo(df: pl.DataFrame) -> pl.DataFrame:
    ultima = (
        df.sort("inicio")
        .group_by("rotina", maintain_order=True)
        .last()
        .select(
            "rotina",
            pl.col("status").alias("ultimo_status"),
            pl.col("minutos").alias("ultima_duracao"),
            pl.col("linhas").alias("ultimas_linhas"),
        )
    )
    return (
        df.group_by("rotina", "app")
        .agg(
            (pl.col("status") == "Sucesso").mean().alias("sucesso"),
            pl.col("minutos").mean().alias("duracao_media"),
            pl.col("minutos").max().alias("duracao_max"),
        )
        .join(ultima, on="rotina")
        .sort("sucesso")
    )
