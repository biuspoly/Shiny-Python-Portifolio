library(DBI)
library(duckdb)
library(glue)

# Portfólio: no original as tabelas do comodato vivem no MySQL. Aqui elas são montadas, com os mesmos
# nomes e colunas, a partir dos .parquet fictícios, num DuckDB em memória -- as consultas, INSERT e
# UPDATE das telas rodam como no original, e o que se grava vale até a página fechar.
if (!exists(".banco_comod", envir = globalenv())) {
  assign(".banco_comod", duckdb::duckdb(), envir = globalenv())
  pasta_comod <- glue("{diretorio}data/bd_comodato")
  ler_comod <- function(nome) as.data.frame(nanoparquet::read_parquet(file.path(pasta_comod, paste0(nome, ".parquet"))))

  geral <- ler_comod("comod_geral_bruto")
  cev <- sub(".* - ", "", geral$CEV)
  tb_comodato <- data.frame(
    CEV = cev, CODCOMP = as.character(geral$CODCOMP), NF = geral$NF, CODCLI = geral$Cliente,
    FANTASIA = geral$Fantasia, NOME = geral$`Razão Social`, DTE = geral$`Data Emissão`,
    DTV = geral$`Data Vencimento`, Intervalo = geral$`Intervalo Vencimento`, PRODUTO_GENERICO = geral$Produto,
    QTD = geral$Qtd, Inadimplente = geral$`Inadimplencia 60 dias +`, `Prazo Envio` = geral$`Prazo Envio`,
    cnpj_rev = geral$cnpj, VEN = geral$VEN,  # minúscula: é como a tela a lê (o MySQL devolve o nome do SELECT)
    # Comodato lançado pela tela (no original, com o número do pré-pedido); os outros vieram do ERP.
    PRE_PED = ifelse(geral$Origem == "Dash", paste0(geral$`Data Emissão`, "5000"), NA),
    check.names = FALSE
  )
  com_anexo <- !is.na(geral$situacao) | !is.na(geral$anexo1)
  # Os PDFs de exemplo moram em Anexos_Comodato/; a consulta original troca "Anexos/" por "Anexos_Comodato/".
  para_anexo <- function(caminho) ifelse(is.na(caminho), NA, paste0("Anexos/", basename(caminho)))
  tb_anexos <- data.frame(
    cnpj_rev = geral$cnpj[com_anexo], ncev = cev[com_anexo], codcli = geral$Cliente[com_anexo],
    nf = as.character(geral$NF[com_anexo]), tipo = "1",
    anexo1 = para_anexo(geral$anexo1[com_anexo]), anexo2 = para_anexo(geral$anexo2[com_anexo]),
    usuario = geral$Usuario[com_anexo], situacao = geral$situacao[com_anexo], dataI = geral$dataI[com_anexo],
    dataA = NA_character_, dataS = NA_character_, anexo3 = para_anexo(geral$anexo3[com_anexo]),
    id_old = NA_character_, comentario = NA_character_
  )
  tb_anexos <- tb_anexos[!duplicated(tb_anexos[, c("cnpj_rev", "ncev")]), ]

  livro <- ler_comod("saldo_livro_bruto")
  livro$DATA <- as.integer(livro$DATA)
  names(livro)[names(livro) == "OPERACAO"] <- "operacao"  # no MySQL esta coluna é minúscula
  # A tela filtra o mês pelo rótulo do calendário ("Mês Atual", "out/2026"); o mês do movimento vem
  # como "202611".
  meses_livro <- unique(livro$MES)
  rotulos_livro <- format(as.Date(paste0(meses_livro, "01"), "%Y%m%d"), "%b/%Y")
  rotulos_livro[rotulos_livro == format(Sys.Date(), "%b/%Y")] <- "Mês Atual"
  livro$MES_ATUAL <- rotulos_livro[match(livro$MES, meses_livro)]

  con_carga <- dbConnect(.banco_comod)
  dbWriteTable(con_carga, "TB_COMODATO", tb_comodato, overwrite = TRUE)
  dbWriteTable(con_carga, "TB_EMPRESAS", unique(data.frame(CNPJ_EMP = geral$cnpj, EMPRESA = geral$EMPRESA)), overwrite = TRUE)
  dbWriteTable(con_carga, "tb_anexos_cev", tb_anexos, overwrite = TRUE)
  dbWriteTable(con_carga, "TB_CLIENTES_INAD", ler_comod("clientes_inadimplentes_titulos_bruto"), overwrite = TRUE)
  dbWriteTable(con_carga, "TB_PRODUTOS_CEV", ler_comod("produtos_cev_bruto"), overwrite = TRUE)
  dbWriteTable(con_carga, "tb_livro_fiscal", livro, overwrite = TRUE)
  dbWriteTable(con_carga, "tb_comod_solicitado", ler_comod("comod_solicitado_bruto"), overwrite = TRUE)
  dbWriteTable(con_carga, "TB_COMOD_RECOLHA", data.frame(
    NPED = character(), CODCLI = character(), CEV = character(), REVENDA = character(), CNPJ = character(), DATA = character()
  ), overwrite = TRUE)
  dbWriteTable(con_carga, "tb_revendas", data.frame(
    CNPJ_REV = c("00000000000100", "00000000000280", "00000000000360", "00000000000440"),
    razao_social = c("DISTRIBUIDORA EXEMPLO NATAL LTDA", "DISTRIBUIDORA EXEMPLO FORTALEZA LTDA",
                     "DISTRIBUIDORA EXEMPLO TERESINA LTDA", "DISTRIBUIDORA EXEMPLO SAO LUIS LTDA"),
    logradouro = c("AV. DAS PALMEIRAS", "RUA DO PORTO", "AV. CENTRAL", "RUA DAS ACACIAS"),
    numero = c("100", "200", "300", "400"), bairro = "CENTRO",
    municipio = c("NATAL", "FORTALEZA", "TERESINA", "SAO LUIS"), uf = c("RN", "CE", "PI", "MA"),
    cep = c("59000-000", "60000-000", "64000-000", "65000-000")
  ), overwrite = TRUE)
  # Esta conexão fica aberta: no DuckDB, fechar a última encerra o banco em memória.
  assign(".ancora_comod", con_carga, envir = globalenv())
}

# O MySQL compara texto sem diferenciar maiúscula ("NATAL" = "Natal"); o DuckDB passa a fazer o mesmo.
conexao_comodato <- function() {
  con <- dbConnect(.banco_comod)
  dbExecute(con, "SET default_collation = 'nocase'")
  con
}

# Crases do MySQL viram aspas, e o LIKE (que no MySQL ignora maiúscula) vira ILIKE.
dbGetQuery <- function(conn, statement, ...) DBI::dbGetQuery(conn, gsub(" LIKE ", " ILIKE ", gsub("`", "\"", statement)), ...)
dbExecute <- function(conn, statement, ...) DBI::dbExecute(conn, gsub(" LIKE ", " ILIKE ", gsub("`", "\"", statement)), ...)

# shQuote() no Windows põe aspas duplas, que o MySQL lê como texto e o DuckDB como nome de coluna.
shQuote <- function(string, type = "sh") base::shQuote(string, type = type)
