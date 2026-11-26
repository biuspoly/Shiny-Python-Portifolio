ciencia_dados = function(){

  # DADOS ------------------------------------------------------------------

  # Etapas do processo (faixa antes dos cards)
  etapas = data.frame(
    titulo    = c("Pergunta", "Dados", "Análise", "Relatório"),
    descricao = c("Problema a responder.", "Coleta e limpeza.", "Estatística e modelos.", "R Markdown e gráficos."),
    icone     = c("circle-question", "database", "flask", "file-lines"),
    cor       = c("primary", "purple", "teal", "orange")
  )

  # Um bloco por projeto
  projetos = rbind(

    # Congestionamento no TRF5 ----------------------------------------------
    data.frame(
      id        = "rmd_trf5",
      titulo    = "Taxa de congestionamento e força de trabalho no TRF5",
      descricao = "Um breve estudo sobre taxa de congestionamento e força de trabalho no TRF5 até 2021, em R Markdown.",
      detalhes  = "Trabalho acadêmico da UFPE publicado no RPubs (rpubs.com/marlonama/1018240).",
      logo      = "r.svg",
      cor       = "info",
      print     = "prints/ufpe.png",
      # endereço do documento que o RPubs mostra por dentro da página dele
      link      = "https://rstudio-pubs-static.s3.amazonaws.com/1018240_6c09a7b337324a8cbedadc9ffd9bc670.html",
      rotulo    = "",
      modo      = "externo"
    )
  )

  # UI ----------------------------------------------------------------------

  fluidPage(
    h2("Ciência de Dados"),
    faixa_etapas(etapas, "Etapas de um estudo"),
    fluidRow(card_projeto(projetos, "rmd_trf5"))
  )

}
