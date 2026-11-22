import asyncio
import io
from datetime import date

import polars as pl
from faicons import icon_svg
from shiny import module, reactive, render, ui
from shiny.ui import HTML

from core.aviso import modal_aviso
from core.compat import para_pandas
from core.cores import DESTAQUE
from core.largura_tabela import ColunaLargura, gerar_css_larguras
from core.rotulo import rotulo
from core.visibilidade import pagina_visivel
from pages.Permissoes.Dados.dados_permissoes import (
    acessos_paineis,
    paineis_ativos,
    usuarios_ativos,
)
from pages.Permissoes.Dados.informar_acesso_painel import (
    adicionar_acesso_usuario,
    excluir_acesso_usuario,
)

_ORDEM_COLUNAS_TABELA = ["Painel", "Login", "Usuario", "Revenda", "Retirar Acesso"]
_LARGURA_POR_COLUNA = {
    "Painel": 180,
    "Login": 140,
    "Usuario": 200,
    "Revenda": 160,
    "Retirar Acesso": 110,
}


_OPCOES_SELECT = {"dropdownParent": "body", "dropdownClass": "acessos-selectize-dropdown"}


def _botao_remover(grupo: str, painel_id: int) -> str:
    return (
        f'<button type="button" class="acessos-btn-cel acessos-btn-remover" '
        f'data-grupo="{grupo}" data-painel="{painel_id}" title="Retirar acesso"></button>'
    )


def tela(acessos: pl.DataFrame):
    na_tela = acessos.pipe(para_pandas)
    na_tela["Retirar Acesso"] = [
        HTML(_botao_remover(grupo, painel_id)) for grupo, painel_id in zip(na_tela["Grupo"], na_tela["id"])
    ]
    return na_tela.drop(columns=["id", "Grupo"])


@module.ui
def pag_permissoes_ui() -> ui.Tag:
    return ui.div(
        ui.div(id="pp-alerta"),
        ui.output_ui("kpis"),
        ui.card(
            ui.card_header("Conceder acesso a painel"),
            ui.div(
                ui.div(
                    ui.input_selectize("sel_painel", rotulo("Painel"), choices=[], options=_OPCOES_SELECT),
                    class_="filtro-acessos",
                ),
                ui.div(
                    ui.input_selectize("sel_revenda", rotulo("Revenda"), choices=[], options=_OPCOES_SELECT),
                    class_="filtro-acessos",
                ),
                ui.div(
                    ui.input_selectize("sel_usuario", rotulo("Usuário"), choices=[], options=_OPCOES_SELECT),
                    class_="filtro-acessos",
                ),
                class_="filtros-acessos acessos-form",
            ),
            ui.div(
                ui.div(),
                ui.div(
                    ui.input_action_button("bt_limpar", None, icon=icon_svg("eraser"), class_="btn-info"),
                    ui.input_action_button("bt_adicionar", "Adicionar", class_="btn-success"),
                    class_="acessos-botoes-usuario",
                ),
                class_="acessos-rodape-form",
            ),
            class_="my-4",
        ),
        ui.card(
            ui.card_header(
                ui.div(
                    ui.span("Acessos por painel"),
                    ui.download_button(
                        "exportar",
                        None,
                        icon=icon_svg("download", a11y="deco"),
                        class_="btn-exportar-acessos ms-auto",
                    ),
                    class_="d-flex justify-content-between align-items-center",
                ),
            ),
            ui.div(ui.output_data_frame("tabela"), class_="tabela-resize"),
            ui.output_ui("css_largura_tabela"),
        ),
        class_="acessos-modulo",
    )


@module.server
def pag_permissoes_server(input, output, session):
    versao = reactive.value(0, name="versao")

    @reactive.calc
    async def base_paineis() -> pl.DataFrame:
        return await asyncio.to_thread(paineis_ativos)

    @reactive.calc
    async def base_usuarios() -> pl.DataFrame:
        return await asyncio.to_thread(usuarios_ativos)

    @reactive.calc
    async def base_acessos() -> pl.DataFrame:
        versao()
        return await asyncio.to_thread(acessos_paineis)

    @reactive.effect
    async def _popula_opcoes():
        if not pagina_visivel(session, "permissoes"):
            return
        try:
            paineis = sorted((await base_paineis())["Painel"].unique().to_list())
            usuarios = sorted((await base_usuarios())["Login"].unique().to_list())
        except Exception:
            return
        ui.update_selectize("sel_painel", choices=paineis)
        ui.update_selectize("sel_usuario", choices=usuarios)

    @reactive.effect
    async def _popula_revenda_do_painel():
        painel = input.sel_painel()
        if not painel or not pagina_visivel(session, "permissoes"):
            ui.update_selectize("sel_revenda", choices=[])
            return
        try:
            df_p = await base_paineis()
        except Exception:
            return
        revendas = sorted(df_p.filter(pl.col("Painel") == painel)["Revenda"].unique().to_list())
        ui.update_selectize("sel_revenda", choices=revendas)

    @reactive.effect
    @reactive.event(input.bt_limpar)
    def _limpar():
        ui.update_selectize("sel_painel", selected="")
        ui.update_selectize("sel_revenda", choices=[], selected="")
        ui.update_selectize("sel_usuario", selected="")

    @reactive.effect
    @reactive.event(input.bt_adicionar)
    async def _adicionar():
        painel, revenda, usuario = input.sel_painel(), input.sel_revenda(), input.sel_usuario()
        if not all([painel, revenda, usuario]):
            return
        df_p, df_u = await base_paineis(), await base_usuarios()
        try:
            grupo_id = df_u.filter(pl.col("Login") == usuario)["nomeGrupo"][0]
            painel_id = int(df_p.filter((pl.col("Painel") == painel) & (pl.col("Revenda") == revenda))["id"][0])
            await asyncio.to_thread(adicionar_acesso_usuario, grupo_id, painel_id)
            versao.set(versao() + 1)
            ui.modal_show(modal_aviso("Acesso adicionado.", tipo="success"), session=session)
        except Exception:
            ui.modal_show(modal_aviso("Erro ao adicionar o acesso. Tente novamente.", tipo="error"), session=session)

    @reactive.effect
    @reactive.event(input.clique_remover_acesso)
    async def _remover():
        grupo, painel_id = input.clique_remover_acesso().split("|")
        try:
            await asyncio.to_thread(excluir_acesso_usuario, grupo, int(painel_id))
            versao.set(versao() + 1)
            ui.modal_show(modal_aviso("Acesso removido.", tipo="success"), session=session)
        except Exception:
            ui.modal_show(modal_aviso("Erro ao remover o acesso. Tente novamente.", tipo="error"), session=session)

    @render.ui
    async def kpis():
        df = await base_acessos()
        return ui.layout_columns(
            ui.value_box(
                "Total de acessos",
                df.height,
                showcase=icon_svg("key"),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#fff"),
            ),
            ui.value_box(
                "Usuários com acesso",
                df["Login"].n_unique(),
                showcase=icon_svg("users"),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#fff"),
            ),
            ui.value_box(
                "Painéis disponíveis",
                df["Painel"].n_unique(),
                showcase=icon_svg("table-cells-large"),
                theme=ui.value_box_theme(bg=DESTAQUE, fg="#fff"),
            ),
        )

    @render.data_frame
    async def tabela():
        with reactive.isolate():
            acessos = await base_acessos()
        return render.DataTable(
            tela(acessos),
            height="55vh",
            filters=True,
            selection_mode="none",
            summary="Linhas {start} a {end} de {total}",
        )

    @reactive.effect
    @reactive.event(versao, ignore_init=True)
    async def _trocar_dados_da_tabela():
        try:
            await tabela.update_data(tela(await base_acessos()))
        except Exception as exc:
            ui.modal_show(modal_aviso(f"Não foi possível reler os acessos: {exc}", tipo="error"), session=session)

    @render.ui
    async def css_largura_tabela():
        larguras = [ColunaLargura(c, _LARGURA_POR_COLUNA[c]) for c in _ORDEM_COLUNAS_TABELA]
        return ui.tags.style(gerar_css_larguras(f"#{session.ns('tabela')}", larguras))

    @render.download_button(filename=lambda: f"permissoes-{date.today().isoformat()}.xlsx")
    async def exportar():
        pandas_df = (await base_acessos()).drop("id", "Grupo").pipe(para_pandas)
        buffer = io.BytesIO()
        pandas_df.to_excel(buffer, index=False, engine="openpyxl")
        yield buffer.getvalue()
