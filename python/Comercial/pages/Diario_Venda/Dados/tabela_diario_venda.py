from __future__ import annotations

import html
import math
from dataclasses import dataclass

import pandas as pd
import polars as pl
from shiny import ui
from shiny.ui import HTML

from core.compat import para_pandas

from .cores_diario_venda import (
    COLUNAS_CHAVE,
    COR_META,
    COR_META_ABP_GRUPO,
    COR_META_BOLD,
    COR_META_DIFERENCA_NEGATIVA,
    COR_META_REV,
    COR_META_TITULO,
    FUNDO_COLUNA_CHAVE,
    SEPARADOR_SECAO,
    cor_cabecalho_dv,
    cor_categoria_dv,
    label_mes_str,
    marcador_categoria_dv,
    secao_dv,
)
from .dados_diario_venda import _mes_offset
from .ordenacao_diario_venda import (
    formatar_categoria_visual_dv,
    ordem_agrupamento_dv,
    ordem_categ_dv,
)


def _vazio(valor) -> bool:

    return valor is None or (isinstance(valor, float) and math.isnan(valor))


def _zero_para_nulo(tabela: pl.DataFrame) -> pl.DataFrame:

    colunas_numericas = [c for c, tipo in tabela.schema.items() if tipo.is_numeric()]
    return tabela.with_columns(
        [pl.when(pl.col(c) == 0).then(None).otherwise(pl.col(c)).alias(c) for c in colunas_numericas]
    )


def _numero(valor, casas: int = 0) -> str:
    if _vazio(valor):
        return ""
    try:
        num = float(valor)
    except (TypeError, ValueError):
        return ""
    texto = f"{num:,.{casas}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def _percentual(valor, casas: int = 1) -> str:
    if _vazio(valor):
        return ""
    try:
        num = float(valor) * 100
    except (TypeError, ValueError):
        return ""
    return f"{_numero(num, casas)}%"


def _moeda(valor) -> str:

    if _vazio(valor):
        return ""
    try:
        num = float(valor)
    except (TypeError, ValueError):
        return ""
    return _numero(num, 2)


def _num_ou_none(valor):
    if _vazio(valor):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _delta(texto: str, positivo: bool | None):
    classe = "kpi-delta-neutro" if positivo is None else ("kpi-delta-pos" if positivo else "kpi-delta-neg")
    return ui.span(texto, class_=f"kpi-delta {classe}")


def _variacao(atual, base, rotulo: str):
    if atual is None or not base:
        return _delta(f"sem {rotulo}", None)
    variacao = atual / base - 1
    seta = "▲" if variacao >= 0 else "▼"
    return _delta(f"{seta} {_numero(abs(variacao) * 100, 1)}% {rotulo}", variacao >= 0)


def cartoes_resumo_dv(total: dict, mes: str):
    """Faixa de indicadores do topo, lida da linha VOLUME TOTAL (os mesmos números da tabela)."""
    real = _num_ou_none(total.get("VOL_MES_ATUAL"))
    tend = _num_ou_none(total.get("TEND"))
    meta = _num_ou_none(total.get("META_REV"))
    ano_ant = _num_ou_none(total.get("VOL_ANO_ANT2"))
    cob = _num_ou_none(total.get("COB_MES_ATUAL"))
    cob_ano_ant = _num_ou_none(total.get("COB_ANO_ANT"))
    fat = _num_ou_none(total.get("FAT"))
    venda_hl = _num_ou_none(total.get("VENDA_HL"))
    rot_mes = label_mes_str(mes)

    if tend is not None and meta:
        perc = tend / meta
        sub_tend = _delta(f"{_numero(perc * 100, 1)}% da meta", perc >= 1)
    else:
        sub_tend = _delta("sem meta", None)

    if meta and real is not None:
        falta = meta - real
        sub_meta = _delta("meta batida", True) if falta <= 0 else _delta(f"faltam {_numero(falta)} HL", None)
    else:
        sub_meta = _delta("sem meta", None)

    def cartao(titulo, valor, sub, destaque=False):
        return ui.div(
            ui.div(titulo, class_="dv-kpi-titulo"),
            ui.div(valor, class_="dv-kpi-valor"),
            sub,
            class_="dv-kpi dv-kpi-destaque" if destaque else "dv-kpi",
        )

    return ui.div(
        cartao(
            f"Realizado {rot_mes}",
            f"{_numero(real)} HL" if real is not None else "–",
            _variacao(real, ano_ant, "vs ano anterior"),
        ),
        cartao("Tendência do mês", f"{_numero(tend)} HL" if tend is not None else "–", sub_tend, destaque=True),
        cartao("Meta revenda", f"{_numero(meta)} HL" if meta is not None else "–", sub_meta),
        cartao(
            "Cobertura (PDVs)", _numero(cob) if cob is not None else "–", _variacao(cob, cob_ano_ant, "vs ano anterior")
        ),
        cartao(
            "Faturamento",
            f"R$ {_numero(fat)}" if fat is not None else "–",
            _delta(f"R$ {_moeda(venda_hl)} por HL", None) if venda_hl else _delta("", None),
        ),
        class_="dv-kpis",
    )


_COLUNAS_COR_SEMPRE = {
    "CATEGORIA",
    "VOL_ANO_RETRASADO",
    "VOL_MES_2",
    "VOL_MES_ANT",
    "META_FAB",
    "META_REV",
    "VOL_ANO_ANT",
    "VOL_ANO_ANT2",
    "VOL_MES_ATUAL",
    "TEND",
}
_COLUNAS_COR_SE_NAO_INDICADOR_FAT = {"PERC_TEND", "VENDA_HL"}
_COLUNAS_COR_SE_TOTAL_OU_SKU = {"PERC_VOL_LN", "PERC_COB_LN"}
_COLUNAS_COR_SE_TOTAL = {"COB_MES_ANT", "COB_ANO_ANT", "COB_MES_ATUAL", "FAT"}


def _perc_ln_por_nivel(valor, nivel: str) -> str:

    if _vazio(valor) or valor == 0:
        return ""
    if nivel == "SKU":
        return _percentual(valor)
    return _numero(valor)


def _formatar_valor_por_nivel(valor, nivel: str, categoria: str) -> str:

    if _vazio(valor):
        return ""
    if nivel == "INDICADOR":
        if categoria.startswith("SKU/PDV "):
            return _numero(valor, 2)
        return f"{_numero(valor, 2)}%"
    if nivel == "FATURAMENTO":
        return _numero(valor, 2)
    return _numero(valor, 0)


def _adiciona_estilo(estilos: list[dict], linha: int, coluna: str, estilo: dict | None):
    if estilo:
        estilos.append({"rows": [linha], "cols": [coluna], "style": estilo})


_NIVEIS_TEND_CONTRA_META = ("INDICADOR", "FATURAMENTO")


def _abaixo_da_meta(tendencia, meta_revenda, nivel: str | None = None) -> bool:

    if nivel in _NIVEIS_TEND_CONTRA_META:
        return False
    if tendencia is None or meta_revenda is None or meta_revenda <= 0:
        return False
    return tendencia < meta_revenda


@dataclass(frozen=True)
class ColDef:
    coluna: str
    rotulo: str | None
    largura: int = 60
    cor: str | None = None
    distintivo: str | None = None


def _gerar_css_cabecalho(seletor_base: str, coldefs: list[ColDef]) -> str:

    grupos: dict[tuple[str, str], list[int]] = {}
    for posicao, cd in enumerate(coldefs, start=1):
        cor = cor_cabecalho_dv(cd.cor or cd.coluna)
        chave = (cor["background-color"], cor["color"])
        grupos.setdefault(chave, []).append(posicao)
    linhas = []
    for (fundo, texto), posicoes in grupos.items():
        seletores = ", ".join(f"{seletor_base} table thead th:nth-child({p})" for p in posicoes)
        linhas.append(f"{seletores} {{ background-color: {fundo}; color: {texto}; }}")
    # Colunas-chave (tendência e cobertura do mês): fundo leve no corpo da coluna.
    chave = [p for p, cd in enumerate(coldefs, start=1) if (cd.cor or cd.coluna) in COLUNAS_CHAVE]
    if chave:
        seletores = ", ".join(f"{seletor_base} table tbody td:nth-child({p})" for p in chave)
        linhas.append(f"{seletores} {{ background-color: {FUNDO_COLUNA_CHAVE}; }}")
    return "\n".join(linhas)


def _gerar_css_larguras(seletor_base: str, coldefs: list[ColDef]) -> str:

    linhas = []
    for posicao, cd in enumerate(coldefs, start=1):
        linhas.append(
            f"{seletor_base} table th:nth-child({posicao}), "
            f"{seletor_base} table td:nth-child({posicao}) {{ width: {cd.largura}px !important; }}"
        )
    return "\n".join(linhas)


def _gerar_css_rodape_total(seletor_base_total: str, coldefs: list[ColDef]) -> str:

    return _gerar_css_larguras(seletor_base_total, coldefs) + f"\n{seletor_base_total} table thead {{ display: none; }}"


def _gerar_css_distintivo_cabecalho(seletor_base: str, coldefs: list[ColDef]) -> str:

    linhas = []
    for posicao, cd in enumerate(coldefs, start=1):
        if not cd.distintivo:
            continue
        linhas.append(
            f"{seletor_base} table thead th:nth-child({posicao})::after {{"
            f' content: "{cd.distintivo}"; display: block; width: fit-content; margin: 2px auto 0;'
            " background-color: transparent; color: #64748B; border: 1px solid #CBD5E1;"
            " padding: 0 5px; border-radius: 8px; font-size: 0.9em; font-weight: normal; }"
        )
    return "\n".join(linhas)


_NIVEIS_TEND_CATEGORIA = {"TOTAL", "MARCA", "SEGMENTO", "SEGMENTO_2", "SEGMENTO_3", "SKU"}


def _attr_tooltip_tend(nivel: str) -> str | None:

    if nivel == "INDICADOR":
        return "data-tooltip-indicador"
    if nivel == "FATURAMENTO":
        return "data-tooltip-fat"
    if nivel in _NIVEIS_TEND_CATEGORIA:
        return "data-tooltip-categoria"
    return None


COLUNAS_CATEGORIAS: list[ColDef] = [
    ColDef("CATEGORIA", "Principais Categorias", 130),
    ColDef("VOL_ANO_RETRASADO", None),
    ColDef("VOL_ANO_ANT", None),
    ColDef("VOL_MES_2", None),
    ColDef("VOL_MES_ANT", None),
    ColDef("META_FAB", "Meta\nFábrica"),
    ColDef("META_REV", "Meta\nRevenda"),
    ColDef("VOL_ANO_ANT2", "Real Ano\nAnterior"),
    ColDef("VOL_MES_ATUAL", None),
    ColDef("TEND", "Tend.\n "),
    ColDef("PERC_TEND", "% Tend./\nRevenda"),
    ColDef("VENDA_HL", "R$/\nHL"),
    ColDef("PERC_VOL_LN", "Sell in", distintivo="Vol/ LN"),
    ColDef("PERC_COB_LN", "Diferença", distintivo="% Cob/LN"),
    ColDef("COB_MES_ANT", None),
    ColDef("COB_ANO_ANT", None),
    ColDef("COB_MES_ATUAL", None),
    ColDef("FAT", None, 90),
]


def construir_categorias_df(
    tabela: pl.DataFrame, mostrar_meta_fab: bool, mes: str, seletor_base: str
) -> tuple[pd.DataFrame, list[dict], str]:
    if tabela.height == 0:
        return pd.DataFrame(), [], ""

    tabela = _zero_para_nulo(tabela)
    ordem = {categoria: posicao for posicao, categoria in enumerate(ordem_categ_dv())}
    tabela = tabela.with_columns(pl.col("CATEGORIA").replace_strict(ordem, default=len(ordem)).alias("_ordem")).sort(
        "_ordem"
    )

    coldefs = [cd for cd in COLUNAS_CATEGORIAS if mostrar_meta_fab or cd.coluna != "META_FAB"]
    colunas = [cd.coluna for cd in coldefs]

    pandas_df = para_pandas(tabela.select(colunas)).astype({c: object for c in colunas if c != "CATEGORIA"})
    estilos: list[dict] = []

    niveis = tabela["NIVEL"].to_list()
    categorias = tabela["CATEGORIA"].to_list()

    pandas_df["CATEGORIA"] = pandas_df["CATEGORIA"].map(formatar_categoria_visual_dv)

    for linha in range(len(pandas_df)):
        nivel = niveis[linha]
        categoria = categorias[linha]

        if linha > 0 and secao_dv(nivel) != secao_dv(niveis[linha - 1]):
            for coluna in colunas:
                _adiciona_estilo(estilos, linha, coluna, SEPARADOR_SECAO)
        _adiciona_estilo(estilos, linha, "CATEGORIA", marcador_categoria_dv(categoria, nivel))

        cor_linha = cor_categoria_dv(categoria, nivel)
        if cor_linha:
            for coluna in colunas:
                if coluna in _COLUNAS_COR_SEMPRE:
                    _adiciona_estilo(estilos, linha, coluna, cor_linha)
                elif coluna in _COLUNAS_COR_SE_NAO_INDICADOR_FAT:
                    if nivel not in ("INDICADOR", "FATURAMENTO"):
                        _adiciona_estilo(estilos, linha, coluna, cor_linha)
                elif coluna in _COLUNAS_COR_SE_TOTAL_OU_SKU:
                    if nivel in ("TOTAL", "SKU"):
                        _adiciona_estilo(estilos, linha, coluna, cor_linha)
                elif coluna in _COLUNAS_COR_SE_TOTAL:
                    if nivel == "TOTAL":
                        _adiciona_estilo(estilos, linha, coluna, cor_linha)

        vol_atual_bruto = tabela["VOL_MES_ATUAL"][linha]
        texto_vol_atual = _formatar_valor_por_nivel(vol_atual_bruto, nivel, categoria)

        for coluna in colunas:
            valor_bruto = pandas_df.at[linha, coluna]
            if coluna == "CATEGORIA":
                continue
            if coluna == "VOL_MES_ATUAL" and nivel in ("INDICADOR", "FATURAMENTO"):
                pandas_df.at[linha, coluna] = ""
                continue
            if coluna == "TEND" and nivel in ("INDICADOR", "FATURAMENTO"):
                pandas_df.at[linha, coluna] = texto_vol_atual
                continue
            if coluna in ("META_REV",) and nivel == "INDICADOR":
                _adiciona_estilo(estilos, linha, coluna, COR_META_REV)
            pandas_df.at[linha, coluna] = (
                _formatar_valor_por_nivel(valor_bruto, nivel, categoria)
                if coluna
                in (
                    "VOL_ANO_RETRASADO",
                    "VOL_MES_2",
                    "VOL_MES_ANT",
                    "META_FAB",
                    "META_REV",
                    "VOL_ANO_ANT",
                    "VOL_ANO_ANT2",
                    "VOL_MES_ATUAL",
                    "TEND",
                )
                else valor_bruto
            )

        atributo_tend = _attr_tooltip_tend(nivel)
        texto_tend = pandas_df.at[linha, "TEND"]
        if atributo_tend and texto_tend:
            pandas_df.at[linha, "TEND"] = HTML(
                f'<span {atributo_tend}="{html.escape(categoria, quote=True)}">{texto_tend}</span>'
            )

        vol_ano_ant2 = tabela["VOL_ANO_ANT2"][linha]
        meta_rev = tabela["META_REV"][linha]
        tend_bruta = tabela["TEND"][linha]
        if nivel in ("INDICADOR", "FATURAMENTO"):
            valor_comparado, comparativo = vol_atual_bruto, meta_rev
        else:
            valor_comparado, comparativo = tend_bruta, vol_ano_ant2
        abaixo_do_ano = valor_comparado is not None and comparativo is not None and valor_comparado <= comparativo
        if abaixo_do_ano or _abaixo_da_meta(tend_bruta, meta_rev, nivel):
            _adiciona_estilo(estilos, linha, "TEND", COR_META_BOLD if nivel == "TOTAL" else COR_META)
        if (
            nivel not in ("INDICADOR", "FATURAMENTO")
            and vol_atual_bruto is not None
            and vol_ano_ant2 is not None
            and vol_atual_bruto <= vol_ano_ant2
        ):
            _adiciona_estilo(estilos, linha, "VOL_MES_ATUAL", COR_META_BOLD if nivel == "TOTAL" else COR_META)

        cob_atual = tabela["COB_MES_ATUAL"][linha]
        cob_ano_ant = tabela["COB_ANO_ANT"][linha]
        if cob_atual is not None and cob_ano_ant is not None and cob_atual <= cob_ano_ant:
            _adiciona_estilo(estilos, linha, "COB_MES_ATUAL", COR_META_BOLD if nivel == "TOTAL" else COR_META)

        perc_vol_ln = tabela["PERC_VOL_LN"][linha]
        perc_cob_ln = tabela["PERC_COB_LN"][linha]
        pandas_df.at[linha, "PERC_VOL_LN"] = _perc_ln_por_nivel(perc_vol_ln, nivel)
        pandas_df.at[linha, "PERC_COB_LN"] = _perc_ln_por_nivel(perc_cob_ln, nivel)

        if perc_cob_ln is not None and perc_cob_ln < 0:
            _adiciona_estilo(estilos, linha, "PERC_COB_LN", COR_META_BOLD if nivel == "TOTAL" else COR_META)

        pandas_df.at[linha, "PERC_TEND"] = _percentual(tabela["PERC_TEND"][linha])
        pandas_df.at[linha, "VENDA_HL"] = _moeda(tabela["VENDA_HL"][linha])

        pandas_df.at[linha, "COB_MES_ANT"] = _numero(tabela["COB_MES_ANT"][linha])
        pandas_df.at[linha, "COB_ANO_ANT"] = _numero(cob_ano_ant)
        texto_cob_atual = _numero(cob_atual)
        pandas_df.at[linha, "COB_MES_ATUAL"] = (
            HTML(f'<span data-tooltip-cob-categoria="{html.escape(categoria, quote=True)}">{texto_cob_atual}</span>')
            if texto_cob_atual
            else texto_cob_atual
        )
        fat_bruto = tabela["FAT"][linha]
        pandas_df.at[linha, "FAT"] = _moeda(fat_bruto) if fat_bruto else ""

    rot_atual = label_mes_str(mes)
    rot_1 = label_mes_str(_mes_offset(mes, 1))
    rot_2 = label_mes_str(_mes_offset(mes, 2))
    rot_aa = label_mes_str(_mes_offset(mes, 12))
    rot_aa2 = label_mes_str(_mes_offset(mes, 24))
    rotulos_dinamicos = {
        "VOL_ANO_RETRASADO": rot_aa2,
        "VOL_MES_2": rot_2,
        "VOL_MES_ANT": rot_1,
        "VOL_ANO_ANT": rot_aa,
        "VOL_MES_ATUAL": f"Real\n{rot_atual}",
        "COB_MES_ANT": f"Cob.\n{rot_1}",
        "COB_ANO_ANT": f"Cob.\n{rot_aa}",
        "COB_MES_ATUAL": f"Cob.\n{rot_atual}",
        "FAT": f"Fat.\n{rot_atual}",
    }

    css_cabecalho = (
        _gerar_css_cabecalho(seletor_base, coldefs)
        + "\n"
        + _gerar_css_larguras(seletor_base, coldefs)
        + "\n"
        + _gerar_css_distintivo_cabecalho(seletor_base, coldefs)
    )

    rotulos = {cd.coluna: (cd.rotulo or rotulos_dinamicos.get(cd.coluna, cd.coluna)) for cd in coldefs}
    pandas_df = pandas_df.rename(columns=rotulos)
    estilos = [{**e, "cols": [rotulos.get(c, c) for c in e["cols"]]} for e in estilos]

    return pandas_df, estilos, css_cabecalho


_COLDEFS_FAMILIA_PAREADAS: list[ColDef] = [
    ColDef("VOL_ANO_RETRASADO", None),
    ColDef("VOL_ANO_ANT", None),
    ColDef("VOL_MES_2", None),
    ColDef("VOL_MES_ANT", None),
    ColDef("META_FAB", "Meta\nFábrica"),
    ColDef("META_REV", "Meta\nRevenda"),
    ColDef("VOL_ANO_ANT2", "Real Ano\nAnterior"),
    ColDef("VOL_MES_ATUAL", None),
    ColDef("TEND", "Tend.\n "),
    ColDef("PERC_TEND", "% Tend./\nMeta"),
]


_COLDEFS_FAMILIA_EXTRA: list[ColDef] = [
    ColDef("PRECO_MEDIO", "Preço\nMédio", cor="VENDA_HL"),
    ColDef("PERC_MKP", "% MKP", cor="PERC_TEND"),
    ColDef("VENDA_HL", "R$/\nHL"),
    ColDef("COB_MES_ANT", None),
    ColDef("COB_ANO_ANT", None),
    ColDef("COB_MES_ATUAL", None),
    ColDef("FAT", None, 90),
]


_COR_LINHA_AGREGADA = {"font-weight": "bold", "background-color": "#F1F5F9", "color": "#0F172A"}


_BASES_ADITIVAS = [
    "VOL_ANO_RETRASADO",
    "VOL_MES_2",
    "VOL_MES_ANT",
    "META_FAB",
    "META_REV",
    "VOL_ANO_ANT",
    "VOL_ANO_ANT2",
    "VOL_MES_ATUAL",
    "TEND",
]


def _celula_produto_grupo(rotulo: str) -> str:

    return rotulo


def _celula_produto_item(produto: str, com_agrupamento: bool) -> HTML | str:

    if not com_agrupamento:
        return produto
    texto = html.escape(str(produto), quote=True)
    return HTML(f'<span style="padding-left:18px;display:inline-block;">{texto}</span>')


def _construir_familia_generico(
    tabela: pl.DataFrame,
    modo_hl: bool,
    com_agrupamento: bool,
    mostrar_meta_fab: bool,
    mes: str,
    seletor_base: str,
    seletor_base_total: str,
) -> tuple[pd.DataFrame, list[dict], pd.DataFrame, list[dict], str]:

    if tabela.height == 0:
        return pd.DataFrame(), [], pd.DataFrame(), [], ""

    sufixo = "_HL" if modo_hl else "_UMB"
    coldefs_pareadas = [cd for cd in _COLDEFS_FAMILIA_PAREADAS if mostrar_meta_fab or cd.coluna != "META_FAB"]
    colunas_pareadas = [f"{cd.coluna}{sufixo}" for cd in coldefs_pareadas]
    colunas_extra = [cd.coluna for cd in _COLDEFS_FAMILIA_EXTRA]

    coldefs_por_base = {cd.coluna: cd for cd in coldefs_pareadas + _COLDEFS_FAMILIA_EXTRA}

    todas_colunas = ["PRODUTO"] + colunas_pareadas + colunas_extra
    colunas_aditivas = [f"{base}{sufixo}" for base in _BASES_ADITIVAS if mostrar_meta_fab or base != "META_FAB"]

    if com_agrupamento:
        ordem_grupo = {grupo: posicao for posicao, grupo in enumerate(ordem_agrupamento_dv())}
        tabela_ordenada = (
            tabela.with_columns(
                pl.col("AGRUPAMENTO_VOLUME")
                .replace_strict(ordem_grupo, default=len(ordem_grupo), return_dtype=pl.Int32)
                .alias("_ordem_grupo")
            )
            .sort(["_ordem_grupo", "VOL_MES_ATUAL_UMB"], descending=[False, True])
            .drop("_ordem_grupo")
        )
    else:
        tabela_ordenada = tabela.sort("VOL_MES_ATUAL_UMB", descending=True)
    tabela_ordenada = _zero_para_nulo(tabela_ordenada)

    coluna_tend = f"TEND{sufixo}"

    def _formata_linha_produto(linha: dict) -> dict:
        registro = {"PRODUTO": _celula_produto_item(linha["PRODUTO"], com_agrupamento)}
        codred_attr = html.escape(str(linha["CODRED"]), quote=True)
        for coluna in colunas_pareadas:
            texto = _percentual(linha[coluna]) if coluna.startswith("PERC_TEND") else _numero(linha[coluna])
            if coluna == coluna_tend and texto:
                texto = HTML(f'<span data-tooltip-familia-prod="{codred_attr}">{texto}</span>')
            registro[coluna] = texto
        registro["PRECO_MEDIO"] = _moeda(linha["PRECO_MEDIO"])
        registro["PERC_MKP"] = _percentual(linha["PERC_MKP"])
        registro["VENDA_HL"] = _moeda(linha["VENDA_HL"])
        registro["COB_MES_ANT"] = _numero(linha["COB_MES_ANT"])
        registro["COB_ANO_ANT"] = _numero(linha["COB_ANO_ANT"])
        texto_cob = _numero(linha["COB_MES_ATUAL"])
        registro["COB_MES_ATUAL"] = (
            HTML(f'<span data-tooltip-cob-familia="{codred_attr}">{texto_cob}</span>') if texto_cob else texto_cob
        )
        registro["FAT"] = _moeda(linha["FAT"])
        return registro

    def _colunas_alerta_produto(linha: dict) -> list[str]:

        vol_atual = linha[f"VOL_MES_ATUAL{sufixo}"]
        vol_ano_ant2 = linha[f"VOL_ANO_ANT2{sufixo}"]
        tend = linha[f"TEND{sufixo}"]
        meta_rev = linha.get(f"META_REV{sufixo}")
        cob_atual = linha["COB_MES_ATUAL"]
        cob_ano_ant = linha["COB_ANO_ANT"]
        colunas = []
        if vol_atual is not None and vol_ano_ant2 is not None and vol_atual <= vol_ano_ant2:
            colunas.append(f"VOL_MES_ATUAL{sufixo}")
        abaixo_do_ano = tend is not None and vol_ano_ant2 is not None and tend <= vol_ano_ant2
        if abaixo_do_ano or _abaixo_da_meta(tend, meta_rev):
            colunas.append(f"TEND{sufixo}")
        if cob_atual is not None and cob_ano_ant is not None and cob_atual <= cob_ano_ant:
            colunas.append("COB_MES_ATUAL")
        return colunas

    def _formata_linha_resumo(rotulo: str, base: pl.DataFrame) -> dict:

        registro = {c: "" for c in todas_colunas}
        registro["PRODUTO"] = _celula_produto_grupo(rotulo)
        for coluna in colunas_aditivas:
            registro[coluna] = _numero(base[coluna].sum())
        registro["COB_MES_ANT"] = _numero(base["COB_MES_ANT"].sum())
        registro["COB_ANO_ANT"] = _numero(base["COB_ANO_ANT"].sum())
        registro["COB_MES_ATUAL"] = _numero(base["COB_MES_ATUAL"].sum())
        registro["FAT"] = _moeda(base["FAT"].sum())
        return registro

    registros: list[dict] = []
    linhas_bold: list[int] = []
    linhas_novo_produto: list[int] = []

    alertas_produto: dict[int, list[str]] = {}

    if com_agrupamento:
        for grupo in tabela_ordenada["AGRUPAMENTO_VOLUME"].unique(maintain_order=True).to_list():
            base_grupo = tabela_ordenada.filter(pl.col("AGRUPAMENTO_VOLUME") == grupo)
            linhas_bold.append(len(registros))

            if grupo == "NOVO PRODUTO":
                linhas_novo_produto.append(len(registros))
            registros.append(_formata_linha_resumo(f"{grupo} ({base_grupo.height} produtos)", base_grupo))
            for linha in base_grupo.iter_rows(named=True):
                if grupo == "NOVO PRODUTO":
                    linhas_novo_produto.append(len(registros))
                indice = len(registros)
                registros.append(_formata_linha_produto(linha))
                alertas_produto[indice] = _colunas_alerta_produto(linha)
    else:
        for linha in tabela_ordenada.iter_rows(named=True):
            indice = len(registros)
            registros.append(_formata_linha_produto(linha))
            alertas_produto[indice] = _colunas_alerta_produto(linha)

    pandas_df = pd.DataFrame(registros, columns=todas_colunas)
    estilos: list[dict] = []
    for linha in linhas_bold:
        for coluna in todas_colunas:
            _adiciona_estilo(estilos, linha, coluna, _COR_LINHA_AGREGADA)
    for linha in linhas_novo_produto:
        for coluna in todas_colunas:
            _adiciona_estilo(estilos, linha, coluna, COR_META)
    for linha, colunas_alerta in alertas_produto.items():
        for coluna in colunas_alerta:
            _adiciona_estilo(estilos, linha, coluna, COR_META)

    pandas_total_df = pd.DataFrame([_formata_linha_resumo("TOTAL GERAL", tabela_ordenada)], columns=todas_colunas)
    estilos_total = [{"rows": [0], "cols": todas_colunas, "style": _COR_LINHA_AGREGADA}]

    def _base(coluna: str) -> str:

        return coluna[: -len(sufixo)] if coluna in colunas_pareadas else coluna

    coldef_produto = ColDef("PRODUTO", "Produto", 250 if com_agrupamento else 240, cor="CATEGORIA")
    coldefs_render = [coldef_produto] + [
        ColDef(
            c,
            None,
            coldefs_por_base[_base(c)].largura,
            cor=coldefs_por_base[_base(c)].cor or _base(c),
        )
        for c in (colunas_pareadas + colunas_extra)
    ]
    css_cabecalho = (
        _gerar_css_cabecalho(seletor_base, coldefs_render)
        + "\n"
        + _gerar_css_larguras(seletor_base, coldefs_render)
        + "\n"
        + _gerar_css_rodape_total(seletor_base_total, coldefs_render)
    )

    rot_atual = label_mes_str(mes)
    rot_1 = label_mes_str(_mes_offset(mes, 1))
    rot_2 = label_mes_str(_mes_offset(mes, 2))
    rot_aa = label_mes_str(_mes_offset(mes, 12))
    rot_aa2 = label_mes_str(_mes_offset(mes, 24))
    rotulos_dinamicos = {
        "VOL_ANO_RETRASADO": rot_aa2,
        "VOL_MES_2": rot_2,
        "VOL_MES_ANT": rot_1,
        "VOL_ANO_ANT": rot_aa,
        "VOL_MES_ATUAL": f"Real\n{rot_atual}",
        "COB_MES_ANT": f"Cob.\n{rot_1}",
        "COB_ANO_ANT": f"Cob.\n{rot_aa}",
        "COB_MES_ATUAL": f"Cob.\n{rot_atual}",
        "FAT": f"Fat.\n{rot_atual}",
    }

    def _rotulo(coluna_base: str) -> str:
        return rotulos_dinamicos.get(coluna_base) or coldefs_por_base[coluna_base].rotulo or coluna_base

    rotulos = {"PRODUTO": coldef_produto.rotulo} | {c: _rotulo(_base(c)) for c in (colunas_pareadas + colunas_extra)}
    pandas_df = pandas_df.rename(columns=rotulos)
    estilos = [{**e, "cols": [rotulos.get(c, c) for c in e["cols"]]} for e in estilos]
    pandas_total_df = pandas_total_df.rename(columns=rotulos)
    estilos_total = [{**e, "cols": [rotulos.get(c, c) for c in e["cols"]]} for e in estilos_total]

    return pandas_df, estilos, pandas_total_df, estilos_total, css_cabecalho


def construir_familia_df(
    tabela: pl.DataFrame, modo_hl: bool, mostrar_meta_fab: bool, mes: str, seletor_base: str, seletor_base_total: str
) -> tuple[pd.DataFrame, list[dict], pd.DataFrame, list[dict], str]:
    return _construir_familia_generico(
        tabela,
        modo_hl,
        com_agrupamento=True,
        mostrar_meta_fab=mostrar_meta_fab,
        mes=mes,
        seletor_base=seletor_base,
        seletor_base_total=seletor_base_total,
    )


def construir_outros_df(
    tabela: pl.DataFrame, modo_hl: bool, mostrar_meta_fab: bool, mes: str, seletor_base: str, seletor_base_total: str
) -> tuple[pd.DataFrame, list[dict], pd.DataFrame, list[dict], str]:
    return _construir_familia_generico(
        tabela,
        modo_hl,
        com_agrupamento=False,
        mostrar_meta_fab=mostrar_meta_fab,
        mes=mes,
        seletor_base=seletor_base,
        seletor_base_total=seletor_base_total,
    )


_COLUNAS_MES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


_COLDEFS_META_ANO = [ColDef("HL_TOTAL", None, 150)] + [ColDef(c, None, 70) for c in _COLUNAS_MES + ["Total"]]
_COLDEFS_META_ABP = [ColDef("COD_SAP", None, 80), ColDef("HL_TOTAL", None, 200)] + [
    ColDef(c, None, 55) for c in _COLUNAS_MES + ["Total"]
]


def construir_meta_ano_df(
    tabela: pl.DataFrame, ano_atual: int, mes_atual: int, seletor_base: str
) -> tuple[pd.DataFrame, list[dict], str]:

    if tabela.height == 0:
        return pd.DataFrame(), [], ""
    colunas = ["HL_TOTAL"] + _COLUNAS_MES + ["Total"]
    pandas_df = para_pandas(tabela.select(colunas))
    estilos: list[dict] = []

    rotulos = tabela["HL_TOTAL"].to_list()
    rotulo_titulo = f"Meta {ano_atual}"
    ano_at_str = str(ano_atual)
    linhas_com_total = {rotulo_titulo, ano_at_str, "Diferenca"}
    linhas_ate_mes = {ano_at_str, "Diferenca"}

    for linha, rotulo in enumerate(rotulos):
        if rotulo == rotulo_titulo:
            _adiciona_estilo(estilos, linha, "HL_TOTAL", COR_META_TITULO)
        if rotulo in linhas_ate_mes:
            for numero_mes, coluna in enumerate(_COLUNAS_MES, start=1):
                if numero_mes > mes_atual:
                    pandas_df.at[linha, coluna] = None
        if rotulo not in linhas_com_total:
            pandas_df.at[linha, "Total"] = None
        if rotulo == "Diferenca":
            for coluna in _COLUNAS_MES + ["Total"]:
                valor = pandas_df.at[linha, coluna]
                if valor is not None and valor < 0:
                    _adiciona_estilo(estilos, linha, coluna, COR_META_DIFERENCA_NEGATIVA)

    for coluna in _COLUNAS_MES + ["Total"]:
        pandas_df[coluna] = pandas_df[coluna].map(_numero)
    css_larguras = _gerar_css_larguras(seletor_base, _COLDEFS_META_ANO)

    css_larguras += f"\n{seletor_base} table {{ width: auto !important; }}"

    pandas_df = pandas_df.rename(columns={"HL_TOTAL": "HL Total"})
    estilos = [{**e, "cols": ["HL Total" if c == "HL_TOTAL" else c for c in e["cols"]]} for e in estilos]
    return pandas_df, estilos, css_larguras


def construir_meta_abp_df(
    tabela: pl.DataFrame, ano_atual: int, mes_atual: int, seletor_base: str, tipo: str = "Cobertura"
) -> tuple[pd.DataFrame, list[dict], str]:

    if tabela.height == 0:
        return pd.DataFrame(), [], ""
    col_real = f"{'Cob' if tipo == 'Cobertura' else 'Vol'} {ano_atual}"
    colunas_visiveis = ["COD_SAP", "HL_TOTAL"] + _COLUNAS_MES + ["Total"]

    novo_cod_sap = tabela["NOVO_COD_SAP"].to_list()
    categorias = tabela["CATEGORIA"].to_list()
    rotulos = tabela["HL_TOTAL"].to_list()
    cod_saps = tabela["COD_SAP"].to_list()

    registros: list[dict] = []
    linhas_grupo: list[int] = []
    linhas_produto: list[int] = []
    linhas_borda: list[int] = []
    linhas_estilo_diferenca: list[int] = []

    categoria_anterior = None
    for i in range(tabela.height):
        cat = categorias[i]
        if cat != categoria_anterior:
            linhas_grupo.append(len(registros))
            registros.append({"COD_SAP": "", "HL_TOTAL": cat, **{m: None for m in _COLUNAS_MES}, "Total": None})
            categoria_anterior = cat

        rotulo = rotulos[i]
        registro = {"COD_SAP": cod_saps[i], "HL_TOTAL": rotulo}
        for numero_mes, coluna in enumerate(_COLUNAS_MES, start=1):
            valor = tabela[coluna][i]
            registro[coluna] = None if (numero_mes > mes_atual and rotulo != "Meta ABP") else valor
        registro["Total"] = tabela["Total"][i]

        if novo_cod_sap[i]:
            linhas_borda.append(len(registros))
        if rotulo not in (col_real, "Meta ABP"):
            linhas_estilo_diferenca.append(len(registros))
        linhas_produto.append(len(registros))
        registros.append(registro)

    pandas_df = pd.DataFrame(registros, columns=colunas_visiveis).astype({"HL_TOTAL": object})
    estilos: list[dict] = []

    for linha in linhas_grupo:
        for coluna in colunas_visiveis:
            _adiciona_estilo(estilos, linha, coluna, COR_META_ABP_GRUPO)
    for linha in linhas_borda:
        for coluna in colunas_visiveis:
            _adiciona_estilo(estilos, linha, coluna, {"border-top": "1px solid #000000"})
    for linha in linhas_estilo_diferenca:
        for coluna in _COLUNAS_MES + ["Total"]:
            valor = pandas_df.at[linha, coluna]
            if valor is not None and valor < 0:
                _adiciona_estilo(estilos, linha, coluna, COR_META)

    for coluna in _COLUNAS_MES + ["Total"]:
        pandas_df[coluna] = pandas_df[coluna].map(_numero)

    for linha in linhas_grupo:
        texto = html.escape(str(pandas_df.at[linha, "HL_TOTAL"]), quote=True)
        pandas_df.at[linha, "HL_TOTAL"] = HTML(f"<strong>{texto}</strong>")

    for linha in linhas_produto:
        texto = html.escape(str(pandas_df.at[linha, "HL_TOTAL"]), quote=True)
        pandas_df.at[linha, "HL_TOTAL"] = HTML(f'<span style="padding-left:18px;display:inline-block;">{texto}</span>')

    novo_nome_hl = "Cobertura" if tipo == "Cobertura" else "Volume"
    if tipo == "Cobertura":
        pandas_df = pandas_df.rename(columns={"Total": "Média"})
        estilos = [{**e, "cols": ["Média" if c == "Total" else c for c in e["cols"]]} for e in estilos]
    pandas_df = pandas_df.rename(columns={"HL_TOTAL": novo_nome_hl})
    estilos = [{**e, "cols": [novo_nome_hl if c == "HL_TOTAL" else c for c in e["cols"]]} for e in estilos]

    css_larguras = _gerar_css_larguras(seletor_base, _COLDEFS_META_ABP)
    return pandas_df, estilos, css_larguras
