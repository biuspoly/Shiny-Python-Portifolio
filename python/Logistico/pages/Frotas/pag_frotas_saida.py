import asyncio
import io
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs

import polars as pl
from faicons import icon_svg
from loguru import logger
from shiny import module, reactive, render, ui

from core.auth import identificar_usuario
from core.aviso import modal_aviso
from core.compat import para_pandas
from core.config import pode
from core.crossfilter import usar_crossfilter
from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.tabela_paginada import TabelaPaginada
from core.visibilidade import pagina_visivel
from pages.Frotas.Dados import mapa_rastreio as mr

from .Dados import dados_frota as d
from .Dados import informar_motivo as im
from .Dados import tabela_itables as ti

FILTROS = [
    ("proprietario", "Prop. Veículo", "EMPRESA", None),
    ("unidade", "Unidade", "UNIDADE", None),
    ("uf", "UF", "UF_Emp", None),
    ("placa", "Placa", "PLACA", None),
    ("tipo", "Tipo", "TIPO", None),
    ("modelo", "Modelo", "MODELO", None),
    ("restadm", "Rest Adm", "RESTRICAO_ADM", ("Geral", "Rest Adm")),
    ("gravame", "Gravame", "GRAVAME", ("Geral", "Rest Adm")),
    ("gravame_pendente", "Gravame Pen", "GRAVAME_PENDENTE", ("Geral", "Rest Adm")),
    ("renajud", "Renajud", "RENAJUD", ("Geral", "Renajud")),
    ("debito", "Débito Detran", "DEBITO_DETRAN", ("Detran",)),
    ("transferencia", "Transferência", "TRANSFERENCIA", None),
    ("atualizacao", "Última Atualização", "ULT_ATUALIZACAO", None),
    ("motivo_saida", "Motivo Saída", "MOTIVO_INFORMADO", None),
    ("tipo_saida_filtro", "Tipo Saída", im.COLUNA_TIPO_SAIDA, None),
]

ID_FILTRO_SITUACAO = "situacao_multa"

ABA_COMBUSTIVEL = "Combustível"
ALTURA_MAPA_RASTREIO = "62vh"
CHAVE_ABA_COMBUSTIVEL = "aba_combustivel"

ABAS = ["Geral", "Rest Adm", "Renajud", "Detran", ABA_COMBUSTIVEL, "Custos"]

CLASSES_VEICULO = [
    ("Cavalo", "cavalo-light.png", "Cavalo e Reboque"),
    ("Caminhão", "caminhao-light.png", "Caminhão"),
    ("Carro", "carro-light.png", "Automóvel"),
    ("Moto", "moto-light.png", "Motocicleta"),
]

_LARGURA_FROTA = {
    "Data": 100,
    "Prop. Veículo": 150,
    "Unidade": 110,
    "UF": 60,
    "Placa": 90,
    "Tipo": 90,
    "Modelo": 140,
    "Ano": 70,
    "Fabricação": 90,
    "Renavam": 110,
    "Chassi": 150,
    "Carroceria": 110,
    "Rest Adm": 90,
    "Gravame": 90,
    "Gravame\nPendente": 100,
    "Proprietário": 140,
    "Renajud": 90,
    "Nº\nProcessos": 90,
    "Processo": 160,
    "Tipo\nRestrição": 110,
    "Tribunal": 110,
    "Órgão": 100,
    "Débito": 100,
    "Ipva Atual": 100,
    "Ipva Ant": 100,
    "Licenciamento": 110,
    "Multa\nDetran": 90,
    "Multa\nSenatran": 90,
    "Tabela Fipe": 100,
    "Outros\nDébitos": 95,
    "Renainf": 100,
    "Auto da\nInfração": 110,
    "Dt/Hr\nInfração": 110,
    "Prazo Ident\nCondutor": 105,
    "Vencimento": 100,
    "Valor": 90,
    "Infração": 140,
    "Local": 125,
    "Paga": 80,
    "Paga por": 130,
    "Consultado\nem": 100,
    "Última\nAtualização": 110,
    "Custo API": 100,
    "Veículos": 90,
    "Transferências": 110,
    "Carro": 70,
    "Moto": 70,
    "Cavalo": 70,
    "Caminhão": 90,
    "Informar\nmotivo": 70,
    "Anexo": 60,
    "Obs": 220,
    "Tipo\nSaída": 100,
    "Informar\n(Outro)": 160,
    "Comprador": 160,
    "Valor\nVenda": 100,
    "Data/Hora": 125,
    "Motorista": 170,
    "Posto": 170,
    "Cidade": 140,
    "Combustível": 130,
    "Hodômetro": 100,
    "Km\nRodados": 90,
    "Litros": 80,
    "Km/Litro": 85,
    "Valor/Litro": 95,
    "Valor/Km": 90,
    "Centro\nde Custo": 105,
    "Cartão": 145,
    "Responsável": 160,
}


def _filtro_ui(id_filtro: str, rotulo: str, abas: tuple[str, ...] | None) -> ui.Tag:
    attrs = {}
    classe = "filtro-frota"
    if abas is not None:
        classe += " filtro-condicional"
        attrs["data-abas"] = ",".join(abas)
    return ui.div(
        ui.input_selectize(
            id_filtro,
            rotulo,
            choices=[],
            multiple=True,
            options={
                "placeholder": "Todos",
                "dropdownParent": "body",
                "dropdownClass": "selectize-dropdown frota-selectize-dropdown",
                "hideSelected": False,
                "plugins": ["remove_button"],
            },
        ),
        class_=classe,
        **attrs,
    )


_OPCOES_TIPO_SAIDA = {"": "Selecione...", "Transferência": "Transferência", "Venda": "Venda", "Outro": "Outro"}


def _parse_valor_venda(texto: str | None) -> float | None:
    texto = (texto or "").strip()
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return round(float(texto), 2)
    except ValueError:
        return None


def _campo_leitura(rotulo: str, valor: str) -> ui.Tag:
    return ui.div(
        ui.tags.label(rotulo, class_="control-label"),
        ui.div(valor, class_="form-control frota-campo-leitura"),
        class_="mb-2",
    )


@module.ui
def frota_saida_ui():
    return ui.div(
        ui.card(
            ui.div(
                *[_filtro_ui(id_filtro, rotulo, abas) for id_filtro, rotulo, _coluna, abas in FILTROS],
                _filtro_ui(ID_FILTRO_SITUACAO, "Situação", ("Detran",)),
                ui.input_action_button(
                    "limpar",
                    None,
                    icon=icon_svg("eraser", a11y="deco"),
                    class_="btn-primary btn-limpar-frota",
                    title="Limpar filtros",
                ),
                class_="filtros-frota",
            ),
        ),
        ui.output_text("aviso"),
        ui.card(
            ui.card_header(
                ui.div(
                    ui.span("Dados consolidados"),
                    ui.input_action_button(
                        "toggle_consolidados",
                        None,
                        icon=icon_svg("minus", a11y="deco"),
                        class_="btn-toggle-card",
                        title="Minimizar",
                    ),
                    class_="d-flex justify-content-between align-items-center w-100",
                )
            ),
            ui.output_ui("corpo_consolidados"),
        ),
        ui.div(
            ui.download_button(
                "exportar",
                None,
                icon=icon_svg("download", a11y="deco"),
                class_="btn-exportar-frota",
                title="Baixar tabela em Excel",
            ),
            ui.div(ui.output_ui("abas_permitidas"), class_="abas-frota"),
            class_="linha-abas-frota my-4",
        ),
        ui.card(
            ui.card_header(
                ui.div(
                    ui.span("Detalhamento"),
                    ui.tooltip(
                        ui.div(
                            ui.input_switch("detalhado", "Ver detalhado", value=False),
                            class_="switch-detalhado",
                        ),
                        "Mostra o detalhamento linha a linha (processos/multas), em vez do resumo por "
                        "veículo. Na aba Combustível, mostra o mapa de onde cada veículo esteve "
                        "por último.",
                        placement="bottom",
                    ),
                    ui.input_action_button(
                        "toggle_detalhamento",
                        None,
                        icon=icon_svg("minus", a11y="deco"),
                        class_="btn-toggle-card ms-auto",
                        title="Minimizar",
                    ),
                    class_="d-flex align-items-center gap-4 w-100",
                )
            ),
            ui.output_ui("corpo_detalhamento"),
        ),
        class_="frota-modulo frota-modulo-saida",
    )


@module.server
def frota_saida_server(input, output, session):
    @reactive.calc
    def revenda_atual() -> str | None:
        query_string = session.clientdata.url_search()
        valores = parse_qs(query_string.lstrip("?")).get("REVENDA")
        return valores[0] if valores else None

    @reactive.calc
    async def transferencias_atuais() -> pl.DataFrame:
        return await asyncio.to_thread(im.carregar_transferencias)

    @reactive.calc
    async def base_completa() -> pl.DataFrame:
        base = await asyncio.to_thread(d.carregar_geral_frota_saida)
        base = im.aplicar_transferencias(base, await transferencias_atuais())
        return d.filtrar_por_revenda(base, revenda_atual())

    @reactive.calc
    async def consolidada_df():
        base = await base_completa_filtrada()
        return await asyncio.to_thread(d.tabela_consolidada, base)

    @reactive.calc
    def mostra_custo_api() -> bool:
        revenda = revenda_atual()
        return revenda is None

    @reactive.calc
    async def tabela_consolidada_pronta():
        consolidada = await consolidada_df()
        return await asyncio.to_thread(ti.construir_consolidada_df, consolidada, mostra_custo_api())

    @render.data_frame
    async def tabela_consolidada():
        pandas_df = await tabela_consolidada_pronta()
        return render.DataTable(pandas_df, height="274px", summary=False, filters=False, selection_mode="row")

    @reactive.calc
    async def data_selecionada():
        selecao = tabela_consolidada.cell_selection()
        if not selecao or not selecao.get("rows"):
            return None
        base = await consolidada_df()
        indice = selecao["rows"][0]
        if indice >= base.height:
            return None
        return base["DTA_EXEC"][indice]

    versao_dados_vivos = reactive.value(0, name="versao_dados_vivos")

    @reactive.calc
    async def movimentacao_atual() -> pl.DataFrame:
        versao_dados_vivos()
        return await asyncio.to_thread(im.carregar_movimentacao)

    @reactive.calc
    async def base_com_motivo() -> pl.DataFrame:
        base, movimentacao = await asyncio.gather(base_completa(), movimentacao_atual())
        return await asyncio.to_thread(im.marcar_motivo_informado, base, movimentacao)

    @reactive.calc
    async def base_bruta() -> pl.DataFrame:
        base, selecionada = await asyncio.gather(base_com_motivo(), data_selecionada())
        if selecionada is not None:
            return d.filtrar_por_data(base, selecionada)
        if any(filtros_atuais().values()):
            return base
        data = d.data_mais_recente(base)
        return d.filtrar_por_data(base, data) if data is not None else base

    @reactive.calc
    async def usuario_atual() -> str:
        usuario, _script_cache = await asyncio.to_thread(identificar_usuario, session.root_scope().http_conn)
        return usuario

    @reactive.calc
    async def pode_combustivel() -> bool:
        return pode(await usuario_atual(), CHAVE_ABA_COMBUSTIVEL)

    @render.ui
    async def abas_permitidas():
        liberado = await pode_combustivel()
        escolhas = [a for a in ABAS if a != ABA_COMBUSTIVEL or liberado]
        return ui.input_radio_buttons("aba", None, choices=escolhas, selected="Geral", inline=True)

    @reactive.calc
    async def rastreio_atual() -> pl.DataFrame:
        return await asyncio.to_thread(d.carregar_geral_rastreio)

    @reactive.calc
    async def combustivel() -> pl.DataFrame:
        return await asyncio.to_thread(d.carregar_geral_combustivel)

    @reactive.calc
    async def renajud() -> pl.DataFrame:
        return await asyncio.to_thread(d.carregar_geral_renajud)

    @reactive.calc
    async def renainf() -> pl.DataFrame:
        return await asyncio.to_thread(d.carregar_geral_renainf)

    @reactive.calc
    async def placas_ult_rom() -> set[str]:
        base = await asyncio.to_thread(d.carregar_geral_frota_saida)
        return await asyncio.to_thread(d.placas_com_romaneio_antigo, base)

    consolidados_aberto = reactive.value(True, name="consolidados_aberto")
    detalhamento_aberto = reactive.value(True, name="detalhamento_aberto")

    @reactive.effect
    @reactive.event(input.toggle_consolidados)
    def _toggle_consolidados():
        aberto = not consolidados_aberto()
        consolidados_aberto.set(aberto)
        ui.update_action_button(
            "toggle_consolidados", icon=icon_svg("minus" if aberto else "plus", a11y="deco"), session=session
        )

    @reactive.effect
    @reactive.event(input.toggle_detalhamento)
    def _toggle_detalhamento():
        aberto = not detalhamento_aberto()
        detalhamento_aberto.set(aberto)
        ui.update_action_button(
            "toggle_detalhamento", icon=icon_svg("minus" if aberto else "plus", a11y="deco"), session=session
        )

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar_filtros():
        for id_filtro, _rotulo, _coluna, _abas in FILTROS:
            ui.update_selectize(id_filtro, selected=[], session=session)
        ui.update_selectize(ID_FILTRO_SITUACAO, selected=[], session=session)

    @reactive.effect
    async def _opcoes_situacao():
        if not pagina_visivel(session, "fro_sai"):
            return
        try:
            situacoes = d.situacoes_disponiveis(await renainf())
        except Exception as exc:
            logger.warning(f"Frotas/Saída: nao deu pra montar o filtro de situacao -- {exc}")
            return
        ui.update_selectize(
            ID_FILTRO_SITUACAO,
            choices={s: d.SITUACOES_MULTA.get(s, s) for s in situacoes},
            selected=list(input[ID_FILTRO_SITUACAO]()),
            session=session,
        )

    @reactive.calc
    def filtros_atuais() -> dict[str, list[str]]:
        return {coluna: input[id_filtro]() for id_filtro, _rotulo, coluna, _abas in FILTROS}

    @reactive.calc
    async def base_filtrada() -> pl.DataFrame:
        base = await base_bruta()
        return d.aplicar_filtros(base, filtros_atuais())

    @reactive.calc
    async def base_completa_filtrada() -> pl.DataFrame:
        base = await base_com_motivo()
        return d.aplicar_filtros(base, filtros_atuais())

    @reactive.calc
    async def base_opcoes() -> pl.DataFrame:
        if await data_selecionada() is not None:
            return await base_filtrada()
        return await base_completa_filtrada()

    usar_crossfilter(
        input,
        session,
        [(id_filtro, coluna) for id_filtro, _rotulo, coluna, _abas in FILTROS],
        base_opcoes,
        valor_navset="fro_sai",
        formatadores={"atualizacao": ti.data_aaaammdd_br},
    )

    @render.text
    async def aviso():
        base = await base_filtrada()
        if "UF_Emp" in base.columns and base.filter(pl.col("UF_Emp") == "NI").height > 0:
            return "Detran PE e RJ se encontram com instabilidades."
        return ""

    @render.ui
    async def cards_classe():
        base = await base_filtrada()
        resumo = d.resumo_por_classe(base)
        linhas = {row["CLASSE"]: row for row in resumo.iter_rows(named=True)}
        cartoes = []
        for classe, imagem, titulo in CLASSES_VEICULO:
            linha = linhas.get(classe, {"QTD": 0, "REST_ADM": 0, "RENAJUD": 0, "DEBITO": 0.0})
            debito_mil = (linha["DEBITO"] or 0) / 1000
            cartoes.append(
                ui.div(
                    ui.img(src=f"img/{imagem}", class_="icone-classe-veiculo", title=titulo),
                    ui.div(str(linha["QTD"]), class_="valor-classe divisor-classe"),
                    ui.div(
                        ui.tags.b("Rest. Adm:"),
                        ui.tags.br(),
                        ui.span(str(linha["REST_ADM"])),
                        class_="detalhe-classe divisor-classe",
                    ),
                    ui.div(
                        ui.tags.b("Renajud:"),
                        ui.tags.br(),
                        ui.span(str(linha["RENAJUD"])),
                        class_="detalhe-classe divisor-classe",
                    ),
                    ui.div(
                        ui.tags.b("Débito:"),
                        ui.tags.br(),
                        ui.span(f"R$ {debito_mil:,.2f} Mil"),
                        class_="detalhe-classe",
                    ),
                    class_="card-classe-veiculo",
                    title=titulo,
                )
            )
        return ui.TagList(*cartoes)

    @render.ui
    async def css_largura_tabela_consolidada():
        pandas_df = await tabela_consolidada_pronta()
        larguras = [ColunaLargura(c, _LARGURA_FROTA.get(c, 100)) for c in pandas_df.columns]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_consolidada')}", larguras))

    @render.ui
    def corpo_consolidados():
        if not consolidados_aberto():
            return None
        return ui.layout_columns(
            ui.div(ui.output_ui("cards_classe"), class_="cards-classe-veiculo"),
            ui.div(
                ui.output_ui("css_largura_tabela_consolidada"),
                ui.output_data_frame("tabela_consolidada"),
                class_="tabela-frota tabela-frota-consolidada tabela-resize",
            ),
            col_widths=[5, 7],
        )

    @render.ui
    async def css_largura_tabela():
        pandas_df, _estilos = await tabela_pronta()
        larguras = [ColunaLargura(c, _LARGURA_FROTA.get(c, 100)) for c in pandas_df.columns]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela')}", larguras))

    @reactive.calc
    async def mapa_rastreio_html() -> str:
        rastreio, base = await asyncio.gather(rastreio_atual(), base_filtrada())
        return await asyncio.to_thread(mr.mapa_html, d.rastreio_das_placas(rastreio, base))

    @render.ui
    async def corpo_detalhamento():
        if not detalhamento_aberto():
            return None
        if input.aba() == ABA_COMBUSTIVEL and input.detalhado():
            return ui.tags.iframe(
                srcdoc=await mapa_rastreio_html(),
                style=f"width:100%; height:{ALTURA_MAPA_RASTREIO}; border:none;",
            )
        return ui.div(
            ui.output_ui("css_largura_tabela"),
            ui.output_data_frame("tabela"),
            ui.output_ui("controles_detalhamento"),
            class_="tabela-frota tabela-frota-detalhamento tabela-resize",
        )

    def _montar(base, aba, detalhado, lado, custo_api=True, situacoes=None):
        if aba == "Geral":
            tabela = d.tabela_geral(base)
            anexos = {p: im.caminho_para_url(c) for p, c in im.mapa_anexo_motivo(lado).items()}
            return ti.adicionar_botoes_motivo(
                tabela,
                im.mapa_motivo(lado),
                anexos,
                im.mapa_tipo_saida(lado),
                im.mapa_tipo_saida_outro(lado),
                im.mapa_comprador(lado),
                im.mapa_valor_venda(lado),
            )
        if aba == "Rest Adm":
            return d.tabela_restadm(base)
        if aba == "Renajud":
            return d.tabela_renajud_detalhado(base, lado) if detalhado else d.tabela_renajud_consolidado(base)
        if aba == "Detran":
            return d.tabela_detran_detalhado(base, lado, situacoes) if detalhado else d.tabela_detran_consolidado(base)
        if aba == "Combustível":
            return d.tabela_combustivel(lado, base)
        return d.tabela_custos(base, custo_api)

    @reactive.calc
    async def tabela_selecionada():
        aba = input.aba() if "aba" in input else "Geral"
        if aba == ABA_COMBUSTIVEL and not await pode_combustivel():
            aba = "Geral"
        detalhado = input.detalhado()
        base = await base_filtrada()
        lado = None
        if aba == "Geral":
            lado = await movimentacao_atual()
        elif aba == "Combustível":
            lado = await combustivel()
        elif aba == "Renajud" and detalhado:
            lado = await renajud()
        situacoes = None
        if aba == "Detran" and detalhado:
            lado = await renainf()
            situacoes = list(input[ID_FILTRO_SITUACAO]())
        return await asyncio.to_thread(_montar, base, aba, detalhado, lado, mostra_custo_api(), situacoes)

    paginador_detalhamento = TabelaPaginada("pag_detalhamento", input, session)

    @reactive.calc
    async def tabela_pronta():
        selecionada, placas = await asyncio.gather(tabela_selecionada(), placas_ult_rom())
        return await asyncio.to_thread(ti.construir_detalhamento_df, selecionada, placas)

    @render.data_frame
    async def tabela():
        pandas_df, estilos = await tabela_pronta()
        fatia, estilos_fatia = paginador_detalhamento.fatiar_com_estilos(pandas_df, estilos)
        return render.DataTable(
            fatia,
            styles=estilos_fatia,
            height="50vh",
            summary=False,
            filters=False,
            selection_mode="none",
        )

    @render.ui
    async def controles_detalhamento():
        pandas_df, _estilos = await tabela_pronta()
        return paginador_detalhamento.controles(len(pandas_df))

    @reactive.effect
    async def _reinicia_pagina_detalhamento():
        if not detalhamento_aberto():
            return
        await tabela_selecionada()
        paginador_detalhamento.reiniciar()

    @render.download_button(filename=lambda: f"frota-saida-{date.today().isoformat()}.xlsx")
    async def exportar():
        selecionada = await tabela_selecionada()
        tabela_atual = selecionada.drop(
            "TRANSFERENCIA",
            "BOTAO_MOTIVO",
            "BOTAO_ANEXO_SAIDA",
            strict=False,
        )
        tabela_atual = tabela_atual.rename({c: ti.rotulo_uma_linha(c) for c in tabela_atual.columns})
        buffer = io.BytesIO()
        await asyncio.to_thread(para_pandas(tabela_atual).to_excel, buffer, index=False, engine="openpyxl")
        yield buffer.getvalue()

    contexto_motivo = reactive.value(None, name="contexto_motivo")

    def _campo_motivo(limite: int) -> ui.Tag:
        campo = ui.input_text_area("motivo_texto", f"Motivo (até {limite} caracteres)")
        for filho in campo.children:
            if getattr(filho, "name", "") == "textarea":
                filho.attrs["maxlength"] = str(limite)
        return campo

    def _modal_motivo(empresa: str, placa: str) -> ui.Tag:
        return ui.modal(
            _campo_leitura("Proprietário", empresa),
            _campo_leitura("Placa", placa),
            _campo_motivo(im.limite_motivo()),
            ui.input_select("tipo_saida_input", "Tipo de saída", choices=_OPCOES_TIPO_SAIDA),
            ui.input_text("tipo_saida_outro_input", "Informar (se Outro)"),
            ui.input_text("valor_venda_input", "Valor da venda (R$)"),
            ui.input_text("comprador_input", "Pra quem foi a venda"),
            ui.input_file(
                "anexo_motivo",
                "Selecionar arquivo",
                button_label="Procurar...",
                placeholder="",
                accept=[".pdf", ".jpg", ".jpeg", ".png"],
            ),
            ui.div(
                ui.input_action_button("bt_enviar_motivo", "Enviar", class_="btn-primary btn-sm", disabled=True),
                class_="text-center",
            ),
            title="Informar motivo de saída:",
            size="s",
            easy_close=True,
            footer=None,
        )

    @reactive.effect
    @reactive.event(input.clique_motivo)
    async def _abrir_modal_motivo():
        placa = input.clique_motivo()
        base = await base_filtrada()
        linha = base.filter(pl.col("PLACA") == placa)
        if linha.height == 0:
            return
        empresa = linha["EMPRESA"][0] or ""
        cnpj_emp = linha["CNPJ_EMP"][0] if "CNPJ_EMP" in linha.columns else ""
        contexto_motivo.set({"placa": placa, "empresa": empresa, "cnpj_emp": cnpj_emp})
        ui.modal_show(_modal_motivo(empresa, placa), session=session)

    @reactive.effect
    def _valida_motivo():
        if "motivo_texto" not in input:
            return
        texto = (input.motivo_texto() or "").strip()
        fora_do_tamanho = len(texto) <= 1 or len(texto) > im.limite_motivo()
        ui.update_action_button("bt_enviar_motivo", disabled=fora_do_tamanho, session=session)

    @reactive.effect
    @reactive.event(input.bt_enviar_motivo)
    async def _enviar_motivo():
        ctx = contexto_motivo()
        motivo = (input.motivo_texto() or "").strip()
        if ctx is None or len(motivo) <= 1:
            return

        anexo_path = None
        arquivos = input.anexo_motivo()
        if arquivos:
            arquivo = arquivos[0]
            anexo_path = await asyncio.to_thread(
                im.salvar_anexo, "MOTIVO", ctx["placa"], ctx["cnpj_emp"], arquivo["datapath"], arquivo["name"]
            )

        tipo_saida = (input.tipo_saida_input() or "").strip() or None
        tipo_saida_outro = (input.tipo_saida_outro_input() or "").strip() or None
        comprador = (input.comprador_input() or "").strip() or None
        valor_venda = _parse_valor_venda(input.valor_venda_input())

        try:
            await asyncio.to_thread(
                im.registrar_motivo_saida,
                ctx["cnpj_emp"],
                ctx["placa"],
                motivo,
                anexo_path,
                tipo_saida,
                tipo_saida_outro,
                comprador,
                valor_venda,
            )
        except Exception:
            logger.exception(f"Falha ao gravar motivo de saida da placa {ctx['placa']}")
            if anexo_path:
                try:
                    Path(anexo_path).unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning(f"Anexo orfao ficou em {anexo_path}: {exc}")
            ui.modal_show(modal_aviso("Erro ao gravar o motivo. Tente novamente.", tipo="error"), session=session)
            return

        versao_dados_vivos.set(versao_dados_vivos() + 1)
        contexto_motivo.set(None)
        ui.modal_remove(session=session)
        ui.modal_show(modal_aviso("Motivo enviado com sucesso.", tipo="success"), session=session)


def pag_frotas_saida_ui():
    return frota_saida_ui("frota_saida")


def pag_frotas_saida_server():
    frota_saida_server("frota_saida")
