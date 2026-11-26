"""Monta e envia o ramo "posit", de onde o Posit Connect Cloud publica cada app.

O ramo é o repositório como está depois de gerar os dados (os da semana, que a main não guarda, e os
.parquet dos apps em R), mais o manifest.json de cada app em R, que o Connect Cloud exige e que o
rsconnect só gera com os pacotes instalados. É um commit sem pai, regravado a cada execução.

Os apps unificados (Acompanhamentos/ em Python e R/Acompanhamentos/ em R) recebem no ramo uma cópia de
cada app em apps/, porque o Posit publica só a pasta do arquivo principal.

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
APPS_PYTHON = ("Comercial", "Logistico", "Financeiro", "Fiscal", "Monitoramento", "Acessos")
RAMO = "posit"
# O que os apps em R gravam rodando local: não vai para o ramo (o .gitignore cobre o resto).
SOBRAS_R = ("R/Logistico/pages/Comodatos/Dados/*.pdf", "R/Logistico/pages/Comodatos/Dados/*.PDF")

# Os apps unificados (um por linguagem: Acompanhamentos/app.py e R/Acompanhamentos/app.R). O Posit publica
# a pasta do arquivo principal, então os apps vão copiados para apps/ dentro dela, só no ramo.
UNIFICADO_PY = RAIZ / "Acompanhamentos"
UNIFICADO_R = RAIZ / "R" / "Acompanhamentos"
_SEM_COPIAR = shutil.ignore_patterns("__pycache__", "*.pyc", "manifest.json", ".Rhistory")


def _copiar_apps_unificados() -> list[str]:
    """Copia cada app (com os dados da semana) para apps/ do unificado. Devolve as pastas criadas."""
    copias = {
        **{UNIFICADO_PY / "apps" / app: RAIZ / app for app in APPS_PYTHON},
        UNIFICADO_PY / "apps" / "Vitrine": RAIZ / "Vitrine",  # nome, cor e resumo de cada app, e os prints
        **{UNIFICADO_R / "apps" / app: RAIZ / "R" / app for app in APPS_R},
        UNIFICADO_R / "apps" / "Vitrine" / "www" / "img": RAIZ / "Vitrine" / "www" / "img",
    }
    for pasta in (UNIFICADO_PY / "apps", UNIFICADO_R / "apps"):
        shutil.rmtree(pasta, ignore_errors=True)
    for destino, origem in copias.items():
        destino.parent.mkdir(parents=True, exist_ok=True)
        if origem.is_dir():
            shutil.copytree(origem, destino, ignore=_SEM_COPIAR)
        else:
            shutil.copy2(origem, destino)
    print("apps copiados para Acompanhamentos/apps e R/Acompanhamentos/apps")
    return [p.relative_to(RAIZ).as_posix() for p in (UNIFICADO_PY / "apps", UNIFICADO_R / "apps")]


def requirements_unificado() -> str:
    """A união dos requirements.txt dos apps, na ordem em que aparecem (o Posit instala este)."""
    vistos: dict[str, str] = {}
    for app in APPS_PYTHON:
        for linha in (RAIZ / app / "requirements.txt").read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#"):
                vistos.setdefault(linha.split("==")[0].strip().lower(), linha)
    cabecalho = (
        "# Gerado por publicar/ramo_posit.py: a união dos requirements.txt dos seis apps.\n"
        "# O Posit instala este para o app Acompanhamentos. Não edite à mão.\n"
    )
    return cabecalho + "\n".join(vistos.values()) + "\n"


def _git(*args: str, env: dict | None = None) -> str:
    feito = subprocess.run(["git", *args], cwd=RAIZ, check=True, capture_output=True, text=True, env=env)
    return feito.stdout.strip()


def _manifestos() -> None:
    rscript = shutil.which("Rscript") or "C:/Program Files/R/R-4.6.1/bin/Rscript.exe"
    # Sem a pré-checagem do renv: ela recusa pacote usado só para compilar (LinkingTo, como o cpp11), que o
    # workflow não instala por usar binários; o Posit resolve essas dependências ao instalar.
    env = {**os.environ, "RENV_CONFIG_SNAPSHOT_VALIDATE": "FALSE"}
    for app in (*APPS_R, "Acompanhamentos"):
        pasta = (RAIZ / "R" / app).as_posix()
        print(f"manifest.json de R/{app}")
        subprocess.run(
            [rscript, "-e", f'rsconnect::writeManifest(appDir = "{pasta}", appPrimaryDoc = "app.R")'],
            check=True,
            env=env,
        )


def montar(enviar: bool) -> None:
    for padrao in SOBRAS_R:
        for arquivo in RAIZ.glob(padrao):
            arquivo.unlink()
    faltando = [f"R/{app}/data" for app in APPS_R if not (RAIZ / "R" / app / "data").exists()]
    if faltando:
        raise SystemExit(f"faltam {faltando}: rode antes python -m gerador.gerar_tudo")
    (UNIFICADO_PY / "requirements.txt").write_text(requirements_unificado(), encoding="utf-8")
    copias = _copiar_apps_unificados()
    # Índice próprio: o da cópia de trabalho fica como estava.
    indice = RAIZ / ".git" / "index_posit"
    env = {**os.environ, "GIT_INDEX_FILE": str(indice)}
    env.setdefault("GIT_AUTHOR_NAME", "github-actions[bot]")
    env.setdefault("GIT_AUTHOR_EMAIL", "41898282+github-actions[bot]@users.noreply.github.com")
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
    try:
        _manifestos()
        _git("add", "-A", env=env)
        ignorados = [f"R/{app}/{nome}" for app in APPS_R for nome in ("data", "manifest.json")]
        ignorados += ["R/Acompanhamentos/manifest.json", *copias]
        _git("add", "-f", *ignorados, env=env)
        arvore = _git("write-tree", env=env)
        origem = _git("rev-parse", "--short", "HEAD")
        commit = _git("commit-tree", arvore, "-m", f"Apps para o Posit Connect Cloud (main {origem})", env=env)
    finally:
        indice.unlink(missing_ok=True)
        # As cópias só existem para o ramo: a cópia de trabalho volta a ter um lugar só para cada app.
        for pasta in copias:
            shutil.rmtree(RAIZ / pasta, ignore_errors=True)
    print(f"ramo {RAMO}: commit {commit[:8]} a partir da main {origem}")
    if enviar:
        _git("push", "--force", "origin", f"{commit}:refs/heads/{RAMO}")
        print(f"enviado para origin/{RAMO}")


if __name__ == "__main__":
    montar(enviar="--sem-enviar" not in sys.argv)
