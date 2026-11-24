library(shiny)
library(bs4Dash)
library(htmltools)
library(fresh)

# Tema (cores) -------------------------------------------------------------
# carregado aqui em cima porque a UI usa o tema.
# Com o www/tema.css pronto (o CI gera com core/gerar_tema.R antes de publicar), o app só aponta para
# ele: compilar o tema a cada abertura deixava o Shinylive mais lento. Sem o arquivo (rodando local),
# o tema é compilado na hora, a partir do core/tema.R.

if (file.exists("www/tema.css")) {
  tema = "tema.css"
} else {
  source("core/tema.R", local = TRUE, encoding = "UTF-8")
}

# Links do canto superior direito ------------------------------------------

link_github   = "https://github.com/biuspoly"
link_linkedin = "https://www.linkedin.com/in/marlon-hesly/"   # trocar pelo seu perfil

ui = dashboardPage(
  freshTheme = tema,
  header = dashboardHeader(
    skin = "dark",          # texto branco
    status = "primary",     # barra superior azul
    title = dashboardBrand(title = "Portfólio", color = "primary"),
    rightUi = tagList(
      tags$li(
        class = "nav-item dropdown",
        tags$a(class = "nav-link", href = link_github, target = "_blank", icon("github"))
      ),
      tags$li(
        class = "nav-item dropdown",
        tags$a(class = "nav-link", href = link_linkedin, target = "_blank", icon("linkedin"))
      )
    )
  ),
  sidebar = dashboardSidebar(
    skin = "dark",          # menu escuro, padrão do AdminLTE
    status = "primary",     # item ativo em azul
    elevation = 4,
    sidebarUserPanel(
      name = HTML("Marlon Hesly <br> Analista de Dados/Estatístico"),
      image = ""
    ),
    sidebarMenu(
      id = "tabs",
      sidebarHeader(
        "Navegação"
      ),
      menuItem(
        "Visão Geral",
        tabName = "id_visao_geral",
        icon = icon("house")
      ),
      menuItem(
        "Análise de Dados",
        icon = icon("chart-column"),
        menuSubItem("Power BI", tabName = "id_analise_dados_powerbi", icon = tags$i(class = "nav-icon logo-powerbi")),
        menuSubItem("R",        tabName = "id_analise_dados_r",       icon = tags$i(class = "nav-icon logo-r")),
        menuSubItem("Excel",    tabName = "id_analise_dados_excel",   icon = tags$i(class = "nav-icon logo-excel")),
        menuSubItem("Python",   tabName = "id_analise_dados_python",  icon = tags$i(class = "nav-icon logo-python"))
      ),
      menuItem(
        "Ciência de Dados",
        tabName = "id_ciencia_dados",
        icon = icon("flask")
      ),
      menuItem(
        "Engenharia de Dados",
        icon = icon("project-diagram"),
        menuSubItem("R",        tabName = "id_engenharia_dados_r",      icon = tags$i(class = "nav-icon logo-r")),
        menuSubItem("Python",   tabName = "id_engenharia_dados_python", icon = tags$i(class = "nav-icon logo-python"))
      ),
      menuItem(
        "Automações",
        icon = icon("gears"),
        menuSubItem("R",        tabName = "id_automacoes_r",        icon = tags$i(class = "nav-icon logo-r")),
        menuSubItem("Python",   tabName = "id_automacoes_python",   icon = tags$i(class = "nav-icon logo-python")),
        menuSubItem("AppSheet", tabName = "id_automacoes_appsheet", icon = tags$i(class = "nav-icon logo-appsheet"))
      ),
      menuItem(
        "Apps e Mobile",
        icon = icon("mobile-screen"),
        menuSubItem("Shiny R",       tabName = "id_apps_mobile_shiny_r",      icon = tags$i(class = "nav-icon logo-shiny")),
        menuSubItem("Shiny Python",   tabName = "id_apps_mobile_shiny_python", icon = tags$i(class = "nav-icon logo-shiny"))
      ),
      menuItem(
        "Dev & Open Source",
        icon = icon("code"),
        menuSubItem("R",        tabName = "id_dev_open_source_r",      icon = tags$i(class = "nav-icon logo-r")),
        menuSubItem("Python",   tabName = "id_dev_open_source_python", icon = tags$i(class = "nav-icon logo-python")),
        menuSubItem("Godot",    tabName = "id_dev_open_source_godot",  icon = tags$i(class = "nav-icon logo-godot")),
        menuSubItem("C++",      tabName = "id_dev_open_source_cpp",    icon = tags$i(class = "nav-icon logo-cpp"))
      ),
      menuItem(
        "Sobre Mim",
        tabName = "id_sobre_mim",
        icon = icon("user")
      )
    )
  ),
  body = dashboardBody(
    tags$head(tags$link(rel = "stylesheet", href = "estilo.css?v=14")),

    # No celular o menu lateral abre POR CIMA da página e não fecha sozinho: depois de tocar num item,
    # a página trocava atrás do menu e parecia que só a Visão Geral existia. Fecha o menu após o toque.
    tags$script(HTML("
      $(document).on('click', '.main-sidebar a.nav-link[data-toggle=\\'tab\\']', function () {
        if (window.innerWidth < 992) {
          $('[data-widget=\\'pushmenu\\']').PushMenu('collapse');
        }
      });
    ")),

    tabItems(
      tabItem(
        tabName = "id_visao_geral",
        uiOutput("conteudo_visao_geral")
      ),
      tabItem(
        tabName = "id_analise_dados_powerbi",
        uiOutput("conteudo_analise_dados_powerbi")
      ),
      tabItem(
        tabName = "id_analise_dados_r",
        uiOutput("conteudo_analise_dados_r")
      ),
      tabItem(
        tabName = "id_analise_dados_excel",
        uiOutput("conteudo_analise_dados_excel")
      ),
      tabItem(
        tabName = "id_analise_dados_python",
        uiOutput("conteudo_analise_dados_python")
      ),
      tabItem(
        tabName = "id_ciencia_dados",
        uiOutput("conteudo_ciencia_dados")
      ),
      tabItem(
        tabName = "id_engenharia_dados_r",
        uiOutput("conteudo_engenharia_dados_r")
      ),
      tabItem(
        tabName = "id_engenharia_dados_python",
        uiOutput("conteudo_engenharia_dados_python")
      ),
      tabItem(
        tabName = "id_automacoes_r",
        uiOutput("conteudo_automacoes_r")
      ),
      tabItem(
        tabName = "id_automacoes_python",
        uiOutput("conteudo_automacoes_python")
      ),
      tabItem(
        tabName = "id_automacoes_appsheet",
        uiOutput("conteudo_automacoes_appsheet")
      ),
      tabItem(
        tabName = "id_apps_mobile_shiny_r",
        uiOutput("conteudo_apps_mobile_shiny_r")
      ),
      tabItem(
        tabName = "id_apps_mobile_shiny_python",
        uiOutput("conteudo_apps_mobile_shiny_python")
      ),
      tabItem(
        tabName = "id_dev_open_source_r",
        uiOutput("conteudo_dev_open_source_r")
      ),
      tabItem(
        tabName = "id_dev_open_source_python",
        uiOutput("conteudo_dev_open_source_python")
      ),
      tabItem(
        tabName = "id_dev_open_source_godot",
        uiOutput("conteudo_dev_open_source_godot")
      ),
      tabItem(
        tabName = "id_dev_open_source_cpp",
        uiOutput("conteudo_dev_open_source_cpp")
      ),
      tabItem(
        tabName = "id_sobre_mim",
        uiOutput("conteudo_sobre_mim")
      )
    )
  ),
  help = NULL
)

server = function(input, output, session){

  # Carregar páginas separadas ---------------------------------------------

  source("core/card_projeto.R", local = TRUE, encoding = "UTF-8")
  source("core/card_destaque.R", local = TRUE, encoding = "UTF-8")
  source("core/faixa_etapas.R", local = TRUE, encoding = "UTF-8")
  source("pages/visao_geral/visao_geral.R", local = TRUE, encoding = "UTF-8")
  source("pages/analise_dados/analise_dados.R", local = TRUE, encoding = "UTF-8")
  source("pages/ciencia_dados/ciencia_dados.R", local = TRUE, encoding = "UTF-8")
  source("pages/engenharia_dados/engenharia_dados.R", local = TRUE, encoding = "UTF-8")
  source("pages/automacoes/automacoes.R", local = TRUE, encoding = "UTF-8")
  source("pages/apps_mobile/apps_mobile.R", local = TRUE, encoding = "UTF-8")
  source("pages/dev_open_source/dev_open_source.R", local = TRUE, encoding = "UTF-8")
  source("pages/sobre_mim/sobre_mim.R", local = TRUE, encoding = "UTF-8")

  # Renderizar conteúdo com base na aba ------------------------------------

  output$conteudo_visao_geral <- renderUI({
    visao_geral()
  })

  output$conteudo_analise_dados_powerbi <- renderUI({
    analise_dados("powerbi")
  })

  output$conteudo_analise_dados_r <- renderUI({
    analise_dados("r")
  })

  output$conteudo_analise_dados_excel <- renderUI({
    analise_dados("excel")
  })

  output$conteudo_analise_dados_python <- renderUI({
    analise_dados("python")
  })

  output$conteudo_ciencia_dados <- renderUI({
    ciencia_dados()
  })

  output$conteudo_engenharia_dados_r <- renderUI({
    engenharia_dados("r")
  })

  output$conteudo_engenharia_dados_python <- renderUI({
    engenharia_dados("python")
  })

  output$conteudo_automacoes_r <- renderUI({
    automacoes("r")
  })

  output$conteudo_automacoes_python <- renderUI({
    automacoes("python")
  })

  output$conteudo_automacoes_appsheet <- renderUI({
    automacoes("appsheet")
  })

  output$conteudo_apps_mobile_shiny_r <- renderUI({
    apps_mobile("shiny_r")
  })

  output$conteudo_apps_mobile_shiny_python <- renderUI({
    apps_mobile("shiny_python")
  })

  output$conteudo_dev_open_source_r <- renderUI({
    dev_open_source("r")
  })

  output$conteudo_dev_open_source_python <- renderUI({
    dev_open_source("python")
  })

  output$conteudo_dev_open_source_godot <- renderUI({
    dev_open_source("godot")
  })

  output$conteudo_dev_open_source_cpp <- renderUI({
    dev_open_source("cpp")
  })

  output$conteudo_sobre_mim <- renderUI({
    sobre_mim()
  })

}

shinyApp(ui, server)
