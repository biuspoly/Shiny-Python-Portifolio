"""Diagnóstico da Vitrine em R: abre o app, mede o tempo e clica em cada página."""

import sys
import time

from playwright.sync_api import sync_playwright

URL = sys.argv[1]
SHINYLIVE = sys.argv[2] == "shinylive"
ABAS = [
    "id_visao_geral", "id_analise_dados_powerbi", "id_analise_dados_r", "id_analise_dados_python",
    "id_ciencia_dados", "id_engenharia_dados_r", "id_automacoes_python", "id_apps_mobile_shiny_r",
    "id_dev_open_source_r", "id_sobre_mim",
]

with sync_playwright() as p:
    nav = p.chromium.launch()
    pagina = nav.new_page()
    pagina.on("console", lambda m: print(f"[console {m.type}] {m.text[:300]}"))
    pagina.on("pageerror", lambda e: print(f"[ERRO JS] {e}"))
    inicio = time.time()
    pagina.goto(URL)

    def quadro():
        if not SHINYLIVE:
            return pagina.main_frame
        for f in pagina.frames:
            if "app_" in f.url or f.url.rstrip("/").endswith("app"):
                return f
        return None

    alvo = None
    for _ in range(300):
        alvo = quadro()
        if alvo is not None:
            try:
                if alvo.evaluate("() => !!document.querySelector('#conteudo_visao_geral .card')"):
                    break
            except Exception:
                pass
        time.sleep(1)
    print(f"[TEMPO] visao geral apareceu em {time.time() - inicio:.1f}s")
    print("[QUADROS]", [f.url for f in pagina.frames])
    if alvo is None:
        sys.exit(0)

    for aba in ABAS:
        saida = "conteudo_" + aba[3:]
        alvo.evaluate(
            "(a) => { const el = document.querySelector('a[href=\"#shiny-tab-' + a + '\"]'); if (el) el.click(); }",
            aba,
        )
        t0 = time.time()
        tamanho = 0
        for _ in range(40):
            tamanho = alvo.evaluate(
                "(s) => { const el = document.getElementById(s); return el ? el.innerHTML.length : -1; }", saida
            )
            if tamanho > 50:
                break
            time.sleep(0.5)
        estado = alvo.evaluate(
            """(a) => {
                const pane = document.getElementById('shiny-tab-' + a);
                const link = document.querySelector('a[href="#shiny-tab-' + a + '"]');
                return {pane_existe: !!pane, pane_ativo: pane ? pane.className : null,
                        link_existe: !!link, link_attrs: link ? link.outerHTML.slice(0, 200) : null,
                        input_tabs: (window.Shiny && Shiny.shinyapp) ? Shiny.shinyapp.$inputValues['tabs'] : null};
            }""",
            aba,
        )
        print(f"[ABA] {aba}: html={tamanho} em {time.time() - t0:.1f}s | {estado}")
    nav.close()
