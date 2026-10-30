__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Orquestrador do estudo de otimização de alocação de BESS: executa o
caso base (sem BESS), varre todas as combinações (barra candidata x
opção de catálogo) — calculando para CADA candidato tanto o benefício
de qualidade de energia (métrica binária E métrica contínua de
severidade, em pu·barra) quanto a economia anual estimada da arbitragem
tarifária —, delega a seleção ótima MULTI-CRITÉRIO para o MILP e, por fim,
executa uma simulação de verificação conjunta da configuração vencedora,
a análise de necessidade de compensação reativa, E a análise de economia
de energia (arbitragem tarifária ponta/fora ponta) para essa mesma
configuração vencedora.

REVISÃO 2026-10-27 (vigésima primeira sessão): a seleção do MILP passou
a combinar qualidade de energia E economia de energia (além do custo).
O fluxo de verificação do vencedor (verificação conjunta, reativo,
economia completa e memoriais) permanece INALTERADO — a diferença é que
ele agora sempre roda, porque a seleção vazia deixou de ser ótima.
Ver o diagnóstico completo no docstring de otimizacao_milp.py.

Gera também um MEMORIAL DE CÁLCULO textual para cada uma dessas análises
(ver memorial_calculo_afundamento.py e memorial_calculo_economia.py)."""

from typing import Optional

from . import estudo_afundamento
from . import otimizacao_milp
from . import reativo_analise
from . import economia_energia
from . import memorial_calculo_afundamento as memorial_calc
from . import memorial_calculo_economia as memorial_econ
from .catalogo_bess import CATALOGO_BESS_PADRAO
from .tarifas_energia import TarifaEnergia


def _profundidades_por_barra(resultado, limite_superior):
    """Profundidade de afundamento (pu) por barra, a partir do resultado
    de estudo_afundamento.rodar_estudo.

    TRANSPARÊNCIA TÉCNICA (métrica contínua de severidade): a métrica
    binária 'beneficio' só reconhece a barra que SAI da janela de
    afundamento (0,1 a 0,9 pu) — um BESS que eleva uma barra de 0,35 pu
    para 0,88 pu não recebe NENHUM crédito, embora tenha melhorado 0,53 pu
    de tensão. Aqui a severidade é contínua:

        profundidade(barra, cenário) = max(0, limite_superior - min(pu))
        profundidade(barra) = MÉDIA entre os cenários de falta

    A barra faltosa do cenário é EXCLUÍDA do cálculo daquele cenário,
    exatamente como em estudo_afundamento._classificar_sag (a tensão no
    próprio ponto do defeito é dominada pela impedância de falta e não
    representa o que o BESS consegue mitigar).

    CORREÇÃO 2026-10-30 (semântica de COLAPSO em cenários não
    convergentes — ver estudo_afundamento.rodar_estudo): o código
    anterior entrava com 'pu' vazio no cenário divergente, que então NÃO
    contribuía para a profundidade — mas o candidato divergente ainda
    herdava a profundidade total do baseline como "benefício" (crédito
    sem medição nenhuma). Agora cada cenário divergente é tratado como
    COLAPSO DE TENSÃO: cada barra monitorada (exceto a faltosa) recebe
    o SENTINEL pu = limite_inferior, logo CONTRIBUI com profundidade de
    janela completa (limite_superior - limite_inferior) — o candidato
    que diverge passa a ser PENALIZADO (S_i <= 0), nunca mais creditado
    por um cenário que não foi medido. A flag 'convergiu' em
    detalhe_por_falta registra quais cenários são sentinels de colapso
    e quais são medições reais.

    CORREÇÃO 2026-10-27 (vigésima segunda sessão) — AGREGAÇÃO POR MÉDIA,
    NÃO POR MÁXIMO: a agregação por MÁXIMO saturava a métrica quando
    existe um cenário em que TODA a rede colapsa. Defeito medido no
    projeto projetos/teste: a falta trifásica sólida na barra da FONTE
    (B1) levava todas as barras a ~0,001 pu, logo a profundidade de cada
    barra saturava em ~0,899 pu (o limite da janela) naquele cenário; com
    o máximo entre cenários, nenhum candidato podia mover a métrica
    (todos empatavam) e o benefício máximo de severidade caía para
    9,4e-05 pu·barra. A MÉDIA entre cenários representa a redução média
    de profundidade de afundamento ao longo dos cenários simulados —
    cenário em que nada é mitigável (falta na fonte) contribui com um
    valor constante para todos os candidatos, em vez de apagar a
    sensibilidade dos demais.

    A média é tomada sobre o número de cenários COM medição de 'pu'
    para aquela barra — que, desde 2026-10-30, inclui os sentinels de
    colapso dos cenários não convergentes (janela completa), de modo
    que a divergência pese contra o candidato em vez de ser ignorada.
    """
    soma = {}
    contagem = {}
    for detalhe in resultado.get("detalhe_por_falta", []):
        nome_faltoso = detalhe["bus_falta"].split(".")[0].lower()
        for bus, valores in detalhe.get("pu", {}).items():
            if bus.split(".")[0].lower() == nome_faltoso:
                continue
            if not valores:
                continue
            profundidade = max(0.0, limite_superior - min(valores))
            soma[bus] = soma.get(bus, 0.0) + profundidade
            contagem[bus] = contagem.get(bus, 0) + 1
    return {bus: soma[bus] / contagem[bus] for bus in soma}


def executar_estudo_completo(caminho_master, barras_candidatas, barras_falta,
                               tipos_falta, catalogo_bess=None, max_unidades=1,
                               peso_custo=0.1, custo_maximo=None,
                               peso_qualidade=1.0, peso_economia=1.0,
                               r_falta_solida=0.05, r_falta_alta_impedancia=40.0,
                               limite_inferior=0.1, limite_superior=0.9,
                               tarifa: Optional[TarifaEnergia] = None,
                               horario_ponta_inicio: int = 18,
                               horario_ponta_fim: int = 21,
                               dias_equivalentes_mes: float = 22,
                               callback_progresso=None, callback_status=None):

    catalogo_bess = catalogo_bess or CATALOGO_BESS_PADRAO

    def _status(msg):
        if callback_status:
            callback_status(msg)

    # -------- 1) Caso base (sem BESS) -------- #
    _status("Executando caso base (sem BESS)...")
    resultado_baseline = estudo_afundamento.rodar_estudo(
        caminho_master, barras_falta, tipos_falta, bess_list=[],
        r_falta_solida=r_falta_solida,
        r_falta_alta_impedancia=r_falta_alta_impedancia,
        limite_inferior=limite_inferior, limite_superior=limite_superior)

    barras_em_sag_baseline = resultado_baseline["barras_em_sag_geral"]
    _status(f"Caso base: {len(barras_em_sag_baseline)} barra(s) em afundamento.")

    profundidade_baseline = _profundidades_por_barra(resultado_baseline, limite_superior)

    # -------- 1b) Escalas físicas de normalização (auditoria/MILP) -------- #
    # Os divisores dos termos de qualidade e economia NÃO devem ser o
    # máximo observado entre candidatos (ver MOTIVO no docstring de
    # otimizacao_milp.py: máximo outlier de 9,4e-05 pu·barra amplificou o
    # termo de qualidade ~10.000x contra uma economia de R$ 98 mil/ano).
    # São usados LIMITES SUPERIORES FÍSICOS do que cada critério pode
    # valer neste estudo, tornando os pesos comparáveis:
    #   qualidade: profundidade total removível = janela de sag x barras.
    #   economia:  arbitragem teórica máxima do caso base.
    escala_qualidade = float(
        max(limite_superior - limite_inferior, 0.0)
        * max(len(barras_em_sag_baseline), 1))

    escala_economia = None
    if tarifa is not None:
        _status("Calculando o potencial teórico de arbitragem (caso base)...")
        economia_base = economia_energia.analisar_economia_energia(
            caminho_master=caminho_master,
            bess_list=[],
            tarifa=tarifa,
            horario_ponta_inicio=horario_ponta_inicio,
            horario_ponta_fim=horario_ponta_fim,
            dias_equivalentes_mes=dias_equivalentes_mes,
            custo_bess_brl=0.0,
            callback_status=None)
        demanda_max_base = max(
            (float(p.get("kw_comprada", 0.0) or 0.0)
             for p in economia_base.get("perfil_base", [])),
            default=0.0)
        spread = float(tarifa.tarifa_ponta_kwh) - float(tarifa.tarifa_fora_ponta_kwh)
        duracao_ponta = max(horario_ponta_fim - horario_ponta_inicio, 0)
        if demanda_max_base > 0 and spread > 0 and duracao_ponta > 0:
            escala_economia = float(
                spread * demanda_max_base * duracao_ponta
                * dias_equivalentes_mes * 12)

    # -------- 2) Varredura exaustiva barra x catálogo -------- #
    candidatos = []
    total_passos = len(barras_candidatas) * len(catalogo_bess)
    passo_atual = 0

    for bus in barras_candidatas:
        for modelo in catalogo_bess:
            _status(f"Simulando BESS '{modelo['nome']}' na barra '{bus}'...")

            resultado = estudo_afundamento.rodar_estudo(
                caminho_master, barras_falta, tipos_falta,
                bess_list=[{"bus": bus, "kw": modelo["kw"], "kwh": modelo["kwh"]}],
                r_falta_solida=r_falta_solida,
                r_falta_alta_impedancia=r_falta_alta_impedancia,
                limite_inferior=limite_inferior, limite_superior=limite_superior)

            barras_resolvidas = barras_em_sag_baseline - resultado["barras_em_sag_geral"]
            beneficio = len(barras_resolvidas)

            # Benefício de SEVERIDADE (métrica contínua, pu·barra):
            # soma, sobre as barras monitoradas, da redução de
            # profundidade em relação ao caso base. Pode ser negativo
            # (se o despacho do BESS agravar algum cenário).
            profundidade_candidato = _profundidades_por_barra(resultado, limite_superior)
            beneficio_severidade = sum(
                profundidade_baseline.get(b, 0.0) - profundidade_candidato.get(b, 0.0)
                for b in set(profundidade_baseline) | set(profundidade_candidato))

            # Economia estimada DESTE candidato (arbitragem tarifária).
            # Necessária para o critério multi-critério do MILP: sem ela,
            # candidatos empatados em qualidade (inclusive com todos os
            # benefícios nulos, caso diagnosticado) não produzem seleção.
            # callback_status=None evita poluir o painel de progresso
            # com 48 pares de mensagens; o tick de progresso abaixo já
            # cobre um passo por candidato (após sag + economia).
            economia_candidato = None
            beneficio_econ_anual = 0.0
            if tarifa is not None:
                _status(f"Estimando economia do BESS '{modelo['nome']}' "
                        f"na barra '{bus}'...")
                resultado_econ = economia_energia.analisar_economia_energia(
                    caminho_master=caminho_master,
                    bess_list=[{"bus": bus, "kw": modelo["kw"], "kwh": modelo["kwh"]}],
                    tarifa=tarifa,
                    horario_ponta_inicio=horario_ponta_inicio,
                    horario_ponta_fim=horario_ponta_fim,
                    dias_equivalentes_mes=dias_equivalentes_mes,
                    custo_bess_brl=modelo["custo_brl"],
                    callback_status=None)
                economia_candidato = {
                    # float() explícito: os valores vêm do numpy (o motor
                    # OpenDSS devolve np.float64); sem o cast eles vazam
                    # para a UI e para o registro de auditoria.
                    "economia_diaria": float(resultado_econ["economia_diaria"]),
                    "economia_anual": float(resultado_econ["economia_anual"]),
                    "economia_demanda_mensal_estimada":
                        float(resultado_econ["economia_demanda_mensal_estimada"]),
                    "payback_anos": (
                        None if resultado_econ["payback_anos"] is None
                        else float(resultado_econ["payback_anos"])),
                    "alerta_superdimensionamento":
                        resultado_econ["alerta_superdimensionamento"],
                }
                beneficio_econ_anual = float(resultado_econ["economia_anual"])

            candidatos.append({
                "bus": bus,
                "modelo_bess": modelo,
                "beneficio": beneficio,
                "beneficio_severidade": beneficio_severidade,
                "beneficio_econ_anual": beneficio_econ_anual,
                "economia_candidato": economia_candidato,
                "barras_resolvidas": sorted(barras_resolvidas),
                "resultado_detalhado": resultado,
            })

            passo_atual += 1
            if callback_progresso:
                callback_progresso(passo_atual, total_passos)

    # -------- 3) Seleção ótima via PLIM (MILP) -------- #
    _status("Resolvendo o problema de otimização (PLIM)...")
    selecionados, status_milp = otimizacao_milp.otimizar_alocacao_bess(
        candidatos, max_unidades=max_unidades, peso_custo=peso_custo,
        custo_maximo=custo_maximo, peso_qualidade=peso_qualidade,
        peso_economia=peso_economia,
        escala_qualidade=escala_qualidade,
        escala_economia=escala_economia)

    # -------- 4) Verificação conjunta (benefício real) -------- #
    resultado_conjunto = None
    beneficio_conjunto_real = 0
    analise_reativo = None
    resultado_economia = None
    memorial_economia_texto = None

    if selecionados:
        bess_conjunto = [
            {"bus": c["bus"], "kw": c["modelo_bess"]["kw"], "kwh": c["modelo_bess"]["kwh"]}
            for c in selecionados
        ]

        _status("Executando verificação conjunta da configuração selecionada...")
        resultado_conjunto = estudo_afundamento.rodar_estudo(
            caminho_master, barras_falta, tipos_falta, bess_list=bess_conjunto,
            r_falta_solida=r_falta_solida,
            r_falta_alta_impedancia=r_falta_alta_impedancia,
            limite_inferior=limite_inferior, limite_superior=limite_superior)

        barras_resolvidas_real = (
            barras_em_sag_baseline - resultado_conjunto["barras_em_sag_geral"])
        beneficio_conjunto_real = len(barras_resolvidas_real)

        _status("Analisando necessidade de compensação reativa...")
        analise_reativo = reativo_analise.analisar_necessidade_reativo(
            caminho_master, bess_conjunto)

        # -------- 4b) Economia de energia (arbitragem ponta/fora ponta) -------- #
        if tarifa is not None:
            _status("Executando análise de economia de energia (ponta/fora ponta)...")
            custo_bess_total = sum(c["modelo_bess"]["custo_brl"] for c in selecionados)

            resultado_economia = economia_energia.analisar_economia_energia(
                caminho_master=caminho_master,
                bess_list=bess_conjunto,
                tarifa=tarifa,
                horario_ponta_inicio=horario_ponta_inicio,
                horario_ponta_fim=horario_ponta_fim,
                dias_equivalentes_mes=dias_equivalentes_mes,
                custo_bess_brl=custo_bess_total,
                callback_status=callback_status,
            )
            memorial_economia_texto = memorial_econ.gerar_memorial_economia(resultado_economia)

    # -------- 5) Memorial de cálculo do afundamento (transparência/auditoria) -------- #
    _status("Gerando memorial de cálculo...")
    if resultado_conjunto is not None:
        memorial_texto = memorial_calc.gerar_memorial_comparativo(
            resultado_baseline, resultado_conjunto,
            limite_inferior=limite_inferior, limite_superior=limite_superior,
            r_falta_solida=r_falta_solida,
            r_falta_alta_impedancia=r_falta_alta_impedancia)
    else:
        memorial_texto = memorial_calc.gerar_memorial_estudo(
            resultado_baseline,
            limite_inferior=limite_inferior, limite_superior=limite_superior,
            r_falta_solida=r_falta_solida,
            r_falta_alta_impedancia=r_falta_alta_impedancia,
            titulo="Caso Base (SEM BESS) — nenhuma alocação foi "
                   "selecionada pelo otimizador")

    return {
        "barras_em_sag_baseline": sorted(barras_em_sag_baseline),
        "resultado_baseline": resultado_baseline,
        "profundidade_baseline": profundidade_baseline,
        "candidatos": candidatos,
        "selecionados": selecionados,
        "status_milp": status_milp,
        "pesos_criterio": {
            "peso_qualidade": peso_qualidade,
            "peso_economia": peso_economia,
            "peso_custo": peso_custo,
        },
        "escala_qualidade": escala_qualidade,
        "escala_economia": escala_economia,
        "resultado_conjunto": resultado_conjunto,
        "beneficio_conjunto_real": beneficio_conjunto_real,
        "analise_reativo": analise_reativo,
        "memorial_calculo": memorial_texto,
        "resultado_economia": resultado_economia,
        "memorial_economia": memorial_economia_texto,
    }