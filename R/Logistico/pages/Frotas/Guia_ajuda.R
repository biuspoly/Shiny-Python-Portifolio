funcao_guia_frota <- function(aba_frota) {
  if (aba_frota == "Geral") {
    guia <- Cicerone$
      new(
      close_btn_text = "Sair",
      next_btn_text = "Próximo",
      prev_btn_text = "Anterior",
      done_btn_text = "Finalizar"
    )$
      step(
      el = "sidebarItemExpanded",
      title = "Menu",
      description = "Menu interativo para acessar aos paineis.",
      position = "right"
    )$
      step(
      el = "box_frota_filtro",
      title = "Filtros",
      description = "Você pode filtrar os dados da página a partir daqui."
    )$
      step(
      el = "bt_limpafrota",
      title = "Filtros",
      description = "Caso queira limpar os filtros, pressionar esse botão.",
      position = "left"
    )$
      step(
      el = "card_frota_consolidada",
      title = "Dados consolidados",
      description = "Nesse card, são informados resumos à respeito dos veículos.",
      position = "top"
    )$
      step(
      el = ".btn.btn-tool.btn-sm",
      title = "Minimizar card",
      description = "Algumas partes dos paineis podem ser minimizadas para melhor aproveitamento da página.",
      position = "left",
      is_id = FALSE
    )$
      step(
      el = "bt_check_frota",
      title = "Detalhamento",
      description = "Botões responsáveis para mudar detalhes dos veículos na tabela a seguir.",
      position = "bottom"
    )$
      step(
      el = 'button.btn.radiobtn.btn-primary:has(input[value="Geral"])',
      title = "Geral",
      description = "Para detalhes mais gerais dos veículos, como Ano de fabricação, Carroceria e Motivo de saída
        (Esse último, deve ser informado na aba de saída de veículos).",
      is_id = FALSE
    )$
      step(
      el = 'button.btn.radiobtn.btn-primary:has(input[value="Rest Adm"])',
      title = "Restrições Administrativas",
      description = "Para mostrar se os veículos possuem restrições, gravames e gravames pendentes (PE).",
      is_id = FALSE
    )$
      step(
      el = 'button.btn.radiobtn.btn-primary:has(input[value="Renajud"])',
      title = "Processos Renajud",
      description = HTML(
        "<p>Para visualizar se os veículos possuem processos judiciais ativos.</p>
        <p><b>Detalhamento de processos:</b> Para ir no detalhamento de processos, basta ativar a opção ao lado de 'Detalhamento'.</p>
        <img src='acomp_log_www/img/detal_ativo.svg' alt='Imagem de detalhamento'>"
      ),
      is_id = FALSE
    )$
      step(
      el = 'button.btn.radiobtn.btn-primary:has(input[value="Detran"])',
      title = "Débitos do Detran",
      description = HTML("
        <p>Para visualizar os débitos ativos, como IPVA, Licenciamento e Multas.</p>
        <p><b>Detalhamento de multas:</b> Para ir no detalhamento de multas, basta ativar a opção ao lado de 'Detalhamento'.</p>
        <img src='acomp_log_www/img/detal_ativo.svg' alt='Imagem de detalhamento'>
      "),
      is_id = FALSE
    )$
      step(
      el = 'button.btn.radiobtn.btn-primary:has(input[value="Custos"])',
      title = "Filtro Geral",
      description = "Mostra um resumo geral dos valores por empresa.",
      is_id = FALSE
    )$
      step(
      el = "card_frota_detalhada",
      title = "Dados detalhados",
      description = "Aqui serão mostrados os detalhes veiculares, de acordo com o botão anterior selecionado.",
      position = "top"
    )$
      step(
      el = "[data-card-widget='maximize']",
      title = "Maximizar card",
      description = "Algumas partes dos paineis também oferecem a opção de maximizar, para aumentar a visualização dos cards.",
      position = "left",
      is_id = FALSE
    )$
      step(
      el = "ult_atualizacao_ui",
      title = "Última atualização",
      description = "Data da última atualização do painel.",
      position = "top"
    )$
      step(
      el = "controlbar-toggle",
      title = "Ferramentas",
      description = "Para acessar outras ferramentas disponíveis, como download dos dados da página atual.",
      position = "left"
    )
  }
  # else if(aba_frota == "Entrada"){
  #   guia = Cicerone$
  #     new(
  #       close_btn_text = "Sair",
  #       next_btn_text = "Próximo",
  #       prev_btn_text = "Anterior",
  #       done_btn_text = "Finalizar"
  #     )$
  #     step(
  #       el = "sidebarItemExpanded",
  #       title = "Menu",
  #       description = "Menu interativo para acessar aos paineis.",
  #       position = "right"
  #     )$
  #     step(
  #       el = "box_frota_filtro_entrada",
  #       title = "Filtros",
  #       description = "Você pode filtrar os dados da página a partir daqui."
  #
  #     )$
  #     step(
  #       el = "bt_limpafrota_entrada",
  #       title = "Filtros",
  #       description = "Caso queira limpar os filtros, pressionar esse botão.",
  #       position = "left"
  #     )$
  #     step(
  #       el = "card_frota_consolidada_entrada",
  #       title = "Dados consolidados",
  #       description = "Nesse card, são informados resumos à respeito dos veículos.",
  #       position = "top"
  #     )$
  #     step(
  #       el = "bt_check_frota_entrada",
  #       title = "Detalhamento",
  #       description = "Botões responsáveis para mudar detalhes dos veículos na tabela a seguir.",
  #       position = "bottom"
  #     )$
  #     step(
  #       el = 'button.btn.radiobtn.btn-primary:has(input[value="Geral"])',
  #       title = "Geral",
  #       description = "Para detalhes mais gerais dos veículos, como Ano de fabricação e Carroceria.",
  #       is_id = FALSE
  #     )$
  #     step(
  #       el = 'button.btn.radiobtn.btn-primary:has(input[value="Rest Adm"])',
  #       title = "Restrições Administrativas",
  #       description = "Para mostrar se os veículos possuem restrições, gravames e gravames pendentes (PE).",
  #       is_id = FALSE
  #     )$
  #     step(
  #       el = 'button.btn.radiobtn.btn-primary:has(input[value="Renajud"])',
  #       title = "Processos Renajud",
  #       description = HTML(
  #         "<p>Para visualizar se os veículos possuem processos judiciais ativos.</p>
  #       <p><b>Detalhamento de processos:</b> Para ir no detalhamento de processos, basta ativar a opção ao lado de 'Detalhamento'.</p>
  #       <img src='acomp_log_www/img/detal_ativo.svg' alt='Imagem de detalhamento'>"
  #       ),
  #       is_id = FALSE
  #     )$
  #     step(
  #       el = 'button.btn.radiobtn.btn-primary:has(input[value="Detran"])',
  #       title = "Débitos do Detran",
  #       description = HTML("
  #       <p>Para visualizar os débitos ativos, como IPVA, Licenciamento e Multas.</p>
  #       <p><b>Detalhamento de multas:</b> Para ir no detalhamento de multas, basta ativar a opção ao lado de 'Detalhamento'.</p>
  #       <img src='acomp_log_www/img/detal_ativo.svg' alt='Imagem de detalhamento'>
  #     "),
  #       is_id = FALSE
  #     )$
  #     step(
  #       el = 'button.btn.radiobtn.btn-primary:has(input[value="Custos"])',
  #       title = "Filtro Geral",
  #       description = "Mostra um resumo geral dos valores por empresa.",
  #       is_id = FALSE
  #     )$
  #     step(
  #       el = "card_frota_detalhada_entrada",
  #       title = "Dados detalhados",
  #       description = "Aqui serão mostrados os detalhes veiculares, de acordo com o botão anterior selecionado.",
  #       position = "top"
  #     )$
  #     step(
  #       el = "[data-card-widget='maximize']",
  #       title = "Maximizar card",
  #       description = "Algumas partes dos paineis também oferecem a opção de maximizar, para aumentar a visualização dos cards.",
  #       position = "left",
  #       is_id = FALSE
  #     )$
  #     step(
  #       el = "ult_atualizacao_ui",
  #       title = "Última atualização",
  #       description = "Data da última atualização do painel.",
  #       position = "top"
  #     )$
  #     step(
  #       el = "controlbar-toggle",
  #       title = "Ferramentas",
  #       description = "Para acessar outras ferramentas disponíveis, como download dos dados da página atual.",
  #       position = "left"
  #     )
  # }
  # else{
  #   guia = Cicerone$
  #     new(
  #       close_btn_text = "Sair",
  #       next_btn_text = "Próximo",
  #       prev_btn_text = "Anterior",
  #       done_btn_text = "Finalizar"
  #     )$
  #     step(
  #       el = "sidebarItemExpanded",
  #       title = "Menu",
  #       description = "Menu interativo para acessar aos paineis.",
  #       position = "right"
  #     )$
  #     step(
  #       el = "box_frota_filtro",
  #       title = "Filtros",
  #       description = "Você pode filtrar os dados da página a partir daqui."
  #
  #     )$
  #     step(
  #       el = "bt_limpafrota",
  #       title = "Filtros",
  #       description = "Caso queira limpar os filtros, pressionar esse botão.",
  #       position = "left"
  #     )$
  #     step(
  #       el = "card_frota_consolidada",
  #       title = "Dados consolidados",
  #       description = "Nesse card, são informados resumos à respeito dos veículos.",
  #       position = "top"
  #     )$
  #     step(
  #       el = ".btn.btn-tool.btn-sm",
  #       title = "Minimizar card",
  #       description = "Algumas partes dos paineis podem ser minimizadas para melhor aproveitamento da página.",
  #       position = "left",
  #       is_id = FALSE
  #     )$
  #     step(
  #       el = "bt_check_frota",
  #       title = "Detalhamento",
  #       description = "Botões responsáveis para mudar detalhes dos veículos na tabela a seguir.",
  #       position = "bottom"
  #     )$
  #     step(
  #       el = 'button.btn.radiobtn.btn-primary:has(input[value="Geral"])',
  #       title = "Geral",
  #       description = "Para detalhes mais gerais dos veículos, como Ano de fabricação e Carroceria.",
  #       is_id = FALSE
  #     )$
  #     step(
  #       el = 'button.btn.radiobtn.btn-primary:has(input[value="Rest Adm"])',
  #       title = "Restrições Administrativas",
  #       description = "Para mostrar se os veículos possuem restrições, gravames e gravames pendentes (PE).",
  #       is_id = FALSE
  #     )$
  #     step(
  #       el = 'button.btn.radiobtn.btn-primary:has(input[value="Renajud"])',
  #       title = "Processos Renajud",
  #       description = HTML(
  #         "<p>Para visualizar se os veículos possuem processos judiciais ativos.</p>
  #       <p><b>Detalhamento de processos:</b> Para ir no detalhamento de processos, basta ativar a opção ao lado de 'Detalhamento'.</p>
  #       <img src='acomp_log_www/img/detal_ativo.svg' alt='Imagem de detalhamento'>"
  #       ),
  #       is_id = FALSE
  #     )$
  #     step(
  #       el = 'button.btn.radiobtn.btn-primary:has(input[value="Detran"])',
  #       title = "Débitos do Detran",
  #       description = HTML("
  #       <p>Para visualizar os débitos ativos, como IPVA, Licenciamento e Multas.</p>
  #       <p><b>Detalhamento de multas:</b> Para ir no detalhamento de multas, basta ativar a opção ao lado de 'Detalhamento'.</p>
  #       <img src='acomp_log_www/img/detal_ativo.svg' alt='Imagem de detalhamento'>
  #     "),
  #       is_id = FALSE
  #     )$
  #     step(
  #       el = 'button.btn.radiobtn.btn-primary:has(input[value="Custos"])',
  #       title = "Filtro Geral",
  #       description = "Mostra um resumo geral dos valores por empresa.",
  #       is_id = FALSE
  #     )$
  #     step(
  #       el = "card_frota_detalhada",
  #       title = "Dados detalhados",
  #       description = "Aqui serão mostrados os detalhes veiculares, de acordo com o botão anterior selecionado.",
  #       position = "top"
  #     )$
  #     step(
  #       el = "[data-card-widget='maximize']",
  #       title = "Maximizar card",
  #       description = "Algumas partes dos paineis também oferecem a opção de maximizar, para aumentar a visualização dos cards.",
  #       position = "left",
  #       is_id = FALSE
  #     )$
  #     step(
  #       el = "ult_atualizacao_ui",
  #       title = "Última atualização",
  #       description = "Data da última atualização do painel.",
  #       position = "top"
  #     )$
  #     step(
  #       el = "controlbar-toggle",
  #       title = "Ferramentas",
  #       description = "Para acessar outras ferramentas disponíveis, como download dos dados da página atual.",
  #       position = "left"
  #     )
  # }


  return(guia)
}
