from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

import cachetools

PASTA_DO_APP = Path(__file__).resolve().parent.parent
PASTA_DO_CACHE_DO_SEGUNDO_ERP = PASTA_DO_APP / "data" / "bd_segundo_erp"
PASTA_DO_MANUAL_DO_SEGUNDO_ERP = PASTA_DO_APP / "data" / "manual_segundo_erp"

ASSUNTOS_DE_TODAS_AS_REVENDAS = {"assinaturas", "celulas_marcadas_mare"}

_revenda_de_cada_sessao: cachetools.LRUCache = cachetools.LRUCache(maxsize=2048)


def _sessao_raiz():
    try:
        from shiny.session import get_current_session

        sessao = get_current_session()
    except Exception:
        return None
    if sessao is None:
        return None
    return sessao.root_scope() if hasattr(sessao, "root_scope") else sessao


def revenda_da_sessao() -> str | None:
    sessao = _sessao_raiz()
    if sessao is None:
        return None
    sessao_id = getattr(sessao, "id", None)
    if sessao_id is not None and sessao_id in _revenda_de_cada_sessao:
        return _revenda_de_cada_sessao[sessao_id]
    try:
        from shiny import reactive

        with reactive.isolate():
            busca = sessao.clientdata.url_search()
    except Exception:
        return None
    valores = parse_qs(str(busca or "").lstrip("?")).get("REVENDA")
    revenda = valores[0] if valores else None
    if sessao_id is not None:
        _revenda_de_cada_sessao[sessao_id] = revenda
    return revenda


def _revenda_do_segundo_erp_da_sessao() -> str | None:
    revenda = revenda_da_sessao()
    if not revenda:
        return None
    from core import revendas as cadastro_revendas

    if not cadastro_revendas.eh_do_segundo_erp(revenda):
        return None
    return revenda


def sessao_do_segundo_erp() -> bool:
    return _revenda_do_segundo_erp_da_sessao() is not None


def arquivos_do_atualizar_do_segundo_erp(regra_do_atualizar: dict) -> list[str]:
    arquivos = [str(tabela) for tabela in regra_do_atualizar.get("tabelas") or []]
    arquivos += [str(tabela) for tabela in regra_do_atualizar.get("tabelas_deste_app") or []]
    if regra_do_atualizar.get("extrato_do_banco"):
        arquivos.append("extratos_bancos")
    if regra_do_atualizar.get("vinculos_pelo_nome"):
        arquivos.append("vinculos_ocr")
    if regra_do_atualizar.get("composicao", True) is not False:
        arquivos += ["composicao", "dados_manuais"]
    return arquivos


def tabelas_da_camada_do_segundo_erp(regra_do_atualizar: dict) -> list[str]:
    tabelas = [str(tabela) for tabela in regra_do_atualizar.get("tabelas") or []]
    if regra_do_atualizar.get("extrato_do_banco"):
        tabelas.append("extratos_bancos_expandido")
    return tabelas


ARQUIVOS_DO_RETRATO = ("composicao_snapshot", "contas_pagar_snapshot", "pagamentos_snapshot")
ARQUIVOS_DA_PRE_AUDITORIA = ("pre_auditoria", "pre_auditoria_conferidos")


def arquivos_da_tela_do_segundo_erp(regra_do_atualizar: dict) -> list[str]:
    arquivos = arquivos_do_atualizar_do_segundo_erp(regra_do_atualizar) + list(ARQUIVOS_DA_PRE_AUDITORIA)
    if regra_do_atualizar.get("retrato_de_ontem"):
        arquivos += list(ARQUIVOS_DO_RETRATO)
    return arquivos


def cache_do_segundo_erp(arquivo: str) -> bool:
    revenda = _revenda_do_segundo_erp_da_sessao()
    if revenda is None:
        return False
    from core.config import regra_do_segundo_erp

    regra_do_atualizar = (regra_do_segundo_erp(revenda) or {}).get("atualizar") or {}
    return arquivo in arquivos_da_tela_do_segundo_erp(regra_do_atualizar)


def pasta_do_cache(arquivo: str, pasta_de_sempre: Path) -> Path:
    if cache_do_segundo_erp(arquivo):
        return PASTA_DO_CACHE_DO_SEGUNDO_ERP
    return pasta_de_sempre


def pasta_dos_carimbos(pasta_de_sempre: Path) -> Path:
    if sessao_do_segundo_erp():
        return PASTA_DO_CACHE_DO_SEGUNDO_ERP
    return pasta_de_sempre


_revenda_do_segundo_erp_do_processo: str | None = None


def usar_o_manual_do_segundo_erp(revenda: str | None) -> None:
    global _revenda_do_segundo_erp_do_processo
    _revenda_do_segundo_erp_do_processo = revenda


def revenda_do_manual_do_segundo_erp() -> str | None:
    return _revenda_do_segundo_erp_da_sessao() or _revenda_do_segundo_erp_do_processo


def manual_do_segundo_erp(assunto: str) -> bool:
    if assunto in ASSUNTOS_DE_TODAS_AS_REVENDAS:
        return False
    return revenda_do_manual_do_segundo_erp() is not None
