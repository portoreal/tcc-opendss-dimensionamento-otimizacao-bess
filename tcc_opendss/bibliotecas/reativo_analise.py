__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Verifica se, depois de alocado o BESS, a rede ainda precisa de
compensação reativa — capacitiva ou indutiva — olhando o fator de potência
que a subestação (a fonte) enxerga.

O limite adotado vem do PRODIST Módulo 8 da ANEEL: 0,92 indutivo a 0,92
capacitivo no ponto de conexão. A função recebe esse limite como parâmetro
justamente porque ele é referência, não dogma.

CONVENÇÃO DE SINAL (propriedade Circuit.TotalPower do OpenDSS): kW e kvar
positivos representam potência entregue PELA fonte À rede. Dessa convenção
decorre a leitura adotada aqui:
    kvar > 0 -> rede predominantemente indutiva   -> pede Capacitor
    kvar < 0 -> rede predominantemente capacitiva -> pede Reactor
Se alguma versão do Engine inverter esse sinal, o conserto é local: troque
o sentido da comparação logo abaixo. A convenção fica registrada aqui
porque um erro de sinal aqui produz uma recomendação fisicamente errada,
sem nenhum aviso.
"""

import math

from .estudo_afundamento import MotorReutilizavel, _preparar_circuito_em_motor
from .dimensionamento_regras import dimensionar_capacitor, dimensionar_reator_indutivo


def analisar_necessidade_reativo(caminho_master, bess_list, fp_minimo=0.92,
                                   kv_conexao_padrao=13.8, fases=3):
    motor = MotorReutilizavel()
    try:
        _preparar_circuito_em_motor(motor, caminho_master, bess_list)

        # TotalPower devolve dois números na ordem [kW, kvar], medidos na fonte.
        potencia = motor.dssCircuit.TotalPower  # [kW, kvar]
        kw, kvar = potencia[0], potencia[1]

        # Potência aparente a partir das componentes ativa e reativa.
        # O "or 1e-9" protege a divisão seguinte quando o circuito está
        # desenergizado (S = 0), caso em que o fator de potência é indefinido.
        modulo_s = math.hypot(kw, kvar) or 1e-9
        fp = abs(kw) / modulo_s

        recomendacao = None

        if fp < fp_minimo:
            # kvar positivo: indutivo. Compensar com banco de capacitores.
            if kvar > 0:
                resultado = dimensionar_capacitor(
                    potencia_ativa_kw=abs(kw), fp_atual=fp, fp_desejado=fp_minimo,
                    kv_conexao=kv_conexao_padrao, fases=fases)
                recomendacao = {"tipo": "Capacitor", **resultado}
            else:
                # kvar negativo: a rede já está capacitiva. O excedente é o
                # que sobra acima do que a potência ativa justificaria no
                # limite de fp desejado. O piso de 30% evita dimensionar um
                # reator irrisório quando a conta dá quase zero.
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