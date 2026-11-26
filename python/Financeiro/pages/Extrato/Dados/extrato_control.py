"""O movimento dos bancos de cada revenda, do cache (data/bd_extrato/<cnpj>/). No original,
a consulta ao ERP grava este cache; no portfólio ele já vem gerado."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl

from core.compat import gravar_parquet, ler_parquet

PASTA_CACHE = Path(__file__).resolve().parents[3] / "data" / "bd_extrato"

MESES_JANELA = 6
DIAS_MAXIMOS_ATRAS = 366


def _pasta(cnpj: str) -> Path:
    return PASTA_CACHE / "".join(ch for ch in str(cnpj) if ch.isdigit())


def _aaaammdd(valor) -> date | None:
    try:
        texto = str(int(valor or 0))
        return datetime.strptime(texto, "%Y%m%d").date() if len(texto) == 8 else None
    except (TypeError, ValueError):
        return None


def janela_padrao(hoje: date | None = None) -> date:
    hoje = hoje or date.today()
    meses = hoje.year * 12 + hoje.month - 1 - MESES_JANELA
    return date(meses // 12, meses % 12 + 1, 1)


def data_da_baixa(lmo) -> date | None:
    texto = "".join(ch for ch in str(lmo or "") if ch.isdigit())
    try:
        return datetime.strptime(texto, "%d%m%Y").date() if len(texto) == 8 else None
    except ValueError:
        return None


ARQUIVO_CATALOGO = "catalogo.json"
VALIDADE_CATALOGO = timedelta(days=1)


def montar_catalogo(linhas, rotulos: dict[str, str]) -> dict:
    bancos, usuarios, contagem = set(), set(), {}
    for banco, usuario, hp, historico, quantas in linhas:
        if banco is not None:
            bancos.add(int(banco))
        if usuario:
            usuarios.add(usuario)
        if hp is not None:
            por_hp = contagem.setdefault(int(hp), {})
            texto = " ".join(str(historico or "").split())
            por_hp[texto] = por_hp.get(texto, 0) + int(quantas or 1)
    hps = {}
    for hp in sorted(contagem):
        if hp == 0:
            hps["0"] = "0 - (sem histórico padrão)"
            continue
        mais_comum = max(sorted(contagem[hp]), key=contagem[hp].get)
        hps[str(hp)] = f"{hp} - {mais_comum}" if mais_comum else str(hp)
    return {
        "bancos": {str(b): rotulos.get(str(b)) or str(b) for b in sorted(bancos)},
        "usuarios": sorted(usuarios),
        "hps": hps,
        "atualizado_em": datetime.now().isoformat(timespec="seconds"),
    }


def catalogo_do_movimento(base: pl.DataFrame, rotulos: dict[str, str]) -> dict:
    if base.is_empty():
        return montar_catalogo([], rotulos)
    agrupado = base.group_by("banco", "usuario", "hp", "historico").len()
    return montar_catalogo(agrupado.iter_rows(), rotulos)


def gravar_catalogo(cnpj: str, catalogo: dict) -> None:
    pasta = _pasta(cnpj)
    pasta.mkdir(parents=True, exist_ok=True)
    temporario = pasta / f"{ARQUIVO_CATALOGO}.tmp"
    temporario.write_text(json.dumps(catalogo, ensure_ascii=False), encoding="utf-8")
    temporario.replace(pasta / ARQUIVO_CATALOGO)


def ler_catalogo(cnpj: str | None) -> dict | None:
    try:
        return json.loads((_pasta(cnpj) / ARQUIVO_CATALOGO).read_text(encoding="utf-8")) if cnpj else None
    except Exception:
        return None


def momento_catalogo(cnpj: str | None) -> int | None:
    try:
        return (_pasta(cnpj) / ARQUIVO_CATALOGO).stat().st_mtime_ns if cnpj else None
    except OSError:
        return None


def catalogo_velho(cnpj: str | None, agora: datetime | None = None) -> bool:
    catalogo = ler_catalogo(cnpj)
    if not catalogo or not catalogo.get("atualizado_em"):
        return True
    try:
        return (agora or datetime.now()) - datetime.fromisoformat(catalogo["atualizado_em"]) > VALIDADE_CATALOGO
    except ValueError:
        return True


def opcoes_dos_filtros(catalogo: dict | None, base: pl.DataFrame, info: dict | None) -> dict[str, dict]:
    catalogo = catalogo or {}
    do_cache = catalogo_do_movimento(base, (info or {}).get("bancos") or {}) if not base.is_empty() else {}
    bancos = {**(catalogo.get("bancos") or {}), **(do_cache.get("bancos") or {})}
    hps = {**(catalogo.get("hps") or {}), **(do_cache.get("hps") or {})}
    usuarios = sorted(set(catalogo.get("usuarios") or []) | set(do_cache.get("usuarios") or []))

    def _por_numero(escolhas: dict) -> dict:
        def ordem(chave: str):
            return (0, int(chave), "") if chave.isdigit() else (1, 0, chave)

        return {k: escolhas[k] for k in sorted(escolhas, key=ordem)}

    return {
        "banco": {"": "Todos", **_por_numero(bancos)},
        "usuario": {"": "Todos", **{u: u for u in usuarios}},
        "hp": {"": "Todos", **_por_numero(hps)},
    }


def aplicar_baixa(cnpj: str, linhas, lmo: str | None) -> int:
    base, info = ler_movimento(cnpj)
    if base.is_empty() or not info:
        return 0
    chaves = pl.DataFrame(
        [[int(b), int(d), str(doc), str(v)] for b, d, doc, v in linhas],
        schema={"banco": pl.Int64, "dtl": pl.Int64, "doc_control": pl.Utf8, "valor_control": pl.Utf8},
        orient="row",
    ).unique()
    marcadas = base.join(
        chaves.with_columns(pl.lit(True).alias("_baixada")),
        on=["banco", "dtl", "doc_control", "valor_control"],
        how="left",
    )["_baixada"].is_not_null()
    base = base.with_columns(pl.when(marcadas).then(pl.lit(lmo or "")).otherwise(pl.col("lmo")).alias("lmo"))
    _gravar(cnpj, base, {**info, "baixa_em": datetime.now().isoformat(timespec="seconds")})
    return int(marcadas.sum())


def _gravar(cnpj: str, base: pl.DataFrame, info: dict) -> None:
    pasta = _pasta(cnpj)
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, gravar in (
        ("movimento.parquet", lambda p: gravar_parquet(base, p)),
        ("movimento.json", lambda p: p.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")),
    ):
        temporario = pasta / f"{nome}.tmp"
        gravar(temporario)
        temporario.replace(pasta / nome)


def ler_info(cnpj: str | None) -> dict | None:
    try:
        return json.loads((_pasta(cnpj) / "movimento.json").read_text(encoding="utf-8")) if cnpj else None
    except Exception:
        return None


def momento_cache(cnpj: str | None) -> int | None:
    try:
        return (_pasta(cnpj) / "movimento.json").stat().st_mtime_ns if cnpj else None
    except OSError:
        return None


def ler_movimento(cnpj: str | None) -> tuple[pl.DataFrame, dict | None]:
    info = ler_info(cnpj)
    try:
        return (ler_parquet(_pasta(cnpj) / "movimento.parquet"), info) if info else (pl.DataFrame(), None)
    except Exception:
        return pl.DataFrame(), None
