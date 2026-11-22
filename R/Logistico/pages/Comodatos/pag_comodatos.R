library(promises)
library(future)

plan(sequential) # portfólio: no navegador não há outro processo para o future usar


# Carregar dados ----------------------------------------------------------

source(glue("{diretorio}pages/Comodatos/Dados/informa_comodato.R"), local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Comodatos/Dados/dados_comodato.R"), local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Comodatos/Dados/adiciona_pedido.R"), local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Comodatos/Dados/devolve_pedido.R"), local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Comodatos/Guia_ajuda.R"), local = TRUE, encoding = "UTF-8")

pag_comodatos = function(){
  
  
 
  # Server ------------------------------------------------------------------
  
   # responsaveis por solicitar
  
  responsaveis = reactive({
    c("visitante")  # Portfólio: no original, os logins de quem pode solicitar
  })


  # gatilho para refresh
  refresh_comod <- reactiveVal(0)
  
  # gatilho para os arquivos
  nao_tem_pdv = reactiveVal(NULL)
  nao_tem_cev = reactiveVal(NULL)
  nao_tem_can = reactiveVal(NULL)
  
  comodato_geral <- reactive({
    req(refresh_comod())
    
    if (length(revenda_query()) == 0){
      comod_geral()
    }
    # else if (str_detect(revenda_query(), "LOCADORA" ) | str_detect(revenda_query(), "ARRENDADORA") | str_detect(revenda_query(), "TRANSPORTADORA")) {
    #   devolucao_geral %>% filter(str_detect(toupper(EMPRESA), revenda_query()))
    # }
    else{
      # comod_geral() %>% filter(str_detect(toupper(CEV), revenda_query()))
      
      comod_geral(revenda_query()) %>% 
        # filter(str_detect(toupper(CEV), revenda_query())) %>% 
        mutate(CEV = str_extract(CEV, "(?<=- ).*"))
      
    }
    
  })
  
  # Botoes e filtros --------------------------------------------------------
  ### Botoes --------------------------------------------------------
  
  ### Ajuda --------------------------------------------------------
  
  observeEvent(input$bt_guia_id_comod_comodatos, {
    funcao_guia_comodato("Comodatos")$init()$start()
  })
  
  #### Atualiza -----------------------------------------------------
  
  observeEvent(input$bt_refresh_id_comod_comodatos, {
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
  
  #### PDV ----------------------------------------------------------
  observeEvent(input$button_group_doc$value,{
    # req(unique(filtro_base_comod_geral()$anexo1[filtro_base_comod_geral()$CEV == input$button_group_doc$cev])[1])
    url = glue("Anexos_Comodato/{URLencode(basename(unique(filtro_base_comod_geral()$anexo1[filtro_base_comod_geral()$CEV == input$button_group_doc$cev])[1]))}")
    
    runjs(glue("window.open('{url}', '_blank');"))
    
    
    # output$bt_download_anexo_comod = downloadHandler(
    #   filename = function() {
    #     req(unique(filtro_base_comod_geral()$anexo1[filtro_base_comod_geral()$CEV == input$button_group_doc$cev])[1])
    #     basename(unique(filtro_base_comod_geral()$anexo1[filtro_base_comod_geral()$CEV == input$button_group_doc$cev])[1])
    #   },
    #   content = function(file) {
    #     req(unique(filtro_base_comod_geral()$anexo1[filtro_base_comod_geral()$CEV == input$button_group_doc$cev])[1])
    #     file.copy(glue("{unique(filtro_base_comod_geral()$anexo1[filtro_base_comod_geral()$CEV == input$button_group_doc$cev])[1]}"), file)
    #   }
    # )
    # 
    # showModal(
    #   if(str_detect(tolower(unique(filtro_base_comod_geral()$anexo1[filtro_base_comod_geral()$CEV == input$button_group_doc$cev])[1]), "\\.(jpg|png|jpeg)$")){
    #     modalDialog(title = NULL,footer = NULL,easyClose = TRUE,size = "xl",
    #                 fluidRow(
    #                   column(12, align = "center",
    #                          imageOutput("imagem_anexo_doc"),
    #                          br(), br(),
    #                          downloadBttn("bt_download_anexo_comod",label = "Baixar arquivo",style = "stretch",color = "primary")
    #                   )
    #                 )
    #     )
    #   }
    #   else if(str_detect(tolower(unique(filtro_base_comod_geral()$anexo1[filtro_base_comod_geral()$CEV == input$button_group_doc$cev])[1]), "\\.(pdf)$")){
    #     modalDialog(title = NULL,footer = NULL,easyClose = TRUE,size = "l",
    #                 fluidRow(
    #                   column(12, align = "center",
    #                          # imagem_pdf = image_read_pdf(tabela_frota_selecionada_saida()$ANEXO[input$button$row], density = 150),
    #                          imageOutput("imagem_anexo_doc"),
    #                          br(), br(),
    #                          downloadBttn("bt_download_anexo_comod",label = "Baixar arquivo",style = "stretch",color = "primary")
    #                   )
    #                 )
    #     )
    #   }
    #   else{
    #     modalDialog(title = NULL,footer = NULL,easyClose = TRUE,size = "s",
    #                 fluidRow(column(12,align = "center", downloadBttn("bt_download_anexo_comod",label = "Baixar arquivo",style = "stretch",color = "primary")))
    #     )
    #   }
    # )
    # 
    # output$imagem_anexo_doc = renderImage({
    # 
    #   if(str_detect(tolower(unique(filtro_base_comod_geral()$anexo1[filtro_base_comod_geral()$CEV == input$button_group_doc$cev])[1]), "\\.(jpg|png|jpeg)$")){
    #     list(src = glue("{unique(filtro_base_comod_geral()$anexo1[filtro_base_comod_geral()$CEV == input$button_group_doc$cev])[1]}"),
    #          style = "max-width: 100%; max-height: 80vh; height: auto;
    #                    display: block; margin: auto;
    #                    position: relative; top: 50%; transform: translateY(-50%);")
    #   }
    #   else if(str_detect(tolower(unique(filtro_base_comod_geral()$anexo1[filtro_base_comod_geral()$CEV == input$button_group_doc$cev])[1]), "\\.(pdf)$")){
    #     list(src = image_write(image_read_pdf(glue("{unique(filtro_base_comod_geral()$anexo1[filtro_base_comod_geral()$CEV == input$button_group_doc$cev])[1]}"))[1], path = tempfile(fileext = ".png"), format = "png"),
    #          height = "120%")
    #   }
    # 
    # }, deleteFile = FALSE)
    
  }
  )
  
  
  #### CEV ----------------------------------------------------------
  observeEvent(input$button_group_cev$value,{
    
    url = glue("Anexos_Comodato/{URLencode(basename(unique(filtro_base_comod_geral()$anexo2[filtro_base_comod_geral()$CEV == input$button_group_cev$cev])[1]))}")
    
    runjs(glue("window.open('{url}', '_blank');"))
    # output$bt_download_anexo_comod = downloadHandler(
    #   filename = function() {
    #     req(unique(filtro_base_comod_geral()$anexo2[filtro_base_comod_geral()$CEV == input$button_group_cev$cev])[1])
    #     basename(unique(filtro_base_comod_geral()$anexo2[filtro_base_comod_geral()$CEV == input$button_group_cev$cev])[1])
    #   },
    #   content = function(file) {
    #     req(unique(filtro_base_comod_geral()$anexo2[filtro_base_comod_geral()$CEV == input$button_group_cev$cev])[1])
    #     # file.copy(glue("pages/Comodatos/Dados/{unique(filtro_base_comod_geral()$anexo2[filtro_base_comod_geral()$CEV == input$button_group_cev$cev])[1]}"), file)
    #     file.copy(glue("{unique(filtro_base_comod_geral()$anexo2[filtro_base_comod_geral()$CEV == input$button_group_cev$cev])[1]}"), file)
    #   }
    # )
    # 
    # showModal(
    #   if(str_detect(tolower(unique(filtro_base_comod_geral()$anexo2[filtro_base_comod_geral()$CEV == input$button_group_cev$cev])[1]), "\\.(jpg|png|jpeg)$")){
    #     modalDialog(title = NULL,footer = NULL,easyClose = TRUE,size = "xl",
    #                 fluidRow(
    #                   column(12, align = "center",
    #                          imageOutput("imagem_anexo_doc"),
    #                          br(), br(),
    #                          downloadBttn("bt_download_anexo_comod",label = "Baixar arquivo",style = "stretch",color = "primary")
    #                   )
    #                 )
    #     )
    #   }
    #   else if(str_detect(tolower(unique(filtro_base_comod_geral()$anexo2[filtro_base_comod_geral()$CEV == input$button_group_cev$cev])[1]), "\\.(pdf)$")){
    #     modalDialog(title = NULL,footer = NULL,easyClose = TRUE,size = "l",
    #                 fluidRow(
    #                   column(12, align = "center",
    #                          # imagem_pdf = image_read_pdf(tabela_frota_selecionada_saida()$ANEXO[input$button$row], density = 150),
    #                          imageOutput("imagem_anexo_doc"),
    #                          br(), br(),
    #                          downloadBttn("bt_download_anexo_comod",label = "Baixar arquivo",style = "stretch",color = "primary")
    #                   )
    #                 )
    #     )
    #   }
    #   else{
    #     modalDialog(title = NULL,footer = NULL,easyClose = TRUE,size = "s",
    #                 fluidRow(column(12,align = "center", downloadBttn("bt_download_anexo_comod",label = "Baixar arquivo",style = "stretch",color = "primary")))
    #     )
    #   }
    # )
    # 
    # output$imagem_anexo_doc = renderImage({
    # 
    #   if(str_detect(tolower(unique(filtro_base_comod_geral()$anexo2[filtro_base_comod_geral()$CEV == input$button_group_cev$cev])[1]), "\\.(jpg|png|jpeg)$")){
    #     list(src = glue("{unique(filtro_base_comod_geral()$anexo2[filtro_base_comod_geral()$CEV == input$button_group_cev$cev])[1]}"),
    #          style = "max-width: 100%; max-height: 80vh; height: auto;
    #                    display: block; margin: auto;
    #                    position: relative; top: 50%; transform: translateY(-50%);")
    #   }
    #   else if(str_detect(tolower(unique(filtro_base_comod_geral()$anexo2[filtro_base_comod_geral()$CEV == input$button_group_cev$cev])[1]), "\\.(pdf)$")){
    #     list(src = image_write(image_read_pdf(glue("{unique(filtro_base_comod_geral()$anexo2[filtro_base_comod_geral()$CEV == input$button_group_cev$cev])[1]}"))[1], path = tempfile(fileext = ".png"), format = "png"),
    #          height = "120%")
    #   }
    # 
    # }, deleteFile = FALSE)
    
  }
  )
  
  #### CANHOTO ----------------------------------------------------------
  observeEvent(input$button_group_can$value,{
    
    url = glue("Anexos_Comodato/{URLencode(basename(unique(filtro_base_comod_geral()$anexo3[filtro_base_comod_geral()$CEV == input$button_group_can$cev])[1]))}")
    
    runjs(glue("window.open('{url}', '_blank');"))
    
    # output$bt_download_anexo_comod = downloadHandler(
    #   filename = function() {
    #     req(unique(filtro_base_comod_geral()$anexo3[filtro_base_comod_geral()$CEV == input$button_group_can$cev])[1])
    #     basename(unique(filtro_base_comod_geral()$anexo3[filtro_base_comod_geral()$CEV == input$button_group_can$cev])[1])
    #   },
    #   content = function(file) {
    #     req(unique(filtro_base_comod_geral()$anexo3[filtro_base_comod_geral()$CEV == input$button_group_can$cev])[1])
    #     file.copy(glue("{unique(filtro_base_comod_geral()$anexo3[filtro_base_comod_geral()$CEV == input$button_group_can$cev])[1]}"), file)
    #   }
    # )
    # 
    # showModal(
    #   if(str_detect(tolower(unique(filtro_base_comod_geral()$anexo3[filtro_base_comod_geral()$CEV == input$button_group_can$cev])[1]), "\\.(jpg|png|jpeg)$")){
    #     modalDialog(title = NULL,footer = NULL,easyClose = TRUE,size = "xl",
    #                 fluidRow(
    #                   column(12, align = "center",
    #                          imageOutput("imagem_anexo_doc"),
    #                          br(), br(),
    #                          downloadBttn("bt_download_anexo_comod",label = "Baixar arquivo",style = "stretch",color = "primary")
    #                   )
    #                 )
    #     )
    #   }
    #   else if(str_detect(tolower(unique(filtro_base_comod_geral()$anexo3[filtro_base_comod_geral()$CEV == input$button_group_can$cev])[1]), "\\.(pdf)$")){
    #     modalDialog(title = NULL,footer = NULL,easyClose = TRUE,size = "l",
    #                 fluidRow(
    #                   column(12, align = "center",
    #                          # imagem_pdf = image_read_pdf(tabela_frota_selecionada_saida()$ANEXO[input$button$row], density = 150),
    #                          imageOutput("imagem_anexo_doc"),
    #                          br(), br(),
    #                          downloadBttn("bt_download_anexo_comod",label = "Baixar arquivo",style = "stretch",color = "primary")
    #                   )
    #                 )
    #     )
    #   }
    #   else{
    #     modalDialog(title = NULL,footer = NULL,easyClose = TRUE,size = "s",
    #                 fluidRow(column(12,align = "center", downloadBttn("bt_download_anexo_comod",label = "Baixar arquivo",style = "stretch",color = "primary")))
    #     )
    #   }
    # )
    # 
    # output$imagem_anexo_doc = renderImage({
    # 
    #   if(str_detect(tolower(unique(filtro_base_comod_geral()$anexo3[filtro_base_comod_geral()$CEV == input$button_group_can$cev])[1]), "\\.(jpg|png|jpeg)$")){
    #     list(src = glue("{unique(filtro_base_comod_geral()$anexo3[filtro_base_comod_geral()$CEV == input$button_group_can$cev])[1]}"),
    #          style = "max-width: 100%; max-height: 80vh; height: auto;
    #                    display: block; margin: auto;
    #                    position: relative; top: 50%; transform: translateY(-50%);")
    #   }
    #   else if(str_detect(tolower(unique(filtro_base_comod_geral()$anexo3[filtro_base_comod_geral()$CEV == input$button_group_can$cev])[1]), "\\.(pdf)$")){
    #     list(src = image_write(image_read_pdf(glue("{unique(filtro_base_comod_geral()$anexo3[filtro_base_comod_geral()$CEV == input$button_group_can$cev])[1]}"))[1], path = tempfile(fileext = ".png"), format = "png"),
    #          height = "120%")
    #   }
    # 
    # }, deleteFile = FALSE)
    
  }
  )
  
  # observeEvent(input$button_group_act,{
  #   print(input$button_group_act)
  #   print(filtro_base_comod_geral()$CEV[filtro_base_comod_geral()$CEV == input$button_group_act$cev])
  #   
  #   
  # })
  
  #### RECOLHA ----------------------------------------------------------------

  observeEvent(input$button_group_dis$value,{
    req(session$userData$usuario)
    
    if(input$button_group_dis$value != "PDF") {

      revenda_recolha <- revenda_query()
      cev_recolha <- unique(filtro_base_comod_geral()$CEV[filtro_base_comod_geral()$CEV == input$button_group_dis$cev]) # pega revenda e comodato

      shinyalert(
        title = "Confirmar recolha?",
        text = "Deseja realmente enviar o pedido de recolha ao ERP?",
        size = "s",
        type = "warning",
        closeOnEsc = TRUE,
        closeOnClickOutside = TRUE,
        showCancelButton = TRUE,
        showConfirmButton = TRUE,
        confirmButtonText = "Sim",
        cancelButtonText = "Não",
        confirmButtonCol = cores_reativo()[2],
        animation = TRUE,
        callbackR = function(confirmado) {

          if (!isTRUE(confirmado)) return()

          shinyalert(
            title = "Aguarde...",
            text = "Enviando recolha para o ERP.",
            size = "s",
            type = "info",
            closeOnEsc = FALSE,
            closeOnClickOutside = FALSE,
            showConfirmButton = FALSE,
            confirmButtonText = "OK",
            confirmButtonCol = cores_reativo()[2],
            animation = TRUE
          )

          future({
            tryCatch({
              gerar_recolha(revenda_recolha, cev_recolha)
              TRUE
            }, error = function(e) {
              message("Erro ao gerar recolha: ", e$message)
              FALSE
            })
          }, seed = TRUE) %...>% (function(resultado) {

            closeAlert(1)

            if (isTRUE(resultado)) {

              refresh_comod(refresh_comod() + 1)

              shinyalert(
                title = "Pedido de recolha gerado",
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

            } else {

              shinyalert(
                title = "Limite de licenças atingido",
                text = "Tente novamente mais tarde.",
                size = "xs",
                closeOnEsc = TRUE,
                closeOnClickOutside = TRUE,
                type = "error",
                showConfirmButton = FALSE,
                confirmButtonText = "OK",
                confirmButtonCol = cores_reativo()[2],
                animation = TRUE
              )

            }
          }) %...!% (function(error) {

            closeAlert(1)

            shinyalert(
              title = "Limite de licenças atingido",
              text = "Tente novamente mais tarde.",
              size = "xs",
              closeOnEsc = TRUE,
              closeOnClickOutside = TRUE,
              type = "error",
              showConfirmButton = FALSE,
              confirmButtonText = "OK",
              confirmButtonCol = cores_reativo()[2],
              animation = TRUE
            )
          })

        }
      )

    } else{

      
      shinyalert(
        title = "Aguarde...",
        text = "Gerando PDF.",
        size = "s",
        type = "info",
        closeOnEsc = FALSE,
        closeOnClickOutside = FALSE,
        showConfirmButton = FALSE,
        confirmButtonText = "OK",
        confirmButtonCol = cores_reativo()[2],
        animation = TRUE
      )
      
      distrato_pdf(
        unique(filtro_base_comod_geral()$CEV[filtro_base_comod_geral()$CEV == input$button_group_dis$cev]),
        unique(filtro_base_comod_geral()$Cliente[filtro_base_comod_geral()$CEV == input$button_group_dis$cev]),
        unique(filtro_base_comod_geral()$Fantasia[filtro_base_comod_geral()$CEV == input$button_group_dis$cev]),
        unique(filtro_base_comod_geral()$cnpj[filtro_base_comod_geral()$CEV == input$button_group_dis$cev]),
        unique(filtro_base_comod_geral()$CNPJ_CLI[filtro_base_comod_geral()$CEV == input$button_group_dis$cev]),
        unique(filtro_base_comod_geral()$ENDERECO[filtro_base_comod_geral()$CEV == input$button_group_dis$cev]),
        unique(filtro_base_comod_geral()$CEP[filtro_base_comod_geral()$CEV == input$button_group_dis$cev]),
        unique(filtro_base_comod_geral()[filtro_base_comod_geral()$CEV == input$button_group_dis$cev,] %>% 
                select(CODCOMP, Produto, Qtd))
      )
      
      closeAlert(1)
      
      runjs("document.getElementById('bt_download_pdf_distrato').click();")

    }

  })

  #### DISTRATO ----------------------------------------------------------------
  
  # observeEvent(input$button_group_dis$value,{
  #   req(session$userData$usuario)
    
  #   shinyalert(
  #     title = "Aguarde...",
  #     text = "Gerando PDF.",
  #     size = "s",
  #     type = "info",
  #     closeOnEsc = FALSE,
  #     closeOnClickOutside = FALSE,
  #     showConfirmButton = FALSE,
  #     confirmButtonText = "OK",
  #     confirmButtonCol = cores_reativo()[2],
  #     animation = TRUE
  #   )
    
  #   distrato_pdf(
  #     unique(filtro_base_comod_geral()$CEV[filtro_base_comod_geral()$CEV == input$button_group_dis$cev]),
  #     unique(filtro_base_comod_geral()$Cliente[filtro_base_comod_geral()$CEV == input$button_group_dis$cev]),
  #     unique(filtro_base_comod_geral()$Fantasia[filtro_base_comod_geral()$CEV == input$button_group_dis$cev]),
  #     unique(filtro_base_comod_geral()$cnpj[filtro_base_comod_geral()$CEV == input$button_group_dis$cev]),
  #     unique(filtro_base_comod_geral()$CNPJ_CLI[filtro_base_comod_geral()$CEV == input$button_group_dis$cev]),
  #     unique(filtro_base_comod_geral()$ENDERECO[filtro_base_comod_geral()$CEV == input$button_group_dis$cev]),
  #     unique(filtro_base_comod_geral()$CEP[filtro_base_comod_geral()$CEV == input$button_group_dis$cev]),
  #     unique(filtro_base_comod_geral()[filtro_base_comod_geral()$CEV == input$button_group_dis$cev,] %>% 
  #              select(CODCOMP, Produto, Qtd))
  #   )
    
  #   closeAlert(1)
    
  #   runjs("document.getElementById('bt_download_pdf_distrato').click();")
  # })
  
  output$bt_download_pdf_distrato <- downloadHandler(
    
    filename = function() { paste0("DISTRATO_",
                                   unique(filtro_base_comod_geral()$Cliente[filtro_base_comod_geral()$CEV == input$button_group_dis$cev]),
                                   "_",
                                   unique(filtro_base_comod_geral()$CEV[filtro_base_comod_geral()$CEV == input$button_group_dis$cev]),
                                   Sys.Date(), ".pdf") },
    content = function(file) {
      file.copy(glue("{diretorio}pages/Comodatos/Dados/DISTRATO_CEV.PDF"), file)
    }
  )
  
  #### Ação ----------------------------------------------------------
  observeEvent(input$button_group_act$value,{
    req(session$userData$usuario)
    # output$comodato_capa <- renderImage( 
    #   { 
    #     list(src = "{diretorio}www/acomp_log_www/img/comodato_capa.svg") 
    #   }, 
    #   deleteFile = FALSE 
    # ) 
    
    if(input$button_group_act$value %in% c("\u26D4","\u2795")){
      
      #Só vai poder mandar novos documentos se não tiver prazo esgotado
      # if (!any(unique(filtro_base_comod_geral()$`Prazo do Input`[filtro_base_comod_geral()$CEV == input$button_group_act$cev]) == "Esgotado",na.rm = TRUE)){
      # if (any(!is.na(unique(filtro_base_comod_geral()$`Prazo do Input`[filtro_base_comod_geral()$CEV == input$button_group_act$cev])))){
      if(TRUE){
        showModal(
          modalDialog(
            title = tags$div("Comodato", style = glue("color: {cores_reativo()[1]}")),
            size = "xl",
            fluidRow(
              column(8,
                     textInput("aud_comod_user_input",label = "Razão Social:",value = unique(filtro_base_comod_geral()$`Razão Social`[filtro_base_comod_geral()$CEV == input$button_group_act$cev]), width = "100%") %>%
                       tagAppendAttributes(style = "pointer-events: none;"),
                     textInput("aud_comod_cev_input",label = "Nº CEV:",value = sub(".*-\\s*(\\d+).*", "\\1", input$button_group_act$cev),width = "100%") %>%
                       tagAppendAttributes(style = "pointer-events: none;"),
                     textInput("aud_comod_resp_input",label = "Usuário:",value = str_to_title(paste0(strsplit(session$userData$usuario,"\\.")[[1]],collapse = " ")), width = "100%") %>%
                       tagAppendAttributes(style = "pointer-events: none;"),
                     fluidRow(
                       column(4,
                              airDatepickerInput(
                                inputId = "data_conf_comod_audi",
                                label = "Data de conferência:", 
                                value = Sys.Date(),
                                dateFormat = "dd/MM/yyyy",
                                language = "pt-BR", 
                                width = "100%"
                              )),
                       column(8)
                     ),
                     fluidRow(
                       column(4,
                              fileInput("anexo_canhot_comod",label = "Canhoto:",buttonLabel = "Procurar...",placeholder = "", accept = c(".pdf", ".jpg", ".jpeg", ".png"))
                       ),
                       column(4,
                              fileInput("anexo_comodo_comod",label = "Comodato:",buttonLabel = "Procurar...",placeholder = "", accept = c(".pdf", ".jpg", ".jpeg", ".png"))
                              # style = "visibility: hidden;"
                       ),
                       column(4,
                              fileInput("anexo_docpdv_comod",label = "Documento PDV:",buttonLabel = "Procurar...",placeholder = "", accept = c(".pdf", ".jpg", ".jpeg", ".png"))
                              # style = "visibility: hidden;"
                       )
                     ),
                     fluidRow(
                       column(12,
                              align = "center",
                              actionBttn("bt_envia_anexo_comod", label = "Enviar",style = "material-flat", color = "success", size = "sm")
                       )
                     )
              ),
              column(4,
                     tags$img(src = "acomp_log_www/img/comodato_capa.svg", width = "100%"))
            ),
            easyClose = TRUE,
            footer = NULL
          )
        )
      }
      
    }
    else if(input$button_group_act$value == "\u2699\uFE0F"){
      
      output$comprom_comod_audi = renderText({tags$div("Declaro que documentação do comodato e do cliente foi conferida de acordo com os Termos do Corporativo")})
      
      if(session$userData$usuario %in% poder_total_comodato){
        
        showModal(
          modalDialog(
            title = tags$div("Auditoria de CEV", style = glue("color: {cores_reativo()[1]}")),
            size = "xl",
            fluidRow(
              column(7,
                     textInput("aud_comod_user_input",label = "Razão Social:",value = unique(filtro_base_comod_geral()$`Razão Social`[filtro_base_comod_geral()$CEV == input$button_group_act$cev]), width = "100%") %>%
                       tagAppendAttributes(style = "pointer-events: none;"),
                     textInput("aud_comod_cev_input",label = "Nº CEV:",value = sub(".*-\\s*(\\d+).*", "\\1", input$button_group_act$cev),width = "100%") %>%
                       tagAppendAttributes(style = "pointer-events: none;"),
                     textInput("aud_comod_resp_input",label = "Usuário:",value = str_to_title(paste0(strsplit(session$userData$usuario,"\\.")[[1]],collapse = " ")), width = "100%") %>%
                       tagAppendAttributes(style = "pointer-events: none;"),
                     fluidRow(
                       column(6,
                              airDatepickerInput(
                                inputId = "data_conf_comod_audi",
                                label = "Data de conferência:", 
                                value = Sys.Date(),
                                dateFormat = "dd/MM/yyyy",
                                language = "pt-BR", 
                                width = "100%"
                              )),
                       column(6)
                     ),
                     textAreaInput("aud_comod_moti_input",label = "Motivo: ",width = "100%"),
                     checkboxInput("check_comod_audi",
                                   label = tags$span("Declaro que documentação do comodato e do cliente foi conferida de acordo com os ",
                                                     actionLink("termos_corporativo", "Termos do Corporativo")),
                                   value = TRUE,
                                   width = "100%"),
                     fluidRow(
                       column(6,
                              align = "center",
                              actionBttn("bt_confirma_comod", label = "Confirmar",style = "material-flat", color = "success", size = "sm")
                       ),
                       column(6,
                              align = "center",
                              actionBttn("bt_bloqueia_comod", label = "Bloquear",style = "material-flat", color = "danger", size = "sm")
                       )
                     )
              ),
              column(5,
                     tags$img(src = "acomp_log_www/img/comodato_capa.svg", width = "100%"))
            ),
            easyClose = TRUE,
            footer = NULL
          )
        )
        
      } else {
        #Só vai poder mandar novos documentos se não tiver prazo esgotado
        if (!any(unique(filtro_base_comod_geral()$`Prazo do Input`[filtro_base_comod_geral()$CEV == input$button_group_act$cev]) == "Esgotado",na.rm = TRUE)){
          showModal(
            modalDialog(
              title = tags$div("Comodato", style = glue("color: {cores_reativo()[1]}")),
              size = "xl",
              fluidRow(
                column(8,
                       textInput("aud_comod_user_input",label = "Razão Social:",value = unique(filtro_base_comod_geral()$`Razão Social`[filtro_base_comod_geral()$CEV == input$button_group_act$cev]), width = "100%") %>%
                         tagAppendAttributes(style = "pointer-events: none;"),
                       textInput("aud_comod_cev_input",label = "Nº CEV:",value = sub(".*-\\s*(\\d+).*", "\\1", input$button_group_act$cev),width = "100%") %>%
                         tagAppendAttributes(style = "pointer-events: none;"),
                       textInput("aud_comod_resp_input",label = "Usuário:",value = str_to_title(paste0(strsplit(session$userData$usuario,"\\.")[[1]],collapse = " ")), width = "100%") %>%
                         tagAppendAttributes(style = "pointer-events: none;"),
                       fluidRow(
                         column(4,
                                airDatepickerInput(
                                  inputId = "data_conf_comod_audi",
                                  label = "Data de conferência:", 
                                  value = Sys.Date(),
                                  dateFormat = "dd/MM/yyyy",
                                  language = "pt-BR", 
                                  width = "100%"
                                )),
                         column(8)
                       ),
                       fluidRow(
                         column(4,
                                fileInput("anexo_canhot_comod",label = "Canhoto:",buttonLabel = "Procurar...",placeholder = "", accept = c(".pdf", ".jpg", ".jpeg", ".png"))
                         ),
                         column(4,
                                fileInput("anexo_comodo_comod",label = "Comodato:",buttonLabel = "Procurar...",placeholder = "", accept = c(".pdf", ".jpg", ".jpeg", ".png"))
                                # style = "visibility: hidden;"
                         ),
                         column(4,
                                fileInput("anexo_docpdv_comod",label = "Documento PDV:",buttonLabel = "Procurar...",placeholder = "", accept = c(".pdf", ".jpg", ".jpeg", ".png"))
                                # style = "visibility: hidden;"
                         )
                       ),
                       fluidRow(
                         column(12,
                                align = "center",
                                actionBttn("bt_envia_anexo_comod", label = "Enviar",style = "material-flat", color = "success", size = "sm")
                         )
                       )
                ),
                column(4,
                       tags$img(src = "acomp_log_www/img/comodato_capa.svg", width = "100%"))
              ),
              easyClose = TRUE,
              footer = NULL
            )
          )
        }
      }
      
    }
  })
  
  ##### Inputs -----------------------------------------
  observeEvent(input$anexo_docpdv_comod,{
    nao_tem_pdv(1)
  })
  observeEvent(input$anexo_comodo_comod,{
    nao_tem_cev(1)
  })
  observeEvent(input$anexo_canhot_comod,{
    nao_tem_can(1)
  })
  
  ##### Enviar -----------------------------------------
  observeEvent(input$bt_envia_anexo_comod,{
    # req(input$anexo_docpdv_comod) # Deixar como comentario para desativar
    # req(input$anexo_comodo_comod) # Deixar como comentario para desativar
    req(input$anexo_canhot_comod)
    
    req(nao_tem_can())
    # req(nao_tem_pdv()) # Deixar como comentario para desativar
    # req(nao_tem_cev()) # Deixar como comentario para desativar
    
    removeModal(session = session)
    
    pdv_path <- if (is.null(input$anexo_docpdv_comod$datapath)) NULL else input$anexo_docpdv_comod$datapath
    comod_path <- if (is.null(input$anexo_comodo_comod$datapath)) NULL else input$anexo_comodo_comod$datapath
    canhoto_path <- if (is.null(input$anexo_canhot_comod$datapath)) NULL else input$anexo_canhot_comod$datapath
    
    pdv_name <- if (is.null(input$anexo_docpdv_comod$name)) NULL else input$anexo_docpdv_comod$name
    comod_name <- if (is.null(input$anexo_comodo_comod$name)) NULL else input$anexo_comodo_comod$name
    canhoto_name <- if (is.null(input$anexo_canhot_comod$name)) NULL else input$anexo_canhot_comod$name
    
    retornos = anexos_comod(pdv_path,
                            comod_path,
                            canhoto_path,
                            unique(filtro_base_comod_geral()$Cliente[filtro_base_comod_geral()$CEV == input$button_group_act$cev])[1],
                            sub(".*-\\s*(\\d+).*", "\\1", input$button_group_act$cev),
                            unique(filtro_base_comod_geral()$cnpj[filtro_base_comod_geral()$CEV == input$button_group_act$cev])[1],
                            input$anexo_docpdv_comod$name,
                            input$anexo_comodo_comod$name,
                            input$anexo_canhot_comod$name)
    
    coloca_anexo_bd(sub(".*-\\s*(\\d+).*", "\\1", input$button_group_act$cev),
                    retornos[["PDV"]],
                    retornos[["CEV"]],
                    retornos[["CANHOTO"]],
                    unique(filtro_base_comod_geral()$cnpj[filtro_base_comod_geral()$CEV == input$button_group_act$cev])[1],
                    str_to_title(paste0(strsplit(session$userData$usuario,"\\.")[[1]],collapse = " ")),
                    unique(filtro_base_comod_geral()$Cliente[filtro_base_comod_geral()$CEV == input$button_group_act$cev])[1],
                    unique(filtro_base_comod_geral()$NF[filtro_base_comod_geral()$CEV == input$button_group_act$cev])[1]
    )
    
    # dispara refresh no reativo
    refresh_comod(refresh_comod() + 1)
    
    shinyalert(
      title = "Enviado",
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
    
    nao_tem_can(NULL)
    nao_tem_cev(NULL)
    nao_tem_pdv(NULL)
  })
  
  ##### Confirmar -----------------------------------------
  observeEvent(input$bt_confirma_comod, {
    removeModal(session = session)
    
    conf_bloq_comod(sub(".*-\\s*(\\d+).*", "\\1", input$button_group_act$cev), "A", input$aud_comod_moti_input, unique(filtro_base_comod_geral()$cnpj[filtro_base_comod_geral()$CEV == input$button_group_act$cev])[1])
    
    # dispara refresh no reativo
    refresh_comod(refresh_comod() + 1)
    
    shinyalert(
      title = "Enviado",
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
  
  ##### Bloquear -----------------------------------------
  observeEvent(input$bt_bloqueia_comod, {
    removeModal(session = session)
    
    conf_bloq_comod(sub(".*-\\s*(\\d+).*", "\\1", input$button_group_act$cev), "B", input$aud_comod_moti_input, unique(filtro_base_comod_geral()$cnpj[filtro_base_comod_geral()$CEV == input$button_group_act$cev])[1])
    
    # dispara refresh no reativo
    refresh_comod(refresh_comod() + 1)
    
    shinyalert(
      title = "Enviado",
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
  
  #### Limpa filtros -----------------------------------------
  observeEvent(input$bt_limpacomod, {
    updateSearchInput(session,inputId = "cevcli_input_comod",value = character(0))
    updatePickerInput(session,inputId = "produt_input_comod",selected = character(0))
    updatePickerInput(session,inputId = "inadim_input_comod",selected = character(0))
    updatePickerInput(session,inputId = "prazoi_input_comod",selected = character(0))
    updatePickerInput(session,inputId = "usuari_input_comod",selected = character(0))
    updatePickerInput(session,inputId = "status_input_comod",selected = character(0))
    updatePickerInput(session,inputId = "interv_input_comod",selected = character(0))
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
  
  # observeEvent(input$cevcli_input_comod, {
  #   req(input$cevcli_input_comod)
  #   print(input$cevcli_input_comod)
  # })
  
  filtro_base_comod_geral = reactive({
    if(
      (is.null(input$cevcli_input_comod) || input$cevcli_input_comod == "") &&
      (is.null(input$produt_input_comod) || length(input$produt_input_comod) == 0) &&
      (is.null(input$inadim_input_comod) || length(input$inadim_input_comod) == 0) &&
      (is.null(input$prazoi_input_comod) || length(input$prazoi_input_comod) == 0) &&
      (is.null(input$usuari_input_comod) || length(input$usuari_input_comod) == 0) &&
      (is.null(input$status_input_comod) || length(input$status_input_comod) == 0) &&
      (is.null(input$interv_input_comod) || length(input$interv_input_comod) == 0)){
      
      dados = comodato_geral()
      
    } else {
      
      dados = comodato_geral() %>%
        filter(
          if (is.null(input$cevcli_input_comod) || input$cevcli_input_comod == "") TRUE else str_detect(toupper(PesquisaCev), toupper(input$cevcli_input_comod)),
          if (is.null(input$produt_input_comod) || length(input$produt_input_comod) == 0) TRUE else Produto %in% input$produt_input_comod,
          if (is.null(input$inadim_input_comod) || length(input$inadim_input_comod) == 0) TRUE else `Inadimplencia 60 dias +` %in% input$inadim_input_comod,
          if (is.null(input$prazoi_input_comod) || length(input$prazoi_input_comod) == 0) TRUE else `Prazo do Input` %in% input$prazoi_input_comod,
          if (is.null(input$usuari_input_comod) || length(input$usuari_input_comod) == 0) TRUE else Usuario %in% input$usuari_input_comod,
          if (is.null(input$status_input_comod) || length(input$status_input_comod) == 0) TRUE else Status %in% input$status_input_comod,
          if (is.null(input$interv_input_comod) || length(input$interv_input_comod) == 0) TRUE else `Intervalo Vencimento` %in% input$interv_input_comod
          
        )
    }
    
    dados
  })
  # 
  # 
  # 
  observeEvent(filtro_base_comod_geral(), {
    #   
    #   # Atualiza apenas se não houver seleção
    if (is.null(input$interv_input_comod) || length(input$interv_input_comod) == 0) {
      updatePickerInput(session, "interv_input_comod", choices = sort(unique(filtro_base_comod_geral()$`Intervalo Vencimento`[!is.na(filtro_base_comod_geral()$`Intervalo Vencimento`)])))
    }
    if (is.null(input$produt_input_comod) || length(input$produt_input_comod) == 0) {
      updatePickerInput(session, "produt_input_comod", choices = sort(unique(filtro_base_comod_geral()$Produto[!is.na(filtro_base_comod_geral()$Produto)])))
    }
    if (is.null(input$inadim_input_comod) || length(input$inadim_input_comod) == 0) {
      updatePickerInput(session, "inadim_input_comod", choices = sort(unique(filtro_base_comod_geral()$`Inadimplencia 60 dias +`[!is.na(filtro_base_comod_geral()$`Inadimplencia 60 dias +`)])))
    }
    if (is.null(input$prazoi_input_comod) || length(input$prazoi_input_comod) == 0) {
      updatePickerInput(session, "prazoi_input_comod", choices = sort(unique(filtro_base_comod_geral()$`Prazo do Input`[!is.na(filtro_base_comod_geral()$`Prazo do Input`)])))
    }
    if (is.null(input$usuari_input_comod) || length(input$usuari_input_comod) == 0) {
      updatePickerInput(session, "usuari_input_comod", choices = sort(unique(filtro_base_comod_geral()$Usuario[!is.na(filtro_base_comod_geral()$Usuario) & filtro_base_comod_geral()$Usuario != ""])))
    }
    if (is.null(input$status_input_comod) || length(input$status_input_comod) == 0) {
      updatePickerInput(session, "status_input_comod", choices = sort(unique(filtro_base_comod_geral()$Status)))
    }
  })
  
  
  
  
  # Tabela consolidada ------------------------------------------------------
  
  output$tabela_consol_comodato = renderReactable({
    req(filtro_base_comod_geral())
    
    historico_comodatos = filtro_base_comod_geral()
    
    reactable(
      historico_comodatos,
      columns = list(
        anexo1 = colDef(show = FALSE),
        anexo2 = colDef(show = FALSE),
        anexo3 = colDef(show = FALSE),
        Status = colDef(show = FALSE),
        cnpj = colDef(show = FALSE),
        PesquisaCev = colDef(show = FALSE),
        NF = colDef(aggregate = "unique", width = 80),
        Cliente = colDef(aggregate = "unique", width = 85),
        CODCOMP = colDef(name = "Comp", width = 80),
        Fantasia = colDef(aggregate = "unique"),
        `Razão Social` = colDef(aggregate = "unique"),
        `Data Emissão` = colDef(name = "Emissão", aggregate = "max", width = 95, format = colFormat(date = TRUE, locales = "pt-BR")),
        `Data Vencimento` = colDef(name = "Venc", aggregate = "max", width = 95, format = colFormat(date = TRUE, locales = "pt-BR")),
        `Intervalo Vencimento` = colDef(name = "Intervalo (dias)", aggregate = "unique", width = 90),
        Qtd = colDef(aggregate = "sum", width = 70),
        `Inadimplencia 60 dias +` = colDef(name = "Inad. 60 dias +", aggregate = "unique", width = 80),
        `Prazo do Input` = colDef(aggregate = "unique", width = 85, name = "Prazo"),
        Usuario = colDef(aggregate = "unique"),
        CNPJ_REV = colDef(show = FALSE),
        ENDERECO = colDef(show = FALSE),
        CEP = colDef(show = FALSE),
        CNPJ_CLI = colDef(show = FALSE),
        Origem = colDef(aggregate = "unique"),
        Acao = colDef(
          name = "Ação",
          cell = function(value, index){
            return("")
          },
          aggregate = JS("
            function(values, rows) {
              // Pega o valor único da coluna atual
              var uniqueVal = Array.from(new Set(values))[0];
              
              // Pega o valor de outra coluna da primeira linha do grupo
              var CEV = rows[0]['CEV']; // substitua pelo nome exato da coluna
              
              // Cria o botão como HTML
              var btn = '<button class=\"button_com_act\" ' +
                        'onclick=\"Shiny.onInputChange(\\'button_group_act\\', {value: \\'' + uniqueVal + '\\', cev: \\'' + CEV + '\\', nonce: Math.random()})\">' +
                        uniqueVal + '</button>';
              return btn;
            }
          "),
          width = 50,
          html = TRUE
        ),
        Doc = colDef(
          # show = FALSE,
          cell = function(value, index){
            return("")
          },
          aggregate = JS("
            function(values, rows) {
              // Pega o valor único da coluna atual
              var uniqueVal = Array.from(new Set(values))[0];
              
              // Pega o valor de outra coluna da primeira linha do grupo
              var CEV = rows[0]['CEV']; // substitua pelo nome exato da coluna
              
              // Cria o botão como HTML
              var btn = '<button class=\"button_com_doc\" ' +
                        'title=\"Visualizar documento\"' +
                        'onclick=\"Shiny.onInputChange(\\'button_group_doc\\', {value: \\'' + uniqueVal + '\\', cev: \\'' + CEV + '\\', nonce: Math.random()})\">' +
                        uniqueVal + '</button>';
              return btn;
            }
          "),
          width = 50,
          html = TRUE
        ),
        `Cev link` = colDef(
          cell = function(value, index){
            return("")
          },
          aggregate = JS("
            function(values, rows) {
              // Pega o valor único da coluna atual
              var uniqueVal = Array.from(new Set(values))[0];
              
              // Pega o valor de outra coluna da primeira linha do grupo
              var CEV = rows[0]['CEV']; // substitua pelo nome exato da coluna
              
              // Cria o botão como HTML
              var btn = '<button class=\"button_com_cev\" ' +
                        'title=\"Visualizar contrato\"' +
                        'onclick=\"Shiny.onInputChange(\\'button_group_cev\\', {value: \\'' + uniqueVal + '\\', cev: \\'' + CEV + '\\', nonce: Math.random()})\">' +
                        uniqueVal + '</button>';
              return btn;
            }
          "),
          width = 50,
          html = TRUE,
          name = "Cev"
        ),
        Canhoto = colDef(
          cell = function(value, index){
            return("")
          },
          aggregate = JS("
            function(values, rows) {
              // Pega o valor único da coluna atual
              var uniqueVal = Array.from(new Set(values))[0];
              
              // Pega o valor de outra coluna da primeira linha do grupo
              var CEV = rows[0]['CEV']; // substitua pelo nome exato da coluna
              
              // Cria o botão como HTML
              var btn = '<button class=\"button_com_can\" ' +
                        'title=\"Visualizar canhoto\"' +
                        'onclick=\"Shiny.onInputChange(\\'button_group_can\\', {value: \\'' + uniqueVal + '\\', cev: \\'' + CEV + '\\', nonce: Math.random()})\">' +
                        uniqueVal + '</button>';
              return btn;
            }
          "),
          width = 50,
          html = TRUE,
          name = "Can"
        ),
        Recolha = colDef(
          show = ifelse(session$userData$usuario %in% responsaveis(), TRUE, FALSE),
          cell = function(value, index){
            return("")
          },
          aggregate = JS("
            function(values, rows) {
              // Pega o valor único da coluna atual
              var uniqueVal = (values || []).filter(v => v != null && v !== '')[0] || '';
              // Pega o valor de outra coluna da primeira linha do grupo
              var CEV = rows[0]['CEV']; // substitua pelo nome exato da coluna

              // Se for PDF, mostra o ícone pra gerar o distrato; senão, mostra o próprio emoji de recolha
              var conteudo = uniqueVal === 'PDF'
                ? '<img src=\"https://cdn-icons-png.flaticon.com/512/337/337946.png\" width=\"20\" height=\"20\" style=\"vertical-align:middle;\">'
                : uniqueVal;

              // Cria o botão como HTML
              var btn = '<button class=\"button_com_doc\" ' +
                        'title=\"Contrato de recolha \"' +
                        'onclick=\"Shiny.onInputChange(\\'button_group_dis\\', {value: \\'' + uniqueVal + '\\', cev: \\'' + CEV + '\\', nonce: Math.random()})\">' +
                        conteudo +
                        '</button>';
              return btn;
            }
          "),
          html = TRUE,
          name = "Recolha"
        ),
        Produto = colDef(aggregate = "count", format = list(aggregated = colFormat(prefix = "Itens comodatados: ")))
      ),
      defaultColDef = colDef(align = "center",minWidth = 80),
      groupBy = c("CEV"),
      defaultSorted = "CEV",
      defaultSortOrder = "desc",
      resizable = TRUE,
      pagination = TRUE,
      defaultPageSize = 50,
      pageSizeOptions = c(50, 100, 500),
      showPageSizeOptions = TRUE,
      wrap = FALSE,
      height = "58vh",
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
      rowStyle = JS("
        function(rowInfo) {
          if (rowInfo.row['Origem'] === 'Dash') {
            return {
              background: 'linear-gradient(135deg, rgba(19,166,192,0.2) 100%, rgba(12,105,122,0.05) 0)'
            };
          } else {
            return {
              background: '#fff3cd'
            };
          }
        }
      "),
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
  
  # observeEvent(filtro_base_comod_geral(), {
  #   print(length(unique(filtro_base_comod_geral()$CEV)))
  #   print(length(unique(filtro_base_comod_geral()$CEV[filtro_base_comod_geral()$`Inadimplencia 60 dias +` == "Sim"])))
  #   print(min(as.numeric(str_extract(filtro_base_comod_geral()$`Prazo do Input`, "\\d+")),na.rm = TRUE))
  # })
  
  # Cards ------------------------------------------------------------------
  
  output$card_prz_curto = renderInfoBox({
    req(filtro_base_comod_geral())
    prazos <- as.numeric(str_extract(filtro_base_comod_geral()$`Prazo do Input`, "\\d+"))
    
    if(is.infinite(min(prazos,na.rm = TRUE))){
      minimo = 0
    }
    else{
      minimo = min(prazos,na.rm = TRUE)
    }
    
    infoBox("Prazo mais curto",
            glue("{minimo} dia(s)"),
            color = "primary",
            icon = icon("clock"))
  })
  
  output$card_cli_inad = renderInfoBox({
    req(filtro_base_comod_geral())
    infoBox("Clientes inadimplentes",length(unique(filtro_base_comod_geral()$CEV[filtro_base_comod_geral()$`Inadimplencia 60 dias +` == "Sim"])),color = "primary", icon = icon("users-slash"))
  })
  # NULL, class = "custom-icon-cerv1l"
  output$card_cevs_abertos = renderInfoBox({
    req(filtro_base_comod_geral())
    infoBox("Quantidade de CEV's",length(unique(filtro_base_comod_geral()$CEV)),color = "primary", icon = icon("file-signature"))
  })
  
  output$card_cevs_cerv1l = renderInfoBox({
    req(filtro_base_comod_geral())
    
    caixa_1L = c('690163', '555001')
    infoBox("Qtd Caixa 1L",
            sum(filtro_base_comod_geral()$Qtd[filtro_base_comod_geral()$CODCOMP %in% caixa_1L],na.rm = TRUE),
            color = "primary", 
            icon = icon(NULL, class = "custom-icon-cerv1l"))
  })
  
  output$card_cevs_cerv300 = renderInfoBox({
    req(filtro_base_comod_geral())
    
    caixa_300ml = c('551003','551002','551001','546004','061007')
    infoBox("Qtd Caixa 300 ML",
            sum(filtro_base_comod_geral()$Qtd[filtro_base_comod_geral()$CODCOMP %in% caixa_300ml],na.rm = TRUE),
            color = "primary", 
            icon = icon(NULL, class = "custom-icon-cerv300ml"))
  })
  
  output$card_cevs_cerv600hnk = renderInfoBox({
    req(filtro_base_comod_geral())
    
    caixa_600ml_HNK = c('587003','587002')
    infoBox("Qtd Caixa 600 ML MAR",
            sum(filtro_base_comod_geral()$Qtd[filtro_base_comod_geral()$CODCOMP %in% caixa_600ml_HNK],na.rm = TRUE),
            color = "primary", 
            icon = icon(NULL, class = "custom-icon-cerv600mlhnk"))
  })
  
  output$card_cevs_cerv600 = renderInfoBox({
    req(filtro_base_comod_geral())
    
    emprestimo_bloq = c('808002','808001','550013','550012','550011','550001') # Todos de Caixa 600ml
    infoBox("Qtd Caixa 600 ML",
            sum(filtro_base_comod_geral()$Qtd[filtro_base_comod_geral()$CODCOMP %in% emprestimo_bloq],na.rm = TRUE),
            color = "primary", 
            icon = icon(NULL, class = "custom-icon-cerv600ml"))
  })
  
  output$card_cevs_carrinho_amb = renderInfoBox({
    req(filtro_base_comod_geral())
    
    infoBox("Carrinho",
            sum(filtro_base_comod_geral()$Qtd[str_detect(filtro_base_comod_geral()$Produto, "Carrinho|Ambulante")],na.rm = TRUE),
            color = "primary", 
            icon = icon(NULL, class = "custom-icon-carrinho"))
  })
  
  output$card_cevs_horizontal = renderInfoBox({
    req(filtro_base_comod_geral())
    
    infoBox("Horizontal",
            sum(filtro_base_comod_geral()$Qtd[str_detect(filtro_base_comod_geral()$Produto, "Horiz|Horizontal")],na.rm = TRUE),
            color = "primary", 
            icon = icon(NULL, class = "custom-icon-horiz"))
  })
  
  output$card_cevs_vertical = renderInfoBox({
    req(filtro_base_comod_geral())
    
    infoBox("Vertical",
            sum(filtro_base_comod_geral()$Qtd[str_detect(filtro_base_comod_geral()$Produto, "Vertical|Vert|Vetical")],na.rm = TRUE),
            color = "primary", 
            icon = icon(NULL, class = "custom-icon-verti"))
  })
  
  output$card_cevs_quiosque = renderInfoBox({
    req(filtro_base_comod_geral())
    
    infoBox("Quiosque",
            sum(filtro_base_comod_geral()$Qtd[str_detect(filtro_base_comod_geral()$Produto, "Quiosque")],na.rm = TRUE),
            color = "primary", 
            icon = icon(NULL, class = "custom-icon-quiosque"))
  })
  
  output$card_cevs_gelaplaca = renderInfoBox({
    req(filtro_base_comod_geral())
    
    infoBox("Gelaplaca",
            sum(filtro_base_comod_geral()$Qtd[str_detect(filtro_base_comod_geral()$Produto, "Gelo Placa")],na.rm = TRUE),
            color = "primary", 
            icon = icon(NULL, class = "custom-icon-gelapl"))
  })
  
  output$cards_comodatos <- renderUI({
    if(!str_detect(revenda_query(), "ESPECIAL")){
      fluidRow(
        column(5,
               fluidRow(
                 infoBoxOutput("card_prz_curto"),
                 infoBoxOutput("card_cli_inad"),
                 infoBoxOutput("card_cevs_abertos")
               )
        ),
        column(7,
               fluidRow(
                 infoBoxOutput("card_cevs_cerv1l", 3),
                 infoBoxOutput("card_cevs_cerv300", 3),
                 infoBoxOutput("card_cevs_cerv600hnk", 3),
                 infoBoxOutput("card_cevs_cerv600", 3)
               )
        )
      )
    } else {
      fluidRow(
        column(5,
               fluidRow(
                 infoBoxOutput("card_cli_inad"),
                 infoBoxOutput("card_cevs_abertos"),
                 infoBoxOutput("card_cevs_carrinho_amb")
               )
        ),
        column(7,
               fluidRow(
                 infoBoxOutput("card_cevs_horizontal", 3),
                 infoBoxOutput("card_cevs_vertical", 3),
                 infoBoxOutput("card_cevs_quiosque", 3),
                 infoBoxOutput("card_cevs_gelaplaca", 3)
               )
        )
      )
    }
  })
  
  # UI ----------------------------------------------------------------------
  
  fluidRow(
    box(
      id = "box_comodatos_filtro",
      title = fluidRow(
        column(5, searchInput("cevcli_input_comod", "Pesquisar CEV", btnSearch = icon("magnifying-glass"),btnReset = icon("xmark"),width = "100%")),
        # column(1, pickerInput("ghost2", "Ghost 2", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
        # column(1, pickerInput("ghost3", "Ghost 3", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
        # column(1, pickerInput("ghost4", "Ghost 4", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
        # column(1, pickerInput("ghost5", "Ghost 5", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
        column(1, pickerInput("interv_input_comod", "Intervalo", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("produt_input_comod", "Produto", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("inadim_input_comod", "Inadimplência", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("prazoi_input_comod", "Prazo", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("usuari_input_comod", "Usuário", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
        column(1, pickerInput("status_input_comod", "Status", choices = NULL, multiple = TRUE, options = opcoes_filtro)),
        column(1, style = "display: flex; align-items: center;",
               column(1),
               column(9, actionButton("bt_limpacomod",label = NULL, icon = icon("eraser"),status = "primary",size = "lg",width = "100%") %>% tagAppendAttributes(title = "Limpar filtros")),
               column(1)
        )
        
      ),
      width = 12,
      status = "primary",
      collapsible = FALSE
    ),
    
    uiOutput("cards_comodatos")
    ,
    
    box(
      id = "tabela_detal_comodatos",
      title = "Comodatos",
      width = 12,
      withSpinner(reactableOutput("tabela_consol_comodato"),type = 4,color = cores_reativo()[2])
    ),
    
    downloadButton("bt_download_pdf_distrato", style = "visibility: hidden; position:absolute; left:-9999px;")
    
  )
  
}