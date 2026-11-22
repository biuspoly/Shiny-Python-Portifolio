from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import polars as pl

from core.config import chave_revenda
from core.config_arquivo import carregar_json
from pages.PPF.Dados import dados_fluxo_fabrica as dff
from pages.PPF.Dados import dados_ppf as dp

DIAS_SEMANA = dff.DIAS_SEMANA

DESCRICAO_DO_CODIGO = {
    157: ("entrada", "Pediu empréstimo"),
    158: ("saida", "Emprestou"),
    159: ("entrada", "Recebeu devolução"),
    160: ("saida", "Devolveu empréstimo"),
}

_NF_NO_TEXTO = re.compile(r"\bNF\b\.?\s*(?:nr\.?)?\s*(\d+)", re.IGNORECASE)

CONSULTA_DANFE = "https://consultadanfe.com/?chave={chave}#"
JANELA_NOTAS_DIAS = 400
_cache_notas: dict = {}
_cache_vencimentos: dict = {}


def _conf() -> dict:
    return (carregar_json("parametros_financeiro") or {}).get("fluxo_consolidado") or {}


def colunas() -> list[str]:
    return list(_conf().get("colunas") or [])


def grupos() -> dict[str, list[str]]:
    return {g: list(m) for g, m in (_conf().get("grupos") or {}).items()}


def _coluna_total() -> str:
    return _conf().get("coluna_total") or "TOTAL"


def _coluna_a_parte() -> str | None:
    return _conf().get("coluna_a_parte")


def _reais(valor) -> str:
    inteiro = f"{abs(float(valor)):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"{'-' if float(valor) < 0 else ''}R$ {inteiro}"


def _classe(valor: float) -> str:
    if valor > 0:
        return "valor-positivo"
    if valor < 0:
        return "valor-negativo"
    return "valor-zero"


def _celula(valor: float, formatado: str, is_grupo: bool, classe: str = "", **extra) -> dict:
    return {"valor": valor, "formatado": formatado, "is_grupo": is_grupo, "classe_valor": classe, **extra}


def extrair_nf(texto) -> str:
    if not texto:
        return "-"
    achado = _NF_NO_TEXTO.search(str(texto))
    return (achado.group(1).lstrip("0") or "-") if achado else "-"


def _por_revenda(base: pl.DataFrame, nomes: list[str]) -> pl.DataFrame:
    if base.is_empty() or "REVENDA" not in base.columns:
        return base
    chaves = {chave_revenda(n) for n in nomes}
    reais = [r for r in base["REVENDA"].unique().to_list() if r and chave_revenda(r) in chaves]
    return base.filter(pl.col("REVENDA").is_in(reais))


def _nome_da_coluna(revenda: str, nomes: list[str]) -> str | None:
    alvo = chave_revenda(revenda or "")
    return next((n for n in nomes if chave_revenda(n) == alvo), None)


def _individuais() -> list[str]:
    g = grupos()
    return [c for c in colunas() if c not in g and c != _coluna_total()]


def datas_de_hoje_no_nome(hoje: date) -> list[str]:
    return [
        hoje.strftime(f) for f in ("%d%m%Y", "%d-%m-%Y", "%d_%m_%Y", "%d.%m.%Y", "%d.%m.%y", "%d-%m-%y", "%d_%m_%y")
    ]


def do_dia(base: pl.DataFrame, hoje: date | None) -> pl.DataFrame:
    if hoje is None or base.is_empty():
        return base
    pela_data = (
        pl.col("data_hora").cast(pl.Datetime, strict=False).dt.date() == hoje
        if "data_hora" in base.columns
        else pl.lit(False)
    )
    if "arquivo" not in base.columns:
        return base.filter(pela_data)
    nome = pl.col("arquivo").cast(pl.Utf8)
    pelo_nome = pl.any_horizontal([nome.str.contains(d, literal=True) for d in datas_de_hoje_no_nome(hoje)])
    return base.filter(pl.when(nome.is_null()).then(pela_data).otherwise(pelo_nome.fill_null(False)))


def credito_por_revenda(hoje: date | None = None) -> dict[str, dict]:
    nomes = _individuais()
    base = dp.ultima_leitura_por_fabrica(do_dia(_por_revenda(dp.extratos_fabricas_totais(), nomes), hoje))
    fora = {}
    if base.is_empty():
        return fora
    for r in (
        base.group_by("REVENDA")
        .agg(
            pl.col("limite_credito").cast(pl.Float64, strict=False).max().alias("limite"),
            pl.col("saldo_debitos_diversos").cast(pl.Float64, strict=False).sum().alias("credito"),
        )
        .iter_rows(named=True)
    ):
        coluna = _nome_da_coluna(r["REVENDA"], nomes)
        if coluna:
            fora[coluna] = {"limite_credito": float(r["limite"] or 0), "credito_mare": float(r["credito"] or 0)}
    return fora


def _partidas(hoje: date | None = None) -> pl.DataFrame:
    if hoje is None:
        return _por_revenda(dp.extratos_fabricas_tabela(), _individuais())
    base = do_dia(_por_revenda(dp.extratos_fabricas_leituras(), _individuais()), hoje)
    if base.is_empty() or not {"REVENDA", "fabrica", "data_hora"} <= set(base.columns):
        return base
    quando = pl.col("data_hora").cast(pl.Datetime, strict=False)
    return base.filter(quando == quando.max().over(["REVENDA", "fabrica"]))


def _titulos_da_fabrica_a_parte(hoje: date) -> list[dict]:
    """No original, a coluna "à parte" (uma revenda cujo débito com a fábrica vem dos títulos
    em aberto, não do extrato). O portfólio não tem essa revenda."""
    return []


def _com_nf_dos_titulos(titulos: list[dict], hoje: date) -> list[dict]:
    base = dp.filtrar_por_revenda(dp.contas_pagar(), _coluna_a_parte())
    notas = {}
    if not base.is_empty():
        for r in base.iter_rows(named=True):
            doc = str(r.get("PGMOVMOV_NDUPL") or "")
            if re.fullmatch(r"NFE\d+", doc):
                notas[(r.get("DATA"), float(r.get("PGMOVMOV_VALOR") or 0))] = doc[3:-2].lstrip("0") or "-"
    return [{**t, "nf": notas.get((t["data"], t["valor"]), "-")} for t in titulos]


def debitos(hoje: date, notas_xml: dict | None = None) -> tuple[dict, dict, list[dict]]:
    nomes = _individuais()
    base = _partidas(hoje)
    por_revenda: dict[str, float] = {}
    total: dict[str, float] = {n: 0.0 for n in nomes}
    por_data: dict[date, dict] = {}
    if not base.is_empty():
        montante = pl.col("montante_mi").cast(pl.Float64, strict=False)
        for r in (
            base.filter(pl.col("cpgt").cast(pl.Utf8).str.strip_chars().fill_null("") != "")
            .group_by("REVENDA")
            .agg(montante.sum())
            .iter_rows()
        ):
            coluna = _nome_da_coluna(r[0], nomes)
            if coluna:
                por_revenda[coluna] = float(r[1] or 0)
        venc = pl.col("vencimento_liquido").cast(pl.Date, strict=False)
        com_data = base.filter(venc.is_not_null() & (montante > 0)).with_columns(venc.alias("_v"), montante.alias("_m"))
        for r in com_data.sort("_v").iter_rows(named=True):
            coluna = _nome_da_coluna(r["REVENDA"], nomes)
            if not coluna:
                continue
            total[coluna] = total.get(coluna, 0.0) + abs(r["_m"])
            dia = por_data.setdefault(r["_v"], {"valores": {}, "notas": {}})
            dia["valores"][coluna] = dia["valores"].get(coluna, 0.0) + r["_m"]
            dia["notas"].setdefault(coluna, []).append((extrair_nf(r.get("texto")), r["_m"]))

    a_parte = _coluna_a_parte()
    titulos = _com_nf_dos_titulos(_titulos_da_fabrica_a_parte(hoje), hoje)
    if a_parte and titulos:
        soma = sum(t["valor"] for t in titulos)
        por_revenda[a_parte] = por_revenda.get(a_parte, 0.0) + soma
        total[a_parte] = total.get(a_parte, 0.0) + soma
        for t in titulos:
            dia = por_data.setdefault(t["data"], {"valores": {}, "notas": {}})
            dia["valores"][a_parte] = dia["valores"].get(a_parte, 0.0) + t["valor"]
            dia["notas"].setdefault(a_parte, []).append((t["nf"], t["valor"]))

    detalhados = [
        {"data": d, "label": f"{d:%d/%m/%Y} | {DIAS_SEMANA[d.weekday()]}", **v} for d, v in sorted(por_data.items())
    ]
    return por_revenda, total, detalhados


def _vence_em_breve(dia: date, hoje: date) -> bool:
    limite = hoje + timedelta(days=6)
    efetiva = (
        dia + timedelta(days=2) if dia.weekday() == 5 else (dia + timedelta(days=1) if dia.weekday() == 6 else dia)
    )
    return hoje <= dia <= limite and efetiva <= limite


def relacoes_de_emprestimo() -> tuple[dict, dict]:
    ledger = dff.emprestimos_revendas()
    nomes = _individuais()
    relacoes: dict[str, dict[str, dict]] = {}
    movimentos: dict[tuple[str, str], list[dict]] = {}
    if not ledger.is_empty():
        for r in ledger.sort("data_lancamento", nulls_last=True).iter_rows(named=True):
            revenda = _nome_da_coluna(r.get("REVENDA") or "", nomes) or (r.get("REVENDA") or "")
            cliente = r.get("revenda_cliente") or ""
            codigo = r.get("codigo_hp")
            if codigo not in DESCRICAO_DO_CODIGO:
                continue
            tipo, descricao = DESCRICAO_DO_CODIGO[codigo]
            valor = abs(float(r.get("valor") or 0))
            item = relacoes.setdefault(revenda, {}).setdefault(cliente, {"entradas": 0.0, "saidas": 0.0, "saldo": 0.0})
            item["entradas" if tipo == "entrada" else "saidas"] += valor
            movimentos.setdefault((revenda, cliente), []).append(
                {
                    "tipo": tipo,
                    "descricao": descricao,
                    "data": r.get("data_lancamento"),
                    "valor": valor,
                }
            )
    iniciais = (carregar_json("parametros_financeiro") or {}).get("saldos_iniciais_emprestimos") or {}
    for revenda, clientes in iniciais.items():
        if revenda.startswith("_"):
            continue
        for cliente in clientes or {}:
            relacoes.setdefault(revenda, {}).setdefault(cliente, {"entradas": 0.0, "saidas": 0.0, "saldo": 0.0})
    for revenda, clientes in relacoes.items():
        for cliente, item in clientes.items():
            inicial = float((iniciais.get(revenda) or {}).get(cliente) or 0)
            item["inicial"] = inicial
            item["saldo"] = max(0.0, inicial + item["entradas"] - item["saidas"])
    return relacoes, movimentos


def saldos_da_revenda(revenda: str, relacoes: dict) -> list[dict]:
    nomes = _individuais()
    coluna = _nome_da_coluna(revenda, nomes) or revenda
    proprias = relacoes.get(coluna, {})
    linhas: dict[str, dict] = {}
    for cliente, item in proprias.items():
        linhas.setdefault(cliente, {"debito": 0.0, "credito": 0.0})["debito"] += item["saldo"]
    for outra in nomes:
        devido = relacoes.get(outra, {}).get(coluna, {}).get("saldo", 0.0)
        if devido:
            nome = dff._nome_no_livro(outra, list(proprias))
            linhas.setdefault(nome, {"debito": 0.0, "credito": 0.0})["credito"] += devido
    return [
        {
            "revenda": revenda,
            "cliente": cliente,
            "debito": v["debito"],
            "credito": v["credito"],
            "saldo": round(v["debito"] - v["credito"], 2),
        }
        for cliente, v in sorted(linhas.items())
        if v["debito"] or v["credito"]
    ]


def notas_do_fiscal(hoje: date) -> dict[tuple[str, str], dict]:
    """No original, casa cada NF do extrato da fábrica com o XML recebido (link para o DANFE).
    O portfólio não tem acervo de XML."""
    return {}


def pdf_da_nota(chave: str):
    return None


def _item_da_nota(nf, valor: float, coluna: str, notas_xml: dict) -> dict:
    nota = notas_xml.get((coluna, str(nf or "").lstrip("0"))) if nf and nf != "-" else None
    return {
        "nf": nf,
        "valor": _reais(valor),
        "consultar": CONSULTA_DANFE.format(chave=nota["chave"]) if nota else "",
        "pdf": nota["chave"] if nota and nota.get("arquivo") else "",
    }


def dia_de_referencia() -> date:
    """O "hoje" da tela. No portfólio os dados são refeitos uma vez por semana: vale o dia da
    última leitura do extrato da fábrica, senão a tela ficaria zerada nos outros dias."""
    base = dp.extratos_fabricas_totais()
    if base.is_empty() or "data_hora" not in base.columns:
        return date.today()
    ultima = base["data_hora"].cast(pl.Datetime, strict=False).max()
    return ultima.date() if ultima else date.today()


def montar(hoje: date | None = None) -> dict:
    hoje = hoje or dia_de_referencia()
    cols = colunas()
    g = grupos()
    total_col = _coluna_total()
    a_parte = _coluna_a_parte()
    membros = {m for ms in g.values() for m in ms}

    credito = credito_por_revenda(hoje)
    try:
        notas_xml = notas_do_fiscal(hoje)
    except Exception:
        notas_xml = {}
    debitos_rev, total_debitos_rev, detalhados = debitos(hoje, notas_xml)
    relacoes, movimentos = relacoes_de_emprestimo()
    iniciais = (carregar_json("parametros_financeiro") or {}).get("saldos_iniciais_emprestimos") or {}

    credores = set()
    for clientes in relacoes.values():
        credores |= set(clientes)
    for revenda, clientes in iniciais.items():
        if not revenda.startswith("_"):
            credores |= {c for c, v in (clientes or {}).items() if float(v or 0) > 0}

    def saldo(rev, cli):
        return relacoes.get(rev, {}).get(cli, {}).get("saldo", 0.0)

    individuais = [c for c in cols if c not in g and c != total_col]
    recebido = {cr: sum(saldo(rev, cr) for rev in individuais) for cr in credores}
    deve_por_coluna = {rev: sum(x["saldo"] for x in relacoes.get(rev, {}).values()) for rev in individuais}
    for grupo, ms in g.items():
        deve_por_coluna[grupo] = sum(deve_por_coluna.get(m, 0.0) for m in ms)

    linhas = {
        k: {"label": rot, "tipo": k, "valores": {}}
        for k, rot in (
            ("limite", "Limite Crédito MAR"),
            ("credito", "Crédito MAR"),
            ("debitos", "Débitos MAR"),
            ("emprestimo_debito", "Débito Empréstimos"),
            ("emprestimo_credito", "Crédito Empréstimos"),
            ("emprestimo_saldo", "Saldo Débito"),
        )
    }
    esp = [{"label": "", "tipo": "espaco", "valores": {}} for _ in range(3)]

    tot = {"limite": 0.0, "credito": 0.0, "debitos": 0.0, "emp_credito": 0.0}
    tot_emp_debito = sum(
        deve_por_coluna.get(c, 0.0) for c in cols if c not in (total_col, a_parte) and (c in g or c not in membros)
    )

    for c in cols:
        if c == total_col:
            continue
        for e in esp:
            e["valores"][c] = _celula(0.0, "", c in g)
        if c in g:
            limite = max((credito.get(m, {}).get("limite_credito", 0.0) for m in g[c]), default=0.0)
            cred = sum(credito.get(m, {}).get("credito_mare", 0.0) for m in g[c])
            debs = sum(debitos_rev.get(m, 0.0) for m in g[c])
            emp_d = deve_por_coluna.get(c, 0.0)
            emp_c = sum(recebido.get(m, 0.0) for m in g[c])
            linhas["limite"]["valores"][c] = _celula(
                limite, _reais(limite) if limite else "", True, _classe(limite) if limite else ""
            )
            linhas["credito"]["valores"][c] = _celula(cred, _reais(cred), False, _classe(cred))
            linhas["debitos"]["valores"][c] = _celula(debs, _reais(debs), True, _classe(debs))
            tot["limite"] += limite
            tot["credito"] += cred
            tot["debitos"] += debs
            tot["emp_credito"] += emp_c
        elif c == a_parte:
            debs = total_debitos_rev.get(c, 0.0)
            emp_d = deve_por_coluna.get(c, 0.0)
            emp_c = recebido.get(c, 0.0)
            linhas["limite"]["valores"][c] = _celula(0.0, _reais(0.0), False)
            linhas["credito"]["valores"][c] = _celula(0.0, _reais(0.0), False)
            linhas["debitos"]["valores"][c] = _celula(debs, _reais(debs), False, _classe(debs))
        else:
            dados = credito.get(c)
            limite = dados["limite_credito"] if dados else 0.0
            cred = dados["credito_mare"] if dados else 0.0
            debs = total_debitos_rev.get(c, 0.0)
            emp_d = deve_por_coluna.get(c, 0.0)
            emp_c = recebido.get(c, 0.0)
            linhas["limite"]["valores"][c] = (
                _celula(0.0, "", False)
                if c in membros
                else _celula(limite, _reais(limite) if dados else "-", False, _classe(limite) if dados else "")
            )
            linhas["credito"]["valores"][c] = _celula(
                cred, _reais(cred) if dados else "-", False, _classe(cred) if dados else ""
            )
            linhas["debitos"]["valores"][c] = _celula(debs, _reais(debs), False, _classe(debs))
            if c not in membros:
                tot["limite"] += limite
                tot["credito"] += cred
                tot["debitos"] += debs
                tot["emp_credito"] += emp_c
        saldo_emp = emp_d - emp_c
        linhas["emprestimo_debito"]["valores"][c] = _celula(emp_d, _reais(emp_d), c in g, _classe(emp_d))
        linhas["emprestimo_credito"]["valores"][c] = _celula(emp_c, _reais(emp_c), c in g, _classe(emp_c))
        linhas["emprestimo_saldo"]["valores"][c] = _celula(saldo_emp, _reais(saldo_emp), c in g, _classe(saldo_emp))

    tot_emp_saldo = tot_emp_debito - tot["emp_credito"]
    for chave, valor in (
        ("limite", tot["limite"]),
        ("credito", tot["credito"]),
        ("debitos", tot["debitos"]),
        ("emprestimo_debito", tot_emp_debito),
        ("emprestimo_credito", tot["emp_credito"]),
        ("emprestimo_saldo", tot_emp_saldo),
    ):
        linhas[chave]["valores"][total_col] = _celula(valor, _reais(valor), True, _classe(valor))
    for e in esp:
        e["valores"][total_col] = _celula(0.0, "", True)

    subtotal = {"label": "Subtotal 7 dias", "tipo": "subtotal_debitos_mar", "valores": {}}
    em_breve = [d for d in detalhados if _vence_em_breve(d["data"], hoje)]
    soma_sub = 0.0
    for c in cols:
        if c == total_col:
            continue
        if c == a_parte:
            subtotal["valores"][c] = _celula(0.0, "", False)
            continue
        ms = g.get(c, [c])
        valor = sum(d["valores"].get(m, 0.0) for d in em_breve for m in ms)
        subtotal["valores"][c] = _celula(
            valor, _reais(valor) if valor > 0 else "-", c in g, _classe(valor) if valor > 0 else ""
        )
        if c in g or c not in membros:
            soma_sub += valor
    subtotal["valores"][total_col] = _celula(
        soma_sub, _reais(soma_sub) if soma_sub > 0 else "-", True, _classe(soma_sub) if soma_sub > 0 else ""
    )

    resultado = [linhas["limite"], linhas["credito"], esp[0], linhas["debitos"], subtotal]

    for d in detalhados:
        linha = {
            "label": d["label"],
            "tipo": "debito_detalhe",
            "valores": {},
            "vence_em_breve": _vence_em_breve(d["data"], hoje),
        }
        soma = 0.0
        for c in cols:
            if c == total_col:
                continue
            if c in g:
                valor = sum(d["valores"].get(m, 0.0) for m in g[c])
                linha["valores"][c] = _celula(
                    valor, _reais(valor) if valor > 0 else "-", True, _classe(valor) if valor > 0 else ""
                )
                soma += valor
                continue
            valor = d["valores"].get(c, 0.0)
            notas = d["notas"].get(c) or []
            tooltip = (
                {
                    "kind": "notas_fiscais",
                    "titulo": f"{c} | {d['data']:%d/%m/%Y}",
                    "itens": [_item_da_nota(nf, v, c, notas_xml) for nf, v in notas],
                }
                if notas
                else None
            )
            classe = _classe(valor) if valor > 0 else ""
            linha["valores"][c] = _celula(valor, _reais(valor) if valor > 0 else "-", False, classe, tooltip=tooltip)
            if c not in membros and c != a_parte:
                soma += valor
        linha["valores"][total_col] = _celula(soma, _reais(soma), True, _classe(soma))
        resultado.append(linha)

    resultado += [esp[1], linhas["emprestimo_debito"], linhas["emprestimo_credito"], linhas["emprestimo_saldo"], esp[2]]

    for cliente in sorted(credores):
        linha = {"label": f"Deve a {cliente}", "tipo": "debito_cliente", "valores": {}}
        soma = 0.0
        for c in cols:
            if c == total_col:
                continue
            if c in g:
                valor = sum(saldo(m, cliente) for m in g[c])
                linha["valores"][c] = _celula(
                    max(valor, 0.0), _reais(valor) if valor > 0 else "-", True, _classe(valor) if valor > 0 else ""
                )
                if valor > 0:
                    soma += valor
                continue
            rel = relacoes.get(c, {}).get(cliente, {})
            valor = rel.get("saldo", 0.0)
            movs = sorted(
                movimentos.get((c, cliente), []),
                key=lambda m: (m["data"] is not None, m["data"] or date.min),
                reverse=True,
            )
            linha["valores"][c] = _celula(
                max(valor, 0.0),
                _reais(valor) if valor > 0 else "-",
                False,
                _classe(valor) if valor > 0 else "",
                tooltip={
                    "saldo_inicial": _reais(rel.get("inicial", 0.0)),
                    "entradas": _reais(rel.get("entradas", 0.0)),
                    "saidas": _reais(rel.get("saidas", 0.0)),
                    "saldo_final": _reais(valor),
                    "movimentos": [
                        {
                            "tipo": m["tipo"],
                            "descricao": m["descricao"],
                            "data": m["data"].strftime("%d/%m/%Y") if m["data"] else "",
                            "valor": _reais(m["valor"]),
                        }
                        for m in movs
                    ],
                }
                if rel
                else None,
            )
            if c not in membros and c != a_parte and valor > 0:
                soma += valor
        linha["valores"][total_col] = _celula(soma, _reais(soma), True, _classe(soma))
        resultado.append(linha)

    total_clientes = {"label": "TOTAL DÉBITOS CLIENTES", "tipo": "total_debitos_clientes", "valores": {}}
    soma_geral = 0.0
    for c in cols:
        if c == total_col:
            continue
        if c == a_parte:
            total_clientes["valores"][c] = _celula(0.0, "", False)
            continue
        if c in g:
            valor = sum(deve_por_coluna.get(m, 0.0) for m in g[c])
            soma_geral += valor
        else:
            valor = deve_por_coluna.get(c, 0.0)
            if c not in membros:
                soma_geral += valor
        total_clientes["valores"][c] = _celula(valor, _reais(valor), c in g, _classe(valor))
    total_clientes["valores"][total_col] = _celula(soma_geral, _reais(soma_geral), True, _classe(soma_geral))
    resultado.append(total_clientes)
    return {"colunas": cols, "linhas": resultado}


def extrato_hoje(hoje: date | None = None) -> dict[str, str]:
    hoje = hoje or dia_de_referencia()
    nomes = _individuais()
    base = _por_revenda(dp.extratos_fabricas_totais(), nomes)
    if base.is_empty() or "data_hora" not in base.columns:
        return {}
    quando = pl.col("data_hora").cast(pl.Datetime, strict=False)
    base = base.filter(quando.dt.date() == hoje)
    fora = {}
    for r in base.group_by("REVENDA").agg(quando.max().alias("q")).iter_rows(named=True):
        coluna = _nome_da_coluna(r["REVENDA"], nomes)
        if coluna and r["q"]:
            fora[coluna] = r["q"].strftime("%d/%m/%Y %H:%M")
    return fora


def extratos_sem_data() -> dict[str, list[str]]:
    nomes = _individuais()
    base = _por_revenda(dp.extratos_fabricas_totais(), nomes)
    if base.is_empty() or "data" not in base.columns:
        return {}
    base = base.filter(pl.col("data").cast(pl.Date, strict=False) == date(1900, 1, 1))
    fora: dict[str, list[str]] = {}
    for r in base.sort([c for c in ("REVENDA", "codigo_empresa") if c in base.columns]).iter_rows(named=True):
        coluna = _nome_da_coluna(r["REVENDA"], nomes)
        if coluna:
            fora.setdefault(coluna, []).append(f"{r.get('codigo_empresa')} → {r.get('fabrica')}")
    return fora


def divergencias_de_boletos() -> dict[str, list[dict]]:
    nomes = _individuais()
    tot = dp.ultima_leitura_por_fabrica(_por_revenda(dp.extratos_fabricas_totais(), nomes))
    tab = _por_revenda(dp.extratos_fabricas_leituras(), nomes)
    if tot.is_empty() or tab.is_empty() or not {"cpgt", "montante_mi", "data_hora"} <= set(tab.columns):
        return {}
    quando = pl.col("data_hora").cast(pl.Datetime, strict=False)
    chave = ["REVENDA", "fabrica", "_dia"]
    somas = (
        tab.with_columns(quando.alias("_quando"), quando.dt.date().alias("_dia"))
        .filter(pl.col("_quando") == pl.col("_quando").max().over(chave))
        .group_by(chave)
        .agg(
            pl.col("montante_mi")
            .cast(pl.Float64, strict=False)
            .filter(pl.col("cpgt").cast(pl.Utf8).str.strip_chars().fill_null("") != "")
            .sum()
            .alias("_soma")
        )
    )
    pares = tot.with_columns(quando.dt.date().alias("_dia")).join(somas, on=chave, how="inner")
    fora: dict[str, list[dict]] = {}
    for r in pares.iter_rows(named=True):
        saldo = float(r.get("saldo_boletos") or 0)
        soma = float(r["_soma"] or 0)
        if abs(saldo - soma) > 0.01:
            coluna = _nome_da_coluna(r["REVENDA"], nomes)
            if coluna:
                fora.setdefault(coluna, []).append(
                    {
                        "codigo_empresa": r.get("codigo_empresa"),
                        "fabrica": r.get("fabrica"),
                        "saldo_boletos_fmt": _reais(saldo),
                        "soma_tabela_fmt": _reais(soma),
                        "diferenca_fmt": _reais(round(saldo - soma, 2)),
                    }
                )
    return fora


def retratos() -> pl.DataFrame:
    return dp._carregar("fluxo_mare_snapshot")


def retrato(hoje: date | None = None) -> dict:
    tabela = montar(hoje)
    marcas = marcacoes()
    for linha in tabela.get("linhas") or []:
        for coluna, dado in (linha.get("valores") or {}).items():
            marca = marcas.get(f"{linha.get('label')}|{coluna}") or {}
            dado["is_marcada"] = bool(marca.get("amarela", dado.get("is_marcada", False)))
            dado["is_marcada_laranja"] = bool(marca.get("laranja", dado.get("is_marcada_laranja", False)))
    return {"revendas": ["TODAS"], "tabela_credito_consolidada": tabela}


def marcacoes() -> dict[str, dict]:
    from core import manual_arquivo

    fora: dict[str, dict] = {}
    base = dp._carregar("celulas_marcadas_mare")
    if not base.is_empty():
        for r in base.iter_rows(named=True):
            fora[f"{r.get('linha_label')}|{r.get('coluna_nome')}"] = {
                "amarela": bool(r.get("marcada")),
                "laranja": bool(r.get("marcada_laranja")),
            }
    for chave, estado in manual_arquivo.celulas_marcadas_mare().items():
        fora[chave] = estado
    return fora


def agora() -> datetime:
    return datetime.now()
