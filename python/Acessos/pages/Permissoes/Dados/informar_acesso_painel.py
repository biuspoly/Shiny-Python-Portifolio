from core.db import executar


def adicionar_acesso_usuario(grupo_id: str, painel_id: int) -> None:
    executar(
        "INSERT IGNORE INTO dash_group (nomeGrupo, id) VALUES (:grupo_id, :painel_id)",
        {"grupo_id": grupo_id, "painel_id": painel_id},
    )


def excluir_acesso_usuario(grupo_id: str, painel_id: int) -> None:
    executar(
        "DELETE FROM dash_group WHERE nomeGrupo = :grupo_id AND id = :painel_id",
        {"grupo_id": grupo_id, "painel_id": painel_id},
    )
