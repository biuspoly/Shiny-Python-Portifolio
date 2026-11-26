from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

import duckdb
import polars as pl
from dateutil.relativedelta import relativedelta
from loguru import logger

from core.compat import polars_de_duckdb
from core.config import REVENDA_NOME_BD

PASTA_PARQUET = Path(__file__).parents[3] / "data" / "bd_comercial"

REVENDAS_ESCOLHE_DISTANCIA: set[str] = set()

# Habitantes por ponto de venda potencial. O original usa 190; a base fictícia
# tem bem menos clientes que uma revenda real, então o fator acompanha.
HAB_POR_PDV = 1000

COR_BORDA_SEDE = "#3B2110"
COR_BORDA_75 = "#006400"
COR_BORDA_150 = "#be9c00"
COR_BORDA_150_M = "#FF0000"
COR_BORDA_200 = "#ADD8E6"
COR_BORDA_NA = "#808080"
COR_BORDA_PADRAO = "#000000"

ORDEM_BORDA = (
    COR_BORDA_PADRAO,
    COR_BORDA_NA,
    COR_BORDA_200,
    COR_BORDA_150_M,
    COR_BORDA_150,
    COR_BORDA_75,
    COR_BORDA_SEDE,
)

COR_AREA_100 = "#3B2110"
COR_AREA_75 = "#006400"
COR_AREA_55 = "#be9c00"
COR_AREA_0_M = "#FF0000"

MESES_PT = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def _revenda_bd(revenda: str) -> str:
    return REVENDA_NOME_BD.get(revenda, revenda)


def escolhe_base_distancia(revenda: str) -> bool:
    return _revenda_bd(revenda) in REVENDAS_ESCOLHE_DISTANCIA


def _escapa(valor: object) -> str:
    return str(valor).replace("'", "''")


def _sql_in(coluna: str, valores: tuple[str, ...] | list[str] | None) -> str:
    if not valores:
        return ""
    lista = ", ".join(f"'{_escapa(valor)}'" for valor in valores)
    return f"AND {coluna} IN ({lista})"


def _conexao() -> duckdb.DuckDBPyConnection:
    arquivos = [a for a in sorted(PASTA_PARQUET.glob("*.parquet")) if not a.name.startswith(("tmp_", "~$", "."))]
    if len(arquivos) < 5:
        raise FileNotFoundError(
            f"Cache do Mapa Comercial incompleto em {PASTA_PARQUET}. São esperados ao menos cinco arquivos Parquet."
        )
    con = duckdb.connect(":memory:")
    for arquivo in arquivos:
        try:
            con.execute(f"CREATE VIEW {arquivo.stem} AS SELECT * FROM read_parquet('{arquivo.as_posix()}')")
        except duckdb.Error as exc:
            logger.warning(f"Mapa Comercial: {arquivo.name} ignorado nesta consulta -- {exc}")
    return con


def _consulta(con: duckdb.DuckDBPyConnection, sql: str) -> pl.DataFrame:
    return polars_de_duckdb(con.sql(sql))


@lru_cache(maxsize=32)
def meses_disponiveis(revenda: str) -> dict[str, str]:
    revenda = _revenda_bd(revenda)
    con = _conexao()
    try:
        meses = (
            _consulta(
                con,
                f"""
            SELECT DISTINCT MES
            FROM tb_cob_cid
            WHERE REVENDA = '{_escapa(revenda)}'
            ORDER BY MES DESC
            """,
            )
            .get_column("MES")
            .cast(pl.Utf8)
            .to_list()
        )
    finally:
        con.close()

    rotulos = {}
    abreviacoes = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")
    for mes in meses:
        rotulos[mes] = f"{abreviacoes[int(mes[4:6]) - 1]}/{mes[:4]}"
    return rotulos


@lru_cache(maxsize=32)
def opcoes_filtro_produto(revenda: str) -> dict[str, list[str]]:
    coluna_marca = "MARCA"
    revenda_bd = _revenda_bd(revenda)
    con = _conexao()

    filtro_ga = ""

    def opcoes(coluna: str, tabela: str = "tb_mapa_pot") -> list[str]:
        dados = _consulta(
            con,
            f"""
            SELECT DISTINCT {coluna}
            FROM {tabela}
            WHERE REVENDA = '{_escapa(revenda_bd)}' AND {coluna} IS NOT NULL
              {filtro_ga}
            ORDER BY {coluna}
            """,
        )
        return dados.get_column(coluna).cast(pl.Utf8).to_list()

    try:
        canais = opcoes("CANAL_PROD")
        canais = [valor for valor in canais if valor.strip().upper() not in {"CHOPP", "OUTRO"}]
        return {
            "marca": opcoes(coluna_marca),
            "canal": canais,
            "categoria": opcoes("SEGMENTO"),
            "embalagem": opcoes("VOLUME"),
            "vendedor": opcoes("VEN"),
            "porte": opcoes("PORTE", "tb_cli_ativos"),
        }
    finally:
        con.close()


@lru_cache(maxsize=32)
def combinacoes_filtro_produto(revenda: str) -> pl.DataFrame:
    coluna_marca = "MARCA"
    revenda_bd = _revenda_bd(revenda)
    con = _conexao()
    try:
        return _consulta(
            con,
            f"""
            SELECT DISTINCT
                {coluna_marca}::VARCHAR AS MARCA,
                CANAL_PROD::VARCHAR AS CANAL_PROD,
                SEGMENTO::VARCHAR AS SEGMENTO,
                VOLUME::VARCHAR AS VOLUME,
                VEN::VARCHAR AS VEN
            FROM tb_mapa_pot
            WHERE REVENDA = '{_escapa(revenda_bd)}'
            """,
        )
    finally:
        con.close()


_COLUNAS_PRODUTO_COBERTURA = ("MARCA", "CANAL_PROD", "VOLUME", "SEGMENTO")


def _cobertura_tem_produto(con: duckdb.DuckDBPyConnection) -> bool:
    try:
        colunas = {c[0] for c in con.execute("SELECT * FROM tb_cob_cid LIMIT 0").description}
    except duckdb.Error as exc:
        logger.warning(f"Mapa Comercial: nao foi possivel ler o esquema de tb_cob_cid -- {exc}")
        return False
    faltando = [c for c in _COLUNAS_PRODUTO_COBERTURA if c not in colunas]
    if faltando:
        logger.warning(
            "Mapa Comercial: tb_cob_cid sem "
            f"{', '.join(faltando)} -- filtro de produto nao vale para a cobertura "
            "ate' scripts/atualiza_mapa_comercial.py rodar."
        )
        return False
    return True


def _meses_historico(mes_atual: str) -> list[str]:
    inicio = date(int(mes_atual[:4]), int(mes_atual[4:6]), 1)
    return [(inicio - relativedelta(months=offset)).strftime("%Y%m") for offset in (3, 2, 1, 0)]


def mapa_potencial(
    revenda: str,
    mes_atual: str,
    marca: tuple[str, ...] = (),
    canal: tuple[str, ...] = (),
    categoria: tuple[str, ...] = (),
    embalagem: tuple[str, ...] = (),
    vendedor: tuple[str, ...] = (),
    porte: tuple[str, ...] = (),
    base_distancia: str = "sede",
) -> dict[str, object]:
    sem_distancia = False
    if not escolhe_base_distancia(revenda):
        base_distancia = "fabrica"
    coluna_distancia = "CR.DIST_FAB" if base_distancia == "fabrica" else "CR.DIST_SEDE"
    rotulo_distancia = "Distância"
    rotulo_dist_zero = "Sede"
    coluna_marca = "MP.MARCA"
    revenda_bd = _revenda_bd(revenda)
    fator = HAB_POR_PDV

    filtro_produto = " ".join(
        (
            _sql_in(coluna_marca, marca),
            _sql_in("MP.CANAL_PROD", canal),
            _sql_in("MP.SEGMENTO", categoria),
            _sql_in("MP.VOLUME", embalagem),
            _sql_in("MP.VEN", vendedor),
        )
    )

    def _filtro_produto_cobertura(alias: str) -> str:
        return " ".join(
            (
                _sql_in(f"{alias}.MARCA", marca),
                _sql_in(f"{alias}.CANAL_PROD", canal),
                _sql_in(f"{alias}.SEGMENTO", categoria),
                _sql_in(f"{alias}.VOLUME", embalagem),
            )
        )

    filtro_porte_c = _sql_in("C.PORTE", porte)
    filtro_porte_cc = _sql_in("CC.PORTE", porte)
    ga_mesa: tuple[str, ...] = ()
    filtro_ga_mp = _sql_in("MP.GA", ga_mesa)
    filtro_ga_c = _sql_in("C.GA", ga_mesa)
    filtro_ga_cc = _sql_in("CC.GA", ga_mesa)
    filtro_vendedor_c = _sql_in("C.VEN", vendedor)
    filtro_vendedor_cc = _sql_in("CC.VEN", vendedor)
    meses_hist = _meses_historico(mes_atual)
    meses_sql = ", ".join(f"'{mes}'" for mes in meses_hist)

    cor_borda_sql = (
        f"'{COR_BORDA_PADRAO}'"
        if sem_distancia
        else f"""
        CASE
            WHEN {coluna_distancia} = 0 THEN '{COR_BORDA_SEDE}'
            WHEN {coluna_distancia} > 0 AND {coluna_distancia} <= 75 THEN '{COR_BORDA_75}'
            WHEN {coluna_distancia} > 75 AND {coluna_distancia} <= 150 THEN '{COR_BORDA_150}'
            WHEN {coluna_distancia} > 150 AND {coluna_distancia} < 200 THEN '{COR_BORDA_150_M}'
            WHEN {coluna_distancia} >= 200 THEN '{COR_BORDA_200}'
            ELSE '{COR_BORDA_NA}'
        END
    """
    )

    con = _conexao()
    try:
        if _cobertura_tem_produto(con):
            filtro_produto_c = _filtro_produto_cobertura("C")
            filtro_produto_cc = _filtro_produto_cobertura("CC")
        else:
            filtro_produto_c = filtro_produto_cc = ""

        venda = _consulta(
            con,
            f"""
            SELECT MP.*
            FROM tb_mapa_pot MP
            WHERE MP.REVENDA = '{_escapa(revenda_bd)}'
              AND MP.MES = '{_escapa(mes_atual)}'
              {filtro_produto} {filtro_ga_mp}
            """,
        )

        cidades = _consulta(
            con,
            f"""
            SELECT
                CR.REVENDA, CR.CIDADE, CR.COD_IBGE, CR.UF,
                MIN(CR.SUBREVENDA) AS SUBREVENDA,
                COUNT(DISTINCT CC.CLI) AS QTD_PDV,
                ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) AS COB_POT,
                CR.POPULACAO,
                CEIL(CR.POPULACAO / {fator}.0) AS POTENCIAL,
                CASE
                    WHEN ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) >= 55
                     AND ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) < 75
                        THEN CEIL(CEIL(CR.POPULACAO / {fator}.0) * 0.75) - COUNT(DISTINCT CC.CLI)
                    WHEN ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) >= 0
                     AND ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) < 55
                        THEN CEIL(CEIL(CR.POPULACAO / {fator}.0) * 0.55) - COUNT(DISTINCT CC.CLI)
                    ELSE 0
                END AS POT_PROX_NVL,
                {coluna_distancia} AS DISTANCIA,
                {cor_borda_sql} AS COR_BORDA,
                CASE
                    WHEN ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) >= 100 THEN '{COR_AREA_100}'
                    WHEN ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) >= 75 THEN '{COR_AREA_75}'
                    WHEN ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) >= 55 THEN '{COR_AREA_55}'
                    ELSE '{COR_AREA_0_M}'
                END AS COR_AREA,
                CASE
                    WHEN ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) >= 55
                     AND ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) < 75 THEN '{COR_AREA_75}'
                    WHEN ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) >= 0
                     AND ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) < 55 THEN '{COR_AREA_55}'
                    ELSE '0'
                END AS COR_POT_PROX_NVL,
                CR.GEOMETRY
            FROM tb_cidades_rev CR
            LEFT JOIN tb_cob_cid CC
              ON CC.REVENDA = CR.REVENDA AND CC.COD_IBGE = CR.COD_IBGE
              AND CC.MES = '{_escapa(mes_atual)}'
              {filtro_porte_cc} {filtro_produto_cc} {filtro_ga_cc}
            WHERE CR.REVENDA = '{_escapa(revenda_bd)}'
            GROUP BY CR.REVENDA, CR.CIDADE, CR.COD_IBGE, CR.UF,
                     CR.POPULACAO, {coluna_distancia}, CR.GEOMETRY
            """,
        )
        if cidades.height == 0:
            raise ValueError(f"Sem dados de cobertura para {revenda_bd} no mês {mes_atual}.")

        clientes_ativos_df = _consulta(
            con,
            f"""
            SELECT C.* FROM tb_cli_ativos C
            WHERE C.REVENDA = '{_escapa(revenda_bd)}'
              AND C.MES = '{_escapa(mes_atual)}'
              {filtro_porte_c} {filtro_vendedor_c} {filtro_ga_c}
            """,
        )
        clientes_inativos_df = _consulta(
            con,
            f"""
            SELECT C.* FROM tb_cli_inativos C
            WHERE C.REVENDA = '{_escapa(revenda_bd)}'
              AND C.MES = '{_escapa(mes_atual)}'
              {filtro_porte_c} {filtro_vendedor_c} {filtro_ga_c}
            """,
        )
        cobertura = _consulta(
            con,
            f"""
            SELECT C.MES, COUNT(DISTINCT C.CLI) AS QTD_PDV
            FROM tb_cob_cid C
            WHERE C.REVENDA = '{_escapa(revenda_bd)}' {filtro_porte_c} {filtro_produto_c} {filtro_ga_c}
            GROUP BY C.MES ORDER BY C.MES
            """,
        )
        cob_hist = _consulta(
            con,
            f"""
            SELECT
                CC.COD_IBGE, CC.MES, COUNT(DISTINCT CC.CLI) AS QTD_PDV,
                CASE
                    WHEN ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) >= 55
                     AND ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) < 75
                        THEN CEIL(CEIL(CR.POPULACAO / {fator}.0) * 0.75) - COUNT(DISTINCT CC.CLI)
                    WHEN ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) >= 0
                     AND ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) < 55
                        THEN CEIL(CEIL(CR.POPULACAO / {fator}.0) * 0.55) - COUNT(DISTINCT CC.CLI)
                    ELSE 0
                END AS POT_PROX_NVL,
                CASE
                    WHEN ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) >= 55
                     AND ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) < 75 THEN '{COR_AREA_75}'
                    WHEN ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) >= 0
                     AND ROUND(COUNT(DISTINCT CC.CLI) / NULLIF(CEIL(CR.POPULACAO / {fator}.0), 0) * 100, 2) < 55 THEN '{COR_AREA_55}'
                    ELSE '0'
                END AS COR_POT_PROX_NVL
            FROM tb_cob_cid CC
            JOIN tb_cidades_rev CR
              ON CR.REVENDA = CC.REVENDA AND CR.COD_IBGE = CC.COD_IBGE
            WHERE CC.REVENDA = '{_escapa(revenda_bd)}'
              AND CC.MES IN ({meses_sql}) {filtro_porte_cc} {filtro_produto_cc} {filtro_ga_cc}
            GROUP BY CC.COD_IBGE, CC.MES, CR.POPULACAO
            """,
        )
        venda_hist = _consulta(
            con,
            f"""
            SELECT MP.COD_IBGE, MP.MES,
                   SUM(MP.QTD_TOTAL_HL) AS VOLUME_HL,
                   SUM(MP.QTD_TOTAL) AS QTD_UMB
            FROM tb_mapa_pot MP
            WHERE MP.REVENDA = '{_escapa(revenda_bd)}'
              AND MP.MES IN ({meses_sql}) {filtro_produto} {filtro_ga_mp}
            GROUP BY MP.COD_IBGE, MP.MES
            """,
        )
        cli_hist = _consulta(
            con,
            f"""
            SELECT CC.COD_IBGE, CC.MES, COUNT(DISTINCT CC.CLI_ATIVO) AS CLI_ATIVO
            FROM tb_cli_ativos CC
            WHERE CC.REVENDA = '{_escapa(revenda_bd)}'
              AND CC.MES IN ({meses_sql}) {filtro_porte_cc} {filtro_vendedor_cc} {filtro_ga_cc}
            GROUP BY CC.COD_IBGE, CC.MES
            """,
        )
    finally:
        con.close()

    cli_cidade = clientes_ativos_df.group_by("COD_IBGE").agg(pl.col("CLI_ATIVO").n_unique().alias("CLI_ATIVO"))
    cidades = cidades.join(cli_cidade, on="COD_IBGE", how="left")
    if venda.height:
        venda_cidade = venda.group_by("COD_IBGE").agg(
            pl.col("FATURAMENTO").sum().alias("FATURAMENTO"),
            pl.col("QTD_TOTAL_HL").sum().ceil().alias("VOLUME_HL"),
            pl.col("QTD_TOTAL").sum().ceil().alias("QTD_UMB"),
        )
        cidades = cidades.join(venda_cidade, on="COD_IBGE", how="left")
    else:
        cidades = cidades.with_columns(
            pl.lit(0.0).alias("FATURAMENTO"),
            pl.lit(0.0).alias("VOLUME_HL"),
            pl.lit(0.0).alias("QTD_UMB"),
        )
    cidades = cidades.with_columns(
        pl.col("FATURAMENTO").fill_null(0),
        pl.col("VOLUME_HL").fill_null(0),
        pl.col("QTD_UMB").fill_null(0),
        pl.col("CLI_ATIVO").fill_null(0),
    ).with_columns((pl.col("FATURAMENTO") / pl.col("POPULACAO")).fill_nan(0).fill_null(0).round(2).alias("FAT_HAB"))

    populacao = int(cidades.get_column("POPULACAO").sum() or 0)
    potencial = int(-(-populacao // fator)) if fator else 0
    clientes = int(clientes_ativos_df.get_column("CLI_ATIVO").n_unique()) if clientes_ativos_df.height else 0
    volume_hl = int(venda.get_column("QTD_TOTAL_HL").sum().__ceil__()) if venda.height else 0
    qtd_umb = int(venda.get_column("QTD_TOTAL").sum().__ceil__()) if venda.height else 0
    faturamento = float(venda.get_column("FATURAMENTO").sum() or 0) if venda.height else 0.0
    fat_hab = round(faturamento / populacao, 2) if populacao else 0.0
    linha_mes = cobertura.filter(pl.col("MES").cast(pl.Utf8) == mes_atual)
    cobertura_atual = int(linha_mes.get_column("QTD_PDV").sum() or 0) if linha_mes.height else 0
    cob_pot = round(cobertura_atual / potencial, 4) * 100 if potencial else 0.0
    perc_cli_ativo = round(cobertura_atual / clientes, 4) * 100 if clientes else 0.0
    mun_amarelo = cidades.filter(pl.col("COR_POT_PROX_NVL") == COR_AREA_55).height
    cob_amarelo = int(cidades.filter(pl.col("COR_POT_PROX_NVL") == COR_AREA_55).get_column("QTD_PDV").sum() or 0)

    historico = cob_hist.join(cli_hist, on=["COD_IBGE", "MES"], how="full", coalesce=True)
    historico = historico.join(venda_hist, on=["COD_IBGE", "MES"], how="full", coalesce=True)
    historico = historico.with_columns(
        pl.col("QTD_PDV").fill_null(0),
        pl.col("CLI_ATIVO").fill_null(0),
        pl.col("VOLUME_HL").fill_null(0),
        pl.col("QTD_UMB").fill_null(0),
        pl.col("POT_PROX_NVL").fill_null(0),
        pl.col("COR_POT_PROX_NVL").fill_null("#555"),
    ).with_columns(
        pl.when(pl.col("CLI_ATIVO") > 0)
        .then((pl.col("QTD_PDV") / pl.col("CLI_ATIVO") * 100).round(2))
        .otherwise(0)
        .alias("PERC_COB_CLI")
    )

    features = []
    for linha in cidades.iter_rows(named=True):
        try:
            geometria = json.loads(linha["GEOMETRY"])
        except (TypeError, json.JSONDecodeError):
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {"name": str(linha["CIDADE"]).strip(), "COD_IBGE": linha["COD_IBGE"]},
                "geometry": geometria,
            }
        )

    qtd_grafico = cobertura.get_column("QTD_PDV").cast(pl.Float64).to_list()
    meses_grafico = cobertura.get_column("MES").cast(pl.Utf8).to_list()
    percentuais_grafico = [round(valor / potencial * 100, 2) if potencial else 0 for valor in qtd_grafico]
    labels_grafico = [f"{MESES_PT[int(mes[4:6]) - 1]}/{mes[:4]}" for mes in meses_grafico]
    if labels_grafico:
        labels_grafico[-1] = "Mês Atual"

    return {
        "cidades": cidades,
        "clientes_ativos": clientes_ativos_df,
        "clientes_inativos": clientes_inativos_df,
        "historico": historico,
        "geojson": {"type": "FeatureCollection", "features": features},
        "sem_distancia": sem_distancia,
        "rotulo_distancia": rotulo_distancia,
        "rotulo_dist_zero": rotulo_dist_zero,
        "cards": {
            "Clientes": clientes,
            "Volume HL": volume_hl,
            "Cobertura": (cobertura_atual, perc_cli_ativo),
            "R$ / Hab": fat_hab,
            "Cob Amarela": cob_amarelo,
            "Fator": fator,
            "Potencial": potencial,
            "Volume UMB": qtd_umb,
            "Cob. Potencial": cob_pot,
            "População": populacao,
            "Mun Amarelos": mun_amarelo,
        },
        "grafico": {"labels": labels_grafico, "qtd": qtd_grafico, "percentuais": percentuais_grafico},
    }


def saiba_mais(dados: dict[str, object]) -> pl.DataFrame:
    cidades: pl.DataFrame = dados["cidades"]
    tabela = (
        cidades.select(
            "COD_IBGE",
            "COR_POT_PROX_NVL",
            "COR_AREA",
            "CIDADE",
            "DISTANCIA",
            "POPULACAO",
            "CLI_ATIVO",
            "POTENCIAL",
            "VOLUME_HL",
            "QTD_UMB",
            "POT_PROX_NVL",
            "QTD_PDV",
            "COB_POT",
            "FAT_HAB",
        )
        .with_columns(
            pl.when(pl.col("CLI_ATIVO") > 0)
            .then((pl.col("QTD_PDV") / pl.col("CLI_ATIVO") * 100).round(2))
            .otherwise(None)
            .alias("PERC_CLI_ATIVO"),
            pl.when(pl.col("POTENCIAL") > 0)
            .then((pl.col("QTD_PDV") / pl.col("POTENCIAL") * 0.75 * 100).round(2))
            .otherwise(None)
            .alias("PERC_CLI_POT_75"),
            (pl.col("POTENCIAL") - pl.col("CLI_ATIVO")).alias("POT_CRESC"),
        )
        .with_columns(
            pl.when((pl.col("PERC_CLI_ATIVO") > 0) & (pl.col("PERC_CLI_ATIVO") <= 55))
            .then(pl.lit(COR_AREA_0_M))
            .when((pl.col("PERC_CLI_ATIVO") > 55) & (pl.col("PERC_CLI_ATIVO") < 75))
            .then(pl.lit(COR_AREA_55))
            .otherwise(pl.lit(COR_AREA_75))
            .alias("COR_PERC_CLI_ATIVO")
        )
    )
    for coluna in (
        "POPULACAO",
        "CLI_ATIVO",
        "POTENCIAL",
        "POT_CRESC",
        "VOLUME_HL",
        "QTD_UMB",
        "QTD_PDV",
        "PERC_CLI_POT_75",
        "POT_PROX_NVL",
        "PERC_CLI_ATIVO",
        "COB_POT",
        "FAT_HAB",
    ):
        tabela = tabela.with_columns(pl.when(pl.col(coluna) <= 0).then(None).otherwise(pl.col(coluna)).alias(coluna))
    return tabela.select(
        "COD_IBGE",
        "COR_POT_PROX_NVL",
        "COR_AREA",
        "COR_PERC_CLI_ATIVO",
        "CIDADE",
        "DISTANCIA",
        "POPULACAO",
        "CLI_ATIVO",
        "POTENCIAL",
        "PERC_CLI_POT_75",
        "POT_CRESC",
        "VOLUME_HL",
        "QTD_UMB",
        "QTD_PDV",
        "POT_PROX_NVL",
        "PERC_CLI_ATIVO",
        "COB_POT",
        "FAT_HAB",
    )


def _preparar_clientes(tabela: pl.DataFrame, incluir_vendedor: bool) -> pl.DataFrame:
    colunas = ["CLI_ATIVO", "NOME", "FANTASIA", "MUNICIPIO", "ENDERECO", "PORTE", "CANAL"]
    if incluir_vendedor:
        colunas.append("VEN")
    colunas.extend(["TITULO_ABERTO", "POSSUI_CEV", "SUBEMPRESA", "ULTIMA_COMPRA"])
    return tabela.select(colunas).with_columns(
        pl.when(pl.col("POSSUI_CEV") == "SIM").then(pl.lit("Sim")).otherwise(pl.lit("Não")).alias("POSSUI_CEV"),
        pl.when(pl.col("TITULO_ABERTO") == "SIM").then(pl.lit("Sim")).otherwise(pl.lit("Não")).alias("TITULO_ABERTO"),
        pl.col("ULTIMA_COMPRA").str.to_date("%Y%m%d", strict=False),
    )


def ruptura_6m(dados: dict[str, object]) -> pl.DataFrame:
    limite = date.today() - relativedelta(months=6)
    tabela: pl.DataFrame = dados["clientes_ativos"]
    tabela = tabela.filter(pl.col("ULTIMA_COMPRA") <= limite.strftime("%Y%m%d"))
    return _preparar_clientes(tabela, incluir_vendedor=True)


def clientes_inativos(dados: dict[str, object]) -> pl.DataFrame:
    tabela: pl.DataFrame = dados["clientes_inativos"]
    return _preparar_clientes(tabela, incluir_vendedor=False)
