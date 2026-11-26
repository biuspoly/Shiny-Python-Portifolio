from __future__ import annotations

if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent if "__file__" in globals() else Path.cwd()))

import json
import os
import threading
from pathlib import Path

from loguru import logger
from shiny import reactive, ui

from core import acervo

ARQUIVO = "colunas_por_usuario.json"
_trava = threading.Lock()
_lido: dict = {"marca": None, "dados": {}}


def _arquivo() -> Path:
    return acervo.raiz() / ARQUIVO


def _ler() -> dict:
    arquivo = _arquivo()
    try:
        estado = arquivo.stat()
        marca = (str(arquivo), estado.st_mtime_ns, estado.st_size)
    except OSError:
        return {}
    if marca != _lido["marca"]:
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning(f"Colunas por pessoa: {arquivo} ilegivel -- {exc}")
            dados = {}
        _lido.update(marca=marca, dados=dados if isinstance(dados, dict) else {})
    return _lido["dados"]


def escolhidas(usuario: str | None, tela: str, padrao: list[str] | None = None) -> list[str] | None:
    guardada = _ler().get(str(usuario or "").strip(), {}).get(tela)
    if isinstance(guardada, dict) and isinstance(guardada.get("colunas"), list):
        colunas = [str(c) for c in guardada["colunas"]]
        padrao_da_escolha = {str(c) for c in guardada.get("padrao") or []}
    elif isinstance(guardada, list):
        colunas = [str(c) for c in guardada]
        padrao_da_escolha = set(colunas)
    else:
        return None
    novas = [c for c in (padrao or []) if c not in padrao_da_escolha and c not in colunas]
    return colunas + novas


def guardar(usuario: str | None, tela: str, colunas: list[str], padrao: list[str]) -> bool:
    login = str(usuario or "").strip()
    if not login:
        return False
    nova = None if set(colunas) == set(padrao) else {"colunas": list(colunas), "padrao": list(padrao)}
    with _trava:
        dados = {pessoa: dict(telas) for pessoa, telas in _ler().items() if isinstance(telas, dict)}
        if dados.get(login, {}).get(tela) == nova:
            return False
        telas = dados.setdefault(login, {})
        if nova is None:
            telas.pop(tela, None)
        else:
            telas[tela] = nova
        if not telas:
            dados.pop(login)
        arquivo = _arquivo()
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        temporario = arquivo.with_name(f".{ARQUIVO}.gravando")
        temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(temporario, arquivo)
    return True


def caixa_das_opcoes(ident: str, opcoes: dict[str, str], padrao: list[str], com_permissao: dict) -> ui.Tag:
    livres = {codigo: nome for codigo, nome in opcoes.items() if codigo not in com_permissao}
    return ui.input_checkbox_group(ident, None, livres, selected=[codigo for codigo in padrao if codigo in livres])


def caixa_das_acoes(acoes: dict[str, str], padrao: list[str], com_permissao: dict) -> ui.Tag:
    return caixa_das_opcoes("acoes", acoes, padrao, com_permissao)


class ColunasDaPessoa:
    def __init__(
        self,
        input,
        tela: str,
        usuario_atual,
        padrao: list[str],
        id_colunas: str = "colunas",
        opcoes=None,
        liberada=None,
    ):
        self._input = input
        self._tela = tela
        self._usuario_atual = usuario_atual
        self._padrao = list(padrao)
        self._id = id_colunas
        self._opcoes = opcoes if callable(opcoes) else dict(opcoes or {})
        self._liberada = liberada
        self._padrao_da_pessoa = list(padrao)
        self._voltou_para = None
        self._registrar_trazer()
        self._registrar_guardar()

    def _usuario(self) -> str:
        return str((self._usuario_atual() if self._usuario_atual is not None else "") or "").strip()

    def _registrar_trazer(self):
        @reactive.effect
        def _trazer_a_escolha():
            try:
                self._trazer()
            except Exception as exc:
                logger.warning(f"Colunas por pessoa ({self._tela}): trazer a escolha -- {exc}")

    def _registrar_guardar(self):
        @reactive.effect
        @reactive.event(self._input[self._id], ignore_init=True)
        def _guardar_a_escolha():
            try:
                self._guardar()
            except Exception as exc:
                logger.warning(f"Colunas por pessoa ({self._tela}): guardar a escolha -- {exc}")

    def _trazer(self):
        usuario = self._usuario()
        if not usuario or usuario == self._voltou_para:
            return
        self._voltou_para = usuario
        if self._liberada is not None:
            todas_as_opcoes = self._opcoes() if callable(self._opcoes) else self._opcoes
            liberadas = {codigo: nome for codigo, nome in todas_as_opcoes.items() if self._liberada(codigo)}
            self._padrao_da_pessoa = [codigo for codigo in self._padrao if codigo in liberadas]
            salvas = escolhidas(usuario, self._tela, self._padrao_da_pessoa)
            escolha = salvas if salvas is not None else self._padrao_da_pessoa
            ui.update_checkbox_group(
                self._id, choices=liberadas, selected=[codigo for codigo in escolha if codigo in liberadas]
            )
            return
        salvas = escolhidas(usuario, self._tela, self._padrao)
        if salvas is not None:
            ui.update_checkbox_group(self._id, selected=salvas)

    def _guardar(self):
        usuario = self._usuario()
        if not usuario or usuario != self._voltou_para:
            return
        guardar(usuario, self._tela, list(self._input[self._id]() or []), self._padrao_da_pessoa)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("arquivo:", _arquivo())
    escolha = sys.argv[1] if len(sys.argv) > 1 and "__file__" in globals() else None
    for login, telas in sorted(_ler().items()):
        if escolha and login != escolha:
            continue
        for tela, guardada in sorted(telas.items()):
            colunas = guardada.get("colunas", []) if isinstance(guardada, dict) else guardada
            print(f"  {login:24} {tela:4} {', '.join(colunas)}")
    if not _ler():
        print("  ninguem escolheu colunas ainda")
