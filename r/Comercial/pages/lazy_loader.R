# Carregamento lazy de modulos de pagina.
# Cada modulo e carregado (source) apenas na primeira vez que o usuario
# acessa a aba correspondente. Chamadas subsequentes reutilizam o que ja
# foi definido no ambiente do server.
#
# Uso dentro do server (apos definir diretorio):
#   source(glue("{diretorio}pages/lazy_loader.R"), local = TRUE, encoding = "UTF-8")
#   setup_lazy_modules(output, diretorio, environment())

setup_lazy_modules <- function(output, diretorio, server_env) {

  modulos <- list(
    list(id = "conteudo_diario_venda",          script = "Diario de venda/pag_diario_venda_novo.R",           fn = "pag_diario_vendas"),
    list(id = "conteudo_mapa_com",               script = "Mapa comercial/pag_mapa_comercial_novo.R",         fn = "pag_mapa_comercial_novo")
  )

  for (m in modulos) {
    local({
      mod      <- m
      carregado <- FALSE

      output[[mod$id]] <- renderUI({
        if (!carregado) {
          source(
            paste0(diretorio, "pages/", mod$script),
            local    = server_env,
            encoding = "UTF-8"
          )
          carregado <<- TRUE
        }
        get(mod$fn, envir = server_env)()
      })
    })
  }
}
