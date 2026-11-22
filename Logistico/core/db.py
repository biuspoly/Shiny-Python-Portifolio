"""No portfólio não há MySQL: toda conexão falha como banco fora do ar. As leituras ao vivo do
original já caem no .parquet quando isso acontece; as gravações foram trocadas pelas de
pages/Comodatos/Dados/banco_memoria.py."""


class SemBanco(ConnectionError):
    pass


def _sem_banco(*_args, **_kwargs):
    raise SemBanco("Portfólio sem MySQL")


def conferir_env(*_variaveis: str) -> None:
    return None


obter_engine = obter_engine_comodato = obter_engine_bruto = obter_engine_romaneios = obter_engine_pde = _sem_banco
