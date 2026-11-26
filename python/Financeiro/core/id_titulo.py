from __future__ import annotations

import re

_SUFIXO = re.compile(r"(?:_clone\d*)+$")


def base_do(id_unico: str | None) -> str:
    return _SUFIXO.sub("", str(id_unico or ""))


def numero_da_parte(id_unico: str | None) -> int:
    sufixo = _SUFIXO.search(str(id_unico or ""))
    if not sufixo:
        return 0
    pedacos = re.findall(r"_clone(\d*)", sufixo.group(0))
    if len(pedacos) == 1 and pedacos[0]:
        return int(pedacos[0])
    return len(pedacos)


def id_da_parte(base: str, numero: int) -> str:
    if numero <= 0:
        return base
    return f"{base}_clone" if numero == 1 else f"{base}_clone{numero}"


def eh_parte(id_unico: str | None) -> bool:
    return numero_da_parte(id_unico) > 0
