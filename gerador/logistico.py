"""Caches do Logístico no esquema original: devoluções (por enquanto).

Quatro revendas fictícias (as filiais do base.py), o catálogo do Comercial e os
clientes e vendedores do base.py.
"""

import json
from datetime import date, datetime, timedelta

import polars as pl

from gerador import base as b
from gerador import comercial

PASTA = b.PY / "Logistico" / "data"

# Filial -> (nome da revenda, CNPJ fictício, licença). Os CNPJs batem com Logistico/core/config.py.
REVENDAS = {
    "NAT": ("Natal", "00000000000100", "4101"),
    "FOR": ("Fortaleza", "00000000000280", "4102"),
    "THE": ("Teresina", "00000000000360", "4103"),
    "SLZ": ("São Luís", "00000000000440", "4104"),
}
MESES_DEV = 13  # atual, os três anteriores e mais nove de histórico
PEDIDOS_DIA = 18
MOTIVOS_DEV = [
    ("FECHADO/AUSENTE", 50),
    ("SEM DINHEIRO", 17),
    ("PDV DESISTIU DA COMPRA", 8),
    ("PEDIDO ERRADO", 7),
    ("SEM VASILHAME RETORNAVEL", 6),
    ("PEDIDO EM DUPLICIDADE", 4),
    ("ATRASO NA ROTA", 4),
    ("LOCAL DE ENTREGA NAO LOCALIZAD", 2),
    ("AVARIA NO TRANSPORTE", 2),
]
GRUPOS = ["atual", "ultimo", "penultimo", "antepenultimo", "historico"]
MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _aaaammdd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _proximo_util(d: date, n: int = 1) -> date:
    while n:
        d += timedelta(days=1)
        if d.weekday() < 6:
            n -= 1
    return d


def _motoristas(filial: b.Filial) -> list[tuple[str, str]]:
    f = b.faker(f"motoristas-{filial.codigo}")
    base_cod = 700 + list(REVENDAS).index(filial.codigo) * 40
    return [(str(base_cod + i), f"{f.first_name()} {f.last_name()}".upper()) for i in range(1, 11)]


def _vendas() -> pl.DataFrame:
    """Itens de pedido de quatro revendas, com devolução e romaneio: base das Devoluções e da PDE."""
    catalogo = comercial._catalogo().filter(pl.col("CANAL") != "OUTRO").to_dicts()
    pesos_prod = [p["PESO"] for p in catalogo]
    clientes = b.clientes()
    equipe = b.equipe()
    hoje = b.HOJE
    inicio = b.meses_atras(hoje, MESES_DEV - 1)
    linhas = []
    for filial in b.FILIAIS:
        nome_rev, cnpj, licenca = REVENDAS[filial.codigo]
        r = b.rng(f"devolucoes-{filial.codigo}")
        cli = clientes.filter(pl.col("filial") == filial.nome).to_dicts()
        pesos_cli = [c["porte"] for c in cli]
        # Uns poucos clientes devolvem bem mais que a média.
        risco = {c["cod_cliente"]: r.choice([0.01, 0.02, 0.03, 0.03, 0.05, 0.12]) for c in cli}
        comodato_cli = {c["cod_cliente"]: r.random() < 0.17 for c in cli}
        tpcobra = {c["cod_cliente"]: r.choices(["Prazo  ", "A Vista", "OUTRO  "], weights=[49, 49, 2])[0] for c in cli}
        nomes_ven = dict(equipe.select("cod_vendedor", "vendedor").iter_rows())
        motoristas = _motoristas(filial)
        nf = 100000 + list(REVENDAS).index(filial.codigo) * 200000
        nf_dev = nf + 150000
        for dia in b.dias_uteis(inicio, hoje):
            # Romaneios abertos: só os dos últimos dias úteis ainda não fecharam.
            dias_ate_hoje = len(b.dias_uteis(dia, hoje)) - 1
            rotas = [
                (f"{_aaaammdd(dia)}{n:03d}", motoristas[(n + dia.toordinal()) % len(motoristas)]) for n in range(1, 7)
            ]
            for seq in range(1, int(PEDIDOS_DIA * r.uniform(0.75, 1.25)) + 1):
                c = r.choices(cli, weights=pesos_cli)[0]
                romaneio, (mot, nome_mot) = r.choice(rotas)
                cod_ped = int(f"{_aaaammdd(dia)}{seq:04d}")
                entrega = _proximo_util(dia)
                aberto = dias_ate_hoje < 2 or (dias_ate_hoje < 6 and r.random() < 0.08)
                baixa = None if aberto else _aaaammdd(_proximo_util(entrega, r.choice([1, 1, 2, 3])))
                nf += 1
                devolve = r.random() < risco[c["cod_cliente"]]
                devolve_tudo = devolve and r.random() < 0.7
                motivo = (
                    r.choices(MOTIVOS_DEV, weights=[m[1] for m in MOTIVOS_DEV])[0][0].ljust(30) if devolve else None
                )
                itens = list(
                    dict.fromkeys(
                        r.choices(range(len(catalogo)), weights=pesos_prod, k=r.choice([1, 2, 2, 3, 3, 4, 5]))
                    )
                )
                parcial = r.randrange(len(itens))
                for i, idx in enumerate(itens):
                    p = catalogo[idx]
                    qtd = max(1, round(r.gammavariate(1.6, 2.2) * min(c["porte"], 4)))
                    valor = round(qtd * p["PRECO"] * r.uniform(0.94, 1.0), 2)
                    dev_item = devolve and (devolve_tudo or i == parcial)
                    dev_cx = (
                        qtd
                        if dev_item and (devolve_tudo or r.random() < 0.6)
                        else (max(1, qtd // 2) if dev_item else 0)
                    )
                    linhas.append(
                        {
                            "COD_PED": float(cod_ped),
                            "CODR": float(p["CODRED"]),
                            "COD_VEN": str(c["cod_vendedor"]),
                            "MOT": mot,
                            "CLI": c["cod_cliente"],
                            "VDCADDEV_DESCR": motivo if dev_item else None,
                            "TPCOBRA": tpcobra[c["cod_cliente"]],
                            "NF_VENDA": nf,
                            "ROMANEIO": float(romaneio),
                            "QTD": qtd,
                            "DEVOLUCAO_CX": dev_cx,
                            "QTD_UN": qtd * p["UNIDADE"],
                            "DEVOLUCAO_UN": dev_cx * p["UNIDADE"],
                            "VALOR VENDA": valor,
                            "VALOR DEVOLUCAO": round(valor * dev_cx / qtd, 2),
                            "MES": dia.strftime("%Y%m"),
                            "DATA_VENDA": _aaaammdd(dia),
                            "DATA_DEV": int(_aaaammdd(entrega)) if dev_item else 0,
                            "NF_DEV": nf_dev + nf % 100000 if dev_item else 0,
                            "CNPJ_REV": cnpj,
                            "REVENDA": nome_rev.upper(),
                            "LICENCA": licenca,
                            "DTA_ENTREGA": None if r.random() < 0.04 else _aaaammdd(entrega),
                            "Comodato": int(comodato_cli[c["cod_cliente"]] and r.random() < 0.3),
                            "CHAVE_VDI": f"{cod_ped}{cnpj}",
                            "FANTASIA": c["cliente"],
                            "CIDADE": b.sem_acento(c["cidade"]).upper()[:15],
                            "UF": filial.uf,
                            "PRODUTO": p["PRODUTO"],
                            "PRODUTO_GENERICO": p["PRODUTO"].rsplit(" CX", 1)[0],
                            "NOME_VEN": nomes_ven[c["cod_vendedor"]].split(" - ", 1)[1].upper(),
                            "NOME_MOT": nome_mot,
                            "Romaneio aberto": "Sim" if aberto else "Não",
                            "DATA_BAIXA_ROM": baixa,
                            "Comodato cliente": "Sim" if comodato_cli[c["cod_cliente"]] else "Não",
                            "GRUPO_REV": nome_rev,
                        }
                    )
    df = pl.DataFrame(linhas, infer_schema_length=None)
    mes_hoje = hoje.year * 12 + hoje.month
    df = df.with_columns(
        (
            pl.lit(mes_hoje)
            - pl.col("MES").str.slice(0, 4).cast(pl.Int32) * 12
            - pl.col("MES").str.slice(4, 2).cast(pl.Int32)
        )
        .cast(pl.Int32)
        .alias("_meses_atras"),
        pl.col("Comodato").cast(pl.Int32),
    ).with_columns(
        pl.when(pl.col("_meses_atras") == 0)
        .then(pl.lit("Mês Atual"))
        .otherwise(
            pl.col("MES").str.slice(4, 2).cast(pl.Int32).replace_strict({i + 1: m for i, m in enumerate(MESES_PT)})
            + pl.lit("/")
            + pl.col("MES").str.slice(0, 4)
        )
        .alias("MES_ATUAL")
    )
    # Taxa de retorno do cliente nos três últimos meses (atual incluído), como no pipeline original.
    taxa = (
        df.filter(pl.col("_meses_atras").is_between(0, 2))
        .group_by("CLI", "CNPJ_REV")
        .agg(
            pl.col("CHAVE_VDI").n_unique().alias("vdi_total"),
            pl.col("CHAVE_VDI").filter(pl.col("VALOR DEVOLUCAO") > 0).n_unique().alias("vdi_dev"),
        )
        .with_columns((pl.col("vdi_dev") / pl.col("vdi_total")).fill_nan(0.0).alias("taxa_media_dev"))
    )
    df = df.join(taxa, on=["CLI", "CNPJ_REV"], how="left").with_columns(
        pl.col("vdi_total").fill_null(0), pl.col("vdi_dev").fill_null(0), pl.col("taxa_media_dev").fill_null(0.0)
    )
    return df


def _devolucoes(df: pl.DataFrame) -> dict[str, pl.DataFrame]:
    saida = {}
    for _, (_, cnpj, _) in REVENDAS.items():
        da_rev = df.filter(pl.col("CNPJ_REV") == cnpj)
        for n, grupo in enumerate(GRUPOS):
            filtro = pl.col("_meses_atras") == n if grupo != "historico" else pl.col("_meses_atras") >= 4
            saida[f"tb_vend_dev_{cnpj}_{grupo}"] = da_rev.filter(filtro)
    saida["tb_empresas"] = pl.DataFrame(
        {"EMPRESA": [v[0] for v in REVENDAS.values()], "CNPJ_EMP": [v[1] for v in REVENDAS.values()]}
    )
    return saida


DIAS_PDE = 45


def _pde(vendas: pl.DataFrame) -> pl.DataFrame:
    """Planilha de entregas: uma linha por romaneio, somando as vendas dele."""
    r = b.rng("pde")
    f = b.faker("pde-ajudantes")
    corte = b.HOJE - timedelta(days=DIAS_PDE)
    veiculos = b.veiculos().filter(~pl.col("tipo").is_in(["Moto", "Utilitário"]))
    rom = (
        vendas.filter(pl.col("DATA_VENDA") >= _aaaammdd(corte))
        .with_columns(pl.col("ROMANEIO").cast(pl.Int64).cast(pl.String))
        .group_by("CNPJ_REV", "GRUPO_REV", "ROMANEIO", "DATA_VENDA", "NOME_MOT")
        .agg(
            pl.col("CLI").n_unique().alias("QTD_ENT"),
            pl.col("NF_VENDA").n_unique().alias("QTD_NF"),
            pl.col("VALOR VENDA").sum().round(0).cast(pl.Int64).alias("FAT_SAIDA"),
            pl.col("CHAVE_VDI").filter(pl.col("VALOR DEVOLUCAO") > 0).n_unique().cast(pl.Int64).alias("QTD_DEV"),
            pl.col("VALOR DEVOLUCAO").sum().round(0).cast(pl.Int64).alias("FAT_DEV"),
            pl.col("CIDADE").first().alias("CIDADE"),
        )
        .sort("CNPJ_REV", "ROMANEIO")
    )
    filiais = {v[1]: k for k, v in REVENDAS.items()}
    nomes_filial = {fl.codigo: fl.nome for fl in b.FILIAIS}
    placas: dict[tuple[str, str], dict] = {}
    hodometro: dict[str, int] = {}
    ajudantes = [f"{f.first_name()} {f.last_name()}".upper() for _ in range(40)]
    linhas = []
    for i, x in enumerate(rom.iter_rows(named=True), start=1):
        cod = filiais[x["CNPJ_REV"]]
        frota = veiculos.filter(pl.col("filial") == nomes_filial[cod]).to_dicts()
        v = placas.setdefault((x["CNPJ_REV"], x["NOME_MOT"]), frota[len(placas) % len(frota)])
        saida = datetime.strptime(x["DATA_VENDA"], "%Y%m%d").date()
        saida = _proximo_util(saida)
        if saida > b.HOJE:
            continue
        dias_rota = 2 if r.random() < 0.08 else 1
        preenchido = (b.HOJE - saida).days > 3 and r.random() < 0.75
        km_ini = hodometro.get(v["placa"], r.randint(40000, 260000))
        km_fim = km_ini + r.randint(35, 120) * dias_rota + r.randint(0, 60)
        if preenchido:
            hodometro[v["placa"]] = km_fim
        linhas.append(
            {
                "EMPRESA": x["GRUPO_REV"],
                "ID": i,
                "CNPJ_EMP": x["CNPJ_REV"],
                "ROMANEIO": x["ROMANEIO"],
                "DT_SAIDA": int(_aaaammdd(saida)),
                "DIAS_ROTA": dias_rota,
                "HR_SAIDA": f"0{r.randint(6, 8)}:{r.choice(['00', '10', '15', '20', '30', '45'])}"
                if preenchido
                else None,
                "PLACA": v["placa"],
                "MOTORISTA": x["NOME_MOT"],
                "AJUDANTE_1": r.choice(ajudantes) if preenchido else None,
                "AJUDANTE_2": r.choice(ajudantes) if preenchido and r.random() < 0.3 else None,
                "ROTA": f"ROTA {x['ROMANEIO'][-2:]} - {x['CIDADE']}",
                "OBS": r.choice(["CLIENTE FECHADO NO 1o HORARIO", "CHUVA NA ROTA", "DESCARGA DEMORADA", "TRANSITO"])
                if preenchido and r.random() < 0.1
                else None,
                "PESO_V": v["capacidade_kg"],
                "PESO_R": int(v["capacidade_kg"] * r.uniform(0.55, 0.98)),
                "QTD_ENT": x["QTD_ENT"],
                "QTD_NF": x["QTD_NF"],
                "FAT_SAIDA": x["FAT_SAIDA"],
                "QTD_DEV": x["QTD_DEV"],
                "FAT_DEV": x["FAT_DEV"],
                "DT_FIM": int(_aaaammdd(saida + timedelta(days=dias_rota - 1))) if preenchido else 0,
                "HR_FIM": f"{r.randint(15, 19)}:{r.randint(0, 59):02d}" if preenchido else "00:00",
                "KM_INI": km_ini if preenchido else 0,
                "KM_FIM": km_fim if preenchido else 0,
            }
        )
    return pl.DataFrame(linhas, infer_schema_length=None)


def _gravar_pasta(pasta, tabelas: dict[str, pl.DataFrame], atualizadas: list[str]) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    for antigo in pasta.glob("*.parquet"):
        antigo.unlink()
    for nome, df in tabelas.items():
        df.write_parquet(pasta / f"{nome}.parquet", compression="zstd")
    total = sum(df.height for df in tabelas.values())
    print(f"  {pasta.relative_to(PASTA)}: {len(tabelas)} arquivos, {total:,} linhas".replace(",", "."))
    momento = datetime.combine(b.HOJE, datetime.min.time()).replace(hour=4, minute=37).isoformat(timespec="seconds")
    (pasta / "_atualizacoes.json").write_text(
        json.dumps({n: momento for n in atualizadas}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def gerar() -> None:
    print("Logístico")
    vendas = _vendas()
    dev = _devolucoes(vendas)
    _gravar_pasta(PASTA / "bd_shiny_bruto" / "devolucoes", dev, [n for n in dev if n.endswith("_atual")])
    _gravar_pasta(PASTA / "bd_pde", {"tb_pde": _pde(vendas)}, ["tb_pde"])
    frota = _frotas()
    _gravar_pasta(PASTA / "bd_senatran", frota, list(frota))


# ---------------------------------------------------------------- Frotas
EXECUCOES = 26  # a consulta dos veículos roda a cada duas semanas: um ano de retratos
_TIPO_FROTA = {
    "Caminhão 3/4": ("CAMINHAO", "Diesel"),
    "Toco": ("CAMINHAO", "Diesel"),
    "Truck": ("CAMINHAO", "Diesel"),
    "Utilitário": ("UTILITARIO", "Flex"),
    "Moto": ("MOTOCICLETA", "Gasolina"),
    "Carro": ("AUTOMOVEL", "Flex"),
    "Cavalo": ("CAMINHAO TRATOR", "Diesel"),
    "Reboque": ("SEMI-REBOQUE", ""),
}
_FIPE = {
    "CAMINHAO TRATOR": (520000, 760000),
    "SEMI-REBOQUE": (110000, 190000),
    "CAMINHAO": (180000, 420000),
    "UTILITARIO": (70000, 110000),
    "MOTOCICLETA": (14000, 21000),
    "AUTOMOVEL": (60000, 95000),
}
_CARROS = [("Carro", "VW Polo Track", 0), ("Carro", "Fiat Argo Drive", 0), ("Carro", "Chevrolet Onix LT", 0)]
_BANCOS = ["BANCO ALFA ARRENDAMENTO MERCANTIL S.A.", "BANCO BETA LEASING S.A."]
_TRIBUNAIS = [
    ("TRABALHO", "TRIBUNAL REGIONAL DO TRABALHO 21A REGIAO", "2VT NATAL"),
    ("FEDERAL", "TRIBUNAL REGIONAL FEDERAL DA 5A REGIAO", "SSJ-NAT-RN"),
    ("ESTADUAL", "TRIBUNAL DE JUSTICA DO CEARA", "5VCC FORTALEZA"),
]
_INFRACOES = [
    ("7455", "TRANSITAR EM VELOCIDADE SUPERIOR A MAXIMA PERMITIDA EM ATE 20%", 130.16),
    ("5746", "TRANSITAR EM LOCAL/HORARIO NAO PERMITIDO PELA REGULAMENTACAO", 130.16),
    ("6637", "CONDUZIR O VEICULO COM EQUIPAMENTO OBRIGATORIO INEFICIENTE/INOPERANTE", 195.23),
    ("5185", "ESTACIONAR EM LOCAL/HORARIO PROIBIDO ESPECIFICAMENTE PELA SINALIZACAO", 195.23),
    ("6050", "DEIXAR DE INDICAR COM ANTECEDENCIA MEDIANTE GESTO OU LUZ A MANOBRA", 130.16),
    ("7366", "TRANSITAR EM VELOCIDADE SUPERIOR A MAXIMA PERMITIDA EM MAIS DE 20% ATE 50%", 195.23),
]
_MESES_EXTENSO = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]


def _renavam(r) -> str:
    return "".join(str(r.randint(0, 9)) for _ in range(11))


def _frotas() -> dict[str, pl.DataFrame]:
    r = b.rng("frotas")
    f = b.faker("frotas")
    hoje = b.HOJE
    ultima = hoje - timedelta(days=(hoje.weekday() + 1) % 7 or 7)  # domingo passado
    execucoes = [ultima - timedelta(days=14 * n) for n in range(EXECUCOES - 1, -1, -1)]
    filial_por_nome = {fl.nome: fl for fl in b.FILIAIS}
    base_veic = b.veiculos().to_dicts()
    for fl in b.FILIAIS:
        for _ in range(r.randint(5, 9)):
            tipo, modelo, carga = r.choice(_CARROS)
            base_veic.append(
                {
                    "placa": b.placa(r),
                    "tipo": tipo,
                    "modelo": modelo,
                    "ano": r.randint(2018, hoje.year),
                    "capacidade_kg": carga,
                    "filial": fl.nome,
                    "uf": fl.uf,
                }
            )
        # Cavalo mecânico e semirreboque: a puxada da fábrica.
        for _ in range(r.randint(2, 3)):
            ano = r.randint(2016, hoje.year)
            base_veic.append(
                {
                    "placa": b.placa(r),
                    "tipo": "Cavalo",
                    "modelo": r.choice(["Volvo FH 460", "Scania R450"]),
                    "ano": ano,
                    "capacidade_kg": 0,
                    "filial": fl.nome,
                    "uf": fl.uf,
                }
            )
            base_veic.append(
                {
                    "placa": b.placa(r),
                    "tipo": "Reboque",
                    "modelo": "Randon SR BA",
                    "ano": ano,
                    "capacidade_kg": 30000,
                    "filial": fl.nome,
                    "uf": fl.uf,
                }
            )
    veiculos = []
    for v in base_veic:
        fl = filial_por_nome[v["filial"]]
        nome_rev, cnpj, _ = REVENDAS[fl.codigo]
        tipo, combustivel = _TIPO_FROTA[v["tipo"]]
        entra = execucoes[0] if r.random() > 0.16 else r.choice(execucoes[1:])
        sai = r.choice(execucoes[execucoes.index(entra) + 2 :] or [None]) if r.random() < 0.12 else None
        financiado = r.random() < 0.2
        renajud = r.random() < 0.05
        trib = r.choice(_TRIBUNAIS)
        fipe = round(r.uniform(*_FIPE[tipo]) * (1 - 0.045 * (hoje.year - v["ano"])), 0)
        veiculos.append(
            {
                **v,
                "fl": fl,
                "nome_rev": nome_rev,
                "cnpj": cnpj,
                "TIPO": tipo,
                "COMBUSTIVEL": combustivel,
                "entra": entra,
                "sai": sai,
                "RENAVAM": _renavam(r),
                "financiado": financiado,
                "PROPRIETARIO": r.choice(_BANCOS) if financiado else "",
                "renajud": renajud,
                "trib": trib,
                "PROCESSO": "".join(str(r.randint(0, 9)) for _ in range(20)) if renajud else "",
                "TIPO_RESTRICAO": r.choice(["CIRCULACAO", "TRANSFERENCIA"]) if renajud else "",
                "rest_adm": r.random() < 0.04,
                "COD_FIPE": f"{r.randint(100000, 899999)}-{r.randint(0, 9)}",
                "fipe": fipe,
                "parado": r.random() < 0.07,
                "cartao": r.random() < 0.85,
                "multas": [],
            }
        )
    # Multas: cada veículo junta de zero a algumas no ano.
    renainf = []
    for v in veiculos:
        for _ in range(int(r.paretovariate(1.6)) - 1 if v["TIPO"] != "MOTOCICLETA" else r.choice([0, 0, 1])):
            cod, desc, valor = r.choice(_INFRACOES)
            quando = datetime.combine(hoje - timedelta(days=r.randint(5, 360)), datetime.min.time()) + timedelta(
                minutes=r.randint(360, 1320)
            )
            venc = (quando + timedelta(days=r.randint(40, 110))).date()
            situacao = (
                "PAGAS"
                if r.random() < 0.55
                else "SUSPENSAS_E_CANCELADAS"
                if r.random() < 0.05
                else "NAO_PAGAS_A_VENCER"
                if venc > hoje
                else "NAO_PAGAS_VENCIDAS"
            )
            orgao = r.choice(["214750", "106100", "225590", "210770"])
            m = {
                "PLACA": v["placa"],
                "AUTO_INFRACAO": f"{r.choice('ABCDEFGH')}{r.randint(10000000, 99999999)}",
                "ORGAO": orgao,
                "INFRACAO": f"{cod} - {desc}",
                "RENAINF": f"{orgao}V0{r.randint(100000000, 999999999)}{cod}",
                "LOCAL": f"{f.street_name().upper()} - {v['fl'].uf}",
                "DATA_HORA_INF": quando.strftime("%d/%m/%Y %H:%M"),
                "VALOR": valor,
                "VENCIMENTO": venc,
                "SITUACAO": situacao,
                "DT_IDENT_CONDUTOR": (quando + timedelta(days=r.randint(3, 25))).date() if r.random() < 0.4 else None,
            }
            v["multas"].append(m)
            renainf.append(m)
    # Retratos: um por veículo ativo em cada execução.
    retratos = []
    for d in execucoes:
        exec_txt = _aaaammdd(d)
        mes_ref = f"{_MESES_EXTENSO[d.month - 1]} de {d.year}"
        for v in veiculos:
            if d < v["entra"] or (v["sai"] and d >= v["sai"]):
                continue
            multas_abertas = sum(
                m["VALOR"]
                for m in v["multas"]
                if m["SITUACAO"].startswith("NAO_PAGAS")
                and m["DATA_HORA_INF"][-10:]
                and datetime.strptime(m["DATA_HORA_INF"], "%d/%m/%Y %H:%M").date() <= d
            )
            ipva = (
                round(v["fipe"] * 0.01, 2) if d.month <= 3 and v["TIPO"] != "MOTOCICLETA" and r.random() < 0.5 else 0.0
            )
            licenc = round(r.uniform(150, 260), 2) if d.month in (9, 10) and r.random() < 0.4 else 0.0
            ult_rom = d - timedelta(days=r.randint(95, 200) if v["parado"] else r.randint(0, 6))
            consultado = r.random() < 0.9
            cnpj_tl = v["cnpj"] if v["cartao"] else None
            retratos.append(
                {
                    "EMPRESA": v["nome_rev"],
                    "UF_Emp": v["fl"].uf,
                    "CNPJ_EMP": v["cnpj"],
                    "UF": v["uf"],
                    "CNPJ_PROP": "",
                    "PLACA": v["placa"],
                    "TIPO": v["TIPO"],
                    "MODELO": v["modelo"].upper()[:15],
                    "ANO_FAB": str(v["ano"] - (1 if r.random() < 0.3 else 0)),
                    "ANO": str(v["ano"]),
                    "CARROCERIA": r.choice(["FECHADA", "ABERTA"])
                    if v["TIPO"] in ("CAMINHAO", "SEMI-REBOQUE")
                    else "NÃO APLICAVEL",
                    "CHASSI": "",
                    "RENAVAM": v["RENAVAM"],
                    "GRAVAME": "Sim" if v["financiado"] else "Não",
                    "GRAVAME_PENDENTE": "Não",
                    "RESTRICAO_ADM": "Sim" if v["rest_adm"] else "Não",
                    "RENAJUD": "Sim" if v["renajud"] else "Não",
                    "PROCESSO": v["PROCESSO"],
                    "TIPO_RESTRICAO": v["TIPO_RESTRICAO"],
                    "TRIBUNAL": v["trib"][1] if v["renajud"] else "",
                    "ORGAO": v["trib"][2] if v["renajud"] else "",
                    "TOTAL_PROCESSOS": r.randint(1, 4) if v["renajud"] else 0,
                    "COD_FIPE": v["COD_FIPE"],
                    "INFO_UF_FIPE": v["fl"].uf,
                    "DEBITO_DETRAN": round(multas_abertas + ipva + licenc, 2) if consultado else None,
                    "LICENCIAMENTO": licenc if consultado else None,
                    "MULTA": round(multas_abertas, 2) if consultado else None,
                    "IPVA": ipva if consultado else None,
                    "IPVA_AL_ANT": None,
                    "CUSTO_API": 0.5 if consultado else None,
                    "DTA_EXEC": exec_txt,
                    "TABELA_FIPE": v["fipe"],
                    "COMBUSTIVEL": v["COMBUSTIVEL"],
                    "MESREFERENCIA": mes_ref,
                    "CNPJ_EMP_TL": cnpj_tl,
                    "ULT_ROMANEIO_TL": int(_aaaammdd(ult_rom)) if cnpj_tl else 0,
                    "EMPRESA_TL": v["nome_rev"] if cnpj_tl else None,
                    "CNPJ_EMP_CONTROL": v["cnpj"],
                    "ULT_ROMANEIO_CONTROL": int(_aaaammdd(ult_rom)),
                    "EMPRESA_CONTROL": v["nome_rev"],
                    "ULT_ROMANEIO_FROTA": int(_aaaammdd(ult_rom)),
                    "NOME_EMPRESA_FINAL": None,
                    "ANEXO": None,
                    "UNIDADE": v["nome_rev"],
                    "PROPRIETARIO": v["PROPRIETARIO"],
                    "Anexo_transf": "",
                    "ULT_ROM": "Maior ou igual a 3 meses" if v["parado"] else None,
                    "TRANSFERENCIA": "Não",
                    "MES_FIPE": mes_ref,
                }
            )
    frota = pl.DataFrame(retratos, infer_schema_length=None)
    por_placa = {x["PLACA"]: x for x in frota.sort("DTA_EXEC").iter_rows(named=True)}
    primeiro = {x["PLACA"]: x for x in frota.sort("DTA_EXEC", descending=True).iter_rows(named=True)}
    entrada = pl.DataFrame(
        [
            {
                **primeiro[v["placa"]],
                "FIPE_PRECO": v["fipe"],
                "FIPE_MES": primeiro[v["placa"]]["MES_FIPE"],
                "DTA_ENTR": _aaaammdd(v["entra"]),
            }
            for v in veiculos
            if v["placa"] in primeiro
        ],
        infer_schema_length=None,
    )
    saida = pl.DataFrame(
        [
            {
                **por_placa[v["placa"]],
                "FIPE_PRECO": v["fipe"],
                "FIPE_MES": por_placa[v["placa"]]["MES_FIPE"],
                "DTA_SAID": _aaaammdd(v["sai"]),
            }
            for v in veiculos
            if v["sai"] and v["placa"] in por_placa
        ],
        infer_schema_length=None,
    )
    ultima_txt = _aaaammdd(execucoes[-1])
    renainf_df = pl.DataFrame(renainf, infer_schema_length=None).with_columns(
        pl.lit(ultima_txt).alias("DTA_EXEC"),
        pl.when(pl.col("SITUACAO") == "PAGAS")
        .then(pl.lit("Sim"))
        .when(pl.col("SITUACAO") == "SUSPENSAS_E_CANCELADAS")
        .then(pl.lit("Susp/Canc"))
        .otherwise(pl.lit("Não"))
        .alias("PAGA"),
    )
    renajud = pl.DataFrame(
        [
            {
                "PLACA": v["placa"],
                "TIPO_RESTRICAO": v["TIPO_RESTRICAO"],
                "TRIBUNAL": v["trib"][1],
                "ORGAO": v["trib"][2],
                "PROCESSO": v["PROCESSO"],
                "DTA_EXEC": _aaaammdd(d),
            }
            for v in veiculos
            if v["renajud"]
            for d in execucoes[-6:]
        ],
        schema={
            "PLACA": pl.Utf8,
            "TIPO_RESTRICAO": pl.Utf8,
            "TRIBUNAL": pl.Utf8,
            "ORGAO": pl.Utf8,
            "PROCESSO": pl.Utf8,
            "DTA_EXEC": pl.Utf8,
        },
    )
    combustivel, rastreio = _abastecimentos(veiculos, r, f)
    return {
        "geral_frota": frota,
        "geral_frota_entrada": entrada,
        "geral_frota_saida": saida,
        "geral_renainf": renainf_df,
        "geral_renajud": renajud,
        "geral_combustivel": combustivel,
        "geral_rastreio": rastreio,
    }


def _abastecimentos(veiculos: list[dict], r, f) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Abastecimentos com o cartão combustível nos últimos seis meses, e o último de cada veículo
    nos dois últimos dias, com a posição do posto (o mapa da aba Combustível)."""
    hoje = b.HOJE
    cidades = {fl.codigo: b.cidades_da_filial(fl, vizinhas=12, interior=0).to_dicts() for fl in b.FILIAIS}
    linhas, ultimos = [], []
    transacao = 1000020000
    for v in veiculos:
        if not v["cartao"] or v["sai"] or v["TIPO"] == "SEMI-REBOQUE":
            continue
        tipo = v["TIPO"]
        tipo = "CAMINHAO" if tipo == "CAMINHAO TRATOR" else tipo
        servico = {"CAMINHAO": "DIESEL S-10 COMUM", "MOTOCICLETA": "GASOLINA COMUM"}.get(
            tipo, r.choice(["GASOLINA COMUM", "ETANOL"])
        )
        preco = {"DIESEL S-10 COMUM": 6.29, "GASOLINA COMUM": 6.19, "ETANOL": 4.49}[servico]
        consumo = {"CAMINHAO": 3.4, "MOTOCICLETA": 32.0}.get(tipo, 11.5)
        tanque = {"CAMINHAO": (120, 260), "MOTOCICLETA": (6, 11)}.get(tipo, (25, 42))
        motorista = f"{f.first_name()} {f.last_name()}".upper()
        km = r.randint(30000, 250000)
        quando = datetime.combine(hoje - timedelta(days=182), datetime.min.time())
        centro = (
            "PUXADA" if tipo == "CAMINHAO" and r.random() < 0.3 else "ENTREGA" if tipo == "CAMINHAO" else "COMERCIAL"
        )
        while True:
            quando += timedelta(days=r.uniform(1.5, 4.5) if tipo != "CAMINHAO" else r.uniform(1.0, 3.0))
            if quando.date() > hoje or v["parado"] and quando.date() > hoje - timedelta(days=100):
                break
            litros = round(r.uniform(*tanque), 2)
            rodados = round(litros * consumo * r.uniform(0.85, 1.12), 2)
            km += int(rodados)
            cidade = r.choice(cidades[v["fl"].codigo][:6] if r.random() < 0.8 else cidades[v["fl"].codigo])
            valor_litro = round(preco * r.uniform(0.97, 1.05), 2)
            transacao += r.randint(1, 900)
            hora = quando.replace(hour=r.randint(5, 20), minute=r.randint(0, 59), second=r.randint(0, 59))
            linha = {
                "EMPRESA": v["nome_rev"],
                "UF_Emp": v["fl"].uf,
                "CNPJ_EMP": v["cnpj"],
                "PLACA": v["placa"],
                "MODELO": f"{v['modelo'].upper()[:12]} - {v['ano']}",
                "DATA_HORA": hora,
                "CARTAO": f"{r.randint(1000, 9999)}",
                "RESPONSAVEL": "FROTA " + v["nome_rev"].upper(),
                "MOTORISTA": motorista,
                "MATRICULA": str(r.randint(1000, 9999)),
                "ESTABELECIMENTO": f"POSTO {f.last_name().upper()}",
                "CIDADE": f"{cidade['nome'].upper()} - {v['fl'].uf}",
                "QUILOMETRAGEM": km,
                "SERVICO": servico,
                "VALOR": round(litros * valor_litro, 2),
                "KM_RODADOS": rodados,
                "LITROS": litros,
                "KM_LITRO": round(rodados / litros, 2),
                "VALOR_LITRO": valor_litro,
                "TRANSACAO": str(transacao),
                "CENTRO_CUSTO": centro,
            }
            linhas.append(linha)
            ultimo = (linha, cidade)
        if linhas and linhas[-1]["PLACA"] == v["placa"] and (hoje - ultimo[0]["DATA_HORA"].date()).days <= 2:
            linha, cidade = ultimo
            ultimos.append(
                {
                    "PLACA": v["placa"],
                    "DATA_HORA": linha["DATA_HORA"].isoformat(timespec="seconds"),
                    "MOTORISTA": linha["MOTORISTA"],
                    "TIPO": v["TIPO"],
                    "VALOR": f"{linha['VALOR']:.2f}",
                    "PLATAFORMA": "CARTÃO COMBUSTÍVEL",
                    "POSTO": linha["ESTABELECIMENTO"],
                    "CIDADE": linha["CIDADE"],
                    "ENDERECO": f"{f.street_name().upper()}, {r.randint(10, 3000)}",
                    "LATITUDE": cidade["latitude"] + r.uniform(-0.02, 0.02),
                    "LONGITUDE": cidade["longitude"] + r.uniform(-0.02, 0.02),
                    "CNPJ_EMP": v["cnpj"],
                    "EMPRESA": v["nome_rev"],
                }
            )
    return pl.DataFrame(linhas, infer_schema_length=None), pl.DataFrame(ultimos, infer_schema_length=None)
