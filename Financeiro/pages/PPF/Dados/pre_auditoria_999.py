from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import NamedTuple

import polars as pl

from core.config_arquivo import carregar_json

from . import pre_auditoria

CONFIG = "pre_auditoria_999"
ARQUIVO_DOS_APONTAMENTOS = "pre_auditoria_999"
ARQUIVO_DOS_CONFERIDOS = "pre_auditoria_999_conferidos"

REGRAS = {
    "numero_diferente": ("Nota", "erro", "O comprovante é de outra nota: o número não é o do lançamento"),
    "nota_de_outra_empresa": ("Nota", "erro", "A nota do comprovante foi emitida para outra empresa"),
    "nota_cancelada": ("Nota", "erro", "A nota do comprovante está cancelada no governo"),
    "nota_nao_encontrada": (
        "Nota",
        "atenção",
        "A chave do comprovante não está nas notas que o governo mandou para a empresa",
    ),
    "nota_depois_do_pagamento": ("Nota", "atenção", "A nota foi emitida depois do dia do caixa"),
    "nota_antiga": ("Nota", "atenção", "A nota foi emitida muito antes do dia do caixa"),
    "valor_diferente_da_nota": ("Valor", "erro", "O valor do lançamento não é o da nota nem o de uma parcela dela"),
    "valor_fora_do_comprovante": ("Valor", "atenção", "O valor do lançamento não aparece no comprovante"),
    "chave_com_digito_errado": ("Arquivo", "atenção", "A chave de acesso do comprovante tem o dígito errado"),
    "nota_paga_duas_vezes": ("Repetição", "erro", "A mesma nota, com o mesmo valor, está em outro lançamento do caixa"),
    "nota_em_outro_lancamento": ("Repetição", "atenção", "A mesma nota está em outro lançamento do caixa"),
    "anexo_repetido": ("Repetição", "atenção", "O mesmo arquivo está em outro lançamento do caixa"),
}

ESQUEMA_DOS_APONTAMENTOS = {
    "CNPJ_REV": pl.Utf8,
    "revenda": pl.Utf8,
    "data": pl.Date,
    "descricao": pl.Utf8,
    "documento": pl.Utf8,
    "valor": pl.Float64,
    "regra": pl.Utf8,
    "grupo": pl.Utf8,
    "gravidade": pl.Utf8,
    "apontamento": pl.Utf8,
    "detalhe": pl.Utf8,
    "gerado_em": pl.Datetime,
}
ESQUEMA_DOS_CONFERIDOS = {
    "CNPJ_REV": pl.Utf8,
    "revenda": pl.Utf8,
    "data": pl.Date,
    "descricao": pl.Utf8,
    "documento": pl.Utf8,
    "valor": pl.Float64,
    "arquivos": pl.Utf8,
    "conferido": pl.Utf8,
    "gerado_em": pl.Datetime,
}

MODELOS_COM_CHAVE_DE_44 = {"55", "57", "65", "67"}
MODELOS_DE_CADA_SIGLA = {
    "NFE": {"55"},
    "CTE": {"57", "67"},
    "NFC": {"65"},
    "CF": {"65"},
    "CFE": {"65"},
    "NFS": {"nfse"},
}
CHAVE_DE_NFSE_NO_TEXTO = re.compile(r"(?<!\d)((?:\d[ .]?){49}\d)(?!\d)")
DINHEIRO_NO_TEXTO = re.compile(r"\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2}|\d+\.\d{2}(?!\d)")


class PreAuditoria999(NamedTuple):
    gerado_em: datetime | None
    apontamentos: list[dict]
    arquivos: tuple[str, ...]
    conferido: str


def configuracao() -> dict:
    do_arquivo = carregar_json(CONFIG) or {}
    janela = do_arquivo.get("janela_dias") or {}
    return {
        "dias_na_tela": int(janela.get("tela") or 10),
        "dias_na_madrugada": int(janela.get("madrugada") or 45),
        "tolerancia_valor": float(do_arquivo.get("tolerancia_valor") or 0.05),
        "dias_antes": int(do_arquivo.get("dias_da_nota_antes_do_caixa") or 90),
        "dias_depois": int(do_arquivo.get("dias_da_nota_depois_do_caixa") or 1),
        "modelos_sem_xml": {str(modelo) for modelo in do_arquivo.get("modelos_sem_xml") or []},
        "tipos_de_nota": {str(tipo).upper() for tipo in do_arquivo.get("tipos_de_nota_no_lancamento") or []},
        "dias_para_chegar_ao_fiscal": int(do_arquivo.get("dias_para_a_nota_chegar_ao_fiscal") or 5),
        "maximo_de_leituras_novas_na_tela": int(do_arquivo.get("maximo_de_leituras_novas_na_tela") or 20),
        "maximo_de_leituras_novas_na_madrugada": int(do_arquivo.get("maximo_de_leituras_novas_na_madrugada", 400) or 0),
        "hoje": date.today(),
    }


def chave_de_44_valida(chave: str) -> bool:
    if len(chave) != 44 or not chave.isdigit():
        return False
    soma_ponderada = sum(int(digito) * peso for digito, peso in zip(reversed(chave[:43]), [2, 3, 4, 5, 6, 7, 8, 9] * 6))
    digito_calculado = 11 - soma_ponderada % 11
    digito_esperado = 0 if digito_calculado >= 10 else digito_calculado
    return (
        digito_esperado == int(chave[43])
        and chave[:2] in pre_auditoria.CODIGOS_DE_UF
        and "01" <= chave[4:6] <= "12"
        and chave[20:22] in MODELOS_COM_CHAVE_DE_44
        and pre_auditoria.cnpj_valido(chave[6:20])
    )


def chaves_de_44_do_texto(texto: str) -> list[str]:
    chaves = []
    for trecho in pre_auditoria.CHAVE_NO_TEXTO.finditer(texto or ""):
        chave = re.sub(r"\D", "", trecho.group(1))
        if chave_de_44_valida(chave) and chave not in chaves:
            chaves.append(chave)
    return chaves


def chaves_de_nfse_do_texto(texto: str, chaves_de_nfse_conhecidas: set[str]) -> list[str]:
    chaves = []
    for trecho in CHAVE_DE_NFSE_NO_TEXTO.finditer(texto or ""):
        chave = re.sub(r"\D", "", trecho.group(1))
        if chave in chaves_de_nfse_conhecidas and chave not in chaves:
            chaves.append(chave)
    return chaves


def valores_do_texto(texto: str) -> set[float]:
    valores = set()
    for achado in DINHEIRO_NO_TEXTO.findall(texto or ""):
        numero = achado.replace(".", "").replace(",", ".") if "," in achado else achado
        try:
            valores.add(round(float(numero), 2))
        except ValueError:
            continue
    return valores


def leitura_do_comprovante(caminho: str, texto: str, como: str, chaves_de_nfse_conhecidas: set[str]) -> dict:
    texto_confiavel = como == "texto"
    return {
        "caminho": caminho,
        "texto_confiavel": texto_confiavel,
        "lido": como in ("texto", "ocr"),
        "chaves": chaves_de_44_do_texto(texto) + chaves_de_nfse_do_texto(texto, chaves_de_nfse_conhecidas),
        "chaves_erradas": pre_auditoria.chaves_com_o_digito_errado(texto) if texto_confiavel else [],
        "valores": valores_do_texto(texto) if texto_confiavel else set(),
    }


def documento_do_lancamento(descricao: str, documento: str, tipos_de_nota: set[str]) -> tuple[str, str] | None:
    texto = str(descricao or "")
    if texto.startswith("For:"):
        depois_do_rotulo = texto[5:] if texto[4:5] == " " else texto[4:]
        sigla = depois_do_rotulo[8:11].strip().upper()
        partes = depois_do_rotulo[11:].split()
        numero = re.sub(r"\D", "", partes[0]).lstrip("0") if partes else ""
        if sigla in tipos_de_nota and numero:
            return sigla, numero
        return None
    no_documento = re.match(r"\s*([A-Za-z]{2,3})\s*0*(\d+)\s*$", str(documento or ""))
    if no_documento and no_documento.group(1).upper() in tipos_de_nota:
        return no_documento.group(1).upper(), no_documento.group(2)
    return None


def nota_do_lancamento(descricao: str, documento: str, tipos_de_nota: set[str]) -> str | None:
    achado = documento_do_lancamento(descricao, documento, tipos_de_nota)
    return achado[1] if achado else None


def numero_da_chave(chave: str) -> str:
    numero = chave[25:34] if len(chave) == 44 else chave[23:36]
    return numero.lstrip("0") or "0"


def mesmo_numero(do_lancamento: str, da_chave: str) -> bool:
    return do_lancamento == da_chave or da_chave.endswith(do_lancamento) or do_lancamento.endswith(da_chave)


def modelo_da_chave(chave: str) -> str:
    return chave[20:22] if len(chave) == 44 else "nfse"


def chaves_da_nota_da_linha(lancamento: dict, chaves: list[str], tipos_de_nota: set[str]) -> list[str]:
    numero_do_lancamento = nota_do_lancamento(lancamento["descricao"], lancamento["documento"], tipos_de_nota)
    if not numero_do_lancamento:
        return chaves
    da_nota = [chave for chave in chaves if mesmo_numero(numero_do_lancamento, numero_da_chave(chave))]
    return da_nota or chaves


def apontamento(regra: str, detalhe: str = "") -> dict:
    grupo, gravidade, texto = REGRAS[regra]
    return {"regra": regra, "grupo": grupo, "gravidade": gravidade, "descricao": texto, "detalhe": detalhe}


def reais(valor) -> str:
    return pre_auditoria.reais(valor)


def regras_do_lancamento(
    lancamento: dict,
    leituras: list[dict],
    notas_por_chave: dict[str, dict],
    parcelas_por_chave: dict[str, list[float]],
    empresas_da_revenda: set[str],
    opcoes: dict,
) -> tuple[list[dict], str]:
    apontamentos = []
    valor = round(float(lancamento["valor"] or 0), 2)
    dia_do_caixa = lancamento["data"]
    tolerancia = opcoes["tolerancia_valor"]
    chaves = []
    for leitura in leituras:
        chaves += [chave for chave in leitura["chaves"] if chave not in chaves]
    if chaves:
        nota_da_linha = documento_do_lancamento(
            lancamento["descricao"], lancamento["documento"], opcoes["tipos_de_nota"]
        )
        if nota_da_linha:
            sigla, numero_do_lancamento = nota_da_linha
            modelos = MODELOS_DE_CADA_SIGLA.get(sigla)
            numeros_das_chaves = [
                numero_da_chave(chave) for chave in chaves if modelos is None or modelo_da_chave(chave) in modelos
            ]
            if numeros_das_chaves and not any(
                mesmo_numero(numero_do_lancamento, numero) for numero in numeros_das_chaves
            ):
                apontamentos.append(
                    apontamento(
                        "numero_diferente",
                        f"O lançamento é da nota {numero_do_lancamento}; o comprovante é da nota "
                        f"{', '.join(sorted(set(numeros_das_chaves)))}.",
                    )
                )
        chaves = chaves_da_nota_da_linha(lancamento, chaves, opcoes["tipos_de_nota"])
        de_fora = [chave for chave in chaves if len(chave) != 44 or chave[6:20] not in empresas_da_revenda]
        referencia = min(opcoes["hoje"], opcoes.get("fiscal_em_dia_ate") or opcoes["hoje"])
        recente = (
            not isinstance(dia_do_caixa, date)
            or dia_do_caixa + timedelta(days=opcoes["dias_para_chegar_ao_fiscal"]) >= referencia
        )
        notas_achadas = []
        ainda_vai_chegar = False
        for chave in de_fora:
            nota = notas_por_chave.get(chave)
            if nota is None:
                if modelo_da_chave(chave) in opcoes["modelos_sem_xml"]:
                    continue
                if recente:
                    ainda_vai_chegar = True
                    continue
                apontamentos.append(apontamento("nota_nao_encontrada", f"Chave {chave}."))
                continue
            notas_achadas.append((chave, nota))
            if nota["empresa"] and nota["empresa"] not in empresas_da_revenda:
                apontamentos.append(
                    apontamento(
                        "nota_de_outra_empresa",
                        f"Destinatária {pre_auditoria.cnpj_formatado(nota['empresa'])}, nota {numero_da_chave(chave)}.",
                    )
                )
            if nota.get("cancelada"):
                apontamentos.append(apontamento("nota_cancelada", f"Nota {numero_da_chave(chave)}, chave {chave}."))
            emissao = nota.get("emissao")
            if isinstance(emissao, date) and isinstance(dia_do_caixa, date):
                if emissao > dia_do_caixa + timedelta(days=opcoes["dias_depois"]):
                    apontamentos.append(
                        apontamento(
                            "nota_depois_do_pagamento",
                            f"Emitida em {emissao:%d/%m/%Y}; o caixa é de {dia_do_caixa:%d/%m/%Y}.",
                        )
                    )
                elif emissao < dia_do_caixa - timedelta(days=opcoes["dias_antes"]):
                    apontamentos.append(
                        apontamento(
                            "nota_antiga", f"Emitida em {emissao:%d/%m/%Y}; o caixa é de {dia_do_caixa:%d/%m/%Y}."
                        )
                    )
        if notas_achadas:
            valores_possiveis = []
            for chave, nota in notas_achadas:
                valores_possiveis.append(round(float(nota.get("valor") or 0), 2))
                valores_possiveis += [round(float(parcela), 2) for parcela in parcelas_por_chave.get(chave) or []]
            if not any(abs(valor - possivel) <= tolerancia for possivel in valores_possiveis):
                parcelas = sorted({possivel for possivel in valores_possiveis[1:]})
                apontamentos.append(
                    apontamento(
                        "valor_diferente_da_nota",
                        f"Lançamento {reais(valor)}; nota {reais(valores_possiveis[0])}"
                        + (f"; parcelas {', '.join(reais(parcela) for parcela in parcelas)}" if parcelas else "")
                        + ".",
                    )
                )
            return apontamentos, "a nota pela chave do comprovante, no XML do Fiscal (número, empresa, valor e data)"
        if ainda_vai_chegar:
            return apontamentos, (
                "o número da nota pela chave do comprovante; a nota ainda não chegou ao Fiscal (ele "
                "ainda não tem as notas da empresa de alguns dias depois do caixa), e a conferência "
                "da madrugada a procura de novo"
            )
        if not de_fora:
            return apontamentos, "o número da nota pela chave do comprovante (nota emitida pela própria empresa)"
        return apontamentos, "o número da nota pela chave do comprovante"
    confiaveis = [leitura for leitura in leituras if leitura["texto_confiavel"]]
    if confiaveis:
        valores_do_comprovante = set()
        for leitura in confiaveis:
            valores_do_comprovante |= leitura["valores"]
        if not any(abs(valor - achado) <= tolerancia for achado in valores_do_comprovante):
            apontamentos.append(apontamento("valor_fora_do_comprovante", f"Lançamento {reais(valor)}."))
        chaves_erradas = []
        for leitura in confiaveis:
            chaves_erradas += [chave for chave in leitura["chaves_erradas"] if chave not in chaves_erradas]
        if chaves_erradas:
            apontamentos.append(apontamento("chave_com_digito_errado", ", ".join(chaves_erradas)))
        return apontamentos, "o valor no texto do comprovante"
    return apontamentos, (
        "só a repetição: o comprovante é imagem, sem a chave de uma nota que o app leia com "
        "segurança (o recibo à mão, por exemplo)"
    )


def descrever_lancamento(lancamento: dict) -> str:
    return (
        f"{lancamento['data']:%d/%m/%Y} {' '.join(str(lancamento['descricao'] or '').split())} | "
        f"{' '.join(str(lancamento['documento'] or '').split())} | {reais(lancamento['valor'])}"
    )


def anexo_repetido(lancamento: dict, outro: dict) -> bool:
    mesmo_valor = abs(float(lancamento["valor"] or 0) - float(outro["valor"] or 0)) < 0.01
    caminhos_do_outro: dict[str, set[str]] = {}
    for assinatura, caminho in zip(outro.get("assinaturas") or [], outro.get("anexos") or []):
        caminhos_do_outro.setdefault(assinatura, set()).add(caminho)
    for assinatura, caminho in zip(lancamento.get("assinaturas") or [], lancamento.get("anexos") or []):
        com_o_mesmo_conteudo = caminhos_do_outro.get(assinatura)
        if com_o_mesmo_conteudo and (mesmo_valor or com_o_mesmo_conteudo - {caminho}):
            return True
    return False


def regras_de_repeticao(lancamentos: list[dict]) -> dict[int, list[dict]]:
    apontamentos_por_posicao: dict[int, list[dict]] = {}
    for posicao, lancamento in enumerate(lancamentos):
        for outra_posicao, outro in enumerate(lancamentos):
            if outra_posicao == posicao:
                continue
            chaves_em_comum = set(lancamento.get("chaves") or []) & set(outro.get("chaves") or [])
            if chaves_em_comum:
                mesmo_valor = abs(float(lancamento["valor"] or 0) - float(outro["valor"] or 0)) < 0.01
                regra = "nota_paga_duas_vezes" if mesmo_valor else "nota_em_outro_lancamento"
                apontamentos_por_posicao.setdefault(posicao, []).append(
                    apontamento(regra, f"Também em {descrever_lancamento(outro)}.")
                )
                continue
            if anexo_repetido(lancamento, outro):
                apontamentos_por_posicao.setdefault(posicao, []).append(
                    apontamento("anexo_repetido", f"Também em {descrever_lancamento(outro)}.")
                )
    return apontamentos_por_posicao


_ORDEM_DA_GRAVIDADE = {"erro": 0, "atenção": 1}


def montar_pre_auditorias(conferidos: pl.DataFrame, apontamentos: pl.DataFrame, chave_da_linha) -> dict:
    linhas: dict = {}
    if not conferidos.is_empty() and set(ESQUEMA_DOS_CONFERIDOS) - {"CNPJ_REV"} <= set(conferidos.columns):
        for conferido in conferidos.iter_rows(named=True):
            chave = chave_da_linha(
                conferido["revenda"], conferido["data"], conferido["descricao"], conferido["documento"]
            )
            arquivos = tuple(caminho for caminho in str(conferido["arquivos"] or "").split("\n") if caminho)
            linhas[chave] = PreAuditoria999(conferido["gerado_em"], [], arquivos, conferido["conferido"] or "")
    if not apontamentos.is_empty() and {"revenda", "data", "descricao", "documento", "gravidade"} <= set(
        apontamentos.columns
    ):
        ordenados = apontamentos.with_columns(
            pl.col("gravidade").replace_strict(_ORDEM_DA_GRAVIDADE, default=9, return_dtype=pl.Int8).alias("_ordem")
        ).sort("_ordem", maintain_order=True)
        for linha in ordenados.iter_rows(named=True):
            chave = chave_da_linha(linha["revenda"], linha["data"], linha["descricao"], linha["documento"])
            if chave not in linhas:
                continue
            linhas[chave].apontamentos.append(
                {
                    "grupo": linha["grupo"] or "",
                    "gravidade": linha["gravidade"] or "",
                    "descricao": linha["apontamento"] or "",
                    "detalhe": linha["detalhe"] or "",
                }
            )
    return linhas


def ainda_vale(pre_auditoria_da_linha: PreAuditoria999 | None, arquivos_de_agora) -> bool:
    if pre_auditoria_da_linha is None:
        return False
    conferidos = set(pre_auditoria_da_linha.arquivos)
    return bool(conferidos) and all(str(caminho) in conferidos for caminho in arquivos_de_agora)


def estado(pre_auditoria_da_linha: PreAuditoria999) -> str:
    gravidades = {apontamento_da_linha["gravidade"] for apontamento_da_linha in pre_auditoria_da_linha.apontamentos}
    if "erro" in gravidades:
        return "erro"
    if gravidades:
        return "atencao"
    return "ok"
