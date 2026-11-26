library(stringr)
library(stringdist)

# Portfólio: no original, a foto do documento vai a um serviço de leitura (nome e CPF). Ele não existe
# aqui, e a resposta é a mesma de quando o serviço está fora do ar: a tela libera a confirmação manual.
extrair_doc = function(imagem){
  nome_completo <- "Nao tem"
  cpf <- "Nao tem"

  return(list(nome_completo = nome_completo,
              cpf = cpf,
              api_offline = TRUE))
}
