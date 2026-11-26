import folium
from folium.plugins import MarkerCluster

PINO_POR_TIPO = {
    "MOTOCICLETA": ("motorcycle", "green"),
    "MOTONETA": ("motorcycle", "green"),
    "CICLOMOTOR": ("motorcycle", "green"),
    "CAMINHAO": ("truck", "blue"),
    "CAMINHAO TRATOR": ("truck-moving", "darkblue"),
    "CAMINHONETE": ("truck-pickup", "cadetblue"),
    "AUTOMOVEL": ("car", "orange"),
    "CAMIONETA": ("car", "orange"),
    "UTILITARIO": ("van-shuttle", "purple"),
    "CARTAO CORINGA": ("credit-card", "gray"),
}
PINO_PADRAO = ("location-dot", "lightgray")

CENTRO_PADRAO = (-8.05, -39.0)
ZOOM_PADRAO = 5

LAT_BRASIL = (-34.0, 5.5)
LON_BRASIL = (-74.0, -34.0)

RAIO_AGRUPAMENTO = 45
ZOOM_SEM_AGRUPAMENTO = 10


def _pino(tipo: str) -> tuple:
    return PINO_POR_TIPO.get(str(tipo or "").strip().upper(), PINO_PADRAO)


def _quando(valor) -> str:
    texto = str(valor or "").strip()
    if len(texto) < 16 or texto[4] != "-":
        return texto
    return f"{texto[8:10]}/{texto[5:7]}/{texto[:4]} {texto[11:16]}"


def _texto_balao(linha: dict) -> str:
    from html import escape

    def campo(rotulo, valor, negrito=False):
        if valor in (None, ""):
            return ""
        texto = escape(str(valor))
        if negrito:
            texto = f"<b>{texto}</b>"
        return f"<div style='margin:2px 0'><span style='color:#666'>{rotulo}:</span> {texto}</div>"

    return (
        f"<div style='font-family:sans-serif;font-size:13px;min-width:210px'>"
        f"{campo('Placa', linha.get('PLACA'), negrito=True)}"
        f"{campo('Tipo', linha.get('TIPO'))}"
        f"{campo('Unidade', linha.get('EMPRESA'))}"
        f"{campo('Motorista', linha.get('MOTORISTA'))}"
        f"{campo('Quando', _quando(linha.get('DATA_HORA')))}"
        f"{campo('Posto', linha.get('POSTO'))}"
        f"{campo('Onde', linha.get('ENDERECO') or linha.get('CIDADE'))}"
        f"</div>"
    )


def _legenda_html(tipos_presentes: list) -> str:
    linhas = []
    for tipo in tipos_presentes:
        icone, cor = _pino(tipo)
        linhas.append(
            f"<div style='display:flex;align-items:center;gap:6px;margin:3px 0'>"
            f"<i class='fa fa-{icone}' style='color:{cor};width:14px;text-align:center'></i>"
            f"<span>{tipo.title()}</span></div>"
        )
    return (
        '<div style="position:absolute;bottom:18px;left:10px;z-index:9999;'
        "background:rgba(255,255,255,.92);padding:8px 10px;border-radius:6px;"
        'box-shadow:0 1px 5px rgba(0,0,0,.3);font:12px sans-serif">'
        "<div style='font-weight:600;margin-bottom:4px'>Tipo de veículo</div>" + "".join(linhas) + "</div>"
    )


def mapa_html(base) -> str:
    com_lugar = (
        base.filter(base["LATITUDE"].is_between(*LAT_BRASIL) & base["LONGITUDE"].is_between(*LON_BRASIL))
        if base.height
        else base
    )

    fmap = folium.Map(location=CENTRO_PADRAO, zoom_start=ZOOM_PADRAO, control_scale=True)

    if com_lugar.height == 0:
        fmap.get_root().html.add_child(
            folium.Element(
                '<div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);'
                "z-index:9999;background:rgba(255,255,255,.95);padding:14px 18px;border-radius:8px;"
                'box-shadow:0 1px 6px rgba(0,0,0,.3);font:14px sans-serif;color:#555">'
                "Nenhum veículo com posição conhecida para este filtro.</div>"
            )
        )
        return fmap.get_root().render()

    grupo = MarkerCluster(
        name="Veículos",
        options={
            "maxClusterRadius": RAIO_AGRUPAMENTO,
            "disableClusteringAtZoom": ZOOM_SEM_AGRUPAMENTO,
            "spiderfyOnMaxZoom": True,
            "showCoverageOnHover": False,
        },
    ).add_to(fmap)
    for linha in com_lugar.iter_rows(named=True):
        icone, cor = _pino(linha.get("TIPO"))
        folium.Marker(
            location=(linha["LATITUDE"], linha["LONGITUDE"]),
            tooltip=f"{linha.get('PLACA')} -- {linha.get('TIPO') or 'sem tipo'}",
            popup=folium.Popup(_texto_balao(linha), max_width=320),
            icon=folium.Icon(color=cor, icon=icone, prefix="fa"),
        ).add_to(grupo)

    latitudes = com_lugar["LATITUDE"].to_list()
    longitudes = com_lugar["LONGITUDE"].to_list()
    fmap.fit_bounds([[min(latitudes), min(longitudes)], [max(latitudes), max(longitudes)]], padding=(30, 30))

    tipos = sorted({str(t).strip().upper() for t in com_lugar["TIPO"].to_list() if t})
    fmap.get_root().html.add_child(folium.Element(_legenda_html(tipos)))
    return fmap.get_root().render()
