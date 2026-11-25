automacoes = function(){

  # DADOS ------------------------------------------------------------------

  # Etapas do processo (faixa antes dos cards)
  etapas = data.frame(
    titulo    = c("Gatilho", "Coleta", "Processamento", "Entrega"),
    descricao = c("Agenda ou evento.", "Banco, planilha ou API.", "R e Python.", "E-mail, PDF e assinatura."),
    icone     = c("clock", "database", "gears", "paper-plane"),
    cor       = c("primary", "purple", "teal", "orange")
  )

  github = "https://github.com/biuspoly/"

  # Um bloco por projeto; valores de cada versão separados por ";"
  projetos = rbind(

    # Contrato de comodato (CEV) --------------------------------------------
    data.frame(
      id        = "comodato_cev",
      titulo    = "Contrato de comodato (CEV)",
      descricao = "Gera o contrato de comodato em PDF e envia para assinatura digital, com telas de reenvio.",
      detalhes  = "A automação em R lê o comodato, monta o contrato em R Markdown, extrai dados dos documentos do cliente, consulta o CNPJ e envia para assinatura na Clicksign. Para reenviar um contrato há duas telas de desktop: uma em R (tcltk) e outra em Python (tkinter), feitas com ajuda do Claude. Funciona junto com a tela de Comodatos do Acompanhamento Logístico.",
      logo      = "r.svg;python.svg",
      cor       = "primary",
      print     = "prints/repo_comodato_cev.png",
      link      = paste0(github, "comodato-cev;", github, "comodato-cev/blob/main/reenvio_cev.R;", github, "comodato-cev/tree/main/app"),
      rotulo    = "Automação (R);Tela tcltk (R);Tela tkinter (Python)",
      modo      = "repo"
    ),

    # Verificador de painéis Power BI ---------------------------------------
    data.frame(
      id        = "verificador_powerbi",
      titulo    = "Verificador de painéis Power BI",
      descricao = "Confere a última atualização de cada painel Power BI e dispara uma nova quando precisa.",
      detalhes  = "Junta o que eram três scripts (token, verificação e atualização) num módulo com funções. Usa a API REST do Power BI com service principal e tem modo demonstração com respostas fictícias.",
      logo      = "python.svg",
      cor       = "primary",
      print     = "prints/repo_verificador_paineis_powerbi.png",
      link      = paste0(github, "verificador-paineis-powerbi"),
      rotulo    = "",
      modo      = "repo"
    ),

    # Consulta de veículos (Senatran) ---------------------------------------
    data.frame(
      id        = "senatran",
      titulo    = "Consulta de veículos (Senatran)",
      descricao = "Robôs que consultam débitos, multas e restrições de veículos e o preço FIPE.",
      detalhes  = "Conjunto de robôs em Python (BUMBLEBEE, IRONHIDE, MEGATRON, OPTIMUS PRIME) que consultam os sistemas do Senatran/Detran com certificado digital e atualizam a FIPE da frota. Repositório só com o código: não roda sem os certificados.",
      logo      = "python.svg",
      cor       = "primary",
      print     = "prints/repo_automacao_senatran.png",
      link      = paste0(github, "automacao-senatran"),
      rotulo    = "",
      modo      = "repo"
    )
  )

  # UI ----------------------------------------------------------------------

  fluidPage(
    h2("Automações"),
    faixa_etapas(etapas, "Estrutura de uma automação"),
    fluidRow(card_projeto(projetos, "comodato_cev")),
    fluidRow(card_projeto(projetos, "verificador_powerbi")),
    fluidRow(card_projeto(projetos, "senatran"))
  )

}
