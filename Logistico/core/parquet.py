"""Gravação de cache .parquet (no original, pelo DuckDB, com espelho no MySQL). No portfólio, pelo pyarrow."""

from pathlib import Path

import polars as pl

from core.compat import gravar_parquet


def sobrescreve_parquet(nome: str, tabela: pl.DataFrame, pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    gravar_parquet(tabela, pasta / f"{nome}.parquet")
