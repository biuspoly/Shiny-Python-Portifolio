import re
from datetime import datetime

import polars as pl

# No portfólio não há banco nem pasta de upload servida: transferências e motivos
# ficam na memória desta sessão (no Shinylive, cada visitante tem o próprio Python),
# e do anexo guarda-se só o nome do arquivo.
TRANSFERENCIAS: list[dict] = []
MOVIMENTACOES: list[dict] = []

UNIDADE_PARA_CNPJ = {
    "NATAL": "00000000000100",
    "FORTALEZA": "00000000000280",
    "TERESINA": "00000000000360",
    "SÃO LUÍS": "00000000000440",
    "LOCADORA": "00000000000002",
    "VENDIDO": "00000000000003",
}

UNIDADES_TRANSFERENCIA = sorted(UNIDADE_PARA_CNPJ)


def _sanitizar_nome_arquivo(nome: str) -> str:
    return re.sub(r"[^\w.\-]", "_", nome)


def limite_motivo() -> int:
    return 150


COLUNA_TIPO_SAIDA = "TIPO_SAIDA"
COLUNA_TIPO_SAIDA_OUTRO = "TIPO_SAIDA_OUTRO"
COLUNA_COMPRADOR = "COMPRADOR"
COLUNA_VALOR_VENDA = "VALOR_VENDA"


def salvar_anexo(prefixo: str, placa: str, sufixo: str, datapath: str, nome_original: str) -> str:
    return f"{prefixo}_{placa}_{sufixo}_{_sanitizar_nome_arquivo(nome_original)}"


def caminho_para_url(caminho) -> str:
    return ""


def registrar_transferencia(
    unidade_ini: str, placa: str, anexo_path: str | None, usuario: str, unidade_fim: str
) -> None:
    TRANSFERENCIAS.append(
        {"DATA_HORA": datetime.now(), "PLACA": placa, "NOME_EMPRESA_FINAL": unidade_fim, "ANEXO": anexo_path or ""}
    )


def registrar_motivo_saida(
    cnpj_emp: str,
    placa: str,
    motivo: str,
    anexo_path: str | None,
    tipo_saida: str | None = None,
    tipo_saida_outro: str | None = None,
    comprador: str | None = None,
    valor_venda: float | None = None,
) -> None:
    MOVIMENTACOES.append(
        {
            "DATA_HORA": datetime.now(),
            "EMPRESA": cnpj_emp,
            "PLACA": placa,
            "MOTIVO": motivo,
            "ANEXO": anexo_path or "",
            COLUNA_TIPO_SAIDA: tipo_saida or None,
            COLUNA_TIPO_SAIDA_OUTRO: tipo_saida_outro or None,
            COLUNA_COMPRADOR: comprador or None,
            COLUNA_VALOR_VENDA: valor_venda,
        }
    )


def carregar_transferencias() -> pl.DataFrame:
    schema = {"DATA_HORA": pl.Datetime, "PLACA": pl.Utf8, "NOME_EMPRESA_FINAL": pl.Utf8, "ANEXO": pl.Utf8}
    return (
        pl.DataFrame(TRANSFERENCIAS, schema=schema)
        .sort("DATA_HORA", descending=True)
        .group_by("PLACA", maintain_order=True)
        .first()
        .select(["PLACA", "NOME_EMPRESA_FINAL", "ANEXO"])
    )


_COLUNAS_MOVIMENTACAO = [
    "EMPRESA",
    "PLACA",
    "MOTIVO",
    "ANEXO",
    COLUNA_TIPO_SAIDA,
    COLUNA_TIPO_SAIDA_OUTRO,
    COLUNA_COMPRADOR,
    COLUNA_VALOR_VENDA,
]


def carregar_movimentacao() -> pl.DataFrame:
    schema = {"DATA_HORA": pl.Datetime, **{c: pl.Utf8 for c in _COLUNAS_MOVIMENTACAO}, COLUNA_VALOR_VENDA: pl.Float64}
    return (
        pl.DataFrame(MOVIMENTACOES, schema=schema)
        .sort("DATA_HORA", descending=True)
        .group_by(["EMPRESA", "PLACA"], maintain_order=True)
        .first()
        .select(_COLUNAS_MOVIMENTACAO)
    )


def _mapa(tabela: pl.DataFrame, coluna_chave: str, coluna_valor: str) -> dict[str, str]:
    if tabela.height == 0:
        return {}
    filtrado = tabela.filter(pl.col(coluna_valor).is_not_null() & (pl.col(coluna_valor) != ""))
    return dict(zip(filtrado[coluna_chave].to_list(), filtrado[coluna_valor].to_list()))


def mapa_anexo_transferencia(transferencias: pl.DataFrame) -> dict[str, str]:
    return _mapa(transferencias, "PLACA", "ANEXO")


def mapa_motivo(movimentacao: pl.DataFrame) -> dict[str, str]:
    return _mapa(movimentacao, "PLACA", "MOTIVO")


def mapa_anexo_motivo(movimentacao: pl.DataFrame) -> dict[str, str]:
    return _mapa(movimentacao, "PLACA", "ANEXO")


def mapa_tipo_saida(movimentacao: pl.DataFrame) -> dict[str, str]:
    return _mapa(movimentacao, "PLACA", COLUNA_TIPO_SAIDA)


def mapa_tipo_saida_outro(movimentacao: pl.DataFrame) -> dict[str, str]:
    return _mapa(movimentacao, "PLACA", COLUNA_TIPO_SAIDA_OUTRO)


def mapa_comprador(movimentacao: pl.DataFrame) -> dict[str, str]:
    return _mapa(movimentacao, "PLACA", COLUNA_COMPRADOR)


def mapa_valor_venda(movimentacao: pl.DataFrame) -> dict[str, float]:
    if movimentacao.height == 0 or COLUNA_VALOR_VENDA not in movimentacao.columns:
        return {}
    filtrado = movimentacao.filter(pl.col(COLUNA_VALOR_VENDA).is_not_null())
    return dict(zip(filtrado["PLACA"].to_list(), filtrado[COLUNA_VALOR_VENDA].to_list()))


def marcar_motivo_informado(base: pl.DataFrame, movimentacao: pl.DataFrame) -> pl.DataFrame:
    if "PLACA" not in base.columns:
        return base.with_columns(
            pl.lit("Não").alias("MOTIVO_INFORMADO"),
            pl.lit("").alias(COLUNA_TIPO_SAIDA),
        )
    placas = pl.Series("placas_com_motivo", list(mapa_motivo(movimentacao)), dtype=pl.Utf8)
    base = base.with_columns(
        pl.when(pl.col("PLACA").is_in(placas)).then(pl.lit("Sim")).otherwise(pl.lit("Não")).alias("MOTIVO_INFORMADO")
    )
    tipos = mapa_tipo_saida(movimentacao)
    coluna_tipo = pl.col("PLACA").replace_strict(tipos, default="", return_dtype=pl.Utf8) if tipos else pl.lit("")
    return base.with_columns(coluna_tipo.alias(COLUNA_TIPO_SAIDA))


def aplicar_transferencias(base: pl.DataFrame, transferencias: pl.DataFrame) -> pl.DataFrame:
    if transferencias.height == 0 or "PLACA" not in base.columns:
        return base

    transferencias_renomeada = transferencias.select(
        "PLACA", pl.col("NOME_EMPRESA_FINAL").alias("_TRANSFERENCIA_UNIDADE")
    )
    return (
        base.join(transferencias_renomeada, on="PLACA", how="left")
        .with_columns(pl.coalesce(["_TRANSFERENCIA_UNIDADE", "UNIDADE"]).alias("UNIDADE"))
        .drop("_TRANSFERENCIA_UNIDADE")
    )
