"""Monta o site estático em site/: a vitrine na raiz e cada app exportado pelo
Shinylive na sua subpasta (o ambiente Python fica uma vez só, compartilhado).

Uso (da raiz do repositório): python -m publicar.montar_site
Para ver: python -m http.server --directory site 8008
"""

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
# Os originais em R (webR), numa raiz própria: o Shinylive de R e o de Python têm arquivos com o mesmo
# nome em shinylive/, de versões diferentes.
APPS_R = {"Acessos": "acessos", "Logistico": "logistico", "Comercial": "comercial"}
ANEXOS_EXEMPLO = ("PDV_exemplo.pdf", "CEV_exemplo.pdf", "CANHOTO_exemplo.pdf")


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
    for pasta, caminho in APPS_R.items():
        print(f"exportando R/{pasta} -> site/r/{caminho}/")
        origem, destino = (RAIZ / "R" / pasta).as_posix(), (SITE / "r").as_posix()
        subprocess.run(
            [rscript, "-e", f'{prefixo}shinylive::export("{origem}", "{destino}", subdir = "{caminho}")'],
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
    for pasta, caminho in APPS.items():
        print(f"exportando {pasta} -> site/{caminho}/")
        subprocess.run(
            [_shinylive(), "export", str(RAIZ / pasta), str(SITE), "--subdir", caminho],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    _exportar_r()
    shutil.copytree(RAIZ / "vitrine", SITE, dirs_exist_ok=True)
    # Sem isto o GitHub Pages passa o site pelo Jekyll, que esconde pastas com "_".
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    tamanho = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file()) / 1024**2
    print(f"site pronto em {SITE} ({tamanho:.0f} MB)")


if __name__ == "__main__":
    montar()
