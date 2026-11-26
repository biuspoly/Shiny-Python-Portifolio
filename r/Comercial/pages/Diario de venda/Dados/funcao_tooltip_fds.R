tooltip_hist_fds <- function(revenda, indicador, rev = NULL, ga = NULL, ven = NULL) {

  usa_revenda <- grepl("REVENDA", indicador, fixed = TRUE)

  filtro_ga  <- if (usa_revenda && !is.null(ga)  && length(ga)  > 0)
    paste0("AND GA  IN (", paste(paste0("'", gsub("'", "''", ga),  "'"), collapse = ", "), ")") else ""
  filtro_ven <- if (usa_revenda && !is.null(ven) && length(ven) > 0)
    paste0("AND VEN IN (", paste(paste0("'", gsub("'", "''", ven), "'"), collapse = ", "), ")") else ""

  revs_efetivas <- if (!is.null(rev) && length(rev) > 0) {
    unique(unlist(lapply(rev, expandir_revendas_dv)))
  } else if (!is.null(revendas_por_grupo[[revenda]])) {
    revendas_por_grupo[[revenda]]
  } else {
    revenda
  }
  revs_sql <- paste(paste0("'", gsub("'", "''", revs_efetivas), "'"), collapse = ", ")

  filtro_rev_sel <- if (!is.null(rev) && length(rev) > 0) {
    rev_exp <- unique(unlist(lapply(rev, expandir_revendas_dv)))
    paste0("AND REVENDA IN (", paste(paste0("'", gsub("'", "''", rev_exp), "'"), collapse = ", "), ")")
  } else ""

  filtro_rev_sel_f <- if (!is.null(rev) && length(rev) > 0) {
    rev_exp <- unique(unlist(lapply(rev, expandir_revendas_dv)))
    paste0("AND F.REVENDA IN (", paste(paste0("'", gsub("'", "''", rev_exp), "'"), collapse = ", "), ")")
  } else ""

  mes_expr_f <- "CASE RIGHT(F.MES, 2) WHEN '01' THEN 'Jan' WHEN '02' THEN 'Fev' WHEN '03' THEN 'Mar' WHEN '04' THEN 'Abr' WHEN '05' THEN 'Mai' WHEN '06' THEN 'Jun' WHEN '07' THEN 'Jul' WHEN '08' THEN 'Ago' WHEN '09' THEN 'Set' WHEN '10' THEN 'Out' WHEN '11' THEN 'Nov' WHEN '12' THEN 'Dez' END"
  mes_expr   <- "CASE RIGHT(MES, 2) WHEN '01' THEN 'Jan' WHEN '02' THEN 'Fev' WHEN '03' THEN 'Mar' WHEN '04' THEN 'Abr' WHEN '05' THEN 'Mai' WHEN '06' THEN 'Jun' WHEN '07' THEN 'Jul' WHEN '08' THEN 'Ago' WHEN '09' THEN 'Set' WHEN '10' THEN 'Out' WHEN '11' THEN 'Nov' WHEN '12' THEN 'Dez' END"

  if (usa_revenda) {

    consulta_sql <- glue("
      SELECT ANO, MES,
          ROUND(SUM(GRUPOS_META) / NULLIF(SUM(TOTAL_GRUPOS), 0) * 100, 2) AS TENDENCIA
      FROM (
          SELECT
              LEFT(MES, 4)  AS ANO,
              MES           AS MES_ORD,
              {mes_expr}    AS MES,
              GRUPOS_META,
              TOTAL_GRUPOS
          FROM TB_EXIG_FDS
          WHERE REVENDA IN ({revs_sql})
            {filtro_rev_sel}
            {filtro_ga}
            {filtro_ven}
      ) sub
      GROUP BY ANO, MES_ORD, MES
      HAVING TENDENCIA IS NOT NULL
      ORDER BY MES_ORD;
    ")

  } else {

    consulta_sql <- glue("
      SELECT ANO, MES,
          ROUND(SUM(GRUPOS_META) / NULLIF(MAX(META_FDS) * 100, 0) * 100, 2) AS TENDENCIA
      FROM (
          SELECT
              LEFT(F.MES, 4) AS ANO,
              F.MES          AS MES_ORD,
              {mes_expr_f}   AS MES,
              F.GRUPOS_META,
              M.META_FDS
          FROM TB_EXIG_FDS F
          JOIN (
              SELECT C.REVENDA, C.MES,
                  CASE WHEN A.VALOR IS NULL OR A.VALOR = 0 THEN C.QTD_PDV ELSE A.VALOR END AS META_FDS
              FROM TB_COB_REV C
              LEFT JOIN TB_META_ABP A ON A.REVENDA = C.REVENDA AND A.MES = C.MES
              WHERE C.REVENDA IN ({revs_sql})
          ) M ON M.REVENDA = F.REVENDA AND M.MES = F.MES
          WHERE F.REVENDA IN ({revs_sql})
            {filtro_rev_sel_f}
      ) sub
      GROUP BY ANO, MES_ORD, MES
      HAVING TENDENCIA IS NOT NULL
      ORDER BY MES_ORD;
    ")

  }

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
