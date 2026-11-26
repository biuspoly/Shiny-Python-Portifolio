# Card compacto de projeto em destaque (grade da Visão Geral).
# Recebe o data.frame da página e o id do projeto; lê a linha daquele projeto.
#
# Colunas esperadas no data.frame:
#   id, titulo, descricao, cor, print, link
#   selos -> um ou dois textos separados por ";" (ex.: "Shiny Python;Polars")
#   modo  -> "app" (abre no modal), "repo" (abre o GitHub em nova aba) ou "externo" (abre o site em nova aba)

card_destaque = function(projetos, id_projeto){

  projeto = projetos[projetos$id == id_projeto, ]
  selos   = strsplit(projeto$selos, ";")[[1]]

  # SERVER ------------------------------------------------------------------

  if (projeto$modo == "app") {
    observeEvent(input[[paste0("bt_destaque_", id_projeto)]], {
      showModal(
        modalDialog(
          title = projeto$titulo,
          size = "xl",
          easyClose = TRUE,
          footer = modalButton("Fechar"),
          tags$iframe(src = projeto$link, width = "100%", style = "height: 75vh;", frameborder = "0")
        )
      )
    })
  }

  if (projeto$modo == "app") {
    botao_ver = actionButton(
      paste0("bt_destaque_", id_projeto),
      label = "Ver projeto",
      icon = icon("up-right-from-square"),
      status = "primary",
      size = "sm"
    )
  } else if (projeto$modo == "externo") {
    # sites que não deixam abrir dentro do shinylive (Power BI, RPubs): abre em nova aba
    botao_ver = actionButton(
      paste0("bt_destaque_", id_projeto),
      label = "Ver projeto",
      icon = icon("up-right-from-square"),
      status = "primary",
      size = "sm",
      onclick = paste0("window.open('", projeto$link, "', '_blank')")
    )
  } else {
    botao_ver = actionButton(
      paste0("bt_destaque_", id_projeto),
      label = "Ver no GitHub",
      icon = icon("github"),
      status = "primary",
      size = "sm",
      onclick = paste0("window.open('", projeto$link, "', '_blank')")
    )
  }

  # UI ----------------------------------------------------------------------

  box(
    # o id "card_destaque_..." é o que o estilo.css usa para o zoom ao passar o mouse
    id = paste0("card_destaque_", id_projeto),
    width = 4,
    title = projeto$titulo,
    status = projeto$cor,       # sem solidHeader: só a borda de cima colorida
    collapsible = FALSE,
    elevation = 2,

    img(src = paste0(caminho_www, projeto$print), width = "100%"),   # caminho_www: definido no app.R
    br(),
    br(),
    dashboardBadge(selos[1], color = projeto$cor),
    if (length(selos) == 2) dashboardBadge(selos[2], color = "secondary"),
    p(projeto$descricao, class = "mt-2"),
    botao_ver
  )
}
