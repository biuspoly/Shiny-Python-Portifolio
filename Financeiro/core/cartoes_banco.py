from __future__ import annotations

import unicodedata

from shiny import ui

from .cores import VALOR_NEGATIVO, VALOR_POSITIVO

PASTA_ICONES = "img/ppf"

ICONE_PADRAO = "pagamentos.svg"

_ICONES: tuple[tuple[str, str], ...] = (
    ("caixa999", "caixa-999-icon.svg"),
    ("bradesco", "bradesco-icon.svg"),
    ("sicoob", "sicoob-icon.svg"),
    ("itau", "itaú-icon.svg"),
    ("santander", "santander-icon.svg"),
    ("daycoval", "daycoval-icon.svg"),
    ("sicredi", "sicredi-icon.svg"),
    ("sicred", "sicredi-icon.svg"),
    ("bancodobrasil", "bb-icon.svg"),
    ("bb", "bb-icon.svg"),
    ("caixaeconomicafederal", "cef-icon.svg"),
    ("caixaeconomica", "cef-icon.svg"),
    ("cef", "cef-icon.svg"),
    ("fabrica", "fabrica-icon.svg"),
)


def _chave(nome: str | None) -> str:
    normal = unicodedata.normalize("NFKD", str(nome or "").strip().lower())
    sem_acento = "".join(c for c in normal if not unicodedata.combining(c))
    return "".join(c for c in sem_acento if c.isalnum())


def icone_do_banco(nome: str | None) -> str:
    chave = _chave(nome)
    if chave.startswith("caixa") and "999" in chave:
        return f"{PASTA_ICONES}/caixa-999-icon.svg"
    for prefixo, arquivo in _ICONES:
        if chave.startswith(prefixo):
            return f"{PASTA_ICONES}/{arquivo}"
    return f"{PASTA_ICONES}/{ICONE_PADRAO}"


def _valor(texto: str, cor: str, classe: str = "") -> ui.Tag:
    return ui.span(texto, class_=f"ppf-banco-valor {classe}".strip(), style=f"color: {cor};")


def linha_saldo(rotulo: str, valor: float | None, *, sempre_saida: bool = False) -> ui.Tag:
    if valor is None:
        valor = 0.0
    cor = VALOR_NEGATIVO if (sempre_saida or valor < 0) else VALOR_POSITIVO
    return ui.div(
        ui.span(rotulo, class_="ppf-banco-rotulo"),
        _valor(formatar_reais(valor), cor),
        class_="ppf-banco-linha",
    )


def formatar_reais(valor: float | None) -> str:
    if valor is None:
        return "R$ 0,00"
    inteiro = f"{abs(valor):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"{'-' if valor < 0 else ''}R$ {inteiro}"


def ler_reais(texto) -> float | None:
    bruto = str(texto or "").replace("R$", "").replace(" ", "").replace(" ", "").strip()
    if not bruto:
        return None
    negativo = bruto.startswith("-") or (bruto.startswith("(") and bruto.endswith(")"))
    bruto = bruto.strip("-()")
    virgula, ponto = bruto.rfind(","), bruto.rfind(".")
    if virgula >= 0 and ponto >= 0:
        decimal = "," if virgula > ponto else "."
        bruto = bruto.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    elif virgula >= 0:
        bruto = bruto.replace(",", "") if bruto.count(",") > 1 else bruto.replace(",", ".")
    elif ponto >= 0:
        partes = bruto.split(".")
        milhar = len(partes) > 2 or (len(partes) == 2 and len(partes[1]) == 3)
        bruto = bruto.replace(".", "") if milhar else bruto
    try:
        valor = round(float(bruto), 2)
    except ValueError:
        return None
    return -valor if negativo else valor


def cartao_banco(nome: str, linhas: list[ui.Tag], *, sem_extrato: bool = False) -> ui.Tag:
    return ui.div(
        ui.div(
            ui.div(
                ui.tags.img(src=icone_do_banco(nome), alt=nome),
                class_="ppf-banco-icone",
            ),
            ui.span(nome, class_="ppf-banco-nome"),
            (
                ui.span(
                    "!",
                    class_="ppf-banco-alerta",
                    title="sem extrato bancário importado",
                )
                if sem_extrato
                else None
            ),
            class_="ppf-banco-cabecalho",
        ),
        ui.div(*linhas, class_="ppf-banco-corpo"),
        class_="ppf-banco",
    )


def grade_cartoes(cartoes: list[ui.Tag]) -> ui.Tag:
    if not cartoes:
        return ui.div(
            "Nenhuma conta bancária com saldo ou limite nesta revenda.",
            class_="ppf-bancos-vazio",
        )
    return ui.div(*cartoes, class_="ppf-bancos", **{"data-cartoes": str(len(cartoes))})
