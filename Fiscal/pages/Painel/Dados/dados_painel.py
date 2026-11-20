from datetime import date

import polars as pl

from core.dados import data_base, ler


def meses() -> list[date]:
    return sorted(ler("documentos")["emissao"].dt.truncate("1mo").unique().to_list(), reverse=True)


def do_mes(mes: date, filial: str | None) -> pl.DataFrame:
    df = ler("documentos").filter(pl.col("emissao").dt.truncate("1mo") == mes)
    return df.filter(pl.col("destinatario") == filial) if filial else df


def por_dia(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.group_by("recebida_em", "tipo")
        .len()
        .pivot(on="tipo", index="recebida_em", values="len")
        .fill_null(0)
        .sort("recebida_em")
    )


def a_manifestar(filial: str | None) -> int:
    df = ler("documentos").filter(
        pl.col("tipo") == "NF-e",
        pl.col("manifestacao").is_in(["Sem manifestação", "Ciência"]),
        pl.col("situacao_sefaz") == "Autorizada",
    )
    return (df.filter(pl.col("destinatario") == filial) if filial else df).height


def pendentes_escrituracao(filial: str | None) -> pl.DataFrame:
    df = ler("documentos").filter(
        ~pl.col("escriturada"), pl.col("situacao_sefaz") == "Autorizada", pl.col("recebida_em") <= data_base()
    )
    return df.filter(pl.col("destinatario") == filial) if filial else df
