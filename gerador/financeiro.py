"""Caches do Financeiro no esquema original: contas a pagar, títulos pagos, extrato da
fábrica e empréstimos entre as revendas. Os retratos diários do Fluxo saem do próprio
app (scripts/retratos_fluxo.py), como na rotina do original."""

import json
import subprocess
import sys
from datetime import date, datetime, timedelta

import polars as pl

from gerador import base as b

PASTA = b.RAIZ / "Financeiro" / "data" / "bd_financeiro"

# (nome, CNPJ fictício, licença, código da revenda na fábrica). Os CNPJs batem com Financeiro/core/config.py.
REVENDAS = [
    ("Natal", "00000000000100", "4101", "0004100211"),
    ("Fortaleza", "00000000000280", "4102", "0004100344"),
    ("Teresina", "00000000000360", "4103", "0004100527"),
    ("São Luís", "00000000000440", "4104", "0004100528"),
]
FABRICA = "MARÉ"
LIMITES = {"Natal": 4_800_000, "Fortaleza": 6_200_000, "Teresina": 3_900_000, "São Luís": 3_900_000}
DIAS_LEITURAS = 45
BANCOS_EMPRESTIMO = ["BANCO ALFA S.A.", "BANCO BETA FINANCIAMENTOS S.A.", "COOP DE CRED REGIONAL", "BANCO GAMA S/A"]
TIPOS_EMPRESTIMO = [
    (106, "CAPITAL DE GIRO"),
    (107, "FINANCIAMENTO DE VEÍCULOS"),
    (108, "FINANCIAMENTO DE MÁQUINAS"),
    (109, "CAPITAL DE GIRO"),
    (110, "ANTECIPAÇÃO DE RECEBÍVEIS"),
]
CODIGO_DESPESA = {
    "Fábrica": 201,
    "Combustível": 310,
    "Manutenção de frota": 320,
    "Aluguel": 410,
    "Energia e água": 420,
    "Serviços": 430,
    "Impostos": 510,
    "Material de escritório": 440,
}


def _uteis(inicio: date, fim: date) -> list[date]:
    return [d for d in b.dias_uteis(inicio, fim) if d.weekday() < 5]


def _contas_pagar(r) -> tuple[tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame], pl.DataFrame]:
    """Títulos em aberto (com juros nos atrasados) e os de empréstimo, mais os já pagos."""
    hoje = b.HOJE
    forn = b.fornecedores().filter(pl.col("tipo_despesa") != "Fábrica").to_dicts()
    abertos, pagos, pagos_emp, configs = [], [], [], []
    seq = 0
    for nome, cnpj, licenca, _cod in REVENDAS:
        for _ in range(r.randint(90, 130)):
            fo = r.choice(forn)
            seq += 1
            venc = hoje + timedelta(days=r.randint(-40, 45))
            valor = round(r.uniform(fo["valor_min"], fo["valor_max"]) / 4, 2)
            atrasado = venc < hoje
            juros = round(valor * 0.0033 * (hoje - venc).days, 2) if atrasado and r.random() < 0.55 else None
            num = f"{r.randint(10000, 999999)}"
            abertos.append(
                _titulo(
                    nome,
                    cnpj,
                    licenca,
                    seq,
                    num,
                    fo,
                    venc,
                    valor,
                    juros,
                    CODIGO_DESPESA[fo["tipo_despesa"]],
                    fo["tipo_despesa"].upper(),
                    r,
                )
            )
            if r.random() < 0.6:
                dia = venc - timedelta(days=r.randint(30, 200))
                pagos.append(_pago(nome, cnpj, licenca, seq + 50000, num, fo["fornecedor"], dia, valor))
        # Empréstimos: contratos com parcelas mensais; as vencidas viram títulos pagos.
        for _ in range(r.randint(3, 6)):
            codigo, tipo = r.choice(TIPOS_EMPRESTIMO)
            banco = r.choice(BANCOS_EMPRESTIMO)
            contrato = f"{r.randint(40000000, 49999999)}"
            parcelas = r.choice([12, 24, 36, 48])
            contratado = b.meses_atras(hoje, r.randint(2, parcelas - 2))
            credito = round(r.uniform(150_000, 1_200_000), -3)
            taxa = round(r.uniform(1.1, 2.3), 2)
            parcela = round(credito * (taxa / 100) / (1 - (1 + taxa / 100) ** -parcelas), 2)
            dia_venc = r.choice([5, 10, 15, 20, 25])
            for n in range(1, parcelas + 1):
                total = contratado.year * 12 + contratado.month - 1 + n
                venc = date(total // 12, total % 12 + 1, dia_venc)
                seq += 1
                doc = f"{contrato} {n:02d}"
                if venc < hoje - timedelta(days=3):
                    pagos_emp.append(
                        {
                            "CNPJ_REV": cnpj,
                            "REVENDA": nome,
                            "LICENCA": licenca,
                            "data_vencimento": venc,
                            "data_pagamento": venc,
                            "num_doc": doc,
                            "codigo_despesa": codigo,
                            "DATA": venc,
                            "PGMOVBAI_DTP": venc,
                            "PGMOVBAI_NDUPL": doc,
                        }
                    )
                    continue
                fo = {
                    "fornecedor": banco,
                    "cod_fornecedor": 900 + BANCOS_EMPRESTIMO.index(banco),
                    "tipo_despesa": "Bancos",
                }
                linha = _titulo(nome, cnpj, licenca, seq, doc, fo, venc, parcela, None, codigo, tipo, r)
                linha["data_emissao"] = contratado
                abertos.append(linha)
            if r.random() < 0.7:
                configs.append(
                    {
                        "REVENDA": nome,
                        "contrato": contrato,
                        "valor_credito": credito,
                        "entrada": 0.0 if r.random() < 0.6 else round(credito * 0.1, -2),
                        "taxa_juros": taxa,
                        "atualizado_em": datetime.combine(contratado, datetime.min.time()),
                        "atualizado_por": "financeiro",
                    }
                )
    return (
        pl.DataFrame(abertos, infer_schema_length=None).with_columns(
            pl.col("data_pagamento").cast(pl.Int32), pl.col("justificativa").cast(pl.Int32)
        ),
        pl.DataFrame(pagos, infer_schema_length=None),
        pl.DataFrame(pagos_emp, infer_schema_length=None),
    ), pl.DataFrame(configs, infer_schema_length=None)


def _titulo(nome, cnpj, licenca, seq, num, fo, venc, valor, juros, codigo, descricao, r) -> dict:
    cnpj_forn = f"{fo['cod_fornecedor']:08d}000{r.randint(100, 199)}"
    return {
        "REVENDA": nome,
        "data_vencimento": venc,
        "data_entrada": venc - timedelta(days=r.randint(5, 40)),
        "data_emissao": venc - timedelta(days=r.randint(10, 45)),
        "codigo_despesa": codigo,
        "centro_custo": r.choice([10, 20, 30]),
        "num_doc": num,
        "num_doc_normalizado": num.replace(" ", ""),
        "tipo_doc": r.choice(["BOL", "NF", "DUP"]),
        "cnpj": cnpj_forn,
        "valor_original": valor,
        "razao_social": fo["fornecedor"],
        "TIPO_FORNECEDOR": fo["tipo_despesa"].upper(),
        "descricao_despesa": descricao,
        "id_unico": f"{cnpj}-{seq}",
        "auditoria_user": None,
        "pagar_user": None,
        "conselho_user": None,
        "CNPJ_REV": cnpj,
        "LICENCA": licenca,
        "valor_pago": None,
        "juros": juros,
        "banco": None,
        "pagar": None,
        "pagou": None,
        "auditoria": None,
        "conselho": None,
        "data_pagamento": None,
        "entrada_manual": None,
        "justificativa": None,
        "alterado_por": None,
        "lancado_por": None,
        "no_erp": 1,
        "valor_titulo": valor,
        "DATA": venc,
        "PGMOVMOV_NDUPL": num,
        "PGMOVMOV_CGC": cnpj_forn,
        "PGMOVMOV_VALOR": valor,
        "PGMOVMOV_TPOD_1": codigo,
        "PGMOVMOV_CCUSTO_1": r.choice([10, 20, 30]),
        "FORNECEDOR": fo["fornecedor"],
    }


def _pago(nome, cnpj, licenca, seq, num, fornecedor, dia, valor) -> dict:
    return {
        "REVENDA": nome,
        "data_vencimento": dia,
        "data_pagamento": dia,
        "num_doc": num,
        "num_doc_normalizado": num,
        "tipo_doc": "BOL",
        "cnpj": None,
        "cod_banco": 341,
        "codigo_despesa": 430,
        "centro_custo": 10,
        "banco": "341",
        "razao_social": fornecedor,
        "tipo_fornecedor": None,
        "id_unico": f"{cnpj}-{seq}",
        "CNPJ_REV": cnpj,
        "LICENCA": licenca,
        "valor_pago": valor,
        "DATA": dia,
        "PGMOVBAI_DTP": dia,
        "PGMOVBAI_NDUPL": num,
        "PGMOVBAI_CGC": None,
        "PGMOVBAI_VALOR": valor,
        "PGMOVBAI_BCOC": 341,
        "FORNECEDOR": fornecedor,
    }


def _extratos_fabrica(r) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Leitura diária do extrato da fábrica: os totais (limite, crédito, boletos) e as
    partidas em aberto (NF de compra com vencimento)."""
    hoje = b.HOJE
    totais, partidas = [], []
    # Cada revenda tem uma carteira de NFs; uma NF nova entra quase todo dia e sai quando vence.
    carteira: dict[str, list[dict]] = {nome: [] for nome, *_ in REVENDAS}
    nf = 400000
    dias = _uteis(hoje - timedelta(days=DIAS_LEITURAS + 30), hoje)
    for dia in dias:
        lida = datetime.combine(dia, datetime.min.time()).replace(hour=r.randint(6, 8), minute=r.randint(0, 59))
        for nome, cnpj, licenca, codigo in REVENDAS:
            notas = [n for n in carteira[nome] if n["vencimento"] >= dia]
            for _ in range(r.choice([0, 1, 1, 2])):
                nf += r.randint(1, 40)
                notas.append(
                    {
                        "nf": nf,
                        "valor": round(r.uniform(40_000, 320_000), 2),
                        "lancamento": dia,
                        "vencimento": dia + timedelta(days=r.choice([14, 21, 21, 28, 28, 35])),
                    }
                )
            carteira[nome] = notas
            if dia < hoje - timedelta(days=DIAS_LEITURAS):
                continue
            boletos = round(sum(n["valor"] for n in notas), 2)
            # Uma divergência de propósito na última leitura (o alerta do cabeçalho do Fluxo).
            if dia == dias[-1] and nome == "Teresina":
                boletos = round(boletos + 18_430.55, 2)
            totais.append(
                {
                    "data_hora": lida,
                    "REVENDA": nome,
                    "data": dia,
                    "codigo_empresa": codigo,
                    "descricao_empresa": f"REVENDA {nome.upper()}",
                    "fabrica": FABRICA,
                    "limite_credito": float(LIMITES[nome]),
                    "dividas_a_receber": round(r.uniform(0, 50_000), 2),
                    "valor_vendas_processadas": round(r.uniform(200_000, 900_000), 2),
                    "valor_total": boletos,
                    "saldo_ordens_pagamento": 0.0,
                    "saldo_cheques_devolvidos": 0.0,
                    "saldo_debitos_diversos": round(r.uniform(40_000, 380_000), 2),
                    "saldo_cheques": 0.0,
                    "saldo_boletos": boletos,
                    "CNPJ_REV": cnpj,
                    "LICENCA": licenca,
                }
            )
            for n in notas:
                partidas.append(
                    {
                        "id_unico": f"{codigo}-{n['nf']}-{dia:%Y%m%d}",
                        "data_hora": lida,
                        "REVENDA": nome,
                        "codigo_empresa": codigo,
                        "descricao_empresa": f"REVENDA {nome.upper()}",
                        "fabrica": FABRICA,
                        "cpgt": "B",
                        "lneg": "01",
                        "data_lancamento": n["lancamento"],
                        "vencimento_liquido": n["vencimento"],
                        "tipo_documento": "RV",
                        "mp": "B",
                        "ce": "",
                        "numero_documento": f"{n['nf']:010d}",
                        "montante_mi": n["valor"],
                        "texto": f"NF {n['nf']} VENDA DE MERCADORIA",
                        "CNPJ_REV": cnpj,
                        "LICENCA": licenca,
                    }
                )
    return pl.DataFrame(totais, infer_schema_length=None), pl.DataFrame(partidas, infer_schema_length=None)


def _emprestimos_revendas(r) -> pl.DataFrame:
    """Livro dos empréstimos entre as revendas: quem pediu (157), emprestou (158), recebeu (159), devolveu (160)."""
    hoje = b.HOJE
    pares = [
        ("Fortaleza", "Natal"),
        ("Teresina", "Fortaleza"),
        ("São Luís", "Natal"),
        ("Teresina", "HOLDING"),
        ("Natal", "HOLDING"),
    ]
    cnpj_de = {nome: cnpj for nome, cnpj, *_ in REVENDAS}
    linhas = []
    for tomador, credor in pares:
        saldo = 0.0
        dia = hoje - timedelta(days=330)
        while dia < hoje:
            dia += timedelta(days=r.randint(8, 30))
            if dia > hoje:
                break
            if saldo < 50_000 or r.random() < 0.55:
                valor = round(r.uniform(30_000, 220_000), -2)
                saldo += valor
                movs = [(tomador, credor, 157, "EMPRESTIMO RECEBIDO"), (credor, tomador, 158, "EMPRESTIMO CONCEDIDO")]
            else:
                valor = round(min(saldo, r.uniform(20_000, 180_000)), -2)
                saldo -= valor
                movs = [(tomador, credor, 160, "DEVOLUCAO DE EMPRESTIMO"), (credor, tomador, 159, "DEVOLUCAO RECEBIDA")]
            for dono, cliente, codigo, descricao in movs:
                if dono not in cnpj_de:
                    continue
                linhas.append(
                    {
                        "CNPJ_REV": cnpj_de[dono],
                        "REVENDA": dono,
                        "LICENCA": "",
                        "data_lancamento": dia,
                        "documento": f"EMP{r.randint(1000, 9999)}",
                        "descricao": f"{descricao} {cliente.upper()}",
                        "codigo_hp": codigo,
                        "valor": valor,
                        "revenda_cliente": cliente,
                    }
                )
    return pl.DataFrame(linhas, infer_schema_length=None)


PASTA_EXTRATO = b.RAIZ / "Financeiro" / "data" / "bd_extrato"
MESES_EXTRATO = 6
BANCOS_DA_REVENDA = [
    (1, "BANCO ALFA", "0451", "000123456"),
    (2, "BANCO BETA", "1020", "000987654"),
    (999, "CAIXA GERAL", "", ""),
]
# (hp, histórico, lado, faixa de valor, por dia útil)
LANCAMENTOS = {
    1: [
        (10, "DEPOSITO DE CLIENTES", "C", (800, 18_000), 6),
        (12, "PIX RECEBIDO", "C", (50, 6_000), 9),
        (50, "PAGAMENTO DE TITULOS", "D", (300, 25_000), 5),
        (55, "PAGAMENTO FABRICA", "D", (40_000, 250_000), 0.3),
        (60, "TARIFA BANCARIA", "D", (8, 90), 1),
        (31, "TRANSF. ENTRE CONTAS", "D", (5_000, 60_000), 0.4),
    ],
    2: [
        (12, "PIX RECEBIDO", "C", (50, 4_000), 5),
        (30, "TRANSF. ENTRE CONTAS", "C", (5_000, 60_000), 0.4),
        (50, "PAGAMENTO DE TITULOS", "D", (300, 15_000), 3),
        (60, "TARIFA BANCARIA", "D", (8, 60), 0.6),
    ],
    999: [
        (70, "RECEBIMENTO EM DINHEIRO", "C", (100, 9_000), 4),
        (71, "SANGRIA PARA DEPOSITO", "D", (2_000, 30_000), 1),
        (72, "DESPESAS DE ROTA", "D", (20, 600), 2),
    ],
}


def _extratos_bancarios(r) -> None:
    """O movimento dos bancos de cada revenda, como a consulta ao ERP grava (data/bd_extrato/<cnpj>/)."""
    f = b.faker("financeiro-extrato")
    hoje = b.HOJE
    total = hoje.year * 12 + hoje.month - 1 - MESES_EXTRATO
    desde = date(total // 12, total % 12 + 1, 1)
    usuarios = [f"{f.first_name()}.{f.last_name()[0]}".upper() for _ in range(6)]
    for nome, cnpj, _licenca, _cod in REVENDAS:
        linhas = []
        doc = r.randint(100000, 200000)
        for dia in b.dias_uteis(desde, hoje):
            for banco, *_ in BANCOS_DA_REVENDA:
                for hp, historico, lado, (minimo, maximo), por_dia in LANCAMENTOS[banco]:
                    quantos = int(por_dia) + (1 if r.random() < por_dia % 1 else 0)
                    for _ in range(int(quantos * r.uniform(0.6, 1.4)) if por_dia >= 1 else quantos):
                        valor = round(r.uniform(minimo, maximo), 2)
                        doc += r.randint(1, 30)
                        baixado = (hoje - dia).days > 5 and r.random() < 0.92
                        baixa = dia + timedelta(days=r.choice([0, 1, 1, 2, 3]))
                        linhas.append(
                            {
                                "banco": banco,
                                "data": dia,
                                "historico": historico,
                                "hp": hp,
                                "documento": str(doc),
                                "debito": valor if lado == "D" else None,
                                "credito": valor if lado == "C" else None,
                                "usuario": r.choice(usuarios),
                                "lmo": f"{baixa:%d%m%Y}" if baixado else "",
                                "dtl": int(f"{dia:%Y%m%d}"),
                                "doc_control": str(doc),
                                "valor_control": f"{-valor if lado == 'D' else valor:.2f}",
                            }
                        )
        base = pl.DataFrame(linhas, infer_schema_length=None).sort(["data", "banco"], maintain_order=True)
        rotulos = {
            str(bco): f"{bco} - {nm}" + (f" · ag {ag}" if ag else "") + (f" · c/c {cc}" if cc else "")
            for bco, nm, ag, cc in BANCOS_DA_REVENDA
        }
        pasta = PASTA_EXTRATO / cnpj
        pasta.mkdir(parents=True, exist_ok=True)
        base.write_parquet(pasta / "movimento.parquet", compression="zstd")
        consultado = datetime.combine(hoje, datetime.min.time()).replace(hour=7, minute=52)
        info = {
            "revenda": nome,
            "desde": desde.isoformat(),
            "bancos": rotulos,
            "linhas": base.height,
            "tem_situacao": True,
            "consultado_em": consultado.isoformat(timespec="seconds"),
            "segundos": 4.8,
        }
        (pasta / "movimento.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
        # O catálogo dos filtros (bancos, usuários, HP com o histórico mais comum).
        hps = {str(hp): f"{hp} - {hist}" for banco in LANCAMENTOS for hp, hist, *_ in LANCAMENTOS[banco]}
        catalogo = {
            "bancos": rotulos,
            "usuarios": sorted(usuarios),
            "hps": {k: hps[k] for k in sorted(hps, key=int)},
            "atualizado_em": consultado.isoformat(timespec="seconds"),
        }
        (pasta / "catalogo.json").write_text(json.dumps(catalogo, ensure_ascii=False), encoding="utf-8")
        print(f"  bd_extrato/{cnpj}/movimento.parquet: {base.height:,} linhas".replace(",", "."))


def gerar() -> None:
    print("Financeiro")
    _extratos_bancarios(b.rng("financeiro-extrato"))
    r = b.rng("financeiro")
    PASTA.mkdir(parents=True, exist_ok=True)
    for antigo in PASTA.glob("*.parquet"):
        antigo.unlink()
    (cp, pagos, pagos_emp), configs = _contas_pagar(r)
    totais, partidas = _extratos_fabrica(r)
    tabelas = {
        "contas_pagar": cp,
        "titulos_pagos": pagos,
        "titulos_pagos_emprestimos": pagos_emp,
        "emprestimos_configuracoes": configs,
        "extratos_fabricas_totais": totais,
        "extratos_fabricas_tabela": partidas,
        "emprestimos_revendas": _emprestimos_revendas(r),
    }
    for nome, df in tabelas.items():
        df.write_parquet(PASTA / f"{nome}.parquet", compression="zstd")
        print(f"  bd_financeiro/{nome}.parquet: {df.height:,} linhas".replace(",", "."))
    momento = datetime.combine(b.HOJE, datetime.min.time()).replace(hour=7, minute=48).isoformat(timespec="seconds")
    (PASTA / "_atualizacoes.json").write_text(
        json.dumps({n: momento for n in tabelas}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Retratos do Fluxo: o próprio app monta a tabela de cada dia passado.
    subprocess.run(
        [sys.executable, str(b.RAIZ / "Financeiro" / "scripts" / "retratos_fluxo.py"), str(DIAS_LEITURAS - 15)],
        check=True,
    )
