from __future__ import annotations

import asyncio
from pathlib import Path

PASTA_APP = Path(__file__).parents[3]
SCRIPT_REENVIO = PASTA_APP / "scripts" / "reenviar_email_cev.py"

TIMEOUT_SEGUNDOS = 300


def disponivel() -> tuple[bool, str]:
    if not SCRIPT_REENVIO.is_file():
        return False, f"Script de reenvio nao encontrado em {SCRIPT_REENVIO}."
    return True, ""


async def reenviar(
    cev: str, cnpj_rev: str, revenda: str = "", usuario: str = "", executar: bool = False
) -> tuple[bool, str, int | None]:
    """Portfólio: o e-mail com o link de assinatura não é enviado; a tela segue como se tivesse ido."""
    await asyncio.sleep(1.0)
    return True, "E-mail de assinatura reenviado ao cliente (simulação do portfólio)", None
