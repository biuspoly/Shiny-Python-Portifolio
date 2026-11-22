"""No portfólio não há MySQL: toda conexão falha, e as telas seguem pelo caminho que o
sistema real usa com o banco fora do ar (arquivo em data/manual/ e fila em memória)."""


class SemBanco(ConnectionError):
    pass


def _sem_banco(*_args, **_kwargs):
    raise SemBanco("Portfólio sem MySQL")


obter_engine = obter_engine_manual = obter_engine_financeiro = _sem_banco
