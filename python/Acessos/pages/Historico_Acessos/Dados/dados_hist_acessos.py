import polars as pl

from core.db import consulta

_SQL_ACESSO_DASH = """
    SELECT
      l.id,
      l.login,
      STR_TO_DATE(l.dataAcesso,'%d/%m/%Y %H:%i:%s') AS dataAcesso,
      d.nome      AS Painel,
      r.nomeExib  AS Revenda
    FROM logacesso  l
    JOIN usuario    u ON u.login   = l.login
    JOIN dashboard  d ON d.id      = l.iddash
    JOIN revenda    r ON r.licenca = d.licenca
    WHERE STR_TO_DATE(l.dataAcesso,'%d/%m/%Y %H:%i:%s') >= NOW() - INTERVAL 7 DAY
    ORDER BY l.id DESC
"""


def acesso_dash() -> pl.DataFrame:
    return consulta(_SQL_ACESSO_DASH)
