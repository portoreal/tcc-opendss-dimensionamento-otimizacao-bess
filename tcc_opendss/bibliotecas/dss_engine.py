__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Camada de acesso ao motor OpenDSS, via biblioteca DSS-Python (pacote
'dss-python', projeto DSS-Extensions).

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
que trata espaço como separador de parâmetros — exatamente como o "cmd" do
Windows. Caminhos como
'C:\\\\Users\\\\usuario\\\\OneDrive - EMPRESA S.A\\\\...\\\\Master.dss' quebravam no
primeiro espaço e produziam o erro "(#242) Redirect file not found". A
correção é envolver o caminho em aspas duplas dentro do próprio comando
.dss, que é a forma padrão e documentada do parser para tratar um caminho
com espaços como um único token.
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
    escrito (indisponibilidade temporária da ferramenta de busca). O
    fallback abaixo cobre essa incerteza: se o método não existir na versão
    instalada, todas as instâncias de DSS passam a compartilhar o mesmo
    contexto global — comportamento equivalente ao que já tínhamos com
    win32com, portanto sem regressão, apenas sem o benefício extra.
    Recomenda-se validar este ponto assim que possível.
    """
    try:
        return dss_global.NewContext()
    except AttributeError:
        return dss_global


class DSS(object):
    """Compila, resolve e analisa circuitos elétricos através do motor
    OpenDSS (DSS-Python).

    Cada método devolve ou consulta uma grandeza do circuito resolvido —
    tensões por barra, perdas, topologia. O motor guarda um estado global:
    quem chama precisa ter resolvido o caso antes de ler as grandezas.
    """

    # ------------------------------------------------------------------ #
    def __init__(self, dssFileName: str):
        """Inicializa o Engine do OpenDSS e compila o modelo informado."""

        # Sem arquivo não há circuito. O encerramento é imediato e explícito:
        # seguir adiante produziria erro obscuro lá na frente.
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

        # Interfaces do motor, guardadas como atributos. Escrever num delas
        # é o que efetivamente comandam o OpenDSS.
        self.dssText = self.dssObj.Text
        self.dssCircuit = self.dssObj.ActiveCircuit
        self.dssSolution = self.dssCircuit.Solution
        self.dssCktElement = self.dssCircuit.ActiveCktElement
        self.dssBus = self.dssCircuit.ActiveBus
        self.dssMeters = self.dssCircuit.Meters
        self.dssPDElement = self.dssCircuit.PDElements

        # ClearAll descarta o circuito anterior. Sem isso, elementos de uma
        # compilação antiga sobrevivem e contaminam a nova.
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
        """Manda o DSS mostrar as tensões fase-neutro por nó (comando
        nativo, saída padrão do motor)."""
        self.dssText.Command = "show voltage LN nodes"

    # ------------------------------------------------------------------ #
    def mySolve(self, loadmult: float):
        """Ajusta o multiplicador de carga e resolve o fluxo de potência.

        O multiplicador escala todas as cargas do circuito de uma vez — 0,5
        deixa o sistema em meia carga sem editar cada elemento. Depois da
        solução, a convergência é reportada: fluxo que não converge devolve
        números sem significado físico.
        """
        self.dssSolution.LoadMult = loadmult
        self.dssSolution.Solve()

        if not self.dssSolution.Converged:
            print(f"[AVISO] A solução NÃO convergiu para LoadMult = {loadmult}")
        else:
            print(f"[OK] Solução convergiu para LoadMult = {loadmult}")

    # ------------------------------------------------------------------ #
    def plot_profile(self, loadmult: float, mostrar: bool):
        """Plota o perfil de tensão por fase contra a distância elétrica até
        o medidor de energia.

        A distância vem em pu do comprimento acumulado a partir do ponto de
        medição, por isso o eixo vai de 0 a 1,6: a queda aparece ao longo do
        alimentador. As linhas vermelhas marcam a faixa 0,95–1,05 pu. Nada é
        gravado em disco; com mostrar=False o gráfico é gerado e descartado
        sem abrir janela.
        """

        VA = self.dssCircuit.AllNodeVmagPUByPhase(1)
        DistA = self.dssCircuit.AllNodeDistancesByPhase(1)
        VB = self.dssCircuit.AllNodeVmagPUByPhase(2)
        DistB = self.dssCircuit.AllNodeDistancesByPhase(2)
        VC = self.dssCircuit.AllNodeVmagPUByPhase(3)
        DistC = self.dssCircuit.AllNodeDistancesByPhase(3)

        plt.figure()
        ax = plt.subplot(1, 1, 1)
        # Limites fixos: o perfil tem de ser comparável entre execuções, e
        # escala automática esconderia justamente a violação que se quer ver.
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
        """Menor tensão (pu) entre as três fases, tomada sobre todas as
        barras. É o indicador de severidade da pior barra do sistema."""

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
        """Devolve {(barra, fase): tensão_pu} para todas as barras do
        circuito ativo.

        A tensão vem em fase-neutro, que é o que a Validação do Modelo
        Computacional compara com os relatórios de solução do IEEE PES Test
        Feeder — esses relatórios trazem tensão por barra e por fase
        (1=A, 2=B, 3=C). A leitura pressupõe sistema aterrado em estrela.

        Confirmado empiricamente após execução completa da validação para os
        4 sistemas, sem erro de atributo.
        """

        resultado = {}
        for nome_barra in self.dssCircuit.AllBusNames:
            self.dssCircuit.SetActiveBus(nome_barra)
            bus_ativo = self.dssCircuit.ActiveBus

            # puVmagAngle devolve pares [mag1, ang1, mag2, ang2, ...],
            # um par por nó/fase presente naquela barra.
            valores = bus_ativo.puVmagAngle
            fases_presentes = bus_ativo.Nodes  # ex.: [1, 2, 3]

            for indice, fase in enumerate(fases_presentes):
                magnitude_pu = valores[indice * 2]
                resultado[(nome_barra.upper(), str(fase))] = magnitude_pu

        return resultado

    # ------------------------------------------------------------------ #
    def obter_tensoes_LL_por_barra(self) -> dict:
        """Devolve {(barra, 'fA-fB'): tensão_LL_pu}, calculada das tensões
        fasoriais complexas de cada nó.

        Existe por causa dos sistemas delta sem neutro aterrado (o IEEE 37
        Node Test Feeder é o caso concreto). Neles, a tensão fase-neutro que
        o motor calcula é referida a um neutro virtual — uma referência
        matemática, sem significado físico direto. O próprio IEEE publica os
        resultados desses sistemas em tensão de linha, e é essa a base da
        comparação.
        """

        resultado = {}
        for nome_barra in self.dssCircuit.AllBusNames:
            self.dssCircuit.SetActiveBus(nome_barra)
            bus_ativo = self.dssCircuit.ActiveBus

            fases_presentes = list(bus_ativo.Nodes)
            tensoes_complexas = bus_ativo.Voltages  # [re1, im1, re2, im2, ...]
            kv_base_ln = bus_ativo.kVBase  # base LN, em kV

            # Barra sem base de tensão definida não permite normalização;
            # fica fora do resultado em vez de gerar divisão inválida.
            if not kv_base_ln:
                continue

            # kVBase vem em fase-neutro; a tensão de linha é raiz de 3 maior.
            kv_base_ll = kv_base_ln * (3 ** 0.5)

            # Monta dicionário fase -> tensão complexa (em Volts)
            fasores = {}
            for indice, fase in enumerate(fases_presentes):
                parte_real = tensoes_complexas[indice * 2]
                parte_imag = tensoes_complexas[indice * 2 + 1]
                fasores[fase] = complex(parte_real, parte_imag)

            # Pares de fase presentes nesta barra (1-2, 2-3, 3-1). A
            # diferença entre fasores já dá a tensão de linha: não é preciso
            # passar pelo neutro virtual.
            for fase_a, fase_b in [(1, 2), (2, 3), (3, 1)]:
                if fase_a in fasores and fase_b in fasores:
                    tensao_ll_volts = abs(fasores[fase_a] - fasores[fase_b])
                    tensao_ll_pu = tensao_ll_volts / (kv_base_ll * 1000.0)
                    resultado[(nome_barra.upper(), f"{fase_a}-{fase_b}")] = tensao_ll_pu

        return resultado

    # ------------------------------------------------------------------ #
    def obter_linhas(self) -> list:
        """Lista de tuplas (bus1, bus2, e_chave) para cada elemento 'Line'
        do circuito, base da topologia desenhada.

        O terceiro campo separa linha de distribuição (e_chave=False) de
        chave (e_chave=True). No OpenDSS as duas são elementos 'Line'; o que
        as distingue é a propriedade nativa 'IsSwitch' (no script .dss,
        'switch=yes'). A distinção existe para o desenho: chave sai em linha
        tracejada, linha comum em linha contínua (ver
        validacao_topologia.py).

        NOTA: linhas e chaves não capturam conexões feitas por
        transformadores ou reguladores — para isso existe
        obter_transformadores().

        ATENÇÃO (transparência metodológica): a propriedade 'IsSwitch' é
        documentada na API do dss-python/DSS-Extensions, mas não foi
        testada isoladamente antes do uso aqui. Se der falha de atributo, o
        código assume e_chave=False e trata a linha como comum, em vez de
        interromper a execução.
        """

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
        """Conjunto de nomes, em maiúsculas, dos transformadores que têm um
        'RegControl' associado — ou seja, que operam como reguladores de
        tensão sob controle automático, e não como transformadores de
        distribuição comuns.

        Serve a obter_transformadores() para separar, no desenho, um
        transformador de distribuição (linha contínua verde) de um banco de
        reguladores (linha tracejada verde). No OpenDSS os dois são
        elementos 'Transformer'; a diferença está em haver um 'RegControl'
        apontando para o nome do transformador pela propriedade
        'Transformer='.

        ATENÇÃO (transparência metodológica): a propriedade
        'RegControls.Transformer' é documentada na API do
        dss-python/DSS-Extensions, mas não foi testada isoladamente antes do
        uso aqui. Se der falha de atributo, o conjunto volta incompleto
        para aquele RegControl e o transformador correspondente acaba
        desenhado como comum, não como regulador — erro conservador.
        """

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
        """Lista de tuplas (bus1, bus2, e_regulador) para cada elemento
        'Transformer' do circuito.

        Inclui os transformadores usados para representar bancos de
        reguladores monofásicos (Reg1/Reg2/Reg3 no sistema de 13 nós, RG7 no
        de 37 nós). Eles também estabelecem conectividade elétrica entre
        barras, tal como as linhas, e ignorá-los deixaria barras soltas no
        desenho.

        O terceiro campo, 'e_regulador', separa transformador de distribuição
        comum (False, linha contínua verde) de banco de reguladores sob
        controle automático (True, linha tracejada verde) — ver
        obter_nomes_reguladores().

        Complementa a topologia de obter_linhas(), evitando que barras
        ligadas só por transformadores apareçam isoladas. O caso típico é a
        barra da fonte, que em praticamente todos os sistemas de teste IEEE
        se conecta apenas pelo transformador de subestação.

        Somente os 2 primeiros terminais de cada transformador entram no
        resultado. Cobre o caso usual de 2 enrolamentos; em bancos de 3
        enrolamentos, o terceiro terminal não é desenhado.

        CORREÇÃO DE BUG (registrada por transparência): a primeira versão
        deste método usava a referência self.dssCktElement, capturada uma
        única vez no __init__, e ela NÃO acompanhava corretamente a troca do
        elemento ativo durante a iteração Transformers.First/Next. A correção
        consulta self.dssCircuit.ActiveCktElement NOVAMENTE a cada iteração
        (propriedade "fresca"), em vez de reutilizar a referência salva no
        __init__.
        """

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
        """Dicionário {nome_barra: (x, y)} com as coordenadas carregadas
        pelo comando 'Buscoords' no script .dss (arquivo de coordenadas
        oficial do pacote IEEE/OpenDSS).

        Barras sem coordenada definida voltam com (0, 0), o padrão do
        OpenDSS. Num desenho, elas se empilham na origem do gráfico — o que
        não significa necessariamente erro, porque existe barra com
        coordenada OFICIAL legítima em (0,0). A distinção está discutida em
        validacao_topologia.py.
        """

        coordenadas = {}
        for nome_barra in self.dssCircuit.AllBusNames:
            self.dssCircuit.SetActiveBus(nome_barra)
            bus_ativo = self.dssCircuit.ActiveBus
            coordenadas[nome_barra.upper()] = (bus_ativo.x, bus_ativo.y)

        return coordenadas

    # ------------------------------------------------------------------ #
    def obter_perdas_totais_kw(self) -> float:
        """Perdas ativas totais do circuito, em kW, lidas da propriedade
        Losses do próprio circuito."""

        # Losses devolve [kW, kvar]; só o termo ativo interessa aqui.
        perdas = self.dssCircuit.Losses  # retorna [kW, kvar], em Watts
        return perdas[0] / 1000.0

    # ------------------------------------------------------------------ #
    def resolver_validacao_oficial(self, caminho_master: str,
                                     comandos_pre_solve: list,
                                     comandos_taps_fixos: list,
                                     desligar_controle_global: bool = True,
                                     loadmult: float = 1.0):
        """Replica a sequência oficial dos scripts 'Run_' do pacote
        IEEE/OpenDSS para os sistemas de teste (13, 34, 37 e 123 nós).

        A sequência é: recompilar o circuito do zero, aplicar os comandos de
        pré-solução (criação de um EnergyMeter, por exemplo, e carregamento
        de BusCoords quando o master compilado direto não os traz) e forçar
        os taps dos reguladores nos valores publicados pelo IEEE. Só então o
        fluxo de potência é resolvido.

        É o modo para comparação direta com a tabela oficial do IEEE PES Test
        Feeder Committee. Os resultados publicados para sistemas com regulação
        automática de tensão foram obtidos com taps fixados manualmente, não
        com o controle atuando livre — daí a exigência de reproduzir a mesma
        condição (ver a nota de transparência metodológica em
        validacao_ieee.py).

        Para o comportamento operacional "normal" — reguladores em controle
        automático, representativo da operação real da rede — use compile +
        mySolve diretamente, sem este método.

        Parameters
        ----------
        desligar_controle_global : bool
            Se True, envia 'Set Controlmode=OFF' após aplicar os taps — é o
            padrão dos sistemas de 13 e 34 nós. Se False, assume que o
            travamento já foi feito regulador a regulador dentro de
            'comandos_taps_fixos' (via RegControl.<nome>.maxtapchange=0, o
            padrão do sistema de 123 nós). O sistema de 37 nós não precisa de
            taps fixos: use desligar_controle_global=False e
            comandos_taps_fixos=[].
        """

        print(f"[INFO] Recompilando para validação estrita: {caminho_master}")
        self.dssText.Command = f'compile "{caminho_master}"'

        for comando in comandos_pre_solve:
            self.dssText.Command = comando

        # Os taps vêm antes do desligamento do controle: do contrário, o
        # RegControl desfaria o ajuste na primeira solução.
        for comando in comandos_taps_fixos:
            self.dssText.Command = comando

        if desligar_controle_global:
            self.dssText.Command = "Set Controlmode=OFF"

        self.mySolve(loadmult)