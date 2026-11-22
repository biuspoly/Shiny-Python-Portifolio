"""Gera os dados fictícios de todos os apps.

Uso (da raiz do repositório): python -m gerador.gerar_tudo [app ...]
"tema" recompila o CSS do Flatly; só roda quando pedido (precisa do libsass).
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from gerador import acessos, comercial, comodato, financeiro, fiscal, logistico, monitoramento, r_dados, tema  # noqa: E402

GERADORES = {
    "comercial": comercial.gerar,
    "logistico": logistico.gerar,
    "comodato": comodato.gerar,
    "financeiro": financeiro.gerar,
    "fiscal": fiscal.gerar,
    "monitoramento": monitoramento.gerar,
    "acessos": acessos.gerar,
    # Os apps em R usam cópias dos mesmos .parquet: vem depois dos apps em Python.
    "r": r_dados.gerar,
    "tema": tema.gerar,
}

if __name__ == "__main__":
    escolhidos = [a.lower() for a in sys.argv[1:]] or [g for g in GERADORES if g != "tema"]
    for nome in escolhidos:
        GERADORES[nome]()
