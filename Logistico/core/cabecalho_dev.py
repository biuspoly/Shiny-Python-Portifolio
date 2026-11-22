from shiny import ui

from .cores import DESTAQUE, FROTA_TEXTO_ESCURO


def valuebox_cabecalho(rotulo: str, valor: str, cor_fundo: str | None = None) -> ui.Tag:
    cor_letra = FROTA_TEXTO_ESCURO if cor_fundo else "#fff"
    return ui.value_box(
        rotulo,
        valor,
        theme=ui.value_box_theme(bg=cor_fundo or DESTAQUE, fg=cor_letra),
        class_="valuebox-atualizacao",
        fill=False,
    )
