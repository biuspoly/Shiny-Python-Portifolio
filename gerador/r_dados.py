"""Dados dos apps em R (pasta R/): os mesmos .parquet fictícios dos apps em Python, copiados para a
pasta de cada app (o Shinylive só publica o que está dentro dela), mais o que só o R usa."""

import shutil

import polars as pl

from gerador import base as b

R = b.RAIZ / "R"


def _acessos() -> None:
    origem = b.RAIZ / "Acessos" / "data" / "bd_acessos"
    destino = R / "Acessos" / "data" / "bd_acessos"
    destino.mkdir(parents=True, exist_ok=True)
    for arquivo in origem.glob("*.parquet"):
        shutil.copy(arquivo, destino / arquivo.name)
    # Quais revendas cada pessoa enxerga (tabela user_revenda do portal): a dela e, às vezes, mais uma.
    r = b.rng("r-acessos")
    usuarios = pl.read_parquet(origem / "usuario.parquet")
    revendas = pl.read_parquet(origem / "revenda.parquet")
    licenca_de = dict(zip(revendas["nomeExib"], revendas["licenca"], strict=True))
    todas = revendas["licenca"].to_list()
    linhas = []
    for login, revenda in usuarios.select("login", "Revenda").iter_rows():
        propria = licenca_de.get(revenda) or r.choice(todas)
        escolhidas = {propria} | ({r.choice(todas)} if r.random() < 0.35 else set())
        linhas += [{"licenca": lic, "login": login} for lic in sorted(escolhidas)]
    pl.DataFrame(linhas).write_parquet(destino / "user_revenda.parquet")
    print(f"  R/Acessos: {len(list(destino.glob('*.parquet')))} tabelas")


def gerar() -> None:
    print("Apps em R")
    _acessos()


if __name__ == "__main__":
    gerar()
