import re
import unicodedata
from pathlib import Path

from loguru import logger

PASTA_APP = Path(__file__).parents[3]

TIMEOUT_SEGUNDOS = 45

TIPOS_ACEITOS = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _sem_acento_maiusculo(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.upper()


NOMES_POR_DOCUMENTO = {
    "anexo1": ("CNH", "CARTEIRA NACIONAL DE HABILITACAO", "HABILITACAO", "CARTEIRA DE IDENTIDADE", "IDENTIDADE"),
    "anexo2": ("COMODATO", "TERMO DE RESPONSABILIDADE", "EMPRESTIMO"),
    "anexo3": ("CANHOTO", "COMPROVANTE", "DANFE", "NOTA FISCAL", "NOTA DE VENDA", "RECIBO"),
}
SIGLAS_POR_DOCUMENTO = {
    "anexo1": ("RG", "CIN"),
    "anexo2": (),
    "anexo3": ("NFE", "NF"),
}

TIPO_IDENTIDADE = "identidade"

TIPO_ESPERADO_POR_DOCUMENTO = {
    "anexo1": TIPO_IDENTIDADE,
    "anexo2": "termo_comodato",
    "anexo3": "canhoto_nfe",
}

NOME_AMIGAVEL = {
    "anexo1": "Documento PDV (RG ou CNH)",
    "anexo2": "Comodato (termo/contrato)",
    "anexo3": "Canhoto (comprovante de entrega ou DANFE)",
}


def tipo_confere(tipo_documento: str | None, documento: str) -> bool:
    if not tipo_documento:
        return False
    texto = _sem_acento_maiusculo(str(tipo_documento))
    if any(nome in texto for nome in NOMES_POR_DOCUMENTO.get(documento, ())):
        return True
    palavras = set(re.findall(r"[A-Z]+", texto))
    return any(sigla in palavras for sigla in SIGLAS_POR_DOCUMENTO.get(documento, ()))


def documento_confere(extraido: dict, documento: str) -> bool:
    if extraido.get("tipo_confere") is True:
        return True
    return tipo_confere(extraido.get("tipo_documento"), documento)


def _ler_pela_api(caminho_imagem: str, tipo_mime: str, tipo_esperado: str | None) -> dict | None:
    """Portfólio: sem o serviço de leitura de documentos -- o mesmo caminho do serviço fora do ar."""
    return None


def api_ligada() -> bool:
    try:
        from core.config_arquivo import carregar_json

        return carregar_json("extracao_documentos", padrao={}).get("api_ligada") is True
    except Exception as erro:
        logger.warning(f"Extração de documentos: chave da API ilegível, segue desligada -- {erro}")
        return False


def aprova_sem_reconhecer() -> bool:
    try:
        from core.config_arquivo import carregar_json

        return carregar_json("extracao_documentos", padrao={}).get("aprova_sem_reconhecer") is True
    except Exception as erro:
        logger.warning(f"Extração de documentos: chave aprova_sem_reconhecer ilegível, segue recusando -- {erro}")
        return False


def ler_documento(caminho_imagem: str, tipo_mime: str, tipo_esperado: str | None = None) -> tuple[dict | None, str]:
    """Portfólio: sem serviço de leitura nem OCR local no navegador."""
    return None, ""


def extrair_doc(caminho_imagem: str, tipo_esperado: str | None = None) -> dict:
    extensao = Path(caminho_imagem).suffix.lower()
    tipo_mime = TIPOS_ACEITOS.get(extensao)
    if tipo_mime is None:
        raise ValueError("Formato de arquivo não suportado. Por favor, envie um arquivo PDF, JPEG, PNG ou WEBP.")

    resultado = {
        "nome_completo": "Nao tem",
        "cpf": "Nao tem",
        "api_offline": False,
        "tipo_documento": None,
        "campos_adicionais": {},
        "tipo_normalizado": None,
        "tipo_confere": None,
        "motor": "",
        "texto": "",
        "cpfs": [],
    }
    corpo, motor = ler_documento(caminho_imagem, tipo_mime, tipo_esperado)
    if corpo is None:
        # Portfólio: o caminho do original quando nenhuma leitura está disponível.
        return {**resultado, "api_offline": True}
    resultado["motor"] = motor
    resultado["texto"] = str(corpo.get("texto") or "")
    resultado["cpfs"] = list(corpo.get("cpfs") or [])
    dados = corpo.get("data") or {}
    resultado["tipo_documento"] = corpo.get("document_type")
    resultado["tipo_normalizado"] = corpo.get("tipo_normalizado")
    resultado["tipo_confere"] = corpo.get("tipo_confere")
    adicionais = dados.get("campos_adicionais")
    if isinstance(adicionais, dict):
        resultado["campos_adicionais"] = adicionais
    nome_completo = dados.get("nome_completo")
    cpf = dados.get("cpf")

    if nome_completo:
        resultado["nome_completo"] = _sem_acento_maiusculo(nome_completo)
    if cpf:
        resultado["cpf"] = "".join(caractere for caractere in str(cpf) if caractere.isdigit())

    return resultado
