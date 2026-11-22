import asyncio
import time
from datetime import date
from numbers import Real
from pathlib import Path
from urllib.parse import parse_qs

import pandas as pd
import polars as pl
from faicons import icon_svg
from loguru import logger
from shiny import module, reactive, render, ui

from core import exportar as exp
from core import revendas
from core.auth import identificar_usuario
from core.aviso import corpo_aviso, modal_aviso
from core.config import CHAVE_SUPREMO, pode
from core.cores import SIDEBAR_BG
from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.visibilidade import pagina_visivel

from .Dados import control_comodato as cc
from .Dados import dados_comodato as d
from .Dados import dados_pdf_comodato as dados_pdf
from .Dados import devolve_pedido as dp
from .Dados import funcao_extracao_doc as ocr
from .Dados import informa_comodato as ic
from .Dados import material_comodato as mc
from .Dados import pdf_distrato
from .Dados import reenvio_email as reenvio
from .Dados import tabela_comodato as ti

PASTA_APP = Path(__file__).parents[2]

ID_FILTRO_INTERVALO = "intervalo"

FILTROS_SELECT = [
    (ID_FILTRO_INTERVALO, "Intervalo", "Intervalo Vencimento"),
    ("produto", "Produto", "Produto"),
    ("inadimplencia", "Inadimplência", "Inadimplencia 60 dias +"),
    ("prazo", "Prazo", "Prazo do Input"),
    ("usuario", "Usuário", "Usuario"),
    ("status", "Status", "Status"),
    ("situacao_recolha", "Recolha", d.COLUNA_SITUACAO_RECOLHA),
]

CODCOMP_CAIXA_1L = ["690163", "555001"]
CODCOMP_CAIXA_300ML = ["551003", "551002", "551001", "546004", "061007"]
CODCOMP_CAIXA_600ML_MAR = ["587003", "587002"]
CODCOMP_CAIXA_600ML = ["808002", "808001", "550013", "550012", "550011", "550001"]

IMG_CAIXA_1L = "img/produtos/caixa_1l.svg"
IMG_CAIXA_300ML = "img/produtos/caixa_300ml.svg"
IMG_CAIXA_600ML_MAR = "img/produtos/caixa_600ml.svg"
IMG_CAIXA_600ML = IMG_CAIXA_1L
IMG_CARRINHO = "img/produtos/carrinho.svg"
IMG_HORIZONTAL = "img/produtos/horizontal.svg"
IMG_VERTICAL = "img/produtos/vertical.svg"
IMG_QUIOSQUE = "img/produtos/quiosque.svg"
IMG_GELAPLACA = "img/produtos/gelaplaca.svg"

_LARGURA_COMODATOS = {
    "Comp": 80,
    "NF": 80,
    "Cliente": 85,
    "Emissão": 95,
    "Venc": 95,
    "Intervalo\n(dias)": 80,
    "Qtd": 70,
    "Inad. 60\ndias +": 80,
    "Prazo": 85,
    "Ação": 60,
    "Doc": 60,
    "Cev": 60,
    "Can": 60,
    "Reenviar\nEmail": 60,
    "Recolha": 60,
    "CEV": 80,
    "Razão\nSocial": 100,
    "Usuario": 80,
    "Origem": 80,
    "Produto": 170,
}


_MENSAGEM_COBRANCA = (
    "Olá! O contrato de comodato do CEV {cev} foi enviado por e-mail e ainda está"
    " aguardando a sua assinatura. Pode conferir a caixa de entrada (e o spam) e"
    " assinar, por favor?"
)

_CAMPOS_ANEXO = {
    d.COLUNA_CANHOTO: ("anexo_canhoto", "Canhoto:"),
    d.COLUNA_CONTRATO: ("anexo_comodato", "Comodato:"),
    d.COLUNA_PDV: ("anexo_pdv", "Documento PDV:"),
}
_DOCUMENTO_DO_CAMPO = {campo: documento for documento, (campo, _rotulo) in _CAMPOS_ANEXO.items()}


def _campos_da_janela(
    manual: bool,
    exige_pdv: bool,
    tem_pdv: bool,
    tem_contrato: bool,
    tem_canhoto: bool,
    prazo_esgotado: bool,
) -> tuple[str, ...]:
    exigidos = [d.COLUNA_CANHOTO, d.COLUNA_CONTRATO] + ([d.COLUNA_PDV] if exige_pdv else [])
    entregues = {
        d.COLUNA_CANHOTO: tem_canhoto,
        d.COLUNA_CONTRATO: tem_contrato,
        d.COLUNA_PDV: tem_pdv,
    }
    faltando = [doc for doc in exigidos if not entregues[doc]]
    if not faltando:
        return tuple(exigidos)
    oferecidos = []
    for doc in faltando:
        if doc == d.COLUNA_CANHOTO and not (manual or tem_contrato or prazo_esgotado):
            continue
        if doc == d.COLUNA_CONTRATO and not (manual or prazo_esgotado):
            continue
        oferecidos.append(doc)
    return tuple(oferecidos)


def _filtro_ui(id_filtro: str, rotulo: str) -> ui.Tag:
    return ui.div(
        ui.input_selectize(
            id_filtro,
            rotulo,
            choices=[],
            multiple=True,
            options={
                "placeholder": "Todos",
                "dropdownParent": "body",
                "dropdownClass": "selectize-dropdown comod-selectize-dropdown",
                "hideSelected": False,
                "plugins": ["remove_button"],
            },
        ),
        class_="filtro-comod",
    )


def _numero_cev(cev: str) -> str:
    return cev.rsplit("-", 1)[-1].strip()


def _nome_usuario(usuario: str) -> str:
    return " ".join(parte.capitalize() for parte in usuario.split("."))


def _campo_so_leitura(id_campo: str, rotulo: str, valor: str) -> ui.Tag:
    return (
        ui.input_text(id_campo, rotulo, value=valor, width="100%")
        .add_style("pointer-events: none;")
        .add_class("comod-campo-leitura comod-modal-claro")
    )


def _corpo_aguarde(titulo: str, motivo: str) -> ui.Tag:
    return ui.div(
        ui.div(class_="comod-aviso-girando"),
        ui.div(titulo, class_="aviso-titulo"),
        ui.div(motivo, class_="aviso-texto"),
        class_="aviso-corpo",
    )


def _card(rotulo: str, valor, icone_fa: str | None = None, imagem: str | None = None) -> ui.Tag:
    if imagem:
        icone = ui.img(src=imagem, class_="icone-resumo-comod")
    elif icone_fa:
        icone = icon_svg(icone_fa, a11y="deco", width="34px", height="34px", margin_left="0", margin_right="0")
    else:
        icone = None
    valor_exibido = int(valor) if isinstance(valor, Real) and not isinstance(valor, bool) else valor
    return ui.div(
        icone,
        ui.div(
            ui.div(str(valor_exibido), class_="valor-resumo-comod"),
            ui.div(rotulo, class_="rotulo-resumo-comod"),
        ),
        class_="card-resumo-comod",
    )


@module.ui
def comodatos_ui():
    return ui.div(
        ui.card(
            ui.div(
                ui.div(
                    ui.input_text("pesquisa", "Pesquisar CEV", placeholder="CEV, cliente ou fantasia..."),
                    class_="filtro-comod",
                ),
                *[_filtro_ui(id_filtro, rotulo) for id_filtro, rotulo, _coluna in FILTROS_SELECT],
                ui.input_action_button(
                    "limpar",
                    None,
                    icon=icon_svg("eraser", a11y="deco"),
                    class_="btn-primary btn-limpar-comod",
                    title="Limpar filtros",
                ),
                class_="filtros-comod",
            ),
        ),
        ui.output_ui("cards_resumo"),
        ui.card(
            ui.card_header(
                ui.div(
                    ui.span("CEVs"),
                    ui.download_button(
                        "exportar",
                        None,
                        icon=icon_svg("file-excel", a11y="deco"),
                        class_="btn-success btn-sm",
                        title="Baixar em Excel o que está filtrado",
                    ),
                    class_="d-flex justify-content-between align-items-center w-100",
                )
            ),
            ui.output_ui("corpo_tabela_comodatos"),
        ),
        ui.div(
            ui.output_ui("painel_produtos_cev"),
            id="comod_produtos_panel",
            class_="comod-produtos-panel",
            onmouseenter="window.comodProdutosCancelarOcultar && window.comodProdutosCancelarOcultar()",
            onmouseleave="window.comodProdutosOcultar && window.comodProdutosOcultar()",
        ),
        class_="comodatos-modulo",
    )


@module.server
def comodatos_server(input, output, session, valor_navset: str, versao_cache):
    @reactive.calc
    def revenda_atual() -> str | None:
        query_string = session.clientdata.url_search()
        valores = parse_qs(query_string.lstrip("?")).get("REVENDA")
        if valores:
            return valores[0]
        # Portfólio: sem a URL do portal, vale a revenda escolhida no cabeçalho.
        raiz = session.root_scope().input
        return (raiz.revenda_escolhida() if "revenda_escolhida" in raiz else "Natal") or None

    @reactive.calc
    async def usuario_atual() -> str:
        usuario, _script_cache = await asyncio.to_thread(identificar_usuario, session.root_scope().http_conn)
        return usuario

    @reactive.calc
    async def pode_recolha() -> bool:
        return pode(await usuario_atual(), "recolha_comodato")

    @reactive.calc
    async def acesso_supremo() -> bool:
        return pode(await usuario_atual(), CHAVE_SUPREMO)

    @reactive.calc
    async def pode_enviar_bloqueado() -> bool:
        return pode(await usuario_atual(), "envio_sem_bloqueio")

    @reactive.calc
    async def reenvio_ilimitado() -> bool:
        return pode(await usuario_atual(), "reenvio_ilimitado")

    async def pode_reenviar() -> bool:
        return pode(await usuario_atual(), "reenvio_email")

    refresh_comod = reactive.value(0, name="refresh_comod")

    async def _recolhas_geral_segura(revenda: str) -> pl.DataFrame:
        try:
            return await asyncio.to_thread(d.recolhas_geral, revenda)
        except Exception:
            logger.exception(f"Falha ao consultar TB_COMOD_RECOLHA para revenda {revenda}")
            return d.recolhas_vazias()

    @reactive.calc
    async def comodatos_geral() -> pl.DataFrame:
        refresh_comod()
        versao_cache()
        revenda = revenda_atual() or "HOLDING"
        base, recolhas = await asyncio.gather(
            asyncio.to_thread(d.comod_geral, revenda),
            _recolhas_geral_segura(revenda),
        )
        return d.adicionar_status_recolha(base, recolhas)

    @reactive.calc
    async def base_filtrada() -> pl.DataFrame:
        base = await comodatos_geral()
        if base.height == 0:
            return base
        if input.pesquisa():
            base = base.filter(pl.col("PesquisaCev").str.to_lowercase().str.contains(input.pesquisa().lower()))
        for id_filtro, _rotulo, coluna in FILTROS_SELECT:
            valores = input[id_filtro]()
            if not valores or coluna not in base.columns:
                continue
            if id_filtro == ID_FILTRO_INTERVALO:
                base = base.filter(d.expr_faixa_intervalo(coluna).is_in(list(valores)))
                continue
            base = base.filter(pl.col(coluna).cast(pl.Utf8).is_in(list(valores)))
        return base

    @reactive.effect
    async def _atualiza_opcoes_filtro():
        if not pagina_visivel(session, valor_navset):
            return
        base = await comodatos_geral()
        for id_filtro, _rotulo, coluna in FILTROS_SELECT:
            if input[id_filtro]() or coluna not in base.columns:
                continue
            if id_filtro == ID_FILTRO_INTERVALO:
                presentes = set(base.select(d.expr_faixa_intervalo(coluna))[:, 0].to_list()) if base.height else set()
                opcoes = [faixa for faixa in d.FAIXAS_INTERVALO if faixa in presentes]
            else:
                opcoes = (
                    sorted(v for v in base[coluna].cast(pl.Utf8).unique().to_list() if v is not None)
                    if base.height
                    else []
                )
            ui.update_selectize(id_filtro, choices=opcoes, session=session)

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar_filtros():
        ui.update_text("pesquisa", value="", session=session)
        for id_filtro, _rotulo, _coluna in FILTROS_SELECT:
            ui.update_selectize(id_filtro, selected=[], session=session)

    @render.ui
    async def cards_resumo():
        base = await base_filtrada()
        if base.height == 0:
            return None
        eh_especial = (revenda_atual() or "").upper() == "ESPECIAL"

        prazo_dias = base.filter(pl.col("Prazo do Input").str.contains("dias restantes"))
        prazo_minimo = (
            prazo_dias.with_columns(pl.col("Prazo do Input").str.extract(r"(-?\d+)").cast(pl.Int64).alias("_dias"))[
                "_dias"
            ].min()
            if prazo_dias.height
            else None
        )
        inadimplentes = base.filter(pl.col("Inadimplencia 60 dias +") == "Sim")["CEV"].n_unique()
        qtd_cevs = base["CEV"].n_unique()

        cartoes = [
            _card("Prazo mais curto", f"{prazo_minimo} dias" if prazo_minimo is not None else "-", icone_fa="clock"),
            _card("Clientes inadimplentes", inadimplentes, icone_fa="users-slash"),
            _card("Quantidade de CEV's", qtd_cevs, icone_fa="file-signature"),
        ]
        if eh_especial:
            for rotulo, regex, imagem in [
                ("Carrinho", r"Carrinho|Ambulante", IMG_CARRINHO),
                ("Horizontal", r"Horizontal", IMG_HORIZONTAL),
                ("Vertical", r"Vertical", IMG_VERTICAL),
                ("Quiosque", r"Quiosque", IMG_QUIOSQUE),
                ("Gelaplaca", r"Gelaplaca", IMG_GELAPLACA),
            ]:
                qtd = base.filter(pl.col("Produto").str.contains(regex))["Qtd"].sum() or 0
                cartoes.append(_card(rotulo, qtd, imagem=imagem))
        else:
            for rotulo, codigos, imagem in [
                ("Qtd Caixa 1L", CODCOMP_CAIXA_1L, IMG_CAIXA_1L),
                ("Qtd Caixa 300ML", CODCOMP_CAIXA_300ML, IMG_CAIXA_300ML),
                ("Qtd Caixa 600ML MAR", CODCOMP_CAIXA_600ML_MAR, IMG_CAIXA_600ML_MAR),
                ("Qtd Caixa 600ML", CODCOMP_CAIXA_600ML, IMG_CAIXA_600ML),
            ]:
                qtd = base.filter(pl.col("CODCOMP").cast(pl.Utf8).is_in(codigos))["Qtd"].sum() or 0
                cartoes.append(_card(rotulo, qtd, imagem=imagem))

        return ui.div(*cartoes, class_="cards-resumo-comod-linha")

    @reactive.calc
    async def comodatos_agrupados() -> tuple[pd.DataFrame, list[dict], pl.DataFrame]:
        base = await base_filtrada()
        if base.height == 0:
            return pd.DataFrame(), [], base
        liberado = await pode_reenviar()
        envios = await asyncio.to_thread(d.contar_envios_email_por_cev) if liberado else {}
        fechado, estilos = await asyncio.to_thread(
            ti.construir_comodatos_df,
            base,
            envios,
            await pode_recolha(),
            liberado,
            await acesso_supremo(),
            await reenvio_ilimitado(),
            await pode_enviar_bloqueado(),
        )
        return fechado, estilos, base

    @reactive.calc
    async def tabela_comodatos_pronta() -> tuple[pd.DataFrame, list[dict]]:
        fechado, estilos, base = await comodatos_agrupados()
        if fechado.empty:
            return fechado, estilos
        return await asyncio.to_thread(
            ti.expandir_comodatos_df,
            fechado,
            estilos,
            base,
            (),
            revenda_atual() is None,
        )

    @reactive.effect
    async def _contar_linhas_download():
        if not pagina_visivel(session, valor_navset):
            return
        try:
            base = await base_filtrada()
        except Exception as exc:
            logger.warning(f"Comodatos: nao deu pra medir o tamanho do download -- {exc}")
            return
        linhas_download.set(base.height)

    @reactive.calc
    async def _tem_comodatos() -> bool:
        fechado, _estilos, _base = await comodatos_agrupados()
        return not fechado.empty

    @render.ui
    async def corpo_tabela_comodatos():
        if not await _tem_comodatos():
            return ui.p("Sem dados para os filtros selecionados.")
        return ui.div(
            ui.output_ui("css_largura_tabela_comodatos"),
            ui.output_data_frame("tabela_comodatos"),
            class_="comod-tabela tabela-resize",
        )

    @render.data_frame
    async def tabela_comodatos():
        pandas_df, estilos = await tabela_comodatos_pronta()
        return render.DataTable(
            pandas_df, styles=estilos, height="58vh", summary=False, filters=False, selection_mode="none"
        )

    linhas_download = reactive.value(0, name="linhas_download_comod")

    def _nome_download() -> str:
        return f"comodatos-{date.today().isoformat()}.{exp.formato_para(linhas_download())}"

    @render.download_button(filename=_nome_download)
    async def exportar():
        base = await base_filtrada()
        envios = await asyncio.to_thread(d.contar_envios_email_por_cev) if await pode_reenviar() else {}
        tabela = await asyncio.to_thread(
            ti.construir_comodatos_download_df,
            base,
            envios,
            await pode_recolha(),
            await pode_reenviar(),
            await acesso_supremo(),
            await reenvio_ilimitado(),
            await pode_enviar_bloqueado(),
            revenda_atual() is None,
        )
        caminho = await asyncio.to_thread(exp.gerar, tabela, "comodatos", exp.formato_para(tabela.height))
        for pedaco in exp.enviar(caminho):
            yield pedaco

    async def _itens_do_cev(chave: str) -> pl.DataFrame:
        _fechado, _estilos, base = await comodatos_agrupados()
        return ti.itens_do_cev(base, chave) if base.height else base

    @render.ui
    async def painel_produtos_cev():
        if "cev_hover" not in input:
            return None
        chave = str(input.cev_hover() or "").strip()
        if not chave:
            return None
        itens = await _itens_do_cev(chave)
        return ui.TagList(
            ui.div(f"CEV {_numero_cev(chave)}", class_="comod-produtos-titulo"),
            ui.HTML(ti.tabela_itens_html(itens, com_foto_generica=True)),
        )

    @reactive.effect
    @reactive.event(input.clique_linha_cev)
    async def _abrir_modal_produtos():
        chave = str((input.clique_linha_cev() or {}).get("chave_cev") or "").strip()
        if not chave:
            return
        itens = await _itens_do_cev(chave)
        if itens.height == 0:
            return
        primeira = itens.row(0, named=True)
        fotos = await asyncio.to_thread(
            mc.fotos_por_item,
            str(primeira.get("cnpj") or ""),
            str(primeira.get("Cliente") or ""),
            [linha.get("CODCOMP") for linha in itens.iter_rows(named=True)],
        )
        cliente = str(primeira.get("Razão Social") or primeira.get("Fantasia") or "").strip()
        ui.modal_show(
            ui.modal(
                ui.div(cliente, class_="comod-produtos-cliente") if cliente else None,
                ui.HTML(ti.tabela_itens_html(itens, com_foto_generica=False, fotos_salvas=fotos)),
                title=f"Itens do CEV {_numero_cev(chave)}",
                size="l",
                easy_close=True,
                footer=ui.modal_button("Fechar", class_="btn-sm"),
            ),
            session=session,
        )

    @reactive.calc
    async def _colunas_comodatos() -> tuple[str, ...]:
        fechado, _estilos, _base = await comodatos_agrupados()
        return tuple(fechado.columns)

    @render.ui
    async def css_largura_tabela_comodatos():
        larguras = [ColunaLargura(c, _LARGURA_COMODATOS.get(c, 100)) for c in await _colunas_comodatos()]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_comodatos')}", larguras))

    contexto_acao = reactive.value(None, name="contexto_acao")
    _anexo_em_curso: dict[str, bool] = {"ativo": False}

    async def _linha_cev(chave_cev: str) -> dict | None:
        base = await comodatos_geral()
        encontrada = base.filter(pl.col("CEV") == chave_cev)
        if encontrada.height == 0:
            return None
        return encontrada.row(0, named=True)

    @reactive.effect
    @reactive.event(input.clique_acao)
    async def _tratar_clique_acao():
        dados = input.clique_acao()
        linha = await _linha_cev(dados["chave_cev"])
        if linha is None:
            return
        emoji = linha.get("Acao")
        if emoji == "\u2705":
            return
        base = await comodatos_geral()
        prazo_esgotado = d.cev_prazo_esgotado(base, dados["chave_cev"])
        tem_pdv = ic.tem_anexo(linha.get("anexo1"))
        tem_contrato = ic.tem_anexo(linha.get("anexo2"))
        tem_canhoto = ic.tem_anexo(linha.get("anexo3"))
        if prazo_esgotado and not d.envio_apos_prazo_liberado(tem_contrato) and not await pode_enviar_bloqueado():
            return
        manual = d.cev_fluxo_manual(base, dados["chave_cev"])
        exige_pdv = d.cev_exige_documento_pdv(base, dados["chave_cev"])
        campos = _campos_da_janela(manual, exige_pdv, tem_pdv, tem_contrato, tem_canhoto, prazo_esgotado)
        substituindo = tem_contrato and tem_canhoto and (tem_pdv or not exige_pdv)
        numero_cev = _numero_cev(str(linha.get("CEV") or dados["chave_cev"]))
        contexto_acao.set(
            {
                "ncev": numero_cev,
                "chave_cev": dados["chave_cev"],
                "cnpj_emp": linha.get("cnpj"),
                "codcli": linha.get("Cliente"),
                "nf": linha.get("NF"),
                "exige_pdv": exige_pdv,
                "tem_contrato": tem_contrato,
                "tem_canhoto": tem_canhoto,
                "campos": campos,
            }
        )
        whatsapp, proprietario = "", ""
        if not campos:
            proprietario, fone, _ = await asyncio.to_thread(d.contato_cliente, linha.get("Cliente"), linha.get("cnpj"))
            whatsapp = d.url_whatsapp(fone, _MENSAGEM_COBRANCA.format(cev=numero_cev))
        validacao_anexos.set({})
        aviso_validacao.set(None)
        _conferidos.clear()
        ui.modal_show(
            _modal_upload(
                linha,
                await usuario_atual(),
                campos,
                substituindo,
                whatsapp,
                proprietario,
                exige_validacao=not await pode_enviar_bloqueado(),
            ),
            session=session,
        )

    estado_reenvio = reactive.value(None, name="estado_reenvio")
    _reenvio_em_curso: dict[str, object] = {"ativo": False, "tarefa": None}

    @reactive.effect
    @reactive.event(input.clique_reenviar)
    async def _tratar_clique_reenviar():
        if not await pode_reenviar():
            return
        dados = input.clique_reenviar()
        chave_cev = str(dados.get("chave_cev") or "")
        envios = int(dados.get("envios") or 0)
        envios_tela = int(dados.get("envios_tela") or 0)
        linha = await _linha_cev(chave_cev)
        if linha is None:
            return
        if envios_tela >= ti.LIMITE_REENVIO_EMAIL and not (await reenvio_ilimitado() or await acesso_supremo()):
            estado_reenvio.set(
                {
                    "etapa": "resultado",
                    "cev": chave_cev,
                    "ok": False,
                    "titulo": "Limite de envio atingido",
                    "texto": f"O CEV {_numero_cev(chave_cev)} já usou o envio disponível por esta tela."
                    " Para enviar de novo, entre em contato com o suporte.",
                }
            )
        else:
            disponivel, motivo = reenvio.disponivel()
            if not disponivel:
                estado_reenvio.set(
                    {
                        "etapa": "resultado",
                        "cev": chave_cev,
                        "ok": False,
                        "titulo": "Envio indisponível",
                        "texto": motivo,
                    }
                )
            else:
                _, _, email_destino = await asyncio.to_thread(
                    d.contato_cliente, linha.get("Cliente"), linha.get("cnpj")
                )
                estado_reenvio.set(
                    {
                        "etapa": "confirmar",
                        "cev": chave_cev,
                        "envios": envios,
                        "envios_tela": envios_tela,
                        "cnpj": str(linha.get("cnpj") or ""),
                        "cliente": str(linha.get("Razão Social") or linha.get("Cliente") or ""),
                        "email": email_destino,
                    }
                )
        ui.modal_show(_modal_reenvio(), session=session)

    def _modal_reenvio() -> ui.Tag:
        return ui.modal(
            ui.output_ui("corpo_reenvio"),
            title=None,
            size="s",
            easy_close=False,
            footer=None,
        )

    @render.ui
    def corpo_reenvio():
        estado = estado_reenvio()
        if estado is None:
            return None
        if estado["etapa"] == "confirmar":
            reenvio_de_verdade = int(estado.get("envios") or 0) > 0
            verbo = "reenviar" if reenvio_de_verdade else "enviar"
            sobra = max(ti.LIMITE_REENVIO_EMAIL - int(estado.get("envios_tela") or 0) - 1, 0)
            cliente = str(estado.get("cliente") or "").strip()
            email = str(estado.get("email") or "").strip()
            return ui.TagList(
                corpo_aviso(
                    f"Deseja realmente {verbo} o comodato do CEV {_numero_cev(estado['cev'])}"
                    + (f" para {cliente}?" if cliente else "?")
                    + f" Cada envio é cobrado pelo serviço de assinatura, e depois deste"
                    f" {'resta' if sobra == 1 else 'restam'} {sobra} envio"
                    f"{'' if sobra == 1 else 's'}.",
                    titulo="Confirmar reenvio?" if reenvio_de_verdade else "Confirmar envio?",
                    tipo="warning",
                ),
                ui.div(
                    ui.tags.b("Vai para: "),
                    email,
                    class_="comod-confirma-email",
                )
                if email
                else ui.div(
                    "O responsável deste comodato está sem e-mail cadastrado no ERP,"
                    " então o envio não vai sair. Corrija o cadastro e use o Atualizar.",
                    class_="comod-confirma-email text-danger",
                ),
                ui.div(
                    ui.input_action_button("bt_confirma_reenvio", "Sim", class_="btn-sm comod-btn-confirmar"),
                    ui.input_action_button("bt_fecha_reenvio", "Não", class_="btn-sm"),
                    class_="d-flex justify-content-center gap-2",
                ),
            )
        if estado["etapa"] == "enviando":
            return _corpo_aguarde(
                "Enviando...",
                estado.get("texto") or "Gerando o comodato e enviando o email.",
            )
        return ui.TagList(
            corpo_aviso(estado["texto"], titulo=estado["titulo"], tipo="success" if estado["ok"] else "error"),
            ui.div(
                ui.input_action_button("bt_fecha_reenvio", "OK", class_="btn-sm comod-btn-confirmar"),
                class_="text-center",
            ),
        )

    @reactive.effect
    @reactive.event(input.bt_confirma_reenvio)
    async def _confirmar_reenvio():
        if not await pode_reenviar():
            return
        estado = estado_reenvio()
        if estado is None or estado.get("etapa") != "confirmar":
            return
        if _reenvio_em_curso["ativo"]:
            return
        _reenvio_em_curso["ativo"] = True
        estado_reenvio.set({**estado, "etapa": "enviando"})
        _reenvio_em_curso["tarefa"] = asyncio.create_task(_executar_reenvio(estado["cev"], estado.get("cnpj", "")))

    async def _executar_reenvio(chave_cev: str, cnpj: str) -> None:
        if not await pode_reenviar():
            logger.warning(f"Comodatos: reenvio do CEV {chave_cev} barrado por falta de permissao")
            _reenvio_em_curso["ativo"] = False
            return
        try:
            dona = revendas.por_cnpj(cnpj)
            ok, mensagem, restantes = await reenvio.reenviar(
                _numero_cev(chave_cev), cnpj, dona.nome if dona else "", await usuario_atual(), executar=True
            )
            if ok and restantes is not None:
                mensagem = f"{mensagem}. Envios restantes: {restantes}."
            titulo = "Email enviado" if ok else "Não foi possível enviar"
        except Exception as exc:
            logger.warning(f"Comodatos: falha no reenvio do CEV {chave_cev} -- {exc}")
            ok, titulo = False, "Não foi possível enviar"
            mensagem = "Algo deu errado ao enviar. Tente de novo em instantes."
        finally:
            _reenvio_em_curso["ativo"] = False
        try:
            async with reactive.lock():
                with reactive.isolate():
                    estado_reenvio.set(
                        {
                            "etapa": "resultado",
                            "cev": chave_cev,
                            "ok": ok,
                            "titulo": titulo,
                            "texto": mensagem,
                        }
                    )
                    if ok:
                        refresh_comod.set(refresh_comod() + 1)
                await reactive.flush()
        except Exception as exc:
            logger.warning(f"Comodatos: nao deu pra mostrar o resultado do reenvio -- {exc}")

    @reactive.effect
    @reactive.event(input.bt_fecha_reenvio)
    def _fechar_reenvio():
        estado_reenvio.set(None)
        ui.modal_remove(session=session)

    validacao_anexos = reactive.value({}, name="validacao_anexos")
    aviso_validacao = reactive.value(None, name="aviso_validacao")
    _conferidos: dict[str, tuple] = {}
    _conferencia_anexo: dict[str, object] = {}

    def _parar_conferencia_ao_fechar() -> None:
        tarefa = _conferencia_anexo.get("tarefa")
        if tarefa is not None and not tarefa.done():
            tarefa.cancel()

    session.on_ended(_parar_conferencia_ao_fechar)

    def _corpo_analisando(titulo: str, motivo: str) -> ui.Tag:
        return ui.div(
            ui.div(class_="comod-aviso-girando"),
            ui.div(titulo, class_="aviso-titulo"),
            ui.div(motivo, class_="aviso-texto"),
            class_="aviso-corpo",
        )

    APROVADO_SEM_CONFERIR = "Documento conferido."
    _CAMPO_NO_LOG = {"anexo1": "PDV", "anexo2": "Comodato", "anexo3": "Canhoto"}

    def _registrar_conferencia(
        chave_cev: str, usuario: str, documento: str, inicio: float, extraido: dict, resultado: str
    ) -> None:
        logger.info(
            f"Comodatos: conferencia do anexo -- CEV {chave_cev} | {_CAMPO_NO_LOG.get(documento, documento)}"
            f" | usuario {usuario or '-'} | esperado {ocr.TIPO_ESPERADO_POR_DOCUMENTO.get(documento) or '-'}"
            f" | lido {extraido.get('tipo_normalizado') or extraido.get('tipo_documento') or '-'}"
            f" | leitura {extraido.get('motor') or '-'} | {time.time() - inicio:.1f}s | {resultado}"
        )

    def _resultado_anexo(documento: str, caminho: str, nome: str, chave_cev: str = "", usuario: str = "") -> dict:
        inicio = time.time()
        if len(nome) > ic.LIMITE_NOME_ARQUIVO:
            _registrar_conferencia(chave_cev, usuario, documento, inicio, {}, "RECUSADO (nome do arquivo longo)")
            return {
                "ok": False,
                "mensagem": (
                    f"Nome muito longo ({len(nome)} caracteres). Renomeie o arquivo para"
                    f" até {ic.LIMITE_NOME_ARQUIVO} caracteres e envie de novo."
                ),
            }
        try:
            extraido = ocr.extrair_doc(caminho, ocr.TIPO_ESPERADO_POR_DOCUMENTO.get(documento))
        except Exception as exc:
            logger.warning(f"Comodatos: falha ao conferir o anexo {nome} -- {exc}")
            _registrar_conferencia(chave_cev, usuario, documento, inicio, {}, "LIBERADO SEM CONFERIR (erro na leitura)")
            return {"ok": True, "mensagem": APROVADO_SEM_CONFERIR}
        if extraido.get("api_offline"):
            _registrar_conferencia(
                chave_cev, usuario, documento, inicio, extraido, "LIBERADO SEM CONFERIR (a leitura nao reconheceu nada)"
            )
            return {"ok": True, "mensagem": APROVADO_SEM_CONFERIR}
        tipo = extraido.get("tipo_documento")
        if ocr.documento_confere(extraido, documento):
            _registrar_conferencia(chave_cev, usuario, documento, inicio, extraido, "APROVADO")
            return {"ok": True, "mensagem": f"{tipo} -- confere."}
        esperado = ocr.NOME_AMIGAVEL.get(documento, "outro documento")
        _registrar_conferencia(
            chave_cev,
            usuario,
            documento,
            inicio,
            extraido,
            "RECUSADO (tipo nao confere)" if tipo else "RECUSADO (a leitura nao reconheceu nada)",
        )
        if not tipo:
            return {
                "ok": False,
                "mensagem": f"Não foi possível identificar o documento. Este campo espera {esperado}.",
            }
        return {"ok": False, "mensagem": f"Isto parece ser {tipo}. Este campo espera {esperado}."}

    async def _conferir_anexos(escolhidos: dict, chave_cev: str = "") -> None:
        try:
            try:
                usuario = await usuario_atual()
            except Exception:
                usuario = ""
            resultados: dict[str, dict] = {}
            total = len(escolhidos)
            for posicao, (id_campo, (documento, caminho, nome)) in enumerate(escolhidos.items(), start=1):
                if total > 1:
                    async with reactive.lock():
                        with reactive.isolate():
                            aviso_validacao.set(
                                {
                                    "tipo": "analisando",
                                    "titulo": "Aguarde...",
                                    "texto": f"Conferindo o documento {posicao} de {total}.",
                                }
                            )
                        await reactive.flush()
                resultados[id_campo] = await asyncio.to_thread(
                    _resultado_anexo, documento, caminho, nome, chave_cev, usuario
                )
            aprovado = all(r["ok"] for r in resultados.values())
            recusados = [r["mensagem"] for r in resultados.values() if not r["ok"]]
            async with reactive.lock():
                with reactive.isolate():
                    validacao_anexos.set(resultados)
                    aviso_validacao.set(
                        None
                        if aprovado
                        else {
                            "tipo": "warning",
                            "titulo": "Documento não confere",
                            "texto": f"Confira o que está marcado em vermelho abaixo dos campos. {recusados[0]}"
                            if recusados
                            else "",
                        }
                    )
                ui.update_action_button("bt_envia_anexo", disabled=not aprovado, session=session)
                await reactive.flush()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"Comodatos: nao deu pra mostrar o resultado da conferencia -- {exc}")

    @reactive.effect
    async def _validar_anexos_escolhidos():
        ctx = contexto_acao()
        if ctx is None:
            return
        campos_janela = [_CAMPOS_ANEXO[doc] for doc in ctx.get("campos", ())]
        if not campos_janela:
            return
        escolhidos = {}
        for id_campo, _rotulo in campos_janela:
            if id_campo not in input:
                return
            try:
                entrada = input[id_campo]()
            except Exception:
                return
            if not entrada:
                return
            arquivo = entrada[0]
            escolhidos[id_campo] = (
                _DOCUMENTO_DO_CAMPO[id_campo],
                arquivo["datapath"],
                arquivo["name"],
            )
        assinatura = tuple((c, v[2]) for c, v in escolhidos.items())
        if _conferidos.get("conjunto") == assinatura:
            return
        _conferidos["conjunto"] = assinatura
        if await pode_enviar_bloqueado():
            return
        aviso_validacao.set(
            {
                "tipo": "analisando",
                "titulo": "Aguarde...",
                "texto": "Conferindo o documento enviado."
                if len(escolhidos) == 1
                else f"Conferindo os {len(escolhidos)} documentos enviados.",
            }
        )
        ui.update_action_button("bt_envia_anexo", disabled=True, session=session)
        anterior = _conferencia_anexo.get("tarefa")
        if anterior is not None and not anterior.done():
            anterior.cancel()
        _conferencia_anexo["tarefa"] = asyncio.create_task(
            _conferir_anexos(escolhidos, str(ctx.get("chave_cev") or ctx.get("ncev") or ""))
        )

    def _feedback_campo(id_campo: str) -> ui.Tag | None:
        resultado = validacao_anexos().get(id_campo)
        if not resultado:
            return None
        cor = "text-success" if resultado["ok"] else "text-danger"
        return ui.div(resultado["mensagem"], class_=f"{cor} comod-feedback-campo")

    @render.ui
    def val_anexo_canhoto():
        return _feedback_campo("anexo_canhoto")

    @render.ui
    def val_anexo_comodato():
        return _feedback_campo("anexo_comodato")

    @render.ui
    def val_anexo_pdv():
        return _feedback_campo("anexo_pdv")

    @render.ui
    def aviso_validacao_ui():
        aviso = aviso_validacao()
        if not aviso:
            return None
        if aviso["tipo"] == "analisando":
            corpo = _corpo_analisando(aviso["titulo"], aviso["texto"])
        else:
            corpo = corpo_aviso(aviso["texto"], titulo=aviso["titulo"], tipo=aviso["tipo"])
        return ui.div(
            corpo,
            ui.input_action_button("bt_fecha_aviso_validacao", "Entendi", class_="btn-sm comod-btn-confirmar")
            if aviso["tipo"] != "analisando"
            else None,
            class_="comod-aviso-sobreposto",
        )

    @reactive.effect
    @reactive.event(input.bt_fecha_aviso_validacao)
    def _fechar_aviso_validacao():
        aviso_validacao.set(None)

    def _campo_arquivo(id_campo: str, rotulo: str) -> ui.Tag:
        return ui.TagList(
            ui.input_file(
                id_campo,
                rotulo,
                button_label="Procurar...",
                placeholder="",
                accept=[".pdf", ".jpg", ".jpeg", ".png"],
            ),
            ui.output_ui(f"val_{id_campo}"),
        )

    def _botao_whatsapp(url: str, nome: str) -> ui.Tag | None:
        if not url:
            return None
        alvo = f" com {nome}" if nome else ""
        return ui.tags.a(
            icon_svg("whatsapp", a11y="deco", margin_left="0", margin_right="0"),
            href=url,
            target="_blank",
            rel="noopener",
            class_="btn btn-sm comod-btn-whatsapp",
            title=f"Cobrar a assinatura pelo WhatsApp{alvo}",
        )

    def _linha_anexos(
        campos: tuple[str, ...],
        tem_whatsapp: bool = False,
        substituindo: bool = False,
        exige_validacao: bool = True,
    ) -> ui.Tag:
        if campos:
            colunas = [ui.column(4, _campo_arquivo(*_CAMPOS_ANEXO[doc])) for doc in campos]
            if len(colunas) < 3:
                colunas.append(ui.column(12 - 4 * len(colunas)))
            linha = ui.row(*colunas)
            if exige_validacao:
                quantos = "do documento" if len(campos) == 1 else f"dos {len(campos)} documentos"
                linha = ui.TagList(
                    linha,
                    ui.p(
                        f"A conferência {quantos} começa depois de escolher"
                        f" {'o arquivo' if len(campos) == 1 else 'todos os arquivos'}."
                        " O envio libera quando tudo estiver certo.",
                        class_="comod-aviso-conferencia",
                    ),
                )
            if not substituindo:
                return linha
            return ui.TagList(
                corpo_aviso(
                    "Este comodato já está com todos os documentos gravados. O que for"
                    " enviado aqui substitui o arquivo atual.",
                    titulo="Documentação completa",
                    tipo="warning",
                ),
                linha,
            )
        if tem_whatsapp:
            saida = (
                "Enquanto isso, dá para cobrar o proprietário pelo WhatsApp (botão ao"
                " lado da Razão Social) ou enviar o e-mail de assinatura pela coluna"
                ' "Reenviar Email" da tabela.'
            )
        else:
            saida = (
                "Enquanto isso, dá para enviar o e-mail de assinatura pela coluna"
                ' "Reenviar Email" da tabela. Não há botão de WhatsApp porque este'
                " cliente está sem telefone válido no cadastro do ERP."
            )
        return corpo_aviso(
            "O contrato deste comodato ainda não foi assinado. Assim que a assinatura"
            f" chegar, o canhoto poderá ser anexado aqui. {saida}",
            titulo="Aguardando o contrato assinado",
            tipo="warning",
        )

    def _modal_upload(
        linha: dict,
        usuario: str,
        campos: tuple[str, ...] = (),
        substituindo: bool = False,
        whatsapp: str = "",
        proprietario: str = "",
        exige_validacao: bool = True,
    ) -> ui.Tag:
        pode_enviar = bool(campos)
        botao_zap = _botao_whatsapp(whatsapp, proprietario)
        return ui.modal(
            ui.output_ui("aviso_validacao_ui"),
            ui.row(
                ui.column(
                    8,
                    ui.div(
                        _campo_so_leitura("upload_razao_social", "Razão Social:", str(linha.get("Razão Social") or "")),
                        botao_zap,
                        class_="comod-linha-razao",
                    )
                    if botao_zap
                    else _campo_so_leitura(
                        "upload_razao_social", "Razão Social:", str(linha.get("Razão Social") or "")
                    ),
                    _campo_so_leitura("upload_cev", "Nº CEV:", _numero_cev(str(linha.get("CEV") or ""))),
                    _campo_so_leitura("upload_usuario", "Usuário:", _nome_usuario(usuario)),
                    ui.row(
                        ui.column(
                            4,
                            ui.input_date(
                                "data_conferencia_comod",
                                "Data de conferência:",
                                value=date.today(),
                                format="dd/mm/yyyy",
                                language="pt-BR",
                            ),
                        ),
                        ui.column(8),
                    ),
                    _linha_anexos(campos, botao_zap is not None, substituindo, exige_validacao),
                    ui.row(
                        ui.column(
                            12,
                            ui.input_action_button(
                                "bt_envia_anexo",
                                "Enviar",
                                class_="btn-sm comod-btn-confirmar",
                                disabled=exige_validacao,
                            ),
                            class_="text-center",
                        ),
                    )
                    if pode_enviar
                    else None,
                ),
                ui.column(4, ui.img(src="img/comodato_capa.svg", class_="comod-modal-capa")),
                style="align-items: flex-start;",
            ),
            title=ui.div("Comodato", style=f"color: {SIDEBAR_BG}"),
            size="xl",
            easy_close=True,
            footer=None,
        )

    @reactive.effect
    @reactive.event(input.bt_envia_anexo)
    async def _enviar_anexos():
        ctx = contexto_acao()
        if ctx is None:
            return

        def _arquivo(id_campo: str):
            if id_campo not in input:
                return (None, None)
            try:
                entrada = input[id_campo]()
            except Exception:
                return (None, None)
            return (entrada[0]["datapath"], entrada[0]["name"]) if entrada else (None, None)

        canhoto_path, canhoto_nome = _arquivo("anexo_canhoto")
        comodato_path, comodato_nome = _arquivo("anexo_comodato")
        pdv_path, pdv_nome = _arquivo("anexo_pdv")
        if not any((canhoto_path, comodato_path, pdv_path)):
            ui.modal_show(modal_aviso("Escolha pelo menos um arquivo para enviar.", tipo="warning"), session=session)
            return

        if not await pode_enviar_bloqueado():
            resultados = validacao_anexos()
            escolhidos = [
                id_campo
                for id_campo, caminho in (
                    ("anexo_canhoto", canhoto_path),
                    ("anexo_comodato", comodato_path),
                    ("anexo_pdv", pdv_path),
                )
                if caminho
            ]
            pendentes = [c for c in escolhidos if c not in resultados]
            recusados = [c for c in escolhidos if not resultados.get(c, {}).get("ok", False)]
            if pendentes:
                ui.modal_show(
                    modal_aviso(
                        "A conferência dos documentos ainda está em andamento. Aguarde o resultado e tente de novo.",
                        tipo="warning",
                    ),
                    session=session,
                )
                return
            if recusados:
                ui.modal_show(
                    modal_aviso(
                        "Um dos arquivos não passou na conferência. Veja a mensagem em vermelho"
                        " abaixo do campo e envie o documento certo.",
                        tipo="warning",
                    ),
                    session=session,
                )
                return

        caminhos = ic.anexos_comod(
            caminho_pdv=pdv_path,
            caminho_cev=comodato_path,
            caminho_canhoto=canhoto_path,
            codcli=ctx["codcli"],
            ncev=ctx["ncev"],
            cnpj_emp=ctx["cnpj_emp"],
            nome_pdv=pdv_nome,
            nome_cev=comodato_nome,
            nome_canhoto=canhoto_nome,
        )
        if _anexo_em_curso["ativo"]:
            return
        _anexo_em_curso["ativo"] = True
        try:
            await asyncio.to_thread(
                ic.coloca_anexo_bd,
                ncev=ctx["ncev"],
                caminho_pdv=caminhos["PDV"],
                caminho_cev=caminhos["CEV"],
                caminho_canhoto=caminhos["CANHOTO"],
                cnpj_emp=ctx["cnpj_emp"],
                usuario=_nome_usuario(await usuario_atual()),
                codcli=ctx["codcli"],
                nf=ctx["nf"],
                executar=True,
                exige_pdv=ctx.get("exige_pdv", False),
            )
        except Exception as exc:
            logger.warning(f"Comodatos: falha ao gravar os anexos do CEV {ctx['chave_cev']} -- {exc}")
            ui.modal_show(
                modal_aviso("Não foi possível gravar os anexos. Tente novamente.", tipo="error"), session=session
            )
            return
        finally:
            _anexo_em_curso["ativo"] = False
        contexto_acao.set(None)
        ui.modal_remove(session=session)
        refresh_comod.set(refresh_comod() + 1)
        versao_cache.set(versao_cache() + 1)
        ui.modal_show(modal_aviso("Anexos enviados.", tipo="success"), session=session)

    estado_distrato = reactive.value(None, name="estado_distrato")
    _distrato_pronto: dict[str, object] = {"nome": "", "conteudo": b""}

    async def _abrir_distrato(chave_cev: str) -> None:
        usuario = await usuario_atual()
        estado_distrato.set({"etapa": "gerando", "cev": _numero_cev(chave_cev)})
        ui.modal_show(
            ui.modal(ui.output_ui("corpo_distrato"), title=None, size="s", easy_close=False, footer=None),
            session=session,
        )
        asyncio.create_task(_gerar_distrato(chave_cev, usuario))

    async def _gerar_distrato(chave_cev: str, usuario: str) -> None:
        try:
            base = await comodatos_geral()
            itens = base.filter(pl.col("CEV") == chave_cev).to_dicts()
            if not itens:
                raise ValueError("CEV sem itens na tabela")
            cnpj_rev = str(itens[0].get("cnpj") or "")
            dados = await asyncio.to_thread(dados_pdf.dados_distrato, itens, cnpj_rev)
            conteudo, nome, caminho = await asyncio.to_thread(_montar_distrato, dados)
            _distrato_pronto.update({"nome": nome, "conteudo": conteudo})
            etapa = {"etapa": "pronto", "cev": _numero_cev(chave_cev), "nome": nome}
            try:
                await asyncio.to_thread(
                    ic.registrar_distrato,
                    cnpj_rev,
                    chave_cev,
                    str(caminho),
                    usuario,
                    True,
                )
            except Exception as exc:
                logger.warning(f"Comodatos: distrato do CEV {chave_cev} gerado, mas nao registrado no banco -- {exc}")
        except Exception as exc:
            logger.warning(f"Comodatos: falha ao gerar o distrato do CEV {chave_cev} -- {exc}")
            etapa = {"etapa": "erro", "cev": _numero_cev(chave_cev)}
        try:
            async with reactive.lock():
                with reactive.isolate():
                    estado_distrato.set(etapa)
                await reactive.flush()
        except Exception as exc:
            logger.info(f"Comodatos: distrato do CEV {chave_cev} nao mostrado (aba fechada?) -- {exc}")

    def _montar_distrato(dados: dict) -> tuple[bytes, str, Path]:
        caminho = pdf_distrato.gerar_pdf(dados, PASTA_APP / "uploads" / "comodatos" / "distratos")
        return caminho.read_bytes(), caminho.name, caminho

    @render.ui
    def corpo_distrato():
        estado = estado_distrato()
        if estado is None:
            return None
        if estado["etapa"] == "gerando":
            return _corpo_aguarde(
                "Gerando o distrato...",
                f"O documento de encerramento do CEV {estado['cev']} está sendo montado.",
            )
        if estado["etapa"] == "erro":
            return ui.TagList(
                corpo_aviso(
                    f"Não foi possível gerar o distrato do CEV {estado['cev']}. Tente de novo em instantes.",
                    titulo="Distrato não gerado",
                    tipo="error",
                ),
                ui.div(
                    ui.input_action_button("bt_fecha_distrato", "OK", class_="btn-sm comod-btn-confirmar"),
                    class_="text-center",
                ),
            )
        return ui.TagList(
            corpo_aviso(
                f"O distrato do CEV {estado['cev']} está pronto.",
                titulo="Distrato gerado",
                tipo="success",
            ),
            ui.div(
                ui.download_button(
                    "baixar_distrato",
                    "Baixar PDF",
                    icon=icon_svg("file-pdf", a11y="deco"),
                    class_="btn-sm comod-btn-confirmar",
                ),
                ui.input_action_button("bt_fecha_distrato", "Fechar", class_="btn-sm"),
                class_="d-flex justify-content-center gap-2",
            ),
        )

    @reactive.effect
    @reactive.event(input.bt_fecha_distrato)
    def _fechar_distrato():
        estado_distrato.set(None)
        ui.modal_remove(session=session)

    @render.download_button(filename=lambda: str(_distrato_pronto["nome"] or "distrato.pdf"))
    async def baixar_distrato():
        yield _distrato_pronto["conteudo"]

    estado_recolha = reactive.value(None, name="estado_recolha")
    _recolha_em_curso: dict[str, object] = {"ativo": False, "tarefa": None}

    @reactive.effect
    @reactive.event(input.clique_recolha)
    async def _gerar_recolha():
        if not await pode_recolha():
            return
        dados = input.clique_recolha()
        linha = await _linha_cev(dados["chave_cev"])
        if linha is None:
            return
        if dados.get("valor") == "PDF" or linha.get("Recolha") == "PDF":
            await _abrir_distrato(str(linha.get("CEV") or dados["chave_cev"]))
            return

        if not await acesso_supremo():
            base = await comodatos_geral()
            if not d.cev_recolha_liberada(base, dados["chave_cev"]):
                return

        chave = str(linha.get("CEV") or dados["chave_cev"])
        revenda = revenda_atual() or chave.rsplit("-", 1)[0].strip()
        estado_recolha.set(
            {
                "etapa": "confirmar",
                "revenda": revenda,
                "cev": _numero_cev(chave),
                "cliente": str(linha.get("Razão Social") or linha.get("Cliente") or ""),
                "escolhe_em_nome": dp.aceita_recolha_pela_revenda(revenda),
            }
        )
        ui.modal_show(
            ui.modal(ui.output_ui("corpo_recolha"), title=None, size="s", easy_close=False, footer=None),
            session=session,
        )

    @render.ui
    def corpo_recolha():
        estado = estado_recolha()
        if estado is None:
            return None
        if estado["etapa"] == "confirmar":
            return ui.TagList(
                corpo_aviso(
                    f"Deseja realmente enviar o pedido de recolha do CEV {estado['cev']} ao ERP?"
                    " Isso grava no ERP e não há como desfazer pela tela.",
                    titulo="Confirmar recolha?",
                    tipo="warning",
                ),
                ui.input_radio_buttons(
                    "recolha_em_nome",
                    "Emitir a nota de retorno em nome de:",
                    {"cliente": "Cliente", "revenda": "Própria revenda"},
                    selected="cliente",
                )
                if estado.get("escolhe_em_nome")
                else None,
                ui.div(
                    ui.input_action_button("bt_confirma_recolha", "Sim", class_="btn-sm comod-btn-confirmar"),
                    ui.input_action_button("bt_nega_recolha", "Não", class_="btn-sm"),
                    class_="d-flex justify-content-center gap-2",
                ),
            )
        if estado["etapa"] == "enviando":
            return _corpo_aguarde(
                "Enviando a recolha...",
                f"O pedido de retorno do CEV {estado['cev']} está sendo gravado no ERP."
                " Isso costuma levar alguns segundos -- não feche esta janela.",
            )
        return ui.TagList(
            corpo_aviso(estado["texto"], titulo=estado["titulo"], tipo="success" if estado["ok"] else "error"),
            ui.div(
                ui.input_action_button("bt_nega_recolha", "OK", class_="btn-sm comod-btn-confirmar"),
                class_="text-center",
            ),
        )

    @reactive.effect
    @reactive.event(input.bt_nega_recolha)
    def _cancelar_recolha():
        estado_recolha.set(None)
        ui.modal_remove(session=session)

    @reactive.effect
    @reactive.event(input.bt_confirma_recolha)
    async def _confirmar_recolha():
        estado = estado_recolha()
        if estado is None or estado.get("etapa") != "confirmar" or not await pode_recolha():
            return
        if _recolha_em_curso["ativo"]:
            return
        pela_revenda = False
        if estado.get("escolhe_em_nome") and "recolha_em_nome" in input:
            try:
                pela_revenda = input.recolha_em_nome() == "revenda"
            except Exception:
                pela_revenda = False
        _recolha_em_curso["ativo"] = True
        estado_recolha.set({**estado, "etapa": "enviando"})
        _recolha_em_curso["tarefa"] = asyncio.create_task(
            _executar_recolha(estado["revenda"], estado["cev"], pela_revenda, await usuario_atual())
        )

    async def _executar_recolha(revenda: str, cev: str, pela_revenda: bool = False, usuario: str = "") -> None:
        try:
            resultado = await cc.gerar_recolha(revenda, cev, pela_revenda=pela_revenda, usuario=usuario)
            desfecho, _separador, pedido_existente = resultado.partition("|")
            ok = desfecho == "pegou"
            titulo = "Recolha gerada" if ok else "Recolha não gerada"
            if ok:
                texto = "Pedido de recolha gerado no ERP." + (
                    " A nota de retorno sai em nome da própria revenda." if pela_revenda else ""
                )
            elif desfecho == "ja_existe":
                texto = (
                    f"Este CEV já tem pedido de recolha no ERP ({pedido_existente})."
                    " Para pedir de novo, esse pedido precisa ser cancelado no ERP antes."
                )
            elif desfecho == "ja_faturado":
                texto = (
                    f"Este CEV já teve recolha faturada no ERP ({pedido_existente})."
                    " Se ainda sobrou item com o cliente, a recolha do restante precisa ser feita no"
                    " ERP: por aqui, o pedido sairia com as quantidades inteiras do contrato."
                )
            else:
                texto = "Não foi encontrado pedido desse CEV no ERP."
        except Exception as exc:
            logger.warning(f"Comodatos: falha ao gerar a recolha do CEV {cev} -- {exc}")
            ok = False
            titulo, texto = cc.erro_amigavel(exc, "a recolha não foi gerada")
        finally:
            _recolha_em_curso["ativo"] = False
        try:
            async with reactive.lock():
                with reactive.isolate():
                    estado_recolha.set(
                        {
                            "etapa": "resultado",
                            "cev": cev,
                            "ok": ok,
                            "titulo": titulo,
                            "texto": texto,
                        }
                    )
                    if ok:
                        refresh_comod.set(refresh_comod() + 1)
                await reactive.flush()
        except Exception as exc:
            logger.warning(f"Comodatos: nao deu pra mostrar o resultado da recolha -- {exc}")


def pag_comodatos_ui():
    return comodatos_ui("comodatos")


def pag_comodatos_server(versao_cache):
    comodatos_server("comodatos", valor_navset="comod_comod", versao_cache=versao_cache)
