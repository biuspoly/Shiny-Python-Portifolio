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
    # Menu por área; subabas só onde há tipos diferentes de entrega.
    # Um projeto com várias linguagens/versões é um card só, com um botão por versão.
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
        menuSubItem("Painéis de gestão", tabName = "id_analise_dados_gestao",  icon = icon("gauge-high")),
        menuSubItem("Power BI",          tabName = "id_analise_dados_powerbi", icon = tags$i(class = "nav-icon logo-powerbi")),
        menuSubItem("Excel",             tabName = "id_analise_dados_excel",   icon = tags$i(class = "nav-icon logo-excel"))
      ),
      menuItem(
        "Ciência de Dados",
        tabName = "id_ciencia_dados",
        icon = icon("flask")
      ),
      menuItem(
        "Engenharia de Dados",
        tabName = "id_engenharia_dados",
        icon = icon("project-diagram")
      ),
      menuItem(
        "Automações",
        tabName = "id_automacoes",
        icon = icon("gears")
      ),
      menuItem(
        "Apps e Mobile",
        tabName = "id_apps_mobile",
        icon = icon("mobile-screen")
      ),
      menuItem(
        "Dev & Open Source",
        icon = icon("code"),
        menuSubItem("Pacotes", tabName = "id_dev_open_source_pacotes", icon = icon("box-open")),
        menuSubItem("Jogos",   tabName = "id_dev_open_source_jogos",   icon = icon("gamepad"))
      ),
      menuItem(
        "Sobre Mim",
        tabName = "id_sobre_mim",
        icon = icon("user")
      )
    )
  ),
  body = dashboardBody(
    tags$head(tags$link(rel = "stylesheet", href = "estilo.css?v=15")),

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
        tabName = "id_analise_dados_gestao",
        uiOutput("conteudo_analise_dados_gestao")
      ),
      tabItem(
        tabName = "id_analise_dados_powerbi",
        uiOutput("conteudo_analise_dados_powerbi")
      ),
      tabItem(
        tabName = "id_analise_dados_excel",
        uiOutput("conteudo_analise_dados_excel")
      ),
      tabItem(
        tabName = "id_ciencia_dados",
        uiOutput("conteudo_ciencia_dados")
      ),
      tabItem(
        tabName = "id_engenharia_dados",
        uiOutput("conteudo_engenharia_dados")
      ),
      tabItem(
        tabName = "id_automacoes",
        uiOutput("conteudo_automacoes")
      ),
      tabItem(
        tabName = "id_apps_mobile",
        uiOutput("conteudo_apps_mobile")
      ),
      tabItem(
        tabName = "id_dev_open_source_pacotes",
        uiOutput("conteudo_dev_open_source_pacotes")
      ),
      tabItem(
        tabName = "id_dev_open_source_jogos",
        uiOutput("conteudo_dev_open_source_jogos")
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

  output$conteudo_analise_dados_gestao <- renderUI({
    analise_dados("gestao")
  })

  output$conteudo_analise_dados_powerbi <- renderUI({
    analise_dados("powerbi")
  })

  output$conteudo_analise_dados_excel <- renderUI({
    analise_dados("excel")
  })

  output$conteudo_ciencia_dados <- renderUI({
    ciencia_dados()
  })

  output$conteudo_engenharia_dados <- renderUI({
    engenharia_dados()
  })

  output$conteudo_automacoes <- renderUI({
    automacoes()
  })

  output$conteudo_apps_mobile <- renderUI({
    apps_mobile()
  })

  output$conteudo_dev_open_source_pacotes <- renderUI({
    dev_open_source("pacotes")
  })

  output$conteudo_dev_open_source_jogos <- renderUI({
    dev_open_source("jogos")
  })

  output$conteudo_sobre_mim <- renderUI({
    sobre_mim()
  })

}

shinyApp(ui, server)
