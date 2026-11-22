import pandas as pd
import polars as pl

from core.compat import para_pandas

RÓTULOS = {
    "EMPRESA": "Empresa",
    "ROMANEIO": "Romaneio",
    "DT_SAIDA": "Data\nSaída",
    "HR_SAIDA": "Hora\nSaída",
    "DIAS_ROTA": "Dias de\nrota",
    "PLACA": "Placa",
    "MOTORISTA": "Motorista",
    "AJUDANTE_1": "Ajudante 1",
    "AJUDANTE_2": "Ajudante 2",
    "ROTA": "Rota",
    "OBS": "Obs",
    "PESO_V": "Peso\nMax",
    "PESO_R": "Peso\nRom",
    "PERC_UTIL": "% Util",
    "QTD_ENT": "Qtd\nEnt",
    "QTD_NF": "Qtd\nNf",
    "FAT_SAIDA": "Fat Saída",
    "QTD_DEV": "Qtd\nDev",
    "FAT_DEV": "Fat Dev",
    "PERC_DEV": "% Dev",
    "DT_FIM": "Data\nChegada",
    "HR_FIM": "Hora\nChegada",
    "KM_INI": "Km\nSaída",
    "KM_FIM": "Km\nChegada",
    "KM_RODADOS": "Km\nRodados",
}

COLUNAS = [
    "EMPRESA",
    "ROMANEIO",
    "DT_SAIDA",
    "HR_SAIDA",
    "DIAS_ROTA",
    "PLACA",
    "MOTORISTA",
    "AJUDANTE_1",
    "AJUDANTE_2",
    "ROTA",
    "OBS",
    "PESO_V",
    "PESO_R",
    "PERC_UTIL",
    "QTD_ENT",
    "QTD_NF",
    "FAT_SAIDA",
    "QTD_DEV",
    "FAT_DEV",
    "PERC_DEV",
    "DT_FIM",
    "HR_FIM",
    "KM_INI",
    "KM_FIM",
    "KM_RODADOS",
]

COLUNAS_MOEDA = {"FAT_SAIDA", "FAT_DEV"}
COLUNAS_PERCENTUAL = {"PERC_UTIL", "PERC_DEV"}
COLUNAS_DATA = {"DT_SAIDA", "DT_FIM"}
COLUNAS_INTEIRAS = {"PESO_V", "PESO_R", "KM_INI", "KM_FIM", "KM_RODADOS"}
COLUNAS_HORA = {"HR_SAIDA", "HR_FIM"}

COLUNAS_DESTACADAS = ("DT_SAIDA", "DIAS_ROTA", "QTD_ENT", "QTD_NF")


def rotulo_uma_linha(coluna: str) -> str:
    return RÓTULOS.get(coluna, coluna).replace("\n", " ")


def moeda(valor) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    return f"R$ {float(valor):,.2f}".translate(str.maketrans(",.", ".,"))


def numero(valor, casas: int = 0) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    try:
        return f"{float(valor):,.{casas}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    except (TypeError, ValueError):
        return str(valor)


def percentual(valor) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    return f"{numero(float(valor) * 100, 2)}%"


def data_aaaammdd(valor) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    texto = str(int(valor)) if not isinstance(valor, str) else valor.strip()
    if len(texto) != 8 or not texto.isdigit():
        return ""
    return f"{texto[6:8]}/{texto[4:6]}/{texto[0:4]}"


def rotulo_romaneio_editar(romaneio: str, placa: str, dt_saida) -> str:
    data = data_aaaammdd(dt_saida)
    seq = romaneio[-3:] if len(romaneio) == 11 else ""
    prefixo = f"{data} nº {seq}" if data and seq else romaneio
    return f"{prefixo} -- {placa}" if placa else prefixo


def hora(valor) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    texto = str(valor).strip()
    return "" if texto in ("", "00:00") else texto


def construir_df(base: pl.DataFrame) -> pd.DataFrame:
    if base.is_empty():
        return pd.DataFrame(columns=[RÓTULOS[c] for c in COLUNAS])
    tabela = base.select([c for c in COLUNAS if c in base.columns]).sort(
        ["DT_SAIDA", "ROMANEIO"], descending=[True, False], nulls_last=True
    )
    tabela = tabela.with_columns(
        pl.col(coluna).fill_null("") for coluna, tipo in tabela.schema.items() if tipo == pl.Utf8
    )
    pandas_df = para_pandas(tabela)
    for coluna in COLUNAS_DATA & set(pandas_df.columns):
        pandas_df[coluna] = pandas_df[coluna].map(data_aaaammdd)
    for coluna in COLUNAS_MOEDA & set(pandas_df.columns):
        pandas_df[coluna] = pandas_df[coluna].map(moeda)
    for coluna in COLUNAS_PERCENTUAL & set(pandas_df.columns):
        pandas_df[coluna] = pandas_df[coluna].map(percentual)
    for coluna in COLUNAS_INTEIRAS & set(pandas_df.columns):
        pandas_df[coluna] = pandas_df[coluna].map(lambda v: numero(v, 0))
    for coluna in COLUNAS_HORA & set(pandas_df.columns):
        pandas_df[coluna] = pandas_df[coluna].map(hora)
    return pandas_df.rename(columns={c: RÓTULOS.get(c, c) for c in pandas_df.columns})


def estilos_destaque(pandas_df: pd.DataFrame, cor: str) -> list[dict]:
    colunas = [RÓTULOS[c] for c in COLUNAS_DESTACADAS if RÓTULOS[c] in pandas_df.columns]
    if not colunas or pandas_df.empty:
        return []
    return [{"cols": colunas, "style": {"background-color": cor}}]
