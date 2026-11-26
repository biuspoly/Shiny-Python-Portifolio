from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColunaLargura:
    coluna: str
    largura: int


def gerar_css_larguras(seletor_base: str, larguras: list[ColunaLargura]) -> str:
    linhas = []
    for posicao, cl in enumerate(larguras, start=1):
        linhas.append(
            f"{seletor_base} table th:nth-child({posicao}), "
            f"{seletor_base} table td:nth-child({posicao}) {{ width: {cl.largura}px !important; }}"
        )
    return "\n".join(linhas)
