import functools
import json
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import polars as pl

from core import manual_arquivo
from core.cartoes_banco import ler_reais
from core.id_titulo import base_do, eh_parte

SUFIXO_PARTE = r"(?:_clone\d*)+$"


def documento_normalizado(texto: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(texto or "").strip().upper())


def valor_pago_pendente(
    valor_original: float, valor_pago: float | None, juros: float, pagou: str, desconto_ate: float = 0.0
) -> float:
    if (pagou or "").strip().lower() == "sim":
        return float(valor_pago or 0.0)
    try:
        valor_original = float(valor_original or 0.0)
        pago = float(valor_pago or 0.0)
        juros = float(juros or 0.0)
    except (TypeError, ValueError):
        return float(valor_pago or 0.0)
    if valor_original <= 0 or abs(juros) > 0.0001:
        return pago
    if pago > 0 and 0 < round(valor_original - pago, 2) <= desconto_ate + 0.0001:
        return pago
    if pago <= 0 or abs(pago - valor_original) < 1:
        return valor_original
    return pago


def valor_pago_exibido(valor_original, valor_pago, juros, pagou, desconto_ate: float = 0.0) -> float | None:
    if valor_pago is None:
        return valor_original
    if valor_original is None:
        return valor_pago
    return valor_pago_pendente(valor_original, valor_pago, juros, str(pagou or ""), desconto_ate)


@functools.lru_cache(maxsize=4)
def _feriados(ano: int) -> frozenset:
    try:
        import holidays

        return frozenset(holidays.Brazil(years=[ano - 1, ano]))
    except Exception:
        return frozenset()


def dia_util_anterior(hoje: date) -> date:
    feriados, dia = _feriados(hoje.year), hoje - timedelta(days=1)
    while dia.weekday() >= 5 or dia in feriados:
        dia -= timedelta(days=1)
    return dia


def vencimentos(dias: list[date | None], hoje: date) -> tuple[list[int], list[int]]:
    como_hoje = datas_de_hoje(hoje)
    vence_hoje, vencidas = [], []
    for posicao, dia in enumerate(dias):
        if dia is None:
            continue
        if dia in como_hoje:
            vence_hoje.append(posicao)
        elif dia < hoje:
            vencidas.append(posicao)
    return vence_hoje, vencidas


def entrada_manual_em_azul(entrada_manual: bool, vence: str | None) -> bool:
    return entrada_manual and vence in ("hoje", "vencida")


_COLUNAS_DO_TITULO = (
    "REVENDA",
    "data_vencimento",
    "num_doc",
    "num_doc_normalizado",
    "tipo_doc",
    "cnpj",
    "valor_original",
    "razao_social",
    "descricao_despesa",
    "id_unico",
)
_COLUNAS_DA_MARCA = (
    "pagar",
    "pagou",
    "valor_pago",
    "juros",
    "banco",
    "auditoria",
    "conselho",
    "data_pagamento",
    "entrada_manual",
)
COLUNAS_PAGO_NO_CONTROL = ("pago_no_control", "valor_pago_no_control", "banco_no_control")


def do_snapshot(lista: pl.DataFrame, marcas: pl.DataFrame, quitados: pl.DataFrame, dia: date) -> pl.DataFrame:
    def _texto(base: pl.DataFrame, coluna: str) -> pl.Expr:
        return pl.col(coluna).cast(pl.Utf8) if coluna in base.columns else pl.lit(None, dtype=pl.Utf8)

    def _sim(coluna: str) -> pl.Expr:
        return pl.col(coluna).fill_null("").str.strip_chars().str.to_lowercase() == "sim"

    if marcas.is_empty() or "data_snapshot" not in marcas.columns or "id_unico" not in marcas.columns:
        do_dia = pl.DataFrame(schema={"id_unico": pl.Utf8, **{c: pl.Utf8 for c in _COLUNAS_DA_MARCA}})
    else:
        do_dia = marcas.filter(pl.col("data_snapshot").cast(pl.Date, strict=False) == dia)
    marca = (
        do_dia.select(
            _texto(do_dia, "id_unico").alias("id_unico"),
            pl.lit(True).alias("_m_tem"),
            *[_texto(do_dia, c).alias(f"_m_{c}") for c in _COLUNAS_DA_MARCA],
            *[_texto(do_dia, c).alias(f"_t_{c}") for c in _COLUNAS_DO_TITULO if c != "id_unico"],
        )
        .with_columns(pl.col("_m_data_pagamento").str.slice(0, 10).str.to_date(strict=False).alias("_m_dia_pago"))
        .unique(subset=["id_unico"], keep="last")
    )
    manual_do_dia = _sim("_m_entrada_manual") & (pl.col("_m_dia_pago").is_null() | (pl.col("_m_dia_pago") == dia))

    pagos_em = (
        quitados.select(
            pl.col("id_unico").cast(pl.Utf8), pl.col("data_pagamento").cast(pl.Date, strict=False).alias("_quitado_em")
        )
        .drop_nulls()
        .unique(subset=["id_unico"], keep="last")
        if not quitados.is_empty() and {"id_unico", "data_pagamento"} <= set(quitados.columns)
        else pl.DataFrame(schema={"id_unico": pl.Utf8, "_quitado_em": pl.Date})
    )

    titulos = (
        lista.select(*[_texto(lista, c).alias(c) for c in (*_COLUNAS_DO_TITULO, *COLUNAS_PAGO_NO_CONTROL)])
        if not lista.is_empty()
        else pl.DataFrame(schema={c: pl.Utf8 for c in (*_COLUNAS_DO_TITULO, *COLUNAS_PAGO_NO_CONTROL)})
    )
    do_control = (pl.col("pago_no_control").fill_null("") == "Sim") & pl.col("_m_tem").is_null()
    juntos = (
        titulos.join(
            marca.select("id_unico", *[c for c in marca.columns if c.startswith("_m_")]), on="id_unico", how="left"
        )
        .with_columns(
            pl.when(do_control).then(pl.lit("Sim")).otherwise(pl.col("_m_pagou")).alias("_m_pagou"),
            pl.when(do_control).then(pl.lit("Não")).otherwise(pl.col("_m_pagar")).alias("_m_pagar"),
            pl.when(do_control)
            .then(pl.col("valor_pago_no_control"))
            .otherwise(pl.col("_m_valor_pago"))
            .alias("_m_valor_pago"),
            pl.when(do_control).then(pl.col("banco_no_control")).otherwise(pl.col("_m_banco")).alias("_m_banco"),
            pl.when(do_control).then(pl.lit(dia)).otherwise(pl.col("_m_dia_pago")).alias("_m_dia_pago"),
            pl.when(do_control).then(pl.lit(True)).otherwise(pl.col("_m_tem")).alias("_m_tem"),
        )
        .join(pagos_em, on="id_unico", how="left")
        .filter(~(pl.col("_quitado_em").is_not_null() & (pl.col("_quitado_em") < dia)).fill_null(False))
        .filter(
            ~(_sim("_m_pagou") & pl.col("_m_dia_pago").is_not_null() & (pl.col("_m_dia_pago") != dia)).fill_null(False)
        )
    )
    extras = marca.filter(manual_do_dia & ~pl.col("id_unico").is_in(titulos["id_unico"].to_list())).select(
        "id_unico",
        *[pl.col(f"_t_{c}").alias(c) for c in _COLUNAS_DO_TITULO if c != "id_unico"],
        *[c for c in marca.columns if c.startswith("_m_")],
    )
    do_dia = pl.concat([juntos.drop("_quitado_em"), extras], how="diagonal_relaxed")
    if do_dia.is_empty():
        return pl.DataFrame()
    usavel = pl.col("_m_id_ok") & ~(
        _sim("_m_entrada_manual") & pl.col("_m_dia_pago").is_not_null() & (pl.col("_m_dia_pago") != dia)
    )
    do_dia = do_dia.with_columns(pl.col("_m_tem").fill_null(False).alias("_m_id_ok")).with_columns(
        usavel.fill_null(False).alias("_usavel")
    )

    def _marca(coluna: str, tipo=pl.Utf8, padrao=None) -> pl.Expr:
        valor = pl.col(f"_m_{coluna}").cast(tipo, strict=False)
        return (
            pl.when(pl.col("_usavel"))
            .then(valor if padrao is None else valor.fill_null(padrao))
            .otherwise(pl.lit(padrao, dtype=tipo))
        )

    def _coluna(origem: str, destino: str, tipo=pl.Utf8) -> pl.Expr:
        if origem in do_dia.columns:
            return pl.col(origem).cast(tipo, strict=False).alias(destino)
        return pl.lit(None, dtype=tipo).alias(destino)

    return do_dia.select(
        pl.col("REVENDA"),
        pl.col("data_vencimento").cast(pl.Date, strict=False).alias("DATA"),
        _coluna("razao_social", "FORNECEDOR"),
        _coluna("descricao_despesa", "TIPO_FORNECEDOR"),
        _coluna("descricao_despesa", "descricao_despesa"),
        pl.lit(None, dtype=pl.Utf8).alias("CENTRO_CUSTO"),
        _coluna("num_doc", "PGMOVMOV_NDUPL"),
        _coluna("tipo_doc", "tipo_doc"),
        _coluna("cnpj", "PGMOVMOV_CGC"),
        _coluna("valor_original", "PGMOVMOV_VALOR", pl.Float64),
        _coluna("num_doc_normalizado", "num_doc_normalizado"),
        _marca("valor_pago", pl.Float64).alias("valor_pago"),
        _marca("juros", pl.Float64).alias("juros"),
        _marca("banco").alias("banco"),
        _marca("auditoria", padrao="Não").alias("auditoria"),
        _marca("pagar", padrao="Não").alias("pagar"),
        _marca("conselho", padrao="Não").alias("conselho"),
        _marca("pagou", padrao="Não").alias("pagou"),
        pl.when(
            _sim("_m_entrada_manual")
            & (pl.col("_m_dia_pago").is_null() | (pl.col("_m_dia_pago") == dia)).fill_null(False)
        )
        .then(pl.lit("Sim"))
        .otherwise(pl.lit("Não"))
        .alias("entrada_manual"),
        _coluna("id_unico", "id_unico"),
    )


def nomes_dos_bancos(baixa_control: dict, revenda: str | None) -> dict[int, str]:
    from core.config import chave_revenda, chaves_das_revendas

    nomes = {
        int(codigo): nome for nome, codigo in (baixa_control.get("bancos_comuns") or {}).items() if codigo is not None
    }
    da_url = chaves_das_revendas([revenda]) if revenda else set()
    for revenda_do_config, bancos in (baixa_control.get("de_para_bancos") or {}).items():
        if str(revenda_do_config).startswith("_") or chave_revenda(revenda_do_config) not in da_url:
            continue
        nomes.update({int(codigo): nome for nome, codigo in (bancos or {}).items() if codigo is not None})
    return nomes


def pagos_no_control_do_dia(
    pagos: pl.DataFrame,
    lista: pl.DataFrame,
    com_registro: set[str],
    despesas: pl.DataFrame,
    bancos: dict[int, str],
    dia: date,
    valores_manuais: list[float] | None = None,
) -> pl.DataFrame:
    if pagos.is_empty() or not {"id_unico", "data_pagamento", "num_doc_normalizado", "cnpj"} <= set(pagos.columns):
        return pl.DataFrame()
    do_dia = pagos.filter(pl.col("data_pagamento").cast(pl.Date, strict=False) == dia).with_columns(
        pl.col("id_unico").cast(pl.Utf8), pl.col("num_doc_normalizado").cast(pl.Utf8), pl.col("cnpj").cast(pl.Utf8)
    )
    ja_na_lista = set(lista["id_unico"].cast(pl.Utf8).to_list()) if "id_unico" in lista.columns else set()
    do_dia = do_dia.filter(~pl.col("id_unico").is_in(list(ja_na_lista | set(com_registro))))
    if {"num_doc_normalizado", "cnpj"} <= set(lista.columns) and not lista.is_empty():
        documentos = lista.select(pl.col("num_doc_normalizado").cast(pl.Utf8), pl.col("cnpj").cast(pl.Utf8)).unique()
        do_dia = do_dia.join(documentos, on=["num_doc_normalizado", "cnpj"], how="anti")
    if valores_manuais and not do_dia.is_empty():
        manuais = (
            pl.DataFrame({"_valor": [round(float(v), 2) for v in valores_manuais]})
            .group_by("_valor")
            .len()
            .rename({"len": "_manuais"})
        )
        do_dia = (
            do_dia.with_columns(pl.col("valor_pago").cast(pl.Float64, strict=False).round(2).alias("_valor"))
            .with_columns(pl.int_range(pl.len()).over("_valor").alias("_ordem"))
            .join(manuais, on="_valor", how="left")
            .filter(pl.col("_ordem") >= pl.col("_manuais").fill_null(0))
            .drop("_valor", "_ordem", "_manuais")
        )
    if do_dia.is_empty():
        return pl.DataFrame()
    if not despesas.is_empty() and "codigo_despesa" in do_dia.columns:
        de_para = (
            despesas.select("codigo_despesa", "descricao_despesa")
            .drop_nulls("codigo_despesa")
            .unique(subset=["codigo_despesa"], keep="first")
        )
        do_dia = do_dia.join(de_para, on="codigo_despesa", how="left")
    if "descricao_despesa" not in do_dia.columns:
        do_dia = do_dia.with_columns(pl.lit(None, dtype=pl.Utf8).alias("descricao_despesa"))
    revenda = "REVENDA" if "REVENDA" in do_dia.columns else "revenda"
    banco = (
        pl.col("cod_banco")
        .cast(pl.Int64, strict=False)
        .replace_strict(bancos, default=pl.col("cod_banco").cast(pl.Utf8), return_dtype=pl.Utf8)
    )
    por_titulo = (
        do_dia.with_columns(banco.alias("_banco"))
        .group_by("num_doc_normalizado", "cnpj", maintain_order=True)
        .agg(
            pl.col(revenda).first().alias("revenda"),
            pl.col("data_vencimento").first(),
            pl.col("num_doc").first(),
            pl.col("tipo_doc").first(),
            pl.col("valor_pago").cast(pl.Float64, strict=False).sum().round(2).alias("valor_pago"),
            pl.col("razao_social").first(),
            pl.col("descricao_despesa").first(),
            pl.col("id_unico").first(),
            pl.col("_banco").unique(maintain_order=True).str.join(" + "),
        )
    )
    return por_titulo.select(
        pl.col("revenda").cast(pl.Utf8),
        pl.col("data_vencimento").cast(pl.Date, strict=False),
        pl.col("num_doc").cast(pl.Utf8),
        "num_doc_normalizado",
        pl.col("tipo_doc").cast(pl.Utf8),
        "cnpj",
        pl.col("valor_pago").alias("valor_original"),
        pl.col("razao_social").cast(pl.Utf8),
        pl.col("descricao_despesa").cast(pl.Utf8),
        "id_unico",
        pl.lit(dia).cast(pl.Date).alias("data_snapshot"),
        pl.lit("Sim").alias("pago_no_control"),
        pl.col("valor_pago").alias("valor_pago_no_control"),
        pl.col("_banco").alias("banco_no_control"),
    )


BANCO_FABRICA = "fabrica"


def e_banco_fabrica(rotulo: str | None) -> bool:
    if not rotulo:
        return False
    limpo = unicodedata.normalize("NFKD", str(rotulo).strip().casefold())
    limpo = "".join(c for c in limpo if not unicodedata.combining(c))
    return limpo == BANCO_FABRICA


ORDEM_FORNECEDOR = "_ORDEM_FORNECEDOR"

ACENTOS = {
    "á": "a",
    "à": "a",
    "â": "a",
    "ã": "a",
    "ä": "a",
    "é": "e",
    "è": "e",
    "ê": "e",
    "ë": "e",
    "í": "i",
    "ì": "i",
    "î": "i",
    "ï": "i",
    "ó": "o",
    "ò": "o",
    "ô": "o",
    "õ": "o",
    "ö": "o",
    "ú": "u",
    "ù": "u",
    "û": "u",
    "ü": "u",
    "ç": "c",
    "ñ": "n",
}


def ordem_por_fornecedor() -> pl.Expr:
    return (
        pl.col("FORNECEDOR")
        .cast(pl.Utf8)
        .fill_null("")
        .str.to_lowercase()
        .str.replace_many(list(ACENTOS), list(ACENTOS.values()))
        .alias(ORDEM_FORNECEDOR)
    )


ARQUIVO_LIBERADAS = Path(__file__).parents[3] / "data" / "bd_financeiro" / "entradas_de_hoje_liberadas.json"


def versao_das_liberadas() -> int:
    try:
        return ARQUIVO_LIBERADAS.stat().st_mtime_ns
    except OSError:
        return 0


def entradas_de_hoje_liberadas(hoje: date | None = None, arquivo: Path | None = None) -> frozenset:
    hoje = hoje or date.today()
    try:
        conteudo = json.loads((arquivo or ARQUIVO_LIBERADAS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    if not isinstance(conteudo, dict) or conteudo.get("dia") != hoje.isoformat():
        return frozenset()
    return frozenset(str(ident) for ident in conteudo.get("ids") or [])


def sem_entradas_de_hoje(
    base: pl.DataFrame, ve_tudo: bool, so_de_hoje: bool = False, liberadas: frozenset = frozenset()
) -> pl.DataFrame:
    if base.is_empty() or "data_entrada" not in base.columns:
        return base
    entrada = pl.col("data_entrada").cast(pl.Date, strict=False)
    liberada = (
        pl.col("id_unico").cast(pl.Utf8).is_in(list(liberadas))
        if liberadas and "id_unico" in base.columns
        else pl.lit(False)
    )
    if so_de_hoje:
        if not ve_tudo:
            return base.filter((entrada == date.today()) & liberada)
        return base.filter(entrada == date.today())
    if ve_tudo:
        return base
    return base.filter(entrada.is_null() | (entrada < date.today()) | liberada)


def sem_acento(texto: str) -> str:
    base = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in base if not unicodedata.combining(c))


def mesma_pessoa(a, b) -> bool:
    def _chave(x):
        return ".".join(sem_acento(x).casefold().replace(".", " ").split())

    return bool(a) and bool(b) and _chave(a) == _chave(b)


def float_ou_none(valor) -> float | None:
    if valor is None:
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def nome_legivel(quem) -> str:
    texto = str(quem or "").strip()
    if not texto or " " in texto or "." not in texto:
        return texto
    return " ".join(parte.capitalize() for parte in texto.split(".") if parte)


_TIPO_DO_VINCULO = {"NF": "como nota", "FATURA": "como boleto"}


def texto_do_vinculo(v: dict | None) -> str:
    if not v:
        return ""
    tipo = _TIPO_DO_VINCULO.get(str(v.get("tipo") or "").upper())
    quem = nome_legivel(v.get("vinculado_por")) if v.get("vinculado_por") else ""
    if v.get("origem") == "conteudo" and v.get("leitura") == "boleto":
        partes = ["ligado junto do boleto que paga esta nota e outra (a mesma compra, na pasta do vencimento)", tipo]
    elif v.get("origem") == "conteudo" and v.get("leitura") == "nome":
        from core.rede_documentos import eh_boleto_pelo_nome

        dentro = str(v.get("tipo") or "").upper() == "FATURA" and not eh_boleto_pelo_nome(
            v.get("nome") or Path(str(v.get("caminho") or "")).name
        )
        partes = [
            "achado pelo nome do arquivo (o número do título, na pasta do vencimento)",
            "o arquivo das notas da mesma compra, com o boleto dentro" if dentro else tipo,
        ]
    elif v.get("origem") == "conteudo" and v.get("leitura") == "guia":
        partes = ["a guia da pasta do vencimento, com o mesmo tipo e o mesmo valor do título", tipo]
    elif v.get("origem") == "conteudo":
        partes = ["achado pelo conteúdo do arquivo (o CNPJ e o número do título no texto)", tipo]
    elif v.get("origem") == "aqui":
        partes = ["vinculado nesta tela", tipo, f"por {quem}" if quem else None]
    else:
        como = "pela varredura automática" if v.get("automatico") else f"por {quem}" if quem else None
        partes = ["vinculado no sistema antigo", tipo, como]
    return ", ".join(p for p in partes if p)


def selo_do_vinculo(v: dict) -> str:
    if v.get("origem") == "conteudo":
        return {"nome": "pelo nome", "boleto": "mesmo boleto", "guia": "pela guia"}.get(
            v.get("leitura"), "pelo conteúdo"
        )
    if v.get("origem") == "aqui":
        return "nesta tela"
    if v.get("automatico"):
        return "sistema antigo · automático"
    if v.get("vinculado_por"):
        return f"sistema antigo · {nome_legivel(v['vinculado_por'])}"
    return "sistema antigo"


def com_partes(base: pl.DataFrame) -> pl.DataFrame:
    if base.is_empty() or "id_unico" not in base.columns or "PGMOVMOV_VALOR" not in base.columns:
        return base
    ids = pl.col("id_unico").cast(pl.Utf8)
    valor = pl.col("PGMOVMOV_VALOR").cast(pl.Float64, strict=False)
    base = base.with_columns(
        ids.str.contains(SUFIXO_PARTE).alias("_eh_parte"),
        ids.str.replace(SUFIXO_PARTE, "").alias("_grupo"),
        valor.alias("_valor_parquet"),
    )
    editados = manual_arquivo.pagamentos_por_titulo()
    desfeitas = manual_arquivo.partes_desfeitas()
    titulos = set(base.filter(~pl.col("_eh_parte"))["id_unico"].to_list())
    no_parquet = set(base.filter(pl.col("_eh_parte"))["id_unico"].to_list())
    antes = base.filter(pl.col("_eh_parte")).group_by("_grupo").agg(pl.col("_valor_parquet").sum().alias("_antes"))

    do_arquivo = {}
    for i, dados in editados.items():
        if not eh_parte(i) or base_do(i) not in titulos:
            continue
        if dados.get("valor_original") is not None:
            do_arquivo[i] = dados["valor_original"]
        elif i not in no_parquet:
            do_arquivo[i] = dados.get("valor_pago")
    novas_ids = [i for i in do_arquivo if i not in no_parquet and i not in desfeitas]
    if novas_ids:
        molde = base.filter(pl.col("id_unico").is_in([base_do(i) for i in novas_ids])).unique(
            subset=["id_unico"], keep="first"
        )
        limpas = [
            c
            for c in ("pagar", "pagar_user", "assinar", "assinar_user", "justificativa", "pagou", "juros", "valor_pago")
            if c in base.columns
        ]
        novas = (
            pl.DataFrame({"id_unico": novas_ids, "_grupo": [base_do(i) for i in novas_ids]})
            .join(molde.drop("id_unico"), on="_grupo", how="inner")
            .with_columns(
                pl.lit(True).alias("_eh_parte"),
                pl.lit(None, dtype=pl.Float64).alias("_valor_parquet"),
                *[pl.lit(None).alias(c) for c in limpas],
            )
        )
        base = pl.concat([base, novas.select(base.columns)], how="vertical_relaxed")
    if desfeitas:
        base = base.filter(~(pl.col("_eh_parte") & pl.col("id_unico").is_in(list(desfeitas))))

    if do_arquivo:
        agora = pl.col("id_unico").replace_strict(do_arquivo, default=None, return_dtype=pl.Float64)
        base = base.with_columns(
            pl.when(pl.col("_eh_parte") & agora.is_not_null())
            .then(agora)
            .otherwise(pl.col("PGMOVMOV_VALOR").cast(pl.Float64, strict=False))
            .alias("PGMOVMOV_VALOR")
        )

    mudanca = (
        base.filter(pl.col("_eh_parte"))
        .group_by("_grupo")
        .agg(pl.col("PGMOVMOV_VALOR").cast(pl.Float64).sum().alias("_agora"))
        .join(antes, on="_grupo", how="full", coalesce=True)
        .with_columns((pl.col("_agora").fill_null(0) - pl.col("_antes").fill_null(0)).alias("_delta"))
        .select("_grupo", "_delta", pl.col("_agora").fill_null(0).alias("_soma_partes"))
    )
    base = base.join(mudanca, on="_grupo", how="left")
    eh_base = ~pl.col("_eh_parte") & pl.col("_delta").is_not_null()
    titulo = (
        pl.col("valor_titulo").cast(pl.Float64, strict=False)
        if "valor_titulo" in base.columns
        else pl.lit(None, dtype=pl.Float64)
    )
    base = base.with_columns(
        pl.when(eh_base)
        .then((pl.col("_valor_parquet") - pl.col("_delta")).round(2))
        .otherwise(pl.col("PGMOVMOV_VALOR").cast(pl.Float64, strict=False))
        .alias("PGMOVMOV_VALOR"),
    ).with_columns(
        pl.when(pl.col("_eh_parte"))
        .then(pl.col("PGMOVMOV_VALOR"))
        .otherwise(pl.coalesce(titulo, pl.col("PGMOVMOV_VALOR") + pl.col("_soma_partes").fill_null(0)))
        .alias("valor_titulo"),
        (~pl.col("_eh_parte") & (pl.col("_soma_partes").fill_null(0) != 0)).alias("_tem_partes"),
    )
    dividido = pl.col("_eh_parte").any().over("_grupo")
    base = base.with_columns(
        pl.when(dividido)
        .then(pl.col("valor_titulo").filter(~pl.col("_eh_parte")).first().over("_grupo"))
        .alias("valor_titulo_cheio"),
    )
    if "valor_original" in base.columns:
        base = base.with_columns(pl.col("PGMOVMOV_VALOR").alias("valor_original"))
    return base.drop("_eh_parte", "_grupo", "_valor_parquet", "_delta", "_soma_partes")


def sem_os_excluidos(
    base: pl.DataFrame, exclusoes: dict, outros: set, atualizado, fora_do_control: set | None = None
) -> pl.DataFrame:
    from core.manual_arquivo import titulo_ainda_excluido

    todos = set(exclusoes) | set(outros)
    if base.is_empty() or not todos or "_id" not in base.columns:
        return base
    do_control = [i for i in todos if i not in exclusoes or titulo_ainda_excluido(exclusoes[i][1], atualizado)]
    manual = (
        pl.col("_entrada_manual").cast(pl.Utf8).fill_null("").str.strip_chars() == "Sim"
        if "_entrada_manual" in base.columns
        else pl.lit(False)
    )
    ident = pl.col("_id").cast(pl.Utf8)
    dono = ident.str.replace(SUFIXO_PARTE, "")
    tirados_de_vez = list(fora_do_control or ())
    ainda_fora_do_control = (
        (pl.col("_no_erp").cast(pl.Int64, strict=False) == 0).fill_null(False)
        if "_no_erp" in base.columns
        else pl.lit(False)
    )
    fora = (
        pl.when(manual)
        .then(ident.is_in(list(todos)) | dono.is_in(list(todos)))
        .otherwise(
            ident.is_in(do_control)
            | dono.is_in(do_control)
            | (ainda_fora_do_control & (ident.is_in(tirados_de_vez) | dono.is_in(tirados_de_vez)))
        )
    )
    return base.filter(~fora)


def manuais_em_aberto(
    do_parquet: pl.DataFrame, do_arquivo: pl.DataFrame, excluidos: set | None = None
) -> tuple[pl.DataFrame, pl.DataFrame]:
    fora = list(excluidos or ())
    if do_parquet.is_empty() or "pagou" not in do_parquet.columns:
        abertos = do_parquet
    else:
        pagou = pl.col("pagou").cast(pl.Utf8).str.strip_chars().str.to_lowercase()
        if not do_arquivo.is_empty():
            pagos = do_parquet.filter(pagou == "sim")["id_unico"].to_list()
            do_arquivo = do_arquivo.filter(~pl.col("id_unico").is_in(pagos))
        abertos = do_parquet.filter(pagou != "sim")
    if not abertos.is_empty() and "id_unico" in abertos.columns:
        if fora:
            abertos = abertos.filter(~pl.col("id_unico").is_in(fora))
        if not do_arquivo.is_empty():
            abertos = abertos.filter(~pl.col("id_unico").is_in(do_arquivo["id_unico"].to_list()))
    return abertos, do_arquivo


def com_manuais_pendentes(base: pl.DataFrame, manuais: pl.DataFrame) -> pl.DataFrame:
    if manuais.is_empty():
        return base
    if not base.is_empty() and "id_unico" in base.columns:
        ja = set(base["id_unico"].to_list())
        manuais = manuais.filter(~pl.col("id_unico").is_in(list(ja)))
    if manuais.is_empty():
        return base

    de_para = {
        "DATA": pl.col("data_vencimento").cast(pl.Date, strict=False),
        "FORNECEDOR": pl.col("razao_social").cast(pl.Utf8),
        "TIPO_FORNECEDOR": pl.col("descricao_despesa").cast(pl.Utf8),
        "descricao_despesa": pl.col("descricao_despesa").cast(pl.Utf8),
        "PGMOVMOV_NDUPL": pl.col("num_doc").cast(pl.Utf8),
        "tipo_doc": pl.col("tipo_doc").cast(pl.Utf8),
        "PGMOVMOV_CGC": pl.col("cnpj").cast(pl.Utf8),
        "PGMOVMOV_VALOR": pl.col("valor_original").cast(pl.Float64),
        "num_doc_normalizado": pl.col("num_doc_normalizado").cast(pl.Utf8),
        "id_unico": pl.col("id_unico").cast(pl.Utf8),
        "entrada_manual": pl.lit("Sim"),
        "pagar": pl.lit("Não"),
        "pagou": pl.lit("Não"),
        "auditoria": pl.lit("Não"),
        "conselho": pl.lit("Não"),
    }
    if base.is_empty():
        return manuais.select([e.alias(n) for n, e in de_para.items()])

    colunas = []
    for nome, tipo in base.schema.items():
        if nome in de_para:
            colunas.append(de_para[nome].cast(tipo, strict=False).alias(nome))
        else:
            colunas.append(pl.lit(None, dtype=tipo).alias(nome))
    return pl.concat([base, manuais.select(colunas)], how="vertical_relaxed")


def auditado(ident: str, linha: dict, marcas: dict, linha_base: dict | None = None) -> bool:
    base_id = base_do(ident)
    for candidato in (base_id, ident) if base_id != ident else (ident,):
        if (candidato, "auditoria") in marcas:
            return bool(marcas[(candidato, "auditoria")])
        if candidato == ident and str(linha.get("auditoria") or "") == "Sim":
            return True
        if candidato == base_id != ident and str((linha_base or {}).get("auditoria") or "") == "Sim":
            return True
    return False


def na_gestao(ident: str, linha: dict, marcas: dict, linha_base: dict | None = None) -> bool:
    marcado = marcas.get((base_do(ident), "conselho"), ...)
    if marcado is ...:
        marcado = str((linha_base or linha).get("conselho") or "") == "Sim"
    return bool(marcado)


def datas_de_hoje(hoje: date) -> set:
    ultimo = dia_util_anterior(hoje)
    return {ultimo + timedelta(days=n) for n in range(1, (hoje - ultimo).days + 1)}


def marcados_para_pagar(base: pl.DataFrame, marcas: dict) -> set[str]:
    marcados = {ident for (ident, tipo), quem in marcas.items() if tipo == "pagar" and quem}
    if base.is_empty() or not {"id_unico", "pagar", "pagar_user"} <= set(base.columns):
        return marcados
    do_cache = base.filter(
        (pl.col("pagar").cast(pl.Utf8) == "Sim")
        & (pl.col("pagar_user").cast(pl.Utf8).fill_null("").str.strip_chars() != "")
    )["id_unico"].to_list()
    return marcados | {ident for ident in do_cache if ident and (ident, "pagar") not in marcas}


def visto_gravado(linha: dict, tipo: str, marcas: dict) -> tuple[bool, str | None]:
    alvo = base_do(linha["id"]) if tipo in ("auditoria", "conselho") else linha["id"]
    if (alvo, tipo) not in marcas:
        return linha["marcado"][tipo], None
    quem = marcas[(alvo, tipo)]
    return quem is not None, quem


def versao_das_marcacoes() -> int:
    alvo = manual_arquivo.caminho("marcacoes")
    return alvo.stat().st_mtime_ns if alvo.exists() else 0


def numero(texto) -> float | None:
    return ler_reais(texto)


def juros_derivado(valor: float | None, original) -> float | None:
    if valor is None:
        return None
    try:
        return max(0.0, round(valor - float(original or 0), 2))
    except (TypeError, ValueError):
        return None


def base_do_titulo(linha: dict) -> dict:
    return {
        "data_vencimento": linha.get("vencimento"),
        "num_doc": linha.get("documento_cru"),
        "num_doc_normalizado": linha.get("doc_norm") or None,
        "tipo_doc": linha.get("tipo_doc") or None,
        "cnpj": linha.get("cnpj"),
        "razao_social": linha.get("rotulo_linha"),
        "descricao_despesa": linha.get("descricao_despesa") or None,
        "valor_original": linha.get("valor_original"),
    }


def numeros_usados(base: str) -> list[str]:
    marcas = (ident for ident, _tipo in manual_arquivo.marcacoes_por_chave())
    todos = [
        *manual_arquivo.pagamentos_por_titulo(),
        *manual_arquivo.partes_desfeitas(),
        *marcas,
        *manual_arquivo.justificativas_por_titulo(),
    ]
    return [i for i in todos if eh_parte(i) and base_do(i) == base]


def juros_da_linha(fatia, posicao: int, editados: dict) -> float:
    ident = fatia["_id"][posicao] if "_id" in fatia.columns else None
    if ident:
        editado = editados.get(ident) or {}
        if editado.get("juros") is not None:
            return float(editado["juros"] or 0)
    return float(fatia["_juros"][posicao] or 0)


_TIPOS_DO_VINCULO = ("NF", "FATURA")
_SIGLAS_DE_NOTA = {"NF", "NFE", "NFS", "NFC", "NFCE", "NFSE", "CTE"}


def tipo_do_vinculo(tipo: str | None, nome: str) -> str | None:
    from core.rede_documentos import eh_boleto_pelo_nome, pares_do_nome

    tipo = str(tipo or "").upper()
    if tipo in _TIPOS_DO_VINCULO:
        return tipo
    if tipo in ("FAT", "BOL") or eh_boleto_pelo_nome(nome):
        return "FATURA"
    if tipo in _SIGLAS_DE_NOTA or any(t in _SIGLAS_DE_NOTA for t, _n in pares_do_nome(Path(str(nome or "")).name)):
        return "NF"
    primeira_palavra = re.match(r"[A-Za-z]+", Path(str(nome or "")).stem.strip())
    if primeira_palavra and primeira_palavra.group(0).upper() in _SIGLAS_DE_NOTA:
        return "NF"
    return None


def xml_conta(ident, doc_norm: str, fornecedor: str, docs: dict, anexos_antigos) -> bool:
    if not ident:
        return False
    base = base_do(ident)
    if base not in docs["com_xml"]:
        return False
    if base in docs["com_pdf_da_nota"] or ident in docs["com_pdf_da_nota"]:
        return False
    return not any(Path(a).stem.upper().endswith("-NF") for a in anexos_antigos(ident, doc_norm, fornecedor))


def tipo_do_olho(
    ident, doc_norm: str, fornecedor: str, docs: dict, sem_boleto_do_titulo, anexos_antigos
) -> bool | None:
    sem_boleto = (
        sem_boleto_do_titulo(ident) if ident and (ident in docs["com_anexo"] or ident in docs["com_vinculo"]) else None
    )
    if (
        sem_boleto is None
        and str(doc_norm or "") in docs["docs_antigos"]
        and (base_do(ident) not in docs["antigos_tirados"] or anexos_antigos(ident, doc_norm, fornecedor))
    ):
        sem_boleto = False
    rede = docs["rede"].get(base_do(ident)) if ident else None
    if rede is not None:
        sem_boleto = (rede == "pix") if sem_boleto is None else (sem_boleto and rede == "pix")
    if sem_boleto is None and xml_conta(ident, doc_norm, fornecedor, docs, anexos_antigos):
        sem_boleto = False
    return sem_boleto


def tem_arquivo_no_olho(ident, doc_norm: str, fornecedor: str, docs: dict, anexos_antigos) -> bool:
    doc_norm = str(doc_norm or "")
    return bool(
        xml_conta(ident, doc_norm, fornecedor, docs, anexos_antigos)
        or base_do(ident) in docs["abrir_rede"]
        or ident in docs["com_vinculo"]
        or ident in docs["com_anexo"]
        or (doc_norm in docs["docs_antigos"] and anexos_antigos(ident, doc_norm, fornecedor))
    )


def so_os_digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def gastos_com_veiculo() -> dict[tuple[str, str], dict]:
    gastos = {}
    for gasto in manual_arquivo.ler("veiculos_notas").iter_rows(named=True):
        cnpj = so_os_digitos(gasto.get("emitente_cnpj")).zfill(14)
        numero = so_os_digitos(gasto.get("numero")).lstrip("0")
        if gasto.get("id") and numero and cnpj.strip("0"):
            gastos[(cnpj, numero)] = gasto
    return gastos


def gasto_com_veiculo_do_titulo(cnpj, num_doc_normalizado, gastos: dict) -> dict | None:
    if not gastos:
        return None
    cnpj_do_fornecedor = so_os_digitos(cnpj).zfill(14)
    digitos = so_os_digitos(num_doc_normalizado)
    for numero in (digitos.lstrip("0"), digitos[:-2].lstrip("0")):
        if numero and (cnpj_do_fornecedor, numero) in gastos:
            return gastos[(cnpj_do_fornecedor, numero)]
    return None


def texto_do_gasto_com_veiculo(gasto: dict) -> str:
    partes = [str(gasto.get(campo)) for campo in ("placa", "tipo") if gasto.get(campo)]
    if gasto.get("km"):
        partes.append(f"KM {int(gasto['km']):,}".replace(",", "."))
    detalhe = (": " + " · ".join(partes)) if partes else ""
    return f"Gasto com veículo{detalhe}. Clique para abrir nas Despesas do Logístico."


def link_das_despesas(gasto: dict) -> str | None:
    from urllib.parse import urlencode

    from core.config import chave_revenda
    from core.config_arquivo import carregar_json

    regra = (carregar_json("parametros_financeiro") or {}).get("despesas_no_logistico") or {}
    if not regra.get("endereco") or not gasto.get("id"):
        return None
    revenda = str(gasto.get("revenda") or "")
    nome_no_dash = next(
        (
            nome
            for chave, nome in (regra.get("revenda_no_dash") or {}).items()
            if not chave.startswith("_") and chave_revenda(chave) == chave_revenda(revenda)
        ),
        revenda,
    )
    parametros = {
        "revenda": nome_no_dash,
        "dashboard": regra.get("dashboard") or "Acompanhamento Logistico",
        "PAGINA": "dsp",
        "NOTA": gasto["id"],
    }
    return f"{regra['endereco']}?{urlencode(parametros)}"


def para_assinar(base: pl.DataFrame, docs: dict, sem_boleto_do_titulo, anexos_antigos) -> pl.DataFrame:
    if base.is_empty():
        return base
    fica = []
    for ident, doc, nome, assinado in zip(base["_id"], base["_doc_norm"], base["Fornecedor"], base["_assinar"]):
        doc, nome = str(doc or ""), str(nome or "")
        fica.append(
            bool(ident)
            and str(assinado or "") != "Sim"
            and tipo_do_olho(ident, doc, nome, docs, sem_boleto_do_titulo, anexos_antigos) is not None
            and tem_arquivo_no_olho(ident, doc, nome, docs, anexos_antigos)
        )
    return base.filter(pl.Series(fica, dtype=pl.Boolean))
