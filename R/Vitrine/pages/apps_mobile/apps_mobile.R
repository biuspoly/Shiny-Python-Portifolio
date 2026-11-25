apps_mobile = function(){

  # DADOS ------------------------------------------------------------------

  # Etapas do processo (faixa antes dos cards)
  etapas = data.frame(
    titulo    = c("Dados", "App", "Uso em campo", "Retorno"),
    descricao = c("Banco ou planilha.", "AppSheet, shinyMobile e Flet.", "Motorista na entrega.", "Status atualizado."),
    icone     = c("database", "mobile-screen", "truck", "rotate"),
    cor       = c("primary", "purple", "teal", "orange")
  )

  github = "https://github.com/biuspoly/"

  # Um bloco por projeto; valores de cada versão separados por ";"
  # ("#" = versão ainda sem endereço)
  projetos = rbind(

    # Comodato do motorista -------------------------------------------------
    data.frame(
      id        = "comodato_motorista",
      titulo    = "Comodato do motorista",
      descricao = "App para o motorista consultar, na entrega, os comodatos pendentes de assinatura.",
      detalhes  = "Três versões do mesmo app. Primeiro em AppSheet, sobre uma planilha Google que uma automação em R mantinha atualizada. Depois em R com shinyMobile (descontinuado; o código fica no repositório, com dados fictícios). A próxima é em Python com Flet, feita com ajuda do Claude.",
      logo      = "appsheet.svg;r.svg;python.svg",
      cor       = "info",
      print     = "prints/mobile_comodato_r.png",
      link      = paste0(github, "comodato-appsheet;", github, "comodato-mobile;#"),
      rotulo    = "AppSheet;shinyMobile;Flet",
      modo      = "repo;repo;em_breve"
    )
  )

  # UI ----------------------------------------------------------------------

  fluidPage(
    h2("Apps e Mobile"),
    faixa_etapas(etapas, "Etapas de um app"),
    fluidRow(card_projeto(projetos, "comodato_motorista"))
  )

}
