"""Monta o site estático em site/: a vitrine (app Shiny) na raiz e, na sua subpasta, cada app que
ainda não tem endereço no Posit Connect Cloud (Vitrine/enderecos.json). Tudo pelo Shinylive.

Uso (da raiz do repositório): python -m publicar.montar_site
Para ver: python -m http.server --directory site 8008
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
SITE = RAIZ / "site"
APPS = {
    "Comercial": "comercial",
    "Logistico": "logistico",
    "Financeiro": "financeiro",
    "Fiscal": "fiscal",
    "Monitoramento": "monitoramento",
    "Acessos": "acessos",
}
# Os originais em R (webR), cada um na sua própria raiz (site/r/<app>/): o Shinylive de R e o de Python
# têm arquivos com o mesmo nome em shinylive/, de versões diferentes. E apps de R exportados para a mesma
# raiz dividem a pasta de pacotes, e o navegador baixa os pacotes de todos ao abrir qualquer um deles
# (a Vitrine chegou a baixar 164 MB, com sf, terra, duckdb e plotly, que ela não usa).
APPS_R = {"Acessos": "acessos", "Logistico": "logistico", "Comercial": "comercial", "Vitrine": "vitrine"}
ANEXOS_EXEMPLO = ("PDV_exemplo.pdf", "CEV_exemplo.pdf", "CANHOTO_exemplo.pdf")
ENDERECOS = json.loads((RAIZ / "Vitrine" / "enderecos.json").read_text(encoding="utf-8"))


def endereco_posit(linguagem: str, pasta: str) -> str | None:
    """O endereço do app no Posit: o próprio, ou a rota dele no app unificado da linguagem."""
    proprio = ENDERECOS[linguagem].get(pasta)
    if proprio:
        return proprio
    unificado = (ENDERECOS.get("acompanhamentos") or {}).get(linguagem)
    if not unificado or pasta not in ENDERECOS[linguagem]:  # a Vitrine em R não faz parte do unificado
        return None
    base = unificado.rstrip("/")
    return f"{base}/{pasta.lower()}/" if linguagem == "python" else f"{base}/?painel={pasta.lower()}"


def _sem_posit(apps: dict[str, str], linguagem: str) -> dict[str, str]:
    """Só os apps sem endereço no Posit: esses continuam no Shinylive."""
    return {pasta: caminho for pasta, caminho in apps.items() if not endereco_posit(linguagem, pasta)}


def _redirecionamentos() -> None:
    """Na subpasta de cada app que foi para o Posit, uma página que leva até lá: os links antigos
    (vitrine em R, currículo, LinkedIn) continuam funcionando."""
    for linguagem, apps, prefixo in (("python", APPS, ""), ("r", APPS_R, "r/")):
        for pasta, caminho in apps.items():
            destino = endereco_posit(linguagem, pasta)
            if not destino:
                continue
            arquivo = SITE / f"{prefixo}{caminho}" / "index.html"
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            arquivo.write_text(
                '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
                f'<meta http-equiv="refresh" content="0; url={destino}"><link rel="canonical" href="{destino}">'
                f"<title>Abrindo {pasta}…</title></head>"
                f'<body><p>Este app agora roda no Posit Connect Cloud: <a href="{destino}">{destino}</a></p>'
                f"<script>location.replace({json.dumps(destino)} + location.search.replace(/^\\?/, "
                f"{json.dumps('&' if '?' in destino else '?')}).replace(/[?&]$/, ''));</script>"
                "</body></html>",
                encoding="utf-8",
            )
            print(f"redireciona site/{prefixo}{caminho}/ -> {destino}")


def _shinylive() -> str:
    """O executável do shinylive do mesmo ambiente Python (não roda com "python -m")."""
    pasta = Path(sys.executable).parent
    for nome in ("shinylive.exe", "shinylive"):
        if (pasta / nome).exists():
            return str(pasta / nome)
    return shutil.which("shinylive") or "shinylive"


def _exportar_r() -> None:
    rscript = shutil.which("Rscript") or "C:/Program Files/R/R-4.6.1/bin/Rscript.exe"
    biblioteca = RAIZ / ".rlib"  # a biblioteca local de R do portfólio, quando existe (no CI não)
    prefixo = f'.libPaths(c("{biblioteca.as_posix()}", .libPaths())); ' if biblioteca.exists() else ""
    for pasta, caminho in _sem_posit(APPS_R, "r").items():
        print(f"exportando R/{pasta} -> site/r/{caminho}/")
        origem, destino = (RAIZ / "R" / pasta).as_posix(), (SITE / "r" / caminho).as_posix()
        subprocess.run(
            [rscript, "-e", f'{prefixo}shinylive::export("{origem}", "{destino}")'],
            check=True,
            stdout=subprocess.DEVNULL,
        )


def montar() -> None:
    if SITE.exists():
        shutil.rmtree(SITE)
    # O que a tela grava rodando local não vai para o site: lá cada visitante começa do zero.
    for sobra in ("Financeiro/data/manual", "Financeiro/data/leituras", "Financeiro/uploads"):
        shutil.rmtree(RAIZ / sobra, ignore_errors=True)
    for anexo in (RAIZ / "Logistico" / "uploads").rglob("*"):
        if anexo.is_file() and anexo.name not in ANEXOS_EXEMPLO:
            anexo.unlink()
    for anexo in (RAIZ / "R" / "Logistico" / "Anexos_Comodato").glob("*"):
        if anexo.name not in ANEXOS_EXEMPLO:
            anexo.unlink()
    for pdf in (RAIZ / "R" / "Logistico" / "pages" / "Comodatos" / "Dados").glob("*.[pP][dD][fF]"):
        pdf.unlink()
    print("exportando Vitrine -> site/")
    subprocess.run([_shinylive(), "export", str(RAIZ / "Vitrine"), str(SITE)], check=True, stdout=subprocess.DEVNULL)
    for pasta, caminho in _sem_posit(APPS, "python").items():
        print(f"exportando {pasta} -> site/{caminho}/")
        subprocess.run(
            [_shinylive(), "export", str(RAIZ / pasta), str(SITE), "--subdir", caminho],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    _exportar_r()
    _redirecionamentos()
    # Sem isto o GitHub Pages passa o site pelo Jekyll, que esconde pastas com "_".
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    tamanho = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file()) / 1024**2
    print(f"site pronto em {SITE} ({tamanho:.0f} MB)")


if __name__ == "__main__":
    montar()
