from __future__ import annotations

from faicons import icon_svg
from shiny import ui


def titulo_secao(rotulo: str, *, icone: str | None = None, extras: list | None = None) -> ui.Tag:
    return ui.div(
        icon_svg(icone, a11y="deco", margin_left="0", margin_right="0") if icone else None,
        ui.span(rotulo),
        *(extras or []),
        class_="ppf-secao-titulo",
    )


def com_placeholder(elemento, texto: str):
    def _passar(no):
        if getattr(no, "name", None) == "input":
            no.attrs["placeholder"] = texto
        for filho in getattr(no, "children", ()) or ():
            _passar(filho)

    _passar(elemento)
    return elemento
