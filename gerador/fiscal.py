"""Caches do Fiscal no esquema original: o livro de faturamento (saídas e entradas por CFOP, com
os impostos) das quatro empresas fictícias."""

import json
from datetime import datetime

import polars as pl

from gerador import base as b
from gerador import comercial

PASTA = b.RAIZ / "Fiscal" / "data" / "bd_fiscal"
MESES = 24

# (nome, CNPJ, porte relativo). Os CNPJs batem com Fiscal/config/empresas.json.
EMPRESAS = [
    ("Natal", "00000000000100", 1.0),
    ("Fortaleza", "00000000000280", 1.35),
    ("Teresina", "00000000000360", 0.75),
    ("São Luís", "00000000000440", 0.8),
]
# CFOP -> (livro, parte do faturamento, alíquota de ICMS próprio, tem ST)
CFOPS = {
    "5102": ("S", 0.38, 0.20, False),
    "5405": ("S", 0.44, 0.0, True),
    "6102": ("S", 0.06, 0.12, False),
    "5910": ("S", 0.03, 0.20, False),
    "5949": ("S", 0.015, 0.0, False),
    "5927": ("S", 0.004, 0.0, False),
    "1102": ("E", 0.10, 0.20, False),
    "1403": ("E", 0.55, 0.0, True),
    "2102": ("E", 0.08, 0.12, False),
    "2403": ("E", 0.07, 0.0, True),
    "1202": ("E", 0.012, 0.20, False),
    "1411": ("E", 0.018, 0.0, True),
    "2202": ("E", 0.002, 0.12, False),
    "1556": ("E", 0.01, 0.0, False),
}
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


def _faturamento(r) -> pl.DataFrame:
    linhas = []
    for nome, cnpj, porte in EMPRESAS:
        for n in range(MESES - 1, -1, -1):
            mes = b.meses_atras(b.HOJE, n)
            parcial = (b.HOJE.day / 30) if n == 0 else 1.0
            crescimento = 1 + 0.06 * (MESES - 1 - n) / 12
            vendas_mes = 4_200_000 * porte * SAZONALIDADE[mes.month] * crescimento * parcial * r.uniform(0.93, 1.07)
            for cfop, (livro, parte, aliquota, st) in CFOPS.items():
                # As entradas (compras) acompanham as vendas com algum descompasso de mês.
                valor = round(
                    vendas_mes * parte * (r.uniform(0.85, 1.15) if livro == "E" else r.uniform(0.95, 1.05)), 2
                )
                base = round(valor * (0.0 if aliquota == 0 else 1.0), 2)
                for cancelada in (0, 1):
                    fator = 1.0 if cancelada == 0 else r.uniform(0.002, 0.008)
                    v = round(valor * fator, 2)
                    linhas.append(
                        {
                            "LIVRO": livro,
                            "MES": f"{mes:%Y-%m}",
                            "EMITENTE": cnpj,
                            "CFOP": cfop,
                            "CANCELADA": cancelada,
                            "VALOR": v,
                            "LINHAS": max(1, int(v / r.uniform(900, 2500))),
                            "BASE_ICMS": round(base * fator, 2),
                            "ICMS": round(base * fator * aliquota, 2),
                            "ISENTAS": round(v * 0.02, 2) if cfop in ("5910", "5927") else 0.0,
                            "OUTRAS": round(v, 2) if aliquota == 0 and not st else 0.0,
                            "ICMS_ST": round(v * 0.21, 2) if st else 0.0,
                            "IPI": 0.0,
                            "PIS": round(v * 0.0165, 2) if livro == "S" else round(v * 0.0165 * 0.9, 2),
                            "COFINS": round(v * 0.076, 2) if livro == "S" else round(v * 0.076 * 0.9, 2),
                            "CNPJ_REV": cnpj,
                            "REVENDA": nome,
                        }
                    )
    return pl.DataFrame(linhas).with_columns(pl.col("CANCELADA").cast(pl.Int64), pl.col("LINHAS").cast(pl.Int64))


MESES_ITENS = 3


def _livro_itens(fat: pl.DataFrame, r) -> tuple[dict[str, pl.DataFrame], dict[str, pl.DataFrame]]:
    """O livro item a item dos últimos meses: cada total de (empresa, mês, CFOP) do faturamento
    repartido em itens de nota, para as duas visões baterem. Mais os cadastros que dão nome às linhas."""
    f = b.faker("fiscal-itens")
    produtos = comercial._catalogo().filter(pl.col("CANAL") != "OUTRO").select("CODRED", "PRODUTO", "PRECO").to_dicts()
    clientes = [(10_000_000_000 + i * 7919, f"{f.last_name().upper()} COMERCIO DE BEBIDAS LTDA") for i in range(60)]
    fabricas = [
        (20_000_000_000 + i * 104_729, nome)
        for i, nome in enumerate(b.fornecedores().filter(pl.col("tipo_despesa") == "Fábrica")["fornecedor"].to_list())
    ]
    meses = sorted(fat["MES"].unique().to_list())[-MESES_ITENS:]
    por_mes: dict[str, list[dict]] = {m: [] for m in meses}
    numero = 30_000
    base = fat.filter(pl.col("MES").is_in(meses) & (pl.col("VALOR") > 0))
    for x in base.iter_rows(named=True):
        restante, notas = x["VALOR"], max(1, min(40, x["LINHAS"] // 6))
        aliquota = (x["ICMS"] / x["BASE_ICMS"]) if x["BASE_ICMS"] else 0.0
        for n in range(notas):
            numero += 1
            valor_nota = restante if n == notas - 1 else round(x["VALOR"] / notas * r.uniform(0.6, 1.4), 2)
            restante = round(restante - valor_nota, 2)
            participante = r.choice(clientes if x["LIVRO"] == "S" else fabricas)
            dia = r.randint(1, 28)
            itens = r.sample(produtos, k=r.randint(1, 4))
            pesos = [r.uniform(0.5, 2) for _ in itens]
            for p, peso in zip(itens, pesos):
                valor = round(valor_nota * peso / sum(pesos), 2)
                qtd = max(1.0, round(valor / p["PRECO"], 0))
                base_icms = valor if aliquota else 0.0
                por_mes[x["MES"]].append(
                    {
                        "LIVRO": x["LIVRO"],
                        "DATA": f"{x['MES']}-{dia:02d}",
                        "NUMERO": numero,
                        "SERIE": 1,
                        "CHAVE": f"{numero:044d}",
                        "CNPJ_PARTICIPANTE": participante[0],
                        "CFOP": x["CFOP"],
                        "CODRED": int(p["CODRED"]),
                        "QUANTIDADE": qtd,
                        "QUANTIDADE_AVULSA": 0.0,
                        "VALOR": valor,
                        "FRETE": 0.0,
                        "BASE_ICMS": base_icms,
                        "ALIQ_ICMS": round(aliquota * 100, 2),
                        "ICMS": round(base_icms * aliquota, 2),
                        "ICMS_ST": round(valor * 0.21, 2) if x["ICMS_ST"] else 0.0,
                        "IPI": 0.0,
                        "CST_PIS": 1,
                        "BASE_PIS": valor,
                        "ALIQ_PIS": 1.65,
                        "PIS": round(valor * 0.0165, 2),
                        "CST_COFINS": 1,
                        "BASE_COFINS": valor,
                        "ALIQ_COFINS": 7.6,
                        "COFINS": round(valor * 0.076, 2),
                        "CANCELADA": x["CANCELADA"],
                        "CNPJ_REV": x["CNPJ_REV"],
                        "DESCRICAO": p["PRODUTO"],
                        "EMITENTE": x["EMITENTE"],
                        "MES": x["MES"],
                    }
                )
    itens = {
        f"livro_itens/{m}": pl.DataFrame(linhas, infer_schema_length=None).with_columns(pl.col("DATA").str.to_date())
        for m, linhas in por_mes.items()
    }
    itens["livro_itens/_meses"] = pl.DataFrame(
        [
            {"CNPJ_REV": cnpj, "MES": m, "LINHAS": sum(1 for i in por_mes[m] if i["CNPJ_REV"] == cnpj)}
            for _, cnpj, _ in EMPRESAS
            for m in meses
        ]
    )
    cadastros = {
        "control_produtos": pl.DataFrame(
            [
                {"CNPJ_REV": cnpj, "CODRED": int(p["CODRED"]), "PRODUTO": p["PRODUTO"]}
                for _, cnpj, _ in EMPRESAS
                for p in produtos
            ]
        ),
        "control_clientes": pl.DataFrame(
            [{"CNPJ_REV": cnpj, "CNPJ_CPF": c, "RAZAO": nome} for _, cnpj, _ in EMPRESAS for c, nome in clientes]
        ),
        "control_fornecedores": pl.DataFrame(
            [{"CNPJ_REV": cnpj, "CNPJ_CPF": c, "RAZAO": nome} for _, cnpj, _ in EMPRESAS for c, nome in fabricas]
        ),
    }
    return itens, cadastros


def gerar() -> None:
    print("Fiscal")
    r = b.rng("fiscal")
    PASTA.mkdir(parents=True, exist_ok=True)
    for antigo in PASTA.glob("*.parquet"):
        antigo.unlink()
    fat = _faturamento(r)
    itens, cadastros = _livro_itens(fat, r)
    (PASTA / "livro_itens").mkdir(exist_ok=True)
    for antigo in (PASTA / "livro_itens").glob("*.parquet"):
        antigo.unlink()
    tabelas = {"faturamento": fat, **itens, **cadastros}
    for nome, df in tabelas.items():
        df.write_parquet(PASTA / f"{nome}.parquet", compression="zstd")
        print(f"  bd_fiscal/{nome}.parquet: {df.height:,} linhas".replace(",", "."))
    momento = datetime.combine(b.HOJE, datetime.min.time()).replace(hour=6, minute=15).isoformat(timespec="seconds")
    (PASTA / "_atualizacoes.json").write_text(
        json.dumps({n: momento for n in tabelas}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
