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

  # Pacotes (valores de cada versão separados por ";")
  pacotes = data.frame(
    id = c(
      "rnfe", "veiculosbr"
    ),
    titulo = c(
      "RNFe", "veiculosbr"
    ),
    descricao = c(
      "Documentos fiscais eletrônicos brasileiros em R: XML, assinatura, SEFAZ e PDFs.",
      "Placa (antiga e Mercosul), RENAVAM e preço FIPE de veículos brasileiros, em R e Python."
    ),
    detalhes = c(
      "NF-e, NFC-e, CT-e, GTV-e, MDF-e e NFS-e: montar o XML pelo schema, assinar, comunicar com a SEFAZ, ler os documentos em tabelas e gerar os PDFs (DANFE, DACTE, DAMDFE, DANFSe). Feito com ajuda do Claude.",
      "Valida e converte placas antigas e Mercosul, valida RENAVAM e consulta o preço FIPE, inclusive a partir da placa. O mesmo pacote existe em R e em Python. Feito com ajuda do Claude."
    ),
    logo = c(
      "r.svg", "r.svg;python.svg"
    ),
    cor = c(
      "info", "info"
    ),
    print = c(
      "prints/repo_rnfe.png", "prints/repo_veiculosbr.png"
    ),
    link = c(
      paste0(github, "RNFe"),
      paste0(github, "veiculosbr/tree/main/r;", github, "veiculosbr/tree/main/python")
    ),
    rotulo = c(
      "", "Pacote R;Pacote Python"
    ),
    modo = c(
      "repo", "repo"
    )
  )

  # Jogos
  jogos = data.frame(
    id = c(
      "pekka_kana", "rivals_avenue", "yume"
    ),
    titulo = c(
      "Pekka Kana 2 para Nintendo Switch", "Rivals Avenue", "Yume em PT-BR no Switch"
    ),
    descricao = c(
      "Port nativo (homebrew) de Pekka Kana 2 para Nintendo Switch.",
      "Jogo em desenvolvimento na Godot Engine.",
      "Tradução para português e guia para jogar Yume no Nintendo Switch."
    ),
    detalhes = c(
      "Port do jogo Pekka Kana 2 em C++ para rodar nativamente no Nintendo Switch (homebrew). Feito com ajuda do Claude.",
      "Projeto pessoal de jogo na Godot Engine (GDScript). Repositório ainda privado. Feito com ajuda do Claude.",
      "Tradução PT-BR do jogo Yume e o passo a passo para rodá-lo no Nintendo Switch. Feito com ajuda do Claude."
    ),
    logo = c(
      "cpp.svg", "godot.svg", "python.svg"
    ),
    cor = c(
      "primary", "primary", "primary"
    ),
    print = c(
      "prints/cpp_pekka_kana.png", "prints/godot_rivals_avenue.png", "prints/repo_yume_switch_ptbr.png"
    ),
    link = c(
      paste0(github, "pekka-kana-2-switch"),
      "#",
      paste0(github, "yume-switch-ptbr")
    ),
    rotulo = c(
      "", "", ""
    ),
    modo = c(
      "repo", "em_breve", "repo"
    )
  )

  # UI ----------------------------------------------------------------------

  if (item == "pacotes") {

    fluidPage(
      h2("Pacotes"),
      faixa_etapas(etapas, "Etapas de um projeto aberto"),
      fluidRow(card_projeto(pacotes, "rnfe")),
      fluidRow(card_projeto(pacotes, "veiculosbr"))
    )

  } else if (item == "jogos") {

    fluidPage(
      h2("Jogos"),
      faixa_etapas(etapas, "Etapas de um projeto aberto"),
      fluidRow(card_projeto(jogos, "pekka_kana")),
      fluidRow(card_projeto(jogos, "rivals_avenue")),
      fluidRow(card_projeto(jogos, "yume"))
    )

  }

}
