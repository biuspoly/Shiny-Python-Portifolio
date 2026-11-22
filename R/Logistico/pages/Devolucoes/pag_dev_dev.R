pag_dev_dev <- function() {
  # Carregar e tratar dados ----------------------------------------------------------

  source(glue("{diretorio}pages/Devolucoes/Dados/dados_devolucoes.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Devolucoes/Dados/funcoes_data_cor.R"), local = TRUE, encoding = "UTF-8")

  # Server ------------------------------------------------------------------

  dev_geral_dev <- reactive({
    req(input$data_dev_dev_input) # garante que o input existe
    # devolucao_geral_dev = geral_dev(input$data_dev_dev_input)

    if (length(revenda_query()) == 0) {
      devolucao_geral_dev <- geral_dev(input$data_dev_dev_input, "HOLDING")
    }
    # else if (str_detect(revenda_query(), "LOCADORA" ) | str_detect(revenda_query(), "ARRENDADORA") | str_detect(revenda_query(), "TRANSPORTADORA")) {
    #   devolucao_geral_dev %>% filter(str_detect(toupper(EMPRESA), revenda_query()))
    # }
    else {
      # devolucao_geral_dev %>% filter(str_detect(toupper(Empresa), revenda_query()))
      devolucao_geral_dev <- geral_dev(input$data_dev_dev_input, revenda_query())
    }
  })


  dev_geral_mensal <- reactive({
    req(input$data_dev_dev_input) # garante que o input existe
    # devolucao_mensal_dev = geral_dev_mensal()

    if (length(revenda_query()) == 0) {
      devolucao_mensal_dev <- geral_dev_mensal("HOLDING")
    }
    # else if (str_detect(revenda_query(), "LOCADORA" ) | str_detect(revenda_query(), "ARRENDADORA") | str_detect(revenda_query(), "TRANSPORTADORA")) {
    #   devolucao_geral_dev %>% filter(str_detect(toupper(EMPRESA), revenda_query()))
    # }
    else {
      devolucao_mensal_dev <- geral_dev_mensal(revenda_query())
    }
  })

  # Textos reativos --------------------------------------------------------

  ### Ultima atualizacao --------------------------------------------------------
  output$ult_atualizacao_id_dev_dev <- renderText({
    glue("Atualizado em: {format(Sys.Date(), '%d/%m/%Y')}")
  })

  ## Aviso --------------------------------------------------------
  output$aviso_id_dev_dev <- renderUI({
    req(filtro_base_dev_geral_dev())
    valores_resumidos_dev <- filtro_base_dev_geral_dev() %>%
      summarise(
        Vendas = round(sum(`VALOR VENDA`), 2),
        Devoluções = round(sum(`VALOR DEVOLUCAO`), 2),
        Retorno = round(sum(`VALOR DEVOLUCAO`), 2) / round(sum(`VALOR VENDA`), 2)
      )

    fluidRow(
      column(
        4,
        box(
          elevation = 2,
          id = "box_vendas_dev",
          div(
            "Vendas:",
            style = "font-size: 12px;"
          ),
          div(
            scales::dollar(valores_resumidos_dev$Vendas, prefix = "R$ ", big.mark = "."),
            style = "font-size: 12px;"
          ),
          background = "primary",
          height = "50px"
        )
      ),
      column(
        4,
        box(
          elevation = 2,
          id = "box_devol_dev",
          div(
            "Devoluções:",
            style = "font-size: 12px;"
          ),
          div(
            scales::dollar(valores_resumidos_dev$Devoluções, prefix = "R$ ", big.mark = "."),
            style = "font-size: 12px;"
          ),
          background = "primary",
          height = "50px"
        )
      ),
      column(
        4,
        box(
          elevation = 2,
          id = "box_taxa_retorno_dev",
          div(
            "Tx retorno (Fin):",
            style = "font-size: 12px;"
          ),
          div(
            scales::percent(valores_resumidos_dev$Retorno, suffix = "%", accuracy = 0.01, decimal.mark = ","),
            style = "font-size: 14px;"
          ),
          background = ifelse(is.na(valores_resumidos_dev$Retorno) | valores_resumidos_dev$Retorno <= 0.02,
            "success",
            "danger"
          ),
          height = "50px"
        )
      )
    )
  })

  # Botoes e filtros --------------------------------------------------------

  ### Botao  --------------------------------------------------------
  observeEvent(input$bt_limpadev_dev, {
    updatePickerInput(session, inputId = "datapeddev_dev_input", selected = character(0))
    updatePickerInput(session, inputId = "revendadev_dev_input", selected = character(0))
    # updatePickerInput(session,inputId = "codpeddev_dev_input",selected = character(0))
    # updatePickerInput(session,inputId = "codvendev_dev_input",selected = character(0))
    # updatePickerInput(session,inputId = "codmotdev_dev_input",selected = character(0))
    # updatePickerInput(session,inputId = "codproddev_dev_input",selected = character(0))
    updatePickerInput(session, inputId = "data_dev_dev_input", selected = "Mês Atual")
    # updatePickerInput(session,inputId = "codclidev_dev_input",selected = character(0))
    # updatePickerInput(session,inputId = "ultcompdev_dev_input",selected = character(0))
    # updatePickerInput(session,inputId = "devpeddev_dev_input",selected = character(0))
  })

  ### Download  --------------------------------------------------------


  output$bt_download_id_dev_dev <- downloadHandler(
    filename = function() {
      paste("devolucao-", Sys.Date(), ".xlsx", sep = "")
    },
    content = function(con) {
      colunas_remover <- c(
        "Comodato", "TPCOBRA", "MES", "QTD_UN", "DEVOLUCAO_UN",
        "CNPJ_REV", "CHAVE_VDI", "VEN", "FANTASIA", "PRODUTO", "PRODUTO_GENERICO",
        "Romaneio aberto", "Comodato cliente", "MES_ATUAL", "NOME_MOT",
        "NOME_VEN", "COD_VEN", "Empresa", "Retorno", "ULT_COMPRA"
      )

      filtro_base_dev_geral_dev() %>%
        dplyr::ungroup() %>% # <- garante que não está mais agrupado
        dplyr::select(-dplyr::any_of(colunas_remover)) %>%
        writexl::write_xlsx(con)
    }
  )

  ### Filtros --------------------------------------------------------
  opcoes_filtro <- pickerOptions(
    noneSelectedText = "Todos",
    size = 5,
    style = "btn-color",
    countSelectedText = " {0} Itens",
    selectedTextFormat = "count > 1",
    container = "body",
    liveSearch = TRUE
  )

  # output$input_filtro_revenda = renderUI({
  #
  #   if (is.null(revenda_query()) | length(revenda_query()) == 0){
  #     pickerInput("unidfrotas_input", "Unidade", choices = sort(unique(frota_principal()$UNIDADE[!is.na(frota_principal()$UNIDADE) & frota_principal()$UNIDADE != ""])), multiple = TRUE, options = opcoes_filtro)
  #   }
  #   else{
  #     div(style = "display: none;",
  #         pickerInput("unidfrotas_input", "Unidade", choices = sort(unique(frota_principal()$UNIDADE[!is.na(frota_principal()$UNIDADE) & frota_principal()$UNIDADE != ""])), multiple = TRUE, options = opcoes_filtro)
  #     )
  #
  #   }
  # })
  #
  filtro_base_dev_geral_dev <- reactive({
    if (
      (is.null(input$datapeddev_dev_input) || length(input$datapeddev_dev_input) == 0) &&
        (is.null(input$revendadev_dev_input) || length(input$revendadev_dev_input) == 0) &&
        # (is.null(input$codpeddev_dev_input) || length(input$codpeddev_dev_input) == 0) &&
        # (is.null(input$codvendev_dev_input) || length(input$codvendev_dev_input) == 0) &&
        # (is.null(input$codmotdev_dev_input) || length(input$codmotdev_dev_input) == 0) &&
        # (is.null(input$codproddev_dev_input) || length(input$codproddev_dev_input) == 0) &&
        (is.null(input$data_dev_dev_input) || length(input$data_dev_dev_input) == 0)
      # (is.null(input$ultcompdev_dev_input) || length(input$ultcompdev_dev_input) == 0) &&
      # (is.null(input$devpeddev_dev_input) || length(input$devpeddev_dev_input) == 0) &&
      #  (is.null(input$codclidev_dev_input) || length(input$codclidev_dev_input) == 0)
    ) {
      dados <- dev_geral_dev()
    } else {
      dados <- dev_geral_dev() %>%
        filter(
          if (is.null(input$datapeddev_dev_input) || length(input$datapeddev_dev_input) == 0) TRUE else DATA_VENDA %in% input$datapeddev_dev_input,
          if (is.null(input$revendadev_dev_input) || length(input$revendadev_dev_input) == 0) TRUE else GRUPO_REV %in% input$revendadev_dev_input,
          # if (is.null(input$codpeddev_dev_input) || length(input$codpeddev_dev_input) == 0) TRUE else COD_PED %in% input$codpeddev_dev_input,
          # if (is.null(input$codvendev_dev_input) || length(input$codvendev_dev_input) == 0) TRUE else COD_VEN %in% input$codvendev_dev_input,
          # if (is.null(input$codmotdev_dev_input) || length(input$codmotdev_dev_input) == 0) TRUE else MOT %in% input$codmotdev_dev_input,
          # if (is.null(input$codclidev_dev_input) || length(input$codclidev_dev_input) == 0) TRUE else CLI %in% input$codclidev_dev_input,
          # if (is.null(input$codproddev_dev_input) || length(input$codproddev_dev_input) == 0) TRUE else CODR %in% input$codproddev_dev_input,
          # if (is.null(input$ultcompdev_dev_input) || length(input$ultcompdev_dev_input) == 0) TRUE else ULT_COMPRA %in% input$ultcompdev_dev_input,
          # if (is.null(input$devpeddev_dev_input) || length(input$devpeddev_dev_input) == 0) TRUE else Retorno %in% input$devpeddev_dev_input,
          if (is.null(input$data_dev_dev_input) || length(input$data_dev_dev_input) == 0) TRUE else MES_ATUAL %in% input$data_dev_dev_input
        )
    }

    dados
  })
  #
  #
  #
  observeEvent(filtro_base_dev_geral_dev(), {
    #
    #   # Atualiza apenas se não houver seleção
    if (is.null(input$datapeddev_dev_input) || length(input$datapeddev_dev_input) == 0) {
      updatePickerInput(session, "datapeddev_dev_input", choices = setNames(
        sort(unique(filtro_base_dev_geral_dev()$DATA_VENDA)),
        format(as.Date(sort(unique(filtro_base_dev_geral_dev()$DATA_VENDA)), format = "%Y%m%d"), "%d/%m/%Y")
      ))
    }
    if (is.null(input$revendadev_dev_input) || length(input$revendadev_dev_input) == 0) {
      updatePickerInput(session, "revendadev_dev_input", choices = sort(unique(filtro_base_dev_geral_dev()$GRUPO_REV)))
    }
    # if (is.null(input$codpeddev_dev_input) || length(input$codpeddev_dev_input) == 0) {
    #   updatePickerInput(session, "codpeddev_dev_input", choices = sort(unique(filtro_base_dev_geral_dev()$COD_PED)))
    # }
    # if (is.null(input$codvendev_dev_input) || length(input$codvendev_dev_input) == 0) {
    #   updatePickerInput(session, "codvendev_dev_input", choices = sort(unique(filtro_base_dev_geral_dev()$COD_VEN)))
    # }
    # if (is.null(input$codmotdev_dev_input) || length(input$codmotdev_dev_input) == 0) {
    #   updatePickerInput(session, "codmotdev_dev_input", choices = sort(unique(filtro_base_dev_geral_dev()$MOT)))
    # }
    # if (is.null(input$codclidev_dev_input) || length(input$codclidev_dev_input) == 0) {
    #   updatePickerInput(session, "codclidev_dev_input", choices = sort(unique(filtro_base_dev_geral_dev()$CLI)))
    # }
    # if (is.null(input$codproddev_dev_input) || length(input$codproddev_dev_input) == 0) {
    #   updatePickerInput(session, "codproddev_dev_input", choices = sort(unique(filtro_base_dev_geral_dev()$CODR)))
    # }
    # if (is.null(input$ultcompdev_dev_input) || length(input$ultcompdev_dev_input) == 0) {
    #   updatePickerInput(session, "ultcompdev_dev_input", choices = sort(unique(filtro_base_dev_geral_dev()$ULT_COMPRA)))
    # }
    # if (is.null(input$devpeddev_dev_input) || length(input$devpeddev_dev_input) == 0) {
    #   updatePickerInput(session, "devpeddev_dev_input", choices = sort(unique(filtro_base_dev_geral_dev()$Retorno)))
    # }
    if (is.null(input$data_dev_dev_input) || length(input$data_dev_dev_input) == 0) {
      updatePickerInput(session, "data_dev_dev_input", choices = sort(unique(filtro_base_dev_geral_dev()$MES_ATUAL)))
    }
  })


  filtro_base_dev_mensal_dev <- reactive({
    if (
      (is.null(input$revendadev_dev_input) || length(input$revendadev_dev_input) == 0)
    ) {
      dados <- dev_geral_mensal()
    } else {
      dados <- dev_geral_mensal() %>%
        filter(
          if (is.null(input$revendadev_dev_input) || length(input$revendadev_dev_input) == 0) TRUE else GRUPO_REV %in% input$revendadev_dev_input
        )
    }

    dados
  })
  # Tabelas reativas ---------------------------------------------------------

  ### Tabela produtos ---------------------------------------------------------
  dev_prod_dev_reativa <- reactive({
    req(input$data_dev_dev_input)
    req(filtro_base_dev_geral_dev())

    conexao_duck_dev <- dbConnect(duckdb::duckdb())
    dbWriteTable(conexao_duck_dev, "geral_dev", filtro_base_dev_geral_dev(), overwrite = TRUE, row.names = FALSE)

    dev_dev_produto <- dbGetQuery(conexao_duck_dev, glue(
      "SELECT
      CODR AS Cod,
      PRODUTO AS Produto,
      SUM(\"VALOR VENDA\") AS Vendas,
      SUM(\"VALOR DEVOLUCAO\") AS Devolução,
      COALESCE(SUM(\"VALOR DEVOLUCAO\") / SUM(\"VALOR VENDA\"), 0) AS 'Taxa de retorno'

   FROM geral_dev
   GROUP BY CODR, PRODUTO
   "
    ))


    dbDisconnect(conexao_duck_dev)
    dev_dev_produto

    # df <- filtro_base_dev_geral_dev()
    #
    # df %>%
    #   group_by(CODR, PRODUTO) %>%
    #   summarise(
    #     Vendas = sum(`VALOR VENDA`, na.rm = TRUE),
    #     Devolucao = sum(`VALOR DEVOLUCAO`, na.rm = TRUE),
    #     `Taxa de retorno` = sum(`VALOR DEVOLUCAO`, na.rm = TRUE)/sum(`VALOR VENDA`, na.rm = TRUE),
    #     .groups = "drop"
    #   )
  })


  output$tabela_devproduto_reativa <- renderReactable({
    # req(input$data_dev_dev_input)
    # req(filtro_base_dev_geral_dev())


    reactable(
      dev_prod_dev_reativa(),
      defaultColDef = colDef(align = "center"),
      columns = list(
        Produto = colDef(cell = function(value) {
          str_to_title(value)
        }),
        Vendas = colDef(format = colFormat(prefix = "R$ ", digits = 2, separators = TRUE)),
        Devolução = colDef(format = colFormat(prefix = "R$ ", digits = 2, separators = TRUE)),
        `Taxa de retorno` = colDef(format = colFormat(percent = TRUE, digits = 2))
      ),
      defaultSorted = "Taxa de retorno",
      defaultSortOrder = "desc",
      pagination = TRUE,
      defaultPageSize = 100,
      pageSizeOptions = c(100, 500, 1000),
      showPageSizeOptions = TRUE,
      wrap = FALSE,
      height = "50vh",
      language = reactableLang(
        pageNext = "Próxima",
        pagePrevious = "Anterior",
        pageNumbers = "{página} of {páginas}",
        pageInfo = "{rowStart}\u2013{rowEnd} de {rows} linhas",
        pageSizeOptions = "Mostrar {rows}",
        pageNextLabel = "Próxima página",
        pagePreviousLabel = "Página anterior",
        pageNumberLabel = "Pág {page}",
        pageJumpLabel = "Ir para a página",
        pageSizeOptionsLabel = "Linhas por página"
      ),
      style = list(overflowX = "auto"),
      theme = reactableTheme(
        backgroundColor = "transparent", headerStyle = list(
          backgroundColor = glue("{cores_reativo()[2]}"),
          color = "white",
          fontWeight = "bold",
          textAlign = "center"
        ),
        rowSelectedStyle = list(
          backgroundColor = "darkgray",
          boxShadow = glue("inset 2px 0 0 0 {cores_reativo()[1]}")
        )
      )
    )
  })

  ### Tabela motoristas ---------------------------------------------------------
  dev_mot_dev_reativa <- reactive({
    req(input$data_dev_dev_input)
    req(filtro_base_dev_geral_dev())

    conexao_duck_dev <- dbConnect(duckdb::duckdb())
    dbWriteTable(conexao_duck_dev, "geral_dev", filtro_base_dev_geral_dev(), overwrite = TRUE, row.names = FALSE)

    dev_dev_motorista <- dbGetQuery(conexao_duck_dev, glue(
      "SELECT
      MOT AS Cod,
      NOME_MOT AS Nome,
      SUM(\"VALOR VENDA\") AS Vendas,
      SUM(\"VALOR DEVOLUCAO\") AS Devolução,
      COALESCE(SUM(\"VALOR DEVOLUCAO\") / SUM(\"VALOR VENDA\"), 0) AS 'Taxa de retorno'

   FROM geral_dev
   GROUP BY MOT, NOME_MOT
   "
    ))

    # df <- filtro_base_dev_geral_dev()
    #
    # df %>%
    #   group_by(MOT, NOME_MOT) %>%
    #   summarise(
    #     Vendas = sum(`VALOR VENDA`, na.rm = TRUE),
    #     Devolucao = sum(`VALOR DEVOLUCAO`, na.rm = TRUE),
    #     `Taxa de retorno` = sum(`VALOR DEVOLUCAO`, na.rm = TRUE)/sum(`VALOR VENDA`, na.rm = TRUE),
    #     .groups = "drop"
    #   )
    #
    dbDisconnect(conexao_duck_dev)
    dev_dev_motorista
  })


  output$tabela_devmotorista_reativa <- renderReactable({
    # req(input$data_dev_dev_input)
    # req(filtro_base_dev_geral_dev())


    reactable(
      dev_mot_dev_reativa(),
      defaultColDef = colDef(align = "center"),
      columns = list(
        Nome = colDef(cell = function(value) {
          str_to_title(value)
        }),
        Vendas = colDef(format = colFormat(prefix = "R$ ", digits = 2, separators = TRUE)),
        Devolução = colDef(format = colFormat(prefix = "R$ ", digits = 2, separators = TRUE)),
        `Taxa de retorno` = colDef(format = colFormat(percent = TRUE, digits = 2))
      ),
      defaultSorted = "Taxa de retorno",
      defaultSortOrder = "desc",
      pagination = TRUE,
      defaultPageSize = 100,
      pageSizeOptions = c(100, 500, 1000),
      showPageSizeOptions = TRUE,
      wrap = FALSE,
      height = "50vh",
      language = reactableLang(
        pageNext = "Próxima",
        pagePrevious = "Anterior",
        pageNumbers = "{página} of {páginas}",
        pageInfo = "{rowStart}\u2013{rowEnd} de {rows} linhas",
        pageSizeOptions = "Mostrar {rows}",
        pageNextLabel = "Próxima página",
        pagePreviousLabel = "Página anterior",
        pageNumberLabel = "Pág {page}",
        pageJumpLabel = "Ir para a página",
        pageSizeOptionsLabel = "Linhas por página"
      ),
      style = list(overflowX = "auto"),
      theme = reactableTheme(
        backgroundColor = "transparent", headerStyle = list(
          backgroundColor = glue("{cores_reativo()[2]}"),
          color = "white",
          fontWeight = "bold",
          textAlign = "center"
        ),
        rowSelectedStyle = list(
          backgroundColor = "darkgray",
          boxShadow = glue("inset 2px 0 0 0 {cores_reativo()[1]}")
        )
      )
    )
  })

  ### Tabela vendedores ---------------------------------------------------------
  dev_ven_dev_reativa <- reactive({
    req(input$data_dev_dev_input)
    req(filtro_base_dev_geral_dev())

    conexao_duck_dev <- dbConnect(duckdb::duckdb())
    dbWriteTable(conexao_duck_dev, "geral_dev", filtro_base_dev_geral_dev(), overwrite = TRUE, row.names = FALSE)

    dev_dev_vendedor <- dbGetQuery(conexao_duck_dev, glue(
      "SELECT
      COD_VEN AS Cod,
      NOME_VEN AS Nome,
      SUM(\"VALOR VENDA\") AS Vendas,
      SUM(\"VALOR DEVOLUCAO\") AS Devolução,
      COALESCE(SUM(\"VALOR DEVOLUCAO\") / SUM(\"VALOR VENDA\"), 0) AS 'Taxa de retorno'

   FROM geral_dev
   GROUP BY COD_VEN, NOME_VEN
   "
    ))


    dbDisconnect(conexao_duck_dev)
    dev_dev_vendedor
    #
    # df <- filtro_base_dev_geral_dev()
    #
    # df %>%
    #   group_by(COD_VEN, NOME_VEN) %>%
    #   summarise(
    #     Vendas = sum(`VALOR VENDA`, na.rm = TRUE),
    #     Devolucao = sum(`VALOR DEVOLUCAO`, na.rm = TRUE),
    #     `Taxa de retorno` = sum(`VALOR DEVOLUCAO`, na.rm = TRUE)/sum(`VALOR VENDA`, na.rm = TRUE),
    #     .groups = "drop"
    #   )
  })


  output$tabela_devvendedor_reativa <- renderReactable({
    # req(input$data_dev_dev_input)
    # req(filtro_base_dev_geral_dev())


    reactable(
      dev_ven_dev_reativa(),
      defaultColDef = colDef(align = "center"),
      columns = list(
        Nome = colDef(cell = function(value) {
          str_to_title(value)
        }),
        Vendas = colDef(format = colFormat(prefix = "R$ ", digits = 2, separators = TRUE)),
        Devolução = colDef(format = colFormat(prefix = "R$ ", digits = 2, separators = TRUE)),
        `Taxa de retorno` = colDef(format = colFormat(percent = TRUE, digits = 2))
      ),
      defaultSorted = "Taxa de retorno",
      defaultSortOrder = "desc",
      pagination = TRUE,
      defaultPageSize = 100,
      pageSizeOptions = c(100, 500, 1000),
      showPageSizeOptions = TRUE,
      wrap = FALSE,
      height = "50vh",
      language = reactableLang(
        pageNext = "Próxima",
        pagePrevious = "Anterior",
        pageNumbers = "{página} of {páginas}",
        pageInfo = "{rowStart}\u2013{rowEnd} de {rows} linhas",
        pageSizeOptions = "Mostrar {rows}",
        pageNextLabel = "Próxima página",
        pagePreviousLabel = "Página anterior",
        pageNumberLabel = "Pág {page}",
        pageJumpLabel = "Ir para a página",
        pageSizeOptionsLabel = "Linhas por página"
      ),
      style = list(overflowX = "auto"),
      theme = reactableTheme(
        backgroundColor = "transparent", headerStyle = list(
          backgroundColor = glue("{cores_reativo()[2]}"),
          color = "white",
          fontWeight = "bold",
          textAlign = "center"
        ),
        rowSelectedStyle = list(
          backgroundColor = "darkgray",
          boxShadow = glue("inset 2px 0 0 0 {cores_reativo()[1]}")
        )
      )
    )
  })

  ### Tabela clientes ---------------------------------------------------------
  dev_cli_dev_reativa <- reactive({
    req(input$data_dev_dev_input)
    req(filtro_base_dev_geral_dev())

    conexao_duck_dev <- dbConnect(duckdb::duckdb())
    dbWriteTable(conexao_duck_dev, "geral_dev", filtro_base_dev_geral_dev(), overwrite = TRUE, row.names = FALSE)

    dev_dev_cliente <- dbGetQuery(conexao_duck_dev, glue(
      "SELECT
      CLI AS Cod,
      FANTASIA AS Fantasia,
      SUM(\"VALOR VENDA\") AS Vendas,
      SUM(\"VALOR DEVOLUCAO\") AS Devolução,
      COALESCE(SUM(\"VALOR DEVOLUCAO\") / SUM(\"VALOR VENDA\"), 0) AS 'Taxa de retorno'

   FROM geral_dev
   GROUP BY CLI, FANTASIA
   "
    ))


    dbDisconnect(conexao_duck_dev)
    dev_dev_cliente

    # df <- filtro_base_dev_geral_dev()
    #
    # df %>%
    #   group_by(CLI, FANTASIA) %>%
    #   summarise(
    #     Vendas = sum(`VALOR VENDA`, na.rm = TRUE),
    #     Devolucao = sum(`VALOR DEVOLUCAO`, na.rm = TRUE),
    #     `Taxa de retorno` = sum(`VALOR DEVOLUCAO`, na.rm = TRUE)/sum(`VALOR VENDA`, na.rm = TRUE),
    #     .groups = "drop"
    #   )
  })


  output$tabela_devcliente_reativa <- renderReactable({
    # req(input$data_dev_dev_input)
    # req(filtro_base_dev_geral_dev())


    reactable(
      dev_cli_dev_reativa(),
      defaultColDef = colDef(align = "center"),
      columns = list(
        Fantasia = colDef(cell = function(value) {
          str_to_title(value)
        }),
        Vendas = colDef(format = colFormat(prefix = "R$ ", digits = 2, separators = TRUE)),
        Devolução = colDef(format = colFormat(prefix = "R$ ", digits = 2, separators = TRUE)),
        `Taxa de retorno` = colDef(format = colFormat(percent = TRUE, digits = 2))
      ),
      defaultSorted = "Taxa de retorno",
      defaultSortOrder = "desc",
      pagination = TRUE,
      defaultPageSize = 100,
      pageSizeOptions = c(100, 500, 1000),
      showPageSizeOptions = TRUE,
      wrap = FALSE,
      height = "50vh",
      language = reactableLang(
        pageNext = "Próxima",
        pagePrevious = "Anterior",
        pageNumbers = "{página} of {páginas}",
        pageInfo = "{rowStart}\u2013{rowEnd} de {rows} linhas",
        pageSizeOptions = "Mostrar {rows}",
        pageNextLabel = "Próxima página",
        pagePreviousLabel = "Página anterior",
        pageNumberLabel = "Pág {page}",
        pageJumpLabel = "Ir para a página",
        pageSizeOptionsLabel = "Linhas por página"
      ),
      style = list(overflowX = "auto"),
      theme = reactableTheme(
        backgroundColor = "transparent", headerStyle = list(
          backgroundColor = glue("{cores_reativo()[2]}"),
          color = "white",
          fontWeight = "bold",
          textAlign = "center"
        ),
        rowSelectedStyle = list(
          backgroundColor = "darkgray",
          boxShadow = glue("inset 2px 0 0 0 {cores_reativo()[1]}")
        )
      )
    )
  })

  # Gráfico reativo ---------------------------------------------------------

  graf_dev_mensal <- reactive({
    req(filtro_base_dev_mensal_dev())

    conexao_duck_dev <- dbConnect(duckdb::duckdb())
    dbWriteTable(conexao_duck_dev, "geral_dev", filtro_base_dev_mensal_dev(), overwrite = TRUE, row.names = FALSE)

    dev_dev_cliente <- dbGetQuery(conexao_duck_dev, glue(
      "SELECT
      MES,
      COALESCE(SUM(Devolução),0) AS Devolução
       FROM geral_dev
       GROUP BY MES
       "
    ))

    dbDisconnect(conexao_duck_dev)
    dev_dev_cliente

    # df <- filtro_base_dev_mensal_dev()
    #
    # df %>%
    #   group_by(MES) %>%
    #   summarise(
    #     Devolução = sum(Devolução, na.rm = TRUE),
    #     .groups = "drop"
    #   )
    #
  })


  output$grafico_dev_mensal <- renderPlotly({
    # Gráfico ggplot

    p <- ggplot(graf_dev_mensal(), aes(x = as.Date(paste0(MES, "01"), format = "%Y%m%d"), y = Devolução)) +
      geom_col(position = "dodge", colour = cores_reativo()[2], fill = cores_reativo()[2]) +
      scale_x_date(date_labels = "%b/%Y", date_breaks = "1 month") +
      geom_text(
        aes(
          label = scales::dollar(Devolução, accuracy = 0.01, big.mark = ".", decimal.mark = ",", prefix = "R$ "),
          y = Devolução + max(Devolução, na.rm = TRUE) * 0.07
        ),
        size = 2.5
      ) +
      scale_y_continuous(labels = scales::dollar_format(prefix = "R$ ", big.mark = ".", decimal.mark = ",")) +
      labs(x = "", y = "") +
      theme_minimal() +
      theme(
        axis.text.x = element_text(angle = 45, hjust = 1, color = "black"),
        axis.text.y = element_text(color = "black"),
        plot.title = element_text(face = "bold", size = 14, hjust = 0.5)
      )


    # Converter para plotly
    ggplotly(p, tooltip = "text") %>%
      layout(
        xaxis = list(
          tickangle = 45
        )
      )
  })

  # UI ----------------------------------------------------------------------

  fluidRow(
    column(
      12,
      box(
        id = "box_dev_dev_filtro",
        width = 12,
        collapsible = FALSE,
        status = "primary",
        title = fluidRow(
          column(1, pickerInput("datapeddev_dev_input", "Data do pedido", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
          column(1, pickerInput("revendadev_dev_input", "Revenda", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
          column(1, div(pickerInput("codpeddev_dev_input", "Cod Pedido", choices = NULL, multiple = TRUE, options = opcoes_filtro)), style = "visibility: hidden;"),
          column(1, div(pickerInput("codvendev_dev_input", "Cod Vendedores", choices = NULL, multiple = TRUE, options = opcoes_filtro)), style = "visibility: hidden;"),
          column(1, div(pickerInput("codmotdev_dev_input", "Cod Motoristas", choices = NULL, multiple = TRUE, options = opcoes_filtro)), style = "visibility: hidden;"),
          column(1, div(pickerInput("codclidev_dev_input", "Cod Clientes", choices = NULL, multiple = TRUE, options = opcoes_filtro)), style = "visibility: hidden;"),
          column(1, div(pickerInput("codproddev_dev_input", "Cod Produtos", choices = NULL, multiple = TRUE, options = opcoes_filtro)), style = "visibility: hidden;"),
          column(1, div(pickerInput("ultcompdev_dev_input", "Últ compra", choices = NULL, multiple = TRUE, options = opcoes_filtro)), style = "visibility: hidden;"),
          column(1, div(pickerInput("devpeddev_dev_input", "Devolução", choices = NULL, multiple = TRUE, options = opcoes_filtro)), style = "visibility: hidden;"),
          column(1),
          column(1, pickerInput("data_dev_dev_input", "Mês", choices = unique(data_calend()$Mes), selected = "Mês Atual", multiple = TRUE, options = opcoes_filtro)),
          column(1,
            style = "display: flex; align-items: center;",
            column(1),
            column(9, actionButton("bt_limpadev_dev", label = NULL, icon = icon("eraser"), status = "primary", size = "lg", width = "100%") %>% tagAppendAttributes(title = "Limpar filtros")),
            column(1)
          )
        )
      )
    ),
    column(
      12,
      fluidRow(
        column(
          6,
          box(
            title = "Devolução mensal",
            status = "primary",
            # solidHeader = TRUE,
            collapsible = TRUE,
            maximizable = TRUE,
            withSpinner(plotlyOutput("grafico_dev_mensal", height = "50vh"), type = 4),
            width = 12
          )
        ),
        column(
          6,
          box(
            title = "Produto",
            status = "primary",
            # solidHeader = TRUE,
            collapsible = TRUE,
            maximizable = TRUE,
            withSpinner(reactableOutput("tabela_devproduto_reativa"), type = 4),
            width = 12
          )
        )
      )
    ),
    column(
      12,
      fluidRow(
        column(
          4,
          box(
            title = "Motorista",
            status = "primary",
            # solidHeader = TRUE,
            collapsible = TRUE,
            maximizable = TRUE,
            withSpinner(reactableOutput("tabela_devmotorista_reativa"), type = 4),
            width = 12
          )
        ),
        column(
          4,
          box(
            title = "Vendedor",
            status = "primary",
            # solidHeader = TRUE,
            collapsible = TRUE,
            maximizable = TRUE,
            withSpinner(reactableOutput("tabela_devvendedor_reativa"), type = 4),
            width = 12
          )
        ),
        column(
          4,
          box(
            title = "Cliente",
            status = "primary",
            # solidHeader = TRUE,
            collapsible = TRUE,
            maximizable = TRUE,
            withSpinner(reactableOutput("tabela_devcliente_reativa"), type = 4),
            width = 12
          )
        )
      )
    )
  )
}
