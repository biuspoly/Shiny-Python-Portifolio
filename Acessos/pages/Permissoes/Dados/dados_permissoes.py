import polars as pl

from core.db import consulta

_SQL_PAINEIS_ATIVOS = """
    SELECT DISTINCT
      d.id,
      d.nome      AS Painel,
      r.nomeExib  AS Revenda
    FROM dashboard d
    JOIN revenda   r ON r.licenca = d.licenca
    WHERE d.inativo = '0'
      AND d.nome IS NOT NULL
      AND r.nomeExib <> 'Lixo'
"""

_SQL_USUARIOS_ATIVOS = """
    SELECT
      login          AS Login,
      cargo          AS Cargo,
      funcao         AS Funcao,
      nomeCompleto,
      nomeGrupo,
      Revenda
    FROM usuario
    WHERE nomeGrupo <> 'Vazio'
"""

_SQL_ACESSOS_PAINEIS = """
    SELECT
      d.id,
      d.nome          AS Painel,
      u.login         AS Login,
      u.nomeCompleto  AS Usuario,
      r.nomeExib      AS Revenda,
      g.nomeGrupo     AS Grupo
    FROM usuario    u
    JOIN dash_group g ON g.nomeGrupo = u.nomeGrupo
    JOIN dashboard  d ON d.id        = g.id
    JOIN revenda    r ON r.licenca   = d.licenca
    WHERE d.inativo    = '0'
      AND d.nome       IS NOT NULL
      AND g.nomeGrupo <> 'Grupo Matriz'
      AND r.nomeExib  <> 'Lixo'
"""


def paineis_ativos() -> pl.DataFrame:
    return consulta(_SQL_PAINEIS_ATIVOS)


def usuarios_ativos() -> pl.DataFrame:
    return consulta(_SQL_USUARIOS_ATIVOS)


def acessos_paineis() -> pl.DataFrame:
    return consulta(_SQL_ACESSOS_PAINEIS)
