"""Leitura de .parquet com medição de tempo: no portfólio só a leitura."""

from core.compat import ler_parquet as _ler


def ler_parquet(caminho, **kwargs):
    return _ler(caminho, **kwargs)
