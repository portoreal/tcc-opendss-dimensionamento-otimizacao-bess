__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Catálogo de BESS (Battery Energy Storage System) disponíveis no mercado.

É a lista de onde o Módulo de Otimização de Alocação de BESS escolhe: o
problema de otimização não trabalha com qualquer potência/energia contínua,
e sim com as opções discretas daqui — por isso a lista precisa ser curta e
plausível, não exaustiva.

ATENÇÃO: os valores de potência, energia e custo são REFERÊNCIAS
APROXIMADAS de mercado, faixas típicas de sistemas containerizados de
íon-lítio (~ US$ 400-600/kWh somados à eletrônica de potência, convertidos
em ordem de grandeza para BRL). Servem para fins didáticos (TCC). Num
projeto executivo, troque-os por cotação e datasheet dos fabricantes
efetivamente avaliados.
"""

CATALOGO_BESS_PADRAO = [
    # Cada item é um produto comercial completo: potência do inversor (kW),
    # energia útil do banco (kWh) e custo de aquisição em reais. Note que a
    # razão kWh/kW cresce do residencial (2 h) ao utility (2 h), mantida
    # constante aqui de propósito — a otimização compara alternativas de
    # mesma autonomia, variando só o porte.
    {"nome": "BESS Residencial 5kW/10kWh", "kw": 5, "kwh": 10, "custo_brl": 35000},
    {"nome": "BESS Comercial 15kW/30kWh", "kw": 15, "kwh": 30, "custo_brl": 95000},
    {"nome": "BESS Comercial 30kW/60kWh", "kw": 30, "kwh": 60, "custo_brl": 180000},
    {"nome": "BESS Comercial 50kW/100kWh", "kw": 50, "kwh": 100, "custo_brl": 300000},
    {"nome": "BESS Industrial 100kW/200kWh", "kw": 100, "kwh": 200, "custo_brl": 560000},
    {"nome": "BESS Industrial 250kW/500kWh", "kw": 250, "kwh": 500, "custo_brl": 1300000},
    {"nome": "BESS Utility 500kW/1000kWh", "kw": 500, "kwh": 1000, "custo_brl": 2500000},
    {"nome": "BESS Utility 1000kW/2000kWh", "kw": 1000, "kwh": 2000, "custo_brl": 4700000},
]