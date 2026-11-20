"""Frota, comodatos, entregas e devoluções fictícias da Atlântida."""

import json
from datetime import date, timedelta

import polars as pl

from gerador import base as b

INFRACOES = [
    ("Excesso de velocidade até 20%", 130.16, 4),
    ("Excesso de velocidade de 20% a 50%", 195.23, 5),
    ("Estacionar em local proibido", 195.23, 5),
    ("Avançar sinal vermelho", 293.47, 7),
    ("Transitar em faixa exclusiva", 293.47, 7),
    ("Deixar de usar cinto de segurança", 195.23, 5),
    ("Carga excedente", 130.16, 4),
]

EQUIPAMENTOS = [
    ("Visa cooler 1 porta", 3200.0, 0.40),
    ("Visa cooler 2 portas", 5600.0, 0.18),
    ("Freezer horizontal", 2900.0, 0.17),
    ("Chopeira elétrica", 4100.0, 0.08),
    ("Jogo de mesas e cadeiras", 780.0, 0.17),
]

MOTIVOS = [
    ("Estabelecimento fechado", 0.31),
    ("Cliente sem dinheiro", 0.22),
    ("Produto avariado", 0.14),
    ("Pedido em duplicidade", 0.09),
    ("Fora do horário de recebimento", 0.13),
    ("Recusa sem motivo", 0.11),
]


def _motoristas(veiculos: pl.DataFrame) -> pl.DataFrame:
    f = b.faker("motoristas")
    return veiculos.select("placa", "filial").with_columns(
        pl.Series("motorista", [f"{f.first_name()} {f.last_name()}" for _ in range(veiculos.height)])
    )


def _frota(veiculos: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    r = b.rng("frota")
    multas, km, documentos = [], [], []
    for v in veiculos.iter_rows(named=True):
        idade = b.HOJE.year - v["ano"]
        for _ in range(r.choices([0, 1, 2, 3, 5], weights=[30, 30, 20, 12, 8])[0]):
            infracao, valor, pontos = r.choice(INFRACOES)
            data = b.HOJE - timedelta(days=r.randint(3, 540))
            paga = r.random() < (0.85 if (b.HOJE - data).days > 60 else 0.35)
            multas.append(
                {
                    "placa": v["placa"],
                    "data": data,
                    "infracao": infracao,
                    "valor": valor,
                    "pontos": pontos,
                    "situacao": "Paga" if paga else "Em aberto",
                    "vencimento": data + timedelta(days=45),
                }
            )
        ipva_venc = date(b.HOJE.year, (int(v["placa"][-1]) % 9) + 2, 10)
        documentos.append(
            {
                "placa": v["placa"],
                "ipva_vencimento": ipva_venc,
                "ipva_pago": ipva_venc > b.HOJE or r.random() < 0.9,
                "licenciamento_vencimento": date(b.HOJE.year, (int(v["placa"][-1]) % 9) + 3, 28),
                "licenciamento_pago": r.random() < 0.88,
            }
        )
        base_km = {"Moto": 2400, "Utilitário": 3600, "Caminhão 3/4": 4300, "Toco": 5200, "Truck": 6100}[v["tipo"]]
        consumo = {"Moto": 32.0, "Utilitário": 10.5, "Caminhão 3/4": 5.8, "Toco": 4.3, "Truck": 3.4}[v["tipo"]]
        for m in range(12, -1, -1):
            mes = b.meses_atras(b.HOJE, m)
            rodado = base_km * r.uniform(0.75, 1.2) * (1 - 0.01 * idade)
            if m == 0:
                rodado *= b.HOJE.day / 30
            preco = 6.05 + 0.03 * (12 - m) + r.uniform(-0.08, 0.08)
            km.append(
                {
                    "placa": v["placa"],
                    "mes": mes,
                    "km": round(rodado),
                    "litros": round(rodado / (consumo * r.uniform(0.9, 1.08)), 1),
                    "custo_combustivel": round(rodado / consumo * preco, 2),
                    "custo_manutencao": round(r.gammavariate(1.6, 380 + 45 * idade), 2),
                }
            )
    return pl.DataFrame(multas), pl.DataFrame(km), pl.DataFrame(documentos)


def _comodatos(clientes: pl.DataFrame) -> pl.DataFrame:
    r = b.rng("comodatos")
    linhas = []
    num = 7000
    for c in clientes.filter(pl.col("canal").is_in(["Bar", "Restaurante", "Conveniência", "Mercado"])).iter_rows(
        named=True
    ):
        if r.random() > 0.42:
            continue
        for _ in range(r.choices([1, 2, 3], weights=[70, 22, 8])[0]):
            nome, valor, _peso = r.choices(EQUIPAMENTOS, weights=[e[2] for e in EQUIPAMENTOS])[0]
            num += 1
            instalado = b.HOJE - timedelta(days=r.randint(10, 1600))
            vencimento = instalado + timedelta(days=730)
            if not c["ativo"]:
                situacao = r.choice(["Recolha pedida", "Recolhido", "Recolha pedida"])
            elif vencimento < b.HOJE:
                situacao = r.choice(["Contrato vencido", "Contrato vencido", "Renovado"])
            else:
                situacao = "Ativo"
            linhas.append(
                {
                    "patrimonio": f"PT-{num}",
                    "equipamento": nome,
                    "valor": valor,
                    "cod_cliente": c["cod_cliente"],
                    "cliente": c["cliente"],
                    "cidade": c["cidade"],
                    "filial": c["filial"],
                    "instalado_em": instalado,
                    "vencimento_contrato": vencimento if situacao != "Renovado" else vencimento + timedelta(days=730),
                    "situacao": "Ativo" if situacao == "Renovado" else situacao,
                    "ultima_visita": max(instalado, b.HOJE - timedelta(days=int(r.expovariate(1 / 45)))),
                }
            )
    return pl.DataFrame(linhas)


def _entregas(clientes: pl.DataFrame, motoristas: pl.DataFrame) -> pl.DataFrame:
    """Romaneios dos últimos 60 dias úteis: cada caminhão sai com 10 a 22 entregas."""
    r = b.rng("entregas")
    ativos = clientes.filter(pl.col("ativo"))
    linhas = []
    num_romaneio, num_nota = 150000, 880000
    dias = [d for d in b.dias_uteis(b.HOJE - timedelta(days=90), b.HOJE)][-60:]
    caminhoes = motoristas.join(b.veiculos().select("placa", "tipo"), on="placa").filter(pl.col("tipo") != "Moto")
    for filial in b.FILIAIS:
        clientes_filial = ativos.filter(pl.col("filial") == filial.nome).to_dicts()
        frota = caminhoes.filter(pl.col("filial") == filial.nome).to_dicts()
        for dia in dias:
            for v in r.sample(frota, k=max(1, int(len(frota) * r.uniform(0.6, 0.9)))):
                num_romaneio += 1
                for c in r.sample(clientes_filial, k=r.randint(10, 22)):
                    num_nota += 1
                    valor = round(r.gammavariate(2.2, 420) * (2.5 if c["canal"] == "Atacado" else 1), 2)
                    # Hoje ainda tem rota na rua; ontem, algumas notas sem baixa.
                    if dia == b.HOJE:
                        status = r.choices(["Entregue", "Pendente"], weights=[45, 55])[0]
                    elif (b.HOJE - dia).days <= 2:
                        status = r.choices(["Entregue", "Pendente", "Devolvida"], weights=[86, 9, 5])[0]
                    else:
                        status = r.choices(["Entregue", "Devolvida", "Devolvida parcial"], weights=[93, 4.5, 2.5])[0]
                    devolvido = (
                        valor
                        if status == "Devolvida"
                        else round(valor * r.uniform(0.1, 0.5), 2)
                        if status == "Devolvida parcial"
                        else 0.0
                    )
                    motivo = (
                        r.choices([m for m, _ in MOTIVOS], weights=[p for _, p in MOTIVOS])[0] if devolvido else None
                    )
                    linhas.append(
                        {
                            "romaneio": num_romaneio,
                            "data": dia,
                            "filial": filial.nome,
                            "placa": v["placa"],
                            "motorista": v["motorista"],
                            "nota": num_nota,
                            "cod_cliente": c["cod_cliente"],
                            "cliente": c["cliente"],
                            "cidade": c["cidade"],
                            "valor": valor,
                            "status": status,
                            "valor_devolvido": devolvido,
                            "motivo": motivo,
                        }
                    )
    return pl.DataFrame(linhas)


def gerar() -> None:
    print("Logistico")
    veiculos = b.veiculos()
    motoristas = _motoristas(veiculos)
    multas, km, documentos = _frota(veiculos)
    clientes = b.clientes()
    b.gravar(veiculos.join(motoristas.select("placa", "motorista"), on="placa"), "Logistico", "veiculos")
    b.gravar(multas, "Logistico", "multas")
    b.gravar(km, "Logistico", "frota_mes")
    b.gravar(documentos, "Logistico", "documentos_veiculo")
    b.gravar(_comodatos(clientes), "Logistico", "comodatos")
    b.gravar(_entregas(clientes, motoristas), "Logistico", "entregas")
    with open(b.RAIZ / "Logistico" / "data" / "_gerado_em.json", "w", encoding="utf-8") as arq:
        json.dump({"data_base": b.HOJE.isoformat(), "gerado_em": date.today().isoformat()}, arq)
