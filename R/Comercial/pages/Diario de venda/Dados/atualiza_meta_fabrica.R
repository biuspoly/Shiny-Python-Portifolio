library(DBI)
library(dplyr)
library(glue)
# Portfólio: sem MySQL (library(RMariaDB) no original).
library(purrr)
library(lubridate)

# Extrai a definicao de uma funcao de um arquivo R sem executar o corpo do script
extrair_funcao_do_script <- function(caminho_arquivo, nome_funcao) {
  for (expressao in parse(caminho_arquivo)) {
    if (is.call(expressao) && length(expressao) == 3 &&
        as.character(expressao[[1]]) %in% c("<-", "=") &&
        as.character(expressao[[2]]) == nome_funcao) {
      env_isolado <- new.env(parent = globalenv())
      eval(expressao, envir = env_isolado)
      return(env_isolado[[nome_funcao]])
    }
  }
  stop("Funcao '", nome_funcao, "' nao encontrada em: ", caminho_arquivo)
}

# Portfólio: estas funções vêm dos scripts do pipeline (MySQL), que não fazem parte do portfólio.
dir_dados <- "C:/webservice shiny/Shiny App/Acompanhamento Comercial/pages/Diario de venda/Dados"
if (dir.exists(dir_dados)) {
  
  calcular_compacto   <- extrair_funcao_do_script(file.path(dir_dados, "atualiza_diario_venda_compacto.R"),    "get_diario_venda_compacto")
  calcular_expandido  <- extrair_funcao_do_script(file.path(dir_dados, "atualiza_diario_venda_expandido.R"),    "get_diario_venda_familia")
  calcular_outros_vol <- extrair_funcao_do_script(file.path(dir_dados, "atualiza_diario_venda_expandido_ov.R"), "get_diario_venda_outros_volumes")
}


conectar_comercial <- function(argumentos_bd) {
  con <- DBI::dbConnect(
    RMariaDB::MariaDB(),
    dbname   = strsplit(argumentos_bd$dbname, ",")[[1]][8],
    host     = argumentos_bd$host,
    port     = as.numeric(argumentos_bd$port),
    user     = argumentos_bd$user,
    password = argumentos_bd$password,
    charset  = "utf8mb4"
  )
  DBI::dbExecute(con, "SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci")
  con
}


# Mesmo mapeamento que REVENDA_PARA_SUFIXO em cache_diario_venda.R — manter sincronizado
REVENDA_PARA_SUFIXO <- c(
  "Natal"        = "natal",
  "Especial"       = "especial_pe",
  "São Luís"     = "sao_luis",
  "Fortaleza"     = "fortaleza",
  "Teresina"     = "teresina",
  "Filial A" = "filial_a",
  "Filial B" = "filial_b",
  "Filial C"         = "filial_c",
  "Filial F"   = "filial_f",
  "Filial D"     = "filial_d",
  "Filial E"    = "filial_e"
)

nome_para_sufixo_rev <- function(revenda) {
  sufixo <- REVENDA_PARA_SUFIXO[[revenda]]
  if (is.null(sufixo) || is.na(sufixo))
    stop("Revenda desconhecida: '", revenda, "'. Adicione ao mapa REVENDA_PARA_SUFIXO.")
  sufixo
}



combinacoes_ga_ven <- function(con, revenda, mes) {
  revenda_sql <- gsub("'", "''", revenda)

  pares <- DBI::dbGetQuery(con, glue(
    "SELECT DISTINCT GA, VEN FROM tb_diario_venda
     WHERE REVENDA = '{revenda_sql}' AND MES = '{mes}'"
  ))

  dplyr::bind_rows(
    data.frame(GA = NA_character_, VEN = NA_character_, stringsAsFactors = FALSE),
    pares %>% dplyr::distinct(GA) %>% dplyr::mutate(VEN = NA_character_),
    pares
  )
}


gravar_tabela_dv <- function(con, tabela_destino, dados_novos) {
  if (nrow(dados_novos) > 0) {
    DBI::dbWriteTable(con, tabela_destino, dados_novos, overwrite = TRUE)
  }
}


rodar_pipeline_por_combinacao <- function(con, fn_calcular, revenda, mes, combinacoes) {
  purrr::pmap_dfr(combinacoes, function(GA, VEN) {
    resultado <- fn_calcular(
      con     = con,
      revenda = revenda,
      mes     = mes,
      ga      = if (is.na(GA)) NULL else GA,
      ven     = if (is.na(VEN)) NULL else VEN
    )
    if (!is.null(resultado) && nrow(resultado) > 0) {
      dplyr::mutate(resultado,
        INDICE_REV = revenda,
        INDICE_MES = mes,
        INDICE_GA  = ifelse(is.na(GA), "GERAL", GA),
        INDICE_VEN = ifelse(is.na(VEN), "GERAL", VEN)
      )
    } else NULL
  })
}


gravar_parquet_dv <- function(dados, tipo, sufixo, mes) {
  base <- "C:/webservice shiny/Shiny App/Acompanhamento Comercial/pages/Diario de venda/Dados/parquet"
  dir_tipo <- file.path(base, tipo)
  dir.create(dir_tipo, recursive = TRUE, showWarnings = FALSE)

  pq_path <- gsub("\\\\", "/", normalizePath(
    file.path(dir_tipo, paste0(sufixo, "_", mes, ".parquet")),
    mustWork = FALSE
  ))

  con_pq <- duckdb::dbConnect(duckdb::duckdb(":memory:"))
  on.exit(duckdb::dbDisconnect(con_pq, shutdown = TRUE), add = TRUE)

  duckdb::duckdb_register(con_pq, "s", dados)
  DBI::dbExecute(con_pq, sprintf("COPY s TO '%s' (FORMAT PARQUET)", pq_path))
  duckdb::duckdb_unregister(con_pq, "s")

  invisible(pq_path)
}


atualizar_parquet_bd_comercial_metas <- function(argumentos_bd) {
  dir_bd  <- "C:/webservice shiny/Shiny App/Acompanhamento Comercial/pages/Diario de venda/Dados/parquet/bd_comercial"
  dir.create(dir_bd, recursive = TRUE, showWarnings = FALSE)
  pq_path <- gsub("\\\\", "/", normalizePath(file.path(dir_bd, "TB_META_FABRICA.parquet"), mustWork = FALSE))

  con_fab <- conectar_comercial(argumentos_bd)
  on.exit(DBI::dbDisconnect(con_fab), add = TRUE)

  df_fab <- DBI::dbGetQuery(con_fab, "SELECT CODRED, CAST(MES AS CHAR) AS MES, REVENDA, VALOR, VALOR_UMB FROM TB_META_FABRICA")
  df_fab$CODRED    <- as.character(df_fab$CODRED)
  df_fab$MES       <- as.character(df_fab$MES)
  df_fab$VALOR     <- as.numeric(df_fab$VALOR)
  df_fab$VALOR_UMB <- as.numeric(df_fab$VALOR_UMB)

  con_pq <- duckdb::dbConnect(duckdb::duckdb(":memory:"))
  on.exit(duckdb::dbDisconnect(con_pq, shutdown = TRUE), add = TRUE)
  duckdb::duckdb_register(con_pq, "tmp", df_fab)
  DBI::dbExecute(con_pq, sprintf("COPY tmp TO '%s' (FORMAT PARQUET)", pq_path))
  duckdb::duckdb_unregister(con_pq, "tmp")

  invisible(TRUE)
}


atualizar_meta_fabrica <- function(revenda, mes, argumentos_bd) {

  con <- conectar_comercial(argumentos_bd)
  on.exit(DBI::dbDisconnect(con), add = TRUE)

  sufixo <- nome_para_sufixo_rev(revenda)

  combinacoes <- combinacoes_ga_ven(con, revenda, mes)

  # Pipeline DV em tryCatch: falhas nao impedem a atualizacao do parquet de metas
  tryCatch({
    dados_compacto <- rodar_pipeline_por_combinacao(con, calcular_compacto,   revenda, mes, combinacoes)
    gravar_tabela_dv(con, paste0("tb_dv_compacto_",     sufixo, "_", mes), dados_compacto)
    gravar_parquet_dv(dados_compacto,   "compacto",     sufixo, mes)

    dados_expandido <- rodar_pipeline_por_combinacao(con, calcular_expandido,  revenda, mes, combinacoes)
    gravar_tabela_dv(con, paste0("tb_dv_expandido_",    sufixo, "_", mes), dados_expandido)
    gravar_parquet_dv(dados_expandido,  "expandido",    sufixo, mes)

    dados_outros_vol <- rodar_pipeline_por_combinacao(con, calcular_outros_vol, revenda, mes, combinacoes)
    gravar_tabela_dv(con, paste0("tb_dv_expandido_ov_", sufixo, "_", mes), dados_outros_vol)
    gravar_parquet_dv(dados_outros_vol, "expandido_ov", sufixo, mes)
  }, error = function(e) {
    warning("Pipeline DV falhou (parquet de metas sera atualizado mesmo assim): ", conditionMessage(e))
  }, finally = {
    atualizar_parquet_bd_comercial_metas(argumentos_bd)
  })

  invisible(TRUE)
}

# ----------------------------------------------------------------------------
# Execucao direta
# ----------------------------------------------------------------------------

if (sys.nframe() == 0L) {
  argumentos_bd <- as.list(read.dcf("C:/webservice shiny/Shiny App/Acompanhamento Comercial/Argumentos DBLocal.txt")[1,])

  revenda <- ""        # preencher com a revenda desejada, ex: "Filial F"
  mes     <- format(Sys.Date(), "%Y%m")

  if (nchar(revenda) == 0) stop("Informe a revenda antes de executar.")

  cat("Recalculando:", revenda, "/", mes, "\n")
  atualizar_meta_fabrica(revenda, mes, argumentos_bd)
  cat("Concluido.\n")
}
