from __future__ import annotations

from datetime import date, timedelta

import polars as pl

from core import revendas as cadastro_revendas
from core.config import chave_revenda
from core.config_arquivo import carregar_json

from . import dados_ppf as dp

DIAS_SEMANA = (
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
)

JANELA_VENCIMENTO_DIAS = 7


def _parametros() -> dict:
    return carregar_json("parametros_financeiro") or {}


def _chaves(nomes) -> set[str]:
    return {chave_revenda(n) for n in nomes or ()}


def emprestimos_revendas() -> pl.DataFrame:
    return dp._carregar("emprestimos_revendas")


def nomes_oficiais(revenda_url: str | None) -> list[str]:
    alvos = dp.revendas_da_url(revenda_url) or []
    nomes = []
    for alvo in alvos:
        oficial = cadastro_revendas.nome_oficial(alvo)
        if oficial and oficial not in nomes:
            nomes.append(oficial)
    return nomes


def _sem_expediente_sabado() -> set[str]:
    return _chaves(_parametros().get("revendas_sem_expediente_sabado"))


def data_pagamento_efetiva(dia: date, revenda: str | None) -> date:
    if dia.weekday() == 6:
        return dia + timedelta(days=1)
    if dia.weekday() == 5 and chave_revenda(revenda or "") in _sem_expediente_sabado():
        return dia + timedelta(days=2)
    return dia


def vence_em_breve(dia: date | None, hoje: date, revenda: str | None) -> bool:
    if dia is None:
        return False
    limite = hoje + timedelta(days=JANELA_VENCIMENTO_DIAS - 1)
    return hoje <= dia <= limite and data_pagamento_efetiva(dia, revenda) <= limite


def _dia(data: date, valor: float, hoje: date, revenda: str | None) -> dict:
    return {
        "data": data,
        "dia_semana": DIAS_SEMANA[data.weekday()],
        "valor": float(valor),
        "hoje": data == hoje,
        "vence_em_breve": vence_em_breve(data, hoje, revenda),
    }


def semanas(dias: list[dict]) -> list[dict]:
    grupos: dict[date, dict] = {}
    for registro in dias:
        data = registro["data"]
        if data.weekday() in (5, 6):
            data = data + timedelta(days=7 - data.weekday())
        inicio = data - timedelta(days=data.weekday())
        semana = grupos.setdefault(
            inicio,
            {
                "inicio": inicio,
                "fim": inicio + timedelta(days=4),
                "pagamentos": [],
                "total": 0.0,
            },
        )
        semana["pagamentos"].append(registro)
        semana["total"] += registro["valor"]
    return [grupos[k] for k in sorted(grupos)]


def cronograma_do_extrato(revenda_url: str | None, hoje: date) -> tuple[list[dict], float]:
    base = dp.filtrar_por_revenda(dp.extratos_fabricas_tabela(), revenda_url)
    if base.is_empty() or "montante_mi" not in base.columns:
        return [], 0.0
    montante = pl.col("montante_mi").cast(pl.Float64, strict=False)
    vencimento = pl.col("vencimento_liquido").cast(pl.Date, strict=False)
    total_debitos = (
        float(
            base.filter(pl.col("cpgt").cast(pl.Utf8).str.strip_chars().fill_null("") != "")
            .select(montante.sum())
            .item()
            or 0.0
        )
        if "cpgt" in base.columns
        else 0.0
    )
    por_dia = (
        base.filter(vencimento.is_not_null() & (montante > 0))
        .group_by(vencimento.alias("data"))
        .agg(montante.sum().alias("valor"), pl.col("REVENDA").first().alias("revenda"))
        .sort("data")
    )
    dias = [_dia(r["data"], r["valor"], hoje, r["revenda"]) for r in por_dia.iter_rows(named=True)]
    return dias, total_debitos


def cronograma_dos_titulos(revenda_url: str | None, cnpjs: list[str], hoje: date) -> list[dict]:
    base = dp.filtrar_por_revenda(dp.contas_pagar(), revenda_url)
    if base.is_empty() or not cnpjs:
        return []
    digitos = {"".join(ch for ch in str(c) if ch.isdigit()) for c in cnpjs}
    base = base.filter(
        pl.col("PGMOVMOV_CGC").cast(pl.Utf8).str.replace_all(r"\D", "").is_in(list(digitos))
        & pl.col("DATA").is_not_null()
    )
    if "CNPJ_REV" in base.columns:
        base = base.filter(pl.col("CNPJ_REV").is_not_null() & (pl.col("CNPJ_REV").cast(pl.Utf8) != ""))
    if "no_erp" in base.columns:
        base = base.filter(pl.col("no_erp").cast(pl.Boolean, strict=False).fill_null(True))
    base = base.sort("DATA")
    return [_dia(r["DATA"], r["PGMOVMOV_VALOR"] or 0.0, hoje, r["REVENDA"]) for r in base.iter_rows(named=True)]


def indicadores(revenda_url: str | None) -> tuple[float, float]:
    base = dp.ultima_leitura_por_fabrica(dp.filtrar_por_revenda(dp.extratos_fabricas_totais(), revenda_url))
    if base.is_empty():
        return 0.0, 0.0
    por_revenda = base.group_by("REVENDA").agg(
        pl.col("limite_credito").cast(pl.Float64, strict=False).max().alias("limite"),
        pl.col("saldo_debitos_diversos").cast(pl.Float64, strict=False).sum().alias("credito"),
    )
    return (
        float(por_revenda["limite"].fill_null(0).sum()),
        float(por_revenda["credito"].fill_null(0).sum()),
    )


def ledger(revenda_url: str | None) -> pl.DataFrame:
    base = dp.filtrar_por_revenda(emprestimos_revendas(), revenda_url)
    if base.is_empty():
        return base
    return base.sort(
        ["data_lancamento", "REVENDA", "revenda_cliente"],
        descending=[True, False, False],
        nulls_last=True,
    )


def _codigos() -> tuple[set[int], set[int]]:
    conf = _parametros().get("codigos_ledger_emprestimo") or {}
    return set(conf.get("entrada") or ()), set(conf.get("saida") or ())


def _nome_no_livro(outra: str, clientes) -> str:
    alvo = chave_revenda(outra)
    iguais = [c for c in clientes if chave_revenda(c) == alvo]
    if iguais:
        return iguais[0]
    curtos = [c for c in clientes if chave_revenda(c) and alvo.startswith(chave_revenda(c) + " ")]
    return curtos[0] if len(curtos) == 1 else outra


def _saldos_iniciais(revenda: str, clientes=()) -> dict[str, float]:
    todos = _parametros().get("saldos_iniciais_emprestimos") or {}
    alvo = chave_revenda(revenda)
    fora: dict[str, float] = {}
    for nome, saldos in todos.items():
        if nome.startswith("_"):
            continue
        for cliente, valor in (saldos or {}).items():
            valor = float(valor or 0)
            if chave_revenda(nome) == alvo:
                fora[cliente] = fora.get(cliente, 0.0) + valor
            elif valor and chave_revenda(cliente) == alvo:
                outra = _nome_no_livro(nome, clientes)
                fora[outra] = fora.get(outra, 0.0) - valor
    return fora


def saldos_por_cliente(base: pl.DataFrame, revenda: str) -> dict[str, dict]:
    entrada, saida = _codigos()
    saldos: dict[str, dict] = {}
    alvo = chave_revenda(revenda)
    if not base.is_empty():
        for linha in base.iter_rows(named=True):
            if chave_revenda(linha.get("REVENDA") or "") != alvo:
                continue
            cliente = linha.get("revenda_cliente") or ""
            item = saldos.setdefault(cliente, {"credito": 0.0, "debito": 0.0, "saldo": 0.0})
            valor = abs(float(linha.get("valor") or 0))
            if linha.get("codigo_hp") in entrada:
                item["credito"] += valor
            elif linha.get("codigo_hp") in saida:
                item["debito"] += valor

    iniciais = _saldos_iniciais(revenda, list(saldos))
    for cliente, inicial in iniciais.items():
        if inicial and cliente not in saldos:
            saldos[cliente] = {"credito": 0.0, "debito": 0.0, "saldo": 0.0}
    for cliente, item in saldos.items():
        inicial = iniciais.get(cliente, 0.0)
        if inicial >= 0:
            item["credito"] += inicial
        else:
            item["debito"] += abs(inicial)
        item["saldo"] = round(item["credito"] - item["debito"], 2)
    return saldos


def _dono_do_livro(nome: str, donos) -> str | None:
    alvo = chave_revenda(nome)
    if not alvo:
        return None
    iguais = [d for d in donos if chave_revenda(d) == alvo]
    if iguais:
        return iguais[0]
    longos = [d for d in donos if chave_revenda(d).startswith(alvo + " ")]
    return longos[0] if len(longos) == 1 else None


def _ultimo_lancamento(livro: pl.DataFrame, cliente: str) -> date | None:
    return livro.filter(pl.col("revenda_cliente") == cliente)["data_lancamento"].max()


def conferencia_dos_livros(linhas: list[dict]) -> dict[tuple[str, str], dict]:
    todas = emprestimos_revendas()
    if todas.is_empty() or not linhas:
        return {}
    donos = todas["REVENDA"].drop_nulls().unique().to_list()
    livros: dict[str, pl.DataFrame] = {}
    saldos: dict[str, dict] = {}

    def _livro(dono: str) -> pl.DataFrame:
        if dono not in livros:
            livros[dono] = todas.filter(pl.col("REVENDA") == dono)
        return livros[dono]

    def _saldos(dono: str) -> dict:
        if dono not in saldos:
            saldos[dono] = saldos_por_cliente(_livro(dono), dono)
        return saldos[dono]

    avisos = {}
    for x in linhas:
        outra = _dono_do_livro(x["cliente"], donos)
        aqui = _dono_do_livro(x["revenda"], donos)
        if not outra or not aqui or outra == aqui:
            continue
        nome_aqui = _nome_no_livro(outra, list(_saldos(aqui)))
        nome_la = _nome_no_livro(aqui, list(_saldos(outra)))
        saldo_aqui = _saldos(aqui)[nome_aqui]["saldo"] if nome_aqui in _saldos(aqui) else 0.0
        saldo_la = -_saldos(outra)[nome_la]["saldo"] if nome_la in _saldos(outra) else 0.0
        diferenca = round(abs(saldo_aqui - saldo_la), 2)
        if diferenca < 0.01:
            continue
        avisos[(x["revenda"], x["cliente"])] = {
            "aqui": aqui,
            "outra": outra,
            "saldo_aqui": saldo_aqui,
            "saldo_la": saldo_la,
            "diferenca": diferenca,
            "ultimo_aqui": _ultimo_lancamento(_livro(aqui), nome_aqui),
            "ultimo_la": _ultimo_lancamento(_livro(outra), nome_la),
        }
    return avisos


def totais_saldos(linhas: list[dict]) -> dict:
    debito = sum(x["debito"] for x in linhas)
    credito = sum(x["credito"] for x in linhas)
    return {"debito": debito, "credito": credito, "saldo": round(debito - credito, 2)}
