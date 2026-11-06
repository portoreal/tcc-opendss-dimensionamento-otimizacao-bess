__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Otimização da alocação de BESS por Programação Linear Inteira Mista
(PLIM/MILP), com a biblioteca PuLP e o solver CBC.

Antes de chegar aqui, o benefício de cada combinação (barra, tamanho de BESS)
já foi calculado por simulação exaustiva no motor de afundamento de tensão
(estudo_afundamento.py). O que resta ao MILP é um problema de SELEÇÃO — uma
mochila com a restrição adicional de no máximo um tamanho por barra. A
função-objetivo é uma utilidade multicritério (ver "REVISÃO 2026-10-27"
abaixo), com penalização leve pelo custo (peso_custo) e restrições opcionais
de orçamento máximo e de número máximo de unidades.

REVISÃO 2026-10-27 (vigésima primeira sessão) — SELEÇÃO MULTICRITÉRIO:
a decisão arquitetural anterior ("2 estágios sequenciais desacoplados",
em que o MILP olhava apenas para a métrica binária de afundamento e a
economia era avaliada só depois, para o vencedor) foi REVOGADA para o
critério de seleção. O diagnóstico que a motivou foi reproduzido headless
no projeto projetos/teste: os 48 candidatos (6 barras x 8 opções de
catálogo) tinham beneficio=0, porque a métrica era BINÁRIA — uma barra só
"resolvia" o sag ao sair da janela 0,1-0,9 pu, de modo que um BESS capaz de
elevar 0,35 pu para 0,88 pu recebia benefício ZERO. Com benefício nulo em
todos os candidatos, o objetivo de qualquer seleção era
-peso_custo*custo_norm (negativo) e a seleção VAZIA valia 0. O CBC
retornava "Optimal" com lista vazia, o orquestrador pulava a verificação
conjunta/reativo/economia e nenhuma proposta era produzida.

Agora o objetivo é uma SOMA PONDERADA de três termos normalizados:
    peso_qualidade * (ben_sev_i / escala_qualidade)
  + peso_economia  * (econ_i   / escala_economia)
  - peso_custo     * (custo_i  / escala_custo)

onde `ben_sev_i` é o benefício de SEVERIDADE do candidato (métrica
contínua em pu·barra, calculada em otimizacao_bess.py) e `econ_i` é a
economia anual estimada (R$/ano, idem).

REVISÃO 2026-10-27 (vigésima segunda sessão) — ESCALA FÍSICA NO LUGAR DO
MÁXIMO OBSERVADO: os divisores de qualidade e economia são ESCALAS
FÍSICAS fornecidas pelo orquestrador (`escala_qualidade` e
`escala_economia`). Com elas, cada termo passa a ser uma FRAÇÃO DO
POTENCIAL TOTAL:

    qualidade = profundidade de sag ELIMINADA / profundidade total possível
                (janela de sag x número de barras monitoradas);
    economia  = economia anual do candidato / potencial teórico de
                arbitragem (spread tarifário x demanda máxima do caso
                base x duração da ponta x dias equivalentes x 12).

Daí decorre a propriedade que interessa: os pesos passam a ser PESOS
RELATIVOS VERDADEIROS. 1.0 em qualidade vale "eliminar todo o sag
possível"; 1.0 em economia vale "capturar todo o potencial de arbitragem".
São grandezas comparáveis, e por isso podem ser somadas.

MOTIVO (defeito medido na iteração anterior): com denominador por MÁXIMO
OBSERVADO, um máximo minúsculo amplifica o termo correspondente. No
projeto projetos/teste, a falta trifásica na barra da fonte saturava a
profundidade de TODAS as barras em ~0,899 pu; nenhum candidato movia a
barra mais severa, e o máximo de benefício de severidade caía para 9,4e-05
pu·barra. Contra uma economia normalizada por R$ 98 mil/ano, isso é uma
amplificação de ~10.000x — o termo de qualidade dominava o problema por
ruído numérico.

RETROCOMPATIBILIDADE / FALLBACK: quando a escala física é None (sem
tarifa, demanda nula ou spread <= 0 — ver otimizacao_bess.py) ou não
positiva, o divisor volta a ser o máximo observado, com fallback 1.0
quando o máximo é <= 0 ou o campo está ausente. Candidatos no formato
antigo (só `beneficio`) continuam degradando o objetivo para a forma
binária. Esse fallback preserva o comportamento anterior, mas herda o
defeito de amplificação descrito acima: é caminho de exceção, não o caminho
normal.

PROPRIEDADE DE NÃO-VACUIDADE (por que a seleção vazia deixa de vencer):
o candidato de MÁXIMA severidade pontua, no mínimo,
peso_qualidade - peso_custo (termo de economia >= 0, custo normalizado
<= 1); o de MÁXIMA economia pontua, no mínimo, peso_economia -
peso_custo. Com os defaults (peso_qualidade=1.0, peso_economia=1.0,
peso_custo=0.1) esses pisos são 0,9 > 0. Logo a seleção VAZIA (objetivo 0)
nunca é ótima quando existe pelo menos um candidato.
NOTA SOBRE O PISO COM ESCALA FÍSICA: o argumento acima exige termo de
mérito >= 0 e custo normalizado <= 1, o que se verifica sem depender do
divisor (fração negativa só aparece com benefício negativo, isto é,
BESS que AGRAVA o sag). A escala física NÃO é um limite superior
garantido: a escala de economia é o potencial de arbitragem calculado
sobre a importação total do caso base, enquanto a economia de um
candidato inclui também as parcelas de energia ponta que a escala não
modela — um candidato pode, legitimamente, gerar fração > 1 (medido:
6,19 no projeto projetos/teste). Isso só torna o termo MAIOR, nunca
inverte o piso, e o candidato de máxima economia continua sendo o de
maior fração. Com o fallback por máximo observado o piso é 1.0 por
definição do divisor.
EXCEÇÃO DOCUMENTADA: com pesos patológicos em que
peso_custo >= max(peso_qualidade, peso_economia), o piso pode ficar
<= 0 e a seleção vazia volta a poder vencer — configuração considerada
incoerente (o custo anularia os próprios critérios de mérito) e não é
protegida por restrição adicional.

LIMITAÇÃO IMPORTANTE quando max_unidades > 1: o benefício de cada
candidato foi calculado supondo a instalação de APENAS aquele BESS
isoladamente. Somar benefícios de múltiplas unidades linearmente no MILP
produz uma ESTIMATIVA — um limite superior, porque duas unidades podem
estar "salvando" a mesma barra e o ganho não se soma. Por isso o módulo
orquestrador (otimizacao_bess.py) executa uma simulação de VERIFICAÇÃO
CONJUNTA depois da escolha do MILP e reporta o benefício real, não o
estimado, da combinação final.
"""

import pulp


def _normalizador_maximo(valores):
    """Maior valor da lista, com fallback 1.0 quando não há valores ou o
    máximo é <= 0 (evita divisão por zero e anula um critério sem sinal).

    O fallback é 1.0, e não um epsilon, por um motivo prático: um critério
    ausente tem valor 0 em todos os candidatos, então valor/1.0 = 0 e o
    termo simplesmente não pesa. Com epsilon o divisor explodiria.
    """
    maximo = max(valores, default=0.0)
    return maximo if maximo > 0 else 1.0


def otimizar_alocacao_bess(candidatos, max_unidades=1, peso_custo=0.1,
                             custo_maximo=None, peso_qualidade=1.0,
                             peso_economia=1.0, escala_qualidade=None,
                             escala_economia=None):
    """
    candidatos: lista de dicts, cada um com:
        {
            "bus": nome_da_barra,
            "modelo_bess": {"nome":..., "kw":..., "kwh":..., "custo_brl":...},
            "beneficio": int (barras que deixam a condição de sag -
                              métrica BINÁRIA, mantida por compatibilidade),
            "beneficio_severidade": float (opcional; redução de severidade
                              de afundamento em pu·barra - métrica CONTÍNUA),
            "beneficio_econ_anual": float (opcional; economia anual
                              estimada da arbitragem tarifária, R$/ano),
        }

    Campos opcionais ausentes degradam o objetivo para a forma antiga
    (ver nota de retrocompatibilidade no topo do arquivo).

    escala_qualidade / escala_economia: escalas FÍSICAS (limite superior
    do potencial) usadas como denominador dos termos de qualidade e
    economia. `None` (default) ou valor <= 0 faz o divisor cair no
    máximo observado entre os candidatos (fallback retrocompatível,
    sujeito à amplificação de outlier minúsculo descrita no topo).

    Retorna (selecionados, status_do_solver).
    """
    if not candidatos:
        # Sem candidatos não há o que otimizar; o status evita que o
        # chamador confunda "lista vazia" com "solver escolheu nada".
        return [], "Sem candidatos"

    problema = pulp.LpProblem("Alocacao_Otima_BESS", pulp.LpMaximize)

    indices = list(range(len(candidatos)))
    # Uma variável binária por candidato: 1 = instala aquele BESS naquela
    # barra, 0 = não instala. É o "inteira" de PLIM.
    y = pulp.LpVariable.dicts("y", indices, cat="Binary")

    # Normalizadores calculados UMA vez sobre o conjunto de candidatos.
    # O termo de qualidade usa a severidade contínua quando disponível;
    # sem o campo, cai para a métrica binária 'beneficio' (forma antiga).
    def _valor_qualidade(c):
        if "beneficio_severidade" in c:
            return c["beneficio_severidade"] or 0.0
        return c["beneficio"]

    def _valor_economia(c):
        return c.get("beneficio_econ_anual", 0.0) or 0.0

    # Escala física quando fornecida e positiva; senão, máximo observado.
    beneficio_max = (
        float(escala_qualidade)
        if escala_qualidade is not None and float(escala_qualidade) > 0
        else _normalizador_maximo([_valor_qualidade(c) for c in candidatos]))
    economia_max = (
        float(escala_economia)
        if escala_economia is not None and float(escala_economia) > 0
        else _normalizador_maximo([_valor_economia(c) for c in candidatos]))
    custo_max_catalogo = _normalizador_maximo(
        [c["modelo_bess"]["custo_brl"] for c in candidatos])

    problema += pulp.lpSum(
        y[i] * (
            peso_qualidade * (_valor_qualidade(candidatos[i]) / beneficio_max)
            + peso_economia * (_valor_economia(candidatos[i]) / economia_max)
            - peso_custo * (candidatos[i]["modelo_bess"]["custo_brl"] / custo_max_catalogo)
        )
        for i in indices
    )

    # Uma barra, um BESS. Duas unidades na mesma barra competiriam pelo mesmo
    # ponto de conexão e o ganho somado no MILP seria fictício.
    barras_unicas = sorted(set(c["bus"] for c in candidatos))
    for bus in barras_unicas:
        indices_da_barra = [i for i in indices if candidatos[i]["bus"] == bus]
        problema += pulp.lpSum(y[i] for i in indices_da_barra) <= 1

    # Teto global de unidades, independente de barra.
    problema += pulp.lpSum(y[i] for i in indices) <= max_unidades

    # Orçamento total (opcional). Sem custo_maximo, a restrição não existe.
    if custo_maximo is not None:
        problema += pulp.lpSum(
            y[i] * candidatos[i]["modelo_bess"]["custo_brl"] for i in indices
        ) <= custo_maximo

    # msg=False silencia o log do CBC no console da interface.
    problema.solve(pulp.PULP_CBC_CMD(msg=False))

    status = pulp.LpStatus[problema.status]
    selecionados = [
        candidatos[i] for i in indices
        if y[i].value() is not None and y[i].value() >= 0.5
    ]

    # Ordenação apenas para leitura do resultado; não interfere no ótimo.
    selecionados.sort(key=lambda c: c["beneficio"], reverse=True)

    return selecionados, status