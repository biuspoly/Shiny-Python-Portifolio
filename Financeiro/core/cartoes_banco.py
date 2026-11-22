"""Valores em reais na tela: formatar e ler de volta."""


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
