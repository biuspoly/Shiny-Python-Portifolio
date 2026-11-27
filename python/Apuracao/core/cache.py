from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

from core.colunas_do_control import com_os_nomes_novos
from core.compat import ler_parquet

PASTA = Path(__file__).resolve().parents[1] / "data" / "bd_fiscal"
_lidos: dict[str, tuple[int, pl.DataFrame]] = {}


def pasta_de(nome: str) -> Path:
    """No original, a tabela fica na pasta deste app ou na do Fiscal; no portfólio, tudo na deste."""
    return PASTA


def momento(nome: str) -> int:
    try:
        return (PASTA / f"{nome}.parquet").stat().st_mtime_ns
    except OSError:
        return 0


def ler(nome: str) -> pl.DataFrame:
    atual = momento(nome)
    guardado = _lidos.get(nome)
    if guardado is None or guardado[0] != atual:
        guardado = (
            atual,
            com_os_nomes_novos(nome, ler_parquet(PASTA / f"{nome}.parquet")) if atual else pl.DataFrame(),
        )
        _lidos[nome] = guardado
    return guardado[1]


def colunas(nome: str) -> list[str]:
    try:
        return list(pq.read_schema(PASTA / f"{nome}.parquet").names)
    except OSError:
        return []


def periodo(de: date | None, ate: date | None, coluna: str = "emissao") -> pl.Expr:
    condicao = pl.lit(True)
    if de:
        condicao = condicao & (pl.col(coluna) >= pl.lit(de).cast(pl.Datetime))
    if ate:
        condicao = condicao & (pl.col(coluna) < pl.lit(ate).cast(pl.Datetime) + pl.duration(days=1))
    return condicao


# scan_parquet não funciona no navegador: a consulta "preguiçosa" parte do arquivo já lido.
def consulta(nome: str) -> pl.LazyFrame | None:
    return ler(nome).lazy() if momento(nome) and colunas(nome) else None


def filtrado(nome: str, filtro: pl.Expr | None = None, so: list[str] | None = None) -> pl.DataFrame:
    if not momento(nome) or not colunas(nome):
        return pl.DataFrame()
    consulta_ = ler(nome).lazy()
    if filtro is not None:
        consulta_ = consulta_.filter(filtro)
    if so:
        existem = set(colunas(nome))
        consulta_ = consulta_.select([c for c in so if c in existem])
    return consulta_.collect()
