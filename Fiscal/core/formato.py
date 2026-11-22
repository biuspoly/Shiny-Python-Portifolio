from __future__ import annotations

import re
from datetime import date, datetime

import polars as pl

VERDE, AZUL, AMBAR, VERMELHO, CINZA = "verde", "azul", "ambar", "vermelho", "cinza"

SITUACAO = {
    "Autorizada": VERDE,
    "Autorizado": VERDE,
    "Normal": VERDE,
    "Cancelada": VERMELHO,
    "Cancelado": VERMELHO,
    "Denegada": CINZA,
}

MANIFESTACAO_NA_TELA = {
    "Confirmada": "Confirmada",
    "Só ciência": "Ciente",
    "Sem manifestação": "Sem manifestação",
    "Desconhecida": "Desconhecida",
    "Não realizada": "Não realizada",
    "Pré-confirmada": "Pré-confirmada",
    "Desacordo": "Desacordo",
}
MANIFESTACAO = {
    "Confirmada": VERDE,
    "Só ciência": AZUL,
    "Ciente": AZUL,
    "Sem manifestação": AMBAR,
    "Desconhecida": VERMELHO,
    "Não realizada": VERMELHO,
    "Pré-confirmada": AMBAR,
    "Desacordo": VERMELHO,
}

TIPOS_MANIFESTACAO = {
    "Sem manifestação": "A empresa ainda não respondeu. Até o fim do prazo, a nota pode ser confirmada, "
    "desconhecida ou dada como não realizada; depois, vale como confirmada.",
    "Só ciência": "Ciência da operação: a empresa viu que a nota existe. Libera o XML completo, mas não é "
    "resposta final.",
    "Pré-confirmada": "Confirmada no Fiscal, ainda não na Receita: a Confirmação vai quando alguém confirmar a "
    "importação na Escrituração. Até lá, dá para trocar a resposta.",
    "Confirmada": "Confirmação da operação: a mercadoria chegou e a nota está certa. Resposta final.",
    "Desconhecida": "Desconhecimento da operação: a empresa não reconhece a compra. Resposta final.",
    "Não realizada": "Operação não realizada: a nota é real, mas a operação não aconteceu (devolvida, "
    "recusada). Resposta final, com justificativa.",
}
EXPLICA_OPERACAO = {
    "ciencia": TIPOS_MANIFESTACAO["Só ciência"],
    "confirmacao": TIPOS_MANIFESTACAO["Confirmada"],
    "desconhecimento": TIPOS_MANIFESTACAO["Desconhecida"],
    "nao_realizada": TIPOS_MANIFESTACAO["Não realizada"],
}

OPERACAO_VISUAL = {
    "ciencia": ("eye", "fis-op-ciencia", "Viu a nota: libera o XML completo. Não é resposta final."),
    "confirmacao": ("circle-check", "fis-op-confirmacao", "A mercadoria chegou e a nota está certa."),
    "desconhecimento": ("circle-xmark", "fis-op-desconhecimento", "A empresa não reconhece a compra."),
    "nao_realizada": ("ban", "fis-op-nao-realizada", "A nota existe, mas a operação não aconteceu."),
}
CLASSE_TIPO = {
    "Sem manifestação": "fis-tipo-sem",
    "Só ciência": "fis-tipo-ciente",
    "Confirmada": "fis-tipo-confirmada",
    "Desconhecida": "fis-tipo-desconhecida",
    "Não realizada": "fis-tipo-nao",
    "Pré-confirmada": "fis-tipo-sem",
}


def rotulo_tipo(tipo: str) -> str:
    return MANIFESTACAO_NA_TELA.get(tipo, tipo)


def prazo(valor) -> str | None:
    texto = str(valor or "")
    if texto == "Prazo encerrado":
        return CINZA
    if texto == "Manifestação em dia":
        return VERDE
    if texto == "Vence hoje":
        return VERMELHO
    try:
        dias = int(texto.split()[0])
    except (TypeError, ValueError, IndexError):
        return None
    return CINZA if dias < 0 else VERMELHO if dias <= 5 else AMBAR if dias <= 15 else None


def texto_prazo(manifestacao: pl.Expr, dias: pl.Expr) -> pl.Expr:
    return (
        pl.when(manifestacao.is_in(["Confirmada", "Desconhecida", "Não realizada"]))
        .then(pl.lit("Manifestação em dia"))
        .when(dias < 0)
        .then(pl.lit("Prazo encerrado"))
        .when(dias == 0)
        .then(pl.lit("Vence hoje"))
        .when(dias == 1)
        .then(pl.lit("1 dia restante"))
        .when(dias.is_not_null())
        .then(dias.cast(pl.Utf8) + pl.lit(" dias restantes"))
        .otherwise(pl.lit("-"))
    )


def estilos(tabela: pl.DataFrame, regras: dict, so_texto: tuple = ()) -> list[dict]:
    saida = []
    for coluna, regra in regras.items():
        if coluna not in tabela.columns:
            continue
        grupos: dict[str, list[int]] = {}
        for i, valor in enumerate(tabela[coluna].to_list()):
            cor = regra(valor) if callable(regra) else regra.get(valor)
            if cor:
                grupos.setdefault(cor, []).append(i)
        j = tabela.columns.index(coluna)
        classe = "fis-cor-{}" if coluna in so_texto else "fis-sit fis-sit-{}"
        saida += [
            {"location": "body", "rows": linhas, "cols": [j], "class": classe.format(cor)}
            for cor, linhas in grupos.items()
        ]
    return saida


def moeda(valor) -> str:
    if valor is None:
        return "-"
    texto = f"{float(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


def inteiro(valor) -> str:
    return f"{int(valor or 0):,}".replace(",", ".")


def data(valor) -> str:
    if isinstance(valor, datetime):
        return f"{valor:%d/%m/%Y %H:%M}"
    if isinstance(valor, date):
        return f"{valor:%d/%m/%Y}"
    return "-"


def cnpj(texto) -> str:
    numero = re.sub(r"\D", "", str(texto or ""))
    if 11 < len(numero) < 14:
        numero = numero.zfill(14)
    if len(numero) == 14:
        return f"{numero[:2]}.{numero[2:5]}.{numero[5:8]}/{numero[8:12]}-{numero[12:]}"
    if len(numero) == 11:
        return f"{numero[:3]}.{numero[3:6]}.{numero[6:9]}-{numero[9:]}"
    return numero or "-"


def coluna_moeda(nome: str) -> pl.Expr:
    return pl.col(nome).map_elements(moeda, return_dtype=pl.Utf8)


def coluna_data(nome: str, com_hora: bool = False) -> pl.Expr:
    return pl.col(nome).dt.strftime("%d/%m/%Y %H:%M" if com_hora else "%d/%m/%Y").fill_null("-")
