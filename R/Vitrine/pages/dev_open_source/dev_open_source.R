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

  # Pacotes: um bloco por projeto; valores de cada versão separados por ";"
  pacotes = rbind(

    # RNFe ------------------------------------------------------------------
    data.frame(
      id        = "rnfe",
      titulo    = "RNFe",
      descricao = "Documentos fiscais eletrônicos brasileiros em R: XML, assinatura, SEFAZ e PDFs.",
      detalhes  = "NF-e, NFC-e, CT-e, GTV-e, MDF-e e NFS-e: montar o XML pelo schema, assinar, comunicar com a SEFAZ, ler os documentos em tabelas e gerar os PDFs (DANFE, DACTE, DAMDFE, DANFSe). Feito com ajuda do Claude.",
      logo      = "r.svg",
      cor       = "info",
      print     = "prints/repo_rnfe.png",
      link      = paste0(github, "RNFe"),
      rotulo    = "",
      modo      = "repo"
    ),

    # veiculosbr ------------------------------------------------------------
    data.frame(
      id        = "veiculosbr",
      titulo    = "veiculosbr",
      descricao = "Placa (antiga e Mercosul), RENAVAM e preço FIPE de veículos brasileiros, em R e Python.",
      detalhes  = "Valida e converte placas antigas e Mercosul, valida RENAVAM e consulta o preço FIPE, inclusive a partir da placa. O mesmo pacote existe em R e em Python. Feito com ajuda do Claude.",
      logo      = "r.svg;python.svg",
      cor       = "info",
      print     = "prints/repo_veiculosbr.png",
      link      = paste0(github, "veiculosbr/tree/main/r;", github, "veiculosbr/tree/main/python"),
      rotulo    = "Pacote R;Pacote Python",
      modo      = "repo"
    )
  )

  # Jogos: um bloco por projeto
  jogos = rbind(

    # Pekka Kana 2 para Nintendo Switch -------------------------------------
    data.frame(
      id        = "pekka_kana",
      titulo    = "Pekka Kana 2 para Nintendo Switch",
      descricao = "Port nativo (homebrew) de Pekka Kana 2 para Nintendo Switch.",
      detalhes  = "Port do jogo Pekka Kana 2 em C++ para rodar nativamente no Nintendo Switch (homebrew). Feito com ajuda do Claude.",
      logo      = "cpp.svg",
      cor       = "primary",
      print     = "prints/cpp_pekka_kana.png",
      link      = paste0(github, "pekka-kana-2-switch"),
      rotulo    = "",
      modo      = "repo"
    ),

    # Rivals Avenue ---------------------------------------------------------
    data.frame(
      id        = "rivals_avenue",
      titulo    = "Rivals Avenue",
      descricao = "Jogo em desenvolvimento na Godot Engine.",
      detalhes  = "Projeto pessoal de jogo na Godot Engine (GDScript). Repositório ainda privado. Feito com ajuda do Claude.",
      logo      = "godot.svg",
      cor       = "primary",
      print     = "prints/godot_rivals_avenue.png",
      link      = "#",
      rotulo    = "",
      modo      = "em_breve"
    ),

    # Yume em PT-BR no Switch -----------------------------------------------
    data.frame(
      id        = "yume",
      titulo    = "Yume em PT-BR no Switch",
      descricao = "Tradução para português e guia para jogar Yume no Nintendo Switch.",
      detalhes  = "Tradução PT-BR do jogo Yume e o passo a passo para rodá-lo no Nintendo Switch. Feito com ajuda do Claude.",
      logo      = "python.svg",
      cor       = "primary",
      print     = "prints/repo_yume_switch_ptbr.png",
      link      = paste0(github, "yume-switch-ptbr"),
      rotulo    = "",
      modo      = "repo"
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
