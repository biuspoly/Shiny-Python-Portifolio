from __future__ import annotations

import os
import re
from datetime import date

import polars as pl
from loguru import logger

from core import acervo, cache, exportar
from core import cfop as tabela_cfop
from core import formato as fmt
from core.config import empresas
from core.config_arquivo import carregar_json

MESES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)
CAMPOS_EMPRESA = (
    "razao",
    "endereco",
    "numero",
    "cep",
    "bairro",
    "municipio",
    "uf",
    "cnpj",
    "ie",
    "im",
    "atividade",
    "natureza_juridica",
)
ACOES = {"cfops": "CFOPs", "pdf": "PDF", "relatorio": "Relatório"}
ACOES_PADRAO = list(ACOES)


def configuracao() -> dict:
    conf = carregar_json("relatorios", {}).get("faturamento") or {}
    return {
        "meses": int(conf.get("meses") or 12),
        "cfops": [str(c) for c in conf.get("cfops") or []],
        "devolucoes": [str(c) for c in conf.get("devolucoes") or []],
    }


def base(cnpj: str) -> pl.DataFrame:
    if not cnpj:
        return pl.DataFrame()
    return cache.filtrado(
        "faturamento", (pl.col("EMITENTE") == cnpj) & (pl.col("CANCELADA") == 0), so=["LIVRO", "MES", "CFOP", "VALOR"]
    )


def meses_com_saida(df: pl.DataFrame) -> list[str]:
    if df.is_empty():
        return []
    return sorted(df.filter(pl.col("LIVRO") == "S")["MES"].unique().to_list(), reverse=True)


def janela(ate: str, meses: int) -> list[str]:
    ano, mes = int(ate[:4]), int(ate[5:7])
    saida = []
    for _ in range(meses):
        saida.append(f"{ano:04d}-{mes:02d}")
        ano, mes = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
    return saida[::-1]


def rotulo_mes(mes: str) -> str:
    return f"{MESES[int(mes[5:7]) - 1]}-{mes[2:4]}"


def opcoes_cfop(df: pl.DataFrame, periodo: list[str], livro: str) -> list[tuple[str, float]]:
    if df.is_empty() or not periodo:
        return []
    somas = (
        df.filter((pl.col("LIVRO") == livro) & pl.col("MES").is_in(periodo))
        .group_by("CFOP")
        .agg(pl.col("VALOR").sum())
        .sort("VALOR", descending=True)
    )
    return [(c, float(v)) for c, v in somas.iter_rows()]


def tabela(df: pl.DataFrame, periodo: list[str], cfops: list[str], devolucoes: list[str]) -> pl.DataFrame:
    meses = pl.DataFrame({"mes": periodo}, schema={"mes": pl.Utf8})
    saida = meses
    if not df.is_empty():
        do_periodo = df.filter(pl.col("MES").is_in(periodo))
        for codigo in cfops:
            soma = (
                do_periodo.filter((pl.col("LIVRO") == "S") & (pl.col("CFOP") == codigo))
                .group_by("MES")
                .agg(pl.col("VALOR").sum().alias(codigo))
                .rename({"MES": "mes"})
            )
            saida = saida.join(soma, on="mes", how="left")
        devolvido = (
            do_periodo.filter((pl.col("LIVRO") == "E") & pl.col("CFOP").is_in(devolucoes))
            .group_by("MES")
            .agg(pl.col("VALOR").sum().alias("devolucoes"))
            .rename({"MES": "mes"})
        )
        saida = saida.join(devolvido, on="mes", how="left")
    for coluna in [*cfops, "devolucoes"]:
        if coluna not in saida.columns:
            saida = saida.with_columns(pl.lit(0.0).alias(coluna))
    saida = saida.with_columns([pl.col(c).fill_null(0.0).cast(pl.Float64) for c in [*cfops, "devolucoes"]])
    vendido = pl.sum_horizontal([pl.col(c) for c in cfops]) if cfops else pl.lit(0.0)
    conta = (vendido - pl.col("devolucoes")).round(2)
    return saida.with_columns(pl.when(conta == 0).then(pl.lit(0.0)).otherwise(conta).alias("faturamento"))


def totais(linhas: pl.DataFrame) -> dict:
    if linhas.is_empty():
        return {"total": 0.0, "media": 0.0, "maior": 0.0, "maior_mes": ""}
    maior = linhas.sort("faturamento", descending=True).row(0, named=True)
    return {
        "total": float(linhas["faturamento"].sum()),
        "media": float(linhas["faturamento"].mean()),
        "maior": float(maior["faturamento"]),
        "maior_mes": maior["mes"] if maior["faturamento"] else "",
    }


def na_tela(linhas: pl.DataFrame, cfops: list[str]) -> pl.DataFrame:
    colunas = [*cfops, "devolucoes", "faturamento"]
    total = linhas.select(pl.lit("Total").alias("mes"), *[pl.col(c).sum() for c in colunas])
    juntas = pl.concat([linhas.select("mes", *colunas), total], how="vertical_relaxed")
    return juntas.select(
        pl.col("mes")
        .map_elements(lambda m: m if m == "Total" else rotulo_mes(m), return_dtype=pl.Utf8)
        .alias("Período"),
        *[pl.col(c).map_elements(fmt.moeda, return_dtype=pl.Utf8).alias(tabela_cfop.rotulo(c)) for c in cfops],
        pl.col("devolucoes")
        .map_elements(lambda v: fmt.moeda(-v) if v else fmt.moeda(0), return_dtype=pl.Utf8)
        .alias("Devoluções"),
        pl.col("faturamento").map_elements(fmt.moeda, return_dtype=pl.Utf8).alias("Faturamento"),
    )


def planilha(linhas: pl.DataFrame, cfops: list[str], nome_empresa: str, colunas: list[str] | None = None) -> bytes:
    return exportar.excel(
        tabela_planilha(linhas, cfops), re.sub(r"[\[\]:*?/\\]", " ", nome_empresa)[:31] or "Faturamento", colunas
    )


def tabela_planilha(linhas: pl.DataFrame, cfops: list[str]) -> pl.DataFrame:
    valores = [*cfops, "devolucoes", "faturamento"]
    total = linhas.select(pl.lit("Total").alias("mes"), *[pl.col(c).sum() for c in valores])
    return pl.concat([linhas.select("mes", *valores), total], how="vertical_relaxed").select(
        pl.col("mes")
        .map_elements(lambda m: m if m == "Total" else rotulo_mes(m), return_dtype=pl.Utf8)
        .alias("Período"),
        *[pl.col(c).round(2).alias(tabela_cfop.rotulo(c)) for c in cfops],
        (-pl.col("devolucoes")).round(2).alias("Devoluções"),
        pl.col("faturamento").round(2).alias("Faturamento"),
    )


def _texto(no, caminho: str) -> str:
    achado = no.xpath(caminho)
    return str(achado[0]).strip() if achado else ""


def endereco_do_xml(xml: bytes, cnpj: str) -> dict:
    from lxml import etree

    raiz = etree.fromstring(xml)
    dest = raiz.xpath("//*[local-name()='dest']")
    if not dest or _texto(dest[0], "./*[local-name()='CNPJ']/text()") != cnpj:
        return {}
    ender = dest[0].xpath("./*[local-name()='enderDest']")
    e = ender[0] if ender else dest[0]
    return {
        "razao": _texto(dest[0], "./*[local-name()='xNome']/text()"),
        "endereco": _texto(e, "./*[local-name()='xLgr']/text()"),
        "numero": _texto(e, "./*[local-name()='nro']/text()"),
        "bairro": _texto(e, "./*[local-name()='xBairro']/text()"),
        "municipio": _texto(e, "./*[local-name()='xMun']/text()"),
        "uf": _texto(e, "./*[local-name()='UF']/text()"),
        "cep": _texto(e, "./*[local-name()='CEP']/text()"),
        "ie": _texto(dest[0], "./*[local-name()='IE']/text()"),
    }


_DO_XML: dict[tuple[str, str], dict] = {}


def dados_empresa(cnpj: str) -> dict:
    dados = {campo: "" for campo in CAMPOS_EMPRESA}
    dados["razao"] = next((e["nome"] for e in empresas() if e["cnpj"] == cnpj), "")
    try:
        notas = cache.filtrado(
            "nfe",
            (pl.col("empresa") == cnpj) & (pl.col("destinatario_cnpj") == cnpj) & pl.col("completa"),
            so=["emissao", "arquivo"],
        )
        if not notas.is_empty():
            arquivo = notas.sort("emissao", descending=True)["arquivo"][0]
            if (cnpj, arquivo) not in _DO_XML:
                _DO_XML[(cnpj, arquivo)] = endereco_do_xml(acervo.ler(arquivo), cnpj)
            dados.update({k: v for k, v in _DO_XML[(cnpj, arquivo)].items() if v})
    except Exception as exc:
        logger.warning(f"Faturamento: endereco de {cnpj} pelo XML -- {exc}")
    do_config = (carregar_json("relatorios", {}).get("empresas") or {}).get(cnpj) or {}
    dados.update({k: str(v) for k, v in do_config.items() if k in CAMPOS_EMPRESA and v})
    dados["cnpj"] = fmt.cnpj(cnpj)
    cep = re.sub(r"\D", "", dados["cep"])
    dados["cep"] = f"{cep[:2]}.{cep[2:5]}-{cep[5:]}" if len(cep) == 8 else dados["cep"]
    return dados


def faltando(dados: dict) -> list[str]:
    nomes = {
        "atividade": "Atividade Econômica",
        "natureza_juridica": "Natureza Jurídica",
        "endereco": "Endereço",
        "ie": "Inscrição Estadual",
    }
    return [rotulo for campo, rotulo in nomes.items() if not dados.get(campo)]


def _pessoa(variavel: str, terceiro: str) -> dict:
    partes = [p.strip() for p in (os.getenv(variavel) or "").split(";")] + ["", "", ""]
    return {"nome": partes[0], "cpf": partes[1], terceiro: partes[2]}


def assinantes(cnpj: str) -> tuple[dict, dict]:
    tecnico = f"FATURAMENTO_TECNICO_{cnpj}" if os.getenv(f"FATURAMENTO_TECNICO_{cnpj}") else "FATURAMENTO_TECNICO"
    return _pessoa(f"FATURAMENTO_RESPONSAVEL_{cnpj}", "rg"), _pessoa(tecnico, "crc")


def data_por_extenso(dia: date) -> str:
    return f"{dia.day} de {MESES[dia.month - 1]} de {dia.year}"
