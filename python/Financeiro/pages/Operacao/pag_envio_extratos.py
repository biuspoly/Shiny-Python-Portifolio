import os
import re
from datetime import date, time, timedelta
from pathlib import Path

import polars as pl
from shiny import module, reactive, render, ui
from shiny.module import resolve_id

from core import arquivo_revenda, extrato_banco_pdf, manual_arquivo
from core.config import chave_revenda
from core.config_arquivo import carregar_json
from core.secao import ICONE_ENVIO_EXTRATOS, titulo_secao
from pages.PPF.Dados import dados_ppf as d

VALOR_NAVSET = "ppf_ext"

TIPOS = (
    ("bancos", "Bancos"),
    ("batida_diaria", "Batida"),
    ("fabrica", "Fábrica"),
    ("modelo_iv", "Modelo IV"),
)

COLUNAS = ["Revenda", *[rotulo for _t, rotulo in TIPOS], "Notas baixadas", "Status"]


def _sem_fabrica() -> set[str]:
    nomes = carregar_json("parametros_financeiro").get("revendas_sem_extrato_fabrica") or []
    return {chave_revenda(n) for n in nomes}


_FONTES_DO_MOVIMENTO = (
    ("extrato_banco", "data_lancamento", ("valor",)),
    ("saldo_banco_999", "data_baixa", ("valor_dinheiro", "valor_moeda", "valor_pix")),
    ("batida_diaria", "data", ("dinheiro_moeda", "oct", "octs_nao_compensadas", "vale", "pix_provisorios")),
)
_cache_movimento: dict = {}


def _dias_com_movimento() -> pl.DataFrame:
    leitores = {
        "extrato_banco": d.extrato_banco,
        "saldo_banco_999": d.saldo_banco_999,
        "batida_diaria": d.batida_diaria,
    }
    caminhos = [d.PASTA_PARQUET / f"{nome}.parquet" for nome, _, _ in _FONTES_DO_MOVIMENTO]
    chave = tuple(c.stat().st_mtime_ns if c.is_file() else 0 for c in caminhos)
    if chave in _cache_movimento:
        return _cache_movimento[chave]
    partes = []
    for nome, coluna_data, colunas in _FONTES_DO_MOVIMENTO:
        base = leitores[nome]()
        colunas = [c for c in colunas if c in base.columns]
        if base.is_empty() or not colunas or not {"REVENDA", coluna_data} <= set(base.columns):
            continue
        if nome == "extrato_banco" and "cod_banco" in base.columns:
            base = base.filter(pl.col("cod_banco").cast(pl.Int64, strict=False) == d.BANCO_CAIXA)
        partes.append(
            base.filter(pl.any_horizontal(pl.col(c).cast(pl.Float64, strict=False).fill_null(0) != 0 for c in colunas))
            .select(
                pl.col("REVENDA").cast(pl.Utf8).alias("revenda"),
                pl.col(coluna_data).cast(pl.Date, strict=False).alias("dia"),
            )
            .drop_nulls()
            .unique()
        )
    dias = pl.concat(partes).unique() if partes else pl.DataFrame(schema={"revenda": pl.Utf8, "dia": pl.Date})
    nomes = {n: chave_revenda(n) for n in dias["revenda"].unique().to_list()}
    dias = dias.with_columns(pl.col("revenda").replace_strict(nomes, return_dtype=pl.Utf8))
    _cache_movimento.clear()
    _cache_movimento[chave] = dias
    return dias


def dia_util_anterior(referencia: date, revenda: str) -> date:
    dias = _dias_com_movimento()
    ultimo = dias.filter((pl.col("revenda") == chave_revenda(revenda)) & (pl.col("dia") < referencia))["dia"].max()
    return ultimo if ultimo is not None else referencia - timedelta(days=1)


def tipos_exigidos(revenda: str) -> list[str]:
    sem_fabrica = chave_revenda(revenda) in _sem_fabrica()
    return [t for t, _r in TIPOS if not (sem_fabrica and t == "fabrica")]


def revendas_do_painel() -> list[str]:
    return list(carregar_json("parametros_financeiro").get("revendas_monitoradas_envio_extratos") or [])


def envios_do_dia(dia: date) -> dict[tuple[str, str], dict]:
    partes = []
    do_cache = d.controle_envio_extratos()
    if not do_cache.is_empty():
        partes.append(
            do_cache.select(
                pl.col("REVENDA").cast(pl.Utf8).alias("revenda"),
                pl.col("extrato").cast(pl.Utf8),
                pl.col("usuario").cast(pl.Utf8),
                pl.col("enviado_em").cast(pl.Datetime, strict=False),
            )
        )
    da_tela = manual_arquivo.envios_extratos()
    if not da_tela.is_empty():
        partes.append(
            da_tela.select(
                pl.col("revenda").cast(pl.Utf8),
                pl.col("extrato").cast(pl.Utf8),
                pl.col("usuario").cast(pl.Utf8),
                pl.col("enviado_em").cast(pl.Datetime, strict=False),
            )
        )
    if not partes:
        return {}
    base = pl.concat(partes, how="vertical_relaxed").drop_nulls("enviado_em")
    base = base.filter(pl.col("enviado_em").dt.date() == dia)
    if base.is_empty():
        return {}
    base = base.sort("enviado_em", descending=True)
    ultimos: dict[tuple[str, str], dict] = {}
    for linha in base.iter_rows(named=True):
        chave = (chave_revenda(linha["revenda"] or ""), linha["extrato"] or "")
        ultimos.setdefault(chave, linha)
    return ultimos


def _pastas_modelo_iv() -> list[Path]:
    return extrato_banco_pdf.pastas("modelo_iv")


_modelos_iv_lidos: dict = {}

HORA_LIMITE_ENVIO = time(8, 0)


def _datas_do_dado(leitor, revenda: str, coluna: str) -> set:
    try:
        base = d.filtrar_por_revenda(leitor(), revenda)
    except Exception:
        return set()
    if base.is_empty() or coluna not in base.columns:
        return set()
    return set(base[coluna].cast(pl.Date, strict=False).drop_nulls().to_list())


_DATAS_DO_MODELO_IV = (
    ("dmy", re.compile(r"(?<!\d)(\d{1,2})[.\-_/ ](\d{1,2})[.\-_/ ](\d{2,4})(?!\d)")),
    ("ymd", re.compile(r"(?<!\d)(\d{4})[.\-_/ ](\d{1,2})[.\-_/ ](\d{1,2})(?!\d)")),
    ("dmy", re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{4})(?!\d)")),
)


def _data_do_nome_modelo_iv(nome: str) -> date | None:
    for tipo, padrao in _DATAS_DO_MODELO_IV:
        for achado in reversed(list(padrao.finditer(nome))):
            a, b, c = achado.groups()
            ano, mes, dia = (a, b, c) if tipo == "ymd" else (c, b, a)
            ano = int(ano) + (2000 if int(ano) < 100 else 0)
            try:
                return date(ano, int(mes), int(dia))
            except ValueError:
                continue
    return None


def _modelo_iv_do_dia(revenda: str, referencia: date) -> bool:
    pastas = [pasta for pasta in _pastas_modelo_iv() if pasta.is_dir()]
    chave = tuple((str(pasta), pasta.stat().st_mtime_ns) for pasta in pastas)
    if chave not in _modelos_iv_lidos:
        achados = set()
        for pasta in pastas:
            with os.scandir(pasta) as itens:
                for item in itens:
                    if not item.is_file() or "modelo" not in item.name.lower():
                        continue
                    dono = (
                        arquivo_revenda.revenda_do_prefixo(item.name) or (arquivo_revenda.revenda_do_nome(item.name)[0])
                    )
                    dia = _data_do_nome_modelo_iv(item.name)
                    if dono and dia:
                        achados.add((chave_revenda(dono), dia))
        _modelos_iv_lidos.clear()
        _modelos_iv_lidos[chave] = achados
    return (chave_revenda(revenda), referencia) in _modelos_iv_lidos[chave]


def _modelo_iv_requerido(revenda: str) -> bool:
    try:
        from pages.PPF.Dados import dados_composicao as dc

        base = dc.composicao()
        if base.is_empty() or not {"REVENDA", "CHAVE", "VALOR"} <= set(base.columns):
            return True
        alvo = chave_revenda(revenda)
        linha = base.filter(
            (pl.col("CHAVE") == "modelo_iv")
            & (pl.col("REVENDA").cast(pl.Utf8).map_elements(chave_revenda, return_dtype=pl.Utf8) == alvo)
        )
        if linha.is_empty():
            return True
        valores = linha["VALOR"].cast(pl.Float64, strict=False).drop_nulls()
        return bool((valores != 0).any())
    except Exception as exc:
        print(f"Envio de Extratos: nao deu para ler o Modelo IV da Composicao -- {exc}")
        return True


def status_envio_do_dia(revenda: str, hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    referencia = dia_util_anterior(hoje, revenda)
    exigidos = tipos_exigidos(revenda)
    if not _modelo_iv_requerido(revenda):
        exigidos = [t for t in exigidos if t != "modelo_iv"]
    pelo_dado = set()
    if hoje in _datas_do_dado(d.extratos_bancos, revenda, "data"):
        pelo_dado.add("bancos")
    if hoje in _datas_do_dado(d.extratos_fabricas_totais, revenda, "data_hora"):
        pelo_dado.add("fabrica")
    if referencia in _datas_do_dado(d.batida_diaria, revenda, "data"):
        pelo_dado.add("batida_diaria")
    enviados = set(pelo_dado)
    if "modelo_iv" in exigidos and _modelo_iv_do_dia(revenda, referencia):
        enviados.add("modelo_iv")

    ultimo = None
    alvo = chave_revenda(revenda)
    for (rev, tipo), linha in envios_do_dia(hoje).items():
        if rev != alvo:
            continue
        if tipo in ("bancos", "batida_diaria", "fabrica"):
            enviados.add(tipo)
        quando = linha.get("enviado_em")
        if quando is not None and (ultimo is None or quando > ultimo):
            ultimo = quando

    rotulos = dict(TIPOS)
    faltando = [rotulos[t] for t in exigidos if t not in enviados]
    todos = not faltando
    if not todos:
        status = "nao_enviado"
    elif all(t in pelo_dado for t in ("bancos", "batida_diaria", "fabrica") if t in exigidos):
        status = "no_prazo"
    elif ultimo is None:
        status = "nao_enviado"
    else:
        status = "no_prazo" if ultimo.time() <= HORA_LIMITE_ENVIO else "fora_prazo"
    return {
        "status": status,
        "mensagem": "Todos os Extratos Enviados" if todos else "Aguardando Envio dos Extratos",
        "faltando": faltando,
        "referencia": referencia,
    }


def baixas_por_revenda(datas: dict[str, date]) -> dict[str, int] | None:
    base = d.titulos_pagos()
    if base.is_empty() or "data_pagamento" not in base.columns:
        return None
    coluna_revenda = "REVENDA" if "REVENDA" in base.columns else "revenda"
    if coluna_revenda not in base.columns:
        return None
    contagem = (
        base.select(
            pl.col(coluna_revenda).cast(pl.Utf8).alias("revenda"),
            pl.col("data_pagamento").cast(pl.Date, strict=False).alias("dia"),
        )
        .drop_nulls()
        .group_by(["revenda", "dia"])
        .len()
    )
    mapa = {(chave_revenda(r["revenda"]), r["dia"]): int(r["len"]) for r in contagem.iter_rows(named=True)}
    return {revenda: mapa.get((chave_revenda(revenda), dia), 0) for revenda, dia in datas.items()}


def _cartao(
    hora: str, nota: str | None, estado: str, titulo: str | None = None, classe_nota: str = "painel-envio-empty"
) -> ui.Tag:
    return ui.tags.td(
        ui.span(
            ui.span(hora, class_="painel-envio-time"),
            ui.span(nota, class_=classe_nota) if nota else None,
            class_=f"painel-envio-cell {estado}",
            title=titulo,
        )
    )


def _celula_envio(envio: dict | None, exigido: bool) -> ui.Tag:
    if not exigido:
        return _cartao("N/A", "Não aplicável", "not-required")
    if not envio:
        return _cartao("--:--", "não enviado", "missing")
    quando = envio["enviado_em"]
    return _cartao(
        quando.strftime("%H:%M"),
        str(envio.get("usuario") or "") or None,
        "ok",
        titulo=quando.strftime("%d/%m/%Y %H:%M"),
        classe_nota="painel-envio-user",
    )


def versao_dos_arquivos(*arquivos: Path) -> tuple:
    return tuple(a.stat().st_mtime_ns if a.exists() else 0 for a in arquivos)


def cabecalho_painel(subtitulo: str) -> ui.Tag:
    return ui.div(ui.p(subtitulo, class_="painel-envio-subtitle"), class_="painel-envio-header")


def filtro_de_data(id_data: str) -> ui.Tag:
    return ui.div(
        ui.div(
            ui.tags.label("Data", for_=resolve_id(id_data)),
            ui.input_date(id_data, None, value=date.today(), format="dd/mm/yyyy", language="pt-BR", width="146px"),
            class_="painel-envio-filter-inline",
        ),
        class_="painel-envio-filters",
    )


@module.ui
def envio_extratos_ui(revenda: str | None = None):
    return ui.div(
        ui.card(
            ui.card_header(titulo_secao("Farol DF", icone=ICONE_ENVIO_EXTRATOS)),
            ui.div(
                cabecalho_painel(
                    "Horários de envio por revenda para Banco, Batida, Fábrica quando aplicável e Modelo IV."
                ),
                ui.tags.section(
                    ui.div(
                        ui.div(ui.output_ui("resumo"), filtro_de_data("dia"), class_="painel-envio-toolbar"),
                        class_="painel-envio-card-toolbar",
                    ),
                    ui.output_ui("corpo_tabela", class_="painel-envio-table-wrapper"),
                    class_="painel-envio-card",
                ),
                class_="painel-envio-page",
            ),
        ),
        class_="fin-modulo",
    )


@module.server
def envio_extratos_server(input, output, session, revenda_atual=None):
    arquivos = (
        *[
            d.PASTA_PARQUET / f"{nome}.parquet"
            for nome in (
                "controle_envio_extratos",
                "titulos_pagos",
                "extrato_banco",
                "saldo_banco_999",
                "batida_diaria",
            )
        ],
        manual_arquivo.caminho("envios_extratos"),
        *_pastas_modelo_iv(),
    )

    @reactive.poll(lambda: versao_dos_arquivos(*arquivos), 15)
    def arquivos_do_painel():
        return versao_dos_arquivos(*arquivos)

    @reactive.calc
    def painel() -> list[dict]:
        arquivos_do_painel()
        if callable(revenda_atual):
            revenda_atual()
        dia = input.dia() or date.today()
        ultimos = envios_do_dia(dia)
        revendas = revendas_do_painel()
        datas_baixa = {r: dia_util_anterior(dia, r) for r in revendas}
        baixas = baixas_por_revenda(datas_baixa)

        linhas = []
        for revenda in revendas:
            exigidos = tipos_exigidos(revenda)
            celulas, enviados = {}, 0
            for tipo, _rotulo in TIPOS:
                envio = ultimos.get((chave_revenda(revenda), tipo))
                exigido = tipo in exigidos
                if tipo == "modelo_iv" and exigido and envio and not _modelo_iv_do_dia(revenda, datas_baixa[revenda]):
                    envio = None
                if envio and exigido:
                    enviados += 1
                celulas[tipo] = (envio if exigido else None, exigido)
            linhas.append(
                {
                    "revenda": revenda,
                    "celulas": celulas,
                    "enviados": enviados,
                    "total": len(exigidos),
                    "completo": enviados == len(exigidos),
                    "baixa_dia": datas_baixa[revenda],
                    "baixa_qtd": None if baixas is None else baixas.get(revenda, 0),
                }
            )
        return linhas

    @render.ui
    def resumo():
        linhas = painel()
        total_envios = sum(linha["enviados"] for linha in linhas)
        completas = sum(1 for linha in linhas if linha["completo"])
        dia = input.dia() or date.today()
        return ui.div(
            ui.span(f"Data {dia:%d/%m/%Y}"),
            ui.span("|"),
            ui.span(f"{total_envios} envios registrados"),
            ui.span("|"),
            ui.span(
                f"{completas}/{len(linhas)} revendas completas",
                class_="painel-envio-summary-completude "
                + ("is-complete" if completas == len(linhas) else "is-pending"),
            ),
            class_="painel-envio-summary",
        )

    @render.ui
    def corpo_tabela():
        linhas = painel()
        tabela_vazia = ui.tags.table(
            ui.tags.thead(ui.tags.tr(*[ui.tags.th(c) for c in COLUNAS])),
            class_="painel-envio-table",
        )
        if not linhas:
            return ui.TagList(
                tabela_vazia, ui.div("Nenhuma revenda configurada para o painel.", class_="painel-envio-empty-state")
            )

        corpo = []
        for linha in linhas:
            corpo.append(
                ui.tags.tr(
                    ui.tags.td(linha["revenda"], class_="painel-envio-revenda"),
                    *[_celula_envio(*linha["celulas"][tipo]) for tipo, _r in TIPOS],
                    _cartao("--", "sem dado", "not-required", titulo="Não foi possível ler as baixas do ERP")
                    if linha["baixa_qtd"] is None
                    else _cartao(
                        str(linha["baixa_qtd"]),
                        f"baixadas em {linha['baixa_dia']:%d/%m}",
                        "ok" if linha["baixa_qtd"] else "not-required",
                        titulo=f"Títulos baixados no ERP em {linha['baixa_dia']:%d/%m}",
                        classe_nota="painel-envio-user",
                    ),
                    ui.tags.td(
                        ui.span("Completo", class_="painel-envio-status done")
                        if linha["completo"]
                        else ui.span(f"{linha['enviados']}/{linha['total']}", class_="painel-envio-status pending"),
                    ),
                )
            )
        return ui.tags.table(
            ui.tags.thead(ui.tags.tr(*[ui.tags.th(c) for c in COLUNAS])),
            ui.tags.tbody(*corpo),
            class_="painel-envio-table",
        )


def pag_envio_extratos_ui(revenda: str | None = None):
    return envio_extratos_ui("envio_extratos", revenda)


def pag_envio_extratos_server(revenda_atual=None):
    return envio_extratos_server("envio_extratos", revenda_atual=revenda_atual)
