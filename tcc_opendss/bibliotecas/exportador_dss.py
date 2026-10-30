__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Exporter: converte o Model (RedeEletrica) em arquivos .dss reais,
seguindo a sintaxe oficial do OpenDSS (opendss.epri.com), incluindo as
curvas características (LoadShape) associadas a Cargas, Geradores,
PVSystems e Storage, e as curvas XY (XYCurve) associadas ao InvControl
(Volt-Var / Volt-Watt), usadas pelo Sistema BESS composto."""

import os
from typing import Dict, Any, Set

from .modelo_rede import RedeEletrica
from .layout_automatico import calcular_posicoes
from .curvas import obter_curva
from .curvas_padrao import criar_curva_padrao


# ============================================================
# TRANSPARÊNCIA TÉCNICA — defaults NÃO-nulos do motor (medidos)
# ============================================================
# Medido no motor real (dss-python 0.15.7) nesta revisão, via read-back e por
# efeito nas perdas/na carga capacitiva:
#
#   * Transformer de 2 enrolamentos SEM %loadloss declarado: o motor aplica
#     dois %r default de 0,2 % (um por enrolamento), o que resulta numa
#     R série efetiva ≈ 0,4043 % (referida ao próprio trafo). O trafo que o
#     usuário desenhou como "ideal" perde, silenciosamente, ~0,4 %.
#   * Line SEM c1/c0 declarados: o motor aplica C1 = 3,4 nF/km e
#     C0 = 1,6 nF/km. A linha carrega capacitância mesmo sem ninguém pedir.
#
# Por isso os parâmetros c1/c0 (Line) e loadloss/noloadloss (Transformer) são
# emitidos SOMENTE quando o usuário os informa, com dado REAL de placa,
# ensaio ou catálogo do fabricante — é o que remove o fantasma. Nenhuma
# estimativa é inventada por este módulo: chave ausente ou vazia não vira
# comando, e o default do motor (acima) é o que vale. O que este bloco faz é
# documentar o default; não é o exportador quem o impõe.
#
# Sintaxe validada funcionalmente no motor real: c1=/c0= em Line e
# %loadloss=/%noloadloss= em Transformer (o "%" é aceito e o nome da
# propriedade é insensível a caixa; aqui o dict usa a chave sem "%" e o "%" é
# recolocado na emissão — precedente: "pctstored" -> "%stored=").
#
# Hierarquia medida: %r explícito (inclusive %r=0) ANULA %loadloss. Como o
# editor não expõe %r em trafo, essa armadilha não é alcançável por esta via
# (e é por isso que ela não é guardada aqui).
#
# ARMADILHA MEDIDA no motor real, e o motivo de %noloadloss NÃO ser a via de
# correção das perdas: %noloadloss (sozinho) desloca o ponto de operação do
# trafo. Medido em trafo 100 kVA 13,8/0,4 kV xhl=5 %: com %noloadloss=0,25
# e SEM %loadloss, o motor passou a apresentar R = 0,2 ohm (o mesmo %r
# default), mas as perdas de série subiram de 454,7 W para 1.387,5 W — a
# perda a vazio virou parcela em série. Com %loadloss=1,2 declarado, as
# perdas ficam coerentes (série 1.393,6 W + núcleo 235,7 W para 100 kVA).
# Regra prática desta revisão: declare %loadloss SEMPRE que declarar
# %noloadloss (os dois formam um par no ensaio do trafo). O exportador apenas
# emite o que o usuário informou — não inventa o par.


# ============================================================
# Formatadores de elementos
# ============================================================

def _sufixo_curva(p: Dict[str, Any]) -> str:
    """Retorna ' daily=<nome>' se o elemento tiver uma curva associada,
    ou string vazia caso contrário."""
    nome_curva = p.get("daily")
    if nome_curva and str(nome_curva).strip() and str(nome_curva) != "Nenhuma":
        return f" daily={nome_curva}"
    return ""


def _tem_curva_projeto(p: Dict[str, Any]) -> bool:
    """Mesma semântica de _sufixo_curva, em forma booleana: True quando o
    elemento referencia uma curva diária de projeto (não vazia/'Nenhuma')."""
    nome_curva = str(p.get("daily", "") or "").strip()
    return bool(nome_curva) and nome_curva != "Nenhuma"


def _opcionais(p: Dict[str, Any], pares) -> str:
    """Monta o sufixo dos parâmetros declarados pelo usuário.

    `pares` é uma sequência de (chave_no_dict, texto_no_comando). Só entra no
    comando o par cuja chave exista em `p` E cujo valor, convertido por str()
    e aparado, não seja vazio. Chave ausente ou vazia = o parâmetro NÃO é
    emitido, e o motor aplica o default dele (ver TRANSPARÊNCIA TÉCNICA no
    topo do módulo). O mapeamento sem "%" no dict -> com "%" no comando segue
    o precedente de "pctstored" -> "%stored=" em _fmt_storage.
    """
    partes = []
    for chave, comando in pares:
        if chave not in p:
            continue
        valor = str(p.get(chave)).strip()
        if valor:
            partes.append(f" {comando}={valor}")
    return "".join(partes)


def _fmt_line(nome, bus1, bus2, p: Dict[str, Any]) -> str:
    linecode = str(p.get("linecode", "")).strip()
    base = (f"New Line.{nome} bus1={bus1} bus2={bus2} "
            f"phases={p.get('phases', 3)} length={p.get('length', 1)} "
            f"units={p.get('units', 'km')}")

    if linecode:
        return f"{base} linecode={linecode}"

    return (f"{base} r1={p.get('r1', 0.1)} x1={p.get('x1', 0.2)} "
            f"r0={p.get('r0', 0.3)} x0={p.get('x0', 0.4)}"
            + _opcionais(p, (("c1", "c1"), ("c0", "c0"))))


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
    """Sintaxe confirmada por documentação oficial EPRI
    (opendss.epri.com/Reactor.html), colada pelo usuário nesta sessão."""
    return (f"New Reactor.{nome} bus1={bus1} phases={p.get('phases', 3)} "
            f"kv={p.get('kv', 13.8)} kvar={p.get('kvar', 300)}")


def _fmt_invcontrol(nome, bus1, p: Dict[str, Any]) -> str:
    """InvControl NÃO se conecta a uma barra própria (o parâmetro 'bus1'
    é ignorado aqui de propósito) — a referência ao elemento controlado
    (ex.: um Storage) é feita através da propriedade DERList.

    Sintaxe confirmada por documentação oficial colada pelo usuário
    nesta sessão (fonte: EPRI / dss-extensions.org)."""
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


def _fmt_loadshape(curva) -> str:
    """Gera 'New Loadshape...' usando hour= e mult= (aceita pontos com
    intervalos irregulares, exatamente o que o editor gráfico produz)."""
    horas = curva.horas()
    mults = curva.multiplicadores()
    npts = len(horas)
    horas_str = ", ".join(f"{h:g}" for h in horas)
    mults_str = ", ".join(f"{m:.4f}" for m in mults)
    return f"New Loadshape.{curva.nome} npts={npts} hour=({horas_str}) mult=({mults_str})"


def _fmt_xycurve(curva) -> str:
    """Gera 'New XYCurve...', usada pelas curvas Volt-Var/Volt-Watt do
    InvControl. Sintaxe padrão OpenDSS (npts/xarray/yarray)."""
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
}

# IMPORTANTE: storage.dss e curvas_xy.dss precisam vir ANTES de
# invcontrol.dss, pois o InvControl referencia um Storage (via DERList)
# e/ou uma XYCurve (via vvc_curve1/voltwatt_curve) que precisam já
# existir no momento da compilação.
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
]

TIPOS_COM_CURVA = {"Load", "Generator", "PVSystem", "Storage"}


def gerar_arquivos_dss(rede: RedeEletrica, pasta_destino: str,
                        nome_circuito: str = "MeuCircuito",
                        pasta_curvas: str = None,
                        dia_curvas_padrao: str = None) -> str:
    """Gera os arquivos .dss (um por categoria) + o Master.dss que os une.

    Parameters
    ----------
    pasta_curvas : str, opcional
        Pasta onde estão salvas as curvas características do projeto
        (Projeto.caminho_curvas). Necessária apenas se algum elemento
        fizer referência a uma curva diária ('daily').
    dia_curvas_padrao : str, opcional
        Dia da semana (ex.: 'Segunda') para injetar as CURVAS PADRÃO
        embutidas da ferramenta em elementos Load/PVSystem SEM curva de
        projeto vinculada.

        TRANSPARÊNCIA TÉCNICA — precedência e não-mutação:
            Precedência: curva de projeto vinculada ('daily' preenchido)
            SEMPRE prevalece sobre a curva padrão embutida. A injeção
            acontece apenas em Load e PVSystem sem vínculo; Generator e
            Storage nunca recebem curva padrão. O parâmetro 'daily' é
            adicionado numa CÓPIA dos parâmetros do elemento para a
            emissão — o modelo em memória (rede.json) NUNCA é mutado.
            Com dia_curvas_padrao=None, o comportamento é exatamente o
            histórico (nenhuma injeção). Os LoadShapes sintéticos usam o
            prefixo '__Padrao_' para não colidir com curvas do usuário, e
            são resolvidos da biblioteca embutida (criar_curva_padrao) —
            não exigem pasta de curvas do projeto.

    Retorna o caminho completo do Master.dss gerado.
    """

    os.makedirs(pasta_destino, exist_ok=True)

    fonte = rede.obter_fonte()
    if fonte is None:
        raise ValueError(
            "É necessário haver exatamente UMA barra do tipo 'Fonte (Vsource)' "
            "na rede antes de exportar."
        )

    # -------- 1) Agrupa comandos por arquivo de destino -------- #
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
        if der.tipo == "Vsource":
            continue
        formatador = FORMATADORES_DERIVACAO.get(der.tipo)
        if not formatador:
            continue

        if der.tipo in TIPOS_COM_CURVA:
            nome_curva = der.parametros.get("daily")
            if nome_curva and str(nome_curva) != "Nenhuma":
                nomes_curvas_referenciadas.add(str(nome_curva))

        # Injeção de curva padrão: apenas Load/PVSystem SEM curva de
        # projeto. Emite com uma CÓPIA dos parâmetros — der.parametros
        # (o modelo do chamador) permanece intocado.
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

    # -------- 2) Gera curvas.dss (LoadShapes, se houver referenciadas) -------- #
    curvas_dss_gerado = False
    if nomes_curvas_referenciadas or nomes_curvas_padrao:
        if nomes_curvas_referenciadas and not pasta_curvas:
            raise ValueError(
                "A rede possui elementos com curva diária associada, mas "
                "nenhuma pasta de curvas do projeto foi informada.")

        linhas_curvas = []

        # Curvas padrão embutidas (prefixo __Padrao_): resolvidas da
        # biblioteca interna, NÃO exigem pasta de curvas do projeto.
        for nome_sintetico in sorted(nomes_curvas_padrao):
            natureza, dia = nomes_curvas_padrao[nome_sintetico]
            curva = criar_curva_padrao(nome_sintetico, natureza, dia)
            if len(curva.pontos) < 2:
                raise ValueError(
                    f"A curva '{nome_sintetico}' possui menos de 2 pontos definidos.")
            linhas_curvas.append(_fmt_loadshape(curva))

        # Curvas de projeto referenciadas: exigem pasta e devem existir.
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

    # -------- 3) Gera curvas_xy.dss (XYCurves, ex.: usadas pelo InvControl) -------- #
    curvas_xy_dss_gerado = False
    if rede.curvas_xy:
        linhas_xy = [_fmt_xycurve(curva) for curva in rede.curvas_xy.values()]
        caminho_curvas_xy_dss = os.path.join(pasta_destino, "curvas_xy.dss")
        with open(caminho_curvas_xy_dss, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas_xy) + "\n")
        curvas_xy_dss_gerado = True

    # -------- 4) Escreve cada arquivo de elementos -------- #
    for arquivo, linhas in conteudo_por_arquivo.items():
        caminho = os.path.join(pasta_destino, arquivo)
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas) + "\n")

    # -------- 5) Escreve o BusCoords.dss usando o layout automático -------- #
    posicoes = calcular_posicoes(rede)
    caminho_coords = os.path.join(pasta_destino, "buscoords.dss")
    with open(caminho_coords, "w", encoding="utf-8") as f:
        for nome in rede.barras:
            x, y = posicoes.get(nome, (0, 0))
            f.write(f"{nome} {x} {y}\n")

    # -------- 6) Monta o Master.dss -------- #
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