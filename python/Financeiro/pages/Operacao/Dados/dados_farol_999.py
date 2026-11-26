from __future__ import annotations

import re
import threading
from datetime import date
from pathlib import Path

if __name__ == "__main__":
    import sys

    sys.path.insert(
        0,
        str(
            Path(globals()["__file__"]).resolve().parents[3]
            if "__file__" in globals()
            else next(
                (
                    pasta
                    for pasta in (Path.cwd(), Path.cwd() / "Acompanhamento Financeiro")
                    if (pasta / "core" / "config_arquivo.py").is_file()
                ),
                Path.cwd(),
            )
        ),
    )

import cachetools
import polars as pl

from core import gravacao, manual_arquivo, rede_documentos
from core.config import chave_revenda
from core.config_arquivo import carregar_json
from pages.PPF.Dados import dados_ppf, pre_auditoria_999

CONFIG = "farol_999"
ASSUNTO_DOS_ANEXOS = "anexos_999"
PASTA_DO_APP = Path(__file__).resolve().parents[3]

_pasta_do_caixa: cachetools.TTLCache = cachetools.TTLCache(maxsize=256, ttl=300)
_trava_do_cache = threading.Lock()


def configuracao() -> dict:
    do_arquivo = carregar_json(CONFIG) or {}
    restritas = do_arquivo.get("restritas") or {}
    return {
        "revendas_restritas": [str(nome) for nome in restritas.get("revendas") or []],
        "veem_as_restritas": [str(login).strip().lower() for login in restritas.get("veem") or []],
        "fora_quando_contem": [
            str(palavra) for palavra in do_arquivo.get("fora_quando_contem") or [] if str(palavra).strip()
        ],
        "descricoes_fora": [
            " ".join(str(descricao).split()).upper()
            for descricao in do_arquivo.get("descricoes_fora") or []
            if str(descricao).strip()
        ],
    }


def todas_as_revendas() -> list[str]:
    revendas_do_painel = list(carregar_json("parametros_financeiro").get("revendas_monitoradas_envio_extratos") or [])
    chaves_do_painel = {chave_revenda(nome) for nome in revendas_do_painel}
    return revendas_do_painel + [
        nome for nome in configuracao()["revendas_restritas"] if chave_revenda(nome) not in chaves_do_painel
    ]


def ve_as_restritas(usuario: str | None) -> bool:
    login = str(usuario or "").strip().lower()
    return bool(login) and login in configuracao()["veem_as_restritas"]


def revendas_do_farol(usuario: str | None) -> list[str]:
    if ve_as_restritas(usuario):
        return todas_as_revendas()
    chaves_restritas = {chave_revenda(nome) for nome in configuracao()["revendas_restritas"]}
    return [nome for nome in todas_as_revendas() if chave_revenda(nome) not in chaves_restritas]


def fica_de_fora(descricao: str, documento: str, palavras_fora: list[str], descricoes_fora: list[str]) -> bool:
    texto = f"{descricao or ''} {documento or ''}".upper()
    if any(re.search(rf"\b{re.escape(palavra.upper())}\b", texto) for palavra in palavras_fora):
        return True
    return " ".join(str(descricao or "").split()).upper() in descricoes_fora


def pastas_dos_anexos() -> list[Path]:
    pastas_configuradas = (carregar_json("arquivos") or {}).get("pastas_origem", {}).get(ASSUNTO_DOS_ANEXOS) or []
    pastas = []
    for pasta_configurada in [gravacao.PASTA_ANEXOS_999, *pastas_configuradas]:
        pasta = Path(pasta_configurada)
        if not pasta.is_absolute():
            pasta = PASTA_DO_APP / pasta
        if pasta.is_dir() and pasta.resolve() not in {ja_vista.resolve() for ja_vista in pastas}:
            pastas.append(pasta)
    return pastas


def anexos_enviados(revenda: str) -> dict[str, str]:
    pasta_da_revenda = gravacao.slug_revenda(revenda)
    caminho_de_cada_nome: dict[str, str] = {}
    for pasta in pastas_dos_anexos():
        alvo = pasta / pasta_da_revenda
        if not alvo.is_dir():
            continue
        try:
            for arquivo in alvo.iterdir():
                if arquivo.is_file():
                    caminho_de_cada_nome.setdefault(arquivo.name, str(arquivo))
        except OSError as erro:
            print(f"Farol 999: pasta de anexos {alvo} -- {erro}")
    return caminho_de_cada_nome


def arquivos_do_caixa(revenda: str, dia: date) -> list[tuple[str, str]] | None:
    chave = (chave_revenda(revenda), dia)
    with _trava_do_cache:
        if chave in _pasta_do_caixa:
            return _pasta_do_caixa[chave]
    try:
        achados, _onde = rede_documentos.arquivos_do_caixa(revenda, dia)
    except Exception as erro:
        print(f"Farol 999: pasta do caixa de {revenda} em {dia} -- {erro}")
        return None
    arquivos = [
        (achado.nome, str(achado.caminho)) for achado in achados if not rede_documentos.eh_backup_do_xml(achado.nome)
    ]
    with _trava_do_cache:
        _pasta_do_caixa[chave] = arquivos
    return arquivos


def lancamentos_do_dia(
    caixa_da_revenda: pl.DataFrame, dia: date | None, palavras_fora: list[str], descricoes_fora: list[str]
) -> list[dict]:
    if caixa_da_revenda.is_empty() or dia is None:
        return []
    lancamentos = []
    for lancamento in dados_ppf.extrato_caixa_999(caixa_da_revenda, dia).iter_rows(named=True):
        descricao = lancamento.get("PGMOVBAN_HISTORICO") or ""
        documento = lancamento.get("PGMOVBAN_NRDOC_EXTENSO") or ""
        if not documento.strip() or fica_de_fora(descricao, documento, palavras_fora, descricoes_fora):
            continue
        valor = lancamento.get("PGMOVBAN_VALORL")
        lancamentos.append(
            {
                "revenda": str(lancamento.get("REVENDA") or ""),
                "data": lancamento["DATA"],
                "descricao": descricao,
                "documento": documento,
                "valor": None if valor is None else abs(float(valor)),
            }
        )
    return lancamentos


def anexos_de_cada_lancamento(
    lancamentos: list[dict], ligados_na_tela: dict, ligados_pelo_atualizar: dict
) -> tuple[list[list[str]], bool]:
    anexos: list[list[str]] = [[] for _lancamento in lancamentos]
    enviados_de_cada_revenda: dict[str, dict[str, str]] = {}
    sem_ligacao_por_dia: dict[tuple, list[tuple[int, str]]] = {}
    caminhos_ja_ligados = set()
    for posicao, lancamento in enumerate(lancamentos):
        revenda = lancamento["revenda"]
        if revenda not in enviados_de_cada_revenda:
            enviados_de_cada_revenda[revenda] = anexos_enviados(revenda)
        enviados = enviados_de_cada_revenda[revenda]
        data_na_tela = lancamento["data"].strftime("%d/%m/%Y")
        nomes_da_linha = gravacao.anexos_999(
            revenda, data_na_tela, lancamento["descricao"], lancamento["documento"], nomes=list(enviados)
        )
        if nomes_da_linha:
            anexos[posicao] = [enviados[nome] for nome in nomes_da_linha]
            continue
        chave = manual_arquivo.chave_999(revenda, lancamento["data"], lancamento["descricao"], lancamento["documento"])
        comprovante_ligado = ligados_na_tela.get(chave) or ligados_pelo_atualizar.get(chave)
        if comprovante_ligado and comprovante_ligado.get("caminho"):
            anexos[posicao] = [str(comprovante_ligado["caminho"])]
            caminhos_ja_ligados.add(str(comprovante_ligado["caminho"]))
            continue
        sem_ligacao_por_dia.setdefault((revenda, lancamento["data"]), []).append((posicao, lancamento["documento"]))
    rede_respondeu = True
    for (revenda, dia), documentos in sem_ligacao_por_dia.items():
        arquivos = arquivos_do_caixa(revenda, dia)
        if arquivos is None:
            rede_respondeu = False
            continue
        caminho_de_cada_nome = {nome: caminho for nome, caminho in arquivos if caminho not in caminhos_ja_ligados}
        for posicao, nome in rede_documentos.casar_caixa(documentos, list(caminho_de_cada_nome)).items():
            anexos[posicao] = [caminho_de_cada_nome[nome]]
    return anexos, rede_respondeu


def situacao_do_lancamento(
    lancamento: dict, pre_auditorias: dict | None
) -> tuple[str, pre_auditoria_999.PreAuditoria999 | None]:
    if not lancamento["anexos"]:
        return "sem_anexo", None
    if pre_auditorias is None:
        return "ok", None
    chave = manual_arquivo.chave_999(
        lancamento["revenda"], lancamento["data"], lancamento["descricao"], lancamento["documento"]
    )
    da_linha = pre_auditorias.get(chave)
    if not pre_auditoria_999.ainda_vale(da_linha, lancamento["anexos"]):
        return "nao_conferido", None
    return pre_auditoria_999.estado(da_linha), da_linha


def linha_da_revenda(
    revenda: str,
    referencia: date,
    caixa_de_todas: pl.DataFrame,
    saldo_999: pl.DataFrame,
    batidas: pl.DataFrame,
    ligados_na_tela: dict,
    ligados_pelo_atualizar: dict,
    regras_de_fora: dict,
    pre_auditorias: dict | None,
) -> dict:
    caixa_da_revenda = (
        dados_ppf.filtrar_por_revenda(caixa_de_todas, revenda) if not caixa_de_todas.is_empty() else caixa_de_todas
    )
    dia = dados_ppf.data_referencia_999(
        caixa_da_revenda,
        referencia,
        saldo_999=dados_ppf.filtrar_por_revenda(saldo_999, revenda),
        batida=dados_ppf.filtrar_por_revenda(batidas, revenda),
    )
    lancamentos = lancamentos_do_dia(
        caixa_da_revenda, dia, regras_de_fora["fora_quando_contem"], regras_de_fora["descricoes_fora"]
    )
    anexos, rede_respondeu = anexos_de_cada_lancamento(lancamentos, ligados_na_tela, ligados_pelo_atualizar)
    for lancamento, anexos_do_lancamento in zip(lancamentos, anexos):
        lancamento["anexos"] = anexos_do_lancamento
        lancamento["situacao"], lancamento["pre_auditoria"] = situacao_do_lancamento(lancamento, pre_auditorias)
    pendentes = [lancamento for lancamento in lancamentos if lancamento["situacao"] != "ok"]
    return {
        "revenda": revenda,
        "dia": dia,
        "total": len(lancamentos),
        "com_anexo": sum(1 for lancamento in lancamentos if lancamento["anexos"]),
        "sem_anexo": sum(1 for lancamento in lancamentos if not lancamento["anexos"]),
        "apontados": sum(1 for lancamento in lancamentos if lancamento["situacao"] in ("erro", "atencao")),
        "nao_conferidos": sum(1 for lancamento in lancamentos if lancamento["situacao"] == "nao_conferido"),
        "pendentes": pendentes,
        "completo": not pendentes,
        "rede_respondeu": rede_respondeu,
    }


def painel_do_dia(referencia: date, revendas: list[str], com_pre_auditoria: bool) -> dict:
    extrato = dados_ppf.extrato_banco()
    caixa_de_todas = (
        extrato.filter(pl.col("PGMOVBAN_NRBCO") == dados_ppf.BANCO_CAIXA)
        if not extrato.is_empty() and "PGMOVBAN_NRBCO" in extrato.columns
        else pl.DataFrame()
    )
    batidas_com_dado = [
        batida for batida in (dados_ppf.batida_diaria(), dados_ppf.batida_diaria_geral()) if not batida.is_empty()
    ]
    batidas = pl.concat(batidas_com_dado, how="diagonal_relaxed") if batidas_com_dado else pl.DataFrame()
    saldo_999 = dados_ppf.saldo_banco_999()
    ligados_na_tela, ligados_pelo_atualizar = manual_arquivo.vinculos_999(), dados_ppf.vinculos_999()
    regras_de_fora = configuracao()
    pre_auditorias = dados_ppf.pre_auditoria_do_999() if com_pre_auditoria else None
    linhas = [
        linha_da_revenda(
            revenda,
            referencia,
            caixa_de_todas,
            saldo_999,
            batidas,
            ligados_na_tela,
            ligados_pelo_atualizar,
            regras_de_fora,
            pre_auditorias,
        )
        for revenda in revendas
    ]
    return {
        "linhas": linhas,
        "total_pendentes": sum(len(linha["pendentes"]) for linha in linhas),
        "revendas_pendentes": sum(1 for linha in linhas if not linha["completo"]),
    }


def arquivos_que_mudam_o_painel(revendas: list[str]) -> list[Path]:
    caches = [
        dados_ppf.PASTA_PARQUET / f"{nome}.parquet"
        for nome in (
            "extrato_banco",
            "saldo_banco_999",
            "batida_diaria",
            "batida_diaria_geral",
            "vinculos_999",
            pre_auditoria_999.ARQUIVO_DOS_APONTAMENTOS,
            pre_auditoria_999.ARQUIVO_DOS_CONFERIDOS,
        )
    ]
    pastas_das_revendas = [
        pasta / gravacao.slug_revenda(revenda) for pasta in pastas_dos_anexos() for revenda in revendas
    ]
    return [*caches, manual_arquivo.caminho("vinculos_999"), *pastas_das_revendas]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    login = sys.argv[1] if "__file__" in globals() and len(sys.argv) > 1 else input("Login: ").strip()
    data_pedida = sys.argv[2] if "__file__" in globals() and len(sys.argv) > 2 else ""
    referencia = date.fromisoformat(data_pedida) if data_pedida else date.today()
    from core.config import CHAVE_VER_PRE_AUDITORIA, pode

    painel = painel_do_dia(referencia, revendas_do_farol(login), pode(login, CHAVE_VER_PRE_AUDITORIA))
    for linha in painel["linhas"]:
        print(
            f"{linha['revenda']:15} dia {linha['dia']} | {linha['com_anexo']}/{linha['total']} com anexo | "
            f"{linha['apontados']} apontado(s) | {linha['nao_conferidos']} nao conferido(s)"
            f"{'' if linha['rede_respondeu'] else ' | a pasta do caixa nao respondeu'}"
        )
        for pendente in linha["pendentes"]:
            print(
                f"    {pendente['situacao']}: {pendente['data']:%d/%m/%Y} | {pendente['descricao'].strip()} | "
                f"{pendente['documento'].strip()} | {pendente['valor']}"
            )
    print(f"pendentes: {painel['total_pendentes']} em {painel['revendas_pendentes']} revenda(s)")
