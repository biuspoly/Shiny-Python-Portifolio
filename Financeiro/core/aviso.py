from shiny import ui

_ICONE_AVISO = {
    "warning": ("!", "#f8bb86"),
    "error": ("\u2715", "#f27474"),
    "success": ("\u2713", "#a5dc86"),
    "message": ("i", "#6baee0"),
}


def corpo_aviso(mensagem: str, titulo: str = "Aviso", tipo: str = "warning") -> ui.Tag:
    simbolo, cor = _ICONE_AVISO.get(tipo, _ICONE_AVISO["warning"])
    return ui.div(
        ui.div(simbolo, class_="aviso-icone", style=f"border-color:{cor}; color:{cor};"),
        ui.div(titulo, class_="aviso-titulo"),
        ui.div(mensagem, class_="aviso-texto"),
        class_="aviso-corpo",
    )


def _e_negativa(mensagem, titulo) -> bool:
    texto = str(mensagem or "")
    return "permiss" in str(titulo or "").lower() or "não tem permissão" in texto or texto.startswith("Sem permissão")


def modal_aviso(mensagem: str, titulo: str = "Aviso", tipo: str = "warning") -> ui.Tag:
    if _e_negativa(mensagem, titulo):
        from core import trava_caixa

        caixa = trava_caixa.da_sessao()
        if caixa:
            return trava_caixa.modal(caixa)
    return ui.modal(
        corpo_aviso(mensagem, titulo=titulo, tipo=tipo),
        title=None,
        footer=None,
        easy_close=True,
        size="s",
    )
