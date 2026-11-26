library(DBI)
library(duckdb)
library(glue)

# Portfólio: no original estas consultas vão ao MySQL (tb_vend_dev_<cnpj>_<período>, tb_vend_dev_itens e
# tb_empresas). Aqui as mesmas tabelas vêm dos .parquet fictícios para um DuckDB em memória, e as consultas
# são as originais -- só as crases do MySQL viram aspas, que é como o DuckDB escreve nome de coluna.
if (!exists(".banco_dev", envir = globalenv())) {
  assign(".banco_dev", duckdb::duckdb(), envir = globalenv())
  pasta_dev <- glue("{diretorio}data/bd_shiny_bruto/devolucoes")
  # O mês vem gravado em português ("out/2026"); a tela compara com format(data, "%b/%Y"), que no navegador
  # sai na língua do R de lá. Os rótulos são refeitos aqui, no formato que este R escreve.
  meses_pt <- c("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
  no_formato_local <- function(rotulos) {
    distintos <- unique(rotulos)
    partes <- strsplit(distintos, "/", fixed = TRUE)
    convertidos <- vapply(partes, function(x) {
      if (length(x) != 2 || !(x[1] %in% meses_pt)) return(paste(x, collapse = "/"))
      format(as.Date(sprintf("%s-%02d-01", x[2], match(x[1], meses_pt))), "%b/%Y")
    }, character(1))
    convertidos[match(rotulos, distintos)]
  }
  con_carga <- dbConnect(.banco_dev)
  itens <- list()
  for (arquivo in list.files(pasta_dev, pattern = "[.]parquet$", full.names = TRUE)) {
    tabela <- as.data.frame(nanoparquet::read_parquet(arquivo))
    if ("MES_ATUAL" %in% names(tabela)) {
      tabela$MES_ATUAL <- no_formato_local(tabela$MES_ATUAL)
      itens[[length(itens) + 1]] <- data.frame(
        CHAVE_VDI = tabela$CHAVE_VDI, COD_PED = tabela$COD_PED, URLImgCODR = "",
        VDPRDPRD_DESCRI = tabela$PRODUTO_GENERICO, `VALOR VENDA` = tabela$`VALOR VENDA`, TPCOBRA = tabela$TPCOBRA,
        check.names = FALSE
      )
    }
    dbWriteTable(con_carga, sub("[.]parquet$", "", basename(arquivo)), tabela, overwrite = TRUE)
  }
  # Os itens de cada pedido (no original, tabela própria): montados das mesmas linhas de venda.
  itens <- do.call(rbind, itens)
  dbWriteTable(con_carga, "tb_vend_dev_itens", itens[!duplicated(itens$CHAVE_VDI), ], overwrite = TRUE)
  # Esta conexão fica aberta: no DuckDB, fechar a última encerra o banco em memória.
  assign(".ancora_dev", con_carga, envir = globalenv())
}

conexao_dev <- function() dbConnect(.banco_dev)
dbGetQuery <- function(conn, statement, ...) DBI::dbGetQuery(conn, gsub("`", "\"", statement), ...)

CNPJ_DAS_REVENDAS <- c(
  "NATAL" = "00000000000100", "FORTALEZA" = "00000000000280", "TERESINA" = "00000000000360", "SÃO LUÍS" = "00000000000440"
)

# Funcao de mês e data ----------------------------------------------------

data_calend <- function() {
  seq_meses <- rev(seq(from = as.Date("2025-01-01"), to = Sys.Date(), by = "month"))

  meses_dev <- format(seq_meses, "%b/%Y")
  meses_dev[meses_dev == format(Sys.Date(), "%b/%Y")] <- "Mês Atual"

  # Inicializar listas para armazenar colunas
  Meses <- c()
  Dias <- c()
  Labels <- c()

  # Preencher listas
  for (i in seq_along(seq_meses)) {
    mes <- seq_meses[i]
    dias_mes <- seq(
      from = mes,
      to = seq_meses[i] + months(1) - 1,
      by = "day"
    )
    dias_mes <- rev(dias_mes[dias_mes <= Sys.Date()])

    Meses <- c(Meses, rep(meses_dev[i], length(dias_mes)))
    Dias <- c(Dias, dias_mes)
    Labels <- c(Labels, format(dias_mes, "%d/%m/%Y"))
  }

  # Criar data.frame final
  df_datas <- data.frame(
    Mes = Meses,
    Dia = Dias,
    Label = Labels,
    stringsAsFactors = FALSE
  )

  df_datas
}


geral_dev <- function(mes_dev, revenda) {
  cnpj_result <- unname(CNPJ_DAS_REVENDAS[revenda])


  con <- conexao_dev()

  # mes_dev = 'ago/2025'
  # revenda = 'FILIAL A'
  lista_meses <- paste0("'", mes_dev, "'", collapse = ", ")

  if (revenda != "HOLDING") {
    inicio <- Sys.time()

    consulta_sql_partes <- lapply(mes_dev, function(mes) {
      mes_result <- if (mes == "Mês Atual") {
        "atual"
      } else if (mes == format(Sys.Date() %m-% months(1), "%b/%Y")) {
        "ultimo"
      } else if (mes == format(Sys.Date() %m-% months(2), "%b/%Y")) {
        "penultimo"
      } else if (mes == format(Sys.Date() %m-% months(3), "%b/%Y")) {
        "antepenultimo"
      } else {
        "historico"
      }

      lista_meses <- paste0("'", mes, "'", collapse = ", ")

      glue("
      SELECT
        v.*,
        CONCAT(v.MOT, ' - ', v.NOME_MOT) AS COD_MOTORISTA,
        CONCAT(v.COD_VEN, ' - ', v.NOME_VEN) AS COD_VENDEDOR,
        CONCAT(v.CLI, ' - ', v.FANTASIA) AS COD_CLIENTE,
        CONCAT(v.CODR, ' - ', v.PRODUTO_GENERICO) AS COD_PRODUTO,
        e.EMPRESA AS Empresa,
        CASE WHEN v.`VALOR DEVOLUCAO` > 0 THEN 'Sim' ELSE 'Não' END AS Retorno,
        ult.ULT_COMPRA
      FROM tb_vend_dev_{cnpj_result}_{mes_result} v
      LEFT JOIN tb_empresas e ON e.CNPJ_EMP = v.CNPJ_REV
      LEFT JOIN (
        SELECT v2.CLI, MAX(v2.`DATA_VENDA`) AS ULT_COMPRA
        FROM tb_vend_dev_{cnpj_result}_{mes_result} v2
        LEFT JOIN tb_empresas e2 ON e2.CNPJ_EMP = v2.CNPJ_REV
        WHERE v2.`VALOR VENDA` > 0
          AND v2.`Romaneio aberto` = 'Não'
          AND v2.`VALOR DEVOLUCAO` = 0
          AND v2.MES_ATUAL IN ({lista_meses})
          AND UPPER(e2.EMPRESA) LIKE UPPER('%{revenda}%')
        GROUP BY v2.CLI
      ) ult ON v.CLI = ult.CLI
      WHERE v.MES_ATUAL IN ({lista_meses})
        AND UPPER(e.EMPRESA) LIKE UPPER('%{revenda}%')
    ")
    })

    consulta_sql_final <- paste(consulta_sql_partes, collapse = " UNION ALL ")

    dados <- dbGetQuery(con, consulta_sql_final)

    fim <- Sys.time()
    print(fim - inicio)
  } else {
    cnpjs_holding <- unname(CNPJ_DAS_REVENDAS)

    inicio <- Sys.time()

    dados_unidos <- data.frame()

    for (cnpj in cnpjs_holding) {
      consulta_sql_partes <- lapply(mes_dev, function(mes) {
        mes_result <- if (mes == "Mês Atual") {
          "atual"
        } else if (mes == format(Sys.Date() %m-% months(1), "%b/%Y")) {
          "ultimo"
        } else if (mes == format(Sys.Date() %m-% months(2), "%b/%Y")) {
          "penultimo"
        } else if (mes == format(Sys.Date() %m-% months(3), "%b/%Y")) {
          "antepenultimo"
        } else {
          "historico"
        }

        lista_meses <- paste0("'", mes, "'", collapse = ", ")

        glue("
      SELECT
        v.*,
        CONCAT(v.MOT, ' - ', v.NOME_MOT) AS COD_MOTORISTA,
        CONCAT(v.COD_VEN, ' - ', v.NOME_VEN) AS COD_VENDEDOR,
        CONCAT(v.CLI, ' - ', v.FANTASIA) AS COD_CLIENTE,
        CONCAT(v.CODR, ' - ', v.PRODUTO_GENERICO) AS COD_PRODUTO,
        e.EMPRESA AS Empresa,
        CASE WHEN v.`VALOR DEVOLUCAO` > 0 THEN 'Sim' ELSE 'Não' END AS Retorno,
        ult.ULT_COMPRA
      FROM tb_vend_dev_{cnpj}_{mes_result} v
      LEFT JOIN tb_empresas e ON e.CNPJ_EMP = v.CNPJ_REV
      LEFT JOIN (
        SELECT v2.CLI, MAX(v2.`DATA_VENDA`) AS ULT_COMPRA
        FROM tb_vend_dev_{cnpj}_{mes_result} v2
        LEFT JOIN tb_empresas e2 ON e2.CNPJ_EMP = v2.CNPJ_REV
        WHERE v2.`VALOR VENDA` > 0
          AND v2.`Romaneio aberto` = 'Não'
          AND v2.`VALOR DEVOLUCAO` = 0
          AND v2.MES_ATUAL IN ({lista_meses})
        GROUP BY v2.CLI
      ) ult ON v.CLI = ult.CLI
      WHERE v.MES_ATUAL IN ({lista_meses})
    ")
      })

      consulta_sql_final <- paste(consulta_sql_partes, collapse = " UNION ALL ")



      dados <- dbGetQuery(con, consulta_sql_final)

      dados_unidos <- rbind(dados_unidos, dados)
    }
    dados <- dados_unidos

    fim <- Sys.time()
    print(fim - inicio)
  }


  dbDisconnect(con)



  dados$GRUPO_REV <- ifelse(is.na(dados$GRUPO_REV) | dados$GRUPO_REV == "",
    dados$Empresa, dados$GRUPO_REV
  )


  return(dados)
}


geral_dev_itens <- function(mes_dev_itens) {
  con <- conexao_dev()

  lista_itens <- paste("'", mes_dev_itens, "'", collapse = ", ")

  dados <- dbGetQuery(con, glue("Select * from tb_vend_dev_itens where cod_ped in ({lista_itens})"))

  dbDisconnect(con)

  return(dados)
}


geral_dev_mensal <- function(revenda) {
  cnpj_result <- unname(CNPJ_DAS_REVENDAS[revenda])


  con <- conexao_dev()

  # mes_dev = 'ago/2025'
  # revenda = 'FILIAL A'

  if (revenda != "HOLDING") {
    inicio <- Sys.time()

    consulta_sql_partes <- lapply(unique(data_calend()$Mes), function(mes) {
      mes_result <- if (mes == "Mês Atual") {
        "atual"
      } else if (mes == format(Sys.Date() %m-% months(1), "%b/%Y")) {
        "ultimo"
      } else if (mes == format(Sys.Date() %m-% months(2), "%b/%Y")) {
        "penultimo"
      } else if (mes == format(Sys.Date() %m-% months(3), "%b/%Y")) {
        "antepenultimo"
      } else {
        "historico"
      }

      lista_meses <- paste0("'", mes, "'", collapse = ", ")

      glue("
      SELECT
        v.GRUPO_REV,
        e.EMPRESA AS Empresa,
        v.MES_ATUAL,
        v.MES,
        sum(v.`VALOR DEVOLUCAO`) AS Devolução
      FROM tb_vend_dev_{cnpj_result}_{mes_result} v
      LEFT JOIN tb_empresas e
          ON e.CNPJ_EMP = v.CNPJ_REV
      WHERE `VALOR DEVOLUCAO` > 0
      GROUP BY e.EMPRESA, v.GRUPO_REV, v.MES_ATUAL, v.MES
        ")
    })

    consulta_sql_final <- paste(consulta_sql_partes, collapse = " UNION ALL ")

    dados <- dbGetQuery(con, consulta_sql_final)

    fim <- Sys.time()
    print(fim - inicio)
  } else {
    cnpjs_holding <- unname(CNPJ_DAS_REVENDAS)

    inicio <- Sys.time()

    dados_unidos <- data.frame()

    for (cnpj in cnpjs_holding) {
      consulta_sql_partes <- lapply(unique(data_calend()$Mes), function(mes) {
        mes_result <- if (mes == "Mês Atual") {
          "atual"
        } else if (mes == format(Sys.Date() %m-% months(1), "%b/%Y")) {
          "ultimo"
        } else if (mes == format(Sys.Date() %m-% months(2), "%b/%Y")) {
          "penultimo"
        } else if (mes == format(Sys.Date() %m-% months(3), "%b/%Y")) {
          "antepenultimo"
        } else {
          "historico"
        }

        lista_meses <- paste0("'", mes, "'", collapse = ", ")

        glue("
      SELECT
        v.GRUPO_REV,
        e.EMPRESA AS Empresa,
        v.MES_ATUAL,
        v.MES,
        sum(v.`VALOR DEVOLUCAO`) AS Devolução
      FROM tb_vend_dev_{cnpj}_{mes_result} v
      LEFT JOIN tb_empresas e
          ON e.CNPJ_EMP = v.CNPJ_REV
      WHERE `VALOR DEVOLUCAO` > 0
      GROUP BY e.EMPRESA, v.GRUPO_REV, v.MES_ATUAL, v.MES
        ")
      })

      consulta_sql_final <- paste(consulta_sql_partes, collapse = " UNION ALL ")


      dados <- dbGetQuery(con, consulta_sql_final)

      dados_unidos <- rbind(dados_unidos, dados)
    }

    dados <- dados_unidos

    fim <- Sys.time()
    print(fim - inicio)
  }


  dbDisconnect(con)


  dados$GRUPO_REV <- ifelse(is.na(dados$GRUPO_REV) | dados$GRUPO_REV == "",
    dados$Empresa, dados$GRUPO_REV
  )

  return(dados)
}

geral_cx_mensal <- function(revenda) {
  cnpj_result <- unname(CNPJ_DAS_REVENDAS[revenda])


  con <- conexao_dev()

  # mes_dev = 'ago/2025'
  # revenda = 'FILIAL A'

  if (revenda != "HOLDING") {
    inicio <- Sys.time()

    consulta_sql_partes <- lapply(unique(data_calend()$Mes), function(mes) {
      mes_result <- if (mes == "Mês Atual") {
        "atual"
      } else if (mes == format(Sys.Date() %m-% months(1), "%b/%Y")) {
        "ultimo"
      } else if (mes == format(Sys.Date() %m-% months(2), "%b/%Y")) {
        "penultimo"
      } else if (mes == format(Sys.Date() %m-% months(3), "%b/%Y")) {
        "antepenultimo"
      } else {
        "historico"
      }

      lista_meses <- paste0("'", mes, "'", collapse = ", ")

      glue("
      SELECT
        v.GRUPO_REV,
        e.EMPRESA AS Empresa,
        v.MES_ATUAL,
        v.MES,
        sum(v.DEVOLUCAO_CX) AS Devolução
      FROM tb_vend_dev_{cnpj_result}_{mes_result} v
      LEFT JOIN tb_empresas e
          ON e.CNPJ_EMP = v.CNPJ_REV
      WHERE v.DEVOLUCAO_CX > 0
      GROUP BY e.EMPRESA, v.GRUPO_REV, v.MES_ATUAL, v.MES
        ")
    })

    consulta_sql_final <- paste(consulta_sql_partes, collapse = " UNION ALL ")

    dados <- dbGetQuery(con, consulta_sql_final)

    fim <- Sys.time()
    print(fim - inicio)
  } else {
    cnpjs_holding <- unname(CNPJ_DAS_REVENDAS)

    inicio <- Sys.time()

    dados_unidos <- data.frame()

    for (cnpj in cnpjs_holding) {
      consulta_sql_partes <- lapply(unique(data_calend()$Mes), function(mes) {
        mes_result <- if (mes == "Mês Atual") {
          "atual"
        } else if (mes == format(Sys.Date() %m-% months(1), "%b/%Y")) {
          "ultimo"
        } else if (mes == format(Sys.Date() %m-% months(2), "%b/%Y")) {
          "penultimo"
        } else if (mes == format(Sys.Date() %m-% months(3), "%b/%Y")) {
          "antepenultimo"
        } else {
          "historico"
        }

        lista_meses <- paste0("'", mes, "'", collapse = ", ")

        glue("
        SELECT
          v.GRUPO_REV,
          e.EMPRESA AS Empresa,
          v.MES_ATUAL,
          v.MES,
          sum(v.DEVOLUCAO_CX) AS Devolução
        FROM tb_vend_dev_{cnpj}_{mes_result} v
        LEFT JOIN tb_empresas e
            ON e.CNPJ_EMP = v.CNPJ_REV
        WHERE v.DEVOLUCAO_CX > 0
        GROUP BY e.EMPRESA, v.GRUPO_REV, v.MES_ATUAL, v.MES
          ")
      })

      consulta_sql_final <- paste(consulta_sql_partes, collapse = " UNION ALL ")

      cat(consulta_sql_final)

      dados <- dbGetQuery(con, consulta_sql_final)

      dados_unidos <- rbind(dados_unidos, dados)
    }

    dados <- dados_unidos

    fim <- Sys.time()
    print(fim - inicio)
  }


  dbDisconnect(con)


  dados$GRUPO_REV <- ifelse(is.na(dados$GRUPO_REV) | dados$GRUPO_REV == "",
    dados$Empresa, dados$GRUPO_REV
  )


  return(dados)
}
