__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Tradução do modelo da rede (RedeEletrica) para arquivos .dss do OpenDSS.

O OpenDSS não é programado no sentido usual: ele lê um arquivo de texto em
que cada linha é um comando ("New Line.L1 bus1=B1 bus2=B2 ..."). Este módulo
é o tradutor entre o grafo que o editor mantém em memória e esse texto.
Ao final sai um Master.dss que apenas encadeia os demais arquivos (via
Redirect) e manda o motor resolver o circuito. A sintaxe dos comandos segue
a documentação oficial do EPRI (opendss.epri.com).

Dois tipos de curva entram junto com os elementos. As LoadShape (curva de
24 h) descrevem o comportamento diário de Cargas, Geradores, PVSystems e
Storage. As XYCurve são outra coisa: relacionam duas grandezas quaisquer e
aqui servem às leis Volt-Var e Volt-Watt do InvControl que acompanha o
Sistema BESS.
"""
import os
from typing import Dict, Any, Set

from .modelo_rede import RedeEletrica
from .layout_automatico import calcular_posicoes
from .curvas import obter_curva
from .curvas_padrao import criar_curva_padrao


# ============================================================
# TRANSPARÊNCIA TÉCNICA — defaults NÃO-nulos do motor (medidos)
# ============================================================
# O motor do OpenDSS preenche sozinho os parâmetros que o usuário não
# declarou — e nem sempre com zero. Dois desses defaults mexem em resultados
# de perdas e de reativo sem aparecer em lugar nenhum do arquivo .dss. Foram
# medidos no motor real (dss-python 0.15.7) nesta revisão, por leitura de
# volta dos valores internos e pelo efeito nas perdas e na carga capacitiva:
#
#   * Transformer de 2 enrolamentos sem %loadloss: o motor aplica %r = 0,2 %
#     em CADA enrolamento, o que soma uma resistência série de
#     aproximadamente 0,4043 % referida ao próprio trafo. Aquele trafo que o
#     usuário desenhou como ideal perde uns 0,4 % em silêncio.
#   * Line sem c1/c0: o motor aplica C1 = 3,4 nF/km e C0 = 1,6 nF/km. A
#     linha passa a ter capacitância sem ninguém ter pedido.
#
# A consequência para o exportador é uma regra só: c1/c0 (Line) e
# loadloss/noloadloss (Transformer) saem no comando APENAS quando o usuário
# informa um valor, e esse valor precisa vir de placa, ensaio ou catálogo do
# fabricante. Nada é estimado aqui. Chave ausente ou vazia simplesmente não
# vira comando e o default acima é o que vale — este bloco documenta o
# default, não o impõe.
#
# A sintaxe foi validada no motor real: c1=/c0= em Line e %loadloss=/
# %noloadloss= em Transformer, com o "%" aceito e o nome da propriedade
# insensível a maiúsculas. Os dicts do modelo guardam a chave sem "%" e o
# símbolo é recolocado na hora de emitir, do mesmo jeito que "pctstored" vira
# "%stored=" em _fmt_storage.
#
# Há uma hierarquia entre esses parâmetros, medida no motor: um %r explícito
# (mesmo %r=0) ANULA o %loadloss. O editor não expõe %r em trafo, então essa
# armadilha não é alcançável por aqui — e é por isso que não há guarda para
# ela no código.
#
# E há uma armadilha que explica por que %noloadloss não serve, sozinho, para
# corrigir perdas: ele desloca o ponto de operação do trafo. Medição em trafo
# de 100 kVA 13,8/0,4 kV com xhl=5 %: declarando %noloadloss=0,25 e nada de
# %loadloss, o motor apresentou R = 0,2 ohm (o mesmo %r default) e as perdas
# de série saltaram de 454,7 W para 1.387,5 W — a perda a vazio tinha virado
# parcela em série. Declarando %loadloss=1,2 os números voltam a fazer
# sentido: 1.393,6 W em série mais 235,7 W no núcleo, para 100 kVA. Daí a
# recomendação prática: %loadloss sempre que houver %noloadloss, porque no
# ensaio de trafo os dois andam juntos. O exportador emite o que o usuário
# informou e não completa o par por conta própria.


# ============================================================
# Formatadores de elementos
# ============================================================

def _sufixo_curva(p: Dict[str, Any]) -> str:
    """Devolve ' daily=<nome>' quando o elemento aponta para uma curva
    diária, e string vazia quando não aponta.

    'Nenhuma' é o texto que o formulário grava quando o usuário desmarca a
    curva, por isso conta como ausência de curva.
    """
    nome_curva = p.get("daily")
    if nome_curva and str(nome_curva).strip() and str(nome_curva) != "Nenhuma":
        return f" daily={nome_curva}"
    return ""


def _tem_curva_projeto(p: Dict[str, Any]) -> bool:
    """A mesma pergunta de _sufixo_curva, respondida com sim ou não.

    Serve para decidir, antes de montar o comando, se o elemento já tem curva
    própria, caso em que a curva padrão embutida não deve ser injetada.
    """
    nome_curva = str(p.get("daily", "") or "").strip()
    return bool(nome_curva) and nome_curva != "Nenhuma"


def _opcionais(p: Dict[str, Any], pares) -> str:
    """Monta o sufixo do comando com os parâmetros que o usuário declarou.

    `pares` é uma sequência de (chave_no_dict, texto_no_comando). Um par entra
    no comando apenas se a chave existir em `p` e se o valor, convertido em
    texto e aparado, não estiver vazio. Faltando a chave ou estando o valor em
    branco, o parâmetro não é emitido e quem decide é o motor, com o default
    dele — o bloco TRANSPARÊNCIA TÉCNICA no topo do módulo lista os que não
    são zero. Esse é o mecanismo que mantém o exportador fora da decisão sobre
    perdas e capacitância: ele não inventa, e o que não foi dado não aparece.

    Quem chama informa o nome de cada chave sem o "%" e o nome do comando com
    ele, porque o dict do modelo e a propriedade do OpenDSS não usam a mesma
    grafia. O caso equivalente em _fmt_storage é "pctstored" -> "%stored=".
    """
    partes = []
    for chave, comando in pares:
        if chave not in p:
            continue
        valor = str(p.get(chave)).strip()
        if valor:
            partes.append(f" {comando}={valor}")
    return "".join(partes)


# Unidades de comprimento aceitas pelo OpenDSS e o fator de conversao de
# cada uma para o quilometro (1 mi = 1,609344 km; 1 ft = 0,0003048 km).
# "none" significa unidade ausente e o motor a trata como quilometro.
FATOR_PARA_KM = {
    "km": 1.0, "m": 0.001, "cm": 0.00001,
    "mi": 1.609344, "kft": 0.3048, "ft": 0.0003048, "in": 0.0000254,
    "none": 1.0,
}


def _num(v: float) -> str:
    # Dez algarismos significativos: preserva o valor sem arrastar residuos
    # binarios do produto por um fator (2000 * 0.0003048 sai "0.6096",
    # nao "0.60960000000001").
    return f"{v:.10g}"


def _fmt_line(nome, bus1, bus2, p: Dict[str, Any]) -> str:
    """Comando New Line com comprimento e impedancias NORMALIZADOS PARA KM.

    Por que normalizar: medido no motor real (dss-python 0.15.7), a mesma
    linha fisica grafada como 'length=2000 units=ft' com r1/x1 declarados
    diretamente na linha NAO reproduz a mesma linha grafada em km — perdas
    e quedas divergem (a unidade ft, acompanhada de impedancia direta, nao
    e invariante). Em km, ou com a unidade omitida, o resultado e exato e
    independe de como o projeto original guardou o comprimento. O modelo
    guarda length/units/r1/x1 coerentes entre si ("R1 (ohm/unid)"), de modo
    que converter os dois pelo mesmo fator preserva a linha fisica:
    length_km = length x fator e r1_km = r1 / fator.
    """
    linecode = str(p.get("linecode", "")).strip()

    if linecode:
        # Com linecode, a impedancia por unidade vive no linecode, nao aqui;
        # converter o comprimento sem converter o linecode trocaria uma
        # incoerencia por outra. Passa sem conversao.
        return (f"New Line.{nome} bus1={bus1} bus2={bus2} "
                f"phases={p.get('phases', 3)} length={p.get('length', 1)} "
                f"units={p.get('units', 'km')} linecode={linecode}")

    fator = FATOR_PARA_KM.get(str(p.get("units", "km")).strip().lower(), 1.0)
    comando = (f"New Line.{nome} bus1={bus1} bus2={bus2} "
               f"phases={p.get('phases', 3)} "
               f"length={_num(float(p.get('length', 1)) * fator)} units=km "
               f"r1={_num(float(p.get('r1', 0.1)) / fator)} "
               f"x1={_num(float(p.get('x1', 0.2)) / fator)} "
               f"r0={_num(float(p.get('r0', 0.3)) / fator)} "
               f"x0={_num(float(p.get('x0', 0.4)) / fator)}")

    # A capacitancia (nF por unidade de comprimento) acompanha a mesma
    # normalizacao das impedancias: por km, e o valor dividido pelo fator.
    for chave, nome_comando in (("c1", "c1"), ("c0", "c0")):
        if chave in p and str(p[chave]).strip():
            comando += f" {nome_comando}={_num(float(p[chave]) / fator)}"
    return comando


def _fmt_switch(nome, bus1, bus2, p: Dict[str, Any]) -> str:
    fechada = str(p.get("fechada", "yes")).lower() in ("yes", "sim", "true", "1")

    linha = (f"New Line.{nome} bus1={bus1} bus2={bus2} "
             f"phases={p.get('phases', 3)} switch=yes "
             f"r1=1e-4 r0=1e-4 x1=1e-4 x0=1e-4 c1=0 c0=0")

    if not fechada:
        linha += f"\nOpen Line.{nome} term=1"

    return linha


def _fmt_transformer(nome, bus1, bus2, p: Dict[str, Any]) -> str:
    kv1 = p.get("kv1", 13.8)
    kv2 = p.get("kv2", 0.38)
    kva = p.get("kva", 150)
    conn1 = p.get("conn1", "wye")
    conn2 = p.get("conn2", "wye")
    xhl = p.get("xhl", 2.0)

    return (f"New Transformer.{nome} phases={p.get('phases', 3)} windings=2 "
            f"buses=({bus1},{bus2}) conns=({conn1},{conn2}) "
            f"kvs=({kv1},{kv2}) kvas=({kva},{kva}) xhl={xhl}"
            + _opcionais(p, (("loadloss", "%loadloss"),
                             ("noloadloss", "%noloadloss"))))


def _fmt_load(nome, bus1, p: Dict[str, Any]) -> str:
    base = (f"New Load.{nome} bus1={bus1} phases={p.get('phases', 3)} "
            f"kv={p.get('kv', 0.38)} kw={p.get('kw', 10)} "
            f"kvar={p.get('kvar', 3)} model={p.get('model', 1)} "
            f"conn={p.get('conn', 'wye')}")
    return base + _sufixo_curva(p)


def _fmt_generator(nome, bus1, p: Dict[str, Any]) -> str:
    base = (f"New Generator.{nome} bus1={bus1} phases={p.get('phases', 3)} "
            f"kv={p.get('kv', 0.38)} kw={p.get('kw', 50)} "
            f"kvar={p.get('kvar', 0)} model={p.get('model', 1)}")
    return base + _sufixo_curva(p)


def _fmt_capacitor(nome, bus1, p: Dict[str, Any]) -> str:
    return (f"New Capacitor.{nome} bus1={bus1} phases={p.get('phases', 3)} "
            f"kv={p.get('kv', 13.8)} kvar={p.get('kvar', 300)}")


def _fmt_pvsystem(nome, bus1, p: Dict[str, Any]) -> str:
    base = (f"New PVSystem.{nome} bus1={bus1} phases={p.get('phases', 3)} "
            f"kv={p.get('kv', 0.38)} kva={p.get('kva', 100)} "
            f"pmpp={p.get('pmpp', 100)} irradiance={p.get('irradiance', 1.0)} "
            f"%cutin={p.get('cutin', 2)} %cutout={p.get('cutout', 2)}")
    return base + _sufixo_curva(p)


def _fmt_storage(nome, bus1, p: Dict[str, Any]) -> str:
    base = (f"New Storage.{nome} bus1={bus1} phases={p.get('phases', 3)} "
            f"kv={p.get('kv', 0.38)} kwrated={p.get('kwrated', 50)} "
            f"kwhrated={p.get('kwhrated', 100)} "
            f"%stored={p.get('pctstored', 50)} "
            f"dispmode={p.get('dispmode', 'default')} "
            f"state={p.get('state', 'idling')}")
    return base + _sufixo_curva(p)


def _fmt_reactor(nome, bus1, p: Dict[str, Any]) -> str:
    """Reator em derivação (banco de indutância), tipicamente para compensar
    reativo capacitivo da linha em regime leve.

    Sintaxe conforme a documentação do EPRI
    (opendss.epri.com/Reactor.html).
    """
    return (f"New Reactor.{nome} bus1={bus1} phases={p.get('phases', 3)} "
            f"kv={p.get('kv', 13.8)} kvar={p.get('kvar', 300)}")


def _fmt_invcontrol(nome, bus1, p: Dict[str, Any]) -> str:
    """Comando do InvControl, o controlador que impõe a lei de tensão ao
    inversor de um Storage.

    O InvControl não ocupa barra nenhuma: recebe `bus1` na assinatura apenas
    para respeitar o formato dos demais formatadores e não o usa. Quem ele
    controla vem em DERList, que aponta para o elemento (em geral um Storage).
    As curvas de Volt-Var e Volt-Watt entram por vvc_curve1 e pelas chaves de
    curva de Watt, que precisam já existir como XYCurve quando este comando
    for lido.

    Sintaxe conforme a documentação do EPRI e da dss-extensions.org.
    """
    partes = [f"New InvControl.{nome}"]

    if "DERList" in p:
        partes.append(f"DERList={p['DERList']}")

    for chave in ("Mode", "CombiMode", "vvc_curve1", "voltwatt_curve",
                  "VoltWattCH_Curve", "RefReactivePower"):
        if chave in p:
            partes.append(f"{chave}={p[chave]}")

    return " ".join(partes)


def _fmt_circuit(nome_circuito, bus1, p: Dict[str, Any]) -> str:
    return (f"New Circuit.{nome_circuito} basekv={p.get('basekv', 13.8)} "
            f"pu={p.get('pu', 1.0)} phases={p.get('phases', 3)} bus1={bus1} "
            f"MVAsc3={p.get('mvasc3', 2000)} MVAsc1={p.get('mvasc1', 2100)}")


def _fmt_energymeter(nome, elemento, terminal) -> str:
    """Medidor de energia: o 2º argumento do comando é o ELEMENTO
    monitorado (ex.: Line.L1), não uma barra — é o ponto da rede onde a
    medição de energia fica, normalmente o ramo da subestação.

    Sintaxe verificada no motor real (dss-python 0.15.7) e no exemplo
    oficial IEEE 123 deste repositório (Run_IEEE123Bus.DSS, linha 45:
    "New EnergyMeter.Feeder Line.L115 1"). Aqui o comando sai na forma
    nomeada (element=/terminal=), seguindo o padrão dos demais
    formatadores do módulo. O motor só aceita elemento de entrega de
    potência no alvo: a validação de existência é feita antes, na
    geração do Master (um medidor órfão não pode virar .dss quebrado em
    silêncio).
    """
    return f"New EnergyMeter.{nome} element={elemento} terminal={terminal}"


def _fmt_loadshape(curva) -> str:
    """Comando New Loadshape, a curva de 24 h de um elemento.

    Sai com hour= e mult= em vez de npts= e interval=, porque hour aceita
    pontos em instantes irregulares — que é exatamente o que o editor gráfico
    do usuário produz quando ele arrasta um ponto para as 18h30, por exemplo.
    """
    horas = curva.horas()
    mults = curva.multiplicadores()
    npts = len(horas)
    horas_str = ", ".join(f"{h:g}" for h in horas)
    mults_str = ", ".join(f"{m:.4f}" for m in mults)
    return f"New Loadshape.{curva.nome} npts={npts} hour=({horas_str}) mult=({mults_str})"


def _fmt_xycurve(curva) -> str:
    """Comando New XYCurve: pares (x, y) que descrevem uma relação, não uma
    variação no tempo.

    No Sistema BESS, x é a tensão em pu e y é a potência reativa (Volt-Var) ou
    a potência ativa (Volt-Watt) pedida ao inversor. Sintaxe padrão do
    OpenDSS: npts, xarray, yarray.
    """
    xstr = ", ".join(f"{x:g}" for x in curva.xarray)
    ystr = ", ".join(f"{y:g}" for y in curva.yarray)
    return f"New XYCurve.{curva.nome} npts={curva.npts} xarray=({xstr}) yarray=({ystr})"


FORMATADORES_RAMO = {
    "Line": _fmt_line,
    "Switch": _fmt_switch,
    "Transformer": _fmt_transformer,
}

FORMATADORES_DERIVACAO = {
    "Load": _fmt_load,
    "Generator": _fmt_generator,
    "Capacitor": _fmt_capacitor,
    "PVSystem": _fmt_pvsystem,
    "Storage": _fmt_storage,
    "Reactor": _fmt_reactor,
    "InvControl": _fmt_invcontrol,
}

ARQUIVO_POR_TIPO = {
    "Line": "linhas.dss",
    "Switch": "linhas.dss",
    "Transformer": "transformadores.dss",
    "Load": "cargas.dss",
    "Generator": "geradores.dss",
    "Capacitor": "capacitores.dss",
    "PVSystem": "pvsystems.dss",
    "Storage": "storage.dss",
    "Reactor": "reatores.dss",
    "InvControl": "invcontrol.dss",
    "EnergyMeter": "medidores.dss",
}

# A ordem abaixo não é cosmética. O OpenDSS compila os Redirect na sequência
# em que aparecem, e um comando que cita outro elemento exige que o citado já
# tenha sido definido. Por isso storage.dss e curvas_xy.dss vêm antes de
# invcontrol.dss: o InvControl referencia um Storage em DERList e/ou uma
# XYCurve em vvc_curve1 e voltwatt_curve.
#
# medidores.dss fecha a lista pelo mesmo motivo. O EnergyMeter aponta para um
# elemento que já precisa existir (um Line.L1, por exemplo) e, ao ser criado,
# reorganiza a zona do circuito em torno de si — então ele entra depois dos
# elementos e antes do Solve. O exemplo oficial IEEE 123 que acompanha este
# repositório faz igual.
ORDEM_REDIRECT = [
    "curvas.dss",        # LoadShapes (Load/Generator/PVSystem/Storage)
    "curvas_xy.dss",     # XYCurves (Volt-Var/Volt-Watt do InvControl)
    "linhas.dss",
    "transformadores.dss",
    "cargas.dss",
    "geradores.dss",
    "capacitores.dss",
    "pvsystems.dss",
    "storage.dss",
    "reatores.dss",
    "invcontrol.dss",
    "medidores.dss",
]

TIPOS_COM_CURVA = {"Load", "Generator", "PVSystem", "Storage"}


def gerar_arquivos_dss(rede: RedeEletrica, pasta_destino: str,
                        nome_circuito: str = "MeuCircuito",
                        pasta_curvas: str = None,
                        dia_curvas_padrao: str = None) -> str:
    """Escreve os arquivos .dss da rede e devolve o caminho do Master.dss.

    O resultado é um arquivo por categoria de elemento (linhas.dss,
    cargas.dss, transformadores.dss, medidores.dss...) mais curvas.dss,
    curvas_xy.dss e buscoords.dss. O Master.dss não contém elemento nenhum:
    ele encadeia os outros por Redirect, define as bases de tensão e pede o
    Solve.

    Parameters
    ----------
    pasta_curvas : str, opcional
        Pasta onde estão as curvas características do projeto
        (Projeto.caminho_curvas). Só é necessária quando algum elemento
        aponta para uma curva diária; sem essa referência, pode vir None.
    dia_curvas_padrao : str, opcional
        Dia da semana (por exemplo 'Segunda'). Preenchido, a função injeta as
        curvas padrão embutidas da ferramenta nos elementos Load e PVSystem
        que estiverem sem curva de projeto vinculada.

        TRANSPARÊNCIA TÉCNICA — precedência e não-mutação:
            Curva vinculada ao projeto sempre ganha. A injeção só acontece em
            Load e PVSystem sem vínculo; Generator e Storage nunca recebem
            curva padrão, porque a curva de um gerador despachável não é
            dada pela ferramenta.

            A injeção acontece sobre uma CÓPIA dos parâmetros do elemento,
            feita só para a emissão. O modelo em memória — o que está em
            rede.json — não é tocado, de modo que exportar duas vezes com
            dias diferentes não contamina o projeto.

            Com dia_curvas_padrao=None nada é injetado e o resultado é o
            mesmo de antes de a opção existir. Os LoadShapes sintéticos levam
            o prefixo '__Padrao_' para não colidirem com curva criada pelo
            usuário, e vêm da biblioteca interna (criar_curva_padrao), sem
            exigir pasta de curvas do projeto.

    Retorna o caminho completo do Master.dss gerado.
    """

    os.makedirs(pasta_destino, exist_ok=True)

    fonte = rede.obter_fonte()
    if fonte is None:
        raise ValueError(
            "É necessário haver exatamente UMA barra do tipo 'Fonte (Vsource)' "
            "na rede antes de exportar."
        )

    # -------- 1) Distribui os comandos pelos arquivos de destino -------- #
    # Cada categoria de elemento tem seu arquivo, e o dicionário abaixo é o
    # que faz essa separação: a chave é o nome do arquivo, o valor é a lista
    # de linhas que vão para ele.
    conteudo_por_arquivo: Dict[str, list] = {}
    nomes_curvas_referenciadas: Set[str] = set()
    nomes_curvas_padrao: Dict[str, Any] = {}

    for ramo in rede.ramos.values():
        formatador = FORMATADORES_RAMO.get(ramo.tipo)
        if not formatador:
            continue
        linha = formatador(ramo.nome, ramo.bus1, ramo.bus2, ramo.parametros)
        arquivo = ARQUIVO_POR_TIPO[ramo.tipo]
        conteudo_por_arquivo.setdefault(arquivo, []).append(linha)

    for der in rede.derivacoes.values():
        # Dois tipos de derivação não passam por aqui. A Vsource não é um
        # elemento do circuito, é a própria barra de referência: ela vira o
        # comando New Circuit do Master. O EnergyMeter precisa validar antes
        # qual elemento pretende medir, e essa checagem mora no bloco 1b.
        if der.tipo in ("Vsource", "EnergyMeter"):
            continue
        formatador = FORMATADORES_DERIVACAO.get(der.tipo)
        if not formatador:
            continue

        if der.tipo in TIPOS_COM_CURVA:
            nome_curva = der.parametros.get("daily")
            if nome_curva and str(nome_curva) != "Nenhuma":
                nomes_curvas_referenciadas.add(str(nome_curva))

        # Injeção de curva padrão, restrita a Load e PVSystem sem curva de
        # projeto. A emissão usa uma CÓPIA dos parâmetros: o dict do chamador
        # fica intocado e a curva padrão não contamina o rede.json.
        if (dia_curvas_padrao and der.tipo in ("Load", "PVSystem")
                and not _tem_curva_projeto(der.parametros)):
            natureza = "geracao" if der.tipo == "PVSystem" else "carga"
            prefixo = "Geracao" if natureza == "geracao" else "Carga"
            nome_sintetico = f"__Padrao_{prefixo}_{dia_curvas_padrao}"
            nomes_curvas_padrao[nome_sintetico] = (natureza, dia_curvas_padrao)
            p_emissao = dict(der.parametros)
            p_emissao["daily"] = nome_sintetico
            linha = formatador(der.nome, der.bus1, p_emissao)
            arquivo = ARQUIVO_POR_TIPO[der.tipo]
            conteudo_por_arquivo.setdefault(arquivo, []).append(linha)
            continue

        linha = formatador(der.nome, der.bus1, der.parametros)
        arquivo = ARQUIVO_POR_TIPO[der.tipo]
        conteudo_por_arquivo.setdefault(arquivo, []).append(linha)

    # -------- 1b) Medidores de energia (EnergyMeter) -------- #
    # Fora do laço genérico de propósito. O comando do medidor não aponta para
    # uma barra, e sim para outro elemento do circuito, então ele carrega um
    # risco que nenhum outro formatador carrega: o alvo pode ter sido
    # excluído ou renomeado e o medidor ficar apontando para o vazio. Um
    # Master.dss assim chega ao motor e falha com mensagem genérica, longe da
    # causa. Aqui a conferência acontece antes de escrever qualquer arquivo e
    # a exceção diz qual medidor e qual elemento estão em desacordo.
    for der in rede.derivacoes.values():
        if der.tipo != "EnergyMeter":
            continue
        elemento = str(der.parametros.get("element", "") or "").strip()
        if rede.resolver_alvo_medidor(elemento, der.parametros.get("terminal", 1)) is None:
            raise ValueError(
                f"O medidor '{der.nome}' monitora o elemento "
                f"'{elemento or '(vazio)'}', que não existe mais na rede. "
                "Edite ou exclua o medidor antes de exportar.")
        terminal = int(float(der.parametros.get("terminal", 1)))
        conteudo_por_arquivo.setdefault("medidores.dss", []).append(
            _fmt_energymeter(der.nome, elemento, terminal))

    # -------- 2) curvas.dss: as LoadShapes citadas pelos elementos -------- #
    curvas_dss_gerado = False
    if nomes_curvas_referenciadas or nomes_curvas_padrao:
        if nomes_curvas_referenciadas and not pasta_curvas:
            raise ValueError(
                "A rede possui elementos com curva diária associada, mas "
                "nenhuma pasta de curvas do projeto foi informada.")

        linhas_curvas = []

        # Primeiro as curvas padrão embutidas (prefixo __Padrao_), que saem da
        # biblioteca interna e por isso não dependem da pasta do projeto.
        for nome_sintetico in sorted(nomes_curvas_padrao):
            natureza, dia = nomes_curvas_padrao[nome_sintetico]
            curva = criar_curva_padrao(nome_sintetico, natureza, dia)
            if len(curva.pontos) < 2:
                raise ValueError(
                    f"A curva '{nome_sintetico}' possui menos de 2 pontos definidos.")
            linhas_curvas.append(_fmt_loadshape(curva))

        # Depois as curvas do projeto. Aqui a pasta é obrigatória: se o
        # elemento cita uma curva e ela não está no repositório do projeto, o
        # .dss sairia com um daily= apontando para o nada.
        for nome_curva in sorted(nomes_curvas_referenciadas):
            curva = obter_curva(pasta_curvas, nome_curva)
            if not curva:
                raise ValueError(
                    f"A curva '{nome_curva}' referenciada na rede não foi "
                    "encontrada no repositório de curvas do projeto.")
            if len(curva.pontos) < 2:
                raise ValueError(
                    f"A curva '{nome_curva}' possui menos de 2 pontos definidos.")
            linhas_curvas.append(_fmt_loadshape(curva))

        caminho_curvas_dss = os.path.join(pasta_destino, "curvas.dss")
        with open(caminho_curvas_dss, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas_curvas) + "\n")
        curvas_dss_gerado = True

    # -------- 3) curvas_xy.dss: as XYCurves (Volt-Var e Volt-Watt) -------- #
    curvas_xy_dss_gerado = False
    if rede.curvas_xy:
        linhas_xy = [_fmt_xycurve(curva) for curva in rede.curvas_xy.values()]
        caminho_curvas_xy_dss = os.path.join(pasta_destino, "curvas_xy.dss")
        with open(caminho_curvas_xy_dss, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas_xy) + "\n")
        curvas_xy_dss_gerado = True

    # -------- 4) Escreve um arquivo por categoria de elemento -------- #
    for arquivo, linhas in conteudo_por_arquivo.items():
        caminho = os.path.join(pasta_destino, arquivo)
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas) + "\n")

    # -------- 5) buscoords.dss: posição de cada barra para o desenho -------- #
    # O OpenDSS só usa este arquivo para desenhar o diagrama na interface
    # dele; não entra em cálculo nenhum. As coordenadas vêm do layout
    # automático, o mesmo que posiciona as barras no editor.
    posicoes = calcular_posicoes(rede)
    caminho_coords = os.path.join(pasta_destino, "buscoords.dss")
    with open(caminho_coords, "w", encoding="utf-8") as f:
        for nome in rede.barras:
            x, y = posicoes.get(nome, (0, 0))
            f.write(f"{nome} {x} {y}\n")

    # -------- 6) Monta o Master.dss -------- #
    # Uma base de tensão por valor de kV distinto na rede, da maior para a
    # menor. O motor precisa dessa lista para montar as matrizes por nível de
    # tensão antes de resolver.
    kvs_base = sorted({b.kv_base for b in rede.barras.values()}, reverse=True)
    voltagebases = ", ".join(str(kv) for kv in kvs_base)

    linhas_master = [
        "Clear",
        "",
        "! Fonte / Subestação",
        _fmt_circuit(nome_circuito, fonte.bus1, fonte.parametros),
        "",
    ]

    for arquivo in ORDEM_REDIRECT:
        # curvas.dss e curvas_xy.dss só entram quando foram de fato escritos;
        # um Redirect para arquivo inexistente derrubaria a compilação.
        if arquivo == "curvas.dss":
            if curvas_dss_gerado:
                linhas_master.append(f"Redirect {arquivo}")
            continue
        if arquivo == "curvas_xy.dss":
            if curvas_xy_dss_gerado:
                linhas_master.append(f"Redirect {arquivo}")
            continue
        if arquivo in conteudo_por_arquivo:
            linhas_master.append(f"Redirect {arquivo}")

    linhas_master += [
        "",
        "Buscoords buscoords.dss",
        "",
        f"Set VoltageBases = ({voltagebases})",
        "CalcVoltageBases",
        "",
        "Solve",
    ]

    caminho_master = os.path.join(pasta_destino, "Master.dss")
    with open(caminho_master, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas_master) + "\n")

    return caminho_master