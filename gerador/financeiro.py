"""Contas a pagar e a receber, extratos e fechamento de caixa fictícios, mais
indicadores econômicos de verdade (Banco Central)."""

import json
from datetime import date, timedelta

import polars as pl

from gerador import base as b
from gerador.publicos import serie_bcb

# Bancos fictícios: nome de banco real não entra no portfólio.
CONTAS = [
    ("Banco Atlântico", "Ag 0101 / CC 22.345-6", 850000.0),
    ("Banco Coral", "Ag 3030 / CC 7.781-0", 420000.0),
    ("Cooperativa Sertão", "Ag 0007 / CC 10.552-3", 180000.0),
]
FORMAS_PAGAR = ["Boleto", "PIX", "TED", "Débito automático"]
CENTROS = {
    "Fábrica": "Compra de mercadoria",
    "Combustível": "Frota",
    "Manutenção de frota": "Frota",
    "Energia e água": "Estrutura",
    "Aluguel": "Estrutura",
    "Serviços": "Administrativo",
    "Material de escritório": "Administrativo",
    "Impostos": "Tributos",
}
DESCRICOES_SO_BANCO = [
    ("Tarifa de manutenção de conta", -89.9, -89.9),
    ("Tarifa de TED", -12.5, -12.5),
    ("IOF", -380.0, -12.0),
    ("Depósito não identificado", 300.0, 9000.0),
    ("Estorno de cobrança", -2500.0, -150.0),
]


def _titulos_pagar() -> pl.DataFrame:
    r = b.rng("pagar")
    forn = b.fornecedores().to_dicts()
    inicio, fim = b.meses_atras(b.HOJE, 6), b.HOJE + timedelta(days=60)
    linhas = []
    num = 40000
    for f in forn:
        # Fábrica fatura toda semana; o resto, uma ou duas vezes por mês.
        intervalo = 7 if f["tipo_despesa"] == "Fábrica" else r.choice([15, 30, 30])
        d = inicio + timedelta(days=r.randint(0, intervalo))
        while d <= fim:
            filial = r.choice(b.FILIAIS).nome
            vencimento = d + timedelta(days=r.choice([7, 14, 21, 28, 30]))
            valor = round(r.uniform(f["valor_min"], f["valor_max"]), 2)
            if vencimento < b.HOJE:
                # Só o vencido recente fica sem pagar: o atraso antigo já foi quitado.
                atrasou = (b.HOJE - vencimento).days <= 20 and r.random() < 0.12
                pago_em = None if atrasou else vencimento - timedelta(days=r.choice([0, 0, 0, 1, 2]))
            elif vencimento == b.HOJE:
                pago_em = b.HOJE if r.random() < 0.4 else None
            else:
                pago_em = None
            num += 1
            linhas.append(
                {
                    "titulo": num,
                    "fornecedor": f["fornecedor"],
                    "tipo_despesa": f["tipo_despesa"],
                    "centro_custo": CENTROS[f["tipo_despesa"]],
                    "filial": filial,
                    "emissao": d,
                    "vencimento": vencimento,
                    "valor": valor,
                    "forma": r.choice(FORMAS_PAGAR),
                    "pago_em": pago_em,
                    "conta": r.choices([c[0] for c in CONTAS], weights=[6, 3, 1])[0],
                }
            )
            d += timedelta(days=intervalo + r.randint(-2, 2))
    return pl.DataFrame(linhas)


def _receber() -> pl.DataFrame:
    """Recebimentos previstos por dia, filial e forma (a venda a prazo vira caixa depois)."""
    r = b.rng("receber")
    formas = [("Boleto", 0.45, 21), ("PIX", 0.25, 0), ("Cartão", 0.18, 30), ("Dinheiro", 0.12, 0)]
    linhas = []
    for filial in b.FILIAIS:
        base_dia = r.uniform(70000, 95000)
        for d in b.dias_uteis(b.meses_atras(b.HOJE, 6), b.HOJE + timedelta(days=60)):
            for forma, peso, _prazo in formas:
                previsto = round(base_dia * peso * r.uniform(0.75, 1.25), 2)
                if d < b.HOJE:
                    recebido = round(previsto * (r.uniform(0.9, 1.0) if forma == "Boleto" else 1.0), 2)
                else:
                    recebido = None
                linhas.append(
                    {
                        "data": d,
                        "filial": filial.nome,
                        "forma": forma,
                        "previsto": previsto,
                        "recebido": recebido,
                        "conta": r.choices([c[0] for c in CONTAS], weights=[6, 3, 1])[0],
                    }
                )
    return pl.DataFrame(linhas)


def _extratos(pagar: pl.DataFrame, receber: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Extrato do banco e o lançamento no ERP dos últimos 3 meses. A maioria casa;
    tarifas e depósitos sem nota só aparecem no banco, e uns pagamentos ficam
    lançados no ERP sem ter saído do banco ainda."""
    r = b.rng("extratos")
    inicio = b.meses_atras(b.HOJE, 2)
    banco, erp = [], []
    seq = 0
    pagos = pagar.filter(pl.col("pago_em").is_not_null(), pl.col("pago_em") >= inicio)
    for t in pagos.iter_rows(named=True):
        seq += 1
        desc = f"PAG {t['forma'].upper()} {t['fornecedor'][:28]}"
        erp.append(
            {
                "id": seq,
                "data": t["pago_em"],
                "conta": t["conta"],
                "historico": f"Título {t['titulo']} - {t['fornecedor']}",
                "valor": -t["valor"],
            }
        )
        if r.random() < 0.3 and (b.HOJE - t["pago_em"]).days < 4:
            continue  # ainda não compensou no banco
        banco.append({"id": seq, "data": t["pago_em"], "conta": t["conta"], "descricao": desc, "valor": -t["valor"]})
    recebidos = receber.filter(pl.col("recebido").is_not_null(), pl.col("data") >= inicio)
    for rec in recebidos.iter_rows(named=True):
        seq += 1
        erp.append(
            {
                "id": seq,
                "data": rec["data"],
                "conta": rec["conta"],
                "historico": f"Recebimento {rec['forma']} - {rec['filial']}",
                "valor": rec["recebido"],
            }
        )
        banco.append(
            {
                "id": seq,
                "data": rec["data"],
                "conta": rec["conta"],
                "descricao": f"CRED {rec['forma'].upper()} LOTE {seq:06d}",
                "valor": rec["recebido"],
            }
        )
    for d in b.dias_uteis(inicio, b.HOJE - timedelta(days=1)):
        for conta, _, _ in CONTAS:
            if r.random() < 0.18:
                desc, lo, hi = r.choice(DESCRICOES_SO_BANCO)
                seq += 1
                banco.append(
                    {
                        "id": None,
                        "data": d,
                        "conta": conta,
                        "descricao": desc.upper(),
                        "valor": round(r.uniform(min(lo, hi), max(lo, hi)), 2),
                    }
                )
    return pl.DataFrame(banco), pl.DataFrame(erp)


def _fechamento_caixa() -> pl.DataFrame:
    """Para cada filial e dia útil: em que dia o caixa daquele dia foi fechado."""
    r = b.rng("caixa")
    linhas = []
    for filial in b.FILIAIS:
        disciplina = r.uniform(0.6, 0.92)
        for d in b.dias_uteis(b.HOJE - timedelta(days=45), b.HOJE - timedelta(days=1)):
            atraso = 0 if r.random() < disciplina else r.choice([1, 1, 2, 3, 5, 8])
            # Teresina está com os dois últimos dias sem fechar.
            if filial.codigo == "THE" and (b.HOJE - d).days <= 2:
                atraso = 99
            fechado = d + timedelta(days=atraso)
            linhas.append({"filial": filial.nome, "data": d, "fechado_em": fechado if fechado <= b.HOJE else None})
    return pl.DataFrame(linhas)


def _indicadores() -> pl.DataFrame:
    dolar = serie_bcb(1, "dolar")
    selic = serie_bcb(432, "selic")
    ipca = serie_bcb(433, "ipca_mes", dias=800)
    return (
        dolar.join(selic, on="data", how="full", coalesce=True)
        .join(ipca, on="data", how="full", coalesce=True)
        .sort("data")
    )


def gerar() -> None:
    print("Financeiro")
    pagar = _titulos_pagar()
    receber = _receber()
    banco, erp = _extratos(pagar, receber)
    b.gravar(pagar, "Financeiro", "titulos_pagar")
    b.gravar(receber, "Financeiro", "receber")
    b.gravar(banco, "Financeiro", "extrato_banco")
    b.gravar(erp, "Financeiro", "lancamentos_erp")
    b.gravar(pl.DataFrame([{"conta": c, "dados": d, "saldo_inicial": s} for c, d, s in CONTAS]), "Financeiro", "contas")
    b.gravar(_fechamento_caixa(), "Financeiro", "fechamento_caixa")
    b.gravar(_indicadores(), "Financeiro", "indicadores_bcb")
    with open(b.RAIZ / "Financeiro" / "data" / "_gerado_em.json", "w", encoding="utf-8") as arq:
        json.dump({"data_base": b.HOJE.isoformat(), "gerado_em": date.today().isoformat()}, arq)
