# Gera o www/tema.css a partir do core/tema.R, para o app não compilar o tema a cada abertura.
# Rodar da pasta R/Vitrine: Rscript core/gerar_tema.R
# O CI roda antes de publicar; o arquivo fica fora do Git (o core/tema.R é a fonte das cores).

library(bs4Dash)
library(fresh)

source("core/tema.R", encoding = "UTF-8")
writeLines(as.character(tema), "www/tema.css", useBytes = TRUE)
cat("tema.css gerado:", file.size("www/tema.css"), "bytes\n")
