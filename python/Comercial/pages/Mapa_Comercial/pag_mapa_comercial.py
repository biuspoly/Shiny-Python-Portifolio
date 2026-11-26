from __future__ import annotations

import asyncio
import html
import io
import json
from datetime import date

import folium
import pandas as pd
import polars as pl
import shapely
from faicons import icon_svg
from loguru import logger
from pyecharts import options as opts
from pyecharts.charts import Line
from pyecharts.commons.utils import JsCode
from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from shiny import module, reactive, render, req, ui

from core.compat import para_pandas
from core.config import REVENDA_PADRAO
from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.tabela_paginada import TabelaPaginada

from .Dados import dados_mapa_comercial as d

ALTURA_MAPA = "calc(100vh - 170px)"
ALTURA_TABELA = "calc(100vh - 210px)"
ALTURA_TABELA_SAIBA = "calc(100vh - 440px)"

_COLUNAS_SAIBA_MAIS = [
    "Município",
    "Distância (km)",
    "População",
    "Clientes",
    "Potencial",
    "Cob Potencial Min (75%)",
    "Potencial Crescim.",
    "HL",
    "UMB",
    "Clientes Cobertos",
    "Falta Próx. Nível",
    "% Ativos",
    "% Potencial",
    "R$/Hab",
]
_LARGURA_SAIBA_MAIS = {
    "Município": 150,
    "Distância (km)": 110,
    "População": 110,
    "Clientes": 100,
    "Potencial": 110,
    "Cob Potencial Min (75%)": 170,
    "Potencial Crescim.": 140,
    "HL": 90,
    "UMB": 90,
    "Clientes Cobertos": 140,
    "Falta Próx. Nível": 140,
    "% Ativos": 100,
    "% Potencial": 110,
    "R$/Hab": 110,
}
_COLUNAS_RUPTURA_6M = [
    "Código",
    "Nome",
    "Fantasia",
    "Município",
    "Endereço",
    "Classificação",
    "Canal",
    "Ven",
    "Títulos Abertos",
    "Comodato Aberto",
    "Subrevenda",
    "Última Compra",
]
_COLUNAS_CLIENTES_INATIVOS = [c for c in _COLUNAS_RUPTURA_6M if c != "Ven"]
_LARGURA_CLIENTES = {
    "Código": 100,
    "Nome": 220,
    "Fantasia": 160,
    "Município": 140,
    "Endereço": 220,
    "Classificação": 130,
    "Canal": 110,
    "Ven": 90,
    "Títulos Abertos": 130,
    "Comodato Aberto": 140,
    "Subrevenda": 130,
    "Última Compra": 120,
}


def pag_mapa_comercial_ui():
    return mapa_comercial_ui("mapa_comercial")


def pag_mapa_comercial_server(gatilho_mapa, versao_cache=None):
    mapa_comercial_server("mapa_comercial", gatilho_mapa=gatilho_mapa, versao_cache=versao_cache)


def _filtro_selectize(id_: str, rotulo: str, choices: list[str] = ()):
    return ui.div(
        ui.input_selectize(
            id_,
            rotulo,
            choices=list(choices),
            multiple=True,
            options={
                "placeholder": "Todos",
                "plugins": ["remove_button"],
                "dropdownParent": "body",
                "dropdownClass": "selectize-dropdown dv-selectize-dropdown",
                "hideSelected": False,
            },
        ),
        class_="filtro-dv",
    )


_CAMPOS_FILTRO_PRODUTO = [
    ("mc_canal_filtro", "Canal", "canal", False),
    ("mc_classif_cliente_filtro", "Classificação Cliente", "porte", True),
    ("mc_categoria_filtro", "Categoria Prod", "categoria", True),
    ("mc_embalagem_filtro", "Tipo Embalagem", "embalagem", False),
    ("mc_marca_filtro", "Marca", "marca", False),
    ("mc_vendedor_filtro", "Vendedor", "vendedor", True),
]


@module.ui
def mapa_comercial_ui():
    condicao_potencial = "input.mc_aba_visualizacao === 'Potencial' || input.mc_aba_visualizacao === 'Saiba Mais'"
    return ui.div(
        ui.div(
            ui.card(
                ui.card_header(
                    ui.div(
                        ui.span("Mapa Comercial - Potencial e Cobertura"),
                        ui.panel_conditional(
                            "input.mc_aba_visualizacao === 'Ruptura 6M+'",
                            ui.download_button(
                                "baixar_ruptura_6m",
                                None,
                                icon=icon_svg("file-excel", a11y="deco"),
                                class_="btn-sm btn-success ms-auto",
                                title="Baixar Excel",
                            ),
                        ),
                        ui.panel_conditional(
                            "input.mc_aba_visualizacao === 'Clientes Inativos'",
                            ui.download_button(
                                "baixar_clientes_inativos",
                                None,
                                icon=icon_svg("file-excel", a11y="deco"),
                                class_="btn-sm btn-success ms-auto",
                                title="Baixar Excel",
                            ),
                        ),
                        ui.panel_conditional(
                            condicao_potencial,
                            ui.output_ui("switch_distancia"),
                        ),
                        class_="d-flex align-items-center w-100",
                    )
                ),
                ui.panel_conditional(
                    "input.mc_aba_visualizacao === 'Potencial'",
                    ui.div(
                        ui.output_ui("mapa_leaflet"),
                        class_="mc-mapa-wrap",
                    ),
                ),
                ui.panel_conditional(
                    "input.mc_aba_visualizacao === 'Saiba Mais'",
                    ui.output_ui("cards_saiba_mais"),
                    ui.div(ui.output_data_frame("tabela_saiba_mais"), class_="mc-tabela mc-tabela-saiba tabela-resize"),
                    ui.output_ui("controles_saiba"),
                    ui.output_ui("css_largura_saiba"),
                ),
                ui.panel_conditional(
                    "input.mc_aba_visualizacao === 'Ruptura 6M+'",
                    ui.div(ui.output_data_frame("tabela_ruptura_6m"), class_="mc-tabela tabela-resize"),
                    ui.output_ui("controles_ruptura"),
                    ui.output_ui("css_largura_ruptura"),
                ),
                ui.panel_conditional(
                    "input.mc_aba_visualizacao === 'Clientes Inativos'",
                    ui.div(ui.output_data_frame("tabela_clientes_inativos"), class_="mc-tabela tabela-resize"),
                    ui.output_ui("controles_inativos"),
                    ui.output_ui("css_largura_inativos"),
                ),
                class_="mc-card-principal",
            ),
            ui.card(
                ui.card_header("Filtros"),
                ui.panel_conditional(
                    condicao_potencial,
                    ui.div(
                        ui.input_selectize(
                            "mes_mc",
                            "Mês",
                            choices={},
                            options={
                                "dropdownParent": "body",
                                "dropdownClass": "selectize-dropdown dv-selectize-dropdown",
                            },
                        ),
                        class_="filtro-dv",
                    ),
                ),
                ui.input_radio_buttons(
                    "mc_aba_visualizacao",
                    None,
                    choices=["Potencial", "Saiba Mais", "Ruptura 6M+", "Clientes Inativos"],
                    selected="Potencial",
                ),
                ui.hr(),
                ui.panel_conditional(
                    condicao_potencial,
                    ui.output_ui("filtros_produto_lateral"),
                ),
                ui.panel_conditional(
                    "input.mc_aba_visualizacao === 'Ruptura 6M+'",
                    ui.output_ui("cards_ruptura_6m"),
                ),
                ui.panel_conditional(
                    "input.mc_aba_visualizacao === 'Clientes Inativos'",
                    ui.output_ui("cards_clientes_inativos"),
                ),
                class_="mc-card-filtros",
            ),
            class_="mc-layout",
        ),
        class_="mc-modulo",
    )


def _numero(valor: object, casas: int = 0) -> str:
    if valor is None:
        return "-"
    numero = float(valor)
    texto = f"{numero:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _valores_input(valor) -> tuple[str, ...]:
    if valor in (None, ""):
        return ()
    if isinstance(valor, str):
        return (valor,)
    return tuple(valor)


def _card_mapa(titulo: str, valor: str, icone: str, cor: str = "#006400"):
    return ui.div(
        ui.span(icon_svg(icone), class_="mc-card-icone", style=f"color:{cor};"),
        ui.div(ui.strong(titulo), ui.br(), valor, style=f"color:{cor if cor != '#006400' else '#555'};"),
        class_="mc-card-mapa",
    )


def _card_mapa_html(titulo: str, valor: str, icone: str, cor: str = "#006400") -> str:
    cor_texto = cor if cor != "#006400" else "#555"
    return (
        '<div style="'
        "display:flex;"
        "align-items:center;"
        "gap:clamp(0.35rem,0.7vw,0.75rem);"
        "min-width:clamp(7rem,11vw,11rem);"
        "padding:clamp(0.35rem,0.7vw,0.75rem);"
        "border-radius:0.35rem;"
        "background:rgba(255,255,255,0.84);"
        "box-shadow:0 0 1rem rgba(0,0,0,0.2);"
        "font-size:clamp(0.85rem,1vw,1.1rem);"
        '">'
        f'<span style="'
        f"color:{cor};"
        "display:flex;"
        "align-items:center;"
        '">'
        f"{icon_svg(icone)}"
        "</span>"
        f'<div style="color:{cor_texto};">'
        f"<strong>{html.escape(titulo)}</strong><br>"
        f"{html.escape(str(valor))}"
        "</div>"
        "</div>"
    )


def _cards_mapa_html(dados: dict[str, object]) -> str:
    cards = dados["cards"]
    cobertura, perc_ativos = cards["Cobertura"]
    linha1 = "".join(
        [
            _card_mapa_html("Clientes", _numero(cards["Clientes"]), "users"),
            _card_mapa_html("Volume HL", _numero(cards["Volume HL"]), "droplet"),
            _card_mapa_html("Cobertura", f"{_numero(cobertura)} ({_numero(perc_ativos, 2)}%)", "user-check"),
            _card_mapa_html("R$ / Hab", f"R$ {_numero(cards['R$ / Hab'], 2)}", "house"),
            _card_mapa_html("Cob Amarela", _numero(cards["Cob Amarela"]), "circle", "#be9c00"),
            _card_mapa_html("Fator", _numero(cards["Fator"]), "ruler"),
        ]
    )
    linha2 = "".join(
        [
            _card_mapa_html("Potencial", _numero(cards["Potencial"]), "users"),
            _card_mapa_html("Volume UMB", _numero(cards["Volume UMB"]), "box"),
            _card_mapa_html("Cob. Potencial", f"{_numero(cards['Cob. Potencial'], 2)}%", "user-check"),
            _card_mapa_html("População", _numero(cards["População"]), "globe"),
            _card_mapa_html("Mun Amarelos", _numero(cards["Mun Amarelos"]), "location-dot", "#be9c00"),
        ]
    )
    return (
        '<div class="mc-cards-bloco">'
        f'<div class="mc-cards-linha">{linha1}</div>'
        f'<div class="mc-cards-linha">{linha2}</div>'
        "</div>"
    )


def _cards_mapa_ui(dados: dict[str, object]):
    cards = dados["cards"]
    cobertura, perc_ativos = cards["Cobertura"]
    return ui.div(
        ui.div(
            _card_mapa("Clientes", _numero(cards["Clientes"]), "users"),
            _card_mapa("Volume HL", _numero(cards["Volume HL"]), "droplet"),
            _card_mapa("Cobertura", f"{_numero(cobertura)} ({_numero(perc_ativos, 2)}%)", "user-check"),
            _card_mapa("R$ / Hab", f"R$ {_numero(cards['R$ / Hab'], 2)}", "house"),
            _card_mapa("Cob Amarela", _numero(cards["Cob Amarela"]), "circle", "#be9c00"),
            _card_mapa("Fator", _numero(cards["Fator"]), "ruler"),
            class_="mc-cards-linha",
        ),
        ui.div(
            _card_mapa("Potencial", _numero(cards["Potencial"]), "users"),
            _card_mapa("Volume UMB", _numero(cards["Volume UMB"]), "box"),
            _card_mapa("Cob. Potencial", f"{_numero(cards['Cob. Potencial'], 2)}%", "user-check"),
            _card_mapa("População", _numero(cards["População"]), "globe"),
            _card_mapa("Mun Amarelos", _numero(cards["Mun Amarelos"]), "location-dot", "#be9c00"),
            class_="mc-cards-linha",
        ),
        class_="mc-cards-bloco",
    )


def _card_lateral(titulo: str, valor: int, cor: str):
    return ui.div(
        ui.div(titulo, class_="mc-card-lateral-label", style=f"color:{cor};"),
        ui.div(_numero(valor), class_="mc-card-lateral-valor"),
        class_="mc-card-lateral",
        style=f"border-color:{cor};",
    )


def _cards_clientes(tabela: pl.DataFrame):
    anos = [date.today().year, date.today().year - 1, date.today().year - 2]
    cores = ["#06825D", "#397C6D", "#6c757d"]
    titulos = tabela.filter(pl.col("TITULO_ABERTO") == "Sim").height
    comodatos = tabela.filter(pl.col("POSSUI_CEV") == "Sim").height
    cards = [
        _card_lateral("Clientes com Títulos em Aberto", titulos, "#c0392b"),
        _card_lateral("Clientes com Comodatos em Aberto", comodatos, "#c0392b"),
    ]
    for ano, cor in zip(anos, cores, strict=True):
        quantidade = tabela.filter(pl.col("ULTIMA_COMPRA").dt.year() == ano).height
        cards.append(_card_lateral(f"Clientes com Últ. Compra em {ano}", quantidade, cor))
    return ui.TagList(*cards)


def _tooltip_municipio(linha: dict, historico: pl.DataFrame) -> str:
    cidade = html.escape(str(linha["CIDADE"]).strip())
    hist = historico.filter(pl.col("COD_IBGE") == linha["COD_IBGE"]).sort("MES")
    cabecalho = "".join(
        f"<th>{html.escape(str(mes)[4:6] + '/' + str(mes)[2:4])}</th>" for mes in hist.get_column("MES").to_list()
    )

    def linha_hist(rotulo: str, valores: list[str]) -> str:
        return f"<tr><th>{rotulo}</th>{''.join(f'<td>{valor}</td>' for valor in valores)}</tr>"

    linhas = hist.iter_rows(named=True)
    dados_hist = list(linhas)
    potencial = float(linha["POTENCIAL"] or 0)
    tabela_hist = (
        linha_hist("Cobertura", [_numero(item["QTD_PDV"]) for item in dados_hist])
        + linha_hist("% Cobertura", [f"{_numero(item['PERC_COB_CLI'], 2)}%" for item in dados_hist])
        + linha_hist(
            "% Potencial",
            [f"{_numero((float(item['QTD_PDV']) / potencial * 100) if potencial else 0, 1)}%" for item in dados_hist],
        )
        + linha_hist("Volume HL", [_numero(float(item["VOLUME_HL"]).__ceil__()) for item in dados_hist])
        + linha_hist("Qtd UMB", [_numero(item["QTD_UMB"]) for item in dados_hist])
        + linha_hist(
            "Falta p/ próx. nível",
            [
                f"<span style='color:{item['COR_POT_PROX_NVL']}'>{_numero(item['POT_PROX_NVL'])}</span>"
                for item in dados_hist
            ],
        )
    )
    return f"""
        <div class="mc-tooltip">
          <h4>{cidade}</h4>
          <table class="mc-tooltip-resumo">
            <tr><td>População:</td><td>{_numero(linha["POPULACAO"])}</td></tr>
            <tr><td>Clientes:</td><td>{_numero(linha["CLI_ATIVO"])}</td></tr>
            <tr><td>R$ / Hab:</td><td>R$ {_numero(linha["FAT_HAB"], 2)}</td></tr>
            <tr><td>Potencial:</td><td>{_numero(linha["POTENCIAL"])}</td></tr>
            <tr><td>Falta p/ próx. nível:</td><td style="color:{linha["COR_POT_PROX_NVL"]}">{_numero(linha["POT_PROX_NVL"])}</td></tr>
          </table>
          <div class="mc-tooltip-titulo">Histórico</div>
          <table class="mc-tooltip-historico"><thead><tr><th></th>{cabecalho}</tr></thead><tbody>{tabela_hist}</tbody></table>
        </div>
    """


ESTILO_MAPA_EXTRA = """
/* Achado real: o folium sempre inclui, por padrao, o CSS do
   "bootstrap-glyphicons" (Bootstrap 3, usado soh pelos icones default
   de folium.Icon -- nao usados aqui, so GeoJson) -- e esse arquivo
   reseta "html { font-size: 62.5% }" (o truque classico de fazer
   1rem = 10px). Como esse documento do iframe eh isolado (sem acesso
   ao style.css da pagina principal), TODO rem usado neste bloco
   (tooltip, legenda, grafico, cards) estava sendo calculado em cima de
   10px em vez dos 16px esperados -- 37,5% menor que o intencional.
   Reset de volta pro padrao do navegador, pra clamp()/rem baterem com
   o valor real. Precisa de "!important": o folium coloca este bloco
   <style> ANTES dos <link> de CSS externo no <head> (confirmado
   inspecionando o HTML gerado) -- sem "!important", a regra do
   bootstrap-glyphicons (que vem depois, mesma especificidade) venceria
   por ordem de origem. */
html { font-size: 16px !important; }
/* O tooltip de municipio (GeoJsonTooltip) vive no pane nativo do
   Leaflet ".leaflet-tooltip-pane", dentro de ".leaflet-map-pane" --
   que tem transform (translate3d, usado no pan do mapa) e por isso
   cria seu proprio contexto de empilhamento. Nenhum z-index colocado
   AQUI DENTRO (nem 1050, nem 99999) consegue vencer ".leaflet-top"/
   ".leaflet-bottom" (z-index: 1000, onde moram os L.control() de
   cards/legenda/grafico) porque a comparacao acontece um nivel acima:
   o ".leaflet-map-pane" inteiro (com z-index:400, de ".leaflet-pane")
   perde pra 1000 e fica atras dos controles, INDEPENDENTE do que tem
   de z-index nos filhos dele -- confirmado testando (Playwright) que o
   tooltip continuava atras dos cards mesmo com z-index 1050/9999 aqui.
   A correcao de verdade fica no listener "tooltipopen" mais abaixo
   (`_mapa_folium_html`), que tira o elemento do tooltip de dentro do
   mapPane assim que ele abre. Aqui so fica o z-index alto pro elemento
   ja reparentado. */
/* Fonte reduzida de novo -- o pedido original era so' "aumente um
   pouco" em cima do que se via com o bug do font-size ainda ativo
   (raiz de 10px); "1rem"/"1.25rem" ficou grande demais depois que a
   raiz foi corrigida pra 16px (mesmo efeito de dobrar-inflar visto na
   legenda/cards, ver comentario grande abaixo). Ajustado pra ficar so'
   um pouco maior que o original (0.9rem/1.15rem), nao mais que isso. */
/* Encolhido acompanhando o R (min-width 21rem -> 13.5rem) e depois aumentado
   "um pouco so" a pedido do usuario -- dai os valores intermediarios abaixo,
   nem os originais nem os do R. */
.mc-tooltip { min-width: 15.5rem; padding: 0.2rem; color: #333; font-family: sans-serif; font-size: 0.8rem; z-index: 9999 !important; }
.mc-tooltip h4 { margin: 0.15rem 0; text-align: center; font-size: 0.95rem; }
.mc-tooltip table { width: 100%; border-collapse: collapse; }
.mc-tooltip-resumo td:last-child { text-align: right; }
.mc-tooltip-titulo { margin-top: 0.35rem; padding: 0.16rem 0; background: #888; color: #fff; text-align: center; font-weight: 700; }
.mc-tooltip-historico th, .mc-tooltip-historico td { padding: 0.16rem 0.5rem; text-align: right; }
/* Legenda (canto inferior esquerdo) -- os valores em rem abaixo (cards,
   legenda, titulo do grafico) tinham sido ajustados numa rodada
   anterior enquanto o bug do font-size (ver "html { font-size: 16px
   !important }" mais acima) ainda existia -- ou seja, tudo foi
   calibrado visualmente em cima de uma raiz de 10px por engano. Depois
   do fix do font-size (raiz correta, 16px), os MESMOS valores em rem
   passaram a renderizar 60% maiores (16/10) do que o visto/aprovado
   antes -- os controles ficaram "extremamente grandes" (achado real do
   usuario, depois de rodar o app de verdade). Corrigido dividindo cada
   valor por 1.6, devolvendo o tamanho visual de antes agora sobre a
   raiz certa (nao mexido: ".mc-tooltip", que o usuario pediu maior
   nesta mesma rodada, e a LARGURA do grafico, "min(62vw, 60rem)", que
   era bug estrutural de verdade, nao calibração visual). */
/* Nesta rodada o R encolheu essa legenda por CSS proprio (font-size 10.5px,
   quadradinho de cor 12px, line-height 1.15) -- fonte e quadradinho aqui ja
   batiam com esses valores (0.66rem = 10.56px, 0.75rem = 12px), so' o
   espacamento entre linhas e a padding continuavam mais folgados. */
.mc-legenda {
  padding: 0.3rem 0.5rem;
  border-radius: 0.3rem; background: rgba(255, 255, 255, 0.92); color: #333;
  box-shadow: 0 0.15rem 0.5rem rgba(0, 0, 0, 0.18);
  font-size: 0.66rem;
  margin-bottom: 0.3rem;
}
.mc-legenda-item { display: flex; align-items: center; gap: 0.2rem; line-height: 1.15; }
.mc-legenda-cor { display: inline-block; width: 0.75rem; height: 0.75rem; border: 1px solid rgba(0, 0, 0, 0.28); }
/* Grafico (canto inferior direito) -- caixa alargada (era min(45vw,
   42rem)) a pedido do usuario; o grafico em si (elemento echarts logo
   abaixo, "#mc-grafico-echarts") ja e' width:100% da caixa, entao
   alargar a caixa alarga o grafico junto, sem precisar mexer no
   grid interno do echarts (chart.options["grid"] em _grafico_chart). */
/* Largura reduzida um pouco (era "62vw" -- pedido do usuario, "diminua
   um pouco a largura do control direito inferior"), e reduzida de novo nesta
   rodada na mesma proporcao do R (650px -> 480px, ou 0,74x): min(52vw, 55rem)
   -> min(38vw, 40rem). Continua em unidade relativa, nao no px fixo do R
   (CLAUDE.md, "altura e largura sempre em unidade relativa"). */
.mc-grafico-card { overflow: hidden; border-radius: 0.3rem; background: #fff; box-shadow: 0 0.15rem 0.55rem rgba(0, 0, 0, 0.22); width: min(38vw, 40rem); }
.mc-grafico-titulo { display: inline-block; padding: 0.22rem 0.47rem; border-radius: 0.3rem 0.3rem 0 0; background: #006400; color: #fff; font-size: 0.56rem; font-weight: 700; }
/* ".mc-card-mapa"/".mc-card-icone" nao ficam aqui -- os cards de KPI
   dentro do iframe (`_card_mapa_html`) usam estilo INLINE, nao essas
   classes (o tamanho de verdade foi corrigido la, direto no Python).
   So' o bloco/linha (wrappers de `_cards_mapa_html`) usam classe de
   verdade aqui. */
.mc-cards-bloco { display: flex; flex-direction: column; gap: clamp(0.35rem, 0.7vw, 0.75rem); }
.mc-cards-linha { display: flex; flex-wrap: wrap; gap: clamp(0.35rem, 0.7vw, 0.75rem); }
"""


def _bounds_geojson(geojson: dict) -> list[list[float]] | None:
    lats: list[float] = []
    lons: list[float] = []

    def visita(coordenadas):
        if not coordenadas:
            return
        primeiro = coordenadas[0]
        if isinstance(primeiro, int | float):
            lons.append(coordenadas[0])
            lats.append(coordenadas[1])
        else:
            for item in coordenadas:
                visita(item)

    for feature in geojson.get("features", []):
        visita((feature.get("geometry") or {}).get("coordinates"))
    if not lats:
        return None
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


_RANK_BORDA = {cor: posicao for posicao, cor in enumerate(d.ORDEM_BORDA)}


def _ordem_desenho_borda(cor: str) -> int:
    return _RANK_BORDA.get(cor, len(_RANK_BORDA))


def _dissolve_por_cor_borda(features: list[dict]) -> dict:
    grupos: dict[str, list] = {}
    for feature in features:
        cor = feature["properties"]["cor_borda"]
        geometria = shapely.make_valid(shape(feature["geometry"]))
        grupos.setdefault(cor, []).append(geometria)

    contornos = [
        {
            "type": "Feature",
            "geometry": mapping(unary_union(geometrias)),
            "properties": {"cor_borda": cor},
        }
        for cor, geometrias in sorted(grupos.items(), key=lambda par: _ordem_desenho_borda(par[0]))
    ]
    return {"type": "FeatureCollection", "features": contornos}


def _legenda_html(dados: dict[str, object]) -> str:
    def item(cor: str, rotulo: str) -> str:
        return (
            f'<div class="mc-legenda-item"><span class="mc-legenda-cor" style="background:{cor};"></span>{rotulo}</div>'
        )

    cobertura = (
        '<div class="mc-legenda"><strong>Cobertura</strong>'
        + item(d.COR_AREA_100, ">= 100%")
        + item(d.COR_AREA_75, ">= 75% < 100%")
        + item(d.COR_AREA_55, ">= 55% < 75%")
        + item(d.COR_AREA_0_M, "< 55%")
        + "</div>"
    )
    if dados["sem_distancia"]:
        return cobertura
    distancia = (
        f'<div class="mc-legenda"><strong>{dados["rotulo_distancia"]}</strong>'
        + item(d.COR_BORDA_SEDE, str(dados["rotulo_dist_zero"]))
        + item(d.COR_BORDA_75, "Até 75 km")
        + item(d.COR_BORDA_150, "De 75 km a 150 km")
        + item(d.COR_BORDA_150_M, "Acima de 150 km")
        + item(d.COR_BORDA_200, "+200 km Longa distância")
        + item(d.COR_BORDA_NA, "Sem distância cadastrada")
        + "</div>"
    )
    return cobertura + distancia


def _mapa_folium_html(dados: dict[str, object]) -> str:
    cidades: pl.DataFrame = dados["cidades"]
    historico: pl.DataFrame = dados["historico"]
    linhas_por_ibge = {str(linha["COD_IBGE"]): linha for linha in cidades.iter_rows(named=True)}

    features_fill = []
    for feature in dados["geojson"]["features"]:
        linha = linhas_por_ibge.get(str(feature["properties"]["COD_IBGE"]))
        if not linha:
            continue
        features_fill.append(
            {
                "type": "Feature",
                "geometry": feature["geometry"],
                "properties": {
                    "cor_area": linha["COR_AREA"],
                    "cor_borda": linha["COR_BORDA"],
                    "tooltip_html": _tooltip_municipio(linha, historico),
                },
            }
        )

    features_fill.sort(key=lambda feature: _ordem_desenho_borda(feature["properties"]["cor_borda"]))

    geojson_fill = {"type": "FeatureCollection", "features": features_fill}
    geojson_contorno = _dissolve_por_cor_borda(features_fill)

    fmap = folium.Map(tiles="OpenStreetMap", zoom_control=True, control_scale=False, attributionControl=False)
    limites = _bounds_geojson(geojson_fill)
    if limites:
        fmap.fit_bounds(limites)

    folium.GeoJson(
        geojson_fill,
        style_function=lambda feature: {
            "fillColor": feature["properties"]["cor_area"],
            "color": "#B8B8B8",
            "weight": 0.5,
            "opacity": 0.8,
            "fillOpacity": 0.6,
        },
        highlight_function=lambda feature: {"weight": 1},
        tooltip=folium.GeoJsonTooltip(
            fields=["tooltip_html"],
            aliases=[""],
            labels=False,
            sticky=False,
            parse_html=False,
        ),
    ).add_to(fmap)

    folium.GeoJson(
        geojson_contorno,
        style_function=lambda feature: {
            "fill": False,
            "fillOpacity": 0,
            "color": feature["properties"]["cor_borda"],
            "weight": 2.5,
            "opacity": 1,
            "interactive": False,
        },
    ).add_to(fmap)

    fmap.get_root().header.add_child(folium.Element(f"<style>{ESTILO_MAPA_EXTRA}</style>"))
    fmap.get_root().header.add_child(folium.Element('<script src="js/echarts.min.js"></script>'))

    legenda_html = json.dumps(_legenda_html(dados))
    cards_html = json.dumps(_cards_mapa_html(dados))
    grafico_opcoes = _grafico_chart(dados).dump_options()
    nome_mapa = fmap.get_name()
    script = f"""
    window.addEventListener('load', function() {{
        var mapa = {nome_mapa};
        mapa.zoomControl.setPosition('topright');

        // Cards de KPI (Clientes/Volume HL/Cobertura/...) -- controle
        // nativo do Leaflet, mesma tecnica de legenda/grafico abaixo.
        // Antes era uma <div> do Shiny flutuando por cima do iframe
        // inteiro (".mc-cards-sobre-mapa"), que cobria visualmente o
        // popup/tooltip de municipio (bug real encontrado pelo
        // usuario) -- aqui, os cards vivem no MESMO documento do
        // popup, sem sobrepor nada. Sem altura/overflow fixados: o
        // controle so ocupa o espaco que o conteudo real pede, sem
        // barra de rolagem (pedido explicito do usuario).
        var cards = L.control({{position: 'topleft'}});
        cards.onAdd = function() {{
            var div = L.DomUtil.create('div');
            div.innerHTML = {cards_html};
            L.DomEvent.disableClickPropagation(div);
            return div;
        }};
        cards.addTo(mapa);

        var legenda = L.control({{position: 'bottomleft'}});
        legenda.onAdd = function() {{
            var div = L.DomUtil.create('div');
            div.innerHTML = {legenda_html};
            L.DomEvent.disableClickPropagation(div);
            return div;
        }};
        legenda.addTo(mapa);

        var grafico = L.control({{position: 'bottomright'}});
        grafico.onAdd = function() {{
            var div = L.DomUtil.create('div', 'mc-grafico-card');
            div.innerHTML = '<div class="mc-grafico-titulo">Cobertura Potencial</div>'
                + '<div id="mc-grafico-echarts" style="width:100%;height:22vh;"></div>';
            L.DomEvent.disableClickPropagation(div);
            return div;
        }};
        grafico.addTo(mapa);

        if (typeof echarts !== 'undefined') {{
            var elementoGrafico = document.getElementById('mc-grafico-echarts');
            var instanciaGrafico = echarts.init(elementoGrafico);
            instanciaGrafico.setOption({grafico_opcoes});
            // Mesmo achado do hover do Diario de Venda (core/pyecharts_shiny.py)
            // -- o 1o callback do ResizeObserver dispara sozinho, so'
            // reportando o tamanho inicial, e "resize()" corta a animacao
            // de entrada do echarts se rodar cedo demais. Ignorado aqui
            // pelo mesmo motivo.
            var primeiroResizeGrafico = true;
            new ResizeObserver(function() {{
                if (primeiroResizeGrafico) {{ primeiroResizeGrafico = false; return; }}
                instanciaGrafico.resize();
            }}).observe(elementoGrafico);
        }}

        // Tooltip de municipio na frente dos cards/legenda/grafico
        // (L.control(), z-index 1000) -- nao da pra vencer isso so com
        // CSS/z-index (ver comentario grande em ESTILO_MAPA_EXTRA):
        // o tooltip nasce dentro de ".leaflet-map-pane", que tem
        // transform (pan do mapa) e por isso cria seu proprio contexto
        // de empilhamento, sempre perdendo pra ".leaflet-top"/
        // ".leaflet-bottom" (onde moram os controles) um nivel acima,
        // nao importa o z-index usado dentro do mapPane. Corrigido
        // tirando o elemento do tooltip de dentro do mapPane assim que
        // ele abre (evento nativo do Leaflet "tooltipopen"): a posicao
        // que o Leaflet ja calculou (transform relativo ao mapPane) e'
        // corrigida somando o deslocamento atual do mapPane
        // (`_getMapPanePos()`), e o elemento e' reanexado direto no
        // container do mapa -- irmao de ".leaflet-control-container",
        // fora do contexto de empilhamento baixo do mapPane.
        mapa.on('tooltipopen', function(e) {{
            var el = e.tooltip && e.tooltip.getElement && e.tooltip.getElement();
            if (!el) return;
            var panePos = mapa._getMapPanePos();
            var atual = L.DomUtil.getPosition(el);
            L.DomUtil.setPosition(el, L.point(atual.x + panePos.x, atual.y + panePos.y));
            mapa.getContainer().appendChild(el);
            el.style.zIndex = 10000;
        }});
    }});
    """
    fmap.get_root().script.add_child(folium.Element(script))
    return fmap.get_root().render()


def _grafico_chart(dados: dict[str, object]) -> Line:
    info = dados["grafico"]
    maximo = max(info["qtd"], default=0) * 1.3
    percentuais = json.dumps(info["percentuais"], ensure_ascii=False)
    chart = (
        Line(init_opts=opts.InitOpts(width="100%", height="16vh", bg_color="#ffffff"))
        .add_xaxis(info["labels"])
        .add_yaxis(
            "",
            info["qtd"],
            is_smooth=True,
            symbol="circle",
            symbol_size=5,
            linestyle_opts=opts.LineStyleOpts(color="#006400", width=2),
            itemstyle_opts=opts.ItemStyleOpts(color="#006400"),
            areastyle_opts=opts.AreaStyleOpts(opacity=0.25, color="#006400"),
            label_opts=opts.LabelOpts(
                is_show=True,
                position="bottom",
                color="#333",
                font_size=10,
                formatter=JsCode(
                    "function(p){var v=Array.isArray(p.value)?p.value[1]:p.value; "
                    "return Number(v).toLocaleString('pt-BR');}"
                ),
            ),
        )
        .add_yaxis(
            "",
            info["qtd"],
            is_smooth=True,
            symbol="circle",
            symbol_size=5,
            linestyle_opts=opts.LineStyleOpts(color="#006400", width=2),
            itemstyle_opts=opts.ItemStyleOpts(color="#006400"),
            label_opts=opts.LabelOpts(
                is_show=True,
                position="top",
                font_size=10,
                formatter=JsCode(
                    f"function(p){{var v={percentuais}; return Number(v[p.dataIndex]).toLocaleString('pt-BR', "
                    "{minimumFractionDigits:2,maximumFractionDigits:2})+'%';}"
                ),
            ),
        )
        .set_global_opts(
            legend_opts=opts.LegendOpts(is_show=False),
            tooltip_opts=opts.TooltipOpts(is_show=False),
            xaxis_opts=opts.AxisOpts(
                type_="category",
                axistick_opts=opts.AxisTickOpts(is_show=False),
                axisline_opts=opts.AxisLineOpts(is_show=False),
                axislabel_opts=opts.LabelOpts(font_size=10),
            ),
            yaxis_opts=opts.AxisOpts(is_show=False, min_=0, max_=maximo),
        )
    )
    chart.options["grid"] = {"top": 22, "bottom": 32, "left": 12, "right": 12, "containLabel": True}
    return chart


def _tabela_saiba_formatada(tabela: pl.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    tabela = tabela.sort("CLI_ATIVO", descending=True, nulls_last=True)
    estilos = []
    linhas = tabela.to_dicts()
    colunas = _COLUNAS_SAIBA_MAIS
    coluna_indice = {nome: posicao for posicao, nome in enumerate(colunas)}
    dados = []
    for indice, linha in enumerate(linhas):
        dados.append(
            {
                "Município": str(linha["CIDADE"]).strip(),
                "Distância (km)": _numero(linha["DISTANCIA"]) if linha["DISTANCIA"] is not None else None,
                "População": _numero(linha["POPULACAO"]) if linha["POPULACAO"] is not None else None,
                "Clientes": _numero(linha["CLI_ATIVO"]) if linha["CLI_ATIVO"] is not None else None,
                "Potencial": _numero(linha["POTENCIAL"]) if linha["POTENCIAL"] is not None else None,
                "Cob Potencial Min (75%)": f"{_numero(linha['PERC_CLI_POT_75'], 2)}%"
                if linha["PERC_CLI_POT_75"] is not None
                else None,
                "Potencial Crescim.": _numero(linha["POT_CRESC"]) if linha["POT_CRESC"] is not None else None,
                "HL": _numero(linha["VOLUME_HL"]) if linha["VOLUME_HL"] is not None else None,
                "UMB": _numero(linha["QTD_UMB"]) if linha["QTD_UMB"] is not None else None,
                "Clientes Cobertos": _numero(linha["QTD_PDV"]) if linha["QTD_PDV"] is not None else None,
                "Falta Próx. Nível": _numero(linha["POT_PROX_NVL"]) if linha["POT_PROX_NVL"] is not None else None,
                "% Ativos": f"{_numero(linha['PERC_CLI_ATIVO'], 2)}%" if linha["PERC_CLI_ATIVO"] is not None else None,
                "% Potencial": f"{_numero(linha['COB_POT'], 2)}%" if linha["COB_POT"] is not None else None,
                "R$/Hab": f"R$ {_numero(linha['FAT_HAB'], 2)}" if linha["FAT_HAB"] is not None else None,
            }
        )
        estilos.extend(
            [
                {
                    "rows": [indice],
                    "cols": [coluna_indice["Município"]],
                    "style": {"color": linha["COR_AREA"], "fontWeight": "bold"},
                },
                {
                    "rows": [indice],
                    "cols": [coluna_indice["% Ativos"]],
                    "style": {"color": linha["COR_PERC_CLI_ATIVO"], "fontWeight": "bold"},
                },
                {
                    "rows": [indice],
                    "cols": [coluna_indice["% Potencial"]],
                    "style": {"color": linha["COR_AREA"], "fontWeight": "bold"},
                },
            ]
        )
        if linha["FAT_HAB"] is not None and float(linha["FAT_HAB"]) < 5:
            estilos.append(
                {"rows": [indice], "cols": [coluna_indice["R$/Hab"]], "style": {"backgroundColor": "#F4C9CD"}}
            )
    return pd.DataFrame(dados, columns=colunas), estilos


def _tabela_clientes_formatada(tabela: pl.DataFrame) -> pd.DataFrame:
    rotulos = {
        "CLI_ATIVO": "Código",
        "NOME": "Nome",
        "FANTASIA": "Fantasia",
        "MUNICIPIO": "Município",
        "ENDERECO": "Endereço",
        "PORTE": "Classificação",
        "CANAL": "Canal",
        "VEN": "Ven",
        "TITULO_ABERTO": "Títulos Abertos",
        "POSSUI_CEV": "Comodato Aberto",
        "SUBEMPRESA": "Subrevenda",
        "ULTIMA_COMPRA": "Última Compra",
    }
    tabela = tabela.rename({coluna: rotulos.get(coluna, coluna) for coluna in tabela.columns})
    if "Última Compra" in tabela.columns:
        tabela = tabela.with_columns(pl.col("Última Compra").dt.strftime("%d/%m/%Y"))
    return para_pandas(tabela)


@module.server
def mapa_comercial_server(input, output, session, gatilho_mapa, versao_cache=None):
    def _versao_cache() -> None:
        if versao_cache is not None:
            versao_cache()

    dados_atuais = reactive.value(None, name="dados_atuais")
    inicializado = reactive.value(False, name="inicializado")
    mes_padrao = reactive.value(None, name="mes_padrao")
    mapa_ativo = reactive.value(False, name="mapa_ativo")
    opcoes_iniciais = reactive.value(None, name="opcoes_iniciais")
    cache_sessao: dict[tuple, dict[str, object]] = {}
    _versao_vista = {"mapa": 0}

    paginador_saiba = TabelaPaginada("saiba", input, session)
    paginador_ruptura = TabelaPaginada("ruptura", input, session)
    paginador_inativos = TabelaPaginada("inativos", input, session)

    @reactive.effect
    @reactive.event(gatilho_mapa, ignore_init=True)
    def _ativar_mapa():
        mapa_ativo.set(True)

    def revenda_atual() -> str:
        return REVENDA_PADRAO

    # No app original Classificação, Categoria e Vendedor só aparecem em parte
    # das revendas; aqui ficam sempre.
    def filtros_completos() -> bool:
        return True

    @reactive.effect
    async def _inicializar_filtros():
        if inicializado() or not mapa_ativo():
            return
        revenda = revenda_atual()
        try:
            meses = await asyncio.to_thread(d.meses_disponiveis, revenda)
            opcoes = await asyncio.to_thread(d.opcoes_filtro_produto, revenda)
            mes_inicial = next(iter(meses), None)
            mes_padrao.set(mes_inicial)
            ui.update_selectize("mes_mc", choices=meses, selected=mes_inicial)
            opcoes_iniciais.set(opcoes)
            inicializado.set(True)
        except Exception as exc:
            logger.exception("Falha ao inicializar filtros do Mapa Comercial")
            dados_atuais.set({"erro": str(exc)})

    @render.ui
    def filtros_produto_lateral():
        opcoes = opcoes_iniciais()
        if opcoes is None:
            return None
        campos = []
        for id_, rotulo, chave, so_completo in _CAMPOS_FILTRO_PRODUTO:
            if so_completo and not filtros_completos():
                continue
            valores_campo = opcoes.get(chave) or []
            if not valores_campo:
                continue
            campos.append(_filtro_selectize(id_, rotulo, valores_campo))
        if not campos:
            return None
        return ui.div(*campos, class_="filtros-dv mc-filtros-lateral")

    @render.ui
    def switch_distancia():
        revenda = revenda_atual()
        if not revenda or not d.escolhe_base_distancia(revenda):
            return None
        return ui.div(
            ui.span("Distância", class_="mc-switch-rotulo"),
            ui.input_radio_buttons(
                "mc_base_distancia",
                None,
                choices=["Revenda", "Fábrica"],
                selected="Revenda",
            ),
            class_="mc-switch-distancia mc-radio-distancia ms-auto",
        )

    def base_distancia_atual() -> str:
        try:
            return "fabrica" if input.mc_base_distancia() == "Fábrica" else "sede"
        except Exception:
            return "fabrica"

    def valores(nome: str) -> tuple[str, ...]:
        try:
            return _valores_input(getattr(input, nome)())
        except Exception:
            return ()

    @reactive.effect
    async def _crossfilter_produto():
        if not mapa_ativo():
            return
        try:
            base = await asyncio.to_thread(d.combinacoes_filtro_produto, revenda_atual() or "")
            filtros = {
                "MARCA": valores("mc_marca_filtro"),
                "CANAL_PROD": valores("mc_canal_filtro"),
                "SEGMENTO": valores("mc_categoria_filtro") if filtros_completos() else (),
                "VOLUME": valores("mc_embalagem_filtro"),
                "VEN": valores("mc_vendedor_filtro") if filtros_completos() else (),
            }
            filtrada = base
            for coluna, selecionados in filtros.items():
                if selecionados:
                    filtrada = filtrada.filter(pl.col(coluna).is_in(selecionados))

            ids = {
                "MARCA": "mc_marca_filtro",
                "CANAL_PROD": "mc_canal_filtro",
                "SEGMENTO": "mc_categoria_filtro",
                "VOLUME": "mc_embalagem_filtro",
                "VEN": "mc_vendedor_filtro",
            }
            for coluna, input_id in ids.items():
                if coluna in {"SEGMENTO", "VEN"} and not filtros_completos():
                    continue
                if filtros[coluna]:
                    continue
                opcoes = sorted(str(valor) for valor in filtrada.get_column(coluna).drop_nulls().unique().to_list())
                if coluna == "CANAL_PROD" and not filtros_completos():
                    opcoes = [valor for valor in opcoes if valor.strip().upper() not in {"CHOPP", "OUTRO"}]
                ui.update_selectize(input_id, choices=opcoes, selected=[])
        except Exception as exc:
            logger.warning(f"Crossfilter do Mapa Comercial não foi atualizado: {exc}")

    @reactive.effect
    async def _carregar_dados():
        if not mapa_ativo():
            return
        if versao_cache is not None and versao_cache() != _versao_vista["mapa"]:
            _versao_vista["mapa"] = versao_cache()
            cache_sessao.clear()
        revenda = revenda_atual()
        mes = input.mes_mc() or mes_padrao()
        req(revenda, mes)
        base_distancia = base_distancia_atual()
        chave = (
            revenda,
            mes,
            valores("mc_marca_filtro"),
            valores("mc_canal_filtro"),
            valores("mc_categoria_filtro") if filtros_completos() else (),
            valores("mc_embalagem_filtro"),
            valores("mc_vendedor_filtro") if filtros_completos() else (),
            valores("mc_classif_cliente_filtro") if filtros_completos() else (),
            base_distancia,
        )
        if chave in cache_sessao:
            dados_atuais.set(cache_sessao[chave])
            return
        try:
            resultado = await asyncio.to_thread(
                d.mapa_potencial,
                revenda,
                mes,
                chave[2],
                chave[3],
                chave[4],
                chave[5],
                chave[6],
                chave[7],
                chave[8],
            )
            if len(cache_sessao) >= 8:
                cache_sessao.pop(next(iter(cache_sessao)))
            cache_sessao[chave] = resultado
            dados_atuais.set(resultado)
        except Exception as exc:
            logger.exception("Falha ao carregar o Mapa Comercial")
            dados_atuais.set({"erro": str(exc)})

    def dados_validos() -> dict[str, object] | None:
        dados = dados_atuais()
        return dados if dados and "erro" not in dados else None

    @render.ui
    def mapa_leaflet():
        dados = dados_atuais()
        if dados and "erro" in dados:
            return ui.div(icon_svg("triangle-exclamation"), " ", dados["erro"], class_="mc-erro")
        if not dados:
            return None
        return ui.tags.iframe(
            srcdoc=_mapa_folium_html(dados),
            style=f"width:100%; height:{ALTURA_MAPA}; border:none;",
        )

    @render.ui
    def cards_saiba_mais():
        dados = dados_validos()
        return _cards_mapa_ui(dados) if dados else None

    @reactive.calc
    def _base_saiba():
        _versao_cache()
        dados = dados_validos()
        if not dados:
            return pd.DataFrame(), []
        return _tabela_saiba_formatada(d.saiba_mais(dados))

    @reactive.effect
    def _reiniciar_pagina_saiba():
        _base_saiba()
        paginador_saiba.reiniciar()

    @render.data_frame
    def tabela_saiba_mais():
        pandas_df, estilos = _base_saiba()
        fatia, estilos_fatia = paginador_saiba.fatiar_com_estilos(pandas_df, estilos)
        return render.DataTable(
            fatia,
            styles=estilos_fatia,
            height=ALTURA_TABELA_SAIBA,
            summary=False,
            filters=False,
            selection_mode="none",
        )

    @render.ui
    def controles_saiba():
        return paginador_saiba.controles(len(_base_saiba()[0]))

    @render.ui
    def css_largura_saiba():
        larguras = [ColunaLargura(c, _LARGURA_SAIBA_MAIS.get(c, 100)) for c in _COLUNAS_SAIBA_MAIS]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_saiba_mais')}", larguras))

    @reactive.calc
    def tabela_ruptura():
        dados = dados_validos()
        return d.ruptura_6m(dados) if dados else pl.DataFrame()

    @reactive.calc
    def tabela_inativos():
        dados = dados_validos()
        return d.clientes_inativos(dados) if dados else pl.DataFrame()

    @reactive.effect
    def _reiniciar_pagina_ruptura():
        tabela_ruptura()
        paginador_ruptura.reiniciar()

    @reactive.effect
    def _reiniciar_pagina_inativos():
        tabela_inativos()
        paginador_inativos.reiniciar()

    @render.data_frame
    def tabela_ruptura_6m():
        return render.DataTable(
            paginador_ruptura.fatiar(_tabela_clientes_formatada(tabela_ruptura())),
            height=ALTURA_TABELA,
            summary=False,
            filters=True,
            selection_mode="none",
        )

    @render.ui
    def controles_ruptura():
        return paginador_ruptura.controles(tabela_ruptura().height)

    @render.ui
    def css_largura_ruptura():
        larguras = [ColunaLargura(c, _LARGURA_CLIENTES.get(c, 100)) for c in _COLUNAS_RUPTURA_6M]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_ruptura_6m')}", larguras))

    @render.data_frame
    def tabela_clientes_inativos():
        return render.DataTable(
            paginador_inativos.fatiar(_tabela_clientes_formatada(tabela_inativos())),
            height=ALTURA_TABELA,
            summary=False,
            filters=True,
            selection_mode="none",
        )

    @render.ui
    def controles_inativos():
        return paginador_inativos.controles(tabela_inativos().height)

    @render.ui
    def css_largura_inativos():
        larguras = [ColunaLargura(c, _LARGURA_CLIENTES.get(c, 100)) for c in _COLUNAS_CLIENTES_INATIVOS]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela_clientes_inativos')}", larguras))

    @render.ui
    def cards_ruptura_6m():
        tabela = tabela_ruptura()
        return _cards_clientes(tabela) if tabela.height else None

    @render.ui
    def cards_clientes_inativos():
        tabela = tabela_inativos()
        return _cards_clientes(tabela) if tabela.height else None

    @render.download_button(filename=lambda: f"mapa-comercial-ruptura-6m-{date.today().isoformat()}.xlsx")
    async def baixar_ruptura_6m():
        buffer = io.BytesIO()
        tabela = _tabela_clientes_formatada(tabela_ruptura())
        await asyncio.to_thread(tabela.to_excel, buffer, index=False, engine="openpyxl")
        yield buffer.getvalue()

    @render.download_button(filename=lambda: f"mapa-comercial-clientes-inativos-{date.today().isoformat()}.xlsx")
    async def baixar_clientes_inativos():
        buffer = io.BytesIO()
        tabela = _tabela_clientes_formatada(tabela_inativos())
        await asyncio.to_thread(tabela.to_excel, buffer, index=False, engine="openpyxl")
        yield buffer.getvalue()
