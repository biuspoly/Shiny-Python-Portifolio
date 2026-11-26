visao_geral = function(){

  # DADOS ------------------------------------------------------------------

  github = "https://github.com/biuspoly/"
  site_portfolio = "https://biuspoly.github.io/shiny-portfolio/"

  # Projetos em destaque: um bloco por card; selos separados por ";"
  destaques = rbind(

    # Acompanhamento Comercial ----------------------------------------------
    data.frame(
      id        = "comercial_py",
      titulo    = "Acompanhamento Comercial",
      descricao = "Diário de vendas, curva ABC de clientes e mapa comercial.",
      selos     = "Shiny Python;Polars",
      cor       = "primary",
      print     = "prints/shiny_py_comercial.webp",
      link      = paste0(site_portfolio, "comercial/"),
      modo      = "app"
    ),

    # Acompanhamento Logístico ----------------------------------------------
    data.frame(
      id        = "logistico_r",
      titulo    = "Acompanhamento Logístico",
      descricao = "Frota, planilha de entregas, devoluções e comodato, na versão original em R.",
      selos     = "Shiny R;DuckDB",
      cor       = "info",
      print     = "prints/shiny_r_logistico.webp",
      link      = paste0(site_portfolio, "r/logistico/"),
      modo      = "app"
    ),

    # Congestionamento no TRF5 ----------------------------------------------
    data.frame(
      id        = "trf5",
      titulo    = "Congestionamento no TRF5",
      descricao = "Estudo de taxa de congestionamento e força de trabalho até 2021.",
      selos     = "R Markdown;Estatística",
      cor       = "success",
      print     = "prints/ufpe.png",
      link      = "https://rstudio-pubs-static.s3.amazonaws.com/1018240_6c09a7b337324a8cbedadc9ffd9bc670.html",
      modo      = "externo"
    ),

    # Pipelines de dados ----------------------------------------------------
    data.frame(
      id        = "pipelines",
      titulo    = "Pipelines de dados",
      descricao = "Extração do ERP, camada bruta e tabelas dos apps, rodando de madrugada.",
      selos     = "R;Python",
      cor       = "warning",
      print     = "prints/repo_pipeline_dados_python.png",
      link      = paste0(github, "pipeline-dados-python"),
      modo      = "repo"
    ),

    # Comodato Mobile -------------------------------------------------------
    data.frame(
      id        = "comodato_mobile",
      titulo    = "Comodato Mobile",
      descricao = "App do motorista para consultar comodatos pendentes de assinatura.",
      selos     = "shinyMobile",
      cor       = "info",
      print     = "prints/mobile_comodato_r.png",
      link      = paste0(github, "comodato-mobile"),
      modo      = "repo"
    ),

    # RNFe ------------------------------------------------------------------
    data.frame(
      id        = "rnfe",
      titulo    = "RNFe",
      descricao = "Documentos fiscais eletrônicos em R: XML, assinatura, SEFAZ e PDFs.",
      selos     = "Pacote R",
      cor       = "primary",
      print     = "prints/repo_rnfe.png",
      link      = paste0(github, "RNFe"),
      modo      = "repo"
    )
  )

  # SERVER ------------------------------------------------------------------

  # Botão "Sobre mim" leva para a aba Sobre Mim
  observeEvent(input$bt_visao_geral_sobre_mim, {
    updateTabItems(session, "tabs", selected = "id_sobre_mim")
  })

  # UI ----------------------------------------------------------------------

  fluidPage(
    h2("Meu portfólio"),

    # Apresentação
    fluidRow(
      callout(
        title = "Marlon Hesly",
        status = "info",
        width = 12,
        elevation = 2,
        fluidRow(
          column(
            width = 9,
            h5("Análise de dados · Estatística · Ciência de dados"),
            p("Painéis, pipelines, automações e aplicações com dados, em R e Python.")
          ),
          column(
            width = 3,
            align = "right",
            actionButton(
              "bt_visao_geral_sobre_mim",
              label = "Sobre mim",
              icon = icon("user"),
              status = "primary"
            )
          )
        )
      )
    ),

    # Áreas (cada bloco abre a seção do menu)
    fluidRow(
      infoBox(
        title = "Análise de Dados",
        value = "Painéis em Shiny R e Python",
        icon = icon("chart-column"),
        color = "primary",
        width = 4,
        elevation = 2,
        tabName = "id_analise_dados_gestao"
      ),
      infoBox(
        title = "Ciência de Dados",
        value = "Estatística e modelagem",
        icon = icon("flask"),
        color = "teal",
        width = 4,
        elevation = 2,
        tabName = "id_ciencia_dados"
      ),
      infoBox(
        title = "Engenharia de Dados",
        value = "Pipelines e APIs",
        icon = icon("project-diagram"),
        color = "indigo",
        width = 4,
        elevation = 2,
        tabName = "id_engenharia_dados"
      )
    ),
    fluidRow(
      infoBox(
        title = "Automações",
        value = "R, Python e AppSheet",
        icon = icon("gears"),
        color = "purple",
        width = 4,
        elevation = 2,
        tabName = "id_automacoes"
      ),
      infoBox(
        title = "Apps e Mobile",
        value = "Aplicações no celular",
        icon = icon("mobile-screen"),
        color = "orange",
        width = 4,
        elevation = 2,
        tabName = "id_apps_mobile"
      ),
      infoBox(
        title = "Dev & Open Source",
        value = "Pacotes e projetos abertos",
        icon = icon("code"),
        color = "navy",
        width = 4,
        elevation = 2,
        tabName = "id_dev_open_source_pacotes"
      )
    ),

    # Projetos em destaque
    h3("Projetos em destaque", class = "mt-3 mb-3"),
    fluidRow(
      card_destaque(destaques, "comercial_py"),
      card_destaque(destaques, "logistico_r"),
      card_destaque(destaques, "trf5")
    ),
    fluidRow(
      card_destaque(destaques, "pipelines"),
      card_destaque(destaques, "comodato_mobile"),
      card_destaque(destaques, "rnfe")
    ),

    # Próximos projetos
    fluidRow(
      callout(
        title = "Próximos projetos",
        status = "warning",
        width = 12,
        elevation = 2,
        p("Painéis em Power BI e Excel, o app do motorista em Python (Flet) e o jogo Rivals Avenue, na Godot.")
      )
    )
  )

}
