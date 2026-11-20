import polars as pl

from core.dados import ler


def usuarios_por_app() -> pl.DataFrame:
    p = ler("permissoes").join(ler("usuarios").filter(pl.col("ativo")).select("login"), on="login", how="semi")
    return p.group_by("app").agg(pl.col("login").n_unique().alias("usuarios")).sort("usuarios", descending=True)


def por_papel() -> pl.DataFrame:
    u = ler("usuarios")
    paginas = ler("permissoes").group_by("login").agg(pl.len().alias("paginas"))
    return (
        u.join(paginas, on="login", how="left")
        .group_by("papel")
        .agg(
            pl.len().alias("pessoas"),
            pl.col("ativo").sum().alias("ativas"),
            pl.col("paginas").mean().alias("media_paginas"),
        )
        .sort("pessoas", descending=True)
    )


def acesso_amplo(limite: int = 12) -> pl.DataFrame:
    """Quem vê mais páginas: o primeiro lugar para revisar acesso."""
    paginas = ler("permissoes").group_by("login").agg(pl.len().alias("paginas"), pl.col("app").n_unique().alias("apps"))
    return (
        ler("usuarios")
        .filter(pl.col("ativo"))
        .join(paginas, on="login")
        .filter(pl.col("paginas") >= limite)
        .sort("paginas", descending=True)
    )
