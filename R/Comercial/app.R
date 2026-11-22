# options(shiny.sessionTimeout = 3600) #Sessao ativa por 1h

suppressPackageStartupMessages({
  library(shiny)
  library(bslib)
  library(bs4Dash)
  library(fresh)
  library(dplyr)
  library(lubridate)
  library(shinyWidgets)
  library(writexl)
  library(reactable)
  library(DT)
  library(glue)
  library(htmltools)
  library(DBI)
  library(shinyFeedback)
  library(shinycssloaders)
  library(reactable.extras)
  library(shinyalert)
  library(cicerone)
  library(duckdb)
  library(plotly)
  # library(shinymanager)
  library(stringr)
  library(shinyjs)
  library(echarts4r)
  library(jsonlite)
})

# Portfólio: o reactablefmtr não existe para o R do navegador (webR). As telas só usam o icon_sets():
# o ícone (e a cor) de outras colunas da tabela ao lado do valor -- esta é a mesma ideia, mínima.
if (nzchar(system.file(package = "reactablefmtr"))) {  # requireNamespace() no webR tenta instalar e volta vazio
  library(reactablefmtr)
} else {
  icon_sets <- function(data, icon_ref = NULL, icon_color_ref = NULL, icon_position = "left", ...) {
    function(value, index) {
      icone <- if (!is.null(icon_ref)) data[[icon_ref]][index] else NA
      cor <- if (!is.null(icon_color_ref)) data[[icon_color_ref]][index] else "inherit"
      marca <- if (!is.na(icone) && nzchar(icone)) shiny::icon(icone, style = paste0("color:", cor, "; margin-right:6px")) else NULL
      if (identical(icon_position, "right")) htmltools::tagList(value, marca) else htmltools::tagList(marca, value)
    }
  }
}


# Diretorio ---------------------------------------------------------------
diretorio <- ""

# Configurações do banco e usuarios --------------------------------------------------


# source(glue("{diretorio}pega_login.R"), local = TRUE, encoding = "UTF-8")

poder_total <- c("visitante")
poder_total_comodato <- c("visitante")

# usuario = reactiveVal(NULL)

# Definição de botoes do menu ---------------------------------------------

empresas_ven <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_ind <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_mkp <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_mco <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_vas <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_cpz <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_pux <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_dlp <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_cmd <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_rln <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_rln <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_rin <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_rse <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_hlp <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_bnf <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_fis <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_cabc <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")


# Tema --------------------------------------------------------------------
# Cores iniciais

cores_iniciais <- c("#06825d", "#69b49d", "#FFF", "#272c30", "#fff", "#fff")

# Ordem das cores: 1- Sidebar; 2- Botoes e cabecalhos (caixas, cards); 3- Fontes (Botoes e cabecalhos)
#                 4- Fontes (Conteudo das caixas/ cards); 5- Entradas de texto; 6- background caixas



# Caminhos static

try(addResourcePath("acomp_com_www", "www"), silent = TRUE)


# UI + SERVER -------------------------------------------------------------
comercial_ui <-
  # secure_app(
  # timeout = 0,
  # enable_admin = TRUE,
  # language = "pt-BR",
  # keep_auth = TRUE,
  ui <- dashboardPage(
    help = NULL,
    header = dashboardHeader(
      title = uiOutput("revenda"),
      status = "light",
      controlbarIcon = icon("tools") %>% tagAppendAttributes(title = "Ferramentas"),
      sidebarIcon = tagList(
        tags$i(class = "fa fa-angle-left sidebar-toggle-left"),
        tags$i(class = "fa fa-angle-right sidebar-toggle-right")
      ),
      rightUi = tagList(
        tags$li(
          class = "dropdown",
          style = "padding: 6px 10px 0 0;",
          selectInput("revenda_portfolio", NULL, c("Natal" = "NATAL", "Fortaleza" = "FORTALEZA", "Teresina" = "TERESINA", "São Luís" = "SÃO LUÍS"), width = "150px")
        ),
        tags$li(
          class = "dropdown",
          uiOutput("ultima_atualizacao_dv_ui")
        ),
        uiOutput("aviso_ui"),
        tags$li(
          class = "dropdown",
          uiOutput("guia_ui")
        )
      )
    ),
    sidebar = dashboardSidebar(
      # sidebarSearchForm("search_text","bt_procura",label = "Procurar",icon = icon("toggle")),
      width = 500,
      collapsed = TRUE,
      minified = TRUE,
      tags$style(".sidebar-menu {position: relative; top: 20px;}"),
      sidebarMenu(
        id = "tabs",
        menuItemOutput("menu_diario_venda"),
        menuItemOutput("menu_mapa_comercial")
      )
      # br(),
      # div(
      #   style = "display: flex; justify-content: center; align-items: center; height: 60px;",
      #   actionBttn(
      #     inputId = "btn_acao",
      #     label = NULL,
      #     icon = icon("robot"),
      #     style = "material-circle",
      #     color = "default",
      #     size = "sm"
      #   )
      # ),

      # customArea = uiOutput("ult_atualizacao_ui")
    ),
    body = dashboardBody(
      tags$div(
        style = "position: absolute; top: -100px;",
        textOutput("clock")
      ),
      uiOutput("tema_dinamico"),
      includeCSS(glue("{diretorio}www/style_geral.css")),
      includeCSS(glue("{diretorio}www/style_robot.css")),
      useShinyFeedback(),
      useSweetAlert(),
      reactable_extras_dependency(),
      use_cicerone(),
      useShinyjs(),
      tabItems(
        tabItem(
          tabName = "id_diario_venda",
          withSpinner(uiOutput("conteudo_diario_venda"), type = 8)
        ),
        tabItem(
          tabName = "id_mapa_com",
          withSpinner(uiOutput("conteudo_mapa_com"), type = 8)
        )
        # tabItem(
        #   tabName = "id_comod_acomp_ref_com",
        #   withSpinner(uiOutput("conteudo_comodatos_refrig_com"),type = 4,color = cores_iniciais[2])
        # ),
      ),
    ),

    # controlbar = dashboardControlbar(
    # collapsed = TRUE,
    # width = 50,
    # overlay = TRUE,
    # uiOutput("bt_download_ui"),
    # uiOutput("dark_mode_bt")
    # # br(),
    # # uiOutput("bt_refresh_ui")
    # ),

    title = "Acompanhamento comercial"
  )
# )


comercial_server <- function(input, output, session) {
  # Teste local: comentar para producao -------------------------------------

  # Manter conexao viva -----------------------------------------------------
  session$allowReconnect("force")
  # Portfólio: sem login -- quem abre a página é o visitante.
  session$userData$usuario <- "visitante"
  output$clock <- renderText({
    invalidateLater(5000)
    Sys.time()
  })
  observe({
    invalidateLater(10000)
    cat(".")
  })

  # Logs do server ----------------------------------------------------------


  # Usuarios ----------------------------------------------------------------

  observe({
    req(session$userData$usuario)

    # session$userData$usuario = "user.teste"
    # session$userData$usuario = login(session$request$HTTP_COOKIE)
    # print(session$userData$usuario)
    if (!(session$userData$usuario %in% usuarios()$user)) {
      print("Usuario nao consta na lista de permissoes")
      session$userData$usuario <- "user.teste"
    }
    print(session$userData$usuario)
  })


  # Portfólio: no lugar da planilha de usuários, o visitante com as abas do portfólio.
  usuarios <- reactive({
    data.frame(user = "visitante", abas_comercial = "ven,mco", dark_mode = "N")
  })

  # usuarios <- reactive({
  #   readxl::read_excel(glue("{diretorio}usuarios.xlsx"))
  # })


  # Filtro por url ----------------------------------------------------------
  # ReactiveVal em vez de reactive: so notifica downstream quando o VALOR muda.
  # getQueryString() pode ser re-avaliado durante a inicializacao da sessao
  # (mesmo retornando o mesmo valor), o que causaria re-renders desnecessarios.

  revenda_query <- reactiveVal(NULL)
  local({
    # Portfólio: sem o portal que monta a URL, a revenda vem da caixa no topo.
    raw <- reactive({ query <- getQueryString(); if (!is.null(query[["REVENDA"]])) query[["REVENDA"]] else (input$revenda_portfolio %||% "NATAL") })
    observe({
      r <- raw()
      if (!identical(r, revenda_query())) revenda_query(r)
    })
  })

  # user_query <- reactive({
  #   query <- getQueryString()
  #   query[["user"]]
  # })


  # Renderizar Logo e titulo ------------------------------------------------

  output$revenda <- renderUI({
    dashboardBrand(title = tags$b("Comercial (R)"), image = "acomp_com_www/img/marca_mini.svg", color = "secondary")
  })

  # Renderizar abas do menu ------------------------------------------------

  output$menu_diario_venda <- renderMenu({
    if (((length(revenda_query()) == 0) || (revenda_query() %in% empresas_ven)) && session$userData$usuario %in% usuarios()[str_detect(usuarios()$abas_comercial, "ven") %in% TRUE, ]$user) {
      menuItem("Diário de Venda", tabName = "id_diario_venda", icon = icon(NULL, class = "custom-icon-casa"))
    }
  })



  output$menu_mapa_comercial <- renderMenu({
    if (((length(revenda_query()) == 0) || (revenda_query() %in% empresas_mco)) && session$userData$usuario %in% usuarios()[str_detect(usuarios()$abas_comercial, "mco") %in% TRUE, ]$user) {
      menuItem("Mapa Comercial", tabName = "id_mapa_com", icon = icon(NULL, class = "custom-icon-mapa"))
    }
  })















  observe({
    abas_disponiveis <- c()

    if (((length(revenda_query()) == 0) || (revenda_query() %in% empresas_ven)) && session$userData$usuario %in% usuarios()[str_detect(usuarios()$abas_comercial, "ven") %in% TRUE, ]$user) {
      abas_disponiveis <- c(abas_disponiveis, "id_diario_venda")
    }
    if (((length(revenda_query()) == 0) || (revenda_query() %in% empresas_mco)) && session$userData$usuario %in% usuarios()[str_detect(usuarios()$abas_comercial, "mco") %in% TRUE, ]$user) {
      abas_disponiveis <- c(abas_disponiveis, "id_mapa_com")
    }

    # Seleciona a primeira aba disponível
    if (length(abas_disponiveis) > 0) {
      updateTabItems(session, "tabs", selected = abas_disponiveis[1])
    }
  })


  # Carregar páginas separadas ---------------------------------------------
  # pag_fiscal_base_generica e dependencia compartilhada das paginas fiscais —
  # carregada no startup para estar disponivel quando qualquer aba fiscal abrir.

  # Demais modulos: carregados sob demanda na primeira vez que a aba e acessada.
  source(glue("{diretorio}pages/lazy_loader.R"), local = TRUE, encoding = "UTF-8")
  setup_lazy_modules(output, diretorio, environment())

  # Dark mode ----------------------------------------------------------

  # Função para criar tema dinamicamente
  criar_tema <- function(cores_valor) {
    create_theme(
      bs4dash_vars(
        navbar_light_color = cores_valor[3],
        navbar_light_active_color = cores_valor[3],
        navbar_light_hover_color = cores_valor[3],
        card_bg = cores_valor[6]
      ),
      bs4dash_yiq(
        contrasted_threshold = 10,
        text_dark = cores_valor[3],
        text_light = cores_valor[3]
      ),
      bs4dash_layout(
        main_bg = cores_valor[6],
        sidebar_width = "220px"
      ),
      bs4dash_sidebar_light(
        bg = cores_valor[1],
        color = cores_valor[3],
        hover_color = cores_valor[3],
        submenu_color = cores_valor[3],
        submenu_hover_color = cores_valor[3],
        submenu_bg = cores_valor[1],
        submenu_active_bg = cores_valor[2]
      ),
      bs4dash_status(
        primary = cores_valor[2],
        light = cores_valor[1],
        secondary = cores_valor[1]
      ),
      bs4dash_color(
        gray_900 = cores_valor[4],
        white = cores_valor[5]
      )
    )
  }

  cores_reativo <- reactive({
    # if (session$userData$usuario %in% usuarios()[usuarios()$dark_mode == "S",]$user){
    #   c("#272c30","#254D71","#FFF","#FFF","#272c30", "#272c30")
    # } else {
    #   c("#254D71","#3874AB","#FFF","#272c30","#fff", "#fff")
    # }
    c("#06825d", "#69b49d", "#FFF", "#272c30", "#fff", "#fff")
  })

  # Para o tema
  output$tema_dinamico <- renderUI({
    use_theme(criar_tema(cores_reativo()))
  })

  # output$dark_mode_bt = renderUI({
  #   if (session$userData$usuario %in% usuarios()[usuarios()$dark_mode == "S",]$user){
  #     actionBttn("bt_dark_mode",icon = icon("sun"),style = "stretch", color = "default")
  #   } else {
  #     actionBttn("bt_dark_mode",icon = icon("moon"),style = "stretch", color = "default")
  #   }
  # })

  # observeEvent(input$bt_dark_mode, {
  #   # pega o data frame atual
  #   df <- usuarios()
  #
  #   # índice do usuário
  #   idx <- which(df$user == session$userData$usuario)
  #
  #   if (length(idx) == 1) {
  #     # alterna dark_mode
  #     df$dark_mode[idx] <- ifelse(df$dark_mode[idx] == "S", "N", "S")
  #
  #     # salva de volta no arquivo
  #     writexl::write_xlsx(df, glue("{diretorio}usuarios.xlsx"))
  #
  #     # atualiza o ícone do botão
  #     new_icon <- if (df$dark_mode[idx] == "S") icon("sun") else icon("moon")
  #     updateActionButton(session, "bt_dark_mode", icon = new_icon)
  #   }
  # })

  ### Download reativo

  output$bt_download_ui <- renderUI({
    downloadBttn(
      outputId = paste0("bt_download_", input$tabs), # id dinâmico baseado na aba
      label = NULL,
      style = "stretch",
      color = "default"
    ) %>%
      tagAppendAttributes(title = "Baixar tabela")
  })


  ### Ultima atualizacao

  update_time_dv <- reactive({
    # Portfólio: no original, a hora da última carga da tabela de vendas no MySQL.
    as.POSIXct(Sys.Date()) + 3 * 3600
  })

  output$ultima_atualizacao_dv_ui <- renderUI({
    dt_raw       <- update_time_dv()
    dt_br        <- if (!is.na(dt_raw)) as.POSIXct(dt_raw) - 3 * 3600 else NA
    label        <- if (!is.na(dt_br)) format(dt_br, "%d/%m/%Y") else "-"
    desatualizado <- !is.na(dt_br) && as.Date(dt_br) < Sys.Date()
    tags$span(
      style = paste0(
        "font-size: 14px; font-weight: bold; display: flex; align-items: center; padding: 0 10px; white-space: nowrap;",
        if (desatualizado) " color: red;" else " color: #fff; opacity: 0.85;"
      ),
      paste0("Atualizado em: ", label)
    )
  })

  ### Aviso

  # output$aviso_ui = renderUI({
  #   req(input$tabs)
  #   if(str_detect(input$tabs, "frota")){
  #     div(
  #       textOutput(outputId = paste0("aviso_", input$tabs)),
  #       style = glue("color: red; font-size: 26px; display: flex; align-items: center")
  #     )
  #   }
  #   else if(str_detect(input$tabs, "dev")){
  #     uiOutput(outputId = paste0("aviso_", input$tabs))
  #   }
  #   else{
  #     NULL
  #   }
  #
  # })


  ### Guia de ajuda

  # output$guia_ui = renderUI({
  #   req(input$tabs)
  #   if(str_detect(input$tabs, "id_diario_venda")){
  #     div(
  #         actionButton(paste0("bt_guia_", input$tabs),label = NULL,icon = icon("question"), status = "secondary") %>%
  #           tagAppendAttributes(title = "Ajuda")
  #     )
  #   }
  #   else if(str_detect(input$tabs, "id_mapa_com")){
  #     div(
  #       actionButton(paste0("bt_guia_", input$tabs),label = NULL,icon = icon("question"), status = "secondary") %>%
  #         tagAppendAttributes(title = "Ajuda")
  #     )
  #   }
  # })


  ### Robô


  # observeEvent(input$btn_acao, {
  #
  #
  #   showModal(
  #     modalDialog(
  #       # title = "Assistente",
  #
  #       easyClose = TRUE,
  #       bslib::card(style = "height:70vh; overflow-y:auto;",
  #                   bslib::card_header("Robot shiny"),
  #         bslib::card_body(chat_ui(paste0("chat_",input$tabs),messages = "Olá! Em que posso ajudar?",fill = TRUE),fill = TRUE,fillable = TRUE)
  #
  #       ),
  #
  #
  #       footer = NULL
  #     )
  #   )
  # })
  # observeEvent(input$keepalive_COM, {
  #   # mantém conexão viva
  # }, ignoreInit = TRUE)
}

# Executar app
shinyApp(comercial_ui, comercial_server)
#
# runApp(
#   list(ui = comercial_ui, server = comercial_server),
#   host = "0.0.0.0",
#   port = 8080
# )
