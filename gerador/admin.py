"""Uso dos apps (Monitoramento) e permissões (Acessos) fictícios."""

import json
from datetime import date, datetime, timedelta

import polars as pl

from gerador import base as b

PAGINAS = {
    "Comercial": ["Diário de Vendas", "Carteira", "Mapa Comercial", "Markup"],
    "Logístico": ["Romaneios", "Devoluções", "Frotas", "Comodatos"],
    "Financeiro": ["Fluxo de Caixa", "Contas a Pagar", "Conciliação", "Farol de Caixa"],
    "Fiscal": ["Painel", "Documentos", "Manifestação", "Escrituração"],
}
# Que apps cada área usa no dia a dia (o resto é eventual).
APPS_DA_AREA = {
    "Comercial": ["Comercial"],
    "Logística": ["Logístico", "Comercial"],
    "Financeiro": ["Financeiro", "Fiscal"],
    "Fiscal": ["Fiscal", "Financeiro"],
    "TI": ["Comercial", "Logístico", "Financeiro", "Fiscal"],
    "Diretoria": ["Comercial", "Financeiro"],
}
PAPEIS = {
    "Comercial": "Vendas",
    "Logística": "Operação logística",
    "Financeiro": "Tesouraria",
    "Fiscal": "Fiscal",
    "TI": "Administrador",
    "Diretoria": "Diretoria",
}
ROTINAS = [
    ("Vendas do ERP", "Comercial", 6.0),
    ("Metas e cobertura", "Comercial", 2.5),
    ("Entregas e romaneios", "Logístico", 4.0),
    ("Frota e multas", "Logístico", 1.5),
    ("Contas a pagar e receber", "Financeiro", 3.0),
    ("Extratos bancários", "Financeiro", 2.0),
    ("Documentos da SEFAZ", "Fiscal", 7.5),
    ("Indicadores do Banco Central", "Financeiro", 0.4),
]
ERROS = [
    ("Comercial", "Mapa Comercial", "Tempo esgotado ao carregar a malha do município"),
    ("Logístico", "Romaneios", "Romaneio sem placa vinculada"),
    ("Financeiro", "Conciliação", "Extrato com data fora do mês escolhido"),
    ("Fiscal", "Documentos", "XML com assinatura inválida"),
    ("Fiscal", "Manifestação", "SEFAZ indisponível (código 108)"),
    ("Comercial", "Diário de Vendas", "Vendedor sem gerente cadastrado"),
]


def _sessoes(usuarios: pl.DataFrame) -> pl.DataFrame:
    r = b.rng("sessoes")
    linhas = []
    for u in usuarios.iter_rows(named=True):
        if not u["ativo"]:
            continue
        frequencia = r.uniform(0.35, 0.95)
        for d in b.dias_uteis(b.HOJE - timedelta(days=60), b.HOJE):
            if d.weekday() == 5 and r.random() < 0.7:
                continue
            if r.random() > frequencia:
                continue
            for _ in range(r.choices([1, 2, 3], weights=[60, 30, 10])[0]):
                app = r.choice(APPS_DA_AREA[u["area"]]) if r.random() < 0.9 else r.choice(list(PAGINAS))
                inicio = datetime(d.year, d.month, d.day, r.randint(7, 17), r.randint(0, 59))
                if d == b.HOJE and inicio.hour > 11:
                    continue
                linhas.append(
                    {
                        "login": u["login"],
                        "app": app,
                        "pagina": r.choice(PAGINAS[app]),
                        "inicio": inicio,
                        "minutos": round(r.gammavariate(2.0, 9.0), 1),
                        "cliques": r.randint(3, 90),
                    }
                )
    return pl.DataFrame(linhas)


def _rotinas() -> pl.DataFrame:
    r = b.rng("rotinas")
    linhas = []
    for i in range(45, -1, -1):
        d = b.HOJE - timedelta(days=i)
        hora = datetime(d.year, d.month, d.day, 3, 0)
        for nome, app, minutos in ROTINAS:
            duracao = round(minutos * r.uniform(0.8, 1.35), 1)
            status = r.choices(["Sucesso", "Falha parcial", "Falha"], weights=[93, 5, 2])[0]
            # A SEFAZ fora do ar derruba a rotina fiscal de uma noite inteira.
            if nome == "Documentos da SEFAZ" and i in (9, 10):
                status = "Falha"
            linhas.append(
                {
                    "rotina": nome,
                    "app": app,
                    "inicio": hora,
                    "minutos": duracao,
                    "status": status,
                    "linhas": 0 if status == "Falha" else r.randint(800, 60000),
                }
            )
            hora += timedelta(minutes=duracao)
    return pl.DataFrame(linhas)


def _erros(usuarios: pl.DataFrame) -> pl.DataFrame:
    r = b.rng("erros")
    logins = usuarios.filter(pl.col("ativo"))["login"].to_list()
    linhas = []
    for d in b.dias_uteis(b.HOJE - timedelta(days=30), b.HOJE):
        for _ in range(r.choices([0, 1, 2, 4], weights=[40, 35, 18, 7])[0]):
            app, pagina, msg = r.choices(ERROS, weights=[3, 4, 2, 5, 2, 1])[0]
            linhas.append(
                {
                    "momento": datetime(d.year, d.month, d.day, r.randint(7, 18), r.randint(0, 59)),
                    "app": app,
                    "pagina": pagina,
                    "mensagem": msg,
                    "login": r.choice(logins),
                }
            )
    return pl.DataFrame(linhas)


def _permissoes(usuarios: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    r = b.rng("permissoes")
    gestores = usuarios.filter(pl.col("area") == "TI")["login"].to_list()
    linhas, historico = [], []
    for u in usuarios.iter_rows(named=True):
        for app in APPS_DA_AREA[u["area"]]:
            principal = app == APPS_DA_AREA[u["area"]][0]
            for pagina in PAGINAS[app]:
                if principal or u["area"] in ("TI", "Diretoria") or r.random() < 0.35:
                    linhas.append({"login": u["login"], "app": app, "pagina": pagina})
                    quando = datetime.combine(
                        b.HOJE - timedelta(days=r.randint(1, 420)), datetime.min.time()
                    ) + timedelta(hours=r.randint(8, 17), minutes=r.randint(0, 59))
                    historico.append(
                        {
                            "momento": quando,
                            "feito_por": r.choice(gestores),
                            "login": u["login"],
                            "app": app,
                            "pagina": pagina,
                            "acao": "Concedeu",
                        }
                    )
        # Algumas retiradas: quem mudou de função perdeu páginas de outro app.
        if r.random() < 0.25:
            app = r.choice(list(PAGINAS))
            quando = datetime.combine(b.HOJE - timedelta(days=r.randint(1, 90)), datetime.min.time()) + timedelta(
                hours=r.randint(8, 17)
            )
            historico.append(
                {
                    "momento": quando,
                    "feito_por": r.choice(gestores),
                    "login": u["login"],
                    "app": app,
                    "pagina": r.choice(PAGINAS[app]),
                    "acao": "Removeu",
                }
            )
        if not u["ativo"]:
            historico.append(
                {
                    "momento": datetime.combine(b.HOJE - timedelta(days=r.randint(5, 60)), datetime.min.time())
                    + timedelta(hours=10),
                    "feito_por": r.choice(gestores),
                    "login": u["login"],
                    "app": "Todos",
                    "pagina": "Todas",
                    "acao": "Desativou",
                }
            )
    return pl.DataFrame(linhas), pl.DataFrame(historico).sort("momento", descending=True)


def _gravar_data(app: str) -> None:
    with open(b.RAIZ / app / "data" / "_gerado_em.json", "w", encoding="utf-8") as arq:
        json.dump({"data_base": b.HOJE.isoformat(), "gerado_em": date.today().isoformat()}, arq)


def gerar() -> None:
    usuarios = b.usuarios().with_columns(pl.col("area").replace_strict(PAPEIS).alias("papel"))
    print("Monitoramento")
    b.gravar(usuarios, "Monitoramento", "usuarios")
    b.gravar(_sessoes(usuarios), "Monitoramento", "sessoes")
    b.gravar(_rotinas(), "Monitoramento", "rotinas")
    b.gravar(_erros(usuarios), "Monitoramento", "erros")
    _gravar_data("Monitoramento")
    print("Acessos")
    permissoes, historico = _permissoes(usuarios)
    b.gravar(usuarios, "Acessos", "usuarios")
    b.gravar(permissoes, "Acessos", "permissoes")
    b.gravar(historico, "Acessos", "historico")
    b.gravar(
        pl.DataFrame([{"app": a, "pagina": p, "ordem": i} for a, ps in PAGINAS.items() for i, p in enumerate(ps)]),
        "Acessos",
        "paginas",
    )
    _gravar_data("Acessos")
