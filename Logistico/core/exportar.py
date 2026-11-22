from __future__ import annotations

import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import polars as pl
import xlsxwriter

LIMITE_XLSX = 150_000

_PEDACO = 1024 * 1024


def formato_para(linhas: int) -> str:
    return "xlsx" if linhas <= LIMITE_XLSX else "csv"


def gerar(tabela: pl.DataFrame, nome: str, formato: str) -> Path:
    caminho = Path(tempfile.gettempdir()) / f"{nome}-{uuid.uuid4().hex}.{formato}"
    if formato == "csv":
        tabela.write_csv(
            caminho,
            separator=";",
            decimal_comma=True,
            include_bom=True,
            date_format="%d/%m/%Y",
        )
        return caminho

    opcoes = {"constant_memory": True, "default_date_format": "dd/mm/yyyy"}
    with xlsxwriter.Workbook(caminho, opcoes) as livro:
        aba = livro.add_worksheet()
        aba.write_row(0, 0, tabela.columns, livro.add_format({"bold": True}))
        for numero, linha in enumerate(tabela.iter_rows(), start=1):
            aba.write_row(numero, 0, linha)
    return caminho


def enviar(caminho: Path) -> Iterator[bytes]:
    try:
        with caminho.open("rb") as arquivo:
            while pedaco := arquivo.read(_PEDACO):
                yield pedaco
    finally:
        caminho.unlink(missing_ok=True)
