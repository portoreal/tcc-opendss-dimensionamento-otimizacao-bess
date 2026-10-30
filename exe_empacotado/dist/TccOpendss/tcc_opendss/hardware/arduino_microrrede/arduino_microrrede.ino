/* ============================================================================
 *  arduino_microrrede.ino
 *  ----------------------------------------------------------------------------
 *  TCC OpenDSS — Plataforma experimental.
 *
 *  PAPEL DESTA PLACA
 *  -----------------
 *  Este sketch representa, no Arduino Mega, o SISTEMA DE ENERGIA ADJACENTE
 *  ao sistema BESS (a microrrede): as cargas com suas curvas horárias, a
 *  geração fotovoltaica, as impedâncias dos ramos e os bancos de capacitores.
 *  Ele NÃO decide o despacho — quem decide é o ESP32 (controle do BESS).
 *  O Mega recebe o setpoint de potência ativa/reativa do BESS por dois fios
 *  analógicos e devolve, hora a hora, as tensões resultantes em cada barra
 *  por um PWM filtrado. É assim que o efeito da atuação do BESS sobre a
 *  microrrede fica observável no ensaio.
 *
 *  PLACA: Arduino Mega 2560 R3 (ATmega2560, lógica de 5 V) — decisão do
 *  pesquisador. Ver a nota de CONDICIONAMENTO DE NÍVEL mais abaixo.
 *
 *  ESTE ARQUIVO É PRÉ-PRONTO E NÃO CONTÉM NENHUM DADO DE PROJETO.
 *  ----------------------------------------------------------------------------
 *  A lógica embarcada é fixa e versionada. Todos os dados do projeto chegam
 *  pelo cabeçalho `param_microrrede.h`, GERADO pelo módulo Python
 *  `bibliotecas/exportador_arduino.py` a partir da rede desenhada no Editor
 *  de Rede do TCC (arquivo rede/rede.json do projeto). Para usar outro
 *  projeto, basta substituir esse cabeçalho — o sketch não é reescrito.
 *
 *  TRANSPARÊNCIA TÉCNICA — LEIA ANTES DE COMPARAR COM O OpenDSS
 *  ------------------------------------------------------------
 *  O cálculo embarcado NÃO é um fluxo de potência iterativo. É uma
 *  APROXIMAÇÃO DE VARREDURA RADIAL: parte da barra fonte com tensão
 *  conhecida e propaga as quedas de tensão ramo a ramo,
 *
 *      dV ≈ (R·P + X·Q) / V²        [pu, bases do projeto]
 *
 *  com as potências do instante (carga × curva horária, PV como geração
 *  negativa, injeção do BESS vinda do ESP32). Consequências dessa escolha,
 *  declaradas para não gerar conclusões indevidas:
 *
 *   1. A varredura percorre uma ÁRVORE RADIAL (BFS a partir da barra da
 *      fonte). Malhas fechadas, se existirem no projeto, são resolvidas como
 *      se fossem radiais — o resultado num laço é apenas indicativo.
 *   2. As perdas nos ramos NÃO realimentam as potências (não há iteração):
 *      a tensão calculada tende a ficar levemente otimista, mais quanto mais
 *      carregado o alimentador.
 *   3. O termo de queda usa V da barra de origem elevado ao quadrado,
 *      aproximação clássica de linha curta. Erro cresce para quedas grandes.
 *   4. Transformadores são tratados como um ramo com a impedância em pu que
 *      consta no cabeçalho gerado. A relação de tap NÃO é modelada na v1.
 *   5. Capacitores entram como injeção de reativo constante (sempre ligados).
 *      Chaveamento por tensão/horário não existe nesta versão.
 *
 *  Este sketch serve para EXIBIR O SENTIDO E A ORDEM DE GRANDEZA da resposta
 *  da microrrede à atuação do BESS. Os números de referência continuam sendo
 *  os do estudo no OpenDSS. Não use esta saída como resultado quantitativo
 *  final do trabalho.
 *
 *  INTERFACE COM O ESP32 — 12 LIGAÇÕES DIRETAS DIGITAIS E ANALÓGICAS
 *  ------------------------------------------------------------------
 *  NÃO há UART entre as placas. São fios ponto a ponto, cada placa com
 *  alimentação INDEPENDENTE e apenas o GND em comum (referência de sinal —
 *  sem ela o ADC do Mega e o DAC do ESP32 não têm referência e a leitura
 *  não significa nada).
 *
 *  CONDICIONAMENTO DE NÍVEL (Mega 5 V -> ESP32 3,3 V)
 *  ---------------------------------------------------
 *  O Mega 2560 R3 tem saídas de 5 V; as entradas do ESP32 são de 3,3 V e
 *  NÃO são tolerantes a 5 V. Por isso TODAS as linhas Mega -> ESP32 (hora,
 *  tick e o V_pu) passam por um DIVISOR EXTERNO de 10 kOhm em série com
 *  20 kOhm para GND, montado junto ao ESP32:
 *
 *      5,0 V x 20/(10+20) = 3,33 V   (HIGH válido, dentro do absoluto)
 *
 *  Na linha do V_pu (D8) o filtro RC de 4,7 kOhm + 10 uF vem ANTES do
 *  divisor — o RC precisa ver o PWM de 5 V para filtrar direito.
 *  NUNCA ligue um D2..D8 direto no GPIO do ESP32: a entrada queima.
 *  As linhas ESP32 -> Mega (A0/A1 e D9/D10) são DIRETAS: 3,3 V num ATmega
 *  de 5 V é nível alto legítimo (VIH = 0,6 x 5 = 3,0 V), com margem de
 *  0,3 V. Em instalação de campo, use level shifter; na bancada, direto.
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
 *  Todos os pinos vêm de #define do `param_microrrede.h` (PINO_HORA_BIT0..4,
 *  PINO_TICK_HORA, PINO_VPU_SAIDA, PINO_P_ADC, PINO_Q_ADC, PINO_ESTADO0/1).
 *  Nada de número de pino escrito à mão aqui.
 *
 *  CODIFICAÇÃO DOS SINAIS
 *  ----------------------
 *  - Hora: 5 bits em paralelo (D2..D6) + 1 fio de TICK (D7) que pulsa em
 *    borda de subida a cada nova hora. O barramento é ESTÁVEL antes do
 *    pulso, então o ESP32 não precisa de protocolo: lê os 5 bits quando vê
 *    o tick subir. Autossincronizante e visível em LEDs, o que ajuda na
 *    bancada.
 *  - V_pu da barra do BESS: analogWrite no D8 (PWM do Mega), filtrado por
 *    RC (4,7 kΩ + 10 µF) para virar tensão contínua de 0..5 V e então
 *    dividido por 10k/20k (condicionamento acima). Escala:
 *    V = V_pu / VPU_ANALOG_MAX × VREF_MEGA_ADC.
 *  - Setpoint de P/Q: lidos em A0/A1 (ADC de 10 bits, referência 5 V).
 *    Meia-faixa (DAC_MIDRAIL_V = 1,65 V) significa ZERO; acima é INJEÇÃO,
 *    abaixo é ABSORÇÃO. O DAC do ESP32 só chega a 3,3 V, então o Mega usa
 *    no máximo ~66% da própria faixa — a resolução efetiva cai, e isso é
 *    uma limitação DECLARADA da bancada, não corrigida aqui.
 *  - Estado do BESS: 2 bits (D9/D10) — 00 repouso, 01 carregando,
 *    10 descarregando, 11 reservado. É redundante com o sinal analógico de
 *    propósito: serve de conferência rápida (e de diagnóstico se o fio
 *    analógico se soltar).
 *
 *  HARDWARE
 *  --------
 *  - Saída analógica por barra em PWM (analogWrite), conforme PINO_PWM_BARRA
 *    do cabeçalho: duty = pu / PU_PWM_MAX × 255. É uma representação para
 *    instrumentação/visualização, não um sinal de potência. Esses pinos vão
 *    para instrumentos (osciloscópio/medidor), NÃO para o ESP32 — se um dia
 *    forem lidos pelo ESP32, exigem o mesmo divisor 10k/20k.
 *  - O D8 usado para o V_pu do BESS é um pino PWM do Mega; o pino também é
 *    um canal de analogWrite válido — não colidir com PINO_PWM_BARRA.
 *
 *  Autor: Pedro Henrique Sousa Pinheiro — TCC OpenDSS.
 * ==========================================================================*/

#include "param_microrrede.h"

/* ---------------------------------------------------------------------------
 * Relógio acelerado
 * ---------------------------------------------------------------------------
 * SEGUNDOS_POR_HORA vem do cabeçalho: quantos segundos reais valem por hora
 * SIMULADA. Com 1.0, um dia inteiro roda em 24 s reais. Com 3600.0, roda em
 * tempo real. A virada de meia-noite incrementa o DIA e reinicia a hora em 0.
 * O dia da semana (0 = Segunda) NÃO é reenviado pelo Python: ele é derivado
 * de DIA_INICIAL + dia decorrido, módulo 7, aqui na placa.
 * ------------------------------------------------------------------------- */
static uint32_t g_dia = 0;             /* dia decorrido desde DIA_INICIAL      */
static uint8_t  g_hora = 0;            /* 0..23                                */
static uint32_t g_ultimoTickMs = 0;
static uint32_t g_msPorHora = 1000;    /* recalculado no setup()               */

/* Setpoint LIDO do ESP32 pelos ADCs A0/A1 (default = sem injeção). */
static float g_p_kw = 0.0f;
static float g_q_kvar = 0.0f;
static uint8_t g_estado_bess = 0;      /* 2 bits de estado, só diagnóstico   */

/* Valor aceito para |P| e |Q|: sem KW_RATING não há escala e o setpoint lido
   é zero. O guarda existe para o caso de o Storage do projeto não declarar
   potência — dividir por zero silenciosamente seria pior. */
static float escala_kw(void) {
    return (KW_RATING > 0.0f) ? KW_RATING : 0.0f;
}

/* Tensões calculadas no último tick, em pu. Tamanho vem do cabeçalho. */
static float g_tensao_pu[N_BARRAS];
static uint16_t g_ultimoSerialEnvio = 0;

/* ---------------------------------------------------------------------------
 * Curvas horárias: interpolação linear sobre a tabela de 24 multiplicadores.
 * ---------------------------------------------------------------------------
 * A tabela do cabeçalho tem exatamente 24 posições (hora 0..23), já
 * expandida pelo gerador Python a partir dos pontos irregulares do editor.
 * Aqui só interpolamos entre a hora inteira atual e a próxima, usando
 * frac_x1000 (fração da hora em milésimos) para suavizar a transição.
 * ------------------------------------------------------------------------- */
static float interpolar24(const float *tabela, uint8_t hora, uint16_t frac_x1000) {
    uint8_t h0 = hora % 24;
    uint8_t h1 = (uint8_t)((h0 + 1) % 24);
    float f = (float)frac_x1000 / 1000.0f;
    if (f < 0.0f) f = 0.0f;
    if (f > 1.0f) f = 1.0f;
    return tabela[h0] * (1.0f - f) + tabela[h1] * f;
}

/* ---------------------------------------------------------------------------
 * Varredura radial
 * ---------------------------------------------------------------------------
 * TRANSPARÊNCIA TÉCNICA: ver o cabeçalho do arquivo. Esta rotina calcula a
 * tensão de cada barra a partir de BARRA_FONTE, distribuindo as potências
 * do instante e acumulando as quedas ramo a ramo. A ordem de visita é BFS
 * (fila simples), o que exige que o grafo seja uma árvore a partir da fonte.
 * ------------------------------------------------------------------------- */
static void calcular_tensoes(void) {
    /* Potência líquida em pu acumulada por barra: >0 = consumo, <0 = injeção. */
    float p_pu[N_BARRAS];
    float q_pu[N_BARRAS];

    for (uint8_t i = 0; i < N_BARRAS; i++) {
        float mp = interpolar24(LOAD_MULT[i], g_hora, 0);
        /* Fator de carga por dia da semana (modo de simulação declarado).   */
        float fd = FATOR_DIA_SEMANA[(DIA_INICIAL + g_dia) % 7];

        /* Carga: consumo positivo. */
        p_pu[i] = (LOAD_KW[i] * mp * fd) / BASE_KVA;
        q_pu[i] = (LOAD_KVAR[i] * mp * fd) / BASE_KVA;

        /* Geração fotovoltaica: injeção, portanto sinal negativo.           */
        /* A curva de geração já embute o perfil do dia; o índice de nuvens  */
        /* chega pronto do ESP32 embutido no multiplicador pela curva?      */
        /* NÃO: nesta versão o Mega aplica NUVEM_PADRAO do cabeçalho. O      */
        /* operador controla nuvens pelo dashboard Python; o ensaio de       */
        /* bancada replica o valor parametrizado.                           */
        float mg = interpolar24(GEN_MULT[i], g_hora, 0);
        p_pu[i] -= (GEN_KW[i] * mg * NUVEM_FATOR) / BASE_KVA;
        q_pu[i] -= (GEN_KVAR[i] * mg * NUVEM_FATOR) / BASE_KVA;

        /* Capacitor: injeção de reativo, sempre ligado nesta versão.       */
        q_pu[i] -= CAP_KVAR[i] / BASE_KVA;
    }

    /* Injeção do BESS no barramento designado (+ = injeta na rede). */
#if BESS_BUS >= 0
    p_pu[BESS_BUS] -= g_p_kw / BASE_KVA;
    q_pu[BESS_BUS] -= g_q_kvar / BASE_KVA;
#endif

    /* Tensão inicial em todas as barras = tensão da fonte. */
    for (uint8_t i = 0; i < N_BARRAS; i++) {
        g_tensao_pu[i] = V_FONTE_PU;
    }

    /* BFS a partir da barra fonte, propagando potência para a raiz. */
    /* POT_ACUM recebe a soma do consumo de toda a subárvore de cada barra; */
    /* é essa potência que atravessa o ramo de chegada.                    */
    float pot_p[N_BARRAS];
    float pot_q[N_BARRAS];
    for (uint8_t i = 0; i < N_BARRAS; i++) {
        pot_p[i] = p_pu[i];
        pot_q[i] = q_pu[i];
    }

    bool visitado[N_BARRAS];
    uint8_t fila[N_BARRAS];
    int8_t pai[N_BARRAS];
    int8_t ramo_pai[N_BARRAS];

    for (uint8_t i = 0; i < N_BARRAS; i++) {
        visitado[i] = false;
        pai[i] = -1;
        ramo_pai[i] = -1;
    }

    uint8_t ini = 0, fim = 0;
    fila[fim++] = BARRA_FONTE;
    visitado[BARRA_FONTE] = true;

    while (ini < fim) {
        uint8_t atual = fila[ini++];
        for (uint16_t r = 0; r < N_RAMOS; r++) {
            uint8_t b1 = RAMO_BUS1[r];
            uint8_t b2 = RAMO_BUS2[r];
            uint8_t vizinho;
            if (b1 == atual) {
                vizinho = b2;
            } else if (b2 == atual) {
                vizinho = b1;
            } else {
                continue;
            }
            if (visitado[vizinho]) {
                continue;   /* já visitado: aresta de retorno (malha) ignorada */
            }
            visitado[vizinho] = true;
            pai[vizinho] = (int8_t)atual;
            ramo_pai[vizinho] = (int8_t)r;
            fila[fim++] = vizinho;
        }
    }

    /* Acumula do fim da fila para o início (ordem topológica da árvore).   */
    for (int k = (int)fim - 1; k >= 0; k--) {
        uint8_t b = fila[k];
        int8_t p = pai[b];
        if (p >= 0) {
            pot_p[p] += pot_p[b];
            pot_q[p] += pot_q[b];
        }
    }

    /* Propaga tensões na ordem da BFS (pai antes do filho). */
    for (int k = 0; k < (int)fim; k++) {
        uint8_t b = fila[k];
        int8_t p = pai[b];
        int8_t r = ramo_pai[b];
        if (p < 0 || r < 0) {
            continue;
        }
        float v = g_tensao_pu[p];
        if (v < 0.05f) {
            v = 0.05f;   /* evita divisão explosiva em condição degenerada */
        }
        /* Queda de tensão aproximada no ramo (pu).                        */
        float dv = (RAMO_R_PU[r] * pot_p[b] + RAMO_X_PU[r] * pot_q[b]) / (v * v);
        g_tensao_pu[b] = g_tensao_pu[p] - dv;
        if (g_tensao_pu[b] < 0.0f) {
            g_tensao_pu[b] = 0.0f;
        }
    }
}

/* ---------------------------------------------------------------------------
 * Saída PWM por barra
 * ------------------------------------------------------------------------- */
static void atualizar_pwm(void) {
    for (uint8_t i = 0; i < N_BARRAS; i++) {
        if (PINO_PWM_BARRA[i] < 0) {
            continue;   /* barra sem canal analógico atribuído              */
        }
        float razao = g_tensao_pu[i] / PU_PWM_MAX;
        if (razao < 0.0f) razao = 0.0f;
        if (razao > 1.0f) razao = 1.0f;
        analogWrite((uint8_t)PINO_PWM_BARRA[i], (int)(razao * 255.0f));
    }
}

/* ---------------------------------------------------------------------------
 * Publicação do estado para o ESP32 (barramento de 5 bits + tick + V_pu)
 * ---------------------------------------------------------------------------
 * Por que 5 bits paralelos em vez de serial: o ESP32 lê a hora quando vê o
 * tick subir, sem protocolo, sem baud rate e sem estado parcial (os bits já
 * estão estáveis milissegundos antes do pulso). Se o ESP32 reiniciar, o
 * próximo tick ressincroniza — não existe "frame perdido".
 * ------------------------------------------------------------------------- */
static void escrever_bits_hora(uint8_t hora) {
    digitalWrite(PINO_HORA_BIT0, (hora & 0x01) ? HIGH : LOW);
    digitalWrite(PINO_HORA_BIT1, (hora & 0x02) ? HIGH : LOW);
    digitalWrite(PINO_HORA_BIT2, (hora & 0x04) ? HIGH : LOW);
    digitalWrite(PINO_HORA_BIT3, (hora & 0x08) ? HIGH : LOW);
    digitalWrite(PINO_HORA_BIT4, (hora & 0x10) ? HIGH : LOW);
}

static void escrever_vpu_bess(void) {
#if BESS_BUS >= 0
    float v_pu = g_tensao_pu[BESS_BUS];
#else
    /* Sem BESS no projeto: entrega 0 V. O ESP32 lê "sem medição" (v_pu = 0)
       e NÃO atua em reativa — é o comportamento certo, e o aviso já foi
       emitido pelo gerador do cabeçalho. */
    float v_pu = 0.0f;
#endif
    float razao = v_pu / VPU_ANALOG_MAX;
    if (razao < 0.0f) razao = 0.0f;
    if (razao > 1.0f) razao = 1.0f;
    analogWrite(PINO_VPU_SAIDA, (int)(razao * 255.0f));
}

static void publicar_estado(void) {
    escrever_bits_hora(g_hora);
    escrever_vpu_bess();

    /* Pulso de tick: >= 10 ms de nível alto, para que qualquer laço do ESP32
       o veja mesmo se estiver ocupado com o ADC. O pulso vai DEPOIS de os
       bits estarem escritos — é o que garante a atomicidade da leitura. */
    delay(2);
    digitalWrite(PINO_TICK_HORA, HIGH);
    delay(TICK_LARGURA_MS);
    digitalWrite(PINO_TICK_HORA, LOW);
}

/* ---------------------------------------------------------------------------
 * Leitura do setpoint nos ADCs (A0 = P, A1 = Q)
 * ---------------------------------------------------------------------------
 * O ESP32 escreve nos DACs uma tensão mid-rail: DAC_MIDRAIL_V = zero, acima
 * = injeção, abaixo = absorção. A conversão inversa é
 *
 *     P = (V_lido - DAC_MIDRAIL_V) / DAC_MIDRAIL_V * KW_RATING
 *
 * com V_lido = leitura_ADC / 1023 * VREF_MEGA_ADC (ADC de 10 bits do Mega).
 * O Q usa a mesma forma, limitado por Q_LIM_KVAR do lado do ESP32 — aqui só
 * se converte, não se limita (limitar dos dois lados mascararia qual lado
 * cortou, dificultando o diagnóstico na bancada).
 *
 * TRANSPARÊNCIA: DAC_MIDRAIL_V é 1,65 V e o ADC lê 0..5 V, então o zero do
 * setpoint fica em ~33% da faixa do ADC (337 contagens). A resolução útil é
 * (VREF_MEGA_ADC/1023) × (KW_RATING/DAC_MIDRAIL_V) — menor do que seria com
 * referência de 3,3 V no ADC. É limitação de bancada, declarada.
 * ------------------------------------------------------------------------- */
static float ler_adc_midrail(uint8_t pino, float escala) {
    if (escala <= 0.0f) {
        return 0.0f;   /* sem KW_RATING não há como converter para kW */
    }
    long soma = 0;
    for (uint8_t i = 0; i < ADC_AMOSTRAS; i++) {
        soma += analogRead(pino);
    }
    float leitura = (float)soma / (float)ADC_AMOSTRAS;
    float tensao = leitura * (VREF_MEGA_ADC / 1023.0f);
    return (tensao - DAC_MIDRAIL_V) / DAC_MIDRAIL_V * escala;
}

static void ler_setpoint(void) {
    g_p_kw = ler_adc_midrail(PINO_P_ADC, escala_kw());
#if BESS_BUS >= 0
    g_q_kvar = ler_adc_midrail(PINO_Q_ADC, escala_kw());
#else
    g_q_kvar = 0.0f;
#endif

    uint8_t b0 = (uint8_t)digitalRead(PINO_ESTADO0);
    uint8_t b1 = (uint8_t)digitalRead(PINO_ESTADO1);
    g_estado_bess = (uint8_t)(b0 | (b1 << 1));
}

/* ---------------------------------------------------------------------------
 * Setup / loop
 * ------------------------------------------------------------------------- */
void setup(void) {
    Serial.begin(115200);        /* PC: depuração (opcional)               */

    /* Pinos da interface física com o ESP32 (vindos do cabeçalho).        */
    pinMode(PINO_HORA_BIT0, OUTPUT);
    pinMode(PINO_HORA_BIT1, OUTPUT);
    pinMode(PINO_HORA_BIT2, OUTPUT);
    pinMode(PINO_HORA_BIT3, OUTPUT);
    pinMode(PINO_HORA_BIT4, OUTPUT);
    pinMode(PINO_TICK_HORA, OUTPUT);
    pinMode(PINO_VPU_SAIDA, OUTPUT);
    pinMode(PINO_ESTADO0, INPUT);
    pinMode(PINO_ESTADO1, INPUT);
    /* PINO_P_ADC / PINO_Q_ADC (A0/A1) são entradas analógicas: o Mega não
       exige pinMode() para usar analogRead(), e declará-los como INPUT
       desligaria o pull-up interno — que não deve existir aqui, pois quem
       define a tensão é o DAC do ESP32. */
    digitalWrite(PINO_TICK_HORA, LOW);

    if (SEGUNDOS_POR_HORA > 0.0f) {
        g_msPorHora = (uint32_t)(SEGUNDOS_POR_HORA * 1000.0f);
    }
    if (g_msPorHora < 10) {
        g_msPorHora = 10;        /* piso de segurança                      */
    }

    for (uint8_t i = 0; i < N_BARRAS; i++) {
        if (PINO_PWM_BARRA[i] >= 0) {
            pinMode((uint8_t)PINO_PWM_BARRA[i], OUTPUT);
        }
    }

    /* Calcula e publica o estado inicial (hora 0), para o ESP32 já ter a
       fotografia da rede antes de o primeiro tick de relógio ocorrer.      */
    calcular_tensoes();
    atualizar_pwm();
    ler_setpoint();
    publicar_estado();

    g_ultimoTickMs = millis();
    g_ultimoSerialEnvio = 0;
}

void loop(void) {
    uint32_t agora = millis();
    uint32_t decorrido = agora - g_ultimoTickMs;

    if (decorrido >= g_msPorHora) {
        g_ultimoTickMs = agora;

        /* Avança a hora simulada; na virada de meia-noite avança o dia.    */
        g_hora = (uint8_t)((g_hora + 1) % 24);
        if (g_hora == 0) {
            g_dia++;
        }

        /* Ordem do ciclo: ler o setpoint do ESP32 ANTES de recalcular as
           tensões (o setpoint vale para a hora que começa agora) e publicar
           o resultado DEPOIS — é assim que o ESP32 vê o efeito da própria
           atuação. */
        ler_setpoint();
        calcular_tensoes();
        atualizar_pwm();
        publicar_estado();
    }
}
