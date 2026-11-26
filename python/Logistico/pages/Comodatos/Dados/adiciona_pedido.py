from datetime import date, datetime, timedelta

from core import revendas
from core.db import obter_engine_comodato

EMPRESAS = revendas.para_erp(
    chave_dsn="banco",
    conexao_de={revendas.CNPJ_SEM_ERP_PROPRIO: revendas.CNPJ_ERP_EMPRESTADO},
    campos=("cnpj", "nome", "banco", "digito", "prefixo", "uf"),
)

ORIGEM_PEDIDO = "Q"

OCORRENCIA_COMODATO = 50
OCORRENCIA_COMODATO_OUTRO_ESTADO = 51


def _uf_do_cliente(cursor, prefixo: str, codcli: str) -> str:
    try:
        cursor.execute(
            f"SELECT RTRIM(VDCLICLI_ESTFAT) FROM {prefixo}CADCLI01 WHERE "
            "CAST(VDCLICLI_REGI AS VARCHAR(4)) || "
            "RIGHT('000' || LTRIM(RTRIM(CAST(VDCLICLI_NUM AS VARCHAR(4)))),4) = ?",
            codcli,
        )
        linha = cursor.fetchone()
    except Exception as exc:
        print(f"Nao deu pra ler a UF do cliente {codcli} -- {exc}")
        return ""
    return str(linha[0] or "").strip().upper() if linha else ""


def _empresa_da_revenda(revenda: str) -> dict | None:
    revenda_upper = revenda.upper()
    for empresa in EMPRESAS:
        if revenda_upper in empresa["nome"].upper():
            return empresa
    return None


def _codigo(valor, campo: str) -> int:
    texto = "" if valor is None else str(valor).split(" - ")[0].strip()
    if texto in ("", "None", "nan"):
        raise ValueError(f"Solicitacao com {campo} vazio -- confira o cadastro antes de enviar")
    return int(float(texto)) if "." in texto else int(texto)


def _itens_por_produto(itens_pedido: list[dict]) -> list[dict]:
    juntos: dict[tuple[int, int], dict] = {}
    for item in itens_pedido:
        chave = (_codigo(item["PRODUTO"], "produto"), _codigo(item["CODCOMP"], "codigo do item"))
        quantidade = _codigo(item["QTD"], "quantidade")
        valor = round(quantidade * (item["PRECO"] or 0), 2)
        if chave in juntos:
            juntos[chave]["_QTD"] += quantidade
            juntos[chave]["_VALOR"] = round(juntos[chave]["_VALOR"] + valor, 2)
        else:
            juntos[chave] = {**item, "_QTD": quantidade, "_VALOR": valor}
    for consolidado in juntos.values():
        if not consolidado["_QTD"]:
            raise ValueError(
                f'Solicitacao com quantidade zero em "{consolidado.get("PRODUTO")}"'
                " -- corrija a quantidade antes de enviar"
            )
        consolidado["_PRECO_UNIT"] = round(consolidado["_VALOR"] / consolidado["_QTD"], 2)
    return list(juntos.values())


def _proximo_pre_pedido(cursor, prefixo: str, hoje: date) -> int:
    inicio, fim = int(f"{hoje:%Y%m%d}5000"), int(f"{hoje:%Y%m%d}5999")
    cursor.execute(
        f"SELECT MAX(VDPEDCPP_PRE_PED) + 1 AS PRE_PED FROM {prefixo}VDPEDCPP "
        "WHERE VDPEDCPP_PRE_PED <= ? AND VDPEDCPP_PRE_PED >= ?",
        fim,
        inicio,
    )
    linha = cursor.fetchone()
    numero = int(linha[0]) if linha and linha[0] else inicio
    if numero > fim:
        raise RuntimeError(f"Faixa de pre-pedido do dia esgotada ({inicio}-{fim})")
    return numero


def _confere_pre_pedido_unico(cursor, prefixo: str, pre_pedido: int, itens_esperados: int) -> None:
    cursor.execute(f"SELECT COUNT(*) FROM {prefixo}VDPEDCPP WHERE VDPEDCPP_PRE_PED = ?", pre_pedido)
    cabecalhos = int(cursor.fetchone()[0] or 0)
    cursor.execute(f"SELECT COUNT(*) FROM {prefixo}VDPEDIPP WHERE VDPEDIPP_PRE_PED = ?", pre_pedido)
    itens = int(cursor.fetchone()[0] or 0)
    if cabecalhos != 1 or itens != itens_esperados:
        raise RuntimeError(
            f"Pre-pedido {pre_pedido} inconsistente: {cabecalhos} cabecalho(s) e {itens} item(ns)"
            f" (esperado 1 e {itens_esperados}). Outro envio pode ter pegado o mesmo numero."
        )


def gerar_pedido(itens_pedido: list[dict], executar: bool = False) -> str:
    if not itens_pedido:
        raise ValueError("gerar_pedido precisa de pelo menos 1 item")

    revenda = itens_pedido[0]["REVENDA"]
    cliente = itens_pedido[0]["CLIENTE"]
    data_pedido = itens_pedido[0]["DATA"]
    prazo = itens_pedido[0]["PRAZO"]
    tipo = itens_pedido[0]["TIPO"]
    produtos = sorted({item["PRODUTO"] for item in itens_pedido})

    sql_existe = (
        "SELECT COUNT(*) AS pendentes FROM tb_comod_solicitado WHERE "
        "REVENDA = :revenda AND CLIENTE = :cliente AND DATA = :data AND "
        "PRAZO = :prazo AND TIPO = :tipo AND PRODUTO IN :produtos AND PRE_PED IS NULL"
    )
    parametros_existe = {
        "revenda": revenda,
        "cliente": cliente,
        "data": data_pedido,
        "prazo": prazo,
        "tipo": tipo,
        "produtos": tuple(produtos),
    }

    empresa = _empresa_da_revenda(revenda)
    if empresa is None:
        return None

    if not executar:
        print("[DRY-RUN] gerar_pedido -- nao abriu conexao ODBC/MySQL nenhuma.")
        print(f"  1) checaria se ha item pendente: {sql_existe} {parametros_existe}")
        print(
            f"  2) se nao existir, conectaria no ERP via DSN={empresa['banco']} (prefixo={empresa['prefixo'] or '(nenhum)'})"
        )
        print(
            f"     leria a UF do cliente em CADCLI01: ocorrencia {OCORRENCIA_COMODATO} em {empresa['uf']}, {OCORRENCIA_COMODATO_OUTRO_ESTADO} em outro estado"
        )
        consolidados = _itens_por_produto(itens_pedido)
        print(
            f"  3) INSERT em {empresa['prefixo']}VDPEDCPP (1 linha, resumo do pedido, total {round(sum(i['_VALOR'] for i in consolidados), 2)})"
        )
        print(
            f"     + {empresa['prefixo']}VDPEDIPP linha a linha, 1 por produto: {len(consolidados)} item(ns) de {len(itens_pedido)} registro(s)"
        )
        for indice, item in enumerate(consolidados, start=1):
            print(
                f"       item {indice}: {item['PRODUTO']} qtd={item['_QTD']} unit={item['_PRECO_UNIT']} valor={item['_VALOR']}"
            )
        print(
            "  4) UPDATE tb_comod_solicitado SET PRE_PED = <novo> WHERE REVENDA/CLIENTE/PRODUTO/DATA/PRAZO/TIPO baterem, pra cada item"
        )
        return "dry-run"

    import pyodbc
    from sqlalchemy import bindparam, text

    consulta_existe = text(sql_existe).bindparams(bindparam("produtos", expanding=True))
    with obter_engine_comodato().connect() as conexao:
        pendentes = conexao.execute(consulta_existe, parametros_existe).scalar() or 0
    if not pendentes:
        return "consta"

    conexao_odbc = pyodbc.connect(f"DSN={empresa['banco']};charset=utf8mb4", autocommit=False)
    try:
        cursor = conexao_odbc.cursor()
        prefixo = empresa["prefixo"]
        hoje = date.today()
        pre_pedido = _proximo_pre_pedido(cursor, prefixo, hoje)

        itens_gravar = _itens_por_produto(itens_pedido)
        uf_cliente = _uf_do_cliente(cursor, prefixo, str(cliente).split(" - ")[0].strip())
        fora_do_estado = bool(uf_cliente) and uf_cliente != empresa["uf"]
        ocorrencia = OCORRENCIA_COMODATO_OUTRO_ESTADO if fora_do_estado else OCORRENCIA_COMODATO
        if fora_do_estado:
            print(f"Cliente em {uf_cliente}, filial em {empresa['uf']} -- ocorrencia {ocorrencia}")
        valor_total = round(sum(item["_VALOR"] for item in itens_gravar), 2)
        codcli_num = _codigo(cliente, "cliente")
        entrega = hoje + timedelta(days=2 if hoje.strftime("%w") == "6" else 1)

        cursor.execute(
            f"INSERT INTO {prefixo}VDPEDCPP ("
            "VDPEDCPP_NREMP, VDPEDCPP_PRE_PED, VDPEDCPP_LOGDT, VDPEDCPP_INCLDT, VDPEDCPP_INCLHR, "
            "VDPEDCPP_INCLSIGLA, VDPEDCPP_NPED, VDPEDCPP_CODCLI, VDPEDCPP_CGC, VDPEDCPP_FL_ORIGEM, "
            "VDPEDCPP_VEN, VDPEDCPP_TPCOBR, VDPEDCPP_CPG, VDPEDCPP_DT_ENTREGA, VDPEDCPP_TXFIN, "
            "VDPEDCPP_VLRTOTAL, VDPEDCPP_DTEMI, VDPEDCPP_DT1VC, VDPEDCPP_OBS, VDPEDCPP_MOSTRA, "
            "VDPEDCPP_ERP_TERCEIRO, VDPEDCPP_VALOR_ACRESCIMO, VDPEDCPP_VL_DESCTO, VDPEDCPP_QTD_PTS"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            empresa["digito"],
            pre_pedido,
            int(hoje.strftime("%Y%m%d")),
            int(hoje.strftime("%Y%m%d")),
            int(datetime.now().strftime("%H%M")),
            "Das",
            0,
            codcli_num,
            _codigo(itens_pedido[0]["CNPJ"], "CNPJ"),
            ORIGEM_PEDIDO,
            itens_pedido[0]["VEN"],
            5,
            1,
            int(entrega.strftime("%Y%m%d")),
            0.0,
            valor_total,
            int(hoje.strftime("%Y%m%d")),
            _codigo(itens_pedido[0]["VENC"], "vencimento"),
            "",
            1,
            "",
            0,
            0,
            0,
        )
        for indice, item in enumerate(itens_gravar, start=1):
            cursor.execute(
                f"INSERT INTO {prefixo}VDPEDIPP ("
                "VDPEDIPP_NREMP, VDPEDIPP_PRE_PED, VDPEDIPP_ITEM, VDPEDIPP_LOGDT, VDPEDIPP_INCLDT, "
                "VDPEDIPP_INCLHR, VDPEDIPP_INCLSIGLA, VDPEDIPP_OCOKD, VDPEDIPP_CODR, VDPEDIPP_PROD, "
                "VDPEDIPP_QTD, VDPEDIPP_QTDS, VDPEDIPP_TBPRD, VDPEDIPP_VLR_LIQUIDO, VDPEDIPP_VLR_BRUTO, "
                "VDPEDIPP_PREPRDU, VDPEDIPP_PREPRDUS, VDPEDIPP_PREPRDT_CX, VDPEDIPP_ORIGEM"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                empresa["digito"],
                pre_pedido,
                indice,
                int(hoje.strftime("%Y%m%d")),
                int(hoje.strftime("%Y%m%d")),
                int(datetime.now().strftime("%H%M")),
                "Das",
                ocorrencia,
                _codigo(item["PRODUTO"], "produto"),
                _codigo(item["CODCOMP"], "codigo do item"),
                item["_QTD"],
                0,
                _codigo(item["TAB_CEV"], "tabela do CEV"),
                item["_VALOR"],
                item["_VALOR"],
                item["_PRECO_UNIT"],
                round(item["_PRECO_UNIT"] / (item["UNIDADE"] or 1), 2),
                item["_VALOR"],
                ORIGEM_PEDIDO,
            )
        _confere_pre_pedido_unico(cursor, prefixo, pre_pedido, len(itens_gravar))
        conexao_odbc.commit()
    except Exception:
        conexao_odbc.rollback()
        raise
    finally:
        conexao_odbc.close()

    with obter_engine_comodato().connect() as conexao:
        for item in itens_pedido:
            conexao.execute(
                text(
                    "UPDATE tb_comod_solicitado SET PRE_PED = :pre_ped WHERE "
                    "REVENDA = :revenda AND CLIENTE = :cliente AND PRODUTO = :produto AND "
                    "DATA = :data AND PRAZO = :prazo AND TIPO = :tipo AND PRE_PED IS NULL"
                ),
                {
                    "pre_ped": str(pre_pedido),
                    "revenda": revenda,
                    "cliente": cliente,
                    "produto": item["PRODUTO"],
                    "data": data_pedido,
                    "prazo": prazo,
                    "tipo": tipo,
                },
            )
        conexao.commit()

    return "pegou"
