from shiny import ui


def rotulo(texto: str, obrigatorio: bool = True) -> ui.TagList:
    if obrigatorio:
        return ui.TagList(texto, " ", ui.span("*", class_="acessos-obrigatorio"))
    return ui.TagList(texto, " ", ui.span("(opcional)", class_="acessos-opcional"))
