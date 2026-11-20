import polars as pl

from core.dados import data_base, ler


def documentos() -> pl.DataFrame:
    hoje = data_base()
    return (
        ler("documentos")
        .filter(pl.col("situacao_sefaz") == "Autorizada")
        .with_columns(
            pl.col("emissao").dt.truncate("1mo").alias("mes"),
            (pl.lit(hoje) - pl.col("recebida_em")).dt.total_days().alias("dias_parada"),
            (pl.col("escriturada_em") - pl.col("recebida_em")).dt.total_days().alias("dias_para_escriturar"),
        )
    )


def por_filial_mes(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.group_by("destinatario", "mes")
        .agg(pl.len().alias("total"), pl.col("escriturada").sum().alias("escrituradas"))
        .with_columns((pl.col("escrituradas") / pl.col("total")).alias("percentual"))
        .sort("destinatario", "mes")
    )
