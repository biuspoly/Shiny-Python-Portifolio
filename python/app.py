"""Acompanhamentos: os seis apps em Python num processo só, para o Posit Connect Cloud.

Cada app segue independente na sua pasta (é assim que o Shinylive exporta cada um e é assim que ele roda
sozinho com `shiny run python/Comercial/app.py`). Aqui eles viram rotas de um app só:

    /                 página principal, com um cartão por acompanhamento
    /comercial/       o app Comercial, inteiro
    /logistico/       o Logístico... e assim por diante

Cada app só é carregado no primeiro acesso à sua rota, para o servidor acordar rápido.

Os apps têm pacotes com o mesmo nome (`core`, `pages`) e conteúdo diferente. Para conviverem no mesmo
processo, cada um é importado como um pacote próprio (`acomp_comercial`, `acomp_logistico`...) e um gancho
no `import` manda o `from core...` de cada arquivo para o `core` do próprio app, inclusive os imports feitos
dentro de funções. O código dos apps não muda.

Este arquivo fica na pasta python/, acima dos apps: a pasta que o Posit publica (a do arquivo principal)
já contém todos eles. O requirements.txt ao lado é a união dos de cada app (publicar/preparar_posit.py).

Rodar localmente (da raiz do repositório): shiny run python/app.py
"""

from __future__ import annotations

import asyncio
import builtins
import html
import importlib
import importlib.util
import json
import sys
import threading
import types
from dataclasses import dataclass
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, PlainTextResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

PASTA = Path(__file__).resolve().parent
RAIZ_APPS = PASTA  # python/: cada app numa subpasta


@dataclass(frozen=True)
class Painel:
    pasta: str  # pasta do app (e chave em Vitrine/enderecos.json)
    rota: str  # caminho na URL

    @property
    def pacote(self) -> str:
        return f"acomp_{self.rota}"


PAINEIS = [
    Painel("Comercial", "comercial"),
    Painel("Logistico", "logistico"),
    Painel("Financeiro", "financeiro"),
    Painel("Apuracao", "apuracao"),
    Painel("Fiscal", "fiscal"),
    Painel("Monitoramento", "monitoramento"),
    Painel("Acessos", "acessos"),
]


# Imports isolados por app -----------------------------------------------------------------------

# pacote do app -> nomes de topo que pertencem a ele (core, pages, scripts...)
_NOMES_DO_APP: dict[str, set[str]] = {}
_import_original = builtins.__import__


def _import_do_app(name, globals=None, locals=None, fromlist=(), level=0):
    if level == 0 and globals:
        pacote = (globals.get("__name__") or "").split(".", 1)[0]
        nomes = _NOMES_DO_APP.get(pacote)
        topo = name.split(".", 1)[0]
        if nomes and topo in nomes:
            modulo = _import_original(f"{pacote}.{name}", globals, locals, fromlist, 0)
            # Sem fromlist (`import core.cores`), quem chama liga o nome de topo: devolve o `core` do app.
            return modulo if fromlist else sys.modules[f"{pacote}.{topo}"]
    return _import_original(name, globals, locals, fromlist, level)


builtins.__import__ = _import_do_app


def _nomes_de_topo(pasta: Path) -> set[str]:
    nomes = set()
    for item in pasta.iterdir():
        if item.is_file() and item.suffix == ".py" and item.stem != "app":
            nomes.add(item.stem)
        elif item.is_dir() and not item.name.startswith((".", "_")) and any(item.rglob("*.py")):
            nomes.add(item.name)
    return nomes


def _carregar(painel: Painel):
    """Importa o app.py do painel como <pacote>.app e devolve o objeto App do Shiny."""
    pasta = RAIZ_APPS / painel.pasta
    if not (pasta / "app.py").is_file():
        raise FileNotFoundError(f"{pasta / 'app.py'} não existe")
    if painel.pacote not in sys.modules:
        pacote = types.ModuleType(painel.pacote)
        pacote.__path__ = [str(pasta)]
        pacote.__package__ = painel.pacote
        pacote.__file__ = str(pasta / "__init__.py")
        sys.modules[painel.pacote] = pacote
        _NOMES_DO_APP[painel.pacote] = _nomes_de_topo(pasta)
    return importlib.import_module(f"{painel.pacote}.app").app


class AppSobDemanda:
    """Carrega o app no primeiro acesso à rota e daí em diante só repassa as requisições."""

    def __init__(self, painel: Painel):
        self.painel = painel
        self._app = None
        self._erro: str | None = None
        self._trava = threading.Lock()

    def _garantir(self):
        with self._trava:
            if self._app is None and self._erro is None:
                try:
                    self._app = _carregar(self.painel)
                except Exception as exc:  # o resto do portfólio continua no ar
                    self._erro = f"{type(exc).__name__}: {exc}"
                    print(f"[acompanhamentos] erro ao carregar {self.painel.pasta}: {self._erro}", file=sys.stderr)

    async def __call__(self, scope, receive, send):
        if self._app is None and self._erro is None:
            await asyncio.to_thread(self._garantir)
        if self._app is None:
            if scope["type"] == "http":
                resposta = PlainTextResponse(f"O app {self.painel.pasta} não carregou.\n{self._erro}", 500)
                await resposta(scope, receive, send)
            return
        await self._app(scope, receive, send)


# Página principal --------------------------------------------------------------------------------


def _dados_vitrine():
    """Nome, cor, resumo e telas de cada app: os mesmos da Vitrine (uma fonte só)."""
    caminho = RAIZ_APPS / "Vitrine" / "app.py"
    especificacao = importlib.util.spec_from_file_location("acomp_vitrine_dados", caminho)
    modulo = importlib.util.module_from_spec(especificacao)
    especificacao.loader.exec_module(modulo)
    return {app["pasta"]: app for app in modulo.APPS_PYTHON}, modulo.ENDERECOS["site"]


def _pagina_principal() -> str:
    dados, site = _dados_vitrine()
    cartoes = []
    for painel in PAINEIS:
        app = dados[painel.pasta]
        telas = "".join(f"<li>{html.escape(tela)}</li>" for tela in app["telas"])
        cartoes.append(f"""
        <article class="app" style="--cor: {app["cor"]}">
          <a class="foto" href="{painel.rota}/"><img src="img/{app["imagem"]}" alt="Tela do {html.escape(app["nome"])}"
             loading="lazy"></a>
          <div class="corpo">
            <h2>{html.escape(app["nome"])}</h2>
            <p class="resumo">{html.escape(app["resumo"])}</p>
            <ul>{telas}</ul>
          </div>
          <a class="abrir" href="{painel.rota}/">Abrir o {html.escape(app["nome"])}</a>
        </article>""")
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Acompanhamentos | Portfólio Marlon Amaral</title>
<link rel="icon" href="img/icone.svg" type="image/svg+xml">
<style>{(PASTA / "principal.css").read_text(encoding="utf-8")}</style>
</head>
<body>
<header class="topo">
  <div class="conteudo">
    <a class="marca" href="{site}"><img src="img/icone.svg" alt=""><span>Portfólio Marlon Amaral</span></a>
    <h1>Acompanhamentos em Shiny for Python</h1>
    <p>Os seis painéis de gestão do sistema, num servidor só. Cada um abre no próprio endereço
    (<code>/comercial/</code>, <code>/logistico/</code>...); os dados são fictícios, no formato da produção.</p>
  </div>
</header>
<main class="conteudo">
  <div class="grade">{"".join(cartoes)}</div>
</main>
<footer class="conteudo">
  <a href="{site}">Voltar à vitrine</a> · código em
  <a href="https://github.com/biuspoly/shiny-portfolio">github.com/biuspoly/shiny-portfolio</a>
</footer>
</body>
</html>"""


_HTML_PRINCIPAL: str | None = None


async def principal(request):
    global _HTML_PRINCIPAL
    if _HTML_PRINCIPAL is None:
        _HTML_PRINCIPAL = _pagina_principal()
    return HTMLResponse(_HTML_PRINCIPAL)


async def saude(request):
    return PlainTextResponse("ok")


app = Starlette(
    routes=[
        Route("/", principal),
        Route("/saude", saude),
        Mount("/img", app=StaticFiles(directory=RAIZ_APPS / "Vitrine" / "www" / "img"), name="img"),
        *[Mount(f"/{painel.rota}", app=AppSobDemanda(painel)) for painel in PAINEIS],
    ]
)


if __name__ == "__main__":
    print(json.dumps({p.rota: str(RAIZ_APPS / p.pasta) for p in PAINEIS}, indent=2, ensure_ascii=False))
