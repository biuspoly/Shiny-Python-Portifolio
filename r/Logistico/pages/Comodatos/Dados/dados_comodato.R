library(DBI)
library(stringr)
library(dplyr)
library(tidyr)
library(zoo)
library(lubridate)
library(glue)



# Configurações do banco --------------------------------------------------

source(glue("{diretorio}pages/Comodatos/Dados/banco_comodato.R"), local = TRUE, encoding = "UTF-8")




# Aba comodatos -----------------------------------------------------------

comod_geral <- function(revenda) {
  con <- conexao_comodato()

  comodatos_geral <- dbGetQuery(con, glue("
                             SELECT
                                  CONCAT(E.EMPRESA, ' - ', C.CEV) AS CEV,
                                  c.CODCOMP,
                                  C.NF,
                                  c.CODCLI AS Cliente,
                                  c.FANTASIA AS Fantasia,
                                  c.NOME AS 'Razão Social',
                                  c.DTE AS 'Data Emissão',
                                  c.DTV AS 'Data Vencimento',
                                  c.Intervalo AS 'Intervalo Vencimento',
                                  c.PRODUTO_GENERICO AS Produto,
                                  c.QTD AS Qtd,
                                  c.Inadimplente AS 'Inadimplencia 60 dias +',
                                  c.`Prazo Envio` AS 'Prazo do Input',
                                  a.usuario as Usuario,
                                  a.dataI,
                                  REPLACE(REPLACE(a.anexo1, 'Anexos/', 'Anexos_Comodato/'), '.PDF', '.pdf') as anexo1,
                                  REPLACE(REPLACE(a.anexo2, 'Anexos/', 'Anexos_Comodato/'), '.PDF', '.pdf') as anexo2,
                                  REPLACE(REPLACE(a.anexo3, 'Anexos/', 'Anexos_Comodato/'), '.PDF', '.pdf') as anexo3,
                                  a.situacao,
                                  c.CNPJ_REV AS cnpj,
                                  i.CHAVE AS CNPJ_CLI,
                                  i.ENDERECO,
                                  i.CEP,
                                  CASE WHEN c.PRE_PED IS NOT NULL THEN 'Dash' ELSE 'ERP' END AS Origem

                             FROM TB_COMODATO C
                             LEFT JOIN TB_EMPRESAS E ON E.CNPJ_EMP = C.CNPJ_REV
                             LEFT JOIN tb_anexos_cev A
                             ON A.CNPJ_REV = C.CNPJ_REV
                             AND A.ncev = C.CEV
                             AND A.situacao <> 'X'
                             LEFT JOIN TB_CLIENTES_INAD I
                             ON I.CNPJ_REV = C.CNPJ_REV
                             AND C.CODCLI = I.CODCLI
                             WHERE E.EMPRESA LIKE '{revenda}%'
                             /*and (E.EMPRESA LIKE '%ESPECIAL%' OR (C.DTE >= 20260324 AND C.PRE_PED IS NOT NULL))*/
                             AND C.QTD > 0;
                             "))

  recolha_geral = dbGetQuery(con, glue("SELECT * FROM TB_COMOD_RECOLHA WHERE REVENDA LIKE '{revenda}%'"))
  dbDisconnect(con)

  comodatos_geral$dataI <- format(as.Date(comodatos_geral$dataI), format = "%Y%m%d")

  ## só vai deixar a Especial (por enquanto)

  comodatos_geral$`Prazo do Input` <- ifelse(is.na(comodatos_geral$dataI), ifelse(comodatos_geral$`Prazo do Input` < 0 & comodatos_geral$cnpj != "00000000000990", "Esgotado", paste(comodatos_geral$`Prazo do Input`, "dias restantes", sep = " ")), NA)
  comodatos_geral$situacao <- ifelse(is.na(comodatos_geral$situacao),
    ifelse(comodatos_geral$`Validacao Intervalo` != "Incorreto" & comodatos_geral$`Inadimplencia 60 dias +` == "Sim" &
      !(is.na(comodatos_geral$dataI) & (Sys.Date() - as.Date(as.character(comodatos_geral$DTE), "%Y%m%d")) > 10), "Pendente", "Bloqueado"),
    comodatos_geral$situacao
  )
  comodatos_geral$situacao[comodatos_geral$situacao == "A"] <- "Processado"
  comodatos_geral$situacao[comodatos_geral$situacao == "P"] <- "Análise"
  comodatos_geral$situacao[comodatos_geral$situacao == "B"] <- "Bloqueado"
  comodatos_geral$situacao[is.na(comodatos_geral$situacao)] <- "Bloqueado"

  comodatos_geral$Doc <- ifelse(is.na(comodatos_geral$anexo1), "", "\U0001FAAA")
  comodatos_geral$`Cev link` <- ifelse(is.na(comodatos_geral$anexo2), "", "\U0001F4DC")
  comodatos_geral$Canhoto <- ifelse(is.na(comodatos_geral$anexo3), "", "\U0001F9FE")
  comodatos_geral$Acao <- comodatos_geral$situacao
  comodatos_geral$Status <- comodatos_geral$situacao
  comodatos_geral$situacao <- NULL
  comodatos_geral$dataI <- NULL

  comodatos_geral <- comodatos_geral %>%
    mutate(Acao = recode(Acao,
      "Pendente" = "\u23F3",
      "Bloqueado" = "\u26D4",
      "Processado" = "\u2705",
      "Análise" = "\u2699\uFE0F",
      "Adicionar" = "\u2795"
    ))

  comodatos_geral$`Data Emissão` <- as.Date(as.character(comodatos_geral$`Data Emissão`), "%Y%m%d")
  comodatos_geral$`Data Vencimento` <- as.Date(as.character(comodatos_geral$`Data Vencimento`), "%Y%m%d")
  comodatos_geral$PesquisaCev <- paste(comodatos_geral$CEV, comodatos_geral$Fantasia, comodatos_geral$`Razão Social`, comodatos_geral$Cliente, sep = " - ")
  
  comodatos_geral$Recolha <- ifelse(
    str_extract(comodatos_geral$CEV, "(?<=- ).*") %in% recolha_geral$CEV,
    "PDF",
    "\U000021A9\U0000FE0F"
  )
  comodatos_geral
}


# Aba Vasilhame -----------------------------------------------------------

saldo_geral <- function(mes_saldo, produtos_filtro) {
  df_empresas <- data.frame(
    # Especial nao tem
    Nome = c("Filial C", "Filial E", "Filial D", "Filial G", "Filial F", "Natal", "Natal Linha B", "Fortaleza", "São Luís", "Teresina", "Filial A", "Filial B"),
    Chave = c("Filial C", "Filial E", "Filial D", "Filial F", "Filial F", "Natal", "Natal", "Fortaleza", "São Luís", "Teresina", "Filial A", "Filial B")
  )

  emprestimo_bloq <- c("808002", "808001", "550013", "550012", "550011", "550001") # Todos de Caixa 600ml

  caixa_1L <- c("690163", "555001")
  caixa_300ml <- c("551003", "551002", "551001", "546004", "061007")
  caixa_600ml_HNK <- c("587003", "587002")
  # filtro_produto = caixa_600ml_HNK

  con <- conexao_comodato()

  comodatos_geral <- dbGetQuery(con, "
                             SELECT
                                  E.EMPRESA AS Revenda,
                                  c.CODCOMP,
                                  C.NF,
                                  c.CODCLI AS Cliente,
                                  c.FANTASIA AS Fantasia,
                                  c.NOME AS 'Razão Social',
                                  c.DTE AS 'Data Emissão',
                                  c.DTV AS 'Data Vencimento',
                                  c.Intervalo AS 'Intervalo Vencimento',
                                  c.PRODUTO_GENERICO AS Produto,
                                  c.QTD AS Qtd,
                                  c.Inadimplente AS 'Inadimplencia 60 dias +',
                                  c.`Prazo Envio` AS 'Prazo do Input',
                                  a.usuario as Usuario,
                                  a.dataI,
                                  REPLACE(REPLACE(a.anexo1, 'Anexos/', 'Anexos_Comodato/'), '.PDF', '.pdf') as anexo1,
                                  REPLACE(REPLACE(a.anexo2, 'Anexos/', 'Anexos_Comodato/'), '.PDF', '.pdf') as anexo2,
                                  REPLACE(REPLACE(a.anexo3, 'Anexos/', 'Anexos_Comodato/'), '.PDF', '.pdf') as anexo3,
                                  a.situacao
                                  /*c.CNPJ_REV AS cnpj,
                                  CASE
                                      WHEN c.`Prazo Envio` < 0
                                      OR EXISTS (
                                          SELECT 1
                                          FROM tb_anexos_cev a2
                                          WHERE a2.situacao = 'B'
                                            AND a2.CNPJ_REV = c.CNPJ_REV
                                      ) THEN 'B'
                                      ELSE a.situacao
                                  END AS situacao*/

                              FROM TB_COMODATO C
                              LEFT JOIN TB_EMPRESAS E ON E.CNPJ_EMP = C.CNPJ_REV
                              LEFT JOIN (SELECT * FROM tb_anexos_cev WHERE situacao <> 'X') A
                                     ON CONCAT(A.CNPJ_REV, A.ncev) = CONCAT(C.CNPJ_REV, C.CEV)
                              /*WHERE (E.EMPRESA LIKE '%ESPECIAL%' OR (C.DTE >= 20260324 AND C.PRE_PED IS NOT NULL));*/
                              /*WHERE c.CODCOMP IN ('555001', '690163')*/
                             ")


  # saldo_geral = dbGetQuery(con, glue("select * from tb_livro_fiscal where produto in ({paste0(\"'\",filtro_produto,\"'\", collapse = ', ')})"))
  saldo_geral <- dbGetQuery(con, glue("select * from tb_livro_fiscal where data >= 20250101 and produto in ({glue_collapse(shQuote(c(caixa_1L, caixa_300ml, caixa_600ml_HNK, emprestimo_bloq)), sep = ',')})"))


  dbDisconnect(con)

  if (!is.null(produtos_filtro)) {
    filtro_produto <- produtos_filtro
  } else {
    filtro_produto <- c(unique(saldo_geral$PRODUTO))
  }

  comodatos_geral$situacao[comodatos_geral$situacao == "A"] <- "Processado"
  comodatos_geral$situacao[comodatos_geral$situacao == "P"] <- "Análise"
  comodatos_geral$situacao[comodatos_geral$situacao == "B"] <- "Bloqueado"
  comodatos_geral$dataI <- format(as.Date(comodatos_geral$dataI), format = "%Y%m%d")
  comodatos_geral$`Prazo do Input` <- ifelse(is.na(comodatos_geral$dataI), ifelse(comodatos_geral$`Prazo do Input` < 0, "Esgotado", paste(comodatos_geral$`Prazo do Input`, "dias restantes", sep = " ")), NA)
  comodatos_geral$situacao <- ifelse(is.na(comodatos_geral$situacao),
    ifelse(comodatos_geral$`Validacao Intervalo` != "Incorreto" & comodatos_geral$Inadimplente == "Sim" &
      !(is.na(comodatos_geral$dataI) & (Sys.Date() - as.Date(as.character(comodatos_geral$DTE), "%Y%m%d")) > 10), "Pendente", "Bloqueado"),
    comodatos_geral$situacao
  )

  comodatos_geral$situacao[comodatos_geral$`Prazo do Input` == "Esgotado"] <- "Bloqueado"

  fortes_revendas <- c("230352", "10637", "11162", "230350", "1180003", "9210002", "90150002")
  sjms_revemdas <- c()
  saldo_geral$QTD <- ifelse(str_detect(saldo_geral$GRUPO_REV, "Filial") & (saldo_geral$CLI %in% fortes_revendas), 0, saldo_geral$QTD)


  livro_fiscal_ano <- saldo_geral %>%
    # filter(PRODUTO %in% c(filtro_produto,emprestimo_bloq)) %>%
    group_by(GRUPO_REV) %>%
    summarise(
      `Recolha Ano` = sum(QTD[operacao == "Dev Emprestimo" & PRODUTO %in% c(filtro_produto)], na.rm = TRUE),
      `Empréstimo Ano` = sum(QTD[operacao == "Emprestei" & PRODUTO %in% c(filtro_produto)], na.rm = TRUE),
      `Recolha Ano 600ml` = sum(QTD[operacao == "Dev Emprestimo" & PRODUTO %in% c(emprestimo_bloq)], na.rm = TRUE),
      `Empréstimo Ano 600ml` = sum(QTD[operacao == "Emprestei" & PRODUTO %in% c(emprestimo_bloq)], na.rm = TRUE)
      # `Status PLP` = ifelse(any(unique(PRODUTO) %in% emprestimo_bloq), "Bloqueado", "Disponível")
    ) %>%
    mutate(`Saldo Ano` = `Recolha Ano` - `Empréstimo Ano`)

  livro_fiscal_mes <- saldo_geral %>%
    filter( # PRODUTO %in% filtro_produto,
      MES_ATUAL == mes_saldo
    ) %>%
    group_by(GRUPO_REV) %>%
    summarise(
      `Recolha Mês` = sum(QTD[operacao == "Dev Emprestimo" & PRODUTO %in% filtro_produto], na.rm = TRUE),
      `Empréstimo Mês` = sum(QTD[operacao == "Emprestei" & PRODUTO %in% filtro_produto], na.rm = TRUE)
    ) %>%
    mutate(`Saldo Mês` = `Recolha Mês` - `Empréstimo Mês`)


  situacao_doc <- comodatos_geral %>%
    filter(
      situacao == "Bloqueado",
      CODCOMP %in% filtro_produto
    ) %>%
    group_by(Revenda) %>%
    summarise(`Status Doc` = paste0(unique(situacao), collapse = "; "))

  situacao_doc$Revenda[situacao_doc$Revenda == "Natal AL 01"] <- "Natal"
  situacao_doc$Revenda[situacao_doc$Revenda == "Especial"] <- "Especial"
  situacao_doc$Revenda[situacao_doc$Revenda == "Filial C 01"] <- "Filial C"

  df_empresas <- left_join(df_empresas, livro_fiscal_ano, by = c("Nome" = "GRUPO_REV"))
  df_empresas <- left_join(df_empresas, livro_fiscal_mes, by = c("Nome" = "GRUPO_REV"))
  df_empresas <- left_join(df_empresas, situacao_doc, by = c("Chave" = "Revenda"))

  if (all(filtro_produto %in% caixa_600ml_HNK)) {
    df_empresas$`Status PLP` <- ifelse((df_empresas$`Saldo Ano` + floor((df_empresas$`Recolha Ano 600ml` - df_empresas$`Empréstimo Ano 600ml`) / 5)) > 0 &
      # df_empresas$`Status PLP` != "Bloqueado" &
      !is.na(df_empresas$`Saldo Ano`), "Disponível", "Bloqueado")
  } else {
    df_empresas$`Status PLP` <- ifelse(df_empresas$`Saldo Ano` > 0 &
      # df_empresas$`Status PLP` != "Bloqueado" &
      !is.na(df_empresas$`Saldo Ano`), "Disponível", "Bloqueado")
  }

  df_empresas <- df_empresas %>%
    arrange(Nome) %>%
    select(-Chave, -`Recolha Ano 600ml`, -`Empréstimo Ano 600ml`)

  df_empresas$`Status Doc`[is.na(df_empresas$`Status Doc`)] <- "Disponível"

  # print(glue("Esses produtos fazem parte do vasilhame de 600? {all(filtro_produto %in% emprestimo_bloq)}"))
  if (all(filtro_produto %in% emprestimo_bloq)) {
    df_empresas$`Status Doc` <- "Bloqueado"
    df_empresas$`Status PLP` <- "Bloqueado"
  }

  saldo_consolidado <- saldo_geral %>%
    filter(PRODUTO %in% c(caixa_1L, caixa_300ml, emprestimo_bloq, caixa_600ml_HNK)) %>%
    group_by(GRUPO_REV) %>%
    summarise(
      `Recolha Ano 1L` = sum(QTD[operacao == "Dev Emprestimo" & PRODUTO %in% c(caixa_1L)], na.rm = TRUE),
      `Empréstimo Ano 1L` = sum(QTD[operacao == "Emprestei" & PRODUTO %in% c(caixa_1L)], na.rm = TRUE),
      `Recolha Ano 300ml` = sum(QTD[operacao == "Dev Emprestimo" & PRODUTO %in% c(caixa_300ml)], na.rm = TRUE),
      `Empréstimo Ano 300ml` = sum(QTD[operacao == "Emprestei" & PRODUTO %in% c(caixa_300ml)], na.rm = TRUE),
      `Recolha Ano 600ml` = sum(QTD[operacao == "Dev Emprestimo" & PRODUTO %in% c(emprestimo_bloq)], na.rm = TRUE),
      `Empréstimo Ano 600ml` = sum(QTD[operacao == "Emprestei" & PRODUTO %in% c(emprestimo_bloq)], na.rm = TRUE),
      `Recolha Ano 600ml MAR` = sum(QTD[operacao == "Dev Emprestimo" & PRODUTO %in% c(caixa_600ml_HNK)], na.rm = TRUE),
      `Empréstimo Ano 600ml MAR` = sum(QTD[operacao == "Emprestei" & PRODUTO %in% c(caixa_600ml_HNK)], na.rm = TRUE)
    ) %>%
    mutate(
      `Caixa 1L` = `Recolha Ano 1L` - `Empréstimo Ano 1L`,
      `Caixa 300` = `Recolha Ano 300ml` - `Empréstimo Ano 300ml`,
      `Total MAR 600` = `Recolha Ano 600ml MAR` - `Empréstimo Ano 600ml MAR` + floor((`Recolha Ano 600ml` - `Empréstimo Ano 600ml`) / 5),
      `Caixa MAR 600` = `Recolha Ano 600ml MAR` - `Empréstimo Ano 600ml MAR`,
      `Bônus MAR 600` = floor((`Recolha Ano 600ml` - `Empréstimo Ano 600ml`) / 5),
      `Caixa 600ml` = `Recolha Ano 600ml` - `Empréstimo Ano 600ml`
    ) %>%
    select(GRUPO_REV, `Caixa 1L`, `Caixa 300`, `Total MAR 600`, `Caixa MAR 600`, `Bônus MAR 600`, `Caixa 600ml`)

  df_empresas <- left_join(df_empresas, saldo_consolidado, by = c("Nome" = "GRUPO_REV"))
  df_empresas[is.na(df_empresas)] <- 0
  df_empresas <- df_empresas %>% select(
    Nome, `Recolha Ano`, `Empréstimo Ano`, `Saldo Ano`, `Recolha Mês`,
    `Empréstimo Mês`, `Saldo Mês`, `Status PLP`, `Status Doc`, `Caixa 1L`,
    `Caixa 300`, `Total MAR 600`, `Caixa MAR 600`, `Bônus MAR 600`, `Caixa 600ml`
  )
}




produtos_livro_fiscal <- function() {
  con <- conexao_comodato()

  emprestimo_bloq <- c("808002", "808001", "550013", "550012", "550011", "550001") # Todos de Caixa 600ml

  caixa_1L <- c("690163", "555001")
  caixa_300ml <- c("551003", "551002", "551001", "546004", "061007")
  caixa_600ml_HNK <- c("587003", "587002")

  # if(!is.null(mes_livro)){
  #   saldo_geral = dbGetQuery(con, glue("select * from tb_livro_fiscal where mes_atual = '{mes_livro}'"))
  # }
  # else{
  #   saldo_geral = dbGetQuery(con, glue("select * from tb_livro_fiscal where 1"))
  # }

  saldo_geral <- dbGetQuery(con, glue("select * from tb_livro_fiscal where produto in ({glue_collapse(shQuote(c(caixa_1L, caixa_300ml, caixa_600ml_HNK, emprestimo_bloq)), sep = ',')})"))

  dbDisconnect(con)

  saldo_geral
}

# Aba solicitacao -----------------------------------------------------------

clientes_inadimplentes <- function() {
  con <- conexao_comodato()

  comodatos_geral <- dbGetQuery(con, "
                             SELECT
                                  E.EMPRESA AS Revenda,
                                  c.CODCOMP,
                                  C.NF,
                                  c.CEV,
                                  c.CODCLI AS Cliente,
                                  c.FANTASIA AS Fantasia,
                                  c.NOME AS 'Razão Social',
                                  c.DTE AS 'Data Emissão',
                                  c.DTV AS 'Data Vencimento',
                                  c.Intervalo AS 'Intervalo Vencimento',
                                  c.PRODUTO_GENERICO AS Produto,
                                  c.QTD AS Qtd,
                                  c.Inadimplente AS 'Inadimplencia 60 dias +',
                                  c.`Prazo Envio` AS 'Prazo do Input',
                                  a.usuario as Usuario,
                                  a.dataI,
                                  c.cnpj_rev,
                                  REPLACE(REPLACE(a.anexo1, 'Anexos/', 'Anexos_Comodato/'), '.PDF', '.pdf') as anexo1,
                                  REPLACE(REPLACE(a.anexo2, 'Anexos/', 'Anexos_Comodato/'), '.PDF', '.pdf') as anexo2,
                                  REPLACE(REPLACE(a.anexo3, 'Anexos/', 'Anexos_Comodato/'), '.PDF', '.pdf') as anexo3,
                                  a.situacao,
                                  concat(c.codcli, c.cnpj_rev) AS CHAVE_CLI,
                                  p.TIPO

                              FROM TB_COMODATO C
                              LEFT JOIN TB_PRODUTOS_CEV P
                    									ON P.CODCOMP = C.CODCOMP
                    									AND C.CNPJ_REV = P.CNPJ_REV
                              LEFT JOIN TB_EMPRESAS E ON E.CNPJ_EMP = C.CNPJ_REV
                              LEFT JOIN (SELECT * FROM tb_anexos_cev WHERE situacao <> 'X') A
                                     ON CONCAT(A.CNPJ_REV, A.ncev) = CONCAT(C.CNPJ_REV, C.CEV)
                              WHERE /*(E.EMPRESA LIKE '%ESPECIAL%' OR (C.DTE >= 20260324 AND C.PRE_PED IS NOT NULL))
                              AND */ C.QTD > 0;
                              /*WHERE c.CODCOMP IN ('555001', '690163')*/
                             ")

  clientes_inad_titulo <- dbGetQuery(con, "select * from tb_clientes_inad")
  dbDisconnect(con)


  comodatos_geral$dataI <- format(as.Date(comodatos_geral$dataI), format = "%Y%m%d")
  comodatos_geral$`Prazo do Input` <- ifelse(is.na(comodatos_geral$dataI), ifelse(comodatos_geral$`Prazo do Input` < 0, "Esgotado", paste(comodatos_geral$`Prazo do Input`, "dias restantes", sep = " ")), NA)
  comodatos_geral$situacao <- ifelse(is.na(comodatos_geral$situacao),
    ifelse(comodatos_geral$`Validacao Intervalo` != "Incorreto" & comodatos_geral$Inadimplente == "Sim" &
      !(is.na(comodatos_geral$dataI) & (Sys.Date() - as.Date(as.character(comodatos_geral$DTE), "%Y%m%d")) > 10), "Pendente", "Bloqueado"),
    comodatos_geral$situacao
  )
  comodatos_geral$situacao[comodatos_geral$situacao == "A"] <- "Processado"
  comodatos_geral$situacao[comodatos_geral$situacao == "P"] <- "Análise"
  comodatos_geral$situacao[comodatos_geral$situacao == "B"] <- "Bloqueado"
  comodatos_geral$situacao[is.na(comodatos_geral$situacao)] <- "Bloqueado"

  comodatos_geral$COD_RS <- paste0(comodatos_geral$Cliente, " - ", comodatos_geral$`Razão Social`)

  ## Caso tenha no minimo, 1 comodato, vai ter que bloquear, pois ele nao foi baixado
  comodatos_cliente <- comodatos_geral %>%
    group_by(CHAVE_CLI) %>%
    summarise(`Status CEV` = n_distinct(CEV))

  ### Status doc
  clientes_inad_doc <- comodatos_geral %>%
    filter(situacao == "Bloqueado") %>%
    group_by(CHAVE_CLI) %>%
    summarise(`Status Doc` = paste0(unique(situacao), collapse = "; "))

  # clientes_inad$Revenda[clientes_inad$Revenda == "Natal AL 01"] = "Natal"
  # clientes_inad$Revenda[clientes_inad$Revenda == "Especial"] = "Especial"
  # clientes_inad$Revenda[clientes_inad$Revenda == "Filial C 01"] = "Filial C"

  ### Status doc
  clientes_inad_titulo <- left_join(clientes_inad_titulo, clientes_inad_doc, by = "CHAVE_CLI")
  clientes_inad_titulo <- left_join(clientes_inad_titulo, comodatos_cliente, by = "CHAVE_CLI")

  #### Geracao dos status
  clientes_inad_titulo$`Status Doc`[is.na(clientes_inad_titulo$`Status Doc`)] <- "Disponível"

  # clientes_inad_titulo$`Status CEV`[is.na(clientes_inad_titulo$`Status CEV`)] = "Disponível"
  clientes_inad_titulo$`Status CEV` <- ifelse(is.na(clientes_inad_titulo$`Status CEV`) | clientes_inad_titulo$`Status CEV` <= 5, "Disponível", "Bloqueado")

  clientes_inad_titulo$`Status Tit` <- ifelse(clientes_inad_titulo$Inadimplente == "Sim", "Bloqueado", "Disponível")

  clientes_inad_titulo$`Status Cad` <- ifelse(
    trimws(clientes_inad_titulo$PROPRIETARIO) == "" |
      is.na(clientes_inad_titulo$PROPRIETARIO) |
      clientes_inad_titulo$CPF_PROP == 0 |
      clientes_inad_titulo$FONE == 0 |
      is.na(clientes_inad_titulo$CPF_PROP) |
      trimws(clientes_inad_titulo$EMAIL_PROP) == "" |
      is.na(clientes_inad_titulo$EMAIL_PROP),
    "Bloqueado",
    "Disponível"
  )

  # ### Alguns da especial tem que desconsiderar -------
  # clientes_inad_titulo$`Status Cad` = ifelse(
  #   clientes_inad_titulo$REVENDA == "Especial" &
  #     clientes_inad_titulo$VEN == "101",
  #   "Disponível",
  #   clientes_inad_titulo$`Status Cad`)

  ### Bloqueio por revenda, vasilhame e material --------

  # emprestimo_bloq = c('808002','808001','550013','550012','550011','550001') # Todos de Caixa 600ml
  # caixa_1L = c('690163', '555001')
  # caixa_300ml = c('551003','551002','551001','546004','061007')
  # caixa_600ml_HNK = c('587003','587002')
  #
  # produtos_vas = c(emprestimo_bloq, caixa_1L, caixa_300ml, caixa_600ml_HNK)
  # bloqueio_revenda_vas = comodatos_geral %>%
  #   filter(`Prazo do Input` == "Esgotado",
  #          CODCOMP %in% produtos_vas) %>%
  #   group_by(cnpj_rev) %>%
  #   summarise(`Prazos Esgotados Vasilhame` = n())

  bloqueio_revenda_mat <- comodatos_geral %>%
    filter(
      `Prazo do Input` == "Esgotado",
      TIPO == "Material",
      `Data Emissão` >= case_when(
        cnpj_rev %in% c("00000000000540", "00000000000560") ~ 20260409, # Filial F / Filial E
        cnpj_rev %in% c("00000000000530") ~ 20260408, # Filial C
        cnpj_rev %in% c("00000000000280") ~ 20260402, # Fortaleza
        cnpj_rev %in% c("00000000000520") ~ 20260401, # Filial B
        cnpj_rev %in% c("00000000000440") ~ 20260402, # São Luís
        cnpj_rev %in% c("00000000000510") ~ 20260324, # Filial A
        cnpj_rev %in% c("00000000000990") ~ 20260420, # Especial
        cnpj_rev %in% c("00000000000100") ~ 20260427, # Natal
        TRUE ~ 20260324
      )
    ) %>%
    group_by(cnpj_rev) %>%
    summarise(`Prazos Esgotados Material` = n())

  # bloqueio_revenda_total <- bind_rows(
  #   bloqueio_revenda_vas,
  #   bloqueio_revenda_mat
  # ) %>%
  #   group_by(cnpj_rev) %>%
  #   summarise(`Prazos Esgotados` = sum(`Prazos Esgotados`), .groups = "drop")

  clientes_inad_titulo <- left_join(clientes_inad_titulo, bloqueio_revenda_mat, by = c("CNPJ_REV" = "cnpj_rev"))

  # clientes_inad_titulo = left_join(clientes_inad_titulo, bloqueio_revenda, by = c("CNPJ_REV" = "cnpj_rev"))


  ## Para desconsiderar os bloqueios, só deixar como comentario as linhas
  clientes_inad_titulo$Solicitacao <- ifelse(
    # clientes_inad_titulo$`Status Doc` == "Disponível" &
    clientes_inad_titulo$`Status Tit` == "Disponível" &
      clientes_inad_titulo$`Status Cad` == "Disponível" &
      # clientes_inad_titulo$`Status CEV` == "Disponível"  &
      is.na(clientes_inad_titulo$`Prazos Esgotados`), "\u2795", "\u26D4"
  )

  ### Alguns da especial tem que desconsiderar -------
  clientes_inad_titulo$Solicitacao <- ifelse(
    (clientes_inad_titulo$REVENDA == "Especial" &
      clientes_inad_titulo$VEN == "101") | (
     clientes_inad_titulo$REVENDA == "Especial" &
       clientes_inad_titulo$CODCLI %in% c('20014', '20041', '20043', '40015', '10504', '10506', '10509', '10510',
                                           '10512', '10513', '20171', '80089', '90086', '120081', '130045', '160010',
                                           '11171', '11257', '11311', '30083', '90199', '100107', '120189', '150123',
                                           '220020', '230009', '240014', '320011', '350006', '350009', '350010', '350011',
                                           '550003', '14840002', '14840003', '14840001', '15010001', '15650002', '15800002',
                                           '15930007', '90245', '120062', '80230', '20432', '230009', '680003', '14840003',
                                           '140016', '120018', '120170','90210','90199','6430004','11369', '160032', '15600002',
                                          '11374', '6430005', '30050', '120167','11387','10877','15540001','320016','120200')
      ) | (clientes_inad_titulo$REVENDA == "Filial C" & 
        clientes_inad_titulo$CODCLI %in% c('11783')),
    "\u2795",
    clientes_inad_titulo$Solicitacao
  )

  clientes_inad_titulo$SEM_DOC <- ifelse(
    (clientes_inad_titulo$REVENDA == "Especial" &
      clientes_inad_titulo$VEN == "101") | (
     clientes_inad_titulo$REVENDA == "Especial" &
      clientes_inad_titulo$CODCLI %in% c('20014', '20041', '20043', '40015', '10504', '10506', '10509', '10510',
                                              '10512', '10513', '20171', '80089', '90086', '120081', '130045', '160010',
                                              '11171', '11257', '11311', '30083', '90199', '100107', '120189', '150123',
                                              '220020', '230009', '240014', '320011', '350006', '350009', '350010', '350011',
                                              '550003', '14840002', '14840003', '14840001', '15010001', '15650002', '15800002',
                                              '15930007', '90245', '120062', '80230', '20432', '230009', '680003', '14840003',
                                              '140016', '120018', '120170','90210','90199','6430004','11369', '160032', '15600002',
                                          '11374', '6430005', '30050', '120167','11387','10877','15540001','320016','120200')
      ) | (clientes_inad_titulo$REVENDA == "Filial C" & 
        clientes_inad_titulo$CODCLI %in% c('11783')),
    TRUE,
    FALSE
  )

  clientes_inad_titulo
}

produtos_solicita <- function(cnpj_rev) {
  con <- conexao_comodato()

  ## QUERY ANTIGA
  produtos <- dbGetQuery(con, glue("
  select
  *
  from tb_produtos_cev
  where cnpj_rev = '{cnpj_rev}' and
        estoque = 'SIM'
  "))

  # produtos = dbGetQuery(con, glue("
  # SELECT
  #     pr.*,
  #     ROUND(pp.preco_un, 2) AS PRECO,
  #     pp.TAB_CEV
  # FROM (
  #     SELECT *
  #     FROM tb_produtos
  #     WHERE cev IS NOT NULL and
  #           cnpj_rev = '{cnpj_rev}'
  # ) pr
  # LEFT JOIN tb_precos_prod pp
  #   ON pp.codcomp = pr.codcomp
  #  AND pp.cnpj_rev = pr.cnpj_rev;
  # "))

  dbDisconnect(con)

  if (is.null(produtos) || nrow(produtos) == 0) {
    return(produtos)
  }

  produtos$CODPROD <- paste0(produtos$CODRED, " - ", str_to_title(produtos$PRODUTO_GENERICO))
  produtos$STATUS_DLP <- ifelse(produtos$STATUS_DLP == "Bloqueado", "Disponível", produtos$STATUS_DLP)
  produtos
}


comod_solicitados <- function(revenda) {
  con <- conexao_comodato()

  if (revenda == "HOLDING") {
    solicitacoes <- dbGetQuery(con, glue("select * from tb_comod_solicitado where prazo is not null and pre_ped is null"))
  } else {
    solicitacoes <- dbGetQuery(con, glue("SELECT
                                            REVENDA, CLIENTE, CNPJ, USUARIO, PRODUTO, CODCOMP, UNIDADE, PRECO,
                                            TIPO, TAB_CEV, VEN, ENDERECO, CONTATO, PTO_REF, DIA_VISIT, SEQ,
                                            CEP, FONE, DATA, VENC, PRAZO, PRE_PED,
                                            SUM(QTD) AS QTD
                                        FROM tb_comod_solicitado
                                        WHERE revenda = '{revenda}'
                                          AND prazo IS NOT NULL
                                          AND pre_ped IS NULL
                                        GROUP BY
                                            REVENDA, CLIENTE, CNPJ, USUARIO, PRODUTO, CODCOMP, UNIDADE, PRECO,
                                            TIPO, TAB_CEV, VEN, ENDERECO, CONTATO, PTO_REF, DIA_VISIT, SEQ,
                                            CEP, FONE, DATA, VENC, PRAZO, PRE_PED;"))
  }

  dbDisconnect(con)

  # if(nrow(solicitacoes) == 0){
  #   solicitacoes$arquivo = NA
  # }
  # else{
  #   solicitacoes$arquivo = "\U0001F4BE"
  # }

  solicitacoes$arquivo <- rep("\U0001F4BE", nrow(solicitacoes))

  solicitacoes
}


detalhes_cli_inad <- function(chave_cli) {
  con <- conexao_comodato()

  pedidos_cli_inad <- dbGetQuery(con, glue("
                             SELECT
                                  C.CEV,
                                  C.CODCOMP AS Código,
                                  c.PRODUTO_GENERICO AS Produto,
                                  c.QTD AS Qtd,
                                  c.DTE AS DT,
                                  c.DTV AS VENC

                             FROM TB_COMODATO C
                             WHERE CONCAT(CODCLI, CNPJ_REV) = {chave_cli}"))
  dbDisconnect(con)

  pedidos_cli_inad
}


# Aba refrigerador --------------------------------------------------------


refrigerador_geral <- function() {
  con <- conexao_comodato()

  refrigeradores <- dbGetQuery(con, glue("
                             SELECT
                                  E.EMPRESA,
                                  R.*
                              FROM TB_EMPRESAS E,
                                   TB_REFRIG_CEV R
                              WHERE E.CNPJ_EMP = R.CNPJ_REV
                              ORDER BY R.NOME
                                        "))
  dbDisconnect(con)

  refrigeradores
}
