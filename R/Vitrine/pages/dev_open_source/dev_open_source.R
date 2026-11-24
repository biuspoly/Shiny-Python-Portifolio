dev_open_source = function(item){

  # DADOS ------------------------------------------------------------------

  # Etapas do processo (faixa antes dos cards)
  etapas = data.frame(
    titulo    = c("Especificação", "Código", "Testes", "Publicação"),
    descricao = c("Documentação oficial.", "R, Python, C++ e Godot.", "Casos e exemplos.", "Repositório no GitHub."),
    icone     = c("book", "code", "vial-circle-check", "github"),
    cor       = c("primary", "purple", "teal", "orange")
  )

  github = "https://github.com/biuspoly/"

  projetos = data.frame(
    id = c(
      "r_rnfe", "r_veiculosbr", "r_reenvio_cev",
      "py_veiculosbr", "py_yume", "py_reenvio_cev",
      "godot_rivals_avenue",
      "cpp_pekka_kana"
    ),
    titulo = c(
      "RNFe", "veiculosbr", "Reenvio de CEV",
      "veiculosbr", "Yume em PT-BR no Switch", "Reenvio de CEV",
      "Rivals Avenue",
      "Pekka Kana 2 para Nintendo Switch"
    ),
    descricao = c(
      "Documentos fiscais eletrônicos brasileiros em R: XML, assinatura, SEFAZ e PDFs.",
      "Placa (antiga e Mercosul), RENAVAM e preço FIPE de veículos brasileiros, em R.",
      "Interface de desktop em R para reenviar o contrato de comodato para assinatura.",
      "Placa (antiga e Mercosul), RENAVAM e preço FIPE de veículos brasileiros, em Python.",
      "Tradução para português e guia para jogar Yume no Nintendo Switch.",
      "Interface de desktop em Python para gerar e reenviar o contrato de comodato.",
      "Jogo em desenvolvimento na Godot Engine.",
      "Port nativo (homebrew) de Pekka Kana 2 para Nintendo Switch."
    ),
    detalhes = c(
      "NF-e, NFC-e, CT-e, GTV-e, MDF-e e NFS-e: montar o XML pelo schema, assinar, comunicar com a SEFAZ, ler os documentos em tabelas e gerar os PDFs (DANFE, DACTE, DAMDFE, DANFSe).",
      "Valida e converte placas antigas e Mercosul, valida RENAVAM e consulta o preço FIPE, inclusive a partir da placa. O mesmo pacote tem a versão em Python.",
      "Feita com tcltk: escolhe o comodato, gera de novo o PDF do contrato e reenvia para assinatura. Trabalha junto com a tela de Comodatos do Acompanhamento Logístico.",
      "Versão em Python do pacote: validação de placa e RENAVAM e consulta FIPE.",
      "Tradução PT-BR do jogo Yume e o passo a passo para rodá-lo no Nintendo Switch.",
      "Feita com tkinter: gera e reenvia o contrato de comodato para assinatura, com a mesma lógica da versão em R.",
      "Projeto pessoal de jogo na Godot Engine (GDScript). Repositório ainda privado.",
      "Port do jogo Pekka Kana 2 em C++ para rodar nativamente no Nintendo Switch (homebrew)."
    ),
    logo = c(
      "r.svg", "r.svg;python.svg", "r.svg;python.svg",
      "python.svg;r.svg", "python.svg", "python.svg;r.svg",
      "godot.svg",
      "cpp.svg"
    ),
    cor = c(
      "info", "info", "info",
      "primary", "primary", "primary",
      "info",
      "primary"
    ),
    print = c(
      "prints/repo_rnfe.png", "prints/repo_veiculosbr.png", "prints/repo_comodato_cev.png",
      "prints/repo_veiculosbr.png", "prints/repo_yume_switch_ptbr.png", "prints/repo_comodato_cev.png",
      "prints/godot_rivals_avenue.png",
      "prints/cpp_pekka_kana.png"
    ),
    link = c(
      paste0(github, "RNFe"), paste0(github, "veiculosbr"), paste0(github, "comodato-cev;", github, "comodato-cev/tree/main/app"),
      paste0(github, "veiculosbr"), paste0(github, "yume-switch-ptbr"), paste0(github, "comodato-cev;", github, "comodato-cev/tree/main/app"),
      "",
      paste0(github, "pekka-kana-2-switch")
    ),
    rotulo = c(
      "", "", "Versão R;Versão Python",
      "", "", "Versão R;Versão Python",
      "",
      ""
    ),
    modo = c(
      "repo", "repo", "repo",
      "repo", "repo", "repo",
      "em_breve",
      "repo"
    )
  )

  # UI ----------------------------------------------------------------------

  if (item == "r") {

    fluidPage(
      h2("Dev & Open Source em R"),
      faixa_etapas(etapas, "Etapas de um projeto aberto"),
      fluidRow(card_projeto(projetos, "r_rnfe")),
      fluidRow(card_projeto(projetos, "r_veiculosbr")),
      fluidRow(card_projeto(projetos, "r_reenvio_cev"))
    )

  } else if (item == "python") {

    fluidPage(
      h2("Dev & Open Source em Python"),
      faixa_etapas(etapas, "Etapas de um projeto aberto"),
      fluidRow(card_projeto(projetos, "py_veiculosbr")),
      fluidRow(card_projeto(projetos, "py_yume")),
      fluidRow(card_projeto(projetos, "py_reenvio_cev"))
    )

  } else if (item == "godot") {

    fluidPage(
      h2("Dev & Open Source com Godot"),
      faixa_etapas(etapas, "Etapas de um projeto aberto"),
      fluidRow(card_projeto(projetos, "godot_rivals_avenue"))
    )

  } else if (item == "cpp") {

    fluidPage(
      h2("Dev & Open Source em C++"),
      faixa_etapas(etapas, "Etapas de um projeto aberto"),
      fluidRow(card_projeto(projetos, "cpp_pekka_kana"))
    )

  }

}
