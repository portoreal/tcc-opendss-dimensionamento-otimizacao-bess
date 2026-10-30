from __future__ import annotations

__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Gerador da PARAMETRIZAÇÃO do ESP32 (controlador do Sistema BESS).

CONTEXTO ARQUITETURAL (definido com o pesquisador):
o código embarcado do ESP32 NÃO é regenerado a cada projeto. O repositório
contém um sketch PRÉ-PRONTO e fixo
(``hardware/esp32_controle_bess/esp32_controle_bess.ino``) que implementa a
lógica de controle (despacho de potência ativa por tabela horária + controle
de reativa Volt-Var/Volt-Watt do sistema de armazenamento para qualidade de
energia). O que ESTE módulo gera, a cada projeto, é apenas o cabeçalho C
``param_esp32.h`` com as constantes e tabelas daquele projeto — preenchido
DEPOIS de concluído o estudo de otimização de alocação de BESS (a janela de
resultados da Otimização é quem dispara a geração, ver ``otimizacao_ui.py``).

DE ONDE VEM CADA DADO (nenhum valor é inventado):

- Potência ativa nominal (kW), energia (kWh), kVA do inversor: da
  CONFIGURAÇÃO VENCEDORA do estudo de otimização (``config_vencedora``:
  ``{"bus": ..., "kw": ..., "kwh": ...}``), que é o que o otimizador
  efetivamente avaliou. Quando o projeto tem o Sistema BESS desenhado no
  Editor de Rede, o elemento Storage do ``rede.json`` é consultado como
  fonte complementar (kVA, curva diária, limites de SoC).
- Tabela de despacho 24 h: REUTILIZA a regra dos módulos de simulação
  (``_eh_hora_ponta`` de ``economia_energia``; limites de SoC padrão
  0,2/0,95/0,5), aplicada hora a hora com realimentação de SoC — a mesma
  forma de ``economia_energia._simular_dia``. Duas saídas:
    * ``DESPACHO_ESTADO[24]`` / ``DESPACHO_KW[24]``: o despacho OBSERVADO na
      regra sem realimentação (esta tabela é documental/histórica);
    * ``SOC_MIN`` / ``SOC_MAX`` / ``SOC_INICIAL`` + a mesma regra de decisão,
      que o sketch reaplica com o SoC que ele próprio integra. Isto é
      necessário porque a regra real é FECHADA EM MALHA: se a bateria
      atingir o limite de SoC, o módulo de simulação passa a ``idling``. Uma
      tabela estática divergiria da simulação exatamente nos horários em que
      a bateria satura.
- Curvas Volt-Var/Volt-Watt: os PONTOS REAIS da ``XYCurve`` do projeto
  (``rede.json`` → ``curvas_xy``), referenciados pelo ``InvControl`` do
  Sistema BESS via ``vvc_curve1``/``voltwatt_curve``. Nada de curva
  "padrão" hardcoded aqui: se a curva não existir no projeto, a parametrização
  registra AVISO e emite um único ponto neutro (Q = 0), o que desabilita
  funcionalmente o controle de reativa em vez de inventar uma característica.

TRANSPARÊNCIA TÉCNICA (limitações declaradas, não escondidas):

1) O controle de reativa é implementado no sketch como INTERPOLAÇÃO LINEAR
   sobre a curva do projeto. O OpenDSS faz o mesmo tipo de interpolação,
   mas os demais parâmetros do InvControl (``RefReactivePower``,
   ``VoltWattCH_Curve``, dinâmica de atuação, atrasos) NÃO são replicados.
2) O SoC é integrado no firmware como P×Δt/Energia nominal. Um BMS real
   informa o SoC por outro caminho (CAN/Modbus) — o SoC do firmware é
   apropriado para o experimento, não é um substituto do BMS.
3) A telemetria é JSON por porta serial (1 Hz). WiFi/MQTT está fora desta
   versão (``WIFI_SSID`` vazio = desabilitado no sketch).
4) A interface com o Arduino Mega é FÍSICA e direta: 12 ligações digitais
   e analógicas ponto a ponto (mapa canônico em `exportador_arduino.
   MAPA_LIGACOES`, emitido como #define nos dois cabeçalhos). Não há
   protocolo serial entre as placas. Ver `hardware/README.md`.
"""

import os
from typing import Any, Dict, List, Optional, Tuple

from .economia_energia import _eh_hora_ponta
from .exportador_arduino import (
    MAPA_LIGACOES,
    PINO_NUMERICO_MEGA,
    VPU_ANALOG_MAX_PADRAO,
    DAC_MIDRAIL_V_PADRAO,
    VREF_MEGA_ADC_PADRAO,
    VREF_ESP32_DAC_PADRAO,
    FILTRO_RC_SUGERIDO,
    CONDICIONAMENTO,
    DIVISOR_LEVEL_PADRAO,
    MEGA_VCC_PWM_V_PADRAO,
    R_GND_DIV_OHMS,
    R_SERIE_DIV_OHMS,
)
from .modelo_rede import RedeEletrica

# ---------------------------------------------------------------------------
# Constantes da regra de despacho (IDÊNTICAS aos módulos de simulação)
# ---------------------------------------------------------------------------

#: Limites de SoC padrão de `economia_energia` / `ao_vivo_engine` (frações 0-1).
SOC_MIN_PADRAO = 0.20
SOC_MAX_PADRAO = 0.95
SOC_INICIAL_PADRAO = 0.50

#: Janela de ponta padrão (horas inteiras, fim exclusivo), idêntica ao default
#: de `economia_energia.analisar_economia_energia`.
PONTA_INICIO_PADRAO = 18
PONTA_FIM_PADRAO = 21

#: Códigos de estado usados no cabeçalho C (o sketch mapeia para os comandos
#: do inversor). NÃO reordene: os números estão gravados no contrato do .ino.
ESTADO_IDLING = 0
ESTADO_CHARGING = 1
ESTADO_DISCHARGING = 2

#: Número de pino físico no ESP32 para cada ligação do mapa canônico.
#: GPIO 36 é o VP (ADC1, atenuação 11 dB = faixa 0..3,3 V); GPIO 25/26
#: são os únicos DACs do ESP32 (8 bits). A fonte do mapa é
#: exportador_arduino.MAPA_LIGACOES — aqui só se resolve o número.
PINO_NUMERICO_ESP32 = {
    1: 23, 2: 22, 3: 21, 4: 19, 5: 18, 6: 5, 7: 36,
    8: 25, 9: 26, 10: 27, 11: 14, 12: None,
}

#: Amostras do ADC por leitura de tensão (média móvel no sketch).
ADC_AMOSTRAS_PADRAO = 8


# ---------------------------------------------------------------------------
# Leitura do projeto
# ---------------------------------------------------------------------------

def _to_float(valor: Any, padrao: float) -> float:
    """Conversão tolerante de valores do rede.json (que são gravados como
    texto pelo Editor) para float. O Editor grava "" para vazio."""
    if valor is None:
        return padrao
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace(",", ".")
    if not texto:
        return padrao
    try:
        return float(texto)
    except ValueError:
        return padrao


def _carregar_rede(projeto: Any) -> Optional[RedeEletrica]:
    """Carrega o ``rede.json`` do projeto.

    Aceita um caminho direto do ``rede.json``, um objeto ``Projeto`` (usa
    ``caminho_rede/rede.json``, como em ``ao_vivo_ui``) ou qualquer objeto com
    ``caminho_rede_json``. Devolve ``None`` (com aviso do chamador) se não
    houver rede: a parametrização ainda é possível a partir da config
    vencedora, mas sem curvas e sem kVA — o que precisa ser dito, não mascarado.
    """
    caminho = _resolver_caminho_rede(projeto)

    if not caminho or not os.path.exists(caminho):
        return None
    try:
        return RedeEletrica.carregar_json(caminho)
    except Exception:
        return None


def _resolver_caminho_rede(projeto: Any) -> Optional[str]:
    """Resolve o caminho absoluto do ``rede.json`` de um projeto."""
    if isinstance(projeto, str):
        return os.path.abspath(projeto)
    if projeto is None:
        return None

    caminho = getattr(projeto, "caminho_rede_json", None)
    if caminho:
        return str(caminho)

    pasta_rede = getattr(projeto, "caminho_rede", None)
    if pasta_rede:
        return os.path.join(str(pasta_rede), "rede.json")

    raiz = getattr(projeto, "caminho_raiz", None)
    if raiz:
        return os.path.join(str(raiz), "rede", "rede.json")
    return None


def _localizar_sistema_bess(rede: Optional[RedeEletrica],
                            barra_vencedora: str,
                            grupo_preferido: Optional[str] = None
                            ) -> Tuple[Optional[str], Optional[dict], Optional[dict]]:
    """Localiza o Sistema BESS (Storage + InvControl) no ``rede.json``.

    Critério, em ordem:
      1. ``grupo_preferido`` (nome do Sistema BESS), se informado;
      2. o Storage cujo ``bus1`` coincide com a barra vencedora do estudo;
      3. o primeiro Storage existente (registrando a divergência de barra no
         dicionário de avisos do chamador).

    Retorna ``(nome_grupo, derivacao_storage, derivacao_invcontrol)``; os
    itens ausentes vêm como ``None``. NÃO inventa elementos: se não houver
    Storage desenhado, devolve ``(None, None, None)``.
    """
    if rede is None:
        return None, None, None

    storages = [
        d for d in getattr(rede, "derivacoes", {}).values()
        if getattr(d, "tipo", "") == "Storage"
    ]
    if not storages:
        return None, None, None

    escolhido = None
    if grupo_preferido:
        for derivacao in storages:
            if getattr(derivacao, "grupo", None) == grupo_preferido:
                escolhido = derivacao
                break
    if escolhido is None and barra_vencedora:
        for derivacao in storages:
            if str(getattr(derivacao, "bus1", "")) == str(barra_vencedora):
                escolhido = derivacao
                break
    if escolhido is None:
        escolhido = storages[0]

    grupo = getattr(escolhido, "grupo", None)
    invcontrol = None
    if grupo:
        for derivacao in getattr(rede, "derivacoes", {}).values():
            if (getattr(derivacao, "tipo", "") == "InvControl"
                    and getattr(derivacao, "grupo", None) == grupo):
                invcontrol = derivacao
                break
    return grupo, escolhido, invcontrol


def _extrair_curva(projeto_rede: Optional[RedeEletrica],
                   nome_curva: Optional[str]) -> Tuple[List[float], List[float], bool]:
    """Extrai os pontos (x, y) de uma XYCurve do projeto.

    Devolve ``(xs, ys, encontrada)``. Quando a curva não existe (ou o nome
    não foi declarado no InvControl), devolve um único ponto neutro
    ``(1.0, 0.0)`` — Q = 0 em toda a faixa, isto é, controle de reativa
    INERTE — e sinaliza ``encontrada=False`` para que o chamador registre o
    aviso. Preferimos um controle desligado e explícito a uma curva
    fictícia agindo sobre o conversor.
    """
    if not nome_curva or projeto_rede is None:
        return [1.0], [0.0], False

    curvas = getattr(projeto_rede, "curvas_xy", {}) or {}
    curva = curvas.get(nome_curva)
    if curva is None:
        return [1.0], [0.0], False

    xs = [float(v) for v in getattr(curva, "xarray", []) or []]
    ys = [float(v) for v in getattr(curva, "yarray", []) or []]
    n = min(len(xs), len(ys))
    if n == 0:
        return [1.0], [0.0], False

    pontos = sorted(zip(xs[:n], ys[:n]), key=lambda par: par[0])
    return [p[0] for p in pontos], [p[1] for p in pontos], True


def _modo_invcontrol(parametros: dict) -> Tuple[bool, bool]:
    """Decide quais blocos de controle o firmware deve ativar.

    Retorna ``(usa_voltv, usa_voltwatt)`` a partir das chaves reais gravadas
    pelo ``sistema_bess.montar_elementos_sistema_bess``:
    ``Mode`` (VOLTVAR/VOLTWATT) ou ``CombiMode`` (VV_VW/VV_DRC).
    """
    modo = str(parametros.get("Mode", "") or "").upper()
    combi = str(parametros.get("CombiMode", "") or "").upper()
    efetivo = combi or modo

    usa_voltv = ("VOLTVAR" in efetivo) or ("VV_VW" in efetivo) or ("VV_DRC" in efetivo)
    usa_voltwatt = ("VOLTWATT" in efetivo) or ("VV_VW" in efetivo)
    # Fallback: se o modo não casar nenhum rótulo conhecido, a presença da
    # chave de curva é a evidência mais forte de qual controle está ativo.
    if not usa_voltv and "vvc_curve1" in parametros:
        usa_voltv = True
    if not usa_voltwatt and "voltwatt_curve" in parametros:
        usa_voltwatt = True
    return usa_voltv, usa_voltwatt


# ---------------------------------------------------------------------------
# Tabela de despacho
# ---------------------------------------------------------------------------

def _simular_soc_da_tabela(kw_nominal: float, kwh_nominal: float,
                           soc_min: float, soc_max: float, soc_inicial: float,
                           ponta_inicio: int, ponta_fim: int
                           ) -> Tuple[List[int], List[float]]:
    """Percorre as 24 h aplicando a regra com realimentação de SoC, para
    obter a tabela REALMENTE observada na simulação (com saturação) e o SoC
    resultante ao final de cada hora.

    A regra é a LITERAL de ``economia_energia._simular_dia``:
        hora de ponta e soc > soc_min -> DISCHARGING
        fora de ponta  e soc < soc_max -> CHARGING
        caso contrário                 -> IDLING

    O SoC é integrado com passo de 1 h a plena carga (``kW/kWh``), pois
    ``%Charge``/``%Discharge`` = 100% na criação do elemento (ver
    ``economia_energia._inserir_bess_idling``). É a INTEGRAÇÃO que faz a
    tabela fechar em malha: ao saturar, a hora seguinte vira IDLING.
    """
    if kwh_nominal <= 0 or kw_nominal <= 0:
        return [ESTADO_IDLING] * 24, [soc_inicial] * 24

    passo_soc = kw_nominal / kwh_nominal  # fração de SoC em 1 hora a plena carga

    estados_finais: List[int] = []
    soc_por_hora: List[float] = []
    soc = float(soc_inicial)

    for hora in range(24):
        ponta = _eh_hora_ponta(hora, ponta_inicio, ponta_fim)
        if ponta and soc > soc_min:
            estado = ESTADO_DISCHARGING
        elif (not ponta) and soc < soc_max:
            estado = ESTADO_CHARGING
        else:
            estado = ESTADO_IDLING

        if estado == ESTADO_DISCHARGING:
            soc = max(soc_min, soc - passo_soc)
        elif estado == ESTADO_CHARGING:
            soc = min(soc_max, soc + passo_soc)

        estados_finais.append(estado)
        soc_por_hora.append(soc)

    return estados_finais, soc_por_hora


# ---------------------------------------------------------------------------
# Emissão do cabeçalho C
# ---------------------------------------------------------------------------

def _formatar_vetor_float(valores: List[float], casas: int = 4) -> str:
    return ", ".join(f"{v:.{casas}f}" for v in valores)


def _formatar_vetor_int(valores: List[int]) -> str:
    return ", ".join(str(int(v)) for v in valores)


def _montar_cabecalho(dados: dict) -> str:
    """Monta o texto do ``param_esp32.h``."""
    linhas: List[str] = []
    add = linhas.append

    add("/*")
    add(" * param_esp32.h — PARAMETRIZAÇÃO gerada automaticamente.")
    add(" *")
    add(" * NÃO EDITE À MÃO: o arquivo é sobrescrito a cada geração a partir do")
    add(" * projeto e do resultado do estudo de otimização de alocação de BESS.")
    add(" *")
    add(" * Sketch pré-pronto consumidor (lógica fixa, versionada):")
    add(" *   hardware/esp32_controle_bess/esp32_controle_bess.ino")
    add(" *")
    add(" * Gerado por: bibliotecas/exportador_esp32.py")
    add(f" * Projeto:    {dados['projeto']}")
    if dados.get("tarifa"):
        add(f" * Tarifa:     {dados['tarifa']}")
    add(" *")
    add(" * TRANSPARÊNCIA: os limites de SoC e a regra de despacho seguem os")
    add(" * módulos de simulação do TCC (ponta -> descarrega, fora ponta ->")
    add(" * carrega, com bloqueio nos limites de SoC). As curvas de reativa são")
    add(" * os pontos REAIS do InvContç do projeto (XYCurve), não curvas típicas")
    add(" * inventadas. Ver o dicionário de AVISOS devolvido pelo gerador.")
    add(" */")
    add("")
    add("#ifndef PARAM_ESP32_H")
    add("#define PARAM_ESP32_H")
    add("")
    add("/* ---------------- Identificação do projeto ---------------- */")
    add(f"#define BESS_NOME \"{dados['nome_sistema']}\"")
    add(f"#define BESS_BUS  \"{dados['barra']}\"")
    add(f"#define BESS_BUS_IDX {dados['indice_barra']}")
    add("")
    add("/* ---------------- Dimensionamento (configuração vencedora) --- */")
    add(f"#define KW_RATING   {dados['kw_rating']:.3f}f")
    add(f"#define KWH_RATING  {dados['kwh_rating']:.3f}f")
    add(f"#define KVA_INVERSOR {dados['kva_inversor']:.3f}f")
    add(f"#define Q_LIM_KVAR  {dados['q_lim_kvar']:.3f}f")
    add("")
    add("/* ---------------- Limites de operação da bateria ------------- */")
    add(f"#define SOC_MIN     {dados['soc_min']:.4f}f")
    add(f"#define SOC_MAX     {dados['soc_max']:.4f}f")
    add(f"#define SOC_INICIAL {dados['soc_inicial']:.4f}f")
    add("")
    add("/* ---------------- Janela tarifária de ponta ---------------- */")
    add(f"#define PONTA_INICIO {dados['ponta_inicio']}")
    add(f"#define PONTA_FIM    {dados['ponta_fim']}")
    add("")
    add("/* ---------------- Tabela de despacho de ATIVA (24 h) -------- */")
    add("/* 0 = IDLING | 1 = CHARGING | 2 = DISCHARGING")
    add(" * Tabela OBSERVADA na regra de simulação. O sketch reavalia a decisão a")
    add(" * cada hora com o SoC que ele mesmo integra (a regra é fechada em malha:")
    add(" * se o SoC saturar, o estado vira IDLING). */")
    add(f"#define DESPACHO_ESTADO_LEN 24")
    add("static const uint8_t DESPACHO_ESTADO[DESPACHO_ESTADO_LEN] = {")
    add(f"  {_formatar_vetor_int(dados['despacho_estado'])}")
    add("};")
    add("")
    add("/* Magnitude do despacho em kW (potência nominal quando ativo). */")
    add("static const float DESPACHO_KW[DESPACHO_ESTADO_LEN] = {")
    add(f"  {_formatar_vetor_float(dados['despacho_kw'], 3)}")
    add("};")
    add("")
    add("/* SoC ao final de cada hora, para auditoria (não usado no controle). */")
    add("static const float SOC_POR_HORA[DESPACHO_ESTADO_LEN] = {")
    add(f"  {_formatar_vetor_float(dados['soc_por_hora'], 4)}")
    add("};")
    add("")
    add("/* ---------------- Controle de REATIVA (qualidade de energia) - */")
    add(f"#define USA_VOLTVAR    {1 if dados['usa_voltv'] else 0}")
    add(f"#define USA_VOLTWATT   {1 if dados['usa_voltwatt'] else 0}")
    add(f"#define MODO_INVCONTROL \"{dados['modo_texto']}\"")
    add("")
    add(f"#define N_VVCURVE {len(dados['vvc_x'])}")
    add("static const float VVCURVE_V[N_VVCURVE] = {")
    add(f"  {_formatar_vetor_float(dados['vvc_x'])}")
    add("};")
    add("static const float VVCURVE_Q[N_VVCURVE] = {")
    add(f"  {_formatar_vetor_float(dados['vvc_y'])}")
    add("};")
    add("")
    add(f"#define N_VWCURVE {len(dados['vw_x'])}")
    add("static const float VWCURVE_V[N_VWCURVE] = {")
    add(f"  {_formatar_vetor_float(dados['vw_x'])}")
    add("};")
    add("static const float VWCURVE_P[N_VWCURVE] = {")
    add(f"  {_formatar_vetor_float(dados['vw_y'])}")
    add("};")
    add("")
    add("/* -------- Interface física com o Mega (12 ligações, sem UART) ---- */")
    add(" * Um #define por fio. O mapa é o MESMO do param_microrrede.h:")
    add(" * ambos são gerados a partir de exportador_arduino.MAPA_LIGACOES.")
    add(" * O condicionamento de nível de cada fio está no comentário: os")
    add(" * divisores são EXTERNOS, não há nada deles no firmware.")
    add(" * PLACA_CONTROLE: ESP32 (3,3 V) — interface acondicionada para o")
    add(" * Arduino Mega 2560 R3 (lógica de 5 V). */")
    add(f'#define PLACA_CONTROLE '
        f'"ESP32 (3,3 V) — interface acondicionada para Mega 2560 R3"')
    for _lig in MAPA_LIGACOES:
        if not _lig["macro_esp32"]:
            continue
        _pino = PINO_NUMERICO_ESP32[_lig["n"]]
        add(f"#define {_lig['macro_esp32']:16s} ({_pino})"
            f"   /* ESP32 {_lig['esp32']:16s} <-> Mega {_lig['mega']:4s}: "
            f"{_lig['dados']} | {CONDICIONAMENTO[_lig['n']]} */")
    add("")
    add("/* Escalas da interface analógica (escolhas de projeto) ----------- */")
    add("/* O DAC do ESP32 entrega 0..3,3 V e o ADC do Mega lê 0..5 V: o")
    add(" * setpoint usa ~66% da faixa do ADC (resolução efetiva menor).")
    add(" * A saturação é do DAC (0..3,3 V), não do firmware: |P| > KW_RATING")
    add(" * ou |Q| > Q_LIM_KVAR já foram limitados antes da escrita. */")
    add(f"#define VPU_ANALOG_MAX "
        f"({VPU_ANALOG_MAX_PADRAO:.2f}f)")
    add(f"#define DAC_MIDRAIL_V  "
        f"({DAC_MIDRAIL_V_PADRAO:.2f}f)")
    add(f"#define VREF_MEGA_ADC  "
        f"({VREF_MEGA_ADC_PADRAO:.2f}f)")
    add(f"#define VREF_ESP32_DAC "
        f"({VREF_ESP32_DAC_PADRAO:.2f}f)")
    add(f"#define ADC_AMOSTRAS   {dados['adc_amostras']}")
    add(f"#define PWM_FILTRO_RC \"{FILTRO_RC_SUGERIDO}\"")
    add("")
    add("/* Condicionamento de nível — as resistências são EXTERNAS -------- */")
    add("/* O Mega 2560 R3 é lógica de 5 V e este ESP32 NÃO tolera 5 V nas")
    add(" * entradas. As 7 linhas Mega->ESP32 chegam JÁ DIVIDIDAS por")
    add(f" * {R_SERIE_DIV_OHMS/1000.0:.0f}k/{R_GND_DIV_OHMS/1000.0:.0f}k "
        f"(5,0 V -> 3,33 V); a do V_pu soma o filtro RC ANTES do divisor.")
    add(" * Conversão do V_pu (a leitura do ADC é feita em volts):")
    add(" *   v_pu = (v_esp / DIVISOR_VPU / MEGA_VCC_PWM) * VPU_PWM_MAX")
    add(" * Com v_esp = 2,78 V -> 2,78/0,6667/5,0 x 1,20 = 1,00 pu. */")
    add(f"#define DIVISOR_DIGITAL ({DIVISOR_LEVEL_PADRAO:.4f}f)")
    add(f"#define R_SERIE_DIV ({R_SERIE_DIV_OHMS:.1f}f)")
    add(f"#define R_GND_DIV ({R_GND_DIV_OHMS:.1f}f)")
    add(f"#define MEGA_VCC_PWM ({MEGA_VCC_PWM_V_PADRAO:.2f}f)")
    add(f"#define DIVISOR_VPU ({DIVISOR_LEVEL_PADRAO:.4f}f)")
    add(f"#define VPU_PWM_MAX ({VPU_ANALOG_MAX_PADRAO:.2f}f)")
    add("")
    add("/* ---------------- Telemetria IoT (v1: serial apenas) -------- */")
    add("/* WiFi/MQTT fora desta versão: SSID vazio desabilita o bloco no sketch. */")
    add(f"#define WIFI_SSID  \"{dados['wifi_ssid']}\"")
    add(f"#define WIFI_SENHA \"{dados['wifi_senha']}\"")
    add(f"#define TELEMETRIA_MS {dados['telemetria_ms']}")
    add("")
    add("#endif  /* PARAM_ESP32_H */")
    add("")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# API principal
# ---------------------------------------------------------------------------

def gerar_parametrizacao_esp32(projeto: Any, config_vencedora: Optional[dict],
                               caminho_saida: str,
                               grupo: Optional[str] = None,
                               tarifa_nome: str = "",
                               horario_ponta_inicio: int = PONTA_INICIO_PADRAO,
                               horario_ponta_fim: int = PONTA_FIM_PADRAO,
                               adc_amostras: int = ADC_AMOSTRAS_PADRAO,
                               telemetria_ms: int = 1000,
                               wifi_ssid: str = "",
                               wifi_senha: str = "") -> dict:
    """Gera ``param_esp32.h`` e devolve um dicionário de resultado/avisos.

    Parâmetros
    ----------
    projeto : objeto ``Projeto`` (usa ``caminho_rede_json``) ou caminho do
        ``rede.json``.
    config_vencedora : item da lista ``selecionados`` do estudo de
        otimização. Formato aceito:
        ``{"bus": "675", "modelo_bess": {...}, "kw": 300, "kwh": 1200}``
        (as três últimas formas são toleradas: ``kw``/``kwh`` diretos, ou
        aninhados em ``modelo_bess``).
    caminho_saida : caminho completo do ``param_esp32.h``.

    Levanta ``ValueError`` quando falta o que só o pesquisador pode fornecer
    (nenhuma alocação selecionada, barra ausente) — o chamador exibe a
    mensagem. Ausências MENORES (curva, kVA, Storage desenhado) NÃO
    interrompem: viram aviso em ``resultado["avisos"]`` e valor neutro.
    """
    avisos: List[str] = []

    # -------- validação do gatilho (após a otimização) -------- #
    if not config_vencedora:
        raise ValueError(
            "Nenhuma alocação selecionada pelo estudo de otimização. "
            "A parametrização do ESP32 é gerada APÓS a otimização do Sistema "
            "BESS — conclua o estudo com ao menos uma alocação vencedora."
        )

    barra = str(config_vencedora.get("bus", "") or "").strip()
    if not barra:
        raise ValueError(
            "A configuração vencedora não informa a barra do BESS "
            "(chave 'bus'). Refaça o estudo de otimização."
        )

    modelo = config_vencedora.get("modelo_bess") or {}
    kw = _to_float(config_vencedora.get("kw", modelo.get("kw")), 0.0)
    kwh = _to_float(config_vencedora.get("kwh", modelo.get("kwh")), 0.0)
    if kw <= 0 or kwh <= 0:
        raise ValueError(
            f"A configuração vencedora da barra '{barra}' não traz potência "
            f"e/ou energia válidas (kW={kw}, kWh={kwh}). Refaça o estudo."
        )

    # -------- rede do projeto: Storage/InvControl/curvas -------- #
    rede = _carregar_rede(projeto)
    if rede is None:
        avisos.append(
            "rede.json não encontrado/ilegível: as curvas Volt-Var/Volt-Watt e "
            "o kVA do inversor NÃO puderam ser lidos do projeto. O controle de "
            "reativa foi emitido como INERTE (Q = 0)."
        )

    nome_grupo, storage, invcontrol = _localizar_sistema_bess(rede, barra, grupo)
    if rede is not None:
        if storage is None:
            avisos.append(
                "Nenhum elemento Storage encontrado no rede.json: a "
                "parametrização usa apenas a configuração vencedora do estudo; "
                "curvas e kVA ficam neutros."
            )
        elif storage.bus1 and str(storage.bus1) != barra:
            avisos.append(
                f"O Storage '{storage.nome}' do projeto está na barra "
                f"'{storage.bus1}', mas a alocação vencedora é na barra "
                f"'{barra}'. Aplicada a barra vencedora (é a que o otimizador "
                f"avaliou); revise o projeto se isso não for intencional."
            )
        if storage is not None and invcontrol is None:
            avisos.append(
                "Storage sem InvControl associado no mesmo grupo: o despacho de "
                "REATIVA fica inerte (sem curva Volt-Var/Volt-Watt). O despacho "
                "de ativa permanece válido."
            )

    params_storage = getattr(storage, "parametros", {}) or {} if storage else {}
    params_inv = getattr(invcontrol, "parametros", {}) or {} if invcontrol else {}

    kva = _to_float(params_storage.get("kva"), 0.0)
    if kva <= 0:
        avisos.append(
            "kVA do inversor não declarado no Storage: adotado kVA = kW "
            f"({kw:.3f} kVA). Consequência prática: o limite de reativa "
            "Q = sqrt(kVA² − kW²) fica ZERO e o controle Volt-Var não tem "
            "margem. Declare o kVA no Editor de Rede para o experimento ser útil."
        )
        kva = kw
    q_lim = max(0.0, (kva * kva - kw * kw) ** 0.5)

    soc_min = _to_float(params_storage.get("socmin"), SOC_MIN_PADRAO)
    soc_max = _to_float(params_storage.get("socmax"), SOC_MAX_PADRAO)
    soc_ini_bruto = _to_float(params_storage.get("pctstored"), SOC_INICIAL_PADRAO * 100.0)
    # O Editor grava %STORED em porcentagem (50); os módulos de simulação
    # usam fração (0,5). Normaliza como _normalizar_soc de economia_energia.
    soc_inicial = soc_ini_bruto / 100.0 if soc_ini_bruto > 1.5 else soc_ini_bruto
    if not (0.0 < soc_min < soc_max <= 1.0):
        avisos.append(
            f"Limites de SoC incoerentes no projeto (min={soc_min}, "
            f"max={soc_max}); adotados os padrões dos módulos de simulação "
            f"({SOC_MIN_PADRAO} / {SOC_MAX_PADRAO})."
        )
        soc_min, soc_max = SOC_MIN_PADRAO, SOC_MAX_PADRAO
    if not (soc_min <= soc_inicial <= soc_max):
        avisos.append(
            f"SoC inicial ({soc_inicial:.3f}) fora da faixa operacional "
            f"[{soc_min:.2f}, {soc_max:.2f}]; ajustado para dentro da faixa."
        )
        soc_inicial = min(max(soc_inicial, soc_min), soc_max)

    # -------- curvas de reativa -------- #
    usa_voltv, usa_voltwatt = _modo_invcontrol(params_inv)
    vvc_x, vvc_y, vvc_ok = _extrair_curva(rede, params_inv.get("vvc_curve1"))
    vw_x, vw_y, vw_ok = _extrair_curva(rede, params_inv.get("voltwatt_curve"))
    if usa_voltv and not vvc_ok:
        avisos.append(
            "Curva Volt-Var (vvc_curve1) não encontrada no projeto: controle de "
            "reativa emitido INERTE (Q = 0 em toda a faixa)."
        )
    if usa_voltwatt and not vw_ok:
        avisos.append(
            "Curva Volt-Watt (voltwatt_curve) não encontrada no projeto: "
            "curtailment de ativa emitido INERTE (fator = 1)."
        )
    if not usa_voltv and not usa_voltwatt:
        avisos.append(
            "O InvControl do projeto não declara Mode/CombiMode reconhecido: "
            "nenhum bloco de reativa foi habilitado no firmware."
        )

    modo_texto = str(params_inv.get("CombiMode") or params_inv.get("Mode") or "NENHUM")

    # -------- tabela de despacho (regra dos módulos) -------- #
    estados, soc_por_hora = _simular_soc_da_tabela(
        kw, kwh, soc_min, soc_max, soc_inicial,
        horario_ponta_inicio, horario_ponta_fim)
    despacho_kw = [
        (kw if estado != ESTADO_IDLING else 0.0) for estado in estados
    ]

    # Índice da barra no rede.json. NÃO é mais usado para endereçar
    # mensagens (não há protocolo serial), mas é emitido para o log de
    # bancada conferir que o cabeçalho corresponde à rede certa.
    indice_barra = -1
    if rede is not None:
        indice_barra = sorted(getattr(rede, "barras", {}).keys()).index(barra) \
            if barra in getattr(rede, "barras", {}) else -1
    if indice_barra < 0:
        avisos.append(
            f"A barra '{barra}' não está nas barras do rede.json: BESS_BUS_IDX "
            "emitido como -1 (apenas informativo no log de bancada). "
            "Confira se o cabeçalho pertence à rede correta."
        )

    nome_projeto = ""
    if isinstance(projeto, str):
        nome_projeto = os.path.basename(os.path.dirname(projeto))
    else:
        nome_projeto = str(getattr(projeto, "nome", "") or "")

    dados = {
        "projeto": nome_projeto or "(não informado)",
        "tarifa": tarifa_nome,
        "nome_sistema": nome_grupo or (getattr(storage, "nome", "") if storage else "") or "BESS",
        "barra": barra,
        "indice_barra": indice_barra,
        "kw_rating": kw,
        "kwh_rating": kwh,
        "kva_inversor": kva,
        "q_lim_kvar": q_lim,
        "soc_min": soc_min,
        "soc_max": soc_max,
        "soc_inicial": soc_inicial,
        "ponta_inicio": horario_ponta_inicio,
        "ponta_fim": horario_ponta_fim,
        "despacho_estado": estados,
        "despacho_kw": despacho_kw,
        "soc_por_hora": soc_por_hora,
        "usa_voltv": usa_voltv,
        "usa_voltwatt": usa_voltwatt,
        "modo_texto": modo_texto,
        "vvc_x": vvc_x,
        "vvc_y": vvc_y,
        "vw_x": vw_x,
        "vw_y": vw_y,
        "adc_amostras": max(1, int(adc_amostras)),
        "telemetria_ms": int(telemetria_ms),
        "wifi_ssid": str(wifi_ssid or ""),
        "wifi_senha": str(wifi_senha or ""),
    }

    conteudo = _montar_cabecalho(dados)

    pasta = os.path.dirname(os.path.abspath(caminho_saida))
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    with open(caminho_saida, "w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(conteudo)

    return {
        "caminho": caminho_saida,
        "kw_rating": kw,
        "kwh_rating": kwh,
        "kva_inversor": kva,
        "q_lim_kvar": q_lim,
        "soc_min": soc_min,
        "soc_max": soc_max,
        "soc_inicial": soc_inicial,
        "despacho_estado": estados,
        "soc_por_hora": soc_por_hora,
        "usa_voltv": usa_voltv,
        "usa_voltwatt": usa_voltwatt,
        "pontos_vvc": len(vvc_x),
        "pontos_vw": len(vw_x),
        "avisos": avisos,
    }


def gerar_parametrizacao_esp32_do_resultado(projeto: Any, resultado_otimizacao: dict,
                                            caminho_saida: str, **kwargs) -> dict:
    """Variante que consome diretamente o dicionário devolvido por
    ``otimizacao_bess.executar_estudo_completo`` (``resultado["selecionados"]``).

    Usa a PRIMEIRA alocação selecionada como a alocação de referência do
    firmware. Se houver mais de uma, registra aviso: o sketch pré-pronto
    controla UM Sistema BESS; múltiplas unidades exigem múltiplos ESP32,
    decisão de projeto que não é tomada aqui.
    """
    selecionados = (resultado_otimizacao or {}).get("selecionados") or []
    if not selecionados:
        raise ValueError(
            "O estudo de otimização não selecionou nenhuma alocação de BESS. "
            "Não há Sistema BESS para parametrizar. Ajuste os parâmetros do "
            "estudo (peso de custo, restrições) e refaça a otimização."
        )

    resultado = gerar_parametrizacao_esp32(
        projeto, selecionados[0], caminho_saida, **kwargs)

    if len(selecionados) > 1:
        barras = ", ".join(str(c.get("bus", "?")) for c in selecionados)
        resultado["avisos"].append(
            f"O estudo selecionou {len(selecionados)} BESS ({barras}); a "
            f"parametrização foi gerada para a alocação '{selecionados[0].get('bus')}'. "
            "O sketch pré-pronto controla UM Sistema BESS — as demais unidades "
            "exigem firmware/ESP32 adicionais."
        )
    return resultado


def caminho_padrao_param_esp32(projeto: Any) -> str:
    """``<raiz_projeto>/hardware/param_esp32.h``.

    A raiz é a pasta do projeto (``Projeto.caminho_raiz``), a mesma que
    contém ``rede/``, ``curvas/`` e ``dimensionamento/`` — o diretório
    ``hardware/`` nasce ao lado delas. É deliberadamente DENTRO do projeto:
    a parametrização de um ensaio pertence àquele projeto, não ao repositório
    (o sketch pré-pronto é que fica versionado no repositório).
    """
    if isinstance(projeto, str):
        alvo = os.path.abspath(projeto)
        # Se apontarem para o rede.json, a raiz é o avô dele.
        if os.path.isfile(alvo) or alvo.endswith(".json"):
            alvo = os.path.dirname(os.path.dirname(alvo))
        raiz = alvo
    else:
        raiz = getattr(projeto, "caminho_raiz", None)
        if not raiz:
            caminho_rede = _resolver_caminho_rede(projeto)
            raiz = os.path.dirname(os.path.dirname(caminho_rede)) if caminho_rede else os.getcwd()
    return os.path.join(str(raiz), "hardware", "param_esp32.h")
