"""Portfólio: sem login. Quem abre a página é sempre o mesmo visitante."""

from core.config import USUARIO_PORTFOLIO


def identificar_usuario(conexao) -> tuple[str, None]:
    return USUARIO_PORTFOLIO, None
