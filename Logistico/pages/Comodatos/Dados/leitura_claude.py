import base64
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from .funcao_extracao_doc import PASTA_APP, TIMEOUT_SEGUNDOS

MOTOR_CLAUDE = "claude"
MOTOR_EDGE = "edge"

MODELO_PADRAO = "claude-opus-5"

ESFORCO_PADRAO = "low"
ESFORCOS = ("low", "medium", "high", "xhigh", "max")

MAX_TOKENS = 16000

CAMPOS_POR_TIPO: dict[str, dict[str, str]] = {
    "identidade": {
        "nome_completo": "string",
        "cpf": "string",
        "numero_rg": "string",
        "data_nascimento": "string",
        "orgao_emissor": "string",
        "tipo_documento": "string",
    },
    "termo_comodato": {
        "numero_cev": "string",
        "cnpj_cliente": "string",
        "razao_social_cliente": "string",
        "data_documento": "string",
        "tem_assinatura": "boolean",
    },
    "canhoto_nfe": {
        "numero_nota": "string",
        "chave_acesso": "string",
        "cnpj_emitente": "string",
        "cnpj_destinatario": "string",
        "data_emissao": "string",
        "data_recebimento": "string",
        "valor_total": "string",
        "tem_assinatura": "boolean",
    },
    "etiqueta_equipamento": {
        "numero_serie": "string",
        "registro_geral": "string",
        "modelo": "string",
        "codigo_produto": "string",
        "fabricante": "string",
        "marca_bebida": "string",
        "data_fabricacao": "string",
        "codigo_barras": "string",
        "patrimonio": "string",
        "endereco_fabricante": "string",
    },
    "plaqueta_patrimonio": {
        "numero_patrimonio": "string",
        "texto_qr": "string",
    },
}

TIPO_PADRAO = "identidade"

TIPOS_NORMALIZADOS = (*CAMPOS_POR_TIPO, "outro")

ROTULO_POR_TIPO = {
    "identidade": "Documento de identidade (RG ou CNH)",
    "termo_comodato": "Termo de Responsabilidade por Empréstimo / Contrato de Comodato",
    "canhoto_nfe": "Canhoto / DANFE - Documento Auxiliar da Nota Fiscal Eletrônica",
    "etiqueta_equipamento": "Etiqueta de Equipamento",
    "plaqueta_patrimonio": "Plaqueta de Patrimônio",
    "outro": "",
}

INSTRUCOES = """Você lê documentos e etiquetas para um painel de controle de comodato.
Extraia SOMENTE o que está escrito na imagem e responda no formato pedido.

Regras que valem sempre:
- Nunca complete, deduza ou adivinhe valor que não esteja escrito. Prefira null
  a chute: campo vazio a próxima foto preenche, valor errado fica para sempre.
- "fabricante" é a empresa que FABRICOU o equipamento. Nunca endereço, site,
  e-mail, telefone ou CNPJ; o endereço tem campo próprio. Nunca a cervejaria
  patrocinadora (Maré, Coral, Jangada, Farol, Serena, Eisenbahn, Bavaria,
  Kaiser...), mesmo que a etiqueta traga "Grupo MARÉ no Brasil".
- "marca_bebida" é a bebida adesivada no equipamento. Se o que está escrito como
  marca for o nome do fabricante (acontece na Imbera, "MARCA: IMBERA"), devolva
  null em marca_bebida e ponha esse valor em fabricante.
- "numero_serie" é o serial do fabricante. Número com 16 dígitos ou mais é
  código de barras: vai em codigo_barras, e numero_serie fica null.
- "patrimonio" é o controle do dono do parque (começa com HNKM, às vezes com o
  prefixo CP2), nunca o serial do fabricante -- os dois convivem na etiqueta.
- "tipo_normalizado" diz o que o arquivo É DE VERDADE, mesmo que não seja o tipo
  esperado: é com ele que o painel recusa documento anexado no campo errado."""


def motor() -> str:
    load_dotenv(dotenv_path=PASTA_APP / ".env", override=True)
    return (os.getenv("COMODATO_OCR_MOTOR") or MOTOR_EDGE).strip().lower()


def ativo() -> bool:
    return motor() == MOTOR_CLAUDE


def _esforco() -> str:
    escolhido = (os.getenv("COMODATO_OCR_CLAUDE_ESFORCO") or ESFORCO_PADRAO).strip().lower()
    if escolhido not in ESFORCOS:
        logger.warning(
            f'COMODATO_OCR_CLAUDE_ESFORCO="{escolhido}" nao vale --'
            f" usando {ESFORCO_PADRAO}. Valores: {', '.join(ESFORCOS)}."
        )
        return ESFORCO_PADRAO
    return escolhido


def _formato(tipo: str) -> dict:
    propriedades = {"tipo_normalizado": {"type": "string", "enum": list(TIPOS_NORMALIZADOS)}}
    for campo, formato in CAMPOS_POR_TIPO[tipo].items():
        propriedades[campo] = {"type": [formato, "null"]}
    return {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": propriedades,
            "required": list(propriedades),
            "additionalProperties": False,
        },
    }


def ler(caminho_imagem: str, tipo_mime: str, tipo_esperado: str | None = None) -> dict | None:
    try:
        import anthropic
    except ImportError:
        logger.warning(
            'COMODATO_OCR_MOTOR=claude, mas a biblioteca "anthropic" nao esta'
            " instalada (pip install anthropic) -- leitura fora do ar."
        )
        return None

    chave = os.getenv("ANTHROPIC_API_KEY")
    if not chave:
        logger.warning("COMODATO_OCR_MOTOR=claude sem ANTHROPIC_API_KEY no .env -- leitura fora do ar.")
        return None

    tipo = tipo_esperado if tipo_esperado in CAMPOS_POR_TIPO else TIPO_PADRAO
    conteudo = base64.b64encode(Path(caminho_imagem).read_bytes()).decode("ascii")
    natureza = "document" if tipo_mime == "application/pdf" else "image"
    pergunta = (
        f"Este arquivo deveria ser: {tipo}."
        " Extraia os campos pedidos e diga em tipo_normalizado o que ele é de"
        " verdade."
    )

    cliente = anthropic.Anthropic(api_key=chave, timeout=float(TIMEOUT_SEGUNDOS), max_retries=0)
    try:
        resposta = cliente.messages.create(
            model=(os.getenv("COMODATO_OCR_CLAUDE_MODELO") or MODELO_PADRAO).strip(),
            max_tokens=MAX_TOKENS,
            system=INSTRUCOES,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": natureza, "source": {"type": "base64", "media_type": tipo_mime, "data": conteudo}},
                        {"type": "text", "text": pergunta},
                    ],
                }
            ],
            output_config={"effort": _esforco(), "format": _formato(tipo)},
        )
    except Exception as exc:
        logger.warning(f"Leitura pelo Claude falhou -- {type(exc).__name__}: {exc}")
        return None

    if resposta.stop_reason == "refusal":
        logger.warning(
            f"Claude recusou ler {Path(caminho_imagem).name} -- {getattr(resposta.stop_details, 'category', None)}"
        )
        return None

    texto = next((bloco.text for bloco in resposta.content if bloco.type == "text"), "")
    try:
        lido = json.loads(texto)
    except ValueError:
        logger.warning(f"Claude respondeu fora do formato pedido (stop_reason={resposta.stop_reason}): {texto[:300]}")
        return None

    normalizado = lido.pop("tipo_normalizado", "") or ""
    campos = {chave_campo: valor for chave_campo, valor in lido.items() if valor not in (None, "")}
    return {
        "success": True,
        "document_type": ROTULO_POR_TIPO.get(normalizado, ""),
        "tipo_normalizado": normalizado,
        "tipo_confere": (normalizado == tipo_esperado) if tipo_esperado else None,
        "campos": campos,
        "data": {
            "nome_completo": campos.get("nome_completo"),
            "cpf": campos.get("cpf"),
            "numero_rg": campos.get("numero_rg") or campos.get("registro_geral"),
            "campos_adicionais": campos,
        },
    }
