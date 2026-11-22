"""No original, pergunta a cada app (rota /_saude) se está no ar, há quanto tempo e quem está
conectado. No portfólio não há serviço para perguntar: todos "no ar" desde a madrugada, com
as sessões abertas montadas da última hora dos logs fictícios (sempre as mesmas no dia)."""

import random
from datetime import datetime

from core.config import FONTES_LOG
from core.leitura_logs import atualizar, ler_sessoes

PAGINAS_POR_APP = {
    "Comercial": ["Diário de Vendas", "Curva ABC", "Mapa Comercial"],
    "Logistico": ["Frota: Geral", "PDE", "Devoluções: Detalhes", "Devoluções: Gráficos"],
    "Acessos": ["Visão Geral", "Usuários", "Permissões"],
    "Financeiro": ["Fluxo Financeiro", "Empréstimos", "Juros", "Extratos"],
    "Fiscal": ["Apuração", "Faturamento"],
}


def _sessoes_abertas(nome: str, agora: datetime) -> list[dict]:
    sorteio = random.Random(f"{nome}-{agora:%Y%m%d%H}")
    atualizar(FONTES_LOG)  # incremental: só lê o que os logs ganharam desde a última vez
    base = ler_sessoes()
    identificadas = base.filter((base["app"] == nome) & (base["usuario"] != "")) if base.height else base
    pessoas = list(dict.fromkeys(zip(identificadas["usuario"].to_list(), identificadas["revenda"].to_list())))
    sorteio.shuffle(pessoas)
    return [
        {
            "id": f"{nome[:3].lower()}{sorteio.randint(10000, 99999)}",
            "usuario": usuario,
            "revenda": revenda,
            "pagina": sorteio.choice(PAGINAS_POR_APP.get(nome, ["-"])),
            "conectado_ha_s": sorteio.randint(60, 5400),
        }
        for usuario, revenda in pessoas[: sorteio.randint(1, 4)]
    ]


def consultar_saude(app: dict, timeout: float = 0) -> dict:
    agora = datetime.now()
    madrugada = agora.replace(hour=4, minute=10, second=0, microsecond=0)
    sessoes = _sessoes_abertas(app["nome"], agora)
    return {
        "nome": app["nome"],
        "no_ar": True,
        "uptime_s": max(0, int((agora - madrugada).total_seconds())),
        "sessoes_ativas": len(sessoes),
        "sessoes": sessoes,
    }


async def consultar_todos(apps: list[dict]) -> list[dict]:
    return [consultar_saude(app) for app in apps]


def checar_servico(app: dict, timeout: float = 0) -> bool:
    return True
