"""Caches do Comercial no MESMO formato do sistema original (nomes, colunas e
tipos), para as telas lerem sem saber que o dado é fictício.

Simula compra cliente a cliente, com o dia de cada compra: é o que permite ao
painel comparar "até o mesmo dia do ano passado".
"""

import json
import math
from datetime import date, datetime, timedelta

import polars as pl

from gerador import base as b
from gerador import publicos

REVENDA = "Natal"
CNPJ = "00000000000100"
MESES = 28  # mês corrente + 27: o painel olha até 24 meses para trás do mês escolhido

# Nordeste: verão e carnaval vendem mais, o meio do ano menos.
SAZONALIDADE = {
    1: 1.18,
    2: 1.22,
    3: 1.0,
    4: 0.94,
    5: 0.92,
    6: 0.97,
    7: 0.9,
    8: 0.9,
    9: 0.95,
    10: 1.0,
    11: 1.06,
    12: 1.3,
}

# Catálogo fictício na hierarquia que o painel espera.
# (código, produto, marca, canal, agrupamento, volume, unidades/caixa, litros/caixa, preço caixa,
#  segmento, segmento_2, segmento_3, cat_600, grupo_0, sku_grupo, peso de venda)
_S1 = "CORAL ULTRA + CORAL"
_S3 = "CORAL ULTRA + CORAL + JANGADA"
_RGB = "CERVEJA RGB"
CATALOGO = [
    (
        900101,
        "MARÉ 600ML OW CX12",
        "MARÉ",
        "OW",
        "TOTAL 600ML OW",
        "600ml",
        12,
        7.2,
        118.0,
        None,
        None,
        None,
        "MARÉ 600ml",
        None,
        None,
        2.2,
    ),
    (
        900102,
        "MARÉ LATA 350ML CX12",
        "MARÉ",
        "OW",
        "TOTAL 350ML",
        "350ml",
        12,
        4.2,
        64.0,
        None,
        None,
        None,
        None,
        None,
        None,
        3.0,
    ),
    (
        900103,
        "MARÉ LATA 269ML CX8",
        "MARÉ",
        "OW",
        "TOTAL 269ML",
        "269ml",
        8,
        2.152,
        33.0,
        None,
        None,
        None,
        None,
        None,
        None,
        1.8,
    ),
    (
        900104,
        "MARÉ LATA 473ML CX12",
        "MARÉ",
        "OW",
        "TOTAL 473ML",
        "473ml",
        12,
        5.676,
        82.0,
        None,
        None,
        None,
        None,
        None,
        None,
        1.4,
    ),
    (
        900105,
        "MARÉ LN 250ML CX24",
        "MARÉ",
        "OW",
        "TOTAL 250ML",
        "250ml",
        24,
        6.0,
        112.0,
        None,
        None,
        None,
        None,
        None,
        "MAR LN 250ML",
        1.2,
    ),
    (
        900106,
        "MARÉ LN 330ML CX24",
        "MARÉ",
        "OW",
        "TOTAL LN 330ML",
        "330ml",
        24,
        7.92,
        139.0,
        None,
        None,
        None,
        None,
        None,
        "MAR LN 330ML",
        2.6,
    ),
    (
        900107,
        "MARÉ ZERO LN 330ML CX24",
        "MARÉ",
        "OW",
        "TOTAL LN 330ML",
        "330ml",
        24,
        7.92,
        141.0,
        None,
        None,
        None,
        None,
        "0%",
        "MAR LN 330ML 0,0%",
        0.7,
    ),
    (
        900108,
        "MARÉ ZERO LATA 269ML CX8",
        "MARÉ",
        "OW",
        "TOTAL 269ML",
        "269ml",
        8,
        2.152,
        35.0,
        None,
        None,
        None,
        None,
        "0%",
        "MAR LN 269ML 0,0%",
        0.5,
    ),
    (
        900109,
        "MARÉ ZERO LATA 350ML CX12",
        "MARÉ",
        "OW",
        "TOTAL 350ML",
        "350ml",
        12,
        4.2,
        66.0,
        None,
        None,
        None,
        None,
        "0%",
        "MAR LN 350ML 0,0%",
        0.5,
    ),
    (
        900110,
        "MARÉ 600ML RT CX24",
        "MARÉ",
        "RGB",
        "TOTAL 600ML",
        "600ml",
        24,
        14.4,
        168.0,
        None,
        _RGB,
        None,
        "MARÉ 600ml",
        None,
        "MARÉ 600 RT",
        2.4,
    ),
    (
        900111,
        "MARÉ CHOPP BARRIL 50L",
        "MARÉ",
        "CHOPP",
        "TOTAL CHOPP 50L",
        "50l",
        1,
        50.0,
        690.0,
        None,
        None,
        None,
        None,
        None,
        None,
        0.25,
    ),
    (
        900112,
        "MARÉ CHOPP BARRIL 30L",
        "MARÉ",
        "CHOPP",
        "TOTAL CHOPP 30L",
        "30l",
        1,
        30.0,
        430.0,
        None,
        None,
        None,
        None,
        None,
        None,
        0.2,
    ),
    (
        900121,
        "MARÉ ULTIMATE LN 330ML CX24",
        "MARÉ ULTIMATE",
        "OW",
        "TOTAL LN 330ML",
        "330ml",
        24,
        7.92,
        133.0,
        None,
        None,
        None,
        None,
        None,
        "MAR LN 330ML",
        0.9,
    ),
    (
        900201,
        "CORAL 600ML OW CX12",
        "CORAL",
        "OW",
        "TOTAL 600ML OW",
        "600ml",
        12,
        7.2,
        92.0,
        _S1,
        None,
        _S3,
        "CORAL 600ml",
        None,
        None,
        1.8,
    ),
    (
        900202,
        "CORAL LATA 269ML CX12",
        "CORAL",
        "OW",
        "TOTAL 269ML",
        "269ml",
        12,
        3.228,
        38.0,
        _S1,
        None,
        _S3,
        None,
        None,
        None,
        3.2,
    ),
    (
        900203,
        "CORAL LATA 473ML CX12",
        "CORAL",
        "OW",
        "TOTAL 473ML",
        "473ml",
        12,
        5.676,
        61.0,
        _S1,
        None,
        _S3,
        None,
        None,
        None,
        1.6,
    ),
    (
        900204,
        "CORAL LN 350ML CX12",
        "CORAL",
        "OW",
        "TOTAL 350ML",
        "350ml",
        12,
        4.2,
        52.0,
        _S1,
        None,
        _S3,
        None,
        None,
        "CORAL LN 350ML",
        1.5,
    ),
    (
        900205,
        "CORAL 1L RT CX12",
        "CORAL",
        "RGB",
        "TOTAL 1L",
        "1l",
        12,
        12.0,
        98.0,
        _S1,
        _RGB,
        _S3,
        None,
        None,
        None,
        1.4,
    ),
    (
        900206,
        "CORAL 300ML RT CX24",
        "CORAL",
        "RGB",
        "TOTAL 300ML",
        "300ml",
        24,
        7.2,
        71.0,
        _S1,
        _RGB,
        _S3,
        None,
        None,
        None,
        1.3,
    ),
    (
        900207,
        "CORAL 600ML RT CX24",
        "CORAL",
        "RGB",
        "TOTAL 600ML",
        "600ml",
        24,
        14.4,
        129.0,
        _S1,
        _RGB,
        _S3,
        "CORAL 600ml",
        None,
        "CORAL 600 RT",
        2.6,
    ),
    (
        900208,
        "CORAL CHOPP BARRIL 30L",
        "CORAL",
        "CHOPP",
        "TOTAL CHOPP 30L",
        "30l",
        1,
        30.0,
        330.0,
        _S1,
        None,
        _S3,
        None,
        None,
        None,
        0.2,
    ),
    (
        900221,
        "CORAL ULTRA LATA 350ML CX12",
        "CORAL ULTRA",
        "OW",
        "TOTAL 350ML",
        "350ml",
        12,
        4.2,
        58.0,
        _S1,
        None,
        _S3,
        None,
        None,
        None,
        1.3,
    ),
    (
        900222,
        "CORAL ULTRA LATA 269ML CX12",
        "CORAL ULTRA",
        "OW",
        "TOTAL 269ML",
        "269ml",
        12,
        3.228,
        43.0,
        _S1,
        None,
        _S3,
        None,
        None,
        None,
        0.9,
    ),
    (
        900223,
        "CORAL ULTRA LN 275ML CX12",
        "CORAL ULTRA",
        "OW",
        "TOTAL 275ML",
        "275ml",
        12,
        3.3,
        47.0,
        _S1,
        None,
        _S3,
        None,
        None,
        "CORAL LN 275ML",
        1.1,
    ),
    (
        900224,
        "CORAL ULTRA LN 330ML CX24",
        "CORAL ULTRA",
        "OW",
        "TOTAL LN 330ML",
        "330ml",
        24,
        7.92,
        102.0,
        _S1,
        None,
        _S3,
        None,
        None,
        "CORAL LN 330ML",
        0.5,
    ),
    (
        900301,
        "JANGADA LATA 350ML CX12",
        "JANGADA",
        "OW",
        "TOTAL 350ML",
        "350ml",
        12,
        4.2,
        44.0,
        None,
        None,
        _S3,
        None,
        None,
        None,
        2.4,
    ),
    (
        900302,
        "JANGADA LATA 269ML CX12",
        "JANGADA",
        "OW",
        "TOTAL 269ML",
        "269ml",
        12,
        3.228,
        34.0,
        None,
        None,
        _S3,
        None,
        None,
        None,
        2.0,
    ),
    (
        900303,
        "JANGADA LATÃO 473ML CX12",
        "JANGADA",
        "OW",
        "TOTAL 473ML",
        "473lt",
        12,
        5.676,
        52.0,
        None,
        None,
        _S3,
        None,
        None,
        None,
        1.0,
    ),
    (
        900304,
        "JANGADA 1L RT CX12",
        "JANGADA",
        "RGB",
        "TOTAL 1L",
        "1l",
        12,
        12.0,
        86.0,
        None,
        _RGB,
        _S3,
        None,
        None,
        None,
        1.2,
    ),
    (
        900305,
        "JANGADA 300ML RT CX24",
        "JANGADA",
        "RGB",
        "TOTAL 300ML",
        "300ml",
        24,
        7.2,
        63.0,
        None,
        _RGB,
        _S3,
        None,
        None,
        None,
        1.0,
    ),
    (
        900306,
        "JANGADA 600ML RT CX24",
        "JANGADA",
        "RGB",
        "TOTAL 600ML",
        "600ml",
        24,
        14.4,
        112.0,
        None,
        _RGB,
        _S3,
        "JANGADA 600ml",
        None,
        "JANGADA 600 RT",
        2.0,
    ),
    (
        900307,
        "JANGADA CHOPP BARRIL 30L",
        "JANGADA",
        "CHOPP",
        "TOTAL CHOPP 30L",
        "30l",
        1,
        30.0,
        300.0,
        None,
        None,
        _S3,
        None,
        None,
        None,
        0.15,
    ),
    (
        900401,
        "SERENA LN 330ML CX24",
        "SERENA",
        "OW",
        "TOTAL LN 330ML",
        "330ml",
        24,
        7.92,
        125.0,
        None,
        None,
        None,
        None,
        None,
        "SERENA LN 330ML",
        0.8,
    ),
    (
        900501,
        "BRISA LATA 350ML CX12",
        "BRISA",
        "OW",
        "TOTAL 350ML",
        "350ml",
        12,
        4.2,
        40.0,
        None,
        None,
        None,
        None,
        None,
        None,
        1.5,
    ),
    (
        900502,
        "BRISA 600ML RT CX24",
        "BRISA",
        "RGB",
        "TOTAL 600ML",
        "600ml",
        24,
        14.4,
        98.0,
        None,
        _RGB,
        None,
        None,
        None,
        None,
        1.3,
    ),
    (
        900503,
        "BRISA 1L RT CX12",
        "BRISA",
        "RGB",
        "TOTAL 1L",
        "1l",
        12,
        12.0,
        79.0,
        None,
        _RGB,
        None,
        None,
        None,
        None,
        1.0,
    ),
    (
        900601,
        "FAROL LATA 350ML CX12",
        "FAROL",
        "OW",
        "TOTAL 350ML",
        "350ml",
        12,
        4.2,
        39.0,
        None,
        None,
        None,
        None,
        None,
        None,
        1.8,
    ),
    (
        900602,
        "FAROL LATA 269ML CX12",
        "FAROL",
        "OW",
        "TOTAL 269ML",
        "269ml",
        12,
        3.228,
        30.0,
        None,
        None,
        None,
        None,
        None,
        None,
        1.4,
    ),
    (
        900603,
        "FAROL LATÃO 473ML CX12",
        "FAROL",
        "OW",
        "TOTAL 473ML",
        "473ml",
        12,
        5.676,
        47.0,
        None,
        None,
        None,
        None,
        None,
        None,
        0.8,
    ),
    (
        900604,
        "FAROL 600ML RT CX24",
        "FAROL",
        "RGB",
        "TOTAL 600ML",
        "600ml",
        24,
        14.4,
        94.0,
        None,
        _RGB,
        None,
        None,
        None,
        None,
        1.2,
    ),
    (
        900605,
        "FAROL 1L RT CX12",
        "FAROL",
        "RGB",
        "TOTAL 1L",
        "1l",
        12,
        12.0,
        76.0,
        None,
        _RGB,
        None,
        None,
        None,
        None,
        0.9,
    ),
    (
        900701,
        "IPÊ 600ML CX12",
        "IPÊ",
        "OW",
        "TOTAL 600ML OW",
        "600ml",
        12,
        7.2,
        150.0,
        None,
        None,
        None,
        None,
        None,
        None,
        0.3,
    ),
    (
        900702,
        "IPÊ LATA 350ML CX12",
        "IPÊ",
        "OW",
        "TOTAL 350ML",
        "350ml",
        12,
        4.2,
        88.0,
        None,
        None,
        None,
        None,
        None,
        None,
        0.3,
    ),
    (
        900711,
        "LUA AZUL LATA 350ML CX12",
        "LUA AZUL",
        "OW",
        "TOTAL 350ML",
        "350ml",
        12,
        4.2,
        92.0,
        None,
        None,
        None,
        None,
        None,
        None,
        0.3,
    ),
    (
        900712,
        "LUA AZUL LN 355ML CX24",
        "LUA AZUL",
        "OW",
        "TOTAL LN 355ML",
        "355ml",
        24,
        8.52,
        186.0,
        None,
        None,
        None,
        None,
        None,
        "LUA AZUL 355ML",
        0.25,
    ),
    (
        900721,
        "MANDACARU LN 355ML CX12",
        "MANDACARU",
        "OW",
        "TOTAL LN 355ML",
        "355ml",
        12,
        4.26,
        101.0,
        None,
        None,
        None,
        None,
        None,
        None,
        0.2,
    ),
    (
        900722,
        "MANDACARU LATA 350ML CX12",
        "MANDACARU",
        "OW",
        "TOTAL 350ML",
        "350ml",
        12,
        4.2,
        96.0,
        None,
        None,
        None,
        None,
        None,
        None,
        0.2,
    ),
    (
        900801,
        "ÁGUA FAROL 500ML CX12",
        "AGUA FAROL",
        "NAB",
        "TOTAL AGUA",
        "500ml",
        12,
        6.0,
        14.0,
        None,
        None,
        None,
        None,
        None,
        None,
        1.2,
    ),
    (
        900802,
        "TUPÃ GUARANÁ LATA 350ML CX12",
        "TUPÃ",
        "NAB",
        "TOTAL REFRI LATA TUPÃ",
        "350ml",
        12,
        4.2,
        29.0,
        None,
        None,
        None,
        None,
        None,
        None,
        1.4,
    ),
    (
        900803,
        "CAJUÍNA 450ML CX12",
        "CAJUÍNA",
        "NAB",
        "TOTAL CAJUÍNA 450ML",
        "450ml",
        12,
        5.4,
        33.0,
        None,
        None,
        None,
        None,
        None,
        None,
        0.8,
    ),
    (
        900804,
        "VIVA REFRI LATA 350ML CX12",
        "VIVA",
        "NAB",
        None,
        "350ml",
        12,
        4.2,
        26.0,
        None,
        None,
        None,
        None,
        None,
        None,
        0.6,
    ),
    (
        900805,
        "FAROL REFRI LATA 350ML CX12",
        "FAROL",
        "NAB",
        None,
        "350ml",
        12,
        4.2,
        27.0,
        None,
        None,
        None,
        None,
        None,
        None,
        0.6,
    ),
    (900901, "OUTRO 1L CX12", "OUTRO", "OUTRO", None, "1l", 12, 12.0, 55.0, None, None, None, None, None, None, 0.3),
    (
        900902,
        "OUTRO 300ML CX12",
        "OUTRO",
        "OUTRO",
        None,
        "300ml",
        12,
        3.6,
        24.0,
        None,
        None,
        None,
        None,
        None,
        None,
        0.3,
    ),
]
COLUNAS_CATALOGO = [
    "CODRED",
    "PRODUTO",
    "MARCA",
    "CANAL",
    "AGRUPAMENTO_VOLUME",
    "VOLUME",
    "UNIDADE",
    "LITRAGEM",
    "PRECO",
    "SEGMENTO",
    "SEGMENTO_2",
    "SEGMENTO_3",
    "CAT_600",
    "GRUPO_0",
    "SKU_GRUPO",
    "PESO",
]
PREMIUM = {"MARÉ", "MARÉ ULTIMATE", "CORAL ULTRA", "SERENA"}
SKUS_CORAL_LN = {"CORAL LN 275ML", "CORAL LN 330ML"}


# Segmentos com os nomes que o painel lista (a tela ignora os que não estão na ordem dela).
SEGMENTO_DA_MARCA = {
    "MARÉ": "SEGMENTO PREMIUM",
    "MARÉ ULTIMATE": "SEGMENTO PREMIUM",
    "CORAL ULTRA": "SEGMENTO PREMIUM",
    "SERENA": "SEGMENTO PREMIUM",
    "CORAL": "SEGMENTO ECONOMY",
    "JANGADA": "SEGMENTO ECONOMY",
    "BRISA": "SEGMENTO ECONOMY",
    "FAROL": "SEGMENTO ECONOMY",
    "IPÊ": "SEGMENTO CRAFT",
    "LUA AZUL": "SEGMENTO CRAFT",
    "MANDACARU": "SEGMENTO CRAFT",
}
SEGMENTO_3_DA_MARCA = {
    "CORAL": "CORAL + JANGADA",
    "JANGADA": "CORAL + JANGADA",
    "MARÉ": "PREMIUM + MAINSTREAM",
    "MARÉ ULTIMATE": "PREMIUM + MAINSTREAM",
    "CORAL ULTRA": "PREMIUM + MAINSTREAM",
    "SERENA": "PREMIUM + MAINSTREAM",
}


def _catalogo() -> pl.DataFrame:
    df = pl.DataFrame([dict(zip(COLUNAS_CATALOGO, c)) for c in CATALOGO], infer_schema_length=None)
    df = df.with_columns(
        pl.when(pl.col("CANAL") == "NAB")
        .then(pl.lit("SEGMENTO NAB"))
        .otherwise(pl.col("MARCA").replace_strict(SEGMENTO_DA_MARCA, default=None))
        .alias("SEGMENTO"),
        pl.col("MARCA").replace_strict(SEGMENTO_3_DA_MARCA, default=None).alias("SEGMENTO_3"),
    )
    return df.with_columns(
        pl.col("CODRED").cast(pl.String),
        pl.col("CODRED").cast(pl.String).alias("CODCOMP"),
        pl.when(pl.col("CANAL") == "OUTRO")
        .then(pl.lit("OUTRO VOLUMES"))
        .otherwise(pl.lit("VOLUME TOTAL"))
        .alias("VOLUME_TOTAL"),
    )


def _equipe() -> pl.DataFrame:
    linhas = []
    for g in range(4):
        for v in range(5):
            linhas.append({"GA": f"{(g + 1) * 10:03d}", "VEN": f"{100 + g * 5 + v + 1:03d}"})
    return pl.DataFrame(linhas)


_PREFIXOS = {
    "BAR": ["BAR DO", "BAR DA", "BOTECO DO", "ESPETINHO DO"],
    "RESTAURANTE": ["RESTAURANTE", "PEIXARIA", "CHURRASCARIA"],
    "MERCADO": ["MERCADINHO", "MERCEARIA", "MINIBOX", "SUPERMERCADO"],
    "CONVENIENCIA": ["CONVENIÊNCIA", "ADEGA", "POSTO E CONVENIÊNCIA"],
    "ATACADO": ["DISTRIBUIDORA", "ATACADÃO", "DEPÓSITO"],
}
_PESO_CANAL = {"BAR": 42, "RESTAURANTE": 14, "MERCADO": 28, "CONVENIENCIA": 11, "ATACADO": 5}


CIDADES_TERRITORIO = 90


def _territorio() -> pl.DataFrame:
    """As cidades mais próximas da sede: território contíguo, como o de uma revenda real."""
    return b.cidades_da_filial(b.FILIAIS[0], vizinhas=CIDADES_TERRITORIO, interior=0)


def _clientes(equipe: pl.DataFrame) -> list[dict]:
    r = b.rng("comercial-clientes")
    f = b.faker("comercial-clientes")
    vendedores = equipe.to_dicts()
    cidades = _territorio().to_dicts()
    populacao = publicos.populacao_uf(b.FILIAIS[0].uf)
    # Mais cliente onde tem mais gente, e menos quanto mais longe da sede (distância em graus).
    pesos_cidade = [populacao.get(c["codigo_ibge"], 0) * math.exp(-c["distancia"] * 111 / 200) for c in cidades]
    clientes = []
    for i in range(2600):
        ven = r.choice(vendedores)
        inicio = b.HOJE - timedelta(days=int(r.triangular(20, 1900, 1400)))
        parou = None if r.random() > 0.14 else b.meses_atras(b.HOJE, r.randint(1, 14))
        canal = r.choices(list(_PESO_CANAL), weights=list(_PESO_CANAL.values()))[0]
        prefixo = r.choice(_PREFIXOS[canal])
        sobrenome = f.last_name().upper()
        porte = r.paretovariate(2.2) * (2.5 if canal == "ATACADO" else 1.0)
        cidade = r.choices(cidades, weights=pesos_cidade)[0]
        clientes.append(
            {
                "CODCLI": 20000 + i,
                "GA": ven["GA"],
                "VEN": ven["VEN"],
                "inicio": b.inicio_do_mes(inicio),
                "parou": parou,
                "porte": porte,
                "NOME": f"{prefixo} {f.first_name().upper() if canal == 'BAR' else sobrenome} LTDA"
                if canal in ("ATACADO", "MERCADO")
                else f"{prefixo} {f.first_name().upper()}",
                "FANTASIA": f"{prefixo} {sobrenome}",
                "CANAL_CLI": canal,
                "CIDADE": cidade["nome"].upper(),
                "COD_IBGE": cidade["codigo_ibge"],
                "LAT": cidade["latitude"],
                "LON": cidade["longitude"],
                "PORTE": "GRANDE" if porte > 3 else "MEDIO" if porte > 1.6 else "PEQUENO",
                "TIPO_DOC": "CPF" if canal == "BAR" and r.random() < 0.35 else "CNPJ",
                "DIAS_PRAZO": r.choice(["0", "7", "14", "21", "28"]),
            }
        )
    return clientes


def _compras(clientes: list[dict], catalogo: pl.DataFrame) -> pl.DataFrame:
    """Uma linha por cliente, produto e dia de compra."""
    r = b.rng("comercial-compras")
    prods = catalogo.to_dicts()
    pesos = [p["PESO"] for p in prods]
    hoje = b.HOJE
    linhas = []
    for c in clientes:
        mix = set(r.choices(range(len(prods)), weights=pesos, k=r.randint(3, 9)))
        for m in range(MESES - 1, -1, -1):
            mes = b.meses_atras(hoje, m)
            if mes < c["inicio"] or (c["parou"] and mes >= c["parou"]):
                continue
            if r.random() > 0.85:
                continue
            if r.random() < 0.05:
                mix.add(r.choices(range(len(prods)), weights=pesos)[0])
            ultimo_dia = b.fim_do_mes(mes).day
            # Vendas a cada semana ou quinzena: 1 a 3 pedidos no mês.
            dias = sorted(r.sample(range(1, ultimo_dia + 1), k=r.choice([1, 2, 2, 3])))
            crescimento = 1 + 0.05 * (MESES - 1 - m) / 12
            inflacao = 1 + 0.0045 * (MESES - 1 - m)
            fator = c["porte"] * SAZONALIDADE[mes.month] * crescimento / len(dias)
            for dia in dias:
                data = mes.replace(day=dia)
                if data > hoje:
                    continue
                for i in mix:
                    if r.random() > 0.78:
                        continue
                    p = prods[i]
                    caixas = max(1, round(r.gammavariate(2.0, 2.4) * fator * p["PESO"] / 2))
                    linhas.append(
                        (
                            mes.strftime("%Y%m"),
                            dia,
                            c["CODCLI"],
                            c["GA"],
                            c["VEN"],
                            p["CODRED"],
                            caixas,
                            round(caixas * p["PRECO"] * inflacao * (1 - r.uniform(0, 0.07)), 2),
                        )
                    )
    return pl.DataFrame(
        linhas, schema=["MES", "DIA", "CODCLI", "GA", "VEN", "CODRED", "QTD", "VALOR"], orient="row"
    ).join(catalogo, on="CODRED")


def _dias_uteis(mes: str) -> tuple[float, float]:
    inicio = date(int(mes[:4]), int(mes[4:]), 1)
    uteis = b.dias_uteis(inicio, b.fim_do_mes(inicio))
    return float(len(uteis)), float(sum(1 for d in uteis if d <= b.HOJE))


def _diario_venda(compras: pl.DataFrame, catalogo: pl.DataFrame) -> pl.DataFrame:
    dia_hoje = b.HOJE.day
    dias = pl.DataFrame(
        [(m, *_dias_uteis(m)) for m in compras["MES"].unique().to_list()],
        schema=["MES", "DIAS_UTEIS", "DIAS_UTEIS_ATUAL"],
        orient="row",
    )
    ate_dia = pl.col("DIA") <= dia_hoje
    agregado = compras.group_by("MES", "CODRED", "VEN", "GA").agg(
        pl.col("QTD").sum().cast(pl.Float64).alias("QTD_TOTAL"),
        pl.col("QTD").filter(ate_dia).sum().cast(pl.Float64).alias("QTD_TOTAL_AA"),
        (pl.col("QTD") * pl.col("UNIDADE")).filter(ate_dia).sum().cast(pl.Float64).alias("QTDS_TOTAL_AA"),
        pl.col("VALOR").sum().alias("FATURAMENTO"),
    )
    return (
        agregado.join(catalogo, on="CODRED")
        .join(dias, on="MES")
        .with_columns(
            pl.lit(CNPJ).alias("CNPJ_REV"),
            pl.lit(REVENDA).alias("REVENDA"),
            pl.lit(None, pl.String).alias("BASE_FOCO"),
            (pl.col("FATURAMENTO") * 0.96).round(2).alias("VALOR_VENDA"),
            (pl.col("QTD_TOTAL") * pl.col("LITRAGEM") / 100).alias("QTD_TOTAL_HL"),
            (pl.col("QTD_TOTAL_AA") * pl.col("LITRAGEM") / 100).alias("QTD_TOTAL_HL_AA"),
            (
                pl.col("DIAS_UTEIS")
                / pl.when(pl.col("DIAS_UTEIS_ATUAL") > 0).then(pl.col("DIAS_UTEIS_ATUAL")).otherwise(1)
            ).alias("_fator"),
        )
        .with_columns(
            (pl.col("QTD_TOTAL_HL") * pl.col("_fator")).alias("TEND_HL"),
            (pl.col("QTD_TOTAL") * pl.col("_fator")).alias("TEND_UMB"),
        )
        .select(
            "CODRED",
            "VEN",
            "GA",
            "CNPJ_REV",
            "MES",
            "REVENDA",
            "CODCOMP",
            "SEGMENTO",
            "SEGMENTO_2",
            "SEGMENTO_3",
            "CANAL",
            "AGRUPAMENTO_VOLUME",
            "CAT_600",
            "GRUPO_0",
            "MARCA",
            "SKU_GRUPO",
            "VOLUME",
            "VOLUME_TOTAL",
            pl.col("UNIDADE").cast(pl.Int64),
            "LITRAGEM",
            "PRODUTO",
            "DIAS_UTEIS",
            "DIAS_UTEIS_ATUAL",
            "BASE_FOCO",
            "QTD_TOTAL",
            "QTD_TOTAL_AA",
            "QTDS_TOTAL_AA",
            "FATURAMENTO",
            "VALOR_VENDA",
            "QTD_TOTAL_HL",
            "QTD_TOTAL_HL_AA",
            "TEND_HL",
            "TEND_UMB",
        )
        .sort("MES", "VEN", "CODRED")
    )


def _categorias_longas(compras: pl.DataFrame) -> pl.DataFrame:
    """Cada compra repetida em todas as categorias de cobertura dela (TIPO, CATEGORIA)."""
    base = compras.select(
        "MES",
        "DIA",
        "CODCLI",
        "GA",
        "VEN",
        "CODRED",
        "MARCA",
        "SEGMENTO",
        "SEGMENTO_2",
        "SEGMENTO_3",
        "SKU_GRUPO",
        "CAT_600",
        "GRUPO_0",
        "CANAL",
        "VOLUME_TOTAL",
    )
    partes = [
        base.select(*_chave(), pl.lit("VOLUME_TOTAL").alias("TIPO"), pl.col("VOLUME_TOTAL").alias("CATEGORIA")),
        base.select(*_chave(), pl.lit("CANAL").alias("TIPO"), pl.col("CANAL").alias("CATEGORIA")),
    ]
    for tipo in ("MARCA", "SEGMENTO", "SEGMENTO_2", "SEGMENTO_3", "SKU_GRUPO", "CAT_600", "GRUPO_0"):
        partes.append(base.select(*_chave(), pl.lit(tipo).alias("TIPO"), pl.col(tipo).alias("CATEGORIA")))
    partes.append(
        base.filter(pl.col("SKU_GRUPO").is_in(list(SKUS_CORAL_LN))).select(
            *_chave(), pl.lit("SKU_GRUPO_COMB").alias("TIPO"), pl.lit("CORAL LN 275ML / 330ML").alias("CATEGORIA")
        )
    )
    partes.append(
        base.filter(pl.col("MARCA").is_in(list(PREMIUM))).select(
            *_chave(), pl.lit("SEGMENTO_PREMIUM").alias("TIPO"), pl.lit("PREMIUM").alias("CATEGORIA")
        )
    )
    abp = (
        pl.when((pl.col("MARCA") == "CORAL") & (pl.col("CANAL") == "RGB"))
        .then(pl.lit("CORAL RETORNAVEL"))
        .when((pl.col("MARCA") == "MARÉ") & (pl.col("CANAL") == "RGB"))
        .then(pl.lit("MARÉ RETORNAVEL"))
    )
    partes.append(base.select(*_chave(), pl.lit("CATEG_ABP").alias("TIPO"), abp.alias("CATEGORIA")))
    partes.append(
        base.filter(pl.col("CANAL").is_in(["RGB", "CHOPP"])).select(
            *_chave(), pl.lit("CATEG_ABP").alias("TIPO"), pl.lit("CERV RGB + CHOPP").alias("CATEGORIA")
        )
    )
    return pl.concat(partes).filter(pl.col("CATEGORIA").is_not_null())


def _chave() -> list[pl.Expr]:
    return [pl.col(c) for c in ("MES", "DIA", "CODCLI", "GA", "VEN")]


def _contar(df: pl.DataFrame, grupo: list[str], nome: str, com_aa: bool) -> pl.DataFrame:
    aggs = [pl.col("CODCLI").n_unique().alias(nome)]
    if com_aa:
        aggs.append(pl.col("CODCLI").filter(pl.col("DIA") <= b.HOJE.day).n_unique().alias(f"{nome}_AA"))
    return df.group_by(grupo).agg(aggs)


def _coberturas(compras: pl.DataFrame) -> dict[str, pl.DataFrame]:
    longas = _categorias_longas(compras).with_columns(
        pl.lit(REVENDA).alias("REVENDA"), pl.lit(None, pl.String).alias("BASE_FOCO")
    )
    saida = {}
    for sufixo, extra in (("", ["GA", "VEN"]), ("_ga", ["GA"]), ("_rev", [])):
        grupo = ["TIPO", "CATEGORIA", "REVENDA", "MES", *extra, "BASE_FOCO"]
        saida[f"tb_cob_categ{sufixo}"] = _contar(longas, grupo, "COB_CAT", True).select(*grupo, "COB_CAT", "COB_CAT_AA")
    prod = compras.with_columns(pl.lit(REVENDA).alias("REVENDA"), pl.lit(None, pl.String).alias("BASE_FOCO"))
    for sufixo, extra in (("", ["GA", "VEN"]), ("_ga", ["GA"]), ("_rev", [])):
        grupo = ["CODRED", "REVENDA", "MES", *extra, "BASE_FOCO"]
        saida[f"tb_cob_prod{sufixo}"] = _contar(prod, grupo, "COB_PROD", True).select(*grupo, "COB_PROD", "COB_PROD_AA")
    return saida


def _carteira_ativa(clientes: list[dict], mes: str) -> list[dict]:
    m = date(int(mes[:4]), int(mes[4:]), 1)
    return [c for c in clientes if c["inicio"] <= m and not (c["parou"] and m >= c["parou"])]


def _indicadores_cliente(clientes: list[dict], compras: pl.DataFrame) -> dict[str, pl.DataFrame]:
    r = b.rng("comercial-fds")
    meses = sorted(compras["MES"].unique().to_list())
    sku_cli = compras.group_by("MES", "CODCLI", "GA", "VEN").agg(pl.col("CODRED").n_unique().alias("SKUS"))
    cob_cli = sku_cli.group_by("MES", "GA", "VEN").agg(pl.col("SKUS").sum().cast(pl.UInt32).alias("QTD_SKU_PDV"))
    ativos, fds, meta_abp = [], [], []
    for mes in meses:
        carteira = _carteira_ativa(clientes, mes)
        por_ven: dict[tuple, int] = {}
        for c in carteira:
            por_ven[(c["GA"], c["VEN"])] = por_ven.get((c["GA"], c["VEN"]), 0) + 1
        for (ga, ven), n in por_ven.items():
            ativos.append({"REVENDA": REVENDA, "MES": mes, "GA": ga, "VEN": ven, "BASE_FOCO": None, "QTD_PDV": n})
            # FDS: cada cliente faz de 0 a 100 pontos no sortimento obrigatório.
            pontos = sum(min(100, max(0, r.gauss(52, 22))) for _ in range(n))
            fds.append(
                {
                    "REVENDA": REVENDA,
                    "GA": ga,
                    "VEN": ven,
                    "MES": mes,
                    "TOTAL_GRUPOS": n * 100,
                    "GRUPOS_META": round(pontos, 2),
                    "QTD_CLI_ATIVOS": n,
                }
            )
        meta_abp.append({"REVENDA": REVENDA, "MES": mes, "VALOR": round(len(carteira) * r.uniform(0.85, 0.95))})
    cob_ativo = pl.DataFrame(ativos).with_columns(
        pl.col("QTD_PDV").cast(pl.UInt32), pl.col("BASE_FOCO").cast(pl.String)
    )
    return {
        "tb_cob_cli": cob_cli.with_columns(
            pl.lit(REVENDA).alias("REVENDA"), pl.lit(None, pl.String).alias("BASE_FOCO")
        ).select("REVENDA", "MES", "GA", "VEN", "BASE_FOCO", "QTD_SKU_PDV"),
        "tb_cob_cli_ativo": cob_ativo.select("REVENDA", "MES", "GA", "VEN", "BASE_FOCO", "QTD_PDV"),
        "tb_cob_rev": cob_ativo.group_by("REVENDA", "BASE_FOCO", "MES").agg(pl.col("QTD_PDV").sum()),
        "tb_exig_fds": pl.DataFrame(fds).with_columns(
            pl.col("TOTAL_GRUPOS").cast(pl.Int32), pl.col("QTD_CLI_ATIVOS").cast(pl.Int64)
        ),
        "TB_META_ABP": pl.DataFrame(meta_abp).with_columns(pl.col("VALOR").cast(pl.Float64)),
    }


def _metas(diario: pl.DataFrame, catalogo: pl.DataFrame) -> pl.DataFrame:
    """Meta da revenda por produto e vendedor: o mesmo mês do ano anterior, de -3% a +8%."""
    r = b.rng("comercial-metas")
    linhas = []
    for m in range(0, 5):
        mes = b.meses_atras(b.HOJE, m)
        base = diario.filter(pl.col("MES") == b.meses_atras(mes, 12).strftime("%Y%m"))
        for row in base.iter_rows(named=True):
            umb = round(row["QTD_TOTAL"] * r.uniform(0.97, 1.08))
            linhas.append(
                {
                    "MES": mes.strftime("%Y%m"),
                    "CODRED": row["CODRED"],
                    "VEN": row["VEN"],
                    "GA": row["GA"],
                    "QTD_META_REVENDA_UMB": umb,
                }
            )
    metas = pl.DataFrame(linhas).join(catalogo, on="CODRED")
    return metas.with_columns(
        pl.col("CODCOMP").cast(pl.Int64),
        pl.col("UNIDADE").cast(pl.Int64),
        pl.lit(REVENDA).alias("REVENDA"),
        (pl.col("QTD_META_REVENDA_UMB") * pl.col("UNIDADE")).cast(pl.Int64).alias("QTDS"),
        pl.lit(CNPJ).alias("CNPJ_REV"),
        pl.lit("9001").alias("LICENCA"),
        (pl.col("QTD_META_REVENDA_UMB") * pl.col("LITRAGEM") / 100).alias("QTD_META_REVENDA_HL"),
        pl.col("QTD_META_REVENDA_UMB").cast(pl.Int64),
    ).select(
        "CODCOMP",
        "CODRED",
        "SEGMENTO",
        "SEGMENTO_2",
        "SEGMENTO_3",
        "CANAL",
        "AGRUPAMENTO_VOLUME",
        "MARCA",
        "SKU_GRUPO",
        "VOLUME_TOTAL",
        "UNIDADE",
        "LITRAGEM",
        "REVENDA",
        "PRODUTO",
        "MES",
        "VEN",
        "QTD_META_REVENDA_UMB",
        "QTDS",
        "CNPJ_REV",
        "LICENCA",
        "GA",
        "QTD_META_REVENDA_HL",
    )


def _compra_prod(diario: pl.DataFrame, catalogo: pl.DataFrame) -> pl.DataFrame:
    """Sell-in: o que a revenda comprou da fábrica, perto do que vendeu."""
    r = b.rng("comercial-sellin")
    venda = diario.group_by("MES", "CODRED").agg(pl.col("QTD_TOTAL").sum())
    fator = pl.Series([r.uniform(0.9, 1.12) for _ in range(venda.height)])
    return (
        venda.with_columns((pl.col("QTD_TOTAL") * fator).round(0).alias("QTD"))
        .join(catalogo, on="CODRED")
        .with_columns(
            (pl.col("QTD") * pl.col("LITRAGEM") / 100).round(2).alias("QTD_HL"), pl.lit(REVENDA).alias("REVENDA")
        )
        .select(
            "CODRED",
            "CODCOMP",
            "GRUPO_0",
            "CAT_600",
            "SEGMENTO",
            "SEGMENTO_2",
            "SEGMENTO_3",
            "CANAL",
            "AGRUPAMENTO_VOLUME",
            "MARCA",
            "SKU_GRUPO",
            "VOLUME",
            "VOLUME_TOTAL",
            "REVENDA",
            "PRODUTO",
            "MES",
            "QTD",
            "QTD_HL",
        )
    )


def _curva_abc(compras: pl.DataFrame, clientes: list[dict]) -> dict[str, pl.DataFrame]:
    """Uma linha por cliente, produto e mês, separada nas cinco janelas do pipeline original."""
    r = b.rng("comercial-curva")
    cad = pl.DataFrame(
        [
            {k: c[k] for k in ("CODCLI", "NOME", "FANTASIA", "TIPO_DOC", "CIDADE", "PORTE", "CANAL_CLI", "DIAS_PRAZO")}
            for c in clientes
        ]
    )
    doze = b.meses_atras(b.HOJE, 11).strftime("%Y%m")
    base = (
        compras.filter(pl.col("MES") >= doze)
        .group_by("MES", "CODCLI", "VEN", "GA", "CODRED", "PRODUTO", "LITRAGEM")
        .agg(pl.col("QTD").sum().cast(pl.Float64).alias("QTD_TOTAL"), pl.col("VALOR").sum().alias("FATURAMENTO"))
    )
    devolucao = pl.Series([r.random() < 0.04 for _ in range(base.height)])
    fracao = pl.Series([r.uniform(0.05, 0.4) for _ in range(base.height)])
    base = base.with_columns(
        pl.when(devolucao).then((pl.col("QTD_TOTAL") * fracao).round(0)).otherwise(0.0).alias("QTD_DEVOLUCAO"),
    ).with_columns(
        (pl.col("FATURAMENTO") * pl.col("QTD_DEVOLUCAO") / pl.col("QTD_TOTAL")).round(2).alias("VALOR_DEVOLUCAO"),
        (pl.col("QTD_TOTAL") * pl.col("LITRAGEM") / 100).alias("HL"),
        (pl.col("FATURAMENTO") * 0.96).round(2).alias("VALOR_VENDA"),
    )
    tabela = base.join(cad, on="CODCLI").select(
        pl.col("CODCLI").cast(pl.String),
        "NOME",
        "FANTASIA",
        "TIPO_DOC",
        "CIDADE",
        "PORTE",
        pl.col("CANAL_CLI").alias("CANAL"),
        "VEN",
        pl.col("GA").alias("SUBORDINACAO"),
        "DIAS_PRAZO",
        "HL",
        "FATURAMENTO",
        "VALOR_VENDA",
        "VALOR_DEVOLUCAO",
        "QTD_TOTAL",
        "QTD_DEVOLUCAO",
        "CODRED",
        pl.col("PRODUTO").alias("PRODUTO_GENERICO"),
        "MES",
        pl.lit(REVENDA).alias("REVENDA"),
        pl.lit(CNPJ).alias("CNPJ_REV"),
    )
    janelas = {}
    for n, nome in enumerate(["atual", "ultimo", "penultimo", "antepenultimo"]):
        mes = b.meses_atras(b.HOJE, n).strftime("%Y%m")
        janelas[nome] = tabela.filter(pl.col("MES") == mes)
    janelas["historico"] = tabela.filter(pl.col("MES") < b.meses_atras(b.HOJE, 3).strftime("%Y%m"))
    return janelas


MESES_MAPA = 12
_LOGRADOUROS = ["RUA", "RUA", "RUA", "AVENIDA", "TRAVESSA"]
INATIVA_APOS_MESES = 9  # quem para de comprar segue ativo no cadastro por esse tempo


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl, df = math.radians(lon2 - lon1), p2 - p1
    h = math.sin(df / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def _mapa(clientes: list[dict], compras: pl.DataFrame) -> dict[str, pl.DataFrame]:
    """Os cinco caches do Mapa Comercial: território, cobertura, venda e clientes."""
    r = b.rng("comercial-mapa")
    f = b.faker("comercial-mapa")
    uf = b.FILIAIS[0].uf
    populacao = publicos.populacao_uf(uf)
    geometria = {int(x["properties"]["codarea"]): x["geometry"] for x in publicos.malha_uf(uf)["features"]}
    territorio = _territorio().to_dicts()
    sede = territorio[0]
    cidades = []
    for c in territorio:
        dist = 0.0 if c is sede else round(_km(sede["latitude"], sede["longitude"], c["latitude"], c["longitude"]), 1)
        cidades.append(
            {
                "COD_IBGE": str(c["codigo_ibge"]),
                "CIDADE": c["nome"].upper(),
                "UF": uf,
                "REVENDA": REVENDA,
                "POPULACAO": populacao.get(c["codigo_ibge"], 0),
                "LATITUDE": c["latitude"],
                "LONGITUDE": c["longitude"],
                "SUBREVENDA": REVENDA,
                "CIDADE_SEDE": sede["nome"].upper(),
                "DIST_SEDE": dist,
                "CIDADE_FAB": sede["nome"].upper(),
                "DIST_FAB": dist,
                "GEOMETRY": json.dumps(geometria[c["codigo_ibge"]], separators=(",", ":")),
            }
        )
    tb_cidades = pl.DataFrame(cidades).with_columns(pl.col("POPULACAO").cast(pl.Int64))

    meses = [b.meses_atras(b.HOJE, n).strftime("%Y%m") for n in range(MESES_MAPA - 1, -1, -1)]
    cad = pl.DataFrame(
        [
            {
                "CODCLI": c["CODCLI"],
                "COD_IBGE": str(c["COD_IBGE"]),
                "CIDADE": c["CIDADE"],
                "PORTE": c["PORTE"],
                "CANAL_CLI": c["CANAL_CLI"],
            }
            for c in clientes
        ]
    )
    base = (
        compras.filter(pl.col("MES").is_in(meses))
        .join(cad, on="CODCLI")
        .with_columns(pl.col("SEGMENTO").fill_null("OUTROS"))
    )
    produto = ["MARCA", pl.col("CANAL").alias("CANAL_PROD"), "VOLUME", "SEGMENTO"]
    tb_cob = base.select(
        pl.lit(REVENDA).alias("REVENDA"),
        "COD_IBGE",
        "CIDADE",
        "MES",
        pl.col("CODCLI").cast(pl.String).alias("CLI"),
        "VEN",
        "GA",
        "PORTE",
        pl.col("CANAL_CLI").alias("CANAL"),
        *produto,
    ).unique()
    tb_pot = (
        base.group_by("GA", "VEN", "MES", "CIDADE", "COD_IBGE", "MARCA", "CANAL", "VOLUME", "SEGMENTO")
        .agg(
            pl.col("QTD").sum().cast(pl.Int64).alias("QTD_TOTAL"),
            pl.col("CODCLI").n_unique().cast(pl.UInt32).alias("QTD_CLI"),
            pl.col("VALOR").sum().round(2).alias("FATURAMENTO"),
            (pl.col("QTD") * pl.col("LITRAGEM") / 100).sum().alias("QTD_TOTAL_HL"),
        )
        .select(
            pl.lit(REVENDA).alias("REVENDA"),
            pl.lit(REVENDA).alias("SUBEMPRESA"),
            "GA",
            "VEN",
            "MES",
            "CIDADE",
            pl.lit(uf).alias("UF"),
            "COD_IBGE",
            pl.lit(CNPJ).alias("CNPJ_REV"),
            "MARCA",
            pl.col("CANAL").alias("CANAL_PROD"),
            "VOLUME",
            "SEGMENTO",
            "QTD_TOTAL",
            "QTD_CLI",
            pl.col("QTD_CLI").alias("QTD_CLI_COB"),
            "FATURAMENTO",
            "QTD_TOTAL_HL",
        )
    )

    datas = compras.select("CODCLI", (pl.col("MES") + pl.col("DIA").cast(pl.String).str.zfill(2)).alias("DATA"))
    ultima_por_mes = datas.group_by("CODCLI", pl.col("DATA").str.slice(0, 6).alias("MES")).agg(pl.col("DATA").max())
    fixos = {
        c["CODCLI"]: {
            "ENDERECO": f"{r.choice(_LOGRADOUROS)} {f.first_name().upper()} {f.last_name().upper()}, {r.randint(10, 2400)} - {f.bairro().upper()}",
            "TITULO_ABERTO": "SIM" if r.random() < 0.12 else "NAO",
            "POSSUI_CEV": "SIM" if r.random() < 0.3 else "NAO",
        }
        for c in clientes
    }
    ativos, inativos = [], []
    for mes in meses:
        m = date(int(mes[:4]), int(mes[4:]), 1)
        ultimas = dict(
            ultima_por_mes.filter(pl.col("MES") <= mes).group_by("CODCLI").agg(pl.col("DATA").max()).iter_rows()
        )
        for c in clientes:
            if c["inicio"] > m:
                continue
            inativo = c["parou"] and b.meses_atras(m, INATIVA_APOS_MESES) >= c["parou"]
            linha = {
                "REVENDA": REVENDA,
                "VEN": c["VEN"],
                "GA": c["GA"],
                "MES": mes,
                "CLI_ATIVO": str(c["CODCLI"]),
                "NOME": c["NOME"],
                "FANTASIA": c["FANTASIA"],
                "MUNICIPIO": c["CIDADE"],
                **fixos[c["CODCLI"]],
                "PORTE": c["PORTE"],
                "CANAL": c["CANAL_CLI"],
                "SUBEMPRESA": REVENDA,
                "ULTIMA_COMPRA": ultimas.get(c["CODCLI"]),
            }
            if inativo:
                inativos.append(linha)
            else:
                ativos.append({**linha, "CIDADE": c["CIDADE"], "UF": uf, "COD_IBGE": str(c["COD_IBGE"])})
    colunas = [
        "REVENDA",
        "VEN",
        "GA",
        "MES",
        "CLI_ATIVO",
        "NOME",
        "FANTASIA",
        "MUNICIPIO",
        "ENDERECO",
        "PORTE",
        "CANAL",
        "SUBEMPRESA",
        "ULTIMA_COMPRA",
        "TITULO_ABERTO",
        "POSSUI_CEV",
    ]
    esquema = {col: pl.String for col in colunas}
    return {
        "tb_cidades_rev": tb_cidades,
        "tb_cob_cid": tb_cob,
        "tb_mapa_pot": tb_pot,
        "tb_cli_ativos": pl.DataFrame(
            ativos, schema={**esquema, "CIDADE": pl.String, "UF": pl.String, "COD_IBGE": pl.String}
        ),
        "tb_cli_inativos": pl.DataFrame(inativos, schema=esquema),
    }


MESES_MARKUP = 13  # o mês corrente e os 12 anteriores


def _custo_por_caixa(catalogo: pl.DataFrame) -> pl.DataFrame:
    """Custo (CMV) de cada produto em cada mês: uma fração do preço de tabela, com a mesma inflação da venda.
    Cada produto tem a sua fração e o seu % de markup sugerido, para uns venderem acima e outros abaixo."""
    r = b.rng("comercial-markup")
    linhas = []
    for p in catalogo.select("CODRED", "PRECO").to_dicts():
        fracao = r.uniform(0.70, 0.80)
        sugerido = round(r.uniform(0.24, 0.36), 3)
        for m in range(MESES):
            mes = b.meses_atras(b.HOJE, m)
            inflacao = 1 + 0.0045 * (MESES - 1 - m)
            linhas.append((mes.strftime("%Y%m"), p["CODRED"], round(p["PRECO"] * fracao * inflacao, 4), sugerido))
    return pl.DataFrame(linhas, schema=["MES", "CODRED", "CUSTO_CX", "PCT_SUG"], orient="row")


def _markup(compras: pl.DataFrame, custo: pl.DataFrame) -> pl.DataFrame:
    """Markup por produto e mês: grandezas somáveis (a tela faz as razões)."""
    meses = [b.meses_atras(b.HOJE, m).strftime("%Y%m") for m in range(MESES_MARKUP)]
    return (
        compras.filter(pl.col("MES").is_in(meses))
        .join(custo, on=["MES", "CODRED"])
        .group_by("MES", "CODRED", "PRODUTO", "MARCA", "PCT_SUG")
        .agg(
            pl.col("QTD").sum().cast(pl.Float64).alias("QTD"),
            pl.col("VALOR").sum().round(2).alias("FAT"),
            (pl.col("QTD") * pl.col("CUSTO_CX")).sum().round(2).alias("CMV"),
        )
        .with_columns((pl.col("CMV") * (1 + pl.col("PCT_SUG"))).round(2).alias("FAT_SUG"))
        .sort("MES", "FAT", descending=[False, True])
    )


def _carteira(clientes: list[dict], compras: pl.DataFrame, custo: pl.DataFrame) -> pl.DataFrame:
    """Uma linha por cliente: faturamento do mês e de 12 meses, devolução, markup e última compra."""
    r = b.rng("comercial-carteira")
    mes_atual = b.HOJE.strftime("%Y%m")
    meses_12 = [b.meses_atras(b.HOJE, m).strftime("%Y%m") for m in range(12)]
    # Como no Mapa: quem para de comprar segue ativo no cadastro por INATIVA_APOS_MESES.
    ativos = {
        c["CODCLI"]
        for c in clientes
        if c["inicio"] <= b.HOJE and not (c["parou"] and c["parou"] <= b.meses_atras(b.HOJE, INATIVA_APOS_MESES))
    }
    por_cliente = (
        compras.filter(pl.col("MES").is_in(meses_12))
        .join(custo.select("MES", "CODRED", "CUSTO_CX"), on=["MES", "CODRED"])
        .group_by("CODCLI")
        .agg(
            pl.col("VALOR").filter(pl.col("MES") == mes_atual).sum().alias("FAT_MES"),
            pl.col("VALOR").sum().alias("FAT_12M"),
            (pl.col("QTD") * pl.col("CUSTO_CX")).sum().alias("CMV_12M"),
            pl.col("MES").n_unique().alias("MESES_COMPRANDO"),
        )
    )
    ultima_geral = compras.group_by("CODCLI").agg(
        (pl.col("MES") + pl.col("DIA").cast(pl.String).str.zfill(2)).max().alias("_ULTIMA_GERAL")
    )
    cadastro = pl.DataFrame(
        [
            {
                "CODCLI": c["CODCLI"],
                "CLIENTE": c["FANTASIA"],
                "VEN": c["VEN"],
                "GA": c["GA"],
                "CANAL": c["CANAL_CLI"],
                "CIDADE": c["CIDADE"],
                "PORTE": c["PORTE"],
                "ATIVO": c["CODCLI"] in ativos,
                # Devolução fictícia: a maioria devolve pouco, alguns devolvem bem mais.
                "_TAXA_DEV": min(r.betavariate(1.1, 55) * (4 if r.random() < 0.06 else 1), 0.25),
                "_DEV_NO_MES": r.random() < 0.3,
            }
            for c in clientes
        ]
    )
    return (
        cadastro.join(por_cliente, on="CODCLI", how="left")
        .join(ultima_geral, on="CODCLI", how="left")
        .with_columns(
            pl.col("FAT_MES", "FAT_12M", "CMV_12M").fill_null(0.0).round(2),
            pl.col("MESES_COMPRANDO").fill_null(0).cast(pl.Int32),
        )
        .with_columns(
            pl.when(pl.col("_DEV_NO_MES"))
            .then(pl.col("FAT_MES") * pl.col("_TAXA_DEV") * 1.6)
            .otherwise(0.0)
            .round(2)
            .alias("DEV_MES"),
            (pl.col("FAT_12M") * pl.col("_TAXA_DEV")).round(2).alias("DEV_12M"),
            pl.col("_ULTIMA_GERAL").str.strptime(pl.Date, "%Y%m%d").alias("ULTIMA_COMPRA"),
        )
        .select(
            "CODCLI",
            "CLIENTE",
            "VEN",
            "GA",
            "CANAL",
            "CIDADE",
            "PORTE",
            "ATIVO",
            "FAT_MES",
            "DEV_MES",
            "FAT_12M",
            "DEV_12M",
            "CMV_12M",
            "MESES_COMPRANDO",
            "ULTIMA_COMPRA",
        )
        .sort("FAT_12M", descending=True)
    )


def gerar() -> None:
    print("Comercial")
    catalogo = _catalogo()
    equipe = _equipe()
    clientes = _clientes(equipe)
    compras = _compras(clientes, catalogo)
    diario = _diario_venda(compras, catalogo)
    pasta = b.PY / "Comercial" / "data" / "bd_comercial"
    pasta.mkdir(parents=True, exist_ok=True)
    for antigo in pasta.glob("*.parquet"):
        antigo.unlink()

    def gravar(df: pl.DataFrame, nome: str) -> None:
        df.write_parquet(pasta / f"{nome}.parquet", compression="zstd")
        print(f"  bd_comercial/{nome}.parquet: {df.height:,} linhas".replace(",", "."))

    gravar(diario, "tb_diario_venda")
    for nome, df in _coberturas(compras).items():
        gravar(df, nome)
    for nome, df in _indicadores_cliente(clientes, compras).items():
        gravar(df, nome)
    for janela, df in _curva_abc(compras, clientes).items():
        gravar(df, f"tb_curva_abc_{CNPJ}_{janela}")
    for nome, df in _mapa(clientes, compras).items():
        gravar(df, nome)
    custo = _custo_por_caixa(catalogo)
    gravar(_markup(compras, custo), "tb_markup")
    gravar(_carteira(clientes, compras, custo), "tb_carteira")
    gravar(_metas(diario, catalogo), "tb_meta_revenda")
    gravar(_compra_prod(diario, catalogo), "tb_compra_prod")
    gravar(
        catalogo.select(
            pl.lit(REVENDA).alias("REVENDA"),
            pl.lit("CMV").alias("TIPO"),
            pl.col("CODRED").alias("CODR"),
            (pl.col("PRECO") * 0.74).round(2).alias("PRECO"),
        ),
        "tb_cmv",
    )
    momento = datetime.combine(b.HOJE, datetime.min.time()).replace(hour=5, minute=12).isoformat(timespec="seconds")
    (pasta / "_atualizacoes.json").write_text(
        json.dumps(
            {
                n: momento
                for n in ("tb_diario_venda", f"tb_curva_abc_{CNPJ}_atual", "tb_mapa_pot", "tb_markup", "tb_carteira")
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
