from __future__ import annotations

import unicodedata
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

if __name__ == "__main__":
    import sys
    from pathlib import Path

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

from core.config_arquivo import carregar_json

CONFIG = "arquivos"


def _cfg() -> dict:
    return (carregar_json(CONFIG) or {}).get("planilha_fabrica") or {}


def _sem_marca(valor):
    if isinstance(valor, dict):
        return {k: v for k, v in valor.items() if not k.startswith("_")}
    return valor


def _norma(texto) -> str:
    cru = unicodedata.normalize("NFKD", str(texto or ""))
    sem_acento = "".join(c for c in cru if not unicodedata.combining(c))
    return " ".join(sem_acento.lower().split())


class Leitura(NamedTuple):
    tipo: str
    linhas: list[dict]
    quando: datetime | None
    ignoradas: list[str]
    erro: str


def _valor(bruto):
    if bruto is None or isinstance(bruto, (int, float)):
        return bruto
    limpo = str(bruto).strip()
    if not limpo:
        return None
    candidato = limpo.replace(".", "").replace(",", ".") if "," in limpo else limpo
    try:
        return float(candidato)
    except ValueError:
        return limpo


def _achar_cabecalho(aba, mapas: dict) -> tuple[int, dict, str]:
    melhor = (0, {}, "", -1)
    for numero, linha in enumerate(aba.iter_rows(max_row=8, values_only=True), 1):
        if not linha:
            continue
        rotulos = {i: _norma(v) for i, v in enumerate(linha) if v is not None}
        for tipo, mapa in mapas.items():
            casadas = {i: mapa[r] for i, r in rotulos.items() if r in mapa}
            if len(casadas) > melhor[3]:
                melhor = (numero, casadas, tipo, len(casadas))
    return melhor[0], melhor[1], melhor[2]


def ler(caminho: Path | str) -> Leitura:
    caminho = Path(caminho)
    cfg = _cfg()
    colunas = _sem_marca(cfg.get("colunas") or {})
    mapas = {
        "partidas": {_norma(k): v for k, v in (colunas.get("partidas") or {}).items()},
        "limites": {_norma(k): v for k, v in (colunas.get("limites") or {}).items()},
    }
    obrigatorias = {
        "partidas": set(colunas.get("partidas_obrigatorias") or []),
        "limites": set(colunas.get("limites_obrigatorias") or []),
    }

    try:
        import openpyxl

        livro = openpyxl.load_workbook(caminho, data_only=True, read_only=True)
    except Exception as erro:
        return Leitura("", [], None, [], f"não deu para abrir: {str(erro)[:100]}")

    try:
        nome_aba = cfg.get("aba_dados") or livro.sheetnames[0]
        aba = livro[nome_aba] if nome_aba in livro.sheetnames else livro[livro.sheetnames[0]]
        numero, casadas, tipo = _achar_cabecalho(aba, mapas)
        if not casadas or not tipo:
            return Leitura(
                "",
                [],
                None,
                [],
                "o cabeçalho não bate com nenhum formato conhecido — confira "
                "config/arquivos.json (planilha_fabrica.colunas)",
            )

        faltam = obrigatorias[tipo] - set(casadas.values())
        if faltam:
            return Leitura(
                tipo,
                [],
                None,
                [],
                f"a planilha parece “{tipo}” mas falta: {', '.join(sorted(faltam))}",
            )

        linhas, ignoradas = [], []
        for posicao, bruta in enumerate(aba.iter_rows(values_only=True), 1):
            if posicao <= numero or not bruta:
                continue
            registro = {campo: _valor(bruta[i]) for i, campo in casadas.items() if i < len(bruta)}
            if not any(v is not None and v != "" for v in registro.values()):
                continue
            vazias = [c for c in obrigatorias[tipo] if registro.get(c) in (None, "")]
            if vazias:
                tem_valor = any(registro.get(c) not in (None, "") for c in registro if c not in obrigatorias[tipo])
                motivo = "subtotal do SAP (sem documento)" if tem_valor else "sem " + ", ".join(sorted(vazias))
                ignoradas.append(f"linha {posicao}: {motivo}")
                continue
            linhas.append(registro)

        return Leitura(tipo, linhas, _data_da_extracao(livro, cfg), ignoradas, "")
    finally:
        livro.close()


def _data_da_extracao(livro, cfg: dict) -> datetime | None:
    aba_id = cfg.get("aba_identificacao") or "Filtro"
    if aba_id not in livro.sheetnames:
        return None
    meses = {
        "jan": 1,
        "fev": 2,
        "mar": 3,
        "abr": 4,
        "mai": 5,
        "jun": 6,
        "jul": 7,
        "ago": 8,
        "set": 9,
        "out": 10,
        "nov": 11,
        "dez": 12,
    }
    import re

    for linha in livro[aba_id].iter_rows(values_only=True):
        if not linha or not linha[0]:
            continue
        if not _norma(linha[0]).startswith("hora"):
            continue
        if len(linha) > 1 and isinstance(linha[1], datetime):
            return linha[1]
        texto = _norma(linha[1] if len(linha) > 1 else "")
        hora = r"(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?"
        achado = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)" + hora, texto)
        if achado:
            dia, mes, ano = (int(p) for p in achado.groups()[:3])
        else:
            achado = re.search(r"(\d{1,2})\s+de\s+([a-z]{3})[a-z.]*\s+de\s+(\d{4})" + hora, texto)
            if achado and achado.group(2) in meses:
                dia, mes, ano = int(achado.group(1)), meses[achado.group(2)], int(achado.group(3))
            else:
                achado = re.search(r"(\d{4})-(\d{2})-(\d{2})" + hora, texto)
                if not achado:
                    continue
                ano, mes, dia = (int(p) for p in achado.groups()[:3])
        h, m, s = (int(p or 0) for p in achado.groups()[3:])
        try:
            return datetime(ano, mes, dia, h, m, s)
        except ValueError:
            return None
    return None


def resumo(leitura: Leitura) -> str:
    if leitura.erro:
        return leitura.erro
    rotulo = {"partidas": "partidas em aberto", "limites": "saldo/limites"}.get(leitura.tipo, leitura.tipo)
    partes = [f"{len(leitura.linhas)} linha(s) de {rotulo}"]
    if leitura.quando:
        partes.append(f"extraída em {leitura.quando:%d/%m/%Y %H:%M}")
    if leitura.ignoradas:
        partes.append(f"{len(leitura.ignoradas)} linha(s) ignorada(s)")
    return " — ".join(partes)


if __name__ == "__main__":
    import argparse

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("arquivo", nargs="?")
    args = a.parse_args() if "__file__" in globals() else a.parse_args([])
    lido = ler(Path(args.arquivo or input("Caminho do arquivo: ").strip().strip('"')))
    for campo, valor in lido._asdict().items():
        print(
            f"{campo:22}",
            f"{len(valor)} item(ns), os 3 primeiros: {valor[:3]}" if isinstance(valor, (list, tuple)) else valor,
        )
