import re
import shutil
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from core.db import obter_engine_comodato

PASTA_APP = Path(__file__).parent.parent.parent.parent
PASTA_UPLOADS_PDV = PASTA_APP / "uploads" / "comodatos" / "pdv"
PASTA_UPLOADS_CEV = PASTA_APP / "uploads" / "comodatos" / "comodato"
PASTA_UPLOADS_CANHOTO = PASTA_APP / "uploads" / "comodatos" / "canhoto"
for _pasta in (PASTA_UPLOADS_PDV, PASTA_UPLOADS_CEV, PASTA_UPLOADS_CANHOTO):
    _pasta.mkdir(parents=True, exist_ok=True)


FORMATO_DATA_ANEXO = "%Y-%m-%d %H:%M:%S"
_LIMITE_PADRAO_DATA = 15


@lru_cache(maxsize=8)
def _limite_coluna(tabela: str, coluna: str) -> int:
    from sqlalchemy import text

    try:
        with obter_engine_comodato().connect() as conexao:
            limite = conexao.execute(
                text(
                    "SELECT CHARACTER_MAXIMUM_LENGTH FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() AND table_name = :tabela AND column_name = :coluna"
                ),
                {"tabela": tabela, "coluna": coluna},
            ).scalar()
        return int(limite) if limite else _LIMITE_PADRAO_DATA
    except Exception:
        return _LIMITE_PADRAO_DATA


def data_anexo(agora: datetime | None = None) -> str:
    texto = (agora or datetime.now()).strftime(FORMATO_DATA_ANEXO)
    return texto[: _limite_coluna("tb_anexos_cev", "dataI")]


def _sanitizar_nome_arquivo(nome: str) -> str:
    return re.sub(r"[^\w.\-]", "_", nome)


TABELA_DISTRATO = "tb_comod_distrato"


def _garantir_tabela_distrato(conexao) -> None:
    from sqlalchemy import text

    conexao.execute(
        text(f"""
        CREATE TABLE IF NOT EXISTS {TABELA_DISTRATO} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            CNPJ_REV VARCHAR(20) NOT NULL,
            CEV VARCHAR(60) NOT NULL,
            ARQUIVO VARCHAR(255) NOT NULL,
            USUARIO VARCHAR(60),
            DATA VARCHAR(8),
            HORA VARCHAR(8),
            UNIQUE KEY uq_comod_distrato (CNPJ_REV, CEV)
        )
    """)
    )


def registrar_distrato(cnpj_rev: str, cev: str, arquivo: str, usuario: str, executar: bool = False) -> None:
    return None


LIMITE_NOME_ARQUIVO = 50


def anexos_comod(
    caminho_pdv: str | None,
    caminho_cev: str | None,
    caminho_canhoto: str | None,
    codcli: str,
    ncev: str,
    cnpj_emp: str,
    nome_pdv: str | None = None,
    nome_cev: str | None = None,
    nome_canhoto: str | None = None,
) -> dict[str, str | None]:
    resultado: dict[str, str | None] = {"PDV": None, "CEV": None, "CANHOTO": None}

    for chave, origem, nome_original, pasta in (
        ("PDV", caminho_pdv, nome_pdv, PASTA_UPLOADS_PDV),
        ("CEV", caminho_cev, nome_cev, PASTA_UPLOADS_CEV),
        ("CANHOTO", caminho_canhoto, nome_canhoto, PASTA_UPLOADS_CANHOTO),
    ):
        if not origem:
            continue
        nome_arquivo = (
            f"{chave}_{cnpj_emp}_{ncev}_{codcli}_{_sanitizar_nome_arquivo(nome_original or Path(origem).name)}"
        )
        destino = pasta / nome_arquivo
        shutil.copy(origem, destino)
        resultado[chave] = str(destino.resolve())

    return resultado


def caminho_para_url(caminho: str) -> str:
    nome = Path(caminho).name
    if nome.startswith("PDV_"):
        subpasta = "pdv"
    elif nome.startswith("CEV_"):
        subpasta = "comodato"
    else:
        subpasta = "canhoto"
    return f"uploads/comodatos/{subpasta}/{nome}"


_PREFIXOS_NOME = ("PDV_", "CEV_", "CANHOTO_")

SEM_ANEXO = {"", "na", "none", "nan", "null", "<na>"}


def url_anexo(caminho) -> str:
    if caminho is None:
        return ""
    texto = str(caminho).strip().replace("\\", "/")
    if texto.lower() in SEM_ANEXO:
        return ""
    texto = texto.replace(".PDF", ".pdf")

    nome = texto.rsplit("/", 1)[-1]
    for prefixo in _PREFIXOS_NOME:
        if prefixo in nome:
            nome = nome[nome.index(prefixo) :]
            break
    else:
        return ""

    return quote(caminho_para_url(nome), safe="/")


def tem_anexo(caminho) -> bool:
    texto = str(caminho or "").strip()
    return bool(texto) and texto.lower() not in SEM_ANEXO


def situacao_do_cev(anexos_finais: dict[str, str | None], exige_pdv: bool) -> str:
    completo = tem_anexo(anexos_finais.get("anexo2")) and tem_anexo(anexos_finais.get("anexo3"))
    if exige_pdv:
        completo = completo and tem_anexo(anexos_finais.get("anexo1"))
    return "A" if completo else "P"


def coloca_anexo_bd(
    ncev: str,
    caminho_pdv: str | None,
    caminho_cev: str | None,
    caminho_canhoto: str | None,
    cnpj_emp: str,
    usuario: str,
    codcli: str,
    nf: str,
    executar: bool = False,
    exige_pdv: bool = False,
) -> None:
    """Portfólio: grava os anexos nas linhas do CEV do .parquet (no original, tb_anexos_cev), com a
    situação decidida pelos anexos finais -- os que já estavam mais os que vieram."""
    import polars as pl

    from . import banco_memoria as bm

    vindos = {
        coluna: caminho
        for coluna, caminho in (("anexo1", caminho_pdv), ("anexo2", caminho_cev), ("anexo3", caminho_canhoto))
        if tem_anexo(caminho)
    }
    for tabela, col_cnpj in (
        ("comod_geral_bruto", "cnpj"),
        ("clientes_inadimplentes_base_bruto", "cnpj_rev"),
        ("saldo_comodatos_geral_bruto", "cnpj_rev"),
    ):
        base = bm.ler(tabela)
        if base.height == 0 or "CEV" not in base.columns or col_cnpj not in base.columns:
            continue
        do_cev = (pl.col(col_cnpj).cast(pl.Utf8) == str(cnpj_emp)) & (
            pl.col("CEV").cast(pl.Utf8).str.replace(r"^.* - ", "").str.strip_chars() == str(ncev)
        )
        if not base.filter(do_cev).height:
            continue
        atuais = base.filter(do_cev).row(0, named=True)
        finais = {c: vindos.get(c, atuais.get(c)) for c in ("anexo1", "anexo2", "anexo3")}
        mudar = dict(vindos)
        mudar["situacao"] = situacao_do_cev(finais, exige_pdv)
        mudar["Usuario"] = usuario
        mudar["dataI"] = data_anexo()
        base = base.with_columns(
            [
                pl.when(do_cev).then(pl.lit(v, dtype=pl.Utf8)).otherwise(pl.col(c).cast(pl.Utf8)).alias(c)
                for c, v in mudar.items()
                if c in base.columns
            ]
        )
        bm.gravar(tabela, base)
