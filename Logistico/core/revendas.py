from __future__ import annotations

import unicodedata
from typing import NamedTuple


class Revenda(NamedTuple):
    nome: str
    cnpj: str
    licenca: str
    email: str
    dsn: str
    digito: int
    tabela_prod: int
    prefixo: str
    tabref: str
    ocorrencia_recolha: int
    uf: str


# Portfólio: as quatro revendas fictícias (no original, o cadastro das empresas com o acesso ao ERP de cada uma).
REVENDAS: tuple[Revenda, ...] = (
    Revenda("Natal", "00000000000100", "4101", "contato@natal.exemplo", "ERP_4101", 1, 1, "", "2018.01", 73, "RN"),
    Revenda(
        "Fortaleza", "00000000000280", "4102", "contato@fortaleza.exemplo", "ERP_4102", 1, 1, "", "2018.02", 73, "CE"
    ),
    Revenda(
        "Teresina", "00000000000360", "4103", "contato@teresina.exemplo", "ERP_4103", 1, 1, "", "2018.03", 73, "PI"
    ),
    Revenda("São Luís", "00000000000440", "4104", "contato@saoluis.exemplo", "ERP_4104", 1, 1, "", "2018.04", 73, "MA"),
)

# No original, uma empresa usa a conexão do ERP de outra; no portfólio não há esse caso.
CNPJ_SEM_ERP_PROPRIO = "00000000000990"
CNPJ_ERP_EMPRESTADO = "00000000000990"

APELIDOS: dict[str, str] = {}


def _chave(texto: str | None) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).strip().lower()


def chave_nome(texto: str | None) -> str:
    return _chave(texto)


_POR_NOME: dict[str, Revenda] = {_chave(r.nome): r for r in REVENDAS}
_POR_NOME.update({_chave(apelido): _POR_NOME[_chave(oficial)] for apelido, oficial in APELIDOS.items()})
_POR_CNPJ: dict[str, Revenda] = {r.cnpj: r for r in REVENDAS}


def _so_digitos(texto: str | None) -> str:
    return "".join(c for c in str(texto or "") if c.isdigit())


def por_nome(revenda: str | None) -> Revenda | None:
    return _POR_NOME.get(_chave(revenda))


def por_cnpj(cnpj: str | None) -> Revenda | None:
    return _POR_CNPJ.get(_so_digitos(cnpj))


def cnpj_da_revenda(revenda: str | None) -> str | None:
    achada = por_nome(revenda)
    return achada.cnpj if achada else None


def grafias_conhecidas(revenda: str | None) -> tuple[str, ...]:
    achada = por_nome(revenda)
    if achada is None:
        return ()
    apelidos = tuple(apelido for apelido, oficial in APELIDOS.items() if _chave(oficial) == _chave(achada.nome))
    return (achada.nome, *apelidos)


def licenca_da_revenda(revenda: str | None) -> str | None:
    achada = por_nome(revenda)
    return achada.licenca if achada else None


def para_erp(
    *,
    chave_dsn: str = "dsn",
    conexao_de: dict[str, str] | None = None,
    campos: tuple[str, ...] | None = None,
) -> list[dict]:
    conexao_de = conexao_de or {}
    por_cnpj = {r.cnpj: r for r in REVENDAS}
    lista = []
    for revenda in REVENDAS:
        doadora = por_cnpj.get(conexao_de.get(revenda.cnpj, ""), revenda)
        completo = {
            "cnpj": revenda.cnpj,
            "nome": revenda.nome,
            chave_dsn: doadora.dsn,
            "digito": doadora.digito,
            "tabela_prod": doadora.tabela_prod,
            "prefixo": doadora.prefixo,
            "tabref": revenda.tabref,
            "licenca": revenda.licenca,
            "ocorrencia_recolha": revenda.ocorrencia_recolha,
            "uf": revenda.uf,
        }
        lista.append(completo if campos is None else {c: completo[c] for c in campos})
    return lista


def cnpjs() -> list[str]:
    return [r.cnpj for r in REVENDAS]


def cnpj_por_nome_maiusculo() -> dict[str, str]:
    curto = {_chave(oficial): apelido.upper() for apelido, oficial in APELIDOS.items()}
    return {curto.get(_chave(r.nome), r.nome.upper()): r.cnpj for r in REVENDAS}


def cnpj_por_nome_oficial() -> dict[str, str]:
    return {r.nome: r.cnpj for r in REVENDAS}


def nome_oficial(revenda: str | None) -> str | None:
    achada = por_nome(revenda)
    return achada.nome if achada else None
