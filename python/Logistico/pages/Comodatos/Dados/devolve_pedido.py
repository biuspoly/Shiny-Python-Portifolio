import re
from datetime import date, datetime, timedelta
from functools import lru_cache

from loguru import logger
from sqlalchemy import text

from core import revendas
from core.config_arquivo import carregar_json
from core.db import obter_engine_comodato

EMPRESAS = revendas.para_erp(
    chave_dsn="banco",
    campos=("cnpj", "nome", "banco", "digito", "prefixo", "tabref", "ocorrencia_recolha", "uf"),
)

OCORRENCIA_RECOLHA_OUTRO_ESTADO = 100

REVENDAS_RECOLHA_PELA_REVENDA = {"São Luís"}

ARQUIVO_COBRANCA_RECOLHA = "recolha_comodato"
COBRANCA_DO_CONTROL = {"tipo_cobranca": 1, "condicao_pagamento": 15}


def cobranca_da_recolha(nome_revenda: str) -> dict[str, int]:
    config = carregar_json(ARQUIVO_COBRANCA_RECOLHA, padrao={})
    padrao = config.get("padrao") or {}
    chave_da_revenda = revendas.chave_nome(nome_revenda)
    da_revenda = {}
    for nome, valores in (config.get("por_revenda") or {}).items():
        if revendas.chave_nome(nome) == chave_da_revenda:
            da_revenda = valores or {}
    cobranca = {}
    for campo, valor_do_control in COBRANCA_DO_CONTROL.items():
        valor = da_revenda.get(campo, padrao.get(campo, valor_do_control))
        try:
            cobranca[campo] = int(valor)
        except (TypeError, ValueError):
            logger.warning(
                f"config/{ARQUIVO_COBRANCA_RECOLHA}.json: {campo}={valor!r} nao e' numero -- usando {valor_do_control}"
            )
            cobranca[campo] = valor_do_control
    return cobranca


def _empresa_da_revenda(revenda: str) -> dict | None:
    texto = revenda.upper()
    apelidos: dict[str, str] = {}
    nome = next((destino for origem, destino in apelidos.items() if origem in texto), None)
    if nome is None:
        nome = next(
            (empresa["nome"] for empresa in EMPRESAS if empresa["nome"].upper() in texto),
            None,
        )
    return next((empresa for empresa in EMPRESAS if empresa["nome"] == nome), None)


def aceita_recolha_pela_revenda(revenda: str | None) -> bool:
    empresa = _empresa_da_revenda(revenda or "")
    return empresa is not None and empresa["nome"] in REVENDAS_RECOLHA_PELA_REVENDA


def _linhas(cursor) -> list[dict]:
    colunas = [coluna[0] for coluna in cursor.description]
    return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]


def _sem_decimal(valor) -> str:
    if valor is None:
        return ""
    try:
        return str(int(float(valor)))
    except (TypeError, ValueError):
        return str(valor).strip()


def _data_emissao(origem: dict) -> date:
    demi = origem.get("VDFATNFR_DEMI")
    if isinstance(demi, datetime):
        return demi.date()
    if isinstance(demi, date):
        return demi
    texto = str(demi or "").strip().replace("/", "").replace("-", "")
    if re.fullmatch(r"\d{8}", texto):
        return datetime.strptime(texto, "%Y%m%d").date()
    print(f"Nota {_sem_decimal(origem.get('VDPEDCPE_NFIS'))} sem data de emissao -- usando a de inclusao")
    return datetime.strptime(_sem_decimal(origem["VDFATNFR_INCLDT"]), "%Y%m%d").date()


def texto_referencia(cev: str, nota: object, serie: object, emissao: date) -> tuple[str, str, str]:
    linha_1 = f"Ref. Comodato : {cev.zfill(6)}, Nota Fiscal Saida :"
    linha_2 = f" {_sem_decimal(nota).zfill(9)}/{_sem_decimal(serie):<3}, emitida em {emissao:%d/%m/%Y}, Nume"
    linha_3 = "ros dos Ativos:".ljust(43)
    return linha_1, linha_2, linha_3


def _inteiro_quando_der(valor):
    if isinstance(valor, bool) or not isinstance(valor, float):
        return valor
    return int(valor) if valor.is_integer() else valor


def _sem_float_inutil(registro: dict) -> dict:
    return {chave: _inteiro_quando_der(valor) for chave, valor in registro.items()}


def _confere_pedido_unico(cursor, prefixo: str, digito: int, pedido: int, itens_esperados: int) -> None:
    cursor.execute(f"SELECT COUNT(*) FROM {prefixo}PEDCP0{digito} WHERE VDPEDCPE_NPED = ?", pedido)
    cabecalhos = int(cursor.fetchone()[0] or 0)
    cursor.execute(f"SELECT COUNT(*) FROM {prefixo}PEDIT0{digito} WHERE VDPEDIPE_NIT = ?", pedido)
    itens = int(cursor.fetchone()[0] or 0)
    if cabecalhos != 1 or itens != itens_esperados:
        raise RuntimeError(
            f"Pedido de retorno {pedido} inconsistente: {cabecalhos} cabecalho(s) e"
            f" {itens} item(ns) (esperado 1 e {itens_esperados}). Outra recolha pode"
            " ter pegado o mesmo numero."
        )


def _inserir(cursor, tabela: str, registro: dict) -> None:
    colunas = list(registro)
    marcadores = ",".join("?" for _ in colunas)
    cursor.execute(
        f"INSERT INTO {tabela} ({','.join(colunas)}) VALUES ({marcadores})",
        *[registro[coluna] for coluna in colunas],
    )


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


def ler_origem(cursor, prefixo: str, digito: int, cev_consulta: object) -> tuple[list[dict], list[dict]]:
    cursor.execute(
        f"""
        SELECT DISTINCT CP.VDPEDCPE_DTB_X, CP.VDPEDCPE_NPED,
          R.VDROMCRO_DTB, CP.VDPEDCPE_CODCLI, CP.VDPEDCPE_VEN,
          CP.VDPEDCPE_SERIE, CP.VDPEDCPE_NFIS, CP.VDPEDCPE_CODTRA,
          CP.VDPEDCPE_PLACA, CP.VDPEDCPE_MOT, CP.VDPEDCPE_NITENS,
          CP.VDPEDCPE_IMPR, CP.VDPEDCPE_USUARIO, CP.VDPEDCPE_NFISULT,
          CP.VDPEDCPE_FLROMA, CP.VDPEDCPE_VLR_OGEM,
          CP.VDPEDCPE_HORA_GERACAO_NFS, NF.VDFATNFR_INCLDT, NF.VDFATNFR_DEMI
        FROM {prefixo}PEDCP0{digito} CP
        INNER JOIN {prefixo}CEVPED0{digito} C ON C.VDCEVPEN_NPED = CP.VDPEDCPE_NPED
        INNER JOIN {prefixo}CROMA0{digito} R ON
          CAST(R.VDROMCRO_ANOC AS VARCHAR(4)) ||
          RIGHT('00' || LTRIM(RTRIM(CAST(R.VDROMCRO_MESC AS VARCHAR(2)))), 2) ||
          RIGHT('00000' || LTRIM(RTRIM(CAST(R.VDROMCRO_SEQ AS VARCHAR(5)))), 5)
          = CAST(CP.VDPEDCPE_CROMA AS VARCHAR(15))
        INNER JOIN {prefixo}VDFATN0{digito} NF ON NF.VDFATNFR_NNF = CP.VDPEDCPE_NFIS
        WHERE C.VDCEVPEN_NRCCEV = ?
        """,
        cev_consulta,
    )
    cabecalhos = _linhas(cursor)
    if not cabecalhos:
        return [], []
    cursor.execute(
        f"""SELECT DISTINCT IT.* FROM {prefixo}PEDIT0{digito} IT
        INNER JOIN {prefixo}CEVPED0{digito} C ON C.VDCEVPEN_NPED = IT.VDPEDIPE_NIT
        WHERE C.VDCEVPEN_NRCCEV = ?""",
        cev_consulta,
    )
    return cabecalhos, _linhas(cursor)


def pedido_cancelado(fl: object, cancdt: object) -> bool:
    return int(float(fl or 0)) == 9 or int(float(cancdt or 0)) > 0


def recolha_em_aberto(cursor, prefixo: str, digito: int, cev_consulta: object) -> dict | None:
    cursor.execute(
        f"""
        SELECT DISTINCT CP.VDPEDCPE_NPED, CP.VDPEDCPE_FL, CP.VDPEDCPE_CANCDT,
          CP.VDPEDCPE_NFIS, CP.VDPEDCPE_DTEMIPED, CP.VDPEDCPE_USUARIO
        FROM {prefixo}CEVPED0{digito} C
        INNER JOIN {prefixo}PEDCP0{digito} CP ON CP.VDPEDCPE_NPED = C.VDCEVPEN_NPEDR
        INNER JOIN {prefixo}PEDIT0{digito} IT ON IT.VDPEDIPE_NIT = CP.VDPEDCPE_NPED
          AND IT.VDPEDIPE_NRCCEV = C.VDCEVPEN_NRCCEV
        WHERE C.VDCEVPEN_NRCCEV = ? AND C.VDCEVPEN_NPEDR <> C.VDCEVPEN_NPED
        """,
        cev_consulta,
    )
    return next(
        (p for p in _linhas(cursor) if not pedido_cancelado(p["VDPEDCPE_FL"], p["VDPEDCPE_CANCDT"])),
        None,
    )


def descricao_recolha(pedido: dict) -> str:
    numero = _sem_decimal(pedido["VDPEDCPE_NPED"])
    data = _sem_decimal(pedido["VDPEDCPE_DTEMIPED"])
    quando = f"{data[6:8]}/{data[4:6]}/{data[:4]}" if len(data) == 8 else data
    usuario = str(pedido.get("VDPEDCPE_USUARIO") or "").strip()
    nota = _sem_decimal(pedido["VDPEDCPE_NFIS"])
    quem = f", por {usuario}" if usuario else ""
    situacao = f"com a nota {nota}" if nota not in ("", "0") else "ainda sem nota"
    return f"pedido {numero}, de {quando}{quem}, {situacao}"


TABELA_RECOLHAS_CANCELADAS = "tb_comod_recolha_cancelada"
CRIAR_TABELA_RECOLHAS_CANCELADAS = f"""
CREATE TABLE IF NOT EXISTS {TABELA_RECOLHAS_CANCELADAS} (
    NPED VARCHAR(20) NOT NULL PRIMARY KEY,
    CEV VARCHAR(20),
    CNPJ VARCHAR(20),
    CANCELADO_EM VARCHAR(8),
    CONFERIDO_EM DATETIME
) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


@lru_cache(maxsize=1)
def garantir_tabela_recolhas_canceladas() -> bool:
    try:
        with obter_engine_comodato().begin() as conexao:
            conexao.execute(text(CRIAR_TABELA_RECOLHAS_CANCELADAS))
        return True
    except Exception as exc:
        logger.warning(f"Recolhas canceladas: nao deu pra preparar {TABELA_RECOLHAS_CANCELADAS} -- {exc}")
        return False


COLUNAS_QUEM_RECOLHEU = {"USUARIO": "VARCHAR(60)", "HORA": "VARCHAR(8)"}


def garantir_colunas_quem_recolheu() -> bool:
    try:
        with obter_engine_comodato().begin() as conexao:
            existentes = {
                str(nome).upper()
                for (nome,) in conexao.execute(
                    text(
                        "SELECT COLUMN_NAME FROM information_schema.COLUMNS"
                        " WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tb_comod_recolha'"
                    )
                )
            }
            faltando = [coluna for coluna in COLUNAS_QUEM_RECOLHEU if coluna not in existentes]
            if faltando:
                acrescimos = ", ".join(
                    f"ADD COLUMN {coluna} {COLUNAS_QUEM_RECOLHEU[coluna]} NULL" for coluna in faltando
                )
                conexao.execute(text(f"ALTER TABLE tb_comod_recolha {acrescimos}"))
        return True
    except Exception as exc:
        logger.warning(f"Recolha: nao deu pra acrescentar USUARIO/HORA em tb_comod_recolha -- {exc}")
        return False


def gerar_recolha(revenda: str, cev: str, executar: bool = False, pela_revenda: bool = False, usuario: str = "") -> str:
    empresa = _empresa_da_revenda(revenda)
    if empresa is None:
        raise ValueError(f"Revenda sem configuracao de recolha: {revenda}")
    if pela_revenda and empresa["nome"] not in REVENDAS_RECOLHA_PELA_REVENDA:
        raise ValueError(f"Recolha em nome da propria revenda nao conferida para {empresa['nome']}")
    cev = str(cev).removesuffix(".0").strip()
    cev_consulta: object = int(cev) if cev.isdigit() else cev
    cobranca = cobranca_da_recolha(empresa["nome"])

    if not executar:
        print("[DRY-RUN] gerar_recolha -- nao abriu conexao ODBC/MySQL nenhuma.")
        print(f"  1) consultaria o CEV {cev} no ERP via DSN={empresa['banco']}")
        print("     e pararia ai' se o CEV ja' tiver pedido de retorno nao cancelado")
        print(
            "  2) encerraria o pedido de comodato e criaria o pedido de retorno"
            f" (ocorrencia {empresa['ocorrencia_recolha']} em {empresa['uf']},"
            f" {OCORRENCIA_RECOLHA_OUTRO_ESTADO} se o cliente for de outro estado)"
        )
        print(
            f"     com a nota em nome {'da propria revenda' if pela_revenda else 'do cliente'},"
            f" tipo de cobranca {cobranca['tipo_cobranca']} e condicao de pagamento {cobranca['condicao_pagamento']}"
        )
        print(f"  3) registraria o novo pedido em tb_comod_recolha, pedido por {usuario or '(sem login)'}")
        return "dry-run"

    import pyodbc

    prefixo = empresa["prefixo"]
    digito = empresa["digito"]
    conexao = pyodbc.connect(f"DSN={empresa['banco']};charset=utf8mb4", autocommit=False)
    try:
        cursor = conexao.cursor()
        cabecalhos, itens = ler_origem(cursor, prefixo, digito, cev_consulta)
        if not cabecalhos:
            return "nao_encontrado"
        em_aberto = recolha_em_aberto(cursor, prefixo, digito, cev_consulta)
        if em_aberto:
            desfecho = "ja_faturado" if _sem_decimal(em_aberto["VDPEDCPE_NFIS"]) not in ("", "0") else "ja_existe"
            return f"{desfecho}|{descricao_recolha(em_aberto)}"
        origem = cabecalhos[0]
        hoje = date.today()

        cursor.execute(
            f"SELECT MAX(VDPEDCPE_NPED) + 1 FROM {prefixo}PEDCP0{digito} "
            "WHERE VDPEDCPE_NPED <= ? AND VDPEDCPE_NPED > ?",
            int(f"{hoje:%Y%m%d}9999"),
            int(f"{hoje:%Y%m%d}0000"),
        )
        proximo = cursor.fetchone()
        pedido_retorno = int(proximo[0]) if proximo and proximo[0] else int(f"{hoje:%Y%m%d}0001")
        ano_tabref, mes_tabref = empresa["tabref"].split(".")
        linha_1, linha_2, linha_3 = texto_referencia(
            cev, origem["VDPEDCPE_NFIS"], origem["VDPEDCPE_SERIE"], _data_emissao(origem)
        )

        pedido = {
            "VDPEDCPE_NPED": pedido_retorno,
            "VDPEDCPE_DTEMIPED": int(f"{hoje:%Y%m%d}"),
            "VDPEDCPE_NLOTE": 1,
            "VDPEDCPE_CROMA": 0,
            "VDPEDCPE_TIPOP": 1,
            "VDPEDCPE_TABREF1": int(ano_tabref),
            "VDPEDCPE_TABREF2": int(f"{mes_tabref}99"),
            "VDPEDCPE_CODCLI": origem["VDPEDCPE_CODCLI"],
            "VDPEDCPE_CATCLI": "99",
            "VDPEDCPE_VEN": origem["VDPEDCPE_VEN"],
            "VDPEDCPE_TPCOBR": cobranca["tipo_cobranca"],
            "VDPEDCPE_CPG": cobranca["condicao_pagamento"],
            "VDPEDCPE_DT1VC": int(f"{hoje + timedelta(days=180):%Y%m%d}"),
            "VDPEDCPE_LINHA_1": linha_1,
            "VDPEDCPE_LINHA_2": linha_2,
            "VDPEDCPE_LINHA_3": linha_3,
            "VDPEDCPE_ORIGEM_PED": "2",
            "VDPEDCPE_SERIE": "",
            "VDPEDCPE_NFIS": 0,
            "VDPEDCPE_CODTRA": origem["VDPEDCPE_CODTRA"],
            "VDPEDCPE_PLACA": origem["VDPEDCPE_PLACA"],
            "VDPEDCPE_MOT": origem["VDPEDCPE_MOT"],
            "VDPEDCPE_NITENS": origem["VDPEDCPE_NITENS"],
            "VDPEDCPE_FL": 0,
            "VDPEDCPE_IMPR": origem["VDPEDCPE_IMPR"],
            "VDPEDCPE_USUARIO": origem["VDPEDCPE_USUARIO"],
            "VDPEDCPE_NFISULT": origem["VDPEDCPE_NFISULT"],
            "VDPEDCPE_DTB_X": 0,
            "VDPEDCPE_FLROMA": "N",
            "VDPEDCPE_VLR_OGEM": origem["VDPEDCPE_VLR_OGEM"],
            "VDPEDCPE_FILLER_03": "2" if pela_revenda else "1",
            "VDPEDCPE_EM_ROMANEIO": "",
            "VDPEDCPE_TP_ROTEIRIZ": "",
            "VDPEDCPE_MULT_RECEBIMENTOS": "N",
            "VDPEDCPE_HORA_GERACAO_NFS": origem["VDPEDCPE_HORA_GERACAO_NFS"],
        }
        uf_cliente = _uf_do_cliente(cursor, prefixo, _sem_decimal(origem["VDPEDCPE_CODCLI"]))
        ocorrencia = empresa["ocorrencia_recolha"]
        if uf_cliente and uf_cliente != empresa["uf"]:
            ocorrencia = OCORRENCIA_RECOLHA_OUTRO_ESTADO
            print(f"Cliente em {uf_cliente}, filial em {empresa['uf']} -- ocorrencia {ocorrencia}")
        for item in itens:
            item.update(
                {
                    "VDPEDIPE_NIT": pedido_retorno,
                    "VDPEDIPE_LOGDT": 0,
                    "VDPEDIPE_INCLDT": 0,
                    "VDPEDIPE_INCLHR": 0,
                    "VDPEDIPE_INCLSIGLA": "",
                    "VDPEDIPE_NIVELAUDIT": 0,
                    "VDPEDIPE_PREPRDUS": 0,
                    "VDPEDIPE_SERIE": "",
                    "VDPEDIPE_NUMFAT": 0,
                    "VDPEDIPE_NATOP": 0,
                    "VDPEDIPE_LINHA": 0,
                    "VDPEDIPE_OCOKD": ocorrencia,
                    "VDPEDIPE_FL": "",
                    "VDPEDIPE_MOTTROCA": "50",
                    "VDPEDIPE_CFOP_SAIDA": 0,
                    "VDPEDIPE_SEQ_FIXA": 0,
                }
            )

        cursor.execute(
            f"UPDATE {prefixo}PEDCP0{digito} SET VDPEDCPE_FL = 8, VDPEDCPE_DTB_X = ? WHERE VDPEDCPE_NPED = ?",
            _inteiro_quando_der(origem["VDROMCRO_DTB"]),
            _inteiro_quando_der(origem["VDPEDCPE_NPED"]),
        )
        cursor.execute(
            f"UPDATE {prefixo}CEVPED0{digito} SET VDCEVPEN_NPEDR = ? WHERE VDCEVPEN_NRCCEV = ?",
            pedido_retorno,
            cev_consulta,
        )
        _inserir(cursor, f"{prefixo}PEDCP0{digito}", _sem_float_inutil(pedido))
        for item in itens:
            _inserir(cursor, f"{prefixo}PEDIT0{digito}", _sem_float_inutil(item))
        _confere_pedido_unico(cursor, prefixo, digito, pedido_retorno, len(itens))
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()

    registro = {
        "NPED": str(pedido_retorno),
        "CODCLI": str(origem["VDPEDCPE_CODCLI"]),
        "CEV": cev,
        "REVENDA": empresa["nome"],
        "CNPJ": empresa["cnpj"],
        "DATA": hoje.strftime("%Y%m%d"),
    }
    if garantir_colunas_quem_recolheu():
        registro["USUARIO"] = usuario.strip() or None
        registro["HORA"] = datetime.now().strftime("%H:%M:%S")
    colunas = ", ".join(registro)
    valores = ", ".join(f":{coluna}" for coluna in registro)
    with obter_engine_comodato().begin() as conexao:
        conexao.execute(text(f"INSERT INTO tb_comod_recolha ({colunas}) VALUES ({valores})"), registro)
    return "pegou"
