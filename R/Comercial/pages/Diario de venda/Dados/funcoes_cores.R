# Cores de alerta / meta -------------------------------------------------------

cor_meta = function(){
  list(color = "#D71920", background = "#FAEBEB")
}

cor_meta_bold <- function() c(cor_meta(), list(fontWeight = "bold"))

cor_meta_rev = function(){
  list(color = "#000000", background = "#A1C8E4", fontWeight = "bold")
}

cor_meta_2026_titulo <- function() {
  list(color = "#FFFFFF", background = "#0D6ABF", fontWeight = "bold")
}

cor_meta_2026_valor <- function() {
  list(color = "#FFFFFF", background = "#06825D", fontWeight = "bold")
}


# Cor por ano (historico) ------------------------------------------------------

cor_ano <- function(ano) {
  diferenca <- as.integer(format(Sys.Date(), "%Y")) - as.integer(ano)
  switch(as.character(diferenca),
    "0" = "#5DADE2",
    "1" = "#1E8449",
    "2" = "#82E0AA",
    "3" = "#E67E22",
         "#95A5A6"
  )
}


# Cor por categoria / nivel (celulas da tabela) --------------------------------

cor_categoria_dv = function(categoria, nivel){

  cores = list(

    TOTAL = list(
      `VOLUME TOTAL` = list(color = "#000000", fontWeight = "bold")
    ),

    MARCA = list(
      MARÉ       = list(color = "#FFFFFF", background = "#008200"),
      CORAL         = list(color = "#FFFFFF", background = "#D71920"),
      `CORAL ULTRA` = list(color = "#FFFFFF", background = "#054f77"),
      JANGADA        = list(color = "#000000", background = "#ffde21"),
      BRISA        = list(color = "#000000", background = "#fed000"),
      FAROL          = list(color = "#FFFFFF", background = "#D75413")
    ),

    SEGMENTO = list(
      default        = list(color = "#000000", background = "#FFFFFF")
    ),

    SEGMENTO_2 = list(
      `CERVEJA RGB`  = list(color = "#FFFFFF", background = "#000000")
    ),

    SEGMENTO_3 = list(
      default        = list(color = "#000000", background = "#FFFFFF")
    ),

    SKU = list(
      default        = list(color = "#000000", background = "#CFF7D4")
    ),

    INDICADOR = list(
      default        = list(color = "#000000", background = "#e4f2f7")
    ),

    FATURAMENTO = list(
      default        = NULL
    )

  )

  if(nivel == "TOTAL" && categoria %in% names(cores$TOTAL)){
    return(cores$TOTAL[[categoria]])
  }

  if(nivel == "MARCA" && categoria %in% names(cores$MARCA)){
    return(cores$MARCA[[categoria]])
  }

  if(nivel == "SEGMENTO" && categoria %in% names(cores$SEGMENTO)){
    return(cores$SEGMENTO[[categoria]])
  }

  if(nivel == "SEGMENTO_2" && categoria %in% names(cores$SEGMENTO_2)){
    return(cores$SEGMENTO_2[[categoria]])
  }

  if(nivel %in% names(cores)){
    return(cores[[nivel]]$default)
  }

  NULL

}


# Cor de cabecalho das colunas -------------------------------------------------

cor_cabecalho_dv = function(coluna, align = "center") {

  cores = list(
    CATEGORIA         = list(background = "#06825D", color = "#FFFFFF"),
    VOL_ANO_RETRASADO = list(background = "#FFFFFF", color = "#605E5C"),
    VOL_MES_2         = list(background = "#FFFFFF", color = "#605E5C"),
    VOL_MES_ANT       = list(background = "#FFFFFF", color = "#605E5C"),
    META_FAB          = list(background = "#06825D", color = "#FFFFFF"),
    META_REV          = list(background = "#06825D", color = "#FFFFFF"),
    VOL_ANO_ANT       = list(background = "#FFFFFF", color = "#605E5C"),
    VOL_ANO_ANT2      = list(background = "#06825D", color = "#FFFFFF"),
    VOL_MES_ATUAL     = list(background = "#06825D", color = "#FFFFFF"),
    TEND              = list(background = "#0D6ABF", color = "#FFFFFF"),
    PERC_TEND         = list(background = "#06825D", color = "#FFFFFF"),
    VENDA_HL          = list(background = "#06825D", color = "#FFFFFF"),
    PERC_VOL_LN       = list(background = "#06825D", color = "#FFFFFF"),
    PERC_COB_LN       = list(background = "#06825D", color = "#FFFFFF"),
    COB_MES_ANT       = list(background = "#06825D", color = "#FFFFFF"),
    COB_ANO_ANT       = list(background = "#06825D", color = "#FFFFFF"),
    COB_MES_ATUAL     = list(background = "#0D6ABF", color = "#FFFFFF"),
    FAT               = list(background = "#06825D", color = "#FFFFFF")
  )

  cor = cores[[coluna]]
  if (is.null(cor)) cor = list(background = "#FFFFFF", color = "#000000")

  c(cor, list(
    fontWeight    = "bold",
    fontSize      = "110%",
    textAlign     = align,
    whiteSpace    = "normal",
    verticalAlign = "middle"
  ))

}


# Estilos de linha (rowStyle) --------------------------------------------------

estilo_linha_agrupada_dv <- function() {
  JS("function(rowInfo) { if (rowInfo.aggregated) return { fontWeight: 'bold' }; }")
}

estilo_row_familia_dv <- function() {
  JS("function(rowInfo) {
    if (rowInfo.aggregated) return { fontWeight: 'bold' };
    if (rowInfo.row['AGRUPAMENTO_VOLUME'] === 'NOVO PRODUTO') return { color: '#D71920', background: '#FAEBEB' };
  }")
}

estilo_row_meta_abp_dv <- function() {
  JS("function(rowInfo) {
    if (rowInfo.aggregated) {
      return { background: '#04573E', color: '#FFFFFF', fontWeight: 'bold' };
    }
    if (rowInfo.values['NOVO_COD_SAP'] === 1) {
      return { borderTop: '0.5px solid #000000' };
    }
  }")
}


# Tema e fonte -----------------------------------------------------------------

fonte_corpo_dv    <- "75%"
tema_reactable_dv <- reactableTheme(style = list(fontSize = fonte_corpo_dv))
