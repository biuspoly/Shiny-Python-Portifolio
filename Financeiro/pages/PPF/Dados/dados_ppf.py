"""Leitura do cache .parquet do financeiro (data/bd_financeiro/): só o que as telas do portfólio usam."""

from pathlib import Path

import polars as pl

from core.compat import ler_parquet
from core.config import REVENDAS_POR_GRUPO, casar_revendas

PASTA_PARQUET = Path(__file__).parents[3] / "data" / "bd_financeiro"

_cache: dict[tuple[str, int], pl.DataFrame] = {}

# Colunas de "quem viu" que o pipeline às vezes grava como número: a tela trata como texto.
_VISTOS = ("pagar", "pagou", "auditoria", "conselho", "entrada_manual")


def _carregar(arquivo: str, fixar: bool = True) -> pl.DataFrame:
    caminho = PASTA_PARQUET / f"{arquivo}.parquet"
    if not caminho.is_file():
        return pl.DataFrame()
    chave = (str(caminho), caminho.stat().st_mtime_ns)
    if chave not in _cache:
        base = ler_parquet(caminho)
        fora = [c for c in _VISTOS if c in base.columns and base[c].dtype != pl.Utf8]
        _cache[chave] = base.with_columns(pl.col(fora).cast(pl.Utf8)) if fora else base
    return _cache[chave]


def contas_pagar() -> pl.DataFrame:
    return _carregar("contas_pagar")


def titulos_pagos() -> pl.DataFrame:
    return _carregar("titulos_pagos")


def titulos_pagos_emprestimos() -> pl.DataFrame:
    return _carregar("titulos_pagos_emprestimos")


def fornecedores() -> pl.DataFrame:
    return _carregar("fornecedor")


def revendas_da_url(revenda: str | None) -> list[str] | None:
    if not revenda:
        return None
    grupo = REVENDAS_POR_GRUPO.get(revenda.upper())
    return list(grupo) if grupo else [revenda]


def extratos_fabricas_totais(fixar: bool = True) -> pl.DataFrame:
    return _carregar("extratos_fabricas_totais", fixar=fixar)


def extratos_fabricas_tabela() -> pl.DataFrame:
    base = _carregar("extratos_fabricas_tabela")
    if base.is_empty() or not {"REVENDA", "fabrica", "data_hora"} <= set(base.columns):
        return base
    quando = pl.col("data_hora").cast(pl.Datetime, strict=False)
    base = base.filter(quando.is_not_null() & (quando.dt.year() > 1900))
    return base.filter(quando == quando.max().over(["REVENDA", "fabrica"]))


def extratos_fabricas_leituras(fixar: bool = True) -> pl.DataFrame:
    base = _carregar("extratos_fabricas_tabela", fixar=fixar)
    if base.is_empty() or "data_hora" not in base.columns:
        return base
    quando = pl.col("data_hora").cast(pl.Datetime, strict=False)
    return base.filter(quando.is_not_null() & (quando.dt.year() > 1900))


def ultima_leitura_por_fabrica(base: pl.DataFrame) -> pl.DataFrame:
    if base.is_empty() or "fabrica" not in base.columns or "data_hora" not in base.columns:
        return base
    return base.sort("data_hora", descending=True, nulls_last=True).unique(
        subset=["REVENDA", "fabrica"], keep="first", maintain_order=True
    )


def filtrar_por_revenda(base: pl.DataFrame, revenda: str | None) -> pl.DataFrame:
    alvos = revendas_da_url(revenda)
    if base.is_empty() or alvos is None or "REVENDA" not in base.columns:
        return base
    reais = casar_revendas(base["REVENDA"].unique().to_list(), alvos)
    return base.filter(pl.col("REVENDA").is_in(reais))


def com_nome_fornecedor(base: pl.DataFrame, coluna_cgc: str = "PGMOVMOV_CGC") -> pl.DataFrame:
    if base.is_empty():
        return base
    if "FORNECEDOR" in base.columns:
        if "TIPO_FORNECEDOR" in base.columns:
            return base
        return base.with_columns(pl.lit(None, dtype=pl.Utf8).alias("TIPO_FORNECEDOR"))

    forn = fornecedores()
    if forn.is_empty() or coluna_cgc not in base.columns:
        return base.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("FORNECEDOR"),
            pl.lit(None, dtype=pl.Utf8).alias("TIPO_FORNECEDOR"),
        )
    forn = forn.select(
        pl.col("REVENDA"),
        pl.col("PGCADFOR_CGC").alias(coluna_cgc),
        pl.col("FORNECEDOR"),
        pl.col("TIPO_FORNECEDOR"),
    ).unique(subset=["REVENDA", coluna_cgc], keep="first")
    return base.join(forn, on=["REVENDA", coluna_cgc], how="left")
