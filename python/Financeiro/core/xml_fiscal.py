from __future__ import annotations

import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(
        0,
        str(
            Path(globals()["__file__"]).resolve().parents[1]
            if "__file__" in globals()
            else next(
                (
                    p
                    for p in (Path.cwd(), Path.cwd() / "Acompanhamento Financeiro")
                    if (p / "core" / "config_arquivo.py").is_file()
                ),
                Path.cwd(),
            )
        ),
    )

import polars as pl
from dotenv import load_dotenv
from lxml import etree

from core.compat import ler_parquet  # noqa: E402

_PASTA_APP = Path(__file__).resolve().parents[1]
TIPOS = ("nfe", "nfse", "cte")


class SemAcervo(Exception):
    """O caminho do indice ou do acervo nao esta' no .env, ou nao existe."""


def _pasta(variavel: str) -> Path:
    load_dotenv(dotenv_path=_PASTA_APP / ".env", override=False)
    texto = os.getenv(variavel, "").strip().strip('"')
    if not texto:
        raise SemAcervo(f"{variavel} nao esta' no .env")
    pasta = Path(texto) if Path(texto).is_absolute() else (_PASTA_APP / texto).resolve()
    if not pasta.is_dir():
        raise SemAcervo(f"{variavel} aponta para uma pasta que nao existe ({pasta})")
    return pasta


def pasta_do_indice() -> Path:
    return _pasta("FISCAL_INDICE_PASTA")


def pasta_do_acervo() -> Path:
    return _pasta("ACERVO_PASTA")


def indice(tipo: str, empresas: list[str], desde: date) -> pl.DataFrame:
    arquivo = pasta_do_indice() / f"{tipo}.parquet"
    if not arquivo.is_file():
        return pl.DataFrame()
    return (
        ler_parquet(arquivo)
        .lazy()
        .filter(pl.col("empresa").is_in(list(empresas)) & (pl.col("emissao").cast(pl.Date) >= desde))
        .collect()
    )


def caminho(relativo: str) -> Path:
    raiz = pasta_do_acervo().resolve()
    alvo = (raiz / str(relativo)).resolve()
    if raiz not in alvo.parents:
        raise ValueError(f"caminho fora do acervo: {relativo}")
    return alvo


def ler(relativo: str) -> str:
    return caminho(relativo).read_bytes().decode("utf-8", errors="replace")


def duplicatas(xml: str) -> list[dict]:
    raiz = etree.fromstring(xml.encode("utf-8"))
    saida = []
    for dup in raiz.xpath("//*[local-name()='cobr']/*[local-name()='dup']"):
        campos = {etree.QName(f).localname: (f.text or "").strip() for f in dup}
        try:
            saida.append(
                {
                    "numero": campos.get("nDup") or "",
                    "vencimento": date.fromisoformat(campos.get("dVenc", "")),
                    "valor": round(float(campos.get("vDup") or 0), 2),
                }
            )
        except ValueError:
            continue
    return saida


def informacoes(xml: str) -> str:
    raiz = etree.fromstring(xml.encode("utf-8"))
    return " ".join(
        (no.text or "").strip() for no in raiz.xpath("//*[local-name()='infAdic']/*[local-name()='infCpl']")
    )


CONDICAO = re.compile(
    r"(?:PAGTO|PGTO|PAGAMENTO|CONDICAO)[^\d\n]{0,25}((?:\d{1,3}\s*/\s*){1,23}\d{1,3})\s*(?:DIAS|DD)\b"
)


def condicao_de_pagamento(xml: str) -> str | None:
    if duplicatas(xml):
        return None
    import unicodedata

    texto = unicodedata.normalize("NFKD", informacoes(xml)).encode("ascii", "ignore").decode().upper()
    for achado in CONDICAO.finditer(texto):
        prazos = [int(p) for p in re.findall(r"\d+", achado.group(1))]
        if len(prazos) > 1 and all(a < b for a, b in zip(prazos, prazos[1:])):
            return re.sub(r"\s+", " ", achado.group(0)).strip()
    return None


def pdf(relativo: str) -> bytes:
    from core import documento_fiscal

    return documento_fiscal.pdf(ler(relativo))


PASTA_PDF = _PASTA_APP / "data" / "leituras" / "pdf_xml"


def pdf_em_arquivo(relativo: str) -> Path:
    import hashlib

    origem = caminho(relativo)
    destino = PASTA_PDF / hashlib.sha1(str(relativo).encode("utf-8")).hexdigest()[:20] / f"{origem.stem}.pdf"
    if not destino.is_file() or destino.stat().st_mtime < origem.stat().st_mtime:
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_suffix(".tmp")
        temporario.write_bytes(pdf(relativo))
        temporario.replace(destino)
    return destino


def configuracao() -> dict:
    from core.config_arquivo import carregar_json

    return ((carregar_json("parametros_financeiro") or {}).get("liberacao_manual") or {}).get("xml") or {}


def empresas_da_revenda(revenda: str, conf: dict | None = None) -> list[str]:
    from core.config import chave_revenda

    empresas = (conf if conf is not None else configuracao()).get("empresas") or {}
    return [
        cnpj
        for cnpj, nome in empresas.items()
        if not cnpj.startswith("_") and chave_revenda(nome) == chave_revenda(revenda)
    ]


def _cnpj(valor) -> str:
    digitos = re.sub(r"\D", "", str(valor or ""))
    return digitos.zfill(14) if digitos else ""


def _data(valor) -> date | None:
    if valor is None:
        return None
    return valor.date() if hasattr(valor, "date") else valor


def documentos(revenda: str, desde: date, conf: dict | None = None) -> list[dict]:
    conf = conf if conf is not None else configuracao()
    empresas = empresas_da_revenda(revenda, conf)
    if not empresas:
        return []
    saida = []
    nfe = indice("nfe", empresas, desde)
    if not nfe.is_empty():
        for r in nfe.filter((pl.col("papel") == "recebida") & pl.col("completa")).iter_rows(named=True):
            saida.append(
                {
                    "tipo": "NFE",
                    "chave": r["chave"],
                    "numero": str(r["numero"] or "").lstrip("0"),
                    "emitente_cnpj": _cnpj(r["emitente_cnpj"]),
                    "emitente_nome": r["emitente_nome"] or "",
                    "emissao": _data(r["emissao"]),
                    "valor": float(r["valor"] or 0),
                    "cfops": [c for c in re.split(r"[,\s]+", str(r["cfops"] or "")) if c],
                    "cancelada": str(r["situacao"] or "").lower().startswith("cancel"),
                    "entrada": r.get("tipo_nf") == "entrada",
                    "arquivo": r["arquivo"],
                    "empresa": r["empresa"],
                }
            )
    nfse = indice("nfse", empresas, desde)
    if not nfse.is_empty():
        for r in nfse.filter(pl.col("papel") == "tomador").iter_rows(named=True):
            saida.append(
                {
                    "tipo": "NFS",
                    "chave": r["chave"],
                    "numero": str(r["numero"] or "").lstrip("0"),
                    "emitente_cnpj": _cnpj(r["prestador_cnpj"]),
                    "emitente_nome": r["prestador_nome"] or "",
                    "emissao": _data(r["emissao"]),
                    "valor": float(r["valor_liquido"] or r["valor_servico"] or 0),
                    "cfops": [],
                    "cancelada": bool(r["cancelada"]) or str(r["situacao"] or "").lower().startswith("cancel"),
                    "entrada": False,
                    "arquivo": r["arquivo"],
                    "empresa": r["empresa"],
                }
            )
    cte = indice("cte", empresas, desde)
    if not cte.is_empty():
        for r in cte.filter(pl.col("tomadora")).iter_rows(named=True):
            saida.append(
                {
                    "tipo": "CTE",
                    "chave": r["chave"],
                    "numero": str(r["numero"] or "").lstrip("0"),
                    "emitente_cnpj": _cnpj(r["emitente_cnpj"]),
                    "emitente_nome": r["emitente_nome"] or "",
                    "emissao": _data(r["emissao"]),
                    "valor": float(r["valor_frete"] or 0),
                    "cfops": [],
                    "cancelada": str(r["situacao"] or "").lower().startswith("cancel"),
                    "entrada": False,
                    "arquivo": r["arquivo"],
                    "empresa": r["empresa"],
                }
            )
    tipos = set(conf.get("tipos") or ("NFE", "NFS", "CTE"))
    return [d for d in saida if d["tipo"] in tipos]


def tipos_no_lancamento(conf: dict | None = None) -> set[str]:
    conf = conf if conf is not None else configuracao()
    return set(conf.get("tipos_no_lancamento") or ("NFS", "CTE"))


def filiais_com_nfe_a_pagar(revenda: str, conf: dict | None = None) -> set[str]:
    from core.config import chave_revenda

    filiais = (conf if conf is not None else configuracao()).get("nfe_da_filial") or {}
    return {
        _cnpj(cnpj)
        for cnpj, nome in filiais.items()
        if not cnpj.startswith("_") and chave_revenda(nome) == chave_revenda(revenda)
    }


def nfe_a_pagar_da_filial(doc: dict, filiais: set[str]) -> bool:
    from core import cfop

    empresa = str(doc.get("empresa") or "")
    return (
        doc.get("tipo") == "NFE"
        and empresa in filiais
        and not doc.get("entrada")
        and not cfop.nota_de_devolucao(doc.get("cfops"))
        and str(doc.get("emitente_cnpj") or "")[:8] != empresa[:8]
    )


def numeros_do_titulo(num_doc_normalizado) -> tuple[str, set[str]] | None:
    achado = re.match(r"^([A-Z]+)(\d+)$", re.sub(r"[^A-Z0-9]", "", str(num_doc_normalizado or "").upper()))
    if not achado:
        return None
    digitos = achado.group(2)
    return achado.group(1), {
        (digitos[:-corte] if corte else digitos).lstrip("0") or "0" for corte in (0, 2) if len(digitos) > corte
    }


def formas_do_numero(numero: str) -> set[str]:
    numero = str(numero or "").lstrip("0") or "0"
    formas = {numero}
    for ano in (2, 4):
        if len(numero) >= 11 and numero[ano : ano + 3] == "000":
            formas |= {numero[ano:].lstrip("0") or "0", numero[ano - 2 : ano] + (numero[ano:].lstrip("0") or "0")}
    return formas


COMPATIVEIS = {
    "NFE": {"NFE", "NF", "NFF", "FAT", "DUP"},
    "NFS": {"NFS", "NF", "NFE", "FAT", "REC", "DUP"},
    "CTE": {"CTE", "CT", "CTR", "FAT", "DUP"},
}


def indice_de_titulos(titulos: list[dict]) -> dict:
    saida: dict = {}
    for t in titulos:
        partes = numeros_do_titulo(t.get("num_doc_normalizado"))
        if not partes or not t.get("cnpj"):
            continue
        especie, numeros = partes
        for numero in numeros:
            saida.setdefault((_cnpj(t["cnpj"]), numero), []).append({**t, "_especie": especie})
    return saida


def _cabe(titulo: dict, doc: dict) -> bool:
    valor = titulo.get("valor")
    if valor is not None and doc.get("valor") and float(valor) > float(doc["valor"]) + 0.05:
        return False
    vencimento, emissao = _data(titulo.get("data_vencimento")), doc.get("emissao")
    return not (vencimento and emissao and vencimento < emissao - timedelta(days=1))


def titulos_do_documento(doc: dict, indice_titulos: dict) -> list[dict]:
    vistos, saida = set(), []
    for forma in formas_do_numero(doc["numero"]):
        for t in indice_titulos.get((doc["emitente_cnpj"], forma), ()):
            if (
                t["_especie"][:3] in COMPATIVEIS.get(doc["tipo"], {doc["tipo"]})
                and id(t) not in vistos
                and _cabe(t, doc)
            ):
                vistos.add(id(t))
                saida.append(t)
    return saida


if __name__ == "__main__":
    import argparse

    sys.stdout.reconfigure(encoding="utf-8")
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("arquivo", nargs="?", help="o caminho do XML no acervo, como o indice o guarda")
    a.add_argument("--pdf", help="grava o PDF neste caminho")
    args = a.parse_args() if "__file__" in globals() else a.parse_args([])
    relativo = args.arquivo or input("Caminho no acervo: ").strip().strip('"')
    from core import documento_fiscal

    conteudo = ler(relativo)
    for campo, valor in documento_fiscal.ler(conteudo).items():
        print(f"  {campo:24} {valor}")
    for d in duplicatas(conteudo):
        print(f"  duplicata {d['numero']:>8}  {d['vencimento']:%d/%m/%Y}  {d['valor']:>12,.2f}")
    if args.pdf:
        Path(args.pdf).write_bytes(pdf(relativo))
        print(f"  PDF gravado em {args.pdf}")
