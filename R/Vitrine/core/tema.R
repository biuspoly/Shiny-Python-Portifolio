# Tema do portfólio (pacote fresh): AdminLTE clássico, "skin-blue"
# (o visual do shinydashboard): barra superior azul, menu lateral escuro e
# fundo cinza bem claro. Para mudar a cara do app, troque as cores aqui.
#
# Atenção: a faixa em degradê dos cards e a cor do título (www/estilo.css)
# usam as mesmas cores escritas à mão. Se trocar alguma delas aqui, troque
# também lá.

tema = create_theme(

  # Cores de status: botões, cards, badges e o item selecionado do menu
  bs4dash_status(
    primary   = "#2a6496",   # azul escuro (barra superior, botões, item ativo)
    secondary = "#6c757d",
    info      = "#00c0ef",
    success   = "#00a65a",
    warning   = "#f39c12",
    danger    = "#dd4b39",
    light     = "#f9fafc",
    dark      = "#222d32"
  ),

  # Fundo da área de conteúdo: cinza bem claro
  bs4dash_layout(
    main_bg = "#ecf0f5"
  ),

  # Barra superior azul, com texto branco
  bs4dash_vars(
    navbar_dark_color        = "#ffffff",
    navbar_dark_hover_color  = "#f4f4f4",
    navbar_dark_active_color = "#ffffff"
  ),

  # Menu lateral em azul-marinho escuro, item ativo em azul
  bs4dash_sidebar_dark(
    bg                  = "#1a2734",
    color               = "#b8c7ce",
    hover_color         = "#ffffff",
    submenu_bg          = "#213245",
    submenu_color       = "#9fb3c4",
    submenu_hover_color = "#ffffff"
  )
)
