"""Peças de tela comuns às páginas do Fiscal, no mesmo desenho do Diário de Vendas do Comercial:
cartões no topo, tabela neutra com as colunas principais em azul suave e vermelho só no texto."""

from __future__ import annotations

from shiny import ui

from core.cores import CORES_ETAPA

OPCOES_SELECTIZE = {"dropdownParent": "body", "dropdownClass": "selectize-dropdown dv-selectize-dropdown"}
OPCOES_MULTIPLO = {**OPCOES_SELECTIZE, "placeholder": "Todos", "plugins": ["remove_button"]}


def cartao(titulo, valor, sub="", classe_sub="kpi-delta-neutro", destaque=False):
    return ui.div(
        ui.div(titulo, class_="dv-kpi-titulo"),
        ui.div(valor, class_="dv-kpi-valor"),
        ui.span(sub, class_=f"kpi-delta {classe_sub}"),
        class_="dv-kpi dv-kpi-destaque" if destaque else "dv-kpi",
    )


def selo_etapa(etapa: str) -> ui.Tag:
    cor = CORES_ETAPA.get(etapa, "#64748B")
    return ui.span(etapa, class_="fs-selo", style=f"--cor-selo: {cor}")


def css_tabela(seletor: str, larguras: list[int], chave: tuple[int, ...] = (), esquerda: tuple[int, ...] = ()) -> str:
    """Largura de cada coluna (sem isto a grade dá a mesma largura a todas e corta o fim), colunas-chave em
    azul suave e colunas de texto alinhadas à esquerda. Posições começam em 1."""
    regras = [
        f"{seletor} table th:nth-child({i}), {seletor} table td:nth-child({i}) {{ width: {px}px !important; }}"
        for i, px in enumerate(larguras, start=1)
    ]
    if chave:
        regras.append(
            ", ".join(f"{seletor} table thead th:nth-child({i})" for i in chave)
            + " { background-color: #E6F0FA !important; color: #0B4A85 !important; }"
        )
        regras.append(
            ", ".join(f"{seletor} table tbody td:nth-child({i})" for i in chave) + " { background-color: #F5F9FD; }"
        )
    if esquerda:
        regras.append(
            ", ".join(f"{seletor} table th:nth-child({i}), {seletor} table td:nth-child({i})" for i in esquerda)
            + " { text-align: left !important; }"
        )
    return "\n".join(regras)


def legenda(*partes) -> ui.Tag:
    return ui.div(*partes, class_="dv-legenda")


CSS_FISCAL = """
.dv-modulo .fs-selo {
  display: inline-block; padding: 0 8px; border-radius: 10px; font-size: 0.9em; font-weight: 600;
  color: var(--cor-selo); border: 1px solid var(--cor-selo); background: #fff; line-height: 1.5;
}
.dv-modulo .fs-detalhe { display: grid; grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr)); gap: 6px 18px;
  font-size: 0.85rem; margin-bottom: 10px; }
.dv-modulo .fs-detalhe b { color: #64748B; font-weight: 600; display: block; font-size: 0.72rem; text-transform: uppercase; }
.dv-modulo .fs-chave { font-family: ui-monospace, Consolas, monospace; letter-spacing: 0.02em; }
.dv-modulo .fs-acoes { display: flex; gap: 8px; margin: 6px 0 12px; }
.dv-modulo .fs-dica { color: #64748B; font-size: 0.85rem; padding: 6px 2px; }
.fs-xml { max-height: 65vh; overflow: auto; background: #0F172A; color: #E2E8F0; padding: 12px; border-radius: 8px;
  font-size: 0.75rem; white-space: pre; }
"""
