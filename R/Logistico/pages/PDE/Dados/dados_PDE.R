library(DBI)
library(glue)
library(dplyr)

# Portfólio: no original a PDE vive no MySQL (tb_pde e tb_empresas). Aqui as duas tabelas vêm do .parquet
# fictício para um DuckDB em memória, com as colunas na mesma ordem -- a consulta e os UPDATE da tela
# rodam como no original, e o que se grava vale até a página fechar.
if (!exists(".banco_pde", envir = globalenv())) {
  assign(".banco_pde", duckdb::duckdb(), envir = globalenv())
  carga <- as.data.frame(nanoparquet::read_parquet(glue("{diretorio}data/bd_pde/tb_pde.parquet")))
  con_carga <- dbConnect(.banco_pde)
  dbWriteTable(con_carga, "tb_pde", carga[, c(
    "ID", "CNPJ_EMP", "ROMANEIO", "DT_SAIDA", "HR_SAIDA", "DIAS_ROTA", "PLACA", "MOTORISTA", "AJUDANTE_1",
    "AJUDANTE_2", "ROTA", "OBS", "PESO_V", "PESO_R", "QTD_ENT", "QTD_NF", "FAT_SAIDA", "QTD_DEV", "FAT_DEV",
    "DT_FIM", "HR_FIM", "KM_INI", "KM_FIM"
  )], overwrite = TRUE)
  dbWriteTable(con_carga, "tb_empresas", distinct(carga, CNPJ_EMP, EMPRESA), overwrite = TRUE)
  # Esta conexão fica aberta: no DuckDB, fechar a última encerra o banco em memória.
  assign(".ancora_pde", con_carga, envir = globalenv())
}

conexao_pde <- function() dbConnect(.banco_pde)

carregar_dados_pde <- function() {
  con_pde <- conexao_pde()

  pde <- dbGetQuery(con_pde, glue(" SELECT e.EMPRESA, t.* FROM TB_PDE t LEFT JOIN tb_empresas e ON t.cnpj_emp = e.cnpj_emp WHERE CAST(ROMANEIO AS BIGINT) >= {format(Sys.Date()-15,'%Y%m%d')}"))

  dbDisconnect(con_pde)

  # pde = pde %>%
  #   mutate(across(everything(), ~ str_to_title(as.character(.))))

  names(pde) <- c(
    "Empresa", "Id", "Cnpj_emp", "Romaneio",
    "Data Saída", "Hora Saída", "Dias de rota",
    "Placa", "Motorista", "Ajudante 1", "Ajudante 2",
    "Rota", "Obs", "Peso Max", "Peso Rom", "Qtd Ent",
    "Qtd Nf", "Fat Saida", "Qtd Dev", "Fat Dev", "Data Chegada",
    "Hora Chegada", "Km Saída", "Km Chegada"
  )

  pde$`Km Rodados` <- pde$`Km Chegada` - pde$`Km Saída`

  for (coluna_num in 1:ncol(pde)) {
    if (is.character(pde[[coluna_num]])) {
      # pde[[coluna_num]] = as.factor(trimws(pde[[coluna_num]]))
      pde[[coluna_num]] <- trimws(pde[[coluna_num]])
    }
  }

  pde$`% Dev` <- pde$`Qtd Dev` / pde$`Qtd Ent`
  pde$`% Util` <- pde$`Peso Rom` / pde$`Peso Max`
  pde <- pde %>%
    relocate(`% Dev`, .after = `Fat Dev`) %>%
    relocate(`% Util`, .after = `Peso Rom`)

  return(pde)
}
