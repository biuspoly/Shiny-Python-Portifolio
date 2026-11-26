"""Portfólio: a resposta dos scripts que, no original, falam com o ERP (pedido de comodato, recolha,
cancelamento e conferência do pré-pedido, sincronia do cadastro). Cada um devolve o mesmo
"RESULTADO" do script real e mexe só no que o script mexeria do lado do painel."""

from __future__ import annotations

from datetime import date

import polars as pl

from . import banco_memoria as bm

TABELA = "comod_solicitado_bruto"


def _proximo_pre_pedido(base: pl.DataFrame) -> str:
    """A faixa do original: AAAAMMDD + 5000 em diante, um número por pedido no dia."""
    prefixo = f"{date.today():%Y%m%d}"
    usados = [
        int(str(p)[8:])
        for p in (base["PRE_PED"].drop_nulls().to_list() if "PRE_PED" in base.columns else [])
        if str(p).startswith(prefixo) and str(p)[8:].isdigit()
    ]
    return f"{prefixo}{max([4999, *usados]) + 1}"


def _enviar(revenda: str, cliente: str, data: str, prazo: str, tipo: str) -> str:
    base = bm.ler(TABELA)
    alvo = bm.condicao(
        {"REVENDA": revenda, "CLIENTE": cliente, "DATA": data, "PRAZO": prazo, "TIPO": tipo, "PRE_PED": None}
    )
    if base.height == 0 or not base.filter(alvo).height:
        return "sem_itens"
    numero = _proximo_pre_pedido(base)
    base = base.with_columns(
        pl.when(alvo).then(pl.lit(numero)).otherwise(pl.col("PRE_PED").cast(pl.Utf8)).alias("PRE_PED")
    )
    bm.gravar(TABELA, base)
    return "pegou"


def _cancelar(revenda: str, pre_pedido: str, simular: bool) -> str:
    base = bm.ler(TABELA)
    alvo = bm.condicao({"REVENDA": revenda, "PRE_PED": pre_pedido})
    if base.height == 0 or not base.filter(alvo).height:
        return "sem_itens|a solicitação não está mais registrada com esse número"
    if simular:
        return "pode_cancelar|"
    base = base.with_columns(
        pl.when(alvo).then(pl.lit(None, dtype=pl.Utf8)).otherwise(pl.col("PRE_PED")).alias("PRE_PED")
    )
    bm.gravar(TABELA, base)
    return "cancelado|"


def _conferir(revenda: str) -> str:
    base = bm.ler(TABELA)
    if base.height == 0:
        return "0 pedido(s) ainda no ERP"
    enviados = base.filter((pl.col("REVENDA") == revenda) & pl.col("PRE_PED").is_not_null())
    return f"{enviados['PRE_PED'].n_unique()} pedido(s) ainda no ERP"


def responder(script: str, argumentos: list[str]) -> str:
    simular = "--simular" in argumentos
    posicionais = [a for a in argumentos if not a.startswith("--")]
    if script == "enviar_pedido_comodato.py":
        return _enviar(*posicionais[:5])
    if script == "cancelar_pre_pedido_control.py":
        return _cancelar(posicionais[0], posicionais[1], simular)
    if script == "verifica_pre_pedido_control.py":
        return _conferir(argumentos[argumentos.index("--revenda") + 1] if "--revenda" in argumentos else "")
    # Recolha e sincronia do cadastro: o ERP aceita; o painel só vê o efeito na próxima atualização.
    return "pegou"
