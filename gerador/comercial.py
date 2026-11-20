"""Vendas fictícias da Atlântida: simula compra cliente a cliente, mês a mês, e
grava só os agregados que as telas do Comercial leem."""

import json
from datetime import date

import polars as pl

from gerador import base as b
from gerador.publicos import malha_uf

MESES_HISTORICO = 25  # mês corrente + 24 anteriores: dá o "mesmo mês do ano passado"

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


def _compras(clientes: pl.DataFrame, produtos: pl.DataFrame) -> pl.DataFrame:
    """Uma linha por cliente, mês e produto comprado."""
    r = b.rng("compras")
    prods = produtos.to_dicts()
    pesos = [p["peso_venda"] for p in prods]
    linhas = []
    for c in clientes.iter_rows(named=True):
        # Cliente parado: deixou de comprar entre 2 e 10 meses atrás.
        parou_em = None if c["ativo"] else b.meses_atras(b.HOJE, r.randint(2, 10))
        # Cada cliente tem seu "mix" preferido: sorteia uma vez e repete com variação.
        mix = set(r.choices(range(len(prods)), weights=pesos, k=r.randint(3, 8)))
        for m in range(MESES_HISTORICO - 1, -1, -1):
            mes = b.meses_atras(b.HOJE, m)
            if mes < b.inicio_do_mes(c["cliente_desde"]) or (parou_em and mes >= parou_em):
                continue
            if r.random() > 0.86:  # mês sem compra
                continue
            # De vez em quando entra um produto novo no mix.
            if r.random() < 0.04:
                mix.add(r.choices(range(len(prods)), weights=pesos)[0])
            crescimento = 1 + 0.045 * (MESES_HISTORICO - 1 - m) / 12
            inflacao = 1 + 0.0045 * (MESES_HISTORICO - 1 - m)
            fator = c["porte"] * SAZONALIDADE[mes.month] * crescimento
            for i in mix:
                if r.random() > 0.8:
                    continue
                p = prods[i]
                caixas = max(1, round(r.gammavariate(2.0, 3.2) * fator * p["peso_venda"] / 2))
                desconto = r.uniform(0.0, 0.07)
                linhas.append(
                    (
                        mes,
                        c["cod_cliente"],
                        c["cod_vendedor"],
                        p["cod_produto"],
                        caixas,
                        caixas * p["preco_caixa"] * inflacao * (1 - desconto),
                        caixas * p["custo_caixa"] * inflacao,
                    )
                )
    return pl.DataFrame(
        linhas,
        schema=["mes", "cod_cliente", "cod_vendedor", "cod_produto", "caixas", "faturamento", "custo"],
        orient="row",
    )


def _parcial_do_mes_corrente(compras: pl.DataFrame) -> pl.DataFrame:
    """O mês corrente só tem venda até hoje: corta proporcional aos dias úteis passados."""
    mes_atual = b.inicio_do_mes(b.HOJE)
    uteis = b.dias_uteis(mes_atual, b.fim_do_mes(mes_atual))
    passados = sum(1 for d in uteis if d <= b.HOJE)
    fracao = passados / len(uteis)
    r = b.rng("parcial")
    sorteio = pl.Series([r.random() for _ in range(compras.height)])
    return (
        compras.with_columns(sorteio.alias("_s"))
        .filter((pl.col("mes") != mes_atual) | (pl.col("_s") < fracao))
        .drop("_s")
    )


def _vendas_dia(compras_mes: pl.DataFrame) -> pl.DataFrame:
    """Espalha as compras do mês corrente pelos dias úteis já passados."""
    mes_atual = b.inicio_do_mes(b.HOJE)
    dias = [d for d in b.dias_uteis(mes_atual, b.fim_do_mes(mes_atual)) if d <= b.HOJE]
    r = b.rng("dias")
    atual = compras_mes.filter(pl.col("mes") == mes_atual)
    data = pl.Series("data", [r.choice(dias) for _ in range(atual.height)], dtype=pl.Date)
    return (
        atual.with_columns(data)
        .group_by("data", "cod_vendedor", "cod_produto")
        .agg(pl.col("caixas").sum(), pl.col("faturamento").sum())
    )


def _metas(vendas: pl.DataFrame, produtos: pl.DataFrame) -> pl.DataFrame:
    """Meta em HL por vendedor e categoria: o mesmo mês do ano anterior, de -2% a +6%."""
    r = b.rng("metas")
    mes_atual = b.inicio_do_mes(b.HOJE)
    base = (
        vendas.join(produtos.select("cod_produto", "categoria"), on="cod_produto")
        .group_by("mes", "cod_vendedor", "categoria")
        .agg(pl.col("hl").sum())
    )
    linhas = []
    for m in range(0, 4):
        mes = b.meses_atras(mes_atual, m)
        mes_passado = b.meses_atras(mes, 12)
        for row in base.filter(pl.col("mes") == mes_passado).iter_rows(named=True):
            linhas.append(
                {
                    "mes": mes,
                    "cod_vendedor": row["cod_vendedor"],
                    "categoria": row["categoria"],
                    "meta_hl": round(row["hl"] * r.uniform(0.98, 1.06), 2),
                }
            )
    return pl.DataFrame(linhas)


def gerar() -> None:
    print("Comercial")
    produtos = b.produtos()
    equipe = b.equipe()
    clientes = b.clientes()
    compras = (
        _parcial_do_mes_corrente(_compras(clientes, produtos))
        .join(produtos.select("cod_produto", "litros_caixa"), on="cod_produto")
        .with_columns((pl.col("caixas") * pl.col("litros_caixa") / 100).alias("hl"))
        .drop("litros_caixa")
    )

    vendas = (
        compras.group_by("mes", "cod_vendedor", "cod_produto")
        .agg(pl.col("caixas", "hl", "faturamento", "custo").sum(), pl.col("cod_cliente").n_unique().alias("clientes"))
        .with_columns(pl.col("faturamento", "custo").round(2), pl.col("hl").round(3))
        .sort("mes", "cod_vendedor", "cod_produto")
    )

    # Cobertura: clientes distintos por vendedor e mês, em cada nível (marca, categoria, total).
    # Cada cliente tem um só vendedor, então somar vendedores não conta cliente duas vezes.
    com_produto = compras.join(produtos.select("cod_produto", "marca", "categoria"), on="cod_produto")
    cobertura = pl.concat(
        [
            com_produto.group_by("mes", "cod_vendedor", pl.col("marca").alias("item"))
            .agg(pl.col("cod_cliente").n_unique().alias("clientes"))
            .with_columns(pl.lit("marca").alias("nivel")),
            com_produto.group_by("mes", "cod_vendedor", pl.col("categoria").alias("item"))
            .agg(pl.col("cod_cliente").n_unique().alias("clientes"))
            .with_columns(pl.lit("categoria").alias("nivel")),
            com_produto.group_by("mes", "cod_vendedor")
            .agg(pl.col("cod_cliente").n_unique().alias("clientes"))
            .with_columns(pl.lit("TOTAL").alias("item"), pl.lit("total").alias("nivel")),
        ],
        how="diagonal",
    ).select("mes", "cod_vendedor", "nivel", "item", "clientes")

    cliente_mes = (
        compras.filter(pl.col("mes") >= b.meses_atras(b.HOJE, 11))
        .group_by("mes", "cod_cliente")
        .agg(pl.col("hl", "faturamento", "custo").sum())
        .with_columns(pl.col("faturamento", "custo").round(2), pl.col("hl").round(3))
    )
    ultima = compras.group_by("cod_cliente").agg(pl.col("mes").max().alias("ultima_compra"))
    carteira = clientes.join(ultima, on="cod_cliente", how="left").drop("porte", "ativo", "latitude", "longitude")

    b.gravar(produtos.drop("peso_venda"), "Comercial", "produtos")
    b.gravar(equipe, "Comercial", "equipe")
    b.gravar(carteira, "Comercial", "clientes")
    b.gravar(vendas, "Comercial", "vendas_mes")
    b.gravar(cobertura, "Comercial", "cobertura_mes")
    b.gravar(_vendas_dia(compras), "Comercial", "vendas_dia")
    b.gravar(_metas(vendas, produtos), "Comercial", "metas")
    b.gravar(cliente_mes, "Comercial", "cliente_mes")
    b.gravar(
        b.municipios().join(
            clientes.select("cod_ibge").unique(), left_on="codigo_ibge", right_on="cod_ibge", how="semi"
        ),
        "Comercial",
        "municipios",
    )

    pasta_geo = b.RAIZ / "Comercial" / "www" / "geo"
    pasta_geo.mkdir(parents=True, exist_ok=True)
    for filial in b.FILIAIS:
        (pasta_geo / f"{filial.uf}.json").write_text(
            json.dumps(malha_uf(filial.uf), ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    with open(b.RAIZ / "Comercial" / "data" / "_gerado_em.json", "w", encoding="utf-8") as arq:
        json.dump({"data_base": b.HOJE.isoformat(), "gerado_em": date.today().isoformat()}, arq)
