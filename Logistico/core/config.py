"""Configuração do portfólio: revendas fictícias, sem login nem permissão."""

NOME_APP = "Acompanhamento Logístico"
NOME_PORTFOLIO = "Portfólio Marlon Amaral"

# Nome da revenda (maiúsculo, como no cache) -> CNPJ fictício.
REVENDAS_CNPJ = {
    "NATAL": "00000000000100",
    "FORTALEZA": "00000000000280",
    "TERESINA": "00000000000360",
    "SÃO LUÍS": "00000000000440",
}

USUARIO_PORTFOLIO = "visitante"


def pode(usuario: str | None, funcionalidade: str) -> bool:
    """No original, cada ação tem a sua lista de responsáveis; aqui o visitante pode testar todas."""
    return True
