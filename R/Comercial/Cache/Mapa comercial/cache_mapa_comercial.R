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

# Mesmo padrao de Cache/Diario de venda/cache_diario_venda.R (fonte_parquet_dv2):
# le os parquets gravados por atualiza_mapa_comercial.R (pasta bd_comercial) via
# views DuckDB em memoria, evitando ida ao MariaDB a cada troca de filtro.

fonte_parquet_mc = function(query){

  pq_dir_mapa_comercial <- glue("{diretorio}data/bd_comercial/")

  arquivos <- Sys.glob(file.path(pq_dir_mapa_comercial, "*.parquet"))

  if (length(arquivos) == 0) {
    return(NULL)
  }


  con_mc <- dbConnect(duckdb(":memory:"))
  on.exit(dbDisconnect(con_mc, shutdown = TRUE))

  registrar_parquets(con_mc, arquivos, query)

  dbGetQuery(con_mc, query)
}
