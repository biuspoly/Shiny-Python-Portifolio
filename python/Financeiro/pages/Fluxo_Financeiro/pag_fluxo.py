import json
import re
from datetime import date

import polars as pl
from faicons import icon_svg
from shiny import module, reactive, render, ui

from core import manual_arquivo
from core.atualizacao import carimbos_das_tabelas
from core.auth import identificar_usuario
from core.aviso import modal_aviso
from core.config import pode, quem_libera
from core.secao import ICONE_FLUXO_FABRICA, titulo_secao
from pages.PPF.Dados import dados_ppf as dp

from .Dados import dados_fluxo_consolidado as f

VALOR_NAVSET = "flx"

ARQUIVOS_DO_FLUXO = ("extratos_fabricas_totais", "extratos_fabricas_tabela", "emprestimos_revendas", "contas_pagar")
SEGUNDOS_ENTRE_CONFERENCIAS = 15


def _carimbos_dos_arquivos() -> tuple:
    return tuple(sorted(carimbos_das_tabelas(dp.PASTA_PARQUET, *ARQUIVOS_DO_FLUXO).items()))


TIPOS_MARCAVEIS = {"debito_detalhe", "credito"}
_CLASSE_DA_LINHA = {
    "limite": "linha-limite",
    "credito": "linha-credito",
    "espaco": "linha-espaco",
    "debitos": "linha-debitos",
    "subtotal_debitos_mar": "linha-subtotal-debitos-mar",
    "emprestimo_debito": "linha-debitos",
    "emprestimo_credito": "linha-debitos",
    "emprestimo_saldo": "linha-debitos",
    "total_debitos_clientes": "linha-debitos",
}
MAX_LINHAS, MAX_COLUNAS = 120, 16

ICONE_EXCEL = "img/ppf/excel-verde.svg"


def _link_da_nota(item: dict, url_pdf: str | None):
    if item.get("pdf") and url_pdf:
        emenda = "&" if "?" in url_pdf else "?"
        return ui.tags.a(
            icon_svg("file-pdf", a11y="deco"),
            href=f"{url_pdf}{emenda}chave={item['pdf']}",
            target="_blank",
            rel="noopener noreferrer",
            title="Abrir o PDF da nota",
        )
    if item.get("consultar"):
        return ui.tags.a(
            icon_svg("up-right-from-square", a11y="deco"),
            href=item["consultar"],
            target="_blank",
            rel="noopener noreferrer",
            title="Consultar DANFE",
        )
    return "-"


_MESES = (
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)


def _numero_do_texto(texto) -> float:
    limpo = re.sub(r"[^\d,-]", "", str(texto or ""))
    try:
        return float(limpo.replace(",", ".")) if limpo.strip("-") else 0.0
    except ValueError:
        return 0.0


def _em_reais(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def _meses_dos_movimentos(movimentos: list[dict]) -> list[dict]:
    grupos: dict[str, dict] = {}
    for mov in movimentos:
        achado = re.fullmatch(r"\d{2}/(\d{2})/(\d{4})", str(mov.get("data") or "").strip())
        mes = int(achado.group(1)) if achado else 0
        chave = f"{achado.group(2)}-{mes:02d}" if achado and 1 <= mes <= 12 else ""
        grupo = grupos.setdefault(
            chave,
            {
                "mes": chave,
                "entradas": 0.0,
                "saidas": 0.0,
                "itens": [],
                "rotulo": f"{_MESES[mes - 1]}/{achado.group(2)}" if chave else "Sem data",
            },
        )
        grupo["itens"].append(mov)
        if mov.get("tipo") in ("entrada", "saida"):
            grupo["entradas" if mov["tipo"] == "entrada" else "saidas"] += abs(_numero_do_texto(mov.get("valor")))
    return [grupos[c] for c in sorted(grupos, key=lambda c: (c != "", c), reverse=True)]


def _movimentos_por_mes(movimentos: list[dict]):
    def _soma(valor: float, classe: str):
        return ui.tags.td(_em_reais(valor) if valor else "-", class_=f"valor {classe}")

    def _saldo(valor: float):
        sinal = "positivo" if valor > 0.005 else "negativo" if valor < -0.005 else ""
        return ui.tags.td(
            ("-" if sinal == "negativo" else "") + _em_reais(abs(valor)),
            class_=" ".join(x for x in ("valor saldo", sinal) if x),
        )

    grupos = [
        ui.tags.tbody(
            ui.tags.tr(
                ui.tags.td(
                    ui.span(icon_svg("angle-right", a11y="deco"), class_="flx-mov-seta"), mes["rotulo"], colspan="2"
                ),
                ui.tags.td(f"{len(mes['itens'])} movimentaç{'ão' if len(mes['itens']) == 1 else 'ões'}"),
                _soma(mes["entradas"], "entradas"),
                _soma(mes["saidas"], "saidas"),
                _saldo(mes["entradas"] - mes["saidas"]),
                class_="flx-mov-mes",
                title="Clique para ver os movimentos do mês",
            ),
            *[
                ui.tags.tr(
                    ui.tags.td({"entrada": "Entrada", "saida": "Saída"}.get(mov.get("tipo"), "-")),
                    ui.tags.td(mov.get("data") or ""),
                    ui.tags.td(mov.get("descricao") or ""),
                    ui.tags.td(mov.get("valor") or "" if mov.get("tipo") != "saida" else "", class_="valor"),
                    ui.tags.td(mov.get("valor") or "" if mov.get("tipo") == "saida" else "", class_="valor"),
                    ui.tags.td("", class_="valor"),
                    class_=" ".join(x for x in (mov.get("tipo"), "flx-mov-dia") if x),
                )
                for mov in mes["itens"]
            ],
            class_="flx-mov-grupo",
        )
        for mes in _meses_dos_movimentos(movimentos)
    ]
    return ui.tags.table(
        ui.tags.thead(
            ui.tags.tr(
                ui.tags.th("Tipo"),
                ui.tags.th("Data"),
                ui.tags.th("Descrição"),
                ui.tags.th("Entrada", class_="valor"),
                ui.tags.th("Saída", class_="valor"),
                ui.tags.th("Saldo", class_="valor"),
            )
        ),
        *grupos,
        class_="flx-balao-tabela flx-mov-tabela",
    )


def _balao(tooltip, revenda: str, rotulo: str, url_pdf: str | None = None):
    if not tooltip:
        return None
    if tooltip.get("kind") == "notas_fiscais":
        itens = tooltip.get("itens") or []
        com_consulta = any(item.get("consultar") or item.get("pdf") for item in itens)
        notas = (
            ui.div(
                ui.tags.table(
                    ui.tags.thead(
                        ui.tags.tr(
                            ui.tags.th("NF"),
                            ui.tags.th("Valor", class_="valor"),
                            ui.tags.th("Consultar", class_="flx-balao-link") if com_consulta else None,
                        )
                    ),
                    ui.tags.tbody(
                        *[
                            ui.tags.tr(
                                ui.tags.td(item.get("nf") or "-"),
                                ui.tags.td(item.get("valor") or "-", class_="valor"),
                                ui.tags.td(_link_da_nota(item, url_pdf), class_="flx-balao-link")
                                if com_consulta
                                else None,
                            )
                            for item in itens
                        ]
                    ),
                    class_="flx-balao-tabela",
                ),
                class_="flx-balao-rolagem",
            )
            if itens
            else ui.div("Sem notas detalhadas", class_="flx-balao-vazio")
        )
        return (
            tooltip.get("titulo") or "Notas",
            ui.TagList(ui.div("Notas fiscais", class_="flx-balao-secao"), notas),
            "flx-balao flx-balao-notas",
        )
    cliente = re.sub(r"^deve\s+(?:ao|à|a)?\s*", "", rotulo or "", flags=re.IGNORECASE).strip()
    movimentos = tooltip.get("movimentos") or []
    resumo = ui.div(
        *[
            ui.div(ui.span(nome), ui.tags.strong(tooltip.get(chave, ""), class_=classe))
            for nome, chave, classe in (
                ("Saldo Inicial", "saldo_inicial", None),
                ("Entradas", "entradas", "entrada"),
                ("Saídas", "saidas", "saida"),
                ("Saldo Final", "saldo_final", None),
            )
        ],
        class_="flx-balao-resumo",
    )
    lancamentos = (
        ui.div(_movimentos_por_mes(movimentos), class_="flx-balao-rolagem")
        if movimentos
        else ui.div("Sem movimentações detalhadas", class_="flx-balao-vazio")
    )
    return (
        f"Detalhes para {revenda} | {cliente}",
        ui.TagList(resumo, ui.div("Movimentações", class_="flx-balao-secao"), lancamentos),
        "flx-balao",
    )


def _conteudo(formatado: str):
    texto = (formatado or "").strip()
    if texto.startswith("R$"):
        return ui.div(
            ui.span("R$", class_="valor-moeda"),
            ui.span(texto.replace("R$", "", 1).strip(), class_="valor-quantia"),
            class_="valor-alinhado",
        )
    return texto


@module.ui
def fluxo_cabecalho(revenda: str | None = None):
    return ui.div(
        ui.div(
            ui.input_action_button(
                "abrir_fabrica",
                "Fábrica",
                icon=ui.tags.img(src=ICONE_EXCEL, class_="ppf-arquivo-icone", alt=""),
                class_="ppf-arquivo-botao",
            ),
            class_="ppf-arquivo",
            title="Planilhas e extratos da fábrica",
        ),
        ui.div(
            ui.input_select("historico", "Histórico:", {"": "Atual"}),
            class_="ppf-filtro ppf-filtro-historico",
        ),
        class_="ppf-barra-topo",
    )


@module.ui
def fluxo_ui(revenda: str | None = None):
    return ui.div(
        ui.card(
            ui.card_header(titulo_secao("Fluxo Financeiro", icone=ICONE_FLUXO_FABRICA)),
            ui.div(ui.output_ui("tabela"), class_="tabela-consolidada-scroll-container"),
            class_="flx",
        ),
        class_="fin-modulo",
    )


@module.server
def fluxo_server(input, output, session, revenda_atual=None):
    def _revenda() -> str | None:
        return revenda_atual() if callable(revenda_atual) else revenda_atual

    def _usuario() -> str:
        try:
            raiz = session.root_scope() if hasattr(session, "root_scope") else session
            quem, _script = identificar_usuario(raiz.http_conn)
            return (quem or "").strip() or "desconhecido"
        except Exception:
            return "desconhecido"

    @reactive.poll(_carimbos_dos_arquivos, SEGUNDOS_ENTRE_CONFERENCIAS)
    def carimbos_de_agora() -> tuple:
        return _carimbos_dos_arquivos()

    @reactive.calc
    def atual() -> dict:
        _revenda()
        return f.montar()

    @reactive.calc
    def _retratos() -> pl.DataFrame:
        _revenda()
        return f.retratos()

    @reactive.effect
    def _encher_historico():
        base = _retratos()
        if base.is_empty() or "data_snapshot" not in base.columns:
            return
        datas = sorted({d for d in base["data_snapshot"].drop_nulls().to_list()}, reverse=True)
        with reactive.isolate():
            atual_sel = input.historico() if "historico" in input else ""
        opcoes = {"": "Atual", **{d.isoformat(): d.strftime("%d/%m/%Y") for d in datas}}
        ui.update_select("historico", choices=opcoes, selected=atual_sel if atual_sel in opcoes else "")

    def _marcas() -> dict:
        return f.marcacoes()

    def _marcando() -> bool:
        return not input.historico()

    @render.ui
    def tabela():
        return _tabela_montada()

    def _tabela_montada():
        t = _tabela_escolhida()
        cols = t.get("colunas") or []
        grupos = set(f.grupos()) | {"TOTAL"}
        a_parte = f._coluna_a_parte()
        retrato = bool(input.historico())
        extrato = {} if retrato else f.extrato_hoje()
        sem_data = {} if retrato else f.extratos_sem_data()
        divergencias = {} if retrato else f.divergencias_de_boletos()
        marcas = _marcas() if not retrato else {}
        marcando = _marcando()

        def _th(coluna, conteudo):
            classes = ["text-left"] + (["col-grupo-consolidado"] if coluna in grupos else [])
            return ui.tags.th(conteudo, class_=" ".join(classes))

        def _extrato(coluna):
            if coluna not in sem_data and coluna not in divergencias:
                return extrato.get(coluna, "")
            alertas = []
            if coluna in sem_data:
                alertas.append(
                    ui.div(
                        ui.span("Erro", class_="extrato-erro"),
                        ui.div(
                            ui.div(class_="tooltip-arrow"),
                            ui.tags.strong("Sem data"),
                            ui.tags.ul(*[ui.tags.li(fab) for fab in sem_data[coluna]]),
                            class_="extrato-erro-tooltip",
                        ),
                        class_="extrato-erro-container",
                    )
                )
            if coluna in divergencias:
                alertas.append(
                    ui.div(
                        ui.span("Divergência", class_="extrato-divergencia"),
                        ui.div(
                            ui.div(class_="tooltip-arrow tooltip-arrow-warning"),
                            ui.tags.strong("Saldo boletos divergente"),
                            *[
                                ui.div(
                                    ui.div(
                                        f"{d['codigo_empresa']} → {d['fabrica']}", class_="extrato-divergencia-fabrica"
                                    ),
                                    ui.div(
                                        f"Saldo boletos: {d['saldo_boletos_fmt']}", class_="extrato-divergencia-linha"
                                    ),
                                    ui.div(f"Soma tabela: {d['soma_tabela_fmt']}", class_="extrato-divergencia-linha"),
                                    ui.div(f"Diferença: {d['diferenca_fmt']}", class_="extrato-divergencia-linha"),
                                    class_="extrato-divergencia-item",
                                )
                                for d in divergencias[coluna]
                            ],
                            class_="extrato-divergencia-tooltip",
                        ),
                        class_="extrato-divergencia-container",
                    )
                )
            return ui.div(*alertas, class_="extrato-alertas-container")

        cab1, cab2 = (
            [ui.tags.th("Extrato hoje", class_="col-revenda-fixa text-left")],
            [ui.tags.th("Revenda", class_="col-revenda-fixa text-left")],
        )
        for c in cols:
            if c == a_parte:
                cab1.append(ui.tags.th(class_="text-left col-spacer"))
                cab2.append(ui.tags.th(class_="text-left col-spacer"))
            cab1.append(_th(c, _extrato(c)))
            cab2.append(_th(c, c))

        corpo = []
        for i, linha in enumerate(t.get("linhas") or []):
            tipo = linha.get("tipo")
            classes = [_CLASSE_DA_LINHA.get(tipo, "")]
            if linha.get("vence_em_breve"):
                classes.append("linha-vence-em-breve")
            celulas = [
                ui.tags.td(
                    linha.get("label", ""),
                    class_="col-revenda-fixa text-left" + (" celula-espaco" if tipo == "espaco" else ""),
                )
            ]
            for j, c in enumerate(cols):
                if c == a_parte:
                    celulas.append(ui.tags.td(class_="text-left col-spacer"))
                dado = (linha.get("valores") or {}).get(c) or {}
                marca = marcas.get(f"{linha.get('label')}|{c}", {})
                amarela = marca.get("amarela", dado.get("is_marcada", False))
                laranja = marca.get("laranja", dado.get("is_marcada_laranja", False))
                cls = ["text-left", dado.get("classe_valor") or ""]
                if dado.get("is_grupo"):
                    cls.append("col-grupo-consolidado")
                if tipo == "espaco":
                    cls.append("celula-espaco")
                if amarela:
                    cls.append("celula-marcada")
                elif laranja:
                    cls.append("celula-marcada-laranja")
                conteudo = _conteudo(dado.get("formatado", ""))
                atributos = {"data-flx-l": str(i), "data-flx-c": str(j)} if i < MAX_LINHAS and j < MAX_COLUNAS else {}
                if atributos and marcando and tipo in TIPOS_MARCAVEIS:
                    atributos["data-flx-marcavel"] = "1"
                    cls.append("flx-celula-marcavel")
                balao = _balao(dado.get("tooltip"), c, linha.get("label", ""))
                if balao:
                    titulo_balao, corpo_balao, classe_balao = balao
                    conteudo = ui.popover(
                        ui.div(conteudo, class_="flx-celula-balao"),
                        corpo_balao,
                        title=titulo_balao,
                        id=f"balao_{i}_{j}" if atributos else None,
                        placement="left",
                        options={"customClass": classe_balao},
                    )
                    if atributos:
                        atributos["data-flx-balao"] = f"balao_{i}_{j}"
                celulas.append(ui.tags.td(conteudo, class_=" ".join(x for x in cls if x), **atributos))
            corpo.append(ui.tags.tr(*celulas, class_=" ".join(x for x in classes if x)))

        return ui.tags.table(
            ui.tags.thead(ui.tags.tr(*cab1, class_="linha-extrato-atualizacao"), ui.tags.tr(*cab2)),
            ui.tags.tbody(*corpo),
            class_="tabela-mare-consolidada",
        )

    @reactive.calc
    def _tabela_escolhida() -> dict:
        escolhido = input.historico()
        if not escolhido:
            return atual()
        base = _retratos()
        if base.is_empty():
            return atual()
        linha = (
            base.filter(pl.col("data_snapshot") == date.fromisoformat(escolhido)).sort("id", descending=True).head(1)
        )
        if linha.is_empty():
            return atual()
        try:
            payload = json.loads(linha["payload"][0])
            return payload.get("tabela_credito_consolidada") or {"colunas": [], "linhas": []}
        except (TypeError, ValueError):
            return {"colunas": [], "linhas": []}

    _cliques: dict[str, int] = {}

    def _clicou(nome: str) -> bool:
        if nome not in input:
            return False
        atual_v = input[nome]() or 0
        anterior = _cliques.get(nome, 0)
        _cliques[nome] = atual_v
        return atual_v > anterior

    @reactive.effect
    @reactive.event(input.marcar_celula)
    async def _marcar():
        try:
            pedido = input.marcar_celula() or {}
            i, j, cor = int(pedido.get("l", -1)), int(pedido.get("c", -1)), pedido.get("cor")
            if not _marcando() or cor not in ("amarela", "laranja"):
                return
            with reactive.isolate():
                t = atual()
            marcas = _marcas()
            linhas, cols = t.get("linhas") or [], t.get("colunas") or []
            if not (0 <= i < len(linhas) and 0 <= j < len(cols)) or linhas[i].get("tipo") not in TIPOS_MARCAVEIS:
                return
            if not pode(_usuario(), "marcar_fluxo"):
                ui.modal_show(
                    modal_aviso(
                        "Você não tem permissão para marcar. " + quem_libera("marcar_fluxo"),
                        titulo="Fluxo Financeiro",
                        tipo="error",
                    ),
                    session=session,
                )
                return
            rotulo, coluna = linhas[i].get("label"), cols[j]
            estado = marcas.get(f"{rotulo}|{coluna}", {})
            amarela = cor == "amarela" and not estado.get("amarela", False)
            laranja = cor == "laranja" and not estado.get("laranja", False)
            manual_arquivo.marcar_celula_mare(rotulo, coluna, amarela, laranja, _usuario())
            await session.send_custom_message(
                "fluxoMarcar", {"l": i, "c": j, "amarela": amarela, "laranja": laranja and not amarela}
            )
        except Exception as erro:
            print(f"Fluxo Financeiro: marcar -- {erro}")

    @reactive.effect
    @reactive.event(input.detalhe_celula)
    def _abrir_balao():
        nome = str((input.detalhe_celula() or {}).get("id") or "")
        if not re.fullmatch(r"balao_\d+_\d+", nome):
            return
        with reactive.isolate():
            aberto = bool(input[nome]()) if nome in input else False
        ui.update_popover(nome, show=not aberto)

    @reactive.effect
    @reactive.event(input.fechar_baloes)
    def _fechar_baloes():
        for nome in (input.fechar_baloes() or {}).get("ids") or []:
            if re.fullmatch(r"balao_\d+_\d+", str(nome)):
                ui.update_popover(str(nome), show=False)

    _balao_aberto: list[str] = []

    @reactive.effect
    def _um_balao_so():
        t = _tabela_escolhida()
        linhas = min(len(t.get("linhas") or []), MAX_LINHAS)
        colunas = min(len(t.get("colunas") or []), MAX_COLUNAS)
        abertos = [
            nome for i in range(linhas) for j in range(colunas) if (nome := f"balao_{i}_{j}") in input and input[nome]()
        ]
        novos = [nome for nome in abertos if nome not in _balao_aberto]
        if novos:
            for nome in abertos:
                if nome != novos[-1]:
                    ui.update_popover(nome, show=False)
        _balao_aberto[:] = novos[-1:] if novos else abertos

    @reactive.effect
    @reactive.event(input.abrir_fabrica)
    def _abrir_fabrica():
        # No original, aqui se enviam as planilhas e os PDFs de extrato da fábrica, que um
        # leitor próprio (e OCR, quando é imagem) transforma nas tabelas desta tela.
        ui.modal_show(
            modal_aviso(
                "No sistema original, este botão recebe as planilhas e os PDFs de extrato da "
                "fábrica e dispara a leitura deles. No portfólio, os extratos já vêm lidos.",
                titulo="Arquivos de Fábrica",
            ),
            session=session,
        )

    return carimbos_de_agora


def pag_fluxo_ui(revenda: str | None = None):
    return fluxo_ui("fluxo", revenda)


def pag_fluxo_cabecalho(revenda: str | None = None):
    return fluxo_cabecalho("fluxo", revenda)


def pag_fluxo_server(revenda_atual=None):
    return fluxo_server("fluxo", revenda_atual=revenda_atual)
