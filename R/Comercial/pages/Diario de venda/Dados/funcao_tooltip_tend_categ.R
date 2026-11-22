tooltip_hist_tend <- function(revenda, marca, nivel, rev = NULL, cod = NULL, ga = NULL, ven = NULL) {

  col_map <- c(
    "TOTAL"      = "VOLUME_TOTAL",
    "MARCA"      = "MARCA",
    "SEGMENTO"   = "SEGMENTO",
    "SEGMENTO_2" = "SEGMENTO_2",
    "SEGMENTO_3" = "SEGMENTO_3",
    "SKU"        = "SKU_GRUPO"
  )

  col_categ <- unname(col_map[nivel])
  if (is.na(col_categ)) return(NULL)

  tend_field    <- if (nivel == "SKU") "DV.TEND_UMB"  else "DV.TEND_HL"
  qtd_field     <- if (nivel == "SKU") "DV.QTD_TOTAL" else "DV.QTD_TOTAL_HL"
  mes_atual_sql <- format(Sys.Date(), "%Y%m")

  revs_efetivas <- if (!is.null(rev) && length(rev) > 0) {
    unique(unlist(lapply(rev, expandir_revendas_dv)))
  } else if (!is.null(revendas_por_grupo[[revenda]])) {
    revendas_por_grupo[[revenda]]
  } else {
    expandir_revendas_dv(revenda)
  }
  revs_sql <- paste(paste0("'", gsub("'", "''", revs_efetivas), "'"), collapse = ", ")

  filtro_cod <- if (!is.null(cod) && length(cod) > 0) {
    paste0("AND DV.CODRED IN (", paste(paste0("'", gsub("'", "''", cod), "'"), collapse = ", "), ")")
  } else ""
  filtro_ga  <- if (!is.null(ga)  && length(ga)  > 0) paste0("AND DV.GA  IN (", paste(paste0("'", gsub("'", "''", ga),  "'"), collapse = ", "), ")") else ""
  filtro_ven <- if (!is.null(ven) && length(ven) > 0) paste0("AND DV.VEN IN (", paste(paste0("'", gsub("'", "''", ven), "'"), collapse = ", "), ")") else ""

  marca_safe <- gsub("'", "''", marca)
  mes_expr   <- "CASE RIGHT(DV.MES, 2) WHEN '01' THEN 'Jan' WHEN '02' THEN 'Fev' WHEN '03' THEN 'Mar' WHEN '04' THEN 'Abr' WHEN '05' THEN 'Mai' WHEN '06' THEN 'Jun' WHEN '07' THEN 'Jul' WHEN '08' THEN 'Ago' WHEN '09' THEN 'Set' WHEN '10' THEN 'Out' WHEN '11' THEN 'Nov' WHEN '12' THEN 'Dez' END"

  consulta_sql <- glue("
    SELECT
        LEFT(DV.MES, 4) AS ANO,
        DV.MES          AS MES_ORD,
        {mes_expr}      AS MES,
        ROUND(SUM(CASE WHEN DV.MES = '{mes_atual_sql}' THEN {tend_field} ELSE {qtd_field} END), 0) AS TENDENCIA
    FROM TB_DIARIO_VENDA DV
    WHERE DV.{col_categ} = '{marca_safe}'
      AND DV.REVENDA IN ({revs_sql})
      AND LEFT(DV.MES, 4) IS NOT NULL
      {filtro_cod}
      {filtro_ga}
      {filtro_ven}
    GROUP BY DV.MES, DV.{col_categ}
    ORDER BY DV.MES;
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

  if (is.null(dados_brutos) || nrow(dados_brutos) == 0) {
    message("[tooltip_tend_categ] sem dados: ", nivel, "/", marca, " rev=", revenda)
    return(NULL)
  }

  names(dados_brutos) <- toupper(names(dados_brutos))

  if (!all(c("ANO", "MES", "TENDENCIA") %in% names(dados_brutos))) {
    message("[tooltip_tend_categ COLS] cols inesperados: ", paste(names(dados_brutos), collapse = ", "))
    return(NULL)
  }

  niveis_dos_meses <- c("Jan","Fev","Mar","Abr","Mai","Jun",
                        "Jul","Ago","Set","Out","Nov","Dez")

  dados_brutos$MES <- factor(dados_brutos$MES, levels = niveis_dos_meses)

  dados_organizados <- dados_brutos %>%
    select(ANO, MES, TENDENCIA) %>%
    pivot_wider(names_from = ANO, values_from = TENDENCIA, values_fn = sum) %>%
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
    e_title(marca, left = "left") %>%
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
