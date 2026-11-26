from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import polars as pl

from core.compat import ler_parquet  # noqa: E402
from core.config import chave_revenda, chaves_das_revendas
from core.config_arquivo import carregar_json

PASTA_CACHE = Path(__file__).resolve().parent.parent / "data" / "bd_financeiro"
ESTADO = PASTA_CACHE / "virada_app_novo.json"

TABELAS_DA_TELA = {"pagamentos": "revenda", "dados_manuais": "revenda"}

_SUFIXO_PARTE = r"_clone\d*$"


def independente_do_antigo() -> bool:
    return bool((carregar_json("parametros_financeiro") or {}).get("independente_do_antigo"))


def _nomes_oficiais_da_lista(chave: str) -> list[str]:
    from core import revendas as cadastro_revendas
    from core.config import membros_do_grupo

    nomes = (carregar_json("parametros_financeiro") or {}).get(chave) or []
    saida = []
    for nome in nomes:
        for membro in membros_do_grupo(nome) or ([nome] if str(nome).strip() else []):
            oficial = cadastro_revendas.nome_oficial(membro) or membro
            if oficial not in saida:
                saida.append(oficial)
    return saida


def nas_configuracoes() -> list[str]:
    return _nomes_oficiais_da_lista("revendas_no_app_novo")


def sem_o_antigo() -> list[str]:
    return _nomes_oficiais_da_lista("revendas_sem_o_antigo")


def _ler_estado() -> dict:
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def viradas() -> dict[str, datetime]:
    estado = _ler_estado()
    saida = {}
    for revenda in nas_configuracoes():
        quando = next((v for k, v in estado.items() if chave_revenda(k) == chave_revenda(revenda)), None)
        if quando:
            try:
                saida[revenda] = datetime.fromisoformat(quando)
            except ValueError:
                continue
    return saida


def hora_da_virada(revenda: str | None) -> datetime | None:
    if not revenda:
        return None
    pedidas = chaves_das_revendas([revenda])
    horas = {chave_revenda(nome): quando for nome, quando in viradas().items()}
    if not pedidas or not pedidas <= horas.keys():
        return None
    return max(horas[chave] for chave in pedidas)


def virou(revenda: str | None) -> bool:
    return hora_da_virada(revenda) is not None


DESDE_SEMPRE = datetime(2000, 1, 1)


def donas_do_dado() -> dict[str, datetime]:
    donas = {revenda: DESDE_SEMPRE for revenda in sem_o_antigo()}
    donas.update(viradas())
    return donas


def dona_desde(revenda: str | None) -> datetime | None:
    if not revenda:
        return None
    return _hora_pela_revenda_da_url(revenda, {chave_revenda(nome): quando for nome, quando in donas_do_dado().items()})


def e_dona(revenda: str | None) -> bool:
    return dona_desde(revenda) is not None


def _com_chave_e_dia(base: pl.DataFrame, coluna_dia: str) -> pl.DataFrame:
    nomes = [n for n in base["REVENDA"].cast(pl.Utf8).unique().to_list() if n is not None]
    return base.with_columns(
        pl.col("REVENDA")
        .cast(pl.Utf8)
        .replace_strict(nomes, [chave_revenda(n) for n in nomes], default=None, return_dtype=pl.Utf8)
        .alias("_chave"),
        pl.col(coluna_dia).cast(pl.Date).alias("_dia"),
    )


def preferir_retrato_antigo(
    daqui: pl.DataFrame, antigo: pl.DataFrame, coluna_dia: str, coluna_dia_antigo: str | None = None
) -> tuple[pl.DataFrame, pl.DataFrame]:
    if daqui.is_empty() or antigo.is_empty():
        return daqui, antigo
    donas = donas_do_dado()
    viradas_em = pl.DataFrame(
        {"_chave": [chave_revenda(r) for r in donas], "_virada": [q.date() for q in donas.values()]},
        schema={"_chave": pl.Utf8, "_virada": pl.Date},
    )
    d = _com_chave_e_dia(daqui, coluna_dia)
    a = _com_chave_e_dia(antigo, coluna_dia_antigo or coluna_dia)
    no_antigo = a.select("_chave", "_dia").unique().with_columns(pl.lit(True).alias("_no_antigo"))
    fica = (
        d.join(no_antigo, on=["_chave", "_dia"], how="left")
        .join(viradas_em, on="_chave", how="left")
        .filter(pl.col("_no_antigo").is_null() | (pl.col("_virada") <= pl.col("_dia")))
    )
    a = a.join(fica.select("_chave", "_dia").unique(), on=["_chave", "_dia"], how="anti")
    return fica.drop("_chave", "_dia", "_no_antigo", "_virada"), a.drop("_chave", "_dia")


def registrar(revenda: str, quando: datetime) -> None:
    estado = _ler_estado()
    estado[revenda] = quando.isoformat(timespec="seconds")
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    temporario = ESTADO.with_suffix(".tmp")
    temporario.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    temporario.replace(ESTADO)


_cache_ids: dict = {}


def _hora_pela_revenda_da_url(revenda: str, por_chave: dict[str, datetime]) -> datetime | None:
    pedidas = chaves_das_revendas([revenda])
    if not pedidas or not pedidas <= por_chave.keys():
        return None
    return max(por_chave[chave] for chave in pedidas)


def ids_das_donas() -> dict[str, datetime]:
    from core import manual_arquivo

    quando = donas_do_dado()
    if not quando:
        return {}
    arquivos = [PASTA_CACHE / "contas_pagar.parquet", PASTA_CACHE / "pagamentos.parquet"]
    lancados_a_mao = manual_arquivo.PASTA_MANUAL / "entradas_manuais.parquet"
    chave = (
        tuple(sorted((k, v.isoformat()) for k, v in quando.items())),
        *(a.stat().st_mtime_ns if a.is_file() else 0 for a in (*arquivos, lancados_a_mao)),
    )
    if _cache_ids.get("chave") == chave:
        return _cache_ids["ids"]
    por_chave = {chave_revenda(r): dt for r, dt in quando.items()}
    ids: dict[str, datetime] = {}
    for arquivo, coluna in zip(arquivos, ("REVENDA", "revenda")):
        if not arquivo.is_file():
            continue
        try:
            base = ler_parquet(arquivo, columns=[coluna, "id_unico"])
        except Exception:
            continue
        for revenda, ident in base.unique().iter_rows():
            dt = por_chave.get(chave_revenda(revenda or ""))
            if dt is not None and ident:
                ids[str(ident)] = dt
    if lancados_a_mao.is_file():
        try:
            base = ler_parquet(lancados_a_mao, columns=["revenda", "id_unico"])
        except Exception:
            base = pl.DataFrame()
        if not base.is_empty():
            hora_da_revenda = {
                nome: _hora_pela_revenda_da_url(nome, por_chave)
                for nome in base["revenda"].cast(pl.Utf8).unique().to_list()
                if nome
            }
            for revenda, ident in base.unique().iter_rows():
                dt = hora_da_revenda.get(revenda)
                if dt is not None and ident:
                    ids.setdefault(str(ident), dt)
    _cache_ids.update(chave=chave, ids=ids)
    return ids


def ids_da_revenda(revenda: str) -> set[str]:
    alvo = chave_revenda(revenda)
    ids: set[str] = set()
    for arquivo, coluna in (
        (PASTA_CACHE / "contas_pagar.parquet", "REVENDA"),
        (PASTA_CACHE / "pagamentos.parquet", "revenda"),
    ):
        if not arquivo.is_file():
            continue
        try:
            base = ler_parquet(arquivo, columns=[coluna, "id_unico"])
        except Exception:
            continue
        for nome, ident in base.unique().iter_rows():
            if ident and chave_revenda(nome or "") == alvo:
                ids.add(str(ident))
    return ids


def id_base(expressao: pl.Expr) -> pl.Expr:
    return expressao.cast(pl.Utf8).str.replace(_SUFIXO_PARTE, "")
