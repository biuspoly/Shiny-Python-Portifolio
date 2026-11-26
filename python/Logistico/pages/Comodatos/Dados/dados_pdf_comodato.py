from __future__ import annotations

import re

from loguru import logger
from sqlalchemy import text

from core import revendas
from core.db import obter_engine_bruto, obter_engine_comodato

INTERVALO_MINIMO_DIAS = 300

_COLUNAS_CADASTRO_REVENDA = ("razao_social", "logradouro", "bairro", "uf", "cep", "numero", "municipio")

_SQL_CEV_COM_CADASTRO = text(
    """
    SELECT c.CNPJ_REV, r.razao_social, r.logradouro, r.bairro, r.uf,
           r.cep, r.numero, r.municipio
    FROM tb_cev c
    LEFT JOIN tb_revendas r ON c.CNPJ_REV = r.CNPJ_REV
    WHERE c.CEV = :cev AND c.CNPJ_REV = :cnpj_rev
    LIMIT 1
    """
)

_SQL_CEV_SIMPLES = text("SELECT c.CNPJ_REV FROM tb_cev c WHERE c.CEV = :cev AND c.CNPJ_REV = :cnpj_rev LIMIT 1")

_SQL_COMODATO = text(
    """
    SELECT s.CLIENTE, s.ENDERECO, s.CONTATO, s.CNPJ, s.PTO_REF, s.DIA_VISIT,
           s.SEQ, s.VEN, s.DATA, s.VENC, s.CEP, s.REVENDA, s.PRODUTO, s.QTD, s.PRECO,
           c.NPED, c.CEV, c.MOT, c.NF, c.SERIE, c.ROMA, c.CODCLI, c.intervalo,
           i.EMAIL_PROP, i.PROPRIETARIO, i.CPF_PROP, i.FONE AS FONE_PROP,
           i.cnpj_rev, i.cgc_cpf
    FROM tb_comod_solicitado s, tb_comodato c, tb_clientes_inad i
    WHERE c.pre_ped  = s.pre_ped
      AND c.codcli   = i.codcli
      AND s.codcomp  = c.codcomp
      AND i.cnpj_rev = :cnpj_rev
      AND c.cnpj_rev = i.cnpj_rev
      AND c.cev      = :cev
    """
)


_SQL_CADASTRO_REVENDA = text(
    """
    SELECT razao_social, logradouro, bairro, uf, cep, numero, municipio
    FROM tb_revendas
    WHERE CNPJ_REV = :cnpj_rev
    LIMIT 1
    """
)


def _sem_ponto_zero(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float):
        return str(int(valor)) if valor.is_integer() else str(valor)
    texto = str(valor).strip()
    if re.fullmatch(r"[-+]?\d*\.?\d+[eE][-+]?\d+", texto):
        try:
            return f"{int(float(texto))}"
        except (ValueError, OverflowError):
            return texto
    return texto.split(".")[0] if re.fullmatch(r"-?\d+\.0+", texto) else texto


def _formatar_cpf(bruto) -> str:
    digitos = "".join(c for c in _sem_ponto_zero(bruto) if c.isdigit())
    if not digitos or set(digitos) == {"0"}:
        return ""
    cpf = digitos.rjust(11, "0")
    return re.sub(r"(\d{3})(\d{3})(\d{3})(\d{2})", r"\1.\2.\3-\4", cpf)


def formatar_documento(bruto) -> str:
    digitos = "".join(c for c in _sem_ponto_zero(bruto) if c.isdigit())
    if not digitos or set(digitos) == {"0"}:
        return ""
    if len(digitos) <= 11:
        return re.sub(r"(\d{3})(\d{3})(\d{3})(\d{2})", r"\1.\2.\3-\4", digitos.rjust(11, "0"))
    if len(digitos) <= 14:
        return re.sub(r"(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})", r"\1.\2.\3/\4-\5", digitos.rjust(14, "0"))
    return digitos


def _consultar(engine, sql, parametros: dict) -> list[dict]:
    with engine.connect() as conexao:
        return [dict(linha) for linha in conexao.execute(sql, parametros).mappings()]


def buscar_dados_pdf(cev: str, cnpj_rev: str) -> dict | None:
    parametros = {"cev": cev, "cnpj_rev": cnpj_rev}
    try:
        revenda_cev = _consultar(obter_engine_bruto(), _SQL_CEV_COM_CADASTRO, parametros)
    except Exception as exc:
        logger.warning(f"PDF do CEV {cev}: tb_revendas sem cadastro completo, seguindo sem endereco -- {exc}")
        revenda_cev = _consultar(obter_engine_bruto(), _SQL_CEV_SIMPLES, parametros)
    if not revenda_cev:
        return None
    cadastro = dict(revenda_cev[0])
    for coluna in _COLUNAS_CADASTRO_REVENDA:
        cadastro.setdefault(coluna, "")

    itens = _consultar(obter_engine_comodato(), _SQL_COMODATO, {"cev": cev, "cnpj_rev": cnpj_rev})
    if not itens:
        return None

    linhas = [
        linha for linha in itens if linha.get("intervalo") is not None and linha["intervalo"] >= INTERVALO_MINIMO_DIAS
    ]
    if not linhas:
        return None

    primeira = linhas[0]
    if not str(primeira.get("PROPRIETARIO") or "").strip():
        return None

    dona = revendas.por_cnpj(cnpj_rev)
    return {
        "cliente": primeira["CLIENTE"],
        "razao_social": cadastro["razao_social"],
        "logradouro": cadastro["logradouro"],
        "numero": cadastro["numero"],
        "bairro": cadastro["bairro"],
        "municipio": cadastro["municipio"],
        "uf": cadastro["uf"],
        "cep": cadastro["cep"],
        "cnpj_rev": cadastro["CNPJ_REV"],
        "cnpj_rev_documento": formatar_documento(cadastro["CNPJ_REV"]),
        "endereco": primeira["ENDERECO"],
        "contato": primeira["CONTATO"],
        "cnpj": formatar_documento(primeira["CNPJ"]),
        "pto_ref": primeira["PTO_REF"],
        "dia_visit": primeira["DIA_VISIT"],
        "seq": primeira["SEQ"],
        "fone": primeira["FONE_PROP"],
        "ven": primeira["VEN"],
        "emissao": primeira["DATA"],
        "vencimento": primeira["VENC"],
        "cep_comodataria": primeira["CEP"],
        "ncev": primeira["CEV"],
        "nf": primeira["NF"],
        "nf_serie": primeira["SERIE"],
        "mot": primeira["MOT"],
        "nped": primeira["NPED"],
        "rom": _sem_ponto_zero(primeira["ROMA"]),
        "nome_revenda": str(primeira.get("REVENDA") or "").strip(),
        "email_revenda": dona.email if dona else "NAO INFORMADO",
        "produtos": linhas,
        "email_proprietario": str(primeira.get("EMAIL_PROP") or "").strip(),
        "proprietario": str(primeira.get("PROPRIETARIO") or "").strip(),
        "cpf_proprietario": _formatar_cpf(primeira.get("CPF_PROP")),
        "codcli": str(primeira.get("CODCLI") or "").strip(),
    }


def cadastro_revenda(cnpj_rev: str) -> dict:
    """Portfólio: endereço fictício da revenda (no original, tb_revendas)."""
    dona = revendas.por_cnpj(cnpj_rev)
    if dona is None:
        return {}
    return {
        "razao_social": f"Distribuidora Fictícia {dona.nome} Ltda",
        "logradouro": "Avenida das Distribuidoras",
        "numero": "1000",
        "bairro": "Distrito Industrial",
        "municipio": dona.nome,
        "uf": dona.uf,
        "cep": "00000-000",
        "CNPJ_REV": dona.cnpj,
    }


def dados_distrato(itens: list[dict], cnpj_rev: str) -> dict:
    primeira = itens[0] if itens else {}
    cadastro = cadastro_revenda(cnpj_rev)
    endereco_revenda = " - ".join(
        parte
        for parte in (
            f"{str(cadastro.get('logradouro') or '').rstrip(', ')}, {cadastro.get('numero') or ''}".strip(", "),
            cadastro.get("bairro") or "",
            cadastro.get("municipio") or "",
            cadastro.get("uf") or "",
        )
        if str(parte).strip()
    ).title()
    return {
        "comodatante": cadastro.get("razao_social") or "",
        "cnpj_comodatante": formatar_documento(cnpj_rev),
        "end_comodatante": endereco_revenda,
        "cep_comodatante": cadastro.get("cep") or "",
        "comodataria": primeira.get("Fantasia") or primeira.get("Razão Social") or "",
        "cnpj_comodataria": formatar_documento(primeira.get("CNPJ_CLI")),
        "end_comodataria": primeira.get("ENDERECO") or "",
        "cep_comodataria": primeira.get("CEP") or "",
        "cidade": cadastro.get("municipio") or "",
        "ncev": _numero_cev(str(primeira.get("CEV") or "")),
        "codcli": str(primeira.get("Cliente") or "").strip(),
        "itens": [
            {
                "codigo": str(item.get("CODCOMP") or ""),
                "descricao": str(item.get("Produto") or ""),
                "qtd": item.get("Qtd"),
            }
            for item in itens
        ],
    }


def _numero_cev(cev: str) -> str:
    return cev.rsplit("-", 1)[-1].strip()
