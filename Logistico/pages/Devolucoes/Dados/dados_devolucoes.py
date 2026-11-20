from datetime import date, timedelta

import polars as pl

from core.dados import data_base, ler

PERIODOS = {"7": "Últimos 7 dias", "30": "Últimos 30 dias", "60": "Últimos 60 dias"}


def periodo(dias: int, filial: str | None, motivos: list[str]) -> pl.DataFrame:
    # Só dias fechados: hoje ainda tem caminhão na rua e o índice sairia zerado.
    hoje = data_base()
    df = ler("entregas").filter(
        pl.col("data") > hoje - timedelta(days=dias), pl.col("data") < hoje, pl.col("status") != "Pendente"
    )
    if filial:
        df = df.filter(pl.col("filial") == filial)
    if motivos:
        # O motivo filtra o que voltou; o faturado do período fica inteiro para o %.
        df = df.with_columns(
            pl.when(pl.col("motivo").is_in(motivos))
            .then(pl.col("valor_devolvido"))
            .otherwise(0.0)
            .alias("valor_devolvido"),
            pl.when(pl.col("motivo").is_in(motivos)).then(pl.col("motivo")).otherwise(None).alias("motivo"),
        )
    return df


def por_motivo(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.filter(pl.col("valor_devolvido") > 0)
        .group_by("motivo")
        .agg(pl.col("valor_devolvido").sum(), pl.len().alias("notas"))
        .sort("valor_devolvido", descending=True)
    )


def por_dia(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.group_by("data")
        .agg(pl.col("valor", "valor_devolvido").sum())
        .with_columns((pl.col("valor_devolvido") / pl.col("valor")).alias("indice"))
        .sort("data")
    )


def por_cliente(df: pl.DataFrame) -> pl.DataFrame:
    # mode() de texto dentro do agg derruba o polars 1.18 (o do Shinylive):
    # o motivo mais comum sai de uma contagem à parte.
    motivo = (
        df.filter(pl.col("motivo").is_not_null())
        .group_by("cod_cliente", "motivo")
        .len()
        .sort("len", "motivo", descending=[True, False])
        .group_by("cod_cliente", maintain_order=True)
        .first()
        .select("cod_cliente", pl.col("motivo").alias("motivo_mais_comum"))
    )
    return (
        df.group_by("cod_cliente", "cliente", "cidade")
        .agg(
            pl.col("valor").sum().alias("faturado"),
            pl.col("valor_devolvido").sum().alias("devolvido"),
            (pl.col("valor_devolvido") > 0).sum().alias("notas_devolvidas"),
        )
        .filter(pl.col("devolvido") > 0)
        .join(motivo, on="cod_cliente", how="left")
        .with_columns((pl.col("devolvido") / pl.col("faturado")).alias("indice"))
        .sort("devolvido", descending=True)
    )


def ultima_data() -> date:
    return ler("entregas")["data"].max()
