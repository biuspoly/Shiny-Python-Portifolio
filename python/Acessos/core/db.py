"""O banco de acessos. No original, um MySQL remoto lido e gravado ao vivo; no portfólio, as
mesmas consultas rodam no DuckDB sobre tabelas fictícias (data/bd_acessos/*.parquet), num banco
em memória desta sessão: o que a tela grava vale até a página fechar."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import duckdb
import polars as pl

from core.compat import polars_de_duckdb

PASTA = Path(__file__).resolve().parents[1] / "data" / "bd_acessos"
FORMATO_DATA = "%d/%m/%Y %H:%M:%S"
_CONEXAO: list[duckdb.DuckDBPyConnection] = []


def _banco() -> duckdb.DuckDBPyConnection:
    if _CONEXAO:
        return _CONEXAO[0]
    con = duckdb.connect(":memory:")
    # Funções do MySQL que as consultas originais usam.
    con.execute(f"CREATE MACRO STR_TO_DATE(s, f) AS strptime(s, '{FORMATO_DATA}')")
    try:  # DATE() existe no DuckDB recente, não no 1.1 do Shinylive
        con.execute("SELECT DATE(TIMESTAMP '2026-01-01 10:00:00')")
    except duckdb.CatalogException:
        con.execute("CREATE MACRO DATE(x) AS CAST(x AS DATE)")
    for arquivo in sorted(PASTA.glob("*.parquet")):
        con.execute(f"CREATE TABLE {arquivo.stem} AS SELECT * FROM read_parquet('{arquivo.as_posix()}')")
    con.execute("CREATE UNIQUE INDEX dash_group_chave ON dash_group (nomeGrupo, id)")
    # Os acessos fictícios terminam no dia em que foram gerados; o site é refeito por semana.
    # Deslocados para terminar agora, as janelas "últimos 7/30 dias" não esvaziam.
    ultimo = con.execute(f"SELECT max(strptime(dataAcesso, '{FORMATO_DATA}')) FROM logacesso").fetchone()[0]
    if ultimo is not None:
        # Em dias inteiros: mantém o horário de cada acesso (no navegador o relógio é UTC).
        atraso = (date.today() - ultimo.date()).days
        con.execute(
            f"UPDATE logacesso SET dataAcesso = strftime(strptime(dataAcesso, '{FORMATO_DATA}') "
            f"+ INTERVAL ({atraso}) DAY, '{FORMATO_DATA}')"
        )
    _CONEXAO.append(con)
    return con


def _para_duckdb(sql: str) -> str:
    # ":nome" (parâmetro do SQLAlchemy) vira "$nome"; "INSERT IGNORE" vira "INSERT OR IGNORE".
    sql = re.sub(r"(?<![:\w]):(\w+)", r"$\1", sql)
    return sql.replace("INSERT IGNORE", "INSERT OR IGNORE")


def consulta(sql: str, parametros: dict | None = None) -> pl.DataFrame:
    return polars_de_duckdb(_banco().execute(_para_duckdb(sql), parametros or {}))


def executar(sql: str, parametros: dict | None = None) -> None:
    _banco().execute(_para_duckdb(sql), parametros or {})
