import asyncio
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import polars as pl
from faicons import icon_svg
from shiny import module, reactive, render, ui

from core import fabricas, gravacao, manual_arquivo, trava_caixa
from core.auth import identificar_usuario
from core.aviso import corpo_aviso, modal_aviso
from core.cartoes_banco import cartao_banco, formatar_reais, ler_reais
from core.config import pode, quem_libera
from core.id_titulo import base_do, eh_parte
from core.secao import ICONE_MARÉ, ICONE_PAGAMENTOS, com_placeholder, titulo_secao
from core.tabela_paginada import TabelaPaginada
from core.visibilidade import pagina_visivel

from .Dados import dados_anexos as an
from .Dados import dados_composicao as dc
from .Dados import dados_contas_pagar as cp
from .Dados import dados_ppf as d

FILTRO_COM_BUSCA = {
    "placeholder": "Todos",
    "plugins": ["clear_button", "restore_on_backspace"],
    "dropdownParent": "body",
    "dropdownClass": "selectize-dropdown ppf-filtro-dropdown",
}

VALOR_NAVSET = "ppf_pag"

LINHAS_INTERATIVAS = 100

_PREFIXO_PARCEIRO = "PARCEIRO"

FILTROS = [
    ("tipo", "Tipo", "TIPO"),
    ("fornecedor", "Nome", "FORNECEDOR"),
    ("documento", "Documento", "DOCUMENTO"),
    ("banco", "Banco", "BANCO"),
]
FILTROS_ESTREITOS = {"documento", "banco"}

CHAVES = [
    ("chave_pagos", "Pagos"),
    ("chave_juros", "Juros"),
    ("chave_control", "ERP"),
]


_COLUNAS = [
    "Vencimento",
    "Pagamento",
    "Tipo",
    "C. Custo",
    "Fornecedor",
    "Documento",
    "Valor Original",
    "Valor Pago",
    "Juros",
    "Banco",
    "Excluir",
]

_ORDENA_POR = {
    "Vencimento": "DATA",
    "Pagamento": "DATA_PAGAMENTO",
    "Tipo": "TIPO",
    "C. Custo": "CENTRO_CUSTO",
    "Fornecedor": "FORNECEDOR",
    "Documento": "DOCUMENTO",
    "Valor Original": "VALOR_ORIGINAL",
    "Valor Pago": "VALOR_PAGO",
    "Juros": "JUROS",
    "Banco": "BANCO",
}

_CLASSE_TH = {
    "Vencimento": "ppf-th-data",
    "Pagamento": "ppf-th-data",
    "Fornecedor": "ppf-th-fornecedor",
    "Excluir": "ppf-th-excluir",
}


_FORMA = {
    "id_unico": pl.Utf8,
    "REVENDA": pl.Utf8,
    "DATA": pl.Date,
    "DATA_PAGAMENTO": pl.Date,
    "TIPO": pl.Utf8,
    "FORNECEDOR": pl.Utf8,
    "DOCUMENTO": pl.Utf8,
    "VALOR_ORIGINAL": pl.Float64,
    "VALOR_PAGO": pl.Float64,
    "JUROS": pl.Float64,
    "BANCO": pl.Utf8,
    "ENTRADA_MANUAL": pl.Utf8,
    "_EDITAVEL": pl.Boolean,
    "_ID": pl.Int64,
}


def _vazia_como(base: pl.DataFrame) -> pl.DataFrame:
    return base.head(0)


def _como_fila(base: pl.DataFrame) -> pl.DataFrame:
    if base.is_empty():
        return pl.DataFrame(schema=_FORMA)
    return base.select(
        pl.col("id_unico"),
        pl.col("REVENDA"),
        pl.col("DATA"),
        pl.col("data_pagamento").cast(pl.Date, strict=False).alias("DATA_PAGAMENTO"),
        pl.col("descricao_despesa").cast(pl.Utf8).alias("TIPO"),
        pl.col("FORNECEDOR"),
        pl.col("PGMOVMOV_NDUPL").alias("DOCUMENTO"),
        _valor_da_nota(base).alias("VALOR_ORIGINAL"),
        pl.col("valor_pago").cast(pl.Float64, strict=False).alias("VALOR_PAGO"),
        pl.col("juros").cast(pl.Float64, strict=False).alias("JUROS"),
        pl.col("banco").cast(pl.Utf8).alias("BANCO"),
        _entrada_manual(base),
        pl.lit(True).alias("_EDITAVEL"),
        pl.lit(2**62, dtype=pl.Int64).alias("_ID"),
    )


def _como_fila_do_banco(base: pl.DataFrame) -> pl.DataFrame:
    if base.is_empty():
        return pl.DataFrame(schema=_FORMA)
    return base.select(
        pl.col("id_unico").cast(pl.Utf8),
        pl.col("REVENDA").cast(pl.Utf8),
        pl.col("data_vencimento").cast(pl.Date, strict=False).alias("DATA"),
        pl.col("data_pagamento").cast(pl.Date, strict=False).alias("DATA_PAGAMENTO"),
        pl.col("descricao_despesa").cast(pl.Utf8).alias("TIPO"),
        pl.col("razao_social").cast(pl.Utf8).alias("FORNECEDOR"),
        pl.col("num_doc").cast(pl.Utf8).alias("DOCUMENTO"),
        pl.col("valor_original").cast(pl.Float64, strict=False).alias("VALOR_ORIGINAL"),
        pl.col("valor_pago").cast(pl.Float64, strict=False).alias("VALOR_PAGO"),
        pl.col("juros").cast(pl.Float64, strict=False).alias("JUROS"),
        pl.col("banco").cast(pl.Utf8).alias("BANCO"),
        _entrada_manual(base),
        pl.lit(True).alias("_EDITAVEL"),
        pl.col("id").cast(pl.Int64, strict=False).alias("_ID"),
    )


def _valor_da_nota(contas: pl.DataFrame) -> pl.Expr:
    valor = pl.col("valor_original").cast(pl.Float64, strict=False)
    if "valor_titulo" not in contas.columns:
        return valor
    return pl.coalesce(pl.col("valor_titulo").cast(pl.Float64, strict=False), valor)


def valor_das_partes(registros: pl.DataFrame, editados: dict, desfeitas) -> dict[str, float]:
    valor_da_parte: dict[str, float] = {}
    if not registros.is_empty() and {"id_unico", "valor_original"} <= set(registros.columns):
        partes = registros.filter(pl.col("id_unico").cast(pl.Utf8).str.contains(cp.SUFIXO_PARTE))
        for ident, valor in partes.select("id_unico", "valor_original").iter_rows():
            valor_da_parte[ident] = valor
    for ident, dados in editados.items():
        if eh_parte(ident) and dados.get("valor_original") is not None:
            valor_da_parte[ident] = dados["valor_original"]
    soma: dict[str, float] = {}
    for ident, valor in valor_da_parte.items():
        if ident in desfeitas or valor is None:
            continue
        titulo = base_do(ident)
        soma[titulo] = soma.get(titulo, 0.0) + float(valor)
    return soma


def mesma_base(antes: pl.DataFrame, agora: pl.DataFrame) -> bool:
    try:
        return antes.equals(agora)
    except Exception:
        return False


def com_a_parte_da_base(linhas: pl.DataFrame, partes_do_titulo: dict[str, float]) -> pl.DataFrame:
    if linhas.is_empty() or not partes_do_titulo:
        return linhas
    soma_das_partes = pl.col("id_unico").replace_strict(partes_do_titulo, default=0.0, return_dtype=pl.Float64)
    parte_da_base = (pl.col("VALOR_ORIGINAL") - soma_das_partes).round(2)
    return linhas.with_columns(
        pl.when(pl.col("_EDITAVEL") & (soma_das_partes > 0) & (parte_da_base >= 0.01))
        .then(parte_da_base)
        .otherwise(pl.col("VALOR_ORIGINAL"))
        .alias("VALOR_ORIGINAL")
    )


def centro_custo_por_titulo(*tabelas: pl.DataFrame) -> dict[str, int]:
    pedacos = [
        tabela.select(
            pl.col("id_unico").cast(pl.Utf8).str.replace(cp.SUFIXO_PARTE, "").alias("titulo"),
            pl.col("centro_custo").cast(pl.Int64, strict=False).alias("centro"),
        )
        for tabela in tabelas
        if not tabela.is_empty() and {"id_unico", "centro_custo"} <= set(tabela.columns)
    ]
    if not pedacos:
        return {}
    centros = pl.concat(pedacos, how="vertical_relaxed").drop_nulls().unique(subset=["titulo"], keep="first")
    return dict(zip(centros["titulo"].to_list(), centros["centro"].to_list()))


def com_centro_custo(linhas: pl.DataFrame, centros: dict[str, int], revenda: str | None) -> pl.DataFrame:
    titulo = pl.col("id_unico").cast(pl.Utf8).str.replace(cp.SUFIXO_PARTE, "")
    com_numero = linhas.with_columns(
        titulo.replace_strict(centros, default=None, return_dtype=pl.Int64).alias("_centro_custo")
    )
    com_sigla = d.com_centro_custo_abreviado(com_numero, revenda, coluna="_centro_custo")
    if "CENTRO_CUSTO" not in com_sigla.columns:
        com_sigla = com_sigla.with_columns(pl.lit("", dtype=pl.Utf8).alias("CENTRO_CUSTO"))
    return com_sigla.drop("_centro_custo")


def _entrada_manual(base: pl.DataFrame) -> pl.Expr:
    if "entrada_manual" not in base.columns:
        return pl.lit(None, dtype=pl.Utf8).alias("ENTRADA_MANUAL")
    return pl.col("entrada_manual").cast(pl.Utf8).alias("ENTRADA_MANUAL")


def _como_externo(base: pl.DataFrame) -> pl.DataFrame:
    if base.is_empty():
        return pl.DataFrame(schema=_FORMA)
    despesas = d.codigos_despesa()
    if not despesas.is_empty() and "codigo_despesa" in base.columns:
        de_para = (
            despesas.select("codigo_despesa", "descricao_despesa")
            .drop_nulls("codigo_despesa")
            .unique(subset=["codigo_despesa"], keep="first")
        )
        base = base.join(de_para, on="codigo_despesa", how="left")
    tipo = (
        pl.col("descricao_despesa").cast(pl.Utf8)
        if "descricao_despesa" in base.columns
        else pl.col("tipo_fornecedor").cast(pl.Utf8)
    )
    valor = pl.col("valor_pago").cast(pl.Float64, strict=False)
    return base.select(
        pl.col("id_unico"),
        pl.col("REVENDA"),
        pl.col("data_vencimento").cast(pl.Date, strict=False).alias("DATA"),
        pl.col("data_pagamento").cast(pl.Date, strict=False).alias("DATA_PAGAMENTO"),
        tipo.alias("TIPO"),
        pl.col("razao_social").cast(pl.Utf8).alias("FORNECEDOR"),
        pl.col("num_doc").cast(pl.Utf8).alias("DOCUMENTO"),
        valor.alias("VALOR_ORIGINAL"),
        valor.alias("VALOR_PAGO"),
        pl.lit(0.0).alias("JUROS"),
        (pl.col("cod_banco") if "cod_banco" in base.columns else pl.col("banco")).cast(pl.Utf8).alias("BANCO"),
        pl.lit("Não").alias("ENTRADA_MANUAL"),
        pl.lit(False).alias("_EDITAVEL"),
        pl.lit(0, dtype=pl.Int64).alias("_ID"),
    )


def _vazio(valor) -> bool:
    return valor is None or valor != valor


def _reais_cru(valor) -> str:
    if _vazio(valor):
        return ""
    try:
        return f"{float(valor):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    except (TypeError, ValueError):
        return ""


ICONE_POR_NIVEL = {"falha": "circle-exclamation", "atencao": "triangle-exclamation", "ok": "circle-check"}


def _aviso_da_baixa(aviso: dict | None) -> ui.Tag | None:
    if not aviso:
        return None
    dia = aviso["dia"]
    texto = f"{aviso['rotulo']}{f' (rotina de {dia:%d/%m/%Y})' if dia else ''}" + (
        f": {aviso['detalhe']}" if aviso["detalhe"] else ""
    )
    nivel = aviso["nivel"] if aviso["nivel"] in ICONE_POR_NIVEL else "falha"
    return ui.tooltip(
        ui.span(
            icon_svg(ICONE_POR_NIVEL[nivel], a11y="deco"), class_=f"ppf-aviso-baixa ppf-baixa-{nivel}", aria_label=texto
        ),
        texto,
        placement="top",
    )


def _numero(texto) -> float | None:
    return ler_reais(texto)


def _reais(valor: float | None) -> str:
    if _vazio(valor):
        return ""
    inteiro = f"{abs(valor):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"{'-' if valor < 0 else ''}R$ {inteiro}"


def _data(valor) -> str:
    return "" if _vazio(valor) else valor.strftime("%d/%m/%Y")


def _rotulo_banco(banco: str) -> str:
    return "Fábrica" if banco == "Fabrica" else banco


@module.ui
def pagamentos_ui(revenda: str | None = None):
    return ui.div(
        ui.card(
            ui.card_header(titulo_secao("Pagamentos", icone=ICONE_PAGAMENTOS)),
            ui.output_ui("cards_bancos"),
            ui.div(
                ui.div(
                    ui.tags.strong("Data de Pagamento", class_="ppf-titulo-data"),
                    ui.div(
                        ui.span("De:", class_="ppf-rotulo-data"),
                        com_placeholder(
                            ui.input_date_range(
                                "intervalo",
                                None,
                                start="",
                                end="",
                                format="dd/mm/yyyy",
                                language="pt-BR",
                                separator="Até:",
                                weekstart=0,
                            ),
                            "dd/mm/aaaa",
                        ),
                        ui.input_action_button(
                            "limpar_data",
                            icon_svg("eraser", a11y="deco"),
                            class_="ppf-btn-limpar-data",
                            title="Limpar filtro de data",
                        ),
                        class_="ppf-linha-data",
                    ),
                    class_="ppf-grupo-filtros ppf-grupo-data",
                ),
                *[
                    ui.div(
                        *[
                            ui.div(
                                ui.input_selectize(id_filtro, f"{rotulo}:", {"": "Todos"}, options=FILTRO_COM_BUSCA),
                                class_="ppf-filtro ppf-filtro-inline ppf-filtro-"
                                + id_filtro
                                + (" ppf-filtro-estreito" if id_filtro in FILTROS_ESTREITOS else ""),
                            )
                            for id_filtro, rotulo, _coluna in par
                        ],
                        class_="ppf-grupo-filtros ppf-grupo-selects",
                    )
                    for par in (FILTROS[:2], FILTROS[2:])
                ],
                ui.div(
                    ui.input_action_button("limpar", "Limpar", class_="ppf-btn-limpar", title="Limpar filtros"),
                    ui.output_ui("botao_fabrica", class_="ppf-filtro-fabrica"),
                    class_="ppf-grupo-limpar",
                ),
                ui.div(
                    *[ui.input_switch(id_chave, rotulo) for id_chave, rotulo in CHAVES],
                    class_="ppf-chaves-pagamentos",
                ),
                ui.div(
                    ui.input_action_button(
                        "enviar",
                        None,
                        icon=icon_svg("paper-plane", a11y="deco"),
                        class_="ppf-btn-discreto",
                        title="Enviar formulário",
                    ),
                    ui.div("Enviar", class_="ppf-acao-rotulo"),
                    class_="ppf-acao",
                ),
                class_="ppf-faixa-filtros pag-faixa",
                id="faixa_pagamentos",
            ),
            ui.div(
                ui.tags.table(
                    ui.tags.thead(
                        ui.tags.tr(
                            *[
                                ui.tags.th(
                                    ui.TagList(
                                        ui.input_action_link(f"ordem_{i}", rotulo),
                                        ui.output_ui(f"seta_{i}", inline=True),
                                    )
                                    if rotulo in _ORDENA_POR
                                    else rotulo,
                                    ui.div(
                                        ui.input_checkbox("so_com_anexo", "", value=False),
                                        ui.input_checkbox("so_sem_anexo", "", value=False),
                                        class_="ppf-th-anexos",
                                        title="Só com anexo / só sem anexo",
                                    )
                                    if rotulo == "Documento"
                                    else None,
                                    class_=_CLASSE_TH.get(rotulo),
                                )
                                for i, rotulo in enumerate(_COLUNAS)
                            ]
                        )
                    ),
                    ui.output_ui("corpo_tabela", container=ui.tags.tbody),
                    class_="ppf-tabela-pagar-html",
                ),
                class_="ppf-tabela-pagamentos",
            ),
            ui.output_ui("rodape_tabela"),
        ),
        class_="fin-modulo",
    )


def _documento_normalizado() -> pl.Expr:
    return pl.col("DOCUMENTO").cast(pl.Utf8).str.strip_chars().str.to_uppercase().str.replace_all(r"[^A-Z0-9]", "")


@module.server
def pagamentos_server(input, output, session, revenda_atual=None):
    with reactive.isolate():
        revenda_da_url = revenda_atual() if callable(revenda_atual) else revenda_atual
    paginador = TabelaPaginada("pagamentos", input, session, tamanho_padrao=d.linhas_por_pagina(revenda_da_url))

    def _entregar_anexo_antigo(request):
        from starlette.responses import FileResponse, PlainTextResponse

        alvo = gravacao.anexo_antigo(request.query_params.get("nome", ""))
        if alvo is None:
            return PlainTextResponse("anexo nao encontrado", status_code=404)
        return FileResponse(
            alvo,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{alvo.name}"'},
        )

    url_anexo_antigo = session.dynamic_route("ver_anexo_antigo", _entregar_anexo_antigo)

    def _documento_do_olho(ident: str, documento, fornecedor: str) -> Path | None:
        return an.documento_do_olho(ident, documento, fornecedor)

    _olhos_desenhados: dict = {}

    async def _entregar_olho(request):
        from starlette.responses import FileResponse, PlainTextResponse

        ident = request.query_params.get("id", "")
        desenhado = _olhos_desenhados.get(ident)
        if desenhado is None:
            return PlainTextResponse("arquivo nao encontrado", status_code=404)
        assinado = await asyncio.to_thread(gravacao.pdf_assinado, ident)
        original = await asyncio.to_thread(_documento_do_olho, ident, *desenhado)
        alvo = await asyncio.to_thread(an.documento_assinado_do_olho, original, assinado) if assinado else original
        if alvo is None or not await asyncio.to_thread(alvo.is_file):
            return PlainTextResponse("arquivo nao encontrado", status_code=404)
        nome = an.nome_do_olho(original, desenhado[0]) if original else alvo.name
        if assinado and original:
            nome = f"{Path(nome).stem} - assinado.pdf"
        tipo, como = an.como_mostrar(alvo.name)
        return FileResponse(
            alvo, media_type=tipo, filename=nome, content_disposition_type=como, headers={"Cache-Control": "no-store"}
        )

    url_olho = session.dynamic_route("ver_olho", _entregar_olho)
    _emenda_olho = "&" if "?" in url_olho else "?"

    def _revenda() -> str | None:
        return revenda_atual() if callable(revenda_atual) else revenda_atual

    versao = reactive.value(0)

    def _sinal_do_manual() -> tuple:
        sinal = []
        for assunto in ("marcacoes", "pagamentos", "fora_da_fila"):
            try:
                sinal.append(manual_arquivo.caminho(assunto).stat().st_mtime_ns)
            except OSError:
                sinal.append(0)
        return tuple(sinal)

    @reactive.poll(_sinal_do_manual, 5)
    def _manual_no_disco():
        return _sinal_do_manual()

    _pagina_desenhada: dict = {}

    _cliques: dict = {}

    def _usuario() -> str:
        try:
            raiz = session.root_scope() if hasattr(session, "root_scope") else session
            quem, _script = identificar_usuario(raiz.http_conn)
            return (quem or "").strip() or "desconhecido"
        except Exception:
            return "desconhecido"

    def _pode(funcionalidade: str) -> bool:
        return pode(_usuario(), funcionalidade, _revenda())

    def _pode_editar_linha(linha: dict, auditar: bool, pagar: bool) -> bool:
        if not linha.get("_EDITAVEL"):
            return False
        return auditar or (pagar and linha.get("DATA_PAGAMENTO") == date.today())

    def _barrar(funcionalidade: str) -> bool:
        if _pode(funcionalidade):
            return False
        _avisar(
            "Você não tem permissão para isso. " + quem_libera(funcionalidade),
            titulo="Sem permissão",
        )
        return True

    def _avisar(mensagem: str, tipo: str = "warning", titulo: str = "Pagamentos") -> None:
        ui.modal_show(modal_aviso(mensagem, titulo=titulo, tipo=tipo), session=session)

    def _clicou(nome: str) -> bool:
        if nome not in input:
            return False
        atual = input[nome]() or 0
        anterior = _cliques.get(nome, 0)
        _cliques[nome] = atual
        return atual > anterior

    def _opcoes_banco(plano: list, atual) -> dict:
        nome = str(atual or "").strip()
        opcoes = {banco: _rotulo_banco(banco) for banco in plano}
        if nome and nome not in opcoes:
            opcoes[nome] = _rotulo_banco(nome)
        return opcoes

    @reactive.calc
    def _bancos_da_revenda() -> list:
        plano: list[str] = []
        try:
            parte = dc.da_revenda(dc.composicao(), _revenda())
            plano = [dc.rotulo_banco(c, None) for c in dc.bancos_para_lancar(parte)]
            for extra in (dc.rotulo_banco(dc.CHAVE_CAIXA, None), *dc.destinos_extra_pagamento(_revenda())):
                if extra not in plano:
                    plano.append(extra)
        except Exception as erro:
            print(f"Pagamentos: nao deu pra montar a lista de bancos -- {erro}")
        return plano

    @reactive.calc
    def editados() -> dict:
        versao()
        _manual_no_disco()
        return manual_arquivo.pagamentos_por_titulo()

    @reactive.calc
    def base_bruta() -> pl.DataFrame:
        _manual_no_disco()
        pagar = d.com_nome_fornecedor(d.filtrar_por_revenda(d.contas_pagar(), _revenda()))
        registros = d.filtrar_por_revenda(d.pagamentos_manuais(), _revenda())
        fila = (
            registros.filter(pl.col("pagar") == "Sim")
            if not registros.is_empty() and "pagar" in registros.columns
            else registros
        )
        tirados = manual_arquivo.fora_da_fila()
        if not fila.is_empty() and tirados:
            fila = fila.filter(~pl.col("id_unico").is_in(list(tirados)))
        na_fila = set(fila["id_unico"].to_list()) if not fila.is_empty() else set()
        novos = _vazia_como(pagar)
        faltam = set(manual_arquivo.enviados_em()) - tirados - na_fila
        if faltam and not pagar.is_empty():
            novos = pagar.filter(pl.col("id_unico").is_in(list(faltam))).unique(subset=["id_unico"], keep="first")

        com_registro = set(registros["id_unico"].to_list()) if not registros.is_empty() else set()
        com_registro |= na_fila | faltam | set(editados())
        pagos_no_control = d.filtrar_por_revenda(d.titulos_pagos(), _revenda())
        externos = pagos_no_control
        if not externos.is_empty() and "id_unico" in externos.columns:
            externos = externos.filter(~pl.col("id_unico").is_in(list(com_registro) or [""]))

        linhas = pl.concat(
            [_como_fila_do_banco(fila), _como_fila(novos), _como_externo(externos)],
            how="vertical_relaxed",
        )
        partes = valor_das_partes(registros, editados(), manual_arquivo.partes_desfeitas())
        centros = centro_custo_por_titulo(pagar, pagos_no_control)
        return com_centro_custo(com_a_parte_da_base(linhas, partes), centros, _revenda())

    fabrica_ligada = reactive.value(False)

    @reactive.effect
    @reactive.event(input.filtro_fabrica)
    def _alternar_fabrica():
        fabrica_ligada.set(not fabrica_ligada())
        paginador.reiniciar()

    @render.ui
    def botao_fabrica():
        fabrica = fabricas.fabrica_da_revenda(_revenda())
        if fabrica is None:
            return None
        icone = fabrica.get("icone_filtro") or ICONE_MARÉ
        titulo = fabrica.get("titulo_filtro") or f"Filtrar só {fabrica['nome']}"
        return ui.input_action_button(
            "filtro_fabrica",
            ui.tags.img(src=icone, alt=titulo),
            class_=f"btn ppf-botao-fabrica ppf-fabrica-{fabrica['chave']}" + (" ativo" if fabrica_ligada() else ""),
            title=titulo,
        )

    _base_da_tela = reactive.value(None)

    @reactive.effect(priority=10)
    def _guardar_base_da_tela():
        try:
            nova = com_edicoes_agora()
        except Exception as erro:
            print(f"Pagamentos: a base nao foi refeita -- {erro}")
            return
        with reactive.isolate():
            atual = _base_da_tela()
        if atual is None or not mesma_base(atual, nova):
            _base_da_tela.set(nova)

    @reactive.calc
    def com_edicoes() -> pl.DataFrame:
        guardada = _base_da_tela()
        return com_edicoes_agora() if guardada is None else guardada

    @reactive.calc
    def com_edicoes_agora() -> pl.DataFrame:
        base = base_bruta()
        if base.is_empty():
            return base
        por_id = editados()
        if por_id:
            base = base.with_columns(
                [
                    pl.col("id_unico")
                    .replace_strict(
                        {i: v.get(campo) for i, v in por_id.items()},
                        default=None,
                        return_dtype=tipo,
                    )
                    .fill_null(pl.col(coluna))
                    .alias(coluna)
                    for campo, coluna, tipo in (
                        ("valor_pago", "VALOR_PAGO", pl.Float64),
                        ("juros", "JUROS", pl.Float64),
                        ("banco", "BANCO", pl.Utf8),
                        ("data_pagamento", "DATA_PAGAMENTO", pl.Date),
                    )
                ]
            )
        hoje = date.today()
        plano = _bancos_da_revenda()
        sem_valor = pl.col("VALOR_PAGO").is_null() | (pl.col("VALOR_PAGO") == 0)
        sem_banco = pl.col("BANCO").fill_null("").str.strip_chars() == ""
        return base.with_columns(
            (~pl.col("_EDITAVEL") | (pl.col("DATA_PAGAMENTO") < hoje).fill_null(False)).alias("PAGOU"),
            pl.when(pl.col("_EDITAVEL") & sem_valor)
            .then(pl.col("VALOR_ORIGINAL"))
            .otherwise(pl.col("VALOR_PAGO"))
            .alias("VALOR_PAGO"),
            pl.when(pl.col("_EDITAVEL") & sem_banco)
            .then(pl.lit(plano[0] if plano else None, dtype=pl.Utf8))
            .otherwise(pl.col("BANCO"))
            .alias("BANCO"),
        )

    def _escolhidos() -> dict[str, str]:
        return {coluna: input[id_filtro]() for id_filtro, _r, coluna in FILTROS}

    def _aplicar(base: pl.DataFrame, sem: str | None = None) -> pl.DataFrame:
        if base.is_empty():
            return base
        hoje = date.today()
        if not input.chave_control():
            base = base.filter(pl.col("_EDITAVEL"))
        pagos, juros = input.chave_pagos(), input.chave_juros()
        if juros:
            base = base.filter(pl.col("PAGOU") & (pl.col("JUROS").fill_null(0) > 0))
        elif pagos:
            base = base.filter(pl.col("PAGOU"))
        else:
            base = base.filter(
                ~pl.col("PAGOU") | (pl.col("_EDITAVEL") & (pl.col("DATA_PAGAMENTO") == hoje)).fill_null(False)
            )

        intervalo = input.intervalo() or (None, None)
        de, ate = intervalo[0], intervalo[1]
        if not de and not ate and pagos and dia_do_pagos() is not None:
            de = ate = dia_do_pagos()
        data = pl.col("DATA_PAGAMENTO")
        if de and ate:
            base = base.filter(data.is_between(de, ate).fill_null(False))
        elif de:
            base = base.filter(data.is_null() | (data >= de))
        elif ate:
            base = base.filter(data.is_null() | (data <= ate))

        for coluna, escolhido in _escolhidos().items():
            if coluna == sem or not escolhido or coluna not in base.columns:
                continue
            texto = pl.col(coluna).cast(pl.Utf8).fill_null("")
            if coluna == "BANCO":
                base = base.filter(texto == str(escolhido))
            elif coluna == "TIPO":
                base = base.filter(texto.str.to_lowercase().str.contains(str(escolhido).strip().lower(), literal=True))
            else:
                base = base.filter(texto.str.contains(str(escolhido), literal=True))

        fabrica = fabricas.fabrica_da_revenda(_revenda())
        if fabrica_ligada() and fabrica is not None:
            base = base.filter(fabricas.expressao_da_fabrica("FORNECEDOR", fabrica))

        if input.so_com_anexo() or input.so_sem_anexo():
            com = pl.col("id_unico").is_in(list(gravacao.titulos_com_anexo() | set(d.icones_da_rede())) or [""])
            antigos = list(gravacao.docs_com_pdf_antigo())
            if antigos and "DOCUMENTO" in base.columns:
                com = com | _documento_normalizado().is_in(antigos)
            com = com.fill_null(False)
            base = base.filter(com if input.so_com_anexo() else ~com)
            if input.so_com_anexo() and input.so_sem_anexo():
                base = base.head(0)
        return base

    @reactive.calc
    def filtrado() -> pl.DataFrame:
        return _aplicar(com_edicoes())

    _opcoes_enviadas: dict[str, dict] = {}

    @reactive.effect
    def _preencher_filtros():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        try:
            base = com_edicoes()
        except Exception:
            return
        escolhidos = _escolhidos()
        for id_filtro, _rotulo, coluna in FILTROS:
            try:
                if coluna == "BANCO":
                    parcial = base if input.chave_control() else base.filter(pl.col("_EDITAVEL"))
                else:
                    parcial = _aplicar(base, sem=coluna)
                opcoes = (
                    set()
                    if parcial.is_empty() or coluna not in parcial.columns
                    else {str(v) for v in parcial[coluna].unique().to_list() if v not in (None, "")}
                )
            except Exception:
                continue
            atual = str(escolhidos.get(coluna) or "")
            if atual:
                opcoes.add(atual)
            escolhas = {"": "Todos", **{o: o for o in sorted(opcoes)}}
            if _opcoes_enviadas.get(id_filtro) == escolhas:
                continue
            _opcoes_enviadas[id_filtro] = escolhas
            ui.update_selectize(id_filtro, choices=escolhas, selected=atual)

    @reactive.effect
    @reactive.event(input.enviar)
    async def _enviar():
        auditar, pagar = _pode("auditar_ppf"), _pode("processar_pagamento")
        if not auditar and not (
            pagar and any(_pode_editar_linha(linha, auditar, pagar) for linha in _pagina_desenhada.values())
        ):
            _avisar(
                "Somente a auditoria, ou pagamentos com data de hoje, podem enviar dados. "
                + quem_libera("auditar_ppf", "processar_pagamento"),
                titulo="Sem permissão",
            )
            return
        usuario = _usuario()
        corrigidas = 0
        lote: list[dict] = []
        for posicao, linha in sorted(_pagina_desenhada.items()):
            if not _pode_editar_linha(linha, auditar, pagar):
                continue
            ident = str(linha.get("id_unico") or "")
            campo_valor, campo_banco = f"pg_valor_{posicao}", f"pg_banco_{posicao}"
            campo_data = f"pg_data_{posicao}"
            if not ident or campo_valor not in input:
                continue
            valor = _numero(input[campo_valor]())
            banco = (input[campo_banco]() or "").strip() or None if (campo_banco in input) else None
            quando = input[campo_data]() if campo_data in input else None

            original = linha.get("VALOR_ORIGINAL")
            try:
                original = float(original) if original is not None else None
            except (TypeError, ValueError):
                original = None
            if valor is None and original is not None:
                valor = round(original, 2)
            elif valor is not None and original and valor < original:
                valor = round(original, 2)
                corrigidas += 1
            juros = None
            if valor is not None and original is not None:
                juros = max(0.0, round(valor - original, 2))

            lote.append(
                {
                    "id_unico": ident,
                    "valor_pago": valor,
                    "juros": juros,
                    "banco": banco,
                    "data_pagamento": quando,
                    "documento": linha.get("DOCUMENTO"),
                }
            )

        revenda = _revenda() or ""

        def _gravar_lote() -> list[str]:
            falhas = []
            manual_arquivo.editar_pagamentos(lote, usuario)
            for item in lote:
                try:
                    gravacao.gravar_pagamento(
                        item["id_unico"],
                        revenda,
                        valor_pago=item["valor_pago"],
                        juros=item["juros"],
                        banco=item["banco"],
                        data_pagamento=item["data_pagamento"],
                    )
                except Exception as erro:
                    falhas.append(f"{item['documento']}: {str(erro)[:80]}")
            return falhas

        try:
            erros = await asyncio.to_thread(_gravar_lote)
        except Exception as erro:
            erros = [f"arquivo da tela: {str(erro)[:80]}"] * max(len(lote), 1)
        gravadas = max(len(lote) - len(erros), 0)

        versao.set(versao() + 1)
        if erros:
            _avisar(
                f"{gravadas} gravado(s); {len(erros)} falharam — {erros[0]}",
                tipo="error",
                titulo="Enviar",
            )
            return
        recado = f"{gravadas} pagamento(s) processado(s)."
        if corrigidas:
            recado += (
                f" {corrigidas} com valor pago abaixo do original foram"
                " corrigidos para o valor original (regra do sistema)."
            )
        _avisar(recado, tipo="success", titulo="Enviar")

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar():
        for id_filtro, _r, _c in FILTROS:
            ui.update_selectize(id_filtro, selected="")
        for id_chave, _r in CHAVES:
            ui.update_switch(id_chave, value=False)
        ui.update_checkbox("so_com_anexo", value=False)
        ui.update_checkbox("so_sem_anexo", value=False)
        ui.update_date_range("intervalo", start="", end="")
        dia_do_pagos.set(None)
        fabrica_ligada.set(False)
        paginador.reiniciar()

    dia_do_pagos = reactive.value(None)

    @reactive.effect
    @reactive.event(input.chave_pagos)
    def _pagos_com_data():
        if not input.chave_pagos():
            dia_do_pagos.set(None)
            return
        intervalo = input.intervalo() or (None, None)
        if intervalo[0] or intervalo[1]:
            return
        dia = date.today() - timedelta(days=1)
        while dia.weekday() >= 5:
            dia -= timedelta(days=1)
        dia_do_pagos.set(dia)
        ui.update_date_range("intervalo", start=dia, end=dia)

    @reactive.effect
    @reactive.event(input.so_com_anexo)
    def _anexo_exclusivo():
        if input.so_com_anexo():
            ui.update_checkbox("so_sem_anexo", value=False)

    @reactive.effect
    @reactive.event(input.so_sem_anexo)
    def _sem_anexo_exclusivo():
        if input.so_sem_anexo():
            ui.update_checkbox("so_com_anexo", value=False)

    @reactive.effect
    @reactive.event(input.limpar_data)
    def _limpar_data():
        ui.update_date_range("intervalo", start="", end="")
        dia_do_pagos.set(None)
        paginador.reiniciar()

    @render.ui
    def cards_bancos():
        base = tabela_visivel()
        cartoes = []
        if not base.is_empty():
            totais = (
                base.with_row_index("_ORDEM")
                .filter(pl.col("_EDITAVEL") & (pl.col("VALOR_PAGO") > 0) & (pl.col("BANCO").fill_null("") != ""))
                .group_by("BANCO")
                .agg(pl.col("VALOR_PAGO").sum().alias("PAGO"), pl.col("_ORDEM").min())
                .sort("_ORDEM")
            )
            cartoes = [
                cartao_banco(
                    _rotulo_banco(banco),
                    [
                        ui.div(
                            ui.span("Pago", class_="ppf-banco-rotulo"),
                            ui.span(formatar_reais(pago), class_="ppf-banco-valor ppf-banco-pago"),
                            class_="ppf-banco-linha",
                        )
                    ],
                )
                for banco, pago in totais.select("BANCO", "PAGO").iter_rows()
            ]
        return ui.div(*cartoes, class_="ppf-bancos ppf-bancos-pagamentos", **{"data-cartoes": str(len(cartoes))})

    ordem = reactive.value(None)

    def _ligar_ordem(i: int, rotulo: str) -> None:
        @reactive.effect
        @reactive.event(input[f"ordem_{i}"])
        def _ordenar():
            atual = ordem()
            ordem.set((rotulo, not atual[1]) if atual and atual[0] == rotulo else (rotulo, True))
            paginador.reiniciar()

        @render.ui
        def _seta():
            atual = ordem()
            if not atual or atual[0] != rotulo:
                return ui.span(class_="crec-seta")
            return ui.span(class_="crec-seta crec-seta-ativa" + ("" if atual[1] else " crec-seta-desc"))

        output(_seta, id=f"seta_{i}")

    for _i, _rotulo in enumerate(_COLUNAS):
        if _rotulo in _ORDENA_POR:
            _ligar_ordem(_i, _rotulo)

    @reactive.calc
    def tabela_visivel() -> pl.DataFrame:
        base = filtrado()
        if base.is_empty():
            return base
        chaves, decrescente = ["DATA_PAGAMENTO", "_ID"], [True, True]
        escolhida = ordem()
        if escolhida and _ORDENA_POR[escolhida[0]] in base.columns:
            chaves = [_ORDENA_POR[escolhida[0]], *chaves]
            decrescente = [not escolhida[1], *decrescente]
        return base.sort(chaves, descending=decrescente, nulls_last=True)

    @reactive.calc
    def _pagina_atual() -> pl.DataFrame:
        base = tabela_visivel()
        if base.is_empty():
            return base
        inicio, fim = paginador.janela(base.height)
        return base.slice(inicio, fim - inicio)

    @render.ui
    def corpo_tabela():
        base = tabela_visivel()
        if base.is_empty():
            return None

        pagina = _pagina_atual()
        bancos = _bancos_da_revenda()
        auditar, pagar = _pode("auditar_ppf"), _pode("processar_pagamento")
        pode_apagar = _pode("excluir_pagamento")
        motivo_travado = "Quem paga só edita o pagamento com data de hoje" if pagar else "Somente a auditoria edita"
        _pagina_desenhada.clear()

        todas_fabricas = fabricas.fabricas()
        da_revenda = fabricas.fabrica_da_revenda(_revenda()) or {}
        docs = an.documentos_do_olho()
        avisos_baixa = d.avisos_da_baixa()
        bandeiras = dc.bandeiras_da_rede()
        icones_dos_destinos = json.dumps(dc.icones_dos_destinos(), ensure_ascii=False)
        linhas = []
        for posicao, linha in enumerate(pagina.iter_rows(named=True)):
            ident = str(linha.get("id_unico") or "")
            da_fila = bool(linha.get("_EDITAVEL"))
            interativa = posicao < LINHAS_INTERATIVAS
            editavel = interativa and _pode_editar_linha(linha, auditar, pagar)
            travado = (
                None
                if editavel
                else (motivo_travado if interativa else "Página muito grande: use 50 ou 100 por página")
            )
            _pagina_desenhada[posicao] = linha
            nome = str(linha.get("FORNECEDOR") or "")
            olho = None
            documento = linha.get("DOCUMENTO")
            doc_norm = gravacao.normalizar_documento(documento)
            banco = str(linha.get("BANCO") or "")
            sem_boleto = cp.tipo_do_olho(ident, doc_norm, nome, docs, gravacao.titulo_sem_boleto, an.antigos_do_titulo)
            bandeira = bandeiras.get(base_do(ident)) if ident else None
            icone_destino = dc.icone_do_destino(banco, bandeira)
            if sem_boleto is not None or icone_destino:
                titulo_olho = (
                    "Nota sem boleto anexado — pagamento por Pix"
                    if sem_boleto
                    else "PDF salvo"
                    if sem_boleto is not None
                    else "Sem PDF salvo"
                )
                if icone_destino:
                    no_cartao = f" ({bandeira.capitalize()})" if bandeira and dc.icone_da_bandeira(bandeira) else ""
                    titulo_olho = f"Pagamento: {banco}{no_cartao}. {titulo_olho}"
                normal = (
                    ("img/ppf/pix-icon.svg" if sem_boleto else "img/ppf/view.svg") if sem_boleto is not None else ""
                )
                icone = ui.tags.img(
                    src=icone_destino or normal,
                    class_="ppf-cel-anexo ppf-cel-olho"
                    + (" ppf-cel-pix" if sem_boleto and not icone_destino else "")
                    + (" ppf-cel-destino" if icone_destino else ""),
                    alt="",
                    data_icone_normal=normal,
                    data_icones=(
                        json.dumps(dc.icones_com_a_bandeira(bandeira), ensure_ascii=False)
                        if bandeira
                        else icones_dos_destinos
                    ),
                )
                abrir = None
                if cp.tem_arquivo_no_olho(ident, doc_norm, nome, docs, an.antigos_do_titulo):
                    _olhos_desenhados[ident] = (documento, nome)
                    abrir = url_olho + _emenda_olho + "id=" + quote(ident)
                if abrir:
                    olho = ui.tags.a(
                        icone, href=abrir, target="_blank", rel="noopener", class_="ppf-olho-link", title=titulo_olho
                    )
                elif interativa:
                    olho = ui.input_action_button(
                        f"pg_olho_{posicao}", icone, class_="ppf-btn-linha ppf-btn-anexo", title=titulo_olho
                    )
                else:
                    olho = ui.span(icone, title=titulo_olho)
            fabrica = fabricas.fabrica_do_fornecedor(nome, todas_fabricas)
            realca = fabrica is not None and (
                fabrica.get("realce_em_toda_revenda") or fabrica["chave"] == da_revenda.get("chave")
            )
            original = linha.get("VALOR_ORIGINAL")
            texto_original = "" if _vazio(original) else _reais(original)
            juros = linha.get("JUROS")
            classes = []
            if not da_fila:
                classes.append("ppf-linha-erp")
            if str(linha.get("ENTRADA_MANUAL") or "") == "Sim":
                classes.append("ppf-linha-manual")

            if not da_fila:
                cel_data = ui.tags.td(_data(linha.get("DATA_PAGAMENTO")))
                cel_valor = ui.tags.td(_reais(linha.get("VALOR_PAGO")), class_="ppf-cel-valor")
                cel_banco = ui.tags.td(banco, class_="ppf-cel-centro")
            elif editavel:
                cel_data = ui.tags.td(
                    ui.input_date(
                        f"pg_data_{posicao}",
                        "",
                        value=linha.get("DATA_PAGAMENTO") or "",
                        format="dd/mm/yyyy",
                        language="pt-BR",
                    ),
                    class_="ppf-cel-campo",
                )
                cel_valor = ui.tags.td(
                    ui.input_text(
                        f"pg_valor_{posicao}",
                        "",
                        value=_reais_cru(linha.get("VALOR_PAGO")),
                        placeholder="0,00",
                    ),
                    class_="ppf-cel-valor ppf-cel-campo campo-reais-cru",
                )
                cel_banco = ui.tags.td(
                    ui.input_select(
                        f"pg_banco_{posicao}",
                        "",
                        choices=_opcoes_banco(bancos, banco),
                        selected=banco,
                    ),
                    class_="ppf-cel-campo",
                )
            else:
                cel_data = ui.tags.td(
                    ui.tags.input(
                        type="text",
                        value=_data(linha.get("DATA_PAGAMENTO")),
                        class_="form-control",
                        disabled="disabled",
                        title=travado,
                    ),
                    class_="ppf-cel-campo",
                )
                cel_valor = ui.tags.td(
                    ui.tags.input(
                        type="text",
                        value=_reais_cru(linha.get("VALOR_PAGO")),
                        class_="form-control",
                        disabled="disabled",
                        title=travado,
                    ),
                    class_="ppf-cel-valor ppf-cel-campo",
                )
                cel_banco = ui.tags.td(
                    ui.tags.select(
                        ui.tags.option(_rotulo_banco(banco), value=banco, selected="selected"),
                        class_="form-select",
                        disabled="disabled",
                        title=travado,
                    ),
                    class_="ppf-cel-campo",
                )

            if not da_fila:
                excluir = ui.span(
                    icon_svg("circle-info", a11y="deco"),
                    " CONTROL",
                    class_="ppf-cracha-control",
                    title="Baixado por fora do DF",
                )
            elif interativa and pode_apagar:
                excluir = ui.input_action_button(
                    f"pg_excluir_{posicao}",
                    icon_svg("trash", a11y="deco"),
                    class_="ppf-btn-linha ppf-btn-excluir-pagamento",
                    title="Excluir linha",
                )
            else:
                excluir = ui.tags.button(
                    icon_svg("trash", a11y="deco"),
                    type="button",
                    class_="btn ppf-btn-linha ppf-btn-excluir-pagamento",
                    disabled="disabled",
                    title=("Você não tem permissão para excluir este registro." if not pode_apagar else travado),
                )

            linhas.append(
                ui.tags.tr(
                    ui.tags.td(_data(linha.get("DATA"))),
                    cel_data,
                    ui.tags.td(str(linha.get("TIPO") or "")),
                    ui.tags.td(str(linha.get("CENTRO_CUSTO") or "")),
                    ui.tags.td(
                        nome,
                        class_="ppf-cel-fabrica" if realca else None,
                        style=(f"color: {fabrica['cor_texto']};" if realca and fabrica.get("cor_texto") else None),
                    ),
                    ui.tags.td(
                        ui.div(
                            ui.span(
                                str(linha.get("DOCUMENTO") or ""),
                                _aviso_da_baixa(avisos_baixa.get(ident)) if da_fila else None,
                                class_="ppf-doc-nome",
                            ),
                            ui.input_action_button(
                                f"pg_anexo_{posicao}",
                                ui.tags.img(src="img/ppf/pdf-icon.svg", class_="ppf-cel-anexo", alt="Enviar PDF"),
                                class_="ppf-btn-linha ppf-btn-anexo",
                                title="Enviar/Substituir PDF",
                            )
                            if interativa
                            else None,
                            olho,
                            class_="ppf-cel-tipodoc",
                        ),
                    ),
                    ui.tags.td(
                        ui.div(
                            ui.span("R$", class_="ppf-moeda"),
                            ui.span(
                                ("-" if texto_original.startswith("-") else "")
                                + texto_original.replace("-", "").replace("R$", "").strip(),
                                class_="ppf-numero",
                            ),
                            class_="ppf-valor-contabil",
                        )
                        if texto_original
                        else None,
                        class_="ppf-cel-valor ppf-cel-contabil",
                    ),
                    cel_valor,
                    ui.tags.td(_reais(0.0 if _vazio(juros) else juros), class_="ppf-cel-valor"),
                    cel_banco,
                    ui.tags.td(excluir, class_="ppf-cel-excluir"),
                    class_=" ".join(classes) or None,
                )
            )

        return ui.TagList(*linhas)

    @render.ui
    def rodape_tabela():
        base = tabela_visivel()
        if base.is_empty():
            return ui.div(
                "Sem título no filtro atual.",
                class_="text-muted px-2 py-3",
            )
        return paginador.controles(base.height)

    _alvo_exclusao = reactive.value("")

    _acoes_por_linha: list = []
    _arquivos_vistos: dict = {}

    def _ligar_linha(posicao: int) -> None:

        def _excluir():
            if not _clicou(f"pg_excluir_{posicao}"):
                return
            linha = _pagina_desenhada.get(posicao)
            if not linha:
                return
            if _barrar("excluir_pagamento"):
                return
            _alvo_exclusao.set(str(linha.get("id_unico") or ""))
            manual = str(linha.get("ENTRADA_MANUAL") or "") == "Sim"
            ui.modal_show(
                ui.modal(
                    ui.p(
                        "Deseja remover este pagamento manual da tela de pagamentos? O registro será mantido."
                        if manual
                        else "Tem certeza que deseja excluir esta linha? Isso não pode ser desfeito!",
                        ui.tags.br(),
                        ui.tags.strong(str(linha.get("FORNECEDOR") or "")),
                        f" — {linha.get('DOCUMENTO') or ''} — {_reais(linha.get('VALOR_ORIGINAL'))}",
                    ),
                    ui.p(
                        "Ele sai da lista de pagamentos e volta a pendente em Contas a Pagar.",
                        class_="text-muted small",
                    ),
                    title="Excluir título",
                    easy_close=True,
                    footer=ui.div(
                        ui.input_action_button(
                            "confirmar_exclusao",
                            "Excluir",
                            class_="btn-danger",
                        ),
                        ui.modal_button("Cancelar"),
                    ),
                )
            )

        def _anexos():
            clicou_anexo = _clicou(f"pg_anexo_{posicao}")
            clicou_olho = _clicou(f"pg_olho_{posicao}")
            if not (clicou_anexo or clicou_olho):
                return
            if trava_caixa.barrar(_usuario()):
                return
            _abrir_anexos()

        def _abrir_anexos(recado: tuple[str, str] | None = None) -> None:
            linha = _pagina_desenhada.get(posicao)
            if not linha:
                return
            ident = str(linha.get("id_unico") or "")
            if not ident:
                return
            try:
                salvos = gravacao.anexos_do_titulo(ident)
            except Exception as erro:
                salvos = []
                print(f"Pagamentos: nao deu pra listar anexos -- {erro}")
            antigos = an.antigos_do_titulo(ident, linha.get("DOCUMENTO"), str(linha.get("FORNECEDOR") or ""))
            ui.modal_show(
                ui.modal(
                    corpo_aviso(recado[0], titulo="Anexos", tipo=recado[1]) if recado else None,
                    ui.p(
                        ui.tags.strong(str(linha.get("FORNECEDOR") or "")),
                        f" — {linha.get('DOCUMENTO') or ''}",
                    ),
                    ui.input_file(
                        session.ns(f"pg_subir_{posicao}"),
                        "Anexar arquivo",
                        accept=[".pdf", ".png", ".jpg", ".jpeg"],
                        button_label="Escolher",
                        placeholder="nenhum",
                        multiple=False,
                        width="100%",
                    )
                    if _pode("anexar_titulo")
                    else ui.p(
                        "Sem permissão para anexar.",
                        class_="text-muted small",
                    ),
                    ui.hr(),
                    ui.p("Anexos salvos", class_="fw-bold mb-1"),
                    ui.tags.ul(*[ui.tags.li(a.name) for a in salvos])
                    if salvos
                    else ui.p(
                        "Nenhum anexo para este título.",
                        class_="text-muted small",
                    )
                    if not antigos
                    else None,
                    ui.tags.ul(
                        *[
                            ui.tags.li(
                                ui.tags.a(
                                    a.name,
                                    " (app antigo)",
                                    href=url_anexo_antigo
                                    + ("&" if "?" in url_anexo_antigo else "?")
                                    + "nome="
                                    + quote(a.name),
                                    target="_blank",
                                    title="Visualizar",
                                )
                            )
                            for a in antigos
                        ]
                    )
                    if antigos
                    else None,
                    title="Anexos do título",
                    easy_close=True,
                    footer=ui.modal_button("Fechar"),
                )
            )

        def _subir():
            campo = f"pg_subir_{posicao}"
            if campo not in input:
                return
            arquivos = input[campo]()
            if not arquivos:
                return
            linha = _pagina_desenhada.get(posicao)
            if not linha:
                return
            if _barrar("anexar_titulo"):
                return
            ident = str(linha.get("id_unico") or "")
            try:
                for arquivo in arquivos:
                    gravacao.guardar_anexo(
                        ident,
                        arquivo["datapath"],
                        arquivo["name"],
                    )
            except Exception as erro:
                _abrir_anexos((f"Falhou ao anexar: {str(erro)[:140]}", "error"))
                return
            with reactive.isolate():
                versao.set(versao() + 1)
            _abrir_anexos(("Anexo salvo.", "success"))

        _acoes_por_linha.append((posicao, _excluir, _anexos, _subir))

    for _posicao in range(LINHAS_INTERATIVAS):
        _ligar_linha(_posicao)

    @reactive.effect
    def _linhas_da_pagina():
        for posicao, excluir, anexos, subir in _acoes_por_linha:
            excluir()
            anexos()
            campo = f"pg_subir_{posicao}"
            if campo in input:
                valor = input[campo]()
                if valor and _arquivos_vistos.get(campo) != valor:
                    _arquivos_vistos[campo] = valor
                    subir()

    @reactive.effect
    @reactive.event(input.confirmar_exclusao)
    def _confirmar_exclusao():
        ident = _alvo_exclusao()
        if not ident:
            return
        if _barrar("excluir_pagamento"):
            return
        usuario = _usuario()
        try:
            feito = gravacao.devolver_a_pendente(ident)
        except Exception as erro:
            _avisar(f"Falhou ao excluir: {str(erro)[:140]}", tipo="error", titulo="Excluir título")
            return
        for i in feito["ids"]:
            manual_arquivo.desmarcar(i, "pagar", usuario)
        manual_arquivo.desfazer_partes(feito["partes"], usuario)
        manual_arquivo.esquecer_pagamentos([i for i in feito["ids"] if i not in feito["partes"]])
        manual_arquivo.anotar_fila([], feito["ids"], usuario)
        _alvo_exclusao.set("")
        versao.set(versao() + 1)
        _avisar(
            "Pagamento removido da lista: o título voltou a pendente em Contas a Pagar."
            if feito["caso"] != "manual"
            else "Pagamento manual removido da lista; o registro foi mantido.",
            tipo="success",
            titulo="Excluir título",
        )


def pag_pagamentos_ui(revenda: str | None = None):
    return pagamentos_ui("pagamentos", revenda)


def pag_pagamentos_server(revenda_atual=None):
    return pagamentos_server("pagamentos", revenda_atual=revenda_atual)
