from __future__ import annotations

import re
import shutil
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from loguru import logger
from sqlalchemy import bindparam, text

from core.db import obter_engine_comodato

from . import etiqueta_equipamento as eq

PASTA_APP = Path(__file__).parent.parent.parent.parent
PASTA_UPLOADS_IDENT = PASTA_APP / "uploads" / "comodatos" / "identificador"
PASTA_UPLOADS_MATERIAL = PASTA_APP / "uploads" / "comodatos" / "material"
for _pasta in (PASTA_UPLOADS_IDENT, PASTA_UPLOADS_MATERIAL):
    _pasta.mkdir(parents=True, exist_ok=True)

CHAVE_FOTO_MATERIAL = "foto_material_comodato"

TABELA_FOTO = "tb_comod_material_foto"

PREFIXO_IDENT = "IDENT"
PREFIXO_MATERIAL = "MATERIAL"

TIPOS_ACEITOS = list(eq.TIPOS_ACEITOS)

_tabela_pronta = False

_SQL_CRIA_FOTO = f"""
    CREATE TABLE IF NOT EXISTS {TABELA_FOTO} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        SERIAL VARCHAR(60) NOT NULL,
        ANEXO VARCHAR(255) NOT NULL,
        ANEXO_ETIQUETA VARCHAR(255),
        REVENDA VARCHAR(50),
        CNPJ_REV VARCHAR(20),
        CLIENTE VARCHAR(120),
        CODCLI VARCHAR(20),
        CODCOMP VARCHAR(10),
        PRODUTO VARCHAR(120),
        USUARIO VARCHAR(60),
        DATA VARCHAR(19),
        KEY idx_comod_material_foto (SERIAL)
    )
"""


_REFRIGERADOR_POR_EXTENSO = re.compile(r"REFRIGERAD|FREEZER|FRIZER", re.IGNORECASE)

_REFRIGERADOR_ABREVIADO = re.compile(r"\bREFR?\b|\bREF\b", re.IGNORECASE)

_SINAL_DE_EQUIPAMENTO = re.compile(
    r"\d{3}\s*V\b|BIVOLT|\bVT\b|\bVERT\b|HORIZ|\bHZ\b|\bPV\b|\bPC\b|PTCG|PTVD"
    r"|\d+\s*CX\b|\d{2,}\s*L\b",
    re.IGNORECASE,
)


def produto_pede_foto(tipo: str | None, produto: str | None) -> bool:
    if (tipo or "").strip().lower() != "material":
        return False
    nome = (produto or "").strip()
    if not nome:
        return False
    if _REFRIGERADOR_POR_EXTENSO.search(nome):
        return True
    if _REFRIGERADOR_ABREVIADO.search(nome):
        return bool(_SINAL_DE_EQUIPAMENTO.search(nome))
    return False


def _sanitizar_nome_arquivo(nome: str) -> str:
    return re.sub(r"[^\w.\-]", "_", nome)


def garantir_tabela() -> None:
    return None


def url_foto(caminho: str) -> str:
    nome = Path(caminho or "").name
    if not nome:
        return ""
    subpasta = "identificador" if nome.startswith(f"{PREFIXO_IDENT}_") else "material"
    return f"uploads/comodatos/{subpasta}/{quote(nome)}"


def _copiar(origem: str, nome_original: str | None, prefixo: str, serial: str, pasta: Path) -> str:
    nome = f"{prefixo}_{serial}_{_sanitizar_nome_arquivo(nome_original or Path(origem).name)}"
    destino = pasta / nome
    shutil.copy(origem, destino)
    return str(destino.resolve())


def fotos_do_equipamento(serial: str) -> list[dict]:
    return []


def fotos_por_item(cnpj_rev: str, codcli: str, codcomps: Iterable[str]) -> dict[str, list[dict]]:
    codigos = sorted({str(c).removesuffix(".0").strip() for c in codcomps if str(c or "").strip()})
    if not codigos or not str(codcli or "").strip():
        return {}
    achadas: dict[str, list[dict]] = {}
    try:
        garantir_tabela()
        with obter_engine_comodato().connect() as conexao:
            linhas = conexao.execute(
                text(
                    f"SELECT SERIAL, ANEXO, ANEXO_ETIQUETA, CODCOMP, PRODUTO, USUARIO, DATA"
                    f" FROM {TABELA_FOTO}"
                    " WHERE CNPJ_REV = :cnpj AND CODCLI = :codcli"
                    " AND CODCOMP IN :codigos ORDER BY DATA DESC"
                ).bindparams(bindparam("codigos", expanding=True)),
                {"cnpj": str(cnpj_rev or ""), "codcli": str(codcli).strip(), "codigos": codigos},
            ).mappings()
            for linha in linhas:
                achadas.setdefault(str(linha["CODCOMP"] or "").strip(), []).append(dict(linha))
    except Exception as exc:
        logger.warning(f"Comodatos: nao deu pra ler as fotos do material -- {exc}")
        return {}
    return achadas


def ler_etiqueta(caminho_ident: str, nome_ident: str | None = None) -> dict:
    return eq.ler_etiqueta(caminho_ident, nome_arquivo=nome_ident or "")


def registrar(
    caminho_ident: str,
    nome_ident: str | None,
    caminho_material: str,
    nome_material: str | None,
    revenda: str,
    cnpj_rev: str,
    cliente: str,
    codcli: str,
    codcomp: str,
    produto: str,
    usuario: str,
    serial_informado: str = "",
    executar: bool = False,
    leitura: dict | None = None,
    codred: str = "",
) -> dict:
    lida = leitura or eq.ler_etiqueta(caminho_ident, serial_informado)
    serial = lida.get("serial") or ""
    if not serial:
        return {**lida, "preenchidos": [], "divergencias": [], "fotos_guardadas": False}
    linha_equipamento = {**lida["linha"], "CODCOMP": codcomp or "", "CODRED": codred or ""}

    if not executar:
        print(
            f"[DRY-RUN] material -- serial={serial} revenda={revenda}"
            f" cliente={cliente} codcomp={codcomp} codred={codred}"
            f"\n  etiqueta={caminho_ident}\n  material={caminho_material}"
        )
        return {**lida, "preenchidos": [], "divergencias": [], "fotos_guardadas": False}

    arquivo_ident = _copiar(caminho_ident, nome_ident, PREFIXO_IDENT, serial, PASTA_UPLOADS_IDENT)
    arquivo_material = _copiar(caminho_material, nome_material, PREFIXO_MATERIAL, serial, PASTA_UPLOADS_MATERIAL)
    resultado = eq.gravar_etiqueta(linha_equipamento)
    resultado["fotos_guardadas"] = False

    garantir_tabela()
    with obter_engine_comodato().begin() as conexao:
        conexao.execute(
            text(
                f"INSERT INTO {TABELA_FOTO}"
                " (SERIAL, ANEXO, ANEXO_ETIQUETA, REVENDA, CNPJ_REV, CLIENTE, CODCLI,"
                "  CODCOMP, PRODUTO, USUARIO, DATA)"
                " VALUES (:serial, :anexo, :anexo_etiqueta, :revenda, :cnpj_rev, :cliente,"
                "  :codcli, :codcomp, :produto, :usuario, :data)"
            ),
            {
                "serial": serial,
                "anexo": arquivo_material[:255],
                "anexo_etiqueta": arquivo_ident[:255],
                "revenda": (revenda or "")[:50],
                "cnpj_rev": (cnpj_rev or "")[:20],
                "cliente": (cliente or "")[:120],
                "codcli": (codcli or "")[:20],
                "codcomp": (codcomp or "")[:10],
                "produto": (produto or "")[:120],
                "usuario": (usuario or "")[:60],
                "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
    resultado["fotos_guardadas"] = True
    if resultado["situacao"] != "novo":
        logger.info(f"Material {serial} já estava cadastrado ({resultado['situacao']}) -- fotos novas guardadas")
    return resultado
