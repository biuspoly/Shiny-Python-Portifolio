funcao_guia_comodato = function(aba_comodato){
  
  if(aba_comodato == 'Solicitacao'){
    guia = Cicerone$
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
        el = "box_comodatos_solic_filtro",
        title = "Filtros",
        description = "Você pode filtrar os dados da página a partir daqui."
        
      )$
      step(
        el = "bt_limpacomod_solic",
        title = "Filtros",
        description = "Caso queira limpar os filtros, pressionar esse botão.",
        position = "left"
      )$
      step(
        el = ".btn.btn-tool.btn-sm",
        title = "Minimizar card",
        description = "Algumas partes dos paineis podem ser minimizadas para melhor aproveitamento da página.",
        position = "left",
        is_id = FALSE
      )$
      step(
        el = "tabela_cli_solic_comodatos",
        title = "Clientes inadimplentes",
        description = "Através da tabela, será possível fazer solicitações de novos CEVs e verificar detalhes de cada cliente.",
        position = "top"
      )$
      step(
        el = ".rt-tbody .rt-tr-group:first-child .rt-td:nth-last-child(2) .button_group_solic_cev",
        title = "Solicitação",
        description = HTML("
                        <p>Através do botão \u2795 poderá ser feita a solicitação de comodato, enquanto \u26D4 permite visualizar o que impede do cliente fazer a mesma.</p>
                        <p>Depois de clicado, uma nova tela será mostrada com os dados do solicitante, bem como os produtos a serem selecionados e quantidade a ser informada.</p>
                        <p><b>OBS:</b> Aqui não existe limite no número de solicitações.</p>
                      "),
        position = "left",
        is_id = FALSE
      )$
      step(
        el = ".rt-tbody .rt-tr-group:first-child .rt-td:last-child .button_group_solic_cev",
        title = "Detalhes",
        description = "Mostra se o cliente possui CEVs pendentes.",
        position = "left",
        is_id = FALSE
      )$
      step(
        el = "tabela_comodatos_solcitados",
        title = "Solicitações de clientes",
        description = "A tabela mostrará as solicitações pedidas em tempo real, por cliente e data de emissão, à medida em que forem adicionadas.",
        position = "top"
      )$
      step(
        el = ".rt-tbody .rt-tr-group:first-child .rt-td:nth-last-child(2) .button_com_env",
        title = "Envio de comodato",
        description = "Para enviar os dados do CEV para o sistema ERP.",
        position = "left",
        is_id = FALSE
      )$
      step(
        el = "#tabela_comodatos_solcitados .rt-tbody .rt-tr-group:first-child .rt-td:last-child",
        title = "Retirada de produto",
        description = "Caso queira retirar algum produto da lista antes de enviar para o sistema ERP.",
        position = "left",
        is_id = FALSE
      )$
      step(
        el = "controlbar-toggle",
        title = "Ferramentas",
        description = "Para acessar outras ferramentas disponíveis, como atualizar os dados da página atual.",
        position = "left"
      )
  } else if(aba_comodato == 'Comodatos'){
    guia = Cicerone$
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
        el = "box_comodatos_filtro",
        title = "Filtros",
        description = "Você pode filtrar os dados da página a partir daqui."
        
      )$
      step(
        el = "bt_limpacomod",
        title = "Filtros",
        description = "Caso queira limpar os filtros, pressionar esse botão.",
        position = "left"
      )$
      step(
        el = "tabela_detal_comodatos",
        title = "Comodatos abertos",
        description = "Através da tabela, será possível verificar os comodatos abertos no sistema.",
        position = "top"
      )$
      step(
        el = ".button_com_cev",
        title = "Cev",
        description = "Ao clicar, será mostrado o contrato assinado.",
        position = "left",
        is_id = FALSE
      )$
      step(
        el = ".button_com_can",
        title = "Canhoto",
        description = "Ao clicar, será mostrado o canhoto.",
        position = "left",
        is_id = FALSE
      )$
      step(
        el = ".button_com_act",
        title = "Ação",
        description = HTML("
                        <p>A coluna consiste em mostrar 3 ações:</p>
                        <p>\u26D4: Poderá ser feita a adição do canhoto clicando no botão, pois o mesmo não existe ou foi recusado.</p>
                        <p>\u2699\uFE0F: Os documentos estão em análise.</p>
                        <p>\u2705: Comodato aprovado.</p>
                      "),
        position = "left",
        is_id = FALSE
      )$
      step(
        el = "controlbar-toggle",
        title = "Ferramentas",
        description = "Para acessar outras ferramentas disponíveis, como atualizar os dados da página atual.",
        position = "left"
      )
  }
  
  return(guia)
}
