"""Deixa a main pronta para o Posit Connect Cloud publicar os dois apps unificados.

O Posit publica direto da main:
    python/app.py   (Shiny for Python) -> instala python/requirements.txt
    r/app.R         (R Shiny)          -> instala os pacotes do r/manifest.json

Os dois arquivos de dependência são gerados aqui:
- python/requirements.txt: a união dos requirements.txt dos seis apps;
- r/manifest.json: o rsconnect::writeManifest() da pasta r/ (precisa dos pacotes de R instalados).

Rode depois de mudar as dependências de um app, ou de criar/apagar arquivo num app em R, e faça commit
dos dois arquivos junto:

    python -m publicar.preparar_posit

No workflow, `--conferir` só confere (sem R): falha se o requirements.txt não for a união atual ou se
algum .R da pasta r/ não estiver no manifest.json.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
PY = RAIZ / "python"
R_APPS = RAIZ / "r"
APPS_PYTHON = ("Comercial", "Logistico", "Financeiro", "Fiscal", "Monitoramento", "Acessos")
REQUIREMENTS = PY / "requirements.txt"
MANIFEST = R_APPS / "manifest.json"


def requirements_unificado() -> str:
    """A união dos requirements.txt dos apps, na ordem em que aparecem."""
    vistos: dict[str, str] = {}
    for app in APPS_PYTHON:
        for linha in (PY / app / "requirements.txt").read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#"):
                vistos.setdefault(linha.split("==")[0].strip().lower(), linha)
    cabecalho = (
        "# Gerado por publicar/preparar_posit.py: a união dos requirements.txt dos seis apps.\n"
        "# O Posit instala este para o python/app.py. Não edite à mão.\n"
    )
    return cabecalho + "\n".join(vistos.values()) + "\n"


def _manifest() -> None:
    rscript = shutil.which("Rscript") or "C:/Program Files/R/R-4.6.1/bin/Rscript.exe"
    # Sem a pré-checagem do renv: ela recusa pacote usado só para compilar (LinkingTo, como o cpp11).
    env = {**os.environ, "RENV_CONFIG_SNAPSHOT_VALIDATE": "FALSE"}
    subprocess.run(
        [rscript, "-e", f'rsconnect::writeManifest(appDir = "{R_APPS.as_posix()}", appPrimaryDoc = "app.R")'],
        check=True,
        env=env,
    )


def preparar() -> None:
    REQUIREMENTS.write_text(requirements_unificado(), encoding="utf-8")
    print(f"{REQUIREMENTS.relative_to(RAIZ)} atualizado")
    _manifest()
    print(f"{MANIFEST.relative_to(RAIZ)} atualizado")


def conferir() -> None:
    problemas = []
    if REQUIREMENTS.read_text(encoding="utf-8") != requirements_unificado():
        problemas.append("python/requirements.txt não é a união atual dos requirements.txt dos apps")
    if not MANIFEST.exists():
        problemas.append("r/manifest.json não existe")
    else:
        no_manifest = set(json.loads(MANIFEST.read_text(encoding="utf-8"))["files"])
        faltando = sorted(
            p.relative_to(R_APPS).as_posix()
            for p in R_APPS.rglob("*.R")
            if p.relative_to(R_APPS).as_posix() not in no_manifest
        )
        if faltando:
            problemas.append(f"r/manifest.json sem {faltando}")
    if problemas:
        raise SystemExit("Rode python -m publicar.preparar_posit e faça commit:\n- " + "\n- ".join(problemas))
    print("dependências do Posit em dia")


if __name__ == "__main__":
    conferir() if "--conferir" in sys.argv else preparar()
