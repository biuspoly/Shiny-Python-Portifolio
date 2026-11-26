from __future__ import annotations

import contextvars
import functools
import hashlib
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import polars as pl

try:
    from sqlalchemy import bindparam, text
except ImportError:  # portfólio: sem MySQL (core/db.py), o SQL nunca chega a rodar

    def text(sql, *_args, **_kwargs):
        return sql

    def bindparam(*_args, **_kwargs):
        return None


from core.compat import ler_parquet  # noqa: E402

from . import fila_mysql, manual_arquivo
from .db import obter_engine_manual
from .id_titulo import base_do, eh_parte, id_da_parte, numero_da_parte
from .revendas import nome_oficial


def _registrar(acao: str, area: str, **campos) -> None:
    try:
        from . import log_acoes

        log_acoes.registrar(acao, area=area, **campos)
    except Exception:
        pass


def _revenda_oficial(revenda: str | None) -> str | None:
    return nome_oficial(revenda) or revenda


_AGORA: contextvars.ContextVar = contextvars.ContextVar("gravacao_agora", default=None)
_REFAZENDO: contextvars.ContextVar = contextvars.ContextVar("gravacao_refazendo", default=False)
_DURAVEIS: dict = {}


def _agora() -> datetime:
    return _AGORA.get() or datetime.now()


def _hoje() -> date:
    return _agora().date()


def _duravel(provisorio: str | None = None):
    def decorar(funcao):
        @functools.wraps(funcao)
        def envolvida(*args, **kwargs):
            if _AGORA.get() is not None:
                return funcao(*args, **kwargs)
            quando = datetime.now()
            if not fila_mysql.parece_fora() and fila_mysql.tem_pendentes():
                reaplicar_pendentes(compactar=True)
            if fila_mysql.parece_fora() or fila_mysql.tem_pendentes():
                return _na_fila(funcao, provisorio, args, kwargs, quando)
            token = _AGORA.set(quando)
            try:
                return funcao(*args, **kwargs)
            except Exception as erro:
                if not fila_mysql.mysql_fora(erro):
                    raise
                fila_mysql.marcar_fora()
            finally:
                _AGORA.reset(token)
            return _na_fila(funcao, provisorio, args, kwargs, quando)

        _DURAVEIS[funcao.__name__] = funcao
        return envolvida

    return decorar


def _na_fila(funcao, provisorio, args, kwargs, quando):
    resposta, extras = globals()[provisorio](*args, _quando=quando, **kwargs) if provisorio else (None, {})
    fila_mysql.enfileirar(funcao.__name__, list(args), {**kwargs, **extras}, quando)
    _registrar(
        "guardar para o MySQL",
        "mysql",
        descricao=f"{funcao.__name__}: o MySQL não respondeu; a gravação entra quando ele voltar",
    )
    return resposta


def _refazer(registro: dict) -> None:
    funcao = _DURAVEIS[registro["funcao"]]
    hora, refazendo = _AGORA.set(registro["quando"]), _REFAZENDO.set(True)
    try:
        funcao(*registro["args"], **registro["kwargs"])
    finally:
        _AGORA.reset(hora)
        _REFAZENDO.reset(refazendo)


def _avisar_falha(registro: dict, erro: Exception) -> None:
    _registrar(
        "gravação da fila recusada pelo MySQL",
        "mysql",
        descricao=f"{registro['funcao']} de {registro['quando']}: {str(erro)[:300]}",
        depois={"args": registro["args"], "kwargs": registro["kwargs"]},
    )


def reaplicar_pendentes(espera: float = 5.0, compactar: bool = False) -> dict:
    return fila_mysql.reaplicar(_refazer, espera=espera, compactar=compactar, avisar_falha=_avisar_falha)


TIPOS_VISTO = ("assinar", "auditoria", "pagar", "conselho")
ROTULO_VISTO = {"assinar": "Assinar", "auditoria": "Auditoria", "pagar": "Pagar", "conselho": "Gestão"}

PERMISSAO_VISTO = {
    "assinar": "assinar_ppf",
    "auditoria": "auditar_ppf",
    "pagar": "processar_pagamento",
    "conselho": "conselho_ppf",
}

PASTA_ANEXOS = Path(__file__).resolve().parent.parent / "uploads" / "anexos_titulos"


@dataclass
class Overlay:
    vistos: dict = field(default_factory=dict)
    justificativas: dict = field(default_factory=dict)
    excluidos: set = field(default_factory=set)

    def limpar(self) -> None:
        self.vistos.clear()
        self.justificativas.clear()
        self.excluidos.clear()


OVERLAY = Overlay()


_CAMPOS_PARA_COMPLETAR = ("descricao_despesa", "tipo_doc", "num_doc_normalizado")


def _completar_o_titulo(base: dict | None) -> tuple[list[str], dict]:
    valores = {k: (base or {}).get(k) for k in _CAMPOS_PARA_COMPLETAR}
    valores = {f"titulo_{k}": v for k, v in valores.items() if v not in (None, "")}
    return [f"{k[7:]} = COALESCE(NULLIF({k[7:]}, ''), :{k})" for k in valores], valores


@_duravel()
def gravar_pagamento(
    id_unico: str,
    revenda: str,
    *,
    valor_pago=None,
    juros=None,
    banco=None,
    data_pagamento=None,
    base: dict | None = None,
    conexao=None,
) -> None:
    if conexao is None:
        with obter_engine_manual().begin() as nova:
            gravar_pagamento(
                id_unico,
                revenda,
                valor_pago=valor_pago,
                juros=juros,
                banco=banco,
                data_pagamento=data_pagamento,
                base=base,
                conexao=nova,
            )
        return
    agora = _agora()
    campos = {
        "valor_pago": valor_pago,
        "juros": juros,
        "banco": banco,
        "data_pagamento": data_pagamento,
    }
    campos = {k: v for k, v in campos.items() if v is not None}
    if not campos:
        return
    existe = conexao.execute(
        text("SELECT id FROM tb_pagamentos WHERE id_unico = :id"),
        {"id": id_unico},
    ).fetchone()
    if existe:
        completar, do_titulo = _completar_o_titulo(base)
        sets = ", ".join([*(f"{k} = :{k}" for k in campos), *completar])
        conexao.execute(
            text(f"UPDATE tb_pagamentos SET {sets} WHERE id_unico = :id"),
            {**campos, **do_titulo, "id": id_unico},
        )
        return
    linha = {
        "id_unico": id_unico,
        "revenda": _revenda_oficial(revenda),
        "data_registro": agora,
        "entrada_manual": "Não",
        **(base or {}),
        **campos,
    }
    colunas = ", ".join(linha)
    marcas = ", ".join(f":{c}" for c in linha)
    conexao.execute(text(f"INSERT INTO tb_pagamentos ({colunas}) VALUES ({marcas})"), linha)


def id_entrada_manual(
    revenda: str,
    data_vencimento: date,
    num_doc: str,
    cnpj: str,
    razao_social: str,
    tipo_doc: str,
    descricao_despesa: str,
    valor_original: float,
    data_registro: datetime,
) -> str:
    texto = "|".join(
        [
            "manual",
            (revenda or "").strip(),
            data_vencimento.strftime("%Y-%m-%d"),
            (num_doc or "").strip(),
            (cnpj or "").strip(),
            (razao_social or "").strip(),
            (tipo_doc or "").strip(),
            (descricao_despesa or "").strip(),
            f"{float(valor_original):.2f}",
            data_registro.isoformat(timespec="microseconds"),
        ]
    )
    return hashlib.md5(texto.encode("utf-8")).hexdigest()


@_duravel()
def lancar_pagamento_manual(id_unico: str, revenda: str, linha: dict) -> None:
    with obter_engine_manual().begin() as conexao:
        _inserir_manual(conexao, id_unico, revenda, linha)


def _inserir_manual(conexao, id_unico: str, revenda: str, linha: dict) -> None:
    completa = {
        "id_unico": id_unico,
        "revenda": _revenda_oficial(revenda),
        "data_registro": _agora(),
        "data_pagamento": None,
        "valor_pago": 0.0,
        "juros": 0.0,
        "banco": "",
        "pagar": "Não",
        "pagou": "Não",
        "auditoria": "Não",
        "conselho": "Não",
        "entrada_manual": "Sim",
        **linha,
    }
    colunas = ", ".join(completa)
    marcas = ", ".join(f":{c}" for c in completa)
    conexao.execute(text(f"INSERT INTO tb_pagamentos ({colunas}) VALUES ({marcas})"), completa)


class EdicaoRecusada(ValueError):
    """O lancamento manual nao pode mais ser editado (ja' enviado, pago ou dividido)."""


@_duravel("_prov_editar_pagamento_manual")
def editar_pagamento_manual(id_unico: str, revenda: str, linha: dict) -> None:
    with obter_engine_manual().begin() as conexao:
        atual = conexao.execute(
            text("SELECT COALESCE(pagar, ''), COALESCE(pagou, '') FROM tb_pagamentos WHERE id_unico = :id FOR UPDATE"),
            {"id": id_unico},
        ).first()
        if atual is not None and "sim" in (str(atual[0]).strip().lower(), str(atual[1]).strip().lower()):
            raise EdicaoRecusada("este pagamento manual já foi enviado para pagamento")
        partes = conexao.execute(
            text("SELECT 1 FROM tb_pagamentos WHERE id_unico LIKE :p LIMIT 1"),
            {"p": f"{id_unico}\\_clone%"},
        ).first()
        if partes is not None:
            raise EdicaoRecusada("este pagamento manual foi dividido em partes")
        if atual is None:
            _inserir_manual(conexao, id_unico, revenda, linha)
            return
        sets = ", ".join(f"{c} = :{c}" for c in linha)
        conexao.execute(
            text(f"UPDATE tb_pagamentos SET {sets} WHERE id_unico = :id_unico"), {**linha, "id_unico": id_unico}
        )


@_duravel()
def excluir_pagamento_manual(id_unico: str) -> None:
    with obter_engine_manual().begin() as conexao:
        conexao.execute(text("DELETE FROM tb_pagamentos WHERE id_unico = :id"), {"id": id_unico})
        conexao.execute(
            text(
                "DELETE FROM tb_pagamentos WHERE id_unico LIKE :p "
                "AND LOWER(COALESCE(pagar, '')) <> 'sim' AND LOWER(COALESCE(pagou, '')) <> 'sim'"
            ),
            {"p": f"{id_unico}\\_clone%"},
        )
        for tabela, filtro in (
            ("tb_pagamentos_snapshot", "id_unico = :id"),
            ("tb_manual_marcacoes", "id_unico = :id AND tipo = 'pagar'"),
        ):
            try:
                conexao.execute(text(f"DELETE FROM {tabela} WHERE {filtro}"), {"id": id_unico})
            except Exception as erro:
                print(f"gravacao: nao deu pra limpar {tabela} -- {erro}")


@_duravel("_prov_devolver_a_pendente")
def devolver_a_pendente(id_unico: str) -> dict:
    base = base_do(id_unico)
    with obter_engine_manual().begin() as conexao:
        linhas = conexao.execute(
            text(
                "SELECT id_unico, COALESCE(entrada_manual, '') FROM tb_pagamentos "
                "WHERE id_unico = :id OR id_unico = :base OR id_unico LIKE :partes FOR UPDATE"
            ),
            {"id": id_unico, "base": base, "partes": f"{base}\\_clone%"},
        ).fetchall()
        partes = sorted(i for i, _m in linhas if eh_parte(i) and base_do(i) == base)
        manual = any(i == id_unico and str(m).strip().lower() in ("sim", "s", "true", "1") for i, m in linhas)
        tem_base = any(i == base for i, _m in linhas)
        if manual:
            caso, ids = "manual", [id_unico]
            conexao.execute(
                text(
                    "UPDATE tb_pagamentos SET pagar = 'Não', pagou = 'Não', data_pagamento = NULL, "
                    "valor_pago = 0, juros = 0 WHERE id_unico = :id"
                ),
                {"id": id_unico},
            )
        elif partes and tem_base:
            caso, ids = "dividido", [base, *partes]
            conexao.execute(
                text("DELETE FROM tb_pagamentos WHERE id_unico IN :ids").bindparams(bindparam("ids", expanding=True)),
                {"ids": partes},
            )
            conexao.execute(
                text(
                    "UPDATE tb_pagamentos SET pagar = 'Não', pagou = 'Não', conselho = 'Não', "
                    "data_pagamento = NULL, valor_pago = 0, juros = 0, banco = '' "
                    "WHERE id_unico = :base"
                ),
                {"base": base},
            )
        else:
            caso, ids = "comum", [id_unico]
            conexao.execute(text("DELETE FROM tb_pagamentos WHERE id_unico = :id"), {"id": id_unico})
        try:
            conexao.execute(
                text("DELETE FROM tb_pagamentos_snapshot WHERE id_unico IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"ids": ids},
            )
        except Exception as erro:
            print(f"gravacao: nao deu pra limpar tb_pagamentos_snapshot -- {erro}")
    return {"caso": caso, "ids": ids, "partes": partes}


COLUNAS_DADO_MANUAL = (
    "transferencia_bancos",
    "adiantamento_romaneios",
    "devolucao_emprestimos",
    "brinks_antes_16",
    "banco",
    "revenda",
    "destino_transf",
    "data",
    "hora",
    "romaneio_pendente_encerrado",
    "credito_mar_utilizado",
    "tipo_emprestimo_devolucao",
    "entrada_saida",
    "revenda_origem_destino",
    "revenda_destino",
    "transferencia_revendas",
    "credito_parceiro",
)

VALORES_DADO_MANUAL = (
    "transferencia_bancos",
    "adiantamento_romaneios",
    "devolucao_emprestimos",
    "brinks_antes_16",
    "romaneio_pendente_encerrado",
    "credito_mar_utilizado",
    "transferencia_revendas",
)


def id_dado_manual(revenda: str, banco: str, quando: datetime) -> str:
    texto = "|".join(
        ["manual", (revenda or "").strip(), (banco or "").strip(), quando.isoformat(timespec="microseconds")]
    )
    return hashlib.md5(texto.encode("utf-8")).hexdigest()


def _hora_na_coluna(conexao, hora_texto: str):
    tipo = conexao.execute(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = 'tb_dados_manuais' "
            "AND column_name = 'hora'"
        )
    ).scalar()
    if str(tipo or "").lower() in ("time", "varchar", "char", "text"):
        return hora_texto
    h, m, s = (int(x) for x in hora_texto.split(":"))
    return (h * 3600 + m * 60 + s) * 1_000_000_000


BANCO_DO_CAIXA_MANUAL = "Caixa 999"


def _hora_texto(valor) -> str:
    if valor is None:
        return ""
    if hasattr(valor, "total_seconds"):
        segundos = int(valor.total_seconds())
    elif isinstance(valor, (int, float)):
        segundos = int(valor) // 1_000_000_000 if valor > 86_400 else int(valor)
    else:
        return str(valor)[:8]
    return f"{segundos // 3600:02d}:{segundos % 3600 // 60:02d}:{segundos % 60:02d}"


def linhas_do_dia(revenda: str, dia: date, conexao=None) -> list[dict]:
    def _ler(con):
        linhas = (
            con.execute(
                text(f"SELECT {', '.join(COLUNAS_DADO_MANUAL)} FROM tb_dados_manuais WHERE revenda = :r AND data = :d"),
                {"r": revenda, "d": dia},
            )
            .mappings()
            .all()
        )
        fora = []
        for linha in linhas:
            item = dict(linha)
            item["hora"] = _hora_texto(item.get("hora"))
            fora.append(item)
        return fora

    if conexao is not None:
        return _ler(conexao)
    if fila_mysql.parece_fora() or fila_mysql.tem_pendentes():
        return _fatia_do_arquivo(revenda, dia)
    try:
        with obter_engine_manual().connect() as con:
            return _ler(con)
    except Exception as erro:
        if not fila_mysql.mysql_fora(erro):
            raise
        fila_mysql.marcar_fora()
        return _fatia_do_arquivo(revenda, dia)


class _FatiaMySQL:
    def __init__(self, conexao, revenda: str, dia: date, hora_texto: str):
        self.conexao, self.revenda, self.dia = conexao, revenda, dia
        self.hora = _hora_na_coluna(conexao, hora_texto)

    def inserir(self, linha: dict) -> None:
        completa = {c: None for c in COLUNAS_DADO_MANUAL}
        completa.update({c: 0.0 for c in VALORES_DADO_MANUAL})
        completa.update(linha)
        completa.update({"revenda": self.revenda, "data": self.dia, "hora": self.hora})
        completa["id"] = int(
            self.conexao.execute(text("SELECT COALESCE(MAX(id), 0) + 1 FROM tb_dados_manuais")).scalar() or 1
        )
        colunas = ", ".join(completa)
        marcas = ", ".join(f":{c}" for c in completa)
        self.conexao.execute(text(f"INSERT INTO tb_dados_manuais ({colunas}) VALUES ({marcas})"), completa)

    def existente(self, banco_alvo: str):
        return self.conexao.execute(
            text("SELECT id FROM tb_dados_manuais WHERE revenda = :r AND banco = :b AND data = :d ORDER BY id LIMIT 1"),
            {"r": self.revenda, "b": banco_alvo, "d": self.dia},
        ).scalar()

    def atualizar(self, id_linha, valores: dict) -> None:
        if not valores:
            return
        atribuicoes = ", ".join(f"{c} = :{c}" for c in valores)
        self.conexao.execute(
            text(f"UPDATE tb_dados_manuais SET {atribuicoes}, hora = :hora WHERE id = :id"),
            {**valores, "hora": self.hora, "id": id_linha},
        )


class _FatiaArquivo:
    def __init__(self, linhas: list[dict], revenda: str, dia: date, hora_texto: str):
        self.linhas, self.revenda, self.dia, self.hora = [dict(l) for l in linhas], revenda, dia, hora_texto

    def inserir(self, linha: dict) -> None:
        completa = {c: None for c in COLUNAS_DADO_MANUAL}
        completa.update({c: 0.0 for c in VALORES_DADO_MANUAL})
        completa.update(linha)
        completa.update({"revenda": self.revenda, "data": self.dia, "hora": self.hora})
        self.linhas.append(completa)

    def existente(self, banco_alvo: str):
        alvo = str(banco_alvo or "").strip().casefold()
        return next(
            (i for i, l in enumerate(self.linhas) if str(l.get("banco") or "").strip().casefold() == alvo), None
        )

    def atualizar(self, posicao, valores: dict) -> None:
        if valores:
            self.linhas[posicao].update(valores, hora=self.hora)


@_duravel("_prov_salvar_dado_manual")
def salvar_dado_manual(revenda: str, banco: str, quando: datetime, campos: dict) -> list[dict]:
    dia = quando.date()
    with obter_engine_manual().begin() as conexao:
        _aplicar_dado_manual(_FatiaMySQL(conexao, revenda, dia, quando.strftime("%H:%M:%S")), banco, campos)
        return linhas_do_dia(revenda, dia, conexao)


def _aplicar_dado_manual(fatia, banco: str, campos: dict) -> None:
    def _num(nome):
        return float(campos.get(nome) or 0.0)

    def _informados(valores: dict) -> dict:
        return {c: v for c, v in valores.items() if campos.get(c) is not None}

    transferencia = _num("transferencia_bancos")
    emprestimo = _num("devolucao_emprestimos")
    entre_revendas = _num("transferencia_revendas")
    adiantamento = _num("adiantamento_romaneios")
    romaneio = _num("romaneio_pendente_encerrado")
    pix = _num("brinks_antes_16")
    credito_mar = _num("credito_mar_utilizado")
    credito_parceiro = campos.get("credito_parceiro")
    destino_transf = (campos.get("destino_transf") or "").strip()
    banco_destino = (campos.get("banco_destino_transf") or "").strip()
    origem_destino = (campos.get("revenda_origem_destino") or "").strip()
    revenda_destino = (campos.get("revenda_destino") or "").strip()

    no_caixa = banco.strip().casefold() == BANCO_DO_CAIXA_MANUAL.casefold()
    adiantamento_principal = adiantamento if no_caixa else 0.0
    romaneio_principal = romaneio if no_caixa else 0.0

    eh_transferencia = (
        (transferencia > 0 and destino_transf)
        or (emprestimo > 0 and origem_destino)
        or (entre_revendas > 0 and revenda_destino)
    )

    if eh_transferencia:
        destino_final, sentido = "", ""
        if entre_revendas > 0 and banco_destino:
            destino_final = banco_destino
            sentido = campos.get("entrada_saida_transferencia_revendas") or ""
        elif destino_transf:
            destino_final = destino_transf
        if emprestimo > 0 and origem_destino:
            sentido = campos.get("entrada_saida") or ""
        fatia.inserir(
            {
                "transferencia_bancos": transferencia,
                "adiantamento_romaneios": adiantamento_principal,
                "brinks_antes_16": pix,
                "banco": banco,
                "destino_transf": destino_final,
                "romaneio_pendente_encerrado": romaneio_principal,
                "credito_mar_utilizado": credito_mar,
                "credito_parceiro": credito_parceiro,
                "tipo_emprestimo_devolucao": campos.get("tipo_emprestimo_devolucao") or "",
                "entrada_saida": sentido,
                "revenda_origem_destino": origem_destino,
                "devolucao_emprestimos": emprestimo,
                "transferencia_revendas": entre_revendas,
                "revenda_destino": revenda_destino,
            }
        )
    else:
        existente = fatia.existente(banco)
        if existente is not None:
            fatia.atualizar(
                existente,
                _informados(
                    {
                        "brinks_antes_16": pix,
                        "credito_mar_utilizado": credito_mar,
                        "credito_parceiro": credito_parceiro,
                        **(
                            {"adiantamento_romaneios": adiantamento, "romaneio_pendente_encerrado": romaneio}
                            if no_caixa
                            else {}
                        ),
                    }
                ),
            )
        else:
            fatia.inserir(
                {
                    "adiantamento_romaneios": adiantamento_principal,
                    "brinks_antes_16": pix,
                    "romaneio_pendente_encerrado": romaneio_principal,
                    "credito_mar_utilizado": credito_mar,
                    "credito_parceiro": credito_parceiro,
                    "banco": banco,
                    "destino_transf": "",
                    "tipo_emprestimo_devolucao": "",
                    "entrada_saida": "",
                    "revenda_origem_destino": "",
                    "revenda_destino": "",
                }
            )

    romaneios = _informados(
        {
            "adiantamento_romaneios": adiantamento,
            "romaneio_pendente_encerrado": romaneio,
        }
    )
    if romaneios:
        caixa = fatia.existente(BANCO_DO_CAIXA_MANUAL)
        if caixa is not None:
            fatia.atualizar(caixa, romaneios)
        elif any(romaneios.values()):
            fatia.inserir(
                {
                    "adiantamento_romaneios": adiantamento,
                    "romaneio_pendente_encerrado": romaneio,
                    "banco": BANCO_DO_CAIXA_MANUAL,
                    "destino_transf": "",
                    "tipo_emprestimo_devolucao": "",
                    "entrada_saida": "",
                    "revenda_origem_destino": "",
                    "revenda_destino": "",
                }
            )


@_duravel("_prov_excluir_dado_manual")
def excluir_dado_manual(revenda: str, banco: str, dia: date, hora_texto: str) -> int:
    with obter_engine_manual().begin() as conexao:
        hora = _hora_na_coluna(conexao, hora_texto)
        resultado = conexao.execute(
            text("DELETE FROM tb_dados_manuais WHERE revenda = :r AND banco = :b AND data = :d AND hora = :h"),
            {"r": revenda, "b": banco, "d": dia, "h": hora},
        )
        return int(resultado.rowcount or 0)


def lancar_dado_manual(revenda: str, banco: str, quando: datetime, valores: dict) -> None:
    linha = {c: None for c in COLUNAS_DADO_MANUAL}
    linha.update({c: 0.0 for c in VALORES_DADO_MANUAL})
    linha.update({k: v for k, v in valores.items() if k in linha})
    linha["revenda"] = revenda
    linha["banco"] = banco
    linha["data"] = quando.date()
    with obter_engine_manual().begin() as conexao:
        linha["hora"] = _hora_na_coluna(conexao, quando.strftime("%H:%M:%S"))
        proximo = conexao.execute(text("SELECT COALESCE(MAX(id), 0) + 1 FROM tb_dados_manuais")).scalar()
        linha["id"] = int(proximo or 1)
        colunas = ", ".join(linha)
        marcas = ", ".join(f":{c}" for c in linha)
        conexao.execute(text(f"INSERT INTO tb_dados_manuais ({colunas}) VALUES ({marcas})"), linha)


LIMITE_DE_PARTES = 20


def _partes_do_titulo(conexao, base: str) -> dict:
    linhas = conexao.execute(
        text("SELECT id_unico, valor_original FROM tb_pagamentos WHERE id_unico LIKE :p FOR UPDATE"),
        {"p": f"{base}\\_clone%"},
    ).fetchall()
    return {i: v for i, v in linhas if eh_parte(i) and base_do(i) == base}


@_duravel("_prov_dividir_parte")
def dividir_parte(
    id_linha: str,
    revenda: str,
    valor: float,
    banco: str,
    valor_titulo: float,
    campos: dict | None = None,
    usados=(),
    numero: int | None = None,
) -> tuple[str, float]:
    base = base_do(id_linha)
    with obter_engine_manual().begin() as conexao:
        partes = _partes_do_titulo(conexao, base)
        if eh_parte(id_linha):
            if id_linha not in partes:
                raise ValueError("esta parte não existe mais — recarregue a tabela")
            atual = float(partes[id_linha] or 0)
        else:
            atual = float(valor_titulo) - sum(float(v or 0) for v in partes.values())
        atual, valor = round(atual, 2), round(float(valor), 2)
        if not 0 < valor < atual:
            raise ValueError(f"o valor tem de ficar entre zero e {atual:.2f}".replace(".", ","))
        numeros = [numero_da_parte(i) for i in [*partes, *usados] if base_do(i) == base]
        proximo = max(numeros, default=0) + 1
        if numero is not None:
            if id_da_parte(base, int(numero)) in partes:
                raise ValueError(f"a parte {numero} deste título já existe no MySQL")
            proximo = int(numero)
        if proximo > LIMITE_DE_PARTES:
            raise ValueError(f"o título já tem {LIMITE_DE_PARTES} partes")
        resto = round(atual - valor, 2)
        if eh_parte(id_linha):
            conexao.execute(
                text(
                    "UPDATE tb_pagamentos SET valor_pago = :v, valor_original = :v, juros = 0, banco = :b "
                    "WHERE id_unico = :id"
                ),
                {"v": valor, "b": banco, "id": id_linha},
            )
        else:
            gravar_pagamento(id_linha, revenda, valor_pago=valor, juros=0.0, banco=banco, base=campos, conexao=conexao)
        nova = id_da_parte(base, proximo)
        gravar_pagamento(
            nova,
            revenda,
            valor_pago=resto,
            juros=0.0,
            banco=banco,
            base={**(campos or {}), "valor_original": resto},
            conexao=conexao,
        )
    return nova, resto


@_duravel("_prov_desfazer_partes")
def desfazer_partes(
    ids=(),
    base: str | None = None,
    devolver_a_base: bool = True,
) -> tuple[list[str], list[str], dict]:
    ids = [i for i in ids if eh_parte(i)]
    if not ids and not base:
        return [], [], {}
    with obter_engine_manual().begin() as conexao:
        if base:
            linhas = conexao.execute(
                text(
                    "SELECT id_unico, COALESCE(valor_original, valor_pago), COALESCE(pagar, ''), "
                    "COALESCE(pagou, '') FROM tb_pagamentos WHERE id_unico LIKE :p FOR UPDATE"
                ),
                {"p": f"{base}\\_clone%"},
            ).fetchall()
            linhas = [r for r in linhas if eh_parte(r[0]) and base_do(r[0]) == base]
            ids = sorted({*ids, *(r[0] for r in linhas)})
        else:
            linhas = conexao.execute(
                text(
                    "SELECT id_unico, COALESCE(valor_original, valor_pago), COALESCE(pagar, ''), "
                    "COALESCE(pagou, '') FROM tb_pagamentos WHERE id_unico IN :ids FOR UPDATE"
                ).bindparams(bindparam("ids", expanding=True)),
                {"ids": ids},
            ).fetchall()
        recusadas = [i for i, _v, pagar, pagou in linhas if "sim" in (str(pagar).lower(), str(pagou).lower())]
        if devolver_a_base and linhas:
            donos = sorted({base_do(r[0]) for r in linhas})
            enviadas = {
                r[0]
                for r in conexao.execute(
                    text(
                        "SELECT id_unico FROM tb_pagamentos WHERE id_unico IN :ids "
                        "AND 'sim' IN (LOWER(COALESCE(pagar, '')), LOWER(COALESCE(pagou, '')))"
                    ).bindparams(bindparam("ids", expanding=True)),
                    {"ids": donos},
                ).fetchall()
            }
            recusadas += [r[0] for r in linhas if base_do(r[0]) in enviadas and r[0] not in recusadas]
        if recusadas:
            return [], recusadas, {}
        apagar = [(i, v) for i, v, _p, _q in linhas]
        if apagar:
            conexao.execute(
                text("DELETE FROM tb_pagamentos WHERE id_unico IN :ids").bindparams(bindparam("ids", expanding=True)),
                {"ids": [i for i, _v in apagar]},
            )
        pago_da_base = {}
        if devolver_a_base:
            for i, v in apagar:
                conexao.execute(
                    text("UPDATE tb_pagamentos SET valor_pago = COALESCE(valor_pago, 0) + :v WHERE id_unico = :base"),
                    {"v": float(v or 0), "base": base_do(i)},
                )
            for dono in {base_do(i) for i, _v in apagar}:
                valor = conexao.execute(
                    text("SELECT valor_pago FROM tb_pagamentos WHERE id_unico = :id"),
                    {"id": dono},
                ).scalar()
                if valor is not None:
                    pago_da_base[dono] = round(float(valor), 2)
    return list(ids), [], pago_da_base


def atualizar_status_pagamentos(
    conexao, ids: list[str] | None = None, revenda: str | None = None, hoje: date | None = None
) -> set[str]:
    hoje = hoje or _hoje()
    if ids is not None:
        ids = [i for i in dict.fromkeys(ids) if i]
        if not ids:
            return set()
        filtro, parametros = "id_unico IN :ids", {"ids": ids}
    elif revenda:
        filtro, parametros = "revenda = :revenda", {"revenda": revenda}
    else:
        filtro, parametros = "1 = 1", {}

    def _sql(sql: str):
        consulta = text(sql)
        return consulta.bindparams(bindparam("ids", expanding=True)) if ids is not None else consulta

    conexao.execute(
        _sql(
            f"UPDATE tb_pagamentos SET data_pagamento = NULL WHERE {filtro} "
            "AND COALESCE(pagar, '') <> 'Sim' AND data_pagamento IS NOT NULL"
        ),
        parametros,
    )
    conexao.execute(
        _sql(
            f"UPDATE tb_pagamentos SET data_registro = :agora WHERE {filtro} "
            "AND pagar = 'Sim' AND data_registro IS NULL"
        ),
        {**parametros, "agora": _agora()},
    )
    conexao.execute(
        _sql(
            f"UPDATE tb_pagamentos SET data_pagamento = DATE(data_registro) WHERE {filtro} "
            "AND pagar = 'Sim' AND data_pagamento IS NULL"
        ),
        parametros,
    )
    conexao.execute(
        _sql(
            "UPDATE tb_pagamentos SET pagou = CASE "
            "WHEN entrada_manual = 'Sim' AND pagar = 'Sim' AND data_pagamento = :hoje THEN 'Não' "
            "WHEN pagar = 'Sim' AND data_pagamento IS NOT NULL AND data_pagamento < :hoje THEN 'Sim' "
            f"ELSE 'Não' END WHERE {filtro}"
        ),
        {**parametros, "hoje": hoje},
    )
    return {
        r[0]
        for r in conexao.execute(
            _sql(f"SELECT id_unico FROM tb_pagamentos WHERE {filtro} AND pagou = 'Sim'"), parametros
        )
    }


@_duravel("_prov_enviar_pagamentos")
def enviar_pagamentos(
    itens: list[dict], desfazer: list[str], usuario: str
) -> tuple[list[str], list[str], list[str], dict]:
    hoje = _hoje()
    agora = _agora()
    enviados: list[str] = []
    desfeitos: list[str] = []
    partes_apagadas: list[str] = []
    datas: dict = {}
    motor = obter_engine_manual()
    with motor.begin() as conexao:
        conexao.execute(
            text(
                "CREATE TABLE IF NOT EXISTS tb_controle_envio_pagamentos ("
                " id INT AUTO_INCREMENT PRIMARY KEY,"
                " id_unico VARCHAR(100) NULL,"
                " enviado_por VARCHAR(255) NULL,"
                " enviado_em DATETIME NULL)"
            )
        )
    with motor.begin() as conexao:
        atualizar_status_pagamentos(conexao, ids=[i["id_unico"] for i in itens] + list(desfazer), hoje=hoje)
        for item in itens:
            ident = item["id_unico"]
            atual = conexao.execute(
                text("SELECT pagou, data_pagamento FROM tb_pagamentos WHERE id_unico = :id"),
                {"id": ident},
            ).fetchone()
            campos = {
                "pagar": "Sim",
                "pagou": "Não",
                "valor_pago": item.get("valor_pago"),
                "juros": item.get("juros") or 0.0,
                "banco": item.get("banco") or "",
                "auditoria": "Sim",
                "conselho": item.get("conselho") or "Não",
                "data_registro": agora,
            }
            if atual is not None:
                if str(atual[0] or "").strip().lower() == "sim":
                    continue
                campos["data_pagamento"] = atual[1] or hoje
                completar, do_titulo = _completar_o_titulo(item.get("base"))
                sets = ", ".join([*(f"{k} = :{k}" for k in campos), *completar])
                conexao.execute(
                    text(f"UPDATE tb_pagamentos SET {sets} WHERE id_unico = :id"),
                    {**campos, **do_titulo, "id": ident},
                )
                datas[ident] = campos["data_pagamento"]
            else:
                datas[ident] = hoje
                linha = {
                    "id_unico": ident,
                    "revenda": _revenda_oficial(item.get("revenda")),
                    "entrada_manual": item.get("entrada_manual") or "Não",
                    "data_pagamento": hoje,
                    **(item.get("base") or {}),
                    **campos,
                }
                colunas = ", ".join(linha)
                marcas = ", ".join(f":{c}" for c in linha)
                conexao.execute(
                    text(f"INSERT INTO tb_pagamentos ({colunas}) VALUES ({marcas})"),
                    linha,
                )
            enviados.append(ident)

        for ident in desfazer:
            resultado = conexao.execute(
                text(
                    "UPDATE tb_pagamentos SET pagar = 'Não' WHERE id_unico = :id"
                    " AND pagar = 'Sim' AND COALESCE(pagou, '') <> 'Sim'"
                ),
                {"id": ident},
            )
            if resultado.rowcount:
                desfeitos.append(ident)

        titulo_de = {i["id_unico"]: i.get("valor_titulo") for i in itens}
        for ident in enviados:
            if eh_parte(ident):
                continue
            base = conexao.execute(
                text("SELECT valor_original, valor_pago FROM tb_pagamentos WHERE id_unico = :id"),
                {"id": ident},
            ).fetchone()
            try:
                original = float(titulo_de.get(ident) or base[0] or 0)
                pago = float(base[1] or 0)
            except (TypeError, ValueError):
                continue
            if original > 0 and pago >= original - 0.0001:
                sobras = [i for i in _partes_do_titulo(conexao, ident) if i not in enviados]
                if sobras:
                    sobras = [
                        r[0]
                        for r in conexao.execute(
                            text(
                                "SELECT id_unico FROM tb_pagamentos WHERE id_unico IN :ids "
                                "AND COALESCE(pagou, '') <> 'Sim' AND COALESCE(pagar, '') <> 'Sim'"
                            ).bindparams(bindparam("ids", expanding=True)),
                            {"ids": sobras},
                        ).fetchall()
                    ]
                if sobras:
                    conexao.execute(
                        text("DELETE FROM tb_pagamentos WHERE id_unico IN :ids").bindparams(
                            bindparam("ids", expanding=True)
                        ),
                        {"ids": sobras},
                    )
                    partes_apagadas.extend(sobras)

        if enviados:
            conexao.execute(
                text(
                    "INSERT INTO tb_controle_envio_pagamentos (id_unico, enviado_por, enviado_em)"
                    " VALUES (:id, :por, :em)"
                ),
                [{"id": i, "por": usuario or None, "em": agora} for i in enviados],
            )
    if not _REFAZENDO.get():
        _registrar_envio(itens, enviados, desfeitos, partes_apagadas, datas, usuario)
    return enviados, desfeitos, partes_apagadas, datas


def _registrar_envio(itens, enviados, desfeitos, partes_apagadas, datas, usuario) -> None:
    enviado = {i["id_unico"]: i for i in itens}
    for ident in enviados:
        item = enviado.get(ident) or {}
        _registrar(
            "enviar pagamento",
            "pagamentos",
            titulo=ident,
            chave=ident,
            usuario=usuario,
            depois={
                "valor_pago": item.get("valor_pago"),
                "juros": item.get("juros"),
                "banco": item.get("banco"),
                "data_pagamento": datas.get(ident),
            },
        )
    for ident in desfeitos:
        _registrar("desfazer envio do pagamento", "pagamentos", titulo=ident, chave=ident, usuario=usuario)
    for ident in partes_apagadas:
        _registrar("apagar parte (título pago inteiro)", "pagamentos", titulo=ident, chave=ident, usuario=usuario)


def pasta_do_titulo(id_unico: str) -> Path:
    seguro = "".join(c for c in str(id_unico) if c.isalnum() or c in "-_")
    if not seguro:
        raise ValueError("id_unico inválido para pasta de anexo")
    return PASTA_ANEXOS / seguro


def anexos_do_titulo(id_unico: str) -> list:
    pasta = pasta_do_titulo(id_unico)
    if not pasta.is_dir():
        return []
    return sorted(
        (a for a in pasta.iterdir() if a.is_file()),
        key=lambda a: a.stat().st_mtime,
        reverse=True,
    )


def titulos_com_anexo() -> set:
    if not PASTA_ANEXOS.is_dir():
        return set()
    achados = set()
    try:
        for pasta in PASTA_ANEXOS.iterdir():
            if not pasta.is_dir():
                continue
            if any(a.is_file() for a in pasta.iterdir()):
                achados.add(pasta.name)
    except OSError:
        return achados
    return achados


def nomes_dos_anexos() -> dict[str, list[str]]:
    if not PASTA_ANEXOS.is_dir():
        return {}
    achados: dict[str, list[str]] = {}
    try:
        for pasta in PASTA_ANEXOS.iterdir():
            if pasta.is_dir():
                nomes = [a.name for a in pasta.iterdir() if a.is_file()]
                if nomes:
                    achados[pasta.name] = nomes
    except OSError:
        return achados
    return achados


_cache_antigos: dict = {}


def normalizar_documento(texto) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(texto or "").strip().upper())


def _pastas_anexos_antigos(assunto: str = "anexos_contas_pagar") -> list[Path]:
    from .config_arquivo import carregar_json

    raiz = Path(__file__).resolve().parent.parent
    origem = (carregar_json("arquivos") or {}).get("pastas_origem") or {}
    saida = []
    for bruto in origem.get(assunto) or []:
        caminho = Path(bruto)
        if not caminho.is_absolute():
            caminho = raiz / caminho
        if caminho.is_dir():
            saida.append(caminho)
    return saida


def _pdfs_antigos() -> dict:
    pastas = _pastas_anexos_antigos()
    try:
        chave = tuple((str(p), p.stat().st_mtime_ns) for p in pastas)
    except OSError:
        return {}
    if _cache_antigos.get("chave") == chave:
        return _cache_antigos["mapa"]
    mapa: dict = {}
    for pasta in pastas:
        try:
            for arquivo in pasta.iterdir():
                if arquivo.is_file() and arquivo.suffix.lower() == ".pdf":
                    doc = normalizar_documento(arquivo.stem.split("-", 1)[0])
                    if doc:
                        mapa.setdefault(doc, []).append(arquivo)
        except OSError:
            continue
    _cache_antigos.update(chave=chave, mapa=mapa)
    return mapa


def docs_com_pdf_antigo() -> set:
    return set(_pdfs_antigos())


def normalizar_razao_social(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or "").strip())
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"[^a-zA-Z0-9]+", "-", sem_acento).strip("-").lower()


def anexos_antigos_do_documento(documento, razao_social=None) -> list:
    arquivos = _pdfs_antigos().get(normalizar_documento(documento), [])
    razao = normalizar_razao_social(razao_social)
    if not razao:
        return list(arquivos)
    saida = []
    for arquivo in arquivos:
        resto = arquivo.stem.split("-", 1)[1] if "-" in arquivo.stem else ""
        meio = resto.rsplit("-", 1)[0] if "-" in resto else ""
        if not meio or meio.lower() == razao:
            saida.append(arquivo)
    return saida


def anexo_antigo(nome: str) -> Path | None:
    if Path(nome).suffix.lower() != ".pdf":
        return None
    for pasta in _pastas_anexos_antigos():
        alvo = (pasta / Path(nome).name).resolve()
        if alvo.is_relative_to(pasta.resolve()) and alvo.is_file():
            return alvo
    return None


def eh_boleto(nome: str) -> bool:
    minusculo = nome.lower()
    return any(p in minusculo for p in ("boleto", "fatura", "fat_", "_fat", "bol_"))


def titulo_sem_boleto(id_unico: str):
    nomes = [a.name for a in anexos_do_titulo(id_unico)]
    nomes += [v["nome"] for v in manual_arquivo.vinculos_do_titulo(id_unico)]
    if not nomes:
        return None
    declarados = manual_arquivo.tipos_de_anexo()

    def _boleto(nome: str) -> bool:
        tipo = declarados.get((id_unico, nome))
        if tipo:
            return tipo.upper() == "FATURA"
        return eh_boleto(nome)

    return not any(_boleto(n) for n in nomes)


def guardar_anexo(id_unico: str, origem: str, nome: str, mover: bool = True) -> Path:
    destino = pasta_do_titulo(id_unico)
    destino.mkdir(parents=True, exist_ok=True)
    alvo = destino / Path(nome).name
    if mover:
        shutil.move(origem, alvo)
    else:
        shutil.copy2(origem, alvo)
    _registrar(
        "anexar arquivo",
        "anexos",
        titulo=id_unico,
        chave=f"{id_unico}/{alvo.name}",
        descricao=alvo.name + ("" if mover else " (copiado da rede)"),
    )
    return alvo


def excluir_anexo(id_unico: str, nome: str) -> bool:
    pasta = pasta_do_titulo(id_unico)
    alvo = pasta / Path(nome).name
    if not alvo.resolve().is_relative_to(pasta.resolve()):
        return False
    if alvo.is_file():
        alvo.unlink()
        _registrar("excluir anexo", "anexos", titulo=id_unico, chave=f"{id_unico}/{alvo.name}", descricao=alvo.name)
        return True
    return False


PASTA_ASSINADOS = Path(__file__).resolve().parent.parent / "uploads" / "assinados_titulos"


def pdf_assinado(id_unico: str) -> Path | None:
    fim = f" - {pasta_do_titulo(id_unico).name}.pdf"
    return next(PASTA_ASSINADOS.glob(f"*/*{fim}"), None)


def novo_pdf_assinado(id_unico: str, revenda: str | None, vencimento, documento, fornecedor) -> Path:
    def limpo(texto, tamanho: int) -> str:
        texto = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(texto or ""))
        return " ".join(texto.split())[:tamanho].strip(" .")

    dia = vencimento.strftime("%Y-%m-%d") if hasattr(vencimento, "strftime") else limpo(vencimento, 10)
    frente = " ".join(p for p in (dia, limpo(documento, 25), limpo(fornecedor, 40)) if p)
    pasta = PASTA_ASSINADOS / (limpo(_revenda_oficial(revenda), 25) or "Sem revenda")
    return pasta / f"{frente} - {pasta_do_titulo(id_unico).name}.pdf"


PASTA_ANEXOS_999 = Path(__file__).resolve().parent.parent / "uploads" / "pagamentos_999"


def _texto_para_nome(texto: str) -> str:
    import re
    import unicodedata

    limpo = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    limpo = limpo.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9_\-]", "", limpo)


def slug_revenda(revenda: str | None) -> str:
    import re
    import unicodedata

    texto = unicodedata.normalize("NFKD", str(revenda or "")).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"\s+", "-", texto.strip().lower())
    texto = re.sub(r"[^a-z0-9_.-]", "", texto)
    return texto or "global"


def nome_base_999(data_str: str, descricao: str, documento: str) -> str:
    return f"{str(data_str).replace('/', '-')}_{_texto_para_nome(descricao)}_{_texto_para_nome(documento)}"


def pasta_999(revenda: str | None) -> Path:
    return PASTA_ANEXOS_999 / slug_revenda(revenda)


def nomes_na_pasta_999(revenda: str | None) -> list[str]:
    pasta = pasta_999(revenda)
    if not pasta.is_dir():
        return []
    try:
        return sorted(a.name for a in pasta.iterdir() if a.is_file())
    except OSError:
        return []


def anexos_999(
    revenda: str | None,
    data_str: str,
    descricao: str,
    documento: str,
    nomes: list[str] | None = None,
) -> list[str]:
    import re

    base = nome_base_999(data_str, descricao, documento)
    aceitos = (f"{slug_revenda(revenda)}__{base}", base)
    padroes = [re.compile(rf"^{re.escape(a)}(?:_\d+)?\.pdf$", re.IGNORECASE) for a in aceitos]
    if nomes is None:
        nomes = nomes_na_pasta_999(revenda)
    return [n for n in nomes if any(p.match(n) for p in padroes)]


def guardar_anexo_999(
    revenda: str | None,
    data_str: str,
    descricao: str,
    documento: str,
    origem: str,
) -> Path:
    if not (str(data_str).strip() and str(descricao).strip() and str(documento).strip()):
        raise ValueError("data, descrição e documento são obrigatórios")
    pasta = pasta_999(revenda)
    pasta.mkdir(parents=True, exist_ok=True)
    base = f"{slug_revenda(revenda)}__{nome_base_999(data_str, descricao, documento)}"
    alvo = pasta / f"{base}.pdf"
    indice = 1
    while alvo.exists():
        alvo = pasta / f"{base}_{indice}.pdf"
        indice += 1
    shutil.move(origem, alvo)
    _registrar(
        "anexar no Caixa 999",
        "caixa 999",
        chave=alvo.name,
        revenda=_revenda_oficial(revenda),
        descricao=f"{data_str} · {descricao} · {documento}",
    )
    return alvo


def excluir_anexo_999(revenda: str | None, nome: str) -> bool:
    pasta = pasta_999(revenda)
    alvo = pasta / Path(nome).name
    if not alvo.resolve().is_relative_to(pasta.resolve()):
        return False
    if alvo.is_file():
        alvo.unlink()
        _registrar("excluir anexo do Caixa 999", "caixa 999", chave=alvo.name, revenda=_revenda_oficial(revenda))
        return True
    return False


CAMPOS_CONFIG_EMPRESTIMO = ("valor_credito", "entrada", "taxa_juros")

PASTA_CONTRATOS = Path(__file__).resolve().parent.parent / "uploads" / "emprestimos"


@_duravel("_prov_salvar_config_emprestimo")
def salvar_config_emprestimo(revenda: str, contrato: str, campo: str, valor, usuario: str) -> dict:
    if campo not in CAMPOS_CONFIG_EMPRESTIMO:
        raise ValueError(f"Campo inválido: {campo}")
    agora = _agora()
    with obter_engine_manual().begin() as conexao:
        conexao.execute(
            text(
                f"INSERT INTO tb_emprestimos_configuracoes (revenda, contrato, {campo}, "
                "atualizado_em, atualizado_por) VALUES (:r, :c, :v, :em, :por) "
                f"ON DUPLICATE KEY UPDATE {campo} = VALUES({campo}), "
                "atualizado_em = VALUES(atualizado_em), atualizado_por = VALUES(atualizado_por)"
            ),
            {"r": revenda, "c": contrato, "v": valor, "em": agora, "por": usuario},
        )
        linha = (
            conexao.execute(
                text(
                    "SELECT revenda, contrato, valor_credito, entrada, taxa_juros, "
                    "atualizado_em, atualizado_por FROM tb_emprestimos_configuracoes "
                    "WHERE revenda = :r AND contrato = :c"
                ),
                {"r": revenda, "c": contrato},
            )
            .mappings()
            .first()
        )
    fora = dict(linha) if linha else {"revenda": revenda, "contrato": contrato}
    for c in CAMPOS_CONFIG_EMPRESTIMO:
        if fora.get(c) is not None:
            fora[c] = float(fora[c])
    return fora


def _nome_seguro(texto: str) -> str:
    import re
    import unicodedata

    limpo = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    for separador in ("/", "\\"):
        limpo = limpo.replace(separador, " ")
    limpo = re.sub(r"[^A-Za-z0-9_.-]", "", "_".join(limpo.split()))
    return limpo.strip("._")


def pasta_contratos(revenda: str) -> Path:
    return PASTA_CONTRATOS / (_nome_seguro(str(revenda or "").strip().lower().replace(" ", "_")) or "global")


def nome_do_contrato(contrato: str) -> str:
    return _nome_seguro(contrato) + ".pdf"


def _pastas_de_contrato(revenda: str) -> list[Path]:
    pasta = pasta_contratos(revenda)
    return [pasta] + [base / pasta.name for base in _pastas_anexos_antigos("contratos_emprestimos")]


def contrato_salvo(revenda: str, contrato: str) -> Path | None:
    for pasta in _pastas_de_contrato(revenda):
        alvo = pasta / nome_do_contrato(contrato)
        if alvo.is_file():
            return alvo
    return None


def contratos_salvos(revenda: str) -> set[str]:
    return {
        a.name.lower()
        for pasta in _pastas_de_contrato(revenda)
        if pasta.is_dir()
        for a in pasta.iterdir()
        if a.is_file()
    }


def guardar_contrato(revenda: str, contrato: str, origem: str) -> Path:
    pasta = pasta_contratos(revenda)
    pasta.mkdir(parents=True, exist_ok=True)
    alvo = pasta / nome_do_contrato(contrato)
    shutil.move(origem, alvo)
    _registrar(
        "enviar contrato de empréstimo",
        "empréstimos",
        chave=f"{revenda}/{contrato}",
        revenda=_revenda_oficial(revenda),
        descricao=f"contrato {contrato}",
    )
    return alvo


def excluir_contrato(revenda: str, contrato: str) -> bool:
    alvo = pasta_contratos(revenda) / nome_do_contrato(contrato)
    if alvo.is_file():
        alvo.unlink()
        _registrar(
            "excluir contrato de empréstimo",
            "empréstimos",
            chave=f"{revenda}/{contrato}",
            revenda=_revenda_oficial(revenda),
            descricao=f"contrato {contrato}",
        )
        return True
    return False


PASTA_DO_PIPELINE = Path(__file__).resolve().parent.parent / "data" / "bd_financeiro"
_COLUNAS_DO_PAGAMENTO = (
    "id_unico",
    "valor_original",
    "valor_pago",
    "juros",
    "banco",
    "pagar",
    "pagou",
    "entrada_manual",
    "data_pagamento",
)


def _sim(valor) -> bool:
    return str(valor or "").strip().lower() == "sim"


def _do_pipeline(bases: set[str]) -> dict[str, dict]:
    arquivo = PASTA_DO_PIPELINE / "pagamentos.parquet"
    if not bases or not arquivo.is_file():
        return {}
    try:
        tabela = ler_parquet(arquivo).lazy()
        colunas = [c for c in _COLUNAS_DO_PAGAMENTO if c in tabela.collect_schema().names()]
        filtro = pl.col("id_unico").is_in(list(bases))
        for base in bases:
            filtro = filtro | pl.col("id_unico").str.starts_with(f"{base}_clone")
        return {r["id_unico"]: r for r in tabela.filter(filtro).select(colunas).collect().iter_rows(named=True)}
    except Exception as erro:
        print(f"gravacao: pagamentos.parquet sem leitura -- {erro}")
        return {}


def _estado(*bases: str) -> dict[str, dict]:
    bases = {b for b in bases if b}
    linhas = _do_pipeline(bases)
    editado = manual_arquivo.pagamentos_por_titulo()
    desfeitas = manual_arquivo.partes_desfeitas()
    fora = manual_arquivo.fora_da_fila()
    for ident in [*editado, *manual_arquivo.quem_dividiu()]:
        if base_do(ident) in bases:
            linhas.setdefault(ident, {"id_unico": ident})
    estado = {}
    for ident, linha in linhas.items():
        if base_do(ident) not in bases or ident in desfeitas:
            continue
        atual = dict(linha)
        tela = editado.get(ident)
        if tela:
            atual.update({c: tela.get(c) for c in ("valor_pago", "juros", "banco", "data_pagamento")})
            if tela.get("valor_original") is not None:
                atual["valor_original"] = tela["valor_original"]
            if tela.get("enviado_em") is not None:
                atual["pagar"] = "Sim"
        if ident in fora:
            atual["pagar"] = "Não"
        estado[ident] = atual
    return estado


def _enviado(linha: dict | None) -> bool:
    return bool(linha) and (_sim(linha.get("pagar")) or _sim(linha.get("pagou")))


def _prov_editar_pagamento_manual(id_unico, revenda, linha, *, _quando):
    estado = _estado(id_unico)
    if _enviado(estado.get(id_unico)):
        raise EdicaoRecusada("este pagamento manual já foi enviado para pagamento")
    if any(eh_parte(i) for i in estado):
        raise EdicaoRecusada("este pagamento manual foi dividido em partes")
    return None, {}


def _prov_devolver_a_pendente(id_unico, *, _quando):
    base = base_do(id_unico)
    estado = _estado(base)
    partes = sorted(i for i in estado if eh_parte(i))
    manuais = set(manual_arquivo.ler("entradas_manuais")["id_unico"].to_list())
    manual = id_unico in manuais or str((estado.get(id_unico) or {}).get("entrada_manual") or "").strip().lower() in (
        "sim",
        "s",
        "true",
        "1",
    )
    if manual:
        caso, ids = "manual", [id_unico]
    elif partes and base in estado:
        caso, ids = "dividido", [base, *partes]
    else:
        caso, ids = "comum", [id_unico]
    return {"caso": caso, "ids": ids, "partes": partes}, {}


def _prov_dividir_parte(id_linha, revenda, valor, banco, valor_titulo, campos=None, usados=(), numero=None, *, _quando):
    base = base_do(id_linha)
    partes = {i: e.get("valor_original") for i, e in _estado(base).items() if eh_parte(i)}
    if eh_parte(id_linha):
        if id_linha not in partes:
            raise ValueError("esta parte não existe mais — recarregue a tabela")
        atual = float(partes[id_linha] or 0)
    else:
        atual = float(valor_titulo) - sum(float(v or 0) for v in partes.values())
    atual, valor = round(atual, 2), round(float(valor), 2)
    if not 0 < valor < atual:
        raise ValueError(f"o valor tem de ficar entre zero e {atual:.2f}".replace(".", ","))
    usados_todos = [*partes, *usados, *(i for i in manual_arquivo.partes_desfeitas() if eh_parte(i))]
    proximo = max((numero_da_parte(i) for i in usados_todos if base_do(i) == base), default=0) + 1
    if proximo > LIMITE_DE_PARTES:
        raise ValueError(f"o título já tem {LIMITE_DE_PARTES} partes")
    return (id_da_parte(base, proximo), round(atual - valor, 2)), {"numero": proximo}


def _prov_desfazer_partes(ids=(), base=None, devolver_a_base=True, *, _quando):
    ids = [i for i in ids if eh_parte(i)]
    if not ids and not base:
        return ([], [], {}), {}
    estado = _estado(*({base} if base else {base_do(i) for i in ids}))
    if base:
        linhas = {i: e for i, e in estado.items() if eh_parte(i) and base_do(i) == base}
        ids = sorted({*ids, *linhas})
    else:
        linhas = {i: estado[i] for i in ids if i in estado}
    recusadas = [i for i, e in linhas.items() if _enviado(e)]
    if devolver_a_base:
        recusadas += [i for i in linhas if _enviado(estado.get(base_do(i))) and i not in recusadas]
    if recusadas:
        return ([], recusadas, {}), {}
    pago_da_base = {}
    if devolver_a_base:
        for dono in {base_do(i) for i in linhas}:
            if dono in estado:
                volta = sum(
                    float(e["valor_original"] if e.get("valor_original") is not None else e.get("valor_pago") or 0)
                    for i, e in linhas.items()
                    if base_do(i) == dono
                )
                pago_da_base[dono] = round(float(estado[dono].get("valor_pago") or 0) + volta, 2)
    return (list(ids), [], pago_da_base), {}


def _prov_enviar_pagamentos(itens, desfazer, usuario, *, _quando):
    hoje = _quando.date()
    estado = _estado(*{base_do(i["id_unico"]) for i in itens}, *{base_do(i) for i in desfazer})
    enviados, datas = [], {}
    for item in itens:
        ident = item["id_unico"]
        linha = estado.get(ident)
        data = linha.get("data_pagamento") if linha and _sim(linha.get("pagar")) else None
        if linha is not None and (_sim(linha.get("pagou")) or (data is not None and data < hoje)):
            continue
        datas[ident] = data or hoje
        enviados.append(ident)
    desfeitos = [
        i for i in desfazer if _sim((estado.get(i) or {}).get("pagar")) and not _sim((estado.get(i) or {}).get("pagou"))
    ]
    por_id = {i["id_unico"]: i for i in itens}
    partes_apagadas = []
    for ident in enviados:
        if eh_parte(ident):
            continue
        try:
            original = float(por_id[ident].get("valor_titulo") or (estado.get(ident) or {}).get("valor_original") or 0)
            pago = float(por_id[ident].get("valor_pago") or 0)
        except (TypeError, ValueError):
            continue
        if original > 0 and pago >= original - 0.0001:
            partes_apagadas += [
                p
                for p, e in estado.items()
                if eh_parte(p) and base_do(p) == ident and p not in enviados and not _enviado(e)
            ]
    _registrar_envio(itens, enviados, desfeitos, partes_apagadas, datas, usuario)
    return (enviados, desfeitos, partes_apagadas, datas), {}


def _fatia_do_arquivo(revenda: str, dia: date) -> list[dict]:
    alvo = str(revenda or "").strip().casefold()
    if (alvo, dia) in manual_arquivo.fatias_dados_manuais():
        base = manual_arquivo.dados_manuais(revenda, dia)
    else:
        from core import pastas_da_sessao

        arquivo = pastas_da_sessao.pasta_do_cache("dados_manuais", PASTA_DO_PIPELINE) / "dados_manuais.parquet"
        if not arquivo.is_file():
            return []
        base = (
            ler_parquet(arquivo)
            .lazy()
            .filter(
                (pl.col("REVENDA").cast(pl.Utf8).str.strip_chars().str.to_lowercase() == alvo) & (pl.col("data") == dia)
            )
            .collect()
        )
    linhas = []
    for r in base.iter_rows(named=True):
        item = {c: r.get(c) for c in COLUNAS_DADO_MANUAL}
        item.update(revenda=revenda, data=dia, hora=_hora_texto(r.get("hora")))
        linhas.append(item)
    return linhas


def _prov_salvar_dado_manual(revenda, banco, quando, campos, *, _quando):
    fatia = _FatiaArquivo(
        _fatia_do_arquivo(revenda, quando.date()), revenda, quando.date(), quando.strftime("%H:%M:%S")
    )
    _aplicar_dado_manual(fatia, banco, campos)
    return fatia.linhas, {}


def _prov_excluir_dado_manual(revenda, banco, dia, hora_texto, *, _quando):
    linhas = _fatia_do_arquivo(revenda, dia)
    alvo = str(banco or "").strip().casefold()
    ficam = [
        l
        for l in linhas
        if not (str(l.get("banco") or "").strip().casefold() == alvo and str(l.get("hora") or "")[:8] == hora_texto)
    ]
    manual_arquivo.substituir_fatia_dados_manuais(revenda, dia, ficam)
    return len(linhas) - len(ficam), {}


def _prov_salvar_config_emprestimo(revenda, contrato, campo, valor, usuario, *, _quando):
    if campo not in CAMPOS_CONFIG_EMPRESTIMO:
        raise ValueError(f"Campo inválido: {campo}")
    alvo = (str(revenda).strip().casefold(), str(contrato))
    linha = next(
        (
            r
            for r in manual_arquivo.ler("emprestimos_configuracoes").iter_rows(named=True)
            if (str(r.get("revenda") or "").strip().casefold(), str(r.get("contrato"))) == alvo
        ),
        None,
    )
    arquivo = PASTA_DO_PIPELINE / "emprestimos_configuracoes.parquet"
    if linha is None and arquivo.is_file():
        try:
            linha = next(
                (
                    dict(r, revenda=r.get("REVENDA"))
                    for r in ler_parquet(arquivo).iter_rows(named=True)
                    if (str(r.get("REVENDA") or "").strip().casefold(), str(r.get("contrato"))) == alvo
                ),
                None,
            )
        except Exception:
            linha = None
    fora = {c: (linha or {}).get(c) for c in ("valor_credito", "entrada", "taxa_juros")}
    fora.update(revenda=revenda, contrato=contrato, atualizado_em=_quando, atualizado_por=usuario)
    fora[campo] = valor
    for c in CAMPOS_CONFIG_EMPRESTIMO:
        if fora.get(c) is not None:
            fora[c] = float(fora[c])
    return fora, {}


def conteudo_do_contrato(revenda: str, contrato: str) -> bytes | None:
    alvo = contrato_salvo(revenda, contrato)
    return alvo.read_bytes() if alvo else None
