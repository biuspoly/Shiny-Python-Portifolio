import json
from datetime import date
from functools import cache
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

PASTA_DADOS = Path(__file__).resolve().parent.parent / "data"


@cache
def ler(nome: str) -> pl.DataFrame:
    # Lido pelo pyarrow e convertido: no Shinylive o pl.read_parquet do polars
    # empacotado quebra (a parte compilada não bate com a parte em Python).
    return pl.from_arrow(pq.read_table(PASTA_DADOS / f"{nome}.parquet"))


@cache
def data_base() -> date:
    """O "hoje" dos dados fictícios: o dia em que o gerador rodou."""
    with open(PASTA_DADOS / "_gerado_em.json", encoding="utf-8") as arq:
        return date.fromisoformat(json.load(arq)["data_base"])
