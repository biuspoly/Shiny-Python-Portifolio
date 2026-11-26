"""Configuração do portfólio: revendas fictícias, sem login nem permissão."""

import unicodedata

from core.config_arquivo import carregar_json

NOME_APP = "Acompanhamento Financeiro"
USUARIO_PORTFOLIO = "visitante"

# Nome da revenda -> CNPJ fictício (os mesmos do Logístico).
REVENDAS_CNPJ = {
    "Natal": "00000000000100",
    "Fortaleza": "00000000000280",
    "Teresina": "00000000000360",
    "São Luís": "00000000000440",
}

# Grupo da escolha de revenda (no original, o ?REVENDA= da URL) -> revendas dele.
REVENDAS_POR_GRUPO: dict[str, list[str]] = {"TODAS AS REVENDAS": list(REVENDAS_CNPJ)}


def chave_revenda(texto: str | None) -> str:
    sem_acento = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    return "".join(c for c in sem_acento if c.isalnum() or c == " ").upper().strip()


def chaves_das_revendas(nomes) -> set[str]:
    return {chave_revenda(n) for n in nomes or ()}


def casar_revendas(nomes_do_dado, alvos) -> list[str]:
    procurados = {chave_revenda(a) for a in alvos}
    return sorted(n for n in nomes_do_dado if n and chave_revenda(n) in procurados)


def pode(usuario: str | None, funcionalidade: str, revenda: str | None = None) -> bool:
    """No original, cada ação tem a sua lista de responsáveis; aqui o visitante pode testar todas."""
    return True


def quem_libera(*chaves: str) -> str:
    return ""


def sem_extrato_fabrica(revenda: str | None) -> bool:
    nomes = {chave_revenda(n) for n in carregar_json("parametros_financeiro").get("revendas_sem_extrato_fabrica") or ()}
    return bool(revenda) and chave_revenda(revenda) in nomes


def url_da_revenda(nome: str | None) -> str | None:
    return chave_revenda(nome) if nome else None


# --- Diário Financeiro -------------------------------------------------------------------------
# No original cada ação tem a sua lista de logins (config/responsaveis.json) e a tela de permissões
# edita essas listas. No portfólio o visitante pode tudo, e a lista da tela fica só na memória.
CHAVE_VER_PRE_AUDITORIA = "ver_pre_auditoria"
CHAVE_VER_GASTO_VEICULO = "ver_gasto_veiculo"
CHAVE_EDITAR_RESPONSAVEIS = "editar_responsaveis"

DIREITOS = [
    (
        "Diário Financeiro",
        [
            ("informar_dado_manual", "Lançar e editar Dados Manuais"),
            ("excluir_dado_manual", "Excluir Dados Manuais"),
            ("ver_entradas_de_hoje", "Ver as entradas de hoje no Contas a Pagar"),
        ],
    ),
    (
        "Contas a Pagar",
        [
            ("marcar_pagar", "Marcar títulos para pagar"),
            ("auditar", "Auditar títulos"),
            ("conselho", "Visto do conselho"),
            ("enviar_pagamentos", "Enviar os pagamentos do dia"),
            ("lancar_pagamento_manual", "Lançar pagamento manual"),
        ],
    ),
]
_RESPONSAVEIS: dict[str, list[str]] = {chave: [USUARIO_PORTFOLIO] for _s, itens in DIREITOS for chave, _f in itens}


def regra_do_segundo_erp(revenda: str | None) -> dict | None:
    return None


def membros_do_grupo(revenda: str | None) -> list[str]:
    return list(REVENDAS_POR_GRUPO.get((revenda or "").strip().upper()) or [])


def cnpjs_dos_carimbos(revenda: str | None) -> list[str]:
    if not revenda:
        return list(REVENDAS_CNPJ.values())
    alvo = chave_revenda(revenda)
    return [cnpj for nome, cnpj in REVENDAS_CNPJ.items() if chave_revenda(nome) == alvo]


def travado_por_leitura(usuario: str | None, funcionalidade: str) -> bool:
    return False


def no_acesso_total(usuario: str | None) -> bool:
    return True


def secoes_de_direitos() -> list[tuple[str, list[tuple[str, str, list[str]]]]]:
    return [
        (secao, [(chave, frase, list(_RESPONSAVEIS.get(chave, []))) for chave, frase in itens])
        for secao, itens in DIREITOS
    ]


def adicionar_responsavel(funcionalidade: str, usuario: str) -> str:
    login = str(usuario or "").strip().lower()
    if not login or " " in login:
        return "login_invalido"
    lista = _RESPONSAVEIS.setdefault(funcionalidade, [])
    if login in lista:
        return "ja_existia"
    lista.append(login)
    return "adicionado"


def remover_responsavel(funcionalidade: str, usuario: str) -> str:
    alvo = str(usuario or "").strip().lower()
    lista = _RESPONSAVEIS.get(funcionalidade, [])
    if alvo not in lista:
        return "nao_estava"
    lista.remove(alvo)
    return "removido"


def desconto_da_revenda(revenda: str | None):
    from decimal import Decimal

    regra = carregar_json("parametros_financeiro").get("desconto_padrao") or {}
    return Decimal(str(regra.get("ate", 0.10))), int(regra.get("conta", 0))


def descontos_por_fornecedor(revenda: str | None) -> dict:
    return {}


def desconto_ate_da_nota(desconto_ate, percentuais: dict, cnpj, valor_nota):
    return desconto_ate


def manual_com_vencimento_barrado(usuario, revenda, vencimento, hoje=None) -> str | None:
    return None


def exige_auditoria_para_pagar(usuario: str | None) -> bool:
    return False


def so_contas_a_pagar_no_diario(usuario: str | None, revenda: str | None = None) -> bool:
    return False


def empresas_da_url(revenda: str | None) -> list | None:
    if not revenda:
        return None
    from core import revendas as cadastro_revendas

    membros = REVENDAS_POR_GRUPO.get(revenda.strip().upper()) or [revenda]
    return [r for r in map(cadastro_revendas.por_nome, membros) if r is not None]
