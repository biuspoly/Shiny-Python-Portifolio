from __future__ import annotations

import json
import threading
from datetime import date, datetime
from pathlib import Path

from shiny import ui

NOME_ARQUIVO_METADADOS = "_atualizacoes.json"

_trava = threading.Lock()


def registra_atualizacao(pasta: Path, nome: str, momento: datetime | None = None) -> None:
    caminho = pasta / NOME_ARQUIVO_METADADOS
    with _trava:
        dados = {}
        if caminho.exists():
            try:
                dados = json.loads(caminho.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                dados = {}
        dados[nome] = (momento or datetime.now()).isoformat(timespec="seconds")
        caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def obter_atualizacao(pasta: Path, *nomes: str, cnpj: str | None = None) -> datetime | None:
    caminho = pasta / NOME_ARQUIVO_METADADOS
    if not caminho.exists():
        return None
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    momentos = []
    for nome in nomes:
        momentos_da_tabela = []
        if nome in dados:
            momentos_da_tabela.append(datetime.fromisoformat(dados[nome]))
        if cnpj and f"{nome}_{cnpj}" in dados:
            momentos_da_tabela.append(datetime.fromisoformat(dados[f"{nome}_{cnpj}"]))
        if momentos_da_tabela:
            momentos.append(max(momentos_da_tabela))
    return min(momentos) if momentos else None


def cartao_atualizacao(momento: datetime | None, cor_fundo: str) -> ui.Tag:
    if momento is None:
        texto, desatualizado = "-", True
    else:
        texto = momento.strftime("%d/%m/%Y %H:%M")
        desatualizado = momento.date() != date.today()

    classes = "valuebox-atualizacao"
    if desatualizado:
        classes += " valuebox-desatualizado"

    return ui.value_box(
        "Atualizado em",
        texto,
        theme=ui.value_box_theme(bg=cor_fundo, fg="#fff"),
        class_=classes,
        fill=False,
    )
