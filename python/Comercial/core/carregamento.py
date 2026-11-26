from shiny import ui


def com_carregamento(conteudo) -> ui.Tag:

    return ui.div(
        ui.div(
            ui.div(
                ui.div(class_="spinner-border", role="status"),
                ui.span("Carregando...", class_="pagina-carregando-texto"),
                class_="pagina-carregando-conteudo",
            ),
            class_="pagina-carregando-inicial",
        ),
        conteudo,
        class_="pagina-modulo",
    )
