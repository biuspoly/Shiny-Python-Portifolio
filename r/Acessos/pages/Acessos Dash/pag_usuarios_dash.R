pag_usuarios_dash <- function() {
  source(glue("{diretorio}pages/Acessos Dash/Dados/dados_acessos.R"),
    local = TRUE, encoding = "UTF-8"
  )

  # ── State ─────────────────────────────────────────────────────────────────────

  refresh_revendas <- reactiveVal(0)

  lista_usuarios <- reactive({
    usuarios_ativos()
  })

  revendas_acesso <- reactive({
    refresh_revendas()
    acesso_rev()
  })

  # ── Filtros ───────────────────────────────────────────────────────────────────

  opcoes_filtro <- pickerOptions(
    title              = "Selecione",
    size               = 5,
    style              = "btn-color",
    countSelectedText  = " {0} Itens",
    selectedTextFormat = "count > 1",
    container          = "body",
    liveSearch         = TRUE
  )

  # ── Validação de login ────────────────────────────────────────────────────────

  observeEvent(input$input_add_login, {
    req(input$input_add_login)

    if (str_detect(input$input_add_login, "\\.")) {
      hideFeedback("input_add_login")
      updateActionButton(session, "bt_exc_usuario", disabled = FALSE)
      updateTextInput(session, "input_add_nome",
        value = paste0(str_to_title(strsplit(input$input_add_login, "\\.")[[1]]), collapse = " ")
      )
    } else {
      showFeedbackDanger("input_add_login", text = "Insira um login válido (nome.sobrenome)")
      updateActionButton(session, "bt_exc_usuario", disabled = TRUE)
      updateTextInput(session, "input_add_nome",
        value = paste0(str_to_title(strsplit(input$input_add_login, "\\.")[[1]]), collapse = " ")
      )
    }
  })

  observeEvent(
    list(
      input$input_add_login, input$input_add_cargo,
      input$input_add_nome, input$input_usr_revenda
    ),
    {
      req(
        input$input_add_login, input$input_add_cargo,
        input$input_add_nome, input$input_usr_revenda
      )

      campos_ok <- input$input_add_login != "" &&
        input$input_add_cargo != "" &&
        input$input_add_nome != "" &&
        input$input_usr_revenda != "" &&
        str_detect(input$input_add_login, "\\.")

      updateActionButton(session, "bt_add_usuario", disabled = !campos_ok)
    }
  )

  # ── Botões ────────────────────────────────────────────────────────────────────

  observeEvent(input$bt_limpa_adicao, {
    updateTextInput(session, "input_add_login", value = "")
    updateTextInput(session, "input_add_cargo", value = "")
    updateTextInput(session, "input_add_nome", value = "")
    updateTextInput(session, "input_usr_revenda", value = "Matriz")
    updateActionButton(session, "bt_exc_usuario", disabled = TRUE)
    updateActionButton(session, "bt_add_usuario", disabled = TRUE)
  })

  observeEvent(input$bt_check_acesso, {
    req(revendas_acesso_filtradas())

    linha <- input$bt_check_acesso$row
    tabela <- revendas_acesso_filtradas()

    if (is.null(linha) || linha < 1 || linha > nrow(tabela)) {
      return()
    }

    add_ret_acesso_rev(
      tabela$login[linha],
      tabela$licenca[linha],
      input$bt_check_acesso$value
    )
    refresh_revendas(refresh_revendas() + 1)
  })

  observeEvent(input$bt_exc_usuario, {
    req(input$input_add_login)
    retorno <- demitir_usuario(input$input_add_login)
    refresh_revendas(refresh_revendas() + 1)

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

  observeEvent(input$bt_add_usuario, {
    req(
      input$input_add_login, input$input_add_cargo,
      input$input_add_nome, input$input_usr_revenda
    )

    retorno <- admitir_usuario(
      input$input_add_login,
      input$input_add_cargo,
      input$input_add_nome,
      input$input_usr_revenda
    )
    refresh_revendas(refresh_revendas() + 1)

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

  # ── Filtro de usuário para tabela de revendas ─────────────────────────────────

  observeEvent(lista_usuarios(), {
    updatePickerInput(session, "filtro_usr_rev",
      choices  = c("Todos", sort(unique(lista_usuarios()$Login))),
      selected = "Todos"
    )
  })

  revendas_acesso_filtradas <- reactive({
    req(revendas_acesso())
    df <- revendas_acesso()
    if (!is.null(input$filtro_usr_rev) && input$filtro_usr_rev != "Todos") {
      df <- df[df$login == input$filtro_usr_rev, ]
    }
    df
  })

  # ── Tabela de revendas ────────────────────────────────────────────────────────

  output$tabela_acessos_revendas <- renderReactable({
    req(revendas_acesso_filtradas())

    reactable(
      revendas_acesso_filtradas(),
      defaultColDef = colDef(align = "center"),
      columns = list(
        login = colDef(filterable = TRUE, name = "Login"),
        nome = colDef(filterable = TRUE, name = "Revenda"),
        licenca = colDef(show = FALSE),
        check = colDef(
          name = "Acesso",
          cell = checkbox_extra("bt_check_acesso"),
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
        ),
        rowStyle = list(height = "30px"),
        cellStyle = list(padding = "4px 8px")
      )
    )
  })

  output$dl_revendas <- downloadHandler(
    filename = function() paste0("acessos-revendas-", Sys.Date(), ".xlsx"),
    content = function(file) {
      df <- revendas_acesso_filtradas()
      df$check <- NULL
      writexl::write_xlsx(df, file)
    }
  )

  # ── UI ────────────────────────────────────────────────────────────────────────

  fluidRow(
    column(
      12,
      fluidRow(
        box(
          title = "Cadastrar / Desativar usuário",
          status = "primary",
          solidHeader = TRUE,
          collapsible = TRUE,
          maximizable = TRUE,
          width = 12,
          fluidRow(
            column(2, textInput("input_add_login", label = "Login", placeholder = "nome.sobrenome")),
            column(2, textInput("input_add_cargo", label = "Cargo", placeholder = "Cargo")),
            column(2, textInput("input_add_nome", label = "Nome completo")),
            column(2, textInput("input_usr_revenda", label = "Revenda", value = "Matriz")),
            column(1),
            column(
              1,
              div(
                style = "display:flex; align-items:center; justify-content:center; height:100%;",
                actionButton("bt_limpa_adicao", label = NULL, status = "info", icon = icon("eraser"), size = "lg")
              )
            ),
            column(
              1,
              div(
                style = "display:flex; align-items:center; justify-content:center; height:100%;",
                actionButton("bt_exc_usuario", label = NULL, status = "danger", icon = icon("user-minus"), size = "lg", disabled = TRUE)
              )
            ),
            column(
              1,
              div(
                style = "display:flex; align-items:center; justify-content:center; height:100%;",
                actionButton("bt_add_usuario", label = NULL, status = "success", icon = icon("user-plus"), size = "lg", disabled = TRUE)
              )
            )
          )
        )
      ),
      fluidRow(
        box(
          title = fluidRow(
            column(10, "Acesso por Revenda"),
            column(2,
              align = "right",
              downloadBttn("dl_revendas", label = NULL, style = "stretch", color = "default") %>%
                tagAppendAttributes(title = "Download XLSX", style = "background-color:white!important;border-color:white!important;color:#333!important;")
            )
          ),
          status = "primary",
          solidHeader = TRUE,
          collapsible = TRUE,
          maximizable = TRUE,
          width = 12,
          fluidRow(
            column(
              3,
              pickerInput("filtro_usr_rev", "Filtrar por usuário",
                choices = "Todos", selected = "Todos",
                options = opcoes_filtro
              )
            )
          ),
          withSpinner(reactableOutput("tabela_acessos_revendas"), type = 4)
        )
      )
    )
  )
}
