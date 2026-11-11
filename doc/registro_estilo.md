# Registro da verificação de estilo

Data: 2026-10-13

Fonte dos critérios: `C:\Users\hpinheiro\Downloads\Diretrizes de estilo de escrita.md`
— lista de conectivos "de IA" a usar com moderação, proibição de hedging genérico
("é fundamental compreender que", "de forma geral, pode-se afirmar que") e de fechos
de parágrafo de resumo. A diretriz exige ainda: nunca inventar dados, nunca transformar
o registro em informal.

Ferramenta de checagem: `doc/verificar_estilo.py` (stdlib apenas). Varre comentários `#`
e docstrings dos `.py` (via `tokenize` + `ast`; código e strings comuns ficam de fora),
o texto integral dos `.md` e o texto dos `.html` fora de `<style>`/`<script>`.
Resultado atual: **APROVADO — 0 marcadores fora das exceções, 52 arquivos varridos.**

## Marcadores procurados

Além disso · É importante destacar · É importante ressaltar · Nesse sentido ·
Vale ressaltar · Em suma · de forma geral · Dessa forma · É fundamental ·
cabe destacar · Importante destacar · ressalta-se que · Vale lembrar ·
deve-se notar · Em resumo · Em síntese · se faz necessário · faz-se necessário ·
pode-se observar · é possível observar que

## Tabela por artefato

| Arquivo | Linhas | Marcadores encontrados | Decisão | Justificativa |
|---|---:|---:|---|---|
| `tcc_opendss/bibliotecas/validacao_ieee.py` | 888 | 1 antes / 0 depois | ajustado | Único comentário com marcador ("Portanto" como conectivo no comentário de L416-421). O conectivo foi eliminado pela pontuação: `…o tratamento é aplicado;` + `'excecoes_documentadas' fica deliberadamente vazio aqui.` Nenhuma linha de código ou string tocada — `"excecoes_documentadas": {}` permanece intacto. |
| `tcc_opendss/bibliotecas/curvas_semanais_ui.py` | 416 | 0 | mantido-legítimo | Ocorrências de "é válido" são uso semântico (predicado de validade do resultado), não conectivo de IA. Não está sequer na lista de marcadores; registrado para deixar a decisão explícita. |
| `tcc_opendss/bibliotecas/exportador_arduino.py` | 903 | 0 | mantido-legítimo | Idem: "é válido"/"NÃO é válido" com sentido de validade semântica em docstring/comentário. Preservado. |
| `tcc_opendss/bibliotecas/memorial_calculo_economia.py` | 168 | 0 | mantido-legítimo | "Portanto" em L57 ocorre em **string de relatório gerado**, não em comentário nem docstring. Fora do escopo de varredura por decisão de escopo (edições em `.py` restritas a comentários) e uso moderado. As 14 linhas detectadas no arquivo são apenas comentários `#`, todos sem marcador. |
| `tcc_opendss/bibliotecas/*.py` (demais 44 arquivos) | ver saída do verificador | 0 | conforme — varredura sem marcadores | Comentários e docstrings autorais. Soma dos 47 `.py` de `bibliotecas/`: 28.432 linhas; nenhuma ocorrência além das três acima. |
| `README.md` | 263 | 0 | ajustado (2 correções factuais) | Ver seção "Correções factuais no README". Nenhum marcador de estilo; a intervenção foi de **exatidão numérica**, exigida pela diretriz "nunca inventar dados", não de prosa. |
| `doc/manual_usuario.html` | 1177 | 0 | conforme-sem-alteração | Prosa autoral; varredura do texto fora de `<style>`/`<script>` sem marcadores. |
| `doc/manual_desenvolvedor.html` | 1784 | 1 antes / 0 depois | ajustado | Ver seção "Correção no manual do desenvolvedor". |
| `tcc_opendss/hardware/README.md` | 248 | 0 | conforme-sem-alteração | Prosa autoral, sem marcadores. |
| `LICENSE.md` | 67 | 0 | conforme-sem-alteração | Texto jurídico. Semântica intocável; nenhum marcador encontrado na varredura. Não foi editado. |

## Correções factuais no README

Duas edições, ambas com os números conferidos nos dumps do próprio projeto — nada
estimado, nada convertido à mão sem lastro.

### Estudo de referência (seção "Resultado do estudo de referência")

O método econômico do estudo principal migrou do dia isolado de quinta-feira para a
**semana completa**, com a ponta restrita aos dias úteis. O parágrafo descrevia a
premissa antiga e, por consequência, números antigos.

Fonte: `tcc_opendss/projetos/teste/dump_estudo_otimizacao.json`,
caminho `vencedor.economia_candidato`:

| Campo do dump | Valor bruto | No README |
|---|---:|---:|
| `economia_diaria` | 66.48169830289845 | R$ 66,48 |
| `economia_semanal` | 231.3056080197192 | R$ 231,31 |
| `economia_anual` | 12027.891617025398 | R$ 12.027,89 |
| `payback_anos` | 24.942027210766685 | 24,94 anos |

Conferência aritmética: 231,31 × 52 = 12.028,12; o valor do dump (12.027,89) usa a
semana sem arredondamento (231,3056 × 52 = 12.027,89). O README adota o número do
dump, não o produto dos valores arredondados.

O dump conserva, em `economia_vencedor.escalares`, os campos antigos do regime de dia
representativo (`economia_anual` = 17.551,17, `payback_anos` = 17,09). Eles permanecem
no arquivo como registro da escala anterior e **não** são o resultado vigente — por isso
saíram do README. A menção "curvas de quinta-feira" foi substituída por "curvas padrão de
cada dia da semana com a ponta restrita aos dias úteis", que descreve a premissa atual;
`config.dia_curvas_padrao = Quinta` segue existindo como dia representativo dentro da
semana, não como escopo da economia.

### Estudo em rede IEEE 13 nós (seção "### Estudo de demonstração em rede IEEE 13 nós")

O parágrafo atribuía ao estudo de referência parâmetros que o estudo 13 nós apenas
herda parcialmente — e os reunia sob "repetem a configuração de referência", o que
ficou incorreto depois da mudança acima. A redação passou a separar o que é herdado
(tarifa e janela de ponta) do que é fixado localmente.

Fonte: `tcc_opendss/projetos/ieee13/estudo_otimizacao.json`,
objeto `resultado_economia`:

| Campo | Valor |
|---|---:|
| `dias_equivalentes_mes` | 22 |
| `horario_ponta_inicio` | 18 |
| `horario_ponta_fim` | 21 |

Os 22 dias/mês e a ponta 18h–21h permanecem corretos no estudo 13 nós, mas como
parâmetros próprios (`dias_equivalentes_mes` da anualização do **dia representativo**),
não como repetição dos 22 dias do estudo de referência — que agora anualiza pela semana.
O restante do parágrafo (faltas monofásica sólida e de alta impedância, peso de custo
0,01, barras 634/671/675/692/670) não foi alterado.

## Correção no manual do desenvolvedor

`doc/manual_desenvolvedor.html`, L1481, seção "Orçamento de tempo". A frase estava
quebrada no arquivo original: `…leve o tempo para muito` + `além disso introduziu
recompilação desnecessária…`. O "além disso" ali não era conectivo de IA — era
resíduo de uma locução de limite ("muito além disso") partida ao meio, e o verbete
casava com a lista de marcadores.

Texto final: `…qualquer mudança que leve o tempo para muito além do orçamento,
introduziu recompilação desnecessária ou perda do MotorReutilizavel.`

O diagnóstico inicial previa zero marcadores nos manuais; a varredura apontou esta
ocorrência e ela foi confirmada contra o arquivo antes da edição. As demais linhas do
documento não foram tocadas.

## Exceções documentadas (não marcadas)

1. **"é válido" / "NÃO é válido"** — uso semântico, predicado de validade de um
   resultado. Não é conectivo e não consta da lista de marcadores. Ocorre em
   `curvas_semanais_ui.py` e `exportador_arduino.py`. Mantido.
2. **"Portanto" em string de relatório** — `memorial_calculo_economia.py` L57. Está em
   texto gerado para o memorial, não em comentário. Edições em `.py` foram restritas a
   comentários por decisão de escopo, e o uso é moderado. Mantido.

## Reprodutibilidade

```
python doc/verificar_estilo.py     # esperado: VEREDITO: APROVADO (exit 0)
python doc/verificar_artigo.py     # artigo .tex — não tocado nesta verificação
python -m py_compile tcc_opendss/bibliotecas/validacao_ieee.py
```

### Estado de `verificar_artigo.py` nesta verificação

`conference_101719.tex` **não foi tocado** por esta verificação (`git diff` sem
alteracão no arquivo). O verificador do artigo aponta REPROVADO com 36 falhas, todas
relativas à migração do artigo para a semana completa, que estava em curso em outro
ramo de trabalho no mesmo lote: abstract sem `12.027,89`/`24,94`, marcadores antigos
ainda no corpo (`17\,551`, `17{,}09`, `22 \times 12`), figura `fig:curvas_semana`
ausente e seção complementar IEEE 13 não delimitável.

As checagens estruturais que esta verificação poderia afetar passam: (a) 18 refs
resolvidas, 0 sem rótulo; (b) todos os ambientes balanceados; (c) as tensões de
referência e a invariância de `%stored` conferem contra o JSON (`b4` 0,8723/0,8758/
0,9312; `b5` 0,8484/0,8517/0,9055).

O item (c) do critério de aceite — "verificador do artigo APROVADO" — **permanece
pendente** por depender daquele trabalho, não desta tarefa. Não foi alterado o artigo
para forçar aprovação.

O verificador usa `utf-8-sig` na leitura (tolera BOM) e `errors="replace"`, de modo que
um caractere inválido não interrompe a varredura. A numeração de linha das docstrings é
confirmada comparando o valor da string com a linha fonte correspondente; quando a
comparação falha (docstring de uma linha só), vale a posição do nó AST — o marcador
pode aparecer deslocado em uma linha, nunca omitido.
