from datetime import date

import polars as pl

from core.dados import ler


def meses() -> list[date]:
    return sorted(ler("vendas_mes")["mes"].unique().to_list(), reverse=True)[:13]


def _mes_anterior(mes: date) -> date:
    return date(mes.year - 1, 12, 1) if mes.month == 1 else date(mes.year, mes.month - 1, 1)


def por_produto(mes: date, filial: str | None, categorias: list[str], marcas: list[str]) -> pl.DataFrame:
    """Preço, custo e markup de cada produto no mês, com o markup do mês anterior ao lado."""
    eq = ler("equipe")
    if filial:
        eq = eq.filter(pl.col("filial") == filial)
    prod = ler("produtos")
    if categorias:
        prod = prod.filter(pl.col("categoria").is_in(categorias))
    if marcas:
        prod = prod.filter(pl.col("marca").is_in(marcas))
    anterior = _mes_anterior(mes)
    agregado = (
        ler("vendas_mes")
        .filter(pl.col("mes").is_in([mes, anterior]), pl.col("cod_vendedor").is_in(eq["cod_vendedor"].to_list()))
        .join(prod.select("cod_produto"), on="cod_produto", how="semi")
        .group_by("cod_produto", "mes")
        .agg(pl.col("caixas", "faturamento", "custo").sum())
    )
    atual = agregado.filter(pl.col("mes") == mes).drop("mes")
    passado = agregado.filter(pl.col("mes") == anterior).select(
        "cod_produto", (pl.col("faturamento") / pl.col("custo") - 1).alias("markup_anterior")
    )
    return (
        atual.join(passado, on="cod_produto", how="left")
        .join(prod.select("cod_produto", "produto", "marca", "categoria", "cor_marca"), on="cod_produto")
        .with_columns(
            (pl.col("faturamento") / pl.col("caixas")).alias("preco_medio"),
            (pl.col("custo") / pl.col("caixas")).alias("custo_medio"),
            (pl.col("faturamento") / pl.col("custo") - 1).alias("markup"),
            (pl.col("faturamento") - pl.col("custo")).alias("saldo"),
        )
        .with_columns(
            (pl.col("markup") - pl.col("markup_anterior")).alias("variacao_pp"),
            (pl.col("faturamento") / pl.col("faturamento").sum()).alias("participacao"),
        )
        .sort("saldo", descending=True)
    )


def por_categoria(produtos: pl.DataFrame) -> pl.DataFrame:
    return (
        produtos.group_by("categoria")
        .agg(pl.col("faturamento", "custo").sum())
        .with_columns((pl.col("faturamento") / pl.col("custo") - 1).alias("markup"))
        .sort("markup", descending=True)
    )
