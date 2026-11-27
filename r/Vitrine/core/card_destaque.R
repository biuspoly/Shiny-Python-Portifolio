# Card compacto de projeto em destaque (grade da Visão Geral).
# Recebe o data.frame da página e o id do projeto; lê a linha daquele projeto.
#
# Colunas esperadas no data.frame:
#   id, titulo, descricao, cor, print, link
#   selos -> um ou dois textos separados por ";" (ex.: "Shiny Python;Polars")
#   modo  -> "app" (abre no modal), "pdf" (o PDF sozinho no modal), "repo" (abre o GitHub em nova aba) ou
#            "externo" (abre o site em nova aba)

card_destaque = function(projetos, id_projeto){

  projeto = projetos[projetos$id == id_projeto, ]
  selos   = strsplit(projeto$selos, ";")[[1]]

  # SERVER ------------------------------------------------------------------

  if (projeto$modo %in% c("app", "pdf")) {
    observeEvent(input[[paste0("bt_destaque_", id_projeto)]], {
      modal_do_projeto(projeto$titulo, projeto$link, pdf = projeto$modo == "pdf")   # em core/card_projeto.R
    })
  }

  if (projeto$modo %in% c("app", "pdf")) {
    botao_ver = actionButton(
      paste0("bt_destaque_", id_projeto),
      label = if (projeto$modo == "pdf") "Ver PDF" else "Ver projeto",
      icon = icon(if (projeto$modo == "pdf") "file-pdf" else "up-right-from-square"),
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
