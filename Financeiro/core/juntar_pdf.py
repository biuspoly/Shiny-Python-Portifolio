from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

PASTA = Path(__file__).resolve().parents[1] / "data" / "leituras" / "pdf_juntado"
GUARDA_DIAS = 30
EXTENSOES_DE_IMAGEM = {".jpg", ".jpeg", ".png"}
LARGURA_DA_PAGINA_DA_IMAGEM = 595


def _assinatura(arquivos: list[Path]) -> str:
    partes = []
    for arquivo in arquivos:
        info = arquivo.stat()
        partes.append(f"{arquivo}|{info.st_size}|{int(info.st_mtime)}")
    return hashlib.sha1("\n".join(partes).encode("utf-8")).hexdigest()[:20]


def _limpar_antigos(pasta: Path) -> None:
    import time

    limite = time.time() - GUARDA_DIAS * 86400
    for velho in pasta.glob("*.pdf"):
        try:
            if velho.stat().st_mtime < limite:
                velho.unlink()
        except OSError:
            continue


def pdf_da_imagem(arquivo: Path) -> io.BytesIO:
    from PIL import Image, ImageOps

    saida = io.BytesIO()
    with Image.open(arquivo) as aberta:
        imagem = ImageOps.exif_transpose(aberta)
        com_transparencia = imagem.convert("RGBA")
        branca = Image.new("RGB", imagem.size, (255, 255, 255))
        branca.paste(com_transparencia, mask=com_transparencia.getchannel("A"))
        branca.save(saida, format="PDF", resolution=branca.width * 72 / LARGURA_DA_PAGINA_DA_IMAGEM)
    saida.seek(0)
    return saida


def abre(arquivo: Path) -> bool:
    if not arquivo.is_file():
        return False
    try:
        if arquivo.suffix.lower() in EXTENSOES_DE_IMAGEM:
            pdf_da_imagem(arquivo)
            return True
        if arquivo.suffix.lower() == ".pdf":
            from pypdf import PdfReader

            PdfReader(str(arquivo)).pages[0]
            return True
    except Exception:
        return False
    return False


def juntar(arquivos: list[Path], pasta: Path | None = None) -> Path:
    from pypdf import PdfWriter

    pasta = pasta or PASTA
    validos = [arquivo for arquivo in dict.fromkeys(Path(a) for a in arquivos) if abre(arquivo)]
    if not validos:
        raise ValueError("nenhum PDF para juntar")
    if len(validos) == 1:
        return validos[0]
    destino = pasta / f"{_assinatura(validos)}.pdf"
    if destino.is_file():
        return destino
    pasta.mkdir(parents=True, exist_ok=True)
    _limpar_antigos(pasta)
    escritor = PdfWriter()
    for arquivo in validos:
        if arquivo.suffix.lower() in EXTENSOES_DE_IMAGEM:
            escritor.append(pdf_da_imagem(arquivo))
        else:
            escritor.append(str(arquivo))
    temporario = destino.with_suffix(".tmp")
    with temporario.open("wb") as saida:
        escritor.write(saida)
    temporario.replace(destino)
    return destino


def com_a_ultima_pagina(documento: Path, de_onde: Path, pasta: Path | None = None) -> Path:
    from pypdf import PdfReader, PdfWriter

    pasta = pasta or PASTA
    destino = pasta / f"{_assinatura([documento, de_onde])}-assinado.pdf"
    if destino.is_file():
        return destino
    pasta.mkdir(parents=True, exist_ok=True)
    escritor = PdfWriter()
    escritor.append(str(documento))
    paginas_de_onde = PdfReader(str(de_onde)).pages
    escritor.add_page(paginas_de_onde[len(paginas_de_onde) - 1])
    temporario = destino.with_suffix(".tmp")
    with temporario.open("wb") as saida:
        escritor.write(saida)
    temporario.replace(destino)
    return destino


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    entrada = [Path(a) for a in (sys.argv[1:] if "__file__" in globals() else [])] or [
        Path(p.strip().strip('"')) for p in input("PDFs separados por ; : ").split(";") if p.strip()
    ]
    resultado = juntar(entrada)
    from pypdf import PdfReader

    print(f"  arquivos:  {len(entrada)}")
    print(f"  juntado:   {resultado}")
    print(f"  paginas:   {len(PdfReader(str(resultado)).pages)}")
