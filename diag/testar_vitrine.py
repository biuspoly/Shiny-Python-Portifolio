"""Diagnóstico da Vitrine em R: abre o app, mede o tempo e clica em cada página como um usuário."""

import sys
import time

from playwright.sync_api import sync_playwright

URL = sys.argv[1]
# (menu pai ou None, item clicado, aba esperada)
CLIQUES = [
    ("Análise de Dados", "Power BI", "analise_dados_powerbi"),
    (None, "R", "analise_dados_r"),
    ("Ciência de Dados", None, "ciencia_dados"),
    ("Apps e Mobile", "Shiny R", "apps_mobile_shiny_r"),
    ("Sobre Mim", None, "sobre_mim"),
    ("Visão Geral", None, "visao_geral"),
]

with sync_playwright() as p:
    nav = p.chromium.launch()
    pagina = nav.new_page(viewport={"width": 1400, "height": 900})
    pagina.on("console", lambda m: print(f"[console {m.type}] {m.text[:300]}"))
    pagina.on("pageerror", lambda e: print(f"[ERRO JS] {e}"))
    inicio = time.time()
    pagina.goto(URL)

    alvo = None
    for _ in range(300):
        for f in pagina.frames:
            try:
                if f.evaluate("() => !!document.querySelector('#conteudo_visao_geral .card')"):
                    alvo = f
                    break
            except Exception:
                pass
        if alvo:
            break
        time.sleep(1)
    print(f"[TEMPO] visao geral apareceu em {time.time() - inicio:.1f}s")
    print("[QUADROS]", [f.url for f in pagina.frames])
    if alvo is None:
        sys.exit(0)
    print("[LINKS]", alvo.evaluate("() => [...document.querySelectorAll('.main-sidebar a.nav-link')].slice(0,4).map(a => a.outerHTML.slice(0,250))"))

    for pai, item, aba in CLIQUES:
        sb = alvo.locator(".main-sidebar")
        if pai:
            sb.get_by_text(pai, exact=True).first.click()
            time.sleep(0.8)
        if item:
            sb.locator("a.nav-link:visible").filter(has_text=item).first.click()
        t0 = time.time()
        tamanho = 0
        for _ in range(40):
            tamanho = alvo.evaluate("(s) => (document.getElementById(s) || {innerHTML: ''}).innerHTML.length", "conteudo_" + aba)
            if tamanho > 50:
                break
            time.sleep(0.5)
        estado = alvo.evaluate(
            """(a) => ({ativo: (document.querySelector('.tab-pane.active') || {}).id,
                        input_tabs: (window.Shiny && Shiny.shinyapp) ? Shiny.shinyapp.$inputValues['tabs'] : null,
                        recalc: document.getElementById('conteudo_' + a) ? document.getElementById('conteudo_' + a).className : null})""",
            aba,
        )
        print(f"[ABA] {aba}: html={tamanho} em {time.time() - t0:.1f}s | {estado}")
    pagina.screenshot(path="/tmp/fim.png")
    nav.close()
