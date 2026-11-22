from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import NamedTuple

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

CONFIG = "arquivos"


def _cfg() -> dict:
    return carregar_json(CONFIG) or {}


def _sem_marca(valor):
    if isinstance(valor, dict):
        return {k: v for k, v in valor.items() if not k.startswith("_")}
    return valor


def _chave(texto: str | None) -> str:
    sem_acento = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]+", " ", sem_acento.upper()).strip()


def _tokens(texto: str | None) -> set[str]:
    return set(_chave(texto).split())


def _texto_do_nome(nome: str | None) -> str:
    return re.sub(r"(?<=[A-Z])(?=\d)|(?<=\d)(?=[A-Z])", " ", _chave(nome))


def palavras_do_nome(nome: str | None) -> set[str]:
    return set(_texto_do_nome(nome).split())


def _digitos_da_conta(conta: str | None) -> str:
    return re.sub(r"\D", "", str(conta or "")).lstrip("0")


def data_do_nome(nome: str) -> date | None:
    cru = Path(nome).stem
    for achado in re.finditer(r"(?<!\d)(\d{2})(\d{2})(\d{4})(?!\d)", cru):
        dia, mes, ano = (int(p) for p in achado.groups())
        try:
            return date(ano, mes, dia)
        except ValueError:
            continue
    for achado in re.finditer(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)", cru):
        ano, mes, dia = (int(p) for p in achado.groups())
        try:
            return date(ano, mes, dia)
        except ValueError:
            continue
    return None


def nome_padronizado(nome_original: str, revenda: str | None, quando: date | None = None) -> str:
    limpo = Path(nome_original).name
    if not (revenda or "").strip():
        return limpo
    dia = quando or data_do_nome(limpo) or date.today()
    prefixo = _chave(revenda).replace(" ", "_")
    return f"{prefixo}_{dia:%Y%m%d}_{limpo}"


def nome_para_guardar(nome_original: str, revenda: str | None) -> str:
    limpo = Path(nome_original).name
    dono, _como = revenda_do_nome(limpo)
    if dono and revenda and _chave(dono) == _chave(revenda):
        return limpo
    return nome_padronizado(limpo, revenda)


def revenda_do_prefixo(nome: str) -> str | None:
    from core import revendas as cadastro
    from core.config import chave_revenda

    pedacos = Path(nome).name.split("_")
    primeiro = chave_revenda(pedacos[0]).replace(" ", "")
    duas = chave_revenda(" ".join(pedacos[:2]))
    for r in cadastro.REVENDAS:
        oficial = chave_revenda(r.nome)
        if oficial.replace(" ", "") == primeiro or oficial == duas:
            return r.nome
    return None


def revenda_do_nome(nome: str) -> tuple[str | None, str]:
    pelo_prefixo = revenda_do_prefixo(nome)
    if pelo_prefixo:
        return pelo_prefixo, "prefixo do nome"
    sugerida, _motivo = revenda_sugerida_pelo_nome(nome)
    if sugerida:
        return sugerida, "apelido no nome"
    return None, ""


def destino_para_guardar(pasta: Path, nome: str) -> Path:
    alvo = pasta / nome
    alvo.with_suffix(alvo.suffix + ".done").unlink(missing_ok=True)
    return alvo


def revenda_do_conteudo(caminho: Path | str) -> tuple[str | None, str]:
    caminho = Path(caminho)
    if caminho.suffix.lower() not in (".xlsx", ".xlsm"):
        return None, "tipo de arquivo sem identificação interna conhecida"

    cfg = _sem_marca(_cfg().get("planilha_fabrica") or {})
    aba_id = cfg.get("aba_identificacao", "Filtro")
    rotulo = str(cfg.get("rotulo_identificacao", "usu")).lower()

    try:
        import openpyxl

        livro = openpyxl.load_workbook(caminho, data_only=True, read_only=True)
    except Exception as erro:
        return None, f"não deu para abrir a planilha ({str(erro)[:60]})"

    try:
        if aba_id not in livro.sheetnames:
            return None, f"a planilha não tem a aba “{aba_id}”"
        bruto = ""
        for linha in livro[aba_id].iter_rows(values_only=True):
            if linha and linha[0] and str(linha[0]).strip().lower().startswith(rotulo):
                bruto = str(linha[1] or "")
                break
    finally:
        livro.close()

    achado = re.match(r"\s*(\d+)", bruto)
    if not achado:
        return None, "a aba de identificação não traz o código"

    codigo = achado.group(1)
    mapa = _sem_marca(_cfg().get("codigo_sap_por_revenda") or {})
    revenda = mapa.get(codigo)
    if not revenda:
        return None, (f"código {codigo} não está em config/arquivos.json — cadastre o código antes de enviar")
    return revenda, ""


def revenda_pelo_codigo_sap(texto: str | None) -> tuple[str | None, str]:
    mapa = _sem_marca(_cfg().get("codigo_sap_por_revenda") or {})
    achados = sorted({n.lstrip("0") for n in re.findall(r"(?<!\d)\d{6,10}(?!\d)", texto or "")} & set(mapa))
    donas = {mapa[c] for c in achados}
    if len(donas) != 1:
        return None, ""
    return donas.pop(), achados[0]


def de_outra_revenda(nome: str, revendas: list[str] | None) -> bool:
    if not revendas:
        return False
    dono, _como = revenda_do_nome(nome)
    if not dono:
        return False
    from core.config import chave_revenda

    return chave_revenda(dono) not in {chave_revenda(r) for r in revendas}


def impressao_da_identificacao() -> str:
    from core import leituras

    cfg = _cfg()
    return leituras.impressao(
        leituras.sem_comentarios(carregar_json("revendas_cnpj") or {}),
        leituras.sem_comentarios(carregar_json("contas_bancarias") or {}),
        leituras.sem_comentarios(
            {c: cfg.get(c) for c in ("apelidos_no_nome", "apelido_colado", "codigo_sap_por_revenda")}
        ),
    )


def revenda_sugerida_pelo_nome(nome: str) -> tuple[str | None, str]:
    texto = _texto_do_nome(nome)
    palavras = set(texto.split())
    colado = texto.replace(" ", "")
    minimo = int(_sem_marca(_cfg().get("apelido_colado") or {}).get("minimo_de_letras") or 0)
    achadas = set()
    for revenda, apelidos in _sem_marca(_cfg().get("apelidos_no_nome") or {}).items():
        for apelido in apelidos or []:
            marca = _chave(apelido)
            junto = marca.replace(" ", "")
            if ((marca in texto) if " " in marca else (marca in palavras)) or (
                minimo and len(junto) >= minimo and junto in colado
            ):
                achadas.add(revenda)
                break
    if len(achadas) != 1:
        return None, ("nenhuma" if not achadas else "mais de uma")
    return achadas.pop(), ""


def revenda_da_conta(banco: str | None, conta: str | None) -> str | None:
    alvo = _digitos_da_conta(conta)
    if not alvo:
        return None
    catalogo = carregar_json("contas_bancarias") or {}
    nome_banco = " ".join(_chave(banco).lower().split())
    apelidos = _sem_marca(catalogo.get("apelidos") or {})
    for grafia in sorted(apelidos, key=len, reverse=True):
        if nome_banco == grafia or nome_banco.startswith(grafia + " "):
            nome_banco = apelidos[grafia]
            break
    donas = {
        regra["revenda"]
        for regra in catalogo.get("contas") or []
        if _digitos_da_conta(regra.get("conta")) == alvo
        and nome_banco.startswith(" ".join(_chave(regra.get("banco")).lower().split()))
    }
    return donas.pop() if len(donas) == 1 else None


class Veredito(NamedTuple):
    aceito: bool
    nome: str
    erro: str
    aviso: str


def avaliar(nome_original: str, caminho_temporario: Path | str, revenda_da_url: str | None) -> Veredito:
    limpo = Path(nome_original).name
    if not (revenda_da_url or "").strip():
        return Veredito(True, limpo, "", "sem revenda na URL — nome mantido")
    from core.config import empresas_da_url

    empresas = empresas_da_url(revenda_da_url) or []
    revenda_da_url = empresas[0].nome if len(empresas) == 1 else revenda_da_url

    dono, _motivo = revenda_do_conteudo(caminho_temporario)
    if dono and _chave(dono) != _chave(revenda_da_url):
        return Veredito(
            False,
            limpo,
            f"o conteúdo diz que este arquivo é da {dono}, e a tela aberta é da {revenda_da_url}. Nada foi gravado.",
            "",
        )

    aviso = ""
    pelo_nome, _ = revenda_sugerida_pelo_nome(limpo)
    if pelo_nome and _chave(pelo_nome) != _chave(revenda_da_url):
        aviso = (
            f"o nome do arquivo cita “{pelo_nome}”, mas ele foi guardado na "
            f"{revenda_da_url} (a revenda da tela). Confira se é o arquivo certo."
        )

    return Veredito(True, nome_para_guardar(limpo, revenda_da_url), "", aviso)


if __name__ == "__main__":
    import argparse

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("arquivo", nargs="?")
    args = a.parse_args() if "__file__" in globals() else a.parse_args([])
    caminho = Path(args.arquivo or input("Caminho do arquivo: ").strip().strip('"'))
    print("pelo nome:     ", revenda_do_nome(caminho.name))
    print("pelo conteudo: ", revenda_do_conteudo(caminho))
    print("data do nome:  ", data_do_nome(caminho.name))
