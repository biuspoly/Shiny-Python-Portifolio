# Paleta do Diário de Vendas
# A tabela é neutra: a cor fica só onde carrega sentido. Vermelho = abaixo do ano anterior ou da meta
# (só no texto, sem fundo); azul suave = as colunas que mais importam (tendência e cobertura do mês);
# cada marca tem a sua cor, mas como um marcador à esquerda do nome, não pintando a linha inteira.

# Cores de alerta / meta -------------------------------------------------------

cor_alerta_dv <- "#B3262D"

cor_meta = function(){
  list(color = cor_alerta_dv, fontWeight = "600")
}

cor_meta_bold <- function() list(color = cor_alerta_dv, fontWeight = "bold")

cor_meta_rev = function(){
  list(color = "#0F172A", fontWeight = "bold")
}

cor_meta_2026_titulo <- function() {
  list(color = "#0F172A", background = "#EEF2F7", fontWeight = "bold")
}

cor_meta_2026_valor <- function() {
  list(color = "#0F172A", background = "#EEF2F7", fontWeight = "bold")
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

# Estilo da linha inteira: só o necessário para ler a hierarquia.
cor_categoria_dv = function(categoria, nivel){

  if (identical(nivel, "TOTAL") && identical(categoria, "VOLUME TOTAL")) {
    return(list(color = "#0F172A", fontWeight = "bold"))
  }
  if (identical(nivel, "SEGMENTO_2") && identical(categoria, "CERVEJA RGB")) {
    return(list(color = "#0F172A", fontWeight = "bold"))
  }
  if (identical(nivel, "INDICADOR")) {
    return(list(color = "#475569"))
  }
  NULL

}

# Cor de cada marca: vira um marcador à esquerda do nome (coluna Categoria).
cores_marca_dv <- c(
  "MARÉ"          = "#0B6E79",
  "CORAL"         = "#B5532F",
  "JANGADA"       = "#6B8E23",
  "CORAL ULTRA"   = "#6D4AAE",
  "MARÉ ULTIMATE" = "#475569",
  "BRISA"         = "#5B9BD5",
  "FAROL"         = "#A23B72",
  "SERENA"        = "#2B6CB0"
)

marcador_categoria_dv <- function(categoria, nivel) {
  if (identical(nivel, "MARCA") && categoria %in% names(cores_marca_dv)) {
    return(list(
      boxShadow   = paste0("inset 4px 0 0 ", cores_marca_dv[[categoria]]),
      paddingLeft = "12px",
      fontWeight  = "600"
    ))
  }
  NULL
}

# Seções da tabela de categorias: uma linha separa uma seção da outra.
secao_dv <- function(nivel) {
  dplyr::case_when(
    nivel %in% c("TOTAL", "MARCA")                         ~ "marca",
    nivel %in% c("SEGMENTO", "SEGMENTO_2", "SEGMENTO_3")   ~ "segmento",
    TRUE                                                   ~ as.character(nivel)
  )
}

estilo_row_categorias_dv <- function(niveis, categorias) {
  secoes <- secao_dv(as.character(niveis))
  function(index) {
    estilo <- list()
    if (index > 1 && !identical(secoes[index], secoes[index - 1])) {
      estilo$borderTop <- "2px solid #CBD5E1"
    }
    # Fundo da linha total aqui (e não na célula): vale também nas células de alerta.
    if (identical(as.character(niveis[index]), "TOTAL") && identical(as.character(categorias[index]), "VOLUME TOTAL")) {
      estilo$background <- "#F1F5F9"
    }
    if (length(estilo)) estilo else NULL
  }
}


# Cor de cabecalho das colunas -------------------------------------------------
# Histórico em cinza, mês corrente em escuro, colunas-chave com fundo azul suave.

cor_cabecalho_dv = function(coluna, align = "center") {

  historico <- list(background = "#F8FAFC", color = "#64748B")
  atual     <- list(background = "#F8FAFC", color = "#0F172A")
  chave     <- list(background = "#E6F0FA", color = "#0B4A85")

  cor <- switch(coluna,
    VOL_ANO_RETRASADO = , VOL_MES_2 = , VOL_MES_ANT = , VOL_ANO_ANT = ,
    COB_MES_ANT = , COB_ANO_ANT = historico,
    TEND = , COB_MES_ATUAL = chave,
    atual
  )

  c(cor, list(
    fontWeight    = "600",
    textAlign     = align,
    whiteSpace    = "normal",
    verticalAlign = "bottom",
    borderBottom  = "1px solid #CBD5E1"
  ))

}

# Selo pequeno abaixo do título da coluna (Vol/LN, % Cob/LN).
selo_cabecalho_dv <- function(texto) {
  paste0(
    "<span style='display:inline-block;border:1px solid #CBD5E1;color:#64748B;padding:0 5px;",
    "border-radius:8px;font-size:0.9em;font-weight:normal;'>", texto, "</span>"
  )
}


# Estilos de linha (rowStyle) --------------------------------------------------

estilo_linha_agrupada_dv <- function() {
  JS("function(rowInfo) { if (rowInfo.aggregated) return { fontWeight: 'bold', background: '#F1F5F9' }; }")
}

estilo_row_familia_dv <- function() {
  JS(sprintf("function(rowInfo) {
    if (rowInfo.aggregated) return { fontWeight: 'bold', background: '#F1F5F9', color: '#0F172A' };
    if (rowInfo.row['AGRUPAMENTO_VOLUME'] === 'NOVO PRODUTO') return { color: '%s' };
  }", cor_alerta_dv))
}

estilo_row_meta_abp_dv <- function() {
  JS("function(rowInfo) {
    if (rowInfo.aggregated) {
      return { background: '#EEF2F7', color: '#0F172A', fontWeight: 'bold' };
    }
    if (rowInfo.values['NOVO_COD_SAP'] === 1) {
      return { borderTop: '1px solid #CBD5E1' };
    }
  }")
}


# Tema e fonte -----------------------------------------------------------------

fonte_corpo_dv    <- "75%"
tema_reactable_dv <- reactableTheme(
  borderColor     = "#EEF2F6",
  highlightColor  = "#F8FAFC",
  cellPadding     = "5px 6px",
  style           = list(fontSize = fonte_corpo_dv, fontVariantNumeric = "tabular-nums", color = "#1E293B"),
  headerStyle     = list(background = "#F8FAFC"),
  footerStyle     = list(background = "#F1F5F9", fontWeight = "bold", borderTop = "1px solid #CBD5E1")
)
