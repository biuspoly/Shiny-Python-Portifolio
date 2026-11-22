"""O que a tela grava (justificativa de juros, marcação de célula, configuração de
empréstimo). No original vai para arquivo e MySQL; no portfólio fica na memória desta
sessão (no Shinylive, cada visitante tem o próprio Python)."""

from datetime import datetime

import polars as pl

_JUROS: dict[tuple[str, str], dict] = {}
_CELULAS: dict[str, dict] = {}
_CONFIGS_EMPRESTIMO: list[dict] = []
_ENVIOS: list[dict] = []


def pagamentos_por_titulo() -> dict[str, dict]:
    return {}


def justificativas_juros() -> dict[tuple[str, str], dict]:
    return dict(_JUROS)


def justificar_juros(dados: dict) -> None:
    _JUROS[(str(dados.get("revenda") or ""), str(dados.get("documento") or ""))] = dict(dados)


def celulas_marcadas_mare() -> dict[str, dict]:
    return dict(_CELULAS)


def marcar_celula_mare(linha: str, coluna: str, amarela: bool, laranja: bool, usuario: str) -> None:
    """Os dois estados são exclusivos: marcar amarelo desliga o laranja."""
    _CELULAS[f"{linha}|{coluna}"] = {"amarela": bool(amarela), "laranja": bool(laranja) and not amarela}


def configs_emprestimo() -> pl.DataFrame:
    schema = {
        "revenda": pl.Utf8,
        "contrato": pl.Utf8,
        "valor_credito": pl.Float64,
        "entrada": pl.Float64,
        "taxa_juros": pl.Float64,
    }
    if not _CONFIGS_EMPRESTIMO:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(_CONFIGS_EMPRESTIMO, schema=schema)


def guardar_config_emprestimo(linha: dict) -> None:
    chave = (linha.get("revenda"), linha.get("contrato"))
    for i, atual in enumerate(_CONFIGS_EMPRESTIMO):
        if (atual.get("revenda"), atual.get("contrato")) == chave:
            _CONFIGS_EMPRESTIMO[i] = {**atual, **linha}
            return
    _CONFIGS_EMPRESTIMO.append(dict(linha))


def registrar_envio(revenda: str, extrato: str, usuario: str) -> None:
    _ENVIOS.append({"revenda": revenda, "extrato": extrato, "usuario": usuario, "enviado_em": datetime.now()})
