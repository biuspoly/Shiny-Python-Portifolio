from typing import TYPE_CHECKING

_ORIGEM = {
    "pag_comodatos_ui": "pag_comodatos",
    "pag_comodatos_server": "pag_comodatos",
    "pag_comodatos_saldo_ui": "pag_comodatos_saldo",
    "pag_comodatos_saldo_server": "pag_comodatos_saldo",
    "pag_solicitacao_ui": "pag_solicitacao",
    "pag_solicitacao_server": "pag_solicitacao",
}

__all__ = list(_ORIGEM)

if TYPE_CHECKING:
    from .pag_comodatos import pag_comodatos_server, pag_comodatos_ui
    from .pag_comodatos_saldo import pag_comodatos_saldo_server, pag_comodatos_saldo_ui
    from .pag_solicitacao import pag_solicitacao_server, pag_solicitacao_ui


def __getattr__(nome: str):
    modulo = _ORIGEM.get(nome)
    if modulo is None:
        raise AttributeError(f"module {__name__!r} has no attribute {nome!r}")
    from importlib import import_module

    return getattr(import_module(f".{modulo}", __name__), nome)


def __dir__():
    return sorted(__all__)
