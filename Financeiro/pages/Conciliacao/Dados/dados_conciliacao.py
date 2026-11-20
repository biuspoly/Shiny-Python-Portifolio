from datetime import date

import polars as pl

from core.dados import ler

SITUACOES = ["Conciliado", "Só no banco", "Só no ERP"]


def meses() -> list[date]:
    return sorted(ler("extrato_banco")["data"].dt.truncate("1mo").unique().to_list(), reverse=True)


def _numerar(df: pl.DataFrame) -> pl.DataFrame:
    # Dois lançamentos iguais no mesmo dia (mesma conta e valor) casam um a um:
    # o 1o do banco com o 1o do ERP, o 2o com o 2o.
    return df.with_columns(pl.int_range(pl.len()).over("conta", "data", "valor").alias("ordem"))


def conciliar(conta: str | None, mes: date) -> pl.DataFrame:
    """Casa extrato e ERP por conta, data e valor, sem depender de código comum."""
    fim = date(mes.year + mes.month // 12, mes.month % 12 + 1, 1)
    banco = ler("extrato_banco").filter(pl.col("data") >= mes, pl.col("data") < fim)
    erp = ler("lancamentos_erp").filter(pl.col("data") >= mes, pl.col("data") < fim)
    if conta:
        banco = banco.filter(pl.col("conta") == conta)
        erp = erp.filter(pl.col("conta") == conta)
    chave = ["conta", "data", "valor", "ordem"]
    juntos = _numerar(banco.select("conta", "data", "valor", "descricao")).join(
        _numerar(erp.select("conta", "data", "valor", "historico")), on=chave, how="full", coalesce=True
    )
    return (
        juntos.with_columns(
            pl.when(pl.col("descricao").is_not_null() & pl.col("historico").is_not_null())
            .then(pl.lit("Conciliado"))
            .when(pl.col("descricao").is_not_null())
            .then(pl.lit("Só no banco"))
            .otherwise(pl.lit("Só no ERP"))
            .alias("situacao")
        )
        .drop("ordem")
        .sort("data", "conta", "valor")
    )


def pendencias_por_tipo(df: pl.DataFrame) -> pl.DataFrame:
    so_banco = df.filter(pl.col("situacao") == "Só no banco").with_columns(
        pl.col("descricao").str.replace(r"\s+LOTE.*$", "").alias("tipo")
    )
    return so_banco.group_by("tipo").agg(pl.len().alias("qtd"), pl.col("valor").sum()).sort("qtd", descending=True)


def contas() -> list[str]:
    return ler("contas")["conta"].to_list()
