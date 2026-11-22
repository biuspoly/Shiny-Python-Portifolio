"""Grava o retrato diário do Fluxo Financeiro (fluxo_mare_snapshot.parquet) dos últimos N dias
úteis, montando a tabela com o mesmo código da tela. No original, uma rotina faz isso todo dia.

Uso: python scripts/retratos_fluxo.py [dias]
"""

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import polars as pl  # noqa: E402

from pages.Fluxo_Financeiro.Dados import dados_fluxo_consolidado as f  # noqa: E402
from pages.PPF.Dados import dados_ppf as dp  # noqa: E402


def _json(valor):
    return valor.isoformat() if isinstance(valor, (date, datetime)) else str(valor)


def gravar(dias: int) -> None:
    hoje = date.fromisoformat(os.environ["DATA_BASE"]) if os.getenv("DATA_BASE") else date.today()
    linhas = []
    dia = hoje
    while len(linhas) < dias:
        dia -= timedelta(days=1)
        if dia.weekday() >= 5:
            continue
        payload = json.dumps(f.retrato(dia), ensure_ascii=False, default=_json)
        linhas.append(
            {
                "id": len(linhas) + 1,
                "data_snapshot": dia,
                "revendas": "TODAS",
                "payload": payload,
                "created_at": datetime.combine(dia, datetime.min.time()).replace(hour=18),
            }
        )
    pl.DataFrame(linhas).write_parquet(dp.PASTA_PARQUET / "fluxo_mare_snapshot.parquet", compression="zstd")
    print(f"  bd_financeiro/fluxo_mare_snapshot.parquet: {len(linhas)} retratos")


if __name__ == "__main__":
    gravar(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
