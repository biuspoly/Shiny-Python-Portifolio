from __future__ import annotations

import sys

SAIDAS = {
    "101": "Venda de produção do estabelecimento",
    "102": "Venda de mercadoria adquirida de terceiros",
    "103": "Venda de produção, efetuada fora do estabelecimento",
    "104": "Venda de mercadoria de terceiros, efetuada fora do estabelecimento",
    "105": "Venda de produção que não deva transitar pelo estabelecimento",
    "106": "Venda de mercadoria de terceiros que não deva transitar pelo estabelecimento",
    "107": "Venda de produção a não contribuinte",
    "108": "Venda de mercadoria de terceiros a não contribuinte",
    "116": "Venda de produção originada de encomenda para entrega futura",
    "117": "Venda de mercadoria originada de encomenda para entrega futura",
    "118": "Venda de produção entregue ao destinatário por conta e ordem do adquirente",
    "119": "Venda de mercadoria entregue ao destinatário por conta e ordem do adquirente",
    "120": "Venda de mercadoria entregue pelo vendedor remetente, em venda à ordem",
    "122": "Venda de produção remetida para industrialização, por conta e ordem do adquirente",
    "124": "Industrialização efetuada para outra empresa",
    "151": "Transferência de produção do estabelecimento",
    "152": "Transferência de mercadoria adquirida de terceiros",
    "201": "Devolução de compra para industrialização",
    "202": "Devolução de compra para comercialização",
    "252": "Venda de energia elétrica para estabelecimento industrial",
    "253": "Venda de energia elétrica para estabelecimento comercial",
    "301": "Prestação de serviço de comunicação",
    "351": "Prestação de serviço de transporte",
    "352": "Prestação de serviço de transporte a estabelecimento industrial",
    "353": "Prestação de serviço de transporte a estabelecimento comercial",
    "401": "Venda de produção com substituição tributária (substituto)",
    "402": "Venda de produção com ST, entre contribuintes substitutos",
    "403": "Venda de mercadoria de terceiros com substituição tributária (substituto)",
    "404": "Venda de mercadoria com ST já retida anteriormente",
    "405": "Venda de mercadoria de terceiros com substituição tributária (substituído)",
    "408": "Transferência de produção com substituição tributária",
    "409": "Transferência de mercadoria de terceiros com substituição tributária",
    "410": "Devolução de compra para industrialização com substituição tributária",
    "411": "Devolução de compra para comercialização com substituição tributária",
    "412": "Devolução de bem do ativo imobilizado com substituição tributária",
    "413": "Devolução de material de uso ou consumo com substituição tributária",
    "414": "Remessa de produção para venda fora do estabelecimento, com ST",
    "415": "Remessa de mercadoria para venda fora do estabelecimento, com ST",
    "551": "Venda de bem do ativo imobilizado",
    "552": "Transferência de bem do ativo imobilizado",
    "553": "Devolução de compra de bem para o ativo imobilizado",
    "556": "Devolução de compra de material de uso ou consumo",
    "557": "Transferência de material de uso ou consumo",
    "651": "Venda de combustível ou lubrificante de produção, para industrialização",
    "652": "Venda de combustível ou lubrificante de produção, para comercialização",
    "653": "Venda de combustível ou lubrificante de produção, a consumidor final",
    "655": "Venda de combustível ou lubrificante de terceiros, para comercialização",
    "656": "Venda de combustível ou lubrificante de terceiros, a consumidor final",
    "667": "Venda de combustível ou lubrificante a consumidor final de outro estado",
    "901": "Remessa para industrialização por encomenda",
    "902": "Retorno de mercadoria utilizada na industrialização por encomenda",
    "903": "Retorno de mercadoria recebida para industrialização e não aplicada",
    "904": "Remessa para venda fora do estabelecimento",
    "905": "Remessa para depósito fechado ou armazém geral",
    "906": "Retorno de mercadoria depositada em depósito fechado ou armazém geral",
    "907": "Retorno simbólico de mercadoria depositada em depósito fechado ou armazém geral",
    "908": "Remessa de bem por conta de contrato de comodato",
    "909": "Retorno de bem recebido por conta de contrato de comodato",
    "910": "Remessa em bonificação, doação ou brinde",
    "911": "Remessa de amostra grátis",
    "912": "Remessa de mercadoria ou bem para demonstração",
    "913": "Retorno de mercadoria ou bem recebido para demonstração",
    "914": "Remessa de mercadoria ou bem para exposição ou feira",
    "915": "Remessa de mercadoria ou bem para conserto ou reparo",
    "916": "Retorno de mercadoria ou bem recebido para conserto ou reparo",
    "917": "Remessa de mercadoria em consignação mercantil ou industrial",
    "918": "Devolução de mercadoria recebida em consignação",
    "920": "Remessa de vasilhame ou sacaria",
    "921": "Devolução de vasilhame ou sacaria",
    "922": "Lançamento de venda para entrega futura (faturamento antecipado)",
    "923": "Remessa por conta e ordem de terceiros, em venda à ordem",
    "924": "Remessa para industrialização por conta e ordem do adquirente",
    "925": "Retorno de mercadoria recebida para industrialização por conta e ordem do adquirente",
    "927": "Baixa de estoque por perda, roubo ou deterioração",
    "929": "Lançamento de operação também registrada em cupom fiscal (ECF)",
    "933": "Prestação de serviço tributado pelo ISSQN",
    "949": "Outra saída de mercadoria ou prestação de serviço não especificada",
}

ENTRADAS = {
    "101": "Compra para industrialização",
    "102": "Compra para comercialização",
    "201": "Devolução de venda de produção",
    "202": "Devolução de venda de mercadoria adquirida de terceiros",
    "403": "Compra para comercialização com substituição tributária",
    "407": "Compra de material de uso ou consumo com substituição tributária",
    "411": "Devolução de venda de mercadoria com substituição tributária",
    "551": "Compra de bem para o ativo imobilizado",
    "553": "Devolução de venda de bem do ativo imobilizado",
    "556": "Compra de material para uso ou consumo",
    "652": "Compra de combustível ou lubrificante para comercialização",
    "653": "Compra de combustível ou lubrificante por consumidor final",
    "661": "Devolução de venda de combustível ou lubrificante destinado à industrialização",
    "662": "Devolução de venda de combustível ou lubrificante destinado à comercialização",
    "908": "Entrada de bem por conta de contrato de comodato",
    "909": "Retorno de bem remetido por conta de contrato de comodato",
    "910": "Entrada de bonificação, doação ou brinde",
    "918": "Devolução de mercadoria remetida em consignação mercantil ou industrial",
    "921": "Entrada de vasilhame ou sacaria",
    "923": "Entrada de mercadoria recebida do vendedor remetente, em venda à ordem",
    "949": "Outra entrada de mercadoria ou prestação de serviço não especificada",
}

LADO = {
    "1": "dentro do estado",
    "2": "de outro estado",
    "3": "do exterior",
    "5": "dentro do estado",
    "6": "para outro estado",
    "7": "para o exterior",
}

DEVOLUCAO_SAIDA = {
    "201",
    "202",
    "208",
    "209",
    "210",
    "211",
    "410",
    "411",
    "412",
    "413",
    "503",
    "553",
    "555",
    "556",
    "660",
    "661",
    "662",
    "918",
    "919",
    "921",
}
DEVOLUCAO_ENTRADA = {
    "201",
    "202",
    "203",
    "204",
    "208",
    "209",
    "410",
    "411",
    "503",
    "504",
    "505",
    "506",
    "553",
    "660",
    "661",
    "662",
    "918",
    "919",
}


def devolucao(cfop) -> bool:
    codigo = "".join(c for c in str(cfop or "") if c.isdigit())
    if len(codigo) != 4:
        return False
    return codigo[1:] in (DEVOLUCAO_SAIDA if codigo[0] in "567" else DEVOLUCAO_ENTRADA if codigo[0] in "123" else ())


def nota_de_devolucao(cfops) -> bool:
    codigos = lista(cfops)
    return bool(codigos) and all(devolucao(c) for c in codigos)


def descricao(cfop) -> str:
    codigo = "".join(c for c in str(cfop or "") if c.isdigit())
    if len(codigo) != 4:
        return ""
    tabela = SAIDAS if codigo[0] in "567" else ENTRADAS if codigo[0] in "123" else {}
    return tabela.get(codigo[1:], "")


def rotulo(cfop) -> str:
    codigo = "".join(c for c in str(cfop or "") if c.isdigit())
    texto = descricao(codigo)
    return f"{codigo} - {texto}" if texto else codigo


def lista(cfops) -> list[str]:
    if isinstance(cfops, str):
        cfops = cfops.replace(";", ",").split(",")
    return list(dict.fromkeys(c.strip() for c in (cfops or []) if str(c).strip()))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    pedidos = sys.argv[1:] if "ipykernel" not in sys.modules else []
    for cfop in pedidos or [input("CFOP: ")]:
        print(f"{rotulo(cfop)} ({LADO.get(str(cfop)[:1], '?')})")
