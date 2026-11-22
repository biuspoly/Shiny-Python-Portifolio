from typing import Callable

from loguru import logger
from shiny import reactive, ui

from .visibilidade import pagina_visivel


def usar_crossfilter(
    input,
    session,
    filtros: list[tuple[str, str]],
    base_filtrada,
    valor_navset: str | None = None,
    formatadores: dict[str, Callable[[object], str]] | None = None,
) -> None:

    ultimas = {}

    @reactive.effect
    async def _crossfilter():
        if valor_navset is not None and not pagina_visivel(session, valor_navset):
            return
        base = await base_filtrada()
        for id_filtro, coluna in filtros:
            if input[id_filtro]():
                continue
            try:
                opcoes = sorted(v for v in base[coluna].unique() if v is not None)
            except Exception as exc:
                logger.warning(f'Crossfilter: coluna "{coluna}" (filtro "{id_filtro}") nao encontrada na base -- {exc}')
                continue
            if ultimas.get(id_filtro) == opcoes:
                continue
            ultimas[id_filtro] = opcoes
            formatador = (formatadores or {}).get(id_filtro)
            choices = {v: formatador(v) for v in opcoes} if formatador else opcoes
            ui.update_selectize(id_filtro, choices=choices, session=session)
