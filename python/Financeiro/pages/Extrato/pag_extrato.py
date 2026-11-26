from __future__ import annotations

import io
import json
from datetime import date, datetime, timedelta

import pandas as pd
import polars as pl
from faicons import icon_svg
from loguru import logger
from shiny import module, reactive, render, ui
from shiny.types import SafeException

from core import revendas as cadastro_revendas
from core import trava_caixa
from core.auth import identificar_usuario, usuario_pode_ver_pagina
from core.cartoes_banco import formatar_reais, ler_reais
from core.compat import para_pandas
from core.cores import VALOR_NEGATIVO
from core.secao import ICONE_EXTRATO, com_placeholder, titulo_secao
from core.tabela_paginada import TabelaPaginada
from pages.PPF.Dados import dados_ppf as dp

from .Dados import baixa_extrato_control as bx
from .Dados import extrato_control as ec
from .Dados import sincronia_extrato as sx

FILTRO_COM_BUSCA = {
    "placeholder": "Todos",
    "plugins": ["clear_button", "restore_on_backspace"],
    "dropdownParent": "body",
    "dropdownClass": "selectize-dropdown ppf-filtro-dropdown",
}
SEM_TODOS = {**FILTRO_COM_BUSCA, "plugins": ["restore_on_backspace"]}

VALOR_NAVSET = "ppf_xtr"
ALTURA_TABELA = "58vh"
SITUACOES = {"": "Todas", "baixados": "Baixados", "abertos": "Não baixados"}
LADOS = {"": "Todos", "debito": "Débito", "credito": "Crédito"}
COLUNAS = ["Banco", "Data", "Histórico", "HP", "Nº Doc.", "Débito", "Crédito", "Usuário", "Situação"]
SEGUNDOS_ENTRE_CONFERENCIAS = 5
SEGUNDOS_AVISO_FILTRANDO = 1.5


def _numero(valor) -> str:
    if valor is None:
        return ""
    texto = f"{abs(float(valor)):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"-R$ {texto}" if float(valor) < 0 else f"R$ {texto}"


def _situacao(lmo: str) -> str:
    if not lmo:
        return ""
    dia = ec.data_da_baixa(lmo)
    return f"{dia:%d/%m/%Y}" if dia else str(lmo)


def lado_da_linha(x: dict) -> str:
    return "credito" if x.get("credito") is not None else "debito"


def linha_editavel(x: dict, preencher_credito: bool, preencher_debito: bool) -> bool:
    lado = lado_da_linha(x)
    return (lado == "credito" and preencher_credito) or (lado == "debito" and preencher_debito)


SEM_SITUACAO = "O ERP desta revenda não tem o campo Situação: não há o que preencher."


def revenda_tem_situacao(info: dict | None) -> bool:
    return (info or {}).get("tem_situacao", True) is not False


def chave_da_linha(x: dict) -> tuple:
    return (x["banco"], x["dtl"], x["doc_control"], x["valor_control"])


def situacao_digitada(texto) -> str | None:
    codigo = bx.data_baixa(str(texto or "").strip())
    return None if codigo is None else f"{codigo[:2]}/{codigo[2:4]}/{codigo[4:]}"


def agrupar_situacoes(pendentes: dict) -> list[tuple[str | None, list[list]]]:
    grupos: dict = {}
    for chave, data in pendentes.items():
        grupos.setdefault(data, []).append(list(chave))
    return sorted(grupos.items(), key=lambda g: (g[0] is None, g[0] or ""))


FILTROS_DE_LISTA = {"banco": "banco", "usuario": "usuario", "hp": "hp"}


def aplicar_filtros(base: pl.DataFrame, f: dict, sem: str | None = None) -> pl.DataFrame:
    if base.is_empty():
        return base
    filtro = pl.lit(True)
    if f.get("periodo"):
        de, ate = f["periodo"]
        filtro &= pl.col("data").is_between(de, ate)
    for campo in ("banco", "hp"):
        if f.get(campo) and sem != campo and str(f[campo]).lstrip("-").isdigit():
            filtro &= pl.col(campo) == int(f[campo])
    if f.get("usuario") and sem != "usuario":
        filtro &= pl.col("usuario") == f["usuario"]
    if f.get("situacao"):
        baixada = pl.col("lmo") != ""
        filtro &= baixada if f["situacao"] == "baixados" else ~baixada
    if f.get("lado"):
        filtro &= pl.col(f["lado"]).is_not_null()
    for campo in ("historico", "documento"):
        if f.get(campo):
            filtro &= pl.col(campo).fill_null("").str.to_uppercase().str.contains(f[campo].upper(), literal=True)
    if f.get("valor") is not None:
        filtro &= ((pl.col("debito").fill_null(-1.0) - f["valor"]).abs() < 0.005) | (
            (pl.col("credito").fill_null(-1.0) - f["valor"]).abs() < 0.005
        )
    return base.filter(filtro)


def opcoes_que_existem(base: pl.DataFrame, f: dict, todas: dict[str, dict]) -> dict[str, dict]:
    if base.is_empty():
        return todas
    fora = {}
    for campo, escolhas in todas.items():
        coluna = FILTROS_DE_LISTA[campo]
        existem = {str(v) for v in aplicar_filtros(base, f, sem=campo)[coluna].drop_nulls().unique().to_list()}
        atual = str(f.get(campo) or "")
        fora[campo] = {k: v for k, v in escolhas.items() if k == "" or k in existem or k == atual}
    return fora


def _linhas(fatia: pl.DataFrame, pendentes: dict | None = None) -> pd.DataFrame:
    pendentes = pendentes or {}
    linhas = []
    for x in fatia.iter_rows(named=True):
        chave = chave_da_linha(x)
        situacao = (pendentes[chave] or "") if chave in pendentes else _situacao(x["lmo"])
        linhas.append(
            [
                x["banco"],
                f"{x['data']:%d/%m/%Y}" if x["data"] else "",
                x["historico"],
                "" if x["hp"] is None else str(x["hp"]),
                x["documento"],
                _numero(x["debito"]),
                _numero(x["credito"]),
                x["usuario"],
                situacao,
            ]
        )
    return pd.DataFrame(linhas, columns=COLUNAS)


def _prazo() -> str:
    segundos = int(sx.TIMEOUT_SEGUNDOS)
    return f"{segundos // 60} minutos" if segundos >= 120 else f"{segundos} segundos"


def conteudo_consultando(revenda: str) -> ui.Tag:
    return ui.div(
        ui.div(ui.span("Consultando", class_="visually-hidden"), class_="spinner-border xtr-spinner", role="status"),
        ui.div("Consultando o ERP", class_="xtr-modal-titulo"),
        ui.div(
            f"Buscando o movimento dos bancos da {revenda}. Costuma levar alguns segundos; "
            f"se o ERP não responder em {_prazo()}, a consulta é cancelada.",
            class_="xtr-modal-texto",
        ),
        class_="xtr-modal",
    )


def conteudo_filtrando(revenda: str, info: dict | None) -> ui.Tag:
    minutos = int(sx.INTERVALO_MINIMO.total_seconds() // 60)
    if info:
        consultado = datetime.fromisoformat(info["consultado_em"])
        texto = (
            f"Usando a consulta ao ERP das {consultado:%H:%M}, de menos de {minutos} minutos. "
            f"Para consultar de novo agora, use o Atualizar do alto da tela."
        )
    else:
        texto = f"Usando a última consulta ao ERP da {revenda}."
    return ui.div(
        ui.div(ui.span("Filtrando", class_="visually-hidden"), class_="spinner-border xtr-spinner", role="status"),
        ui.div("Filtrando o extrato", class_="xtr-modal-titulo"),
        ui.div(texto, class_="xtr-modal-texto"),
        class_="xtr-modal",
    )


def conteudo_falha(revenda: str, erro: str, info: dict | None, falhou_as: datetime | None = None) -> ui.Tag:
    explicacao = sx.explicar_erro(erro)
    texto, conselho = explicacao.texto, explicacao.conselho
    if falhou_as:
        texto = f"A última consulta, às {falhou_as:%H:%M}, falhou. {texto}"
        conselho = (
            f"Para não sobrecarregar o ERP, uma nova consulta fica liberada às "
            f"{falhou_as + sx.ESPERA_DEPOIS_DE_ERRO:%H:%M}. Tente novamente depois disso."
        )
    if info:
        consultado = datetime.fromisoformat(info["consultado_em"])
        copia = f"A tabela mostra a última consulta que deu certo, de {consultado:%d/%m/%Y} às {consultado:%H:%M}."
    else:
        copia = "Ainda não há uma consulta desta revenda para mostrar na tabela."
    return ui.div(
        ui.div(icon_svg("triangle-exclamation", height="2.2rem", a11y="deco"), class_="xtr-falha-icone"),
        ui.div(f"Não foi possível consultar o ERP da {revenda}", class_="xtr-modal-titulo"),
        ui.div(texto, class_="xtr-modal-texto"),
        ui.div(conselho, class_="xtr-modal-texto"),
        ui.div(copia, class_="xtr-modal-copia"),
        ui.div(f"Detalhe: {erro}", class_="xtr-modal-motivo"),
        ui.div(ui.modal_button("Fechar"), class_="xtr-modal-acoes"),
        class_="xtr-modal",
    )


@module.ui
def extrato_ui(revenda: str | None = None):
    hoje = date.today()
    return ui.div(
        ui.card(
            ui.card_header(
                ui.div(
                    titulo_secao(
                        "Extratos", icone=ICONE_EXTRATO, extras=[ui.output_ui("situacao", class_="xtr-situacao")]
                    ),
                    ui.download_button(
                        "baixar",
                        None,
                        icon=icon_svg("file-excel"),
                        title="Exportar para Excel",
                        class_="btn-sm btn-success",
                    ),
                    class_="d-flex justify-content-between align-items-center w-100",
                )
            ),
            ui.div(
                ui.div(
                    ui.div(
                        ui.tags.strong("Período", class_="ppf-titulo-data"),
                        ui.div(
                            ui.span("De:", class_="ppf-rotulo-data"),
                            com_placeholder(
                                ui.input_date_range(
                                    "periodo",
                                    None,
                                    start=hoje.replace(day=1),
                                    end=hoje,
                                    min=hoje - timedelta(days=ec.DIAS_MAXIMOS_ATRAS),
                                    format="dd/mm/yyyy",
                                    language="pt-BR",
                                    separator="Até:",
                                    weekstart=0,
                                ),
                                "dd/mm/aaaa",
                            ),
                            class_="ppf-linha-data",
                        ),
                        class_="ppf-grupo-filtros ppf-grupo-data",
                    ),
                    ui.div(
                        ui.output_ui("filtro_revenda"),
                        ui.div(
                            ui.input_selectize("banco", "Banco:", {"": "Todos"}, options=FILTRO_COM_BUSCA),
                            class_="ppf-filtro ppf-filtro-inline",
                        ),
                        ui.div(
                            ui.input_selectize("usuario", "Usuário:", {"": "Todos"}, options=FILTRO_COM_BUSCA),
                            class_="ppf-filtro ppf-filtro-inline",
                        ),
                        class_="ppf-grupo-filtros ppf-grupo-selects",
                    ),
                    ui.div(
                        ui.input_checkbox("preencher_credito", "Preencher Crédito"),
                        ui.input_checkbox("preencher_debito", "Preencher Débito"),
                        class_="ppf-grupo-filtros xtr-grupo-preencher",
                    ),
                    ui.div(
                        ui.div(
                            ui.input_selectize(
                                "situacao_baixa",
                                "Situação:",
                                SITUACOES,
                                options={**FILTRO_COM_BUSCA, "placeholder": SITUACOES[""]},
                            ),
                            class_="ppf-filtro ppf-filtro-inline",
                        ),
                        ui.div(
                            ui.input_selectize("lado", "Coluna:", LADOS, options=FILTRO_COM_BUSCA),
                            class_="ppf-filtro ppf-filtro-inline",
                        ),
                        ui.div(
                            ui.input_selectize("hp", "HP:", {"": "Todos"}, options=FILTRO_COM_BUSCA),
                            class_="ppf-filtro ppf-filtro-inline",
                        ),
                        class_="ppf-grupo-filtros ppf-grupo-selects",
                    ),
                    ui.div(
                        ui.div(
                            ui.input_text("historico", "Histórico:", placeholder="contém"),
                            class_="ppf-filtro ppf-filtro-inline xtr-filtro-texto",
                        ),
                        ui.div(
                            ui.input_text("documento", "Nº Doc.:", placeholder="contém"),
                            class_="ppf-filtro ppf-filtro-inline xtr-filtro-texto",
                        ),
                        ui.div(
                            ui.input_text("valor", "Valor:", placeholder="0,00"),
                            class_="ppf-filtro ppf-filtro-inline xtr-filtro-texto campo-reais-cru",
                        ),
                        class_="ppf-grupo-filtros ppf-grupo-selects",
                    ),
                    class_="xtr-filtros",
                ),
                ui.div(
                    ui.input_action_button(
                        "gerar",
                        "Gerar dados",
                        icon=icon_svg("magnifying-glass", a11y="deco"),
                        class_="ppf-btn-limpar xtr-btn-gerar",
                    ),
                    ui.input_action_button(
                        "limpar",
                        "Limpar dados",
                        icon=icon_svg("eraser", a11y="deco"),
                        class_="ppf-btn-limpar xtr-btn-gerar",
                    ),
                    class_="ppf-grupo-limpar",
                ),
                class_="ppf-faixa-filtros xtr-faixa",
                id="faixa_extrato",
            ),
            ui.div(
                ui.output_ui("barra_situacao", class_="xtr-barra-situacao"),
                ui.div(
                    ui.div(
                        ui.span("Total Débito", class_="ppf-cartao-total-titulo"),
                        ui.output_text("total_debito", inline=True),
                        class_="ppf-cartao-total xtr-total-debito",
                    ),
                    ui.div(
                        ui.span("Total Crédito", class_="ppf-cartao-total-titulo"),
                        ui.output_text("total_credito", inline=True),
                        class_="ppf-cartao-total xtr-total-credito",
                    ),
                    class_="xtr-totais",
                ),
                class_="xtr-linha-baixa",
            ),
            ui.div(ui.output_data_frame("grade"), ui.output_ui("paginacao"), class_="xtr-grade"),
        ),
        class_="fin-modulo",
    )


@module.server
def extrato_server(input, output, session, revenda_atual=None, aba_atual=None, atualizar=None, estado=None):
    def _revenda_url():
        return revenda_atual() if callable(revenda_atual) else revenda_atual

    def _aberta() -> bool:
        return aba_atual is not None and aba_atual() == VALOR_NAVSET

    _quem: dict = {}

    def _usuario() -> str:
        if "usuario" not in _quem:
            try:
                raiz = session.root_scope() if hasattr(session, "root_scope") else session
                _quem["usuario"] = (identificar_usuario(raiz.http_conn)[0] or "").strip()
            except Exception:
                _quem["usuario"] = ""
        return _quem["usuario"]

    def _pode() -> bool:
        return usuario_pode_ver_pagina(_usuario(), VALOR_NAVSET)

    def _barrado_pelo_caixa() -> bool:
        return trava_caixa.barrar(_usuario())

    @reactive.calc
    def _opcoes_revenda() -> list[str]:
        alvos = dp.revendas_da_url(_revenda_url())
        nomes = (
            [cadastro_revendas.nome_oficial(a) for a in alvos]
            if alvos
            else [r.nome for r in cadastro_revendas.REVENDAS]
        )
        return [n for n in dict.fromkeys(nomes) if n]

    @render.ui
    def filtro_revenda():
        opcoes = _opcoes_revenda()
        if len(opcoes) <= 1:
            return None
        return ui.div(
            ui.input_selectize("revenda", "Revenda:", opcoes, options=SEM_TODOS), class_="ppf-filtro ppf-filtro-inline"
        )

    @reactive.calc
    def _revenda() -> str | None:
        opcoes = _opcoes_revenda()
        if len(opcoes) > 1 and "revenda" in input and input.revenda() in opcoes:
            return input.revenda()
        return opcoes[0] if opcoes else None

    def _cnpj(nome: str | None) -> str | None:
        cadastro = cadastro_revendas.por_nome(nome)
        return cadastro.cnpj if cadastro else None

    def _erro_da(tarefa) -> str | None:
        if tarefa.status() != "error":
            return None
        try:
            tarefa.result()
        except Exception as erro:
            return str(erro)
        return None

    @reactive.extended_task
    async def tarefa_sincronia(revenda, cnpj, desde, usuario):
        return await sx.sincronizar(revenda, cnpj, date.fromisoformat(desde), usuario=usuario)

    @reactive.extended_task
    async def tarefa_catalogo(revenda, cnpj, usuario):
        try:
            return await sx.consultar("catalogo", revenda, cnpj, usuario=usuario)
        except sx.ConsultaCedida:
            return None

    _versao = reactive.value(None)

    @reactive.effect
    def _conferir_cache():
        if not _aberta():
            return
        reactive.invalidate_later(SEGUNDOS_ENTRE_CONFERENCIAS)
        tarefa_sincronia.status()
        tarefa_catalogo.status()
        revenda = _revenda()
        cnpj = _cnpj(revenda) if revenda else None
        nova = (revenda, ec.momento_cache(cnpj), ec.momento_catalogo(cnpj)) if revenda else None
        with reactive.isolate():
            if nova != _versao():
                _versao.set(nova)

    @reactive.calc
    def _movimento() -> tuple[pl.DataFrame, dict | None]:
        versao = _versao()
        return ec.ler_movimento(_cnpj(versao[0])) if versao else (pl.DataFrame(), None)

    @reactive.calc
    def _tem_situacao() -> bool:
        return revenda_tem_situacao(_movimento()[1])

    @reactive.calc
    def _catalogo() -> dict | None:
        versao = _versao()
        return ec.ler_catalogo(_cnpj(versao[0])) if versao else None

    @reactive.effect
    def _catalogo_ao_abrir():
        if not _aberta():
            return
        reactive.invalidate_later(30 * 60)
        revenda = _revenda()
        with reactive.isolate():
            try:
                if (
                    revenda
                    and _pode()
                    and tarefa_catalogo.status() != "running"
                    and sx.precisa_catalogo(_cnpj(revenda))
                ):
                    tarefa_catalogo.invoke(revenda, _cnpj(revenda), _usuario())
            except Exception as exc:
                logger.warning(f"Extrato: catalogo dos filtros nao pedido -- {exc}")

    _opcoes_enviadas: dict = {}

    def _encher(campo: str, escolhas: dict) -> None:
        if _opcoes_enviadas.get(campo) == escolhas:
            return
        if campo not in input:
            return
        with reactive.isolate():
            atual = input[campo]()
        ui.update_selectize(campo, choices=escolhas, selected=atual if atual in escolhas else "")
        _opcoes_enviadas[campo] = escolhas

    @reactive.effect
    def _preencher_opcoes():
        try:
            base, info = _movimento()
            todas = ec.opcoes_dos_filtros(_catalogo(), base, info)
            for campo, escolhas in opcoes_que_existem(base, _filtros(), todas).items():
                _encher(campo, escolhas)
        except Exception as exc:
            logger.warning(f"Extrato: opcoes dos filtros nao montadas -- {exc}")

    def _campo(nome: str):
        return input[nome]() if nome in input else None

    def _periodo() -> tuple[date, date] | None:
        periodo = _campo("periodo")
        if periodo and len(periodo) == 2 and all(isinstance(d, date) for d in periodo):
            return periodo[0], periodo[1]
        return None

    @reactive.calc
    def _filtros() -> dict:
        valor = ler_reais((_campo("valor") or "").strip())
        return {
            "periodo": _periodo(),
            "banco": _campo("banco") or "",
            "usuario": _campo("usuario") or "",
            "situacao": _campo("situacao_baixa") or "",
            "lado": _campo("lado") or "",
            "hp": _campo("hp") or "",
            "historico": (_campo("historico") or "").strip(),
            "documento": (_campo("documento") or "").strip(),
            "valor": abs(valor) if valor is not None else None,
        }

    _gerado = reactive.value(None)
    _consulta: dict = {}

    _aviso = reactive.value(None)

    def _abrir_aviso(*estado) -> None:
        _aviso.set(estado)
        ui.modal_show(ui.modal(ui.output_ui("aviso_consulta"), title=None, footer=None, easy_close=False, size="m"))

    @render.ui
    def aviso_consulta():
        estado = _aviso()
        if not estado:
            return None
        if estado[0] == "consultando":
            return conteudo_consultando(estado[1])
        if estado[0] == "filtrando":
            return conteudo_filtrando(*estado[1:])
        return conteudo_falha(*estado[1:])

    _fechar_filtrando_em = reactive.value(None)

    @reactive.effect
    def _fechar_filtrando():
        quando = _fechar_filtrando_em()
        if quando is None:
            return
        falta = (quando - datetime.now()).total_seconds()
        if falta > 0:
            reactive.invalidate_later(falta)
            return
        _fechar_filtrando_em.set(None)
        with reactive.isolate():
            if (_aviso() or ("",))[0] == "filtrando":
                ui.modal_remove()
                _aviso.set(None)

    def _sincronizar(forcar: bool, desde: date | None = None) -> str | None:
        try:
            if not _aberta() or not _pode() or tarefa_sincronia.status() == "running":
                return None
            revenda = _revenda()
            if not revenda:
                return None
            cnpj = _cnpj(revenda)
            desde = min(desde or date.today(), ec.janela_padrao())
            if forcar or sx.sincronizando(cnpj) or sx.precisa_sincronizar(cnpj, desde):
                _consulta.update(revenda=revenda, cnpj=cnpj)
                tarefa_sincronia.invoke(revenda, cnpj, desde.isoformat(), _usuario())
                _abrir_aviso("consultando", revenda)
                return "consulta"
            if (erro := sx.erro_recente(cnpj)) and not sx.cache_basta(cnpj, desde):
                _abrir_aviso("falha", revenda, erro[1], ec.ler_info(cnpj), erro[0])
                return "falha"
            return "copia"
        except Exception as exc:
            logger.warning(f"Extrato: consulta ao ERP nao disparada -- {exc}")
            return None

    @reactive.effect
    def _fim_da_consulta():
        if tarefa_sincronia.status() not in ("success", "error"):
            return
        with reactive.isolate():
            erro = _erro_da(tarefa_sincronia)
            if erro is None:
                ui.modal_remove()
                return
            revenda = _consulta.get("revenda") or _revenda() or ""
            _aviso.set(("falha", revenda, erro, ec.ler_info(_consulta.get("cnpj") or _cnpj(revenda)), None))

    @reactive.effect
    @reactive.event(input.gerar)
    def _gerar():
        periodo = _periodo()
        if not periodo or periodo[0] > periodo[1]:
            ui.modal_show(
                ui.modal(
                    "Escolha o período (De e Até) antes de gerar.",
                    title="Extratos",
                    easy_close=True,
                    footer=ui.modal_button("Fechar"),
                )
            )
            return
        valor_texto = (input.valor() or "").strip()
        if valor_texto and ler_reais(valor_texto) is None:
            ui.modal_show(
                ui.modal(
                    "O Valor não é um número (ex.: 1.234,56).",
                    title="Extratos",
                    easy_close=True,
                    footer=ui.modal_button("Fechar"),
                )
            )
            return
        _gerado.set({"revenda": _revenda(), "periodo": periodo})
        if _sincronizar(False, periodo[0]) == "copia":
            revenda = _revenda()
            _abrir_aviso("filtrando", revenda, ec.ler_info(_cnpj(revenda)))
            _fechar_filtrando_em.set(datetime.now() + timedelta(seconds=SEGUNDOS_AVISO_FILTRANDO))

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar():
        hoje = date.today()
        ui.update_date_range("periodo", start=hoje.replace(day=1), end=hoje)
        for campo in ("banco", "usuario", "situacao_baixa", "lado", "hp"):
            ui.update_selectize(campo, selected="")
        for campo in ("historico", "documento", "valor"):
            ui.update_text(campo, value="")
        for campo in ("preencher_credito", "preencher_debito"):
            ui.update_checkbox(campo, value=False)
        _descartar(redesenhar=False)
        _gerado.set(None)

    if atualizar is not None:

        @reactive.effect
        @reactive.event(atualizar, ignore_init=True)
        def _consultar_pelo_topo():
            periodo = _periodo() if _gerado() else None
            _sincronizar(True, periodo[0] if periodo else None)

    if estado is not None:

        @reactive.effect
        def _publicar_estado():
            _base, info = _movimento()
            consultado = datetime.fromisoformat(info["consultado_em"]) if info else None
            estado.set(
                {
                    "rodando": tarefa_sincronia.status() == "running",
                    "erro": _erro_da(tarefa_sincronia),
                    "consultado_em": consultado,
                }
            )

    def _outra_revenda_na_tela() -> bool:
        f = _gerado()
        return bool(f) and f["revenda"] != _revenda()

    @reactive.calc
    def _filtrada() -> pl.DataFrame:
        base, _info = _movimento()
        if base.is_empty() or not _gerado() or _outra_revenda_na_tela():
            return base.clear()
        if tarefa_sincronia.status() == "running":
            return base.clear()
        f = _filtros()
        if f["periodo"] is None:
            f = {**f, "periodo": _gerado()["periodo"]}
        return aplicar_filtros(base, f)

    @render.ui
    def situacao():
        if tarefa_sincronia.status() == "running":
            return ui.span("consultando o ERP...")
        erro = _erro_da(tarefa_sincronia)
        if erro:
            return ui.span(
                f"Não consegui consultar o ERP ({sx.explicar_erro(erro).curto}). Tente novamente mais tarde.",
                class_="xtr-erro",
            )
        _base, info = _movimento()
        if not _gerado():
            return None
        if _outra_revenda_na_tela():
            return ui.span(f"clique em Gerar dados para ver a {_revenda()}", class_="xtr-erro")
        base = _filtrada()
        texto = f"{base.height:,} linha(s)".replace(",", ".")
        if not revenda_tem_situacao(info):
            texto += " · sem o campo Situação no ERP desta revenda"
        avisos = []
        valor_texto = (_campo("valor") or "").strip()
        if valor_texto and ler_reais(valor_texto) is None:
            avisos.append(" · o Valor não é um número e ficou de fora")
        periodo = _periodo() or _gerado()["periodo"]
        if info and periodo[0] < date.fromisoformat(info["desde"]):
            avisos.append(
                f" · o ERP foi consultado a partir de {date.fromisoformat(info['desde']):%d/%m/%Y}"
                f" (Gerar dados busca o resto)"
            )
        return ui.span(texto, *[ui.span(a, class_="xtr-erro") for a in avisos])

    paginador = TabelaPaginada("extrato", input, session)

    @reactive.effect
    @reactive.event(_gerado, _filtros)
    def _voltar_a_primeira_pagina():
        paginador.reiniciar()

    @reactive.calc
    def _pagina() -> pl.DataFrame:
        base = _filtrada()
        inicio, fim = paginador.janela(base.height)
        return base.slice(inicio, fim - inicio)

    _pendentes: dict = {}
    _contagem = reactive.value(0)
    _redesenho = reactive.value(0)
    COLUNA_SITUACAO = COLUNAS.index("Situação")

    def _avisar_pendentes() -> None:
        with reactive.isolate():
            _contagem.set(_contagem() + 1)

    def _descartar(redesenhar: bool = True) -> None:
        _pendentes.clear()
        _avisar_pendentes()
        if redesenhar:
            with reactive.isolate():
                _redesenho.set(_redesenho() + 1)

    @reactive.effect
    @reactive.event(_revenda)
    def _outra_revenda():
        _descartar(redesenhar=False)

    def _preencher() -> tuple[bool, bool]:
        return bool(input.preencher_credito()), bool(input.preencher_debito())

    @render.data_frame
    def grade():
        _redesenho()
        pagina = _pagina()
        credito, debito_marcado = _preencher()
        debito = COLUNAS.index("Débito")
        estilos = [
            {"cols": [debito, debito + 1], "style": {"text-align": "right"}},
            {"cols": [debito], "style": {"color": VALOR_NEGATIVO}},
        ]
        editavel = _pode() and _tem_situacao() and (credito or debito_marcado)
        if editavel:
            linhas = [
                i for i, x in enumerate(pagina.iter_rows(named=True)) if linha_editavel(x, credito, debito_marcado)
            ]
            if linhas:
                estilos.append({"rows": linhas, "cols": [COLUNA_SITUACAO], "class": "xtr-cel-preencher"})
        return render.DataTable(
            _linhas(pagina, _pendentes),
            styles=estilos,
            width="100%",
            height=ALTURA_TABELA,
            summary=False,
            filters=False,
            selection_mode="none",
            editable=editavel,
        )

    @grade.set_patch_fn
    def _preencher_situacao(*, patch):
        if not _pode():
            raise SafeException("Sem permissão para alterar a Situação.")
        if _barrado_pelo_caixa():
            raise SafeException(f"{trava_caixa.TITULO}.")
        if patch["column_index"] != COLUNA_SITUACAO:
            raise SafeException("Só a coluna Situação se preenche.")
        with reactive.isolate():
            if not _tem_situacao():
                raise SafeException(SEM_SITUACAO)
            pagina = _pagina()
            credito, debito = _preencher()
        if patch["row_index"] >= pagina.height:
            raise SafeException("A linha mudou; gere os dados de novo.")
        x = pagina.row(patch["row_index"], named=True)
        if not linha_editavel(x, credito, debito):
            raise SafeException("Marque o Preencher do lado desta linha (Crédito ou Débito).")
        try:
            nova = situacao_digitada(patch["value"])
        except bx.Recusa:
            raise SafeException("Digite a data da Situação (dd/mm/aaaa), ou apague para limpar.")
        chave = chave_da_linha(x)
        if nova == (_situacao(x["lmo"]) or None):
            _pendentes.pop(chave, None)
        else:
            _pendentes[chave] = nova
        _avisar_pendentes()
        return nova or ""

    @reactive.extended_task
    async def tarefa_situacao(revenda, cnpj, grupos, usuario, gravar):
        resultados = []
        for data, linhas in grupos:
            resultado = await sx.consultar(
                "baixar",
                revenda,
                cnpj,
                json.dumps(linhas),
                data or "-",
                usuario or "",
                "1" if gravar else "0",
                usuario=usuario,
            )
            resultados.append((data, resultado))
        return resultados

    @render.ui
    def barra_situacao():
        _contagem()
        if not _pode():
            return None
        if not _tem_situacao() and any(_preencher()):
            return ui.div(ui.span(SEM_SITUACAO, class_="xtr-situacao-texto xtr-erro"), class_="xtr-situacao-pendente")
        if not _pendentes:
            return None
        rodando = tarefa_situacao.status() == "running"
        preenchidas = sum(1 for d in _pendentes.values() if d)
        limpas = len(_pendentes) - preenchidas
        partes = ([f"{preenchidas} com data"] if preenchidas else []) + ([f"{limpas} limpa(s)"] if limpas else [])
        return ui.div(
            ui.span(
                f"Situação alterada em {len(_pendentes)} linha(s): {', '.join(partes)}.", class_="xtr-situacao-texto"
            ),
            ui.input_action_button(
                "ok_situacao",
                "Gravando..." if rodando else "Ok",
                class_="xtr-btn-ok",
                disabled=rodando,
                title="Grava a Situação no ERP",
            ),
            ui.input_action_button("descartar_situacao", "Descartar", class_="xtr-btn-descartar", disabled=rodando),
            class_="xtr-situacao-pendente",
        )

    @reactive.effect
    @reactive.event(input.descartar_situacao)
    def _ao_descartar():
        _descartar()

    _pedido: dict = {}

    @reactive.effect
    @reactive.event(input.ok_situacao)
    def _ao_ok():
        if not _pode() or not _pendentes or not _tem_situacao() or tarefa_situacao.status() == "running":
            return
        if _barrado_pelo_caixa():
            return
        simular = bool(bx.antes_de_gravar())
        _pedido.clear()
        _pedido.update({"revenda": _revenda(), "grupos": agrupar_situacoes(_pendentes), "gravar": not simular})
        itens = [
            ui.tags.li(f"{len(linhas)} linha(s): " + (f"Situação {data}" if data else "limpar a Situação"))
            for data, linhas in _pedido["grupos"]
        ]
        ui.modal_show(
            ui.modal(
                ui.p(f"Gravar a Situação no ERP, {_revenda()}:"),
                ui.tags.ul(*itens),
                ui.p(
                    "SIMULAÇÃO: nada vai para o ERP enquanto a gravação não for liberada "
                    "(liberação da gravação). Mostra o que seria gravado."
                    if simular
                    else "Grava no ERP, com registro de tudo.",
                    class_="xtr-erro" if simular else None,
                ),
                title="Situação no ERP",
                easy_close=True,
                footer=ui.TagList(
                    ui.modal_button("Cancelar"),
                    ui.input_action_button(
                        "confirmar_situacao", "Simular" if simular else "Confirmar", class_="btn-sm xtr-btn-ok"
                    ),
                ),
            )
        )

    @reactive.effect
    @reactive.event(input.confirmar_situacao)
    def _confirmar():
        ui.modal_remove()
        if not _pedido or not _pode() or tarefa_situacao.status() == "running":
            return
        if _barrado_pelo_caixa():
            _pedido.clear()
            return
        p = dict(_pedido)
        _pedido.clear()
        tarefa_situacao.invoke(p["revenda"], _cnpj(p["revenda"]), p["grupos"], _usuario(), p["gravar"])
        _avisar_pendentes()

    @reactive.effect
    def _resultado_da_situacao():
        status = tarefa_situacao.status()
        if status not in ("success", "error"):
            return
        with reactive.isolate():
            erro = _erro_da(tarefa_situacao)
            if erro:
                _avisar_pendentes()
                ui.modal_show(
                    ui.modal(
                        f"A Situação não foi gravada: {erro}",
                        title="Situação no ERP",
                        easy_close=True,
                        footer=ui.modal_button("Fechar"),
                    )
                )
                return
            resultados = tarefa_situacao.result()
            gravada = all(r.get("situacao") == "gravada" for _d, r in resultados)
            itens = [
                ui.tags.li(
                    f"{'Gravado' if r.get('situacao') == 'gravada' else 'Simulado'}: "
                    f"{r.get('linhas')} linha(s)" + (f", Situação {data}" if data else ", Situação limpa")
                )
                for data, r in resultados
            ]
            _descartar(redesenhar=not gravada)
            ui.modal_show(
                ui.modal(ui.tags.ul(*itens), title="Situação no ERP", easy_close=True, footer=ui.modal_button("Fechar"))
            )

    @render.ui
    def paginacao():
        if _gerado() is None:
            return ui.div("Escolha o período e os filtros e clique em Gerar dados.", class_="text-muted px-2 py-3")
        if tarefa_sincronia.status() == "running":
            return ui.div("Consultando o ERP...", class_="text-muted px-2 py-3")
        if _outra_revenda_na_tela():
            return ui.div(f"Clique em Gerar dados para ver a {_revenda()}.", class_="text-muted px-2 py-3")
        base = _filtrada()
        if base.is_empty():
            return ui.div("Nenhuma linha nos filtros escolhidos.", class_="text-muted px-2 py-3")
        return paginador.controles(base.height)

    @render.text
    def total_debito():
        base = _filtrada()
        return formatar_reais(-(base["debito"].sum() or 0.0)) if base.height else "-"

    @render.text
    def total_credito():
        base = _filtrada()
        return formatar_reais(base["credito"].sum() or 0.0) if base.height else "-"

    @render.download(filename=lambda: f"extrato_{(_revenda() or '').replace(' ', '_')}_{date.today():%Y-%m-%d}.xlsx")
    def baixar():
        base = _filtrada()
        tabela = (
            base.select(
                pl.col("banco").alias("Banco"),
                pl.col("data").alias("Data"),
                pl.col("historico").alias("Histórico"),
                pl.col("hp").alias("HP"),
                pl.col("documento").alias("Nº Doc."),
                pl.col("debito").alias("Débito"),
                pl.col("credito").alias("Crédito"),
                pl.col("usuario").alias("Usuário"),
                pl.col("lmo").str.replace_all(r"\D", "").str.to_date("%d%m%Y", strict=False).alias("Data da baixa"),
            )
            if base.height
            else pl.DataFrame(schema={c: pl.Utf8 for c in COLUNAS})
        )
        memoria = io.BytesIO()
        para_pandas(tabela).to_excel(memoria, index=False, sheet_name="Extrato")
        yield memoria.getvalue()


def pag_extrato_ui(revenda: str | None = None):
    return extrato_ui("extrato", revenda)


def pag_extrato_server(revenda_atual=None, aba_atual=None, atualizar=None, estado=None):
    return extrato_server(
        "extrato", revenda_atual=revenda_atual, aba_atual=aba_atual, atualizar=atualizar, estado=estado
    )
