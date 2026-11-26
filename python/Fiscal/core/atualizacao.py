from __future__ import annotations

import json
import threading
from datetime import date, datetime
from pathlib import Path

from shiny import reactive, ui

from core.aviso import modal_aviso
from core.cores import FAROL_CRITICO

NOME_ARQUIVO_METADADOS = "_atualizacoes.json"

_trava = threading.Lock()


def registra_atualizacao(pasta: Path, nome: str) -> None:
    caminho = pasta / NOME_ARQUIVO_METADADOS
    with _trava:
        dados = {}
        if caminho.exists():
            try:
                dados = json.loads(caminho.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                dados = {}
        dados[nome] = datetime.now().isoformat(timespec="seconds")
        caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def obter_atualizacao(pasta: Path, *nomes: str, cnpj: str | list[str] | None = None) -> datetime | None:
    caminho = pasta / NOME_ARQUIVO_METADADOS
    if not caminho.exists():
        return None
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    particoes = [cnpj] if isinstance(cnpj, str) else (list(cnpj or []) or [None])
    momentos = []
    for nome in nomes:
        for particao in particoes:
            chaves = (nome, f"{nome}_{particao}" if particao else None)
            do_nome = [dados[c] for c in chaves if c in dados]
            if do_nome:
                momentos.append(max(datetime.fromisoformat(m) for m in do_nome))
    return min(momentos) if momentos else None


def cartao_atualizacao(momento: datetime | date | None, cor_fundo: str, dias_tolerancia: int = 0) -> ui.Tag:
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
        texto,
        theme=ui.value_box_theme(bg=FAROL_CRITICO if desatualizado else cor_fundo, fg="#fff"),
        class_=classes,
        fill=False,
    )


def fim_do_atualizar(versao_cache, ressalva: str | None, receita: str | None = None) -> ui.Tag:
    with reactive.isolate():
        versao_cache.set(versao_cache() + 1)
    da_receita = f" {receita}" if receita else ""
    if ressalva:
        return modal_aviso(
            f"O que ficou de fora: {ressalva.rstrip('. ')}. O resto já está na tela.{da_receita}",
            "Atualização concluída com ressalva",
            "warning",
        )
    return modal_aviso(f"Os dados da tela já são os novos.{da_receita}", "Atualização concluída", "success")
