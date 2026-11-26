library(promises)
library(future)

plan(sequential) # portfólio: no navegador não há outro processo para o future usar

# Carregar dados ----------------------------------------------------------

source(glue("{diretorio}pages/Comodatos/Dados/dados_comodato.R"), local = TRUE, encoding = "UTF-8")
source(glue("{diretorio}pages/Comodatos/Dados/funcoes_data_cor.R"), local = TRUE, encoding = "UTF-8")


pag_comodatos_saldo = function(){
  


  # Server ------------------------------------------------------------------

  saldo_geral_comodato <- reactive({
    req(input$data_input_comod_saldo)
    saldo_geral(input$data_input_comod_saldo, input$produt_input_comod_saldo)
  })
  
  produto_geral_comodato = reactive({
    # req(input$data_input_comod_saldo)
    unique(produtos_livro_fiscal())
  })
  
  # Botoes e filtros --------------------------------------------------------
  ### Botoes --------------------------------------------------------
  
  #### Limpa filtros -----------------------------------------
  observeEvent(input$bt_limpacomod_saldo, {
    updatePickerInput(session,inputId = "produt_input_comod_saldo",selected = character(0))
    updatePickerInput(session,inputId = "data_input_comod_saldo",selected = "Mês Atual")
  })
  
  #### Atualiza -----------------------------------------------------
  
  observeEvent(input$bt_refresh_id_comod_sld_revendas, {
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
  
  output$ui_produto_comod_saldo = renderUI({
    req(produto_geral_comodato())
    
    pickerInput(
      inputId = "produt_input_comod_saldo",
      label = "Produto",
      choices = setNames(unique(produto_geral_comodato()$PRODUTO),paste0(unique(produto_geral_comodato()$PRODUTO), " - ", unique(produto_geral_comodato()$PRODUTO_GENERICO))),
      multiple = TRUE,
      options = opcoes_filtro
    )
  })
  
  # Tabela consolidada ------------------------------------------------------

  output$tabela_saldo_comodato = renderReactable({
    req(saldo_geral_comodato())
    
    # acomp_log_www/img/produtos/152597.svg
    # acomp_log_www/img/produtos/215209.svg
    # acomp_log_www/img/produtos/107522.svg
    reactable(
      saldo_geral_comodato(),
      defaultColDef = colDef(align = "center"),
      columns = list(
        .selection = colDef(show = FALSE),
        Nome = colDef(minWidth = 150, align = "left",headerStyle = list(display = "flex", alignItems = "center")),
        `Recolha Ano` = colDef(format = colFormat(separators = TRUE),headerStyle = list(display = "flex", alignItems = "center")),
        `Empréstimo Ano` = colDef(format = colFormat(separators = TRUE),headerStyle = list(display = "flex", alignItems = "center")),
        `Saldo Ano` = colDef(format = colFormat(separators = TRUE),headerStyle = list(display = "flex", alignItems = "center")),
        `Recolha Mês` = colDef(format = colFormat(separators = TRUE),headerStyle = list(display = "flex", alignItems = "center")),
        `Empréstimo Mês` = colDef(format = colFormat(separators = TRUE),headerStyle = list(display = "flex", alignItems = "center")),
        `Saldo Mês` = colDef(format = colFormat(separators = TRUE),headerStyle = list(display = "flex", alignItems = "center")),
        `Status PLP` = colDef(style = function(value){
          if(value == "Bloqueado"){
            list(color = "#A1343C", fontWeight = "bold")
          }
          else{
            list(color = "#008D21", fontWeight = "bold")
          }
        },headerStyle = list(display = "flex", alignItems = "center")),
        `Status Doc` = colDef(
          style = function(value){
          if(value == "Bloqueado"){
            list(color = "#A1343C", fontWeight = "bold")
          }
          else{
            list(color = "#008D21", fontWeight = "bold")
          }
        },headerStyle = list(display = "flex", alignItems = "center")),
        `Caixa 1L` = colDef(name = HTML('
                              <div style="display: flex; align-items: center;">
                                <img src="acomp_log_www/img/produtos/107522.svg" height="36"">
                                <span>Caixa 1L</span>
                              </div>
                            '),
                            format = colFormat(separators = TRUE),
                            html = TRUE, 
                            headerStyle = list(display = "flex", alignItems = "center"),
                            style = list(background = "#F7EBB7")),
        `Caixa 300` = colDef(name = HTML('
                              <div style="display: flex; align-items: center;">
                                <img src="acomp_log_www/img/produtos/152597.svg" height="36"">
                                <span>Caixa 300</span>
                              </div>
                            '),
                             format = colFormat(separators = TRUE),
                             html = TRUE, 
                             headerStyle = list(display = "flex", alignItems = "center"),
                             style = list(background = "#F7EBB7")),
        `Total MAR 600` = colDef(name = HTML('
                              <div style="display: flex; align-items: center;">
                                <img src="acomp_log_www/img/produtos/215209.svg" height="36"">
                                <span>Total MAR 600</span>
                              </div>
                            '),
                                 format = colFormat(separators = TRUE),
                                 html = TRUE, 
                                 headerStyle = list(display = "flex", alignItems = "center"),
                                 style = list(background = "#F7EBB7")),
        `Caixa MAR 600` = colDef(name = HTML('
                              <div style="display: flex; align-items: center;">
                                <img src="acomp_log_www/img/produtos/215209.svg" height="36"">
                                <span>Caixa MAR 600</span>
                              </div>
                            '),
                                 format = colFormat(separators = TRUE),
                                 html = TRUE, headerStyle = list(display = "flex", alignItems = "center")),
        `Bônus MAR 600` = colDef(name = HTML('
                              <div style="display: flex; align-items: center;">
                                <img src="acomp_log_www/img/produtos/215209.svg" height="36"">
                                <span>Bônus MAR 600</span>
                              </div>
                            '),
                                 format = colFormat(separators = TRUE),
                                 html = TRUE, headerStyle = list(display = "flex", alignItems = "center")),
        `Caixa 600ml` = colDef(name = HTML('
                              <div style="display: flex; align-items: center;">
                                <img src="acomp_log_www/img/produtos/107522.svg" height="36"">
                                <span>Caixa 600ml</span>
                              </div>
                            '),
                               format = colFormat(separators = TRUE),
                               html = TRUE, headerStyle = list(display = "flex", alignItems = "center"))
      ),
      wrap = TRUE,
      height = "58vh",
      pagination = FALSE,
      compact = TRUE,
      highlight = TRUE,
      selection = "single",
      onClick = "select",
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
  
  fluidRow(
    box(
      id = "box_comodatos_saldo_filtro",
      title = fluidRow(
        column(1, uiOutput("ui_produto_comod_saldo")),
        column(1, pickerInput("ghost1", "Ghost 2", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
        column(1, pickerInput("ghost2", "Ghost 2", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
        column(1, pickerInput("ghost3", "Ghost 3", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
        column(1, pickerInput("ghost4", "Ghost 4", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
        column(1, pickerInput("ghost5", "Ghost 5", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
        column(1, pickerInput("ghost6", "Ghost 2", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
        column(1, pickerInput("ghost7", "Ghost 2", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
        column(1, pickerInput("ghost8", "Ghost 3", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
        column(1, pickerInput("ghost9", "Ghost 4", choices = NULL, multiple = TRUE), style = "visibility: hidden;"),
        column(1, pickerInput("data_input_comod_saldo", "Mês", choices = unique(data_calend()$Mes), multiple = FALSE,selected = "Mês Atual", options = opcoes_filtro)),
        column(1, style = "display: flex; align-items: center;",
               column(1),
               column(9, actionButton("bt_limpacomod_saldo",label = NULL, icon = icon("eraser"),status = "primary",size = "lg",width = "100%") %>% tagAppendAttributes(title = "Limpar filtros")),
               column(1)
        )
  
      ),
      width = 12,
      status = "primary",
      collapsible = FALSE
    ),
    box(
      id = "tabela_saldo_comodatos",
      title = "Saldo Revendas",
      width = 12,
      withSpinner(reactableOutput("tabela_saldo_comodato"),type = 4,color = cores_reativo()[2])
    )
    
  )
  
}