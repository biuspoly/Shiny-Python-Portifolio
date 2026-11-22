import asyncio
from datetime import date
from urllib.parse import quote

import polars as pl
from faicons import icon_svg
from shiny import module, reactive, render, ui

from core import gravacao, manual_arquivo
from core.auth import identificar_usuario
from core.config import pode, quem_libera
from core.secao import ICONE_EMPRESTIMOS, titulo_secao
from core.visibilidade import pagina_visivel

from .Dados import dados_emprestimos as de

FILTRO_COM_BUSCA = {
    "placeholder": "Todos",
    "plugins": ["clear_button", "restore_on_backspace"],
    "dropdownParent": "body",
    "dropdownClass": "selectize-dropdown ppf-filtro-dropdown",
}

VALOR_NAVSET = "emp"

NOMES_MES = [
    "",
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]

FILTROS = [
    ("revenda", "Empresa", "Revenda", "Todas", "emp-filtro"),
    ("banco", "Banco", "Banco", "Todos", "emp-filtro emp-filtro-largo"),
    ("tipo", "Tipo", "Tipo", "Todos", "emp-filtro emp-filtro-largo"),
    ("ano", "Ano Contratação", "ano", "Todos", "emp-filtro emp-compacto"),
    ("mes", "Mês Contratação", "mes", "Todos", "emp-filtro emp-compacto"),
]

COLUNAS = (
    ("Empresa", "Revenda", "texto", "text-center"),
    ("Contratação", "Contratação", "data", "text-center"),
    ("Banco", "Banco", "banco", "text-left"),
    ("Tipo", "Tipo", "texto", "text-left"),
    ("Valor Crédito", "Valor Crédito", "moeda", "col-valor-contabil"),
    ("Entrada", "Entrada", "moeda", "col-valor-contabil"),
    ("Data Inicial", "Data Inicial", "data", "text-center"),
    ("Data Final", "Data Final", "data", "text-center"),
    ("Valor Parcela", "Valor Parcela", "moeda", "col-valor-contabil"),
    ("Parcelas", "Parcelas", "inteiro", "text-center"),
    ("Vencimento", "Vencimento", "texto", "text-center"),
    ("Taxa Juros %", "Taxa Juros %", "taxa", "col-valor-contabil"),
    ("Parcelas Pagas", "Parcelas Pagas", "inteiro", "text-center"),
    ("Parcelas a Vencer", "Parcelas a vencer", "inteiro", "text-center"),
    ("Saldo a Pagar", "Saldo a Pagar", "moeda", "col-valor-contabil"),
)
SUBTOTAIS = {"Valor Crédito": "credito", "Valor Parcela": "parcela", "Saldo a Pagar": "pagar"}
EDITAVEIS = {"Valor Crédito": "valor_credito", "Entrada": "entrada", "Taxa Juros %": "taxa_juros"}
MAX_LINHAS = 200


def _vazio(valor) -> bool:
    return valor is None or valor != valor


def _reais(valor) -> str:
    if _vazio(valor):
        valor = 0.0
    inteiro = f"{abs(float(valor)):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"{'-' if float(valor) < 0 else ''}{inteiro}"


def _rotulo_opcao(chave: str, valor) -> str:
    return f"{int(valor):02d} — {NOMES_MES[int(valor)]}" if chave == "mes" else str(valor)


@module.ui
def emprestimos_ui(revenda: str | None = None):
    return ui.div(
        ui.card(
            ui.card_header(
                titulo_secao("Empréstimos e Financiamentos", icone=ICONE_EMPRESTIMOS), class_="emp-cabecalho"
            ),
            ui.div(
                ui.div(
                    ui.div(
                        *[
                            ui.div(
                                ui.tags.label(rotulo, class_="emp-rotulo"),
                                ui.input_selectize(
                                    id_filtro, None, {"": todos}, options={**FILTRO_COM_BUSCA, "placeholder": todos}
                                ),
                                class_=classe,
                            )
                            for id_filtro, rotulo, _chave, todos, classe in FILTROS
                        ],
                        ui.div(
                            ui.span("Limpar", class_="emp-rotulo"),
                            ui.input_action_button(
                                "limpar", icon_svg("eraser", a11y="deco"), class_="emp-limpar", title="Limpar filtros"
                            ),
                            class_="emp-limpar-slot",
                        ),
                        class_="emp-filtros",
                    ),
                    class_="emp-toolbar",
                ),
                ui.div(
                    ui.tags.table(
                        ui.tags.thead(
                            ui.output_ui("subtotais", container=ui.tags.tr, class_="subtotais-row"),
                            ui.tags.tr(
                                *[
                                    ui.tags.th(
                                        ui.input_action_link(
                                            f"ordem_{i}",
                                            ui.TagList(rotulo, ui.output_ui(f"seta_{i}", inline=True)),
                                        ),
                                        class_="th-ordenavel" + (f" sticky-col sticky-col-{i + 1}" if i < 4 else ""),
                                        title="Clique para ordenar",
                                    )
                                    for i, (rotulo, _c, _f, _a) in enumerate(COLUNAS)
                                ],
                                class_="cabecalho-row",
                            ),
                        ),
                        ui.output_ui("corpo", container=ui.tags.tbody),
                        class_="emp-tabela",
                    ),
                    class_="emp-caixa",
                ),
                class_="emp-card",
            ),
        ),
        class_="fin-modulo",
    )


@module.server
def emprestimos_server(input, output, session, revenda_atual=None):
    versao = reactive.value(0)

    def _revenda() -> str | None:
        return revenda_atual() if callable(revenda_atual) else revenda_atual

    def _usuario() -> str:
        try:
            raiz = session.root_scope() if hasattr(session, "root_scope") else session
            quem, _script = identificar_usuario(raiz.http_conn)
            return (quem or "").strip() or "desconhecido"
        except Exception:
            return "desconhecido"

    def _incrementar(valor: reactive.Value) -> None:
        with reactive.isolate():
            valor.set(valor() + 1)

    @reactive.calc
    def base_bruta() -> pl.DataFrame:
        versao()
        return de.contratos(_revenda())

    def _escolhidos() -> dict[str, object]:
        return {chave: input[id_filtro]() for id_filtro, _r, chave, _t, _c in FILTROS}

    @reactive.calc
    def filtrado() -> pl.DataFrame:
        return de.recortar(base_bruta(), _escolhidos())

    _opcoes_enviadas: dict[str, dict] = {}

    @reactive.effect
    def _preencher_filtros():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        base = base_bruta()
        if base.is_empty():
            return
        escolhidos = _escolhidos()
        for id_filtro, _rotulo, chave, todos, _classe in FILTROS:
            opcoes = de.opcoes_em_cascata(base, chave, escolhidos)
            escolhas = {"": todos, **{str(o): _rotulo_opcao(chave, o) for o in opcoes}}
            if _opcoes_enviadas.get(id_filtro) == escolhas:
                continue
            _opcoes_enviadas[id_filtro] = escolhas
            ui.update_selectize(id_filtro, choices=escolhas, selected=str(escolhidos.get(chave) or ""))

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar():
        for id_filtro, *_resto in FILTROS:
            ui.update_selectize(id_filtro, selected="")

    ordem = reactive.value((1, True))

    def _ligar_ordem(i: int) -> None:
        @reactive.effect
        @reactive.event(input[f"ordem_{i}"])
        def _ordenar():
            coluna, crescente = ordem()
            ordem.set((i, not crescente) if coluna == i else (i, True))

        @render.ui
        def _seta():
            coluna, crescente = ordem()
            if coluna != i:
                return ui.span("\u21c5", class_="sort-ind")
            return ui.span("\u25b2" if crescente else "\u25bc", class_="sort-ind is-ordenado")

        output(_seta, id=f"seta_{i}")

    for _i in range(len(COLUNAS)):
        _ligar_ordem(_i)

    @reactive.calc
    def ordenado() -> pl.DataFrame:
        base = filtrado()
        if base.is_empty():
            return base
        indice, crescente = ordem()
        _rotulo, coluna, fmt, _alinhamento = COLUNAS[indice]
        chave = pl.col(coluna)
        if coluna == "Vencimento":
            chave = chave.str.extract(r"(\d+)").cast(pl.Int64, strict=False)
        elif fmt in ("texto", "banco"):
            chave = (
                pl.when(chave.str.strip_chars().is_in(["", "-"]))
                .then(None)
                .otherwise(chave)
                .str.normalize("NFD")
                .str.replace_all(r"\p{M}", "")
                .str.to_lowercase()
            )
        elif fmt == "moeda":
            chave = chave.fill_nan(0).fill_null(0)
        elif fmt == "inteiro":
            chave = chave.fill_null(0)
        elif fmt == "taxa":
            chave = chave.fill_nan(None)
        return base.sort(chave, descending=not crescente, nulls_last=True, maintain_order=True)

    @reactive.calc
    def _pode_editar() -> bool:
        return pode(_usuario(), "processar_pagamento")

    @render.ui
    def subtotais():
        base = filtrado()
        if base.is_empty():
            return ui.TagList()
        tot = de.totais(base)
        return ui.TagList(
            *[
                ui.tags.th(
                    f"{'-' if tot[SUBTOTAIS[rotulo]] < 0 else ''}R$ {_reais(abs(tot[SUBTOTAIS[rotulo]]))}"
                    if rotulo in SUBTOTAIS
                    else "",
                    class_=("subtotais-valor" if rotulo in SUBTOTAIS else "")
                    + (f" sticky-col sticky-col-{i + 1}" if i < 4 else ""),
                )
                for i, (rotulo, _c, _f, _a) in enumerate(COLUNAS)
            ]
        )

    def _valor_contabil(valor, fmt: str, lapis):
        if fmt == "taxa":
            texto = "-" if _vazio(valor) else f"{float(valor):.2f}".replace(".", ",")
            partes = [ui.span(texto, class_="valor"), ui.span("%", class_="moeda")]
        else:
            partes = [ui.span("R$", class_="moeda"), ui.span(_reais(valor), class_="valor")]
        return ui.div(*partes, lapis, class_="valor-wrapper")

    @render.ui
    def corpo():
        base = ordenado()
        _linhas_na_tela.clear()
        if base.is_empty():
            return ui.tags.tr(
                ui.tags.td(
                    ui.div(ui.p("Nenhum empréstimo encontrado."), class_="emp-vazio"),
                    colspan=str(len(COLUNAS)),
                )
            )
        contratos_mudaram()
        editar = _pode_editar()
        pdfs: dict[str, set] = {}
        linhas = []
        for n, r in enumerate(base.iter_rows(named=True)):
            _linhas_na_tela.append((r["Revenda"], r["Contrato"]))
            revenda = r["Revenda"] or ""
            if revenda not in pdfs:
                pdfs[revenda] = gravacao.contratos_salvos(revenda)
            tem_pdf = gravacao.nome_do_contrato(r["Contrato"] or "").lower() in pdfs[revenda]
            celulas = []
            for i, (rotulo, coluna, fmt, alinhamento) in enumerate(COLUNAS):
                valor = r.get(coluna)
                classe = alinhamento + (f" sticky-col sticky-col-{i + 1}" if i < 4 else "")
                titulo = None
                if fmt == "banco":
                    ver = (
                        ui.tags.a(
                            ui.tags.img(src="img/ppf/view.svg", alt="PDF Salvo", class_="pdf-check-img"),
                            href=_url_contrato(revenda, r["Contrato"]),
                            target="_blank",
                            title="Ver contrato",
                            class_="emp-pdf-ver",
                        )
                        if tem_pdf
                        else ui.span(
                            ui.tags.img(src="img/ppf/view.svg", alt="", class_="pdf-check-img"),
                            class_="emp-pdf-ver is-hidden",
                        )
                    )
                    conteudo = ui.div(
                        ui.span(valor or "-", class_="banco-nome"),
                        ui.span(
                            ui.input_action_button(
                                f"pdf_{n}",
                                ui.tags.img(src="img/ppf/file-upload-2.svg", alt="Enviar PDF", class_="pdf-upload-img"),
                                class_="upload-pdf-btn",
                                title="Enviar/Substituir PDF",
                            )
                            if n < MAX_LINHAS
                            else None,
                            ver,
                            class_="pdf-actions",
                        ),
                        class_="banco-cell",
                    )
                    titulo = valor or "-"
                elif fmt in ("moeda", "taxa"):
                    lapis = None
                    if rotulo in EDITAVEIS and editar and n < MAX_LINHAS:
                        lapis = ui.input_action_button(
                            f"editar_{n}_{list(EDITAVEIS).index(rotulo)}",
                            icon_svg("pencil", a11y="deco"),
                            class_="btn-editar-valor",
                            title=f"Editar {rotulo}",
                        )
                    conteudo = _valor_contabil(valor, fmt, lapis)
                elif fmt == "data":
                    conteudo = valor.strftime("%d/%m/%Y") if isinstance(valor, date) else "-"
                elif fmt == "inteiro":
                    conteudo = "0" if _vazio(valor) else str(int(valor))
                else:
                    conteudo = valor or "-"
                    titulo = conteudo
                celulas.append(ui.tags.td(conteudo, class_=classe, title=titulo))
            linhas.append(ui.tags.tr(*celulas))
        return ui.TagList(*linhas)

    _linhas_na_tela: list[tuple[str, str]] = []
    contrato_aberto = reactive.value(("", ""))
    contratos_mudaram = reactive.value(0)
    excluir_pendente = reactive.value(False)
    recado_contrato = reactive.value(("", ""))

    def _entregar_contrato(request):
        from starlette.responses import PlainTextResponse, Response

        revenda = request.query_params.get("rev", "")
        contrato = request.query_params.get("c", "")
        if (revenda, contrato) not in set(_linhas_na_tela):
            return PlainTextResponse("contrato nao encontrado", status_code=404)
        conteudo = gravacao.conteudo_do_contrato(revenda, contrato)
        if conteudo is None:
            return PlainTextResponse("contrato nao encontrado", status_code=404)
        nome = gravacao.nome_do_contrato(contrato)
        return Response(
            conteudo, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nome}"'}
        )

    url_contrato = session.dynamic_route("ver_contrato", _entregar_contrato)
    _emenda = "&" if "?" in url_contrato else "?"

    def _url_contrato(revenda: str, contrato: str) -> str:
        return url_contrato + _emenda + "rev=" + quote(revenda or "") + "&c=" + quote(contrato or "")

    _cliques: dict[str, int] = {}

    def _clicou(nome: str) -> bool:
        if nome not in input:
            return False
        atual = input[nome]() or 0
        anterior = _cliques.get(nome, 0)
        _cliques[nome] = atual
        return atual > anterior

    def _recado(texto: str, tipo: str = "") -> None:
        recado_contrato.set((texto, tipo))

    @render.ui
    def recado():
        texto, tipo = recado_contrato()
        return ui.div(texto, class_=f"emp-status emp-status-{tipo or 'info'}") if texto else ui.div()

    @render.ui
    def lista_contrato():
        contratos_mudaram()
        revenda, contrato = contrato_aberto()
        if not contrato:
            return ui.div()
        alvo = gravacao.contrato_salvo(revenda, contrato)
        if alvo is None:
            return ui.p("Nenhum contrato enviado.", class_="ppf-modal-lista-vazia")
        confirmacao = None
        if excluir_pendente():
            confirmacao = ui.div(
                ui.span(f"Excluir {alvo}?"),
                ui.input_action_button("confirmar_excluir", "Excluir", class_="btn btn-danger btn-sm"),
                ui.input_action_button("cancelar_excluir", "Cancelar", class_="btn btn-secondary btn-sm"),
                class_="ppf-modal-confirmar",
            )
        return ui.TagList(
            ui.tags.ul(
                ui.tags.li(
                    ui.div(
                        ui.tags.img(src="img/ppf/pdf-icon2.svg", class_="ppf-arquivo-icone", alt=""),
                        ui.span(alvo, class_="ppf-modal-lista-nome"),
                        class_="ppf-modal-lista-arquivo",
                    ),
                    ui.div(
                        ui.tags.a(
                            ui.tags.img(src="img/ppf/view.svg", alt="Ver"),
                            href=_url_contrato(revenda, contrato),
                            target="_blank",
                            class_="ppf-modal-btn ppf-modal-btn-ver",
                            title="Visualizar",
                        ),
                        ui.input_action_button(
                            "excluir_contrato",
                            ui.tags.img(src="img/ppf/delete-icon.svg", alt="Excluir"),
                            class_="ppf-modal-btn ppf-modal-btn-excluir",
                            title="Excluir contrato",
                        ),
                        class_="ppf-modal-lista-acoes",
                    ),
                ),
                class_="ppf-modal-lista",
            ),
            confirmacao,
        )

    def _modal_contrato(contrato: str):
        return ui.modal(
            ui.h3("Upload de Contrato (PDF)", class_="emp-modal-subtitulo"),
            ui.div(
                ui.input_file(
                    session.ns("arq_contrato"),
                    None,
                    button_label=ui.TagList(
                        ui.tags.img(src="img/ppf/pdf-icon2.svg", class_="ppf-arquivo-icone", alt=""),
                        "Selecionar contrato PDF",
                    ),
                    placeholder="Nenhum arquivo selecionado",
                    accept=".pdf",
                    width="100%",
                ),
                class_="ppf-modal-arquivo",
            ),
            ui.output_ui(session.ns("recado")),
            ui.tags.hr(class_="emp-modal-divisor"),
            ui.h3("Contratos disponíveis", class_="emp-modal-subtitulo"),
            ui.output_ui(session.ns("lista_contrato")),
            title=f"Contrato: {contrato}",
            easy_close=True,
            class_="emp-modal-contrato",
            footer=ui.modal_button("Fechar", class_="btn btn-secondary"),
            fade=False,
        )

    editando = reactive.value(None)
    recado_edicao = reactive.value(("", ""))
    aberturas_janela = [0]
    _tarefas: set[asyncio.Task] = set()

    @render.ui
    def status_edicao():
        texto, tipo = recado_edicao()
        return ui.div(texto, class_=f"emp-status emp-status-{tipo or 'error'}") if texto else ui.div()

    def _modal_edicao(revenda: str, contrato: str, rotulo: str, campo: str, atual):
        return ui.modal(
            ui.p(f"{contrato} — {revenda}", class_="emp-modal-info"),
            ui.tags.label(
                "Valor (%)" if campo == "taxa_juros" else "Valor (R$)",
                for_=session.ns("valor_editado"),
                class_="emp-modal-rotulo",
            ),
            ui.input_text(
                session.ns("valor_editado"), None, value="" if _vazio(atual) else _reais(atual), placeholder="0,00"
            ),
            ui.output_ui(session.ns("status_edicao")),
            title=f"Editar {rotulo}",
            easy_close=True,
            size="s",
            class_="emp-modal-editar",
            footer=ui.TagList(
                ui.input_action_button(session.ns("salvar_valor"), "Salvar"),
                ui.modal_button("Cancelar"),
            ),
            fade=False,
        )

    @reactive.effect
    def _cliques_da_tabela():
        pdfs = [n for n in range(MAX_LINHAS) if _clicou(f"pdf_{n}") and n < len(_linhas_na_tela)]
        lapis = [
            (n, j)
            for n in range(MAX_LINHAS)
            for j in range(len(EDITAVEIS))
            if _clicou(f"editar_{n}_{j}") and n < len(_linhas_na_tela)
        ]
        if pdfs:
            revenda, contrato = _linhas_na_tela[pdfs[0]]
            contrato_aberto.set((revenda, contrato))
            excluir_pendente.set(False)
            _recado("")
            aberturas_janela[0] += 1
            ui.modal_show(_modal_contrato(contrato), session=session)
            return
        if lapis:
            n, j = lapis[0]
            rotulo, campo = list(EDITAVEIS.items())[j]
            revenda, contrato = _linhas_na_tela[n]
            with reactive.isolate():
                linha = base_bruta().filter((pl.col("Revenda") == revenda) & (pl.col("Contrato") == contrato))
            atual = linha[rotulo][0] if not linha.is_empty() else None
            editando.set((revenda, contrato, campo, rotulo))
            recado_edicao.set(("", ""))
            aberturas_janela[0] += 1
            ui.modal_show(_modal_edicao(revenda, contrato, rotulo, campo, atual), session=session)

    @reactive.effect
    @reactive.event(input.arq_contrato)
    def _receber_contrato():
        enviados = input.arq_contrato()
        revenda, contrato = contrato_aberto()
        if not enviados or not contrato:
            return
        if not pode(_usuario(), "anexar_contrato_emprestimo"):
            _recado("Sem permissão. " + quem_libera("anexar_contrato_emprestimo"), "error")
            return
        arquivo = enviados[0]
        if not str(arquivo["name"]).lower().endswith(".pdf"):
            _recado("Selecione um arquivo PDF.", "error")
            return
        try:
            gravacao.guardar_contrato(revenda, contrato, arquivo["datapath"])
        except Exception as erro:
            _recado(f"Erro ao enviar: {str(erro)[:160]}", "error")
            return
        excluir_pendente.set(False)
        _recado("Contrato enviado com sucesso.", "success")
        _incrementar(contratos_mudaram)

    @reactive.effect
    def _excluir_contrato():
        if _clicou("excluir_contrato"):
            excluir_pendente.set(True)
            return
        if _clicou("cancelar_excluir"):
            excluir_pendente.set(False)
            return
        if not _clicou("confirmar_excluir"):
            return
        with reactive.isolate():
            revenda, contrato = contrato_aberto()
        excluir_pendente.set(False)
        if not contrato:
            return
        if not pode(_usuario(), "anexar_contrato_emprestimo"):
            _recado("Sem permissão. " + quem_libera("anexar_contrato_emprestimo"), "error")
            return
        if gravacao.excluir_contrato(revenda, contrato):
            _recado("Arquivo excluído.", "success")
        elif gravacao.contrato_salvo(revenda, contrato):
            _recado("Este contrato foi enviado pelo sistema antigo e só pode ser excluído por lá.", "error")
        else:
            _recado("Arquivo não encontrado.", "error")
        _incrementar(contratos_mudaram)

    @reactive.effect
    @reactive.event(input.salvar_valor)
    def _salvar_valor():
        alvo = editando()
        if not alvo:
            return
        revenda, contrato, campo, _rotulo = alvo
        if not _pode_editar():
            recado_edicao.set(("Sem permissão.", "error"))
            return
        bruto = (input.valor_editado() or "").strip().replace("R$", "").replace("%", "").replace(" ", "")
        if "," in bruto:
            bruto = bruto.replace(".", "").replace(",", ".")
        try:
            valor = float(bruto) if bruto else None
        except ValueError:
            recado_edicao.set(("Valor inválido.", "error"))
            return
        try:
            linha = gravacao.salvar_config_emprestimo(revenda, contrato, campo, valor, _usuario())
            manual_arquivo.guardar_config_emprestimo(linha)
        except Exception as erro:
            recado_edicao.set((f"Erro ao salvar: {str(erro)[:160]}", "error"))
            return
        editando.set(None)
        recado_edicao.set(("Valor salvo com sucesso", "success"))
        _incrementar(versao)

        vez = aberturas_janela[0]

        async def _fechar_depois():
            await asyncio.sleep(0.8)
            if aberturas_janela[0] == vez:
                try:
                    ui.modal_remove(session=session)
                except Exception:
                    pass

        tarefa = asyncio.create_task(_fechar_depois())
        _tarefas.add(tarefa)
        tarefa.add_done_callback(_tarefas.discard)


def pag_emprestimos_ui(revenda: str | None = None):
    return emprestimos_ui("emprestimos", revenda)


def pag_emprestimos_server(revenda_atual=None):
    return emprestimos_server("emprestimos", revenda_atual=revenda_atual)
