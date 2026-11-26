from datetime import datetime

import polars as pl
from shiny import module, reactive, render, ui

from core import manual_arquivo
from core.auth import identificar_usuario
from core.aviso import modal_aviso
from core.cartoes_banco import formatar_reais
from core.config import pode, quem_libera
from core.secao import titulo_secao
from pages.PPF.Dados import dados_ppf as d

VALOR_NAVSET = "jur"

LIMITE_TEXTO = 400

MAX_LINHAS = 500


def _com_limite(area):
    for no in area.children:
        if getattr(no, "name", None) == "textarea":
            no.attrs["maxlength"] = str(LIMITE_TEXTO)
    return area


COLUNAS_LISTA = [
    ("Revenda", "REVENDA"),
    ("Documento", "num_doc"),
    ("Fornecedor", "razao_social"),
    ("Valor Original", "valor_original"),
    ("Vencimento", "data_vencimento"),
    ("Baixa", "data_pagamento"),
    ("Juros", "juros"),
]


def _texto(valor) -> str:
    if valor is None or valor != valor:
        return ""
    return str(valor)


def _data(valor) -> str:
    if valor is None or valor != valor:
        return ""
    try:
        return valor.strftime("%d/%m/%Y")
    except (AttributeError, ValueError):
        return str(valor)


def titulos_com_juros(revenda: str | None) -> pl.DataFrame:
    base = d.contas_pagar()
    if base.is_empty():
        return base
    base = d.filtrar_por_revenda(base, revenda)
    if base.is_empty() or "juros" not in base.columns:
        return base.head(0)

    editados = manual_arquivo.pagamentos_por_titulo()
    if editados and "id_unico" in base.columns:
        por_id = {ident: dados.get("juros") for ident, dados in editados.items() if dados.get("juros") is not None}
        if por_id:
            base = base.with_columns(
                pl.col("id_unico")
                .replace_strict(por_id, default=None, return_dtype=pl.Float64)
                .fill_null(pl.col("juros"))
                .alias("juros")
            )
    return base.filter(pl.col("juros").is_not_null() & (pl.col("juros") != 0)).sort("juros", descending=True)


@module.ui
def juros_ui(revenda: str | None = None):
    return ui.div(
        ui.card(
            ui.card_header(
                titulo_secao(
                    "Títulos com juros",
                    emoji="\U0001f4c8",
                    extras=[
                        ui.div(
                            ui.input_checkbox(
                                "so_pendentes",
                                "Só os ainda sem justificativa",
                                value=False,
                            ),
                            class_="ms-auto ppf-juros-filtro",
                        ),
                    ],
                )
            ),
            ui.output_ui("lista"),
        ),
        ui.card(
            ui.card_header(titulo_secao("Dados do Documento", emoji="\U0001f9fe")),
            ui.output_ui("dados_do_documento"),
        ),
        ui.card(
            ui.card_header(titulo_secao("Justificativa", emoji="\U0001f4dd")),
            ui.div(
                ui.tags.label("Justificativa:", for_="justificativa", class_="ppf-juros-rotulo"),
                _com_limite(
                    ui.input_text_area(
                        "justificativa",
                        None,
                        placeholder="Descreva a justificativa",
                        rows=5,
                        width="100%",
                    )
                ),
                ui.output_ui("contador"),
                class_="px-2",
            ),
            ui.div(
                ui.input_action_button("enviar", "Enviar", class_="btn-primary"),
                class_="px-2 pb-2",
            ),
        ),
        class_="fin-modulo",
    )


@module.server
def juros_server(input, output, session, revenda_atual=None):
    escolhido = reactive.value(None)
    _escolhidas: dict[tuple, dict] = {}
    versao = reactive.value(0)
    _linhas: dict[int, dict] = {}

    def _revenda():
        return revenda_atual() if callable(revenda_atual) else revenda_atual

    def _usuario() -> str:
        quem, _script = identificar_usuario(session.root_scope().http_conn)
        return quem

    @reactive.calc
    def base() -> pl.DataFrame:
        versao()
        return titulos_com_juros(_revenda())

    @reactive.calc
    def gravadas() -> dict:
        versao()
        return manual_arquivo.justificativas_juros()

    @render.ui
    def lista():
        titulos = base()
        if titulos.is_empty():
            return ui.p(
                "Nenhum título com juros nesta revenda. A lista mostra o que o "
                "pipeline trouxe mais o que foi lançado na tela.",
                class_="text-muted small px-2 pb-2",
            )
        ja = gravadas()
        _linhas.clear()
        corpo = []
        for posicao, linha in enumerate(titulos.head(MAX_LINHAS).iter_rows(named=True)):
            _linhas[posicao] = linha
            chave = (_texto(linha.get("REVENDA")), _texto(linha.get("num_doc")))
            tem = chave in ja
            if input.so_pendentes() and tem:
                continue
            corpo.append(
                ui.tags.tr(
                    ui.tags.td(_texto(linha.get("REVENDA"))),
                    ui.tags.td(_texto(linha.get("num_doc"))),
                    ui.tags.td(_texto(linha.get("razao_social"))),
                    ui.tags.td(formatar_reais(linha.get("valor_original") or 0), class_="ppf-cel-valor"),
                    ui.tags.td(_data(linha.get("data_vencimento"))),
                    ui.tags.td(_data(linha.get("data_pagamento"))),
                    ui.tags.td(formatar_reais(linha.get("juros") or 0), class_="ppf-cel-valor ppf-juros-valor"),
                    ui.tags.td(
                        ui.span("justificado", class_="ppf-envio-selo ppf-envio-feito")
                        if tem
                        else ui.span("pendente", class_="ppf-envio-selo ppf-envio-falta-selo")
                    ),
                    ui.tags.td(
                        ui.input_action_button(
                            f"abrir_{posicao}",
                            "Justificar",
                            class_="btn btn-sm btn-outline-secondary",
                        )
                    ),
                    class_="ppf-juros-escolhida" if escolhido() == chave else None,
                )
            )
        if not corpo:
            return ui.p("Todos os títulos com juros já têm justificativa.", class_="text-muted small px-2 pb-2")
        return ui.div(
            ui.tags.table(
                ui.tags.thead(
                    ui.tags.tr(
                        *[ui.tags.th(r) for r, _c in COLUNAS_LISTA],
                        ui.tags.th("Situação"),
                        ui.tags.th(""),
                    )
                ),
                ui.tags.tbody(*corpo),
                class_="ppf-tabela-envio",
            ),
            class_="px-2 pb-2",
        )

    def _abrir(posicao: int) -> None:
        linha = _linhas.get(posicao) or {}
        chave = (_texto(linha.get("REVENDA")), _texto(linha.get("num_doc")))
        _escolhidas[chave] = linha
        escolhido.set(chave)
        anterior = gravadas().get(chave)
        ui.update_text_area(
            "justificativa",
            value=(anterior or {}).get("justificativa") or "",
        )

    _cliques: dict = {}

    @reactive.effect
    def _abrir_linha():
        for posicao in range(MAX_LINHAS):
            nome = f"abrir_{posicao}"
            if nome not in input:
                continue
            atual = input[nome]() or 0
            anterior = _cliques.get(nome, 0)
            _cliques[nome] = atual
            if atual > anterior:
                with reactive.isolate():
                    _abrir(posicao)

    @render.ui
    def dados_do_documento():
        linha = _escolhidas.get(escolhido())
        if not linha:
            return ui.p(
                "Escolha um título na lista acima para justificar o juro dele.",
                class_="text-muted small px-2 pb-2",
            )
        campos = [
            ("Documento", _texto(linha.get("num_doc"))),
            ("Nome", _texto(linha.get("razao_social"))),
            ("Valor Original", formatar_reais(linha.get("valor_original") or 0)),
            ("Data de Vencimento", _data(linha.get("data_vencimento"))),
            ("Data de Baixa", _data(linha.get("data_pagamento"))),
            ("Dispensa de Juros", formatar_reais(linha.get("juros") or 0)),
            ("Usuário", _usuario()),
            ("Revenda", _texto(linha.get("REVENDA"))),
        ]
        return ui.div(
            *[
                ui.div(
                    ui.tags.strong(f"{rotulo}: "),
                    ui.span(valor),
                    class_="ppf-juros-dado",
                )
                for rotulo, valor in campos
            ],
            class_="ppf-juros-dados px-2 pb-2",
        )

    @render.ui
    def contador():
        n = len(input.justificativa() or "")
        return ui.div(
            f"{n}/{LIMITE_TEXTO}",
            class_="ppf-juros-contador" + (" ppf-juros-cheio" if n > LIMITE_TEXTO else ""),
        )

    @reactive.effect
    @reactive.event(input.enviar)
    def _enviar():
        texto = (input.justificativa() or "").strip()
        linha = _escolhidas.get(escolhido())
        if not linha:
            ui.modal_show(
                modal_aviso(
                    "Escolha um título na lista antes de enviar.",
                    titulo="Juros",
                ),
                session=session,
            )
            return
        if not pode(_usuario(), "justificar_juros"):
            ui.modal_show(
                modal_aviso(
                    "Você não tem permissão. " + quem_libera("justificar_juros"),
                    titulo="Sem permissão",
                    tipo="error",
                ),
                session=session,
            )
            return
        if not texto:
            ui.modal_show(
                modal_aviso(
                    "Escreva a justificativa antes de enviar.",
                    titulo="Juros",
                ),
                session=session,
            )
            return
        if len(texto) > LIMITE_TEXTO:
            ui.modal_show(
                modal_aviso(
                    f"A justificativa tem {len(texto)} caracteres e o limite é {LIMITE_TEXTO}.",
                    titulo="Juros",
                ),
                session=session,
            )
            return
        try:
            manual_arquivo.justificar_juros(
                {
                    "revenda": _texto(linha.get("REVENDA")),
                    "documento": _texto(linha.get("num_doc")),
                    "nome": _texto(linha.get("razao_social")),
                    "valor_original": float(linha.get("valor_original") or 0),
                    "dt_vencto": linha.get("data_vencimento"),
                    "dt_baixa": linha.get("data_pagamento"),
                    "dispensa_juros": float(linha.get("juros") or 0),
                    "justificativa": texto,
                    "usuario": _usuario(),
                    "data_hora": datetime.now(),
                }
            )
        except Exception as erro:
            ui.modal_show(
                modal_aviso(
                    f"Falhou ao gravar: {str(erro)[:200]}",
                    titulo="Juros",
                    tipo="error",
                ),
                session=session,
            )
            return
        versao.set(versao() + 1)
        ui.modal_show(
            modal_aviso(
                "Justificativa registrada com sucesso!",
                titulo="Juros",
                tipo="success",
            ),
            session=session,
        )


def pag_juros_ui(revenda: str | None = None):
    return juros_ui("juros", revenda)


def pag_juros_server(revenda_atual=None):
    return juros_server("juros", revenda_atual=revenda_atual)
