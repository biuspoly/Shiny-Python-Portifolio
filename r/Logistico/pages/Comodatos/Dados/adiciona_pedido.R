library(DBI)
library(glue)
library(dplyr)
source(glue("{diretorio}pages/Comodatos/Dados/erp_simulado.R"), local = TRUE, encoding = "UTF-8")

gerar_pedido = function(tabela_pedido){
  
  # Verifica se já tem pedido -----------------------------------------------
  mysql_server <- conexao_comodato()
  
  existe = dbGetQuery(mysql_server, glue("
  select PRE_PED from tb_comod_solicitado
  WHERE REVENDA = '{unique(tabela_pedido$REVENDA)}'
    AND CLIENTE = '{unique(tabela_pedido$CLIENTE)}'
    AND DATA = '{unique(tabela_pedido$DATA)}' 
    AND PRAZO = '{unique(tabela_pedido$PRAZO)}' 
    AND PRODUTO IN ({glue_collapse(shQuote(c(tabela_pedido$PRODUTO)), sep = ',')});
  "))
  
  if(!(nrow(existe) == 0 || all(is.na(existe$PRE_PED)) || all(existe$PRE_PED == ""))){
    return("consta")
    # return("passa")
  }
  else{
    options(scipen = 999)
    # Acessar control ---------------------------------------------------------
    
    empresas = data.frame()
    
    empresas <- rbind(empresas, data.frame(cnpj="00000000000100", Nome="Natal", banco="ERP_NATAL", digito=1, tabela_prod=1, prefixo = ""))
    empresas <- rbind(empresas, data.frame(cnpj="00000000000510", Nome="Filial A", banco="ERP_FILIAL_A", digito=1, tabela_prod=1, prefixo = ""))
    empresas <- rbind(empresas, data.frame(cnpj="00000000000520", Nome="Filial B", banco="ERP_FILIAL_B", digito=2, tabela_prod=1, prefixo = ""))
    empresas <- rbind(empresas, data.frame(cnpj="00000000000440", Nome="São Luís", banco="ERP_SAO_LUIS", digito=1, tabela_prod=1, prefixo = ""))
    empresas <- rbind(empresas, data.frame(cnpj="00000000000530", Nome="Filial C", banco="ERP_FILIAL_C", digito=1, tabela_prod=1, prefixo = ""))
    empresas <- rbind(empresas, data.frame(cnpj="00000000000990", Nome="Especial", banco="ERP_ESPECIAL", digito=2, tabela_prod=1, prefixo = "ERP_ESPECIAL_2."))
    empresas <- rbind(empresas, data.frame(cnpj="00000000000360", Nome="Teresina", banco="ERP_TERESINA", digito=1, tabela_prod=1, prefixo = ""))
    empresas <- rbind(empresas, data.frame(cnpj="00000000000280", Nome="Fortaleza", banco="ERP_FORTALEZA", digito=2, tabela_prod=2, prefixo = ""))
    empresas <- rbind(empresas, data.frame(cnpj="00000000000540", Nome="Filial F", banco="ERP_FILIAL_F", digito=2, tabela_prod=1, prefixo = ""))
    empresas <- rbind(empresas, data.frame(cnpj="00000000000550", Nome="Filial D", banco="ERP_FILIAL_D", digito=2, tabela_prod=1, prefixo = ""))
    empresas <- rbind(empresas, data.frame(cnpj="00000000000560", Nome="Filial E", banco="ERP_FILIAL_E", digito=1, tabela_prod=1, prefixo = ""))
    
    # tabela_pedido = data.frame(REVENDA = "Teresina")
    
    con <- conexao_erp(empresas$banco[str_detect(empresas$Nome,unique(tabela_pedido$REVENDA))])
    print(glue("Conectou na {empresas$Nome[str_detect(empresas$Nome,unique(tabela_pedido$REVENDA))]}"))
    
    pre_pedido <- as.character(dbGetQuery(con, glue("select max(VDPEDCPP_PRE_PED) + 1 as PRE_PED
                                                       from {empresas$prefixo[str_detect(empresas$Nome, unique(tabela_pedido$REVENDA))]}VDPEDCPP
                                                       where VDPEDCPP_PRE_PED <= {format(Sys.Date(), '%Y%m%d')}5999 and
                                                             VDPEDCPP_PRE_PED >= {format(Sys.Date(), '%Y%m%d')}5000"))$PRE_PED[1])
    
    if (is.na(pre_pedido)) {
      pre_pedido <- glue("{format(Sys.Date(), '%Y%m%d')}5000")
    }
    
    
    formato_VDPEDCPP = data.frame(VDPEDCPP_NREMP      = as.integer(empresas$digito[str_detect(empresas$Nome,unique(tabela_pedido$REVENDA))]),
                                  VDPEDCPP_PRE_PED    = as.numeric(pre_pedido),
                                  VDPEDCPP_LOGDT      = as.integer(format(Sys.Date(),format = "%Y%m%d")),
                                  VDPEDCPP_INCLDT     = as.integer(format(Sys.Date(),format = "%Y%m%d")),
                                  VDPEDCPP_INCLHR     = as.integer(format(Sys.time(),format = "%H%M")),
                                  VDPEDCPP_INCLSIGLA  = "Das",
                                  VDPEDCPP_NPED       = 0,
                                  VDPEDCPP_CODCLI     = as.numeric(str_extract(unique(tabela_pedido$CLIENTE), "^\\d+(?=\\s*-)")),
                                  VDPEDCPP_CGC        = as.numeric(unique(tabela_pedido$CNPJ)),
                                  VDPEDCPP_FL_ORIGEM  = "9",
                                  VDPEDCPP_VEN        = unique(tabela_pedido$VEN),
                                  VDPEDCPP_TPCOBR     = 5,
                                  VDPEDCPP_CPG        = 1,
                                  VDPEDCPP_DT_ENTREGA = ifelse(format(Sys.Date(),"%w") == "6", as.integer(format(Sys.Date() +2,format = "%Y%m%d")),as.integer(format(Sys.Date() + 1,format = "%Y%m%d"))),
                                  VDPEDCPP_TXFIN      = round(0,2),
                                  VDPEDCPP_VLRTOTAL   = round(sum(tabela_pedido$QTD * tabela_pedido$PRECO,na.rm = TRUE),2),
                                  VDPEDCPP_DTEMI      = as.integer(format(Sys.Date(),format = "%Y%m%d")),
                                  VDPEDCPP_DT1VC      = as.integer(unique(tabela_pedido$VENC)),
                                  VDPEDCPP_OBS        = "",
                                  VDPEDCPP_MOSTRA     = 1,
                                  VDPEDCPP_ERP_TERCEIRO = "",
                                  VDPEDCPP_VALOR_ACRESCIMO = 0,
                                  VDPEDCPP_VL_DESCTO  = 0,
                                  VDPEDCPP_QTD_PTS    = 0
    )
    
    
    formato_VDPEDIPP = data.frame(VDPEDIPP_NREMP      = as.integer(empresas$digito[str_detect(empresas$Nome,unique(tabela_pedido$REVENDA))]),
                                  VDPEDIPP_PRE_PED    = as.numeric(pre_pedido),
                                  VDPEDIPP_ITEM       = seq_len(nrow(tabela_pedido)),
                                  VDPEDIPP_LOGDT      = as.integer(format(Sys.Date(),format = "%Y%m%d")),
                                  VDPEDIPP_INCLDT     = as.integer(format(Sys.Date(),format = "%Y%m%d")),
                                  VDPEDIPP_INCLHR     = as.integer(format(Sys.time(),format = "%H%M")),
                                  VDPEDIPP_INCLSIGLA  = "Das",
                                  VDPEDIPP_OCOKD      = as.integer(50),
                                  VDPEDIPP_CODR       = as.numeric(str_extract(tabela_pedido$PRODUTO, "^\\d+(?=\\s*-)")),
                                  VDPEDIPP_PROD       = as.integer(tabela_pedido$CODCOMP),
                                  VDPEDIPP_QTD        = as.integer(tabela_pedido$QTD),
                                  VDPEDIPP_QTDS       = as.integer(0),
                                  VDPEDIPP_TBPRD      = as.integer(tabela_pedido$TAB_CEV),
                                  VDPEDIPP_VLR_LIQUIDO= round(tabela_pedido$QTD * tabela_pedido$PRECO,2),
                                  VDPEDIPP_VLR_BRUTO  = round(tabela_pedido$QTD * tabela_pedido$PRECO,2),
                                  VDPEDIPP_PREPRDU    = round(tabela_pedido$PRECO, 2),
                                  VDPEDIPP_PREPRDUS   = round(tabela_pedido$PRECO / tabela_pedido$UNIDADE, 2),
                                  VDPEDIPP_PREPRDT_CX = round(tabela_pedido$QTD * tabela_pedido$PRECO,2),
                                  VDPEDIPP_ORIGEM     = "9"
    )
    
    if(empresas$Nome[str_detect(empresas$Nome,unique(tabela_pedido$REVENDA))] == "Especial"){
      
      dbAppendTable(con, Id(schema = glue("{sub('\\\\.$', '', empresas$prefixo[str_detect(empresas$Nome, unique(tabela_pedido$REVENDA))])}"), table = "VDPEDCPP"), formato_VDPEDCPP,row.names = NULL)
      print("tabela de pedido")
      # print(formato_VDPEDCPP)
      print("tabela de itens")
      # print("foi a primeira")
      for (linha in 1:nrow(formato_VDPEDIPP)){
        dbAppendTable(con, Id(schema = glue("{sub('\\\\.$', '', empresas$prefixo[str_detect(empresas$Nome, unique(tabela_pedido$REVENDA))])}"), table = "VDPEDIPP"), formato_VDPEDIPP[linha,],row.names = NULL)
        # print(formato_VDPEDIPP[linha,])
      }
    } else{
      dbAppendTable(con, "VDPEDCPP", formato_VDPEDCPP,row.names = NULL)
      print("tabela de pedido")
      # print(formato_VDPEDCPP)
      print("tabela de itens")
      # print("foi a primeira")
      for (linha in 1:nrow(formato_VDPEDIPP)){
        dbAppendTable(con, "VDPEDIPP", formato_VDPEDIPP[linha,],row.names = NULL)
        # print(formato_VDPEDIPP[linha,])
      }
    }
    
    
    
    # print("foi a segunda")
    dbDisconnect(con)
    
    # Acessar mysql server ----------------------------------------------------
    
    apply(tabela_pedido, 1, function(linha_cev) {
      dbExecute(mysql_server, glue("
    UPDATE tb_comod_solicitado
    SET PRE_PED = '{pre_pedido}'
    WHERE REVENDA = '{linha_cev['REVENDA']}'
      AND CLIENTE = '{linha_cev['CLIENTE']}'
      AND PRODUTO = '{linha_cev['PRODUTO']}'
      AND DATA = '{linha_cev['DATA']}';
    "))
    })
    
    
  }
  
  dbDisconnect(mysql_server)
  
}