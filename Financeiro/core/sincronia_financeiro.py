"""O botão Atualizar e o retrato do dia vão para o worker (Celery/Redis) no sistema real.
No portfólio não há worker: os dados já vêm prontos, e nada é enfileirado."""


def disparar(revenda: str, tarefa: str = "coleta", usuario: str | None = None, perfil: str | None = None) -> str:
    return ""
