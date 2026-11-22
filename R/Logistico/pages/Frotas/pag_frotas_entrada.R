pag_frotas_entrada <- function() {
  # Carregar e tratar dados ----------------------------------------------------------

  source(glue("{diretorio}pages/Frotas/Dados/dados_frotas.R"), local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Frotas/Guia_ajuda.R"), local = TRUE, encoding = "UTF-8")


  # Server ------------------------------------------------------------------
  frota_revenda_entrada <- reactiveVal(geral_frota_entrada)
  frota_renajud_entrada <- reactiveVal(geral_renajud)
  frota_renainf_entrada <- reactiveVal(geral_renainf)

  frota_principal_entrada <- reactive({
    if (length(revenda_query()) == 0) {
      frota_revenda_entrada()
    } else if (str_detect(revenda_query(), "LOCADORA") | str_detect(revenda_query(), "ARRENDADORA") | str_detect(revenda_query(), "TRANSPORTADORA")) {
      frota_revenda_entrada() %>% filter(str_detect(toupper(EMPRESA), revenda_query()))
    } else {
      frota_revenda_entrada() %>% filter(str_detect(toupper(UNIDADE), revenda_query()) | str_detect(toupper(EMPRESA), revenda_query()))
    }
  })

  # Textos reativos --------------------------------------------------------

  ### Ultima atualizacao --------------------------------------------------------
  output$ult_atualizacao_id_entrada_frota <- renderText({
    glue("Atualizado em: {format(as.Date(as.character(max(geral_frota$DTA_EXEC)), '%Y%m%d'), '%d/%m/%Y')}")
  })

  ### Aviso --------------------------------------------------------
  output$aviso_id_entrada_frota <- renderText({
    if (any(filtro_base_geral_entrada()$UF_Emp %in% c("NI"))) {
      "Detran PE e RJ se encontram com instabilidades."
    } else {
      ""
    }
  })

  # Botoes e filtros --------------------------------------------------------

  ### Botao --------------------------------------------------------
  observeEvent(input$bt_limpafrota_entrada, {
    updatePickerInput(session, inputId = "propfrotas_input_entrada", selected = character(0))
    updatePickerInput(session, inputId = "unidfrotas_input_entrada", selected = character(0))
    updatePickerInput(session, inputId = "uffrotas_input_entrada", selected = character(0))
    updatePickerInput(session, inputId = "placafrotas_input_entrada", selected = character(0))
    updatePickerInput(session, inputId = "tipofrotas_input_entrada", selected = character(0))
    updatePickerInput(session, inputId = "modelfrotas_input_entrada", selected = character(0))
    updatePickerInput(session, inputId = "carrocfrotas_input_entrada", selected = character(0))
    updatePickerInput(session, inputId = "restadmfrotas_input_entrada", selected = character(0))
    updatePickerInput(session, inputId = "gravamefrotas_input_entrada", selected = character(0))
    updatePickerInput(session, inputId = "gravamepenfrotas_input_entrada", selected = character(0))
    updatePickerInput(session, inputId = "renajudfrotas_input_entrada", selected = character(0))
    updatePickerInput(session, inputId = "detranfrotas_input_entrada", selected = character(0))
    updatePickerInput(session, inputId = "transffrotas_input_entrada", selected = character(0))
  })

  tabela_frota_selecionada_entrada <- reactive({
    base_geral_entrada <- switch(input$bt_check_frota_entrada,
      "Geral" = tabela_geral_frota_entrada(),
      "Rest Adm" = tabela_restadm_frota_entrada(),
      "Renajud" = {
        if (isTRUE(input$switch_renajud_renainf_frota_entrada)) {
          tabela_renajuddetal_frota_entrada()
        } else {
          tabela_renajudconsol_frota_entrada()
        }
      },
      "Detran" = {
        if (isTRUE(input$switch_renajud_renainf_frota_entrada)) {
          tabela_renainfdetal_frota_entrada()
        } else {
          tabela_detran_frota_entrada()
        }
      },
      "Custos" = tabela_custos_frota_entrada(),
      tabela_geral_frota_entrada() # default
    )

    base_geral_entrada
  })

  output$switch_renajud_renainf_entrada <- renderUI({
    if (!is.null(input$bt_check_frota_entrada) && input$bt_check_frota_entrada == "Renajud") {
      # Mostra o switch
      prettySwitch(
        inputId = "switch_renajud_renainf_frota_entrada",
        label = NULL,
        status = "success",
        fill = TRUE,
        bigger = FALSE
      )
    } else if (!is.null(input$bt_check_frota_entrada) && input$bt_check_frota_entrada == "Detran") {
      prettySwitch(
        inputId = "switch_renajud_renainf_frota_entrada",
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
          inputId = "switch_renajud_renainf_frota_entrada",
          label = NULL,
          status = "success",
          fill = TRUE,
          bigger = FALSE
        )
      )
    }
  })

  ### Download --------------------------------------------------------

  output$bt_download_id_entrada_frota <- downloadHandler(
    filename = function() {
      paste("frota-", Sys.Date(), ".xlsx", sep = "")
    },
    content = function(con) {
      colunas_remover <- c("Custo API", "CNPJ_EMP", "Anexo", "ANEXO", "Informar motivo", "ULT_ROM", "TRANSFERENCIA")

      tabela_frota_selecionada_entrada() %>%
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


  output$input_filtro_unidade_entrada <- renderUI({
    if (is.null(revenda_query()) | length(revenda_query()) == 0) {
      pickerInput("unidfrotas_input_entrada", "Unidade", choices = sort(unique(frota_principal_entrada()$UNIDADE[!is.na(frota_principal_entrada()$UNIDADE) & frota_principal_entrada()$UNIDADE != ""])), multiple = TRUE, options = opcoes_filtro)
    } else if (str_detect(revenda_query(), "LOCADORA") | str_detect(revenda_query(), "ARRENDADORA") | str_detect(revenda_query(), "TRANSPORTADORA")) {
      pickerInput("unidfrotas_input_entrada", "Unidade", choices = sort(unique(frota_principal_entrada()$UNIDADE[!is.na(frota_principal_entrada()$UNIDADE) & frota_principal_entrada()$UNIDADE != ""])), multiple = TRUE, options = opcoes_filtro)
    } else {
      div( # style = "display: none;",
        pickerInput("unidfrotas_input_entrada", "Unidade", choices = sort(unique(frota_principal_entrada()$UNIDADE[!is.na(frota_principal_entrada()$UNIDADE) & frota_principal_entrada()$UNIDADE != ""])), multiple = TRUE, options = opcoes_filtro)
      )
    }
  })

  # observeEvent(input$propfrotas_input_entrada,{
  #   req(input$propfrotas_input_entrada)
  #   print(nrow(frota_principal_entrada() %>% filter(EMPRESA %in% input$propfrotas_input_entrada)))
  # })

  filtro_base_geral_entrada <- reactive({
    if ((is.null(input$propfrotas_input_entrada) || length(input$propfrotas_input_entrada) == 0) &&
      (is.null(input$unidfrotas_input_entrada) || length(input$unidfrotas_input_entrada) == 0) &&
      (is.null(input$uffrotas_input_entrada) || length(input$uffrotas_input_entrada) == 0) &&
      (is.null(input$placafrotas_input_entrada) || length(input$placafrotas_input_entrada) == 0) &&
      (is.null(input$tipofrotas_input_entrada) || length(input$tipofrotas_input_entrada) == 0) &&
      (is.null(input$modelfrotas_input_entrada) || length(input$modelfrotas_input_entrada) == 0) &&
      (is.null(input$carrocfrotas_input_entrada) || length(input$carrocfrotas_input_entrada) == 0) &&
      (is.null(input$restadmfrotas_input_entrada) || length(input$restadmfrotas_input_entrada) == 0) &&
      (is.null(input$gravamefrotas_input_entrada) || length(input$gravamefrotas_input_entrada) == 0) &&
      (is.null(input$gravamepenfrotas_input_entrada) || length(input$gravamepenfrotas_input_entrada) == 0) &&
      (is.null(input$renajudfrotas_input_entrada) || length(input$renajudfrotas_input_entrada) == 0) &&
      (is.null(input$detranfrotas_input_entrada) || length(input$detranfrotas_input_entrada) == 0) &&
      (is.null(input$transffrotas_input_entrada) || length(input$transffrotas_input_entrada) == 0)) {
      dados <- frota_principal_entrada()
    } else {
      dados <- frota_principal_entrada() %>%
        filter(
          if (is.null(input$propfrotas_input_entrada) || length(input$propfrotas_input_entrada) == 0) TRUE else EMPRESA %in% input$propfrotas_input_entrada,
          if (is.null(input$uffrotas_input_entrada) || length(input$uffrotas_input_entrada) == 0) TRUE else UF_Emp %in% input$uffrotas_input_entrada,
          if (is.null(input$unidfrotas_input_entrada) || length(input$unidfrotas_input_entrada) == 0) TRUE else UNIDADE %in% input$unidfrotas_input_entrada,
          if (is.null(input$placafrotas_input_entrada) || length(input$placafrotas_input_entrada) == 0) TRUE else PLACA %in% input$placafrotas_input_entrada,
          if (is.null(input$tipofrotas_input_entrada) || length(input$tipofrotas_input_entrada) == 0) TRUE else TIPO %in% input$tipofrotas_input_entrada,
          if (is.null(input$modelfrotas_input_entrada) || length(input$modelfrotas_input_entrada) == 0) TRUE else MODELO %in% input$modelfrotas_input_entrada,
          if (is.null(input$carrocfrotas_input_entrada) || length(input$carrocfrotas_input_entrada) == 0) TRUE else CARROCERIA %in% input$carrocfrotas_input_entrada,
          if (is.null(input$restadmfrotas_input_entrada) || length(input$restadmfrotas_input_entrada) == 0) TRUE else RESTRICAO_ADM %in% input$restadmfrotas_input_entrada,
          if (is.null(input$gravamefrotas_input_entrada) || length(input$gravamefrotas_input_entrada) == 0) TRUE else GRAVAME %in% input$gravamefrotas_input_entrada,
          if (is.null(input$gravamepenfrotas_input_entrada) || length(input$gravamepenfrotas_input_entrada) == 0) TRUE else GRAVAME_PENDENTE %in% input$gravamepenfrotas_input_entrada,
          if (is.null(input$renajudfrotas_input_entrada) || length(input$renajudfrotas_input_entrada) == 0) TRUE else RENAJUD %in% input$renajudfrotas_input_entrada,
          if (is.null(input$detranfrotas_input_entrada) || length(input$detranfrotas_input_entrada) == 0) TRUE else DEBITO_DETRAN %in% input$detranfrotas_input_entrada,
          if (is.null(input$transffrotas_input_entrada) || length(input$transffrotas_input_entrada) == 0) TRUE else TRANSFERENCIA %in% input$transffrotas_input_entrada
        )
    }

    dados
  })


  observeEvent(filtro_base_geral_entrada(), {
    # Atualiza apenas se não houver seleção — opções sempre da base completa (sem cascata)
    if (is.null(input$uffrotas_input_entrada) || length(input$uffrotas_input_entrada) == 0) {
      updatePickerInput(session, "uffrotas_input_entrada", choices = sort(unique(frota_principal_entrada()$UF_Emp)))
    }
    if (is.null(input$propfrotas_input_entrada) || length(input$propfrotas_input_entrada) == 0) {
      updatePickerInput(session, "propfrotas_input_entrada", choices = sort(unique(frota_principal_entrada()$EMPRESA)))
    }
    if (is.null(input$unidfrotas_input_entrada) || length(input$unidfrotas_input_entrada) == 0) {
      updatePickerInput(session, "unidfrotas_input_entrada", choices = sort(unique(frota_principal_entrada()$UNIDADE)))
    }
    if (is.null(input$placafrotas_input_entrada) || length(input$placafrotas_input_entrada) == 0) {
      updatePickerInput(session, "placafrotas_input_entrada", choices = sort(unique(frota_principal_entrada()$PLACA)))
    }
    if (is.null(input$tipofrotas_input_entrada) || length(input$tipofrotas_input_entrada) == 0) {
      updatePickerInput(session, "tipofrotas_input_entrada", choices = sort(unique(frota_principal_entrada()$TIPO)))
    }
    if (is.null(input$modelfrotas_input_entrada) || length(input$modelfrotas_input_entrada) == 0) {
      updatePickerInput(session, "modelfrotas_input_entrada", choices = sort(unique(frota_principal_entrada()$MODELO)))
    }
    if (is.null(input$carrocfrotas_input_entrada) || length(input$carrocfrotas_input_entrada) == 0) {
      updatePickerInput(session, "carrocfrotas_input_entrada", choices = sort(unique(frota_principal_entrada()$CARROCERIA)))
    }
    if (is.null(input$restadmfrotas_input_entrada) || length(input$restadmfrotas_input_entrada) == 0) {
      updatePickerInput(session, "restadmfrotas_input_entrada", choices = sort(unique(frota_principal_entrada()$RESTRICAO_ADM)))
    }
    if (is.null(input$gravamefrotas_input_entrada) || length(input$gravamefrotas_input_entrada) == 0) {
      updatePickerInput(session, "gravamefrotas_input_entrada", choices = sort(unique(frota_principal_entrada()$GRAVAME)))
    }
    if (is.null(input$gravamepenfrotas_input_entrada) || length(input$gravamepenfrotas_input_entrada) == 0) {
      updatePickerInput(session, "gravamepenfrotas_input_entrada", choices = sort(unique(frota_principal_entrada()$GRAVAME_PENDENTE)))
    }
    if (is.null(input$renajudfrotas_input_entrada) || length(input$renajudfrotas_input_entrada) == 0) {
      updatePickerInput(session, "renajudfrotas_input_entrada", choices = sort(unique(frota_principal_entrada()$RENAJUD)))
    }
    if (is.null(input$detranfrotas_input_entrada) || length(input$detranfrotas_input_entrada) == 0) {
      updatePickerInput(session, "detranfrotas_input_entrada", choices = sort(unique(frota_principal_entrada()$DEBITO_DETRAN)))
    }
    if (is.null(input$transffrotas_input_entrada) || length(input$transffrotas_input_entrada) == 0) {
      updatePickerInput(session, "transffrotas_input_entrada", choices = sort(unique(frota_principal_entrada()$TRANSFERENCIA)))
    }
    # if (!is.null(getReactableState("tabela_frotaconsolid_reativa_entrada","selected"))){
    #   data_filtro(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada","selected")])
    # }
    # else{
    #   data_filtro(NULL)
    # }
    # print(which(tabela_consolidada_entrada()$Data == data_filtro()))
  })

  # ### Ajuda --------------------------------------------------------
  #
  # observeEvent(input$bt_guia_id_entrada_frota, {
  #   funcao_guia_frota("Entrada")$init()$start()
  # })
  #
  # Cards -------------------------------------------------------------------

  cavalo_reativo_entrada <- reactive({
    if (is.null(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) ||
      length(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) == 0) {
      dados <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR == max(DTA_ENTR), str_detect(TIPO, "TRATOR|REBOQ")) %>%
        group_by(DTA_ENTR) %>%
        summarise(
          veiculos = sum(str_detect(TIPO, "TRATOR|REBOQ"), na.rm = TRUE),
          rest_adm = sum(RESTRICAO_ADM == "Sim", na.rm = TRUE),
          renajud = sum(RENAJUD == "Sim", na.rm = TRUE),
          debito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) / 1000
        ) %>%
        mutate(debito = scales::dollar(debito, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01, suffix = " Mil"))
    } else {
      dados <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR %in% tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")], str_detect(TIPO, "TRATOR|REBOQ")) %>%
        group_by(DTA_ENTR) %>%
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

  output$cavalo_veic_reativo_entrada <- renderText({
    cavalo_reativo_entrada()$veiculos
  })
  output$cavalo_radm_reativo_entrada <- renderText({
    cavalo_reativo_entrada()$rest_adm
  })
  output$cavalo_rjud_reativo_entrada <- renderText({
    cavalo_reativo_entrada()$renajud
  })
  output$cavalo_debi_reativo_entrada <- renderText({
    cavalo_reativo_entrada()$debito
  })

  caminhao_reativo_entrada <- reactive({
    if (is.null(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) ||
      length(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) == 0) {
      dados <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR == max(DTA_ENTR), str_detect(TIPO, "CAMINH") & !str_detect(TIPO, "TRATOR")) %>%
        group_by(DTA_ENTR) %>%
        summarise(
          veiculos = sum(str_detect(TIPO, "CAMINH") & !str_detect(TIPO, "TRATOR"), na.rm = TRUE),
          rest_adm = sum(RESTRICAO_ADM == "Sim", na.rm = TRUE),
          renajud = sum(RENAJUD == "Sim", na.rm = TRUE),
          debito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) / 1000
        ) %>%
        mutate(debito = scales::dollar(debito, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01, suffix = " Mil"))
    } else {
      dados <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR %in% tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")], str_detect(TIPO, "CAMINH") & !str_detect(TIPO, "TRATOR")) %>%
        group_by(DTA_ENTR) %>%
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


  output$caminhao_veic_reativo_entrada <- renderText({
    caminhao_reativo_entrada()$veiculos
  })
  output$caminhao_radm_reativo_entrada <- renderText({
    caminhao_reativo_entrada()$rest_adm
  })
  output$caminhao_rjud_reativo_entrada <- renderText({
    caminhao_reativo_entrada()$renajud
  })
  output$caminhao_debi_reativo_entrada <- renderText({
    caminhao_reativo_entrada()$debito
  })


  carro_reativo_entrada <- reactive({
    if (is.null(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) ||
      length(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) == 0) {
      dados <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR == max(DTA_ENTR), TIPO %in% c("AUTOMOVEL", "CAMIONETA", "UTILITARIO")) %>%
        group_by(DTA_ENTR) %>%
        summarise(
          veiculos = sum(TIPO %in% c("AUTOMOVEL", "CAMIONETA", "UTILITARIO"), na.rm = TRUE),
          rest_adm = sum(RESTRICAO_ADM == "Sim", na.rm = TRUE),
          renajud = sum(RENAJUD == "Sim", na.rm = TRUE),
          debito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) / 1000
        ) %>%
        mutate(debito = scales::dollar(debito, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01, suffix = " Mil"))
    } else {
      dados <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR %in% tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")], TIPO %in% c("AUTOMOVEL", "CAMIONETA", "UTILITARIO")) %>%
        group_by(DTA_ENTR) %>%
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

  output$carro_veic_reativo_entrada <- renderText({
    carro_reativo_entrada()$veiculos
  })
  output$carro_radm_reativo_entrada <- renderText({
    carro_reativo_entrada()$rest_adm
  })
  output$carro_rjud_reativo_entrada <- renderText({
    carro_reativo_entrada()$renajud
  })
  output$carro_debi_reativo_entrada <- renderText({
    carro_reativo_entrada()$debito
  })

  moto_reativo_entrada <- reactive({
    if (is.null(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) ||
      length(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) == 0) {
      dados <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR == max(DTA_ENTR), str_detect(TIPO, "MOTO")) %>%
        group_by(DTA_ENTR) %>%
        summarise(
          veiculos = sum(str_detect(TIPO, "MOTO"), na.rm = TRUE),
          rest_adm = sum(RESTRICAO_ADM == "Sim", na.rm = TRUE),
          renajud = sum(RENAJUD == "Sim", na.rm = TRUE),
          debito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) / 1000
        ) %>%
        mutate(debito = scales::dollar(debito, prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01, suffix = " Mil"))
    } else {
      dados <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR %in% tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")], str_detect(TIPO, "MOTO")) %>%
        group_by(DTA_ENTR) %>%
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

  output$moto_veic_reativo_entrada <- renderText({
    moto_reativo_entrada()$veiculos
  })
  output$moto_radm_reativo_entrada <- renderText({
    moto_reativo_entrada()$rest_adm
  })
  output$moto_rjud_reativo_entrada <- renderText({
    moto_reativo_entrada()$renajud
  })
  output$moto_debi_reativo_entrada <- renderText({
    moto_reativo_entrada()$debito
  })

  # Tabela consolidada ------------------------------------------------------

  # Tabela consolidada com renajud ------------------------------------------

  tabela_consolidada_entrada <- reactive({
    tabela <- filtro_base_geral_entrada()

    geral_consolid_entrada <- unite(tabela, col = "CHAVE", PLACA, DTA_EXEC, sep = "", remove = FALSE)
    geral_renajud_consolid_entrada <- unite(frota_renajud_entrada(), col = "CHAVE", PLACA, DTA_EXEC, sep = "")


    geral_renajud_detal_entrada <- left_join(
      geral_consolid_entrada,
      geral_renajud_consolid_entrada,
      by = "CHAVE",
      relationship = "many-to-many"
    )


    tabela_consol_entrada <- distinct(geral_renajud_detal_entrada, PLACA, DTA_ENTR, .keep_all = TRUE)


    frota_consolid_entrada <- tabela_consol_entrada %>%
      group_by(DTA_ENTR) %>%
      summarise(
        `Custo API` = round(sum(as.numeric(CUSTO_API), na.rm = TRUE), 2), Veículos = sum(!is.na(PLACA)),
        Carro = sum(TIPO %in% c("AUTOMOVEL", "CAMIONETA", "UTILITARIO"), na.rm = TRUE), Moto = sum(str_detect(TIPO, "MOTO"), na.rm = TRUE),
        Cavalo = sum(str_detect(TIPO, "TRATOR|REBOQ"), na.rm = TRUE), Caminhao = sum(str_detect(TIPO, "CAMINH") & !str_detect(TIPO, "TRATOR"), na.rm = TRUE),
        Débito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE), Renajud = sum(RENAJUD == "Sim", na.rm = TRUE), `Tabela Fipe` = sum(as.numeric(TABELA_FIPE), na.rm = TRUE)
      ) %>%
      arrange(desc(DTA_ENTR)) %>%
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
      # DTA_ENTR = format(DTA_ENTR, "%d/%m/%Y")) %>%
      rename(Data = DTA_ENTR)

    frota_consolid_entrada
  })


  output$tabela_frotaconsolid_reativa_entrada <- renderReactable({
    req(tabela_consolidada_entrada())

    reactable(
      tabela_consolidada_entrada() %>% mutate(Data = format(as.Date(as.character(Data), "%Y%m%d"), "%d/%m/%Y")),
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
        `Custo API` = colDef(show = length(revenda_query()) == 0, cell = icon_sets(tabela_consolidada_entrada(), icon_ref = "Taxa_Custo API", icon_color_ref = "cor_Taxa_Custo API", icon_position = "left")),
        Veículos = colDef(cell = icon_sets(tabela_consolidada_entrada(), icon_ref = "Taxa_Veículos", icon_color_ref = "cor_Taxa_Veículos", icon_position = "left")),
        Carro = colDef(cell = icon_sets(tabela_consolidada_entrada(), icon_ref = "Taxa_Carro", icon_color_ref = "cor_Taxa_Carro", icon_position = "left")),
        Moto = colDef(cell = icon_sets(tabela_consolidada_entrada(), icon_ref = "Taxa_Moto", icon_color_ref = "cor_Taxa_Moto", icon_position = "left")),
        Caminhao = colDef(cell = icon_sets(tabela_consolidada_entrada(), icon_ref = "Taxa_Caminhao", icon_color_ref = "cor_Taxa_Caminhao", icon_position = "left")),
        Cavalo = colDef(cell = icon_sets(tabela_consolidada_entrada(), icon_ref = "Taxa_Cavalo", icon_color_ref = "cor_Taxa_Cavalo", icon_position = "left")),
        Débito = colDef(cell = icon_sets(tabela_consolidada_entrada(), icon_ref = "Taxa_Débito", icon_color_ref = "cor_Taxa_Débito", icon_position = "left")),
        Renajud = colDef(cell = icon_sets(tabela_consolidada_entrada(), icon_ref = "Taxa_Renajud", icon_color_ref = "cor_Taxa_Renajud", icon_position = "left")),
        `Tabela Fipe` = colDef(cell = icon_sets(tabela_consolidada_entrada(), icon_ref = "Taxa_Tabela Fipe", icon_color_ref = "cor_Taxa_Tabela Fipe", icon_position = "left"))
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

  tabela_geral_frota_entrada <- reactive({
    if (is.null(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) ||
      length(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) == 0) {
      tabela_geral_entrada <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR == max(DTA_ENTR)) %>%
        select(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, ANO_FAB, RENAVAM, CHASSI, CARROCERIA, ULT_ROM, TRANSFERENCIA) %>%
        arrange(EMPRESA) %>%
        rename(
          "Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
          "Modelo" = MODELO, "Ano" = ANO, "Fabricação" = ANO_FAB, "Renavam" = RENAVAM,
          "Chassi" = CHASSI, "Carroceria" = CARROCERIA
        ) %>%
        mutate(across(where(is.character) & !c(Placa, UF, TRANSFERENCIA), str_to_title))
    } else {
      # tabela_geral_filtrada = tabela_consolidada_entrada() %>% filter(Data)
      tabela_geral_entrada <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR %in% tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) %>%
        select(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, ANO_FAB, RENAVAM, CHASSI, CARROCERIA, ULT_ROM, TRANSFERENCIA) %>%
        arrange(EMPRESA) %>%
        rename(
          "Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
          "Modelo" = MODELO, "Ano" = ANO, "Fabricação" = ANO_FAB, "Renavam" = RENAVAM,
          "Chassi" = CHASSI, "Carroceria" = CARROCERIA
        ) %>%
        mutate(across(where(is.character) & !c(Placa, UF, TRANSFERENCIA), str_to_title))
    }
  })

  # Tabela Restricao Adm ------------------------------------------------------------

  tabela_restadm_frota_entrada <- reactive({
    if (is.null(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) ||
      length(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) == 0) {
      tabela_rest_adm_frota_entrada <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR == max(DTA_ENTR)) %>%
        select(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAVAM, RESTRICAO_ADM, GRAVAME, GRAVAME_PENDENTE, ULT_ROM, TRANSFERENCIA) %>%
        arrange(EMPRESA) %>%
        rename(
          "Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
          "Modelo" = MODELO, "Ano" = ANO, "Renavam" = RENAVAM, `Rest Adm` = RESTRICAO_ADM,
          "Gravame" = GRAVAME, `Gravame Pendente` = GRAVAME_PENDENTE
        ) %>%
        mutate(across(where(is.character) & !c(Placa, UF, TRANSFERENCIA), str_to_title))
    } else {
      # tabela_geral_filtrada = tabela_consolidada_entrada() %>% filter(Data)
      tabela_rest_adm_frota_entrada <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR %in% tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) %>%
        select(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAVAM, RESTRICAO_ADM, GRAVAME, GRAVAME_PENDENTE, ULT_ROM, TRANSFERENCIA) %>%
        arrange(EMPRESA) %>%
        rename(
          "Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
          "Modelo" = MODELO, "Ano" = ANO, "Renavam" = RENAVAM, `Rest Adm` = RESTRICAO_ADM,
          "Gravame" = GRAVAME, `Gravame Pendente` = GRAVAME_PENDENTE
        ) %>%
        mutate(across(where(is.character) & !c(Placa, UF, TRANSFERENCIA), str_to_title))
    }
  })

  # Tabela Renajud consol ------------------------------------------------------------

  tabela_renajudconsol_frota_entrada <- reactive({
    if (is.null(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) ||
      length(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) == 0) {
      tabela_renajud_consol_frota_entrada <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR == max(DTA_ENTR)) %>%
        mutate(across(where(is.character) & !c(PLACA, UF_Emp, TRANSFERENCIA), str_to_title)) %>%
        group_by(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAJUD, TRANSFERENCIA, ULT_ROM) %>%
        summarise(`Nº processos` = sum(as.numeric(TOTAL_PROCESSOS), na.rm = TRUE)) %>%
        arrange(EMPRESA) %>%
        rename(
          "Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
          "Modelo" = MODELO, "Ano" = ANO, "Renajud" = RENAJUD
        )
    } else {
      # tabela_geral_filtrada = tabela_consolidada_entrada() %>% filter(Data)
      tabela_renajud_consol_frota_entrada <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR %in% tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) %>%
        mutate(across(where(is.character) & !c(PLACA, UF_Emp, TRANSFERENCIA), str_to_title)) %>%
        group_by(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAJUD, TRANSFERENCIA, ULT_ROM) %>%
        summarise(`Nº processos` = sum(as.numeric(TOTAL_PROCESSOS), na.rm = TRUE)) %>%
        arrange(EMPRESA) %>%
        rename(
          "Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
          "Modelo" = MODELO, "Ano" = ANO, "Renajud" = RENAJUD
        )
    }
  })

  # Tabela Renajud detal ------------------------------------------------------------

  tabela_renajuddetal_frota_entrada <- reactive({
    tabela_entrada <- filtro_base_geral_entrada()

    geral_consolid_entrada <- unite(tabela_entrada, col = "CHAVE", PLACA, DTA_EXEC, sep = "", remove = FALSE)
    geral_renajud_consolid_entrada <- unite(frota_renajud_entrada(), col = "CHAVE", PLACA, DTA_EXEC, sep = "")


    geral_renajud_detal_entrada <- left_join(
      geral_consolid_entrada[, c("EMPRESA", "UNIDADE", "UF_Emp", "PLACA", "DTA_ENTR", "RENAJUD", "TIPO", "MODELO", "ANO", "ULT_ROM", "CHAVE", "TRANSFERENCIA")],
      geral_renajud_consolid_entrada,
      by = "CHAVE",
      relationship = "many-to-many"
    )


    tabela_consol_entrada <- distinct(geral_renajud_detal_entrada, PLACA, DTA_ENTR, .keep_all = TRUE)


    if (is.null(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) ||
      length(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) == 0) {
      tabela_renajud_detal_frota_entrada <- tabela_consol_entrada %>%
        filter(
          DTA_ENTR == max(DTA_ENTR),
          RENAJUD == "Sim"
        ) %>%
        select(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, PROCESSO, TIPO_RESTRICAO, TRIBUNAL, ORGAO, TRANSFERENCIA, ULT_ROM) %>%
        arrange(EMPRESA) %>%
        mutate(across(where(is.character) & !c(PLACA, UF_Emp, TRANSFERENCIA), str_to_title)) %>%
        rename(
          "Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
          "Modelo" = MODELO, "Ano" = ANO, "Processo" = PROCESSO, `Tipo Restrição` = TIPO_RESTRICAO,
          "Tribunal" = TRIBUNAL, "Órgão" = ORGAO
        )
    } else {
      # tabela_geral_filtrada = tabela_consolidada_entrada() %>% filter(Data)

      tabela_renajud_detal_frota_entrada <- tabela_consol_entrada %>%
        filter(
          DTA_ENTR %in% tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")],
          RENAJUD == "Sim"
        ) %>%
        select(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, PROCESSO, TIPO_RESTRICAO, TRIBUNAL, ORGAO, TRANSFERENCIA, ULT_ROM) %>%
        arrange(EMPRESA) %>%
        mutate(across(where(is.character) & !c(PLACA, UF_Emp, TRANSFERENCIA), str_to_title)) %>%
        rename(
          "Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
          "Modelo" = MODELO, "Ano" = ANO, "Processo" = PROCESSO, `Tipo Restrição` = TIPO_RESTRICAO,
          "Tribunal" = TRIBUNAL, "Órgão" = ORGAO
        )
    }
  })

  # Tabela Detran ------------------------------------------------------------

  tabela_detran_frota_entrada <- reactive({
    if (is.null(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) ||
      length(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) == 0) {
      tabela_detran_frota_entrada <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR == max(DTA_ENTR)) %>%
        mutate(across(where(is.character) & !c(PLACA, UF_Emp, TRANSFERENCIA), str_to_title)) %>%
        group_by(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAVAM, TRANSFERENCIA, ULT_ROM) %>%
        summarise(
          Débito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE),
          `Ipva Atual` = sum(as.numeric(IPVA), na.rm = TRUE),
          `Ipva Ant` = sum(as.numeric(IPVA_AL_ANT), na.rm = TRUE),
          Licenciamento = sum(as.numeric(LICENCIAMENTO), na.rm = TRUE),
          Multa = sum(as.numeric(MULTA), na.rm = TRUE),
          `Outros débitos` = round(sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) - sum(as.numeric(LICENCIAMENTO), na.rm = TRUE) - sum(as.numeric(IPVA), na.rm = TRUE) - sum(as.numeric(MULTA), na.rm = TRUE), 2),
          `Tabela Fipe` = sum(as.numeric(TABELA_FIPE), na.rm = TRUE)
        ) %>%
        arrange(desc(Débito)) %>%
        rename(
          "Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
          "Modelo" = MODELO, "Ano" = ANO, "Renavam" = RENAVAM
        )
      # mutate(Débito = scales::dollar(Débito,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #        `Ipva Atual` = scales::dollar(`Ipva Atual`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #        `Ipva Ant` = scales::dollar(`Ipva Ant`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #        Licenciamento = scales::dollar(Licenciamento,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #        Multa = scales::dollar(Multa,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #        `Outros débitos` = scales::dollar(`Outros débitos`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #        `Tabela Fipe` = scales::dollar(`Tabela Fipe`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01))
    } else {
      # tabela_geral_filtrada = tabela_consolidada_entrada() %>% filter(Data)
      tabela_detran_frota_entrada <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR %in% tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) %>%
        mutate(across(where(is.character) & !c(PLACA, UF_Emp, TRANSFERENCIA), str_to_title)) %>%
        group_by(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAVAM, TRANSFERENCIA, ULT_ROM) %>%
        summarise(
          Débito = sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE),
          `Ipva Atual` = sum(as.numeric(IPVA), na.rm = TRUE),
          `Ipva Ant` = sum(as.numeric(IPVA_AL_ANT), na.rm = TRUE),
          Licenciamento = sum(as.numeric(LICENCIAMENTO), na.rm = TRUE),
          Multa = sum(as.numeric(MULTA), na.rm = TRUE),
          `Outros débitos` = round(sum(as.numeric(DEBITO_DETRAN), na.rm = TRUE) - sum(as.numeric(LICENCIAMENTO), na.rm = TRUE) - sum(as.numeric(IPVA), na.rm = TRUE) - sum(as.numeric(MULTA), na.rm = TRUE), 2),
          `Tabela Fipe` = sum(as.numeric(TABELA_FIPE), na.rm = TRUE)
        ) %>%
        arrange(desc(Débito)) %>%
        rename(
          "Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
          "Modelo" = MODELO, "Ano" = ANO, "Renavam" = RENAVAM
        )
      # mutate(Débito = scales::dollar(Débito,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #        `Ipva Atual` = scales::dollar(`Ipva Atual`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #        `Ipva Ant` = scales::dollar(`Ipva Ant`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #        Licenciamento = scales::dollar(Licenciamento,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #        Multa = scales::dollar(Multa,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #        `Outros débitos` = scales::dollar(`Outros débitos`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01),
      #        `Tabela Fipe` = scales::dollar(`Tabela Fipe`,prefix = "R$ ", big.mark = ".", decimal.mark = ",", accuracy = 0.01))
    }
  })

  # Tabela Multas detalhadas ------------------------------------------------------------

  tabela_renainfdetal_frota_entrada <- reactive({
    tabela_entrada <- filtro_base_geral_entrada()

    # geral_consolid_entrada = unite(tabela_entrada, col = "CHAVE", PLACA, DTA_EXEC, sep = "", remove = FALSE)
    # geral_renainf_consolid_entrada = unite(frota_renainf_entrada(), col = "CHAVE", PLACA, DTA_EXEC, sep = "")
    #
    #
    # geral_renainf_detal_entrada = inner_join(
    #   geral_renainf_consolid_entrada,
    #   geral_consolid_entrada %>% select(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, CHAVE, DTA_EXEC, TRANSFERENCIA),
    #   by = "CHAVE"
    # )

    geral_consolid_entrada <- tabela_entrada %>%
      group_by(PLACA, CNPJ_EMP) %>%
      filter(DTA_EXEC == max(DTA_EXEC)) %>%
      ungroup()
    geral_renainf_consolid_entrada <- frota_renainf_entrada()

    geral_renainf_detal_entrada <- inner_join(
      geral_renainf_consolid_entrada,
      geral_consolid_entrada %>% select(EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, ULT_ROM, TRANSFERENCIA),
      by = "PLACA",
      relationship = "many-to-many"
    )

    tabela_multas_frota_entrada <- geral_renainf_detal_entrada %>%
      select(
        EMPRESA, UNIDADE, UF_Emp, PLACA, TIPO, MODELO, ANO, RENAINF, AUTO_INFRACAO, DATA_HORA_INF, VENCIMENTO,
        DT_IDENT_CONDUTOR, VALOR, INFRACAO, LOCAL, ORGAO, PAGA, TRANSFERENCIA
      ) %>%
      arrange(PAGA, desc(VENCIMENTO)) %>%
      rename(
        "Empresa" = EMPRESA, "Unidade" = UNIDADE, "UF" = UF_Emp, "Placa" = PLACA, "Tipo" = TIPO,
        "Modelo" = MODELO, "Ano" = ANO, "Renainf" = RENAINF, `Auto da Infração` = AUTO_INFRACAO,
        "Vencimento" = VENCIMENTO, "Infração" = INFRACAO, "Local" = LOCAL, "Órgão" = ORGAO,
        `Dt/Hr Infração` = DATA_HORA_INF, "Valor" = VALOR, "Prazo ident condutor" = DT_IDENT_CONDUTOR,
        "Paga" = PAGA
      ) %>%
      mutate(across(where(is.character) & !c(Placa, UF, Paga, TRANSFERENCIA), str_to_title))
    tabela_multas_frota_entrada <- unique(tabela_multas_frota_entrada)
  })

  # Tabela Custos ------------------------------------------------------------

  tabela_custos_frota_entrada <- reactive({
    if (is.null(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) ||
      length(tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) == 0) {
      tabela_custos_frota_entrada <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR == max(DTA_ENTR)) %>%
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
    } else {
      # tabela_geral_filtrada = tabela_consolidada_entrada() %>% filter(Data)
      tabela_custos_frota_entrada <- filtro_base_geral_entrada() %>%
        filter(DTA_ENTR %in% tabela_consolidada_entrada()$Data[getReactableState("tabela_frotaconsolid_reativa_entrada", "selected")]) %>%
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



  output$tabela_frotageral_reativa_entrada <- renderReactable({
    req(tabela_frota_selecionada_entrada())

    frota_selecionada_entrada <- tabela_frota_selecionada_entrada() %>%
      mutate(Data = if ("Data" %in% names(.)) format(as.Date(as.character(Data), "%Y%m%d"), "%d/%m/%Y") else NULL)
    # datatable(
    #   tabela_geral_frota_entrada,
    #   selection = 'none',                # Para evitar seleção (como reactable padrão)
    #   extensions = c('Scroller'),        # Para scroll eficiente com muitos dados
    #   options = list(
    #     scrollY = "59vh",                # Equivale ao maxHeight = "60vh"
    #     scrollX = TRUE,                  # Equivale ao overflowX = "auto"
    #     scrollCollapse = TRUE,           # Para colapsar quando há poucos dados
    #     info = FALSE,                    # Remove informações de paginação
    #     ordering = TRUE,                 # Permite ordenação
    #     scroller = TRUE,                 # Scroll eficiente para muitos dados
    #     deferRender = TRUE,              # Renderização sob demanda
    #     compact = TRUE,                  # Equivale ao compact = TRUE
    #     autoWidth = TRUE,               # Controle manual da largura
    #     dom = 't',                       # Apenas filtros e tabela (remove outros elementos)
    #     columnDefs = list(
    #       # list(width = "50px", className = 'dt-left', targets = 0),
    #       list(className = 'dt-center', targets = "_all")
    #     )
    #     # fixedColumns = list(leftColumns = 5)
    #
    #   ),
    #   rownames = FALSE,                  # Remove nomes das linhas
    #   escape = FALSE,                     # Permite HTML nas células se necessário
    #   class = "compact stripe hover"
    # )

    reactable(
      frota_selecionada_entrada,
      pagination = FALSE,
      compact = TRUE,
      highlight = TRUE,
      bordered = TRUE,
      resizable = TRUE,
      defaultColDef = colDef(
        align = "center",
        cell = function(value, index) {
          if (frota_selecionada_entrada[index, "TRANSFERENCIA"] == "Sim") {
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
      selection = "multiple",
      onClick = "select",
      columns = c(
        list(
          .selection = colDef(show = FALSE),
          TRANSFERENCIA = colDef(show = FALSE),
          `Custo API` = colDef(show = length(revenda_query()) == 0),
          ULT_ROM = colDef(show = FALSE),
          Placa = colDef(
            cell = function(value) {
              if (value %in% geral_frota_entrada$PLACA[!is.na(geral_frota_entrada$ULT_ROM)]) {
                tags$span(
                  title = "Último romaneio há mais de 2 meses",
                  value
                )
              } else {
                value
              }
            },
            style = function(value) {
              if (value %in% geral_frota_entrada$PLACA[!is.na(geral_frota_entrada$ULT_ROM)]) {
                list(background = "orange", fontWeight = "bold", color = "#fff")
              }
            }
          )
        ),
        if ("Prazo ident condutor" %in% names(frota_selecionada_entrada)) {
          list(
            `Prazo ident condutor` = colDef(
              width = 150,
              name = "Prz ident condutor",
              cell = function(value) {
                if (is.na(value)) "" else format(value, "%d/%m/%Y")
              }
            )
          )
        } else {
          list()
        },
        if ("Vencimento" %in% names(frota_selecionada_entrada)) {
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
        if ("Paga" %in% names(frota_selecionada_entrada)) {
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
        if ("Valor" %in% names(frota_selecionada_entrada)) {
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
        if ("Infração" %in% names(frota_selecionada_entrada)) {
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
        if ("Local" %in% names(frota_selecionada_entrada)) {
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
        if ("Órgão" %in% names(frota_selecionada_entrada)) {
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
        if ("Débito" %in% names(frota_selecionada_entrada)) {
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
        if ("Ipva Atual" %in% names(frota_selecionada_entrada)) {
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
        if ("Ipva Ant" %in% names(frota_selecionada_entrada)) {
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
        if ("Licenciamento" %in% names(frota_selecionada_entrada)) {
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
        if ("Multa" %in% names(frota_selecionada_entrada)) {
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
        if ("Outros débitos" %in% names(frota_selecionada_entrada)) {
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
        if ("Tabela Fipe" %in% names(frota_selecionada_entrada)) {
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
        if (frota_selecionada_entrada[index, "TRANSFERENCIA"] == "Sim") {
          list(background = "#F0E199", height = "35px")
        } else {
          list(height = "35px")
        }
      },
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
  #
  # observe({
  #   linhas_frotageral_reativa = getReactableState("tabela_frotageral_reativa_entrada ","selected",session)
  #   if(length(linhas_frotageral_reativa)){
  #     print(linhas_frotageral_reativa)
  #   }
  # })

  # UI ----------------------------------------------------------------------

  fluidRow(
    box(
      id = "box_frota_filtro_entrada",
      title = fluidRow(
        column(1, pickerInput("propfrotas_input_entrada", "Proprietário", choices = sort(unique(frota_principal_entrada()$EMPRESA)), multiple = TRUE, options = opcoes_filtro)),
        column(1, uiOutput("input_filtro_unidade_entrada")),
        column(1, pickerInput("uffrotas_input_entrada", "UF", choices = sort(unique(frota_principal_entrada()$UF_Emp)), multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("placafrotas_input_entrada", "Placa", choices = sort(unique(frota_principal_entrada()$PLACA)), multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("tipofrotas_input_entrada", "Tipo", choices = sort(unique(frota_principal_entrada()$TIPO)), multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("modelfrotas_input_entrada", "Modelo", choices = sort(unique(frota_principal_entrada()$MODELO)), multiple = TRUE, options = opcoes_filtro)),
        column(
          1,
          conditionalPanel(
            "input.bt_check_frota_entrada == 'Geral'",
            pickerInput("carrocfrotas_input_entrada", "Carroceria",
              choices = sort(unique(frota_principal_entrada()$CARROCERIA[frota_principal_entrada()$CARROCERIA != ""])),
              multiple = TRUE, options = opcoes_filtro
            )
          ),
          conditionalPanel(
            "input.bt_check_frota_entrada == 'Rest Adm'",
            pickerInput("restadmfrotas_input_entrada", "Rest Adm",
              choices = sort(unique(frota_principal_entrada()$RESTRICAO_ADM[frota_principal_entrada()$RESTRICAO_ADM != ""])),
              multiple = TRUE, options = opcoes_filtro
            )
          ),
          conditionalPanel(
            "input.bt_check_frota_entrada == 'Renajud'",
            pickerInput("renajudfrotas_input_entrada", "Renajud",
              choices = sort(unique(frota_principal_entrada()$RENAJUD[frota_principal_entrada()$RENAJUD != ""])),
              multiple = TRUE, options = opcoes_filtro
            )
          ),
          conditionalPanel(
            "input.bt_check_frota_entrada == 'Detran'",
            pickerInput("detranfrotas_input_entrada", "Débito",
              choices = sort(unique(frota_principal_entrada()$DEBITO_DETRAN[frota_principal_entrada()$DEBITO_DETRAN != ""])),
              multiple = TRUE, options = opcoes_filtro
            )
          )
        ),
        column(
          1,
          conditionalPanel(
            "input.bt_check_frota_entrada == 'Rest Adm'",
            pickerInput("gravamefrotas_input_entrada", "Gravame",
              choices = sort(unique(frota_principal_entrada()$GRAVAME[frota_principal_entrada()$GRAVAME != ""])),
              multiple = TRUE, options = opcoes_filtro
            )
          )
        ),
        column(
          1,
          conditionalPanel(
            "input.bt_check_frota_entrada == 'Rest Adm'",
            pickerInput("gravamepenfrotas_input_entrada", "Gravame Pen",
              choices = sort(unique(frota_principal_entrada()$GRAVAME_PENDENTE[
                frota_principal_entrada()$GRAVAME_PENDENTE != ""
              ])),
              multiple = TRUE, options = opcoes_filtro
            )
          )
        ),
        column(1),
        column(1, pickerInput("transffrotas_input_entrada", "Transferência", choices = sort(unique(frota_principal_entrada()$TRANSFERENCIA)), multiple = TRUE, options = opcoes_filtro)),
        column(1,
          style = "display: flex; align-items: center;",
          column(1),
          column(9, actionButton("bt_limpafrota_entrada", label = NULL, icon = icon("eraser"), status = "primary", size = "lg", width = "100%") %>% tagAppendAttributes(title = "Limpar filtros")),
          column(1)
        )
      ),
      width = 12,
      status = "primary",
      collapsible = FALSE
    ),
    box(
      id = "card_frota_consolidada_entrada",
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
                column(3, tags$div(tags$span(textOutput("cavalo_veic_reativo_entrada"), style = "font-size: 32px;"), style = "border-right:1px solid #ccc; padding-right:10px;  display:flex; align-items:center; justify-content:center;")),
                column(3, tags$div(tags$b("Rest. Adm:"), br(), tags$span(textOutput("cavalo_radm_reativo_entrada"), style = "font-size: 17px;"), style = "border-right:1px solid #ccc; padding-right:10px")),
                column(3, tags$div(tags$b("Renajud:"), br(), tags$span(textOutput("cavalo_rjud_reativo_entrada"), style = "font-size: 17px;"), style = "border-right:1px solid #ccc; padding-right:10px")),
                column(3, tags$div(tags$b("Débito:"), br(), tags$span(textOutput("cavalo_debi_reativo_entrada"), style = "font-size: 17px;")))
              )
            ) %>%
              tagAppendAttributes(title = "Cavalo e Reboque"),
            infoBox(
              elevation = 2,
              title = NULL, width = 12, color = "primary", gradient = TRUE, fill = TRUE, icon = icon(NULL, class = "custom-icon-caminhao"),
              value = fluidRow(
                column(3, tags$div(tags$span(textOutput("caminhao_veic_reativo_entrada"), style = "font-size: 32px;"), style = "border-right:1px solid #ccc; padding-right:10px;  display:flex; align-items:center; justify-content:center;")),
                column(3, tags$div(tags$b("Rest. Adm:"), br(), tags$span(textOutput("caminhao_radm_reativo_entrada"), style = "font-size: 17px;"), style = "border-right:1px solid #ccc; padding-right:10px")),
                column(3, tags$div(tags$b("Renajud:"), br(), tags$span(textOutput("caminhao_rjud_reativo_entrada"), style = "font-size: 17px;"), style = "border-right:1px solid #ccc; padding-right:10px")),
                column(3, tags$div(tags$b("Débito:"), br(), tags$span(textOutput("caminhao_debi_reativo_entrada"), style = "font-size: 17px;")))
              )
            ) %>%
              tagAppendAttributes(title = "Caminhão"),
            infoBox(
              elevation = 2,
              title = NULL, width = 12, color = "primary", gradient = TRUE, fill = TRUE, icon = icon(NULL, class = "custom-icon-carro"),
              value = fluidRow(
                column(3, tags$div(tags$span(textOutput("carro_veic_reativo_entrada"), style = "font-size: 32px;"), style = "border-right:1px solid #ccc; padding-right:10px;  display:flex; align-items:center; justify-content:center;")),
                column(3, tags$div(tags$b("Rest. Adm:"), br(), tags$span(textOutput("carro_radm_reativo_entrada"), style = "font-size: 17px;"), style = "border-right:1px solid #ccc; padding-right:10px")),
                column(3, tags$div(tags$b("Renajud:"), br(), tags$span(textOutput("carro_rjud_reativo_entrada"), style = "font-size: 17px;"), style = "border-right:1px solid #ccc; padding-right:10px")),
                column(3, tags$div(tags$b("Débito:"), br(), tags$span(textOutput("carro_debi_reativo_entrada"), style = "font-size: 17px;")))
              )
            ) %>%
              tagAppendAttributes(title = "Automóvel"),
            infoBox(
              elevation = 2,
              title = NULL, width = 12, color = "primary", gradient = TRUE, fill = TRUE, icon = icon(NULL, class = "custom-icon-moto"),
              value = fluidRow(
                column(3, tags$div(tags$span(textOutput("moto_veic_reativo_entrada"), style = "font-size: 32px;"), style = "border-right:1px solid #ccc; padding-right:10px;  display:flex; align-items:center; justify-content:center;")),
                column(3, tags$div(tags$b("Rest. Adm:"), br(), tags$span(textOutput("moto_radm_reativo_entrada"), style = "font-size: 17px;"), style = "border-right:1px solid #ccc; padding-right:10px")),
                column(3, tags$div(tags$b("Renajud:"), br(), tags$span(textOutput("moto_rjud_reativo_entrada"), style = "font-size: 17px;"), style = "border-right:1px solid #ccc; padding-right:10px")),
                column(3, tags$div(tags$b("Débito:"), br(), tags$span(textOutput("moto_debi_reativo_entrada"), style = "font-size: 17px;")))
              ) %>%
                tagAppendAttributes(title = "Motocicleta")
            )
          )
        ),
        column(6, withSpinner(reactableOutput("tabela_frotaconsolid_reativa_entrada"), type = 4))
      )
    ),
    column(12, br()),
    column(
      12,
      fluidRow(
        column(2),
        column(8,
          align = "center",
          radioGroupButtons("bt_check_frota_entrada",
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
        id = "card_frota_detalhada_entrada",
        title = fluidRow(
          column(4, "Detalhamento"),
          column(8, uiOutput("switch_renajud_renainf_entrada"))
        ),
        collapsible = TRUE,
        maximizable = TRUE,
        status = "primary",
        width = 12,
        withSpinner(reactableOutput("tabela_frotageral_reativa_entrada"), type = 4)
      )
    )
  )
}
