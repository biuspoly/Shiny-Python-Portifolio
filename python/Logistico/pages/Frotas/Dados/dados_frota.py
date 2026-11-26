from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl

from core.compat import ler_parquet
from core.config_arquivo import PASTA_CONFIG

from .regra_multa import (
    COLUNA_SITUACAO_MULTA,
    PAGA_DESCONHECIDA,
    PAGA_NAO,
    PAGA_SUSPENSA,
    SITUACAO_SEM_INFORMACAO,
    SITUACOES_MULTA,
    expr_paga,
    expr_sem_situacao,
)
from .regra_unidade import ARQUIVO_CONFIG as ARQUIVO_UNIDADE_FIXA
from .regra_unidade import aplicar_unidade_fixa

PASTA_PARQUET = Path(__file__).parents[3] / "data" / "bd_senatran"

_cache: dict[tuple, object] = {}


def _carregar(nome: str) -> pl.DataFrame:
    caminho = PASTA_PARQUET / f"{nome}.parquet"
    chave = (nome, caminho.stat().st_mtime)
    if chave not in _cache:
        _cache[chave] = ler_parquet(caminho)
    return _cache[chave]


def _carregar_frota(nome: str) -> pl.DataFrame:
    caminho = PASTA_PARQUET / f"{nome}.parquet"
    try:
        mtime_config = (PASTA_CONFIG / f"{ARQUIVO_UNIDADE_FIXA}.json").stat().st_mtime_ns
    except OSError:
        mtime_config = 0
    caminho_renainf = PASTA_PARQUET / "geral_renainf.parquet"
    mtime_renainf = caminho_renainf.stat().st_mtime if caminho_renainf.is_file() else 0
    chave = (nome, caminho.stat().st_mtime, mtime_config, mtime_renainf, "unidade_fixa")
    if chave not in _cache:
        base = aplicar_unidade_fixa(_carregar(nome)).with_columns(pl.col("DTA_EXEC").alias("ULT_ATUALIZACAO"))
        _cache[chave] = _com_multa_senatran(base, mtime_renainf)
    return _cache[chave]


def multa_senatran_por_placa(renainf: pl.DataFrame) -> pl.DataFrame:
    if renainf.height == 0 or not {"PLACA", "DTA_EXEC", "VALOR", "PAGA"} <= set(renainf.columns):
        return pl.DataFrame(schema={"PLACA": pl.Utf8, "MULTA_SENATRAN": pl.Float64, "CONSULTA_SENATRAN": pl.Utf8})
    return (
        renainf.with_columns(pl.col("DTA_EXEC").cast(pl.Utf8))
        .filter(pl.col("DTA_EXEC") == pl.col("DTA_EXEC").max().over("PLACA"))
        .group_by("PLACA")
        .agg(
            pl.col("VALOR")
            .cast(pl.Float64, strict=False)
            .filter(pl.col("PAGA") == PAGA_NAO)
            .sum()
            .alias("MULTA_SENATRAN"),
            pl.col("DTA_EXEC").first().alias("CONSULTA_SENATRAN"),
        )
    )


def _com_multa_senatran(base: pl.DataFrame, mtime_renainf: float) -> pl.DataFrame:
    renainf = carregar_geral_renainf() if mtime_renainf else pl.DataFrame()
    por_placa = multa_senatran_por_placa(renainf)
    multa_senatran = (
        pl.when(pl.col("DTA_EXEC").cast(pl.Utf8) >= pl.col("CONSULTA_SENATRAN"))
        .then(pl.col("MULTA_SENATRAN"))
        .otherwise(0.0)
        .fill_null(0.0)
    )
    alem_detran = (pl.col("MULTA_SENATRAN") - pl.col("MULTA").cast(pl.Float64, strict=False).fill_null(0.0)).clip(
        lower_bound=0.0
    )
    return (
        base.join(por_placa, on="PLACA", how="left")
        .with_columns(multa_senatran.alias("MULTA_SENATRAN"))
        .with_columns(alem_detran.alias("SENATRAN_ALEM_DETRAN"))
        .with_columns(
            pl.when(pl.col("SENATRAN_ALEM_DETRAN") > 0)
            .then(pl.col("DEBITO_DETRAN").fill_null(0.0) + pl.col("SENATRAN_ALEM_DETRAN"))
            .otherwise(pl.col("DEBITO_DETRAN"))
            .alias("DEBITO_DETRAN")
        )
        .drop("CONSULTA_SENATRAN")
    )


def carregar_geral_frota() -> pl.DataFrame:
    return _carregar_frota("geral_frota")


def carregar_geral_frota_entrada() -> pl.DataFrame:
    return _carregar_frota("geral_frota_entrada")


def carregar_geral_frota_saida() -> pl.DataFrame:
    return _carregar_frota("geral_frota_saida")


def carregar_geral_renajud() -> pl.DataFrame:
    return _carregar("geral_renajud")


def carregar_geral_rastreio() -> pl.DataFrame:
    caminho = PASTA_PARQUET / "geral_rastreio.parquet"
    if not caminho.is_file():
        return pl.DataFrame()
    return _carregar("geral_rastreio")


def rastreio_das_placas(rastreio: pl.DataFrame, base: pl.DataFrame) -> pl.DataFrame:
    if rastreio.is_empty() or "PLACA" not in base.columns:
        return rastreio
    return rastreio.filter(pl.col("PLACA").is_in(set(base["PLACA"].to_list())))


def carregar_geral_combustivel() -> pl.DataFrame:
    caminho = PASTA_PARQUET / "geral_combustivel.parquet"
    if not caminho.is_file():
        return pl.DataFrame()
    return _carregar("geral_combustivel")


def carregar_geral_renainf() -> pl.DataFrame:
    base = _carregar("geral_renainf")
    for coluna in base.columns:
        if coluna != COLUNA_SITUACAO_MULTA and coluna.upper() == COLUNA_SITUACAO_MULTA:
            base = base.rename({coluna: COLUNA_SITUACAO_MULTA})
            break
    if "PAGA_POR" not in base.columns:
        base = base.with_columns(pl.lit(None, dtype=pl.Utf8).alias("PAGA_POR"))
    if COLUNA_SITUACAO_MULTA not in base.columns:
        return base.with_columns(pl.lit(PAGA_DESCONHECIDA).alias("PAGA"))
    return base.with_columns(expr_paga())


def filtrar_por_revenda(base: pl.DataFrame, revenda: str | None) -> pl.DataFrame:
    if not revenda:
        return base
    revenda_upper = revenda.upper()
    return base.filter(
        pl.col("UNIDADE").str.to_uppercase().str.contains(revenda_upper)
        | pl.col("EMPRESA").str.to_uppercase().str.contains(revenda_upper)
    )


def placas_com_romaneio_antigo(base: pl.DataFrame) -> set[str]:
    return set(base.filter(pl.col("ULT_ROM").is_not_null())["PLACA"].to_list())


DIAS_JANELA_RECENTE = 7


def janela_recente(base: pl.DataFrame, dias: int = DIAS_JANELA_RECENTE) -> pl.DataFrame:
    if base.height == 0 or "DTA_EXEC" not in base.columns:
        return base
    maior = base["DTA_EXEC"].max()
    try:
        corte = (datetime.strptime(str(maior), "%Y%m%d") - timedelta(days=dias)).strftime("%Y%m%d")
    except (TypeError, ValueError):
        return base
    janela = base.filter(pl.col("DTA_EXEC") >= corte)
    chave = [c for c in ("PLACA", "CNPJ_EMP") if c in janela.columns]
    if not chave:
        return janela
    return janela.filter(pl.col("DTA_EXEC") == pl.col("DTA_EXEC").max().over(chave))


def data_mais_recente(base: pl.DataFrame) -> str | None:
    if "DTA_EXEC" not in base.columns or base.height == 0:
        return None
    return base["DTA_EXEC"].max()


def data_ultima_execucao() -> date | None:
    caminho = PASTA_PARQUET / "geral_frota.parquet"
    try:
        chave = ("_ultima_execucao", caminho.stat().st_mtime)
        if chave not in _cache:
            valor = ler_parquet(caminho, columns=["DTA_EXEC"])["DTA_EXEC"].max()
            _cache[chave] = datetime.strptime(str(valor), "%Y%m%d").date() if valor else None
        return _cache[chave]
    except (OSError, ValueError, TypeError):
        return None


def filtrar_por_data(base: pl.DataFrame, data: str) -> pl.DataFrame:
    return base.filter(pl.col("DTA_EXEC") == data)


def ultima_foto_por_placa(base: pl.DataFrame) -> pl.DataFrame:
    if base.height == 0 or "PLACA" not in base.columns or "DTA_EXEC" not in base.columns:
        return base
    return base.filter(pl.col("DTA_EXEC") == pl.col("DTA_EXEC").max().over("PLACA"))


def aplicar_filtros(base: pl.DataFrame, filtros: dict[str, list[str]]) -> pl.DataFrame:
    resultado = base
    for coluna, valores in filtros.items():
        if valores:
            resultado = resultado.filter(pl.col(coluna).is_in(valores))
    return resultado


COLUNAS_GERAL = [
    "EMPRESA",
    "UNIDADE",
    "UF_Emp",
    "PLACA",
    "TIPO",
    "MODELO",
    "ANO",
    "ANO_FAB",
    "RENAVAM",
    "CHASSI",
    "CARROCERIA",
    "TRANSFERENCIA",
    "ULT_ATUALIZACAO",
]


def tabela_geral(base: pl.DataFrame) -> pl.DataFrame:
    return base.select(COLUNAS_GERAL)


COLUNAS_RESTADM = [
    "EMPRESA",
    "UNIDADE",
    "UF_Emp",
    "PLACA",
    "TIPO",
    "MODELO",
    "ANO",
    "RENAVAM",
    "RESTRICAO_ADM",
    "GRAVAME",
    "GRAVAME_PENDENTE",
    "PROPRIETARIO",
    "TRANSFERENCIA",
    "ULT_ATUALIZACAO",
]


def tabela_restadm(base: pl.DataFrame) -> pl.DataFrame:
    return base.select(COLUNAS_RESTADM)


def tabela_renajud_consolidado(base: pl.DataFrame) -> pl.DataFrame:
    return base.group_by(
        ["EMPRESA", "UNIDADE", "UF_Emp", "PLACA", "TIPO", "MODELO", "ANO", "RENAJUD", "TRANSFERENCIA"]
    ).agg(
        pl.col("TOTAL_PROCESSOS").sum().alias("N_PROCESSOS"),
        pl.col("ULT_ATUALIZACAO").max(),
    )


def tabela_renajud_detalhado(base: pl.DataFrame, renajud: pl.DataFrame) -> pl.DataFrame:
    renajud_atual = renajud.filter(pl.col("DTA_EXEC") == renajud["DTA_EXEC"].max())
    veiculos_com_renajud = base.filter(pl.col("RENAJUD") == "Sim")
    return veiculos_com_renajud.select(
        "EMPRESA",
        "UNIDADE",
        "UF_Emp",
        "PLACA",
        "TIPO",
        "MODELO",
        "ANO",
        "TRANSFERENCIA",
        "ULT_ATUALIZACAO",
    ).join(
        renajud_atual.select("PLACA", "PROCESSO", "TIPO_RESTRICAO", "TRIBUNAL", "ORGAO"),
        on="PLACA",
        how="inner",
    )


def tabela_detran_consolidado(base: pl.DataFrame) -> pl.DataFrame:
    tabela = (
        base.group_by(["EMPRESA", "UNIDADE", "UF_Emp", "PLACA", "TIPO", "MODELO", "ANO", "RENAVAM", "TRANSFERENCIA"])
        .agg(
            pl.col("DEBITO_DETRAN").sum().alias("DEBITO_DETRAN"),
            pl.col("IPVA").sum().alias("IPVA"),
            pl.col("IPVA_AL_ANT").sum().alias("IPVA_AL_ANT"),
            pl.col("LICENCIAMENTO").sum().alias("LICENCIAMENTO"),
            pl.col("MULTA").sum().alias("MULTA"),
            pl.col("MULTA_SENATRAN").first().alias("MULTA_SENATRAN"),
            pl.col("SENATRAN_ALEM_DETRAN").sum().alias("SENATRAN_ALEM_DETRAN"),
            pl.col("TABELA_FIPE").first().alias("TABELA_FIPE"),
            pl.col("ULT_ATUALIZACAO").max(),
        )
        .with_columns(
            (
                pl.col("DEBITO_DETRAN")
                - pl.col("LICENCIAMENTO")
                - pl.col("IPVA")
                - pl.col("MULTA")
                - pl.col("SENATRAN_ALEM_DETRAN")
            ).alias("OUTROS_DEBITOS")
        )
        .drop("SENATRAN_ALEM_DETRAN")
    )
    return tabela.sort("DEBITO_DETRAN", descending=True)


COLUNAS_DETRAN_DETALHADO = [
    "EMPRESA",
    "UNIDADE",
    "UF_Emp",
    "PLACA",
    "TIPO",
    "MODELO",
    "ANO",
    "RENAINF",
    "AUTO_INFRACAO",
    "DATA_HORA_INF",
    "DT_IDENT_CONDUTOR",
    "VENCIMENTO",
    "VALOR",
    "PAGA",
    "PAGA_POR",
    "CONSULTADO_EM",
    "INFRACAO",
    "LOCAL",
    "ORGAO",
    "ULT_ATUALIZACAO",
    "TRANSFERENCIA",
    "MULTA_DESATUALIZADA",
]


def situacoes_disponiveis(renainf: pl.DataFrame) -> list[str]:
    if COLUNA_SITUACAO_MULTA not in renainf.columns or renainf.height == 0:
        return []
    presentes = {v for v in renainf[COLUNA_SITUACAO_MULTA].drop_nulls().unique().to_list() if str(v).strip()}
    conhecidas = [s for s in SITUACOES_MULTA if s in presentes]
    lista = conhecidas + sorted(presentes - set(SITUACOES_MULTA))
    if renainf.select(expr_sem_situacao().any()).item():
        lista.append(SITUACAO_SEM_INFORMACAO)
    return lista


def tabela_detran_detalhado(
    base: pl.DataFrame, renainf: pl.DataFrame, situacoes: list[str] | None = None
) -> pl.DataFrame:
    if "DTA_EXEC" in renainf.columns:
        renainf = renainf.with_columns(
            pl.col("DTA_EXEC").alias("CONSULTADO_EM"),
            (pl.col("DTA_EXEC") < pl.col("DTA_EXEC").max().over("PLACA")).alias("MULTA_DESATUALIZADA"),
        )
    else:
        renainf = renainf.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("CONSULTADO_EM"),
            pl.lit(False).alias("MULTA_DESATUALIZADA"),
        )
    if situacoes and COLUNA_SITUACAO_MULTA in renainf.columns:
        escolhidas = [s for s in situacoes if s != SITUACAO_SEM_INFORMACAO]
        condicao = pl.col(COLUNA_SITUACAO_MULTA).is_in(escolhidas) if escolhidas else pl.lit(False)
        if SITUACAO_SEM_INFORMACAO in situacoes:
            condicao = condicao | expr_sem_situacao()
        renainf = renainf.filter(condicao)
    tabela = base.select(
        "EMPRESA", "UNIDADE", "UF_Emp", "PLACA", "TIPO", "MODELO", "ANO", "TRANSFERENCIA", "ULT_ATUALIZACAO"
    ).join(
        renainf.select(
            "PLACA",
            "RENAINF",
            "AUTO_INFRACAO",
            "DATA_HORA_INF",
            "DT_IDENT_CONDUTOR",
            "VENCIMENTO",
            "VALOR",
            "INFRACAO",
            "LOCAL",
            "ORGAO",
            "PAGA",
            "PAGA_POR",
            "CONSULTADO_EM",
            "MULTA_DESATUALIZADA",
        ),
        on="PLACA",
        how="inner",
    )
    ordem = (
        pl.when(pl.col("PAGA") == PAGA_NAO)
        .then(0)
        .when(pl.col("PAGA") == PAGA_DESCONHECIDA)
        .then(1)
        .when(pl.col("PAGA") == PAGA_SUSPENSA)
        .then(2)
        .otherwise(3)
        .alias("_ORDEM_PAGA")
    )
    return (
        tabela.with_columns(ordem)
        .sort(["_ORDEM_PAGA", "VENCIMENTO"], descending=[False, True])
        .select(COLUNAS_DETRAN_DETALHADO)
    )


CLASSIFICACAO_TIPO = (
    pl.when(pl.col("TIPO").str.contains("TRATOR|REBOQ"))
    .then(pl.lit("Cavalo"))
    .when(pl.col("TIPO").str.contains("CAMINH") & ~pl.col("TIPO").str.contains("TRATOR"))
    .then(pl.lit("Caminhão"))
    .when(pl.col("TIPO").is_in(["AUTOMOVEL", "CAMIONETA", "UTILITARIO"]))
    .then(pl.lit("Carro"))
    .when(pl.col("TIPO").str.contains("MOTO"))
    .then(pl.lit("Moto"))
    .otherwise(pl.lit("Outros"))
)


def resumo_por_classe(base: pl.DataFrame) -> pl.DataFrame:
    return (
        base.with_columns(CLASSIFICACAO_TIPO.alias("CLASSE"))
        .filter(pl.col("CLASSE") != "Outros")
        .group_by("CLASSE")
        .agg(
            pl.len().alias("QTD"),
            (pl.col("RESTRICAO_ADM") == "Sim").sum().alias("REST_ADM"),
            (pl.col("RENAJUD") == "Sim").sum().alias("RENAJUD"),
            pl.col("DEBITO_DETRAN").sum().alias("DEBITO"),
        )
    )


def tabela_consolidada(base: pl.DataFrame) -> pl.DataFrame:
    consolidada = (
        base.with_columns(CLASSIFICACAO_TIPO.alias("CLASSE"))
        .group_by("DTA_EXEC")
        .agg(
            pl.col("CUSTO_API").sum().alias("CUSTO_API"),
            pl.col("PLACA").n_unique().alias("VEICULOS"),
            (pl.col("CLASSE") == "Carro").sum().alias("CARRO"),
            (pl.col("CLASSE") == "Moto").sum().alias("MOTO"),
            (pl.col("CLASSE") == "Cavalo").sum().alias("CAVALO"),
            (pl.col("CLASSE") == "Caminhão").sum().alias("CAMINHAO"),
            pl.col("DEBITO_DETRAN").sum().alias("DEBITO"),
            (pl.col("RENAJUD") == "Sim").sum().alias("RENAJUD"),
            pl.col("TABELA_FIPE").sum().alias("TABELA_FIPE"),
        )
        .sort("DTA_EXEC", descending=True)
    )
    for coluna in ["CUSTO_API", "VEICULOS", "CARRO", "MOTO", "CAVALO", "CAMINHAO", "DEBITO", "RENAJUD", "TABELA_FIPE"]:
        anterior = pl.col(coluna).shift(-1)
        consolidada = consolidada.with_columns(
            pl.when(pl.col(coluna) > anterior)
            .then(1)
            .when(pl.col(coluna) < anterior)
            .then(-1)
            .otherwise(0)
            .alias(f"TREND_{coluna}")
        )
    return consolidada


def tabela_custos(base: pl.DataFrame, mostrar_custo_api: bool = True) -> pl.DataFrame:
    custos = (
        base.group_by("EMPRESA")
        .agg(
            pl.col("CUSTO_API").sum().alias("CUSTO_API"),
            pl.col("PLACA").n_unique().alias("VEICULOS"),
            pl.col("DEBITO_DETRAN").sum().alias("DEBITO_DETRAN"),
            pl.col("IPVA").sum().alias("IPVA"),
            pl.col("IPVA_AL_ANT").sum().alias("IPVA_AL_ANT"),
            pl.col("LICENCIAMENTO").sum().alias("LICENCIAMENTO"),
            pl.col("MULTA").sum().alias("MULTA"),
            pl.col("MULTA_SENATRAN").filter(pl.col("PLACA").is_first_distinct()).sum().alias("MULTA_SENATRAN"),
            pl.col("SENATRAN_ALEM_DETRAN").sum().alias("SENATRAN_ALEM_DETRAN"),
            pl.col("TABELA_FIPE").sum().alias("TABELA_FIPE"),
            (pl.col("TRANSFERENCIA") == "Sim").sum().alias("TRANSFERENCIAS"),
            pl.col("DTA_EXEC").max().alias("DATA"),
        )
        .with_columns(
            (
                pl.col("DEBITO_DETRAN")
                - pl.col("LICENCIAMENTO")
                - pl.col("IPVA")
                - pl.col("MULTA")
                - pl.col("SENATRAN_ALEM_DETRAN")
            ).alias("OUTROS_DEBITOS")
        )
        .drop("SENATRAN_ALEM_DETRAN")
    )
    return custos if mostrar_custo_api else custos.drop("CUSTO_API")


COLUNAS_COMBUSTIVEL = [
    "EMPRESA",
    "PLACA",
    "MODELO",
    "ANO",
    "DATA_HORA",
    "MOTORISTA",
    "ESTABELECIMENTO",
    "CIDADE",
    "SERVICO",
    "QUILOMETRAGEM",
    "KM_RODADOS",
    "LITROS",
    "KM_LITRO",
    "VALOR",
    "VALOR_LITRO",
    "VALOR_KM",
    "CENTRO_CUSTO",
    "CARTAO",
    "RESPONSAVEL",
]


def tabela_combustivel(historico: pl.DataFrame, base: pl.DataFrame) -> pl.DataFrame:
    if historico.is_empty():
        return historico
    placas = set(base["PLACA"].to_list()) if "PLACA" in base.columns else set()
    dado = historico.filter(pl.col("PLACA").is_in(placas))
    dado = dado.with_columns(
        # split_exact/extract em vez de str.split(...).list: o polars do navegador (32 bits)
        # entra em pânico montando a lista com alguns milhares de linhas.
        pl.col("MODELO").str.split_exact(" - ", 1).struct.field("field_0").alias("MODELO"),
        pl.when(pl.col("MODELO").str.contains(" - "))
        .then(pl.col("MODELO").str.extract(r".* - (.*)$", 1))
        .otherwise(pl.lit(None))
        .alias("ANO"),
        pl.when(pl.col("MATRICULA").is_not_null() & (pl.col("MATRICULA") != ""))
        .then(pl.col("MOTORISTA").str.replace(r"^(\S+).* (\S+)$", "${1} ${2}") + pl.lit(" - ") + pl.col("MATRICULA"))
        .otherwise(pl.col("MOTORISTA").str.replace(r"^(\S+).* (\S+)$", "${1} ${2}"))
        .alias("MOTORISTA"),
    )
    dado = dado.with_columns(
        pl.when(pl.col("KM_RODADOS").cast(pl.Float64, strict=False) > 0)
        .then(pl.col("VALOR").cast(pl.Float64, strict=False) / pl.col("KM_RODADOS").cast(pl.Float64, strict=False))
        .otherwise(pl.lit(None))
        .round(2)
        .alias("VALOR_KM")
    )
    return dado.select([c for c in COLUNAS_COMBUSTIVEL if c in dado.columns]).sort(
        "DATA_HORA", descending=True, nulls_last=True
    )
