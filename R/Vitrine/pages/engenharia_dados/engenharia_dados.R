engenharia_dados = function(item){

  # DADOS ------------------------------------------------------------------

  # Etapas do processo (faixa antes dos cards)
  etapas = data.frame(
    titulo    = c("Fontes", "Extração", "Transformação", "Entrega"),
    descricao = c("ERP, MySQL e APIs.", "Camada bruta.", "Tabelas dos apps.", "Parquet para os painéis."),
    icone     = c("database", "download", "gears", "table"),
    cor       = c("primary", "purple", "teal", "orange")
  )

  github = "https://github.com/biuspoly/"

  projetos = data.frame(
    id = c(
      "r_pipeline", "r_webhooks",
      "py_pipeline"
    ),
    titulo = c(
      "Pipeline de dados em R", "Webhooks e APIs com plumber",
      "Pipeline de dados em Python"
    ),
    descricao = c(
      "Rotina da madrugada que extrai do ERP, monta a camada bruta e atualiza as tabelas dos apps Shiny em R.",
      "API em R que recebe webhooks (Clicksign, GitHub) e expõe consultas de veículos.",
      "Orquestração da madrugada: camada bruta, camada intermediária e os Parquet dos apps Shiny for Python."
    ),
    detalhes = c(
      "Três etapas: camada bruta (ERP para tabelas de clientes, vendas, pedidos, romaneios e comodatos), tabelas dos apps (devoluções, romaneios pendentes, comodatos, pedidos cancelados) e consultas diretas ao ERP (PDE, último romaneio, FIPE). Escrita sem IA. Aqui roda sobre Parquet fictício no lugar do ERP e do MySQL.",
      "Rotas plumber: webhook da Clicksign (contrato assinado atualiza o status do comodato), webhook do GitHub, consulta FIPE e rastreio de veículos.",
      "Alimenta os painéis do portfólio em Shiny for Python. Roda de madrugada, com o aviso de prazo de comodato ao meio-dia. Aqui roda sobre Parquet fictício no lugar do ERP e do MySQL."
    ),
    logo = c(
      "r.svg", "r.svg",
      "python.svg"
    ),
    cor = c(
      "info", "info",
      "primary"
    ),
    print = c(
      "prints/repo_pipeline_dados_r.png", "prints/repo_webhooks_plumber.png",
      "prints/repo_pipeline_dados_python.png"
    ),
    link = c(
      paste0(github, "pipeline-dados-r"), paste0(github, "webhooks-plumber"),
      paste0(github, "pipeline-dados-python")
    ),
    rotulo = c(
      "", "",
      ""
    ),
    modo = c(
      "repo", "repo",
      "repo"
    )
  )

  # UI ----------------------------------------------------------------------

  if (item == "r") {

    fluidPage(
      h2("Engenharia de Dados em R"),
      faixa_etapas(etapas, "Estrutura de uma pipeline"),
      fluidRow(card_projeto(projetos, "r_pipeline")),
      fluidRow(card_projeto(projetos, "r_webhooks"))
    )

  } else if (item == "python") {

    fluidPage(
      h2("Engenharia de Dados em Python"),
      faixa_etapas(etapas, "Estrutura de uma pipeline"),
      fluidRow(card_projeto(projetos, "py_pipeline"))
    )

  }

}
