from __future__ import annotations

from datetime import date

from pyecharts import options as opts
from pyecharts.charts import Line

from core.pyecharts_shiny import renderizar

from .cores_diario_venda import cor_ano
from .dados_diario_venda import (
    REVENDA_NOME_BD,
    REVENDAS_POR_GRUPO,
    SKU_CORAL_LN,
    SKUS_CORAL_LN,
    _fonte_parquet_dv,
    _sql_escapa,
    _sql_in,
    _sql_lista,
    expandir_revendas_dv,
    tabela_cobertura,
)
from .ordenacao_diario_venda import formatar_categoria_visual_dv

_ORDEM_MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _expr_mes(coluna: str) -> str:
    casos = " ".join(f"WHEN '{m:02d}' THEN '{nome}'" for m, nome in enumerate(_ORDEM_MESES, start=1))
    return f"CASE RIGHT({coluna}, 2) {casos} END"


def _revs_efetivas_tooltip(revenda_query: str, rev: list[str] | None) -> list[str]:

    if rev:
        expandidas: list[str] = []
        for revenda_selecionada in rev:
            expandidas.extend(expandir_revendas_dv(revenda_selecionada, revenda_query))
        return list(dict.fromkeys(expandidas))
    revenda_norm = REVENDA_NOME_BD.get(revenda_query, revenda_query)
    if revenda_norm in REVENDAS_POR_GRUPO:
        return REVENDAS_POR_GRUPO[revenda_norm]
    return expandir_revendas_dv(revenda_norm, revenda_query)


def _construir_grafico_historico(tabela, coluna_valor: str, titulo: str) -> str | None:

    tabela = tabela.filter(tabela["ANO"].is_not_null() & tabela["MES"].is_not_null())
    if tabela.height == 0:
        return None
    anos = sorted(tabela["ANO"].unique().to_list())
    meses_com_dado = set(tabela["MES"].to_list())
    meses_presentes = [m for m in _ORDEM_MESES if m in meses_com_dado]
    ano_atual = date.today().year

    chart = Line().add_xaxis(meses_presentes)
    for ano in anos:
        valores = []
        for mes in meses_presentes:
            linha = tabela.filter((tabela["ANO"] == ano) & (tabela["MES"] == mes))
            valores.append(round(linha[coluna_valor].sum(), 2) if linha.height else None)
        chart.add_yaxis(
            str(ano),
            valores,
            label_opts=opts.LabelOpts(is_show=True, position="top"),
            color=cor_ano(ano_atual - int(ano)),
        )
    chart.set_global_opts(
        title_opts=opts.TitleOpts(title=titulo, pos_left="left"),
        legend_opts=opts.LegendOpts(pos_bottom=0),
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(interval=0)),
        yaxis_opts=opts.AxisOpts(
            is_show=True,
            is_scale=True,
            axislabel_opts=opts.LabelOpts(is_show=False),
            axistick_opts=opts.AxisTickOpts(is_show=False),
            axisline_opts=opts.AxisLineOpts(is_show=False),
            splitline_opts=opts.SplitLineOpts(is_show=False),
        ),
    )

    return renderizar(chart, altura="100%")


_COL_MAP_NIVEL = {
    "TOTAL": "VOLUME_TOTAL",
    "MARCA": "MARCA",
    "SEGMENTO": "SEGMENTO",
    "SEGMENTO_2": "SEGMENTO_2",
    "SEGMENTO_3": "SEGMENTO_3",
    "SKU": "SKU_GRUPO",
}


def historico_tend_categ(
    revenda_query: str,
    marca: str,
    nivel: str,
    ga: list[str] | None = None,
    ven: list[str] | None = None,
    rev: list[str] | None = None,
    base: str | None = None,
) -> str | None:
    col_categ = _COL_MAP_NIVEL.get(nivel)
    if col_categ is None:
        return None
    try:
        tend_field = "DV.TEND_UMB" if nivel == "SKU" else "DV.TEND_HL"
        qtd_field = "DV.QTD_TOTAL" if nivel == "SKU" else "DV.QTD_TOTAL_HL"

        filtro_categ = (
            f"DV.SKU_GRUPO IN ({_sql_lista(SKUS_CORAL_LN)})"
            if marca == SKU_CORAL_LN
            else f"DV.{col_categ} = '{_sql_escapa(marca)}'"
        )
        mes_atual_sql = date.today().strftime("%Y%m")
        revs_sql = _sql_lista(_revs_efetivas_tooltip(revenda_query, rev))
        query = f"""
            SELECT LEFT(DV.MES, 4) AS ANO, DV.MES AS MES_ORD, {_expr_mes("DV.MES")} AS MES,
                   ROUND(SUM(CASE WHEN DV.MES = '{mes_atual_sql}' THEN {tend_field} ELSE {qtd_field} END), 0) AS TENDENCIA
            FROM TB_DIARIO_VENDA DV
            WHERE {filtro_categ}
              AND DV.REVENDA IN ({revs_sql})
              {_sql_in("DV.GA", ga)}
              {_sql_in("DV.VEN", ven)}
              {_sql_in("DV.BASE_FOCO", [base] if base else None)}
            GROUP BY DV.MES
            ORDER BY DV.MES
        """
        tabela = _fonte_parquet_dv(query)
        if tabela.height == 0:
            return None

        return _construir_grafico_historico(tabela, "TENDENCIA", formatar_categoria_visual_dv(marca))
    except Exception:
        return None


def historico_cob_categ(
    revenda_query: str,
    categoria: str,
    ga: list[str] | None = None,
    ven: list[str] | None = None,
    rev: list[str] | None = None,
    base: str | None = None,
) -> str | None:
    try:
        revs_sql = _sql_lista(_revs_efetivas_tooltip(revenda_query, rev))
        query = f"""
            SELECT ANO, MES, SUM(COBERTURA) AS COBERTURA
            FROM (
                SELECT LEFT(CP.MES, 4) AS ANO, CP.MES AS MES_ORD, {_expr_mes("CP.MES")} AS MES,
                       ROUND(SUM(CP.COB_CAT), 0) AS COBERTURA
                FROM {tabela_cobertura("tb_cob_categ", ga, ven)} CP
                WHERE CP.CATEGORIA = '{_sql_escapa(categoria)}'
                  AND CP.REVENDA IN ({revs_sql})
                  {_sql_in("CP.GA", ga)}
                  {_sql_in("CP.VEN", ven)}
                  {_sql_in("CP.BASE_FOCO", [base] if base else None)}
                GROUP BY CP.MES, CP.REVENDA
            ) sub
            GROUP BY ANO, MES_ORD, MES
            ORDER BY MES_ORD
        """
        tabela = _fonte_parquet_dv(query)
        if tabela.height == 0:
            return None
        return _construir_grafico_historico(tabela, "COBERTURA", formatar_categoria_visual_dv(categoria))
    except Exception:
        return None


_INDICADOR_MAPA = {
    "CORAL 600/MAR 600": ("CORAL 600ml", "MARÉ 600ml"),
    "MAR 600/RGB TT": ("MARÉ 600ml", "RGB"),
    "MAR 0.0%/MAR TT": ("0%", "MARÉ"),
}


def _historico_indicador_generico(
    revenda_query: str,
    indicador: str,
    rev: list[str] | None,
    ga: list[str] | None,
    ven: list[str] | None,
    base: str | None = None,
) -> str | None:
    mapa = _INDICADOR_MAPA.get(indicador)
    if mapa is None:
        return None
    cat_num, cat_den = mapa
    revs_sql = _sql_lista(_revs_efetivas_tooltip(revenda_query, rev))
    query = f"""
        SELECT ANO, MES, TENDENCIA
        FROM (
            SELECT LEFT(CH.MES, 4) AS ANO, CH.MES AS MES_ORD, {_expr_mes("CH.MES")} AS MES,
                   ROUND(
                       MAX(CASE WHEN CH.CATEGORIA = '{_sql_escapa(cat_num)}' THEN CH.COB_CAT END) /
                       NULLIF(MAX(CASE WHEN CH.CATEGORIA = '{_sql_escapa(cat_den)}' THEN CH.COB_CAT END), 0) * 100
                   , 2) AS TENDENCIA
            FROM (
                SELECT MES, CATEGORIA, SUM(COB_CAT) AS COB_CAT
                FROM {tabela_cobertura("tb_cob_categ", ga, ven)}
                WHERE REVENDA IN ({revs_sql})
                  {_sql_in("GA", ga)}
                  {_sql_in("VEN", ven)}
                  {_sql_in("BASE_FOCO", [base] if base else None)}
                  AND CATEGORIA IN ('{_sql_escapa(cat_num)}', '{_sql_escapa(cat_den)}')
                GROUP BY MES, CATEGORIA
            ) CH
            GROUP BY CH.MES
        ) sub
        WHERE TENDENCIA IS NOT NULL
        ORDER BY MES_ORD
    """
    tabela = _fonte_parquet_dv(query)
    if tabela.height == 0:
        return None
    return _construir_grafico_historico(tabela, "TENDENCIA", indicador)


def _historico_sku_pdv(
    revenda_query: str,
    indicador: str,
    rev: list[str] | None,
    ga: list[str] | None,
    ven: list[str] | None,
    base: str | None = None,
) -> str | None:

    usa_abp = "REVENDA" not in indicador
    revs_efetivas = _revs_efetivas_tooltip(revenda_query, rev)
    revs_sql = _sql_lista(revs_efetivas)
    revs_sql_upper = _sql_lista([r.upper() for r in revs_efetivas])
    den_col = "MA_SKU.VALOR" if usa_abp else "PDV_SKU.PDV_ATENDIDO"
    filtro_ga = _sql_in("GA", ga) if not usa_abp else ""
    filtro_ven = _sql_in("VEN", ven) if not usa_abp else ""

    filtro_base = _sql_in("BASE_FOCO", [base] if base else None)
    query = f"""
        SELECT ANO, MES, ROUND(SUM(QTD_SKU_PDV) / NULLIF(SUM(META_DEN), 0), 2) AS TENDENCIA
        FROM (
            SELECT LEFT(Q.MES, 4) AS ANO, Q.MES AS MES_ORD, {_expr_mes("Q.MES")} AS MES,
                   Q.QTD_SKU_PDV, COALESCE({den_col}, 0) AS META_DEN
            FROM (
                SELECT REVENDA, MES, SUM(QTD_SKU_PDV) AS QTD_SKU_PDV
                FROM tb_cob_cli
                WHERE REVENDA IN ({revs_sql})
                  {filtro_ga}
                  {filtro_ven}
                  {filtro_base}
                GROUP BY REVENDA, MES
            ) Q
            LEFT JOIN (
                SELECT REVENDA, MES, SUM(VALOR) AS VALOR
                FROM TB_META_ABP
                WHERE UPPER(REVENDA) IN ({revs_sql_upper})
                GROUP BY REVENDA, MES
            ) MA_SKU ON MA_SKU.REVENDA = Q.REVENDA AND MA_SKU.MES = Q.MES
            LEFT JOIN (
                SELECT REVENDA, MES, SUM(QTD_PDV) AS PDV_ATENDIDO
                FROM tb_cob_cli_ativo
                WHERE REVENDA IN ({revs_sql})
                  {filtro_ga}
                  {filtro_ven}
                  {filtro_base}
                GROUP BY REVENDA, MES
            ) PDV_SKU ON PDV_SKU.REVENDA = Q.REVENDA AND PDV_SKU.MES = Q.MES
        ) sub
        GROUP BY ANO, MES_ORD, MES
        HAVING TENDENCIA IS NOT NULL
        ORDER BY MES_ORD
    """
    tabela = _fonte_parquet_dv(query)
    if tabela.height == 0:
        return None
    return _construir_grafico_historico(tabela, "TENDENCIA", indicador)


def _historico_fds(
    revenda_query: str,
    indicador: str,
    rev: list[str] | None,
    ga: list[str] | None,
    ven: list[str] | None,
    base: str | None = None,
) -> str | None:
    usa_revenda = "REVENDA" in indicador
    revs_sql = _sql_lista(_revs_efetivas_tooltip(revenda_query, rev))
    filtro_ga = _sql_in("GA", ga) if usa_revenda else ""
    filtro_ven = _sql_in("VEN", ven) if usa_revenda else ""
    filtro_rev_sel = _sql_in("REVENDA", rev)
    filtro_rev_sel_f = _sql_in("F.REVENDA", rev)

    if usa_revenda:
        query = f"""
            SELECT ANO, MES, ROUND(SUM(GRUPOS_META) / NULLIF(SUM(TOTAL_GRUPOS), 0) * 100, 2) AS TENDENCIA
            FROM (
                SELECT LEFT(MES, 4) AS ANO, MES AS MES_ORD, {_expr_mes("MES")} AS MES,
                       GRUPOS_META, TOTAL_GRUPOS
                FROM tb_exig_fds
                WHERE REVENDA IN ({revs_sql})
                  {filtro_rev_sel}
                  {filtro_ga}
                  {filtro_ven}
            ) sub
            GROUP BY ANO, MES_ORD, MES
            HAVING TENDENCIA IS NOT NULL
            ORDER BY MES_ORD
        """
    else:
        query = f"""
            SELECT ANO, MES, ROUND(SUM(GRUPOS_META) / NULLIF(MAX(META_FDS) * 100, 0) * 100, 2) AS TENDENCIA
            FROM (
                SELECT LEFT(F.MES, 4) AS ANO, F.MES AS MES_ORD, {_expr_mes("F.MES")} AS MES,
                       F.GRUPOS_META, M.META_FDS
                FROM tb_exig_fds F
                JOIN (
                    SELECT C.REVENDA, C.MES,
                           CASE WHEN A.VALOR IS NULL OR A.VALOR = 0 THEN C.QTD_PDV ELSE A.VALOR END AS META_FDS
                    FROM (
                        SELECT REVENDA, MES, SUM(QTD_PDV) AS QTD_PDV
                        FROM tb_cob_rev
                        WHERE REVENDA IN ({revs_sql}) {_sql_in("BASE_FOCO", [base] if base else None)}
                        GROUP BY REVENDA, MES
                    ) C
                    LEFT JOIN TB_META_ABP A ON A.REVENDA = C.REVENDA AND A.MES = C.MES
                ) M ON M.REVENDA = F.REVENDA AND M.MES = F.MES
                WHERE F.REVENDA IN ({revs_sql})
                  {filtro_rev_sel_f}
            ) sub
            GROUP BY ANO, MES_ORD, MES
            HAVING TENDENCIA IS NOT NULL
            ORDER BY MES_ORD
        """
    tabela = _fonte_parquet_dv(query)
    if tabela.height == 0:
        return None
    return _construir_grafico_historico(tabela, "TENDENCIA", indicador)


def historico_indicador(
    revenda_query: str,
    indicador: str,
    rev: list[str] | None = None,
    ga: list[str] | None = None,
    ven: list[str] | None = None,
    base: str | None = None,
) -> str | None:
    try:
        if indicador.startswith("SKU/PDV"):
            return _historico_sku_pdv(revenda_query, indicador, rev, ga, ven, base)
        if indicador.startswith("FDS"):
            return _historico_fds(revenda_query, indicador, rev, ga, ven, base)
        return _historico_indicador_generico(revenda_query, indicador, rev, ga, ven, base)
    except Exception:
        return None


def historico_fat(
    revenda_query: str,
    canal: str,
    titulo: str,
    rev: list[str] | None = None,
    ga: list[str] | None = None,
    ven: list[str] | None = None,
    base: str | None = None,
) -> str | None:
    try:
        revs_sql = _sql_lista(_revs_efetivas_tooltip(revenda_query, rev))
        canal_filtro = f"AND DV.CANAL = '{_sql_escapa(canal)}'" if canal else ""
        query = f"""
            SELECT ANO, MES, SUM(TENDENCIA) AS TENDENCIA
            FROM (
                SELECT LEFT(DV.MES, 4) AS ANO, DV.MES AS MES_ORD, {_expr_mes("DV.MES")} AS MES,
                       ROUND(SUM(DV.FATURAMENTO), 2) AS TENDENCIA
                FROM TB_DIARIO_VENDA DV
                WHERE DV.REVENDA IN ({revs_sql})
                  {canal_filtro}
                  {_sql_in("DV.GA", ga)}
                  {_sql_in("DV.VEN", ven)}
                  {_sql_in("DV.BASE_FOCO", [base] if base else None)}
                GROUP BY DV.MES, DV.REVENDA
            ) sub
            GROUP BY ANO, MES_ORD, MES
            ORDER BY MES_ORD
        """
        tabela = _fonte_parquet_dv(query)
        if tabela.height == 0:
            return None
        return _construir_grafico_historico(tabela, "TENDENCIA", titulo)
    except Exception:
        return None


def historico_tend_familia(
    revenda_query: str,
    codred: str | None = None,
    agrupamento: str | None = None,
    titulo_override: str | None = None,
    unidade: str = "UMB",
    mes: str | None = None,
    rev: list[str] | None = None,
    base: str | None = None,
    ga: list[str] | None = None,
    ven: list[str] | None = None,
) -> str | None:
    try:
        mes_atual_sql = mes or date.today().strftime("%Y%m")
        revs_sql = _sql_lista(_revs_efetivas_tooltip(revenda_query, rev))
        if codred:
            tend_field = "DV.TEND_HL" if unidade == "HL" else "DV.TEND_UMB"
            qtd_field = "DV.QTD_TOTAL_HL" if unidade == "HL" else "DV.QTD_TOTAL"
            query = f"""
                SELECT ANO, MES, SUM(TENDENCIA) AS TENDENCIA
                FROM (
                    SELECT LEFT(DV.MES, 4) AS ANO, DV.MES AS MES_ORD, {_expr_mes("DV.MES")} AS MES,
                           ROUND(SUM(CASE WHEN DV.MES = '{mes_atual_sql}' THEN {tend_field} ELSE {qtd_field} END), 0) AS TENDENCIA
                    FROM TB_DIARIO_VENDA DV
                    WHERE DV.CODRED = '{_sql_escapa(codred)}'
                      AND DV.REVENDA IN ({revs_sql})
                      {_sql_in("DV.GA", ga)}
                      {_sql_in("DV.VEN", ven)}
                      {_sql_in("DV.BASE_FOCO", [base] if base else None)}
                    GROUP BY DV.MES, DV.REVENDA
                ) sub
                GROUP BY ANO, MES_ORD, MES
                ORDER BY MES_ORD
            """
            titulo = titulo_override or codred
        else:
            query = f"""
                SELECT ANO, MES, SUM(TENDENCIA) AS TENDENCIA
                FROM (
                    SELECT LEFT(DV.MES, 4) AS ANO, DV.MES AS MES_ORD, {_expr_mes("DV.MES")} AS MES,
                           ROUND(SUM(CASE WHEN DV.MES = '{mes_atual_sql}' THEN DV.TEND_HL ELSE DV.QTD_TOTAL_HL END), 0) AS TENDENCIA
                    FROM TB_DIARIO_VENDA DV
                    WHERE DV.AGRUPAMENTO_VOLUME = '{_sql_escapa(agrupamento or "")}'
                      AND DV.REVENDA IN ({revs_sql})
                      {_sql_in("DV.GA", ga)}
                      {_sql_in("DV.VEN", ven)}
                      {_sql_in("DV.BASE_FOCO", [base] if base else None)}
                    GROUP BY DV.MES, DV.REVENDA
                ) sub
                GROUP BY ANO, MES_ORD, MES
                ORDER BY MES_ORD
            """
            titulo = titulo_override or agrupamento or ""
        tabela = _fonte_parquet_dv(query)
        if tabela.height == 0:
            return None
        return _construir_grafico_historico(tabela, "TENDENCIA", titulo)
    except Exception:
        return None


def historico_cob_familia(
    revenda_query: str,
    codred: str,
    titulo: str | None = None,
    rev: list[str] | None = None,
    base: str | None = None,
    ga: list[str] | None = None,
    ven: list[str] | None = None,
) -> str | None:
    try:
        revs_sql = _sql_lista(_revs_efetivas_tooltip(revenda_query, rev))
        query = f"""
            SELECT ANO, MES, SUM(COBERTURA) AS COBERTURA
            FROM (
                SELECT LEFT(CP.MES, 4) AS ANO, CP.MES AS MES_ORD, {_expr_mes("CP.MES")} AS MES,
                       ROUND(SUM(CP.COB_PROD), 0) AS COBERTURA
                FROM {tabela_cobertura("tb_cob_prod", ga, ven)} CP
                WHERE CP.CODRED = '{_sql_escapa(codred)}'
                  AND CP.REVENDA IN ({revs_sql})
                  {_sql_in("CP.GA", ga)}
                  {_sql_in("CP.VEN", ven)}
                  {_sql_in("CP.BASE_FOCO", [base] if base else None)}
                GROUP BY CP.MES, CP.REVENDA
            ) sub
            GROUP BY ANO, MES_ORD, MES
            ORDER BY MES_ORD
        """
        tabela = _fonte_parquet_dv(query)
        if tabela.height == 0:
            return None
        return _construir_grafico_historico(tabela, "COBERTURA", titulo or codred)
    except Exception:
        return None
