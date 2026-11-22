# Portfólio: o original monta o contrato e o distrato em R Markdown com LaTeX, que o R do navegador (webR)
# não tem. Este render() recebe os mesmos parâmetros e desenha o documento com o pdf() do próprio R.
render <- function(input, output_file, params = list(), ...) {
  distrato <- grepl("distrato", basename(input), ignore.case = TRUE)
  titulo <- if (distrato) "DISTRATO DE COMODATO" else "CONTRATO DE COMODATO"
  campo <- function(nome) {
    valor <- params[[nome]]
    if (is.null(valor) || length(valor) == 0 || all(is.na(valor))) "NÃO INFORMADO" else paste(valor, collapse = " ")
  }
  linhas <- c(
    if (distrato) paste0("CEV Nº: ", campo("ncev")),
    "",
    "COMODANTE",
    paste0("  ", campo("comodatante"), " - CNPJ ", campo("cnpj_comodatante")),
    paste0("  ", campo("end_comodatante"), " - CEP ", campo("cep_comodatante")),
    "",
    "COMODATÁRIA",
    paste0("  ", campo("comodataria"), " - CNPJ/CPF ", campo("cnpj_comodataria")),
    paste0("  ", campo("end_comodataria"), " - CEP ", campo("cep_comodataria")),
    if (!distrato) paste0("  Contato: ", campo("cont_comodataria"), " - Fone: ", campo("fone"), " - Vendedor: ", campo("ven_comodataria")),
    "",
    if (distrato) "As partes encerram o comodato dos bens abaixo, que retornam à comodante:"
    else "A comodante cede em comodato à comodatária os bens abaixo:",
    ""
  )
  tabela <- params$tabela_agrup
  if (is.data.frame(tabela) && nrow(tabela) > 0) {
    colunas <- intersect(c("CODCOMP", "PRODUTO", "Produto", "QTD", "Qtd"), names(tabela))
    tabela <- tabela[, colunas, drop = FALSE]
    linhas <- c(linhas, paste(names(tabela), collapse = "   |   "))
    linhas <- c(linhas, apply(tabela, 1, function(x) paste(trimws(x), collapse = "   |   ")))
  }
  linhas <- c(linhas, "", "", paste0(campo("cid"), ", ", format(Sys.Date(), "%d/%m/%Y")), "", "",
              "______________________________          ______________________________",
              "            COMODANTE                                    COMODATÁRIA",
              "", "Documento de demonstração do portfólio (dados fictícios).")

  grDevices::pdf(output_file, width = 8.27, height = 11.69)
  on.exit(grDevices::dev.off())
  graphics::par(mar = c(0, 0, 0, 0))
  graphics::plot.new()
  graphics::text(0.5, 0.96, titulo, font = 2, cex = 1.4)
  y <- 0.90
  for (linha in linhas) {
    graphics::text(0.06, y, linha, adj = c(0, 0.5), cex = 0.8, family = "mono")
    y <- y - 0.022
  }
  invisible(output_file)
}
