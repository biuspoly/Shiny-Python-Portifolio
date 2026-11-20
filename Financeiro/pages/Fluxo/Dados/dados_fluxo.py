from datetime import date, timedelta

import polars as pl

from core.dados import data_base, ler


def contas() -> list[str]:
    return ler("contas")["conta"].to_list()


def _movimentos(conta: str | None) -> pl.DataFrame:
    """Entradas e saídas por dia: o que já aconteceu (realizado) e o que está previsto."""
    hoje = data_base()
    pagar = ler("titulos_pagar")
    receber = ler("receber")
    if conta:
        pagar = pagar.filter(pl.col("conta") == conta)
        receber = receber.filter(pl.col("conta") == conta)
    saidas = (
        pl.concat(
            [
                pagar.filter(pl.col("pago_em").is_not_null()).select(pl.col("pago_em").alias("data"), "valor"),
                # Título vencido e não pago entra como saída de hoje: é o que a tesouraria vai ter de cobrir.
                pagar.filter(pl.col("pago_em").is_null()).select(
                    pl.max_horizontal(pl.col("vencimento"), pl.lit(hoje)).alias("data"), "valor"
                ),
            ]
        )
        .group_by("data")
        .agg(pl.col("valor").sum().alias("saidas"))
    )
    entradas = (
        receber.select(
            "data", pl.when(pl.col("data") < hoje).then(pl.col("recebido")).otherwise(pl.col("previsto")).alias("valor")
        )
        .group_by("data")
        .agg(pl.col("valor").sum().alias("entradas"))
    )
    return (
        entradas.join(saidas, on="data", how="full", coalesce=True)
        .with_columns(pl.col("entradas", "saidas").fill_null(0.0))
        .sort("data")
    )


def fluxo(conta: str | None, dias_frente: int, dias_tras: int = 30) -> pl.DataFrame:
    hoje = data_base()
    inicial = ler("contas")
    if conta:
        inicial = inicial.filter(pl.col("conta") == conta)
    mov = _movimentos(conta).with_columns(
        (inicial["saldo_inicial"].sum() + (pl.col("entradas") - pl.col("saidas")).cum_sum()).alias("saldo"),
        (pl.col("data") < hoje).alias("realizado"),
    )
    return mov.filter(
        pl.col("data") >= hoje - timedelta(days=dias_tras), pl.col("data") <= hoje + timedelta(days=dias_frente)
    )


def saldo_hoje(conta: str | None) -> float:
    hoje = data_base()
    passado = fluxo(conta, 0, dias_tras=10000).filter(pl.col("data") < hoje)
    return passado["saldo"][-1] if passado.height else 0.0


def indicadores() -> dict:
    ind = ler("indicadores_bcb")
    dolar = ind.drop_nulls("dolar").select("data", "dolar")
    selic = ind.drop_nulls("selic").filter(pl.col("data") <= data_base()).select("data", "selic")
    ipca = ind.drop_nulls("ipca_mes").select("data", "ipca_mes").tail(12)
    acumulado = 1.0
    for v in ipca["ipca_mes"]:
        acumulado *= 1 + v / 100
    return {
        "dolar": dolar.tail(90),
        "selic": selic["selic"][-1] if selic.height else None,
        "selic_data": selic["data"][-1] if selic.height else None,
        "ipca_12m": acumulado - 1,
        "ipca_ate": ipca["data"][-1] if ipca.height else None,
    }


def ultimo_dia_util(d: date) -> date:
    while d.weekday() == 6:
        d -= timedelta(days=1)
    return d
