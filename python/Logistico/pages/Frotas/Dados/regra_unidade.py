from __future__ import annotations

import polars as pl

from core.config_arquivo import carregar_json

ARQUIVO_CONFIG = "frota_unidade_fixa"

_EMPRESA_SEM_NOME = ("", "0")


def grupos() -> list[dict]:
    config = carregar_json(ARQUIVO_CONFIG, {})
    if not isinstance(config, dict):
        return []
    validos = []
    for grupo in config.get("grupos", []) or []:
        if not isinstance(grupo, dict):
            continue
        raizes = [str(r).strip() for r in grupo.get("raizes_cnpj", []) or [] if str(r).strip()]
        nomes = [str(n).strip().upper() for n in grupo.get("nomes_empresa", []) or [] if str(n).strip()]
        if not raizes and not nomes:
            continue
        validos.append(
            {
                "nome": str(grupo.get("nome") or "").strip(),
                "raizes_cnpj": raizes,
                "nomes_empresa": nomes,
                "unidade_padrao": str(grupo.get("unidade_padrao") or "").strip(),
            }
        )
    return validos


def _raiz_cnpj() -> pl.Expr:
    return pl.col("CNPJ_EMP").cast(pl.Utf8).str.replace_all(r"\D", "").str.slice(0, 8)


def _nome_empresa() -> pl.Expr:
    return pl.col("EMPRESA").cast(pl.Utf8).str.strip_chars().str.to_uppercase()


def _expr_do_grupo(grupo: dict) -> pl.Expr:
    condicoes = []
    if grupo["raizes_cnpj"]:
        condicoes.append(_raiz_cnpj().is_in(grupo["raizes_cnpj"]))
    for trecho in grupo["nomes_empresa"]:
        condicoes.append(_nome_empresa().str.contains(trecho, literal=True))
    pertence = condicoes[0]
    for condicao in condicoes[1:]:
        pertence = pertence | condicao
    return pertence.fill_null(False)


def _unidade_do_grupo(grupo: dict) -> pl.Expr:
    nome = _nome_empresa()
    padrao = pl.lit(grupo["unidade_padrao"] or None, dtype=pl.Utf8)
    return (
        pl.when(nome.is_null() | nome.is_in(_EMPRESA_SEM_NOME))
        .then(padrao)
        .otherwise(pl.col("EMPRESA").cast(pl.Utf8).str.strip_chars())
    )


def expr_unidade_fixa() -> pl.Expr | None:
    configurados = grupos()
    if not configurados:
        return None
    expressao = pl.when(_expr_do_grupo(configurados[0])).then(_unidade_do_grupo(configurados[0]))
    for grupo in configurados[1:]:
        expressao = expressao.when(_expr_do_grupo(grupo)).then(_unidade_do_grupo(grupo))
    return expressao.otherwise(None)


def aplicar_unidade_fixa(base: pl.DataFrame) -> pl.DataFrame:
    expressao = expr_unidade_fixa()
    if expressao is None or base.is_empty():
        return base
    if "UNIDADE" not in base.columns or "CNPJ_EMP" not in base.columns:
        return base
    if "EMPRESA" not in base.columns:
        base = base.with_columns(pl.lit(None, dtype=pl.Utf8).alias("EMPRESA"))
    fixa = pl.coalesce([expressao, pl.col("UNIDADE")])
    if "NOME_EMPRESA_FINAL" in base.columns:
        fixa = pl.when(pl.col("NOME_EMPRESA_FINAL").is_not_null()).then(pl.col("UNIDADE")).otherwise(fixa)
    return base.with_columns(fixa.alias("UNIDADE"))
