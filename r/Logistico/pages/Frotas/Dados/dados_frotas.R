suppressPackageStartupMessages({
  library(stringr)
  library(dplyr)
  library(tidyr)
  library(zoo)
  library(lubridate)
  library(glue)
})

# Portfólio: no original estas tabelas saem do MySQL (veículos, tb_renajud, tb_renainf, tb_movimentacao...) e
# são tratadas aqui. O tratamento até a unidade de cada veículo já vem pronto no .parquet fictício (o mesmo
# da versão em Python, que portou este código); daqui para baixo, a partir da entrada e saída, é o original.
ler_frota <- function(nome) as.data.frame(nanoparquet::read_parquet(glue("{diretorio}data/bd_senatran/{nome}.parquet")))

geral_frota <- ler_frota("geral_frota")
geral_renajud <- ler_frota("geral_renajud")
geral_renainf <- ler_frota("geral_renainf")
geral_renainf$VALOR <- as.numeric(geral_renainf$VALOR)
geral_renainf$PAGA <- ifelse(!is.na(geral_renainf$SITUACAO) & geral_renainf$SITUACAO == "PAGAS", "Sim", "Não")

movimentacao <- if (exists(".frota_memoria", envir = globalenv())) {
  get("movimentacao", envir = .frota_memoria)
} else {
  data.frame()
}
if (nrow(movimentacao) == 0) {
  movimentacao <- data.frame(EMPRESA = character(), PLACA = character(), MOTIVO = character(), ANEXO = character())
}

geral_frota[geral_frota == "nan"] <- 0

geral_frota_movim_saida <- geral_frota %>%
  # filter(PLACA == placa) %>%
  group_by(PLACA, CNPJ_EMP) %>%
  summarise(DTA_SAID = max(DTA_EXEC), DTA_EXEC = max(DTA_EXEC)) %>%
  unite("PLACA_CNPJ_DTAEXEC", PLACA, CNPJ_EMP, DTA_EXEC, sep = "", remove = TRUE)
for (linha_saida in 1:nrow(geral_frota_movim_saida)) {
  geral_frota_movim_saida$DTA_SAID[linha_saida] <- ifelse(any(geral_frota_movim_saida$DTA_SAID[linha_saida] < unique(geral_frota$DTA_EXEC)),
    unique(geral_frota$DTA_EXEC)[which(geral_frota_movim_saida$DTA_SAID[linha_saida] < unique(geral_frota$DTA_EXEC))][1],
    NA
  )
}

geral_frota_movim_entrada <- geral_frota %>%
  # filter(PLACA == placa) %>%
  group_by(PLACA, CNPJ_EMP) %>%
  summarise(DTA_ENTR = min(DTA_EXEC), DTA_EXEC = min(DTA_EXEC)) %>%
  unite("PLACA_CNPJ_DTAEXEC", PLACA, CNPJ_EMP, DTA_EXEC, sep = "", remove = TRUE)

geral_frota$PLACA_CNPJ_DTAEXEC <- paste0(geral_frota$PLACA, geral_frota$CNPJ_EMP, geral_frota$DTA_EXEC)
geral_frota <- left_join(geral_frota, geral_frota_movim_entrada, by = "PLACA_CNPJ_DTAEXEC")
geral_frota <- left_join(geral_frota, geral_frota_movim_saida, by = "PLACA_CNPJ_DTAEXEC")

geral_frota$TABELA_FIPE <- as.numeric(gsub("[R$\\.]", "", geral_frota$TABELA_FIPE) %>% gsub(",", ".", .))
geral_frota$DEBITO_DETRAN <- as.numeric(geral_frota$DEBITO_DETRAN)
geral_frota$IPVA <- as.numeric(geral_frota$IPVA)
geral_frota$IPVA_AL_ANT <- as.numeric(geral_frota$IPVA_AL_ANT)
geral_frota$LICENCIAMENTO <- as.numeric(geral_frota$LICENCIAMENTO)
geral_frota$MULTA <- as.numeric(geral_frota$MULTA)
geral_frota$CARROCERIA <- ifelse(
  str_detect(geral_frota$CARROCERIA, "ABER"),
  "ABERTA",
  ifelse(
    geral_frota$CARROCERIA == "" | geral_frota$CARROCERIA == "NA",
    "",
    ifelse(
      str_detect(geral_frota$CARROCERIA, "FECH"),
      "FECHADA",
      geral_frota$CARROCERIA # mantém o resto
    )
  )
)


geral_frota_saida <- geral_frota %>%
  filter(!is.na(DTA_SAID)) %>%
  select(-ANEXO)
geral_frota_saida$CNPJ_PLACA <- paste0(geral_frota_saida$CNPJ_EMP, geral_frota_saida$PLACA)
movimentacao$CNPJ_PLACA <- paste0(movimentacao$EMPRESA, movimentacao$PLACA)

geral_frota_saida <- left_join(geral_frota_saida, movimentacao[, c("CNPJ_PLACA", "MOTIVO", "ANEXO")], "CNPJ_PLACA")
geral_frota_saida$`Informar motivo` <- ifelse(is.na(geral_frota_saida$MOTIVO), "\U0001F4CB", "\u2705")
geral_frota_saida$Anexo <- ifelse(!is.na(geral_frota_saida$ANEXO) & nchar(geral_frota_saida$ANEXO) > 1, "\U0001F4BE", "")

geral_frota_entrada <- geral_frota %>% filter(!is.na(DTA_ENTR))


#
# geral_consolid = geral_frota %>% filter(DTA_EXEC == max(DTA_EXEC))
# geral_renainf_consolid = geral_renainf %>% filter(DTA_EXEC == max(DTA_EXEC))
#
# geral_renainf_detal = inner_join(
#   geral_renainf_consolid,
#   geral_consolid %>% select(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, TRANSFERENCIA, ULT_ROM),
#   by = "PLACA"
# )
