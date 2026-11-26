from datetime import date, datetime

import polars as pl
from shiny import module, reactive, render, ui

from core import fabricas, gravacao, manual_arquivo
from core import revendas as cadastro_revendas
from core.auth import identificar_usuario
from core.aviso import modal_aviso
from core.cartoes_banco import icone_do_banco, ler_reais
from core.config import chave_revenda, chaves_das_revendas, pode, quem_libera, regra_do_segundo_erp
from core.config_arquivo import carregar_json
from core.revendas import nome_oficial, por_nome_em_qualquer_erp
from core.secao import ICONE_DADOS_MANUAIS, titulo_secao
from core.visibilidade import pagina_visivel

from .Dados import dados_composicao as dc
from .Dados import dados_ppf as d

VALOR_NAVSET = "ppf_man"

TIPOS_OPERACAO = {"": "Selecione", "Empréstimo": "Empréstimo", "Devolução": "Devolução"}
ENTRADA_SAIDA = {"": "Selecione", "Entrada": "Entrada", "Saída": "Saída"}

ROTULO_ROMANEIO_ADIANT = dc.rotulo_do_item("adiantamento_romaneios")
ROTULO_ROMANEIO_PEND = dc.rotulo_do_item("romaneio_pendente")
ROTULO_PIX_DIARIO = dc.rotulo_do_item("brinks_antes_16")

COLUNAS_TOTAIS = [
    "Banco",
    "Romaneio Adiant.",
    "Romaneio Pend.",
    ROTULO_PIX_DIARIO,
    "Transf. Entrada",
    "Transf. Saída",
]
COLUNAS_EMPRESTIMO = [
    "Revenda",
    "Banco",
    "Tipo de Operação",
    "Entrada/Saída",
    "Origem/Destino",
    "Valor",
    "Excluir",
]
COLUNAS_TRANSFERENCIA = [
    "Revenda",
    "Banco",
    "Revenda Destino",
    "Banco Destino",
    "Entrada/Saída",
    "Valor",
    "Excluir",
]
COLUNAS_DEMAIS = [
    "Data",
    "Hora",
    "Banco Origem",
    "Banco Destino",
    "Transferência",
    "Romaneios Pend.",
    "Romaneios Adiant.",
    ROTULO_PIX_DIARIO,
]

LINHAS_COM_LIXEIRA = 80


def _reais(valor) -> str:
    if valor is None or valor != valor or float(valor) == 0:
        return ""
    inteiro = f"{abs(float(valor)):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"{'-' if float(valor) < 0 else ''}R$ {inteiro}"


def _numero(valor) -> float:
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def _campo_fabrica(revenda: str | None) -> tuple[str, str] | None:
    fabrica = fabricas.fabrica_da_revenda(revenda) or {}
    campo = fabrica.get("campo_no_dado_manual")
    return (campo, f"Crédito {fabrica['nome']}") if campo else None


def _grupo_da_revenda(revenda: str | None) -> list[str]:
    minhas = chaves_das_revendas([revenda]) if revenda else set()
    grupos = carregar_json("parametros_financeiro").get("grupos_transferencia_matriz_filial") or {}
    for nome, membros in grupos.items():
        if str(nome).startswith("_") or not isinstance(membros, list) or len(membros) < 2:
            continue
        if any(chave_revenda(membro) in minhas for membro in membros):
            return [membro for membro in membros if chave_revenda(membro) not in minhas]
    return []


def _linha(rotulo: str, controle) -> ui.Tag:
    return ui.div(ui.tags.label(rotulo, class_="dm-rotulo"), controle, class_="dm-linha")


def _valor(id_campo: str) -> ui.Tag:
    return ui.input_text(id_campo, None, placeholder="Ex: 1234,56")


def _secao(titulo: str, *linhas) -> ui.Tag:
    return ui.div(ui.h4(titulo, class_="dm-secao-titulo"), *linhas, class_="dm-secao")


@module.ui
def dados_manuais_ui(revenda: str | None = None):
    grupo = _grupo_da_revenda(revenda)
    campo_fabrica = _campo_fabrica(revenda)
    enviar = ui.input_action_button("gravar", "Enviar", class_="dm-enviar")
    enviar.attrs["type"] = "submit"
    return ui.div(
        ui.card(
            ui.card_header(titulo_secao("Dados Manuais", icone=ICONE_DADOS_MANUAIS)),
            ui.div(
                ui.div(
                    ui.div(
                        ui.tags.label("Banco Origem", class_="dm-rotulo-topo"),
                        ui.input_select("banco", None, {"": "Selecione"}),
                        ui.output_ui("logo_banco", inline=True),
                        class_="dm-topo-linha",
                    ),
                    ui.div(
                        ui.tags.label("Data", class_="dm-rotulo-topo"),
                        ui.input_date(
                            "data_referencia",
                            None,
                            value=date.today(),
                            format="dd/mm/yyyy",
                            language="pt-BR",
                            weekstart=0,
                        ),
                        class_="dm-topo-linha",
                    ),
                    class_="dm-origem",
                ),
                ui.div(
                    ui.span("Dados Inseridos em:", class_="dm-inseridos-rotulo"),
                    ui.output_text("dados_em", inline=True),
                    class_="dm-inseridos",
                ),
                class_="dm-topo",
            ),
            ui.div(
                ui.tags.form(
                    ui.h3("Inserir Dados", class_="dm-titulo"),
                    _secao(
                        "Transferência entre bancos",
                        _linha(
                            "Destino da Transferência",
                            ui.div(
                                ui.input_select("destino_transf", None, {"": "Selecione"}),
                                ui.output_ui("logo_destino", inline=True),
                                class_="dm-destino",
                            ),
                        ),
                        _linha("Valor da Transferência", _valor("transferencia_bancos")),
                    ),
                    _secao(
                        "Empréstimos e devoluções entre revendas",
                        _linha("Tipo de Operação:", ui.input_select("tipo_emprestimo_devolucao", None, TIPOS_OPERACAO)),
                        _linha("Entrada/Saída:", ui.input_select("entrada_saida", None, ENTRADA_SAIDA)),
                        _linha(
                            "Revenda Origem/Destino:",
                            ui.input_select("revenda_origem_destino", None, {"": "Selecione"}),
                        ),
                        _linha("Valor Empréstimo/Devolução", _valor("devolucao_emprestimos")),
                    ),
                    _secao(
                        "Transferência entre Matriz e Filial",
                        _linha(
                            "Revenda Destino:",
                            ui.input_select(
                                "revenda_destino",
                                None,
                                ({"": "Selecione"} if len(grupo) != 1 else {}) | {r: r for r in grupo},
                            ),
                        ),
                        _linha("Banco Destino:", ui.input_select("banco_destino_transf", None, {"": "Selecione"})),
                        _linha(
                            "Entrada/Saída:",
                            ui.input_select("entrada_saida_transferencia_revendas", None, ENTRADA_SAIDA),
                        ),
                        _linha("Valor da Transferência:", _valor("transferencia_revendas")),
                    )
                    if grupo
                    else None,
                    _secao(
                        "Outros dados",
                        _linha("Adiantamento de Romaneios", _valor("adiantamento_romaneios")),
                        _linha(ROTULO_PIX_DIARIO, _valor("brinks_antes_16")),
                        _linha("Romaneio Pendente Encerrado", _valor("romaneio_pendente_encerrado")),
                        _linha(campo_fabrica[1], _valor(campo_fabrica[0])) if campo_fabrica else None,
                    ),
                    enviar,
                    method="dialog",
                    class_="dm-esquerda",
                ),
                ui.div(
                    ui.div(
                        ui.h4("Totais por banco Hoje", class_="dm-quadro-titulo"),
                        ui.output_ui("tabela_totais"),
                        class_="dm-quadro",
                    ),
                    ui.div(
                        ui.h4("Empréstimo/Devolução entre revendas", class_="dm-quadro-titulo"),
                        ui.output_ui("tabela_emprestimos"),
                        class_="dm-quadro",
                    ),
                    ui.div(
                        ui.h4("Transferência entre Matriz e Filial", class_="dm-quadro-titulo"),
                        ui.output_ui("tabela_transferencias"),
                        class_="dm-quadro",
                    )
                    if grupo
                    else None,
                    class_="dm-direita",
                ),
                class_="dm-colunas",
            ),
            ui.div(
                ui.h4("Demais Operações", class_="dm-quadro-titulo"),
                ui.output_ui("tabela_demais"),
                class_="dm-quadro dm-demais",
            ),
            class_="dm",
        ),
        class_="fin-modulo",
    )


@module.server
def dados_manuais_server(input, output, session, revenda_atual=None):

    def _revenda() -> str | None:
        return revenda_atual() if callable(revenda_atual) else revenda_atual

    def _campo() -> tuple[str, str] | None:
        return _campo_fabrica(_revenda())

    _CAMPOS_TEXTO = (
        "transferencia_bancos",
        "devolucao_emprestimos",
        "transferencia_revendas",
        "adiantamento_romaneios",
        "brinks_antes_16",
        "romaneio_pendente_encerrado",
        "credito_parceiro",
    )
    _CAMPOS_SELECAO = (
        "destino_transf",
        "tipo_emprestimo_devolucao",
        "entrada_saida",
        "revenda_origem_destino",
        "banco_destino_transf",
        "entrada_saida_transferencia_revendas",
    )

    lancamentos_versao = reactive.value(0)

    def _usuario() -> str:
        try:
            raiz = session.root_scope() if hasattr(session, "root_scope") else session
            quem, _script = identificar_usuario(raiz.http_conn)
            return (quem or "").strip() or "desconhecido"
        except Exception:
            return "desconhecido"

    def _avisar(texto: str, tipo: str = "message") -> None:
        ui.modal_show(modal_aviso(texto, titulo="Dados Manuais", tipo=tipo), session=session)

    def _oficial() -> str:
        bruta = _revenda() or ""
        return nome_oficial(bruta) or bruta

    @reactive.calc
    def _bancos_da_revenda() -> list[str]:
        parte = dc.da_revenda(dc.composicao(), _revenda())
        return [dc.rotulo_banco(chave, None) for chave in dc.bancos_para_lancar(parte)]

    @reactive.effect
    def _preencher_selects():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        bancos = _bancos_da_revenda()
        for campo in ("banco", "destino_transf", "banco_destino_transf"):
            with reactive.isolate():
                escolhido = input[campo]() if campo in input else ""
            opcoes = {"": "Selecione", **{b: b for b in bancos}}
            if campo == "banco" and escolhido not in bancos:
                principal = (carregar_json("parametros_financeiro").get("banco_pagamento_por_revenda") or {}).get(
                    _oficial()
                )
                escolhido = principal if principal in bancos else (bancos[0] if bancos else "")
            ui.update_select(campo, choices=opcoes, selected=escolhido if escolhido in opcoes else "")
        regra_da_revenda_do_segundo_erp = regra_do_segundo_erp(_revenda())
        if regra_da_revenda_do_segundo_erp is not None:
            nomes = list(regra_da_revenda_do_segundo_erp.get("contrapartes_emprestimo") or [])
        else:
            extras = carregar_json("parametros_financeiro").get("contrapartes_emprestimo_fora_das_revendas") or []
            nomes = list(cadastro_revendas.cnpj_por_nome_oficial()) + list(extras)
        with reactive.isolate():
            escolhido = input.revenda_origem_destino() if "revenda_origem_destino" in input else ""
        opcoes = {"": "Selecione", **{n: n for n in nomes}}
        ui.update_select("revenda_origem_destino", choices=opcoes, selected=escolhido if escolhido in opcoes else "")

    @render.ui
    def logo_banco():
        escolhido = input.banco()
        if not escolhido:
            return ui.span()
        return ui.tags.img(src=icone_do_banco(escolhido), alt=escolhido, class_="dm-logo-banco")

    @render.ui
    def logo_destino():
        escolhido = input.destino_transf()
        if not escolhido:
            return ui.span()
        return ui.tags.img(src=icone_do_banco(escolhido), alt=escolhido, class_="dm-logo-banco")

    @render.text
    def dados_em():
        dia = input.data_referencia() or date.today()
        return dia.strftime("%d-%m-%Y")

    def _texto(campo: str) -> str:
        try:
            return str(input[campo]() or "").strip()
        except Exception:
            return ""

    def _valor_digitado(campo: str) -> float | None:
        return ler_reais(_texto(campo))

    @reactive.effect
    @reactive.event(input.gravar)
    def _gravar():
        if not pode(_usuario(), "informar_dado_manual"):
            _avisar("Você não tem permissão para lançar dado manual. " + quem_libera("informar_dado_manual"), "error")
            return
        revenda_encontrada = por_nome_em_qualquer_erp(_revenda() or "")
        revenda = revenda_encontrada.nome if revenda_encontrada else None
        if not revenda:
            _avisar("O lançamento é de uma empresa: abra a revenda dele no menu e lance por lá.", "error")
            return
        hoje = date.today()
        dia = min(input.data_referencia() or hoje, hoje)
        if dia != hoje and not any(
            pode(_usuario(), chave, revenda) for chave in ("auditar_ppf", "processar_pagamento", "conselho_ppf")
        ):
            _avisar("Somente usuários com permissão podem enviar dados manuais fora da data de hoje.", "error")
            return
        banco = _texto("banco")
        if not banco:
            _avisar("Escolha o Banco Origem.", "error")
            return
        invalido = next((t for t in map(_texto, _CAMPOS_TEXTO) if t and ler_reais(t) is None), None)
        if invalido:
            _avisar(f'Valor inválido: "{invalido}". Digite só o número, como 1.234,56.', "error")
            return
        campos = {
            c: _valor_digitado(c)
            for c in (
                "transferencia_bancos",
                "adiantamento_romaneios",
                "devolucao_emprestimos",
                "brinks_antes_16",
                "romaneio_pendente_encerrado",
                "transferencia_revendas",
            )
        }
        campos.update(
            {
                c: _texto(c)
                for c in (
                    "destino_transf",
                    "banco_destino_transf",
                    "tipo_emprestimo_devolucao",
                    "entrada_saida",
                    "entrada_saida_transferencia_revendas",
                    "revenda_origem_destino",
                    "revenda_destino",
                )
            }
        )
        campo_fabrica = _campo()
        if campo_fabrica:
            campos[campo_fabrica[0]] = _valor_digitado(campo_fabrica[0])
        valores = [*gravacao.VALORES_DADO_MANUAL, *([campo_fabrica[0]] if campo_fabrica else [])]
        if all(campos.get(c) is None for c in valores):
            _avisar("Nada a lançar: preencha ao menos um valor.", "warning")
            return
        agora = datetime.combine(dia, datetime.now().time())
        try:
            fatia = gravacao.salvar_dado_manual(revenda, banco, agora, campos)
            manual_arquivo.substituir_fatia_dados_manuais(revenda, agora.date(), fatia)
        except Exception as erro:
            _avisar(f"Não deu para lançar: {str(erro)[:200]}", "error")
            return
        for campo in _CAMPOS_TEXTO:
            if campo in input:
                ui.update_text(campo, value="")
        for campo in _CAMPOS_SELECAO:
            if campo in input:
                ui.update_select(campo, selected="")
        with reactive.isolate():
            lancamentos_versao.set(lancamentos_versao() + 1)
        _avisar(
            f"Lançado em {banco}. A Composição do Diário já mostra."
            if dia == hoje
            else f"Lançado em {banco}, com a data de {dia:%d/%m/%Y}.",
            "success",
        )

    @reactive.calc
    def lancamentos() -> pl.DataFrame:
        lancamentos_versao()
        dia = input.data_referencia()
        revenda = _oficial()
        if dia is None or not revenda:
            return pl.DataFrame()
        if (revenda.strip().casefold(), dia) in manual_arquivo.fatias_dados_manuais():
            base = manual_arquivo.dados_manuais(revenda, dia)
            return base.rename({"revenda": "REVENDA"}) if "revenda" in base.columns else base
        base = d.filtrar_por_revenda(d.dados_manuais(), _revenda())
        if base.is_empty() or "data" not in base.columns:
            return pl.DataFrame()
        return base.filter(pl.col("data").cast(pl.Date, strict=False) == dia)

    @reactive.calc
    def _linhas() -> list[dict]:
        base = lancamentos()
        if base.is_empty():
            return []
        linhas = list(base.iter_rows(named=True))
        return sorted(linhas, key=lambda r: str(r.get("hora") or ""), reverse=True)

    def _tabela(colunas: list[str], corpo: list, vazio: str = "") -> ui.Tag:
        return ui.tags.table(
            ui.tags.thead(ui.tags.tr(*[ui.tags.th(c) for c in colunas])),
            ui.tags.tbody(*corpo)
            if corpo
            else ui.tags.tbody(
                ui.tags.tr(ui.tags.td(vazio, colspan=str(len(colunas)), class_="dm-vazio")) if vazio else None
            ),
            class_="dm-tabela",
        )

    def _revenda_da_linha(linha: dict) -> str:
        return nome_oficial(str(linha.get("REVENDA") or linha.get("revenda") or "")) or _oficial()

    def _pode_apagar(revenda: str) -> bool:
        return pode(_usuario(), "excluir_dado_manual", revenda)

    def _lixeira(posicao: int) -> ui.Tag:
        if posicao >= LINHAS_COM_LIXEIRA:
            return ui.span()
        linhas = _linhas()
        pode_apagar = _pode_apagar(_revenda_da_linha(linhas[posicao]) if posicao < len(linhas) else _oficial())
        return ui.input_action_button(
            f"excluir_{posicao}",
            ui.span("\U0001f5d1", aria_hidden="true"),
            class_="dm-lixeira",
            disabled=not pode_apagar,
            title="Excluir linha" if pode_apagar else "Sem permissão",
        )

    @render.ui
    def tabela_totais():
        linhas = _linhas()
        corpo = []
        for banco in _bancos_da_revenda():
            do_banco = [r for r in linhas if (r.get("banco") or "") == banco]
            ultimo = do_banco[0] if do_banco else {}
            pix = sum(_numero(r.get("brinks_antes_16")) for r in do_banco)
            entrada = sum(
                _numero(r.get("transferencia_bancos")) for r in linhas if (r.get("destino_transf") or "") == banco
            )
            saida = sum(_numero(r.get("transferencia_bancos")) for r in do_banco)
            corpo.append(
                ui.tags.tr(
                    ui.tags.td(banco, class_="dm-banco"),
                    ui.tags.td(_reais(ultimo.get("adiantamento_romaneios"))),
                    ui.tags.td(_reais(ultimo.get("romaneio_pendente_encerrado"))),
                    ui.tags.td(_reais(pix)),
                    ui.tags.td(_reais(entrada)),
                    ui.tags.td(_reais(saida)),
                )
            )
        return _tabela(COLUNAS_TOTAIS, corpo)

    @render.ui
    def tabela_emprestimos():
        corpo = [
            ui.tags.tr(
                ui.tags.td(r.get("REVENDA") or ""),
                ui.tags.td(r.get("banco") or ""),
                ui.tags.td(r.get("tipo_emprestimo_devolucao") or ""),
                ui.tags.td(r.get("entrada_saida") or ""),
                ui.tags.td(r.get("revenda_origem_destino") or ""),
                ui.tags.td(_reais(r.get("devolucao_emprestimos"))),
                ui.tags.td(_lixeira(i)),
            )
            for i, r in enumerate(_linhas())
            if _numero(r.get("devolucao_emprestimos"))
        ]
        return _tabela(COLUNAS_EMPRESTIMO, corpo)

    @render.ui
    def tabela_transferencias():
        corpo = [
            ui.tags.tr(
                ui.tags.td(r.get("REVENDA") or ""),
                ui.tags.td(r.get("banco") or ""),
                ui.tags.td(r.get("revenda_destino") or ""),
                ui.tags.td(r.get("destino_transf") or ""),
                ui.tags.td(r.get("entrada_saida") or ""),
                ui.tags.td(_reais(r.get("transferencia_revendas"))),
                ui.tags.td(_lixeira(i)),
            )
            for i, r in enumerate(_linhas())
            if _numero(r.get("transferencia_revendas"))
        ]
        return _tabela(COLUNAS_TRANSFERENCIA, corpo)

    @render.ui
    def tabela_demais():
        campo_fabrica = _campo()
        colunas = list(COLUNAS_DEMAIS)
        if campo_fabrica:
            colunas.append(campo_fabrica[1])
        colunas.append("Excluir")
        corpo = []
        for i, r in enumerate(_linhas()):
            valores = [
                _numero(r.get(c))
                for c in (
                    "transferencia_bancos",
                    "romaneio_pendente_encerrado",
                    "adiantamento_romaneios",
                    "brinks_antes_16",
                )
            ]
            fabrica = _numero(r.get(campo_fabrica[0])) if campo_fabrica else 0.0
            if not (any(valores) or fabrica):
                continue
            if _numero(r.get("devolucao_emprestimos")) or _numero(r.get("transferencia_revendas")):
                continue
            dia = r.get("data")
            corpo.append(
                ui.tags.tr(
                    ui.tags.td(dia.strftime("%d/%m/%Y") if hasattr(dia, "strftime") else str(dia or "")),
                    ui.tags.td(str(r.get("hora") or "")[:8]),
                    ui.tags.td(r.get("banco") or ""),
                    ui.tags.td(r.get("destino_transf") or ""),
                    *[ui.tags.td(_reais(v)) for v in valores],
                    *([ui.tags.td(_reais(fabrica))] if campo_fabrica else []),
                    ui.tags.td(_lixeira(i)),
                )
            )
        return _tabela(colunas, corpo)

    _cliques: dict[str, int] = {}
    linha_a_excluir = reactive.value(None)

    def _clicou(nome: str) -> bool:
        if nome not in input:
            return False
        atual = input[nome]() or 0
        anterior = _cliques.get(nome, 0)
        _cliques[nome] = atual
        return atual > anterior

    @reactive.effect
    def _pedir_exclusao():
        with reactive.isolate():
            linhas = _linhas()
        clicadas = [n for n in range(LINHAS_COM_LIXEIRA) if _clicou(f"excluir_{n}")]
        for n in clicadas:
            if n >= len(linhas):
                continue
            if not _pode_apagar(_revenda_da_linha(linhas[n])):
                _avisar("Você não tem permissão para excluir. " + quem_libera("excluir_dado_manual"), "error")
                return
            linha_a_excluir.set(linhas[n])
            ui.modal_show(
                ui.modal(
                    ui.p("Tem certeza que deseja excluir esta linha? Isso não pode ser desfeito!"),
                    title="Excluir lançamento",
                    easy_close=True,
                    footer=ui.TagList(
                        ui.modal_button("Cancelar", class_="btn btn-secondary"),
                        ui.input_action_button("confirmar_exclusao", "Excluir", class_="btn btn-danger"),
                    ),
                ),
                session=session,
            )
            return

    @reactive.effect
    @reactive.event(input.confirmar_exclusao)
    def _excluir():
        linha = linha_a_excluir()
        ui.modal_remove(session=session)
        if not linha:
            return
        revenda = _revenda_da_linha(linha)
        if not _pode_apagar(revenda):
            _avisar("Você não tem permissão para excluir.", "error")
            return
        dia = linha.get("data")
        if not isinstance(dia, date):
            dia = input.data_referencia()
        try:
            gravacao.excluir_dado_manual(revenda, linha.get("banco") or "", dia, str(linha.get("hora") or "")[:8])
            manual_arquivo.substituir_fatia_dados_manuais(revenda, dia, gravacao.linhas_do_dia(revenda, dia))
        except Exception as erro:
            _avisar(f"Não deu para excluir: {str(erro)[:200]}", "error")
            return
        linha_a_excluir.set(None)
        with reactive.isolate():
            lancamentos_versao.set(lancamentos_versao() + 1)


def pag_dados_manuais_ui(revenda: str | None = None):
    return dados_manuais_ui("dados_manuais", revenda)


def pag_dados_manuais_server(revenda_atual=None):
    return dados_manuais_server("dados_manuais", revenda_atual=revenda_atual)
