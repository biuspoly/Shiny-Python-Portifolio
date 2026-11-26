from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

import polars as pl

ARQUIVO_CATALOGO = Path(__file__).resolve().parent.parent / "config" / "composicao_financeira.json"

CATEGORIAS_ENTRADA_DO_DIA = ("MOVIMENTAÇÃO DO DIA", "OUTRAS ENTRADAS")

AGREGADOS = {
    "novo_saldo_liberado": {
        "chaves": ["saldo_liberado_conta", "aplicacao_financeira"],
        "categorias": list(CATEGORIAS_ENTRADA_DO_DIA),
    },
    "novo_saldo_com_especial": {"chaves": ["novo_saldo_liberado", "limite_especial"], "fora_do_caixa": True},
    "saldo_final_liberado": {"chaves": ["novo_saldo_liberado", "total_despesas_sugeridas"]},
    "saldo_uso_especial": {"chaves": ["saldo_final_liberado", "limite_especial"]},
}


def por_revenda(base: pl.DataFrame, revenda: str) -> pl.DataFrame:
    if base.is_empty() or "revenda" not in base.columns:
        return pl.DataFrame()
    return base.filter(pl.col("revenda") == revenda)


@lru_cache(maxsize=1)
def _rotulos_dos_bancos() -> dict[str, str]:
    try:
        catalogo = json.loads(ARQUIVO_CATALOGO.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  [!] catalogo nao lido pra rotulo de banco -- {exc}")
        return {}
    return {b["chave"]: b["rotulo"] for b in catalogo.get("bancos", [])}


@lru_cache(maxsize=1)
def categorias() -> dict[str, str]:
    try:
        catalogo = json.loads(ARQUIVO_CATALOGO.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  [!] catalogo nao lido pra categoria -- {exc}")
        return {}
    return {i["chave"]: i["categoria"] for i in catalogo.get("itens", [])}


def rotulo_banco(chave: str) -> str:
    return _rotulos_dos_bancos().get(chave, chave)


def _manual_do_dia(dados, revenda: str, data_ref: date, banco: str) -> pl.DataFrame:
    base = por_revenda(dados["dados_manuais"], revenda)
    if base.is_empty() or "banco" not in base.columns:
        return pl.DataFrame()
    return base.filter(
        (pl.col("banco") == rotulo_banco(banco)) & (pl.col("data").cast(pl.Date, strict=False) == data_ref)
    )


def _soma_manual(dados, revenda, data_ref, banco, coluna, condicao=None):
    linhas = _manual_do_dia(dados, revenda, data_ref, banco)
    if linhas.is_empty() or coluna not in linhas.columns:
        return None, "sem lançamento manual no dia"
    if condicao is not None:
        linhas = linhas.filter(condicao)
        if linhas.is_empty():
            return None, "sem lançamento manual no dia"
    return float(linhas[coluna].cast(pl.Float64, strict=False).sum() or 0), f"manual de {data_ref}"


def transf_outros_bancos_sai(dados, revenda, data_ref, banco="caixa_999"):
    return _soma_manual(dados, revenda, data_ref, banco, "transferencia_bancos")


def transf_outros_bancos_entra(dados, revenda, data_ref, banco="caixa_999"):
    base = por_revenda(dados["dados_manuais"], revenda)
    if base.is_empty() or "destino_transf" not in base.columns:
        return None, "sem lançamento manual no dia"
    linhas = base.filter(
        (pl.col("destino_transf") == rotulo_banco(banco)) & (pl.col("data").cast(pl.Date, strict=False) == data_ref)
    )
    if linhas.is_empty():
        return None, "sem lançamento manual no dia"
    return float(linhas["transferencia_bancos"].cast(pl.Float64, strict=False).sum() or 0), f"manual de {data_ref}"


def brinks_antes_16(dados, revenda, data_ref, banco="caixa_999"):
    linhas = _manual_do_dia(dados, revenda, data_ref, banco)
    if linhas.is_empty() or "brinks_antes_16" not in linhas.columns:
        return None, "sem lançamento manual no dia"
    return float(linhas["brinks_antes_16"].cast(pl.Float64, strict=False).sum() or 0), f"manual de {data_ref}"


def adiantamento_romaneios(dados, revenda, data_ref, banco="caixa_999"):
    linhas = _manual_do_dia(dados, revenda, data_ref, banco)
    if linhas.is_empty() or "adiantamento_romaneios" not in linhas.columns:
        return None, "sem lançamento manual no dia"
    valor = linhas["adiantamento_romaneios"].cast(pl.Float64, strict=False).max()
    return float(valor or 0), f"manual de {data_ref}"


def emprestimos_devolucoes(dados, revenda, data_ref, banco="caixa_999"):
    return _soma_manual(dados, revenda, data_ref, banco, "devolucao_emprestimos", pl.col("entrada_saida") == "Entrada")


def devolucoes_emprestimos(dados, revenda, data_ref, banco="caixa_999"):
    return _soma_manual(dados, revenda, data_ref, banco, "devolucao_emprestimos", pl.col("entrada_saida") == "Saída")


def romaneio_pendente(dados, revenda, data_ref, banco="caixa_999"):
    return _soma_manual(dados, revenda, data_ref, banco, "romaneio_pendente_encerrado")


def credito_mar_utilizado(dados, revenda, data_ref, banco="caixa_999"):
    return _soma_manual(dados, revenda, data_ref, banco, "credito_mar_utilizado")


def credito_fabrica_manual(dados, revenda, data_ref, banco="bradesco_1"):
    from core import fabricas

    campo = (fabricas.fabrica_da_revenda(revenda) or {}).get("campo_no_dado_manual")
    if not campo:
        return None, "a fábrica desta revenda manda extrato"
    if banco != "bradesco_1":
        return 0.0, "só entra na coluna do Bradesco 1"
    if "dados_manuais" not in dados:
        return 0.0, "sem lançamento manual no dia"
    linhas = _manual_do_dia(dados, revenda, data_ref, banco)
    if linhas.is_empty() or campo not in linhas.columns:
        return 0.0, "sem crédito informado no dia"
    valores = (linhas.sort("hora", nulls_last=False) if "hora" in linhas.columns else linhas)[campo]
    valores = valores.cast(pl.Utf8).str.strip_chars().cast(pl.Float64, strict=False).drop_nulls()
    if valores.is_empty():
        return 0.0, "sem crédito informado no dia"
    return float(valores[-1]), f"informado nos Dados Manuais de {data_ref}"


def _movimentos_entre_revendas(dados, data_ref: date) -> pl.DataFrame:
    base = dados["dados_manuais"]
    colunas = (
        "data",
        "revenda",
        "banco",
        "revenda_destino",
        "destino_transf",
        "entrada_saida",
        "transferencia_revendas",
    )
    if base.is_empty() or any(c not in base.columns for c in colunas):
        return pl.DataFrame()

    lancamentos = (
        base.select(colunas)
        .with_columns(
            pl.col("transferencia_revendas").cast(pl.Float64, strict=False).fill_null(0.0).alias("valor"),
            pl.col("data").cast(pl.Date, strict=False).alias("dia"),
        )
        .filter((pl.col("valor") != 0) & (pl.col("dia") == data_ref))
    )
    if lancamentos.is_empty():
        return pl.DataFrame()

    def ponta(marcador: str, coluna_revenda: str, coluna_banco: str, tipo: str) -> pl.DataFrame:
        parte = lancamentos.filter(pl.col("entrada_saida") == marcador)
        if parte.is_empty():
            return pl.DataFrame()
        return parte.select(
            pl.col(coluna_revenda).cast(pl.Utf8).alias("revenda"),
            pl.col(coluna_banco).cast(pl.Utf8).alias("banco"),
            pl.lit(tipo).alias("tipo"),
            pl.col("valor"),
        )

    partes = [
        ponta("Entrada", "revenda", "banco", "entrada"),
        ponta("Entrada", "revenda_destino", "destino_transf", "saida"),
        ponta("Saída", "revenda", "banco", "saida"),
        ponta("Saída", "revenda_destino", "destino_transf", "entrada"),
    ]
    partes = [x for x in partes if not x.is_empty()]
    return pl.concat(partes, how="vertical") if partes else pl.DataFrame()


def _transf_entre_revendas(dados, revenda, data_ref, banco, tipo: str):
    movimentos = _movimentos_entre_revendas(dados, data_ref)
    if movimentos.is_empty():
        return None, "sem transferência entre revendas no dia"
    do_banco = movimentos.filter(
        (pl.col("revenda") == revenda) & (pl.col("banco") == rotulo_banco(banco)) & (pl.col("tipo") == tipo)
    )
    if do_banco.is_empty():
        return None, "sem transferência entre revendas no dia"
    return float(do_banco["valor"].sum() or 0), f"transferência de {data_ref}"


def transf_matriz_filial_entra(dados, revenda, data_ref, banco="caixa_999"):
    return _transf_entre_revendas(dados, revenda, data_ref, banco, "entrada")


def transf_matriz_filial_sai(dados, revenda, data_ref, banco="caixa_999"):
    return _transf_entre_revendas(dados, revenda, data_ref, banco, "saida")


ITENS_MANUAIS = {
    "transf_outros_bancos_entra": transf_outros_bancos_entra,
    "transf_outros_bancos_sai": transf_outros_bancos_sai,
    "transf_matriz_filial_entra": transf_matriz_filial_entra,
    "transf_matriz_filial_sai": transf_matriz_filial_sai,
    "brinks_antes_16": brinks_antes_16,
    "adiantamento_romaneios": adiantamento_romaneios,
    "emprestimos_devolucoes": emprestimos_devolucoes,
    "devolucoes_emprestimos": devolucoes_emprestimos,
    "romaneio_pendente": romaneio_pendente,
    "credito_mar_utilizado": credito_mar_utilizado,
    "credito_fabrica": credito_fabrica_manual,
}

SAIDAS_JA_CONTADAS = (
    "devolucoes_emprestimos",
    "transf_outros_bancos_sai",
    "transf_matriz_filial_sai",
    "romaneio_pendente",
    "credito_mar_utilizado",
)


def _propagar(delta: dict[str, float], banco: str, categoria_de: dict[str, str]) -> dict[tuple[str, str], float]:
    if not delta:
        return {}
    delta = dict(delta)
    delta["total_despesas_sugeridas"] = -sum(delta.get(c, 0.0) for c in SAIDAS_JA_CONTADAS)
    for chave, regra in AGREGADOS.items():
        if regra.get("fora_do_caixa") and banco == "caixa_999":
            continue
        parcelas = list(regra.get("chaves", []))
        for categoria in regra.get("categorias", []):
            parcelas += [c for c, cat in categoria_de.items() if cat == categoria]
        delta[chave] = sum(delta.get(p, 0.0) for p in parcelas)
    return {(chave, banco): valor for chave, valor in delta.items() if round(valor, 2)}


def diferenca(
    antes: pl.DataFrame, depois: pl.DataFrame, revenda: str, data_ref: date, bancos, categoria_de: dict[str, str]
) -> dict[tuple[str, str], float]:
    mudou: dict[tuple[str, str], float] = {}
    for banco in bancos:
        delta: dict[str, float] = {}
        for chave, funcao in ITENS_MANUAIS.items():
            novo = funcao({"dados_manuais": depois}, revenda, data_ref, banco)[0] or 0.0
            velho = funcao({"dados_manuais": antes}, revenda, data_ref, banco)[0] or 0.0
            if round(novo - velho, 2):
                delta[chave] = novo - velho
        mudou.update(_propagar(delta, banco, categoria_de))
    return mudou


def refazer_manuais(linhas: pl.DataFrame, dados_manuais: pl.DataFrame, revenda: str) -> pl.DataFrame:
    if linhas.is_empty() or "DATA_REFERENCIA" not in linhas.columns:
        return linhas
    dia = linhas["DATA_REFERENCIA"].cast(pl.Date, strict=False).max()
    dados = {"dados_manuais": dados_manuais}
    guardado = {
        (r["CHAVE"], r["BANCO"]): r["VALOR"] for r in linhas.select("CHAVE", "BANCO", "VALOR").iter_rows(named=True)
    }
    categoria_de = categorias()
    mudou: dict[tuple[str, str], float] = {}
    for banco in linhas["BANCO"].unique().to_list():
        delta: dict[str, float] = {}
        for chave, funcao in ITENS_MANUAIS.items():
            if (chave, banco) not in guardado:
                continue
            novo = funcao(dados, revenda, dia, banco)[0]
            if novo is None and chave == "credito_fabrica":
                continue
            diferenca_item = (novo or 0.0) - (guardado[(chave, banco)] or 0.0)
            if round(diferenca_item, 2):
                delta[chave] = diferenca_item
        mudou.update(_propagar(delta, banco, categoria_de))
    if not mudou:
        return linhas
    soma = pl.DataFrame(
        {"CHAVE": [c for c, _b in mudou], "BANCO": [b for _c, b in mudou], "_delta": list(mudou.values())},
        schema={"CHAVE": pl.Utf8, "BANCO": pl.Utf8, "_delta": pl.Float64},
    )
    return (
        linhas.join(soma, on=["CHAVE", "BANCO"], how="left")
        .with_columns(
            pl.when(pl.col("_delta").is_not_null())
            .then(pl.col("VALOR").cast(pl.Float64).fill_null(0.0) + pl.col("_delta"))
            .otherwise(pl.col("VALOR"))
            .alias("VALOR")
        )
        .drop("_delta")
    )
