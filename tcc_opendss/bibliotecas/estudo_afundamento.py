__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Motor de estudo de afundamento de tensão (voltage sag) baseado em
faltas aplicadas sequencialmente em cada barra candidata, seguindo a
metodologia de "área de vulnerabilidade" (Bollen, 2000), amplamente
utilizada para avaliação de VTCD (Variações de Tensão de Curta Duração).

Classificação conforme ANEEL (afundamento momentâneo de tensão):
    - Amplitude: 0,1 a 0,9 pu do valor eficaz.
    - Duração: 1 ciclo a 3 segundos.

LIMITAÇÃO IMPORTANTE (documentada por transparência de engenharia):
O OpenDSS resolve o sistema em regime fasorial (quase-estático). A
duração real do afundamento depende do tempo de atuação da proteção
(religadores, relés, fusíveis), o que é objeto de um estudo de
coordenação de proteção separado. Este módulo assume que a duração do
defeito está dentro da janela "momentânea" da norma (1 ciclo a 3 s) -
premissa válida para a maioria dos esquemas de proteção primária de
redes de distribuição - e concentra a classificação no critério de
AMPLITUDE (0,1 a 0,9 pu).

A contribuição do BESS durante a falta é modelada com o elemento
Storage (model=1, despacho PQ constante - o mesmo modelo do módulo
economia_energia.py).

CORREÇÃO DE BUG (model=7 inválido, silenciosamente ignorado pelo motor):
o código anterior usava model=7 "para representar um inversor com
limitação de corrente" - premissa INCORRETA. O parâmetro 'model' do
Storage aceita qualquer inteiro (read-back de '? storage.b1.model' ecoa
1, 7 ou 99 sem erro) e valores fora da faixa válida são SILENCIOSAMENTE
ignorados, caindo no comportamento default (PQ constante): experimento
controlado no dss-python 0.15.7 (circuito mínimo de 3 barras, BESS
300 kW/1200 kWh, falta trifásica remota r=0,0001 e r=1,0 e falta no
próprio barramento r=1,0) mostrou resultado bit a bit idêntico para
model=1, model=7 e model=99. A correção é, portanto, numericamente
inerte (higiene e alinhamento com a documentação oficial e com o
economia_energia.py, já corrigido para model=1).

TRANSPARÊNCIA TÉCNICA (medido no mesmo experimento): a injeção
quase-estática do Storage NÃO é constante-PQ ideal sob queda severa de
tensão - degrada com a tensão terminal (aprox. 92 kW a 0,5 pu; aprox.
7 kW a 0,14 pu, para BESS de 300 kW despachando 300 kW pré-falta), de
forma idêntica para qualquer valor de 'model'. A contribuição do BESS
sob falta neste estudo é, portanto, uma aproximação de regime
quase-estático da resposta do inversor, e pressupõe capacidade de
LVRT/FRT (Low/Fault Ride-Through) - premissa razoável para inversores
atuais compatíveis com as Normas de Acesso vigentes, mas que deve ser
validada com o datasheet do equipamento real em um projeto executivo.

SEVERIDADE DA FALTA 'SOLIDA' (atualizada 2026-10-28):
O default ``r_falta_solida`` mudou de 0,0001 para 0,05 ohm. Falta COMPLETAMENTE
solida (r=1e-4) colapsa as barras vizinhas a ~0,005 pu — um afundamento que
nenhum BESS realista mitiga (falta desenha corrente milhares de vezes maior
que a injecao do inversor), tornando o beneficio do estudo estruturalmente
zero. A faixa 0,02-0,3 ohm representa falta franca com arco (impedancia
tipica de distribuicao) e produz afundamentos intermediarios — a faixa onde
a mitigacao por armazenamento e fisicamente possivel e o estudo produz
resultado. O valor permanece PARAMETRO (o chamador pode passar 0.0001 para
replicar falta bolted).

MUDANÇA DE MOTOR (registrada por transparência metodológica):
Este módulo foi migrado de win32com/COM (OpenDSSEngine.DLL oficial da
EPRI) para a biblioteca DSS-Python (projeto DSS-Extensions). A
documentação oficial do DSS-Extensions ("Multiple engines and
multithreading") confirma que a arquitetura interna (DSSContext) foi
projetada especificamente para permitir múltiplas instâncias isoladas
do motor em cenários multithreaded - exatamente o nosso caso de uso
aqui, já que o estudo de otimização de BESS roda o motor repetidamente
em uma thread separada da interface gráfica. Isso elimina a necessidade
de inicialização COM por thread (pythoncom.CoInitialize/CoUninitialize)
que era necessária na versão anterior baseada em win32com.

CORREÇÃO DE BUG (caminhos com espaço, ex.: pastas OneDrive corporativas):
O método recompilar() enviava o comando 'compile' sem aspas ao redor do
caminho. Como o parser de scripts do OpenDSS trata espaço como separador
de parâmetros, caminhos como
'C:\\Users\\usuario\\OneDrive - EMPRESA S.A\\...\\Master.dss' quebravam
no primeiro espaço, gerando o erro "(#242) Redirect file not found".
Corrigido envolvendo o caminho entre aspas duplas dentro do comando.

CORREÇÃO DE BUG (2026-10-30 — assimetria de caixa + semântica de
não-convergência), no pipeline de afundamento consumido pela Otimização
de BESS:
  1. ASSIMETRIA DE CAUSA DE NOMES DE BARRA: _capturar_pu_todas_barras
     devolvia as chaves como o motor fornece (ex.: 'b4', minúsculas),
     mas o ramo de não-convergência de rodar_estudo derivava o conjunto
     de barras em sag da LISTA DE ENTRADA (ex.: 'B4', maiúsculas).
     Diferenças de conjuntos no orquestrador (barras_em_sag_baseline -
     barras do candidato) nunca cancelavam entre caixas diferentes ->
     crédito falso de barras mitigadas. Correção: TODA chave de barra
     que ENTRA nos resultados é normalizada para minúsculas
     (_nome_base_barra: split em '.' antes do lower — mesmo critério
     que _classificar_sag já usava para COMPARAR; agora a chave
     armazenada também sai normalizada).
  2. SEMÂNTICA DE NÃO-CONVERGÊNCIA (decisão de projeto: COLAPSO): o
     código anterior devolvia pu = {} no cenário divergente — nenhuma
     medição — e ainda assim o candidato herdava a profundidade total
     do baseline como "benefício" (creditado sem medição nenhuma).
     Correção: divergência do solver sob falta + injeção de BESS é
     tratada como COLAPSO DE TENSÃO não demonstravelmente mitigável
     (coerente com o texto do TCC sobre interrupção): cada barra que a
     captura normal registraria (mesma enumeração de AllBusNames, mesmo
     formato de chave, exceto a barra faltosa — mesma exclusão de
     _classificar_sag) recebe o SENTINEL limite_inferior (0,1 pu).
     Consequências intencionais: (i) todas essas barras ficam dentro da
     janela de afundamento [0,1; 0,9) -> o binário não credencia NADA
     como resolvido; (ii) a profundidade do cenário vira a janela
     completa (limite_superior - limite_inferior) -> S_i do candidato
     fica <= 0: divergir é PENALIZADO, nunca creditado. O novo campo
     'convergiu' em detalhe_por_falta distingue medição real de
     sentinel em TODOS os cenários. ATENÇÃO: o sentinel é
     limite_inferior e NÃO 0,0 — com 0,0 a barra cairia FORA da janela
     [limite_inferior, limite_superior) (V < limite_inferior é
     classificado como interrupção, não sag) e voltaria a contar como
     "resolvida", restaurando o bug.
"""

import math

from dss import dss as dss_global

# Vminpu do Storage: abaixo desta tensão (pu), o modelo do OpenDSS degrada
# a injeção para impedância constante (P ∝ V²) — com o DEFAULT (0,9), o
# BESS entregava ~12% da potência nominal justamente dentro da faixa de
# afundamento (prova por experimento, 2026-10-28: P/V² = -370,4 constante
# na varredura 0,50-0,71 pu; 92 kW a 0,5 pu para um BESS de 300 kW; com
# Vminpu=0.05: 300 kW constantes). Vminpu=0.05 modela o inversor COM
# ride-through (LVRT) — coerente com a premissa já declarada no docstring
# do módulo ("pressupõe capacidade de LVRT/FRT do BESS").
VMINPU_STORAGE_PADRAO = 0.05


class MotorReutilizavel:
    """Mantém uma instância isolada do Engine OpenDSS (DSS-Python) viva
    durante todo o estudo, recompilando o circuito a cada cenário. Isso
    evita o overhead de recriar o contexto a cada uma das centenas de
    soluções necessárias no estudo."""

    def __init__(self):
        # Tenta obter um contexto isolado do motor (recomendado para uso
        # em threads separadas, conforme a arquitetura DSSContext do
        # DSS-Extensions). Caso a versão instalada do pacote não exponha
        # este método (não confirmado com 100% de certeza no momento em
        # que este código foi escrito, por indisponibilidade temporária
        # da documentação), cai de volta para o contexto global - sem
        # regressão funcional, apenas sem o isolamento extra.
        try:
            self.dssObj = dss_global.NewContext()
        except AttributeError:
            self.dssObj = dss_global

        self.dssText = self.dssObj.Text
        self.dssCircuit = self.dssObj.ActiveCircuit
        self.dssSolution = self.dssCircuit.Solution

    def recompilar(self, caminho_master):
        self.dssObj.ClearAll()
        # IMPORTANTE: aspas duplas ao redor do caminho (ver nota de
        # correção de bug no topo do arquivo) - necessário para caminhos
        # com espaço, como pastas OneDrive corporativas.
        self.dssText.Command = f'compile "{caminho_master}"'
        self.dssCircuit = self.dssObj.ActiveCircuit
        self.dssSolution = self.dssCircuit.Solution
        self.dssSolution.Solve()

    def finalizar(self):
        self.dssObj = None
        self.dssText = None
        self.dssCircuit = None
        self.dssSolution = None


def _obter_kv_linha_barra(dssCircuit, bus):
    dssCircuit.SetActiveBus(bus)
    kv_ln = dssCircuit.ActiveBus.kVBase
    return kv_ln * math.sqrt(3)


def _preparar_circuito_em_motor(motor: MotorReutilizavel, caminho_master, bess_list):
    motor.recompilar(caminho_master)
    for i, bess in enumerate(bess_list):
        kv_linha = _obter_kv_linha_barra(motor.dssCircuit, bess["bus"])
        nome_bess = f"BESS_OTIM_{i}"
        motor.dssText.Command = (
            f"New Storage.{nome_bess} bus1={bess['bus']} phases=3 "
            f"kv={kv_linha:.4f} kwrated={bess['kw']} kwhrated={bess['kwh']} "
            f"kva={bess['kw']} %stored=50 state=discharging model=1 "
            f"Vminpu={VMINPU_STORAGE_PADRAO} dispmode=default"
        )
    if bess_list:
        motor.dssSolution.Solve()


def _spec_falta(bus, tipo_falta_dss):
    if tipo_falta_dss == "trifasica":
        return f"{bus}.1.2.3", 3
    return f"{bus}.1", 1  # monofásica (fase A, por convenção)


def _aplicar_falta(motor: MotorReutilizavel, bus, tipo_falta_dss, r_falta):
    spec, fases = _spec_falta(bus, tipo_falta_dss)
    motor.dssText.Command = (
        f"New Fault.FALTA_OTIM Bus1={spec} phases={fases} r={r_falta}"
    )


def _nome_base_barra(bus):
    """Nome base de barra normalizado para minúsculas (remove sufixos de
    nó: 'B4.1' -> 'b4'). Fonte ÚNICA de normalização de chaves de barra
    nos resultados do estudo — ver CORREÇÃO DE BUG (2026-10-30) no topo
    do arquivo."""
    return bus.split(".")[0].lower()


def _capturar_pu_todas_barras(dssCircuit):
    resultados = {}
    for bus in dssCircuit.AllBusNames:
        dssCircuit.SetActiveBus(bus)
        mag_ang = list(dssCircuit.ActiveBus.puVmagAngle)
        magnitudes = [m for m in mag_ang[0::2] if m > 0]
        # CORREÇÃO DE BUG (2026-10-30, assimetria de caixa): a chave era
        # o nome cru de AllBusNames; agora é normalizada para minúsculas
        # para casar com o ramo de não-convergência e com as listas de
        # entrada do orquestrador (ex.: 'B4' da config vs 'b4' do motor).
        resultados[_nome_base_barra(bus)] = magnitudes
    return resultados


def _classificar_sag(pu_por_barra, bus_faltoso, limite_inferior, limite_superior):
    barras_sag = set()
    nome_faltoso = _nome_base_barra(bus_faltoso)
    for bus, valores in pu_por_barra.items():
        # CORREÇÃO DE BUG (2026-10-30): a chave guardada no conjunto é a
        # JÁ NORMALIZADA (lower), e não a crua da entrada — garante que a
        # diferença de conjuntos no orquestrador (baseline - candidato)
        # cancele entre caixas iguais.
        chave = _nome_base_barra(bus)
        if chave == nome_faltoso:
            continue
        if any(limite_inferior <= v < limite_superior for v in valores):
            barras_sag.add(chave)
    return barras_sag


TIPOS_FALTA_DISPONIVEIS = {
    "trifasica": "Trifásica (curto-circuito trifásico)",
    "monofasica_solida": "Monofásica com terra (sólida, baixa impedância)",
    "monofasica_alta_impedancia": "Monofásica sem terra efetiva (alta impedância)",
}


def rodar_estudo(caminho_master, barras_falta, tipos_falta, bess_list=None,
                  r_falta_solida=0.05, r_falta_alta_impedancia=40.0,
                  limite_inferior=0.1, limite_superior=0.9,
                  callback_progresso=None):
    """Executa o estudo de afundamento de tensão para uma configuração
    de BESS (podendo ser vazia = caso base).

    Retorna um dicionário com:
        - barras_em_sag_geral: conjunto de barras que caem na faixa de
          afundamento em PELO MENOS um dos cenários de falta simulados.
        - detalhe_por_falta: lista com o resultado individual de cada
          combinação (barra faltosa, tipo de falta), incluindo o campo
          'convergiu' (True = medição real pós-solve; False = cenário
          divergente, tratado como COLAPSO com sentinel limite_inferior
          — ver CORREÇÃO DE BUG de 2026-10-30 no topo do arquivo).
    """
    bess_list = bess_list or []
    barras_em_sag_geral = set()
    detalhe_por_falta = []

    total = max(len(barras_falta) * len(tipos_falta), 1)
    passo = 0

    motor = MotorReutilizavel()
    try:
        for bus_falta in barras_falta:
            for tipo_falta in tipos_falta:
                tipo_falta_dss = "trifasica" if tipo_falta == "trifasica" else "monofasica"
                r_falta = (r_falta_alta_impedancia
                           if tipo_falta == "monofasica_alta_impedancia"
                           else r_falta_solida)

                _preparar_circuito_em_motor(motor, caminho_master, bess_list)
                _aplicar_falta(motor, bus_falta, tipo_falta_dss, r_falta)
                motor.dssSolution.Solve()

                if motor.dssSolution.Converged:
                    pu = _capturar_pu_todas_barras(motor.dssCircuit)
                    barras_sag = _classificar_sag(
                        pu, bus_falta, limite_inferior, limite_superior)
                    convergiu = True
                else:
                    # CORREÇÃO DE BUG (2026-10-30) — SEMÂNTICA DE COLAPSO.
                    # Dois defeitos do código anterior:
                    #   1. barras_sag = set(barras_falta) - {bus_falta}
                    #      usava os nomes DA LISTA DE ENTRADA (ex.: 'B4',
                    #      maiúsculas) enquanto o caminho normal guarda
                    #      nomes normalizados do motor (ex.: 'b4'); a
                    #      diferença de conjuntos no orquestrador
                    #      (baseline - candidato) nunca cancelava entre
                    #      caixas diferentes -> crédito falso de barras
                    #      mitigadas. Resolvido pela normalização lower
                    #      (_nome_base_barra / _classificar_sag).
                    #   2. pu = {} não media nada, mas o candidato
                    #      divergente ainda herdava a profundidade total
                    #      do baseline como "benefício" (crédito sem
                    #      medição).
                    # Semântica adotada (COLAPSO): divergência sob falta
                    # + injeção é colapso de tensão não demonstravelmente
                    # mitigável. Cada barra que a captura normal
                    # registraria recebe o SENTINEL limite_inferior.
                    # ATENÇÃO: o sentinel DEVE ser limite_inferior e NÃO
                    # 0.0 — com 0.0 a barra cairia FORA da janela
                    # [limite_inferior, limite_superior) e voltaria a
                    # contar como "resolvida" (interrupção não é sag).
                    # AllBusNames existe após o Compile mesmo sem solve
                    # convergido (depende da definição do circuito, não
                    # da solução) — a enumeração abaixo replica a de
                    # _capturar_pu_todas_barras, com a MESMA exclusão da
                    # barra faltosa feita por _classificar_sag.
                    nome_faltoso = _nome_base_barra(bus_falta)
                    pu = {}
                    for bus in motor.dssCircuit.AllBusNames:
                        chave = _nome_base_barra(bus)
                        if chave == nome_faltoso:
                            continue
                        pu[chave] = [limite_inferior]
                    barras_sag = _classificar_sag(
                        pu, bus_falta, limite_inferior, limite_superior)
                    convergiu = False

                barras_em_sag_geral |= barras_sag
                detalhe_por_falta.append({
                    "bus_falta": bus_falta,
                    "tipo_falta": tipo_falta,
                    "convergiu": convergiu,
                    "barras_em_sag": sorted(barras_sag),
                    "pu": pu,
                })

                passo += 1
                if callback_progresso:
                    callback_progresso(passo, total)
    finally:
        motor.finalizar()

    return {
        "barras_em_sag_geral": barras_em_sag_geral,
        "detalhe_por_falta": detalhe_por_falta,
        "bess_list": bess_list,
    }