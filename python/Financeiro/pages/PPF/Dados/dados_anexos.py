import io
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple

from core import arquivo_revenda, gravacao, manual_arquivo, rede_documentos
from core import extrato_banco_pdf as fontes
from core.config import chave_revenda, chaves_das_revendas
from core.config_arquivo import carregar_json
from core.id_titulo import base_do

from . import dados_contas_pagar as cp
from . import dados_ppf as d


def extensoes_aceitas(assunto: str, padrao: str) -> str:
    lista = (carregar_json("arquivos").get(assunto) or {}).get("extensoes")
    return ",".join(str(e).upper() for e in lista) if lista else padrao


class Upload(NamedTuple):
    campo: str
    rotulo: str
    aceita: str
    varios: bool
    dica: str
    pasta: str
    titulo: str
    lista: str
    icone: str
    permissao: str = "upload_extrato"
    grupo: str = ""
    aba: str = ""


ICONE_PDF = "img/ppf/pdf-icon2.svg"

ICONE_TXT = "img/ppf/txt-icon.svg"

ICONE_EXCEL = "img/ppf/excel-verde.svg"

UPLOADS = [
    Upload(
        "arq_banco",
        "Banco",
        ".pdf",
        True,
        "Extratos bancários em PDF",
        "bancos_extratos",
        "Gerenciar Extratos de Bancos",
        "Extratos de Bancos disponíveis",
        ICONE_PDF,
    ),
    Upload(
        "arq_batida",
        "Batida",
        extensoes_aceitas("batida_diaria", ".LST,.TXT"),
        False,
        "Batida diária do caixa (.LST)",
        "batida_diaria",
        "Gerenciar Batida Diária",
        "Batidas disponíveis",
        ICONE_TXT,
    ),
    Upload(
        "arq_fabrica_xlsx",
        "Fábrica",
        ".xlsx",
        True,
        "Planilhas e extratos da fábrica",
        "fabricas_planilhas",
        "Gerenciar Arquivos de Fábrica",
        "Planilhas de Fábrica disponíveis",
        ICONE_EXCEL,
        "upload_extrato_fabrica_excel",
        "fabrica",
        "Extrato e Partidas (Excel)",
    ),
    Upload(
        "arq_fabrica",
        "Fábrica",
        ".pdf",
        True,
        "Extrato da fábrica em PDF",
        "fabricas_extratos",
        "Gerenciar Arquivos de Fábrica",
        "Extratos de Fábrica disponíveis",
        ICONE_PDF,
        "upload_extrato",
        "fabrica",
        "Extrato (PDF)",
    ),
    Upload(
        "arq_modelo_iv",
        "Modelo IV",
        ".LST,.TXT",
        False,
        "Modelo IV (.LST)",
        "modelo_iv",
        "Enviar Anexo - Modelo IV",
        "Anexos existentes",
        ICONE_TXT,
    ),
]

PASTA_UPLOADS = Path(__file__).parents[3] / "uploads"


def pasta_do_upload(pasta: str, revenda: str | None) -> Path:
    from core import virada

    if revenda and virada.virou(revenda):
        assunto = (carregar_json("arquivos").get("assunto_do_upload") or {}).get(pasta) or pasta
        raiz = PASTA_UPLOADS.parent.resolve()
        do_antigo = next((p for p in fontes.pastas(assunto) if not Path(p).resolve().is_relative_to(raiz)), None)
        if do_antigo is not None:
            return Path(do_antigo)
    return PASTA_UPLOADS / pasta


TIPOS_QUE_ABREM = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    ".lst": "text/plain; charset=utf-8",
}


def como_mostrar(nome: str) -> tuple[str, str]:
    extensao = Path(nome).suffix.lower()
    tipo = TIPOS_QUE_ABREM.get(extensao)
    if tipo:
        return tipo, "inline"
    return "application/octet-stream", "attachment"


def uploads_da_revenda(revenda: str | None) -> list[Upload]:
    from core import revendas as cadastro_revendas
    from core.config import regra_do_segundo_erp, sem_extrato_fabrica

    sem_fabrica = sem_extrato_fabrica(revenda)
    envios_da_revenda_do_segundo_erp = None
    if cadastro_revendas.eh_do_segundo_erp(revenda):
        envios_da_revenda_do_segundo_erp = set((regra_do_segundo_erp(revenda) or {}).get("envios_do_cabecalho") or [])
    botoes, vistos = [], set()
    for u in UPLOADS:
        if sem_fabrica and u.grupo == "fabrica":
            continue
        if envios_da_revenda_do_segundo_erp is not None and u.campo not in envios_da_revenda_do_segundo_erp:
            continue
        chave = u.grupo or u.campo
        if chave in vistos:
            continue
        vistos.add(chave)
        botoes.append(u)
    return botoes


def variantes(u: Upload) -> list[Upload]:
    if not u.grupo:
        return [u]
    return [x for x in UPLOADS if x.grupo == u.grupo]


LISTAS_DE_UPLOAD: dict = {}


def esquecer_listas() -> None:
    LISTAS_DE_UPLOAD.clear()


def _virada_de(revenda: str | None) -> datetime | None:
    from core import virada

    return virada.hora_da_virada(revenda)


def pastas_nossas(pasta: str, revenda: str | None) -> list[tuple[Path, datetime | None]]:
    nossas = [((PASTA_UPLOADS / pasta).resolve(), None)]
    quando = _virada_de(revenda)
    destino = pasta_do_upload(pasta, revenda).resolve() if quando else None
    if destino is not None and destino != nossas[0][0]:
        nossas.append((destino, quando))
    return nossas


def nome_do_download(caminhos: list[Path], prefixo: str) -> str:
    if len(caminhos) == 1:
        return caminhos[0].name
    return f"{prefixo}_{date.today():%Y-%m-%d}.zip"


def conteudo_do_download(caminhos: list[Path]) -> bytes:
    if len(caminhos) == 1:
        return caminhos[0].read_bytes()
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as pacote:
        for caminho in caminhos:
            pacote.write(caminho, arcname=caminho.name)
    return memoria.getvalue()


def caminho_nosso(pasta: str, revenda: str | None, nome: str) -> Path | None:
    for base, desde in pastas_nossas(pasta, revenda):
        alvo = (base / Path(nome).name).resolve()
        if (
            alvo.is_relative_to(base)
            and alvo.is_file()
            and (desde is None or datetime.fromtimestamp(alvo.stat().st_mtime) >= desde)
        ):
            return alvo
    return None


def arquivos_enviados(pasta: str, revenda: str | None) -> list[tuple[str, str, bool, bool]]:
    minhas = frozenset(chaves_das_revendas([revenda]) | ({chave_revenda(revenda)} if revenda else set()))
    assunto = (carregar_json("arquivos").get("assunto_do_upload") or {}).get(pasta) or pasta

    def _do_zip(pasta_disco: Path):
        for zipado in sorted(pasta_disco.glob("_arquivo_*.zip")):
            try:
                with zipfile.ZipFile(zipado) as z:
                    for item in z.infolist():
                        if item.is_dir():
                            continue
                        yield item.filename, datetime(*item.date_time).date()
            except (zipfile.BadZipFile, OSError):
                continue

    nossas = dict(pastas_nossas(pasta, revenda))
    aceitas = {e.strip().lower() for u in UPLOADS if u.pasta == pasta for e in u.aceita.split(",") if e.strip()}
    vistos = set()
    linhas: list[tuple[str, date, bool, bool]] = []
    for destino in fontes.pastas(assunto):
        resolvida = destino.resolve()
        versao = destino.stat().st_mtime_ns
        guardado = LISTAS_DE_UPLOAD.get((str(destino), minhas))
        if guardado and guardado[0] == versao:
            da_pasta = guardado[1]
        else:
            da_pasta = []
            for a in destino.iterdir():
                if not a.is_file() or a.suffix == ".done":
                    continue
                if a.name.startswith("_arquivo_") and a.suffix == ".zip":
                    continue
                dono, _como = arquivo_revenda.revenda_do_nome(a.name)
                if minhas and chave_revenda(dono or "") not in minhas:
                    continue
                da_pasta.append((a.name, datetime.fromtimestamp(a.stat().st_mtime), True))
            for nome_zip, dia_zip in _do_zip(destino):
                nome_zip = Path(nome_zip).name
                dono, _como = arquivo_revenda.revenda_do_nome(nome_zip)
                if minhas and chave_revenda(dono or "") not in minhas:
                    continue
                da_pasta.append((nome_zip, datetime.combine(dia_zip, datetime.min.time()), False))
            LISTAS_DE_UPLOAD[(str(destino), minhas)] = (versao, da_pasta)
        for nome, quando, no_disco in da_pasta:
            if nome.lower() in vistos or (aceitas and Path(nome).suffix.lower() not in aceitas):
                continue
            vistos.add(nome.lower())
            meu = resolvida in nossas and (nossas[resolvida] is None or quando >= nossas[resolvida])
            linhas.append((nome, quando.date(), meu, no_disco))
    if not linhas:
        return []
    linhas.sort(key=lambda linha: linha[1], reverse=True)
    mais_recente = linhas[0][1]
    return [
        (nome, dia.strftime("%d/%m/%Y"), dia == mais_recente, meu and no_disco)
        for nome, dia, meu, no_disco in linhas[:30]
    ]


def entregar_anexo(request):
    from starlette.responses import FileResponse, PlainTextResponse

    ident = request.query_params.get("id", "")
    nome = request.query_params.get("nome", "")
    if not ident or not nome:
        return PlainTextResponse("faltou id ou nome", status_code=400)
    try:
        pasta = gravacao.pasta_do_titulo(ident)
    except ValueError:
        return PlainTextResponse("titulo invalido", status_code=400)
    alvo = (pasta / Path(nome).name).resolve()
    if not alvo.is_relative_to(pasta.resolve()) or not alvo.is_file():
        return PlainTextResponse("anexo nao encontrado", status_code=404)
    tipo, como = como_mostrar(alvo.name)
    return FileResponse(
        alvo,
        media_type=tipo,
        headers={"Content-Disposition": f'{como}; filename="{alvo.name}"'},
    )


def entregar_anexo_antigo(request):
    from starlette.responses import FileResponse, PlainTextResponse

    alvo = gravacao.anexo_antigo(request.query_params.get("nome", ""))
    if alvo is None:
        return PlainTextResponse("anexo nao encontrado", status_code=404)
    tipo, como = como_mostrar(alvo.name)
    return FileResponse(
        alvo,
        media_type=tipo,
        headers={"Content-Disposition": f'{como}; filename="{alvo.name}"'},
    )


def tipo_do_anexo(ident: str, nome: str, tipos: dict | None = None) -> tuple[str, bool]:
    declarado = (manual_arquivo.tipos_de_anexo() if tipos is None else tipos).get((ident, nome))
    if declarado:
        return ("FATURA" if declarado.upper() == "FATURA" else "NF"), False
    return ("FATURA" if gravacao.eh_boleto(nome) else "NF"), True


_cache_nota_da_rede: dict = {}


def titulos_com_pdf_da_nota() -> set:
    chave, _rede = d._vinculos_da_rede()
    if chave not in _cache_nota_da_rede:
        de_fora = d._vinculos_com_origem()
        notas = set()
        if not de_fora.is_empty():
            for ident, caminho, nome, tipo, existe in de_fora.select(
                "id_unico", "caminho", "nome", "tipo", "existe"
            ).iter_rows():
                if existe and cp.tipo_do_vinculo(tipo, nome or Path(str(caminho or "")).name) == "NF":
                    notas.add(ident)
        _cache_nota_da_rede.clear()
        _cache_nota_da_rede[chave] = notas
    achados = set(_cache_nota_da_rede[chave])
    aqui = manual_arquivo.ler("vinculos")
    for ident, caminho, nome in aqui.select("id_unico", "caminho", "nome").iter_rows():
        if cp.tipo_do_vinculo(None, nome or Path(str(caminho or "")).name) == "NF":
            achados.add(ident)
    tipos = manual_arquivo.tipos_de_anexo()
    for ident, nomes in gravacao.nomes_dos_anexos().items():
        if any(n.lower().endswith(".pdf") and tipo_do_anexo(ident, n, tipos)[0] == "NF" for n in nomes):
            achados.add(ident)
    return achados


def documentos_do_olho() -> dict:
    return {
        "com_anexo": gravacao.titulos_com_anexo(),
        "com_vinculo": manual_arquivo.titulos_com_vinculo(),
        "docs_antigos": gravacao.docs_com_pdf_antigo(),
        "rede": d.icones_da_rede(),
        "abrir_rede": d.pdf_da_rede(),
        "com_xml": d.xml_dos_titulos(),
        "com_pdf_da_nota": titulos_com_pdf_da_nota(),
        "antigos_tirados": {i for i, origem, _r in manual_arquivo.desvinculados() if origem == "antigo"},
    }


def antigos_do_titulo(ident: str, documento, fornecedor: str) -> list[Path]:
    if not ident or not documento:
        return []
    arquivos = gravacao.anexos_antigos_do_documento(documento, fornecedor)
    if not arquivos:
        return []
    base = base_do(ident)
    tirados = {r for i, origem, r in manual_arquivo.desvinculados() if i == base and origem == "antigo"}
    return [a for a in arquivos if manual_arquivo.referencia_do_desvinculo("antigo", a.name) not in tirados]


def xml_vale(ident: str, documento=None, fornecedor: str = "") -> bool:
    docs = {"com_xml": d.xml_dos_titulos(), "com_pdf_da_nota": titulos_com_pdf_da_nota()}
    return cp.xml_conta(
        ident, gravacao.normalizar_documento(documento) if documento else "", fornecedor or "", docs, antigos_do_titulo
    )


def outras_notas_do_boleto(base: str) -> list[str]:
    tirados = {r for i, origem, r in manual_arquivo.desvinculados() if i == base and origem == "xml"}
    return [
        outro
        for outro in d.titulos_do_mesmo_boleto(base)
        if xml_vale(outro)
        and manual_arquivo.referencia_do_desvinculo("xml", d.referencia_do_xml(d.xml_do_titulo(outro) or {}))
        not in tirados
    ]


def pdf_do_xml(ident: str) -> Path | None:
    relativo = d.xml_dos_titulos().get(base_do(ident))
    if not relativo:
        return None
    try:
        from core import xml_fiscal

        return xml_fiscal.pdf_em_arquivo(relativo)
    except Exception:
        return None


ORDEM_DO_TIPO = {"NF": 0, "FATURA": 1}


def documento_do_xml(titulo: str) -> tuple[str, str] | None:
    numero = str((d.xml_do_titulo(titulo) or {}).get("numero") or "").lstrip("0")
    return ("NF", numero) if numero else None


def arquivos_do_olho(ident: str, documento, fornecedor: str) -> list[Path]:
    base = base_do(ident)
    com_ordem = []
    if xml_vale(ident, documento, fornecedor):
        do_xml = pdf_do_xml(ident)
        if do_xml:
            com_ordem.append((0, do_xml, documento_do_xml(base)))
    for outro in outras_notas_do_boleto(base):
        do_outro = pdf_do_xml(outro)
        if do_outro:
            com_ordem.append((0, do_outro, documento_do_xml(outro)))
    for vinculo in d.vinculos_de_fora(base):
        if not vinculo.get("caminho"):
            continue
        atual = rede_documentos.caminho_atual(vinculo["caminho"])
        if atual is None:
            continue
        tipo = cp.tipo_do_vinculo(vinculo.get("tipo"), vinculo.get("nome") or atual.name)
        com_ordem.append((ORDEM_DO_TIPO.get(tipo, 2), atual, rede_documentos.documento_pelo_nome(atual.name)))
    for vinculo in manual_arquivo.vinculos_do_titulo(ident):
        if vinculo.get("estado") == "sumiu" or not vinculo.get("caminho"):
            continue
        caminho = Path(vinculo["caminho"])
        tipo = cp.tipo_do_vinculo(vinculo.get("tipo"), vinculo.get("nome") or "")
        com_ordem.append((ORDEM_DO_TIPO.get(tipo, 2), caminho, rede_documentos.documento_pelo_nome(caminho.name)))
    tipos = manual_arquivo.tipos_de_anexo()
    for anexo in gravacao.anexos_do_titulo(ident):
        ordem = ORDEM_DO_TIPO[tipo_do_anexo(ident, anexo.name, tipos)[0]]
        com_ordem.append((ordem, anexo, rede_documentos.documento_pelo_nome(anexo.name)))
    for antigo in antigos_do_titulo(ident, documento, fornecedor):
        com_ordem.append((2, antigo, rede_documentos.documento_pelo_nome(antigo.name)))
    arquivos, caminhos_vistos, documentos_vistos = [], set(), []
    for _ordem, arquivo, documento_do_arquivo in sorted(com_ordem, key=ordem_do_par):
        caminho = str(arquivo).lower()
        if caminho in caminhos_vistos or rede_documentos.repete_algum(documento_do_arquivo, documentos_vistos):
            continue
        if not arquivo.is_file():
            continue
        caminhos_vistos.add(caminho)
        documentos_vistos.append(documento_do_arquivo)
        arquivos.append(arquivo)
    return arquivos


def ordem_do_par(par: tuple) -> tuple[int, bool]:
    return par[0], rede_documentos.eh_boleto_pelo_nome(par[1].name)


def nome_do_olho(arquivo: Path, documento) -> str:
    from core import juntar_pdf

    if arquivo.parent == juntar_pdf.PASTA:
        return f"{documento or 'titulo'} - arquivos juntos.pdf"
    return arquivo.name


def documento_assinado_do_olho(original: Path | None, assinado: Path | None) -> Path | None:
    from core import juntar_pdf

    if assinado is None:
        return None
    if original is None or original.parent != juntar_pdf.PASTA:
        return assinado
    try:
        return juntar_pdf.com_a_ultima_pagina(original, assinado)
    except Exception as erro:
        print(f"Olho: a assinatura no juntado de {original.name} -- {erro}")
        return assinado


def documento_do_olho(ident: str, documento, fornecedor: str) -> Path | None:
    from core import juntar_pdf

    arquivos = arquivos_do_olho(ident, documento, fornecedor)
    if not arquivos:
        return None
    if len(arquivos) == 1:
        return arquivos[0]
    try:
        return juntar_pdf.juntar(arquivos)
    except Exception as erro:
        print(f"Olho: juntar os arquivos de {ident} -- {erro}")
        return arquivos[0]


def buscar_na_rede(revenda, venc, doc, tudo: bool):
    achados, onde = (
        rede_documentos.listar_pasta(revenda, venc) if tudo else rede_documentos.procurar(revenda, venc, doc)
    )
    return achados, onde, rede_documentos.pastas_do_dia_por_raiz(revenda, venc)
