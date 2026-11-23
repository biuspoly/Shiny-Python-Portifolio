"""Monta e envia o ramo "posit", de onde o Posit Connect Cloud publica cada app.

O ramo é o repositório como está depois de gerar os dados (os da semana, que a main não guarda, e os
.parquet dos apps em R), mais o manifest.json de cada app em R, que o Connect Cloud exige e que o
rsconnect só gera com os pacotes instalados. É um commit sem pai, regravado a cada execução.

Uso (no workflow, depois de gerar os dados): python -m publicar.ramo_posit
Sem enviar (só monta e mostra o commit): python -m publicar.ramo_posit --sem-enviar
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
APPS_R = ("Acessos", "Comercial", "Logistico")
RAMO = "posit"
# O que os apps em R gravam rodando local: não vai para o ramo (o .gitignore cobre o resto).
SOBRAS_R = ("R/Logistico/pages/Comodatos/Dados/*.pdf", "R/Logistico/pages/Comodatos/Dados/*.PDF")


def _git(*args: str, env: dict | None = None) -> str:
    feito = subprocess.run(["git", *args], cwd=RAIZ, check=True, capture_output=True, text=True, env=env)
    return feito.stdout.strip()


def _manifestos() -> None:
    rscript = shutil.which("Rscript") or "C:/Program Files/R/R-4.6.1/bin/Rscript.exe"
    for app in APPS_R:
        pasta = (RAIZ / "R" / app).as_posix()
        print(f"manifest.json de R/{app}")
        subprocess.run(
            [rscript, "-e", f'rsconnect::writeManifest(appDir = "{pasta}", appPrimaryDoc = "app.R")'],
            check=True,
        )


def montar(enviar: bool) -> None:
    for padrao in SOBRAS_R:
        for arquivo in RAIZ.glob(padrao):
            arquivo.unlink()
    _manifestos()
    # Índice próprio: o da cópia de trabalho fica como estava.
    indice = RAIZ / ".git" / "index_posit"
    env = {**os.environ, "GIT_INDEX_FILE": str(indice)}
    env.setdefault("GIT_AUTHOR_NAME", "github-actions[bot]")
    env.setdefault("GIT_AUTHOR_EMAIL", "41898282+github-actions[bot]@users.noreply.github.com")
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
    try:
        _git("add", "-A", env=env)
        ignorados = [f"R/{app}/{nome}" for app in APPS_R for nome in ("data", "manifest.json")]
        faltando = [caminho for caminho in ignorados if not (RAIZ / caminho).exists()]
        if faltando:
            raise SystemExit(f"faltam {faltando}: rode antes python -m gerador.gerar_tudo")
        _git("add", "-f", *ignorados, env=env)
        arvore = _git("write-tree", env=env)
        origem = _git("rev-parse", "--short", "HEAD")
        commit = _git("commit-tree", arvore, "-m", f"Apps para o Posit Connect Cloud (main {origem})", env=env)
    finally:
        indice.unlink(missing_ok=True)
    print(f"ramo {RAMO}: commit {commit[:8]} a partir da main {origem}")
    if enviar:
        _git("push", "--force", "origin", f"{commit}:refs/heads/{RAMO}")
        print(f"enviado para origin/{RAMO}")


if __name__ == "__main__":
    montar(enviar="--sem-enviar" not in sys.argv)
