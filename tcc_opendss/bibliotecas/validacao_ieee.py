__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Núcleo da Validação do Modelo Computacional: compara o pipeline
OpenDSS + Python (via dss_engine.DSS) contra os sistemas de referência
do IEEE PES Distribution System Analysis Subcommittee (13, 34, 37 e 123
nós), usando os resultados oficialmente publicados pelo comitê.

Fontes documentais utilizadas (registradas por rastreabilidade):
    - Documentos de referência oficiais (.doc, contendo as tabelas de
      solução de fluxo de potência publicadas, e planilhas .xls com os
      dados de entrada originais - impedâncias, cargas, capacitores,
      reguladores, transformadores e switches): obtidos da página de
      recursos do comitê IEEE PES Distribution System Analysis
      Subcommittee (https://cmte.ieee.org/pes-testfeeders/resources/),
      dentro dos pacotes oficiais feeder13.zip, feeder34.zip,
      feeder37.zip e feeder123.zip.
    - Implementação computacional dos sistemas em linguagem de script
      do OpenDSS (.dss, utilizada como instrumento de simulação neste
      trabalho): obtida do repositório de distribuição do OpenDSS
      mantido por terceiros vinculados ao ecossistema EPRI/OpenDSS
      (https://github.com/tshort/OpenDSS/tree/master), e NÃO do próprio
      comitê do IEEE.

Referências bibliográficas:
    - KERSTING, W. H. Radial Distribution Test Feeders. IEEE
      Transactions on Power Systems, v. 6, n. 3, 1991.
    - SCHNEIDER, K. P. et al. Analytic Considerations and Design Basis
      for the IEEE Distribution Test Feeders. IEEE Transactions on
      Power Systems, v. 33, n. 3, 2018.
    - SHORT, T. OpenDSS — Electrical power system simulation tool
      (mirror/distribution repository). GitHub, 2026. Disponível em:
      https://github.com/tshort/OpenDSS.

TRANSPARÊNCIA METODOLÓGICA (ler antes de confiar nos resultados):

1) Para os sistemas de 13, 34 e 123 nós, os resultados oficiais do IEEE
   foram publicados com os TAPS dos reguladores FIXADOS nos valores
   reportados, e com o controle automático de tensão DESLIGADO.

2) O sistema de 37 nós é um caso particular: sistema trifásico a três
   fios, em configuração DELTA, sem neutro aterrado - comparação
   realizada em tensão de LINHA (VLL), via obter_tensoes_LL_por_barra().

   ACHADO CONFIRMADO (fonte): o sistema de 37 nós apresenta erro
   sistemático elevado (~3,8-4,0% em A-B/C-A). Causa raiz confirmada por
   comparação direta com 'Transformer Data.xls' oficial: o transformador
   de subestação é especificado com impedância NOMINAL real (R=2%, X=8%),
   fielmente reproduzida no arquivo de terceiros 'ieee37.dss', ao passo
   que os demais sistemas (13, 34, 123 nós) "enrijecem" artificialmente
   essa mesma impedância, reproduzindo a premissa de barra de fonte
   rígida assumida pelo documento de solução oficial do IEEE.

   RESOLUÇÃO METODOLÓGICA IMPLEMENTADA E CONFIRMADA EXPERIMENTALMENTE:
   criado o arquivo derivado 'ieee37_corrigido.dss' (NÃO oficial,
   elaborado neste trabalho), aplicando ao transformador de subestação a
   mesma técnica de enrijecimento de impedância já usada nos demais
   sistemas de referência. A primeira correção reduziu o erro máximo de
   7,68% para ~0,75% (valor inicialmente estimado e depois CONFIRMADO
   por medição: a configuração v3 mediu 0,7464%), confirmando a causa
   raiz dominante. Após essa correção, identificou-se um resíduo
   sistemático e aproximadamente uniforme em toda a rede (assinatura
   típica de divergência de tap de regulador, e não de erro de fluxo de
   potência propriamente dito). A posição final de tap do regulador RG7
   (open-delta) É PUBLICADA pelo documento de solução oficial, na tabela
   "VOLTAGE REGULATOR DATA" (TAP=7 para o ramo A-B/'reg1a'; TAP=4 para o
   ramo C-B/'reg1c'; convertidos pela convenção ANSI de 0,625% por
   posição: 1,04375 pu e 1,025 pu), valores cruzados e confirmados pela
   tabela "VOLTAGE PROFILE" do mesmo documento (nó 'RG7': A-B=1,0437 pu;
   B-C=1,0250 pu). Uma SEGUNDA CORREÇÃO, travando esses taps, foi MEDIDA
   em erro máximo de 1,38% - PIOR que a primeira. Uma TERCEIRA CORREÇÃO,
   com o controle automático de tensão (LDC) ativo, mediu 0,7464% -
   ainda REPROVADO (tolerância 0,5%). O DIAGNÓSTICO FINAL, CONFIRMADO
   POR EXPERIMENTO CONTROLADO, identificou que a causa raiz do resíduo
   era uma PARTICULARIDADE DO MOTOR OpenDSS: em transformadores de DOIS
   enrolamentos, a resistência série efetiva do modelo é alimentada pelo
   parâmetro %LoadLoss (DEFAULT 1,5556%), e NÃO pelos %r dos
   enrolamentos. O enrijecimento das correções anteriores era, portanto,
   ILUSÓRIO quanto à resistência - o SubXF mantinha R série = 1,5556%
   (default não tocado), e os reguladores (XHL=1, SEM %LoadLoss)
   herdavam o mesmo default. Os sistemas que APROVAM declaram impedância
   quase nula de forma explícita (123-bus: "XHL=.001 %LoadLoss=0.00001
   ppm=0.0", comentário "KERSTING ASSUMES NO IMPEDANCE IN THE REGULATOR";
   13-bus: "XHL=0.01 %LoadLoss=0.01"), reproduzindo a premissa do
   gabarito oficial (fonte rígida, regulador SEM impedância). QUARTA E
   ATUAL CORREÇÃO: SubXF com %LoadLoss enrijecido por /1000; reguladores
   com XHL=.001 e %LoadLoss=0.00001 (técnica do 123-bus); taps oficiais
   7/4 travados; controle global desligado. RESULTADO MEDIDO: erro máximo
   de 0,0147% - APROVADO.

   ACHADO INVESTIGADO E DESCARTADO COMO ERRO: observou-se inicialmente
   que os valores R/X do compensador do RegControl no '.dss' (R=-0,201/
   X=3,348 para reg1a; R=2,799/X=1,848 para reg1c) divergem dos valores
   nameplate oficiais da planilha 'Regulator Data.xls' (R=1,5/X=3,0,
   simétrico entre os dois ramos). Após investigação (W. H. Kersting,
   relatório "Radial Distribution Test Feeders", confirma que o
   regulador do sistema de 37 nós é conectado em OPEN DELTA), concluiu-
   se que essa diferença NÃO é um erro de modelagem: valores R/X
   nameplate de reguladores em conexão open-delta exigem uma
   transformação trigonométrica (defasagem de 30°) para o referencial
   efetivo visto pelo software de simulação, resultando justamente em
   valores assimétricos entre os dois ramos monofásicos - prática
   documentada na literatura de modelagem de reguladores de tensão.
   Este achado foi, portanto, tratado como hipótese investigada e
   refutada, e não alterado nos arquivos '.dss' (original ou corrigido).

   Mantido como REPROVADO na entrada original ('IEEE 37 Node Test
   Feeder') por rigor metodológico, por refletir o arquivo de terceiros
   efetivamente distribuído e amplamente reutilizado pela comunidade,
   com controle automático de tensão (sem taps fixados).

3) Para o sistema de 123 nós, identificou-se uma divergência isolada na
   barra '610' (secundário Delta-Delta sem carga e sem referência de
   terra), tratada como EXCEÇÃO DOCUMENTADA (não contabilizada no erro
   máximo oficial, por ser isolada e com causa raiz confirmada como
   física, não de parâmetro - ver 'Transformer Data.xls' oficial, que
   confirma os parâmetros do transformador correspondente como
   idênticos aos valores publicados).

   ACHADO ADICIONAL: a planilha oficial 'Switch Data.xls' documenta 5
   chaves normalmente abertas, mas o arquivo de terceiros
   'IEEE123Master.dss' implementa apenas 2 delas - as barras 251, 350 e
   451, e as chaves associadas a elas, estão ausentes.

   RESOLUÇÃO METODOLÓGICA IMPLEMENTADA: criado o arquivo derivado
   'IEEE123Master_corrigido.dss' (NÃO oficial, elaborado neste
   trabalho), adicionando as 3 chaves normalmente abertas ausentes,
   restaurando a fidelidade topológica completa frente à documentação
   oficial. BUG ENCONTRADO E CORRIGIDO (registrado por transparência):
   a primeira versão desse arquivo usava comandos explícitos "Open
   Line.SwX term=1" para refletir fielmente a condição "aberta" da
   planilha oficial, o que causou o erro "Bus '251' not found" durante
   a compilação (motor dss-python/AltDSS parece deixar de reconhecer,
   na lista de barras ativas, uma barra cujo único elemento de conexão
   tem o terminal correspondente aberto - comportamento não observado
   no motor COM oficial da EPRI). Como as barras 251/350/451 não
   possuem NENHUMA outra conexão nem carga, a correção manteve as
   chaves Sw9/Sw10/Sw11 FECHADAS (sem comando "Open"), produzindo
   exatamente o mesmo efeito elétrico de uma chave aberta - nenhuma
   corrente flui para um ramal morto sem caminho de retorno - técnica
   idêntica à já empregada pelo arquivo original em Sw7/Sw8. Esse
   sistema corrigido é registrado como uma entrada adicional em
   SISTEMAS_DISPONIVEIS ("IEEE 123 Node Test Feeder (corrigido)").
   Diferente do caso do sistema de 37 nós, espera-se que o resultado
   numérico desta versão corrigida seja IDÊNTICO ao da versão original,
   uma vez que os ramais adicionados são dead-ends sem carga e sem
   qualquer outra conexão à rede - confirmando que a omissão
   identificada, embora real e digna de registro, não comprometia a
   validação numérica do sistema, apenas sua fidelidade topológica.

4) Confirmado empiricamente, após execução completa da validação para
   os sistemas originais, que os métodos auxiliares de dss_engine.py
   funcionam corretamente na instalação utilizada.

5) Os arquivos de referência numérica (tabelas de tensão) foram
   transcritos manualmente a partir dos documentos originais (.doc) do
   IEEE, e são REAPROVEITADOS, sem qualquer alteração, para a validação
   dos sistemas corrigidos - uma vez que o gabarito de comparação (o
   documento de solução oficial) é o mesmo; apenas o instrumento de
   simulação (arquivo .dss) é distinto entre a versão original e a
   versão corrigida de cada sistema.

6) O objeto DSS já compilado e resolvido durante a validação de cada
   sistema é devolvido junto do resultado (chave 'objeto_dss'), para
   ser reaproveitado pelo módulo de desenho de topologia
   (validacao_topologia.py).

7) Os masters de 34 e 123 nós não incluem o comando 'Buscoords' em seu
   próprio texto - adicionado explicitamente via comandos_pre_solve.
   Barras conectadas exclusivamente por transformadores exigiram o
   método dss_engine.obter_transformadores() para serem corretamente
   desenhadas na topologia, incluindo barras com coordenada oficial
   legítima em (0, 0) (barra '800' no sistema de 34 nós; barra '799r'
   no sistema de 37 nós).

8) CONVENÇÃO VISUAL DA TOPOLOGIA (ver validacao_topologia.py): linhas
   comuns (contínua cinza), chaves/switches (tracejada cinza),
   transformadores de distribuição (contínua verde) e reguladores de
   tensão (tracejada verde) são desenhados com estilos visuais
   distintos, segregando os quatro tipos de elemento. Essa distinção
   depende dos métodos obter_linhas() e obter_transformadores() de
   dss_engine.py retornarem, respectivamente, as flags 'e_chave' e
   'e_regulador' para cada elemento.
"""

import os
import csv

from .projeto import OPEN_DSS_DIR
from .dss_engine import DSS


DIR_VALIDACAO = os.path.join(OPEN_DSS_DIR, "validacao_ieee")
DIR_REFERENCIAS = os.path.join(DIR_VALIDACAO, "referencias")
DIR_SAIDA = os.path.join(DIR_VALIDACAO, "saida")

# ------------------------------------------------------------
# TRANSPARÊNCIA TÉCNICA — localização dos modelos de teste IEEE.
# Dois layouts válidos, resolvidos por candidatos RELATIVOS a __file__
# (via OPEN_DSS_DIR, que é a pasta do projeto em runtime):
#   1. Layout do repositório PUBLICADO: 'IEEE/' é IRMÃ da pasta do
#      projeto (<raiz>/IEEE/), e o código vive em <raiz>/tcc_opendss/.
#   2. Layout de DESENVOLVIMENTO: 'IEEETestCases/' dentro da pasta do
#      projeto (<raiz>/tcc_opendss/IEEETestCases/).
# Vence o primeiro candidato cujo diretório exista. Se nenhum existir,
# permanece o primeiro — o debugger (check_dados_referencia_ieee) então
# exibe o problema em vez de a validação falhar de forma opaca.
#
# MODO CONGELADO (.exe --onedir): OPEN_DSS_DIR aponta para
# <pasta do exe>/tcc_opendss (ver projeto.py), portanto
# dirname(OPEN_DSS_DIR) = pasta do exe. Aí entra o terceiro candidato,
# <pasta do exe>/IEEE — a distribuição leva "IEEE/" ao lado do
# executável, espelhando o layout do repositório.
# ------------------------------------------------------------
import sys as _sys

_CONGELADO = bool(getattr(_sys, "frozen", False))

_CANDIDATOS_DIR_FEEDERS = [
    os.path.join(os.path.dirname(OPEN_DSS_DIR), "IEEE"),  # repo publicado
    os.path.join(OPEN_DSS_DIR, "IEEETestCases"),  # desenvolvimento
]
if _CONGELADO:
    _CANDIDATOS_DIR_FEEDERS.append(
        os.path.join(os.path.dirname(os.path.abspath(_sys.executable)), "IEEE")
    )  # distribuição congelada (IEEE/ ao lado do .exe)
DIR_FEEDERS = _CANDIDATOS_DIR_FEEDERS[0]
for _candidato in _CANDIDATOS_DIR_FEEDERS:
    if os.path.isdir(_candidato):
        DIR_FEEDERS = _candidato
        break


# ============================================================
# Definição dos sistemas de teste IEEE (originais + versões
# corrigidas, elaboradas neste trabalho para fins de verificação da
# causa raiz das divergências identificadas - ver notas de
# transparência metodológica no topo deste arquivo).
# ============================================================

SISTEMAS_DISPONIVEIS = {
    "IEEE 13 Node Test Feeder": {
        "pasta": "13Bus",
        "master": "IEEE13Nodeckt.dss",
        "referencia_csv": "ieee13_referencia.csv",
        "tipo_tensao_referencia": "LN",
        "comandos_pre_solve": [],
        "comandos_taps_fixos": [
            "Transformer.Reg1.Taps=[1.0 1.0625]",
            "Transformer.Reg2.Taps=[1.0 1.0500]",
            "Transformer.Reg3.Taps=[1.0 1.06875]",
        ],
        "desligar_controle_global": True,
        "excecoes_documentadas": {},
        "nota_sistema": None,
    },
    "IEEE 34 Node Test Feeder": {
        "pasta": "34Bus",
        "master": "ieee34Mod1.dss",
        "referencia_csv": "ieee34_referencia.csv",
        "tipo_tensao_referencia": "LN",
        "comandos_pre_solve": [
            "New Energymeter.M1 Line.L1 1",
            "Buscoords IEEE34_BusXY.csv",
        ],
        "comandos_taps_fixos": [
            "Transformer.reg1a.wdg=2 Tap=(0.00625 12 * 1 +)",
            "Transformer.reg1b.wdg=2 Tap=(0.00625 5 * 1 +)",
            "Transformer.reg1c.wdg=2 Tap=(0.00625 5 * 1 +)",
            "Transformer.reg2a.wdg=2 Tap=(0.00625 13 * 1 +)",
            "Transformer.reg2b.wdg=2 Tap=(0.00625 11 * 1 +)",
            "Transformer.reg2c.wdg=2 Tap=(0.00625 12 * 1 +)",
        ],
        "desligar_controle_global": True,
        "excecoes_documentadas": {},
        "nota_sistema": None,
    },
    "IEEE 37 Node Test Feeder": {
        "pasta": "37Bus",
        "master": "ieee37.dss",
        "referencia_csv": "ieee37_referencia.csv",
        "tipo_tensao_referencia": "LL",
        "comandos_pre_solve": [],
        "comandos_taps_fixos": [],
        "desligar_controle_global": False,
        "excecoes_documentadas": {},
        "nota_sistema": (
            "Erro sistemático identificado (~3,8-4,0% em A-B/C-A; ~0,3-0,4% "
            "em B-C; erro máximo medido: 7,68%). CAUSA RAIZ CONFIRMADA por "
            "comparação direta com 'Transformer Data.xls' oficial "
            "(feeder37.zip): o transformador de subestação mantém "
            "impedância NOMINAL real (R=2%, X=8%) no arquivo de terceiros "
            "'ieee37.dss', diferente dos demais sistemas de referência, que "
            "a enrijecem artificialmente para reproduzir a premissa de "
            "barra de fonte rígida assumida pelo documento de solução "
            "oficial. RESOLUÇÃO METODOLÓGICA: ver sistema 'IEEE 37 Node "
            "Test Feeder (corrigido)', que aplica a mesma técnica de "
            "enrijecimento mantendo o controle automático de tensão "
            "(os testes com taps travados foram realizados e documentados, "
            "resultando na decisão de manter o LDC ativo - ver nota da "
            "entrada corrigida para a narrativa completa), permitindo "
            "verificar, por resultado numérico direto, a correção da causa "
            "raiz diagnosticada. Mantido como REPROVADO nesta entrada original "
            "por rigor metodológico, por refletir o arquivo de terceiros "
            "efetivamente distribuído e amplamente reutilizado pela "
            "comunidade, operando com controle automático de tensão (sem "
            "taps fixados). ACHADO INVESTIGADO E DESCARTADO: os valores R/X "
            "do compensador do RegControl neste arquivo (assimétricos entre "
            "os dois ramos monofásicos) inicialmente pareciam divergir do "
            "nameplate oficial ('Regulator Data.xls': R=1,5/X=3,0 "
            "simétrico); confirmou-se, porém, que essa assimetria é "
            "esperada e correta para reguladores em conexão OPEN DELTA "
            "(este sistema é o único dos quatro com regulador open-delta), "
            "que exige transformação trigonométrica do nameplate para o "
            "referencial efetivo de simulação - não é um erro de "
            "modelagem."
        ),
    },
    "IEEE 37 Node Test Feeder (corrigido)": {
        "pasta": "37Bus",
        "master": "ieee37_corrigido.dss",
        "referencia_csv": "ieee37_referencia.csv",
        "tipo_tensao_referencia": "LL",
        "comandos_pre_solve": [],
        "comandos_taps_fixos": [
            "Transformer.reg1a.Wdg=2 Tap=1.04375",
            "Transformer.reg1c.Wdg=2 Tap=1.025",
        ],
        "desligar_controle_global": True,
        "excecoes_documentadas": {},
        "nota_sistema": (
            "Arquivo derivado (NÃO oficial), elaborado neste trabalho a "
            "partir de 'ieee37.dss', aplicando ao transformador de "
            "subestação a mesma técnica de enrijecimento de impedância já "
            "empregada pelos arquivos de terceiros dos sistemas de 13, 34 "
            "e 123 nós, de modo a reproduzir a premissa de barra de fonte "
            "rígida assumida pelo documento de solução oficial do IEEE "
            "para este sistema.\n\n"
            "HISTÓRICO DAS CORREÇÕES (todas MEDIDAS, exceto a v1):\n"
            "PRIMEIRA CORREÇÃO (só enrijecimento da impedância da fonte, "
            "via Xhl e %r divididos por 1000): erro máximo caiu de 7,68% "
            "para ~0,75%. Esse 0,75% foi inicialmente uma ESTIMATIVA "
            "comunicada verbalmente, depois CONFIRMADA por medição (a v3 "
            "mediu 0,7464%).\n"
            "SEGUNDA CORREÇÃO (taps oficiais 7/4 travados, extraídos da "
            "tabela 'VOLTAGE REGULATOR DATA' do documento oficial e "
            "confirmados pela tabela 'VOLTAGE PROFILE' do nó RG7): erro "
            "máximo MEDIDO de 1,38% - PIOR que a primeira.\n"
            "TERCEIRA CORREÇÃO (controle automático de tensão/LDC ativo): "
            "erro máximo MEDIDO de 0,7464% - ainda REPROVADO frente à "
            "tolerância de 0,5%.\n\n"
            "DIAGNÓSTICO FINAL - CONFIRMADO POR EXPERIMENTO CONTROLADO: a "
            "causa raiz do resíduo remanescente NÃO era o tap nem o "
            "mecanismo de controle, mas uma PARTICULARIDADE DO MOTOR "
            "OpenDSS: em transformadores de DOIS enrolamentos, a "
            "resistência série efetiva do modelo é alimentada pelo "
            "parâmetro %LoadLoss (DEFAULT 1,5556%), e NÃO pelos %r dos "
            "enrolamentos. Assim, o enrijecimento das correções anteriores "
            "era ILUSÓRIO quanto à resistência: o transformador de "
            "subestação (SubXF) continuava com R série = 1,5556% (default "
            "não tocado). Adicionalmente, os reguladores reg1a/reg1c "
            "declaravam apenas XHL=1, SEM %LoadLoss - herdando o MESMO "
            "default de 1,5556%. Em contraste, os sistemas que APROVAM "
            "declaram impedância quase nula de forma explícita (123-bus: "
            "'XHL=.001 %LoadLoss=0.00001 ppm=0.0', com o comentário "
            "'KERSTING ASSUMES NO IMPEDANCE IN THE REGULATOR'; 13-bus: "
            "'XHL=0.01 %LoadLoss=0.01'), reproduzindo a premissa do "
            "gabarito oficial: fonte rígida e regulador SEM impedância.\n\n"
            "QUARTA CORREÇÃO (CONFIGURAÇÃO ATUAL DESTA ENTRADA): SubXF com "
            "%LoadLoss enrijecido por /1000 (e ppm/%noloadloss zerados); "
            "reguladores com XHL=.001 e %LoadLoss=0.00001 (mesma técnica do "
            "123-bus); taps oficiais 7/4 travados; controle global "
            "desligado (mesma convenção das entradas 13/34). RESULTADO "
            "MEDIDO (114 barras comparadas): erro máximo de 0,014655885984% "
            "(~0,0147%) - APROVADO, com folga ampla frente à tolerância de "
            "0,5% (na verdade, melhor que os demais sistemas). Piores barras "
            "no limite de 0,0147%: 729, 706, 738, 724 (fase 1-2) e 744 "
            "(fase 3-1).\n\n"
            "LIÇÃO METODOLÓGICA: um controle automático de tensão (LDC) bem "
            "ajustado MASCARA divergências estruturais de impedância, pois "
            "compensa-as ajustando o tap - por isso a v3 (LDC) reprovava de "
            "forma aparentemente estável e não isolava a causa. A "
            "resistência fantasma só se revelou ao zerar a impedância dos "
            "reguladores e enrijecer o %LoadLoss do SubXF."
        ),
    },
    "IEEE 123 Node Test Feeder": {
        "pasta": "123Bus",
        "master": "IEEE123Master.dss",
        "referencia_csv": "ieee123_referencia.csv",
        "tipo_tensao_referencia": "LN",
        "comandos_pre_solve": [
            "New EnergyMeter.Feeder Line.L115 1",
            "Buscoords Buscoords.dat",
        ],
        "comandos_taps_fixos": [
            "Transformer.reg1a.wdg=2 Tap=(0.00625 7 * 1 +)",
            "Transformer.reg2a.wdg=2 Tap=(0.00625 -1 * 1 +)",
            "Transformer.reg3a.wdg=2 Tap=(0.00625 0 * 1 +)",
            "Transformer.reg3c.wdg=2 Tap=(0.00625 -1 * 1 +)",
            "Transformer.reg4a.wdg=2 Tap=(0.00625 8 * 1 +)",
            "Transformer.reg4b.wdg=2 Tap=(0.00625 1 * 1 +)",
            "Transformer.reg4c.wdg=2 Tap=(0.00625 5 * 1 +)",
            "RegControl.creg1a.maxtapchange=0",
            "RegControl.creg2a.maxtapchange=0",
            "RegControl.creg3a.maxtapchange=0",
            "RegControl.creg4a.maxtapchange=0",
            "RegControl.creg3c.maxtapchange=0",
            "RegControl.creg4b.maxtapchange=0",
            "RegControl.creg4c.maxtapchange=0",
        ],
        "desligar_controle_global": False,
        # DECISÃO DE APRESENTAÇÃO (2026-10-13): esta entrada (arquivo
        # original de terceiros) apresenta o resultado BRUTO da
        # comparação, SEM tratamento de exceção documentada. O objetivo é
        # evidenciar a divergência real da barra 610 e contrastá-la com a
        # entrada "(corrigido)", onde o tratamento é aplicado. Portanto
        # 'excecoes_documentadas' é deliberadamente vazio aqui.
        "excecoes_documentadas": {},
        "nota_sistema": (
            "APRESENTAÇÃO SEM TRATAMENTO (decisão deliberada de "
            "transparência): esta entrada exibe o resultado BRUTO da "
            "comparação, sem exceção documentada. Por isso o erro máximo "
            "REAL medido é 1,5469% (REPROVADO), localizado EXCLUSIVAMENTE "
            "na barra 610, fase 2. Todas as demais barras/fases "
            "permanecem dentro do erro histórico de ~0,13%. O tratamento "
            "dessa divergência como exceção documentada é aplicado "
            "SOMENTE na entrada 'IEEE 123 Node Test Feeder (corrigido)' "
            "(ver nota daquela entrada), permitindo comparar o resultado "
            "bruto com o resultado tratado.\n\n"
            "CAUSA RAIZ DA BARRA 610: secundário Delta-Delta isolado do "
            "Transformer.XFM1, sem carga declarada e sem referência de "
            "terra - a tensão fase-neutro é fisicamente indeterminada "
            "nessa condição de contorno. Os parâmetros do transformador "
            "foram CONFIRMADOS como idênticos aos oficiais ('Transformer "
            "Data.xls'), ou seja, não há erro de transcrição. A MESMA "
            "divergência existe no arquivo corrigido: a física da barra "
            "610 é idêntica nos dois modelos, e a única diferença entre "
            "os arquivos são as chaves Sw9/Sw10/Sw11 (dead-ends sem "
            "carga). O erro máximo das demais barras (~0,1356%) é o "
            "número efetivamente comparado ao gabarito.\n\n"
            "ACHADO ADICIONAL: a planilha oficial 'Switch Data.xls' "
            "(feeder123.zip) documenta 5 chaves normalmente abertas, mas "
            "o arquivo de terceiros 'IEEE123Master.dss' implementa apenas "
            "2 delas; as barras 251, 350 e 451 estão ausentes. RESOLUÇÃO "
            "METODOLÓGICA: ver sistema 'IEEE 123 Node Test Feeder "
            "(corrigido)', que adiciona as chaves ausentes. Não se espera "
            "alteração do erro numérico nesta correção específica, pois "
            "os ramais adicionados são dead-ends sem carga."
        ),
    },
    "IEEE 123 Node Test Feeder (corrigido)": {
        "pasta": "123Bus",
        "master": "IEEE123Master_corrigido.dss",
        "referencia_csv": "ieee123_referencia.csv",
        "tipo_tensao_referencia": "LN",
        "comandos_pre_solve": [
            "New EnergyMeter.Feeder Line.L115 1",
            "Buscoords Buscoords.dat",
            # Coordenadas ilustrativas das 3 barras adicionadas (251, 350,
            # 451), emitidas APÓS o Compile completo. Não podem ser
            # emitidas inline no master: no dss-python 0.15.7 a lista de
            # barras não é materializada durante o script de compilação,
            # e um SetBusXY inline após "New Line" que cria a barra falha
            # com "Bus '251' not found". Afetam apenas o desenho da
            # topologia, não o resultado numérico.
            "SetBusXY Bus=251 X=-50  Y=-50",
            "SetBusXY Bus=451 X=-50  Y=-150",
            "SetBusXY Bus=350 X=-50  Y=-100",
        ],
        "comandos_taps_fixos": [
            "Transformer.reg1a.wdg=2 Tap=(0.00625 7 * 1 +)",
            "Transformer.reg2a.wdg=2 Tap=(0.00625 -1 * 1 +)",
            "Transformer.reg3a.wdg=2 Tap=(0.00625 0 * 1 +)",
            "Transformer.reg3c.wdg=2 Tap=(0.00625 -1 * 1 +)",
            "Transformer.reg4a.wdg=2 Tap=(0.00625 8 * 1 +)",
            "Transformer.reg4b.wdg=2 Tap=(0.00625 1 * 1 +)",
            "Transformer.reg4c.wdg=2 Tap=(0.00625 5 * 1 +)",
            "RegControl.creg1a.maxtapchange=0",
            "RegControl.creg2a.maxtapchange=0",
            "RegControl.creg3a.maxtapchange=0",
            "RegControl.creg4a.maxtapchange=0",
            "RegControl.creg3c.maxtapchange=0",
            "RegControl.creg4b.maxtapchange=0",
            "RegControl.creg4c.maxtapchange=0",
        ],
        "desligar_controle_global": False,
        "excecoes_documentadas": {
            "610": (
                "Secundário Delta-Delta isolado do Transformer.XFM1, sem "
                "carga declarada e sem referência de terra. Mesma natureza "
                "do sistema original - não é afetado pela adição das "
                "chaves normalmente abertas. Excluída do cálculo do erro "
                "máximo; demais 127 barras validam com erro inferior a "
                "0,05%.\n\n"
                "VERIFICAÇÃO NUMÉRICA ADICIONAL (2026-10-13): as tensões "
                "de LINHA simuladas na barra 610 divergem apenas "
                "0,0095-0,021% das tensões de linha implícitas no "
                "documento de solução oficial (computadas por diferença "
                "vetorial das tensões fase-neutro publicadas: "
                "0,9880∠-3,51 / 1,0256∠-122,00 / 1,0052∠117,76 pu), ou "
                "seja, ordem de grandeza inferior ao erro global da rede "
                "(0,1356%). A divergência de 1,5469% existe exclusivamente "
                "na comparação fase-neutro - grandeza fisicamente "
                "indeterminada em secundário delta-delta isolado, para a "
                "qual o gabarito declara zero corrente ('TO NODE 610: "
                ".00 .00 .00') e nenhuma carga ('Spot Loads.xls') e "
                "nenhum aterramento. Os valores fase-neutro publicados "
                "para a barra 610 são convenção interna do software "
                "oficial, não grandeza reprodutível por modelo "
                "eletromagnético.\n\n"
                "CARACTERIZAÇÃO DEFINITIVA (2026-10-13): as três fontes "
                "oficiais (planilha 'Spot Loads', planilha 'Line Data' e "
                "perfil de tensões do gabarito) confirmam a topologia desta "
                "barra: ela é o ponto de distribuição secundária (480 V) do "
                "transformador de distribuição XF1 (150 kVA, Delta-Delta, "
                "4,16 kV -> 0,48 kV) pendurado na barra 61 do alimentador de "
                "4,16 kV. No gabarito oficial o caminho é 61 -> <XF1> -> nó "
                "'XF1' (terminal secundário, 480 V) -> nó 610, com ZERO "
                "ampères e ZERO perdas explicitamente declarados pelo próprio "
                "gabarito ('TO NODE 610: .00 .00 .00 AMP/DG', 'LOSS = .000 "
                "kW'); no arquivo .dss de terceiros os nós 'XF1' e '610' "
                "foram unificados na barra 610 (lícito, pois a corrente entre "
                "eles é nula) e o nó '61s' é apenas o terminal primário atrás "
                "da chave Sw6. A barra 610 não conecta a mais NADA: sem carga "
                "(ausente em 'Spot Loads'), sem linha, sem capacitor, sem "
                "aterramento. Em um secundário Delta-Delta isolado (sem carga "
                "e sem caminho à terra), o potencial ABSOLUTO das fases é "
                "indeterminado pela teoria de circuitos - apenas as tensões de "
                "LINHA são determinadas, impostas pela razão de transformação "
                "a partir do primário; o potencial fase-neutro é um grau de "
                "liberdade da solução. O teste do vetor comum (diferenças "
                "complexas fase-neutro gabarito-menos-simulação, por fase) "
                "mostrou que tais diferenças NÃO constituem um vetor comum "
                "(variam de 0,03 a 0,81 pu): os dois softwares posicionam o "
                "'neutro virtual' desse nó isolado de formas estruturalmente "
                "distintas, sem relação rígida entre si (convenção do WindMil "
                "de um lado, regularização numérica do OpenDSS de outro). "
                "CONCLUSÃO: NÃO houve erro de dados nem de transcrição na "
                "documentação oficial do IEEE para o 123-bus. Houve uma "
                "OMISSÃO METODOLÓGICA: o documento de solução reporta tensões "
                "fase-neutro para uma barra cuja tensão fase-neutro é "
                "fisicamente indeterminada (nó isolado, com zero corrente "
                "declarada pelo próprio gabarito), sem registrar que tais "
                "valores derivam da convenção de referencial do software "
                "utilizado na solução oficial. Qualquer comparação "
                "fase-neutro entre softwares diferentes nesse nó compara "
                "convenções não documentadas, não grandezas físicas - daí a "
                "divergência de 1,5469% e o tratamento correto como exceção "
                "documentada, com a modelagem comprovada correta nas "
                "grandezas determináveis (as tensões de linha)."
            ),
        },
        "nota_sistema": (
            "Arquivo derivado (NÃO oficial), elaborado neste trabalho a "
            "partir de 'IEEE123Master.dss', adicionando as 3 chaves "
            "normalmente abertas ausentes (250-251, 450-451, 300-350), "
            "conforme 'Switch Data.xls' oficial. As chaves Sw9/Sw10/Sw11 "
            "são mantidas FECHADAS (sem comando 'Open'), técnica idêntica "
            "à já empregada pelo arquivo original em Sw7/Sw8: como as "
            "barras 251/350/451 não possuem NENHUMA outra conexão nem "
            "carga, uma chave fechada em ramal morto produz exatamente o "
            "mesmo efeito elétrico de uma chave aberta (nenhuma corrente "
            "flui sem caminho de retorno).\n\n"
            "TRATAMENTO DA BARRA 610 (aplicado EXCLUSIVAMENTE nesta "
            "entrada): o resultado exibido aqui é o TRATADO - a barra 610 "
            "(secundário Delta-Delta isolado do Transformer.XFM1, tensão "
            "fase-neutro fisicamente indeterminada) é excluída do erro "
            "máximo de aprovação, levando a APROVADO com 0,1356%. A "
            "entrada 'IEEE 123 Node Test Feeder' (original) exibe o "
            "resultado BRUTO da MESMA física (REPROVADO, 1,5469% na barra "
            "610), para contraste. A diferença entre os dois arquivos são "
            "apenas as chaves Sw9/Sw10/Sw11. PROVA NUMÉRICA (2026-10-13): "
            "as tensões de LINHA na barra 610 (grandeza fisicamente "
            "determinada pela razão de transformação) batem com as "
            "implícitas no gabarito com erro de 0,0095-0,021% - ordem de "
            "grandeza inferior ao erro global (0,1356%). A divergência "
            "fase-neutro de 1,5469% é convenção interna do software "
            "oficial para um nó de neutro fisicamente indeterminado, não "
            "erro de modelagem (ver justificativa completa em "
            "excecoes_documentadas['610']).\n\n"
            "BUG ENCONTRADO E CORRIGIDO (registrado por transparência): "
            "a compilação falhava com 'Bus \"251\" not found'. A primeira "
            "hipótese - de que o culpado fossem comandos explícitos 'Open "
            "Line.SwX term=1' - foi TESTADA E REFUTADA empiricamente: com "
            "as chaves já fechadas, o erro PERSISTIU. A causa raiz real, "
            "confirmada por teste controlado, é que no motor dss-python "
            "0.15.7 (DSS-Extensions) a lista de barras do circuito não é "
            "materializada DURANTE o script de compilação: um comando "
            "'SetBusXY' inline imediatamente após um 'New Line' que cria "
            "a barra (251/350/451) não a encontra. Esse comportamento não "
            "é observado no motor COM oficial da EPRI. CORREÇÃO: as "
            "coordenadas ilustrativas dessas 3 barras foram movidas do "
            "master para os comandos_pre_solve deste validador, emitidas "
            "APÓS o Compile completo - onde os mesmos SetBusXY executam "
            "normalmente (barra reconhecida, NumBuses=135). As "
            "coordenadas afetam apenas o desenho da topologia, não o "
            "resultado numérico. Resultado esperado: erro numérico "
            "IDÊNTICO ao do sistema original, confirmando que a omissão "
            "identificada não comprometia a validação numérica, apenas a "
            "fidelidade topológica do modelo."
        ),
    },
}


# ============================================================
# Leitura da referência oficial (CSV transcrito manualmente)
# ============================================================

def carregar_referencia(nome_sistema: str):
    """Lê o CSV de referência oficial. Retorna None se o arquivo ainda
    não existir (sistema pendente de transcrição do .doc original)."""
    info = SISTEMAS_DISPONIVEIS[nome_sistema]
    caminho = os.path.join(DIR_REFERENCIAS, info["referencia_csv"])

    if not os.path.exists(caminho):
        return None

    referencia = {}
    with open(caminho, newline="", encoding="utf-8") as arquivo:
        leitor = csv.DictReader(arquivo)
        for linha in leitor:
            chave = (linha["barra"].strip().upper(), linha["fase"].strip())
            referencia[chave] = {
                "tensao_pu": float(linha["tensao_pu"]),
                "angulo_graus": float(linha.get("angulo_graus", 0) or 0),
            }
    return referencia


# ============================================================
# Comparação
# ============================================================

def comparar_resultados(resultado_simulado: dict, referencia: dict,
                          excecoes_documentadas: dict = None):
    """Calcula o erro percentual de tensão, barra a barra e fase a
    fase, retornando o detalhamento completo e o erro máximo
    encontrado.

    Barras listadas em 'excecoes_documentadas' (dict {barra: texto de
    justificativa}) aparecem no detalhamento com seu valor e erro reais,
    mas NÃO são contabilizadas no erro máximo usado para a decisão de
    aprovação/reprovação - apenas para situações com causa raiz
    tecnicamente identificada e documentada (ver notas em
    SISTEMAS_DISPONIVEIS), nunca para "esconder" divergências não
    investigadas."""

    excecoes_documentadas = excecoes_documentadas or {}

    detalhamento = []
    erros_validos = []
    erros_excecao = []

    for chave, dados_ref in referencia.items():
        barra, fase = chave
        tensao_ref = dados_ref["tensao_pu"]
        tensao_sim = resultado_simulado.get(chave)
        em_excecao = barra in excecoes_documentadas

        if tensao_sim is None:
            detalhamento.append({
                "barra": barra, "fase": fase,
                "tensao_referencia": tensao_ref, "tensao_simulada": None,
                "erro_pct": None, "excecao": em_excecao,
                "observacao": (
                    excecoes_documentadas.get(barra, "")
                    if em_excecao else
                    "Barra/fase não encontrada no resultado simulado."
                ),
            })
            continue

        erro_pct = abs(tensao_sim - tensao_ref) / tensao_ref * 100

        if em_excecao:
            erros_excecao.append(erro_pct)
            observacao = f"[EXCEÇÃO DOCUMENTADA] {excecoes_documentadas[barra]}"
        else:
            erros_validos.append(erro_pct)
            observacao = ""

        detalhamento.append({
            "barra": barra, "fase": fase,
            "tensao_referencia": tensao_ref, "tensao_simulada": round(tensao_sim, 5),
            "erro_pct": round(erro_pct, 4), "excecao": em_excecao,
            "observacao": observacao,
        })

    erro_maximo = max(erros_validos) if erros_validos else None
    erro_maximo_com_excecoes = (
        max(erros_validos + erros_excecao) if (erros_validos or erros_excecao) else None
    )

    return detalhamento, erro_maximo, erro_maximo_com_excecoes


# ============================================================
# Execução de um sistema
# ============================================================

def validar_sistema(nome_sistema: str, tolerancia_percentual: float = 0.5):
    """Executa a validação de UM sistema. Retorna um dicionário com o
    status, o erro máximo, o detalhamento por barra/fase, observações
    de transparência (ex.: referência ainda não disponível, exceções
    documentadas, notas de sistema) e a instância DSS já resolvida
    (chave 'objeto_dss'), reaproveitável para o desenho de topologia."""

    info = SISTEMAS_DISPONIVEIS[nome_sistema]
    caminho_master = os.path.join(DIR_FEEDERS, info["pasta"], info["master"])

    if not os.path.exists(caminho_master):
        return {
            "status": "ERRO",
            "mensagem": f"Arquivo não encontrado: {caminho_master}",
            "objeto_dss": None,
        }

    referencia = carregar_referencia(nome_sistema)
    if referencia is None:
        return {
            "status": "PENDENTE",
            "mensagem": (
                "Referência oficial ainda não transcrita para este sistema "
                f"(esperado em: validacao_ieee/referencias/{info['referencia_csv']}). "
                "A simulação pode ser executada, mas não há valores oficiais "
                "do IEEE para comparação neste momento."
            ),
            "objeto_dss": None,
        }

    try:
        objeto_dss = DSS(caminho_master)
        objeto_dss.resolver_validacao_oficial(
            caminho_master=caminho_master,
            comandos_pre_solve=info["comandos_pre_solve"],
            comandos_taps_fixos=info["comandos_taps_fixos"],
            desligar_controle_global=info["desligar_controle_global"],
        )

        if info["tipo_tensao_referencia"] == "LL":
            resultado_simulado = objeto_dss.obter_tensoes_LL_por_barra()
        else:
            resultado_simulado = objeto_dss.obter_tensoes_por_barra()

    except Exception as e:
        return {
            "status": "ERRO",
            "mensagem": f"Falha durante a simulação: {e}",
            "objeto_dss": None,
        }

    excecoes = info.get("excecoes_documentadas", {})
    detalhamento, erro_maximo, erro_maximo_com_excecoes = comparar_resultados(
        resultado_simulado, referencia, excecoes_documentadas=excecoes)

    if erro_maximo is None:
        status = "ERRO"
        mensagem = "Nenhuma barra/fase da referência (fora das exceções) foi encontrada no resultado simulado."
    elif erro_maximo <= tolerancia_percentual:
        status = "APROVADO"
        mensagem = f"Erro máximo de tensão: {erro_maximo:.4f} % (tolerância: {tolerancia_percentual} %)"
        if excecoes:
            mensagem += (
                f" | {len(excecoes)} barra(s) tratada(s) como exceção "
                f"documentada (erro máx. incluindo exceções: "
                f"{erro_maximo_com_excecoes:.4f} %)"
            )
    else:
        status = "REPROVADO"
        mensagem = f"Erro máximo de tensão: {erro_maximo:.4f} % EXCEDE a tolerância de {tolerancia_percentual} %"

    if info.get("nota_sistema"):
        mensagem += f" | NOTA: {info['nota_sistema']}"

    return {
        "status": status,
        "mensagem": mensagem,
        "erro_maximo_pct": erro_maximo,
        "erro_maximo_com_excecoes_pct": erro_maximo_com_excecoes,
        "detalhamento": detalhamento,
        "tipo_tensao_referencia": info["tipo_tensao_referencia"],
        "excecoes_documentadas": excecoes,
        "nota_sistema": info.get("nota_sistema"),
        "objeto_dss": objeto_dss,
    }


def executar_validacao(sistemas_selecionados, tolerancia_percentual: float = 0.5):
    """Executa a validação para todos os sistemas selecionados.
    Retorna {nome_sistema: resultado}."""
    os.makedirs(DIR_SAIDA, exist_ok=True)
    return {
        nome: validar_sistema(nome, tolerancia_percentual)
        for nome in sistemas_selecionados
    }


# ============================================================
# Memorial de cálculo (mesmo padrão de transparência/auditoria já
# usado em memorial_calculo_afundamento.py e memorial_calculo_economia.py)
# ============================================================

def gerar_memorial_validacao(resultados: dict) -> str:
    linhas = []
    linhas.append("#" * 90)
    linhas.append("MEMORIAL DE CÁLCULO — Validação do Modelo Computacional (Sistemas IEEE)")
    linhas.append("#" * 90)
    linhas.append("")
    linhas.append(
        "Referência: Kersting (1991); Schneider et al. (2018). IEEE PES "
        "Distribution System Analysis Subcommittee - Distribution Test Feeders.")
    linhas.append("")
    linhas.append(
        "NOTA METODOLÓGICA GERAL: os documentos .doc e as planilhas .xls "
        "distribuídos pelo IEEE constituem a referência oficial (gabarito). "
        "Os arquivos .dss utilizados como instrumento de simulação são "
        "implementações de terceiros (github.com/tshort/OpenDSS), passíveis "
        "de divergências/omissões de modelagem. Sistemas identificados com "
        "o sufixo '(corrigido)' são arquivos derivados, elaborados neste "
        "trabalho, que corrigem especificamente a divergência confirmada do "
        "sistema original correspondente - permitindo verificar, por "
        "resultado numérico direto, a consistência do motor de simulação e "
        "do processo de validação desenvolvidos.")
    linhas.append("")

    for nome_sistema, resultado in resultados.items():
        linhas.append("=" * 90)
        linhas.append(f"SISTEMA: {nome_sistema}")
        linhas.append("=" * 90)
        linhas.append(f"Status: {resultado['status']}")
        linhas.append(f"Observação: {resultado['mensagem']}")

        if resultado.get("nota_sistema"):
            linhas.append("")
            linhas.append(f"NOTA DE SISTEMA: {resultado['nota_sistema']}")

        if resultado.get("excecoes_documentadas"):
            linhas.append("")
            linhas.append("EXCEÇÕES DOCUMENTADAS (não contabilizadas no erro máximo oficial):")
            for barra, justificativa in resultado["excecoes_documentadas"].items():
                linhas.append(f"  - Barra {barra}: {justificativa}")

        linhas.append("")

        detalhamento = resultado.get("detalhamento")
        if detalhamento:
            tipo_tensao = resultado.get("tipo_tensao_referencia", "LN")
            linhas.append(
                f"{'Barra':<12}{'Fase':<8}{'V_ref (pu)':>14}{'V_sim (pu)':>14}{'Erro (%)':>12}   Observação")
            linhas.append("-" * 90)
            for item in detalhamento:
                v_sim_texto = f"{item['tensao_simulada']:.5f}" if item["tensao_simulada"] is not None else "--"
                erro_texto = f"{item['erro_pct']:.4f}" if item["erro_pct"] is not None else "--"
                marcador = " *" if item.get("excecao") else ""
                linhas.append(
                    f"{item['barra']:<12}{item['fase']:<8}{item['tensao_referencia']:>14.5f}"
                    f"{v_sim_texto:>14}{erro_texto:>12}{marcador}   {item['observacao']}")
            linhas.append(f"(Tipo de tensão de referência utilizada: {tipo_tensao})")
            if resultado.get("excecoes_documentadas"):
                linhas.append("(* = barra tratada como exceção documentada, ver acima)")
            linhas.append("")

    return "\n".join(linhas)


def salvar_memorial_validacao(texto: str, caminho_arquivo: str):
    with open(caminho_arquivo, "w", encoding="utf-8") as f:
        f.write(texto)