"""Dados dos apps em R (pasta r/): os mesmos .parquet fictícios dos apps em Python, copiados para a
pasta de cada app (o Shinylive só publica o que está dentro dela), mais o que só o R usa."""

import shutil

import polars as pl

from gerador import base as b

R = b.R_APPS


def _acessos() -> None:
    origem = b.PY / "Acessos" / "data" / "bd_acessos"
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
    print(f"  r/Acessos: {len(list(destino.glob('*.parquet')))} tabelas")


def _copiar_pasta(app_py: str, app_r: str, *pastas: str) -> None:
    """Copia os .parquet (e o que mais houver) das pastas de dados do app em Python para o app em R."""
    for pasta in pastas:
        origem = b.PY / app_py / "data" / pasta
        destino = R / app_r / "data" / pasta
        if destino.exists():
            shutil.rmtree(destino)
        shutil.copytree(origem, destino)
    print(f"  r/{app_r}: {', '.join(pastas)}")


def gerar() -> None:
    print("Apps em R")
    _acessos()
    _copiar_pasta("Logistico", "Logistico", "bd_senatran", "bd_pde", "bd_shiny_bruto", "bd_comodato")
    _copiar_pasta("Comercial", "Comercial", "bd_comercial")
    # Meta da fábrica: no original, só existe depois que alguém a envia pela tela. Vazia, como no começo.
    pl.DataFrame(
        schema={"REVENDA": pl.Utf8, "MES": pl.Utf8, "CODRED": pl.Utf8, "VALOR": pl.Float64, "VALOR_UMB": pl.Float64}
    ).write_parquet(R / "Comercial" / "data" / "bd_comercial" / "tb_meta_fabrica.parquet")


if __name__ == "__main__":
    gerar()
