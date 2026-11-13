#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera os dados da figura de dois paineis (SoC horario + tensao minima por
barra sob falta trifasica na barra do BESS) para o artigo.

Fonte unica dos numeros: o dump do estudo de otimizacao
(tcc_opendss/projetos/teste/dump_estudo_otimizacao.json) para o SoC horario e
para a marcacao de ponta, e o motor OpenDSS para as tensoes pos-falta.

Nada neste script e "a mao": o SoC do ponto de otimizacao (h18 de quinta) e
lido do dump, nao digitado; as tensoes vem de rodar_estudo / do motor
reutilizavel do proprio estudo (tcc_opendss/bibliotecas/estudo_afundamento.py),
com as mesmas convencoes (Vminpu=0.05, falta solida r=0.05 ohm, barra faltosa
excluida da classificacao).

Saidas:
    doc/fig_soc_falta_dados.json  -- dados estruturados + coordenadas pgfplots
    stdout                        -- tabela-resumo

Dependencias: stdlib + dss-python (0.15.7). Executar da RAIZ do repositorio:
    python doc/gerar_figura_soc_falta.py
"""

import json
import math
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# sys.path aponta para as bibliotecas do projeto antes de importa-las.
_BIBLIOTECAS = os.path.join(RAIZ, "tcc_opendss", "bibliotecas")
if _BIBLIOTECAS not in sys.path:
    sys.path.insert(0, _BIBLIOTECAS)

from estudo_afundamento import (  # noqa: E402
    MotorReutilizavel,
    VMINPU_STORAGE_PADRAO,
    _aplicar_falta,
    _capturar_pu_todas_barras,
    _nome_base_barra,
    rodar_estudo,
)

DUMP = os.path.join(RAIZ, "tcc_opendss", "projetos", "teste",
                    "dump_estudo_otimizacao.json")
# Caminho ABSOLUTO obrigatorio: o OpenDSS resolve os paths relativos do .dss
# master a partir do diretorio do processo, nao do arquivo, e falha com erro
# #243 quando recebe caminho relativo.
MASTER = os.path.abspath(os.path.join(RAIZ, "tcc_opendss", "projetos",
                                      "teste", "rede", "Master.dss"))
SAIDA = os.path.join(RAIZ, "doc", "fig_soc_falta_dados.json")

BUS_FALTA = "B5"
TIPO_FALTA = "trifasica"
R_FALTA = 0.05
DIA = "Quinta"
BARRAS_MONITORADAS = ["b1", "b2", "b3", "b4", "b5", "b6"]
LIMITE_INFERIOR = 0.1
LIMITE_SUPERIOR = 0.9

BESS_SELECIONADO = {"bus": BUS_FALTA, "kw": 50, "kwh": 100}

# Ordem do painel (b) da Fig. de curvas da semana. A chave JSON nao leva
# acento (seguranca de identificador); o rotulo do grafico leva, e fica no
# .tex.
DIAS_SEMANA = [
    ("Segunda", "Segunda"),
    ("Terça", "Terca"),
    ("Quarta", "Quarta"),
    ("Quinta", "Quinta"),
    ("Sexta", "Sexta"),
    ("Sábado", "Sabado"),
    ("Domingo", "Domingo"),
]


def carregar_dump(caminho):
    with open(caminho, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _perfil_do_dia(dump, nome_dia):
    for dia in dump["semanal_vencedor"]["perfis_por_dia"]:
        if dia["dia"].strip().lower().startswith(nome_dia.lower()[:4]):
            return dia
    raise KeyError(f"dia {nome_dia!r} ausente em semanal_vencedor.perfis_por_dia")


def _primeira_chave(dicionario):
    # O nome do BESS economico e indexado (BESS_ECON_0); o 1o item e o que
    # alimenta o SoC do perfil.
    for chave in dicionario:
        return chave
    return None


def extrair_soc_diario(dump, nome_dia=DIA):
    """Serie horaria de SoC (%) do 1o BESS no dia representativo, mais as
    flags de ponta e o SoC do passo em que a falta e simulada (h18)."""
    dia = _perfil_do_dia(dump, nome_dia)
    horas, soc_pct, ponta = [], [], []
    for registro in dia["perfil_bess"]:
        chave = _primeira_chave(registro["soc_depois"])
        if chave is None:
            raise ValueError(f"SoC ausente na hora {registro['hora']} de {nome_dia}")
        horas.append(int(registro["hora"]))
        soc_pct.append(round(float(registro["soc_depois"][chave]) * 100.0, 4))
        ponta.append(bool(registro["ponta"]))
    if len(horas) != 24:
        raise ValueError(f"esperadas 24 horas, obtidas {len(horas)}")
    return horas, soc_pct, ponta


def soc_na_hora(horas, soc_pct, hora):
    if hora not in horas:
        raise ValueError(f"hora {hora} ausente na serie de SoC")
    return soc_pct[horas.index(hora)]


def _pu_minimo_por_barra(pu_por_barra):
    """Minimo entre as fases de cada barra monitorada.

    A captura devolve uma lista de magnitudes por barra; a tensao minima de
    fase e a que caracteriza o afundamento (criterio do estudo: basta uma fase
    dentro da janela).
    """
    minimos = {}
    for barra in BARRAS_MONITORADAS:
        valores = pu_por_barra.get(barra) or []
        if not valores:
            raise ValueError(f"barra {barra} sem medicao de tensao")
        minimos[barra] = min(valores)
    return minimos


def classificar_sag(minimos, bus_faltoso=BUS_FALTA):
    """Barras na janela [0.1, 0.9) pu, com a barra faltosa EXCLUIDA.

    Mesma convencao de _classificar_sag do estudo: no no em falta a tensao e o
    proprio curto, nao o efeito que se quer medir no restante da rede.
    """
    excluida = _nome_base_barra(bus_faltoso)
    return sorted(
        barra for barra, valor in minimos.items()
        if barra != excluida and LIMITE_INFERIOR <= valor < LIMITE_SUPERIOR
    )


def _nomes_analisados(pu_por_barra):
    return {
        barra: _pu_minimo_por_barra(pu_por_barra)[barra]
        for barra in BARRAS_MONITORADAS
    }


def simular_com_motor(percentual_stored):
    """Roda a falta trifasica em BUS_FALTA com o BESS selecionado, controlando
    o %stored. Serve tanto para o cenario da figura quanto para a validacao de
    invariancia (o resultado deve ser identico ao das rodadas via
    rodar_estudo, que fixa %stored=50).
    """
    motor = MotorReutilizavel()
    try:
        motor.recompilar(MASTER)
        # kVBase vem em fase-neutro; a definicao do Storage pede tensao de
        # linha (mesma conversao de _obter_kv_linha_barra).
        motor.dssCircuit.SetActiveBus(BUS_FALTA)
        kv_linha = motor.dssCircuit.ActiveBus.kVBase * math.sqrt(3)
        motor.dssText.Command = (
            f"New Storage.BESS_FIG bus1={BUS_FALTA} phases=3 "
            f"kv={kv_linha:.4f} kwrated={BESS_SELECIONADO['kw']} "
            f"kwhrated={BESS_SELECIONADO['kwh']} "
            f"kva={BESS_SELECIONADO['kw']} "
            f"%stored={percentual_stored:.4f} state=discharging model=1 "
            f"Vminpu={VMINPU_STORAGE_PADRAO} dispmode=default"
        )
        motor.dssSolution.Solve()
        _aplicar_falta(motor, BUS_FALTA, TIPO_FALTA, R_FALTA)
        motor.dssSolution.Solve()
        if not motor.dssSolution.Converged:
            raise RuntimeError(
                f"falta trifasica em {BUS_FALTA} nao convergiu "
                f"(%stored={percentual_stored:.4f})"
            )
        return _capturar_pu_todas_barras(motor.dssCircuit)
    finally:
        motor.finalizar()


def simular_rodar_estudo(bess_list):
    """Wrapper de rodar_estudo para um unico cenario (falta trifasica em
    BUS_FALTA). bess_list=None reproduz o caso base."""
    resultado = rodar_estudo(
        MASTER, [BUS_FALTA], [TIPO_FALTA], bess_list=bess_list,
        r_falta_solida=R_FALTA,
        limite_inferior=LIMITE_INFERIOR, limite_superior=LIMITE_SUPERIOR,
    )
    detalhe = resultado["detalhe_por_falta"][0]
    if not detalhe["convergiu"]:
        raise RuntimeError(
            f"cenario de falta nao convergiu (bess_list={bess_list})"
        )
    return detalhe["pu"], detalhe["barras_em_sag"]


def serie_pgfplots(pontos):
    """String de coordenadas pgfplots pronta: '(x,y) (x,y) ...'.

    Formata com virgula decimal? Nao: pgfplots le ponto como separador
    decimal por padrao nas coordenadas. Mantemos ponto e deixamos a
    formatacao de rotulos para o eixo (yticklabel style)."""
    return " ".join(
        "({},{:.4f})".format(_fmt_x(x), y) for x, y in pontos
    )


def _fmt_x(x):
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def serie_pgfplots_carga(pontos):
    """Coordenadas pgfplots da carga com 1 casa decimal:
    '(0,18.6) (1,18.0) ...'."""
    return " ".join(
        "({},{:.1f})".format(_fmt_x(x), y) for x, y in pontos
    )


def serie_carga_b4_por_dia(dump):
    """Carga horaria da barra B4 (kWh por intervalo de 1 h) por dia.

    O dump traz carga_kw como a carga AGREGADA do alimentador; a barra B4
    responde por metade dela (B4 e B5 compartilham a mesma curva padrao de
    carga), de modo que a serie da barra e carga_kw/2 -- arredondada a 1 casa
    decimal, a mesma resolucao da coluna 'Carga' da tabela do dia
    representativo.
    """
    perfis = {
        registro["dia"].strip(): registro
        for registro in dump["semanal_vencedor"]["perfis_por_dia"]
    }
    series = {}
    for rotulo, chave in DIAS_SEMANA:
        if rotulo not in perfis:
            raise KeyError(
                f"dia {rotulo!r} ausente em semanal_vencedor.perfis_por_dia")
        registros = perfis[rotulo]["perfil_bess"]
        if len(registros) != 24:
            raise ValueError(
                f"{rotulo}: esperadas 24 horas, obtidas {len(registros)}")
        carga = [round(float(registro["carga_kw"]) / 2.0, 1)
                 for registro in registros]
        series[chave] = {
            "rotulo": rotulo,
            "carga_kw_dump": [round(float(r["carga_kw"]), 4)
                              for r in registros],
            "carga_b4_kwh": carga,
            "coordenadas": serie_pgfplots_carga(list(zip(range(24), carga))),
        }
    return series


def serie_fv_por_dia(dump):
    """Geracao fotovoltaica horaria (kWh por intervalo de 1 h) por dia.

    Serie lida diretamente de fv_kw no dump -- sem escala a partir do dia
    representativo: cada dia tem a sua propria curva.
    """
    perfis = {
        registro["dia"].strip(): registro
        for registro in dump["semanal_vencedor"]["perfis_por_dia"]
    }
    series = {}
    for rotulo, chave in DIAS_SEMANA:
        if rotulo not in perfis:
            raise KeyError(
                f"dia {rotulo!r} ausente em semanal_vencedor.perfis_por_dia")
        registros = perfis[rotulo]["perfil_bess"]
        if len(registros) != 24:
            raise ValueError(
                f"{rotulo}: esperadas 24 horas, obtidas {len(registros)}")
        fv = [round(float(registro["fv_kw"]), 1) for registro in registros]
        series[chave] = {
            "rotulo": rotulo,
            "fv_kwh": fv,
            "coordenadas": serie_pgfplots_carga(list(zip(range(24), fv))),
        }
    return series



def main():
    if not os.path.isfile(MASTER):
        raise SystemExit(f"Master.dss nao encontrado: {MASTER}")

    dump = carregar_dump(DUMP)
    horas, soc_pct, ponta = extrair_soc_diario(dump)
    hora_falta = 18
    soc_falta_pct = soc_na_hora(horas, soc_pct, hora_falta)

    # (i) caso base -- mesmo caminho do estudo.
    pu_base, sag_base = simular_rodar_estudo(None)
    # (ii) selecionado via rodar_estudo (%stored=50) -- tambem e a rodada de
    # validacao de invariancia em relacao ao %stored do ponto de otimizacao.
    pu_sel_estudo, sag_sel_estudo = simular_rodar_estudo([BESS_SELECIONADO])
    # (ii') selecionado com %stored do ponto de otimizacao -- o cenario da
    # figura.
    pu_sel_fig = simular_com_motor(soc_falta_pct)

    min_base = _pu_minimo_por_barra(pu_base)
    min_sel_estudo = _pu_minimo_por_barra(pu_sel_estudo)
    min_sel_fig = _pu_minimo_por_barra(pu_sel_fig)

    # Validacao: a tensao nao pode depender do %stored inicial. Se depender,
    # o modelo do Storage estaria acoplando tensao a energia armazenada e a
    # premissa da figura (falta na hora do despacho) seria falsa.
    TOL_STORED = 1e-6
    desvios = {
        barra: abs(min_sel_fig[barra] - min_sel_estudo[barra])
        for barra in BARRAS_MONITORADAS
    }
    invariancia_ok = all(v <= TOL_STORED for v in desvios.values())
    if not invariancia_ok:
        raise SystemExit(
            "FALHA: tensao depende do %stored -- " +
            ", ".join(f"{b}: {d:.2e}" for b, d in desvios.items())
        )

    # A barra faltosa e excluida da classificacao (convencao do estudo).
    classificacao = {
        "base": classificar_sag(min_base),
        "selecionado_50kw": classificar_sag(min_sel_fig),
    }

    # Coordenadas pgfplots: painel (a) SoC, painel (b) tensao.
    coords_soc = serie_pgfplots(list(zip(horas, soc_pct)))
    px = {barra: i + 1 for i, barra in enumerate(BARRAS_MONITORADAS)}
    coords_base = serie_pgfplots([(px[b], min_base[b]) for b in BARRAS_MONITORADAS])
    coords_sel = serie_pgfplots([(px[b], min_sel_fig[b]) for b in BARRAS_MONITORADAS])

    # Carga da barra B4 por dia -- painel (b) da Fig. de curvas da semana.
    carga_b4 = serie_carga_b4_por_dia(dump)

    # Geracao FV por dia -- painel (a) da Fig. de curvas da semana.
    fv_por_dia = serie_fv_por_dia(dump)

    dados = {
        "meta": {
            "gerado_por": "doc/gerar_figura_soc_falta.py",
            "fonte_soc": "tcc_opendss/projetos/teste/dump_estudo_otimizacao.json",
            "fonte_tensoes": "OpenDSS (estudo_afundamento)",
            "master": MASTER,
            "bus_falta": BUS_FALTA,
            "tipo_falta": TIPO_FALTA,
            "r_falta_ohm": R_FALTA,
            "vminpu_storage": VMINPU_STORAGE_PADRAO,
            "dia_representativo": DIA,
            "hora_falta": hora_falta,
            "limite_inferior_pu": LIMITE_INFERIOR,
            "limite_superior_pu": LIMITE_SUPERIOR,
            "convencao": "barra faltosa excluida da classificacao de sag",
        },
        "soc": {
            "horas": horas,
            "soc_pct": soc_pct,
            "ponta": ponta,
            "hora_falta": hora_falta,
            "soc_falta_pct": soc_falta_pct,
            "janela_ponta": [
                horas[ponta.index(True)],
                horas[len(ponta) - 1 - ponta[::-1].index(True)],
            ],
            "piso_operacao_pct": 20.0,
        },
        "tensao": {
            "barras": BARRAS_MONITORADAS,
            "pu_minimo": {
                "base": min_base,
                "selecionado_50kw": min_sel_fig,
            },
            "classificacao_sag": classificacao,
            "excluida_da_classificacao": _nome_base_barra(BUS_FALTA),
        },
        "validacao": {
            "teste": "invariancia de %stored (%stored do ponto de otimizacao "
                     "vs %stored=50 de rodar_estudo)",
            "stored_ponto_otimizacao_pct": soc_falta_pct,
            "stored_rodar_estudo_pct": 50,
            "tolerancia_pu": TOL_STORED,
            "desvio_absoluto_por_barra": desvios,
            "aprovado": invariancia_ok,
        },
        "pgfplots": {
            "soc": coords_soc,
            "tensao_base": coords_base,
            "tensao_selecionado": coords_sel,
            "eixo_x_tensao": ["{}={}".format(b, px[b]) for b in BARRAS_MONITORADAS],
        },
        "carga_b4_por_dia": carga_b4,
        "fv_por_dia": fv_por_dia,
    }

    with open(SAIDA, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(dados, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    # ---- tabela-resumo no stdout ----
    cabecalho = "barra | base   | 50kW   | classificacao (base/50kW)"
    print(cabecalho)
    print("-" * len(cabecalho))
    for barra in BARRAS_MONITORADAS:
        def marca(chave):
            if barra == _nome_base_barra(BUS_FALTA):
                return "excl"
            return "sag" if barra in classificacao[chave] else "ok"
        print("{:5s} | {:.4f} | {:.4f} | {:4s} / {:4s}".format(
            barra, min_base[barra], min_sel_fig[barra],
            marca("base"), marca("selecionado_50kw"),
        ))
    print()
    print("SoC em {} h{:02d} = {:.1f}% | janela de ponta = h{:02d}-h{:02d}".format(
        DIA, hora_falta, soc_falta_pct,
        dados["soc"]["janela_ponta"][0], dados["soc"]["janela_ponta"][1]))
    print("Invariancia de %stored: {}".format(
        "OK (desvio max {:.2e} pu)".format(max(desvios.values()))))
    print("carga_b4_por_dia: {} dias, {} valores cada".format(
        len(carga_b4), len(carga_b4[DIAS_SEMANA[0][1]]["carga_b4_kwh"])))
    print("fv_por_dia: {} dias, {} valores cada".format(
        len(fv_por_dia), len(fv_por_dia[DIAS_SEMANA[0][1]]["fv_kwh"])))
    print("JSON escrito em {}".format(SAIDA))
    return 0


if __name__ == "__main__":
    sys.exit(main())
