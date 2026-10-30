__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Catálogo de opções de BESS (Battery Energy Storage System) comumente
disponíveis no mercado, usado como base discreta de dimensionamento no
Módulo de Otimização de Alocação de BESS.

ATENÇÃO: valores de potência/energia e custo são REFERÊNCIAS
APROXIMADAS de mercado (faixas típicas de sistemas containerizados de
íon-lítio, ~ US$ 400-600/kWh + eletrônica de potência, convertidos em
ordem de grandeza para BRL), adequadas para fins didáticos (TCC). Em um
projeto executivo, substitua pelos dados de cotação/datasheet reais dos
fabricantes avaliados.
"""

CATALOGO_BESS_PADRAO = [
    {"nome": "BESS Residencial 5kW/10kWh", "kw": 5, "kwh": 10, "custo_brl": 35000},
    {"nome": "BESS Comercial 15kW/30kWh", "kw": 15, "kwh": 30, "custo_brl": 95000},
    {"nome": "BESS Comercial 30kW/60kWh", "kw": 30, "kwh": 60, "custo_brl": 180000},
    {"nome": "BESS Comercial 50kW/100kWh", "kw": 50, "kwh": 100, "custo_brl": 300000},
    {"nome": "BESS Industrial 100kW/200kWh", "kw": 100, "kwh": 200, "custo_brl": 560000},
    {"nome": "BESS Industrial 250kW/500kWh", "kw": 250, "kwh": 500, "custo_brl": 1300000},
    {"nome": "BESS Utility 500kW/1000kWh", "kw": 500, "kwh": 1000, "custo_brl": 2500000},
    {"nome": "BESS Utility 1000kW/2000kWh", "kw": 1000, "kwh": 2000, "custo_brl": 4700000},
]