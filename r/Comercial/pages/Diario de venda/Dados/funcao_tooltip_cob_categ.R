tooltip_hist_cob <- function(revenda, categoria, rev = NULL, ga = NULL, ven = NULL) {

  revs_efetivas <- if (!is.null(rev) && length(rev) > 0) rev else if (!is.null(revendas_por_grupo[[revenda]])) revendas_por_grupo[[revenda]] else expandir_revendas_dv(revenda)
  revs_sql      <- paste(paste0("'", gsub("'", "''", revs_efetivas), "'"), collapse = ", ")

  filtro_ga  <- if (!is.null(ga)  && length(ga)  > 0) paste0("AND CP.GA  IN (", paste(paste0("'", gsub("'", "''", ga),  "'"), collapse = ", "), ")") else ""
  filtro_ven <- if (!is.null(ven) && length(ven) > 0) paste0("AND CP.VEN IN (", paste(paste0("'", gsub("'", "''", ven), "'"), collapse = ", "), ")") else ""

  categoria_safe <- gsub("'", "''", categoria)
  mes_expr       <- "CASE RIGHT(CP.MES, 2) WHEN '01' THEN 'Jan' WHEN '02' THEN 'Fev' WHEN '03' THEN 'Mar' WHEN '04' THEN 'Abr' WHEN '05' THEN 'Mai' WHEN '06' THEN 'Jun' WHEN '07' THEN 'Jul' WHEN '08' THEN 'Ago' WHEN '09' THEN 'Set' WHEN '10' THEN 'Out' WHEN '11' THEN 'Nov' WHEN '12' THEN 'Dez' END"

  consulta_sql <- glue("
    SELECT ANO, MES, SUM(COBERTURA) AS COBERTURA
    FROM (
        SELECT
            LEFT(CP.MES, 4) AS ANO,
            CP.MES          AS MES_ORD,
            {mes_expr}      AS MES,
            ROUND(SUM(CP.COB_CAT), 0) AS COBERTURA
        FROM TB_COB_CATEG CP
        WHERE CP.CATEGORIA = '{categoria_safe}'
          AND CP.REVENDA   IN ({revs_sql})
          {filtro_ga}
          {filtro_ven}
        GROUP BY CP.MES, CP.REVENDA
    ) sub
    GROUP BY ANO, MES_ORD, MES
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
    select(ANO, MES, COBERTURA) %>%
    pivot_wider(names_from = ANO, values_from = COBERTURA) %>%
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
    e_title(categoria, left = "left") %>%
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
