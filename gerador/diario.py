"""Caches do Diário Financeiro no esquema original: saldos dos bancos, caixa 999, Dados
Manuais, pagamentos marcados pela tela e a Composição Financeira (itens x bancos), com
os retratos dos dias anteriores para o Histórico.

A Composição é montada aqui com as mesmas regras do pipeline original: as folhas dos
Dados Manuais e as somas vêm de Financeiro/core/composicao_manual.py, o mesmo módulo
que a tela usa para refazer a conta quando um dado manual muda."""

import hashlib
import sys
import unicodedata
from datetime import date, datetime, timedelta

import polars as pl

from gerador import base as b

sys.path.insert(0, str(b.PY / "Financeiro"))
from core import composicao_manual as cm  # noqa: E402

# Contas de cada revenda (o rótulo é o do catálogo da Composição) e o código de compensação.
BANCOS_DA_REVENDA = {
    "Natal": ["Bradesco 1", "Bradesco 2", "Itaú", "Caixa 999"],
    "Fortaleza": ["Bradesco 1", "Itaú", "Daycoval 1", "Caixa 999"],
    "Teresina": ["BB", "Bradesco 1", "Caixa 999"],
    "São Luís": ["Bradesco 1", "Sicoob 1", "Caixa 999"],
}
COD_BANCO = {
    "Bradesco 1": "237",
    "Bradesco 2": "237",
    "Itaú": "341",
    "BB": "001",
    "Sicoob 1": "756",
    "Daycoval 1": "707",
    "Caixa 999": "999",
}
NOME_BANCO = {"237": "BRADESCO", "341": "ITAU", "001": "BANCO DO BRASIL", "756": "SICOOB", "707": "DAYCOVAL"}
# (saldo típico, limite especial, aplicação típica) por conta.
PERFIL = {
    "Bradesco 1": (380_000, 300_000, 250_000),
    "Bradesco 2": (60_000, 0, 0),
    "Itaú": (140_000, 150_000, 120_000),
    "BB": (220_000, 200_000, 90_000),
    "Sicoob 1": (90_000, 80_000, 0),
    "Daycoval 1": (45_000, 0, 300_000),
}
DIAS_HISTORICO = 30
DESPESAS_CAIXA = [
    ("DESPESA COMBUSTIVEL ROTA", (80, 900)),
    ("DIARIA MOTORISTA", (60, 240)),
    ("DIARIA AJUDANTE", (50, 160)),
    ("MANUTENCAO VEICULO", (120, 2_400)),
    ("PEDAGIO", (15, 120)),
    ("MATERIAL DE LIMPEZA", (40, 350)),
    ("FRETE AVULSO", (150, 1_800)),
    ("LANCHE EQUIPE ENTREGA", (40, 260)),
]


def chave_banco(rotulo: str) -> str:
    sem_acento = unicodedata.normalize("NFD", rotulo).encode("ascii", "ignore").decode("ascii")
    return "_".join("".join(c if c.isalnum() else " " for c in sem_acento).strip().lower().split())


def _id(*partes) -> str:
    return hashlib.md5("|".join(map(str, partes)).encode("utf-8")).hexdigest()[:25]


def _dias() -> tuple[list[date], date]:
    """Os dias úteis passados do histórico e o dia de hoje (a referência do Diário)."""
    hoje = b.HOJE
    passados = [
        d
        for d in b.dias_uteis(hoje - timedelta(days=DIAS_HISTORICO * 7 // 5), hoje - timedelta(days=1))
        if d.weekday() < 5
    ]
    return passados[-DIAS_HISTORICO:], hoje


def _extratos_bancos(r, revendas, dias) -> pl.DataFrame:
    linhas, ident = [], 0
    for nome, cnpj, licenca, _cod in revendas:
        for n, rotulo in enumerate(BANCOS_DA_REVENDA[nome]):
            if rotulo == "Caixa 999":
                continue
            tipico, limite, aplicacao = PERFIL[rotulo]
            saldo = tipico * r.uniform(0.6, 1.4)
            invest = aplicacao * r.uniform(0.8, 1.2)
            cod = COD_BANCO[rotulo]
            for dia in dias:
                saldo = max(-limite * 0.5, saldo + r.gauss(0, tipico * 0.18))
                invest = max(0.0, invest + (r.gauss(0, aplicacao * 0.03) if aplicacao else 0))
                bloqueado = round(r.uniform(3_000, 25_000), 2) if r.random() < 0.04 else 0.0
                ident += 1
                linhas.append(
                    {
                        "id": ident,
                        "REVENDA": nome,
                        "banco": NOME_BANCO[cod],
                        "banco_contabil": rotulo,
                        "agencia": f"{1000 + n * 37}",
                        "conta": f"{10000 + n * 101}-{n}",
                        "conta_contabil": f"11{n:02d}",
                        "cod_banco": cod,
                        "data": datetime.combine(dia, datetime.min.time()).replace(hour=6, minute=30),
                        "saldo_final": round(saldo, 2),
                        "saldo_investimento": round(invest, 2),
                        "saldo_bloqueado": bloqueado,
                        "limite_total": float(limite),
                        "limite_disponivel": float(limite),
                        "saldo_total": round(saldo + limite, 2),
                        "CNPJ_REV": cnpj,
                        "LICENCA": licenca,
                        "conta_chave": f"{nome}|{rotulo}",
                    }
                )
    return pl.DataFrame(linhas, infer_schema_length=None)


def _caixa(r, revendas, dias):
    """Baixas do caixa (saldo_banco_999), extrato do caixa 999, batida diária e vales provisórios."""
    baixas, extrato, batida, vales = [], [], [], []
    f = b.faker("financeiro-caixa")
    responsaveis = [f"{f.first_name()} {f.last_name()}".upper() for _ in range(8)]
    for nome, cnpj, licenca, _cod in revendas:
        saldo_999 = r.uniform(15_000, 60_000)
        for dia in dias:
            for n in range(r.randint(5, 12)):
                baixas.append(
                    {
                        "REVENDA": nome,
                        "data_baixa": dia,
                        "valor_dinheiro": round(r.uniform(1_500, 14_000), 2),
                        "valor_moeda": round(r.uniform(0, 400), 2),
                        "valor_pix": round(r.uniform(800, 11_000), 2),
                        "CNPJ_REV": cnpj,
                        "LICENCA": licenca,
                        "codigo_romaneio": f"{dia:%m%d}{n + 1:03d}",
                    }
                )
            doc = r.randint(1000, 9000)
            total_dia = 0.0
            for historico, (minimo, maximo) in DESPESAS_CAIXA:
                for _ in range(r.choice([0, 1, 1, 2, 3])):
                    doc += 1
                    valor = round(r.uniform(minimo, maximo), 2)
                    total_dia += valor
                    extrato.append(_linha_extrato(nome, cnpj, licenca, dia, f"DESP{doc}", historico, valor, 999))
            # Cobrança e adiantamento: entram no extrato do caixa e a tela tira (prefixos CR0 e AC0).
            extrato.append(
                _linha_extrato(
                    nome, cnpj, licenca, dia, f"CR0{doc}", "COBRANCA DINHEIRO", round(r.uniform(5_000, 30_000), 2), 999
                )
            )
            dinheiro = round(r.uniform(20_000, 90_000), 2)
            oct_, vale = round(r.uniform(0, 6_000), 2), round(r.uniform(0, 1_500), 2)
            pix_prov = round(r.uniform(0, 4_000), 2)
            movimento = dinheiro + oct_ + vale + pix_prov
            saldo_atual = saldo_999 + movimento - total_dia - dinheiro * 0.9
            batida.append(
                {
                    "REVENDA": nome,
                    "data": dia,
                    "saldo_999_anterior": round(saldo_999, 2),
                    "total_dia": round(movimento, 2),
                    "dinheiro_moeda": dinheiro,
                    "cheque_a_vista": 0.0,
                    "cheque_pre": 0.0,
                    "oct": oct_,
                    "vale": vale,
                    "fazenda": 0.0,
                    "octs_nao_compensadas": round(r.uniform(0, 2_500), 2),
                    "pix_provisorios": pix_prov,
                    "romaneios_pendentes": round(r.uniform(0, 8_000), 2),
                    "total_movimento_dia": round(movimento, 2),
                    "saldo_atual_caixa": round(saldo_atual, 2),
                    "saldo_octs_fisico": oct_,
                    "total_diferenca_dia": round(r.choice([0.0, 0.0, 0.0, r.uniform(-50, 50)]), 2),
                    "CNPJ_REV": cnpj,
                    "LICENCA": licenca,
                    "cheque_caucao": 0.0,
                    "adiantamentos": r.randint(0, 3),
                }
            )
            saldo_999 = max(5_000.0, saldo_atual)
            if r.random() < 0.35:
                vales.append(
                    {
                        "REVENDA": nome,
                        "DATA": dia,
                        "DATA_CAIXA": dia,
                        "DESCRICAO": r.choice(
                            ["VALE COMBUSTIVEL", "ADIANTAMENTO DE DIARIA", "VALE TRANSPORTE", "COMPRA EMERGENCIAL"]
                        ),
                        "VALOR": round(r.uniform(50, 1_200), 2),
                        "RESPONSAVEL": r.choice(responsaveis),
                        "CNPJ_REV": cnpj,
                        "LICENCA": licenca,
                    }
                )
    return (
        pl.DataFrame(baixas),
        pl.DataFrame(extrato, infer_schema_length=None),
        pl.DataFrame(batida, infer_schema_length=None).with_columns(pl.col("adiantamentos").cast(pl.Int32)),
        pl.DataFrame(vales),
    )


def _linha_extrato(nome, cnpj, licenca, dia, doc, historico, valor, nrbco) -> dict:
    return {
        "CNPJ_REV": cnpj,
        "REVENDA": nome,
        "LICENCA": licenca,
        "data_lancamento": dia,
        "documento": doc,
        "descricao": historico,
        "codigo_hp": 72,
        "valor": valor,
        "cod_banco": nrbco,
        "banco": "CAIXA" if nrbco == 999 else NOME_BANCO.get(f"{nrbco:03d}", str(nrbco)),
        "DATA": dia,
        "PGMOVBAN_NRDOC_EXTENSO": doc,
        "PGMOVBAN_HISTORICO": historico,
        "PGMOVBAN_CODHST": 72,
        "PGMOVBAN_VALORL": valor,
        "PGMOVBAN_NRBCO": nrbco,
    }


def _dados_manuais(r, revendas, dias, hoje) -> pl.DataFrame:
    """O que o financeiro lança à mão: transferências, pix diário, adiantamento de romaneio,
    romaneio pendente e empréstimo entre as revendas."""
    linhas, ident = [], 0
    nomes = [n for n, *_ in revendas]

    def nova(nome, dia, banco, **valores):
        nonlocal ident
        ident += 1
        linha = {
            "id": ident,
            "transferencia_bancos": 0.0,
            "adiantamento_romaneios": 0.0,
            "devolucao_emprestimos": 0.0,
            "brinks_antes_16": 0.0,
            "banco": banco,
            "REVENDA": nome,
            "destino_transf": "",
            "data": dia,
            "hora": f"{r.randint(8, 17):02d}:{r.randint(0, 59):02d}:{r.randint(0, 59):02d}",
            "romaneio_pendente_encerrado": 0.0,
            "credito_mar_utilizado": 0.0,
            "tipo_emprestimo_devolucao": "",
            "entrada_saida": "",
            "revenda_origem_destino": "",
            "revenda_destino": "",
            "transferencia_revendas": 0.0,
            "credito_parceiro": None,
            "credito_parceiro_utilizado": None,
        }
        linha.update(valores)
        linhas.append(linha)

    for dia in [*dias[-10:], hoje]:
        for nome in nomes:
            bancos = [x for x in BANCOS_DA_REVENDA[nome] if x != "Caixa 999"]
            principal = bancos[0]
            nova(nome, dia, principal, brinks_antes_16=round(r.uniform(15_000, 70_000), 2))
            if r.random() < 0.6:
                nova(nome, dia, "Caixa 999", adiantamento_romaneios=round(r.uniform(2_000, 18_000), 2))
            if len(bancos) > 1 and r.random() < 0.55:
                nova(
                    nome,
                    dia,
                    bancos[1],
                    transferencia_bancos=round(r.uniform(10_000, 80_000), -2),
                    destino_transf=principal,
                )
            if r.random() < 0.3:
                nova(nome, dia, "Caixa 999", romaneio_pendente_encerrado=round(r.uniform(500, 6_000), 2))
        if r.random() < 0.45:
            origem, destino = r.sample(nomes, 2)
            valor = round(r.uniform(30_000, 200_000), -3)
            tipo = r.choice(["Empréstimo", "Devolução"])
            nova(
                origem,
                dia,
                "Bradesco 1",
                tipo_emprestimo_devolucao=tipo,
                entrada_saida="Saída",
                revenda_origem_destino=destino,
                revenda_destino=destino,
                transferencia_revendas=valor,
                destino_transf="Bradesco 1",
            )
    return pl.DataFrame(linhas, infer_schema_length=None).with_columns(
        pl.col("credito_parceiro").cast(pl.Int32), pl.col("credito_parceiro_utilizado").cast(pl.Int32)
    )


def _pagamentos(r, revendas, dias, hoje, contas_pagar: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Os títulos marcados para pagar pela tela: os dias passados já pagos e a fila de hoje (títulos
    que ainda estão em aberto no Contas a Pagar)."""
    forn = b.fornecedores().filter(pl.col("tipo_despesa") != "Fábrica").to_dicts()
    linhas, ident = [], 0
    for nome, cnpj, _licenca, _cod in revendas:
        bancos = [x for x in BANCOS_DA_REVENDA[nome] if x != "Caixa 999"]
        pesos = [6] + [2] * (len(bancos) - 1)
        for dia in dias:
            for _ in range(r.randint(8, 22)):
                fo = r.choice(forn)
                ident += 1
                valor = round(r.uniform(fo["valor_min"], fo["valor_max"]) / 4, 2)
                juros = round(valor * r.uniform(0.002, 0.03), 2) if r.random() < 0.15 else 0.0
                num = f"{r.randint(10000, 999999)}"
                linhas.append(
                    _pagamento(
                        r,
                        ident,
                        nome,
                        cnpj,
                        dia,
                        dia,
                        num,
                        fo["fornecedor"],
                        f"{fo['cod_fornecedor']:08d}000{r.randint(100, 199)}",
                        fo["tipo_despesa"].upper(),
                        valor,
                        juros,
                        r.choices(bancos + ["Caixa 999"], pesos + [1])[0],
                        pagou="Sim",
                    )
                )
        # A fila de hoje: títulos em aberto que vencem até amanhã.
        abertos = contas_pagar.filter(
            (pl.col("REVENDA") == nome)
            & (pl.col("data_vencimento") <= hoje + timedelta(days=1))
            & (pl.col("data_vencimento") >= hoje - timedelta(days=3))
        ).to_dicts()
        for t in r.sample(abertos, min(len(abertos), r.randint(6, 12))):
            ident += 1
            linha = _pagamento(
                r,
                ident,
                nome,
                cnpj,
                t["data_vencimento"],
                hoje,
                t["num_doc"],
                t["razao_social"],
                t["cnpj"],
                t["descricao_despesa"],
                t["valor_original"],
                t["juros"] or 0.0,
                r.choices(bancos, pesos)[0],
                pagou="Não",
            )
            linha["id_unico"] = t["id_unico"]
            linhas.append(linha)
    pagamentos = pl.DataFrame(linhas, infer_schema_length=None)
    retrato = (
        pagamentos.filter(pl.col("data_pagamento") < hoje)
        .with_columns(pl.col("data_pagamento").alias("data_snapshot"))
        .select(
            "REVENDA",
            "data_snapshot",
            "data_vencimento",
            "razao_social",
            "descricao_despesa",
            "num_doc",
            "tipo_doc",
            "cnpj",
            "valor_original",
            "valor_pago",
            "juros",
            "banco",
            "pagar",
            "pagou",
            "auditoria",
            "conselho",
            "id_unico",
        )
    )
    return pagamentos, retrato


def _pagamento(r, ident, nome, cnpj, venc, dia, num, fornecedor, cnpj_forn, despesa, valor, juros, banco, pagou):
    return {
        "id": ident,
        "id_unico": _id(cnpj, num, ident),
        "REVENDA": nome,
        "data_vencimento": venc,
        "data_pagamento": dia,
        "num_doc": num,
        "num_doc_normalizado": num,
        "tipo_doc": r.choice(["NFE", "NFS", "BOL"]),
        "cnpj": cnpj_forn,
        "valor_original": valor,
        "valor_pago": round(valor + juros, 2),
        "juros": juros,
        "razao_social": fornecedor,
        "descricao_despesa": despesa,
        "pagar": "Sim",
        "banco": banco,
        "data_registro": datetime.combine(dia, datetime.min.time()).replace(
            hour=r.randint(8, 11), minute=r.randint(0, 59)
        ),
        "pagou": pagou,
        "entrada_manual": "Sim" if r.random() < 0.08 else "Não",
        "auditoria": "Sim",
        "conselho": "Não",
        "justificativa": None,
    }


def _composicao(revendas, dia: date, extratos, baixas, extrato_caixa, dados_manuais, pagamentos, credito) -> list[dict]:
    """A matriz item x banco de cada revenda num dia, com as regras do pipeline original."""
    import json

    catalogo = json.loads(cm.ARQUIVO_CATALOGO.read_text(encoding="utf-8"))
    itens = catalogo["itens"]
    categoria_de = {i["chave"]: i["categoria"] for i in itens}
    manuais = dados_manuais.rename({"REVENDA": "revenda"})
    dados = {"dados_manuais": manuais}
    linhas = []
    for nome, cnpj, _licenca, _cod in revendas:
        ext_dia = extratos.filter((pl.col("REVENDA") == nome) & (pl.col("data").dt.date() == dia))
        anterior = max(
            (d for d in baixas.filter(pl.col("REVENDA") == nome)["data_baixa"].unique().to_list() if d < dia),
            default=None,
        )
        for rotulo in BANCOS_DA_REVENDA[nome]:
            banco = chave_banco(rotulo)
            valores: dict[str, float | None] = {}
            conta = ext_dia.filter(pl.col("banco_contabil") == rotulo)
            caixa = banco == "caixa_999"
            for item in itens:
                chave = item["chave"]
                if chave in cm.AGREGADOS:
                    continue
                if chave == "credito_fabrica":
                    valores[chave] = credito.get(nome) if banco == "bradesco_1" else 0.0
                elif chave in cm.ITENS_MANUAIS:
                    valores[chave] = cm.ITENS_MANUAIS[chave](dados, nome, dia, banco)[0]
                elif chave in ("saldo_liberado_conta", "aplicacao_financeira", "limite_especial", "bloqueio_judicial"):
                    coluna = {
                        "saldo_liberado_conta": "saldo_final",
                        "aplicacao_financeira": "saldo_investimento",
                        "limite_especial": "limite_total",
                        "bloqueio_judicial": "saldo_bloqueado",
                    }[chave]
                    valores[chave] = 0.0 if caixa else (float(conta[coluna][0]) if conta.height else None)
                elif chave == "saldo_liberado":
                    valores[chave] = (
                        0.0
                        if caixa
                        else (float(conta["saldo_final"][0] + conta["saldo_investimento"][0]) if conta.height else None)
                    )
                elif chave == "estoque_do_dia":
                    valores[chave] = credito.get(f"{nome}|estoque") if banco == "bradesco_1" else 0.0
                elif chave == "modelo_iv":
                    if caixa and anterior is not None:
                        do_dia = baixas.filter((pl.col("REVENDA") == nome) & (pl.col("data_baixa") == anterior))
                        valores[chave] = float(
                            sum(do_dia[c].sum() for c in ("valor_dinheiro", "valor_moeda", "valor_pix"))
                        )
                    else:
                        valores[chave] = 0.0 if not caixa else None
                elif chave == "saque":
                    valores[chave] = 0.0
                elif chave == "saldo_caixa_dia_anterior":
                    valores[chave] = None
                elif chave == "saldo_dinheiro_cobranca":
                    if caixa and anterior is not None:
                        cob = extrato_caixa.filter(
                            (pl.col("REVENDA") == nome)
                            & (pl.col("DATA") == anterior)
                            & pl.col("PGMOVBAN_NRDOC_EXTENSO").str.starts_with("CR0")
                        )
                        valores[chave] = float(cob["PGMOVBAN_VALORL"].sum())
                    else:
                        valores[chave] = 0.0
                elif chave == "brinks_apos_16":
                    valores[chave] = None
                elif chave == "total_despesas_sugeridas":
                    do_dia = pagamentos.filter(
                        (pl.col("REVENDA") == nome)
                        & (pl.col("banco") == rotulo)
                        & (pl.col("pagar") == "Sim")
                        & (pl.col("data_pagamento") == dia)
                    )
                    despesas = -float(do_dia["valor_pago"].sum() or 0)
                    ja = sum(cm.ITENS_MANUAIS[c](dados, nome, dia, banco)[0] or 0 for c in cm.SAIDAS_JA_CONTADAS)
                    if caixa and anterior is not None:
                        gasto = extrato_caixa.filter(
                            (pl.col("REVENDA") == nome)
                            & (pl.col("DATA") == anterior)
                            & pl.col("PGMOVBAN_NRDOC_EXTENSO").str.starts_with("DESP")
                        )
                        despesas -= float(gasto["PGMOVBAN_VALORL"].sum() or 0)
                    valores[chave] = despesas - ja
                else:
                    valores[chave] = None
            for chave, regra in cm.AGREGADOS.items():
                if regra.get("fora_do_caixa") and caixa:
                    valores[chave] = 0.0
                    continue
                parcelas = list(regra.get("chaves", []))
                for categoria in regra.get("categorias", []):
                    parcelas += [c for c, cat in categoria_de.items() if cat == categoria]
                presentes = [valores.get(p) for p in parcelas if valores.get(p) is not None]
                valores[chave] = sum(presentes) if presentes else None
            for ordem, item in enumerate(itens, start=1):
                valor = valores.get(item["chave"])
                linhas.append(
                    {
                        "CNPJ_REV": cnpj,
                        "REVENDA": nome,
                        "DATA_REFERENCIA": dia,
                        "ORDEM": ordem,
                        "CHAVE": item["chave"],
                        "ITEM": item["rotulo"],
                        "CATEGORIA": item["categoria"],
                        "NATUREZA": item["natureza"],
                        "BANCO": banco,
                        "VALOR": None if valor is None else round(float(valor), 2),
                        "MOTIVO": "soma das parcelas" if item["chave"] in cm.AGREGADOS else "dado do dia",
                        "AVISO_REVENDA": "",
                    }
                )
    return linhas


def _verificacao(r, revendas, dias) -> pl.DataFrame:
    f = b.faker("financeiro-verificacao")
    financeiro = [b.login_de(f"{f.first_name()} {f.last_name()}") for _ in range(3)]
    diretoria = [b.login_de(f"{f.first_name()} {f.last_name()}") for _ in range(2)]
    linhas, ident = [], 0
    for dia in dias:
        for nome, *_ in revendas:
            ident += 1
            fin, dire = r.random() < 0.95, r.random() < 0.8
            quando = datetime.combine(dia, datetime.min.time())
            linhas.append(
                {
                    "id": ident,
                    "data": dia,
                    "REVENDA": nome,
                    "financeiro_ok": int(fin),
                    "financeiro_em": quando.replace(hour=r.randint(9, 11), minute=r.randint(0, 59)) if fin else None,
                    "financeiro_por": r.choice(financeiro) if fin else None,
                    "diretoria_ok": int(fin and dire),
                    "diretoria_em": quando.replace(hour=r.randint(12, 16), minute=r.randint(0, 59))
                    if fin and dire
                    else None,
                    "diretoria_por": r.choice(diretoria) if fin and dire else None,
                    "financeiro_desmarcado_em": None,
                    "financeiro_desmarcado_por": None,
                    "diretoria_desmarcada_em": None,
                    "diretoria_desmarcada_por": None,
                }
            )
    return pl.DataFrame(linhas, infer_schema_length=None).with_columns(
        pl.col("financeiro_desmarcado_em").cast(pl.Datetime("us")),
        pl.col("financeiro_desmarcado_por").cast(pl.Utf8),
        pl.col("diretoria_desmarcada_em").cast(pl.Int32),
        pl.col("diretoria_desmarcada_por").cast(pl.Int32),
    )


def _justificativas(r, contas_pagar: pl.DataFrame) -> pl.DataFrame:
    f = b.faker("financeiro-justificativas")
    autores = [b.login_de(f"{f.first_name()} {f.last_name()}") for _ in range(3)]
    textos = [
        "Boleto chegou depois do vencimento; fornecedor confirmou o valor com juros.",
        "Aguardando a nota de serviço para conferir o valor.",
        "Pagamento combinado em duas parcelas.",
        "Fornecedor reemitiu o boleto com nova data.",
        "Juros cobrados pela segunda via do boleto.",
    ]
    atrasados = contas_pagar.filter(pl.col("juros").fill_null(0) > 0).to_dicts()
    linhas = []
    for n, t in enumerate(r.sample(atrasados, min(len(atrasados), 25)), start=1):
        quando = datetime.combine(b.HOJE - timedelta(days=r.randint(0, 10)), datetime.min.time()).replace(
            hour=r.randint(8, 17)
        )
        autor = r.choice(autores)
        linhas.append(
            {
                "id": n,
                "id_unico": t["id_unico"],
                "REVENDA": t["REVENDA"],
                "texto": r.choice(textos),
                "criado_em": quando,
                "criado_por": autor,
                "atualizado_em": quando,
                "atualizado_por": autor,
            }
        )
    return pl.DataFrame(linhas, infer_schema_length=None)


def _cod_despesa(revendas, codigos: dict) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "REVENDA": nome,
                "codigo_despesa": cod,
                "descricao_despesa": desc.upper(),
                "CNPJ_REV": cnpj,
                "LICENCA": licenca,
                "GEGENDES_COD": cod,
                "GEGENDES_DESCR": desc.upper(),
            }
            for nome, cnpj, licenca, _c in revendas
            for desc, cod in codigos.items()
        ]
    )


def tabelas(r, revendas, contas_pagar: pl.DataFrame, codigos_despesa: dict, limites: dict) -> dict[str, pl.DataFrame]:
    passados, hoje = _dias()
    todos = [*passados, hoje]
    extratos = _extratos_bancos(r, revendas, todos)
    baixas, extrato_caixa, batida, vales = _caixa(r, revendas, passados)
    manuais = _dados_manuais(r, revendas, passados, hoje)
    pagamentos, pagamentos_retrato = _pagamentos(r, revendas, passados, hoje, contas_pagar)
    credito = {}
    for nome, *_ in revendas:
        credito[nome] = round(limites[nome] * r.uniform(0.08, 0.22), 2)
        credito[f"{nome}|estoque"] = round(limites[nome] * r.uniform(0.35, 0.6), 2)
    hoje_linhas = _composicao(revendas, hoje, extratos, baixas, extrato_caixa, manuais, pagamentos, credito)
    retratos = []
    for dia in passados[-15:]:
        for linha in _composicao(revendas, dia, extratos, baixas, extrato_caixa, manuais, pagamentos, credito):
            retratos.append({**linha, "DATA_SNAPSHOT": dia})
    lista_retrato = pl.concat(
        [
            contas_pagar.filter(pl.col("data_vencimento") >= dia)
            .select(
                "REVENDA",
                "data_vencimento",
                "num_doc",
                "num_doc_normalizado",
                "tipo_doc",
                "cnpj",
                "valor_original",
                "razao_social",
                "descricao_despesa",
                "id_unico",
            )
            .with_columns(pl.lit(dia).alias("data_snapshot"))
            for dia in passados[-15:]
        ]
    )
    return {
        "extratos_bancos": extratos,
        "saldo_banco_999": baixas,
        "extrato_banco": extrato_caixa,
        "batida_diaria": batida,
        "vales_provisorios": vales,
        "dados_manuais": manuais,
        "pagamentos": pagamentos,
        "pagamentos_snapshot": pagamentos_retrato,
        "composicao": pl.DataFrame(hoje_linhas, infer_schema_length=None),
        "composicao_snapshot": pl.DataFrame(retratos, infer_schema_length=None),
        "contas_pagar_snapshot": lista_retrato,
        "verificacao_diaria": _verificacao(r, revendas, passados),
        "justificativas_contas_pagar": _justificativas(r, contas_pagar),
        "cod_despesa": _cod_despesa(revendas, codigos_despesa),
    }
