from __future__ import annotations

from faicons import icon_svg
from shiny import ui

ICONE_EXTRATO = "file-invoice-dollar"
ICONE_FLUXO_FABRICA = "money-bill-transfer"
ICONE_EMPRESTIMOS = "hand-holding-dollar"


def titulo_secao(
    rotulo: str,
    *,
    icone: str | None = None,
    emoji: str | None = None,
    extras: list | None = None,
) -> ui.Tag:
    return ui.div(
        _icone(icone) if icone else None,
        ui.span(emoji, class_="ppf-secao-emoji") if emoji else None,
        ui.span(rotulo),
        *(extras or []),
        class_="ppf-secao-titulo",
    )


def _icone(icone: str) -> ui.Tag | None:
    if icone.endswith(".svg"):
        return ui.tags.img(src=icone, class_="ppf-secao-icone", alt="")
    try:
        return ui.span(icon_svg(icone, a11y="deco"), class_="ppf-secao-icone ppf-secao-fa")
    except Exception:
        return None


def com_placeholder(elemento, texto: str):
    def _passar(no):
        if getattr(no, "name", None) == "input":
            no.attrs["placeholder"] = texto
        for filho in getattr(no, "children", ()) or ():
            _passar(filho)

    _passar(elemento)
    return elemento
