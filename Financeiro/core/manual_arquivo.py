from __future__ import annotations

import contextvars
import functools
import inspect
import shutil
import threading
import time
from datetime import date, datetime
from pathlib import Path

import cachetools
import polars as pl

from core.compat import gravar_parquet, ler_parquet  # noqa: E402

PASTA_MANUAL = Path(__file__).resolve().parent.parent / "data" / "manual"

_trava = threading.Lock()
_cache = cachetools.LRUCache(maxsize=8)

_contexto: contextvars.ContextVar = contextvars.ContextVar("acao_da_tela", default=None)


def _acao(nome):
    def decorar(funcao):
        assinatura = inspect.signature(funcao)

        @functools.wraps(funcao)
        def envolvida(*args, **kwargs):
            if _contexto.get() is not None:
                return funcao(*args, **kwargs)
            try:
                argumentos = assinatura.bind_partial(*args, **kwargs).arguments
                texto = (
                    nome(argumentos)
                    if callable(nome)
                    else nome.format(**{k: v for k, v in argumentos.items() if isinstance(v, (str, int, float))})
                )
            except Exception:
                argumentos, texto = {}, nome if isinstance(nome, str) else funcao.__name__
            token = _contexto.set(
                {
                    "acao": texto,
                    "usuario": argumentos.get("usuario"),
                    "revenda": argumentos.get("revenda") if isinstance(argumentos.get("revenda"), str) else None,
                }
            )
            try:
                return funcao(*args, **kwargs)
            finally:
                _contexto.reset(token)

        return envolvida

    return decorar


def _acao_da_liberacao(argumentos: dict) -> str:
    campos = {c: v for mudanca in (argumentos.get("mudancas") or {}).values() for c, v in (mudanca or {}).items()}
    if "enviado_por" in campos:
        return "enviar (Lançamentos a Pagar)"
    if "excluido_por" in campos:
        return "excluir (Lançamentos a Pagar)"
    if "criado_por" in campos:
        return "novo lançamento (Lançamentos a Pagar)"
    if "marcado_por" in campos:
        return ("marcar" if campos["marcado_por"] else "desmarcar") + " (Lançamentos a Pagar)"
    return "conferir (Lançamentos a Pagar)"


ESQUEMA = {
    "justificativas_juros": {
        "revenda": pl.Utf8,
        "documento": pl.Utf8,
        "nome": pl.Utf8,
        "valor_original": pl.Float64,
        "dt_vencto": pl.Date,
        "dt_baixa": pl.Date,
        "dispensa_juros": pl.Float64,
        "justificativa": pl.Utf8,
        "usuario": pl.Utf8,
        "data_hora": pl.Datetime,
    },
    "envios_extratos": {
        "revenda": pl.Utf8,
        "extrato": pl.Utf8,
        "usuario": pl.Utf8,
        "enviado_em": pl.Datetime,
    },
    "entradas_manuais": {
        "id_unico": pl.Utf8,
        "revenda": pl.Utf8,
        "data_vencimento": pl.Date,
        "num_doc": pl.Utf8,
        "num_doc_normalizado": pl.Utf8,
        "tipo_doc": pl.Utf8,
        "cnpj": pl.Utf8,
        "razao_social": pl.Utf8,
        "descricao_despesa": pl.Utf8,
        "valor_original": pl.Float64,
        "lancado_por": pl.Utf8,
        "lancado_em": pl.Datetime,
    },
    "dados_manuais": {
        "id_unico": pl.Utf8,
        "revenda": pl.Utf8,
        "banco": pl.Utf8,
        "data": pl.Date,
        "hora": pl.Utf8,
        "transferencia_bancos": pl.Float64,
        "destino_transf": pl.Utf8,
        "adiantamento_romaneios": pl.Float64,
        "brinks_antes_16": pl.Float64,
        "romaneio_pendente_encerrado": pl.Float64,
        "credito_mar_utilizado": pl.Float64,
        "credito_parceiro": pl.Utf8,
        "devolucao_emprestimos": pl.Float64,
        "tipo_emprestimo_devolucao": pl.Utf8,
        "entrada_saida": pl.Utf8,
        "revenda_origem_destino": pl.Utf8,
        "transferencia_revendas": pl.Float64,
        "revenda_destino": pl.Utf8,
        "lancado_por": pl.Utf8,
        "lancado_em": pl.Datetime,
    },
    "celulas_marcadas_mare": {
        "linha_label": pl.Utf8,
        "coluna_nome": pl.Utf8,
        "marcada": pl.Boolean,
        "marcada_laranja": pl.Boolean,
        "marcado_por": pl.Utf8,
        "marcado_em": pl.Datetime,
    },
    "emprestimos_configuracoes": {
        "revenda": pl.Utf8,
        "contrato": pl.Utf8,
        "valor_credito": pl.Float64,
        "entrada": pl.Float64,
        "taxa_juros": pl.Float64,
        "atualizado_em": pl.Datetime,
        "atualizado_por": pl.Utf8,
    },
    "dados_manuais_fatias": {
        "revenda": pl.Utf8,
        "data": pl.Date,
        "gravado_em": pl.Datetime,
    },
    "marcacoes": {
        "id_unico": pl.Utf8,
        "tipo": pl.Utf8,
        "marcado_por": pl.Utf8,
        "marcado_em": pl.Datetime,
    },
    "justificativas": {
        "id_unico": pl.Utf8,
        "revenda": pl.Utf8,
        "texto": pl.Utf8,
        "atualizado_por": pl.Utf8,
        "atualizado_em": pl.Datetime,
        "criado_por": pl.Utf8,
        "criado_em": pl.Datetime,
    },
    "vinculos": {
        "id_unico": pl.Utf8,
        "caminho": pl.Utf8,
        "nome": pl.Utf8,
        "tamanho": pl.Int64,
        "modificado_em": pl.Datetime,
        "vinculado_por": pl.Utf8,
        "vinculado_em": pl.Datetime,
    },
    "desvinculados": {
        "id_unico": pl.Utf8,
        "origem": pl.Utf8,
        "referencia": pl.Utf8,
        "nome": pl.Utf8,
        "desvinculado_por": pl.Utf8,
        "desvinculado_em": pl.Datetime,
    },
    "tipos_anexo": {
        "id_unico": pl.Utf8,
        "arquivo": pl.Utf8,
        "tipo": pl.Utf8,
        "marcado_por": pl.Utf8,
        "marcado_em": pl.Datetime,
    },
    "verificacao": {
        "data": pl.Date,
        "revenda": pl.Utf8,
        "etapa": pl.Utf8,
        "marcado_por": pl.Utf8,
        "marcado_em": pl.Datetime,
    },
    "excluidos": {
        "id_unico": pl.Utf8,
        "revenda": pl.Utf8,
        "excluido_por": pl.Utf8,
        "excluido_em": pl.Datetime,
        "fora_do_control": pl.Utf8,
    },
    "pagamentos": {
        "id_unico": pl.Utf8,
        "valor_pago": pl.Float64,
        "juros": pl.Float64,
        "banco": pl.Utf8,
        "data_pagamento": pl.Date,
        "editado_por": pl.Utf8,
        "editado_em": pl.Datetime,
        "enviado_em": pl.Datetime,
        "valor_original": pl.Float64,
    },
    "partes_desfeitas": {
        "id_unico": pl.Utf8,
        "desfeito_por": pl.Utf8,
        "desfeito_em": pl.Datetime,
    },
    "partes_criadas": {
        "id_unico": pl.Utf8,
        "dividido_por": pl.Utf8,
        "dividido_em": pl.Datetime,
    },
    "fora_da_fila": {
        "id_unico": pl.Utf8,
        "tirado_por": pl.Utf8,
        "tirado_em": pl.Datetime,
    },
    "assinaturas": {
        "usuario": pl.Utf8,
        "imagem": pl.Binary,
        "origem": pl.Utf8,
        "de_onde": pl.Utf8,
        "cadastrado_em": pl.Datetime,
    },
    "liberacoes": {
        "id_arquivo": pl.Utf8,
        "revenda": pl.Utf8,
        "tipo_doc": pl.Utf8,
        "numero": pl.Utf8,
        "parcela": pl.Utf8,
        "cnpj_fornecedor": pl.Utf8,
        "emissao": pl.Date,
        "vencimento": pl.Date,
        "valor": pl.Float64,
        "rateio": pl.Utf8,
        "por_socio": pl.Boolean,
        "socios": pl.Utf8,
        "editado_por": pl.Utf8,
        "editado_em": pl.Datetime,
        "marcado_por": pl.Utf8,
        "marcado_em": pl.Datetime,
        "enviado_por": pl.Utf8,
        "enviado_em": pl.Datetime,
        "no_control": pl.Boolean,
        "excluido_por": pl.Utf8,
        "excluido_em": pl.Datetime,
        "novo": pl.Boolean,
        "criado_por": pl.Utf8,
        "criado_em": pl.Datetime,
    },
    "lancamentos_manuais_documentos": {
        "id_arquivo": pl.Utf8,
        "revenda": pl.Utf8,
        "tipo_doc": pl.Utf8,
        "numero": pl.Utf8,
        "parcela": pl.Utf8,
        "cnpj_fornecedor": pl.Utf8,
        "emissao": pl.Date,
        "vencimento": pl.Date,
        "valor": pl.Float64,
        "rateio": pl.Utf8,
        "editado_por": pl.Utf8,
        "editado_em": pl.Datetime,
        "marcado_por": pl.Utf8,
        "marcado_em": pl.Datetime,
        "enviado_por": pl.Utf8,
        "enviado_em": pl.Datetime,
        "excluido_por": pl.Utf8,
        "excluido_em": pl.Datetime,
    },
    "lancamentos_manuais_movimento": {
        "id": pl.Utf8,
        "revenda": pl.Utf8,
        "documento": pl.Utf8,
        "data": pl.Date,
        "valor": pl.Float64,
        "historico": pl.Int64,
        "banco": pl.Int64,
        "banco_destino": pl.Int64,
        "centro_custo": pl.Int64,
        "editado_por": pl.Utf8,
        "editado_em": pl.Datetime,
        "envio_situacao": pl.Utf8,
        "envio_motivo": pl.Utf8,
        "envio_documento": pl.Utf8,
        "gravado": pl.Boolean,
        "enviado_por": pl.Utf8,
        "enviado_em": pl.Datetime,
        "novo": pl.Boolean,
        "tipo": pl.Utf8,
        "direcao": pl.Utf8,
        "criado_por": pl.Utf8,
        "criado_em": pl.Datetime,
        "excluido_por": pl.Utf8,
        "excluido_em": pl.Datetime,
        "sem_hp": pl.Boolean,
        "destino": pl.Utf8,
        "para_pagar": pl.Utf8,
        "data_lancamento": pl.Date,
        "enviado_com_data": pl.Date,
        "apagado_do_control_por": pl.Utf8,
        "apagado_do_control_em": pl.Datetime,
        "pix_da_conciliacao": pl.Utf8,
    },
    "lancamento_fiscal": {
        "id": pl.Utf8,
        "revenda": pl.Utf8,
        "chave": pl.Utf8,
        "tipo": pl.Utf8,
        "numero": pl.Utf8,
        "emitente_cnpj": pl.Utf8,
        "valor": pl.Float64,
        "envio_situacao": pl.Utf8,
        "envio_motivo": pl.Utf8,
        "gravado": pl.Boolean,
        "enviado_por": pl.Utf8,
        "enviado_em": pl.Datetime,
        "titulo_rateio": pl.Utf8,
        "titulo_vencimento": pl.Date,
        "titulo_vencimentos": pl.Utf8,
        "titulo_valor": pl.Float64,
        "titulo_entrada": pl.Date,
        "titulo_por": pl.Utf8,
        "titulo_em": pl.Datetime,
    },
    "veiculos_notas": {
        "id": pl.Utf8,
        "revenda": pl.Utf8,
        "chave": pl.Utf8,
        "numero": pl.Utf8,
        "emissao": pl.Date,
        "emitente_cnpj": pl.Utf8,
        "fornecedor": pl.Utf8,
        "valor": pl.Float64,
        "vencimento": pl.Date,
        "placa": pl.Utf8,
        "placa_2": pl.Utf8,
        "empilhadeira": pl.Boolean,
        "km": pl.Int64,
        "centro_custo": pl.Utf8,
        "rateio_centros": pl.Utf8,
        "tipo": pl.Utf8,
        "controle": pl.Utf8,
        "servico": pl.Utf8,
        "servico_mecanico": pl.Utf8,
        "informado_por": pl.Utf8,
        "informado_em": pl.Datetime,
        "origem": pl.Utf8,
    },
    "vinculos_999": {
        "revenda": pl.Utf8,
        "data": pl.Date,
        "descricao": pl.Utf8,
        "documento": pl.Utf8,
        "caminho": pl.Utf8,
        "nome": pl.Utf8,
        "vinculado_por": pl.Utf8,
        "vinculado_em": pl.Datetime,
    },
}


def caminho(assunto: str) -> Path:
    from core import pastas_da_sessao

    if pastas_da_sessao.manual_do_segundo_erp(assunto):
        return pastas_da_sessao.PASTA_DO_MANUAL_DO_SEGUNDO_ERP / f"{assunto}.parquet"
    return PASTA_MANUAL / f"{assunto}.parquet"


def _chave(alvo: Path) -> tuple:
    info = alvo.stat()
    return (str(alvo), info.st_mtime_ns, info.st_size)


def ler(assunto: str) -> pl.DataFrame:
    vazio = pl.DataFrame(schema=ESQUEMA[assunto])
    alvo = caminho(assunto)
    if not alvo.is_file():
        return vazio
    chave = _chave(alvo)
    if chave not in _cache:
        try:
            _cache[chave] = _com_esquema(assunto, ler_parquet(alvo))
        except Exception:
            return vazio
    return _cache[chave]


def _com_esquema(assunto: str, tabela: pl.DataFrame) -> pl.DataFrame:
    esquema = ESQUEMA[assunto]
    faltando = [pl.lit(None, dtype=tipo).alias(nome) for nome, tipo in esquema.items() if nome not in tabela.columns]
    if faltando:
        tabela = tabela.with_columns(faltando)
    extras = [c for c in tabela.columns if c not in esquema]
    return tabela.select([*esquema.keys(), *extras])


def _gravar(assunto: str, tabela: pl.DataFrame) -> None:
    alvo = caminho(assunto)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    temporario = alvo.with_suffix(".parquet.tmp")
    gravar_parquet(tabela, temporario)
    temporario.replace(alvo)
    _cache[_chave(alvo)] = _com_esquema(assunto, tabela)


PREFIXO_TABELA = "tb_manual_"
PREFIXO_TABELA_DO_SEGUNDO_ERP = "tb_manual_segundo_erp_"

_ultimo_erro = ""


def tabela_do_espelho(assunto: str) -> str:
    from core import pastas_da_sessao

    if pastas_da_sessao.manual_do_segundo_erp(assunto):
        return f"{PREFIXO_TABELA_DO_SEGUNDO_ERP}{assunto}"
    return f"{PREFIXO_TABELA}{assunto}"


def espelhar_tudo(assuntos: list[str] | None = None) -> dict[str, str]:
    resultado = {}
    for assunto in assuntos or sorted(ESQUEMA):
        if not caminho(assunto).is_file():
            resultado[assunto] = "sem arquivo"
            continue
        tabela = ler(assunto)
        _espelhar(assunto, tabela)
        erro = ultimo_erro_banco()
        resultado[assunto] = f"erro: {erro}" if erro else f"{tabela.height} linha(s)"
    return resultado


def ultimo_erro_banco() -> str:
    return _ultimo_erro


_TEXTO_LONGO = {"para_pagar", "rateio_centros"}


def _tipo_sql(dtype, coluna: str = "") -> str:
    if dtype == pl.Datetime:
        return "DATETIME"
    if dtype == pl.Date:
        return "DATE"
    if dtype == pl.Binary:
        return "MEDIUMBLOB"
    return "TEXT" if coluna in _TEXTO_LONGO else "VARCHAR(255)"


_espelho_conferido: set[str] = set()


def _espelhar(assunto: str, tabela: pl.DataFrame) -> None:
    global _ultimo_erro
    try:
        from sqlalchemy import text

        from .db import obter_engine_manual

        nome = tabela_do_espelho(assunto)
        colunas = ", ".join(f"`{c}` {_tipo_sql(d, c)}" for c, d in ESQUEMA[assunto].items())
        engine = obter_engine_manual()
        with engine.begin() as con:
            con.execute(text(f"CREATE TABLE IF NOT EXISTS `{nome}` ({colunas}) DEFAULT CHARSET=utf8mb4"))
            if nome not in _espelho_conferido:
                existentes = {
                    linha[0].lower()
                    for linha in con.execute(
                        text(
                            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
                        ),
                        {"t": nome},
                    )
                }
                for c, d in ESQUEMA[assunto].items():
                    if c.lower() not in existentes:
                        con.execute(text(f"ALTER TABLE `{nome}` ADD COLUMN `{c}` {_tipo_sql(d, c)} NULL"))
                _espelho_conferido.add(nome)
            con.execute(text(f"DELETE FROM `{nome}`"))
            if tabela.is_empty():
                _ultimo_erro = ""
                return
            campos = list(ESQUEMA[assunto])
            marcas = ", ".join(f":{c}" for c in campos)
            nomes = ", ".join(f"`{c}`" for c in campos)
            con.execute(
                text(f"INSERT INTO `{nome}` ({nomes}) VALUES ({marcas})"),
                tabela.to_dicts(),
            )
        _ultimo_erro = ""
    except Exception as erro:
        _ultimo_erro = f"{assunto}: {str(erro)[:160]}"


def _guardar(assunto: str, tabela: pl.DataFrame) -> None:
    antes = ler(assunto)
    _gravar(assunto, tabela)
    try:
        from . import log_acoes

        log_acoes.mudancas(assunto, antes, tabela, _contexto.get())
    except Exception:
        pass


ASSUNTOS_POR_TITULO = (
    "marcacoes",
    "justificativas",
    "vinculos",
    "desvinculados",
    "tipos_anexo",
    "excluidos",
    "pagamentos",
    "partes_desfeitas",
    "partes_criadas",
    "fora_da_fila",
)

TESTES_DA_VIRADA = {
    "marcacoes": ("marcado_em", None),
    "pagamentos": ("editado_em", None),
    "partes_desfeitas": ("desfeito_em", None),
    "partes_criadas": ("dividido_em", None),
    "fora_da_fila": ("tirado_em", None),
    "justificativas": ("atualizado_em", "revenda"),
    "verificacao": ("marcado_em", "revenda"),
    "excluidos": ("excluido_em", "revenda"),
    "dados_manuais": ("lancado_em", "revenda"),
    "dados_manuais_fatias": ("gravado_em", "revenda"),
    "entradas_manuais": ("lancado_em", "revenda"),
}


@_acao("tirar testes da revenda")
def tirar_testes_da_revenda(revenda: str, ids: set[str], ate: datetime, pasta_backup: Path) -> dict[str, int]:
    from core import revendas as cadastro_revendas
    from core.config import chave_revenda, membros_do_grupo

    sairam = {}
    alvo = chave_revenda(cadastro_revendas.nome_oficial(revenda) or revenda)
    with _trava:
        for assunto, (coluna_hora, coluna_revenda) in TESTES_DA_VIRADA.items():
            base = ler(assunto)
            if base.is_empty():
                continue
            if coluna_revenda:
                nomes = [n for n in base[coluna_revenda].cast(pl.Utf8).unique().to_list() if n]
                da_virada = [
                    n
                    for n in nomes
                    if alvo
                    in {chave_revenda(cadastro_revendas.nome_oficial(m) or m) for m in membros_do_grupo(n) or [n]}
                ]
                da_revenda = pl.col(coluna_revenda).cast(pl.Utf8).is_in(da_virada)
            else:
                da_revenda = pl.col("id_unico").cast(pl.Utf8).str.replace(r"_clone\d*$", "").is_in(list(ids))
            antes = pl.col(coluna_hora).cast(pl.Datetime, strict=False) <= ate
            sai = (da_revenda & antes.fill_null(True)).fill_null(False)
            tirar = base.filter(sai)
            if tirar.is_empty():
                continue
            pasta_backup.mkdir(parents=True, exist_ok=True)
            gravar_parquet(tirar, pasta_backup / f"{assunto}.parquet")
            _guardar(assunto, base.filter(~sai))
            _espelhar(assunto, base.filter(~sai))
            sairam[assunto] = tirar.height
    return sairam


@_acao("trocar ids dos títulos")
def remapear_ids(troca, pasta_backup: Path) -> dict[str, int]:
    mudou = {}
    with _trava:
        for assunto in ASSUNTOS_POR_TITULO:
            base = ler(assunto)
            if base.is_empty():
                continue
            novos = base["id_unico"].map_elements(troca, return_dtype=pl.Utf8)
            n = int((novos != base["id_unico"]).fill_null(False).sum())
            if not n:
                continue
            pasta_backup.mkdir(parents=True, exist_ok=True)
            copia = pasta_backup / f"{assunto}.parquet"
            if not copia.exists():
                shutil.copy2(caminho(assunto), copia)
            _guardar(assunto, base.with_columns(novos.alias("id_unico")))
            mudou[assunto] = n
    return mudou


@_acao("levar os vistos ao título de agora")
def levar_vistos(mapa: dict[str, str], tipos: tuple[str, ...] | None = None) -> int:
    if not mapa:
        return 0
    with _trava:
        base = ler("marcacoes")
        velhos = base.filter(pl.col("id_unico").is_in(list(mapa)) & pl.col("marcado_por").is_not_null())
        if tipos is not None:
            velhos = velhos.filter(pl.col("tipo").is_in(list(tipos)))
        if velhos.is_empty():
            return 0
        novos = (
            velhos.with_columns(pl.col("id_unico").replace_strict(mapa, return_dtype=pl.Utf8))
            .join(base.select("id_unico", "tipo").unique(), on=["id_unico", "tipo"], how="anti")
            .unique(subset=["id_unico", "tipo"], keep="last", maintain_order=True)
        )
        if novos.is_empty():
            return 0
        _guardar("marcacoes", pl.concat([base, novos], how="vertical_relaxed"))
        return novos.height


def tirar_pagar_levado(mapa: dict[str, str]) -> int:
    if not mapa:
        return 0
    with _trava:
        base = ler("marcacoes")
        do_pagar = base.filter((pl.col("tipo") == "pagar") & pl.col("marcado_por").is_not_null())
        copiados = (
            do_pagar.filter(pl.col("id_unico").is_in(list(mapa)))
            .with_columns(pl.col("id_unico").replace_strict(mapa, return_dtype=pl.Utf8))
            .select("id_unico", "marcado_por", "marcado_em")
            .with_columns(pl.lit(True).alias("_copia"))
        )
        if copiados.is_empty():
            return 0
        marcada = base.join(copiados, on=["id_unico", "marcado_por", "marcado_em"], how="left")
        tirar = (pl.col("tipo") == "pagar") & pl.col("_copia").fill_null(False)
        quantos = marcada.filter(tirar).height
        if not quantos:
            return 0
        _guardar("marcacoes", marcada.filter(~tirar).drop("_copia"))
        return quantos


_ultima_mudanca: dict[tuple[str, str], tuple[str, float]] = {}


def primeira_marcacao(id_unico: str, tipo: str, usuario: str, segundos: float) -> tuple[str, float] | None:
    anterior = _ultima_mudanca.get((id_unico, tipo))
    if anterior and anterior[0] != usuario and time.monotonic() - anterior[1] < segundos:
        return anterior[0], time.monotonic() - anterior[1]
    return None


def _anotar_mudanca(id_unico: str, tipo: str, usuario: str | None) -> None:
    if not usuario:
        return
    agora = time.monotonic()
    if len(_ultima_mudanca) > 1000:
        for chave in [c for c, (_q, t) in _ultima_mudanca.items() if agora - t > 600]:
            del _ultima_mudanca[chave]
    _ultima_mudanca[(id_unico, tipo)] = (usuario, agora)


@_acao("marcar {tipo}")
def marcar(id_unico: str, tipo: str, usuario: str) -> None:
    with _trava:
        base = ler("marcacoes")
        base = base.filter(~((pl.col("id_unico") == id_unico) & (pl.col("tipo") == tipo)))
        nova = pl.DataFrame(
            {
                "id_unico": [id_unico],
                "tipo": [tipo],
                "marcado_por": [usuario],
                "marcado_em": [datetime.now()],
            },
            schema=ESQUEMA["marcacoes"],
        )
        _guardar("marcacoes", pl.concat([base, nova], how="vertical_relaxed"))
        _anotar_mudanca(id_unico, tipo, usuario)


@_acao("desmarcar {tipo}")
def desmarcar(id_unico: str, tipo: str, usuario: str | None = None) -> None:
    with _trava:
        base = ler("marcacoes")
        base = base.filter(~((pl.col("id_unico") == id_unico) & (pl.col("tipo") == tipo)))
        nova = pl.DataFrame(
            {
                "id_unico": [id_unico],
                "tipo": [tipo],
                "marcado_por": [None],
                "marcado_em": [datetime.now()],
            },
            schema=ESQUEMA["marcacoes"],
        )
        _guardar("marcacoes", pl.concat([base, nova], how="vertical_relaxed"))
        _anotar_mudanca(id_unico, tipo, usuario)


COPIA_DO_ANTIGO = PASTA_MANUAL.parent / "bd_financeiro" / "copia_app_antigo.json"


def corte_do_app_antigo() -> datetime | None:
    from core.config_arquivo import carregar_json

    if not (carregar_json("parametros_financeiro") or {}).get("espelhar_app_antigo"):
        return None
    try:
        return datetime.fromtimestamp(COPIA_DO_ANTIGO.stat().st_mtime)
    except OSError:
        return None


def sem_as_cobertas(base: pl.DataFrame, coluna_hora: str = "marcado_em") -> pl.DataFrame:
    corte = corte_do_app_antigo()
    if corte is None or base.is_empty() or coluna_hora not in base.columns:
        return base
    from core import pastas_da_sessao, virada

    hora = pl.col(coluna_hora).cast(pl.Datetime, strict=False)
    revenda_do_segundo_erp = pastas_da_sessao.revenda_do_manual_do_segundo_erp()
    if revenda_do_segundo_erp is not None:
        return base.filter(hora > (virada.dona_desde(revenda_do_segundo_erp) or corte))
    das_donas = virada.ids_das_donas()
    if not das_donas or "id_unico" not in base.columns:
        return base.filter(hora > corte)
    mapa = pl.DataFrame(
        {"_id": list(das_donas), "_desde": list(das_donas.values())}, schema={"_id": pl.Utf8, "_desde": pl.Datetime}
    )
    return (
        base.with_columns(virada.id_base(pl.col("id_unico")).alias("_id"))
        .join(mapa, on="_id", how="left")
        .filter(hora > pl.coalesce(pl.col("_desde"), pl.lit(corte)))
        .drop("_id", "_desde")
    )


def marcacoes_por_chave() -> dict:
    base = sem_as_cobertas(ler("marcacoes"))
    if base.is_empty():
        return {}
    return {(linha["id_unico"], linha["tipo"]): linha["marcado_por"] for linha in base.iter_rows(named=True)}


@_acao("justificar")
def justificar(id_unico: str, revenda: str, texto: str, usuario: str, criado: tuple | None = None) -> None:
    with _trava:
        tudo = ler("justificativas")
        anterior = tudo.filter(pl.col("id_unico") == id_unico)
        base = tudo.filter(pl.col("id_unico") != id_unico)
        agora = datetime.now()
        if not anterior.is_empty() and anterior["criado_por"][-1]:
            criado = (anterior["criado_por"][-1], anterior["criado_em"][-1])
        elif not anterior.is_empty():
            criado = (anterior["atualizado_por"][-1], anterior["atualizado_em"][-1])
        elif not (criado and criado[0]):
            criado = (usuario, agora)
        nova = pl.DataFrame(
            {
                "id_unico": [id_unico],
                "revenda": [revenda],
                "texto": [(texto or "").strip()],
                "atualizado_por": [usuario],
                "atualizado_em": [agora],
                "criado_por": [criado[0]],
                "criado_em": [criado[1]],
            },
            schema=ESQUEMA["justificativas"],
        )
        _guardar("justificativas", pl.concat([base, nova], how="vertical_relaxed"))


def autoria_da_justificativa(id_unico: str) -> dict | None:
    base = ler("justificativas")
    if base.is_empty():
        return None
    linha = base.filter(pl.col("id_unico") == id_unico)
    if linha.is_empty():
        return None
    r = linha.row(-1, named=True)
    return {
        "criado_por": r.get("criado_por") or r["atualizado_por"],
        "criado_em": r.get("criado_em") or r["atualizado_em"],
        "atualizado_por": r["atualizado_por"],
        "atualizado_em": r["atualizado_em"],
    }


def justificativas_por_titulo() -> dict:
    base = ler("justificativas")
    if base.is_empty():
        return {}
    return {linha["id_unico"]: (linha["texto"] or "") for linha in base.iter_rows(named=True)}


@_acao(lambda a: f"{'marcar' if a.get('usuario') else 'desmarcar'} verificação {a.get('etapa')}")
def verificar(dia: date, revenda: str, etapa: str, usuario: str | None) -> None:
    with _trava:
        base = ler("verificacao")
        if not base.is_empty():
            base = base.filter(~((pl.col("data") == dia) & (pl.col("revenda") == revenda) & (pl.col("etapa") == etapa)))
        nova = pl.DataFrame(
            {
                "data": [dia],
                "revenda": [revenda],
                "etapa": [etapa],
                "marcado_por": [usuario],
                "marcado_em": [datetime.now()],
            },
            schema=ESQUEMA["verificacao"],
        )
        _guardar("verificacao", pl.concat([base, nova], how="vertical_relaxed"))


@_acao("justificar juros")
def justificar_juros(dados: dict) -> None:
    with _trava:
        base = ler("justificativas_juros")
        if not base.is_empty():
            base = base.filter(~((pl.col("revenda") == dados["revenda"]) & (pl.col("documento") == dados["documento"])))
        nova = pl.DataFrame(
            {c: [dados.get(c)] for c in ESQUEMA["justificativas_juros"]},
            schema=ESQUEMA["justificativas_juros"],
        )
        _guardar(
            "justificativas_juros",
            pl.concat([base, nova], how="vertical_relaxed"),
        )


def justificativas_juros() -> dict:
    base = ler("justificativas_juros")
    if base.is_empty():
        return {}
    return {(linha["revenda"], linha["documento"]): linha for linha in base.iter_rows(named=True)}


@_acao("enviar extrato {extrato}")
def registrar_envio(revenda: str, extrato: str, usuario: str) -> None:
    with _trava:
        base = ler("envios_extratos")
        nova = pl.DataFrame(
            {
                "revenda": [revenda],
                "extrato": [extrato],
                "usuario": [usuario],
                "enviado_em": [datetime.now()],
            },
            schema=ESQUEMA["envios_extratos"],
        )
        _guardar("envios_extratos", pl.concat([base, nova], how="vertical_relaxed"))


def envios_extratos() -> pl.DataFrame:
    return ler("envios_extratos")


def verificacoes_com_hora() -> dict:
    base = ler("verificacao")
    if base.is_empty():
        return {}
    return {
        (linha["data"], linha["revenda"], linha["etapa"]): (linha["marcado_por"], linha["marcado_em"])
        for linha in base.iter_rows(named=True)
    }


def verificacoes_por_dia() -> dict:
    base = ler("verificacao")
    if base.is_empty():
        return {}
    return {
        (linha["data"], linha["revenda"], linha["etapa"]): linha["marcado_por"] for linha in base.iter_rows(named=True)
    }


@_acao("classificar anexo")
def classificar_anexo(id_unico: str, arquivo: str, tipo: str | None, usuario: str) -> None:
    with _trava:
        base = ler("tipos_anexo")
        if not base.is_empty():
            base = base.filter(~((pl.col("id_unico") == id_unico) & (pl.col("arquivo") == arquivo)))
        nova = pl.DataFrame(
            {
                "id_unico": [id_unico],
                "arquivo": [arquivo],
                "tipo": [tipo],
                "marcado_por": [usuario],
                "marcado_em": [datetime.now()],
            },
            schema=ESQUEMA["tipos_anexo"],
        )
        _guardar("tipos_anexo", pl.concat([base, nova], how="vertical_relaxed"))


def tipos_de_anexo() -> dict:
    base = ler("tipos_anexo")
    if base.is_empty():
        return {}
    return {(linha["id_unico"], linha["arquivo"]): linha["tipo"] for linha in base.iter_rows(named=True)}


@_acao("vincular arquivo")
def vincular(id_unico: str, caminho, usuario: str) -> None:
    from pathlib import Path as _P

    alvo = _P(str(caminho))
    try:
        info = alvo.stat()
        tamanho, quando = info.st_size, datetime.fromtimestamp(info.st_mtime)
    except OSError:
        tamanho, quando = None, None

    with _trava:
        base = ler("vinculos")
        if not base.is_empty():
            base = base.filter(~((pl.col("id_unico") == id_unico) & (pl.col("caminho") == str(alvo))))
        nova = pl.DataFrame(
            {
                "id_unico": [id_unico],
                "caminho": [str(alvo)],
                "nome": [alvo.name],
                "tamanho": [tamanho],
                "modificado_em": [quando],
                "vinculado_por": [usuario],
                "vinculado_em": [datetime.now()],
            },
            schema=ESQUEMA["vinculos"],
        )
        _guardar("vinculos", pl.concat([base, nova], how="vertical_relaxed"))


@_acao("desvincular arquivo")
def desvincular(id_unico: str, caminho: str) -> None:
    from core import rede_documentos

    with _trava:
        base = ler("vinculos")
        if base.is_empty():
            return
        do_titulo = base.filter(pl.col("id_unico") == id_unico)
        caminhos_que_saem = {caminho}
        for caminho_gravado in do_titulo["caminho"].to_list():
            if caminho_gravado == caminho:
                continue
            atual = rede_documentos.caminho_atual(caminho_gravado)
            if atual is not None and str(atual) == caminho:
                caminhos_que_saem.add(caminho_gravado)
        _guardar(
            "vinculos",
            base.filter(~((pl.col("id_unico") == id_unico) & pl.col("caminho").is_in(list(caminhos_que_saem)))),
        )


def referencia_do_desvinculo(origem: str, referencia) -> str:
    texto = str(referencia or "").strip()
    if origem == "rede":
        return texto.replace("/", "\\").lower()
    return texto.lower() if origem == "antigo" else texto


def referencia_do_xml(chave, arquivo) -> str:
    return str(chave or arquivo or "").strip()


def _trocar_desvinculo(id_unico: str, origem: str, referencia, nome: str | None, usuario: str | None) -> None:
    ref = referencia_do_desvinculo(origem, referencia)
    with _trava:
        base = ler("desvinculados")
        if not base.is_empty():
            base = base.filter(
                ~((pl.col("id_unico") == id_unico) & (pl.col("origem") == origem) & (pl.col("referencia") == ref))
            )
        nova = pl.DataFrame(
            {
                "id_unico": [id_unico],
                "origem": [origem],
                "referencia": [ref],
                "nome": [nome],
                "desvinculado_por": [usuario],
                "desvinculado_em": [datetime.now()],
            },
            schema=ESQUEMA["desvinculados"],
        )
        _guardar("desvinculados", pl.concat([base, nova], how="vertical_relaxed"))


@_acao("desvincular {origem}")
def desvincular_de_fora(id_unico: str, origem: str, referencia, nome: str, usuario: str) -> None:
    _trocar_desvinculo(id_unico, origem, referencia, nome, usuario)


@_acao("vincular de novo {origem}")
def vincular_de_novo(id_unico: str, origem: str, referencia, usuario: str) -> None:
    _trocar_desvinculo(id_unico, origem, referencia, None, None)


def desvinculados() -> set:
    base = ler("desvinculados")
    if base.is_empty():
        return set()
    vivos = base.filter(pl.col("desvinculado_por").is_not_null())
    return set(zip(vivos["id_unico"].to_list(), vivos["origem"].to_list(), vivos["referencia"].to_list()))


def desvinculados_do_titulo(id_unico: str) -> list[dict]:
    base = ler("desvinculados")
    if base.is_empty():
        return []
    return (
        base.filter((pl.col("id_unico") == id_unico) & pl.col("desvinculado_por").is_not_null())
        .sort("desvinculado_em", descending=True)
        .to_dicts()
    )


def titulos_com_vinculo() -> set:
    base = ler("vinculos")
    if base.is_empty() or "id_unico" not in base.columns:
        return set()
    return set(base["id_unico"].drop_nulls().to_list())


def vinculos_do_titulo(id_unico: str) -> list[dict]:
    from core import rede_documentos

    base = ler("vinculos")
    if base.is_empty():
        return []
    fora = []
    caminhos_vistos = set()
    for linha in base.filter(pl.col("id_unico") == id_unico).iter_rows(named=True):
        alvo = rede_documentos.caminho_atual(linha["caminho"])
        caminho_de_agora = str(alvo) if alvo is not None else linha["caminho"]
        if caminho_de_agora.casefold() in caminhos_vistos:
            continue
        caminhos_vistos.add(caminho_de_agora.casefold())
        estado = "ok"
        if alvo is None:
            estado = "sumiu"
        else:
            try:
                info = alvo.stat()
                if linha["tamanho"] is not None and info.st_size != linha["tamanho"]:
                    estado = "mudou"
            except OSError:
                estado = "sumiu"
        fora.append({**linha, "caminho": caminho_de_agora, "estado": estado})
    return fora


_MANTER = object()


@_acao("editar pagamento")
def editar_pagamento(
    id_unico: str,
    valor_pago: float | None,
    juros: float | None,
    banco: str | None,
    usuario: str,
    data_pagamento=_MANTER,
    enviado_em=_MANTER,
    valor_original=_MANTER,
) -> None:
    editar_pagamentos(
        [
            {
                "id_unico": id_unico,
                "valor_pago": valor_pago,
                "juros": juros,
                "banco": banco,
                "data_pagamento": data_pagamento,
                "enviado_em": enviado_em,
                "valor_original": valor_original,
            }
        ],
        usuario,
    )


@_acao("editar pagamento")
def editar_pagamentos(edicoes: list[dict], usuario: str) -> None:
    if not edicoes:
        return
    with _trava:
        tudo = ler("pagamentos")
        ids = [e["id_unico"] for e in edicoes]
        anteriores = {r["id_unico"]: r for r in tudo.filter(pl.col("id_unico").is_in(ids)).iter_rows(named=True)}
        agora = datetime.now()
        novas = []
        for e in edicoes:
            anterior = anteriores.get(e["id_unico"]) or {}
            linha = {
                "id_unico": e["id_unico"],
                "valor_pago": e.get("valor_pago"),
                "juros": e.get("juros"),
                "banco": e.get("banco") or None,
                "editado_por": usuario,
                "editado_em": agora,
            }
            for campo in ("data_pagamento", "enviado_em", "valor_original"):
                valor = e.get(campo, _MANTER)
                linha[campo] = anterior.get(campo) if valor is _MANTER else valor
            novas.append(linha)
        nova = pl.DataFrame(novas, schema=ESQUEMA["pagamentos"]).unique(
            subset=["id_unico"], keep="last", maintain_order=True
        )
        base = tudo.filter(~pl.col("id_unico").is_in(ids))
        _guardar("pagamentos", pl.concat([base, nova], how="vertical_relaxed"))


@_acao("devolver pagamento a pendente")
def esquecer_pagamentos(ids) -> None:
    ids = list(ids)
    if not ids:
        return
    with _trava:
        _guardar("pagamentos", ler("pagamentos").filter(~pl.col("id_unico").is_in(ids)))


@_acao("desfazer divisão")
def desfazer_partes(ids, usuario: str | None) -> None:
    ids = list(ids)
    if not ids:
        return
    agora = datetime.now()
    with _trava:
        _guardar("pagamentos", ler("pagamentos").filter(~pl.col("id_unico").is_in(ids)))
        lapides = ler("partes_desfeitas").filter(~pl.col("id_unico").is_in(ids))
        novas = pl.DataFrame(
            {"id_unico": ids, "desfeito_por": [usuario] * len(ids), "desfeito_em": [agora] * len(ids)},
            schema=ESQUEMA["partes_desfeitas"],
        )
        _guardar("partes_desfeitas", pl.concat([lapides, novas], how="vertical_relaxed"))


def partes_desfeitas() -> set:
    base = ler("partes_desfeitas")
    return set(base["id_unico"].to_list()) if not base.is_empty() else set()


@_acao("mudar a fila de pagamento")
def anotar_fila(entraram, sairam, usuario: str | None) -> None:
    entraram, sairam = set(entraram), set(sairam)
    if not entraram and not sairam:
        return
    with _trava:
        base = ler("fora_da_fila").filter(~pl.col("id_unico").is_in(list(entraram | sairam)))
        novas = pl.DataFrame(
            {
                "id_unico": sorted(sairam),
                "tirado_por": [usuario] * len(sairam),
                "tirado_em": [datetime.now()] * len(sairam),
            },
            schema=ESQUEMA["fora_da_fila"],
        )
        _guardar("fora_da_fila", pl.concat([base, novas], how="vertical_relaxed"))


def fora_da_fila() -> set:
    base = sem_as_cobertas(ler("fora_da_fila"), "tirado_em")
    return set(base["id_unico"].to_list()) if not base.is_empty() else set()


@_acao("dividir título")
def registrar_divisao(id_parte: str, usuario: str | None) -> None:
    nova = pl.DataFrame(
        {"id_unico": [id_parte], "dividido_por": [usuario], "dividido_em": [datetime.now()]},
        schema=ESQUEMA["partes_criadas"],
    )
    with _trava:
        anteriores = ler("partes_criadas").filter(pl.col("id_unico") != id_parte)
        _guardar("partes_criadas", pl.concat([anteriores, nova], how="vertical_relaxed"))


def quem_dividiu() -> dict:
    base = ler("partes_criadas")
    if base.is_empty():
        return {}
    return {linha["id_unico"]: (linha["dividido_por"], linha["dividido_em"]) for linha in base.iter_rows(named=True)}


def enviados_em() -> dict:
    base = ler("pagamentos")
    if base.is_empty() or "enviado_em" not in base.columns:
        return {}
    base = sem_as_cobertas(base.filter(pl.col("enviado_em").is_not_null()), "enviado_em")
    return {
        linha["id_unico"]: linha["enviado_em"] for linha in base.select("id_unico", "enviado_em").iter_rows(named=True)
    }


def marcacoes_do_tipo(tipo: str) -> pl.DataFrame:
    base = sem_as_cobertas(ler("marcacoes"))
    if base.is_empty():
        return base
    return base.filter(pl.col("tipo") == tipo)


def pagamentos_por_titulo() -> dict:
    base = ler("pagamentos")
    if base.is_empty():
        return {}
    return {
        linha["id_unico"]: {
            "valor_pago": linha["valor_pago"],
            "juros": linha["juros"],
            "banco": linha["banco"],
            "data_pagamento": linha["data_pagamento"],
            "editado_por": linha["editado_por"],
            "enviado_em": linha.get("enviado_em"),
            "valor_original": linha.get("valor_original"),
        }
        for linha in base.iter_rows(named=True)
    }


@_acao("excluir título")
def excluir_titulo(id_unico: str, revenda: str, usuario: str, fora_do_control: bool = False) -> None:
    with _trava:
        base = ler("excluidos").filter(pl.col("id_unico") != id_unico)
        nova = pl.DataFrame(
            {
                "id_unico": [id_unico],
                "revenda": [revenda or None],
                "excluido_por": [usuario],
                "excluido_em": [datetime.now()],
                "fora_do_control": ["Sim" if fora_do_control else None],
            },
            schema=ESQUEMA["excluidos"],
        )
        _guardar("excluidos", pl.concat([base, nova], how="vertical_relaxed"))


@_acao("restaurar título")
def restaurar_titulo(id_unico: str) -> None:
    with _trava:
        base = ler("excluidos").filter(pl.col("id_unico") != id_unico)
        nova = pl.DataFrame(
            {
                "id_unico": [id_unico],
                "revenda": [None],
                "excluido_por": [None],
                "excluido_em": [datetime.now()],
                "fora_do_control": [None],
            },
            schema=ESQUEMA["excluidos"],
        )
        _guardar("excluidos", pl.concat([base, nova], how="vertical_relaxed"))


def titulos_excluidos() -> set:
    base = ler("excluidos")
    if base.is_empty():
        return set()
    return {linha["id_unico"] for linha in base.iter_rows(named=True) if linha["excluido_por"]}


def exclusoes() -> dict:
    base = ler("excluidos")
    if base.is_empty():
        return {}
    return {
        linha["id_unico"]: (linha["revenda"], linha["excluido_em"])
        for linha in base.iter_rows(named=True)
        if linha["excluido_por"]
    }


def excluidos_fora_do_control() -> set:
    base = ler("excluidos")
    if base.is_empty():
        return set()
    de_pe = (pl.col("excluido_por").cast(pl.Utf8).fill_null("") != "") & (
        pl.col("fora_do_control").cast(pl.Utf8).fill_null("") == "Sim"
    )
    return set(base.filter(de_pe)["id_unico"].to_list())


def titulo_ainda_excluido(excluido_em, atualizado_em) -> bool:
    if excluido_em is None or atualizado_em is None:
        return True
    return excluido_em > atualizado_em


@_acao("lançar pagamento manual")
def lancar_entrada_manual(
    id_unico: str,
    revenda: str,
    *,
    data_vencimento: date,
    num_doc: str,
    num_doc_normalizado: str,
    tipo_doc: str,
    cnpj: str,
    razao_social: str,
    descricao_despesa: str,
    valor_original: float,
    usuario: str,
) -> None:
    with _trava:
        base = ler("entradas_manuais").filter(pl.col("id_unico") != id_unico)
        nova = pl.DataFrame(
            {
                "id_unico": [id_unico],
                "revenda": [revenda or None],
                "data_vencimento": [data_vencimento],
                "num_doc": [num_doc or None],
                "num_doc_normalizado": [num_doc_normalizado or None],
                "tipo_doc": [tipo_doc or None],
                "cnpj": [cnpj or None],
                "razao_social": [razao_social or None],
                "descricao_despesa": [descricao_despesa or None],
                "valor_original": [float(valor_original)],
                "lancado_por": [usuario],
                "lancado_em": [datetime.now()],
            },
            schema=ESQUEMA["entradas_manuais"],
        )
        _guardar("entradas_manuais", pl.concat([base, nova], how="vertical_relaxed"))


def entradas_manuais(revenda: str | None = None) -> pl.DataFrame:
    base = ler("entradas_manuais")
    if base.is_empty():
        return base
    fora = titulos_excluidos()
    if fora:
        base = base.filter(~pl.col("id_unico").is_in(list(fora)))
    if revenda:
        alvo = str(revenda).strip().casefold()
        base = base.filter(pl.col("revenda").cast(pl.Utf8).str.strip_chars().str.to_lowercase() == alvo)
    return base


def id_ja_lancado(id_unico: str) -> bool:
    base = ler("entradas_manuais")
    if base.is_empty():
        return False
    return id_unico in set(base["id_unico"].to_list())


@_acao("lançar dado manual")
def lancar_dado_manual(id_unico: str, campos: dict) -> None:
    with _trava:
        base = ler("dados_manuais").filter(pl.col("id_unico") != id_unico)
        linha = {c: [campos.get(c)] for c in ESQUEMA["dados_manuais"]}
        linha["id_unico"] = [id_unico]
        nova = pl.DataFrame(linha, schema=ESQUEMA["dados_manuais"])
        _guardar("dados_manuais", pl.concat([base, nova], how="vertical_relaxed"))


@_acao("gravar dados manuais")
def substituir_fatia_dados_manuais(revenda: str, dia: date, linhas: list[dict]) -> None:
    from core import pastas_da_sessao
    from core import revendas as cadastro_revendas

    if cadastro_revendas.eh_do_segundo_erp(revenda) and not pastas_da_sessao.manual_do_segundo_erp("dados_manuais"):
        raise RuntimeError("o dado manual da revenda do segundo ERP so' e' gravado pela tela dela")
    alvo = str(revenda).strip().casefold()
    with _trava:
        base = ler("dados_manuais")
        if not base.is_empty():
            base = base.filter(
                ~(
                    (pl.col("revenda").cast(pl.Utf8).str.strip_chars().str.to_lowercase() == alvo)
                    & (pl.col("data") == dia)
                )
            )
        esquema = ESQUEMA["dados_manuais"]
        novas = []
        for linha in linhas:
            item = {c: linha.get(c) for c in esquema}
            item["id_unico"] = "|".join([alvo, str(linha.get("banco") or ""), str(dia), str(linha.get("hora") or "")])
            item["revenda"] = revenda
            item["data"] = dia
            if item.get("credito_parceiro") is not None:
                item["credito_parceiro"] = str(item["credito_parceiro"])
            novas.append(item)
        if novas:
            nova = pl.DataFrame(novas, schema=esquema)
            base = pl.concat([base, nova], how="vertical_relaxed") if not base.is_empty() else nova
        _guardar("dados_manuais", base)

        fatias = ler("dados_manuais_fatias")
        if not fatias.is_empty():
            fatias = fatias.filter(
                ~((pl.col("revenda").cast(pl.Utf8).str.to_lowercase() == alvo) & (pl.col("data") == dia))
            )
        marca = pl.DataFrame(
            {"revenda": [revenda], "data": [dia], "gravado_em": [datetime.now()]},
            schema=ESQUEMA["dados_manuais_fatias"],
        )
        _guardar(
            "dados_manuais_fatias",
            pl.concat([fatias, marca], how="vertical_relaxed") if not fatias.is_empty() else marca,
        )


@_acao("marcar célula do fluxo")
def marcar_celula_mare(linha: str, coluna: str, amarela: bool, laranja: bool, usuario: str) -> None:
    if amarela:
        laranja = False
    with _trava:
        base = ler("celulas_marcadas_mare")
        if not base.is_empty():
            base = base.filter(~((pl.col("linha_label") == linha) & (pl.col("coluna_nome") == coluna)))
        nova = pl.DataFrame(
            {
                "linha_label": [linha],
                "coluna_nome": [coluna],
                "marcada": [amarela],
                "marcada_laranja": [laranja],
                "marcado_por": [usuario],
                "marcado_em": [datetime.now()],
            },
            schema=ESQUEMA["celulas_marcadas_mare"],
        )
        _guardar(
            "celulas_marcadas_mare", pl.concat([base, nova], how="vertical_relaxed") if not base.is_empty() else nova
        )


def celulas_marcadas_mare() -> dict[str, dict]:
    base = ler("celulas_marcadas_mare")
    if base.is_empty():
        return {}
    return {
        f"{r['linha_label']}|{r['coluna_nome']}": {"amarela": bool(r["marcada"]), "laranja": bool(r["marcada_laranja"])}
        for r in base.iter_rows(named=True)
    }


@_acao("configurar empréstimo")
def guardar_config_emprestimo(linha: dict) -> None:
    with _trava:
        base = ler("emprestimos_configuracoes")
        if not base.is_empty():
            base = base.filter(
                ~((pl.col("revenda") == linha.get("revenda")) & (pl.col("contrato") == linha.get("contrato")))
            )
        nova = pl.DataFrame(
            {c: [linha.get(c)] for c in ESQUEMA["emprestimos_configuracoes"]},
            schema=ESQUEMA["emprestimos_configuracoes"],
        )
        _guardar(
            "emprestimos_configuracoes",
            pl.concat([base, nova], how="vertical_relaxed") if not base.is_empty() else nova,
        )


def configs_emprestimo() -> pl.DataFrame:
    return ler("emprestimos_configuracoes")


def fatias_dados_manuais() -> set[tuple[str, date]]:
    base = ler("dados_manuais_fatias")
    if base.is_empty():
        return set()
    return {(str(r["revenda"]).strip().casefold(), r["data"]) for r in base.iter_rows(named=True)}


def dados_manuais(revenda: str | None = None, dia: date | None = None) -> pl.DataFrame:
    base = ler("dados_manuais")
    if base.is_empty():
        return base
    if revenda:
        alvo = str(revenda).strip().casefold()
        base = base.filter(pl.col("revenda").cast(pl.Utf8).str.strip_chars().str.to_lowercase() == alvo)
    if dia is not None:
        base = base.filter(pl.col("data") == dia)
    return base


@_acao("cadastrar assinatura")
def gravar_assinatura(usuario: str, png: bytes, origem: str, de_onde: str) -> None:
    with _trava:
        base = ler("assinaturas").filter(pl.col("usuario") != usuario)
        nova = pl.DataFrame(
            {
                "usuario": [usuario],
                "imagem": [png],
                "origem": [origem],
                "de_onde": [de_onde[:250]],
                "cadastrado_em": [datetime.now()],
            },
            schema=ESQUEMA["assinaturas"],
        )
        _guardar("assinaturas", pl.concat([base, nova], how="vertical_relaxed"))


def assinatura_de(usuario: str | None) -> dict | None:
    if not usuario:
        return None
    linha = ler("assinaturas").filter(pl.col("usuario") == usuario)
    return None if linha.is_empty() else linha.row(0, named=True)


@_acao("apagar assinatura")
def apagar_assinatura(usuario: str) -> None:
    with _trava:
        _guardar("assinaturas", ler("assinaturas").filter(pl.col("usuario") != usuario))


_SO_CARIMBO = {
    "revenda",
    "marcado_por",
    "marcado_em",
    "enviado_por",
    "enviado_em",
    "no_control",
    "excluido_por",
    "excluido_em",
}


def liberacoes() -> dict:
    return {r["id_arquivo"]: r for r in ler("liberacoes").iter_rows(named=True)}


def liberacoes_excluidas() -> set:
    base = ler("liberacoes")
    if base.is_empty():
        return set()
    return set(base.filter(pl.col("excluido_por").is_not_null())["id_arquivo"].to_list())


@_acao(_acao_da_liberacao)
def gravar_liberacoes(mudancas: dict, usuario: str) -> None:
    esquema = ESQUEMA["liberacoes"]
    with _trava:
        tudo = ler("liberacoes")
        anteriores = {r["id_arquivo"]: r for r in tudo.iter_rows(named=True)}
        novas = []
        for ident, campos in mudancas.items():
            linha = {c: (anteriores.get(ident) or {}).get(c) for c in esquema}
            linha.update({c: v for c, v in campos.items() if c in esquema})
            linha["id_arquivo"] = ident
            if set(campos) - _SO_CARIMBO:
                linha.update(editado_por=usuario, editado_em=datetime.now())
            novas.append(linha)
        base = tudo.filter(~pl.col("id_arquivo").is_in(list(mudancas)))
        _guardar("liberacoes", pl.concat([base, pl.DataFrame(novas, schema=esquema)], how="vertical_relaxed"))


def _acao_do_documento_manual(argumentos: dict) -> str:
    campos = {c: v for mudanca in (argumentos.get("mudancas") or {}).values() for c, v in (mudanca or {}).items()}
    if "enviado_por" in campos:
        return "enviar (Lançamentos Manuais)"
    if "excluido_por" in campos:
        return "excluir (Lançamentos Manuais)"
    if "marcado_por" in campos:
        return ("marcar" if campos["marcado_por"] else "desmarcar") + " (Lançamentos Manuais)"
    return "conferir (Lançamentos Manuais)"


def documentos_manuais() -> dict:
    return {r["id_arquivo"]: r for r in ler("lancamentos_manuais_documentos").iter_rows(named=True)}


def documentos_manuais_excluidos() -> set:
    base = ler("lancamentos_manuais_documentos")
    if base.is_empty():
        return set()
    return set(base.filter(pl.col("excluido_por").is_not_null())["id_arquivo"].to_list())


@_acao(_acao_do_documento_manual)
def gravar_documentos_manuais(mudancas: dict, usuario: str) -> None:
    esquema = ESQUEMA["lancamentos_manuais_documentos"]
    with _trava:
        tudo = ler("lancamentos_manuais_documentos")
        anteriores = {r["id_arquivo"]: r for r in tudo.iter_rows(named=True)}
        novas = []
        for ident, campos in mudancas.items():
            linha = {c: (anteriores.get(ident) or {}).get(c) for c in esquema}
            linha.update({c: v for c, v in campos.items() if c in esquema})
            linha["id_arquivo"] = ident
            if set(campos) - _SO_CARIMBO:
                linha.update(editado_por=usuario, editado_em=datetime.now())
            novas.append(linha)
        base = tudo.filter(~pl.col("id_arquivo").is_in(list(mudancas)))
        _guardar(
            "lancamentos_manuais_documentos",
            pl.concat([base, pl.DataFrame(novas, schema=esquema)], how="vertical_relaxed"),
        )


_SO_ENVIO = {
    "revenda",
    "envio_situacao",
    "envio_motivo",
    "envio_documento",
    "gravado",
    "enviado_por",
    "enviado_em",
    "excluido_por",
    "excluido_em",
    "destino",
    "para_pagar",
    "enviado_com_data",
    "apagado_do_control_por",
    "apagado_do_control_em",
}


def _acao_do_movimento_manual(argumentos: dict) -> str:
    campos = {c for mudanca in (argumentos.get("mudancas") or {}).values() for c in (mudanca or {})}
    if "apagado_do_control_por" in campos:
        return "apagar do ERP (Lançamentos Manuais)"
    if "enviado_por" in campos:
        return "enviar movimento (Lançamentos Manuais)"
    if "excluido_por" in campos:
        return "excluir movimento (Lançamentos Manuais)"
    if "criado_por" in campos:
        return "novo movimento (Lançamentos Manuais)"
    return "conferir movimento (Lançamentos Manuais)"


def movimentos_manuais() -> dict:
    return {r["id"]: r for r in ler("lancamentos_manuais_movimento").iter_rows(named=True)}


def movimentos_novos() -> list[dict]:
    base = ler("lancamentos_manuais_movimento")
    if base.is_empty():
        return []
    return [r for r in base.iter_rows(named=True) if r.get("novo") and not r.get("excluido_por")]


def lancamentos_fiscais() -> dict:
    return {r["id"]: r for r in ler("lancamento_fiscal").iter_rows(named=True)}


def lancamentos_fiscais_no_control() -> set:
    base = ler("lancamento_fiscal")
    if base.is_empty():
        return set()
    return set(base.filter(pl.col("envio_situacao").is_in(["lancada", "ja_lancada"]))["chave"].to_list())


@_acao("enviar (Importar notas)")
def gravar_lancamentos_fiscais(mudancas: dict, usuario: str) -> None:
    _gravar_lancamento_fiscal(mudancas)


@_acao("ajustar o título (Importar notas)")
def gravar_titulos_fiscais(mudancas: dict, usuario: str) -> None:
    _gravar_lancamento_fiscal(mudancas)


def chave_999(revenda, data, descricao, documento) -> tuple:
    from core.config import chave_revenda

    return (chave_revenda(str(revenda or "")), data, str(descricao or "").strip(), str(documento or "").strip())


def vinculos_999() -> dict:
    return {
        chave_999(r["revenda"], r["data"], r["descricao"], r["documento"]): r
        for r in ler("vinculos_999").iter_rows(named=True)
    }


@_acao("vincular arquivo da rede (Caixa 999)")
def vincular_999(revenda: str, data, descricao: str, documento: str, caminho: str | None, usuario: str) -> None:
    esquema = ESQUEMA["vinculos_999"]
    alvo = chave_999(revenda, data, descricao, documento)
    with _trava:
        tudo = ler("vinculos_999")
        base = (
            tudo.filter(
                pl.Series(
                    [
                        chave_999(r["revenda"], r["data"], r["descricao"], r["documento"]) != alvo
                        for r in tudo.iter_rows(named=True)
                    ],
                    dtype=pl.Boolean,
                )
            )
            if tudo.height
            else tudo
        )
        if caminho:
            linha = {
                "revenda": revenda,
                "data": data,
                "descricao": str(descricao or "").strip(),
                "documento": str(documento or "").strip(),
                "caminho": str(caminho),
                "nome": Path(caminho).name,
                "vinculado_por": usuario,
                "vinculado_em": datetime.now(),
            }
            base = pl.concat([base, pl.DataFrame([linha], schema=esquema)], how="vertical_relaxed")
        _guardar("vinculos_999", base)


def veiculos_das_notas() -> dict:
    return {r["id"]: r for r in ler("veiculos_notas").iter_rows(named=True)}


@_acao(lambda argumentos: f"informar o veículo ({argumentos.get('origem') or 'Importar notas'})")
def gravar_veiculo_da_nota(ident: str, campos: dict | None, usuario: str, origem: str = "Importar notas") -> None:
    esquema = ESQUEMA["veiculos_notas"]
    with _trava:
        base = ler("veiculos_notas").filter(pl.col("id") != ident)
        if campos:
            linha = {c: campos.get(c) for c in esquema} | {"id": ident, "origem": origem}
            base = pl.concat([base, pl.DataFrame([linha], schema=esquema)], how="vertical_relaxed")
        _guardar("veiculos_notas", base)


def _gravar_lancamento_fiscal(mudancas: dict) -> None:
    esquema = ESQUEMA["lancamento_fiscal"]
    with _trava:
        tudo = ler("lancamento_fiscal")
        anteriores = {r["id"]: r for r in tudo.iter_rows(named=True)}
        novas = []
        for ident, campos in mudancas.items():
            linha = {c: (anteriores.get(ident) or {}).get(c) for c in esquema}
            linha.update({c: v for c, v in campos.items() if c in esquema})
            linha["id"] = ident
            novas.append(linha)
        base = tudo.filter(~pl.col("id").is_in(list(mudancas)))
        _guardar("lancamento_fiscal", pl.concat([base, pl.DataFrame(novas, schema=esquema)], how="vertical_relaxed"))


@_acao(_acao_do_movimento_manual)
def gravar_movimentos_manuais(mudancas: dict, usuario: str) -> None:
    esquema = ESQUEMA["lancamentos_manuais_movimento"]
    with _trava:
        tudo = ler("lancamentos_manuais_movimento")
        anteriores = {r["id"]: r for r in tudo.iter_rows(named=True)}
        novas = []
        for ident, campos in mudancas.items():
            linha = {c: (anteriores.get(ident) or {}).get(c) for c in esquema}
            linha.update({c: v for c, v in campos.items() if c in esquema})
            linha["id"] = ident
            if set(campos) - _SO_ENVIO:
                linha.update(editado_por=usuario, editado_em=datetime.now())
            novas.append(linha)
        base = tudo.filter(~pl.col("id").is_in(list(mudancas)))
        _guardar(
            "lancamentos_manuais_movimento",
            pl.concat([base, pl.DataFrame(novas, schema=esquema)], how="vertical_relaxed"),
        )
