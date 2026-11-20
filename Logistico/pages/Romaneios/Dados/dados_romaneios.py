from datetime import date

import polars as pl

from core.dados import ler


def datas() -> list[date]:
    return sorted(ler("entregas")["data"].unique().to_list(), reverse=True)


def entregas(dia: date, filial: str | None) -> pl.DataFrame:
    df = ler("entregas").filter(pl.col("data") == dia)
    return df.filter(pl.col("filial") == filial) if filial else df


def pendentes_anteriores(dia: date, filial: str | None) -> pl.DataFrame:
    """Notas de dias anteriores que ainda não tiveram baixa."""
    df = ler("entregas").filter(pl.col("data") < dia, pl.col("status") == "Pendente")
    return df.filter(pl.col("filial") == filial) if filial else df


def por_romaneio(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.group_by("romaneio", "placa", "motorista", "filial")
        .agg(
            pl.len().alias("entregas"),
            (pl.col("status") == "Entregue").sum().alias("entregues"),
            (pl.col("status") == "Pendente").sum().alias("pendentes"),
            pl.col("status").str.starts_with("Devolvida").sum().alias("devolvidas"),
            pl.col("valor").sum(),
            pl.col("valor_devolvido").sum(),
        )
        .with_columns(((pl.col("entregas") - pl.col("pendentes")) / pl.col("entregas")).alias("concluido"))
        .sort("concluido", "romaneio")
    )
