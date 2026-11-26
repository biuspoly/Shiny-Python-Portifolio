from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

PASTA_CONFIG = Path(__file__).parents[1] / "config"

_cache: dict = {}


def carregar_json(nome: str, padrao: Any = None) -> Any:
    caminho = PASTA_CONFIG / f"{nome}.json"
    try:
        chave = (nome, caminho.stat().st_mtime_ns)
    except OSError:
        logger.warning(f"config/{nome}.json não encontrado -- seguindo com o padrão")
        return padrao if padrao is not None else {}
    if chave not in _cache:
        try:
            _cache[chave] = json.loads(caminho.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"config/{nome}.json inválido ({exc}) -- seguindo com o padrão")
            return padrao if padrao is not None else {}
    return _cache[chave]


def gravar_json(nome: str, config: Any) -> None:
    caminho = PASTA_CONFIG / f"{nome}.json"
    temporario = caminho.with_suffix(".json.tmp")
    temporario.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporario.replace(caminho)
