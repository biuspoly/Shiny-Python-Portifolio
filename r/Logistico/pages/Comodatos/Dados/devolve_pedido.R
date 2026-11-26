library(DBI)
library(glue)
library(dplyr)
library(stringr)
source(glue("{diretorio}pages/Comodatos/Dados/erp_simulado.R"), local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Comodatos/Dados/pdf_portfolio.R"), local = TRUE, encoding = "UTF-8")

# Escapa caracteres especiais do LaTeX (nomes/enderecos com "&" quebram o distrato_comod.Rmd) ----

escapar_latex <- function(texto) {
  if (is.null(texto)) return(texto)
  texto <- as.character(texto)

  str_replace_all(texto, c(
    "&"   = "\\&",
    "%"   = "\\%",
    "\\$" = "\\$",
    "#"   = "\\#",
    "_"   = "\\_",
    "\\{" = "\\{",
    "\\}" = "\\}"
  ))
}

# Integração com control --------------------------------------------------

gerar_recolha <- function(revenda, cev) {
  empresas <- data.frame()

  empresas <- rbind(empresas, data.frame(cnpj = "00000000000100", Nome = "Natal", banco = "ERP_NATAL", digito = 1, tabela_prod = 1, prefixo = "", tabref = "2018.01"))
  empresas <- rbind(empresas, data.frame(cnpj = "00000000000510", Nome = "Filial A", banco = "ERP_FILIAL_A", digito = 1, tabela_prod = 1, prefixo = "", tabref = "2019.03"))
  empresas <- rbind(empresas, data.frame(cnpj = "00000000000520", Nome = "Filial B", banco = "ERP_FILIAL_B", digito = 2, tabela_prod = 1, prefixo = "", tabref = "2020.02"))
  empresas <- rbind(empresas, data.frame(cnpj = "00000000000440", Nome = "São Luís", banco = "ERP_SAO_LUIS", digito = 1, tabela_prod = 1, prefixo = "", tabref = "2017.07"))
  empresas <- rbind(empresas, data.frame(cnpj = "00000000000530", Nome = "Filial C", banco = "ERP_FILIAL_C", digito = 1, tabela_prod = 1, prefixo = "", tabref = "2018.01"))
  empresas <- rbind(empresas, data.frame(cnpj = "00000000000990", Nome = "Especial", banco = "ERP_ESPECIAL", digito = 2, tabela_prod = 1, prefixo = "ERP_ESPECIAL_2.", tabref = "2020.01"))
  empresas <- rbind(empresas, data.frame(cnpj = "00000000000360", Nome = "Teresina", banco = "ERP_TERESINA", digito = 1, tabela_prod = 1, prefixo = "", tabref = "2016.01"))
  empresas <- rbind(empresas, data.frame(cnpj = "00000000000280", Nome = "Fortaleza", banco = "ERP_FORTALEZA", digito = 2, tabela_prod = 2, prefixo = "", tabref = "2018.01"))
  empresas <- rbind(empresas, data.frame(cnpj = "00000000000540", Nome = "Filial F", banco = "ERP_FILIAL_F", digito = 2, tabela_prod = 1, prefixo = "", tabref = "2020.02"))
  empresas <- rbind(empresas, data.frame(cnpj = "00000000000550", Nome = "Filial D", banco = "ERP_FILIAL_D", digito = 3, tabela_prod = 1, prefixo = "", tabref = "2020.02"))
  empresas <- rbind(empresas, data.frame(cnpj = "00000000000560", Nome = "Filial E", banco = "ERP_FILIAL_E", digito = 1, tabela_prod = 1, prefixo = "", tabref = "2018.02"))

  # tabela_pedido = data.frame(REVENDA = "Teresina")
  # revenda = "FILIAL A"
  # cev = 7128

  revenda <- switch(toupper(revenda),
    "NATAL"        = "Natal",
    "FILIAL A" = "Filial A",
    "FILIAL B" = "Filial B",
    "SÃO LUÍS"     = "São Luís",
    "FILIAL C"         = "Filial C",
    "ESPECIAL"       = "Especial",
    "TERESINA"     = "Teresina",
    "FORTALEZA"     = "Fortaleza",
    "FILIAL F"   = "Filial F",
    "FILIAL D"     = "Filial D",
    "FILIAL E"    = "Filial E",
    revenda
  )

  con <- conexao_erp(empresas$banco[str_detect(empresas$Nome, revenda)])
  on.exit(dbDisconnect(con), add = TRUE)
  print(glue("Conectou na {empresas$Nome[str_detect(empresas$Nome,revenda)]}"))


  verifica_cev <- dbGetQuery(con, glue("
                              SELECT
                              DISTINCT
                              CP.VDPEDCPE_DTB_X,
                              CP.VDPEDCPE_NPED,
                              R.VDROMCRO_DTB,
                              CP.VDPEDCPE_CODCLI,
                              CP.VDPEDCPE_VEN,
                              CP.VDPEDCPE_SERIE,
                              CP.VDPEDCPE_NFIS,
                              CP.VDPEDCPE_CODTRA,
                              CP.VDPEDCPE_PLACA,
                              CP.VDPEDCPE_MOT,
                              CP.VDPEDCPE_NITENS,
                              CP.VDPEDCPE_IMPR,
                              CP.VDPEDCPE_USUARIO,
                              CP.VDPEDCPE_NFISULT,
                              CP.VDPEDCPE_FLROMA,
                              CP.VDPEDCPE_VLR_OGEM,
                              CP.VDPEDCPE_HORA_GERACAO_NFS,
                              NF.VDFATNFR_INCLDT

                              FROM {empresas$prefixo[str_detect(empresas$Nome,revenda)]}PEDCP0{empresas$digito[str_detect(empresas$Nome,revenda)]} CP
                              INNER JOIN {empresas$prefixo[str_detect(empresas$Nome,revenda)]}CEVPED0{empresas$digito[str_detect(empresas$Nome,revenda)]} C
                              ON C.VDCEVPEN_NPED = CP.VDPEDCPE_NPED
                              INNER JOIN {empresas$prefixo[str_detect(empresas$Nome,revenda)]}CROMA0{empresas$digito[str_detect(empresas$Nome,revenda)]} R
                              ON CAST(R.VDROMCRO_ANOC AS VARCHAR(4)) || RIGHT('00' || LTRIM(RTRIM(CAST(R.VDROMCRO_MESC AS VARCHAR(2)))), 2) || RIGHT('00000' || LTRIM(RTRIM(CAST(R.VDROMCRO_SEQ AS VARCHAR(5)))), 5) = CAST(CP.VDPEDCPE_CROMA AS VARCHAR(15))
                              INNER JOIN {empresas$prefixo[str_detect(empresas$Nome,revenda)]}VDFATN0{empresas$digito[str_detect(empresas$Nome,revenda)]} NF
                              ON NF.VDFATNFR_NNF = CP.VDPEDCPE_NFIS
                              WHERE C.VDCEVPEN_NRCCEV = {cev}"))

  verifica_cev_item <- dbGetQuery(con, glue("
                                           SELECT DISTINCT IT.*
                                           FROM {empresas$prefixo[str_detect(empresas$Nome,revenda)]}PEDIT0{empresas$digito[str_detect(empresas$Nome,revenda)]} IT
                                           INNER JOIN {empresas$prefixo[str_detect(empresas$Nome,revenda)]}CEVPED0{empresas$digito[str_detect(empresas$Nome,revenda)]} C
                                           ON C.VDCEVPEN_NPED = IT.VDPEDIPE_NIT
                                           WHERE C.VDCEVPEN_NRCCEV = {cev}
                                           "))

  if (nrow(verifica_cev) > 0) {
    data_acerto <- verifica_cev$VDROMCRO_DTB[1]
    pedido_acerto <- verifica_cev$VDPEDCPE_NPED[1]
    cliente_acerto <- verifica_cev$VDPEDCPE_CODCLI[1]
    vendedor_acerto <- verifica_cev$VDPEDCPE_VEN[1]
    nf_serie <- verifica_cev$VDPEDCPE_SERIE[1]
    nf <- verifica_cev$VDPEDCPE_NFIS[1]
    cod_transp <- verifica_cev$VDPEDCPE_CODTRA[1]
    placa_acerto <- verifica_cev$VDPEDCPE_PLACA[1]
    mot_acerto <- verifica_cev$VDPEDCPE_MOT[1]
    itens_acerto <- verifica_cev$VDPEDCPE_NITENS[1]
    impr_acerto <- verifica_cev$VDPEDCPE_IMPR[1]
    usuario_acerto <- verifica_cev$VDPEDCPE_USUARIO[1]
    nf_ult_acerto <- verifica_cev$VDPEDCPE_NFISULT[1]
    vlr_orig_acerto <- verifica_cev$VDPEDCPE_VLR_OGEM[1]
    hrger_nf_acerto <- verifica_cev$VDPEDCPE_HORA_GERACAO_NFS[1]
    dt_nfis_acerto <- verifica_cev$VDFATNFR_INCLDT[1]

    pedido_control <- dbGetQuery(con, glue("select max(VDPEDCPE_NPED) + 1 as PEDIDO
                                                       from {empresas$prefixo[str_detect(empresas$Nome,revenda)]}PEDCP0{empresas$digito[str_detect(empresas$Nome,revenda)]}
                                                       where VDPEDCPE_NPED <= {format(Sys.Date(), '%Y%m%d')}9999 and
                                                             VDPEDCPE_NPED > {format(Sys.Date(), '%Y%m%d')}0000"))
    if (is.na(pedido_control$PEDIDO)) {
      pedido_retorno <- paste0(format(Sys.Date(), "%Y%m%d"), "0001")
    } else {
      pedido_retorno <- as.character(pedido_control)
    }


    formato_PEDCP <- data.frame(
      VDPEDCPE_NPED = as.numeric(pedido_retorno),
      VDPEDCPE_DTEMIPED = as.integer(format(Sys.Date(), format = "%Y%m%d")),
      VDPEDCPE_NLOTE = "1",
      VDPEDCPE_CROMA = "0",
      VDPEDCPE_TIPOP = "1",
      VDPEDCPE_TABREF1 = as.numeric(str_split(empresas$tabref[str_detect(empresas$Nome, revenda)], "\\.")[[1]][1]),
      VDPEDCPE_TABREF2 = as.numeric(paste0(str_split(empresas$tabref[str_detect(empresas$Nome, revenda)], "\\.")[[1]][2], "99")),
      VDPEDCPE_CODCLI = as.numeric(cliente_acerto),
      VDPEDCPE_CATCLI = "99",
      VDPEDCPE_VEN = vendedor_acerto,
      VDPEDCPE_TPCOBR = "1",
      VDPEDCPE_CPG = "15",
      VDPEDCPE_DT1VC = as.integer(format(Sys.Date() + 180, format = "%Y%m%d")),
      VDPEDCPE_LINHA_1 = glue("Ref. Comodato : {str_pad(cev, 6,'left','0')}, Nota Fiscal Saida :"),
      VDPEDCPE_LINHA_2 = glue(" {str_pad(nf, 9,'left','0')}/{nf_serie} , emitida em {format(as.Date(as.character(dt_nfis_acerto), '%Y%m%d'),'%d/%m/%Y')}, Nume"),
      VDPEDCPE_LINHA_3 = glue("ros dos Ativos:                            "),
      VDPEDCPE_ORIGEM_PED = "2",
      VDPEDCPE_SERIE = "",
      VDPEDCPE_NFIS = 0,
      VDPEDCPE_CODTRA = cod_transp,
      VDPEDCPE_PLACA = placa_acerto,
      VDPEDCPE_MOT = mot_acerto,
      VDPEDCPE_NITENS = itens_acerto,
      VDPEDCPE_FL = "0",
      VDPEDCPE_IMPR = impr_acerto,
      VDPEDCPE_USUARIO = usuario_acerto,
      VDPEDCPE_NFISULT = nf_ult_acerto,
      VDPEDCPE_DTB_X = 0,
      VDPEDCPE_FLROMA = "N",
      VDPEDCPE_VLR_OGEM = vlr_orig_acerto,
      VDPEDCPE_FILLER_03 = "1",
      VDPEDCPE_EM_ROMANEIO = "",
      VDPEDCPE_TP_ROTEIRIZ = "",
      VDPEDCPE_MULT_RECEBIMENTOS = "N",
      VDPEDCPE_HORA_GERACAO_NFS = hrger_nf_acerto
    )

    formato_PEDIT <- verifica_cev_item
    formato_PEDIT <- formato_PEDIT %>%
      mutate(
        VDPEDIPE_NIT        = as.numeric(pedido_retorno),
        VDPEDIPE_LOGDT      = 0,
        VDPEDIPE_INCLDT     = 0,
        VDPEDIPE_INCLHR     = 0,
        VDPEDIPE_INCLSIGLA  = "",
        VDPEDIPE_NIVELAUDIT = 0,
        VDPEDIPE_PREPRDUS   = as.numeric(0),
        VDPEDIPE_SERIE      = "",
        VDPEDIPE_NUMFAT     = 0,
        VDPEDIPE_NATOP      = 0,
        VDPEDIPE_LINHA      = 0,
        VDPEDIPE_OCOKD      = "99",
        VDPEDIPE_FL         = "",
        VDPEDIPE_MOTTROCA   = "50",
        VDPEDIPE_CFOP_SAIDA = 0,
        VDPEDIPE_SEQ_FIXA   = 0
      )


    dbExecute(con, glue("
                      UPDATE {empresas$prefixo[str_detect(empresas$Nome,revenda)]}PEDCP0{empresas$digito[str_detect(empresas$Nome,revenda)]}
                      SET VDPEDCPE_FL = 8,
                          VDPEDCPE_DTB_X = {data_acerto}
                      WHERE VDPEDCPE_NPED = {pedido_acerto}
                      "))
    dbExecute(con, glue("
                      UPDATE {empresas$prefixo[str_detect(empresas$Nome,revenda)]}CEVPED0{empresas$digito[str_detect(empresas$Nome,revenda)]}
                      SET VDCEVPEN_NPEDR = {pedido_acerto}
                      WHERE VDCEVPEN_NRCCEV = {cev}
                      "))

    # print(glue("NPED: {pedido_retorno} | CODCLI: {cliente_acerto} | CEV: {cev} | REVENDA: {revenda} | CNPJ: {empresas$cnpj[str_detect(empresas$Nome, revenda)]}"))

    
    if (empresas$Nome[str_detect(empresas$Nome, revenda)] == "Especial") {
    
      for (i in seq_len(nrow(formato_PEDCP))) {
        dbAppendTable(
          con,
          Id(
            schema = glue("{sub('\\\\.$', '', empresas$prefixo[str_detect(empresas$Nome, revenda)])}"),
            table  = glue("PEDCP0{empresas$digito[str_detect(empresas$Nome, revenda)]}")
          ),
          formato_PEDCP[i, , drop = FALSE],
          row.names = NULL
        )
      }
    
      for (i in seq_len(nrow(formato_PEDIT))) {
        dbAppendTable(
          con,
          Id(
            schema = glue("{sub('\\\\.$', '', empresas$prefixo[str_detect(empresas$Nome, revenda)])}"),
            table  = glue("PEDIT0{empresas$digito[str_detect(empresas$Nome, revenda)]}")
          ),
          formato_PEDIT[i, , drop = FALSE],
          row.names = NULL
        )
      }
    
    } else {
    
      for (i in seq_len(nrow(formato_PEDCP))) {
        dbAppendTable(
          con,
          glue("{empresas$prefixo[str_detect(empresas$Nome, revenda)]}PEDCP0{empresas$digito[str_detect(empresas$Nome, revenda)]}"),
          formato_PEDCP[i, , drop = FALSE],
          row.names = NULL
        )
      }
    
      for (i in seq_len(nrow(formato_PEDIT))) {
        dbAppendTable(
          con,
          glue("{empresas$prefixo[str_detect(empresas$Nome, revenda)]}PEDIT0{empresas$digito[str_detect(empresas$Nome, revenda)]}"),
          formato_PEDIT[i, , drop = FALSE],
          row.names = NULL
        )
      }
    }

    con_recolha <- conexao_comodato()
    on.exit(dbDisconnect(con_recolha), add = TRUE)

    registro_recolha <- data.frame(
      NPED = as.character(pedido_retorno),
      CODCLI = as.character(cliente_acerto),
      CEV = as.character(cev),
      REVENDA = revenda,
      CNPJ = empresas$cnpj[str_detect(empresas$Nome, revenda)],
      DATA = format(Sys.Date(), format = "%Y%m%d")
    )

    if (!dbExistsTable(con_recolha, "tb_comod_recolha")) {
      dbCreateTable(con_recolha, "tb_comod_recolha", registro_recolha)
    }

    dbAppendTable(con_recolha, "tb_comod_recolha", registro_recolha)

  }

  return(list(formato_PEDCP, formato_PEDIT))
}

# Distrato ----------------------------------------------------------------

distrato_pdf <- function(ncev, cliente, fantasia, cnpj_rev, cnpj_cli, end_cli,
                         cep_cli, produtos_comod) {
  rev_bruto <- conexao_comodato()

  rev_diario <- dbGetQuery(rev_bruto, glue("
      SELECT
          r.razao_social,
          r.logradouro,
          r.bairro,
          r.uf,
          r.cep,
          r.numero,
          r.municipio
      FROM tb_revendas r
      WHERE r.CNPJ_REV = {cnpj_rev}
  "))

  dbDisconnect(rev_bruto)

  nome_rev <- rev_diario$razao_social
  end_rev <- str_to_title(glue("{rev_diario$logradouro}, {rev_diario$numero} - {rev_diario$bairro} - {rev_diario$municipio} - {rev_diario$uf}"))
  cep_rev <- rev_diario$cep
  cid_rev <- rev_diario$municipio

  # caminho_rmd = glue("{diretorio}pages/Comodatos/Dados/")
  # rmd_file <- glue("{caminho_rmd}distrato_comod.Rmd")

  caminho_rmd <- normalizePath(glue("{diretorio}pages/Comodatos/Dados"), winslash = "/")
  rmd_file <- file.path(caminho_rmd, "distrato_comod.Rmd")

  # output_pdf <- file.path(caminho_rmd, glue("DISTRATO_{cnpj_rev}_{cliente}_{ncev}.PDF"))
  output_pdf <- file.path(caminho_rmd, glue("DISTRATO_CEV.PDF"))
  # output_pdf <- glue("{caminho_rmd}CEV_{cod_cliente}_{ncev}.pdf")

  render(rmd_file,
    output_file = output_pdf,
    params = list(
      comodatante = escapar_latex(nome_rev),
      end_comodatante = escapar_latex(end_rev),
      cep_comodatante = cep_rev,
      cnpj_comodatante = cnpj_rev,
      comodataria = escapar_latex(fantasia),
      end_comodataria = escapar_latex(end_cli),
      cnpj_comodataria = cnpj_cli,
      cep_comodataria = cep_cli,
      cid = escapar_latex(cid_rev),
      tabela_agrup = produtos_comod,
      ncev = ncev
    ),
    envir = new.env(),
    quiet = TRUE
  )

  return(output_pdf)
}
