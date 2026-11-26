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
    ),

    # App de entregas -------------------------------------------------------
    data.frame(
      id        = "app_entregas",
      titulo    = "App de entregas",
      descricao = "O motorista confirma a entrega pelo celular e o status chega ao banco de dados na hora.",
      detalhes  = "Feito para encurtar o tempo entre a confirmação da entrega e o banco de dados. O app monta cards com as entregas do motorista: distância, clima no local, rota pelo Google Maps ou Waze e contato com o vendedor (telefone ou WhatsApp). O motorista marca entregue, entregue com ocorrência ou não entregue, e o app grava a data, a hora e o motivo. Primeiro em Shiny R (um dos meus primeiros apps Shiny), depois em AppSheet sobre uma planilha Google, com scripts de automação em R levando os dados ao banco da empresa. Dados fictícios. Para entrar: motor1 ou motor3 (no Shiny, a senha é igual ao login).",
      logo      = "r.svg;appsheet.svg",
      cor       = "info",
      print     = "prints/mobile_entregas.png",
      link      = "https://marlonufpe.shinyapps.io/entregas/;https://www.appsheet.com/start/d9697071-b7a0-4d71-ae9f-a4e324abf156",
      rotulo    = "Shiny R;AppSheet",
      modo      = "externo"
    ),

    # Portfólio antigo ------------------------------------------------------
    data.frame(
      id        = "portfolio_antigo",
      titulo    = "Portfólio antigo",
      descricao = "Meu portfólio anterior, como site no Wix e como app no AppSheet.",
      detalhes  = "O site no Wix renovou um portfólio mais antigo e organizou os projetos por categoria. Junto dele nasceu uma versão em app no AppSheet: um texto de apresentação leva ao menu de projetos, com os detalhes de cada um separados por categoria, e os cards são gerados a partir de uma planilha Google atualizada.",
      logo      = "appsheet.svg",
      cor       = "info",
      print     = "prints/mobile_portfolio_appsheet.png",
      link      = "https://marlonheslypro.wixsite.com/portfolio/inicio;https://www.appsheet.com/start/a5cc10cd-9090-4c3c-9883-788712d4da13",
      rotulo    = "Site (Wix);App (AppSheet)",
      modo      = "externo"
    )
  )

  # UI ----------------------------------------------------------------------

  fluidPage(
    h2("Apps e Mobile"),
    faixa_etapas(etapas, "Etapas de um app"),
    fluidRow(card_projeto(projetos, "comodato_motorista")),
    fluidRow(card_projeto(projetos, "app_entregas")),
    fluidRow(card_projeto(projetos, "portfolio_antigo"))
  )

}
