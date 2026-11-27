# Clientes: a carteira, uma linha por cliente (versão enxuta, escrita para o portfólio: a tela não existia
# na versão original em R). Mesmas contas da versão em Python, sobre o mesmo cache fictício (tb_carteira).
# O resto do Comercial conta por produto; aqui a pergunta é a oposta: o que a revenda tem com cada cliente.

pag_clientes <- function() {

  source(glue("{diretorio}pages/Diario de venda/Dados/funcoes_cores.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Diario de venda/Dados/funcoes_meses.R"), local = TRUE, encoding = "UTF-8")

  # DADOS ----------------------------------------------------------------------

  carteira <- as.data.frame(nanoparquet::read_parquet(glue("{diretorio}data/bd_comercial/tb_carteira.parquet")))
  carteira$ULTIMA_COMPRA <- as.Date(carteira$ULTIMA_COMPRA)
  dias_parado    <- 90
  limiar_dev     <- 0.05  # devolução acima de 5% do faturamento fica em vermelho
  limite_parado  <- Sys.Date() - dias_parado
  rot_mes        <- label_mes(Sys.Date())
  situacoes <- c(
    "Todos"                                   = "todos",
    "Só ativos"                               = "ativos",
    "Compraram no mês"                        = "compraram_mes",
    "Ativos sem comprar no mês"               = "ativos_sem_mes",
    "Ativos parados há 90+ dias"              = "parados"
  )

  fmt <- function(x, casas = 0) {
    ifelse(is.na(x), "", trimws(format(round(x, casas), nsmall = casas, big.mark = ".", decimal.mark = ",", scientific = FALSE)))
  }
  pct <- function(x, casas = 1) ifelse(is.na(x) | is.infinite(x), "", paste0(fmt(x * 100, casas), "%"))
  parado <- function(df) df$ATIVO & !is.na(df$ULTIMA_COMPRA) & df$ULTIMA_COMPRA < limite_parado

  recorte_cli <- reactive({
    df <- carteira
    if (length(input$ven_cli))    df <- df[df$VEN %in% input$ven_cli, ]
    if (length(input$canal_cli))  df <- df[df$CANAL %in% input$canal_cli, ]
    if (length(input$cidade_cli)) df <- df[df$CIDADE %in% input$cidade_cli, ]
    df <- switch(input$situacao_cli %||% "todos",
      ativos         = df[df$ATIVO, ],
      compraram_mes  = df[df$FAT_MES > 0, ],
      ativos_sem_mes = df[df$ATIVO & df$FAT_MES == 0, ],
      parados        = df[parado(df), ],
      df
    )
    busca <- toupper(trimws(input$busca_cli %||% ""))
    if (nzchar(busca)) df <- df[grepl(busca, toupper(paste(df$CODCLI, "-", df$CLIENTE)), fixed = TRUE), ]
    df
  })

  observeEvent(input$limpar_cli, {
    for (campo in c("ven_cli", "canal_cli", "cidade_cli")) updatePickerInput(session, campo, selected = character(0))
    updateSelectInput(session, "situacao_cli", selected = "todos")
    updateTextInput(session, "busca_cli", value = "")
  })

  # CARTÕES --------------------------------------------------------------------

  output$cartoes_cli <- renderUI({
    df <- recorte_cli()
    cartao <- function(titulo, valor, sub, classe = "kpi-delta-neutro", destaque = FALSE) {
      div(class = if (destaque) "dv-kpi dv-kpi-destaque" else "dv-kpi",
          div(class = "dv-kpi-titulo", titulo),
          div(class = "dv-kpi-valor", valor),
          span(class = paste("kpi-delta", classe), sub))
    }
    ativos   <- sum(df$ATIVO)
    parados  <- sum(parado(df))
    pct_dev  <- sum(df$DEV_MES) / (sum(df$FAT_MES) + sum(df$DEV_MES))
    div(class = "dv-kpis",
      cartao("Clientes", fmt(nrow(df)), paste(fmt(ativos), "ativos")),
      cartao(paste("Faturamento", rot_mes), paste("R$", fmt(sum(df$FAT_MES))),
             paste(fmt(sum(df$FAT_MES > 0)), "clientes compraram"), destaque = TRUE),
      cartao("Faturamento 12 meses", paste("R$", fmt(sum(df$FAT_12M))), paste(fmt(sum(df$FAT_12M > 0)), "compraram")),
      cartao(paste("Devolução", rot_mes), paste("R$", fmt(sum(df$DEV_MES))),
             paste(pct(pct_dev, 2), "da venda bruta do mês"),
             if (isTRUE(pct_dev > limiar_dev)) "kpi-delta-neg" else "kpi-delta-neutro"),
      cartao("Markup 12 meses", pct(sum(df$FAT_12M) / sum(df$CMV_12M) - 1),
             paste("R$", fmt(sum(df$FAT_12M) - sum(df$CMV_12M)))),
      cartao(paste0("Ativos parados ", dias_parado, "+ dias"), fmt(parados),
             paste(pct(if (ativos) parados / ativos else NA), "dos ativos"),
             if (parados > 0) "kpi-delta-neg" else "kpi-delta-neutro")
    )
  })

  # TABELA ---------------------------------------------------------------------

  output$titulo_cli <- renderText(paste0("Carteira de clientes (", fmt(nrow(recorte_cli())), ")"))

  output$tabela_cli <- renderReactable({
    df <- recorte_cli() %>%
      mutate(PCT_MKP = ifelse(CMV_12M > 0, FAT_12M / CMV_12M - 1, NA_real_)) %>%
      select(CODCLI, CLIENTE, VEN, CANAL, CIDADE, FAT_MES, DEV_MES, FAT_12M, DEV_12M, PCT_MKP,
             MESES_COMPRANDO, ULTIMA_COMPRA, ATIVO)
    vazio_zero <- function(value) if (is.na(value) || value == 0) "" else fmt(value, 2)
    devolucao_alta <- function(fat) {
      function(value, index) {
        f <- df[[fat]][index]
        if (!is.na(value) && value > 0 && value / (f + value) > limiar_dev) cor_meta() else NULL
      }
    }

    reactable(
      df,
      theme         = tema_reactable_dv,
      defaultColDef = colDef(align = "right", minWidth = 80, headerStyle = cor_cabecalho_dv("FAT")),
      columns = list(
        CODCLI  = colDef(name = "Código", align = "left", minWidth = 70, headerStyle = cor_cabecalho_dv("FAT", align = "left")),
        CLIENTE = colDef(name = "Cliente", align = "left", minWidth = 220, headerStyle = cor_cabecalho_dv("FAT", align = "left")),
        VEN     = colDef(name = "Vendedor", align = "center", minWidth = 75),
        CANAL   = colDef(name = "Canal", align = "center", minWidth = 100),
        CIDADE  = colDef(name = "Cidade", align = "left", minWidth = 150, headerStyle = cor_cabecalho_dv("FAT", align = "left")),
        FAT_MES = colDef(name = paste("Fat.", rot_mes), cell = vazio_zero, minWidth = 100,
                         headerStyle = cor_cabecalho_dv("TEND"), class = "dv-col-chave"),
        DEV_MES = colDef(name = paste("Devol.", rot_mes), cell = vazio_zero, style = devolucao_alta("FAT_MES")),
        FAT_12M = colDef(name = "Fat. 12 meses", cell = vazio_zero, minWidth = 110,
                         headerStyle = cor_cabecalho_dv("TEND"), class = "dv-col-chave"),
        DEV_12M = colDef(name = "Devol. 12 meses", cell = vazio_zero, style = devolucao_alta("FAT_12M")),
        PCT_MKP = colDef(name = "% Markup 12 meses", format = colFormat(percent = TRUE, digits = 1)),
        MESES_COMPRANDO = colDef(name = "Meses com compra (de 12)", align = "center"),
        ULTIMA_COMPRA = colDef(
          name = "Última compra", align = "center", format = colFormat(date = TRUE, locales = "pt-BR"),
          style = function(value, index) if (df$ATIVO[index] && !is.na(value) && value < limite_parado) cor_meta() else NULL
        ),
        ATIVO = colDef(show = FALSE)
      ),
      highlight       = TRUE,
      compact         = TRUE,
      fullWidth       = TRUE,
      wrap            = FALSE,
      pagination      = TRUE,
      defaultPageSize = 25
    )
  })

  # UI -------------------------------------------------------------------------

  multiplo <- pickerOptions(container = "body", noneSelectedText = "Todos", actionsBox = TRUE, liveSearch = TRUE)
  fluidPage(
    fluidRow(
      box(
        width = 12, status = "primary", collapsible = FALSE,
        title = fluidRow(
          column(2, pickerInput("ven_cli", "Vendedor", choices = sort(unique(carteira$VEN)), multiple = TRUE, options = multiplo)),
          column(2, pickerInput("canal_cli", "Canal", choices = sort(unique(carteira$CANAL)), multiple = TRUE, options = multiplo)),
          column(2, pickerInput("cidade_cli", "Cidade", choices = sort(unique(carteira$CIDADE)), multiple = TRUE, options = multiplo)),
          column(2, selectInput("situacao_cli", "Situação", choices = situacoes, selected = "todos")),
          column(3, textInput("busca_cli", "Cliente", placeholder = "código ou nome")),
          column(1, style = "display: flex; align-items: center;",
                 actionButton("limpar_cli", label = NULL, icon = icon("eraser"), status = "primary", width = "100%") %>%
                   tagAppendAttributes(title = "Limpar filtros"))
        )
      ),
      column(12, uiOutput("cartoes_cli")),
      box(
        width = 12, collapsible = FALSE, title = textOutput("titulo_cli", inline = TRUE),
        withSpinner(reactableOutput("tabela_cli"), type = 4, color = cores_reativo()[2]),
        div(class = "dv-legenda",
            span(class = "dv-legenda-alerta"),
            paste0("devolução acima de 5% do faturamento, ou ativo parado há ", dias_parado, "+ dias"),
            span(class = "dv-legenda-chave"), "faturamento do mês e de 12 meses")
      )
    )
  )
}
