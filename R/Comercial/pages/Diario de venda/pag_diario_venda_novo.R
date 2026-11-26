pag_diario_vendas <- function() {
  
  # Portfólio: aqui o original desviava uma revenda para um painel externo (fora do portfólio).

  # DEPENDENCIAS --------------------------------------------------------------

  source(glue("{diretorio}pages/Diario de venda/Dados/dados_diario_venda_v8.R"),       local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Diario de venda/Dados/funcoes_cores.R"),              local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Diario de venda/Dados/funcoes_meses.R"),              local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Diario de venda/Dados/funcao_ordenacao_dv.R"),        local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Diario de venda/Dados/funcao_tooltip_fat.R"),         local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Diario de venda/Dados/funcao_tooltip_indicador.R"),   local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Diario de venda/Dados/funcao_tooltip_tend_familia.R"),local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Diario de venda/Dados/funcao_tooltip_tend_categ.R"),  local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Diario de venda/Dados/funcao_tooltip_cob_familia.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Diario de venda/Dados/funcao_tooltip_cob_categ.R"),   local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Diario de venda/Dados/funcao_tooltip_sku_pdv.R"),    local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Diario de venda/Dados/funcao_tooltip_fds.R"),       local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Diario de venda/Dados/atualiza_meta_fabrica.R"),    local = TRUE, encoding = "UTF-8")
  
  
  # SERVER =====================================================================
  
  # 1. CONSTANTES --------------------------------------------------------------
  
  grupos_multi_rev <- c("GRUPO FILIAL", "GRUPO FILIAL PI", "GRUPO FILIAL")
  
  
  # 2. FILTROS -----------------------------------------------------------------
  
  ## Mes e dias uteis ----
  
  meses_rv <- reactive({
    meses_disponiveis_dv(revenda = revenda_query())
  })
  
  observe({
    meses <- meses_rv()
    req(length(meses) > 0)
    updatePickerInput(session, "mes_dv", choices = meses, selected = head(meses, 1))
  })
  
  info_dias_rv <- reactive({
    req(input$mes_dv)
    info_dias_uteis_dv(revenda = revenda_query(), mes = input$mes_dv)
  })
  
  output$card_dias_uteis <- renderUI({
    info <- info_dias_rv()
    div(
      class = "card-dias-uteis",
      div(class = "card-label", "Dias Úteis"),
      div(class = "card-value", if (!is.null(info$DIAS_UTEIS) && !is.na(info$DIAS_UTEIS)) info$DIAS_UTEIS else "-")
    )
  })
  
  output$card_dias_uteis_atual <- renderUI({
    info <- info_dias_rv()
    div(
      class = "card-dias-uteis",
      div(class = "card-label", "Atual"),
      div(class = "card-value", if (!is.null(info$DIAS_UTEIS_ATUAL) && !is.na(info$DIAS_UTEIS_ATUAL)) info$DIAS_UTEIS_ATUAL else "-")
    )
  })
  
  ## GA / VEN / Revenda / Produto ----
  
  filtros_dv_rv <- reactive({
    req(revenda_query(), !str_detect(revenda_query(), "GRUPO"))
    filtros_ga_ven_dv(revenda = revenda_query())
  })
  
  output$ga_dv_ui <- renderUI({
    req(revenda_query())
    rev <- revenda_query()
    if (str_detect(rev, "GRUPO")) {
      if (rev %in% grupos_multi_rev) {
        choices_rev <- revendas_por_grupo[[rev]]
        if (rev == "GRUPO FILIAL") choices_rev <- setdiff(choices_rev, "Filial D")
        pickerInput("rev_dv", "Revenda",
                    choices  = c("Todos", choices_rev),
                    selected = "Todos",
                    multiple = FALSE,
                    options  = pickerOptions(style = "btn-dv-rev", size = 8, container = "body"))
      }
    } else {
      filtros <- filtros_dv_rv()
      pickerInput("ga_dv", "GA", choices = if (!is.null(filtros)) filtros$ga else NULL, multiple = TRUE,
                  options = pickerOptions(noneSelectedText = "Todos", size = 8, style = "btn-dv-ga",
                                          countSelectedText = " {0} Itens", selectedTextFormat = "count > 1",
                                          container = "body", liveSearch = TRUE))
    }
  })
  
  output$ven_dv_ui <- renderUI({
    req(revenda_query())
    if (!str_detect(revenda_query(), "GRUPO")) {
      filtros <- filtros_dv_rv()
      pickerInput("ven_dv", "VEN", choices = if (!is.null(filtros)) filtros$ven else NULL, multiple = TRUE,
                  options = pickerOptions(noneSelectedText = "Todos", size = 8, style = "btn-dv-ven",
                                          countSelectedText = " {0} Itens", selectedTextFormat = "count > 1",
                                          container = "body", liveSearch = TRUE))
    }
  })
  
  
  ## Crossfilter GA <-> VEN ----
  
  observeEvent(input$ga_dv, {
    req(!str_detect(revenda_query(), "GRUPO"))
    filtros <- filtros_dv_rv()
    req(!is.null(filtros))
    ga_sel <- input$ga_dv
    ven_choices <- if (length(ga_sel) == 0) {
      filtros$ven
    } else {
      sort(unique(filtros$pairs$VEN[filtros$pairs$GA %in% ga_sel]))
    }
    updatePickerInput(session, "ven_dv",
                      choices  = ven_choices,
                      selected = intersect(input$ven_dv, ven_choices))
  }, ignoreNULL = FALSE, ignoreInit = TRUE)
  
  observeEvent(input$ven_dv, {
    req(!str_detect(revenda_query(), "GRUPO"))
    filtros <- filtros_dv_rv()
    req(!is.null(filtros))
    ven_sel <- input$ven_dv
    ga_choices <- if (length(ven_sel) == 0) {
      sort(unique(filtros$pairs$GA))
    } else {
      sort(unique(filtros$pairs$GA[filtros$pairs$VEN %in% ven_sel]))
    }
    selected_ga <- if (length(ven_sel) > 0 && length(input$ga_dv) == 0) {
      ga_choices
    } else {
      intersect(input$ga_dv, ga_choices)
    }
    updatePickerInput(session, "ga_dv",
                      choices  = ga_choices,
                      selected = selected_ga)
  }, ignoreNULL = FALSE, ignoreInit = TRUE)

  ## Revenda selecionada — NULL quando "Todos" ----
  # ReactiveVal: so propaga quando o valor semantico muda (NULL/"Todos" -> NULL).
  # Impede que input$rev_dv passando de NULL para "Todos" invalide dados_rv.
  
  rev_dv_selecionada <- local({
    rv <- reactiveVal(NULL)
    observe({
      val <- input$rev_dv
      r   <- if (is.null(val) || length(val) == 0 || val == "Todos") NULL else val
      if (!identical(r, rv())) rv(r)
    })
    rv
  })
  
  ## Botao limpar ----
  
  observeEvent(input$bt_limpa_dv, {
    meses <- meses_rv()
    updatePickerInput(session, "mes_dv", selected = head(meses, 1))
    updatePickerInput(session, "ga_dv",  selected = character(0))
    updatePickerInput(session, "ven_dv", selected = character(0))
    updatePickerInput(session, "rev_dv", selected = "Todos")
  })

  # 3. DADOS - Queries e cache -------------------------------------------------
  
  # bindCache serve resultados identicos do cache de sessao quando os filtros
  # nao mudaram — mesma combinacao de filtros = resposta instantanea.
  
  ## Trigger de invalidacao (dispara re-query apos importar meta fabrica) ----
  
  meta_fab_trigger <- reactiveVal(0)
  
  ## Categorias ----
  
  dados_rv <- reactive({
    meta_fab_trigger()
    req(input$mes_dv)
    categorias_dv(revenda = revenda_query(), mes = input$mes_dv,
                  ga = input$ga_dv, ven = input$ven_dv, rev = rev_dv_selecionada())
  }) %>% bindCache(
    revenda_query(), input$mes_dv, input$ga_dv, input$ven_dv,
    rev_dv_selecionada(), meta_fab_trigger(),
    cache = "session"
  )

  ## Familia / Produto ----

  dados_familia_rv <- reactive({
    meta_fab_trigger()
    req(input$mes_dv)
    familia_dv(revenda = revenda_query(), mes = input$mes_dv,
               ga = input$ga_dv, ven = input$ven_dv, rev = rev_dv_selecionada())
  }) %>% bindCache(
    revenda_query(), input$mes_dv, input$ga_dv, input$ven_dv,
    rev_dv_selecionada(), meta_fab_trigger(),
    cache = "session"
  )

  ## Outros Volumes ----

  dados_outros_rv <- reactive({
    meta_fab_trigger()
    req(input$mes_dv)
    outros_volumes_dv(revenda = revenda_query(), mes = input$mes_dv,
                      ga = input$ga_dv, ven = input$ven_dv, rev = rev_dv_selecionada())
  }) %>% bindCache(
    revenda_query(), input$mes_dv, input$ga_dv, input$ven_dv,
    rev_dv_selecionada(), meta_fab_trigger(),
    cache = "session"
  )
  
  ## Meta Ano (modal de GRUPO) ----
  
  dados_meta_rv <- reactive({
    req(revenda_query())
    meta_ano_dv(revenda = revenda_query())
  }) %>% bindCache(revenda_query(), format(Sys.Date(), "%Y"))

  tipo_meta_abp_rv <- reactive({
    tipo <- input$tipo_meta_abp
    if (is.null(tipo) || !tipo %in% c("Cobertura", "Volume")) "Cobertura" else tipo
  })

  dados_meta_abp_rv <- reactive({
    req(revenda_query())
    meta_abp_dv(revenda = revenda_query(), tipo = tipo_meta_abp_rv())
  }) %>% bindCache(revenda_query(), tipo_meta_abp_rv(), format(Sys.Date(), "%Y"))
  
  ## Pre-carregamento ao abrir a pagina ----
  
  # Somente categorias e pre-carregada — familia e outros carregam via
  # renderReactable, respeitando a ordem definida pelos debounces acima
  observe({ dados_rv() })
  
  
  # 4. METAS FABRICA - Importacao ----------------------------------------------
  
  ## Revenda alvo para importacao ----
  
  revenda_importacao_rv <- reactive({
    rev <- revenda_query()
    req(str_detect(rev, "GRUPO"))
    if (rev %in% grupos_multi_rev) {
      sel <- rev_dv_selecionada()
      if (is.null(sel)) return(NULL)
      sel
    } else {
      revendas_por_grupo[[rev]][1]
    }
  })
  
  ## Helpers de parse (chaves e funcoes internas) ----
  
  chaves_codred <- c("CODRED", "COD_PRODUTO", "CODIGO", "COD", "CODPRODUTO", "MATERIAL")
  chaves_valor  <- c("VALOR", "HL", "VALOR_HL", "META_HL", "META", "META EM HL")
  
  normalizar_cabecalho <- function(x) toupper(trimws(gsub("\\s*\\(.*?\\)", "", as.character(x))))
  
  parse_celulas_meta_fab <- function(celulas, n_cols) {
    primeira_token <- trimws(celulas[[1]][1])
    tem_header     <- !grepl("^\\d", primeira_token) && !is.na(primeira_token)
    
    if (tem_header) {
      if (length(celulas) < 2)
        return(list(erro = "Cabecalho encontrado mas sem linhas de dados abaixo."))
      header    <- sapply(celulas[[1]], normalizar_cabecalho)
      dados_cel <- celulas[-1]
    } else {
      header    <- NULL
      dados_cel <- celulas
    }
    
    df <- as.data.frame(
      do.call(rbind, lapply(dados_cel, function(r) {
        r <- as.character(r)
        if (length(r) < n_cols) c(r, rep(NA_character_, n_cols - length(r))) else r
      })),
      stringsAsFactors = FALSE
    )
    
    idx_cod <- if (!is.null(header)) { m <- which(header %in% chaves_codred); if (!length(m)) 1L else m[1L] } else 1L
    idx_val <- if (!is.null(header)) { m <- which(header %in% chaves_valor);  if (!length(m)) n_cols else m[1L] } else n_cols
    
    df_out <- data.frame(
      CODRED = trimws(df[[idx_cod]]),
      VALOR  = suppressWarnings(as.numeric(gsub(",", ".", trimws(df[[idx_val]]))))
    )
    df_out <- df_out[!is.na(df_out$CODRED) & grepl("^\\d", df_out$CODRED) & !is.na(df_out$VALOR), ]
    
    if (!nrow(df_out))
      return(list(erro = "Nenhuma linha valida. Verifique se os codigos comecam com digito e os valores sao numericos."))
    
    list(dados = df_out)
  }
  
  ## Botao e abertura do modal ----

  rev_meta_fab_alvo <- reactiveVal(NULL)

  output$bt_meta_fab_ui <- renderUI({
    req(revenda_importacao_rv())
    tagList(
      tags$label("Input", class = "control-label"),
      actionButton("bt_meta_fab", "Metas Fábrica", icon = icon("file-import"),
                   class = "btn-dv-fab")
    )
  })

  observeEvent(input$bt_meta_fab, {
    rev <- revenda_importacao_rv()
    req(rev)
    rev_meta_fab_alvo(rev)
    mes     <- input$mes_dv
    mes_fmt <- tryCatch({
      d <- as.Date(paste0(mes, "01"), format = "%Y%m%d")
      format(d, "%m/%Y")
    }, error = function(e) mes)

    grupo             <- revenda_query()
    revendas_grupo    <- revendas_por_grupo[[grupo]]
    rev_choices       <- if (!is.null(revendas_grupo) && length(revendas_grupo) > 1) revendas_grupo else NULL

    # Normaliza para ASCII antes de comparar -- evita mismatch de encoding entre
    # strings do R (CP1252) e valores vindos do browser (UTF-8 marcado)
    sel_safe <- if (!is.null(rev_choices)) {
      m <- rev_choices[iconv(rev_choices, to = "ASCII//TRANSLIT") == iconv(rev, to = "ASCII//TRANSLIT")]
      if (length(m) > 0) m[1] else rev_choices[1]
    } else rev

    rev_meta_fab_alvo(sel_safe)

    showModal(modalDialog(
      title     = "Importar Metas Fábrica",
      size      = "l",
      easyClose = TRUE,
      footer    = tagList(
        uiOutput("bt_confirmar_meta_fab_ui"),
        modalButton("Cancelar")
      ),

      div(class = "alert alert-info", style = "margin-bottom: 12px;",
          icon("circle-info"), " ",
          strong("Mês: "), mes_fmt),

      if (!is.null(rev_choices)) {
        div(style = "margin-bottom: 14px;",
          selectInput(
            "rev_modal_meta_fab",
            strong("Revenda de destino:"),
            choices  = rev_choices,
            selected = sel_safe,
            width    = "100%"
          )
        )
      } else {
        div(class = "alert alert-success", style = "margin-bottom: 12px;",
            icon("check-circle"), " ",
            strong("Revenda: "), rev)
      },

      tags$p("Colunas reconhecidas automaticamente: código (", tags$code("CODRED"),
             ", ", tags$code("MATERIAL"), " etc.) e valor (",
             tags$code("VALOR"), ", ", tags$code("META EM HL"), " etc.).",
             " Registros existentes para esta revenda/mês serão sobrescritos."),

      tags$p(strong("Opção 1 — Colar do Excel (Ctrl+V):")),
      textAreaInput(
        "txt_meta_fab", NULL,
        rows        = 8,
        width       = "100%",
        placeholder = "CODRED\tVALOR\n107522\t150\n152597\t80"
      ),

      tags$hr(style = "margin: 14px 0;"),

      tags$p(strong("Opção 2 — Arquivo .xlsx"),
             tags$small(class = "text-muted",
                        " (dados podem começar em qualquer linha; imagens/cabeçalhos decorativos são ignorados)")),
      fileInput("file_meta_fab", NULL, accept = ".xlsx",
                buttonLabel = tagList(icon("folder-open"), " Escolher .xlsx"),
                placeholder = "Nenhum arquivo selecionado",
                width       = "100%"),

      uiOutput("erro_meta_fab_ui"),
      uiOutput("preview_meta_fab_ui")
    ))

  })

  observeEvent(input$rev_modal_meta_fab, {
    if (!is.null(input$rev_modal_meta_fab) && nzchar(input$rev_modal_meta_fab))
      rev_meta_fab_alvo(input$rev_modal_meta_fab)
  }, ignoreNULL = TRUE)

  ## Parse do input (paste e xlsx) ----
  
  meta_fab_parsed_rv <- reactive({
    arq   <- input$file_meta_fab
    texto <- input$txt_meta_fab
    
    # Arquivo tem prioridade sobre o paste
    if (!is.null(arq)) {
      return(tryCatch({
        df_raw <- readxl::read_excel(arq$datapath, col_names = FALSE, .name_repair = "minimal")
        if (!nrow(df_raw)) return(list(erro = "Arquivo vazio."))
        
        # Converte tudo para caracter
        mat <- matrix(apply(df_raw, 2, function(x) as.character(x)),
                      nrow = nrow(df_raw), ncol = ncol(df_raw))
        
        all_keys <- c(chaves_codred, chaves_valor)
        
        # Varre linhas ate achar cabecalho reconhecivel ou primeira linha de dados numericos
        start_row <- NA_integer_
        for (i in seq_len(nrow(mat))) {
          nonempty <- trimws(mat[i, !is.na(mat[i, ]) & nzchar(trimws(mat[i, ]))])
          if (!length(nonempty)) next
          primeiro <- nonempty[1]
          if (grepl("^\\d", primeiro) || normalizar_cabecalho(primeiro) %in% all_keys) {
            start_row <- i
            break
          }
        }
        
        if (is.na(start_row))
          return(list(erro = "Nao foi possivel localizar os dados no arquivo. Verifique se ha colunas de codigo e valor."))
        
        sub_mat <- mat[start_row:nrow(mat), , drop = FALSE]
        # Remove colunas totalmente vazias
        col_ok  <- apply(sub_mat, 2, function(c) any(!is.na(c) & nzchar(trimws(c))))
        sub_mat <- sub_mat[, col_ok, drop = FALSE]
        n_cols  <- ncol(sub_mat)
        
        if (n_cols < 2)
          return(list(erro = "O arquivo precisa ter pelo menos duas colunas preenchidas (codigo e valor)."))
        
        celulas <- lapply(seq_len(nrow(sub_mat)), function(i) sub_mat[i, ])
        parse_celulas_meta_fab(celulas, n_cols)
        
      }, error = function(e) list(erro = paste("Erro ao ler arquivo:", conditionMessage(e)))))
    }
    
    # Fallback: parse do texto colado
    if (is.null(texto) || !nzchar(trimws(texto))) return(NULL)
    
    linhas <- strsplit(texto, "\n")[[1]]
    linhas <- trimws(linhas)
    linhas <- linhas[nzchar(linhas)]
    if (!length(linhas)) return(list(erro = "Cole pelo menos uma linha de dados."))
    
    celulas <- lapply(linhas, function(l) strsplit(l, "\t")[[1]])
    n_cols  <- max(sapply(celulas, length))
    if (n_cols < 2)
      return(list(erro = "Dados precisam de pelo menos duas colunas separadas por tab."))
    
    celulas <- lapply(celulas, function(r) {
      if (length(r) < n_cols) c(r, rep("", n_cols - length(r))) else r
    })
    parse_celulas_meta_fab(celulas, n_cols)
  })
  
  ## Outputs do modal (erro, preview, botao confirmar) ----
  
  output$erro_meta_fab_ui <- renderUI({
    parsed <- meta_fab_parsed_rv()
    if (!is.null(parsed) && !is.null(parsed$erro))
      div(class = "alert alert-danger", style = "margin-top: 8px;",
          icon("circle-xmark"), " ", parsed$erro)
  })
  
  output$preview_meta_fab_ui <- renderUI({
    parsed <- meta_fab_parsed_rv()
    if (is.null(parsed) || !is.null(parsed$erro)) return(NULL)
    df <- parsed$dados
    tagList(
      div(style = "margin-top: 10px;",
          strong(nrow(df), " produto(s) prontos para importar:")),
      reactableOutput("preview_meta_fab_tbl")
    )
  })
  
  output$preview_meta_fab_tbl <- renderReactable({
    parsed <- meta_fab_parsed_rv()
    req(!is.null(parsed), is.null(parsed$erro))
    reactable(
      parsed$dados,
      theme      = tema_reactable_dv,
      compact    = TRUE,
      bordered   = TRUE,
      highlight  = TRUE,
      pagination = FALSE,
      height     = "280px",
      columns    = list(
        CODRED = colDef(name = "CODRED",     minWidth = 120, align = "left"),
        VALOR  = colDef(name = "Valor (HL)", format = colFormat(separators = TRUE, digits = 2))
      )
    )
  })
  
  output$bt_confirmar_meta_fab_ui <- renderUI({
    parsed <- meta_fab_parsed_rv()
    ok     <- !is.null(parsed) && is.null(parsed$erro)
    actionButton(
      "bt_confirmar_meta_fab",
      label = if (ok) glue("Importar {nrow(parsed$dados)} produto(s)") else "Importar",
      icon  = icon("check"),
      class = if (ok) "btn-success" else "btn-secondary",
      style = if (!ok) "pointer-events: none; opacity: 0.55;" else ""
    )
  })
  
  ## Acao de importacao ----
  
  observeEvent(input$bt_confirmar_meta_fab, {
    parsed <- meta_fab_parsed_rv()
    rev    <- rev_meta_fab_alvo()
    req(!is.null(parsed), is.null(parsed$erro), !is.null(rev))
    
    mes    <- input$mes_dv
    df_ins <- parsed$dados
    df_ins$REVENDA <- rev
    df_ins$MES     <- mes
    
    rev_safe <- gsub("'", "''", rev)
    mes_safe <- gsub("'", "''", mes)
    
    # Grava no banco bruto (fonte) -----------------------------------------------
    con_bruto <- tryCatch(
      dbConnect(RMariaDB::MariaDB(),
                dbname   = strsplit(argumentos_bd$dbname, ",")[[1]][4],
                host     = argumentos_bd$host,
                port     = as.numeric(argumentos_bd$port),
                user     = argumentos_bd$user,
                password = argumentos_bd$password,
                charset  = "utf8mb4"),
      error = function(e) NULL
    )
    if (!is.null(con_bruto)) {
      tryCatch({
        dbExecute(con_bruto, glue("DELETE FROM TB_META_FABRICA WHERE REVENDA = '{rev_safe}' AND MES = '{mes_safe}'"))
        dbAppendTable(con_bruto, "TB_META_FABRICA", df_ins)
      }, error = function(e) NULL)
      dbDisconnect(con_bruto)
    }
    
    # Grava no banco shiny (leitura) + calcula VALOR_UMB via LITRAGEM -----------
    con_shiny <- tryCatch(
      dbConnect(RMariaDB::MariaDB(),
                dbname   = strsplit(argumentos_bd$dbname, ",")[[1]][8],
                host     = argumentos_bd$host,
                port     = as.numeric(argumentos_bd$port),
                user     = argumentos_bd$user,
                password = argumentos_bd$password,
                charset  = "utf8mb4"),
      error = function(e) NULL
    )
    if (is.null(con_shiny)) {
      showNotification("Erro ao conectar ao banco de dados.", type = "error", duration = 6)
      return()
    }
    tryCatch({
      # Busca LITRAGEM em TODAS as revendas do grupo para cobrir produtos
      # que nao tem historico de vendas na revenda especifica selecionada
      todas_revs <- unique(c(
        if (!is.null(rev_aliases_dv[[rev]])) rev_aliases_dv[[rev]] else rev,
        if (!is.null(revendas_por_grupo[[revenda_query()]])) revendas_por_grupo[[revenda_query()]] else rev
      ))
      codreds_sql  <- paste(paste0("'", gsub("'", "''", df_ins$CODRED), "'"), collapse = ",")
      
      revs_sql_lit <- paste(paste0("'", gsub("'", "''", todas_revs), "'"), collapse = ",")
      
      lit_df <- dbGetQuery(con_shiny, glue(
         "SELECT CODRED, MAX(LITRAGEM) AS LITRAGEM
          FROM tb_diario_venda _dv_lit
          WHERE REVENDA IN ({revs_sql_lit}) AND CODRED IN ({codreds_sql})
          GROUP BY CODRED"
      ))
      
      df_shiny           <- merge(df_ins, lit_df, by = "CODRED", all.x = TRUE)
      df_shiny$VALOR_UMB <- round(df_shiny$VALOR * df_shiny$LITRAGEM, 0)
      df_shiny$VALOR_UMB[is.na(df_shiny$VALOR_UMB)] <- 0   # fallback quando LITRAGEM nao encontrada
      df_shiny$LITRAGEM  <- NULL
      
      dbExecute(con_shiny, glue("DELETE FROM tb_meta_fabrica WHERE REVENDA = '{rev_safe}' AND MES = '{mes_safe}'"))
      dbAppendTable(con_shiny, "tb_meta_fabrica", df_shiny)

      removeModal()

      shinyalert(
        title              = "Aguarde",
        text               = paste0("Atualizando tabelas de venda para ", rev, "..."),
        type               = "info",
        showConfirmButton  = FALSE,
        closeOnClickOutside = FALSE,
        closeOnEsc         = FALSE
      )

      tryCatch(
        atualizar_meta_fabrica(rev, mes, argumentos_bd),
        error = function(e) showNotification(
          paste("Meta importada, mas erro ao recalcular tabelas:", conditionMessage(e)),
          type = "warning", duration = 10
        )
      )

      closeAlert()
      meta_fab_trigger(meta_fab_trigger() + 1)
      showNotification(
        glue("{nrow(df_ins)} registro(s) importado(s) para {rev} / {mes}."),
        type = "message", duration = 4
      )
    }, error = function(e) {
      showNotification(paste("Erro na importacao:", conditionMessage(e)), type = "error", duration = 8)
    }, finally = {
      dbDisconnect(con_shiny)
    })
  })
  
  # 5. TOOLTIPS - Historico e hover handlers -----------------------------------
  
  ## Limpar cache ao mudar mes ou revenda ----
  observeEvent(list(input$mes_dv, rev_dv_selecionada()), {
    historico_familia_rv(list())
    historico_cob_familia_rv(list())
  }, ignoreInit = TRUE)
  
  ## Historico de tendencia - categorias ----
  
  historico_por_categoria <- reactiveVal(list())
  
  observe({
    req(historico_ativado())
    tabela_atual <- dados_rv()
    req(!is.null(tabela_atual), nrow(tabela_atual) > 0)

    rev_atual <- revenda_query()
    rev_sel   <- rev_dv_selecionada()
    graficos  <- list()

    for (linha in seq_len(nrow(tabela_atual))) {
      nome_categoria <- as.character(tabela_atual$CATEGORIA[linha])
      nome_nivel     <- as.character(tabela_atual$NIVEL[linha])

      resultado_historico <- tryCatch(
        tooltip_hist_tend(revenda = rev_atual, marca = nome_categoria, nivel = nome_nivel,
                          rev = rev_sel, ga = input$ga_dv, ven = input$ven_dv),
        error = function(e) {
          message("[tooltip_tend_categ] ", nome_nivel, "/", nome_categoria, ": ", conditionMessage(e))
          NULL
        }
      )

      if (!is.null(resultado_historico)) {
        graficos[[nome_categoria]] <- resultado_historico$grafico
      }
    }

    historico_por_categoria(graficos)
  })
  
  ## Historico de cobertura - categorias ----
  
  historico_cob_por_categoria <- reactiveVal(list())
  
  observe({
    req(historico_ativado())
    tabela_atual <- dados_rv()
    req(!is.null(tabela_atual), nrow(tabela_atual) > 0)

    rev_atual    <- revenda_query()
    rev_sel      <- rev_dv_selecionada()
    graficos_cob <- list()

    for (linha in seq_len(nrow(tabela_atual))) {
      nome_categoria <- as.character(tabela_atual$CATEGORIA[linha])

      resultado_cob <- tryCatch(
        tooltip_hist_cob(revenda = rev_atual, categoria = nome_categoria,
                         rev = rev_sel, ga = input$ga_dv, ven = input$ven_dv),
        error = function(e) NULL
      )

      if (!is.null(resultado_cob)) {
        graficos_cob[[nome_categoria]] <- resultado_cob$grafico
      }
    }

    historico_cob_por_categoria(graficos_cob)
  })
  
  ## Painel ativo e botao toggle ----
  
  historico_ativado <- reactiveVal(FALSE)
  
  observeEvent(input$bt_toggle_tooltip, {
    historico_ativado(!historico_ativado())
    session$sendCustomMessage("setDvTooltipAtivo", historico_ativado())
  }, ignoreInit = TRUE)
  
  output$bt_toggle_tooltip_ui <- renderUI({
    ativo <- historico_ativado()
    actionButton(
      "bt_toggle_tooltip",
      label  = if (ativo) "Histórico ligado" else "Histórico",
      icon   = icon("chart-line"),
      class  = if (ativo) "btn-historico-ativo" else "btn-historico-inativo",
      size   = "sm"
    ) %>% tagAppendAttributes(title = "Mostra a evolução ao passar o mouse na tendência e na cobertura")
  })

  ## Indicadores do topo (linha VOLUME TOTAL: os mesmos números da tabela) ----

  output$kpis_dv <- renderUI({
    req(dados_rv(), input$mes_dv)
    total <- dados_rv() %>% filter(CATEGORIA == "VOLUME TOTAL")
    req(nrow(total) > 0)
    total <- total[1, ]

    num <- function(x) {
      x <- suppressWarnings(as.numeric(x))
      if (length(x) == 0 || is.na(x) || x == 0) NA_real_ else x
    }
    fmt <- function(x, casas = 0) {
      if (is.na(x)) return("–")
      trimws(format(round(x, casas), nsmall = casas, big.mark = ".", decimal.mark = ",", scientific = FALSE))
    }
    delta <- function(texto, positivo = NA) {
      classe <- if (is.na(positivo)) "kpi-delta-neutro" else if (positivo) "kpi-delta-pos" else "kpi-delta-neg"
      span(class = paste("kpi-delta", classe), texto)
    }
    variacao <- function(atual, base) {
      if (is.na(atual) || is.na(base)) return(delta("sem ano anterior"))
      v <- atual / base - 1
      delta(paste0(if (v >= 0) "▲ " else "▼ ", fmt(abs(v) * 100, 1), "% vs ano anterior"), v >= 0)
    }
    cartao <- function(titulo, valor, sub, destaque = FALSE) {
      div(class = if (destaque) "dv-kpi dv-kpi-destaque" else "dv-kpi",
          div(class = "dv-kpi-titulo", titulo),
          div(class = "dv-kpi-valor", valor),
          sub)
    }

    real  <- num(total$VOL_MES_ATUAL); tend <- num(total$TEND); meta <- num(total$META_REV)
    ano   <- num(total$VOL_ANO_ANT2);  cob  <- num(total$COB_MES_ATUAL); cob_aa <- num(total$COB_ANO_ANT)
    fat   <- num(total$FAT);           r_hl <- num(total$VENDA_HL)

    sub_tend <- if (!is.na(tend) && !is.na(meta)) delta(paste0(fmt(tend / meta * 100, 1), "% da meta"), tend >= meta) else delta("sem meta")
    sub_meta <- if (is.na(meta) || is.na(real)) delta("sem meta") else if (real >= meta) delta("meta batida", TRUE) else delta(paste0("faltam ", fmt(meta - real), " HL"))
    rot_mes  <- label_mes(as.Date(paste0(input$mes_dv, "01"), format = "%Y%m%d"))

    div(class = "dv-kpis",
      cartao(paste("Realizado", rot_mes), paste(fmt(real), "HL"), variacao(real, ano)),
      cartao("Tendência do mês", paste(fmt(tend), "HL"), sub_tend, destaque = TRUE),
      cartao("Meta revenda", paste(fmt(meta), "HL"), sub_meta),
      cartao("Cobertura (PDVs)", fmt(cob), variacao(cob, cob_aa)),
      cartao("Faturamento", paste("R$", fmt(fat)), if (!is.na(r_hl)) delta(paste0("R$ ", fmt(r_hl, 2), " por HL")) else NULL)
    )
  })
  
  ## Indicadores e faturamento ----
  
  historico_indicador_rv <- reactiveVal(list())
  historico_fat_rv       <- reactiveVal(list())
  
  observe({
    req(historico_ativado())
    tabela_atual <- dados_rv()
    rev_sel      <- rev_dv_selecionada()
    req(!is.null(tabela_atual), nrow(tabela_atual) > 0)

    rev_atual    <- revenda_query()
    graficos_ind <- list()
    graficos_fat <- list()

    for (linha in seq_len(nrow(tabela_atual))) {
      nivel     <- as.character(tabela_atual$NIVEL[linha])
      categoria <- as.character(tabela_atual$CATEGORIA[linha])

      if (nivel == "INDICADOR") {
        resultado <- tryCatch(
          if (grepl("^SKU/PDV", categoria)) {
            tooltip_hist_sku_pdv(revenda = rev_atual, indicador = categoria,
                                 rev = rev_sel, ga = input$ga_dv, ven = input$ven_dv)
          } else if (grepl("^FDS", categoria)) {
            tooltip_hist_fds(revenda = rev_atual, indicador = categoria,
                             rev = rev_sel, ga = input$ga_dv, ven = input$ven_dv)
          } else {
            tooltip_hist_indicador(revenda = rev_atual, indicador = categoria, rev = rev_sel,
                                   ga = input$ga_dv, ven = input$ven_dv)
          },
          error = function(e) { message("[tooltip indicador] ", categoria, ": ", conditionMessage(e)); NULL }
        )
        if (!is.null(resultado)) graficos_ind[[categoria]] <- resultado$grafico

      } else if (nivel == "FATURAMENTO") {
        canal <- sub("^FATURAMENTO ", "", categoria)
        resultado <- tryCatch(
          tooltip_hist_fat(revenda = rev_atual, canal = canal, titulo = categoria, rev = rev_sel),
          error = function(e) NULL
        )
        if (!is.null(resultado)) graficos_fat[[categoria]] <- resultado$grafico
      }
    }

    historico_indicador_rv(graficos_ind)
    historico_fat_rv(graficos_fat)
  })
  
  ## Hover handlers - categorias ----
  
  grafico_tooltip_ativo <- reactiveVal(NULL)
  
  observeEvent(input$dv_categoria_hover, {
    chart <- historico_por_categoria()[[input$dv_categoria_hover]]
    if (!is.null(chart)) { grafico_tooltip_ativo(chart); return() }
    tabela <- dados_rv()
    req(!is.null(tabela))
    idx <- which(as.character(tabela$CATEGORIA) == input$dv_categoria_hover)
    if (!length(idx)) return()
    resultado <- tryCatch(
      tooltip_hist_tend(revenda = revenda_query(), marca = input$dv_categoria_hover,
                        nivel = as.character(tabela$NIVEL[idx[1]]),
                        rev = rev_dv_selecionada(), ga = input$ga_dv, ven = input$ven_dv),
      error = function(e) {
        message("[tooltip_tend_categ hover] ", input$dv_categoria_hover, ": ", conditionMessage(e))
        NULL
      }
    )
    if (!is.null(resultado)) grafico_tooltip_ativo(resultado$grafico)
  })

  observeEvent(input$dv_cob_categoria_hover, {
    chart <- historico_cob_por_categoria()[[input$dv_cob_categoria_hover]]
    if (!is.null(chart)) { grafico_tooltip_ativo(chart); return() }
    resultado <- tryCatch(
      tooltip_hist_cob(revenda = revenda_query(), categoria = input$dv_cob_categoria_hover,
                       rev = rev_dv_selecionada(), ga = input$ga_dv, ven = input$ven_dv),
      error = function(e) NULL
    )
    if (!is.null(resultado)) grafico_tooltip_ativo(resultado$grafico)
  })

  observeEvent(input$dv_indicador_hover, {
    chart <- historico_indicador_rv()[[input$dv_indicador_hover]]
    if (!is.null(chart)) { grafico_tooltip_ativo(chart); return() }
    rev_sel   <- rev_dv_selecionada()
    categoria <- input$dv_indicador_hover
    resultado <- tryCatch(
      if (grepl("^SKU/PDV", categoria)) {
        tooltip_hist_sku_pdv(revenda = revenda_query(), indicador = categoria,
                             rev = rev_sel, ga = input$ga_dv, ven = input$ven_dv)
      } else if (grepl("^FDS", categoria)) {
        tooltip_hist_fds(revenda = revenda_query(), indicador = categoria,
                         rev = rev_sel, ga = input$ga_dv, ven = input$ven_dv)
      } else {
        tooltip_hist_indicador(revenda = revenda_query(), indicador = categoria,
                               rev = rev_sel, ga = input$ga_dv, ven = input$ven_dv)
      },
      error = function(e) NULL
    )
    if (!is.null(resultado)) grafico_tooltip_ativo(resultado$grafico)
  })

  observeEvent(input$dv_fat_hover, {
    chart <- historico_fat_rv()[[input$dv_fat_hover]]
    if (!is.null(chart)) { grafico_tooltip_ativo(chart); return() }
    categoria <- input$dv_fat_hover
    canal     <- sub("^FATURAMENTO ", "", categoria)
    resultado <- tryCatch(
      tooltip_hist_fat(revenda = revenda_query(), canal = canal, titulo = categoria,
                       rev = rev_dv_selecionada()),
      error = function(e) NULL
    )
    if (!is.null(resultado)) grafico_tooltip_ativo(resultado$grafico)
  })
  
  ## Familia - cache e hover handlers ----
  
  historico_familia_rv     <- reactiveVal(list())
  historico_cob_familia_rv <- reactiveVal(list())
  
  observeEvent(input$familia_grupo_hover, {
    rev_sel <- rev_dv_selecionada()
    chave   <- paste0("grupo:", input$familia_grupo_hover, ":",
                      if (is.null(rev_sel)) "" else rev_sel)
    cache <- historico_familia_rv()
    
    if (!is.null(cache[[chave]])) {
      grafico_tooltip_ativo(cache[[chave]])
      return()
    }
    
    resultado <- tryCatch(
      tooltip_hist_tend_familia(
        revenda    = revenda_query(),
        agrupamento = input$familia_grupo_hover,
        mes        = input$mes_dv,
        rev        = rev_sel
      ),
      error = function(e) NULL
    )
    if (!is.null(resultado)) {
      cache[[chave]] <- resultado$grafico
      historico_familia_rv(cache)
      grafico_tooltip_ativo(resultado$grafico)
    }
  })
  
  observeEvent(input$familia_prod_umb_hover, {
    rev_sel <- rev_dv_selecionada()
    chave   <- paste0("prod_umb:", input$familia_prod_umb_hover, ":",
                      if (is.null(rev_sel)) "" else rev_sel)
    cache <- historico_familia_rv()
    
    if (!is.null(cache[[chave]])) {
      grafico_tooltip_ativo(cache[[chave]])
      return()
    }
    
    fam <- dados_familia_rv()
    idx <- which(as.character(fam$CODRED) == input$familia_prod_umb_hover)
    titulo_prod <- if (length(idx) > 0) {
      fam$PRODUTO[idx[1]]
    } else {
      out <- dados_outros_rv()
      idx2 <- which(as.character(out$CODRED) == input$familia_prod_umb_hover)
      if (length(idx2) > 0) out$PRODUTO[idx2[1]] else input$familia_prod_umb_hover
    }
    
    resultado <- tryCatch(
      tooltip_hist_tend_familia(
        revenda         = revenda_query(),
        codred          = input$familia_prod_umb_hover,
        titulo_override = titulo_prod,
        unidade         = "UMB",
        mes             = input$mes_dv,
        rev             = rev_sel
      ),
      error = function(e) NULL
    )
    if (!is.null(resultado)) {
      cache[[chave]] <- resultado$grafico
      historico_familia_rv(cache)
      grafico_tooltip_ativo(resultado$grafico)
    }
  })
  
  observeEvent(input$familia_prod_hl_hover, {
    rev_sel <- rev_dv_selecionada()
    chave   <- paste0("prod_hl:", input$familia_prod_hl_hover, ":",
                      if (is.null(rev_sel)) "" else rev_sel)
    cache <- historico_familia_rv()
    
    if (!is.null(cache[[chave]])) {
      grafico_tooltip_ativo(cache[[chave]])
      return()
    }
    
    fam <- dados_familia_rv()
    idx <- which(as.character(fam$CODRED) == input$familia_prod_hl_hover)
    titulo_prod <- if (length(idx) > 0) {
      fam$PRODUTO[idx[1]]
    } else {
      out <- dados_outros_rv()
      idx2 <- which(as.character(out$CODRED) == input$familia_prod_hl_hover)
      if (length(idx2) > 0) out$PRODUTO[idx2[1]] else input$familia_prod_hl_hover
    }
    
    resultado <- tryCatch(
      tooltip_hist_tend_familia(
        revenda         = revenda_query(),
        codred          = input$familia_prod_hl_hover,
        titulo_override = titulo_prod,
        unidade         = "HL",
        mes             = input$mes_dv,
        rev             = rev_sel
      ),
      error = function(e) NULL
    )
    if (!is.null(resultado)) {
      cache[[chave]] <- resultado$grafico
      historico_familia_rv(cache)
      grafico_tooltip_ativo(resultado$grafico)
    }
  })
  
  observeEvent(input$familia_cob_hover, {
    rev_sel <- rev_dv_selecionada()
    chave   <- paste0("cob:", input$familia_cob_hover, ":",
                      if (is.null(rev_sel)) "" else rev_sel)
    cache <- historico_cob_familia_rv()
    
    if (!is.null(cache[[chave]])) {
      grafico_tooltip_ativo(cache[[chave]])
      return()
    }
    
    fam   <- dados_familia_rv()
    idx   <- which(as.character(fam$CODRED) == input$familia_cob_hover)
    titulo_cob <- if (length(idx) > 0) {
      fam$PRODUTO[idx[1]]
    } else {
      out <- dados_outros_rv()
      idx2 <- which(as.character(out$CODRED) == input$familia_cob_hover)
      if (length(idx2) > 0) out$PRODUTO[idx2[1]] else input$familia_cob_hover
    }
    
    resultado <- tryCatch(
      tooltip_hist_cob_familia(
        revenda = revenda_query(),
        codred  = input$familia_cob_hover,
        titulo  = titulo_cob,
        rev     = rev_sel
      ),
      error = function(e) NULL
    )
    if (!is.null(resultado)) {
      cache[[chave]] <- resultado$grafico
      historico_cob_familia_rv(cache)
      grafico_tooltip_ativo(resultado$grafico)
    }
  })
  
  ## Switch UMB / HL ----
  
  output$dv_grafico_tooltip <- renderEcharts4r({
    req(grafico_tooltip_ativo())
    grafico_tooltip_ativo()
  })
  
  # 6. TABELAS -----------------------------------------------------------------
  
  ## Tabela Categorias ----
  
  output$tabela_dv_novo <- renderReactable({
    req(dados_rv(), input$mes_dv)
    
    mes_data  <- as.Date(paste0(input$mes_dv, "01"), format = "%Y%m%d")
    rot_atual <- label_mes(mes_data)
    rot_1     <- label_mes(mes_data %m-% months(1))
    rot_2     <- label_mes(mes_data %m-% months(2))
    rot_3     <- label_mes(mes_data %m-% months(3))
    rot_11    <- label_mes(mes_data %m-% months(11))
    rot_aa    <- label_mes(mes_data %m-% months(12))
    rot_aa2   <- label_mes(mes_data %m-% months(24))
    
    categorias = dados_rv()

    nivel_ordem <- c("TOTAL", "MARCA", "SEGMENTO", "SEGMENTO_2", "SKU",
                     "SEGMENTO_3", "INDICADOR", "FATURAMENTO")
    
    categorias <- categorias %>%
      arrange(
        coalesce(match(CATEGORIA, ordem_categ_dv()), 1000L),
        coalesce(match(NIVEL,     nivel_ordem),       99L),
        CATEGORIA
      ) %>%
      select(REVENDA, NIVEL, CATEGORIA, VOL_ANO_RETRASADO, VOL_ANO_ANT, everything())
    
    categorias$CATEGORIA <- as.character(categorias$CATEGORIA)
    
    categorias <- categorias %>%
      mutate(across(where(is.numeric), ~ ifelse(. == 0, NA_real_, .)))
    
    formatar_valor_por_nivel <- function(value, index) {
      if (is.null(value) || is.na(value) || !is.numeric(value)) {
        return("")
      } else {
        nivel <- as.character(categorias$NIVEL[index])
        if (nivel == "INDICADOR") {
          valor_formatado <- format(round(suppressWarnings(as.numeric(value)), 2), nsmall = 2, big.mark = ".", decimal.mark = ",", scientific = FALSE)
          cat_atual <- as.character(categorias$CATEGORIA[index])
          if (grepl("^SKU/PDV ", cat_atual)) {
            return(valor_formatado)
          }
          return(paste0(valor_formatado, "%"))
        } else if (nivel == "FATURAMENTO") {
          return(format(round(value, 2), nsmall = 2, big.mark = ".", decimal.mark = ",", scientific = FALSE))
        } else {
          return(trimws(format(round(value, 0), big.mark = ".", decimal.mark = ",", scientific = FALSE)))
        }
      }
    }
    
    reactable(
      categorias,
      theme         = tema_reactable_dv,
      defaultColDef = colDef(
        align    = "center",
        minWidth = 60
      ),
      columns = list(
        
        REVENDA = colDef(show = FALSE),
        NIVEL   = colDef(show = FALSE),
        
        CATEGORIA = colDef(
          name        = "Principais Categorias",
          minWidth    = 130,
          align       = "left",
          headerStyle = cor_cabecalho_dv("CATEGORIA", align = "left"),
          cell        = function(value) formatar_categoria_visual_dv(as.character(value)),
          style = function(value, index) {
            categoria <- as.character(categorias$CATEGORIA[index])
            nivel     <- if (!is.na(categorias$NIVEL[index])) categorias$NIVEL[index] else ""
            c(cor_categoria_dv(categoria = categoria, nivel = nivel),
              marcador_categoria_dv(categoria, nivel))
          }
        ),
        
        VOL_ANO_RETRASADO = colDef(
          name        = glue("{rot_aa2}"),
          html        = TRUE,
          cell        = formatar_valor_por_nivel,
          headerStyle = cor_cabecalho_dv("VOL_ANO_RETRASADO"),
          style = function(value, index) {
            cor_categoria_dv(
              categoria = as.character(categorias$CATEGORIA[index]),
              nivel     = if (!is.na(categorias$NIVEL[index])) categorias$NIVEL[index] else ""
            )
          }
        ),
        
        VOL_MES_2 = colDef(
          name        = glue("{rot_2}"),
          html        = TRUE,
          cell        = formatar_valor_por_nivel,
          headerStyle = cor_cabecalho_dv("VOL_MES_2"),
          style = function(value, index) {
            cor_categoria_dv(
              categoria = as.character(categorias$CATEGORIA[index]),
              nivel     = if (!is.na(categorias$NIVEL[index])) categorias$NIVEL[index] else ""
            )
          }
        ),
        
        VOL_MES_ANT = colDef(
          name        = glue("{rot_1}"),
          html        = TRUE,
          cell        = formatar_valor_por_nivel,
          headerStyle = cor_cabecalho_dv("VOL_MES_ANT"),
          style = function(value, index) {
            cor_categoria_dv(
              categoria = as.character(categorias$CATEGORIA[index]),
              nivel     = if (!is.na(categorias$NIVEL[index])) categorias$NIVEL[index] else ""
            )
          }
        ),
        
        META_FAB = colDef(
          name        = "Meta<br/>Fábrica",
          html        = TRUE,
          show        = str_detect(revenda_query(), "GRUPO"),
          cell        = formatar_valor_por_nivel,
          headerStyle = cor_cabecalho_dv("META_FAB"),
          style = function(value, index) {
            cor_categoria_dv(
              categoria = as.character(categorias$CATEGORIA[index]),
              nivel     = if (!is.na(categorias$NIVEL[index])) categorias$NIVEL[index] else ""
            )
          }
        ),
        
        META_REV = colDef(
          name        = "Meta<br/>Revenda",
          html        = TRUE,
          cell        = formatar_valor_por_nivel,
          headerStyle = cor_cabecalho_dv("META_REV"),
          style = function(value, index) {
            nivel <- as.character(categorias$NIVEL[index])
            if (nivel == "INDICADOR") {
              return(cor_meta_rev())
            }
            cor_categoria_dv(
              categoria = as.character(categorias$CATEGORIA[index]),
              nivel     = nivel
            )
          }
        ),
        
        VOL_ANO_ANT = colDef(
          name        = glue("{rot_aa}"),
          html        = TRUE,
          cell        = formatar_valor_por_nivel,
          headerStyle = cor_cabecalho_dv("VOL_ANO_ANT"),
          style = function(value, index) {
            cor_categoria_dv(
              categoria = as.character(categorias$CATEGORIA[index]),
              nivel     = if (!is.na(categorias$NIVEL[index])) categorias$NIVEL[index] else ""
            )
          }
        ),
        
        VOL_ANO_ANT2 = colDef(
          name        = "Real Ano<br/>Anterior",
          html        = TRUE,
          cell        = formatar_valor_por_nivel,
          headerStyle = cor_cabecalho_dv("VOL_ANO_ANT2"),
          style = function(value, index) {
            cor_categoria_dv(
              categoria = as.character(categorias$CATEGORIA[index]),
              nivel     = if (!is.na(categorias$NIVEL[index])) categorias$NIVEL[index] else ""
            )
          }
        ),
        
        VOL_MES_ATUAL = colDef(
          name        = glue("Real<br/>{rot_atual}"),
          html        = TRUE,
          cell        = function(value, index) {
            nivel <- as.character(categorias$NIVEL[index])
            if (nivel %in% c("INDICADOR", "FATURAMENTO")) return("")
            formatar_valor_por_nivel(value, index)
          },
          headerStyle = cor_cabecalho_dv("VOL_MES_ATUAL"),
          style = function(value, index) {
            nivel <- as.character(categorias$NIVEL[index])
            if (nivel %in% c("INDICADOR", "FATURAMENTO")) {
              return(cor_categoria_dv(
                categoria = as.character(categorias$CATEGORIA[index]),
                nivel     = nivel
              ))
            }
            meta <- categorias$VOL_ANO_ANT2[index]
            if (!is.na(value) && !is.na(meta) && value <= meta) {
              if (nivel == "TOTAL") return(cor_meta_bold())
              return(cor_meta())
            }
            cor_categoria_dv(
              categoria = as.character(categorias$CATEGORIA[index]),
              nivel     = nivel
            )
          }
        ),

        TEND = colDef(
          name        = "Tend.<br/>&nbsp;",
          html        = TRUE,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("TEND"),
          class       = "dv-col-chave",
          cell = function(value, index) {
            nivel     <- as.character(categorias$NIVEL[index])
            categoria <- as.character(categorias$CATEGORIA[index])
            if (nivel %in% c("INDICADOR", "FATURAMENTO")) {
              real_value <- categorias$VOL_MES_ATUAL[index]
              formatted  <- formatar_valor_por_nivel(real_value, index)
              if (!nzchar(formatted)) return("")
              if (nivel == "INDICADOR") {
                return(tags$span(style = "cursor: default;", `data-tooltip-indicador` = categoria, formatted))
              } else {
                return(tags$span(style = "cursor: default;", `data-tooltip-fat` = categoria, formatted))
              }
            }
            if (is.na(value)) return("")
            tags$span(
              style                    = "cursor: default;",
              `data-tooltip-categoria` = categoria,
              trimws(format(value, big.mark = ".", decimal.mark = ",", scientific = FALSE))
            )
          },
          style = function(value, index) {
            nivel <- as.character(categorias$NIVEL[index])
            if (nivel %in% c("INDICADOR", "FATURAMENTO")) {
              real_value <- categorias$VOL_MES_ATUAL[index]
              meta       <- categorias$META_REV[index]
              if (!is.na(real_value) && !is.na(meta) && real_value <= meta) return(cor_meta())
              return(cor_categoria_dv(
                categoria = as.character(categorias$CATEGORIA[index]),
                nivel     = nivel
              ))
            }
            meta <- categorias$VOL_ANO_ANT2[index]
            if (!is.na(value) && !is.na(meta) && value <= meta) return(cor_meta())
            cor_categoria_dv(
              categoria = as.character(categorias$CATEGORIA[index]),
              nivel     = if (!is.na(categorias$NIVEL[index])) categorias$NIVEL[index] else ""
            )
          }
        ),
        
        PERC_TEND = colDef(
          name        = "% Tend./<br/>Revenda",
          html        = TRUE,
          format      = colFormat(percent = TRUE, digits = 1),
          headerStyle = cor_cabecalho_dv("PERC_TEND"),
          style = function(value, index) {
            nivel <- as.character(categorias$NIVEL[index])
            if (nivel %in% c("INDICADOR", "FATURAMENTO")) return(list(background = "none"))
            cor_categoria_dv(
              categoria = as.character(categorias$CATEGORIA[index]),
              nivel     = nivel
            )
          }
        ),
        
        VENDA_HL = colDef(
          name        = "R$/<br/>HL",
          html        = TRUE,
          format      = colFormat(separators = TRUE, digits = 2),
          headerStyle = cor_cabecalho_dv("VENDA_HL"),
          style = function(value, index) {
            nivel <- as.character(categorias$NIVEL[index])
            if (nivel %in% c("INDICADOR", "FATURAMENTO")) return(list(background = "none"))
            cor_categoria_dv(
              categoria = as.character(categorias$CATEGORIA[index]),
              nivel     = nivel
            )
          }
        ),
        
        PERC_VOL_LN = colDef(
          name        = paste0("Sell in<br/>", selo_cabecalho_dv("Vol/ LN")),
          html        = TRUE,
          headerStyle = cor_cabecalho_dv("PERC_VOL_LN"),
          cell = function(value, index) {
            if (is.na(value) || value == 0) return("")
            nivel <- as.character(categorias$NIVEL[index])
            if (nivel == "SKU") {
              paste0(format(round(value * 100, 2), nsmall = 2, big.mark = ".", decimal.mark = ",", scientific = FALSE), "%")
            } else {
              trimws(format(round(value, 0), big.mark = ".", decimal.mark = ",", scientific = FALSE))
            }
          },
          style = function(value, index) {
            nivel <- if (!is.na(categorias$NIVEL[index])) categorias$NIVEL[index] else ""
            if (!nivel %in% c("TOTAL", "SKU")) return(NULL)
            cor_categoria_dv(categoria = as.character(categorias$CATEGORIA[index]), nivel = nivel)
          }
        ),

        PERC_COB_LN = colDef(
          name        = paste0("Diferença<br/>", selo_cabecalho_dv("% Cob/LN")),
          html        = TRUE,
          headerStyle = cor_cabecalho_dv("PERC_COB_LN"),
          cell = function(value, index) {
            if (is.na(value) || value == 0) return("")
            nivel <- as.character(categorias$NIVEL[index])
            if (nivel == "SKU") {
              paste0(format(round(value * 100, 2), nsmall = 2, big.mark = ".", decimal.mark = ",", scientific = FALSE), "%")
            } else {
              trimws(format(round(value, 0), big.mark = ".", decimal.mark = ",", scientific = FALSE))
            }
          },
          style = function(value, index) {
            nivel <- if (!is.na(categorias$NIVEL[index])) categorias$NIVEL[index] else ""
            if (!is.na(value) && value < 0) {
              if (nivel == "TOTAL") return(cor_meta_bold())
              return(cor_meta())
            }
            if (!nivel %in% c("TOTAL", "SKU")) return(NULL)
            cor_categoria_dv(categoria = as.character(categorias$CATEGORIA[index]), nivel = nivel)
          }
        ),

        COB_MES_ANT = colDef(
          name        = glue("Cob.<br/>{rot_1}"),
          html        = TRUE,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("COB_MES_ANT"),
          style = function(value, index) {
            nivel <- if (!is.na(categorias$NIVEL[index])) categorias$NIVEL[index] else ""
            if (nivel != "TOTAL") return(NULL)
            cor_categoria_dv(categoria = as.character(categorias$CATEGORIA[index]), nivel = nivel)
          }
        ),

        COB_ANO_ANT = colDef(
          name        = glue("Cob.<br/>{rot_aa}"),
          html        = TRUE,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("COB_ANO_ANT"),
          style = function(value, index) {
            nivel <- if (!is.na(categorias$NIVEL[index])) categorias$NIVEL[index] else ""
            if (nivel != "TOTAL") return(NULL)
            cor_categoria_dv(categoria = as.character(categorias$CATEGORIA[index]), nivel = nivel)
          }
        ),
        
        COB_MES_ATUAL = colDef(
          name        = glue("Cob.<br/>{rot_atual}"),
          html        = TRUE,
          cell = function(value, index) {
            if (is.null(value) || is.na(value)) {
              return("")
            } else {
              tags$span(
                style                        = "cursor: default;",
                `data-tooltip-cob-categoria` = as.character(categorias$CATEGORIA[index]),
                trimws(format(round(value, 0), big.mark = ".", decimal.mark = ",", scientific = FALSE))
              )
            }
          },
          headerStyle = cor_cabecalho_dv("COB_MES_ATUAL"),
          class       = "dv-col-chave",
          style = function(value, index){
            nivel <- if (!is.na(categorias$NIVEL[index])) categorias$NIVEL[index] else ""
            meta  <- categorias$COB_ANO_ANT[index]
            if (!is.na(value) && !is.na(meta) && value <= meta) {
              if (nivel == "TOTAL") return(cor_meta_bold())
              return(cor_meta())
            }
            if (nivel != "TOTAL") return(NULL)
            cor_categoria_dv(categoria = as.character(categorias$CATEGORIA[index]), nivel = nivel)
          }
        ),
        
        FAT = colDef(
          name        = glue("Fat.<br/>{rot_atual}"),
          html        = TRUE,
          cell        = function(value) {
            if (is.na(value) || value == 0) return("")
            format(round(value, 2), nsmall = 2, big.mark = ".", decimal.mark = ",", scientific = FALSE)
          },
          headerStyle = cor_cabecalho_dv("FAT"),
          minWidth    = 90,
          style = function(value, index) {
            nivel <- if (!is.na(categorias$NIVEL[index])) categorias$NIVEL[index] else ""
            if (nivel != "TOTAL") return(NULL)
            cor_categoria_dv(categoria = as.character(categorias$CATEGORIA[index]), nivel = nivel)
          }
        )

      ),
      # columnGroups = list(
      #   colGroup(
      #     name    = "Cobertura",
      #     columns = c("COB_MES_ANT", "COB_ANO_ANT", "COB_MES_ATUAL"),
      #     headerStyle = list(
      #       background = "#06825D",
      #       color      = "#FFFFFF",
      #       fontWeight = "bold",
      #       fontSize   = "14px",
      #       textAlign  = "center"
      #     )
      #   )
      # ),
      rowStyle   = estilo_row_categorias_dv(categorias$NIVEL, categorias$CATEGORIA),
      bordered   = FALSE,
      highlight  = TRUE,
      striped    = FALSE,
      compact    = TRUE,
      fullWidth  = TRUE,
      resizable  = TRUE,
      wrap       = FALSE,
      pagination = FALSE
    )
  })
  
  ## Tabela Familia / Produto ----
  
  output$tabela_dv_familia <- renderReactable({
    req(dados_familia_rv(), input$mes_dv)
    
    mes_data  <- as.Date(paste0(input$mes_dv, "01"), format = "%Y%m%d")
    rot_atual <- label_mes(mes_data)
    rot_1     <- label_mes(mes_data %m-% months(1))
    rot_2     <- label_mes(mes_data %m-% months(2))
    rot_aa    <- label_mes(mes_data %m-% months(12))
    rot_aa2   <- label_mes(mes_data %m-% months(24))
    
    familia <- dados_familia_rv()
    modo_hl <- isTRUE(input$familia_modo)
    
    familia <- familia %>%
      select(any_of(c(
        "AGRUPAMENTO_VOLUME", "PRODUTO",
        "VOL_ANO_RETRASADO_UMB", "VOL_ANO_RETRASADO_HL",
        "VOL_ANO_ANT_UMB",       "VOL_ANO_ANT_HL",
        "VOL_MES_2_UMB",         "VOL_MES_2_HL",
        "VOL_MES_ANT_UMB",       "VOL_MES_ANT_HL",
        "META_FAB_UMB",          "META_FAB_HL",
        "META_REV_UMB",          "META_REV_HL",
        "VOL_ANO_ANT2_UMB",      "VOL_ANO_ANT2_HL",
        "VOL_MES_ATUAL_UMB",     "VOL_MES_ATUAL_HL",
        "TEND_UMB",              "TEND_HL",
        "PERC_TEND_UMB",         "PERC_TEND_HL",
        "PRECO_MEDIO", "PERC_MKP", "VENDA_HL",
        "COB_MES_ANT", "COB_ANO_ANT", "COB_MES_ATUAL",
        "FAT",
        "REVENDA", "CODRED"
      )))
    
    ordem_agr <- ordem_agrupamento_dv()
    familia <- familia %>%
      mutate(
        AGRUPAMENTO_VOLUME = factor(
          AGRUPAMENTO_VOLUME,
          levels = c(ordem_agr, setdiff(as.character(AGRUPAMENTO_VOLUME), ordem_agr))
        )
      ) %>%
      arrange(AGRUPAMENTO_VOLUME) %>%
      mutate(AGRUPAMENTO_VOLUME = as.character(AGRUPAMENTO_VOLUME))
    
    familia <- familia %>%
      mutate(across(where(is.numeric), ~ ifelse(. == 0, NA_real_, .)))
    
    formatar_tend_familia <- function(valor) {
      if (is.null(valor) || is.na(valor)) return("")
      trimws(format(round(valor, 0), big.mark = ".", decimal.mark = ",", scientific = FALSE))
    }
    
    footer_vol <- function(values) {
      tags$b(trimws(format(round(sum(values, na.rm = TRUE), 0), big.mark = ".", decimal.mark = ",", scientific = FALSE)))
    }
    footer_fat <- function(values) {
      tags$b(trimws(format(round(sum(values, na.rm = TRUE), 2), nsmall = 2, big.mark = ".", decimal.mark = ",", scientific = FALSE)))
    }
    
    reactable(
      familia,
      theme           = tema_reactable_dv,
      groupBy         = "AGRUPAMENTO_VOLUME",
      defaultExpanded = TRUE,
      defaultColDef   = colDef(align = "center", minWidth = 60),
      rowStyle = estilo_row_familia_dv(),
      columns = list(
        
        AGRUPAMENTO_VOLUME = colDef(show = FALSE),
        
        REVENDA = colDef(show = FALSE),
        CODRED  = colDef(show = FALSE),
        
        PRODUTO = colDef(
          name        = "Produto",
          minWidth    = 250,
          align       = "left",
          html        = TRUE,
          aggregate   = "count",
          aggregated  = JS("function(cellInfo) {
            return '<strong>' + cellInfo.row['AGRUPAMENTO_VOLUME'] + '</strong>' +
                   ' <span style=\"color:#888;font-size:0.9em;\">(' + cellInfo.value + ')</span>';
          }"),
          footer      = tags$b("TOTAL GERAL"),
          headerStyle = cor_cabecalho_dv("CATEGORIA", align = "left"),
          cell        = function(value, index) {
            paste0("<span style='padding-left:18px;display:inline-block;'>", value, "</span>")
          }
        ),
        
        VOL_ANO_RETRASADO_UMB = colDef(
          name        = glue("{rot_aa2}"),
          html        = TRUE,
          show        = !modo_hl,
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("VOL_ANO_RETRASADO")
        ),
        VOL_MES_2_UMB = colDef(
          name        = glue("{rot_2}"),
          html        = TRUE,
          show        = !modo_hl,
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("VOL_MES_2")
        ),
        VOL_MES_ANT_UMB = colDef(
          name        = glue("{rot_1}"),
          html        = TRUE,
          show        = !modo_hl,
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("VOL_MES_ANT")
        ),
        META_FAB_UMB = colDef(
          name        = "Meta<br/>Fábrica",
          html        = TRUE,
          show        = !modo_hl && str_detect(revenda_query(), "GRUPO"),
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("META_FAB")
        ),
        META_FAB_HL = colDef(
          name        = "Meta<br/>Fábrica",
          html        = TRUE,
          show        = modo_hl && str_detect(revenda_query(), "GRUPO"),
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("META_FAB")
        ),
        META_REV_UMB = colDef(
          name        = "Meta<br/>Revenda",
          html        = TRUE,
          show        = !modo_hl,
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("META_REV")
        ),
        VOL_ANO_ANT_UMB = colDef(
          name        = glue("{rot_aa}"),
          html        = TRUE,
          show        = !modo_hl,
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("VOL_ANO_ANT")
        ),
        VOL_ANO_ANT2_UMB = colDef(
          name        = "Real Ano<br/>Anterior",
          html        = TRUE,
          show        = !modo_hl,
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("VOL_ANO_ANT2")
        ),
        VOL_MES_ATUAL_UMB = colDef(
          name        = glue("Real<br/>{rot_atual}"),
          html        = TRUE,
          show        = !modo_hl,
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("VOL_MES_ATUAL"),
          style = function(value, index) {
            meta <- familia$VOL_ANO_ANT2_UMB[index]
            if (!is.na(value) && !is.na(meta) && value <= meta) return(cor_meta())
            NULL
          }
        ),
        TEND_UMB = colDef(
          name        = "Tend.<br/>&nbsp;",
          html        = TRUE,
          show        = !modo_hl,
          aggregate   = "sum",
          aggregated  = JS("function(cellInfo) { return cellInfo.value == null ? '' : Math.round(cellInfo.value).toLocaleString('pt-BR'); }"),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("TEND"),
          class       = "dv-col-chave",
          cell = function(value, index) {
            if (is.null(value) || is.na(value)) return("")
            tags$span(
              style                       = "cursor: default;",
              `data-tooltip-familia-umb` = as.character(familia$CODRED[index]),
              formatar_tend_familia(value)
            )
          },
          style = function(value, index) {
            meta <- familia$VOL_ANO_ANT2_UMB[index]
            if (!is.na(value) && !is.na(meta) && value <= meta) return(cor_meta())
            NULL
          }
        ),
        PERC_TEND_UMB = colDef(
          name        = "% Tend./<br/>Meta",
          html        = TRUE,
          show        = !modo_hl,
          format      = colFormat(percent = TRUE, digits = 1),
          headerStyle = cor_cabecalho_dv("PERC_TEND")
        ),
        
        VOL_ANO_RETRASADO_HL = colDef(
          name        = glue("{rot_aa2}"),
          html        = TRUE,
          show        = modo_hl,
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("VOL_ANO_RETRASADO")
        ),
        VOL_MES_2_HL = colDef(
          name        = glue("{rot_2}"),
          html        = TRUE,
          show        = modo_hl,
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("VOL_MES_2")
        ),
        VOL_MES_ANT_HL = colDef(
          name        = glue("{rot_1}"),
          html        = TRUE,
          show        = modo_hl,
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("VOL_MES_ANT")
        ),
        META_REV_HL = colDef(
          name        = "Meta<br/>Revenda",
          html        = TRUE,
          show        = modo_hl,
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("META_REV")
        ),
        VOL_ANO_ANT_HL = colDef(
          name        = glue("{rot_aa}"),
          html        = TRUE,
          show        = modo_hl,
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("VOL_ANO_ANT")
        ),
        VOL_ANO_ANT2_HL = colDef(
          name        = "Real Ano<br/>Anterior",
          html        = TRUE,
          show        = modo_hl,
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("VOL_ANO_ANT2")
        ),
        VOL_MES_ATUAL_HL = colDef(
          name        = glue("Real<br/>{rot_atual}"),
          html        = TRUE,
          show        = modo_hl,
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("VOL_MES_ATUAL"),
          style = function(value, index) {
            meta <- familia$VOL_ANO_ANT2_HL[index]
            if (!is.na(value) && !is.na(meta) && value <= meta) return(cor_meta())
            NULL
          }
        ),
        TEND_HL = colDef(
          name        = "Tend.<br/>&nbsp;",
          html        = TRUE,
          show        = modo_hl,
          aggregate   = "sum",
          aggregated  = JS("function(cellInfo) { return cellInfo.value == null ? '' : Math.round(cellInfo.value).toLocaleString('pt-BR'); }"),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("TEND"),
          class       = "dv-col-chave",
          cell = function(value, index) {
            if (is.null(value) || is.na(value)) return("")
            tags$span(
              style                      = "cursor: default;",
              `data-tooltip-familia-hl` = as.character(familia$CODRED[index]),
              formatar_tend_familia(value)
            )
          },
          style = function(value, index) {
            meta <- familia$VOL_ANO_ANT2_HL[index]
            if (!is.na(value) && !is.na(meta) && value <= meta) return(cor_meta())
            NULL
          }
        ),
        PERC_TEND_HL = colDef(
          name        = "% Tend./<br/>Meta",
          html        = TRUE,
          show        = modo_hl,
          format      = colFormat(percent = TRUE, digits = 1),
          headerStyle = cor_cabecalho_dv("PERC_TEND")
        ),
        
        PRECO_MEDIO = colDef(
          name        = "Preço<br/>Médio",
          html        = TRUE,
          show        = !modo_hl,
          format      = colFormat(separators = TRUE, digits = 2),
          headerStyle = cor_cabecalho_dv("VENDA_HL")
        ),
        PERC_MKP = colDef(
          name        = "% MKP",
          html        = TRUE,
          show        = !modo_hl,
          format      = colFormat(percent = TRUE, digits = 1),
          headerStyle = cor_cabecalho_dv("PERC_TEND")
        ),
        VENDA_HL = colDef(
          name        = "R$/<br/>HL",
          html        = TRUE,
          show        = modo_hl,
          format      = colFormat(separators = TRUE, digits = 2),
          headerStyle = cor_cabecalho_dv("VENDA_HL")
        ),
        
        COB_MES_ANT = colDef(
          name        = glue("Cob.<br/>{rot_1}"),
          html        = TRUE,
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("COB_MES_ANT")
        ),
        COB_ANO_ANT = colDef(
          name        = glue("Cob.<br/>{rot_aa}"),
          html        = TRUE,
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("COB_ANO_ANT")
        ),
        COB_MES_ATUAL = colDef(
          name        = glue("Cob.<br/>{rot_atual}"),
          html        = TRUE,
          aggregate   = "sum",
          format      = colFormat(separators = TRUE, digits = 0),
          cell = function(value, index) {
            if (is.null(value) || is.na(value)) return("")
            tags$span(
              style                      = "cursor: default;",
              `data-tooltip-cob-familia` = as.character(familia$CODRED[index]),
              trimws(format(round(value, 0), big.mark = ".", decimal.mark = ",", scientific = FALSE))
            )
          },
          footer      = footer_vol,
          headerStyle = cor_cabecalho_dv("COB_MES_ATUAL"),
          class       = "dv-col-chave",
          style = function(value, index) {
            meta <- familia$COB_ANO_ANT[index]
            if (!is.na(value) && !is.na(meta) && value <= meta) return(cor_meta())
            NULL
          }
        ),
        FAT = colDef(
          name        = glue("Fat.<br/>{rot_atual}"),
          html        = TRUE,
          aggregate   = "sum",
          aggregated  = JS("function(cellInfo) {
            if (!cellInfo.value && cellInfo.value !== 0) return '';
            return cellInfo.value.toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
          }"),
          cell        = function(value) {
            if (is.na(value) || value == 0) return("")
            format(round(value, 2), nsmall = 2, big.mark = ".", decimal.mark = ",", scientific = FALSE)
          },
          footer      = footer_fat,
          headerStyle = cor_cabecalho_dv("FAT"),
          minWidth    = 90
        )
        
      ),
      bordered   = TRUE,
      highlight  = TRUE,
      striped    = FALSE,
      compact    = TRUE,
      fullWidth  = TRUE,
      resizable  = TRUE,
      wrap       = FALSE,
      pagination = FALSE,
      height     = "600px"
    )
  })
  
  ## Tabela Meta Ano - modal de GRUPO ----
  
  output$bt_meta_ano_ui <- renderUI({
    req(revenda_query())
    if (str_detect(revenda_query(), "GRUPO")) {
      actionButton("bt_meta_ano",
                   label = glue("Meta {format(Sys.Date(), '%Y')}"),
                   icon  = icon("chart-bar"),
                   class = "btn-primary btn-sm")
    }
  })
  
  observeEvent(input$bt_meta_ano, {
    ano_at <- format(Sys.Date(), "%Y")
    showModal(modalDialog(
      title     = glue("Meta {ano_at}"),
      size      = "xl",
      easyClose = TRUE,
      footer    = modalButton("Fechar"),
      tags$style(HTML(".modal-xl { max-width: 96vw !important; }")),
      withSpinner(reactableOutput("tabela_meta_ano"), type = 4, color = cores_reativo()[2])
    ))
  })

  ## Tabela Meta ABP - modal de GRUPO ----

  output$bt_meta_abp_ui <- renderUI({
    req(revenda_query())
    if (str_detect(revenda_query(), "GRUPO")) {
      actionButton("bt_meta_abp",
                   label = "Meta ABP",
                   icon  = icon("bullseye"),
                   class = "btn-primary btn-sm")
    }
  })

  observeEvent(input$bt_meta_abp, {
    ano_at <- format(Sys.Date(), "%Y")
    showModal(modalDialog(
      title     = tags$div(
        class = "meta-abp-modal-title",
        tags$span(glue("Meta ABP {ano_at}")),
        radioGroupButtons(
          inputId    = "tipo_meta_abp",
          label      = NULL,
          choices    = c("Cobertura", "Volume"),
          selected   = "Cobertura",
          status     = "primary",
          individual = FALSE,
          width      = "230px"
        )
      ),
      size      = "xl",
      easyClose = TRUE,
      footer    = modalButton("Fechar"),
      tags$style(HTML("
        .modal-xl { max-width: 78vw !important; }
        .meta-abp-modal-title {
          width: 100%;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
        }
        .meta-abp-modal-title .form-group { margin-bottom: 0; }
      ")),
      withSpinner(reactableOutput("tabela_meta_abp"), type = 4, color = cores_reativo()[2])
    ))
  })

  output$tabela_meta_abp <- renderReactable({
    req(dados_meta_abp_rv())

    ano_at    <- format(Sys.Date(), "%Y")
    mes_at    <- as.integer(format(Sys.Date(), "%m"))
    meta      <- dados_meta_abp_rv()
    tipo_meta <- tipo_meta_abp_rv()

    formatar_numero <- function(value) {
      if (is.null(value) || is.na(value)) return("")
      trimws(format(round(value, 0), big.mark = ".", decimal.mark = ",", scientific = FALSE))
    }

    linha_e_diferenca <- function(index) {
      identical(meta$HL_TOTAL[index], "Diferença")
    }

    coluna_mes <- function(nome_mes, numero_mes, nome_col) {
      colDef(
        name        = nome_mes,
        html        = TRUE,
        format      = NULL,
        aggregated  = JS("function() { return ''; }"),
        headerStyle = cor_cabecalho_dv("VOL_MES_ATUAL"),
        cell = function(value, index) {
          if (numero_mes > mes_at && !meta$HL_TOTAL[index] %in% "Meta ABP") return("")
          formatar_numero(value)
        },
        style = function(value, index) {
          if (linha_e_diferenca(index) && numero_mes <= mes_at && is.numeric(value) && !is.na(value) && value < 0)
            return(cor_meta())
          NULL
        }
      )
    }

    estilo_linhas_meta_abp <- estilo_row_meta_abp_dv()

    reactable(
      meta,
      theme           = tema_reactable_dv,
      groupBy         = "CATEGORIA",
      defaultExpanded = TRUE,
      rowStyle        = estilo_linhas_meta_abp,
      defaultColDef   = colDef(align = "center", minWidth = 55),
      columns = list(
        NOVO_COD_SAP = colDef(show = FALSE),
        COD_SAP = colDef(
          name        = "Cód. SAP",
          minWidth    = 80,
          align       = "center",
          format      = NULL,
          headerStyle = cor_cabecalho_dv("CATEGORIA"),
          aggregate   = JS("function() { return ''; }"),
          aggregated  = JS("function() { return ''; }")
        ),
        CATEGORIA = colDef(show = FALSE),
        HL_TOTAL  = colDef(
          name        = "Categoria / Indicador",
          minWidth    = 200,
          align       = "left",
          html        = TRUE,
          format      = NULL,
          headerStyle = cor_cabecalho_dv("CATEGORIA", align = "left"),
          aggregated  = JS("function(cellInfo) {
            return '<strong>' + cellInfo.row['CATEGORIA'] + '</strong>';
          }"),
          cell = function(value, index) {
            paste0("<span style='padding-left:18px;display:inline-block;'>", value, "</span>")
          }
        ),
        Jan = coluna_mes("Jan",  1, "Jan"), Fev = coluna_mes("Fev",  2, "Fev"),
        Mar = coluna_mes("Mar",  3, "Mar"), Abr = coluna_mes("Abr",  4, "Abr"),
        Mai = coluna_mes("Mai",  5, "Mai"), Jun = coluna_mes("Jun",  6, "Jun"),
        Jul = coluna_mes("Jul",  7, "Jul"), Ago = coluna_mes("Ago",  8, "Ago"),
        Set = coluna_mes("Set",  9, "Set"), Out = coluna_mes("Out", 10, "Out"),
        Nov = coluna_mes("Nov", 11, "Nov"), Dez = coluna_mes("Dez", 12, "Dez"),
        Total = colDef(
          name        = if (identical(tipo_meta, "Cobertura")) "Média" else "Total",
          html        = TRUE,
          format      = NULL,
          aggregated  = JS("function() { return ''; }"),
          headerStyle = cor_cabecalho_dv("VOL_MES_ATUAL"),
          cell = function(value, index) {
            formatar_numero(value)
          },
          style = function(value, index) {
            if (linha_e_diferenca(index) && is.numeric(value) && !is.na(value) && value < 0)
              return(cor_meta())
            NULL
          }
        )
      ),
      bordered   = TRUE,
      compact    = TRUE,
      fullWidth  = TRUE,
      pagination = FALSE
    )
  })

  output$tabela_meta_ano <- renderReactable({
    req(dados_meta_rv())
    
    ano_at <- format(Sys.Date(), "%Y")
    mes_at <- as.integer(format(Sys.Date(), "%m"))
    meta   <- dados_meta_rv()
    
    label_meta       <- glue("Meta {ano_at}")
    linhas_com_total <- c(label_meta, ano_at, "Diferenca")
    linhas_ate_mes   <- c(ano_at, "Diferenca")
    
    fmt_num <- function(value) {
      if (is.null(value) || is.na(value)) return("")
      trimws(format(round(value, 0), big.mark = ".", decimal.mark = ",", scientific = FALSE))
    }
    
    estilo_num <- function(value, index) {
      hl <- meta$HL_TOTAL[index]
      if (hl == "Diferenca" && is.numeric(value) && !is.na(value) && value < 0)
        return(list(color = cor_meta()$color))
      NULL
    }
    
    mes_col <- function(nome, mes_num) {
      colDef(
        name   = nome,
        html   = TRUE,
        format = NULL,
        cell   = function(value, index) {
          hl <- meta$HL_TOTAL[index]
          if (hl %in% linhas_ate_mes && mes_num > mes_at) return("")
          fmt_num(value)
        },
        style  = function(value, index) estilo_num(value, index)
      )
    }
    
    reactable(
      meta,
      theme         = tema_reactable_dv,
      defaultColDef = colDef(
        align       = "center",
        format      = colFormat(separators = TRUE, digits = 0),
        headerStyle = cor_cabecalho_dv("VOL_MES_ATUAL")
      ),
      columns = list(
        HL_TOTAL = colDef(
          name        = "HL Total",
          align       = "left",
          minWidth    = 180,
          format      = NULL,
          headerStyle = cor_cabecalho_dv("CATEGORIA", align = "left"),
          style    = function(value) {
            if (!is.null(value) && value == label_meta) return(cor_meta_2026_titulo())
            NULL
          }
        ),
        Jan = mes_col("Jan",  1), Fev = mes_col("Fev",  2),
        Mar = mes_col("Mar",  3), Abr = mes_col("Abr",  4),
        Mai = mes_col("Mai",  5), Jun = mes_col("Jun",  6),
        Jul = mes_col("Jul",  7), Ago = mes_col("Ago",  8),
        Set = mes_col("Set",  9), Out = mes_col("Out", 10),
        Nov = mes_col("Nov", 11), Dez = mes_col("Dez", 12),
        Total = colDef(
          name   = "Total",
          html   = TRUE,
          format = NULL,
          cell   = function(value, index) {
            hl <- meta$HL_TOTAL[index]
            if (!hl %in% linhas_com_total) return("")
            fmt_num(value)
          },
          style  = function(value, index) estilo_num(value, index)
        )
      ),
      bordered   = TRUE,
      compact    = TRUE,
      fullWidth  = TRUE,
      pagination = FALSE
    )
  })
  
  ## Tabela Outros Volumes ----
  
  output$tabela_dv_outros <- renderReactable({
    req(dados_outros_rv(), input$mes_dv)
    
    mes_data  <- as.Date(paste0(input$mes_dv, "01"), format = "%Y%m%d")
    rot_atual <- label_mes(mes_data)
    rot_1     <- label_mes(mes_data %m-% months(1))
    rot_2     <- label_mes(mes_data %m-% months(2))
    rot_aa    <- label_mes(mes_data %m-% months(12))
    rot_aa2   <- label_mes(mes_data %m-% months(24))
    
    outros  <- dados_outros_rv()
    modo_hl <- isTRUE(input$familia_modo)
    
    outros <- outros %>%
      select(any_of(c(
        "PRODUTO",
        "VOL_ANO_RETRASADO_UMB", "VOL_ANO_RETRASADO_HL",
        "VOL_ANO_ANT_UMB",       "VOL_ANO_ANT_HL",
        "VOL_MES_2_UMB",         "VOL_MES_2_HL",
        "VOL_MES_ANT_UMB",       "VOL_MES_ANT_HL",
        "META_FAB_UMB",          "META_FAB_HL",
        "META_REV_UMB",          "META_REV_HL",
        "VOL_ANO_ANT2_UMB",      "VOL_ANO_ANT2_HL",
        "VOL_MES_ATUAL_UMB",     "VOL_MES_ATUAL_HL",
        "TEND_UMB",              "TEND_HL",
        "PERC_TEND_UMB",         "PERC_TEND_HL",
        "PRECO_MEDIO", "PERC_MKP", "VENDA_HL",
        "COB_MES_ANT", "COB_ANO_ANT", "COB_MES_ATUAL",
        "FAT", "REVENDA", "CODRED"
      )))
    
    outros <- outros %>%
      mutate(across(where(is.numeric), ~ ifelse(. == 0, NA_real_, .)))
    
    formatar_tend_outros <- function(valor) {
      if (is.null(valor) || is.na(valor)) return("")
      trimws(format(round(valor, 0), big.mark = ".", decimal.mark = ",", scientific = FALSE))
    }
    
    reactable(
      outros,
      theme         = tema_reactable_dv,
      defaultColDef = colDef(align = "right", minWidth = 60),
      columns = list(
        
        REVENDA = colDef(show = FALSE),
        CODRED  = colDef(show = FALSE),
        
        PRODUTO = colDef(
          name        = "Produto",
          minWidth    = 240,
          align       = "left",
          html        = TRUE,
          headerStyle = cor_cabecalho_dv("CATEGORIA", align = "left")
        ),
        
        VOL_ANO_RETRASADO_UMB = colDef(
          name        = glue("{rot_aa2}"),
          html        = TRUE,
          show        = !modo_hl,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("VOL_ANO_RETRASADO")
        ),
        VOL_MES_2_UMB = colDef(
          name        = glue("{rot_2}"),
          html        = TRUE,
          show        = !modo_hl,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("VOL_MES_2")
        ),
        VOL_MES_ANT_UMB = colDef(
          name        = glue("{rot_1}"),
          html        = TRUE,
          show        = !modo_hl,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("VOL_MES_ANT")
        ),
        META_FAB_UMB = colDef(
          name        = "Meta<br/>Fábrica",
          html        = TRUE,
          show        = !modo_hl && str_detect(revenda_query(), "GRUPO"),
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("META_FAB")
        ),
        META_FAB_HL = colDef(
          name        = "Meta<br/>Fábrica",
          html        = TRUE,
          show        = modo_hl && str_detect(revenda_query(), "GRUPO"),
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("META_FAB")
        ),
        META_REV_UMB = colDef(
          name        = "Meta<br/>Revenda",
          html        = TRUE,
          show        = !modo_hl,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("META_REV")
        ),
        VOL_ANO_ANT_UMB = colDef(
          name        = glue("{rot_aa}"),
          html        = TRUE,
          show        = !modo_hl,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("VOL_ANO_ANT")
        ),
        VOL_ANO_ANT2_UMB = colDef(
          name        = "Real Ano<br/>Anterior",
          html        = TRUE,
          show        = !modo_hl,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("VOL_ANO_ANT2")
        ),
        VOL_MES_ATUAL_UMB = colDef(
          name        = glue("Real<br/>{rot_atual}"),
          html        = TRUE,
          show        = !modo_hl,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("VOL_MES_ATUAL"),
          style = function(value, index) {
            meta <- outros$VOL_ANO_ANT2_UMB[index]
            if (!is.na(value) && !is.na(meta) && value <= meta) return(cor_meta())
            NULL
          }
        ),
        TEND_UMB = colDef(
          name        = "Tend.<br/>&nbsp;",
          html        = TRUE,
          show        = !modo_hl,
          headerStyle = cor_cabecalho_dv("TEND"),
          class       = "dv-col-chave",
          cell = function(value, index) {
            if (is.null(value) || is.na(value)) return("")
            tags$span(
              style                       = "cursor: default;",
              `data-tooltip-familia-umb` = as.character(outros$CODRED[index]),
              formatar_tend_outros(value)
            )
          },
          style = function(value, index) {
            meta <- outros$VOL_ANO_ANT2_UMB[index]
            if (!is.na(value) && !is.na(meta) && value <= meta) return(cor_meta())
            NULL
          }
        ),
        PERC_TEND_UMB = colDef(
          name        = "% Tend./<br/>Meta",
          html        = TRUE,
          show        = !modo_hl,
          format      = colFormat(percent = TRUE, digits = 1),
          headerStyle = cor_cabecalho_dv("PERC_TEND")
        ),
        
        VOL_ANO_RETRASADO_HL = colDef(
          name        = glue("{rot_aa2}"),
          html        = TRUE,
          show        = modo_hl,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("VOL_ANO_RETRASADO")
        ),
        VOL_MES_2_HL = colDef(
          name        = glue("{rot_2}"),
          html        = TRUE,
          show        = modo_hl,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("VOL_MES_2")
        ),
        VOL_MES_ANT_HL = colDef(
          name        = glue("{rot_1}"),
          html        = TRUE,
          show        = modo_hl,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("VOL_MES_ANT")
        ),
        META_REV_HL = colDef(
          name        = "Meta<br/>Revenda",
          html        = TRUE,
          show        = modo_hl,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("META_REV")
        ),
        VOL_ANO_ANT_HL = colDef(
          name        = glue("{rot_aa}"),
          html        = TRUE,
          show        = modo_hl,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("VOL_ANO_ANT")
        ),
        VOL_ANO_ANT2_HL = colDef(
          name        = "Real Ano<br/>Anterior",
          html        = TRUE,
          show        = modo_hl,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("VOL_ANO_ANT2")
        ),
        VOL_MES_ATUAL_HL = colDef(
          name        = glue("Real<br/>{rot_atual}"),
          html        = TRUE,
          show        = modo_hl,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("VOL_MES_ATUAL"),
          style = function(value, index) {
            meta <- outros$VOL_ANO_ANT2_HL[index]
            if (!is.na(value) && !is.na(meta) && value <= meta) return(cor_meta())
            NULL
          }
        ),
        TEND_HL = colDef(
          name        = "Tend.<br/>&nbsp;",
          html        = TRUE,
          show        = modo_hl,
          headerStyle = cor_cabecalho_dv("TEND"),
          class       = "dv-col-chave",
          cell = function(value, index) {
            if (is.null(value) || is.na(value)) return("")
            tags$span(
              style                      = "cursor: default;",
              `data-tooltip-familia-hl` = as.character(outros$CODRED[index]),
              formatar_tend_outros(value)
            )
          },
          style = function(value, index) {
            meta <- outros$VOL_ANO_ANT2_HL[index]
            if (!is.na(value) && !is.na(meta) && value <= meta) return(cor_meta())
            NULL
          }
        ),
        PERC_TEND_HL = colDef(
          name        = "% Tend./<br/>Meta",
          html        = TRUE,
          show        = modo_hl,
          format      = colFormat(percent = TRUE, digits = 1),
          headerStyle = cor_cabecalho_dv("PERC_TEND")
        ),
        
        PRECO_MEDIO = colDef(
          name        = "Preço<br/>Médio",
          html        = TRUE,
          show        = !modo_hl,
          format      = colFormat(separators = TRUE, digits = 2),
          headerStyle = cor_cabecalho_dv("VENDA_HL")
        ),
        PERC_MKP = colDef(
          name        = "% MKP",
          html        = TRUE,
          show        = !modo_hl,
          format      = colFormat(percent = TRUE, digits = 1),
          headerStyle = cor_cabecalho_dv("PERC_TEND")
        ),
        VENDA_HL = colDef(
          name        = "R$/<br/>HL",
          html        = TRUE,
          show        = modo_hl,
          format      = colFormat(separators = TRUE, digits = 2),
          headerStyle = cor_cabecalho_dv("VENDA_HL")
        ),
        
        COB_MES_ANT = colDef(
          name        = glue("Cob.<br/>{rot_1}"),
          html        = TRUE,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("COB_MES_ANT")
        ),
        COB_ANO_ANT = colDef(
          name        = glue("Cob.<br/>{rot_aa}"),
          html        = TRUE,
          format      = colFormat(separators = TRUE, digits = 0),
          headerStyle = cor_cabecalho_dv("COB_ANO_ANT")
        ),
        COB_MES_ATUAL = colDef(
          name        = glue("Cob.<br/>{rot_atual}"),
          html        = TRUE,
          format      = colFormat(separators = TRUE, digits = 0),
          cell = function(value, index) {
            if (is.null(value) || is.na(value)) return("")
            tags$span(
              style                      = "cursor: default;",
              `data-tooltip-cob-familia` = as.character(outros$CODRED[index]),
              trimws(format(round(value, 0), big.mark = ".", decimal.mark = ",", scientific = FALSE))
            )
          },
          headerStyle = cor_cabecalho_dv("COB_MES_ATUAL"),
          class       = "dv-col-chave",
          style = function(value, index) {
            meta <- outros$COB_ANO_ANT[index]
            if (!is.na(value) && !is.na(meta) && value <= meta) return(cor_meta())
            NULL
          }
        ),
        FAT = colDef(
          name        = glue("Fat.<br/>{rot_atual}"),
          html        = TRUE,
          cell        = function(value) {
            if (is.na(value) || value == 0) return("")
            format(round(value, 2), nsmall = 2, big.mark = ".", decimal.mark = ",", scientific = FALSE)
          },
          headerStyle = cor_cabecalho_dv("FAT"),
          minWidth    = 90
        )
        
      ),
      bordered   = TRUE,
      highlight  = TRUE,
      striped    = FALSE,
      compact    = TRUE,
      fullWidth  = TRUE,
      resizable  = TRUE,
      wrap       = FALSE,
      pagination = FALSE,
      height     = if (nrow(outros) > 15) "480px" else "auto"
    )
  })
  
  # UI =========================================================================
  
  fluidPage(
    
    tags$script(HTML("

      var timerOcultarTooltipDV   = null;
      var categoriaAtualTooltipDV = null;  // evita re-disparar Shiny ao mover o mouse dentro da mesma celula
      var dvTooltipAtivo          = false;  // começa desativado; controlado pelo botao de toggle

      // Recebe do Shiny o estado do toggle
      Shiny.addCustomMessageHandler('setDvTooltipAtivo', function(ativo) {
        dvTooltipAtivo = ativo;
        if (!ativo) ocultarTooltipDV();  // fecha painel imediatamente ao desativar
      });

      function mostrarPainelTooltipDV(evento) {
        var painel = document.getElementById('dv_tooltip_panel');
        painel.style.visibility = 'visible';
        painel.style.opacity    = '1';
        var posX = evento.clientX + 15;
        var posY = evento.clientY - 20;
        if (posX + 630 > window.innerWidth)  posX = window.innerWidth  - 635;
        if (posY + 480 > window.innerHeight) posY = window.innerHeight - 485;
        painel.style.left = posX + 'px';
        painel.style.top  = posY + 'px';
      }

      // Hover nas celulas das duas tabelas (categorias + familia)
      document.addEventListener('mouseover', function(evento) {

        // Categorias DV — respeita o toggle
        if (dvTooltipAtivo) {
          var celulaTend = evento.target.closest('[data-tooltip-categoria]');
          var celulaCob  = evento.target.closest('[data-tooltip-cob-categoria]');
          var celulaInd  = evento.target.closest('[data-tooltip-indicador]');
          var celulaFat  = evento.target.closest('[data-tooltip-fat]');
          var celula     = celulaTend || celulaCob || celulaInd || celulaFat;
          if (celula) {
            var categoria, inputName;
            if (celulaTend) {
              categoria = celulaTend.getAttribute('data-tooltip-categoria');
              inputName = 'dv_categoria_hover';
            } else if (celulaCob) {
              categoria = celulaCob.getAttribute('data-tooltip-cob-categoria');
              inputName = 'dv_cob_categoria_hover';
            } else if (celulaInd) {
              categoria = celulaInd.getAttribute('data-tooltip-indicador');
              inputName = 'dv_indicador_hover';
            } else {
              categoria = celulaFat.getAttribute('data-tooltip-fat');
              inputName = 'dv_fat_hover';
            }
            var dedupeKey = inputName + ':' + categoria;
            if (dedupeKey === categoriaAtualTooltipDV) return;
            categoriaAtualTooltipDV = dedupeKey;
            clearTimeout(timerOcultarTooltipDV);
            Shiny.setInputValue(inputName, categoria, {priority: 'event'});
            mostrarPainelTooltipDV(evento);
            return;
          }
        }

        // Familia — respeita o toggle
        if (dvTooltipAtivo) {
          var celulaFamUmb   = evento.target.closest('[data-tooltip-familia-umb]');
          var celulaFamHl    = evento.target.closest('[data-tooltip-familia-hl]');
          var celulaFamGrupo = evento.target.closest('[data-tooltip-familia-grupo]');
          var celulaFamCob   = evento.target.closest('[data-tooltip-cob-familia]');
          var celulaFam      = celulaFamCob || celulaFamUmb || celulaFamHl || celulaFamGrupo;
          if (celulaFam) {
            var chave, inputName;
            if (celulaFamCob) {
              chave     = celulaFamCob.getAttribute('data-tooltip-cob-familia');
              inputName = 'familia_cob_hover';
            } else if (celulaFamUmb) {
              chave     = celulaFamUmb.getAttribute('data-tooltip-familia-umb');
              inputName = 'familia_prod_umb_hover';
            } else if (celulaFamHl) {
              chave     = celulaFamHl.getAttribute('data-tooltip-familia-hl');
              inputName = 'familia_prod_hl_hover';
            } else {
              chave     = celulaFamGrupo.getAttribute('data-tooltip-familia-grupo');
              inputName = 'familia_grupo_hover';
            }
            var dedupeKey = inputName + ':' + chave;
            if (dedupeKey === categoriaAtualTooltipDV) return;
            categoriaAtualTooltipDV = dedupeKey;
            clearTimeout(timerOcultarTooltipDV);
            Shiny.setInputValue(inputName, chave, {priority: 'event'});
            mostrarPainelTooltipDV(evento);
            return;
          }
        }
      });

      // Saida do mouse — todos os tipos de celula
      document.addEventListener('mouseout', function(evento) {
        var seletores = '[data-tooltip-categoria], [data-tooltip-cob-categoria], [data-tooltip-indicador], [data-tooltip-fat], [data-tooltip-familia-umb], [data-tooltip-familia-hl], [data-tooltip-familia-grupo], [data-tooltip-cob-familia]';
        var celula = evento.target.closest(seletores);
        if (!celula) return;
        if (!celula.contains(evento.relatedTarget)) {
          ocultarTooltipDV();
        }
      });

      // Oculta o painel com atraso para permitir mover o mouse ate dentro do painel
      function ocultarTooltipDV() {
        timerOcultarTooltipDV = setTimeout(function() {
          var painel = document.getElementById('dv_tooltip_panel');
          painel.style.visibility = 'hidden';
          painel.style.opacity    = '0';
          categoriaAtualTooltipDV = null;
        }, 250);
      }

      // Move o botao de toggle para dentro do card-tools da box (ao lado dos controles nativos)
      function posicionaBotaoToggle() {
        var btn   = document.getElementById('bt_toggle_tooltip_ui');
        var tools = document.querySelector('#box_dv_tabela .card-tools');
        if (!btn || !tools) return;
        if (btn.closest('.card-tools')) return;
        tools.insertBefore(btn, tools.firstChild);
      }

      function posicionaBotaoMeta() {
        var btn   = document.getElementById('bt_meta_ano_ui');
        var tools = document.querySelector('#box_dv_tabela .card-tools');
        if (!btn || !tools) return;
        if (btn.closest('.card-tools')) return;
        tools.insertBefore(btn, tools.firstChild);
      }

      function posicionaBotaoMetaABP() {
        var btn   = document.getElementById('bt_meta_abp_ui');
        var tools = document.querySelector('#box_dv_tabela .card-tools');
        if (!btn || !tools) return;
        if (btn.closest('.card-tools')) return;
        tools.insertBefore(btn, tools.firstChild);
      }

      $(document).ready(function() { posicionaBotaoToggle(); posicionaBotaoMeta(); posicionaBotaoMetaABP(); });
      $(document).on('shiny:value', function(e) {
        if (e.name === 'bt_toggle_tooltip_ui') setTimeout(posicionaBotaoToggle,   0);
        if (e.name === 'bt_meta_ano_ui')       setTimeout(posicionaBotaoMeta,     0);
        if (e.name === 'bt_meta_abp_ui')       setTimeout(posicionaBotaoMetaABP,  0);
      });

    ")),
    
    tags$style(HTML("
      .rt-tr:has(button[aria-expanded='true']) .prod-count { display: none; }
    ")),
    
    div(
      id    = "dv_tooltip_panel",
      style = paste(
        "position: fixed;",
        "visibility: hidden;",
        "opacity: 0;",
        "z-index: 9999;",
        "background: white;",
        "border: 1px solid #ccc;",
        "border-radius: 6px;",
        "padding: 8px;",
        "width: 620px;",
        "height: 263px;",
        "box-shadow: 3px 3px 12px rgba(0,0,0,0.3);",
        "transition: opacity 0.15s;"
      ),
      onmouseenter = "clearTimeout(timerOcultarTooltipDV)",
      onmouseleave = "ocultarTooltipDV()",
      echarts4rOutput("dv_grafico_tooltip", height = "252px")
    ),
    
    fluidRow(
      box(
        id          = "box_dv_filtro",
        title       = fluidRow(
          column(1,
                 pickerInput("mes_dv", "Mês", choices = NULL,
                             options = pickerOptions(style = "btn-dv-mes", container = "body", size = 8))
          ),
          column(1, pickerInput("ghost5", "Ghost 5", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
          column(1,
                 uiOutput("card_dias_uteis")
          ),
          column(1,
                 uiOutput("card_dias_uteis_atual")
          ),
          column(1, pickerInput("ghost7", "Ghost 7", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
          column(1, uiOutput("bt_meta_fab_ui")),
          column(1, uiOutput("ga_dv_ui")),
          column(1, uiOutput("ven_dv_ui")),
          column(1, pickerInput("ghost_cod", "Ghost Cod", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
          column(1, pickerInput("ghost4", "Ghost 4", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
          column(1, pickerInput("ghost9", "Ghost 9", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
          column(1,
                 style = "display: flex; align-items: center;",
                 column(1),
                 column(9, actionButton("bt_limpa_dv", label = NULL, icon = icon("eraser"),
                                        status = "primary", size = "lg", width = "100%") %>%
                          tagAppendAttributes(title = "Limpar filtros")),
                 column(1)
          )
        ),
        width       = 12,
        status      = "primary",
        collapsible = FALSE
      ),
      column(12, uiOutput("kpis_dv")),
      # As três tabelas numa caixa só, em abas (antes eram três caixas empilhadas).
      tabBox(
        id          = "abas_dv",
        width       = 12,
        side        = "left",
        collapsible = FALSE,
        status      = "primary",
        title       = div(
          class = "dv-card-toolbar",
          div(class = "dv-switch-hl", title = "Unidade das tabelas de produto: UMB ou hectolitro",
              switchInput(
                inputId  = "familia_modo",
                label    = NULL,
                value    = FALSE,
                onLabel  = "HL",
                offLabel = "UMB",
                size     = "mini",
                inline   = TRUE
              )),
          uiOutput("bt_meta_abp_ui", inline = TRUE),
          uiOutput("bt_meta_ano_ui", inline = TRUE),
          uiOutput("bt_toggle_tooltip_ui", inline = TRUE)
        ),
        tabPanel(
          "Categorias",
          withSpinner(reactableOutput("tabela_dv_novo"), type = 4, color = cores_reativo()[2]),
          div(class = "dv-legenda",
              span(class = "dv-legenda-alerta"), "abaixo do ano anterior ou da meta",
              span(class = "dv-legenda-chave"), "colunas principais do mês",
              span(class = "dv-legenda-dica", "passe o mouse com o histórico ativo para ver a evolução"))
        ),
        tabPanel(
          "Produto / Família",
          withSpinner(reactableOutput("tabela_dv_familia"), type = 4, color = cores_reativo()[2])
        ),
        tabPanel(
          "Outros volumes",
          withSpinner(reactableOutput("tabela_dv_outros"), type = 4, color = cores_reativo()[2])
        )
      )
    )
  )
}
