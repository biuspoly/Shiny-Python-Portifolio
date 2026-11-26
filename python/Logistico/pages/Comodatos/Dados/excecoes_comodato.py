from sqlalchemy import text

from core.config_arquivo import carregar_json
from core.config_arquivo import gravar_json as gravar_config

_NOME_CONFIG = "excecoes_comodato"
_CHAVE_LIVRES = "clientes_livres_por_revenda"

_PADRAO_CORTE = "20260324"

TIPO_CLIENTE = "clientes"
TIPO_VENDEDOR = "vendedores"
TIPOS = (TIPO_CLIENTE, TIPO_VENDEDOR)

TABELA_EXCECOES = "tb_comod_excecao_cli"

LISTA_EXCECAO = "excecao"
LISTA_ESTRANGEIRO = "estrangeiro"
LISTAS = {
    LISTA_EXCECAO: (_CHAVE_LIVRES, TABELA_EXCECOES),
    LISTA_ESTRANGEIRO: ("estrangeiros_por_revenda", "tb_comod_estrangeiro_cli"),
}

_SQL_CRIA_TABELA = """
    CREATE TABLE IF NOT EXISTS {tabela} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        REVENDA VARCHAR(50) NOT NULL,
        TIPO VARCHAR(12) NOT NULL,
        CODIGO VARCHAR(20) NOT NULL,
        USUARIO VARCHAR(60),
        DATA VARCHAR(8),
        HORA VARCHAR(8),
        UNIQUE KEY uq_excecao (REVENDA, TIPO, CODIGO)
    ) DEFAULT CHARSET=utf8mb4
"""


def clientes_livres_por_revenda() -> dict[str, dict[str, list[str]]]:
    return carregar_json(_NOME_CONFIG).get(_CHAVE_LIVRES, {})


def estrangeiros_por_revenda() -> dict[str, dict[str, list[str]]]:
    return carregar_json(_NOME_CONFIG).get(LISTAS[LISTA_ESTRANGEIRO][0], {})


def cnpj_especial() -> str:
    return carregar_json(_NOME_CONFIG).get("cnpj_especial", "00000000000990")


def corte_prazo_material() -> tuple[dict[str, str], str]:
    config = carregar_json(_NOME_CONFIG)
    return (
        config.get("corte_prazo_material_esgotado", {}),
        config.get("corte_prazo_material_padrao", _PADRAO_CORTE),
    )


def garantir_tabela(conexao, lista: str = LISTA_EXCECAO) -> None:
    conexao.execute(text(_SQL_CRIA_TABELA.format(tabela=LISTAS[lista][1])))


def registrar_excecao(revenda: str, tipo: str, codigo: str, usuario: str, lista: str = LISTA_EXCECAO) -> str:
    """Portfólio: sem o registro no banco; a exceção vale pelo JSON, que a tela lê."""
    if tipo not in TIPOS:
        raise ValueError(f"Tipo de exceção desconhecido: {tipo}")
    if lista not in LISTAS:
        raise ValueError(f"Lista de exceção desconhecida: {lista}")
    revenda, codigo = str(revenda or "").strip(), str(codigo or "").strip()
    if not revenda or not codigo:
        raise ValueError("Exceção precisa de revenda e código")
    _acrescentar_no_json(revenda, tipo, codigo, lista)
    return "adicionada"


def _acrescentar_no_json(revenda: str, tipo: str, codigo: str, lista: str = LISTA_EXCECAO) -> None:
    chave_json = LISTAS[lista][0]
    config = dict(carregar_json(_NOME_CONFIG))
    livres = {chave: dict(valor) for chave, valor in config.get(chave_json, {}).items()}
    da_revenda = livres.setdefault(revenda, {})
    lista = list(da_revenda.get(tipo, []))
    if codigo not in lista:
        lista.append(codigo)
    da_revenda[tipo] = lista
    da_revenda.setdefault(TIPO_VENDEDOR if tipo == TIPO_CLIENTE else TIPO_CLIENTE, [])
    config[chave_json] = livres
    gravar_json(config)


def gravar_json(config: dict) -> None:
    gravar_config(_NOME_CONFIG, config)


def excecoes_do_banco(lista: str = LISTA_EXCECAO) -> dict[str, dict[str, list[str]]]:
    return {}
