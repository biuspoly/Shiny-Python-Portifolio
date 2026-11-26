# Card de projeto, usado por todas as páginas de projetos.
# Recebe o data.frame da página e o id do projeto; lê a linha daquele projeto.
# Um projeto pode ter até 5 versões (um botão para cada) e até 3 linguagens (um círculo para cada).
#
# Colunas esperadas no data.frame (valores de cada versão separados por ";"):
#   id, titulo, descricao, detalhes, cor, print
#   logo   -> até 3 arquivos, um por linguagem   (ex.: "powerbi.svg;r.svg;python.svg")
#   link   -> um endereço por versão
#   rotulo -> o texto do botão de cada versão  ("" usa o texto padrão)
#   modo   -> o modo de cada versão; um valor só vale para todas:
#             "app" (abre no modal), "repo" (GitHub em nova aba),
#             "externo" (site em nova aba) ou "em_breve"

card_projeto = function(projetos, id_projeto){

  projeto = projetos[projetos$id == id_projeto, ]

  logos   = strsplit(projeto$logo, ";")[[1]]
  links   = strsplit(projeto$link, ";")[[1]]
  rotulos = strsplit(projeto$rotulo, ";")[[1]]
  modos   = strsplit(projeto$modo, ";")[[1]]

  if (length(links) == 0) links = ""
  versoes = length(links)
  if (length(rotulos) < versoes) rotulos = c(rotulos, rep("", versoes - length(rotulos)))
  if (length(modos) < versoes)   modos   = rep(modos[1], versoes)

  # SERVER ------------------------------------------------------------------

  # Versão no modo app: o botão abre o app num modal
  abrir_modal = function(posicao){
    if (versoes >= posicao && modos[posicao] == "app") {
      observeEvent(input[[paste0("bt_ver_", id_projeto, "_", posicao)]], {
        showModal(
          modalDialog(
            title = projeto$titulo,
            size = "xl",
            easyClose = TRUE,
            footer = modalButton("Fechar"),
            tags$iframe(src = links[posicao], width = "100%", style = "height: 75vh;", frameborder = "0")
          )
        )
      })
    }
  }

  abrir_modal(1)
  abrir_modal(2)
  abrir_modal(3)
  abrir_modal(4)
  abrir_modal(5)

  # Botões das versões --------------------------------------------------------

  botao_ver = function(posicao){

    if (versoes < posicao) return(NULL)

    rotulo = rotulos[posicao]
    modo   = modos[posicao]
    id_bt  = paste0("bt_ver_", id_projeto, "_", posicao)

    if (modo == "app") {
      botao = actionButton(
        id_bt,
        label = if (rotulo == "") "Ver projeto" else rotulo,
        icon = icon("up-right-from-square"),
        status = "primary",
        size = "sm",
        width = "100%"
      )
    } else if (modo == "repo") {
      # o GitHub não abre dentro de modal: abre o repositório em nova aba
      botao = actionButton(
        id_bt,
        label = if (rotulo == "") "Ver no GitHub" else rotulo,
        icon = icon("github"),
        status = "primary",
        size = "sm",
        width = "100%",
        onclick = paste0("window.open('", links[posicao], "', '_blank')")
      )
    } else if (modo == "externo") {
      # sites que não deixam abrir dentro do shinylive (Power BI, RPubs): abre em nova aba
      botao = actionButton(
        id_bt,
        label = if (rotulo == "") "Ver projeto" else rotulo,
        icon = icon("up-right-from-square"),
        status = "primary",
        size = "sm",
        width = "100%",
        onclick = paste0("window.open('", links[posicao], "', '_blank')")
      )
    } else {
      botao = actionButton(
        id_bt,
        label = if (rotulo == "") "Em breve" else paste(rotulo, "(em breve)"),
        icon = icon("clock"),
        status = "primary",
        size = "sm",
        width = "100%",
        disabled = NA
      )
    }

    # com uma versão só, o botão divide a linha com "Detalhes"; com várias, duas por linha
    column(width = 6, class = "mb-2", botao)
  }

  # sem status: segue o modo claro/escuro do bs4Dash
  botao_detalhes = column(
    width = 6,
    class = "mb-2",
    actionButton(
      paste0("bt_detalhes_", id_projeto),
      label = "Detalhes",
      icon = icon("circle-info"),
      size = "sm",
      width = "100%"
    )
  )

  botoes = fluidRow(
    botao_ver(1),
    botao_ver(2),
    botao_ver(3),
    botao_ver(4),
    botao_ver(5),
    botao_detalhes
  )

  # Círculos do header (uma linguagem por círculo) ----------------------------

  circulo = function(posicao){
    if (length(logos) < posicao) return(NULL)
    img(
      src = logos[posicao],
      # altura relativa ao texto (rem); a largura acompanha
      style = "height: 2.25rem;",
      class = "img-circle elevation-2 bg-white p-1 mt-n3 mb-n4 mr-2"
    )
  }

  # d-flex: círculos lado a lado sem ocupar altura de linha (a faixa fica estreita)
  circulos = span(
    class = "d-flex",
    circulo(1),
    circulo(2),
    circulo(3)
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
