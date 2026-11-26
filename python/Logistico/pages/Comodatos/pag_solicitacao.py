import asyncio
import re
import unicodedata
from datetime import date
from functools import partial
from urllib.parse import parse_qs

import pandas as pd
import polars as pl
from faicons import icon_svg
from loguru import logger

try:
    from rapidfuzz import fuzz
    from rapidfuzz.distance import JaroWinkler, Levenshtein
except ImportError:  # Shinylive: o rapidfuzz é compilado e não existe no navegador
    from core.rapidfuzz_puro import JaroWinkler, Levenshtein, fuzz
from shiny import module, reactive, render, ui

from core import revendas
from core.auth import identificar_usuario
from core.aviso import corpo_aviso, modal_aviso
from core.config import (
    CHAVE_SUPREMO,
    adicionar_responsavel,
    pode,
    remover_responsavel,
    secoes_de_direitos,
)
from core.cores import SIDEBAR_BG
from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.tabela_paginada import TabelaPaginada
from core.visibilidade import pagina_visivel

from .Dados import control_comodato as cc
from .Dados import dados_comodato as d
from .Dados import excecoes_comodato as ex
from .Dados import funcao_cnpj as cnpj_api
from .Dados import funcao_extracao_doc as ocr
from .Dados import material_comodato as mc
from .Dados import solicita_comodato as sc
from .Dados import tabela_comodato as ti

LIMITE_OPCOES_LOCAIS = 300

FILTROS = [
    ("cliente", "Cliente", "COD_RS"),
    ("tipo", "Tipo", "CGC_CPF"),
    ("cidade", "Cidade", "CIDADE"),
    ("classificacao", "Classificação", "PORTE"),
    ("canal", "Canal", "CANAL"),
    ("vendedor", "Vendedor", "VEN"),
    ("ga", "Gerente de Área", "subordinacao"),
    ("inadimplente", "Inadimplente", "Inadimplente"),
    ("status_doc", "Status Doc", "Status Doc"),
    ("solic_liberada", "Solic Liberada", "Solic Liberada"),
]

CHAVE_FOTO_MATERIAL = mc.CHAVE_FOTO_MATERIAL

MOSTRAR_CANCELAR_PRE_PEDIDO = True

CANCELAR_PRE_PEDIDO_ATIVO = True

_ALTURA_TABELA_CLIENTES = "40vh"
_ALTURA_TABELA_SOLICITACOES = "22vh"
_ALTURA_TABELA_PRE_PEDIDOS = "22vh"

MOSTRAR_BOTAO_EXCECAO = True

LIMIAR_JARO_WINKLER = 0.5

_LARGURA_CLIENTES = {
    "Revenda": 100,
    "Cliente": 130,
    "Fantasia": 130,
    "Tipo": 80,
    "Cidade": 120,
    "Classificação": 110,
    "Canal": 90,
    "Ven": 80,
    "GA": 80,
    "Inadimplente": 100,
    "Solicitação": 90,
    "Detalhes": 80,
}
_LARGURA_SOLICITACOES = {
    "Cliente": 280,
    "Produto": 190,
    "Quantidade": 90,
    "Valor": 110,
    "Prazo": 80,
    "Tipo": 90,
    "Cancelar": 80,
}
_LARGURA_DETALHES_CLIENTE = {"Produto": 180}
_LARGURA_PRE_PEDIDOS = {
    "Revenda": 100,
    "Pré-pedido": 110,
    "Cliente": 260,
    "Prazo": 80,
    "Tipo": 90,
    "Usuário": 110,
    "Produto": 170,
    "Quantidade": 90,
    "Valor": 110,
    "Emissão": 90,
    "Vencimento": 100,
    "Cancelar": 80,
}


_OPCOES_LISTA_ITEM = {
    "dropdownParent": "body",
    "dropdownClass": "selectize-dropdown comod-selectize-dropdown",
}


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


def _nome_usuario(usuario: str) -> str:
    return " ".join(parte.capitalize() for parte in usuario.split("."))


def _valor_input_seguro(input, id_input: str):
    try:
        return input[id_input]()
    except Exception:
        return None


def _cpf_comparavel(valor) -> str:
    digitos = "".join(c for c in str(valor or "") if c.isdigit())
    return digitos.rjust(11, "0") if 0 < len(digitos) <= 11 else digitos


def _campo_so_leitura(id_campo: str, rotulo: str, valor: str) -> ui.Tag:
    return (
        ui.input_text(id_campo, rotulo, value=valor, width="100%")
        .add_style("pointer-events: none;")
        .add_class("comod-campo-leitura comod-modal-claro")
    )


def _liberados_primeiro(base: pl.DataFrame) -> pl.DataFrame:
    if base.height == 0 or "Solicitacao" not in base.columns:
        return base
    return base.sort(pl.col("Solicitacao") != "\u2795", maintain_order=True)


def _nomes_parecidos(nome_documento: str, candidatos: list) -> bool:
    if not nome_documento or nome_documento == "Nao tem":
        return False
    distancias = [
        JaroWinkler.distance(nome_documento, str(nome).strip().upper())
        for nome in candidatos
        if nome and str(nome).strip()
    ]
    return bool(distancias) and min(distancias) < LIMIAR_JARO_WINKLER


_DIGITO_LIDO_NO_LUGAR_DA_LETRA = str.maketrans("10582", "IOSBZ")


def _palavras_maiusculas(texto) -> list[str]:
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    palavras = []
    for palavra in re.findall(r"[A-Z0-9]+", sem_acento.upper()):
        if any(caractere.isalpha() for caractere in palavra):
            palavras.append(palavra.translate(_DIGITO_LIDO_NO_LUGAR_DA_LETRA))
    return palavras


def _letras_erradas_toleradas(palavra: str) -> int:
    return 2 if len(palavra) >= 8 else 1


LETRAS_DO_NOME_COLADO = 12
PARECIDO_DO_NOME_COLADO = 92
FRACAO_DO_NOME_NO_TITULAR = 0.8


def _nome_confere_com_o_titular(nome_titular: str, candidatos: list) -> bool:
    if not nome_titular or nome_titular == "Nao tem":
        return False
    palavras_do_titular = {palavra for palavra in _palavras_maiusculas(nome_titular) if len(palavra) >= 3}
    titular_colado = "".join(_palavras_maiusculas(nome_titular))
    for nome in candidatos:
        nome_colado = "".join(_palavras_maiusculas(nome))
        if (
            len(nome_colado) >= LETRAS_DO_NOME_COLADO
            and len(titular_colado) >= FRACAO_DO_NOME_NO_TITULAR * len(nome_colado)
            and fuzz.partial_ratio(nome_colado, titular_colado, score_cutoff=PARECIDO_DO_NOME_COLADO) > 0
        ):
            return True
        palavras_do_nome = [
            palavra for palavra in _palavras_maiusculas(nome) if len(palavra) >= 3 and palavra not in ("DOS", "DAS")
        ]
        if len(palavras_do_nome) < 2:
            continue
        achadas = 0
        for palavra in palavras_do_nome:
            tolerancia = _letras_erradas_toleradas(palavra)
            for palavra_do_titular in palavras_do_titular:
                if Levenshtein.distance(palavra, palavra_do_titular, score_cutoff=tolerancia) <= tolerancia:
                    achadas += 1
                    break
        if achadas == len(palavras_do_nome):
            return True
    return False


def _nome_confere(motor: str, nome_documento: str, candidatos: list) -> bool:
    if motor == "local":
        return _nome_confere_com_o_titular(nome_documento, candidatos)
    return _nomes_parecidos(nome_documento, candidatos)


def _codigo_do_cliente(rotulo) -> str:
    return str(rotulo or "").split(" - ", 1)[0].strip()


def _revenda_da_excecao(base: pl.DataFrame, codcli: str, vendedor: str) -> str | None:
    if base.height == 0 or "REVENDA" not in base.columns:
        return None
    if codcli:
        linhas = base.filter(pl.col("CODCLI").cast(pl.Utf8) == codcli)
    elif vendedor:
        linhas = base.filter(pl.col("VEN").cast(pl.Utf8) == vendedor)
    else:
        return None
    nomes = [n for n in linhas["REVENDA"].cast(pl.Utf8).unique().to_list() if n]
    return nomes[0] if len(nomes) == 1 else None


def _aviso_excecao_ui(mensagem: str | None) -> ui.Tag | None:
    if not mensagem:
        return None
    return ui.div(mensagem, class_="text-danger comod-feedback-campo")


EXPLICA_NUMERO = (
    'É o número de série do aparelho (o "R.G. do produto"), que fica na etiqueta'
    " do fabricante, na traseira ou na embalagem. Não é a plaqueta da cervejaria,"
    " aquela que começa com HNKM."
)


def _campo_serial_travado(id_campo: str, valor: str) -> ui.Tag:
    return ui.div(
        ui.tags.label("Número de série:", class_="control-label", for_=id_campo),
        ui.tags.input(
            id=id_campo,
            type="text",
            class_="form-control",
            value=valor or "",
            readonly=True,
            tabindex="-1",
            placeholder="Sai da foto da etiqueta",
            title=(
                "O número vem da foto da etiqueta. Se o serviço de leitura estiver"
                " fora do ar, este campo abre para você digitar."
            ),
        ),
        class_="form-group shiny-input-container comod-campo-leitura comod-modal-claro comod-campo-serial",
    )


def _icone_camera() -> ui.Tag:
    return icon_svg("camera", position="static", margin_left="0", margin_right="0")


def _rotulo_enviar_foto() -> ui.TagList:
    return ui.TagList(_icone_camera(), " Enviar")


def _campo_material(id_botao: str, identificador: str) -> ui.Tag:
    if identificador:
        rotulo = identificador
        titulo = f"Equipamento {identificador} -- clique para trocar as fotos"
    else:
        rotulo = "Enviar fotos"
        titulo = "Foto da etiqueta de identificação e foto do material"
    return ui.div(
        ui.tags.label("Id Prod", class_="control-label"),
        ui.input_action_button(
            id_botao,
            rotulo,
            title=titulo,
            icon=None if identificador else _icone_camera(),
            class_="btn-sm comod-btn-material" + (" comod-material-ok" if identificador else ""),
        ),
        class_="form-group comod-campo-material",
    )


def _corpo_aguarde(titulo: str, motivo: str) -> ui.Tag:
    return ui.div(
        ui.div(class_="comod-aviso-girando"),
        ui.div(titulo, class_="aviso-titulo"),
        ui.div(motivo, class_="aviso-texto"),
        class_="aviso-corpo",
    )


def _feedback_documento_ui(feedback: dict | None) -> ui.Tag | None:
    if not feedback:
        return None
    cor = "text-success" if feedback["sucesso"] else "text-danger"
    return ui.div(feedback["mensagem"], class_=f"{cor} comod-feedback-campo")


@module.ui
def solicitacao_ui():
    return ui.div(
        ui.card(
            ui.div(
                *[_filtro_ui(id_filtro, rotulo) for id_filtro, rotulo, _coluna in FILTROS],
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
        ui.card(
            ui.card_header(
                ui.div(
                    ui.span("Clientes"),
                    ui.div(
                        ui.output_ui("bt_responsaveis_ui"),
                        ui.output_ui("bt_excecao_ui"),
                        class_="comod-card-toolbar",
                    ),
                    style="display:flex; justify-content:space-between; align-items:center; width:100%;",
                )
            ),
            ui.output_ui("corpo_tabela_clientes"),
        ),
        ui.card(
            ui.card_header("Solicitações pendentes"),
            ui.output_ui("corpo_tabela_solicitacoes"),
        ),
        ui.card(
            ui.card_header(
                ui.div(
                    ui.span("Cancelar pré-pedido"),
                    ui.div(ui.output_ui("bt_conferir_pre_pedidos_ui"), class_="comod-card-toolbar"),
                    style="display:flex; justify-content:space-between; align-items:center; width:100%;",
                )
            ),
            ui.output_ui("corpo_tabela_pre_pedidos"),
        )
        if MOSTRAR_CANCELAR_PRE_PEDIDO
        else None,
        class_="comodatos-modulo",
    )


@module.server
def solicitacao_server(input, output, session, valor_navset: str, versao_cache):
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
    async def pode_gerenciar() -> bool:
        return pode(await usuario_atual(), "solicitacao_comodato")

    @reactive.calc
    async def acesso_supremo() -> bool:
        return pode(await usuario_atual(), CHAVE_SUPREMO)

    @reactive.calc
    async def pode_foto_material() -> bool:
        return pode(await usuario_atual(), CHAVE_FOTO_MATERIAL)

    @reactive.calc
    async def solicita_sem_bloqueio() -> bool:
        return pode(await usuario_atual(), "solicitacao_sem_bloqueio")

    versao_clientes = reactive.value(0, name="versao_clientes")

    @reactive.calc
    async def clientes_geral() -> pl.DataFrame:
        versao_clientes()
        versao_cache()
        base = await asyncio.to_thread(
            d.clientes_inadimplentes,
            revenda_atual(),
            await acesso_supremo(),
            await solicita_sem_bloqueio(),
        )
        revenda = revenda_atual()
        if not revenda or base.height == 0:
            return base
        alvo = revendas.chave_nome(revenda)
        nomes = [
            nome
            for nome in base["REVENDA"].cast(pl.Utf8).unique().to_list()
            if nome and alvo in revendas.chave_nome(nome)
        ]
        return base.filter(pl.col("REVENDA").cast(pl.Utf8).is_in(nomes))

    @reactive.calc
    async def clientes_filtrados() -> pl.DataFrame:
        base = await clientes_geral()
        if base.height == 0:
            return base
        for id_filtro, _rotulo, coluna in FILTROS:
            valores = input[id_filtro]()
            if valores and coluna in base.columns:
                base = base.filter(pl.col(coluna).cast(pl.Utf8).is_in(list(valores)))
        return _liberados_primeiro(base)

    @reactive.effect
    async def _atualiza_opcoes_filtro():
        if not pagina_visivel(session, valor_navset):
            return
        base = await clientes_geral()
        for id_filtro, _rotulo, coluna in FILTROS:
            if input[id_filtro]() or coluna not in base.columns:
                continue
            opcoes = (
                sorted(v for v in base[coluna].cast(pl.Utf8).unique().to_list() if v is not None) if base.height else []
            )
            ui.update_selectize(
                id_filtro,
                choices=opcoes,
                session=session,
                server=len(opcoes) > LIMITE_OPCOES_LOCAIS,
            )

    @reactive.effect
    async def _resolve_usuario_antes_do_modal():
        if not pagina_visivel(session, valor_navset):
            return
        try:
            await usuario_atual()
        except Exception as exc:
            logger.warning(f"Solicitação: falha ao resolver o usuário logado -- {exc}")

    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar_filtros():
        for id_filtro, _rotulo, _coluna in FILTROS:
            ui.update_selectize(id_filtro, selected=[], session=session)

    @reactive.calc
    def revenda_solicitados() -> str:
        return revenda_atual() or "HOLDING"

    versao_solicitacoes = reactive.value(0, name="versao_solicitacoes")

    @reactive.calc
    async def solicitacoes_pendentes() -> pl.DataFrame:
        versao_solicitacoes()
        return await asyncio.to_thread(d.comod_solicitados, revenda_solicitados())

    paginador_clientes = TabelaPaginada("pag_clientes", input, session)

    ordem_clientes = reactive.value(None, name="ordem_clientes")

    def _clique_no_cabecalho() -> tuple:
        try:
            return tuple(tabela_clientes.sort())
        except Exception:
            return ()

    @reactive.effect
    def _troca_ordem_pelo_cabecalho():
        clique = _clique_no_cabecalho()
        if not clique:
            return
        colunas = ti.colunas_clientes_exibidas(not revenda_atual())
        indice = clique[0]["col"]
        nome = colunas[indice] if 0 <= indice < len(colunas) else None
        if nome not in ti.COLUNA_CRUA_CLIENTES:
            return
        escolha = (nome, bool(clique[0]["desc"]))
        if ordem_clientes() == escolha:
            return
        ordem_clientes.set(escolha)
        paginador_clientes.reiniciar()

    @reactive.effect
    @reactive.event(input.clique_ordenar_solicitacao)
    def _ordena_pela_coluna_solicitacao():
        atual = ordem_clientes()
        if atual is None or atual[0] != "Solicitação":
            ordem_clientes.set(("Solicitação", False))
        elif not atual[1]:
            ordem_clientes.set(("Solicitação", True))
        else:
            ordem_clientes.set(None)
        paginador_clientes.reiniciar()

    @reactive.calc
    async def clientes_ordenados() -> pl.DataFrame:
        base = await clientes_filtrados()
        if base.height == 0:
            return base
        ordem = ordem_clientes()
        coluna_crua = ti.COLUNA_CRUA_CLIENTES.get(ordem[0]) if ordem else None
        if not coluna_crua or coluna_crua not in base.columns:
            return _liberados_primeiro(base)
        return base.sort(coluna_crua, descending=ordem[1], maintain_order=True)

    @reactive.calc
    async def tabela_clientes_pagina() -> tuple[pd.DataFrame, list[dict]]:
        base = await clientes_ordenados()
        if base.height == 0:
            return pd.DataFrame(), []
        inicio, fim = paginador_clientes.janela(base.height)
        mostra_revenda = not revenda_atual()
        return await asyncio.to_thread(ti.construir_clientes_solicitacao_df, base[inicio:fim], mostra_revenda)

    @render.ui
    async def corpo_tabela_clientes():
        base = await clientes_filtrados()
        if base.height == 0:
            return ui.p("Sem clientes para os filtros selecionados.")
        return ui.div(
            ui.output_ui("css_largura_tabela_clientes"),
            ui.output_data_frame("tabela_clientes"),
            ui.output_ui("controles_tabela_clientes"),
            class_="comod-tabela tabela-resize",
        )

    @render.data_frame
    async def tabela_clientes():
        pandas_df, estilos = await tabela_clientes_pagina()
        return render.DataTable(
            pandas_df,
            styles=estilos,
            height=_ALTURA_TABELA_CLIENTES,
            summary=False,
            filters=False,
            selection_mode="none",
        )

    @render.ui
    async def css_largura_tabela_clientes():
        pandas_df, _estilos = await tabela_clientes_pagina()
        larguras = [ColunaLargura(c, _LARGURA_CLIENTES.get(c, 100)) for c in pandas_df.columns]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_clientes')}", larguras))

    @render.ui
    async def controles_tabela_clientes():
        base = await clientes_filtrados()
        return paginador_clientes.controles(base.height)

    @reactive.effect
    async def _reinicia_pagina_clientes():
        if not pagina_visivel(session, valor_navset):
            return
        await clientes_filtrados()
        paginador_clientes.reiniciar()

    grupos_abertos = reactive.value((), name="grupos_abertos")

    @reactive.effect
    @reactive.event(input.clique_expandir)
    def _abrir_fechar_grupo():
        chave = (input.clique_expandir() or {}).get("chave_grupo")
        if not chave:
            return
        abertos = grupos_abertos()
        if chave in abertos:
            grupos_abertos.set(tuple(c for c in abertos if c != chave))
        else:
            grupos_abertos.set(abertos + (chave,))

    @reactive.calc
    async def solicitacoes_agrupadas() -> tuple[pd.DataFrame, list[str], pl.DataFrame, bool, bool]:
        base = await solicitacoes_pendentes()
        liberado = await pode_gerenciar()
        mostra_revenda = bool(not revenda_atual())
        if base.height == 0:
            return pd.DataFrame(), [], base, liberado, mostra_revenda
        fechado, chaves = await asyncio.to_thread(
            ti.construir_solicitacoes_pendentes_df, base, liberado, mostra_revenda
        )
        return fechado, chaves, base, liberado, mostra_revenda

    @reactive.calc
    async def tabela_solicitacoes_pronta() -> pd.DataFrame:
        fechado, chaves, base, liberado, mostra_revenda = await solicitacoes_agrupadas()
        if fechado.empty:
            return fechado
        return await asyncio.to_thread(
            ti.expandir_solicitacoes_df,
            fechado,
            chaves,
            base,
            liberado,
            grupos_abertos(),
            mostra_revenda,
        )

    @reactive.calc
    async def _tem_solicitacoes() -> bool:
        fechado, *_resto = await solicitacoes_agrupadas()
        return not fechado.empty

    @render.ui
    async def corpo_tabela_solicitacoes():
        if not await _tem_solicitacoes():
            return ui.p("Sem solicitações pendentes.")
        return ui.div(
            ui.output_ui("css_largura_tabela_solicitacoes"),
            ui.output_data_frame("tabela_solicitacoes"),
            class_="comod-tabela tabela-resize",
        )

    @render.data_frame
    async def tabela_solicitacoes():
        pandas_df = await tabela_solicitacoes_pronta()
        return render.DataTable(
            pandas_df,
            height=_ALTURA_TABELA_SOLICITACOES,
            summary=False,
            filters=False,
            selection_mode="none",
        )

    @reactive.calc
    async def _colunas_solicitacoes() -> tuple[str, ...]:
        fechado, *_resto = await solicitacoes_agrupadas()
        return tuple(fechado.columns)

    @render.ui
    async def css_largura_tabela_solicitacoes():
        larguras = [ColunaLargura(c, _LARGURA_SOLICITACOES.get(c, 100)) for c in await _colunas_solicitacoes()]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_solicitacoes')}", larguras))

    @reactive.calc
    async def pode_cancelar_pre_pedido() -> bool:
        return pode(await usuario_atual(), "cancelar_pre_pedido")

    @reactive.calc
    async def pre_pedidos() -> pl.DataFrame:
        versao_solicitacoes()
        versao_cache()
        return await asyncio.to_thread(d.comod_pre_pedidos, revenda_solicitados())

    @reactive.calc
    async def tabela_pre_pedidos_pronta() -> pd.DataFrame:
        base = await pre_pedidos()
        if base.height == 0:
            return pd.DataFrame()
        return await asyncio.to_thread(
            ti.construir_pre_pedidos_df,
            base,
            await pode_cancelar_pre_pedido(),
            bool(not revenda_atual()),
        )

    @reactive.calc
    async def _tem_pre_pedidos() -> bool:
        return not (await tabela_pre_pedidos_pronta()).empty

    @render.ui
    async def corpo_tabela_pre_pedidos():
        if not await _tem_pre_pedidos():
            return ui.p(f"Nenhum pedido enviado ao ERP nos últimos {d.DIAS_PRE_PEDIDO_VISIVEL} dias.")
        return ui.div(
            ui.output_ui("css_largura_tabela_pre_pedidos"),
            ui.output_data_frame("tabela_pre_pedidos"),
            class_="comod-tabela tabela-resize",
        )

    @render.data_frame
    async def tabela_pre_pedidos():
        pandas_df = await tabela_pre_pedidos_pronta()
        return render.DataTable(
            pandas_df,
            height=_ALTURA_TABELA_PRE_PEDIDOS,
            summary=False,
            filters=False,
            selection_mode="none",
        )

    @render.ui
    async def css_largura_tabela_pre_pedidos():
        pandas_df = await tabela_pre_pedidos_pronta()
        larguras = [ColunaLargura(c, _LARGURA_PRE_PEDIDOS.get(c, 100)) for c in pandas_df.columns]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_pre_pedidos')}", larguras))

    conferencia_em_curso = reactive.value(False, name="conferencia_em_curso")
    _conferencia: dict[str, object] = {"tarefa": None}

    @render.ui
    async def bt_conferir_pre_pedidos_ui():
        if not await pode_cancelar_pre_pedido() or not revenda_atual():
            return None
        if conferencia_em_curso():
            return ui.input_action_button(
                "bt_conferir_pre_pedidos",
                "Conferindo...",
                class_="btn-sm btn-atualizar-comod",
                disabled=True,
            )
        return ui.input_action_button(
            "bt_conferir_pre_pedidos",
            "Conferir agora",
            icon=icon_svg("rotate", a11y="deco"),
            class_="btn-sm btn-atualizar-comod",
        )

    @reactive.effect
    @reactive.event(input.bt_conferir_pre_pedidos)
    async def _conferir_pre_pedidos():
        revenda = revenda_atual()
        if not revenda or conferencia_em_curso() or not await pode_cancelar_pre_pedido():
            return
        conferencia_em_curso.set(True)
        _conferencia["tarefa"] = asyncio.create_task(_executar_conferencia(revenda))

    async def _executar_conferencia(revenda: str) -> None:
        try:
            resultado = await cc.conferir_pre_pedidos(revenda)
            tipo, texto = "success", f"Lista atualizada: {resultado}."
        except Exception as exc:
            logger.warning(f"Solicitação: falha ao conferir os pré-pedidos -- {exc}")
            tipo, texto = "error", cc.erro_amigavel(exc, "a lista não foi atualizada")[1]
        try:
            async with reactive.lock():
                with reactive.isolate():
                    conferencia_em_curso.set(False)
                    versao_solicitacoes.set(versao_solicitacoes() + 1)
                await reactive.flush()
            ui.notification_show(texto, type=tipo, duration=6, session=session)
        except Exception as exc:
            logger.warning(f"Solicitação: nao deu pra mostrar o fim da conferência -- {exc}")

    estado_cancelamento_pp = reactive.value(None, name="estado_cancelamento_pp")
    _cancelamento_pp_em_curso: dict[str, object] = {"ativo": False, "tarefa": None}

    @reactive.effect
    @reactive.event(input.clique_cancelar_pre_pedido)
    async def _abrir_confirmacao_pre_pedido():
        if not await pode_cancelar_pre_pedido():
            return
        dados = input.clique_cancelar_pre_pedido()
        estado_cancelamento_pp.set({"etapa": "confirmar", **dados})
        ui.modal_show(
            ui.modal(
                ui.output_ui("corpo_cancelamento_pre_pedido"), title=None, size="s", easy_close=False, footer=None
            ),
            session=session,
        )

    @reactive.effect
    @reactive.event(input.bt_nega_cancelamento_pp)
    def _fechar_confirmacao_pre_pedido():
        estado_cancelamento_pp.set(None)
        ui.modal_remove(session=session)

    @reactive.effect
    @reactive.event(input.bt_confirma_cancelamento_pp)
    async def _confirmar_cancelamento_pre_pedido():
        estado = estado_cancelamento_pp()
        if estado is None or estado.get("etapa") != "confirmar":
            return
        if not await pode_cancelar_pre_pedido():
            return
        if _cancelamento_pp_em_curso["ativo"]:
            return
        _cancelamento_pp_em_curso["ativo"] = True
        estado_cancelamento_pp.set({**estado, "etapa": "cancelando"})
        _cancelamento_pp_em_curso["tarefa"] = asyncio.create_task(_executar_cancelamento_pp(estado))

    async def _executar_cancelamento_pp(dados: dict) -> None:
        simular = not CANCELAR_PRE_PEDIDO_ATIVO
        mexeu_no_banco = False
        try:
            desfecho, motivo = await cc.cancelar_pre_pedido(
                dados["revenda"], dados["pre_ped"], dados["cliente"], simular=simular
            )
            mexeu_no_banco = desfecho in ("cancelado", "cancelado_sem_liberar")
            tipo, titulo, texto = _resultado_cancelamento_pp(desfecho, motivo, simular)
        except Exception as exc:
            logger.warning(f"Solicitação: falha ao cancelar o pré-pedido -- {exc}")
            tipo = "error"
            titulo, texto = cc.erro_amigavel(exc, "o pré-pedido não foi cancelado")
        finally:
            _cancelamento_pp_em_curso["ativo"] = False
        try:
            await _sincronizar_parquet_solicitacoes(regravar=mexeu_no_banco)
        except Exception as exc:
            logger.warning(f"Solicitação: parquet não regravado após o cancelamento -- {exc}")
        try:
            async with reactive.lock():
                with reactive.isolate():
                    estado_cancelamento_pp.set({"etapa": "resultado", "tipo": tipo, "titulo": titulo, "texto": texto})
                await reactive.flush()
        except Exception as exc:
            logger.warning(f"Solicitação: nao deu pra mostrar o resultado do cancelamento -- {exc}")

    def _resultado_cancelamento_pp(desfecho: str, motivo: str, simular: bool) -> tuple[str, str, str]:
        if desfecho == "cancelado":
            return (
                "success",
                "Pré-pedido cancelado",
                (
                    "O pedido foi marcado como cancelado no ERP e sai desta lista. A solicitação"
                    " voltou para os pendentes: dá para corrigir e enviar de novo, sem risco de pedido"
                    " repetido -- o antigo ficou cancelado no ERP."
                ),
            )
        if desfecho == "cancelado_sem_liberar":
            return (
                "warning",
                "Cancelado, mas a solicitação não voltou",
                (
                    f"{motivo}. O pedido está cancelado no ERP (nada foi enviado em duplicidade),"
                    " só a solicitação não voltou para os pendentes."
                ),
            )
        if desfecho == "pode_cancelar":
            return (
                "warning",
                "Modo de teste",
                (
                    "O pedido ainda está no ERP e pode ser cancelado, mas nada foi gravado:"
                    " o cancelamento de verdade está desligado nesta versão."
                ),
            )
        if desfecho == "ja_importado":
            return (
                "warning",
                "Não dá mais para cancelar",
                (f"O ERP já validou esse pedido ({motivo}). A partir daqui o caminho é a recolha."),
            )
        if desfecho in ("nao_encontrado", "sem_itens"):
            return (
                "warning",
                "Esse pedido não está mais lá",
                (f"{motivo}. A solicitação será destravada sozinha na próxima conferência automática."),
            )
        if desfecho == "divergente":
            return (
                "warning",
                "O pedido foi alterado no ERP",
                (
                    f"{motivo}. Como ele não está mais igual ao que foi enviado, o cancelamento"
                    " precisa ser feito por quem alterou."
                ),
            )
        if desfecho == "numero_invalido":
            return "error", "Número inválido", motivo
        return "error", "Resultado inesperado", f"{desfecho}: {motivo}"

    @render.ui
    def corpo_cancelamento_pre_pedido():
        estado = estado_cancelamento_pp()
        if estado is None:
            return None
        if estado["etapa"] == "confirmar":
            aviso = (
                "Isso marca o pedido como cancelado no ERP, e a solicitação volta para os"
                " pendentes -- dá para corrigir e enviar de novo."
                if CANCELAR_PRE_PEDIDO_ATIVO
                else "O cancelamento de verdade está DESLIGADO nesta versão: o pedido vai apenas"
                " ser conferido no ERP, sem ser cancelado."
            )
            return ui.TagList(
                corpo_aviso(
                    f"Pré-pedido {estado.get('pre_ped', '')} de {estado.get('cliente', '')}. {aviso}"
                    " Só dá certo enquanto o ERP não tiver validado o pedido.",
                    titulo="Cancelar este pré-pedido?",
                    tipo="warning",
                ),
                ui.div(
                    ui.input_action_button(
                        "bt_confirma_cancelamento_pp", "Sim, cancelar", class_="btn-sm comod-btn-cancelar"
                    ),
                    ui.input_action_button("bt_nega_cancelamento_pp", "Não, voltar", class_="btn-sm"),
                    class_="d-flex justify-content-center gap-2",
                ),
            )
        if estado["etapa"] == "cancelando":
            return _corpo_aguarde(
                "Cancelando pré-pedido...",
                "O pedido está sendo conferido no ERP. Isso costuma levar alguns segundos.",
            )
        return ui.TagList(
            corpo_aviso(estado["texto"], titulo=estado["titulo"], tipo=estado["tipo"]),
            ui.div(
                ui.input_action_button("bt_fecha_cancelamento_pp", "OK", class_="btn-sm comod-btn-confirmar"),
                class_="text-center",
            ),
        )

    @reactive.effect
    @reactive.event(input.bt_fecha_cancelamento_pp)
    def _fechar_resultado_cancelamento_pp():
        estado_cancelamento_pp.set(None)
        ui.modal_remove(session=session)

    contexto_solicitacao = reactive.value(None, name="contexto_solicitacao")
    documento_aprovado = reactive.value(False, name="documento_aprovado")
    feedback_documento = reactive.value(None, name="feedback_documento")
    aviso_documento = reactive.value(None, name="aviso_documento")
    _conferencia_doc: dict[str, asyncio.Task | None] = {"tarefa": None}

    def _parar_conferencia_ao_fechar() -> None:
        tarefa = _conferencia_doc["tarefa"]
        if tarefa is not None and not tarefa.done():
            tarefa.cancel()

    session.on_ended(_parar_conferencia_ao_fechar)
    itens_ativos = reactive.value([1], name="itens_ativos")
    cliques_remover: dict[tuple[int, int], int] = {}
    _envio_em_curso: dict[str, bool] = {"ativo": False}
    _envio_control_em_curso: dict[str, object] = {"ativo": False, "tarefa": None}
    geracao_modal = reactive.value(0, name="geracao_modal")
    materiais = reactive.value({}, name="materiais")
    material_aberto = reactive.value(None, name="material_aberto")
    geracao_material = reactive.value(0, name="geracao_material")
    aviso_material = reactive.value(None, name="aviso_material")
    identificador_lido = reactive.value("", name="identificador_lido")
    leitura_material = reactive.value(None, name="leitura_material")
    digitar_identificador = reactive.value(False, name="digitar_identificador")
    aviso_leitura = reactive.value(None, name="aviso_leitura")
    _fotos_lidas: dict[str, str] = {}
    _leitura_material: dict[str, asyncio.Task | None] = {"tarefa": None}
    _gravacao_material: dict[str, asyncio.Task | None] = {"tarefa": None}
    _material_em_curso: dict[str, bool] = {"ativo": False}
    cliques_material: dict[tuple[int, int], int] = {}

    async def _linha_cliente(chave_cli: str) -> dict | None:
        base = await clientes_geral()
        encontrada = base.filter(pl.col("CHAVE_CLI") == chave_cli)
        if encontrada.height == 0:
            return None
        return encontrada.row(0, named=True)

    def _mensagens_bloqueio(linha: dict) -> list[str]:
        mensagens = []
        if linha.get("Status Cad") == "Bloqueado":
            faltando = []
            if not str(linha.get("PROPRIETARIO") or "").strip():
                faltando.append("nome do responsável")
            if not linha.get("CPF_PROP") or str(linha.get("CPF_PROP")) == "0":
                faltando.append("CPF do responsável")
            if not linha.get("FONE") or str(linha.get("FONE")) == "0":
                faltando.append("telefone do responsável")
            if not str(linha.get("EMAIL_PROP") or "").strip():
                faltando.append("e-mail do responsável")
            mensagens.append("não possui no control: " + ", ".join(faltando))
        if linha.get("Status CEV") not in (None, "Disponível"):
            mensagens.append("Já possui comodato ativo")
        if linha.get("Prazos Esgotados Material") is not None:
            mensagens.append("Está bloqueado por que a revenda possui inadimplências com CEV's antigos.")
        if linha.get("Status Tit") not in (None, "Disponível"):
            mensagens.append("Possui título(s) em aberto.")
        return mensagens or ["Solicitação bloqueada."]

    @reactive.effect
    @reactive.event(input.clique_solicitar)
    async def _abrir_modal_solicitar():
        dados = input.clique_solicitar()
        linha = await _linha_cliente(dados["chave_cli"])
        if linha is None:
            return
        if linha.get("Solicitacao") != "\u2795":
            texto = f"O cliente {linha.get('NOME') or ''} " + "; ".join(_mensagens_bloqueio(linha))
            ui.modal_show(modal_aviso(texto), session=session)
            return

        documento_aprovado.set(bool(linha.get("SEM_DOC")))
        feedback_documento.set(None)
        aviso_documento.set(None)
        material_aberto.set(None)
        aviso_material.set(None)
        identificador_lido.set("")
        itens_ativos.set([1])
        geracao_modal.set(geracao_modal() + 1)
        contexto_solicitacao.set(
            {
                "chave_cli": dados["chave_cli"],
                "cliente": linha.get("COD_RS"),
                "razao_social": linha.get("NOME"),
                "chave": linha.get("CHAVE"),
                "cnpj_rev": linha.get("CNPJ_REV"),
                "cgc_cpf": linha.get("CGC_CPF"),
                "revenda": linha.get("REVENDA"),
                "ven": linha.get("VEN"),
                "proprietario": linha.get("PROPRIETARIO"),
                "sem_doc": bool(linha.get("SEM_DOC")),
                "endereco": linha.get("ENDERECO"),
                "contato": linha.get("CONTATO"),
                "pto_ref": linha.get("PTO_REF"),
                "dia_visit": linha.get("DIA_VISIT"),
                "seq": linha.get("SEQ"),
                "cep": linha.get("CEP"),
                "fone": linha.get("FONE"),
            }
        )
        ui.modal_show(
            _modal_solicitacao(await usuario_atual(), contexto_solicitacao(), geracao_modal()),
            session=session,
        )

    def _modal_solicitacao(usuario: str, ctx: dict, geracao: int) -> ui.Tag:
        return ui.modal(
            ui.div(
                ui.row(
                    ui.column(
                        9,
                        ui.row(
                            ui.column(
                                4,
                                _campo_so_leitura(
                                    f"solic_razao_social_{geracao}", "Razão Social:", str(ctx.get("razao_social") or "")
                                ),
                                ui.output_ui("feedback_razao_social"),
                            ),
                            ui.column(
                                4,
                                _campo_so_leitura(
                                    f"solic_cnpj_{geracao}",
                                    "CNPJ/CPF:",
                                    _cpf_comparavel(ctx.get("chave"))
                                    if str(ctx.get("cgc_cpf") or "").strip().lower() == "cpf"
                                    else str(ctx.get("chave") or ""),
                                ),
                                ui.output_ui("feedback_cnpj"),
                            ),
                            ui.column(
                                4,
                                ui.input_file(
                                    "documento",
                                    "Verificar documento:",
                                    button_label="Enviar",
                                    placeholder="Sem documento",
                                    accept=[".pdf", ".jpg", ".jpeg", ".png", ".webp"],
                                ),
                                class_="comod-solic-documento",
                            ),
                            class_="comod-solic-cabecalho",
                        ),
                        _campo_so_leitura(f"solic_usuario_{geracao}", "Usuário:", _nome_usuario(usuario)),
                        ui.output_ui("itens_solicitacao"),
                        ui.input_action_button("adicionar_item", "Adicionar item", class_="btn-sm"),
                        ui.row(
                            ui.column(
                                3,
                                _campo_so_leitura(
                                    f"solic_data_{geracao}", "Data da solicitação:", date.today().strftime("%d/%m/%Y")
                                ),
                            ),
                            ui.column(9),
                        ),
                        ui.row(
                            ui.column(
                                6,
                                ui.input_action_button(
                                    "bt_envia_solicitacao",
                                    "Solicitar",
                                    class_="btn-sm comod-btn-confirmar",
                                    disabled=not documento_aprovado(),
                                ),
                                class_="text-end",
                            ),
                            ui.column(
                                6,
                                ui.input_action_button(
                                    "bt_cancela_solicitacao", "Cancelar", class_="btn-sm comod-btn-cancelar"
                                ),
                                class_="text-start",
                            ),
                        ),
                    ),
                    ui.column(3, ui.img(src="img/comodato_capa.jpg", class_="comod-solic-capa")),
                    style="align-items: flex-start;",
                ),
                ui.output_ui("aviso_documento_ui"),
                ui.output_ui("painel_material"),
                ui.output_ui("aviso_leitura_ui"),
                class_="comod-solic-modal",
            ),
            title=ui.div("Solicitar comodato", style=f"color: {SIDEBAR_BG}"),
            size="xl",
            easy_close=False,
            footer=None,
        )

    @reactive.effect
    @reactive.event(input.documento)
    def _valida_documento():
        ctx = contexto_solicitacao()
        arquivos = input.documento()
        if ctx is None or not arquivos:
            return
        aviso_documento.set(
            {
                "tipo": "analisando",
                "titulo": "Aguarde...",
                "texto": "Verificando o documento enviado.",
            }
        )
        tarefa = _conferencia_doc["tarefa"]
        if tarefa is not None and not tarefa.done():
            tarefa.cancel()
        _conferencia_doc["tarefa"] = asyncio.create_task(_conferir_documento(ctx, arquivos[0]["datapath"]))

    async def _conferir_documento(ctx: dict, caminho: str) -> None:
        try:
            aprovado, titulo, texto, tipo = await _resultado_conferencia(ctx, caminho)
        except Exception as exc:
            logger.warning(f"Solicitação: falha na conferência do documento -- {exc}")
            aprovado = False
            titulo, tipo = "Algo aconteceu!", "error"
            texto = "Não foi possível concluir a conferência do documento. Tente enviar novamente."
        eh_cnpj = str(ctx.get("cgc_cpf") or "").strip().upper() == "CNPJ"
        campo = "razao_social" if eh_cnpj else "cnpj"
        libera = aprovado
        try:
            async with reactive.lock():
                with reactive.isolate():
                    documento_aprovado.set(libera)
                    feedback_documento.set(
                        {
                            "campo": campo,
                            "mensagem": "Compatível" if aprovado else "Dados não compatíveis",
                            "sucesso": aprovado,
                        }
                    )
                    aviso_documento.set({"tipo": tipo, "titulo": titulo, "texto": texto})
                ui.update_action_button("bt_envia_solicitacao", disabled=not libera, session=session)
                await reactive.flush()
        except Exception as exc:
            logger.warning(f"Solicitação: não deu pra mostrar o resultado da conferência -- {exc}")

    async def _resultado_conferencia(ctx: dict, caminho: str) -> tuple[bool, str, str, str]:
        extraido = await asyncio.to_thread(ocr.extrair_doc, caminho, ocr.TIPO_IDENTIDADE)
        if extraido.get("api_offline"):
            return True, "Tudo certo!", "Documento recebido com sucesso.", "success"

        nome_doc = str(extraido.get("nome_completo") or "").strip()
        cpf_doc = "".join(c for c in str(extraido.get("cpf") or "") if c.isdigit())
        texto_doc = str(extraido.get("texto") or "")
        cpfs_doc = [cpf_doc, *(extraido.get("cpfs") or [])]
        tipo_lido = extraido.get("tipo_normalizado")
        motor = extraido.get("motor") or ""
        if motor == "local" and tipo_lido and tipo_lido != ocr.TIPO_IDENTIDADE:
            return (
                False,
                "Documento não reconhecido",
                f"O arquivo parece ser {extraido.get('tipo_documento') or 'outro documento'}."
                " Envie um documento do responsável com o nome e o CPF (RG, CNH ou CPF).",
                "error",
            )
        nada_lido = nome_doc in ("", "Nao tem") and not cpf_doc and not texto_doc
        if nada_lido:
            return (
                False,
                "Documento não reconhecido",
                "Não foi possível ler nome nem CPF no arquivo enviado. Envie uma foto nítida"
                " (ou PDF) do documento do responsável, sem cortes e sem reflexo.",
                "error",
            )

        eh_cnpj = str(ctx.get("cgc_cpf") or "").strip().upper() == "CNPJ"
        if eh_cnpj:
            responsavel_cadastrado = [ctx.get("proprietario")]
            if _nome_confere(motor, nome_doc, responsavel_cadastrado):
                return True, "Tudo certo!", "Documento confere com o responsável cadastrado.", "success"
            socios = await asyncio.to_thread(cnpj_api.dados_cnpj, ctx["chave"])
            candidatos = socios if isinstance(socios, list) else [socios]
            if _nome_confere(motor, nome_doc, candidatos):
                return True, "Tudo certo!", "Documento confere com os sócios registrados na Receita.", "success"
            if motor == "local" and nome_doc in ("", "Nao tem"):
                return (
                    False,
                    "Documento não reconhecido",
                    "Não foi possível ler o nome do titular no documento. Envie uma foto nítida"
                    " (ou PDF) do documento do responsável, sem cortes e sem reflexo.",
                    "error",
                )
            responsavel = str(ctx.get("proprietario") or "").strip() or "(sem responsável cadastrado)"
            nome_lido = f'O nome do documento ("{nome_doc}")' if nome_doc not in ("", "Nao tem") else "O documento"
            return (
                False,
                "Algo aconteceu!",
                f"{nome_lido} não corresponde ao responsável cadastrado"
                f' ("{responsavel}") nem aos sócios registrados na Receita.',
                "error",
            )

        cpf_cadastro = _cpf_comparavel(ctx.get("chave"))
        cpfs_comparaveis = [_cpf_comparavel(cpf) for cpf in cpfs_doc if cpf]
        if cpf_cadastro in cpfs_comparaveis:
            return True, "Tudo certo!", "CPF do documento confere com o do cadastro.", "success"
        return (
            False,
            "Algo aconteceu!",
            f'O CPF do documento ("{cpf_doc or "não encontrado"}") não corresponde ao CPF do cadastro deste cliente.',
            "error",
        )

    @render.ui
    def aviso_documento_ui():
        aviso = aviso_documento()
        if aviso is None:
            return None
        if aviso["tipo"] == "analisando":
            corpo = ui.div(
                ui.div(class_="comod-aviso-girando"),
                ui.div(aviso["titulo"], class_="aviso-titulo"),
                ui.div(aviso["texto"], class_="aviso-texto"),
                class_="aviso-corpo",
            )
        else:
            corpo = ui.TagList(
                corpo_aviso(aviso["texto"], titulo=aviso["titulo"], tipo=aviso["tipo"]),
                ui.div(
                    ui.input_action_button("fechar_aviso_doc", "OK", class_="btn-sm comod-btn-confirmar"),
                    class_="text-center",
                ),
            )
        return ui.div(ui.div(corpo, class_="comod-aviso-caixa"), class_="comod-aviso-sobreposto")

    @reactive.effect
    @reactive.event(input.fechar_aviso_doc)
    def _fechar_aviso_documento():
        aviso_documento.set(None)

    @render.ui
    def feedback_razao_social():
        fb = feedback_documento()
        return _feedback_documento_ui(fb if fb and fb["campo"] == "razao_social" else None)

    @render.ui
    def feedback_cnpj():
        fb = feedback_documento()
        return _feedback_documento_ui(fb if fb and fb["campo"] == "cnpj" else None)

    @reactive.effect
    @reactive.event(input.adicionar_item)
    def _adicionar_item():
        ativos = itens_ativos()
        itens_ativos.set(ativos + [(max(ativos) if ativos else 0) + 1])

    @reactive.effect
    def _remover_item():
        ativos = itens_ativos()
        geracao = geracao_modal()
        remover = []
        for indice in ativos:
            cliques = _valor_input_seguro(input, f"item_remover_{geracao}_{indice}") or 0
            if cliques > cliques_remover.get((geracao, indice), 0):
                remover.append(indice)
            cliques_remover[(geracao, indice)] = cliques
        if remover and len(ativos) > len(remover):
            itens_ativos.set([i for i in ativos if i not in remover])

    def identificador_da_linha(indice: int) -> str:
        return str(materiais().get((geracao_modal(), indice), {}).get("identificador") or "")

    def _identificador_do_item(indice: int, usa_foto: bool) -> str:
        return identificador_da_linha(indice) if usa_foto else ""

    @reactive.effect
    async def _abrir_painel_material():
        if not await pode_foto_material():
            return
        geracao = geracao_modal()
        for indice in itens_ativos():
            cliques = _valor_input_seguro(input, f"item_matid_{geracao}_{indice}") or 0
            if not isinstance(cliques, int):
                continue
            anterior = cliques_material.get((geracao, indice), 0)
            cliques_material[(geracao, indice)] = cliques
            if cliques > anterior:
                with reactive.isolate():
                    ja_cadastrado = identificador_da_linha(indice)
                identificador_lido.set(ja_cadastrado)
                aviso_material.set(None)
                aviso_leitura.set(None)
                leitura_material.set(None)
                digitar_identificador.set(False)
                _fotos_lidas.clear()
                geracao_material.set(geracao_material() + 1)
                material_aberto.set(indice)
                return

    @reactive.effect
    def _ler_etiqueta_escolhida():
        if material_aberto() is None:
            return
        arquivos = _valor_input_seguro(input, f"foto_ident_{geracao_material()}")
        if not arquivos:
            return
        caminho = arquivos[0]["datapath"]
        if _fotos_lidas.get("ident") == caminho:
            return
        _fotos_lidas["ident"] = caminho
        aviso_leitura.set(
            {
                "tipo": "analisando",
                "titulo": "Lendo a etiqueta...",
                "texto": "Procurando o número de série na foto. Isso leva alguns segundos.",
            }
        )
        tarefa = _leitura_material["tarefa"]
        if tarefa is not None and not tarefa.done():
            tarefa.cancel()
        _leitura_material["tarefa"] = asyncio.create_task(_ler_etiqueta(caminho, str(arquivos[0].get("name") or "")))

    async def _ler_etiqueta(caminho: str, nome: str = "") -> None:
        try:
            lida = await asyncio.to_thread(mc.ler_etiqueta, caminho, nome)
        except Exception as exc:
            logger.warning(f"Solicitação: falha ao ler a etiqueta do material -- {exc}")
            lida = {"situacao": "erro", "serial": "", "linha": {}}

        serial = str(lida.get("serial") or "")
        if serial:
            detalhes = _descricao_equipamento(lida.get("linha") or {})
            aviso = {
                "tipo": "success",
                "titulo": "Etiqueta lida",
                "texto": f"Número de série: {serial}." + (f" ({detalhes})" if detalhes else ""),
            }
        elif lida.get("situacao") == "api_offline":
            aviso = {
                "tipo": "warning",
                "titulo": "Serviço indisponível no momento",
                "texto": (
                    "Não foi possível ler a etiqueta agora, então digite o identificador do"
                    " produto. " + EXPLICA_NUMERO + " Ele é obrigatório: sem o número o"
                    " material não pode ser solicitado."
                ),
            }
        else:
            aviso = {
                "tipo": "error",
                "titulo": "Número não reconhecido",
                "texto": (
                    "A foto chegou, mas nenhum número de série foi reconhecido nela."
                    " Envie outra foto da etiqueta, mais perto e com o número legível."
                ),
            }
        async with reactive.lock():
            with reactive.isolate():
                leitura_material.set(lida if serial else None)
                identificador_lido.set(serial)
                aviso_leitura.set(aviso)
                if lida.get("situacao") == "api_offline":
                    digitar_identificador.set(True)
            await reactive.flush()

    @render.ui
    def aviso_leitura_ui():
        aviso = aviso_leitura()
        if aviso is None:
            return None
        if aviso["tipo"] == "analisando":
            corpo = ui.div(
                ui.div(class_="comod-aviso-girando"),
                ui.div(aviso["titulo"], class_="aviso-titulo"),
                ui.div(aviso["texto"], class_="aviso-texto"),
                class_="aviso-corpo",
            )
        else:
            corpo = ui.TagList(
                corpo_aviso(aviso["texto"], titulo=aviso["titulo"], tipo=aviso["tipo"]),
                ui.div(
                    ui.input_action_button("bt_ok_leitura", "OK", class_="btn-sm comod-btn-confirmar"),
                    class_="text-center",
                ),
            )
        return ui.div(
            ui.div(corpo, class_="comod-aviso-caixa"),
            class_="comod-leitura-sobreposto",
        )

    @reactive.effect
    @reactive.event(input.bt_ok_leitura)
    def _fechar_aviso_leitura():
        aviso_leitura.set(None)

    @render.ui
    def painel_material():
        indice = material_aberto()
        if indice is None:
            return None
        with reactive.isolate():
            geracao = geracao_material()
        corpo = ui.TagList(
            ui.div("Fotos do material", class_="aviso-titulo"),
            ui.div(
                "São duas, e as duas são obrigatórias: a etiqueta de identificação do"
                " refrigerador/freezer e o próprio material. Escolha primeiro a foto da"
                " etiqueta: o número de série sai dela. Se o serviço de leitura estiver fora"
                " do ar, o campo do número abre para você digitar.",
                class_="aviso-texto",
            ),
            ui.input_file(
                f"foto_ident_{geracao}",
                "Foto da etiqueta de identificação:",
                button_label=_rotulo_enviar_foto(),
                placeholder="Sem foto",
                accept=mc.TIPOS_ACEITOS,
            ),
            ui.input_file(
                f"foto_material_{geracao}",
                "Foto do material:",
                button_label=_rotulo_enviar_foto(),
                placeholder="Sem foto",
                accept=mc.TIPOS_ACEITOS,
            ),
            ui.output_ui("campo_identificador_material"),
            ui.output_ui("aviso_material_ui"),
            ui.div(
                ui.input_action_button("bt_salva_material", "Salvar", class_="btn-sm comod-btn-confirmar"),
                ui.input_action_button("bt_fecha_material", "Cancelar", class_="btn-sm comod-btn-cancelar"),
                class_="comod-material-botoes",
            ),
        )
        return ui.div(
            ui.div(corpo, class_="comod-aviso-caixa comod-material-caixa"),
            class_="comod-material-sobreposto",
        )

    @render.ui
    def campo_identificador_material():
        if digitar_identificador():
            return ui.div(
                ui.input_text(
                    f"ident_digitado_{geracao_material()}",
                    "Número de série:",
                    value=identificador_lido(),
                    placeholder="Digite o número de série do aparelho",
                ),
                class_="comod-campo-serial-aberto",
            )
        return _campo_serial_travado(f"ident_material_{geracao_material()}", identificador_lido())

    @render.ui
    def aviso_material_ui():
        aviso = aviso_material()
        if aviso is None:
            return None
        if aviso["tipo"] == "analisando":
            corpo = ui.div(
                ui.div(class_="comod-aviso-girando"),
                ui.div(aviso["texto"], class_="aviso-texto"),
                class_="comod-material-aviso",
            )
        else:
            corpo = ui.div(
                corpo_aviso(aviso["texto"], titulo=aviso["titulo"], tipo=aviso["tipo"]),
                class_="comod-material-aviso",
            )
        if not aviso.get("fecha"):
            return corpo
        return ui.TagList(
            corpo,
            ui.div(
                ui.input_action_button("bt_ok_material", "OK", class_="btn-sm comod-btn-confirmar"),
                class_="text-center",
            ),
        )

    def _fechar_painel_material() -> None:
        material_aberto.set(None)
        aviso_material.set(None)

    @reactive.effect
    @reactive.event(input.bt_fecha_material)
    def _cancelar_painel_material():
        _fechar_painel_material()

    @reactive.effect
    @reactive.event(input.bt_ok_material)
    def _confirmar_aviso_material():
        _fechar_painel_material()

    @reactive.effect
    @reactive.event(input.bt_salva_material)
    async def _salvar_material():
        indice = material_aberto()
        ctx = contexto_solicitacao()
        if indice is None or ctx is None:
            return
        if not await pode_foto_material():
            return
        geracao = geracao_material()
        fotos_ident = _valor_input_seguro(input, f"foto_ident_{geracao}")
        fotos_material = _valor_input_seguro(input, f"foto_material_{geracao}")
        if not fotos_ident or not fotos_material:
            aviso_material.set(
                {
                    "tipo": "warning",
                    "titulo": "Faltou foto",
                    "texto": "Envie as duas: a foto da etiqueta de identificação e a do material.",
                }
            )
            return
        digitado = ""
        if digitar_identificador():
            digitado = str(_valor_input_seguro(input, f"ident_digitado_{geracao}") or "").strip()
            if not digitado:
                aviso_material.set(
                    {
                        "tipo": "warning",
                        "titulo": "Falta o identificador",
                        "texto": (
                            "O serviço de leitura não respondeu, então o número precisa ser digitado. " + EXPLICA_NUMERO
                        ),
                    }
                )
                return
        lida = leitura_material()
        if not digitado and (not lida or not lida.get("serial")):
            aviso_material.set(
                {
                    "tipo": "warning",
                    "titulo": "Sem o número de série",
                    "texto": (
                        "A etiqueta enviada não teve o número reconhecido. Envie outra foto da"
                        " etiqueta, mais perto e com o número legível."
                    ),
                }
            )
            return
        if _material_em_curso["ativo"]:
            return
        _material_em_curso["ativo"] = True
        aviso_material.set(
            {
                "tipo": "analisando",
                "titulo": "Aguarde...",
                "texto": f"Guardando as fotos do equipamento {digitado or lida['serial']}.",
            }
        )
        tarefa = _gravacao_material["tarefa"]
        if tarefa is not None and not tarefa.done():
            tarefa.cancel()
        _gravacao_material["tarefa"] = asyncio.create_task(
            _cadastrar_material(indice, ctx, fotos_ident[0], fotos_material[0], lida, digitado)
        )

    async def _cadastrar_material(
        indice: int, ctx: dict, foto_ident: dict, foto_material: dict, lida: dict, digitado: str = ""
    ) -> None:
        codcomp = str(_codcomp_da_linha(indice) or "")
        try:
            produto, codred = await _dados_catalogo(codcomp)
            usuario = await usuario_atual()
            resultado = await asyncio.to_thread(
                partial(
                    mc.registrar,
                    foto_ident["datapath"],
                    foto_ident["name"],
                    foto_material["datapath"],
                    foto_material["name"],
                    ctx.get("revenda") or "",
                    ctx.get("cnpj_rev") or "",
                    ctx.get("cliente") or "",
                    _codigo_do_cliente(ctx.get("cliente")),
                    codcomp,
                    produto,
                    usuario,
                    serial_informado=digitado,
                    executar=True,
                    leitura=None if digitado else lida,
                    codred=codred,
                )
            )
        except Exception as exc:
            logger.warning(f"Solicitação: falha ao cadastrar o material -- {exc}")
            resultado = {"situacao": "erro", "serial": "", "linha": {}}
        finally:
            _material_em_curso["ativo"] = False

        async with reactive.lock():
            with reactive.isolate():
                _concluir_cadastro_material(indice, resultado)
            await reactive.flush()

    def _concluir_cadastro_material(indice: int, resultado: dict) -> None:
        situacao = resultado.get("situacao")
        serial = str(resultado.get("serial") or "")
        if situacao == "erro":
            aviso_material.set(
                {
                    "tipo": "error",
                    "titulo": "Não foi possível salvar",
                    "texto": "O cadastro do material não foi gravado. Tente novamente em instantes.",
                }
            )
            return
        if situacao == "api_offline":
            digitar_identificador.set(True)
            aviso_material.set(
                {
                    "tipo": "warning",
                    "titulo": "Serviço indisponível no momento",
                    "texto": (
                        "Não foi possível ler a etiqueta agora, então digite o identificador do"
                        " produto e salve de novo. " + EXPLICA_NUMERO
                    ),
                }
            )
            return
        if situacao == "sem_serial" or not serial:
            aviso_material.set(
                {
                    "tipo": "warning",
                    "titulo": "Número não reconhecido",
                    "texto": (
                        "A foto chegou, mas nenhum número de série foi reconhecido nela. Envie"
                        " outra foto da etiqueta, mais perto e com o número legível."
                    ),
                }
            )
            return

        linha = resultado.get("linha") or {}
        materiais.set(
            {
                **materiais(),
                (geracao_modal(), indice): {
                    "identificador": serial,
                    "novo": situacao == "novo",
                    "modelo": linha.get("MODELO") or "",
                    "marca": linha.get("MARCA") or "",
                    "fabricante": linha.get("FABRICANTE") or "",
                },
            }
        )
        identificador_lido.set(serial)
        if situacao == "novo":
            _fechar_painel_material()
            ui.notification_show(
                f"Material {serial} cadastrado"
                + (f" -- {_descricao_equipamento(linha)}." if _descricao_equipamento(linha) else "."),
                type="message",
                duration=6,
                session=session,
            )
            return
        completou = resultado.get("preenchidos") or []
        detalhes = _descricao_equipamento(linha)
        texto = f"O equipamento {serial} já estava cadastrado, então ele foi aproveitado."
        if detalhes:
            texto += f" ({detalhes})"
        if completou:
            texto += " A foto nova completou: " + ", ".join(c.lower() for c in completou) + "."
        aviso_material.set(
            {
                "tipo": "warning",
                "titulo": "Equipamento já cadastrado",
                "fecha": True,
                "texto": texto,
            }
        )

    def _descricao_equipamento(linha: dict) -> str:
        partes = [linha.get(coluna) or "" for coluna in ("FABRICANTE", "MODELO", "MARCA")]
        return " / ".join(p for p in partes if p)

    def _codcomp_da_linha(indice: int):
        return _valor_input_seguro(input, f"item_produto_{geracao_modal()}_{indice}")

    async def _dados_catalogo(codcomp: str) -> tuple[str, str]:
        if not codcomp:
            return "", ""
        produtos = await produtos_disponiveis()
        if produtos.height == 0:
            return "", ""
        linha = produtos.filter(pl.col("CODCOMP") == codcomp)
        if linha.height == 0:
            return "", ""
        linha = linha.row(0, named=True)
        codred = linha.get("CODRED")
        return (str(linha.get("CODPROD") or ""), str(int(codred)) if codred is not None else "")

    @reactive.calc
    async def produtos_disponiveis() -> pl.DataFrame:
        ctx = contexto_solicitacao()
        if ctx is None:
            return pl.DataFrame()
        return await asyncio.to_thread(d.produtos_solicita, ctx["cnpj_rev"])

    @render.ui
    async def itens_solicitacao():
        geracao = geracao_modal()

        def id_campo(campo: str, indice: int) -> str:
            return f"item_{campo}_{geracao}_{indice}"

        linhas = []
        produtos = await produtos_disponiveis()
        ativos = itens_ativos()
        foto_liberada = await pode_foto_material()
        for indice in ativos:
            tipo_atual = _valor_input_seguro(input, id_campo("tipo", indice))
            produto_atual = _valor_input_seguro(input, id_campo("produto", indice))
            with reactive.isolate():
                qtd_atual = _valor_input_seguro(input, id_campo("qtd", indice)) or 1
            produtos_do_tipo = (
                produtos.filter(pl.col("TIPO") == tipo_atual) if (tipo_atual and produtos.height) else produtos.clear()
            )
            nome_produto = ""
            if produto_atual and produtos_do_tipo.height:
                escolhido = produtos_do_tipo.filter(pl.col("CODCOMP") == produto_atual)
                if escolhido.height:
                    nome_produto = str(escolhido.row(0, named=True).get("PRODUTO") or "")
            usa_foto = foto_liberada and mc.produto_pede_foto(tipo_atual, nome_produto)
            if usa_foto:
                matid_atual = identificador_da_linha(indice)
            else:
                with reactive.isolate():
                    matid_atual = _valor_input_seguro(input, id_campo("matid", indice)) or ""
            opcoes_produto = {row["CODCOMP"]: row["CODPROD"] for row in produtos_do_tipo.iter_rows(named=True)}
            if produto_atual not in opcoes_produto:
                produto_atual = None

            valor_produto = ""
            if produto_atual:
                linha_produto = produtos_do_tipo.filter(pl.col("CODCOMP") == produto_atual)
                if linha_produto.height:
                    preco = linha_produto.row(0, named=True).get("PRECO")
                    valor_produto = "" if preco is None else preco

            linhas.append(
                ui.row(
                    ui.column(
                        2,
                        ui.input_selectize(
                            id_campo("tipo", indice),
                            "Tipo",
                            choices={"": "Selecione...", "Material": "Material", "Vasilhame": "Vasilhame"},
                            selected=tipo_atual or "",
                            options=_OPCOES_LISTA_ITEM,
                        ),
                    ),
                    ui.column(
                        3,
                        ui.input_selectize(
                            id_campo("produto", indice),
                            "Item",
                            choices={"": "Selecione...", **opcoes_produto},
                            selected=produto_atual or "",
                            options={**_OPCOES_LISTA_ITEM, "placeholder": "Selecione..."},
                        ),
                    ),
                    ui.column(
                        2,
                        _campo_material(id_campo("matid", indice), matid_atual)
                        if usa_foto
                        else ui.input_text(
                            id_campo("matid", indice),
                            "Id Prod",
                            value=matid_atual,
                            placeholder="Identificador",
                        ),
                    ),
                    ui.column(2, ui.input_numeric(id_campo("qtd", indice), "Qtd", value=qtd_atual, min=1)),
                    ui.column(
                        1,
                        ui.input_selectize(
                            id_campo("prazo", indice),
                            "Prazo",
                            choices=["1 ano", "30 dias"] if tipo_atual else [],
                            selected=_valor_input_seguro(input, id_campo("prazo", indice)),
                            options={**_OPCOES_LISTA_ITEM, "placeholder": ""},
                        ),
                    ),
                    ui.column(
                        2,
                        ui.div(
                            _campo_so_leitura(id_campo("valor", indice), "Valor:", str(valor_produto))
                            .add_class("flex-grow-1")
                            .add_style("min-width: 0;"),
                            ui.input_action_button(
                                id_campo("remover", indice),
                                None,
                                icon=icon_svg("xmark", a11y="deco"),
                                class_="btn-sm comod-item-remover",
                                title="Remover este item",
                                disabled=len(ativos) <= 1,
                            ),
                            class_="d-flex align-items-end gap-1",
                        ),
                    ),
                    class_="comod-item-linha",
                )
            )
        return ui.TagList(*linhas)

    @reactive.effect
    @reactive.event(input.bt_cancela_solicitacao)
    def _cancelar_solicitacao():
        contexto_solicitacao.set(None)
        ui.modal_remove(session=session)

    @reactive.effect
    @reactive.event(input.bt_envia_solicitacao)
    async def _enviar_solicitacao():
        ctx = contexto_solicitacao()
        if ctx is None or not documento_aprovado():
            return
        if _envio_em_curso["ativo"]:
            return
        _envio_em_curso["ativo"] = True
        try:
            await _gravar_solicitacao(ctx)
        finally:
            _envio_em_curso["ativo"] = False

    def _chave_item(codcomp, produto, prazo, tipo, data) -> tuple[str, str, str, str, str]:
        return str(codcomp), str(produto), str(prazo), str(tipo), str(data)

    def _consolidar_itens(linhas: list[dict]) -> list[dict]:
        juntas: dict[tuple[str, str, str, str, str], dict] = {}
        for linha in linhas:
            chave = _chave_item(linha["CODCOMP"], linha["PRODUTO"], linha["PRAZO"], linha["TIPO"], linha["DATA"])
            if chave in juntas:
                juntas[chave]["QTD"] += linha["QTD"]
            else:
                juntas[chave] = dict(linha)
        return list(juntas.values())

    async def _pendentes_do_cliente(ctx: dict) -> set[tuple[str, str]]:
        base = await solicitacoes_pendentes()
        if base.height == 0:
            return set()
        cliente = str(ctx.get("cliente") or "").strip()
        revenda = str(ctx.get("revenda") or "").strip().upper()
        do_cliente = base.filter(
            (pl.col("CLIENTE").cast(pl.Utf8).str.strip_chars() == cliente)
            & (pl.col("REVENDA").cast(pl.Utf8).str.strip_chars().str.to_uppercase() == revenda)
        )
        return {
            _chave_item(linha["CODCOMP"], linha["PRODUTO"], linha["PRAZO"], linha["TIPO"], linha["DATA"])
            for linha in do_cliente.iter_rows(named=True)
        }

    async def _gravar_solicitacao(ctx: dict) -> None:
        produtos = await produtos_disponiveis()
        usuario = await usuario_atual()
        foto_liberada = await pode_foto_material()
        geracao = geracao_modal()
        linhas = []
        for indice in itens_ativos():
            tipo = input[f"item_tipo_{geracao}_{indice}"]()
            prazo = input[f"item_prazo_{geracao}_{indice}"]()
            codcomp = input[f"item_produto_{geracao}_{indice}"]()
            qtd = input[f"item_qtd_{geracao}_{indice}"]()
            if not tipo or not prazo or not codcomp or not qtd or qtd < 1:
                ui.notification_show("Verifique todos os campos!", type="error", duration=5, session=session)
                return
            produto_linha = produtos.filter(pl.col("CODCOMP") == codcomp)
            if produto_linha.height == 0:
                ui.notification_show(
                    "Item fora do catálogo desta revenda. Escolha o item de novo.",
                    type="error",
                    duration=8,
                    session=session,
                )
                return
            produto_linha = produto_linha.row(0, named=True)
            preco_catalogo = produto_linha.get("PRECO")
            if preco_catalogo is None or float(preco_catalogo) <= 0:
                motivo = "está sem preço" if preco_catalogo is None else "está com preço zero"
                aviso_documento.set(
                    {
                        "tipo": "warning",
                        "titulo": "Produto sem preço",
                        "texto": (
                            f'"{produto_linha["CODPROD"]}" {motivo} no catálogo e não pode ser'
                            " solicitado. Escolha outro item ou peça o cadastro do preço."
                        ),
                    }
                )
                return
            if foto_liberada and mc.produto_pede_foto(tipo, produto_linha.get("CODPROD")):
                if not materiais().get((geracao, indice), {}).get("identificador"):
                    aviso_documento.set(
                        {
                            "tipo": "warning",
                            "titulo": "Faltam as fotos do material",
                            "texto": (
                                f'"{produto_linha["CODPROD"]}" é refrigerador ou freezer, então'
                                " precisa das duas fotos (a etiqueta de identificação e o"
                                ' material). Clique em "Enviar fotos" na coluna Id Prod dessa'
                                " linha."
                            ),
                        }
                    )
                    return
            identificador = _identificador_do_item(indice, foto_liberada)
            nome_item = str(produto_linha["CODPROD"] or "")
            if identificador:
                nome_item = f"{nome_item} {identificador}"[:120]
            linhas.append(
                sc.montar_linha(
                    cliente=ctx["cliente"],
                    usuario=usuario,
                    item=nome_item,
                    cod_prod=codcomp,
                    unidade=produto_linha.get("UNIDADE", ""),
                    qtd=qtd,
                    preco=produto_linha.get("PRECO", 0),
                    tab_cev=produto_linha.get("TAB_CEV", ""),
                    revenda=ctx["revenda"],
                    endereco=ctx.get("endereco") or "",
                    contato=ctx.get("contato") or "",
                    pto_ref=ctx.get("pto_ref") or "",
                    dia_visit=ctx.get("dia_visit") or "",
                    seq=ctx.get("seq") or "",
                    cep=ctx.get("cep") or "",
                    fone=ctx.get("fone") or "",
                    cnpj=ctx.get("chave") or "",
                    ven=ctx["ven"],
                    prazo=prazo,
                    tipo=tipo,
                )
            )
        if not linhas:
            ui.notification_show("Adicione pelo menos um item.", type="error", duration=5, session=session)
            return

        linhas = _consolidar_itens(linhas)

        pendentes = await _pendentes_do_cliente(ctx)
        inserir, somar = [], []
        for linha in linhas:
            chave = _chave_item(linha["CODCOMP"], linha["PRODUTO"], linha["PRAZO"], linha["TIPO"], linha["DATA"])
            if chave in pendentes:
                somar.append(
                    {
                        "revenda": linha["REVENDA"],
                        "cliente": linha["CLIENTE"],
                        "codcomp": linha["CODCOMP"],
                        "produto": linha["PRODUTO"],
                        "prazo": linha["PRAZO"],
                        "tipo": linha["TIPO"],
                        "data": linha["DATA"],
                        "qtd": linha["QTD"],
                    }
                )
            else:
                inserir.append(linha)

        try:
            gravadas, somadas = await asyncio.to_thread(sc.solicita_comodato, inserir, somar, True)
        except Exception as exc:
            logger.warning(f"Solicitação: falha ao gravar a solicitação -- {exc}")
            aviso_documento.set(
                {
                    "tipo": "error",
                    "titulo": "Não foi possível registrar",
                    "texto": "A solicitação não foi gravada. Tente novamente em instantes.",
                }
            )
            return

        contexto_solicitacao.set(None)
        ui.modal_remove(session=session)
        await _sincronizar_parquet_solicitacoes()
        partes = []
        if gravadas:
            partes.append(f"{gravadas} item(ns) novo(s)")
        if somadas:
            partes.append(f"{somadas} item(ns) somado(s) a uma solicitação já pendente")
        ui.modal_show(
            modal_aviso(
                "Solicitação registrada: " + " e ".join(partes) + '. Confira em "Solicitações pendentes".',
                tipo="success",
            ),
            session=session,
        )

    chave_cliente_detalhes = reactive.value(None, name="chave_cliente_detalhes")

    @reactive.effect
    @reactive.event(input.clique_detalhes)
    def _abrir_modal_detalhes():
        dados = input.clique_detalhes()
        chave_cliente_detalhes.set(dados["chave_cli"])
        ui.modal_show(
            ui.modal(
                ui.div(
                    ui.output_ui("css_largura_tabela_detalhes"),
                    ui.output_data_frame("tabela_detalhes_cliente"),
                    class_="comod-detalhes-modal comod-tabela tabela-resize",
                ),
                title=None,
                size="s",
                easy_close=True,
                footer=None,
            ),
            session=session,
        )

    @reactive.calc
    async def tabela_detalhes_cliente_pronta() -> pd.DataFrame:
        chave = chave_cliente_detalhes()
        if not chave:
            return pd.DataFrame()
        detalhes = await asyncio.to_thread(d.detalhes_cli_inad, chave)
        return await asyncio.to_thread(ti.construir_detalhes_cliente_df, detalhes)

    @render.data_frame
    async def tabela_detalhes_cliente():
        pandas_df = await tabela_detalhes_cliente_pronta()
        return render.DataTable(pandas_df, height="70vh", summary=False, filters=False, selection_mode="none")

    @render.ui
    async def css_largura_tabela_detalhes():
        pandas_df = await tabela_detalhes_cliente_pronta()
        larguras = [ColunaLargura(c, _LARGURA_DETALHES_CLIENTE.get(c, 100)) for c in pandas_df.columns]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_detalhes_cliente')}", larguras))

    @reactive.calc
    async def pode_excecao() -> bool:
        return await acesso_supremo()

    estado_excecao = reactive.value(None, name="estado_excecao")

    @render.ui
    async def bt_excecao_ui():
        if not MOSTRAR_BOTAO_EXCECAO or not await pode_excecao():
            return None
        return ui.input_action_button(
            "bt_excecao",
            "Adicionar exceção",
            icon=icon_svg("user-check"),
            class_="btn-sm comod-btn-cabecalho",
        )

    @reactive.effect
    @reactive.event(input.bt_excecao)
    async def _abrir_modal_excecao():
        if not await pode_excecao():
            return
        estado_excecao.set({"etapa": "abrindo"})
        ui.modal_show(
            ui.modal(ui.output_ui("corpo_excecao"), title=None, size="m", easy_close=True, footer=None),
            session=session,
        )
        asyncio.create_task(_carregar_listas_excecao())

    async def _carregar_listas_excecao() -> None:
        try:
            async with reactive.lock():
                with reactive.isolate():
                    base = await clientes_geral()
                    estado_excecao.set(
                        {
                            "etapa": "form",
                            "clientes": sorted(v for v in base["COD_RS"].cast(pl.Utf8).unique().to_list() if v)
                            if base.height
                            else [],
                            "vendedores": sorted(v for v in base["VEN"].cast(pl.Utf8).unique().to_list() if v)
                            if base.height
                            else [],
                        }
                    )
                await reactive.flush()
        except Exception as exc:
            logger.warning(f"Solicitação: nao deu pra montar o formulário de exceção -- {exc}")

    @render.ui
    def corpo_excecao():
        estado = estado_excecao()
        if estado is None:
            return None
        if estado["etapa"] == "abrindo":
            return _corpo_aguarde(
                "Abrindo...",
                "Carregando a lista de clientes e vendedores da revenda.",
            )
        if estado["etapa"] == "form":
            return ui.div(
                ui.div("Adicionar exceção", class_="comod-excecao-titulo"),
                ui.p(
                    "A exceção serve só para o cliente ou o vendedor que NÃO precisa enviar"
                    " documento para solicitar comodato. Quem estiver na lista passa a poder"
                    " solicitar mesmo com documentação pendente.",
                    class_="comod-excecao-texto",
                ),
                ui.p(
                    "Estrangeiro é diferente: o cliente segue os bloqueios de sempre, mas não passa"
                    " pela conferência do documento na hora de solicitar (ela não reconhece"
                    " documento de fora) e não recebe o contrato por e-mail: o contrato assinado"
                    " sobe pela tela, junto do canhoto e do documento, como no comodato manual.",
                    class_="comod-excecao-texto",
                ),
                ui.p(
                    "Informe o cliente, o vendedor, ou os dois. Vendedor vale para todos os clientes dele.",
                    class_="comod-excecao-texto",
                ),
                ui.input_radio_buttons(
                    "exc_lista",
                    "Tipo:",
                    {ex.LISTA_EXCECAO: "Exceção", ex.LISTA_ESTRANGEIRO: "Estrangeiro"},
                    selected=estado.get("lista_escolhida", ex.LISTA_EXCECAO),
                    inline=True,
                ),
                ui.row(
                    ui.column(
                        7,
                        ui.input_selectize(
                            "exc_cliente",
                            "Cliente:",
                            choices=["", *estado.get("clientes", [])],
                            selected=estado.get("cliente_escolhido", ""),
                            multiple=False,
                            options={
                                "placeholder": "Digite o código ou o nome",
                                "dropdownParent": "body",
                                "dropdownClass": "selectize-dropdown comod-selectize-dropdown",
                            },
                            width="100%",
                        ),
                    ),
                    ui.column(
                        5,
                        ui.input_selectize(
                            "exc_vendedor",
                            "Vendedor:",
                            choices=["", *estado.get("vendedores", [])],
                            selected=estado.get("vendedor_escolhido", ""),
                            multiple=False,
                            options={
                                "placeholder": "Nenhum",
                                "dropdownParent": "body",
                                "dropdownClass": "selectize-dropdown comod-selectize-dropdown",
                            },
                            width="100%",
                        ),
                    ),
                ),
                _aviso_excecao_ui(estado.get("aviso")),
                ui.row(
                    ui.column(
                        12,
                        ui.div(
                            ui.input_action_button(
                                "bt_add_excecao",
                                "Adicionar",
                                class_="btn-sm comod-btn-confirmar",
                            ),
                            ui.input_action_button("bt_fecha_excecao", "Fechar", class_="btn-sm"),
                            class_="d-flex justify-content-center gap-2",
                        ),
                    ),
                ),
                class_="comod-modal-claro",
            )
        if estado["etapa"] == "confirmar":
            efeito = (
                "passará a solicitar comodato sem a conferência do documento, e o contrato"
                " dele sobe pela tela em vez de ir por e-mail"
                if estado.get("lista") == ex.LISTA_ESTRANGEIRO
                else "passará a solicitar comodato sem enviar documento"
            )
            return ui.TagList(
                corpo_aviso(
                    f"{estado['descricao']} {efeito}. Deseja adicionar?",
                    titulo="Tem certeza?",
                    tipo="warning",
                ),
                ui.div(
                    ui.input_action_button("bt_confirma_excecao", "Sim", class_="btn-sm comod-btn-confirmar"),
                    ui.input_action_button("bt_fecha_excecao", "Não", class_="btn-sm"),
                    class_="d-flex justify-content-center gap-2",
                ),
            )
        if estado["etapa"] == "gravando":
            return _corpo_aguarde(
                "Gravando a exceção...",
                "A liberação está sendo registrada no sistema e na lista que a tela lê.",
            )
        return ui.TagList(
            corpo_aviso(estado["texto"], titulo=estado["titulo"], tipo=estado["tipo"]),
            ui.div(
                ui.input_action_button("bt_fecha_excecao", "OK", class_="btn-sm comod-btn-confirmar"),
                class_="text-center",
            ),
        )

    @reactive.effect
    @reactive.event(input.bt_add_excecao)
    async def _revisar_excecao():
        estado = estado_excecao()
        if estado is None or estado.get("etapa") != "form" or not await pode_excecao():
            return
        rotulo_cliente = str(_valor_input_seguro(input, "exc_cliente") or "")
        codcli = _codigo_do_cliente(rotulo_cliente)
        vendedor = str(_valor_input_seguro(input, "exc_vendedor") or "").strip()
        lista = str(_valor_input_seguro(input, "exc_lista") or ex.LISTA_EXCECAO)
        if lista not in ex.LISTAS:
            lista = ex.LISTA_EXCECAO
        escolhido = {"cliente_escolhido": rotulo_cliente, "vendedor_escolhido": vendedor, "lista_escolhida": lista}
        if not codcli and not vendedor:
            estado_excecao.set({**estado, **escolhido, "aviso": "Informe um cliente, um vendedor, ou os dois."})
            return
        base = await clientes_geral()
        revenda = _revenda_da_excecao(base, codcli, vendedor)
        if revenda is None:
            estado_excecao.set(
                {
                    **estado,
                    **escolhido,
                    "aviso": "Não deu pra saber de qual revenda é essa exceção -- abra a página"
                    " pela revenda antes de cadastrar.",
                }
            )
            return
        partes = []
        if codcli:
            partes.append(f"o cliente {codcli}")
        if vendedor:
            partes.append(f"todo cliente do vendedor {vendedor}")
        estado_excecao.set(
            {
                "etapa": "confirmar",
                "revenda": revenda,
                "codcli": codcli,
                "vendedor": vendedor,
                "lista": lista,
                "descricao": f"Em {revenda}, {' e '.join(partes)}",
            }
        )

    @reactive.effect
    @reactive.event(input.bt_confirma_excecao)
    async def _confirmar_excecao():
        estado = estado_excecao()
        if estado is None or estado.get("etapa") != "confirmar" or not await pode_excecao():
            return
        estado_excecao.set({**estado, "etapa": "gravando"})
        usuario = await usuario_atual()
        asyncio.create_task(_gravar_excecao(estado, usuario))

    async def _gravar_excecao(estado: dict, usuario: str) -> None:
        pedidos = [
            (ex.TIPO_CLIENTE, estado["codcli"]),
            (ex.TIPO_VENDEDOR, estado["vendedor"]),
        ]
        try:
            lista = estado.get("lista", ex.LISTA_EXCECAO)
            resultados = [
                await asyncio.to_thread(ex.registrar_excecao, estado["revenda"], tipo, codigo, usuario, lista)
                for tipo, codigo in pedidos
                if codigo
            ]
            novas = sum(1 for r in resultados if r == "adicionada")
            if novas:
                resultado = {
                    "etapa": "resultado",
                    "tipo": "success",
                    "titulo": "Pronto",
                    "texto": (
                        "Estrangeiro adicionado. A solicitação dele não pede mais a conferência do documento."
                        if lista == ex.LISTA_ESTRANGEIRO
                        else "Exceção adicionada. O cliente já pode solicitar sem enviar documento."
                    ),
                }
            else:
                resultado = {
                    "etapa": "resultado",
                    "tipo": "warning",
                    "titulo": "Aviso",
                    "texto": "Essa exceção já estava cadastrada -- nada mudou.",
                }
        except Exception as exc:
            logger.warning(f"Solicitação: falha ao gravar a exceção -- {exc}")
            resultado = {
                "etapa": "resultado",
                "tipo": "error",
                "titulo": "Não foi possível adicionar",
                "texto": "A exceção não foi gravada. Tente novamente.",
            }
        try:
            async with reactive.lock():
                with reactive.isolate():
                    estado_excecao.set(resultado)
                    if resultado["tipo"] == "success":
                        versao_clientes.set(versao_clientes() + 1)
                await reactive.flush()
        except Exception as exc:
            logger.warning(f"Solicitação: nao deu pra mostrar o resultado da exceção -- {exc}")

    @reactive.effect
    @reactive.event(input.bt_fecha_excecao)
    def _fechar_excecao():
        estado_excecao.set(None)
        ui.modal_remove(session=session)

    versao_responsaveis = reactive.value(0, name="versao_responsaveis")
    estado_responsaveis = reactive.value(None, name="estado_responsaveis")
    logins_na_tela: dict[tuple[str, int], str] = {}
    cliques_resp: dict[str, int] = {}

    @render.ui
    async def bt_responsaveis_ui():
        if not await pode_excecao():
            return None
        return ui.input_action_button(
            "bt_responsaveis",
            "Responsáveis",
            icon=icon_svg("user-gear"),
            class_="btn-sm comod-btn-cabecalho",
        )

    @reactive.effect
    @reactive.event(input.bt_responsaveis)
    async def _abrir_modal_responsaveis():
        if not await pode_excecao():
            return
        estado_responsaveis.set({"aviso": None})
        ui.modal_show(
            ui.modal(ui.output_ui("corpo_responsaveis"), title=None, size="l", easy_close=True, footer=None),
            session=session,
        )

    @render.ui
    def corpo_responsaveis():
        estado = estado_responsaveis()
        if estado is None:
            return None
        versao_responsaveis()
        logins_na_tela.clear()
        secoes = []
        for secao, itens in secoes_de_direitos():
            linhas = []
            for chave, frase, logins in itens:
                for posicao, login in enumerate(logins):
                    logins_na_tela[(chave, posicao)] = login
                linhas.append(
                    ui.div(
                        ui.div(
                            ui.div(frase, class_="comod-resp-frase"),
                            ui.div(chave, class_="comod-resp-chave"),
                            class_="comod-resp-rotulo",
                        ),
                        ui.div(
                            ui.div(
                                ui.input_text(f"resp_novo_{chave}", None, placeholder="user.name"),
                                ui.input_action_button(
                                    f"resp_add_{chave}",
                                    None,
                                    icon=icon_svg("plus", a11y="deco"),
                                    class_="btn-sm comod-resp-add",
                                    title="Acrescentar este login",
                                ),
                                class_="comod-resp-entrada",
                            ),
                            ui.div(
                                *[
                                    ui.span(
                                        login,
                                        ui.input_action_button(
                                            f"resp_del_{chave}_{posicao}",
                                            None,
                                            icon=icon_svg("xmark", a11y="deco"),
                                            class_="comod-resp-tirar",
                                            title=f"Tirar {login} desta lista",
                                        ),
                                        class_="comod-resp-chip",
                                    )
                                    for posicao, login in enumerate(logins)
                                ]
                                or [ui.span("Ninguém liberado", class_="comod-resp-vazio")],
                                class_="comod-resp-lista",
                            ),
                            class_="comod-resp-valores",
                        ),
                        class_="comod-resp-item",
                    )
                )
            secoes.append(
                ui.div(
                    ui.div(secao, class_="comod-resp-secao"),
                    *linhas,
                )
            )
        return ui.div(
            ui.div("Responsáveis", class_="comod-excecao-titulo"),
            ui.p(
                "Quem pode cada coisa no painel, por login. Vale no próximo carregamento"
                " de página de quem for incluído ou retirado -- não precisa reiniciar nada.",
                class_="comod-excecao-texto",
            ),
            _aviso_excecao_ui(estado.get("aviso")),
            ui.div(*secoes, class_="comod-resp-corpo"),
            ui.div(
                ui.input_action_button("bt_fecha_responsaveis", "Fechar", class_="btn-sm"),
                class_="d-flex justify-content-center gap-2",
            ),
            class_="comod-modal-claro",
        )

    @reactive.effect
    async def _mexer_nos_responsaveis():
        if estado_responsaveis() is None:
            return
        versao_responsaveis()
        adicionar = remover = None
        for chave, posicao in list(logins_na_tela):
            id_botao = f"resp_del_{chave}_{posicao}"
            cliques = _valor_input_seguro(input, id_botao) or 0
            if cliques > cliques_resp.get(id_botao, 0):
                remover = (chave, logins_na_tela[(chave, posicao)])
            cliques_resp[id_botao] = cliques
        for _secao, itens in secoes_de_direitos():
            for chave, _frase, _logins in itens:
                id_botao = f"resp_add_{chave}"
                cliques = _valor_input_seguro(input, id_botao) or 0
                if cliques > cliques_resp.get(id_botao, 0):
                    with reactive.isolate():
                        adicionar = (chave, str(_valor_input_seguro(input, f"resp_novo_{chave}") or ""))
                cliques_resp[id_botao] = cliques
        if not adicionar and not remover:
            return
        if not await pode_excecao():
            return
        try:
            if adicionar:
                chave, login = adicionar
                aviso = _gravar_responsavel(adicionar_responsavel, chave, login)
                if aviso is None:
                    ui.update_text(f"resp_novo_{chave}", value="", session=session)
            else:
                aviso = _gravar_responsavel(remover_responsavel, *remover)
        except Exception as exc:
            logger.warning(f"Responsáveis: falha inesperada -- {exc}")
            aviso = "Não deu para gravar. Tente de novo."
        estado_responsaveis.set({"aviso": aviso})
        versao_responsaveis.set(versao_responsaveis() + 1)

    def _gravar_responsavel(gravar, chave: str, login: str) -> str | None:
        try:
            resultado = gravar(chave, login)
        except Exception as exc:
            logger.warning(f"Responsáveis: falha ao gravar {chave}/{login} -- {exc}")
            return "Não deu para gravar. Tente de novo."
        if resultado == "login_invalido":
            return "Escreva o login como no exemplo: nome.sobrenome, sem espaço."
        if resultado == "ja_existia":
            return "Esse login já estava nessa lista."
        if resultado == "nao_estava":
            return "Esse login já não estava nessa lista."
        return None

    @reactive.effect
    @reactive.event(input.bt_fecha_responsaveis)
    def _fechar_responsaveis():
        estado_responsaveis.set(None)
        ui.modal_remove(session=session)

    @reactive.effect
    @reactive.event(input.clique_sincronizar)
    async def _sincronizar_cliente():
        dados = input.clique_sincronizar()
        try:
            await cc.sincronizar_cadastro(dados["revenda"], dados["codcli"])
        except Exception as exc:
            logger.warning(f"Solicitação: falha ao sincronizar o cliente {dados.get('codcli')} -- {exc}")
            ui.modal_show(modal_aviso("Erro ao sincronizar. Tente novamente.", tipo="error"), session=session)
            return
        try:
            await asyncio.to_thread(d.regravar_parquet_titulos)
        except Exception as exc:
            logger.warning(f"Solicitação: cadastro sincronizado, mas o parquet não foi regravado -- {exc}")
        versao_clientes.set(versao_clientes() + 1)
        ui.modal_show(modal_aviso("Cadastro sincronizado com o ERP.", tipo="success"), session=session)

    async def _sincronizar_parquet_solicitacoes(regravar: bool = True):
        if regravar:
            try:
                await asyncio.to_thread(d.regravar_parquet_solicitacoes)
            except Exception as exc:
                logger.warning(f"Solicitação: não deu pra regravar o parquet -- {exc}")
        with reactive.isolate():
            proxima = versao_solicitacoes() + 1
        versao_solicitacoes.set(proxima)

    estado_envio = reactive.value(None, name="estado_envio")

    @reactive.effect
    @reactive.event(input.clique_enviar)
    async def _enviar_pedido():
        if not await pode_gerenciar():
            return
        dados = input.clique_enviar()
        pendentes = await solicitacoes_pendentes()
        base = pendentes.filter(
            (pl.col("REVENDA") == dados["revenda"])
            & (pl.col("CLIENTE") == dados["cliente"])
            & (pl.col("DATA") == dados["data"])
            & (pl.col("PRAZO") == dados["prazo"])
            & (pl.col("TIPO") == dados["tipo"])
        )
        if base.height == 0:
            return
        estado_envio.set(
            {
                "etapa": "confirmar",
                "dados": dados,
                "cliente": str(dados.get("cliente") or ""),
                "prazo": str(dados.get("prazo") or ""),
                "tipo": str(dados.get("tipo") or ""),
                "produtos": base["PRODUTO"].to_list(),
            }
        )
        ui.modal_show(
            ui.modal(ui.output_ui("corpo_envio"), title=None, size="s", easy_close=False, footer=None),
            session=session,
        )

    @reactive.effect
    @reactive.event(input.bt_confirma_envio)
    async def _confirmar_envio():
        estado = estado_envio()
        if estado is None or estado.get("etapa") != "confirmar" or not await pode_gerenciar():
            return
        if _envio_control_em_curso["ativo"]:
            return
        _envio_control_em_curso["ativo"] = True
        estado_envio.set({**estado, "etapa": "enviando"})
        _envio_control_em_curso["tarefa"] = asyncio.create_task(_executar_envio(estado["dados"]))

    @reactive.effect
    @reactive.event(input.bt_nega_envio)
    def _fechar_confirmacao_envio():
        estado_envio.set(None)
        ui.modal_remove(session=session)

    async def _executar_envio(dados: dict) -> None:
        mexeu_no_banco = False
        try:
            resultado = await cc.enviar_pedido(
                dados["revenda"], dados["cliente"], dados["data"], dados["prazo"], dados["tipo"]
            )
            if resultado == "consta":
                tipo, titulo, texto = "warning", "Aviso", "Solicitação já enviada."
            elif resultado == "sem_itens":
                tipo, titulo, texto = "warning", "Aviso", "Essa solicitação não está mais pendente."
            else:
                mexeu_no_banco = True
                tipo, titulo, texto = "success", "Pedido gerado", "Pedido gerado no ERP."
        except Exception as exc:
            logger.warning(f"Comodatos: falha ao gerar pedido -- {exc}")
            tipo = "error"
            titulo, texto = cc.erro_amigavel(exc, "nada foi enviado")
        finally:
            _envio_control_em_curso["ativo"] = False
        try:
            await _sincronizar_parquet_solicitacoes(regravar=mexeu_no_banco)
        except Exception as exc:
            logger.warning(f"Solicitação: parquet não regravado após o envio -- {exc}")
        try:
            async with reactive.lock():
                with reactive.isolate():
                    estado_envio.set({"etapa": "resultado", "tipo": tipo, "titulo": titulo, "texto": texto})
                await reactive.flush()
        except Exception as exc:
            logger.warning(f"Solicitação: nao deu pra mostrar o resultado do envio -- {exc}")

    @render.ui
    def corpo_envio():
        estado = estado_envio()
        if estado is None:
            return None
        if estado["etapa"] == "confirmar":
            produtos = estado.get("produtos") or []
            prazo = estado.get("prazo") or ""
            tipo = estado.get("tipo") or ""
            return ui.TagList(
                corpo_aviso(
                    f"Isso gera o pedido de comodato de {estado['cliente']} no ERP"
                    f" ({len(produtos)} produto(s), {tipo.lower()}, prazo {prazo}). Depois de"
                    " enviado, desfazer só é possível cancelando o pré-pedido -- e apenas"
                    " enquanto o ERP não tiver validado.",
                    titulo="Confirmar envio ao ERP?",
                    tipo="warning",
                ),
                ui.tags.ul(*[ui.tags.li(produto) for produto in produtos], class_="comod-confirma-lista"),
                ui.div(
                    ui.input_action_button("bt_confirma_envio", "Sim, enviar", class_="btn-sm comod-btn-confirmar"),
                    ui.input_action_button("bt_nega_envio", "Não", class_="btn-sm"),
                    class_="d-flex justify-content-center gap-2",
                ),
            )
        if estado["etapa"] == "enviando":
            cliente = str(estado.get("cliente") or "").strip()
            return _corpo_aguarde(
                "Enviando ao ERP...",
                f"O pedido de comodato{f' de {cliente}' if cliente else ''} está sendo gravado no"
                " ERP. Isso costuma levar alguns segundos -- não feche esta janela.",
            )
        return ui.TagList(
            corpo_aviso(estado["texto"], titulo=estado["titulo"], tipo=estado["tipo"]),
            ui.div(
                ui.input_action_button("bt_fecha_envio", "OK", class_="btn-sm comod-btn-confirmar"),
                class_="text-center",
            ),
        )

    @reactive.effect
    @reactive.event(input.bt_fecha_envio)
    def _fechar_envio():
        estado_envio.set(None)
        ui.modal_remove(session=session)

    @reactive.effect
    @reactive.event(input.clique_retirar)
    async def _retirar_solicitacao():
        if not await pode_gerenciar():
            return
        dados = input.clique_retirar()
        try:
            removidas = await asyncio.to_thread(
                sc.retira_comodato,
                revenda=dados["revenda"],
                cliente=dados["cliente"],
                produto=dados["produto"],
                emissao=dados["data"],
                tipo=dados["tipo"],
                prazo=dados["prazo"],
                executar=True,
            )
        except Exception as exc:
            logger.warning(f"Solicitação: falha ao retirar o produto -- {exc}")
            ui.modal_show(
                modal_aviso("Não foi possível retirar o produto. Tente novamente.", tipo="error"), session=session
            )
            return
        await _sincronizar_parquet_solicitacoes(regravar=bool(removidas))
        if removidas:
            ui.modal_show(modal_aviso("Produto retirado da solicitação.", tipo="success"), session=session)
        else:
            ui.modal_show(
                modal_aviso(
                    "Esse produto não está mais pendente -- pode já ter sido enviado ou retirado.", tipo="warning"
                ),
                session=session,
            )

    cancelamento_pendente = reactive.value(None, name="cancelamento_pendente")

    async def _itens_da_solicitacao(dados: dict) -> pl.DataFrame:
        base = await solicitacoes_pendentes()
        if base.height == 0:
            return base
        return base.filter(
            (pl.col("REVENDA") == dados["revenda"])
            & (pl.col("CLIENTE") == dados["cliente"])
            & (pl.col("DATA") == dados["data"])
            & (pl.col("PRAZO") == dados["prazo"])
            & (pl.col("TIPO") == dados["tipo"])
        )

    @reactive.effect
    @reactive.event(input.clique_cancelar_solicitacao)
    async def _abrir_confirmacao_cancelamento():
        if not await pode_gerenciar():
            return
        dados = input.clique_cancelar_solicitacao()
        itens = await _itens_da_solicitacao(dados)
        if itens.height == 0:
            ui.modal_show(
                modal_aviso("Essa solicitação não está mais pendente.", tipo="warning"),
                session=session,
            )
            return
        cancelamento_pendente.set(dados)
        ui.modal_show(_modal_confirma_cancelamento(dados, itens), session=session)

    def _modal_confirma_cancelamento(dados: dict, itens: pl.DataFrame) -> ui.Tag:
        emissao = dados["data"]
        data_legivel = f"{emissao[6:8]}/{emissao[4:6]}/{emissao[:4]}" if len(emissao) == 8 else emissao
        produtos = itens["PRODUTO"].to_list()
        return ui.modal(
            corpo_aviso(
                f"Isso retira os {len(produtos)} produto(s) da solicitação de "
                f"{dados['cliente']} ({data_legivel}, prazo {dados['prazo']}). "
                "Nada foi enviado ao ERP ainda, e não há como desfazer.",
                titulo="Cancelar a solicitação toda?",
                tipo="warning",
            ),
            ui.tags.ul(*[ui.tags.li(produto) for produto in produtos], class_="comod-confirma-lista"),
            ui.div(
                ui.input_action_button("bt_confirma_cancelamento", "Sim, cancelar", class_="btn-sm comod-btn-cancelar"),
                ui.input_action_button("bt_nega_cancelamento", "Não, voltar", class_="btn-sm"),
                class_="d-flex justify-content-center gap-2",
            ),
            title=None,
            size="s",
            easy_close=False,
            footer=None,
        )

    @reactive.effect
    @reactive.event(input.bt_nega_cancelamento)
    def _fechar_confirmacao_cancelamento():
        cancelamento_pendente.set(None)
        ui.modal_remove(session=session)

    @reactive.effect
    @reactive.event(input.bt_confirma_cancelamento)
    async def _cancelar_solicitacao_inteira():
        dados = cancelamento_pendente()
        if dados is None or not await pode_gerenciar():
            return
        cancelamento_pendente.set(None)
        try:
            removidas = await asyncio.to_thread(
                sc.retira_solicitacao,
                revenda=dados["revenda"],
                cliente=dados["cliente"],
                emissao=dados["data"],
                prazo=dados["prazo"],
                tipo=dados["tipo"],
                executar=True,
            )
        except Exception as exc:
            logger.warning(f"Solicitação: falha ao cancelar a solicitação -- {exc}")
            ui.modal_show(
                modal_aviso("Não foi possível cancelar a solicitação. Tente novamente.", tipo="error"), session=session
            )
            return
        await _sincronizar_parquet_solicitacoes(regravar=bool(removidas))
        if removidas:
            ui.modal_show(
                modal_aviso(f"Solicitação cancelada ({removidas} produto(s) retirado(s)).", tipo="success"),
                session=session,
            )
        else:
            ui.modal_show(modal_aviso("Essa solicitação não está mais pendente.", tipo="warning"), session=session)


def pag_solicitacao_ui():
    return solicitacao_ui("comod_solic")


def pag_solicitacao_server(versao_cache):
    solicitacao_server("comod_solic", valor_navset="comod_solic", versao_cache=versao_cache)
