from datetime import date, timedelta
from pathlib import Path

import polars as pl

from core.compat import ler_parquet

from .informar_pde import GRAVADOS

PASTA_PARQUET = Path(__file__).parents[3] / "data" / "bd_pde"
ARQUIVO = "tb_pde"

DIAS_VISIVEIS = 30

COLUNAS_NUMERICAS = ("PESO_V", "PESO_R", "FAT_SAIDA", "FAT_DEV")

_cache: dict[tuple, pl.DataFrame] = {}


def _preparar(base: pl.DataFrame) -> pl.DataFrame:
    if base.is_empty():
        return base
    base = base.with_columns([pl.col(c).cast(pl.Float64, strict=False) for c in COLUNAS_NUMERICAS if c in base.columns])
    texto = [c for c, tipo in base.schema.items() if tipo == pl.Utf8]
    base = base.with_columns([pl.col(c).str.strip_chars() for c in texto])
    return base.with_columns(
        (pl.col("KM_FIM") - pl.col("KM_INI")).alias("KM_RODADOS"),
        _divisao("QTD_DEV", "QTD_ENT").alias("PERC_DEV"),
        _divisao("PESO_R", "PESO_V").alias("PERC_UTIL"),
        pl.col("DT_SAIDA").cast(pl.Utf8).str.to_date("%Y%m%d", strict=False).alias("DATA_SAIDA"),
    )


def _divisao(numerador: str, denominador: str) -> pl.Expr:
    return (
        pl.when(pl.col(denominador).cast(pl.Float64, strict=False).fill_null(0) != 0)
        .then(pl.col(numerador).cast(pl.Float64, strict=False) / pl.col(denominador).cast(pl.Float64, strict=False))
        .otherwise(pl.lit(None))
    )


def carregar_pde() -> pl.DataFrame:
    caminho = PASTA_PARQUET / f"{ARQUIVO}.parquet"
    if not caminho.is_file():
        return pl.DataFrame()
    chave = (ARQUIVO, caminho.stat().st_mtime_ns)
    if chave not in _cache:
        _cache.clear()
        _cache[chave] = ler_parquet(caminho)
    return _preparar(_com_gravados(_cache[chave]))


def _com_gravados(base: pl.DataFrame) -> pl.DataFrame:
    for (cnpj, romaneio), campos in GRAVADOS.items():
        da_linha = (pl.col("CNPJ_EMP") == cnpj) & (pl.col("ROMANEIO") == romaneio)
        base = base.with_columns(
            [
                pl.when(da_linha).then(pl.lit(v, dtype=base.schema[c])).otherwise(pl.col(c)).alias(c)
                for c, v in campos.items()
            ]
        )
    return base


def janela_recente(base: pl.DataFrame, dias: int = DIAS_VISIVEIS) -> pl.DataFrame:
    if base.is_empty() or "DT_SAIDA" not in base.columns:
        return base
    corte = int((date.today() - timedelta(days=dias)).strftime("%Y%m%d"))
    return base.filter(pl.col("DT_SAIDA") >= corte)


def filtrar_por_revenda(base: pl.DataFrame, revenda: str | None) -> pl.DataFrame:
    if base.is_empty() or not revenda:
        return base
    return base.filter(pl.col("EMPRESA").str.to_uppercase().str.contains(revenda.upper(), literal=True))


def datas_disponiveis(base: pl.DataFrame) -> list[int]:
    if base.is_empty() or "DT_SAIDA" not in base.columns:
        return []
    return sorted((d for d in base["DT_SAIDA"].unique().to_list() if d), reverse=True)


def romaneios_para_editar(base: pl.DataFrame) -> dict[str, dict]:
    if base.is_empty():
        return {}
    escolhas: dict[str, dict] = {}
    for linha in base.sort("ROMANEIO").iter_rows(named=True):
        chave = f"{linha['CNPJ_EMP']}|{linha['ROMANEIO']}"
        escolhas[chave] = {
            "romaneio": linha["ROMANEIO"],
            "placa": (linha.get("PLACA") or "").strip(),
            "dt_saida": linha.get("DT_SAIDA"),
        }
    return escolhas


def linha_do_romaneio(base: pl.DataFrame, chave: str | None) -> dict | None:
    if not chave or base.is_empty() or "|" not in chave:
        return None
    cnpj, romaneio = chave.split("|", 1)
    achadas = base.filter((pl.col("CNPJ_EMP") == cnpj) & (pl.col("ROMANEIO") == romaneio))
    return achadas.row(0, named=True) if achadas.height else None
