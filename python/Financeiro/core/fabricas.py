from __future__ import annotations

from datetime import date, timedelta

import polars as pl

from core.config import REVENDAS_POR_GRUPO, chave_revenda
from core.config_arquivo import carregar_json


def _parametros() -> dict:
    return carregar_json("parametros_financeiro") or {}


def fabricas() -> dict[str, dict]:
    lidas = _parametros().get("fabricas") or {}
    return {
        chave: {**conf, "chave": chave, "prefixos": tuple(str(p).upper() for p in conf.get("prefixos") or ())}
        for chave, conf in lidas.items()
    }


def fabrica_do_fornecedor(nome: str | None, todas: dict | None = None) -> dict | None:
    limpo = str(nome or "").strip().upper()
    if not limpo:
        return None
    for conf in (todas if todas is not None else fabricas()).values():
        if any(limpo.startswith(p) for p in conf["prefixos"]):
            return conf
    return None


def fabrica_da_revenda(revenda: str | None) -> dict | None:
    regra = _parametros().get("fabrica_por_revenda") or {}
    por_chave = {chave_revenda(nome): chave for nome, chave in regra.items() if not str(nome).startswith("_")}
    alvo = chave_revenda(revenda)
    if alvo in por_chave:
        escolhidas = {por_chave[alvo]}
    else:
        membros = next(
            (lista for grupo, lista in REVENDAS_POR_GRUPO.items() if chave_revenda(grupo) == alvo),
            [],
        )
        escolhidas = {por_chave.get(chave_revenda(m)) for m in membros}
    if len(escolhidas) != 1 or None in escolhidas:
        return None
    return fabricas().get(escolhidas.pop())


def expressao_da_fabrica(coluna: str, conf: dict) -> pl.Expr:
    nome = pl.col(coluna).cast(pl.Utf8).fill_null("").str.to_uppercase()
    condicao = pl.lit(False)
    for prefixo in conf["prefixos"]:
        condicao = condicao | nome.str.starts_with(prefixo)
    return condicao


def dispensa_auditoria_na_revenda(revenda: str | None) -> bool:
    alvo = chave_revenda(revenda)
    return any(chave_revenda(nome) == alvo for nome in _parametros().get("revendas_sem_auditoria_para_pagar") or ())


def inicio_do_banco() -> date:
    try:
        return date.fromisoformat(str((_parametros().get("banco_mar") or {}).get("inicio")))
    except ValueError:
        return date.today() + timedelta(days=1)
