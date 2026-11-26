label_mes <- function(data) {
  nomes <- c("Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
             "Jul", "Ago", "Set", "Out", "Nov", "Dez")
  paste0(nomes[as.integer(format(data, "%m"))], "/", format(data, "%y"))
}
