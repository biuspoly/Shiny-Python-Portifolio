from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import pyarrow.parquet as pq
from dateutil.relativedelta import relativedelta

from core.compat import para_pandas
from core.config import CNPJ_PADRAO

PASTA_PARQUET = Path(__file__).parents[3] / "data" / "bd_comercial"

GRUPOS = ["atual", "ultimo", "penultimo", "antepenultimo", "historico"]


def cnpjs_da_revenda(revenda: str | None) -> list[str]:
    return [CNPJ_PADRAO]


def _grupo_do_mes(mes: str, hoje: date) -> str:
    ano, mm = int(mes[:4]), int(mes[4:6])
    meses_atras = (hoje.year - ano) * 12 + (hoje.month - mm)
    if meses_atras <= 0:
        return "atual"
    if meses_atras == 1:
        return "ultimo"
    if meses_atras == 2:
        return "penultimo"
    if meses_atras == 3:
        return "antepenultimo"
    return "historico"


def _carregar_grupos(cnpjs: list[str], grupos: set[str]) -> pl.DataFrame:
    partes = []
    for cnpj in cnpjs:
        for grupo in grupos:
            caminho = PASTA_PARQUET / f"tb_curva_abc_{cnpj}_{grupo}.parquet"
            if caminho.exists():
                partes.append(pl.from_arrow(pq.read_table(caminho)))
    if not partes:
        return pl.DataFrame()
    return pl.concat(partes, how="diagonal_relaxed")


def meses_disponiveis(revenda: str | None) -> list[str]:
    hoje = date.today()
    mes_atual = date(hoje.year, hoje.month, 1)
    return [(mes_atual - relativedelta(months=i)).strftime("%Y%m") for i in range(12)]


def consulta(revenda: str | None, mes: str) -> pd.DataFrame:
    hoje = date.today()
    cnpjs = cnpjs_da_revenda(revenda)
    grupo = _grupo_do_mes(str(mes), hoje)
    dados_pl = _carregar_grupos(cnpjs, {grupo})
    if dados_pl.height:
        dados_pl = dados_pl.filter(pl.col("MES").cast(pl.Utf8) == str(mes))
    dados = para_pandas(dados_pl)
    if dados.empty:
        return dados

    dados.columns = [str(coluna).upper() for coluna in dados.columns]
    dados["FATURAMENTO"] = pd.to_numeric(dados["FATURAMENTO"], errors="coerce").fillna(0)
    clientes = dados.groupby("CODCLI", dropna=False)["FATURAMENTO"].sum().sort_values(ascending=False).reset_index()
    total = clientes["FATURAMENTO"].sum()
    clientes["ORDEM"] = np.arange(1, len(clientes) + 1)
    if total:
        clientes["PERC_INDIVIDUAL"] = clientes["FATURAMENTO"].div(total).mul(100).round(2)
        clientes["PERC_ACUMULADO"] = clientes["FATURAMENTO"].cumsum().div(total).mul(100).round(2)
    else:
        clientes["PERC_INDIVIDUAL"] = 0.0
        clientes["PERC_ACUMULADO"] = 0.0
    dados = dados.merge(clientes[["CODCLI", "ORDEM", "PERC_INDIVIDUAL", "PERC_ACUMULADO"]], on="CODCLI", how="left")
    dados["CLIENTE"] = dados["CODCLI"].astype(str) + " - " + dados["NOME"].fillna("").astype(str)
    return dados.sort_values(["ORDEM", "FATURAMENTO"], ascending=[True, False]).reset_index(drop=True)
