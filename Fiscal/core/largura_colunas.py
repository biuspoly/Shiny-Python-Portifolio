from __future__ import annotations

import html
import math
import re

import polars as pl
from htmltools import HTML
from loguru import logger
from shiny import render

MAIUSCULA = 1.12
MINUSCULA = 0.92
ALGARISMO = 1.0
ESPACO = 0.51
OUTRA = 0.6
ZERO_EM_EM = 0.539
TETO = 30
FOLGA = 3
FOLGA_DO_PONTO = 2.5
ICONE = 2.5
ETIQUETA = 2
BOTAO = 5
SEM_LARGURA = {"Marcar"}

_MOLDE_DA_DICA = re.compile(r"<template.*?</template>", re.S)
_BOTAO = re.compile(r"<button\b[^>]*>.*?</button>", re.S)
_ETIQUETA = re.compile(r"<[^>]+>")
_HTML_DE_BOTOES = re.compile(r"<(?!/?(?:bslib-tooltip|template|span|br|svg|path|g|title)\b)[a-zA-Z]")
_MAIUSCULAS = r"[A-ZÀ-ÖØ-Þ]"
_MINUSCULAS = r"[a-zß-öø-ÿ]"
_ALGARISMOS = r"[0-9]"


def medida(letras: float) -> str:
    return f"{math.ceil(letras) * ZERO_EM_EM:.2f}em"


def sem_menu_escondido(marcacao: str) -> str:
    inicio = marcacao.find("dropdown-menu")
    while inicio >= 0:
        abertura = marcacao.rfind("<", 0, inicio)
        nome_da_etiqueta = re.match(r"<(\w+)", marcacao[abertura:]).group(1)
        profundidade = 0
        fim = len(marcacao)
        for etiqueta in re.finditer(rf"<(/?){nome_da_etiqueta}\b[^>]*>", marcacao[abertura:]):
            profundidade += -1 if etiqueta.group(1) else 1
            if profundidade == 0:
                fim = abertura + etiqueta.end()
                break
        marcacao = marcacao[:abertura] + marcacao[fim:]
        inicio = marcacao.find("dropdown-menu")
    return marcacao


def texto_da_celula(valor) -> str:
    if valor is None:
        return ""
    texto = str(valor)
    if isinstance(valor, HTML):
        texto = html.unescape(_ETIQUETA.sub("", sem_menu_escondido(_MOLDE_DA_DICA.sub("", texto))))
    return texto


def largura_do_texto(texto: str) -> float:
    maiusculas = len(re.findall(_MAIUSCULAS, texto))
    minusculas = len(re.findall(_MINUSCULAS, texto))
    algarismos = len(re.findall(_ALGARISMOS, texto))
    espacos = texto.count(" ")
    outras = len(texto) - maiusculas - minusculas - algarismos - espacos
    return maiusculas * MAIUSCULA + minusculas * MINUSCULA + algarismos * ALGARISMO + espacos * ESPACO + outras * OUTRA


def largura_da_coluna_de_texto(coluna: str) -> pl.Expr:
    texto = pl.col(coluna).cast(pl.Utf8, strict=False).fill_null("")
    maiusculas = texto.str.count_matches(_MAIUSCULAS)
    minusculas = texto.str.count_matches(_MINUSCULAS)
    algarismos = texto.str.count_matches(_ALGARISMOS)
    espacos = texto.str.count_matches(" ", literal=True)
    outras = texto.str.len_chars() - maiusculas - minusculas - algarismos - espacos
    return maiusculas * MAIUSCULA + minusculas * MINUSCULA + algarismos * ALGARISMO + espacos * ESPACO + outras * OUTRA


def de_botoes(valores: list) -> bool:
    for valor in valores:
        if valor is not None and _HTML_DE_BOTOES.search(sem_menu_escondido(str(valor))):
            return True
    return False


def largura_alem_do_texto(valor) -> float:
    if not isinstance(valor, HTML):
        return 0.0
    marcacao = sem_menu_escondido(_MOLDE_DA_DICA.sub("", str(valor)))
    botoes = len(_BOTAO.findall(marcacao))
    icones_fora_dos_botoes = _BOTAO.sub("", marcacao).count("<svg")
    return botoes * BOTAO + icones_fora_dos_botoes * ICONE + marcacao.count('class="fis-etiqueta"') * ETIQUETA


def largura_da_celula(valor) -> float:
    return largura_do_texto(texto_da_celula(valor)) + largura_alem_do_texto(valor)


def celula_com_dica(texto: str) -> HTML:
    escrito = html.escape(texto, quote=False)
    return HTML(
        f'<bslib-tooltip placement="top"><template style="display:none;">{escrito}</template>'
        f'<span class="fis-com-dica">{escrito}</span></bslib-tooltip>'
    )


def com_o_texto_na_dica(valor, texto: str) -> HTML:
    marcacao = str(valor)
    escrito = html.escape(texto, quote=False)
    inicio_do_molde = marcacao.find("<template")
    fim_da_abertura = marcacao.find(">", inicio_do_molde) + 1
    if inicio_do_molde < 0 or marcacao[fim_da_abertura:].startswith(escrito):
        return HTML(marcacao)
    return HTML(f"{marcacao[:fim_da_abertura]}{escrito}<br/>{marcacao[fim_da_abertura:]}")


def com_dica_no_que_nao_cabe(tabela: pl.DataFrame, coluna: str, teto: float) -> pl.DataFrame:
    valores = []
    for valor in tabela.get_column(coluna).to_list():
        texto = texto_da_celula(valor)
        tem_dica = isinstance(valor, HTML) and "<template" in str(valor)
        if largura_alem_do_texto(valor) or largura_do_texto(texto) <= teto:
            valores.append(
                valor if isinstance(valor, HTML) else HTML(f"<span>{html.escape(texto, quote=False)}</span>")
            )
        elif tem_dica:
            valores.append(com_o_texto_na_dica(valor, texto))
        else:
            valores.append(celula_com_dica(texto))
    return tabela.with_columns(pl.Series(coluna, valores, dtype=pl.Object))


def maior_largura(tabela: pl.DataFrame, coluna: str) -> float:
    if tabela.get_column(coluna).dtype == pl.Object:
        return max((largura_da_celula(valor) for valor in tabela.get_column(coluna).to_list()), default=0.0)
    return tabela.select(largura_da_coluna_de_texto(coluna).max()).item() or 0.0


def colunas_com_ponto(estilos: list[dict]) -> set[int]:
    posicoes = set()
    for estilo in estilos:
        if "fis-sit" in str(estilo.get("class") or ""):
            posicoes.update(estilo.get("cols") or [])
    return posicoes


def grade(tabela, styles=None, teto: float = TETO, **opcoes) -> render.DataGrid:
    if not isinstance(tabela, pl.DataFrame) or callable(styles):
        return render.DataGrid(tabela, styles=styles, **opcoes)
    tabela_fixa, estilos = fixar(tabela, styles, teto)
    return render.DataGrid(tabela_fixa, styles=estilos, **opcoes)


def fixar(
    tabela: pl.DataFrame, estilos: list[dict] | None = None, teto: float = TETO
) -> tuple[pl.DataFrame, list[dict]]:
    estilos_com_largura = list(estilos or [])
    com_ponto = colunas_com_ponto(estilos_com_largura)
    for posicao, coluna in enumerate(tabela.columns):
        if coluna in SEM_LARGURA:
            continue
        try:
            coluna_de_botoes = tabela.get_column(coluna).dtype == pl.Object and de_botoes(
                tabela.get_column(coluna).to_list()
            )
            maior = maior_largura(tabela, coluna)
            if maior > teto and not coluna_de_botoes:
                tabela = com_dica_no_que_nao_cabe(tabela, coluna, teto)
        except Exception as exc:
            logger.warning(f'Largura da coluna "{coluna}" nao calculada; fica a do conteudo -- {exc}')
            continue
        folga = FOLGA + (FOLGA_DO_PONTO if posicao in com_ponto else 0)
        if coluna_de_botoes:
            largura = medida(maior + folga)
            estilo = {"width": largura, "min-width": largura}
        else:
            largura = medida(min(maior, teto) + folga)
            estilo = {"width": largura, "min-width": largura, "max-width": largura}
        estilos_com_largura.append({"location": "body", "cols": [posicao], "style": estilo})
    return tabela, estilos_com_largura
