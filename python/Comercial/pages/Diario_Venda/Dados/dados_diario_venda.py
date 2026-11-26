from __future__ import annotations

import os
import re
import threading
from datetime import date
from pathlib import Path

import duckdb
import polars as pl
from loguru import logger

from core.compat import polars_de_duckdb
from core.config import REVENDA_NOME_BD

from .cores_diario_venda import excluir_categorias_dv
from .ordenacao_diario_venda import ordem_categ_dv

PASTA_PARQUET = Path(__file__).parents[3] / "data" / "bd_comercial"


_VENDEDOR_DO_CADASTRO = True
PASTA_PARQUET_CADASTRO = PASTA_PARQUET / "cadastro"


REVENDAS_POR_GRUPO: dict[str, list[str]] = {}


SKUS_CORAL_LN = ("CORAL LN 275ML", "CORAL LN 330ML")
SKU_CORAL_LN = "CORAL LN 275ML / 330ML"


def expandir_revendas_dv(revenda: str, revenda_query: str) -> list[str]:

    revenda_norm = REVENDA_NOME_BD.get(revenda, revenda)
    if revenda_norm in REVENDAS_POR_GRUPO:
        return REVENDAS_POR_GRUPO[revenda_norm]
    return [revenda_norm]


VIEWS_OPCIONAIS_DV = {
    "tb_cmv": "SELECT '' AS REVENDA, '' AS TIPO, '' AS CODR, CAST(NULL AS DOUBLE) AS PRECO WHERE FALSE",
    "tb_meta_fabrica": "SELECT '' AS REVENDA, '' AS MES, '' AS CODRED, CAST(NULL AS DOUBLE) AS VALOR, "
    "CAST(NULL AS DOUBLE) AS VALOR_UMB WHERE FALSE",
    "tb_meta_abp": "SELECT '' AS REVENDA, '' AS MES, CAST(NULL AS DOUBLE) AS VALOR WHERE FALSE",
    "tb_base_foco": "SELECT '' AS VENDEDOR, '' AS LICENCA, '' AS BASE_FOCO WHERE FALSE",
}


TABELAS_PARTICIONADAS_DV = {
    "tb_diario_venda": re.compile(r"^tb_diario_venda_\d{14}$"),
}


_PREFIXOS_NAO_TABELA = ("tmp_", "~$", ".")


_conexao_dv: duckdb.DuckDBPyConnection | None = None
_assinatura_dv: tuple | None = None
_views_dv: set[str] = set()
_montagem_dv = threading.Lock()


def _conexao_dv_pronta() -> duckdb.DuckDBPyConnection | None:

    global _conexao_dv, _assinatura_dv, _views_dv

    por_nome: dict[str, Path] = {}
    assinatura: list[tuple] = []
    pastas = [PASTA_PARQUET]
    if _VENDEDOR_DO_CADASTRO and PASTA_PARQUET_CADASTRO.is_dir():
        pastas.append(PASTA_PARQUET_CADASTRO)
    for pasta in pastas:
        with os.scandir(pasta) as entradas:
            for entrada in entradas:
                if not entrada.name.endswith(".parquet") or entrada.name.startswith(_PREFIXOS_NAO_TABELA):
                    continue
                try:
                    info = entrada.stat()
                except OSError:
                    continue
                por_nome[entrada.name] = Path(entrada.path)
                assinatura.append((pasta.name, entrada.name, info.st_mtime_ns, info.st_size))
    arquivos = list(por_nome.values())
    if not arquivos:
        return None

    chave = tuple(sorted(assinatura))
    if _conexao_dv is not None and _assinatura_dv == chave:
        return _conexao_dv

    with _montagem_dv:
        if _conexao_dv is not None and _assinatura_dv == chave:
            return _conexao_dv

        arquivos.sort()

        particionadas: dict[str, list[Path]] = {nome: [] for nome in TABELAS_PARTICIONADAS_DV}
        soltos = []
        for arquivo in arquivos:
            for nome, padrao in TABELAS_PARTICIONADAS_DV.items():
                if padrao.match(arquivo.stem):
                    particionadas[nome].append(arquivo)
                    break
            else:
                soltos.append(arquivo)

        con = _conexao_dv or duckdb.connect(":memory:")
        montadas: set[str] = set()
        for arquivo in soltos:
            try:
                con.execute(
                    f"CREATE OR REPLACE VIEW {arquivo.stem} AS SELECT * FROM read_parquet('{arquivo.as_posix()}')"
                )
                montadas.add(arquivo.stem)
            except duckdb.Error as exc:
                logger.warning(f"Diario de Venda: {arquivo.name} ignorado nesta montagem -- {exc}")

        for nome, partes in particionadas.items():
            if not partes:
                continue
            lista = ", ".join(f"'{parte.as_posix()}'" for parte in partes)
            try:
                con.execute(
                    f"CREATE OR REPLACE VIEW {nome} AS SELECT * FROM read_parquet([{lista}], union_by_name = true)"
                )
                montadas.add(nome)
            except duckdb.Error as exc:
                logger.warning(f"Diario de Venda: {nome} nao montado nesta montagem -- {exc}")
        presentes = {nome.lower() for nome in montadas}
        for nome, corpo in VIEWS_OPCIONAIS_DV.items():
            if nome.lower() not in presentes:
                con.execute(f"CREATE OR REPLACE VIEW {nome} AS {corpo}")
                montadas.add(nome)

        for antiga in _views_dv - montadas:
            con.execute(f"DROP VIEW IF EXISTS {antiga}")

        _conexao_dv, _assinatura_dv, _views_dv = con, chave, montadas
        return con


def _fonte_parquet_dv(query: str) -> pl.DataFrame:

    global _assinatura_dv

    if True:
        for tentativa in (1, 2):
            con = _conexao_dv_pronta()
            if con is None:
                return pl.DataFrame()

            cursor = con.cursor()
            try:
                tabela = polars_de_duckdb(cursor.sql(query))
            except duckdb.Error:
                if tentativa == 2:
                    raise
                _assinatura_dv = None
                continue
            finally:
                cursor.close()
            return tabela


def _mes_offset(mes: str, meses_atras: int) -> str:

    ano, mm = int(mes[:4]), int(mes[4:6])
    total = ano * 12 + (mm - 1) - meses_atras
    return f"{total // 12:04d}{(total % 12) + 1:02d}"


def _sql_escapa(valor: str) -> str:
    return str(valor).replace("'", "''")


def _sql_lista(valores) -> str:
    return ", ".join(f"'{_sql_escapa(v)}'" for v in valores)


def _sql_in(coluna: str, valores, prefixo: str = "AND") -> str:
    if not valores:
        return ""
    return f"{prefixo} {coluna} IN ({_sql_lista(valores)})"


def tabela_cobertura(tabela: str, ga=None, ven=None) -> str:

    if ven:
        return tabela
    tabela_nivel = f"{tabela}{'_ga' if ga else '_rev'}"
    if (PASTA_PARQUET / f"{tabela_nivel}.parquet").exists():
        return tabela_nivel
    logger.warning(
        f"Diario de Venda: {tabela_nivel}.parquet ausente -- cobertura lida de "
        f"{tabela} (soma por vendedor). Rodar scripts/atualiza_diario_venda.py."
    )
    return tabela


def _coluna_existe(tabela: str, coluna: str) -> bool:

    try:
        return coluna in _fonte_parquet_dv(f"SELECT * FROM {tabela} LIMIT 0").columns
    except duckdb.Error:
        return False


def categorias_dv(
    revenda: str,
    mes: str,
    ven: list[str] | None = None,
    ga: list[str] | None = None,
    rev: list[str] | None = None,
    base: str | None = None,
) -> pl.DataFrame:
    revenda_query = revenda
    revenda = REVENDA_NOME_BD.get(revenda, revenda)

    mes_1 = _mes_offset(mes, 1)
    mes_2 = _mes_offset(mes, 2)
    mes_11 = _mes_offset(mes, 11)
    mes_12 = _mes_offset(mes, 12)
    mes_24 = _mes_offset(mes, 24)

    hoje_mes = date.today().strftime("%Y%m")
    campo_aa_hl = "DV.QTD_TOTAL_HL_AA" if mes == hoje_mes else "DV.QTD_TOTAL_HL"
    campo_aa = "DV.QTD_TOTAL_AA" if mes == hoje_mes else "DV.QTD_TOTAL"
    campo_cob_ano_ant = "CP.COB_CAT_AA" if mes == hoje_mes else "CP.COB_CAT"

    revs_efetivas = expandir_revendas_dv(revenda, revenda_query)
    revs_sql = _sql_lista(revs_efetivas)
    filtro_revenda = f"REVENDA IN ({revs_sql})"
    filtro_revenda_dv = f"DV.REVENDA IN ({revs_sql})"

    rev_exp = None
    if rev:
        expandidas: list[str] = []
        for revenda_selecionada in rev:
            expandidas.extend(expandir_revendas_dv(revenda_selecionada, revenda_query))
        rev_exp = list(dict.fromkeys(expandidas))

    filtro_rev_sel = _sql_in("REVENDA", rev_exp)
    filtro_rev_sel_f = _sql_in("F.REVENDA", rev_exp)
    filtro_ga = _sql_in("GA", ga)
    filtro_ven = _sql_in("VEN", ven)
    filtro_ga_ven_ativo = bool(ga) or bool(ven)

    filtro_base = _sql_in("BASE_FOCO", [base] if base else None)

    expr_rev = "REVENDA"
    expr_dv_rev = "DV.REVENDA"

    expr_sku = f"CASE WHEN SKU_GRUPO IN ({_sql_lista(SKUS_CORAL_LN)}) THEN '{SKU_CORAL_LN}' ELSE SKU_GRUPO END"
    expr_dv_sku = f"CASE WHEN DV.SKU_GRUPO IN ({_sql_lista(SKUS_CORAL_LN)}) THEN '{SKU_CORAL_LN}' ELSE DV.SKU_GRUPO END"

    def _cte_meta_fab(nome: str, coluna: str, campo: str = "VALOR") -> str:
        return f"""
    {nome} AS (
        SELECT G.REVENDA, G.CHAVE, SUM(MF.{campo}) AS META_FAB
        FROM (
            SELECT DISTINCT {expr_dv_rev} AS REVENDA, {coluna} AS CHAVE, DV.CODRED
            FROM DV_FILTRADO DV
            WHERE DV.MES = '{mes}' AND {coluna} IS NOT NULL
        ) G
        JOIN META_FABRICA MF ON MF.REVENDA = G.REVENDA AND MF.CODRED = G.CODRED
        GROUP BY G.REVENDA, G.CHAVE
    ),"""

    ctes_meta_fab = "".join(
        _cte_meta_fab(nome, coluna, campo)
        for nome, coluna, campo in (
            ("MF_TOTAL", "DV.VOLUME_TOTAL", "VALOR"),
            ("MF_MARCA", "DV.MARCA", "VALOR"),
            ("MF_SEGMENTO_1", "DV.SEGMENTO", "VALOR"),
            ("MF_SEGMENTO_2", "DV.SEGMENTO_2", "VALOR"),
            ("MF_SEGMENTO_3", "DV.SEGMENTO_3", "VALOR"),
            ("MF_SKU", expr_dv_sku, "VALOR_UMB"),
        )
    )

    query = f"""
    WITH DV_FILTRADO AS (
        SELECT * FROM TB_DIARIO_VENDA
        WHERE {filtro_revenda}
        {filtro_rev_sel}
        {filtro_ga}
        {filtro_ven}
        {filtro_base}
    ),

    DV_COB_CAT AS (
      SELECT
          MES,
          {expr_rev} AS REVENDA,
          CATEGORIA,
          SUM(COB_CAT)    AS COB_CAT,
          SUM(COB_CAT_AA) AS COB_CAT_AA
      FROM {tabela_cobertura("tb_cob_categ", ga, ven)}
      WHERE {filtro_revenda}
        AND MES IN ('{mes_24}','{mes_12}','{mes_2}','{mes_1}','{mes}')
        {filtro_rev_sel}
        {filtro_ga}
        {filtro_ven}
        {filtro_base}
      GROUP BY MES, {expr_rev}, CATEGORIA
    ),

    META_TOTAL AS (
        SELECT {expr_rev} AS REVENDA, MES, VOLUME_TOTAL, ROUND(SUM(QTD_META_REVENDA_HL),0) AS META_HL
        FROM tb_meta_revenda
        WHERE {filtro_revenda} AND MES = '{mes}' {filtro_ga} {filtro_ven}
        GROUP BY {expr_rev}, MES, VOLUME_TOTAL
    ),

    META_MARCA AS (
        SELECT {expr_rev} AS REVENDA, MES, MARCA, ROUND(SUM(QTD_META_REVENDA_HL),0) AS META_HL
        FROM tb_meta_revenda
        WHERE {filtro_revenda} AND MES = '{mes}' {filtro_ga} {filtro_ven}
        GROUP BY {expr_rev}, MES, MARCA
    ),

    META_SEGMENTO_1 AS (
        SELECT {expr_rev} AS REVENDA, MES, SEGMENTO, ROUND(SUM(QTD_META_REVENDA_HL),0) AS META_HL
        FROM tb_meta_revenda
        WHERE {filtro_revenda} AND MES = '{mes}' {filtro_ga} {filtro_ven}
        GROUP BY {expr_rev}, MES, SEGMENTO
    ),

    META_SEGMENTO_2 AS (
        SELECT {expr_rev} AS REVENDA, MES, SEGMENTO_2, ROUND(SUM(QTD_META_REVENDA_HL),0) AS META_HL
        FROM tb_meta_revenda
        WHERE {filtro_revenda} AND MES = '{mes}' {filtro_ga} {filtro_ven}
        GROUP BY {expr_rev}, MES, SEGMENTO_2
    ),

    META_SEGMENTO_3 AS (
        SELECT {expr_rev} AS REVENDA, MES, SEGMENTO_3, ROUND(SUM(QTD_META_REVENDA_HL),0) AS META_HL
        FROM tb_meta_revenda
        WHERE {filtro_revenda} AND MES = '{mes}' {filtro_ga} {filtro_ven}
        GROUP BY {expr_rev}, MES, SEGMENTO_3
    ),

    META_SKU AS (
        SELECT {expr_rev} AS REVENDA, MES, {expr_sku} AS SKU_GRUPO, ROUND(SUM(QTD_META_REVENDA_UMB),0) AS META_UMB
        FROM tb_meta_revenda
        WHERE {filtro_revenda} AND MES = '{mes}' {filtro_ga} {filtro_ven}
        GROUP BY {expr_rev}, MES, {expr_sku}
    ),

    META_FABRICA AS (
        SELECT {expr_rev} AS REVENDA, MES, CODRED, SUM(VALOR) AS VALOR, SUM(VALOR_UMB) AS VALOR_UMB
        FROM "TB_META_FABRICA"
        WHERE {filtro_revenda} AND MES IN ('{mes}')
        GROUP BY MES, {expr_rev}, CODRED
    ),
{ctes_meta_fab}

    LN_BASE AS (
        SELECT {expr_dv_rev} AS REVENDA, SUM(DV.QTD_TOTAL) AS VOL_LN, MAX(CP.COB_CAT) AS COB_LN
        FROM DV_FILTRADO DV
        LEFT JOIN DV_COB_CAT CP ON CP.MES = DV.MES AND CP.REVENDA = {expr_dv_rev} AND CP.CATEGORIA = DV.SKU_GRUPO
        WHERE {filtro_revenda_dv} AND DV.MES IN ('{mes}') AND DV.SKU_GRUPO IN ('MAR LN 330ML')
        GROUP BY {expr_dv_rev}
    ),

    CP_MARCA AS (
        SELECT MARCA AS CATEGORIA, SUM(QTD_HL) AS QTD FROM tb_compra_prod
        WHERE {filtro_revenda} AND MES = '{mes}' {filtro_rev_sel} GROUP BY MARCA
    ),
    CP_SEGMENTO AS (
        SELECT SEGMENTO AS CATEGORIA, 0 AS QTD FROM tb_compra_prod
        WHERE {filtro_revenda} AND MES = '{mes}' {filtro_rev_sel} GROUP BY SEGMENTO
    ),
    CP_SEGMENTO_2 AS (
        SELECT SEGMENTO_2 AS CATEGORIA, SUM(QTD_HL) AS QTD FROM tb_compra_prod
        WHERE {filtro_revenda} AND MES = '{mes}' {filtro_rev_sel} GROUP BY SEGMENTO_2
    ),
    CP_SEGMENTO_3 AS (
        SELECT SEGMENTO_3 AS CATEGORIA, 0 AS QTD FROM tb_compra_prod
        WHERE {filtro_revenda} AND MES = '{mes}' {filtro_rev_sel} GROUP BY SEGMENTO_3
    ),
    CP_VOL_TOTAL AS (
        SELECT VOLUME_TOTAL AS CATEGORIA, SUM(QTD_HL) AS QTD FROM tb_compra_prod
        WHERE {filtro_revenda} AND MES = '{mes}' {filtro_rev_sel} GROUP BY VOLUME_TOTAL
    ),

    DV_TOTAL AS (
        SELECT
            {expr_dv_rev} AS REVENDA, 'TOTAL' AS NIVEL, DV.VOLUME_TOTAL AS CATEGORIA,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_RETRASADO,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_2}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_2,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_1}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ANT,
            ROUND(COALESCE(MAX(MF.META_FAB), 0), 0) AS META_FAB,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0) AS META_REV,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_ANT,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN {campo_aa_hl} ELSE 0 END), 0) AS VOL_ANO_ANT2,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ATUAL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) AS TEND,
            ROUND(ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) / NULLIF(ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0), 0), 4) AS PERC_TEND,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.VALOR_VENDA ELSE 0 END) / NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0), 2) AS VENDA_HL,
            COALESCE(MAX(CP_VT.QTD), 0) AS PERC_VOL_LN,
            CASE WHEN COALESCE(MAX(CP_VT.QTD), 0) <= 0 THEN 0
                 ELSE ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) - COALESCE(MAX(CP_VT.QTD), 0)
            END AS PERC_COB_LN,
            ROUND(MAX(CASE WHEN DV.MES = '{mes_1}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ANT,
            ROUND(MAX(CASE WHEN DV.MES = '{mes_12}' THEN {campo_cob_ano_ant} ELSE NULL END), 0) AS COB_ANO_ANT,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ATUAL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS FAT
        FROM DV_FILTRADO DV
        LEFT JOIN DV_COB_CAT CP ON CP.MES = DV.MES AND CP.REVENDA = {expr_dv_rev} AND CP.CATEGORIA = DV.VOLUME_TOTAL
        LEFT JOIN META_TOTAL MR ON MR.MES = DV.MES AND MR.REVENDA = {expr_dv_rev} AND MR.VOLUME_TOTAL = DV.VOLUME_TOTAL
        LEFT JOIN MF_TOTAL MF ON MF.REVENDA = {expr_dv_rev} AND MF.CHAVE = DV.VOLUME_TOTAL
        LEFT JOIN CP_VOL_TOTAL CP_VT ON CP_VT.CATEGORIA = DV.VOLUME_TOTAL
        WHERE {filtro_revenda_dv} AND DV.MES IN ('{mes_24}','{mes_2}','{mes_1}','{mes_12}','{mes}','{mes_11}') AND DV.VOLUME_TOTAL IS NOT NULL
        GROUP BY {expr_dv_rev}, DV.VOLUME_TOTAL
    ),

    DV_MARCA AS (
        SELECT
            {expr_dv_rev} AS REVENDA, 'MARCA' AS NIVEL, DV.MARCA AS CATEGORIA,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_RETRASADO,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_2}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_2,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_1}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ANT,
            ROUND(COALESCE(MAX(MF.META_FAB), 0), 0) AS META_FAB,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0) AS META_REV,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_ANT,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN {campo_aa_hl} ELSE 0 END), 0) AS VOL_ANO_ANT2,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ATUAL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) AS TEND,
            ROUND(ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) / NULLIF(ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0), 0), 4) AS PERC_TEND,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.VALOR_VENDA ELSE 0 END) / NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0), 2) AS VENDA_HL,
            COALESCE(MAX(CP_M.QTD), 0) AS PERC_VOL_LN,
            CASE WHEN COALESCE(MAX(CP_M.QTD), 0) <= 0 THEN 0
                 ELSE ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) - COALESCE(MAX(CP_M.QTD), 0)
            END AS PERC_COB_LN,
            ROUND(MAX(CASE WHEN DV.MES = '{mes_1}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ANT,
            ROUND(MAX(CASE WHEN DV.MES = '{mes_12}' THEN {campo_cob_ano_ant} ELSE NULL END), 0) AS COB_ANO_ANT,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ATUAL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS FAT
        FROM DV_FILTRADO DV
        LEFT JOIN DV_COB_CAT CP ON CP.MES = DV.MES AND CP.REVENDA = {expr_dv_rev} AND CP.CATEGORIA = DV.MARCA
        LEFT JOIN META_MARCA MR ON MR.MES = DV.MES AND MR.REVENDA = {expr_dv_rev} AND MR.MARCA = DV.MARCA
        LEFT JOIN MF_MARCA MF ON MF.REVENDA = {expr_dv_rev} AND MF.CHAVE = DV.MARCA
        LEFT JOIN CP_MARCA CP_M ON CP_M.CATEGORIA = DV.MARCA
        WHERE {filtro_revenda_dv} AND DV.MES IN ('{mes_24}','{mes_2}','{mes_1}','{mes_12}','{mes}','{mes_11}') AND DV.MARCA IS NOT NULL
        GROUP BY {expr_dv_rev}, DV.MARCA
    ),

    DV_SEGMENTO_1 AS (
        SELECT
            {expr_dv_rev} AS REVENDA, 'SEGMENTO' AS NIVEL, DV.SEGMENTO AS CATEGORIA,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_RETRASADO,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_2}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_2,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_1}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ANT,
            ROUND(COALESCE(MAX(MF.META_FAB), 0), 0) AS META_FAB,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0) AS META_REV,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_ANT,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN {campo_aa_hl} ELSE 0 END), 0) AS VOL_ANO_ANT2,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ATUAL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) AS TEND,
            ROUND(ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) / NULLIF(ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0), 0), 4) AS PERC_TEND,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.VALOR_VENDA ELSE 0 END) / NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0), 2) AS VENDA_HL,
            COALESCE(MAX(CP_S.QTD), 0) AS PERC_VOL_LN,
            0 AS PERC_COB_LN,
            ROUND(MAX(CASE WHEN DV.MES = '{mes_1}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ANT,
            ROUND(MAX(CASE WHEN DV.MES = '{mes_12}' THEN {campo_cob_ano_ant} ELSE NULL END), 0) AS COB_ANO_ANT,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ATUAL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS FAT
        FROM DV_FILTRADO DV
        LEFT JOIN DV_COB_CAT CP ON CP.MES = DV.MES AND CP.REVENDA = {expr_dv_rev} AND CP.CATEGORIA = DV.SEGMENTO
        LEFT JOIN META_SEGMENTO_1 MR ON MR.MES = DV.MES AND MR.REVENDA = {expr_dv_rev} AND MR.SEGMENTO = DV.SEGMENTO
        LEFT JOIN MF_SEGMENTO_1 MF ON MF.REVENDA = {expr_dv_rev} AND MF.CHAVE = DV.SEGMENTO
        LEFT JOIN CP_SEGMENTO CP_S ON CP_S.CATEGORIA = DV.SEGMENTO
        WHERE {filtro_revenda_dv} AND DV.MES IN ('{mes_24}','{mes_2}','{mes_1}','{mes_12}','{mes}') AND DV.SEGMENTO IS NOT NULL
        GROUP BY {expr_dv_rev}, DV.SEGMENTO
    ),

    DV_SEGMENTO_2 AS (
        SELECT
            {expr_dv_rev} AS REVENDA, 'SEGMENTO_2' AS NIVEL, DV.SEGMENTO_2 AS CATEGORIA,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_RETRASADO,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_2}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_2,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_1}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ANT,
            ROUND(COALESCE(MAX(MF.META_FAB), 0), 0) AS META_FAB,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0) AS META_REV,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_ANT,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN {campo_aa_hl} ELSE 0 END), 0) AS VOL_ANO_ANT2,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ATUAL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) AS TEND,
            ROUND(ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) / NULLIF(ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0), 0), 4) AS PERC_TEND,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.VALOR_VENDA ELSE 0 END) / NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0), 2) AS VENDA_HL,
            COALESCE(MAX(CP_S2.QTD), 0) AS PERC_VOL_LN,
            CASE WHEN COALESCE(MAX(CP_S2.QTD), 0) <= 0 THEN 0
                 ELSE ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) - COALESCE(MAX(CP_S2.QTD), 0)
            END AS PERC_COB_LN,
            ROUND(MAX(CASE WHEN DV.MES = '{mes_1}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ANT,
            ROUND(MAX(CASE WHEN DV.MES = '{mes_12}' THEN {campo_cob_ano_ant} ELSE NULL END), 0) AS COB_ANO_ANT,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ATUAL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS FAT
        FROM DV_FILTRADO DV
        LEFT JOIN DV_COB_CAT CP ON CP.MES = DV.MES AND CP.REVENDA = {expr_dv_rev} AND CP.CATEGORIA = DV.SEGMENTO_2
        LEFT JOIN META_SEGMENTO_2 MR ON MR.MES = DV.MES AND MR.REVENDA = {expr_dv_rev} AND MR.SEGMENTO_2 = DV.SEGMENTO_2
        LEFT JOIN MF_SEGMENTO_2 MF ON MF.REVENDA = {expr_dv_rev} AND MF.CHAVE = DV.SEGMENTO_2
        LEFT JOIN CP_SEGMENTO_2 CP_S2 ON CP_S2.CATEGORIA = DV.SEGMENTO_2
        WHERE {filtro_revenda_dv} AND DV.MES IN ('{mes_24}','{mes_2}','{mes_1}','{mes_12}','{mes}') AND DV.SEGMENTO_2 IS NOT NULL
        GROUP BY {expr_dv_rev}, DV.SEGMENTO_2
    ),

    DV_SEGMENTO_3 AS (
        SELECT
            {expr_dv_rev} AS REVENDA, 'SEGMENTO_3' AS NIVEL, DV.SEGMENTO_3 AS CATEGORIA,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_RETRASADO,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_2}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_2,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_1}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ANT,
            ROUND(COALESCE(MAX(MF.META_FAB), 0), 0) AS META_FAB,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0) AS META_REV,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_ANT,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN {campo_aa_hl} ELSE 0 END), 0) AS VOL_ANO_ANT2,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ATUAL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) AS TEND,
            ROUND(ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) / NULLIF(ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0), 0), 4) AS PERC_TEND,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.VALOR_VENDA ELSE 0 END) / NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0), 2) AS VENDA_HL,
            COALESCE(MAX(CP_S3.QTD), 0) AS PERC_VOL_LN,
            0 AS PERC_COB_LN,
            ROUND(MAX(CASE WHEN DV.MES = '{mes_1}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ANT,
            ROUND(MAX(CASE WHEN DV.MES = '{mes_12}' THEN {campo_cob_ano_ant} ELSE NULL END), 0) AS COB_ANO_ANT,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ATUAL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS FAT
        FROM DV_FILTRADO DV
        LEFT JOIN DV_COB_CAT CP ON CP.MES = DV.MES AND CP.REVENDA = {expr_dv_rev} AND CP.CATEGORIA = DV.SEGMENTO_3
        LEFT JOIN META_SEGMENTO_3 MR ON MR.MES = DV.MES AND MR.REVENDA = {expr_dv_rev} AND MR.SEGMENTO_3 = DV.SEGMENTO_3
        LEFT JOIN MF_SEGMENTO_3 MF ON MF.REVENDA = {expr_dv_rev} AND MF.CHAVE = DV.SEGMENTO_3
        LEFT JOIN CP_SEGMENTO_3 CP_S3 ON CP_S3.CATEGORIA = DV.SEGMENTO_3
        WHERE {filtro_revenda_dv} AND DV.MES IN ('{mes_24}','{mes_2}','{mes_1}','{mes_12}','{mes}') AND DV.SEGMENTO_3 IS NOT NULL
        GROUP BY {expr_dv_rev}, DV.SEGMENTO_3
    ),

    DV_SKU AS (
        SELECT
            {expr_dv_rev} AS REVENDA, 'SKU' AS NIVEL, {expr_dv_sku} AS CATEGORIA,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.QTD_TOTAL ELSE 0 END), 0) AS VOL_ANO_RETRASADO,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_2}' THEN DV.QTD_TOTAL ELSE 0 END), 0) AS VOL_MES_2,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_1}' THEN DV.QTD_TOTAL ELSE 0 END), 0) AS VOL_MES_ANT,
            ROUND(COALESCE(MAX(MF.META_FAB), 0), 0) AS META_FAB,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_UMB ELSE 0 END), 0) AS META_REV,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN DV.QTD_TOTAL ELSE 0 END), 0) AS VOL_ANO_ANT,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN {campo_aa} ELSE 0 END), 0) AS VOL_ANO_ANT2,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL ELSE 0 END), 0) AS VOL_MES_ATUAL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_UMB ELSE 0 END), 0) AS TEND,
            ROUND(ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_UMB ELSE 0 END), 0) / NULLIF(ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_UMB ELSE 0 END), 0), 0), 4) AS PERC_TEND,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.VALOR_VENDA ELSE 0 END) / NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL ELSE 0 END), 0), 2) AS VENDA_HL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL ELSE 0 END) / NULLIF(MAX(LN.VOL_LN),0), 4) AS PERC_VOL_LN,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN CP.COB_CAT ELSE NULL END) / NULLIF(MAX(LN.COB_LN),0), 4) AS PERC_COB_LN,
            ROUND(MAX(CASE WHEN DV.MES = '{mes_1}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ANT,
            ROUND(MAX(CASE WHEN DV.MES = '{mes_12}' THEN {campo_cob_ano_ant} ELSE NULL END), 0) AS COB_ANO_ANT,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ATUAL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS FAT
        FROM DV_FILTRADO DV
        LEFT JOIN DV_COB_CAT CP ON CP.MES = DV.MES AND CP.REVENDA = {expr_dv_rev} AND CP.CATEGORIA = {expr_dv_sku}
        LEFT JOIN META_SKU MR ON MR.MES = DV.MES AND MR.REVENDA = {expr_dv_rev} AND MR.SKU_GRUPO = {expr_dv_sku}
        LEFT JOIN LN_BASE LN ON LN.REVENDA = {expr_dv_rev}
        LEFT JOIN MF_SKU MF ON MF.REVENDA = {expr_dv_rev} AND MF.CHAVE = {expr_dv_sku}
        WHERE {filtro_revenda_dv} AND DV.MES IN ('{mes_24}','{mes_2}','{mes_1}','{mes_12}','{mes}') AND DV.SKU_GRUPO IS NOT NULL
        GROUP BY {expr_dv_rev}, {expr_dv_sku}
    ),

    DV_FATURAMENTO AS (
        SELECT
            {expr_dv_rev} AS REVENDA, 'FATURAMENTO' AS NIVEL, DV.CANAL AS CATEGORIA,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS VOL_ANO_RETRASADO,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_2}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS VOL_MES_2,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_1}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS VOL_MES_ANT,
            0 AS META_FAB, 0 AS META_REV,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS VOL_ANO_ANT,
            0 AS VOL_ANO_ANT2,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS VOL_MES_ATUAL,
            0 AS TEND, 0 AS PERC_TEND, 0 AS VENDA_HL, 0 AS PERC_VOL_LN, 0 AS PERC_COB_LN,
            0 AS COB_MES_ANT, 0 AS COB_ANO_ANT, 0 AS COB_MES_ATUAL, 0 AS FAT
        FROM DV_FILTRADO DV
        WHERE {filtro_revenda_dv} AND DV.MES IN ('{mes_24}','{mes_2}','{mes_1}','{mes_12}','{mes}') AND DV.CANAL IN ('OW', 'RGB')
        GROUP BY {expr_dv_rev}, DV.CANAL
    ),

    MARÉ_600 AS (SELECT MES, SUM(COB_CAT) AS COB_CAT FROM DV_COB_CAT WHERE CATEGORIA = 'MARÉ 600ml' GROUP BY MES),
    CORAL_600   AS (SELECT MES, SUM(COB_CAT) AS COB_CAT FROM DV_COB_CAT WHERE CATEGORIA = 'CORAL 600ml' GROUP BY MES),
    MARÉ_0   AS (SELECT MES, SUM(COB_CAT) AS COB_CAT FROM DV_COB_CAT WHERE CATEGORIA = '0%' GROUP BY MES),
    MARÉ_CAT AS (SELECT MES, SUM(COB_CAT) AS COB_CAT FROM DV_COB_CAT WHERE CATEGORIA = 'MARÉ' GROUP BY MES),
    RGB_TOTAL    AS (SELECT MES, SUM(COB_CAT) AS COB_CAT FROM DV_COB_CAT WHERE CATEGORIA = 'RGB' GROUP BY MES),

    BASE_IND AS (
        SELECT '{revenda}' AS REVENDA, R.MES, 'PERC_CORAL_MAR_600' AS INDICADOR, A600.COB_CAT / NULLIF(H600.COB_CAT, 0) AS VALOR, 60 AS META
        FROM RGB_TOTAL R LEFT JOIN MARÉ_600 H600 ON H600.MES = R.MES LEFT JOIN CORAL_600 A600 ON A600.MES = R.MES
        UNION ALL
        SELECT '{revenda}' AS REVENDA, R.MES, 'PERC_MARÉ_600_RGB' AS INDICADOR, H600.COB_CAT / NULLIF(R.COB_CAT, 0) AS VALOR, 70 AS META
        FROM RGB_TOTAL R LEFT JOIN MARÉ_600 H600 ON H600.MES = R.MES
        UNION ALL
        SELECT '{revenda}' AS REVENDA, R.MES, 'PERC_MARÉ_0_TT' AS INDICADOR, H0.COB_CAT / NULLIF(HC.COB_CAT, 0) AS VALOR, 40 AS META
        FROM RGB_TOTAL R LEFT JOIN MARÉ_0 H0 ON H0.MES = R.MES LEFT JOIN MARÉ_CAT HC ON HC.MES = R.MES
    ),

    INDI AS (
        SELECT
            REVENDA, 'INDICADOR' AS NIVEL, INDICADOR AS CATEGORIA,
            ROUND(MAX(CASE WHEN MES = '{mes_24}' THEN VALOR END) * 100, 2) AS VOL_ANO_RETRASADO,
            ROUND(MAX(CASE WHEN MES = '{mes_2}' THEN VALOR END) * 100, 2) AS VOL_MES_2,
            ROUND(MAX(CASE WHEN MES = '{mes_1}' THEN VALOR END) * 100, 2) AS VOL_MES_ANT,
            0 AS META_FAB, MAX(META) AS META_REV,
            ROUND(MAX(CASE WHEN MES = '{mes_12}' THEN VALOR END) * 100, 2) AS VOL_ANO_ANT,
            0 AS VOL_ANO_ANT2,
            ROUND(MAX(CASE WHEN MES = '{mes}' THEN VALOR END) * 100, 2) AS VOL_MES_ATUAL,
            0 AS TEND, 0 AS PERC_TEND, 0 AS VENDA_HL, 0 AS PERC_VOL_LN, 0 AS PERC_COB_LN,
            0 AS COB_MES_ANT, 0 AS COB_ANO_ANT, 0 AS COB_MES_ATUAL, 0 AS FAT
        FROM BASE_IND
        GROUP BY REVENDA, INDICADOR
    )

    SELECT * FROM DV_TOTAL
    UNION ALL SELECT * FROM DV_MARCA
    UNION ALL SELECT * FROM DV_SEGMENTO_1
    UNION ALL SELECT * FROM DV_SEGMENTO_2
    UNION ALL SELECT * FROM DV_SKU
    UNION ALL SELECT * FROM DV_SEGMENTO_3
    UNION ALL SELECT * FROM INDI
    UNION ALL SELECT * FROM DV_FATURAMENTO
    """
    tabela_final = _fonte_parquet_dv(query)

    revs_sql_upper = _sql_lista([r.upper() for r in revs_efetivas])
    filtro_revenda_upper = f"UPPER(REVENDA) IN ({revs_sql_upper})"
    filtro_rev_sel_upper = _sql_in("UPPER(REVENDA)", [r.upper() for r in rev_exp]) if rev_exp else ""

    if filtro_ga_ven_ativo:
        query_skupdv_rev = f"""
        WITH PDV_ATENDIDO AS (
            SELECT REVENDA, MES, SUM(QTD_PDV) AS PDV_ATENDIDO
            FROM tb_cob_cli_ativo
            WHERE {filtro_revenda} AND MES IN ('{mes_2}', '{mes_1}', '{mes}') {filtro_rev_sel} {filtro_ga} {filtro_ven} {filtro_base}
            GROUP BY REVENDA, MES
        ),
        QTD_SKU_VEN AS (
            SELECT REVENDA, MES, SUM(QTD_SKU_PDV) AS QTD_SKU_PDV
            FROM tb_cob_cli
            WHERE {filtro_revenda} AND MES IN ('{mes_2}', '{mes_1}', '{mes}') {filtro_rev_sel} {filtro_ga} {filtro_ven} {filtro_base}
            GROUP BY REVENDA, MES
        ),
        BASE AS (
            SELECT PA.REVENDA, PA.MES, COALESCE(SV.QTD_SKU_PDV, 0) AS QTD_SKU_PDV, PA.PDV_ATENDIDO AS META_REVENDA
            FROM PDV_ATENDIDO PA LEFT JOIN QTD_SKU_VEN SV ON SV.REVENDA = PA.REVENDA AND SV.MES = PA.MES
        )
        SELECT
            '{revenda}' AS REVENDA, 'INDICADOR' AS NIVEL, 'SKU/PDV REVENDA' AS CATEGORIA,
            0 AS VOL_ANO_RETRASADO,
            ROUND(SUM(CASE WHEN MES = '{mes_2}' THEN QTD_SKU_PDV ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes_2}' THEN META_REVENDA ELSE 0 END), 0), 2) AS VOL_MES_2,
            ROUND(SUM(CASE WHEN MES = '{mes_1}' THEN QTD_SKU_PDV ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes_1}' THEN META_REVENDA ELSE 0 END), 0), 2) AS VOL_MES_ANT,
            0 AS META_FAB, 5.0 AS META_REV, 0 AS VOL_ANO_ANT, 0 AS VOL_ANO_ANT2,
            ROUND(SUM(CASE WHEN MES = '{mes}' THEN QTD_SKU_PDV ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes}' THEN META_REVENDA ELSE 0 END), 0), 2) AS VOL_MES_ATUAL,
            0 AS TEND, 0 AS PERC_TEND, 0 AS VENDA_HL, 0 AS PERC_VOL_LN, 0 AS PERC_COB_LN,
            0 AS COB_MES_ANT, 0 AS COB_ANO_ANT, 0 AS COB_MES_ATUAL, 0 AS FAT
        FROM BASE
        """
        tabela_final_skupdv = _fonte_parquet_dv(query_skupdv_rev)

        query_fds_rev = f"""
        SELECT
            '{revenda}' AS REVENDA, 'INDICADOR' AS NIVEL, 'FDS REVENDA' AS CATEGORIA,
            0 AS VOL_ANO_RETRASADO,
            ROUND(SUM(CASE WHEN MES = '{mes_2}' THEN GRUPOS_META ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes_2}' THEN TOTAL_GRUPOS ELSE 0 END), 0) * 100, 2) AS VOL_MES_2,
            ROUND(SUM(CASE WHEN MES = '{mes_1}' THEN GRUPOS_META ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes_1}' THEN TOTAL_GRUPOS ELSE 0 END), 0) * 100, 2) AS VOL_MES_ANT,
            0 AS META_FAB, 50 AS META_REV, 0 AS VOL_ANO_ANT, 0 AS VOL_ANO_ANT2,
            ROUND(SUM(CASE WHEN MES = '{mes}' THEN GRUPOS_META ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes}' THEN TOTAL_GRUPOS ELSE 0 END), 0) * 100, 2) AS VOL_MES_ATUAL,
            0 AS TEND, 0 AS PERC_TEND, 0 AS VENDA_HL, 0 AS PERC_VOL_LN, 0 AS PERC_COB_LN,
            0 AS COB_MES_ANT, 0 AS COB_ANO_ANT, 0 AS COB_MES_ATUAL, 0 AS FAT
        FROM tb_exig_fds
        WHERE {filtro_revenda} AND MES IN ('{mes_2}', '{mes_1}', '{mes}') {filtro_rev_sel} {filtro_ga} {filtro_ven}
        """
        tabela_final_fds = _fonte_parquet_dv(query_fds_rev)
    else:
        rev_norm_sql = "REVENDA"

        query_skupdv_abp = f"""
        WITH META_ABP AS (
            SELECT REVENDA, MES, SUM(VALOR) AS META_ABP
            FROM "TB_META_ABP"
            WHERE {filtro_revenda_upper} AND MES IN ('{mes_2}', '{mes_1}', '{mes}') {filtro_rev_sel_upper}
            GROUP BY REVENDA, MES
        ),
        QTD_SKU AS (
            SELECT {rev_norm_sql} AS REVENDA, MES, SUM(QTD_SKU_PDV) AS QTD_SKU_PDV
            FROM tb_cob_cli
            WHERE {filtro_revenda} AND MES IN ('{mes_2}', '{mes_1}', '{mes}') {filtro_rev_sel} {filtro_base}
            GROUP BY 1, 2
        ),
        BASE AS (
            SELECT MA.REVENDA, MA.MES, COALESCE(SV.QTD_SKU_PDV, 0) AS QTD_SKU_PDV, MA.META_ABP
            FROM META_ABP MA LEFT JOIN QTD_SKU SV ON SV.REVENDA = MA.REVENDA AND SV.MES = MA.MES
        )
        SELECT
            '{revenda}' AS REVENDA, 'INDICADOR' AS NIVEL, 'SKU/PDV ABP' AS CATEGORIA,
            0 AS VOL_ANO_RETRASADO,
            ROUND(SUM(CASE WHEN MES = '{mes_2}' THEN QTD_SKU_PDV ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes_2}' THEN META_ABP ELSE 0 END), 0), 2) AS VOL_MES_2,
            ROUND(SUM(CASE WHEN MES = '{mes_1}' THEN QTD_SKU_PDV ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes_1}' THEN META_ABP ELSE 0 END), 0), 2) AS VOL_MES_ANT,
            0 AS META_FAB, 5.0 AS META_REV, 0 AS VOL_ANO_ANT, 0 AS VOL_ANO_ANT2,
            ROUND(SUM(CASE WHEN MES = '{mes}' THEN QTD_SKU_PDV ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes}' THEN META_ABP ELSE 0 END), 0), 2) AS VOL_MES_ATUAL,
            0 AS TEND, 0 AS PERC_TEND, 0 AS VENDA_HL, 0 AS PERC_VOL_LN, 0 AS PERC_COB_LN,
            0 AS COB_MES_ANT, 0 AS COB_ANO_ANT, 0 AS COB_MES_ATUAL, 0 AS FAT
        FROM BASE
        """
        tabela_final_skupdv = _fonte_parquet_dv(query_skupdv_abp)

        query_fds_abp = f"""
        SELECT
            '{revenda}' AS REVENDA, 'INDICADOR' AS NIVEL, 'FDS ABP' AS CATEGORIA,
            0 AS VOL_ANO_RETRASADO,
            ROUND(SUM(CASE WHEN F.MES = '{mes_2}' THEN F.GRUPOS_META ELSE 0 END) / NULLIF(MAX(CASE WHEN F.MES = '{mes_2}' THEN M.META_FDS END) * 100, 0) * 100, 2) AS VOL_MES_2,
            ROUND(SUM(CASE WHEN F.MES = '{mes_1}' THEN F.GRUPOS_META ELSE 0 END) / NULLIF(MAX(CASE WHEN F.MES = '{mes_1}' THEN M.META_FDS END) * 100, 0) * 100, 2) AS VOL_MES_ANT,
            0 AS META_FAB, 50 AS META_REV, 0 AS VOL_ANO_ANT, 0 AS VOL_ANO_ANT2,
            ROUND(SUM(CASE WHEN F.MES = '{mes}' THEN F.GRUPOS_META ELSE 0 END) / NULLIF(MAX(CASE WHEN F.MES = '{mes}' THEN M.META_FDS END) * 100, 0) * 100, 2) AS VOL_MES_ATUAL,
            0 AS TEND, 0 AS PERC_TEND, 0 AS VENDA_HL, 0 AS PERC_VOL_LN, 0 AS PERC_COB_LN,
            0 AS COB_MES_ANT, 0 AS COB_ANO_ANT, 0 AS COB_MES_ATUAL, 0 AS FAT
        FROM tb_exig_fds F
        JOIN (
            SELECT C.REVENDA, C.MES,
                CASE WHEN A.VALOR IS NULL OR A.VALOR = 0 THEN C.QTD_PDV ELSE A.VALOR END AS META_FDS
            FROM (
                SELECT REVENDA, MES, SUM(QTD_PDV) AS QTD_PDV
                FROM tb_cob_rev
                WHERE REVENDA IN ({revs_sql}) AND MES IN ('{mes_2}', '{mes_1}', '{mes}') {filtro_base}
                GROUP BY REVENDA, MES
            ) C
            LEFT JOIN "TB_META_ABP" A ON A.REVENDA = C.REVENDA AND A.MES = C.MES
        ) M ON M.REVENDA = F.REVENDA AND M.MES = F.MES
        WHERE F.REVENDA IN ({revs_sql}) AND F.MES IN ('{mes_2}', '{mes_1}', '{mes}') {filtro_rev_sel_f}
        """
        tabela_final_fds = _fonte_parquet_dv(query_fds_abp)

    if tabela_final_skupdv.height > 0:
        tabela_final = pl.concat([tabela_final, tabela_final_skupdv], how="diagonal_relaxed")
    if tabela_final_fds.height > 0:
        tabela_final = pl.concat([tabela_final, tabela_final_fds], how="diagonal_relaxed")

    if len(revs_efetivas) > 1:
        tabela_final = _reagrega_categorias(tabela_final, revenda)

    tabela_final = tabela_final.with_columns(
        pl.col("CATEGORIA").replace(
            {
                "PERC_CORAL_MAR_600": "CORAL 600/MAR 600",
                "PERC_MARÉ_600_RGB": "MAR 600/RGB TT",
                "PERC_MARÉ_0_TT": "MAR 0.0%/MAR TT",
                "OW": "FATURAMENTO OW",
                "RGB": "FATURAMENTO RGB",
            }
        )
    )

    ordem = ordem_categ_dv()
    excluidas = excluir_categorias_dv(revenda)
    tabela_final = tabela_final.filter(pl.col("CATEGORIA").is_in(ordem) & ~pl.col("CATEGORIA").is_in(excluidas))
    return tabela_final


def _reagrega_categorias(tabela: pl.DataFrame, revenda: str) -> pl.DataFrame:

    tabela = tabela.with_columns(
        pl.when((pl.col("VENDA_HL").is_not_null()) & (pl.col("VOL_MES_ATUAL") > 0))
        .then(pl.col("VENDA_HL") * pl.col("VOL_MES_ATUAL"))
        .alias("_valor_hl_pond"),
        pl.when((pl.col("VENDA_HL").is_not_null()) & (pl.col("VOL_MES_ATUAL") > 0))
        .then(pl.col("VOL_MES_ATUAL"))
        .alias("_vol_hl_pond"),
        pl.when((pl.col("PERC_VOL_LN") > 0) & (pl.col("VOL_MES_ATUAL") > 0))
        .then(pl.col("VOL_MES_ATUAL") / pl.col("PERC_VOL_LN"))
        .alias("_vol_ln_back"),
        pl.when((pl.col("PERC_VOL_LN") > 0) & (pl.col("VOL_MES_ATUAL") > 0))
        .then(pl.col("VOL_MES_ATUAL"))
        .alias("_vol_sku_ln"),
        pl.when((pl.col("PERC_COB_LN") > 0) & (pl.col("COB_MES_ATUAL").is_not_null()) & (pl.col("COB_MES_ATUAL") > 0))
        .then(pl.col("COB_MES_ATUAL") / pl.col("PERC_COB_LN"))
        .alias("_cob_ln_back"),
        pl.when((pl.col("PERC_COB_LN") > 0) & (pl.col("COB_MES_ATUAL").is_not_null()) & (pl.col("COB_MES_ATUAL") > 0))
        .then(pl.col("COB_MES_ATUAL"))
        .alias("_cob_sku_ln"),
    )

    agregada = tabela.group_by(["NIVEL", "CATEGORIA"], maintain_order=True).agg(
        pl.col("VOL_ANO_RETRASADO").sum().fill_null(0).alias("_soma_var"),
        pl.col("VOL_ANO_RETRASADO").first().alias("_first_vol_ano_retrasado"),
        pl.col("VOL_MES_2").sum().fill_null(0).alias("_soma_vol_mes_2"),
        pl.col("VOL_MES_2").first().alias("_first_vol_mes_2"),
        pl.col("VOL_MES_ANT").sum().fill_null(0).alias("_soma_vol_mes_ant"),
        pl.col("VOL_MES_ANT").first().alias("_first_vol_mes_ant"),
        pl.col("META_FAB").sum().fill_null(0).alias("_soma_meta_fab"),
        pl.col("META_REV").max().alias("_max_meta_rev"),
        pl.col("META_REV").sum().fill_null(0).alias("_soma_meta_rev"),
        pl.col("VOL_ANO_ANT").sum().fill_null(0).alias("_soma_vol_ano_ant"),
        pl.col("VOL_ANO_ANT").first().alias("_first_vol_ano_ant"),
        pl.col("VOL_ANO_ANT2").sum().fill_null(0).alias("_soma_vol_ano_ant2"),
        pl.col("VOL_MES_ATUAL").sum().fill_null(0).alias("_soma_vol_mes_atual"),
        pl.col("VOL_MES_ATUAL").first().alias("_first_vol_mes_atual"),
        pl.col("TEND").sum().fill_null(0).alias("_soma_tend"),
        pl.col("_valor_hl_pond").sum().alias("_soma_valor_hl_pond"),
        pl.col("_vol_hl_pond").sum().alias("_soma_vol_hl_pond"),
        pl.col("_vol_ln_back").sum().alias("_soma_vol_ln_back"),
        pl.col("_vol_sku_ln").sum().alias("_soma_vol_sku_ln"),
        pl.col("_cob_ln_back").sum().alias("_soma_cob_ln_back"),
        pl.col("_cob_sku_ln").sum().alias("_soma_cob_sku_ln"),
        pl.col("COB_MES_ANT").sum().alias("_soma_cob_mes_ant"),
        pl.col("COB_MES_ANT").null_count().alias("_null_cob_mes_ant"),
        pl.col("COB_ANO_ANT").sum().alias("_soma_cob_ano_ant"),
        pl.col("COB_ANO_ANT").null_count().alias("_null_cob_ano_ant"),
        pl.col("COB_MES_ATUAL").sum().alias("_soma_cob_mes_atual"),
        pl.col("COB_MES_ATUAL").null_count().alias("_null_cob_mes_atual"),
        pl.len().alias("_n"),
        pl.col("FAT").sum().fill_null(0).alias("_soma_fat"),
    )

    eh_indicador = pl.col("NIVEL") == "INDICADOR"
    eh_indicador_ou_fat = pl.col("NIVEL").is_in(["INDICADOR", "FATURAMENTO"])
    eh_sku = pl.col("NIVEL") == "SKU"

    agregada = agregada.with_columns(
        pl.lit(revenda).alias("REVENDA"),
        pl.when(eh_indicador)
        .then(pl.col("_first_vol_ano_retrasado"))
        .otherwise(pl.col("_soma_var"))
        .alias("VOL_ANO_RETRASADO"),
        pl.when(eh_indicador).then(pl.col("_first_vol_mes_2")).otherwise(pl.col("_soma_vol_mes_2")).alias("VOL_MES_2"),
        pl.when(eh_indicador)
        .then(pl.col("_first_vol_mes_ant"))
        .otherwise(pl.col("_soma_vol_mes_ant"))
        .alias("VOL_MES_ANT"),
        pl.when(eh_indicador).then(None).otherwise(pl.col("_soma_meta_fab")).alias("META_FAB"),
        pl.when(eh_indicador).then(pl.col("_max_meta_rev")).otherwise(pl.col("_soma_meta_rev")).alias("META_REV"),
        pl.when(eh_indicador)
        .then(pl.col("_first_vol_ano_ant"))
        .otherwise(pl.col("_soma_vol_ano_ant"))
        .alias("VOL_ANO_ANT"),
        pl.when(eh_indicador).then(None).otherwise(pl.col("_soma_vol_ano_ant2")).alias("VOL_ANO_ANT2"),
        pl.when(eh_indicador)
        .then(pl.col("_first_vol_mes_atual"))
        .otherwise(pl.col("_soma_vol_mes_atual"))
        .alias("VOL_MES_ATUAL"),
        pl.when(eh_indicador_ou_fat).then(None).otherwise(pl.col("_soma_tend")).alias("TEND"),
        pl.when(pl.col("_soma_vol_hl_pond") > 0)
        .then((pl.col("_soma_valor_hl_pond") / pl.col("_soma_vol_hl_pond")).round(2))
        .otherwise(None)
        .alias("VENDA_HL"),
        pl.when(pl.col("_soma_vol_ln_back") > 0)
        .then((pl.col("_soma_vol_sku_ln") / pl.col("_soma_vol_ln_back")).round(4))
        .otherwise(None)
        .alias("PERC_VOL_LN"),
        pl.when(eh_sku & (pl.col("_soma_cob_ln_back") > 0))
        .then((pl.col("_soma_cob_sku_ln") / pl.col("_soma_cob_ln_back")).round(4))
        .otherwise(None)
        .alias("_perc_cob_ln_sku"),
        pl.when(pl.col("_null_cob_mes_ant") == pl.col("_n"))
        .then(None)
        .otherwise(pl.col("_soma_cob_mes_ant"))
        .alias("COB_MES_ANT"),
        pl.when(pl.col("_null_cob_ano_ant") == pl.col("_n"))
        .then(None)
        .otherwise(pl.col("_soma_cob_ano_ant"))
        .alias("COB_ANO_ANT"),
        pl.when(pl.col("_null_cob_mes_atual") == pl.col("_n"))
        .then(None)
        .otherwise(pl.col("_soma_cob_mes_atual"))
        .alias("COB_MES_ATUAL"),
        pl.when(eh_indicador_ou_fat).then(None).otherwise(pl.col("_soma_fat")).alias("FAT"),
    )

    agregada = agregada.with_columns(
        pl.when(eh_sku)
        .then(pl.col("_perc_cob_ln_sku"))
        .otherwise(
            pl.when(pl.col("PERC_VOL_LN").is_null())
            .then(None)
            .otherwise(pl.col("VOL_MES_ATUAL") - pl.col("PERC_VOL_LN"))
        )
        .alias("PERC_COB_LN")
    ).with_columns(
        pl.when(pl.col("META_REV") > 0).then(pl.col("TEND") / pl.col("META_REV")).otherwise(None).alias("PERC_TEND")
    )

    return agregada.select(
        "REVENDA",
        "NIVEL",
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
        "PERC_TEND",
        "VENDA_HL",
        "PERC_VOL_LN",
        "PERC_COB_LN",
        "COB_MES_ANT",
        "COB_ANO_ANT",
        "COB_MES_ATUAL",
        "FAT",
    )


def familia_dv(
    revenda: str,
    mes: str,
    ven: list[str] | None = None,
    ga: list[str] | None = None,
    rev: list[str] | None = None,
    agrupamento_nulo: bool = False,
    base: str | None = None,
) -> pl.DataFrame:
    revenda_query = revenda
    revenda = REVENDA_NOME_BD.get(revenda, revenda)

    mes_1 = _mes_offset(mes, 1)
    mes_2 = _mes_offset(mes, 2)
    mes_12 = _mes_offset(mes, 12)
    mes_24 = _mes_offset(mes, 24)

    hoje_mes = date.today().strftime("%Y%m")
    campo_aa_hl = "DV.QTD_TOTAL_HL_AA" if mes == hoje_mes else "DV.QTD_TOTAL_HL"
    campo_aa = "DV.QTD_TOTAL_AA" if mes == hoje_mes else "DV.QTD_TOTAL"

    if agrupamento_nulo:
        prod_agr_select = "MAX(AGRUPAMENTO_VOLUME) AS AGRUPAMENTO_VOLUME"
        filtro_agr_prod = "AND AGRUPAMENTO_VOLUME IS NULL AND VOLUME_TOTAL IS NOT NULL AND CODCOMP IS NOT NULL"
        prod_agr_having = ""
    else:
        prod_agr_select = (
            "COALESCE(MAX(AGRUPAMENTO_VOLUME), "
            f"CASE WHEN MAX(VOLUME_TOTAL) IS NULL AND SUM(CASE WHEN MES = '{mes}' THEN FATURAMENTO ELSE 0 END) > 0 "
            "THEN 'NOVO PRODUTO' END) AS AGRUPAMENTO_VOLUME"
        )
        filtro_agr_prod = (
            "AND ((AGRUPAMENTO_VOLUME IS NOT NULL AND CODCOMP IS NOT NULL) "
            "OR (VOLUME_TOTAL IS NULL AND AGRUPAMENTO_VOLUME IS NULL))"
        )
        prod_agr_having = (
            f"HAVING MAX(AGRUPAMENTO_VOLUME) IS NOT NULL OR (MAX(VOLUME_TOTAL) IS NULL "
            f"AND SUM(CASE WHEN MES = '{mes}' THEN FATURAMENTO ELSE 0 END) > 0)"
        )

    revs_efetivas = expandir_revendas_dv(revenda, revenda_query)
    revs_sql = _sql_lista(revs_efetivas)
    filtro_revenda = f"REVENDA IN ({revs_sql})"
    filtro_revenda_ref = f"REF.REVENDA IN ({revs_sql})"

    rev_exp_fam = None
    if rev:
        rev_exp_fam = []
        for r in rev:
            rev_exp_fam.extend(expandir_revendas_dv(r, revenda_query))
        rev_exp_fam = list(dict.fromkeys(rev_exp_fam))
    filtro_rev_sel = _sql_in("REVENDA", rev_exp_fam)
    filtro_ga = _sql_in("GA", ga)
    filtro_ven = _sql_in("VEN", ven)

    filtro_base = _sql_in("BASE_FOCO", [base] if base else None)

    expr_rev = "REVENDA"
    expr_dv_rev = "DV.REVENDA"

    tabela_cob_prod = tabela_cobertura("tb_cob_prod", ga, ven)
    campo_cob_ano_ant = "CP.COB_PROD"
    soma_cob_aa = ""
    if mes == hoje_mes:
        if _coluna_existe(tabela_cob_prod, "COB_PROD_AA"):
            campo_cob_ano_ant = "CP.COB_PROD_AA"
            soma_cob_aa = ", SUM(COB_PROD_AA) AS COB_PROD_AA"
        else:
            logger.warning(
                f"Diario de Venda: {tabela_cob_prod} sem COB_PROD_AA -- cobertura do ano anterior "
                "da Familia com o mes cheio. Rodar scripts/atualiza_diario_venda.py."
            )

    query = f"""
    WITH DV_FILTRADO AS (
        SELECT * FROM TB_DIARIO_VENDA
        WHERE {filtro_revenda} {filtro_rev_sel} {filtro_ga} {filtro_ven} {filtro_base}
    ),

    DV_COB_PROD AS (
        SELECT MES, {expr_rev} AS REVENDA, CODRED, SUM(COB_PROD) AS COB_PROD{soma_cob_aa}
        FROM {tabela_cob_prod}
        WHERE {filtro_revenda} AND MES IN ('{mes_12}', '{mes_1}', '{mes}') {filtro_rev_sel} {filtro_ga} {filtro_ven} {filtro_base}
        GROUP BY MES, {expr_rev}, CODRED
    ),

    CMV_SKU AS (
        SELECT {expr_rev} AS REVENDA, CODR AS CODRED, SUM(PRECO) AS PRECO
        FROM tb_cmv
        WHERE {filtro_revenda}
        GROUP BY {expr_rev}, CODR
    ),

    META_FABRICA AS (
        SELECT {expr_rev} AS REVENDA, CODRED, SUM(VALOR) AS VALOR, SUM(VALOR_UMB) AS VALOR_UMB
        FROM "TB_META_FABRICA"
        WHERE {filtro_revenda} AND MES = '{mes}'
        GROUP BY {expr_rev}, CODRED
    ),

    META_SKU AS (
        SELECT
            {expr_rev} AS REVENDA, MES, AGRUPAMENTO_VOLUME, CODRED,
            ROUND(SUM(QTD_META_REVENDA_UMB), 0) AS META_UMB,
            ROUND(SUM(QTD_META_REVENDA_HL),  0) AS META_HL
        FROM tb_meta_revenda
        WHERE {filtro_revenda} AND MES = '{mes}' {filtro_ga} {filtro_ven}
        GROUP BY {expr_rev}, MES, AGRUPAMENTO_VOLUME, CODRED
    ),

    PROD_REF AS (
        SELECT {expr_rev} AS REVENDA, CODRED, {prod_agr_select}, MAX(PRODUTO) AS PRODUTO
        FROM DV_FILTRADO
        WHERE {filtro_revenda} AND CODRED IS NOT NULL AND TRIM(CODRED) != '' {filtro_agr_prod}
        GROUP BY {expr_rev}, CODRED
        {prod_agr_having}
    ),

    DV_SKU AS (
        SELECT
            REF.REVENDA, REF.AGRUPAMENTO_VOLUME, REF.CODRED,
            CONCAT(REF.CODRED, ' - ', COALESCE(REF.PRODUTO, '')) AS PRODUTO,

            ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.QTD_TOTAL ELSE 0 END), 0) AS VOL_ANO_RETRASADO_UMB,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_2}'  THEN DV.QTD_TOTAL ELSE 0 END), 0) AS VOL_MES_2_UMB,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_1}'  THEN DV.QTD_TOTAL ELSE 0 END), 0) AS VOL_MES_ANT_UMB,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}'    THEN MR.META_UMB ELSE 0 END), 0)  AS META_REV_UMB,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN DV.QTD_TOTAL ELSE 0 END), 0) AS VOL_ANO_ANT_UMB,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN {campo_aa}   ELSE 0 END), 0) AS VOL_ANO_ANT2_UMB,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}'    THEN DV.QTD_TOTAL ELSE 0 END), 0) AS VOL_MES_ATUAL_UMB,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}'    THEN DV.TEND_UMB  ELSE 0 END), 0) AS TEND_UMB,
            ROUND(ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_UMB ELSE 0 END), 0) / NULLIF(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_UMB ELSE 0 END), 0), 4) AS PERC_TEND_UMB,

            ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_RETRASADO_HL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_2}'  THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_2_HL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_1}'  THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ANT_HL,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}'    THEN MR.META_HL  ELSE 0 END), 0)     AS META_REV_HL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_ANT_HL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN {campo_aa_hl}   ELSE 0 END), 0) AS VOL_ANO_ANT2_HL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}'    THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ATUAL_HL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}'    THEN DV.TEND_HL      ELSE 0 END), 0) AS TEND_HL,
            ROUND(ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) / NULLIF(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0), 4) AS PERC_TEND_HL,

            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END) / NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL ELSE 0 END), 0), 2) AS PRECO_MEDIO,
            ROUND((
                (SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END) / NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL ELSE 0 END), 0))
                / NULLIF(MAX(CASE WHEN DV.MES = '{mes}' THEN CMV.PRECO END), 0)
            ) - 1, 4) AS PERC_MKP,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.VALOR_VENDA ELSE 0 END) / NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0), 2) AS VENDA_HL,

            ROUND(MAX(CASE WHEN DV.MES = '{mes_1}'  THEN CP.COB_PROD ELSE NULL END), 0) AS COB_MES_ANT,
            ROUND(MAX(CASE WHEN DV.MES = '{mes_12}' THEN {campo_cob_ano_ant} ELSE NULL END), 0) AS COB_ANO_ANT,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}'    THEN CP.COB_PROD ELSE NULL END), 0) AS COB_MES_ATUAL,

            ROUND(COALESCE(MAX(MF.VALOR),     0), 0) AS META_FAB_HL,
            ROUND(COALESCE(MAX(MF.VALOR_UMB), 0), 0) AS META_FAB_UMB,

            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS FAT

        FROM PROD_REF REF
        LEFT JOIN DV_FILTRADO DV
            ON DV.CODRED = REF.CODRED AND {expr_dv_rev} = REF.REVENDA
           AND DV.MES IN ('{mes_24}', '{mes_2}', '{mes_1}', '{mes_12}', '{mes}')
        LEFT JOIN DV_COB_PROD CP ON CP.MES = DV.MES AND CP.REVENDA = {expr_dv_rev} AND CP.CODRED = DV.CODRED
        LEFT JOIN META_SKU MR ON MR.MES = DV.MES AND MR.REVENDA = {expr_dv_rev} AND MR.CODRED = DV.CODRED
        LEFT JOIN CMV_SKU CMV ON CMV.REVENDA = {expr_dv_rev} AND CMV.CODRED = DV.CODRED
        LEFT JOIN META_FABRICA MF ON MF.REVENDA = REF.REVENDA AND MF.CODRED = REF.CODRED
        WHERE {filtro_revenda_ref}
        GROUP BY REF.REVENDA, REF.AGRUPAMENTO_VOLUME, REF.CODRED, REF.PRODUTO
    )

    SELECT * FROM DV_SKU
    ORDER BY AGRUPAMENTO_VOLUME, VOL_MES_ATUAL_UMB DESC
    """
    tabela_familia = _fonte_parquet_dv(query)

    if len(revs_efetivas) > 1:
        tabela_familia = _reagrega_familia(tabela_familia, revenda)

    return tabela_familia


def _reagrega_familia(tabela: pl.DataFrame, revenda: str) -> pl.DataFrame:

    tabela = tabela.with_columns(
        pl.when((pl.col("VENDA_HL").is_not_null()) & (pl.col("VOL_MES_ATUAL_HL") > 0))
        .then(pl.col("VENDA_HL") * pl.col("VOL_MES_ATUAL_HL"))
        .alias("_valor_hl_pond"),
        pl.when((pl.col("VENDA_HL").is_not_null()) & (pl.col("VOL_MES_ATUAL_HL") > 0))
        .then(pl.col("VOL_MES_ATUAL_HL"))
        .alias("_vol_hl_pond"),
        pl.when((pl.col("PERC_MKP").is_not_null()) & ((1 + pl.col("PERC_MKP")) > 0))
        .then(pl.col("FAT") / (1 + pl.col("PERC_MKP")))
        .alias("_fat_cmv"),
    )

    agregada = tabela.group_by(["AGRUPAMENTO_VOLUME", "CODRED", "PRODUTO"], maintain_order=True).agg(
        pl.lit(revenda).alias("REVENDA"),
        pl.col("VOL_ANO_RETRASADO_UMB").sum().alias("VOL_ANO_RETRASADO_UMB"),
        pl.col("VOL_MES_2_UMB").sum().alias("VOL_MES_2_UMB"),
        pl.col("VOL_MES_ANT_UMB").sum().alias("VOL_MES_ANT_UMB"),
        pl.col("META_FAB_HL").sum().alias("META_FAB_HL"),
        pl.col("META_FAB_UMB").sum().alias("META_FAB_UMB"),
        pl.col("META_REV_UMB").sum().alias("META_REV_UMB"),
        pl.col("VOL_ANO_ANT_UMB").sum().alias("VOL_ANO_ANT_UMB"),
        pl.col("VOL_ANO_ANT2_UMB").sum().alias("VOL_ANO_ANT2_UMB"),
        pl.col("VOL_MES_ATUAL_UMB").sum().alias("VOL_MES_ATUAL_UMB"),
        pl.col("TEND_UMB").sum().alias("TEND_UMB"),
        pl.col("VOL_ANO_RETRASADO_HL").sum().alias("VOL_ANO_RETRASADO_HL"),
        pl.col("VOL_MES_2_HL").sum().alias("VOL_MES_2_HL"),
        pl.col("VOL_MES_ANT_HL").sum().alias("VOL_MES_ANT_HL"),
        pl.col("META_REV_HL").sum().alias("META_REV_HL"),
        pl.col("VOL_ANO_ANT_HL").sum().alias("VOL_ANO_ANT_HL"),
        pl.col("VOL_ANO_ANT2_HL").sum().alias("VOL_ANO_ANT2_HL"),
        pl.col("VOL_MES_ATUAL_HL").sum().alias("VOL_MES_ATUAL_HL"),
        pl.col("TEND_HL").sum().alias("TEND_HL"),
        pl.col("FAT").sum().alias("FAT"),
        pl.col("_valor_hl_pond").sum().alias("_soma_valor_hl_pond"),
        pl.col("_vol_hl_pond").sum().alias("_soma_vol_hl_pond"),
        pl.col("_fat_cmv").sum().alias("_soma_fat_cmv"),
        pl.col("COB_MES_ANT").sum().alias("_soma_cob_mes_ant"),
        pl.col("COB_MES_ANT").null_count().alias("_null_cob_mes_ant"),
        pl.col("COB_ANO_ANT").sum().alias("_soma_cob_ano_ant"),
        pl.col("COB_ANO_ANT").null_count().alias("_null_cob_ano_ant"),
        pl.col("COB_MES_ATUAL").sum().alias("_soma_cob_mes_atual"),
        pl.col("COB_MES_ATUAL").null_count().alias("_null_cob_mes_atual"),
        pl.len().alias("_n"),
    )

    agregada = agregada.with_columns(
        pl.when(pl.col("VOL_MES_ATUAL_UMB") > 0)
        .then((pl.col("FAT") / pl.col("VOL_MES_ATUAL_UMB")).round(2))
        .otherwise(None)
        .alias("PRECO_MEDIO"),
        pl.when(pl.col("_soma_fat_cmv") > 0)
        .then((pl.col("FAT") / pl.col("_soma_fat_cmv") - 1).round(4))
        .otherwise(None)
        .alias("PERC_MKP"),
        pl.when(pl.col("_soma_vol_hl_pond") > 0)
        .then((pl.col("_soma_valor_hl_pond") / pl.col("_soma_vol_hl_pond")).round(2))
        .otherwise(None)
        .alias("VENDA_HL"),
        pl.when(pl.col("_null_cob_mes_ant") == pl.col("_n"))
        .then(None)
        .otherwise(pl.col("_soma_cob_mes_ant"))
        .alias("COB_MES_ANT"),
        pl.when(pl.col("_null_cob_ano_ant") == pl.col("_n"))
        .then(None)
        .otherwise(pl.col("_soma_cob_ano_ant"))
        .alias("COB_ANO_ANT"),
        pl.when(pl.col("_null_cob_mes_atual") == pl.col("_n"))
        .then(None)
        .otherwise(pl.col("_soma_cob_mes_atual"))
        .alias("COB_MES_ATUAL"),
    ).with_columns(
        pl.when(pl.col("META_REV_UMB") > 0)
        .then(pl.col("TEND_UMB") / pl.col("META_REV_UMB"))
        .otherwise(None)
        .alias("PERC_TEND_UMB"),
        pl.when(pl.col("META_REV_HL") > 0)
        .then(pl.col("TEND_HL") / pl.col("META_REV_HL"))
        .otherwise(None)
        .alias("PERC_TEND_HL"),
    )

    return agregada.select(
        "REVENDA",
        "AGRUPAMENTO_VOLUME",
        "CODRED",
        "PRODUTO",
        "VOL_ANO_RETRASADO_UMB",
        "VOL_ANO_ANT_UMB",
        "VOL_MES_2_UMB",
        "VOL_MES_ANT_UMB",
        "META_FAB_UMB",
        "META_REV_UMB",
        "VOL_ANO_ANT2_UMB",
        "VOL_MES_ATUAL_UMB",
        "TEND_UMB",
        "PERC_TEND_UMB",
        "VOL_ANO_RETRASADO_HL",
        "VOL_ANO_ANT_HL",
        "VOL_MES_2_HL",
        "VOL_MES_ANT_HL",
        "META_FAB_HL",
        "META_REV_HL",
        "VOL_ANO_ANT2_HL",
        "VOL_MES_ATUAL_HL",
        "TEND_HL",
        "PERC_TEND_HL",
        "PRECO_MEDIO",
        "PERC_MKP",
        "VENDA_HL",
        "COB_MES_ANT",
        "COB_ANO_ANT",
        "COB_MES_ATUAL",
        "FAT",
    )


def outros_volumes_dv(
    revenda: str,
    mes: str,
    ven: list[str] | None = None,
    ga: list[str] | None = None,
    rev: list[str] | None = None,
    base: str | None = None,
) -> pl.DataFrame:
    return familia_dv(revenda=revenda, mes=mes, ven=ven, ga=ga, rev=rev, agrupamento_nulo=True, base=base)


def meses_disponiveis_dv(revenda: str) -> dict[str, str]:

    revs_efetivas = expandir_revendas_dv(revenda, revenda)
    filtro_revenda = f"REVENDA IN ({_sql_lista(revs_efetivas)})"

    resultado = _fonte_parquet_dv(f"SELECT DISTINCT MES FROM TB_DIARIO_VENDA WHERE {filtro_revenda} ORDER BY MES DESC")

    meses = {m for m in resultado["MES"].to_list() if m is not None} if resultado.height else set()
    meses.add(date.today().strftime("%Y%m"))
    meses_ordenados = sorted(meses, reverse=True)

    nomes_meses = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    rotulos = {}
    for m in meses_ordenados:
        ano, mm = int(m[:4]), int(m[4:6])
        rotulos[f"{nomes_meses[mm - 1]}/{ano}"] = m
    return rotulos


def filtros_ga_ven_dv(revenda: str, base: str | None = None) -> dict:

    revs_efetivas = expandir_revendas_dv(revenda, revenda)

    resultado = _fonte_parquet_dv(f"""
        SELECT DISTINCT GA, VEN FROM TB_DIARIO_VENDA
        WHERE REVENDA IN ({_sql_lista(revs_efetivas)}) AND GA IS NOT NULL AND VEN IS NOT NULL
        {_sql_in("BASE_FOCO", [base] if base else None)}
        ORDER BY GA, VEN
    """)

    if resultado.height == 0:
        return {"ga": [], "ven": [], "pairs": resultado}

    return {
        "ga": sorted(resultado["GA"].unique().to_list()),
        "ven": sorted(resultado["VEN"].unique().to_list()),
        "pairs": resultado,
    }


def bases_foco_dv(revenda: str) -> list[str]:

    revs_efetivas = expandir_revendas_dv(REVENDA_NOME_BD.get(revenda, revenda), revenda)

    try:
        resultado = _fonte_parquet_dv(f"""
            SELECT DISTINCT BASE_FOCO FROM TB_DIARIO_VENDA
            WHERE REVENDA IN ({_sql_lista(revs_efetivas)}) AND BASE_FOCO IS NOT NULL
            ORDER BY BASE_FOCO
        """)
    except Exception as exc:
        logger.warning(f"Diario de Venda: bases de foco nao lidas ({exc}) -- filtro 'Base' fica escondido")
        return []
    if resultado.height == 0:
        return []
    return resultado.get_column("BASE_FOCO").to_list()


def info_dias_uteis_dv(revenda: str, mes: str) -> dict[str, str]:
    revs_efetivas = expandir_revendas_dv(revenda, revenda)
    filtro_revenda = f"REVENDA IN ({_sql_lista(revs_efetivas)})"

    resultado = _fonte_parquet_dv(
        f"SELECT DIAS_UTEIS, DIAS_UTEIS_ATUAL FROM TB_DIARIO_VENDA WHERE {filtro_revenda} AND MES = '{mes}' LIMIT 1"
    )
    if resultado.height == 0:
        return {"DIAS_UTEIS": "-", "DIAS_UTEIS_ATUAL": "-"}
    linha = resultado.row(0, named=True)
    return {"DIAS_UTEIS": linha["DIAS_UTEIS"], "DIAS_UTEIS_ATUAL": linha["DIAS_UTEIS_ATUAL"]}


def meta_ano_dv(revenda: str) -> pl.DataFrame:
    ano_at_int = date.today().year
    ano_1, ano_2, ano_at = str(ano_at_int - 1), str(ano_at_int - 2), str(ano_at_int)

    revs_efetivas = expandir_revendas_dv(revenda, revenda)
    filtro_revenda = f"REVENDA IN ({_sql_lista(revs_efetivas)})"

    volumes_mensais = _fonte_parquet_dv(f"""
        SELECT LEFT(MES,4) AS ANO, RIGHT(MES,2) AS MES_NUM,
               ROUND(SUM(QTD_TOTAL_HL),0) AS QTD, ROUND(SUM(TEND_HL),0) AS TEND
        FROM TB_DIARIO_VENDA
        WHERE {filtro_revenda} AND LEFT(MES,4) IN ('{ano_2}','{ano_1}','{ano_at}')
        GROUP BY LEFT(MES,4), RIGHT(MES,2)
    """)
    if volumes_mensais.height == 0:
        return pl.DataFrame()

    meses_seq = [f"{m:02d}" for m in range(1, 13)]
    nomes_meses = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

    def valores_por_ano(ano: str, coluna: str) -> list[float]:
        linhas = volumes_mensais.filter(pl.col("ANO") == ano)
        mapa = dict(zip(linhas["MES_NUM"].to_list(), linhas[coluna].to_list()))
        return [mapa.get(m, 0.0) or 0.0 for m in meses_seq]

    vol_ano_2 = valores_por_ano(ano_2, "QTD")
    vol_ano_1 = valores_por_ano(ano_1, "QTD")
    tend_ano_at = valores_por_ano(ano_at, "TEND")

    meta_min = [max(a, b) for a, b in zip(vol_ano_2, vol_ano_1)]
    meta_at = [m + 2000 for m in meta_min]
    dif = [t - m for t, m in zip(tend_ano_at, meta_at)]

    def montar_linha(rotulo: str, valores: list[float]) -> dict:
        linha = {"HL_TOTAL": rotulo, **dict(zip(nomes_meses, valores)), "Total": sum(valores)}
        return linha

    linhas = [
        montar_linha(ano_2, vol_ano_2),
        montar_linha(ano_1, vol_ano_1),
        montar_linha("Meta Minima Equipe", meta_min),
        montar_linha("Incremento", [2000.0] * 12),
        montar_linha(f"Meta {ano_at}", meta_at),
        montar_linha(ano_at, tend_ano_at),
        montar_linha("Diferenca", dif),
    ]
    return pl.DataFrame(linhas)


_CATEGORIAS_ABP = [
    "CORAL RETORNAVEL",
    "CORAL ULTRA",
    "CERV RGB + CHOPP",
    "TUPÃ TOTAL",
    "MARÉ RETORNAVEL",
    "MARÉ TOTAL",
    "COBERTURA TOTAL",
]

_MESES_ABP = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _tabela_abp_vazia() -> pl.DataFrame:

    return pl.DataFrame(
        schema={
            "COD_SAP": pl.Utf8,
            "CATEGORIA": pl.Utf8,
            "HL_TOTAL": pl.Utf8,
            **{mes: pl.Float64 for mes in _MESES_ABP},
            "Total": pl.Float64,
            "NOVO_COD_SAP": pl.Boolean,
        }
    )


def meta_abp_dv(revenda: str, tipo: str = "Cobertura") -> pl.DataFrame:

    ano_at = str(date.today().year)
    revs_efetivas = expandir_revendas_dv(revenda, revenda)
    revs_sql = _sql_lista(revs_efetivas)
    revs_sql_up = _sql_lista([r.upper() for r in revs_efetivas])
    categorias_sql = _sql_lista(_CATEGORIAS_ABP)

    if tipo == "Volume":
        query_meta = f"""
        SELECT
            cod_sap                 AS COD_SAP,
            UPPER(TRIM(REVENDA))    AS REVENDA,
            UPPER(TRIM(CATEGORIA))  AS CATEGORIA,
            RIGHT(CHAVE_MES_ANO, 2) AS MES_NUM,
            SUM(VOLUME)             AS META_ABP
        FROM tb_metas_abp_vol
        WHERE LEFT(CHAVE_MES_ANO, 4) = '{ano_at}'
          AND REVENDA IN ({revs_sql})
          AND UPPER(TIPO_META) = 'MENSAL'
        GROUP BY cod_sap, UPPER(TRIM(REVENDA)), UPPER(TRIM(CATEGORIA)), RIGHT(CHAVE_MES_ANO, 2)
        """
        query_real = f"""
        SELECT
            CASE
              WHEN UPPER(TRIM(MARCA)) = 'IPÊ' THEN 'IPÊ - IPÊ'
              ELSE UPPER(TRIM(MARCA))
            END                        AS CATEGORIA,
            RIGHT(MES, 2)              AS MES_NUM,
            UPPER(TRIM(REVENDA))       AS REVENDA,
            CEILING(SUM(QTD_TOTAL_HL)) AS REAL_ABP
        FROM TB_DIARIO_VENDA
        WHERE LEFT(MES, 4) = '{ano_at}'
          AND UPPER(REVENDA) IN ({revs_sql_up})
          AND UPPER(TRIM(MARCA)) IN (
                'AGUA FAROL', 'CORAL', 'IPÊ', 'LUA AZUL',
                'JANGADA', 'TUPÃ', 'BRISA', 'MARÉ',
                'MANDACARU', 'SERENA', 'FAROL', 'CAJUÍNA'
              )
        GROUP BY 1, 2, 3
        """
    else:
        query_meta = f"""
        SELECT
            cod_sap                 AS COD_SAP,
            UPPER(TRIM(REVENDA))    AS REVENDA,
            UPPER(TRIM(CATEGORIA))  AS CATEGORIA,
            RIGHT(CHAVE_MES_ANO, 2) AS MES_NUM,
            SUM(COBERTURA)          AS META_ABP
        FROM tb_metas_abp_cob
        WHERE LEFT(CHAVE_MES_ANO, 4) = '{ano_at}'
          AND REVENDA IN ({revs_sql})
          AND CATEGORIA IN ({categorias_sql})
          AND TIPO_META IN ('MENSAL')
        GROUP BY cod_sap, UPPER(TRIM(REVENDA)), UPPER(TRIM(CATEGORIA)), RIGHT(CHAVE_MES_ANO, 2)
        """

        query_real = f"""
        SELECT
            CASE
              WHEN TIPO = 'MARCA' AND UPPER(TRIM(CATEGORIA)) = 'MARÉ' THEN 'MARÉ TOTAL'
              WHEN TIPO = 'MARCA' AND UPPER(TRIM(CATEGORIA)) = 'TUPÃ'      THEN 'TUPÃ TOTAL'
              WHEN TIPO = 'VOLUME_TOTAL'                                 THEN 'COBERTURA TOTAL'
              ELSE UPPER(TRIM(CATEGORIA))
            END                  AS CATEGORIA,
            RIGHT(MES, 2)        AS MES_NUM,
            UPPER(TRIM(REVENDA)) AS REVENDA,
            SUM(COB_CAT)         AS REAL_ABP
        FROM {tabela_cobertura("tb_cob_categ")}
        WHERE LEFT(MES, 4) = '{ano_at}'
          AND UPPER(REVENDA) IN ({revs_sql_up})
          AND (
                (TIPO = 'MARCA'        AND UPPER(TRIM(CATEGORIA)) IN ('CORAL ULTRA', 'TUPÃ', 'MARÉ'))
             OR  TIPO = 'CATEG_ABP'
             OR (TIPO = 'VOLUME_TOTAL' AND UPPER(TRIM(CATEGORIA)) = 'VOLUME TOTAL')
              )
        GROUP BY 1, 2, 3
        """

    meses_seq = [f"{m:02d}" for m in range(1, 13)]
    nomes_meses = _MESES_ABP
    col_real = f"REAL_{ano_at}"

    try:
        meta = _fonte_parquet_dv(query_meta)

        realizado = _fonte_parquet_dv(query_real)
    except Exception:
        return _tabela_abp_vazia()

    if meta.height == 0:
        return _tabela_abp_vazia()

    if realizado.height == 0 or "REAL_ABP" not in realizado.columns:
        realizado = pl.DataFrame(
            schema={
                "CATEGORIA": pl.Utf8,
                "MES_NUM": pl.Utf8,
                "REVENDA": pl.Utf8,
                "REAL_ABP": pl.Float64,
            }
        )

    chaves = ["CATEGORIA", "MES_NUM", "REVENDA"]
    resultado = (
        meta.with_columns([pl.col(chave).cast(pl.Utf8) for chave in chaves])
        .join(
            realizado.with_columns([pl.col(chave).cast(pl.Utf8) for chave in chaves]),
            on=chaves,
            how="left",
        )
        .group_by(["COD_SAP", "CATEGORIA", "MES_NUM"])
        .agg(
            pl.col("REAL_ABP").sum().alias(col_real),
            pl.col("META_ABP").sum().alias("META_ABP"),
        )
        .with_columns(
            pl.col(col_real).fill_null(0),
            pl.col("META_ABP").fill_null(0),
        )
        .with_columns((pl.col(col_real) - pl.col("META_ABP")).alias("DIFERENCA"))
    )

    if tipo == "Cobertura":
        ordem = {categoria: i for i, categoria in enumerate(_CATEGORIAS_ABP)}
        resultado = (
            resultado.with_columns(
                pl.col("CATEGORIA").replace_strict(ordem, default=len(ordem), return_dtype=pl.Int32).alias("_ordem")
            )
            .sort(["_ordem", "COD_SAP", "MES_NUM"])
            .drop("_ordem")
        )
    else:
        resultado = resultado.sort(["CATEGORIA", "COD_SAP", "MES_NUM"])

    rotulo_real = f"{'Cob' if tipo == 'Cobertura' else 'Vol'} {ano_at}"

    categorias = resultado.select(["COD_SAP", "CATEGORIA"]).unique(maintain_order=True)

    linhas = []
    for cod, cat in categorias.iter_rows():
        sub = resultado.filter((pl.col("COD_SAP") == cod) & (pl.col("CATEGORIA") == cat))
        mapa_mes = {row["MES_NUM"]: row for row in sub.iter_rows(named=True)}

        def preencher(coluna: str) -> list[float]:
            return [float(mapa_mes[m][coluna]) if m in mapa_mes else 0.0 for m in meses_seq]

        def montar_linha(rotulo: str, valores: list[float]) -> dict:

            total = sum(valores) / len(valores) if tipo == "Cobertura" else sum(valores)
            return {
                "COD_SAP": cod,
                "CATEGORIA": cat,
                "HL_TOTAL": rotulo,
                **dict(zip(nomes_meses, valores)),
                "Total": total,
            }

        linhas.append(montar_linha(rotulo_real, preencher(col_real)))
        linhas.append(montar_linha("Meta ABP", preencher("META_ABP")))
        linhas.append(montar_linha("Diferença", preencher("DIFERENCA")))

    tabela = pl.DataFrame(linhas)

    tabela = tabela.with_columns(
        (pl.col("COD_SAP") != pl.col("COD_SAP").shift(1).over("CATEGORIA")).fill_null(True).alias("NOVO_COD_SAP")
    )
    return tabela
