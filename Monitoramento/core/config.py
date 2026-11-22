from pathlib import Path

TITULO_APP = "Acompanhamento de Monitoramento - Portfólio Marlon Amaral"

# No original, cada app grava o próprio logs/app.log na pasta dele, e o Monitoramento lê as
# pastas vizinhas. No portfólio cada app é um pacote à parte no navegador: os logs (fictícios)
# ficam dentro deste, em data/logs/<app>/logs/.
PASTA_LOGS = Path(__file__).parent.parent / "data" / "logs"

APPS_MONITORADOS = [
    {"nome": nome, "porta": porta, "caminho_url": caminho, "pasta": PASTA_LOGS / nome}
    for nome, porta, caminho in (
        ("Comercial", 7001, "/comercial/"),
        ("Logistico", 7004, "/logistico/"),
        ("Acessos", 7006, "/acessos/"),
        ("Financeiro", 7008, "/financeiro/"),
        ("Fiscal", 7009, "/fiscal/"),
    )
]

# Os pipelines não são um serviço no ar, são execuções: entram só como fonte de log.
FONTES_LOG = APPS_MONITORADOS + [{"nome": "Pipelines", "pasta": PASTA_LOGS / "Pipelines"}]
