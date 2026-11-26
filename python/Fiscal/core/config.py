"""Configuração do portfólio: empresas fictícias (config/empresas.json), sem login nem permissão."""

from core.config_arquivo import carregar_json

NOME_APP = "Acompanhamento Fiscal"
USUARIO_PORTFOLIO = "visitante"
ERP_PADRAO = "ERP"


def _chave(texto: str | None) -> str:
    return " ".join(str(texto or "").upper().split())


def empresas() -> list[dict]:
    return [e for e in carregar_json("empresas", {}).get("empresas", []) if e.get("cnpj")]


def empresas_da_url(revenda: str | None) -> list[dict]:
    todas = empresas()
    if not revenda:
        return todas
    return [e for e in todas if _chave(e.get("revenda")) == _chave(revenda)] or todas


def cnpjs_da_url(revenda: str | None) -> list[str]:
    return [e["cnpj"] for e in empresas_da_url(revenda)]


def erp_da_empresa(empresa: dict) -> str | None:
    return empresa.get("erp") or ERP_PADRAO


def erp_das_empresas(cnpjs) -> str:
    escolhidas = set(cnpjs)
    nomes = [erp for e in empresas() if e["cnpj"] in escolhidas and (erp := erp_da_empresa(e))]
    return "/".join(dict.fromkeys(nomes)) or ERP_PADRAO


def erp_curto(erp: str) -> str:
    return "ERP" if "/" in str(erp or "") else erp


def trocar_o_erp(texto: str, erp: str) -> str:
    return texto.replace(ERP_PADRAO, erp)


def nome_da_empresa(cnpj: str) -> str:
    return next((e["nome"] for e in empresas() if e["cnpj"] == cnpj), cnpj)


def pode(usuario: str | None, funcionalidade: str) -> bool:
    """No original, cada ação tem a sua lista de responsáveis; aqui o visitante pode testar todas."""
    return True
