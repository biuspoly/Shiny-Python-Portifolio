"""Vitrine do portfólio: a página de entrada, com um cartão por app.

Exportada pelo Shinylive para a raiz do site (publicar/montar_site.py). Cada botão leva ao endereço
do app no Posit Connect Cloud (enderecos.json) ou, sem endereço, à cópia dele no Shinylive.
"""

import json
from pathlib import Path

from shiny import App, ui

PASTA = Path(__file__).parent
ENDERECOS = json.loads((PASTA / "enderecos.json").read_text(encoding="utf-8"))
SITE = ENDERECOS["site"]

APPS_PYTHON = [
    {
        "pasta": "Comercial",
        "nome": "Comercial",
        "cor": "#06825d",
        "imagem": "comercial.webp",
        "resumo": "Vendas do mês contra a meta, por categoria, produto e cliente.",
        "telas": [
            "Diário de Vendas: tendência, meta, cobertura e histórico de 24 meses no gráfico",
            "Curva ABC de clientes com filtros em cascata",
            "Mapa Comercial: potencial e cobertura por município, sobre a malha e a população do IBGE",
        ],
    },
    {
        "pasta": "Logistico",
        "nome": "Logístico",
        "cor": "#254d71",
        "imagem": "logistico.webp",
        "resumo": "Frota, comodato de equipamentos, entregas e devoluções de quatro revendas.",
        "telas": [
            "Frota: débitos, multas, restrições, combustível e mapa do último abastecimento",
            "Entrada e saída de veículos, com transferência e motivo de saída",
            "Comodato: solicitação com as travas do cliente, envio do pedido, documentos do CEV e recolha",
            "Planilha de Entregas, preenchida pelo próprio formulário",
            "Devoluções: detalhes, caixas, valores e rankings",
        ],
    },
    {
        "pasta": "Financeiro",
        "nome": "Financeiro",
        "cor": "#5b3a78",
        "imagem": "financeiro.webp",
        "resumo": "O dia do financeiro: saldos, o que pagar e a posição com a fábrica.",
        "telas": [
            "Diário Financeiro: saldo de cada banco e a composição financeira do dia, item a item",
            "Contas a Pagar com auditoria, marcação e envio dos pagamentos; Pagamentos e Dados Manuais",
            "Fluxo Financeiro: crédito, débitos por vencimento e empréstimos entre revendas, com histórico diário",
            "Empréstimos, juros justificados e o extrato dos bancos com a baixa linha a linha",
        ],
    },
    {
        "pasta": "Fiscal",
        "nome": "Fiscal",
        "cor": "#2e2b6b",
        "imagem": "fiscal.webp",
        "resumo": "Apuração dos livros fiscais e relatórios.",
        "telas": [
            "Apuração do ICMS por CFOP e por operação",
            "Livro fiscal item a item, com filtros e exportação",
            "Receita bruta e PIS/COFINS mês a mês",
            "Demonstrativo de Faturamento em PDF",
        ],
    },
    {
        "pasta": "Monitoramento",
        "nome": "Monitoramento",
        "cor": "#7a2e1d",
        "imagem": "monitoramento.webp",
        "resumo": "Saúde dos apps, lida dos logs de telemetria de cada um.",
        "telas": [
            "Situação dos apps e sessões abertas por hora",
            "Quem está conectado e em qual tela",
            "Erros com o detalhe, tempo de resposta e rotinas da madrugada",
        ],
    },
    {
        "pasta": "Acessos",
        "nome": "Acessos",
        "cor": "#3e2352",
        "imagem": "acessos.webp",
        "resumo": "Quem pode ver cada painel e quem de fato entra.",
        "telas": [
            "Acesso por painel, com conceder e retirar",
            "Visão geral: tendência de acessos e dias sem acesso de cada pessoa",
            "Histórico de acessos por hora",
        ],
    },
]

APPS_R = [
    {
        "pasta": "Comercial",
        "nome": "Comercial (R)",
        "cor": "#06825d",
        "imagem": "r_comercial.webp",
        "resumo": "O Diário de Venda e o Mapa Comercial originais.",
        "telas": [
            "Diário de Venda com metas, tendência, cobertura, indicadores e os gráficos de histórico",
            "Mapa Comercial: potencial e cobertura por município com Leaflet e sf",
        ],
    },
    {
        "pasta": "Logistico",
        "nome": "Logístico (R)",
        "cor": "#254d71",
        "imagem": "r_logistico.webp",
        "resumo": "Frota, entregas, devoluções e comodato, como eram em R.",
        "telas": [
            "Frota: geral, entrada e saída de veículos",
            "Planilha de Entregas e Devoluções (detalhes, caixas, valores e gráficos)",
            "Comodato: solicitação, pedido, documentos, recolha com distrato em PDF e saldo de vasilhames",
        ],
    },
    {
        "pasta": "Acessos",
        "nome": "Acessos (R)",
        "cor": "#3e2352",
        "imagem": "r_acessos.webp",
        "resumo": "O painel de logs e permissões original.",
        "telas": [
            "Visão geral com a tendência de acessos e os dias sem acesso",
            "Acessos, usuários e permissões por painel",
        ],
    },
]

SELOS = [
    "Shiny for Python",
    "Polars",
    "DuckDB",
    "ECharts (pyecharts)",
    "Folium / Leaflet",
    "Posit Connect Cloud",
    "Shinylive (WebAssembly)",
    "GitHub Actions",
]

COMO_FOI_FEITO = [
    (
        "As telas de produção",
        "Cada tela é o módulo do sistema real (interface, regras e consultas), só com as integrações trocadas: "
        "ERP, banco ao vivo e login saem, e o que a tela grava fica na memória da sessão.",
    ),
    (
        "Dados fictícios no formato real",
        "Um gerador com semente fixa cria os caches Parquet com as mesmas colunas da produção. As telas leem com "
        "Polars e DuckDB, sem saber que os dados são inventados. Toda semana um workflow refaz tudo.",
    ),
    (
        "Onde roda",
        "Cada app é publicado direto do GitHub no Posit Connect Cloud; o que ainda não está lá roda no próprio "
        "navegador pelo Shinylive (Pyodide e webR). Esta página também é um app Shiny, pelo Shinylive.",
    ),
    (
        "Um padrão para os seis",
        "Menu lateral, filtros, cartões, tabelas paginadas e gráficos seguem o mesmo desenho em todos os apps; "
        "só a paleta muda.",
    ),
]


def endereco_posit(linguagem: str, pasta: str) -> str | None:
    """O endereço do app no Posit: o próprio, ou a rota dele no app unificado (Acompanhamentos).
    Mesma regra do publicar/montar_site.py (a vitrine roda sozinha no Shinylive e não importa de lá)."""
    proprio = ENDERECOS[linguagem].get(pasta)
    if proprio:
        return proprio
    unificado = (ENDERECOS.get("acompanhamentos") or {}).get(linguagem)
    if not unificado:
        return None
    base = unificado.rstrip("/")
    return f"{base}/{pasta.lower()}/" if linguagem == "python" else f"{base}/?painel={pasta.lower()}"


def endereco(linguagem: str, pasta: str) -> str:
    """Endereço do Posit, ou o do Shinylive (absoluto: a vitrine roda num iframe do Shinylive)."""
    posit = endereco_posit(linguagem, pasta)
    if posit:
        return posit
    return f"{SITE}{'r/' if linguagem == 'r' else ''}{pasta.lower()}/"


def cartao(app: dict, linguagem: str):
    no_posit = bool(endereco_posit(linguagem, app["pasta"]))
    return ui.card(
        ui.tags.img(src=f"img/{app['imagem']}", alt=f"Tela do {app['nome']}", class_="app-foto"),
        ui.card_body(
            ui.h2(app["nome"]),
            ui.p(app["resumo"], class_="app-resumo"),
            ui.tags.ul(*[ui.tags.li(tela) for tela in app["telas"]]),
        ),
        ui.card_footer(
            ui.tags.a(
                f"Abrir o {app['nome']}",
                href=endereco(linguagem, app["pasta"]),
                target="_blank" if no_posit else "_top",
                class_="btn app-botao",
            ),
            ui.span("servidor" if no_posit else "no navegador", class_="app-onde"),
        ),
        class_="app",
        style=f"--cor: {app['cor']}",
    )


app_ui = ui.page_bootstrap(
    ui.head_content(
        ui.tags.meta(
            name="description",
            content="Portfólio de Marlon Amaral: telas reais de painéis de gestão em Shiny for Python e R, "
            "com dados fictícios.",
        ),
        ui.tags.link(rel="icon", href="img/icone.svg", type="image/svg+xml"),
        ui.include_css(PASTA / "www" / "vitrine.css"),
    ),
    ui.tags.header(
        ui.div(
            ui.div(ui.tags.img(src="img/icone.svg", alt=""), ui.span("Portfólio Marlon Amaral"), class_="marca"),
            ui.h1("Painéis de gestão em Shiny for Python"),
            ui.p(
                "Telas de um sistema que eu desenvolvi e mantenho em produção numa distribuidora de bebidas: "
                "comercial, logística, financeiro, fiscal e a administração dos próprios painéis. O código das "
                "telas é o mesmo de lá; os dados são fictícios, gerados no formato original, com alguns dados "
                "públicos de verdade (IBGE).",
                class_="lead",
            ),
            ui.div(*[ui.span(selo, class_="badge rounded-pill selo") for selo in SELOS], class_="selos"),
            class_="conteudo",
        ),
        class_="topo",
    ),
    ui.tags.main(
        ui.card(
            ui.card_body(
                ui.tags.strong("Onde cada app roda."),
                ui.p(
                    "Os apps marcados como servidor abrem no Posit Connect Cloud; se ninguém o usou há algum "
                    "tempo, a primeira abertura acorda o servidor. Os marcados como navegador carregam o Python "
                    "(ou o R) na própria página: a primeira vez leva de 15 a 60 segundos. O que se grava na tela "
                    "(uma justificativa, uma marcação, uma permissão) vale até a página fechar.",
                ),
            ),
            class_="aviso conteudo",
        ),
        ui.div(
            ui.layout_column_wrap(*[cartao(app, "python") for app in APPS_PYTHON], width="340px", gap="1.5rem"),
            ui.tags.section(
                ui.h2("Versão original em R"),
                ui.p(
                    "Antes do Python, o mesmo sistema existiu em R Shiny (bs4Dash, reactable, DuckDB), escrito e "
                    "mantido sozinho. Estes três apps são o código original, com as mesmas telas: só a leitura do "
                    "MySQL foi trocada pelos mesmos dados fictícios em Parquet.",
                    class_="intro",
                ),
                class_="tecnica",
            ),
            ui.layout_column_wrap(*[cartao(app, "r") for app in APPS_R], width="340px", gap="1.5rem"),
            ui.tags.section(
                ui.h2("Como foi feito"),
                ui.layout_column_wrap(
                    *[
                        ui.card(ui.card_body(ui.h3(titulo), ui.p(texto)), class_="bloco")
                        for titulo, texto in COMO_FOI_FEITO
                    ],
                    width="260px",
                    gap="1.25rem",
                ),
                class_="tecnica",
            ),
            class_="conteudo",
        ),
    ),
    ui.tags.footer(
        "Marlon Amaral · código em ",
        ui.tags.a(
            "github.com/biuspoly/shiny-portfolio",
            href="https://github.com/biuspoly/shiny-portfolio",
            target="_blank",
        ),
        ui.br(),
        "As revendas, marcas, clientes e pessoas que aparecem nos painéis são fictícios.",
    ),
    title="Portfólio Marlon Amaral | Painéis em Shiny for Python",
    lang="pt-BR",
)


def server(input, output, session):
    pass


app = App(app_ui, server, static_assets=PASTA / "www")
