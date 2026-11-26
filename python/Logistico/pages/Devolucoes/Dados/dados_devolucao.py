from datetime import date
from functools import lru_cache
from pathlib import Path

import polars as pl

from core.compat import ler_parquet
from core.config import REVENDAS_CNPJ

PASTA_PARQUET = Path(__file__).parents[3] / "data" / "bd_shiny_bruto" / "devolucoes"

GRUPOS = ["atual", "ultimo", "penultimo", "antepenultimo", "historico"]

MESES_PT = {
    1: "jan",
    2: "fev",
    3: "mar",
    4: "abr",
    5: "mai",
    6: "jun",
    7: "jul",
    8: "ago",
    9: "set",
    10: "out",
    11: "nov",
    12: "dez",
}
MESES_PT_INV = {nome: numero for numero, nome in MESES_PT.items()}

REVENDA_CNPJ = REVENDAS_CNPJ


def cnpjs_da_revenda(revenda: str | None) -> list[str]:
    if not revenda:
        return list(REVENDA_CNPJ.values())
    return [REVENDA_CNPJ[revenda]] if revenda in REVENDA_CNPJ else []


def _rotulo_do_mes(mes: str, hoje: date) -> str:
    if mes == hoje.strftime("%Y%m"):
        return "Mês Atual"
    return f"{MESES_PT[int(mes[4:])]}/{mes[:4]}"


def _numero_do_mes(rotulo: str, hoje: date) -> str | None:
    if rotulo == "Mês Atual":
        return hoje.strftime("%Y%m")
    try:
        nome_mes, ano = rotulo.split("/")
        return f"{int(ano):04d}{MESES_PT_INV[nome_mes]:02d}"
    except (ValueError, KeyError):
        return None


def _meses_do_arquivo(caminho: Path) -> set[str]:
    try:
        return _meses_em_cache(str(caminho), caminho.stat().st_mtime_ns)
    except OSError:
        return set()


@lru_cache(maxsize=128)
def _meses_em_cache(caminho: str, marca: int) -> frozenset[str]:
    return frozenset(ler_parquet(caminho, columns=["MES"])["MES"].unique().drop_nulls().to_list())


def _arquivos_da_revenda(cnpjs: list[str]) -> list[Path]:
    caminhos = []
    for cnpj in cnpjs:
        for grupo in GRUPOS:
            caminho = PASTA_PARQUET / f"tb_vend_dev_{cnpj}_{grupo}.parquet"
            if caminho.exists():
                caminhos.append(caminho)
    return caminhos


def listar_meses_disponiveis() -> list[str]:
    hoje = date.today()
    meses: set[str] = set()
    for caminho in _arquivos_da_revenda(list(REVENDA_CNPJ.values())):
        meses |= _meses_do_arquivo(caminho)
    rotulos = [_rotulo_do_mes(mes, hoje) for mes in sorted(meses, reverse=True)]
    if "Mês Atual" not in rotulos:
        rotulos.insert(0, "Mês Atual")
    return rotulos


def _carregar_grupos(cnpjs: list[str], meses: set[str] | None = None) -> pl.DataFrame:
    partes = []
    for caminho in _arquivos_da_revenda(cnpjs):
        if meses is not None and not (meses & _meses_do_arquivo(caminho)):
            continue
        partes.append(ler_parquet(caminho))
    if not partes:
        return pl.DataFrame()
    return pl.concat(partes, how="diagonal_relaxed")


def _com_rotulo_do_mes(base: pl.DataFrame, hoje: date) -> pl.DataFrame:
    if base.height == 0 or "MES" not in base.columns:
        return base
    return base.with_columns(
        pl.when(pl.col("MES") == hoje.strftime("%Y%m"))
        .then(pl.lit("Mês Atual"))
        .otherwise(
            pl.col("MES").str.slice(4, 2).cast(pl.Int32).replace_strict(MESES_PT, default=None)
            + pl.lit("/")
            + pl.col("MES").str.slice(0, 4)
        )
        .alias("MES_ATUAL")
    )


def _juntar_empresa(base: pl.DataFrame) -> pl.DataFrame:
    empresas = ler_parquet(PASTA_PARQUET / "tb_empresas.parquet").rename({"EMPRESA": "Empresa", "CNPJ_EMP": "CNPJ_REV"})
    base = base.join(empresas, on="CNPJ_REV", how="left")
    return base.with_columns(
        pl.when(pl.col("GRUPO_REV").is_null() | (pl.col("GRUPO_REV") == ""))
        .then(pl.col("Empresa"))
        .otherwise(pl.col("GRUPO_REV"))
        .alias("GRUPO_REV")
    )


def so_primeira_maiuscula(coluna: str) -> pl.Expr:
    return pl.col(coluna).str.slice(0, 1).str.to_uppercase() + pl.col(coluna).str.slice(1).str.to_lowercase()


def _cidade_uf() -> pl.Expr:
    cidade = so_primeira_maiuscula("CIDADE").str.strip_chars()
    return (
        pl.when(cidade.is_null() | (cidade == ""))
        .then(None)
        .when(pl.col("UF").is_null() | (pl.col("UF") == ""))
        .then(cidade)
        .otherwise(cidade + pl.lit(" - ") + pl.col("UF"))
        .alias("CIDADE_UF")
    )


def _calcular_campos_geral_dev(base: pl.DataFrame) -> pl.DataFrame:
    base = base.with_columns(pl.col("COD_PED").cast(pl.Int64))

    base = base.with_columns(
        pl.concat_str([pl.col("MOT"), pl.lit(" - "), pl.col("NOME_MOT")]).alias("COD_MOTORISTA"),
        pl.concat_str([pl.col("COD_VEN"), pl.lit(" - "), pl.col("NOME_VEN")]).alias("COD_VENDEDOR"),
        pl.concat_str([pl.col("CLI").cast(pl.Utf8), pl.lit(" - "), pl.col("FANTASIA")]).alias("COD_CLIENTE"),
        pl.when(pl.col("VALOR DEVOLUCAO") > 0).then(pl.lit("Sim")).otherwise(pl.lit("Não")).alias("Retorno"),
    )

    if "UF" not in base.columns:
        base = base.with_columns(pl.lit(None, dtype=pl.Utf8).alias("UF"))
    base = base.with_columns(_cidade_uf())

    if "DATA_BAIXA_ROM" not in base.columns:
        base = base.with_columns(pl.lit(None, dtype=pl.Utf8).alias("DATA_BAIXA_ROM"))

    if "DTA_ENTREGA" not in base.columns:
        base = base.with_columns(pl.lit(None, dtype=pl.Utf8).alias("DTA_ENTREGA"))

    base_valida = base.filter(
        (pl.col("VALOR VENDA") > 0) & (pl.col("Romaneio aberto") == "Não") & (pl.col("VALOR DEVOLUCAO") == 0)
    )
    ult_compra = base_valida.group_by(["CLI", "CNPJ_REV", "MES_ATUAL"]).agg(
        pl.col("DATA_VENDA").max().alias("ULT_COMPRA")
    )
    return base.join(ult_compra, on=["CLI", "CNPJ_REV", "MES_ATUAL"], how="left")


def carregar_geral_dev(revenda: str | None, meses_selecionados: list[str]) -> pl.DataFrame:
    if not meses_selecionados:
        return pl.DataFrame()
    hoje = date.today()
    meses = {mes for mes in (_numero_do_mes(rotulo, hoje) for rotulo in meses_selecionados) if mes}
    if not meses:
        return pl.DataFrame()
    base = _carregar_grupos(cnpjs_da_revenda(revenda), meses)
    if base.height == 0:
        return base
    base = base.filter(pl.col("MES").is_in(list(meses)))
    base = _com_rotulo_do_mes(base, hoje)
    base = _juntar_empresa(base)
    return _calcular_campos_geral_dev(base)


def geral_dev_mensal(revenda: str | None) -> pl.DataFrame:
    base = _carregar_grupos(cnpjs_da_revenda(revenda))
    if base.height == 0:
        return base
    base = _com_rotulo_do_mes(base, date.today())
    base = _juntar_empresa(base)
    return (
        base.filter(pl.col("VALOR DEVOLUCAO") > 0)
        .group_by(["Empresa", "GRUPO_REV", "MES_ATUAL", "MES"])
        .agg(pl.col("VALOR DEVOLUCAO").sum().alias("Devolução"))
    )


def geral_cx_mensal(revenda: str | None) -> pl.DataFrame:
    base = _carregar_grupos(cnpjs_da_revenda(revenda))
    if base.height == 0:
        return base
    base = _com_rotulo_do_mes(base, date.today())
    base = _juntar_empresa(base)
    return (
        base.filter(pl.col("DEVOLUCAO_CX") > 0)
        .group_by(["Empresa", "GRUPO_REV", "MES_ATUAL", "MES"])
        .agg(pl.col("DEVOLUCAO_CX").sum().alias("Devolução"))
    )
