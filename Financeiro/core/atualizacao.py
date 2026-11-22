from __future__ import annotations

import json
import re
import threading
from datetime import date, datetime
from pathlib import Path

from shiny import ui

from core.cores import FAROL_CRITICO

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


def carimbos(pasta: Path) -> dict[str, str]:
    try:
        dados = json.loads((pasta / NOME_ARQUIVO_METADADOS).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dados if isinstance(dados, dict) else {}


def carimbos_das_tabelas(pasta: Path, *nomes: str) -> dict[str, str]:
    padrao = re.compile(rf"(?:{'|'.join(map(re.escape, nomes))})(?:_\d{{8,14}})?")
    return {chave: momento for chave, momento in carimbos(pasta).items() if padrao.fullmatch(chave)}


def momentos_por_tabela(pasta: Path, *nomes: str, cnpj: str | list[str] | None = None) -> dict[str, datetime]:
    particoes = [cnpj] if isinstance(cnpj, str) else list(cnpj or [])
    todos = carimbos_das_tabelas(pasta, *nomes)
    saida = {}
    for nome in nomes:
        chaves = (
            [nome, *(f"{nome}_{p}" for p in particoes)]
            if particoes
            else [c for c in todos if c == nome or c.startswith(f"{nome}_")]
        )
        momentos = []
        for chave in chaves:
            try:
                momentos.append(datetime.fromisoformat(todos[chave]))
            except (KeyError, TypeError, ValueError):
                continue
        if momentos:
            saida[nome] = max(momentos)
    return saida


def obter_atualizacao(pasta: Path, *nomes: str, cnpj: str | list[str] | None = None) -> datetime | None:
    dados = carimbos(pasta)
    particoes = [cnpj] if isinstance(cnpj, str) else (list(cnpj or []) or [None])
    momentos = []
    for nome in nomes:
        for particao in particoes:
            chaves = (nome, f"{nome}_{particao}" if particao else None)
            do_nome = [dados[c] for c in chaves if c in dados]
            if do_nome:
                momentos.append(max(datetime.fromisoformat(m) for m in do_nome))
    return min(momentos) if momentos else None


def cartao_atualizacao(
    momento: datetime | date | None, cor_fundo: str, dias_tolerancia: int = 0, detalhe: str | None = None
) -> ui.Tag:
    if momento is None:
        texto, desatualizado = "-", True
    else:
        com_hora = isinstance(momento, datetime)
        dia = momento.date() if com_hora else momento
        texto = momento.strftime("%d/%m/%Y %H:%M") if com_hora else dia.strftime("%d/%m/%Y")
        desatualizado = (date.today() - dia).days > dias_tolerancia

    classes = "valuebox-atualizacao"
    if desatualizado:
        classes += " valuebox-desatualizado"

    return ui.value_box(
        "Atualizado em",
        ui.span(texto, title=detalhe) if detalhe else texto,
        theme=ui.value_box_theme(bg=FAROL_CRITICO if desatualizado else cor_fundo, fg="#fff"),
        class_=classes,
        fill=False,
    )
