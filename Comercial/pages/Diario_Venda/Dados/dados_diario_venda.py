from datetime import date, timedelta

import polars as pl

from core.dados import data_base, ler


def _mes_menos(mes: date, n: int) -> date:
    ano, m = mes.year, mes.month - n
    while m <= 0:
        m += 12
        ano -= 1
    return date(ano, m, 1)


def meses_com_meta() -> list[date]:
    return sorted(ler("metas")["mes"].unique().to_list(), reverse=True)


def dias_uteis(mes: date) -> tuple[int, int]:
    """(dias úteis do mês, dias úteis já passados) -- segunda a sábado."""
    fim = _mes_menos(mes, -1) - timedelta(days=1)
    hoje = data_base()
    dias = [mes + timedelta(days=i) for i in range((fim - mes).days + 1)]
    uteis = [d for d in dias if d.weekday() < 6]
    return len(uteis), sum(1 for d in uteis if d <= hoje)


def equipe(filial: str | None) -> pl.DataFrame:
    eq = ler("equipe")
    return eq if not filial else eq.filter(pl.col("filial") == filial)


def vendedores_escolhidos(filial: str | None, gerentes: list[str], vendedores: list[str]) -> list[int]:
    eq = equipe(filial)
    if gerentes:
        eq = eq.filter(pl.col("gerente").is_in(gerentes))
    if vendedores:
        eq = eq.filter(pl.col("vendedor").is_in(vendedores))
    return eq["cod_vendedor"].to_list()


def tabela_categorias(mes: date, cods: list[int]) -> pl.DataFrame:
    """Uma linha por total, categoria e marca; colunas por mês e indicador."""
    meses = {"m12": _mes_menos(mes, 12), "m2": _mes_menos(mes, 2), "m1": _mes_menos(mes, 1), "real": mes}
    prod = ler("produtos").select("cod_produto", "categoria", "marca", "cor_marca")
    vendas = (
        ler("vendas_mes")
        .filter(pl.col("cod_vendedor").is_in(cods), pl.col("mes").is_in(list(meses.values())))
        .join(prod, on="cod_produto")
    )

    def por(nivel: str | None) -> pl.DataFrame:
        chave = [pl.lit("VOLUME TOTAL").alias("linha")] if nivel is None else [pl.col(nivel).alias("linha")]
        return vendas.group_by(*chave, "mes").agg(pl.col("hl", "faturamento").sum())

    longo = pl.concat(
        [
            por(None).with_columns(pl.lit("total").alias("nivel")),
            por("categoria").with_columns(pl.lit("categoria").alias("nivel")),
            por("marca").with_columns(pl.lit("marca").alias("nivel")),
        ]
    )
    nome_mes = {v: k for k, v in meses.items()}
    largo = longo.with_columns(pl.col("mes").replace_strict(nome_mes).alias("coluna")).pivot(
        on="coluna", index=["nivel", "linha"], values="hl"
    )
    for col in meses:
        if col not in largo.columns:
            largo = largo.with_columns(pl.lit(None, dtype=pl.Float64).alias(col))
    fat = longo.filter(pl.col("mes") == mes).select("nivel", "linha", pl.col("faturamento").alias("fat"))

    metas = ler("metas").filter(pl.col("mes") == mes, pl.col("cod_vendedor").is_in(cods))
    meta = (
        pl.concat(
            [
                metas.select(pl.lit("total").alias("nivel"), pl.lit("VOLUME TOTAL").alias("linha"), "meta_hl"),
                metas.select(pl.lit("categoria").alias("nivel"), pl.col("categoria").alias("linha"), "meta_hl"),
            ]
        )
        .group_by("nivel", "linha")
        .agg(pl.col("meta_hl").sum().alias("meta"))
    )

    cob = (
        ler("cobertura_mes")
        .filter(pl.col("cod_vendedor").is_in(cods), pl.col("mes").is_in([meses["m1"], mes]))
        .with_columns(pl.when(pl.col("mes") == mes).then(pl.lit("cob")).otherwise(pl.lit("cob_m1")).alias("coluna"))
    )
    cob = (
        cob.with_columns(
            pl.when(pl.col("nivel") == "total").then(pl.lit("VOLUME TOTAL")).otherwise(pl.col("item")).alias("linha")
        )
        .group_by("nivel", "linha", "coluna")
        .agg(pl.col("clientes").sum())
        .pivot(on="coluna", index=["nivel", "linha"], values="clientes")
    )
    for col in ("cob", "cob_m1"):
        if col not in cob.columns:
            cob = cob.with_columns(pl.lit(None, dtype=pl.UInt32).alias(col))

    total_uteis, passados = dias_uteis(mes)
    fator = total_uteis / passados if passados else 1.0
    ordem_nivel = {"total": 0, "categoria": 1, "marca": 2}
    cores = prod.select(pl.col("marca").alias("linha"), "cor_marca").unique()
    return (
        largo.join(meta, on=["nivel", "linha"], how="left")
        .join(cob, on=["nivel", "linha"], how="left")
        .join(fat, on=["nivel", "linha"], how="left")
        .join(cores, on="linha", how="left")
        .with_columns(
            (pl.col("real") * fator).alias("tend"),
            (pl.col("fat") / pl.col("real") / 1.0).alias("rs_hl"),
            pl.col("nivel").replace_strict(ordem_nivel).alias("_ordem"),
        )
        .with_columns((pl.col("tend") / pl.col("meta")).alias("tend_meta"))
        .sort("_ordem", "real", descending=[False, True], nulls_last=True)
        .drop("_ordem")
    )


def venda_por_dia(mes: date, cods: list[int]) -> pl.DataFrame:
    prod = ler("produtos").select("cod_produto", "litros_caixa")
    return (
        ler("vendas_dia")
        .filter(pl.col("cod_vendedor").is_in(cods), pl.col("data") >= mes, pl.col("data") < _mes_menos(mes, -1))
        .join(prod, on="cod_produto")
        .group_by("data")
        .agg((pl.col("caixas") * pl.col("litros_caixa") / 100).sum().alias("hl"), pl.col("faturamento").sum())
        .sort("data")
    )


def evolucao_mensal(mes: date, cods: list[int]) -> pl.DataFrame:
    inicio = _mes_menos(mes, 12)
    return (
        ler("vendas_mes")
        .filter(pl.col("cod_vendedor").is_in(cods), pl.col("mes") >= inicio, pl.col("mes") <= mes)
        .group_by("mes")
        .agg(pl.col("hl", "faturamento").sum())
        .sort("mes")
    )
