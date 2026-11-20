from datetime import date

import polars as pl

from core.dados import ler

INDICADORES = {
    "hl": "Volume (HL)",
    "faturamento": "Faturamento (R$)",
    "positivados": "Clientes positivados",
    "cobertura": "Cobertura (% da carteira)",
}


def meses() -> list[date]:
    return sorted(ler("cliente_mes")["mes"].unique().to_list(), reverse=True)


def filiais() -> dict[str, str]:
    """Filial -> UF (o mapa desenha um estado por vez)."""
    return dict(ler("clientes").select("filial", "uf").unique().sort("filial").iter_rows())


def por_cidade(filial: str, mes: date) -> pl.DataFrame:
    clientes = ler("clientes").filter(pl.col("filial") == filial)
    compras = (
        ler("cliente_mes")
        .filter(pl.col("mes") == mes)
        .join(clientes.select("cod_cliente", "cod_ibge"), on="cod_cliente")
        .group_by("cod_ibge")
        .agg(pl.col("hl", "faturamento").sum(), pl.len().alias("positivados"))
    )
    carteira = clientes.group_by("cod_ibge", "cidade").agg(pl.len().alias("carteira"))
    return (
        carteira.join(compras, on="cod_ibge", how="left")
        .with_columns(pl.col("hl", "faturamento").fill_null(0.0), pl.col("positivados").fill_null(0))
        .with_columns((pl.col("positivados") / pl.col("carteira")).alias("cobertura"))
        .sort("hl", descending=True)
    )
