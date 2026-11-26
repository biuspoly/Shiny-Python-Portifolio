pag_graf_dev <- function() {
  # Carregar e tratar dados ----------------------------------------------------------

  source(glue("{diretorio}pages/Devolucoes/Dados/dados_devolucoes.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Devolucoes/Dados/funcoes_data_cor.R"), local = TRUE, encoding = "UTF-8")

  # Server ------------------------------------------------------------------

  dev_geral_graf <- reactive({
    req(input$data_dev_graf_input) # garante que o input existe
    # devolucao_geral_graf = geral_dev(input$data_dev_graf_input)

    if (length(revenda_query()) == 0) {
      devolucao_geral_graf <- geral_dev(input$data_dev_graf_input, "HOLDING")
    }
    # else if (str_detect(revenda_query(), "LOCADORA" ) | str_detect(revenda_query(), "ARRENDADORA") | str_detect(revenda_query(), "TRANSPORTADORA")) {
    #   devolucao_geral_dev %>% filter(str_detect(toupper(EMPRESA), revenda_query()))
    # }
    else {
      # devolucao_geral_graf %>% filter(str_detect(toupper(Empresa), revenda_query()))
      devolucao_geral_graf <- geral_dev(input$data_dev_graf_input, revenda_query())
    }
  })


  # Textos reativos --------------------------------------------------------


  ### Ultima atualizacao --------------------------------------------------------
  output$ult_atualizacao_id_grafico_dev <- renderText({
    glue("Atualizado em: {format(Sys.Date(), '%d/%m/%Y')}")
  })

  ## Aviso --------------------------------------------------------


  # Botoes e filtros --------------------------------------------------------

  ### Botao  --------------------------------------------------------
  observeEvent(input$bt_limpadev_graf, {
    updatePickerInput(session, inputId = "datapeddev_graf_input", selected = character(0))
    updatePickerInput(session, inputId = "revendadev_graf_input", selected = character(0))
    # updatePickerInput(session,inputId = "codpeddev_dev_input",selected = character(0))
    # updatePickerInput(session,inputId = "codvendev_dev_input",selected = character(0))
    # updatePickerInput(session,inputId = "codmotdev_dev_input",selected = character(0))
    # updatePickerInput(session,inputId = "codproddev_dev_input",selected = character(0))
    updatePickerInput(session, inputId = "data_dev_graf_input", selected = "Mês Atual")
    updatePickerInput(session, inputId = "codclidev_graf_input", selected = character(0))
    # updatePickerInput(session,inputId = "ultcompdev_dev_input",selected = character(0))
    # updatePickerInput(session,inputId = "devpeddev_dev_input",selected = character(0))
  })

  ### Download  --------------------------------------------------------


  output$bt_download_id_grafico_dev <- downloadHandler(
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

      filtro_base_graf_geral_dev() %>%
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
  filtro_base_graf_geral_dev <- reactive({
    if (
      (is.null(input$datapeddev_graf_input) || length(input$datapeddev_graf_input) == 0) &&
        (is.null(input$revendadev_graf_input) || length(input$revendadev_graf_input) == 0) &&
        # (is.null(input$codpeddev_dev_input) || length(input$codpeddev_dev_input) == 0) &&
        # (is.null(input$codvendev_dev_input) || length(input$codvendev_dev_input) == 0) &&
        # (is.null(input$codmotdev_dev_input) || length(input$codmotdev_dev_input) == 0) &&
        # (is.null(input$codproddev_dev_input) || length(input$codproddev_dev_input) == 0) &&
        (is.null(input$data_dev_graf_input) || length(input$data_dev_graf_input) == 0) &&
        # (is.null(input$ultcompdev_dev_input) || length(input$ultcompdev_dev_input) == 0) &&
        # (is.null(input$devpeddev_dev_input) || length(input$devpeddev_dev_input) == 0) &&
        (is.null(input$codclidev_graf_input) || length(input$codclidev_graf_input) == 0)
    ) {
      dados <- dev_geral_graf()
    } else {
      dados <- dev_geral_graf() %>%
        filter(
          if (is.null(input$datapeddev_graf_input) || length(input$datapeddev_graf_input) == 0) TRUE else DATA_VENDA %in% input$datapeddev_graf_input,
          if (is.null(input$revendadev_graf_input) || length(input$revendadev_graf_input) == 0) TRUE else GRUPO_REV %in% input$revendadev_graf_input,
          # if (is.null(input$codpeddev_dev_input) || length(input$codpeddev_dev_input) == 0) TRUE else COD_PED %in% input$codpeddev_dev_input,
          # if (is.null(input$codvendev_dev_input) || length(input$codvendev_dev_input) == 0) TRUE else COD_VEN %in% input$codvendev_dev_input,
          # if (is.null(input$codmotdev_dev_input) || length(input$codmotdev_dev_input) == 0) TRUE else MOT %in% input$codmotdev_dev_input,
          if (is.null(input$codclidev_graf_input) || length(input$codclidev_graf_input) == 0) TRUE else COD_CLIENTE %in% input$codclidev_graf_input,
          # if (is.null(input$codproddev_dev_input) || length(input$codproddev_dev_input) == 0) TRUE else CODR %in% input$codproddev_dev_input,
          # if (is.null(input$ultcompdev_dev_input) || length(input$ultcompdev_dev_input) == 0) TRUE else ULT_COMPRA %in% input$ultcompdev_dev_input,
          # if (is.null(input$devpeddev_dev_input) || length(input$devpeddev_dev_input) == 0) TRUE else Retorno %in% input$devpeddev_dev_input,
          if (is.null(input$data_dev_graf_input) || length(input$data_dev_graf_input) == 0) TRUE else MES_ATUAL %in% input$data_dev_graf_input
        )
    }

    dados
  })
  #
  #
  #
  observeEvent(filtro_base_graf_geral_dev(), {
    #
    #   # Atualiza apenas se não houver seleção
    if (is.null(input$datapeddev_graf_input) || length(input$datapeddev_graf_input) == 0) {
      updatePickerInput(session, "datapeddev_graf_input", choices = setNames(
        sort(unique(filtro_base_graf_geral_dev()$DATA_VENDA)),
        format(as.Date(sort(unique(filtro_base_graf_geral_dev()$DATA_VENDA)), format = "%Y%m%d"), "%d/%m/%Y")
      ))
    }
    if (is.null(input$revendadev_graf_input) || length(input$revendadev_graf_input) == 0) {
      updatePickerInput(session, "revendadev_graf_input", choices = sort(unique(filtro_base_graf_geral_dev()$GRUPO_REV)))
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
    if (is.null(input$codclidev_graf_input) || length(input$codclidev_graf_input) == 0) {
      updatePickerInput(session, "codclidev_graf_input", choices = sort(unique(filtro_base_graf_geral_dev()$COD_CLIENTE)))
    }
    # if (is.null(input$codproddev_dev_input) || length(input$codproddev_dev_input) == 0) {
    #   updatePickerInput(session, "codproddev_dev_input", choices = sort(unique(filtro_base_dev_geral_dev()$CODR)))
    # }
    # if (is.null(input$ultcompdev_dev_input) || length(input$ultcompdev_dev_input) == 0) {
    #   updatePickerInput(session, "ultcompdev_dev_input", choices = sort(unique(filtro_base_dev_geral_dev()$ULT_COMPRA)))
    # }
    # if (is.null(input$devpeddev_dev_input) || length(input$devpeddev_dev_input) == 0) {
    #   updatePickerInput(session, "devpeddev_dev_input", choices = sort(unique(filtro_base_dev_geral_dev()$Retorno)))
    # }
    if (is.null(input$data_dev_graf_input) || length(input$data_dev_graf_input) == 0) {
      updatePickerInput(session, "data_dev_graf_input", choices = sort(unique(filtro_base_graf_geral_dev()$MES_ATUAL)))
    }
  })

  # Gráficos reativos ---------------------------------------------------------

  ### Gráfico produtos ---------------------------------------------------------
  graf_graf_prod <- reactive({
    req(filtro_base_graf_geral_dev())

    conexao_duck_graf <- dbConnect(duckdb::duckdb())
    dbWriteTable(conexao_duck_graf, "geral_dev", filtro_base_graf_geral_dev(), overwrite = TRUE, row.names = FALSE)

    dev_graf_produto <- dbGetQuery(conexao_duck_graf, glue(
      "SELECT
          PRODUTO_GENERICO AS Produto,
          SUM(\"VALOR DEVOLUCAO\") AS Devolucao,
          SUM(\"VALOR DEVOLUCAO\") / SUM(SUM(\"VALOR DEVOLUCAO\")) OVER() AS Percentual
       FROM geral_dev
       WHERE PRODUTO_GENERICO IS NOT NULL
       GROUP BY PRODUTO_GENERICO
       HAVING SUM(\"VALOR DEVOLUCAO\") > 0
       ORDER BY SUM(\"VALOR DEVOLUCAO\") DESC
       LIMIT 10
       "
    ))

    dbDisconnect(conexao_duck_graf)
    dev_graf_produto
  })


  output$graf_rankprod <- renderPlotly({
    # Gráfico ggplot

    p <- ggplot(graf_graf_prod(), aes(x = Devolucao, y = reorder(Produto, Devolucao))) +
      geom_col(position = "dodge", colour = cores_reativo()[2], fill = cores_reativo()[2]) +
      # scale_x_date(date_labels = "%b/%Y", date_breaks = "1 month") +
      geom_text(
        aes(
          label = paste0(scales::number(Devolucao, big.mark = ".", decimal.mark = ",", accuracy = 0.01, prefix = "R$ "), " (", scales::percent(Percentual, accuracy = 0.1), ")"),
          x = Devolucao + max(Devolucao, na.rm = TRUE) * 0.07
        ),
        size = 2.5
      ) +
      scale_x_continuous(labels = scales::dollar_format(prefix = "R$ ", big.mark = ".", decimal.mark = ",")) +
      scale_y_discrete(labels = function(x) str_wrap(str_to_title(x), width = 20)) +
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


  ### Gráfico motoristas ---------------------------------------------------------
  graf_graf_mot <- reactive({
    req(filtro_base_graf_geral_dev())

    conexao_duck_graf <- dbConnect(duckdb::duckdb())
    dbWriteTable(conexao_duck_graf, "geral_dev", filtro_base_graf_geral_dev(), overwrite = TRUE, row.names = FALSE)

    dev_graf_motorista <- dbGetQuery(conexao_duck_graf, glue(
      "SELECT
          COD_MOTORISTA AS 'Cod Motorista',
          SUM(\"VALOR DEVOLUCAO\") AS Devolucao,
          SUM(\"VALOR DEVOLUCAO\") / SUM(SUM(\"VALOR DEVOLUCAO\")) OVER() AS Percentual
       FROM geral_dev
       WHERE COD_MOTORISTA IS NOT NULL
       GROUP BY COD_MOTORISTA
       ORDER BY SUM(\"VALOR DEVOLUCAO\") DESC
       "
    ))

    dbDisconnect(conexao_duck_graf)
    dev_graf_motorista
  })


  output$graf_rankmot <- renderPlotly({
    # Gráfico ggplot

    p <- ggplot(graf_graf_mot(), aes(x = Devolucao, y = reorder(`Cod Motorista`, Devolucao))) +
      geom_col(position = "dodge", colour = cores_reativo()[2], fill = cores_reativo()[2]) +
      # scale_x_date(date_labels = "%b/%Y", date_breaks = "1 month") +
      geom_text(
        aes(
          label = paste0(scales::number(Devolucao, big.mark = ".", decimal.mark = ",", accuracy = 0.01, prefix = "R$ "), " (", scales::percent(Percentual, accuracy = 0.1), ")"),
          x = Devolucao + max(Devolucao, na.rm = TRUE) * 0.07
        ),
        size = 2.5
      ) +
      scale_x_continuous(labels = scales::dollar_format(prefix = "R$ ", big.mark = ".", decimal.mark = ",")) +
      scale_y_discrete(labels = function(x) str_wrap(str_to_title(x), width = 20)) +
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

  output$graf_rankmot_ui <- renderUI({
    req(graf_graf_mot())
    altura_interna <- max(300, nrow(graf_graf_mot()) * 40)
    div(
      style = "overflow-y: auto; height: 400px;",
      plotlyOutput("graf_rankmot", height = paste0(altura_interna, "px"))
    )
  })


  ### Tabela vendedores ---------------------------------------------------------
  graf_graf_ven <- reactive({
    req(filtro_base_graf_geral_dev())

    conexao_duck_graf <- dbConnect(duckdb::duckdb())
    dbWriteTable(conexao_duck_graf, "geral_dev", filtro_base_graf_geral_dev(), overwrite = TRUE, row.names = FALSE)

    dev_graf_vendedor <- dbGetQuery(conexao_duck_graf, glue(
      "SELECT
          COD_VENDEDOR AS 'Cod Vendedor',
          SUM(\"VALOR DEVOLUCAO\") AS Devolucao,
          SUM(\"VALOR DEVOLUCAO\") / SUM(SUM(\"VALOR DEVOLUCAO\")) OVER() AS Percentual
       FROM geral_dev
       WHERE COD_VENDEDOR IS NOT NULL
       GROUP BY COD_VENDEDOR
       ORDER BY SUM(\"VALOR DEVOLUCAO\") DESC
       "
    ))

    dbDisconnect(conexao_duck_graf)
    dev_graf_vendedor
  })


  output$graf_rankven <- renderPlotly({
    # Gráfico ggplot

    p <- ggplot(graf_graf_ven(), aes(x = Devolucao, y = reorder(`Cod Vendedor`, Devolucao))) +
      geom_col(position = "dodge", colour = cores_reativo()[2], fill = cores_reativo()[2]) +
      # scale_x_date(date_labels = "%b/%Y", date_breaks = "1 month") +
      geom_text(
        aes(
          label = paste0(scales::number(Devolucao, big.mark = ".", decimal.mark = ",", accuracy = 0.01, prefix = "R$ "), " (", scales::percent(Percentual, accuracy = 0.1), ")"),
          x = Devolucao + max(Devolucao, na.rm = TRUE) * 0.07
        ),
        size = 2.5
      ) +
      scale_x_continuous(labels = scales::dollar_format(prefix = "R$ ", big.mark = ".", decimal.mark = ",")) +
      scale_y_discrete(labels = function(x) str_wrap(str_to_title(x), width = 20)) +
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

  output$graf_rankven_ui <- renderUI({
    req(graf_graf_ven())
    altura_interna <- max(300, nrow(graf_graf_ven()) * 40)
    div(
      style = "overflow-y: auto; height: 400px;",
      plotlyOutput("graf_rankven", height = paste0(altura_interna, "px"))
    )
  })


  ### Tabela clientes ---------------------------------------------------------
  graf_graf_cliente <- reactive({
    req(filtro_base_graf_geral_dev())

    conexao_duck_graf <- dbConnect(duckdb::duckdb())
    dbWriteTable(conexao_duck_graf, "geral_dev", filtro_base_graf_geral_dev(), overwrite = TRUE, row.names = FALSE)

    dev_graf_cliente <- dbGetQuery(conexao_duck_graf, glue(
      "SELECT
          COD_CLIENTE AS 'Cod Cliente',
          SUM(\"VALOR DEVOLUCAO\") AS Devolucao,
          SUM(\"VALOR DEVOLUCAO\") / SUM(SUM(\"VALOR DEVOLUCAO\")) OVER() AS Percentual
       FROM geral_dev
       WHERE COD_CLIENTE IS NOT NULL
       GROUP BY COD_CLIENTE
       HAVING SUM(\"VALOR DEVOLUCAO\") > 0
       ORDER BY SUM(\"VALOR DEVOLUCAO\") DESC
       LIMIT 10
       "
    ))

    dbDisconnect(conexao_duck_graf)
    dev_graf_cliente
  })


  output$graf_rankcli <- renderPlotly({
    # Gráfico ggplot

    p <- ggplot(graf_graf_cliente(), aes(x = Devolucao, y = reorder(`Cod Cliente`, Devolucao))) +
      geom_col(position = "dodge", colour = cores_reativo()[2], fill = cores_reativo()[2]) +
      # scale_x_date(date_labels = "%b/%Y", date_breaks = "1 month") +
      geom_text(
        aes(
          label = paste0(scales::number(Devolucao, big.mark = ".", decimal.mark = ",", accuracy = 0.01, prefix = "R$ "), " (", scales::percent(Percentual, accuracy = 0.1), ")"),
          x = Devolucao + max(Devolucao, na.rm = TRUE) * 0.07
        ),
        size = 2.5
      ) +
      scale_x_continuous(labels = scales::dollar_format(prefix = "R$ ", big.mark = ".", decimal.mark = ",")) +
      scale_y_discrete(labels = function(x) str_wrap(str_to_title(x), width = 20)) +
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


  # Gráfico Motivo ---------------------------------------------------------

  graf_graf_motivo <- reactive({
    req(filtro_base_graf_geral_dev())

    conexao_duck_graf <- dbConnect(duckdb::duckdb())
    dbWriteTable(conexao_duck_graf, "geral_dev", filtro_base_graf_geral_dev(), overwrite = TRUE, row.names = FALSE)

    dev_graf_motivo <- dbGetQuery(conexao_duck_graf, glue(
      "SELECT
          VDCADDEV_DESCR AS 'Motivo',
          SUM(\"VALOR DEVOLUCAO\") AS Devolucao,
          SUM(\"VALOR DEVOLUCAO\") / SUM(SUM(\"VALOR DEVOLUCAO\")) OVER() AS Percentual
       FROM geral_dev
       WHERE VDCADDEV_DESCR IS NOT NULL
       GROUP BY VDCADDEV_DESCR
       HAVING SUM(\"VALOR DEVOLUCAO\") > 0
       ORDER BY SUM(\"VALOR DEVOLUCAO\") DESC
       LIMIT 10
       "
    ))

    dbDisconnect(conexao_duck_graf)
    dev_graf_motivo
  })


  output$graf_rankmotivo <- renderPlotly({
    # Gráfico ggplot

    p <- ggplot(graf_graf_motivo(), aes(x = Devolucao, y = reorder(Motivo, Devolucao))) +
      geom_col(position = "dodge", colour = cores_reativo()[2], fill = cores_reativo()[2]) +
      # scale_x_date(date_labels = "%b/%Y", date_breaks = "1 month") +
      geom_text(
        aes(
          label = paste0(scales::number(Devolucao, big.mark = ".", decimal.mark = ",", accuracy = 0.01, prefix = "R$ "), " (", scales::percent(Percentual, accuracy = 0.1), ")"),
          x = Devolucao + max(Devolucao, na.rm = TRUE) * 0.07
        ),
        size = 2.5
      ) +
      scale_x_continuous(labels = scales::dollar_format(prefix = "R$ ", big.mark = ".", decimal.mark = ",")) +
      scale_y_discrete(labels = function(x) str_wrap(str_to_title(x), width = 20)) +
      labs(x = "", y = "") +
      theme_minimal() +
      theme(
        axis.text.x = element_text(angle = 45, hjust = 1, color = "black"),
        axis.text.y = element_text(color = "black"),
        plot.title = element_text(face = "bold", size = 14, hjust = 0.5)
      )


    # Converter para plotly
    ggplotly(p, tooltip = "text")
  })

  # UI ----------------------------------------------------------------------

  fluidRow(
    column(
      12,
      box(
        id = "box_graf_dev_filtro",
        width = 12,
        collapsible = FALSE,
        status = "primary",
        title = fluidRow(
          column(1, pickerInput("datapeddev_graf_input", "Data do pedido", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
          column(1, pickerInput("revendadev_graf_input", "Revenda", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
          column(1, pickerInput("codclidev_graf_input", "Cod Clientes", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
          column(1, div(pickerInput("codpeddev_graf_input", "Cod Pedido", choices = NULL, multiple = TRUE, options = opcoes_filtro)), style = "visibility: hidden;"),
          column(1, div(pickerInput("codvendev_graf_input", "Cod Vendedores", choices = NULL, multiple = TRUE, options = opcoes_filtro)), style = "visibility: hidden;"),
          column(1, div(pickerInput("codmotdev_graf_input", "Cod Motoristas", choices = NULL, multiple = TRUE, options = opcoes_filtro)), style = "visibility: hidden;"),
          column(1, div(pickerInput("codproddev_graf_input", "Cod Produtos", choices = NULL, multiple = TRUE, options = opcoes_filtro)), style = "visibility: hidden;"),
          column(1, div(pickerInput("ultcompdev_graf_input", "Últ compra", choices = NULL, multiple = TRUE, options = opcoes_filtro)), style = "visibility: hidden;"),
          column(1, div(pickerInput("devpeddev_graf_input", "Devolução", choices = NULL, multiple = TRUE, options = opcoes_filtro)), style = "visibility: hidden;"),
          column(1),
          column(1, pickerInput("data_dev_graf_input", "Mês", choices = unique(data_calend()$Mes), selected = "Mês Atual", multiple = TRUE, options = opcoes_filtro)),
          column(1,
            style = "display: flex; align-items: center;",
            column(1),
            column(9, actionButton("bt_limpadev_graf", label = NULL, icon = icon("eraser"), status = "primary", size = "lg", width = "100%") %>% tagAppendAttributes(title = "Limpar filtros")),
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
            title = "Top 10 ranking de devolução - Produto",
            status = "primary",
            # solidHeader = TRUE,
            collapsible = TRUE,
            maximizable = TRUE,
            withSpinner(plotlyOutput("graf_rankprod", height = "50vh"), type = 4),
            width = 12
          )
        ),
        column(
          6,
          box(
            title = "Top 10 ranking de devolução - Cliente",
            status = "primary",
            # solidHeader = TRUE,
            collapsible = TRUE,
            maximizable = TRUE,
            withSpinner(plotlyOutput("graf_rankcli", height = "50vh"), type = 4),
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
            title = "Ranking de devolução - Motorista",
            status = "primary",
            # solidHeader = TRUE,
            collapsible = TRUE,
            maximizable = TRUE,
            uiOutput("graf_rankmot_ui"),
            width = 12
          )
        ),
        column(
          4,
          box(
            title = "Ranking de devolução - Vendedor",
            status = "primary",
            # solidHeader = TRUE,
            collapsible = TRUE,
            maximizable = TRUE,
            uiOutput("graf_rankven_ui"),
            width = 12
          )
        ),
        column(
          4,
          box(
            title = "Top 10 ranking de devolução - Motivo",
            status = "primary",
            # solidHeader = TRUE,
            collapsible = TRUE,
            maximizable = TRUE,
            withSpinner(plotlyOutput("graf_rankmotivo"), type = 4),
            width = 12
          )
        )
      )
    )
  )
}
