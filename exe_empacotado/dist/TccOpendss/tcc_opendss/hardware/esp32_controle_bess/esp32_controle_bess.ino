/*
 * esp32_controle_bess.ino — CONTROLADOR do Sistema BESS (sketch PRÉ-PRONTO)
 * ============================================================================
 *
 * PAPEL NO EXPERIMENTO
 * --------------------
 * Este é o firmware do ESP32 que ATUA sobre a microrede: despacha potência
 * ATIVA (arbitragem tarifária, pelo SoC e pela tabela horária) e potência
 * REATIVA (qualidade de energia, pela curva Volt-Var/Volt-Watt do sistema de
 * armazenamento já desenvolvido no TCC). A placa constrói a rede adjacente e
 * informa medições — ela MEDE, este ESP32 ATUA. O efeito da atuação é visto
 * na leitura de tensão que o Arduino envia.
 *
 * ESTE ARQUIVO É FIXO E VERSIONADO NO REPOSITÓRIO.
 * Ele NÃO é regerado a cada projeto. Todos os valores do projeto vivem em
 *   #include "param_esp32.h"
 * que é GERADO por `bibliotecas/exportador_esp32.py` a partir do resultado do
 * estudo de otimização de alocação de BESS (janela de resultados da
 * Otimização → botão "Exportar parametrização ESP32"). Se você editar valores
 * de projeto AQUI, eles serão mascarados na próxima geração e o experimento
 * deixa de corresponder ao estudo — não faça isso.
 *
 * INTERFACE COM O MEGA — 12 LIGAÇÕES DIRETAS DIGITAIS E ANALÓGICAS
 * ----------------------------------------------------------------
 *  NÃO há UART entre as placas. São fios ponto a ponto; cada placa tem
 *  alimentação INDEPENDENTE e apenas o GND em comum (referência de sinal).
 *
 *    ESP32 GPIO 25 (DAC1) <-> Arduino Mega A0 (Dados: setpoint de P)
 *    ESP32 GPIO 26 (DAC2) <-> Arduino Mega A1 (Dados: setpoint de Q)
 *    ESP32 GPIO 27        <-> Arduino Mega D9 (Dados: estado do BESS, bit 0)
 *    ESP32 GPIO 14        <-> Arduino Mega D10 (Dados: estado do BESS, bit 1)
 *    ESP32 GPIO 36 (ADC)  <-> Arduino Mega D8 (Dados: V_pu da barra do BESS)
 *    ESP32 GPIO 23        <-> Arduino Mega D2 (Dados: hora, bit 0)
 *                   ... até D6 / GPIO 18 (hora, bit 4)
 *    ESP32 GPIO 5         <-> Arduino Mega D7 (Dados: tick de hora)
 *    GND                  <-> GND (referência comum)
 *
 *  Todos os pinos vêm de #define do `param_esp32.h`. Nenhum número de pino
 *  é escrito à mão neste arquivo.
 *
 *  ESTE LADO DO ENLACE
 *  -------------------
 *  - Relógio: o Mega mantém 5 bits da hora em paralelo e pulsa o TICK. Aqui
 *    basta detectar a borda de subida do tick e ler os 5 bits — sem
 *    protocolo, sem timeout e sem ressincronização: perdido um tick, o
 *    próximo traz a hora certa.
 *  - Medição: o Mega escreve o V_pu da barra do BESS num PWM filtrado por
 *    RC no D8; aqui se lê o GPIO 36 (ADC1/VP) e se converte
 *    V_pu = (v_esp / DIVISOR_VPU / MEGA_VCC_PWM) × VPU_PWM_MAX, onde
 *    v_esp é a leitura do ADC em volts. O DIVISOR 10k/20k é EXTERNO e
 *    existe porque o Mega 2560 R3 tem lógica de 5 V (ver `ler_v_pu`).
 *  - Atuação: P e Q saem como tensão nos DACs (GPIO 25/26). Zero é o
 *    MID-RAIL (DAC_MIDRAIL_V = 1,65 V); acima injeta, abaixo absorve.
 *    O DAC do ESP32 tem 8 bits e fundo de escala 3,3 V: o valor escrito é
 *    (V/3,3)×255, saturado em 0..255. Como |P| <= KW_RATING e
 *    |Q| <= Q_LIM_KVAR são limitados antes, a saturação do DAC só ocorre
 *    se o Q_LIM exceder a meia-faixa — daí a mensagem de aviso no setup().
 *  - Estado do BESS: 2 bits em GPIO 27/14 (00 repouso, 01 carregando,
 *    10 descarregando, 11 reservado). Redundante de propósito: permite ao
 *    Mega conferir a coerência entre o fio analógico e o digital.
 *
 * TRANSPARÊNCIA TÉCNICA (declarada, não escondida)
 * -----------------------------------------------
 * 1) As curvas Volt-Var/Volt-Watt vêm do InvControl DO PROJETO (XYCurve do
 *    rede.json). Curvas típicas de norma (ex.: IEEE 1547-2018 Cat B) NÃO são
 *    confirmadas para um projeto real — por isso não há valores default aqui.
 *    O firmware faz INTERPOLAÇÃO LINEAR; outros parâmetros do InvControl
 *    (RefReactivePower, VoltWattCH_Curve, dinâmica de atuação) NÃO são
 *    replicados.
 * 2) O SoC é integrado LOCALMENTE (P×Δt / energia nominal). Um BMS real
 *    informa o SoC por outro caminho (CAN/Modbus). O SoC daqui serve ao
 *    experimento; NÃO é um substituto do BMS.
 * 3) O despacho reproduz a REGRA de simulação do TCC (ponta -> descarrega,
 *    fora de ponta -> carrega, bloqueando nos limites de SoC). A tabela
 *    DESPACHO_ESTADO[] é a observação da simulação; a decisão efetiva é
 *    reavaliada aqui a cada hora com o SoC local — a regra é fechada em malha
 *    e, se o SoC saturar, o estado vira IDLING, como no OpenDSS.
 * 4) WiFi/MQTT está FORA desta versão. `WIFI_SSID` vazio desabilita o bloco;
 *    a telemetria de v1 é JSON 1 Hz pela USB Serial.
 * 5) As magnitudes de P/Q enviadas ao Mega (frame "C") são um SETPOINT para a
 *    eletrônica de potência do ensaio; este firmware não aciona IGBTs nem
 *    fecha laço de corrente em hardware real.
 *
 * PENDÊNCIA CONHECIDA: este sketch NÃO foi compilado nesta máquina (sem
 * arduino-cli/IDE ESP32 disponível). A compilação e o upload são passo do
 * pesquisador na IDE do Arduino com o core ESP32 instalado.
 */

#include "param_esp32.h"

// ---------------------------------------------------------------------------
// Pinos da interface física (todos vêm do param_esp32.h)
// ---------------------------------------------------------------------------
// Nenhum pino é escrito à mão: o cabeçalho é gerado do mapa canônico em
// exportador_arduino.MAPA_LIGACOES, o MESMO que gera o param_microrrede.h.
// Se os dois cabeçalhos divergirem, a bancada não funciona — por isso os dois
// saem da mesma fonte.

// Formato de printf usado na telemetria: %ld com (long), %u com uint8_t
// promovido. Evita o UB de passar int32_t a %d (int32_t é `int` no ESP32,
// mas em outras toolchains pode diferir — o cast explícito elimina a dúvida).

// Faixa de aquisição do SoC local (fração 0..1) — sanidade do integrador.
static const float SOC_FISICO_MIN = 0.0f;
static const float SOC_FISICO_MAX = 1.0f;

// Fator de Volt-Watt do ciclo corrente (1.0 = sem curtailment). Fica fora de
// calcular_reativa() para que a INTEGRAÇÃO DO SoC use o P efetivamente
// entregue: se a curva Volt-Watt corta a ativa, a bateria carrega/descarrega
// menos e o SoC não pode avançar como se a potência cheia tivesse passado.
static float fator_voltwatt = 1.0f;

// ---------------------------------------------------------------------------
// Estado global
// ---------------------------------------------------------------------------
struct EstadoRede {
  int32_t dia = 1;          // 1 = primeiro dia do ensaio
  int32_t hora = 0;         // 0..23
  int32_t frac = 0;         // sempre 0: a hora é publicada em degraus de 1 h
  bool clock_valido = false;
  uint32_t millis_ultimo_tick = 0;   // último tick recebido / contador local
  uint8_t nivel_tick_anterior = 0;   // para detectar a BORDA DE SUBIDA
};

EstadoRede rede;

// Última medição do V_pu da barra do BESS (0 = sem medição plausível).
float v_pu_bess = 0.0f;
uint32_t millis_ultima_medicao = 0;
static const uint32_t TIMEOUT_MEDICAO_MS = 5000;

// SoC integrado localmente.
float soc = SOC_INICIAL;

// Estado de despacho corrente e saídas.
uint8_t estado_despacho = 0;   // 0=IDLING 1=CHARGING 2=DISCHARGING
float p_kw = 0.0f;
float q_kvar = 0.0f;

uint32_t millis_ultima_telemetria = 0;
uint32_t millis_ultimo_passo_soc = 0;

// ---------------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------------

// Interpolação LINEAR sobre curva ordenada por tensão. Fora da faixa,
// satura no primeiro/último ponto (é o comportamento do InvControl do
// OpenDSS: a curva define a característica dentro dos pontos declarados).
float interpolar(const float *xs, const float *ys, int n, float x) {
  if (n <= 0) return 0.0f;
  if (n == 1) return ys[0];
  if (x <= xs[0]) return ys[0];
  if (x >= xs[n - 1]) return ys[n - 1];

  for (int i = 1; i < n; i++) {
    if (x <= xs[i]) {
      float x0 = xs[i - 1];
      float x1 = xs[i];
      if (x1 == x0) return ys[i];
      float t = (x - x0) / (x1 - x0);
      return ys[i - 1] + t * (ys[i] - ys[i - 1]);
    }
  }
  return ys[n - 1];
}

bool hora_de_ponta(int hora) {
  // Intervalo com fim EXCLUSIVO, igual a economia_energia._eh_hora_ponta
  // (suporta janela que cruza a meia-noite).
  if (PONTA_INICIO <= PONTA_FIM) {
    return (hora >= PONTA_INICIO) && (hora < PONTA_FIM);
  }
  return (hora >= PONTA_INICIO) || (hora < PONTA_FIM);
}

// ---------------------------------------------------------------------------
// Decisão de despacho (ATIVA)
// ---------------------------------------------------------------------------
void atualizar_estado_despacho() {
  // REGRA IDÊNTICA a economia_energia._simular_dia / ao_vivo_engine:
  //   ponta      e soc > SOC_MIN  -> DISCHARGING
  //   fora ponta e soc < SOC_MAX  -> CHARGING
  //   caso contrário              -> IDLING
  // Com SOC_MIN/SOC_MAX vindos do cabeçalho, um projeto configurado fora
  // da faixa simplesmente nunca satura — o que é a verdade, não um erro.
  bool ponta = hora_de_ponta(rede.hora);

  if (ponta && soc > SOC_MIN) {
    estado_despacho = 2;
  } else if (!ponta && soc < SOC_MAX) {
    estado_despacho = 1;
  } else {
    estado_despacho = 0;
  }

  switch (estado_despacho) {
    case 2:  p_kw = +KW_RATING; break;   // descarrega (injeta)
    case 1:  p_kw = -KW_RATING; break;   // carrega  (absorve)
    default: p_kw = 0.0f;        break;
  }

  // O despacho base é recalculado a cada ciclo; o curtailment de Volt-Watt é
  // reaplicado em calcular_reativa() sobre este valor.
  fator_voltwatt = 1.0f;
}

// Integra o SoC local com o estado corrente. O passo de integração é o
// tempo REAL decorrido (não a hora do frame), evitando erro se um tick se
// atrasar.
void integrar_soc(float dt_horas) {
  if (KWH_RATING <= 0.0f) return;   // sem energia nominal não há integração
  float delta = (p_kw * dt_horas) / KWH_RATING;
  soc += delta;
  if (soc < SOC_FISICO_MIN) soc = SOC_FISICO_MIN;
  if (soc > SOC_FISICO_MAX) soc = SOC_FISICO_MAX;
}

// ---------------------------------------------------------------------------
// Controle de REATIVA (qualidade de energia)
// ---------------------------------------------------------------------------
void calcular_reativa() {
  q_kvar = 0.0f;

  bool medicao_ok = (v_pu_bess > 0.0f) &&
                    ((millis() - millis_ultima_medicao) < TIMEOUT_MEDICAO_MS);

#if USA_VOLTWATT
  // Volt-Watt: reduz a ATIVA quando a tensão sobe (curtailment). Aplicado
  // sobre o despacho já fixado por atualizar_estado_despacho(). O fator fica
  // em `fator_voltwatt` para a integração do SoC usar o P efetivo.
  if (medicao_ok) {
    float fator = interpolar(VWCURVE_V, VWCURVE_P, N_VWCURVE, v_pu_bess);
    if (fator < 0.0f) fator = 0.0f;
    if (fator > 1.0f) fator = 1.0f;
    fator_voltwatt = fator;
  }
  p_kw *= fator_voltwatt;
#endif

#if USA_VOLTVAR
  // Sem medição fresca da barra do BESS, atuar seria atuar às cegas: fica em
  // Q = 0 e o operador vê isso na telemetria ("med":0).
  if (medicao_ok) {
    float q_pu = interpolar(VVCURVE_V, VVCURVE_Q, N_VVCURVE, v_pu_bess);
    // Convenção: q_pu > 0 = capacitiva (injeta reativo na rede);
    // q_pu < 0 = indutiva (absorve). É a convenção das curvas Volt-Var
    // típicas (tensão baixa -> injeta) e a do frame "C" (+ = injeção).
    q_kvar = q_pu * Q_LIM_KVAR;
  }
#endif

  // Limite físico do INVERSOR, não da curva: |Q| <= Q_LIM_KVAR e, junto com
  // P, dentro da aparente (|S| <= KVA_INVERSOR). A segunda restrição importa
  // porque a curva pode pedir Q máximo enquanto P também está máximo — o
  // inversor não entrega os dois ao mesmo tempo.
  float q_max_curva = Q_LIM_KVAR;

  // Limita Q pela margem aparente remanescente: sqrt(S² - P²).
  float margem = (KVA_INVERSOR * KVA_INVERSOR) - (p_kw * p_kw);
  if (margem > 0.0f) {
    float q_margem = sqrtf(margem);
    if (q_margem < q_max_curva) q_max_curva = q_margem;
  } else {
    q_max_curva = 0.0f;   // inversor sem margem: P consome toda a aparente
  }

  if (q_kvar > q_max_curva) q_kvar = q_max_curva;
  if (q_kvar < -q_max_curva) q_kvar = -q_max_curva;
}

// ---------------------------------------------------------------------------
// Leitura do relógio do Mega: 5 bits em paralelo + pulso de TICK
// ---------------------------------------------------------------------------
// O tick é lido por BORDA DE SUBIDA, não por nível: assim o firmware não
// confunde "hora não mudou" com "hora nova com os mesmos bits" (o que
// acontece de hora em hora, ex.: dois ticks com a mesma contagem em dias
// diferentes nunca ocorrem, mas no mesmo dia os bits mudam sempre — a borda
// torna a lógica independente dessa sutileza).
// ---------------------------------------------------------------------------
uint8_t ler_bits_hora() {
  uint8_t h = 0;
  if (digitalRead(PINO_HORA_IN0)) h |= 0x01;
  if (digitalRead(PINO_HORA_IN1)) h |= 0x02;
  if (digitalRead(PINO_HORA_IN2)) h |= 0x04;
  if (digitalRead(PINO_HORA_IN3)) h |= 0x08;
  if (digitalRead(PINO_HORA_IN4)) h |= 0x10;
  return h;
}

void processar_tick() {
  uint8_t h = ler_bits_hora();
  if (h > 23) {
    // 5 bits comportam 0..31, mas só 0..23 são válidos. Um valor fora disso
    // significa fio solto/ruído: mantém a hora anterior e reporta, em vez de
    // saltar para um horário impossível.
    Serial.printf("AVISO: hora invalida %u nos bits de entrada (fio solto?)\n",
                  (unsigned)h);
    return;
  }

  bool trocou_hora = (h != (uint8_t)rede.hora);
  rede.hora = h;
  rede.frac = 0;
  rede.clock_valido = true;
  rede.millis_ultimo_tick = millis();

  // Meia-noite: o Mega incrementa o dia e volta a hora a 0. Aqui só se
  // conta o dia (o dia da semana é derivado pelo Mega; o ESP32 não precisa).
  if (trocou_hora && h == 0) {
    rede.dia++;
  }

  // A regra de despacho depende da hora (ponta) e do SoC, que mudou desde a
  // hora anterior: reavaliar aqui é o que fecha a malha.
  if (trocou_hora) {
    atualizar_estado_despacho();
    Serial.printf("[%02ldh] despacho=%u p=%.2f kW soc=%.1f pct\n",
                  (long)rede.hora, (unsigned)estado_despacho, p_kw,
                  soc * 100.0f);
  }
}

void ler_relogio() {
  uint8_t nivel = (uint8_t)digitalRead(PINO_TICK_IN);
  if (nivel && !rede.nivel_tick_anterior) {
    processar_tick();          // borda de subida
  }
  rede.nivel_tick_anterior = nivel;
}

// ---------------------------------------------------------------------------
// Medição do V_pu da barra do BESS (ADC no GPIO 36)
// ---------------------------------------------------------------------------
// O Mega entrega a tensão num PWM filtrado por RC. A leitura é a MÉDIA de
// ADC_AMOSTRAS conversões: o filtro RC não é ideal e o PWM tem ondulação
// residual; a média reduz o ruído sem custar nada.
//
// CONDICIONAMENTO EXTERNO: antes do GPIO 36 há um DIVISOR 10k/20k
// (DIVISOR_VPU), porque o Mega 2560 R3 trabalha em 5 V e este ESP32 não
// tolera 5 V nas entradas. O divisor reduz 5,0 V para 3,33 V — logo a
// tensão que o Mega REALMENTE escreveu vale V_mega = v_esp / DIVISOR_VPU,
// e o V_pu correspondente é proporcional a ela:
//
//   v_esp  = leitura/4095 × VREF_ESP32_DAC           (volts no pino)
//   v_mega = v_esp / DIVISOR_VPU                     (volts antes do divisor)
//   V_pu   = v_mega / MEGA_VCC_PWM × VPU_PWM_MAX     (fundo de escala do PWM)
//
// Com v_esp = 2,78 V: 2,78/0,6667 = 4,17 V no Mega -> 4,17/5,0 × 1,20 =
// 1,00 pu. As três constantes vêm do param_esp32.h; nenhum valor é escrito
// à mão aqui.
// ---------------------------------------------------------------------------
float ler_v_pu() {
  long soma = 0;
  for (int i = 0; i < ADC_AMOSTRAS; i++) {
    soma += analogRead(PINO_VPU_ADC);
  }
  float leitura = (float)soma / (float)ADC_AMOSTRAS;
  float v_esp = (leitura / 4095.0f) * VREF_ESP32_DAC;
  return (v_esp / DIVISOR_VPU / MEGA_VCC_PWM) * VPU_PWM_MAX;
}

void medir_tensao() {
  float v = ler_v_pu();
  // V_pu abaixo de ~0,5 significa "sem sinal" (fio solto ou Mega com BESS_BUS
  // = -1 escrevendo 0 V). Não inventa medição: v_pu_bess fica em 0 e o
  // controle de reativa se mantém inerte, com a telemetria mostrando med=0.
  if (v < 0.5f) {
    v_pu_bess = 0.0f;
    return;
  }
  v_pu_bess = v;
  millis_ultima_medicao = millis();
}

// ---------------------------------------------------------------------------
// Atuação: P/Q nos DACs + estado em dois fios digitais
// ---------------------------------------------------------------------------
// O DAC é de 8 bits com fundo de escala 3,3 V. A tensão desejada é
//     V = DAC_MIDRAIL_V + (grandeza / escala) × DAC_MIDRAIL_V
// e o valor escrito, (V / VREF_ESP32_DAC) × 255.
// Sinal: positivo INJETA (V acima do mid-rail), negativo ABSORVE (abaixo).
//
// SATURAÇÃO: se |grandeza| > escala, V sai da faixa 0..3,3 V e é grampeada
// em 0 ou 255. Isso NÃO deve ocorrer em operação normal (P já é limitado a
// KW_RATING e Q a Q_LIM_KVAR); quando ocorre, o Serial mostra o valor
// efetivo ao lado do pretendido na telemetria, o que denuncia o erro de
// parametrização em vez de escondê-lo.
// ---------------------------------------------------------------------------
uint8_t tensao_para_dac(float v) {
  if (v <= 0.0f) return 0;
  if (v >= VREF_ESP32_DAC) return 255;
  return (uint8_t)((v / VREF_ESP32_DAC) * 255.0f + 0.5f);
}

void escrever_atuacao() {
  float escala_p = (KW_RATING > 0.0f) ? KW_RATING : 0.0f;
  float escala_q = (Q_LIM_KVAR > 0.0f) ? Q_LIM_KVAR : 0.0f;

  float v_p = DAC_MIDRAIL_V;
  if (escala_p > 0.0f) {
    v_p = DAC_MIDRAIL_V + (p_kw / escala_p) * DAC_MIDRAIL_V;
  }
  dacWrite(PINO_P_DAC, tensao_para_dac(v_p));

  float v_q = DAC_MIDRAIL_V;
  if (escala_q > 0.0f) {
    v_q = DAC_MIDRAIL_V + (q_kvar / escala_q) * DAC_MIDRAIL_V;
  }
  dacWrite(PINO_Q_DAC, tensao_para_dac(v_q));

  // Estado em 2 bits: redundante com o sinal analógico, de propósito — o
  // Mega usa para conferir coerência e para diagnóstico de fio solto.
  digitalWrite(PINO_ESTADO0, (estado_despacho & 0x01) ? HIGH : LOW);
  digitalWrite(PINO_ESTADO1, (estado_despacho & 0x02) ? HIGH : LOW);
}

// ---------------------------------------------------------------------------
// Telemetria (JSON 1 Hz pela USB Serial) — pronta para o dashboard IoT
// ---------------------------------------------------------------------------
void enviar_telemetria() {
  // p_kw/q_kvar são os SETPOINTS EFETIVOS (já limitados por Volt-Watt e pela
  // margem aparente); v_p/v_q são as tensões correspondentes escritas nos
  // DACs — conferir uma contra a outra é o teste mais rápido de fio trocado
  // na bancada.
  float escala_p = (KW_RATING > 0.0f) ? KW_RATING : 0.0f;
  float escala_q = (Q_LIM_KVAR > 0.0f) ? Q_LIM_KVAR : 0.0f;
  float v_p = (escala_p > 0.0f)
                  ? DAC_MIDRAIL_V + (p_kw / escala_p) * DAC_MIDRAIL_V
                  : DAC_MIDRAIL_V;
  float v_q = (escala_q > 0.0f)
                  ? DAC_MIDRAIL_V + (q_kvar / escala_q) * DAC_MIDRAIL_V
                  : DAC_MIDRAIL_V;

  Serial.printf(
      "{\"dia\":%ld,\"hora\":%ld,\"v_pu\":%.4f,\"p_kw\":%.2f,\"q_kvar\":%.2f,"
      "\"v_p\":%.3f,\"v_q\":%.3f,"
      "\"soc\":%.3f,\"med\":%d,\"clock\":%d,\"estado\":%u}\n",
      (long)rede.dia, (long)rede.hora, v_pu_bess, p_kw, q_kvar, v_p, v_q, soc,
      (millis() - millis_ultima_medicao < TIMEOUT_MEDICAO_MS) ? 1 : 0,
      rede.clock_valido ? 1 : 0, (unsigned)estado_despacho);
}

// ---------------------------------------------------------------------------
// Arduino
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);       // USB: telemetria JSON para o PC/dashboard

  // ---- Interface física com o Mega (ver o cabeçalho do arquivo) ---------
  // Entradas do Mega: hora em 5 bits + tick.
  pinMode(PINO_HORA_IN0, INPUT);
  pinMode(PINO_HORA_IN1, INPUT);
  pinMode(PINO_HORA_IN2, INPUT);
  pinMode(PINO_HORA_IN3, INPUT);
  pinMode(PINO_HORA_IN4, INPUT);
  pinMode(PINO_TICK_IN, INPUT);

  // ADC do V_pu: atenuação de 11 dB = faixa 0..3,3 V, casando com a escala
  // do VPU_ANALOG_MAX. Sem essa atenuação o ADC satura em ~1,1 V e todas as
  // tensões lidas acima de 40% do fundo de escala viriam erradas.
  analogReadResolution(12);
  analogSetPinAttenuation(PINO_VPU_ADC, ADC_11db);

  // DACs: 8 bits (padrão do core ESP32, declarado por clareza).
  dacWrite(PINO_P_DAC, tensao_para_dac(DAC_MIDRAIL_V));
  dacWrite(PINO_Q_DAC, tensao_para_dac(DAC_MIDRAIL_V));

  // Estado do BESS: saídas.
  pinMode(PINO_ESTADO0, OUTPUT);
  pinMode(PINO_ESTADO1, OUTPUT);
  digitalWrite(PINO_ESTADO0, LOW);
  digitalWrite(PINO_ESTADO1, LOW);

  rede.nivel_tick_anterior = (uint8_t)digitalRead(PINO_TICK_IN);

  soc = SOC_INICIAL;
  atualizar_estado_despacho();

  millis_ultimo_passo_soc = millis();
  millis_ultima_telemetria = millis();
  millis_ultima_medicao = 0;

  Serial.println();
  Serial.println("=== ESP32 — Controle do Sistema BESS ===");
  Serial.printf("BESS '%s' na barra '%s' (idx %d)\n", BESS_NOME, BESS_BUS, BESS_BUS_IDX);
  Serial.printf("P nominal: %.1f kW | E: %.1f kWh | Q_lim: %.1f kvar\n",
                KW_RATING, KWH_RATING, Q_LIM_KVAR);
  Serial.printf("SoC inicial: %.0f pct (faixa %.0f pct .. %.0f pct)\n",
                SOC_INICIAL * 100.0f, SOC_MIN * 100.0f, SOC_MAX * 100.0f);
  Serial.printf("InvControl: %s (VoltVar=%d, VoltWatt=%d)\n",
                MODO_INVCONTROL, USA_VOLTVAR, USA_VOLTWATT);
  Serial.printf("Ponta: %02dH .. %02dH\n", PONTA_INICIO, PONTA_FIM);

#if defined(WIFI_SSID) && defined(WIFI_SENHA)
  if (strlen(WIFI_SSID) > 0) {
    Serial.println("WiFi: SSID configurado, mas MQTT esta FORA da v1 (serial apenas).");
  } else {
    Serial.println("WiFi: desabilitado (WIFI_SSID vazio).");
  }
#endif

  if (Q_LIM_KVAR <= 0.0f) {
    Serial.println("AVISO: Q_LIM_KVAR = 0 (inversor sem margem reativa). "
                   "O controle Volt-Var nao tera efeito — revise o kVA do inversor.");
  }

  // A escala do DAC é a meia-faixa (DAC_MIDRAIL_V): |Q| maior que essa escala
  // grampearia a tensão no extremo do DAC, perdendo a informação do sinal.
  if (Q_LIM_KVAR > DAC_MIDRAIL_V) {
    Serial.printf("AVISO: Q_LIM_KVAR (%.1f kvar) excede a escala do DAC "
                  "(DAC_MIDRAIL_V = %.2f); Q sera saturação no extremo. "
                  "Reduza o kVA de margem ou aceite a perda de escala.\n",
                  Q_LIM_KVAR, DAC_MIDRAIL_V);
  }
}

void loop() {
  // 1) Relógio: detecta a borda de subida do TICK e lê os 5 bits da hora.
  //    Não bloqueia (um único digitalRead por volta).
  ler_relogio();

  // 2) Relógio de reserva: se o Mega parar de pulsar o tick, o firmware
  //    continua contando o tempo pelo millis() para não congelar o SoC. Isso
  //    é um CONTADOR, não um RTC — após um reset sem tick, o horário exibido
  //    começa em 0. O relógio autoritativo é sempre o do Mega.
  uint32_t agora = millis();
  if (!rede.clock_valido) {
    uint32_t decorrido = (agora - rede.millis_ultimo_tick);
    if (decorrido >= 1000) {
      rede.millis_ultimo_tick = agora;
      rede.hora = (rede.hora + 1) % 24;
      rede.frac = 0;
      atualizar_estado_despacho();
    }
  }

  // 3) Integração do SoC com o tempo REAL decorrido.
  uint32_t delta_ms = agora - millis_ultimo_passo_soc;
  if (delta_ms >= 100) {   // passo bem menor que a hora => erro desprezível
    integrar_soc((float)delta_ms / 3600000.0f);
    millis_ultimo_passo_soc = agora;
  }

  // 3b) Medição do V_pu da barra do BESS pelo ADC (a cada volta, para a
  //     média móvel não ficar velha). Custo: ADC_AMOSTRAS conversões.
  medir_tensao();

  // 4) Despacho + controle de reativa com a medição mais recente.
  //    A ordem importa: o despacho base é recomposto a cada ciclo e o
  //    curtailment de Volt-Watt é aplicado sobre ele DENTRO de
  //    calcular_reativa(), de modo que p_kw ao fim do ciclo é o valor
  //    EFETIVO — o mesmo que o setpoint enviado e que a integração do SoC
  //    do próximo ciclo vai usar.
  atualizar_estado_despacho();
  calcular_reativa();

  // 5) Setpoint para o Mega: tensões nos DACs + estado em 2 bits.
  escrever_atuacao();

  // 6) Telemetria JSON 1 Hz.
  if ((agora - millis_ultima_telemetria) >= (uint32_t)TELEMETRIA_MS) {
    millis_ultima_telemetria = agora;
    enviar_telemetria();
  }
}
