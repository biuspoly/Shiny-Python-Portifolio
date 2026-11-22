from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from core.db import consulta

_SQL_KPIS = """
    SELECT
      (SELECT COUNT(DISTINCT login) FROM usuario WHERE nomeGrupo <> 'Vazio')
        AS total_usuarios,
      (SELECT COUNT(*) FROM dashboard WHERE inativo = '0' AND nome IS NOT NULL)
        AS total_paineis,
      (SELECT COUNT(*) FROM logacesso
       WHERE STR_TO_DATE(dataAcesso,'%d/%m/%Y %H:%i:%s') >= NOW() - INTERVAL 7 DAY)
        AS acessos_7_dias,
      (SELECT COUNT(DISTINCT login) FROM logacesso
       WHERE STR_TO_DATE(dataAcesso,'%d/%m/%Y %H:%i:%s') >= NOW() - INTERVAL 7 DAY)
        AS usuarios_ativos_7_dias
"""

_SQL_TENDENCIA = """
    SELECT
      DATE(STR_TO_DATE(dataAcesso,'%d/%m/%Y %H:%i:%s'))  AS data,
      COUNT(*)                                             AS total_acessos,
      COUNT(DISTINCT login)                               AS usuarios_distintos
    FROM logacesso
    WHERE STR_TO_DATE(dataAcesso,'%d/%m/%Y %H:%i:%s') >= NOW() - INTERVAL 30 DAY
    GROUP BY DATE(STR_TO_DATE(dataAcesso,'%d/%m/%Y %H:%i:%s'))
    ORDER BY data
"""

_SQL_ULTIMO_ACESSO = """
    SELECT
      u.login,
      u.nomeCompleto                                                  AS nome,
      u.cargo,
      u.Revenda                                                       AS revenda,
      MAX(STR_TO_DATE(l.dataAcesso,'%d/%m/%Y %H:%i:%s'))             AS ultimo_acesso,
      SUM(
        CASE
          WHEN STR_TO_DATE(l.dataAcesso,'%d/%m/%Y %H:%i:%s') >= NOW() - INTERVAL 30 DAY
          THEN 1 ELSE 0
        END
      )                                                               AS acessos_30d
    FROM usuario u
    LEFT JOIN logacesso l ON l.login = u.login
    WHERE u.nomeGrupo <> 'Vazio'
    GROUP BY u.login, u.nomeCompleto, u.cargo, u.Revenda
    ORDER BY ultimo_acesso DESC
"""


def kpis_acesso() -> dict:
    df = consulta(_SQL_KPIS)
    return df.row(0, named=True)


def tendencia_acessos() -> pl.DataFrame:
    return consulta(_SQL_TENDENCIA)


def ultimo_acesso_usuario() -> pl.DataFrame:
    df = consulta(_SQL_ULTIMO_ACESSO)

    agora = datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None)
    return df.with_columns((pl.lit(agora) - pl.col("ultimo_acesso")).dt.total_days().alias("dias_inativo"))
