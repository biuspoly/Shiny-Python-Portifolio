from __future__ import annotations

import re

from loguru import logger

# No portfólio não há banco: o que se grava fica na memória desta sessão
# (no Shinylive, cada visitante tem o próprio Python) e a leitura aplica por cima
# do cache. (cnpj, romaneio) -> campos gravados.
GRAVADOS: dict[tuple[str, str], dict] = {}

CAMPOS = ("HR_SAIDA", "HR_FIM", "KM_INI", "KM_FIM", "AJUDANTE_1", "AJUDANTE_2", "OBS")

_HORA = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")

LIMITE_AJUDANTE = 50
LIMITE_OBS = 100


def hora_valida(valor: str | None) -> bool:
    return bool(valor) and bool(_HORA.match(valor.strip()))


def km_texto(valor: str | None) -> str:
    return str(valor or "").strip().replace(".", "").replace(" ", "")


def km_valido(valor: str | None) -> bool:
    return km_texto(valor).isdigit()


def conferir(valores: dict) -> list[str]:
    problemas = []
    if not hora_valida(valores.get("HR_SAIDA")):
        problemas.append("Hora de saída deve estar no formato HH:MM (ex.: 07:30).")
    if not hora_valida(valores.get("HR_FIM")):
        problemas.append("Hora de chegada deve estar no formato HH:MM (ex.: 18:40).")
    if not km_valido(valores.get("KM_INI")):
        problemas.append("Km de saída deve ser um número inteiro.")
    if not km_valido(valores.get("KM_FIM")):
        problemas.append("Km de chegada deve ser um número inteiro.")
    if not problemas and int(km_texto(valores["KM_FIM"])) < int(km_texto(valores["KM_INI"])):
        problemas.append("Km de chegada não pode ser menor que o de saída.")
    return problemas


def _texto(valor: str | None, limite: int) -> str | None:
    if valor is None:
        return None
    limpo = valor.strip()[:limite]
    return limpo or None


def gravar(cnpj: str, romaneio: str, valores: dict, executar: bool = True) -> int:
    problemas = conferir(valores)
    if problemas:
        raise ValueError(" ".join(problemas))

    parametros = {
        "HR_SAIDA": valores["HR_SAIDA"].strip(),
        "HR_FIM": valores["HR_FIM"].strip(),
        "KM_INI": int(km_texto(valores["KM_INI"])),
        "KM_FIM": int(km_texto(valores["KM_FIM"])),
        "AJUDANTE_1": _texto(valores.get("AJUDANTE_1"), LIMITE_AJUDANTE),
        "AJUDANTE_2": _texto(valores.get("AJUDANTE_2"), LIMITE_AJUDANTE),
        "OBS": _texto(valores.get("OBS"), LIMITE_OBS),
        "cnpj": cnpj,
        "romaneio": romaneio,
    }
    if not executar:
        return 0
    GRAVADOS[(cnpj, romaneio)] = {c: parametros[c] for c in CAMPOS}
    logger.info(f"PDE: romaneio {romaneio} ({cnpj}) atualizado na sessão")
    return 1


def regravar_parquet() -> int:
    """No original, refaz o .parquet a partir do banco; aqui a leitura já aplica GRAVADOS."""
    return 0
