__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Regras/fórmulas de dimensionamento elétrico.

ATENÇÃO: os catálogos (condutores, potências padronizadas de
transformadores e geradores) contêm valores de REFERÊNCIA/APROXIMADOS,
usuais em literatura de distribuição de energia, adequados para fins
didáticos (TCC/protótipo). Para projetos reais, substitua pelos dados de
catálogo do fabricante e pelas normas técnicas da concessionária local
(ex.: NBR 5410, NBR 14039, normas de distribuição da concessionária).
"""

import math


# ============================================================
# Linha (condutor) — dimensionamento por ampacidade + queda de tensão
# ============================================================

CATALOGO_CONDUTORES = [
    # nome, material, secao_mm2, r_ohm_km, x_ohm_km, ampacidade_A
    {"nome": "4 AWG CAA", "material": "CAA", "secao_mm2": 21.1,
     "r_ohm_km": 1.5949, "x_ohm_km": 0.4171, "ampacidade_A": 140},
    {"nome": "2 AWG CAA", "material": "CAA", "secao_mm2": 33.6,
     "r_ohm_km": 1.0066, "x_ohm_km": 0.4013, "ampacidade_A": 184},
    {"nome": "1/0 AWG CAA", "material": "CAA", "secao_mm2": 53.5,
     "r_ohm_km": 0.6417, "x_ohm_km": 0.3956, "ampacidade_A": 242},
    {"nome": "4/0 AWG CAA", "material": "CAA", "secao_mm2": 107.2,
     "r_ohm_km": 0.3179, "x_ohm_km": 0.3778, "ampacidade_A": 340},
    {"nome": "336,4 MCM CAA", "material": "CAA", "secao_mm2": 170.5,
     "r_ohm_km": 0.2032, "x_ohm_km": 0.3661, "ampacidade_A": 470},
    {"nome": "16 mm² Cu", "material": "Cu", "secao_mm2": 16,
     "r_ohm_km": 1.150, "x_ohm_km": 0.350, "ampacidade_A": 95},
    {"nome": "25 mm² Cu", "material": "Cu", "secao_mm2": 25,
     "r_ohm_km": 0.727, "x_ohm_km": 0.340, "ampacidade_A": 125},
    {"nome": "35 mm² Cu", "material": "Cu", "secao_mm2": 35,
     "r_ohm_km": 0.524, "x_ohm_km": 0.330, "ampacidade_A": 154},
    {"nome": "50 mm² Cu", "material": "Cu", "secao_mm2": 50,
     "r_ohm_km": 0.387, "x_ohm_km": 0.320, "ampacidade_A": 188},
    {"nome": "70 mm² Cu", "material": "Cu", "secao_mm2": 70,
     "r_ohm_km": 0.268, "x_ohm_km": 0.310, "ampacidade_A": 240},
    {"nome": "95 mm² Cu", "material": "Cu", "secao_mm2": 95,
     "r_ohm_km": 0.193, "x_ohm_km": 0.300, "ampacidade_A": 289},
]


def calcular_corrente_projeto(potencia_kva, tensao_kv, fases=3):
    """Corrente de projeto pela potência aparente (Lei de Ohm trifásica/monofásica)."""
    tensao_v = tensao_kv * 1000
    potencia_va = potencia_kva * 1000
    if fases == 3:
        return potencia_va / (math.sqrt(3) * tensao_v)
    return potencia_va / tensao_v


def calcular_queda_tensao_pct(corrente_a, comprimento_km, r_ohm_km, x_ohm_km,
                                fator_potencia, tensao_kv, fases=3):
    """Queda de tensão percentual, método usual de projeto de redes de
    distribuição (aproximação linear R,X em série)."""
    sen_phi = math.sqrt(max(0.0, 1 - fator_potencia ** 2))
    r_total = r_ohm_km * comprimento_km
    x_total = x_ohm_km * comprimento_km

    if fases == 3:
        queda_v = math.sqrt(3) * corrente_a * (r_total * fator_potencia + x_total * sen_phi)
    else:
        queda_v = 2 * corrente_a * (r_total * fator_potencia + x_total * sen_phi)

    tensao_v = tensao_kv * 1000
    return (queda_v / tensao_v) * 100


def dimensionar_linha(potencia_kva, tensao_kv, fator_potencia, comprimento_km,
                        queda_max_pct=5.0, fases=3, material_preferido=None):
    """Seleciona o menor condutor do catálogo que atenda simultaneamente
    à ampacidade (corrente de projeto) e à queda de tensão máxima admissível."""

    fases = int(fases)
    corrente_projeto = calcular_corrente_projeto(potencia_kva, tensao_kv, fases)

    candidatos = [
        c for c in CATALOGO_CONDUTORES
        if material_preferido in (None, "Qualquer", c["material"])
    ]
    candidatos_ordenados = sorted(candidatos, key=lambda c: c["secao_mm2"])

    for cond in candidatos_ordenados:
        if cond["ampacidade_A"] < corrente_projeto:
            continue

        queda_pct = calcular_queda_tensao_pct(
            corrente_projeto, comprimento_km, cond["r_ohm_km"], cond["x_ohm_km"],
            fator_potencia, tensao_kv, fases)

        if queda_pct <= queda_max_pct:
            # Aproximação usual para sequência zero em linhas aéreas de
            # distribuição (r0/x0 ~ 3x r1/x1). Ajuste se tiver dados reais.
            r0 = cond["r_ohm_km"] * 3
            x0 = cond["x_ohm_km"] * 3

            return {
                "parametros": {
                    "phases": fases,
                    "length": comprimento_km,
                    "units": "km",
                    "linecode": "",
                    "r1": round(cond["r_ohm_km"], 4),
                    "x1": round(cond["x_ohm_km"], 4),
                    "r0": round(r0, 4),
                    "x0": round(x0, 4),
                },
                "memoria_calculo": {
                    "corrente_projeto_A": round(corrente_projeto, 2),
                    "condutor_escolhido": cond["nome"],
                    "material": cond["material"],
                    "secao_mm2": cond["secao_mm2"],
                    "ampacidade_A": cond["ampacidade_A"],
                    "queda_tensao_calculada_pct": round(queda_pct, 3),
                    "queda_tensao_admissivel_pct": queda_max_pct,
                },
            }

    raise ValueError(
        f"Nenhum condutor do catálogo atende simultaneamente à ampacidade "
        f"({corrente_projeto:.1f} A) e à queda de tensão máxima "
        f"({queda_max_pct}%) para {comprimento_km} km. Considere aumentar a "
        "tensão, reduzir o comprimento ou revisar os limites.")


# ============================================================
# Transformador — dimensionamento por potência de carga + margem
# ============================================================

POTENCIAS_PADRAO_TRAFO_KVA = [15, 30, 45, 75, 112.5, 150, 225, 300,
                               500, 750, 1000, 1500, 2000, 2500]


def _estimar_xhl_percentual(kva):
    """Estimativa típica de impedância percentual por faixa de potência
    (valores de referência usuais para transformadores de distribuição)."""
    if kva <= 112.5:
        return 3.5
    if kva <= 300:
        return 4.5
    if kva <= 750:
        return 5.5
    return 6.5


def dimensionar_transformador(potencia_carga_kw, fator_potencia, margem_seguranca_pct,
                                kv_primario, kv_secundario, fases=3):
    fases = int(fases)
    s_carga_kva = potencia_carga_kw / fator_potencia
    s_dimensionada_kva = s_carga_kva * (1 + margem_seguranca_pct / 100)

    kva_escolhido = next(
        (p for p in POTENCIAS_PADRAO_TRAFO_KVA if p >= s_dimensionada_kva),
        POTENCIAS_PADRAO_TRAFO_KVA[-1])

    xhl = _estimar_xhl_percentual(kva_escolhido)

    return {
        "parametros": {
            "phases": fases,
            "kv1": kv_primario,
            "kv2": kv_secundario,
            "kva": kva_escolhido,
            "conn1": "wye",
            "conn2": "wye",
            "xhl": xhl,
        },
        "memoria_calculo": {
            "potencia_carga_kw": potencia_carga_kw,
            "fator_potencia": fator_potencia,
            "s_carga_kva": round(s_carga_kva, 2),
            "margem_seguranca_pct": margem_seguranca_pct,
            "s_dimensionada_kva": round(s_dimensionada_kva, 2),
            "kva_padrao_escolhido": kva_escolhido,
            "xhl_estimado_pct": xhl,
        },
    }


# ============================================================
# Fotovoltaico (PVSystem) — dimensionamento por consumo + HSP
# ============================================================

def dimensionar_fotovoltaico(consumo_mensal_kwh, hsp_local, performance_ratio,
                               potencia_modulo_wp, razao_dc_ac, kv_conexao, fases=3):
    fases = int(fases)
    potencia_necessaria_kwp = consumo_mensal_kwh / (30 * hsp_local * performance_ratio)
    numero_modulos = math.ceil(potencia_necessaria_kwp * 1000 / potencia_modulo_wp)
    pmpp_kw_real = numero_modulos * potencia_modulo_wp / 1000
    kva_inversor = pmpp_kw_real / razao_dc_ac

    return {
        "parametros": {
            "phases": fases,
            "kv": kv_conexao,
            "kva": round(kva_inversor, 2),
            "pmpp": round(pmpp_kw_real, 2),
            "irradiance": 1.0,
            "cutin": 2,
            "cutout": 2,
        },
        "memoria_calculo": {
            "consumo_mensal_kwh": consumo_mensal_kwh,
            "hsp_local_h_dia": hsp_local,
            "performance_ratio": performance_ratio,
            "potencia_necessaria_kwp": round(potencia_necessaria_kwp, 2),
            "potencia_modulo_wp": potencia_modulo_wp,
            "numero_modulos": numero_modulos,
            "pmpp_real_kw": round(pmpp_kw_real, 2),
            "razao_dc_ac": razao_dc_ac,
            "kva_inversor": round(kva_inversor, 2),
        },
    }


# ============================================================
# Storage (BESS) — dimensionamento por autonomia + DoD + eficiência
# ============================================================

def dimensionar_storage(potencia_media_kw, horas_autonomia, profundidade_descarga_pct,
                          eficiencia_pct, kv_conexao, fases=3):
    fases = int(fases)
    dod = profundidade_descarga_pct / 100
    eficiencia = eficiencia_pct / 100

    kwh_rated = (potencia_media_kw * horas_autonomia) / (dod * eficiencia)
    kw_rated = potencia_media_kw

    return {
        "parametros": {
            "phases": fases,
            "kv": kv_conexao,
            "kwrated": round(kw_rated, 2),
            "kwhrated": round(kwh_rated, 2),
            "pctstored": 50,
            "dispmode": "default",
            "state": "idling",
        },
        "memoria_calculo": {
            "potencia_media_kw": potencia_media_kw,
            "horas_autonomia": horas_autonomia,
            "profundidade_descarga_pct": profundidade_descarga_pct,
            "eficiencia_pct": eficiencia_pct,
            "kwh_rated_calculado": round(kwh_rated, 2),
            "kw_rated_calculado": round(kw_rated, 2),
        },
    }


# ============================================================
# Capacitor — dimensionamento por correção de fator de potência
# (compensação de reativo INDUTIVO em excesso, situação mais comum
# em redes de distribuição convencionais).
# ============================================================

def dimensionar_capacitor(potencia_ativa_kw, fp_atual, fp_desejado, kv_conexao, fases=3):
    fases = int(fases)
    ang_atual = math.acos(fp_atual)
    ang_desejado = math.acos(fp_desejado)
    qc_kvar = potencia_ativa_kw * (math.tan(ang_atual) - math.tan(ang_desejado))

    if qc_kvar <= 0:
        raise ValueError(
            "O fator de potência desejado deve ser maior que o atual para "
            "que seja necessária compensação capacitiva.")

    return {
        "parametros": {
            "phases": fases,
            "kv": kv_conexao,
            "kvar": round(qc_kvar, 2),
        },
        "memoria_calculo": {
            "potencia_ativa_kw": potencia_ativa_kw,
            "fp_atual": fp_atual,
            "fp_desejado": fp_desejado,
            "kvar_calculado": round(qc_kvar, 2),
        },
    }


# ============================================================
# Reactor (banco de reatores shunt) — dimensionamento para
# absorção de reativo CAPACITIVO em excesso.
#
# Situação típica: redes com grande penetração de geração
# distribuída (PVSystem/Storage com inversores sobre-excitados,
# ou cabos subterrâneos de grande extensão) injetando reativo
# capacitivo além do que a rede consegue absorver, elevando o
# fator de potência acima do limite superior de referência do
# PRODIST Módulo 8 (0,92 capacitivo).
#
# Sintaxe oficial confirmada na documentação EPRI (Reactor.html):
#     New Reactor.nome bus1=<barra> phases=<n> kv=<tensão_LL>
#         kvar=<total, todas as fases> conn=wye
#
# Observações importantes da própria documentação do OpenDSS:
#   - bus2 NÃO precisa ser especificado: por padrão, o Reactor
#     assume conexão Wye aterrada no 2º terminal (elemento SHUNT),
#     que é exatamente o comportamento desejado aqui (análogo ao
#     Capacitor).
#   - 'kvar' é o TOTAL somado de todas as fases, dividido
#     igualmente entre elas, e determina APENAS a reatância X.
#     A resistência (R) é especificada separadamente (parâmetro
#     'R', em ohms) - se não for informada, o Reactor assume R=0,
#     o que é aceitável para um banco de reatores idealizado em
#     estudos de regime permanente.
# ============================================================

def dimensionar_reator_indutivo(potencia_reativa_excedente_kvar, kv_conexao, fases=3):
    """Dimensiona um banco de reatores shunt para absorver o excedente
    de reativo capacitivo informado (kvar), aproximando para o próximo
    múltiplo de 50 kvar (padrão comercial usual de bancos de reatores).
    """
    fases = int(fases)

    if potencia_reativa_excedente_kvar <= 0:
        raise ValueError(
            "A potência reativa excedente a ser absorvida deve ser maior "
            "que zero para que seja necessária a instalação de um reator.")

    passo_comercial_kvar = 50
    kvar_comercial = math.ceil(
        potencia_reativa_excedente_kvar / passo_comercial_kvar) * passo_comercial_kvar

    return {
        "parametros": {
            "phases": fases,
            "kv": kv_conexao,
            "kvar": kvar_comercial,
            "conn": "wye",
        },
        "memoria_calculo": {
            "potencia_reativa_excedente_calculada_kvar": round(
                potencia_reativa_excedente_kvar, 2),
            "kvar_comercial_escolhido": kvar_comercial,
            "passo_comercial_kvar": passo_comercial_kvar,
            "observacao": (
                "Banco de reatores shunt (conexão Wye aterrada), dimensionado "
                "para absorver reativo capacitivo excedente da rede."
            ),
        },
    }


# ============================================================
# Gerador — dimensionamento por potência de carga + fator de demanda
# ============================================================

POTENCIAS_PADRAO_GERADOR_KVA = [15, 30, 50, 75, 100, 150, 180, 220, 275,
                                 330, 400, 500, 630, 800, 1000, 1250]


def dimensionar_gerador(potencia_carga_kw, fator_potencia, fator_demanda_pct,
                          margem_seguranca_pct, kv_conexao, fases=3):
    fases = int(fases)
    s_carga_kva = (potencia_carga_kw * (fator_demanda_pct / 100)) / fator_potencia
    s_dimensionada_kva = s_carga_kva * (1 + margem_seguranca_pct / 100)

    kva_escolhido = next(
        (p for p in POTENCIAS_PADRAO_GERADOR_KVA if p >= s_dimensionada_kva),
        POTENCIAS_PADRAO_GERADOR_KVA[-1])

    kw_nominal = round(kva_escolhido * fator_potencia, 2)

    return {
        "parametros": {
            "phases": fases,
            "kv": kv_conexao,
            "kw": kw_nominal,
            "kvar": 0,
            "model": 1,
        },
        "memoria_calculo": {
            "potencia_carga_kw": potencia_carga_kw,
            "fator_demanda_pct": fator_demanda_pct,
            "fator_potencia": fator_potencia,
            "s_carga_kva": round(s_carga_kva, 2),
            "margem_seguranca_pct": margem_seguranca_pct,
            "s_dimensionada_kva": round(s_dimensionada_kva, 2),
            "kva_padrao_escolhido": kva_escolhido,
            "kw_nominal_gerador": kw_nominal,
        },
    }