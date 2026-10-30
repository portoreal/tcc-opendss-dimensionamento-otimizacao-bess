__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Wrapper em torno do OpenDSS Engine, usando a biblioteca DSS-Python
(pacote 'dss-python', projeto DSS-Extensions).

MUDANÇA DE MOTOR (registrada por transparência metodológica):
Diferente da versão anterior deste arquivo (baseada em win32com/COM, que
carregava o OpenDSSEngine.DLL oficial da EPRI, registrado via regsvr32),
esta versão utiliza o motor mantido pelo projeto DSS-Extensions
(https://dss-extensions.org). Trata-se de uma reimplementação com muito
boa compatibilidade com o motor oficial EPRI, mas não é o mesmo binário.
A linguagem de script .dss e os nomes das propriedades/métodos usados
aqui (AllNodeVmagPUByPhase, AllNodeDistancesByPhase, LoadMult, etc.) são
idênticos em ambas as implementações, conforme tabela de compatibilidade
oficial do projeto DSS-Extensions.

CORREÇÃO DE BUG (caminhos com espaço, ex.: pastas OneDrive corporativas):
O comando 'compile' é enviado ao parser de scripts do próprio OpenDSS,
que trata espaço como separador de parâmetros - exatamente como o "cmd"
do Windows. Caminhos como
'C:\\Users\\usuario\\OneDrive - EMPRESA S.A\\...\\Master.dss' quebravam
no primeiro espaço, gerando o erro "(#242) Redirect file not found".
A correção envolve o caminho entre aspas duplas dentro do próprio
comando .dss, que é a forma padrão e documentada do parser OpenDSS para
tratar um caminho com espaços como um único token.
"""

import os
import sys

import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

from dss import dss as dss_global


fontP = FontProperties()
fontP.set_size("small")


def _obter_novo_contexto():
    """Obtém um contexto isolado do Engine, quando suportado pela versão
    instalada do DSS-Python (recomendado para evitar interferência entre
    threads/instâncias simultâneas, ex.: o Editor de Rede e o Módulo de
    Otimização de BESS rodando em momentos próximos).

    ATENÇÃO: o nome do método 'NewContext()' não pôde ser confirmado com
    certeza absoluta na documentação no momento em que este código foi
    escrito (indisponibilidade temporária da ferramenta de busca). Por
    segurança, o fallback abaixo garante que o sistema continue
    funcionando mesmo que o método não exista na versão instalada -
    nesse caso, todas as instâncias de DSS passam a compartilhar o
    mesmo contexto global (comportamento equivalente ao que já tínhamos
    com win32com, então não há regressão, apenas perda de um benefício
    extra). Recomenda-se validar este ponto assim que possível.
    """
    try:
        return dss_global.NewContext()
    except AttributeError:
        return dss_global


class DSS(object):
    """Wrapper em torno do OpenDSS Engine (via DSS-Python) para compilar,
    resolver e analisar circuitos elétricos."""

    # ------------------------------------------------------------------ #
    def __init__(self, dssFileName: str):
        """Inicializa o Engine do OpenDSS e compila o modelo informado."""

        if not os.path.exists(dssFileName):
            print(f"[ERRO] Arquivo não encontrado: {dssFileName}")
            sys.exit(1)

        try:
            self.dssObj = _obter_novo_contexto()
        except Exception as e:
            print("[ERRO] Não foi possível iniciar o Engine do OpenDSS (DSS-Python).")
            print("Verifique se o pacote 'dss-python' está instalado corretamente.")
            print("Detalhe:", e)
            sys.exit(1)

        print("[OK] Engine do OpenDSS (DSS-Python) iniciado com sucesso.")

        # Atribui as interfaces principais para facilitar o acesso
        self.dssText = self.dssObj.Text
        self.dssCircuit = self.dssObj.ActiveCircuit
        self.dssSolution = self.dssCircuit.Solution
        self.dssCktElement = self.dssCircuit.ActiveCktElement
        self.dssBus = self.dssCircuit.ActiveBus
        self.dssMeters = self.dssCircuit.Meters
        self.dssPDElement = self.dssCircuit.PDElements

        # Sempre é uma boa prática limpar o DSS antes de carregar um novo circuito
        self.dssObj.ClearAll()

        # Carrega o arquivo master do circuito no OpenDSS.
        # IMPORTANTE: o caminho é envolvido em aspas duplas DENTRO do
        # próprio comando .dss, pois o parser de scripts do OpenDSS trata
        # espaço como separador de parâmetros. Sem as aspas, caminhos como
        # "...\\OneDrive - EMPRESA S.A\\..." quebram no primeiro espaço.
        print(f"[INFO] Compilando circuito: {dssFileName}")
        self.dssText.Command = f'compile "{dssFileName}"'
        print("[OK] Circuito compilado com sucesso.")

    # ------------------------------------------------------------------ #
    def versionDSS(self) -> str:
        """Retorna a versão do Engine do OpenDSS."""
        self.version = self.dssObj.Version
        return self.version

    # ------------------------------------------------------------------ #
    def myShow(self):
        """Exibe as tensões de linha-neutro por nó (comando nativo do DSS)."""
        self.dssText.Command = "show voltage LN nodes"

    # ------------------------------------------------------------------ #
    def mySolve(self, loadmult: float):
        """Ajusta o multiplicador de carga e resolve o fluxo de potência."""
        self.dssSolution.LoadMult = loadmult
        self.dssSolution.Solve()

        if not self.dssSolution.Converged:
            print(f"[AVISO] A solução NÃO convergiu para LoadMult = {loadmult}")
        else:
            print(f"[OK] Solução convergiu para LoadMult = {loadmult}")

    # ------------------------------------------------------------------ #
    def plot_profile(self, loadmult: float, mostrar: bool):
        """Plota o perfil de tensão por fase em função da distância do medidor.

        As imagens não são salvas em disco. Se mostrar=False, o gráfico
        é apenas gerado e descartado sem abrir janela.
        """

        VA = self.dssCircuit.AllNodeVmagPUByPhase(1)
        DistA = self.dssCircuit.AllNodeDistancesByPhase(1)
        VB = self.dssCircuit.AllNodeVmagPUByPhase(2)
        DistB = self.dssCircuit.AllNodeDistancesByPhase(2)
        VC = self.dssCircuit.AllNodeVmagPUByPhase(3)
        DistC = self.dssCircuit.AllNodeDistancesByPhase(3)

        plt.figure()
        ax = plt.subplot(1, 1, 1)
        ax.set_xlim([0, 1.6])
        ax.set_ylim([0.9, 1.1])

        plt.title(f"Voltage Profile - LoadMult = {loadmult:.2f}")
        plt.plot(DistA, VA, "k*", label="VA")
        plt.plot(DistB, VB, "b+", label="VB")
        plt.plot(DistC, VC, "gd", label="VC")
        plt.plot([0, 1.6], [0.95, 0.95], "r")
        plt.plot([0, 1.6], [1.05, 1.05], "r")
        plt.ylabel("Volts (pu)")
        plt.xlabel("Distance from Energy Meter")

        plt.legend(
            bbox_to_anchor=(0, 0.96, 1, .102),
            loc=3,
            ncol=4,
            borderaxespad=0,
            shadow=True,
            fancybox=True,
            prop=fontP,
        )
        plt.grid(True)

        if mostrar:
            plt.show()
        else:
            plt.close()

    # ------------------------------------------------------------------ #
    def find_Vmin(self) -> float:
        """Retorna a menor tensão (pu) entre as três fases."""

        VA = self.dssCircuit.AllNodeVmagPUByPhase(1)
        VB = self.dssCircuit.AllNodeVmagPUByPhase(2)
        VC = self.dssCircuit.AllNodeVmagPUByPhase(3)

        Vmin = min(VA)

        if Vmin > min(VB):
            Vmin = min(VB)
        if Vmin > min(VC):
            Vmin = min(VC)

        return Vmin

    # ------------------------------------------------------------------ #
    # MÉTODOS ADICIONADOS PARA O MÓDULO DE VALIDAÇÃO DO MODELO
    # COMPUTACIONAL (comparação com os sistemas de referência IEEE e
    # desenho da topologia).
    # ------------------------------------------------------------------ #

    def obter_tensoes_por_barra(self) -> dict:
        """Retorna {(barra, fase): tensao_pu}, percorrendo todas as
        barras ativas do circuito. Usado na Validação do Modelo
        Computacional para sistemas aterrados em estrela (tensão LN),
        comparando diretamente com os relatórios de solução oficiais do
        IEEE PES Test Feeder, que reportam tensão por barra e por fase
        (1=A, 2=B, 3=C).

        Confirmado empiricamente após execução completa da validação
        para os 4 sistemas, sem erro de atributo."""

        resultado = {}
        for nome_barra in self.dssCircuit.AllBusNames:
            self.dssCircuit.SetActiveBus(nome_barra)
            bus_ativo = self.dssCircuit.ActiveBus

            # puVmagAngle retorna pares [mag1, ang1, mag2, ang2, ...],
            # um par por nó/fase presente naquela barra.
            valores = bus_ativo.puVmagAngle
            fases_presentes = bus_ativo.Nodes  # ex.: [1, 2, 3]

            for indice, fase in enumerate(fases_presentes):
                magnitude_pu = valores[indice * 2]
                resultado[(nome_barra.upper(), str(fase))] = magnitude_pu

        return resultado

    # ------------------------------------------------------------------ #
    def obter_tensoes_LL_por_barra(self) -> dict:
        """Retorna {(barra, 'fA-fB'): tensao_LL_pu}, calculado a partir
        das tensões fasoriais complexas de cada nó.

        Necessário para sistemas delta sem neutro aterrado (ex.: IEEE 37
        Node Test Feeder), cuja tensão linha-neutro calculada
        internamente pelo motor de fluxo de potência corresponde a uma
        referência matemática (neutro virtual), sem significado físico
        direto. Nesses casos, o próprio IEEE publica os resultados de
        referência em tensão de linha (fase-fase), e não em tensão de
        fase (fase-neutro)."""

        resultado = {}
        for nome_barra in self.dssCircuit.AllBusNames:
            self.dssCircuit.SetActiveBus(nome_barra)
            bus_ativo = self.dssCircuit.ActiveBus

            fases_presentes = list(bus_ativo.Nodes)
            tensoes_complexas = bus_ativo.Voltages  # [re1, im1, re2, im2, ...]
            kv_base_ln = bus_ativo.kVBase  # base LN, em kV

            if not kv_base_ln:
                continue

            kv_base_ll = kv_base_ln * (3 ** 0.5)

            # Monta dicionário fase -> tensão complexa (em Volts)
            fasores = {}
            for indice, fase in enumerate(fases_presentes):
                parte_real = tensoes_complexas[indice * 2]
                parte_imag = tensoes_complexas[indice * 2 + 1]
                fasores[fase] = complex(parte_real, parte_imag)

            # Combinações de pares de fase presentes nesta barra (1-2, 2-3, 3-1)
            for fase_a, fase_b in [(1, 2), (2, 3), (3, 1)]:
                if fase_a in fasores and fase_b in fasores:
                    tensao_ll_volts = abs(fasores[fase_a] - fasores[fase_b])
                    tensao_ll_pu = tensao_ll_volts / (kv_base_ll * 1000.0)
                    resultado[(nome_barra.upper(), f"{fase_a}-{fase_b}")] = tensao_ll_pu

        return resultado

    # ------------------------------------------------------------------ #
    def obter_linhas(self) -> list:
        """Retorna uma lista de tuplas (bus1, bus2, e_chave) para cada
        elemento 'Line' do circuito, usada para montar a topologia da
        rede. O terceiro valor da tupla, 'e_chave', diferencia uma
        linha comum de distribuição (e_chave=False) de uma chave/switch
        (e_chave=True) - ambas são representadas no OpenDSS como
        elementos 'Line', distinguidas apenas pela propriedade nativa
        'IsSwitch' (ex.: 'switch=yes' na definição do script .dss).

        Essa distinção permite que o desenho de topologia (ver
        validacao_topologia.py) represente chaves com um estilo visual
        próprio (linha tracejada), segregando-as visualmente das linhas
        de distribuição comuns (linha contínua).

        NOTA: linhas/chaves NÃO capturam conexões feitas por
        transformadores ou reguladores de tensão - ver
        obter_transformadores() para essa finalidade complementar.

        ATENÇÃO (transparência metodológica): a propriedade 'IsSwitch'
        é documentada na API do dss-python/DSS-Extensions, mas não foi
        isoladamente testada antes de seu uso aqui. Em caso de falha
        de atributo, o código assume e_chave=False (comportamento
        anterior, tratando a linha como comum) em vez de interromper a
        execução."""

        linhas = []
        dssLines = self.dssCircuit.Lines

        if dssLines.First > 0:
            while True:
                bus1 = dssLines.Bus1.split(".")[0].upper()
                bus2 = dssLines.Bus2.split(".")[0].upper()

                try:
                    e_chave = bool(dssLines.IsSwitch)
                except Exception:
                    e_chave = False

                linhas.append((bus1, bus2, e_chave))

                if dssLines.Next == 0:
                    break

        return linhas

    # ------------------------------------------------------------------ #
    def obter_nomes_reguladores(self) -> set:
        """Retorna o conjunto de nomes (em maiúsculas) de transformadores
        que possuem um elemento 'RegControl' associado - ou seja, que
        atuam como reguladores de tensão sob controle automático, e não
        como transformadores de distribuição comuns.

        Usado por obter_transformadores() para diferenciar, na topologia
        desenhada, um transformador de distribuição (linha contínua
        verde) de um banco de reguladores de tensão (linha tracejada
        verde) - ambos representados internamente no OpenDSS como
        elementos 'Transformer', distinguidos apenas pela existência de
        um 'RegControl' referenciando o nome do transformador via sua
        propriedade 'Transformer='.

        ATENÇÃO (transparência metodológica): a propriedade
        'RegControls.Transformer' é documentada na API do
        dss-python/DSS-Extensions, mas não foi isoladamente testada
        antes de seu uso aqui. Em caso de falha de atributo, o conjunto
        retornado permanece incompleto para aquele RegControl específico
        (comportamento conservador: o transformador correspondente seria
        desenhado como comum, não como regulador)."""

        nomes = set()
        dssRegControls = self.dssCircuit.RegControls

        if dssRegControls.First > 0:
            while True:
                try:
                    nomes.add(dssRegControls.Transformer.upper())
                except Exception:
                    pass

                if dssRegControls.Next == 0:
                    break

        return nomes

    # ------------------------------------------------------------------ #
    def obter_transformadores(self) -> list:
        """Retorna uma lista de tuplas (bus1, bus2, e_regulador) para
        cada elemento 'Transformer' do circuito - incluindo os
        transformadores usados para representar bancos de reguladores
        de tensão monofásicos (ex.: Reg1/Reg2/Reg3 no sistema de 13 nós,
        ou RG7 no sistema de 37 nós), que também estabelecem
        conectividade elétrica entre barras, assim como as linhas.

        O terceiro valor da tupla, 'e_regulador', diferencia um
        transformador de distribuição comum (e_regulador=False,
        desenhado em linha contínua verde) de um banco de reguladores
        de tensão sob controle automático (e_regulador=True, desenhado
        em linha tracejada verde) - ver obter_nomes_reguladores().

        Usado para complementar a topologia desenhada a partir de
        obter_linhas(), evitando que barras conectadas exclusivamente
        por transformadores apareçam como pontos isolados no desenho
        (ex.: a barra da fonte, conectada apenas pelo transformador de
        subestação, em praticamente todos os sistemas de teste IEEE).

        Considera apenas os 2 primeiros terminais de cada transformador
        (cobre o caso usual de transformadores de 2 enrolamentos; em
        bancos de 3 enrolamentos, o 3º terminal não é desenhado).

        CORREÇÃO DE BUG (registrada por transparência): a primeira
        versão deste método usava a referência self.dssCktElement,
        capturada uma única vez no __init__, que NÃO acompanhava
        corretamente a troca do elemento ativo durante a iteração
        Transformers.First/Next. A correção consulta
        self.dssCircuit.ActiveCktElement NOVAMENTE a cada iteração
        (propriedade "fresca"), em vez de reutilizar a referência salva
        no __init__."""

        nomes_reguladores = self.obter_nomes_reguladores()

        pares = []
        dssTransformers = self.dssCircuit.Transformers

        if dssTransformers.First > 0:
            while True:
                try:
                    elemento_ativo = self.dssCircuit.ActiveCktElement
                    nomes_bus = elemento_ativo.BusNames
                    buses_base = [b.split(".")[0].upper() for b in nomes_bus]

                    nome_transformador = dssTransformers.Name.upper()
                    e_regulador = nome_transformador in nomes_reguladores

                    if len(buses_base) >= 2 and buses_base[0] != buses_base[1]:
                        pares.append((buses_base[0], buses_base[1], e_regulador))
                except Exception:
                    pass

                if dssTransformers.Next == 0:
                    break

        return pares

    # ------------------------------------------------------------------ #
    def obter_coordenadas_barras(self) -> dict:
        """Retorna um dicionário {nome_barra: (x, y)} com as coordenadas
        carregadas via comando 'Buscoords' no script .dss do circuito
        ativo (arquivo de coordenadas oficial do pacote IEEE/OpenDSS).

        Barras sem coordenada definida (x=0, y=0 por padrão no OpenDSS)
        são retornadas, mas devem ser tratadas com cautela em um
        eventual desenho de topologia (podem sobrepor-se na origem do
        gráfico, caso não possuam Buscoords real associado - ver nota em
        validacao_topologia.py sobre barras com coordenada OFICIAL
        legítima em (0,0))."""

        coordenadas = {}
        for nome_barra in self.dssCircuit.AllBusNames:
            self.dssCircuit.SetActiveBus(nome_barra)
            bus_ativo = self.dssCircuit.ActiveBus
            coordenadas[nome_barra.upper()] = (bus_ativo.x, bus_ativo.y)

        return coordenadas

    # ------------------------------------------------------------------ #
    def obter_perdas_totais_kw(self) -> float:
        """Retorna as perdas totais ativas do circuito (kW), obtidas
        diretamente da propriedade Losses do circuito."""

        perdas = self.dssCircuit.Losses  # retorna [kW, kvar], em Watts
        return perdas[0] / 1000.0

    # ------------------------------------------------------------------ #
    def resolver_validacao_oficial(self, caminho_master: str,
                                     comandos_pre_solve: list,
                                     comandos_taps_fixos: list,
                                     desligar_controle_global: bool = True,
                                     loadmult: float = 1.0):
        """Replica a sequência oficial dos scripts 'Run_' do pacote
        IEEE/OpenDSS para os sistemas de teste (13, 34, 37 e 123 nós):
        recompila o circuito do zero, aplica comandos de pré-solução
        (ex.: criação de um EnergyMeter, carregamento de BusCoords
        quando o master compilado diretamente não os inclui) e força os
        taps dos reguladores nos valores publicados pelo IEEE antes de
        resolver o fluxo de potência.

        Esse é o modo que deve ser usado para comparação direta com a
        tabela de resultados oficialmente publicada pelo IEEE PES Test
        Feeder Committee - os resultados publicados para sistemas com
        regulação automática de tensão foram obtidos com os taps
        fixados manualmente, e não com o controle automático em
        operação livre (ver nota de transparência metodológica em
        validacao_ieee.py).

        Para o comportamento operacional "normal" (reguladores em
        controle automático, representativo da operação real da rede),
        utilize compile + mySolve diretamente, sem este método.

        Parameters
        ----------
        desligar_controle_global : bool
            Se True, envia 'Set Controlmode=OFF' após aplicar os taps
            (padrão usado pelos sistemas de 13 e 34 nós). Se False,
            assume que o travamento já foi feito individualmente por
            regulador dentro de 'comandos_taps_fixos' (ex.: via
            RegControl.<nome>.maxtapchange=0, padrão usado pelo sistema
            de 123 nós). Para o sistema de 37 nós, que não requer taps
            fixos, utilize desligar_controle_global=False e
            comandos_taps_fixos=[].
        """

        print(f"[INFO] Recompilando para validação estrita: {caminho_master}")
        self.dssText.Command = f'compile "{caminho_master}"'

        for comando in comandos_pre_solve:
            self.dssText.Command = comando

        for comando in comandos_taps_fixos:
            self.dssText.Command = comando

        if desligar_controle_global:
            self.dssText.Command = "Set Controlmode=OFF"

        self.mySolve(loadmult)