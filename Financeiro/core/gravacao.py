"""Contratos de empréstimo (PDF) e a configuração de cada contrato. No original vão
para pasta e MySQL; no portfólio ficam na memória desta sessão."""

import re
from pathlib import Path

CAMPOS_CONFIG_EMPRESTIMO = ("valor_credito", "entrada", "taxa_juros")

_CONTRATOS: dict[tuple[str, str], bytes] = {}
_CONFIG: dict[tuple[str, str], dict] = {}


def _nome_seguro(texto: str) -> str:
    return re.sub(r"[^\w.\-]", "_", str(texto or "")).strip("_") or "contrato"


def nome_do_contrato(contrato: str) -> str:
    return _nome_seguro(contrato) + ".pdf"


def contrato_salvo(revenda: str, contrato: str) -> str | None:
    return nome_do_contrato(contrato) if (revenda, nome_do_contrato(contrato)) in _CONTRATOS else None


def conteudo_do_contrato(revenda: str, contrato: str) -> bytes | None:
    return _CONTRATOS.get((revenda, nome_do_contrato(contrato)))


def contratos_salvos(revenda: str) -> set[str]:
    return {nome.lower() for rev, nome in _CONTRATOS if rev == revenda}


def guardar_contrato(revenda: str, contrato: str, origem: str) -> str:
    _CONTRATOS[(revenda, nome_do_contrato(contrato))] = Path(origem).read_bytes()
    return nome_do_contrato(contrato)


def excluir_contrato(revenda: str, contrato: str) -> bool:
    return _CONTRATOS.pop((revenda, nome_do_contrato(contrato)), None) is not None


def salvar_config_emprestimo(revenda: str, contrato: str, campo: str, valor, usuario: str) -> dict:
    if campo not in CAMPOS_CONFIG_EMPRESTIMO:
        raise ValueError(f"Campo inválido: {campo}")
    linha = _CONFIG.setdefault((revenda, contrato), {"revenda": revenda, "contrato": contrato})
    linha[campo] = valor
    linha["atualizado_por"] = usuario
    return dict(linha)
