# Acompanhamentos em R: os três apps originais (Comercial, Logístico e Acessos) num processo só,
# para o Posit Connect Cloud.
#
# O painel vem da URL, como no portal do sistema original (que montava a URL com a ?REVENDA=):
#   /                                   página principal, um cartão por painel
#   /?painel=comercial                  o app Comercial, inteiro
#   /?painel=logistico&REVENDA=NATAL    o Logístico, já numa revenda
#
# Cada app segue independente na sua pasta (shiny::runApp("r/Comercial") continua funcionando). Aqui o
# app.R de cada um é avaliado num ambiente próprio, com `diretorio` apontando para a pasta dele: é por
# `diretorio` que os apps acham as páginas, os dados e o CSS. O shinyApp() do fim de cada app.R não roda;
# a UI e o server dele são guardados e servidos quando a URL pede o painel. Cada app só carrega no
# primeiro acesso.
#
# Este arquivo fica na pasta r/, acima dos apps: a pasta que o Posit publica (a do arquivo principal) já
# contém todos eles. O manifest.json ao lado é gerado por publicar/preparar_posit.py.

library(shiny)
library(htmltools)

pasta_app <- normalizePath(".", winslash = "/")
raiz_apps <- pasta_app  # r/: cada app numa subpasta

paineis <- list(
  comercial = list(
    pasta = "Comercial", nome = "Comercial", cor = "#06825d", imagem = "shiny_r_comercial.webp",
    resumo = "O Diário de Venda e o Mapa Comercial originais.",
    telas = c("Diário de Venda com meta, tendência, cobertura, indicadores e os gráficos de histórico",
              "Mapa Comercial: potencial e cobertura por município, com Leaflet e sf")
  ),
  logistico = list(
    pasta = "Logistico", nome = "Logístico", cor = "#254d71", imagem = "shiny_r_logistico.webp",
    resumo = "Frota, entregas, devoluções e comodato, como eram em R.",
    telas = c("Frota: geral, entrada e saída de veículos",
              "Planilha de Entregas e Devoluções (detalhes, caixas, valores e gráficos)",
              "Comodato: solicitação, pedido, documentos, recolha com distrato em PDF e saldo de vasilhames")
  ),
  acessos = list(
    pasta = "Acessos", nome = "Acessos", cor = "#3e2352", imagem = "shiny_r_acessos.webp",
    resumo = "O painel de logs e permissões original.",
    telas = c("Visão geral com a tendência de acessos e os dias sem acesso",
              "Acessos, usuários e permissões por painel")
  )
)


# Arquivos estáticos ------------------------------------------------------------------------------
# Os apps pedem as imagens em img/... (a raiz do www de cada um). Num processo só há uma raiz: as
# pastas img/ dos três vão para uma pasta única (os arquivos com o mesmo nome são idênticos). Os CSS
# de cada app entram embutidos na página (includeCSS), então não disputam endereço.

pasta_img <- file.path(tempdir(), "acompanhamentos_img")
dir.create(pasta_img, showWarnings = FALSE, recursive = TRUE)
for (p in paineis) {
  origem <- file.path(raiz_apps, p$pasta, "www", "img")
  if (dir.exists(origem)) file.copy(list.files(origem, full.names = TRUE), pasta_img, recursive = TRUE, overwrite = FALSE)
}
addResourcePath("img", pasta_img)
# Os prints dos cartões são os da Vitrine em R (r/Vitrine/www/prints).
addResourcePath("vitrine_img", file.path(raiz_apps, "Vitrine", "www", "prints"))


# Carregar um app -----------------------------------------------------------------------------------

carregados <- new.env()

eh_chamada <- function(e, nomes) is.call(e) && is.name(e[[1]]) && as.character(e[[1]]) %in% nomes

carregar_painel <- function(id) {
  if (!is.null(carregados[[id]])) return(carregados[[id]])

  pasta <- file.path(raiz_apps, paineis[[id]]$pasta)
  ambiente <- new.env(parent = globalenv())
  app <- NULL

  # O que o app.R faz ao carregar (addResourcePath("www"), includeCSS...) é relativo à pasta dele.
  anterior <- setwd(pasta)
  on.exit(setwd(anterior), add = TRUE)

  for (e in parse(file.path(pasta, "app.R"), encoding = "UTF-8")) {
    if (eh_chamada(e, "shinyApp")) {
      app <- list(ui = eval(e[[2]], ambiente), server = eval(e[[3]], ambiente))
      next
    }
    eval(e, ambiente)
    if (eh_chamada(e, c("<-", "=")) && identical(e[[2]], as.name("diretorio"))) {
      assign("diretorio", paste0(pasta, "/"), envir = ambiente)
    }
  }
  if (is.null(app)) stop("o app.R de ", pasta, " não chama shinyApp()")

  carregados[[id]] <- app
  app
}

painel_da_url <- function(query_string) {
  id <- parseQueryString(query_string %||% "")[["painel"]]
  if (!is.null(id) && tolower(id) %in% names(paineis)) tolower(id) else NULL
}


# Página principal ------------------------------------------------------------------------------------

pagina_principal <- function() {
  cartoes <- lapply(names(paineis), function(id) {
    p <- paineis[[id]]
    tags$article(
      class = "app", style = paste0("--cor: ", p$cor),
      tags$a(class = "foto", href = paste0("?painel=", id),
             tags$img(src = paste0("vitrine_img/", p$imagem), alt = paste("Tela do", p$nome), loading = "lazy")),
      div(class = "corpo",
          tags$h2(p$nome),
          tags$p(class = "resumo", p$resumo),
          tags$ul(lapply(p$telas, tags$li))),
      tags$a(class = "abrir", href = paste0("?painel=", id), paste("Abrir o", p$nome))
    )
  })

  tags$html(
    lang = "pt-BR",
    tags$head(
      tags$meta(charset = "utf-8"),
      tags$meta(name = "viewport", content = "width=device-width, initial-scale=1"),
      tags$title("Acompanhamentos em R | Portfólio Marlon Amaral"),
      tags$link(rel = "icon", href = "icone.svg", type = "image/svg+xml"),
      includeCSS(file.path(pasta_app, "principal.css"))
    ),
    tags$body(
      tags$header(class = "topo", div(class = "conteudo",
        tags$a(class = "marca", href = "https://biuspoly.github.io/shiny-portfolio/",
               tags$img(src = "icone.svg", alt = ""), span("Portfólio Marlon Amaral")),
        tags$h1("Acompanhamentos em R Shiny"),
        tags$p("A versão original do sistema, antes do Python (bs4Dash, reactable, DuckDB), num servidor só.",
               "Cada painel abre pela URL, como no portal original: ", tags$code("?painel=comercial"), ".")
      )),
      tags$main(class = "conteudo", div(class = "grade", cartoes)),
      tags$footer(class = "conteudo",
        tags$a(href = "https://biuspoly.github.io/shiny-portfolio/", "Voltar à vitrine"), " · código em ",
        tags$a(href = "https://github.com/biuspoly/shiny-portfolio", "github.com/biuspoly/shiny-portfolio"))
    )
  )
}


# UI e server: escolhem o painel pela URL ----------------------------------------------------------------

ui <- function(req) {
  id <- painel_da_url(req$QUERY_STRING)
  if (is.null(id)) return(pagina_principal())
  ui_painel <- carregar_painel(id)$ui
  if (is.function(ui_painel)) ui_painel(req) else ui_painel
}

server <- function(input, output, session) {
  id <- painel_da_url(isolate(session$clientData$url_search))
  if (is.null(id)) return(invisible(NULL))
  carregar_painel(id)$server(input, output, session)
}

shinyApp(ui, server)
