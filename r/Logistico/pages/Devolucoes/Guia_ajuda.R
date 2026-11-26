funcao_guia_dev <- function(aba_dev) {
  if (aba_dev == "Detalhes") {
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
      el = "box_det_dev_filtro",
      title = "Filtros",
      description = "Você pode filtrar os dados da página a partir daqui."
    )$
      step(
      el = "bt_limpadet_dev",
      title = "Filtros",
      description = "Caso queira limpar os filtros, pressionar esse botão.",
      position = "left"
    )$
      step(
      el = "card_dev_consol_detal",
      title = "Dados consolidados",
      description = "Nesse card, são informados resumos à respeito das devoluções.",
      position = "top"
    )$
      step(
      el = "#card_dev_consol_detal .btn.btn-tool.btn-sm",
      title = "Minimizar card",
      description = "Algumas partes dos paineis podem ser minimizadas para melhor aproveitamento da página.",
      position = "left",
      is_id = FALSE
    )$
      step(
      el = ".reactable .rt-expander:first-child",
      title = "Expandir linhas",
      description = "Nessa tabela, as linhas podem ser expandidas para mostrar as informações por revendas.",
      position = "right",
      is_id = FALSE
    )$
      step(
      el = "switch_consolidado_detal_dev",
      title = "Dados detalhados",
      description = "Mostra os dados detalhados de cada pedido.",
    )$
      step(
      el = "card_dev_diaria",
      title = "Devolução diária",
      description = "Gráfico para devolução de pedidos diários."
    )$
      step(
      el = "ult_atualizacao_ui",
      title = "Última atualização",
      description = "Data da última atualização do painel.",
      position = "top"
    )$
      step(
      el = "box_taxa_retorno_det",
      title = "Taxa de retorno total",
      description = "Card vermelho indica que a taxa de retorno está acima do limite.",
      position = "left"
    )$
      step(
      el = "controlbar-toggle",
      title = "Ferramentas",
      description = "Para acessar outras ferramentas disponíveis, como download dos dados da página atual.",
      position = "left"
    )
  } else if (aba_dev == "Detalhes det") {
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
      el = "box_det_dev_filtro",
      title = "Filtros",
      description = "Você pode filtrar os dados da página a partir daqui."
    )$
      step(
      el = "bt_limpadet_dev",
      title = "Filtros",
      description = "Caso queira limpar os filtros, pressionar esse botão.",
      position = "left"
    )$
      step(
      el = "card_dev_consol_detal",
      title = "Dados detalhados",
      description = "Nesse card, são informados detalhes à respeito das devoluções.",
      position = "top"
    )$
      step(
      el = "#card_dev_consol_detal .btn.btn-tool.btn-sm",
      title = "Minimizar card",
      description = "Algumas partes dos paineis podem ser minimizadas para melhor aproveitamento da página.",
      position = "left",
      is_id = FALSE
    )$
      step(
      el = "switch_consolidado_detal_dev",
      title = "Dados consolidados",
      description = "Mostra os dados consolidados de cada revenda por data.",
    )$
      step(
      el = ".bt_extra_dev",
      title = "Mostrar produtos",
      description = HTML("<p>Clicando no código do pedido, é possível visualizar os produtos.</p>,
                           <img src='acomp_log_www/img/ped_detal_dev.svg' alt='Detalhamento pedido'>"),
      position = "right",
      is_id = FALSE
    )$
      step(
      el = "ult_atualizacao_ui",
      title = "Última atualização",
      description = "Data da última atualização do painel.",
      position = "top"
    )$
      step(
      el = "box_taxa_retorno_det",
      title = "Taxa de retorno total",
      description = "Card vermelho indica que a taxa de retorno está acima do limite.",
      position = "left"
    )$
      step(
      el = "controlbar-toggle",
      title = "Ferramentas",
      description = "Para acessar outras ferramentas disponíveis, como download dos dados da página atual.",
      position = "left"
    )
  }

  return(guia)
}
