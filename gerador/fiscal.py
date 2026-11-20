"""Documentos fiscais recebidos pela Atlântida: nascem dos mesmos títulos a pagar
do Financeiro, para os dois apps contarem a mesma história."""

import json
from datetime import date, timedelta

import polars as pl

from gerador import base as b
from gerador.financeiro import _titulos_pagar

_CODIGO_UF = {"RN": 24, "CE": 23, "PI": 22, "MA": 21, "PE": 26, "PB": 25}
_NCM = {
    "Pilsen": "2203.00.00",
    "Puro Malte": "2203.00.00",
    "Premium": "2203.00.00",
    "Zero Álcool": "2202.91.00",
    "Não Alcoólicos": "2202.10.00",
}
TRANSPORTADORAS = ["Rodoviário {s} Ltda", "{s} Transportes e Logística", "Expresso {s}"]
PENDENCIAS = [
    "Fornecedor sem cadastro",
    "CFOP sem de-para",
    "Aguardando conferência física",
    "Divergência de valor com o pedido",
]


def _cnpj(r) -> str:
    return "".join(str(r.randint(0, 9)) for _ in range(8)) + "0001" + "".join(str(r.randint(0, 9)) for _ in range(2))


def chave_acesso(uf: str, emissao: date, cnpj: str, modelo: int, numero: int, r) -> str:
    """44 dígitos no leiaute da SEFAZ, com o dígito verificador (módulo 11) calculado."""
    corpo = f"{_CODIGO_UF.get(uf, 26):02d}{emissao:%y%m}{cnpj}{modelo:02d}001{numero:09d}1{r.randint(0, 99999999):08d}"
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(d) * pesos[i % 8] for i, d in enumerate(reversed(corpo)))
    resto = soma % 11
    return corpo + str(0 if resto < 2 else 11 - resto)


def _documentos() -> tuple[pl.DataFrame, pl.DataFrame]:
    r = b.rng("fiscal")
    f = b.faker("fiscal")
    titulos = _titulos_pagar().filter(pl.col("emissao") <= b.HOJE)
    produtos = b.produtos().to_dicts()
    filial_uf = {fl.nome: fl.uf for fl in b.FILIAIS}
    cnpjs: dict[str, tuple[str, str]] = {}
    transportadoras = [
        (t.format(s=f.last_name()).upper(), _cnpj(r), r.choice(["PE", "CE", "RN"])) for t in TRANSPORTADORAS
    ]
    docs, itens = [], []
    numero = 1000
    for t in titulos.iter_rows(named=True):
        tipo_desp = t["tipo_despesa"]
        if tipo_desp in ("Aluguel", "Impostos", "Energia e água"):
            continue
        if t["fornecedor"] not in cnpjs:
            cnpjs[t["fornecedor"]] = (
                _cnpj(r),
                r.choice(["PE", "PB", "CE", "RN"]) if tipo_desp == "Fábrica" else filial_uf[t["filial"]],
            )
        cnpj, uf_emit = cnpjs[t["fornecedor"]]
        modelo, tipo = (
            (99, "NFS-e")
            if tipo_desp in ("Serviços",) or (tipo_desp == "Manutenção de frota" and r.random() < 0.4)
            else (55, "NF-e")
        )
        numero += r.randint(1, 40)
        emissao = t["emissao"]
        chave = chave_acesso(uf_emit, emissao, cnpj, modelo, numero, r) if tipo == "NF-e" else f"NFSE{numero:011d}"
        recebida = emissao + timedelta(days=r.choice([0, 0, 1, 1, 2, 3]))
        if recebida > b.HOJE:
            continue  # ainda não chegou
        escriturada = recebida < b.HOJE - timedelta(days=12) or r.random() < 0.55
        cancelada = r.random() < 0.02
        if tipo == "NF-e":
            if cancelada:
                manifestacao = "Sem manifestação"
            elif recebida < b.HOJE - timedelta(days=60):
                manifestacao = r.choices(["Confirmada", "Desconhecida"], weights=[97, 3])[0]
            elif recebida < b.HOJE - timedelta(days=20):
                manifestacao = r.choices(["Confirmada", "Ciência", "Desconhecida"], weights=[80, 17, 3])[0]
            else:
                manifestacao = r.choices(["Sem manifestação", "Ciência", "Confirmada"], weights=[45, 30, 25])[0]
        else:
            manifestacao = "Não se aplica"
        doc = {
            "chave": chave,
            "tipo": tipo,
            "numero": numero,
            "emitente": t["fornecedor"],
            "uf_emitente": uf_emit,
            "destinatario": t["filial"],
            "emissao": emissao,
            "recebida_em": recebida,
            "valor": t["valor"],
            "situacao_sefaz": "Cancelada" if cancelada else "Autorizada",
            "manifestacao": manifestacao,
            "escriturada": escriturada and not cancelada,
            "escriturada_em": (recebida + timedelta(days=r.randint(1, 10))) if escriturada and not cancelada else None,
            "pendencia": None if (escriturada or cancelada) else r.choice(PENDENCIAS),
            "titulo": t["titulo"],
        }
        if tipo == "NF-e":
            doc["icms"] = round(t["valor"] * (0.18 if tipo_desp == "Fábrica" else 0.12), 2)
            if tipo_desp == "Fábrica":
                restante = t["valor"]
                escolhidos = r.sample(produtos, k=r.randint(4, 9))
                for i, p in enumerate(escolhidos):
                    parte = restante if i == len(escolhidos) - 1 else round(t["valor"] * r.uniform(0.05, 0.22), 2)
                    restante -= parte
                    custo = p["custo_caixa"]
                    itens.append(
                        {
                            "chave": chave,
                            "item": i + 1,
                            "cod_produto": p["cod_produto"],
                            "produto": p["produto"],
                            "ncm": _NCM[p["categoria"]],
                            "cfop": "1102" if uf_emit == filial_uf[t["filial"]] else "2102",
                            "quantidade": max(1, round(parte / custo)),
                            "valor": round(parte, 2),
                            "icms": round(parte * 0.18, 2),
                        }
                    )
                # O frete da fábrica vem num CT-e da transportadora.
                tnome, tcnpj, tuf = r.choice(transportadoras)
                numero += 1
                docs.append(
                    {
                        **doc,
                        "chave": chave_acesso(tuf, emissao, tcnpj, 57, numero, r),
                        "tipo": "CT-e",
                        "numero": numero,
                        "emitente": tnome,
                        "uf_emitente": tuf,
                        "valor": round(t["valor"] * r.uniform(0.02, 0.04), 2),
                        "icms": None,
                        "manifestacao": "Não se aplica",
                        "titulo": None,
                    }
                )
        else:
            doc["icms"] = None
        docs.append(doc)
    return pl.DataFrame(docs, infer_schema_length=None), pl.DataFrame(itens)


def gerar() -> None:
    print("Fiscal")
    docs, itens = _documentos()
    b.gravar(docs, "Fiscal", "documentos")
    b.gravar(itens, "Fiscal", "itens_nfe")
    with open(b.RAIZ / "Fiscal" / "data" / "_gerado_em.json", "w", encoding="utf-8") as arq:
        json.dump({"data_base": b.HOJE.isoformat(), "gerado_em": date.today().isoformat()}, arq)
