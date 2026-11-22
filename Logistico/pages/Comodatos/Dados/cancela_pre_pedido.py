from __future__ import annotations

from datetime import date, datetime

from loguru import logger
from sqlalchemy import text

from core.db import obter_engine_comodato

from .adiciona_pedido import _codigo, _empresa_da_revenda

EXISTE = "existe"
DIVERGENTE = "divergente"
AUSENTE = "ausente"
CANCELADO_NO_ERP = "cancelado"
JA_IMPORTADO = "ja_importado"

EXIGIR_QTD_E_VALOR = True


SIGLA_CANCELAMENTO = "Das"

CANCELADO = 1

_TAMANHO_NUMERO = 12


def numero_plausivel(texto: str) -> bool:
    limpo = str(texto).strip()
    if len(limpo) != _TAMANHO_NUMERO or not limpo.isdigit():
        return False
    try:
        date(int(limpo[:4]), int(limpo[4:6]), int(limpo[6:8]))
    except ValueError:
        return False
    return True


def esperado_do_dash(itens: list[dict], digito: int) -> dict:
    return {
        "nremp": digito,
        "codcli": _codigo(itens[0]["CLIENTE"], "cliente"),
        "dt1vc": _codigo(itens[0]["VENC"], "vencimento"),
        "valor_total": round(sum(float(item["QTD"]) * float(item["PRECO"] or 0) for item in itens), 2),
        "itens": _quantidade_por_item(itens),
    }


def _quantidade_por_item(itens: list[dict]) -> dict:
    somado: dict = {}
    for item in itens:
        chave = (_codigo(item["PRODUTO"], "produto"), _codigo(item["CODCOMP"], "codigo do item"))
        somado[chave] = somado.get(chave, 0) + _codigo(item["QTD"], "quantidade")
    return somado


TOLERANCIA_VENCIMENTO_DIAS = 5


def _para_data(valor) -> date | None:
    texto = str(valor).strip().removesuffix(".0")
    if len(texto) != 8 or not texto.isdigit():
        return None
    try:
        return date(int(texto[:4]), int(texto[4:6]), int(texto[6:8]))
    except ValueError:
        return None


def _vencimento_parecido(no_control, esperado) -> bool:
    data_control, data_esperada = _para_data(no_control), _para_data(esperado)
    if data_control is None or data_esperada is None:
        return str(no_control).strip() == str(esperado).strip()
    return abs((data_control - data_esperada).days) <= TOLERANCIA_VENCIMENTO_DIAS


def aviso_vencimento(esperado: dict, cabecalho: dict | None) -> str | None:
    if not cabecalho:
        return None
    if _vencimento_parecido(cabecalho.get("DT1VC"), esperado.get("dt1vc")):
        return None
    return (
        f"vencimento recalculado pelo ERP (ERP {cabecalho.get('DT1VC')}, "
        f"solicitado {esperado.get('dt1vc')}) -- nao muda o desfecho"
    )


def _pedido_gerado(cabecalho: dict) -> int:
    try:
        return int(float(cabecalho.get("NPED") or 0))
    except (TypeError, ValueError):
        return 0


def avaliar_pedido(esperado: dict, cabecalho: dict | None, itens_control: list[dict]) -> tuple[str, str]:
    if cabecalho is None:
        return AUSENTE, "nenhum pre-pedido com esse numero no ERP"

    ja_gerado = _pedido_gerado(cabecalho)
    if ja_gerado:
        return JA_IMPORTADO, f"o ERP ja gerou o pedido {ja_gerado} a partir dele"

    if int(cabecalho["NREMP"]) != esperado["nremp"]:
        return AUSENTE, f"empresa diferente (ERP {cabecalho['NREMP']}, esperado {esperado['nremp']})"
    if int(cabecalho["CODCLI"]) != esperado["codcli"]:
        return AUSENTE, f"cliente diferente (ERP {cabecalho['CODCLI']}, esperado {esperado['codcli']})"

    no_control: dict[tuple[int, int], int] = {}
    for item in itens_control:
        chave = (int(item["CODR"]), int(item["PROD"]))
        no_control[chave] = no_control.get(chave, 0) + int(item["QTD"])

    faltando = set(esperado["itens"]) - set(no_control)
    if faltando:
        return AUSENTE, f"produto(s) {sorted(faltando)} nao esta(o) no pedido (numero reaproveitado ou item removido)"

    if not EXIGIR_QTD_E_VALOR:
        return EXISTE, "cliente e produtos conferem"

    sobrando = set(no_control) - set(esperado["itens"])
    if sobrando:
        return DIVERGENTE, f"pedido tem produto que a solicitacao nao pediu: {sorted(sobrando)}"
    for chave, quantidade in esperado["itens"].items():
        if no_control[chave] != quantidade:
            return (
                DIVERGENTE,
                f"quantidade do produto {chave[0]} mudou (ERP {no_control[chave]}, solicitado {quantidade})",
            )
    if abs(round(float(cabecalho["VLRTOTAL"]), 2) - esperado["valor_total"]) > 0.01:
        return DIVERGENTE, f"valor total mudou (ERP {cabecalho['VLRTOTAL']}, solicitado {esperado['valor_total']})"

    return EXISTE, "cliente, produtos, quantidades e valor conferem"


def liberar_solicitacao(revenda: str, pre_pedido: str, cliente: str) -> int:
    with obter_engine_comodato().begin() as conexao:
        return conexao.execute(
            text(
                "UPDATE tb_comod_solicitado SET PRE_PED = NULL WHERE "
                "REVENDA = :revenda AND PRE_PED = :pre_ped AND CLIENTE = :cliente"
            ),
            {"revenda": revenda, "pre_ped": pre_pedido, "cliente": cliente},
        ).rowcount


TABELA_ESTADO = "tb_comod_pre_ped_estado"

_SQL_CRIA_ESTADO = f"""
CREATE TABLE IF NOT EXISTS {TABELA_ESTADO} (
    REVENDA      VARCHAR(60)  NOT NULL,
    PRE_PED      VARCHAR(20)  NOT NULL,
    CLIENTE      VARCHAR(120) NOT NULL,
    NPED         VARCHAR(20)  NOT NULL,
    DESFECHO     VARCHAR(20)  NOT NULL,
    CONFERIDO_EM DATETIME     NOT NULL,
    PRIMARY KEY (REVENDA, PRE_PED, CLIENTE)
)
"""
_SQL_GRAVA_ESTADO = f"""
REPLACE INTO {TABELA_ESTADO} (REVENDA, PRE_PED, CLIENTE, NPED, DESFECHO, CONFERIDO_EM)
VALUES (:revenda, :pre_ped, :cliente, :nped, :desfecho, NOW())
"""


def registrar_estado(linhas: list[dict]) -> int:
    if not linhas:
        return 0
    with obter_engine_comodato().begin() as conexao:
        conexao.execute(text(_SQL_CRIA_ESTADO))
        conexao.execute(text(_SQL_GRAVA_ESTADO), linhas)
    return len(linhas)


def pre_pedidos_fechados(revenda: str | None = None) -> set[tuple[str, str, str]]:
    consulta = (
        f"SELECT REVENDA, PRE_PED, CLIENTE FROM {TABELA_ESTADO} "
        f"WHERE (NPED <> '0' OR DESFECHO IN ('nao_encontrado', 'ausente', '{CANCELADO_NO_ERP}'))"
    )
    parametros: dict[str, str] = {}
    if revenda and revenda != "HOLDING":
        consulta += " AND UPPER(REVENDA) = :revenda"
        parametros["revenda"] = revenda.upper()
    try:
        with obter_engine_comodato().connect() as conexao:
            return {
                (str(linha[0]).upper(), str(linha[1]), str(linha[2]))
                for linha in conexao.execute(text(consulta), parametros).all()
            }
    except Exception as exc:
        logger.warning(f"Comodatos: nao deu pra ler o estado dos pre-pedidos -- {exc}")
        return set()


def _ler_pedido(cursor, prefixo: str, numero: int) -> tuple[dict | None, list[dict], int, bool]:
    cursor.execute(
        "SELECT VDPEDCPP_NREMP, VDPEDCPP_CODCLI, VDPEDCPP_DT1VC, VDPEDCPP_VLRTOTAL, "
        "VDPEDCPP_NPED, VDPEDCPP_CANCSN "
        f"FROM {prefixo}VDPEDCPP WHERE VDPEDCPP_PRE_PED = ?",
        numero,
    )
    linhas = cursor.fetchall()
    if not linhas:
        return None, [], 0, False
    linha = linhas[0]
    cabecalho = {
        "NREMP": linha[0],
        "CODCLI": linha[1],
        "DT1VC": linha[2],
        "VLRTOTAL": linha[3],
    }
    try:
        cancelado = int(linha[5] or 0) == CANCELADO
    except (TypeError, ValueError):
        cancelado = False
    try:
        nped = int(float(linha[4] or 0))
    except (TypeError, ValueError):
        nped = 0

    cursor.execute(
        f"SELECT VDPEDIPP_CODR, VDPEDIPP_PROD, VDPEDIPP_QTD FROM {prefixo}VDPEDIPP WHERE VDPEDIPP_PRE_PED = ?",
        numero,
    )
    itens = [{"CODR": linha[0], "PROD": linha[1], "QTD": linha[2]} for linha in cursor.fetchall()]
    return cabecalho, itens, nped, cancelado


def _virou_cev(cursor, prefixo: str, digito: int, nped: int) -> bool:
    if not nped:
        return False
    cursor.execute(f"SELECT COUNT(*) FROM {prefixo}CEVPED0{digito} WHERE VDCEVPEN_NPED = ?", nped)
    return int(cursor.fetchone()[0] or 0) > 0


def _fechar_na_tela(revenda: str, pre_pedido: str, cliente: str, desfecho: str, nped: str = "0") -> None:
    try:
        registrar_estado(
            [
                {
                    "revenda": revenda,
                    "pre_ped": str(pre_pedido).strip(),
                    "cliente": cliente,
                    "nped": str(nped or "0"),
                    "desfecho": desfecho,
                }
            ]
        )
    except Exception as exc:
        logger.warning(f"Cancelamento do pre-pedido {pre_pedido}: estado nao gravado -- {exc}")


def cancelar_pre_pedido(
    revenda: str, pre_pedido: str, itens_solicitacao: list[dict], executar: bool = False
) -> tuple[str, str]:
    if not itens_solicitacao:
        return "nao_encontrado", "nenhuma solicitacao com esse numero no Dash"
    numero_texto = str(pre_pedido).strip()
    if not numero_plausivel(numero_texto):
        return "numero_invalido", f"'{numero_texto}' nao tem cara de numero de pre-pedido"

    empresa = _empresa_da_revenda(revenda)
    if empresa is None:
        raise ValueError(f"Revenda sem configuracao de pedido: {revenda}")

    numero = int(numero_texto)
    esperado = esperado_do_dash(itens_solicitacao, empresa["digito"])
    prefixo = empresa["prefixo"]

    import pyodbc

    conexao = pyodbc.connect(f"DSN={empresa['banco']};charset=utf8mb4", autocommit=False)
    try:
        cursor = conexao.cursor()
        cliente = str(itens_solicitacao[0].get("CLIENTE") or "")
        cabecalho, itens_control, nped, cancelado = _ler_pedido(cursor, prefixo, numero)
        if cabecalho is None:
            _fechar_na_tela(revenda, numero_texto, cliente, AUSENTE)
            return "nao_encontrado", "esse pre-pedido nao esta mais no ERP"
        if cancelado:
            _fechar_na_tela(revenda, numero_texto, cliente, CANCELADO_NO_ERP)
            return "nao_encontrado", "esse pre-pedido ja esta cancelado no ERP"
        if nped or _virou_cev(cursor, prefixo, empresa["digito"], nped):
            _fechar_na_tela(revenda, numero_texto, cliente, EXISTE, nped=str(nped or "1"))
            return "ja_importado", f"o ERP ja gerou o pedido {nped} a partir dele"

        desfecho, motivo = avaliar_pedido(esperado, cabecalho, itens_control)
        if desfecho == AUSENTE:
            return "nao_encontrado", motivo
        if desfecho == DIVERGENTE:
            return "divergente", motivo

        if not executar:
            return "pode_cancelar", f"{motivo}; nada foi cancelado (modo simulado)"

        agora = datetime.now()
        cursor.execute(
            f"UPDATE {prefixo}VDPEDCPP SET VDPEDCPP_CANCDT = ?, VDPEDCPP_CANCHR = ?, "
            "VDPEDCPP_CANCSIGLA = ?, VDPEDCPP_CANCSN = ? WHERE VDPEDCPP_PRE_PED = ?",
            int(agora.strftime("%Y%m%d")),
            int(agora.strftime("%H%M")),
            SIGLA_CANCELAMENTO,
            CANCELADO,
            numero,
        )
        cursor.execute(
            f"SELECT COUNT(*) FROM {prefixo}VDPEDCPP WHERE VDPEDCPP_PRE_PED = ? AND VDPEDCPP_CANCSN = ?",
            numero,
            CANCELADO,
        )
        if int(cursor.fetchone()[0] or 0) != 1:
            raise RuntimeError(f"o pre-pedido {numero} nao ficou marcado como cancelado no ERP")
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()

    _fechar_na_tela(revenda, numero_texto, cliente, CANCELADO_NO_ERP)
    try:
        liberar_solicitacao(revenda, numero_texto, cliente)
    except Exception as exc:
        logger.warning(f"Cancelamento do pre-pedido {numero}: nao deu pra liberar a solicitacao -- {exc}")
        return "cancelado_sem_liberar", (
            f"pre-pedido {numero} cancelado no ERP, mas a solicitacao nao voltou pra pendente -- avise a TI"
        )
    return "cancelado", f"pre-pedido {numero} marcado como cancelado no ERP ({len(itens_control)} item(ns))"
