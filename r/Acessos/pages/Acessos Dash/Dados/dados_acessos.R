library(stringr)
library(dplyr)
library(glue)

source(glue("{diretorio}pages/bd_lmo.R"), local = TRUE, encoding = "UTF-8")

# Mesmas funções (e as mesmas colunas de saída) das consultas SQL do original, em dplyr.

# ── Consultas de leitura ──────────────────────────────────────────────────────

acesso_dash <- function() {
  tb("logacesso") |>
    mutate(.quando = data_acesso(dataAcesso)) |>
    filter(.quando >= agora() - as.difftime(7, units = "days")) |>
    inner_join(select(tb("usuario"), login), by = "login") |>
    inner_join(select(tb("dashboard"), iddash = id, Painel = nome, licenca), by = "iddash") |>
    inner_join(select(tb("revenda"), licenca, Revenda = nomeExib), by = "licenca") |>
    arrange(desc(id)) |>
    select(id, login, dataAcesso, Painel, Revenda)
}

paineis_ativos <- function() {
  tb("dashboard") |>
    filter(inativo == "0", !is.na(nome)) |>
    inner_join(tb("revenda"), by = "licenca") |>
    filter(nomeExib != "Lixo") |>
    distinct(id, Painel = nome, Revenda = nomeExib)
}

usuarios_ativos <- function() {
  tb("usuario") |>
    filter(nomeGrupo != "Vazio") |>
    transmute(Login = login, Cargo = cargo, Funcao = funcao, nomeCompleto, nomeGrupo, Revenda)
}

acessos_paineis <- function() {
  tb("usuario") |>
    inner_join(tb("dash_group"), by = "nomeGrupo") |>
    inner_join(select(tb("dashboard"), id, nome, licenca, inativo), by = "id") |>
    inner_join(tb("revenda"), by = "licenca") |>
    filter(inativo == "0", !is.na(nome), nomeGrupo != "Grupo Matriz", nomeExib != "Lixo") |>
    transmute(
      id, Painel = nome, Login = login, Usuario = nomeCompleto, Revenda = nomeExib,
      Grupo = nomeGrupo, Excluir = "❌"
    )
}

acesso_rev <- function() {
  logins <- tb("usuario") |> filter(nomeGrupo != "Vazio") |> distinct(login)
  marcadas <- tb("user_revenda") |> mutate(check = TRUE)
  logins |>
    cross_join(select(tb("revenda"), nome = nomeExib, licenca, nomeR)) |>
    filter(!nomeR %in% c("Lixo")) |>
    left_join(marcadas, by = c("login", "licenca")) |>
    mutate(check = !is.na(check)) |>
    arrange(login, nome) |>
    select(login, nome, licenca, check)
}

# ── Alteração de acessos a painéis ────────────────────────────────────────────

adicion_acesso_usuario <- function(grupo_id, painel_id) {
  tryCatch(
    {
      atual <- tb("dash_group")
      if (!any(atual$nomeGrupo == grupo_id & atual$id == painel_id)) {
        tb_gravar("dash_group", rbind(atual, data.frame(nomeGrupo = grupo_id, id = as.numeric(painel_id))))
      }
      "Acesso adicionado"
    },
    error = function(e) paste("Erro:", conditionMessage(e))
  )
}

excluir_acesso_usuario <- function(grupo_id, painel_id) {
  tryCatch(
    {
      atual <- tb("dash_group")
      tb_gravar("dash_group", atual[!(atual$nomeGrupo == grupo_id & atual$id == painel_id), ])
      "Acesso removido"
    },
    error = function(e) paste("Erro:", conditionMessage(e))
  )
}

# ── Alteração de acesso a revendas ────────────────────────────────────────────

add_ret_acesso_rev <- function(login, licenca, valor) {
  tryCatch(
    {
      valor <- if (is.logical(valor)) {
        valor
      } else if (is.numeric(valor)) {
        valor == 1
      } else {
        tolower(as.character(valor)) %in% c("true", "1")
      }
      atual <- tb("user_revenda")
      sem <- atual[!(atual$login == login & atual$licenca == licenca), ]
      tb_gravar("user_revenda", if (isTRUE(valor)) rbind(sem, data.frame(licenca = licenca, login = login)) else sem)
      "Acesso alterado"
    },
    error = function(e) paste("Erro:", conditionMessage(e))
  )
}

# ── Gestão de usuários ────────────────────────────────────────────────────────

demitir_usuario <- function(login) {
  tryCatch(
    {
      usuarios <- tb("usuario")
      usuarios$nomeGrupo[usuarios$login == login] <- "Vazio"
      tb_gravar("usuario", usuarios)
      "Usuario demitido"
    },
    error = function(e) paste("Erro:", conditionMessage(e))
  )
}

admitir_usuario <- function(login, cargo, nomeCompleto, Revenda) {
  tryCatch(
    {
      usuarios <- tb("usuario")
      if (!login %in% usuarios$login) {
        novo <- usuarios[0, ][1, ]
        novo[1, ] <- NA
        novo$login <- login
        novo$cargo <- cargo
        novo$nomeCompleto <- nomeCompleto
        novo$nomeGrupo <- login
        novo$Revenda <- Revenda
        novo$funcao <- "administrativo"
        tb_gravar("usuario", rbind(usuarios, novo))
        adicion_acesso_usuario(login, 1)
      }
      "Cadastrado com sucesso"
    },
    error = function(e) paste("Erro:", conditionMessage(e))
  )
}
