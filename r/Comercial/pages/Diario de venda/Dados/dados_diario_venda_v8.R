library(DBI)
library(stringr)
library(dplyr)
library(tidyr)
library(lubridate)
library(glue)

if (!exists("fonte_parquet_dv2", mode = "function", inherits = TRUE)) {
  source(glue("{diretorio}Cache/Diario de venda/cache_diario_venda.R"), local = TRUE, encoding = "UTF-8")
}

# Configurações do banco --------------------------------------------------



# Leitura de funcoes ------------------------------------------------------

## Ordenacao

source(glue("{diretorio}pages/Diario de venda/Dados/funcao_ordenacao_dv.R"), local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Diario de venda/Dados/exclusoes_dv.R"),       local = TRUE, encoding = "UTF-8")


# Mapeamento grupo -> revendas individuais -----------------------------------

revendas_por_grupo <- list(
  "GRUPO NATAL"    = c("Natal"),
  "GRUPO FILIAL C"     = c("Filial C"),
  "GRUPO FILIAL"     = c("Filial A", "Filial B"),
  "GRUPO SÃO LUÍS" = c("São Luís"),
  "GRUPO FILIAL PI" = c("Teresina", "Fortaleza"),
  "GRUPO FILIAL"       = c("Filial D", "Filial F", "Filial E")
)

# Revendas que agregam outras ao serem filtradas individualmente

if (revenda_query() == "GRUPO FILIAL"){
  rev_aliases_dv <- list(
    "Filial F" = c("Filial F", "Filial D")
  )
} else{
  rev_aliases_dv <- list(
    "Filial F" = c("Filial F")
  )
}


# Case canonical: revenda_query() retorna maiusculas; parquet usa proper-case
REVENDA_NOME_BD <- list(
  "NATAL"        = "Natal",
  "ESPECIAL"       = "Especial",
  "SÃO LUÍS"     = "São Luís",
  "FORTALEZA"     = "Fortaleza",
  "TERESINA"     = "Teresina",
  "FILIAL A" = "Filial A",
  "FILIAL B" = "Filial B",
  "FILIAL B" = "Filial B",
  "FILIAL C"         = "Filial C",
  "FILIAL F"   = "Filial F",
  "FILIAL F"   = "Filial F",
  "FILIAL D"     = "Filial D",
  "FILIAL D"     = "Filial D",
  "FILIAL E"    = "Filial E"
)

expandir_revendas_dv <- function(revenda) {
  revenda_norm <- if (!is.null(REVENDA_NOME_BD[[revenda]])) REVENDA_NOME_BD[[revenda]] else revenda
  if (!is.null(revendas_por_grupo[[revenda_norm]])) return(revendas_por_grupo[[revenda_norm]])
  if (!is.null(rev_aliases_dv[[revenda_norm]])) return(rev_aliases_dv[[revenda_norm]])
  alias_key <- names(rev_aliases_dv)[toupper(names(rev_aliases_dv)) == toupper(revenda_norm)]
  if (length(alias_key) > 0) return(rev_aliases_dv[[alias_key[1]]])
  revenda_norm
}


# Aba Diario de Vendas - Categorias ---------------------------------------

categorias_dv = function(revenda, mes, ven = NULL, ga = NULL, rev = NULL){
  revenda <- if (!is.null(REVENDA_NOME_BD[[revenda]])) REVENDA_NOME_BD[[revenda]] else revenda

  mes_1 = format(as.Date(paste0(mes, "01"), format = "%Y%m%d") %m-% months(1), format = "%Y%m")
  mes_2 = format(as.Date(paste0(mes, "01"), format = "%Y%m%d") %m-% months(2), format = "%Y%m")
  mes_3 = format(as.Date(paste0(mes, "01"), format = "%Y%m%d") %m-% months(3), format = "%Y%m")
  mes_11 = format(as.Date(paste0(mes, "01"), format = "%Y%m%d") %m-% months(11), format = "%Y%m")
  mes_12 = format(as.Date(paste0(mes, "01"), format = "%Y%m%d") %m-% months(12), format = "%Y%m")
  mes_24 = format(as.Date(paste0(mes, "01"), format = "%Y%m%d") %m-% months(24), format = "%Y%m")
  
  # Para o mes atual usa o acumulado progressivo do ano passado (atualizado diariamente);
  # para meses fechados usa o total real do mesmo mes do ano anterior.
  campo_aa_hl       <- if (mes == format(Sys.Date(), "%Y%m")) "DV.QTD_TOTAL_HL_AA" else "DV.QTD_TOTAL_HL"
  campo_aa          <- if (mes == format(Sys.Date(), "%Y%m")) "DV.QTD_TOTAL_AA"    else "DV.QTD_TOTAL"
  campo_cob_ano_ant <- if (mes == format(Sys.Date(), "%Y%m")) "CP.COB_CAT_AA"      else "CP.COB_CAT"
  
  revs_efetivas     <- expandir_revendas_dv(revenda)
  revs_sql          <- paste(paste0("'", revs_efetivas, "'"), collapse = ", ")
  filtro_revenda    <- paste0("REVENDA IN (", revs_sql, ")")
  filtro_revenda_dv <- paste0("DV.REVENDA IN (", revs_sql, ")")
  rev_exp <- if (!is.null(rev) && length(rev) > 0) {
    unique(unlist(lapply(rev, function(revenda_selecionada) expandir_revendas_dv(revenda_selecionada))))
  } else {
    rev
  }
  filtro_rev_sel <- if (!is.null(rev_exp) && length(rev_exp) > 0) paste0("AND REVENDA IN (", paste(paste0("'", gsub("'", "''", rev_exp), "'"), collapse = ", "), ")") else ""
  filtro_ga         <- if (!is.null(ga)  && length(ga)  > 0) paste0("AND GA  IN (", paste(paste0("'", gsub("'", "''", ga),  "'"), collapse = ", "), ")") else ""
  filtro_ven        <- if (!is.null(ven) && length(ven) > 0) paste0("AND VEN IN (", paste(paste0("'", gsub("'", "''", ven), "'"), collapse = ", "), ")") else ""
  
  filtro_ga_ven_ativo <- (!is.null(ga) && length(ga) > 0) || (!is.null(ven) && length(ven) > 0)
  filtro_rev_sel_f    <- if (!is.null(rev_exp) && length(rev_exp) > 0) paste0("AND F.REVENDA IN (", paste(paste0("'", gsub("'", "''", rev_exp), "'"), collapse = ", "), ")") else ""
  
  expr_rev    <- if (revenda == "GRUPO FILIAL") "CASE WHEN REVENDA IN ('Filial D') THEN 'Filial F' ELSE REVENDA END" else "REVENDA"
  expr_dv_rev <- if (revenda == "GRUPO FILIAL") "CASE WHEN DV.REVENDA IN ('Filial D') THEN 'Filial F' ELSE DV.REVENDA END" else "DV.REVENDA"

  query = glue("

  WITH DV_FILTRADO AS (
      SELECT * FROM TB_DIARIO_VENDA
      WHERE {filtro_revenda}
      {filtro_rev_sel}
      {filtro_ga}
      {filtro_ven}
  ),

  DV_COB_CAT AS (
    SELECT
        MES,
        {expr_rev} AS REVENDA,
        CATEGORIA,
        SUM(COB_CAT)    AS COB_CAT,
        SUM(COB_CAT_AA) AS COB_CAT_AA
    FROM TB_COB_CATEG
    WHERE {filtro_revenda}
      AND MES IN ('{mes_12}','{mes_1}','{mes}')
      {filtro_rev_sel}
      {filtro_ga}
      {filtro_ven}
    GROUP BY MES, {expr_rev}, CATEGORIA
  ),
  
  META_TOTAL AS (
      SELECT
          {expr_rev} AS REVENDA,
          MES,
          VOLUME_TOTAL,
          ROUND(SUM(QTD_META_REVENDA_HL),0) AS META_HL
      FROM TB_META_REVENDA
      WHERE {filtro_revenda}
        AND MES = '{mes}'
        {filtro_ga}
        {filtro_ven}
      GROUP BY {expr_rev}, MES, VOLUME_TOTAL
  ),

  META_MARCA AS (
      SELECT
          {expr_rev} AS REVENDA,
          MES,
          MARCA,
          ROUND(SUM(QTD_META_REVENDA_HL),0) AS META_HL
      FROM TB_META_REVENDA
      WHERE {filtro_revenda}
        AND MES = '{mes}'
        {filtro_ga}
        {filtro_ven}
      GROUP BY {expr_rev}, MES, MARCA
  ),

  META_SEGMENTO_1 AS (
    SELECT
        {expr_rev} AS REVENDA,
        MES,
        SEGMENTO,
        ROUND(SUM(QTD_META_REVENDA_HL),0) AS META_HL
    FROM TB_META_REVENDA
    WHERE {filtro_revenda}
        AND MES = '{mes}'
        {filtro_ga}
        {filtro_ven}
    GROUP BY {expr_rev}, MES, SEGMENTO
  ),

  META_SEGMENTO_2 AS (
      SELECT
          {expr_rev} AS REVENDA,
          MES,
          SEGMENTO_2,
          ROUND(SUM(QTD_META_REVENDA_HL),0) AS META_HL
      FROM TB_META_REVENDA
      WHERE {filtro_revenda}
        AND MES = '{mes}'
        {filtro_ga}
        {filtro_ven}
      GROUP BY {expr_rev}, MES, SEGMENTO_2
  ),

  META_SEGMENTO_3 AS (
      SELECT
          {expr_rev} AS REVENDA,
          MES,
          SEGMENTO_3,
          ROUND(SUM(QTD_META_REVENDA_HL),0) AS META_HL
      FROM TB_META_REVENDA
      WHERE {filtro_revenda}
        AND MES = '{mes}'
        {filtro_ga}
        {filtro_ven}
      GROUP BY {expr_rev}, MES, SEGMENTO_3
  ),

  META_SKU AS (
      SELECT
          {expr_rev} AS REVENDA,
          MES,
          SKU_GRUPO,
          ROUND(SUM(QTD_META_REVENDA_UMB),0) AS META_UMB
      FROM TB_META_REVENDA
      WHERE {filtro_revenda}
        AND MES = '{mes}'
        {filtro_ga}
        {filtro_ven}
      GROUP BY {expr_rev}, MES, SKU_GRUPO
  ),
  META_FABRICA AS (
  	SELECT
  		{expr_rev} AS REVENDA,
          MES,
  		CODRED,
  		SUM(VALOR)     AS VALOR,
  		SUM(VALOR_UMB) AS VALOR_UMB
  	FROM TB_META_FABRICA
  	WHERE {filtro_revenda}
  		  AND MES IN ('{mes}')
  	GROUP BY MES, {expr_rev}, CODRED
  ),

  LN_BASE AS (
      SELECT
          {expr_dv_rev} AS REVENDA,
          SUM(DV.QTD_TOTAL) AS VOL_LN,
          MAX(CP.COB_CAT) AS COB_LN
      FROM DV_FILTRADO DV
      LEFT JOIN DV_COB_CAT CP
          ON CP.MES = DV.MES
         AND CP.REVENDA = {expr_dv_rev}
         AND CP.CATEGORIA = DV.SKU_GRUPO
      WHERE {filtro_revenda_dv}
        AND DV.MES IN ('{mes}')
        AND DV.SKU_GRUPO IN ('MAR LN 330ML')
      GROUP BY {expr_dv_rev}
  ),

  CP_MARCA AS (
      SELECT MARCA AS CATEGORIA, SUM(QTD_HL) AS QTD
      FROM TB_COMPRA_PROD
      WHERE {filtro_revenda}
        AND MES = '{mes}'
        {filtro_rev_sel}
      GROUP BY MARCA
  ),

  CP_SEGMENTO AS (
      /*SELECT SEGMENTO AS CATEGORIA, SUM(QTD_HL) AS QTD*/
      SELECT SEGMENTO AS CATEGORIA, 0 AS QTD
      FROM TB_COMPRA_PROD
      WHERE {filtro_revenda}
        AND MES = '{mes}'
        {filtro_rev_sel}
      GROUP BY SEGMENTO
  ),

  CP_SEGMENTO_2 AS (
      SELECT SEGMENTO_2 AS CATEGORIA, SUM(QTD_HL) AS QTD
      FROM TB_COMPRA_PROD
      WHERE {filtro_revenda}
        AND MES = '{mes}'
        {filtro_rev_sel}
      GROUP BY SEGMENTO_2
  ),

  CP_SEGMENTO_3 AS (
      /*SELECT SEGMENTO_3 AS CATEGORIA, SUM(QTD_HL) AS QTD*/
      SELECT SEGMENTO_3 AS CATEGORIA, 0 AS QTD
      FROM TB_COMPRA_PROD
      WHERE {filtro_revenda}
        AND MES = '{mes}'
        {filtro_rev_sel}
      GROUP BY SEGMENTO_3
  ),

  CP_VOL_TOTAL AS (
      SELECT VOLUME_TOTAL AS CATEGORIA, SUM(QTD_HL) AS QTD
      FROM TB_COMPRA_PROD
      WHERE {filtro_revenda}
        AND MES = '{mes}'
        {filtro_rev_sel}
      GROUP BY VOLUME_TOTAL
  ),

  DV_TOTAL AS (
      SELECT
          {expr_dv_rev} AS REVENDA,
          'TOTAL' AS NIVEL,
          DV.VOLUME_TOTAL AS CATEGORIA,
  
          ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_RETRASADO,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_2}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_2,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_1}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ANT,
          ROUND(SUM(DISTINCT CASE WHEN DV.MES = '{mes}' THEN MF.VALOR ELSE 0 END), 0) AS META_FAB,
          ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0) AS META_REV,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_ANT,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN {campo_aa_hl} ELSE 0 END), 0) AS VOL_ANO_ANT2,
          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ATUAL,
  		ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) AS TEND,
          ROUND(ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) / NULLIF(ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0), 0), 4) AS PERC_TEND,
          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.VALOR_VENDA ELSE 0 END) / NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0), 2) AS VENDA_HL,
      		COALESCE(MAX(CP_VT.QTD), 0) AS PERC_VOL_LN,
      		CASE WHEN COALESCE(MAX(CP_VT.QTD), 0) <= 0 
        		THEN 0
        		ELSE ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) - COALESCE(MAX(CP_VT.QTD), 0)
        	END AS PERC_COB_LN,
          ROUND(MAX( CASE WHEN DV.MES = '{mes_1}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ANT,
          ROUND(MAX( CASE WHEN DV.MES = '{mes_12}' THEN {campo_cob_ano_ant} ELSE NULL END), 0) AS COB_ANO_ANT,
          ROUND(MAX( CASE WHEN DV.MES = '{mes}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ATUAL,

          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS FAT
      FROM DV_FILTRADO DV
      LEFT JOIN DV_COB_CAT CP
          ON CP.MES = DV.MES
         AND CP.REVENDA = {expr_dv_rev}
         AND CP.CATEGORIA = DV.VOLUME_TOTAL
  	LEFT JOIN META_TOTAL MR
  		ON MR.MES = DV.MES
  	   AND MR.REVENDA = {expr_dv_rev}
  	   AND MR.VOLUME_TOTAL = DV.VOLUME_TOTAL
  	LEFT JOIN META_FABRICA MF
  		ON MF.MES = DV.MES
  	   AND MF.REVENDA = {expr_dv_rev}
  	   AND MF.CODRED = DV.CODRED
      LEFT JOIN CP_VOL_TOTAL CP_VT ON CP_VT.CATEGORIA = DV.VOLUME_TOTAL
      WHERE {filtro_revenda_dv}
        AND DV.MES IN ('{mes_24}','{mes_2}','{mes_1}','{mes_12}','{mes}','{mes_11}')
        AND DV.VOLUME_TOTAL IS NOT NULL
      GROUP BY {expr_dv_rev}, DV.VOLUME_TOTAL
  ),
  
  DV_MARCA AS (
      SELECT
          {expr_dv_rev} AS REVENDA,
          'MARCA' AS NIVEL,
          DV.MARCA AS CATEGORIA,
  
          ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_RETRASADO,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_2}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_2,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_1}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ANT,
          ROUND(SUM(DISTINCT CASE WHEN DV.MES = '{mes}' THEN MF.VALOR ELSE 0 END), 0) AS META_FAB,
          ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0) AS META_REV,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_ANT,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN {campo_aa_hl} ELSE 0 END), 0) AS VOL_ANO_ANT2,
          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ATUAL,
  		ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) AS TEND,
          ROUND(ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) / NULLIF(ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0), 0), 4) AS PERC_TEND,
          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.VALOR_VENDA ELSE 0 END) / NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0), 2) AS VENDA_HL,
      		COALESCE(MAX(CP_M.QTD), 0) AS PERC_VOL_LN,
      		CASE WHEN COALESCE(MAX(CP_M.QTD), 0) <= 0
      		  THEN 0
      		  ELSE ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) - COALESCE(MAX(CP_M.QTD), 0)  
      		END AS PERC_COB_LN,
          ROUND(MAX( CASE WHEN DV.MES = '{mes_1}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ANT,
          ROUND(MAX( CASE WHEN DV.MES = '{mes_12}' THEN {campo_cob_ano_ant} ELSE NULL END), 0) AS COB_ANO_ANT,
          ROUND(MAX( CASE WHEN DV.MES = '{mes}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ATUAL,

          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS FAT
      FROM DV_FILTRADO DV
      LEFT JOIN DV_COB_CAT CP
          ON CP.MES = DV.MES
         AND CP.REVENDA = {expr_dv_rev}
         AND CP.CATEGORIA = DV.MARCA
  	LEFT JOIN META_MARCA MR
  		ON MR.MES = DV.MES
  	   AND MR.REVENDA = {expr_dv_rev}
  	   AND MR.MARCA = DV.MARCA
  	LEFT JOIN META_FABRICA MF
  		ON MF.MES = DV.MES
  	   AND MF.REVENDA = {expr_dv_rev}
  	   AND MF.CODRED = DV.CODRED
      LEFT JOIN CP_MARCA CP_M ON CP_M.CATEGORIA = DV.MARCA
      WHERE {filtro_revenda_dv}
        AND DV.MES IN ('{mes_24}','{mes_2}','{mes_1}','{mes_12}','{mes}','{mes_11}')
        AND DV.MARCA IS NOT NULL
      GROUP BY {expr_dv_rev}, DV.MARCA
  ),
  
  DV_SEGMENTO_1 AS (
    SELECT 
        {expr_dv_rev} AS REVENDA,
        'SEGMENTO' AS NIVEL,
        DV.SEGMENTO AS CATEGORIA,

          ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_RETRASADO,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_2}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_2,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_1}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ANT,
          ROUND(SUM(DISTINCT CASE WHEN DV.MES = '{mes}' THEN MF.VALOR ELSE 0 END), 0) AS META_FAB,
          ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0) AS META_REV,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_ANT,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN {campo_aa_hl} ELSE 0 END), 0) AS VOL_ANO_ANT2,
          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ATUAL,
  		ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) AS TEND,
          ROUND(ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) / NULLIF(ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0), 0), 4) AS PERC_TEND,
          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.VALOR_VENDA ELSE 0 END) / NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0), 2) AS VENDA_HL,
      		COALESCE(MAX(CP_S.QTD), 0) AS PERC_VOL_LN,
      		0 AS PERC_COB_LN,
          ROUND(MAX( CASE WHEN DV.MES = '{mes_1}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ANT,
          ROUND(MAX( CASE WHEN DV.MES = '{mes_12}' THEN {campo_cob_ano_ant} ELSE NULL END), 0) AS COB_ANO_ANT,
          ROUND(MAX( CASE WHEN DV.MES = '{mes}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ATUAL,

          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS FAT
      FROM DV_FILTRADO DV
    LEFT JOIN DV_COB_CAT CP
        ON CP.MES = DV.MES
       AND CP.REVENDA = {expr_dv_rev}
       AND CP.CATEGORIA = DV.SEGMENTO
  	LEFT JOIN META_SEGMENTO_1 MR
  		ON MR.MES = DV.MES
  	   AND MR.REVENDA = {expr_dv_rev}
  	   AND MR.SEGMENTO = DV.SEGMENTO
  	LEFT JOIN META_FABRICA MF
  		ON MF.MES = DV.MES
  	   AND MF.REVENDA = {expr_dv_rev}
  	   AND MF.CODRED = DV.CODRED
      LEFT JOIN CP_SEGMENTO CP_S ON CP_S.CATEGORIA = DV.SEGMENTO
      WHERE {filtro_revenda_dv}
        AND DV.MES IN ('{mes_24}','{mes_2}','{mes_1}','{mes_12}','{mes}')
        AND DV.SEGMENTO IS NOT NULL
      GROUP BY {expr_dv_rev}, DV.SEGMENTO
  ),
  
  DV_SEGMENTO_2 AS (
      SELECT 
          {expr_dv_rev} AS REVENDA,
          'SEGMENTO_2' AS NIVEL,
          DV.SEGMENTO_2 AS CATEGORIA,
  
          ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_RETRASADO,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_2}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_2,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_1}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ANT,
          ROUND(SUM(DISTINCT CASE WHEN DV.MES = '{mes}' THEN MF.VALOR ELSE 0 END), 0) AS META_FAB,
          ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0) AS META_REV,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_ANT,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN {campo_aa_hl} ELSE 0 END), 0) AS VOL_ANO_ANT2,
          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ATUAL,
  		ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) AS TEND,
          ROUND(ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) / NULLIF(ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0), 0), 4) AS PERC_TEND,
          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.VALOR_VENDA ELSE 0 END) / NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0), 2) AS VENDA_HL,
      		COALESCE(MAX(CP_S2.QTD), 0) AS PERC_VOL_LN,
      		CASE WHEN COALESCE(MAX(CP_S2.QTD), 0) <= 0
      		  THEN 0
      		  ELSE ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) - COALESCE(MAX(CP_S2.QTD), 0) 
      		END AS PERC_COB_LN,
          ROUND(MAX( CASE WHEN DV.MES = '{mes_1}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ANT,
          ROUND(MAX( CASE WHEN DV.MES = '{mes_12}' THEN {campo_cob_ano_ant} ELSE NULL END), 0) AS COB_ANO_ANT,
          ROUND(MAX( CASE WHEN DV.MES = '{mes}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ATUAL,

          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS FAT
       FROM DV_FILTRADO DV
      LEFT JOIN DV_COB_CAT CP
          ON CP.MES = DV.MES
         AND CP.REVENDA = {expr_dv_rev}
         AND CP.CATEGORIA = DV.SEGMENTO_2
  	LEFT JOIN META_SEGMENTO_2 MR
  		ON MR.MES = DV.MES
  	   AND MR.REVENDA = {expr_dv_rev}
  	   AND MR.SEGMENTO_2 = DV.SEGMENTO_2
  	LEFT JOIN META_FABRICA MF
  		ON MF.MES = DV.MES
  	   AND MF.REVENDA = {expr_dv_rev}
  	   AND MF.CODRED = DV.CODRED
      LEFT JOIN CP_SEGMENTO_2 CP_S2 ON CP_S2.CATEGORIA = DV.SEGMENTO_2
      WHERE {filtro_revenda_dv}
        AND DV.MES IN ('{mes_24}','{mes_2}','{mes_1}','{mes_12}','{mes}')
        AND DV.SEGMENTO_2 IS NOT NULL
      GROUP BY {expr_dv_rev}, DV.SEGMENTO_2
  ),
  
  DV_SEGMENTO_3 AS (
      SELECT 
          {expr_dv_rev} AS REVENDA,
          'SEGMENTO_3' AS NIVEL,
          DV.SEGMENTO_3 AS CATEGORIA,
  
          ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_RETRASADO,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_2}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_2,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_1}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ANT,
          ROUND(SUM(DISTINCT CASE WHEN DV.MES = '{mes}' THEN MF.VALOR ELSE 0 END), 0) AS META_FAB,
          ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0) AS META_REV,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_ANT,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN {campo_aa_hl} ELSE 0 END), 0) AS VOL_ANO_ANT2,
          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ATUAL,
  		ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) AS TEND,
          ROUND(ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) / NULLIF(ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0), 0), 4) AS PERC_TEND,
          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.VALOR_VENDA ELSE 0 END) / NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0), 2) AS VENDA_HL,
      		COALESCE(MAX(CP_S3.QTD), 0) AS PERC_VOL_LN,
      		0 AS PERC_COB_LN,
          ROUND(MAX( CASE WHEN DV.MES = '{mes_1}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ANT,
          ROUND(MAX( CASE WHEN DV.MES = '{mes_12}' THEN {campo_cob_ano_ant} ELSE NULL END), 0) AS COB_ANO_ANT,
          ROUND(MAX( CASE WHEN DV.MES = '{mes}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ATUAL,

          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS FAT
       FROM DV_FILTRADO DV
      LEFT JOIN DV_COB_CAT CP
          ON CP.MES = DV.MES
         AND CP.REVENDA = {expr_dv_rev}
         AND CP.CATEGORIA = DV.SEGMENTO_3
  	LEFT JOIN META_SEGMENTO_3 MR
  		ON MR.MES = DV.MES
  	   AND MR.REVENDA = {expr_dv_rev}
  	   AND MR.SEGMENTO_3 = DV.SEGMENTO_3
  	LEFT JOIN META_FABRICA MF
  		ON MF.MES = DV.MES
  	   AND MF.REVENDA = {expr_dv_rev}
  	   AND MF.CODRED = DV.CODRED
      LEFT JOIN CP_SEGMENTO_3 CP_S3 ON CP_S3.CATEGORIA = DV.SEGMENTO_3
      WHERE {filtro_revenda_dv}
        AND DV.MES IN ('{mes_24}','{mes_2}','{mes_1}','{mes_12}','{mes}')
        AND DV.SEGMENTO_3 IS NOT NULL
      GROUP BY {expr_dv_rev}, DV.SEGMENTO_3
  ),
  
  DV_SKU AS (
      SELECT 
          {expr_dv_rev} AS REVENDA,
          'SKU' AS NIVEL,
          DV.SKU_GRUPO AS CATEGORIA,
  
          ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.QTD_TOTAL ELSE 0 END), 0) AS VOL_ANO_RETRASADO,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_2}' THEN DV.QTD_TOTAL ELSE 0 END), 0) AS VOL_MES_2,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_1}' THEN DV.QTD_TOTAL ELSE 0 END), 0) AS VOL_MES_ANT,
          ROUND(SUM(DISTINCT CASE WHEN DV.MES = '{mes}' THEN MF.VALOR_UMB ELSE 0 END), 0) AS META_FAB,
          ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_UMB ELSE 0 END), 0) AS META_REV,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN DV.QTD_TOTAL ELSE 0 END), 0) AS VOL_ANO_ANT,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN {campo_aa} ELSE 0 END), 0) AS VOL_ANO_ANT2,
          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL ELSE 0 END), 0) AS VOL_MES_ATUAL,
  		ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_UMB ELSE 0 END), 0) AS TEND,
          ROUND(ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_UMB ELSE 0 END), 0) / NULLIF(ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_UMB ELSE 0 END), 0), 0), 4) AS PERC_TEND,
          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.VALOR_VENDA ELSE 0 END) / NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL ELSE 0 END), 0), 2) AS VENDA_HL,
  		ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL ELSE 0 END) / NULLIF(MAX(LN.VOL_LN),0), 4) AS PERC_VOL_LN,
  		ROUND(MAX(CASE WHEN DV.MES = '{mes}' THEN CP.COB_CAT ELSE NULL END) / NULLIF(MAX(LN.COB_LN),0), 4) AS PERC_COB_LN,
          ROUND(MAX( CASE WHEN DV.MES = '{mes_1}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ANT,
          ROUND(MAX( CASE WHEN DV.MES = '{mes_12}' THEN {campo_cob_ano_ant} ELSE NULL END), 0) AS COB_ANO_ANT,
          ROUND(MAX( CASE WHEN DV.MES = '{mes}' THEN CP.COB_CAT ELSE NULL END), 0) AS COB_MES_ATUAL,
  
          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS FAT
      FROM DV_FILTRADO DV
      LEFT JOIN DV_COB_CAT CP
          ON CP.MES = DV.MES
         AND CP.REVENDA = {expr_dv_rev}
         AND CP.CATEGORIA = DV.SKU_GRUPO
  	LEFT JOIN META_SKU MR
  		ON MR.MES = DV.MES
  	   AND MR.REVENDA = {expr_dv_rev}
  	   AND MR.SKU_GRUPO = DV.SKU_GRUPO
  	LEFT JOIN LN_BASE LN
  		ON LN.REVENDA = {expr_dv_rev}
  	LEFT JOIN META_FABRICA MF
  		ON MF.MES     = DV.MES
  	   AND MF.REVENDA = {expr_dv_rev}
  	   AND MF.CODRED  = DV.CODRED
      WHERE {filtro_revenda_dv}
        AND DV.MES IN ('{mes_24}','{mes_2}','{mes_1}','{mes_12}','{mes}')
        AND DV.SKU_GRUPO IS NOT NULL
      GROUP BY {expr_dv_rev}, DV.SKU_GRUPO
  ),
  
  DV_FATURAMENTO AS (
      SELECT 
          {expr_dv_rev} AS REVENDA,
          'FATURAMENTO' AS NIVEL,
          DV.CANAL AS CATEGORIA,
  
          ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS VOL_ANO_RETRASADO,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_2}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS VOL_MES_2,
          ROUND(SUM(CASE WHEN DV.MES = '{mes_1}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS VOL_MES_ANT,
          0 AS META_FAB,
          0 AS META_REV,
          0 AS VOL_ANO_ANT,
          0 AS VOL_ANO_ANT2,
          ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS VOL_MES_ATUAL,
          0 AS TEND,
          0 AS PERC_TEND,
          0 AS VENDA_HL,
          0 AS PERC_VOL_LN,
          0 AS PERC_COB_LN,
          0 AS COB_MES_ANT,
          0 AS COB_ANO_ANT,
          0 AS COB_MES_ATUAL,
          0 AS FAT
      FROM DV_FILTRADO DV
      WHERE {filtro_revenda_dv}
        AND DV.MES IN ('{mes_24}','{mes_2}','{mes_1}','{mes_12}','{mes}')
        AND DV.CANAL IN ('OW', 'RGB')
      GROUP BY {expr_dv_rev}, DV.CANAL
  ),
  
  MARE_600 AS (
      SELECT MES, SUM(COB_CAT) AS COB_CAT
      FROM DV_COB_CAT
      WHERE CATEGORIA = 'MARÉ 600ml'
      GROUP BY MES
  ),

  CORAL_600 AS (
      SELECT MES, SUM(COB_CAT) AS COB_CAT
      FROM DV_COB_CAT
      WHERE CATEGORIA = 'CORAL 600ml'
      GROUP BY MES
  ),

  MARE_0 AS (
      SELECT MES, SUM(COB_CAT) AS COB_CAT
      FROM DV_COB_CAT
      WHERE CATEGORIA = '0%'
        AND MES IN ('{mes_2}','{mes_1}','{mes}')
      GROUP BY MES
  ),

  MARE_CAT AS (
      SELECT MES, SUM(COB_CAT) AS COB_CAT
      FROM DV_COB_CAT
      WHERE CATEGORIA = 'MARÉ'
        AND MES IN ('{mes_12}','{mes_1}','{mes}')
      GROUP BY MES
  ),

  RGB_TOTAL AS (
      SELECT MES, SUM(COB_CAT) AS COB_CAT
      FROM DV_COB_CAT
      WHERE CATEGORIA = 'RGB'
        AND MES IN ('{mes_12}','{mes_1}','{mes}')
      GROUP BY MES
  ),

  BASE_IND AS (

      SELECT
          '{revenda}'           AS REVENDA,
          R.MES,
          'PERC_CORAL_MAR_600' AS INDICADOR,
          A600.COB_CAT / NULLIF(H600.COB_CAT, 0) AS VALOR,
          60 AS META
      FROM RGB_TOTAL R
      LEFT JOIN MARE_600 H600 ON H600.MES = R.MES
      LEFT JOIN CORAL_600   A600 ON A600.MES = R.MES

      UNION ALL

      SELECT
          '{revenda}'             AS REVENDA,
          R.MES,
          'PERC_MARE_600_RGB' AS INDICADOR,
          H600.COB_CAT / NULLIF(R.COB_CAT, 0) AS VALOR,
          70 AS META
      FROM RGB_TOTAL R
      LEFT JOIN MARE_600 H600 ON H600.MES = R.MES

      UNION ALL

      SELECT
          '{revenda}'          AS REVENDA,
          R.MES,
          'PERC_MARE_0_TT' AS INDICADOR,
          H0.COB_CAT / NULLIF(HC.COB_CAT, 0) AS VALOR,
          40 AS META
      FROM RGB_TOTAL R
      LEFT JOIN MARE_0   H0 ON H0.MES = R.MES
      LEFT JOIN MARE_CAT HC ON HC.MES = R.MES
  ),
  
  INDI AS (
  SELECT
      REVENDA,
      'INDICADOR' AS NIVEL,
      INDICADOR AS CATEGORIA,
      0 AS VOL_ANO_RETRASADO,
      ROUND(MAX(CASE WHEN MES = '{mes_2}' THEN VALOR END) * 100, 2) AS VOL_MES_2,
      ROUND(MAX(CASE WHEN MES = '{mes_1}' THEN VALOR END) * 100, 2) AS VOL_MES_ANT,
      0 AS META_FAB,
      META AS META_REV,
      0 AS VOL_ANO_ANT,
      0 AS VOL_ANO_ANT2,
      ROUND(MAX(CASE WHEN MES = '{mes}' THEN VALOR END) * 100, 2) AS VOL_MES_ATUAL,
      0 AS TEND,
      0 AS PERC_TEND,
      0 AS VENDA_HL,
      0 AS PERC_VOL_LN,
      0 AS PERC_COB_LN,
      0 AS COB_MES_ANT,
      0 AS COB_ANO_ANT,
      0 AS COB_MES_ATUAL,
      0 AS FAT
  
  FROM BASE_IND
  GROUP BY
      REVENDA,
      INDICADOR,
      META
  ORDER BY
      INDICADOR
  )

  SELECT *
  FROM DV_TOTAL

  UNION ALL

  SELECT *
  FROM DV_MARCA

  UNION ALL

  SELECT *
  FROM DV_SEGMENTO_1

  UNION ALL

  SELECT *
  FROM DV_SEGMENTO_2

  UNION ALL

  SELECT *
  FROM DV_SKU


  UNION ALL

  SELECT *
  FROM DV_SEGMENTO_3


  UNION ALL

  SELECT *
  FROM INDI

  UNION ALL

  SELECT *
  FROM DV_FATURAMENTO;
  ")
  
  tabela_final = fonte_parquet_dv2(query)
  
  revs_sql_upper       <- paste(paste0("'", toupper(revs_efetivas), "'"), collapse = ", ")
  filtro_revenda_upper <- paste0("UPPER(REVENDA) IN (", revs_sql_upper, ")")
  filtro_rev_sel_upper <- if (!is.null(rev_exp) && length(rev_exp) > 0) paste0("AND UPPER(REVENDA) IN (", paste(paste0("'", toupper(gsub("'", "''", rev_exp)), "'"), collapse = ", "), ")") else ""
  
  if (filtro_ga_ven_ativo) {
    
    query_skupdv_rev = glue("
    WITH META_REVENDA AS (
        SELECT REVENDA, MES, SUM(QTD_META_REVENDA_HL) AS META_REVENDA
        FROM TB_META_REVENDA
        WHERE {filtro_revenda}
          AND MES IN ('{mes_2}', '{mes_1}', '{mes}')
          {filtro_rev_sel}
          {filtro_ga}
          {filtro_ven}
        GROUP BY REVENDA, MES
    ),
    QTD_SKU_VEN AS (
        SELECT REVENDA, MES, SUM(QTD_SKU_PDV) AS QTD_SKU_PDV
        FROM TB_COB_CLI
        WHERE {filtro_revenda}
          AND MES IN ('{mes_2}', '{mes_1}', '{mes}')
          {filtro_rev_sel}
          {filtro_ga}
          {filtro_ven}
        GROUP BY REVENDA, MES
    ),
    BASE AS (
        SELECT MR.REVENDA, MR.MES,
               COALESCE(SV.QTD_SKU_PDV, 0) AS QTD_SKU_PDV,
               MR.META_REVENDA
        FROM META_REVENDA MR
        LEFT JOIN QTD_SKU_VEN SV ON SV.REVENDA = MR.REVENDA AND SV.MES = MR.MES
    )
    SELECT
        '{revenda}'        AS REVENDA,
        'INDICADOR'        AS NIVEL,
        'SKU/PDV REVENDA'  AS CATEGORIA,
        0 AS VOL_ANO_RETRASADO,
        ROUND(SUM(CASE WHEN MES = '{mes_2}' THEN QTD_SKU_PDV ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes_2}' THEN META_REVENDA ELSE 0 END), 0), 2) AS VOL_MES_2,
        ROUND(SUM(CASE WHEN MES = '{mes_1}' THEN QTD_SKU_PDV ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes_1}' THEN META_REVENDA ELSE 0 END), 0), 2) AS VOL_MES_ANT,
        0     AS META_FAB,
        5.0   AS META_REV,
        0     AS VOL_ANO_ANT,
        0     AS VOL_ANO_ANT2,
        ROUND(SUM(CASE WHEN MES = '{mes}' THEN QTD_SKU_PDV ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes}' THEN META_REVENDA ELSE 0 END), 0), 2) AS VOL_MES_ATUAL,
        0 AS TEND,
        0 AS PERC_TEND,
        0 AS VENDA_HL,
        0 AS PERC_VOL_LN,
        0 AS PERC_COB_LN,
        0 AS COB_MES_ANT,
        0 AS COB_ANO_ANT,
        0 AS COB_MES_ATUAL,
        0 AS FAT
    FROM BASE
  ")
    
    tabela_final_skupdv = fonte_parquet_dv2(query_skupdv_rev) %>%
      mutate(across(-c(REVENDA, NIVEL, CATEGORIA), as.double))
    
  } else {
    
    rev_norm_sql <- if (revenda_query() == "GRUPO FILIAL") {
      "CASE WHEN REVENDA = 'Filial D' THEN 'Filial F' ELSE REVENDA END"
    } else {
      "REVENDA"
    }

    query_skupdv_abp = glue("
    WITH META_ABP AS (
        SELECT REVENDA, MES, SUM(VALOR) AS META_ABP
        FROM TB_META_ABP
        WHERE {filtro_revenda_upper}
          AND MES IN ('{mes_2}', '{mes_1}', '{mes}')
          {filtro_rev_sel_upper}
        GROUP BY REVENDA, MES
    ),
    QTD_SKU AS (
        SELECT {rev_norm_sql} AS REVENDA, MES, SUM(QTD_SKU_PDV) AS QTD_SKU_PDV
        FROM TB_COB_CLI
        WHERE {filtro_revenda}
          AND MES IN ('{mes_2}', '{mes_1}', '{mes}')
          {filtro_rev_sel}
        GROUP BY 1, 2
    ),
    BASE AS (
        SELECT MA.REVENDA, MA.MES,
               COALESCE(SV.QTD_SKU_PDV, 0) AS QTD_SKU_PDV,
               MA.META_ABP
        FROM META_ABP MA
        LEFT JOIN QTD_SKU SV ON SV.REVENDA = MA.REVENDA AND SV.MES = MA.MES
    )
    SELECT
        '{revenda}'   AS REVENDA,
        'INDICADOR'   AS NIVEL,
        'SKU/PDV ABP' AS CATEGORIA,
        0 AS VOL_ANO_RETRASADO,
        ROUND(SUM(CASE WHEN MES = '{mes_2}' THEN QTD_SKU_PDV ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes_2}' THEN META_ABP ELSE 0 END), 0), 2) AS VOL_MES_2,
        ROUND(SUM(CASE WHEN MES = '{mes_1}' THEN QTD_SKU_PDV ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes_1}' THEN META_ABP ELSE 0 END), 0), 2) AS VOL_MES_ANT,
        0     AS META_FAB,
        5.0   AS META_REV,
        0     AS VOL_ANO_ANT,
        0     AS VOL_ANO_ANT2,
        ROUND(SUM(CASE WHEN MES = '{mes}' THEN QTD_SKU_PDV ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes}' THEN META_ABP ELSE 0 END), 0), 2) AS VOL_MES_ATUAL,
        0 AS TEND,
        0 AS PERC_TEND,
        0 AS VENDA_HL,
        0 AS PERC_VOL_LN,
        0 AS PERC_COB_LN,
        0 AS COB_MES_ANT,
        0 AS COB_ANO_ANT,
        0 AS COB_MES_ATUAL,
        0 AS FAT
    FROM BASE
  ")
    
    tabela_final_skupdv = fonte_parquet_dv2(query_skupdv_abp) %>%
      mutate(across(-c(REVENDA, NIVEL, CATEGORIA), as.double))
    
  }
  
  if (filtro_ga_ven_ativo) {
    
    query_fds_rev = glue("
    SELECT
        '{revenda}'   AS REVENDA,
        'INDICADOR'   AS NIVEL,
        'FDS REVENDA' AS CATEGORIA,
        0 AS VOL_ANO_RETRASADO,
        ROUND(SUM(CASE WHEN MES = '{mes_2}' THEN GRUPOS_META ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes_2}' THEN TOTAL_GRUPOS ELSE 0 END), 0) * 100, 2) AS VOL_MES_2,
        ROUND(SUM(CASE WHEN MES = '{mes_1}' THEN GRUPOS_META ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes_1}' THEN TOTAL_GRUPOS ELSE 0 END), 0) * 100, 2) AS VOL_MES_ANT,
        0 AS META_FAB,
        50 AS META_REV,
        0 AS VOL_ANO_ANT,
        0 AS VOL_ANO_ANT2,
        ROUND(SUM(CASE WHEN MES = '{mes}' THEN GRUPOS_META ELSE 0 END) / NULLIF(SUM(CASE WHEN MES = '{mes}' THEN TOTAL_GRUPOS ELSE 0 END), 0) * 100, 2) AS VOL_MES_ATUAL,
        0 AS TEND,
        0 AS PERC_TEND,
        0 AS VENDA_HL,
        0 AS PERC_VOL_LN,
        0 AS PERC_COB_LN,
        0 AS COB_MES_ANT,
        0 AS COB_ANO_ANT,
        0 AS COB_MES_ATUAL,
        0 AS FAT
    FROM TB_EXIG_FDS
    WHERE {filtro_revenda}
      AND MES IN ('{mes_2}', '{mes_1}', '{mes}')
      {filtro_rev_sel}
      {filtro_ga}
      {filtro_ven}
  ")
    tabela_final_fds = fonte_parquet_dv2(query_fds_rev) %>%
      mutate(across(-c(REVENDA, NIVEL, CATEGORIA), as.double))
    
  } else {
    
    query_fds_abp = glue("
    SELECT
        '{revenda}' AS REVENDA,
        'INDICADOR' AS NIVEL,
        'FDS ABP'   AS CATEGORIA,
        0 AS VOL_ANO_RETRASADO,
        ROUND(SUM(CASE WHEN F.MES = '{mes_2}' THEN F.GRUPOS_META ELSE 0 END) / NULLIF(MAX(CASE WHEN F.MES = '{mes_2}' THEN M.META_FDS END) * 100, 0) * 100, 2) AS VOL_MES_2,
        ROUND(SUM(CASE WHEN F.MES = '{mes_1}' THEN F.GRUPOS_META ELSE 0 END) / NULLIF(MAX(CASE WHEN F.MES = '{mes_1}' THEN M.META_FDS END) * 100, 0) * 100, 2) AS VOL_MES_ANT,
        0 AS META_FAB,
        50 AS META_REV,
        0 AS VOL_ANO_ANT,
        0 AS VOL_ANO_ANT2,
        ROUND(SUM(CASE WHEN F.MES = '{mes}' THEN F.GRUPOS_META ELSE 0 END) / NULLIF(MAX(CASE WHEN F.MES = '{mes}' THEN M.META_FDS END) * 100, 0) * 100, 2) AS VOL_MES_ATUAL,
        0 AS TEND,
        0 AS PERC_TEND,
        0 AS VENDA_HL,
        0 AS PERC_VOL_LN,
        0 AS PERC_COB_LN,
        0 AS COB_MES_ANT,
        0 AS COB_ANO_ANT,
        0 AS COB_MES_ATUAL,
        0 AS FAT
    FROM TB_EXIG_FDS F
    JOIN (
        SELECT C.REVENDA, C.MES,
            CASE WHEN A.VALOR IS NULL OR A.VALOR = 0 THEN C.QTD_PDV ELSE A.VALOR END AS META_FDS
        FROM TB_COB_REV C
        LEFT JOIN TB_META_ABP A ON A.REVENDA = C.REVENDA AND A.MES = C.MES
        WHERE C.REVENDA IN ({revs_sql})
          AND C.MES IN ('{mes_2}', '{mes_1}', '{mes}')
    ) M ON M.REVENDA = F.REVENDA AND M.MES = F.MES
    WHERE F.REVENDA IN ({revs_sql})
      AND F.MES IN ('{mes_2}', '{mes_1}', '{mes}')
      {filtro_rev_sel_f}
  ")
    tabela_final_fds = fonte_parquet_dv2(query_fds_abp) %>%
      mutate(across(-c(REVENDA, NIVEL, CATEGORIA), as.double))

  }

  if (nrow(tabela_final_skupdv) > 0) {
    tabela_final <- bind_rows(tabela_final, tabela_final_skupdv)
  }
  
  if (nrow(tabela_final_fds) > 0) {
    tabela_final <- bind_rows(tabela_final, tabela_final_fds)
  }
  
  if (length(revs_efetivas) > 1) {
    tabela_final <- tabela_final %>%
      mutate(
        VALOR_HL_POND = ifelse(!is.na(VENDA_HL) & !is.na(VOL_MES_ATUAL) & VOL_MES_ATUAL > 0,
                               VENDA_HL * VOL_MES_ATUAL, NA_real_),
        VOL_HL_POND   = ifelse(!is.na(VENDA_HL) & !is.na(VOL_MES_ATUAL) & VOL_MES_ATUAL > 0,
                               VOL_MES_ATUAL, NA_real_),
        VOL_LN_BACK   = ifelse(!is.na(PERC_VOL_LN) & PERC_VOL_LN > 0 & VOL_MES_ATUAL > 0,
                               VOL_MES_ATUAL / PERC_VOL_LN, NA_real_),
        VOL_SKU_LN    = ifelse(!is.na(PERC_VOL_LN) & PERC_VOL_LN > 0 & VOL_MES_ATUAL > 0,
                               VOL_MES_ATUAL, NA_real_),
        COB_LN_BACK   = ifelse(!is.na(PERC_COB_LN) & PERC_COB_LN > 0 & !is.na(COB_MES_ATUAL) & COB_MES_ATUAL > 0,
                               COB_MES_ATUAL / PERC_COB_LN, NA_real_),
        COB_SKU_LN    = ifelse(!is.na(PERC_COB_LN) & PERC_COB_LN > 0 & !is.na(COB_MES_ATUAL) & COB_MES_ATUAL > 0,
                               COB_MES_ATUAL, NA_real_)
      ) %>%
      group_by(NIVEL, CATEGORIA) %>%
      summarise(
        REVENDA           = revenda,
        VOL_ANO_RETRASADO = if (first(NIVEL) == "INDICADOR") NA_real_              else sum(VOL_ANO_RETRASADO, na.rm = TRUE),
        VOL_MES_2         = if (first(NIVEL) == "INDICADOR") first(VOL_MES_2)      else sum(VOL_MES_2,         na.rm = TRUE),
        VOL_MES_ANT       = if (first(NIVEL) == "INDICADOR") first(VOL_MES_ANT)    else sum(VOL_MES_ANT,       na.rm = TRUE),
        META_FAB          = if (first(NIVEL) == "INDICADOR") NA_real_              else sum(META_FAB,           na.rm = TRUE),
        META_REV          = if (first(NIVEL) == "INDICADOR") max(META_REV, na.rm = TRUE) else sum(META_REV, na.rm = TRUE),
        VOL_ANO_ANT       = if (first(NIVEL) == "INDICADOR") NA_real_              else sum(VOL_ANO_ANT,        na.rm = TRUE),
        VOL_ANO_ANT2      = if (first(NIVEL) == "INDICADOR") NA_real_              else sum(VOL_ANO_ANT2,       na.rm = TRUE),
        VOL_MES_ATUAL     = if (first(NIVEL) == "INDICADOR") first(VOL_MES_ATUAL)  else sum(VOL_MES_ATUAL,      na.rm = TRUE),
        TEND              = if (first(NIVEL) %in% c("INDICADOR", "FATURAMENTO")) NA_real_ else sum(TEND, na.rm = TRUE),
        VENDA_HL    = ifelse(sum(VOL_HL_POND,  na.rm = TRUE) > 0,
                             round(sum(VALOR_HL_POND, na.rm = TRUE) / sum(VOL_HL_POND,  na.rm = TRUE), 2),
                             NA_real_),
        PERC_VOL_LN = ifelse(sum(VOL_LN_BACK,  na.rm = TRUE) > 0,
                             round(sum(VOL_SKU_LN,    na.rm = TRUE) / sum(VOL_LN_BACK,  na.rm = TRUE), 4),
                             NA_real_),
        PERC_COB_LN = if (first(NIVEL) == "SKU") {
          ifelse(sum(COB_LN_BACK, na.rm = TRUE) > 0,
                 round(sum(COB_SKU_LN, na.rm = TRUE) / sum(COB_LN_BACK, na.rm = TRUE), 4),
                 NA_real_)
        } else {
          if (is.na(PERC_VOL_LN)) NA_real_ else sum(VOL_MES_ATUAL, na.rm = TRUE) - PERC_VOL_LN
        },
        COB_MES_ANT       = if (all(is.na(COB_MES_ANT)))  NA_real_ else sum(COB_MES_ANT,  na.rm = TRUE),
        COB_ANO_ANT       = if (all(is.na(COB_ANO_ANT)))  NA_real_ else sum(COB_ANO_ANT,  na.rm = TRUE),
        COB_MES_ATUAL     = if (all(is.na(COB_MES_ATUAL))) NA_real_ else sum(COB_MES_ATUAL, na.rm = TRUE),
        FAT               = if (first(NIVEL) %in% c("INDICADOR", "FATURAMENTO")) NA_real_ else sum(FAT, na.rm = TRUE),
        .groups           = "drop"
      ) %>%
      mutate(PERC_TEND = ifelse(META_REV > 0, TEND / META_REV, NA_real_)) %>%
      select(REVENDA, NIVEL, CATEGORIA,
             VOL_ANO_RETRASADO, VOL_MES_2, VOL_MES_ANT, META_FAB, META_REV,
             VOL_ANO_ANT, VOL_ANO_ANT2, VOL_MES_ATUAL, TEND, PERC_TEND,
             VENDA_HL, PERC_VOL_LN, PERC_COB_LN,
             COB_MES_ANT, COB_ANO_ANT, COB_MES_ATUAL, FAT)
  }
  
  tabela_final = tabela_final %>%
    mutate(
      CATEGORIA = recode(
        CATEGORIA,
        
        "VOLUME TOTAL" = "VOLUME TOTAL",
        "MARÉ" = "MARÉ",
        "CORAL" = "CORAL",
        "JANGADA" = "JANGADA",
        "FAROL" = "FAROL",
        
        "MAR LN 250ML" = "MAR LN 250ML",
        "SERENA LN 330ML" = "SERENA LN 330ML",
        "CORAL LN 275ML" = "CORAL LN 275ML",
        
        "SKU/PDV ABP"     = "SKU/PDV ABP",
        "SKU/PDV REVENDA" = "SKU/PDV REVENDA",
        
        "PERC_CORAL_MAR_600" = "CORAL 600/MAR 600",
        "PERC_MARE_600_RGB" = "MAR 600/RGB TT",
        "PERC_MARE_0_TT" = "MAR 0.0%/MAR TT",
        
        "OW" = "FATURAMENTO OW",
        "RGB" = "FATURAMENTO RGB",

        "DOCES" = "DOCES",
        "SNACKS" = "SNACKS",

        "IMPULSE" = "FATURAMENTO IMPULSE",
        "TAKE HOME" = "FATURAMENTO TAKE HOME"
      )
    )
  
  tabela_final = tabela_final %>%
    mutate(CATEGORIA = factor(CATEGORIA, levels = ordem_categ_dv())) %>%
    filter(!is.na(CATEGORIA)) %>%
    filter(!as.character(CATEGORIA) %in% excluir_categorias_dv(revenda))

  if (revenda %in% c("Filial F", "Filial D")) {
    tabela_final <- tabela_final %>%
      mutate(
        PERC_VOL_LN = ifelse(as.character(NIVEL) %in% c("MARCA", "SEGMENTO", "SEGMENTO_2", "SEGMENTO_3", "TOTAL"), 0, PERC_VOL_LN),
        PERC_COB_LN = ifelse(as.character(NIVEL) %in% c("MARCA", "SEGMENTO", "SEGMENTO_2", "SEGMENTO_3", "TOTAL"), 0, PERC_COB_LN)
      )
  }

  tabela_final
}


# Aba Diario de Vendas - Familia ---------------------------------------

familia_dv = function(revenda, mes, ven = NULL, ga = NULL, rev = NULL, agrupamento_nulo = FALSE, canal = NULL){
  revenda <- if (!is.null(REVENDA_NOME_BD[[revenda]])) REVENDA_NOME_BD[[revenda]] else revenda

  if (is.null(canal) && revenda == "Especial") canal <- "IMPULSE"

  mes_1 = format(as.Date(paste0(mes, "01"), format = "%Y%m%d") %m-% months(1), format = "%Y%m")
  mes_2 = format(as.Date(paste0(mes, "01"), format = "%Y%m%d") %m-% months(2), format = "%Y%m")
  mes_3 = format(as.Date(paste0(mes, "01"), format = "%Y%m%d") %m-% months(3), format = "%Y%m")
  mes_11 = format(as.Date(paste0(mes, "01"), format = "%Y%m%d") %m-% months(11), format = "%Y%m")
  mes_12 = format(as.Date(paste0(mes, "01"), format = "%Y%m%d") %m-% months(12), format = "%Y%m")
  mes_24 = format(as.Date(paste0(mes, "01"), format = "%Y%m%d") %m-% months(24), format = "%Y%m")
  
  campo_aa_hl <- if (mes == format(Sys.Date(), "%Y%m")) "DV.QTD_TOTAL_HL_AA" else "DV.QTD_TOTAL_HL"
  campo_aa    <- if (mes == format(Sys.Date(), "%Y%m")) "DV.QTD_TOTAL_AA"    else "DV.QTD_TOTAL"
  
  filtro_agr <- if (agrupamento_nulo) "IS NULL" else "IS NOT NULL"
  
  prod_agr_select <- if (agrupamento_nulo) {
    "MAX(AGRUPAMENTO_VOLUME) AS AGRUPAMENTO_VOLUME"
  } else {
    glue("COALESCE(MAX(AGRUPAMENTO_VOLUME), CASE WHEN MAX(VOLUME_TOTAL) IS NULL AND SUM(CASE WHEN MES = '{mes}' THEN FATURAMENTO ELSE 0 END) > 0 THEN 'NOVO PRODUTO' END) AS AGRUPAMENTO_VOLUME")
  }
  filtro_agr_prod <- if (agrupamento_nulo) {
    "AND AGRUPAMENTO_VOLUME IS NULL AND VOLUME_TOTAL IS NOT NULL AND CODCOMP IS NOT NULL"
  } else {
    "AND ((AGRUPAMENTO_VOLUME IS NOT NULL AND CODCOMP IS NOT NULL) OR (VOLUME_TOTAL IS NULL AND AGRUPAMENTO_VOLUME IS NULL))"
  }
  prod_agr_having <- if (agrupamento_nulo) {
    ""
  } else {
    glue("HAVING MAX(AGRUPAMENTO_VOLUME) IS NOT NULL OR (MAX(VOLUME_TOTAL) IS NULL AND SUM(CASE WHEN MES = '{mes}' THEN FATURAMENTO ELSE 0 END) > 0)")
  }
  
  revs_efetivas      <- if (!is.null(revendas_por_grupo[[revenda]])) revendas_por_grupo[[revenda]] else revenda
  revs_sql           <- paste(paste0("'", revs_efetivas, "'"), collapse = ", ")
  filtro_revenda     <- paste0("REVENDA IN (", revs_sql, ")")
  filtro_revenda_ref <- paste0("REF.REVENDA IN (", revs_sql, ")")
  rev_exp_fam    <- if (!is.null(rev) && length(rev) > 0) unique(unlist(lapply(rev, function(r) if (!is.null(rev_aliases_dv[[r]])) rev_aliases_dv[[r]] else r))) else rev
  filtro_rev_sel <- if (!is.null(rev_exp_fam) && length(rev_exp_fam) > 0) paste0("AND REVENDA IN (", paste(paste0("'", gsub("'", "''", rev_exp_fam), "'"), collapse = ", "), ")") else ""
  filtro_ga      <- if (!is.null(ga)  && length(ga)  > 0) paste0("AND GA  IN (", paste(paste0("'", gsub("'", "''", ga),  "'"), collapse = ", "), ")") else ""
  filtro_ven     <- if (!is.null(ven) && length(ven) > 0) paste0("AND VEN IN (", paste(paste0("'", gsub("'", "''", ven), "'"), collapse = ", "), ")") else ""
  filtro_canal   <- if (!is.null(canal) && length(canal) > 0) paste0("AND CANAL = '", gsub("'", "''", canal), "'") else ""
  expr_rev    <- if (revenda == "GRUPO FILIAL") "CASE WHEN REVENDA IN ('Filial D') THEN 'Filial F' ELSE REVENDA END" else "REVENDA"
  expr_dv_rev <- if (revenda == "GRUPO FILIAL") "CASE WHEN DV.REVENDA IN ('Filial D') THEN 'Filial F' ELSE DV.REVENDA END" else "DV.REVENDA"

  query = glue("
    WITH DV_FILTRADO AS (
        SELECT * FROM TB_DIARIO_VENDA
        WHERE {filtro_revenda}
        {filtro_rev_sel}
        {filtro_ga}
        {filtro_ven}
        {filtro_canal}
    ),

    DV_COB_PROD AS (
        SELECT
            MES,
            {expr_rev} AS REVENDA,
            CODRED,
            SUM(COB_PROD) AS COB_PROD
        FROM TB_COB_PROD
        WHERE {filtro_revenda}
          AND MES IN ('{mes_12}', '{mes_1}', '{mes}')
          {filtro_rev_sel}
          {filtro_ga}
          {filtro_ven}
        GROUP BY MES, {expr_rev}, CODRED
    ),

    CMV_SKU AS (
        SELECT
            {expr_rev} AS REVENDA,
            CODR AS CODRED,
            SUM(PRECO) AS PRECO
        FROM TB_CMV
        WHERE {filtro_revenda}
        GROUP BY {expr_rev}, CODR
    ),

    META_FABRICA AS (
        SELECT
            {expr_rev} AS REVENDA,
            CODRED,
            SUM(VALOR)     AS VALOR,
            SUM(VALOR_UMB) AS VALOR_UMB
        FROM TB_META_FABRICA
        WHERE {filtro_revenda}
          AND MES = '{mes}'
        GROUP BY {expr_rev}, CODRED
    ),

    META_SKU AS (
        SELECT
            {expr_rev} AS REVENDA,
            MES,
            AGRUPAMENTO_VOLUME,
            CODRED,
            ROUND(SUM(QTD_META_REVENDA_UMB), 0) AS META_UMB,
            ROUND(SUM(QTD_META_REVENDA_HL),  0) AS META_HL
        FROM TB_META_REVENDA
        WHERE {filtro_revenda}
          AND MES = '{mes}'
          {filtro_ga}
          {filtro_ven}
        GROUP BY {expr_rev}, MES, AGRUPAMENTO_VOLUME, CODRED
    ),

    PROD_REF AS (
        SELECT
            {expr_rev} AS REVENDA,
            CODRED,
            {prod_agr_select},
            MAX(PRODUTO) AS PRODUTO
        FROM DV_FILTRADO
        WHERE {filtro_revenda}
          AND CODRED IS NOT NULL
          AND TRIM(CODRED) != ''
          {filtro_agr_prod}
        GROUP BY {expr_rev}, CODRED
        {prod_agr_having}
    ),

    DV_SKU AS (
        SELECT
            REF.REVENDA,
            REF.AGRUPAMENTO_VOLUME,
            REF.CODRED,
            CONCAT(REF.CODRED, ' - ', COALESCE(REF.PRODUTO, '')) AS PRODUTO,

            ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.QTD_TOTAL    ELSE 0 END), 0) AS VOL_ANO_RETRASADO_UMB,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_2}'  THEN DV.QTD_TOTAL    ELSE 0 END), 0) AS VOL_MES_2_UMB,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_1}'  THEN DV.QTD_TOTAL    ELSE 0 END), 0) AS VOL_MES_ANT_UMB,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}'    THEN MR.META_UMB ELSE 0 END), 0)     AS META_REV_UMB,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN DV.QTD_TOTAL    ELSE 0 END), 0) AS VOL_ANO_ANT_UMB,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN {campo_aa}      ELSE 0 END), 0) AS VOL_ANO_ANT2_UMB,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}'    THEN DV.QTD_TOTAL    ELSE 0 END), 0) AS VOL_MES_ATUAL_UMB,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}'    THEN DV.TEND_UMB     ELSE 0 END), 0) AS TEND_UMB,
            ROUND(
                ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_UMB ELSE 0 END), 0) /
                NULLIF(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_UMB ELSE 0 END), 0)
            , 4) AS PERC_TEND_UMB,

            ROUND(SUM(CASE WHEN DV.MES = '{mes_24}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_RETRASADO_HL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_2}'  THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_2_HL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_1}'  THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ANT_HL,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}'    THEN MR.META_HL  ELSE 0 END), 0)     AS META_REV_HL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_ANO_ANT_HL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes_12}' THEN {campo_aa_hl}   ELSE 0 END), 0) AS VOL_ANO_ANT2_HL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}'    THEN DV.QTD_TOTAL_HL ELSE 0 END), 0) AS VOL_MES_ATUAL_HL,
            ROUND(SUM(CASE WHEN DV.MES = '{mes}'    THEN DV.TEND_HL      ELSE 0 END), 0) AS TEND_HL,
            ROUND(
                ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.TEND_HL ELSE 0 END), 0) /
                NULLIF(MAX(CASE WHEN DV.MES = '{mes}' THEN MR.META_HL ELSE 0 END), 0)
            , 4) AS PERC_TEND_HL,

            ROUND(
                SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END) /
                NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL ELSE 0 END), 0)
            , 2) AS PRECO_MEDIO,
            ROUND(
                (
                    SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END) /
                    NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL ELSE 0 END), 0) /
                    NULLIF(MAX(CASE WHEN DV.MES = '{mes}' THEN CMV.PRECO END), 0)
                ) - 1
            , 4) AS PERC_MKP,
            ROUND(
                SUM(CASE WHEN DV.MES = '{mes}' THEN DV.VALOR_VENDA  ELSE 0 END) /
                NULLIF(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.QTD_TOTAL_HL ELSE 0 END), 0)
            , 2) AS VENDA_HL,

            ROUND(MAX(CASE WHEN DV.MES = '{mes_1}'  THEN CP.COB_PROD ELSE NULL END), 0) AS COB_MES_ANT,
            ROUND(MAX(CASE WHEN DV.MES = '{mes_12}' THEN CP.COB_PROD ELSE NULL END), 0) AS COB_ANO_ANT,
            ROUND(MAX(CASE WHEN DV.MES = '{mes}'    THEN CP.COB_PROD ELSE NULL END), 0) AS COB_MES_ATUAL,

            ROUND(COALESCE(MAX(MF.VALOR),     0), 0) AS META_FAB_HL,
            ROUND(COALESCE(MAX(MF.VALOR_UMB), 0), 0) AS META_FAB_UMB,

            ROUND(SUM(CASE WHEN DV.MES = '{mes}' THEN DV.FATURAMENTO ELSE 0 END), 2) AS FAT

        FROM PROD_REF REF
        LEFT JOIN DV_FILTRADO DV
            ON DV.CODRED  = REF.CODRED
           AND {expr_dv_rev} = REF.REVENDA
           AND DV.MES IN ('{mes_24}', '{mes_2}', '{mes_1}', '{mes_12}', '{mes}')
        LEFT JOIN DV_COB_PROD CP
            ON CP.MES     = DV.MES
           AND CP.REVENDA = {expr_dv_rev}
           AND CP.CODRED  = DV.CODRED
        LEFT JOIN META_SKU MR
            ON MR.MES     = DV.MES
           AND MR.REVENDA = {expr_dv_rev}
           AND MR.CODRED  = DV.CODRED
        LEFT JOIN CMV_SKU CMV
            ON CMV.REVENDA = {expr_dv_rev}
           AND CMV.CODRED  = DV.CODRED
        LEFT JOIN META_FABRICA MF
            ON MF.REVENDA = REF.REVENDA
           AND MF.CODRED  = REF.CODRED
        WHERE {filtro_revenda_ref}
        GROUP BY REF.REVENDA, REF.AGRUPAMENTO_VOLUME, REF.CODRED, REF.PRODUTO
    )

    SELECT * FROM DV_SKU
    ORDER BY AGRUPAMENTO_VOLUME, VOL_MES_ATUAL_UMB DESC
  ")
  
  tabela_familia <- fonte_parquet_dv2(query)
  
  if (length(revs_efetivas) > 1) {
    tabela_familia <- tabela_familia %>%
      mutate(
        VALOR_HL_POND = ifelse(!is.na(VENDA_HL) & VOL_MES_ATUAL_HL > 0,
                               VENDA_HL * VOL_MES_ATUAL_HL, NA_real_),
        VOL_HL_POND   = ifelse(!is.na(VENDA_HL) & VOL_MES_ATUAL_HL > 0,
                               VOL_MES_ATUAL_HL, NA_real_),
        FAT_CMV       = ifelse(!is.na(PERC_MKP) & (1 + PERC_MKP) > 0,
                               FAT / (1 + PERC_MKP), NA_real_)
      ) %>%
      group_by(AGRUPAMENTO_VOLUME, CODRED, PRODUTO) %>%
      summarise(
        REVENDA               = revenda,
        VOL_ANO_RETRASADO_UMB = sum(VOL_ANO_RETRASADO_UMB, na.rm = TRUE),
        VOL_MES_2_UMB         = sum(VOL_MES_2_UMB,         na.rm = TRUE),
        VOL_MES_ANT_UMB       = sum(VOL_MES_ANT_UMB,       na.rm = TRUE),
        META_FAB_HL           = sum(META_FAB_HL,             na.rm = TRUE),
        META_FAB_UMB          = sum(META_FAB_UMB,           na.rm = TRUE),
        META_REV_UMB          = sum(META_REV_UMB,           na.rm = TRUE),
        VOL_ANO_ANT_UMB       = sum(VOL_ANO_ANT_UMB,        na.rm = TRUE),
        VOL_ANO_ANT2_UMB      = sum(VOL_ANO_ANT2_UMB,       na.rm = TRUE),
        VOL_MES_ATUAL_UMB     = sum(VOL_MES_ATUAL_UMB,      na.rm = TRUE),
        TEND_UMB              = sum(TEND_UMB,               na.rm = TRUE),
        VOL_ANO_RETRASADO_HL  = sum(VOL_ANO_RETRASADO_HL,   na.rm = TRUE),
        VOL_MES_2_HL          = sum(VOL_MES_2_HL,           na.rm = TRUE),
        VOL_MES_ANT_HL        = sum(VOL_MES_ANT_HL,         na.rm = TRUE),
        META_REV_HL           = sum(META_REV_HL,            na.rm = TRUE),
        VOL_ANO_ANT_HL        = sum(VOL_ANO_ANT_HL,         na.rm = TRUE),
        VOL_ANO_ANT2_HL       = sum(VOL_ANO_ANT2_HL,        na.rm = TRUE),
        VOL_MES_ATUAL_HL      = sum(VOL_MES_ATUAL_HL,       na.rm = TRUE),
        TEND_HL               = sum(TEND_HL,                na.rm = TRUE),
        PRECO_MEDIO = ifelse(sum(VOL_MES_ATUAL_UMB, na.rm = TRUE) > 0,
                             round(sum(FAT, na.rm = TRUE) / sum(VOL_MES_ATUAL_UMB, na.rm = TRUE), 2),
                             NA_real_),
        PERC_MKP    = ifelse(sum(FAT_CMV, na.rm = TRUE) > 0,
                             round(sum(FAT, na.rm = TRUE) / sum(FAT_CMV, na.rm = TRUE) - 1, 4),
                             NA_real_),
        VENDA_HL    = ifelse(sum(VOL_HL_POND, na.rm = TRUE) > 0,
                             round(sum(VALOR_HL_POND, na.rm = TRUE) / sum(VOL_HL_POND, na.rm = TRUE), 2),
                             NA_real_),
        COB_MES_ANT   = if (all(is.na(COB_MES_ANT)))  NA_real_ else sum(COB_MES_ANT,  na.rm = TRUE),
        COB_ANO_ANT   = if (all(is.na(COB_ANO_ANT)))  NA_real_ else sum(COB_ANO_ANT,  na.rm = TRUE),
        COB_MES_ATUAL = if (all(is.na(COB_MES_ATUAL))) NA_real_ else sum(COB_MES_ATUAL, na.rm = TRUE),
        FAT                   = sum(FAT,                    na.rm = TRUE),
        .groups               = "drop"
      ) %>%
      mutate(
        PERC_TEND_UMB = ifelse(META_REV_UMB > 0, TEND_UMB / META_REV_UMB, NA_real_),
        PERC_TEND_HL  = ifelse(META_REV_HL  > 0, TEND_HL  / META_REV_HL,  NA_real_)
      ) %>%
      select(REVENDA, AGRUPAMENTO_VOLUME, CODRED, PRODUTO,
             VOL_ANO_RETRASADO_UMB, VOL_ANO_ANT_UMB, VOL_MES_2_UMB, VOL_MES_ANT_UMB,
             META_FAB_UMB, META_REV_UMB, VOL_ANO_ANT2_UMB, VOL_MES_ATUAL_UMB, TEND_UMB, PERC_TEND_UMB,
             VOL_ANO_RETRASADO_HL, VOL_ANO_ANT_HL, VOL_MES_2_HL, VOL_MES_ANT_HL,
             META_FAB_HL, META_REV_HL, VOL_ANO_ANT2_HL, VOL_MES_ATUAL_HL, TEND_HL, PERC_TEND_HL,
             PRECO_MEDIO, PERC_MKP, VENDA_HL,
             COB_MES_ANT, COB_ANO_ANT, COB_MES_ATUAL, FAT)
  }
  
  tabela_familia
}

outros_volumes_dv <- function(revenda, mes, ven = NULL, ga = NULL, rev = NULL) {

  if(revenda_query() == "ESPECIAL"){
    familia_dv(revenda = revenda, mes = mes, ven = ven, ga = ga, rev = rev, agrupamento_nulo = FALSE, canal = "TAKE HOME")
  } else{
    familia_dv(revenda = revenda, mes = mes, ven = ven, ga = ga, rev = rev, agrupamento_nulo = TRUE)
  }
  
}


# Meta ano atual -------------------------------------------------------------

meta_ano_dv <- function(revenda) {

  ano_at <- as.integer(format(Sys.Date(), "%Y"))
  ano_1  <- as.character(ano_at - 1)
  ano_2  <- as.character(ano_at - 2)
  ano_at <- as.character(ano_at)

  revs_efetivas  <- expandir_revendas_dv(revenda)
  filtro_revenda <- paste0("REVENDA IN (", paste(paste0("'", revs_efetivas, "'"), collapse = ", "), ")")

  volumes_mensais <- fonte_parquet_dv2(glue("
    SELECT LEFT(MES,4)  AS ANO,
           RIGHT(MES,2) AS MES_NUM,
           ROUND(SUM(QTD_TOTAL_HL),0) AS QTD,
           ROUND(SUM(TEND_HL),0)      AS TEND
    FROM TB_DIARIO_VENDA
    WHERE {filtro_revenda}
      AND LEFT(MES,4) IN ('{ano_2}','{ano_1}','{ano_at}')
    GROUP BY LEFT(MES,4), RIGHT(MES,2)
  "))

  if (is.null(volumes_mensais) || nrow(volumes_mensais) == 0) return(data.frame())

  meses_seq   <- sprintf("%02d", 1:12)
  nomes_meses <- c("Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez")

  valores_por_ano <- function(ano, coluna) {
    linhas <- volumes_mensais[volumes_mensais$ANO == ano, , drop = FALSE]
    vals   <- setNames(rep(0, 12), meses_seq)
    if (nrow(linhas) > 0) vals[linhas$MES_NUM] <- linhas[[coluna]]
    vals
  }

  vol_ano_2   <- valores_por_ano(ano_2, "QTD")
  vol_ano_1   <- valores_por_ano(ano_1, "QTD")
  tend_ano_at <- valores_por_ano(ano_at, "TEND")

  meta_min <- pmax(vol_ano_2, vol_ano_1)
  meta_at  <- meta_min + 2000
  dif      <- tend_ano_at - meta_at

  montar_linha <- function(rotulo, valores) {
    linha          <- setNames(as.list(as.numeric(valores)), nomes_meses)
    linha$HL_TOTAL <- rotulo
    linha$Total    <- sum(as.numeric(valores))
    as.data.frame(linha, stringsAsFactors = FALSE)[, c("HL_TOTAL", nomes_meses, "Total")]
  }

  rbind(
    montar_linha(ano_2,                    vol_ano_2),
    montar_linha(ano_1,                    vol_ano_1),
    montar_linha("Meta Minima Equipe",     meta_min),
    montar_linha("Incremento",             rep(2000, 12)),
    montar_linha(paste("Meta", ano_at),    meta_at),
    montar_linha(ano_at,                   tend_ano_at),
    montar_linha("Diferenca",              dif)
  )
}


# Meta ABP ano atual ---------------------------------------------------------

meta_abp_dv <- function(revenda, tipo = c("Cobertura", "Volume")) {

  tipo <- match.arg(tipo)

  ano_at        <- as.character(format(Sys.Date(), "%Y"))
  revs_efetivas <- expandir_revendas_dv(revenda)
  revs_sql      <- paste(paste0("'", revs_efetivas, "'"), collapse = ", ")
  revs_sql_up   <- paste(paste0("'", toupper(revs_efetivas), "'"), collapse = ", ")

  resultado <- tryCatch({
    con <- dbConnect(RMariaDB::MariaDB(),
                     dbname   = strsplit(argumentos_bd$dbname, ",")[[1]][8],
                     host     = argumentos_bd$host,
                     port     = as.numeric(argumentos_bd$port),
                     user     = argumentos_bd$user,
                     password = argumentos_bd$password,
                     charset  = "utf8mb4")
    on.exit(dbDisconnect(con), add = TRUE)
    if (identical(tipo, "Volume")) {
      dbGetQuery(con, glue("
        SELECT
            m.COD_SAP,
            m.CATEGORIA,
            m.MES_NUM,
            COALESCE(r.REAL_{ano_at}, 0)                             AS REAL_{ano_at},
            COALESCE(m.META_ABP,     0)                             AS META_ABP,
            COALESCE(r.REAL_{ano_at}, 0) - COALESCE(m.META_ABP, 0) AS DIFERENCA
        FROM (
            SELECT
                cod_sap                 AS COD_SAP,
                REVENDA,
                UPPER(TRIM(CATEGORIA))  AS CATEGORIA,
                RIGHT(CHAVE_MES_ANO, 2) AS MES_NUM,
                SUM(VOLUME)             AS META_ABP
            FROM tb_mar_metas_abp_vol
            WHERE LEFT(CHAVE_MES_ANO, 4) = '{ano_at}'
              AND REVENDA IN ({revs_sql})
              AND UPPER(TIPO_META) = 'MENSAL'
            GROUP BY cod_sap, REVENDA, UPPER(TRIM(CATEGORIA)), RIGHT(CHAVE_MES_ANO, 2)
        ) m
        LEFT JOIN (
            SELECT
                CASE
                  WHEN UPPER(TRIM(MARCA)) = 'IPÊ' THEN 'IPÊ - IPÊ'
                  ELSE UPPER(TRIM(MARCA))
                END AS CATEGORIA,
                RIGHT(MES, 2) AS MES_NUM,
                UPPER(REVENDA) AS REVENDA,
                CEILING(SUM(QTD_TOTAL_HL)) AS REAL_{ano_at}
            FROM TB_DIARIO_VENDA
            WHERE LEFT(MES, 4) = '{ano_at}'
              AND UPPER(REVENDA) IN ({revs_sql_up})
              AND UPPER(TRIM(MARCA)) IN (
                    'AGUA FAROL', 'CORAL', 'IPÊ', 'LUA AZUL',
                    'JANGADA', 'TUPÃ', 'BRISA', 'MARÉ',
                    'MANDACARU', 'SERENA', 'FAROL', 'CAJUÍNA'
                  )
            GROUP BY
                CASE
                  WHEN UPPER(TRIM(MARCA)) = 'IPÊ' THEN 'IPÊ - IPÊ'
                  ELSE UPPER(TRIM(MARCA))
                END,
                RIGHT(MES, 2),
                UPPER(REVENDA)
        ) r ON m.CATEGORIA COLLATE utf8mb4_unicode_ci = r.CATEGORIA
              AND m.MES_NUM = r.MES_NUM
              AND UPPER(m.REVENDA) COLLATE utf8mb4_unicode_ci = r.REVENDA
        ORDER BY m.CATEGORIA, m.COD_SAP, m.MES_NUM
      "))
    } else {
      dbGetQuery(con, glue("
      WITH PRODUTO_DIM AS (
          /* TB_COB_PROD possui apenas CODRED; o Diario e usado somente como
             dimensao para recuperar os atributos do produto. */
          SELECT
              UPPER(REVENDA) AS REVENDA,
              CODRED,
              MAX(MARCA)   AS MARCA,
              MAX(CANAL)   AS CANAL,
              MAX(PRODUTO) AS PRODUTO
          FROM TB_DIARIO_VENDA
          WHERE UPPER(REVENDA) IN ({revs_sql_up})
            AND CODRED IS NOT NULL
          GROUP BY UPPER(REVENDA), CODRED
      ),
      COBERTURA_PROD AS (
          /* Categorias de produto usam a cobertura por CODRED. */
          SELECT
              RIGHT(CP.MES, 2) AS MES_NUM,
              UPPER(CP.REVENDA) AS REVENDA,
              CP.CODRED,
              SUM(CP.COB_PROD) AS COB_PROD
          FROM TB_COB_PROD CP
          WHERE LEFT(CP.MES, 4) = '{ano_at}'
            AND UPPER(CP.REVENDA) IN ({revs_sql_up})
          GROUP BY RIGHT(CP.MES, 2), UPPER(CP.REVENDA), CP.CODRED
      ),
      COBERTURA_REV AS (
          /* COBERTURA TOTAL e calculada no nivel da revenda, sem somar SKUs. */
          SELECT
              RIGHT(CR.MES, 2) AS MES_NUM,
              UPPER(CR.REVENDA) AS REVENDA,
              SUM(CR.QTD_PDV) AS COB_TOTAL
          FROM TB_COB_REV CR
          WHERE LEFT(CR.MES, 4) = '{ano_at}'
            AND UPPER(CR.REVENDA) IN ({revs_sql_up})
          GROUP BY RIGHT(CR.MES, 2), UPPER(CR.REVENDA)
      )
      SELECT
          m.COD_SAP,
          m.CATEGORIA,
          m.MES_NUM,
          COALESCE(r.REAL_{ano_at}, 0)                             AS REAL_{ano_at},
          COALESCE(m.META_ABP,     0)                             AS META_ABP,
          COALESCE(r.REAL_{ano_at}, 0) - COALESCE(m.META_ABP, 0) AS DIFERENCA
      FROM (
          SELECT
              cod_sap                 AS COD_SAP,
              REVENDA,
              CATEGORIA,
              RIGHT(CHAVE_MES_ANO, 2) AS MES_NUM,
              SUM(COBERTURA)          AS META_ABP
          FROM tb_mar_metas_abp_cob
          WHERE LEFT(CHAVE_MES_ANO, 4) = '{ano_at}'
            AND REVENDA IN ({revs_sql})
            AND CATEGORIA IN (
                  'CORAL ULTRA', 'CORAL RETORNAVEL', 'CERV RGB + CHOPP',
                  'TUPÃ TOTAL', 'MARÉ RETORNAVEL', 'MARÉ TOTAL', 'COBERTURA TOTAL'
                )
            AND TIPO_META IN ('MENSAL')
          GROUP BY cod_sap, REVENDA, CATEGORIA, RIGHT(CHAVE_MES_ANO, 2)
      ) m
      LEFT JOIN (
          SELECT CATEGORIA, MES_NUM, REVENDA, CEILING(SUM(COB_PROD)) AS REAL_{ano_at}
          FROM (
              SELECT 'CORAL ULTRA' AS CATEGORIA, CP.MES_NUM, CP.REVENDA, CP.COB_PROD
              FROM COBERTURA_PROD CP
              WHERE CP.CODRED IN (904631, 904632, 905542)

              UNION ALL

              SELECT 'CORAL RETORNAVEL', CP.MES_NUM, CP.REVENDA, CP.COB_PROD
              FROM COBERTURA_PROD CP
              INNER JOIN PRODUTO_DIM P
                  ON P.REVENDA = CP.REVENDA AND P.CODRED = CP.CODRED
              WHERE P.MARCA = 'CORAL' AND P.PRODUTO LIKE '%RT%'

              UNION ALL

              SELECT 'CERV RGB + CHOPP', CP.MES_NUM, CP.REVENDA, CP.COB_PROD
              FROM COBERTURA_PROD CP
              INNER JOIN PRODUTO_DIM P
                  ON P.REVENDA = CP.REVENDA AND P.CODRED = CP.CODRED
              WHERE P.CANAL IN ('RGB', 'CHOPP')

              UNION ALL

              SELECT 'TUPÃ TOTAL', CP.MES_NUM, CP.REVENDA, CP.COB_PROD
              FROM COBERTURA_PROD CP
              INNER JOIN PRODUTO_DIM P
                  ON P.REVENDA = CP.REVENDA AND P.CODRED = CP.CODRED
              WHERE P.MARCA = 'TUPÃ'

              UNION ALL

              SELECT 'MARÉ RETORNAVEL', CP.MES_NUM, CP.REVENDA, CP.COB_PROD
              FROM COBERTURA_PROD CP
              INNER JOIN PRODUTO_DIM P
                  ON P.REVENDA = CP.REVENDA AND P.CODRED = CP.CODRED
              WHERE P.MARCA = 'MARÉ' AND P.PRODUTO LIKE '%RT%'

              UNION ALL

              SELECT 'MARÉ TOTAL', CP.MES_NUM, CP.REVENDA, CP.COB_PROD
              FROM COBERTURA_PROD CP
              INNER JOIN PRODUTO_DIM P
                  ON P.REVENDA = CP.REVENDA AND P.CODRED = CP.CODRED
              WHERE P.MARCA = 'MARÉ'

              UNION ALL

              SELECT 'COBERTURA TOTAL', CR.MES_NUM, CR.REVENDA, CR.COB_TOTAL
              FROM COBERTURA_REV CR

          ) sub
          GROUP BY CATEGORIA, MES_NUM, REVENDA
      ) r ON m.CATEGORIA = r.CATEGORIA AND m.MES_NUM = r.MES_NUM
            AND UPPER(m.REVENDA) = r.REVENDA
      ORDER BY CASE m.CATEGORIA
                 WHEN 'CORAL RETORNAVEL'   THEN 1
                 WHEN 'CORAL ULTRA'        THEN 2
                 WHEN 'CERV RGB + CHOPP'    THEN 3
                 WHEN 'TUPÃ TOTAL'           THEN 4
                 WHEN 'MARÉ RETORNAVEL' THEN 5
                 WHEN 'MARÉ TOTAL'      THEN 6
                 WHEN 'COBERTURA TOTAL'     THEN 7
                 ELSE 8
               END,
               m.COD_SAP,
               m.MES_NUM
      "))
    }
  }, error = function(e) NULL)
  
  if (is.null(resultado) || nrow(resultado) == 0) return(data.frame())

  meses_seq   <- sprintf("%02d", 1:12)
  nomes_meses <- c("Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez")
  col_real    <- paste0("REAL_", ano_at)

  categorias <- unique(resultado[, c("COD_SAP", "CATEGORIA")])

  linhas <- lapply(seq_len(nrow(categorias)), function(i) {
    cod <- categorias$COD_SAP[i]
    cat <- categorias$CATEGORIA[i]
    sub <- resultado[resultado$COD_SAP == cod & resultado$CATEGORIA == cat, ]

    preencher <- function(coluna) {
      vals <- setNames(rep(0, 12), meses_seq)
      vals[sub$MES_NUM] <- as.numeric(sub[[coluna]])
      vals
    }

    montar_linha <- function(rotulo, valores) {
      linha           <- setNames(as.list(as.numeric(valores)), nomes_meses)
      linha$COD_SAP   <- cod
      linha$CATEGORIA <- cat
      linha$HL_TOTAL  <- rotulo
      # Cobertura usa a media dos meses; volume conserva o total anual.
      linha$Total     <- if (identical(tipo, "Cobertura")) {
        mean(as.numeric(valores), na.rm = TRUE)
      } else {
        sum(as.numeric(valores), na.rm = TRUE)
      }
      as.data.frame(linha, stringsAsFactors = FALSE)[, c("COD_SAP", "CATEGORIA", "HL_TOTAL", nomes_meses, "Total")]
    }

    rbind(
      montar_linha(paste(if (identical(tipo, "Cobertura")) "Cob" else "Vol", ano_at), preencher(col_real)),
      montar_linha("Meta ABP",            preencher("META_ABP")),
      montar_linha(paste0("Diferença"), preencher("DIFERENCA"))
    )
  })

  tbl <- do.call(rbind, linhas)

  # Marca a primeira linha de cada novo COD_SAP dentro de cada CATEGORIA
  tbl <- tbl %>%
    group_by(CATEGORIA) %>%
    mutate(NOVO_COD_SAP = as.integer(COD_SAP != lag(COD_SAP, default = first(COD_SAP)))) %>%
    ungroup() %>%
    as.data.frame()

  tbl
}


# Historico de tendencia / cobertura para a tabela familia -------------------

source(glue("{diretorio}pages/Diario de venda/Dados/funcao_tooltip_tend_familia.R"), local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Diario de venda/Dados/funcao_tooltip_cob_familia.R"),  local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Diario de venda/Dados/funcao_tooltip_fat.R"),           local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Diario de venda/Dados/funcao_tooltip_indicador.R"),     local = TRUE, encoding = "UTF-8")


# Meses disponiveis no diario de vendas (para o filtro) -----------------------

meses_disponiveis_dv <- function(revenda) {
  
  revs_efetivas  <- expandir_revendas_dv(revenda)
  filtro_revenda <- paste0("REVENDA IN (", paste(paste0("'", revs_efetivas, "'"), collapse = ", "), ")")
  
  meses <- fonte_parquet_dv2(glue("
    SELECT DISTINCT MES
    FROM TB_DIARIO_VENDA
    WHERE {filtro_revenda}
    ORDER BY MES DESC
  "))$MES
  
  mes_atual <- format(Sys.Date(), "%Y%m")
  meses     <- sort(unique(c(as.character(meses), mes_atual)), decreasing = TRUE)
  
  nomes_meses <- c("Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez")
  
  rotulos <- sapply(meses, function(m) {
    data <- as.Date(paste0(m, "01"), format = "%Y%m%d")
    paste0(nomes_meses[as.integer(format(data, "%m"))], "/", format(data, "%Y"))
  })
  
  setNames(as.character(meses), rotulos)
}


# Filtros de GA e VEN disponiveis ---------------------------------------------

filtros_ga_ven_dv <- function(revenda) {
  
  revs_efetivas <- switch(revenda,
                          "NATAL"          = ,
                          "GRUPO NATAL"    = "Natal",
                          "ESPECIAL"         = "Especial",
                          "SÃO LUÍS"       = ,
                          "GRUPO SÃO LUÍS" = "São Luís",
                          "FORTALEZA"       = "Fortaleza",
                          "TERESINA"       = "Teresina",
                          "GRUPO FILIAL PI" = c("Teresina", "Fortaleza"),
                          "FILIAL A"   = "Filial A",
                          "FILIAL B"   = "Filial B",
                          "GRUPO FILIAL"     = c("Filial A", "Filial B"),
                          "FILIAL C"           = ,
                          "GRUPO FILIAL C"     = "Filial C",
                          "FILIAL F"     = "Filial F",
                          "FILIAL D"       = "Filial D",
                          "FILIAL E"      = "Filial E",
                          "GRUPO FILIAL"       = c("Filial F", "Filial D", "Filial E"),
                          revenda
  )
  
  filtro_revenda <- paste0("REVENDA IN (", paste(paste0("'", revs_efetivas, "'"), collapse = ", "), ")")
  
  resultado <- fonte_parquet_dv2(glue("
    SELECT DISTINCT GA, VEN
    FROM TB_DIARIO_VENDA
    WHERE {filtro_revenda}
      AND GA  IS NOT NULL
      AND VEN IS NOT NULL
    ORDER BY GA, VEN
  "))
  
  list(
    ga    = sort(unique(resultado$GA)),
    ven   = sort(unique(resultado$VEN)),
    pairs = resultado
  )
}


# Dias uteis do mes selecionado -----------------------------------------------

info_dias_uteis_dv <- function(revenda, mes) {
  
  revs_efetivas  <- expandir_revendas_dv(revenda)
  filtro_revenda <- paste0("REVENDA IN (", paste(paste0("'", revs_efetivas, "'"), collapse = ", "), ")")
  
  resultado <- fonte_parquet_dv2(glue("
    SELECT DIAS_UTEIS, DIAS_UTEIS_ATUAL
    FROM TB_DIARIO_VENDA
    WHERE {filtro_revenda}
      AND MES = '{mes}'
    LIMIT 1
  "))
  
  if (nrow(resultado) == 0) return(list(DIAS_UTEIS = "-", DIAS_UTEIS_ATUAL = "-"))
  as.list(resultado[1, ])
}

