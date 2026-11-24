automacoes = function(item){

  # DADOS ------------------------------------------------------------------

  # Etapas do processo (faixa antes dos cards)
  etapas = data.frame(
    titulo    = c("Gatilho", "Coleta", "Processamento", "Entrega"),
    descricao = c("Agenda ou evento.", "Banco, planilha ou API.", "R e Python.", "E-mail, PDF e assinatura."),
    icone     = c("clock", "database", "gears", "paper-plane"),
    cor       = c("primary", "purple", "teal", "orange")
  )

  github = "https://github.com/biuspoly/"

  projetos = data.frame(
    id = c(
      "r_comodato_cev",
      "py_verificador_powerbi", "py_senatran",
      "appsheet_comodato"
    ),
    titulo = c(
      "Automação do contrato de comodato (CEV)",
      "Verificador de painéis Power BI", "Automação de consulta de veículos (Senatran)",
      "Comodato com AppSheet"
    ),
    descricao = c(
      "Gera o contrato de comodato em PDF e envia por e-mail para assinatura digital.",
      "Confere a última atualização de cada painel Power BI e dispara uma nova quando precisa.",
      "Robôs que consultam débitos, multas e restrições de veículos e o preço FIPE.",
      "O primeiro processo de comodato: app AppSheet sobre planilha Google, com automação em R."
    ),
    detalhes = c(
      "Lê o comodato, monta o contrato em R Markdown, extrai dados dos documentos do cliente, consulta o CNPJ e envia para assinatura na Clicksign. Funciona junto com a tela de Comodatos do Acompanhamento Logístico.",
      "Junta o que eram três scripts (token, verificação e atualização) num módulo com funções. Usa a API REST do Power BI com service principal e tem modo demonstração com respostas fictícias.",
      "Conjunto de robôs em Python (BUMBLEBEE, IRONHIDE, MEGATRON, OPTIMUS PRIME) que consultam os sistemas do Senatran/Detran com certificado digital e atualizam a FIPE da frota. Repositório só com o código: não roda sem os certificados.",
      "O app AppSheet roda sobre uma planilha Google; a automação em R lê os comodatos do banco e atualiza essa planilha em ciclos, mantendo o app em dia com o que está assinado e pendente. Foi a primeira versão do processo, antes da tela de Comodatos no Acompanhamento Logístico."
    ),
    logo = c(
      "r.svg",
      "python.svg", "python.svg",
      "appsheet.svg;r.svg"
    ),
    cor = c(
      "info",
      "primary", "primary",
      "success"
    ),
    print = c(
      "prints/repo_comodato_cev.png",
      "prints/repo_verificador_paineis_powerbi.png", "prints/repo_automacao_senatran.png",
      "prints/repo_comodato_appsheet.png"
    ),
    link = c(
      paste0(github, "comodato-cev"),
      paste0(github, "verificador-paineis-powerbi"), paste0(github, "automacao-senatran"),
      paste0(github, "comodato-appsheet")
    ),
    rotulo = c(
      "",
      "", "",
      ""
    ),
    modo = c(
      "repo",
      "repo", "repo",
      "repo"
    )
  )

  # UI ----------------------------------------------------------------------

  if (item == "r") {

    fluidPage(
      h2("Automações em R"),
      faixa_etapas(etapas, "Estrutura de uma automação"),
      fluidRow(card_projeto(projetos, "r_comodato_cev"))
    )

  } else if (item == "python") {

    fluidPage(
      h2("Automações em Python"),
      faixa_etapas(etapas, "Estrutura de uma automação"),
      fluidRow(card_projeto(projetos, "py_verificador_powerbi")),
      fluidRow(card_projeto(projetos, "py_senatran"))
    )

  } else if (item == "appsheet") {

    fluidPage(
      h2("Automações com AppSheet"),
      faixa_etapas(etapas, "Estrutura de uma automação"),
      fluidRow(card_projeto(projetos, "appsheet_comodato"))
    )

  }

}
