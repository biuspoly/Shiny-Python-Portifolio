import polars as pl

from core.dados import data_base, ler

SITUACOES = ["Ativo", "Contrato vencido", "Recolha pedida", "Recolhido"]
EM_CAMPO = ["Ativo", "Contrato vencido", "Recolha pedida"]
DIAS_SEM_VISITA = 90


def comodatos() -> pl.DataFrame:
    hoje = data_base()
    return (
        ler("comodatos")
        .with_columns(
            (pl.lit(hoje) - pl.col("ultima_visita")).dt.total_days().alias("dias_sem_visita"),
            (pl.col("vencimento_contrato") - pl.lit(hoje)).dt.total_days().alias("dias_para_vencer"),
        )
        .sort("situacao", "dias_sem_visita", descending=[False, True])
    )


def por_equipamento(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.group_by("equipamento", "situacao")
        .len()
        .pivot(on="situacao", index="equipamento", values="len")
        .fill_null(0)
        .sort("equipamento")
    )
