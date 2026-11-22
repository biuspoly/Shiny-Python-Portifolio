from __future__ import annotations

import json
from collections.abc import Callable, Iterable

import polars as pl
from loguru import logger
from shiny import reactive

CLASSE = "tabela-ordem-valor"

COMUNS: dict[str, tuple[tuple[str, ...], bool]] = {
    "Emissão": (("emissao", "nfe_emissao"), False),
    "Chegou em": (("chegou_em",), False),
    "Lançada em": (("DTE",), False),
    "Emissão da citada": (("emissao_origem",), False),
    "Tentaram enviar em": (("tentativa_em",), False),
    "Última compra": (("ultima",), False),
    "Último documento": (("chegou_em_ultimo", "ultimo_documento"), False),
    "Vence em": (("vence_em",), False),
    "Valor": (("valor", "vprod"), True),
    "Valor da nota": (("nfe_valor", "valor_nota"), True),
    "Valor da citada": (("valor_origem",), True),
    "Valor travado": (("valor",), True),
    "Valor do serviço": (("valor_servico",), True),
    "Valor líquido": (("valor_liquido",), True),
    "Valor no SPED": (("valor_sped",), True),
    "Valor no XML": (("valor_xml",), True),
    "Valor das notas": (("valor",), True),
    "Diferença": (("diferenca",), True),
    "Frete": (("valor_frete", "frete"), True),
    "Frete total": (("frete",), True),
    "Frete rateado": (("frete",), True),
    "Carga": (("valor_carga",), True),
    "Carga total": (("carga",), True),
    "Número": (("numero",), True),
    "NF-e": (("nfe_numero", "numero"), True),
    "Dias": (("dias",), True),
    "Notas": (("notas",), True),
    "Preço": (("preco",), True),
    "Total": (("total",), True),
    "Quantidade": (("quantidade", "qcom"), True),
    "Menor": (("menor",), True),
    "Maior": (("maior",), True),
    "Média ponderada": (("media",), True),
    "Último preço": (("ultimo",), True),
    "Preço anterior": (("anterior", "preco_anterior"), True),
    "Variação (%)": (("variacao",), True),
    "Tentativas": (("tentativas",), True),
    "Consulta SEFAZ": (("consulta",), False),
}


Colunas = dict[str, tuple]


def atributos(colunas: Colunas | None = None) -> dict[str, str]:
    return {"data-ordem-colunas": json.dumps(sorted(COMUNS if colunas is None else colunas), ensure_ascii=False)}


def mapa(colunas_cruas: Iterable[str], colunas: Colunas | None = None) -> dict[str, pl.Expr]:
    existem = set(colunas_cruas)
    saida = {}
    for nome, especificacao in (COMUNS if colunas is None else colunas).items():
        candidatas, como_numero = especificacao[0], especificacao[1]
        crua = next((c for c in candidatas if c in existem), None)
        if crua is not None:
            saida[nome] = pl.col(crua).cast(pl.Float64, strict=False) if como_numero else pl.col(crua)
    return saida


Escolha = tuple[str, bool] | None


def proxima_escolha(atual: Escolha, nome: str, maior_primeiro: bool) -> Escolha:
    if atual is None or atual[0] != nome:
        return (nome, maior_primeiro)
    if atual[1] == maior_primeiro:
        return (nome, not maior_primeiro)
    return None


def ordenar_por(dados: pl.DataFrame, escolha: Escolha, colunas: Colunas | None = None) -> pl.DataFrame:
    if escolha is None or dados.height < 2:
        return dados
    expressao = mapa(dados.columns, colunas).get(escolha[0])
    if expressao is None:
        return dados
    try:
        return dados.sort(expressao, descending=escolha[1], nulls_last=True, maintain_order=True)
    except Exception as exc:
        logger.warning(f'Ordem da tabela: coluna "{escolha[0]}" nao ordenou -- {exc}')
        return dados


class OrdemPorValor:
    def __init__(
        self,
        id_tabela: str,
        input,
        session,
        *,
        ao_mudar: Callable[[], None] | None = None,
        colunas: Colunas | None = None,
    ):
        self.escolha = reactive.value(None, name=f"ordem_{id_tabela}")
        self._id = id_tabela
        self._input = input
        self._session = session
        self._ao_mudar = ao_mudar
        self._colunas = COMUNS if colunas is None else colunas
        self._entrada = f"{id_tabela}_ordem"
        reactive.effect(reactive.event(input[self._entrada])(self._clique))

    async def _clique(self):
        try:
            pedido = self._input[self._entrada]()
            nome = pedido.get("coluna") if isinstance(pedido, dict) else None
            if nome not in self._colunas:
                return
            especificacao = self._colunas[nome]
            nova = proxima_escolha(self.escolha(), nome, especificacao[2] if len(especificacao) > 2 else True)
            self.escolha.set(nova)
            if self._ao_mudar is not None:
                self._ao_mudar()
            await self._session.send_custom_message(
                "tabelaOrdem",
                {"id": self._session.ns(self._id), "coluna": nova[0] if nova else None, "desc": bool(nova and nova[1])},
            )
        except Exception as exc:
            logger.warning(f"Ordem da tabela {self._id}: clique -- {exc}")

    def ordenar(self, dados: pl.DataFrame) -> pl.DataFrame:
        return ordenar_por(dados, self.escolha(), self._colunas)
