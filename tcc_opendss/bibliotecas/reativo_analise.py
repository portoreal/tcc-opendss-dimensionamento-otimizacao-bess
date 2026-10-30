__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Análise de necessidade de compensação reativa (capacitiva ou indutiva)
após a alocação do sistema BESS, verificando o fator de potência visto
na subestação (fonte) do sistema.

Referência normativa: ANEEL PRODIST Módulo 8 estabelece faixa de fator
de potência de referência entre 0,92 indutivo e 0,92 capacitivo no
ponto de conexão. Usamos esse limite como referência padrão (ajustável).

CONVENÇÃO DE SINAL ASSUMIDA (Circuit.TotalPower do OpenDSS): kW/kvar
positivos representam potência entregue PELA fonte À rede. Portanto:
    kvar > 0 -> rede predominantemente indutiva  -> precisa de Capacitor
    kvar < 0 -> rede predominantemente capacitiva -> precisa de Reactor
Caso observe resultado invertido em alguma versão específica do
Engine, ajuste o sinal nesta função (documentado aqui por transparência).
"""

import math

from .estudo_afundamento import MotorReutilizavel, _preparar_circuito_em_motor
from .dimensionamento_regras import dimensionar_capacitor, dimensionar_reator_indutivo


def analisar_necessidade_reativo(caminho_master, bess_list, fp_minimo=0.92,
                                   kv_conexao_padrao=13.8, fases=3):
    motor = MotorReutilizavel()
    try:
        _preparar_circuito_em_motor(motor, caminho_master, bess_list)

        potencia = motor.dssCircuit.TotalPower  # [kW, kvar]
        kw, kvar = potencia[0], potencia[1]

        modulo_s = math.hypot(kw, kvar) or 1e-9
        fp = abs(kw) / modulo_s

        recomendacao = None

        if fp < fp_minimo:
            if kvar > 0:
                resultado = dimensionar_capacitor(
                    potencia_ativa_kw=abs(kw), fp_atual=fp, fp_desejado=fp_minimo,
                    kv_conexao=kv_conexao_padrao, fases=fases)
                recomendacao = {"tipo": "Capacitor", **resultado}
            else:
                excedente_kvar = abs(kvar) - abs(kw) * math.tan(math.acos(fp_minimo))
                excedente_kvar = max(excedente_kvar, abs(kvar) * 0.3)
                resultado = dimensionar_reator_indutivo(
                    potencia_reativa_excedente_kvar=excedente_kvar,
                    kv_conexao=kv_conexao_padrao, fases=fases)
                recomendacao = {"tipo": "Reactor", **resultado}

        return {
            "kw_fonte": round(kw, 2),
            "kvar_fonte": round(kvar, 2),
            "fator_potencia": round(fp, 4),
            "fp_minimo_referencia": fp_minimo,
            "conforme": fp >= fp_minimo,
            "recomendacao": recomendacao,
        }
    finally:
        motor.finalizar()