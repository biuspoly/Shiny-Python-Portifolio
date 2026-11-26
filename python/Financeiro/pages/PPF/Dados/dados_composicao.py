import json
import re
import unicodedata
from datetime import date
from pathlib import Path

import cachetools
import polars as pl

from core import composicao_manual as cm
from core import manual_arquivo, pastas_da_sessao, virada
from core.atualizacao import obter_atualizacao
from core.compat import ler_parquet  # noqa: E402
from core.config import REVENDAS_POR_GRUPO, chave_revenda
from core.config_arquivo import carregar_json
from core.id_titulo import base_do
from core.performance import medir_tempo

from .dados_ppf import _carregar, _estado_das_viradas, _vinculos_da_rede, dados_manuais, filtrar_por_revenda

PASTA_PARQUET = Path(__file__).parents[3] / "data" / "bd_financeiro"
ARQUIVO = "composicao"


@medir_tempo(pagina="PPF")
def composicao() -> pl.DataFrame:
    return _carregar(ARQUIVO)


ARQUIVO_RETRATO = "composicao_snapshot"
ARQUIVO_RETRATO_ANTIGO = "composicao_snapshot_antigo"
ROTULOS_ANTIGOS = {"Depósito Brinks antes das 16:00h": "brinks_antes_16", "Saldo liberado": "saldo_liberado"}
COLUNAS_DA_COMPOSICAO = (
    "CNPJ_REV",
    "REVENDA",
    "DATA_REFERENCIA",
    "ORDEM",
    "CHAVE",
    "ITEM",
    "CATEGORIA",
    "NATUREZA",
    "BANCO",
    "VALOR",
    "MOTIVO",
    "AVISO_REVENDA",
)
_cache_retrato = cachetools.LRUCache(maxsize=8)


def composicao_do_retrato(dia: date) -> pl.DataFrame:
    caminhos = [PASTA_PARQUET / f"{a}.parquet" for a in (ARQUIVO_RETRATO, ARQUIVO_RETRATO_ANTIGO)]
    chave = (dia, *(c.stat().st_mtime_ns if c.is_file() else 0 for c in caminhos), _estado_das_viradas())
    if chave in _cache_retrato:
        return _cache_retrato[chave]
    daqui = antigo = pl.DataFrame()
    if caminhos[0].is_file():
        daqui = ler_parquet(caminhos[0]).lazy().filter(pl.col("DATA_SNAPSHOT").cast(pl.Date) == dia).collect()
    if caminhos[1].is_file():
        antigo = ler_parquet(caminhos[1]).lazy().filter(pl.col("data_snapshot").cast(pl.Date) == dia).collect()
    daqui, antigo = virada.preferir_retrato_antigo(daqui, antigo, "DATA_SNAPSHOT", "data_snapshot")
    partes = []
    if not daqui.is_empty():
        partes.append(
            daqui.select([pl.col(c) if c in daqui.columns else pl.lit(None).alias(c) for c in COLUNAS_DA_COMPOSICAO])
        )
    if not antigo.is_empty():
        convertido = _do_retrato_antigo(antigo, dia)
        if not convertido.is_empty():
            partes.append(convertido)
    saida = pl.concat(partes, how="vertical_relaxed") if partes else pl.DataFrame()
    _cache_retrato[chave] = saida
    return saida


def _do_retrato_antigo(largo: pl.DataFrame, dia: date) -> pl.DataFrame:
    from core import revendas as cadastro_revendas

    catalogo = _catalogo()
    itens = catalogo.get("itens", [])
    bancos = [b["chave"] for b in catalogo.get("bancos", []) if b["chave"] in largo.columns]
    if not bancos or "composicao_financeira" not in largo.columns:
        return pl.DataFrame()
    mapa = pl.DataFrame(
        {
            "composicao_financeira": [i["rotulo"] for i in itens] + list(ROTULOS_ANTIGOS),
            "CHAVE": [i["chave"] for i in itens] + list(ROTULOS_ANTIGOS.values()),
        }
    )
    dados_item = pl.DataFrame(
        {
            "CHAVE": [i["chave"] for i in itens],
            "ORDEM": list(range(1, len(itens) + 1)),
            "ITEM": [i["rotulo"] for i in itens],
            "CATEGORIA": [i["categoria"] for i in itens],
            "NATUREZA": [i["natureza"] for i in itens],
        }
    )
    longo = (
        largo.with_columns(
            pl.col("composicao_financeira").cast(pl.Utf8).str.strip_chars(), pl.col("REVENDA").cast(pl.Utf8)
        )
        .join(mapa, on="composicao_financeira", how="inner")
        .unpivot(index=["REVENDA", "CHAVE"], on=bancos, variable_name="BANCO", value_name="VALOR")
        .with_columns(pl.col("VALOR").cast(pl.Float64, strict=False))
    )
    atual = composicao()
    de_hoje = (
        atual.select("REVENDA", "BANCO").unique()
        if not atual.is_empty()
        else pl.DataFrame(schema={"REVENDA": pl.Utf8, "BANCO": pl.Utf8})
    )
    com_valor = (
        longo.group_by(["REVENDA", "BANCO"])
        .agg(((pl.col("VALOR").fill_null(0.0).abs()) > 0.005).any().alias("_tem"))
        .filter(pl.col("_tem"))
        .drop("_tem")
    )
    longo = longo.join(
        pl.concat([com_valor, de_hoje], how="vertical_relaxed").unique(), on=["REVENDA", "BANCO"], how="semi"
    )
    if longo.is_empty():
        return pl.DataFrame()
    cnpjs = pl.DataFrame(
        {"REVENDA": longo["REVENDA"].unique().to_list()},
        schema={"REVENDA": pl.Utf8},
    ).with_columns(
        pl.col("REVENDA").map_elements(cadastro_revendas.cnpj_da_revenda, return_dtype=pl.Utf8).alias("CNPJ_REV")
    )
    return (
        longo.join(dados_item, on="CHAVE", how="left")
        .join(cnpjs, on="REVENDA", how="left")
        .with_columns(
            pl.lit(dia).alias("DATA_REFERENCIA"),
            pl.lit("retrato do app antigo").alias("MOTIVO"),
            pl.lit(None, dtype=pl.Utf8).alias("AVISO_REVENDA"),
        )
        .select(list(COLUNAS_DA_COMPOSICAO))
        .sort(["REVENDA", "ORDEM", "BANCO"])
    )


def _catalogo() -> dict:
    return carregar_json("composicao_financeira") or {}


def _sufixos_da_revenda(revenda: str | None) -> dict:
    from core.config import chave_revenda

    todos = _catalogo().get("sufixo_conta_por_revenda") or {}
    procurada = chave_revenda(revenda)
    for nome, sufixos in todos.items():
        if chave_revenda(nome) == procurada:
            return sufixos or {}
    return {}


def rotulo_banco(chave_banco: str, revenda: str | None) -> str:
    catalogo = _catalogo()
    rotulos = {b["chave"]: b["rotulo"] for b in catalogo.get("bancos", [])}
    base = rotulos.get(chave_banco, chave_banco)
    sufixo = _sufixos_da_revenda(revenda).get(chave_banco)
    return f"{base} · {sufixo}" if sufixo else base


def chave_do_rotulo(rotulo: str | None, revenda: str | None) -> str | None:
    if not rotulo:
        return None
    alvo = str(rotulo).strip().casefold()
    catalogo = _catalogo()
    for banco in catalogo.get("bancos", []):
        chave = banco["chave"]
        candidatos = (chave, banco.get("rotulo") or "", rotulo_banco(chave, revenda))
        if alvo in {str(c).strip().casefold() for c in candidatos}:
            return chave
    return None


def da_revenda(base: pl.DataFrame, revenda: str | None) -> pl.DataFrame:
    if base.is_empty() or "REVENDA" not in base.columns:
        return base
    return filtrar_por_revenda(base, revenda)


ITEM_SALDO_LIBERADO = "saldo_liberado"
ITEM_SALDO_FINAL = "saldo_final_liberado"
ITEM_SALDO_ESPECIAL = "saldo_uso_especial"

CHAVE_CAIXA = "caixa_999"


def rotulo_do_item(chave: str, padrao: str | None = None) -> str:
    for item in _catalogo().get("itens", []):
        if item.get("chave") == chave:
            return item.get("rotulo") or padrao or chave
    return padrao or chave


def chave_do_item(rotulo: str | None) -> str | None:
    if not rotulo:
        return None

    def _normal(texto):
        sem = unicodedata.normalize("NFKD", str(texto or ""))
        return "".join(c for c in sem if not unicodedata.combining(c)).strip().casefold()

    alvo = _normal(rotulo)
    for item in _catalogo().get("itens", []):
        nomes = (item.get("chave"), item.get("rotulo"), item.get("rotulo_anterior"))
        if any(n and _normal(n) == alvo for n in nomes):
            return item.get("chave")
    return None


def destinos_extra_pagamento(revenda: str | None = None) -> list[str]:
    catalogo = _catalogo()
    destinos = list(catalogo.get("destinos_extra_pagamento") or [])
    for nome, extras in (catalogo.get("destinos_extra_por_revenda") or {}).items():
        if revenda and chave_revenda(nome) == chave_revenda(revenda):
            destinos += [extra for extra in extras or [] if extra not in destinos]
    return destinos


def icones_dos_destinos() -> dict[str, str]:
    return {
        str(nome): str(caminho)
        for nome, caminho in (_catalogo().get("icone_do_destino") or {}).items()
        if not str(nome).startswith("_") and caminho
    }


def icone_do_destino(banco: str | None, bandeira: str | None = None) -> str | None:
    icones = {nome.strip().casefold(): caminho for nome, caminho in icones_com_a_bandeira(bandeira).items()}
    return icones.get(str(banco or "").strip().casefold())


def _bandeiras() -> dict:
    return _catalogo().get("bandeiras") or {}


def icone_da_bandeira(bandeira: str | None) -> str | None:
    return (_bandeiras().get("icones") or {}).get(str(bandeira or ""))


def icones_com_a_bandeira(bandeira: str | None) -> dict[str, str]:
    icones = icones_dos_destinos()
    desenho = icone_da_bandeira(bandeira)
    if not desenho:
        return icones
    com_bandeira = {str(d).strip().casefold() for d in _bandeiras().get("destinos") or []}
    return {nome: desenho if nome.strip().casefold() in com_bandeira else caminho for nome, caminho in icones.items()}


def _pedacos_do_cartao(caminho: str | None) -> list[set[str]]:
    pedacos = []
    for parte in reversed(re.split(r"[\\/]", str(caminho or ""))[-3:]):
        sem_acento = "".join(c for c in unicodedata.normalize("NFKD", parte) if not unicodedata.combining(c)).upper()
        termos = set(re.findall(r"[A-Z]+", sem_acento))
        if termos & {"CARTAO", "CARTOES"}:
            pedacos.append(termos)
    return pedacos


def do_cartao(caminho: str | None) -> bool:
    return bool(_pedacos_do_cartao(caminho))


def bandeira_do_caminho(caminho: str | None) -> str | None:
    palavras = {
        bandeira: {str(p).upper() for p in nomes} for bandeira, nomes in (_bandeiras().get("palavras") or {}).items()
    }
    for termos in _pedacos_do_cartao(caminho):
        for bandeira, nomes in palavras.items():
            if termos & nomes:
                return bandeira
    return None


_cache_cartoes: dict = {}


def _cartoes_da_rede() -> dict[str, str | None]:
    chave, base = _vinculos_da_rede()
    if base.is_empty() or not {"id_unico", "caminho"} <= set(base.columns):
        return {}
    chave = (chave, json.dumps(_bandeiras(), sort_keys=True, ensure_ascii=False))
    if chave not in _cache_cartoes:
        com_cart = base.filter(pl.col("caminho").cast(pl.Utf8).str.contains(r"(?i)cart[aãõ]"))
        saida: dict[str, str | None] = {}
        for ident, caminho in zip(com_cart["id_unico"].to_list(), com_cart["caminho"].to_list()):
            if ident and do_cartao(caminho):
                saida[ident] = saida.get(ident) or bandeira_do_caminho(caminho)
        _cache_cartoes.clear()
        _cache_cartoes[chave] = saida
    return _cache_cartoes[chave]


def bandeiras_da_rede() -> dict[str, str]:
    return {ident: bandeira for ident, bandeira in _cartoes_da_rede().items() if bandeira}


def titulos_do_cartao() -> set[str]:
    return set(_cartoes_da_rede())


def banco_do_cartao(ident: str | None, bancos, do_cartao_ids: set[str]) -> str | None:
    if not ident or base_do(ident) not in do_cartao_ids:
        return None
    return next((destino for destino in _bandeiras().get("destinos") or [] if destino in bancos), None)


def bancos_presentes(base: pl.DataFrame) -> list[str]:
    if base.is_empty() or "BANCO" not in base.columns:
        return []

    visiveis = {CHAVE_CAIXA} if CHAVE_CAIXA in set(base["BANCO"].unique().to_list()) else set()
    try:
        decisivos = base.filter(
            pl.col("CHAVE").is_in([ITEM_SALDO_FINAL, ITEM_SALDO_ESPECIAL])
            & pl.col("VALOR").is_not_null()
            & (pl.col("VALOR") != 0)
        )
        visiveis |= set(decisivos["BANCO"].unique().to_list())
        sem_extrato = base.filter((pl.col("CHAVE") == ITEM_SALDO_LIBERADO) & pl.col("VALOR").is_null())
        visiveis |= sem_as_so_com_saldo(sem_extrato)
    except Exception as exc:
        print(f"Composicao: nao deu pra aplicar a regra de banco visivel -- {exc}")
        visiveis = set(base["BANCO"].unique().to_list())

    return na_ordem_do_catalogo(visiveis)


def sem_as_so_com_saldo(linhas: pl.DataFrame) -> set[str]:
    rotulo_para_chave = {b["rotulo"]: b["chave"] for b in _catalogo().get("bancos", [])}
    so_com_saldo = {
        (chave_revenda(c.get("revenda")), rotulo_para_chave.get(c.get("banco_contabil")))
        for c in (carregar_json("contas_bancarias") or {}).get("contas", [])
        if c.get("so_com_extrato")
    }
    if so_com_saldo and "REVENDA" in linhas.columns:
        return {
            banco
            for revenda, banco in linhas.select("REVENDA", "BANCO").unique().iter_rows()
            if (chave_revenda(revenda), banco) not in so_com_saldo
        }
    return set(linhas["BANCO"].unique().to_list())


def na_ordem_do_catalogo(bancos: set[str]) -> list[str]:
    ordem = [b["chave"] for b in _catalogo().get("bancos", [])]
    conhecidos = [c for c in ordem if c in bancos]
    novos = sorted(bancos - set(ordem))
    return conhecidos + novos


def bancos_para_lancar(base: pl.DataFrame) -> list[str]:
    presentes = bancos_presentes(base)
    if base.is_empty() or "BANCO" not in base.columns:
        return presentes
    try:
        com_extrato = base.filter((pl.col("CHAVE") == ITEM_SALDO_LIBERADO) & pl.col("VALOR").is_not_null())
        zerados = sem_as_so_com_saldo(com_extrato)
    except Exception as exc:
        print(f"Composicao: nao deu pra achar as contas com extrato -- {exc}")
        return presentes
    return na_ordem_do_catalogo(set(presentes) | zerados)


def data_referencia(base: pl.DataFrame) -> date | None:
    if base.is_empty() or "DATA_REFERENCIA" not in base.columns:
        return None
    return base["DATA_REFERENCIA"].max()


ITENS_OCULTOS = {"estoque_do_dia"}


def _linha_trocada(parte: pl.DataFrame) -> set[str]:
    if "REVENDA" not in parte.columns or parte.is_empty():
        return {"saque"}
    com_saque = {chave_revenda(r) for r in (_catalogo().get("revendas_saque_no_lugar_do_brinks") or [])}
    nomes = {chave_revenda(r) for r in parte["REVENDA"].drop_nulls().unique().to_list()}
    if nomes and nomes <= com_saque:
        return {"brinks_apos_16"}
    if not (nomes & com_saque):
        return {"saque"}
    return set()


def escopo_unico(parte: pl.DataFrame) -> bool:
    if parte.is_empty() or "REVENDA" not in parte.columns:
        return True
    return parte["REVENDA"].n_unique() <= 1


def eh_grupo(revenda: str | None) -> bool:
    return bool(revenda) and revenda.strip().upper() in REVENDAS_POR_GRUPO


def consolidar_grupo(parte: pl.DataFrame) -> pl.DataFrame:
    if parte.is_empty() or "REVENDA" not in parte.columns:
        return parte
    chaves = [c for c in ("ORDEM", "ITEM", "NATUREZA", "CHAVE", "BANCO") if c in parte.columns]
    junto = parte.group_by(chaves).agg(
        pl.when(pl.col("VALOR").is_not_null().any()).then(pl.col("VALOR").sum()).otherwise(None).alias("VALOR"),
        pl.col("VALOR").is_not_null().sum().alias("_COM_VALOR"),
        pl.col("REVENDA").n_unique().alias("_REVENDAS"),
    )
    junto = junto.with_columns(
        pl.when(pl.col("_COM_VALOR") == 0)
        .then(pl.lit("nenhuma revenda do grupo tem valor"))
        .otherwise(
            pl.format(
                "soma de {} de {} revendas do grupo",
                pl.col("_COM_VALOR"),
                pl.col("_REVENDAS"),
            )
        )
        .alias("MOTIVO"),
        pl.lit(None, dtype=pl.Utf8).alias("REVENDA"),
    ).drop("_COM_VALOR", "_REVENDAS")
    return junto.sort("ORDEM") if "ORDEM" in junto.columns else junto


def versao_dados_manuais() -> int:
    alvo = manual_arquivo.caminho("dados_manuais_fatias")
    return alvo.stat().st_mtime_ns if alvo.exists() else 0


_COLUNAS_DA_CONTA = {
    "revenda": pl.Utf8,
    "banco": pl.Utf8,
    "data": pl.Date,
    "destino_transf": pl.Utf8,
    "entrada_saida": pl.Utf8,
    "revenda_destino": pl.Utf8,
    **{
        c: pl.Float64
        for c in (
            "transferencia_bancos",
            "adiantamento_romaneios",
            "devolucao_emprestimos",
            "brinks_antes_16",
            "romaneio_pendente_encerrado",
            "credito_mar_utilizado",
            "transferencia_revendas",
        )
    },
}


def _para_a_conta(base: pl.DataFrame) -> pl.DataFrame:
    if "REVENDA" in base.columns and "revenda" not in base.columns:
        base = base.rename({"REVENDA": "revenda"})
    return base.select(
        [
            pl.col(c).cast(t, strict=False) if c in base.columns else pl.lit(None, dtype=t).alias(c)
            for c, t in _COLUNAS_DA_CONTA.items()
        ]
    )


def ajuste_dos_dados_manuais(base: pl.DataFrame, revenda: str | None) -> dict[tuple[str, str], float]:
    parte = da_revenda(base, revenda)
    if parte.is_empty():
        return {}
    fatias = manual_arquivo.ler("dados_manuais_fatias")
    if fatias.is_empty():
        return {}
    categoria_de = {i["chave"]: i["categoria"] for i in _catalogo().get("itens", [])}
    antes = None
    total: dict[tuple[str, str], float] = {}
    for (nome, cnpj), da_matriz in parte.group_by(["REVENDA", "CNPJ_REV"]):
        feita = obter_atualizacao(pastas_da_sessao.pasta_dos_carimbos(PASTA_PARQUET), ARQUIVO, cnpj=cnpj)
        dia = da_matriz["DATA_REFERENCIA"].max()
        novas = fatias.filter((pl.col("data") == dia) & (pl.col("gravado_em") > feita if feita else pl.lit(True)))
        if novas.is_empty():
            continue
        if antes is None:
            antes = _para_a_conta(dados_manuais())
        alvo = list({str(r).strip().casefold() for r in novas["revenda"]})
        da_fatia = pl.col("revenda").str.strip_chars().str.to_lowercase().is_in(alvo) & (pl.col("data") == dia)
        da_tela = _para_a_conta(manual_arquivo.ler("dados_manuais")).filter(da_fatia)
        depois = pl.concat([antes.filter(~da_fatia), da_tela], how="vertical_relaxed")
        bancos = da_matriz["BANCO"].unique().to_list()
        for celula, valor in cm.diferenca(antes, depois, nome, dia, bancos, categoria_de).items():
            total[celula] = total.get(celula, 0.0) + valor
    return total


def matriz(base: pl.DataFrame, revenda: str | None) -> tuple[pl.DataFrame, list[str], list[str]]:
    parte = da_revenda(base, revenda)
    if parte.is_empty():
        return pl.DataFrame(), [], []

    bancos = bancos_para_lancar(parte)
    if not bancos:
        return pl.DataFrame(), [], []

    ocultos = ITENS_OCULTOS | _linha_trocada(parte)
    if "CHAVE" in parte.columns and ocultos:
        parte = parte.filter(~pl.col("CHAVE").is_in(list(ocultos)))
        if parte.is_empty():
            return pl.DataFrame(), [], []

    if not escopo_unico(parte):
        if not eh_grupo(revenda):
            return pl.DataFrame(), [], []
        parte = consolidar_grupo(parte)

    largo = parte.pivot(on="BANCO", index=["ORDEM", "ITEM", "NATUREZA", "CHAVE"], values="VALOR")
    largo = largo.sort("ORDEM")
    naturezas = largo["NATUREZA"].to_list()
    chaves = largo["CHAVE"].to_list()

    colunas = [pl.col("ITEM").alias("COMPOSIÇÃO FINANCEIRA")]
    for banco in bancos:
        if banco in largo.columns:
            colunas.append(pl.col(banco).alias(rotulo_banco(banco, revenda).upper()))
    return largo.select(colunas), naturezas, chaves
