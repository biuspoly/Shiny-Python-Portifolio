# Markup por produto (versão enxuta, escrita para o portfólio: a tela de markup não existia na versão
# original em R). Mesmas contas da versão em Python, sobre o mesmo cache fictício (tb_markup):
#   markup real     = faturamento / CMV - 1
#   markup sugerido = faturamento sugerido / CMV - 1  (o mesmo CMV, para os dois serem comparáveis)
#   saldo           = faturamento - faturamento sugerido (negativo: vendeu abaixo do sugerido)

pag_markup <- function() {

  source(glue("{diretorio}pages/Diario de venda/Dados/funcoes_cores.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Diario de venda/Dados/funcoes_meses.R"), local = TRUE, encoding = "UTF-8")

  # DADOS ----------------------------------------------------------------------

  markup <- as.data.frame(nanoparquet::read_parquet(glue("{diretorio}data/bd_comercial/tb_markup.parquet")))
  meses_mkp <- sort(unique(markup$MES), decreasing = TRUE)
  rotulos_mes <- setNames(meses_mkp, label_mes(as.Date(paste0(meses_mkp, "01"), format = "%Y%m%d")))

  fmt <- function(x, casas = 0) {
    ifelse(is.na(x), "", trimws(format(round(x, casas), nsmall = casas, big.mark = ".", decimal.mark = ",", scientific = FALSE)))
  }
  pct <- function(x, casas = 1) ifelse(is.na(x), "", paste0(fmt(x * 100, casas), "%"))

  recorte_mkp <- reactive({
    req(input$mes_mkp)
    df <- markup[markup$MES == input$mes_mkp, ]
    if (length(input$marca_mkp)) df <- df[df$MARCA %in% input$marca_mkp, ]
    df
  })

  observeEvent(input$limpar_mkp, {
    updatePickerInput(session, "mes_mkp", selected = meses_mkp[1])
    updatePickerInput(session, "marca_mkp", selected = character(0))
  })

  # CARTÕES --------------------------------------------------------------------

  output$cartoes_mkp <- renderUI({
    df <- recorte_mkp()
    req(nrow(df) > 0)
    fat <- sum(df$FAT); cmv <- sum(df$CMV); sug <- sum(df$FAT_SUG)
    pct_real <- fat / cmv - 1; pct_sug <- sug / cmv - 1; saldo <- fat - sug
    cartao <- function(titulo, valor, sub, classe = "kpi-delta-neutro", destaque = FALSE) {
      div(class = if (destaque) "dv-kpi dv-kpi-destaque" else "dv-kpi",
          div(class = "dv-kpi-titulo", titulo),
          div(class = "dv-kpi-valor", valor),
          span(class = paste("kpi-delta", classe), sub))
    }
    div(class = "dv-kpis",
      cartao("Faturamento", paste("R$", fmt(fat)), paste(fmt(sum(df$QTD)), "caixas")),
      cartao("CMV", paste("R$", fmt(cmv)), "custo do que foi vendido"),
      cartao("Markup real", pct(pct_real), paste0("R$ ", fmt(fat - cmv), " sobre o CMV"),
             if (pct_real < pct_sug) "kpi-delta-neg" else "kpi-delta-pos", destaque = TRUE),
      cartao("Markup sugerido", pct(pct_sug), paste("faturaria R$", fmt(sug))),
      cartao("Saldo do markup", paste("R$", fmt(saldo)),
             if (saldo < 0) "abaixo do sugerido" else "acima do sugerido",
             if (saldo < 0) "kpi-delta-neg" else "kpi-delta-pos")
    )
  })

  # TABELA ---------------------------------------------------------------------

  output$tabela_mkp <- renderReactable({
    df <- recorte_mkp()
    req(nrow(df) > 0)
    prod <- df %>%
      group_by(PRODUTO, MARCA) %>%
      summarise(across(c(QTD, FAT, CMV, FAT_SUG), sum), .groups = "drop") %>%
      mutate(
        PESO       = FAT / sum(FAT),
        PRECO_REAL = FAT / QTD,
        PRECO_SUG  = FAT_SUG / QTD,
        PCT_MKP    = FAT / CMV - 1,
        PCT_SUG    = FAT_SUG / CMV - 1,
        SALDO      = FAT - FAT_SUG
      ) %>%
      arrange(desc(FAT)) %>%
      select(PRODUTO, MARCA, QTD, FAT, PESO, CMV, PRECO_REAL, PRECO_SUG, PCT_MKP, PCT_SUG, SALDO)

    abaixo <- function(value, index) if (prod$SALDO[index] < 0) cor_meta() else NULL
    numero <- function(casas) colFormat(separators = TRUE, locales = "pt-BR", digits = casas)

    reactable(
      prod,
      theme         = tema_reactable_dv,
      defaultColDef = colDef(align = "right", minWidth = 80, headerStyle = cor_cabecalho_dv("FAT")),
      columns = list(
        PRODUTO    = colDef(name = "Produto", align = "left", minWidth = 220,
                            headerStyle = cor_cabecalho_dv("CATEGORIA", align = "left")),
        MARCA      = colDef(name = "Marca", align = "left", minWidth = 100,
                            headerStyle = cor_cabecalho_dv("CATEGORIA", align = "left")),
        QTD        = colDef(name = "Qtd. (cx)", format = numero(0)),
        FAT        = colDef(name = "Faturamento", format = numero(2), minWidth = 110),
        PESO       = colDef(name = "Peso no faturamento", format = colFormat(percent = TRUE, digits = 1)),
        CMV        = colDef(name = "CMV", format = numero(2), minWidth = 110),
        PRECO_REAL = colDef(name = "Preço real", format = numero(2)),
        PRECO_SUG  = colDef(name = "Preço sugerido", format = numero(2)),
        PCT_MKP    = colDef(name = "% Markup real", format = colFormat(percent = TRUE, digits = 1),
                            style = abaixo, headerStyle = cor_cabecalho_dv("TEND"), class = "dv-col-chave"),
        PCT_SUG    = colDef(name = "% Markup sugerido", format = colFormat(percent = TRUE, digits = 1)),
        SALDO      = colDef(name = "Saldo (real - sugerido)", format = numero(2), minWidth = 120,
                            style = abaixo, headerStyle = cor_cabecalho_dv("TEND"), class = "dv-col-chave")
      ),
      highlight  = TRUE,
      compact    = TRUE,
      fullWidth  = TRUE,
      wrap       = FALSE,
      pagination = FALSE,
      height     = "560px"
    )
  })

  # UI -------------------------------------------------------------------------

  fluidPage(
    fluidRow(
      box(
        width = 12, status = "primary", collapsible = FALSE,
        title = fluidRow(
          column(2, pickerInput("mes_mkp", "Mês", choices = rotulos_mes, selected = meses_mkp[1],
                                options = pickerOptions(container = "body"))),
          column(3, pickerInput("marca_mkp", "Marca", choices = sort(unique(markup$MARCA)), multiple = TRUE,
                                options = pickerOptions(container = "body", noneSelectedText = "Todas",
                                                        actionsBox = TRUE, liveSearch = TRUE))),
          column(1, offset = 6, style = "display: flex; align-items: center;",
                 actionButton("limpar_mkp", label = NULL, icon = icon("eraser"), status = "primary", width = "100%") %>%
                   tagAppendAttributes(title = "Limpar filtros"))
        )
      ),
      column(12, uiOutput("cartoes_mkp")),
      box(
        width = 12, collapsible = FALSE, title = "Markup por produto",
        withSpinner(reactableOutput("tabela_mkp"), type = 4, color = cores_reativo()[2]),
        div(class = "dv-legenda",
            span(class = "dv-legenda-alerta"), "vendeu abaixo do markup sugerido",
            span(class = "dv-legenda-chave"), "colunas principais",
            span(class = "dv-legenda-dica", "markup = faturamento ÷ CMV − 1; o sugerido usa o mesmo CMV"))
      )
    )
  )
}
