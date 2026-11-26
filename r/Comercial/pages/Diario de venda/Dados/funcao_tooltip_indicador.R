tooltip_hist_indicador <- function(revenda, indicador, titulo = NULL, rev = NULL, ga = NULL, ven = NULL) {

  mapa <- switch(indicador,
    "PERC_CORAL_MAR_600"   = list(num = "CORAL 600ml",   den = "MARÉ 600ml"),
    "PERC_MARE_600_RGB" = list(num = "MARÉ 600ml", den = "RGB"),
    "PERC_MARE_0_TT"   = list(num = "0%",             den = "MARÉ"),
    "CORAL 600/MAR 600"   = list(num = "CORAL 600ml",   den = "MARÉ 600ml"),
    "MAR 600/RGB TT"       = list(num = "MARÉ 600ml", den = "RGB"),
    "MAR 0.0%/MAR TT"     = list(num = "0%",             den = "MARÉ"),
    NULL
  )

  if (is.null(mapa)) return(NULL)

  cat_num <- mapa$num
  cat_den <- mapa$den

  revs_efetivas <- if (!is.null(rev) && length(rev) > 0) {
    unique(unlist(lapply(rev, expandir_revendas_dv)))
  } else if (!is.null(revendas_por_grupo[[revenda]])) {
    revendas_por_grupo[[revenda]]
  } else {
    revenda
  }
  revs_sql <- paste(paste0("'", gsub("'", "''", revs_efetivas), "'"), collapse = ", ")

  filtro_ga  <- if (!is.null(ga)  && length(ga)  > 0) paste0("AND GA IN (", paste(paste0("'", gsub("'", "''", ga),  "'"), collapse = ", "), ")") else ""
  filtro_ven <- if (!is.null(ven) && length(ven) > 0) paste0("AND VEN IN (", paste(paste0("'", gsub("'", "''", ven), "'"), collapse = ", "), ")") else ""

  mes_expr <- "CASE RIGHT(CH.MES, 2) WHEN '01' THEN 'Jan' WHEN '02' THEN 'Fev' WHEN '03' THEN 'Mar' WHEN '04' THEN 'Abr' WHEN '05' THEN 'Mai' WHEN '06' THEN 'Jun' WHEN '07' THEN 'Jul' WHEN '08' THEN 'Ago' WHEN '09' THEN 'Set' WHEN '10' THEN 'Out' WHEN '11' THEN 'Nov' WHEN '12' THEN 'Dez' END"

  consulta_sql <- glue("
    SELECT ANO, MES, TENDENCIA
    FROM (
        SELECT
            LEFT(CH.MES, 4) AS ANO,
            CH.MES          AS MES_ORD,
            {mes_expr}      AS MES,
            ROUND(
                MAX(CASE WHEN CH.CATEGORIA = '{cat_num}' THEN CH.COB_CAT END) /
                NULLIF(MAX(CASE WHEN CH.CATEGORIA = '{cat_den}' THEN CH.COB_CAT END), 0) * 100
            , 2) AS TENDENCIA
        FROM (
            SELECT MES, CATEGORIA, SUM(COB_CAT) AS COB_CAT
            FROM TB_COB_CATEG
            WHERE REVENDA IN ({revs_sql})
              {filtro_ga}
              {filtro_ven}
              AND CATEGORIA IN ('{cat_num}', '{cat_den}')
            GROUP BY MES, CATEGORIA
        ) CH
        GROUP BY CH.MES
    ) sub
    WHERE TENDENCIA IS NOT NULL
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

  titulo_grafico   <- if (!is.null(titulo)) titulo else indicador
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
    e_title(titulo_grafico, left = "left") %>%
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
