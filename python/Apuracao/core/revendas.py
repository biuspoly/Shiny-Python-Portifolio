"""Cadastro das revendas fictícias do portfólio (o mesmo de config/empresas.json)."""

from typing import NamedTuple

from core.config import empresas


class Revenda(NamedTuple):
    nome: str
    cnpj: str


def _chave(texto: str | None) -> str:
    return " ".join(str(texto or "").upper().split())


def por_nome(revenda: str | None) -> Revenda | None:
    return next(
        (Revenda(e["revenda"], e["cnpj"]) for e in empresas() if _chave(e.get("revenda")) == _chave(revenda)), None
    )
