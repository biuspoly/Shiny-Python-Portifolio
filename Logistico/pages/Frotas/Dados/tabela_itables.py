from datetime import date

import pandas as pd
import polars as pl
from shiny.ui import HTML

from core.compat import para_pandas
from core.cores import (
    FROTA_ALERTA,
    FROTA_NEGATIVO,
    FROTA_NEUTRO,
    FROTA_POSITIVO,
    FROTA_TENDENCIA_ALTA,
    FROTA_TENDENCIA_BAIXA,
    FROTA_TENDENCIA_NEUTRA,
    FROTA_TRANSFERENCIA,
    FROTA_ULTIMA_ATUALIZACAO_FUNDO,
)

from .regra_multa import PAGA_NAO, PAGA_SIM, PAGA_SUSPENSA

RÓTULOS = {
    "DTA_EXEC": "Data",
    "EMPRESA": "Prop. Veículo",
    "UNIDADE": "Unidade",
    "UF_Emp": "UF",
    "ULT_ATUALIZACAO": "Última\nAtualização",
    "PLACA": "Placa",
    "TIPO": "Tipo",
    "MODELO": "Modelo",
    "ANO": "Ano",
    "ANO_FAB": "Fabricação",
    "RENAVAM": "Renavam",
    "CHASSI": "Chassi",
    "CARROCERIA": "Carroceria",
    "RESTRICAO_ADM": "Rest Adm",
    "GRAVAME": "Gravame",
    "GRAVAME_PENDENTE": "Gravame\nPendente",
    "PROPRIETARIO": "Proprietário",
    "RENAJUD": "Renajud",
    "N_PROCESSOS": "Nº\nProcessos",
    "PROCESSO": "Processo",
    "TIPO_RESTRICAO": "Tipo\nRestrição",
    "TRIBUNAL": "Tribunal",
    "ORGAO": "Órgão",
    "DEBITO_DETRAN": "Débito",
    "DEBITO": "Débito",
    "IPVA": "Ipva Atual",
    "IPVA_AL_ANT": "Ipva Ant",
    "LICENCIAMENTO": "Licenciamento",
    "MULTA": "Multa\nDetran",
    "MULTA_SENATRAN": "Multa\nSenatran",
    "TABELA_FIPE": "Tabela Fipe",
    "OUTROS_DEBITOS": "Outros\nDébitos",
    "RENAINF": "Renainf",
    "AUTO_INFRACAO": "Auto da\nInfração",
    "DATA_HORA_INF": "Dt/Hr\nInfração",
    "DT_IDENT_CONDUTOR": "Prazo Ident\nCondutor",
    "VENCIMENTO": "Vencimento",
    "VALOR": "Valor",
    "INFRACAO": "Infração",
    "LOCAL": "Local",
    "PAGA": "Paga",
    "PAGA_POR": "Paga por",
    "CONSULTADO_EM": "Consultado\nem",
    "CUSTO_API": "Custo API",
    "VEICULOS": "Veículos",
    "TRANSFERENCIAS": "Transferências",
    "DATA": "Data",
    "CARRO": "Carro",
    "MOTO": "Moto",
    "CAVALO": "Cavalo",
    "CAMINHAO": "Caminhão",
    "BOTAO_TRANSFERENCIA": "Transferência\nmanual",
    "BOTAO_ANEXO_TRANSF": "Anexo",
    "BOTAO_MOTIVO": "Informar\nmotivo",
    "BOTAO_ANEXO_SAIDA": "Anexo",
    "OBS_MOTIVO": "Obs",
    "TIPO_SAIDA": "Tipo\nSaída",
    "TIPO_SAIDA_OUTRO": "Informar\n(Outro)",
    "COMPRADOR": "Comprador",
    "VALOR_VENDA": "Valor\nVenda",
    "DATA_HORA": "Data/Hora",
    "MOTORISTA": "Motorista",
    "ESTABELECIMENTO": "Posto",
    "CIDADE": "Cidade",
    "SERVICO": "Combustível",
    "QUILOMETRAGEM": "Hodômetro",
    "KM_RODADOS": "Km\nRodados",
    "LITROS": "Litros",
    "KM_LITRO": "Km/Litro",
    "VALOR_LITRO": "Valor/Litro",
    "VALOR_KM": "Valor/Km",
    "CENTRO_CUSTO": "Centro\nde Custo",
    "CARTAO": "Cartão",
    "RESPONSAVEL": "Responsável",
}


CLASSE_PLACA_ATRASADA = "frota-placa-atrasada"
CLASSE_LINHA_TRANSFERENCIA = "frota-linha-transferencia"


def rotulo_uma_linha(coluna: str) -> str:
    return RÓTULOS.get(coluna, coluna).replace("\n", " ")


def _moeda(valor) -> str:
    if pd.isna(valor):
        return ""
    texto = f"R$ {valor:,.2f}"
    return texto.translate(str.maketrans(",.", ".,"))


def data_aaaammdd_br(valor) -> str:
    valor = str(valor)
    if len(valor) != 8 or not valor.isdigit():
        return ""
    return f"{valor[6:8]}/{valor[4:6]}/{valor[0:4]}"


def _data_timestamp_br(valor) -> str:
    if pd.isna(valor):
        return ""
    return valor.strftime("%d/%m/%Y")


def _cor_vencimento(hoje: str):
    def estilo(valor) -> str:
        if pd.isna(valor):
            return ""
        venceu = valor.strftime("%Y-%m-%d") < hoje
        return f"color: {FROTA_NEGATIVO if venceu else FROTA_POSITIVO};"

    return estilo


def _cor_placa(placas_ult_rom: set[str]):
    def estilo(valor) -> str:
        if valor in placas_ult_rom:
            return f"background-color: {FROTA_ALERTA}; color: white; font-weight: bold;"
        return ""

    return estilo


CORES_PAGA = {PAGA_SIM: FROTA_POSITIVO, PAGA_NAO: FROTA_NEGATIVO, PAGA_SUSPENSA: FROTA_NEUTRO}


def _cor_paga(valor) -> str:
    cor = CORES_PAGA.get(valor)
    return f"color: {cor}; font-weight: bold;" if cor else ""


def _linha_transferencia(linha: pd.Series) -> list[str]:
    destaque = f"background-color: {FROTA_TRANSFERENCIA};" if linha["TRANSFERENCIA"] == "Sim" else ""
    return [destaque] * len(linha)


def _botao_transferencia(placa: str) -> str:
    return (
        f'<button type="button" class="frota-btn-cel frota-btn-transferencia" '
        f'data-placa="{placa}" title="Transferência manual">\u2795</button>'
    )


def _link_anexo(url: str, classe: str) -> str:
    return f'<a href="{url}" target="_blank" rel="noopener" class="frota-btn-cel {classe}" title="Ver anexo">\U0001f4be</a>'


def _botao_motivo(placa: str, ja_informado: bool) -> str:
    if ja_informado:
        return '<span class="frota-motivo-ok" title="Motivo já informado">\u2705</span>'
    return (
        f'<button type="button" class="frota-btn-cel frota-btn-motivo" '
        f'data-placa="{placa}" title="Informar motivo de saída">\U0001f4cb</button>'
    )


def adicionar_botao_transferencia(tabela: pl.DataFrame, pode_transferir: bool, anexos: dict[str, str]) -> pl.DataFrame:
    if not pode_transferir:
        return tabela
    return tabela.with_columns(
        pl.col("PLACA").map_elements(_botao_transferencia, return_dtype=pl.Utf8).alias("BOTAO_TRANSFERENCIA"),
        pl.col("PLACA")
        .map_elements(
            lambda placa: _link_anexo(anexos[placa], "frota-btn-anexo-transf") if anexos.get(placa) else "",
            return_dtype=pl.Utf8,
        )
        .alias("BOTAO_ANEXO_TRANSF"),
    )


def adicionar_botoes_motivo(
    tabela: pl.DataFrame,
    motivos: dict[str, str],
    anexos: dict[str, str],
    tipos_saida: dict[str, str] | None = None,
    tipos_saida_outro: dict[str, str] | None = None,
    compradores: dict[str, str] | None = None,
    valores_venda: dict[str, float] | None = None,
) -> pl.DataFrame:
    tipos_saida = tipos_saida or {}
    tipos_saida_outro = tipos_saida_outro or {}
    compradores = compradores or {}
    valores_venda = valores_venda or {}
    return tabela.with_columns(
        pl.col("PLACA").map_elements(lambda placa: motivos.get(placa) or "", return_dtype=pl.Utf8).alias("OBS_MOTIVO"),
        pl.col("PLACA")
        .map_elements(lambda placa: tipos_saida.get(placa) or "", return_dtype=pl.Utf8)
        .alias("TIPO_SAIDA"),
        pl.col("PLACA")
        .map_elements(lambda placa: tipos_saida_outro.get(placa) or "", return_dtype=pl.Utf8)
        .alias("TIPO_SAIDA_OUTRO"),
        pl.col("PLACA")
        .map_elements(lambda placa: compradores.get(placa) or "", return_dtype=pl.Utf8)
        .alias("COMPRADOR"),
        pl.col("PLACA")
        .map_elements(lambda placa: valores_venda.get(placa), return_dtype=pl.Float64)
        .alias("VALOR_VENDA"),
        pl.col("PLACA")
        .map_elements(lambda placa: _botao_motivo(placa, bool(motivos.get(placa))), return_dtype=pl.Utf8)
        .alias("BOTAO_MOTIVO"),
        pl.col("PLACA")
        .map_elements(
            lambda placa: _link_anexo(anexos[placa], "frota-btn-anexo-saida") if anexos.get(placa) else "",
            return_dtype=pl.Utf8,
        )
        .alias("BOTAO_ANEXO_SAIDA"),
    )


COLUNAS_MOEDA = {
    "DEBITO_DETRAN",
    "IPVA",
    "IPVA_AL_ANT",
    "LICENCIAMENTO",
    "MULTA",
    "MULTA_SENATRAN",
    "OUTROS_DEBITOS",
    "TABELA_FIPE",
    "VALOR",
    "CUSTO_API",
    "VALOR_LITRO",
    "VALOR_KM",
    "VALOR_VENDA",
}

COLUNAS_DECIMAIS = {"LITROS": 2, "KM_LITRO": 2, "KM_RODADOS": 0, "QUILOMETRAGEM": 0}


def _numero(valor, casas: int) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    try:
        return f"{float(valor):,.{casas}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    except (TypeError, ValueError):
        return str(valor)


def construir_detalhamento_df(tabela: pl.DataFrame, placas_ult_rom: set[str]) -> tuple[pd.DataFrame, list[dict]]:
    hoje = date.today().strftime("%Y-%m-%d")
    tem_transferencia = "TRANSFERENCIA" in tabela.columns

    tabela = tabela.with_columns(
        pl.col(coluna).fill_null("") for coluna, tipo in tabela.schema.items() if tipo == pl.Utf8
    )
    pandas_df = para_pandas(tabela)

    estilos: list[dict] = []

    if "DATA" in pandas_df.columns:
        pandas_df["DATA"] = pandas_df["DATA"].map(data_aaaammdd_br)

    if "CONSULTADO_EM" in pandas_df.columns:
        pandas_df["CONSULTADO_EM"] = pandas_df["CONSULTADO_EM"].map(data_aaaammdd_br)

    if "ULT_ATUALIZACAO" in pandas_df.columns:
        estilos.append(
            {
                "rows": list(range(len(pandas_df))),
                "cols": ["ULT_ATUALIZACAO"],
                "style": {"background-color": FROTA_ULTIMA_ATUALIZACAO_FUNDO},
            }
        )
        pandas_df["ULT_ATUALIZACAO"] = pandas_df["ULT_ATUALIZACAO"].map(data_aaaammdd_br)

    for coluna_data in ["VENCIMENTO", "DT_IDENT_CONDUTOR"]:
        if coluna_data in pandas_df.columns:
            cor_fn = _cor_vencimento(hoje)
            for posicao, valor in enumerate(pandas_df[coluna_data]):
                cor = cor_fn(valor)
                if cor:
                    estilos.append({"rows": [posicao], "cols": [coluna_data], "style": _css_para_dict(cor)})
            pandas_df[coluna_data] = pandas_df[coluna_data].map(_data_timestamp_br)

    for coluna in COLUNAS_MOEDA:
        if coluna in pandas_df.columns:
            pandas_df[coluna] = pandas_df[coluna].map(_moeda)

    if "DATA_HORA" in pandas_df.columns:
        pandas_df["DATA_HORA"] = (
            pd.to_datetime(pandas_df["DATA_HORA"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M").fillna("")
        )
    for coluna, casas in COLUNAS_DECIMAIS.items():
        if coluna in pandas_df.columns:
            pandas_df[coluna] = pandas_df[coluna].map(lambda v, c=casas: _numero(v, c))

    if "PLACA" in pandas_df.columns and placas_ult_rom:
        linhas_placa = [i for i, p in enumerate(pandas_df["PLACA"]) if p in placas_ult_rom]
        if linhas_placa:
            estilos.append(
                {
                    "rows": linhas_placa,
                    "cols": ["PLACA"],
                    "style": {"background-color": FROTA_ALERTA, "color": "white", "font-weight": "bold"},
                    "class": CLASSE_PLACA_ATRASADA,
                }
            )

    if "PAGA" in pandas_df.columns:
        for valor_paga in CORES_PAGA:
            linhas = [i for i, v in enumerate(pandas_df["PAGA"]) if v == valor_paga]
            if linhas:
                estilos.append({"rows": linhas, "cols": ["PAGA"], "style": _css_para_dict(_cor_paga(valor_paga))})

    if "MULTA_DESATUALIZADA" in pandas_df.columns:
        if "CONSULTADO_EM" in pandas_df.columns:
            linhas_velhas = [i for i, v in enumerate(pandas_df["MULTA_DESATUALIZADA"]) if bool(v)]
            if linhas_velhas:
                estilos.append(
                    {
                        "rows": linhas_velhas,
                        "cols": ["CONSULTADO_EM"],
                        "style": {"color": FROTA_ALERTA, "font-weight": "bold"},
                    }
                )
        pandas_df = pandas_df.drop(columns=["MULTA_DESATUALIZADA"])

    if tem_transferencia:
        linhas_transf = [i for i, v in enumerate(pandas_df["TRANSFERENCIA"]) if v == "Sim"]
        if linhas_transf:
            estilos.append(
                {
                    "rows": linhas_transf,
                    "style": _css_para_dict(f"background-color: {FROTA_TRANSFERENCIA};"),
                    "class": CLASSE_LINHA_TRANSFERENCIA,
                }
            )
        pandas_df = pandas_df.drop(columns=["TRANSFERENCIA"])

    for coluna_botao in ["BOTAO_TRANSFERENCIA", "BOTAO_ANEXO_TRANSF", "BOTAO_MOTIVO", "BOTAO_ANEXO_SAIDA"]:
        if coluna_botao in pandas_df.columns:
            pandas_df[coluna_botao] = pandas_df[coluna_botao].map(HTML)

    for regra in estilos:
        if "cols" in regra:
            regra["cols"] = [RÓTULOS.get(c, c) for c in regra["cols"]]

    pandas_df = pandas_df.rename(columns=RÓTULOS)
    return pandas_df, estilos


def _css_para_dict(declaracoes: str) -> dict[str, str]:
    resultado = {}
    for parte in declaracoes.strip().rstrip(";").split(";"):
        if ":" not in parte:
            continue
        chave, valor = parte.split(":", 1)
        resultado[chave.strip()] = valor.strip()
    return resultado


COLUNAS_TENDENCIA = ["CUSTO_API", "VEICULOS", "CARRO", "MOTO", "CAVALO", "CAMINHAO", "DEBITO", "RENAJUD", "TABELA_FIPE"]
COLUNAS_MOEDA_CONSOLIDADA = {"CUSTO_API", "DEBITO", "TABELA_FIPE"}
CORES_TENDENCIA = {
    1: (FROTA_TENDENCIA_ALTA, "▲"),
    -1: (FROTA_TENDENCIA_BAIXA, "▼"),
    0: (FROTA_TENDENCIA_NEUTRA, "—"),
}


def construir_consolidada_df(consolidada: pl.DataFrame, mostrar_custo_api: bool) -> pd.DataFrame:
    colunas = [c for c in COLUNAS_TENDENCIA if c != "CUSTO_API" or mostrar_custo_api]

    linhas = []
    for linha in consolidada.iter_rows(named=True):
        data_raw = linha["DTA_EXEC"]
        nova = {"DTA_EXEC": data_aaaammdd_br(data_raw)}
        for coluna in colunas:
            valor = linha[coluna]
            texto = _moeda(valor) if coluna in COLUNAS_MOEDA_CONSOLIDADA else f"{valor:,.0f}".replace(",", ".")
            cor, seta = CORES_TENDENCIA.get(linha[f"TREND_{coluna}"], CORES_TENDENCIA[0])
            nova[coluna] = HTML(f'<span style="color: {cor};">{seta} {texto}</span>')
        linhas.append(nova)

    return pd.DataFrame(linhas, columns=["DTA_EXEC", *colunas]).rename(columns=RÓTULOS)
