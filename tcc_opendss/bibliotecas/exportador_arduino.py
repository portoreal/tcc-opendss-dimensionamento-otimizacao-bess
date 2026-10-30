__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Exportador de parametrização para o Arduino Mega (microrrede).

Papel desta frente no TCC
-------------------------
O Arduino Mega representa/controla/adquire os sinais do SISTEMA DE ENERGIA
ADJACENTE ao sistema BESS — a microrrede: cargas com curvas horárias, geração
fotovoltaica, impedâncias dos ramos e bancos de capacitores. Ele NÃO decide
despacho: recebe o setpoint de P/Q do ESP32 e devolve as tensões resultantes.

O sketch embarcado (`hardware/arduino_microrrede/arduino_microrrede.ino`) é
PRÉ-PRONTO: a lógica é fixa e versionada. O que este módulo gera, a cada
projeto, é apenas o cabeçalho ``param_microrrede.h`` com os dados da rede
desenhada no Editor.

TRANSPARÊNCIA TÉCNICA — o que este gerador NÃO faz
--------------------------------------------------
- Não inventa dados. Elemento sem o campo necessário vira AVISO no retorno e
  valor neutro no cabeçalho (0.0), nunca um chute.
- Não resolve fluxo de potência. A aproximação usada está declarada no
  cabeçalho C gerado e no topo do sketch.
- A conversão para pu usa BASE_KVA = 1000 kVA (base de potência arbitrária
  mas fixa) e as tensões em pu relativas à tensão nominal de cada barra. A
  impedância em pu é calculada sobre a base de potência e a tensão da barra
  de origem do ramo — é o que a varredura do sketch consome.
"""

import os
from typing import Any, Dict, List, Optional, Tuple

from .curvas import obter_curva
from .modelo_rede import RedeEletrica

# Base de potência única para toda a conversão em pu. Fixa por desenho: a
# varredura do sketch soma potências de barras diferentes, o que exige uma
# base comum. 1000 kVA = 1 MVA é a convenção usada no cabeçalho gerado.
BASE_KVA = 1000.0

# Pinos PWM do Arduino Mega disponíveis para o mapa de barras.
#
# ATENÇÃO — COLISÃO COM O ENLACE: o Mega tem PWM nos pinos 2..13, mas o
# enlace com o ESP32 usa D2..D10 (hora, tick, V_pu, estado). Usar 2..13
# cru colocaria uma saída PWM de barra no MESMO pino do tick de hora (D7),
# do V_pu (D8) ou da entrada de estado (D9/D10) — a placa ficaria
# silenciosamente errada. A lista abaixo usa os pinos com PWM que NÃO
# participam do enlace: 11, 12 e 13.
#
# São só 3 barras. Projetos maiores precisam que o pesquisador escolha:
#   (a) remover a PWM das barras excedentes (PINO_PWM_BARRA = -1, o sketch
#       não aciona nada), ou
#   (b) mover o enlace para outros pinos do mapa canônico, ou
#   (c) usar um expansor de PWM.
# O gerador emite AVISO para toda barra que ficar sem canal analógico.
PINOS_PWM_MEGA = [11, 12, 13]

# Pinos do Mega ocupados pelo enlace com o ESP32. Derivado do mapa canônico
# (PINO_NUMERICO_MEGA) para não haver uma segunda lista a manter em sincronia.
def pinos_ocupados_pelo_enlace():
    """Números de pino do Mega já usados pela interface com o ESP32."""
    return {p for p in PINO_NUMERICO_MEGA.values() if p is not None}

NOME_ARQUIVO = "param_microrrede.h"

# ---------------------------------------------------------------------------
# MAPA CANÔNICO DA INTERFACE FÍSICA Mega <-> ESP32 (decisão do pesquisador)
# ---------------------------------------------------------------------------
# A ligação entre as duas placas NÃO usa UART. São conexões diretas digitais
# e analógicas, ponto a ponto — algo que se monta em bancada com jumpers.
# Cada placa tem alimentação INDIVIDUAL; apenas o GND é comum (referência de
# sinal, obrigatória para o ADC e o DAC funcionarem).
#
# ESTA LISTA É A FONTE ÚNICA DA VERDADE: o exportador do ESP32 importa daqui
# em vez de repetir os pinos. Um só caminho, dois cabeçalhos gerados —
# impossível divergirem entre si.
#
# Sentido do dado: Mega -> ESP32 nas ligações 1..7 (o Mega publica o estado
# da microrrede); ESP32 -> Mega nas 8..11 (o ESP32 atua); a 12 é a
# referência elétrica comum, sem dado.
#
# CONDIÇÃO DE NÍVEL (decisão do pesquisador: Arduino Mega 2560 R3)
# -----------------------------------------------------------------
# O Mega 2560 R3 é lógica de 5 V; o ESP32 é de 3,3 V e NÃO tolera 5 V nas
# entradas. Toda linha Mega -> ESP32 passa por DIVISOR DE TENSÃO
# R_SERIE 10 kOhm + R_GND 20 kOhm (no lado do ESP32): 5 x 20/30 = 3,33 V.
# A linha analógica (D8) soma um filtro RC 4,7 kOhm + 10 uF ANTES do divisor.
# Nas linhas ESP32 -> Mega (3,3 V dentro de uma entrada de 5 V) a ligação é
# DIRETA: 3,3 V > VIH do ATmega2560 (0,6 x 5 V = 3,0 V), margem de 0,3 V.
# O campo "condicionamento" de cada ligação abaixo é emitido nos dois
# cabeçalhos e conferido pelo README de bancada.
MAPA_LIGACOES = [
 {"n": 1, "mega": "D2", "mega_papel": "saída digital",
 "esp32": "GPIO 23", "esp32_papel": "entrada",
 "dados": "hora do dia simulada, bit 0 (LSB)",
 "sentido": "Mega -> ESP32", "dado": "digital",
 "macro_mega": "PINO_HORA_BIT0", "macro_esp32": "PINO_HORA_IN0"},
 {"n": 2, "mega": "D3", "mega_papel": "saída digital",
 "esp32": "GPIO 22", "esp32_papel": "entrada",
 "dados": "hora do dia simulada, bit 1",
 "sentido": "Mega -> ESP32", "dado": "digital",
 "macro_mega": "PINO_HORA_BIT1", "macro_esp32": "PINO_HORA_IN1"},
 {"n": 3, "mega": "D4", "mega_papel": "saída digital",
 "esp32": "GPIO 21", "esp32_papel": "entrada",
 "dados": "hora do dia simulada, bit 2",
 "sentido": "Mega -> ESP32", "dado": "digital",
 "macro_mega": "PINO_HORA_BIT2", "macro_esp32": "PINO_HORA_IN2"},
 {"n": 4, "mega": "D5", "mega_papel": "saída digital",
 "esp32": "GPIO 19", "esp32_papel": "entrada",
 "dados": "hora do dia simulada, bit 3",
 "sentido": "Mega -> ESP32", "dado": "digital",
 "macro_mega": "PINO_HORA_BIT3", "macro_esp32": "PINO_HORA_IN3"},
 {"n": 5, "mega": "D6", "mega_papel": "saída digital",
 "esp32": "GPIO 18", "esp32_papel": "entrada",
 "dados": "hora do dia simulada, bit 4 (MSB)",
 "sentido": "Mega -> ESP32", "dado": "digital",
 "macro_mega": "PINO_HORA_BIT4", "macro_esp32": "PINO_HORA_IN4"},
 {"n": 6, "mega": "D7", "mega_papel": "saída digital",
 "esp32": "GPIO 5", "esp32_papel": "entrada",
 "dados": "tick de hora (borda de subida = nova hora simulada)",
 "sentido": "Mega -> ESP32", "dado": "digital",
 "macro_mega": "PINO_TICK_HORA", "macro_esp32": "PINO_TICK_IN"},
 {"n": 7, "mega": "D8", "mega_papel": "PWM + filtro RC",
 "esp32": "GPIO 36 (ADC1/VP)", "esp32_papel": "entrada analógica",
 "dados": "V_pu da barra do BESS: V = V_pu/VPU_ANALOG_MAX x 3,3 V",
 "sentido": "Mega -> ESP32", "dado": "analógica",
 "macro_mega": "PINO_VPU_SAIDA", "macro_esp32": "PINO_VPU_ADC"},
 {"n": 8, "mega": "A0", "mega_papel": "ADC (referência 5 V)",
 "esp32": "GPIO 25 (DAC1)", "esp32_papel": "saída analógica",
 "dados": "setpoint de P: V = 1,65 V + P/KW_RATING x 1,65 V",
 "sentido": "ESP32 -> Mega", "dado": "analógica",
 "macro_mega": "PINO_P_ADC", "macro_esp32": "PINO_P_DAC"},
 {"n": 9, "mega": "A1", "mega_papel": "ADC (referência 5 V)",
 "esp32": "GPIO 26 (DAC2)", "esp32_papel": "saída analógica",
 "dados": "setpoint de Q (mesma escala do P, limitado por Q_LIM_KVAR)",
 "sentido": "ESP32 -> Mega", "dado": "analógica",
 "macro_mega": "PINO_Q_ADC", "macro_esp32": "PINO_Q_DAC"},
 {"n": 10, "mega": "D9", "mega_papel": "entrada digital",
 "esp32": "GPIO 27", "esp32_papel": "saída digital",
 "dados": "estado do BESS, bit 0 (00 repouso | 01 carrega | 10 descarrega)",
 "sentido": "ESP32 -> Mega", "dado": "digital",
 "macro_mega": "PINO_ESTADO0", "macro_esp32": "PINO_ESTADO0"},
 {"n": 11, "mega": "D10", "mega_papel": "entrada digital",
 "esp32": "GPIO 14", "esp32_papel": "saída digital",
 "dados": "estado do BESS, bit 1 (11 reservado)",
 "sentido": "ESP32 -> Mega", "dado": "digital",
 "macro_mega": "PINO_ESTADO1", "macro_esp32": "PINO_ESTADO1"},
 {"n": 12, "mega": "GND", "mega_papel": "referência",
 "esp32": "GND", "esp32_papel": "referência",
 "dados": "referência de sinal comum (alimentações SEPARADAS)",
 "sentido": "-", "dado": "referência",
 "macro_mega": None, "macro_esp32": None},
]

# Número do pino físico no Mega para cada ligação (D2 -> 2, A0 -> 54, GND ->
# None). O rótulo "D2"/"A0" é a serigrafia da placa; o número é o que o
# Arduino usa em pinMode()/analogRead(). No Mega os analógicos A0..A15 são os
# pinos digitais 54..69 — por isso A0 = 54, e não 0.
PINO_NUMERICO_MEGA = {
 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8,
 8: 54, 9: 55, 10: 9, 11: 10, 12: None,
}

# Escalas da interface analógica. São ESCOLHAS DE PROJETO declaradas, não
# dados medidos. O ADC do Mega lê 0..5 V e o DAC do ESP32 entrega 0..3,3 V:
# o sinal do ESP32 usa no máximo ~66% da faixa do ADC — resolução efetiva
# menor, documentada no cabeçalho gerado e no README.
VPU_ANALOG_MAX_PADRAO = 1.20 # tensão pu correspondente a 3,3 V na linha
DAC_MIDRAIL_V_PADRAO = 1.65 # 1,65 V = zero de P/Q (metade do fundo de escala)
VREF_MEGA_ADC_PADRAO = 5.0 # referência do ADC do Mega
VREF_ESP32_DAC_PADRAO = 3.3 # fundo de escala do DAC do ESP32
FILTRO_RC_SUGERIDO = "4,7 kOhm em serie + 10 uF para GND"

# ---------------------------------------------------------------------------
# Condicionamento de nível Mega 2560 R3 (5 V) -> ESP32 (3,3 V)
# ---------------------------------------------------------------------------
# Escolhas de projeto declaradas, não medidas. O divisor 10k/20k é usado em
# TODAS as linhas Mega -> ESP32 (6 digitais + a analógica), para um BOM
# uniforme: 5 x 20/(10+20) = 3,333 V, abaixo dos 3,6 V de entrada do ESP32 e
# acima do VIH do ESP32 (0,75 x 3,3 = 2,475 V). A linha analógica soma o
# filtro RC de 4,7 kOhm/10 uF ANTES do divisor — o RC precisa ver a fonte
# do PWM a 5 V, não o nó já dividido.
R_SERIE_DIV_OHMS = 10000.0 # resistor em série com a linha do Mega
R_GND_DIV_OHMS = 20000.0 # resistor de fuga para GND, no lado do ESP32
MEGA_VCC_PWM_V_PADRAO = 5.0 # fundo de escala do PWM do Mega (lógica 5 V)
VIH_MEGA_V_PADRAO = 3.0 # 0,6 x VCC = limiar de nível alto do ATmega2560

#: Razão do divisor: V_esp = V_mega x DIVISOR_LEVEL.
DIVISOR_LEVEL_PADRAO = round(
    R_GND_DIV_OHMS / (R_SERIE_DIV_OHMS + R_GND_DIV_OHMS), 4)

#: Texto de condicionamento por ligação, indexado pelo número da ligação.
#: Emitido como comentário nos dois cabeçalhos (fonte única).
CONDICIONAMENTO = {
    1: "divisor 10k/20k -> 3,33 V",
    2: "divisor 10k/20k -> 3,33 V",
    3: "divisor 10k/20k -> 3,33 V",
    4: "divisor 10k/20k -> 3,33 V",
    5: "divisor 10k/20k -> 3,33 V",
    6: "divisor 10k/20k -> 3,33 V",
    7: "filtro RC 4,7k/10uF + divisor 10k/20k -> 3,33 V",
    8: "direta (3,3 V no ADC do Mega; ~66% da faixa)",
    9: "direta (3,3 V no ADC do Mega; ~66% da faixa)",
    10: "direta (3,3 V > VIH 3,0 V do Mega)",
    11: "direta (3,3 V > VIH 3,0 V do Mega)",
    12: "referência de sinal comum (alimentações separadas)",
}

# Defaults de operação do ensaio (ajustáveis editando o cabeçalho gerado).
SEGUNDOS_POR_HORA_PADRAO = 1.0
DIA_INICIAL_PADRAO = 0 # 0 = Segunda, consistente com a Simulação ao Vivo
PU_PWM_MAX_PADRAO = 1.20
V_FONTE_PU_PADRAO = 1.0
NUVEM_FATOR_PADRAO = 1.0 # 1.0 = céu limpo (sem atenuação da PV)


# ---------------------------------------------------------------------------
# Utilidades de conversão
# ---------------------------------------------------------------------------
def _num(valor: Any, default: Optional[float] = None) -> Optional[float]:
    """Converte para float tolerando string vazia/inválida. Nunca levanta."""
    if valor is None:
        return default
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace(",", ".")
    if not texto:
        return default
    try:
        return float(texto)
    except ValueError:
        return default


def _curva_24h(pasta_curvas: Optional[str], nome: str,
               avisos: List[str], contexto: str) -> List[float]:
    """Resolve a curva diária e a expande para 24 multiplicadores horários.

    Os pontos do editor têm horas irregulares (ex.: 0, 6.5, 18, 22). O sketch
    precisa de uma tabela de 24 posições indexada pela hora inteira e, por
    isso, o gerador INTERPOLA LINEARMENTE entre pontos vizinhos, com
    repetição do primeiro/último valor fora da faixa coberta.

    TRANSPARÊNCIA TÉCNICA: essa interpolação é uma decisão de implementação
    desta camada, não do modelo. O OpenDSS interpola internamente do mesmo
    modo (linear entre pontos de `hour`), então a tabela é fiel ao que o
    motor calcula para as horas inteiras.
    """
    if not nome or str(nome) == "Nenhuma":
        avisos.append(f"{contexto}: sem curva diária associada; multiplicador "
                      f"constante 1.0 em todas as horas.")
        return [1.0] * 24

    if not pasta_curvas:
        avisos.append(f"{contexto}: curva '{nome}' referenciada, mas o "
                      f"projeto não tem pasta de curvas; multiplicador 1.0.")
        return [1.0] * 24

    curva = obter_curva(pasta_curvas, str(nome))
    if curva is None:
        avisos.append(f"{contexto}: curva '{nome}' não encontrada no "
                      f"repositório; multiplicador 1.0.")
        return [1.0] * 24

    pontos = curva.pontos_ordenados()
    if len(pontos) < 2:
        avisos.append(f"{contexto}: curva '{nome}' com menos de 2 pontos; "
                      f"multiplicador 1.0.")
        return [1.0] * 24

    horas = [p[0] for p in pontos]
    mults = [p[1] / 100.0 for p in pontos]

    tabela: List[float] = []
    for h in range(24):
        if h <= horas[0]:
            tabela.append(mults[0])
            continue
        if h >= horas[-1]:
            tabela.append(mults[-1])
            continue
        for i in range(len(horas) - 1):
            if horas[i] <= h <= horas[i + 1]:
                x0, x1 = horas[i], horas[i + 1]
                y0, y1 = mults[i], mults[i + 1]
                if x1 == x0:
                    tabela.append(y0)
                else:
                    f = (h - x0) / (x1 - x0)
                    tabela.append(y0 + f * (y1 - y0))
                break
    return tabela


def _impedancia_pu(ramo, base_kva: float, avisos: List[str]
                   ) -> Tuple[float, float]:
    """Devolve (R_pu, X_pu) do ramo na base do projeto.

    Convenções confirmadas no exportador .dss (`_fmt_line`):
      - Line  -> r1/x1 em ohm por unidade de comprimento, `length` e `units`.
      - Switch -> impedância desprezível (1e-4 ohm) por construção.
      - Transformer -> `xhl` em % sobre a base do próprio trafo (kva).

    TRANSPARÊNCIA TÉCNICA: para linha, R e X são multiplicados pelo
    comprimento (`length`, em `units`). A conversão para pu usa a tensão da
    barra de origem do ramo e BASE_KVA. Ramo sem impedância declarada recebe
    0.0 e a omissão é registrada em `avisos` — nunca um valor inventado.
    """
    p = ramo.parametros or {}
    tipo = ramo.tipo

    if tipo == "Switch":
        return 1e-4 / 1000.0, 1e-4 / 1000.0   # praticamente nulo, como no .dss

    r = _num(p.get("r1"))
    x = _num(p.get("x1"))

    if tipo == "Transformer":
        # xhl em % sobre a base do trafo; aproximado como reatância pura.     #
        xhl = _num(p.get("xhl"), 0.0) or 0.0
        kva = _num(p.get("kva"), base_kva) or base_kva
        if kva <= 0:
            kva = base_kva
        x_pu = (xhl / 100.0) * (base_kva / kva)
        avisos.append(
            f"Ramo '{ramo.nome}' (Transformer): modelado como reatância pura "
            f"a partir de xhl={xhl}% na base {kva:.0f} kVA; relação de tap "
            f"não é representada pela varredura radial.")
        return 0.0, x_pu

    if r is None or x is None:
        avisos.append(
            f"Ramo '{ramo.nome}' ({tipo}): r1/x1 ausentes no modelo; "
            f"impedância tratada como 0.0 na parametrização.")
        return 0.0, 0.0

    comprimento = _num(p.get("length"), 1.0) or 1.0
    unidade = str(p.get("units", "km")).strip().lower()

    # Normaliza o comprimento para km, que é a unidade em que r1/x1 do
    # OpenDSS são declarados por metro/quilômetro conforme `units`.
    if unidade in ("km", ""):
        fator_km = 1.0
    elif unidade in ("m", "meter", "meters", "metro", "metros"):
        fator_km = 0.001
    elif unidade in ("mi", "mile", "miles"):
        fator_km = 1.609344
    elif unidade in ("ft", "feet", "foot"):
        fator_km = 0.0003048
    elif unidade in ("kft", "1000ft"):
        fator_km = 0.3048
    elif unidade in ("in", "inch", "inches"):
        fator_km = 0.0000254
    elif unidade in ("cm",):
        fator_km = 0.00001
    else:
        fator_km = 1.0
        avisos.append(
            f"Ramo '{ramo.nome}': unidade '{unidade}' não reconhecida; "
            f"comprimento tratado como km.")

    r_ohm = r * comprimento * fator_km
    x_ohm = x * comprimento * fator_km

    # Z_base = kV² / MVA na barra de origem.
    kv = 13.8
    if ramo.bus1 in _BARRAS_KV:
        kv = _BARRAS_KV[ramo.bus1]
    z_base = (kv * kv) / (base_kva / 1000.0) if kv > 0 else 1.0
    if z_base <= 0:
        z_base = 1.0

    return r_ohm / z_base, x_ohm / z_base


# Mapa auxiliar barra -> kV, preenchido antes da conversão de impedâncias.
# (Usado por _impedancia_pu; ver montar_dados.)
_BARRAS_KV: Dict[str, float] = {}


# ---------------------------------------------------------------------------
# Montagem dos dados
# ---------------------------------------------------------------------------
def _ordenar_barras(rede: RedeEletrica) -> List[str]:
    """Ordem estável: fonte primeiro, depois BFS a partir dela, depois o resto.

    TRANSPARÊNCIA TÉCNICA: a varredura radial do sketch pressupõe uma árvore
    a partir da barra fonte. Ordenar em BFS aqui não muda o resultado, mas
    garante que a barra fonte fique no índice conhecido (BARRA_FONTE) e que
    barras desconexas apareçam no fim, sinalizadas por aviso.
    """
    fonte = rede.obter_fonte()
    raiz = fonte.bus1 if (fonte and fonte.bus1 in rede.barras) else None

    ordem: List[str] = []
    if raiz:
        ordem.append(raiz)
    elif rede.barras:
        ordem.append(next(iter(rede.barras)))

    visitados = set(ordem)
    fila = list(ordem)
    while fila:
        atual = fila.pop(0)
        for ramo in rede.ramos.values():
            if ramo.bus1 == atual and ramo.bus2 not in visitados:
                visitados.add(ramo.bus2)
                ordem.append(ramo.bus2)
                fila.append(ramo.bus2)
            elif ramo.bus2 == atual and ramo.bus1 not in visitados:
                visitados.add(ramo.bus1)
                ordem.append(ramo.bus1)
                fila.append(ramo.bus1)

    for nome in rede.barras:
        if nome not in visitados:
            ordem.append(nome)
            visitados.add(nome)

    return ordem


def _fmt_float(v: float, casas: int = 6) -> str:
    texto = f"{float(v):.{casas}f}"
    return texto


def _fmt_vetor(nome_tipo: str, nome: str, valores: List[str],
               comentario: str) -> str:
    corpo = ", ".join(valores) if valores else "0"
    return (f"/* {comentario} */\n"
            f"{nome_tipo} {nome}[{len(valores) if valores else 1}] = {{ "
            f"{corpo} }};")


def gerar_parametrizacao_arduino(projeto, caminho_saida: str) -> Dict[str, Any]:
    """Gera ``param_microrrede.h`` para o projeto e devolve um relatório.

    Parameters
    ----------
    projeto : objeto com ``caminho_rede`` e ``caminho_curvas`` (o ``Projeto``
        de ``bibliotecas.projeto``) OU uma ``RedeEletrica`` já carregada,
        caso em que ``caminho_curvas`` não é usado.
    caminho_saida : str
        Caminho completo do cabeçalho a gerar.

    Returns
    -------
    dict com ``caminho``, ``avisos`` (lista de strings), ``n_barras``,
    ``n_ramos`` e ``bess_bus``.
    """
    avisos: List[str] = []

    if isinstance(projeto, RedeEletrica):
        rede = projeto
        pasta_curvas = None
        avisos.append("Projeto recebido sem repositório de curvas: as curvas "
                      "horárias caem no default 1.0.")
    else:
        pasta_curvas = getattr(projeto, "caminho_curvas", None)
        caminho_rede_dir = getattr(projeto, "caminho_rede", None)
        if not caminho_rede_dir:
            raise ValueError("Projeto sem pasta de rede; nada a parametrizar.")

        caminho_json = os.path.join(caminho_rede_dir, "rede.json")
        if not os.path.isfile(caminho_json):
            raise ValueError(
                f"Nenhum 'rede.json' encontrado em '{caminho_rede_dir}'. "
                f"Desenhe e salve a rede no Editor antes de exportar a "
                f"parametrização do Arduino.")
        rede = RedeEletrica.carregar_json(caminho_json)

    if not rede.barras:
        raise ValueError(
            "A rede do projeto não possui barras. Nada a parametrizar — "
            "desenhe a rede no Editor antes de exportar.")

    nomes_barras = _ordenar_barras(rede)
    idx = {nome: i for i, nome in enumerate(nomes_barras)}

    global _BARRAS_KV
    _BARRAS_KV = {n: rede.barras[n].kv_base for n in nomes_barras}

    # ------------------------- Fonte e BESS ------------------------------ #
    fonte = rede.obter_fonte()
    if fonte and fonte.bus1 in idx:
        barra_fonte = idx[fonte.bus1]
        v_fonte = _num((fonte.parametros or {}).get("pu"), V_FONTE_PU_PADRAO)
        v_fonte = v_fonte if v_fonte is not None else V_FONTE_PU_PADRAO
    else:
        barra_fonte = 0
        v_fonte = V_FONTE_PU_PADRAO
        avisos.append(
            "Nenhuma fonte (Vsource) encontrada na rede; a barra de índice 0 "
            "foi adotada como origem da varredura, com 1.0 pu.")

    bess_bus = -1
    for der in rede.derivacoes.values():
        if der.tipo == "Storage" and der.bus1 in idx:
            bess_bus = idx[der.bus1]
            break

    # Potencia nominal do BESS: o Mega precisa dela para converter a tensao
    # do DAC (A0/A1) de volta em kW/kvar. Vem do Storage do rede.json; sem
    # valor, KW_RATING = 0 e os setpoints analogicos sao lidos como zero em
    # vez de serem multiplicados por uma escala inventada.
    kw_bess = 0.0
    for der in rede.derivacoes.values():
        if der.tipo != "Storage":
            continue
        kw_bess = _num((der.parametros or {}).get("kw"), 0.0) or 0.0
        if kw_bess > 0:
            break
    if bess_bus >= 0 and kw_bess <= 0:
        avisos.append(
            "Storage sem potencia nominal (kW) declarada: KW_RATING = 0 no "
            "cabecalho do Mega e os setpoints analogicos recebidos do ESP32 "
            "serao lidos como zero. Declare a potencia no Editor de Rede.")
    if bess_bus < 0:
        avisos.append(
            "Nenhum Storage no rede.json: BESS_BUS = -1. A placa não aplicará "
            "injeção do BESS (a atuação do ESP32 fica inerte nesta bancada).")

    # --------------------------- Ramos ---------------------------------- #
    ramos_validos = []
    for ramo in rede.ramos.values():
        if ramo.bus1 not in idx or ramo.bus2 not in idx:
            avisos.append(
                f"Ramo '{ramo.nome}' ignorado: referencia barra inexistente.")
            continue
        r_pu, x_pu = _impedancia_pu(ramo, BASE_KVA, avisos)
        ramos_validos.append((idx[ramo.bus1], idx[ramo.bus2], r_pu, x_pu,
                              ramo.nome))

    if not ramos_validos:
        avisos.append("Nenhum ramo válido na rede: a varredura devolverá a "
                      "tensão da fonte em todas as barras.")

    # ------------------------ Cargas e geração --------------------------- #
    load_kw = [0.0] * len(nomes_barras)
    load_kvar = [0.0] * len(nomes_barras)
    load_curva: List[str] = ["Nenhuma"] * len(nomes_barras)
    load_mult: List[List[float]] = [[1.0] * 24 for _ in nomes_barras]

    gen_kw = [0.0] * len(nomes_barras)
    gen_kvar = [0.0] * len(nomes_barras)
    gen_mult: List[List[float]] = [[0.0] * 24 for _ in nomes_barras]

    cap_kvar = [0.0] * len(nomes_barras)

    for der in rede.derivacoes.values():
        if der.bus1 not in idx:
            continue
        b = idx[der.bus1]
        p = der.parametros or {}

        if der.tipo == "Load":
            load_kw[b] += _num(p.get("kw"), 0.0) or 0.0
            load_kvar[b] += _num(p.get("kvar"), 0.0) or 0.0
            nome_curva = str(p.get("daily", "Nenhuma"))
            m = _curva_24h(pasta_curvas, nome_curva, avisos,
                           f"Carga '{der.nome}'")
            if load_curva[b] == "Nenhuma":
                load_curva[b] = nome_curva
                load_mult[b] = m
            else:
                # Duas cargas na mesma barra com curvas diferentes: a tabela
                # única do protocolo não distingue. Mantém a primeira e avisa.
                avisos.append(
                    f"Barra '{der.bus1}' tem mais de uma carga; a curva de "
                    f"'{der.nome}' foi agregada pela primeira curva "
                    f"('{load_curva[b]}'). Limitação da tabela de 24 "
                    f"multiplicadores por barra.")

        elif der.tipo in ("PVSystem", "Generator"):
            kw = _num(p.get("pmpp"))
            if kw is None:
                kw = _num(p.get("kva"), 0.0) or 0.0
            gen_kw[b] += kw or 0.0
            gen_kvar[b] += _num(p.get("kvar"), 0.0) or 0.0
            nome_curva = str(p.get("daily", "Nenhuma"))
            m = _curva_24h(pasta_curvas, nome_curva, avisos,
                           f"Geração '{der.nome}'")
            if sum(gen_mult[b]) == 0.0:
                gen_mult[b] = m
            else:
                avisos.append(
                    f"Barra '{der.bus1}' tem mais de uma geração; a curva de "
                    f"'{der.nome}' foi desprezada na tabela agregada.")

        elif der.tipo == "Capacitor":
            cap_kvar[b] += _num(p.get("kvar"), 0.0) or 0.0

    # ----------------------- Mapa de pinos PWM --------------------------- #
    pinos: List[int] = []
    for i in range(len(nomes_barras)):
        if i < len(PINOS_PWM_MEGA):
            pinos.append(PINOS_PWM_MEGA[i])
        else:
            pinos.append(-1)
    if len(nomes_barras) > len(PINOS_PWM_MEGA):
        avisos.append(
            f"A rede tem {len(nomes_barras)} barras e o Mega oferece "
            f"{len(PINOS_PWM_MEGA)} canais PWM livres (pinos "
            f"{PINOS_PWM_MEGA}) depois de reservar os pinos do enlace com "
            f"o ESP32: as barras de índice >= {len(PINOS_PWM_MEGA)} ficam "
            f"sem saída analógica (PINO_PWM_BARRA = -1). O sketch não aciona "
            f"nada para elas — a tensão dessas barras não aparece na bancada.")
    ocupados = pinos_ocupados_pelo_enlace()
    colididos = [p for p in pinos if p >= 0 and p in ocupados]
    if colididos:
        avisos.append(
            f"COLISÃO DE PINOS: {colididos} são usados simultaneamente como "
            f"saída PWM de barra e como fio do enlace com o ESP32. O "
            f"experimento NÃO é válido assim — ajuste PINOS_PWM_MEGA em "
            f"exportador_arduino.py ou reduza o número de barras.")

    # --------------------------- Escrita -------------------------------- #
    linhas: List[str] = []
    linhas.append("/* ======================================================"
                  "=====================")
    linhas.append(" *  param_microrrede.h  —  GERADO AUTOMATICAMENTE. NÃO EDITE.")
    linhas.append(" *")
    linhas.append(" *  Fonte: rede desenhada no Editor do TCC OpenDSS.")
    linhas.append(" *  Gerador: bibliotecas/exportador_arduino.py")
    linhas.append(f" *  Projeto: {getattr(projeto, 'nome', '(rede avulsa)')}")
    linhas.append(" *")
    linhas.append(" *  Consumido por: hardware/arduino_microrrede/"
                  "arduino_microrrede.ino")
    linhas.append(" *")
    linhas.append(" *  TRANSPARÊNCIA TÉCNICA")
    linhas.append(" *  --------------------")
    linhas.append(" *  O sketch calcula as tensões por VARREDURA RADIAL "
                  "aproximada:")
    linhas.append(" *      dV ~= (R*P + X*Q) / V^2   [pu]")
    linhas.append(" *  Não é fluxo de potência iterativo. Perdas não "
                  "realimentam as potências;")
    linhas.append(" *  malhas são tratadas como radiais; tap de "
                  "transformador não é modelado.")
    linhas.append(" *  Serve para ver sentido e ordem de grandeza da resposta "
                  "da microrrede.")
    linhas.append(" *  Os números de referência continuam sendo os do "
                  "OpenDSS.")
    linhas.append(" * ======================================================"
                  "=====================*/")
    linhas.append("")
    linhas.append("#ifndef PARAM_MICRORREDE_H")
    linhas.append("#define PARAM_MICRORREDE_H")
    linhas.append("")
    linhas.append("/* --- Dimensões da rede ---------------------------------- */")
    linhas.append(f"#define N_BARRAS ({len(nomes_barras)})")
    linhas.append(f"#define N_RAMOS  ({len(ramos_validos)})")
    linhas.append(f"#define BARRA_FONTE ({barra_fonte})")
    linhas.append(f"#define BESS_BUS ({bess_bus})")
    linhas.append("")
    linhas.append("/* --- Bases e escalas do ensaio -------------------------- */")
    linhas.append(f"#define BASE_KVA ({_fmt_float(BASE_KVA, 1)}f)")
    linhas.append(f"#define V_FONTE_PU ({_fmt_float(v_fonte, 4)}f)")
    linhas.append(f"#define PU_PWM_MAX ({_fmt_float(PU_PWM_MAX_PADRAO, 2)}f)")
    linhas.append(f"#define SEGUNDOS_POR_HORA "
                  f"({_fmt_float(SEGUNDOS_POR_HORA_PADRAO, 2)}f)")
    linhas.append(f"#define DIA_INICIAL ({DIA_INICIAL_PADRAO})")
    linhas.append(f"#define NUVEM_FATOR ({_fmt_float(NUVEM_FATOR_PADRAO, 2)}f)")
    linhas.append(f"#define KW_RATING ({_fmt_float(kw_bess, 3)}f)")
    linhas.append("")
    linhas.append("/* --- Interface física com o ESP32 (12 ligações, sem UART) - */")
    linhas.append("/* Cada #define abaixo é um fio: o pino do Mega e o pino do ESP32")
    linhas.append(" * correspondente. O MAPA_LIGACOES de exportador_arduino.py é a")
    linhas.append(" * fonte única — o cabeçalho do ESP32 é gerado do mesmo mapa. */")
    linhas.append(f'#define PLACA_MICRORREDE '
                  f'"Arduino Mega 2560 R3 (ATmega2560, 5 V)"')
    for lig in MAPA_LIGACOES:
        if not lig["macro_mega"]:
            continue
        pino = PINO_NUMERICO_MEGA[lig["n"]]
        linhas.append(f"#define {lig['macro_mega']:16s} ({pino})"
                      f"   /* Mega {lig['mega']:4s} <-> ESP32 "
                      f"{lig['esp32']}: {lig['dados']} | "
                      f"{CONDICIONAMENTO[lig['n']]} */")
    linhas.append("")
    linhas.append("/* Escalas da interface analógica (escolhas de projeto) ---- */")
    linhas.append("/* V_pu convertida em tensão para o PWM; e o inverso no ADC que")
    linhas.append(" * lê o DAC do ESP32. O DAC entrega no máximo 3,3 V num ADC de")
    linhas.append(" * referência 5 V: a leitura usa ~66% da faixa (resolução menor,")
    linhas.append(" * declarada, não corrigida por hardware). */")
    linhas.append(f"#define VPU_ANALOG_MAX "
                  f"({_fmt_float(VPU_ANALOG_MAX_PADRAO, 2)}f)")
    linhas.append(f"#define DAC_MIDRAIL_V "
                  f"({_fmt_float(DAC_MIDRAIL_V_PADRAO, 2)}f)")
    linhas.append(f"#define VREF_MEGA_ADC "
                  f"({_fmt_float(VREF_MEGA_ADC_PADRAO, 2)}f)")
    linhas.append(f"#define PWM_FILTRO_RC \"{FILTRO_RC_SUGERIDO}\"")
    linhas.append("")
    linhas.append("/* Condicionamento de nível Mega 5 V -> ESP32 3,3 V (externo) - */")
    linhas.append("/* O Mega 2560 R3 tem lógica de 5 V e o ESP32 NÃO tolera 5 V nas")
    linhas.append(" * entradas. As 7 linhas Mega->ESP32 levam DIVISOR externo")
    linhas.append(" * 10k/20k (no lado do ESP32); a linha do V_pu soma o filtro RC")
    linhas.append(f" * ANTES do divisor. Divisão: {_fmt_float(R_GND_DIV_OHMS, 0)}/"
                  f"({_fmt_float(R_SERIE_DIV_OHMS, 0)}+"
                  f"{_fmt_float(R_GND_DIV_OHMS, 0)}) = "
                  f"{_fmt_float(DIVISOR_LEVEL_PADRAO, 4)}.")
    linhas.append(" * 5,0 V -> 3,33 V (HIGH válido e dentro do absoluto máximo).")
    linhas.append(" * As linhas ESP32->Mega são DIRETAS: 3,3 V > VIH do ATmega")
    linhas.append(" * (0,6 x 5 V = 3,0 V). Em instalação de campo use level")
    linhas.append(" * shifter; na bancada v1 a ligação direta é suficiente. */")
    linhas.append(f"#define DIVISOR_DIGITAL ({_fmt_float(DIVISOR_LEVEL_PADRAO, 4)}f)")
    linhas.append(f"#define R_SERIE_DIV ({_fmt_float(R_SERIE_DIV_OHMS, 1)}f)")
    linhas.append(f"#define R_GND_DIV ({_fmt_float(R_GND_DIV_OHMS, 1)}f)")
    linhas.append(f"#define MEGA_VCC_PWM ({_fmt_float(MEGA_VCC_PWM_V_PADRAO, 2)}f)")
    linhas.append(f"#define DIVISOR_VPU ({_fmt_float(DIVISOR_LEVEL_PADRAO, 4)}f)")
    linhas.append(f"#define VIH_MEGA ({_fmt_float(VIH_MEGA_V_PADRAO, 2)}f)")
    linhas.append("")
    linhas.append("/* --- Nomes das barras (para o log de bancada) ----------- */")
    nomes_c = ", ".join(f'"{n}"' for n in nomes_barras)
    linhas.append(f'static const char *const NOME_BARRA[N_BARRAS] = '
                  f'{{ {nomes_c} }};')
    linhas.append("")
    linhas.append("/* --- Topologia: ramos (índices de barra + pu) ----------- */")
    if ramos_validos:
        linhas.append("static const uint8_t RAMO_BUS1[N_RAMOS] = { "
                      + ", ".join(str(r[0]) for r in ramos_validos) + " };")
        linhas.append("static const uint8_t RAMO_BUS2[N_RAMOS] = { "
                      + ", ".join(str(r[1]) for r in ramos_validos) + " };")
        linhas.append("static const float RAMO_R_PU[N_RAMOS] = { "
                      + ", ".join(_fmt_float(r[2]) + "f"
                                  for r in ramos_validos) + " };")
        linhas.append("static const float RAMO_X_PU[N_RAMOS] = { "
                      + ", ".join(_fmt_float(r[3]) + "f"
                                  for r in ramos_validos) + " };")
        comentario_ramos = "\n".join(
            f" *   [{i}] {r[4]}: {nomes_barras[r[0]]} -> {nomes_barras[r[1]]}"
            f"  R={r[2]:.6f} pu  X={r[3]:.6f} pu"
            for i, r in enumerate(ramos_validos))
        linhas.append("/*\n" + comentario_ramos + "\n */")
    else:
        linhas.append("static const uint8_t RAMO_BUS1[1] = { 0 };")
        linhas.append("static const uint8_t RAMO_BUS2[1] = { 0 };")
        linhas.append("static const float RAMO_R_PU[1] = { 0.0f };")
        linhas.append("static const float RAMO_X_PU[1] = { 0.0f };")
    linhas.append("")
    linhas.append("/* --- Cargas por barra (kW/kvar nominais agregados) ------ */")
    linhas.append(_fmt_vetor("static const float", "LOAD_KW",
                             [_fmt_float(v, 3) + "f" for v in load_kw],
                             "Nominal agregado por barra."))
    linhas.append(_fmt_vetor("static const float", "LOAD_KVAR",
                             [_fmt_float(v, 3) + "f" for v in load_kvar],
                             "Nominal agregado por barra."))
    for b, nome_curva in enumerate(load_curva):
        if nome_curva != "Nenhuma":
            linhas.append(f"/* Barra {b} ({nomes_barras[b]}): curva "
                          f"'{nome_curva}' */")
    linhas.append("")
    linhas.append("/* --- Curvas horárias de carga: 24 multiplicadores ------ */")
    linhas.append("static const float LOAD_MULT[N_BARRAS][24] = {")
    for b, m in enumerate(load_mult):
        linhas.append(f"  /* {b} {nomes_barras[b][:14]:14s} */ {{ "
                      + ", ".join(f"{x:.3f}f" for x in m) + " },")
    linhas.append("};")
    linhas.append("")
    linhas.append("/* --- Geração (PV/Generator) por barra ------------------ */")
    linhas.append(_fmt_vetor("static const float", "GEN_KW",
                             [_fmt_float(v, 3) + "f" for v in gen_kw],
                             "Geração nominal agregada (injeção)."))
    linhas.append(_fmt_vetor("static const float", "GEN_KVAR",
                             [_fmt_float(v, 3) + "f" for v in gen_kvar],
                             "Reativo nominal agregado (injeção)."))
    linhas.append("static const float GEN_MULT[N_BARRAS][24] = {")
    for b, m in enumerate(gen_mult):
        linhas.append(f"  /* {b} {nomes_barras[b][:14]:14s} */ {{ "
                      + ", ".join(f"{x:.3f}f" for x in m) + " },")
    linhas.append("};")
    linhas.append("")
    linhas.append("/* --- Capacitores (kvar fixo, sempre ligados na v1) ---- */")
    linhas.append(_fmt_vetor("static const float", "CAP_KVAR",
                             [_fmt_float(v, 3) + "f" for v in cap_kvar],
                             "Injeção reativa por barra (constante)."))
    linhas.append("")
    linhas.append("/* --- Saída analógica: pino PWM por barra --------------- */")
    linhas.append("static const int8_t PINO_PWM_BARRA[N_BARRAS] = { "
                  + ", ".join(str(p) for p in pinos) + " };")
    linhas.append("")
    linhas.append("#endif /* PARAM_MICRORREDE_H */")
    linhas.append("")

    os.makedirs(os.path.dirname(os.path.abspath(caminho_saida)), exist_ok=True)
    with open(caminho_saida, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(linhas))

    return {
        "caminho": os.path.abspath(caminho_saida),
        "avisos": avisos,
        "n_barras": len(nomes_barras),
        "n_ramos": len(ramos_validos),
        "bess_bus": bess_bus,
    }


# ---------------------------------------------------------------------------
# Execução direta (teste / linha de comando)
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    """`python -m bibliotecas.exportador_arduino <caminho_raiz_projeto>`."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Gera param_microrrede.h a partir do projeto do TCC.")
    parser.add_argument("projeto", help="Caminho raiz do projeto "
                                        "(contém rede/ e curvas/).")
    parser.add_argument("--saida", help="Caminho completo do .h gerado. "
                                        "Default: <projeto>/hardware/"
                                        "param_microrrede.h")
    args = parser.parse_args(argv)

    from .projeto import abrir_projeto_por_caminho

    projeto = abrir_projeto_por_caminho(args.projeto)
    saida = args.saida or os.path.join(
        projeto.caminho_raiz, "hardware", NOME_ARQUIVO)

    relatorio = gerar_parametrizacao_arduino(projeto, saida)
    print(f"Gerado: {relatorio['caminho']}")
    print(f"Barras: {relatorio['n_barras']} | Ramos: {relatorio['n_ramos']} "
          f"| BESS_BUS: {relatorio['bess_bus']}")
    for aviso in relatorio["avisos"]:
        print(f"  AVISO: {aviso}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
