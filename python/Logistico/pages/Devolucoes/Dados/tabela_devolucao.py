import html

import pandas as pd
import polars as pl
from shiny.ui import HTML

from core.compat import para_pandas
from core.cores import DEV_RETORNO_NEGATIVO, DEV_RETORNO_NEUTRO, DEV_RETORNO_POSITIVO


def _moeda(valor) -> str:
    if pd.isna(valor):
        return ""
    texto = f"R$ {valor:,.2f}"
    return texto.translate(str.maketrans(",.", ".,"))


def _numero(valor) -> str:
    if pd.isna(valor):
        return ""
    return f"{valor:,.0f}".replace(",", ".")


def _percentual_0a100(valor) -> str:
    if pd.isna(valor):
        return ""
    return f"{valor:.2f}%".replace(".", ",")


def _percentual_razao(valor) -> str:
    if pd.isna(valor):
        return ""
    return f"{valor * 100:.2f}%".replace(".", ",")


def _cor_retorno(valor) -> str:
    if pd.isna(valor):
        return ""
    if valor < 2:
        cor = DEV_RETORNO_POSITIVO
    elif valor > 2:
        cor = DEV_RETORNO_NEGATIVO
    else:
        cor = DEV_RETORNO_NEUTRO
    return f"background-color: {cor};"


def construir_consolidada_df(tabela: pl.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    if tabela.height == 0:
        return pd.DataFrame(), []
    tem_grupo = "_grupo" in tabela.columns
    pandas_df = para_pandas(tabela)
    pandas_df["Vendas"] = pandas_df["Vendas"].map(_moeda)
    pandas_df["Devolução"] = pandas_df["Devolução"].map(_moeda)
    for coluna in ("Num de pedidos", "Pedidos devolvidos"):
        if coluna in pandas_df.columns:
            pandas_df[coluna] = pandas_df[coluna].map(_numero)

    estilos = []
    if tem_grupo:
        linhas_grupo = [i for i, v in enumerate(tabela["_grupo"]) if v]
        if linhas_grupo:
            estilos.append(
                {
                    "rows": linhas_grupo,
                    "style": {"font-weight": "bold", "background-color": "rgba(56, 116, 171, 0.08)"},
                }
            )
            pandas_df["Data do pedido"] = [
                HTML(
                    f'<span class="dev-grupo-data" tabindex="0" role="button" '
                    f'data-grupo-data="{html.escape(data_bruta, quote=True)}">{texto}</span>'
                )
                if grupo
                else texto
                for texto, grupo, data_bruta in zip(
                    pandas_df["Data do pedido"], tabela["_grupo"], tabela["_data_bruta"]
                )
            ]
    for posicao, valor in enumerate(tabela["Taxa de retorno"]):
        cor = _cor_retorno(valor)
        if cor:
            estilos.append({"rows": [posicao], "cols": ["Taxa de retorno"], "style": _css_para_dict(cor)})
    pandas_df["Taxa de retorno"] = pandas_df["Taxa de retorno"].map(_percentual_0a100)
    if tem_grupo:
        pandas_df = pandas_df.drop(columns=["_grupo", "_data_bruta"])
    return pandas_df, estilos


def _css_para_dict(declaracoes: str) -> dict[str, str]:
    resultado = {}
    for parte in declaracoes.strip().rstrip(";").split(";"):
        if ":" not in parte:
            continue
        chave, valor = parte.split(":", 1)
        resultado[chave.strip()] = valor.strip()
    return resultado


def construir_detalhada_df(tabela: pl.DataFrame) -> pd.DataFrame:
    if tabela.height == 0:
        return pd.DataFrame()
    pandas_df = para_pandas(tabela)
    pandas_df["Devolução"] = pandas_df["Devolução"].map(_moeda)
    return pandas_df.drop(columns=["CHAVE_VDI"])


def tabela_grupo(
    base: pl.DataFrame,
    coluna_cod: str,
    coluna_nome: str,
    rotulo_nome: str,
    coluna_venda: str,
    coluna_dev: str,
    rotulo_venda: str,
    rotulo_dev: str,
    incluir_num_pedidos: bool,
) -> pl.DataFrame:
    aggs = [
        pl.col(coluna_venda).sum().alias(rotulo_venda),
        pl.col(coluna_dev).sum().alias(rotulo_dev),
    ]
    if incluir_num_pedidos:
        aggs.append(pl.col("COD_PED").n_unique().alias("Num de pedidos"))

    tabela = (
        base.group_by([coluna_cod, coluna_nome])
        .agg(*aggs)
        .rename({coluna_cod: "Cod", coluna_nome: rotulo_nome})
        .with_columns(pl.col(rotulo_nome).str.to_titlecase())
    )
    return tabela.with_columns(
        pl.when(pl.col(rotulo_venda) == 0)
        .then(pl.lit(0.0))
        .otherwise(pl.col(rotulo_dev) / pl.col(rotulo_venda))
        .alias("Taxa de retorno")
    ).sort("Taxa de retorno", descending=True)


def construir_grupo_df(tabela: pl.DataFrame, colunas_moeda: list[str]) -> pd.DataFrame:
    if tabela.height == 0:
        return pd.DataFrame()
    pandas_df = para_pandas(tabela)
    for coluna in colunas_moeda:
        if coluna in pandas_df.columns:
            pandas_df[coluna] = pandas_df[coluna].map(_moeda)
    if "Taxa de retorno" in pandas_df.columns:
        pandas_df["Taxa de retorno"] = pandas_df["Taxa de retorno"].map(_percentual_razao)
    for coluna in pandas_df.columns:
        if coluna == "Cod" or coluna in colunas_moeda:
            continue
        if pd.api.types.is_numeric_dtype(pandas_df[coluna]):
            pandas_df[coluna] = pandas_df[coluna].map(_numero)
    return pandas_df
