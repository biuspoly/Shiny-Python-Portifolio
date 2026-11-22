"""Entidades fictícias compartilhadas por todos os apps.

Tudo sai de uma semente fixa: rodar de novo gera as mesmas pessoas, clientes e
produtos. Só as datas andam junto com o dia em que o gerador roda, para os
painéis sempre mostrarem o mês corrente.
"""

import hashlib
import os
import random
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import polars as pl
from faker import Faker

from gerador.publicos import municipios

RAIZ = Path(__file__).resolve().parent.parent
SEMENTE = 2026

# DATA_BASE=2026-11-20 no ambiente fixa o "hoje" (útil para comparar duas gerações).
HOJE = date.fromisoformat(os.environ["DATA_BASE"]) if os.getenv("DATA_BASE") else date.today()
EMPRESA = "Distribuidora fictícia"


def rng(nome: str) -> random.Random:
    """Um gerador por assunto: mudar um assunto não embaralha os outros."""
    return random.Random(f"{SEMENTE}-{nome}")


# Palavras que o Faker não deve devolver (nome, sobrenome, bairro, rua) e municípios que ficam fora dos
# territórios: guardados como hash, para não publicar quais são.
NOMES_EVITADOS = {"6f790e9c9e0aea51", "475e0686eb742c10"}
CIDADES_EVITADAS = {"f9cdfe68a7241fd4", "7c5706bc0bf52da5", "2ad4e6c2a578f844", "89381bec1ce4ba3b", "86faff74a84c3834"}


def _hash(texto: str) -> str:
    return hashlib.sha256(sem_acento(texto).upper().strip().encode()).hexdigest()[:16]


def faker(nome: str) -> Faker:
    f = Faker("pt_BR")
    f.seed_instance(f"{SEMENTE}-{nome}")

    def sem_evitados(gerar):
        def gerado() -> str:
            while True:
                escolhido = gerar()
                if not NOMES_EVITADOS & {_hash(p) for p in escolhido.split()}:
                    return escolhido

        return gerado

    for campo in ("first_name", "last_name", "bairro", "street_name"):
        setattr(f, campo, sem_evitados(getattr(f, campo)))
    return f


def sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def login_de(nome: str) -> str:
    partes = sem_acento(nome).lower().split()
    return f"{partes[0]}.{partes[-1]}"


def gravar(df: pl.DataFrame, app: str, nome: str) -> None:
    pasta = RAIZ / app / "data"
    pasta.mkdir(parents=True, exist_ok=True)
    df.write_parquet(pasta / f"{nome}.parquet", compression="zstd")
    print(f"  {app}/data/{nome}.parquet: {df.height:,} linhas".replace(",", "."))


@dataclass(frozen=True)
class Filial:
    codigo: str
    nome: str
    uf: str
    cod_ibge_sede: int


FILIAIS = [
    Filial("NAT", "Natal", "RN", 2408102),
    Filial("FOR", "Fortaleza", "CE", 2304400),
    Filial("THE", "Teresina", "PI", 2211001),
    Filial("SLZ", "São Luís", "MA", 2111300),
]

# marca, categoria, cor (hex), embalagens (nome, litros por caixa, preço da caixa)
MARCAS = [
    ("MARÉ", "Pilsen", "#0E7490", [("LATA 350ML", 4.2, 46.0), ("600ML", 14.4, 98.0), ("LN 330ML", 7.92, 72.0)]),
    ("JANGADA", "Pilsen", "#D97706", [("LATA 269ML", 4.304, 39.0), ("600ML", 14.4, 89.0), ("1L", 12.0, 79.0)]),
    ("CORAL", "Puro Malte", "#DC2626", [("LATA 350ML", 4.2, 54.0), ("LN 330ML", 7.92, 84.0)]),
    ("IPÊ", "Puro Malte", "#CA8A04", [("LATA 350ML", 4.2, 52.0), ("600ML", 14.4, 109.0)]),
    ("FAROL", "Premium", "#166534", [("LN 355ML", 8.52, 119.0), ("LATA 350ML", 4.2, 69.0)]),
    ("SERENA", "Premium", "#7C3AED", [("LN 330ML", 7.92, 126.0)]),
    ("BRISA ZERO", "Zero Álcool", "#64748B", [("LATA 350ML", 4.2, 58.0), ("LN 330ML", 7.92, 88.0)]),
    ("TUPÃ", "Não Alcoólicos", "#15803D", [("LATA 350ML", 4.2, 36.0), ("PET 2L", 12.0, 48.0)]),
    ("FONTE CLARA", "Não Alcoólicos", "#0284C7", [("PET 500ML", 6.0, 18.0), ("PET 1,5L", 9.0, 22.0)]),
]


def produtos() -> pl.DataFrame:
    r = rng("produtos")
    linhas = []
    codigo = 100100
    for marca, categoria, cor, embalagens in MARCAS:
        for embalagem, litros, preco in embalagens:
            codigo += r.randint(7, 40)
            # Custo de 62% a 80% do preço: dá markups entre 25% e 60%.
            custo = round(preco * r.uniform(0.62, 0.80), 2)
            linhas.append(
                {
                    "cod_produto": codigo,
                    "produto": f"{marca} {embalagem}",
                    "marca": marca,
                    "categoria": categoria,
                    "embalagem": embalagem,
                    "litros_caixa": litros,
                    "preco_caixa": preco,
                    "custo_caixa": custo,
                    "cor_marca": cor,
                    # Peso de venda: lata e 600ML vendem mais que garrafa pequena e premium.
                    "peso_venda": (3.0 if "LATA" in embalagem or "600" in embalagem else 1.2)
                    * (0.5 if categoria == "Premium" else 1.0),
                }
            )
    return pl.DataFrame(linhas)


def equipe() -> pl.DataFrame:
    """Gerentes e vendedores: 2 gerentes por filial, 5 vendedores por gerente."""
    f = faker("equipe")
    linhas = []
    cod = 10
    for filial in FILIAIS:
        for _ in range(2):
            gerente = f"{f.first_name()} {f.last_name()}"
            for _ in range(5):
                cod += 1
                linhas.append(
                    {
                        "cod_vendedor": cod,
                        "vendedor": f"{cod} - {f.first_name()} {f.last_name()}",
                        "gerente": gerente,
                        "filial": filial.nome,
                        "cod_filial": filial.codigo,
                    }
                )
    return pl.DataFrame(linhas)


_PREFIXOS = {
    "Bar": ["Bar do", "Bar da", "Boteco do", "Espetinho do"],
    "Restaurante": ["Restaurante", "Peixaria", "Churrascaria", "Cantina"],
    "Mercado": ["Mercadinho", "Mercearia", "Minibox", "Supermercado"],
    "Conveniência": ["Conveniência", "Posto e Conveniência", "Adega"],
    "Atacado": ["Distribuidora", "Atacadão", "Depósito"],
}
_PESO_CANAL = {"Bar": 0.42, "Restaurante": 0.14, "Mercado": 0.28, "Conveniência": 0.11, "Atacado": 0.05}


def cidades_da_filial(filial: Filial, vizinhas: int = 30, interior: int = 45) -> pl.DataFrame:
    """A sede e as vizinhas primeiro (é onde está a maior parte dos clientes), e
    mais um sorteio de cidades do interior: a filial atende o estado inteiro."""
    todas = municipios().filter(~pl.col("nome").map_elements(_hash, return_dtype=pl.Utf8).is_in(list(CIDADES_EVITADAS)))
    sede = todas.filter(pl.col("codigo_ibge") == filial.cod_ibge_sede).row(0, named=True)
    do_estado = (
        todas.filter(pl.col("uf") == filial.uf)
        .with_columns(
            ((pl.col("latitude") - sede["latitude"]) ** 2 + (pl.col("longitude") - sede["longitude"]) ** 2)
            .sqrt()
            .alias("distancia")
        )
        .sort("distancia")
    )
    resto = do_estado.slice(vizinhas)
    sorteio = rng(f"interior-{filial.codigo}").sample(range(resto.height), min(interior, resto.height))
    return pl.concat([do_estado.head(vizinhas), resto[sorted(sorteio)]]).with_columns(
        pl.lit(filial.nome).alias("filial")
    )


def clientes() -> pl.DataFrame:
    r = rng("clientes")
    f = faker("clientes")
    vendedores = equipe()
    linhas = []
    cod = 20000
    for filial in FILIAIS:
        cidades = cidades_da_filial(filial)
        # A sede concentra os clientes: peso cai com a posição na lista.
        pesos_cidade = [1 / (i + 1) ** 0.9 for i in range(cidades.height)]
        pesos_cidade[0] *= 4
        vend_filial = vendedores.filter(pl.col("filial") == filial.nome)["cod_vendedor"].to_list()
        for _ in range(520):
            cod += r.randint(1, 9)
            canal = r.choices(list(_PESO_CANAL), weights=list(_PESO_CANAL.values()))[0]
            prefixo = r.choice(_PREFIXOS[canal])
            nome = f"{prefixo} {f.first_name()}" if canal in ("Bar", "Conveniência") else f"{prefixo} {f.last_name()}"
            cidade = cidades.row(r.choices(range(cidades.height), weights=pesos_cidade)[0], named=True)
            # Inicio da carteira: a maioria é antiga, uma parte entrou neste ano.
            inicio = HOJE - timedelta(days=int(r.triangular(20, 2200, 1500)))
            linhas.append(
                {
                    "cod_cliente": cod,
                    "cliente": nome.upper(),
                    "canal": canal,
                    "cidade": cidade["nome"],
                    "cod_ibge": cidade["codigo_ibge"],
                    "uf": filial.uf,
                    "latitude": cidade["latitude"] + r.uniform(-0.03, 0.03),
                    "longitude": cidade["longitude"] + r.uniform(-0.03, 0.03),
                    "filial": filial.nome,
                    "cod_vendedor": r.choice(vend_filial),
                    "cliente_desde": inicio,
                    # Tamanho do cliente: poucos grandes, muitos pequenos.
                    "porte": round(r.paretovariate(2.2), 3) * (2.5 if canal == "Atacado" else 1.0),
                    # Uma parte da carteira está parada (sem compra recente).
                    "ativo": r.random() > 0.13,
                }
            )
    return pl.DataFrame(linhas)


def placa(r: random.Random) -> str:
    letras = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return (
        "".join(r.choice(letras) for _ in range(3))
        + str(r.randint(0, 9))
        + r.choice(letras)
        + f"{r.randint(0, 99):02d}"
    )


def veiculos() -> pl.DataFrame:
    r = rng("veiculos")
    modelos = [
        ("Caminhão 3/4", "VW Delivery 11.180", 9000),
        ("Caminhão 3/4", "Mercedes Accelo 1016", 9000),
        ("Toco", "VW Constellation 17.230", 14000),
        ("Truck", "Volvo VM 270", 23000),
        ("Utilitário", "Fiat Fiorino", 650),
        ("Moto", "Honda CG 160 Cargo", 20),
    ]
    linhas = []
    for filial in FILIAIS:
        for _ in range(r.randint(14, 20)):
            tipo, modelo, carga = r.choices(modelos, weights=[5, 4, 3, 2, 3, 2])[0]
            linhas.append(
                {
                    "placa": placa(r),
                    "tipo": tipo,
                    "modelo": modelo,
                    "ano": r.randint(2012, HOJE.year),
                    "capacidade_kg": carga,
                    "filial": filial.nome,
                    "uf": filial.uf,
                }
            )
    return pl.DataFrame(linhas)


def fornecedores() -> pl.DataFrame:
    r = rng("fornecedores")
    f = faker("fornecedores")
    tipos = [
        ("Fábrica", 6, (150000, 340000)),
        ("Combustível", 5, (8000, 60000)),
        ("Manutenção de frota", 8, (800, 18000)),
        ("Energia e água", 4, (2500, 22000)),
        ("Aluguel", 4, (9000, 35000)),
        ("Serviços", 10, (600, 12000)),
        ("Material de escritório", 4, (150, 3000)),
        ("Impostos", 3, (15000, 240000)),
    ]
    # Nome pelo ramo: "{s}" é um sobrenome sorteado.
    modelos = {
        "Fábrica": ["Cervejaria {s} Ltda", "Indústria de Bebidas {s}"],
        "Combustível": ["Posto {s} Combustíveis", "Auto Posto {s} Ltda"],
        "Manutenção de frota": ["{s} Auto Peças", "Oficina Diesel {s}", "{s} Pneus e Serviços"],
        "Energia e água": [
            "Companhia Energética Regional",
            "Companhia de Águas e Esgoto",
            "{s} Energia Solar",
            "Gás {s} Distribuidora",
        ],
        "Aluguel": ["{s} Imóveis Ltda", "Condomínio Logístico {s}"],
        "Serviços": [
            "{s} Contabilidade",
            "{s} Segurança Patrimonial",
            "{s} Limpeza e Conservação",
            "{s} Tecnologia da Informação",
            "{s} Advocacia",
        ],
        "Material de escritório": ["Papelaria {s}", "{s} Suprimentos de Escritório"],
        "Impostos": ["Secretaria da Fazenda Estadual", "Receita Federal - DARF", "Prefeitura Municipal - ISS"],
    }
    linhas = []
    cod = 5000
    for tipo, quantos, faixa in tipos:
        for i in range(quantos):
            cod += r.randint(1, 30)
            opcoes = modelos[tipo]
            nome = (opcoes[i % len(opcoes)] if tipo == "Impostos" else r.choice(opcoes)).format(s=f.last_name())
            linhas.append(
                {
                    "cod_fornecedor": cod,
                    "fornecedor": nome.upper(),
                    "tipo_despesa": tipo,
                    "valor_min": float(faixa[0]),
                    "valor_max": float(faixa[1]),
                }
            )
    return pl.DataFrame(linhas).unique("fornecedor", keep="first", maintain_order=True)


def usuarios() -> pl.DataFrame:
    """Quem usa os painéis: a equipe comercial e mais as áreas de apoio."""
    f = faker("usuarios")
    r = rng("usuarios")
    areas = [("Comercial", 10), ("Logística", 7), ("Financeiro", 6), ("Fiscal", 5), ("TI", 3), ("Diretoria", 2)]
    linhas = []
    for area, quantos in areas:
        for _ in range(quantos):
            nome = f"{f.first_name()} {f.last_name()}"
            linhas.append(
                {
                    "login": login_de(nome),
                    "nome": nome,
                    "area": area,
                    "filial": r.choice(FILIAIS).nome if area in ("Comercial", "Logística") else "Matriz",
                    "ativo": r.random() > 0.08,
                }
            )
    return pl.DataFrame(linhas).unique("login", keep="first", maintain_order=True)


def dias_uteis(inicio: date, fim: date) -> list[date]:
    """Segunda a sábado, como na operação de distribuição."""
    dias = []
    d = inicio
    while d <= fim:
        if d.weekday() < 6:
            dias.append(d)
        d += timedelta(days=1)
    return dias


def inicio_do_mes(d: date) -> date:
    return d.replace(day=1)


def meses_atras(d: date, n: int) -> date:
    """1º dia do mês n meses antes de d (n negativo anda para a frente)."""
    total = d.year * 12 + (d.month - 1) - n
    return date(total // 12, total % 12 + 1, 1)


def fim_do_mes(d: date) -> date:
    return meses_atras(d, -1) - timedelta(days=1)
