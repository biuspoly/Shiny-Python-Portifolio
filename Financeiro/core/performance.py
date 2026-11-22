"""Medição de tempo por OpenTelemetry: no portfólio o decorador não mede nada."""


def medir_tempo(pagina: str, limite_ms: int = 0):
    def decorador(func):
        return func

    return decorador
