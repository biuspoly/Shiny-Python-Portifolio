"""Tabelas fictícias do banco de acessos (as mesmas do original): usuários, revendas, painéis,
grupos que dão acesso a cada painel e o registro de acessos."""

from datetime import datetime, timedelta

import polars as pl

from gerador import base as b

PASTA = b.RAIZ / "Acessos" / "data" / "bd_acessos"
DIAS_LOG = 60

REVENDAS = [
    ("4101", "Natal", "NATAL"),
    ("4102", "Fortaleza", "FORTALEZA"),
    ("4103", "Teresina", "TERESINA"),
    ("4104", "São Luís", "SAO LUIS"),
]
# Área -> painéis que ela usa (as telas do portfólio).
PAINEIS = {
    "Comercial": ["Diário de Vendas", "Curva ABC", "Mapa Comercial"],
    "Logística": ["Frota", "PDE", "Devoluções"],
    "Financeiro": ["Fluxo Financeiro", "Empréstimos", "Juros", "Extratos"],
    "Fiscal": ["Apuração", "Faturamento"],
    "TI": ["Monitoramento", "Acessos"],
}
CARGOS = {
    "Comercial": ["Vendedor", "Supervisor de Vendas", "Gerente Comercial"],
    "Logística": ["Analista de Logística", "Coordenador de Frota"],
    "Financeiro": ["Analista Financeiro", "Coordenador Financeiro"],
    "Fiscal": ["Analista Fiscal", "Contador"],
    "TI": ["Analista de Sistemas"],
    "Diretoria": ["Diretor"],
}


def gerar() -> None:
    print("Acessos")
    r = b.rng("acessos")
    PASTA.mkdir(parents=True, exist_ok=True)
    for antigo in PASTA.glob("*.parquet"):
        antigo.unlink()
    revenda = pl.DataFrame([{"licenca": lic, "nomeExib": nome, "nomeR": nome_r} for lic, nome, nome_r in REVENDAS])
    paineis, id_painel = [], 1
    for lic, _nome, _ in REVENDAS:
        for area, nomes in PAINEIS.items():
            for nome in nomes:
                id_painel += 1
                paineis.append(
                    {
                        "id": id_painel,
                        "nome": nome,
                        "licenca": lic,
                        "area": area,
                        "inativo": "1" if r.random() < 0.04 else "0",
                    }
                )
    dashboard = pl.DataFrame(paineis)
    usuarios, grupos = [], []
    for u in b.usuarios().to_dicts():
        area = u["area"]
        cargo = r.choice(CARGOS[area])
        ativo = u["ativo"]
        usuarios.append(
            {
                "login": u["login"],
                "nomeCompleto": u["nome"],
                "cargo": cargo,
                "funcao": area,
                "nomeGrupo": u["login"] if ativo else "Vazio",
                "Revenda": u["filial"],
            }
        )
        if not ativo:
            continue
        areas = list(PAINEIS) if area == "Diretoria" else [area]
        for p in paineis:
            da_revenda = (
                u["filial"] == "Matriz" or dict((lic, n) for lic, n, _ in REVENDAS)[p["licenca"]] == u["filial"]
            )
            if p["area"] in areas and da_revenda:
                grupos.append({"nomeGrupo": u["login"], "id": p["id"]})
    usuario = pl.DataFrame(usuarios)
    dash_group = pl.DataFrame(grupos)
    # Acessos: quem tem o painel abre ao longo dos dias úteis, mais nas manhãs.
    por_grupo: dict[str, list[int]] = {}
    for g in grupos:
        por_grupo.setdefault(g["nomeGrupo"], []).append(g["id"])
    fim = datetime.combine(b.HOJE, datetime.min.time()).replace(hour=18)
    # Uns poucos param de entrar há algumas semanas (a coluna "dias sem acesso" da Visão Geral).
    parou = {login: fim - timedelta(days=r.randint(8, 50)) for login in por_grupo if r.random() < 0.2}
    log, id_log = [], 1000
    for dia in (fim - timedelta(days=n) for n in range(DIAS_LOG, -1, -1)):
        if dia.weekday() == 6:
            continue
        for login, ids in por_grupo.items():
            if login in parou and dia > parou[login]:
                continue
            if r.random() < (0.25 if dia.weekday() == 5 else 0.75):
                for _ in range(r.randint(1, 6)):
                    quando = dia.replace(hour=0) + timedelta(minutes=int(r.triangular(7 * 60, 18 * 60, 9 * 60)))
                    if quando > fim:
                        continue
                    id_log += 1
                    log.append(
                        {
                            "id": id_log,
                            "login": login,
                            "iddash": r.choice(ids),
                            "dataAcesso": quando.strftime("%d/%m/%Y %H:%M:%S"),
                        }
                    )
    logacesso = pl.DataFrame(log).sort("id")
    for nome, df in {
        "revenda": revenda,
        "dashboard": dashboard.drop("area"),
        "usuario": usuario,
        "dash_group": dash_group,
        "logacesso": logacesso,
    }.items():
        df.write_parquet(PASTA / f"{nome}.parquet", compression="zstd")
        print(f"  bd_acessos/{nome}.parquet: {df.height:,} linhas".replace(",", "."))
