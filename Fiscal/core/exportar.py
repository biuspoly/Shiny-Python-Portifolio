from __future__ import annotations

import io
import json
import os
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import polars as pl
from faicons import icon_svg
from loguru import logger
from shiny import reactive, ui
from shiny.ui._html_deps_external import jqui_deps

from core import acervo
from core.aviso import modal_aviso

ID_COLUNAS = "exportar_colunas"
ID_TODAS = "exportar_todas"
PREFIXO_ABRIR = "exportar_abrir_"

ARQUIVO_DAS_ESCOLHAS = "exportar_colunas.json"
_trava = threading.Lock()
_escolhas_lidas: dict = {"marca_do_arquivo": None, "escolhas_por_planilha": {}}


def _arquivo_das_escolhas() -> Path:
    return acervo.raiz() / ARQUIVO_DAS_ESCOLHAS


def _escolhas() -> dict:
    arquivo = _arquivo_das_escolhas()
    try:
        situacao_do_arquivo = arquivo.stat()
        marca_do_arquivo = (str(arquivo), situacao_do_arquivo.st_mtime_ns, situacao_do_arquivo.st_size)
    except OSError:
        return {}
    if marca_do_arquivo != _escolhas_lidas["marca_do_arquivo"]:
        try:
            escolhas_por_planilha = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning(f"Exportar: {arquivo} ilegivel -- {exc}")
            escolhas_por_planilha = {}
        if not isinstance(escolhas_por_planilha, dict):
            escolhas_por_planilha = {}
        _escolhas_lidas.update(marca_do_arquivo=marca_do_arquivo, escolhas_por_planilha=escolhas_por_planilha)
    return _escolhas_lidas["escolhas_por_planilha"]


def escolha_salva(planilha: str) -> list[str]:
    guardada = _escolhas().get(planilha)
    if isinstance(guardada, dict) and isinstance(guardada.get("colunas"), list):
        return [str(coluna) for coluna in guardada["colunas"]]
    return []


def salvar_escolha(planilha: str, colunas: list[str], todas: list[str]) -> bool:
    escolhidas = [str(coluna) for coluna in colunas]
    escolha_nova = None if not escolhidas or escolhidas == list(todas) else escolhidas
    with _trava:
        escolhas_por_planilha = {nome: guardada for nome, guardada in _escolhas().items() if isinstance(guardada, dict)}
        if (escolhas_por_planilha.get(planilha) or {}).get("colunas") == escolha_nova:
            return False
        if escolha_nova is None:
            escolhas_por_planilha.pop(planilha, None)
        else:
            escolhas_por_planilha[planilha] = {
                "colunas": escolha_nova,
                "quando": datetime.now().isoformat(timespec="seconds"),
            }
        arquivo = _arquivo_das_escolhas()
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo_gravando = arquivo.with_name(f".{ARQUIVO_DAS_ESCOLHAS}.gravando")
        arquivo_gravando.write_text(
            json.dumps(escolhas_por_planilha, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
        )
        os.replace(arquivo_gravando, arquivo)
    return True


def dependencia():
    jquery_ui = jqui_deps()
    jquery_ui.stylesheet = []
    return jquery_ui


def botao(id_download: str, dica: str, icone: str = "file-excel"):
    return ui.TagList(
        dependencia(),
        ui.input_action_button(
            PREFIXO_ABRIR + id_download, None, icon=icon_svg(icone, a11y="deco"), class_="ppf-btn-discreto", title=dica
        ),
    )


def link(id_download: str, texto: str, icone: str):
    return ui.TagList(
        dependencia(), ui.input_action_link(PREFIXO_ABRIR + id_download, texto, icon=icon_svg(icone, a11y="deco"))
    )


def excel(tabela: pl.DataFrame, aba: str, colunas: list[str] | tuple | None = None) -> bytes:
    escolhidas = [c for c in (colunas or []) if c in tabela.columns]
    saida = io.BytesIO()
    (tabela.select(escolhidas) if escolhidas else tabela).write_excel(
        saida, worksheet=aba[:31] or "Planilha", autofit=True
    )
    return saida.getvalue()


def campo_das_colunas(ident: str, rotulo: str, todas: list[str], escolhidas: list[str]) -> ui.Tag:
    ordem = escolhidas + [c for c in todas if c not in escolhidas]
    return ui.input_selectize(
        ident,
        rotulo,
        choices=ordem,
        selected=escolhidas,
        multiple=True,
        width="100%",
        options={"plugins": ["drag_drop", "remove_button"], "placeholder": "Escolha ao menos uma coluna"},
    )


def janela(nome: str, id_download: str, todas: list[str], escolhidas: list[str]):
    return ui.modal(
        ui.p(
            "Escolha as colunas e a ordem delas: arraste uma etiqueta para mudar de lugar, o × tira a coluna e a lista "
            "do campo põe de volta. A planilha sai como ficar aqui, e a escolha fica salva para todos.",
            class_="fis-op-explica",
        ),
        campo_das_colunas(ID_COLUNAS, "Colunas da planilha", todas, escolhidas),
        title=ui.span(
            ui.span(icon_svg("file-excel", a11y="deco"), class_="fis-op-icone"),
            f"Exportar: {nome}",
            class_="fis-op-titulo",
        ),
        footer=ui.TagList(
            ui.input_action_button(
                ID_TODAS,
                "Voltar ao padrão",
                icon=icon_svg("rotate-left", a11y="deco"),
                class_="btn-outline-secondary me-auto",
                title="Todas as colunas, na ordem de sempre, para todos",
            ),
            ui.modal_button("Fechar", class_="btn-outline-secondary"),
            ui.download_button(id_download, "Baixar", icon=icon_svg("download", a11y="deco"), class_="btn-primary"),
        ),
        easy_close=True,
        size="l",
        class_="fis-exportar",
    )


class Exportar:
    def __init__(self, input, planilhas: dict[str, tuple[str, Callable[[], list[str]]]], popover: str | None = None):
        self._input = input
        self._planilhas = planilhas
        self._popover = popover
        self._aberta = reactive.value(None)
        self._todas: dict[str, list[str]] = {}
        for id_download in planilhas:
            self._registrar_abrir(id_download)
        self._registrar_todas()
        self._registrar_salvar()

    def chave(self, id_download: str) -> str:
        return f"{self._planilhas[id_download][0]}|{id_download}"

    def salvas(self, id_download: str) -> list[str]:
        return escolha_salva(self.chave(id_download))

    def _registrar_abrir(self, id_download: str):
        @reactive.effect
        @reactive.event(self._input[PREFIXO_ABRIR + id_download])
        def _abrir():
            self._abrir(id_download)

    def _registrar_todas(self):
        @reactive.effect
        @reactive.event(self._input[ID_TODAS])
        def _todas_as_colunas():
            try:
                aberta = self._aberta()
                todas = self._todas.get(aberta or "", [])
                ui.update_selectize(ID_COLUNAS, choices=todas, selected=todas)
                if aberta:
                    salvar_escolha(self.chave(aberta), todas, todas)
            except Exception as exc:
                logger.warning(f"Exportar: voltar ao padrao -- {exc}")

    def _registrar_salvar(self):
        @reactive.effect
        @reactive.event(self._input[ID_COLUNAS], ignore_init=True)
        def _salvar_a_escolha():
            try:
                with reactive.isolate():
                    aberta = self._aberta()
                escolhidas = list(self._input[ID_COLUNAS]() or [])
                if aberta and escolhidas and aberta in self._todas:
                    salvar_escolha(self.chave(aberta), escolhidas, self._todas[aberta])
            except Exception as exc:
                logger.warning(f"Exportar: salvar a escolha -- {exc}")

    def _abrir(self, id_download: str):
        nome, colunas_da_planilha = self._planilhas[id_download]
        if self._popover:
            ui.update_popover(self._popover, show=False)
        try:
            todas = list(colunas_da_planilha())
        except Exception as exc:
            logger.exception(f"Exportar: colunas de {id_download} -- {exc}")
            ui.modal_show(modal_aviso(f"Não foi possível montar a planilha: {exc}", "Erro", "error"))
            return
        if not todas:
            ui.modal_show(modal_aviso("Não há linhas na lista para exportar.", "Exportar", "message"))
            return
        salvas = [c for c in self.salvas(id_download) if c in todas]
        self._todas[id_download] = todas
        self._aberta.set(id_download)
        ui.modal_show(janela(nome, id_download, todas, salvas or todas))

    def colunas(self, id_download: str) -> list[str]:
        with reactive.isolate():
            aberta = self._aberta()
        escolhidas = (
            list(self._input[ID_COLUNAS]() or []) if aberta == id_download and ID_COLUNAS in self._input else []
        )
        return escolhidas or self.salvas(id_download)
