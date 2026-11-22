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


def por_nome_em_qualquer_erp(revenda: str | None) -> Revenda | None:
    return por_nome(revenda)


def eh_do_segundo_erp(revenda: str | None) -> bool:
    return False


def cnpj_da_revenda(revenda: str | None) -> str | None:
    achada = por_nome(revenda)
    return achada.cnpj if achada else None


def cnpj_em_qualquer_erp(revenda: str | None) -> str | None:
    return cnpj_da_revenda(revenda)


def cnpj_por_nome_oficial() -> dict[str, str]:
    return {r.nome: r.cnpj for r in REVENDAS}
