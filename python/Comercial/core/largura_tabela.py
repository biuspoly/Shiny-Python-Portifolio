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


_LARGAS = r"[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ]"
_ESTREITOS = r"[ .,:;/|'()\-]"
_PESO_LARGO = 0.10
_PESO_ESTREITO = -0.5


def larguras_do_conteudo(
    dados,
    colunas: list[str],
    fixas: dict[str, int] | None = None,
    teto: dict[str, int] | None = None,
    folga: int = 3,
    minimo: int = 6,
) -> list[ColunaLargura]:

    fixas, teto = fixas or {}, teto or {}
    larguras = []
    for coluna in colunas:
        if coluna in fixas:
            larguras.append(ColunaLargura(coluna, fixas[coluna]))
            continue
        cabecalho = max((len(palavra) for palavra in str(coluna).split()), default=0)
        conteudo = 0
        if dados is not None and coluna in dados and len(dados):
            texto = dados[coluna].astype(str)
            peso = (
                texto.str.len() + _PESO_LARGO * texto.str.count(_LARGAS) + _PESO_ESTREITO * texto.str.count(_ESTREITOS)
            )
            maior = peso.max()

            conteudo = round(maior) if maior == maior else 0
        largura = max(minimo, cabecalho, conteudo) + folga
        larguras.append(ColunaLargura(coluna, min(largura, teto.get(coluna, largura))))
    return larguras


def gerar_css_larguras_pct(seletor_base: str, larguras: list[ColunaLargura]) -> str:

    total = sum(cl.largura for cl in larguras) or 1
    linhas = []
    for posicao, cl in enumerate(larguras, start=1):
        pct = cl.largura / total * 100
        linhas.append(
            f"{seletor_base} table th:nth-child({posicao}), "
            f"{seletor_base} table td:nth-child({posicao}) {{ width: {pct:.3f}% !important; }}"
        )
    return "\n".join(linhas)
