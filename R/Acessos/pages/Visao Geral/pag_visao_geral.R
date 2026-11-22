pag_visao_geral <- function() {
  source(glue("{diretorio}pages/Visao Geral/Dados/dados_visao_geral.R"),
    local = TRUE, encoding = "UTF-8"
  )

  # ── Reactive state ────────────────────────────────────────────────────────────

  rv_kpi <- reactiveVal()
  rv_tend <- reactiveVal()
  rv_ultimo <- reactiveVal()

  observeEvent(TRUE,
    {
      rv_kpi(kpis_acesso())
      rv_tend(tendencia_acessos())
      rv_ultimo(ultimo_acesso_usuario())
    },
    once = TRUE
  )

  timer_vg <- reactiveTimer(60000)

  observe({
    timer_vg()
    rv_kpi(kpis_acesso())
    rv_tend(tendencia_acessos())
    rv_ultimo(ultimo_acesso_usuario())
  })

  # ── Info boxes ────────────────────────────────────────────────────────────────

  output$ibox_vg_usuarios <- renderInfoBox({
    req(rv_kpi())
    infoBox(rv_kpi()$total_usuarios,
      subtitle = "Usuários Ativos",
      icon = icon("users"), color = "primary"
    )
  })

  output$ibox_vg_paineis <- renderInfoBox({
    req(rv_kpi())
    infoBox(rv_kpi()$total_paineis,
      subtitle = "Painéis Ativos",
      icon = icon("desktop"), color = "info"
    )
  })

  output$ibox_vg_acessos7d <- renderInfoBox({
    req(rv_kpi())
    infoBox(rv_kpi()$acessos_7_dias,
      subtitle = "Acessos (7 dias)",
      icon = icon("sign-in-alt"), color = "success"
    )
  })

  output$ibox_vg_usu7d <- renderInfoBox({
    req(rv_kpi())
    infoBox(rv_kpi()$usuarios_ativos_7_dias,
      subtitle = "Usuários Ativos (7 dias)",
      icon = icon("user-check"), color = "warning"
    )
  })

  # ── Tendência ─────────────────────────────────────────────────────────────────

  output$graf_vg_tendencia <- renderPlotly({
    req(rv_tend())
    df <- rv_tend()
    req(nrow(df) > 0)

    escala <- if (max(df$total_acessos, na.rm = TRUE) > 0 && max(df$usuarios_distintos, na.rm = TRUE) > 0) {
      max(df$total_acessos) / max(df$usuarios_distintos)
    } else {
      1
    }

    p <- ggplot(df, aes(x = data)) +
      geom_col(
        aes(
          y = total_acessos,
          text = paste0("Data: ", format(data, "%d/%m"), "<br>Acessos: ", total_acessos)
        ),
        fill = cores_iniciais[2], alpha = 0.8
      ) +
      geom_line(
        aes(
          y = usuarios_distintos * escala,
          text = paste0("Usuários únicos: ", usuarios_distintos)
        ),
        color = "#E74C3C", linewidth = 1
      ) +
      geom_point(aes(y = usuarios_distintos * escala), color = "#E74C3C", size = 2.5) +
      scale_y_continuous(
        name = "Total Acessos",
        sec.axis = sec_axis(~ . / escala, name = "Usuários Únicos")
      ) +
      labs(x = "") +
      theme_minimal(base_size = 13) +
      theme(axis.text.x = element_text(angle = 45, hjust = 1))

    ggplotly(p, tooltip = "text") %>%
      layout(hovermode = "x unified")
  })

  # ── Tabela último acesso ──────────────────────────────────────────────────────

  output$tabela_vg_ultimo_acesso <- renderReactable({
    req(rv_ultimo())
    df <- rv_ultimo()

    df$dias_inativo <- as.numeric(
      difftime(Sys.time(), df$ultimo_acesso, units = "days")
    )

    reactable(
      df,
      defaultColDef = colDef(align = "center"),
      columns = list(
        login = colDef(name = "Login", filterable = TRUE),
        nome = colDef(name = "Nome", filterable = TRUE),
        cargo = colDef(name = "Cargo"),
        revenda = colDef(name = "Revenda", filterable = TRUE),
        ultimo_acesso = colDef(name = "Último Acesso", format = colFormat(datetime = TRUE)),
        acessos_30d = colDef(name = "Acessos (30d)"),
        dias_inativo = colDef(
          name = "Dias Sem Acesso",
          defaultSortOrder = "desc",
          cell = function(value) {
            if (is.na(value)) {
              cor <- "#999"
              txt <- "Nunca acessou"
            } else if (value > 30) {
              cor <- "#E53935"
              txt <- as.character(round(value))
            } else if (value > 7) {
              cor <- "#FF8F00"
              txt <- as.character(round(value))
            } else {
              cor <- "#43A047"
              txt <- as.character(round(value))
            }
            tags$span(style = glue("color:{cor}; font-weight:bold"), txt)
          },
          html = TRUE
        )
      ),
      wrap = FALSE,
      height = "50vh",
      pagination = TRUE,
      defaultPageSize = 50,
      pageSizeOptions = c(50, 100),
      showPageSizeOptions = TRUE,
      resizable = TRUE,
      defaultSorted = "dias_inativo",
      defaultSortOrder = "desc",
      style = list(overflowX = "auto"),
      language = reactableLang(
        pageNext = "Próxima",
        pagePrevious = "Anterior",
        pageInfo = "{rowStart}–{rowEnd} de {rows} linhas",
        pageSizeOptions = "Mostrar {rows}",
        pageNextLabel = "Próxima página",
        pagePreviousLabel = "Página anterior",
        pageNumberLabel = "Pág {page}",
        pageJumpLabel = "Ir para a página",
        pageSizeOptionsLabel = "Linhas por página",
        noData = "Sem dados"
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

  output$dl_vg_ultimo <- downloadHandler(
    filename = function() paste0("ultimo-acesso-", Sys.Date(), ".xlsx"),
    content = function(file) {
      df <- rv_ultimo()
      df$dias_inativo <- as.numeric(difftime(Sys.time(), df$ultimo_acesso, units = "days"))
      writexl::write_xlsx(df, file)
    }
  )

  # ── UI ────────────────────────────────────────────────────────────────────────

  fluidRow(
    column(
      12,
      fluidRow(
        infoBoxOutput("ibox_vg_usuarios", width = 3),
        infoBoxOutput("ibox_vg_paineis", width = 3),
        infoBoxOutput("ibox_vg_acessos7d", width = 3),
        infoBoxOutput("ibox_vg_usu7d", width = 3)
      ),
      fluidRow(
        box(
          title = "Tendência de Acessos — últimos 30 dias",
          status = "primary",
          solidHeader = TRUE,
          collapsible = TRUE,
          maximizable = TRUE,
          width = 12,
          withSpinner(plotlyOutput("graf_vg_tendencia", height = "300px"), type = 4)
        )
      ),
      fluidRow(
        box(
          title = fluidRow(
            column(10, "Último Acesso por Usuário"),
            column(2,
              align = "right",
              downloadBttn("dl_vg_ultimo", label = NULL, style = "stretch", color = "default") %>%
                tagAppendAttributes(title = "Download XLSX", style = "background-color:white!important;border-color:white!important;color:#333!important;")
            )
          ),
          status = "primary",
          solidHeader = TRUE,
          collapsible = TRUE,
          maximizable = TRUE,
          width = 12,
          withSpinner(reactableOutput("tabela_vg_ultimo_acesso"), type = 4)
        )
      )
    )
  )
}
