from datetime import date

import polars as pl

from core.dados import data_base, ler


def _mes_anterior() -> date:
    hoje = data_base()
    return date(hoje.year - 1, 12, 1) if hoje.month == 1 else date(hoje.year, hoje.month - 1, 1)


def _situacao_documento(vencimento: str, pago: str) -> pl.Expr:
    hoje = data_base()
    return (
        pl.when(pl.col(pago))
        .then(pl.lit("Pago"))
        .when(pl.col(vencimento) < hoje)
        .then(pl.lit("Vencido"))
        .otherwise(pl.lit("A vencer"))
    )


def veiculos() -> pl.DataFrame:
    """Um veículo por linha com custo do mês anterior, multas abertas e documentos."""
    mes = _mes_anterior()
    uso = (
        ler("frota_mes")
        .filter(pl.col("mes") == mes)
        .select("placa", "km", (pl.col("custo_combustivel") + pl.col("custo_manutencao")).alias("custo"))
    )
    abertas = (
        ler("multas")
        .filter(pl.col("situacao") == "Em aberto")
        .group_by("placa")
        .agg(pl.len().alias("multas_abertas"), pl.col("valor").sum().alias("valor_multas"))
    )
    docs = ler("documentos_veiculo").select(
        "placa",
        _situacao_documento("ipva_vencimento", "ipva_pago").alias("ipva"),
        _situacao_documento("licenciamento_vencimento", "licenciamento_pago").alias("licenciamento"),
    )
    return (
        ler("veiculos")
        .join(uso, on="placa", how="left")
        .join(abertas, on="placa", how="left")
        .join(docs, on="placa", how="left")
        .with_columns(
            pl.col("multas_abertas").fill_null(0),
            pl.col("valor_multas").fill_null(0.0),
            (pl.col("custo") / pl.col("km")).alias("custo_km"),
            (data_base().year - pl.col("ano")).alias("idade"),
        )
        .with_columns(
            (
                (pl.col("multas_abertas") > 0) | (pl.col("ipva") == "Vencido") | (pl.col("licenciamento") == "Vencido")
            ).alias("pendente")
        )
        .sort("pendente", "valor_multas", descending=True)
    )


def custo_mensal(placas: list[str]) -> pl.DataFrame:
    return (
        ler("frota_mes")
        .filter(pl.col("placa").is_in(placas))
        .group_by("mes")
        .agg(pl.col("km", "custo_combustivel", "custo_manutencao").sum())
        .sort("mes")
    )


def multas(placas: list[str], so_abertas: bool) -> pl.DataFrame:
    df = ler("multas").filter(pl.col("placa").is_in(placas))
    if so_abertas:
        df = df.filter(pl.col("situacao") == "Em aberto")
    return df.sort("data", descending=True)
