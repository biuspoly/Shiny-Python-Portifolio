"""Documentos fiscais recebidos (NF-e e CT-e), fictícios, para o app Fiscal: o substituto do Qive.

A revenda de Natal recebe notas de seis tipos de fornecedor: a fábrica de bebidas (com os produtos do
catálogo do Comercial, transportados por CT-e), garrafeira, posto, oficina, papelaria e o fornecedor de
refrigeradores. Cada nota tem chave de acesso no formato da NF-e (com o dígito verificador), CNPJs
fictícios (raiz começando em 9, com dígitos verificadores válidos), CFOP de saída do emitente e o de entrada
na revenda, e uma etapa que depende da idade da nota: recebida, manifestada, escriturada ou recusada.

O XML não é gravado: o app monta o de cada nota a partir destas tabelas, na hora de mostrar.
"""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta

import polars as pl

from gerador import base as b
from gerador import comercial

PASTA = b.PY / "Fiscal" / "data" / "bd_notas"
MESES = 3  # o mês corrente e os dois anteriores

UF_CODIGO = {"RN": "24", "PE": "26", "PB": "25", "CE": "23", "SP": "35"}

DESTINATARIO = {
    "CNPJ": "00000000000100",
    "NOME": "DISTRIBUIDORA FICTÍCIA LTDA",
    "IE": "200000001",
    "UF": "RN",
    "MUNICIPIO": "Natal",
}

# tipo, nome, UF, município, CFOP do emitente, CFOP de entrada, natureza da entrada, alíquota ICMS, notas/mês
FORNECEDORES = [
    (
        "Mercadoria para revenda",
        "CERVEJARIA MARÉ INDÚSTRIA DE BEBIDAS S.A.",
        "PE",
        "Itapissuma",
        "6401",
        "2403",
        "Compra para comercialização com ST",
        0.12,
        70,
    ),
    ("Vasilhame", "GARRAFEIRA PARAIBANA LTDA", "PB", "João Pessoa", "6920", "2920", "Entrada de vasilhame", 0.0, 8),
    (
        "Uso e consumo",
        "POSTO PONTA NEGRA COMBUSTÍVEIS LTDA",
        "RN",
        "Natal",
        "5656",
        "1653",
        "Combustível para uso e consumo",
        0.0,
        12,
    ),
    (
        "Uso e consumo",
        "AUTO PEÇAS E OFICINA POTIGUAR LTDA",
        "RN",
        "Parnamirim",
        "5102",
        "1556",
        "Material de uso e consumo",
        0.18,
        9,
    ),
    (
        "Uso e consumo",
        "PAPELARIA E INFORMÁTICA DUNAS ME",
        "RN",
        "Natal",
        "5102",
        "1556",
        "Material de uso e consumo",
        0.18,
        4,
    ),
    (
        "Ativo imobilizado",
        "REFRIGERAÇÃO COMERCIAL PAULISTA LTDA",
        "SP",
        "Guarulhos",
        "6101",
        "2551",
        "Compra para o ativo imobilizado",
        0.07,
        2,
    ),
]

TRANSPORTADORAS = [
    ("TRANSPORTES LITORAL NORTE LTDA", "PE", "Recife"),
    ("RODOVIÁRIO SERTÃO CARGAS LTDA", "PB", "Campina Grande"),
    ("EXPRESSO POTIGUAR LOGÍSTICA LTDA", "RN", "Mossoró"),
]

ITENS_POR_TIPO = {
    "Vasilhame": [
        ("GARRAFEIRA PLÁSTICA 24 GARRAFAS", "3923.10.90", "UN", 21.5),
        ("GARRAFA 600ML ÂMBAR", "7010.90.21", "UN", 1.4),
    ],
    "POSTO": [("ÓLEO DIESEL S10", "2710.19.21", "L", 6.19), ("ARLA 32", "3102.10.10", "L", 3.9)],
    "OFICINA": [
        ("PASTILHA DE FREIO DIANTEIRA", "8708.30.90", "JG", 189.0),
        ("FILTRO DE ÓLEO", "8421.23.00", "UN", 42.0),
        ("PNEU 215/75 R17.5", "4011.20.90", "UN", 1290.0),
        ("ÓLEO LUBRIFICANTE 15W40 20L", "2710.19.32", "BD", 389.0),
    ],
    "PAPELARIA": [
        ("PAPEL A4 500 FOLHAS", "4802.56.10", "PCT", 29.9),
        ("TONER IMPRESSORA LASER", "8443.99.33", "UN", 219.0),
        ("BOBINA TÉRMICA 80MM", "4811.90.90", "UN", 4.5),
    ],
    "Ativo imobilizado": [
        ("REFRIGERADOR VERTICAL 1 PORTA 400L", "8418.50.10", "UN", 4890.0),
        ("FREEZER HORIZONTAL 2 PORTAS 500L", "8418.30.00", "UN", 3990.0),
    ],
}


def _dv_cnpj(base12: str) -> str:
    def digito(numeros: str, pesos: list[int]) -> str:
        resto = sum(int(n) * p for n, p in zip(numeros, pesos, strict=True)) % 11
        return "0" if resto < 2 else str(11 - resto)

    d1 = digito(base12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = digito(base12 + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return base12 + d1 + d2


def _cnpj_ficticio(r) -> str:
    return _dv_cnpj(f"9{r.randint(0, 9999999):07d}0001")


def _dv_chave(chave43: str) -> str:
    soma, peso = 0, 2
    for n in reversed(chave43):
        soma += int(n) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    return chave43 + ("0" if resto < 2 else str(11 - resto))


def _chave(uf: str, emissao: datetime, cnpj: str, modelo: str, serie: int, numero: int, r) -> str:
    return _dv_chave(f"{UF_CODIGO[uf]}{emissao:%y%m}{cnpj}{modelo}{serie:03d}{numero:09d}1{r.randint(0, 99999999):08d}")


def _etapa(emissao: datetime, r) -> tuple[str, str, datetime | None]:
    """(etapa, manifestação, escriturada_em): quanto mais velha a nota, mais provável estar escriturada."""
    idade = (datetime.combine(b.HOJE, time(18)) - emissao).days
    sorteio = r.random()
    if sorteio < 0.025:
        return "Recusada", r.choice(["Desconhecimento da operação", "Operação não realizada"]), None
    # A maior parte é lançada na primeira semana; passado um mês, tudo o que não foi recusado está no livro.
    p_escriturada = 1.0 if idade > 30 else min(0.96, max(0.0, (idade - 1) / 7))
    if r.random() < p_escriturada:
        return "Escriturada", "Confirmação da operação", emissao + timedelta(days=r.randint(1, min(max(idade, 1), 8)))
    if idade >= 1 and r.random() < 0.6:
        return "Manifestada", "Confirmação da operação", None
    return "Recebida", r.choice(["Ciência da operação", "Sem manifestação"]), None


def _itens_fabrica(r) -> list[tuple]:
    catalogo = comercial._catalogo().filter(pl.col("CANAL") != "OUTRO").to_dicts()
    pesos = [p["PESO"] for p in catalogo]
    escolhidos = {p["CODRED"]: p for p in r.choices(catalogo, weights=pesos, k=r.randint(4, 12))}
    itens = []
    for p in escolhidos.values():
        ncm = "2201.10.00" if "AGUA" in p["MARCA"] else "2202.10.00" if p["CANAL"] == "NAB" else "2203.00.00"
        # Escala próxima da venda do Comercial: a compra do mês fica perto do CMV do que se vende.
        caixas = r.randint(30, 230)
        itens.append((f"{p['CODRED']} - {p['PRODUTO']}", ncm, "CX", caixas, round(p["PRECO"] * 0.74, 2)))
    return itens


def _itens_outros(chave_itens: str, r) -> list[tuple]:
    lista = ITENS_POR_TIPO[chave_itens]
    escolhidos = r.sample(lista, k=r.randint(1, len(lista)))
    itens = []
    for descricao, ncm, unidade, preco in escolhidos:
        if unidade == "L":
            qtd = r.randint(300, 2500)
        elif chave_itens == "Vasilhame":
            qtd = r.randint(200, 1500)
        elif chave_itens == "Ativo imobilizado":
            qtd = r.randint(5, 30)
        else:
            qtd = r.randint(1, 12)
        itens.append((descricao, ncm, unidade, qtd, round(preco * r.uniform(0.95, 1.05), 2)))
    return itens


def gerar() -> None:
    print("Fiscal (notas recebidas)")
    r = b.rng("fiscal-notas")
    PASTA.mkdir(parents=True, exist_ok=True)
    for antigo in PASTA.glob("*.parquet"):
        antigo.unlink()

    emitentes = [(*f, _cnpj_ficticio(r)) for f in FORNECEDORES]
    transportadoras = [(*t, _cnpj_ficticio(r)) for t in TRANSPORTADORAS]
    inicio = b.meses_atras(b.HOJE, MESES - 1)
    dias = [d for d in b.dias_uteis(inicio, b.HOJE)]

    notas, itens, ctes, cte_nfe = [], [], [], []
    numero = {f[1]: r.randint(10000, 90000) for f in FORNECEDORES}
    numero_cte = {t[0]: r.randint(3000, 30000) for t in TRANSPORTADORAS}

    for tipo, nome, uf, municipio, cfop_emit, cfop_ent, natureza, aliq, por_mes, cnpj in emitentes:
        quantidade = int(por_mes * MESES * r.uniform(0.9, 1.1))
        datas = sorted(r.choices(dias, k=quantidade))
        chave_itens = next(
            (
                itens
                for prefixo, itens in (("POSTO", "POSTO"), ("AUTO", "OFICINA"), ("PAPEL", "PAPELARIA"))
                if nome.startswith(prefixo)
            ),
            tipo,
        )
        for d in datas:
            emissao = datetime.combine(d, time(r.randint(6, 18), r.randint(0, 59)))
            if emissao > datetime.combine(b.HOJE, time(18)):
                continue
            numero[nome] += 1
            chave = _chave(uf, emissao, cnpj, "55", 1, numero[nome], r)
            linhas = _itens_fabrica(r) if tipo == "Mercadoria para revenda" else _itens_outros(chave_itens, r)
            v_prod = v_icms = v_st = 0.0
            for n, (descricao, ncm, unidade, qtd, v_unit) in enumerate(linhas, start=1):
                bruto = round(qtd * v_unit, 2)
                icms = round(bruto * aliq, 2)
                st = round(bruto * 0.18, 2) if cfop_emit == "6401" else 0.0
                v_prod, v_icms, v_st = v_prod + bruto, v_icms + icms, v_st + st
                itens.append(
                    (
                        chave,
                        n,
                        descricao.split(" - ")[0] if " - " in descricao else f"{n:04d}",
                        descricao.split(" - ")[-1],
                        ncm,
                        cfop_emit,
                        unidade,
                        float(qtd),
                        v_unit,
                        bruto,
                        icms,
                        st,
                    )
                )
            etapa, manifestacao, escriturada = _etapa(emissao, r)
            notas.append(
                {
                    "CHAVE": chave,
                    "NUMERO": numero[nome],
                    "SERIE": 1,
                    "EMISSAO": emissao,
                    "RECEBIDA_EM": emissao + timedelta(minutes=r.randint(3, 240)),
                    "EMIT_CNPJ": cnpj,
                    "EMIT_NOME": nome,
                    "EMIT_UF": uf,
                    "EMIT_MUNICIPIO": municipio,
                    "TIPO": tipo,
                    "CFOP_EMIT": cfop_emit,
                    "CFOP_ENTRADA": cfop_ent,
                    "NATUREZA": natureza,
                    "V_PROD": round(v_prod, 2),
                    "BASE_ICMS": round(v_prod, 2) if aliq else 0.0,
                    "V_ICMS": round(v_icms, 2),
                    "V_ST": round(v_st, 2),
                    "V_NF": round(v_prod + v_st, 2),
                    "N_ITENS": len(linhas),
                    "MANIFESTACAO": manifestacao,
                    "ETAPA": etapa,
                    "ESCRITURADA_EM": escriturada,
                }
            )

    # CT-e: a fábrica manda as cargas por transportadora; um CT-e leva de 1 a 3 notas do mesmo dia.
    fabrica = [n for n in notas if n["TIPO"] == "Mercadoria para revenda"]
    por_dia: dict = {}
    for n in fabrica:
        por_dia.setdefault(n["EMISSAO"].date(), []).append(n)
    for d, do_dia in sorted(por_dia.items()):
        r.shuffle(do_dia)
        i = 0
        while i < len(do_dia):
            tamanho = r.randint(1, 3)
            lote = do_dia[i : i + tamanho]
            i += tamanho
            nome_t, uf_t, mun_t, cnpj_t = r.choice(transportadoras)
            numero_cte[nome_t] += 1
            emissao = max(n["EMISSAO"] for n in lote) + timedelta(minutes=r.randint(10, 90))
            chave = _chave(uf_t, emissao, cnpj_t, "57", 1, numero_cte[nome_t], r)
            valor_cargas = sum(n["V_NF"] for n in lote)
            v_prest = round(valor_cargas * r.uniform(0.018, 0.03), 2)
            etapa, _, escriturada = _etapa(emissao, r)
            ctes.append(
                {
                    "CHAVE": chave,
                    "NUMERO": numero_cte[nome_t],
                    "EMISSAO": emissao,
                    "EMIT_CNPJ": cnpj_t,
                    "EMIT_NOME": nome_t,
                    "EMIT_UF": uf_t,
                    "EMIT_MUNICIPIO": mun_t,
                    "ORIGEM": "Itapissuma/PE",
                    "DESTINO": "Natal/RN",
                    "V_PREST": v_prest,
                    "V_ICMS": round(v_prest * 0.12, 2),
                    "V_CARGA": round(valor_cargas, 2),
                    "PESO_KG": round(sum(1 for _ in lote) * r.uniform(9000, 24000), 1),
                    "CFOP_ENTRADA": "2353",
                    "NATUREZA": "Aquisição de serviço de transporte",
                    "ETAPA": "Desacordo"
                    if etapa == "Recusada"
                    else "Escriturado"
                    if etapa == "Escriturada"
                    else "Recebido",
                    "ESCRITURADA_EM": escriturada,
                    "N_NFE": len(lote),
                }
            )
            cte_nfe += [(chave, n["CHAVE"]) for n in lote]

    def gravar(df: pl.DataFrame, nome: str) -> None:
        df.write_parquet(PASTA / f"{nome}.parquet", compression="zstd")
        print(f"  bd_notas/{nome}.parquet: {df.height:,} linhas".replace(",", "."))

    gravar(pl.DataFrame(notas).sort("EMISSAO", descending=True), "nfe_recebidas")
    gravar(
        pl.DataFrame(
            itens,
            schema=[
                "CHAVE",
                "N_ITEM",
                "CODIGO",
                "DESCRICAO",
                "NCM",
                "CFOP",
                "UNIDADE",
                "QTD",
                "V_UNIT",
                "V_PROD",
                "V_ICMS",
                "V_ST",
            ],
            orient="row",
        ),
        "nfe_itens",
    )
    gravar(pl.DataFrame(ctes).sort("EMISSAO", descending=True), "cte_recebidos")
    gravar(pl.DataFrame(cte_nfe, schema=["CHAVE_CTE", "CHAVE_NFE"], orient="row"), "cte_nfe")
    gravar(pl.DataFrame([DESTINATARIO]), "destinatario")
    momento = datetime.combine(b.HOJE, time(5, 40)).isoformat(timespec="seconds")
    (PASTA / "_atualizacoes.json").write_text(
        json.dumps({"nfe_recebidas": momento, "cte_recebidos": momento}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
