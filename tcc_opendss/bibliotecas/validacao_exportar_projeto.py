__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Conversor: a partir de um sistema de referência IEEE já compilado e
resolvido (instância dss_engine.DSS, ver validacao_ieee.py), monta um
modelo RedeEletrica equivalente e o salva como um novo Projeto. O projeto
abre então no Editor de Rede Elétrica, onde o trabalho continua — inserir
um Sistema BESS, rodar o Dimensionamento, rodar a Otimização de Alocação
de BESS.

LIMITAÇÕES METODOLÓGICAS (ler antes de interpretar o resultado):

(1) ENDEREÇAMENTO DE FASE: o modelo RedeEletrica representa cada elemento
pela QUANTIDADE de fases (1, 2 ou 3), não por QUAL fase (A, B ou C). Os
sistemas IEEE têm vários elementos monofásicos e bifásicos ligados a fases
específicas, e essa informação não é preservada na conversão. A topologia
— barras e conectividade — é fiel. O padrão exato de desequilíbrio entre
fases já não é garantido numa reexportação para .dss.

(2) REGULADORES DE TENSÃO: o elemento Transformer do modelo não tem
controle automático de tap (RegControl). Cada banco de reguladores
monofásicos do sistema original (Reg1/Reg2/Reg3) é convertido num único
transformador trifásico equivalente, de impedância mínima. A conectividade
da rede se preserva; a função de regulação automática de tensão, não.

(3) IMPEDÂNCIA DE LINHA: o modelo guarda apenas R1/X1/R0/X0, valores
agregados, e não a matriz de impedância completa por fase usada pelos
sistemas IEEE. R1/X1 saem da extração de sequência positiva da matriz de
cada linha (elemento próprio médio menos elemento mútuo médio),
normalizados para ohm/km conforme a unidade declarada da linha —
normalização que também elimina a ambiguidade de unidade na reexportação;
R0 é aproximado como 3xR1 — a mesma aproximação de engenharia já usada em
dimensionamento_regras.py para linhas dimensionadas manualmente.

Este conversor substitui a Validação do Modelo Computacional
(validacao_ieee.py)? Não. O papel dele é outro: fornecer base de rede
topologicamente realista para experimentos de alocação e dimensionamento
de armazenamento.
"""

import os

from .modelo_rede import RedeEletrica
from .projeto import criar_ou_abrir_projeto_por_nome, Projeto
from .exportador_dss import FATOR_PARA_KM


# ============================================================
# Utilitarios de leitura do circuito DSS ja resolvido
# ============================================================

def _nome_base_barra(bus_completo: str) -> str:
    """Retira o sufixo de nó ('634.1' vira '634')."""
    return bus_completo.split(".")[0]


def _kv_ll(objeto_dss, bus: str) -> float:
    """Tensão base de linha (LL), em kV, derivada da base fase-neutro do nó.

    O retorno 0.0 quando a base é nula deixa o chamador decidir o valor
    padrão; converter aqui esconderia barra sem tensão definida.
    """
    objeto_dss.dssCircuit.SetActiveBus(bus)
    kv_ln = objeto_dss.dssCircuit.ActiveBus.kVBase
    return round(kv_ln * (3 ** 0.5), 4) if kv_ln else 0.0


def _bus_ativo(objeto_dss) -> str:
    """Nome base da primeira barra do elemento ativo.

    Devolve string vazia se o elemento não tiver barras legíveis: o
    chamador então simplesmente não cria o ramo, em vez de quebrar a
    conversão inteira por causa de um elemento atípico.
    """
    try:
        nomes = objeto_dss.dssCktElement.BusNames
        return _nome_base_barra(nomes[0])
    except Exception:
        return ""


def _bus_ativo_todos(objeto_dss) -> list:
    # Variante que devolve todas as barras do elemento ativo — usada pelos
    # transformadores, que precisam dos dois terminais.
    try:
        return [_nome_base_barra(b) for b in objeto_dss.dssCktElement.BusNames]
    except Exception:
        return []


def _r1_x1_aproximados(dssLines, nfases: int) -> tuple:
    """Extrai R1/X1 da matriz de impedância em fase da linha ativa,
    pelo par elemento próprio médio menos elemento mútuo médio (d − m).
    Quando a matriz deriva de componentes simétricas, d − m devolve
    exatamente a sequência positiva; a média da diagonal sozinha, não.

    A matriz vem achatada em lista, com o elemento i,j em i*nfases + j.
    A leitura PRECISA ser feita pelo mesmo objeto Lines que itera o
    circuito: reobter `ActiveCircuit.Lines` dentro da função devolve uma
    instância sem índice posicionado, e a matriz que vem é de outro
    elemento. Os atributos do binding são Rmatrix/Xmatrix (com 'm'
    minúsculo) — a grafia RMatrix não existe em dss-python 0.15.7, e a
    exceção resultante derrubava toda leitura para o fallback, com todas
    as linhas herdando o mesmo valor genérico. Ver a nota de
    transparência metodológica no topo do arquivo, item 3.
    """
    try:
        rmatrix = list(dssLines.Rmatrix)
        xmatrix = list(dssLines.Xmatrix)

        def sequencia_positiva(matriz) -> float:
            diagonal = [matriz[i * nfases + i] for i in range(nfases)]
            mutuos = [matriz[i * nfases + j]
                      for i in range(nfases) for j in range(nfases) if i != j]
            media_mutuos = sum(mutuos) / len(mutuos) if mutuos else 0.0
            return sum(diagonal) / len(diagonal) - media_mutuos

        # Sem arredondamento aqui: o valor sai por unidade da linha (por
        # pé, por exemplo, casa de 1e-5), e um round em 4 casas o zeraria
        # antes da conversão. Quem arredonda é o chamador, já em ohm/km.
        return sequencia_positiva(rmatrix), sequencia_positiva(xmatrix)
    except Exception:
        # Fallback conservador (em ohm/km) para quando a matriz não está
        # acessível: valores típicos de linha de distribuição média. A
        # aproximação fica registrada no item 3 da nota metodológica.
        return 0.3, 0.3


def _unidade_da_linha(objeto_dss, nome: str) -> str:
    """Unidade de comprimento declarada da linha, lida pelo Texto do motor.

    A propriedade ILines.Units do binding devolve 0 em qualquer situação
    nesta versão do dss-python, e a consulta '? line.<nome>.units' é a
    única leitura confiável. Linha sem unidade declarada responde 'none',
    que o motor trata como quilometro.
    """
    try:
        objeto_dss.dssText.Command = f"? line.{nome}.units"
        return objeto_dss.dssText.Result.strip().lower()
    except Exception:
        return ""


# ============================================================
# Conversao barra a barra / elemento a elemento
# ============================================================

def _converter_barras(objeto_dss, rede: RedeEletrica):
    for nome_barra in objeto_dss.dssCircuit.AllBusNames:
        nome_base = _nome_base_barra(nome_barra)
        # Vários nós da mesma barra viram uma barra só; o teste evita
        # recriar a barra a cada fase.
        if nome_base in rede.barras:
            continue
        kv_base = _kv_ll(objeto_dss, nome_barra)
        rede.adicionar_barra(nome_base, kv_base or 13.8)


def _converter_linhas(objeto_dss, rede: RedeEletrica):
    dssLines = objeto_dss.dssCircuit.Lines
    if dssLines.First == 0:
        return

    while True:
        nome_dss = dssLines.Name
        nome = f"L_{nome_dss}"
        bus1 = _nome_base_barra(dssLines.Bus1)
        bus2 = _nome_base_barra(dssLines.Bus2)
        fases = objeto_dss.dssCktElement.NumPhases

        # A consulta textual da unidade fica por último: a matriz é lida
        # pelo próprio iterador (dssLines), que é a única leitura em que
        # cada linha devolve a matriz dela mesma.
        comprimento = dssLines.Length
        r1, x1 = _r1_x1_aproximados(dssLines, fases)
        unidade = _unidade_da_linha(objeto_dss, nome_dss)

        # No circuito de origem, o comprimento declarado e a impedância por
        # unidade compartilham a MESMA unidade. Normalizar os dois para km
        # (mesma linha física, valores por km) elimina a ambiguidade de
        # unidade na reexportação: com impedância direta na linha, o motor
        # não reproduz fielmente unidades como o pé, e km é a representação
        # invariante medida nele.
        fator = FATOR_PARA_KM.get(unidade, 1.0)
        comprimento_km = round(comprimento * fator, 8)

        r1, x1 = round(r1 / fator, 4), round(x1 / fator, 4)
        # Mesma regra prática de dimensionamento_regras.py: sequência zero
        # como 3x a sequência positiva.
        r0, x0 = round(r1 * 3, 4), round(x1 * 3, 4)

        if bus1 in rede.barras and bus2 in rede.barras and bus1 != bus2:
            try:
                rede.adicionar_ramo(
                    "Line", nome, bus1, bus2,
                    {"phases": fases, "length": comprimento_km, "units": "km",
                     "linecode": "", "r1": r1, "x1": x1, "r0": r0, "x0": x0})
            except ValueError:
                # Ramo duplicado ou inválido: a linha é descartada sem
                # interromper a conversão do restante do sistema.
                pass

        if dssLines.Next == 0:
            break


def _converter_transformadores(objeto_dss, rede: RedeEletrica):
    """Agrupa transformadores por par de barras e colapsa bancos de
    reguladores monofásicos num único transformador trifásico equivalente,
    de impedância mínima.

    Ver a nota de transparência metodológica no topo do arquivo, item 2.
    """

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
        # Em banco trifásico a tensão informada é de linha; no monofásico é
        # fase-neutro, daí a divisão por raiz de 3.
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
            # Ligação em estrela é a hipótese segura quando a propriedade
            # não está disponível no binding.
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
        # Sem leitura da fonte, usa-se a tensão da própria barra com 1,0 pu.
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
    """Monta uma RedeEletrica equivalente ao circuito já compilado e
    resolvido em objeto_dss (instância dss_engine.DSS).

    A ordem importa: as barras precisam existir antes dos ramos e das
    derivações, que validam suas extremidades contra elas.
    """

    rede = RedeEletrica()
    _converter_barras(objeto_dss, rede)
    _converter_linhas(objeto_dss, rede)
    _converter_transformadores(objeto_dss, rede)
    _converter_capacitores(objeto_dss, rede)
    _converter_cargas(objeto_dss, rede)
    _converter_fonte(objeto_dss, rede)
    return rede


def exportar_sistema_como_projeto(objeto_dss, nome_projeto: str) -> Projeto:
    """Converte o sistema e grava como novo Projeto (rede.json), pronto
    para abrir no Editor de Rede Elétrica. Devolve o Projeto criado."""

    rede = converter_sistema_para_rede(objeto_dss)

    projeto = criar_ou_abrir_projeto_por_nome(nome_projeto)
    caminho_rede_json = os.path.join(projeto.caminho_rede, "rede.json")
    rede.salvar_json(caminho_rede_json)

    return projeto