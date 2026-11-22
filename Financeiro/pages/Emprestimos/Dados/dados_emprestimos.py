from datetime import date

import polars as pl

from core.config_arquivo import carregar_json
from pages.PPF.Dados import dados_ppf as d

CODIGOS_EMPRESTIMO = carregar_json("parametros_financeiro").get(
    "codigos_emprestimo", [106, 107, 108, 109, 110, 111, 112, 96, 61]
)


def _contrato_e_parcela(num_doc: str | None) -> tuple[str | None, int | None]:
    if not num_doc:
        return None, None
    texto = num_doc.strip()

    partes = texto.split()
    if len(partes) >= 2:
        parcela = partes[-1]
        return partes[0], int(parcela) if parcela.isdigit() else None

    if "/" in texto:
        posicao = texto.index("/")
        depois = texto[posicao + 1 :]
        if len(depois) == 6 and depois.isdigit():
            return texto[: posicao + 5], int(depois[4:])
        if len(depois) == 4 and depois.isdigit():
            return texto[:posicao], int(depois[:2])

    if len(texto) >= 3 and texto[-2:].isdigit():
        return texto[:-2], int(texto[-2:])

    return texto, None


_TIRAR_DO_BANCO = [
    r"\bBANCO\b",
    r"\bFINANCIAMENTOS\b",
    r"\bFINANCIAMENTO\b",
    r"\bFINANCEIRA\b",
    r"\bS\.?A\.?\b",
    r"\bS\/A\b",
    r"\bSA\b",
    r"\bA0031767\b",
    r"\bFINANCIAMENT\b",
    r"\bS A\b",
    r"\bBRASIL\b",
    r"\bLTDA\b",
    r"\bE\b",
    r"\bCOM\b",
    r"\bV\b",
    r"\bIND\b",
    r"\bCOM\b",
    r"\bCOOP\b",
    r"\bCRED\b",
    r"\bPOUP\b",
    r"\bDO\b",
    r"\bRN\b",
]


def limpar_nome_banco(nome: str | None) -> str | None:
    import re

    if not nome:
        return nome
    texto = str(nome).upper()
    for padrao in _TIRAR_DO_BANCO:
        texto = re.sub(padrao, "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"[\.,]", "", texto)
    return re.sub(r"\s{2,}", " ", texto).strip()


def _configuracoes() -> dict[tuple[str, str], dict]:
    from core import manual_arquivo

    fora: dict[tuple[str, str], dict] = {}
    base = d._carregar("emprestimos_configuracoes")
    for fonte in (base, manual_arquivo.configs_emprestimo()):
        if fonte.is_empty():
            continue
        coluna = "REVENDA" if "REVENDA" in fonte.columns else "revenda"
        for r in fonte.iter_rows(named=True):
            fora[(r.get(coluna), r.get("contrato"))] = {
                "valor_credito": r.get("valor_credito"),
                "entrada": r.get("entrada"),
                "taxa_juros": r.get("taxa_juros"),
            }
    return fora


def _pagos_por_contrato(revenda: str | None) -> dict[tuple[str, str], dict]:
    base = d.titulos_pagos_emprestimos()
    if base.is_empty():
        base = d.titulos_pagos()
    base = d.filtrar_por_revenda(base, revenda)
    fora: dict[tuple[str, str], dict] = {}
    if base.is_empty() or "PGMOVBAI_NDUPL" not in base.columns:
        return fora
    for r in base.select("REVENDA", "PGMOVBAI_NDUPL", "PGMOVBAI_DTP", "DATA").iter_rows(named=True):
        contrato, _parcela = _contrato_e_parcela(r["PGMOVBAI_NDUPL"])
        if not contrato:
            continue
        item = fora.setdefault((r["REVENDA"], contrato), {"datas": [], "docs": set()})
        quando = r["PGMOVBAI_DTP"] or r["DATA"]
        if quando is not None:
            item["datas"].append(quando)
        item["docs"].add(r["PGMOVBAI_NDUPL"])
    return {
        k: {"data_inicial_paga": min(v["datas"]) if v["datas"] else None, "parcelas_pagas_reais": len(v["docs"])}
        for k, v in fora.items()
    }


def contratos(revenda: str | None) -> pl.DataFrame:
    base = d.filtrar_por_revenda(d.contas_pagar(), revenda)
    if base.is_empty():
        return pl.DataFrame()
    base = base.filter(pl.col("PGMOVMOV_TPOD_1").is_in(CODIGOS_EMPRESTIMO))
    if base.is_empty():
        return pl.DataFrame()
    base = d.com_nome_fornecedor(base)

    partes = [_contrato_e_parcela(doc) for doc in base["PGMOVMOV_NDUPL"].to_list()]
    base = base.with_columns(
        pl.Series("CONTRATO", [c for c, _p in partes], dtype=pl.Utf8),
        pl.Series("PARCELA_NUM", [p for _c, p in partes], dtype=pl.Int64),
        pl.col("data_emissao").cast(pl.Date, strict=False).alias("DATA_EMISSAO"),
    ).drop_nulls("CONTRATO")
    if base.is_empty():
        return pl.DataFrame()

    base = base.sort(["CONTRATO", "DATA"], nulls_last=True)
    agrupado = (
        base.group_by("CONTRATO")
        .agg(
            pl.col("REVENDA").first().alias("Revenda"),
            pl.col("FORNECEDOR").first().alias("_banco"),
            pl.col("descricao_despesa")
            .filter(pl.col("descricao_despesa").is_not_null() & (pl.col("descricao_despesa") != ""))
            .last()
            .alias("Tipo"),
            pl.col("DATA_EMISSAO").first().alias("Contratação"),
            pl.col("DATA").last().alias("Data Final"),
            pl.col("DATA").first().alias("_primeira"),
            pl.col("PGMOVMOV_VALOR").first().alias("Valor Parcela"),
            pl.col("PARCELA_NUM").max().alias("Parcelas"),
            pl.len().alias("Parcelas a vencer"),
            pl.col("PGMOVMOV_VALOR").sum().alias("Saldo a Pagar"),
        )
        .with_columns(
            ("Dia " + pl.col("_primeira").dt.day().cast(pl.Utf8)).alias("Vencimento"),
            pl.col("CONTRATO").alias("Contrato"),
        )
    )
    config = _configuracoes()
    pagos = _pagos_por_contrato(revenda)
    extras = {
        "Banco": [],
        "Valor Crédito": [],
        "Entrada": [],
        "Taxa Juros %": [],
        "Data Inicial": [],
        "Parcelas Pagas": [],
    }
    for r in agrupado.iter_rows(named=True):
        chave = (r["Revenda"], r["Contrato"])
        cfg = config.get(chave, {})
        pg = pagos.get(chave, {})
        extras["Banco"].append(limpar_nome_banco(r["_banco"]))
        extras["Valor Crédito"].append(cfg.get("valor_credito"))
        extras["Entrada"].append(cfg.get("entrada"))
        extras["Taxa Juros %"].append(cfg.get("taxa_juros"))
        extras["Data Inicial"].append(pg.get("data_inicial_paga"))
        extras["Parcelas Pagas"].append(pg.get("parcelas_pagas_reais", 0))
    agrupado = agrupado.with_columns(
        pl.Series("Banco", extras["Banco"], dtype=pl.Utf8),
        pl.Series("Valor Crédito", extras["Valor Crédito"], dtype=pl.Float64),
        pl.Series("Entrada", extras["Entrada"], dtype=pl.Float64),
        pl.Series("Taxa Juros %", extras["Taxa Juros %"], dtype=pl.Float64),
        pl.Series("Data Inicial", extras["Data Inicial"], dtype=pl.Date),
        pl.Series("Parcelas Pagas", extras["Parcelas Pagas"], dtype=pl.Int64),
    ).drop("_banco", "_primeira")
    return agrupado.sort("Contratação", nulls_last=True)


def totais(base: pl.DataFrame) -> dict[str, float]:
    if base.is_empty():
        return {"credito": 0.0, "parcela": 0.0, "pagar": 0.0}
    return {
        "credito": float(base["Valor Crédito"].fill_null(0).sum() or 0),
        "parcela": float(base["Valor Parcela"].sum() or 0),
        "pagar": float(base["Saldo a Pagar"].sum() or 0),
    }


FILTROS_DE_DATA = {"ano": "year", "mes": "month"}


def recortar(base: pl.DataFrame, escolhidos: dict[str, object], sem: str | None = None) -> pl.DataFrame:
    if base.is_empty():
        return base
    for chave, valor in escolhidos.items():
        if chave == sem or not valor:
            continue
        if chave in FILTROS_DE_DATA:
            parte = getattr(pl.col("Contratação").dt, FILTROS_DE_DATA[chave])()
            base = base.filter(parte == int(valor))
        elif chave in base.columns:
            base = base.filter(pl.col(chave).cast(pl.Utf8) == str(valor))
    return base


def opcoes_em_cascata(base: pl.DataFrame, chave: str, escolhidos: dict[str, object]) -> list:
    if base.is_empty():
        return []
    parcial = recortar(base, escolhidos, sem=chave)
    proprio = escolhidos.get(chave)
    if chave in FILTROS_DE_DATA:
        opcoes = {
            getattr(d_, "year" if chave == "ano" else "month")
            for d_ in parcial["Contratação"].to_list()
            if isinstance(d_, date)
        }
        if proprio:
            opcoes.add(int(proprio))
        return sorted(opcoes, reverse=chave == "ano")
    if chave not in parcial.columns:
        return []
    opcoes = {str(v) for v in parcial[chave].unique().to_list() if v not in (None, "")}
    if proprio:
        opcoes.add(str(proprio))
    return sorted(opcoes)
