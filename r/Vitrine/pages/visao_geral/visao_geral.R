visao_geral = function(){

  # DADOS ------------------------------------------------------------------

  github = "https://github.com/biuspoly/"
  # Apps no Posit Connect Cloud: abrem em nova aba (o Shinylive não deixa abrir num iframe).
  posit_r  = "https://01a2190a-f130-f119-72e4-d16f0322add0.share.connect.posit.cloud/"
  posit_py = "https://01a2190b-b942-a96c-d03c-a67adef5d830.share.connect.posit.cloud/"
  site_portfolio = "https://biuspoly.github.io/Shiny-Python-Portifolio/"

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
      link      = paste0(posit_py, "comercial/"),
      modo      = "externo"
    ),

    # Acompanhamento Logístico ----------------------------------------------
    data.frame(
      id        = "logistico_r",
      titulo    = "Acompanhamento Logístico",
      descricao = "Frota, planilha de entregas, devoluções e comodato, na versão original em R.",
      selos     = "Shiny R;DuckDB",
      cor       = "info",
      print     = "prints/shiny_r_logistico.webp",
      link      = paste0(posit_r, "?painel=logistico"),
      modo      = "externo"
    ),

    # TCC: gráficos de controle no TRF5 -------------------------------------
    data.frame(
      id        = "tcc",
      titulo    = "TCC: gráficos de controle no TRF5",
      descricao = "Gráficos de controle nos indicadores de eficiência do TRF5.",
      selos     = "Estatística;R Markdown",
      cor       = "success",
      print     = "prints/ufpe.png",
      link      = "https://repositorio.ufpe.br/handle/123456789/47526",
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
      card_destaque(destaques, "tcc")
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
