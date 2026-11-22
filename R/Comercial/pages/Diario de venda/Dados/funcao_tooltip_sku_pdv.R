tooltip_hist_sku_pdv <- function(revenda, indicador, rev = NULL, ga = NULL, ven = NULL) {

  usa_abp <- !grepl("REVENDA", indicador, fixed = TRUE)

  filtro_ga  <- if (!usa_abp && !is.null(ga)  && length(ga)  > 0)
    paste0("AND GA  IN (", paste(paste0("'", gsub("'", "''", ga),  "'"), collapse = ", "), ")") else ""
  filtro_ven <- if (!usa_abp && !is.null(ven) && length(ven) > 0)
    paste0("AND VEN IN (", paste(paste0("'", gsub("'", "''", ven), "'"), collapse = ", "), ")") else ""

  revs_efetivas <- if (!is.null(rev) && length(rev) > 0) {
    unique(unlist(lapply(rev, expandir_revendas_dv)))
  } else if (!is.null(revendas_por_grupo[[revenda]])) {
    revendas_por_grupo[[revenda]]
  } else {
    revenda
  }
  revs_sql       <- paste(paste0("'", gsub("'", "''", revs_efetivas), "'"), collapse = ", ")
  revs_sql_upper <- paste(paste0("'", toupper(gsub("'", "''", revs_efetivas)), "'"), collapse = ", ")

  den_col <- if (usa_abp) "MA_SKU.VALOR" else "MR_SKU.META_REVENDA"

  mes_expr <- "CASE RIGHT(Q.MES, 2) WHEN '01' THEN 'Jan' WHEN '02' THEN 'Fev' WHEN '03' THEN 'Mar' WHEN '04' THEN 'Abr' WHEN '05' THEN 'Mai' WHEN '06' THEN 'Jun' WHEN '07' THEN 'Jul' WHEN '08' THEN 'Ago' WHEN '09' THEN 'Set' WHEN '10' THEN 'Out' WHEN '11' THEN 'Nov' WHEN '12' THEN 'Dez' END"

  consulta_sql <- glue("
    SELECT ANO, MES,
        ROUND(SUM(QTD_SKU_PDV) / NULLIF(SUM(META_DEN), 0), 2) AS TENDENCIA
    FROM (
        SELECT
            LEFT(Q.MES, 4) AS ANO,
            Q.MES          AS MES_ORD,
            {mes_expr}     AS MES,
            Q.QTD_SKU_PDV,
            COALESCE({den_col}, 0) AS META_DEN
        FROM (
            SELECT REVENDA, MES, SUM(QTD_SKU_PDV) AS QTD_SKU_PDV
            FROM TB_COB_CLI
            WHERE REVENDA IN ({revs_sql})
              {filtro_ga}
              {filtro_ven}
            GROUP BY REVENDA, MES
        ) Q
        LEFT JOIN (
            SELECT REVENDA, MES, SUM(VALOR) AS VALOR
            FROM TB_META_ABP
            WHERE UPPER(REVENDA) IN ({revs_sql_upper})
            GROUP BY REVENDA, MES
        ) MA_SKU ON MA_SKU.REVENDA = Q.REVENDA AND MA_SKU.MES = Q.MES
        LEFT JOIN (
            SELECT REVENDA, MES, SUM(QTD_META_REVENDA_HL) AS META_REVENDA
            FROM TB_META_REVENDA
            WHERE REVENDA IN ({revs_sql})
              {filtro_ga}
              {filtro_ven}
            GROUP BY REVENDA, MES
        ) MR_SKU ON MR_SKU.REVENDA = Q.REVENDA AND MR_SKU.MES = Q.MES
    ) sub
    GROUP BY ANO, MES_ORD, MES
    HAVING TENDENCIA IS NOT NULL
    ORDER BY MES_ORD;
  ")

  dados_brutos <- tryCatch(fonte_parquet_dv2(consulta_sql), error = function(e) NULL)

  if (is.null(dados_brutos) || nrow(dados_brutos) == 0) {
    conexao <- tryCatch(
      dbConnect(RMariaDB::MariaDB(),
                dbname   = strsplit(argumentos_bd$dbname, ",")[[1]][8],
                host     = argumentos_bd$host,
                port     = as.numeric(argumentos_bd$port),
                user     = argumentos_bd$user,
                password = argumentos_bd$password,
                charset  = "utf8mb4"),
      error = function(e) NULL
    )
    if (is.null(conexao)) return(NULL)
    on.exit(dbDisconnect(conexao), add = TRUE)
    dados_brutos <- tryCatch(dbGetQuery(conexao, consulta_sql), error = function(e) NULL)
  }

  if (is.null(dados_brutos) || nrow(dados_brutos) == 0) return(NULL)

  niveis_dos_meses <- c("Jan","Fev","Mar","Abr","Mai","Jun",
                        "Jul","Ago","Set","Out","Nov","Dez")

  dados_brutos$MES <- factor(dados_brutos$MES, levels = niveis_dos_meses)

  dados_organizados <- dados_brutos %>%
    select(ANO, MES, TENDENCIA) %>%
    pivot_wider(names_from = ANO, values_from = TENDENCIA) %>%
    arrange(MES)

  lista_de_anos <- unique(dados_brutos$ANO)

  grafico_resultado <- dados_organizados %>% e_charts(MES)

  for (ano_especifico in lista_de_anos) {
    grafico_resultado <- grafico_resultado %>%
      e_line_(as.character(ano_especifico), name = as.character(ano_especifico))
  }

  grafico_resultado <- grafico_resultado %>%
    e_labels(show = TRUE, position = "top") %>%
    e_color(unname(sapply(as.character(lista_de_anos), cor_ano))) %>%
    e_title(indicador, left = "left") %>%
    e_x_axis(axisLabel = list(interval = 0)) %>%
    e_y_axis(
      show      = TRUE,
      scale     = TRUE,
      axisLabel = list(show = FALSE),
      axisTick  = list(show = FALSE),
      axisLine  = list(show = FALSE),
      splitLine = list(show = FALSE)
    )

  lista_elementos_visuais <- list()
  alturas_dos_textos <- seq(70, 30, length.out = length(lista_de_anos))

  for (posicao in seq_along(lista_de_anos)) {
    lista_elementos_visuais[[posicao]] <- list(
      type  = "text",
      left  = 10,
      top   = paste0(round(alturas_dos_textos[posicao]), "%"),
      style = list(
        text = as.character(lista_de_anos[posicao]),
        fill = cor_ano(lista_de_anos[posicao]),
        font = "bold 12px sans-serif"
      )
    )
  }

  grafico_resultado <- grafico_resultado %>%
    e_graphic_g(elements = lista_elementos_visuais) %>%
    e_legend(bottom = 0) %>%
    e_grid(left = "80", right = "5%", bottom = "15%")

  list(tabela = dados_brutos, grafico = grafico_resultado)
}
