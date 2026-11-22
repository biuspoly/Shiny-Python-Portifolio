"""Portfólio: o que o Comodato grava no MySQL (solicitações, anexos) vai direto para o .parquet que a tela
lê. No navegador esse arquivo fica na memória da página: vale até ela fechar."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from core.compat import gravar_parquet, ler_parquet

PASTA = Path(__file__).parents[3] / "data" / "bd_comodato"


def ler(nome: str) -> pl.DataFrame:
    caminho = PASTA / f"{nome}.parquet"
    return ler_parquet(caminho) if caminho.exists() else pl.DataFrame()


def gravar(nome: str, tabela: pl.DataFrame) -> None:
    gravar_parquet(tabela, PASTA / f"{nome}.parquet")
    # As partições por revenda (<nome>_<cnpj>.parquet) são o mesmo dado cortado: refeitas junto.
    for parcial in PASTA.glob(f"{nome}_*.parquet"):
        cnpj = parcial.stem.rsplit("_", 1)[-1]
        coluna = next((c for c in ("cnpj", "cnpj_rev", "CNPJ_REV") if c in tabela.columns), None)
        if coluna and cnpj.isdigit():
            gravar_parquet(tabela.filter(pl.col(coluna) == cnpj), parcial)


def condicao(filtros: dict) -> pl.Expr:
    expr = pl.lit(True)
    for coluna, valor in filtros.items():
        expr = expr & (pl.col(coluna).is_null() if valor is None else (pl.col(coluna).cast(pl.Utf8) == str(valor)))
    return expr
