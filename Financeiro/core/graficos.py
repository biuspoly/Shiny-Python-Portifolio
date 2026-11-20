"""Gráfico ECharts a partir de um dict de opções montado em Python.

O echarts.min.js é carregado uma vez no app.py; aqui só sai o <div> e o
<script> que desenha. Texto que começa com "js:" vira código JavaScript cru
(formatadores de tooltip e de eixo), o resto vai como JSON.
"""

import json
import re
import uuid

from shiny import ui

_JS_CRU = re.compile(r'"js:((?:[^"\\]|\\.)*)"')

# Formatador pt-BR reaproveitado nos tooltips e eixos.
NUMERO_BR = (
    "js:function (v) { return v == null ? '-' : Number(v).toLocaleString('pt-BR', {maximumFractionDigits: 0}); }"
)
MOEDA_BR = (
    "js:function (v) { return v == null ? '-' : "
    "'R$ ' + Number(v).toLocaleString('pt-BR', {maximumFractionDigits: 0}); }"
)
# Para eixo: "R$ 50 mil", "R$ 1,2 mi" -- o valor inteiro não cabe entre as marcas.
MOEDA_CURTA = (
    "js:function (v) { var a = Math.abs(v); "
    "if (a >= 1e6) return 'R$ ' + (v / 1e6).toLocaleString('pt-BR', {maximumFractionDigits: 1}) + ' mi'; "
    "if (a >= 1e3) return 'R$ ' + (v / 1e3).toLocaleString('pt-BR', {maximumFractionDigits: 0}) + ' mil'; "
    "return 'R$ ' + v; }"
)


def eixo_valor(nome: str = "", formato: str = NUMERO_BR, **extra) -> dict:
    return {"type": "value", "name": nome, "axisLabel": {"formatter": formato}, **extra}


def _para_js(opcoes: dict) -> str:
    texto = json.dumps(opcoes, ensure_ascii=False)
    return _JS_CRU.sub(lambda m: json.loads(f'"{m.group(1)}"'), texto)


def grafico(opcoes: dict, altura: str = "40vh", mapas: dict[str, str] | None = None) -> ui.HTML:
    """`mapas`: nome do mapa -> caminho do GeoJSON em www/, registrado antes de desenhar."""
    id_div = f"echarts-{uuid.uuid4().hex}"
    mapas_js = json.dumps(mapas or {})
    return ui.HTML(f"""
    <div id="{id_div}" class="grafico-echarts" style="width:100%;height:{altura};"></div>
    <script>
    (function () {{
      var el = document.getElementById("{id_div}");
      if (!el || typeof echarts === "undefined") return;
      var mapas = {mapas_js};
      var nomes = Object.keys(mapas);
      Promise.all(nomes.map(function (n) {{
        if (echarts.getMap(n)) return null;
        return fetch(mapas[n]).then(function (r) {{ return r.json(); }})
          .then(function (geo) {{ echarts.registerMap(n, geo); }});
      }})).then(function () {{
        var g = echarts.init(el);
        var opcoes = {_para_js(opcoes)};
        var fonte = {{ fontFamily: "'Source Sans Pro', 'Segoe UI', Roboto, sans-serif" }};
        opcoes.textStyle = Object.assign(fonte, opcoes.textStyle || {{}});
        g.setOption(opcoes);
        new ResizeObserver(function () {{ g.resize(); }}).observe(el);
      }});
    }})();
    </script>
    """)
