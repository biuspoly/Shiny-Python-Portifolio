"""Configuração do portfólio: revendas fictícias, sem login nem permissão."""

NOME_APP = "Acompanhamento Logístico"
NOME_PORTFOLIO = "Portfólio Marlon Amaral"

# Nome da revenda (maiúsculo, como no cache) -> CNPJ fictício.
REVENDAS_CNPJ = {
    "NATAL": "00000000000100",
    "FORTALEZA": "00000000000280",
    "TERESINA": "00000000000360",
    "SÃO LUÍS": "00000000000440",
}

USUARIO_PORTFOLIO = "visitante"


def pode(usuario: str | None, funcionalidade: str) -> bool:
    """No original, cada ação tem a sua lista de responsáveis; aqui o visitante pode testar todas."""
    return True


# --- Comodatos ----------------------------------------------------------------------------------
# No original, cada direito tem a sua lista de logins (config/responsaveis.json), editada pela tela
# "Responsáveis". No portfólio o visitante pode tudo, e a lista da tela fica só na memória.
CHAVE_SUPREMO = "supremo"

DIREITOS = [
    ("Acesso total", [(CHAVE_SUPREMO, "Passa em todas as regras abaixo, sem estar na lista de cada uma")]),
    (
        "Comodatos",
        [
            ("solicitacao_comodato", 'Solicitar comodato (botões "Enviar" e "Retirar")'),
            ("cancelar_pre_pedido", "Cancelar pré-pedido já enviado ao ERP"),
            ("solicitacao_sem_bloqueio", "Pedir comodato para cliente bloqueado"),
            ("envio_sem_bloqueio", "Enviar os documentos do CEV mesmo com o prazo vencido"),
            ("recolha_comodato", 'Pedir a recolha e baixar o distrato (coluna "Recolha")'),
            ("reenvio_email", 'Reenviar o e-mail de assinatura (coluna "Reenviar Email")'),
            ("excecao_comodato", 'Liberar cliente de enviar documento ("Adicionar exceção")'),
        ],
    ),
    ("Frotas", [("transferencia_manual", 'Transferir veículo de unidade ("Transferência manual")')]),
]
_RESPONSAVEIS: dict[str, list[str]] = {chave: [USUARIO_PORTFOLIO] for _s, itens in DIREITOS for chave, _f in itens}


def secoes_de_direitos() -> list[tuple[str, list[tuple[str, str, list[str]]]]]:
    return [(secao, [(c, f, list(_RESPONSAVEIS.get(c, []))) for c, f in itens]) for secao, itens in DIREITOS]


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
