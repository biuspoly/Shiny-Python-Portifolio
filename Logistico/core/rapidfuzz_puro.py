"""As três medidas do rapidfuzz que a Solicitação usa, em Python puro, com as mesmas assinaturas.
Só entram no Shinylive, onde o rapidfuzz (compilado) não existe; fora dele vale o pacote."""

from __future__ import annotations

from difflib import SequenceMatcher


class Levenshtein:
    @staticmethod
    def distance(a: str, b: str, score_cutoff: int | None = None) -> int:
        anterior = list(range(len(b) + 1))
        for i, ca in enumerate(a, start=1):
            atual = [i]
            for j, cb in enumerate(b, start=1):
                atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
            anterior = atual
        distancia = anterior[-1]
        if score_cutoff is not None and distancia > score_cutoff:
            return score_cutoff + 1
        return distancia


class JaroWinkler:
    @staticmethod
    def similarity(a: str, b: str, prefix_weight: float = 0.1) -> float:
        if a == b:
            return 1.0
        if not a or not b:
            return 0.0
        janela = max(max(len(a), len(b)) // 2 - 1, 0)
        marcas_a, marcas_b = [False] * len(a), [False] * len(b)
        iguais = 0
        for i, ca in enumerate(a):
            for j in range(max(0, i - janela), min(len(b), i + janela + 1)):
                if not marcas_b[j] and b[j] == ca:
                    marcas_a[i] = marcas_b[j] = True
                    iguais += 1
                    break
        if not iguais:
            return 0.0
        trocas, k = 0, 0
        for i, marcado in enumerate(marcas_a):
            if marcado:
                while not marcas_b[k]:
                    k += 1
                trocas += a[i] != b[k]
                k += 1
        jaro = (iguais / len(a) + iguais / len(b) + (iguais - trocas / 2) / iguais) / 3
        prefixo = 0
        for ca, cb in zip(a[:4], b[:4]):
            if ca != cb:
                break
            prefixo += 1
        return jaro + prefixo * prefix_weight * (1 - jaro)

    @staticmethod
    def distance(a: str, b: str) -> float:
        return 1.0 - JaroWinkler.similarity(a, b)


class fuzz:  # noqa: N801 -- mesmo nome do módulo do rapidfuzz
    @staticmethod
    def partial_ratio(a: str, b: str, score_cutoff: float = 0) -> float:
        curta, longa = (a, b) if len(a) <= len(b) else (b, a)
        if not curta:
            return 0.0
        melhor = (
            max(
                SequenceMatcher(None, curta, longa[i : i + len(curta)]).ratio()
                for i in range(len(longa) - len(curta) + 1)
            )
            * 100
        )
        return melhor if melhor >= score_cutoff else 0.0
