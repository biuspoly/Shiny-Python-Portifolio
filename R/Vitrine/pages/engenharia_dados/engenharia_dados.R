engenharia_dados = function(){

  # DADOS ------------------------------------------------------------------

  # Etapas do processo (faixa antes dos cards)
  etapas = data.frame(
    titulo    = c("Fontes", "Extração", "Transformação", "Entrega"),
    descricao = c("ERP, MySQL e APIs.", "Camada bruta.", "Tabelas dos apps.", "Parquet para os painéis."),
    icone     = c("database", "download", "gears", "table"),
    cor       = c("primary", "purple", "teal", "orange")
  )

  github = "https://github.com/biuspoly/"

  # Valores de cada versão separados por ";"
  projetos = data.frame(
    id = c(
      "pipeline", "webhooks"
    ),
    titulo = c(
      "Pipeline de dados", "Webhooks e APIs com plumber"
    ),
    descricao = c(
      "Rotina da madrugada que extrai do ERP, monta a camada bruta e atualiza as tabelas dos painéis.",
      "API em R que recebe webhooks (Clicksign, GitHub) e expõe consultas de veículos."
    ),
    detalhes = c(
      "Duas versões. Em R (escrita sem IA): camada bruta, tabelas dos apps Shiny em R e consultas diretas ao ERP. Em Python (com ajuda do Claude): orquestração com Prefect, camada bruta, camada intermediária e os Parquet dos apps Shiny for Python, com o aviso de prazo de comodato ao meio-dia. As duas rodam aqui sobre Parquet fictício no lugar do ERP e do MySQL.",
      "Rotas plumber: webhook da Clicksign (contrato assinado atualiza o status do comodato), webhook do GitHub, consulta FIPE e rastreio de veículos."
    ),
    logo = c(
      "r.svg;python.svg", "r.svg"
    ),
    cor = c(
      "info", "info"
    ),
    print = c(
      "prints/repo_pipeline_dados_python.png", "prints/repo_webhooks_plumber.png"
    ),
    link = c(
      paste0(github, "pipeline-dados-r;", github, "pipeline-dados-python"),
      paste0(github, "webhooks-plumber")
    ),
    rotulo = c(
      "Versão R;Versão Python", ""
    ),
    modo = c(
      "repo", "repo"
    )
  )

  # UI ----------------------------------------------------------------------

  fluidPage(
    h2("Engenharia de Dados"),
    faixa_etapas(etapas, "Estrutura de uma pipeline"),
    fluidRow(card_projeto(projetos, "pipeline")),
    fluidRow(card_projeto(projetos, "webhooks"))
  )

}
