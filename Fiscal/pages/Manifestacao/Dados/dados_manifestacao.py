from datetime import timedelta

import polars as pl

from core.dados import data_base, ler

# Confirmação, desconhecimento ou operação não realizada: até 180 dias da autorização.
PRAZO_DIAS = 180
SITUACOES = ["Sem manifestação", "Ciência", "Confirmada", "Desconhecida", "Não realizada"]


def nfe_recebidas() -> pl.DataFrame:
    hoje = data_base()
    return (
        ler("documentos")
        .filter(pl.col("tipo") == "NF-e", pl.col("situacao_sefaz") == "Autorizada")
        .with_columns(
            (pl.col("emissao") + timedelta(days=PRAZO_DIAS)).alias("prazo"),
            (pl.col("emissao") + timedelta(days=PRAZO_DIAS) - pl.lit(hoje)).dt.total_days().alias("dias_restantes"),
        )
        .select(
            "chave", "numero", "emitente", "destinatario", "emissao", "valor", "manifestacao", "prazo", "dias_restantes"
        )
        .sort("manifestacao", "emissao")
    )
