import os
from pathlib import Path

_PASTA_WWW = Path(__file__).parent.parent / "www"


def forca_style(src_relativo: str) -> str:
    caminho = _PASTA_WWW / src_relativo
    mtime = int(os.path.getmtime(caminho))
    return f"{src_relativo}?v={mtime}"
