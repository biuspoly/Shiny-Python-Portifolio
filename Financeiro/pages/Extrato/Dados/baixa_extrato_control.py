"""A data da Situação digitada na tela. No original, este módulo também grava a baixa no
ERP, com registro de tudo; no portfólio a gravação vale para o cache da sessão."""

from datetime import date, datetime


class Recusa(Exception):
    """A baixa não vai: a frase é a que a tela mostra."""


def data_baixa(valor) -> str | None:
    if valor in (None, "", "-"):
        return None
    if isinstance(valor, (date, datetime)):
        return f"{valor:%d%m%Y}"
    texto = str(valor).strip()
    for formato in ("%d/%m/%Y", "%d%m%Y", "%Y-%m-%d"):
        try:
            return f"{datetime.strptime(texto, formato):%d%m%Y}"
        except ValueError:
            continue
    raise Recusa(f"data da baixa invalida: {texto!r}")


def antes_de_gravar() -> list[str]:
    """O que ainda impede a gravação (vazio: grava). No original vem de um JSON de liberação."""
    return []
