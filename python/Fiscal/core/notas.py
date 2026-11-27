"""Os documentos recebidos (NF-e e CT-e, fictícios): leitura dos caches e o XML de cada um.

O XML não fica gravado: é montado na hora, a partir das tabelas, no leiaute da NF-e 4.00 e do CT-e 4.00
(as tags principais). Leva no próprio texto o aviso de que é um documento fictício.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

import polars as pl
import pyarrow.parquet as pq

PASTA = Path(__file__).parents[1] / "data" / "bd_notas"
_NOMES_MES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
_cache: dict[tuple[str, float], pl.DataFrame] = {}


def _ler(nome: str) -> pl.DataFrame:
    arquivo = PASTA / f"{nome}.parquet"
    chave = (nome, arquivo.stat().st_mtime)
    if chave not in _cache:
        _cache[chave] = pl.from_arrow(pq.read_table(arquivo))  # pyarrow: o polars do navegador não lê Parquet
    return _cache[chave]


def nfe() -> pl.DataFrame:
    return _ler("nfe_recebidas").with_columns(pl.col("EMISSAO").dt.strftime("%Y%m").alias("MES"))


def itens() -> pl.DataFrame:
    return _ler("nfe_itens")


def cte() -> pl.DataFrame:
    return _ler("cte_recebidos").with_columns(pl.col("EMISSAO").dt.strftime("%Y%m").alias("MES"))


def cte_nfe() -> pl.DataFrame:
    return _ler("cte_nfe")


def destinatario() -> dict:
    return _ler("destinatario").row(0, named=True)


def meses() -> dict[str, str]:
    """{AAAAMM: 'Nov/26'}, do mais recente para o mais antigo."""
    valores = sorted(nfe()["MES"].unique().to_list(), reverse=True)
    return {m: f"{_NOMES_MES[int(m[4:]) - 1]}/{m[2:4]}" for m in valores}


def cnpj_formatado(cnpj: str) -> str:
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def chave_formatada(chave: str) -> str:
    return " ".join(chave[i : i + 4] for i in range(0, 44, 4))


def dias_parado(emissao) -> int:
    return (date.today() - emissao.date()).days


def texto_dias(dias: int) -> str:
    return "hoje" if dias == 0 else "1 dia" if dias == 1 else f"{dias} dias"


# XML ---------------------------------------------------------------------------------------------

_AVISO = "DOCUMENTO FICTICIO GERADO PARA O PORTFOLIO - SEM VALOR FISCAL"


def _t(nome: str, valor) -> str:
    return f"<{nome}>{escape(str(valor))}</{nome}>"


def _v(valor: float) -> str:
    return f"{valor:.2f}"


def xml_nfe(chave: str) -> str:
    n = nfe().filter(pl.col("CHAVE") == chave).row(0, named=True)
    linhas = itens().filter(pl.col("CHAVE") == chave).sort("N_ITEM").to_dicts()
    dest = destinatario()
    det = "".join(
        f'<det nItem="{i["N_ITEM"]}"><prod>{_t("cProd", i["CODIGO"])}{_t("xProd", i["DESCRICAO"])}{_t("NCM", i["NCM"].replace(".", ""))}'
        f"{_t('CFOP', i['CFOP'])}{_t('uCom', i['UNIDADE'])}{_t('qCom', format(i['QTD'], '.4f'))}{_t('vUnCom', format(i['V_UNIT'], '.10f'))}"
        f"{_t('vProd', _v(i['V_PROD']))}</prod><imposto><ICMS>{_t('vICMS', _v(i['V_ICMS']))}{_t('vICMSST', _v(i['V_ST']))}"
        f"</ICMS></imposto></det>"
        for i in linhas
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">'
        f'<NFe><infNFe Id="NFe{chave}" versao="4.00">'
        f"<ide>{_t('cUF', chave[:2])}{_t('natOp', n['NATUREZA'].upper())}{_t('mod', '55')}{_t('serie', n['SERIE'])}"
        f"{_t('nNF', n['NUMERO'])}{_t('dhEmi', n['EMISSAO'].strftime('%Y-%m-%dT%H:%M:%S-03:00'))}{_t('tpNF', '1')}"
        f"{_t('tpAmb', '2')}</ide>"
        f"<emit>{_t('CNPJ', n['EMIT_CNPJ'])}{_t('xNome', n['EMIT_NOME'])}<enderEmit>{_t('xMun', n['EMIT_MUNICIPIO'])}"
        f"{_t('UF', n['EMIT_UF'])}</enderEmit></emit>"
        f"<dest>{_t('CNPJ', dest['CNPJ'])}{_t('xNome', dest['NOME'])}<enderDest>{_t('xMun', dest['MUNICIPIO'])}"
        f"{_t('UF', dest['UF'])}</enderDest>{_t('IE', dest['IE'])}</dest>"
        f"{det}"
        f"<total><ICMSTot>{_t('vBC', _v(n['BASE_ICMS']))}{_t('vICMS', _v(n['V_ICMS']))}{_t('vST', _v(n['V_ST']))}"
        f"{_t('vProd', _v(n['V_PROD']))}{_t('vNF', _v(n['V_NF']))}</ICMSTot></total>"
        f"<infAdic>{_t('infCpl', _AVISO)}</infAdic>"
        "</infNFe></NFe>"
        f'<protNFe versao="4.00"><infProt>{_t("tpAmb", "2")}{_t("chNFe", chave)}'
        f"{_t('dhRecbto', n['RECEBIDA_EM'].strftime('%Y-%m-%dT%H:%M:%S-03:00'))}{_t('cStat', '100')}"
        f"{_t('xMotivo', 'Autorizado o uso da NF-e')}</infProt></protNFe>"
        "</nfeProc>"
    )


def xml_cte(chave: str) -> str:
    c = cte().filter(pl.col("CHAVE") == chave).row(0, named=True)
    notas = cte_nfe().filter(pl.col("CHAVE_CTE") == chave)["CHAVE_NFE"].to_list()
    dest = destinatario()
    inf_nfe = "".join(f"<infNFe>{_t('chave', ch)}</infNFe>" for ch in notas)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<cteProc xmlns="http://www.portalfiscal.inf.br/cte" versao="4.00">'
        f'<CTe><infCte Id="CTe{chave}" versao="4.00">'
        f"<ide>{_t('cUF', chave[:2])}{_t('CFOP', '6353')}{_t('natOp', 'PRESTACAO DE SERVICO DE TRANSPORTE')}"
        f"{_t('mod', '57')}{_t('nCT', c['NUMERO'])}{_t('dhEmi', c['EMISSAO'].strftime('%Y-%m-%dT%H:%M:%S-03:00'))}"
        f"{_t('xMunIni', c['ORIGEM'])}{_t('xMunFim', c['DESTINO'])}{_t('tpAmb', '2')}</ide>"
        f"<emit>{_t('CNPJ', c['EMIT_CNPJ'])}{_t('xNome', c['EMIT_NOME'])}<enderEmit>{_t('xMun', c['EMIT_MUNICIPIO'])}"
        f"{_t('UF', c['EMIT_UF'])}</enderEmit></emit>"
        f"<dest>{_t('CNPJ', dest['CNPJ'])}{_t('xNome', dest['NOME'])}</dest>"
        f"<vPrest>{_t('vTPrest', _v(c['V_PREST']))}</vPrest><imp><ICMS>{_t('vICMS', _v(c['V_ICMS']))}</ICMS></imp>"
        f"<infCTeNorm><infCarga>{_t('vCarga', _v(c['V_CARGA']))}{_t('qCarga', format(c['PESO_KG'], '.4f'))}</infCarga>"
        f"<infDoc>{inf_nfe}</infDoc></infCTeNorm>"
        f"<compl>{_t('xObs', _AVISO)}</compl>"
        "</infCte></CTe></cteProc>"
    )


def xml_indentado(xml: str) -> str:
    """O XML com recuo, para ler na tela."""
    from xml.dom import minidom

    return minidom.parseString(xml.encode("utf-8")).toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
