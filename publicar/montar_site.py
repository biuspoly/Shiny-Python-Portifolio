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


def _shinylive() -> str:
    """O executável do shinylive do mesmo ambiente Python (não roda com "python -m")."""
    pasta = Path(sys.executable).parent
    for nome in ("shinylive.exe", "shinylive"):
        if (pasta / nome).exists():
            return str(pasta / nome)
    return shutil.which("shinylive") or "shinylive"


def montar() -> None:
    if SITE.exists():
        shutil.rmtree(SITE)
    for pasta, caminho in APPS.items():
        print(f"exportando {pasta} -> site/{caminho}/")
        subprocess.run(
            [_shinylive(), "export", str(RAIZ / pasta), str(SITE), "--subdir", caminho],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    shutil.copytree(RAIZ / "vitrine", SITE, dirs_exist_ok=True)
    # Sem isto o GitHub Pages passa o site pelo Jekyll, que esconde pastas com "_".
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    tamanho = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file()) / 1024**2
    print(f"site pronto em {SITE} ({tamanho:.0f} MB)")


if __name__ == "__main__":
    montar()
