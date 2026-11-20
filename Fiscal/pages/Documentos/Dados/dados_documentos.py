from datetime import date, timedelta

import polars as pl

from core.dados import data_base, ler


def periodo_padrao() -> tuple[date, date]:
    hoje = data_base()
    return hoje - timedelta(days=30), hoje


def documentos(inicio: date, fim: date, tipos: list[str], filial: str | None, texto: str) -> pl.DataFrame:
    df = ler("documentos").filter(pl.col("emissao").is_between(inicio, fim))
    if tipos:
        df = df.filter(pl.col("tipo").is_in(tipos))
    if filial:
        df = df.filter(pl.col("destinatario") == filial)
    if texto:
        # Busca também pelos itens: quem procura "MARÉ" acha a nota que trouxe o produto.
        por_item = (
            ler("itens_nfe")
            .filter(pl.col("produto").str.contains(texto, literal=True) | pl.col("ncm").str.starts_with(texto))["chave"]
            .unique()
            .to_list()
        )
        df = df.filter(
            pl.col("emitente").str.contains(texto, literal=True)
            | pl.col("chave").str.contains(texto, literal=True)
            | pl.col("numero").cast(pl.String).str.starts_with(texto)
            | pl.col("chave").is_in(por_item)
        )
    return df.sort("emissao", descending=True)


def itens(chave: str) -> pl.DataFrame:
    return ler("itens_nfe").filter(pl.col("chave") == chave).sort("item")


def chave_formatada(chave: str) -> str:
    """Em blocos de 4, como no DANFE."""
    return " ".join(chave[i : i + 4] for i in range(0, len(chave), 4)) if chave.isdigit() else chave
