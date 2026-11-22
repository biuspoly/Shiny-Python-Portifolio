"""Configuração do portfólio: revendas fictícias, sem login nem permissão."""

import unicodedata

from core.config_arquivo import carregar_json

NOME_APP = "Acompanhamento Financeiro"
NOME_PORTFOLIO = "Portfólio Marlon Amaral"
USUARIO_PORTFOLIO = "visitante"

# Nome da revenda -> CNPJ fictício (os mesmos do Logístico).
REVENDAS_CNPJ = {
    "Natal": "00000000000100",
    "Fortaleza": "00000000000280",
    "Teresina": "00000000000360",
    "São Luís": "00000000000440",
}

# Grupo na URL (?REVENDA=) -> revendas dele. Sem grupo nenhum no portfólio.
REVENDAS_POR_GRUPO: dict[str, list[str]] = {}


def chave_revenda(texto: str | None) -> str:
    sem_acento = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    return "".join(c for c in sem_acento if c.isalnum() or c == " ").upper().strip()


def chaves_das_revendas(nomes) -> set[str]:
    return {chave_revenda(n) for n in nomes or ()}


def casar_revendas(nomes_do_dado, alvos) -> list[str]:
    procurados = {chave_revenda(a) for a in alvos}
    return sorted(n for n in nomes_do_dado if n and chave_revenda(n) in procurados)


def pode(usuario: str | None, funcionalidade: str, revenda: str | None = None) -> bool:
    """No original, cada ação tem a sua lista de responsáveis; aqui o visitante pode testar todas."""
    return True


def quem_libera(*chaves: str) -> str:
    return ""


def sem_extrato_fabrica(revenda: str | None) -> bool:
    nomes = {chave_revenda(n) for n in carregar_json("parametros_financeiro").get("revendas_sem_extrato_fabrica") or ()}
    return bool(revenda) and chave_revenda(revenda) in nomes


def url_da_revenda(nome: str | None) -> str | None:
    return chave_revenda(nome) if nome else None
