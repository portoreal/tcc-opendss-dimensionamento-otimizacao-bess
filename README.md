# TCC OpenDSS — Dimensionamento e Otimização do Posicionamento de BESS para Mitigação de Afundamentos de Tensão

Ferramenta de engenharia em Python sobre o motor OpenDSS que implementa o processo completo de
dimensionamento e otimização do posicionamento de sistemas de
armazenamento de energia (BESS) para mitigação de afundamentos de tensão: simula e mapeia os
cenários de afundamento, formula e resolve a seleção da localização e do porte por programação
linear inteira mista (PLIM) com critérios combinados de qualidade de energia e economia
tarifária, e avalia o impacto econômico da configuração selecionada. O processo de modelagem e
simulação é validado contra os sistemas de teste IEEE 13, 34, 37 e 123 nós, e o método completo
é demonstrado em um estudo de rede de distribuição — da modelagem ao relatório de ROI/DRE,
incluindo a geração de firmware de bancada em ESP32 e Arduino.

Trabalho de Conclusão de Curso de Engenharia Elétrica — Universidade Católica de Santa Catarina
(Jaraguá do Sul/SC), 2026. Autoria: Pedro Henrique Sousa Pinheiro. Orientação: Douglas Flores
Copetti. Coorientação: Fabiano Luz Cardoso.

## Documentação

- [Manual do Usuário](doc/manual_usuario.html) — operação das telas, interpretação dos
  resultados e solução de problemas.
- [Manual do Desenvolvedor](doc/manual_desenvolvedor.html) — arquitetura, contratos entre
  módulos, regras de manutenção, procedência dos dados e os achados do motor de simulação.

## Funcionalidades

- **Projeto** — cria e abre a pasta de trabalho de um estudo, com as subpastas `rede/`
  (topologia e parâmetros), `curvas/` (LoadShapes e curvas características) e
  `dimensionamento/` (memoriais e saídas).
- **Editor de Rede** — desenho gráfico da rede com barras arrastáveis em *canvas* e árvore
  hierárquica; linhas e transformadores aceitam campos opcionais de ensaio (`c1`/`c0` e
  `loadloss`/`noloadloss`), que ficam em branco quando não há dado de placa.
- **Exportador DSS** — converte `rede.json` em scripts OpenDSS executáveis, com curvas padrão
  por dia da semana para os elementos que não têm curva própria.
- **Dimensionamento** — cálculo de condutores (queda de tensão), transformadores (margem de
  carga e XHL por faixa), BESS por autonomia/DoD/eficiência, geração fotovoltaica por HSP,
  banco de capacitores ou reator e grupo gerador, cada um com memorial de cálculo.
- **Otimização de BESS** — varredura exaustiva barra × porte de catálogo, seleção por PLIM
  multi-critério (PuLP/CBC), verificação conjunta do vencedor por simulação e análise de
  reativo segundo o PRODIST.
- **Economia** — QSTS de 24 h com despacho do BESS por estado de carga (SoC) e cálculo de
  payback.
- **Relatório ROI/DRE em HTML** — receitas contra investimento, projeção de payback, quatro
  gráficos embutidos e incentivos regulatórios com fonte declarada.
- **Simulação ao Vivo** — painel animado de operação multi-dia, com nuvens sobre a geração
  fotovoltaica, faltas interativas e exportação dos gráficos.
- **Afundamento de tensão** — varredura de cenários de falta com classificação de severidade e
  memorial de cálculo.
- **Reativo** — análise e proposição de banco de capacitores ou reator para compensação.
- **Validação IEEE** — comparação do pipeline contra os sistemas de teste IEEE 13, 34, 37 e 123
  nós, com exportação para Excel, desenho de topologia e conversão em Projeto editável.
- **Exportadores Arduino/ESP32** — sketches pré-prontos de bancada mais a parametrização `.h`
  gerada por projeto a partir dos resultados das simulações.
- **Debugger de integridade** — 11 verificações do ambiente e do projeto antes de abrir o menu.

## Arquitetura

A abertura é uma cadeia de três etapas: `tcc_opendss.bat` ativa o ambiente virtual e chama
`verificar_dependencias.py` (verifica e instala pacotes faltantes), que dispara o debugger de
integridade com as 11 verificações; ao concluir, é o próprio debugger que lança o menu principal
(PySide6). Exit code 0 abre o menu; exit code 1 (janela fechada sem concluir) não abre.

Cada módulo de interface roda em **processo próprio**, lançado pelo menu via
`python -m bibliotecas.<módulo> --projeto <raiz do projeto>`, com o diretório de trabalho na raiz
do projeto. Não há janela compartilhada entre processos — o parâmetro `parent` é ignorado por
contrato.

`rede.json` é a **fonte da verdade** do modelo elétrico: os estudos (otimização, afundamento,
economia) partem dele e exportam uma cópia temporária para o motor, de modo que o projeto em
disco nunca é alterado por uma simulação.

## Resultados de validação

Comparação do pipeline contra os resultados oficialmente publicados pelo IEEE PES Distribution
System Analysis Subcommittee, com tolerância de 0,5% no erro máximo de tensão:

| Sistema | Erro máximo | Status |
| --- | --- | --- |
| 13 nós | 0,135% | Aprovado |
| 34 nós | 0,141% | Aprovado |
| 37 nós (original) | 7,68% | Reprovado — impedância da fonte e dos reguladores |
| 37 nós (corrigido) | 0,0147% | Aprovado |
| 123 nós (original) | 1,547% | Reprovado — barra 610, resultado bruto |
| 123 nós (corrigido) | 0,136% | Aprovado (1 exceção documentada) |

A entrada de 123 nós corrigida mantém uma única exceção documentada, a barra 610 — secundário
delta-delta isolado, sem carga e sem terra, onde a tensão fase-neutro é fisicamente
indeterminada. A exceção tem veredito quantificado: as tensões de **linha** dessa barra, as
únicas grandezas determinadas pela razão de transformação, batem com o gabarito em 0,021%.

**A validação funcionou como auditoria de implementações de terceiros.** Os arquivos `.dss`
disponíveis publicamente reproduzem o *nameplate* oficial, mas assumem premissas de modelagem
distintas das do documento de solução do IEEE — e a divergência aparece como erro numérico. A
causa raiz do resíduo de 7,68% em 37 nós é a impedância série efetiva dos transformadores de dois
enrolamentos, regida pelo parâmetro de perdas sob carga quando não há resistência percentual
declarada por enrolamento; idealizar apenas a resistência declarada não corrige o modelo.

### Resultado do estudo de referência

No estudo de demonstração (rede de distribuição com 6 barras candidatas, 48 candidatos — 6 barras × 8 portes de catálogo —, faltas trifásica e monofásica em duas barras, tarifa verde A4, curvas de quinta-feira), o método compara todos os candidatos simulados e seleciona o BESS Comercial de 50 kW/100 kWh (R$ 300.000) na barra B4: melhoria da profundidade de afundamento nas 5 barras monitoradas, fator de potência de 0,972 conforme ao PRODIST Módulo 8, economia de R$ 66,48/dia (R$ 17.551,17/ano) e payback de 17,09 anos — a verificação conjunta confirma o benefício real da configuração, que substitui a estimativa da soma de benefícios individuais.

## Destaques técnicos

1. **Seleção multi-critério no PLIM.** O objetivo combina qualidade de energia (severidade
   contínua em pu·barra), economia anual estimada e custo do equipamento, cada termo normalizado
   pela sua **escala física** — janela de afundamento e número de barras afetadas no caso base
   para qualidade, spread tarifário e demanda máxima para economia. Normalizar por escala física,
   e não pelo máximo observado, faz dos pesos pesos relativos verdadeiros. A formulação garante a
   **não-vacuidade da seleção**: com candidatos disponíveis, a seleção vazia não é ótima.

2. **Semântica de colapso.** Um cenário que não converge — falta severa somada a injeção forte —
   não pode ser lido como ausência de afundamento. O candidato recebe um valor sentinela no
   **limite inferior** da janela de afundamento em todas as barras monitoradas, de modo que a
   divergência nunca é creditada como benefício. Sem essa regra, um BESS superdimensionado era
   premiado por derrubar a simulação.

3. **Verificação conjunta.** A soma dos benefícios individuais dos candidatos selecionados é
   apenas um **limite superior** — a atuação de dois BESS no mesmo cenário de falta não é a soma
   das atuações isoladas. O valor real da configuração vencedora é apurado por simulação do
   conjunto, e não pela agregação das parcelas.

4. **Achados do motor dss-python 0.15.7.** Comportamentos verificados por experimento controlado,
   registrados porque alteram resultados sem emitir erro:
   - `Text.Command` aceita **um comando por atribuição**; bloco multi-linha falha com erro de
     compilação.
   - `SetBusXY` só funciona **após** o Compile: durante a compilação a lista de barras ainda não
     está materializada.
   - A convenção de sinal de `TotalPower` é **da instância do motor**, não uma constante
     documentada — precisa ser calibrada com um micro-circuito de importação conhecida.
   - Em transformadores de dois enrolamentos há **hierarquia entre `%r` e `%LoadLoss`**: a
     resistência explícita por enrolamento prevalece; o parâmetro de perdas sob carga só governa
     quando não há resistência declarada, e `%r=0` explícito zera a resistência mesmo com
     `%LoadLoss` declarado.
   - `%noloadloss` **isolado** desloca o ponto de operação do transformador: o par de ensaio deve
     ser preenchido completo.
   - Linhas sem `c1`/`c0` declarados recebem shunt capacitivo implícito de **3,4 nF/km** e
     **1,6 nF/km**.
   - O `Vminpu` padrão (0,9) do elemento Storage degrada a injeção para impedância constante
     dentro da faixa de afundamento; o modelo usa **0,05**.

   Detalhes completos no [Manual do Desenvolvedor](doc/manual_desenvolvedor.html).

## Trabalhos futuros

1. **Bancada experimental** — plataforma com ESP32 (controle do BESS) e Arduino Mega 2560 R3
   (representação da microrrede), firmwares parametrizados a partir das simulações (o módulo de
   parametrização já existe na ferramenta), para o ensaio físico e a validação comparativa
   computacional × experimental.
2. **Sensoriamento via IoT** — monitoramento em tempo real do dispositivo físico, com coleta de
   dados de operação para o previsionamento de demanda e de geração.
3. **Inteligência artificial nas decisões** — modelos de previsão e de decisão treinados sobre os
   dados coletados, evoluindo o despacho atual baseado em regras de estado de carga.
4. **Catálogo ampliado** — mais opções por fornecedores e faixas de preço variadas, ampliando o
   espaço combinatório da otimização.
5. **Monitoramento remoto e redes reais** — implantação do monitoramento remoto e aplicação do
   método a redes de distribuição reais, com dados de ocorrências registradas.

## Stack

Python 3, `dss-python` (DSS-Extensions) como motor OpenDSS, PySide6 para as interfaces, PuLP com
o solver CBC embutido para o PLIM, matplotlib para gráficos e openpyxl para exportação Excel.

## Como executar

1. **Executável** (modo distribuído) — baixe o pacote na página de
   [Releases](https://github.com/portoreal/tcc-opendss-dimensionamento-otimizacao-bess/releases).
   Não exige Python instalado.
2. **Código-fonte** (modo de desenvolvimento) — execute `tcc_opendss.bat` na raiz do
   repositório. O script cria o `venv` e instala as dependências na primeira execução; requer
   Python 3 e internet apenas nesse primeiro momento.

## Mapa de pastas

| Pasta | Conteúdo | Procedência |
| --- | --- | --- |
| `tcc_opendss/` | Código-fonte (`bibliotecas/`), projetos (`projetos/`), sketches de bancada (`hardware/`), `validacao_ieee/` e `verificar_dependencias.py` | **Fruto original deste trabalho** |
| `doc/` | `manual_usuario.html` e `manual_desenvolvedor.html` | **Fruto original deste trabalho** |
| `IEEE/` | `feeder13/34/37/123.zip` e os demais sistemas de teste publicados | **Sistemas de teste oficiais do IEEE PES DSASC** — gabarito oficial, © IEEE |
| `OpenDSS/` | Binários do motor EPRI OpenDSS (`.exe`/`.dll` — COM), legados e **não usados em runtime** (o motor é o `dss-python` do pip) | EPRI — OpenDSS oficial |
| `OpenDSS/tutorials_files-master/` | Tutoriais e materiais de eventos (UFRGS, Mackenzie, UFSM, PES Day) | **Materiais de treinamento da comunidade OpenDSS** — material de estudo, **NÃO gabarito** |
| `exe_empacotado/` | Destino futuro do empacotamento em `.exe` | Saída de build |

## Procedência

O gabarito de validação vem exclusivamente da documentação oficial do IEEE (`IEEE/`) — os
documentos de solução e as planilhas de dados publicados pelo PES Distribution System Analysis
Subcommittee.

Os arquivos `.dss` de terceiros usados como ponto de partida da simulação são **instrumento de
simulação, sujeito a auditoria**, e não fonte de referência numérica: as divergências encontradas
foram investigadas uma a uma e estão documentadas nos resultados de validação.

Os tutoriais da comunidade OpenDSS (`OpenDSS/tutorials_files-master/`) são material de estudo e
**não têm valor de referência numérica**.

## Licença

Distribuído sob a [LICENSE.md](LICENSE.md) — software livre para fins **não comerciais**:
uso, estudo, modificação e redistribuição permitidos; comercialização proibida.

## Citação

> PINHEIRO, Pedro Henrique Sousa. **Dimensionamento e otimização do posicionamento de sistemas
> de armazenamento de energia para mitigação de afundamentos de tensão em sistemas de
> distribuição.** 2026. Trabalho de Conclusão de Curso (Engenharia Elétrica) — Universidade
> Católica de Santa Catarina, Jaraguá do Sul, 2026.
