"""Assinatura de documentos pelo celular (QR code -> página no celular -> PDF carimbado).
No portfólio não há servidor para o celular alcançar: o cadastro mostra o aviso e nada é assinado."""

VALIDADE_MINUTOS = 10
TAMANHO_MAXIMO = 8 * 1024 * 1024
EXTENSOES_ASSINAVEIS = {".pdf", ".png", ".jpg", ".jpeg"}


def novo_link(usuario: str) -> str:
    return ""


def limpar(bruto: bytes) -> bytes:
    return bruto


def assinar_pdf(original, destino, png: bytes, nome: str, quando) -> None:
    raise RuntimeError("Assinatura indisponível no portfólio")


def como_data_uri(png: bytes | None) -> str:
    return ""


def de_onde(request) -> str:
    return ""


def bind_partial(*_args, **_kwargs) -> None:
    return None
