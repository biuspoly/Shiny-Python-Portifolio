import polars as pl

COLUNA_SITUACAO_MULTA = "SITUACAO"

PAGA_SIM = "Sim"
PAGA_NAO = "Não"
PAGA_SUSPENSA = "Susp/Canc"
PAGA_DESCONHECIDA = ""

SITUACAO_SEM_INFORMACAO = "__sem_informacao__"

SITUACOES_MULTA = {
    "PAGAS": "Pagas",
    "NAO_PAGAS_VENCIDAS": "Não pagas - vencidas",
    "NAO_PAGAS_A_VENCER": "Não pagas - a vencer",
    "SUSPENSAS_E_CANCELADAS": "Suspensas e canceladas",
    SITUACAO_SEM_INFORMACAO: "Sem informação",
}


def _situacao_normalizada() -> pl.Expr:
    return pl.col(COLUNA_SITUACAO_MULTA).cast(pl.Utf8).str.strip_chars().str.to_uppercase()


def expr_paga() -> pl.Expr:
    situacao = _situacao_normalizada()
    return (
        pl.when(situacao == "PAGAS")
        .then(pl.lit(PAGA_SIM))
        .when(situacao == "SUSPENSAS_E_CANCELADAS")
        .then(pl.lit(PAGA_SUSPENSA))
        .when(situacao.is_null() | (situacao == ""))
        .then(pl.lit(PAGA_DESCONHECIDA))
        .otherwise(pl.lit(PAGA_NAO))
        .alias("PAGA")
    )


JANELA_SENATRAN_DIAS = 365

PAGA_POR_SENATRAN = "Senatran"
PAGA_POR_HISTORICO = "Constou paga antes"
PAGA_POR_SUMIU = "Sumiu da consulta"


def marcar_pagas(renainf: pl.DataFrame, consultas_ok: pl.DataFrame | None = None) -> pl.DataFrame:
    if renainf.height == 0 or not {"PLACA", "AUTO_INFRACAO", "DTA_EXEC"} <= set(renainf.columns):
        return renainf
    chave = ["PLACA", "AUTO_INFRACAO"]
    situacao = _situacao_normalizada()
    data_inf = (
        pl.col("DATA_HORA_INF").cast(pl.Utf8).str.slice(0, 10).str.to_date("%d/%m/%Y", strict=False)
        if "DATA_HORA_INF" in renainf.columns
        else pl.lit(None, dtype=pl.Date)
    )
    marcado = renainf.with_columns(
        pl.col("DTA_EXEC").cast(pl.Utf8),
        (situacao == "PAGAS").fill_null(False).any().over(chave).alias("_JA_PAGA"),
        pl.col("DTA_EXEC").cast(pl.Utf8).max().over(chave).alias("_ULTIMA_VEZ"),
        pl.col("DTA_EXEC").cast(pl.Utf8).max().over("PLACA").alias("_ULTIMA_OK"),
        data_inf.alias("_DATA_INF"),
    )
    if consultas_ok is not None and consultas_ok.height:
        ok = (
            consultas_ok.select(pl.col("PLACA").cast(pl.Utf8), pl.col("DTA_EXEC").cast(pl.Utf8).alias("_CONSULTA_OK"))
            .group_by("PLACA")
            .agg(pl.col("_CONSULTA_OK").max())
        )
        marcado = (
            marcado.join(ok, on="PLACA", how="left")
            .with_columns(
                pl.when(pl.col("_CONSULTA_OK") > pl.col("_ULTIMA_OK"))
                .then(pl.col("_CONSULTA_OK"))
                .otherwise(pl.col("_ULTIMA_OK"))
                .alias("_ULTIMA_OK")
            )
            .drop("_CONSULTA_OK")
        )
    data_ok = pl.col("_ULTIMA_OK").str.to_date("%Y%m%d", strict=False)
    sumiu = (
        (pl.col("_ULTIMA_VEZ") < pl.col("_ULTIMA_OK"))
        & (pl.col("_DATA_INF") >= data_ok - pl.duration(days=JANELA_SENATRAN_DIAS))
    ).fill_null(False)
    return marcado.with_columns(
        pl.col(COLUNA_SITUACAO_MULTA).alias("SITUACAO_SENATRAN"),
        pl.when(situacao == "PAGAS")
        .then(pl.lit(PAGA_POR_SENATRAN))
        .when(pl.col("_JA_PAGA"))
        .then(pl.lit(PAGA_POR_HISTORICO))
        .when(sumiu)
        .then(pl.lit(PAGA_POR_SUMIU))
        .otherwise(pl.lit(None, dtype=pl.Utf8))
        .alias("PAGA_POR"),
        pl.when(pl.col("_JA_PAGA") | sumiu)
        .then(pl.lit("PAGAS"))
        .otherwise(pl.col(COLUNA_SITUACAO_MULTA))
        .alias(COLUNA_SITUACAO_MULTA),
    ).drop("_JA_PAGA", "_ULTIMA_VEZ", "_ULTIMA_OK", "_DATA_INF")


def expr_sem_situacao() -> pl.Expr:
    situacao = _situacao_normalizada()
    return situacao.is_null() | (situacao == "")
