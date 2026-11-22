from __future__ import annotations

import contextvars
import os
import re
import threading
from datetime import date
from pathlib import Path
from typing import NamedTuple

import cachetools

if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(
        0,
        str(
            Path(globals()["__file__"]).resolve().parents[1]
            if "__file__" in globals()
            else next(
                (
                    p
                    for p in (Path.cwd(), Path.cwd() / "Acompanhamento Financeiro")
                    if (p / "core" / "config_arquivo.py").is_file()
                ),
                Path.cwd(),
            )
        ),
    )

from core.config_arquivo import carregar_json

CONFIG = "pastas_rede"


def _cfg() -> dict:
    return carregar_json(CONFIG) or {}


def _sem_marca(valor):
    if isinstance(valor, dict):
        return {k: v for k, v in valor.items() if not k.startswith("_")}
    return valor


def _norm(texto: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(texto or "").upper())


def _familia_nf() -> frozenset[str]:
    return frozenset(_cfg().get("familia_nf") or ["NF", "NFE", "NFS", "NFC"])


def tipos_compativeis(do_arquivo: str, do_erp: str) -> bool:
    if do_arquivo == do_erp:
        return True
    familia = _familia_nf()
    return (do_arquivo == "NF" and do_erp in familia) or (do_erp == "NF" and do_arquivo in familia)


def pares_do_nome(nome_arquivo: str) -> list[tuple[str, str]]:
    miolo = os.path.splitext(str(nome_arquivo or ""))[0].upper()
    so_a_sigla_troca_o_tipo = _SIGLA_NO_COMECO.get()
    siglas = (_familia_nf() | {"NF"} | set(PALAVRAS_DE_BOLETO)) if so_a_sigla_troca_o_tipo else set()
    pares: list[tuple[str, str]] = []
    tipo_atual: str | None = None
    for token in re.findall(r"[A-Z]+|\d+", miolo):
        if token.isalpha():
            if not so_a_sigla_troca_o_tipo or token in siglas:
                tipo_atual = token
        elif tipo_atual:
            pares.append((tipo_atual, token.lstrip("0") or "0"))
    return pares


_SIGLA_NO_COMECO: contextvars.ContextVar[bool] = contextvars.ContextVar("sigla_no_comeco", default=False)


def ler_os_nomes_como_a_revenda(revenda: str | None) -> None:
    _SIGLA_NO_COMECO.set(bool(regras_da_revenda(revenda).get("sigla_no_comeco")) if revenda else False)


def candidatos_do_numero(digitos: str) -> set[str]:
    cands = {digitos.lstrip("0") or "0"}
    resto = digitos
    for _ in range(2):
        if len(resto) > 2:
            resto = resto[:-2]
            sem = resto.lstrip("0") or "0"
            if len(sem) >= 3:
                cands.add(sem)
    return cands


TAM_NUMERO_DO_TITULO = 7


def numero_no_formato(num_doc: str) -> str | None:
    nd = str(num_doc or "").strip().upper()
    prefixo = re.match(r"[A-Z]*", nd).group(0)
    fim = 3 + TAM_NUMERO_DO_TITULO
    if len(prefixo) < 2 or len(nd) != fim + 2 or not nd[fim:].isdigit():
        return None
    numero = nd[3:fim].replace(" ", "")
    return (numero.lstrip("0") or "0") if numero.isdigit() else ""


def numeros_do_titulo(num_doc: str) -> set[str]:
    numero = numero_no_formato(num_doc)
    if numero is not None:
        return {numero} if numero else set()
    achado = re.match(r"^[A-Z]+(\d+)$", _norm(num_doc))
    return candidatos_do_numero(achado.group(1)) if achado else set()


def casa(num_doc_normalizado: str, nome_arquivo: str) -> bool:
    n = _norm(num_doc_normalizado)
    achado = re.match(r"^([A-Z]+)(\d+)$", n)
    if not achado:
        return False
    tipo_erp, digitos = achado.group(1), achado.group(2)
    cands = candidatos_do_numero(digitos)
    for tipo_arquivo, numero_arquivo in pares_do_nome(nome_arquivo):
        if numero_arquivo in cands and tipos_compativeis(tipo_arquivo, tipo_erp):
            return True
    return False


PALAVRAS_DE_BOLETO = frozenset({"BOLETO", "BOLETOS", "BOL"})


def eh_boleto_pelo_nome(nome_arquivo: str) -> bool:
    miolo = os.path.splitext(Path(str(nome_arquivo or "")).name)[0].upper()
    return bool(set(re.findall(r"[A-Z]+", miolo)) & PALAVRAS_DE_BOLETO)


def numeros_no_nome_do_boleto(nome_arquivo: str) -> list[str]:
    if not eh_boleto_pelo_nome(nome_arquivo):
        return []
    return [n for t, n in pares_do_nome(nome_arquivo) if t in PALAVRAS_DE_BOLETO or len(n) >= 3]


def documento_pelo_nome(nome_arquivo: str) -> tuple[str, str] | None:
    nome = Path(str(nome_arquivo or "")).name
    if eh_boleto_pelo_nome(nome):
        citados = numeros_no_nome_do_boleto(nome)
        return ("BOLETO", citados[0].lstrip("0")) if citados else None
    palavras = re.findall(r"[A-Z]+", os.path.splitext(nome)[0].upper())
    siglas_de_nota = _familia_nf() | {"NF", "CTE"}
    if not palavras or palavras[0] not in siglas_de_nota:
        return None
    for tipo, numero in pares_do_nome(nome):
        if tipo in siglas_de_nota and numero.lstrip("0"):
            return tipo, numero.lstrip("0")
    return None


def mesmo_documento(um: tuple[str, str] | None, outro: tuple[str, str] | None) -> bool:
    if um is None or outro is None or um[1] != outro[1]:
        return False
    if "BOLETO" in (um[0], outro[0]):
        return um[0] == outro[0]
    return tipos_compativeis(um[0], outro[0])


def repete_algum(documento: tuple[str, str] | None, vistos: list) -> bool:
    return any(mesmo_documento(documento, visto) for visto in vistos)


def casa_o_boleto(num_doc_normalizado: str, nome_arquivo: str) -> bool:
    achado = re.match(r"^([A-Z]+)(\d+)$", _norm(num_doc_normalizado))
    return bool(achado) and bool(candidatos_do_numero(achado.group(2)) & set(numeros_no_nome_do_boleto(nome_arquivo)))


MARCA_BACKUP_XML = "(gerado do XML)"


def eh_backup_do_xml(nome: str) -> bool:
    return MARCA_BACKUP_XML.lower() in str(nome or "").lower()


def base_da_rede() -> Path:
    do_env = os.getenv("REDE_CONTAS_PAGAR_BASE", "").strip()
    return Path(do_env or _cfg().get("base") or ".")


def credenciais_rede() -> tuple[str, str] | None:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=False)
    for prefixo in ("REDE", "CONTROL_REDE"):
        usuario = os.getenv(f"{prefixo}_USUARIO", "").strip()
        if usuario:
            return usuario, os.getenv(f"{prefixo}_SENHA", "")
    return None


def compartilhamento(caminho: Path | str) -> str | None:
    raiz = Path(caminho).parts[0] if Path(caminho).parts else ""
    return raiz.rstrip("\\/") if raiz.startswith(("\\\\", "//")) else None


_login_rede: dict[str, str | None] = {}


def conectar_rede(base: Path | None = None) -> str | None:
    alvo = compartilhamento(base or base_da_rede())
    if not alvo or os.name != "nt":
        return None
    if alvo in _login_rede:
        return _login_rede[alvo]
    login = credenciais_rede()
    if login is None:
        return None
    try:
        import pywintypes
        import win32netcon
        import win32wnet
    except ImportError:
        _login_rede[alvo] = "pywin32 nao instalado: sem login no compartilhamento"
        return _login_rede[alvo]
    recurso = win32wnet.NETRESOURCE()
    recurso.dwType = win32netcon.RESOURCETYPE_DISK
    recurso.lpRemoteName = alvo
    try:
        win32wnet.WNetAddConnection2(recurso, login[1], login[0], 0)
        resultado = None
    except pywintypes.error as erro:
        if erro.winerror == 1219:
            resultado = None
        elif erro.winerror in (5, 1326):
            resultado = f"o usuario de rede {login[0]} foi recusado em {alvo} ({erro.strerror})"
        else:
            resultado = f"nao abriu {alvo}: {erro.strerror}"
    _login_rede[alvo] = resultado
    return resultado


def motivo_sem_rede(base: Path | None = None) -> str:
    falha = conectar_rede(base)
    if falha:
        return falha
    if credenciais_rede() is None and compartilhamento(base or base_da_rede()):
        return "sem REDE_USUARIO/REDE_SENHA no .env, e o usuario do Windows do servico nao abre a pasta"
    return "a pasta de rede nao responde"


def logar_e_avisar() -> None:
    try:
        falha = conectar_rede()
    except Exception as erro:
        falha = str(erro)
    if falha:
        from loguru import logger

        logger.warning(f"Rede: {falha}")


def rede_responde(base: Path | None = None) -> bool:
    base = base or base_da_rede()
    falha_login = conectar_rede(base)
    try:
        if base.is_dir():
            return True
    except OSError as erro:
        print(f"  [!] pasta de rede sem acesso: {erro}", flush=True)
    if falha_login:
        print(f"  [!] login na rede: {falha_login}", flush=True)
    elif credenciais_rede() is None and compartilhamento(base):
        print("  [!] sem REDE_USUARIO/REDE_SENHA no .env: o acesso e' o do usuario do Windows", flush=True)
    return False


def nome_na_rede(revenda: str | None) -> str | None:
    from core.revendas import nome_oficial

    return nome_oficial(revenda) or revenda


def regras_da_revenda(revenda: str | None) -> dict:
    from core.config import chave_revenda

    regras = dict(_sem_marca(_cfg().get("padrao") or {}))
    procurada = chave_revenda(nome_na_rede(revenda))
    for nome, dados in _sem_marca(_cfg().get("excecoes") or {}).items():
        if chave_revenda(nome) == procurada:
            regras.update(_sem_marca(dados))
            break
    return regras


def _pasta_da_revenda(revenda: str | None) -> Path | None:
    from core.config import chave_revenda

    regras = regras_da_revenda(revenda)
    base = base_da_rede()
    if regras.get("pasta"):
        return base / regras["pasta"]
    oficial = nome_na_rede(revenda)
    procurada = chave_revenda(oficial)
    if not procurada:
        return None
    for p in _subpastas(base):
        if chave_revenda(p.name) == procurada:
            return p
    return base / str(oficial)


def _desativada_desde(extra) -> date | None:
    try:
        return date.fromisoformat(str(extra.get("desativada_desde"))[:10]) if extra.get("desativada_desde") else None
    except ValueError:
        return None


def raizes_da_revenda(revenda: str | None, dia: date | None = None) -> list[Path]:
    pasta = _pasta_da_revenda(revenda)
    if pasta is None:
        return []
    regras = regras_da_revenda(revenda)
    caminhos = [pasta / Path(regras.get("subpasta") or "Contas a Pagar")]
    for extra in regras.get("extras") or []:
        caminho = _caminho_da_extra(pasta, extra)
        desde = _desativada_desde(extra) if isinstance(extra, dict) else None
        if caminho and not (dia is not None and desde is not None and dia >= desde):
            caminhos.append(caminho)
    return caminhos


def _caminho_da_extra(pasta_da_revenda: Path, extra) -> Path | None:
    caminho = extra.get("pasta") if isinstance(extra, dict) else extra
    if not caminho:
        return None
    if isinstance(extra, dict) and extra.get("empresa"):
        return base_da_rede() / str(extra["empresa"]) / Path(caminho)
    return pasta_da_revenda / Path(caminho)


def rotulo_da_raiz(revenda: str | None, raiz: Path) -> str:
    pasta = _pasta_da_revenda(revenda)
    for extra in regras_da_revenda(revenda).get("extras") or []:
        if (
            isinstance(extra, dict)
            and extra.get("rotulo")
            and pasta is not None
            and _caminho_da_extra(pasta, extra) == raiz
        ):
            return str(extra["rotulo"])
    try:
        return raiz.relative_to(pasta).parts[0]
    except (ValueError, IndexError, TypeError):
        return raiz.name


def pastas_do_dia_por_raiz(revenda: str | None, vencimento: date) -> list[tuple[str, Sugestao]]:
    return [
        (rotulo_da_raiz(revenda, raiz), _descer(str(revenda), raiz, vencimento))
        for raiz in raizes_da_revenda(revenda, vencimento)
    ]


def _ano_da_pasta(nome: str) -> int | None:
    achado = re.match(r"^(\d{4})(?!\d)", nome) or re.search(r"\s-\s*(\d{4})$", nome.strip())
    return int(achado.group(1)) if achado else None


def _subpastas(pasta: Path) -> list[Path]:
    _ajustar_prazos()
    chave = f"{pasta}|pastas"
    if chave not in _cache_lista:
        try:
            with os.scandir(pasta) as itens:
                _cache_lista[chave] = sorted(Path(e.path) for e in itens if e.is_dir())
        except OSError:
            _cache_lista[chave] = []
    return _cache_lista[chave]


def _pasta_do_ano(raiz: Path, ano: int) -> Path | None:
    return next((p for p in _subpastas(raiz) if _ano_da_pasta(p.name) == ano), None)


_pastas_da_rede: cachetools.TTLCache = cachetools.TTLCache(maxsize=512, ttl=600)
_trava_das_pastas_da_rede = threading.Lock()
_MES_NO_COMECO = re.compile(r"^(\d{1,2})(?=\D|$)(?![./-]\d)")
_MES_NO_FIM = re.compile(r"_(\d{2})$")


def _arquivo_existe(arquivo: Path) -> bool:
    try:
        return arquivo.is_file()
    except OSError:
        return False


def _mes_da_pasta(nome: str) -> int | None:
    limpo = nome.strip()
    for padrao in (_MES_NO_COMECO, _MES_NO_FIM):
        achado = padrao.search(limpo)
        if achado and 1 <= int(achado.group(1)) <= 12:
            return int(achado.group(1))
    palavras = _palavras_de_letras(limpo)
    for mes in range(1, 13):
        nomes_do_mes = {
            palavra
            for alias in (_cfg().get("meses") or {}).get(str(mes)) or []
            for palavra in _palavras_de_letras(alias)
        }
        if palavras & nomes_do_mes:
            return mes
    return None


def _mesma_pasta(nome_gravado: str, nome_de_agora: str) -> bool:
    ano_gravado, ano_de_agora = _ano_da_pasta(nome_gravado), _ano_da_pasta(nome_de_agora)
    mes_gravado, mes_de_agora = _mes_da_pasta(nome_gravado), _mes_da_pasta(nome_de_agora)
    if ano_gravado and ano_de_agora and ano_gravado != ano_de_agora:
        return False
    if mes_gravado and mes_de_agora and mes_gravado != mes_de_agora:
        return False
    mesmo_ano = bool(ano_gravado) and ano_gravado == ano_de_agora
    mesmo_mes = bool(mes_gravado) and mes_gravado == mes_de_agora
    return mesmo_ano or mesmo_mes


def _pastas_dentro(pasta: Path) -> dict[str, Path]:
    chave = str(pasta).casefold()
    with _trava_das_pastas_da_rede:
        if chave in _pastas_da_rede:
            return _pastas_da_rede[chave]
    try:
        with os.scandir(pasta) as itens:
            dentro = {item.name.casefold(): Path(item.path) for item in itens if item.is_dir()}
    except OSError:
        dentro = {}
    with _trava_das_pastas_da_rede:
        _pastas_da_rede[chave] = dentro
    return dentro


def _achar_com_os_nomes_de_agora(pasta: Path, partes_que_faltam: tuple[str, ...]) -> Path | None:
    if len(partes_que_faltam) == 1:
        arquivo = pasta / partes_que_faltam[0]
        return arquivo if _arquivo_existe(arquivo) else None
    nome_gravado, resto = partes_que_faltam[0], partes_que_faltam[1:]
    dentro = _pastas_dentro(pasta)
    mesma = dentro.get(nome_gravado.casefold())
    candidatas = [mesma] if mesma else [p for p in dentro.values() if _mesma_pasta(nome_gravado, p.name)]
    for candidata in candidatas:
        achado = _achar_com_os_nomes_de_agora(candidata, resto)
        if achado is not None:
            return achado
    return None


def caminho_atual(caminho: str | Path | None) -> Path | None:
    if not caminho:
        return None
    arquivo = Path(caminho)
    if _arquivo_existe(arquivo):
        return arquivo
    partes = arquivo.parts
    if len(partes) < 2:
        return None
    return _achar_com_os_nomes_de_agora(Path(partes[0]), partes[1:])


def _pasta_do_mes(pasta_ano: Path, mes: int) -> Path | None:
    entradas = _subpastas(pasta_ano)
    mes_str = f"{mes:02d}"
    nomes = {p for alias in (_cfg().get("meses") or {}).get(str(mes)) or [] for p in _palavras_de_letras(alias)}
    for e in entradas:
        nome = e.name.upper()
        if nome.startswith(mes_str) or nome.endswith(f"_{mes_str}"):
            return e
    for e in entradas:
        if _palavras_de_letras(e.name) & nomes:
            return e
    return None


def _palavras_de_letras(texto: str) -> set[str]:
    return set(re.findall(r"[A-Z]+", " ".join(_palavras(texto))))


def _pasta_do_dia(pasta_mes: Path, dia: int) -> Path | None:
    entradas = _subpastas(pasta_mes)
    dia_str = f"{dia:02d}"
    for e in entradas:
        if re.match(rf"^(DIA\s*)?{dia_str}\b", e.name, re.IGNORECASE):
            return e
    return None


class Sugestao(NamedTuple):
    achou: bool
    caminho: Path | None
    nivel: str
    motivo: str


def _descer(revenda: str, raiz: Path, vencimento: date, com_ano: bool | None = None) -> Sugestao:
    if com_ano is None:
        com_ano = regras_da_revenda(revenda).get("com_pasta_de_ano", True)
    if not com_ano:
        pasta_ano = raiz
    else:
        pasta_ano = _pasta_do_ano(raiz, vencimento.year)
        if not pasta_ano:
            return Sugestao(False, raiz, "ano", f"não há pasta de {vencimento.year} em {raiz}")

    pasta_mes = _pasta_do_mes(pasta_ano, vencimento.month)
    if not pasta_mes:
        return Sugestao(False, pasta_ano, "mes", f"não há pasta do mês {vencimento.month:02d} em {pasta_ano}")

    pasta_dia = _pasta_do_dia(pasta_mes, vencimento.day)
    if not pasta_dia:
        return Sugestao(False, pasta_mes, "dia", f"não há pasta do dia {vencimento.day:02d} em {pasta_mes}")

    return Sugestao(True, pasta_dia, "dia", "")


def sugerir_pasta(revenda: str | None, vencimento: date) -> Sugestao:
    _ajustar_prazos()
    chave = ("sugestao", str(revenda), vencimento)
    if chave in _cache_pasta:
        return _cache_pasta[chave]
    resultado = _sugerir_pasta(revenda, vencimento)
    _cache_pasta[chave] = resultado
    return resultado


def _sugerir_pasta(revenda: str | None, vencimento: date) -> Sugestao:
    raizes = raizes_da_revenda(revenda, vencimento)
    if not raizes:
        return Sugestao(
            False,
            None,
            "revenda",
            f"a revenda {revenda or '(vazia)'} não tem pasta em config/pastas_rede.json",
        )
    parcial = None
    for raiz in raizes:
        resultado = _descer(str(revenda), raiz, vencimento)
        if resultado.achou:
            return resultado
        parcial = parcial or resultado
    return parcial


class Achado(NamedTuple):
    caminho: Path
    nome: str


_TTL_PADRAO_PASTA = 600.0
_TTL_PADRAO_LISTA = 60.0

_cache_pasta: cachetools.TTLCache = cachetools.TTLCache(maxsize=512, ttl=_TTL_PADRAO_PASTA)
_cache_lista: cachetools.TTLCache = cachetools.TTLCache(maxsize=512, ttl=_TTL_PADRAO_LISTA)


_prazos_lidos: tuple = ()


def _ajustar_prazos() -> None:
    global _prazos_lidos
    cfg = _sem_marca(_cfg().get("cache") or {})
    marca = (cfg.get("pasta_segundos"), cfg.get("listagem_segundos"))
    if marca == _prazos_lidos:
        return
    _prazos_lidos = marca
    for cache, chave, padrao in (
        (_cache_pasta, "pasta_segundos", _TTL_PADRAO_PASTA),
        (_cache_lista, "listagem_segundos", _TTL_PADRAO_LISTA),
    ):
        try:
            novo = float(cfg.get(chave, padrao))
        except (TypeError, ValueError):
            novo = padrao
        if novo > 0 and cache.ttl != novo:
            cache.clear()
            cache._TTLCache__ttl = novo


def esquecer(revenda: str | None = None, vencimento: date | None = None) -> None:
    if revenda is None or vencimento is None:
        _cache_pasta.clear()
        _cache_lista.clear()
        return
    for raiz in raizes_da_revenda(revenda, vencimento):
        onde = _descer(str(revenda), raiz, vencimento)
        if onde.caminho is None:
            continue
        if onde.achou:
            base = str(onde.caminho)
            for chave in [
                c for c in list(_cache_lista) if c == base or c.startswith(base + os.sep) or c.startswith(base + "|")
            ]:
                _cache_lista.pop(chave, None)
        else:
            _cache_lista.pop(f"{onde.caminho}|pastas", None)
    for chave in [c for c in list(_cache_pasta) if str(revenda) in c and vencimento in c]:
        _cache_pasta.pop(chave, None)


def _arquivos_em(pasta: Path) -> list[Path]:
    _ajustar_prazos()
    chave = str(pasta)
    if chave in _cache_lista:
        return _cache_lista[chave]
    try:
        with os.scandir(pasta) as itens:
            arquivos = sorted(Path(e.path) for e in itens if e.is_file())
    except OSError:
        arquivos = []
    _cache_lista[chave] = arquivos
    return arquivos


def _pastas_do_dia(revenda: str | None, vencimento: date) -> list[Path]:
    _ajustar_prazos()
    chave = (str(revenda), vencimento)
    if chave in _cache_pasta:
        return _cache_pasta[chave]
    achadas = []
    for raiz in raizes_da_revenda(revenda, vencimento):
        resultado = _descer(str(revenda), raiz, vencimento)
        if resultado.achou and resultado.caminho is not None:
            achadas.append(resultado.caminho)
    _cache_pasta[chave] = achadas
    return achadas


def subpastas_do_dia(revenda: str | None, vencimento: date) -> tuple[str, ...]:
    return tuple(dict.fromkeys(p.name for pasta in _pastas_do_dia(revenda, vencimento) for p in _subpastas(pasta)))


def procurar(revenda: str | None, vencimento: date, num_doc: str) -> tuple[list[Achado], Sugestao]:
    onde = sugerir_pasta(revenda, vencimento)
    achados = [
        Achado(a, a.name)
        for pasta in _pastas_do_dia(revenda, vencimento)
        for a in _arquivos_em(pasta)
        if casa(num_doc, a.name) or casa_o_boleto(num_doc, a.name)
    ]
    return achados, onde


def regras_do_caixa(revenda: str | None) -> dict:
    from core.config import chave_revenda

    conf = _sem_marca(_cfg().get("caixa_999") or {})
    regras = {k: v for k, v in conf.items() if k != "excecoes"}
    for nome, dados in _sem_marca(conf.get("excecoes") or {}).items():
        if chave_revenda(nome) == chave_revenda(nome_na_rede(revenda)):
            regras.update(_sem_marca(dados))
            break
    return regras


def pasta_do_caixa(revenda: str | None, dia: date) -> Sugestao:
    _ajustar_prazos()
    chave = ("caixa", str(revenda), dia)
    if chave in _cache_pasta:
        return _cache_pasta[chave]
    pasta = _pasta_da_revenda(revenda)
    if pasta is None:
        return Sugestao(False, None, "revenda", f"a revenda {revenda or '(vazia)'} não tem pasta na rede")
    regras = regras_do_caixa(revenda)
    onde = _descer(
        str(revenda),
        pasta / Path(regras.get("subpasta") or "Caixa"),
        dia,
        com_ano=bool(regras.get("com_pasta_de_ano", True)),
    )
    if onde.achou and onde.caminho is not None:
        dentro = {p.name.upper(): p for p in _subpastas(onde.caminho)}
        sub = next((dentro[s.upper()] for s in regras.get("subpastas_do_dia") or [] if s.upper() in dentro), None)
        if sub is not None:
            onde = Sugestao(True, sub, "dia", "")
    _cache_pasta[chave] = onde
    return onde


def esquecer_caixa(revenda: str | None, dia: date) -> None:
    onde = _cache_pasta.pop(("caixa", str(revenda), dia), None)
    if onde is not None and onde.caminho is not None:
        _cache_lista.pop(str(onde.caminho), None)
        _cache_lista.pop(f"{onde.caminho}|pastas", None)
        if onde.achou:
            _cache_lista.pop(f"{onde.caminho.parent}|pastas", None)
    if regras_do_caixa(revenda).get("tambem_no_contas_a_pagar"):
        esquecer(revenda, dia)


def pastas_do_caixa(revenda: str | None, dia: date) -> tuple[list[Path], Sugestao]:
    regras = regras_do_caixa(revenda)
    onde = pasta_do_caixa(revenda, dia)
    pastas = [onde.caminho] if onde.achou and onde.caminho is not None else []
    if regras.get("tambem_no_contas_a_pagar"):
        subs = {s.upper() for s in regras.get("subpastas_do_dia") or []}
        for pasta in _pastas_do_dia(revenda, dia):
            pastas += [p for p in _subpastas(pasta) if p.name.upper() in subs]
    if pastas and not onde.achou:
        onde = Sugestao(True, pastas[0], "dia", "")
    return pastas, onde


def arquivos_da_subpasta_do_caixa(revenda: str | None, dia: date, subpasta: str) -> list[Path]:
    pasta = _pasta_da_revenda(revenda)
    if pasta is None:
        return []
    regras = regras_do_caixa(revenda)
    onde = _descer(
        str(revenda),
        pasta / Path(regras.get("subpasta") or "Caixa"),
        dia,
        com_ano=bool(regras.get("com_pasta_de_ano", True)),
    )
    if not onde.achou or onde.caminho is None:
        return []
    dentro = {p.name.upper(): p for p in _subpastas(onde.caminho)}
    achada = dentro.get(subpasta.upper())
    if achada is None:
        return []
    return [arquivo for arquivo in _arquivos_em(achada) if arquivo.suffix.lower() == ".pdf"]


def arquivos_do_caixa(revenda: str | None, dia: date) -> tuple[list[Achado], Sugestao]:
    pastas, onde = pastas_do_caixa(revenda, dia)
    vistos, arquivos = set(), []
    for pasta in pastas:
        for a in _arquivos_em(pasta):
            if a.suffix.lower() == ".pdf" and a.name.upper() not in vistos:
                vistos.add(a.name.upper())
                arquivos.append(Achado(a, a.name))
    return arquivos, onde


def _palavras(texto) -> list[str]:
    import unicodedata

    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    return re.findall(r"[A-Z0-9]+", sem_acento.upper())


def _sem_repeticao(palavras: list[str], do_control: bool) -> tuple[list[str], int]:
    if not palavras:
        return [], 1
    ultima = palavras[-1]
    if do_control:
        colado = re.fullmatch(r"([A-Z]+)(\d{1,2})", ultima)
        if colado:
            return palavras[:-1] + [colado.group(1)], int(colado.group(2))
    elif len(palavras) > 1 and re.fullmatch(r"\d{1,2}", ultima):
        return palavras[:-1], int(ultima)
    return palavras, 1


def _placa(texto: str) -> str:
    achado = re.search(r"\b([A-Z]{3}) ?(\d[A-Z0-9]\d{2})\b", texto)
    return achado.group(1) + achado.group(2) if achado else ""


def parecido_no_caixa(documento: str, nome_arquivo: str) -> float:
    doc = [p for p in _sem_repeticao(_palavras(documento), do_control=True)[0] if len(p) >= 3]
    nome = _palavras(Path(str(nome_arquivo)).stem)
    if not doc:
        return 0.0
    return sum(any(q.startswith(p) for q in nome) for p in doc) / len(doc)


def _palavra_casa(do_control: str, do_nome: str) -> bool:
    if do_nome.startswith(do_control):
        return True
    if len(do_control) < 4 or do_control[0] != do_nome[0] or len(do_nome) > len(do_control) + 2:
        return False
    restante = iter(do_nome)
    return all(letra in restante for letra in do_control)


def _sobras_no_caixa(documento: str, nome_arquivo: str) -> int | None:
    nome_todo = _palavras(Path(str(nome_arquivo)).stem)
    placa = _placa(" ".join(_palavras(documento)))
    if placa and placa == _placa(" ".join(nome_todo)):
        return 0
    doc, n_doc = _sem_repeticao(_palavras(documento), do_control=True)
    nome, n_nome = _sem_repeticao(nome_todo, do_control=False)
    if not doc or n_doc != n_nome or not any(len(p) >= 3 for p in doc):
        return None
    i, usadas = 0, 0
    for palavra in doc:
        while i < len(nome) and not _palavra_casa(palavra, nome[i]):
            i += 1
        if i == len(nome):
            return None
        i += 1
        usadas += 1
    return sum(1 for p in nome if len(p) > 3) - sum(1 for p in doc if len(p) > 3) if usadas else None


def casa_no_caixa(documento: str, nome_arquivo: str) -> bool:
    return _sobras_no_caixa(documento, nome_arquivo) is not None


def casar_caixa(linhas: list[tuple], nomes: list[str]) -> dict:
    pares = [(s, chave, n) for chave, doc in linhas for n in nomes if (s := _sobras_no_caixa(doc, n)) is not None]
    saida, linhas_usadas, nomes_usados = {}, set(), set()
    for sobras, chave, n in sorted(pares, key=lambda p: p[0]):
        if chave in linhas_usadas or n in nomes_usados:
            continue
        empate = any(
            s == sobras and ((c == chave) != (m == n)) and c not in linhas_usadas and m not in nomes_usados
            for s, c, m in pares
        )
        if empate:
            continue
        saida[chave] = n
        linhas_usadas.add(chave)
        nomes_usados.add(n)
    return saida


def listar_pasta(
    revenda: str | None, vencimento: date, subpastas: tuple[str, ...] = ()
) -> tuple[list[Achado], Sugestao]:
    onde = sugerir_pasta(revenda, vencimento)
    todos = [
        Achado(a, a.name)
        for pasta in _pastas_do_dia(revenda, vencimento)
        for dentro in (pasta, *(pasta / s for s in subpastas))
        for a in _arquivos_em(dentro)
    ]
    return todos, onde


if __name__ == "__main__":
    import argparse

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("revenda", nargs="?")
    a.add_argument("vencimento", nargs="?", help="AAAA-MM-DD")
    a.add_argument("num_doc", nargs="?", help="o documento do ERP (ex.: NFE123456); sem ele, lista a pasta")
    args = a.parse_args() if "__file__" in globals() else a.parse_args([])
    revenda = args.revenda or input("Revenda: ").strip()
    vencimento = date.fromisoformat(args.vencimento or input("Vencimento (AAAA-MM-DD): ").strip())
    num_doc = args.num_doc if args.num_doc is not None else input("Documento (vazio lista a pasta): ").strip()
    achados, onde = procurar(revenda, vencimento, num_doc) if num_doc else listar_pasta(revenda, vencimento)
    print("pasta:", onde.caminho, "|", onde.nivel, "|", onde.motivo)
    for achado in achados:
        print("  ", achado.caminho)
    print(len(achados), "arquivo(s)")
