"""Contornos para o Python do navegador (Shinylive: Pyodide, 32 bits).

O polars empacotado ali entra em pânico ("capacity overflow") em três casos que
no servidor funcionam: o .pl() direto do DuckDB, colunas Decimal e o
DataFrame.to_pandas() com texto. As funções abaixo fazem o mesmo trabalho por
outro caminho, com o mesmo resultado nos dois ambientes.
"""

import pandas as pd
import polars as pl
import pyarrow.parquet as pq


def polars_de_duckdb(relacao) -> pl.DataFrame:
    """Resultado do DuckDB em polars, via Arrow, com Decimal virando Float64
    (SUM de inteiro volta Decimal no DuckDB)."""
    # O nome do método mudou entre versões do DuckDB (o do Shinylive é o 1.1).
    buscar = getattr(relacao, "fetch_arrow_table", None) or relacao.to_arrow_table
    tabela = pl.from_arrow(buscar())
    return tabela.with_columns(pl.col(pl.Decimal).cast(pl.Float64))


def para_pandas(tabela: pl.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({coluna: tabela[coluna].to_list() for coluna in tabela.columns})


def ler_parquet(caminho, columns: list[str] | None = None) -> pl.DataFrame:
    """pl.read_parquet quebra no navegador; o pyarrow lê o mesmo arquivo."""
    return pl.from_arrow(pq.read_table(caminho, columns=columns))


def gravar_parquet(tabela: pl.DataFrame, caminho) -> None:
    """DataFrame.write_parquet não existe no polars do navegador; o pyarrow grava o mesmo arquivo."""
    import pyarrow as pa

    pq.write_table(pa.table({coluna: tabela[coluna].to_list() for coluna in tabela.columns}), caminho)
