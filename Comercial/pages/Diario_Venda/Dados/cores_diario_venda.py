COR_META = {"color": "#D71920", "background-color": "#FAEBEB"}
COR_META_BOLD = {**COR_META, "font-weight": "bold"}
COR_META_REV = {"color": "#000000", "background-color": "#A1C8E4", "font-weight": "bold"}


COR_META_TITULO = {"color": "#FFFFFF", "background-color": "#0D6ABF", "font-weight": "bold"}
COR_META_DIFERENCA_NEGATIVA = {"color": "#D71920"}


COR_META_ABP_GRUPO = {"color": "#FFFFFF", "background-color": "#04573E", "font-weight": "bold"}

_CORES_MARCA = {
    "MARÉ": {"color": "#FFFFFF", "background-color": "#0B6E79"},
    "CORAL": {"color": "#FFFFFF", "background-color": "#B5532F"},
    "JANGADA": {"color": "#FFFFFF", "background-color": "#6B8E23"},
    "CORAL ULTRA": {"color": "#FFFFFF", "background-color": "#6D4AAE"},
    "MARÉ ULTIMATE": {"color": "#FFFFFF", "background-color": "#475569"},
    "BRISA": {"color": "#1A1A1A", "background-color": "#9CC3E6"},
    "FAROL": {"color": "#FFFFFF", "background-color": "#A23B72"},
    "SERENA": {"color": "#FFFFFF", "background-color": "#2B6CB0"},
}
_COR_TOTAL_VOLUME = {"color": "#000000", "font-weight": "bold"}
_COR_SEGMENTO_2_RGB = {"color": "#FFFFFF", "background-color": "#3F3F46"}
_COR_SEGMENTO_3_DEFAULT = {"color": "#000000", "background-color": "#FFFFFF"}
_COR_SKU_DEFAULT = {"color": "#000000", "background-color": "#CFF7D4"}
_COR_INDICADOR_DEFAULT = {"color": "#000000", "background-color": "#e4f2f7"}


def cor_categoria_dv(categoria: str, nivel: str) -> dict[str, str] | None:

    if nivel == "TOTAL" and categoria == "VOLUME TOTAL":
        return _COR_TOTAL_VOLUME
    if nivel == "MARCA" and categoria in _CORES_MARCA:
        return _CORES_MARCA[categoria]
    if nivel == "SEGMENTO_2" and categoria == "CERVEJA RGB":
        return _COR_SEGMENTO_2_RGB
    if nivel == "SEGMENTO_3":
        return _COR_SEGMENTO_3_DEFAULT
    if nivel == "SKU":
        return _COR_SKU_DEFAULT
    if nivel == "INDICADOR":
        return _COR_INDICADOR_DEFAULT
    return None


_CORES_CABECALHO = {
    "CATEGORIA": {"background-color": "#06825D", "color": "#FFFFFF"},
    "VOL_ANO_RETRASADO": {"background-color": "#FFFFFF", "color": "#605E5C"},
    "VOL_MES_2": {"background-color": "#FFFFFF", "color": "#605E5C"},
    "VOL_MES_ANT": {"background-color": "#FFFFFF", "color": "#605E5C"},
    "META_FAB": {"background-color": "#06825D", "color": "#FFFFFF"},
    "META_REV": {"background-color": "#06825D", "color": "#FFFFFF"},
    "VOL_ANO_ANT": {"background-color": "#FFFFFF", "color": "#605E5C"},
    "VOL_ANO_ANT2": {"background-color": "#06825D", "color": "#FFFFFF"},
    "VOL_MES_ATUAL": {"background-color": "#06825D", "color": "#FFFFFF"},
    "TEND": {"background-color": "#0D6ABF", "color": "#FFFFFF"},
    "PERC_TEND": {"background-color": "#06825D", "color": "#FFFFFF"},
    "VENDA_HL": {"background-color": "#06825D", "color": "#FFFFFF"},
    "PERC_VOL_LN": {"background-color": "#06825D", "color": "#FFFFFF"},
    "PERC_COB_LN": {"background-color": "#06825D", "color": "#FFFFFF"},
    "COB_MES_ANT": {"background-color": "#06825D", "color": "#FFFFFF"},
    "COB_ANO_ANT": {"background-color": "#06825D", "color": "#FFFFFF"},
    "COB_MES_ATUAL": {"background-color": "#0D6ABF", "color": "#FFFFFF"},
    "FAT": {"background-color": "#06825D", "color": "#FFFFFF"},
}


def cor_cabecalho_dv(coluna: str) -> dict[str, str]:
    cor = _CORES_CABECALHO.get(coluna, {"background-color": "#FFFFFF", "color": "#000000"})
    return {**cor, "font-weight": "bold"}


def excluir_categorias_dv(revenda: str) -> list[str]:
    return []


_NOMES_MES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def label_mes(data) -> str:

    return f"{_NOMES_MES[data.month - 1]}/{data.strftime('%y')}"


def label_mes_str(mes: str) -> str:

    ano, mm = mes[:4], int(mes[4:6])
    return f"{_NOMES_MES[mm - 1]}/{ano[2:]}"


_CORES_ANO = {0: "#5DADE2", 1: "#1E8449", 2: "#82E0AA", 3: "#E67E22"}
_COR_ANO_PADRAO = "#95A5A6"


def cor_ano(distancia: int) -> str:
    return _CORES_ANO.get(distancia, _COR_ANO_PADRAO)
