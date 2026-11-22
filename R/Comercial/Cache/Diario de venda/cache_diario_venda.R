library(DBI)
library(duckdb)
library(glue)

# Portfólio: as tabelas vêm dos .parquet fictícios em data/bd_comercial. O R do navegador não tem o
# read_parquet do DuckDB (é extensão), então cada arquivo é lido uma vez pelo nanoparquet, fica na
# memória e é registrado como tabela na conexão -- só os que a consulta cita. O SQL é o original.
if (!exists(".tabelas_parquet", envir = globalenv())) assign(".tabelas_parquet", new.env(), envir = globalenv())
ler_tabela_parquet <- function(arquivo) {
  memoria <- get(".tabelas_parquet", envir = globalenv())
  if (is.null(memoria[[arquivo]])) assign(arquivo, as.data.frame(nanoparquet::read_parquet(arquivo)), envir = memoria)
  memoria[[arquivo]]
}
registrar_parquets <- function(con, arquivos, query) {
  for (arquivo in arquivos) {
    nome <- sub("[.]parquet$", "", basename(arquivo))
    if (grepl(paste0("(^|[^[:alnum:]_])", nome, "([^[:alnum:]_]|$)"), query, ignore.case = TRUE)) {
      duckdb::duckdb_register(con, nome, ler_tabela_parquet(arquivo))
    }
  }
}

# Mapeamento: nome da revenda -> prefixo do arquivo parquet no disco.
# Incluir variantes com e sem acento para cobrir tanto revenda_query()
# (que pode retornar uppercase com ou sem acento) quanto os nomes de grupo
# (que precisam bater com INDICE_REV no parquet).
REVENDA_PARA_SUFIXO <- list(
  "NATAL"           = "natal",
  "ESPECIAL"          = "especial_pe",
  "SÃO LUÍS"        = "sao_luis",
  "FORTALEZA"        = "fortaleza",
  "TERESINA"        = "teresina",
  "FILIAL A"    = "filial_a",
  "FILIAL B"    = "filial_b",
  "FILIAL B" = "filial_b",
  "FILIAL C"            = "filial_c",
  "FILIAL F"      = "filial_f",
  "FILIAL F" = "filial_f",
  "FILIAL D"        = "filial_d",
  "FILIAL D"   = "filial_d",
  "FILIAL E"       = "filial_e",
  "Natal"           = "natal",
  "Especial"          = "especial_pe",
  "São Luís"        = "sao_luis",
  "Fortaleza"        = "fortaleza",
  "Teresina"        = "teresina",
  "Filial A"    = "filial_a",
  "Filial B"    = "filial_b",
  "Filial B" = "filial_b",
  "Filial C"            = "filial_c",
  "Filial F"      = "filial_f",
  "Filial F" = "filial_f",
  "Filial D"        = "filial_d",
  "Filial D"   = "filial_d",
  "Filial E"       = "filial_e"
)

escapar_sql_dv  <- function(valor)   gsub("'", "''", valor)
valores_sql_dv  <- function(valores) paste(paste0("'", escapar_sql_dv(valores), "'"), collapse = ", ")
literal_sql_dv  <- function(valor)   paste0("'", escapar_sql_dv(valor), "'")

pasta_parquet_dv <- function() {
  base <- if (exists("diretorio", inherits = TRUE)) get("diretorio", inherits = TRUE) else "Acompanhamento Comercial/"
  file.path(base, "pages/Diario de venda/Dados/parquet")
}

# Retorna subquery DuckDB lendo os parquets diretamente do disco.
# Cada query cria sua propria conexao DuckDB — sem estado compartilhado.
fonte_parquet_dv <- function(tipo_parquet, revendas, mes = NULL) {
  pasta_do_tipo <- file.path(pasta_parquet_dv(), tipo_parquet)

  caminhos <- unlist(lapply(revendas, function(nome_revenda) {
    sufixo <- REVENDA_PARA_SUFIXO[[nome_revenda]]
    if (is.null(sufixo) || is.na(sufixo)) return(NULL)

    if (!is.null(mes)) {
      arq_mes  <- file.path(pasta_do_tipo, paste0(sufixo, "_", mes, ".parquet"))
      arq_hist <- file.path(pasta_do_tipo, paste0(sufixo, "_historico.parquet"))
      if (file.exists(arq_mes))  return(gsub("\\\\", "/", normalizePath(arq_mes)))
      if (file.exists(arq_hist)) return(gsub("\\\\", "/", normalizePath(arq_hist)))
      return(NULL)
    }

    arquivos <- Sys.glob(file.path(pasta_do_tipo, paste0(sufixo, "_*.parquet")))
    if (length(arquivos) == 0) return(NULL)
    vapply(arquivos, function(p) gsub("\\\\", "/", normalizePath(p)), character(1))
  }), use.names = FALSE)

  caminhos <- unique(caminhos[!is.na(caminhos) & nzchar(caminhos)])
  if (length(caminhos) == 0) return(NULL)

  arquivos_sql <- paste(vapply(caminhos, literal_sql_dv, character(1)), collapse = ", ")
  glue("read_parquet([{arquivos_sql}])")
}

remover_colunas_tecnicas_cache_dv <- function(tabela) tabela


fonte_parquet_dv2 = function(query, tabelas = NULL){

  pq_dir_bd_comercial <- glue("{diretorio}data/bd_comercial/")

  arquivos <- if (!is.null(tabelas)) {
    candidatos <- file.path(pq_dir_bd_comercial, paste0(tabelas, ".parquet"))
    candidatos[file.exists(candidatos)]
  } else {
    Sys.glob(file.path(pq_dir_bd_comercial, "*.parquet"))
  }

  if (length(arquivos) == 0) {
    return(NULL)
  }

  
  con_dv <- dbConnect(duckdb(":memory:"))
  on.exit(dbDisconnect(con_dv, shutdown = TRUE))
  
  registrar_parquets(con_dv, arquivos, query)
  
  dbGetQuery(con_dv, query)
}
