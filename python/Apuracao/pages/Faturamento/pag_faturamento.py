from __future__ import annotations

from datetime import date

import polars as pl
from faicons import icon_svg
from loguru import logger
from shiny import module, reactive, render, ui

from core import cfop as tabela_cfop
from core import colunas_do_usuario, exportar, largura_colunas
from core import formato as fmt
from core.aviso import modal_aviso
from core.config import cnpjs_da_url, empresas_da_url, erp_das_empresas, nome_da_empresa
from core.secao import titulo_secao
from core.visibilidade import pagina_visivel

from .Dados import dados_faturamento as df_
from .Dados import pdf_faturamento

VALOR_NAVSET = "fat"
FILTRO_COM_BUSCA = {
    "placeholder": "Todas",
    "plugins": ["clear_button", "restore_on_backspace"],
    "dropdownParent": "body",
    "dropdownClass": "selectize-dropdown ppf-filtro-dropdown",
}
OBRIGATORIO = {**FILTRO_COM_BUSCA, "plugins": ["restore_on_backspace"]}


def _acao(controle: ui.Tag, rotulo: str) -> ui.Tag:
    return ui.div(controle, ui.div(rotulo, class_="ppf-acao-rotulo"), class_="ppf-acao")


def _acao_opcional(codigo: str, acao: ui.Tag) -> ui.Tag:
    return ui.panel_conditional(f"(input.acoes || []).includes('{codigo}')", acao)


def _mes(mes: str) -> str:
    return f"{mes[5:7]}/{mes[:4]}" if mes else "-"


@module.ui
def faturamento_ui(revenda: str | None = None):
    varias_empresas = len(empresas_da_url(revenda)) > 1
    filtro_empresa = ui.input_selectize(
        "empresa", "Empresa", {}, width="100%", options={**OBRIGATORIO, "placeholder": ""}
    )
    mes_final = ui.input_selectize(
        "ate",
        "Até o mês",
        {"": "Sem faturamento"},
        width="100%",
        options={**OBRIGATORIO, "placeholder": "Sem faturamento"},
    )
    if varias_empresas:
        linha_principal = ui.layout_columns(
            filtro_empresa, mes_final, col_widths=(4, 3), gap="0.5rem", class_="align-items-end"
        )
    else:
        linha_principal = ui.TagList(
            ui.div(filtro_empresa, class_="d-none"),
            ui.layout_columns(mes_final, col_widths=(3,), gap="0.5rem", class_="align-items-end"),
        )
    return ui.div(
        ui.card(
            ui.card_header(titulo_secao("Demonstrativo de Faturamento", icone="file-invoice-dollar")),
            ui.div(
                linha_principal,
                ui.div(
                    ui.output_ui("total_da_lista"),
                    class_="d-flex flex-wrap align-items-center justify-content-end gap-2",
                ),
                class_="fis-filtros",
            ),
            class_="fis-caixa-filtros",
        ),
        ui.card(
            ui.div(
                ui.output_ui("regra", class_="fis-tipos fis-fila"),
                ui.div(
                    _acao_opcional(
                        "cfops",
                        _acao(
                            ui.input_action_button(
                                "abrir_cfops",
                                None,
                                icon=icon_svg("list-check", a11y="deco"),
                                class_="ppf-btn-discreto",
                                title="Escolher o que entra no faturamento",
                            ),
                            "CFOPs",
                        ),
                    ),
                    _acao_opcional(
                        "pdf",
                        _acao(
                            ui.input_action_button(
                                "abrir_pdf",
                                None,
                                icon=icon_svg("file-pdf", a11y="deco"),
                                class_="ppf-btn-discreto",
                                title="O Demonstrativo de Faturamento em PDF, com os campos de assinatura",
                            ),
                            "PDF",
                        ),
                    ),
                    _acao_opcional(
                        "relatorio",
                        _acao(
                            exportar.botao(
                                "planilha",
                                "A tabela em planilha, os valores como número: escolha as colunas e a ordem delas",
                            ),
                            "Relatório",
                        ),
                    ),
                    _acao(
                        ui.popover(
                            ui.input_action_button(
                                "abrir_acoes",
                                None,
                                icon=icon_svg("sliders", a11y="deco"),
                                class_="ppf-btn-discreto",
                                title="Escolher as ações que aparecem aqui",
                            ),
                            ui.div(
                                ui.input_checkbox_group("acoes", None, df_.ACOES, selected=df_.ACOES_PADRAO),
                                class_="fis-colunas",
                            ),
                            ui.div(
                                ui.input_action_link("acoes_padrao", "Voltar ao padrão"), class_="fis-colunas-rodape"
                            ),
                            title="Ações da barra",
                            placement="bottom",
                            id="popover_acoes",
                        ),
                        "Ações",
                    ),
                    class_="ppf-grupo-acoes",
                ),
                class_="fis-barra",
            ),
            ui.div(ui.output_data_frame("tabela"), class_="fis-tabela"),
            class_="fis-caixa-lista",
        ),
        class_="fis-modulo",
    )


@module.server
def faturamento_server(input, output, session, revenda_atual, usuario_atual=None, versao_cache=None):
    @reactive.effect
    @reactive.event(input.acoes_padrao, ignore_init=True)
    def _acoes_padrao():
        ui.update_checkbox_group("acoes", selected=df_.ACOES_PADRAO)

    colunas_do_usuario.ColunasDaPessoa(
        input, f"{VALOR_NAVSET}_acoes", usuario_atual, df_.ACOES_PADRAO, id_colunas="acoes"
    )

    @reactive.calc
    def cnpjs() -> list[str]:
        return cnpjs_da_url(revenda_atual())

    @reactive.calc
    def erp_da_tela() -> str:
        empresa = input.empresa() or ""
        return erp_das_empresas([empresa] if empresa else cnpjs())

    @reactive.effect
    def _opcoes_empresa():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        try:
            lista = [e for e in empresas_da_url(revenda_atual()) if e["cnpj"] in cnpjs()]
            validos = [e["cnpj"] for e in lista]
            with reactive.isolate():
                atual = input.empresa() or ""
            ui.update_selectize(
                "empresa",
                choices={e["cnpj"]: e["nome"] for e in lista},
                selected=atual if atual in validos else next(iter(validos), ""),
            )
        except Exception as exc:
            logger.warning(f"Faturamento: opcoes de empresa -- {exc}")

    @reactive.calc
    def base() -> pl.DataFrame:
        if versao_cache is not None:
            versao_cache()
        return df_.base(input.empresa() or "")

    @reactive.effect
    def _opcoes_ate():
        if not pagina_visivel(session, VALOR_NAVSET):
            return
        try:
            meses = df_.meses_com_saida(base())
            with reactive.isolate():
                atual = input.ate() or ""
            fechados = [m for m in meses if m < f"{date.today():%Y-%m}"]
            selecionado = atual if atual in meses else next(iter(fechados or meses), "")
            ui.update_selectize(
                "ate", choices={m: _mes(m) for m in meses} or {"": "Sem faturamento"}, selected=selecionado
            )
        except Exception as exc:
            logger.warning(f"Faturamento: opcoes do mes -- {exc}")

    @reactive.calc
    def periodo() -> list[str]:
        ate = input.ate() or ""
        return df_.janela(ate, df_.configuracao()["meses"]) if len(ate) == 7 else []

    escolha = reactive.value(None)

    @reactive.calc
    def saidas() -> list[tuple[str, float]]:
        return df_.opcoes_cfop(base(), periodo(), "S")

    @reactive.calc
    def entradas() -> list[tuple[str, float]]:
        return [(c, v) for c, v in df_.opcoes_cfop(base(), periodo(), "E") if tabela_cfop.devolucao(c)]

    def _marcados(chave: str, opcoes: list[tuple[str, float]]) -> list[str]:
        pedidos = (escolha() or df_.configuracao())[chave]
        presentes = {c for c, _ in opcoes}
        return [c for c in pedidos if c in presentes]

    @reactive.calc
    def escolhidos() -> list[str]:
        return _marcados("cfops", saidas())

    @reactive.calc
    def devolucoes() -> list[str]:
        return _marcados("devolucoes", entradas())

    @reactive.calc
    def linhas() -> pl.DataFrame:
        return df_.tabela(base(), periodo(), escolhidos(), devolucoes())

    @reactive.calc
    def totais() -> dict:
        return df_.totais(linhas())

    @render.ui
    def total_da_lista():
        totais_do_periodo = totais()
        meses = periodo()
        partes_do_total = [
            ui.span("Faturamento"),
            ui.span(f" de {_mes(meses[0])} a {_mes(meses[-1])}" if meses else ""),
            ui.span(": "),
            ui.tags.strong(fmt.moeda(totais_do_periodo["total"])),
            ui.span(" · média por mês"),
            ui.span(f" ({len(meses)} meses)" if meses else ""),
            ui.span(": "),
            ui.tags.strong(fmt.moeda(totais_do_periodo["media"])),
            ui.span(" · maior mês"),
            ui.span(f" ({df_.rotulo_mes(totais_do_periodo['maior_mes'])})" if totais_do_periodo["maior_mes"] else ""),
            ui.span(": "),
            ui.tags.strong(fmt.moeda(totais_do_periodo["maior"])),
        ]
        return ui.span(*partes_do_total)

    @render.ui
    def regra():
        cfops, saem = escolhidos(), devolucoes()
        if not cfops:
            return ui.span(
                icon_svg("triangle-exclamation", a11y="deco"),
                " Escolha em CFOPs o que entra no faturamento.",
                class_="fis-op-alerta",
            )
        return ui.span(
            ui.tags.strong("Entram: "),
            ", ".join(cfops),
            *([ui.tags.strong("  ·  Saem: "), ", ".join(saem)] if saem else []),
            title="\n".join(tabela_cfop.rotulo(c) for c in [*cfops, *saem]),
        )

    def _caixas(id_caixas: str, opcoes: list[tuple[str, float]], marcados: list[str]) -> ui.Tag:
        if not opcoes:
            return ui.p("Nenhum no período.", class_="fis-op-explica")
        rotulos = {
            c: ui.span(
                ui.span(c, class_="fis-cfop-numero"),
                ui.span(tabela_cfop.descricao(c) or "-", class_="fis-cfop-texto"),
                ui.span(fmt.moeda(v), class_="fis-cfop-valor"),
                class_="fis-cfop-linha",
            )
            for c, v in opcoes
        }
        return ui.input_checkbox_group(id_caixas, None, rotulos, selected=marcados, width="100%")

    @reactive.effect
    @reactive.event(input.abrir_cfops)
    def _abrir_cfops():
        try:
            if not periodo():
                ui.modal_show(modal_aviso(f"Esta empresa ainda não tem faturamento lido do {erp_da_tela()}.", "CFOPs"))
                return
            ui.modal_show(
                ui.modal(
                    ui.p(
                        f"Os CFOPs que a empresa usou de {_mes(periodo()[0])} a {_mes(periodo()[-1])}, do maior valor para o "
                        "menor. O que está marcado aqui vale nesta tela até ela ser aberta de novo.",
                        class_="fis-op-explica",
                    ),
                    ui.layout_columns(
                        ui.div(
                            ui.div("Entram no faturamento", class_="fis-cfops-titulo"),
                            _caixas("janela_cfops", saidas(), escolhidos()),
                            class_="fis-cfops",
                        ),
                        ui.div(
                            ui.div("Devoluções que saem", class_="fis-cfops-titulo"),
                            _caixas("janela_devolucoes", entradas(), devolucoes()),
                            class_="fis-cfops",
                        ),
                        col_widths=(6, 6),
                    ),
                    title=ui.span(
                        ui.span(icon_svg("list-check", a11y="deco"), class_="fis-op-icone fis-op-ciencia"),
                        "O que entra no faturamento",
                        class_="fis-op-titulo",
                    ),
                    easy_close=True,
                    size="xl",
                    footer=ui.TagList(
                        ui.input_action_button(
                            "cfops_padrao", "Voltar à regra do config", class_="btn-outline-secondary me-auto"
                        ),
                        ui.modal_button("Cancelar", class_="btn-outline-secondary"),
                        ui.input_action_button("aplicar_cfops", "Aplicar", class_="btn-primary"),
                    ),
                )
            )
        except Exception as exc:
            logger.warning(f"Faturamento: abrir os CFOPs -- {exc}")

    @reactive.effect
    @reactive.event(input.cfops_padrao, ignore_init=True)
    def _cfops_padrao():
        try:
            conf = df_.configuracao()
            ui.update_checkbox_group("janela_cfops", selected=[c for c in conf["cfops"] if c in dict(saidas())])
            ui.update_checkbox_group(
                "janela_devolucoes", selected=[c for c in conf["devolucoes"] if c in dict(entradas())]
            )
        except Exception as exc:
            logger.warning(f"Faturamento: voltar a' regra -- {exc}")

    @reactive.effect
    @reactive.event(input.aplicar_cfops, ignore_init=True)
    def _aplicar_cfops():
        try:
            agora = escolha() or df_.configuracao()
            escolha.set(
                {
                    "cfops": list(input.janela_cfops() or []) if "janela_cfops" in input else agora["cfops"],
                    "devolucoes": list(input.janela_devolucoes() or [])
                    if "janela_devolucoes" in input
                    else agora["devolucoes"],
                }
            )
            ui.modal_remove()
        except Exception as exc:
            logger.warning(f"Faturamento: aplicar os CFOPs -- {exc}")

    @render.data_frame
    def tabela():
        if not periodo():
            return render.DataGrid(
                pl.DataFrame({f"Sem faturamento desta empresa no {erp_da_tela()}.": []}), height="10vh"
            )
        return largura_colunas.grade(df_.na_tela(linhas(), escolhidos()), height="62vh", width="100%", summary=False)

    @render.download(filename=lambda: f"faturamento_{input.empresa() or 'empresa'}_{input.ate() or ''}.xlsx")
    def planilha():
        yield df_.planilha(
            linhas(), escolhidos(), nome_da_empresa(input.empresa() or ""), colunas=janela_exportar.colunas("planilha")
        )

    def colunas_da_planilha() -> list[str]:
        return [] if linhas().is_empty() else df_.tabela_planilha(linhas().head(1), escolhidos()).columns

    janela_exportar = exportar.Exportar(input, {"planilha": ("Faturamento", colunas_da_planilha)})

    @reactive.effect
    @reactive.event(input.abrir_pdf)
    def _abrir_pdf():
        try:
            cnpj = input.empresa() or ""
            if not cnpj or not periodo():
                ui.modal_show(modal_aviso("Escolha a empresa e o mês.", "Demonstrativo"))
                return
            if not escolhidos():
                ui.modal_show(
                    modal_aviso("Escolha em CFOPs o que entra no faturamento antes de gerar o PDF.", "Demonstrativo")
                )
                return
            empresa = df_.dados_empresa(cnpj)
            responsavel, tecnico = df_.assinantes(cnpj)
            faltam = df_.faltando(empresa)
            ui.modal_show(
                ui.modal(
                    ui.p(
                        f"{empresa['razao']} ({empresa['cnpj']}), {_mes(periodo()[0])} a {_mes(periodo()[-1])}: "
                        f"{fmt.moeda(totais()['total'])}.",
                        class_="fis-op-explica",
                    ),
                    ui.div(
                        icon_svg("triangle-exclamation", a11y="deco"),
                        f" Sai em branco no PDF (falta em config/relatorios.json): {', '.join(faltam)}.",
                        class_="fis-op-alerta",
                    )
                    if faltam
                    else None,
                    ui.tags.strong("Responsável pela empresa"),
                    ui.layout_columns(
                        ui.input_text("resp_nome", "Nome", responsavel["nome"]),
                        ui.input_text("resp_cpf", "CPF", responsavel["cpf"]),
                        ui.input_text("resp_rg", "RG", responsavel["rg"]),
                        col_widths=(6, 3, 3),
                    ),
                    ui.tags.strong("Responsável técnico"),
                    ui.layout_columns(
                        ui.input_text("tec_nome", "Nome", tecnico["nome"]),
                        ui.input_text("tec_cpf", "CPF", tecnico["cpf"]),
                        ui.input_text("tec_crc", "CRC", tecnico["crc"]),
                        col_widths=(6, 3, 3),
                    ),
                    ui.layout_columns(
                        ui.input_text("local", "Cidade", empresa["municipio"].title()),
                        ui.input_date("data", "Data", value=date.today(), format="dd/mm/yyyy", language="pt-BR"),
                        col_widths=(6, 6),
                    ),
                    title=ui.span(
                        ui.span(icon_svg("file-pdf", a11y="deco"), class_="fis-op-icone fis-op-ciencia"),
                        "Demonstrativo de Faturamento",
                        class_="fis-op-titulo",
                    ),
                    easy_close=True,
                    size="l",
                    footer=ui.TagList(
                        ui.modal_button("Cancelar", class_="btn-outline-secondary"),
                        ui.download_button("baixar_pdf", "Gerar PDF", class_="btn-primary"),
                    ),
                )
            )
        except Exception as exc:
            logger.warning(f"Faturamento: abrir o PDF -- {exc}")
            ui.notification_show(f"Não foi possível preparar o PDF: {exc}", type="error", duration=10)

    @render.download(filename=lambda: f"demonstrativo_faturamento_{input.empresa() or ''}_{input.ate() or ''}.pdf")
    def baixar_pdf():
        cnpj = input.empresa() or ""
        meses = linhas()
        dia = input.data() or date.today()
        yield pdf_faturamento.gerar(
            {
                "empresa": df_.dados_empresa(cnpj),
                "meses": [
                    (df_.rotulo_mes(m), fmt.moeda(v).removeprefix("R$ "))
                    for m, v in meses.select("mes", "faturamento").iter_rows()
                ],
                "total": fmt.moeda(df_.totais(meses)["total"]).removeprefix("R$ "),
                "local_e_data": f"{(input.local() or '').strip()}, {df_.data_por_extenso(dia)}".lstrip(", "),
                "responsavel": {"nome": input.resp_nome(), "cpf": input.resp_cpf(), "rg": input.resp_rg()},
                "tecnico": {"nome": input.tec_nome(), "cpf": input.tec_cpf(), "crc": input.tec_crc()},
            }
        )


def pag_faturamento_ui(revenda: str | None = None):
    return faturamento_ui("faturamento", revenda)


def pag_faturamento_server(revenda_atual, usuario_atual=None, versao_cache=None):
    return faturamento_server(
        "faturamento", revenda_atual=revenda_atual, usuario_atual=usuario_atual, versao_cache=versao_cache
    )
