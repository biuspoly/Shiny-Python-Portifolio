library(promises)
library(future)

plan(sequential) # portfólio: no navegador não há outro processo para o future usar

# Carregar dados ----------------------------------------------------------

source(glue("{diretorio}pages/Comodatos/Dados/dados_comodato.R"), local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Comodatos/Dados/funcoes_data_cor.R"), local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Comodatos/Dados/solicita_comodato.R"), local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Comodatos/Dados/adiciona_pedido.R"), local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Comodatos/Dados/verifica_cadcli.R"), local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Comodatos/Dados/gerar_pdf.R"), local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Comodatos/Dados/funcao_cnpj.R"), local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Comodatos/Dados/funcao_extracao_doc.R"), local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Comodatos/Guia_ajuda.R"), local = TRUE, encoding = "UTF-8")


pag_comodatos_inadimplentes = function(){
  
  
  
  # Server ------------------------------------------------------------------
  
  # responsaveis por solicitar
  
  responsaveis = reactive({
    c("visitante")  # Portfólio: no original, os logins de quem pode solicitar
  })
  
  # gatilho para refresh
  refresh_solic <- reactiveVal(0)
  
  clientes_inad_geral <- reactive({
    if (length(revenda_query()) == 0){
      clientes_inadimplentes()
    }
    else{
      clientes_inadimplentes() %>% filter(str_detect(toupper(REVENDA), revenda_query()))
    }
  })
  
  comod_pedidos = reactive({
    req(refresh_solic())
    # req(input$data_input_comod_saldo)
    if (length(revenda_query()) == 0){
      dados = comod_solicitados("HOLDING")
    }
    else{
      dados = comod_solicitados(revenda_query())
    }
    
    if(!is.null(input$cli_solic_comod_input)){
      dados = dados %>% filter(CLIENTE %in% c(input$cli_solic_comod_input))
    }
    
    dados
    
  })
  
  
  # Botoes e filtros --------------------------------------------------------
  ### Botoes --------------------------------------------------------
  
  #### Limpa filtros -----------------------------------------
  observeEvent(input$bt_limpacomod_solic, {
    updatePickerInput(session,inputId = "cli_solic_comod_input",selected = character(0))
    updatePickerInput(session,inputId = "tip_solic_comod_input",selected = character(0))
    updatePickerInput(session,inputId = "cid_solic_comod_input",selected = character(0))
    updatePickerInput(session,inputId = "cla_solic_comod_input",selected = character(0))
    updatePickerInput(session,inputId = "canal_solic_comod_input",selected = character(0))
    updatePickerInput(session,inputId = "ven_solic_comod_input",selected = character(0))
    updatePickerInput(session,inputId = "ga_solic_comod_input",selected = character(0))
    updatePickerInput(session,inputId = "ina_solic_comod_input",selected = character(0))
    updatePickerInput(session,inputId = "stdoc_solic_comod_input",selected = character(0))
  })
  
  #### Produtos no modal ------------
  produtos_filtrados <- reactive({
    req(input$button_comod_inad)
    produtos_solicita(unique(filtro_solic_comod_geral()$CNPJ_REV[input$button_comod_inad$row]))
  })
  
  
  #### Detalhes de clientes ----------
  
  observeEvent(input$button_det_comod_inad,{
    req(input$button_det_comod_inad)
    
    detalhes_cli = detalhes_cli_inad(unique(filtro_solic_comod_geral()$CHAVE_CLI[input$button_det_comod_inad$row]))
    detalhes_cli$DT = as.Date(as.character(detalhes_cli$DT), "%Y%m%d")
    detalhes_cli$VENC = as.Date(as.character(detalhes_cli$VENC), "%Y%m%d")
    detalhes_cli$Produto = str_to_title(detalhes_cli$Produto)
    # 
    # detalhes_cli <- detalhes_cli %>%
    #   mutate(TIPO_COBRANCA = case_when(
    #     TIPO_COBRANCA == 1 ~ "A vista",
    #     TIPO_COBRANCA == 3 ~ "Comodato",
    #     TIPO_COBRANCA == 4 ~ "Boleto",
    #     TIPO_COBRANCA == 5 ~ "Comodato",
    #     TIPO_COBRANCA == 8 ~ "Cartão",
    #     TRUE ~ NA_character_
    #   ))
    
    showModal(
      modalDialog(
        class = "modal_cli_inad_ped",
        
        htmltools::tags$div(
          style = "display: flex; justify-content: center;", 
          reactable(
            detalhes_cli,
            columns = list(
              CEV = colDef(name = "Cev"),
              DT = colDef(name = "Emissão", format = colFormat(date = TRUE,locales = "pt-BR")),
              Produto = colDef(width = 180),
              VENC = colDef(name = "Vencimento", format = colFormat(date = TRUE,locales = "pt-BR"))
            ),
            defaultColDef = colDef(align = "center"),
            defaultPageSize = 100,
            outlined = TRUE,
            wrap = FALSE,
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
          )
        ),
        easyClose = TRUE,
        footer = NULL,
        size = "s"
      )
    )
  })
  
  #### Solicitacao de clientes ----------
  
  socios <- reactiveVal(NULL) # salva os socios
  
  blocos_comod <- reactiveVal(0) # Contador de blocos
  
  dados_comodato_inad <- reactive({
    req(blocos_comod() > 0)
    
    do.call(rbind, lapply(seq_len(blocos_comod()), function(i) {
      
      # ignora blocos removidos
      if (is.null(input[[paste0("solic_prod_comod_input_", i)]])) return(NULL)
      
      if(is.null(input[[paste0("solic_matid_comod_input_", i)]])){
        id_mat = ""
      } else {
        id_mat = input[[paste0("solic_matid_comod_input_", i)]]
      }
      
      data.frame(
        Tipo        = input[[paste0("solic_tipo_comod_input_", i)]],
        Item        = paste(input[[paste0("solic_prod_comod_input_", i)]], id_mat, sep = " "),
        Quantidade  = input[[paste0("solic_qtd_comod_input_", i)]],
        Valor       = input[[paste0("solic_comod_valor_input_", i)]],
        Prazo       = input[[paste0("solic_prazo_comod_input_", i)]],
        TabRef      = input[[paste0("solic_comod_tbprd_input_", i)]],
        stringsAsFactors = FALSE
      )
    }))
  })
  
  ### Limpar arquivo da documentacao ---------------------------------------
  
  tem_arquivo = reactiveVal(FALSE)
  
  
  observeEvent(input$extrai_doc_input,{
    req(input$button_comod_inad)
    
    shinyjs::disable("bt_envia_solic_comod")
    shinyjs::disable("bt_cancel_solic_comod")
    
    hideFeedback("solic_comod_user_input")
    hideFeedback("solic_comod_cnpj_input")
    
    # notif_doc_comod = showNotification("Extraindo informações...",duration = 0, type = "warning", closeButton = FALSE)
    shinyalert(
      title = "Aguarde...",
      text = "Verificando dados da documentação.",
      size = "s",
      type = "info",
      closeOnEsc = TRUE,
      closeOnClickOutside = TRUE,
      showConfirmButton = FALSE,
      confirmButtonText = "OK",
      confirmButtonCol = cores_reativo()[2],
      animation = TRUE
    )
    
    dado_doc = extrair_doc(input$extrai_doc_input$datapath)
    
    nome_doc = dado_doc$nome_completo
    numr_doc = dado_doc$cpf
    # print(nome_doc)
    # print(numr_doc)
    ## Verifica se tem arquivo carregado
    tem_arquivo(TRUE)
    
    # numr_doc = "00000000000000"
    # print(nome_doc)
    
    
    if(isTRUE(dado_doc$api_offline)){

      ## API de extracao fora do ar -> libera confirmacao imediata
      aproximacao = 0

    } else if(unique(filtro_solic_comod_geral()$CGC_CPF[input$button_comod_inad$row]) == "CNPJ" && !is.null(socios())){

      aproximacao_control = stringdist(nome_doc, toupper(trimws(unique(filtro_solic_comod_geral()$PROPRIETARIO[input$button_comod_inad$row]))), method = "jw")

      if(any(aproximacao_control < 0.5,na.rm = TRUE)){
        
        aproximacao = stringdist(nome_doc, socios(), method = "jw")
        
      } else{

        if(any(aproximacao_control < 0.5,na.rm = TRUE)){
          aproximacao = stringdist(nome_doc, toupper(trimws(unique(filtro_solic_comod_geral()$PROPRIETARIO[input$button_comod_inad$row]))), method = "jw")

        } else{
          aproximacao = 1
        }
        
        
      }
      
    } else{
      
      aproximacao = stringdist(numr_doc, unique(filtro_solic_comod_geral()$CHAVE[input$button_comod_inad$row]), method = "jw")
    }
    
    
    
    
    # print(unique(filtro_solic_comod_geral()$CHAVE[input$button_comod_inad$row]))
    # removeNotification(notif_doc_comod)
    
    closeAlert(1)
    
    if(any(aproximacao < 0.5,na.rm = TRUE)){
      # print("Compatível")
      
      if(unique(filtro_solic_comod_geral()$CGC_CPF[input$button_comod_inad$row]) == "CNPJ" && !is.null(socios())){
        
        showFeedbackSuccess("solic_comod_user_input","Compatível")
        shinyalert(
          title = "Tudo certo!",
          text = "Dados verificados com sucesso.",
          size = "s",
          type = "success",
          closeOnEsc = TRUE,
          closeOnClickOutside = TRUE,
          showConfirmButton = TRUE,
          confirmButtonText = "OK",
          confirmButtonCol = cores_reativo()[2],
          animation = TRUE,
          timer = 3000
        )
      } else{
        showFeedbackSuccess("solic_comod_cnpj_input","Compatível")
        shinyalert(
          title = "Tudo certo!",
          text = "Dados verificados com sucesso.",
          size = "s",
          type = "success",
          closeOnEsc = TRUE,
          closeOnClickOutside = TRUE,
          showConfirmButton = TRUE,
          confirmButtonText = "OK",
          confirmButtonCol = cores_reativo()[2],
          animation = TRUE,
          timer = 3000
        )
      }
      
      shinyjs::enable("bt_envia_solic_comod")
      shinyjs::enable("bt_cancel_solic_comod")
    } else{
      # print("Não Compatível")
      
      if(unique(filtro_solic_comod_geral()$CGC_CPF[input$button_comod_inad$row]) == "CNPJ"){
        showFeedbackDanger("solic_comod_user_input","Dados não compatíveis")
        shinyalert(
          title = "Algo aconteceu!",
          text = "Os dados não batem com a receita federal ou control.",
          size = "s",
          type = "error",
          closeOnEsc = TRUE,
          closeOnClickOutside = TRUE,
          showConfirmButton = TRUE,
          confirmButtonText = "OK",
          confirmButtonCol = cores_reativo()[2],
          animation = TRUE,
          timer = 3000
        )
      } else{
        showFeedbackDanger("solic_comod_cnpj_input","Dados não compatíveis")
        shinyalert(
          title = "Algo aconteceu!",
          text = "Os dados não batem com a receita federal ou control.",
          size = "s",
          type = "error",
          closeOnEsc = TRUE,
          closeOnClickOutside = TRUE,
          showConfirmButton = TRUE,
          confirmButtonText = "OK",
          confirmButtonCol = cores_reativo()[2],
          animation = TRUE,
          timer = 3000
        )
      }
      
      shinyjs::enable("bt_cancel_solic_comod")
    }
  }, ignoreInit = TRUE)
  
  

  ## Modal de solicitacao ----------------------------------------------------

  
  observeEvent(input$button_comod_inad,{
    req(input$button_comod_inad)
    
    ## Sempre que abrir o modal, ele reseta a variavel 'tem_arquivo' menos para alguns marcados anteriormente
    
    tem_arquivo(filtro_solic_comod_geral()$SEM_DOC[input$button_comod_inad$row])
    
    if(filtro_solic_comod_geral()$Solicitacao[input$button_comod_inad$row] %in% c("\u2795")){
      # listagem_produtos = produtos_filtrados()$CODPROD
      
      blocos_comod(0)     # reseta contador
      removeUI(selector = "#container_blocos_comod > *", immediate = TRUE)
      
      if(unique(filtro_solic_comod_geral()$CGC_CPF[input$button_comod_inad$row]) == "CNPJ"){
        socios(dados_cnpj(unique(filtro_solic_comod_geral()$CHAVE[input$button_comod_inad$row])))
      } else{
        socios(NULL)
      }
      
      # print(socios)
      
      showModal(
        modalDialog(
          title = tags$div("Solicitar comodato", style = glue("color: {cores_reativo()[1]}")),
          size = "xl",
          fluidRow(
            column(9,
                   fluidRow(
                     column(4,
                            textInput("solic_comod_user_input",label = "Razão Social:",value = unique(filtro_solic_comod_geral()$NOME[input$button_comod_inad$row]), width = "100%") %>%
                              tagAppendAttributes(style = "pointer-events: none;")
                     ),
                     column(4, 
                            textInput("solic_comod_cnpj_input",label = "CNPJ/CPF:",value = unique(filtro_solic_comod_geral()$CHAVE[input$button_comod_inad$row]), width = "100%") %>%
                              tagAppendAttributes(style = "pointer-events: none;")
                     ),
                     column(4,
                            fileInput(
                              "extrai_doc_input",
                              "Verificar documento:",
                              placeholder = "Sem documento",
                              buttonLabel = "Enviar",
                              accept = c( ".jpeg", ".png", ".webp", ".pdf", "image/*"),
                              capture = "environment"
                            )
                     )
                   ),
                   textInput("solic_comod_resp_input",label = "Usuário:",value = str_to_title(paste0(strsplit(session$userData$usuario,"\\.")[[1]],collapse = " ")), width = "100%") %>%
                     tagAppendAttributes(style = "pointer-events: none;"),
                   # fluidRow(
                   #   column(2,
                   #          pickerInput("solic_tipo_comod_input", label = "Tipo", choices = c("Material", "Vasilhame"), options = opcoes_filtro)
                   #          ),
                   #   column(2,
                   #          pickerInput("solic_prod_comod_input", label = "Item", choices = listagem_produtos, options = opcoes_filtro)
                   #          ),
                   #   column(2,
                   #          numericInput("solic_qtd_comod_input",label = "Quantidade",value = 0)
                   #          ),
                   #   column(2,
                   #          textInput("solic_comod_valor_input",label = "Valor Und:",
                   #                    value = "",
                   #                    width = "100%") %>%
                   #            tagAppendAttributes(style = "pointer-events: none;")
                   #          ),
                   #   column(2,
                   #          pickerInput("solic_prazo_comod_input", label = "Prazo", choices = c("1 ano", "30 dias"), options = opcoes_filtro)
                   #   ),
                   #   column(2,
                   #          textInput("solic_comod_tbprd_input",label = "Tab Ref:",
                   #                    value = "",
                   #                    width = "100%") %>%
                   #            tagAppendAttributes(style = "pointer-events: none;")
                   #   )
                   #        ),
                   div(id = "container_blocos_comod"),
                   actionButton("add_comod_block", "Adicionar item", class = "btn btn-secondary"),
                   
                   fluidRow(
                     column(3,
                            airDatepickerInput(
                              readonly = TRUE,
                              inputId = "data_conf_comod_solic",
                              label = "Data da solicitação:", 
                              value = Sys.Date(),
                              dateFormat = "dd/MM/yyyy",
                              language = "pt-BR", 
                              width = "100%"
                            )),
                     column(9)
                   ),
                   br(), br(), br(), br(), br(),
                   fluidRow(
                     column(6,
                            align = "right",
                            actionBttn("bt_envia_solic_comod", label = "Solicitar",style = "material-flat", color = "success")
                     ),
                     column(6,
                            align = "left",
                            actionBttn("bt_cancel_solic_comod", label = "Cancelar",style = "material-flat", color = "danger")
                     )
                   )
            ),
            column(3,
                   tags$img(src = "acomp_log_www/img/comodato_capa.svg", width = "100%"))
          ),
          easyClose = FALSE,
          footer = NULL
        )
      )
      
      
      # observeEvent(input$solic_prod_comod_input, {
      #   req(input$solic_prod_comod_input)
      #   
      #   valor <- produtos_filtrados()$PRECO[
      #     produtos_filtrados()$CODPROD == input$solic_prod_comod_input
      #   ]
      #   
      #   tab_ref = produtos_filtrados()$TAB_CEV[
      #     produtos_filtrados()$CODPROD == input$solic_prod_comod_input
      #   ]
      #   
      #   updateTextInput(session, "solic_comod_valor_input", value = valor)
      #   updateTextInput(session, "solic_comod_tbprd_input", value = tab_ref)
      # })
      
      # observe({
      #   lapply(seq_len(blocos_comod()), function(i) {
      #     prod_id <- paste0("solic_prod_comod_input_", i)
      #     valor_id <- paste0("solic_comod_valor_input_", i)
      #     tab_id <- paste0("solic_comod_tbprd_input_", i)
      #     
      #     observeEvent(input[[prod_id]], ignoreInit = TRUE, {
      #       valor <- produtos_filtrados()$PRECO[
      #         produtos_filtrados()$CODPROD == input[[prod_id]]
      #       ]
      #       tab_ref <- produtos_filtrados()$TAB_CEV[
      #         produtos_filtrados()$CODPROD == input[[prod_id]]
      #       ]
      #       
      #       updateTextInput(session, valor_id, value = valor)
      #       updateTextInput(session, tab_id, value = tab_ref)
      #     })
      #   })
      # })
      
    }
    else{
      
      mensagens <- c()
      
      # condição status cad
      if(filtro_solic_comod_geral()$`Status Cad`[input$button_comod_inad$row] == "Bloqueado"){
        dados_faltantes <- c()

        if(is.na(filtro_solic_comod_geral()$PROPRIETARIO[input$button_comod_inad$row]) ||
           trimws(filtro_solic_comod_geral()$PROPRIETARIO[input$button_comod_inad$row]) == ""){
          dados_faltantes <- c(dados_faltantes, "nome do responsável")
        }

        if(is.na(filtro_solic_comod_geral()$CPF_PROP[input$button_comod_inad$row]) ||
           filtro_solic_comod_geral()$CPF_PROP[input$button_comod_inad$row] == 0){
          dados_faltantes <- c(dados_faltantes, "CPF do responsável")
        }

        if(is.na(filtro_solic_comod_geral()$FONE[input$button_comod_inad$row]) ||
           filtro_solic_comod_geral()$FONE[input$button_comod_inad$row] == 0){
          dados_faltantes <- c(dados_faltantes, "telefone do responsável")
        }

        if(is.na(filtro_solic_comod_geral()$EMAIL_PROP[input$button_comod_inad$row]) ||
           trimws(filtro_solic_comod_geral()$EMAIL_PROP[input$button_comod_inad$row]) == ""){
          dados_faltantes <- c(dados_faltantes, "e-mail do responsável")
        }

        mensagens <- c(mensagens, paste0("não possui no control: ", paste(dados_faltantes, collapse = ", ")))
      }
      
      # condição status cev
      if(filtro_solic_comod_geral()$`Status CEV`[input$button_comod_inad$row] != "Disponível"){
        mensagens <- c(mensagens, "Já possui comodato ativo")
      }
      
      # condição documentos
      if(is.na(filtro_solic_comod_geral()$`Status Doc`[input$button_comod_inad$row])){
        mensagens <- c(mensagens, "Precisa revisar a documentação enviada. (Sem assinatura do cliente e/ou canhoto auditado.)")
      }
      
      # condição Vasilhame/material
      if(!is.na(filtro_solic_comod_geral()$`Prazos Esgotados`[input$button_comod_inad$row])){
        mensagens <- c(mensagens, "Está bloqueado por que a revenda possui inadimplências com CEV's antigos.")
      } 
      
      if(filtro_solic_comod_geral()$`Status Tit`[input$button_comod_inad$row] != "Disponível"){
        mensagens <- c(mensagens, paste0("Possui título(s) em aberto."))
      }
      
      text <- glue::glue(
        "O cliente {filtro_solic_comod_geral()$NOME[input$button_comod_inad$row]} {paste(mensagens, collapse='; <br><br>')}"
      )
      
      shinyalert(
        title = "Aviso",
        text = HTML(text),
        size = "s", 
        closeOnEsc = TRUE,
        closeOnClickOutside = TRUE,
        html = TRUE,
        type = "warning",
        showConfirmButton = FALSE,
        showCancelButton = FALSE,
        timer = 0,
        imageUrl = "",
        animation = TRUE
      )
    }
  })
  
  ##### Cancelar solicitacao ----------
  observeEvent(input$bt_cancel_solic_comod,{
    removeModal()
    blocos_comod(0)     # reseta contador
    removeUI(selector = "#container_blocos_comod > *", immediate = TRUE)
  })
  
  ##### Adicionar mais inputs ----------
  observeEvent(input$add_comod_block, {
    
    if (is.null(produtos_filtrados()) || nrow(produtos_filtrados()) == 0) {
      
      shinyalert(
        title = "Nenhum produto em estoque",
        # text = "Ocorreu um erro ao tentar enviar o pedido. Tente novamente mais tarde.",
        size = "xs",
        type = "error",
        closeOnEsc = TRUE,
        closeOnClickOutside = TRUE,
        showConfirmButton = FALSE,
        confirmButtonText = "OK",
        confirmButtonCol = cores_reativo()[2],
        animation = TRUE
      )
      
    } else{ 
      
      i <- blocos_comod() + 1
      blocos_comod(i)
      
      insertUI(
        selector = "#container_blocos_comod",
        where = "beforeEnd",
        ui = bloco_comod_ui(i)
      )
      
      
      # Atualiza os dados da tabref e preco
      lapply(seq_len(blocos_comod()), function(i) {
        prod_id <- paste0("solic_prod_comod_input_", i)
        valor_id <- paste0("solic_comod_valor_input_", i)
        tab_id <- paste0("solic_comod_tbprd_input_", i)
        
        observeEvent(input[[prod_id]], ignoreInit = TRUE, {
          
          ## Vai bloquear caso o produto esteja bloqueado no status dlp
          if(produtos_filtrados()$STATUS_DLP[produtos_filtrados()$CODPROD == input[[prod_id]]] == "Bloqueado" &
             !is.na(produtos_filtrados()$STATUS_DLP[produtos_filtrados()$CODPROD == input[[prod_id]]])){
            showFeedbackDanger(prod_id, text = "Sem saldo.")
            shinyjs::disable("bt_envia_solic_comod")
          } else{
            hideFeedback(prod_id)
            shinyjs::enable("bt_envia_solic_comod")
          }
          ##
          
          valor <- produtos_filtrados()$PRECO[
            produtos_filtrados()$CODPROD == input[[prod_id]]
          ]
          tab_ref <- produtos_filtrados()$TAB_CEV[
            produtos_filtrados()$CODPROD == input[[prod_id]]
          ]
          
          updateTextInput(session, valor_id, value = valor)
          updateTextInput(session, tab_id, value = tab_ref)
        })
      })
      
      #### Escolhas pra prazo --------------------------------------------
      observeEvent(input[[paste0("solic_tipo_comod_input_", i)]], {
        
        tipo_id <- input[[paste0("solic_tipo_comod_input_", i)]]
        prod_id <- paste0("solic_prod_comod_input_", i)
        prazo_id <- paste0("solic_prazo_comod_input_", i)
        
        if (tipo_id == "Material") {
          novos_choices <- c("1 ano", "30 dias")
        } else if (tipo_id == "Vasilhame") {
          novos_choices <- c("1 ano", "30 dias")
        } else {
          novos_choices = ""
        }
        
        if (tipo_id %in% c("Material", "Vasilhame")){
          updatePickerInput(
            session,
            inputId = prod_id,
            choices = produtos_filtrados()$CODPROD[
              produtos_filtrados()$TIPO == tipo_id & !is.na(produtos_filtrados()$CODPROD)
            ],
            selected = produtos_filtrados()$CODPROD[
              produtos_filtrados()$TIPO == tipo_id & !is.na(produtos_filtrados()$CODPROD)
            ][1]
          )
        } else {
          updatePickerInput(
            session,
            inputId = prod_id,
            choices = "",
            selected = FALSE
          )
        }
        
        updatePickerInput(
          session,
          inputId = prazo_id,
          choices = novos_choices,
          selected = novos_choices[1]
        )
      })
      
      # observeEvent(input[[paste0("remove_comod_block_", i)]], {
      #   removeUI(
      #     selector = paste0("#bloco_comod_", i), 
      #     immediate = TRUE
      #   )
      #   blocos_comod(blocos_comod() - 1)
      # }, ignoreInit = TRUE, once = TRUE)
      
    }
    
  })
  
  
  bloco_comod_ui <- function(i) {
    listagem_produtos = produtos_filtrados()$CODPROD
    
    fluidRow(
      id = paste0("bloco_comod_", i),
      column(2,
             pickerInput(paste0("solic_tipo_comod_input_", i), "Tipo",
                         choices = c("Material", "Vasilhame"),
                         selected = "",
                         options = pickerOptions(
                           title = "Tipo",
                           size = 5,
                           style = "btn-color",
                           container = "body"
                         ))
      ),
      column(2,
             pickerInput(paste0("solic_prod_comod_input_", i), "Item",
                         choices = listagem_produtos,
                         selected = FALSE,
                         options = opcoes_filtro)
      ),
      column(2,
             textInput(paste0("solic_matid_comod_input_", i), "Id Prod",placeholder = "Identificador")
      ),
      column(2,
             numericInput(paste0("solic_qtd_comod_input_", i), "Qtd", value = 1,min = 1)
      ),
      column(2,
             pickerInput(paste0("solic_prazo_comod_input_", i), "Prazo",
                         choices = "",
                         selected = FALSE,
                         options = pickerOptions(
                           title = "Prazo",
                           size = 5,
                           style = "btn-color",
                           container = "body"
                         ))
      ),
      # column(
      #   1,
      #   div(
      #     style = "display:flex; height:93%; align-items:center; justify-content:center;",
      #     actionButton(paste0("remove_comod_block_", i), "\u274C",
      #                  class = "btn btn-danger btn-sm w-100")
      #   )
      # ),
      column(2,
             column(10,
                    textInput(paste0("solic_comod_valor_input_", i), "Valor:", value = "") %>%
                      tagAppendAttributes(readonly = "readonly", style = "pointer-events: none;")
                    
             ),
             column(2,
                    textInput(paste0("solic_comod_tbprd_input_", i),label = NULL, value = "") %>%
                      tagAppendAttributes(style = "pointer-events: none;"),
                    style = "visibility: hidden;"
             )
      )
      
    )
    
  }
  
  
  #### Add pedido, deletar e Gerar pdf ---------------------------------------------------------------
  
  ##### Enviar ------------
  observeEvent(input$button_env_ped_comod,{
    req(input$button_env_ped_comod)
    
    # print(comod_pedidos() %>%
    #                 filter(DATA == format(as.Date(input$button_env_ped_comod$data, format = "%Y-%m-%d"), "%Y%m%d"),
    #                        CLIENTE == input$button_env_ped_comod$cliente,
    #                        TIPO == input$button_env_ped_comod$tipo))
    
    # notif_ped_comod = showNotification("Enviando pedido para o sistema",duration = 0, type = "warning", closeButton = FALSE)
    
    shinyalert(
      title = "Aguarde...",
      text = "Enviando pedido para o sistema.",
      size = "s",
      type = "info",
      closeOnEsc = FALSE,
      closeOnClickOutside = FALSE,
      showConfirmButton = FALSE,
      confirmButtonText = "OK",
      confirmButtonCol = cores_reativo()[2],
      animation = TRUE
    )
    
    pedido_gerado <- try({
      gerar_pedido(
        comod_pedidos() %>%
          filter(DATA == format(as.Date(input$button_env_ped_comod$data, format = "%Y-%m-%d"), "%Y%m%d"),
                 CLIENTE == input$button_env_ped_comod$cliente,
                 TIPO == input$button_env_ped_comod$tipo,
                 PRAZO == input$button_env_ped_comod$prazo)
      )
    }, silent = TRUE)  # evita mostrar erro no console
    
    # removeNotification(notif_ped_comod)
    closeAlert(1)
    
    if (inherits(pedido_gerado, "try-error")) {
      shinyalert(
        title = "Erro ao enviar solicitação",
        text = "Ocorreu um erro ao tentar enviar o pedido. Tente novamente mais tarde.",
        size = "xs",
        type = "error",
        closeOnEsc = TRUE,
        closeOnClickOutside = TRUE,
        showConfirmButton = FALSE,
        confirmButtonText = "OK",
        confirmButtonCol = cores_reativo()[2],
        animation = TRUE
      )
      
    }
    
    else if(pedido_gerado == "consta"){
      
      shinyalert(
        title = "Solicitação já enviada",
        text = "",
        size = "xs",
        closeOnEsc = TRUE,
        closeOnClickOutside = TRUE,
        type = "warning",
        showConfirmButton = FALSE,
        confirmButtonText = "OK",
        confirmButtonCol = cores_reativo()[2],
        animation = TRUE
      )
    }
    else{
      refresh_solic(refresh_solic() + 1)
      
      shinyalert(
        title = "Solicitação enviada",
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
    }
  })
  
  ##### Deletar ------------ 
  observeEvent(input$button, {
    if(input$button$column == "Cancelar solicitação" & session$userData$usuario %in% responsaveis()){
      retira_comodato(comod_pedidos()$REVENDA[input$button$row],
                      comod_pedidos()$CLIENTE[input$button$row],
                      comod_pedidos()$PRODUTO[input$button$row],
                      comod_pedidos()$DATA[input$button$row],
                      comod_pedidos()$TIPO[input$button$row],
                      comod_pedidos()$PRAZO[input$button$row]
      )
      
      refresh_solic(refresh_solic() + 1)
      
      showNotification("Produto retirado",duration = 3, type = "warning", closeButton = TRUE)
    }
  })
  
  ##### PDF ------------
  observeEvent(input$button_group_sol, {
    req(input$button_group_sol)
    if(input$button_group_sol$value %in% c("\U0001F4BE") & session$userData$usuario %in% poder_total_comodato){
      
      gerar_pdf(
        # comod_pedidos()$USUARIO[input$button_comod_solic$row],
        unique(comod_pedidos()$CLIENTE[comod_pedidos()$CLIENTE == input$button_group_sol$cliente]),
        # comod_pedidos()$PRODUTO[comod_pedidos()$PRODUTO == input$button_group_sol$cliente],
        # comod_pedidos()$QTD[comod_pedidos()$QTD == input$button_group_sol$cliente],
        unique(comod_pedidos()$REVENDA[comod_pedidos()$CLIENTE == input$button_group_sol$cliente]),
        unique(comod_pedidos()$ENDERECO[comod_pedidos()$CLIENTE == input$button_group_sol$cliente]),
        unique(comod_pedidos()$CONTATO[comod_pedidos()$CLIENTE == input$button_group_sol$cliente]),
        unique(comod_pedidos()$PTO_REF[comod_pedidos()$CLIENTE == input$button_group_sol$cliente]),
        unique(comod_pedidos()$DIA_VISIT[comod_pedidos()$CLIENTE == input$button_group_sol$cliente]),
        unique(comod_pedidos()$SEQ[comod_pedidos()$CLIENTE == input$button_group_sol$cliente]),
        unique(comod_pedidos()$CEP[comod_pedidos()$CLIENTE == input$button_group_sol$cliente]),
        unique(comod_pedidos()$FONE[comod_pedidos()$CLIENTE == input$button_group_sol$cliente]),
        unique(comod_pedidos()$CNPJ[comod_pedidos()$CLIENTE == input$button_group_sol$cliente]),
        unique(comod_pedidos()$VEN[comod_pedidos()$CLIENTE == input$button_group_sol$cliente]),
        comod_pedidos()[comod_pedidos()$CLIENTE == input$button_group_sol$cliente,] %>%
          filter(DATA == format(as.Date(input$button_group_sol$data, format = "%Y-%m-%d"), "%Y%m%d"))
      )
      
      
      runjs("document.getElementById('bt_download_pdf_comod').click();")
    }
  })
  
  output$bt_download_pdf_comod <- downloadHandler(
    
    filename = function() { paste0("CEV_",comod_pedidos()$CLIENTE[comod_pedidos()$CLIENTE == input$button_group_sol$cliente], Sys.Date(), ".pdf") },
    content = function(file) {
      file.copy(glue("{diretorio}pages/Comodatos/Dados/Contrato_CEV.pdf"), file)
    }
  )
  
  #### Sincronizar cliente com control --------------------------------------------------
  
  observeEvent(input$button_comod_sinc,{
    req(input$button_comod_sinc)
    
    
    # if(filtro_solic_comod_geral()$`Status Cad`[input$button_comod_sinc$row] != "Disponível"){
    if(!is.null(filtro_solic_comod_geral()$`Status Cad`[input$button_comod_sinc$row])){
      
      notif_verifica_cadcli = showNotification("Acessando o sistema",duration = 0, type = "warning", closeButton = FALSE)
      
      
      
      verificacao <- try({
        verifica_cadcli(filtro_solic_comod_geral()$REVENDA[input$button_comod_sinc$row], 
                        filtro_solic_comod_geral()$Cliente[input$button_comod_sinc$row])
      }, silent = TRUE)  # evita mostrar erro no console
      
      removeNotification(notif_verifica_cadcli)
      
      if (inherits(verificacao, "try-error")) {
        shinyalert(
          title = "Erro ao sincronizar",
          text = "Ocorreu ao sincronizar o cliente. Tente novamente mais tarde.",
          size = "xs",
          type = "error",
          closeOnEsc = TRUE,
          closeOnClickOutside = TRUE,
          showConfirmButton = FALSE,
          confirmButtonText = "OK",
          confirmButtonCol = cores_reativo()[2],
          animation = TRUE
        )
        
      }
      
      else{
        
        shinyalert(
          title = "Sincronização realizada",
          text = "Recarregue a página para ver os dados atualizados",
          size = "xs",
          closeOnEsc = TRUE,
          closeOnClickOutside = TRUE,
          type = "success",
          showConfirmButton = FALSE,
          confirmButtonText = "OK",
          confirmButtonCol = cores_reativo()[2],
          animation = TRUE
        )
      }
      
    }
    
    
  })
  
  #### Solicitar comodato ---------------------------------------------------------------
  
  observeEvent(input$bt_envia_solic_comod,{
    # req(input$button_comod_inad) ## Testar pra ver se é essa reatividade que acaba duplicando alguns casos
    shinyjs::disable("bt_envia_solic_comod")  # bloqueia imediatamente
    req(dados_comodato_inad())
    req(tem_arquivo())
    
    # req(input$solic_prod_comod_input)
    
    # codigo_produto = produtos_filtrados()$CODCOMP[
    #   produtos_filtrados()$CODPROD == dados_comodato_inad()$Item
    # ]
    # unidade_produto = produtos_filtrados()$UNIDADE[
    #   produtos_filtrados()$CODPROD == dados_comodato_inad()$Item
    # ]
    
    
    # print(dados_comodato_inad())
    
    if(all(nchar(as.character(dados_comodato_inad()$Tipo)) >= 2, na.rm = TRUE) && 
       all(nchar(as.character(dados_comodato_inad()$Prazo)) >= 2, na.rm = TRUE) && 
       all(nchar(as.character(dados_comodato_inad()$Valor)) >= 1,na.rm = TRUE)){
      
      # prod_info <- left_join(dados_comodato_inad(), produtos_filtrados(), by = c("Item" = "CODPROD"))
      # prod_info <- left_join(
      #   dados_comodato_inad() %>%
      #     mutate(Item = trimws(gsub("\\s\\d+$", "", Item))),
      #   produtos_filtrados(), by = c("Item" = "CODPROD"))
      
      prod_info <- left_join(
        dados_comodato_inad() %>%
          mutate(CODRED_JOIN = sub("^([0-9]+).*", "\\1", Item)),
        
        produtos_filtrados() %>%
          mutate(CODRED_JOIN = sub("^([0-9]+).*", "\\1", CODPROD)),
        
        by = "CODRED_JOIN"
      )
      prod_info <- prod_info %>% select(-CODRED_JOIN)
      
      
      codigo_produto  <- prod_info$CODCOMP
      unidade_produto <- prod_info$UNIDADE
      
      if(is.null(codigo_produto) && is.null(unidade_produto)){
        shinyalert(
          title = "Aviso",
          text = "Ocorreu um erro ao carregar os produtos! Recarregue a página e solicite novamente.",
          size = "xs",
          closeOnEsc = FALSE,
          closeOnClickOutside = FALSE,
          type = "warning",
          showConfirmButton = FALSE,
          confirmButtonText = "OK",
          confirmButtonCol = cores_reativo()[2],
          animation = TRUE
        )
      } else{
        
        solicita_comodato(
          paste0(unique(filtro_solic_comod_geral()$CODCLI[input$button_comod_inad$row])," - ",unique(filtro_solic_comod_geral()$NOME[input$button_comod_inad$row])),
          str_to_title(paste0(strsplit(session$userData$usuario,"\\.")[[1]],collapse = " ")),
          # input$solic_prod_comod_input,
          # codigo_produto,
          # unidade_produto,
          # input$solic_qtd_comod_input,
          # input$solic_comod_valor_input,
          # input$solic_comod_tbprd_input,
          dados_comodato_inad()$Item,
          codigo_produto,
          unidade_produto,
          dados_comodato_inad()$Quantidade,
          dados_comodato_inad()$Valor,
          dados_comodato_inad()$TabRef,
          unique(filtro_solic_comod_geral()$REVENDA[input$button_comod_inad$row]),
          unique(filtro_solic_comod_geral()$ENDERECO[input$button_comod_inad$row]),
          unique(filtro_solic_comod_geral()$CONTATO[input$button_comod_inad$row]),
          unique(filtro_solic_comod_geral()$PTO_REF[input$button_comod_inad$row]),
          unique(filtro_solic_comod_geral()$DIA_VISIT[input$button_comod_inad$row]),
          unique(filtro_solic_comod_geral()$SEQ[input$button_comod_inad$row]),
          unique(filtro_solic_comod_geral()$CEP[input$button_comod_inad$row]),
          unique(filtro_solic_comod_geral()$FONE[input$button_comod_inad$row]),
          unique(filtro_solic_comod_geral()$CHAVE[input$button_comod_inad$row]),
          unique(filtro_solic_comod_geral()$VEN[input$button_comod_inad$row]),
          dados_comodato_inad()$Prazo,
          dados_comodato_inad()$Tipo
        )
        
        refresh_solic(refresh_solic() + 1)
        
        removeModal()
        showNotification("Solicitação enviada", duration = 3, type = "default",closeButton = TRUE)
      }
    } else {
      shinyjs::enable("bt_envia_solic_comod")  # reabilita só se der erro de validação
      shinyalert(
        title = "Aviso",
        text = "Verifique todos os campos!",
        size = "xs",
        closeOnEsc = TRUE,
        closeOnClickOutside = TRUE,
        type = "warning",
        showConfirmButton = FALSE,
        confirmButtonText = "OK",
        confirmButtonCol = cores_reativo()[2],
        animation = TRUE,
        timer = 5000
      )
    }
    
  })
  
  
  #### Atualiza ----------------------------------------------------------------
  
  
  observeEvent(input$bt_refresh_id_solicit_comodatos, {
    if(session$userData$usuario %in% poder_total_comodato){
      notif_atualiza <- showNotification("Atualizando dados, por favor aguarde...", 
                                         duration = NULL, type = "warning", closeButton = FALSE)
      
      # Construir os paths completos ANTES do future
      script1 <- glue("{diretorio}pages/Comodatos/Dados/atualiza_comodatos_bruto.R")
      script2 <- glue("{diretorio}pages/Comodatos/Dados/atualiza_comodato.R")
      
      future({
        tryCatch({
          source(script1, local = new.env())
          source(script2, local = new.env())
          TRUE
        }, error = function(e) {
          message("Erro na atualização: ", e$message)
          FALSE
        })
      }, seed = TRUE) %...>% (function(resultado) {
        removeNotification(notif_atualiza)
        
        if(isTRUE(resultado)) {
          shinyalert(
            title = "Atualização concluída",
            text = "Recarregue a página para mostrar os dados atualizados.",
            size = "xs", 
            closeOnEsc = FALSE,
            closeOnClickOutside = FALSE,
            type = "success",
            showConfirmButton = FALSE,
            confirmButtonCol = cores_reativo()[2],
            animation = TRUE
          )
        } else {
          shinyalert(
            title = "Erro de atualização",
            text = "Tente novamente mais tarde.",
            size = "xs", 
            closeOnEsc = TRUE,
            closeOnClickOutside = TRUE,
            type = "warning",
            showConfirmButton = FALSE,
            confirmButtonText = "OK",
            confirmButtonCol = cores_reativo()[2],
            animation = TRUE,
            timer = 3000
          )
        }
      }) %...!% (function(error) {
        removeNotification(notif_atualiza)
        
        shinyalert(
          title = "Erro de atualização",
          text = "Tente novamente mais tarde.",
          size = "xs", 
          closeOnEsc = TRUE,
          closeOnClickOutside = TRUE,
          type = "warning",
          showConfirmButton = FALSE,
          confirmButtonText = "OK",
          confirmButtonCol = cores_reativo()[2],
          animation = TRUE,
          timer = 3000
        )
      })
    }
  })
  
  ### Ajuda --------------------------------------------------------
  
  observeEvent(input$bt_guia_id_solicit_comodatos, {
    funcao_guia_comodato("Solicitacao")$init()$start()
  })
  
  ### Filtros --------------------------------------------------------
  opcoes_filtro = pickerOptions(
    noneSelectedText = "Todos",
    size = 5,
    style = "btn-color",
    countSelectedText = " {0} Itens",
    selectedTextFormat = "count > 1",
    container = "body", 
    liveSearch = TRUE
  )
  
  
  
  #### Demais config ------------------------------------------------
  filtro_solic_comod_geral = reactive({
    if((is.null(input$cli_solic_comod_input) || length(input$cli_solic_comod_input) == 0) &&
       (is.null(input$tip_solic_comod_input) || length(input$tip_solic_comod_input) == 0) &&
       (is.null(input$cid_solic_comod_input) || length(input$cid_solic_comod_input) == 0) &&
       (is.null(input$cla_solic_comod_input) || length(input$cla_solic_comod_input) == 0) &&
       (is.null(input$canal_solic_comod_input) || length(input$canal_solic_comod_input) == 0) &&
       (is.null(input$ven_solic_comod_input) || length(input$ven_solic_comod_input) == 0) &&
       (is.null(input$ga_solic_comod_input) || length(input$ga_solic_comod_input) == 0) &&
       (is.null(input$ceva_solic_comod_input) || length(input$ceva_solic_comod_input) == 0) &&
       (is.null(input$ina_solic_comod_input) || length(input$ina_solic_comod_input) == 0) &&
       (is.null(input$stdoc_solic_comod_input) || length(input$stdoc_solic_comod_input) == 0)){
      
      dados = clientes_inad_geral()
      dados$Cliente = paste0(dados$CODCLI," - ",dados$NOME)
      
      
    } else {
      
      dados = clientes_inad_geral()
      dados$Cliente = paste0(dados$CODCLI," - ",dados$NOME)
      dados = dados %>% 
        filter(
          if (is.null(input$cli_solic_comod_input) || length(input$cli_solic_comod_input) == 0) TRUE else Cliente %in% input$cli_solic_comod_input,
          if (is.null(input$tip_solic_comod_input) || length(input$tip_solic_comod_input) == 0) TRUE else CGC_CPF %in% input$tip_solic_comod_input,
          if (is.null(input$cid_solic_comod_input) || length(input$cid_solic_comod_input) == 0) TRUE else CIDADE %in% input$cid_solic_comod_input,
          if (is.null(input$cla_solic_comod_input) || length(input$cla_solic_comod_input) == 0) TRUE else PORTE %in% input$cla_solic_comod_input,
          if (is.null(input$canal_solic_comod_input) || length(input$canal_solic_comod_input) == 0) TRUE else CANAL %in% input$canal_solic_comod_input,
          if (is.null(input$ven_solic_comod_input) || length(input$ven_solic_comod_input) == 0) TRUE else VEN %in% input$ven_solic_comod_input,
          if (is.null(input$ga_solic_comod_input) || length(input$ga_solic_comod_input) == 0) TRUE else subordinacao %in% input$ga_solic_comod_input,
          if (is.null(input$ceva_solic_comod_input) || length(input$ceva_solic_comod_input) == 0) TRUE else CEV_PEN %in% input$ceva_solic_comod_input,
          if (is.null(input$stdoc_solic_comod_input) || length(input$stdoc_solic_comod_input) == 0) TRUE else `Status Doc` %in% input$stdoc_solic_comod_input,
          if (is.null(input$ina_solic_comod_input) || length(input$ina_solic_comod_input) == 0) TRUE else Inadimplente %in% input$ina_solic_comod_input
        )
      
      
    }
    
    dados
  })
  
  observeEvent(filtro_solic_comod_geral(), {
    
    # Atualiza apenas se não houver seleção
    if (is.null(input$stdoc_solic_comod_input) || length(input$stdoc_solic_comod_input) == 0) {
      updatePickerInput(session, "stdoc_solic_comod_input", choices = sort(unique(filtro_solic_comod_geral()$`Status Doc`)))
    }
    if (is.null(input$cli_solic_comod_input) || length(input$cli_solic_comod_input) == 0) {
      updatePickerInput(session, "cli_solic_comod_input", choices = sort(unique(filtro_solic_comod_geral()$Cliente)))
    }
    if (is.null(input$tip_solic_comod_input) || length(input$tip_solic_comod_input) == 0) {
      updatePickerInput(session, "tip_solic_comod_input", choices = sort(unique(filtro_solic_comod_geral()$CGC_CPF)))
    }
    if (is.null(input$cid_solic_comod_input) || length(input$cid_solic_comod_input) == 0) {
      updatePickerInput(session, "cid_solic_comod_input", choices = sort(unique(filtro_solic_comod_geral()$CIDADE)))
    }
    if (is.null(input$cla_solic_comod_input) || length(input$cla_solic_comod_input) == 0) {
      updatePickerInput(session, "cla_solic_comod_input", choices = sort(unique(filtro_solic_comod_geral()$PORTE)))
    }
    if (is.null(input$canal_solic_comod_input) || length(input$canal_solic_comod_input) == 0) {
      updatePickerInput(session, "canal_solic_comod_input", choices = sort(unique(filtro_solic_comod_geral()$CANAL)))
    }
    if (is.null(input$ven_solic_comod_input) || length(input$ven_solic_comod_input) == 0) {
      updatePickerInput(session, "ven_solic_comod_input", choices = sort(unique(filtro_solic_comod_geral()$VEN)))
    }
    if (is.null(input$ga_solic_comod_input) || length(input$ga_solic_comod_input) == 0) {
      updatePickerInput(session, "ga_solic_comod_input", choices = sort(unique(filtro_solic_comod_geral()$subordinacao)))
    }
    if (is.null(input$ceva_solic_comod_input) || length(input$ceva_solic_comod_input) == 0) {
      updatePickerInput(session, "ceva_solic_comod_input", choices = sort(unique(filtro_solic_comod_geral()$CEV_PEN)))
    }
    if (is.null(input$ina_solic_comod_input) || length(input$ina_solic_comod_input) == 0) {
      updatePickerInput(session, "ina_solic_comod_input", choices = sort(unique(filtro_solic_comod_geral()$Inadimplente)))
    }
  })
  # Tabela de clientes ------------------------------------------------------
  
  output$tabela_cli_solic_comodato = renderReactable({
    req(filtro_solic_comod_geral())
    
    clientes_inadimplentes_geral = filtro_solic_comod_geral()
    clientes_inadimplentes_geral$Detalhes = "\U0001F50D"
    clientes_inadimplentes_geral$`Status Cad` = ifelse(clientes_inadimplentes_geral$`Status Cad` == "Disponível", 
                                                       "\u21A9","\u21A9") 
    reactable(
      clientes_inadimplentes_geral %>% select(REVENDA, Cliente, FANTASIA, CGC_CPF,
                                              CIDADE, PORTE, CANAL, VEN, subordinacao,
                                              Inadimplente, `Status Doc`, Solicitacao,Detalhes, `Status Cad`, CHAVE_CLI, PROPRIETARIO),
      # clientes_inadimplentes_geral %>% select(REVENDA, Cliente, FANTASIA, CGC_CPF,
      #                                         CIDADE, PORTE, CANAL, VEN, subordinacao,
      #                                         Inadimplente, Solicitacao,Detalhes, `Status Cad`, CHAVE_CLI),
      defaultColDef = colDef(align = "left"),
      columns = list(
        .selection = colDef(show = FALSE),
        REVENDA = colDef(name = "Revenda", align = "left", show =
                           if(length(revenda_query()) == 0){
                             TRUE
                           }
                         else{
                           FALSE
                         }),
        CHAVE_CLI = colDef(show = FALSE),
        FANTASIA = colDef(name = "Fantasia",width = 130),
        VEN = colDef(name = "Ven",width = 80, align = "center"),
        CGC_CPF = colDef(name = "Tipo",width = 80),
        CIDADE = colDef(name = "Cidade"),
        PORTE = colDef(name = "Classificação"),
        Cliente = colDef(width = 130),
        CANAL = colDef(name = "Canal"),
        Titulos = colDef(show = FALSE),
        PROPRIETARIO = colDef(show = FALSE),
        subordinacao = colDef(name = "GA",width = 80, align = "center"),
        `Status Cad` = colDef(name = "Sincronizar", cell = button_extra("button_comod_sinc", class = "button_group_solic_cev"), align = "center"),
        Solicitacao = colDef(name = "Solicitação", cell = button_extra("button_comod_inad", class = "button_group_solic_cev"), align = "center"),
        Detalhes = colDef(cell = button_extra("button_det_comod_inad", class = "button_group_solic_cev"), align = "center"),
        Inadimplente = colDef(align = "center", style = function(value){
          if(value == "Sim"){
            list(color = "#A1343C", fontWeight = "bold")
          }
          else{
            list(color = "#008D21", fontWeight = "bold")
          }
        },headerStyle = list(display = "flex", alignItems = "center")),
        `Status Doc` = colDef(align = "center",
                              show = FALSE,
                              style = function(value){
                                if(value == "Bloqueado"){
                                  list(color = "#A1343C", fontWeight = "bold")
                                }
                                else{
                                  list(color = "#008D21", fontWeight = "bold")
                                }
                              },headerStyle = list(display = "flex", alignItems = "center"))
      ),
      wrap = FALSE,
      height = "58vh",
      resizable = TRUE,
      pagination = TRUE,
      defaultPageSize = 50,
      pageSizeOptions = c(50, 100, 500),
      showPageSizeOptions = TRUE,
      compact = TRUE,
      highlight = TRUE,
      selection = "single",
      onClick = "select",
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
        backgroundColor = "transparent",
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
    )
  })
  
  # Tabela de solicitações de comodato ------------------------------------------------------
  output$tabela_solicitacoes = renderReactable({
    req(comod_pedidos())
    
    comod_pedidos_novo = comod_pedidos() %>% select(REVENDA, CLIENTE, USUARIO, PRODUTO, QTD, TIPO, DATA, VENC, PRAZO, arquivo, PRE_PED)
    comod_pedidos_novo$DATA = as.Date(comod_pedidos_novo$DATA, "%Y%m%d")
    comod_pedidos_novo$VENC = as.Date(comod_pedidos_novo$VENC, "%Y%m%d")
    comod_pedidos_novo$`Cancelar solicitação` = ifelse(!is.na(comod_pedidos_novo$PRE_PED) & !is.null(comod_pedidos_novo$PRE_PED),"","\u274C")
    comod_pedidos_novo$Envio = rep("", nrow(comod_pedidos_novo))
    comod_pedidos_novo = comod_pedidos_novo[,c("REVENDA", "CLIENTE", "PRAZO", "TIPO", "USUARIO", "PRODUTO", "QTD", "DATA", "VENC", "Envio", "arquivo", "Cancelar solicitação", "PRE_PED")]
    
    reactable(
      comod_pedidos_novo,
      defaultColDef = colDef(align = "center"),
      columns = list(
        .selection = colDef(show = FALSE),
        REVENDA = colDef(name = "Revenda", aggregate = "unique", show =
                           if(length(revenda_query()) == 0){
                             TRUE
                           }
                         else{
                           FALSE
                         }),
        USUARIO = colDef(name = "Usuário"),
        CLIENTE = colDef(name = "Cliente", align = "left", minWidth = 180,
                         aggregate = JS("
                            function(values, rows) {
                              // Cria um Set para remover duplicados
                              var uniqueClients = Array.from(new Set(values));
                              return uniqueClients.length;
                            }
                          "),
                         format = list(aggregated = colFormat(prefix = "Clientes comodatários: "))),
        TIPO = colDef(name = "Tipo"),
        PRAZO = colDef(name = "Prazo"),
        QTD = colDef(name = "Quantidade", format = colFormat(separators = TRUE), aggregate = "sum"),
        PRODUTO = colDef(name = "Produto", minWidth = 150, aggregate = "count", format = list(aggregated = colFormat(prefix = "Itens solicitados: "))),
        DATA = colDef(name = "Emissão", format = colFormat(date = TRUE, locales = "pt-BR"), aggregate = "unique"),
        VENC = colDef(name = "Vencimento", format = colFormat(date = TRUE, locales = "pt-BR"), aggregate = "min"),
        `Cancelar solicitação` = colDef(
          name = "Retirar", 
          width = 85,
          show = ifelse(session$userData$usuario %in% responsaveis(), TRUE, FALSE),
          cell = button_extra("button", class = "bt_canc_solic_comod")),
        Envio = colDef(
          name = "Enviar",
          html = TRUE,
          show = ifelse(session$userData$usuario %in% responsaveis(), TRUE, FALSE),
          cell = function(value, index){
            return("")
          },
          aggregate = JS("
            function(values, rows) {
              // Obtém todos os clientes dentro do grupo atual
              var clientes = rows.map(r => r['CLIENTE']);
              var clientesUnicos = Array.from(new Set(clientes));
              
              var tipo_produto = rows.map(r => r['TIPO']);
              var tipo_produtoUnicos = Array.from(new Set(tipo_produto));
              
              var prazo = rows.map(r => r['PRAZO']);
              var prazo_produtoUnicos = Array.from(new Set(prazo));
              
              // Só mostra o botão se o grupo tiver 1 cliente
              if (clientesUnicos.length !== 1) {
                return '';
              }
          
              // Valor único do 'arquivo'
              var uniqueVal = Array.from(new Set(values))[0];
              var CLIENTE = clientesUnicos[0];
              var TIPO    = tipo_produtoUnicos[0];
              var PRAZO   = prazo_produtoUnicos[0];
          
              // Obtém a data (primeira única)
              var datas = rows.map(r => r['DATA']);
              var DATA = Array.from(new Set(datas))[0];
          
              // Cria o botão
              var btn = '<button class=\"button_com_env\" ' +
                        'title=\"Enviar para o sistema\" ' +
                        'onclick=\"Shiny.onInputChange(\\'button_env_ped_comod\\', {' +
                          'value: \\'' + uniqueVal + '\\',' +
                          'cliente: \\'' + CLIENTE + '\\',' +
                          'tipo: \\'' + TIPO + '\\',' +
                          'prazo: \\'' + PRAZO + '\\',' +
                          'data: \\'' + DATA + '\\',' +
                          'nonce: Math.random()' +
                        '})\">' +
                        '<img src=\\\"acomp_log_www/img/bt_envio_ped.svg\\\" width=\\\"20\\\" height=\\\"20\\\" style=\\\"vertical-align:middle;\\\">' +
                        '</button>';
          
              return btn;
            }
          ")
          
        ),
        # arquivo = colDef(name = "Contrato", cell = button_extra("button_comod_solic", class = "button_group_solic_contrato"))
        arquivo = colDef(
          name = "Contrato",
          html = TRUE,
          show = FALSE,
          cell = function(value, index){
            return("")
          },
          aggregate = JS("
            function(values, rows) {
              // Obtém todos os clientes dentro do grupo atual
              var clientes = rows.map(r => r['CLIENTE']);
              var clientesUnicos = Array.from(new Set(clientes));
          
              // Só mostra o botão se o grupo tiver 1 cliente
              if (clientesUnicos.length !== 1) {
                return('');
              }
          
              // Valor único do 'arquivo'
              var uniqueVal = Array.from(new Set(values))[0];
              var CLIENTE = clientesUnicos[0];
          
              // Obtém a data (primeira única)
              var datas = rows.map(r => r['DATA']);
              var DATA = Array.from(new Set(datas))[0];
          
              // Cria o botão
              var btn = '<button class=\"button_com_sol\" ' +
                        'title=\"Gerar contrato\" ' +
                        'onclick=\"Shiny.onInputChange(\\'button_group_sol\\', {' +
                          'value: \\'' + uniqueVal + '\\',' +
                          'cliente: \\'' + CLIENTE + '\\',' +
                          'data: \\'' + DATA + '\\',' +
                          'nonce: Math.random()' +
                        '})\">' +
                        '<img src=\\\"acomp_log_www/img/bt_pdf.svg\\\" width=\\\"20\\\" height=\\\"20\\\" style=\\\"vertical-align:middle;\\\">' +
                        '</button>';
          
              return btn;
            }
          ")
          
        ),
        PRE_PED = colDef(name = "Status",
                         cell = function(value){
                           if(!is.na(value) && !is.null(value)){
                             return(as.character(tags$span("\u2705", title = "Enviado")))
                           } else {
                             return("")
                           }
                         },
                         html = TRUE)
        
      ),
      groupBy = c("DATA", "CLIENTE", "PRAZO", "TIPO"),
      defaultSorted = "DATA",
      defaultSortOrder = "desc",
      wrap = FALSE,
      resizable = TRUE,
      height = "58vh",
      pagination = TRUE,
      defaultPageSize = 50,
      pageSizeOptions = c(50, 100, 500),
      showPageSizeOptions = TRUE,
      compact = TRUE,
      highlight = TRUE,
      selection = "single",
      onClick = "select",
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
        pageSizeOptionsLabel = "Linhas por página",
        noData = "Sem solicitações pendentes"
      ),
      style = list(overflowX = "auto"),
      theme = reactableTheme(
        backgroundColor = "transparent",
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
    )
  })
  
  
  # UI ----------------------------------------------------------------------

  tagList(
    tags$style(HTML("#bt_download_ui { display: none !important; }")),
    fluidRow(
    box(
      id = "box_comodatos_solic_filtro",
      title = fluidRow(
        column(1, pickerInput("cli_solic_comod_input", "Cliente", choices = sort(unique(clientes_inad_geral()$Cliente)), multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("tip_solic_comod_input", "Tipo", choices = sort(unique(clientes_inad_geral()$CGC_CPF)), multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("cid_solic_comod_input", "Cidade", choices = sort(unique(clientes_inad_geral()$CIDADE)), multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("cla_solic_comod_input", "Classificação", choices = sort(unique(clientes_inad_geral()$PORTE)), multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("canal_solic_comod_input", "Canal", choices = sort(unique(clientes_inad_geral()$CANAL)), multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("ven_solic_comod_input", "Vendedor", choices = sort(unique(clientes_inad_geral()$VEN)), multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("ga_solic_comod_input", "Gerente de Área", choices = sort(unique(clientes_inad_geral()$subordinacao)), multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("ghost6", "Ghost 2", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
        column(1, pickerInput("ceva_solic_comod_input", "Cev Ativo", choices = sort(unique(clientes_inad_geral()$CEV_PEN)), multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("ina_solic_comod_input", "Inadimplente", choices = sort(unique(clientes_inad_geral()$Inadimplente)), multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("stdoc_solic_comod_input", "Status Doc", choices = sort(unique(clientes_inad_geral()$`Status Doc`)), multiple = TRUE, options = opcoes_filtro)),
        column(1, style = "display: flex; align-items: center;",
               column(1),
               column(9, actionButton("bt_limpacomod_solic",label = NULL, icon = icon("eraser"),status = "primary",size = "lg",width = "100%") %>% tagAppendAttributes(title = "Limpar filtros")),
               column(1)
        )
        
      ),
      width = 12,
      status = "primary",
      collapsible = FALSE
    ),
    box(
      id = "tabela_cli_solic_comodatos",
      title = "Clientes",
      width = 12,
      withSpinner(reactableOutput("tabela_cli_solic_comodato"),type = 4,color = cores_reativo()[2])
    ),
    
    box(
      id = "tabela_comodatos_solcitados",
      title = "Solicitações",
      width = 12,
      withSpinner(reactableOutput("tabela_solicitacoes"),type = 4,color = cores_reativo()[2])
    ),
    
    downloadButton("bt_download_pdf_comod", style = "visibility: hidden; position:absolute; left:-9999px;")

  )
  )


}