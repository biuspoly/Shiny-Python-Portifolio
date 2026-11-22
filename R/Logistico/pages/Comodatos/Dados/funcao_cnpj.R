library(jsonlite)
library(stringdist)


dados_cnpj = function(cnpj){
  
  url = paste0("https://brasilapi.com.br/api/cnpj/v1/", cnpj)
  
  response = GET(url)
  socios <- "Dados invalidos"
  
  if (response$status_code == 200) {
    
    data = fromJSON(content(response, "text", encoding = "UTF-8"))
    
    mei = tryCatch(
      data$natureza_juridica,
      error = function(e) NA
    )
    
    if(!is.na(mei) & grepl("INDIVIDUAL", toupper(mei))){
      socios = tryCatch(
        data$razao_social,
        error = function(e) NA
      )
    } else{
      socios = tryCatch(
        data$qsa$nome_socio,
        error = function(e) NA
      )
    }
    
    
  } else {
    url = paste0("https://kitana.opencnpj.com/cnpj/", cnpj)
    
    response_2 = GET(url)
    socios <- "Dados invalidos"
   
    if (response_2$status_code == 200) {
      
      data = fromJSON(content(response_2, "text", encoding = "UTF-8"))
      
      mei = tryCatch(
        data$data$naturezaJuridica,
        error = function(e) NA
      )
      
      if(!is.na(mei) & grepl("INDIVIDUAL", toupper(mei))){
        socios = tryCatch(
          data$data$razaoSocial,
          error = function(e) NA
        )
      } else{
        socios = tryCatch(
          data$data$socios$nomeSocio,
          error = function(e) NA
        )
      }
    } else{
      
      url = paste0("https://receitaws.com.br/v1/cnpj/", cnpj)
      
      response_3 = GET(url)
      socios <- "Dados invalidos"
      
      if (response_3$status_code == 200) {
        
        data = fromJSON(content(response_3, "text", encoding = "UTF-8"))
        
        mei = tryCatch(
          data$natureza_juridica,
          error = function(e) NA
        )
        
        if(!is.na(mei) & grepl("INDIVIDUAL", toupper(mei))){
          socios = tryCatch(
            data$nome,
            error = function(e) NA
          )
        } else{
          socios = tryCatch(
            data$qsa$nome,
            error = function(e) NA
          )
        }
      } else{
        
      }
      
    }
      
     
  }
  
  socios
}

# imagem = "documento.png"
# 
# dados_doc = extrair_doc(api_key, imagem)
# 
# aproximacao = stringdist(dados_doc$nome_completo, socios, method = "jw")
# 
# if(any(aproximacao < 0.1)){
#   print("Compatível")
# } else{
#   print("Não Compatível")
# }

# Portfólio: as consultas acima vão a serviços da internet, que o R do navegador não alcança. Sem a
# resposta, a tela segue como quando a consulta não traz os sócios.
dados_cnpj = function(cnpj){
  NULL
}
