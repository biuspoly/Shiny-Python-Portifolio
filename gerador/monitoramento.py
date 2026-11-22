"""Logs fictícios dos apps no formato que o Monitoramento lê (loguru, com os eventos de
telemetria como JSON depois de "OTEL "), e o histórico por hora dos dias anteriores."""

import json
import random
from datetime import datetime, timedelta

import polars as pl

from gerador import base as b

PASTA = b.RAIZ / "Monitoramento" / "data"
PASTA_LOGS = PASTA / "logs"
DIAS_HISTORICO = 29

# app -> (páginas com as funções que elas medem, fontes de dados lidas, outputs reativos)
APPS = {
    "Comercial": (
        {
            "Diário de Vendas": ["carregar_diario", "tabela_categorias"],
            "Curva ABC": ["curva_abc"],
            "Mapa Comercial": ["mapa_potencial"],
        },
        ["tb_diario_venda.parquet", "tb_curva_abc_atual.parquet", "tb_mapa_pot.parquet", "tb_cob_cid.parquet"],
        ["tabela_dv", "grafico_historico", "mapa_leaflet", "tabela_saiba_mais"],
    ),
    "Logistico": (
        {
            "Frotas": ["carregar_geral_frota", "tabela_consolidada"],
            "PDE": ["carregar_pde"],
            "Devolucoes": ["carregar_geral_dev"],
        },
        ["geral_frota.parquet", "geral_combustivel.parquet", "tb_pde.parquet", "tb_vend_dev_atual.parquet"],
        ["tabela", "cards_classe", "grafico_mensal", "tabela_detalhada"],
    ),
    "Acessos": (
        {"Usuários": ["listar_usuarios"], "Permissões": ["permissoes_do_app"]},
        ["usuarios.parquet", "permissoes.json"],
        ["tabela_usuarios", "tabela_permissoes"],
    ),
    "Financeiro": (
        {"Fluxo Financeiro": ["montar"], "Empréstimos": ["contratos"], "Extratos": ["ler_movimento"]},
        [
            "extratos_fabricas_tabela.parquet",
            "contas_pagar.parquet",
            "emprestimos_revendas.parquet",
            "movimento.parquet",
        ],
        ["tabela", "lista", "grade"],
    ),
    "Fiscal": (
        {"Apuração": ["livros_da_empresa", "itens_do_mes"], "Faturamento": ["base"]},
        ["faturamento.parquet", "livro_itens.parquet", "control_produtos.parquet"],
        ["tabela_cfop", "tabela_itens", "grafico_receita"],
    ),
}
PIPELINES = [
    ("atualiza_diario_venda", 95_000),
    ("atualiza_curva_abc", 140_000),
    ("atualiza_frota", 260_000),
    ("atualiza_devolucao", 75_000),
    ("atualiza_pde", 30_000),
    ("atualiza_financeiro", 420_000),
    ("atualiza_fiscal", 380_000),
    ("atualiza_mapa_comercial", 210_000),
]
# app -> erros possíveis (classe, mensagem, arquivo, função) e avisos de log
ERROS = {
    "Comercial": [
        (
            "ValueError",
            "Sem dados de cobertura para o mês escolhido.",
            "pages/Mapa_Comercial/Dados/dados_mapa_comercial.py",
            "mapa_potencial",
        )
    ],
    "Logistico": [
        ("KeyError", "'VALOR DEVOLUCAO'", "pages/Devolucoes/Dados/dados_devolucao.py", "_calcular_campos_geral_dev")
    ],
    "Acessos": [
        (
            "PermissionError",
            "config/permissoes.json em uso por outra gravação",
            "pages/Permissoes/Dados/dados_permissoes.py",
            "gravar",
        )
    ],
    "Financeiro": [
        (
            "TimeoutError",
            "a consulta ao ERP não respondeu em 120 s",
            "pages/Extrato/Dados/sincronia_extrato.py",
            "consultar",
        )
    ],
    "Fiscal": [("ColumnNotFoundError", "ALIQ_ICMS", "pages/Apuracao/Dados/dados_apuracao.py", "itens_filtrados")],
}
AVISOS = {
    "Comercial": ['Crossfilter: coluna "CANAL" ausente nesta base -- filtro ignorado'],
    "Logistico": ["config/frota_unidade_fixa.json não encontrado -- seguindo com o padrão"],
    "Acessos": ['Usuário sem área cadastrada -- mostrado em "Outros"'],
    "Financeiro": ["Fluxo: leitura do extrato da fábrica sem data -- ignorada no total"],
    "Fiscal": ["Faturamento: endereço da empresa pelo XML -- sem nota de entrada no mês"],
}


def _linha(momento: datetime, nivel: str, onde: str, mensagem: str) -> str:
    return f"{momento:%Y-%m-%d %H:%M:%S}.{momento.microsecond // 1000:03d} | {nivel:<8} | {onde} - {mensagem}"


def _otel(momento: datetime, **span) -> str:
    return _linha(
        momento,
        "INFO",
        "core.telemetria:exportar:48",
        "OTEL "
        + json.dumps({"inicio": momento.isoformat(sep=" ", timespec="milliseconds"), **span}, ensure_ascii=False),
    )


def _log_do_app(nome: str, usuarios: list[dict], r: random.Random, dia: datetime, fim: datetime) -> list[str]:
    paginas, fontes, outputs = APPS[nome]
    linhas = []
    momento = dia.replace(hour=7, minute=r.randint(0, 20))
    while momento < fim:
        momento += timedelta(minutes=r.expovariate(1 / (6 if 8 <= momento.hour <= 17 else 25)))
        if momento >= fim:
            break
        u = r.choice(usuarios)
        sessao = f"{nome[:3].lower()}{r.randint(100000, 999999)}"
        linhas.append(
            _otel(
                momento,
                tipo="sessao",
                nome="session_start",
                sessao=sessao,
                revenda=u["filial"],
                usuario=u["login"],
                status="OK",
            )
        )
        t = momento
        for _ in range(r.randint(2, 9)):
            t += timedelta(seconds=r.randint(5, 240))
            pagina = r.choice(list(paginas))
            for funcao in paginas[pagina]:
                lento = r.random() < 0.05
                duracao = int(r.lognormvariate(5.9, 0.6) * (6 if lento else 1))
                linhas.append(
                    _otel(
                        t,
                        tipo="medir_tempo",
                        pagina=pagina,
                        nome=funcao,
                        duracao_ms=duracao,
                        sessao=sessao,
                        status="OK",
                    )
                )
            fonte = r.choice(fontes)
            linhas.append(
                _otel(
                    t,
                    tipo="dados",
                    nome=r.choice(["dados.parquet", "dados.duckdb"]),
                    fonte=fonte,
                    duracao_ms=int(r.lognormvariate(4.6, 0.7)),
                    sessao=sessao,
                    status="OK",
                )
            )
            saida = r.choice(outputs)
            erro = r.random() < 0.004
            span = {
                "tipo": "shiny",
                "nome": f"output:{saida}",
                "duracao_ms": int(r.lognormvariate(5.2, 0.6)),
                "sessao": sessao,
                "status": "ERROR" if erro else "OK",
            }
            if erro:
                classe, msg, arquivo, funcao = r.choice(ERROS[nome])
                span["erro"] = {
                    "classe": classe,
                    "msg": msg,
                    "stack": (
                        "Traceback (most recent call last):\n"
                        f'  File "{arquivo}", line {r.randint(80, 600)}, in {funcao}\n'
                        f"{classe}: {msg}"
                    ),
                }
                span["codigo"] = f"{arquivo}:{funcao}"
            linhas.append(_otel(t, **span))
            if r.random() < 0.01:
                linhas.append(_linha(t, "WARNING", "core.crossfilter:usar_crossfilter:31", r.choice(AVISOS[nome])))
        t += timedelta(seconds=r.randint(30, 900))
        if t < fim:
            linhas.append(_otel(t, tipo="sessao", nome="session_end", sessao=sessao, status="OK"))
    return sorted(linhas)


def _log_dos_pipelines(r: random.Random, dia: datetime) -> list[str]:
    linhas = []
    momento = dia.replace(hour=1, minute=0)
    for nome, media in PIPELINES:
        duracao = int(media * r.uniform(0.7, 1.4))
        falhou = nome == "atualiza_mapa_comercial" and r.random() < 0.5
        span = {"tipo": "pipeline", "nome": nome, "duracao_ms": duracao, "status": "ERROR" if falhou else "OK"}
        if falhou:
            span["erro"] = {
                "classe": "ConnectionError",
                "msg": "o banco de origem não respondeu",
                "stack": f'Traceback (most recent call last):\n  File "scripts/{nome}.py", line 212, '
                "in main\nConnectionError: o banco de origem não respondeu",
            }
        linhas.append(_otel(momento, **span))
        momento += timedelta(milliseconds=duracao + r.randint(2_000, 20_000))
    return linhas


def _historico(r: random.Random, hoje: datetime) -> pl.DataFrame:
    linhas = []
    for d in range(DIAS_HISTORICO, 0, -1):
        dia = hoje - timedelta(days=d)
        if dia.weekday() == 6:
            continue
        for app in APPS:
            for hora in range(7, 20):
                movimento = (1.0 if 8 <= hora <= 17 else 0.3) * (0.5 if dia.weekday() == 5 else 1.0)
                chamadas = int(r.uniform(20, 90) * movimento) + 1
                media = r.lognormvariate(4.7, 0.25)
                linhas.append(
                    {
                        "app": app,
                        "hora": f"{dia:%Y-%m-%d}T{hora:02d}",
                        "chamadas": chamadas,
                        "soma_ms": int(media * chamadas),
                        "max_ms": int(media * r.uniform(3, 12)),
                        "lentas": int(chamadas * r.uniform(0, 0.03)),
                        "sessoes": int(r.uniform(2, 14) * movimento),
                    }
                )
    return pl.DataFrame(linhas)


def gerar() -> None:
    print("Monitoramento")
    r = b.rng("monitoramento")
    usuarios = b.usuarios().filter(pl.col("ativo")).to_dicts()
    hoje = datetime.combine(b.HOJE, datetime.min.time())
    fim = hoje.replace(hour=18, minute=30)
    for app in [*APPS, "Pipelines"]:
        pasta = PASTA_LOGS / app / "logs"
        pasta.mkdir(parents=True, exist_ok=True)
        for antigo in pasta.glob("*.log"):
            antigo.unlink()
        linhas = _log_dos_pipelines(r, hoje) if app == "Pipelines" else _log_do_app(app, usuarios, r, hoje, fim)
        (pasta / "app.log").write_text("\n".join(linhas) + "\n", encoding="utf-8")
        print(f"  logs/{app}/logs/app.log: {len(linhas):,} linhas".replace(",", "."))
    historico = _historico(r, hoje)
    historico.write_parquet(PASTA / "historico_horas.parquet", compression="zstd")
    print(f"  historico_horas.parquet: {historico.height:,} linhas".replace(",", "."))
