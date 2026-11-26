from __future__ import annotations

import math

import pandas as pd
from faicons import icon_svg
from shiny import reactive, ui

TAMANHOS_PAGINA = [50, 100, 500]


class TabelaPaginada:
    def __init__(self, id_base: str, input, session, tamanho_padrao: int = 50):
        self.id_base = id_base
        self._input = input
        self._session = session
        self.pagina = reactive.value(1, name="pagina")
        self.tamanho = reactive.value(tamanho_padrao, name="tamanho")
        self._ultima_pagina_conhecida = 1
        self._registrar_eventos()

    def _registrar_eventos(self):
        id_primeira = f"{self.id_base}_pag_primeira"
        id_ant = f"{self.id_base}_pag_ant"
        id_prox = f"{self.id_base}_pag_prox"
        id_ultima = f"{self.id_base}_pag_ultima"
        id_tam = f"{self.id_base}_pag_tam"

        @reactive.effect
        @reactive.event(self._input[id_primeira])
        def _primeira():
            self.pagina.set(1)

        @reactive.effect
        @reactive.event(self._input[id_ant])
        def _volta():
            self.pagina.set(max(1, self.pagina() - 1))

        @reactive.effect
        @reactive.event(self._input[id_prox])
        def _avanca():
            self.pagina.set(self.pagina() + 1)

        @reactive.effect
        @reactive.event(self._input[id_ultima])
        def _ultima():
            self.pagina.set(self._ultima_pagina_conhecida)

        @reactive.effect
        @reactive.event(self._input[id_tam])
        def _muda_tamanho():
            escolhido = str(self._input[id_tam]() or "").strip()
            if not escolhido.isdigit():
                return
            self.tamanho.set(int(escolhido))
            self.pagina.set(1)

    def reiniciar(self):
        self.pagina.set(1)

    def janela(self, total: int) -> tuple[int, int]:
        tamanho = self.tamanho()
        total_paginas = max(1, math.ceil(total / tamanho))
        pagina_atual = min(max(1, self.pagina()), total_paginas)
        inicio = (pagina_atual - 1) * tamanho
        return inicio, inicio + tamanho

    def _janela(self, total: int) -> tuple[int, int]:
        return self.janela(total)

    def fatiar(self, base: pd.DataFrame) -> pd.DataFrame:
        inicio, fim = self._janela(len(base))
        return base.iloc[inicio:fim].reset_index(drop=True)

    def fatiar_com_estilos(self, base: pd.DataFrame, estilos: list[dict]) -> tuple[pd.DataFrame, list[dict]]:
        inicio, fim = self._janela(len(base))
        fatia = base.iloc[inicio:fim].reset_index(drop=True)

        estilos_fatia = []
        for regra in estilos:
            linhas_originais = regra.get("rows")
            if linhas_originais is None:
                estilos_fatia.append(regra)
                continue
            linhas_na_fatia = [r - inicio for r in linhas_originais if inicio <= r < fim]
            if linhas_na_fatia:
                estilos_fatia.append({**regra, "rows": linhas_na_fatia})
        return fatia, estilos_fatia

    def controles(self, total: int) -> ui.Tag:
        tamanho = self.tamanho()
        total_paginas = max(1, math.ceil(total / tamanho))
        pagina_atual = min(max(1, self.pagina()), total_paginas)
        self._ultima_pagina_conhecida = total_paginas

        return ui.div(
            ui.div(
                "Mostrar ",
                ui.input_select(
                    f"{self.id_base}_pag_tam",
                    None,
                    choices={str(t): str(t) for t in TAMANHOS_PAGINA},
                    selected=str(tamanho),
                ),
                class_="paginacao-tamanho",
            ),
            ui.div(
                ui.input_action_button(
                    f"{self.id_base}_pag_primeira",
                    None,
                    icon=icon_svg("angles-left", a11y="deco"),
                    class_="btn-paginacao",
                    disabled=pagina_atual <= 1,
                    title="Primeira página",
                ),
                ui.input_action_button(
                    f"{self.id_base}_pag_ant",
                    None,
                    icon=icon_svg("angle-left", a11y="deco"),
                    class_="btn-paginacao",
                    disabled=pagina_atual <= 1,
                    title="Página anterior",
                ),
                ui.span(
                    f"Página {pagina_atual} de {total_paginas} ({total} registros)" if total else "Sem linhas",
                    class_="paginacao-numero",
                ),
                ui.input_action_button(
                    f"{self.id_base}_pag_prox",
                    None,
                    icon=icon_svg("angle-right", a11y="deco"),
                    class_="btn-paginacao",
                    disabled=pagina_atual >= total_paginas,
                    title="Próxima página",
                ),
                ui.input_action_button(
                    f"{self.id_base}_pag_ultima",
                    None,
                    icon=icon_svg("angles-right", a11y="deco"),
                    class_="btn-paginacao",
                    disabled=pagina_atual >= total_paginas,
                    title="Última página",
                ),
                class_="paginacao-botoes",
            ),
            class_="paginacao-tabela",
        )
