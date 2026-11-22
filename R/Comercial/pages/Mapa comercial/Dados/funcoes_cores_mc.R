# Tema e fonte -----------------------------------------------------------------
# Mesmos valores do Diario de Venda para consistência visual entre as abas

fonte_corpo_mc    <- "75%"
tema_reactable_mc <- reactableTheme(style = list(fontSize = fonte_corpo_mc))


# Cor de cabeçalho das colunas -------------------------------------------------
# Padrao do Mapa Comercial: verde (#06825D) com texto branco.

cor_cabecalho_mc <- function(coluna, align = "center") {

  c(list(background = "#06825D", color = "#FFFFFF"), list(
    fontWeight    = "bold",
    fontSize      = "110%",
    textAlign     = align,
    whiteSpace    = "normal",
    lineHeight     = "1.15",
    height         = "auto",
    verticalAlign = "middle"
  ))

}


# Cor de fonte por linha (faixas de cobertura/potencial) ------------------------
# Recebe o vetor de cores ja calculado na tabela (ex: COR_AREA, COR_PERC_CLI_ATIVO)
# e devolve a funcao de estilo no formato que o reactable espera: function(value, index)

cor_coluna_mc <- function(cores_linha) {
  function(value, index) {
    list(color = cores_linha[index], fontWeight = "bold")
  }
}


# Fundo de alerta do R$/Hab quando abaixo do minimo aceitavel -------------------

cor_fundo_fat_hab_mc <- function(value, index) {
  if (!is.na(value) && value < 5) list(background = "#F4C9CD") else list()
}
