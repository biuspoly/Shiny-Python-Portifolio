from __future__ import annotations

import asyncio
from pathlib import Path

PASTA_APP = Path(__file__).parents[3]
SCRIPT_ENVIO = PASTA_APP / "scripts" / "enviar_pedido_comodato.py"
SCRIPT_RECOLHA = PASTA_APP / "scripts" / "recolher_comodato.py"
SCRIPT_CADCLI = PASTA_APP / "scripts" / "sincronizar_cadcli.py"
SCRIPT_CANCELA_PRE_PEDIDO = PASTA_APP / "scripts" / "cancelar_pre_pedido_control.py"
SCRIPT_CONFERE_PRE_PEDIDO = PASTA_APP / "scripts" / "verifica_pre_pedido_control.py"

TIMEOUT_SEGUNDOS = 180


async def _rodar(script: Path, *argumentos: str) -> str:
    """Portfólio: no lugar do script que fala com o ERP, a mesma resposta (RESULTADO) feita na memória."""
    from . import erp_simulado

    await asyncio.sleep(1.2)  # o ERP de verdade leva alguns segundos; a tela de espera aparece igual
    return erp_simulado.responder(script.name, list(argumentos))


LIMITE_DE_LICENCAS = "Limite de licenças atingido"


def erro_amigavel(exc: Exception, nada_feito: str) -> tuple[str, str]:
    detalhe = str(exc).lower()
    if "exceeds user license" in detalhe:
        return LIMITE_DE_LICENCAS, (
            f"O ERP está com todas as licenças de acesso ocupadas, então {nada_feito}."
            " Espere alguns minutos e tente de novo."
        )
    if "nao respondeu" in detalhe:
        return "O ERP não respondeu", (
            "O ERP demorou demais e a operação parou no meio do caminho. Confira no"
            " ERP como ficou antes de repetir: se já estiver lá, repetir criaria"
            " duplicado."
        )
    return "Não foi possível falar com o ERP", (
        "A conversa com o ERP falhou no meio do caminho. Confira no ERP como ficou"
        " antes de repetir: se já estiver lá, repetir criaria duplicado. Se o erro continuar,"
        " avise a TI."
    )


async def enviar_pedido(revenda: str, cliente: str, data: str, prazo: str, tipo: str) -> str:
    return await _rodar(SCRIPT_ENVIO, revenda, cliente, data, prazo, tipo)


async def gerar_recolha(revenda: str, cev: str, pela_revenda: bool = False, usuario: str = "") -> str:
    argumentos = [revenda, str(cev)] + (["--pela-revenda"] if pela_revenda else [])
    if usuario:
        argumentos += ["--usuario", usuario]
    return await _rodar(SCRIPT_RECOLHA, *argumentos)


async def cancelar_pre_pedido(revenda: str, pre_pedido: str, cliente: str, simular: bool = True) -> tuple[str, str]:
    argumentos = [revenda, str(pre_pedido), cliente]
    if simular:
        argumentos.append("--simular")
    resposta = await _rodar(SCRIPT_CANCELA_PRE_PEDIDO, *argumentos)
    desfecho, _separador, motivo = resposta.partition("|")
    return desfecho.strip(), motivo.strip()


async def conferir_pre_pedidos(revenda: str) -> str:
    return await _rodar(SCRIPT_CONFERE_PRE_PEDIDO, "--revenda", revenda)


async def sincronizar_cadastro(revenda: str, codcli: str) -> str:
    return await _rodar(SCRIPT_CADCLI, revenda, str(codcli))
