library(DBI)
library(stringr)
library(dplyr)
library(tidyr)
library(zoo)
library(lubridate)
library(glue)



# Configurações do banco --------------------------------------------------

source(glue("{diretorio}pages/Comodatos/Dados/banco_comodato.R"), local = TRUE, encoding = "UTF-8")


anexos_comod = function(anexo1, anexo2, anexo3, codcli, ncev, cnpj_emp, nome_anexo1, nome_anexo2, nome_anexo3){
  # pasta_destino = glue("{diretorio}pages/Comodatos/Dados/Anexos")
  pasta_destino = glue("Anexos_Comodato")
  
  if (!dir.exists(pasta_destino)) {
    dir.create(pasta_destino, recursive = TRUE)
  }
  
  # vetor para armazenar os caminhos
  caminhos <- c(PDV = NA, CEV = NA, CANHOTO = NA)
  
  ### PDV
  if (!is.null(anexo1)) {
    caminho_pdv <- paste("PDV", cnpj_emp, ncev, codcli, nome_anexo1, sep = "_")
    arquivo_pdv <- file.copy(from = anexo1,
                             to = file.path(pasta_destino, caminho_pdv),
                             overwrite = TRUE)
    if (arquivo_pdv) {
      caminhos["PDV"] <- sub(".*(Anexos/.*)", "\\1",
                             normalizePath(file.path(pasta_destino, caminho_pdv), winslash = "/"))
    }
  }
  
  ### CEV
  if (!is.null(anexo2)) {
    caminho_cev <- paste("CEV", cnpj_emp, ncev, codcli, nome_anexo2, sep = "_")
    arquivo_cev <- file.copy(from = anexo2,
                             to = file.path(pasta_destino, caminho_cev),
                             overwrite = TRUE)
    if (arquivo_cev) {
      caminhos["CEV"] <- sub(".*(Anexos/.*)", "\\1",
                             normalizePath(file.path(pasta_destino, caminho_cev), winslash = "/"))
    }
  }
  
  ### CANHOTO
  if (!is.null(anexo3)) {
    caminho_can <- paste("CANHOTO", cnpj_emp, ncev, codcli, nome_anexo3, sep = "_")
    arquivo_can <- file.copy(from = anexo3,
                             to = file.path(pasta_destino, caminho_can),
                             overwrite = TRUE)
    if (arquivo_can) {
      caminhos["CANHOTO"] <- sub(".*(Anexos/.*)", "\\1",
                                 normalizePath(file.path(pasta_destino, caminho_can), winslash = "/"))
    }
  }
  
  return(caminhos)
}


coloca_anexo_bd = function(ncev, caminho_pdv, caminho_cev, caminho_can, cnpj_emp, usuario, codcli, nf){
  
  con <- conexao_comodato()
  
  verifica_anexo = dbGetQuery(con, glue("select * from tb_anexos_cev where ncev = '{ncev}' and cnpj_rev = '{cnpj_emp}'"))
  
  status = if (!is.null(caminho_can) && caminho_can != "") "A" else "P"
  
  if(cnpj_emp != "00000000000990"){
    if(nrow(verifica_anexo) > 0){
      dbExecute(con, glue("update tb_anexos_cev 
                         set 
                         anexo1 = '{caminho_pdv}',
                         /*anexo2 = '{caminho_cev}',*/
                         anexo3 = '{caminho_can}',
                         dataI  = '{substr(format(Sys.time(), format = '%Y-%m-%d %H:%M:%S'),1,15)}',
                         situacao = '{status}',
                         usuario = '{usuario}'
                         where ncev = {ncev} and cnpj_rev = {cnpj_emp}"))
    } else{
      
      dbExecute(con, glue("insert into `tb_anexos_cev`(`cnpj_rev`, `ncev`, `codcli`, `nf`, `tipo`, `anexo1`, `anexo2`, `usuario`, `situacao`, `dataI`, `dataA`, `dataS`, `anexo3`, `id_old`, `comentario`)
                        values ('{cnpj_emp}',
                                '{ncev}',
                                '{codcli}',
                                '{nf}',
                                1,
                                '{caminho_pdv}',
                                '{caminho_cev}',
                                '{usuario}',
                                '{status}',
                                '{substr(format(Sys.time(), format = '%Y-%m-%d %H:%M:%S'),1,15)}',
                                NULL,
                                NULL,
                                '{caminho_can}',
                                NULL,
                                NULL)")
      )
    }
  } else{
    if(nrow(verifica_anexo) > 0){
      dbExecute(con, glue("update tb_anexos_cev 
                         set 
                         anexo1 = '{caminho_pdv}',
                         anexo2 = '{caminho_cev}',
                         anexo3 = '{caminho_can}',
                         dataI  = '{substr(format(Sys.time(), format = '%Y-%m-%d %H:%M:%S'),1,15)}',
                         situacao = '{status}',
                         usuario = '{usuario}'
                         where ncev = {ncev} and cnpj_rev = {cnpj_emp}"))
    }
    else{
      
      dbExecute(con, glue("insert into `tb_anexos_cev`(`cnpj_rev`, `ncev`, `codcli`, `nf`, `tipo`, `anexo1`, `anexo2`, `usuario`, `situacao`, `dataI`, `dataA`, `dataS`, `anexo3`, `id_old`, `comentario`)
                        values ('{cnpj_emp}',
                                '{ncev}',
                                '{codcli}',
                                '{nf}',
                                1,
                                '{caminho_pdv}',
                                '{caminho_cev}', 
                                '{usuario}',
                                '{status}',
                                '{substr(format(Sys.time(), format = '%Y-%m-%d %H:%M:%S'),1,15)}',
                                NULL,
                                NULL,
                                '{caminho_can}',
                                NULL,
                                NULL)")
      )
    }
  }
  
  
  dbDisconnect(con)
}

conf_bloq_comod = function(ncev, situacao, motivo, cnpj_emp){
  con <- conexao_comodato()
  
  dbExecute(con, glue("
                        UPDATE tb_anexos_cev
                        SET SITUACAO = '{situacao}',
                            COMENTARIO = '{motivo}'
                        WHERE 
                            CNPJ_REV = {cnpj_emp} AND
                            NCEV = {ncev}
                        "))
  
  dbDisconnect(con)
  
}
