library(DBI)
library(duckdb)
library(glue)

# Portfólio: no original o pedido de comodato e a recolha vão ao ERP por ODBC, um DSN por revenda. Aqui
# cada DSN é um DuckDB em memória com as tabelas que esses scripts leem e gravam, montadas dos comodatos
# fictícios da revenda -- o código de pedido e de recolha roda como no original.
if (!exists(".bancos_erp", envir = globalenv())) assign(".bancos_erp", list(), envir = globalenv())

# Qual revenda cada DSN atende (o mesmo nome que as tabelas "empresas" dos scripts usam).
CNPJ_DO_DSN <- c(
  ERP_NATAL = "00000000000100", ERP_FORTALEZA = "00000000000280",
  ERP_TERESINA = "00000000000360", ERP_SAO_LUIS = "00000000000440"
)

montar_erp <- function(dsn) {
  banco <- duckdb::duckdb()
  con <- dbConnect(banco)
  digito <- if (dsn == "ERP_FORTALEZA") 2 else 1
  con_comod <- conexao_comodato()
  comod <- DBI::dbGetQuery(con_comod, glue("SELECT * FROM TB_COMODATO WHERE CNPJ_REV = '{CNPJ_DO_DSN[[dsn]]}'"))
  dbDisconnect(con_comod)
  ceves <- unique(comod[, c("CEV", "CODCLI", "VEN", "NF", "DTE")])
  ceves <- ceves[!duplicated(ceves$CEV), ]
  nped <- as.numeric(paste0(ceves$DTE, sprintf("%04d", seq_len(nrow(ceves)))))
  ano <- as.integer(substr(ceves$DTE, 1, 4))
  mes <- as.integer(substr(ceves$DTE, 5, 6))

  dbWriteTable(con, glue("PEDCP0{digito}"), data.frame(
    VDPEDCPE_NPED = nped, VDPEDCPE_DTEMIPED = as.integer(ceves$DTE), VDPEDCPE_NLOTE = "1",
    VDPEDCPE_CROMA = sprintf("%04d%02d%05d", ano, mes, seq_len(nrow(ceves))), VDPEDCPE_TIPOP = "1",
    VDPEDCPE_TABREF1 = 2018, VDPEDCPE_TABREF2 = 199, VDPEDCPE_CODCLI = as.numeric(ceves$CODCLI),
    VDPEDCPE_CATCLI = "1", VDPEDCPE_VEN = ceves$VEN, VDPEDCPE_TPCOBR = "1", VDPEDCPE_CPG = "1",
    VDPEDCPE_DT1VC = as.integer(ceves$DTE), VDPEDCPE_LINHA_1 = "", VDPEDCPE_LINHA_2 = "", VDPEDCPE_LINHA_3 = "",
    VDPEDCPE_ORIGEM_PED = "1", VDPEDCPE_SERIE = "1", VDPEDCPE_NFIS = as.numeric(ceves$NF),
    VDPEDCPE_CODTRA = "1", VDPEDCPE_PLACA = "ABC1D23", VDPEDCPE_MOT = "1", VDPEDCPE_NITENS = 1,
    VDPEDCPE_FL = "0", VDPEDCPE_IMPR = "S", VDPEDCPE_USUARIO = "ERP", VDPEDCPE_NFISULT = as.numeric(ceves$NF),
    VDPEDCPE_DTB_X = 0, VDPEDCPE_FLROMA = "S", VDPEDCPE_VLR_OGEM = 0, VDPEDCPE_FILLER_03 = "1",
    VDPEDCPE_EM_ROMANEIO = "", VDPEDCPE_TP_ROTEIRIZ = "", VDPEDCPE_MULT_RECEBIMENTOS = "N",
    VDPEDCPE_HORA_GERACAO_NFS = 800
  ), overwrite = TRUE)
  dbWriteTable(con, glue("CEVPED0{digito}"), data.frame(
    VDCEVPEN_NPED = nped, VDCEVPEN_NRCCEV = as.numeric(ceves$CEV), VDCEVPEN_NPEDR = 0
  ), overwrite = TRUE)
  dbWriteTable(con, glue("CROMA0{digito}"), data.frame(
    VDROMCRO_ANOC = ano, VDROMCRO_MESC = mes, VDROMCRO_SEQ = seq_len(nrow(ceves)), VDROMCRO_DTB = as.integer(ceves$DTE)
  ), overwrite = TRUE)
  dbWriteTable(con, glue("VDFATN0{digito}"), data.frame(
    VDFATNFR_NNF = as.numeric(ceves$NF), VDFATNFR_INCLDT = as.integer(ceves$DTE)
  ), overwrite = TRUE)
  dbWriteTable(con, glue("PEDIT0{digito}"), data.frame(
    VDPEDIPE_NIT = nped[match(comod$CEV, ceves$CEV)], VDPEDIPE_PROD = as.integer(comod$CODCOMP),
    VDPEDIPE_QTD = as.integer(comod$QTD), VDPEDIPE_LOGDT = 0, VDPEDIPE_INCLDT = 0, VDPEDIPE_INCLHR = 0,
    VDPEDIPE_INCLSIGLA = "", VDPEDIPE_NIVELAUDIT = 0, VDPEDIPE_PREPRDUS = 0, VDPEDIPE_SERIE = "",
    VDPEDIPE_NUMFAT = 0, VDPEDIPE_NATOP = 0, VDPEDIPE_LINHA = 0, VDPEDIPE_OCOKD = "50", VDPEDIPE_FL = "",
    VDPEDIPE_MOTTROCA = "", VDPEDIPE_CFOP_SAIDA = 0, VDPEDIPE_SEQ_FIXA = 0
  ), overwrite = TRUE)
  # Pré-pedidos que a tela grava (cabeçalho e itens), vazios no começo.
  DBI::dbExecute(con, "CREATE TABLE VDPEDCPP (VDPEDCPP_NREMP INTEGER, VDPEDCPP_PRE_PED DOUBLE, VDPEDCPP_LOGDT INTEGER,
    VDPEDCPP_INCLDT INTEGER, VDPEDCPP_INCLHR INTEGER, VDPEDCPP_INCLSIGLA VARCHAR, VDPEDCPP_NPED DOUBLE,
    VDPEDCPP_CODCLI DOUBLE, VDPEDCPP_CGC DOUBLE, VDPEDCPP_FL_ORIGEM VARCHAR, VDPEDCPP_VEN VARCHAR,
    VDPEDCPP_TPCOBR DOUBLE, VDPEDCPP_CPG DOUBLE, VDPEDCPP_DT_ENTREGA INTEGER, VDPEDCPP_TXFIN DOUBLE,
    VDPEDCPP_VLRTOTAL DOUBLE, VDPEDCPP_DTEMI INTEGER, VDPEDCPP_DT1VC INTEGER, VDPEDCPP_OBS VARCHAR,
    VDPEDCPP_MOSTRA DOUBLE, VDPEDCPP_ERP_TERCEIRO VARCHAR, VDPEDCPP_VALOR_ACRESCIMO DOUBLE,
    VDPEDCPP_VL_DESCTO DOUBLE, VDPEDCPP_QTD_PTS DOUBLE)")
  DBI::dbExecute(con, "CREATE TABLE VDPEDIPP (VDPEDIPP_NREMP INTEGER, VDPEDIPP_PRE_PED DOUBLE, VDPEDIPP_ITEM INTEGER,
    VDPEDIPP_LOGDT INTEGER, VDPEDIPP_INCLDT INTEGER, VDPEDIPP_INCLHR INTEGER, VDPEDIPP_INCLSIGLA VARCHAR,
    VDPEDIPP_OCOKD INTEGER, VDPEDIPP_CODR DOUBLE, VDPEDIPP_PROD INTEGER, VDPEDIPP_QTD INTEGER,
    VDPEDIPP_QTDS INTEGER, VDPEDIPP_TBPRD INTEGER, VDPEDIPP_VLR_LIQUIDO DOUBLE, VDPEDIPP_VLR_BRUTO DOUBLE,
    VDPEDIPP_PREPRDU DOUBLE, VDPEDIPP_PREPRDUS DOUBLE, VDPEDIPP_PREPRDT_CX DOUBLE, VDPEDIPP_ORIGEM VARCHAR)")
  # Âncora: fechar a última conexão encerra o banco em memória.
  list(banco = banco, ancora = con)
}

conexao_erp <- function(dsn) {
  if (!(dsn %in% names(CNPJ_DO_DSN))) stop(glue("ERP simulado: DSN {dsn} não existe no portfólio"))
  bancos <- get(".bancos_erp", envir = globalenv())
  if (is.null(bancos[[dsn]])) {
    bancos[[dsn]] <- montar_erp(dsn)
    assign(".bancos_erp", bancos, envir = globalenv())
  }
  dbConnect(bancos[[dsn]]$banco)
}
