import polars as pl

from core.dados import ler

MARCA = "\u2713"  # "U+2713" (check): a pessoa vê a página


def paginas(app: str) -> list[str]:
    return ler("paginas").filter(pl.col("app") == app).sort("ordem")["pagina"].to_list()


def matriz(app: str, permissoes: pl.DataFrame, areas: list[str], so_ativos: bool) -> pl.DataFrame:
    """Uma linha por pessoa, uma coluna por página do app (True = vê)."""
    u = ler("usuarios")
    if areas:
        u = u.filter(pl.col("area").is_in(areas))
    if so_ativos:
        u = u.filter(pl.col("ativo"))
    colunas = paginas(app)
    tem = permissoes.filter(pl.col("app") == app).with_columns(pl.lit(True).alias("ve"))
    largo = (
        tem.pivot(on="pagina", index="login", values="ve")
        if tem.height
        else pl.DataFrame({"login": []}, schema={"login": pl.String})
    )
    for c in colunas:
        if c not in largo.columns:
            largo = largo.with_columns(pl.lit(None, dtype=pl.Boolean).alias(c))
    return (
        u.select("login", "nome", "papel")
        .join(largo, on="login", how="left")
        .with_columns([pl.col(c).fill_null(False) for c in colunas])
        .select("login", "nome", "papel", *colunas)
        .sort("papel", "nome")
    )
