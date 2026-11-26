from datetime import date, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

import cachetools
import polars as pl

from core import pastas_da_sessao, virada
from core.compat import ler_parquet  # noqa: E402
from core.config import REVENDAS_POR_GRUPO, casar_revendas, chave_revenda
from core.config_arquivo import carregar_json
from core.performance import medir_tempo

PASTA_PARQUET = Path(__file__).parents[3] / "data" / "bd_financeiro"

_cache = cachetools.LRUCache(maxsize=64)

_VISTOS = ("pagar", "pagou", "auditoria", "conselho", "entrada_manual")


_versoes_da_sessao: dict[str, dict[str, int]] = {}


def _sessao() -> str | None:
    try:
        from shiny.session import get_current_session

        atual = get_current_session()
    except Exception:
        return None
    if atual is None:
        return None
    raiz = atual.root_scope() if hasattr(atual, "root_scope") else atual
    return getattr(raiz, "id", None)


def soltar_versoes(sessao_id: str | None) -> None:
    _versoes_da_sessao.pop(sessao_id, None)


def _pasta_do_arquivo(arquivo: str) -> Path:
    return pastas_da_sessao.pasta_do_cache(arquivo, PASTA_PARQUET)


def versao_lida(arquivo: str) -> datetime | None:
    caminho = _pasta_do_arquivo(arquivo) / f"{arquivo}.parquet"
    if not caminho.is_file():
        return None
    atual = caminho.stat().st_mtime_ns
    sessao = _sessao()
    fixada = _versoes_da_sessao.get(sessao, {}).get(arquivo) if sessao is not None else None
    versao = fixada if fixada is not None and (str(caminho), fixada) in _cache else atual
    return datetime.fromtimestamp(versao / 1e9)


def _carregar(arquivo: str, fixar: bool = True) -> pl.DataFrame:
    caminho = _pasta_do_arquivo(arquivo) / f"{arquivo}.parquet"
    if not caminho.is_file():
        return pl.DataFrame()
    atual = caminho.stat().st_mtime_ns
    sessao = _sessao() if fixar else None
    if sessao is not None:
        vistas = _versoes_da_sessao.setdefault(sessao, {})
        fixada = vistas.get(arquivo)
        if fixada is not None and fixada != atual and (str(caminho), fixada) in _cache:
            return _cache[(str(caminho), fixada)]
        vistas[arquivo] = atual
    chave = (str(caminho), atual)
    if chave not in _cache:
        base = ler_parquet(caminho)
        fora = [c for c in _VISTOS if c in base.columns and base[c].dtype != pl.Utf8]
        _cache[chave] = base.with_columns(pl.col(fora).cast(pl.Utf8)) if fora else base
    return _cache[chave]


@medir_tempo(pagina="PPF")
def contas_pagar() -> pl.DataFrame:
    return _carregar("contas_pagar")


@medir_tempo(pagina="PPF")
def contas_receber() -> pl.DataFrame:
    return _carregar("contas_receber")


@medir_tempo(pagina="PPF")
def liberacao_manual() -> pl.DataFrame:
    linhas = _carregar("liberacao_manual")
    boletos_na_lista = ((carregar_json("parametros_financeiro") or {}).get("liberacao_manual") or {}).get("boletos")
    if boletos_na_lista or linhas.is_empty() or not {"tipo_doc", "nome"} <= set(linhas.columns):
        return linhas
    nome_diz_boleto = (
        pl.col("nome")
        .cast(pl.Utf8)
        .fill_null("")
        .str.to_uppercase()
        .str.contains(r"(?:^|[^A-Z])(?:BOLETOS?|BOL)(?:[^A-Z]|$)")
    )
    especie_bol = (pl.col("tipo_doc").cast(pl.Utf8) == "BOL").fill_null(False)
    return linhas.filter(~(especie_bol & nome_diz_boleto))


@medir_tempo(pagina="PPF")
def titulos_pagos() -> pl.DataFrame:
    return _carregar("titulos_pagos")


def titulos_pagos_emprestimos() -> pl.DataFrame:
    return _carregar("titulos_pagos_emprestimos")


@medir_tempo(pagina="PPF")
def extrato_banco() -> pl.DataFrame:
    return _carregar("extrato_banco")


BANCO_CAIXA = carregar_json("parametros_financeiro").get("banco_caixa", 999)
"""O "banco" 999 nao e' um banco: e' o caixa da revenda dentro do ERP."""


_BATIDA_COM_MOVIMENTO = ("dinheiro_moeda", "oct", "octs_nao_compensadas", "vale", "pix_provisorios")
_SALDO_999_COM_MOVIMENTO = ("valor_dinheiro", "valor_moeda", "valor_pix")


def _maior_dia_com_valor(base: pl.DataFrame | None, coluna_data: str, colunas: tuple, ontem: date) -> date | None:
    if base is None or base.is_empty() or coluna_data not in base.columns:
        return None
    presentes = [c for c in colunas if c in base.columns]
    if not presentes:
        return None
    dia = pl.col(coluna_data).cast(pl.Date, strict=False)
    validas = base.filter(
        (dia <= ontem)
        & pl.any_horizontal([pl.col(c).cast(pl.Float64, strict=False).fill_null(0) != 0 for c in presentes])
    )
    return validas.select(dia.max()).item() if validas.height else None


def data_referencia_999(
    base: pl.DataFrame,
    hoje: date | None = None,
    saldo_999: pl.DataFrame | None = None,
    batida: pl.DataFrame | None = None,
) -> date | None:
    ontem = (hoje or date.today()) - timedelta(days=1)
    do_caixa = base.filter(pl.col("PGMOVBAN_NRBCO") == BANCO_CAIXA) if "PGMOVBAN_NRBCO" in base.columns else base
    dias = [
        _maior_dia_com_valor(do_caixa, "DATA", ("PGMOVBAN_VALORL",), ontem),
        _maior_dia_com_valor(saldo_999, "data_baixa", _SALDO_999_COM_MOVIMENTO, ontem),
        _maior_dia_com_valor(batida, "data", _BATIDA_COM_MOVIMENTO, ontem),
    ]
    return max((d for d in dias if d is not None), default=ontem)


def extrato_caixa_999(base: pl.DataFrame, dia: date | None = None) -> pl.DataFrame:
    if base.is_empty() or "PGMOVBAN_NRBCO" not in base.columns:
        return base
    linhas = base.filter(pl.col("PGMOVBAN_NRBCO") == BANCO_CAIXA)
    if dia is not None:
        linhas = linhas.filter(pl.col("DATA") == dia)
    if "PGMOVBAN_NRDOC_EXTENSO" in linhas.columns:
        documento = pl.col("PGMOVBAN_NRDOC_EXTENSO").fill_null("")
        historico = pl.col("PGMOVBAN_HISTORICO").fill_null("")
        regras = (carregar_json("composicao_financeira") or {}).get("documentos_caixa_999") or {}
        com_pix = str(regras.get("prefixo_com_excecao_pix") or "")
        for prefixo in regras.get("prefixos_fora") or ["AC0", "CR0"]:
            eh = documento.str.starts_with(prefixo)
            if prefixo == com_pix:
                eh = eh & ~historico.str.contains("PIX")
            linhas = linhas.filter(~eh)
        catalogo = carregar_json("composicao_financeira") or {}
        if "REVENDA" in linhas.columns:
            chave = pl.col("REVENDA").cast(pl.Utf8).map_elements(chave_revenda, return_dtype=pl.Utf8)
            com_saque = [chave_revenda(r) for r in catalogo.get("revendas_saque_no_lugar_do_brinks") or []]
            if com_saque:
                linhas = linhas.filter(~(chave.is_in(com_saque) & (documento.str.strip_chars() == "SAQUE")))
            so_positivo = [chave_revenda(r) for r in catalogo.get("revendas_999_so_valor_positivo") or []]
            if so_positivo and "PGMOVBAN_VALORL" in linhas.columns:
                linhas = linhas.filter(
                    ~(chave.is_in(so_positivo) & (pl.col("PGMOVBAN_VALORL").cast(pl.Float64, strict=False) <= 0))
                )
    return linhas.sort(["DATA", "PGMOVBAN_VALORL"], descending=[True, False], nulls_last=True)


def saldos_por_banco(base: pl.DataFrame) -> pl.DataFrame:
    if base.is_empty() or "PGMOVBAN_NRBCO" not in base.columns:
        return pl.DataFrame()
    return (
        base.filter(pl.col("PGMOVBAN_NRBCO") != BANCO_CAIXA)
        .group_by("PGMOVBAN_NRBCO")
        .agg(pl.col("PGMOVBAN_VALORL").sum().alias("SALDO"))
        .sort("PGMOVBAN_NRBCO")
    )


def dados_manuais() -> pl.DataFrame:
    return _carregar("dados_manuais")


_pagamentos_corrigidos: dict = {"de": None, "valor": None}


def pagamentos_manuais() -> pl.DataFrame:
    base = _carregar("pagamentos")
    if _pagamentos_corrigidos["de"] is base:
        return _pagamentos_corrigidos["valor"]
    corrigida = base
    if not base.is_empty() and {"id_unico", "valor_pago", "valor_original"} <= set(base.columns):
        ident = pl.col("id_unico").cast(pl.Utf8)
        parte = ident.str.contains(r"_clone\d*$")
        chave = [c for c in ("REVENDA",) if c in base.columns]
        partes = (
            base.filter(parte)
            .group_by(ident.str.replace(r"(?:_clone\d*)+$", "").alias("_base"), *chave)
            .agg(pl.col("valor_pago").cast(pl.Float64, strict=False).sum().alias("_pago_partes"))
        )
        if not partes.is_empty():
            pago = pl.col("valor_pago").cast(pl.Float64, strict=False)
            titulo = pl.col("valor_original").cast(pl.Float64, strict=False)
            cheia = (
                ~parte
                & (pl.col("_pago_partes") > 0.009)
                & ((pago - titulo).abs() < 0.01)
                & (titulo - pl.col("_pago_partes") >= 0)
            )
            corrigida = (
                base.with_columns(ident.alias("_base"))
                .join(partes, on=["_base", *chave], how="left")
                .with_columns(pl.when(cheia).then(titulo - pl.col("_pago_partes")).otherwise(pago).alias("valor_pago"))
                .drop("_base", "_pago_partes")
            )
    _pagamentos_corrigidos.update(de=base, valor=corrigida)
    return corrigida


def pagamentos_snapshot() -> pl.DataFrame:
    daqui = _carregar("pagamentos_snapshot", fixar=False)
    antigo = _carregar("pagamentos_snapshot_antigo", fixar=False)
    if antigo.is_empty():
        return daqui
    chave = ("marcacoes", _mtime("pagamentos_snapshot"), _mtime("pagamentos_snapshot_antigo"), _estado_das_viradas())
    if chave not in _cache_retratos:
        if len(_cache_retratos) > 16:
            _cache_retratos.clear()
        daqui, antigo = virada.preferir_retrato_antigo(daqui, antigo, "data_snapshot")
        _cache_retratos[chave] = pl.concat([daqui, antigo], how="diagonal_relaxed") if not daqui.is_empty() else antigo
    return _cache_retratos[chave]


RETRATOS_DA_LISTA = (("contas_pagar_snapshot", "data_snapshot"), ("contas_pagar_snapshot_antigo", "data_snapshot"))
RETRATOS_DA_COMPOSICAO = (("composicao_snapshot", "DATA_SNAPSHOT"), ("composicao_snapshot_antigo", "data_snapshot"))
_cache_retratos: dict = {}


def _mtime(arquivo: str) -> int:
    caminho = PASTA_PARQUET / f"{arquivo}.parquet"
    return caminho.stat().st_mtime_ns if caminho.is_file() else 0


def _estado_das_viradas() -> tuple:
    return tuple(sorted((r, q.isoformat()) for r, q in virada.donas_do_dado().items()))


def assinatura_dos_retratos() -> tuple:
    return tuple(_mtime(a) for a, _c in RETRATOS_DA_LISTA + RETRATOS_DA_COMPOSICAO) + (
        _mtime("pagamentos_snapshot"),
        _mtime("pagamentos_snapshot_antigo"),
    )


def contas_pagar_do_retrato(dia: date) -> pl.DataFrame:
    chave = ("lista", dia, *(_mtime(a) for a, _c in RETRATOS_DA_LISTA), _estado_das_viradas())
    if chave in _cache_retratos:
        return _cache_retratos[chave]

    def _do_dia(arquivo: str, coluna: str) -> pl.DataFrame:
        caminho = PASTA_PARQUET / f"{arquivo}.parquet"
        if not caminho.is_file():
            return pl.DataFrame()
        return ler_parquet(caminho).lazy().filter(pl.col(coluna).cast(pl.Date) == dia).collect()

    (lista_daqui, dia_daqui), (lista_antiga, dia_antigo) = RETRATOS_DA_LISTA
    daqui, antigo = virada.preferir_retrato_antigo(
        _do_dia(lista_daqui, dia_daqui), _do_dia(lista_antiga, dia_antigo), dia_daqui, dia_antigo
    )
    partes = [p for p in (daqui, antigo) if not p.is_empty()]
    saida = pl.concat(partes, how="diagonal_relaxed") if partes else pl.DataFrame()
    if len(_cache_retratos) > 16:
        _cache_retratos.clear()
    _cache_retratos[chave] = saida
    return saida


def datas_com_retrato() -> pl.DataFrame:
    chave = ("datas", *(_mtime(a) for a, _c in RETRATOS_DA_LISTA + RETRATOS_DA_COMPOSICAO))
    if chave in _cache_retratos:
        return _cache_retratos[chave]
    partes = []
    for arquivo, coluna in RETRATOS_DA_LISTA + RETRATOS_DA_COMPOSICAO:
        caminho = PASTA_PARQUET / f"{arquivo}.parquet"
        if caminho.is_file():
            partes.append(
                ler_parquet(caminho)
                .lazy()
                .select(
                    pl.col("REVENDA").cast(pl.Utf8),
                    pl.col(coluna).cast(pl.Date).alias("data_snapshot"),
                )
                .unique()
                .collect()
            )
    saida = pl.concat(partes).unique() if partes else pl.DataFrame()
    _cache_retratos[chave] = saida
    return saida


def datas_de_snapshot(base: pl.DataFrame) -> list[date]:
    if base.is_empty() or "data_snapshot" not in base.columns:
        return []
    try:
        datas = (
            base.select(pl.col("data_snapshot").cast(pl.Date, strict=False))
            .drop_nulls()
            .unique()
            .sort("data_snapshot", descending=True)
        )
    except Exception as exc:
        print(f"Snapshot: nao deu pra listar as datas -- {exc}")
        return []
    return datas["data_snapshot"].to_list()


def justificativas() -> pl.DataFrame:
    return _carregar("justificativas_contas_pagar")


def verificacao_diaria() -> pl.DataFrame:
    return _carregar("verificacao_diaria")


def pipeline_jobs() -> pl.DataFrame:
    return _carregar("pipeline_jobs")


def controle_envio_extratos() -> pl.DataFrame:
    return _carregar("controle_envio_extratos", fixar=False)


def avisos_da_baixa() -> dict[str, dict]:
    config_baixa = carregar_json("baixa_control")
    if not (config_baixa.get("rotina_noturna") or {}).get("habilitada", False):
        return {}
    base = _carregar("baixa_control")
    if base.is_empty() or not {"id_unico", "situacao"} <= set(base.columns):
        return {}
    so_estas = (config_baixa.get("rotina_noturna") or {}).get("revendas")
    if so_estas is not None and "revenda" in base.columns:
        chaves = {chave_revenda(r) for r in so_estas}
        base = base.filter(
            pl.col("revenda").map_elements(lambda r: chave_revenda(r or "") in chaves, return_dtype=pl.Boolean)
        )
    textos = config_baixa.get("avisos_na_tela") or {}
    chave = (len(base), base["executado_em"].max() if "executado_em" in base.columns else None, id(textos))
    if _cache_avisos_baixa.get("chave") != chave:
        avisos = {}
        for r in base.iter_rows(named=True):
            situacao = r["situacao"]
            diferencas = str(r.get("diferencas") or "")
            if situacao == "ja_baixada" and diferencas:
                situacao = "ja_baixada_diferente"
            texto = textos.get(situacao)
            if not texto:
                continue
            quando = r.get("executado_em")
            avisos[str(r["id_unico"])] = {
                "nivel": texto.get("nivel", "falha"),
                "rotulo": texto.get("rotulo", situacao),
                "detalhe": diferencas if situacao == "ja_baixada_diferente" else str(r.get("motivo") or ""),
                "dia": quando.date() if quando else None,
            }
        _cache_avisos_baixa.update(chave=chave, avisos=avisos)
    return _cache_avisos_baixa["avisos"]


_cache_avisos_baixa: dict = {}


def farol_original() -> pl.DataFrame:
    if not carregar_json("parametros_financeiro").get("espelhar_app_antigo"):
        return pl.DataFrame()
    return _carregar("farol_original")


_cache_icones: dict = {}


def _desvinculados() -> tuple[tuple, set]:
    from core import manual_arquivo

    arquivo = manual_arquivo.caminho("desvinculados")
    marca = (arquivo.stat().st_mtime_ns, arquivo.stat().st_size) if arquivo.is_file() else (0, 0)
    return marca, manual_arquivo.desvinculados()


def _sem_os_desvinculados(base: pl.DataFrame, fora: set) -> pl.DataFrame:
    rede = [(i, r) for i, origem, r in fora if origem == "rede"]
    if base.is_empty() or not rede or not {"id_unico", "caminho"} <= set(base.columns):
        return base
    tirar = pl.DataFrame(rede, schema={"id_unico": pl.Utf8, "_ref": pl.Utf8}, orient="row")
    return (
        base.with_columns(
            pl.col("id_unico").cast(pl.Utf8),
            pl.col("caminho")
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.replace_all("/", "\\", literal=True)
            .str.to_lowercase()
            .alias("_ref"),
        )
        .join(tirar, on=["id_unico", "_ref"], how="anti")
        .drop("_ref")
    )


def _vinculos_da_rede() -> tuple[tuple, pl.DataFrame]:
    marca, fora = _desvinculados()
    chave = tuple(
        (PASTA_PARQUET / f"{n}.parquet").stat().st_mtime_ns if (PASTA_PARQUET / f"{n}.parquet").is_file() else 0
        for n in ("vinculos_rede", "vinculos_ocr")
    ) + (marca,)
    partes = []
    antigo = _carregar("vinculos_rede")
    if not antigo.is_empty() and {"id_unico", "existe", "veredito", "caminho"} <= set(antigo.columns):
        partes.append(
            antigo.select(
                "id_unico",
                "caminho",
                pl.col("tipo").cast(pl.Utf8),
                pl.col("existe").cast(pl.Boolean, strict=False),
                pl.col("veredito").cast(pl.Utf8),
                pl.col("casa_vencimento").cast(pl.Boolean, strict=False),
            )
        )
    pelo_conteudo = _carregar("vinculos_ocr")
    if not pelo_conteudo.is_empty():
        partes.append(
            pelo_conteudo.select(
                "id_unico",
                "caminho",
                pl.col("tipo").cast(pl.Utf8).fill_null("NF"),
                pl.lit(True).alias("existe"),
                (
                    pl.col("veredito").cast(pl.Utf8) if "veredito" in pelo_conteudo.columns else pl.lit(None, pl.Utf8)
                ).alias("veredito"),
                pl.lit(True).alias("casa_vencimento"),
            )
        )
    return chave, _sem_os_desvinculados(pl.concat(partes) if partes else pl.DataFrame(), fora)


def icones_da_rede() -> dict:
    chave, base = _vinculos_da_rede()
    if base.is_empty():
        return {}
    if chave not in _cache_icones:
        existem = base.filter(pl.col("existe").cast(pl.Boolean, strict=False).fill_null(False))
        acende = existem.filter(
            pl.col("tipo").is_not_null() & (pl.col("tipo").cast(pl.Utf8) != "")
            | pl.col("casa_vencimento").cast(pl.Boolean, strict=False).fill_null(False)
        )["id_unico"].unique()
        pix = existem.group_by("id_unico").agg(
            (pl.col("veredito").fill_null("indeterminado") == "sem_boleto").all().alias("pix")
        )
        pix = pix.filter(pl.col("id_unico").is_in(acende.to_list()))
        _cache_icones.clear()
        _cache_icones[chave] = dict(
            zip(pix["id_unico"].to_list(), ["pix" if p else "olho" for p in pix["pix"].to_list()])
        )
    return _cache_icones[chave]


_cache_abrir: dict = {}


def pdf_da_rede() -> dict:
    chave, base = _vinculos_da_rede()
    if base.is_empty():
        return {}
    if chave not in _cache_abrir:
        acesos = list(icones_da_rede())
        if not acesos:
            return {}
        veredito = pl.col("veredito").fill_null("indeterminado")
        escolhido = (
            base.filter(
                pl.col("existe").cast(pl.Boolean, strict=False).fill_null(False) & pl.col("id_unico").is_in(acesos)
            )
            .with_columns(
                pl.when(veredito == "sem_boleto")
                .then(0)
                .when(veredito != "com_boleto")
                .then(1)
                .otherwise(2)
                .alias("_ordem")
            )
            .sort(["id_unico", "_ordem"])
            .unique("id_unico", keep="first")
        )
        _cache_abrir.clear()
        _cache_abrir[chave] = dict(zip(escolhido["id_unico"].to_list(), escolhido["caminho"].to_list()))
    return _cache_abrir[chave]


def quantos_da_rede_por_titulo() -> dict:
    from core.rede_documentos import documento_pelo_nome, repete_algum

    vinculos = _vinculos_com_origem()
    if vinculos.is_empty():
        return {}
    documentos_por_titulo: dict[str, list] = {}
    caminhos_vistos = set()
    for ident, caminho in vinculos.filter(pl.col("existe").fill_null(False)).select("id_unico", "caminho").iter_rows():
        if not caminho or (ident, str(caminho).lower()) in caminhos_vistos:
            continue
        caminhos_vistos.add((ident, str(caminho).lower()))
        documento = documento_pelo_nome(Path(caminho).name)
        vistos = documentos_por_titulo.setdefault(ident, [])
        if not repete_algum(documento, vistos):
            vistos.append(documento)
    return {ident: len(documentos) for ident, documentos in documentos_por_titulo.items()}


def _vinculos_com_origem() -> pl.DataFrame:
    partes = []
    for arquivo, origem in (("vinculos_rede", "antigo"), ("vinculos_ocr", "conteudo")):
        base = _carregar(arquivo)
        if base.is_empty() or not {"id_unico", "caminho"} <= set(base.columns):
            continue

        def _col(nome: str, tipo=pl.Utf8, b=base) -> pl.Expr:
            return (pl.col(nome).cast(tipo, strict=False) if nome in b.columns else pl.lit(None, tipo)).alias(nome)

        partes.append(
            base.select(
                pl.col("id_unico").cast(pl.Utf8),
                pl.col("caminho").cast(pl.Utf8),
                _col("nome"),
                _col("tipo").fill_null("NF") if origem == "conteudo" else _col("tipo"),
                (pl.lit(True) if origem == "conteudo" else _col("existe", pl.Boolean).fill_null(False)).alias("existe"),
                pl.lit(origem).alias("origem"),
                _col("automatico", pl.Boolean),
                _col("vinculado_por"),
                _col("leitura"),
            )
        )
    if not partes:
        return pl.DataFrame()
    return _sem_os_desvinculados(pl.concat(partes, how="vertical_relaxed"), _desvinculados()[1])


def titulos_do_mesmo_boleto(base_id: str) -> list[str]:
    base = _vinculos_com_origem()
    if base.is_empty() or "tipo" not in base.columns:
        return []
    boletos = base.filter((pl.col("id_unico") == base_id) & (pl.col("tipo").str.to_uppercase() == "FATURA"))["caminho"]
    if boletos.is_empty():
        return []
    outros = base.filter(pl.col("caminho").is_in(boletos.to_list()) & (pl.col("id_unico") != base_id))["id_unico"]
    return sorted(set(outros.to_list()))


def vinculos_de_fora(base_id: str) -> list[dict]:
    base = _vinculos_com_origem()
    if base.is_empty():
        return []
    return (
        base.filter(pl.col("id_unico") == base_id)
        .with_columns(pl.col("caminho").str.to_lowercase().alias("_caminho"))
        .unique("_caminho", keep="first", maintain_order=True)
        .drop("_caminho")
        .to_dicts()
    )


_cache_origem: dict = {}


def origem_do_olho_da_rede() -> dict:
    chave, _base = _vinculos_da_rede()
    if chave not in _cache_origem:
        abrir, base, fora = pdf_da_rede(), _vinculos_com_origem(), {}
        if abrir and not base.is_empty():
            escolhidos = pl.DataFrame(
                {"id_unico": list(abrir), "caminho": list(abrir.values())},
                schema={"id_unico": pl.Utf8, "caminho": pl.Utf8},
            )
            achados = escolhidos.join(base, on=["id_unico", "caminho"], how="inner").unique("id_unico", keep="first")
            fora = {r["id_unico"]: r for r in achados.iter_rows(named=True)}
        _cache_origem.clear()
        _cache_origem[chave] = fora
    return _cache_origem[chave]


_cache_xml: dict = {}


def referencia_do_xml(xml: dict) -> str:
    from core import manual_arquivo

    return manual_arquivo.referencia_do_xml(xml.get("chave"), xml.get("arquivo"))


def xml_dos_titulos() -> dict:
    arquivo = PASTA_PARQUET / "vinculos_xml.parquet"
    desvinculados, fora = _desvinculados()
    marca = (arquivo.stat().st_mtime_ns if arquivo.is_file() else 0, desvinculados)
    if marca not in _cache_xml:
        base = _carregar("vinculos_xml")
        xmls = {}
        if not base.is_empty() and {"id_unico", "arquivo"} <= set(base.columns):
            chaves = base["chave"].cast(pl.Utf8).to_list() if "chave" in base.columns else [None] * base.height
            tirados = {(i, r) for i, origem, r in fora if origem == "xml"}
            xmls = {
                i: a
                for i, a, c in zip(base["id_unico"].cast(pl.Utf8).to_list(), base["arquivo"].to_list(), chaves)
                if (i, referencia_do_xml({"chave": c, "arquivo": a})) not in tirados
            }
        _cache_xml.clear()
        _cache_xml[marca] = xmls
    return _cache_xml[marca]


_cache_999: dict = {}


def vinculos_999() -> dict:
    from core.manual_arquivo import chave_999

    arquivo = PASTA_PARQUET / "vinculos_999.parquet"
    marca = arquivo.stat().st_mtime_ns if arquivo.is_file() else 0
    if marca not in _cache_999:
        base = _carregar("vinculos_999")
        _cache_999.clear()
        _cache_999[marca] = (
            {}
            if base.is_empty() or not {"revenda", "data", "documento", "caminho"} <= set(base.columns)
            else {
                chave_999(r["revenda"], r["data"], r.get("descricao"), r["documento"]): r
                for r in base.iter_rows(named=True)
            }
        )
    return _cache_999[marca]


def xml_do_titulo(base_id: str) -> dict | None:
    base = _carregar("vinculos_xml")
    if base.is_empty() or "id_unico" not in base.columns:
        return None
    achado = base.filter(pl.col("id_unico").cast(pl.Utf8) == base_id).head(1).to_dicts()
    return achado[0] if achado else None


def vales_provisorios() -> pl.DataFrame:
    return _carregar("vales_provisorios")


def extratos_bancos() -> pl.DataFrame:
    return _carregar("extratos_bancos")


def batida_diaria() -> pl.DataFrame:
    return _carregar("batida_diaria")


def batida_diaria_geral() -> pl.DataFrame:
    return _carregar("batida_diaria_geral")


def saldo_banco_999() -> pl.DataFrame:
    return _carregar("saldo_banco_999")


def fornecedores() -> pl.DataFrame:
    return _carregar("fornecedor")


def clientes() -> pl.DataFrame:
    return _carregar("clientes")


def codigos_despesa() -> pl.DataFrame:
    return _carregar("cod_despesa")


def centros_custo() -> pl.DataFrame:
    return _carregar("centros_custo")


def plano_contas() -> pl.DataFrame:
    return _carregar("plano_contas")


def especies_do_control(revenda: str | None) -> list[tuple[str, int, str]]:
    partes = [
        filtrar_por_revenda(base, revenda).select("num_doc")
        for base in (contas_pagar(), titulos_pagos())
        if "num_doc" in base.columns
    ]
    if not partes:
        return []
    contagem = (
        pl.concat(partes)
        .with_columns(pl.col("num_doc").str.slice(0, 3).str.strip_chars().str.to_uppercase().alias("especie"))
        .filter(pl.col("especie").str.contains(r"^[A-Z]{2,3}$"))
        .group_by("especie")
        .agg(pl.len().alias("titulos"), pl.col("num_doc").max().alias("exemplo"))
        .sort(["titulos", "especie"], descending=[True, False])
    )
    return [(e, int(n), str(x)) for e, n, x in contagem.iter_rows()]


def revendas_da_url(revenda: str | None) -> list[str] | None:
    if not revenda or chave_revenda(revenda) == "HOLDING":
        return None
    grupo = REVENDAS_POR_GRUPO.get(revenda.upper())
    return list(grupo) if grupo else [revenda]


def linhas_por_pagina(revenda: str | None) -> int:
    config = carregar_json("parametros_financeiro").get("linhas_por_pagina_contas_pagar") or {}
    por_chave = {chave_revenda(nome): int(quantas) for nome, quantas in config.items() if not str(nome).startswith("_")}
    alvo = chave_revenda(revenda)
    if alvo in por_chave:
        return por_chave[alvo]
    tamanhos = [por_chave[chave_revenda(m)] for m in revendas_da_url(revenda) or [] if chave_revenda(m) in por_chave]
    return max(tamanhos) if tamanhos else 50


def extratos_fabricas_totais(fixar: bool = True) -> pl.DataFrame:
    return _carregar("extratos_fabricas_totais", fixar=fixar)


def extratos_fabricas_tabela() -> pl.DataFrame:
    base = _carregar("extratos_fabricas_tabela")
    if base.is_empty() or not {"REVENDA", "fabrica", "data_hora"} <= set(base.columns):
        return base
    quando = pl.col("data_hora").cast(pl.Datetime, strict=False)
    base = base.filter(quando.is_not_null() & (quando.dt.year() > 1900))
    return base.filter(quando == quando.max().over(["REVENDA", "fabrica"]))


def extratos_fabricas_leituras(fixar: bool = True) -> pl.DataFrame:
    base = _carregar("extratos_fabricas_tabela", fixar=fixar)
    if base.is_empty() or "data_hora" not in base.columns:
        return base
    quando = pl.col("data_hora").cast(pl.Datetime, strict=False)
    return base.filter(quando.is_not_null() & (quando.dt.year() > 1900))


def banco_mar_historico() -> pl.DataFrame:
    return _carregar("banco_mar_historico")


def ultima_leitura_por_fabrica(base: pl.DataFrame) -> pl.DataFrame:
    if base.is_empty() or "fabrica" not in base.columns:
        return base
    if "data_hora" not in base.columns:
        return base
    return base.sort("data_hora", descending=True, nulls_last=True).unique(
        subset=["REVENDA", "fabrica"], keep="first", maintain_order=True
    )


def filtrar_por_revenda(base: pl.DataFrame, revenda: str | None) -> pl.DataFrame:
    alvos = revendas_da_url(revenda)
    if base.is_empty() or alvos is None or "REVENDA" not in base.columns:
        return base
    reais = casar_revendas(base["REVENDA"].unique().to_list(), alvos)
    return base.filter(pl.col("REVENDA").is_in(reais))


def abreviacao_centro_custo(revenda: str | None) -> dict[str, str]:
    config = carregar_json("centro_custo") or {}
    for nome, mapa in (config.get("por_revenda") or {}).items():
        if chave_revenda(nome) == chave_revenda(revenda):
            return {str(k): str(v) for k, v in (mapa or {}).items()}
    return {}


def com_centro_custo_abreviado(
    base: pl.DataFrame, revenda: str | None, coluna: str = "PGMOVMOV_CCUSTO_1"
) -> pl.DataFrame:
    if base.is_empty() or coluna not in base.columns:
        return base
    numero = pl.col(coluna).cast(pl.Utf8).fill_null("")
    if "REVENDA" in base.columns and base["REVENDA"].n_unique() > 1:
        chaves = {}
        for nome in base["REVENDA"].drop_nulls().unique().to_list():
            for codigo, texto in abreviacao_centro_custo(nome).items():
                chaves[f"{nome}|{codigo}"] = texto
        par = pl.col("REVENDA").cast(pl.Utf8).fill_null("") + "|" + numero
        sigla = par.replace_strict(chaves, default="")
    else:
        unica = base["REVENDA"][0] if "REVENDA" in base.columns and base.height else revenda
        sigla = numero.replace_strict(abreviacao_centro_custo(unica), default="")
    return base.with_columns(
        pl.when(numero == "")
        .then(pl.lit(""))
        .when(sigla == "")
        .then(numero)
        .otherwise(numero + " - " + sigla)
        .alias("CENTRO_CUSTO")
    )


def janela(base: pl.DataFrame, de: date | None, ate: date | None) -> pl.DataFrame:
    if base.is_empty() or "DATA" not in base.columns:
        return base
    if de is not None:
        base = base.filter(pl.col("DATA") >= de)
    if ate is not None:
        base = base.filter(pl.col("DATA") <= ate)
    return base


def com_nome_fornecedor(base: pl.DataFrame, coluna_cgc: str = "PGMOVMOV_CGC") -> pl.DataFrame:
    if base.is_empty():
        return base
    if "FORNECEDOR" in base.columns:
        if "TIPO_FORNECEDOR" in base.columns:
            return base
        return base.with_columns(pl.lit(None, dtype=pl.Utf8).alias("TIPO_FORNECEDOR"))

    forn = fornecedores()
    if forn.is_empty() or coluna_cgc not in base.columns:
        return base.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("FORNECEDOR"),
            pl.lit(None, dtype=pl.Utf8).alias("TIPO_FORNECEDOR"),
        )
    coluna_nome = "FORNECEDOR" if "FORNECEDOR" in forn.columns else "PGCADFOR_RAZAO"
    coluna_tipo = "TIPO_FORNECEDOR" if "TIPO_FORNECEDOR" in forn.columns else "PGCADFTP_DESCR"
    forn = forn.select(
        pl.col("REVENDA"),
        pl.col("PGCADFOR_CGC").alias(coluna_cgc),
        pl.col(coluna_nome).alias("FORNECEDOR"),
        pl.col(coluna_tipo).alias("TIPO_FORNECEDOR"),
    ).unique(subset=["REVENDA", coluna_cgc], keep="first")
    return base.join(forn, on=["REVENDA", coluna_cgc], how="left")


def resumo_caixa(pagar: pl.DataFrame, receber: pl.DataFrame) -> dict[str, float]:
    entra = float(receber["CRMOVMOV_VALOR"].sum() or 0) if not receber.is_empty() else 0.0
    sai = float(pagar["PGMOVMOV_VALOR"].sum() or 0) if not pagar.is_empty() else 0.0
    return {"entra": entra, "sai": sai, "saldo": entra - sai}


def por_dia(pagar: pl.DataFrame, receber: pl.DataFrame) -> pl.DataFrame:
    partes = []
    if not pagar.is_empty() and "DATA" in pagar.columns:
        partes.append(pagar.drop_nulls("DATA").group_by("DATA").agg(pl.col("PGMOVMOV_VALOR").sum().alias("SAI")))
    if not receber.is_empty() and "DATA" in receber.columns:
        partes.append(receber.drop_nulls("DATA").group_by("DATA").agg(pl.col("CRMOVMOV_VALOR").sum().alias("ENTRA")))
    if not partes:
        return pl.DataFrame()

    base = partes[0]
    for parte in partes[1:]:
        base = base.join(parte, on="DATA", how="full", coalesce=True)

    for coluna in ("ENTRA", "SAI"):
        if coluna not in base.columns:
            base = base.with_columns(pl.lit(0.0).alias(coluna))

    return (
        base.with_columns(pl.col("ENTRA").fill_null(0.0), pl.col("SAI").fill_null(0.0))
        .sort("DATA")
        .with_columns((pl.col("ENTRA") - pl.col("SAI")).alias("SALDO_DIA"))
        .with_columns(pl.col("SALDO_DIA").cum_sum().alias("SALDO_ACUMULADO"))
    )


class PreAuditoriaDoTitulo(NamedTuple):
    gerado_em: datetime | None
    apontamentos: list[dict]


_cache_pre_auditoria: dict = {}
_ORDEM_DA_GRAVIDADE = {"erro": 0, "atenção": 1}


def pre_auditoria_dos_titulos() -> dict[str, PreAuditoriaDoTitulo]:
    marca = (
        str(_pasta_do_arquivo("pre_auditoria")),
        versao_lida("pre_auditoria"),
        versao_lida("pre_auditoria_conferidos"),
    )
    if marca in _cache_pre_auditoria:
        return _cache_pre_auditoria[marca]
    apontamentos = _carregar("pre_auditoria")
    conferidos = _carregar("pre_auditoria_conferidos")
    titulos: dict[str, PreAuditoriaDoTitulo] = {}
    if not conferidos.is_empty() and {"id_unico", "gerado_em"} <= set(conferidos.columns):
        for conferido in conferidos.select("id_unico", "gerado_em").iter_rows(named=True):
            titulos[str(conferido["id_unico"])] = PreAuditoriaDoTitulo(conferido["gerado_em"], [])
    colunas_dos_apontamentos = {"id_unico", "grupo", "gravidade", "descricao", "detalhe", "gerado_em"}
    if not apontamentos.is_empty() and colunas_dos_apontamentos <= set(apontamentos.columns):
        ordenados = apontamentos.with_columns(
            pl.col("gravidade").replace_strict(_ORDEM_DA_GRAVIDADE, default=9, return_dtype=pl.Int8).alias("_ordem")
        ).sort(["id_unico", "_ordem"], maintain_order=True)
        for linha in ordenados.iter_rows(named=True):
            id_unico = str(linha["id_unico"])
            titulo = titulos.get(id_unico) or PreAuditoriaDoTitulo(linha["gerado_em"], [])
            titulo.apontamentos.append(
                {
                    "grupo": linha["grupo"] or "",
                    "gravidade": linha["gravidade"] or "",
                    "descricao": linha["descricao"] or "",
                    "detalhe": linha["detalhe"] or "",
                }
            )
            titulos[id_unico] = titulo
    _cache_pre_auditoria.clear()
    _cache_pre_auditoria[marca] = titulos
    return titulos


_cache_pre_auditoria_999: dict = {}


def pre_auditoria_do_999() -> dict:
    from core.manual_arquivo import chave_999

    from . import pre_auditoria_999

    marca = (
        versao_lida(pre_auditoria_999.ARQUIVO_DOS_APONTAMENTOS),
        versao_lida(pre_auditoria_999.ARQUIVO_DOS_CONFERIDOS),
    )
    if marca not in _cache_pre_auditoria_999:
        linhas = pre_auditoria_999.montar_pre_auditorias(
            _carregar(pre_auditoria_999.ARQUIVO_DOS_CONFERIDOS),
            _carregar(pre_auditoria_999.ARQUIVO_DOS_APONTAMENTOS),
            chave_999,
        )
        _cache_pre_auditoria_999.clear()
        _cache_pre_auditoria_999[marca] = linhas
    return _cache_pre_auditoria_999[marca]
