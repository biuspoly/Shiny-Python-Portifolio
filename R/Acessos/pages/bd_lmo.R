# Portfólio: as tabelas do banco do portal (no original, MySQL) vêm de .parquet fictícios em
# data/bd_acessos/. Lidas uma vez; o que a tela grava muda a cópia em memória (no navegador,
# cada visitante tem a sua, que some ao fechar a página).

library(dplyr)

if (!exists(".bd_lmo", envir = globalenv())) {
  assign(".bd_lmo", new.env(), envir = globalenv())
  for (tabela in c("usuario", "dashboard", "revenda", "logacesso", "dash_group", "user_revenda")) {
    # Pelo `diretorio`, como o resto do app: no app unificado (R/Acompanhamentos) a pasta atual é outra.
    caminho <- file.path(paste0(get0("diretorio", ifnotfound = ""), "data"), "bd_acessos", paste0(tabela, ".parquet"))
    assign(tabela, as.data.frame(nanoparquet::read_parquet(caminho)), envir = .bd_lmo)
  }
}

tb <- function(nome) get(nome, envir = .bd_lmo)
tb_gravar <- function(nome, valor) assign(nome, as.data.frame(valor), envir = .bd_lmo)

# O STR_TO_DATE(dataAcesso, '%d/%m/%Y %H:%i:%s') das consultas originais.
data_acesso <- function(texto) as.POSIXct(texto, format = "%d/%m/%Y %H:%M:%S", tz = "America/Fortaleza")
agora <- function() as.POSIXct(format(Sys.time(), tz = "America/Fortaleza"), tz = "America/Fortaleza")
