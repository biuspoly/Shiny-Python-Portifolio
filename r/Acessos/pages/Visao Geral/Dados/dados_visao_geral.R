library(dplyr)
library(glue)

source(glue("{diretorio}pages/bd_lmo.R"), local = TRUE, encoding = "UTF-8")

# Mesmas funções (e as mesmas colunas de saída) das consultas SQL do original, em dplyr.

.acessos_desde <- function(dias) {
  tb("logacesso") |>
    mutate(.quando = data_acesso(dataAcesso)) |>
    filter(.quando >= agora() - as.difftime(dias, units = "days"))
}

kpis_acesso <- function() {
  ultimos <- .acessos_desde(7)
  data.frame(
    total_usuarios = n_distinct(tb("usuario")$login[tb("usuario")$nomeGrupo != "Vazio"]),
    total_paineis = sum(tb("dashboard")$inativo == "0" & !is.na(tb("dashboard")$nome)),
    acessos_7_dias = nrow(ultimos),
    usuarios_ativos_7_dias = n_distinct(ultimos$login)
  )
}

tendencia_acessos <- function() {
  .acessos_desde(30) |>
    mutate(data = as.Date(.quando, tz = "America/Fortaleza")) |>
    group_by(data) |>
    summarise(total_acessos = n(), usuarios_distintos = n_distinct(login), .groups = "drop") |>
    arrange(data)
}

ultimo_acesso_usuario <- function() {
  limite <- agora() - as.difftime(30, units = "days")
  tb("usuario") |>
    filter(nomeGrupo != "Vazio") |>
    left_join(mutate(tb("logacesso"), .quando = data_acesso(dataAcesso)), by = "login") |>
    group_by(login, nome = nomeCompleto, cargo, revenda = Revenda) |>
    summarise(
      ultimo_acesso = suppressWarnings(max(.quando, na.rm = TRUE)),
      acessos_30d = sum(!is.na(.quando) & .quando >= limite),
      .groups = "drop"
    ) |>
    mutate(ultimo_acesso = if_else(is.finite(ultimo_acesso), ultimo_acesso, as.POSIXct(NA))) |>
    arrange(desc(ultimo_acesso)) |>
    as.data.frame()
}
