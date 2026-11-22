import json
import uuid

from pyecharts.charts.base import Base


def renderizar(chart: Base, altura: str = "360px", mapas: dict[str, dict] | None = None) -> str:

    id_grafico = f"echarts-{uuid.uuid4().hex}"
    opcoes = chart.dump_options()
    mapas_json = json.dumps(mapas or {}, ensure_ascii=False, separators=(",", ":"))
    return f"""
    <div id="{id_grafico}" style="width:100%; height:{altura};"></div>
    <script>
    (function () {{
        var elemento = document.getElementById("{id_grafico}");
        if (!elemento || typeof echarts === "undefined") return;
        var instancia = echarts.init(elemento);
        var mapas = {mapas_json};
        Object.keys(mapas).forEach(function (nome) {{
            echarts.registerMap(nome, mapas[nome]);
        }});
        var opcoes = {opcoes};
        // Fonte do app, nunca a que o echarts impoe no Windows (ver o
        // comentario do modulo). Object.assign preserva o que o grafico tiver
        // definido: quem passa textStyle proprio continua mandando.
        opcoes.textStyle = Object.assign(
            {{ fontFamily: "'Source Sans Pro', -apple-system, 'Segoe UI', Roboto, sans-serif" }},
            opcoes.textStyle || {{}}
        );
        instancia.setOption(opcoes);
        // ResizeObserver sempre dispara 1 callback inicial (so' reportando
        // o tamanho que o elemento ja tem, mesmo sem ter mudado de
        // verdade) -- pego confirmado medindo com Playwright: "resize()"
        // rodava ~70ms depois do "setOption()", e o metodo resize() do
        // echarts redesenha na hora, sem reanimar, cortando a animacao de
        // entrada quase no comeco (o grafico "aparecia ja pronto", achado
        // real do usuario no hover do Diario de Venda). Ignorar so' essa
        // 1a chamada resolve, sem perder o resize de verdade quando o
        // container mudar de tamanho depois (ex: filtro lateral abrindo).
        var primeiroResize = true;
        new ResizeObserver(function () {{
            if (primeiroResize) {{ primeiroResize = false; return; }}
            instancia.resize();
        }}).observe(elemento);
    }})();
    </script>
    """
