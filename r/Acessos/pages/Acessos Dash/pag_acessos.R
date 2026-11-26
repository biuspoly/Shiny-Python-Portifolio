pag_acessos <- function() {
  source(glue("{diretorio}pages/Acessos Dash/Dados/dados_acessos.R"),
    local = TRUE, encoding = "UTF-8"
  )

  # ── State ─────────────────────────────────────────────────────────────────────

  dados_acessos <- reactiveVal()

  observeEvent(TRUE,
    {
      dados_acessos(acesso_dash())
    },
    once = TRUE
  )

  acessos_geral <- reactive({
    req(dados_acessos())
    dados_acessos()
  })

  # ── Timer de refresh ──────────────────────────────────────────────────────────

  timer_acesso <- reactive({
    req(input$tempo_input_ac)
    reactiveTimer(input$tempo_input_ac * 1000)
  })

  observe({
    timer_acesso()()
    dados_acessos(acesso_dash())
  })

  # ── Filtros ───────────────────────────────────────────────────────────────────

  opcoes_filtro <- pickerOptions(
    noneSelectedText   = "Todos",
    size               = 5,
    style              = "btn-color",
    countSelectedText  = " {0} Itens",
    selectedTextFormat = "count > 1",
    container          = "body",
    liveSearch         = TRUE
  )

  filtro_acessos <- reactive({
    df <- acessos_geral()
    df$dataAcesso <- as.POSIXct(df$dataAcesso, format = "%d/%m/%Y %H:%M:%S", tz = Sys.timezone())

    if (!is.null(input$painel_ac_input) && length(input$painel_ac_input) > 0) {
      df <- df[df$Painel %in% input$painel_ac_input, ]
    }
    if (!is.null(input$usuario_ac_input) && length(input$usuario_ac_input) > 0) {
      df <- df[df$login %in% input$usuario_ac_input, ]
    }
    df
  })

  observeEvent(acessos_geral(), {
    if (is.null(input$painel_ac_input) || length(input$painel_ac_input) == 0) {
      updatePickerInput(session, "painel_ac_input", choices = sort(unique(acessos_geral()$Painel)))
    }
    if (is.null(input$usuario_ac_input) || length(input$usuario_ac_input) == 0) {
      updatePickerInput(session, "usuario_ac_input", choices = sort(unique(acessos_geral()$login)))
    }
  })

  # ── Tabela ────────────────────────────────────────────────────────────────────

  output$tabela_detalhe_log_acessos <- renderReactable({
    req(filtro_acessos())

    reactable(
      filtro_acessos(),
      defaultColDef = colDef(align = "center"),
      columns = list(
        id          = colDef(show = FALSE),
        login       = colDef(name = "Login", filterable = TRUE),
        dataAcesso  = colDef(name = "Acesso", format = colFormat(datetime = TRUE)),
        Painel      = colDef(name = "Painel", filterable = TRUE),
        Revenda     = colDef(name = "Revenda", filterable = TRUE)
      ),
      wrap = FALSE,
      height = "55vh",
      pagination = TRUE,
      defaultPageSize = 100,
      pageSizeOptions = c(100, 500),
      showPageSizeOptions = TRUE,
      resizable = TRUE,
      defaultSorted = "dataAcesso",
      defaultSortOrder = "desc",
      style = list(overflowX = "auto"),
      language = reactableLang(
        pageNext             = "Próxima",
        pagePrevious         = "Anterior",
        pageInfo             = "{rowStart}–{rowEnd} de {rows} linhas",
        pageSizeOptions      = "Mostrar {rows}",
        noData               = "Sem dados"
      ),
      theme = reactableTheme(
        backgroundColor = "transparent",
        headerStyle = list(
          backgroundColor = cores_iniciais[2],
          color           = "white",
          fontWeight      = "bold",
          textAlign       = "center"
        ),
        rowSelectedStyle = list(
          backgroundColor = "darkgray",
          boxShadow       = glue("inset 2px 0 0 0 {cores_iniciais[1]}")
        )
      )
    )
  })

  output$dl_log_acessos <- downloadHandler(
    filename = function() paste0("log-acessos-", Sys.Date(), ".xlsx"),
    content  = function(file) writexl::write_xlsx(filtro_acessos(), file)
  )

  # ── Gráfico ───────────────────────────────────────────────────────────────────

  output$graf_acessos_hora <- renderPlotly({
    req(filtro_acessos())
    df <- filtro_acessos()
    df <- df[!is.na(df$dataAcesso), ]
    if (nrow(df) == 0) {
      return(NULL)
    }

    df$hora <- lubridate::floor_date(df$dataAcesso, unit = "hour")

    dados_agg <- df %>%
      dplyr::group_by(hora) %>%
      dplyr::summarise(num_acessos = n(), .groups = "drop")

    p <- ggplot(dados_agg, aes(x = hora, y = num_acessos)) +
      geom_area(fill = cores_iniciais[2], alpha = 0.4) +
      geom_line(color = cores_iniciais[1], linewidth = 1) +
      geom_point(color = cores_iniciais[1], size = 2) +
      labs(x = "", y = "Acessos por hora") +
      theme_minimal(base_size = 13) +
      theme(axis.text.x = element_text(angle = 45, hjust = 1))

    ggplotly(p) %>% layout(hovermode = "x unified")
  })

  # ── UI ────────────────────────────────────────────────────────────────────────

  fluidRow(
    column(
      12,
      fluidRow(
        column(2, numericInput("tempo_input_ac", "Intervalo (s)", value = 30, min = 5, step = 5)),
        column(3, pickerInput("painel_ac_input", "Painel", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
        column(3, pickerInput("usuario_ac_input", "Usuário", choices = NULL, multiple = TRUE, options = opcoes_filtro))
      ),
      fluidRow(
        box(
          title = "Acessos por hora",
          status = "primary",
          solidHeader = TRUE,
          collapsible = TRUE,
          collapsed = FALSE,
          maximizable = TRUE,
          width = 12,
          withSpinner(plotlyOutput("graf_acessos_hora", height = "280px"), type = 4)
        )
      ),
      fluidRow(
        box(
          title = fluidRow(
            column(10, "Detalhes — últimos 7 dias"),
            column(2,
              align = "right",
              downloadBttn("dl_log_acessos", label = NULL, style = "stretch", color = "default") %>%
                tagAppendAttributes(title = "Download XLSX", style = "background-color:white!important;border-color:white!important;color:#333!important;")
            )
          ),
          status = "primary",
          solidHeader = TRUE,
          collapsible = TRUE,
          maximizable = TRUE,
          width = 12,
          withSpinner(reactableOutput("tabela_detalhe_log_acessos"), type = 4)
        )
      )
    )
  )
}
