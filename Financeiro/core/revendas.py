"""Cadastro das revendas fictícias do portfólio."""

from dataclasses import dataclass

from core.config import REVENDAS_CNPJ, chave_revenda


@dataclass(frozen=True)
class Revenda:
    nome: str
    cnpj: str


REVENDAS = [Revenda(nome, cnpj) for nome, cnpj in REVENDAS_CNPJ.items()]


def por_nome(revenda: str | None) -> Revenda | None:
    alvo = chave_revenda(revenda)
    return next((r for r in REVENDAS if chave_revenda(r.nome) == alvo), None)


def nome_oficial(revenda: str | None) -> str | None:
    achada = por_nome(revenda)
    return achada.nome if achada else None
