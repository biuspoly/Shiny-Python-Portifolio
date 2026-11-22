excluir_categorias_dv <- function(revenda) {
  exclusoes <- list(
    "Natal"        = c("BRISA"),
    "Filial C"         = c("BRISA"),
    "Filial A" = c("BRISA"),
    "Filial B" = c("BRISA"),
    "Filial F"   = c("BRISA"),
    "Filial D"     = c("BRISA"),
    "Filial E"    = c("BRISA"),
    "GRUPO NATAL"  = c("BRISA"),
    "GRUPO FILIAL"   = c("BRISA"),
    "GRUPO FILIAL C"   = c("BRISA"),
    "GRUPO FILIAL"     = c("BRISA"),
    "Fortaleza"     = c("FAROL"),
    "Teresina"     = c("FAROL")
  )
  exclusoes[[revenda]] %||% character(0)
}
