from shiny import ui

from .cores import DESTAQUE


def _texto(valor) -> str:

    if valor in (None, "-"):
        return "-"
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    return str(int(numero)) if numero.is_integer() else str(numero).replace(".", ",")


def resumo_dias(aba: str, dias, dias_atual) -> dict:

    return {
        "aba": aba,
        "cards": [
            ui.value_box(
                "Dias Úteis",
                _texto(dias),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#fff"),
                class_="valuebox-atualizacao valuebox-dias",
                fill=False,
            ),
            ui.value_box(
                "Atual",
                _texto(dias_atual),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#fff"),
                class_="valuebox-atualizacao valuebox-dias",
                fill=False,
            ),
        ],
    }
