# Hardware — plataforma experimental (ESP32 + Arduino Mega 2560 R3)

Parte experimental do TCC: duas placas que representam, em bancada, a
microrrede e o sistema BESS de qualidade de energia. É a implementação do
que a Metodologia do `.tex` chama de *parametrização da plataforma
experimental com os resultados obtidos pela otimização*.

**Placas adotadas (decisão do pesquisador):** Arduino **Mega 2560 R3**
(ATmega2560, lógica de **5 V**) e **ESP32** (lógica de **3,3 V**). A
diferença de nível entre as duas é o único ponto elétrico que exige
componentes externos — ver *Condicionamento de nível* abaixo.

## Princípio: sketch pré-pronto + parametrização gerada

**O código embarcado NÃO é gerado a cada execução.** Os dois sketches são
fixos, revisados e compilados uma vez; o software do TCC gera apenas um
**cabeçalho de parametrização** (`.h`) por projeto, que o sketch inclui.

```
hardware/
  arduino_microrrede/
    arduino_microrrede.ino      <- pré-pronto (lógica fixa, não editar por projeto)
  esp32_controle_bess/
    esp32_controle_bess.ino     <- pré-pronto (lógica fixa, não editar por projeto)
```

A parametrização é escrita **dentro da pasta do projeto**, em
`<projeto>/hardware/`:

| Arquivo gerado | Origem no software | Quando |
|---|---|---|
| `<projeto>/hardware/param_microrrede.h` | `bibliotecas/exportador_arduino.py` | após a rede estar **desenhada/projetada** |
| `<projeto>/hardware/param_esp32.h` | `bibliotecas/exportador_esp32.py` | após a **otimização do BESS** concluir |

Para compilar, copie o `.h` gerado para a mesma pasta do `.ino`
correspondente (a IDE Arduino exige o cabeçalho ao lado do sketch) — ou
copie o `.ino` para a pasta do projeto.

## Papel de cada placa

### Arduino Mega 2560 R3 — rede adjacente ao BESS (representa e mede)

Representa a microrrede em que o BESS está inserido e **entrega os sinais
elétricos** para o ESP32. Recebe do `param_microrrede.h`: topologia
(barras/ramos com R e X em pu), tabelas de carga 24 h por barra, curva da
geração fotovoltaica, capacitores e a barra de conexão do BESS. Escreve
uma saída PWM por barra (tensão em pu) e publica a hora simulada, o V_pu
da barra do BESS e lê os setpoints de P/Q vindos do ESP32.

- Limitação: **até 3 barras** com saída PWM (`D11`, `D12`, `D13`). Os
  pinos `D2..D10` estão tomados pelo enlace com o ESP32 — usar `D2..D13`
  cru colocaria uma saída PWM de barra no mesmo pino do tick de hora, do
  V_pu ou das entradas de estado. Projetos com mais de 3 barras precisam
  escolher (o gerador emite AVISO por barra sem canal analógico):
  remover a PWM das barras excedentes, mover o enlace ou usar um expansor
  de PWM. **Esta é a limitação prática mais relevante do mapa de pinos.**
- Sem `BESS_BUS` no projeto → o gerador escreve `BESS_BUS = -1` e emite
  aviso; o sketch escreve 0 V no fio de V_pu e o ESP32 não atua.

### ESP32 — controle do sistema BESS (atua)

Executa o **despacho de potência ativa e reativa** do BESS conforme o
sistema de armazenamento para qualidade de energia já desenvolvido no
TCC. Recebe do `param_esp32.h`: tabela de despacho 24 h (estado e kW por
hora), limites de SoC, limites P/Q do inversor e os pontos das curvas
**Volt-Var** e **Volt-Watt** reais do projeto.

- A reativa é interpolada nas curvas Volt-Var/Volt-Watt e limitada pela
  margem aparente `sqrt(KVA² − P²)`.
- O despacho é **fechado em malha**: o estado é reavaliado a cada hora com
  o SoC que o próprio firmware integra — reproduzindo a regra de
  `economia_energia.py` em vez de divergir dela.
- **1 sistema BESS por ESP32** na v1.
- WiFi/MQTT estão **fora da v1** (blocos desativados por `#ifdef`).

## Esquema de ligação — 12 conexões diretas digitais e analógicas

**Não há UART entre as placas.** São fios ponto a ponto: cada placa tem
**alimentação individual** (fonte própria — USB ou fonte externa) e apenas
o **GND em comum**, que é a referência de sinal do ADC e do DAC.

```
ESP32 GPIO 25 (DAC1) <-> Arduino Mega A0  (Dados: setpoint de P)
```

| # | Ligação | Dados | Sentido | Condicionamento |
|---|---|---|---|---|
| 1 | ESP32 GPIO 23 <-> Arduino Mega D2 | hora simulada, bit 0 (LSB) — digital | Mega → ESP32 | divisor 10 kΩ / 20 kΩ |
| 2 | ESP32 GPIO 22 <-> Arduino Mega D3 | hora simulada, bit 1 — digital | Mega → ESP32 | divisor 10 kΩ / 20 kΩ |
| 3 | ESP32 GPIO 21 <-> Arduino Mega D4 | hora simulada, bit 2 — digital | Mega → ESP32 | divisor 10 kΩ / 20 kΩ |
| 4 | ESP32 GPIO 19 <-> Arduino Mega D5 | hora simulada, bit 3 — digital | Mega → ESP32 | divisor 10 kΩ / 20 kΩ |
| 5 | ESP32 GPIO 18 <-> Arduino Mega D6 | hora simulada, bit 4 (MSB) — digital | Mega → ESP32 | divisor 10 kΩ / 20 kΩ |
| 6 | ESP32 GPIO 5 <-> Arduino Mega D7 | tick de hora (borda de subida = nova hora) — digital | Mega → ESP32 | divisor 10 kΩ / 20 kΩ |
| 7 | ESP32 GPIO 36 (ADC1/VP) <-> Arduino Mega D8 | V_pu da barra do BESS — analógica (PWM + filtro RC) | Mega → ESP32 | filtro RC **+** divisor 10 kΩ / 20 kΩ |
| 8 | ESP32 GPIO 25 (DAC1) <-> Arduino Mega A0 | setpoint de P — analógica (mid-rail 1,65 V = 0) | ESP32 → Mega | **direta** |
| 9 | ESP32 GPIO 26 (DAC2) <-> Arduino Mega A1 | setpoint de Q — analógica (mid-rail 1,65 V = 0) | ESP32 → Mega | **direta** |
| 10 | ESP32 GPIO 27 <-> Arduino Mega D9 | estado do BESS, bit 0 (00 repouso / 01 carregando / 10 descarregando / 11 reservado) — digital | ESP32 → Mega | **direta** |
| 11 | ESP32 GPIO 14 <-> Arduino Mega D10 | estado do BESS, bit 1 — digital | ESP32 → Mega | **direta** |
| 12 | ESP32 GND <-> Arduino Mega GND | referência de sinal comum — **OBRIGATÓRIA**, não é opcional | — | — |

## Condicionamento de nível (Mega 5 V → ESP32 3,3 V)

O **Mega 2560 R3 trabalha em 5 V**; o **ESP32 é de 3,3 V e suas entradas
NÃO são tolerantes a 5 V** (absoluto máximo ≈ 3,6 V). Por isso toda linha
que sai do Mega em direção ao ESP32 precisa ser reduzida. Sem isso o
experimento **queima a entrada do ESP32** na primeira hora simulada.

**Divisor adotado: 10 kΩ em série + 20 kΩ para GND**, montado junto ao
ESP32:

```
V_esp = 5,0 V × 20 kΩ/(10 kΩ + 20 kΩ) = 3,33 V
```

3,33 V é HIGH legítimo para o ESP32 (VIH ≈ 0,75 × 3,3 = 2,5 V) e fica
abaixo do absoluto máximo. As macros correspondentes saem nos dois
cabeçalhos: `DIVISOR_DIGITAL` = 0,6667, `R_SERIE_DIV` = 10 000 Ω,
`R_GND_DIV` = 20 000 Ω, `MEGA_VCC_PWM` = 5,0 V.

### Linha do V_pu (D8 → GPIO 36) — RC **antes** do divisor

```
D8 (PWM 5 V) ──[4,7 kΩ]──┬──[10 kΩ]── GPIO 36
                          │             │
                        [10 µF]       [20 kΩ]
                          │             │
                         GND           GND
```

O filtro RC tem de ver o PWM de 5 V **antes** de ser dividido — invertendo
a ordem, o divisor carregaria o filtro e a constante de tempo mudaria.
O firmware converte de volta a tensão do Mega:

```
v_esp  = leitura/4095 × VREF_ESP32_DAC        (volts no GPIO)
v_pu   = (v_esp / DIVISOR_VPU / MEGA_VCC_PWM) × VPU_PWM_MAX
```

Confere: 1,00 pu → Mega escreve 4,167 V → divisor entrega 2,778 V →
ADC lê 3447 LSB → a fórmula devolve 1,0000 pu.

### Linhas ESP32 → Mega — diretas

3,3 V dentro de uma entrada de 5 V é nível alto legítimo: o VIH do
ATmega2560 é **0,6 × 5 V = 3,0 V**, então há **0,3 V de margem** nas
linhas de estado (GPIO 27/14 → D9/D10). Nos DACs (GPIO 25/26 → A0/A1) a
ligação é analógica e o Mega usa ~66 % da faixa de 10 bits — limitação
declarada, não é falha.

> **Atenção à margem de 0,3 V**: em bancada é suficiente. Para instalação
> de campo (cabos longos, ruído, queda no cabo) use **level shifter**
> bidirecional nas linhas ESP32 → Mega. A v1 é de bancada.

### BOM do condicionamento

| Item | Qtd | Uso |
|---|---|---|
| Resistor 10 kΩ (1/4 W, 1 %) | 7 | série do divisor — 6 digitais + 1 do V_pu |
| Resistor 20 kΩ (1/4 W, 1 %) | 7 | fuga para GND — 6 digitais + 1 do V_pu |
| Resistor 4,7 kΩ (1/4 W) | 1 | série do filtro RC do D8 |
| Capacitor 10 µF (eletrolítico) | 1 | filtro RC do D8, para GND |

Todos os divisores usam os **mesmos valores** (BOM uniforme): 6 nas linhas
digitais Mega → ESP32 e 1 na linha do V_pu. As 4 linhas ESP32 → Mega não
levam componente algum.

### Notas de montagem

- **Filtro RC no D8**: o Mega escreve o V_pu como PWM; o ESP32 lê tensão
  contínua. Sem filtro a leitura oscila com o duty cycle. Use
  **4,7 kΩ em série + 10 µF para GND** (constante de tempo ≈ 47 ms, muito
  menor que a hora simulada). O valor sai em `PWM_FILTRO_RC` no cabeçalho.
- **NUNCA ligue um pino de saída do Mega (D2..D8) direto num GPIO do
  ESP32.** São 5 V contra uma entrada de 3,3 V não tolerante — a entrada
  queima. O divisor 10 kΩ/20 kΩ não é opcional; o esquema acima parte do
  princípio de que ele existe.
- **Referência comum**: sem o GND ligado, o ADC do Mega e o DAC do ESP32
  não têm referência comum e as leituras não significam nada. Fontes
  separadas + GND comum é o padrão de bancada — **não** ligue as duas
  placas pela alimentação.
- **Resolução do ADC do Mega**: o DAC do ESP32 chega a 3,3 V e o ADC do
  Mega tem referência 5 V, então o setpoint usa no máximo **~66%** da faixa
  do ADC (337 contagens para o zero, em 1023). A resolução efetiva é menor;
  é uma limitação declarada da bancada, não corrigida por hardware.
- **Escalas** (todas em `#define`, ajustáveis no `.h` gerado):
  `VPU_ANALOG_MAX` = 1,20 pu (tensão pu que corresponde ao fundo de escala),
  `DAC_MIDRAIL_V` = 1,65 V (zero de P/Q), `VREF_MEGA_ADC` = 5,0 V,
  `VREF_ESP32_DAC` = 3,3 V, `DIVISOR_VPU` = 0,6667 (divisor da linha do
  V_pu), `MEGA_VCC_PWM` = 5,0 V (fundo de escala do PWM do Mega),
  `VPU_PWM_MAX` = 1,20 pu, `VIH_MEGA` = 3,0 V, `KW_RATING` (escala de P e
  de Q no Mega).
- **Identificação das placas nos cabeçalhos**: `PLACA_MICRORREDE` =
  `"Arduino Mega 2560 R3 (ATmega2560, 5 V)"` e `PLACA_CONTROLE` =
  `"ESP32 (3,3 V) — interface acondicionada para Mega 2560 R3"`. Servem
  para o log de bancada provar qual par de cabeçalhos está gravado.
- **Nenhum número de pino está escrito nos sketches**: eles vêm de
  `#define` do cabeçalho, gerados a partir de `MAPA_LIGACOES` em
  `exportador_arduino.py` — a mesma fonte para os dois cabeçalhos. Se os
  dois `.h` divergirem, a bancada não funciona; por isso os dois saem do
  mesmo mapa.

## Como usar

1. **Arduino** — abra o projeto no **Editor de Rede**, desenhe/projete a
   microrrede, exporte o `.dss` e escolha
   *menu Arquivo → "Exportar parametrização Arduino (microrrede)"*.
   Gera `param_microrrede.h`.
2. **ESP32** — rode a **Otimização do BESS** até concluir e, na janela de
   resultados, clique em *"Exportar parametrização ESP32 (controle BESS)"*.
   Gera `param_esp32.h`.
   Sem configuração vencedora o gerador **recusa com erro claro** — não há
   como parametrizar o controle antes de existir o despacho.
3. Copie cada `.h` para junto do `.ino` correspondente e compile.

Os dois geradores também rodam por linha de comando:

```
python -m bibliotecas.exportador_arduino <caminho_raiz_projeto>
python -m bibliotecas.exportador_esp32   <caminho_raiz_projeto>
```

## Requisitos para compilar

- **IDE Arduino** com os cores **Arduino AVR (Mega)** e **ESP32**
  instalados. **Nenhum dos dois está disponível na máquina onde o
  software foi desenvolvido** — a compilação dos sketches é pendência
  declarada para o pesquisador.
- Os sketches usam apenas funções nativas (`digitalRead/Write`,
  `analogRead/Write`, `dacWrite`, `analogSetPinAttenuation`) e o
  `#include` do cabeçalho gerado: sem bibliotecas externas.
- O ESP32 usa `analogReadResolution(12)` e atenuação `ADC_11db` no GPIO 36
  (faixa 0–3,3 V, casando com a escala do V_pu). O Mega usa ADC de 10 bits
  com a referência de 5 V da placa.

## Aviso sobre os números do experimento

Os valores de referência do experimento são os do **OpenDSS**. O Arduino
Mega **não roda fluxo de potência**: ele usa uma **varredura radial
aproximada**, `dV ≈ (R·P + X·Q)/V²` por ramo, marcada no código como
`TRANSPARÊNCIA TÉCNICA`. É uma aproximação quase-estática adequada para
mostrar a propagação do afundamento em bancada — **não substitui** os
resultados do simulador nem o estudo de afundamento de tensão
(`estudo_afundamento.py`).

A cobertura de nuvens na bancada é fixa, via `NUVEM_FATOR` no cabeçalho
gerado: o enlace entre as placas não transporta cobertura de nuvens (são
12 fios digitais/analógicos; um canal a mais para nuvem não existe nesta
versão).
