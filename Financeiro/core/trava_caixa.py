"""No original, trava a gravação de quem está com o caixa da revenda fechado. Sem trava no portfólio."""

TITULO = "Caixa da revenda travado"


def barrar(usuario: str | None) -> bool:
    return False


def da_sessao() -> str | None:
    return None


def barrado(usuario: str | None) -> str | None:
    return None


def modal(aviso: str):
    from shiny import ui

    from core.aviso import corpo_aviso

    return ui.modal(corpo_aviso(aviso, titulo=TITULO, tipo="error"), title=None, footer=None, easy_close=True, size="s")
