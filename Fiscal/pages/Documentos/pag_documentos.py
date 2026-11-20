import polars as pl
from shiny import module, reactive, render, ui

from core import cores
from core.dados import ler
from core.formato import moeda, numero
from core.layout import cartao, filtros
from pages.Documentos.Dados import dados_documentos as dados

_TIPOS = ["NF-e", "CT-e", "NFS-e"]


@module.ui
def documentos_ui():
    inicio, fim = dados.periodo_padrao()
    filiais = sorted(ler("documentos")["destinatario"].unique().to_list())
    return ui.div(
        filtros(
            ui.input_date_range(
                "periodo", "Emissão", start=inicio, end=fim, format="dd/mm/yyyy", language="pt-BR", separator="até"
            ),
            ui.input_selectize("tipo", "Tipo", _TIPOS, multiple=True, options={"placeholder": "Todos"}),
            ui.input_select("filial", "Filial", {"": "Todas", **{f: f for f in filiais}}),
            ui.input_text("busca", "Busca", placeholder="Emitente, número, chave, produto ou NCM"),
            limpar_id="limpar",
        ),
        cartao(
            "Documentos fiscais recebidos",
            ui.output_data_frame("tabela"),
            ui.div("Clique numa NF-e para ver os itens dela.", class_="legenda"),
        ),
        cartao("Itens da NF-e", ui.output_ui("cabecalho_nota"), ui.output_data_frame("itens")),
    )


@module.server
def documentos_server(input, output, session):
    @reactive.effect
    @reactive.event(input.limpar)
    def _limpar():
        inicio, fim = dados.periodo_padrao()
        ui.update_date_range("periodo", start=inicio, end=fim)
        ui.update_selectize("tipo", selected=[])
        ui.update_select("filial", selected="")
        ui.update_text("busca", value="")

    @reactive.calc
    def base() -> pl.DataFrame:
        inicio, fim = input.periodo()
        return dados.documentos(inicio, fim, list(input.tipo()), input.filial() or None, input.busca().strip().upper())

    @render.data_frame
    def tabela():
        df = base()
        exibir = pl.DataFrame(
            {
                "Tipo": df["tipo"],
                "Número": df["numero"].cast(pl.String),
                "Emitente": df["emitente"],
                "UF": df["uf_emitente"],
                "Destinatário": df["destinatario"],
                "Emissão": [d.strftime("%d/%m/%Y") for d in df["emissao"]],
                "Valor": [moeda(v) for v in df["valor"]],
                "SEFAZ": df["situacao_sefaz"],
                "Manifestação": df["manifestacao"],
                "Escriturada": ["Sim" if e else "Não" for e in df["escriturada"]],
            }
        )
        idx = df.with_row_index()
        estilos = []
        for tipo, cor in cores.TIPOS.items():
            linhas = idx.filter(pl.col("tipo") == tipo)["index"].to_list()
            if linhas:
                estilos.append(
                    {
                        "rows": linhas,
                        "cols": [0],
                        "style": {"background-color": cor, "color": "#fff", "font-weight": "700"},
                    }
                )
        for coluna, filtro, cor in (
            (7, pl.col("situacao_sefaz") == "Cancelada", cores.NEGATIVO),
            (9, ~pl.col("escriturada"), cores.NEGATIVO),
            (8, pl.col("manifestacao").is_in(["Sem manifestação", "Ciência"]), cores.ALERTA),
        ):
            linhas = idx.filter(filtro)["index"].to_list()
            if linhas:
                estilos.append({"rows": linhas, "cols": [coluna], "style": {"color": cor, "font-weight": "700"}})
        return render.DataGrid(
            exibir,
            selection_mode="row",
            styles=estilos,
            width="100%",
            height="45vh",
            summary="Mostrando {start} a {end} de {total} documentos",
        )

    @reactive.calc
    def escolhido() -> dict | None:
        linhas = tabela.cell_selection()["rows"]
        return base().row(linhas[0], named=True) if linhas else None

    @render.ui
    def cabecalho_nota():
        d = escolhido()
        if d is None:
            return ui.div("Nenhum documento escolhido.", class_="legenda")
        return ui.div(
            ui.div(ui.strong(f"{d['tipo']} {d['numero']}"), f" · {d['emitente']} · {moeda(d['valor'])}"),
            ui.div(f"Chave de acesso: {dados.chave_formatada(d['chave'])}", class_="legenda"),
            ui.div(f"ICMS destacado: {moeda(d['icms'])}" if d["icms"] else "", class_="legenda"),
        )

    @render.data_frame
    def itens():
        d = escolhido()
        it = dados.itens(d["chave"]) if d else ler("itens_nfe").head(0)
        return render.DataGrid(
            pl.DataFrame(
                {
                    "Item": it["item"].cast(pl.String),
                    "Produto": it["produto"],
                    "NCM": it["ncm"],
                    "CFOP": it["cfop"],
                    "Quantidade": [numero(v) for v in it["quantidade"]],
                    "Valor": [moeda(v) for v in it["valor"]],
                    "ICMS": [moeda(v) for v in it["icms"]],
                }
            ),
            width="100%",
            height="auto",
            summary=False,
        )
