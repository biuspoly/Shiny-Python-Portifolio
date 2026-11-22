"""No sistema real cada ação da tela vai para um log de auditoria (arquivo + MySQL), gravado
por uma thread. O navegador não abre thread: no portfólio o registro não é feito."""


def registrar(acao: str, **_kwargs) -> None:
    return None


def mudancas(assunto: str, antes, depois, contexto: dict | None = None) -> None:
    return None
