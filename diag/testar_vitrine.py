"""Diagnóstico da Vitrine em R: abre o app, mede o tempo e clica em cada página como um usuário."""

import re
import sys
import time

from playwright.sync_api import sync_playwright

URL = sys.argv[1]
import os
LARGURA = int(os.environ.get("LARGURA", "1400"))
os.makedirs("prints_diag", exist_ok=True)
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
    pagina = nav.new_page(viewport={"width": LARGURA, "height": 900})
    pagina.on("console", lambda m: print(f"[console {m.type}] {m.text[:300]}"))
    pagina.on("pageerror", lambda e: print(f"[ERRO JS] {e}"))
    baixado = {"total": 0, "maiores": []}

    def _resposta(r):
        try:
            tam = int(r.headers.get("content-length") or 0)
        except Exception:
            tam = 0
        baixado["total"] += tam
        baixado["maiores"].append((tam, r.status, r.url[-90:]))
        if r.status >= 400:
            print(f"[HTTP {r.status}] {r.url}")

    pagina.on("response", _resposta)
    if len(sys.argv) > 3:
        # visita antes outra página do site (a vitrine em Python, na raiz), como um visitante real
        pagina.goto(sys.argv[3])
        time.sleep(40)
        print("[ANTES] visitou", sys.argv[3])
    inicio = time.time()
    baixado["total"] = 0
    baixado["maiores"].clear()
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
    print(f"[BAIXADO] {baixado['total'] / 1e6:.1f} MB (pelo content-length)")
    for tam, st, u in sorted(baixado["maiores"], reverse=True)[:25]:
        print(f"[ARQ] {tam / 1e6:6.2f} MB {st} {u}")
    print("[QUADROS]", [f.url for f in pagina.frames])
    if alvo is None:
        sys.exit(0)
    print("[LINKS]", alvo.evaluate("() => [...document.querySelectorAll('.main-sidebar a.nav-link')].slice(0,4).map(a => a.outerHTML.slice(0,250))"))

    for pai, item, aba in CLIQUES:
        sb = alvo.locator(".main-sidebar")
        if LARGURA < 900:
            alvo.locator("[data-widget=pushmenu]").first.click()
            time.sleep(0.8)
        if pai:
            sb.get_by_text(pai, exact=True).first.click()
            time.sleep(0.8)
        if item:
            sb.locator("a.nav-link:visible").filter(has_text=re.compile(r"^\s*" + re.escape(item) + r"\s*$")).first.click()
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
        time.sleep(2)
        pagina.screenshot(path=f"prints_diag/{sys.argv[2]}_{LARGURA}_{aba}.png")
    pagina.screenshot(path="/tmp/fim.png")
    nav.close()
