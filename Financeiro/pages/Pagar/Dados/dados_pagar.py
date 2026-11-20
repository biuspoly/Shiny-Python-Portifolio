from datetime import date, timedelta

import polars as pl

from core.dados import data_base, ler

SITUACOES = ["Vencido", "Vence hoje", "Próximos 7 dias", "A vencer", "Pago"]


def titulos() -> pl.DataFrame:
    hoje = data_base()
    return ler("titulos_pagar").with_columns(
        pl.when(pl.col("pago_em").is_not_null())
        .then(pl.lit("Pago"))
        .when(pl.col("vencimento") < hoje)
        .then(pl.lit("Vencido"))
        .when(pl.col("vencimento") == hoje)
        .then(pl.lit("Vence hoje"))
        .when(pl.col("vencimento") <= hoje + timedelta(days=7))
        .then(pl.lit("Próximos 7 dias"))
        .otherwise(pl.lit("A vencer"))
        .alias("situacao"),
        (pl.lit(hoje) - pl.col("vencimento")).dt.total_days().alias("dias_atraso"),
    )


def periodo_padrao() -> tuple[date, date]:
    hoje = data_base()
    return hoje - timedelta(days=15), hoje + timedelta(days=30)


def por_centro(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.group_by("centro_custo")
        .agg(
            pl.col("valor").filter(pl.col("situacao") == "Pago").sum().alias("pago"),
            pl.col("valor").filter(pl.col("situacao") != "Pago").sum().alias("aberto"),
        )
        .sort(pl.col("pago") + pl.col("aberto"), descending=True)
    )
