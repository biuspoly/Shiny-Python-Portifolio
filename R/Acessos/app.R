suppressPackageStartupMessages({
  library(shiny)
  library(bs4Dash)
  library(shinyWidgets)
  library(reactable)
  library(reactable.extras)
  library(ggplot2)
  library(plotly)
  library(dplyr)
  library(lubridate)
  library(glue)
  library(shinycssloaders)
  library(shinyalert)
  library(shinyFeedback)
  library(stringr)
  library(jsonlite)
})

# Diretório ---------------------------------------------------------------

diretorio <- ""

# Cores -------------------------------------------------------------------

cores_iniciais <- c("#2E75B6", "#5B9BD5", "#FFF", "#272c30", "#fff", "#fff")

# UI ----------------------------------------------------------------------

logs_ui <- dashboardPage(
  help = NULL,
  header = dashboardHeader(
    title = dashboardBrand(
      title = tags$b("Logs & Acesso"),
      image = "img/marca.svg",
      color = "secondary"
    ),
    status = "light",
    sidebarIcon = tagList(
      tags$i(class = "fa fa-angle-left sidebar-toggle-left"),
      tags$i(class = "fa fa-angle-right sidebar-toggle-right")
    )
  ),
  sidebar = dashboardSidebar(
    width = 280,
    collapsed = FALSE,
    minified = TRUE,
    sidebarMenu(
      id = "tabs",
      menuItem(
        "Gerenciamento",
        icon = icon("users-cog"),
        menuSubItem("Usuários", tabName = "id_logs_usuarios", icon = icon("user")),
        menuSubItem("Permissões", tabName = "id_logs_permissoes", icon = icon("lock"))
      ),
      menuItem(
        "Visão Geral",
        tabName = "id_logs_visao_geral",
        icon    = icon("chart-line")
      ),
      menuItem(
        "Acessos",
        icon = icon("key"),
        menuSubItem("Log Dash", tabName = "id_logs_acessos", icon = icon("list-alt"))
      )
    )
  ),
  body = dashboardBody(
    tags$head(
      tags$script(HTML("
        setInterval(function() {
          Shiny.setInputValue('keepalive_LOGS', Date.now(), {priority: 'event'});
        }, 1000);
      "))
    ),
    includeCSS(glue("{diretorio}www/style_geral.css")),
    useShinyFeedback(),
    useSweetAlert(),
    reactable_extras_dependency(),
    tabItems(
      tabItem(
        tabName = "id_logs_visao_geral",
        withSpinner(uiOutput("conteudo_logs_visao_geral"), type = 4, color = cores_iniciais[2])
      ),
      tabItem(
        tabName = "id_logs_acessos",
        withSpinner(uiOutput("conteudo_logs_acessos"), type = 4, color = cores_iniciais[2])
      ),
      tabItem(
        tabName = "id_logs_usuarios",
        withSpinner(uiOutput("conteudo_logs_usuarios"), type = 4, color = cores_iniciais[2])
      ),
      tabItem(
        tabName = "id_logs_permissoes",
        withSpinner(uiOutput("conteudo_logs_permissoes"), type = 4, color = cores_iniciais[2])
      )
    )
  ),
  title = "Logs & Gerenciamento de Acesso - Portfólio Marlon Amaral"
)

# Server ------------------------------------------------------------------

logs_server <- function(input, output, session) {
  # Carregar páginas --------------------------------------------------------

  source(glue("{diretorio}pages/Visao Geral/pag_visao_geral.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Acessos Dash/pag_acessos.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Acessos Dash/pag_usuarios_dash.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Acessos Dash/pag_usuarios.R"), local = TRUE, encoding = "UTF-8")

  # Renderizar conteúdo -----------------------------------------------------

  output$conteudo_logs_visao_geral <- renderUI({
    pag_visao_geral()
  })
  output$conteudo_logs_acessos <- renderUI({
    pag_acessos()
  })
  output$conteudo_logs_usuarios <- renderUI({
    pag_usuarios_dash()
  })
  output$conteudo_logs_permissoes <- renderUI({
    pag_usuarios()
  })
}

shinyApp(logs_ui, logs_server)
