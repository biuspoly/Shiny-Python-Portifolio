library(DBI)
library(stringr)
source(glue("{diretorio}pages/Comodatos/Dados/pdf_portfolio.R"), local = TRUE, encoding = "UTF-8")

gerar_pdf <- function(cliente, revenda, endereco, contato, pto_ref, dia_visit, seq, cep, fone, cnpj, ven, produtos_comod) {
  
  
  # Diretorio atual
  caminho_rmd = glue("{diretorio}pages/Comodatos/Dados/")
  
  con <- conexao_comodato()
  
  cnpj_result <- switch(
    toupper(revenda),
    "NATAL"          = "00000000000100",
    "FILIAL A"   = "00000000000510",
    "FILIAL B"   = "00000000000520",
    "SÃO LUÍS"       = "00000000000440",
    "FILIAL C"           = "00000000000530",
    "ESPECIAL"         = "00000000000990",
    "TERESINA"       = "00000000000360",
    "FORTALEZA"       = "00000000000280",
    "FILIAL F"     = "00000000000540",
    "FILIAL D"       = "00000000000550",
    "FILIAL E"      = "00000000000560",
    NA
  )
  
  
  revenda = dbGetQuery(con, glue("select * from tb_revendas where cnpj_rev = '{cnpj_result}'"))
  
  # caminho absoluto do Rmd e do PDF
  rmd_file <- glue("{caminho_rmd}comodato_pdf1.Rmd")
  output_pdf <- glue("{caminho_rmd}Contrato_CEV.pdf")
  
  render(rmd_file,
         output_file = output_pdf,
         params = list(comodatante = revenda$razao_social,
                       end_comodatante = paste0(revenda$logradouro," ", revenda$numero," - ", revenda$bairro," - ", revenda$municipio, " - ", revenda$uf),
                       cep_comodatante = revenda$cep,
                       cnpj_comodatante = revenda$CNPJ_REV,
                       comodataria = str_extract(cliente, "(?<=-\\s).*"),
                       cod_comodataria = str_extract(cliente, "^[^\\s-]+"),
                       end_comodataria = endereco,
                       cont_comodataria = contato,
                       cnpj_comodataria = cnpj,
                       pto_ref = pto_ref,
                       dias_visit = dia_visit,
                       cep_comodataria = cep,
                       fone = fone,
                       seq = seq,
                       cid_uf = toupper(paste0(revenda$municipio, " - ", revenda$uf)),
                       cid = toupper(revenda$municipio),
                       ven_comodataria = ven,
                       tabela_agrup = produtos_comod
                       # cod_item = str_extract(item, "(?<=-\\s).*"),
                       # desc_item = str_extract(item, "^[^\\s-]+"),
                       # qtd = qtd
                       ),
         envir = globalenv(),
         quiet = TRUE)
  
  
}