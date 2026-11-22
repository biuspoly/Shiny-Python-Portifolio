from __future__ import annotations

import hashlib
import json
from pathlib import Path

import polars as pl

from core.compat import gravar_parquet, ler_parquet  # noqa: E402

PASTA = Path(__file__).resolve().parent.parent / "data" / "leituras"

COL_ARQUIVO = "_ARQUIVO"
COL_TAMANHO = "_TAMANHO"
COL_MTIME = "_MTIME"
IDENTIDADE = (COL_ARQUIVO, COL_TAMANHO, COL_MTIME)

BLOCO_VISTOS = "vistos"

BLOCO_AVISOS = "avisos"
CHAVE_AVISOS = "_avisos"
COL_AVISO = "AVISO"
COL_IMPRESSAO = "_IMPRESSAO"


def sem_comentarios(valor):
    if isinstance(valor, dict):
        return {k: sem_comentarios(v) for k, v in valor.items() if not str(k).startswith("_")}
    if isinstance(valor, list):
        return [sem_comentarios(v) for v in valor]
    return valor


def impressao(*regras) -> str:
    bruto = json.dumps(regras, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()[:16]


def _caminho(assunto: str, bloco: str) -> Path:
    return PASTA / f"{assunto}__{bloco}.parquet"


def identidade(caminho: Path) -> tuple[str, int, int]:
    info = caminho.stat()
    return caminho.name, int(info.st_size), int(info.st_mtime_ns)


def _ler(caminho: Path) -> pl.DataFrame:
    if not caminho.exists():
        return pl.DataFrame()
    try:
        return ler_parquet(caminho)
    except Exception as erro:
        print(f"  aviso: registro de leituras ilegível ({caminho.name}): {str(erro)[:120]} -- relendo tudo")
        return pl.DataFrame()


class Registro:
    def __init__(
        self,
        assunto: str,
        blocos: tuple[str, ...],
        reler_vazio: bool = False,
        podar: bool = True,
        versao: str = "",
        impressao_vazio: str = "",
    ):
        self.assunto = assunto
        self.versao = versao
        self.blocos = tuple(blocos)
        self.reler_vazio = reler_vazio
        self.impressao_vazio = impressao_vazio
        self._guardados = self.blocos + (BLOCO_AVISOS,)
        self.podar = podar
        self.reaproveitados = 0
        self.lidos = 0
        self._vistos_antes: set[tuple[str, int, int]] = set()
        self._antes: dict[str, pl.DataFrame] = {}
        self._agora: dict[str, list[pl.DataFrame]] = {b: [] for b in self._guardados}
        self._vistos_agora: list[tuple[str, int, int]] = []
        self._carregar()

    def _carregar(self) -> None:
        marca = PASTA / f"{self.assunto}__versao.txt"
        if self.versao and (not marca.exists() or marca.read_text(encoding="utf-8").strip() != self.versao):
            print(f"  registro de leituras de {self.assunto}: as regras mudaram -- relendo tudo")
            return
        vistos = _ler(_caminho(self.assunto, BLOCO_VISTOS))
        if not vistos.is_empty() and all(c in vistos.columns for c in IDENTIDADE):
            self._vistos_antes = {(n, int(t), int(m)) for n, t, m in vistos.select(IDENTIDADE).iter_rows()}
        for bloco in self._guardados:
            self._antes[bloco] = _ler(_caminho(self.assunto, bloco))

    def _linhas_de(self, bloco: str, chave: tuple[str, int, int]) -> pl.DataFrame:
        base = self._antes.get(bloco)
        if base is None or base.is_empty():
            return pl.DataFrame()
        if not all(c in base.columns for c in IDENTIDADE):
            return pl.DataFrame()
        nome, tamanho, mtime = chave
        return base.filter(
            (pl.col(COL_ARQUIVO) == nome) & (pl.col(COL_TAMANHO) == tamanho) & (pl.col(COL_MTIME) == mtime)
        )

    def pegar(self, caminho: Path, reler_se=None, valido=None) -> dict[str, list[dict]] | None:
        try:
            chave = identidade(caminho)
        except OSError:
            return None
        if chave not in self._vistos_antes:
            return None
        guardados = self._linhas_de(BLOCO_AVISOS, chave)
        if reler_se and not guardados.is_empty() and reler_se(guardados[COL_AVISO].to_list()):
            return None
        partes = {bloco: self._linhas_de(bloco, chave) for bloco in self.blocos}
        if (
            self.reler_vazio
            and not guardados.is_empty()
            and all(p.is_empty() for p in partes.values())
            and (
                not self.impressao_vazio
                or COL_IMPRESSAO not in guardados.columns
                or guardados[COL_IMPRESSAO].to_list() != [self.impressao_vazio] * guardados.height
            )
        ):
            return None
        saida: dict[str, list[dict]] = {
            bloco: [] if parte.is_empty() else parte.drop(IDENTIDADE, strict=False).to_dicts()
            for bloco, parte in partes.items()
        }
        saida[CHAVE_AVISOS] = [] if guardados.is_empty() else guardados[COL_AVISO].to_list()
        if valido is not None and not valido(saida):
            return None
        self.reaproveitados += 1
        self._vistos_agora.append(chave)
        for bloco, parte in partes.items():
            if not parte.is_empty():
                self._agora[bloco].append(parte)
        if not guardados.is_empty():
            self._agora[BLOCO_AVISOS].append(guardados)
        return saida

    def guardar(
        self,
        caminho: Path,
        blocos: dict[str, list[dict]],
        avisos: list[str] | tuple[str, ...] = (),
    ) -> None:
        self.lidos += 1
        try:
            chave = identidade(caminho)
        except OSError:
            return
        nome, tamanho, mtime = chave
        self._vistos_agora.append(chave)
        for bloco in self.blocos:
            linhas = blocos.get(bloco) or []
            if not linhas:
                continue
            tabela = pl.DataFrame(linhas, infer_schema_length=None).with_columns(
                pl.lit(nome).alias(COL_ARQUIVO),
                pl.lit(tamanho).alias(COL_TAMANHO),
                pl.lit(mtime).alias(COL_MTIME),
            )
            self._agora[bloco].append(tabela)
        if avisos:
            self._agora[BLOCO_AVISOS].append(
                pl.DataFrame(
                    {
                        COL_AVISO: list(avisos),
                        COL_ARQUIVO: [nome] * len(avisos),
                        COL_TAMANHO: [tamanho] * len(avisos),
                        COL_MTIME: [mtime] * len(avisos),
                        COL_IMPRESSAO: [self.impressao_vazio] * len(avisos),
                    }
                )
            )

    def fechar(self) -> None:
        PASTA.mkdir(parents=True, exist_ok=True)
        if self.versao:
            (PASTA / f"{self.assunto}__versao.txt").write_text(self.versao, encoding="utf-8")
        vistos = self._vistos_agora
        if not self.podar:
            ja_vistos = set(vistos)
            vistos = vistos + [c for c in self._vistos_antes if c not in ja_vistos]
        self._gravar(
            BLOCO_VISTOS,
            pl.DataFrame(vistos, schema=list(IDENTIDADE), orient="row") if vistos else pl.DataFrame(),
        )
        for bloco in self._guardados:
            partes = list(self._agora[bloco])
            antes = self._antes.get(bloco)
            if (
                not self.podar
                and antes is not None
                and not antes.is_empty()
                and all(c in antes.columns for c in IDENTIDADE)
            ):
                if self._vistos_agora:
                    antes = antes.with_columns(
                        pl.col(COL_TAMANHO).cast(pl.Int64),
                        pl.col(COL_MTIME).cast(pl.Int64),
                    ).join(
                        pl.DataFrame(self._vistos_agora, schema=list(IDENTIDADE), orient="row"),
                        on=list(IDENTIDADE),
                        how="anti",
                    )
                if not antes.is_empty():
                    partes.append(antes)
            self._gravar(
                bloco,
                pl.concat(partes, how="diagonal_relaxed") if partes else pl.DataFrame(),
            )

    def _gravar(self, bloco: str, tabela: pl.DataFrame) -> None:
        caminho = _caminho(self.assunto, bloco)
        if tabela.is_empty():
            caminho.unlink(missing_ok=True)
            return
        try:
            gravar_parquet(tabela, caminho)
        except Exception as erro:
            print(f"  aviso: não deu para gravar o registro de leituras ({caminho.name}): {str(erro)[:120]}")

    def resumo(self, de_outras: int = 0) -> str:
        total = self.lidos + self.reaproveitados
        outras = (
            (f", {de_outras} de outra(s) revenda(s) pelo nome, deixado(s) para o Atualizar dela(s)")
            if de_outras
            else ""
        )
        return (
            f"  {total} arquivo(s): {self.lidos} lido(s) agora, "
            f"{self.reaproveitados} reaproveitado(s) do registro{outras}"
        )
