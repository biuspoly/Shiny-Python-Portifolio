import json
import os
import re
import time
from collections import deque
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl
from loguru import logger

from core.compat import gravar_parquet, ler_parquet

LINHA_LOG = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\s*\|\s*"
    r"(?P<nivel>\w+)\s*\|\s*[^-]+-\s*(?P<mensagem>.*)$"
)
PREFIXO_OTEL = "OTEL "

JANELA_HORAS = 26

MAX_ERROS = 400
MAX_SESSOES = 4000

PASTA_DADOS = Path(__file__).resolve().parents[1] / "data"
ARQUIVO_HORAS = PASTA_DADOS / "historico_horas.parquet"
RETENCAO_DIAS = 30

_POSICOES: dict[str, dict] = {}
_RESUMOS: dict[str, dict] = {}
_DIA = None
_HORAS: dict[tuple[str, str], dict] = {}
_HORAS_SUJO = False
_HORAS_LIDO = False


def _acumular_hora(
    nome_app: str, momento: str, duracao_ms: int | None = None, lenta: bool = False, sessao: bool = False
) -> None:
    global _HORAS_SUJO
    hora = momento[:13]
    if len(hora) < 13:
        return
    linha = _HORAS.get((nome_app, hora))
    if linha is None:
        linha = _HORAS[(nome_app, hora)] = {
            "chamadas": 0,
            "soma_ms": 0,
            "max_ms": 0,
            "lentas": 0,
            "sessoes": 0,
        }
    if duracao_ms is not None:
        linha["chamadas"] += 1
        linha["soma_ms"] += duracao_ms
        linha["max_ms"] = max(linha["max_ms"], duracao_ms)
        if lenta:
            linha["lentas"] += 1
    if sessao:
        linha["sessoes"] += 1
    _HORAS_SUJO = True


def _carregar_horas() -> None:
    global _HORAS_LIDO
    _HORAS_LIDO = True
    if not ARQUIVO_HORAS.exists():
        return
    try:
        for linha in ler_parquet(ARQUIVO_HORAS).iter_rows(named=True):
            _HORAS[(linha["app"], linha["hora"])] = {
                campo: linha[campo] for campo in ("chamadas", "soma_ms", "max_ms", "lentas", "sessoes")
            }
    except Exception as exc:
        logger.warning(f"Historico por hora: {ARQUIVO_HORAS.name} ignorado -- {exc}")


def _gravar_horas() -> None:
    global _HORAS_SUJO
    _HORAS_SUJO = False
    corte = (date.today() - timedelta(days=RETENCAO_DIAS)).isoformat()
    for chave in [c for c in _HORAS if c[1][:10] < corte]:
        del _HORAS[chave]
    if not _HORAS:
        return
    try:
        PASTA_DADOS.mkdir(parents=True, exist_ok=True)
        temporario = PASTA_DADOS / f"tmp_{ARQUIVO_HORAS.name}"
        gravar_parquet(
            pl.DataFrame([{"app": app, "hora": hora, **valores} for (app, hora), valores in sorted(_HORAS.items())]),
            temporario,
        )
        os.replace(temporario, ARQUIVO_HORAS)
    except Exception as exc:
        logger.warning(f"Historico por hora nao gravado -- {exc}")


def historico_por_hora(dias: int) -> pl.DataFrame:
    if not _HORAS_LIDO:
        _carregar_horas()
    esquema = {
        "app": pl.Utf8,
        "hora": pl.Utf8,
        "media_ms": pl.Int64,
        "max_ms": pl.Int64,
        "sessoes": pl.Int64,
        "chamadas": pl.Int64,
    }
    corte = (date.today() - timedelta(days=dias - 1)).isoformat()
    linhas = [
        {
            "app": app,
            "hora": hora,
            "media_ms": round(v["soma_ms"] / v["chamadas"]) if v["chamadas"] else 0,
            "max_ms": v["max_ms"],
            "sessoes": v["sessoes"],
            "chamadas": v["chamadas"],
        }
        for (app, hora), v in _HORAS.items()
        if hora[:10] >= corte
    ]
    if not linhas:
        return pl.DataFrame(schema=esquema)
    return pl.DataFrame(linhas, schema=esquema).sort(["hora", "app"])


def _resumo_do_app(nome: str) -> dict:
    return _RESUMOS.setdefault(
        nome,
        {
            "performance": {},
            "reativa": {},
            "dados": {},
            "erros": deque(maxlen=MAX_ERROS),
            "sessoes": deque(maxlen=MAX_SESSOES),
            "identificadas": {},
        },
    )


def _contar(destino: dict, chave, duracao_ms: int, erro: bool, limite_ms: int) -> None:
    linha = destino.get(chave)
    if linha is None:
        linha = destino[chave] = {"chamadas": 0, "soma_ms": 0, "max_ms": 0, "lentas": 0, "erros": 0}
    linha["chamadas"] += 1
    linha["soma_ms"] += duracao_ms
    linha["max_ms"] = max(linha["max_ms"], duracao_ms)
    if duracao_ms > limite_ms:
        linha["lentas"] += 1
    if erro:
        linha["erros"] += 1


def _arquivos_recentes(pasta_logs: Path) -> list[Path]:
    if not pasta_logs.exists():
        return []
    limite = time.time() - JANELA_HORAS * 3600
    return sorted(p for p in pasta_logs.glob("*.log") if p.stat().st_mtime >= limite)


def _linhas_novas(arquivo: Path):
    chave = str(arquivo)
    estado = _POSICOES.setdefault(chave, {"posicao": 0, "resto": b""})
    tamanho = arquivo.stat().st_size
    if tamanho < estado["posicao"]:
        estado["posicao"] = 0
        estado["resto"] = b""
    if tamanho == estado["posicao"]:
        return []

    with open(arquivo, "rb") as fonte:
        fonte.seek(estado["posicao"])
        bruto = estado["resto"] + fonte.read()
        estado["posicao"] = fonte.tell()

    partes = bruto.split(b"\n")
    estado["resto"] = partes.pop()
    return (parte.decode("utf-8", errors="ignore") for parte in partes)


def _processar(nome_app: str, bruta: str) -> None:
    m = LINHA_LOG.match(bruta)
    if not m:
        return
    resumo = _resumo_do_app(nome_app)
    nivel = m.group("nivel").strip()
    mensagem = m.group("mensagem")
    momento = m.group("timestamp")

    if not mensagem.startswith(PREFIXO_OTEL):
        if nivel in ("WARNING", "ERROR", "CRITICAL"):
            resumo["erros"].append(
                {
                    "app": nome_app,
                    "timestamp": momento,
                    "nivel": nivel,
                    "origem": "log",
                    "onde": "",
                    "mensagem": mensagem,
                    "detalhe": "",
                    "sessao": "",
                }
            )
        return

    try:
        span = json.loads(mensagem[len(PREFIXO_OTEL) :])
    except json.JSONDecodeError:
        return

    tipo = span.get("tipo")
    duracao = span.get("duracao_ms") or 0
    erro = span.get("status") == "ERROR"
    inicio = span.get("inicio") or momento
    nome_span = span.get("nome") or ""

    if tipo == "medir_tempo":
        _contar(resumo["performance"], (span.get("pagina") or "-", nome_span), duracao, erro, 2000)
    elif tipo == "dados":
        _contar(resumo["dados"], (nome_span, span.get("fonte") or "-"), duracao, erro, 1500)
        _acumular_hora(nome_app, inicio, duracao, lenta=duracao > 1500)
    elif tipo == "pipeline":
        _contar(resumo["performance"], ("pipeline", nome_span), duracao, erro, 60000)
    elif tipo == "sessao" or nome_span in ("session_start", "session_end"):
        _registrar_sessao(resumo, nome_app, span, inicio, nome_span)
    elif tipo == "shiny":
        _contar(resumo["reativa"], nome_span, duracao, erro, 2000)

    if erro:
        detalhe = span.get("erro") or {}
        cabecalho = f"Origem no código: {span['codigo']}\n\n" if span.get("codigo") else ""
        resumo["erros"].append(
            {
                "app": nome_app,
                "timestamp": inicio,
                "nivel": "ERROR",
                "origem": tipo or "shiny",
                "onde": nome_span,
                "mensagem": f"{detalhe.get('classe') or ''} {detalhe.get('msg') or ''}".strip(),
                "detalhe": cabecalho + (detalhe.get("stack") or "") + (f"\n\n{span['sql']}" if span.get("sql") else ""),
                "sessao": span.get("sessao") or "",
            }
        )


def _registrar_sessao(resumo: dict, nome_app: str, span: dict, inicio: str, nome_span: str) -> None:
    sessao = span.get("sessao") or ""
    if not sessao:
        return
    conhecido = resumo["identificadas"].setdefault(sessao, {})
    for campo in ("revenda", "usuario"):
        if span.get(campo):
            conhecido[campo] = span[campo]

    if nome_span in ("session_start", "session_end"):
        resumo["sessoes"].append(
            {
                "app": nome_app,
                "timestamp": inicio,
                "evento": "entrou" if nome_span == "session_start" else "saiu",
                "sessao": sessao,
            }
        )
        if nome_span == "session_start":
            _acumular_hora(nome_app, inicio, sessao=True)


def atualizar(apps: list[dict]) -> None:
    global _DIA
    hoje = date.today()
    if _DIA != hoje:
        _RESUMOS.clear()
        _DIA = hoje

    if not _HORAS_LIDO:
        _carregar_horas()

    for app in apps:
        for arquivo in _arquivos_recentes(app["pasta"] / "logs"):
            for bruta in _linhas_novas(arquivo):
                _processar(app["nome"], bruta)

    if _HORAS_SUJO:
        _gravar_horas()


def _tabela(linhas: list[dict], esquema: dict) -> pl.DataFrame:
    return pl.DataFrame(linhas) if linhas else pl.DataFrame(schema=esquema)


def ler_performance() -> pl.DataFrame:
    linhas = [
        {
            "app": nome,
            "pagina": pagina,
            "funcao": funcao,
            "chamadas": c["chamadas"],
            "media_ms": round(c["soma_ms"] / c["chamadas"]),
            "max_ms": c["max_ms"],
            "lentas": c["lentas"],
        }
        for nome, resumo in _RESUMOS.items()
        for (pagina, funcao), c in resumo["performance"].items()
    ]
    return _tabela(
        linhas,
        {
            "app": pl.Utf8,
            "pagina": pl.Utf8,
            "funcao": pl.Utf8,
            "chamadas": pl.Int64,
            "media_ms": pl.Int64,
            "max_ms": pl.Int64,
            "lentas": pl.Int64,
        },
    ).sort("media_ms", descending=True)


def ler_execucao_reativa() -> pl.DataFrame:
    linhas = [
        {
            "app": nome,
            "nome": alvo,
            "chamadas": c["chamadas"],
            "media_ms": round(c["soma_ms"] / c["chamadas"]),
            "max_ms": c["max_ms"],
            "erros": c["erros"],
        }
        for nome, resumo in _RESUMOS.items()
        for alvo, c in resumo["reativa"].items()
    ]
    return _tabela(
        linhas,
        {
            "app": pl.Utf8,
            "nome": pl.Utf8,
            "chamadas": pl.Int64,
            "media_ms": pl.Int64,
            "max_ms": pl.Int64,
            "erros": pl.Int64,
        },
    ).sort("media_ms", descending=True)


def ler_dados() -> pl.DataFrame:
    linhas = [
        {
            "app": nome,
            "canal": canal.replace("dados.", ""),
            "fonte": fonte,
            "chamadas": c["chamadas"],
            "media_ms": round(c["soma_ms"] / c["chamadas"]),
            "max_ms": c["max_ms"],
            "lentas": c["lentas"],
            "erros": c["erros"],
        }
        for nome, resumo in _RESUMOS.items()
        for (canal, fonte), c in resumo["dados"].items()
    ]
    return _tabela(
        linhas,
        {
            "app": pl.Utf8,
            "canal": pl.Utf8,
            "fonte": pl.Utf8,
            "chamadas": pl.Int64,
            "media_ms": pl.Int64,
            "max_ms": pl.Int64,
            "lentas": pl.Int64,
            "erros": pl.Int64,
        },
    ).sort("media_ms", descending=True)


def ler_erros() -> pl.DataFrame:
    linhas = [erro for resumo in _RESUMOS.values() for erro in resumo["erros"]]
    esquema = {
        "app": pl.Utf8,
        "timestamp": pl.Utf8,
        "nivel": pl.Utf8,
        "origem": pl.Utf8,
        "onde": pl.Utf8,
        "mensagem": pl.Utf8,
        "detalhe": pl.Utf8,
        "sessao": pl.Utf8,
    }
    return _tabela(linhas, esquema).sort("timestamp", descending=True)


def ler_sessoes() -> pl.DataFrame:
    linhas = []
    for resumo in _RESUMOS.values():
        for evento in resumo["sessoes"]:
            conhecido = resumo["identificadas"].get(evento["sessao"], {})
            linhas.append(
                {
                    **evento,
                    "revenda": conhecido.get("revenda") or "",
                    "usuario": conhecido.get("usuario") or "",
                }
            )
    esquema = {
        "app": pl.Utf8,
        "timestamp": pl.Utf8,
        "evento": pl.Utf8,
        "sessao": pl.Utf8,
        "revenda": pl.Utf8,
        "usuario": pl.Utf8,
    }
    return _tabela(linhas, esquema).sort("timestamp", descending=True)


def sessoes_por_hora() -> pl.DataFrame:
    base = ler_sessoes().filter(pl.col("evento") == "entrou")
    if base.height == 0:
        return pl.DataFrame(schema={"app": pl.Utf8, "hora": pl.Utf8, "sessoes": pl.Int64})
    return (
        base.with_columns(pl.col("timestamp").str.slice(11, 2).alias("hora"))
        .group_by(["app", "hora"])
        .agg(pl.len().alias("sessoes"))
        .sort(["hora", "app"])
    )


def momento_da_leitura() -> str:
    return datetime.now().strftime("%H:%M:%S")
