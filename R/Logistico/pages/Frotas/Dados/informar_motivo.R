# Portfólio: no original o motivo de saída e a transferência gravam no MySQL (tb_movimentacao e
# tb_transferencia). Aqui ficam na memória da página; os anexos são copiados como no original.
if (!exists(".frota_memoria", envir = globalenv())) {
  assign(".frota_memoria", new.env(), envir = globalenv())
  assign("movimentacao", data.frame(), envir = .frota_memoria)
  assign("transferencias", data.frame(), envir = .frota_memoria)
}

motivo_saida <- function(cnpj_saida_frota, placa_saida_frota, motivo_saida_frota, anexo_saida_frota) {
  registro <- data.frame(
    DATA_HORA = format(Sys.time(), "%Y-%m-%d %H:%M:%S"), EMPRESA = cnpj_saida_frota, PLACA = placa_saida_frota,
    RENAVAM = "", MOTIVO = motivo_saida_frota, ANEXO = anexo_saida_frota
  )
  assign("movimentacao", rbind(get("movimentacao", envir = .frota_memoria), registro), envir = .frota_memoria)
}

anexo_saida <- function(cnpj_saida_frota, placa_saida_frota, local_anexo_saida, nome_anexo_saida) {
  pasta_destino <- glue("{diretorio}pages/Frotas/Dados/Anexos")

  if (!dir.exists(pasta_destino)) {
    dir.create(pasta_destino, recursive = TRUE)
  }

  caminho_anexo <- paste("MOTIVO", placa_saida_frota, cnpj_saida_frota, nome_anexo_saida, sep = "_")

  arquivo_anexo <- file.copy(
    from = local_anexo_saida,
    to = file.path(pasta_destino, caminho_anexo),
    overwrite = TRUE
  )

  if (arquivo_anexo) {
    return(normalizePath(file.path(pasta_destino, caminho_anexo), , winslash = "/"))
  } else {
    return(NA)
  }
}



info_transferencia <- function(cnpj_frota, placa_frota, local_anexo_transf, usuario, revenda_fin) {
  registro <- data.frame(
    DATA_HORA = format(Sys.time(), "%Y-%m-%d %H:%M:%S"), EMPRESA_INI = toupper(cnpj_frota), PLACA = placa_frota,
    EMPRESA_FIN = toupper(revenda_fin), USUARIO = usuario, ANEXO = local_anexo_transf
  )
  assign("transferencias", rbind(get("transferencias", envir = .frota_memoria), registro), envir = .frota_memoria)
}

anexo_transferencia <- function(cnpj_frota, placa_frota, local_anexo_transf, cnpj_final, nome_anexo_transf) {
  pasta_destino <- glue("{diretorio}pages/Frotas/Dados/Anexos")

  if (!dir.exists(pasta_destino)) {
    dir.create(pasta_destino, recursive = TRUE)
  }

  caminho_anexo <- paste("TRANSFERENCIA", placa_frota, cnpj_frota, cnpj_final, nome_anexo_transf, sep = "_")

  arquivo_anexo <- file.copy(
    from = local_anexo_transf,
    to = file.path(pasta_destino, caminho_anexo),
    overwrite = TRUE
  )

  if (arquivo_anexo) {
    return(normalizePath(file.path(pasta_destino, caminho_anexo), , winslash = "/"))
  } else {
    return(NA)
  }
}
