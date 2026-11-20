"""Esqueleto comum das telas: cabeçalho com a marca, menu lateral recolhível e
a área de conteúdo trocada por `navset_hidden`.

O menu é descrito uma vez (lista de `Item`/`Grupo`) e serve para montar os
botões e para ligar cada botão ao seu painel no servidor.
"""

from dataclasses import dataclass, field
from pathlib import Path

from faicons import icon_svg
from shiny import reactive, ui

from core import cores

PASTA_APP = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Item:
    painel: str
    rotulo: str
    icone: str

    @property
    def id_botao(self) -> str:
        return f"bt_{self.painel}"


@dataclass(frozen=True)
class Grupo:
    rotulo: str
    icone: str
    itens: list[Item] = field(default_factory=list)


def _itens(menu: list) -> list[Item]:
    return [i for m in menu for i in (m.itens if isinstance(m, Grupo) else [m])]


def _botao(item: Item, selecionado: str) -> ui.Tag:
    return ui.input_action_button(
        item.id_botao,
        item.rotulo,
        icon=icon_svg(item.icone),
        class_="selecionado" if item.painel == selecionado else None,
    )


def _menu(menu: list, selecionado: str) -> list[ui.Tag]:
    botoes = []
    for m in menu:
        if isinstance(m, Grupo):
            aberto = any(i.painel == selecionado for i in m.itens)
            botoes.append(
                ui.accordion(
                    ui.accordion_panel(m.rotulo, *[_botao(i, selecionado) for i in m.itens], icon=icon_svg(m.icone)),
                    open=aberto,
                )
            )
        else:
            botoes.append(_botao(m, selecionado))
    return botoes


def marca(nome_app: str) -> ui.Tag:
    return ui.div(
        ui.tags.img(src="img/logo.svg", height="40px", alt="Atlântida Distribuidora"),
        ui.span(nome_app, class_="cabecalho-app-nome"),
        class_="cabecalho-app-marca",
    )


def pagina_app(nome_app: str, menu: list, paineis: dict[str, ui.Tag], direita: ui.Tag | None = None) -> ui.Tag:
    selecionado = _itens(menu)[0].painel
    return ui.page_sidebar(
        ui.sidebar(
            *_menu(menu, selecionado),
            gap="10px",
            padding="50px 0 0 0",
            width="200px",
            open={"desktop": "open", "mobile": "closed"},
        ),
        ui.navset_hidden(
            *[ui.nav_panel(None, conteudo, value=valor) for valor, conteudo in paineis.items()],
            id="conteudo_tabs",
            selected=selecionado,
        ),
        ui.tags.style(f"""
            :root {{
                --cor-sidebar: {cores.SIDEBAR_BG};
                --cor-destaque: {cores.DESTAQUE};
                --cor-texto-sidebar: {cores.TEXTO_SIDEBAR};
                --bs-primary: {cores.SIDEBAR_BG};
            }}
        """),
        ui.tags.link(rel="stylesheet", href="css/style.css"),
        ui.tags.script(src="js/echarts.min.js"),
        ui.tags.script(src="js/sidebar.js"),
        title=ui.div(marca(nome_app), ui.div(direita, class_="cabecalho-app-direita"), class_="cabecalho-app"),
        # Flatly já compilado (gerador/tema.py): o Shinylive não tem o libsass
        # que o ui.Theme("flatly") usaria para compilar na hora.
        theme=PASTA_APP / "www" / "css" / "flatly.min.css",
        window_title=f"{nome_app} | Atlântida",
    )


def ligar_menu(input, menu: list) -> None:
    """Um efeito por botão: o clique mostra o painel dele."""
    for item in _itens(menu):

        def _ligar(item: Item = item):
            @reactive.effect
            @reactive.event(input[item.id_botao])
            def _():
                ui.update_navset("conteudo_tabs", selected=item.painel)

        _ligar()


def mini_valuebox(titulo: str, valor: str, classe: str = "") -> ui.Tag:
    return ui.value_box(titulo, valor, class_=f"valuebox-cabecalho {classe}")


def cartao(titulo: str | None, *conteudo, ferramentas: ui.Tag | None = None, classe: str = "") -> ui.Tag:
    cabecalho = ui.card_header(ui.span(titulo), ferramentas, class_="cartao-cabecalho") if titulo else None
    return ui.card(cabecalho, *conteudo, class_=f"cartao {classe}")


def filtros(*campos, limpar_id: str | None = None) -> ui.Tag:
    botao = (
        ui.input_action_button(limpar_id, None, icon=icon_svg("eraser"), class_="btn-limpar", title="Limpar filtros")
        if limpar_id
        else None
    )
    return ui.card(
        ui.div(*[ui.div(c, class_="filtro") for c in campos], botao, class_="filtros-linha"),
        class_="cartao cartao-filtros",
    )


def kpi(titulo: str, valor: str, detalhe=None, cor: str | None = None) -> ui.Tag:
    """Card de indicador; `cor` troca a faixa da esquerda (ex.: situação)."""
    return ui.div(
        ui.div(titulo, class_="kpi-titulo"),
        ui.div(valor, class_="kpi-valor"),
        ui.div(detalhe or "", class_="kpi-detalhe"),
        class_="kpi",
        style=f"border-left-color:{cor}" if cor else None,
    )


def linha_kpis(*cards) -> ui.Tag:
    return ui.div(*cards, class_="linha-kpis")
