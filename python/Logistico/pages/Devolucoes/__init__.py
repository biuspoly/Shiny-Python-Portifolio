from .pag_dev_caixas import pag_dev_caixas_server, pag_dev_caixas_ui
from .pag_dev_detalhes import pag_dev_detalhes_server, pag_dev_detalhes_ui
from .pag_dev_devolucoes import pag_dev_devolucoes_server, pag_dev_devolucoes_ui
from .pag_dev_graficos import pag_dev_graficos_server, pag_dev_graficos_ui

__all__ = [
    "pag_dev_detalhes_ui",
    "pag_dev_detalhes_server",
    "pag_dev_caixas_ui",
    "pag_dev_caixas_server",
    "pag_dev_devolucoes_ui",
    "pag_dev_devolucoes_server",
    "pag_dev_graficos_ui",
    "pag_dev_graficos_server",
]
