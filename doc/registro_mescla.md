# Registro de Mescla — Backup → `conference_101719.tex`

**Data:** 2026-11-11
**Fonte (backup):** `C:/Users/hpinheiro/Downloads/conference_101719 2.tex`
**Diretriz de estilo:** `C:/Users/hpinheiro/Downloads/Diretrizes de estilo de escrita.md`
**Destino:** `conference_101719.tex` (raiz do repositório)
**Critério:** o parágrafo do backup substitui verbatim o parágrafo correspondente do atual, preservando `\ref`, `\cite` e `\label`. Onde o parágrafo atual já era materialmente idêntico (diferença apenas de quebra de linha), registrou-se "sem divergência material" e nenhum edit foi feito. Números proibidos no estudo principal (`17\,551`, `17{,}09`, `56\,157`, `d = 22`) não foram introduzidos.

## Decisões por bloco

| Bloco (linhas do backup) | Região do artigo | Decisão | Antes → Depois (1 linha) |
|---|---|---|---|
| Rodada final — Bloco 1 (abertura de `subsec:economia`) | Parágrafo final da fundamentação, imediatamente antes da Seção Metodologia (`\ref{subsec:economia}` na linha 193) | Substituído | "Por fim, ... fundamenta-se na estrutura tarifária horária" → "A avaliação da viabilidade econômica ... apoia-se na estrutura tarifária horária" |
| Rodada final — Bloco 2 (abertura de `subsec:validacao`) | Parágrafo de abertura de "Validação do Modelo Computacional" | Substituído + **adaptação registrada**: verbo ausente no backup corrigido ("que dependem diretamente") | "... simulação adotado, de modo a garantir que os resultados obtidos ... Essa etapa é fundamental em trabalhos que utilizam ferramentas de simulação como instrumento central de análise, uma vez que a confiabilidade das conclusões obtidas nas etapas subsequentes ... depende diretamente" → "simulação adotado, para que os resultados obtidos ... Em trabalhos cujo instrumento central é a simulação, essa etapa condiciona a confiabilidade das conclusões obtidas nas fases seguintes ..., que dependem diretamente" |
| Rodada final — Bloco 3 (fontes documentais) | Parágrafo das duas fontes documentais, `subsec:validacao` | Mescla parcial (só a abertura estilizada); fecho atual preservado após "mantido por" | "É importante registrar, por rastreabilidade metodológica, a distinção entre as duas fontes documentais utilizadas nesta etapa. Os documentos de referência" → "As duas fontes documentais desta etapa são distintas e convém não confundi-las. Os documentos de referência" |
| Rodada final — Bloco 4 (reguladores, solução em duas etapas) | Parágrafo da "Validação por reprodução do ponto de operação publicado", contém "banda morta" e "duas etapas" | Substituído até "distribuída pelo comitê"; continuação atual preservada | "Dessa forma, a comparação direta e rigorosa com os valores oficialmente publicados requer que o modelo seja resolvido em duas etapas" → "Comparar diretamente com os valores oficialmente publicados exige, então, resolver o modelo em duas etapas"; "de modo a eliminar o grau de liberdade ... e isolar, assim, exclusivamente" → "Assim se elimina o grau de liberdade ... e se isola, exclusivamente" |
| Rodada final — Bloco 5 (`subsec:cenarios`, medição) | Parágrafo "Para cada combinação de barra candidata ..." | Substituído | "... durante o evento, de modo a avaliar sua capacidade de reduzir ..." → "... durante o evento. O que se mede é a sua capacidade de reduzir ..." |
| Rodada final — Bloco 6 (`subsec:cenarios`, modelagem do armazenamento) | Parágrafo do `\textit{low voltage ride-through}` / "quadrado da tensão" | Substituído (pontuação/materialização da oração) | "de 0,9~pu -- de modo que, sem o ajuste, um sistema de 300~kW" → "de 0,9~pu. Sem o ajuste, um sistema de 300~kW" |
| Rodada final — Bloco 7 (`subsec:Aquisição de dados`) | Parágrafo "Os resultados obtidos nas simulações da etapa anterior ..." | Substituído | "Essa estruturação é fundamental para estabelecer, de forma sistemática, a relação entre ..." → "É essa estruturação que permite estabelecer a relação, sistemática e verificável, entre ..." |
| Rodada final — Bloco 8 (`subsec:otimizacao`, mochila) | Parágrafo PLIM/`knapsack` | Mescla parcial (ajuste até "seja"); continuação preservada | "por barra, de modo que melhoras parciais sejam creditadas proporcionalmente" → "por barra, o que credita melhoras parciais proporcionalmente" |
| Rodada anterior — justificativa/abertura da introdução | Introdução | Mesclado | parágrafo de justificativa da introdução reescrito conforme backup |
| Rodada anterior — introdução do PLIM | `subsec:otimizacao` | Mesclado | abertura do PLIM alinhada ao backup |
| Rodada anterior — fundamentação | Fundamentação teórica | Mesclado | redação da fundamentação alinhada ao backup |
| Rodada anterior — cinco etapas | Seção Metodologia, abertura | Mesclado | enumeração das cinco etapas conforme backup |
| Rodada anterior — particularidades do 37 nós | `subsec:validacao`, após solução em duas etapas | Mesclado | parágrafo de leitura crítica da documentação do 37 nós |
| Rodada anterior — fecho da modelagem | `subsec:modelagem` | Mesclado | fecho do parágrafo de modelagem da rede |
| Rodada anterior — Sugiyama/layout | Descrição da ferramenta computacional | Mesclado | referência ao algoritmo de Sugiyama para layout |
| Rodada anterior — "O que se mede" | `subsec:cenarios` | Já aplicado anteriormente (revalidado nesta rodada) | frase de medição do benefício já presente; sem novo edit |
| Rodada anterior — fecho da otimização | `subsec:otimizacao` | Mesclado | fecho do parágrafo de otimização |
| Rodada anterior — "Da configuração selecionada" | `subsec:economia` / interface com resultados | Mesclado | parágrafo "Da configuração selecionada ..." |
| Rodada anterior — consolidação | Resultados | Mesclado | parágrafo de consolidação dos resultados |
| Rodada anterior — efeito de cada resolução | Discussão dos resultados | Mesclado | parágrafo sobre efeito de cada resolução simulada |
| Rodada anterior — escopo da conclusão | Conclusão | Mesclado | delimitação do escopo na conclusão |
| Rodada anterior — item (vi) faixas de curto-circuito | Lista de contribuições/itens da revisão | Mesclado | item (vi) sobre faixas de curto-circuito |
| Seção IEEE 13 — estudo complementar | Subseção complementar do sistema de 13 barras (corpo final do artigo) | Mesclada com **2 adaptações** | (1) "Os parâmetros seguem o estudo principal; a economia apura-se sobre o dia representativo, com $d = 22$ dias equivalentes por mês"; (2) retornos "24,94 pela semana completa" / "13,38 pelo dia representativo" |
| SKIP — abstract antigo | Abstract | Ignorado (motivo: já restaurado com os números novos) | sem ação |
| SKIP — σ_E antigo `56.157` | Fundação/economia | Ignorado (motivo: valor antigo; número proibido no corpo) | sem ação |
| SKIP — números `17.551` / `17,09` / `0,31253` / `0,30740` | Estudo principal | Ignorado (motivo: não introduzir números do estudo principal antigo) | sem ação |
| SKIP — "economia diária, mensal e anual" | `subsec:economia` | Ignorado (motivo: redação superada pela formulação em `d` dias equivalentes) | sem ação |
| SKIP — `[htbp]` | Figuras/tabelas | Ignorado (motivo: o artigo adotou `[H]`) | sem ação |
| SKIP — parágrafo do solver "ramo-e-corte" | `subsec:otimizacao` | Ignorado (motivo: já presente no artigo) | sem ação |

## Adaptações registradas

- **Bloco 2:** o backup omitia o verbo da oração final ("que depend[em] diretamente da correção do modelo"). Corrigido para "que dependem diretamente", mantendo a concordância com "conclusões". Registrado como adaptação deliberada, não como divergência de mérito.

## Validação

Executado `python doc/verificar_artigo.py` após a aplicação dos 8 blocos: **RESULTADO: APROVADO**.

## Histórico

- 2026-11-11 (tarde): estado final reaplicado ao arquivo após reversão acidental pelo git restore de um ator concorrente; verificar_artigo.py APROVADO novamente.
