__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Conversor: a partir de um sistema de referencia IEEE ja compilado e
resolvido (instancia dss_engine.DSS, ver validacao_ieee.py), monta um
modelo RedeEletrica equivalente e o salva como um novo Projeto,
permitindo abri-lo no Editor de Rede Eletrica para continuar o
trabalho - por exemplo, inserir um Sistema BESS e rodar os demais
modulos do software (Dimensionamento, Otimizacao de Alocacao de BESS).

LIMITACOES METODOLOGICAS (ler antes de interpretar o resultado):

(1) ENDERECAMENTO DE FASE: o modelo RedeEletrica representa cada
elemento apenas pela QUANTIDADE de fases (1, 2 ou 3), nao por QUAL
fase especificamente (A, B ou C). Os sistemas IEEE possuem diversos
elementos monofasicos/bifasicos conectados a fases especificas; essa
informacao nao e preservada na conversao. A topologia (barras e
conectividade) e fiel; o padrao exato de desequilibrio entre fases,
nao necessariamente, apos uma eventual reexportacao para .dss.

(2) REGULADORES DE TENSAO: o elemento Transformer do modelo nao possui
conceito de controle automatico de tap (RegControl). Cada banco de
reguladores monofasicos do sistema original (ex.: Reg1/Reg2/Reg3) e
convertido em um unico transformador trifasico equivalente, de
impedancia minima, preservando a conectividade da rede, mas sem a
funcao de regulacao automatica de tensao.

(3) IMPEDANCIA DE LINHA: o modelo armazena apenas R1/X1/R0/X0 (valores
agregados), nao a matriz de impedancia completa por fase utilizada
pelos sistemas IEEE. R1/X1 sao aproximados pela media dos elementos
proprios (diagonal) da matriz de cada linha; R0 e aproximado como
3xR1 - mesma aproximacao de engenharia ja utilizada em
dimensionamento_regras.py para linhas dimensionadas manualmente.

Este conversor NAO deve ser utilizado como substituto da Validacao do
Modelo Computacional (validacao_ieee.py); seu proposito e fornecer uma
base de rede topologicamente realista para experimentos de alocacao e
dimensionamento de sistemas de armazenamento de energia.
"""

import os

from .modelo_rede import RedeEletrica
from .projeto import criar_ou_abrir_projeto_por_nome, Projeto


# ============================================================
# Utilitarios de leitura do circuito DSS ja resolvido
# ============================================================

def _nome_base_barra(bus_completo: str) -> str:
    """Remove o sufixo de no (ex.: '634.1' -> '634')."""
    return bus_completo.split(".")[0]


def _kv_ll(objeto_dss, bus: str) -> float:
    """Tensao base de linha (LL), em kV, a partir da base LN do no."""
    objeto_dss.dssCircuit.SetActiveBus(bus)
    kv_ln = objeto_dss.dssCircuit.ActiveBus.kVBase
    return round(kv_ln * (3 ** 0.5), 4) if kv_ln else 0.0


def _bus_ativo(objeto_dss) -> str:
    """Retorna o nome base da primeira barra do elemento ativo."""
    try:
        nomes = objeto_dss.dssCktElement.BusNames
        return _nome_base_barra(nomes[0])
    except Exception:
        return ""


def _bus_ativo_todos(objeto_dss) -> list:
    try:
        return [_nome_base_barra(b) for b in objeto_dss.dssCktElement.BusNames]
    except Exception:
        return []


def _r1_x1_aproximados(objeto_dss) -> tuple:
    """Aproxima R1/X1 (ohm/milha) pela media dos elementos proprios
    (diagonal) da matriz de impedancia da linha ativa. Ver nota de
    transparencia metodologica no topo do arquivo (item 3)."""
    try:
        nfases = objeto_dss.dssCktElement.NumPhases
        rmatrix = list(objeto_dss.dssCircuit.Lines.RMatrix)
        xmatrix = list(objeto_dss.dssCircuit.Lines.XMatrix)

        diagonais_r = [rmatrix[i * nfases + i] for i in range(nfases)]
        diagonais_x = [xmatrix[i * nfases + i] for i in range(nfases)]

        r1 = sum(diagonais_r) / len(diagonais_r)
        x1 = sum(diagonais_x) / len(diagonais_x)
        return round(r1, 4), round(x1, 4)
    except Exception:
        # Fallback conservador caso a matriz nao esteja acessivel.
        return 0.3, 0.3


# ============================================================
# Conversao barra a barra / elemento a elemento
# ============================================================

def _converter_barras(objeto_dss, rede: RedeEletrica):
    for nome_barra in objeto_dss.dssCircuit.AllBusNames:
        nome_base = _nome_base_barra(nome_barra)
        if nome_base in rede.barras:
            continue
        kv_base = _kv_ll(objeto_dss, nome_barra)
        rede.adicionar_barra(nome_base, kv_base or 13.8)


def _converter_linhas(objeto_dss, rede: RedeEletrica):
    dssLines = objeto_dss.dssCircuit.Lines
    if dssLines.First == 0:
        return

    while True:
        nome = f"L_{dssLines.Name}"
        bus1 = _nome_base_barra(dssLines.Bus1)
        bus2 = _nome_base_barra(dssLines.Bus2)
        fases = objeto_dss.dssCktElement.NumPhases
        comprimento = dssLines.Length
        unidade = dssLines.Units or "km"

        r1, x1 = _r1_x1_aproximados(objeto_dss)
        r0, x0 = round(r1 * 3, 4), round(x1 * 3, 4)

        if bus1 in rede.barras and bus2 in rede.barras and bus1 != bus2:
            try:
                rede.adicionar_ramo(
                    "Line", nome, bus1, bus2,
                    {"phases": fases, "length": comprimento, "units": unidade,
                     "linecode": "", "r1": r1, "x1": x1, "r0": r0, "x0": x0})
            except ValueError:
                pass

        if dssLines.Next == 0:
            break


def _converter_transformadores(objeto_dss, rede: RedeEletrica):
    """Agrupa transformadores por par de barras (base), colapsando
    bancos de reguladores monofasicos em um unico transformador
    trifasico equivalente de impedancia minima. Ver nota de
    transparencia metodologica no topo do arquivo (item 2)."""

    dssTransf = objeto_dss.dssCircuit.Transformers
    grupos = {}

    if dssTransf.First > 0:
        while True:
            buses = _bus_ativo_todos(objeto_dss)
            if len(buses) >= 2 and buses[0] in rede.barras and buses[1] in rede.barras:
                chave = (buses[0], buses[1])
                try:
                    xhl = dssTransf.Xhl
                except Exception:
                    xhl = 2.0
                try:
                    kva = dssTransf.kVA if hasattr(dssTransf, "kVA") else 150.0
                except Exception:
                    kva = 150.0

                grupo = grupos.setdefault(chave, {"xhl_min": xhl, "kva_total": 0.0})
                grupo["xhl_min"] = min(grupo["xhl_min"], xhl)
                grupo["kva_total"] += kva or 150.0

            if dssTransf.Next == 0:
                break

    for i, ((bus1, bus2), dados) in enumerate(grupos.items()):
        nome = f"TR_{i}_{bus1}_{bus2}"
        kv1 = _kv_ll(objeto_dss, bus1) or 13.8
        kv2 = _kv_ll(objeto_dss, bus2) or 13.8
        try:
            rede.adicionar_ramo(
                "Transformer", nome, bus1, bus2,
                {"phases": 3, "kv1": kv1, "kv2": kv2,
                 "kva": round(dados["kva_total"], 1),
                 "conn1": "wye", "conn2": "wye",
                 "xhl": max(dados["xhl_min"], 0.5)})
        except ValueError:
            pass


def _converter_capacitores(objeto_dss, rede: RedeEletrica):
    dssCap = objeto_dss.dssCircuit.Capacitors
    if dssCap.First == 0:
        return

    while True:
        nome = f"CAP_{dssCap.Name}"
        bus1 = _bus_ativo(objeto_dss)
        fases = objeto_dss.dssCktElement.NumPhases
        try:
            kvar_total = sum(dssCap.kvar) if hasattr(dssCap.kvar, "__iter__") else dssCap.kvar
        except Exception:
            kvar_total = 300.0
        kv = _kv_ll(objeto_dss, bus1) if fases == 3 else _kv_ll(objeto_dss, bus1) / (3 ** 0.5)

        if bus1 in rede.barras:
            try:
                rede.adicionar_derivacao(
                    "Capacitor", nome, bus1,
                    {"phases": fases, "kv": round(kv, 3), "kvar": round(kvar_total, 1)})
            except ValueError:
                pass

        if dssCap.Next == 0:
            break


def _converter_cargas(objeto_dss, rede: RedeEletrica):
    dssLoads = objeto_dss.dssCircuit.Loads
    if dssLoads.First == 0:
        return

    while True:
        nome = f"CARGA_{dssLoads.Name}"
        bus1 = _bus_ativo(objeto_dss)
        fases = objeto_dss.dssCktElement.NumPhases

        try:
            kw = dssLoads.kW
            kvar = dssLoads.kvar
            kv = dssLoads.kV
        except Exception:
            kw, kvar, kv = 10.0, 3.0, 0.38

        try:
            conn = "delta" if dssLoads.IsDelta else "wye"
        except Exception:
            conn = "wye"

        if bus1 in rede.barras and (kw or kvar):
            try:
                rede.adicionar_derivacao(
                    "Load", nome, bus1,
                    {"phases": fases, "kv": kv, "kw": kw, "kvar": kvar,
                     "model": 1, "conn": conn})
            except ValueError:
                pass

        if dssLoads.Next == 0:
            break


def _converter_fonte(objeto_dss, rede: RedeEletrica):
    dssV = objeto_dss.dssCircuit.Vsources
    if dssV.First == 0:
        return

    bus1 = _bus_ativo(objeto_dss)
    try:
        basekv = dssV.BasekV
        pu = dssV.pu
    except Exception:
        basekv = _kv_ll(objeto_dss, bus1) or 13.8
        pu = 1.0

    if bus1 in rede.barras:
        try:
            rede.adicionar_derivacao(
                "Vsource", f"FONTE_{bus1}", bus1,
                {"phases": 3, "basekv": round(basekv, 3), "pu": round(pu, 4),
                 "mvasc3": 2000, "mvasc1": 2100})
        except ValueError:
            pass


# ============================================================
# Ponto de entrada
# ============================================================

def converter_sistema_para_rede(objeto_dss) -> RedeEletrica:
    """Monta uma RedeEletrica equivalente ao circuito ja compilado e
    resolvido em objeto_dss (instancia dss_engine.DSS)."""

    rede = RedeEletrica()
    _converter_barras(objeto_dss, rede)
    _converter_linhas(objeto_dss, rede)
    _converter_transformadores(objeto_dss, rede)
    _converter_capacitores(objeto_dss, rede)
    _converter_cargas(objeto_dss, rede)
    _converter_fonte(objeto_dss, rede)
    return rede


def exportar_sistema_como_projeto(objeto_dss, nome_projeto: str) -> Projeto:
    """Converte o sistema e salva como um novo Projeto (rede.json),
    pronto para ser aberto no Editor de Rede Eletrica. Retorna o
    Projeto criado."""

    rede = converter_sistema_para_rede(objeto_dss)

    projeto = criar_ou_abrir_projeto_por_nome(nome_projeto)
    caminho_rede_json = os.path.join(projeto.caminho_rede, "rede.json")
    rede.salvar_json(caminho_rede_json)

    return projeto