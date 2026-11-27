from __future__ import annotations


def opcoes(fixas: dict[str, str], valores) -> dict[str, str]:
    presentes = {str(valor) for valor in valores if valor not in (None, "")}
    saida = {valor: rotulo for valor, rotulo in fixas.items() if valor == "" or valor in presentes}
    saida.update({valor: valor for valor in sorted(presentes) if valor not in saida})
    return saida


def escolha_que_fica(escolhida, novas: dict[str, str]) -> str:
    return escolhida if escolhida in novas else ""
