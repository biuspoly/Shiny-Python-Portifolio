analise_dados = function(item){

  # DADOS ------------------------------------------------------------------

  # Etapas do processo (faixa antes dos cards)
  etapas = data.frame(
    titulo    = c("Fontes", "Preparação", "Painel", "Decisão"),
    descricao = c("ERP e bancos de dados.", "Parquet e regras de negócio.", "Shiny R e Python.", "Gestores e equipes."),
    icone     = c("database", "gears", "chart-column", "users"),
    cor       = c("primary", "purple", "teal", "orange")
  )

  site_portfolio = "https://biuspoly.github.io/Shiny-Python-Portifolio/"

  projetos = data.frame(
    id = c(
      "py_comercial", "py_logistico", "py_financeiro", "py_fiscal", "py_monitoramento", "py_acessos",
      "r_comercial", "r_logistico", "r_acessos"
    ),
    titulo = c(
      "Acompanhamento Comercial", "Acompanhamento Logístico", "Acompanhamento Financeiro",
      "Acompanhamento Fiscal", "Monitoramento", "Acessos",
      "Acompanhamento Comercial", "Acompanhamento Logístico", "Acessos"
    ),
    descricao = c(
      "Diário de vendas, curva ABC de clientes e mapa comercial.",
      "Frota, comodatos, planilha de entregas e devoluções.",
      "Diário financeiro, pagamentos, fluxo, empréstimos, juros e extratos.",
      "Apuração de ICMS e PIS/COFINS e demonstrativo de faturamento em PDF.",
      "Usuários conectados, erros, desempenho e rotinas, a partir da telemetria.",
      "Acesso por painel, visão geral de uso e histórico de acessos.",
      "Diário de venda e mapa comercial (versão original em R).",
      "Frota, planilha de entregas, devoluções e comodato (versão original em R).",
      "Acesso por painel e histórico de acessos (versão original em R)."
    ),
    detalhes = c(
      "Meta, tendência, cobertura e histórico por categoria e produto; curva ABC de clientes; potencial e cobertura por município sobre a malha e a população do IBGE.",
      "Frota (débitos, multas, restrições, combustível e mapa), comodatos (solicitação, travas do cliente, pedido ao ERP, documentos, recolha e distrato), planilha de entregas e devoluções.",
      "Saldos dos bancos, composição financeira do dia, contas a pagar com auditoria, posição com a fábrica, empréstimos entre revendas, juros e extratos bancários.",
      "Apuração de ICMS com livro fiscal item a item, PIS/COFINS e demonstrativo de faturamento gerado em PDF.",
      "Painel lido dos logs de telemetria do próprio sistema: quem está conectado, erros, tempo de resposta e execução das rotinas.",
      "Controle de acesso aos painéis: quem acessou, quando e com que frequência.",
      "Sistema original em R Shiny (bs4Dash, reactable, DuckDB). Telas originais; o MySQL virou DuckDB em memória sobre Parquet fictício.",
      "Sistema original em R Shiny. O ERP virou um DuckDB por revenda e o contrato em R Markdown/LaTeX virou PDF desenhado com o pdf() do R.",
      "Sistema original em R Shiny, rodando no navegador pelo Shinylive (webR)."
    ),
    logo = c(
      "python.svg", "python.svg", "python.svg", "python.svg", "python.svg", "python.svg",
      "r.svg", "r.svg", "r.svg"
    ),
    cor = c(
      "primary", "primary", "primary", "primary", "primary", "primary",
      "info", "info", "info"
    ),
    print = c(
      "prints/shiny_py_comercial.webp", "prints/shiny_py_logistico.webp", "prints/shiny_py_financeiro.webp",
      "prints/shiny_py_fiscal.webp", "prints/shiny_py_monitoramento.webp", "prints/shiny_py_acessos.webp",
      "prints/shiny_r_comercial.webp", "prints/shiny_r_logistico.webp", "prints/shiny_r_acessos.webp"
    ),
    link = c(
      paste0(site_portfolio, "comercial/"), paste0(site_portfolio, "logistico/"), paste0(site_portfolio, "financeiro/"),
      paste0(site_portfolio, "fiscal/"), paste0(site_portfolio, "monitoramento/"), paste0(site_portfolio, "acessos/"),
      paste0(site_portfolio, "r/comercial/"), paste0(site_portfolio, "r/logistico/"), paste0(site_portfolio, "r/acessos/")
    ),
    rotulo = c(
      "", "", "", "", "", "",
      "", "", ""
    ),
    modo = c(
      "app", "app", "app", "app", "app", "app",
      "app", "app", "app"
    )
  )

  # Painéis em Power BI (publicados na web; abrem no modal)
  paineis_powerbi = data.frame(
    id = c(
      "pbi_secoge", "pbi_dengue", "pbi_performance", "pbi_vendas",
      "pbi_frotas", "pbi_custos_frota", "pbi_devolucoes", "pbi_acoes"
    ),
    titulo = c(
      "Vacinação COVID-19 (SECOGE)", "Dengue e Chikungunya no Recife", "Painel de performance", "Dashboard de vendas",
      "Frotas", "Custos de frota", "Devoluções", "Mercado de ações"
    ),
    descricao = c(
      "Doses aplicadas, reforços e cobertura vacinal contra a COVID-19.",
      "Notificações de dengue e chikungunya na cidade do Recife entre 2020 e 2021.",
      "Tempo das fases do pedido, faturamento, ticket médio e pedidos ao longo do tempo.",
      "Lucro, faturamento e quantidade de vendas por ano, produto, fabricante e canal.",
      "Veículos, restrições, débitos e custos da frota.",
      "Custo, combustível, distância e consumo por veículo e motorista.",
      "Vendas, devoluções e taxa de retorno por dia, motorista e produto.",
      "Volume e preço de ações ao longo do tempo, com narrativa inteligente."
    ),
    detalhes = c(
      "Dados públicos. O painel não está atualizado porque o Power BI não permite atualizar esse tipo de publicação pela API.",
      "Dados públicos. O painel não está atualizado porque o Power BI não permite atualizar esse tipo de publicação pela API.",
      "Dados fictícios.",
      "Dados fictícios.",
      "Dados fictícios. Primeira versão da aba de Frota do Acompanhamento Logístico, antes do Shiny.",
      "Dados fictícios. Primeira versão do acompanhamento de custos da frota (antigo TicketLog).",
      "Dados fictícios. Primeira versão da aba de Devoluções do Acompanhamento Logístico, antes do Shiny.",
      "Dados fictícios. O primeiro painel que fiz em Power BI."
    ),
    logo = c(
      "powerbi.svg", "powerbi.svg", "powerbi.svg", "powerbi.svg",
      "powerbi.svg", "powerbi.svg", "powerbi.svg", "powerbi.svg"
    ),
    cor = c(
      "warning", "warning", "warning", "warning",
      "warning", "warning", "warning", "warning"
    ),
    print = c(
      "prints/pbi_secoge.png", "prints/pbi_dengue.png", "prints/pbi_performance.png", "prints/pbi_vendas.png",
      "prints/pbi_frotas.png", "prints/pbi_custos_frota.png", "prints/pbi_devolucoes.png", "prints/pbi_acoes.png"
    ),
    link = c(
      "https://app.powerbi.com/view?r=eyJrIjoiZTc3ZTc0MjItZDVjMy00MTg5LTgyMDQtZGE4NDM1Yjk5YWNhIiwidCI6ImUyZjc3ZDAwLTAxNjMtNGNmNi05MmIwLTQ4NGJhZmY5ZGY3ZCJ9",
      "https://app.powerbi.com/view?r=eyJrIjoiY2QyMTBkMjgtZmIxZS00ZWJjLWI1NzgtNmJkOTE4YjMxNDY5IiwidCI6ImUyZjc3ZDAwLTAxNjMtNGNmNi05MmIwLTQ4NGJhZmY5ZGY3ZCJ9",
      "https://app.powerbi.com/view?r=eyJrIjoiZDJkYzJiMGQtNDQ1ZS00ZmIxLWEzYjMtMDliMjZjYTdkMDM2IiwidCI6ImUyZjc3ZDAwLTAxNjMtNGNmNi05MmIwLTQ4NGJhZmY5ZGY3ZCJ9",
      "https://app.powerbi.com/view?r=eyJrIjoiMzg4NGIyNDMtODQ1Ny00YmY3LTkwZTUtNmU3YmY0ODZjNTE3IiwidCI6ImUyZjc3ZDAwLTAxNjMtNGNmNi05MmIwLTQ4NGJhZmY5ZGY3ZCJ9",
      "https://app.powerbi.com/view?r=eyJrIjoiMDg4YzVmMjctY2Q0YS00NDBlLTg3YzgtOTFjY2UzMGEyMDk4IiwidCI6ImUyZjc3ZDAwLTAxNjMtNGNmNi05MmIwLTQ4NGJhZmY5ZGY3ZCJ9",
      "https://app.powerbi.com/view?r=eyJrIjoiZjAxNzM5MjEtODY1MS00ZWU3LWFmODctZThmNWMxYzc5YTA2IiwidCI6ImUyZjc3ZDAwLTAxNjMtNGNmNi05MmIwLTQ4NGJhZmY5ZGY3ZCJ9",
      "https://app.powerbi.com/view?r=eyJrIjoiODEwYjBmMGYtYzQ1OC00ZTA3LTg0YzMtMTNkNDYzNzJkZjQzIiwidCI6ImUyZjc3ZDAwLTAxNjMtNGNmNi05MmIwLTQ4NGJhZmY5ZGY3ZCJ9",
      "https://app.powerbi.com/view?r=eyJrIjoiMDYwODRmZDctYmU4NS00M2Y4LThiZGUtZjhhOThjNGVmNWFhIiwidCI6ImUyZjc3ZDAwLTAxNjMtNGNmNi05MmIwLTQ4NGJhZmY5ZGY3ZCJ9"
    ),
    rotulo = c(
      "", "", "", "",
      "", "", "", ""
    ),
    modo = c(
      "app", "app", "app", "app",
      "app", "app", "app", "app"
    )
  )

  # UI ----------------------------------------------------------------------

  if (item == "python") {

    fluidPage(
      h2("Análise de Dados com Shiny for Python"),
      faixa_etapas(etapas, "Etapas de um painel"),
      fluidRow(card_projeto(projetos, "py_comercial")),
      fluidRow(card_projeto(projetos, "py_logistico")),
      fluidRow(card_projeto(projetos, "py_financeiro")),
      fluidRow(card_projeto(projetos, "py_fiscal")),
      fluidRow(card_projeto(projetos, "py_monitoramento")),
      fluidRow(card_projeto(projetos, "py_acessos"))
    )

  } else if (item == "r") {

    fluidPage(
      h2("Análise de Dados com Shiny R"),
      faixa_etapas(etapas, "Etapas de um painel"),
      fluidRow(card_projeto(projetos, "r_comercial")),
      fluidRow(card_projeto(projetos, "r_logistico")),
      fluidRow(card_projeto(projetos, "r_acessos"))
    )

  } else if (item == "powerbi") {

    fluidPage(
      h2("Análise de Dados com Power BI"),
      faixa_etapas(etapas, "Etapas de um painel"),
      fluidRow(card_projeto(paineis_powerbi, "pbi_secoge")),
      fluidRow(card_projeto(paineis_powerbi, "pbi_dengue")),
      fluidRow(card_projeto(paineis_powerbi, "pbi_performance")),
      fluidRow(card_projeto(paineis_powerbi, "pbi_vendas")),
      fluidRow(card_projeto(paineis_powerbi, "pbi_frotas")),
      fluidRow(card_projeto(paineis_powerbi, "pbi_custos_frota")),
      fluidRow(card_projeto(paineis_powerbi, "pbi_devolucoes")),
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
