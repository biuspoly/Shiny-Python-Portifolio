"""Dados públicos de verdade, baixados da internet e guardados em gerador/cache/.

Sem internet, vale o que já estiver no cache; sem cache, o gerador para com a
mensagem de qual fonte faltou.
"""

import json
import urllib.request
from datetime import date, timedelta
from functools import cache
from pathlib import Path

import polars as pl

CACHE = Path(__file__).resolve().parent / "cache"

URL_MUNICIPIOS = "https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/municipios.csv"
URL_MALHA_UF = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/estados/{uf}"
    "?formato=application/vnd.geo%2Bjson&intrarregiao=municipio&qualidade=minima"
)
# Censo 2022, população residente (agregado 4709, variável 93), por município do estado.
URL_POPULACAO_UF = (
    "https://servicodados.ibge.gov.br/api/v3/agregados/4709/periodos/2022/variaveis/93?localidades=N6[N3[{codigo_uf}]]"
)
URL_SGS = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados?formato=json&dataInicial={inicio}&dataFinal={fim}"
)

_CODIGO_UF = {21: "MA", 22: "PI", 23: "CE", 24: "RN"}


def _baixar(url: str, tempo: int = 60) -> bytes:
    pedido = urllib.request.Request(url, headers={"User-Agent": "portifolio-shiny/1.0"})
    with urllib.request.urlopen(pedido, timeout=tempo) as resposta:
        return resposta.read()


def _com_cache(nome: str, url: str) -> bytes:
    arquivo = CACHE / nome
    try:
        conteudo = _baixar(url)
        CACHE.mkdir(exist_ok=True)
        arquivo.write_bytes(conteudo)
        return conteudo
    except Exception as exc:
        if arquivo.exists():
            print(f"  aviso: {nome} sem internet ({exc}), usando o cache")
            return arquivo.read_bytes()
        raise RuntimeError(f"Fonte pública indisponível e sem cache: {url}") from exc


@cache
def municipios() -> pl.DataFrame:
    """Municípios de RN, CE, PI e MA com latitude e longitude."""
    bruto = _com_cache("municipios.csv", URL_MUNICIPIOS)
    return (
        pl.read_csv(bruto)
        .filter(pl.col("codigo_uf").is_in(list(_CODIGO_UF)))
        .with_columns(pl.col("codigo_uf").replace_strict(_CODIGO_UF).alias("uf"))
        .select("codigo_ibge", "nome", "uf", "latitude", "longitude", "capital")
    )


def malha_uf(uf: str) -> dict:
    """GeoJSON dos municípios de um estado (IBGE), para o mapa do Comercial."""
    return json.loads(_com_cache(f"malha_{uf}.json", URL_MALHA_UF.format(uf=uf)))


@cache
def populacao_uf(uf: str) -> dict[int, int]:
    """Código IBGE do município -> população do Censo 2022."""
    codigo_uf = next(c for c, sigla in _CODIGO_UF.items() if sigla == uf)
    bruto = json.loads(_com_cache(f"populacao_{uf}.json", URL_POPULACAO_UF.format(codigo_uf=codigo_uf)))
    return {int(s["localidade"]["id"]): int(s["serie"]["2022"]) for s in bruto[0]["resultados"][0]["series"]}


def serie_bcb(serie: int, nome: str, dias: int = 800) -> pl.DataFrame:
    """Série do SGS do Banco Central (1 = dólar, 432 = Selic meta, 433 = IPCA mensal)."""
    fim = date.today()
    inicio = fim - timedelta(days=dias)
    url = URL_SGS.format(serie=serie, inicio=inicio.strftime("%d/%m/%Y"), fim=fim.strftime("%d/%m/%Y"))
    dados = json.loads(_com_cache(f"sgs_{serie}.json", url))
    return pl.DataFrame(dados).select(
        pl.col("data").str.strptime(pl.Date, "%d/%m/%Y"),
        pl.col("valor").cast(pl.Float64).alias(nome),
    )
