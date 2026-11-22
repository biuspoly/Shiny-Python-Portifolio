pag_frotas <- function() {
  # Carregar e tratar dados ----------------------------------------------------------

  source(glue("{diretorio}pages/Frotas/Dados/dados_frotas.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Frotas/Guia_ajuda.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Frotas/Dados/informar_motivo.R"), local = TRUE, encoding = "UTF-8")


  # Server ------------------------------------------------------------------
  frota_revenda <- reactiveVal(geral_frota)
  frota_renajud <- reactiveVal(geral_renajud)
  frota_renainf <- reactiveVal(geral_renainf)

  frota_principal <- reactive({
    if (length(revenda_query()) == 0) {
      frota_revenda()
    } else if (str_detect(revenda_query(), "ARRENDADORA")) {
      frota_revenda() %>% filter(str_detect(toupper(EMPRESA), revenda_query()))
    } else {
      frota_revenda() %>% filter(str_detect(toupper(UNIDADE), revenda_query()) | str_detect(toupper(EMPRESA), revenda_query()))
    }
  })

  # Textos reativos --------------------------------------------------------

  ### Ultima atualizacao --------------------------------------------------------
  output$ult_atualizacao_id_geral_frota <- renderText({
    glue("Atualizado em: {format(as.Date(as.character(max(geral_frota$DTA_EXEC)), '%Y%m%d'), '%d/%m/%Y')}")
  })

  ### Aviso --------------------------------------------------------
  output$aviso_id_geral_frota <- renderText({
    req(filtro_base_geral())
    if (any(filtro_base_geral()$UF_Emp %in% c("NI")) && nrow(filtro_base_geral()) > 0) {
      "Detran PE e RJ se encontram com instabilidades."
    } else {
      ""
    }
  })

  # Botoes e filtros --------------------------------------------------------

  ### Botao  --------------------------------------------------------
  observeEvent(input$bt_limpafrota, {
    updatePickerInput(session, inputId = "propfrotas_input", selected = character(0))
    updatePickerInput(session, inputId = "unidfrotas_input", selected = character(0))
    updatePickerInput(session, inputId = "uffrotas_input", selected = character(0))
    updatePickerInput(session, inputId = "placafrotas_input", selected = character(0))
    updatePickerInput(session, inputId = "tipofrotas_input", selected = character(0))
    updatePickerInput(session, inputId = "modelfrotas_input", selected = character(0))
    updatePickerInput(session, inputId = "carrocfrotas_input", selected = character(0))
    updatePickerInput(session, inputId = "restadmfrotas_input", selected = character(0))
    updatePickerInput(session, inputId = "gravamefrotas_input", selected = character(0))
    updatePickerInput(session, inputId = "gravamepenfrotas_input", selected = character(0))
    updatePickerInput(session, inputId = "renajudfrotas_input", selected = character(0))
    updatePickerInput(session, inputId = "detranfrotas_input", selected = character(0))
    updatePickerInput(session, inputId = "transffrotas_input", selected = character(0))
  })

  tabela_frota_selecionada <- reactive({
    base_geral <- switch(input$bt_check_frota,
      "Geral" = tabela_geral_frota(),
      "Rest Adm" = tabela_restadm_frota(),
      "Renajud" = {
        if (isTRUE(input$switch_renajud_renainf_frota)) {
          tabela_renajuddetal_frota()
        } else {
          tabela_renajudconsol_frota()
        }
      },
      "Detran" = {
        if (isTRUE(input$switch_renajud_renainf_frota)) {
          tabela_renainfdetal_frota()
        } else {
          tabela_detran_frota()
        }
      },
      "Custos" = tabela_custos_frota(),
      tabela_geral_frota() # default
    )

    base_geral
  })

  output$switch_renajud_renainf <- renderUI({
    if (!is.null(input$bt_check_frota) && input$bt_check_frota == "Renajud") {
      # Mostra o switch
      prettySwitch(
        inputId = "switch_renajud_renainf_frota",
        label = NULL,
        status = "success",
        fill = TRUE,
        bigger = FALSE
      )
    } else if (!is.null(input$bt_check_frota) && input$bt_check_frota == "Detran") {
      prettySwitch(
        inputId = "switch_renajud_renainf_frota",
        label = NULL,
        status = "success",
        fill = TRUE,
        bigger = FALSE
      )
    } else {
      # Oculta o switch
      div(
        style = "visibility: hidden;",
        prettySwitch(
          inputId = "switch_renajud_renainf_frota",
          label = NULL,
          status = "success",
          fill = TRUE,
          bigger = FALSE
        )
      )
    }
  })


  ### Transferencia -----------------------------------------------------------


  observeEvent(input$bt_rev_transf, {
    if (input$bt_rev_transf$column == "Transferência manual") {
      showModal(
        modalDialog(
          title = "Informar nova unidade:", size = "l",
          easyClose = TRUE,
          footer = NULL,
          fluidRow(
            column(
              5,
              textInput("unid_ini_frota_empresa_input", label = "Unidade atual", value = tabela_frota_selecionada()$Unidade[input$bt_rev_transf$row]) %>%
                tagAppendAttributes(style = "pointer-events: none;"),
              textInput("transf_frota_placa_input", label = "Placa", value = tabela_frota_selecionada()$Placa[input$bt_rev_transf$row]) %>%
                tagAppendAttributes(style = "pointer-events: none;"),
              pickerInput("unid_fim_frota_empresa_input",
                label = "Nova unidade",
                choices = sort(c(
                  "Natal",
                  "Natal Estoque",
                  "Fortaleza",
                  "Teresina",
                  "São Luís",
                  "Vendido"
                )),
                multiple = FALSE,
                options = opcoes_filtro
              ),
              fileInput("anexo_unid_frota", label = "Selecionar arquivo", buttonLabel = "Procurar...", placeholder = "", accept = c(".pdf", ".jpg", ".jpeg", ".png")),
              fluidRow(
                column(12,
                  align = "center",
                  actionButton("bt_insere_unid_frota", label = "Enviar", status = "primary", size = "sm")
                )
              )
            ),
            column(
              7,
              tags$img(src = "acomp_log_www/img/transporte.svg", width = "100%", height = "100%")
            )
          )
        )
      )
    }
  })

  observeEvent(input$bt_insere_unid_frota, {
    if (length(input$anexo_unid_frota) > 0) {
      informacao_anexo <- anexo_transferencia(
        input$unid_ini_frota_empresa_input,
        input$transf_frota_placa_input,
        input$anexo_unid_frota$datapath,
        input$unid_fim_frota_empresa_input,
        input$anexo_unid_frota$name
      )
    } else {
      informacao_anexo <- ""
    }

    info_transferencia(
      input$unid_ini_frota_empresa_input,
      input$transf_frota_placa_input,
      informacao_anexo,
      session$userData$usuario,
      input$unid_fim_frota_empresa_input
    )

    removeModal(session = session)

    shinyalert(
      title = "Unidade alterada",
      text = "",
      size = "xs",
      closeOnEsc = TRUE,
      closeOnClickOutside = TRUE,
      type = "success",
      showConfirmButton = FALSE,
      confirmButtonText = "OK",
      confirmButtonCol = cores_reativo()[2],
      animation = TRUE
    )
  })


  ### Download (arquivo de transferencia) -------------------------------------

  observeEvent(input$bt_rev_anexo, {
    runjs("document.getElementById('bt_download_transf_anexo').click();")
  })

  output$bt_download_transf_anexo <- downloadHandler(
    filename = function() {
      basename(tabela_frota_selecionada()$ANEXO[input$bt_rev_anexo$row])
    },
    content = function(file) {
      file.copy(tabela_frota_selecionada()$ANEXO[input$bt_rev_anexo$row], file)
    }
  )

  ### Download (Geral)  --------------------------------------------------------

  output$bt_download_id_geral_frota <- downloadHandler(
    filename = function() {
      paste("frota-", Sys.Date(), ".xlsx", sep = "")
    },
    content = function(con) {
      colunas_remover <- c("Custo API", "CNPJ_EMP", "Anexo", "ANEXO", "Informar motivo", "ULT_ROM", "TRANSFERENCIA", "Anexo_transf")

      tabela_frota_selecionada() %>%
        dplyr::ungroup() %>% # <- garante que não está mais agrupado
        dplyr::select(-dplyr::any_of(colunas_remover)) %>%
        writexl::write_xlsx(con)
    }
  )

  ### Download (Formato banco)  --------------------------------------------------------

  output$bt_download_frota_banco <- downloadHandler(
    filename = function() {
      paste("frota-formatado", Sys.time(), ".xlsx", sep = "")
    },
    content = function(con) {
      duck_tabela_banco <- dbConnect(duckdb())

      dbWriteTable(duck_tabela_banco, "geral", tabela_geral_frota(), overwrite = TRUE)
      dbWriteTable(duck_tabela_banco, "rest_adm", tabela_restadm_frota(), overwrite = TRUE)
      dbWriteTable(duck_tabela_banco, "renajud_consol", tabela_renajudconsol_frota(), overwrite = TRUE)
      dbWriteTable(duck_tabela_banco, "multas", tabela_renainfdetal_frota(), overwrite = TRUE)
      dbWriteTable(duck_tabela_banco, "detran", tabela_detran_frota(), overwrite = TRUE)

      tabelao_banco <- dbGetQuery(duck_tabela_banco, "
    SELECT
      g.Empresa,
      g.Unidade,
      g.UF,
      g.Placa,
      g.Tipo,
      g.Modelo,
      g.Ano,
      g.Fabricação,
      g.Renavam,
      g.Chassi,
      r.\"Rest Adm\",
      r.Gravame,
      r.\"Gravame Pendente\",
      rd.RENAJUD AS Renajud,
      rd.\"Nº processos\",
      d.Débito,
      d.\"Ipva Atual\",
      d.\"Ipva Ant\",
      d.Licenciamento,
      d.Multa,
      d.\"Outros débitos\",
      d.\"Tabela Fipe\"
    FROM geral AS g
    LEFT JOIN rest_adm AS r ON g.Placa = r.Placa
    LEFT JOIN renajud_consol AS rd ON g.Placa = rd.Placa
    /*LEFT JOIN multas AS md ON g.Placa = md.Placa*/
    LEFT JOIN detran AS d ON g.Placa = d.Placa
  ") %>%
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


  output$input_filtro_unidade <- renderUI({
    if (is.null(revenda_query()) | length(revenda_query()) == 0) {
      pickerInput("unidfrotas_input", "Unidade", choices = sort(unique(frota_principal()$UNIDADE[!is.na(frota_principal()$UNIDADE) & frota_principal()$UNIDADE != ""])), multiple = TRUE, options = opcoes_filtro)
    } else if (str_detect(revenda_query(), "LOCADORA") | str_detect(revenda_query(), "ARRENDADORA") | str_detect(revenda_query(), "TRANSPORTADORA")) {
      pickerInput("unidfrotas_input", "Unidade", choices = sort(unique(frota_principal()$UNIDADE[!is.na(frota_principal()$UNIDADE) & frota_principal()$UNIDADE != ""])), multiple = TRUE, options = opcoes_filtro)
    } else {
      div( # style = "display: none;",
        pickerInput("unidfrotas_input", "Unidade", choices = sort(unique(frota_principal()$UNIDADE[!is.na(frota_principal()$UNIDADE) & frota_principal()$UNIDADE != ""])), multiple = TRUE, options = opcoes_filtro)
      )
    }
  })

  filtro_base_geral <- reactive({
    if ((is.null(input$propfrotas_input) || length(input$propfrotas_input) == 0) &&
      (is.null(input$unidfrotas_input) || length(input$unidfrotas_input) == 0) &&
      (is.null(input$uffrotas_input) || length(input$uffrotas_input) == 0) &&
      (is.null(input$placafrotas_input) || length(input$placafrotas_input) == 0) &&
      (is.null(input$tipofrotas_input) || length(input$tipofrotas_input) == 0) &&
      (is.null(input$modelfrotas_input) || length(input$modelfrotas_input) == 0) &&
      (is.null(input$carrocfrotas_input) || length(input$carrocfrotas_input) == 0) &&
      (is.null(input$restadmfrotas_input) || length(input$restadmfrotas_input) == 0) &&
      (is.null(input$gravamefrotas_input) || length(input$gravamefrotas_input) == 0) &&
      (is.null(input$gravamepenfrotas_input) || length(input$gravamepenfrotas_input) == 0) &&
      (is.null(input$renajudfrotas_input) || length(input$renajudfrotas_input) == 0) &&
      (is.null(input$detranfrotas_input) || length(input$detranfrotas_input) == 0) &&
      (is.null(input$transffrotas_input) || length(input$transffrotas_input) == 0)) {
      dados <- frota_principal()
    } else {
      dados <- frota_principal() %>%
        filter(
          if (is.null(input$propfrotas_input) || length(input$propfrotas_input) == 0) TRUE else EMPRESA %in% input$propfrotas_input,
          if (is.null(input$uffrotas_input) || length(input$uffrotas_input) == 0) TRUE else UF_Emp %in% input$uffrotas_input,
          if (is.null(input$unidfrotas_input) || length(input$unidfrotas_input) == 0) TRUE else UNIDADE %in% input$unidfrotas_input,
          if (is.null(input$placafrotas_input) || length(input$placafrotas_input) == 0) TRUE else PLACA %in% input$placafrotas_input,
          if (is.null(input$tipofrotas_input) || length(input$tipofrotas_input) == 0) TRUE else TIPO %in% input$tipofrotas_input,
          if (is.null(input$modelfrotas_input) || length(input$modelfrotas_input) == 0) TRUE else MODELO %in% input$modelfrotas_input,
          if (is.null(input$carrocfrotas_input) || length(input$carrocfrotas_input) == 0) TRUE else CARROCERIA %in% input$carrocfrotas_input,
          if (is.null(input$restadmfrotas_input) || length(input$restadmfrotas_input) == 0) TRUE else RESTRICAO_ADM %in% input$restadmfrotas_input,
          if (is.null(input$gravamefrotas_input) || length(input$gravamefrotas_input) == 0) TRUE else GRAVAME %in% input$gravamefrotas_input,
          if (is.null(input$gravamepenfrotas_input) || length(input$gravamepenfrotas_input) == 0) TRUE else GRAVAME_PENDENTE %in% input$gravamepenfrotas_input,
          if (is.null(input$renajudfrotas_input) || length(input$renajudfrotas_input) == 0) TRUE else RENAJUD %in% input$renajudfrotas_input,
          if (is.null(input$detranfrotas_input) || length(input$detranfrotas_input) == 0) TRUE else DEBITO_DETRAN %in% input$detranfrotas_input,
          if (is.null(input$transffrotas_input) || length(input$transffrotas_input) == 0) TRUE else TRANSFERENCIA %in% input$transffrotas_input
        )
    }

    dados
  })



  observeEvent(filtro_base_geral(), {
    # Atualiza apenas se não houver seleção
    if (is.null(input$uffrotas_input) || length(input$uffrotas_input) == 0) {
      updatePickerInput(session, "uffrotas_input", choices = sort(unique(filtro_base_geral()$UF_Emp)))
    }
    if (is.null(input$propfrotas_input) || length(input$propfrotas_input) == 0) {
      updatePickerInput(session, "propfrotas_input", choices = sort(unique(filtro_base_geral()$EMPRESA)))
    }
    if (is.null(input$unidfrotas_input) || length(input$unidfrotas_input) == 0) {
      updatePickerInput(session, "unidfrotas_input", choices = sort(unique(filtro_base_geral()$UNIDADE)))
    }
    if (is.null(input$placafrotas_input) || length(input$placafrotas_input) == 0) {
      updatePickerInput(session, "placafrotas_input", choices = sort(unique(filtro_base_geral()$PLACA)))
    }
    if (is.null(input$tipofrotas_input) || length(input$tipofrotas_input) == 0) {
      updatePickerInput(session, "tipofrotas_input", choices = sort(unique(filtro_base_geral()$TIPO)))
    }
    if (is.null(input$modelfrotas_input) || length(input$modelfrotas_input) == 0) {
      updatePickerInput(session, "modelfrotas_input", choices = sort(unique(filtro_base_geral()$MODELO)))
    }
    if (is.null(input$carrocfrotas_input) || length(input$carrocfrotas_input) == 0) {
      updatePickerInput(session, "carrocfrotas_input", choices = sort(unique(filtro_base_geral()$CARROCERIA)))
    }
    if (is.null(input$restadmfrotas_input) || length(input$restadmfrotas_input) == 0) {
      updatePickerInput(session, "restadmfrotas_input", choices = sort(unique(filtro_base_geral()$RESTRICAO_ADM)))
    }
    if (is.null(input$gravamefrotas_input) || length(input$gravamefrotas_input) == 0) {
      updatePickerInput(session, "gravamefrotas_input", choices = sort(unique(filtro_base_geral()$GRAVAME)))
    }
    if (is.null(input$gravamepenfrotas_input) || length(input$gravamepenfrotas_input) == 0) {
      updatePickerInput(session, "gravamepenfrotas_input", choices = sort(unique(filtro_base_geral()$GRAVAME_PENDENTE)))
    }
    if (is.null(input$renajudfrotas_input) || length(input$renajudfrotas_input) == 0) {
      updatePickerInput(session, "renajudfrotas_input", choices = sort(unique(filtro_base_geral()$RENAJUD)))
    }
    if (is.null(input$detranfrotas_input) || length(input$detranfrotas_input) == 0) {
      updatePickerInput(session, "detranfrotas_input", choices = sort(unique(filtro_base_geral()$DEBITO_DETRAN)))
    }
    if (is.null(input$transffrotas_input) || length(input$transffrotas_input) == 0) {
      updatePickerInput(session, "transffrotas_input", choices = sort(unique(filtro_base_geral()$TRANSFERENCIA)))
    }
    # if (!is.null(getReactableState("tabela_frotaconsolid_reativa","selected"))){
    #   data_filtro(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa","selected")])
    # }
    # else{
    #   data_filtro(NULL)
    # }
    # print(which(tabela_consolidada()$Data == data_filtro()))
  })

  # observeEvent(input$propfrotas_input,{
  #   req(input$propfrotas_input)
  #   print(nrow(frota_principal() %>% filter(EMPRESA %in% input$propfrotas_input)))
  # })

  # Registro mais recente por PLACA+CNPJ_EMP dentro dos ultimos 7 dias do max DTA_EXEC
  filtro_base_atual <- reactive({
    dados <- filtro_base_geral()
    if (nrow(dados) == 0) return(dados)
    max_dta <- max(dados$DTA_EXEC)
    max_date <- as.Date(as.character(max_dta), "%Y%m%d")
    dados %>%
      filter(as.Date(as.character(DTA_EXEC), "%Y%m%d") >= max_date - 7) %>%
      group_by(PLACA, CNPJ_EMP) %>%
      filter(DTA_EXEC == max(DTA_EXEC)) %>%
      ungroup()
  })


  ### Ajuda --------------------------------------------------------

  observeEvent(input$bt_guia_id_geral_frota, {
    funcao_guia_frota("Geral")$init()$start()
  })





  # Cards -------------------------------------------------------------------

  cavalo_reativo <- reactive({
    if (is.null(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) ||
      length(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) == 0) {
      dados <- filtro_base_atual() %>%
        filter(str_detect(TIPO, "TRATOR|REBOQ")) %>%
        summarise(
          DTA_EXEC = max(DTA_EXEC),
          veiculos = sum(str_detect(TIPO, "TRATOR|REBOQ"), na.rm = TRUE),
          rest_adm = sum(RESTRICAO_ADM == "Sim", na.rm = TRUE),
          renajud = sum(RENAJUD == "Sim", na.rm = TRUE),
          debito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) / 1000
        ) %>%
        mutate(debito = scales::dollar(debito, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01, suffix = " Mil"))
    } else {
      dados <- filtro_base_geral() %>%
        filter(DTA_EXEC %in% tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")], str_detect(TIPO, "TRATOR|REBOQ")) %>%
        group_by(DTA_EXEC) %>%
        summarise(
          veiculos = sum(str_detect(TIPO, "TRATOR|REBOQ"), na.rm = TRUE),
          rest_adm = sum(RESTRICAO_ADM == "Sim", na.rm = TRUE),
          renajud = sum(RENAJUD == "Sim", na.rm = TRUE),
          debito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) / 1000
        ) %>%
        mutate(debito = scales::dollar(debito, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01, suffix = " Mil"))
    }
    if (nrow(dados) == 0) {
      dados <- data.frame(
        veiculos = 0,
        rest_adm = 0,
        renajud  = 0,
        debito   = "R$ 0,00"
      )
    }


    dados
  })

  output$cavalo_veic_reativo <- renderText({
    cavalo_reativo()$veiculos
  })
  output$cavalo_radm_reativo <- renderText({
    cavalo_reativo()$rest_adm
  })
  output$cavalo_rjud_reativo <- renderText({
    cavalo_reativo()$renajud
  })
  output$cavalo_debi_reativo <- renderText({
    cavalo_reativo()$debito
  })

  caminhao_reativo <- reactive({
    if (is.null(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) ||
      length(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) == 0) {
      dados <- filtro_base_atual() %>%
        filter(str_detect(TIPO, "CAMINH") & !str_detect(TIPO, "TRATOR")) %>%
        summarise(
          DTA_EXEC = max(DTA_EXEC),
          veiculos = sum(str_detect(TIPO, "CAMINH") & !str_detect(TIPO, "TRATOR"), na.rm = TRUE),
          rest_adm = sum(RESTRICAO_ADM == "Sim", na.rm = TRUE),
          renajud = sum(RENAJUD == "Sim", na.rm = TRUE),
          debito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) / 1000
        ) %>%
        mutate(debito = scales::dollar(debito, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01, suffix = " Mil"))
    } else {
      dados <- filtro_base_geral() %>%
        filter(DTA_EXEC %in% tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")], str_detect(TIPO, "CAMINH") & !str_detect(TIPO, "TRATOR")) %>%
        group_by(DTA_EXEC) %>%
        summarise(
          veiculos = sum(str_detect(TIPO, "CAMINH") & !str_detect(TIPO, "TRATOR"), na.rm = TRUE),
          rest_adm = sum(RESTRICAO_ADM == "Sim", na.rm = TRUE),
          renajud = sum(RENAJUD == "Sim", na.rm = TRUE),
          debito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) / 1000
        ) %>%
        mutate(debito = scales::dollar(debito, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01, suffix = " Mil"))
    }
    if (nrow(dados) == 0) {
      dados <- data.frame(
        veiculos = 0,
        rest_adm = 0,
        renajud  = 0,
        debito   = "R$ 0,00"
      )
    }


    dados
  })


  output$caminhao_veic_reativo <- renderText({
    caminhao_reativo()$veiculos
  })
  output$caminhao_radm_reativo <- renderText({
    caminhao_reativo()$rest_adm
  })
  output$caminhao_rjud_reativo <- renderText({
    caminhao_reativo()$renajud
  })
  output$caminhao_debi_reativo <- renderText({
    caminhao_reativo()$debito
  })


  carro_reativo <- reactive({
    if (is.null(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) ||
      length(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) == 0) {
      dados <- filtro_base_atual() %>%
        filter(TIPO %in% c("AUTOMOVEL", "CAMIONETA", "UTILITARIO")) %>%
        summarise(
          DTA_EXEC = max(DTA_EXEC),
          veiculos = sum(TIPO %in% c("AUTOMOVEL", "CAMIONETA", "UTILITARIO"), na.rm = TRUE),
          rest_adm = sum(RESTRICAO_ADM == "Sim", na.rm = TRUE),
          renajud = sum(RENAJUD == "Sim", na.rm = TRUE),
          debito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) / 1000
        ) %>%
        mutate(debito = scales::dollar(debito, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01, suffix = " Mil"))
    } else {
      dados <- filtro_base_geral() %>%
        filter(DTA_EXEC %in% tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")], TIPO %in% c("AUTOMOVEL", "CAMIONETA", "UTILITARIO")) %>%
        group_by(DTA_EXEC) %>%
        summarise(
          veiculos = sum(TIPO %in% c("AUTOMOVEL", "CAMIONETA", "UTILITARIO"), na.rm = TRUE),
          rest_adm = sum(RESTRICAO_ADM == "Sim", na.rm = TRUE),
          renajud = sum(RENAJUD == "Sim", na.rm = TRUE),
          debito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) / 1000
        ) %>%
        mutate(debito = scales::dollar(debito, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01, suffix = " Mil"))
    }
    if (nrow(dados) == 0) {
      dados <- data.frame(
        veiculos = 0,
        rest_adm = 0,
        renajud  = 0,
        debito   = "R$ 0,00"
      )
    }

    dados
  })

  output$carro_veic_reativo <- renderText({
    carro_reativo()$veiculos
  })
  output$carro_radm_reativo <- renderText({
    carro_reativo()$rest_adm
  })
  output$carro_rjud_reativo <- renderText({
    carro_reativo()$renajud
  })
  output$carro_debi_reativo <- renderText({
    carro_reativo()$debito
  })

  moto_reativo <- reactive({
    if (is.null(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) ||
      length(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) == 0) {
      dados <- filtro_base_atual() %>%
        filter(str_detect(TIPO, "MOTO")) %>%
        summarise(
          DTA_EXEC = max(DTA_EXEC),
          veiculos = sum(str_detect(TIPO, "MOTO"), na.rm = TRUE),
          rest_adm = sum(RESTRICAO_ADM == "Sim", na.rm = TRUE),
          renajud = sum(RENAJUD == "Sim", na.rm = TRUE),
          debito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) / 1000
        ) %>%
        mutate(debito = scales::dollar(debito, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01, suffix = " Mil"))
    } else {
      dados <- filtro_base_geral() %>%
        filter(DTA_EXEC %in% tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")], str_detect(TIPO, "MOTO")) %>%
        group_by(DTA_EXEC) %>%
        summarise(
          veiculos = sum(str_detect(TIPO, "MOTO"), na.rm = TRUE),
          rest_adm = sum(RESTRICAO_ADM == "Sim", na.rm = TRUE),
          renajud = sum(RENAJUD == "Sim", na.rm = TRUE),
          debito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) / 1000
        ) %>%
        mutate(debito = scales::dollar(debito, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01, suffix = " Mil"))
    }
    if (nrow(dados) == 0) {
      dados <- data.frame(
        veiculos = 0,
        rest_adm = 0,
        renajud  = 0,
        debito   = "R$ 0,00"
      )
    }

    dados
  })

  output$moto_veic_reativo <- renderText({
    moto_reativo()$veiculos
  })
  output$moto_radm_reativo <- renderText({
    moto_reativo()$rest_adm
  })
  output$moto_rjud_reativo <- renderText({
    moto_reativo()$renajud
  })
  output$moto_debi_reativo <- renderText({
    moto_reativo()$debito
  })

  # Tabela consolidada ------------------------------------------------------

  # Tabela consolidada com renajud ------------------------------------------

  tabela_consolidada <- reactive({
    tabela <- filtro_base_geral()

    geral_consolid <- unite(tabela, col = "CHAVE", PLACA, DTA_EXEC, sep = "", remove = FALSE)
    geral_renajud_consolid <- unite(frota_renajud(), col = "CHAVE", PLACA, DTA_EXEC, sep = "")


    geral_renajud_detal <- left_join(
      geral_consolid,
      geral_renajud_consolid,
      by = "CHAVE",
      relationship = "many-to-many"
    )


    tabela_consol <- distinct(geral_renajud_detal, PLACA, DTA_EXEC, .keep_all = TRUE)


    frota_consolid <- tabela_consol %>%
      group_by(DTA_EXEC) %>%
      summarise(
        `Custo API` = round(sum(as.numeric(CUSTO_API), na.rm = TRUE), 2), Veículos = sum(!is.na(PLACA)),
        Carro = sum(TIPO %in% c("AUTOMOVEL", "CAMIONETA", "UTILITARIO"), na.rm = TRUE), Moto = sum(str_detect(TIPO, "MOTO"), na.rm = TRUE),
        Cavalo = sum(str_detect(TIPO, "TRATOR|REBOQ"), na.rm = TRUE), Caminhao = sum(str_detect(TIPO, "CAMINH") & !str_detect(TIPO, "TRATOR"), na.rm = TRUE),
        Débito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE), Renajud = sum(RENAJUD == "Sim", na.rm = TRUE), `Tabela Fipe` = sum(as.numeric(TABELA_FIPE), na.rm = TRUE)
      ) %>%
      arrange(desc(DTA_EXEC)) %>%
      mutate(
        `Taxa_Custo API` = round((`Custo API` - lead(`Custo API`)) / lead(`Custo API`), 2),
        `Taxa_Veículos` = round((Veículos - lead(Veículos)) / lead(Veículos), 2),
        `Taxa_Carro` = round((Carro - lead(Carro)) / lead(Carro), 2),
        `Taxa_Moto` = round((Moto - lead(Moto)) / lead(Moto), 2),
        `Taxa_Cavalo` = round((Cavalo - lead(Cavalo)) / lead(Cavalo), 2),
        `Taxa_Caminhao` = round((Caminhao - lead(Caminhao)) / lead(Caminhao), 2),
        `Taxa_Débito` = round((Débito - lead(Débito)) / lead(Débito), 2),
        `Taxa_Renajud` = round((Renajud - lead(Renajud)) / lead(Renajud), 2),
        `Taxa_Tabela Fipe` = round((`Tabela Fipe` - lead(`Tabela Fipe`)) / lead(`Tabela Fipe`), 2)
      ) %>%
      mutate(across(
        starts_with("Taxa"),
        ~ case_when(
          .x > 0 ~ "caret-up",
          .x < 0 ~ "caret-down",
          TRUE ~ "minus"
        )
      )) %>%
      mutate(across(starts_with("Taxa"),
        ~ case_when(
          .x == "caret-up" ~ "#64b178",
          .x == "caret-down" ~ "#f26e5f",
          .x == "minus" ~ "#d7962e"
        ),
        .names = "cor_{.col}"
      )) %>%
      mutate(
        Débito = scales::dollar(Débito, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
        `Custo API` = scales::dollar(`Custo API`, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
        `Tabela Fipe` = scales::dollar(`Tabela Fipe`, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01)
      ) %>%
      # DTA_EXEC = format(DTA_EXEC, "%d/%m/%Y")) %>%
      rename(Data = DTA_EXEC)

    frota_consolid
  })


  output$tabela_frotaconsolid_reativa <- renderReactable({
    req(tabela_consolidada())

    reactable(
      tabela_consolidada() %>% mutate(Data = format(as.Date(as.character(Data), "%Y%m%d"), "%d/%m/%Y")),
      pagination = FALSE,
      compact = TRUE,
      highlight = TRUE,
      bordered = TRUE,
      defaultColDef = colDef(align = "center"),
      wrap = FALSE,
      height = "370px",
      selection = "single",
      onClick = "select",
      columns = list(
        .selection = colDef(show = FALSE),
        `Taxa_Custo API` = colDef(show = FALSE),
        `cor_Taxa_Custo API` = colDef(show = FALSE),
        Taxa_Veículos = colDef(show = FALSE),
        cor_Taxa_Veículos = colDef(show = FALSE),
        Taxa_Carro = colDef(show = FALSE),
        cor_Taxa_Carro = colDef(show = FALSE),
        Taxa_Moto = colDef(show = FALSE),
        cor_Taxa_Moto = colDef(show = FALSE),
        Taxa_Caminhao = colDef(show = FALSE),
        cor_Taxa_Caminhao = colDef(show = FALSE),
        Taxa_Cavalo = colDef(show = FALSE),
        cor_Taxa_Cavalo = colDef(show = FALSE),
        Taxa_Débito = colDef(show = FALSE),
        cor_Taxa_Débito = colDef(show = FALSE),
        Taxa_Renajud = colDef(show = FALSE),
        cor_Taxa_Renajud = colDef(show = FALSE),
        `Taxa_Tabela Fipe` = colDef(show = FALSE),
        `cor_Taxa_Tabela Fipe` = colDef(show = FALSE),
        `Custo API` = colDef(show = length(revenda_query()) == 0, cell = icon_sets(tabela_consolidada(), icon_ref = "Taxa_Custo API", icon_color_ref = "cor_Taxa_Custo API", icon_position = "left")),
        Veículos = colDef(cell = icon_sets(tabela_consolidada(), icon_ref = "Taxa_Veículos", icon_color_ref = "cor_Taxa_Veículos", icon_position = "left")),
        Carro = colDef(cell = icon_sets(tabela_consolidada(), icon_ref = "Taxa_Carro", icon_color_ref = "cor_Taxa_Carro", icon_position = "left")),
        Moto = colDef(cell = icon_sets(tabela_consolidada(), icon_ref = "Taxa_Moto", icon_color_ref = "cor_Taxa_Moto", icon_position = "left")),
        Caminhao = colDef(cell = icon_sets(tabela_consolidada(), icon_ref = "Taxa_Caminhao", icon_color_ref = "cor_Taxa_Caminhao", icon_position = "left")),
        Cavalo = colDef(cell = icon_sets(tabela_consolidada(), icon_ref = "Taxa_Cavalo", icon_color_ref = "cor_Taxa_Cavalo", icon_position = "left")),
        Débito = colDef(cell = icon_sets(tabela_consolidada(), icon_ref = "Taxa_Débito", icon_color_ref = "cor_Taxa_Débito", icon_position = "left")),
        Renajud = colDef(cell = icon_sets(tabela_consolidada(), icon_ref = "Taxa_Renajud", icon_color_ref = "cor_Taxa_Renajud", icon_position = "left")),
        `Tabela Fipe` = colDef(cell = icon_sets(tabela_consolidada(), icon_ref = "Taxa_Tabela Fipe", icon_color_ref = "cor_Taxa_Tabela Fipe", icon_position = "left"))
      ),
      style = list(overflowX = "hidden"),
      theme = reactableTheme(
        backgroundColor = "transparent", headerStyle = list(
          backgroundColor = glue("{cores_reativo()[2]}"),
          color = "white",
          fontWeight = "bold",
          textAlign = "center"
        ),
        rowSelectedStyle = list(backgroundColor = "darkgray", boxShadow = glue("inset 2px 0 0 0 {cores_reativo()[1]}"))
      )
    )
  })

  # Tabelas principais --------------------------------------------------------


  # Tabela Geral ------------------------------------------------------------

  tabela_geral_frota <- reactive({
    if (is.null(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) ||
      length(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) == 0) {
      tabela_geral <- filtro_base_atual() %>%
        select(
          EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, ANO_FAB, RENAVAM, CHASSI, CARROCERIA, ULT_ROM, TRANSFERENCIA, Anexo_transf, ANEXO,
          RESTRICAO_ADM, GRAVAME, GRAVAME_PENDENTE, RENAJUD
        ) %>%
        arrange(EMPRESA) %>%
        rename(
          "Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
          "Modelo" = MODELO, "Ano" = ANO, "Fabricação" = ANO_FAB, "Renavam" = RENAVAM,
          "Chassi" = CHASSI, "Carroceria" = CARROCERIA, `Rest Adm` = RESTRICAO_ADM,
          "Gravame" = GRAVAME, `Gravame Pendente` = GRAVAME_PENDENTE, "Renajud" = RENAJUD
        ) %>%
        mutate(across(where(is.character) & !c(Placa, UF, TRANSFERENCIA), str_to_title))
    } else {
      # tabela_geral_filtrada = tabela_consolidada() %>% filter(Data)
      tabela_geral <- filtro_base_geral() %>%
        filter(DTA_EXEC %in% tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) %>%
        select(
          EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, ANO_FAB, RENAVAM, CHASSI, CARROCERIA, ULT_ROM, TRANSFERENCIA, Anexo_transf, ANEXO,
          RESTRICAO_ADM, GRAVAME, GRAVAME_PENDENTE, RENAJUD
        ) %>%
        arrange(EMPRESA) %>%
        rename(
          "Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
          "Modelo" = MODELO, "Ano" = ANO, "Fabricação" = ANO_FAB, "Renavam" = RENAVAM,
          "Chassi" = CHASSI, "Carroceria" = CARROCERIA, `Rest Adm` = RESTRICAO_ADM,
          "Gravame" = GRAVAME, `Gravame Pendente` = GRAVAME_PENDENTE, "Renajud" = RENAJUD
        ) %>%
        mutate(across(where(is.character) & !c(Placa, UF, TRANSFERENCIA), str_to_title))
    }
  })

  # Tabela Restricao Adm ------------------------------------------------------------

  tabela_restadm_frota <- reactive({
    if (is.null(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) ||
      length(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) == 0) {
      tabela_rest_adm_frota <- filtro_base_atual() %>%
        select(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAVAM, RESTRICAO_ADM, GRAVAME, GRAVAME_PENDENTE, PROPRIETARIO, ULT_ROM, TRANSFERENCIA) %>%
        arrange(EMPRESA) %>%
        rename(
          "Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
          "Modelo" = MODELO, "Ano" = ANO, "Renavam" = RENAVAM, `Rest Adm` = RESTRICAO_ADM,
          "Gravame" = GRAVAME, `Gravame Pendente` = GRAVAME_PENDENTE, "Proprietário" = PROPRIETARIO
        ) %>%
        mutate(across(where(is.character) & !c(Placa, UF, TRANSFERENCIA), str_to_title))
    } else {
      # tabela_geral_filtrada = tabela_consolidada() %>% filter(Data)
      tabela_restadm <- filtro_base_geral() %>%
        filter(DTA_EXEC %in% tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) %>%
        select(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAVAM, RESTRICAO_ADM, GRAVAME, GRAVAME_PENDENTE, PROPRIETARIO, ULT_ROM, TRANSFERENCIA) %>%
        arrange(EMPRESA) %>%
        rename(
          "Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
          "Modelo" = MODELO, "Ano" = ANO, "Renavam" = RENAVAM, `Rest Adm` = RESTRICAO_ADM,
          "Gravame" = GRAVAME, `Gravame Pendente` = GRAVAME_PENDENTE, "Proprietário" = PROPRIETARIO
        ) %>%
        mutate(across(where(is.character) & !c(Placa, UF, TRANSFERENCIA), str_to_title))
    }
  })

  # Tabela Renajud consol ------------------------------------------------------------

  tabela_renajudconsol_frota <- reactive({
    conexao_duck <- dbConnect(duckdb())
    dbWriteTable(conexao_duck, "filtro_base_geral", filtro_base_geral(), overwrite = TRUE)
    dbWriteTable(conexao_duck, "filtro_base_atual", filtro_base_atual(), overwrite = TRUE)

    if (is.null(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) ||
      length(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) == 0) {

      tabela_renajud_consol_frota <- dbGetQuery(conexao_duck, "
        SELECT
            EMPRESA AS Empresa,
            UNIDADE AS Unidade,
            UF_Emp AS UF,
            PLACA AS Placa,
            upper(substr(TIPO, 1, 1)) || lower(substr(TIPO, 2)) AS Tipo,
            upper(substr(MODELO, 1, 1)) || lower(substr(MODELO, 2)) AS Modelo,
            ANO AS Ano,
            RENAJUD AS Renajud,
            TRANSFERENCIA,
            ULT_ROM,
            SUM(CAST(TOTAL_PROCESSOS AS DOUBLE)) AS 'Nº processos'
        FROM filtro_base_atual
        GROUP BY
            EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAJUD, TRANSFERENCIA, ULT_ROM
        ORDER BY EMPRESA

      ")
    } else {
      # tabela_geral_filtrada = tabela_consolidada() %>% filter(Data)
      # tabela_renajud_consol_frota = filtro_base_geral() %>%
      #   filter(DTA_EXEC %in% tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa","selected")]) %>%
      #   mutate(across(where(is.character) & !c(PLACA, UF_Emp, TRANSFERENCIA),str_to_title)) %>%
      #   group_by(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAJUD, TRANSFERENCIA,ULT_ROM) %>%
      #   summarise(`Nº processos` = sum(as.numeric(TOTAL_PROCESSOS),na.rm = TRUE)) %>%
      #   arrange(EMPRESA) %>%
      #   rename("Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
      #          "Modelo" = MODELO, "Ano" = ANO, "Renajud" = RENAJUD)

      tabela_renajud_consol_frota <- dbGetQuery(conexao_duck, glue("
        SELECT
            EMPRESA AS Empresa,
            UNIDADE AS Unidade,
            UF_Emp AS UF,
            PLACA AS Placa,
            upper(substr(TIPO, 1, 1)) || lower(substr(TIPO, 2)) AS Tipo,
            upper(substr(MODELO, 1, 1)) || lower(substr(MODELO, 2)) AS Modelo,
            ANO AS Ano,
            RENAJUD AS Renajud,
            TRANSFERENCIA,
            ULT_ROM,
            SUM(CAST(TOTAL_PROCESSOS AS DOUBLE)) AS 'Nº processos'
        FROM filtro_base_geral
        WHERE DTA_EXEC IN ({tabela_consolidada()$Data[getReactableState('tabela_frotaconsolid_reativa','selected')]})
        GROUP BY
            EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAJUD, TRANSFERENCIA, ULT_ROM
        ORDER BY EMPRESA

      "))
    }

    dbDisconnect(conexao_duck)

    tabela_renajud_consol_frota
  })

  # Tabela Renajud detal ------------------------------------------------------------

  tabela_renajuddetal_frota <- reactive({
    selected_dates <- tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]

    tabela <- if (is.null(selected_dates) || length(selected_dates) == 0) {
      filtro_base_atual()
    } else {
      filtro_base_geral() %>% filter(DTA_EXEC %in% selected_dates)
    }

    geral_consolid <- unite(tabela, col = "CHAVE", PLACA, DTA_EXEC, sep = "", remove = FALSE)
    geral_renajud_consolid <- unite(frota_renajud(), col = "CHAVE", PLACA, DTA_EXEC, sep = "")

    inner_join(
      geral_renajud_consolid,
      geral_consolid[, c("EMPRESA", "UNIDADE", "UF_Emp", "PLACA", "DTA_EXEC", "RENAJUD", "TIPO", "MODELO", "ANO", "ULT_ROM", "CHAVE", "TRANSFERENCIA")],
      by = "CHAVE",
      relationship = "many-to-many"
    ) %>%
      filter(RENAJUD == "Sim") %>%
      select(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, PROCESSO, TIPO_RESTRICAO, TRIBUNAL, ORGAO, TRANSFERENCIA, ULT_ROM) %>%
      arrange(EMPRESA) %>%
      mutate(across(where(is.character) & !c(PLACA, UF_Emp, TRANSFERENCIA), str_to_title)) %>%
      rename(
        "Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
        "Modelo" = MODELO, "Ano" = ANO, "Processo" = PROCESSO, `Tipo Restrição` = TIPO_RESTRICAO,
        "Tribunal" = TRIBUNAL, "Órgão" = ORGAO
      )
  })

  # Tabela Detran ------------------------------------------------------------

  tabela_detran_frota <- reactive({
    conexao_duck <- dbConnect(duckdb())
    dbWriteTable(conexao_duck, "filtro_base_geral", filtro_base_geral(), overwrite = TRUE)
    dbWriteTable(conexao_duck, "filtro_base_atual", filtro_base_atual(), overwrite = TRUE)

    if (is.null(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) ||
      length(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) == 0) {
      # tabela_detran_frota = filtro_base_geral() %>%
      #   filter(DTA_EXEC == max(DTA_EXEC)) %>%
      #   mutate(across(where(is.character) & !c(PLACA, UF_Emp, TRANSFERENCIA),str_to_title)) %>%
      #   group_by(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAVAM, TRANSFERENCIA,ULT_ROM) %>%
      #   summarise(Débito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE),
      #             `Ipva Atual` = sum(as.numeric(IPVA), na.rm = TRUE),
      #             `Ipva Ant` = sum(as.numeric(IPVA_AL_ANT), na.rm = TRUE),
      #             Licenciamento = sum(as.numeric(LICENCIAMENTO), na.rm = TRUE),
      #             Multa = sum(as.numeric(MULTA), na.rm = TRUE),
      #             `Outros débitos` = round(sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) - sum(as.numeric(LICENCIAMENTO), na.rm = TRUE) - sum(as.numeric(IPVA), na.rm = TRUE) - sum(as.numeric(MULTA), na.rm = TRUE), 2),
      #             `Tabela Fipe` = sum(as.numeric(TABELA_FIPE), na.rm = TRUE)) %>%
      #   arrange(desc(Débito)) %>%
      #   rename("Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
      #          "Modelo" = MODELO, "Ano" = ANO, "Renavam" = RENAVAM) %>%
      #   mutate(Débito = scales::dollar(Débito,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #          `Ipva Atual` = scales::dollar(`Ipva Atual`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #          `Ipva Ant` = scales::dollar(`Ipva Ant`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #          Licenciamento = scales::dollar(Licenciamento,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #          Multa = scales::dollar(Multa,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #          `Outros débitos` = scales::dollar(`Outros débitos`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #          `Tabela Fipe` = scales::dollar(`Tabela Fipe`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01))

      tabela_detran_frota <- dbGetQuery(conexao_duck, "
                 SELECT
                        EMPRESA AS Empresa,
                        UNIDADE AS Unidade,
                        UF_Emp AS UF,
                        PLACA AS Placa,
                        upper(substr(TIPO, 1, 1)) || lower(substr(TIPO, 2)) AS Tipo,
                        upper(substr(MODELO, 1, 1)) || lower(substr(MODELO, 2)) AS Modelo,
                        ANO AS Ano,
                        RENAVAM AS Renavam,
                        TRANSFERENCIA,
                        ULT_ROM,
                        SUM(COALESCE(DEBITO_DETRAN,0)) AS Débito,
                        SUM(COALESCE(IPVA,0)) AS 'Ipva Atual',
                        SUM(COALESCE(IPVA_AL_ANT,0)) AS 'Ipva Ant',
                        SUM(COALESCE(LICENCIAMENTO,0)) AS Licenciamento,
                        SUM(COALESCE(MULTA,0)) AS Multa,

                              SUM(COALESCE(DEBITO_DETRAN,0))
                            - SUM(COALESCE(LICENCIAMENTO,0))
                            - SUM(COALESCE(IPVA,0))
                            - SUM(COALESCE(MULTA,0))
                         AS 'Outros débitos',
                        SUM(COALESCE(TABELA_FIPE,0)) AS 'Tabela Fipe'
                    FROM filtro_base_atual
                    GROUP BY
                        EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAVAM, TRANSFERENCIA, ULT_ROM
                    ORDER BY SUM(COALESCE(DEBITO_DETRAN,0)) DESC;
                    ")
    } else {
      # tabela_detran_frota = filtro_base_geral() %>%
      #   filter(DTA_EXEC %in% tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa","selected")]) %>%
      #   mutate(across(where(is.character) & !c(PLACA, UF_Emp, TRANSFERENCIA),str_to_title)) %>%
      #   group_by(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAVAM, TRANSFERENCIA,ULT_ROM) %>%
      #   summarise(Débito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE),
      #             `Ipva Atual` = sum(as.numeric(IPVA), na.rm = TRUE),
      #             `Ipva Ant` = sum(as.numeric(IPVA_AL_ANT), na.rm = TRUE),
      #             Licenciamento = sum(as.numeric(LICENCIAMENTO), na.rm = TRUE),
      #             Multa = sum(as.numeric(MULTA), na.rm = TRUE),
      #             `Outros débitos` = round(sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) - sum(as.numeric(LICENCIAMENTO), na.rm = TRUE) - sum(as.numeric(IPVA), na.rm = TRUE) - sum(as.numeric(MULTA), na.rm = TRUE), 2),
      #             `Tabela Fipe` = sum(as.numeric(TABELA_FIPE), na.rm = TRUE)) %>%
      #   arrange(desc(Débito)) %>%
      #   rename("Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
      #          "Modelo" = MODELO, "Ano" = ANO, "Renavam" = RENAVAM) %>%
      #   mutate(Débito = scales::dollar(Débito,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #          `Ipva Atual` = scales::dollar(`Ipva Atual`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #          `Ipva Ant` = scales::dollar(`Ipva Ant`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #          Licenciamento = scales::dollar(Licenciamento,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #          Multa = scales::dollar(Multa,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #          `Outros débitos` = scales::dollar(`Outros débitos`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #          `Tabela Fipe` = scales::dollar(`Tabela Fipe`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01))

      tabela_detran_frota <- dbGetQuery(conexao_duck, glue("
          SELECT
              EMPRESA AS Empresa,
              UNIDADE AS Unidade,
              UF_Emp AS UF,
              PLACA AS Placa,
              TIPO AS Tipo,
              upper(substr(MODELO, 1, 1)) || lower(substr(MODELO, 2)) AS Modelo,
              ANO AS Ano,
              RENAVAM AS Renavam,
              TRANSFERENCIA,
              ULT_ROM,
              SUM(COALESCE(DEBITO_DETRAN,0)) AS Débito,
              SUM(COALESCE(IPVA,0)) AS 'Ipva Atual',
              SUM(COALESCE(IPVA_AL_ANT,0)) AS 'Ipva Ant',
              SUM(COALESCE(LICENCIAMENTO,0)) AS Licenciamento,
              SUM(COALESCE(MULTA,0)) AS Multa,

                    SUM(COALESCE(DEBITO_DETRAN,0))
                  - SUM(COALESCE(LICENCIAMENTO,0))
                  - SUM(COALESCE(IPVA,0))
                  - SUM(COALESCE(MULTA,0))
               AS 'Outros débitos',
              SUM(COALESCE(TABELA_FIPE,0)) AS 'Tabela Fipe'
          FROM filtro_base_geral
          WHERE DTA_EXEC in ({tabela_consolidada()$Data[getReactableState('tabela_frotaconsolid_reativa','selected')]})
          GROUP BY
              EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAVAM, TRANSFERENCIA, ULT_ROM
          ORDER BY SUM(COALESCE(DEBITO_DETRAN,0)) DESC;
      "))
    }

    dbDisconnect(conexao_duck)
    tabela_detran_frota
  })

  # Tabela Multas detalhadas ------------------------------------------------------------

  tabela_renainfdetal_frota <- reactive({
    tabela <- filtro_base_geral()

    # geral_consolid = unite(tabela, col = "CHAVE", PLACA, DTA_EXEC, sep = "", remove = FALSE)
    # geral_renainf_consolid = unite(frota_renainf(), col = "CHAVE", PLACA, DTA_EXEC, sep = "")

    geral_consolid <- tabela %>%
      group_by(PLACA) %>%
      filter(DTA_EXEC == max(DTA_EXEC)) %>%
      ungroup()

    geral_renainf_consolid <- frota_renainf()

    geral_renainf_detal <- inner_join(
      geral_renainf_consolid,
      geral_consolid %>% select(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, ULT_ROM, TRANSFERENCIA),
      by = "PLACA"
    )

    tabela_multas_frota <- geral_renainf_detal %>%
      select(
        EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAINF, AUTO_INFRACAO, DATA_HORA_INF,DT_IDENT_CONDUTOR, VENCIMENTO,
        VALOR, INFRACAO, LOCAL, ORGAO, PAGA, TRANSFERENCIA
      ) %>%
      arrange(PAGA, desc(VENCIMENTO)) %>%
      rename(
        "Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
        "Modelo" = MODELO, "Ano" = ANO, "Renainf" = RENAINF, `Auto da Infração` = AUTO_INFRACAO,
        "Vencimento" = VENCIMENTO, "Infração" = INFRACAO, "Valor" = VALOR, "Local" = LOCAL, "Órgão" = ORGAO,
        `Dt/Hr Infração` = DATA_HORA_INF, "Prazo ident condutor" = DT_IDENT_CONDUTOR, "Paga" = PAGA
      ) %>%
      mutate(across(where(is.character) & !c(Placa, UF, TRANSFERENCIA, Paga), str_to_title))
    # Valor = scales::dollar(as.numeric(Valor),prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01))
    # }
    # else {
    #   tabela_multas_frota = geral_renainf_detal %>%
    #     filter(DTA_EXEC %in% tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa","selected")]) %>%
    #     select(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAINF, AUTO_INFRACAO, VENCIMENTO,
    #            INFRACAO, LOCAL, ORGAO, DATA_HORA_INF, VALOR, TRANSFERENCIA) %>%
    #     arrange(desc(as.Date(VENCIMENTO, '%d/%m/%Y'))) %>%
    #     rename("Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
    #            "Modelo" = MODELO, "Ano" = ANO, "Renainf" = RENAINF, `Auto da Infração` = AUTO_INFRACAO,
    #            "Vencimento" = VENCIMENTO, "Infração" = INFRACAO, "Local" = LOCAL, "Órgão" = ORGAO,
    #            `Dt/Hr Infração` = DATA_HORA_INF, "Valor" = VALOR) %>%
    #     mutate(across(where(is.character) & !c(Placa, UF, TRANSFERENCIA),str_to_title),
    #            Valor = scales::dollar(as.numeric(Valor),prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01))
    #
    # }

    tabela_multas_frota <- unique(tabela_multas_frota)
  })



  # Tabela Custos ------------------------------------------------------------

  tabela_custos_frota <- reactive({
    if (is.null(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) ||
      length(tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) == 0) {
      tabela_custos_frota <- filtro_base_atual() %>%
        group_by(EMPRESA) %>%
        summarise(
          DTA_EXEC = max(DTA_EXEC),
          `Custo API` = round(sum(as.numeric(CUSTO_API), na.rm = TRUE), 2),
          Veículos = sum(!is.na(PLACA)),
          Débito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE),
          `Ipva Atual` = sum(as.numeric(IPVA), na.rm = TRUE),
          `Ipva Ant` = sum(as.numeric(IPVA_AL_ANT), na.rm = TRUE),
          Licenciamento = sum(as.numeric(LICENCIAMENTO), na.rm = TRUE),
          Multa = sum(as.numeric(MULTA), na.rm = TRUE),
          `Outros débitos` = round(sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) - sum(as.numeric(LICENCIAMENTO), na.rm = TRUE) - sum(as.numeric(IPVA), na.rm = TRUE) - sum(as.numeric(MULTA), na.rm = TRUE), 2),
          `Tabela Fipe` = sum(as.numeric(TABELA_FIPE), na.rm = TRUE),
          TRANSFERENCIA = sum(TRANSFERENCIA == "Sim", na.rm = TRUE)
        ) %>%
        arrange(EMPRESA, desc(DTA_EXEC)) %>%
        rename("Empresa" = EMPRESA) %>%
        # mutate(Débito = scales::dollar(Débito,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
        #        `Ipva Atual` = scales::dollar(`Ipva Atual`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
        #        `Ipva Ant` = scales::dollar(`Ipva Ant`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
        #        Licenciamento = scales::dollar(Licenciamento,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
        #        Multa = scales::dollar(Multa,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
        #        `Outros débitos` = scales::dollar(`Outros débitos`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
        #        `Tabela Fipe` = scales::dollar(`Tabela Fipe`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01)) %>%
        rename(Data = DTA_EXEC)
    } else {
      # tabela_geral_filtrada = tabela_consolidada() %>% filter(Data)
      tabela_custos_frota <- filtro_base_geral() %>%
        filter(DTA_EXEC %in% tabela_consolidada()$Data[getReactableState("tabela_frotaconsolid_reativa", "selected")]) %>%
        group_by(EMPRESA, DTA_EXEC) %>%
        summarise(
          `Custo API` = round(sum(as.numeric(CUSTO_API), na.rm = TRUE), 2),
          Veículos = sum(!is.na(PLACA)),
          Débito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE),
          `Ipva Atual` = sum(as.numeric(IPVA), na.rm = TRUE),
          `Ipva Ant` = sum(as.numeric(IPVA_AL_ANT), na.rm = TRUE),
          Licenciamento = sum(as.numeric(LICENCIAMENTO), na.rm = TRUE),
          Multa = sum(as.numeric(MULTA), na.rm = TRUE),
          `Outros débitos` = round(sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) - sum(as.numeric(LICENCIAMENTO), na.rm = TRUE) - sum(as.numeric(IPVA), na.rm = TRUE) - sum(as.numeric(MULTA), na.rm = TRUE), 2),
          `Tabela Fipe` = sum(as.numeric(TABELA_FIPE), na.rm = TRUE),
          TRANSFERENCIA = sum(TRANSFERENCIA == "Sim", na.rm = TRUE)
        ) %>%
        arrange(EMPRESA, desc(DTA_EXEC)) %>%
        rename("Empresa" = EMPRESA) %>%
        # mutate(Débito = scales::dollar(Débito,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
        #        `Ipva Atual` = scales::dollar(`Ipva Atual`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
        #        `Ipva Ant` = scales::dollar(`Ipva Ant`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
        #        Licenciamento = scales::dollar(Licenciamento,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
        #        Multa = scales::dollar(Multa,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
        #        `Outros débitos` = scales::dollar(`Outros débitos`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
        #        `Tabela Fipe` = scales::dollar(`Tabela Fipe`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01)) %>%
        rename(Data = DTA_EXEC)
    }
  })

  # Tabela principal --------------------------------------------------------

  output$tabela_frotageral_reativa <- renderReactable({
    req(tabela_frota_selecionada())

    if (input$bt_check_frota == "Geral" & session$userData$usuario %in% poder_total) {
      frota_selecionada <- tabela_frota_selecionada() %>%
        mutate(Data = if ("Data" %in% names(.)) format(as.Date(as.character(Data), "%Y%m%d"), "%d/%m/%Y") else NULL) %>%
        # mutate(Vencimento = if ("Vencimento" %in% names(.)) as.Date(as.character(Vencimento), "%Y%m%d")) %>%
        mutate(`Transferência manual` = "\u2795") %>%
        relocate(Anexo_transf, .after = last_col())
    } else {
      frota_selecionada <- tabela_frota_selecionada() %>%
        mutate(Data = if ("Data" %in% names(.)) format(as.Date(as.character(Data), "%Y%m%d"), "%d/%m/%Y") else NULL) %>%
        # mutate(Vencimento = if ("Vencimento" %in% names(.)) as.Date(as.character(Vencimento), "%Y%m%d")) %>%
        select(-dplyr::any_of("Anexo_transf"))
    }



    reactable(
      frota_selecionada,
      pagination = FALSE,
      compact = TRUE,
      highlight = TRUE,
      bordered = TRUE,
      resizable = TRUE,
      defaultColDef = colDef(
        align = "center",
        cell = function(value, index) {
          if (frota_selecionada[index, "TRANSFERENCIA"] == "Sim") {
            tags$span(
              title = "Oportunidade de transferência",
              value <- ifelse(is.na(value), "", value)
            )
          } else {
            value <- ifelse(is.na(value), "", value)
          }
        }
      ),
      wrap = FALSE,
      height = "50vh",
      selection = "single",
      onClick = "select",
      columns = c(
        list(
          .selection = colDef(show = FALSE),
          TRANSFERENCIA = colDef(show = FALSE),
          `Custo API` = colDef(show = length(revenda_query()) == 0),
          ULT_ROM = colDef(show = FALSE),
          Placa = colDef(
            cell = function(value) {
              if (value %in% geral_frota$PLACA[!is.na(geral_frota$ULT_ROM)]) {
                tags$span(
                  title = "Último romaneio há mais de 2 meses",
                  value
                )
              } else {
                value
              }
            },
            style = function(value) {
              if (value %in% geral_frota$PLACA[!is.na(geral_frota$ULT_ROM)]) {
                list(background = "orange", fontWeight = "bold", color = "#fff")
              }
            }
          )
        ),
        if (input$bt_check_frota == "Geral") {
          list(
            `Rest Adm` = colDef(show = FALSE),
            Gravame = colDef(show = FALSE),
            `Gravame Pendente` = colDef(show = FALSE),
            Renajud = colDef(show = FALSE)
          )
        } else {
          list()
        },
        if ("Prazo ident condutor" %in% names(frota_selecionada)) {
          list(
            `Prazo ident condutor` = colDef(
              width = 150,
              name = "Prz ident condutor",
              cell = function(value) {
                if (is.na(value)) "" else format(value, "%d/%m/%Y")
              },
              style = function(value) {
                # converter valor para Date (assumindo formato dd/mm/yyyy)
                data_val <- as.Date(value, format = "%d/%m/%Y")
                
                if (!is.na(data_val)) {
                  if (data_val >= Sys.Date()) {
                    # verde claro, fonte bold branca
                    return(list(
                      background = "#66BB6A", # verde clarinho
                      color = "white",
                      fontWeight = "bold"
                    ))
                  } else {
                    # vermelho, fonte bold branca
                    return(list(
                      background = "#E53935",
                      color = "white",
                      fontWeight = "bold"
                    ))
                  }
                }
                return(NULL) # caso data inválida
              }
            )
          )
        } else {
          list()
        },
        if ("Vencimento" %in% names(frota_selecionada)) {
          list(
            Vencimento = colDef(
              defaultSortOrder = "desc",
              cell = function(value) {
                if (is.na(value)) "" else format(value, "%d/%m/%Y")
              },
              style = function(value) {
                # converter valor para Date (assumindo formato dd/mm/yyyy)
                data_val <- as.Date(value, format = "%d/%m/%Y")

                if (!is.na(data_val)) {
                  if (data_val >= Sys.Date()) {
                    # verde claro, fonte bold branca
                    return(list(
                      background = "#66BB6A", # verde clarinho
                      color = "white",
                      fontWeight = "bold"
                    ))
                  } else {
                    # vermelho, fonte bold branca
                    return(list(
                      background = "#E53935",
                      color = "white",
                      fontWeight = "bold"
                    ))
                  }
                }
                return(NULL) # caso data inválida
              }
            )
          )
        } else {
          list()
        },
        if ("Transferência manual" %in% names(frota_selecionada)) {
          list(
            `Transferência manual` = colDef(
              cell = button_extra("bt_rev_transf", class = "bt_rev_transf_frota")
            )
          )
        } else {
          list()
        },
        if ("Anexo_transf" %in% names(frota_selecionada)) {
          list(
            Anexo_transf = colDef(
              name = "Anexo",
              cell = button_extra("bt_rev_anexo", class = "bt_rev_transf_frota")
            )
          )
        } else {
          list()
        },
        if ("ANEXO" %in% names(frota_selecionada)) {
          list(
            ANEXO = colDef(
              show = FALSE
            )
          )
        } else {
          list()
        },
        if ("Paga" %in% names(frota_selecionada)) {
          list(
            Paga = colDef(
              cell = function(value) {
                if (identical(value, "Sim")) {
                  tags$span(value, style = "color: #2e7d32; font-weight: bold;")
                } else {
                  tags$span(value, style = "color: #c62828; font-weight: bold;")
                }
              }
            )
          )
        } else {
          list()
        },
        if ("Valor" %in% names(frota_selecionada)) {
          list(
            Valor = colDef(
              cell = function(value) {
                scales::dollar(value, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01)
              }
            )
          )
        } else {
          list()
        },
        if ("Infração" %in% names(frota_selecionada)) {
          list(
            Infração = colDef(
              cell = function(value) {
                tags$span(
                  title = value,
                  value
                )
              }
            )
          )
        } else {
          list()
        },
        if ("Local" %in% names(frota_selecionada)) {
          list(
            Local = colDef(
              cell = function(value) {
                tags$span(
                  title = value,
                  value
                )
              }
            )
          )
        } else {
          list()
        },
        if ("Órgão" %in% names(frota_selecionada)) {
          list(
            Órgão = colDef(
              cell = function(value) {
                tags$span(
                  title = value,
                  value
                )
              }
            )
          )
        } else {
          list()
        },
        if ("Débito" %in% names(frota_selecionada)) {
          list(
            Débito = colDef(
              cell = function(value) {
                scales::dollar(value, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01)
              }
            )
          )
        } else {
          list()
        },
        if ("Ipva Atual" %in% names(frota_selecionada)) {
          list(
            `Ipva Atual` = colDef(
              cell = function(value) {
                scales::dollar(value, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01)
              }
            )
          )
        } else {
          list()
        },
        if ("Ipva Ant" %in% names(frota_selecionada)) {
          list(
            `Ipva Ant` = colDef(
              cell = function(value) {
                scales::dollar(value, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01)
              }
            )
          )
        } else {
          list()
        },
        if ("Licenciamento" %in% names(frota_selecionada)) {
          list(
            Licenciamento = colDef(
              cell = function(value) {
                scales::dollar(value, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01)
              }
            )
          )
        } else {
          list()
        },
        if ("Multa" %in% names(frota_selecionada)) {
          list(
            Multa = colDef(
              cell = function(value) {
                scales::dollar(value, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01)
              }
            )
          )
        } else {
          list()
        },
        if ("Outros débitos" %in% names(frota_selecionada)) {
          list(
            `Outros débitos` = colDef(
              cell = function(value) {
                scales::dollar(value, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01)
              }
            )
          )
        } else {
          list()
        },
        if ("Tabela Fipe" %in% names(frota_selecionada)) {
          list(
            `Tabela Fipe` = colDef(
              cell = function(value) {
                scales::dollar(value, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01)
              }
            )
          )
        } else {
          list()
        }
      ),
      rowStyle = function(index) {
        if (frota_selecionada[index, "TRANSFERENCIA"] == "Sim") {
          list(background = "#F0E199", height = "35px")
        } else {
          list(height = "35px")
        }
      },
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
  #
  # observe({
  #   linhas_frotageral_reativa = getReactableState("tabela_frotageral_reativa","selected",session)
  #   if(length(linhas_frotageral_reativa)){
  #     print(linhas_frotageral_reativa)
  #   }
  # })

  # UI ----------------------------------------------------------------------

  fluidRow(
    box(
      id = "box_frota_filtro",
      title = fluidRow(
        column(1, pickerInput("propfrotas_input", "Proprietário", choices = sort(unique(frota_principal()$EMPRESA)), multiple = TRUE, options = opcoes_filtro)),
        column(1, uiOutput("input_filtro_unidade")),
        column(1, pickerInput("uffrotas_input", "UF", choices = sort(unique(frota_principal()$UF_Emp)), multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("placafrotas_input", "Placa", choices = sort(unique(frota_principal()$PLACA)), multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("tipofrotas_input", "Tipo", choices = sort(unique(frota_principal()$TIPO)), multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("modelfrotas_input", "Modelo", choices = sort(unique(frota_principal()$MODELO)), multiple = TRUE, options = opcoes_filtro)),
        column(
          1,
          conditionalPanel(
            "input.bt_check_frota == 'Geral'",
            pickerInput("restadmfrotas_input", "Rest Adm",
              choices = sort(unique(frota_principal()$RESTRICAO_ADM[frota_principal()$RESTRICAO_ADM != ""])),
              multiple = TRUE, options = opcoes_filtro
            )
          ),
          conditionalPanel(
            "input.bt_check_frota == 'Rest Adm'",
            pickerInput("restadmfrotas_input", "Rest Adm",
              choices = sort(unique(frota_principal()$RESTRICAO_ADM[frota_principal()$RESTRICAO_ADM != ""])),
              multiple = TRUE, options = opcoes_filtro
            )
          ),
          conditionalPanel(
            "input.bt_check_frota == 'Renajud'",
            pickerInput("renajudfrotas_input", "Renajud",
              choices = sort(unique(frota_principal()$RENAJUD[frota_principal()$RENAJUD != ""])),
              multiple = TRUE, options = opcoes_filtro
            )
          ),
          conditionalPanel(
            "input.bt_check_frota == 'Detran'",
            pickerInput("detranfrotas_input", "Débito",
              choices = sort(unique(frota_principal()$DEBITO_DETRAN[frota_principal()$DEBITO_DETRAN != ""])),
              multiple = TRUE, options = opcoes_filtro
            )
          )
        ),
        column(
          1,
          conditionalPanel(
            "input.bt_check_frota == 'Geral'",
            pickerInput("gravamefrotas_input", "Gravame",
              choices = sort(unique(frota_principal()$GRAVAME[frota_principal()$GRAVAME != ""])),
              multiple = TRUE, options = opcoes_filtro
            )
          ),
          conditionalPanel(
            "input.bt_check_frota == 'Rest Adm'",
            pickerInput("gravamefrotas_input", "Gravame",
              choices = sort(unique(frota_principal()$GRAVAME[frota_principal()$GRAVAME != ""])),
              multiple = TRUE, options = opcoes_filtro
            )
          )
        ),
        column(
          1,
          conditionalPanel(
            "input.bt_check_frota == 'Geral'",
            pickerInput("gravamepenfrotas_input", "Gravame Pen",
              choices = sort(unique(frota_principal()$GRAVAME_PENDENTE[
                frota_principal()$GRAVAME_PENDENTE != ""
              ])),
              multiple = TRUE, options = opcoes_filtro
            )
          ),
          conditionalPanel(
            "input.bt_check_frota == 'Rest Adm'",
            pickerInput("gravamepenfrotas_input", "Gravame Pen",
              choices = sort(unique(frota_principal()$GRAVAME_PENDENTE[
                frota_principal()$GRAVAME_PENDENTE != ""
              ])),
              multiple = TRUE, options = opcoes_filtro
            )
          )
        ),
        column(
          1,
          conditionalPanel(
            "input.bt_check_frota == 'Geral'",
            pickerInput("renajudfrotas_input", "Renajud",
              choices = sort(unique(frota_principal()$RENAJUD[frota_principal()$RENAJUD != ""])),
              multiple = TRUE, options = opcoes_filtro
            )
          )
        ),
        column(1, pickerInput("transffrotas_input", "Transferência", choices = sort(unique(frota_principal()$TRANSFERENCIA)), multiple = TRUE, options = opcoes_filtro)),
        column(1,
          style = "display: flex; align-items: center;",
          column(1),
          column(9, actionButton("bt_limpafrota", label = NULL, icon = icon("eraser"), status = "primary", size = "lg", width = "100%") %>% tagAppendAttributes(title = "Limpar filtros")),
          column(1)
        )
      ),
      width = 12,
      status = "primary",
      collapsible = FALSE
    ),
    box(
      id = "card_frota_consolidada",
      width = 12,
      title = "Dados consolidados",
      status = "primary",
      collapsible = TRUE,
      collapsed = FALSE,
      fluidRow(
        column(
          6,
          fluidRow(
            infoBox(
              elevation = 2,
              title = NULL, width = 12, color = "primary", gradient = TRUE, fill = TRUE, icon = icon(NULL, class = "custom-icon-cavalo"),
              value = fluidRow(
                column(3, tags$div(tags$span(textOutput("cavalo_veic_reativo"), style = "font-size: 32px;"), style = "border-right:1px solid #ccc; padding-right:10px;  display:flex; align-items:center; justify-content:center;")),
                column(3, tags$div(tags$b("Rest. Adm:"), br(), tags$span(textOutput("cavalo_radm_reativo"), style = "font-size: 17px;"), style = "border-right:1px solid #ccc; padding-right:10px")),
                column(3, tags$div(tags$b("Renajud:"), br(), tags$span(textOutput("cavalo_rjud_reativo"), style = "font-size: 17px;"), style = "border-right:1px solid #ccc; padding-right:10px")),
                column(3, tags$div(tags$b("Débito:"), br(), tags$span(textOutput("cavalo_debi_reativo"), style = "font-size: 17px;")))
              )
            ) %>%
              tagAppendAttributes(title = "Cavalo e Reboque"),
            infoBox(
              elevation = 2,
              title = NULL, width = 12, color = "primary", gradient = TRUE, fill = TRUE, icon = icon(NULL, class = "custom-icon-caminhao"),
              value = fluidRow(
                column(3, tags$div(tags$span(textOutput("caminhao_veic_reativo"), style = "font-size: 32px;"), style = "border-right:1px solid #ccc; padding-right:10px;  display:flex; align-items:center; justify-content:center;")),
                column(3, tags$div(tags$b("Rest. Adm:"), br(), tags$span(textOutput("caminhao_radm_reativo"), style = "font-size: 17px;"), style = "border-right:1px solid #ccc; padding-right:10px")),
                column(3, tags$div(tags$b("Renajud:"), br(), tags$span(textOutput("caminhao_rjud_reativo"), style = "font-size: 17px;"), style = "border-right:1px solid #ccc; padding-right:10px")),
                column(3, tags$div(tags$b("Débito:"), br(), tags$span(textOutput("caminhao_debi_reativo"), style = "font-size: 17px;")))
              )
            ) %>%
              tagAppendAttributes(title = "Caminhão"),
            infoBox(
              elevation = 2,
              title = NULL, width = 12, color = "primary", gradient = TRUE, fill = TRUE, icon = icon(NULL, class = "custom-icon-carro"),
              value = fluidRow(
                column(3, tags$div(tags$span(textOutput("carro_veic_reativo"), style = "font-size: 32px;"), style = "border-right:1px solid #ccc; padding-right:10px;  display:flex; align-items:center; justify-content:center;")),
                column(3, tags$div(tags$b("Rest. Adm:"), br(), tags$span(textOutput("carro_radm_reativo"), style = "font-size: 17px;"), style = "border-right:1px solid #ccc; padding-right:10px")),
                column(3, tags$div(tags$b("Renajud:"), br(), tags$span(textOutput("carro_rjud_reativo"), style = "font-size: 17px;"), style = "border-right:1px solid #ccc; padding-right:10px")),
                column(3, tags$div(tags$b("Débito:"), br(), tags$span(textOutput("carro_debi_reativo"), style = "font-size: 17px;")))
              )
            ) %>%
              tagAppendAttributes(title = "Automóvel"),
            infoBox(
              elevation = 2,
              title = NULL, width = 12, color = "primary", gradient = TRUE, fill = TRUE, icon = icon(NULL, class = "custom-icon-moto"),
              value = fluidRow(
                column(3, tags$div(tags$span(textOutput("moto_veic_reativo"), style = "font-size: 32px;"), style = "border-right:1px solid #ccc; padding-right:10px;  display:flex; align-items:center; justify-content:center;")),
                column(3, tags$div(tags$b("Rest. Adm:"), br(), tags$span(textOutput("moto_radm_reativo"), style = "font-size: 17px;"), style = "border-right:1px solid #ccc; padding-right:10px")),
                column(3, tags$div(tags$b("Renajud:"), br(), tags$span(textOutput("moto_rjud_reativo"), style = "font-size: 17px;"), style = "border-right:1px solid #ccc; padding-right:10px")),
                column(3, tags$div(tags$b("Débito:"), br(), tags$span(textOutput("moto_debi_reativo"), style = "font-size: 17px;")))
              ) %>%
                tagAppendAttributes(title = "Motocicleta")
            )
          )
        ),
        column(6, withSpinner(reactableOutput("tabela_frotaconsolid_reativa"), type = 4))
      )
    ),
    column(12, br()),
    column(
      12,
      fluidRow(
        column(
          2,
          column(6,
            align = "left",
            downloadBttn("bt_download_frota_banco", label = NULL, style = "stretch", color = "primary") %>%
              tagAppendAttributes(title = "Baixar tabela formatada")
          ),
          column(6)
        ),
        column(8,
          align = "center",
          radioGroupButtons("bt_check_frota",
            label = NULL,
            choices = c("Geral", "Rest Adm", "Renajud", "Detran", "Custos"),
            # width = "100px",
            status = "primary",
            justified = TRUE,
            individual = TRUE
          )
        ),
        column(2)
      )
    ),
    column(12, br()),
    column(
      width = 12,
      box(
        id = "card_frota_detalhada",
        title = fluidRow(
          column(4, "Detalhamento"),
          column(8, uiOutput("switch_renajud_renainf"))
        ),
        collapsible = TRUE,
        maximizable = TRUE,
        status = "primary",
        width = 12,
        withSpinner(reactableOutput("tabela_frotageral_reativa"), type = 4)
      )
    ),
    downloadButton("bt_download_transf_anexo", style = "visibility: hidden; position:absolute; left:-9999px;")
  )
}
