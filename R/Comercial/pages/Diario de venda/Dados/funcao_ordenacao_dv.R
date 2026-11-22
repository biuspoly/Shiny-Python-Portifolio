ordem_agrupamento_dv <- function() {
  c(
    "NOVO PRODUTO",
    "TOTAL 600ML",
    "TOTAL 1L",
    "TOTAL 300ML",
    "TOTAL 473ML",
    "TOTAL 350ML",
    "TOTAL 275ML",
    "TOTAL LN 330ML",
    "TOTAL LN 355ML",
    "TOTAL 600ML OW",
    "TOTAL CHOPP 30L",
    "TOTAL CHOPP 50L",
    "TOTAL REFRI LATA TUPÃ",
    "TOTAL CAJUÍNA 450ML",
    "TOTAL AGUA",
    "DOCES",
    "SNACKS"
  )
}

# Renomeio visual de categorias combinadas (nao altera dado, so exibicao na tabela) --

renomeio_visual_categoria_dv <- function(){
  c(
    "CORAL ULTRA + CORAL + JANGADA" = "A. ULTRA + CORAL + JANGADA"
  )
}

formatar_categoria_visual_dv <- function(categoria){
  mapa <- renomeio_visual_categoria_dv()
  ifelse(categoria %in% names(mapa), mapa[categoria], categoria)
}

ordem_categ_dv = function(){
  
  c(
      "VOLUME TOTAL",
      "MARÉ",
      "CORAL ULTRA",
      "CORAL",
      "JANGADA",
      "BRISA",
      "FAROL",
      "CERVEJA RGB",
      "PREMIUM + MAINSTREAM",
      "CORAL ULTRA + CORAL",
      "CORAL ULTRA + CORAL + JANGADA",
      "MAR LN 330ML",
      "MAR LN 330ML 0,0%",
      "MAR LN 250ML",
      "SERENA LN 330ML",
      "CORAL LN 275ML",
      " ",
      "SKU/PDV ABP",
      "SKU/PDV REVENDA",
      "FDS ABP",
      "FDS REVENDA",
      "CORAL 600/MAR 600",
      "MAR 600/RGB TT",
      "MAR 0.0%/MAR TT",
      "FATURAMENTO OW",
      "FATURAMENTO RGB",
      "DOCES",
      "SNACKS",
      "FATURAMENTO IMPULSE",
      "FATURAMENTO TAKE HOME"
    )
  
  
}
