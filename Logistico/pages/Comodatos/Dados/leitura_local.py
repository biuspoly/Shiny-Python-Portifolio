from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from functools import lru_cache
from pathlib import Path

if __name__ == "__main__" and "__file__" in globals():
    PYTHON_DO_PROJETO = Path(__file__).resolve().parents[4] / ".venv" / "Scripts" / "python.exe"
    try:
        import loguru  # noqa: F401
    except ImportError:
        if PYTHON_DO_PROJETO.is_file() and Path(sys.executable).resolve() != PYTHON_DO_PROJETO.resolve():
            sys.exit(subprocess.run([str(PYTHON_DO_PROJETO), __file__, *sys.argv[1:]], check=False).returncode)
        raise

import numpy as np
from loguru import logger
from PIL import Image, ImageOps
from rapidfuzz import fuzz

try:
    from rapidocr_onnxruntime import RapidOCR

    ERRO_DO_RAPIDOCR = ""
except Exception as erro_de_import:
    RapidOCR = None
    ERRO_DO_RAPIDOCR = f"{type(erro_de_import).__name__}: {erro_de_import}"

try:
    from pyzbar.pyzbar import ZBarSymbol
    from pyzbar.pyzbar import decode as ler_codigos_de_barra

    SIMBOLOS_LIDOS = [ZBarSymbol.CODE128, ZBarSymbol.QRCODE, ZBarSymbol.EAN13, ZBarSymbol.I25, ZBarSymbol.CODE39]
    ERRO_DO_LEITOR_DE_BARRAS = ""
except Exception as erro_de_import:
    ler_codigos_de_barra = None
    SIMBOLOS_LIDOS = []
    ERRO_DO_LEITOR_DE_BARRAS = f"{type(erro_de_import).__name__}: {erro_de_import}"


EXECUTAVEIS_TESSERACT = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)
PASTAS_DE_IDIOMA_EXTRAS = (Path.home() / "tessdata",)
IDIOMA = "por"
SEGUNDOS_POR_LEITURA = 30

MODO_AUTOMATICO = 3
MODO_SO_ORIENTACAO = 0

LADO_MAXIMO_PARA_LER = 3000
LADO_MINIMO_PARA_LER = 2500
LADO_MAXIMO_PARA_AMPLIAR = 2000

PAGINAS_LIDAS = 3
DPI_DO_PDF = 200
MINIMO_LETRAS_DO_TEXTO = 60

_TRAVA_PDFIUM = threading.Lock()


def executavel_tesseract() -> str | None:
    no_caminho = shutil.which("tesseract")
    if no_caminho:
        return no_caminho
    for candidato in EXECUTAVEIS_TESSERACT:
        if Path(candidato).is_file():
            return candidato
    return None


@lru_cache(maxsize=4)
def _argumentos_de_idioma(executavel: str) -> tuple[str, ...] | None:
    try:
        saida = subprocess.run([executavel, "--list-langs"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    linhas = saida.stdout.decode("utf-8", "replace").splitlines()[1:]
    idiomas = [linha.strip() for linha in linhas]
    if IDIOMA in idiomas:
        return ()
    for pasta in PASTAS_DE_IDIOMA_EXTRAS:
        if (pasta / f"{IDIOMA}.traineddata").is_file():
            return ("--tessdata-dir", str(pasta))
    return None


def tesseract_indisponivel() -> str:
    executavel = executavel_tesseract()
    if not executavel:
        return "tesseract não encontrado (instalar: winget install UB-Mannheim.TesseractOCR)"
    if _argumentos_de_idioma(executavel) is None:
        return (
            f"o tesseract não tem o português ({IDIOMA}.traineddata na pasta tessdata dele,"
            f" ou em {PASTAS_DE_IDIOMA_EXTRAS[0]})"
        )
    return ""


def indisponivel() -> str:
    if RapidOCR is not None:
        return ""
    motivo = tesseract_indisponivel()
    return f"RapidOCR ausente ({ERRO_DO_RAPIDOCR}) e {motivo}" if motivo else ""


def _rodar_tesseract(imagem: Image.Image, argumentos: list[str]) -> subprocess.CompletedProcess:
    executavel = executavel_tesseract()
    argumentos_de_idioma = _argumentos_de_idioma(executavel) if executavel else None
    if executavel is None or argumentos_de_idioma is None:
        raise RuntimeError(tesseract_indisponivel())
    with tempfile.TemporaryDirectory() as pasta:
        arquivo = Path(pasta) / "pagina.png"
        imagem.save(arquivo)
        comando = [executavel, *argumentos_de_idioma, str(arquivo), "stdout", *argumentos]
        return subprocess.run(comando, capture_output=True, timeout=SEGUNDOS_POR_LEITURA)


def _texto_da_imagem(imagem: Image.Image) -> str:
    resultado = _rodar_tesseract(imagem, ["-l", IDIOMA, "--psm", str(MODO_AUTOMATICO)])
    if resultado.returncode != 0:
        raise RuntimeError(resultado.stderr.decode("utf-8", "replace").strip()[:150])
    return resultado.stdout.decode("utf-8", "replace")


def _giro_da_imagem(imagem: Image.Image) -> int:
    try:
        resultado = _rodar_tesseract(imagem, ["--psm", str(MODO_SO_ORIENTACAO)])
    except (OSError, subprocess.SubprocessError):
        return 0
    achado = re.search(r"Rotate:\s*(\d+)", resultado.stdout.decode("utf-8", "replace"))
    return int(achado.group(1)) if achado else 0


NUCLEOS_DO_RAPIDOCR = 1

PROPORCAO_DE_LINHA = 2.0
LINHAS_QUE_VOTAM = 24
PROPORCAO_DE_CAIXA_DE_LADO = 1.5
CONFIANCA_MINIMA_DA_CAIXA = 0.5
FRACAO_DA_MESMA_LINHA = 0.6
GRAUS_PARA_ENDIREITAR = 1.0
PASSADAS_PARA_ENDIREITAR = 2
LADO_MENOR_DA_DETECCAO = 736
_FORA_DO_ALFABETO_LATINO = re.compile(r"[^\x20-\x7eª°ºÀ-ÿ]")

PASTA_DOS_MODELOS = Path(__file__).resolve().parent / "modelos"
MODELO_DE_LEITURA = PASTA_DOS_MODELOS / "latin_PP-OCRv5_rec_mobile.onnx"
ALFABETO_DO_MODELO = PASTA_DOS_MODELOS / "ppocrv5_latin_dict.txt"

_TRAVA_RAPIDOCR = threading.Lock()
_motor_rapidocr = None


def _motor() -> RapidOCR:
    global _motor_rapidocr
    if _motor_rapidocr is None:
        modelo_latino = {}
        if MODELO_DE_LEITURA.is_file() and ALFABETO_DO_MODELO.is_file():
            modelo_latino = {"rec_model_path": str(MODELO_DE_LEITURA), "rec_keys_path": str(ALFABETO_DO_MODELO)}
        else:
            logger.warning(f"Leitura local: modelo latino ausente em {PASTA_DOS_MODELOS}, segue o de chinês do pacote")
        _motor_rapidocr = RapidOCR(
            intra_op_num_threads=NUCLEOS_DO_RAPIDOCR, inter_op_num_threads=NUCLEOS_DO_RAPIDOCR, **modelo_latino
        )
    return _motor_rapidocr


def versao_da_leitura() -> str:
    if RapidOCR is None:
        return "tesseract"
    if MODELO_DE_LEITURA.is_file() and ALFABETO_DO_MODELO.is_file():
        return f"rapidocr {MODELO_DE_LEITURA.name}"
    return "rapidocr chines"


def _largura_e_altura(cantos: np.ndarray) -> tuple[float, float]:
    largura = max(np.linalg.norm(cantos[0] - cantos[1]), np.linalg.norm(cantos[2] - cantos[3]))
    altura = max(np.linalg.norm(cantos[0] - cantos[3]), np.linalg.norm(cantos[1] - cantos[2]))
    return float(largura), float(altura)


def _recorte(figura: np.ndarray, cantos: np.ndarray) -> np.ndarray:
    import cv2

    largura, altura = _largura_e_altura(cantos)
    largura, altura = max(int(largura), 1), max(int(altura), 1)
    destino = np.array([[0, 0], [largura, 0], [largura, altura], [0, altura]], dtype=np.float32)
    matriz = cv2.getPerspectiveTransform(cantos.astype(np.float32), destino)
    return cv2.warpPerspective(
        figura, matriz, (largura, altura), borderMode=cv2.BORDER_REPLICATE, flags=cv2.INTER_CUBIC
    )


def _giro_da_pagina(motor, figura: np.ndarray, caixas: list[np.ndarray]) -> int:
    linhas = []
    for cantos in caixas:
        largura, altura = _largura_e_altura(cantos)
        if max(largura, altura) >= PROPORCAO_DE_LINHA * max(min(largura, altura), 1.0):
            linhas.append((max(largura, altura), altura > largura, cantos))
    if not linhas:
        return 0
    pagina_de_lado = sum(1 for _comprimento, de_lado, _cantos in linhas if de_lado) * 2 > len(linhas)
    votantes = sorted((linha for linha in linhas if linha[1] == pagina_de_lado), key=lambda linha: -linha[0])
    recortes = []
    for _comprimento, _de_lado, cantos in votantes[:LINHAS_QUE_VOTAM]:
        recorte = _recorte(figura, cantos)
        recortes.append(np.ascontiguousarray(np.rot90(recorte)) if pagina_de_lado else recorte)
    if not recortes:
        return 0
    _recortes, classes, _tempo = motor.text_cls(recortes)
    votos_de_cabeca_para_baixo = sum(confianca for rotulo, confianca in classes if rotulo == "180")
    votos_em_pe = sum(confianca for rotulo, confianca in classes if rotulo == "0")
    de_cabeca_para_baixo = votos_de_cabeca_para_baixo > votos_em_pe
    if pagina_de_lado:
        return 90 if de_cabeca_para_baixo else 270
    return 180 if de_cabeca_para_baixo else 0


def _inclinacao_das_linhas(caixas: list[np.ndarray]) -> float:
    angulos = []
    pesos = []
    for cantos in caixas:
        largura, altura = _largura_e_altura(cantos)
        if max(largura, altura) < PROPORCAO_DE_LINHA * max(min(largura, altura), 1.0):
            continue
        lado = cantos[1] - cantos[0] if largura >= altura else cantos[2] - cantos[1]
        angulo = float(np.degrees(np.arctan2(lado[1], lado[0])))
        angulos.append((angulo + 45.0) % 90.0 - 45.0)
        pesos.append(max(largura, altura))
    if not angulos:
        return 0.0
    ordem = np.argsort(angulos)
    acumulado = np.cumsum(np.array(pesos)[ordem])
    return float(np.array(angulos)[ordem][np.searchsorted(acumulado, acumulado[-1] / 2)])


def _endireitada(figura: np.ndarray, graus: float) -> np.ndarray:
    import cv2

    altura, largura = figura.shape[:2]
    matriz = cv2.getRotationMatrix2D((largura / 2, altura / 2), graus, 1.0)
    cosseno, seno = abs(matriz[0, 0]), abs(matriz[0, 1])
    nova_largura = int(altura * seno + largura * cosseno)
    nova_altura = int(altura * cosseno + largura * seno)
    matriz[0, 2] += nova_largura / 2 - largura / 2
    matriz[1, 2] += nova_altura / 2 - altura / 2
    return cv2.warpAffine(
        figura,
        matriz,
        (nova_largura, nova_altura),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def _cantos_na_pagina_em_pe(cantos: np.ndarray, giro: int, largura: int, altura: int) -> np.ndarray:
    x, y = cantos[:, 0], cantos[:, 1]
    if giro == 90:
        return np.stack([altura - y, x], axis=1)
    if giro == 180:
        return np.stack([largura - x, altura - y], axis=1)
    if giro == 270:
        return np.stack([y, largura - x], axis=1)
    return cantos


def _caixas_achadas(motor, figura: np.ndarray, escala: float) -> list[np.ndarray]:
    import cv2

    ampliada = cv2.resize(figura, None, fx=escala, fy=escala, interpolation=cv2.INTER_LINEAR) if escala > 1 else figura
    caixas, _tempos = motor(ampliada, use_det=True, use_cls=False, use_rec=False)
    return [np.array(cantos, dtype=np.float32) / escala for cantos in (caixas or [])]


def _ler_com_rapidocr(imagem: Image.Image) -> tuple[list, int]:
    figura = np.ascontiguousarray(np.asarray(imagem.convert("RGB")))
    escala = max(1.0, LADO_MENOR_DA_DETECCAO / max(min(figura.shape[:2]), 1))
    with _TRAVA_RAPIDOCR:
        motor = _motor()
        caixas = _caixas_achadas(motor, figura, 1.0)
        if not caixas:
            return [], 0
        original = figura
        giro_total = 0.0
        for _passada in range(PASSADAS_PARA_ENDIREITAR):
            inclinacao = _inclinacao_das_linhas(caixas)
            if abs(inclinacao) < GRAUS_PARA_ENDIREITAR:
                break
            giro_total += inclinacao
            figura = _endireitada(original, giro_total)
            caixas = _caixas_achadas(motor, figura, escala)
            if not caixas:
                return [], 0
        altura, largura = figura.shape[:2]
        giro = _giro_da_pagina(motor, figura, caixas)
        recortes = []
        de_lado = []
        for posicao, cantos in enumerate(caixas):
            recorte = np.rot90(_recorte(figura, cantos), k=-(giro // 90))
            if recorte.shape[0] >= PROPORCAO_DE_CAIXA_DE_LADO * recorte.shape[1]:
                recorte = np.rot90(recorte)
                de_lado.append(posicao)
            recortes.append(np.ascontiguousarray(recorte))
        if de_lado:
            desviradas, _classes, _tempo = motor.text_cls([recortes[posicao] for posicao in de_lado])
            for posicao, desvirada in zip(de_lado, desviradas):
                recortes[posicao] = np.ascontiguousarray(desvirada)
        lidos, _tempo = motor.text_rec(recortes)
    linhas = []
    for cantos, (texto, confianca) in zip(caixas, lidos):
        if confianca < CONFIANCA_MINIMA_DA_CAIXA:
            continue
        texto = _FORA_DO_ALFABETO_LATINO.sub("", texto).strip()
        if texto:
            linhas.append((_cantos_na_pagina_em_pe(cantos, giro, largura, altura), texto))
    return linhas, giro


def _texto_das_caixas(linhas_lidas: list) -> str:
    if not linhas_lidas:
        return ""
    deitadas = []
    de_lado = []
    for cantos, texto in linhas_lidas:
        xs = cantos[:, 0]
        ys = cantos[:, 1]
        largura = float(xs.max() - xs.min())
        altura = float(ys.max() - ys.min())
        if altura >= PROPORCAO_DE_CAIXA_DE_LADO * largura and len(texto) > 2:
            de_lado.append(((xs.min() + xs.max()) / 2, texto))
        else:
            deitadas.append(((ys.min() + ys.max()) / 2, (xs.min() + xs.max()) / 2, altura, texto))
    linhas = []
    if deitadas:
        deitadas.sort()
        espessuras = sorted(espessura for _y, _x, espessura, _texto in deitadas)
        tolerancia = FRACAO_DA_MESMA_LINHA * espessuras[len(espessuras) // 2]
        linha_atual = []
        inicio_da_linha = None
        for centro_y, centro_x, _espessura, texto in deitadas:
            if inicio_da_linha is not None and centro_y - inicio_da_linha > tolerancia:
                linhas.append(linha_atual)
                linha_atual = []
                inicio_da_linha = None
            if inicio_da_linha is None:
                inicio_da_linha = centro_y
            linha_atual.append((centro_x, texto))
        linhas.append(linha_atual)
    textos = []
    for linha in linhas:
        linha.sort()
        textos.append(" ".join(texto for _posicao, texto in linha))
    textos.extend(texto for _x, texto in sorted(de_lado))
    return "\n".join(textos)


def _imagem_preparada(imagem: Image.Image) -> Image.Image:
    em_pe = ImageOps.exif_transpose(imagem)
    cinza = em_pe.convert("L")
    maior_lado = max(cinza.size)
    if maior_lado > LADO_MAXIMO_PARA_LER:
        escala = LADO_MAXIMO_PARA_LER / maior_lado
        cinza = cinza.resize((round(cinza.width * escala), round(cinza.height * escala)), Image.LANCZOS)
    elif maior_lado < LADO_MINIMO_PARA_LER:
        cinza = cinza.resize((cinza.width * 2, cinza.height * 2), Image.LANCZOS)
    return ImageOps.autocontrast(cinza)


def _paginas_do_pdf(caminho: Path) -> tuple[str, list[Image.Image]]:
    import pypdfium2 as pdfium

    textos = []
    imagens = []
    with _TRAVA_PDFIUM:
        documento = pdfium.PdfDocument(str(caminho))
        try:
            for indice in range(min(len(documento), PAGINAS_LIDAS)):
                pagina = documento[indice]
                try:
                    pagina_de_texto = pagina.get_textpage()
                    textos.append(pagina_de_texto.get_text_range())
                    pagina_de_texto.close()
                    desenho = pagina.render(scale=DPI_DO_PDF / 72, grayscale=True)
                    imagens.append(desenho.to_pil().copy())
                    desenho.close()
                finally:
                    pagina.close()
        finally:
            documento.close()
    return "\n".join(textos), imagens


def _codigos_de_barra(imagem: Image.Image) -> list[str]:
    if ler_codigos_de_barra is None:
        return []
    try:
        achados = ler_codigos_de_barra(imagem, symbols=SIMBOLOS_LIDOS)
        if not achados and max(imagem.size) <= LADO_MAXIMO_PARA_AMPLIAR:
            ampliada = imagem.resize((imagem.width * 2, imagem.height * 2), Image.LANCZOS)
            achados = ler_codigos_de_barra(ampliada, symbols=SIMBOLOS_LIDOS)
    except Exception as erro:
        logger.warning(f"Leitura local: código de barras não lido -- {erro}")
        return []
    codigos = []
    for achado in achados:
        conteudo = achado.data.decode("utf-8", "replace").strip()
        if conteudo and conteudo not in codigos:
            codigos.append(conteudo)
    return codigos


def _so_digitos(texto) -> str:
    return "".join(caractere for caractere in str(texto or "") if caractere.isdigit())


def _dv_modulo_11(corpo: str) -> int:
    soma = 0
    peso = 2
    for digito in reversed(corpo):
        soma += int(digito) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def cpf_valido(digitos: str) -> bool:
    if len(digitos) != 11 or digitos == digitos[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = 0
        for posicao in range(tamanho):
            soma += int(digitos[posicao]) * (tamanho + 1 - posicao)
        if (soma * 10) % 11 % 10 != int(digitos[tamanho]):
            return False
    return True


def chave_valida(digitos: str) -> bool:
    return len(digitos) == 44 and _dv_modulo_11(digitos[:43]) == int(digitos[43])


def rg_da_etiqueta_valido(digitos: str) -> bool:
    return len(digitos) == 14 and _dv_modulo_11(digitos[:13]) == int(digitos[13])


_PADRAO_CPF = re.compile(r"(?<!\d)\d{3}[.,\s]?\d{3}[.,\s]?\d{3}\s?[-.\s]?\s?\d{2}(?!\d)")
_PADRAO_CPF_PONTUADO = re.compile(r"(?<!\d)\d{3}[.,]\d{3}[.,]\d{3}\s?-\s?\d{2}")
_PADRAO_CHAVE = re.compile(r"(?<!\d)(?:\d{4}\s?){10}\d{4}(?!\d)")
_PADRAO_RG_ETIQUETA = re.compile(r"(?<!\d)\d{13}\s?[-.]?\s?\d(?!\d)")


def _numeros_validos(texto: str, padrao: re.Pattern, valido) -> list[str]:
    numeros = []
    for achado in padrao.finditer(texto):
        digitos = _so_digitos(achado.group(0))
        if valido(digitos) and digitos not in numeros:
            numeros.append(digitos)
    return numeros


def sem_acento_maiusculo(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    return sem_acento.upper()


def texto_comparavel(texto) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", sem_acento_maiusculo(texto)).strip()


def texto_colado(texto) -> str:
    return re.sub(r"[^A-Z0-9]+", "", sem_acento_maiusculo(texto))


LETRAS_DO_SINAL_LONGO = 8
PARECIDO_DO_SINAL_LONGO = 88


def _tem_sinal(texto_de_busca: str, texto_sem_espaco: str, sinal: str) -> bool:
    if f" {texto_comparavel(sinal)} " in texto_de_busca:
        return True
    sinal_colado = texto_colado(sinal)
    if len(sinal_colado) < LETRAS_DO_SINAL_LONGO:
        return False
    if sinal_colado in texto_sem_espaco:
        return True
    return fuzz.partial_ratio(sinal_colado, texto_sem_espaco, score_cutoff=PARECIDO_DO_SINAL_LONGO) > 0


SINAIS_POR_TIPO = {
    "identidade": (
        "HABILITACAO",
        "CARTEIRA DE IDENTIDADE",
        "REGISTRO GERAL",
        "IDENTIFICACAO CIVIL",
        "INSTITUTO DE IDENTIFICACAO",
        "SEGURANCA PUBLICA",
        "DEPARTAMENTO NACIONAL DE TRANSITO",
        "SENATRAN",
        "DENATRAN",
        "DETRAN",
        "FILIACAO",
        "NATURALIDADE",
        "DATA DE NASCIMENTO",
        "DATA NASCIMENTO",
        "ORGAO EMISSOR",
        "DOC IDENTIDADE",
        "REPUBLICA FEDERATIVA DO BRASIL",
        "VALIDA EM TODO O TERRITORIO NACIONAL",
        "PROIBIDO PLASTIFICAR",
        "PRIMEIRA HABILITACAO",
        "MINISTERIO DAS CIDADES",
        "ASSINATURA DO PORTADOR",
        "ASSINATURA DO DIRETOR",
        "DOC ORIGEM",
        "IDENTIDADE NACIONAL",
        "NACIONALIDADE",
        "LOCAL DE NASCIMENTO",
        "CADASTRO DE PESSOAS FISICAS",
        "RECEITA FEDERAL",
        "MINISTERIO DA FAZENDA",
    ),
    "termo_comodato": (
        "COMODATO",
        "COMODATANTE",
        "COMODANTE",
        "COMODATARIA",
        "COMODATARIO",
        "TERMO DE RESPONSABILIDADE",
        "EMPRESTIMO",
        "CLAUSULA",
    ),
    "canhoto_nfe": (
        "DANFE",
        "DOCUMENTO AUXILIAR DA NOTA FISCAL",
        "RECEBEMOS DE",
        "DATA DE RECEBIMENTO",
        "ASSINATURA DO RECEBEDOR",
        "CHAVE DE ACESSO",
        "PROTOCOLO DE AUTORIZACAO",
        "NATUREZA DA OPERACAO",
        "DESTINATARIO",
        "NOTA FISCAL ELETRONICA",
        "COMPROVANTE DE ENTREGA",
        "COMPROVANTE DE RECEBIMENTO",
        "CALCULO DO IMPOSTO",
        "TRANSPORTADOR",
    ),
    "etiqueta_equipamento": (
        "REFRIGERADOR",
        "CONSERVADOR",
        "FREEZER",
        "CERVEJEIRA",
        "EXPOSITOR",
        "GAS REFRIGERANTE",
        "FLUIDO REFRIGERANTE",
        "TENSAO",
        "FREQUENCIA",
        "POTENCIA",
        "CORRENTE NOMINAL",
        "CLASSE CLIMATICA",
        "METALFRIO",
        "MERCOFRICON",
        "FRICON",
        "IMBERA",
        "GELOPAR",
        "ELETROFRIO",
        "VENAX",
    ),
    "plaqueta_patrimonio": ("PATRIMONIO",),
}

ROTULO_POR_TIPO = {
    "identidade": "Documento de identidade (RG ou CNH)",
    "termo_comodato": "Termo de Responsabilidade por Empréstimo / Contrato de Comodato",
    "canhoto_nfe": "Canhoto / DANFE - Documento Auxiliar da Nota Fiscal Eletrônica",
    "etiqueta_equipamento": "Etiqueta de Equipamento",
    "plaqueta_patrimonio": "Plaqueta de Patrimônio",
}

DOCUMENTOS_COM_NOME = {
    "Título de eleitor": ("TITULO ELEITORAL", "TITULO DE ELEITOR", "JUSTICA ELEITORAL", "NOME DO ELEITOR"),
    "Cartão CNPJ": ("CADASTRO NACIONAL DA PESSOA JURIDICA", "SITUACAO CADASTRAL", "NOME EMPRESARIAL"),
    "CRLV": ("CERTIFICADO DE REGISTRO E LICENCIAMENTO", "RENAVAM", "PLACA ANTERIOR"),
    "Certificado militar": ("SERVICO MILITAR", "RESERVISTA", "CERTIFICADO DE DISPENSA", "JUNTA DE SERVICO"),
    "Comprovante de endereço": (
        "UNIDADE CONSUMIDORA",
        "LEITURA ANTERIOR",
        "LEITURA ATUAL",
        "CONTA DE ENERGIA",
        "COMPROVANTE DE RESIDENCIA",
        "COMPROVANTE DE ENDERECO",
        "HIDROMETRO",
    ),
}

PESO_DO_NUMERO_CONFERIDO = 3
PESO_DO_SINAL_DE_DOCUMENTO_COM_NOME = 3

MINIMO_PARA_OUTRO_TIPO = 2

_PATRIMONIO = re.compile(r"\b(?:CP\s?\d\s?)?HNKM\s?\d{5,}")


ARQUIVO_DO_APRENDIZADO = Path(__file__).resolve().parents[3] / "data" / "leituras" / "aprendizado_comodato.json"
PALAVRAS_APRENDIDAS_POR_PONTO = 2
PONTOS_APRENDIDOS_NO_MAXIMO = 3
LETRAS_MINIMAS_DA_PALAVRA = 5
_aprendizado_em_cache: dict = {}


def palavras_do_texto(texto) -> set[str]:
    return {
        palavra
        for palavra in texto_comparavel(texto).split()
        if len(palavra) >= LETRAS_MINIMAS_DA_PALAVRA and palavra.isalpha()
    }


def sinais_aprendidos() -> dict[str, list[str]]:
    try:
        marca = ARQUIVO_DO_APRENDIZADO.stat().st_mtime_ns
    except OSError:
        return {}
    if _aprendizado_em_cache.get("marca") != marca:
        try:
            gravado = json.loads(ARQUIVO_DO_APRENDIZADO.read_text(encoding="utf-8"))
            _aprendizado_em_cache.update(marca=marca, sinais=dict(gravado.get("sinais") or {}))
        except (OSError, ValueError, AttributeError) as erro:
            logger.warning(f"Leitura local: aprendizado ilegível, segue sem ele -- {erro}")
            return {}
    return _aprendizado_em_cache["sinais"]


def _sinais_de_documento_com_nome(texto_de_busca: str, texto_sem_espaco: str) -> dict[str, int]:
    return {
        nome: sum(1 for sinal in sinais if _tem_sinal(texto_de_busca, texto_sem_espaco, sinal))
        for nome, sinais in DOCUMENTOS_COM_NOME.items()
    }


def _pontos_por_tipo(
    texto: str, cpfs: list, chaves: list, rgs_da_etiqueta: list, codigos: list, aprendidos: dict | None = None
) -> dict[str, int]:
    texto_de_busca = f" {texto_comparavel(texto)} "
    texto_sem_espaco = texto_colado(texto)
    pontos = {}
    for tipo, sinais in SINAIS_POR_TIPO.items():
        pontos[tipo] = 0
        for sinal in sinais:
            if _tem_sinal(texto_de_busca, texto_sem_espaco, sinal):
                pontos[tipo] += 1
    aprendidos = sinais_aprendidos() if aprendidos is None else aprendidos
    if aprendidos:
        palavras = palavras_do_texto(texto)
        for tipo, palavras_do_tipo in aprendidos.items():
            if tipo in pontos:
                achadas = len(palavras.intersection(palavras_do_tipo))
                pontos[tipo] += min(achadas // PALAVRAS_APRENDIDAS_POR_PONTO, PONTOS_APRENDIDOS_NO_MAXIMO)
    if chaves:
        pontos["canhoto_nfe"] += PESO_DO_NUMERO_CONFERIDO
    if rgs_da_etiqueta:
        pontos["etiqueta_equipamento"] += PESO_DO_NUMERO_CONFERIDO
    if cpfs:
        pontos["identidade"] += 1
    if _PATRIMONIO.search(sem_acento_maiusculo(texto)):
        pontos["plaqueta_patrimonio"] += 1
    pontos["identidade"] += PESO_DO_SINAL_DE_DOCUMENTO_COM_NOME * max(
        _sinais_de_documento_com_nome(texto_de_busca, texto_sem_espaco).values()
    )
    for codigo in codigos:
        if codigo.isdigit() and 6 <= len(codigo) <= 12 and codigo in texto:
            pontos["plaqueta_patrimonio"] += 1
    return pontos


def tipo_do_documento(pontos: dict[str, int], tipo_esperado: str | None) -> str:
    melhor = max(pontos, key=pontos.get)
    if tipo_esperado in pontos and pontos[tipo_esperado] >= 1 and pontos[tipo_esperado] >= pontos[melhor]:
        return tipo_esperado
    if pontos[melhor] >= MINIMO_PARA_OUTRO_TIPO:
        return melhor
    if pontos[melhor] == 1 and not tipo_esperado:
        return melhor
    return ""


_PALAVRAS_DO_ROTULO_DO_NOME = {"NOME", "E", "SOBRENOME", "NAME", "SURNAME"}
_PALAVRAS_DE_OUTRO_ROTULO = {
    "DATA",
    "CPF",
    "DOC",
    "DOCTO",
    "IDENTIDADE",
    "NASCIMENTO",
    "FILIACAO",
    "ASSINATURA",
    "ORG",
    "ORGAO",
    "EMISSOR",
    "UF",
    "CATEGORIA",
    "VALIDADE",
    "HABILITACAO",
    "PERMISSAO",
    "REGISTRO",
    "GERAL",
    "NACIONAL",
    "CARTEIRA",
    "REPUBLICA",
    "FEDERATIVA",
    "BRASIL",
    "MINISTERIO",
    "DEPARTAMENTO",
    "TRANSITO",
    "LOCAL",
    "EMISSAO",
    "EXPEDICAO",
    "NATURALIDADE",
    "SECRETARIA",
    "ESTADO",
    "SOCIAL",
    "OBSERVACOES",
    "INSTITUTO",
    "IDENTIFICACAO",
    "SEGURANCA",
    "PUBLICA",
    "GOVERNO",
    "POLICIA",
    "CIVIL",
    "DIRETOR",
    "RECEITA",
    "FEDERAL",
    "FAZENDA",
    "CADASTRO",
    "PESSOAS",
    "FISICAS",
    "INSCRICAO",
    "NUMERO",
    "COMPROVANTE",
    "CIDADES",
    "TERRITORIO",
    "VALIDA",
    "PROIBIDO",
    "PLASTIFICAR",
    "NACIONALIDADE",
    "SEXO",
    "DOCUMENTO",
    "TITULAR",
    "PORTADOR",
    "CONTROLE",
    "CODIGO",
    "AUTENTICIDADE",
    "DETRAN",
    "ORIGEM",
    "VIA",
    "NOME",
    "SOBRENOME",
    "POLEGAR",
    "DIREITO",
    "ESQUERDO",
    "DIGITAL",
    "PERICIAS",
    "ACC",
    "CAT",
    "HAB",
    "NAO",
    "DIRETORIA",
    "INFRAESTRUTURA",
    "TRANSPORTES",
    "DRIVER",
    "LICENSE",
    "PERMISO",
    "CONDUCCION",
    "CONFORMIDADE",
    "PROVISORIA",
    "CERTIFICADO",
    "ASSINADO",
    "ELEITOR",
    "ELEITORAL",
    "ZONA",
    "SEC",
    "SECAO",
    "CTPS",
    "SERIE",
    "NIS",
    "PIS",
    "PASEP",
    "CNS",
    "MILITAR",
    "CERT",
    "PROFISSIONAL",
    "DNI",
    "NASC",
    "LIV",
    "FLS",
    "OFC",
    "EMPRESARIAL",
    "FANTASIA",
    "ESTABELECIMENTO",
    "VEICULO",
    "SEGURO",
    "DPVAT",
    "INFORMACOES",
}
_SOBRENOMES_IMPRESSOS = ("GUMBLETON",)
PARECIDO_COM_O_SOBRENOME_IMPRESSO = 80
_SIGLAS_DOS_ESTADOS = {
    "AC",
    "AL",
    "AP",
    "AM",
    "BA",
    "CE",
    "DF",
    "ES",
    "GO",
    "MA",
    "MT",
    "MS",
    "MG",
    "PA",
    "PB",
    "PR",
    "PE",
    "PI",
    "RJ",
    "RN",
    "RS",
    "RO",
    "RR",
    "SC",
    "SP",
    "SE",
    "TO",
}
_ROTULOS_QUE_A_FOTO_BORRA = (
    "IDENTIDADE",
    "EMISSOR",
    "FILIACAO",
    "EXPEDICAO",
    "NATURALIDADE",
    "ASSINATURA",
    "HABILITACAO",
    "PERMISSAO",
    "VALIDADE",
    "CATEGORIA",
    "PLASTIFICAR",
    "IDENTIFICACAO",
    "REGISTRO",
    "DEPARTAMENTO",
    "SECRETARIA",
    "SEGURANCA",
    "INSTITUTO",
    "TERRITORIO",
    "NACIONAL",
    "REPUBLICA",
    "FEDERATIVA",
    "MINISTERIO",
    "OBSERVACOES",
    "DOCUMENTO",
    "PORTADOR",
    "TITULAR",
    "INSCRICAO",
    "COMPROVANTE",
    "AUTENTICIDADE",
    "DIRETORIA",
    "SOBRENOME",
    "INFRAESTRUTURA",
    "TRANSPORTES",
    "CONFORMIDADE",
)
PARECIDO_COM_O_ROTULO_BORRADO = 85
LETRAS_MINIMAS_DO_ROTULO_BORRADO = 6
PARECIDO_COM_O_ROTULO_BORRADO_COLADO = 90
LETRAS_MINIMAS_DO_ROTULO_BORRADO_COLADO = 8
_SOBRAS_NA_PONTA = {"AO", "NAO", "LTDA", "ME", "EPP", "EIRELI"}
_LINHA_DE_PARENTE = ("PAI", "MAE", "FILIACAO", "SOCIAL")
_ROTULO_DO_NOME = re.compile(r"^(?:\d+ )?(?:NOME(?: ?E ?SOBRENOME)? ?|NOM[A-Z]{0,2} )(?=[A-Z])")


PARECIDO_COM_O_ROTULO = 75


def _e_o_rotulo(palavra: str, rotulo: str) -> bool:
    for tamanho in (len(rotulo) - 1, len(rotulo), len(rotulo) + 1):
        if fuzz.ratio(palavra[:tamanho], rotulo, score_cutoff=PARECIDO_COM_O_ROTULO) > 0:
            return True
    return False


def _linha_de_parente(comparavel: str) -> bool:
    palavras = comparavel.split()
    if any(palavra in ("PAI", "MAE") for palavra in palavras):
        return True
    return any(palavra.startswith("SOCIAL") or _e_o_rotulo(palavra, "FILIACAO") for palavra in palavras)


LETRAS_DO_NOME_COLADO = 10
LETRAS_DO_ROTULO_GRUDADO = 6
LETRAS_MINIMAS_DO_NOME = 8
DIGITOS_DE_LINHA_SEM_NOME = 4
LETRAS_MAXIMAS_DO_SOBRENOME_QUE_DESCE = 10
_CONECTORES_DO_NOME = {"DA", "DE", "DO", "DAS", "DOS", "E"}
_ESTADOS_QUE_PARECEM_NOME = {
    "RIO JANEIRO",
    "SAO PAULO",
    "MINAS GERAIS",
    "RIO GRANDE NORTE",
    "RIO GRANDE SUL",
    "ESPIRITO SANTO",
    "MATO GROSSO",
    "MATO GROSSO SUL",
    "SANTA CATARINA",
}


_ROTULOS_QUE_SAO_SOBRENOME = {"NASCIMENTO", "BRASIL", "FAZENDA"}
_ROTULOS_COLADOS = ("DATANASCIMENTO", "DATADENASCIMENTO")
PARECIDO_COM_O_ROTULO_COLADO = 80


_FRASES_DO_CABECALHO = (
    "REPUBLICAFEDERATIVADOBRASILVALIDAEMTODOOTERRITORIONACIONAL",
    "REGISTROGERAL",
    "REGISTRODATADEEXPEDICAO",
    "DATADEEXPEDICAO",
    "INSTITUTOGERALDEPERICIAS",
    "CARTEIRADEIDENTIDADE",
    "CARTEIRANACIONALDEHABILITACAO",
    "DEPARTAMENTONACIONALDETRANSITO",
    "MINISTERIODASCIDADES",
    "SECRETARIADASEGURANCAPUBLICA",
    "RIODEJANEIRO",
    "SAOPAULO",
    "MINASGERAIS",
    "RIOGRANDEDONORTE",
    "RIOGRANDEDOSUL",
    "ESPIRITOSANTO",
    "MATOGROSSODOSUL",
    "SANTACATARINA",
)
_PALAVRAS_DO_CABECALHO = (
    "REPUBLICA",
    "FEDERATIVA",
    "TERRITORIO",
    "NACIONAL",
    "DEPARTAMENTO",
    "MINISTERIO",
    "SECRETARIA",
    "HABILITACAO",
    "IDENTIFICACAO",
    "SEGURANCA",
)
PARECIDO_COM_O_CABECALHO = 80
LETRAS_MINIMAS_PARA_COMPARAR_COM_O_CABECALHO = 6


def _linha_de_cabecalho(linha: str) -> bool:
    colada = texto_colado(linha)
    if len(colada) < LETRAS_MINIMAS_PARA_COMPARAR_COM_O_CABECALHO:
        return False
    for frase in _FRASES_DO_CABECALHO:
        if fuzz.partial_ratio(colada, frase, score_cutoff=PARECIDO_COM_O_CABECALHO) > 0:
            return True
    for palavra in texto_comparavel(linha).split():
        if len(palavra) >= LETRAS_MINIMAS_PARA_COMPARAR_COM_O_CABECALHO and any(
            fuzz.ratio(palavra, cabecalho, score_cutoff=PARECIDO_COM_O_CABECALHO) > 0
            for cabecalho in _PALAVRAS_DO_CABECALHO
        ):
            return True
    return False


def _e_rotulo(palavra: str) -> bool:
    return palavra in _PALAVRAS_DE_OUTRO_ROTULO and palavra not in _ROTULOS_QUE_SAO_SOBRENOME


def _parece_rotulo(palavra: str) -> bool:
    if _e_rotulo(palavra):
        return True
    return len(palavra) >= LETRAS_MINIMAS_DO_ROTULO_BORRADO and any(
        fuzz.ratio(palavra, rotulo, score_cutoff=PARECIDO_COM_O_ROTULO_BORRADO) > 0
        for rotulo in _ROTULOS_QUE_A_FOTO_BORRA
    )


def _sobra_na_ponta(palavra: str) -> bool:
    return (
        _parece_rotulo(palavra)
        or palavra in _PALAVRAS_DO_ROTULO_DO_NOME
        or palavra in _CONECTORES_DO_NOME
        or palavra in _SOBRAS_NA_PONTA
    )


def _tem_rotulo_grudado(palavra: str) -> bool:
    if len(palavra) < LETRAS_DO_NOME_COLADO or palavra in _ROTULOS_QUE_SAO_SOBRENOME:
        return False
    if any(fuzz.ratio(palavra, rotulo, score_cutoff=PARECIDO_COM_O_ROTULO_COLADO) > 0 for rotulo in _ROTULOS_COLADOS):
        return True
    if any(
        len(rotulo) >= LETRAS_MINIMAS_DO_ROTULO_BORRADO_COLADO
        and fuzz.partial_ratio(rotulo, palavra, score_cutoff=PARECIDO_COM_O_ROTULO_BORRADO_COLADO) > 0
        for rotulo in _ROTULOS_QUE_A_FOTO_BORRA
    ):
        return True
    return any(
        len(rotulo) >= LETRAS_DO_ROTULO_GRUDADO and rotulo in palavra
        for rotulo in _PALAVRAS_DE_OUTRO_ROTULO - _ROTULOS_QUE_SAO_SOBRENOME
    )


_DIGITO_NO_LUGAR_DA_LETRA = str.maketrans("10582", "IOSBZ")
LETRAS_PARA_TROCAR_O_DIGITO = 2


def _sem_digito_no_lugar_da_letra(palavra: str) -> str:
    if sum(caractere.isalpha() for caractere in palavra) < LETRAS_PARA_TROCAR_O_DIGITO:
        return palavra
    return palavra.translate(_DIGITO_NO_LUGAR_DA_LETRA)


def _nome_da_linha(linha: str) -> str:
    linha = _DATA.sub(" ", linha)
    if sum(caractere.isdigit() for caractere in linha) >= DIGITOS_DE_LINHA_SEM_NOME:
        return ""
    comparavel = " ".join(_sem_digito_no_lugar_da_letra(palavra) for palavra in texto_comparavel(linha).split())
    if any(
        fuzz.ratio(palavra, impresso, score_cutoff=PARECIDO_COM_O_SOBRENOME_IMPRESSO) > 0
        for palavra in comparavel.split()
        if len(palavra) >= LETRAS_MINIMAS_DO_ROTULO_BORRADO
        for impresso in _SOBRENOMES_IMPRESSOS
    ):
        return ""
    if any(palavra.isdigit() and len(palavra) >= 2 for palavra in comparavel.split()):
        return ""
    rotulo_no_comeco = _ROTULO_DO_NOME.match(comparavel)
    if rotulo_no_comeco:
        comparavel = comparavel[rotulo_no_comeco.end() :]
    palavras = [palavra for palavra in comparavel.split() if palavra.isalpha() and not _tem_rotulo_grudado(palavra)]
    while palavras and _sobra_na_ponta(palavras[0]):
        palavras = palavras[1:]
    while palavras and _sobra_na_ponta(palavras[-1]):
        palavras = palavras[:-1]
    if any(_parece_rotulo(palavra) and palavra not in _PALAVRAS_DO_ROTULO_DO_NOME for palavra in palavras):
        return ""
    if palavras and palavras[-1] in _SIGLAS_DOS_ESTADOS:
        return ""
    inteiras = [
        palavra
        for palavra in palavras
        if len(palavra) >= 3 and palavra not in ("DOS", "DAS") and palavra not in _PALAVRAS_DE_OUTRO_ROTULO
    ]
    letras = sum(len(palavra) for palavra in inteiras)
    if " ".join(inteiras) in _ESTADOS_QUE_PARECEM_NOME or (palavras and _linha_de_cabecalho(" ".join(palavras))):
        return ""
    if (len(inteiras) == 1 and letras >= LETRAS_DO_NOME_COLADO) or (
        len(inteiras) >= 2 and letras >= LETRAS_MINIMAS_DO_NOME
    ):
        return " ".join(palavras)
    sobrenomes = [palavra for palavra in palavras if palavra in _ROTULOS_QUE_SAO_SOBRENOME]
    if inteiras and sobrenomes and letras + sum(len(palavra) for palavra in sobrenomes) >= LETRAS_MINIMAS_DO_NOME:
        return " ".join(palavras)
    return ""


def _e_o_rotulo_do_nome(palavra: str) -> bool:
    return len(palavra) <= 5 and fuzz.ratio(palavra, "NOME", score_cutoff=PARECIDO_COM_O_ROTULO) > 0


def _so_o_rotulo_do_nome(linha: str) -> bool:
    palavras = texto_comparavel(linha).split()
    return len(palavras) == 1 and _e_o_rotulo_do_nome(palavras[0])


def _linha_do_nome_pelo_rotulo(linhas: list[str]) -> tuple[int, str] | None:
    rotulo_sem_nome = None
    for posicao, linha in enumerate(linhas):
        comparavel = texto_comparavel(linha)
        if _linha_de_parente(comparavel):
            continue
        rotulo_no_comeco = _ROTULO_DO_NOME.match(comparavel)
        if rotulo_no_comeco:
            depois_do_rotulo = comparavel[rotulo_no_comeco.end() :]
            rotulo_firme = True
        else:
            palavras = comparavel.split()
            posicao_do_rotulo = next(
                (
                    posicao_da_palavra
                    for posicao_da_palavra, palavra in enumerate(palavras)
                    if _e_o_rotulo_do_nome(palavra)
                ),
                None,
            )
            if posicao_do_rotulo is None:
                continue
            depois_do_rotulo = " ".join(palavras[posicao_do_rotulo + 1 :])
            rotulo_firme = len(palavras) == 1 or palavras[posicao_do_rotulo] in ("NOME", "NOM")
        candidatas = [(posicao, depois_do_rotulo)]
        if posicao + 1 < len(linhas):
            candidatas.append((posicao + 1, linhas[posicao + 1]))
        if posicao > 0:
            candidatas.append((posicao - 1, linhas[posicao - 1]))
        for posicao_do_nome, candidata in candidatas:
            nome = _nome_da_linha(candidata)
            if nome:
                return posicao_do_nome, nome
        if rotulo_sem_nome is None and rotulo_firme:
            rotulo_sem_nome = (posicao, "")
    return rotulo_sem_nome


_PEDACOS_DO_CABECALHO_DA_CNH = ("HABILITAC",)
_PEDACOS_DO_ROTULO_DE_IDENTIDADE = ("EMISSOR", "DOCIDENT")


def _linha_do_nome_na_cnh(linhas: list[str]) -> tuple[int, str] | None:
    for posicao, linha in enumerate(linhas):
        colada = texto_colado(linha)
        if any(pedaco in colada for pedaco in _PEDACOS_DO_ROTULO_DE_IDENTIDADE) and posicao > 0:
            nome = _nome_da_linha(linhas[posicao - 1])
            if nome:
                return posicao - 1, nome
        if any(pedaco in colada for pedaco in _PEDACOS_DO_CABECALHO_DA_CNH) and posicao + 1 < len(linhas):
            nome = _nome_da_linha(linhas[posicao + 1])
            if nome:
                return posicao + 1, nome
    return None


DIGITOS_DO_NUMERO_DO_DOCUMENTO = 6
_DATA = re.compile(r"\d{1,2}\s?[/.-]\s?\d{1,2}\s?[/.-]\s?\d{2,4}")


def _digitos_fora_das_datas(linha: str) -> int:
    return sum(caractere.isdigit() for caractere in _DATA.sub(" ", linha))


def _linha_do_nome_pela_ordem(linhas: list[str], e_cnh: bool, e_rg: bool) -> tuple[int, str] | None:
    parentes = next(
        (posicao for posicao, linha in enumerate(linhas) if _linha_de_parente(texto_comparavel(linha))), len(linhas)
    )
    nomes = [_nome_da_linha(linha) for linha in linhas[:parentes]]
    if e_rg and not e_cnh:
        depois_de_um_numero = False
        for posicao, nome in enumerate(nomes):
            if depois_de_um_numero and nome:
                return posicao, nome
            if _digitos_fora_das_datas(linhas[posicao]) >= DIGITOS_DO_NUMERO_DO_DOCUMENTO:
                depois_de_um_numero = True
        return None
    primeiro_numero = next(
        (
            posicao
            for posicao, linha in enumerate(linhas[:parentes])
            if sum(caractere.isdigit() for caractere in linha) >= DIGITOS_DO_NUMERO_DO_DOCUMENTO
        ),
        None,
    )
    if primeiro_numero is not None:
        numero_e_o_cpf = bool(_numeros_validos(linhas[primeiro_numero], _PADRAO_CPF, cpf_valido))
        antes_do_numero = [] if numero_e_o_cpf else [posicao for posicao in range(primeiro_numero) if nomes[posicao]]
        if antes_do_numero:
            return antes_do_numero[-1], " ".join(nomes[posicao] for posicao in antes_do_numero)
        if e_cnh:
            return None
        numero_do_documento = next(
            (
                posicao
                for posicao in range(primeiro_numero, len(nomes))
                if _digitos_fora_das_datas(linhas[posicao]) >= DIGITOS_DO_NUMERO_DO_DOCUMENTO
            ),
            None,
        )
        if numero_do_documento is None:
            return None
        for posicao in range(numero_do_documento + 1, len(nomes)):
            if nomes[posicao]:
                return posicao, nomes[posicao]
            if _digitos_fora_das_datas(linhas[posicao]) >= DIGITOS_DO_NUMERO_DO_DOCUMENTO:
                return None
        return None
    for posicao, nome in enumerate(nomes):
        if nome:
            return posicao, nome
    return None


def nome_da_identidade(texto: str) -> str:
    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]
    documento = _documento_de_identidade(texto)
    achado = _linha_do_nome_pelo_rotulo(linhas)
    if achado is not None and not achado[1]:
        return ""
    pelo_rotulo = achado is not None
    if achado is None and documento == "CNH":
        achado = _linha_do_nome_na_cnh(linhas)
    if achado is None:
        texto_de_busca = f" {texto_comparavel(texto)} "
        texto_sem_espaco = texto_colado(texto)
        e_cnh = any(_tem_sinal(texto_de_busca, texto_sem_espaco, sinal) for sinal in _SINAIS_SO_DA_CNH)
        e_rg = any(_tem_sinal(texto_de_busca, texto_sem_espaco, sinal) for sinal in _SINAIS_SO_DO_RG)
        campos_do_verso = sum(1 for campo in _CAMPOS_DO_VERSO_DO_RG_NOVO if f" {campo} " in texto_de_busca)
        if e_rg and not e_cnh and campos_do_verso >= CAMPOS_PARA_SER_O_VERSO_DO_RG_NOVO:
            return ""
        achado = _linha_do_nome_pela_ordem(linhas, e_cnh, e_rg)
    if achado is None:
        return ""
    posicao, nome = achado
    sobrenome = _sobrenome_que_desceu(linhas[posicao + 1 : posicao + 3], pelo_rotulo)
    return f"{nome} {sobrenome}" if sobrenome else nome


_SINAIS_SO_DA_CNH = ("HABILITACAO", "DEPARTAMENTO NACIONAL DE TRANSITO", "PERMISSAO", "DOC IDENTIDADE")
_SINAIS_SO_DO_RG = (
    "REGISTRO GERAL",
    "CARTEIRA DE IDENTIDADE",
    "DOC ORIGEM",
    "ASSINATURA DO DIRETOR",
    "INSTITUTO DE IDENTIFICACAO",
    "7116 DE 29",
)
_CAMPOS_DO_VERSO_DO_RG_NOVO = ("CTPS", "PASEP", "CNS", "T ELEITOR", "CERT MILITAR")
CAMPOS_PARA_SER_O_VERSO_DO_RG_NOVO = 2


def _sobrenome_que_desceu(seguintes: list[str], pelo_rotulo: bool) -> str:
    if not seguintes:
        return ""
    rotulo_no_meio = pelo_rotulo and len(seguintes) == 2 and _so_o_rotulo_do_nome(seguintes[0])
    candidata = seguintes[1] if rotulo_no_meio else seguintes[0]
    palavras = texto_comparavel(candidata).split()
    sobrenome = palavras[-1] if palavras else ""
    conector_antes = len(palavras) == 2 and palavras[0] in _CONECTORES_DO_NOME
    so_a_palavra = len(palavras) == 1 and rotulo_no_meio
    if (
        (conector_antes or so_a_palavra)
        and sobrenome.isalpha()
        and 3 <= len(sobrenome) <= LETRAS_MAXIMAS_DO_SOBRENOME_QUE_DESCE
        and not _parece_rotulo(sobrenome)
        and not _linha_de_parente(sobrenome)
    ):
        return " ".join(palavras)
    return ""


_NUMERO_DO_CEV = re.compile(r"(?:EMPRESTIMO|COMODATO|CEV)\W{0,8}N[^\w\s]?O?\W{0,3}(\d{3,8})(?!\d)")


SINAIS_DO_DOCUMENTO = (
    (
        "CNH",
        ("HABILITACAO", "PROIBIDO PLASTIFICAR", "DEPARTAMENTO NACIONAL DE TRANSITO", "DOC IDENTIDADE", "PERMISSAO"),
    ),
    ("CPF", ("CADASTRO DE PESSOAS FISICAS",)),
)
FRASES_PARA_SER_DOCUMENTO_COM_NOME = 2


def _documento_de_identidade(texto: str) -> str:
    texto_de_busca = f" {texto_comparavel(texto)} "
    texto_sem_espaco = texto_colado(texto)
    if _tem_sinal(texto_de_busca, texto_sem_espaco, "IDENTIDADE NACIONAL"):
        return "CIN"
    if any(_tem_sinal(texto_de_busca, texto_sem_espaco, sinal) for sinal in _SINAIS_SO_DO_RG):
        return "RG"
    com_nome = _sinais_de_documento_com_nome(texto_de_busca, texto_sem_espaco)
    mais_achado = max(com_nome, key=com_nome.get)
    if com_nome[mais_achado] >= FRASES_PARA_SER_DOCUMENTO_COM_NOME:
        return mais_achado
    for documento, sinais in SINAIS_DO_DOCUMENTO:
        if any(_tem_sinal(texto_de_busca, texto_sem_espaco, sinal) for sinal in sinais):
            return documento
    return mais_achado if com_nome[mais_achado] else "RG"


def _campos_da_identidade(texto: str, cpfs: list) -> dict:
    return {
        "nome_completo": nome_da_identidade(texto),
        "cpf": cpfs[0] if cpfs else "",
        "tipo_documento": _documento_de_identidade(texto),
    }


def _campos_do_termo(texto: str) -> dict:
    achado = _NUMERO_DO_CEV.search(sem_acento_maiusculo(texto))
    return {"numero_cev": achado.group(1) if achado else ""}


def _campos_do_canhoto(chaves: list) -> dict:
    if not chaves:
        return {}
    chave = chaves[0]
    return {
        "chave_acesso": chave,
        "numero_nota": str(int(chave[25:34])),
        "cnpj_emitente": chave[6:20],
        "data_emissao": f"{chave[4:6]}/20{chave[2:4]}",
    }


def _campos_da_etiqueta(rgs_da_etiqueta: list, codigos: list) -> dict:
    rg = rgs_da_etiqueta[0] if rgs_da_etiqueta else ""
    codigo_barras = ""
    for codigo in codigos:
        if len(codigo) >= 16 and not chave_valida(codigo):
            codigo_barras = codigo
            break
    return {
        "registro_geral": f"{rg[:13]}-{rg[13]}" if rg else "",
        "codigo_barras": codigo_barras,
    }


def _campos_do_tipo(tipo: str, texto: str, cpfs: list, chaves: list, rgs_da_etiqueta: list, codigos: list) -> dict:
    if tipo == "identidade":
        return _campos_da_identidade(texto, cpfs)
    if tipo == "termo_comodato":
        return _campos_do_termo(texto)
    if tipo == "canhoto_nfe":
        return _campos_do_canhoto(chaves)
    if tipo in ("etiqueta_equipamento", "plaqueta_patrimonio"):
        return _campos_da_etiqueta(rgs_da_etiqueta, codigos)
    return {}


def _numeros_do_texto(texto: str, codigos: list) -> dict:
    texto_e_codigos = texto + "\n" + "\n".join(codigos)
    cpfs = _numeros_validos(texto, _PADRAO_CPF, cpf_valido)
    for cpf in _numeros_validos(texto, _PADRAO_CPF_PONTUADO, cpf_valido):
        if cpf not in cpfs:
            cpfs.append(cpf)
    return {
        "cpfs": cpfs,
        "chaves": _numeros_validos(texto_e_codigos, _PADRAO_CHAVE, chave_valida),
        "rgs_da_etiqueta": _numeros_validos(texto, _PADRAO_RG_ETIQUETA, rg_da_etiqueta_valido),
    }


def _imagem_em_pe(imagem: Image.Image) -> Image.Image:
    em_pe = ImageOps.exif_transpose(imagem)
    maior_lado = max(em_pe.size)
    if maior_lado > LADO_MAXIMO_PARA_LER:
        escala = LADO_MAXIMO_PARA_LER / maior_lado
        em_pe = em_pe.resize((round(em_pe.width * escala), round(em_pe.height * escala)), Image.LANCZOS)
    return em_pe


def _ler_imagens(imagens: list[Image.Image], motor: str) -> tuple[str, list[str], str]:
    textos = []
    codigos = []
    for imagem in imagens:
        em_pe = _imagem_em_pe(imagem)
        if motor == "rapidocr":
            linhas_lidas, _giro = _ler_com_rapidocr(em_pe)
            textos.append(_texto_das_caixas(linhas_lidas))
        else:
            textos.append(_texto_da_imagem(_imagem_preparada(em_pe)))
        for codigo in _codigos_de_barra(em_pe.convert("L")):
            if codigo not in codigos:
                codigos.append(codigo)
    return "\n".join(textos), codigos, motor


def _ler_imagens_giradas(imagens: list[Image.Image]) -> str:
    textos = []
    alguma_girada = False
    for imagem in imagens:
        preparada = _imagem_preparada(imagem)
        giro = _giro_da_imagem(preparada)
        if giro:
            alguma_girada = True
            preparada = preparada.rotate(-giro, expand=True)
        textos.append(_texto_da_imagem(preparada))
    return "\n".join(textos) if alguma_girada else ""


def _analisar(
    texto: str, codigos: list, tipo_esperado: str | None, aprendidos: dict | None = None
) -> tuple[str, dict, dict]:
    numeros = _numeros_do_texto(texto, codigos)
    pontos = _pontos_por_tipo(
        texto, numeros["cpfs"], numeros["chaves"], numeros["rgs_da_etiqueta"], codigos, aprendidos
    )
    return tipo_do_documento(pontos, tipo_esperado), numeros, pontos


def tipo_do_texto(texto: str, codigos: list, tipo_esperado: str | None, aprendidos: dict | None = None) -> str:
    return _analisar(texto, codigos, tipo_esperado, aprendidos)[0]


TIPOS_DE_FOLHA_IMPRESSA = ("canhoto_nfe", "termo_comodato")


def _ler_por_ocr(imagens: list[Image.Image], tipo_esperado: str | None) -> tuple:
    if tipo_esperado in TIPOS_DE_FOLHA_IMPRESSA and RapidOCR is not None and not tesseract_indisponivel():
        texto, codigos, motor = _ler_imagens(imagens, "tesseract")
        tipo, numeros, pontos = _analisar(texto, codigos, tipo_esperado)
        if tipo and pontos[tipo] >= MINIMO_PARA_OUTRO_TIPO:
            return texto, codigos, motor, tipo, numeros, pontos
    motor = "rapidocr" if RapidOCR is not None else "tesseract"
    texto, codigos, motor = _ler_imagens(imagens, motor)
    tipo, numeros, pontos = _analisar(texto, codigos, tipo_esperado)
    if not tipo and motor == "tesseract":
        texto_girado = _ler_imagens_giradas(imagens)
        if texto_girado:
            texto = texto + "\n" + texto_girado
            tipo, numeros, pontos = _analisar(texto, codigos, tipo_esperado)
    return texto, codigos, motor, tipo, numeros, pontos


def ler(caminho_arquivo, tipo_esperado: str | None = None) -> dict | None:
    return ler_detalhado(caminho_arquivo, tipo_esperado)["corpo"]


def ler_detalhado(caminho_arquivo, tipo_esperado: str | None = None) -> dict:
    inicio = time.time()
    caminho = Path(caminho_arquivo)
    detalhes = {"corpo": None, "texto": "", "pontos": {}, "motor": "", "segundos": 0.0, "codigos": []}
    motivo = indisponivel()
    if motivo:
        logger.warning(f"Leitura local indisponível -- {motivo}")
        return detalhes
    try:
        texto_do_pdf = ""
        if caminho.suffix.lower() == ".pdf":
            texto_do_pdf, imagens = _paginas_do_pdf(caminho)
        else:
            with Image.open(caminho) as foto:
                foto.load()
                imagens = [foto.copy()]
        if sum(caractere.isalpha() for caractere in texto_do_pdf) >= MINIMO_LETRAS_DO_TEXTO:
            texto = texto_do_pdf
            motor = "texto do pdf"
            codigos = []
            for imagem in imagens:
                codigos.extend(_codigos_de_barra(imagem))
            tipo, numeros, pontos = _analisar(texto, codigos, tipo_esperado)
            if not tipo or (tipo == "identidade" and not numeros["cpfs"]):
                texto_da_imagem, codigos, motor, _tipo, _numeros, _pontos = _ler_por_ocr(imagens, tipo_esperado)
                texto = f"{texto_da_imagem}\n{texto_do_pdf}"
                motor = f"{motor} + texto do pdf"
                tipo, numeros, pontos = _analisar(texto, codigos, tipo_esperado)
        else:
            texto, codigos, motor, tipo, numeros, pontos = _ler_por_ocr(imagens, tipo_esperado)
    except Exception as erro:
        logger.warning(f"Leitura local de {caminho.name} falhou -- {type(erro).__name__}: {erro}")
        return detalhes

    segundos = time.time() - inicio
    detalhes.update({"texto": texto, "pontos": pontos, "motor": motor, "segundos": segundos, "codigos": codigos})
    if not tipo:
        logger.info(f"Leitura local de {caminho.name} ({motor}): nada reconhecido em {segundos:.1f}s ({pontos})")
        return detalhes
    campos = _campos_do_tipo(tipo, texto, numeros["cpfs"], numeros["chaves"], numeros["rgs_da_etiqueta"], codigos)
    campos = {nome: valor for nome, valor in campos.items() if valor not in (None, "")}
    logger.info(f"Leitura local de {caminho.name} ({motor}): {tipo} em {segundos:.1f}s")
    rotulo = ROTULO_POR_TIPO[tipo]
    if tipo == "identidade" and campos.get("tipo_documento"):
        rotulo = f"Documento de identidade ({campos['tipo_documento']})"
    detalhes["corpo"] = {
        "success": True,
        "document_type": rotulo,
        "tipo_normalizado": tipo,
        "tipo_confere": (tipo == tipo_esperado) if tipo_esperado else None,
        "campos": campos,
        "data": {
            "nome_completo": campos.get("nome_completo"),
            "cpf": campos.get("cpf"),
            "numero_rg": campos.get("registro_geral"),
            "campos_adicionais": campos,
        },
        "texto": texto,
        "cpfs": numeros["cpfs"],
        "codigos_de_barra": codigos,
        "pontos": pontos,
        "motor": motor,
    }
    return detalhes


def mostrar_leitura(arquivo: str, tipo_esperado: str | None, mostrar_texto: bool) -> None:
    print(f"\n===== {Path(arquivo).name} =====")
    if not Path(arquivo).is_file():
        print("Arquivo não encontrado.")
        return
    detalhes = ler_detalhado(arquivo, tipo_esperado)
    print(f"lido por {detalhes['motor'] or '-'} em {detalhes['segundos']:.1f}s")
    resultado = detalhes["corpo"]
    if resultado is None:
        print("Nada reconhecido (quem chama trata como serviço fora do ar).")
        print(f"pontos: {detalhes['pontos']}")
    else:
        resultado = dict(resultado)
        resultado.pop("texto")
        for chave, valor in resultado.items():
            print(f"{chave}: {valor}")
    if mostrar_texto:
        print("\n----- texto lido -----\n" + detalhes["texto"])


if __name__ == "__main__":
    import argparse

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argumentos = argparse.ArgumentParser(description="O que a leitura local tira de documentos do comodato.")
    argumentos.add_argument("arquivos", nargs="*")
    argumentos.add_argument("--tipo", choices=list(ROTULO_POR_TIPO), help="o tipo que o campo espera")
    argumentos.add_argument("--texto", action="store_true", help="mostra também o texto lido inteiro")
    lidos = argumentos.parse_args() if "__file__" in globals() else argumentos.parse_args([])
    modelo = "latino" if MODELO_DE_LEITURA.is_file() and ALFABETO_DO_MODELO.is_file() else "de chinês (o latino falta)"
    print("RapidOCR:", ERRO_DO_RAPIDOCR or f"pronto ({NUCLEOS_DO_RAPIDOCR} núcleo, modelo {modelo})")
    print("tesseract (reserva):", executavel_tesseract() or "-", "|", tesseract_indisponivel() or "pronto")
    print("código de barras:", ERRO_DO_LEITOR_DE_BARRAS or "pronto")
    for arquivo in lidos.arquivos:
        mostrar_leitura(arquivo, lidos.tipo, lidos.texto)
    if not lidos.arquivos:
        while True:
            try:
                caminho = input("\nCaminho do arquivo (Enter vazio termina): ").replace("\ufeff", "").strip().strip('"')
            except EOFError:
                print(
                    "\nEste painel não deixa digitar. Rode no terminal (no Code Runner,"
                    ' "code-runner.runInTerminal": true) ou passe o caminho na linha de comando.'
                )
                break
            if not caminho:
                break
            mostrar_leitura(caminho, lidos.tipo, True)
