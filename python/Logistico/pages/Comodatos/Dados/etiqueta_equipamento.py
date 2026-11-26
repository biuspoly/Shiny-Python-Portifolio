from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

import polars as pl
from loguru import logger
from sqlalchemy import text

from core.db import obter_engine_comodato

from .funcao_extracao_doc import TIPOS_ACEITOS, ler_documento

try:
    from PIL import Image
    from pyzbar.pyzbar import ZBarSymbol
    from pyzbar.pyzbar import decode as _ler_codigos_de_barra

    _ERRO_LEITOR_QR = ""
except Exception as _erro:
    Image = None
    ZBarSymbol = None
    _ler_codigos_de_barra = None
    _ERRO_LEITOR_QR = f"{type(_erro).__name__}: {_erro}"
_leitor_qr_avisado = False

NOME_TABELA = "tb_equipamento_etiqueta"

TIPO_ESPERADO = "etiqueta_equipamento"

CHAVE = "SERIAL"

COLUNAS = (
    "SERIAL",
    "RG",
    "MODELO",
    "COD",
    "MARCA",
    "FABRICANTE",
    "DATA_FABRICACAO",
    "CODIGO_BARRAS",
    "PATRIMONIO",
    "CODCOMP",
    "CODRED",
    "TIPO_DOC",
    "ARQUIVOS",
    "ATUALIZADO_EM",
)

CAMPOS_DE_CONTROLE = ("ARQUIVOS", "ATUALIZADO_EM")

COLUNAS_DO_FABRICANTE = ("RG", "MODELO", "COD", "MARCA", "FABRICANTE", "DATA_FABRICACAO", "CODIGO_BARRAS")

CAMPOS_SEM_DIVERGENCIA = ("TIPO_DOC",)

CAMPOS_SEMPRE_ATUALIZA = ("CODCOMP", "CODRED")

CAMPOS_CANONIZAVEIS = ("FABRICANTE", "MARCA", "PATRIMONIO")

CAMPOS = {
    "SERIAL": ([{"numero", "serie"}, {"serial"}, {"serie"}], {"patrimon", "sap", "documento"}),
    "RG": ([{"rg"}, {"registro", "geral"}], {"codigo", "cod", "sap", "barras"}),
    "MODELO": ([{"modelo"}, {"mod"}], {"codigo", "eletrico", "opcional", "refrigerante"}),
    "COD": (
        [{"codigo"}, {"cod"}],
        {
            "barras",
            "barra",
            "sap",
            "cliente",
            "aviso",
            "seguranca",
            "gas",
            "parte",
            "ciclopentano",
            "patrimon",
            "advertencia",
            "refrigerante",
            "eletrico",
            "opcional",
        },
    ),
    "MARCA": ([{"marca", "bebida"}, {"logomarca"}, {"cor"}, {"marca"}], {"codigo"}),
    "FABRICANTE": ([{"fabricante"}, {"fabricado"}, {"empresa"}], {"associada", "responsavel", "brasil"}),
    "DATA_FABRICACAO": ([{"fabricacao"}], {"entrada", "saida", "validade"}),
    "CODIGO_BARRAS": ([{"barras"}, {"barra"}], set()),
    "DESCRICAO": ([{"descricao"}, {"aparelho"}, {"produto"}, {"especificacao"}, {"desc"}], {"codigo", "tipo"}),
    "PLAQUETA": (
        [
            {"patrimonio"},
            {"numero", "placa"},
            {"numero", "identificacao"},
            {"numero", "identificador"},
            {"numero", "tag"},
            {"placa"},
            {"identificacao"},
            {"identificador"},
            {"tag"},
            {"texto", "identificado"},
        ],
        {"ano", "validade", "selo", "adesivo", "qr", "data", "barras", "sap", "parcial", "repetitivo", "destaque"},
    ),
}

MINIMO_MARCA_SOLTA = 5

APELIDOS_MARCA = {"DEV": "JANGADA", "MAR": "MARÉ", "AMS": "CORAL"}

MARCAS_CONHECIDAS = (
    "MARÉ",
    "CORAL",
    "JANGADA",
    "TRILHO",
    "BAVARIA",
    "BRAVA",
    "SOLAR",
    "TIGER",
    "SERENA",
    "LUA AZUL",
    "EDELWEISS",
    "MANDACARU",
    "FAROL",
    "IPÊ IPÊ",
    "CINTRA",
    "MURPHYS",
)
FABRICANTES_CONHECIDOS = (
    "METALFRIO",
    "MERCOFRICON",
    "FRICON",
    "IMBERA",
    "GELOPAR",
    "ELETROFRIO",
    "VENAX",
)

DIGITOS_RG = 14
DIGITOS_SERIAL_NO_RG = 7

LIMITE_DIGITOS_SERIAL = 15

DIGITOS_BARRAS_METALFRIO = 24
SERIAL_NO_BARRAS = slice(12, 19)


_LETRAS_SOLTAS = re.compile(r"\b(?:[a-z] )+[a-z]\b")

_PADRAO_PATRIMONIO = re.compile(r"^(?:CP\d)?HNKM\d", re.IGNORECASE)

_PREFIXO_PATRIMONIO = re.compile(r"^CP\d", re.IGNORECASE)

_PONTAS_SUJAS = re.compile(r"^[^0-9A-Za-z]+|[^0-9A-Za-z]+$")

_PADRAO_CONTATO = re.compile(
    r"@|WWW\.|HTTPS?:|\.COM|\.BR\b|\bBR\s*-?\s*\d{2,}|"
    r"\b(?:CEP|KM|BAIRRO|DISTRITO|SETOR|RODOVIA|ROD|RUA|AV|AVENIDA|ESTRADA|"
    r"TRAVESSA|ALAMEDA|PRACA|LOTE|QUADRA|GALPAO)\b"
)

EXTENSOES_COM_QR = (".jpg", ".jpeg", ".png", ".webp")

LADO_MAXIMO_PARA_AMPLIAR = 2000

MINIMO_DIGITOS_PLAQUETA = 6

_TOKEN_PLAQUETA = re.compile(r"[0-9A-Za-z]+")

_QR_E_CODIGO = re.compile(r"^[0-9A-Za-z._-]{1,40}$")


def _texto_chave(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[_.\-/]", " ", sem_acento)).strip().lower()


def _maiusculo(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", sem_acento).strip().upper()


def _so_digitos(texto) -> str:
    return "".join(c for c in str(texto) if c.isdigit())


def serial_limpo(texto) -> str:
    if texto is None:
        return ""
    return _maiusculo(texto).replace(" ", "")


def _nome_canonico(nome: str) -> str:
    return _LETRAS_SOLTAS.sub(lambda achado: achado.group(0).replace(" ", ""), _texto_chave(nome))


def _campos_por_chave(campos_adicionais: dict) -> dict:
    return {
        _nome_canonico(nome): valor
        for nome, valor in (campos_adicionais or {}).items()
        if valor not in (None, "", "null")
    }


def _valores_do_campo(campos: dict, coluna: str) -> list[str]:
    exige, proibe = CAMPOS[coluna]
    achados = []
    for nome, valor in campos.items():
        if not valor:
            continue
        palavras = set(nome.split())
        if any(vetada in palavra for palavra in palavras for vetada in proibe):
            continue
        posicao = next((i for i, alternativa in enumerate(exige) if alternativa <= palavras), None)
        if posicao is not None:
            achados.append((posicao, len(nome), nome, str(valor).strip()))
    return [valor for *_, valor in sorted(achados)]


def _valor_do_campo(campos: dict, coluna: str) -> str:
    valores = _valores_do_campo(campos, coluna)
    return valores[0] if valores else ""


def _e_patrimonio(valor: str) -> bool:
    return bool(_PADRAO_PATRIMONIO.match(str(valor or "").replace(" ", "")))


def _serial_do_rg(rg: str) -> str:
    digitos = _so_digitos(rg)
    if len(digitos) != DIGITOS_RG:
        return ""
    return digitos[:-1][-DIGITOS_SERIAL_NO_RG:]


def _serial_do_codigo_barras(codigo_barras: str) -> str:
    digitos = _so_digitos(codigo_barras)
    if len(digitos) != DIGITOS_BARRAS_METALFRIO:
        return ""
    return digitos[SERIAL_NO_BARRAS]


def _codigo_barras_limpo(valor) -> str:
    return _maiusculo(valor).replace(" ", "")


def _data_fabricacao(valor: str) -> str:
    texto = _PONTAS_SUJAS.sub("", str(valor).strip())
    completa = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})$", texto)
    if completa:
        dia, mes, ano = completa.groups()
        ano = ano if len(ano) == 4 else f"20{ano}"
        return f"{int(dia):02d}/{int(mes):02d}/{ano}"
    ano_mes = re.match(r"^(\d{4})[/\-.](\d{1,2})$", texto)
    if ano_mes:
        ano, mes = ano_mes.groups()
        return f"{int(mes):02d}/{ano}"
    return texto


def marca_canonica(texto) -> str:
    alvo = _maiusculo(texto)
    return next((marca for marca in MARCAS_CONHECIDAS if marca in alvo), "")


def fabricante_canonico(texto) -> str:
    alvo = _maiusculo(texto)
    return next((nome for nome in FABRICANTES_CONHECIDOS if nome in alvo), "")


def _parece_contato(texto) -> bool:
    alvo = _maiusculo(texto)
    if _PADRAO_CONTATO.search(alvo):
        return True
    return not any(letra.isalpha() for letra in alvo)


def _e_dono_do_parque(texto) -> bool:
    return bool(marca_canonica(texto))


def _marca_na_descricao(marca: str, descricao: str) -> bool:
    if len(marca.replace(" ", "")) >= MINIMO_MARCA_SOLTA:
        return marca in descricao
    return bool(re.search(rf"(?<![A-Z]){re.escape(marca)}(?![A-Z])", descricao))


def _marca_da_cerveja(campos: dict, fabricante: str) -> str:
    candidato = _maiusculo(_valor_do_campo(campos, "MARCA"))
    conhecido = bool(fabricante_canonico(candidato))
    if candidato and not conhecido and candidato not in _maiusculo(fabricante):
        conhecida = marca_canonica(candidato)
        if conhecida:
            return conhecida
        de_campo_marca = any("marca" in nome and _maiusculo(valor) == candidato for nome, valor in campos.items())
        if de_campo_marca:
            return candidato
    descricao = _maiusculo(_valor_do_campo(campos, "DESCRICAO"))
    for marca in MARCAS_CONHECIDAS:
        if _marca_na_descricao(marca, descricao):
            return marca
    palavras = set(re.findall(r"[A-Z]+", descricao))
    for apelido, marca in APELIDOS_MARCA.items():
        if apelido in palavras:
            return marca
    return ""


def _fabricante_da_etiqueta(campos: dict) -> str:
    candidatos = _valores_do_campo(campos, "FABRICANTE")
    for texto in candidatos:
        conhecido = fabricante_canonico(texto)
        if conhecido:
            return conhecido
    for texto in _valores_do_campo(campos, "MARCA"):
        conhecido = fabricante_canonico(texto)
        if conhecido:
            return conhecido
    for texto in candidatos:
        alvo = _maiusculo(texto)
        if alvo and not _parece_contato(alvo) and not _e_dono_do_parque(alvo):
            return alvo
    return ""


def _pode_substituir(coluna: str, valor_atual: str, valor_novo: str) -> bool:
    if coluna not in CAMPOS_CANONIZAVEIS:
        return False
    if coluna == "FABRICANTE":
        return (
            fabricante_canonico(valor_atual) == valor_novo
            or _parece_contato(valor_atual)
            or _e_dono_do_parque(valor_atual)
        )
    if coluna == "PATRIMONIO":
        return patrimonio_canonico(valor_atual) == valor_novo
    return marca_canonica(valor_atual) == valor_novo


def patrimonio_canonico(texto) -> str:
    return _PREFIXO_PATRIMONIO.sub("", serial_limpo(texto))


def _patrimonio_da_etiqueta(campos: dict) -> str:
    for coluna in ("SERIAL", "COD", "MODELO"):
        for valor in _valores_do_campo(campos, coluna):
            limpo = serial_limpo(valor)
            if _e_patrimonio(limpo):
                return patrimonio_canonico(limpo)
    for nome, valor in campos.items():
        if "patrimon" in nome or "cp" in nome.split():
            limpo = serial_limpo(valor)
            if _e_patrimonio(limpo):
                return patrimonio_canonico(limpo)
    return ""


def _numero_na_plaqueta(valor) -> str:
    candidatos = [
        pedaco
        for pedaco in _TOKEN_PLAQUETA.findall(_maiusculo(valor))
        if MINIMO_DIGITOS_PLAQUETA <= len(_so_digitos(pedaco)) < LIMITE_DIGITOS_SERIAL
    ]
    return max(candidatos, key=lambda pedaco: len(_so_digitos(pedaco)), default="")


def _numero_da_plaqueta(campos: dict) -> str:
    for valor in _valores_do_campo(campos, "PLAQUETA"):
        numero = _numero_na_plaqueta(valor)
        if numero:
            return numero
    return ""


def _qr_da_foto(caminho_imagem) -> str:
    global _leitor_qr_avisado
    caminho = Path(caminho_imagem)
    if _ler_codigos_de_barra is None:
        if not _leitor_qr_avisado:
            _leitor_qr_avisado = True
            logger.warning(
                f"Leitor de QR indisponível ({_ERRO_LEITOR_QR}) -- a plaqueta de"
                " patrimônio só será lida pelo texto da foto. No Windows o zbar exige o"
                " Visual C++ 2013 x64 (MSVCR120.dll); sem a biblioteca, pip install pyzbar."
            )
        return ""
    if caminho.suffix.lower() not in EXTENSOES_COM_QR:
        return ""
    try:
        with Image.open(caminho) as foto:
            achados = _ler_codigos_de_barra(foto, symbols=[ZBarSymbol.QRCODE])
            if not achados and max(foto.size) <= LADO_MAXIMO_PARA_AMPLIAR:
                ampliada = foto.convert("L").resize((foto.width * 2, foto.height * 2), Image.LANCZOS)
                achados = _ler_codigos_de_barra(ampliada, symbols=[ZBarSymbol.QRCODE])
    except Exception as erro:
        logger.warning(f"QR da plaqueta nao pode ser lido ({caminho.name}) -- {erro}")
        return ""
    for achado in achados:
        texto = achado.data.decode("utf-8", "replace").strip()
        numero = serial_limpo(texto) if _QR_E_CODIGO.match(texto) else _numero_na_plaqueta(texto)
        if numero:
            return numero
    return ""


def _serial_da_etiqueta(campos: dict, rg: str, codigo_barras: str, qr: str = "") -> str:
    candidatos = [serial_limpo(valor) for valor in _valores_do_campo(campos, "SERIAL")]
    patrimonio = next((valor for valor in candidatos if _e_patrimonio(valor)), "")
    solto = next(
        (valor for valor in candidatos if not _e_patrimonio(valor) and len(_so_digitos(valor)) < LIMITE_DIGITOS_SERIAL),
        "",
    )
    do_rg = _serial_do_rg(rg)
    do_barras = _serial_do_codigo_barras(codigo_barras)
    if do_rg and do_barras and do_rg != do_barras:
        logger.warning(
            f"Etiqueta: serial do R.G. ({do_rg}) != do código de barras ({do_barras}) -- ficou com o do R.G."
        )
    return do_rg or do_barras or solto or qr or patrimonio


def _marca_nas_linhas_do_rotulo(texto: str) -> str:
    for linha in str(texto).splitlines():
        palavras = set(re.findall(r"[A-Z]+", _maiusculo(linha)))
        if palavras & {"COR", "MARCA", "LOGOMARCA"}:
            marca = marca_canonica(linha)
            if marca:
                return marca
    return ""


def _extrair(caminho_imagem: Path) -> dict:
    tipo_mime = TIPOS_ACEITOS.get(caminho_imagem.suffix.lower())
    if tipo_mime is None:
        raise ValueError("Formato não suportado. Envie PDF, JPEG, PNG ou WEBP.")
    corpo, motor = ler_documento(str(caminho_imagem), tipo_mime, TIPO_ESPERADO)
    if corpo is None:
        return {"api_offline": True}
    dados = corpo.get("data") or {}
    campos = {**(dados.get("campos_adicionais") or {}), **(corpo.get("campos") or {})}
    texto = str(corpo.get("texto") or "")
    if texto and not campos.get("fabricante"):
        campos["fabricante"] = fabricante_canonico(texto)
    if texto and not campos.get("marca_bebida"):
        campos["marca_bebida"] = _marca_nas_linhas_do_rotulo(texto)
    return {
        "api_offline": False,
        "motor": motor,
        "tipo_documento": corpo.get("document_type") or "",
        "tipo_normalizado": corpo.get("tipo_normalizado") or "",
        "campos": _campos_por_chave(campos),
        "numero_rg": dados.get("numero_rg") or "",
    }


def _linha_da_etiqueta(extraido: dict, arquivo: str, qr: str = "") -> dict:
    campos = _campos_por_chave(extraido["campos"])
    rg = _maiusculo(extraido.get("numero_rg") or _valor_do_campo(campos, "RG"))
    codigo_barras = _codigo_barras_limpo(_valor_do_campo(campos, "CODIGO_BARRAS"))
    if not codigo_barras:
        solto = _maiusculo(_valor_do_campo(campos, "SERIAL")).replace(" ", "")
        if len(_so_digitos(solto)) >= LIMITE_DIGITOS_SERIAL:
            codigo_barras = solto

    fabricante = _fabricante_da_etiqueta(campos)
    serial = _serial_da_etiqueta(campos, rg, codigo_barras, qr)
    patrimonio = qr or _patrimonio_da_etiqueta(campos)
    if not serial:
        patrimonio = patrimonio or _numero_da_plaqueta(campos)
        if not patrimonio and not rg and not _valor_do_campo(campos, "MODELO") and not fabricante_canonico(fabricante):
            patrimonio = next(
                (
                    numero
                    for numero in map(
                        _numero_na_plaqueta,
                        (codigo_barras, _valor_do_campo(campos, "COD"), _valor_do_campo(campos, "DATA_FABRICACAO")),
                    )
                    if numero
                ),
                "",
            )
        serial = patrimonio
    so_a_plaqueta = bool(serial) and serial == patrimonio
    return {
        "SERIAL": serial,
        "RG": rg,
        "MODELO": _maiusculo(_valor_do_campo(campos, "MODELO")),
        "COD": _maiusculo(_valor_do_campo(campos, "COD")),
        "MARCA": _marca_da_cerveja(campos, fabricante),
        "FABRICANTE": fabricante,
        "DATA_FABRICACAO": _data_fabricacao(_valor_do_campo(campos, "DATA_FABRICACAO")),
        "CODIGO_BARRAS": codigo_barras,
        "PATRIMONIO": patrimonio,
        "TIPO_DOC": str(extraido.get("tipo_documento") or ""),
        "ARQUIVOS": arquivo,
        "ATUALIZADO_EM": datetime.now().isoformat(timespec="seconds"),
        **({coluna: "" for coluna in COLUNAS_DO_FABRICANTE} if so_a_plaqueta else {}),
    }


def _mesclar(atual: dict, novo: dict) -> tuple[dict, list[str], list[str]]:
    linha, preenchidos, divergencias = dict(atual), [], []
    for coluna in COLUNAS:
        valor_novo = str(novo.get(coluna) or "").strip()
        if not valor_novo or coluna in CAMPOS_DE_CONTROLE:
            continue
        valor_atual = str(atual.get(coluna) or "").strip()
        if not valor_atual:
            linha[coluna] = valor_novo
            preenchidos.append(coluna)
        elif valor_atual == valor_novo:
            continue
        elif coluna in CAMPOS_SEMPRE_ATUALIZA:
            linha[coluna] = valor_novo
            preenchidos.append(coluna)
        elif _pode_substituir(coluna, valor_atual, valor_novo):
            linha[coluna] = valor_novo
            preenchidos.append(coluna)
        elif coluna not in CAMPOS_SEM_DIVERGENCIA:
            divergencias.append(f"{coluna}: base={valor_atual} foto={valor_novo}")

    arquivos = [a for a in str(atual.get("ARQUIVOS") or "").split(" | ") if a]
    if novo["ARQUIVOS"] not in arquivos:
        arquivos.append(novo["ARQUIVOS"])
    linha["ARQUIVOS"] = " | ".join(arquivos)
    if preenchidos:
        linha["ATUALIZADO_EM"] = novo["ATUALIZADO_EM"]
    return linha, preenchidos, divergencias


_SQL_CRIA = f"""
    CREATE TABLE IF NOT EXISTS {NOME_TABELA} (
        {CHAVE} VARCHAR(60) NOT NULL,
        RG VARCHAR(60),
        MODELO VARCHAR(60),
        COD VARCHAR(60),
        MARCA VARCHAR(40),
        FABRICANTE VARCHAR(60),
        DATA_FABRICACAO VARCHAR(10),
        CODIGO_BARRAS VARCHAR(40),
        PATRIMONIO VARCHAR(60),
        CODCOMP VARCHAR(10),
        CODRED VARCHAR(10),
        TIPO_DOC VARCHAR(120),
        ARQUIVOS TEXT,
        ATUALIZADO_EM VARCHAR(19),
        PRIMARY KEY ({CHAVE})
    )
"""

_tabela_pronta = False


COLUNAS_ACRESCENTADAS = {
    "PATRIMONIO": "VARCHAR(60)",
    "CODCOMP": "VARCHAR(10)",
    "CODRED": "VARCHAR(10)",
}


def _garantir_tabela(conexao) -> None:
    conexao.execute(text(_SQL_CRIA))
    faltando = [
        (coluna, tipo)
        for coluna, tipo in COLUNAS_ACRESCENTADAS.items()
        if not conexao.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS"
                " WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tabela"
                " AND COLUMN_NAME = :coluna"
            ),
            {"tabela": NOME_TABELA, "coluna": coluna},
        ).scalar()
    ]
    for coluna, tipo in faltando:
        logger.info(f"{NOME_TABELA}: acrescentando a coluna {coluna}")
        conexao.execute(text(f"ALTER TABLE {NOME_TABELA} ADD COLUMN {coluna} {tipo}"))


def garantir_tabela() -> None:
    global _tabela_pronta
    if _tabela_pronta:
        return
    with obter_engine_comodato().begin() as conexao:
        _garantir_tabela(conexao)
    _tabela_pronta = True


def _ler_linha(serial: str) -> dict | None:
    garantir_tabela()
    with obter_engine_comodato().connect() as conexao:
        linha = (
            conexao.execute(
                text(f"SELECT {', '.join(COLUNAS)} FROM {NOME_TABELA} WHERE {CHAVE} = :serial"),
                {"serial": serial},
            )
            .mappings()
            .first()
        )
    return {coluna: (linha[coluna] or "") for coluna in COLUNAS} if linha else None


LIMITE_COLUNA = {
    "SERIAL": 60,
    "RG": 60,
    "MODELO": 60,
    "COD": 60,
    "MARCA": 40,
    "FABRICANTE": 60,
    "DATA_FABRICACAO": 10,
    "CODIGO_BARRAS": 40,
    "PATRIMONIO": 60,
    "CODCOMP": 10,
    "CODRED": 10,
    "TIPO_DOC": 120,
    "ATUALIZADO_EM": 19,
}


def _no_tamanho_da_coluna(coluna: str, valor) -> str:
    texto = str(valor or "")
    limite = LIMITE_COLUNA.get(coluna)
    return texto[:limite] if limite else texto


def _gravar_linha(linha: dict) -> None:
    colunas = ", ".join(COLUNAS)
    valores = ", ".join(f":{coluna.lower()}" for coluna in COLUNAS)
    atualiza = ", ".join(f"{coluna}=VALUES({coluna})" for coluna in COLUNAS if coluna != CHAVE)
    with obter_engine_comodato().begin() as conexao:
        _garantir_tabela(conexao)
        conexao.execute(
            text(f"INSERT INTO {NOME_TABELA} ({colunas}) VALUES ({valores}) ON DUPLICATE KEY UPDATE {atualiza}"),
            {coluna.lower(): _no_tamanho_da_coluna(coluna, linha.get(coluna)) for coluna in COLUNAS},
        )


def ler_base() -> pl.DataFrame:
    garantir_tabela()
    with obter_engine_comodato().connect() as conexao:
        linhas = [
            {coluna: (registro[coluna] or "") for coluna in COLUNAS}
            for registro in conexao.execute(
                text(f"SELECT {', '.join(COLUNAS)} FROM {NOME_TABELA} ORDER BY ATUALIZADO_EM DESC")
            ).mappings()
        ]
    return pl.DataFrame(linhas, schema={coluna: pl.Utf8 for coluna in COLUNAS})


def ler_etiqueta(caminho_imagem, serial_informado: str = "", nome_arquivo: str = "") -> dict:
    caminho = Path(caminho_imagem)
    nome = nome_arquivo or caminho.name
    extraido = _extrair(caminho)
    digitado = serial_limpo(serial_informado)
    qr = _qr_da_foto(caminho)
    if extraido.get("api_offline"):
        if not digitado and not qr:
            return {"situacao": "api_offline", "serial": "", "linha": {}}
        extraido = {"tipo_documento": "", "numero_rg": "", "campos": {}}

    linha = _linha_da_etiqueta(extraido, nome, qr)
    if not linha[CHAVE] and digitado:
        linha[CHAVE] = digitado
    if not linha[CHAVE]:
        if extraido.get("motor") == "local":
            return {"situacao": "api_offline", "serial": "", "linha": linha}
        return {"situacao": "sem_serial", "serial": "", "linha": linha}
    return {"situacao": "lida", "serial": linha[CHAVE], "linha": linha}


def gravar_etiqueta(linha_lida: dict) -> dict:
    nova = dict(linha_lida or {})
    if not nova.get(CHAVE):
        return {"situacao": "sem_serial", "serial": "", "linha": nova, "preenchidos": [], "divergencias": []}

    atual = _ler_linha(nova[CHAVE])
    if atual is None:
        linha = nova
        situacao, preenchidos, divergencias = "novo", [c for c in COLUNAS if nova.get(c)], []
    else:
        linha, preenchidos, divergencias = _mesclar(atual, nova)
        situacao = "atualizado" if preenchidos else "sem_mudanca"

    _gravar_linha(linha)
    return {
        "situacao": situacao,
        "serial": nova[CHAVE],
        "linha": linha,
        "preenchidos": preenchidos,
        "divergencias": divergencias,
    }


def registrar_etiqueta(caminho_imagem, gravar: bool = True, serial_informado: str = "", nome_arquivo: str = "") -> dict:
    lida = ler_etiqueta(caminho_imagem, serial_informado, nome_arquivo)
    if lida["situacao"] != "lida":
        return {**lida, "preenchidos": [], "divergencias": []}
    if not gravar:
        atual = _ler_linha(lida["serial"])
        if atual is None:
            return {
                "situacao": "novo",
                "serial": lida["serial"],
                "linha": lida["linha"],
                "preenchidos": [c for c in COLUNAS if lida["linha"].get(c)],
                "divergencias": [],
            }
        linha, preenchidos, divergencias = _mesclar(atual, lida["linha"])
        return {
            "situacao": "atualizado" if preenchidos else "sem_mudanca",
            "serial": lida["serial"],
            "linha": linha,
            "preenchidos": preenchidos,
            "divergencias": divergencias,
        }
    return gravar_etiqueta(lida["linha"])
