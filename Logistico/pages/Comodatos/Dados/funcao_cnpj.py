import requests
from loguru import logger

TIMEOUT_SEGUNDOS = 10


def _socios_brasilapi(cnpj: str) -> list[str] | str | None:
    resposta = requests.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}", timeout=TIMEOUT_SEGUNDOS)
    if resposta.status_code != 200:
        return None
    dados = resposta.json()
    natureza = dados.get("natureza_juridica") or ""
    if "INDIVIDUAL" in natureza.upper():
        return dados.get("razao_social")
    return [socio.get("nome_socio") for socio in dados.get("qsa") or []]


def _socios_kitana(cnpj: str) -> list[str] | str | None:
    resposta = requests.get(f"https://kitana.opencnpj.com/cnpj/{cnpj}", timeout=TIMEOUT_SEGUNDOS)
    if resposta.status_code != 200:
        return None
    dados = (resposta.json() or {}).get("data") or {}
    natureza = dados.get("naturezaJuridica") or ""
    if "INDIVIDUAL" in natureza.upper():
        return dados.get("razaoSocial")
    return [socio.get("nomeSocio") for socio in dados.get("socios") or []]


def _socios_receitaws(cnpj: str) -> list[str] | str | None:
    resposta = requests.get(f"https://receitaws.com.br/v1/cnpj/{cnpj}", timeout=TIMEOUT_SEGUNDOS)
    if resposta.status_code != 200:
        return None
    dados = resposta.json()
    natureza = dados.get("natureza_juridica") or ""
    if "INDIVIDUAL" in natureza.upper():
        return dados.get("nome")
    return [socio.get("nome") for socio in dados.get("qsa") or []]


def dados_cnpj(cnpj: str) -> list[str] | str:
    for consulta in (_socios_brasilapi, _socios_kitana, _socios_receitaws):
        try:
            resultado = consulta(cnpj)
        except Exception:
            logger.warning(f"Falha ao consultar CNPJ {cnpj} via {consulta.__name__}")
            resultado = None
        if resultado is not None:
            return resultado
    return "Dados invalidos"
