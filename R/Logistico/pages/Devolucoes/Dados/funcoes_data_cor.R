data_calend <- function() {
  seq_meses <- rev(seq(from = as.Date("2025-01-01"), to = Sys.Date(), by = "month"))

  meses_dev <- format(seq_meses, "%b/%Y")
  meses_dev[meses_dev == format(Sys.Date(), "%b/%Y")] <- "Mês Atual"

  # Inicializar listas para armazenar colunas
  Meses <- c()
  Dias <- c()
  Labels <- c()

  # Preencher listas
  for (i in seq_along(seq_meses)) {
    mes <- seq_meses[i]
    dias_mes <- seq(
      from = mes,
      to = seq_meses[i] + months(1) - 1,
      by = "day"
    )
    dias_mes <- rev(dias_mes[dias_mes <= Sys.Date()])

    Meses <- c(Meses, rep(meses_dev[i], length(dias_mes)))
    Dias <- c(Dias, dias_mes)
    Labels <- c(Labels, format(dias_mes, "%d/%m/%Y"))
  }

  # Criar data.frame final
  df_datas <- data.frame(
    Mes = Meses,
    Dia = Dias,
    Label = Labels,
    stringsAsFactors = FALSE
  )

  df_datas
}
as.numeric(gsub(",", ".", gsub("%", "", "6,22%")))

cor_agrup <- function(column, threshold, color_above, color_below, color_same = "#fcfffd") {
  JS(
    paste0(
      "function(rowInfo) {
          var value = parseFloat(String(rowInfo.row['", column, "']).replace('%','').replace(',','.').trim());

          if(value > ", threshold, ") {
            var color = '", color_above, "'
          } else if(value < ", threshold, ") {
            var color = '", color_below, "'
          } else {
            var color = '", color_same, "'
          }

          return {background:color}
        }"
    )
  )
}
