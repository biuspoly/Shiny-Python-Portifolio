"""A consulta ao ERP do Extrato. No original, roda num processo à parte (ODBC) e grava o
cache; no portfólio, o cache já vem gerado e a "consulta" só o devolve, depois de uma
espera curta para o aviso de consulta aparecer como no original. A gravação da Situação
vale para o cache desta sessão."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from typing import NamedTuple

from . import baixa_extrato_control as bx
from . import extrato_control as ec

TIMEOUT_SEGUNDOS = 120.0
INTERVALO_MINIMO = timedelta(minutes=5)
ESPERA_DEPOIS_DE_ERRO = timedelta(minutes=5)
ESPERA_SIMULADA_SEGUNDOS = 1.2

_rodando: set[str] = set()


class ConsultaCedida(RuntimeError):
    """O catálogo encerrado porque o "Gerar dados" pediu o movimento: não é erro."""


class Explicacao(NamedTuple):
    curto: str
    texto: str
    conselho: str


def sincronizando(cnpj: str) -> bool:
    return cnpj in _rodando


def erro_recente(cnpj: str) -> tuple[datetime, str] | None:
    return None


def cache_basta(cnpj: str, desde: date) -> bool:
    info = ec.ler_info(cnpj)
    return bool(info) and desde >= date.fromisoformat(info["desde"])


def precisa_sincronizar(cnpj: str, desde: date) -> bool:
    return not sincronizando(cnpj) and not cache_basta(cnpj, desde)


def explicar_erro(erro: str | None) -> Explicacao:
    return Explicacao("erro na consulta", "O ERP devolveu um erro na consulta.", "Tente novamente mais tarde.")


def precisa_catalogo(cnpj: str) -> bool:
    return False


async def consultar(modo: str, revenda: str, cnpj: str, *argumentos: str, usuario: str = "") -> dict:
    await asyncio.sleep(ESPERA_SIMULADA_SEGUNDOS)
    if modo == "catalogo":
        return ec.ler_catalogo(cnpj) or {}
    if modo == "baixar":
        linhas_json, data, _usuario, gravar = argumentos
        linhas = json.loads(linhas_json)
        if gravar != "1":
            return {"situacao": "simulada", "linhas": len(linhas)}
        lmo = bx.data_baixa(None if data == "-" else data) or ""
        return {"situacao": "gravada", "linhas": ec.aplicar_baixa(cnpj, linhas, lmo)}
    return ec.ler_info(cnpj) or {}


async def sincronizar(revenda: str, cnpj: str, desde: date, usuario: str = "") -> dict | None:
    _rodando.add(cnpj)
    try:
        await asyncio.sleep(ESPERA_SIMULADA_SEGUNDOS)
        return ec.ler_info(cnpj)
    finally:
        _rodando.discard(cnpj)
