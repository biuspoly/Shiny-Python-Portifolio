"""Números no jeito brasileiro: ponto no milhar, vírgula no decimal."""

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def numero(valor: float | None, casas: int = 0) -> str:
    if valor is None:
        return ""
    valor = round(valor, casas) or 0.0  # sem "-0,0"
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def moeda(valor: float | None, casas: int = 2) -> str:
    return "" if valor is None else f"R$ {numero(valor, casas)}"


def pct(valor: float | None, casas: int = 1) -> str:
    return "" if valor is None else f"{numero(valor * 100, casas)}%"


def mes_curto(d) -> str:
    """date(2026, 11, 1) -> "Nov/26"."""
    return f"{MESES[d.month - 1]}/{d.year % 100:02d}"
