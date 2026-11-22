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
  library(stringr)
  library(shinyjs)
  library(future)
  library(promises)
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


# Definição de botoes do menu ---------------------------------------------

empresas_fro <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_tic <- c()
empresas_ind <- c()
empresas_pde <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_dev <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_rom <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_pux <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_inv <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")
empresas_cmd <- c("NATAL", "FORTALEZA", "TERESINA", "SÃO LUÍS")




# Tema --------------------------------------------------------------------
# Cores iniciais

# cores_iniciais = c("#254D71","#3874AB","#FFF","#272c30","#fff", "#fff")

# Ordem das cores: 1- Sidebar; 2- Botoes e cabecalhos (caixas, cards); 3- Fontes (Botoes e cabecalhos)
#                 4- Fontes (Conteudo das caixas/ cards); 5- Entradas de texto; 6- background caixas



# Caminhos static

try(addResourcePath("acomp_log_www", "www"), silent = TRUE)
# Portfólio: os PDFs de exemplo dos comodatos (no original, a pasta é servida pelo app principal).
try(addResourcePath("Anexos_Comodato", "Anexos_Comodato"), silent = TRUE)



# UI + SERVER -------------------------------------------------------------
logistica_ui <-
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
        menuItemOutput("menu_frota"),
        menuItemOutput("menu_pde"),
        menuItemOutput("menu_devolucao"),
        menuItemOutput("menu_comod_log")
      ),
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

      customArea = uiOutput("ult_atualizacao_ui")
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
          tabName = "id_geral_frota",
          withSpinner(uiOutput("conteudo_frotas"), type = 4)
        ),
        tabItem(
          tabName = "id_entrada_frota",
          withSpinner(uiOutput("conteudo_frotas_entrada"), type = 4)
        ),
        tabItem(
          tabName = "id_saida_frota",
          withSpinner(uiOutput("conteudo_frotas_saida"), type = 4)
        ),
        tabItem(
          tabName = "id_entrega",
          withSpinner(uiOutput("conteudo_entregas"), type = 4)
        ),
        tabItem(
          tabName = "id_detalhe_dev",
          withSpinner(uiOutput("conteudo_dev"), type = 4)
        ),
        tabItem(
          tabName = "id_caixa_dev",
          withSpinner(uiOutput("conteudo_cx_dev"), type = 4)
        ),
        tabItem(
          tabName = "id_dev_dev",
          withSpinner(uiOutput("conteudo_dev_dev"), type = 4)
        ),
        tabItem(
          tabName = "id_grafico_dev",
          withSpinner(uiOutput("conteudo_graf_dev"), type = 4)
        ),
        tabItem(
          tabName = "id_solicit_comodatos_log",
          withSpinner(uiOutput("conteudo_inadimplentes_log"), type = 4)
        ),
        tabItem(
          tabName = "id_comod_comodatos_log",
          withSpinner(uiOutput("conteudo_comodatos_log"), type = 4)
        ),
        # tabItem(
        #   tabName = "id_comod_acomp_ref_log",
        #   withSpinner(uiOutput("conteudo_comodatos_refrig_log"),type = 4)
        # ),
        tabItem(
          tabName = "id_comod_sld_revendas_log",
          withSpinner(uiOutput("conteudo_comodatos_saldo_log"), type = 4)
        )
      )
    ),
    controlbar = dashboardControlbar(
      collapsed = TRUE,
      width = 50,
      overlay = TRUE,
      uiOutput("bt_download_ui"),
      # uiOutput("dark_mode_bt"),
      uiOutput("bt_ferramenta1")
      # br(),
      # uiOutput("bt_refresh_ui")
    ),
    title = "Acompanhamento logístico"
  )
# )


logistica_server <- function(input, output, session) {
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

    # session$userData$usuario = login(session$request$HTTP_COOKIE)
    print(session$userData$usuario)
  })

  # Filtro por url ----------------------------------------------------------

  revenda_query <- reactive({
    query <- getQueryString()
    # Portfólio: sem o portal que monta a URL, a revenda vem da caixa no topo.
    if (!is.null(query[["REVENDA"]])) query[["REVENDA"]] else (input$revenda_portfolio %||% "NATAL")
  })

  # user_query <- reactive({
  #   query <- getQueryString()
  #   query[["user"]]
  # })

  # Usuarios ----------------------------------------------------------------

  # Portfólio: no lugar da planilha de usuários, o visitante com todas as abas.
  usuarios <- reactive({
    data.frame(user = "visitante", abas_logistica = "fro,pde,dev,cmd", dark_mode = "N")
  })

  # usuarios <- reactive({
  #   readxl::read_excel(glue("{diretorio}usuarios.xlsx"))
  # })

  # Renderizar Logo e titulo ------------------------------------------------

  output$revenda <- renderUI({
    dashboardBrand(title = tags$b("Logístico (R)"), image = "acomp_log_www/img/marca_mini.svg", color = "secondary")
  })

  # Renderizar abas do menu ------------------------------------------------


  output$menu_frota <- renderMenu({
    if (((length(revenda_query()) == 0) || (revenda_query() %in% empresas_fro)) & session$userData$usuario %in% usuarios()[str_detect(usuarios()$abas_logistica, "fro"), ]$user) {
      menuItem("Frota",
        tabName = "id_frotas", icon = icon(NULL, class = "custom-icon-car"),
        menuSubItem("Geral", tabName = "id_geral_frota", icon = icon(NULL, class = "custom-icon-car-geral")),
        menuSubItem("Entrada de veículos", tabName = "id_entrada_frota", icon = icon(NULL, class = "custom-icon-car-entrada")),
        menuSubItem("Saída de veículos", tabName = "id_saida_frota", icon = icon(NULL, class = "custom-icon-car-saida"))
      )
    }
  })



  output$menu_pde <- renderMenu({
    if ((!is.null(revenda_query()) && (revenda_query() %in% empresas_pde)) && session$userData$usuario %in% usuarios()[str_detect(usuarios()$abas_logistica, "pde"), ]$user) {
      menuItem("PDE", tabName = "id_entrega", icon = icon(NULL, class = "custom-icon-calendario"))
    }
  })

  output$menu_devolucao <- renderMenu({
    if ((!is.null(revenda_query()) && (revenda_query() %in% empresas_dev)) && session$userData$usuario %in% usuarios()[str_detect(usuarios()$abas_logistica, "dev"), ]$user) {
      menuItem("Devoluções",
        tabName = "id_devolucao", icon = icon(NULL, class = "custom-icon-devolucoes"),
        menuSubItem("Detalhes", tabName = "id_detalhe_dev", icon = icon(NULL, class = "custom-icon-detalhe-dev")),
        menuSubItem("Caixas", tabName = "id_caixa_dev", icon = icon(NULL, class = "custom-icon-caixa-dev")),
        menuSubItem("Devoluções", tabName = "id_dev_dev", icon = icon(NULL, class = "custom-icon-dev-dev")),
        menuSubItem("Gráficos", tabName = "id_grafico_dev", icon = icon(NULL, class = "custom-icon-grafico-dev"))
      )
    }
  })

  # output$menu_romaneio = renderMenu({
  #   if((!is.null(revenda_query()) && (revenda_query() %in% empresas_rom)) && session$userData$usuario %in% usuarios()[str_detect(usuarios()$abas_logistica, "rom"),]$user){
  #     menuItem("Romaneios", tabName = "id_romaneio", icon = icon(NULL, class = "custom-icon-romaneios"))
  #   }
  # })




  output$menu_comod_log <- renderMenu({
    if ((!is.null(revenda_query()) && (revenda_query() %in% empresas_cmd) && revenda_query() != "ESPECIAL") && session$userData$usuario %in% usuarios()[str_detect(usuarios()$abas_logistica, "cmd"), ]$user) {
      menuItem("Comodatos",
        tabName = "id_comod_comodato_log", icon = icon(NULL, class = "custom-icon-comodato"),
        menuSubItem("Solicitação", tabName = "id_solicit_comodatos_log", icon = icon(NULL, class = "custom-icon-solic")),
        menuSubItem("Comodatos", tabName = "id_comod_comodatos_log", icon = icon(NULL, class = "custom-icon-comodatos")),
        # menuSubItem("Freezers", tabName = "id_comod_acomp_fre", icon = icon(NULL, class = "custom-icon-freezer")),
        # menuSubItem("Refrigeradores", tabName = "id_comod_acomp_ref", icon = icon(NULL, class = "custom-icon-geladeira")),
        menuSubItem("Vasilhames", tabName = "id_comod_sld_revendas_log", icon = icon(NULL, class = "custom-icon-vasilhame"))
      )
    } else if ((!is.null(revenda_query()) && (revenda_query() %in% empresas_cmd) && revenda_query() == "ESPECIAL") && session$userData$usuario %in% usuarios()[str_detect(usuarios()$abas_logistica, "cmd"), ]$user) {
      menuItem("Comodatos",
        tabName = "id_comod_comodato_log_2", icon = icon(NULL, class = "custom-icon-comodato"),
        menuSubItem("Solicitação", tabName = "id_solicit_comodatos_log", icon = icon(NULL, class = "custom-icon-solic")),
        menuSubItem("Comodatos", tabName = "id_comod_comodatos_log", icon = icon(NULL, class = "custom-icon-comodatos"))
      )
    }
  })

  observe({
    abas_disponiveis <- c()

    if (((length(revenda_query()) == 0) || (revenda_query() %in% empresas_fro)) &&
      session$userData$usuario %in% usuarios()[str_detect(usuarios()$abas_logistica, "fro"), ]$user) {
      abas_disponiveis <- c(abas_disponiveis, "id_geral_frota")
    }

    if (((length(revenda_query()) == 0) || (revenda_query() %in% empresas_pde)) &&
      session$userData$usuario %in% usuarios()[str_detect(usuarios()$abas_logistica, "pde"), ]$user) {
      abas_disponiveis <- c(abas_disponiveis, "id_entrega")
    }

    if (((length(revenda_query()) == 0) || (revenda_query() %in% empresas_dev)) &&
      session$userData$usuario %in% usuarios()[str_detect(usuarios()$abas_logistica, "dev"), ]$user) {
      abas_disponiveis <- c(abas_disponiveis, "id_detalhe_dev")
    }

    if (((length(revenda_query()) == 0) || (revenda_query() %in% empresas_inv)) &&
      session$userData$usuario %in% usuarios()[str_detect(usuarios()$abas_logistica, "inv"), ]$user) {
      abas_disponiveis <- c(abas_disponiveis, "id_inv_vas")
    }
    if (((length(revenda_query()) == 0) || (revenda_query() %in% empresas_cmd)) && session$userData$usuario %in% usuarios()[str_detect(usuarios()$abas_logistica, "cmd"), ]$user) {
      abas_disponiveis <- c(abas_disponiveis, "id_solicit_comodatos_log")
    }

    if (length(abas_disponiveis) > 0) {
      updateTabItems(session, "tabs", selected = abas_disponiveis[1])
    }
  })



  # Carregar páginas separadas ---------------------------------------------

  source(glue("{diretorio}pages/Frotas/pag_frotas.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Frotas/pag_frotas_entrada.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Frotas/pag_frotas_saida.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/PDE/pag_pde.R"), local = TRUE, encoding = "UTF-8")
  # source(glue("{diretorio}pages/Devolucoes/pag_dev.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Devolucoes/pag_det_dev.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Devolucoes/pag_dev_dev.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Devolucoes/pag_cx_dev.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Devolucoes/pag_graf_dev.R"), local = TRUE, encoding = "UTF-8")
  # source(glue("{diretorio}pages/Romaneios pendentes/pag_romaneios.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Comodatos/pag_clientes_inadimplentes.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Comodatos/pag_comodatos.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Comodatos/pag_comodatos_saldo.R"), local = TRUE, encoding = "UTF-8")
  # source(glue("{diretorio}pages/Comodatos/pag_refrigerador.R"), local = TRUE, encoding = "UTF-8")


  # Renderizar conteúdo com base na aba ------------------------------------

  output$conteudo_frotas <- renderUI({
    pag_frotas()
  })

  output$conteudo_frotas_entrada <- renderUI({
    pag_frotas_entrada()
  })

  output$conteudo_frotas_saida <- renderUI({
    pag_frotas_saida()
  })



  output$conteudo_entregas <- renderUI({
    pag_pde()
  })

  # output$conteudo_dev <- renderUI({
  #   pag_dev()
  # })

  output$conteudo_dev <- renderUI({
    pag_det_dev()
  })

  output$conteudo_cx_dev <- renderUI({
    pag_cx_dev()
  })

  output$conteudo_dev_dev <- renderUI({
    pag_dev_dev()
  })

  output$conteudo_graf_dev <- renderUI({
    pag_graf_dev()
  })

  # output$conteudo_rom_pen <- renderUI({
  #   pag_romaneios()
  # })





  output$conteudo_inadimplentes_log <- renderUI({
    pag_comodatos_inadimplentes()
  })

  output$conteudo_comodatos_log <- renderUI({
    pag_comodatos()
  })

  output$conteudo_comodatos_saldo_log <- renderUI({
    pag_comodatos_saldo()
  })

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
    if (session$userData$usuario %in% usuarios()[usuarios()$dark_mode == "S", ]$user) {
      c("#272c30", "#254D71", "#FFF", "#FFF", "#272c30", "#272c30")
    } else {
      c("#254D71", "#3874AB", "#FFF", "#272c30", "#fff", "#fff")
    }
  })

  # Para o tema
  output$tema_dinamico <- renderUI({
    use_theme(criar_tema(cores_reativo()))
  })

  output$dark_mode_bt <- renderUI({
    if (session$userData$usuario %in% usuarios()[usuarios()$dark_mode == "S", ]$user) {
      actionBttn("bt_dark_mode", icon = icon("sun"), style = "stretch", color = "default")
    } else {
      actionBttn("bt_dark_mode", icon = icon("moon"), style = "stretch", color = "default")
    }
  })

  observeEvent(input$bt_dark_mode, {
    # pega o data frame atual
    df <- usuarios()

    # índice do usuário
    idx <- which(df$user == session$userData$usuario)

    if (length(idx) == 1) {
      # alterna dark_mode
      df$dark_mode[idx] <- ifelse(df$dark_mode[idx] == "S", "N", "S")

      # salva de volta no arquivo
      writexl::write_xlsx(df, glue("{diretorio}usuarios.xlsx"))

      # atualiza o ícone do botão
      new_icon <- if (df$dark_mode[idx] == "S") icon("sun") else icon("moon")
      updateActionButton(session, "bt_dark_mode", icon = new_icon)
    }
  })

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

  ### Atualizacao reativa

  # output$bt_refresh_ui = renderUI({
  #
  #   if(input$tabs == "id_saida_frota"){
  #     div(
  #       actionBttn(
  #         inputId = "bt_refresh",
  #         icon = icon("sync-alt"),
  #         label = NULL,
  #         style = "stretch",
  #         color = "default"
  #       )
  #     ) %>%
  #       tagAppendAttributes(title = "Recarregar página")
  #   }
  #   else{
  #     div(style = "display: none;",
  #         actionBttn(
  #           inputId = "bt_refresh",
  #           icon = icon("sync-alt"),
  #           label = NULL,
  #           style = "stretch",
  #           color = "default"
  #         )
  #     ) %>%
  #       tagAppendAttributes(title = "Recarregar página")
  #   }
  #
  # })
  #
  # observeEvent(input$bt_refresh, {
  #   if(input$tabs == "id_saida_frota"){
  #     output$conteudo_frotas_saida <- renderUI({
  #       return(NULL)
  #     })
  #
  #     output$conteudo_frotas_saida <- renderUI({
  #       pag_frotas_saida()
  #     })
  #   }
  # })

  ### Ultima atualizacao

  output$ult_atualizacao_ui <- renderUI({
    div(
      textOutput(outputId = paste0("ult_atualizacao_", input$tabs)),
      style = glue("color: {cores_reativo()[3]}; font-size: 12px;")
    )
  })

  ### Aviso

  output$aviso_ui <- renderUI({
    req(input$tabs)
    if (str_detect(input$tabs, "frota")) {
      div(
        textOutput(outputId = paste0("aviso_", input$tabs)),
        style = glue("color: red; font-size: 26px; display: flex; align-items: center")
      )
    } else if (str_detect(input$tabs, "dev")) {
      uiOutput(outputId = paste0("aviso_", input$tabs))
    } else if (str_detect(input$tabs, "rom")) {
      uiOutput(outputId = paste0("aviso_", input$tabs))
    } else {
      NULL
    }
  })


  ### Guia de ajuda

  output$guia_ui <- renderUI({
    req(input$tabs)
    if (str_detect(input$tabs, "id_geral_frota")) {
      div(
        actionButton(paste0("bt_guia_", input$tabs), label = NULL, icon = icon("question"), status = "secondary") %>%
          tagAppendAttributes(title = "Ajuda")
      )
    } else if (str_detect(input$tabs, "id_detalhe_dev")) {
      div(
        actionButton(paste0("bt_guia_", input$tabs), label = NULL, icon = icon("question"), status = "secondary") %>%
          tagAppendAttributes(title = "Ajuda")
      )
    }
  })


  # observeEvent(input$keepalive_LOG, {
  #   # mantém conexão viva
  # }, ignoreInit = TRUE)
}

# Executar app
shinyApp(logistica_ui, logistica_server)

# runApp(
#   list(ui = logistica_ui, server = logistica_server),
#   host = "0.0.0.0",
#   port = 8080
# )

shinyApp(logistica_ui, logistica_server)
