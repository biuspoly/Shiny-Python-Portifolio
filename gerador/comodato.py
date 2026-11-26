"""Caches do Comodato (Logístico) no esquema original: os CEVs de comodato de cada revenda, a base e os
títulos dos clientes (o que libera ou trava uma solicitação nova), as solicitações já feitas, o catálogo
de produtos e o livro fiscal dos vasilhames. Também os três documentos de exemplo que os anexos abrem."""

from datetime import date, datetime, timedelta

import polars as pl

from gerador import base as b
from gerador.logistico import REVENDAS

PASTA = b.PY / "Logistico" / "data" / "bd_comodato"
UPLOADS = b.PY / "Logistico" / "uploads" / "comodatos"
CEVS_POR_REVENDA = 170
DIAS_PRAZO_ENVIO = 10
# Data de corte do bloqueio por prazo de material (config/excecoes_comodato.json): CEV de material
# emitido depois dela e sem documentação no prazo trava a revenda inteira na Solicitação.
CORTE_MATERIAL = date(2026, 8, 1)
REVENDA_COM_PRAZO_ESGOTADO = "Teresina"  # mostra o bloqueio da revenda inteira

# (CODCOMP, descrição, preço, tipo). Os códigos das caixas são os que a tela de Vasilhames reconhece.
PRODUTOS = [
    ("620050", "Refrigerador Vertical Mare 8Cx 220V", 2650.0, "Material"),
    ("620855", "Refrigerador Vertical Duas Portas 220V", 4100.0, "Material"),
    ("626014", "Refrigerador Horizontal 2 Tampas", 2300.0, "Material"),
    ("626015", "Freezer Horizontal 1 Tampa", 1850.0, "Material"),
    ("694004", "Mesa Plastica Quadrada Mare", 95.0, "Material"),
    ("694010", "Cadeira Plastica C/ Braco Mare", 48.0, "Material"),
    ("694020", "Cadeira De Madeira Mare", 120.0, "Material"),
    ("697001", "Carrinho Termico", 1500.0, "Material"),
    ("698001", "Quiosque Desmontavel", 3200.0, "Material"),
    ("699001", "Gela Placa 4 Grades", 980.0, "Material"),
    ("551001", "Caixa Plastica 24 Un 0,30L", 18.0, "Vasilhame"),
    ("587002", "Caixa Plastica 0,60L", 22.0, "Vasilhame"),
    ("690163", "Caixa Plastica 1L", 25.0, "Vasilhame"),
]
CANAIS = ["Bar C/D      ", "Mini C/D     ", "Adega        ", "Restaurante C", "Armazem/Merce"]
PORTES = ["Bronze", "Prata", "Ouro", "Diamante", "S/Definicao"]


def _aaaammdd(d: date) -> int:
    return int(f"{d:%Y%m%d}")


def _documentos_exemplo() -> None:
    """Um PDF de exemplo por tipo de anexo (no original, o arquivo de cada CEV)."""
    from fpdf import FPDF

    textos = {
        "pdv": ("PDV_exemplo.pdf", "Documento do responsável pelo ponto de venda"),
        "comodato": ("CEV_exemplo.pdf", "Contrato de comodato assinado"),
        "canhoto": ("CANHOTO_exemplo.pdf", "Canhoto da nota de entrega do equipamento"),
    }
    for pasta, (nome, titulo) in textos.items():
        destino = UPLOADS / pasta
        destino.mkdir(parents=True, exist_ok=True)
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 12, titulo, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(
            0,
            7,
            "Documento de exemplo do portfólio. No sistema real, aqui fica o arquivo enviado "
            "pela revenda ou pelo serviço de assinatura eletrônica.",
        )
        pdf.output(str(destino / nome))


def _clientes(r) -> dict[str, list[dict]]:
    f = b.faker("comodato-clientes")
    por_revenda: dict[str, list[dict]] = {}
    base = b.clientes()
    for codigo, (nome, cnpj, _licenca) in REVENDAS.items():
        filial = next(fl.nome for fl in b.FILIAIS if fl.codigo == codigo)
        linhas = []
        for c in base.filter(pl.col("filial") == filial).head(380).iter_rows(named=True):
            proprietario = f"{f.first_name()} {f.last_name()}"
            completo = r.random() < 0.85
            linhas.append(
                {
                    "codcli": str(c["cod_cliente"]),
                    "nome": c["cliente"],
                    "fantasia": c["cliente"],
                    "cnpj_cli": f"{r.randint(10_000_000, 99_999_999)}0001{r.randint(10, 99)}",
                    "cidade": c["cidade"],
                    "ven": f"{c['cod_vendedor']:03d}",
                    "canal": r.choice(CANAIS),
                    "porte": r.choice(PORTES),
                    "endereco": f"{f.street_name()}, {r.randint(10, 2000)}",
                    "cep": f"{r.randint(57000, 65999)}-{r.randint(0, 999):03d}",
                    "fone": f"{r.randint(81, 99)}9{r.randint(10_000_000, 99_999_999)}" if completo else "0",
                    "proprietario": proprietario if completo else "",
                    "cpf": float(r.randint(10_000_000_000, 99_999_999_999)) if completo else 0.0,
                    "email": f"{b.login_de(proprietario)}@exemplo.com" if completo else "",
                    "inadimplente": "Sim" if r.random() < 0.06 else "Não",
                    "revenda": nome,
                    "cnpj_rev": cnpj,
                }
            )
        por_revenda[nome] = linhas
    return por_revenda


def _cevs(r, clientes: dict[str, list[dict]]) -> list[dict]:
    hoje = b.HOJE
    f = b.faker("comodato-usuarios")
    usuarios = [b.login_de(f"{f.first_name()} {f.last_name()}") for _ in range(6)]
    materiais = [p for p in PRODUTOS if p[3] == "Material"]
    vasilhames = [p for p in PRODUTOS if p[3] == "Vasilhame"]
    linhas = []
    numero = 3000
    for nome, cnpj, _licenca in REVENDAS.values():
        bloqueou = False
        for _ in range(CEVS_POR_REVENDA):
            numero += r.randint(1, 9)
            cliente = r.choice(clientes[nome])
            emissao = hoje - timedelta(days=int(r.triangular(0, 700, 60)))
            sorteio = r.random()
            intervalo = 365 if sorteio < 0.78 else 30 if sorteio < 0.9 else r.choice([0, 181, 730])
            vencimento = emissao + timedelta(days=intervalo)
            tipo = "Material" if r.random() < 0.82 else "Vasilhame"
            origem = "Dash" if (hoje - emissao).days < 200 and r.random() < 0.55 else "ERP"
            prazo_vence = emissao + timedelta(days=DIAS_PRAZO_ENVIO)
            no_prazo = prazo_vence >= hoje
            # Quem passou do prazo de envio quase sempre está com a documentação em dia; depois do corte,
            # sem exceção (senão a revenda inteira trava) -- menos um CEV de propósito numa revenda.
            if no_prazo:
                completo = r.random() < 0.25
            elif tipo == "Material" and emissao >= CORTE_MATERIAL:
                completo = not (nome == REVENDA_COM_PRAZO_ESGOTADO and not bloqueou)
                bloqueou = bloqueou or not completo
            else:
                completo = r.random() < 0.8
            parcial = not completo and r.random() < 0.4
            anexos = {
                "anexo1": "uploads/comodatos/pdv/PDV_exemplo.pdf" if completo else None,
                "anexo2": "uploads/comodatos/comodato/CEV_exemplo.pdf" if completo or parcial else None,
                "anexo3": "uploads/comodatos/canhoto/CANHOTO_exemplo.pdf" if completo else None,
            }
            situacao = "A" if completo else ("B" if parcial else None)
            inad = cliente["inadimplente"]
            for codcomp, produto, _preco, _tipo in r.sample(
                materiais if tipo == "Material" else vasilhames, r.randint(1, 3) if tipo == "Material" else 1
            ):
                if tipo == "Vasilhame":
                    qtd = float(r.choice([10, 20, 30, 50, 80, 120]))
                elif "Mesa" in produto or "Cadeira" in produto:
                    qtd = float(r.choice([4, 8, 12, 16, 24]))
                else:
                    qtd = 1.0
                linhas.append(
                    {
                        "revenda": nome,
                        "cnpj": cnpj,
                        "cev": numero,
                        "codcomp": int(codcomp),
                        "produto": produto,
                        "qtd": qtd,
                        "tipo": tipo,
                        "emissao": emissao,
                        "vencimento": vencimento,
                        "intervalo": intervalo,
                        "prazo": (prazo_vence - hoje).days,
                        "nf": r.randint(100000, 999999),
                        "cliente": cliente,
                        "inad": inad,
                        "usuario": r.choice(usuarios) if situacao else None,
                        "dataI": f"{emissao + timedelta(days=r.randint(1, 9)):%Y-%m-%d} {r.randint(8, 17):02d}:{r.randint(0, 5)}"
                        if situacao
                        else None,
                        "situacao": situacao,
                        "origem": origem,
                        **anexos,
                    }
                )
    return linhas


def _tabelas_dos_cevs(linhas: list[dict]) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    geral, base, saldo = [], [], []
    for x in linhas:
        c = x["cliente"]
        comuns = {
            "Data Emissão": _aaaammdd(x["emissao"]),
            "Data Vencimento": _aaaammdd(x["vencimento"]),
            "Intervalo Vencimento": x["intervalo"],
            "Prazo Envio": x["prazo"],
        }
        geral.append(
            {
                "EMPRESA": x["revenda"],
                "CEV": f"{x['revenda']} - {x['cev']}",
                "CODCOMP": x["codcomp"],
                "NF": x["nf"],
                "Cliente": c["codcli"],
                "Fantasia": c["fantasia"],
                "Razão Social": c["nome"],
                **comuns,
                "Produto": x["produto"],
                "Qtd": x["qtd"],
                "Inadimplencia 60 dias +": x["inad"],
                "Usuario": x["usuario"],
                "dataI": x["dataI"],
                "anexo1": x["anexo1"],
                "anexo2": x["anexo2"],
                "anexo3": x["anexo3"],
                "situacao": x["situacao"],
                "cnpj": x["cnpj"],
                "VEN": c["ven"],
                "CNPJ_CLI": c["cnpj_cli"],
                "ENDERECO": c["endereco"],
                "CEP": c["cep"],
                "Origem": x["origem"],
            }
        )
        base.append(
            {
                "Revenda": x["revenda"],
                "CODCOMP": x["codcomp"],
                "CEV": x["cev"],
                "Cliente": c["codcli"],
                "Fantasia": c["fantasia"],
                "Razão Social": c["nome"],
                **comuns,
                "Produto": x["produto"],
                "Qtd": x["qtd"],
                "Inadimplencia 60 dias +": x["inad"],
                "Usuario": x["usuario"],
                "dataI": x["dataI"],
                "cnpj_rev": x["cnpj"],
                "anexo1": x["anexo1"],
                "anexo2": x["anexo2"],
                "anexo3": x["anexo3"],
                "situacao": x["situacao"],
                "CHAVE_CLI": c["codcli"] + x["cnpj"],
                "TIPO": x["tipo"],
            }
        )
        saldo.append(
            {
                "Revenda": x["revenda"],
                "CODCOMP": x["codcomp"],
                "Inadimplente": x["inad"],
                "Prazo Envio": x["prazo"],
                "Data Emissão": _aaaammdd(x["emissao"]),
                "Intervalo Vencimento": x["intervalo"],
                "dataI": x["dataI"],
                "situacao": x["situacao"],
                "cnpj_rev": x["cnpj"],
                "CEV": x["cev"],
            }
        )
    return (
        pl.DataFrame(geral, infer_schema_length=None),
        pl.DataFrame(base, infer_schema_length=None),
        pl.DataFrame(saldo, infer_schema_length=None),
    )


def _titulos(r, clientes: dict[str, list[dict]], linhas: list[dict]) -> pl.DataFrame:
    com_cev = {(x["cnpj"], x["cliente"]["codcli"]) for x in linhas}
    saida = []
    for nome, lista in clientes.items():
        for c in lista:
            saida.append(
                {
                    "CGC_CPF": "Cnpj",
                    "PORTE": c["porte"],
                    "CHAVE": c["cnpj_cli"],
                    "CHAVE_CLI": c["codcli"] + c["cnpj_rev"],
                    "CHAVE_VEN": c["ven"] + c["cnpj_rev"],
                    "FANTASIA": c["fantasia"],
                    "NOME": c["nome"],
                    "CANAL": c["canal"],
                    "VEN": c["ven"],
                    "CODCLI": c["codcli"],
                    "CNPJ_REV": c["cnpj_rev"],
                    "ENDERECO": c["endereco"],
                    "CONTATO": c["proprietario"],
                    "PTO_REF": "",
                    "CIDADE": c["cidade"],
                    "DIA_VISIT": r.choice(["2", "3", "4", "5", "6"]),
                    "SEQ": str(r.randint(1, 40)),
                    "CEP": c["cep"],
                    "FONE": c["fone"],
                    "PROPRIETARIO": c["proprietario"],
                    "CPF_PROP": c["cpf"],
                    "EMAIL_PROP": c["email"],
                    "NASC_PROP": r.randint(19600101, 20000101),
                    "TITULO_MAIS_ANTIGO": _aaaammdd(b.HOJE - timedelta(days=r.randint(0, 120))),
                    "Inadimplente": c["inadimplente"],
                    "Titulos": r.randint(0, 6),
                    "CEV_PEN": "Sim" if (c["cnpj_rev"], c["codcli"]) in com_cev and r.random() < 0.1 else "Não",
                    "subordinacao": r.choice(["100", "300", "400", None]),
                    "REVENDA": nome,
                    "TEM_CAD": "Sim" if (c["cnpj_rev"], c["codcli"]) in com_cev else "Não",
                }
            )
    return pl.DataFrame(saida, infer_schema_length=None)


def _catalogo(r) -> pl.DataFrame:
    linhas = []
    for nome, cnpj, licenca in REVENDAS.values():
        for n, (codcomp, produto, preco, tipo) in enumerate(PRODUTOS):
            linhas.append(
                {
                    "CODCOMP": codcomp,
                    "CODRED": float(9000 + n),
                    "PRODUTO": produto,
                    "PRODUTO_GENERICO": produto,
                    "UNIDADE": 1,
                    "LITRAGEM": 0.0,
                    "TIPO": tipo,
                    "GRUPO": 50 if tipo == "Material" else 60,
                    "NCM": 84182100 if "Refrigerador" in produto or "Freezer" in produto else 39241000,
                    "CEV": "S",
                    "MARCA": "MARE                " if "Mare" in produto else "OUTROS              ",
                    "CNPJ_REV": cnpj,
                    "REVENDA": nome,
                    "LICENCA": licenca,
                    "TIPO_2": "A",
                    "COD_PROD_FORN": codcomp,
                    "ESTOQUE": "SIM",
                    "PRECO": round(preco * r.uniform(0.95, 1.05), 2),
                    "TAB_CEV": "20200199",
                    "STATUS_DLP": None,
                }
            )
    return pl.DataFrame(linhas, infer_schema_length=None)


def _solicitacoes(r, clientes: dict[str, list[dict]]) -> pl.DataFrame:
    f = b.faker("comodato-solicitantes")
    usuarios = [b.login_de(f"{f.first_name()} {f.last_name()}") for _ in range(4)]
    linhas = []
    for nome, lista in clientes.items():
        for _ in range(r.randint(6, 10)):
            c = r.choice([x for x in lista if x["inadimplente"] == "Não" and x["proprietario"]])
            dia = b.HOJE - timedelta(days=r.randint(0, 20))
            prazo = r.choice(["1 ano", "1 ano", "30 dias"])
            venc = dia + (timedelta(days=365) if prazo == "1 ano" else timedelta(days=30))
            enviado = r.random() < 0.5
            pre_ped = f"{dia:%Y%m%d}{5000 + r.randint(0, 80)}" if enviado else None
            for codcomp, produto, preco, tipo in r.sample([p for p in PRODUTOS if p[3] == "Material"], r.randint(1, 2)):
                linhas.append(
                    {
                        "REVENDA": nome,
                        "CLIENTE": c["codcli"],
                        "CNPJ": c["cnpj_cli"],
                        "USUARIO": r.choice(usuarios),
                        "PRODUTO": produto,
                        "CODCOMP": codcomp,
                        "UNIDADE": 1,
                        "PRECO": preco,
                        "QTD": 1 if preco > 500 else r.choice([4, 8, 12]),
                        "TIPO": tipo,
                        "TAB_CEV": "20200199",
                        "VEN": c["ven"],
                        "ENDERECO": c["endereco"],
                        "CONTATO": c["proprietario"],
                        "PTO_REF": "",
                        "DIA_VISIT": "3",
                        "SEQ": "1",
                        "CEP": c["cep"],
                        "FONE": c["fone"],
                        "DATA": f"{dia:%Y%m%d}",
                        "VENC": f"{venc:%Y%m%d}",
                        "PRAZO": prazo,
                        "PRE_PED": pre_ped,
                    }
                )
    return pl.DataFrame(linhas, infer_schema_length=None)


def _livro(r, clientes: dict[str, list[dict]]) -> pl.DataFrame:
    """Livro fiscal dos vasilhames: vendas, empréstimos e devoluções de caixa por cliente."""
    hoje = b.HOJE
    caixas = [p for p in PRODUTOS if p[3] == "Vasilhame"]
    operacoes = [("Vendi", 0.35), ("Emprestei", 0.25), ("Dev Emprestimo", 0.3), ("Dev Venda", 0.1)]
    linhas = []
    for nome, cnpj, licenca in REVENDAS.values():
        for _ in range(420):
            c = r.choice(clientes[nome])
            dia = hoje - timedelta(days=r.randint(0, 420))
            codcomp, produto, _p, _t = r.choice(caixas)
            operacao = r.choices([o for o, _ in operacoes], [p for _, p in operacoes])[0]
            qtd = r.choice([5, 10, 20, 30, 50])
            linhas.append(
                {
                    "NF": r.randint(100000, 999999),
                    "OPERACAO": operacao,
                    "DATA": f"{dia:%Y%m%d}",
                    "CLI": int(c["codcli"]),
                    "PRODUTO": codcomp,
                    "QTD": qtd,
                    "QTDS": qtd,
                    "VEN": c["ven"],
                    "CNPJ_REV": cnpj,
                    "PRODUTO_GENERICO": produto,
                    "LICENCA": licenca,
                    "MES": f"{dia:%Y%m}",
                    "GRUPO_REV": nome,
                    "MES_ATUAL": f"{hoje:%Y%m}",
                    "CHAVE_PROD": f"{codcomp}{cnpj}",
                    "UNIDADE": 24.0,
                    "QTD_REAL": float(qtd * 24),
                }
            )
    return pl.DataFrame(linhas, infer_schema_length=None)


def gerar() -> None:
    print("Comodato")
    r = b.rng("comodato")
    PASTA.mkdir(parents=True, exist_ok=True)
    for antigo in PASTA.glob("*.parquet"):
        antigo.unlink()
    _documentos_exemplo()
    clientes = _clientes(r)
    linhas = _cevs(r, clientes)
    geral, base, saldo = _tabelas_dos_cevs(linhas)
    tabelas = {
        "comod_geral_bruto": geral,
        "clientes_inadimplentes_base_bruto": base,
        "saldo_comodatos_geral_bruto": saldo,
        "clientes_inadimplentes_titulos_bruto": _titulos(r, clientes, linhas),
        "produtos_cev_bruto": _catalogo(r),
        "comod_solicitado_bruto": _solicitacoes(r, clientes),
        "saldo_livro_bruto": _livro(r, clientes),
    }
    for nome, df in tabelas.items():
        df.write_parquet(PASTA / f"{nome}.parquet", compression="zstd")
        print(f"  bd_comodato/{nome}.parquet: {df.height:,} linhas".replace(",", "."))
    momento = datetime.combine(b.HOJE, datetime.min.time()).replace(hour=6, minute=10).isoformat(timespec="seconds")
    import json

    (PASTA / "_atualizacoes.json").write_text(json.dumps({n: momento for n in tabelas}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    gerar()
