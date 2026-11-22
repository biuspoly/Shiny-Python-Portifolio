"""O que a tela Apuração usa da geração do SPED (o original monta o arquivo inteiro)."""

TIPO_DO_AJUSTE = {
    "0": "outros_debitos",
    "1": "estornos_de_credito",
    "2": "outros_creditos",
    "3": "estornos_de_debito",
    "4": "deducoes",
    "5": "debitos_especiais",
}
NOME_DO_TIPO_DE_AJUSTE = {
    "outros_debitos": "outros débitos",
    "estornos_de_credito": "estorno de créditos",
    "outros_creditos": "outros créditos",
    "estornos_de_debito": "estorno de débitos",
    "deducoes": "deduções",
    "debitos_especiais": "débitos especiais",
}


def documento(cgc) -> tuple[str, str]:
    """(CNPJ, CPF) do número do participante como o livro grava."""
    s = str(int(cgc or 0)).zfill(15)
    if s[9:13] == "0000":
        return "", s[:9] + s[13:]
    return s[1:], ""
