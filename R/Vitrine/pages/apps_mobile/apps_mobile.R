apps_mobile = function(item){

  # DADOS ------------------------------------------------------------------

  # Etapas do processo (faixa antes dos cards)
  etapas = data.frame(
    titulo    = c("Dados", "App", "Uso em campo", "Retorno"),
    descricao = c("Banco ou planilha.", "shinyMobile e Flet.", "Motorista na entrega.", "Status atualizado."),
    icone     = c("database", "mobile-screen", "truck", "rotate"),
    cor       = c("primary", "purple", "teal", "orange")
  )

  github = "https://github.com/biuspoly/"

  projetos = data.frame(
    id = c(
      "shiny_r_comodato_mobile",
      "shiny_py_comodato_mobile"
    ),
    titulo = c(
      "Comodato Mobile (shinyMobile)",
      "Comodato Mobile (Python)"
    ),
    descricao = c(
      "App do motorista: consulta, na entrega, os comodatos pendentes de assinatura.",
      "O mesmo app do motorista, portado para Python."
    ),
    detalhes = c(
      "Feito em R com shinyMobile. Mostra os comodatos pendentes do motorista, os detalhes de cada um e a busca por cliente, CEV ou nota. App descontinuado; o código fica no repositório, com dados fictícios.",
      "Versão em Python do app do motorista. Repositório ainda privado."
    ),
    logo = c(
      "shiny.svg",
      "shiny.svg"
    ),
    cor = c(
      "info",
      "primary"
    ),
    print = c(
      "prints/mobile_comodato_r.png",
      "prints/mobile_comodato_py.png"
    ),
    link = c(
      paste0(github, "comodato-mobile"),
      ""
    ),
    rotulo = c(
      "",
      ""
    ),
    modo = c(
      "repo",
      "em_breve"
    )
  )

  # UI ----------------------------------------------------------------------

  if (item == "shiny_r") {

    fluidPage(
      h2("Apps mobile com Shiny R"),
      faixa_etapas(etapas, "Etapas de um app"),
      fluidRow(card_projeto(projetos, "shiny_r_comodato_mobile"))
    )

  } else if (item == "shiny_python") {

    fluidPage(
      h2("Apps mobile com Python"),
      faixa_etapas(etapas, "Etapas de um app"),
      fluidRow(card_projeto(projetos, "shiny_py_comodato_mobile"))
    )

  }

}
