library(DBI)
library(stringr)
library(dplyr)
library(tidyr)
library(zoo)
library(lubridate)
library(glue)
source(glue("{diretorio}pages/Comodatos/Dados/banco_comodato.R"), local = TRUE, encoding = "UTF-8")



# Configurações do banco --------------------------------------------------



solicita_comodato = function(cliente, usuario, item, cod_prod, unid, qtd, preco, tabprd, revenda, endereco, contato, pto_ref, dia_visit, seq, cep, fone, cnpj, ven, prazo, tipo){
  
  con <- conexao_comodato()
  
  adicionar_solic = data.frame(REVENDA = revenda, 
                               CLIENTE = cliente, 
                               CNPJ = cnpj,
                               USUARIO = usuario,
                               PRODUTO = item, 
                               CODCOMP = cod_prod,
                               UNIDADE = unid,
                               QTD = qtd, 
                               PRECO = preco,
                               TIPO = tipo,
                               TAB_CEV = tabprd,
                               VEN = ven,
                               ENDERECO = endereco,
                               CONTATO = contato,
                               PTO_REF = pto_ref,
                               DIA_VISIT = dia_visit,
                               SEQ = seq,
                               CEP = cep,
                               FONE = fone,
                               DATA = format(Sys.Date(), format = "%Y%m%d"),
                               VENC = ifelse(prazo == "1 ano", format(Sys.Date() + 365, format = "%Y%m%d"),format(Sys.Date() + 31, format = "%Y%m%d")),
                               PRAZO = prazo
                               )
  

  if(!dbExistsTable(con, "tb_comod_solicitado")){
    dbCreateTable(con, "tb_comod_solicitado", adicionar_solic)
  }
  
  dbAppendTable(con, "tb_comod_solicitado",adicionar_solic)
    

  

  dbDisconnect(con)
}


retira_comodato = function(revenda, cliente, produto, emissao, tipo, prazo){
  
  con <- conexao_comodato()
  
  dbExecute(con, glue("delete from tb_comod_solicitado 
                      where REVENDA = '{revenda}' and
                            CLIENTE = '{cliente}' and
                            PRODUTO = '{produto}' and
                            DATA = '{emissao}' and
                            TIPO = '{tipo}' and
                            PRAZO = '{prazo}'"))
  
  dbDisconnect(con)
}