analise_dados = function(item){

  # DADOS ------------------------------------------------------------------

  # Etapas do processo (faixa antes dos cards)
  etapas = data.frame(
    titulo    = c("Fontes", "Preparação", "Painel", "Decisão"),
    descricao = c("ERP e bancos de dados.", "Parquet e regras de negócio.", "Shiny, Power BI e Excel.", "Gestores e equipes."),
    icone     = c("database", "gears", "chart-column", "users"),
    cor       = c("primary", "purple", "teal", "orange")
  )

  site_portfolio = "https://biuspoly.github.io/Shiny-Python-Portifolio/"
  powerbi        = "https://app.powerbi.com/view?r="

  # Apps no Posit Connect Cloud (um servidor por linguagem, com todos os painéis dentro). Abrem em nova
  # aba: o Shinylive (webR) roda isolado (COEP) e não deixa outro app abrir num iframe dentro dele.
  # R: o painel vem pela URL (?painel=comercial). Python: cada painel tem a sua rota (comercial/).
  posit_r  = "https://01a2190a-f130-f119-72e4-d16f0322add0.share.connect.posit.cloud/"
  posit_py = "https://01a2190b-b942-a96c-d03c-a67adef5d830.share.connect.posit.cloud/"

  # Painéis de gestão: o sistema da distribuidora, com as versões de cada painel
  # (Power BI, Shiny R e Shiny Python). Um bloco por projeto; os valores de cada
  # versão (logo, link, rotulo, modo) ficam separados por ";".
  paineis_gestao = rbind(

    # Acompanhamento Logístico ----------------------------------------------
    data.frame(
      id        = "logistico",
      titulo    = "Acompanhamento Logístico",
      descricao = "Frota, comodatos, planilha de entregas e devoluções.",
      detalhes  = "Começou em Power BI (Frotas, Custos de frota e Devoluções, com dados fictícios), passou para Shiny R (bs4Dash, reactable, DuckDB) e hoje está em Shiny for Python. Frota: débitos, multas, restrições, combustível e mapa; comodatos: solicitação, travas do cliente, pedido ao ERP, documentos, recolha e distrato.",
      logo      = "powerbi.svg;r.svg;python.svg",
      cor       = "primary",
      print     = "prints/shiny_py_logistico.webp",
      link      = paste0(
        powerbi, "eyJrIjoiMDg4YzVmMjctY2Q0YS00NDBlLTg3YzgtOTFjY2UzMGEyMDk4IiwidCI6ImUyZjc3ZDAwLTAxNjMtNGNmNi05MmIwLTQ4NGJhZmY5ZGY3ZCJ9;",
        powerbi, "eyJrIjoiZjAxNzM5MjEtODY1MS00ZWU3LWFmODctZThmNWMxYzc5YTA2IiwidCI6ImUyZjc3ZDAwLTAxNjMtNGNmNi05MmIwLTQ4NGJhZmY5ZGY3ZCJ9;",
        powerbi, "eyJrIjoiODEwYjBmMGYtYzQ1OC00ZTA3LTg0YzMtMTNkNDYzNzJkZjQzIiwidCI6ImUyZjc3ZDAwLTAxNjMtNGNmNi05MmIwLTQ4NGJhZmY5ZGY3ZCJ9;",
        posit_r,  "?painel=logistico;",
        posit_py, "logistico/"
      ),
      rotulo    = "Frotas (Power BI);Custos (Power BI);Devoluções (Power BI);Shiny R;Shiny Python",
      modo      = "externo"
    ),

    # Acompanhamento Comercial ----------------------------------------------
    data.frame(
      id        = "comercial",
      titulo    = "Acompanhamento Comercial",
      descricao = "Diário de vendas, curva ABC de clientes e mapa comercial.",
      detalhes  = "Primeiro em Shiny R e hoje em Shiny for Python. Meta, tendência, cobertura e histórico por categoria e produto; curva ABC de clientes; potencial e cobertura por município sobre a malha e a população do IBGE.",
      logo      = "r.svg;python.svg",
      cor       = "primary",
      print     = "prints/shiny_py_comercial.webp",
      link      = paste0(posit_r, "?painel=comercial;", posit_py, "comercial/"),
      rotulo    = "Shiny R;Shiny Python",
      modo      = "externo"
    ),

    # Acompanhamento Financeiro ---------------------------------------------
    data.frame(
      id        = "financeiro",
      titulo    = "Acompanhamento Financeiro",
      descricao = "Diário financeiro, pagamentos, fluxo, empréstimos, juros e extratos.",
      detalhes  = "Saldos dos bancos, composição financeira do dia, contas a pagar com auditoria, posição com a fábrica, empréstimos entre revendas, juros e extratos bancários.",
      logo      = "python.svg",
      cor       = "primary",
      print     = "prints/shiny_py_financeiro.webp",
      link      = paste0(posit_py, "financeiro/"),
      rotulo    = "Shiny Python",
      modo      = "externo"
    ),

    # Acompanhamento Fiscal -------------------------------------------------
    data.frame(
      id        = "fiscal",
      titulo    = "Acompanhamento Fiscal",
      descricao = "Apuração de ICMS e PIS/COFINS e demonstrativo de faturamento em PDF.",
      detalhes  = "Apuração de ICMS com livro fiscal item a item, PIS/COFINS e demonstrativo de faturamento gerado em PDF.",
      logo      = "python.svg",
      cor       = "primary",
      print     = "prints/shiny_py_fiscal.webp",
      link      = paste0(posit_py, "fiscal/"),
      rotulo    = "Shiny Python",
      modo      = "externo"
    ),

    # Monitoramento ---------------------------------------------------------
    data.frame(
      id        = "monitoramento",
      titulo    = "Monitoramento",
      descricao = "Usuários conectados, erros, desempenho e rotinas, a partir da telemetria.",
      detalhes  = "Painel lido dos logs de telemetria do próprio sistema: quem está conectado, erros, tempo de resposta e execução das rotinas.",
      logo      = "python.svg",
      cor       = "primary",
      print     = "prints/shiny_py_monitoramento.webp",
      link      = paste0(posit_py, "monitoramento/"),
      rotulo    = "Shiny Python",
      modo      = "externo"
    ),

    # Acessos ---------------------------------------------------------------
    data.frame(
      id        = "acessos",
      titulo    = "Acessos",
      descricao = "Acesso por painel, visão geral de uso e histórico de acessos.",
      detalhes  = "Primeiro em Shiny R e hoje em Shiny for Python. Controle de acesso aos painéis: quem acessou, quando e com que frequência.",
      logo      = "r.svg;python.svg",
      cor       = "primary",
      print     = "prints/shiny_py_acessos.webp",
      link      = paste0(posit_r, "?painel=acessos;", posit_py, "acessos/"),
      rotulo    = "Shiny R;Shiny Python",
      modo      = "externo"
    ),

    # Primeiros painéis em Shiny --------------------------------------------
    data.frame(
      id        = "primeiros_shiny",
      titulo    = "Primeiros painéis em Shiny",
      descricao = "Painel de vendas e painel de demandas: os primeiros passos com Shiny, em flexdashboard.",
      detalhes  = "Feitos para aprender os recursos do Shiny em R. O de vendas usa flexdashboard em R Markdown com Shiny por dentro, sobre dados fictícios de uma empresa. O de demandas adapta um painel de Power BI: filtra as tarefas por responsável e status e permite baixar os dados. Hospedados no shinyapps.io (podem levar alguns segundos para acordar).",
      logo      = "r.svg",
      cor       = "primary",
      print     = "prints/shiny_r_primeiros_paineis.png",
      link      = "https://marlonufpe.shinyapps.io/VENDAS/;https://marlonufpe.shinyapps.io/demanda/",
      rotulo    = "Vendas;Demandas",
      modo      = "externo"
    )
  )

  # Painéis em Power BI (publicados na web; abrem em nova aba)
  paineis_powerbi = rbind(

    # Vacinação COVID-19 (SECOGE) -------------------------------------------
    data.frame(
      id        = "pbi_secoge",
      titulo    = "Vacinação COVID-19 (SECOGE)",
      descricao = "Doses aplicadas, reforços e cobertura vacinal contra a COVID-19.",
      detalhes  = "Dados públicos. O painel não está atualizado porque o Power BI não permite atualizar esse tipo de publicação pela API.",
      logo      = "powerbi.svg",
      cor       = "warning",
      print     = "prints/pbi_secoge.png",
      link      = paste0(powerbi, "eyJrIjoiZTc3ZTc0MjItZDVjMy00MTg5LTgyMDQtZGE4NDM1Yjk5YWNhIiwidCI6ImUyZjc3ZDAwLTAxNjMtNGNmNi05MmIwLTQ4NGJhZmY5ZGY3ZCJ9"),
      rotulo    = "",
      modo      = "externo"
    ),

    # Dengue e Chikungunya no Recife ----------------------------------------
    data.frame(
      id        = "pbi_dengue",
      titulo    = "Dengue e Chikungunya no Recife",
      descricao = "Notificações de dengue e chikungunya na cidade do Recife entre 2020 e 2021.",
      detalhes  = "Dados públicos. O painel não está atualizado porque o Power BI não permite atualizar esse tipo de publicação pela API.",
      logo      = "powerbi.svg",
      cor       = "warning",
      print     = "prints/pbi_dengue.png",
      link      = paste0(powerbi, "eyJrIjoiY2QyMTBkMjgtZmIxZS00ZWJjLWI1NzgtNmJkOTE4YjMxNDY5IiwidCI6ImUyZjc3ZDAwLTAxNjMtNGNmNi05MmIwLTQ4NGJhZmY5ZGY3ZCJ9"),
      rotulo    = "",
      modo      = "externo"
    ),

    # Painel de performance -------------------------------------------------
    data.frame(
      id        = "pbi_performance",
      titulo    = "Painel de performance",
      descricao = "Tempo das fases do pedido, faturamento, ticket médio e pedidos ao longo do tempo.",
      detalhes  = "Dados fictícios.",
      logo      = "powerbi.svg",
      cor       = "warning",
      print     = "prints/pbi_performance.png",
      link      = paste0(powerbi, "eyJrIjoiZDJkYzJiMGQtNDQ1ZS00ZmIxLWEzYjMtMDliMjZjYTdkMDM2IiwidCI6ImUyZjc3ZDAwLTAxNjMtNGNmNi05MmIwLTQ4NGJhZmY5ZGY3ZCJ9"),
      rotulo    = "",
      modo      = "externo"
    ),

    # Dashboard de vendas ---------------------------------------------------
    data.frame(
      id        = "pbi_vendas",
      titulo    = "Dashboard de vendas",
      descricao = "Lucro, faturamento e quantidade de vendas por ano, produto, fabricante e canal.",
      detalhes  = "Dados fictícios.",
      logo      = "powerbi.svg",
      cor       = "warning",
      print     = "prints/pbi_vendas.png",
      link      = paste0(powerbi, "eyJrIjoiMzg4NGIyNDMtODQ1Ny00YmY3LTkwZTUtNmU3YmY0ODZjNTE3IiwidCI6ImUyZjc3ZDAwLTAxNjMtNGNmNi05MmIwLTQ4NGJhZmY5ZGY3ZCJ9"),
      rotulo    = "",
      modo      = "externo"
    ),

    # Mercado de ações ------------------------------------------------------
    data.frame(
      id        = "pbi_acoes",
      titulo    = "Mercado de ações",
      descricao = "Volume e preço de ações ao longo do tempo, com narrativa inteligente.",
      detalhes  = "Dados fictícios. O primeiro painel que fiz em Power BI.",
      logo      = "powerbi.svg",
      cor       = "warning",
      print     = "prints/pbi_acoes.png",
      link      = paste0(powerbi, "eyJrIjoiMDYwODRmZDctYmU4NS00M2Y4LThiZGUtZjhhOThjNGVmNWFhIiwidCI6ImUyZjc3ZDAwLTAxNjMtNGNmNi05MmIwLTQ4NGJhZmY5ZGY3ZCJ9"),
      rotulo    = "",
      modo      = "externo"
    )
  )

  # UI ----------------------------------------------------------------------

  if (item == "gestao") {

    fluidPage(
      h2("Painéis de gestão"),
      faixa_etapas(etapas, "Etapas de um painel"),
      fluidRow(card_projeto(paineis_gestao, "logistico")),
      fluidRow(card_projeto(paineis_gestao, "comercial")),
      fluidRow(card_projeto(paineis_gestao, "financeiro")),
      fluidRow(card_projeto(paineis_gestao, "fiscal")),
      fluidRow(card_projeto(paineis_gestao, "monitoramento")),
      fluidRow(card_projeto(paineis_gestao, "acessos")),
      fluidRow(card_projeto(paineis_gestao, "primeiros_shiny"))
    )

  } else if (item == "powerbi") {

    fluidPage(
      h2("Painéis em Power BI"),
      faixa_etapas(etapas, "Etapas de um painel"),
      fluidRow(card_projeto(paineis_powerbi, "pbi_secoge")),
      fluidRow(card_projeto(paineis_powerbi, "pbi_dengue")),
      fluidRow(card_projeto(paineis_powerbi, "pbi_performance")),
      fluidRow(card_projeto(paineis_powerbi, "pbi_vendas")),
      fluidRow(card_projeto(paineis_powerbi, "pbi_acoes"))
    )

  } else if (item == "excel") {

    fluidPage(
      h2("Análise de Dados com Excel"),
      faixa_etapas(etapas, "Etapas de um painel"),
      p("Em breve.")
    )

  }

}
