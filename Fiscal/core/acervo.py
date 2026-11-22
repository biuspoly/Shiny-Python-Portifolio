"""Onde ficam os arquivos que o app guarda (XML, preferências). No portfólio, a pasta docs/ do app."""

from pathlib import Path

_PASTA_APP = Path(__file__).resolve().parents[1]


def raiz() -> Path:
    pasta = _PASTA_APP / "docs"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def ler(relativo: str) -> bytes:
    base = raiz().resolve()
    alvo = (base / relativo).resolve()
    if not alvo.is_relative_to(base):
        raise ValueError("arquivo fora do acervo")
    return alvo.read_bytes()
