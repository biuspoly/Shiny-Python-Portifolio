import sys
from collections.abc import Iterable
from html import escape

import pandas as pd
import polars as pl
from faicons import icon_svg
from shiny.ui import HTML

from core.compat import para_pandas
from core.cores import (
    COMODATO_COLUNA_DESTAQUE,
    COMODATO_ICONE_CANCELAR,
    COMODATO_ICONE_CANHOTO,
    COMODATO_ICONE_CONTRATO,
    COMODATO_ICONE_DOC_PDV,
    COMODATO_ICONE_FALHA_EMAIL,
    COMODATO_ICONE_PDF,
    COMODATO_ICONE_PRIMEIRO_ENVIO,
    COMODATO_ICONE_RECOLHA,
    COMODATO_ICONE_REENVIAR,
    COMODATO_ICONE_TRAVADO,
    COMODATO_LINHA_CONTROL,
    COMODATO_LINHA_DASH,
    COMODATO_LINHA_ESGOTADO,
    COMODATO_PRAZO_ATENCAO_FUNDO,
    COMODATO_PRAZO_ATENCAO_TEXTO,
    COMODATO_PRAZO_CRITICO_FUNDO,
    COMODATO_PRAZO_CRITICO_TEXTO,
    COMODATO_PRAZO_FOLGA_FUNDO,
    COMODATO_PRAZO_FOLGA_TEXTO,
    COMODATO_STATUS_BLOQUEADO,
    COMODATO_STATUS_DISPONIVEL,
)

from . import dados_comodato as dc
from . import informa_comodato as ic
from . import material_comodato as mc


def _icone(nome: str, cor: str, altura: str = "17px") -> str:
    return str(
        icon_svg(nome, height=altura, fill=cor, a11y="deco", margin_left="0", margin_right="0", position="static")
    )


def _icone_pastilha(nome: str, fundo: str, altura: str = "12px") -> str:
    return f'<span class="comod-icone-pastilha" style="background-color: {fundo}">{_icone(nome, "#fff", altura)}</span>'


_ICONE_DOC_PDV = _icone("id-card", COMODATO_ICONE_DOC_PDV, altura="15px")
_ICONE_CONTRATO = _icone("file-contract", COMODATO_ICONE_CONTRATO, altura="15px")
_ICONE_CANHOTO = _icone("receipt", COMODATO_ICONE_CANHOTO, altura="15px")


def _icone_pastilha_com_selo(nome: str, fundo: str, selo: str, cor_selo: str) -> str:
    return (
        f'<span class="comod-icone-com-selo">{_icone_pastilha(nome, fundo)}'
        f'<span class="comod-icone-selo" style="color: {cor_selo}">'
        f"{_icone(selo, cor_selo, altura='10px')}</span></span>"
    )


_ICONE_REENVIAR = _icone_pastilha("envelope", COMODATO_ICONE_REENVIAR)
_ICONE_REENVIAR_FALHOU = _icone_pastilha_com_selo(
    "envelope", COMODATO_ICONE_REENVIAR, "circle-xmark", COMODATO_ICONE_FALHA_EMAIL
)
_ICONE_PRIMEIRO_ENVIO = _icone_pastilha_com_selo(
    "envelope", COMODATO_ICONE_REENVIAR, "circle-plus", COMODATO_ICONE_PRIMEIRO_ENVIO
)


# Portfólio (Shinylive): o Polars do navegador entra em pânico ao juntar texto dentro de group_by().agg().
# Lá, o mesmo agrupamento -- as mesmas regras por coluna -- é feito em pandas.
NO_NAVEGADOR = sys.platform == "emscripten"


def _agrupar_em_pandas(tabela: pl.DataFrame, chaves: list[str], regras: dict, rotulo_conta: str) -> pl.DataFrame:
    df = para_pandas(tabela)
    linhas = []
    for valores, grupo in df.groupby(chaves, sort=False, dropna=False):
        valores = valores if isinstance(valores, tuple) else (valores,)
        linha = dict(zip(chaves, valores, strict=True))
        for coluna in df.columns:
            if coluna in chaves:
                continue
            regra, serie = regras.get(coluna), grupo[coluna]
            if regra == "soma":
                linha[coluna] = serie.sum()
            elif regra == "maior":
                linha[coluna] = serie.max()
            elif regra == "menor":
                linha[coluna] = serie.min()
            elif regra == "conta":
                linha[coluna] = f"{rotulo_conta}{len(grupo)}"
            elif regra in ("unique", "vazio"):
                textos = [str(v).strip() for v in serie if v is not None and not pd.isna(v) and str(v).strip()]
                juntos = ", ".join(dict.fromkeys(textos))
                linha[coluna] = "" if regra == "vazio" and serie.nunique(dropna=False) > 1 else juntos
            else:
                linha[coluna] = serie.iloc[0]
        linhas.append({c: (None if not isinstance(v, str) and pd.isna(v) else v) for c, v in linha.items()})
    return pl.DataFrame(linhas, infer_schema_length=None) if linhas else tabela.head(0)


_ICONE_REENVIAR_TRAVADO = _icone_pastilha("ban", COMODATO_ICONE_TRAVADO)
_ICONE_RECOLHER = _icone_pastilha("truck-ramp-box", COMODATO_ICONE_RECOLHA, altura="13px")
_ICONE_DISTRATO_PDF = _icone_pastilha("file-pdf", COMODATO_ICONE_PDF)
_ICONE_CAMERA = _icone_pastilha("camera", COMODATO_ICONE_RECOLHA, altura="13px")


def _cor_status(valor) -> dict[str, str] | None:
    if pd.isna(valor):
        return None
    cor = COMODATO_STATUS_BLOQUEADO if valor == "Bloqueado" else COMODATO_STATUS_DISPONIVEL
    return {"color": cor, "font-weight": "bold"}


def _estilos_cor_status(pandas_df: pd.DataFrame, colunas: list[str]) -> list[dict]:
    estilos = []
    for coluna in colunas:
        if coluna not in pandas_df.columns:
            continue
        for posicao, valor in enumerate(pandas_df[coluna]):
            estilo = _cor_status(valor)
            if estilo:
                estilos.append({"rows": [posicao], "cols": [coluna], "style": estilo})
    return estilos


def _cor_inadimplente(valor) -> dict[str, str] | None:
    if pd.isna(valor):
        return None
    cor = COMODATO_STATUS_BLOQUEADO if valor == "Sim" else COMODATO_STATUS_DISPONIVEL
    return {"color": cor, "font-weight": "bold"}


def _estilos_cor_inadimplente(pandas_df: pd.DataFrame, coluna: str) -> list[dict]:
    if coluna not in pandas_df.columns:
        return []
    estilos = []
    for posicao, valor in enumerate(pandas_df[coluna]):
        estilo = _cor_inadimplente(valor)
        if estilo:
            estilos.append({"rows": [posicao], "cols": [coluna], "style": estilo})
    return estilos


def _link_botao(rotulo: str, classe: str, data_attrs: dict, titulo: str | None = None) -> str:
    atributos = " ".join(f'data-{chave}="{valor}"' for chave, valor in data_attrs.items())
    return (
        f'<span class="comod-btn-cel {classe}" role="button" tabindex="0" '
        f'title="{titulo or rotulo}" {atributos}>{rotulo}</span>'
    )


COLUNAS_SALDO_NUMERICAS = [
    "Recolha Ano",
    "Empréstimo Ano",
    "Saldo Ano",
    "Recolha Mês",
    "Empréstimo Mês",
    "Saldo Mês",
    "Caixa 1L",
    "Caixa 300",
    "Total MAR 600",
    "Caixa MAR 600",
    "Bônus MAR 600",
    "Caixa 600ml",
]
COLUNAS_SALDO_DESTAQUE = ["Caixa 1L", "Caixa 300", "Total MAR 600"]


def _numero(valor) -> str:
    if pd.isna(valor):
        return ""
    return f"{valor:,.0f}".replace(",", ".")


def construir_saldo_df(tabela: pl.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    if tabela.height == 0:
        return pd.DataFrame(), []
    pandas_df = tabela.pipe(para_pandas)
    estilos = _estilos_cor_status(pandas_df, ["Status PLP", "Status Doc"])
    for coluna in COLUNAS_SALDO_NUMERICAS:
        if coluna in pandas_df.columns:
            pandas_df[coluna] = pandas_df[coluna].map(_numero)
    destaque = [c for c in COLUNAS_SALDO_DESTAQUE if c in pandas_df.columns]
    if destaque:
        estilos.append({"cols": destaque, "style": {"background-color": COMODATO_COLUNA_DESTAQUE}})
    return pandas_df, estilos


def _botao_solicitacao(chave_cli: str, emoji: str) -> str:
    return _link_botao(emoji, "comod-btn-solicitar", {"chave-cli": chave_cli})


def _botao_detalhes(chave_cli: str) -> str:
    return _link_botao("\U0001f50d", "comod-btn-detalhes", {"chave-cli": chave_cli})


def _botao_sincronizar(revenda: str, codcli: str) -> str:
    return _link_botao("\u21a9", "comod-btn-sincronizar", {"revenda": revenda, "codcli": codcli})


_RENOMEIA_CLIENTES = {
    "REVENDA": "Revenda",
    "COD_RS": "Cliente",
    "FANTASIA": "Fantasia",
    "CGC_CPF": "Tipo",
    "CIDADE": "Cidade",
    "PORTE": "Classificação",
    "CANAL": "Canal",
    "VEN": "Ven",
    "subordinacao": "GA",
    "Inadimplente": "Inadimplente",
}
_ORDEM_COLUNAS_CLIENTES = [
    "Revenda",
    "Cliente",
    "Fantasia",
    "Tipo",
    "Cidade",
    "Classificação",
    "Canal",
    "Ven",
    "GA",
    "Inadimplente",
    "Solicitação",
    "Detalhes",
]

COLUNA_CRUA_CLIENTES = {
    **{exibido: cru for cru, exibido in _RENOMEIA_CLIENTES.items()},
    "Solicitação": "Solicitacao",
}


def colunas_clientes_exibidas(mostra_revenda: bool = True) -> list[str]:
    return [c for c in _ORDEM_COLUNAS_CLIENTES if c != "Revenda" or mostra_revenda]


def construir_clientes_solicitacao_df(
    tabela: pl.DataFrame, mostra_revenda: bool = True
) -> tuple[pd.DataFrame, list[dict]]:
    if tabela.height == 0:
        return pd.DataFrame(), []
    pandas_df = tabela.pipe(para_pandas)
    pandas_df["Solicitação"] = [
        HTML(_botao_solicitacao(chave, emoji)) for chave, emoji in zip(pandas_df["CHAVE_CLI"], pandas_df["Solicitacao"])
    ]
    pandas_df["Detalhes"] = [
        HTML(_botao_detalhes(chave)) if inad == "Sim" else ""
        for chave, inad in zip(pandas_df["CHAVE_CLI"], pandas_df["Inadimplente"])
    ]
    estilos = _estilos_cor_inadimplente(pandas_df, "Inadimplente")
    pandas_df = pandas_df.rename(columns=_RENOMEIA_CLIENTES)
    pandas_df = pandas_df[colunas_clientes_exibidas(mostra_revenda)]
    return pandas_df, estilos


CHAVES_GRUPO_SOLICITACAO = ["DATA", "CLIENTE", "PRAZO", "TIPO"]
_SEPARADOR_GRUPO = "|"

_RENOMEIA_SOLICITACOES = {
    "REVENDA": "Revenda",
    "CLIENTE": "Cliente",
    "PRAZO": "Prazo",
    "TIPO": "Tipo",
    "USUARIO": "Usuário",
    "PRODUTO": "Produto",
    "QTD": "Quantidade",
    "DATA": "Emissão",
    "VENC": "Vencimento",
}
_ORDEM_COLUNAS_SOLICITACOES = [
    "Revenda",
    "Cliente",
    "Prazo",
    "Tipo",
    "Usuário",
    "Produto",
    "Quantidade",
    "Valor",
    "Emissão",
    "Vencimento",
    "Enviar",
    "Retirar",
    "Cancelar",
]
_DATAS_SOLICITACOES = ["Emissão", "Vencimento"]

_AGREGACAO_SOLICITACOES = {
    "_VALOR": "soma",
    "REVENDA": "unique",
    "USUARIO": "vazio",
    "PRODUTO": "conta",
    "QTD": "soma",
    "VENC": "menor",
}


def chave_grupo(linha: dict) -> str:
    return _SEPARADOR_GRUPO.join(str(linha.get(coluna) or "") for coluna in CHAVES_GRUPO_SOLICITACAO)


def partes_chave_grupo(chave: str) -> dict:
    valores = chave.split(_SEPARADOR_GRUPO)
    return dict(zip(CHAVES_GRUPO_SOLICITACAO, valores + [""] * len(CHAVES_GRUPO_SOLICITACAO)))


def _valor_em_reais(valor) -> str:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return ""
    formatado = f"{numero:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"R$ {formatado}"


def _agrupar_solicitacoes(tabela: pl.DataFrame, chaves: list[str] | None = None) -> pl.DataFrame:
    if "QTD" in tabela.columns and "PRECO" in tabela.columns:
        tabela = tabela.with_columns((pl.col("QTD") * pl.col("PRECO").fill_null(0)).alias("_VALOR"))
    chaves = chaves or CHAVES_GRUPO_SOLICITACAO
    if NO_NAVEGADOR:
        return _agrupar_em_pandas(tabela, chaves, _AGREGACAO_SOLICITACOES, "Itens solicitados: ")
    agregacoes = []
    for coluna in tabela.columns:
        if coluna in chaves:
            continue
        regra = _AGREGACAO_SOLICITACOES.get(coluna)
        if regra == "soma":
            agregacoes.append(pl.col(coluna).sum())
        elif regra == "menor":
            agregacoes.append(pl.col(coluna).min())
        elif regra == "conta":
            agregacoes.append((pl.lit("Itens solicitados: ") + pl.len().cast(pl.Utf8)).alias(coluna))
        elif regra in ("unique", "vazio"):
            texto = pl.col(coluna).cast(pl.Utf8).str.strip_chars()
            distintos = (
                texto.filter(texto.is_not_null() & (texto.str.len_chars() > 0))
                .unique(maintain_order=True)
                .str.join(", ")
            )
            if regra == "vazio":
                distintos = pl.when(pl.col(coluna).n_unique() <= 1).then(distintos).otherwise(pl.lit(""))
            agregacoes.append(distintos.alias(coluna))
        else:
            agregacoes.append(pl.col(coluna).first())
    return tabela.group_by(chaves, maintain_order=True).agg(agregacoes)


def _celula_grupo_solicitacao(chave: str, cliente: str, aberto: bool) -> str:
    seta = "\u25be" if aberto else "\u25b8"
    return (
        '<span class="comod-btn-cel comod-btn-expandir" role="button" tabindex="0" '
        f'title="{cliente}" data-chave-grupo="{chave}">{seta} {cliente}</span>'
    )


def _formatar_datas(pandas_df: pd.DataFrame) -> pd.DataFrame:
    for coluna in _DATAS_SOLICITACOES:
        if coluna in pandas_df.columns:
            convertida = pd.to_datetime(pandas_df[coluna].astype("string"), format="%Y%m%d", errors="coerce")
            pandas_df[coluna] = convertida.dt.strftime("%d/%m/%Y").fillna("")
    return pandas_df


def _linhas_dos_produtos(tabela: pl.DataFrame, chave: str, pode_gerenciar: bool, mostra_revenda: bool) -> pd.DataFrame:
    partes = partes_chave_grupo(chave)
    itens = tabela
    for coluna, valor in partes.items():
        itens = itens.filter(pl.col(coluna).cast(pl.Utf8) == valor)
    if itens.height == 0:
        return pd.DataFrame()
    itens_pd = itens.pipe(para_pandas)
    detalhe = pd.DataFrame(index=range(len(itens_pd)))
    for coluna in _ORDEM_COLUNAS_SOLICITACOES:
        detalhe[coluna] = ""
    detalhe["Produto"] = ["\u21b3 " + str(v) for v in itens_pd["PRODUTO"]]
    detalhe["Quantidade"] = list(itens_pd["QTD"])
    if "PRECO" in itens_pd.columns:
        detalhe["Valor"] = [
            _valor_em_reais(q * (0 if pd.isna(p) else p)) for q, p in zip(itens_pd["QTD"], itens_pd["PRECO"])
        ]
    if "USUARIO" in itens_pd.columns:
        detalhe["Usuário"] = list(itens_pd["USUARIO"])
    if pode_gerenciar:
        detalhe["Retirar"] = [
            HTML(
                _link_botao(
                    "\u274c",
                    "comod-btn-retirar",
                    {
                        "revenda": r,
                        "cliente": c,
                        "produto": pr,
                        "data": d,
                        "tipo": t,
                        "prazo": pz,
                    },
                    titulo="Retirar este produto da solicitação",
                )
            )
            for r, c, pr, d, t, pz in zip(
                itens_pd["REVENDA"],
                itens_pd["CLIENTE"],
                itens_pd["PRODUTO"],
                itens_pd["DATA"],
                itens_pd["TIPO"],
                itens_pd["PRAZO"],
            )
        ]
    if not mostra_revenda:
        detalhe = detalhe.drop(columns=["Revenda"])
    return detalhe


def _inserir_detalhes(
    pandas_df: pd.DataFrame, detalhes: list[tuple[int, pd.DataFrame]]
) -> tuple[pd.DataFrame, dict[int, list[int]]]:
    pedacos: list[pd.DataFrame] = []
    blocos: dict[int, list[int]] = {}
    inicio = 0
    deslocamento = 0
    for posicao_grupo, detalhe in sorted(detalhes, key=lambda item: item[0]):
        corte = posicao_grupo + 1
        pedacos.append(pandas_df.iloc[inicio:corte])
        pedacos.append(detalhe)
        primeira = corte + deslocamento
        blocos[posicao_grupo] = list(range(primeira, primeira + len(detalhe)))
        deslocamento += len(detalhe)
        inicio = corte
    if not pedacos:
        return pandas_df, {}
    pedacos.append(pandas_df.iloc[inicio:])
    return pd.concat(pedacos, ignore_index=True), blocos


def construir_solicitacoes_pendentes_df(
    tabela: pl.DataFrame,
    pode_gerenciar: bool,
    mostra_revenda: bool = True,
) -> tuple[pd.DataFrame, list[str]]:
    if tabela.height == 0:
        return pd.DataFrame(), []

    grupos = _agrupar_solicitacoes(tabela)
    pandas_df = grupos.pipe(para_pandas)
    chaves = [chave_grupo(linha) for linha in grupos.iter_rows(named=True)]
    crus = {
        coluna: pandas_df[coluna].tolist()
        for coluna in ("REVENDA", "CLIENTE", "DATA", "PRAZO", "TIPO")
        if coluna in pandas_df.columns
    }
    if pode_gerenciar:
        pandas_df["Enviar"] = [
            HTML(
                _link_botao(
                    "\U0001f4e4",
                    "comod-btn-enviar",
                    {
                        "revenda": r,
                        "cliente": c,
                        "data": d,
                        "prazo": p,
                        "tipo": t,
                    },
                    titulo="Enviar esta solicita\u00e7\u00e3o ao ERP",
                )
            )
            for r, c, d, p, t in zip(
                crus["REVENDA"],
                crus["CLIENTE"],
                crus["DATA"],
                crus["PRAZO"],
                crus["TIPO"],
            )
        ]
        pandas_df["Cancelar"] = [
            HTML(
                _link_botao(
                    "\U0001f5d1",
                    "comod-btn-cancelar-solicitacao",
                    {
                        "revenda": r,
                        "cliente": c,
                        "data": d,
                        "prazo": pz,
                        "tipo": t,
                    },
                    titulo="Cancelar a solicita\u00e7\u00e3o toda",
                )
            )
            for r, c, d, pz, t in zip(
                crus["REVENDA"],
                crus["CLIENTE"],
                crus["DATA"],
                crus["PRAZO"],
                crus["TIPO"],
            )
        ]
    pandas_df["Retirar"] = ""
    pandas_df = pandas_df.rename(columns=_RENOMEIA_SOLICITACOES)
    if "_VALOR" in pandas_df.columns:
        pandas_df["Valor"] = [_valor_em_reais(v) for v in pandas_df["_VALOR"]]
    pandas_df["Cliente"] = [str(cliente).strip() for cliente in crus["CLIENTE"]]
    pandas_df = _formatar_datas(pandas_df)
    colunas = [c for c in _ORDEM_COLUNAS_SOLICITACOES if c in pandas_df.columns]
    if not mostra_revenda:
        colunas = [c for c in colunas if c != "Revenda"]
    return pandas_df[colunas], chaves


def expandir_solicitacoes_df(
    fechado: pd.DataFrame,
    chaves: list[str],
    tabela: pl.DataFrame,
    pode_gerenciar: bool,
    grupos_abertos: Iterable[str] | None = None,
    mostra_revenda: bool = True,
) -> pd.DataFrame:
    if fechado.empty:
        return fechado
    pandas_df = fechado.copy()
    abertos = {str(c) for c in (grupos_abertos or ())}
    pandas_df["Cliente"] = [
        HTML(_celula_grupo_solicitacao(chave, str(cliente), chave in abertos))
        for chave, cliente in zip(chaves, fechado["Cliente"])
    ]

    detalhes = []
    for chave in abertos:
        if chave not in chaves:
            continue
        produtos = _linhas_dos_produtos(tabela, chave, pode_gerenciar, mostra_revenda)
        if produtos.empty:
            continue
        detalhes.append((chaves.index(chave), produtos[[c for c in pandas_df.columns if c in produtos.columns]]))
    pandas_df, _blocos = _inserir_detalhes(pandas_df, detalhes)
    return pandas_df


CHAVES_GRUPO_PRE_PEDIDO = ["PRE_PED", "CLIENTE"]

_RENOMEIA_PRE_PEDIDOS = {
    "REVENDA": "Revenda",
    "PRE_PED": "Pré-pedido",
    "CLIENTE": "Cliente",
    "PRAZO": "Prazo",
    "TIPO": "Tipo",
    "USUARIO": "Usuário",
    "PRODUTO": "Produto",
    "QTD": "Quantidade",
    "DATA": "Emissão",
    "VENC": "Vencimento",
}
_ORDEM_COLUNAS_PRE_PEDIDOS = [
    "Revenda",
    "Pré-pedido",
    "Cliente",
    "Prazo",
    "Tipo",
    "Usuário",
    "Produto",
    "Quantidade",
    "Valor",
    "Emissão",
    "Vencimento",
    "Cancelar",
]

_ICONE_CANCELAR_PRE_PEDIDO = _icone_pastilha("trash-can", COMODATO_ICONE_CANCELAR)


def construir_pre_pedidos_df(
    tabela: pl.DataFrame,
    pode_cancelar: bool,
    mostra_revenda: bool = True,
) -> pd.DataFrame:
    if tabela.height == 0:
        return pd.DataFrame()

    grupos = _agrupar_solicitacoes(tabela, CHAVES_GRUPO_PRE_PEDIDO)
    pandas_df = grupos.pipe(para_pandas)
    crus = {
        coluna: pandas_df[coluna].tolist()
        for coluna in ("REVENDA", "CLIENTE", "PRE_PED", "DATA", "PRAZO", "TIPO")
        if coluna in pandas_df.columns
    }
    if pode_cancelar:
        pandas_df["Cancelar"] = [
            HTML(
                _link_botao(
                    _ICONE_CANCELAR_PRE_PEDIDO,
                    "comod-btn-cancelar-pre-pedido",
                    {
                        "revenda": r,
                        "cliente": c,
                        "pre-ped": n,
                        "data": d,
                        "prazo": pz,
                        "tipo": t,
                    },
                    titulo="Cancelar este pré-pedido no ERP",
                )
            )
            for r, c, n, d, pz, t in zip(
                crus["REVENDA"],
                crus["CLIENTE"],
                crus["PRE_PED"],
                crus["DATA"],
                crus["PRAZO"],
                crus["TIPO"],
            )
        ]
    pandas_df = pandas_df.rename(columns=_RENOMEIA_PRE_PEDIDOS)
    if "_VALOR" in pandas_df.columns:
        pandas_df["Valor"] = [_valor_em_reais(v) for v in pandas_df["_VALOR"]]
    pandas_df["Cliente"] = [str(cliente).strip() for cliente in crus["CLIENTE"]]
    pandas_df = _formatar_datas(pandas_df)
    colunas = [c for c in _ORDEM_COLUNAS_PRE_PEDIDOS if c in pandas_df.columns]
    if not mostra_revenda:
        colunas = [c for c in colunas if c != "Revenda"]
    return pandas_df[colunas]


_RENOMEIA_DETALHES_CLIENTE = {"CEV": "Cev", "DT": "Emissão", "VENC": "Vencimento"}
_DATAS_DETALHES_CLIENTE = ["Emissão", "Vencimento"]


def construir_detalhes_cliente_df(tabela: pl.DataFrame) -> pd.DataFrame:
    pandas_df = tabela.pipe(para_pandas).rename(columns=_RENOMEIA_DETALHES_CLIENTE)
    for coluna in _DATAS_DETALHES_CLIENTE:
        if coluna in pandas_df.columns:
            convertida = pd.to_datetime(pandas_df[coluna].astype("string"), format="%Y%m%d", errors="coerce")
            pandas_df[coluna] = convertida.dt.strftime("%d/%m/%Y").fillna("")
    return pandas_df


_ICONE_ACAO_ATENCAO = "\u26a0\ufe0f"


def _botao_acao(
    chave: str,
    emoji: str,
    prazo_esgotado: bool = False,
    envio_liberado: bool = False,
    tem_contrato: bool = False,
) -> str:
    if emoji == "\u2705":
        return '<span class="comod-acao-ok" title="Concluído">\u2705</span>'
    apos_prazo = prazo_esgotado and dc.envio_apos_prazo_liberado(tem_contrato)
    if prazo_esgotado and not apos_prazo and not envio_liberado:
        return f'<span class="comod-acao-esgotado" title="Prazo de envio esgotado">{emoji}</span>'
    if apos_prazo:
        return _link_botao(
            _ICONE_ACAO_ATENCAO,
            "comod-btn-acao",
            {"chave-cev": chave},
            "Prazo esgotado -- envie o que falta (a revenda segue bloqueada)",
        )
    titulo = (
        "Prazo de envio esgotado -- ainda dá para enviar o que falta"
        if prazo_esgotado
        else "Enviar documentos do comodato"
    )
    return _link_botao(emoji, "comod-btn-acao", {"chave-cev": chave}, titulo)


def _link_anexo(caminho, classe: str, icone: str) -> str:
    if pd.isna(caminho):
        return ""
    url = ic.url_anexo(caminho)
    if not url:
        return ""
    return (
        f'<a href="{url}" target="_blank" rel="noopener" class="comod-btn-cel {classe}" title="Ver anexo">{icone}</a>'
    )


def _celula_anexo(url, classe: str, icone: str) -> HTML | str:
    marcacao = _link_anexo(url, classe, icone)
    return HTML(marcacao) if marcacao else ""


def _so_o_numero_do_cev(chave: str) -> str:
    return chave.rsplit(" - ", 1)[-1].strip() or chave


def _celula_cev(chave: str, aberto: bool, mostrar_revenda: bool = False) -> str:
    rotulo = chave if mostrar_revenda else _so_o_numero_do_cev(chave)
    return (
        '<span class="comod-cev-alvo" tabindex="0" '
        f'title="{escape(chave, quote=True)}" data-tooltip-cev="{escape(chave, quote=True)}">'
        f"{escape(rotulo)}</span>"
    )


_COLUNAS_ITENS_CEV = (
    ("Comp", "CODCOMP"),
    ("Produto", "Produto"),
    ("Qtd", "Qtd"),
    ("Emissão", "Data Emissão"),
    ("Venc", "Data Vencimento"),
    ("Prazo", "Prazo do Input"),
)

_COLUNAS_ITENS_HOVER = ("Comp", "Produto", "Qtd")


def itens_do_cev(tabela: pl.DataFrame, chave: str) -> pl.DataFrame:
    if tabela.height == 0 or not chave:
        return tabela.clear()
    return tabela.filter(pl.col("CEV").cast(pl.Utf8) == str(chave))


def _data_curta(valor) -> str:
    if valor is None:
        return ""
    if hasattr(valor, "strftime"):
        return valor.strftime("%d/%m/%Y")
    texto = str(valor).removesuffix(".0").strip()
    if len(texto) == 8 and texto.isdigit():
        return f"{texto[6:]}/{texto[4:6]}/{texto[:4]}"
    if len(texto) == 10 and texto[4] == "-" and texto[7] == "-":
        return f"{texto[8:]}/{texto[5:7]}/{texto[:4]}"
    return texto


def tabela_itens_html(
    itens: pl.DataFrame,
    com_foto_generica: bool = True,
    fotos_salvas: dict[str, list[dict]] | None = None,
) -> str:
    if itens.height == 0:
        return '<p class="comod-itens-vazio">Sem itens neste CEV.</p>'
    fotos_salvas = fotos_salvas or {}
    colunas = [
        (rotulo, coluna)
        for rotulo, coluna in _COLUNAS_ITENS_CEV
        if coluna in itens.columns and (not com_foto_generica or rotulo in _COLUNAS_ITENS_HOVER)
    ]
    cabecalhos = [rotulo for rotulo, _coluna in colunas]
    linhas: list[str] = []
    for item in itens.iter_rows(named=True):
        celulas: list[str] = []
        if com_foto_generica:
            imagem = dc.imagem_do_produto(item.get("Produto"))
            celulas.append(
                f'<td class="comod-itens-foto"><img src="{imagem}" alt="" loading="eager" decoding="async"></td>'
                if imagem
                else '<td class="comod-itens-foto"></td>'
            )
        for rotulo, coluna in colunas:
            valor = item.get(coluna)
            if coluna in ("Data Emissão", "Data Vencimento"):
                texto = _data_curta(valor)
            elif valor is None:
                texto = ""
            else:
                texto = str(valor).removesuffix(".0")
            classe = ' class="comod-itens-num"' if rotulo in ("Qtd", "Comp") else ""
            celulas.append(f"<td{classe}>{escape(texto)}</td>")
        if fotos_salvas is not None and not com_foto_generica:
            celulas.append(f'<td class="comod-itens-camera">{_botao_foto_salva(item, fotos_salvas)}</td>')
        linhas.append(f"<tr>{''.join(celulas)}</tr>")

    cabecalho = ""
    if com_foto_generica:
        cabecalho += "<th></th>"
    cabecalho += "".join(f"<th>{escape(r)}</th>" for r in cabecalhos)
    if not com_foto_generica:
        cabecalho += "<th>Foto</th>"
    return (
        f'<table class="comod-itens-tabela"><thead><tr>{cabecalho}</tr></thead><tbody>{"".join(linhas)}</tbody></table>'
    )


def _botao_foto_salva(item: dict, fotos_salvas: dict[str, list[dict]]) -> str:
    codcomp = str(item.get("CODCOMP") or "").removesuffix(".0").strip()
    fotos = fotos_salvas.get(codcomp) or []
    if not fotos:
        return ""
    foto = fotos[0]
    url = mc.url_foto(str(foto.get("ANEXO") or ""))
    if not url:
        return ""
    serial = str(foto.get("SERIAL") or "").strip()
    titulo = f"Foto do equipamento {serial}" if serial else "Foto do equipamento"
    if len(fotos) > 1:
        titulo += f" -- {len(fotos)} fotos guardadas, mostrando a mais recente"
    return (
        f'<a class="comod-btn-camera" href="{url}" target="_blank" rel="noopener"'
        f' title="{escape(titulo)}">{_ICONE_CAMERA}</a>'
    )


def _celula_produto_grupo(texto, chave: str) -> str:
    conteudo = "" if texto is None else str(texto).strip()
    if not conteudo:
        return ""
    return f'<span class="comod-cev-alvo" data-tooltip-cev="{escape(chave, quote=True)}">{escape(conteudo)}</span>'


LIMITE_REENVIO_EMAIL = 1


def _celula_reenviar_email(
    chave: str,
    envios_feitos: int,
    prazo_esgotado: bool = False,
    acesso_supremo: bool = False,
    documentacao_completa: bool = False,
    reenvio_ilimitado: bool = False,
    tentativas: int = 0,
    ultimo_erro: str = "",
    envios_tela: int = 0,
    tem_email_de_assinatura: bool = True,
) -> HTML | str:
    if documentacao_completa:
        return ""
    if prazo_esgotado and not acesso_supremo:
        return ""
    if not tem_email_de_assinatura and envios_feitos <= 0 and tentativas <= 0:
        return ""
    restantes = LIMITE_REENVIO_EMAIL - envios_tela
    icone, classe = _ICONE_REENVIAR, "comod-btn-reenviar"
    if envios_feitos <= 0:
        if tentativas > 0:
            icone = _ICONE_REENVIAR_FALHOU
            motivo = (ultimo_erro or "").strip() or "envio anterior falhou"
            titulo = f"Email nao enviado ({motivo}) -- clique para tentar de novo"
        else:
            icone = _ICONE_PRIMEIRO_ENVIO
            titulo = "Enviar email pela 1a vez (nenhum envio ate agora)"
    elif reenvio_ilimitado:
        titulo = f"Reenviar email (sem limite; {envios_feitos} envio(s) ate agora)"
    elif restantes > 0:
        titulo = f"Reenviar email ({restantes} reenvio disponivel)"
    elif acesso_supremo:
        titulo = "Limite de envio atingido -- acesso supremo ainda permite enviar"
    else:
        icone, classe = _ICONE_REENVIAR_TRAVADO, "comod-btn-reenviar-travado"
        titulo = "Limite de envio atingido -- contate o suporte"
    return HTML(
        f'<span class="comod-btn-cel {classe}" role="button" tabindex="0" '
        f'title="{titulo}" data-chave-cev="{chave}" data-envios="{envios_feitos}" '
        f'data-envios-tela="{envios_tela}">{icone}</span>'
    )


_CORES_PRAZO = {
    dc.FAIXA_PRAZO_FOLGA: (COMODATO_PRAZO_FOLGA_FUNDO, COMODATO_PRAZO_FOLGA_TEXTO),
    dc.FAIXA_PRAZO_ATENCAO: (COMODATO_PRAZO_ATENCAO_FUNDO, COMODATO_PRAZO_ATENCAO_TEXTO),
    dc.FAIXA_PRAZO_CRITICO: (COMODATO_PRAZO_CRITICO_FUNDO, COMODATO_PRAZO_CRITICO_TEXTO),
}

_COLUNA_PRAZO_EXIBIDA = "Prazo"


def _estilos_comodatos(
    pandas_df: pd.DataFrame,
    esgotados: list[bool] | None = None,
    faixas_prazo: list[str | None] | None = None,
) -> list[dict]:
    estilos = []
    for origem, cor in (("ERP", COMODATO_LINHA_CONTROL), ("Dash", COMODATO_LINHA_DASH)):
        linhas = [i for i, v in enumerate(pandas_df["Origem"]) if v == origem]
        if linhas:
            estilos.append({"rows": linhas, "style": {"background-color": cor}})
    if esgotados:
        linhas = [i for i, v in enumerate(esgotados) if v]
        if linhas:
            estilos.append({"rows": linhas, "style": {"background-color": COMODATO_LINHA_ESGOTADO}})
    if faixas_prazo:
        for faixa, (fundo, texto) in _CORES_PRAZO.items():
            linhas = [i for i, v in enumerate(faixas_prazo) if v == faixa]
            if linhas:
                estilos.append(
                    {
                        "rows": linhas,
                        "cols": [_COLUNA_PRAZO_EXIBIDA],
                        "style": {"background-color": fundo, "color": texto, "font-weight": "bold"},
                    }
                )
    return estilos


def _botao_recolha(
    chave: str,
    valor: str,
    recolha_liberada: bool = True,
    acesso_supremo: bool = False,
) -> str:
    ja_recolhido = valor == "PDF"
    if not ja_recolhido and not recolha_liberada and not acesso_supremo:
        return ""
    conteudo = _ICONE_DISTRATO_PDF if ja_recolhido else _ICONE_RECOLHER
    if ja_recolhido:
        titulo = "Baixar o distrato em PDF"
    elif recolha_liberada:
        titulo = "Pedir a recolha deste comodato"
    else:
        titulo = "Prazo vencido sem documentacao -- acesso supremo ainda permite recolher"
    return (
        '<span class="comod-btn-cel comod-btn-recolha" role="button" tabindex="0" '
        f'title="{titulo}" data-chave-cev="{chave}" data-valor="{valor}">{conteudo}</span>'
    )


_RENOMEIA_COMODATOS = {
    "CODCOMP": "Comp",
    "Data Emissão": "Emissão",
    "Data Vencimento": "Venc",
    "Intervalo Vencimento": "Intervalo\n(dias)",
    "Inadimplencia 60 dias +": "Inad. 60\ndias +",
    "Prazo do Input": "Prazo",
    "Razão Social": "Razão\nSocial",
    "Canhoto": "Can",
    "Reenviar": "Reenviar\nEmail",
}
_ORDEM_COLUNAS_COMODATOS = [
    "CEV",
    "Comp",
    "NF",
    "Cliente",
    "Razão\nSocial",
    "Emissão",
    "Venc",
    "Intervalo\n(dias)",
    "Produto",
    "Qtd",
    "Inad. 60\ndias +",
    "Prazo",
    "Usuario",
    "Origem",
    "Doc",
    "Cev",
    "Can",
    "Ação",
    "Reenviar\nEmail",
    "Recolha",
]

_AGREGACAO_COMODATOS = {
    "CODCOMP": "vazio",
    "NF": "unique",
    "Cliente": "unique",
    "Razão Social": "unique",
    "Data Emissão": "maior",
    "Data Vencimento": "maior",
    "Intervalo Vencimento": "unique",
    "Produto": "conta",
    "Qtd": "soma",
    "Inadimplencia 60 dias +": "unique",
    "Prazo do Input": "unique",
    "Usuario": "unique",
    "Origem": "unique",
}


def _agrupar_por_cev(tabela: pl.DataFrame) -> pl.DataFrame:
    if NO_NAVEGADOR:
        agrupado = _agrupar_em_pandas(tabela, ["CEV"], _AGREGACAO_COMODATOS, "Itens comodatados: ")
        if "Data Emissão" in agrupado.columns:
            agrupado = agrupado.sort("Data Emissão", descending=True, nulls_last=True)
        return agrupado
    agregacoes = []
    for coluna in tabela.columns:
        if coluna == "CEV":
            continue
        regra = _AGREGACAO_COMODATOS.get(coluna)
        if regra == "soma":
            agregacoes.append(pl.col(coluna).sum())
        elif regra == "maior":
            agregacoes.append(pl.col(coluna).max())
        elif regra == "conta":
            agregacoes.append((pl.lit("Itens comodatados: ") + pl.len().cast(pl.Utf8)).alias(coluna))
        elif regra in ("unique", "vazio"):
            texto = pl.col(coluna).cast(pl.Utf8).str.strip_chars()
            distintos = (
                texto.filter(texto.is_not_null() & (texto.str.len_chars() > 0))
                .unique(maintain_order=True)
                .str.join(", ")
            )
            if regra == "vazio":
                distintos = pl.when(pl.col(coluna).n_unique() <= 1).then(distintos).otherwise(pl.lit(""))
            agregacoes.append(distintos.alias(coluna))
        else:
            agregacoes.append(pl.col(coluna).first())
    agrupado = tabela.group_by("CEV", maintain_order=True).agg(agregacoes)
    if "Data Emissão" in agrupado.columns:
        agrupado = agrupado.sort("Data Emissão", descending=True, nulls_last=True)
    return agrupado


def _linhas_do_cev_aberto(itens_cev: pl.DataFrame) -> pd.DataFrame:
    itens = itens_cev.pipe(para_pandas)
    if itens.empty:
        return itens
    for coluna in ("Data Emissão", "Data Vencimento"):
        if coluna in itens.columns:
            itens[coluna] = pd.to_datetime(itens[coluna], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")
    detalhe = pd.DataFrame(index=range(len(itens)))
    for coluna in _ORDEM_COLUNAS_COMODATOS:
        detalhe[coluna] = ""
    detalhe["Produto"] = ["\u21b3 " + str(v) for v in itens.get("Produto", [""] * len(itens))]
    for destino, origem in (
        ("Comp", "CODCOMP"),
        ("Qtd", "Qtd"),
        ("Emissão", "Data Emissão"),
        ("Venc", "Data Vencimento"),
        ("Prazo", "Prazo do Input"),
    ):
        if origem in itens.columns:
            detalhe[destino] = [("" if pd.isna(v) else v) for v in itens[origem]]
    return detalhe


def _detalhes_por_cev(tabela: pl.DataFrame, cevs: list[str]) -> dict[str, pd.DataFrame]:
    partes = tabela.filter(pl.col("CEV").cast(pl.Utf8).is_in(cevs)).partition_by("CEV", as_dict=True)
    detalhes = {}
    for chave, itens in partes.items():
        cev = str(chave[0] if isinstance(chave, tuple) else chave)
        detalhes[cev] = _linhas_do_cev_aberto(itens)
    return detalhes


def construir_comodatos_df(
    tabela: pl.DataFrame,
    envios_por_cev: dict[tuple[str, str], dict] | None = None,
    pode_recolha: bool = False,
    pode_reenviar: bool = False,
    acesso_supremo: bool = False,
    reenvio_ilimitado: bool = False,
    envio_sem_bloqueio: bool = False,
) -> tuple[pd.DataFrame, list[dict]]:
    if tabela.height == 0:
        return pd.DataFrame(), []
    if envios_por_cev is None:
        envios_por_cev = {}
    pandas_df = _agrupar_por_cev(tabela).pipe(para_pandas)
    for coluna in ("Data Emissão", "Data Vencimento"):
        if coluna in pandas_df.columns:
            pandas_df[coluna] = pd.to_datetime(pandas_df[coluna], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")
    esgotado_por_cev = dc.mapa_prazo_esgotado(tabela)
    esgotados = [bool(esgotado_por_cev.get(str(cev), False)) for cev in pandas_df["CEV"]]
    completa_por_cev = dc.mapa_documentacao_completa(tabela)
    completas = [bool(completa_por_cev.get(str(cev), False)) for cev in pandas_df["CEV"]]
    faixas_prazo = [
        dc.faixa_prazo(texto, esgotado)
        for texto, esgotado in zip(pandas_df.get("Prazo do Input", [None] * len(pandas_df)), esgotados)
    ]
    contratos = pandas_df.get("anexo2", [None] * len(pandas_df))
    pandas_df["Ação"] = [
        HTML(_botao_acao(chave, emoji, esgotado, acesso_supremo or envio_sem_bloqueio, ic.tem_anexo(contrato)))
        for chave, emoji, esgotado, contrato in zip(pandas_df["CEV"], pandas_df["Acao"], esgotados, contratos)
    ]
    if pode_reenviar:
        cnpjs = pandas_df["cnpj"] if "cnpj" in pandas_df.columns else [""] * len(pandas_df)
        email_por_cev = dc.mapa_email_de_assinatura(tabela)
        vazio = {"envios": 0, "envios_tela": 0, "tentativas": 0, "ultimo_erro": ""}
        pandas_df["Reenviar"] = [
            _celula_reenviar_email(
                chave,
                (estado := envios_por_cev.get((str(cnpj or ""), _so_o_numero_do_cev(str(chave))), vazio))["envios"],
                esgotado,
                acesso_supremo,
                completa,
                reenvio_ilimitado,
                tentativas=estado["tentativas"],
                ultimo_erro=estado["ultimo_erro"],
                envios_tela=estado["envios_tela"],
                tem_email_de_assinatura=email_por_cev.get(str(chave), True),
            )
            for chave, cnpj, esgotado, completa in zip(pandas_df["CEV"], cnpjs, esgotados, completas)
        ]
    pandas_df["Doc"] = [_celula_anexo(url, "comod-anexo-doc", _ICONE_DOC_PDV) for url in pandas_df.get("anexo1", [])]
    pandas_df["Cev"] = [_celula_anexo(url, "comod-anexo-cev", _ICONE_CONTRATO) for url in pandas_df.get("anexo2", [])]
    pandas_df["Canhoto"] = [
        _celula_anexo(url, "comod-anexo-canhoto", _ICONE_CANHOTO) for url in pandas_df.get("anexo3", [])
    ]
    if pode_recolha and "Recolha" in pandas_df.columns:
        liberada_por_cev = dc.mapa_recolha_liberada(tabela)
        pandas_df["Recolha"] = [
            HTML(
                _botao_recolha(
                    chave,
                    valor,
                    liberada_por_cev.get(str(chave), True),
                    acesso_supremo,
                )
            )
            for chave, valor in zip(pandas_df["CEV"], pandas_df["Recolha"])
        ]
    elif "Recolha" in pandas_df.columns:
        pandas_df = pandas_df.drop(columns=["Recolha"])

    estilos = _estilos_comodatos(pandas_df, esgotados, faixas_prazo)

    pandas_df = pandas_df.rename(columns=_RENOMEIA_COMODATOS)
    pandas_df = pandas_df[[c for c in _ORDEM_COLUNAS_COMODATOS if c in pandas_df.columns]]
    return pandas_df, estilos


def expandir_comodatos_df(
    fechado: pd.DataFrame,
    estilos_fechado: list[dict],
    tabela: pl.DataFrame,
    cevs_abertos: Iterable[str] | None = None,
    mostrar_revenda: bool = False,
) -> tuple[pd.DataFrame, list[dict]]:
    if fechado.empty:
        return fechado, list(estilos_fechado)
    pandas_df = fechado.copy()
    estilos = list(estilos_fechado)

    abertos: set[str] = set()
    if "CEV" in pandas_df.columns:
        chaves = [str(v) for v in pandas_df["CEV"]]
        if "Produto" in pandas_df.columns:
            pandas_df["Produto"] = [
                HTML(marcacao) if (marcacao := _celula_produto_grupo(texto, chave)) else ""
                for texto, chave in zip(pandas_df["Produto"], chaves)
            ]
        pandas_df["CEV"] = [
            HTML(_celula_cev(chave, chave in abertos, mostrar_revenda)) if chave.strip() else "" for chave in chaves
        ]
    return pandas_df, estilos


_RENOMEIA_DOWNLOAD = {
    "CODCOMP": "Comp",
    "Data Emissão": "Emissão",
    "Data Vencimento": "Vencimento",
    "Intervalo Vencimento": "Intervalo (dias)",
    "Prazo do Input": "Prazo",
}

_ORDEM_COLUNAS_DOWNLOAD = [
    "CEV",
    "Comp",
    "NF",
    "Cliente",
    "Razão Social",
    "Fantasia",
    "Emissão",
    "Vencimento",
    "Intervalo (dias)",
    "Produto",
    "Qtd",
    "Inadimplencia 60 dias +",
    "Prazo",
    "Usuario",
    "Origem",
    "Status",
    "Documento PDV",
    "Contrato assinado",
    "Canhoto",
    "Ação",
    "Reenviar Email",
    "Recolha",
    *dc.COLUNAS_DETALHE_RECOLHA,
]


def _expr_do_mapa(mapa: dict[str, bool], padrao: bool) -> pl.Expr:
    return pl.col("CEV").cast(pl.Utf8).replace_strict(mapa, default=padrao, return_dtype=pl.Boolean)


def _expr_tem_anexo(coluna: str) -> pl.Expr:
    texto = pl.col(coluna).cast(pl.Utf8).fill_null("").str.strip_chars()
    return (texto != "") & ~texto.str.to_lowercase().is_in(list(ic.SEM_ANEXO))


def _expr_numero_cev() -> pl.Expr:
    numero = pl.col("CEV").cast(pl.Utf8).str.replace(r"^.* - ", "").str.strip_chars()
    return pl.when(numero.str.len_chars() > 0).then(numero).otherwise(pl.col("CEV").cast(pl.Utf8))


def _texto_acao(esgotado: pl.Expr, tem_contrato: pl.Expr, envio_liberado: bool) -> pl.Expr:
    apos_prazo = esgotado & tem_contrato & pl.lit(dc.envio_apos_prazo_liberado(True))
    return (
        pl.when(pl.col("Acao") == "\u2705")
        .then(pl.lit("Concluído"))
        .when(apos_prazo)
        .then(pl.lit("Pode enviar o que falta (prazo esgotado)"))
        .when(~esgotado)
        .then(pl.lit("Pode enviar documentos"))
        .when(pl.lit(envio_liberado))
        .then(pl.lit("Pode enviar (prazo esgotado)"))
        .otherwise(pl.lit("Sem envio (prazo esgotado)"))
    )


def _texto_reenviar(
    esgotado: pl.Expr,
    completa: pl.Expr,
    tem_email: pl.Expr,
    acesso_supremo: bool,
    reenvio_ilimitado: bool,
) -> pl.Expr:
    envios, tentativas = pl.col("_envios"), pl.col("_tentativas")
    restantes = LIMITE_REENVIO_EMAIL - pl.col("_envios_tela")
    return (
        pl.when(completa)
        .then(pl.lit("Não se aplica (documentação completa)"))
        .when(esgotado & ~pl.lit(acesso_supremo))
        .then(pl.lit("Não se aplica (prazo esgotado)"))
        .when(~tem_email & (envios <= 0) & (tentativas <= 0))
        .then(pl.lit("Não se aplica (contrato manual)"))
        .when((envios <= 0) & (tentativas > 0))
        .then(pl.lit("Pode tentar de novo (envio anterior falhou)"))
        .when(envios <= 0)
        .then(pl.lit("Pode enviar (1º envio)"))
        .when(pl.lit(reenvio_ilimitado))
        .then(pl.lit("Pode reenviar (sem limite)"))
        .when(restantes > 0)
        .then(pl.lit("Pode reenviar"))
        .when(pl.lit(acesso_supremo))
        .then(pl.lit("Limite atingido (acesso supremo ainda envia)"))
        .otherwise(pl.lit("Limite atingido"))
    )


def _texto_recolha(recolha_liberada: pl.Expr, acesso_supremo: bool) -> pl.Expr:
    return (
        pl.when(pl.col("Recolha") == "PDF")
        .then(pl.lit("Recolhido (distrato em PDF)"))
        .when(recolha_liberada)
        .then(pl.lit("Pode recolher"))
        .when(pl.lit(acesso_supremo))
        .then(pl.lit("Prazo vencido sem documentação (acesso supremo ainda recolhe)"))
        .otherwise(pl.lit("Indisponível"))
    )


def construir_comodatos_download_df(
    tabela: pl.DataFrame,
    envios_por_cev: dict[tuple[str, str], dict] | None = None,
    pode_recolha: bool = False,
    pode_reenviar: bool = False,
    acesso_supremo: bool = False,
    reenvio_ilimitado: bool = False,
    envio_sem_bloqueio: bool = False,
    mostrar_revenda: bool = False,
) -> pl.DataFrame:
    if tabela.height == 0:
        return pl.DataFrame()

    esgotado = _expr_do_mapa(dc.mapa_prazo_esgotado(tabela), padrao=False)
    completa = _expr_do_mapa(dc.mapa_documentacao_completa(tabela), padrao=False)
    tem_email = _expr_do_mapa(dc.mapa_email_de_assinatura(tabela), padrao=True)
    liberada = _expr_do_mapa(dc.mapa_recolha_liberada(tabela), padrao=True)

    base = tabela.with_columns(
        pl.when(_expr_tem_anexo("anexo1")).then(pl.lit("Sim")).otherwise(pl.lit("Não")).alias("Documento PDV"),
        pl.when(_expr_tem_anexo("anexo2")).then(pl.lit("Sim")).otherwise(pl.lit("Não")).alias("Contrato assinado"),
        pl.when(_expr_tem_anexo("anexo3")).then(pl.lit("Sim")).otherwise(pl.lit("Não")).alias("Canhoto"),
        _texto_acao(esgotado, _expr_tem_anexo("anexo2"), acesso_supremo or envio_sem_bloqueio).alias("Ação"),
    )

    if pode_reenviar:
        historico = pl.DataFrame(
            [
                {
                    "_cnpj": str(cnpj or ""),
                    "_num_cev": str(numero or ""),
                    "_envios": int(estado["envios"]),
                    "_envios_tela": int(estado["envios_tela"]),
                    "_tentativas": int(estado["tentativas"]),
                }
                for (cnpj, numero), estado in (envios_por_cev or {}).items()
            ],
            schema={
                "_cnpj": pl.Utf8,
                "_num_cev": pl.Utf8,
                "_envios": pl.Int64,
                "_envios_tela": pl.Int64,
                "_tentativas": pl.Int64,
            },
        )
        base = (
            base.with_columns(
                pl.col("cnpj").cast(pl.Utf8).fill_null("").alias("_cnpj"),
                _expr_numero_cev().alias("_num_cev"),
            )
            .join(historico, on=["_cnpj", "_num_cev"], how="left")
            .with_columns(pl.col("_envios", "_envios_tela", "_tentativas").fill_null(0))
        )
        base = base.with_columns(
            _texto_reenviar(esgotado, completa, tem_email, acesso_supremo, reenvio_ilimitado).alias("Reenviar Email")
        )
    if pode_recolha and "Recolha" in base.columns:
        base = base.with_columns(_texto_recolha(liberada, acesso_supremo).alias("Recolha"))
    elif "Recolha" in base.columns:
        base = base.drop("Recolha")

    if not mostrar_revenda:
        base = base.with_columns(_expr_numero_cev().alias("CEV"))
    base = base.rename({c: novo for c, novo in _RENOMEIA_DOWNLOAD.items() if c in base.columns})
    return base.select([c for c in _ORDEM_COLUNAS_DOWNLOAD if c in base.columns])
