pag_det_dev <- function() {
  # Carregar e tratar dados ----------------------------------------------------------

  source(glue("{diretorio}pages/Devolucoes/Dados/dados_devolucoes.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Devolucoes/Dados/funcoes_data_cor.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Devolucoes/Guia_ajuda.R"), local = TRUE, encoding = "UTF-8")


  # Server ------------------------------------------------------------------


  dev_geral <- reactive({
    req(input$data_dev_input) # garante que o input existe
    # devolucao_geral = geral_dev(input$data_dev_input)

    if (length(revenda_query()) == 0) {
      devolucao_geral <- geral_dev(input$data_dev_input, "HOLDING")
    }
    # else if (str_detect(revenda_query(), "LOCADORA" ) | str_detect(revenda_query(), "ARRENDADORA") | str_detect(revenda_query(), "TRANSPORTADORA")) {
    #   devolucao_geral %>% filter(str_detect(toupper(EMPRESA), revenda_query()))
    # }
    else {
      # devolucao_geral %>% filter(str_detect(toupper(Empresa), revenda_query()))
      devolucao_geral <- geral_dev(input$data_dev_input, revenda_query())
    }
  })



  # Reativo para itens
  dev_geral_itens <- reactive({
    req(dev_geral())
    geral_dev_itens(unique(dev_geral()$COD_PED))
  })

  # Textos reativos --------------------------------------------------------

  ### Ultima atualizacao --------------------------------------------------------
  output$ult_atualizacao_id_detalhe_dev <- renderText({
    glue("Atualizado em: {format(Sys.Date(), '%d/%m/%Y')}")
  })

  ## Aviso --------------------------------------------------------
  output$aviso_id_detalhe_dev <- renderUI({
    req(filtro_base_dev_geral())
    valores_resumidos <- filtro_base_dev_geral() %>%
      summarise(
        Vendas = round(sum(`VALOR VENDA`), 2),
        Devoluções = round(sum(`VALOR DEVOLUCAO`), 2),
        Retorno = round(sum(`VALOR DEVOLUCAO`), 2) / round(sum(`VALOR VENDA`), 2)
      )

    box(
      elevation = 2,
      id = "box_taxa_retorno_det",
      div(
        "Tx retorno (Fin):",
        style = "font-size: 12px;"
      ),
      div(
        scales::percent(valores_resumidos$Retorno, suffix = "%", accuracy = 0.01, decimal.mark = ","),
        style = "font-size: 14px;"
      ),
      background = ifelse(is.na(valores_resumidos$Retorno) | valores_resumidos$Retorno <= 0.02,
        "success",
        "danger"
      ),
      height = "50px"
    )
  })

  # Botoes e filtros --------------------------------------------------------

  ### Botao  --------------------------------------------------------
  observeEvent(input$bt_limpadet_dev, {
    updatePickerInput(session, inputId = "dataped_dev_input", selected = character(0))
    updatePickerInput(session, inputId = "revenda_dev_input", selected = character(0))
    updatePickerInput(session, inputId = "codped_dev_input", selected = character(0))
    updatePickerInput(session, inputId = "codven_dev_input", selected = character(0))
    updatePickerInput(session, inputId = "codmot_dev_input", selected = character(0))
    updatePickerInput(session, inputId = "codprod_dev_input", selected = character(0))
    updatePickerInput(session, inputId = "data_dev_input", selected = "Mês Atual")
    updatePickerInput(session, inputId = "codcli_dev_input", selected = character(0))
    updatePickerInput(session, inputId = "ultcomp_dev_input", selected = character(0))
    updatePickerInput(session, inputId = "devped_dev_input", selected = character(0))
    updatePickerInput(session, inputId = "motivo_dev_input", selected = character(0))
  })

  output$switch_consolidado_detal <- renderUI({
    prettySwitch(
      inputId = "switch_consolidado_detal_dev",
      label = NULL,
      status = "success",
      fill = TRUE,
      bigger = FALSE
    )
  })

  output$tipo_dados_dev <- renderText({
    if (isFALSE(input$switch_consolidado_detal_dev)) {
      texto_reativo <- "Dados consolidados"
    } else {
      texto_reativo <- "Dados detalhados"
    }
  })

  output$tabela_dev_selecionada <- renderUI({
    if (isFALSE(input$switch_consolidado_detal_dev)) {
      withSpinner(reactableOutput("tabela_devconsolidada_reativa"), type = 4)
    } else {
      withSpinner(reactableOutput("tabela_devdetalhada_reativa"), type = 4)
    }
  })

  ### Download  --------------------------------------------------------


  output$bt_download_id_detalhe_dev <- downloadHandler(
    filename = function() {
      paste("devolucao-", Sys.Date(), ".xlsx", sep = "")
    },
    content = function(con) {
      if (isFALSE(input$switch_consolidado_detal_dev)) {
        colunas_remover <- c()

        dev_consolidada_reativa() %>%
          dplyr::ungroup() %>% # <- garante que não está mais agrupado
          dplyr::select(-dplyr::any_of(colunas_remover)) %>%
          writexl::write_xlsx(con)
      } else {
        colunas_remover <- c()

        dev_detalhada_reativa() %>%
          dplyr::ungroup() %>% # <- garante que não está mais agrupado
          dplyr::select(-dplyr::any_of(colunas_remover)) %>%
          writexl::write_xlsx(con)
      }
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

  ### Ajuda --------------------------------------------------------

  observeEvent(input$bt_guia_id_detalhe_dev, {
    if (isFALSE(input$switch_consolidado_detal_dev)) {
      funcao_guia_dev("Detalhes")$init()$start()
    } else {
      funcao_guia_dev("Detalhes det")$init()$start()
    }
  })


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
  filtro_base_dev_geral <- reactive({
    if (
      (is.null(input$dataped_dev_input) || length(input$dataped_dev_input) == 0) &&
        (is.null(input$revenda_dev_input) || length(input$revenda_dev_input) == 0) &&
        (is.null(input$codped_dev_input) || length(input$codped_dev_input) == 0) &&
        (is.null(input$codven_dev_input) || length(input$codven_dev_input) == 0) &&
        (is.null(input$codmot_dev_input) || length(input$codmot_dev_input) == 0) &&
        (is.null(input$codprod_dev_input) || length(input$codprod_dev_input) == 0) &&
        (is.null(input$data_dev_input) || length(input$data_dev_input) == 0) &&
        (is.null(input$ultcomp_dev_input) || length(input$ultcomp_dev_input) == 0) &&
        (is.null(input$devped_dev_input) || length(input$devped_dev_input) == 0) &&
        (is.null(input$motivo_dev_input) || length(input$motivo_dev_input) == 0) &&
        (is.null(input$codcli_dev_input) || length(input$codcli_dev_input) == 0)) {
      dados <- dev_geral()
    } else {
      dados <- dev_geral() %>%
        filter(
          if (is.null(input$dataped_dev_input) || length(input$dataped_dev_input) == 0) TRUE else DATA_VENDA %in% input$dataped_dev_input,
          if (is.null(input$revenda_dev_input) || length(input$revenda_dev_input) == 0) TRUE else GRUPO_REV %in% input$revenda_dev_input,
          if (is.null(input$codped_dev_input) || length(input$codped_dev_input) == 0) TRUE else COD_PED %in% input$codped_dev_input,
          if (is.null(input$codven_dev_input) || length(input$codven_dev_input) == 0) TRUE else COD_VENDEDOR %in% input$codven_dev_input,
          if (is.null(input$codmot_dev_input) || length(input$codmot_dev_input) == 0) TRUE else COD_MOTORISTA %in% input$codmot_dev_input,
          if (is.null(input$codcli_dev_input) || length(input$codcli_dev_input) == 0) TRUE else COD_CLIENTE %in% input$codcli_dev_input,
          if (is.null(input$codprod_dev_input) || length(input$codprod_dev_input) == 0) TRUE else COD_PRODUTO %in% input$codprod_dev_input,
          if (is.null(input$ultcomp_dev_input) || length(input$ultcomp_dev_input) == 0) TRUE else ULT_COMPRA %in% input$ultcomp_dev_input,
          if (is.null(input$devped_dev_input) || length(input$devped_dev_input) == 0) TRUE else Retorno %in% input$devped_dev_input,
          if (is.null(input$data_dev_input) || length(input$data_dev_input) == 0) TRUE else MES_ATUAL %in% input$data_dev_input,
          if (is.null(input$motivo_dev_input) || length(input$motivo_dev_input) == 0) TRUE else VDCADDEV_DESCR %in% input$motivo_dev_input
        )
    }

    dados
  })
  #
  #
  #
  observeEvent(filtro_base_dev_geral(), {
    #
    #   # Atualiza apenas se não houver seleção
    if (is.null(input$dataped_dev_input) || length(input$dataped_dev_input) == 0) {
      updatePickerInput(session, "dataped_dev_input", choices = setNames(
        sort(unique(filtro_base_dev_geral()$DATA_VENDA)),
        format(as.Date(sort(unique(filtro_base_dev_geral()$DATA_VENDA)), format = "%Y%m%d"), "%d/%m/%Y")
      ))
    }
    if (is.null(input$revenda_dev_input) || length(input$revenda_dev_input) == 0) {
      updatePickerInput(session, "revenda_dev_input", choices = sort(unique(filtro_base_dev_geral()$GRUPO_REV)))
    }
    if (is.null(input$codped_dev_input) || length(input$codped_dev_input) == 0) {
      updatePickerInput(session, "codped_dev_input", choices = sort(unique(filtro_base_dev_geral()$COD_PED)))
    }
    if (is.null(input$codven_dev_input) || length(input$codven_dev_input) == 0) {
      updatePickerInput(session, "codven_dev_input", choices = sort(unique(filtro_base_dev_geral()$COD_VENDEDOR)))
    }
    if (is.null(input$codmot_dev_input) || length(input$codmot_dev_input) == 0) {
      updatePickerInput(session, "codmot_dev_input", choices = sort(unique(filtro_base_dev_geral()$COD_MOTORISTA)))
    }
    if (is.null(input$codcli_dev_input) || length(input$codcli_dev_input) == 0) {
      updatePickerInput(session, "codcli_dev_input", choices = sort(unique(filtro_base_dev_geral()$COD_CLIENTE)))
    }
    if (is.null(input$codprod_dev_input) || length(input$codprod_dev_input) == 0) {
      updatePickerInput(session, "codprod_dev_input", choices = sort(unique(filtro_base_dev_geral()$COD_PRODUTO)))
    }
    if (is.null(input$ultcomp_dev_input) || length(input$ultcomp_dev_input) == 0) {
      updatePickerInput(session, "ultcomp_dev_input", choices = setNames(
        sort(unique(filtro_base_dev_geral()$ULT_COMPRA)),
        format(as.Date(sort(unique(filtro_base_dev_geral()$ULT_COMPRA)), format = "%Y%m%d"), "%d/%m/%Y")
      ))
    }
    if (is.null(input$devped_dev_input) || length(input$devped_dev_input) == 0) {
      updatePickerInput(session, "devped_dev_input", choices = sort(unique(filtro_base_dev_geral()$Retorno)))
    }
    if (is.null(input$data_dev_input) || length(input$data_dev_input) == 0) {
      updatePickerInput(session, "data_dev_input", choices = sort(unique(filtro_base_dev_geral()$MES_ATUAL)))
    }
    if (is.null(input$motivo_dev_input) || length(input$motivo_dev_input) == 0) {
      updatePickerInput(session, "motivo_dev_input", choices = sort(unique(filtro_base_dev_geral()$VDCADDEV_DESCR[!is.na(filtro_base_dev_geral()$VDCADDEV_DESCR)])))
    }
  })

  # Tabelas reativas ---------------------------------------------------------

  ### Tabela consolidada ---------------------------------------------------------
  dev_consolidada_reativa <- reactive({
    req(input$data_dev_input)
    req(filtro_base_dev_geral())

    conexao_duck_dev <- dbConnect(duckdb::duckdb())
    dbWriteTable(conexao_duck_dev, "geral_dev", filtro_base_dev_geral(), overwrite = TRUE, row.names = FALSE)

    dados_dev_consolidados <- dbGetQuery(conexao_duck_dev, glue(
      "SELECT
      DATA_VENDA AS 'Data do pedido',
      Empresa,
      GRUPO_REV as Grupo_rev,
      --'R$ ' || format('{{:t..2f}}', SUM(\"VALOR VENDA\")) AS Vendas,
      --'R$ ' || format('{{:t..2f}}', SUM(\"VALOR DEVOLUCAO\")) AS Devolução,
      --format('{{:t..2f}}', COALESCE(SUM(\"VALOR DEVOLUCAO\") / SUM(\"VALOR VENDA\") * 100, 0)) || '%' AS 'Taxa de retorno',
      SUM(\"VALOR VENDA\") AS Vendas,
      SUM(\"VALOR DEVOLUCAO\") AS Devolução,
      COALESCE(SUM(\"VALOR DEVOLUCAO\") / SUM(\"VALOR VENDA\") * 100, 0) AS 'Taxa de retorno',
      COUNT(DISTINCT COD_PED) AS 'Num de pedidos',
      COUNT(DISTINCT CASE WHEN \"VALOR DEVOLUCAO\" > 0 THEN COD_PED END) AS 'Pedidos devolvidos'
      FROM geral_dev
      GROUP BY DATA_VENDA, Empresa, GRUPO_REV
      ORDER BY DATA_VENDA DESC"
    ))


    dbDisconnect(conexao_duck_dev)
    dados_dev_consolidados
  })

  ### Tabela detalhada ---------------------------------------------------------
  dev_detalhada_reativa <- reactive({
    req(input$data_dev_input)
    req(filtro_base_dev_geral())

    conexao_duck_dev <- dbConnect(duckdb::duckdb())
    dbWriteTable(conexao_duck_dev, "geral_dev", filtro_base_dev_geral(), overwrite = TRUE, row.names = FALSE)

    dados_dev_detalhados <- dbGetQuery(conexao_duck_dev, glue(
      "SELECT
            DATA_DEV AS 'Data de devolução',
            DATA_VENDA AS 'Data do pedido',
            Empresa,
            GRUPO_REV as Revenda,
            CHAVE_VDI,
            COD_PED AS 'Cod Pedido',
            COD_VEN || ' - ' || upper(substr(NOME_VEN,1,1)) || lower(substr(NOME_VEN,2)) AS Vendedor,
            MOT || ' - ' || upper(substr(NOME_MOT,1,1)) || lower(substr(NOME_MOT,2)) AS Motorista,
            CLI || ' - ' || upper(substr(FANTASIA,1,1)) || lower(substr(FANTASIA,2)) AS Cliente,
            upper(substr(CIDADE,1,1)) || lower(substr(CIDADE,2)) AS 'Cidade - Cli',
            ULT_COMPRA as 'Últ compra',
            NF_VENDA AS Nfe,
            VDCADDEV_DESCR AS Motivo,
            SUM(\"VALOR DEVOLUCAO\") AS Devolução,
            vdi_dev AS 'Devolução (Ped)',
            /*format('{{:t..2f}}', COALESCE(SUM(\"VALOR DEVOLUCAO\") / SUM(\"VALOR VENDA\") * 100, 0)) || '%' AS 'Taxa de retorno (Ped)',*/
            format('{{:t..2f}}', taxa_media_dev) || '%' AS 'Taxa de retorno (Ped)',
            \"Comodato cliente\" AS Comodato
        FROM geral_dev
        GROUP BY DATA_DEV, DATA_VENDA, Empresa, GRUPO_REV,CHAVE_VDI, CLI, COD_VEN, MOT, COD_PED, NOME_VEN, NOME_MOT, FANTASIA, CIDADE, ULT_COMPRA, NF_VENDA, VDCADDEV_DESCR,taxa_media_dev,vdi_dev, \"Comodato cliente\"
        ORDER BY DATA_VENDA DESC"
    ))


    dbDisconnect(conexao_duck_dev)
    dados_dev_detalhados
  })


  # Gráfico reativo ---------------------------------------------------------

  dev_diaria_graf <- reactive({
    req(input$data_dev_input)
    req(filtro_base_dev_geral())

    conexao_duck_dev <- dbConnect(duckdb::duckdb())
    dbWriteTable(conexao_duck_dev, "geral_dev", filtro_base_dev_geral(), overwrite = TRUE, row.names = FALSE)

    dev_diaria <- dbGetQuery(conexao_duck_dev, glue(
      "SELECT
          DATA_VENDA,
          SUM(\"VALOR DEVOLUCAO\") AS Devolucao
       FROM geral_dev
       GROUP BY DATA_VENDA
       ORDER BY DATA_VENDA DESC
       "
    ))

    dev_diaria$DATA_VENDA <- as.Date(dev_diaria$DATA_VENDA, format = "%Y%m%d")

    dbDisconnect(conexao_duck_dev)
    dev_diaria
  })


  output$tabela_devconsolidada_reativa <- renderReactable({
    req(input$data_dev_input)
    req(filtro_base_dev_geral())
    req(input$switch_consolidado_detal_dev == FALSE)

    filtro_dev_consol <- dev_consolidada_reativa() %>% select(-c("Empresa"))
    filtro_dev_consol <- dev_consolidada_reativa()[, c(
      "Data do pedido", "Grupo_rev", "Vendas", "Devolução",
      "Num de pedidos", "Pedidos devolvidos", "Taxa de retorno"
    )]
    filtro_dev_consol$`Data do pedido` <- as.Date(filtro_dev_consol$`Data do pedido`, format = "%Y%m%d")
    filtro_dev_consol <- filtro_dev_consol[order(filtro_dev_consol$Grupo_rev, decreasing = TRUE), ]

    reactable(
      filtro_dev_consol,
      defaultColDef = colDef(align = "center"),
      columns = list(
        `Data do pedido` = colDef(name = "Data do pedido", format = colFormat(date = TRUE, locales = "pt-BR")),
        Grupo_rev = colDef(name = "Revenda", aggregate = "count", format = list(aggregated = colFormat(prefix = "Total de revendas: "))),
        Vendas = colDef(aggregate = "sum", format = colFormat(prefix = "R$ ", digits = 2, separators = TRUE)),
        Devolução = colDef(aggregate = "sum", format = colFormat(prefix = "R$ ", digits = 2, separators = TRUE)),
        `Num de pedidos` = colDef(aggregate = "sum", format = colFormat(separators = TRUE)),
        `Pedidos devolvidos` = colDef(aggregate = "sum", format = colFormat(separators = TRUE)),
        `Taxa de retorno` = colDef(
          name = "Taxa de retorno (Fin)",
          aggregate = JS("function(values, rows) {
              let totalDevs = 0;
              let totalVendas = 0;
              rows.forEach(function(row) {
                totalDevs += row['Devolução'];
                totalVendas += row['Vendas'];
              });
              return (totalDevs / totalVendas) * 100;
            }"),
          # cell = function(value){ paste0(gsub("\\.",",",round(value,2)),"%") },
          format = colFormat(digits = 2, suffix = "%"),
          style = cor_agrup(column = "Taxa de retorno", threshold = 2, color_below = "#B5EFBA", color_above = "#EFB5B9")
        )
      ),
      groupBy = c("Data do pedido"),
      defaultSorted = "Data do pedido",
      defaultSortOrder = "desc",
      resizable = TRUE,
      pagination = FALSE,
      wrap = FALSE,
      height = "50vh",
      style = list(overflowX = "auto"), ,
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

  observeEvent(input$bt_ped_dev, {
    req(input$bt_ped_dev)
    req(dev_geral_itens())
    req(dev_detalhada_reativa())

    itens_dev <- dev_geral_itens()[dev_geral_itens()$CHAVE_VDI == dev_detalhada_reativa()$CHAVE_VDI[input$bt_ped_dev$row], ]
    itens_dev <- itens_dev[, c("URLImgCODR", "VDPRDPRD_DESCRI", "VALOR VENDA", "TPCOBRA")]

    showModal(
      modalDialog(
        class = "modal_dev_ped",
        htmltools::tags$div(
          style = "display: flex; justify-content: center;", # centraliza horizontalmente
          reactable(
            itens_dev,
            defaultColDef = colDef(align = "center"),
            defaultPageSize = 100,
            columns = list(
              URLImgCODR = colDef(
                name = "Produto",
                cell = function(value) {
                  if (!is.na(value) && nzchar(value)) {
                    htmltools::tags$img(src = value, height = "90px")
                  } else {
                    ""
                  }
                },
                html = TRUE
              ),
              VDPRDPRD_DESCRI = colDef(
                name = "Descrição",
                width = 90,
                cell = function(value) {
                  str_to_title(value)
                }
              ),
              `VALOR VENDA` = colDef(name = "Valor", width = 90, format = colFormat(digits = 2, separators = TRUE, prefix = "R$ ")),
              TPCOBRA = colDef(name = "Cobrança", width = 90)
            ),
            outlined = TRUE,
            wrap = TRUE,
            height = "70vh",
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
              backgroundColor = glue("{cores_reativo()[5]}"),
              headerStyle = list(
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
            # fullWidth = FALSE,          # largura automática
          )
        ),
        easyClose = TRUE,
        footer = NULL,
        size = "s"
      )
    )
  })

  output$tabela_devdetalhada_reativa <- renderReactable({
    req(input$data_dev_input)
    req(filtro_base_dev_geral())
    req(input$switch_consolidado_detal_dev == TRUE)

    filtro_dev_detal <- dev_detalhada_reativa() %>% select(-c("Empresa"))
    filtro_dev_detal$`Data de devolução` <- as.Date(ifelse(as.numeric(filtro_dev_detal$`Data de devolução`) == 0, NA, as.character(filtro_dev_detal$`Data de devolução`)), format = "%Y%m%d")
    filtro_dev_detal$`Data do pedido` <- as.Date(filtro_dev_detal$`Data do pedido`, format = "%Y%m%d")
    filtro_dev_detal$`Últ compra` <- as.Date(ifelse(as.numeric(filtro_dev_detal$`Últ compra`) == 0, NA, as.character(filtro_dev_detal$`Últ compra`)), format = "%Y%m%d")


    reactable(
      filtro_dev_detal,
      columns = list(
        `Data do pedido` = colDef(name = "Data do pedido", format = colFormat(date = TRUE, locales = "pt-BR")),
        `Data de devolução` = colDef(name = "Data de devolução", format = colFormat(date = TRUE, locales = "pt-BR"), footer = "Total"),
        `Últ compra` = colDef(format = colFormat(date = TRUE, locales = "pt-BR")),
        `Cod Pedido` = colDef(cell = button_extra("bt_ped_dev", class = "bt_extra_dev"), footer = function(values) paste0(length(unique(values)), " ped.")),
        CHAVE_VDI = colDef(show = FALSE),
        Devolução = colDef(format = colFormat(prefix = "R$ ", digits = 2, separators = TRUE), footer = function(values) paste0("R$ ", format(round(sum(values, na.rm = TRUE), 2), nsmall = 2, big.mark = ".", decimal.mark = ","))),
        `Devolução (Ped)` = colDef(footer = function(values) sum(values, na.rm = TRUE))
      ),
      defaultColDef = colDef(align = "center", footerStyle = list(fontWeight = "bold", background = "white", color = "black")),
      defaultSorted = "Data do pedido",
      defaultSortOrder = "desc",
      resizable = TRUE,
      pagination = TRUE,
      defaultPageSize = 50,
      pageSizeOptions = c(50, 100, 500),
      showPageSizeOptions = TRUE,
      # details = function(index){
      # itens_dev = dev_geral_itens()[dev_geral_itens()$CHAVE_VDI == filtro_dev_detal$CHAVE_VDI[index], ]
      # itens_dev = itens_dev[, c("URLImgCODR", "VDPRDPRD_DESCRI", "VALOR VENDA")]
      #
      # htmltools::tags$div(
      #   # style = "display: flex; justify-content: left;",  # centraliza horizontalmente
      #   reactable(
      #     itens_dev,
      #     columns = list(
      #       URLImgCODR = colDef(
      #         name = "Imagem",
      #         cell = function(value) {
      #           if (!is.na(value) && nzchar(value)) {
      #             htmltools::tags$img(src = value, height = "80px")
      #           } else {
      #             ""
      #           }
      #         },
      #         html = TRUE
      #       )
      #     ),
      #     outlined = TRUE,
      #     wrap = FALSE,
      #     # fullWidth = FALSE,          # largura automática
      #     style = list(display = "inline-block", minWidth = "500px")
      #   )
      # )
      # },
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

  output$grafico_dev_diario <- renderPlotly({
    # Gráfico ggplot


    p <- ggplot(dev_diaria_graf(), aes(x = DATA_VENDA, y = Devolucao)) +
      geom_line(size = 1, color = cores_reativo()[2]) +
      geom_point(size = 3, color = cores_reativo()[2], aes(text = paste0(
        "Data: ", format(DATA_VENDA, "%d/%m/%Y"),
        "<br>Devolução: R$ ", format(Devolucao, big.mark = ".", decimal.mark = ",")
      ))) +
      geom_text(aes(label = scales::dollar(Devolucao / 2, scale = 2, big.mark = ".", decimal.mark = ",", prefix = "R$ "), y = Devolucao + max(Devolucao, na.rm = TRUE) * 0.07), size = 2.5) +
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
        hoverlabel = list(bgcolor = "white", font = list(color = "black")),
        xaxis = list(
          tickangle = 45,
          nticks = 8, # mostra apenas 8 datas no eixo X
          tickformat = "%d/%m/%Y"
        )
      )
  })




  # UI ----------------------------------------------------------------------

  fluidRow(
    column(
      12,
      box(
        id = "box_det_dev_filtro",
        width = 12,
        collapsible = FALSE,
        status = "primary",
        title = fluidRow(
          column(1, pickerInput("dataped_dev_input", "Data do pedido", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
          column(1, pickerInput("revenda_dev_input", "Revenda", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
          column(1, pickerInput("codped_dev_input", "Cod Pedido", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
          column(1, pickerInput("codven_dev_input", "Cod Vendedores", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
          column(1, pickerInput("codmot_dev_input", "Cod Motoristas", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
          column(1, pickerInput("codcli_dev_input", "Cod Clientes", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
          column(1, pickerInput("codprod_dev_input", "Cod Produtos", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
          column(1, pickerInput("ultcomp_dev_input", "Últ compra", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
          column(1, pickerInput("devped_dev_input", "Devolução", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
          column(1, pickerInput("motivo_dev_input", "Motivo", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
          column(1, pickerInput("data_dev_input", "Mês", choices = unique(data_calend()$Mes), selected = "Mês Atual", multiple = TRUE, options = opcoes_filtro)),
          column(1,
            style = "display: flex; align-items: center;",
            column(1),
            column(9, actionButton("bt_limpadet_dev", label = NULL, icon = icon("eraser"), status = "primary", size = "lg", width = "100%") %>% tagAppendAttributes(title = "Limpar filtros")),
            column(1)
          )
        )
      )
    ),
    column(
      12,
      box(
        id = "card_dev_consol_detal",
        title = fluidRow(
          column(5, textOutput("tipo_dados_dev")),
          column(7, uiOutput("switch_consolidado_detal"))
          # column(6, uiOutput("card_retorno_dev"))
        ),
        collapsible = TRUE,
        status = "primary",
        width = 12,
        withSpinner(uiOutput("tabela_dev_selecionada"), type = 4)
      )
    ),
    column(
      12,
      box(
        id = "card_dev_diaria",
        title = "Devolução diária",
        collapsible = TRUE,
        status = "primary",
        width = 12,
        withSpinner(plotlyOutput("grafico_dev_diario", height = "40vh"), type = 4)
      )
    )
  )
}
