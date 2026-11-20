import polars as pl

from core.dados import data_base, ler

# Faixas do farol pelo atraso do fechamento (dias entre o movimento e o fechamento).
FAIXAS = [
    (0, "No dia", "#087F5B"),
    (1, "1 a 2 dias", "#C9A227"),
    (3, "3 dias ou mais", "#B3262D"),
    (-1, "Em aberto", "#3F3F46"),
]


def fechamentos(dias: int = 30) -> pl.DataFrame:
    hoje = data_base()
    return (
        ler("fechamento_caixa")
        .filter(pl.col("data") >= pl.lit(hoje) - pl.duration(days=dias))
        .with_columns(
            pl.when(pl.col("fechado_em").is_null())
            .then(-1)
            .otherwise((pl.col("fechado_em") - pl.col("data")).dt.total_days())
            .alias("atraso")
        )
        .with_columns(
            pl.when(pl.col("atraso") < 0)
            .then(3)
            .when(pl.col("atraso") == 0)
            .then(0)
            .when(pl.col("atraso") <= 2)
            .then(1)
            .otherwise(2)
            .alias("faixa")
        )
        .sort("filial", "data")
    )


def resumo(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.group_by("filial")
        .agg(
            (pl.col("atraso") == 0).mean().alias("no_dia"),
            pl.col("atraso").filter(pl.col("atraso") >= 0).mean().alias("atraso_medio"),
            (pl.col("atraso") < 0).sum().alias("em_aberto"),
            pl.col("data").filter(pl.col("atraso") < 0).min().alias("aberto_desde"),
        )
        .sort("no_dia")
    )
