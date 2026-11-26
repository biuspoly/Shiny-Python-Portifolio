# Carregar dados ----------------------------------------------------------

source(glue("{diretorio}pages/PDE/Dados/dados_PDE.R"), local = TRUE, encoding = "UTF-8")

pag_pde <- function() {
  # Server ------------------------------------------------------------------

  pde_reativo <- reactiveVal(carregar_dados_pde())



  filtro_pde_reativo <- reactive({
    req(input$datapde_input)
    # req(input$empresapde_input)

    if (length(revenda_query()) == 0) {
      pde_reativo() %>% filter(
        `Data Saída` %in% input$datapde_input,
        Empresa == input$empresapde_input,
        if (is.null(input$placapde_input) || length(input$placapde_input) == 0) TRUE else Placa %in% input$placapde_input
      )
    } else {
      pde_reativo() %>% filter(
        `Data Saída` %in% input$datapde_input,
        toupper(Empresa) == revenda_query(),
        if (is.null(input$placapde_input) || length(input$placapde_input) == 0) TRUE else Placa %in% input$placapde_input
      )
    }
  })


  # Textos reativos --------------------------------------------------------

  ### Ultima atualizacao
  output$ult_atualizacao_id_entrega <- renderText({
    glue("Atualizado em: {format(Sys.Date(),'%d/%m/%Y')}")
  })

  # Filtros reativos --------------------------------------------------------

  ### Data
  output$datapde_input <- renderUI({
    # req(input$empresapde_input)
    req(pde_reativo())


    if (length(revenda_query()) == 0) {
      req(input$empresapde_input)
      datas_filtradas_pde <- pde_reativo() %>%
        filter(Empresa == input$empresapde_input)
    } else {
      datas_filtradas_pde <- pde_reativo() %>%
        filter(toupper(Empresa) == revenda_query())
    }

    datas_pde_selecionadas <- input$datapde_input
    if (!is.null(datas_pde_selecionadas)) {
      datas_pde_selecionadas <- datas_pde_selecionadas[datas_pde_selecionadas %in% unique(datas_filtradas_pde$`Data Saída`)]
    } else {
      datas_pde_selecionadas <- max(unique(datas_filtradas_pde$`Data Saída`))
    }

    pickerInput(
      "datapde_input",
      label = "Data",
      choices = setNames(
        sort(unique(datas_filtradas_pde$`Data Saída`), decreasing = TRUE),
        format(as.Date(as.character(sort(unique(datas_filtradas_pde$`Data Saída`), decreasing = TRUE)), format = "%Y%m%d"), "%d/%m/%Y")
      ),
      multiple = TRUE,
      selected = datas_pde_selecionadas,
      options = pickerOptions(
        size = 7,
        style = "btn-color",
        countSelectedText = " {0} Itens selecionados",
        selectedTextFormat = "count > 2"
      )
    )
  })

  ### Romaneio
  output$romaneio_veiculo_pde <- renderUI({
    req(input$datapde_input)
    # req(input$empresapde_input)

    if (length(revenda_query()) == 0) {
      req(input$empresapde_input)
      romaneios_pde_filtrados <- pde_reativo() %>%
        filter(
          Empresa == input$empresapde_input,
          `Data Saída` %in% input$datapde_input,
          if (is.null(input$placapde_input) || length(input$placapde_input) == 0) TRUE else Placa %in% input$placapde_input
        )
    } else {
      romaneios_pde_filtrados <- pde_reativo() %>%
        filter(
          toupper(Empresa) == revenda_query(),
          `Data Saída` %in% input$datapde_input,
          if (is.null(input$placapde_input) || length(input$placapde_input) == 0) TRUE else Placa %in% input$placapde_input
        )
    }

    # romaneios_pde_filtrados <- pde %>%
    #   filter(Empresa == input$empresapde_input,
    #          `Data Saída` == input$datapde_input)

    selectInput(
      "romaneio_veiculo_pde",
      label = "Romaneio",
      choices = unique(romaneios_pde_filtrados$Romaneio[input$tabela_pde_reativa_rows_all])
    )
  })

  ### Revenda

  output$empresapde_input <- renderUI({
    req(pde_reativo())

    revendas_pde_choices <- pde_reativo()
    if (length(revenda_query()) == 0) {
      revendas_pde_selecionadas <- input$empresapde_input
      if (!is.null(revendas_pde_selecionadas)) {
        revendas_pde_selecionadas <- revendas_pde_selecionadas[revendas_pde_selecionadas %in% unique(pde_reativo()$Empresa)]
      }
      selectInput(
        "empresapde_input",
        label = "Revenda", choices = sort(unique(pde_reativo()$Empresa)), selected = revendas_pde_selecionadas
      )
    } else {
      div(
        style = "display: none;",
        selectInput(
          "empresapde_input",
          label = "Revenda", choices = revenda_query(), selected = revenda_query()
        )
      )
    }
  })

  ### Placa

  output$placapde_input <- renderUI({
    req(input$datapde_input)


    if (length(revenda_query()) == 0) {
      req(input$empresapde_input)
      placas_filtradas_pde <- pde_reativo() %>%
        filter(
          Empresa == input$empresapde_input,
          `Data Saída` %in% input$datapde_input
        )
    } else {
      placas_filtradas_pde <- pde_reativo() %>%
        filter(
          toupper(Empresa) == revenda_query(),
          `Data Saída` %in% input$datapde_input
        )
    }


    placas_pde_selecionadas <- input$placapde_input
    if (!is.null(placas_pde_selecionadas)) {
      placas_pde_selecionadas <- placas_pde_selecionadas[placas_pde_selecionadas %in% unique(placas_filtradas_pde$Placa)]
    }

    pickerInput(
      "placapde_input",
      label = "Placa",
      choices = unique(placas_filtradas_pde$Placa),
      multiple = TRUE,
      selected = placas_pde_selecionadas,
      options = pickerOptions(
        noneSelectedText = "Filtrar placa",
        size = 7,
        style = "btn-color",
        countSelectedText = " {0} Itens selecionados",
        selectedTextFormat = "count > 2"
      )
    )
  })

  # Botao de inserir dados --------------------------------------------------

  ## HR Saida
  observeEvent(input$id_hrsaida_pde,
    {
      if (nchar(input$id_hrsaida_pde) != 5 ||
        !grepl("^([01][0-9]|2[0-3]):[0-5][0-9]$", input$id_hrsaida_pde)) {
        showFeedbackDanger("id_hrsaida_pde", text = NULL)
      } else {
        hideFeedback("id_hrsaida_pde")
      }
    },
    ignoreInit = TRUE
  )

  ## HR Chegada
  observeEvent(input$id_hrchegada_pde,
    {
      if (nchar(input$id_hrchegada_pde) != 5 ||
        !grepl("^([01][0-9]|2[0-3]):[0-5][0-9]$", input$id_hrchegada_pde)) {
        showFeedbackDanger("id_hrchegada_pde", text = NULL)
      } else {
        hideFeedback("id_hrchegada_pde")
      }
    },
    ignoreInit = TRUE
  )

  ## KM final
  observeEvent(input$id_kmchegada_pde,
    {
      if (is.na(as.numeric(input$id_kmchegada_pde)) || as.numeric(input$id_kmchegada_pde) <= 0) {
        showFeedbackDanger("id_kmchegada_pde", text = NULL)
      } else {
        hideFeedback("id_kmchegada_pde")
      }
    },
    ignoreInit = TRUE
  )

  ## KM inicial
  observeEvent(input$id_kmsaida_pde,
    {
      if (is.na(as.numeric(input$id_kmsaida_pde)) || as.numeric(input$id_kmsaida_pde) < 0) {
        showFeedbackDanger("id_kmsaida_pde", text = NULL)
      } else {
        hideFeedback("id_kmsaida_pde")
      }
    },
    ignoreInit = TRUE
  )


  observeEvent(input$bt_insere_dados_pde, {
    req(nchar(input$id_hrsaida_pde) == 5 && grepl("^([01][0-9]|2[0-3]):[0-5][0-9]$", input$id_hrsaida_pde))
    req(nchar(input$id_hrchegada_pde) == 5 && grepl("^([01][0-9]|2[0-3]):[0-5][0-9]$", input$id_hrchegada_pde))
    req(as.numeric(input$id_kmsaida_pde) >= 0 && as.numeric(input$id_kmchegada_pde) >= 0)

    con_pde <- conexao_pde() # portfólio: o banco em memória de Dados/dados_PDE.R

    if (length(revenda_query()) == 0) {
      dbExecute(
        con_pde,
        glue("UPDATE tb_pde
             SET HR_SAIDA   = '{input$id_hrsaida_pde}',
                 AJUDANTE_1 = '{input$id_ajudante1_pde}',
                 AJUDANTE_2 = '{input$id_ajudante2_pde}',
                 OBS        = '{input$id_obs_pde}',
                 HR_FIM     = '{input$id_hrchegada_pde}',
                 KM_INI     = '{input$id_kmsaida_pde}',
                 KM_FIM     = '{input$id_kmchegada_pde}'

             WHERE ROMANEIO = '{input$romaneio_veiculo_pde}' AND
             CNPJ_EMP = {pde_reativo()$Cnpj_emp[pde_reativo()$Romaneio == input$romaneio_veiculo_pde &
                                      pde_reativo()$`Data Saída` == input$datapde_input &
                                      pde_reativo()$Empresa == input$empresapde_input]}")
      )
    } else {
      dbExecute(
        con_pde,
        glue("UPDATE tb_pde
               SET HR_SAIDA = '{input$id_hrsaida_pde}',
                 AJUDANTE_1 = '{input$id_ajudante1_pde}',
                 AJUDANTE_2 = '{input$id_ajudante2_pde}',
                 OBS        = '{input$id_obs_pde}',
                 HR_FIM     = '{input$id_hrchegada_pde}',
                 KM_INI     = '{input$id_kmsaida_pde}',
                 KM_FIM     = '{input$id_kmchegada_pde}'

               WHERE ROMANEIO = '{input$romaneio_veiculo_pde}' AND
               DT_SAIDA = {input$datapde_input} AND
               CNPJ_EMP = {pde_reativo()$Cnpj_emp[pde_reativo()$Romaneio== input$romaneio_veiculo_pde &
                                        pde_reativo()$`Data Saída` == input$datapde_input &
                                        toupper(pde_reativo()$Empresa) == revenda_query()]}")
      )
    }

    dbDisconnect(con_pde)
    pde_reativo(carregar_dados_pde())
  })


  # Tabela Geral ------------------------------------------------------------


  colunas_filtradas_reativas <- reactiveVal(NULL)

  observeEvent(input$datapde_input, {
    # ### Filtro não sumir quando adicionar inputs (caso precise, verificar maneira pra atrasar o tempo de resposta entre a teclagem do usuario e a busca)
    if (all(input$tabela_pde_reativa_search_columns == "")) {
      colunas_pde_filtradas <- NULL
    } else {
      colunas_pde_filtradas <- lapply(1:ncol(tabela_pde()), function(coluna_pde) {
        if (coluna_pde %in% which(input$tabela_pde_reativa_search_columns != "")) {
          filtro_pde_acionado <- list(search = input$tabela_pde_reativa_search_columns[which(input$tabela_pde_reativa_search_columns != "")])

          return(filtro_pde_acionado)
        } else {
          return(NULL)
        }
      })
    }

    colunas_filtradas_reativas(colunas_pde_filtradas)
  })

  observeEvent(input$placapde_input, {
    # ### Filtro não sumir quando adicionar inputs (caso precise, verificar maneira pra atrasar o tempo de resposta entre a teclagem do usuario e a busca)
    if (all(input$tabela_pde_reativa_search_columns == "")) {
      colunas_pde_filtradas <- NULL
    } else {
      colunas_pde_filtradas <- lapply(1:ncol(tabela_pde()), function(coluna_pde) {
        if (coluna_pde %in% which(input$tabela_pde_reativa_search_columns != "")) {
          filtro_pde_acionado <- list(search = input$tabela_pde_reativa_search_columns[which(input$tabela_pde_reativa_search_columns != "")])

          return(filtro_pde_acionado)
        } else {
          return(NULL)
        }
      })
    }

    colunas_filtradas_reativas(colunas_pde_filtradas)
  })


  tabela_pde <- reactive(filtro_pde_reativo())


  output$tabela_pde_reativa <- renderDT(
    {
      req(tabela_pde())

      datatable(
        tabela_pde() %>%
          mutate(
            `Data Saída` = ifelse(`Data Saída` == 0, "", format(as.Date(as.character(`Data Saída`), "%Y%m%d"), "%d/%m/%Y")),
            `Data Chegada` = ifelse(`Data Chegada` == 0, "", format(as.Date(as.character(`Data Chegada`), "%Y%m%d"), "%d/%m/%Y")),
            `Fat Saida` = scales::dollar(`Fat Saida`, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
            `Fat Dev` = scales::dollar(`Fat Dev`, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
            `% Util` = scales::percent(`% Util`, accuracy = 0.01, decimal.mark = ","),
            `% Dev` = scales::percent(`% Dev`, accuracy = 0.01, decimal.mark = ",")
          ),
        selection = "none", # Para evitar seleção (como reactable padrão)
        filter = "top",
        extensions = c("Scroller", "FixedColumns"), # Para scroll eficiente com muitos dados
        options = list(
          scrollY = "59vh", # Equivale ao maxHeight = "60vh"
          scrollX = TRUE, # Equivale ao overflowX = "auto"
          # scrollCollapse = TRUE,           # Para colapsar quando há poucos dados
          searchCols = colunas_filtradas_reativas(),
          info = FALSE, # Remove informações de paginação
          ordering = TRUE, # Permite ordenação
          scroller = TRUE, # Scroll eficiente para muitos dados
          deferRender = TRUE, # Renderização sob demanda
          compact = TRUE, # Equivale ao compact = TRUE
          autoWidth = TRUE, # Controle manual da largura
          dom = "t", # Apenas filtros e tabela (remove outros elementos)
          columnDefs = list(
            list(width = "50px", className = "dt-left", targets = 0),
            list(width = "50px", className = "dt-center", targets = 1:(ncol(tabela_pde()) - 1)),
            list(visible = FALSE, targets = which(colnames(tabela_pde()) == "Cnpj_emp") - 1),
            list(visible = FALSE, targets = which(colnames(tabela_pde()) == "Empresa") - 1),
            list(visible = FALSE, targets = which(colnames(tabela_pde()) == "Id") - 1)
          ),
          fixedColumns = list(leftColumns = 5)
        ),
        rownames = FALSE, # Remove nomes das linhas
        escape = FALSE, # Permite HTML nas células se necessário
        class = "compact stripe hover"
      ) %>%
        formatStyle(c("Data Saída", "Dias de rota", "Qtd Ent", "Qtd Nf"), backgroundColor = "#F0E199")
    },
    server = FALSE
  )

  # output$tabela_pde_reativa <- renderReactable({
  #   req(tabela_pde())
  #
  #
  #   reactable(
  #     tabela_pde() %>%
  #       mutate(
  #         `Data Saída` = ifelse(
  #           `Data Saída` == 0,
  #           NA_character_,
  #           format(as.Date(as.character(`Data Saída`), "%Y%m%d"), "%d/%m/%Y")
  #         ),
  #         `Data Chegada` = ifelse(
  #           `Data Chegada` == 0,
  #           NA_character_,
  #           format(as.Date(as.character(`Data Chegada`), "%Y%m%d"), "%d/%m/%Y")
  #         )
  #       )
  #     ,
  #     elementId = "minha_tabela",
  #     filterable = TRUE,
  #     pagination = FALSE,
  #     compact = TRUE,
  #     highlight = TRUE,
  #     bordered = TRUE,
  #     defaultColDef = colDef(align = "center", width = 80),
  #     wrap = FALSE,
  #     columns = list(
  #       # Colunas a ocultar
  #       Cnpj_emp = colDef(show = FALSE),
  #       Empresa = colDef(show = FALSE),
  #       Id = colDef(show = FALSE),
  #       `Fat Dev` = colDef(format = colFormat(currency = "BRL", locales = "pt-BR", separators = TRUE)),
  #       `Fat Saida` = colDef(format = colFormat(currency = "BRL", locales = "pt-BR", separators = TRUE)),
  #       `% Dev` = colDef(format = colFormat(percent = TRUE, digits = 2)),
  #       `% Util` = colDef(format = colFormat(percent = TRUE, digits = 2)),
  #       `Dias de rota` = colDef(style = list(background = "#F0E199")),
  #       `Qtd Ent` = colDef(style = list(background = "#F0E199")),
  #       `Qtd Nf` = colDef(style = list(background = "#F0E199"))
  #     ),
  #     height = "59vh",
  #     style = list(overflowX = "auto"),
  #     theme = reactableTheme(
  #       headerStyle = list(
  #         backgroundColor = glue("{cores_iniciais[2]}"),
  #         color = "white",
  #         fontWeight = "bold",
  #         textAlign = "center"
  #       )
  #     )
  #   )
  # })


  ### Download

  output$bt_download_id_entrega <- downloadHandler(
    filename = function() {
      paste("pde-", Sys.Date(), ".xlsx", sep = "")
    },
    content = function(con) {
      write_xlsx(tabela_pde()[input$tabela_pde_reativa_rows_all, ], con)
    }
  )


  # UI ----------------------------------------------------------------------

  fluidRow(
    box(
      status = "primary",
      collapsed = FALSE,
      width = 12,
      title = "Inserir dados",
      fluidRow(
        column(
          width = 2,
          fluidRow(
            column(
              width = 12,
              uiOutput("romaneio_veiculo_pde")
            ),
            column(
              width = 12,
              textInput(
                "id_ajudante1_pde",
                label = "Ajudante 1", placeholder = "Opcional"
              )
            )
          )
        ),
        column(
          width = 8,
          fluidRow(
            column(
              width = 3,
              textInput(
                "id_hrsaida_pde",
                label = "Hora de Saída", placeholder = "HH:MM"
              )
            ),
            column(
              width = 3,
              textInput(
                "id_hrchegada_pde",
                label = "Hora de Chegada", placeholder = "HH:MM"
              )
            ),
            column(
              width = 3,
              textInput(
                "id_kmsaida_pde",
                label = "Km Saída", placeholder = NULL
              )
            ),
            column(
              width = 3,
              textInput(
                "id_kmchegada_pde",
                label = "Km Chegada", placeholder = NULL
              )
            ),
            column(
              width = 3,
              textInput(
                "id_ajudante2_pde",
                label = "Ajudante 2", placeholder = "Opcional"
              )
            ),
            column(
              width = 3,
              textInput(
                "id_obs_pde",
                label = "Observação", placeholder = "Opcional"
              )
            )
          )
        ),
        column(
          width = 2,
          style = "display: flex; align-items: center;",
          actionButton("bt_insere_dados_pde", label = "Inserir dados", status = "primary", size = "lg", width = "100%")
        )
      )
    ),
    box(
      status = "primary",
      width = 12,
      title = "PDE",
      fluidRow(
        column(
          width = 2,
          uiOutput("empresapde_input")
        ),
        column(width = 6),
        column(
          width = 2,
          uiOutput("placapde_input")
        ),
        column(
          width = 2,
          uiOutput("datapde_input")
        ),
        column(
          width = 12,
          DTOutput("tabela_pde_reativa")
          # tags$script(HTML("
          #   Shiny.addCustomMessageHandler('runDelayedState', function(message) {
          #       Shiny.setInputValue('estado_tabela', Reactable.getState('minha_tabela'));
          #   });
          # "))
        )
      )
    )
  )
}
