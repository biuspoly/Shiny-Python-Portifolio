"""Formatação brasileira de números para as tabelas e cartões (vazio quando não há valor)."""

from __future__ import annotations

import math


def vazio(valor) -> bool:
    return valor is None or (isinstance(valor, float) and math.isnan(valor))


def numero(valor, casas: int = 0) -> str:
    if vazio(valor):
        return ""
    texto = f"{float(valor):,.{casas}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def moeda(valor, casas: int = 2) -> str:
    return "" if vazio(valor) else f"R$ {numero(valor, casas)}"


def percentual(fracao, casas: int = 1) -> str:
    return "" if vazio(fracao) else f"{numero(float(fracao) * 100, casas)}%"


def razao(numerador, denominador):
    """numerador / denominador, ou None quando o denominador é zero ou vazio."""
    if vazio(numerador) or vazio(denominador) or not denominador:
        return None
    return float(numerador) / float(denominador)
