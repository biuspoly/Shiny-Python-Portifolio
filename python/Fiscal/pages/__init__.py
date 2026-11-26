from .Apuracao import pag_apuracao_server, pag_apuracao_ui
from .Faturamento import pag_faturamento_server, pag_faturamento_ui

PAGINAS = {
    "apu": (pag_apuracao_ui, pag_apuracao_server),
    "fat": (pag_faturamento_ui, pag_faturamento_server),
}
