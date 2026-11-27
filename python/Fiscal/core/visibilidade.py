from shiny import Session


def pagina_visivel(session: Session, valor_navset: str) -> bool:
    root_input = session.root_scope().input

    if "conteudo_tabs" not in root_input:
        return True
    return root_input.conteudo_tabs() == valor_navset
