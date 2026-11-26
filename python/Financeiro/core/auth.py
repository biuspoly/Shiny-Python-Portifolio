"""Portfólio: sem login. Quem abre a página é sempre o mesmo visitante."""

from core.config import USUARIO_PORTFOLIO


def identificar_usuario(conexao) -> tuple[str, None]:
    return USUARIO_PORTFOLIO, None


def usuario_pode_ver_pagina(usuario: str | None, pagina: str, revenda: str | None = None) -> bool:
    return True
