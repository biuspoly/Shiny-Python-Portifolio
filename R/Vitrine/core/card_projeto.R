# Card de projeto, usado por todas as páginas de projetos.
# Recebe o data.frame da página e o id do projeto; lê a linha daquele projeto.
#
# Colunas esperadas no data.frame:
#   id, titulo, descricao, detalhes, cor, print
#   logo       -> um ou dois arquivos separados por ";"  (ex.: "r.svg;python.svg")
#   link       -> um ou dois endereços separados por ";" (um botão para cada)
#   rotulo     -> texto de cada botão, separado por ";"  ("" usa o texto padrão)
#   modo       -> "app" (abre no modal), "repo" (abre o GitHub em nova aba) ou "em_breve"

card_projeto = function(projetos, id_projeto){

  projeto = projetos[projetos$id == id_projeto, ]

  logos   = strsplit(projeto$logo, ";")[[1]]
  links   = strsplit(projeto$link, ";")[[1]]
  rotulos = strsplit(projeto$rotulo, ";")[[1]]

  if (length(links) == 0)   links = ""
  if (length(rotulos) < length(links)) rotulos = c(rotulos, rep("", length(links) - length(rotulos)))

  # SERVER ------------------------------------------------------------------

  # Botões "Ver projeto" no modo app: abrem o app num modal
  if (projeto$modo == "app") {

    observeEvent(input[[paste0("bt_ver_", id_projeto, "_1")]], {
      showModal(
        modalDialog(
          title = projeto$titulo,
          size = "xl",
          easyClose = TRUE,
          footer = modalButton("Fechar"),
          tags$iframe(src = links[1], width = "100%", style = "height: 75vh;", frameborder = "0")
        )
      )
    })

    if (length(links) == 2) {
      observeEvent(input[[paste0("bt_ver_", id_projeto, "_2")]], {
        showModal(
          modalDialog(
            title = projeto$titulo,
            size = "xl",
            easyClose = TRUE,
            footer = modalButton("Fechar"),
            tags$iframe(src = links[2], width = "100%", style = "height: 75vh;", frameborder = "0")
          )
        )
      })
    }
  }

  # Botões "Ver projeto" ----------------------------------------------------

  botao_ver = function(posicao){

    rotulo = rotulos[posicao]

    if (projeto$modo == "app") {
      actionButton(
        paste0("bt_ver_", id_projeto, "_", posicao),
        label = if (rotulo == "") "Ver projeto" else rotulo,
        icon = icon("up-right-from-square"),
        status = "primary",
        size = "sm",
        width = "100%"
      )
    } else if (projeto$modo == "repo") {
      # o GitHub não abre dentro de modal: abre o repositório em nova aba
      actionButton(
        paste0("bt_ver_", id_projeto, "_", posicao),
        label = if (rotulo == "") "Ver no GitHub" else rotulo,
        icon = icon("github"),
        status = "primary",
        size = "sm",
        width = "100%",
        onclick = paste0("window.open('", links[posicao], "', '_blank')")
      )
    } else {
      actionButton(
        paste0("bt_ver_", id_projeto, "_", posicao),
        label = "Em breve",
        icon = icon("clock"),
        status = "primary",
        size = "sm",
        width = "100%",
        disabled = NA
      )
    }
  }

  # sem status: segue o modo claro/escuro do bs4Dash
  botao_detalhes = actionButton(
    paste0("bt_detalhes_", id_projeto),
    label = "Detalhes",
    icon = icon("circle-info"),
    size = "sm",
    width = "100%"
  )

  if (length(links) == 2) {
    botoes = fluidRow(
      column(width = 4, botao_ver(1)),
      column(width = 4, botao_ver(2)),
      column(width = 4, botao_detalhes)
    )
  } else {
    botoes = fluidRow(
      column(width = 6, botao_ver(1)),
      column(width = 6, botao_detalhes)
    )
  }

  # Círculos do header -------------------------------------------------------

  circulo = function(arquivo){
    img(
      src = arquivo,
      # altura relativa ao texto (rem); a largura acompanha
      style = "height: 2.25rem;",
      class = "img-circle elevation-2 bg-white p-1 mt-n3 mb-n4 mr-2"
    )
  }

  # d-flex: círculos lado a lado sem ocupar altura de linha (a faixa fica estreita)
  circulos = span(
    class = "d-flex",
    circulo(logos[1]),
    if (length(logos) == 2) circulo(logos[2])
  )

  # UI ----------------------------------------------------------------------

  box(
    # o id "card_projeto_..." é o que o estilo.css usa para a faixa em degradê
    id = paste0("card_projeto_", id_projeto),
    width = 12,
    status = projeto$cor,
    solidHeader = TRUE,
    collapsible = FALSE,
    elevation = 2,

    # Header: só os ícones, à frente da faixa
    title = circulos,

    fluidRow(
      column(
        width = 2,
        img(src = projeto$print, width = "100%")
      ),
      column(
        width = 6,
        h4(projeto$titulo),
        p(projeto$descricao)
      ),
      column(
        width = 4,
        botoes
      )
    ),

    # Detalhes: aparece/esconde a cada clique em "Detalhes"
    conditionalPanel(
      condition = paste0("input.bt_detalhes_", id_projeto, " % 2 == 1"),
      hr(),
      p(projeto$detalhes)
    )
  )
}
