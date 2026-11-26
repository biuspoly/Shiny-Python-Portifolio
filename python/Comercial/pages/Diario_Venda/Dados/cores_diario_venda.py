# Paleta do Diário de Vendas.
# A tabela é neutra: a cor fica só onde carrega sentido. Vermelho = abaixo do ano anterior ou da meta
# (só no texto, sem fundo); azul suave = as colunas que mais importam (tendência e cobertura do mês);
# cada marca tem a sua cor, mas como um marcador à esquerda do nome, não pintando a linha inteira.

COR_ALERTA = "#B3262D"

COR_META = {"color": COR_ALERTA, "font-weight": "600"}
COR_META_BOLD = {"color": COR_ALERTA, "font-weight": "bold"}
COR_META_REV = {"color": "#0F172A", "font-weight": "bold"}


COR_META_TITULO = {"color": "#0F172A", "background-color": "#EEF2F7", "font-weight": "bold"}
COR_META_DIFERENCA_NEGATIVA = {"color": COR_ALERTA}


COR_META_ABP_GRUPO = {"color": "#0F172A", "background-color": "#EEF2F7", "font-weight": "bold"}

# Cor de cada marca (usada no marcador da linha e nos gráficos).
CORES_MARCA = {
    "MARÉ": "#0B6E79",
    "CORAL": "#B5532F",
    "JANGADA": "#6B8E23",
    "CORAL ULTRA": "#6D4AAE",
    "MARÉ ULTIMATE": "#475569",
    "BRISA": "#5B9BD5",
    "FAROL": "#A23B72",
    "SERENA": "#2B6CB0",
}

_COR_TOTAL_VOLUME = {"color": "#0F172A", "background-color": "#F1F5F9", "font-weight": "bold"}
_COR_SUBTOTAL = {"color": "#0F172A", "font-weight": "bold"}
_COR_INDICADOR = {"color": "#475569"}


def cor_categoria_dv(categoria: str, nivel: str) -> dict[str, str] | None:
    """Estilo da linha inteira (só o necessário para ler a hierarquia)."""
    if nivel == "TOTAL" and categoria == "VOLUME TOTAL":
        return _COR_TOTAL_VOLUME
    if nivel == "SEGMENTO_2" and categoria == "CERVEJA RGB":
        return _COR_SUBTOTAL
    if nivel == "INDICADOR":
        return _COR_INDICADOR
    return None


def marcador_categoria_dv(categoria: str, nivel: str) -> dict[str, str] | None:
    """Marcador colorido na célula do nome, para as marcas."""
    if nivel == "MARCA" and categoria in CORES_MARCA:
        return {"box-shadow": f"inset 4px 0 0 {CORES_MARCA[categoria]}", "padding-left": "12px", "font-weight": "600"}
    return None


# Seções da tabela de categorias: uma linha separa uma seção da outra.
_SECAO_POR_NIVEL = {
    "TOTAL": "marca",
    "MARCA": "marca",
    "SEGMENTO": "segmento",
    "SEGMENTO_2": "segmento",
    "SEGMENTO_3": "segmento",
    "SKU": "sku",
    "INDICADOR": "indicador",
    "FATURAMENTO": "faturamento",
}
SEPARADOR_SECAO = {"border-top": "2px solid #CBD5E1"}


def secao_dv(nivel: str) -> str:
    return _SECAO_POR_NIVEL.get(nivel, nivel)


# Cabeçalho: histórico em cinza, mês corrente em escuro, colunas-chave com fundo azul suave.
_CAB_HISTORICO = {"background-color": "#F8FAFC", "color": "#64748B"}
_CAB_ATUAL = {"background-color": "#F8FAFC", "color": "#0F172A"}
_CAB_CHAVE = {"background-color": "#E6F0FA", "color": "#0B4A85"}

_CORES_CABECALHO = {
    "CATEGORIA": _CAB_ATUAL,
    "VOL_ANO_RETRASADO": _CAB_HISTORICO,
    "VOL_MES_2": _CAB_HISTORICO,
    "VOL_MES_ANT": _CAB_HISTORICO,
    "VOL_ANO_ANT": _CAB_HISTORICO,
    "META_FAB": _CAB_ATUAL,
    "META_REV": _CAB_ATUAL,
    "VOL_ANO_ANT2": _CAB_ATUAL,
    "VOL_MES_ATUAL": _CAB_ATUAL,
    "TEND": _CAB_CHAVE,
    "PERC_TEND": _CAB_ATUAL,
    "VENDA_HL": _CAB_ATUAL,
    "PERC_VOL_LN": _CAB_ATUAL,
    "PERC_COB_LN": _CAB_ATUAL,
    "COB_MES_ANT": _CAB_HISTORICO,
    "COB_ANO_ANT": _CAB_HISTORICO,
    "COB_MES_ATUAL": _CAB_CHAVE,
    "FAT": _CAB_ATUAL,
}

# Colunas-chave: o corpo da coluna também leva um fundo bem leve.
COLUNAS_CHAVE = {"TEND", "COB_MES_ATUAL"}
FUNDO_COLUNA_CHAVE = "#F5F9FD"


def cor_cabecalho_dv(coluna: str) -> dict[str, str]:
    cor = _CORES_CABECALHO.get(coluna, _CAB_ATUAL)
    return {**cor, "font-weight": "600"}


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
