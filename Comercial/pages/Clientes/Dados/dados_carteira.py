from datetime import date

import polars as pl

from core.dados import data_base, ler

SITUACOES = ["Ativo", "Em risco", "Inativo"]


def _meses_entre(inicio: date, fim: date) -> int:
    return (fim.year - inicio.year) * 12 + fim.month - inicio.month


def carteira() -> pl.DataFrame:
    """Um cliente por linha, com os números dos últimos 12 meses.

    Situação pela última compra: no mês corrente = Ativo, 1 a 2 meses sem
    comprar = Em risco, 3 ou mais = Inativo.
    """
    hoje = data_base()
    mes_atual = date(hoje.year, hoje.month, 1)
    doze = (
        ler("cliente_mes")
        .group_by("cod_cliente")
        .agg(
            pl.col("hl").sum().alias("hl_12m"),
            pl.col("faturamento").sum().alias("fat_12m"),
            pl.col("custo").sum().alias("custo_12m"),
            pl.col("mes").n_unique().alias("meses_com_compra"),
        )
    )
    equipe = ler("equipe").select("cod_vendedor", "vendedor", "gerente")
    return (
        ler("clientes")
        .join(doze, on="cod_cliente", how="left")
        .join(equipe, on="cod_vendedor", how="left")
        .with_columns(
            pl.col("ultima_compra")
            .map_elements(lambda d: None if d is None else _meses_entre(d, mes_atual), return_dtype=pl.Int64)
            .alias("meses_sem_compra"),
            pl.col("hl_12m", "fat_12m", "custo_12m").fill_null(0),
            pl.col("meses_com_compra").fill_null(0),
        )
        .with_columns(
            pl.when(pl.col("meses_sem_compra") == 0)
            .then(pl.lit("Ativo"))
            .when(pl.col("meses_sem_compra") <= 2)
            .then(pl.lit("Em risco"))
            .otherwise(pl.lit("Inativo"))
            .alias("situacao"),
            (pl.col("fat_12m") / pl.col("custo_12m") - 1).alias("markup_12m"),
            (pl.col("fat_12m") - pl.col("custo_12m")).alias("saldo_markup_12m"),
        )
        .sort("fat_12m", descending=True)
    )


def historico(cod_cliente: int) -> pl.DataFrame:
    return ler("cliente_mes").filter(pl.col("cod_cliente") == cod_cliente).sort("mes")
