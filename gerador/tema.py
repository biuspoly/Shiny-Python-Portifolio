"""Compila o tema Flatly do Bootstrap para www/css/flatly.min.css de cada app.

O Shinylive roda sem o libsass, então o tema vai pronto. Rodar de novo só ao
trocar a versão do Shiny.
"""

from shiny import ui

from gerador.base import PY

APPS = ["Comercial", "Logistico", "Financeiro", "Apuracao", "Fiscal", "Monitoramento", "Acessos"]


def gerar() -> None:
    css = ui.Theme("flatly").to_css()
    for app in APPS:
        pasta = PY / app / "www" / "css"
        if pasta.exists():
            (pasta / "flatly.min.css").write_text(css, encoding="utf-8")
            print(f"  {app}/www/css/flatly.min.css")
