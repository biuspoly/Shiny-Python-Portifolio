import re
import unicodedata
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

import cachetools
import polars as pl
from dateutil.relativedelta import relativedelta
from loguru import logger
from sqlalchemy import text

from core import revendas
from core.config_arquivo import carregar_json
from core.db import obter_engine_comodato
from core.parquet import sobrescreve_parquet
from core.telemetria_dados import ler_parquet

from . import dados_pdf_comodato as dados_pdf
from . import devolve_pedido
from . import excecoes_comodato as excecoes
from .informa_comodato import SEM_ANEXO

PASTA_PARQUET = Path(__file__).parents[3] / "data" / "bd_comodato"


COLUNA_PDV = "anexo1"
COLUNA_CONTRATO = "anexo2"
COLUNA_CANHOTO = "anexo3"

DOCUMENTOS_EXIGIDOS_AUTOMATICO = (COLUNA_CONTRATO, COLUNA_CANHOTO)
DOCUMENTOS_EXIGIDOS_MANUAL = (COLUNA_PDV, COLUNA_CONTRATO, COLUNA_CANHOTO)
DOCUMENTOS_EXIGIDOS_EXCECAO = (COLUNA_CONTRATO, COLUNA_CANHOTO)

DIAS_PRAZO_ENVIO = 10
DTE_MINIMA_PRAZO = 20240507
DATA_BASE_PRAZO_ANTIGO = date(2025, 4, 7)

ROTULO_PRAZO_ESGOTADO = "Esgotado"

PERMITE_ENVIO_APOS_PRAZO_COM_CONTRATO = True

FAIXA_PRAZO_FOLGA = "folga"
FAIXA_PRAZO_ATENCAO = "atencao"
FAIXA_PRAZO_CRITICO = "critico"

PRAZO_DIAS_FOLGA = 7
PRAZO_DIAS_ATENCAO = 3

DIAS_CONTRATO_AUTOMATICO = 300

ORIGEM_SOLICITACAO = "Dash"

DIAS_MINIMOS_TERMO = dados_pdf.INTERVALO_MINIMO_DIAS

TIPOS_QUE_BLOQUEIAM_REVENDA = ("Material",)

FAIXA_INTERVALO_MENSAL = "30 dias"
FAIXA_INTERVALO_ANUAL = "1 ano"
FAIXA_INTERVALO_OUTROS = "Outros"
DIAS_INTERVALO_MENSAL = (28, 31)
FAIXAS_INTERVALO = (FAIXA_INTERVALO_MENSAL, FAIXA_INTERVALO_ANUAL, FAIXA_INTERVALO_OUTROS)


def expr_faixa_intervalo(coluna: str = "Intervalo Vencimento") -> pl.Expr:
    dias = pl.col(coluna).cast(pl.Int64, strict=False)
    return (
        pl.when(dias.is_between(*DIAS_INTERVALO_MENSAL))
        .then(pl.lit(FAIXA_INTERVALO_MENSAL))
        .when(dias > DIAS_CONTRATO_AUTOMATICO)
        .then(pl.lit(FAIXA_INTERVALO_ANUAL))
        .otherwise(pl.lit(FAIXA_INTERVALO_OUTROS))
    )


BLOQUEIA_SOLICITACAO_POR_TITULO = True
BLOQUEIA_SOLICITACAO_POR_CADASTRO = True
BLOQUEIA_SOLICITACAO_POR_PRAZO_MATERIAL = True
BLOQUEIA_SOLICITACAO_POR_DOCUMENTACAO = False
BLOQUEIA_SOLICITACAO_POR_CEV_ATIVO = False
LIMITE_CEV_ATIVOS = 5

BLOQUEIA_RECOLHA_SEM_DOCUMENTACAO = False

SITUACAO_PARA_ROTULO = {
    "A": "Processado",
    "P": "Bloqueado",
    "B": "Bloqueado",
}
ROTULO_SEM_REGISTRO = "Bloqueado"
ROTULO_DOCUMENTACAO_INCOMPLETA = "Bloqueado"

_cache = cachetools.LRUCache(maxsize=12)


def _regravar_particoes(nome: str, tabela: pl.DataFrame, coluna_cnpj: str) -> None:
    if tabela.height == 0 or coluna_cnpj not in tabela.columns:
        return
    for chave, parte in tabela.partition_by(coluna_cnpj, as_dict=True).items():
        cnpj = chave[0] if isinstance(chave, tuple) else chave
        if cnpj:
            sobrescreve_parquet(f"{nome}_{cnpj}", parte, PASTA_PARQUET)


def _cnpj_da_revenda(revenda: str | None) -> str | None:
    return revendas.cnpj_da_revenda(revenda)


def _carregar(nome: str, cnpj_rev: str | None = None) -> pl.DataFrame:
    if cnpj_rev:
        parcial = PASTA_PARQUET / f"{nome}_{cnpj_rev}.parquet"
        if parcial.exists():
            chave = (nome, cnpj_rev, parcial.stat().st_mtime)
            if chave not in _cache:
                _cache[chave] = ler_parquet(parcial)
            return _cache[chave]

    caminho = PASTA_PARQUET / f"{nome}.parquet"
    chave = (nome, caminho.stat().st_mtime)
    if chave not in _cache:
        _cache[chave] = ler_parquet(caminho)
    return _cache[chave]


MESES_PT = {
    1: "jan",
    2: "fev",
    3: "mar",
    4: "abr",
    5: "mai",
    6: "jun",
    7: "jul",
    8: "ago",
    9: "set",
    10: "out",
    11: "nov",
    12: "dez",
}


def listar_meses_disponiveis() -> list[str]:
    hoje = date.today()
    mes_atual = date(hoje.year, hoje.month, 1)
    inicio = date(2025, 1, 1)
    meses = []
    cursor = mes_atual
    while cursor >= inicio:
        rotulo = "Mês Atual" if cursor == mes_atual else f"{MESES_PT[cursor.month]}/{cursor.year}"
        meses.append(rotulo)
        cursor -= relativedelta(months=1)
    return meses


def _consultar(sql: str) -> pl.DataFrame:
    with obter_engine_comodato().connect() as conexao:
        return pl.read_database(query=sql, connection=conexao, infer_schema_length=None)


_ENVIO_DA_TELA = "COALESCE(usuario, '') <> ''"

_SQL_ENVIOS_EMAIL = """
    SELECT chave_rev_cev,
           SUM(status_email = 'email enviado') AS envios,
           SUM(status_email = 'email enviado' AND {envio_da_tela}) AS envios_tela,
           COUNT(*) AS tentativas,
           SUBSTRING_INDEX(
               GROUP_CONCAT(
                   CASE WHEN status_email <> 'email enviado' THEN status_email END
                   ORDER BY data_envio DESC SEPARATOR ''
               ), '', 1
           ) AS ultimo_erro
    FROM tb_comod_email
    GROUP BY chave_rev_cev
"""
_SEPARADOR_CHAVE_EMAIL = "|"


def contar_envios_email_por_cev() -> dict[tuple[str, str], dict]:
    criterio_antigo = False
    try:
        resultado = _consultar(_SQL_ENVIOS_EMAIL.format(envio_da_tela=_ENVIO_DA_TELA))
    except Exception as exc:
        logger.warning(f'Comodatos: contagem de envios sem a coluna "usuario" -- {exc}')
        try:
            resultado = _consultar(_SQL_ENVIOS_EMAIL.format(envio_da_tela="FALSE"))
            criterio_antigo = True
        except Exception as exc:
            logger.warning(f"Comodatos: nao deu pra contar os envios de email -- {exc}")
            return {}
    if resultado.height == 0:
        return {}

    contagem: dict[tuple[str, str], dict] = {}
    sem_cnpj: set[str] = set()
    for chave, envios, envios_tela, tentativas, ultimo_erro in resultado.iter_rows():
        revenda, _, cev = str(chave or "").partition(_SEPARADOR_CHAVE_EMAIL)
        if not revenda or not cev:
            continue
        cnpj = _cnpj_da_revenda(str(revenda).strip())
        if not cnpj:
            sem_cnpj.add(str(revenda).strip())
            continue
        chave = (str(cnpj), str(cev).strip())
        atual = contagem.setdefault(chave, {"envios": 0, "envios_tela": 0, "tentativas": 0, "ultimo_erro": ""})
        atual["envios"] += int(envios or 0)
        atual["envios_tela"] += int(envios_tela or 0)
        atual["tentativas"] += int(tentativas or 0)
        if ultimo_erro and not atual["ultimo_erro"]:
            atual["ultimo_erro"] = str(ultimo_erro).strip()
    if criterio_antigo:
        for dados in contagem.values():
            dados["envios_tela"] = max(dados["envios"] - 1, 0)
    if sem_cnpj:
        logger.warning(f"Comodatos: revenda sem CNPJ conhecido em tb_comod_email -- {sorted(sem_cnpj)}")
    return contagem


_SQL_ANEXOS = """
    SELECT a.CNPJ_REV, a.ncev, a.anexo1, a.anexo2, a.anexo3, a.situacao, a.usuario, a.dataI
    FROM tb_anexos_cev a
    JOIN (
        SELECT CNPJ_REV, ncev, MAX(id) AS id
        FROM tb_anexos_cev WHERE situacao <> 'X'
        GROUP BY CNPJ_REV, ncev
    ) ultimo ON ultimo.id = a.id
"""

_COLUNAS_ANEXO = {
    "anexo1": "anexo1",
    "anexo2": "anexo2",
    "anexo3": "anexo3",
    "situacao": "situacao",
    "usuario": "Usuario",
    "dataI": "dataI",
}


def _com_anexos_ao_vivo(base: pl.DataFrame, coluna_cnpj: str, expr_cev: pl.Expr) -> pl.DataFrame:
    if base.height == 0 or coluna_cnpj not in base.columns:
        return base
    presentes = {
        origem: destino
        for origem, destino in _COLUNAS_ANEXO.items()
        if destino in base.columns or origem.startswith("anexo")
    }
    if not presentes:
        return base
    try:
        anexos = _consultar(_SQL_ANEXOS)
    except Exception as exc:
        logger.warning(f"Comodatos: anexos ao vivo indisponiveis, usando o cache -- {exc}")
        return base

    base = base.with_columns(
        pl.col(coluna_cnpj).cast(pl.Utf8).str.strip_chars().alias("_cnpj_anexo"),
        expr_cev.alias("_cev_anexo"),
    ).drop(list(presentes.values()), strict=False)
    if anexos.height == 0:
        return base.with_columns([pl.lit(None, dtype=pl.Utf8).alias(destino) for destino in presentes.values()]).drop(
            "_cnpj_anexo", "_cev_anexo"
        )

    base = base.with_row_index("_ordem_anexo")

    anexos = (
        anexos.with_columns(
            pl.col("CNPJ_REV").cast(pl.Utf8).str.strip_chars().alias("_cnpj_anexo"),
            pl.col("ncev").cast(pl.Utf8).str.strip_chars().alias("_cev_anexo"),
        )
        .select(["_cnpj_anexo", "_cev_anexo", *presentes])
        .rename(presentes)
    )
    if "Usuario" in anexos.columns:
        anexos = anexos.with_columns(nome_de_usuario("Usuario").alias("Usuario"))
    return (
        base.join(anexos, on=["_cnpj_anexo", "_cev_anexo"], how="left")
        .sort("_ordem_anexo")
        .drop("_ordem_anexo", "_cnpj_anexo", "_cev_anexo")
    )


def nome_de_usuario(coluna: str) -> pl.Expr:
    return pl.col(coluna).cast(pl.Utf8).str.replace_all(r"\.", " ").str.to_titlecase()


def _numero_do_cev(coluna: str = "CEV") -> pl.Expr:
    texto = pl.col(coluna).cast(pl.Utf8)
    numero = texto.str.extract(r"-\s*([^\-]+)$", 1).fill_null(texto).str.strip_chars()
    return numero.str.strip_suffix(".0")


def _emoji_se_presente(coluna: str, emoji: str) -> pl.Expr:
    return (
        pl.when(pl.col(coluna).is_not_null())
        .then(pl.lit(emoji))
        .otherwise(pl.lit(""))
        .alias(coluna.replace("anexo", "_emoji_"))
    )


def _data_aaaammdd(coluna: str) -> pl.Expr:
    return pl.col(coluna).cast(pl.Utf8).str.to_date("%Y%m%d", strict=False)


def _expr_corte_contrato_automatico(coluna_cnpj: str = "cnpj") -> pl.Expr:
    corte_por_revenda, corte_padrao = excecoes.corte_prazo_material()
    return (
        pl.col(coluna_cnpj)
        .cast(pl.Utf8)
        .replace_strict(corte_por_revenda, default=corte_padrao, return_dtype=pl.Utf8)
        .str.to_date("%Y%m%d", strict=False)
    )


def _expr_antes_contrato_automatico(coluna_cnpj: str = "cnpj") -> pl.Expr:
    emissao = pl.col("Data Emissão").cast(pl.Utf8).str.replace_all("-", "").str.to_date("%Y%m%d", strict=False)
    return emissao.is_not_null() & (emissao < _expr_corte_contrato_automatico(coluna_cnpj))


def _expr_tem_anexo(coluna: str) -> pl.Expr:
    texto = pl.col(coluna).cast(pl.Utf8).str.strip_chars()
    return texto.is_not_null() & ~texto.str.to_lowercase().is_in(list(SEM_ANEXO))


def expr_cliente_excecao(colunas, coluna_cnpj: str = "cnpj", estrangeiro: bool = False) -> pl.Expr | None:
    coluna_cliente = "Cliente" if "Cliente" in colunas else ("CODCLI" if "CODCLI" in colunas else None)
    if coluna_cnpj not in colunas or coluna_cliente is None:
        return None
    listas = excecoes.estrangeiros_por_revenda() if estrangeiro else excecoes.clientes_livres_por_revenda()
    expressao = None
    for revenda_livre, regras in listas.items():
        cnpj = revendas.cnpj_da_revenda(revenda_livre)
        if not cnpj:
            continue
        quem = None
        if regras.get("clientes"):
            quem = pl.col(coluna_cliente).cast(pl.Utf8).is_in(list(regras["clientes"]))
        if regras.get("vendedores") and "VEN" in colunas:
            por_vendedor = pl.col("VEN").cast(pl.Utf8).is_in(list(regras["vendedores"]))
            quem = por_vendedor if quem is None else (quem | por_vendedor)
        if quem is None:
            continue
        desta = (pl.col(coluna_cnpj).cast(pl.Utf8).str.strip_chars() == cnpj) & quem
        expressao = desta if expressao is None else (expressao | desta)
    return expressao


def _expr_contrato_manual(colunas, coluna_cnpj: str = "cnpj") -> pl.Expr | None:
    partes = []
    if "Data Emissão" in colunas and coluna_cnpj in colunas:
        partes.append(_expr_antes_contrato_automatico(coluna_cnpj).any().over("CEV"))
    if "Intervalo Vencimento" in colunas:
        intervalo = pl.col("Intervalo Vencimento").cast(pl.Int64, strict=False).max().over("CEV")
        partes.append(intervalo.is_null() | (intervalo <= DIAS_CONTRATO_AUTOMATICO))
    excecao = expr_cliente_excecao(colunas, coluna_cnpj)
    if excecao is not None:
        partes.append(excecao.any().over("CEV"))
    estrangeiro = expr_cliente_excecao(colunas, coluna_cnpj, estrangeiro=True)
    if estrangeiro is not None:
        partes.append(estrangeiro.any().over("CEV"))
    if not partes:
        return None
    expressao = partes[0]
    for parte in partes[1:]:
        expressao = expressao | parte
    return expressao


def _todos_entregues(documentos) -> pl.Expr:
    expressao = pl.lit(True)
    for coluna in documentos:
        expressao = expressao & _expr_tem_anexo(coluna)
    return expressao


def _expr_docs_completos(colunas, coluna_cnpj: str = "cnpj") -> pl.Expr:
    if not all(coluna in colunas for coluna in DOCUMENTOS_EXIGIDOS_MANUAL):
        return pl.col("dataI").is_not_null()
    automatico = _todos_entregues(DOCUMENTOS_EXIGIDOS_AUTOMATICO)
    excecao = expr_cliente_excecao(colunas, coluna_cnpj)
    if excecao is not None:
        excecao = excecao.any().over("CEV")
    manual = _expr_contrato_manual(colunas, coluna_cnpj)
    if manual is not None and excecao is not None:
        return (
            pl.when(excecao)
            .then(_todos_entregues(DOCUMENTOS_EXIGIDOS_EXCECAO))
            .when(manual)
            .then(_todos_entregues(DOCUMENTOS_EXIGIDOS_MANUAL))
            .otherwise(automatico)
        )
    if manual is None:
        return automatico
    return pl.when(manual).then(_todos_entregues(DOCUMENTOS_EXIGIDOS_MANUAL)).otherwise(automatico)


def _rotulo_situacao(colunas, coluna_cnpj: str = "cnpj", coluna: str = "situacao") -> pl.Expr:
    rotulo = pl.col(coluna).replace_strict(
        SITUACAO_PARA_ROTULO, default=pl.lit(ROTULO_SEM_REGISTRO), return_dtype=pl.Utf8
    )
    return (
        pl.when(_expr_docs_completos(colunas, coluna_cnpj))
        .then(rotulo)
        .otherwise(pl.lit(ROTULO_DOCUMENTACAO_INCOMPLETA))
    )


def _prazo_input(colunas, coluna_cnpj: str = "cnpj", ignora_especial: bool = False) -> pl.Expr:
    prazo = _expr_prazo_envio(colunas)
    prazo_negativo = prazo < 0
    if ignora_especial and coluna_cnpj in colunas:
        prazo_negativo = prazo_negativo & (pl.col(coluna_cnpj) != excecoes.cnpj_especial())
    return (
        pl.when(_expr_docs_completos(colunas, coluna_cnpj))
        .then(None)
        .when(prazo_negativo)
        .then(pl.lit(ROTULO_PRAZO_ESGOTADO))
        .otherwise(prazo.cast(pl.Utf8) + pl.lit(" dias restantes"))
    )


def _expr_prazo_envio(colunas) -> pl.Expr:
    if "Data Emissão" not in colunas:
        return pl.col("Prazo Envio").cast(pl.Int64, strict=False)
    emissao_texto = pl.col("Data Emissão").cast(pl.Utf8).str.replace_all("-", "")
    emissao = emissao_texto.str.to_date("%Y%m%d", strict=False)
    base = (
        pl.when(emissao_texto.cast(pl.Int64, strict=False) < DTE_MINIMA_PRAZO)
        .then(pl.lit(DATA_BASE_PRAZO_ANTIGO))
        .otherwise(emissao)
    )
    calculado = (DIAS_PRAZO_ENVIO - (pl.lit(date.today()) - base).dt.total_days()).cast(pl.Int64)
    return calculado.fill_null(pl.col("Prazo Envio").cast(pl.Int64, strict=False))


def comod_geral(revenda: str | None) -> pl.DataFrame:
    revenda_up = (revenda or "HOLDING").upper()
    base = _carregar("comod_geral_bruto", _cnpj_da_revenda(revenda))
    if base.height == 0:
        return base
    base = base.filter(pl.col("EMPRESA").str.to_uppercase().str.starts_with(revenda_up)).drop("EMPRESA")
    if base.height == 0:
        return base

    base = _com_anexos_ao_vivo(base, "cnpj", _numero_do_cev("CEV"))

    base = base.with_columns(
        _prazo_input(base.columns, ignora_especial=True).alias("Prazo do Input"),
        _rotulo_situacao(base.columns).alias("Status"),
        pl.when(pl.col("anexo1").is_not_null()).then(pl.lit("\U0001faaa")).otherwise(pl.lit("")).alias("Doc"),
        pl.when(pl.col("anexo2").is_not_null()).then(pl.lit("\U0001f4dc")).otherwise(pl.lit("")).alias("Cev link"),
        pl.when(pl.col("anexo3").is_not_null()).then(pl.lit("\U0001f9fe")).otherwise(pl.lit("")).alias("Canhoto"),
        _data_aaaammdd("Data Emissão").alias("Data Emissão"),
        _data_aaaammdd("Data Vencimento").alias("Data Vencimento"),
    )
    base = base.with_columns(
        pl.col("Status")
        .replace({"Processado": "\u2705", "Análise": "\u2699\ufe0f", "Bloqueado": "\u26d4"})
        .alias("Acao"),
        (
            pl.col("CEV")
            + pl.lit(" - ")
            + pl.col("Fantasia").fill_null("")
            + pl.lit(" - ")
            + pl.col("Razão Social").fill_null("")
            + pl.lit(" - ")
            + pl.col("Cliente").cast(pl.Utf8)
        ).alias("PesquisaCev"),
    )
    return base


def expr_prazo_esgotado() -> pl.Expr:
    dias = pl.col("Prazo do Input").str.extract(r"(-?\d+)").cast(pl.Int64, strict=False)
    esgotado = (pl.col("Prazo do Input") == ROTULO_PRAZO_ESGOTADO) | (dias < 0)
    return esgotado.fill_null(False) & ~_expr_antes_contrato_automatico()


def _linhas_do_cev(base: pl.DataFrame, cev: str) -> pl.DataFrame:
    return base.filter(pl.col("CEV").cast(pl.Utf8) == str(cev))


def mapa_prazo_esgotado(base: pl.DataFrame) -> dict[str, bool]:
    if base.height == 0 or "Prazo do Input" not in base.columns:
        return {}
    agrupado = (
        base.with_columns(expr_prazo_esgotado().alias("_esgotado")).group_by("CEV").agg(pl.col("_esgotado").any())
    )
    return {str(cev): bool(valor) for cev, valor in zip(agrupado["CEV"], agrupado["_esgotado"])}


_RE_DIAS_PRAZO = re.compile(r"-?\d+")


def dias_do_prazo(texto) -> int | None:
    if texto is None:
        return None
    valores = _RE_DIAS_PRAZO.findall(str(texto))
    return min(int(valor) for valor in valores) if valores else None


def faixa_prazo(texto, esgotado: bool = False) -> str | None:
    if esgotado:
        return FAIXA_PRAZO_CRITICO
    conteudo = "" if texto is None else str(texto).strip()
    if not conteudo or conteudo.lower() == "nan":
        return None
    if ROTULO_PRAZO_ESGOTADO in conteudo:
        return FAIXA_PRAZO_CRITICO
    dias = dias_do_prazo(conteudo)
    if dias is None:
        return None
    if dias >= PRAZO_DIAS_FOLGA:
        return FAIXA_PRAZO_FOLGA
    if dias >= PRAZO_DIAS_ATENCAO:
        return FAIXA_PRAZO_ATENCAO
    return FAIXA_PRAZO_CRITICO


def mapa_apos_implantacao(base: pl.DataFrame, coluna_cnpj: str = "cnpj") -> dict[str, bool]:
    if base.height == 0 or "CEV" not in base.columns or "Data Emissão" not in base.columns:
        return {}
    agrupado = (
        base.with_columns((~_expr_antes_contrato_automatico(coluna_cnpj)).alias("_apos"))
        .group_by("CEV")
        .agg(pl.col("_apos").any())
    )
    return {str(cev): bool(valor) for cev, valor in zip(agrupado["CEV"], agrupado["_apos"])}


def mapa_documentacao_completa(base: pl.DataFrame) -> dict[str, bool]:
    if base.height == 0 or "CEV" not in base.columns:
        return {}
    agrupado = (
        base.with_columns(_expr_docs_completos(base.columns).alias("_completa"))
        .group_by("CEV")
        .agg(pl.col("_completa").all())
    )
    return {str(cev): bool(valor) for cev, valor in zip(agrupado["CEV"], agrupado["_completa"])}


def mapa_email_de_assinatura(base: pl.DataFrame) -> dict[str, bool]:
    if base.height == 0 or "CEV" not in base.columns:
        return {}
    manual = _expr_contrato_manual(base.columns)
    automatico = pl.lit(True) if manual is None else ~manual
    if "Intervalo Vencimento" in base.columns:
        intervalo = pl.col("Intervalo Vencimento").cast(pl.Int64, strict=False).max().over("CEV")
        automatico = automatico & intervalo.is_not_null() & (intervalo >= DIAS_MINIMOS_TERMO)
    if "Origem" in base.columns:
        automatico = automatico & (pl.col("Origem") == ORIGEM_SOLICITACAO).any().over("CEV")
    agrupado = base.with_columns(automatico.alias("_email")).group_by("CEV").agg(pl.col("_email").all())
    return {str(cev): bool(valor) for cev, valor in zip(agrupado["CEV"], agrupado["_email"])}


def cev_prazo_esgotado(base: pl.DataFrame, cev: str) -> bool:
    linhas = _linhas_do_cev(base, cev)
    if linhas.height == 0 or "Prazo do Input" not in linhas.columns:
        return False
    return bool(linhas.select(expr_prazo_esgotado().any()).item())


def envio_apos_prazo_liberado(tem_contrato: bool) -> bool:
    return PERMITE_ENVIO_APOS_PRAZO_COM_CONTRATO and tem_contrato


def cev_documentacao_completa(base: pl.DataFrame, cev: str) -> bool:
    linhas = _linhas_do_cev(base, cev)
    if linhas.height == 0:
        return False
    return bool(linhas.select(_expr_docs_completos(linhas.columns).all()).item())


def mapa_recolha_liberada(base: pl.DataFrame) -> dict[str, bool]:
    if not BLOQUEIA_RECOLHA_SEM_DOCUMENTACAO:
        return {}
    completa = mapa_documentacao_completa(base)
    esgotado = mapa_prazo_esgotado(base)
    return {
        str(cev): bool(completa.get(str(cev), False)) or not bool(esgotado.get(str(cev), False))
        for cev in {*completa, *esgotado}
    }


def cev_recolha_liberada(base: pl.DataFrame, cev: str) -> bool:
    if not BLOQUEIA_RECOLHA_SEM_DOCUMENTACAO:
        return True
    return cev_documentacao_completa(base, cev) or not cev_prazo_esgotado(base, cev)


def cev_fluxo_manual(base: pl.DataFrame, cev: str) -> bool:
    linhas = _linhas_do_cev(base, cev)
    if linhas.height == 0:
        return False
    manual = _expr_contrato_manual(linhas.columns)
    if manual is None:
        return True
    return bool(linhas.select(manual.any()).item())


def cev_exige_documento_pdv(base: pl.DataFrame, cev: str) -> bool:
    if not cev_fluxo_manual(base, cev):
        return False
    linhas = _linhas_do_cev(base, cev)
    excecao = expr_cliente_excecao(linhas.columns)
    if excecao is None or linhas.height == 0:
        return True
    return not bool(linhas.select(excecao.any()).item())


DDI_BRASIL = "55"

_SQL_CONTATO_CLIENTE = """
    SELECT PROPRIETARIO, FONE, EMAIL_PROP
    FROM tb_clientes_inad
    WHERE CODCLI = :codcli AND CNPJ_REV = :cnpj_rev
    LIMIT 1
"""


def contato_cliente(codcli, cnpj_rev) -> tuple[str, str, str]:
    if not codcli or not cnpj_rev:
        return "", "", ""
    try:
        with obter_engine_comodato().connect() as conexao:
            linha = (
                conexao.execute(
                    text(_SQL_CONTATO_CLIENTE),
                    {"codcli": str(codcli).strip(), "cnpj_rev": str(cnpj_rev).strip()},
                )
                .mappings()
                .first()
            )
    except Exception as exc:
        logger.warning(f"Comodatos: nao deu pra ler o contato do cliente {codcli} -- {exc}")
        return "", "", ""
    if linha is None:
        return "", "", ""
    return (
        str(linha["PROPRIETARIO"] or "").strip(),
        str(linha["FONE"] or "").strip(),
        str(linha["EMAIL_PROP"] or "").strip(),
    )


def url_whatsapp(fone, mensagem: str = "") -> str:
    digitos = "".join(c for c in str(fone or "") if c.isdigit()).lstrip("0")
    if len(digitos) < 10:
        return ""
    if not digitos.startswith(DDI_BRASIL) or len(digitos) < 12:
        digitos = DDI_BRASIL + digitos
    if len(digitos) > 13:
        return ""
    endereco = f"https://wa.me/{digitos}"
    return f"{endereco}?text={quote(mensagem)}" if mensagem else endereco


PASTA_IMAGENS_PRODUTO = "img/comodatos"

PASTA_FOTOS_PRODUTO = Path(__file__).resolve().parents[3] / "www" / "img" / "comodatos"

_acervo_cache: dict[tuple[int, int], list[tuple[frozenset[str], str]]] = {}
_vocabulario_cache: dict[int, tuple[re.Pattern | None, dict[str, str], frozenset[str]]] = {}


def _vocabulario():
    dados = carregar_json("imagens_comodato", {})
    chave = id(dados)
    if chave not in _vocabulario_cache:
        _vocabulario_cache.clear()
        sinonimos = {str(k).upper(): str(v).upper() for k, v in dados.get("sinonimos", {}).items()}
        termos = sorted(sinonimos, key=lambda t: (-len(t.split()), -len(t)))
        padrao = re.compile(r"\b(?:%s)\b" % "|".join(re.escape(t) for t in termos)) if termos else None
        marcas = frozenset(str(m).upper() for m in dados.get("marcas", []))
        _vocabulario_cache[chave] = (padrao, sinonimos, marcas)
    return _vocabulario_cache[chave]


def _acervo() -> list[tuple[frozenset[str], str]]:
    marcas = _vocabulario()[2]
    try:
        arquivos = sorted(p.name for p in PASTA_FOTOS_PRODUTO.glob("*.webp"))
        versao = round(PASTA_FOTOS_PRODUTO.stat().st_mtime_ns)
    except OSError as exc:
        logger.warning(f"Comodatos: nao consegui listar {PASTA_FOTOS_PRODUTO} -- {exc}")
        return []
    chave = (hash(tuple(arquivos)), versao)
    if chave not in _acervo_cache:
        _acervo_cache.clear()
        acervo = [(frozenset(nome.removesuffix(".webp").upper().split("_")), nome) for nome in arquivos]
        acervo.sort(key=lambda item: (-len(item[0]), not (item[0] & marcas), item[1]))
        _acervo_cache[chave] = acervo
    return _acervo_cache[chave]


@lru_cache(maxsize=4096)
def _palavras(descricao: str, versao: int) -> frozenset[str]:
    texto = "".join(c for c in unicodedata.normalize("NFD", descricao) if unicodedata.category(c) != "Mn").upper()
    texto = re.sub(r"[^0-9A-Z,.]+", " ", texto)
    texto = re.sub(r"(?<=[0-9])(?=[A-Z])|(?<=[A-Z])(?=[0-9])", " ", texto)
    padrao, sinonimos, _ = _vocabulario()
    if padrao is not None:
        texto = padrao.sub(lambda m: sinonimos[m.group(0)], texto)
    return frozenset(p for p in re.split(r"[^0-9A-Z]+", texto) if p)


def imagem_do_produto(produto) -> str:
    descricao = str(produto or "").strip()
    if not descricao:
        return ""
    palavras = _palavras(descricao, id(carregar_json("imagens_comodato", {})))
    for chaves, arquivo in _acervo():
        if chaves <= palavras:
            return f"{PASTA_IMAGENS_PRODUTO}/{quote(arquivo)}"
    return ""


COLUNA_SITUACAO_RECOLHA = "Situação da recolha"
RECOLHA_PEDIDA = "Pedida"
RECOLHA_NAO_PEDIDA = "Não pedida"
COLUNAS_DETALHE_RECOLHA = ("Recolha pedida por", "Recolha pedida em", "Hora da recolha", "Pedido da recolha")


def recolhas_vazias() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "_num_cev": pl.Utf8,
            "Recolha pedida por": pl.Utf8,
            "Recolha pedida em": pl.Date,
            "Hora da recolha": pl.Utf8,
            "Pedido da recolha": pl.Utf8,
        }
    )


def recolhas_geral(revenda: str | None) -> pl.DataFrame:
    revenda_sql = (revenda or "HOLDING").replace("'", "''")
    recolhas = _consultar(f"SELECT * FROM TB_COMOD_RECOLHA WHERE REVENDA LIKE '{revenda_sql}%'")
    if recolhas.height == 0 or "CEV" not in recolhas.columns:
        return recolhas_vazias()
    for coluna in ("USUARIO", "HORA"):
        if coluna not in recolhas.columns:
            recolhas = recolhas.with_columns(pl.lit(None, dtype=pl.Utf8).alias(coluna))
    canceladas = list(_recolhas_canceladas())
    recolhas = recolhas.with_columns(
        pl.col("CEV").cast(pl.Utf8).str.strip_chars().str.strip_suffix(".0").alias("_num_cev"),
        nome_de_usuario("USUARIO").alias("Recolha pedida por"),
        pl.col("DATA").cast(pl.Utf8).str.strptime(pl.Date, "%Y%m%d", strict=False).alias("Recolha pedida em"),
        pl.col("HORA").cast(pl.Utf8).alias("Hora da recolha"),
        pl.col("NPED").cast(pl.Utf8).str.strip_chars().str.strip_suffix(".0").alias("Pedido da recolha"),
    )
    recolhas = recolhas.filter(pl.col("_num_cev").is_not_null() & ~pl.col("Pedido da recolha").is_in(canceladas))
    recolhas = recolhas.sort(["Recolha pedida em", "Hora da recolha", "Pedido da recolha"], nulls_last=False)
    recolhas = recolhas.unique(subset="_num_cev", keep="last", maintain_order=True)
    return recolhas.select(recolhas_vazias().columns)


def _recolhas_canceladas() -> set[str]:
    if not devolve_pedido.garantir_tabela_recolhas_canceladas():
        return set()
    try:
        canceladas = _consultar(f"SELECT NPED FROM {devolve_pedido.TABELA_RECOLHAS_CANCELADAS}")
    except Exception as exc:
        logger.warning(f"Recolhas canceladas indisponiveis -- {exc}")
        return set()
    return {str(valor).removesuffix(".0").strip() for valor in canceladas["NPED"].to_list() if valor}


def adicionar_status_recolha(base: pl.DataFrame, recolhas: pl.DataFrame) -> pl.DataFrame:
    if base.height == 0:
        return base
    numero_cev = (
        pl.col("CEV")
        .cast(pl.Utf8)
        .str.extract(r"-\s*([^\-]+)$", 1)
        .fill_null(pl.col("CEV").cast(pl.Utf8))
        .str.strip_chars()
    )
    pedidas = numero_cev.is_in(recolhas["_num_cev"].to_list())
    colunas = [
        pl.when(pedidas).then(pl.lit("PDF")).otherwise(pl.lit("\u21a9\ufe0f")).alias("Recolha"),
        pl.when(pedidas)
        .then(pl.lit(RECOLHA_PEDIDA))
        .otherwise(pl.lit(RECOLHA_NAO_PEDIDA))
        .alias(COLUNA_SITUACAO_RECOLHA),
    ]
    for coluna in COLUNAS_DETALHE_RECOLHA:
        valor_por_cev = dict(zip(recolhas["_num_cev"].to_list(), recolhas[coluna].to_list()))
        colunas.append(
            numero_cev.replace_strict(valor_por_cev, default=None, return_dtype=recolhas.schema[coluna]).alias(coluna)
        )
    return base.with_columns(colunas)


CAIXA_1L = ["690163", "555001"]
CAIXA_300ML = ["551003", "551002", "551001", "546004", "061007"]
CAIXA_600ML_MAR = ["587003", "587002"]
EMPRESTIMO_BLOQ = ["808002", "808001", "550013", "550012", "550011", "550001"]

REVENDA_PARA_CHAVE_SALDO = {
    "Natal": "Natal",
    "Fortaleza": "Fortaleza",
    "Teresina": "Teresina",
    "São Luís": "São Luís",
}

MANUAL_COMOD_SLUGS = {
    "NATAL": "NATAL",
    "FORTALEZA": "FORTALEZA",
    "TERESINA": "TERESINA",
    "SÃO LUÍS": "SAO_LUIS",
}


def url_manual(revenda: str | None) -> str | None:
    if not revenda:
        return None
    slug = MANUAL_COMOD_SLUGS.get(revenda.upper())
    if not slug:
        return None
    return f"manuais/comodatos/Manual_Comodatos_{slug}.pdf"


FORTES_REVENDAS_ZERAR_QTD = ["230352", "10637", "11162", "230350", "1180003", "9210002", "90150002"]


def produtos_livro_fiscal() -> pl.DataFrame:
    livro = _carregar("saldo_livro_bruto")
    if livro.height == 0:
        return livro
    coluna_produto = next((c for c in livro.columns if c.lower() == "produto"), "PRODUTO")
    alvo = CAIXA_1L + CAIXA_300ML + CAIXA_600ML_MAR + EMPRESTIMO_BLOQ
    return livro.filter(pl.col(coluna_produto).cast(pl.Utf8).is_in(alvo))


def saldo_geral(mes_saldo: str, produtos_filtro: list[str] | None, revenda: str | None = None) -> pl.DataFrame:
    comodatos_geral = _carregar("saldo_comodatos_geral_bruto", _cnpj_da_revenda(revenda))
    comodatos_geral = _com_anexos_ao_vivo(comodatos_geral, "cnpj_rev", _numero_do_cev("CEV"))
    livro = _carregar("saldo_livro_bruto")

    if comodatos_geral.height:
        comodatos_geral = comodatos_geral.with_columns(pl.col("CODCOMP").cast(pl.Utf8))
    if livro.height:
        livro = livro.rename({c: "operacao" for c in livro.columns if c.lower() == "operacao"})
        livro = livro.with_columns(pl.col("PRODUTO").cast(pl.Utf8), pl.col("CLI").cast(pl.Utf8))

    filtro_produto = produtos_filtro or (livro["PRODUTO"].unique().to_list() if livro.height else [])

    if comodatos_geral.height:
        comodatos_geral = comodatos_geral.with_columns(
            _rotulo_situacao(comodatos_geral.columns, "cnpj_rev").alias("situacao"),
            _prazo_input(comodatos_geral.columns, "cnpj_rev").alias("Prazo do Input"),
        )
        comodatos_geral = comodatos_geral.with_columns(
            pl.when(pl.col("Prazo do Input") == ROTULO_PRAZO_ESGOTADO)
            .then(pl.lit("Bloqueado"))
            .otherwise(pl.col("situacao"))
            .alias("situacao")
        )

    if livro.height:
        livro = livro.with_columns(
            pl.when(pl.col("GRUPO_REV").str.contains("Forte") & pl.col("CLI").is_in(FORTES_REVENDAS_ZERAR_QTD))
            .then(pl.lit(0))
            .otherwise(pl.col("QTD"))
            .alias("QTD")
        )

    def _soma(df: pl.DataFrame, operacao: str, produtos: list[str]) -> pl.DataFrame:
        if df.height == 0:
            return pl.DataFrame({"GRUPO_REV": [], "valor": []})
        return (
            df.filter((pl.col("operacao") == operacao) & pl.col("PRODUTO").is_in(produtos))
            .group_by("GRUPO_REV")
            .agg(pl.col("QTD").sum().alias("valor"))
        )

    ano_recolha = _soma(livro, "Dev Emprestimo", filtro_produto).rename({"valor": "Recolha Ano"})
    ano_emprestimo = _soma(livro, "Emprestei", filtro_produto).rename({"valor": "Empréstimo Ano"})
    ano_recolha_600 = _soma(livro, "Dev Emprestimo", EMPRESTIMO_BLOQ).rename({"valor": "Recolha Ano 600ml"})
    ano_emprestimo_600 = _soma(livro, "Emprestei", EMPRESTIMO_BLOQ).rename({"valor": "Empréstimo Ano 600ml"})

    livro_mes = livro.filter(pl.col("MES_ATUAL") == mes_saldo) if livro.height else livro
    mes_recolha = _soma(livro_mes, "Dev Emprestimo", filtro_produto).rename({"valor": "Recolha Mês"})
    mes_emprestimo = _soma(livro_mes, "Emprestei", filtro_produto).rename({"valor": "Empréstimo Mês"})

    situacao_doc = (
        comodatos_geral.filter(pl.col("situacao") == "Bloqueado", pl.col("CODCOMP").is_in(filtro_produto))
        .group_by("Revenda")
        .agg(pl.lit("Bloqueado").alias("Status Doc"))
        if comodatos_geral.height
        else pl.DataFrame({"Revenda": [], "Status Doc": []})
    )
    if situacao_doc.height:
        situacao_doc = situacao_doc.with_columns(pl.col("Revenda"))

    df = pl.DataFrame({"Nome": list(REVENDA_PARA_CHAVE_SALDO.keys())})
    df = df.with_columns(pl.col("Nome").replace(REVENDA_PARA_CHAVE_SALDO).alias("Chave"))
    for tabela, chave in [
        (ano_recolha, "Nome"),
        (ano_emprestimo, "Nome"),
        (ano_recolha_600, "Nome"),
        (ano_emprestimo_600, "Nome"),
        (mes_recolha, "Nome"),
        (mes_emprestimo, "Nome"),
    ]:
        if tabela.height:
            df = df.join(tabela.rename({"GRUPO_REV": chave}), on=chave, how="left")
    if situacao_doc.height:
        df = df.join(situacao_doc.rename({"Revenda": "Chave"}), on="Chave", how="left")

    for coluna in [
        "Recolha Ano",
        "Empréstimo Ano",
        "Recolha Ano 600ml",
        "Empréstimo Ano 600ml",
        "Recolha Mês",
        "Empréstimo Mês",
    ]:
        if coluna not in df.columns:
            df = df.with_columns(pl.lit(0).alias(coluna))
        else:
            df = df.with_columns(pl.col(coluna).fill_null(0))
    df = df.with_columns(
        (pl.col("Recolha Ano") - pl.col("Empréstimo Ano")).alias("Saldo Ano"),
        (pl.col("Recolha Mês") - pl.col("Empréstimo Mês")).alias("Saldo Mês"),
    )

    so_mar = all(p in CAIXA_600ML_MAR for p in filtro_produto) if filtro_produto else False
    so_600 = all(p in EMPRESTIMO_BLOQ for p in filtro_produto) if filtro_produto else False
    if so_mar:
        df = df.with_columns(
            (
                (pl.col("Saldo Ano") + ((pl.col("Recolha Ano 600ml") - pl.col("Empréstimo Ano 600ml")) / 5).floor()) > 0
            ).alias("_disponivel")
        )
    else:
        df = df.with_columns((pl.col("Saldo Ano") > 0).alias("_disponivel"))
    df = df.with_columns(
        pl.when(pl.col("_disponivel")).then(pl.lit("Disponível")).otherwise(pl.lit("Bloqueado")).alias("Status PLP")
    ).drop("_disponivel", "Recolha Ano 600ml", "Empréstimo Ano 600ml")

    if "Status Doc" not in df.columns:
        df = df.with_columns(pl.lit(None).alias("Status Doc"))
    df = df.with_columns(pl.col("Status Doc").fill_null("Disponível"))
    if so_600:
        df = df.with_columns(pl.lit("Bloqueado").alias("Status Doc"), pl.lit("Bloqueado").alias("Status PLP"))

    consolidado = (
        (
            livro.filter(pl.col("PRODUTO").is_in(CAIXA_1L + CAIXA_300ML + EMPRESTIMO_BLOQ + CAIXA_600ML_MAR))
            .group_by("GRUPO_REV")
            .agg(
                pl.col("QTD")
                .filter((pl.col("operacao") == "Dev Emprestimo") & pl.col("PRODUTO").is_in(CAIXA_1L))
                .sum()
                .alias("_r1l"),
                pl.col("QTD")
                .filter((pl.col("operacao") == "Emprestei") & pl.col("PRODUTO").is_in(CAIXA_1L))
                .sum()
                .alias("_e1l"),
                pl.col("QTD")
                .filter((pl.col("operacao") == "Dev Emprestimo") & pl.col("PRODUTO").is_in(CAIXA_300ML))
                .sum()
                .alias("_r300"),
                pl.col("QTD")
                .filter((pl.col("operacao") == "Emprestei") & pl.col("PRODUTO").is_in(CAIXA_300ML))
                .sum()
                .alias("_e300"),
                pl.col("QTD")
                .filter((pl.col("operacao") == "Dev Emprestimo") & pl.col("PRODUTO").is_in(EMPRESTIMO_BLOQ))
                .sum()
                .alias("_r600"),
                pl.col("QTD")
                .filter((pl.col("operacao") == "Emprestei") & pl.col("PRODUTO").is_in(EMPRESTIMO_BLOQ))
                .sum()
                .alias("_e600"),
                pl.col("QTD")
                .filter((pl.col("operacao") == "Dev Emprestimo") & pl.col("PRODUTO").is_in(CAIXA_600ML_MAR))
                .sum()
                .alias("_r600hnk"),
                pl.col("QTD")
                .filter((pl.col("operacao") == "Emprestei") & pl.col("PRODUTO").is_in(CAIXA_600ML_MAR))
                .sum()
                .alias("_e600hnk"),
            )
            .with_columns(
                (pl.col("_r1l") - pl.col("_e1l")).alias("Caixa 1L"),
                (pl.col("_r300") - pl.col("_e300")).alias("Caixa 300"),
                (pl.col("_r600hnk") - pl.col("_e600hnk") + ((pl.col("_r600") - pl.col("_e600")) / 5).floor()).alias(
                    "Total MAR 600"
                ),
                (pl.col("_r600hnk") - pl.col("_e600hnk")).alias("Caixa MAR 600"),
                ((pl.col("_r600") - pl.col("_e600")) / 5).floor().alias("Bônus MAR 600"),
                (pl.col("_r600") - pl.col("_e600")).alias("Caixa 600ml"),
            )
            .select(
                "GRUPO_REV", "Caixa 1L", "Caixa 300", "Total MAR 600", "Caixa MAR 600", "Bônus MAR 600", "Caixa 600ml"
            )
        )
        if livro.height
        else pl.DataFrame({"GRUPO_REV": []})
    )

    if consolidado.height:
        df = df.join(consolidado.rename({"GRUPO_REV": "Nome"}), on="Nome", how="left")
    for coluna in ["Caixa 1L", "Caixa 300", "Total MAR 600", "Caixa MAR 600", "Bônus MAR 600", "Caixa 600ml"]:
        if coluna not in df.columns:
            df = df.with_columns(pl.lit(0).alias(coluna))
        else:
            df = df.with_columns(pl.col(coluna).fill_null(0))

    df = df.sort("Nome").select(
        "Nome",
        "Recolha Ano",
        "Empréstimo Ano",
        "Saldo Ano",
        "Recolha Mês",
        "Empréstimo Mês",
        "Saldo Mês",
        "Status PLP",
        "Status Doc",
        "Caixa 1L",
        "Caixa 300",
        "Total MAR 600",
        "Caixa MAR 600",
        "Bônus MAR 600",
        "Caixa 600ml",
    )
    return df


NOME_PARQUET_TITULOS = "clientes_inadimplentes_titulos_bruto"


def sem_a_propria_revenda(titulos: pl.DataFrame) -> pl.DataFrame:
    if "CHAVE" not in titulos.columns or "CNPJ_REV" not in titulos.columns:
        return titulos
    documento = (
        pl.col("CHAVE").cast(pl.Utf8).fill_null("").str.replace(r"\.0$", "").str.replace_all(r"\D", "").str.zfill(14)
    )
    return titulos.filter(documento != pl.col("CNPJ_REV").cast(pl.Utf8).fill_null("").str.zfill(14))


def clientes_inadimplentes(
    revenda: str | None = None, supremo: bool = False, solicita_sem_bloqueio: bool = False
) -> pl.DataFrame:
    cnpj_particao = _cnpj_da_revenda(revenda)
    base = _carregar("clientes_inadimplentes_base_bruto", cnpj_particao)
    base = _com_anexos_ao_vivo(base, "cnpj_rev", _numero_do_cev("CEV"))
    titulos = _carregar(NOME_PARQUET_TITULOS, cnpj_particao)
    if titulos.height == 0:
        return titulos
    titulos = sem_a_propria_revenda(titulos)

    if base.height:
        base = base.with_columns(_rotulo_situacao(base.columns, "cnpj_rev").alias("situacao"))

        cev_por_cliente = base.group_by("CHAVE_CLI").agg(pl.col("CEV").n_unique().alias("Status CEV"))
        doc_por_cliente = (
            base.filter(pl.col("situacao") == "Bloqueado")
            .group_by("CHAVE_CLI")
            .agg(pl.lit("Bloqueado").alias("Status Doc"))
        )
        titulos = titulos.join(doc_por_cliente, on="CHAVE_CLI", how="left")
        titulos = titulos.join(cev_por_cliente, on="CHAVE_CLI", how="left")

        corte_por_revenda, corte_padrao = excecoes.corte_prazo_material()
        bloqueio_material = (
            base.with_columns(
                _prazo_input(base.columns, "cnpj_rev").alias("Prazo do Input"),
                _data_aaaammdd("Data Emissão").alias("_data_emissao"),
            )
            .with_columns(
                pl.col("cnpj_rev")
                .replace_strict(corte_por_revenda, default=corte_padrao, return_dtype=pl.Utf8)
                .str.to_date("%Y%m%d")
                .alias("_corte")
            )
            .filter(
                (pl.col("Prazo do Input") == ROTULO_PRAZO_ESGOTADO)
                & pl.col("TIPO").is_in(list(TIPOS_QUE_BLOQUEIAM_REVENDA))
                & (pl.col("_data_emissao") >= pl.col("_corte"))
            )
            .group_by("cnpj_rev")
            .agg(pl.len().alias("Prazos Esgotados Material"))
        )
        titulos = titulos.join(bloqueio_material.rename({"cnpj_rev": "CNPJ_REV"}), on="CNPJ_REV", how="left")
    else:
        titulos = titulos.with_columns(
            pl.lit(None).alias("Status Doc"),
            pl.lit(None).alias("Status CEV"),
            pl.lit(None).alias("Prazos Esgotados Material"),
        )

    titulos = titulos.with_columns(
        pl.col("Status Doc").fill_null("Disponível"),
        pl.when(pl.col("Status CEV").is_null() | (pl.col("Status CEV") <= LIMITE_CEV_ATIVOS))
        .then(pl.lit("Disponível"))
        .otherwise(pl.lit("Bloqueado"))
        .alias("Status CEV"),
        pl.when(pl.col("Inadimplente") == "Sim")
        .then(pl.lit("Bloqueado"))
        .otherwise(pl.lit("Disponível"))
        .alias("Status Tit"),
        (
            pl.when(
                (pl.col("PROPRIETARIO").str.strip_chars() == "")
                | pl.col("PROPRIETARIO").is_null()
                | (pl.col("CPF_PROP").cast(pl.Utf8) == "0")
                | pl.col("CPF_PROP").is_null()
                | (pl.col("FONE").cast(pl.Utf8) == "0")
                | pl.col("FONE").is_null()
                | (pl.col("EMAIL_PROP").str.strip_chars() == "")
                | pl.col("EMAIL_PROP").is_null()
            )
            .then(pl.lit("Bloqueado"))
            .otherwise(pl.lit("Disponível"))
        ).alias("Status Cad"),
    )

    condicoes = [
        (BLOQUEIA_SOLICITACAO_POR_TITULO, pl.col("Status Tit") == "Disponível"),
        (BLOQUEIA_SOLICITACAO_POR_CADASTRO, pl.col("Status Cad") == "Disponível"),
        (BLOQUEIA_SOLICITACAO_POR_PRAZO_MATERIAL, pl.col("Prazos Esgotados Material").is_null()),
        (BLOQUEIA_SOLICITACAO_POR_DOCUMENTACAO, pl.col("Status Doc") == "Disponível"),
        (BLOQUEIA_SOLICITACAO_POR_CEV_ATIVO, pl.col("Status CEV") == "Disponível"),
    ]
    liberado = pl.lit(True)
    for ligada, condicao in condicoes:
        if ligada:
            liberado = liberado & condicao
    titulos = titulos.with_columns(
        pl.when(liberado).then(pl.lit("\u2795")).otherwise(pl.lit("\u26d4")).alias("Solicitacao")
    )

    livre = pl.lit(False)
    for revenda_livre, regras in excecoes.clientes_livres_por_revenda().items():
        condicao = pl.lit(False)
        if regras.get("vendedores"):
            condicao = condicao | pl.col("VEN").cast(pl.Utf8).is_in(regras["vendedores"])
        if regras.get("clientes"):
            condicao = condicao | pl.col("CODCLI").cast(pl.Utf8).is_in(regras["clientes"])
        livre = livre | ((pl.col("REVENDA") == revenda_livre) & condicao)
    if supremo:
        livre = pl.lit(True)
    estrangeiro = pl.lit(False)
    for revenda_estrangeiro, regras in excecoes.estrangeiros_por_revenda().items():
        condicao = pl.lit(False)
        if regras.get("vendedores"):
            condicao = condicao | pl.col("VEN").cast(pl.Utf8).is_in(regras["vendedores"])
        if regras.get("clientes"):
            condicao = condicao | pl.col("CODCLI").cast(pl.Utf8).is_in(regras["clientes"])
        estrangeiro = estrangeiro | ((pl.col("REVENDA") == revenda_estrangeiro) & condicao)
    titulos = titulos.with_columns(
        pl.when(livre).then(pl.lit("\u2795")).otherwise(pl.col("Solicitacao")).alias("Solicitacao"),
        (livre | estrangeiro).alias("SEM_DOC"),
    )
    if solicita_sem_bloqueio:
        titulos = titulos.with_columns(pl.lit("\u2795").alias("Solicitacao"))
    titulos = titulos.with_columns((pl.col("CODCLI").cast(pl.Utf8) + pl.lit(" - ") + pl.col("NOME")).alias("COD_RS"))
    titulos = titulos.with_columns(
        pl.when(pl.col("Solicitacao") == "\u2795").then(pl.lit("Sim")).otherwise(pl.lit("Não")).alias("Solic Liberada")
    )
    return titulos


def produtos_solicita(cnpj_rev: str) -> pl.DataFrame:
    produtos = _carregar("produtos_cev_bruto").filter(pl.col("CNPJ_REV") == cnpj_rev)
    if produtos.height == 0:
        return produtos
    return produtos.with_columns(
        pl.col("CODCOMP").cast(pl.Int64).cast(pl.Utf8),
        (
            pl.col("CODRED").cast(pl.Int64).cast(pl.Utf8)
            + pl.lit(" - ")
            + pl.col("PRODUTO_GENERICO").str.to_titlecase()
        ).alias("CODPROD"),
        pl.when(pl.col("STATUS_DLP") == "Bloqueado")
        .then(pl.lit("Disponível"))
        .otherwise(pl.col("STATUS_DLP"))
        .alias("STATUS_DLP"),
    )


NOME_PARQUET_SOLICITADO = "comod_solicitado_bruto"

_CHAVES_SOLICITADO = [
    "REVENDA",
    "CLIENTE",
    "CNPJ",
    "USUARIO",
    "PRODUTO",
    "CODCOMP",
    "UNIDADE",
    "PRECO",
    "TIPO",
    "TAB_CEV",
    "VEN",
    "ENDERECO",
    "CONTATO",
    "PTO_REF",
    "DIA_VISIT",
    "SEQ",
    "CEP",
    "FONE",
    "DATA",
    "VENC",
    "PRAZO",
    "PRE_PED",
]


def regravar_parquet_solicitacoes() -> int:
    """Portfólio: a gravação já foi no .parquet (banco_memoria); só esquece o que estava em cache."""
    _cache.clear()
    return _carregar(NOME_PARQUET_SOLICITADO).height


def regravar_parquet_titulos() -> int:
    _cache.clear()
    return _carregar(NOME_PARQUET_TITULOS).height


def comod_solicitados(revenda: str | None) -> pl.DataFrame:
    solicitacoes = _carregar(NOME_PARQUET_SOLICITADO)
    if solicitacoes.height == 0:
        return solicitacoes
    solicitacoes = solicitacoes.filter(pl.col("PRAZO").is_not_null() & pl.col("PRE_PED").is_null())
    return _da_revenda_somando_qtd(solicitacoes, revenda)


def _da_revenda_somando_qtd(solicitacoes: pl.DataFrame, revenda: str | None) -> pl.DataFrame:
    if not revenda or revenda == "HOLDING" or solicitacoes.height == 0:
        return solicitacoes
    solicitacoes = solicitacoes.filter(pl.col("REVENDA").cast(pl.Utf8).str.to_uppercase() == revenda.upper())
    if solicitacoes.height == 0:
        return solicitacoes
    chaves = [c for c in _CHAVES_SOLICITADO if c in solicitacoes.columns]
    return solicitacoes.group_by(chaves, maintain_order=True).agg(pl.col("QTD").sum().alias("QTD"))


DIAS_PRE_PEDIDO_VISIVEL = 10

_TAMANHO_PRE_PEDIDO = 12


def comod_pre_pedidos(revenda: str | None) -> pl.DataFrame:
    solicitacoes = _carregar(NOME_PARQUET_SOLICITADO)
    if solicitacoes.height == 0:
        return solicitacoes
    numero = pl.col("PRE_PED").cast(pl.Int64, strict=False).cast(pl.Utf8)
    corte = (date.today() - timedelta(days=DIAS_PRE_PEDIDO_VISIVEL)).strftime("%Y%m%d")
    solicitacoes = solicitacoes.filter(
        pl.col("PRAZO").is_not_null()
        & numero.is_not_null()
        & (numero.str.len_chars() == _TAMANHO_PRE_PEDIDO)
        & (numero.str.slice(0, 8) >= corte)
    ).with_columns(numero.alias("PRE_PED"))
    solicitacoes = _sem_os_que_o_control_ja_validou(solicitacoes, revenda)
    return _da_revenda_somando_qtd(solicitacoes, revenda)


def _sem_os_que_o_control_ja_validou(solicitacoes: pl.DataFrame, revenda: str | None) -> pl.DataFrame:
    if solicitacoes.height == 0:
        return solicitacoes
    from . import cancela_pre_pedido

    fechados = cancela_pre_pedido.pre_pedidos_fechados(revenda)
    if not fechados:
        return solicitacoes
    chave = (
        pl.col("REVENDA").cast(pl.Utf8).str.to_uppercase()
        + pl.lit("|")
        + pl.col("PRE_PED").cast(pl.Utf8)
        + pl.lit("|")
        + pl.col("CLIENTE").cast(pl.Utf8)
    )
    return solicitacoes.filter(~chave.is_in([f"{r}|{n}|{c}" for r, n, c in fechados]))


def detalhes_cli_inad(chave_cli: str) -> pl.DataFrame:
    chave_sql = chave_cli.replace("'", "''")
    return _consultar(f"""
        SELECT
             C.CEV,
             C.CODCOMP AS `Código`,
             c.PRODUTO_GENERICO AS Produto,
             c.QTD AS Qtd,
             c.DTE AS DT,
             c.DTV AS VENC
        FROM TB_COMODATO C
        WHERE CONCAT(CODCLI, CNPJ_REV) = '{chave_sql}'
    """)
