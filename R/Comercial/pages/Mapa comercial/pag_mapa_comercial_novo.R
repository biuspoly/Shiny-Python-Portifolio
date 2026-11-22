pag_mapa_comercial_novo <- function() {

  if (length(revenda_query()) == 0) {
    return(fluidPage(h1("Aba em manutenção")))
  }

  if (str_detect(revenda_query(), "GRUPO")) {
    return(fluidPage(
      div(style = "padding: 60px 20px; text-align: center; color: #666;",
          h3("Selecione uma revenda específica no filtro superior para visualizar o Mapa Comercial."))
    ))
  }

  # DEPENDENCIAS --------------------------------------------------------------

  source(glue("{diretorio}pages/Mapa comercial/Dados/dados_mapa_comercial.R"),  local = TRUE, encoding = "UTF-8")
  source(glue("{diretorio}pages/Mapa comercial/Dados/funcoes_cores_mc.R"),       local = TRUE, encoding = "UTF-8")

  # Vendedor, Classificacao Cliente e Categoria Prod ficam exclusivos da
  # ESPECIAL. GA nao e exibido para nenhuma revenda.
  filtros_especial_mc <- any(str_detect(toupper(revenda_query()), "ESPECIAL"))

  # Botao Revenda/Fabrica: so nas revendas com mais de uma sede de verdade (ver
  # REVENDAS_ESCOLHE_DISTANCIA_MC em dados_mapa_comercial.R). Nas outras o botao
  # nao e montado e mapa_pot() usa sempre a distancia ate a fabrica.
  escolhe_distancia_mc <- escolhe_base_distancia_mc(revenda_query())

  # 1. FILTRO DE MES -------------------------------------------------------------

  meses_mc_rv <- reactive({
    meses_disponiveis_mc(revenda = revenda_query())
  })

  observe({
    meses <- meses_mc_rv()
    req(length(meses) > 0)
    updatePickerInput(session, "mes_mc", choices = meses, selected = head(meses, 1))
  })

  # 2. DADOS - Query com cache de sessao ------------------------------------------

  # bindCache evita reprocessar o mapa (joins/sf/leaflet) quando a combinacao
  # revenda + mes ja foi visitada nesta sessao; fonte_parquet_mc le os parquets
  # gravados por atualiza_mapa_comercial.R (sem ida ao MariaDB a cada troca)

  # Opcoes dos pickerInput de produto/vendedor/classificacao, restritas ao que
  # a revenda tem em TB_MAPA_POT (a maioria) ou TB_CLI_ATIVOS (PORTE)
  opcoes_filtro_mc_rv <- reactive({
    opcoes_filtro_produto_mc(revenda = revenda_query())
  })

  observe({
    opcoes_produto_mc <- opcoes_filtro_mc_rv()
    updatePickerInput(
      session, "mc_canal_filtro",
      choices  = opcoes_produto_mc$canal,
      selected = intersect(isolate(input$mc_canal_filtro), opcoes_produto_mc$canal)
    )
    updatePickerInput(session, "mc_embalagem_filtro",       choices = opcoes_produto_mc$embalagem)
    updatePickerInput(
      session, "mc_marca_filtro",
      choices  = opcoes_produto_mc$marca,
      selected = intersect(isolate(input$mc_marca_filtro), opcoes_produto_mc$marca)
    )

    if (filtros_especial_mc) {
      updatePickerInput(session, "mc_classif_cliente_filtro", choices = opcoes_produto_mc$porte)
      updatePickerInput(session, "mc_categoria_filtro",       choices = opcoes_produto_mc$categoria)
      updatePickerInput(session, "mc_vendedor_filtro",        choices = opcoes_produto_mc$vendedor)
    }
  })

  # Crossfilter entre os 6 pickers de produto/vendedor - mesmo padrao usado
  # em Curva ABC/Pedidos Cancelados etc.: um reativo com a base (aqui, as
  # combinacoes de TB_MAPA_POT) ja filtrada por tudo que esta selecionado, e
  # um observer que atualiza as opcoes dos OUTROS pickers a partir dela. O
  # picker que a pessoa acabou de mexer nao e sobrescrito (por isso o
  # "if is.null/length == 0" antes de cada updatePickerInput) - so quem
  # ainda esta em "Todos" ganha a lista restrita ao que sobrou.
  # Classificacao Cliente (porte) fica de fora - vem de TB_CLI_ATIVOS, tabela
  # sem essas colunas de produto.
  combinacoes_produto_mc_rv <- reactive({
    combinacoes_filtro_produto_mc(revenda = revenda_query())
  })

  filtro_combinacoes_produto_mc <- reactive({
    req(combinacoes_produto_mc_rv())
    combinacoes_produto_mc_rv() %>%
      filter(
        if (is.null(input$mc_marca_filtro)     || length(input$mc_marca_filtro)     == 0) TRUE else MARCA      %in% input$mc_marca_filtro,
        if (is.null(input$mc_canal_filtro)     || length(input$mc_canal_filtro)     == 0) TRUE else CANAL_PROD %in% input$mc_canal_filtro,
        if (!filtros_especial_mc || is.null(input$mc_categoria_filtro) || length(input$mc_categoria_filtro) == 0) TRUE else SEGMENTO %in% input$mc_categoria_filtro,
        if (is.null(input$mc_embalagem_filtro) || length(input$mc_embalagem_filtro) == 0) TRUE else VOLUME     %in% input$mc_embalagem_filtro,
        if (!filtros_especial_mc || is.null(input$mc_vendedor_filtro) || length(input$mc_vendedor_filtro) == 0) TRUE else VEN %in% input$mc_vendedor_filtro
      )
  })

  observeEvent(filtro_combinacoes_produto_mc(), {
    combinacoes <- filtro_combinacoes_produto_mc()

    if (is.null(input$mc_marca_filtro) || length(input$mc_marca_filtro) == 0)
      updatePickerInput(
        session, "mc_marca_filtro",
        choices = sort(unique(combinacoes$MARCA[!is.na(combinacoes$MARCA)]))
      )
    if (is.null(input$mc_canal_filtro) || length(input$mc_canal_filtro) == 0) {
      opcoes_canal_mc <- sort(unique(combinacoes$CANAL_PROD[!is.na(combinacoes$CANAL_PROD)]))
      if (!filtros_especial_mc) {
        opcoes_canal_mc <- opcoes_canal_mc[
          !toupper(trimws(opcoes_canal_mc)) %in% c("CHOPP", "OUTRO")
        ]
      }
      updatePickerInput(session, "mc_canal_filtro", choices = opcoes_canal_mc)
    }
    if (filtros_especial_mc &&
        (is.null(input$mc_categoria_filtro) || length(input$mc_categoria_filtro) == 0))
      updatePickerInput(session, "mc_categoria_filtro", choices = sort(unique(combinacoes$SEGMENTO)))
    if (is.null(input$mc_embalagem_filtro) || length(input$mc_embalagem_filtro) == 0)
      updatePickerInput(session, "mc_embalagem_filtro", choices = sort(unique(combinacoes$VOLUME)))
    if (filtros_especial_mc &&
        (is.null(input$mc_vendedor_filtro) || length(input$mc_vendedor_filtro) == 0))
      updatePickerInput(session, "mc_vendedor_filtro",  choices = sort(unique(combinacoes$VEN)))
  })

  # Um unico picker vazio (NULL/character(0)) equivale a "Todos" (sem filtro
  # naquele campo) - ver mapa_pot() no dados_mapa_comercial.R
  # base_distancia_mc(): "fabrica" fixo nas revendas sem o botao - nelas o input
  # nao existe, entao req(input$mc_base_distancia) travaria a pagina pra sempre
  # (e o bindCache abaixo receberia NULL).
  base_distancia_mc <- reactive({
    if (!escolhe_distancia_mc) return("fabrica")
    input$mc_base_distancia
  })

  dados_mapa_rv <- reactive({
    req(input$mes_mc, base_distancia_mc())
    tryCatch(
      mapa_pot(
        revenda        = revenda_query(),
        mes_atual      = input$mes_mc,
        marca          = input$mc_marca_filtro,
        canal          = input$mc_canal_filtro,
        categoria      = if (filtros_especial_mc) input$mc_categoria_filtro else NULL,
        embalagem      = input$mc_embalagem_filtro,
        ga             = NULL,
        vendedor       = if (filtros_especial_mc) input$mc_vendedor_filtro else NULL,
        porte          = if (filtros_especial_mc) input$mc_classif_cliente_filtro else NULL,
        base_distancia = base_distancia_mc()
      ),
      error = function(e) list(erro = conditionMessage(e))
    )
  }) %>% bindCache(
    revenda_query(), input$mes_mc,
    input$mc_marca_filtro, input$mc_canal_filtro,
    if (filtros_especial_mc) input$mc_categoria_filtro else NULL,
    input$mc_embalagem_filtro,
    if (filtros_especial_mc) input$mc_vendedor_filtro else NULL,
    if (filtros_especial_mc) input$mc_classif_cliente_filtro else NULL,
    base_distancia_mc(),
    cache = "session"
  )

  ## Pre-carregamento ao abrir a pagina ----

  observe({ dados_mapa_rv() })

  # Altura unica: aplicada direto no leafletOutput/reactable de cada aba e no
  # `height` do box() (que define o tamanho da .card-body no bs4Dash). Mesmo
  # padrao usado em Pedidos Cancelados/Bonificados (reactable com height fixo
  # em vh) - herdar height:100% em cascata por varias divs (withSpinner etc.)
  # se mostrou fragil, entao aqui cada elemento recebe o valor direto.
  altura_box_mc <- "calc(100vh - 150px)"

  # Tabelas ficam um pouco menores que o box para nao encostar nas bordas;
  # a do Saiba Mais desconta tambem a altura dos cards que aparecem acima dela
  altura_tabela_mc            <- "calc(100vh - 190px)"
  altura_tabela_saiba_mais_mc <- "calc(100vh - 420px)"

  # 3. MAPA ------------------------------------------------------------------

  # Quando o mes selecionado ainda nao tem dados processados (mapa_pot lanca
  # erro), mostra um aviso em vez do mapa em branco/travado

  # box_mc_mapa_conteudo so alterna entre "erro" e o bloco estatico com as 4 abas
  # (mapa + 3 tabelas). As abas em si sao mostradas/escondidas via conditionalPanel
  # (JS, condicionado a input$mc_aba_visualizacao) em vez de recriadas a cada troca
  # de aba - antes, como as 4 visualizacoes eram um if/else dentro do renderUI, ao
  # trocar de aba o painel de cards (absolutePanel) as vezes nao era desmontado a
  # tempo e ficava visivel por cima da tabela nova
  output$box_mc_mapa_conteudo <- renderUI({
    mapa_potencial_dados <- dados_mapa_rv()

    if (!is.null(mapa_potencial_dados$erro)) {
      div(style = "padding: 60px 20px; text-align: center; color: #a33;",
          icon("triangle-exclamation"), " ", mapa_potencial_dados$erro)
    } else {
      tagList(
        conditionalPanel(
          condition = "input.mc_aba_visualizacao == 'Potencial'",
          div(
            style = "position: relative;",
            withSpinner(leafletOutput("mapa_mc_leaflet", height = altura_box_mc), type = 4, color = cores_reativo()[2]),
            absolutePanel(
              top = 10, left = 50, right = "auto", bottom = "auto",
              draggable = FALSE, style = "z-index: 1000;",
              uiOutput("mapa_mc_cards")
            )
          )
        ),
        conditionalPanel(
          condition = "input.mc_aba_visualizacao == 'Saiba Mais'",
          div(
            uiOutput("mapa_mc_cards_saiba_mais"),
            div(
              style = "margin-top: 24px;",
              withSpinner(reactableOutput("tabela_mc_saiba_mais"), type = 4, color = cores_reativo()[2])
            )
          )
        ),
        conditionalPanel(
          condition = "input.mc_aba_visualizacao == 'Ruptura 6M+'",
          withSpinner(reactableOutput("tabela_mc_ruptura_6m"), type = 4, color = cores_reativo()[2])
        ),
        conditionalPanel(
          condition = "input.mc_aba_visualizacao == 'Clientes Inativos'",
          withSpinner(reactableOutput("tabela_mc_clientes_inativos"), type = 4, color = cores_reativo()[2])
        )
      )
    }
  })

  output$mapa_mc_leaflet <- renderLeaflet({
    mapa_potencial_dados <- dados_mapa_rv()
    req(is.null(mapa_potencial_dados$erro))
    mapa_potencial_dados$mapa_potencial
  })

  output$mapa_mc_cards <- renderUI({
    mapa_potencial_dados <- dados_mapa_rv()
    req(is.null(mapa_potencial_dados$erro))
    mapa_potencial_dados$cards
  })

  # Mesmo conteudo de mapa_mc_cards, mas em output separado: o id de um
  # uiOutput nao pode se repetir no DOM (mesmo com o outro escondido pelo
  # conditionalPanel), entao o Saiba Mais tem a sua propria copia do output
  output$mapa_mc_cards_saiba_mais <- renderUI({
    mapa_potencial_dados <- dados_mapa_rv()
    req(is.null(mapa_potencial_dados$erro))
    mapa_potencial_dados$cards
  })

  # 4. ABAS ALTERNATIVAS (Saiba Mais / Ruptura 6M+ / Clientes Inativos) -------

  # Combobox custom (input + lista propria em vez de <select>/<datalist>
  # nativos): digitar filtra os itens da lista e a tabela ao mesmo tempo;
  # clicar num item seleciona ele. Trocado do <input type="search" list=...>
  # porque o datalist nativo do navegador: (1) nao da pra limitar a altura
  # nem colocar scroll, (2) desenha um icone proprio no canto direito do
  # campo, (3) em alguns navegadores perde o background customizado ao
  # digitar. As funcoes JS (mcFiltroDigitar/Abrir/Fechar/Escolher) ficam
  # definidas uma unica vez no <script> da UI (fluidPage), reaproveitadas por
  # todo filtro criado aqui. trimws()/data-valor (em vez de innerText) evitam
  # mismatch entre a opcao e o valor real da celula quando o dado vem com
  # espaco sobrando (ex.: MUNICIPIO). Roda 100% no navegador via
  # Reactable.setFilter - nao depende do servidor Shiny.
  filtro_dropdown_mc <- function(id_tabela) {
    function(valores_coluna, id_coluna) {
      valores_unicos_coluna <- sort(unique(trimws(as.character(valores_coluna))))
      id_lista_opcoes       <- paste0("mc-lista-", id_tabela, "-", id_coluna)

      tags$div(
        class = "mc-filtro-wrap",
        tags$input(
          type         = "text",
          class        = "mc-filtro-combo",
          placeholder  = "Todos",
          "aria-label" = sprintf("Filtrar %s", id_coluna),
          oninput      = sprintf("mcFiltroDigitar(event, '%s', '%s')", id_tabela, id_coluna),
          onfocus      = sprintf("mcFiltroAbrir(event, '%s', '%s')",   id_tabela, id_coluna),
          onblur       = "mcFiltroFechar(event)"
        ),
        tags$div(
          id    = id_lista_opcoes,
          class = "mc-filtro-lista",
          style = "display: none;",
          tags$div(
            class        = "mc-filtro-opcao mc-filtro-opcao-todos",
            "data-valor" = "",
            onmousedown  = sprintf("mcFiltroEscolher(event, '%s', '%s')", id_tabela, id_coluna),
            "Todos"
          ),
          lapply(valores_unicos_coluna, function(valor_opcao) {
            tags$div(
              class        = "mc-filtro-opcao",
              "data-valor" = valor_opcao,
              onmousedown  = sprintf("mcFiltroEscolher(event, '%s', '%s')", id_tabela, id_coluna),
              valor_opcao
            )
          })
        )
      )
    }
  }

  linguagem_tabela_mc <- reactableLang(
    pageNext             = "Próxima",
    pagePrevious         = "Anterior",
    pageNumbers          = "{página} of {páginas}",
    pageInfo             = "{rowStart}–{rowEnd} de {rows} linhas",
    pageSizeOptions      = "Mostrar {rows}",
    pageNextLabel        = "Próxima página",
    pagePreviousLabel    = "Página anterior",
    pageNumberLabel      = "Pág {page}",
    pageJumpLabel        = "Ir para a página",
    pageSizeOptionsLabel = "Linhas por página"
  )

  output$tabela_mc_saiba_mais <- renderReactable({
    mapa_potencial_dados <- dados_mapa_rv()
    req(is.null(mapa_potencial_dados$erro))

    tabela_saiba_mais <- saiba_mais_cli(mapa_potencial_dados)
    formata_percentual_saiba_mais_mc <- function(value) {
      ifelse(is.na(value), NA, paste0(format(round(value, 2), big.mark = ".", decimal.mark = ",", nsmall = 2), "%"))
    }
    formata_moeda_saiba_mais_mc <- function(value) {
      ifelse(is.na(value), NA, paste0("R$ ", format(round(value, 2), big.mark = ".", decimal.mark = ",", nsmall = 2)))
    }

    reactable(
      tabela_saiba_mais,
      theme               = tema_reactable_mc,
      columns             = list(
        COD_IBGE         = colDef(show = FALSE),
        COR_POT_PROX_NVL = colDef(show = FALSE),
        COR_AREA         = colDef(show = FALSE),
        COR_PERC_CLI_ATIVO = colDef(show = FALSE),
        CIDADE           = colDef(name = "Município",             align = "left", minWidth = 130, headerStyle = cor_cabecalho_mc("CIDADE",          "left"), style = cor_coluna_mc(tabela_saiba_mais$COR_AREA)),
        # Acompanha o botao Revenda/Fabrica do cabecalho do box (a coluna ja
        # vem de mapa_pot() na base escolhida) - NA = sem distancia cadastrada
        DISTANCIA        = colDef(name = "Distância<br>(km)", html = TRUE,        headerStyle = cor_cabecalho_mc("DISTANCIA"), format = colFormat(separators = TRUE, digits = 0, locales = "pt-BR")),
        POPULACAO        = colDef(name = "População",                                          headerStyle = cor_cabecalho_mc("POPULACAO"), format = colFormat(separators = TRUE, locales = "pt-BR")),
        CLI_ATIVO        = colDef(name = "Clientes",                                           headerStyle = cor_cabecalho_mc("CLI_ATIVO"), format = colFormat(separators = TRUE, locales = "pt-BR")),
        POTENCIAL        = colDef(name = "Potencial",                                          headerStyle = cor_cabecalho_mc("POTENCIAL"), format = colFormat(separators = TRUE, locales = "pt-BR")),
        PERC_CLI_POT_75  = colDef(name = "Cob Potencial<br>Min (75%)", html = TRUE,             headerStyle = cor_cabecalho_mc("PERC_CLI_POT_75"), cell = formata_percentual_saiba_mais_mc),
        POT_CRESC        = colDef(name = "Potencial<br>Crescim.",      html = TRUE,             headerStyle = cor_cabecalho_mc("POT_CRESC"), format = colFormat(separators = TRUE, locales = "pt-BR")),
        VOLUME_HL        = colDef(name = "HL",                                                 headerStyle = cor_cabecalho_mc("VOLUME_HL"), format = colFormat(separators = TRUE, locales = "pt-BR")),
        QTD_UMB          = colDef(name = "UMB",                                                headerStyle = cor_cabecalho_mc("QTD_UMB"), format = colFormat(separators = TRUE, locales = "pt-BR")),
        QTD_PDV          = colDef(name = "Clientes<br>Cobertos",       html = TRUE,             headerStyle = cor_cabecalho_mc("QTD_PDV"), format = colFormat(separators = TRUE, locales = "pt-BR")),
        POT_PROX_NVL     = colDef(name = "Falta Próx.<br>Nível",       html = TRUE,             headerStyle = cor_cabecalho_mc("POT_PROX_NVL"), format = colFormat(separators = TRUE, locales = "pt-BR")),
        PERC_CLI_ATIVO   = colDef(name = "% Ativos",                                        headerStyle = cor_cabecalho_mc("PERC_CLI_ATIVO"), cell = formata_percentual_saiba_mais_mc, style = cor_coluna_mc(tabela_saiba_mais$COR_PERC_CLI_ATIVO)),
        COB_POT          = colDef(name = "% Potencial",                                     headerStyle = cor_cabecalho_mc("COB_POT"), cell = formata_percentual_saiba_mais_mc, style = cor_coluna_mc(tabela_saiba_mais$COR_AREA)),
        FAT_HAB          = colDef(name = "R$/Hab",                                             headerStyle = cor_cabecalho_mc("FAT_HAB"), cell = formata_moeda_saiba_mais_mc, style = cor_fundo_fat_hab_mc)
      ),
      defaultColDef       = colDef(align = "center", minWidth = 80),
      defaultSorted       = list(CLI_ATIVO = "desc"),
      resizable           = TRUE,
      pagination          = TRUE,
      defaultPageSize     = 50,
      pageSizeOptions     = c(50, 100, 500),
      showPageSizeOptions = TRUE,
      wrap                = FALSE,
      height              = altura_tabela_saiba_mais_mc,
      language            = linguagem_tabela_mc,
      style               = list(overflowX = "auto")
    )
  })

  # Reativos compartilhados entre a tabela e os cards (Titulos/Comodatos em
  # aberto, Ultima Compra por ano) de cada aba - assim ruptura_6m()/
  # clientes_inativos() sao calculados uma unica vez por invalidacao, nao
  # uma vez pra tabela e outra pros cards
  tabela_ruptura_6m_rv <- reactive({
    mapa_potencial_dados <- dados_mapa_rv()
    req(is.null(mapa_potencial_dados$erro))
    ruptura_6m(mapa_potencial_dados)
  })

  tabela_clientes_inativos_rv <- reactive({
    mapa_potencial_dados <- dados_mapa_rv()
    req(is.null(mapa_potencial_dados$erro))
    clientes_inativos(mapa_potencial_dados)
  })

  # Cards simples no lugar dos filtros de produto (que nao se aplicam aqui) -
  # Titulos/Comodatos em aberto e Ultima Compra por ano, calculados em cima
  # do mesmo dado que ja alimenta a tabela de cada aba (tabela_..._rv)
  card_simples_mc <- function(rotulo_card, valor_card, cor_card = "#06825D") {
    tags$div(
      style = glue("background: #fff; border: 1px solid {cor_card}; border-radius: 4px;
                     padding: 6px 4px; margin-bottom: 6px; text-align: center;"),
      tags$div(style = glue("font-size: 14px; color: {cor_card}; font-weight: bold;"), rotulo_card),
      tags$div(style = "font-size: 26px; font-weight: bold; color: #333;", valor_card)
    )
  }

  cards_clientes_mc <- function(clientes_filtrados) {
    ano_atual          <- as.integer(format(Sys.Date(), "%Y"))
    anos_ultima_compra <- seq(ano_atual, ano_atual - 2)
    # gradiente verde -> cinza (ano atual verde, o do meio um verde acinzentado
    # de transicao, o mais antigo cinza) - sinaliza visualmente o quao antiga
    # esta a ultima compra
    cores_anos_ultima_compra <- c("#06825D", "#397C6D", "#6c757d")

    tagList(
      card_simples_mc("Clientes com Títulos em Aberto",   format(sum(clientes_filtrados$TITULO_ABERTO == "Sim", na.rm = TRUE), big.mark = ".", decimal.mark = ","), cor_card = "#c0392b"),
      card_simples_mc("Clientes com Comodatos em Aberto", format(sum(clientes_filtrados$POSSUI_CEV    == "Sim", na.rm = TRUE), big.mark = ".", decimal.mark = ","), cor_card = "#c0392b"),
      lapply(seq_along(anos_ultima_compra), function(indice_ano_compra) {
        ano_compra <- anos_ultima_compra[indice_ano_compra]
        card_simples_mc(
          glue("Clientes com Últ. Compra em {ano_compra}"),
          format(sum(format(clientes_filtrados$ULTIMA_COMPRA, "%Y") == as.character(ano_compra), na.rm = TRUE), big.mark = ".", decimal.mark = ","),
          cor_card = cores_anos_ultima_compra[indice_ano_compra]
        )
      })
    )
  }

  output$mc_cards_ruptura_6m <- renderUI({
    cards_clientes_mc(tabela_ruptura_6m_rv())
  })

  output$mc_cards_clientes_inativos <- renderUI({
    cards_clientes_mc(tabela_clientes_inativos_rv())
  })

  # Downloads das listas completas exibidas nas duas abas. PESQUISA_CLI e uma
  # coluna tecnica do reactable e nao deve aparecer no arquivo entregue.
  output$bt_download_mc_ruptura_6m <- downloadHandler(
    filename = function() paste0("mapa-comercial-ruptura-6m-", Sys.Date(), ".xlsx"),
    content = function(file) {
      dados_download <- tabela_ruptura_6m_rv() %>%
        select(-any_of("PESQUISA_CLI"))
      writexl::write_xlsx(dados_download, file)
    }
  )

  output$bt_download_mc_clientes_inativos <- downloadHandler(
    filename = function() paste0("mapa-comercial-clientes-inativos-", Sys.Date(), ".xlsx"),
    content = function(file) {
      dados_download <- tabela_clientes_inativos_rv() %>%
        select(-any_of("PESQUISA_CLI"))
      writexl::write_xlsx(dados_download, file)
    }
  )

  output$tabela_mc_ruptura_6m <- renderReactable({
    tabela_ruptura_6m <- tabela_ruptura_6m_rv()

    reactable(
      tabela_ruptura_6m,
      theme               = tema_reactable_mc,
      filterable          = TRUE,
      columns             = list(
        PESQUISA_CLI  = colDef(show = FALSE),
        CLI_ATIVO     = colDef(name = "Código",                                        headerStyle = cor_cabecalho_mc("CLI_ATIVO")),
        NOME          = colDef(name = "Nome",          align = "left", minWidth = 160, headerStyle = cor_cabecalho_mc("NOME",         "left")),
        FANTASIA      = colDef(name = "Fantasia",      align = "left", minWidth = 130, headerStyle = cor_cabecalho_mc("FANTASIA",     "left")),
        MUNICIPIO     = colDef(name = "Município",     align = "left",                 headerStyle = cor_cabecalho_mc("MUNICIPIO",    "left")),
        ENDERECO      = colDef(name = "Endereço",      align = "left", minWidth = 160, headerStyle = cor_cabecalho_mc("ENDERECO",     "left")),
        PORTE         = colDef(name = "Classificação",                                 headerStyle = cor_cabecalho_mc("PORTE")),
        CANAL         = colDef(name = "Canal",                                         headerStyle = cor_cabecalho_mc("CANAL")),
        VEN           = colDef(name = "Ven",                                           headerStyle = cor_cabecalho_mc("VEN")),
        TITULO_ABERTO = colDef(name = "Títulos<br>Abertos",   html = TRUE,                headerStyle = cor_cabecalho_mc("TITULO_ABERTO")),
        POSSUI_CEV    = colDef(name = "Comodato<br>Aberto", html = TRUE,                headerStyle = cor_cabecalho_mc("POSSUI_CEV")),
        SUBEMPRESA    = colDef(name = "Subrevenda",                                    headerStyle = cor_cabecalho_mc("SUBEMPRESA")),
        ULTIMA_COMPRA = colDef(name = "Última<br>Compra",   html = TRUE,                headerStyle = cor_cabecalho_mc("ULTIMA_COMPRA"), format = colFormat(date = TRUE, locales = "pt-BR"))
      ),
      # filterInput no default aplica o combobox verde/pesquisavel em TODAS as
      # colunas (nao so nas listadas com override individual)
      defaultColDef       = colDef(align = "center", minWidth = 80, filterInput = filtro_dropdown_mc("tabela_mc_ruptura_6m")),
      resizable           = TRUE,
      pagination          = TRUE,
      defaultPageSize     = 50,
      pageSizeOptions     = c(50, 100, 500),
      showPageSizeOptions = TRUE,
      wrap                = FALSE,
      height              = altura_tabela_mc,
      language            = linguagem_tabela_mc,
      style               = list(overflowX = "auto")
    )
  })

  output$tabela_mc_clientes_inativos <- renderReactable({
    tabela_clientes_inativos <- tabela_clientes_inativos_rv()

    reactable(
      tabela_clientes_inativos,
      theme               = tema_reactable_mc,
      filterable          = TRUE,
      columns             = list(
        PESQUISA_CLI  = colDef(show = FALSE),
        CLI_ATIVO     = colDef(name = "Código",                                        headerStyle = cor_cabecalho_mc("CLI_ATIVO")),
        NOME          = colDef(name = "Nome",          align = "left", minWidth = 160, headerStyle = cor_cabecalho_mc("NOME",         "left")),
        FANTASIA      = colDef(name = "Fantasia",      align = "left", minWidth = 130, headerStyle = cor_cabecalho_mc("FANTASIA",     "left")),
        PORTE         = colDef(name = "Porte",                                         headerStyle = cor_cabecalho_mc("PORTE")),
        CANAL         = colDef(name = "Canal",                                         headerStyle = cor_cabecalho_mc("CANAL")),
        MUNICIPIO     = colDef(name = "Município",     align = "left",                 headerStyle = cor_cabecalho_mc("MUNICIPIO",    "left")),
        ENDERECO      = colDef(name = "Endereço",      align = "left", minWidth = 160, headerStyle = cor_cabecalho_mc("ENDERECO",     "left")),
        TITULO_ABERTO = colDef(name = "Títulos<br>Abertos", html = TRUE,                  headerStyle = cor_cabecalho_mc("TITULO_ABERTO")),
        POSSUI_CEV    = colDef(name = "Comodato<br>Aberto",    html = TRUE,                  headerStyle = cor_cabecalho_mc("POSSUI_CEV")),
        SUBEMPRESA    = colDef(name = "Subempresa",                                    headerStyle = cor_cabecalho_mc("SUBEMPRESA")),
        ULTIMA_COMPRA = colDef(name = "Última<br>Compra", html = TRUE,                  headerStyle = cor_cabecalho_mc("ULTIMA_COMPRA"), format = colFormat(date = TRUE, locales = "pt-BR"))
      ),
      # filterInput no default aplica o combobox verde/pesquisavel em TODAS as
      # colunas (nao so nas listadas com override individual)
      defaultColDef       = colDef(align = "center", minWidth = 80, filterInput = filtro_dropdown_mc("tabela_mc_clientes_inativos")),
      resizable           = TRUE,
      pagination          = TRUE,
      defaultPageSize     = 50,
      pageSizeOptions     = c(50, 100, 500),
      showPageSizeOptions = TRUE,
      wrap                = FALSE,
      height              = altura_tabela_mc,
      language            = linguagem_tabela_mc,
      style               = list(overflowX = "auto")
    )
  })

  # UI ==========================================================================

  # Mesmo padrao de pickerOptions usado em Curva ABC/Comodatos etc.
  opcoes_filtro <- pickerOptions(
    noneSelectedText   = "Todos",
    size               = 5,
    style              = "btn-color",
    countSelectedText  = " {0} Itens",
    selectedTextFormat = "count > 1",
    container          = "body",
    liveSearch         = TRUE
  )

  fluidPage(
    # Combobox de filtro por coluna do reactable (Ruptura 6M+ / Clientes
    # Inativos) - mesmo verde (#06825D) dos pickerInput da pagina, acende
    # quando o filtro esta ativo; lista de opcoes mostra so ~5 itens, com
    # scroll pro resto (mesmo padrao do size = 5 do pickerInput)
    tags$style(HTML("
      .mc-filtro-wrap {
        position: relative;
        width: 100%;
      }
      .mc-filtro-combo {
        width: 100%;
        box-sizing: border-box;
        padding: 3px 6px;
        font-size: 12px;
        font-weight: normal;
        border: 1px solid #06825D;
        border-radius: 4px;
        background-color: #fff;
        color: #000;
      }
      .mc-filtro-combo::placeholder {
        color: #999;
      }
      .mc-filtro-combo:focus {
        outline: none;
        box-shadow: 0 0 0 2px rgba(6, 130, 93, 0.35);
      }
      .mc-filtro-combo.mc-filtro-ativo {
        background-color: #06825D;
        color: #fff;
      }
      .mc-filtro-combo.mc-filtro-ativo::placeholder {
        color: #e6f4ef;
      }
      .mc-filtro-lista {
        /* position: fixed (nao absolute) - o filtro fica dentro do container
           do reactable, que tem overflow: auto (scroll da tabela); um
           dropdown absolute ficaria cortado por esse overflow e pareceria
           renderizado 'por dentro' da tabela. Fixed escapa disso porque so
           e recortado por overflow em ancestral com transform/filter, o que
           nao e o caso aqui. Posicao (top/left/width) calculada em JS. */
        position: fixed;
        z-index: 3000;
        max-height: 142px;
        overflow-y: auto;
        background-color: #fff;
        border: 1px solid #06825D;
        border-radius: 4px;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
        text-align: left;
      }
      .mc-filtro-opcao {
        padding: 4px 8px;
        font-size: 12px;
        line-height: 20px;
        cursor: pointer;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        color: #000;
        font-weight: normal;
      }
      .mc-filtro-opcao:hover {
        background-color: #06825D;
        color: #fff;
      }
      .mc-filtro-opcao-todos {
        font-style: italic;
        border-bottom: 1px solid #eee;
      }
      /* Legendas de Cobertura/Distancia (addLegend, bottomleft): o tamanho
         padrao do leaflet ocupava um canto grande do mapa */
      #mapa_mc_leaflet .info.legend {
        font-size: 10.5px;
        line-height: 1.15;
        padding: 5px 8px;
      }
      #mapa_mc_leaflet .info.legend i {
        width: 12px;
        height: 12px;
        margin-right: 3px;
      }
    ")),
    tags$script(HTML("
      function mcFiltroPosicionar(input, lista) {
        var rect = input.getBoundingClientRect();
        lista.style.top   = rect.bottom + 'px';
        lista.style.left  = rect.left + 'px';
        lista.style.width = rect.width + 'px';
      }

      function mcFiltroFecharAoRolar(lista) {
        var fechar = function(ev) {
          // ignora o scroll gerado pela propria lista (a barra de rolagem
          // dos ~5 itens) - so fecha quando quem rolou foi outra coisa
          // (a tabela, a pagina etc.)
          if (ev.target === lista || lista.contains(ev.target)) return;
          lista.style.display = 'none';
          window.removeEventListener('scroll', fechar, true);
        };
        window.addEventListener('scroll', fechar, true);
      }

      function mcFiltroDigitar(ev, tabela, coluna) {
        var valor = ev.target.value;
        Reactable.setFilter(tabela, coluna, valor);
        ev.target.classList.toggle('mc-filtro-ativo', valor !== '');
        var lista = document.getElementById('mc-lista-' + tabela + '-' + coluna);
        if (!lista) return;
        var termo = valor.toLowerCase();
        lista.querySelectorAll('.mc-filtro-opcao:not(.mc-filtro-opcao-todos)').forEach(function(opcao) {
          var texto = opcao.textContent.toLowerCase();
          opcao.style.display = texto.indexOf(termo) !== -1 ? '' : 'none';
        });
        mcFiltroPosicionar(ev.target, lista);
        lista.style.display = 'block';
      }

      function mcFiltroAbrir(ev, tabela, coluna) {
        var lista = document.getElementById('mc-lista-' + tabela + '-' + coluna);
        if (!lista) return;
        mcFiltroPosicionar(ev.target, lista);
        lista.style.display = 'block';
        mcFiltroFecharAoRolar(lista);
      }

      function mcFiltroFechar(ev) {
        var input = ev.target;
        setTimeout(function() {
          var wrap  = input.closest('.mc-filtro-wrap');
          var lista = wrap ? wrap.querySelector('.mc-filtro-lista') : null;
          if (lista) lista.style.display = 'none';
        }, 150);
      }

      function mcFiltroEscolher(ev, tabela, coluna) {
        var valor = ev.currentTarget.getAttribute('data-valor');
        var wrap  = ev.currentTarget.closest('.mc-filtro-wrap');
        var input = wrap.querySelector('.mc-filtro-combo');
        input.value = valor;
        Reactable.setFilter(tabela, coluna, valor);
        input.classList.toggle('mc-filtro-ativo', valor !== '');
        wrap.querySelector('.mc-filtro-lista').style.display = 'none';
      }
    ")),
    fluidRow(
      column(
        width = 10,
        box(
          id     = "box_mc_mapa",
          title  = fluidRow(
            column(8, "Mapa Comercial - Potencial e Cobertura"),
            column(4,
              # Alterna a base das faixas de distancia do mapa: "Revenda" usa
              # DIST_SEDE (cidade -> sede da subrevenda que a atende) e
              # "Fábrica" usa DIST_FAB (cidade -> cidade da revenda). So
              # aparece em Potencial/Saiba Mais porque a distancia so se
              # reflete nas bordas/legenda do mapa e no card de Saiba Mais.
              # E so nas revendas com mais de uma sede (escolhe_distancia_mc,
              # calculado no topo) - nas outras nem o input e criado, e
              # base_distancia_mc() devolve "fabrica" fixo.
              if (escolhe_distancia_mc) {
                conditionalPanel(
                  condition = "input.mc_aba_visualizacao == 'Potencial' || input.mc_aba_visualizacao == 'Saiba Mais'",
                  # choiceValues sem acento: o valor viaja ate mapa_pot() e e
                  # comparado lá com string literal - "Fábrica" dependeria do
                  # encoding dos dois arquivos casar
                  radioGroupButtons(
                    inputId      = "mc_base_distancia",
                    label        = NULL,
                    choiceNames  = c("Revenda", "Fábrica"),
                    choiceValues = c("sede", "fabrica"),
                    selected     = "sede",
                    status       = "primary",
                    size         = "sm",
                    justified    = TRUE,
                    width        = "100%"
                  )
                )
              }
            )
          ),
          width  = 12,
          height = altura_box_mc,
          uiOutput("box_mc_mapa_conteudo")
        )
      ),
      column(
        width = 2,
        box(
          id          = "box_mc_filtro",
          title       = "Filtros",
          width       = 12,
          height      = altura_box_mc,
          status      = "primary",
          collapsible = FALSE,
          # Mes tambem so aparece em Potencial/Saiba Mais (mesma condicao dos
          # filtros de produto abaixo) - o valor selecionado continua valendo
          # nas outras abas, so o picker fica escondido
          conditionalPanel(
            condition = "input.mc_aba_visualizacao == 'Potencial' || input.mc_aba_visualizacao == 'Saiba Mais'",
            pickerInput("mes_mc", "Mês", choices = NULL,
                        options = pickerOptions(style = "btn-dv-mes", container = "body", size = 8))
          ),
          # individual = TRUE deixa cada botao com sua propria div (.btn-group),
          # em vez de um grupo conectado sem espaco entre eles; o CSS abaixo
          # empilha essas divs em coluna (com gap) e forca 100% de largura,
          # ja que o direction = "vertical" do shinyWidgets nao se aplica
          # quando individual = TRUE (fica ligado ao btn-group-vertical, que
          # so existe quando os botoes NAO sao individuais)
          radioGroupButtons(
            inputId    = "mc_aba_visualizacao",
            label      = NULL,
            choices    = c("Potencial", "Saiba Mais", "Ruptura 6M+", "Clientes Inativos"),
            selected   = "Potencial",
            status     = "primary",
            direction  = "vertical",
            individual = TRUE,
            width      = "100%"
          ),
          tags$style(HTML("
            #mc_aba_visualizacao .btn-group-container-sw {
              display: flex;
              flex-direction: column;
              gap: 6px;
            }
            #mc_aba_visualizacao .btn-group-container-sw .btn-group,
            #mc_aba_visualizacao .btn-group-container-sw .btn-group .btn {
              width: 100%;
            }
          ")),
          hr(),
          # Nas abas Ruptura 6M+/Clientes Inativos os filtros de produto nao
          # se aplicam (ver conditionalPanel abaixo) - no lugar deles, cards
          # simples com Titulos/Comodatos em aberto e Ultima Compra por ano
          conditionalPanel(
            condition = "input.mc_aba_visualizacao == 'Ruptura 6M+'",
            uiOutput("mc_cards_ruptura_6m"),
            downloadButton(
              "bt_download_mc_ruptura_6m", "Baixar Excel",
              icon = icon("file-excel"),
              class = "btn-success btn-block",
              style = "margin-top: 8px; width: 100%;"
            )
          ),
          conditionalPanel(
            condition = "input.mc_aba_visualizacao == 'Clientes Inativos'",
            uiOutput("mc_cards_clientes_inativos"),
            downloadButton(
              "bt_download_mc_clientes_inativos", "Baixar Excel",
              icon = icon("file-excel"),
              class = "btn-success btn-block",
              style = "margin-top: 8px; width: 100%;"
            )
          ),
          # Filtros de produto/vendedor/classificacao so fazem sentido nas abas
          # Potencial e Saiba Mais (Ruptura 6M+ e Clientes Inativos usam listas
          # de clientes que nao sao filtradas por eles)
          conditionalPanel(
            condition = "input.mc_aba_visualizacao == 'Potencial' || input.mc_aba_visualizacao == 'Saiba Mais'",
            # Filtros de produto/vendedor: vem de TB_MAPA_POT, entao so afetam
            # o que vem de venda (cards de volume/faturamento e as colunas
            # HL/UMB/R$ por cidade) - cobertura e clientes nao mudam.
            # Picker vazio = "Todos" (sem filtro naquele campo).
            pickerInput("mc_canal_filtro", "Canal", choices = NULL,
                        multiple = TRUE, options = opcoes_filtro),
            # Classificacao Cliente (PORTE): ao contrario dos filtros acima, vem
            # de TB_CLI_ATIVOS/TB_CLI_INATIVOS/TB_COB_CID (nao existe em
            # TB_MAPA_POT), entao afeta cobertura/clientes e NAO afeta venda
            if (filtros_especial_mc)
              pickerInput("mc_classif_cliente_filtro", "Classificação Cliente", choices = NULL,
                          multiple = TRUE, options = opcoes_filtro),
            if (filtros_especial_mc)
              pickerInput("mc_categoria_filtro", "Categoria Prod", choices = NULL,
                          multiple = TRUE, options = opcoes_filtro),
            pickerInput("mc_embalagem_filtro", "Tipo Embalagem", choices = NULL,
                        multiple = TRUE, options = opcoes_filtro),
            pickerInput("mc_marca_filtro", "Marca", choices = NULL,
                        multiple = TRUE, options = opcoes_filtro),
            if (filtros_especial_mc)
              pickerInput("mc_vendedor_filtro", "Vendedor", choices = NULL,
                          multiple = TRUE, options = opcoes_filtro)
          ),
          # 9 campos (mes + 7 pickers + menu de abas) nao cabem no espaco
          # padrao do Bootstrap dentro de uma coluna estreita - encolhe label,
          # espacamento entre campos e altura do botao fechado de cada picker
          tags$style(HTML("
            #box_mc_filtro .form-group {
              margin-bottom: 6px;
            }
            #box_mc_filtro label.control-label {
              margin-bottom: 3px;
              font-size: 13.5px;
            }
            #box_mc_filtro .bootstrap-select .btn {
              padding: 6px 12px;
              min-height: 36px;
              font-size: 14px;
              line-height: 1.3;
            }
            #box_mc_filtro hr {
              margin: 6px 0;
            }
          "))
        )
      )
    )
  )
}
