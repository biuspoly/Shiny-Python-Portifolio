"""Onde ficam os arquivos do SPED. No original, o SPED gerado de cada mês; o portfólio não tem SPED."""

from pathlib import Path

_PASTA_APP = Path(__file__).resolve().parents[1]


def raiz() -> Path:
    return _PASTA_APP / "docs" / "sped"
