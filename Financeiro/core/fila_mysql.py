from __future__ import annotations

if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import os
import threading
import time
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent / "data" / "manual"
FILA = PASTA / "mysql_pendente.jsonl"
FEITO = PASTA / "mysql_feito.jsonl"
FALHAS = PASTA / "mysql_pendente_falhas.jsonl"
TRAVA = PASTA / "mysql_pendente.trava"

ESPERA_SEGUNDOS = 30

TRAVA_VELHA_SEGUNDOS = 900

CODIGOS_FORA = {1040, 1053, 1077, 1081, 2002, 2003, 2005, 2006, 2013, 2055}

_trava = threading.RLock()
_fora_ate = {"t": 0.0}


def mysql_fora(erro: BaseException) -> bool:
    atual = erro
    for _ in range(4):
        if atual is None:
            break
        if isinstance(atual, (ConnectionError, TimeoutError)):
            return True
        argumentos = getattr(atual, "args", ()) or ()
        if argumentos and isinstance(argumentos[0], int) and argumentos[0] in CODIGOS_FORA:
            return True
        if getattr(atual, "connection_invalidated", False):
            return True
        nome = type(atual).__name__
        if nome in ("InterfaceError",) or (nome == "TimeoutError" and "QueuePool" in str(atual)):
            return True
        atual = getattr(atual, "orig", None) or atual.__cause__ or atual.__context__
    return False


def marcar_fora() -> None:
    _fora_ate["t"] = time.monotonic() + ESPERA_SEGUNDOS


def parece_fora() -> bool:
    return time.monotonic() < _fora_ate["t"]


def _para_json(valor):
    if isinstance(valor, datetime):
        return {"__momento__": valor.isoformat()}
    if isinstance(valor, date):
        return {"__data__": valor.isoformat()}
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (set, frozenset, tuple)):
        return list(valor)
    if hasattr(valor, "item"):
        return valor.item()
    return str(valor)


def _de_json(objeto: dict):
    if "__momento__" in objeto:
        return datetime.fromisoformat(objeto["__momento__"])
    if "__data__" in objeto:
        return date.fromisoformat(objeto["__data__"])
    return objeto


def _acrescentar(arquivo: Path, registro: dict) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    linha = json.dumps(registro, ensure_ascii=False, default=_para_json) + "\n"
    with open(arquivo, "a", encoding="utf-8") as saida:
        saida.write(linha)
        saida.flush()
        os.fsync(saida.fileno())


def _linhas(arquivo: Path) -> list[dict]:
    if not arquivo.is_file():
        return []
    saida = []
    with open(arquivo, encoding="utf-8") as entrada:
        for linha in entrada:
            try:
                saida.append(json.loads(linha, object_hook=_de_json))
            except ValueError:
                continue
    return saida


def enfileirar(funcao: str, args: list, kwargs: dict, quando: datetime) -> str:
    ident = uuid.uuid4().hex
    with _trava:
        _acrescentar(FILA, {"id": ident, "funcao": funcao, "args": list(args), "kwargs": kwargs, "quando": quando})
    return ident


def pendentes() -> list[dict]:
    with _trava:
        feitos = {r.get("id") for r in _linhas(FEITO)}
        return [r for r in _linhas(FILA) if r.get("id") not in feitos]


def tem_pendentes() -> bool:
    try:
        tamanho_fila = FILA.stat().st_size
    except OSError:
        return False
    if not tamanho_fila:
        return False
    return bool(pendentes())


def falhas() -> list[dict]:
    return _linhas(FALHAS)


def _pegar_trava(espera: float) -> bool:
    PASTA.mkdir(parents=True, exist_ok=True)
    limite = time.monotonic() + espera
    while True:
        try:
            descritor = os.open(TRAVA, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descritor, f"{os.getpid()} {datetime.now().isoformat()}".encode())
            os.close(descritor)
            return True
        except FileExistsError:
            try:
                if time.time() - TRAVA.stat().st_mtime > TRAVA_VELHA_SEGUNDOS:
                    TRAVA.unlink(missing_ok=True)
                    continue
            except OSError:
                continue
        if time.monotonic() >= limite:
            return False
        time.sleep(0.2)


def _soltar_trava() -> None:
    TRAVA.unlink(missing_ok=True)


def reaplicar(executar, espera: float = 5.0, compactar: bool = False, avisar_falha=None) -> dict:
    resumo = {"feitas": 0, "falhas": 0, "pendentes": 0, "fora": False, "ocupada": False}
    if not _pegar_trava(espera):
        resumo.update(ocupada=True, pendentes=len(pendentes()))
        return resumo
    try:
        fila = pendentes()
        for posicao, registro in enumerate(fila):
            try:
                executar(registro)
            except Exception as erro:
                if mysql_fora(erro):
                    marcar_fora()
                    resumo.update(fora=True, pendentes=len(fila) - posicao)
                    return resumo
                _acrescentar(FALHAS, {**registro, "erro": str(erro)[:500], "em": datetime.now()})
                resumo["falhas"] += 1
                if avisar_falha:
                    try:
                        avisar_falha(registro, erro)
                    except Exception:
                        pass
            else:
                resumo["feitas"] += 1
            _acrescentar(FEITO, {"id": registro["id"], "em": datetime.now()})
        if compactar:
            with _trava:
                if not pendentes():
                    for arquivo in (FILA, FEITO):
                        if arquivo.is_file():
                            open(arquivo, "w", encoding="utf-8").close()
        return resumo
    finally:
        _soltar_trava()


def compactar_se_vazia() -> None:
    try:
        if not FILA.is_file() or not FILA.stat().st_size:
            return
    except OSError:
        return
    if not _pegar_trava(0.0):
        return
    try:
        with _trava:
            if not pendentes():
                for arquivo in (FILA, FEITO):
                    open(arquivo, "w", encoding="utf-8").close()
    finally:
        _soltar_trava()


def reaplicar_antes_do_script(nome: str) -> None:
    try:
        if not tem_pendentes():
            return
        from core import gravacao

        resumo = gravacao.reaplicar_pendentes(espera=60.0)
        print(f"  fila do MySQL antes de {nome}: {resumo}", flush=True)
    except Exception as erro:
        print(f"  [!] fila do MySQL antes de {nome}: {str(erro)[:200]}", flush=True)


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if "--reaplicar" in sys.argv[1:]:
        from core import gravacao

        print(gravacao.reaplicar_pendentes(espera=30.0))
    for registro in pendentes():
        print("pendente:", registro["quando"], registro["funcao"], registro["args"], registro["kwargs"])
    for registro in falhas():
        print("falhou:", registro.get("em"), registro["funcao"], registro.get("erro"))
    print(f"{len(pendentes())} pendente(s), {len(falhas())} falha(s)")
