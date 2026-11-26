# Faixa com as etapas do processo de uma página (antes dos cards).
# Recebe um data.frame com 4 linhas (uma por etapa) e o título da faixa.
#
# Colunas esperadas no data.frame:
#   titulo, descricao, icone (nome do Font Awesome), cor (cor do bs4Dash)

faixa_etapas = function(etapas, titulo){

  # Uma etapa ocupa 3 das 12 colunas: a caixa e, à direita, a seta para a próxima.
  # A última etapa reserva o mesmo espaço da seta (vazio), para as 4 caixas terem a mesma largura.
  etapa = function(numero){
    column(
      width = 3,
      fluidRow(
        column(
          width = 10,
          infoBox(
            title = strong(etapas$titulo[numero]),
            value = span(etapas$descricao[numero], class = "font-weight-normal text-muted small"),
            icon = icon(etapas$icone[numero]),
            color = etapas$cor[numero],
            width = 12,
            elevation = 1
          )
        ),
        column(
          width = 2,
          class = "d-flex align-items-center justify-content-center px-0",
          if (numero < 4) icon("arrow-right", class = "text-muted")
        )
      )
    )
  }

  tagList(
    h5(titulo, class = "mt-2"),
    dashboardBadge("Exemplo de fluxo", color = "secondary"),
    fluidRow(
      # "faixa-etapas": o estilo.css deixa todas as caixas da mesma altura
      class = "mt-2 faixa-etapas",
      etapa(1),
      etapa(2),
      etapa(3),
      etapa(4)
    )
  )
}
