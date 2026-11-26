pag_usuarios <- function() {
  source(glue("{diretorio}pages/Acessos Dash/Dados/dados_acessos.R"),
    local = TRUE, encoding = "UTF-8"
  )

  # ── State ─────────────────────────────────────────────────────────────────────

  refresh_perm <- reactiveVal(0)

  lista_paineis <- reactive({
    paineis_ativos()
  })
  lista_usuarios <- reactive({
    usuarios_ativos()
  })

  filtro_acesso_paineis <- reactive({
    refresh_perm()
    acessos_paineis()
  })

  # ── Filtros ───────────────────────────────────────────────────────────────────

  opcoes_filtro <- pickerOptions(
    title                = "Selecione",
    size                 = 5,
    style                = "btn-color",
    countSelectedText    = " {0} Itens",
    selectedTextFormat   = "count > 1",
    container            = "body",
    liveSearch           = TRUE
  )

  observeEvent(lista_paineis(), {
    updatePickerInput(session, "input_add_painel",
      choices = sort(unique(lista_paineis()$Painel))
    )
  })

  observeEvent(lista_usuarios(), {
    updatePickerInput(session, "input_add_usuario",
      choices = sort(unique(lista_usuarios()$Login))
    )
  })

  observeEvent(input$input_add_painel, {
    req(input$input_add_painel)
    updatePickerInput(
      session, "input_add_revenda",
      choices = sort(unique(
        lista_paineis()$Revenda[lista_paineis()$Painel == input$input_add_painel]
      ))
    )
  })

  # ── Botões ────────────────────────────────────────────────────────────────────

  observeEvent(input$bt_limpa_acesso, {
    updatePickerInput(session, "input_add_painel", selected = character(0))
    updatePickerInput(session, "input_add_revenda", choices = "", selected = character(0))
    updatePickerInput(session, "input_add_usuario", selected = character(0))
  })

  observeEvent(input$bt_add_acesso, {
    req(input$input_add_painel, input$input_add_usuario, input$input_add_revenda)

    grupo_id <- lista_usuarios()$nomeGrupo[lista_usuarios()$Login == input$input_add_usuario]
    painel_id <- lista_paineis()$id[
      lista_paineis()$Painel == input$input_add_painel &
        lista_paineis()$Revenda == input$input_add_revenda
    ]

    retorno <- adicion_acesso_usuario(grupo_id, painel_id)
    refresh_perm(refresh_perm() + 1)

    tipo <- if (startsWith(retorno, "Erro")) "danger" else "success"
    shinyalert(
      title               = retorno,
      size                = "xs",
      type                = tipo,
      timer               = 2000,
      closeOnClickOutside = TRUE,
      showConfirmButton   = FALSE
    )
  })

  observeEvent(input$bt_exclui_acesso_usu, {
    req(input$bt_exclui_acesso_usu)

    row_idx <- input$bt_exclui_acesso_usu$row
    df <- filtro_acesso_paineis()

    retorno <- excluir_acesso_usuario(df$Grupo[row_idx], df$id[row_idx])
    refresh_perm(refresh_perm() + 1)

    tipo <- if (startsWith(retorno, "Erro")) "danger" else "success"
    shinyalert(
      title               = retorno,
      size                = "xs",
      type                = tipo,
      timer               = 2000,
      closeOnClickOutside = TRUE,
      showConfirmButton   = FALSE
    )
  })

  # ── KPIs ──────────────────────────────────────────────────────────────────────

  output$kpi_permissoes_ui <- renderUI({
    df <- filtro_acesso_paineis()
    fluidRow(
      infoBox(
        title = "Total de acessos",
        value = nrow(df),
        icon  = icon("key"),
        color = "success",
        width = 4,
        fill  = TRUE
      ),
      infoBox(
        title = "Usuários com acesso",
        value = n_distinct(df$Login),
        icon  = icon("users"),
        color = "info",
        width = 4,
        fill  = TRUE
      ),
      infoBox(
        title = "Painéis disponíveis",
        value = n_distinct(df$Painel),
        icon  = icon("th-large"),
        color = "warning",
        width = 4,
        fill  = TRUE
      )
    )
  })

  # ── Tabela ────────────────────────────────────────────────────────────────────

  output$tabela_acessos_paineis_dash <- renderReactable({
    req(filtro_acesso_paineis())

    reactable(
      filtro_acesso_paineis(),
      defaultColDef = colDef(align = "center"),
      columns = list(
        id = colDef(show = FALSE),
        Painel = colDef(filterable = TRUE),
        Login = colDef(filterable = TRUE),
        Usuario = colDef(filterable = TRUE),
        Revenda = colDef(filterable = TRUE),
        Grupo = colDef(show = FALSE, filterable = TRUE),
        Excluir = colDef(
          name = "Retirar Acesso",
          cell = button_extra("bt_exclui_acesso_usu"),
          html = TRUE
        )
      ),
      wrap = FALSE,
      height = "55vh",
      pagination = TRUE,
      defaultPageSize = 50,
      pageSizeOptions = c(50, 100, 500),
      showPageSizeOptions = TRUE,
      resizable = TRUE,
      style = list(overflowX = "auto"),
      language = reactableLang(
        pageNext             = "Próxima",
        pagePrevious         = "Anterior",
        pageInfo             = "{rowStart}–{rowEnd} de {rows} linhas",
        pageSizeOptions      = "Mostrar {rows}",
        pageNextLabel        = "Próxima página",
        pagePreviousLabel    = "Página anterior",
        pageNumberLabel      = "Pág {page}",
        pageJumpLabel        = "Ir para a página",
        pageSizeOptionsLabel = "Linhas por página",
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

  output$dl_permissoes <- downloadHandler(
    filename = function() paste0("permissoes-", Sys.Date(), ".xlsx"),
    content = function(file) {
      df <- filtro_acesso_paineis()
      df$Excluir <- NULL
      writexl::write_xlsx(df, file)
    }
  )

  # ── UI ────────────────────────────────────────────────────────────────────────

  fluidRow(
    column(
      12,
      uiOutput("kpi_permissoes_ui"),
      fluidRow(
        box(
          title = "Conceder acesso a painel",
          status = "primary",
          solidHeader = TRUE,
          collapsible = TRUE,
          maximizable = TRUE,
          width = 12,
          fluidRow(
            column(3, pickerInput("input_add_painel", "Painel", choices = NULL, options = opcoes_filtro)),
            column(3, pickerInput("input_add_revenda", "Revenda", choices = "", options = opcoes_filtro)),
            column(3, pickerInput("input_add_usuario", "Usuário", choices = NULL, options = opcoes_filtro)),
            column(1),
            column(
              1,
              div(
                style = "display:flex; align-items:center; justify-content:center; height:100%;",
                actionButton("bt_limpa_acesso", label = NULL, status = "primary", icon = icon("eraser"))
              )
            ),
            column(
              1,
              div(
                style = "display:flex; align-items:center; justify-content:center; height:100%;",
                actionButton("bt_add_acesso", label = "Adicionar", status = "success")
              )
            )
          )
        )
      ),
      fluidRow(
        box(
          title = fluidRow(
            column(10, "Acessos por painel"),
            column(2,
              align = "right",
              downloadBttn("dl_permissoes", label = NULL, style = "stretch", color = "default") %>%
                tagAppendAttributes(title = "Download XLSX", style = "background-color:white!important;border-color:white!important;color:#333!important;")
            )
          ),
          status = "primary",
          solidHeader = TRUE,
          collapsible = TRUE,
          maximizable = TRUE,
          width = 12,
          withSpinner(reactableOutput("tabela_acessos_paineis_dash"), type = 4)
        )
      )
    )
  )
}
