def ordem_agrupamento_dv() -> list[str]:
    return [
        "NOVO PRODUTO",
        "TOTAL 600ML",
        "TOTAL 1L",
        "TOTAL 300ML",
        "TOTAL 473ML",
        "TOTAL 350ML",
        "TOTAL 269ML",
        "TOTAL 250ML",
        "TOTAL 275ML",
        "TOTAL LN 330ML",
        "TOTAL LN 355ML",
        "TOTAL 600ML OW",
        "TOTAL CHOPP 30L",
        "TOTAL CHOPP 5L",
        "TOTAL CHOPP 50L",
        "TOTAL REFRI LATA TUPÃ",
        "TOTAL CAJUÍNA 450ML",
        "TOTAL AGUA",
    ]


def ordem_categ_dv() -> list[str]:
    return [
        "VOLUME TOTAL",
        "MARÉ",
        "MARÉ ULTIMATE",
        "CORAL ULTRA",
        "SERENA",
        "CORAL",
        "JANGADA",
        "BRISA",
        "FAROL",
        "CERVEJA RGB",
        "PREMIUM + MAINSTREAM",
        "CORAL + JANGADA",
        "SEGMENTO CRAFT",
        "SEGMENTO PREMIUM",
        "SEGMENTO ECONOMY",
        "SEGMENTO NAB",
        "MAR LN 330ML",
        "MAR LN 330ML 0,0%",
        "MAR LN 250ML",
        "MAR LN 350ML",
        "SERENA LN 330ML",
        "CORAL LN 275ML / 330ML",
        " ",
        "SKU/PDV ABP",
        "SKU/PDV REVENDA",
        "CORAL 600/MAR 600",
        "MAR 600/RGB TT",
        "MAR 0.0%/MAR TT",
        "FATURAMENTO OW",
        "FATURAMENTO RGB",
    ]


_RENOMEIO_VISUAL_CATEGORIA = {
    "SEGMENTO CRAFT": "CRAFT",
    "SEGMENTO PREMIUM": "PREMIUM",
    "SEGMENTO ECONOMY": "ECONOMY",
    "SEGMENTO NAB": "NAB",
}


def formatar_categoria_visual_dv(categoria: str) -> str:
    return _RENOMEIO_VISUAL_CATEGORIA.get(categoria, categoria)
