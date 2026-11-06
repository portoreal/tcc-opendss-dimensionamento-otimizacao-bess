"""
Sistema BESS composto: Inversor (InvControl) + Armazenamento (Storage)
+ Banco de Capacitores (opcional, automático) + Reator (opcional, automático).

TRANSPARÊNCIA TÉCNICA (ler antes de usar em projeto real):

1) CONFIRMADO por documentação oficial colada pelo usuário nesta sessão:
   - Sintaxe do InvControl: Mode, CombiMode, DERList, vvc_curve1, voltwatt_curve,
     VoltWattCH_Curve, RefReactivePower (fonte: doc EPRI/dss-extensions.org).
   - Sintaxe do Reactor: phases, bus1, bus2, kv, kvar, conn, R, X, etc.
     (fonte: opendss.epri.com/Reactor.html).

2) CONFIRMADO nesta revisão, ao analisar o código real do projeto:
   - Formato de "campos" para pedir_valores(): tupla de 4 posições
     (chave, rótulo, tipo_campo, valor_padrão_ou_opções) — corrigido nesta
     versão (a v1 deste arquivo usava um formato errado de 3 posições).
   - Assinatura real de pedir_valores(): chamada POSICIONAL
     (parent, titulo, campos, valores_iniciais=None, dica=None) —
     corrigido nesta versão (a v1 usava keyword args titulo=/campos=).

3) NÃO CONFIRMADO nesta sessão (valores de referência, ajustar conforme projeto):
   - CURVA_VOLTVAR_PADRAO_PONTOS e CURVA_VOLTWATT_PADRAO_PONTOS são pontos
     TÍPICOS de literatura (aproximação de IEEE 1547-2018 Categoria B).
     Devem ser revisados/ajustados conforme PRODIST Módulo 8 e norma da
     distribuidora antes de qualquer uso em projeto real.

4) NÃO CONFIRMADO (assumido a partir do resumo da conversa, não do código
   literal, pois reativo_analise.py não foi colado nesta sessão):
   - Assinatura de analisar_necessidade_reativo(caminho_master, bess_list,
     fp_minimo, kv_conexao_padrao, fases) e formato do dict de retorno
     ("tipo", "kvar", "memoria", "kv", "fases"). Se divergir, ajustar os
     pontos marcados com # ADAPTAR.
"""

import os
from dataclasses import dataclass
from typing import Optional

from .reativo_analise import analisar_necessidade_reativo
from .modelo_rede import gerar_nome_unico
from .dialogos import pedir_valores
from .ui_win11 import confirmar_win11, mostrar_aviso_win11


# ---------------------------------------------------------------------------
# Curvas padrão do InvControl (ver aviso de transparência no topo do arquivo)
# ---------------------------------------------------------------------------

MODOS_INVCONTROL = [
    "VOLTVAR",
    "VOLTWATT",
    "VV_VW (Volt-Var + Volt-Watt)",
    "VV_DRC (Volt-Var + Dynamic Reactive Current)",
]

CURVA_VOLTVAR_PADRAO_NOME = "vvcurve_padrao"
# Curva Volt-Var: pares (tensão em pu, potência reativa em pu da potência
# nominal). Entre 0,5 e 0,92 pu o inversor entrega reativo capacitivo pleno
# (+1,0) para levantar a tensão; de 0,98 a 1,02 pu fica em zero — é a faixa
# morta que evita atuação a cada variação de carga; acima de 1,08 pu absorve
# reativo indutivo (-1,0) para derrubar a tensão. Os pontos em 0,5 e 1,5 pu
# existem para que a curva cubra qualquer tensão encontrada em simulação.
CURVA_VOLTVAR_PADRAO_PONTOS = [
    (0.5, 1.0),
    (0.92, 1.0),
    (0.98, 0.0),
    (1.02, 0.0),
    (1.08, -1.0),
    (1.5, -1.0),
]

CURVA_VOLTWATT_PADRAO_NOME = "vwcurve_padrao"
# Curva Volt-Watt: acima de 1,06 pu o inversor começa a cortar potência
# ativa, chegando a zero em 1,10 pu. É a proteção contra sobretensão por
# injeção excessiva — o inversor deixa de gerar antes que a rede suba mais.
CURVA_VOLTWATT_PADRAO_PONTOS = [
    (0.5, 1.0),
    (1.06, 1.0),
    (1.10, 0.0),
    (1.5, 0.0),
]

# Formato confirmado: (chave, rótulo, tipo_campo, valor_padrão_ou_opções).
# A chave é o que o formulário devolve no dicionário de valores — não é
# texto de tela. O padrão 50 kVA / 50 kW / 100 kWh corresponde a 2 h de
# autonomia na potência nominal.
CAMPOS_SISTEMA_BESS_BASICO = [
    ("nome", "Nome do Sistema BESS", "texto", ""),
    ("kva_inversor", "kVA do Inversor", "texto", "50"),
    ("kwrated_bateria", "kW nominal da Bateria", "texto", "50"),
    ("kwhrated_bateria", "kWh nominal da Bateria", "texto", "100"),
    ("modo_invcontrol", "Modo do Inversor (InvControl)", "combobox", MODOS_INVCONTROL),
]


@dataclass
class ConfiguracaoSistemaBess:
    # Reúne o que o usuário respondeu no formulário e o que foi concluído
    # pela análise de reativo, para que montar_elementos_sistema_bess()
    # não precise voltar à interface.
    nome: str
    bus1: str
    parametros_storage: dict
    modo_invcontrol: str = "VOLTVAR"
    incluir_compensacao_reativa: bool = False
    # None quando a compensação não foi pedida, não pôde ser calculada ou
    # concluiu que não há necessidade.
    resultado_reativo: Optional[dict] = None


# ---------------------------------------------------------------------------
# Perguntas ao usuário
# ---------------------------------------------------------------------------

def perguntar_deseja_compensacao_reativa(parent) -> bool:
    """Pergunta se o usuário quer a análise automática de Capacitor/Reator.

    A pergunta é explícita — e não um padrão silencioso — porque a análise
    roda o fluxo de potência do circuito inteiro, o que leva tempo num
    Master.dss grande, e porque inserir um Capacitor não solicitado mudaria
    o resultado do estudo sem o usuário saber.
    """
    return confirmar_win11(
        "Compensação de Reativo",
        "Deseja que o sistema calcule AUTOMATICAMENTE se este Sistema BESS "
        "precisa de Banco de Capacitores (fator de potência indutivo) ou "
        "Reator (fator de potência capacitivo)?\n\n"
        "O cálculo usa a potência total do circuito (TotalPower) e a lógica "
        "já existente em reativo_analise.py.\n\n"
        "Se responder Não, o Sistema BESS será criado apenas com "
        "Inversor + Armazenamento.",
        parent=parent,
    )


# ---------------------------------------------------------------------------
# Cálculo automático de reativo
# ---------------------------------------------------------------------------

def calcular_compensacao_automatica(
    caminho_master,
    parametros_storage,
    fp_minimo=0.92,
    kv_conexao=13.8,
    fases=3,
):
    """
    Decide entre Capacitor e Reactor usando analisar_necessidade_reativo,
    que já existe no projeto.

    O limite de 0,92 segue o PRODIST Módulo 8, que admite fator de potência
    entre 0,92 indutivo e 0,92 capacitivo no ponto de conexão. O resultado
    ainda não é aplicado: a função só devolve a recomendação, e a decisão
    de incluir ou não o equipamento fica com o usuário.

    # ADAPTAR se a assinatura/retorno real de analisar_necessidade_reativo
    # divergir do documentado no resumo da conversa (dict esperado: "tipo",
    # "kvar", "memoria", "kv", "fases").
    """
    bess_list = [parametros_storage]
    # A análise enxerga o BESS como uma carga a mais no circuito; por isso
    # recebe o storage como lista de um elemento só.
    resultado = analisar_necessidade_reativo(
        caminho_master=caminho_master,
        bess_list=bess_list,
        fp_minimo=fp_minimo,
        kv_conexao_padrao=kv_conexao,
        fases=fases,
    )
    return resultado


# ---------------------------------------------------------------------------
# Montagem dos elementos internos do Sistema BESS
# ---------------------------------------------------------------------------

def _construir_pontos_xycurve(nome, pontos):
    # Converte a lista de pares (x, y) no formato que o exportador .dss
    # espera para XYCurve: três arrays paralelos de mesmo tamanho. Manter
    # npts explícito é exigência do OpenDSS, que não infere o tamanho.
    return {
        "nome": nome,
        "npts": len(pontos),
        "xarray": [p[0] for p in pontos],
        "yarray": [p[1] for p in pontos],
    }


def montar_elementos_sistema_bess(config: ConfiguracaoSistemaBess, nomes_existentes: set):
    """
    Monta os elementos internos do Sistema BESS composto:
      - Storage (sempre)
      - InvControl (sempre, referenciando o Storage via DERList)
      - Capacitor (opcional, se recomendado automaticamente)
      - Reactor (opcional, se recomendado automaticamente)
      - Curvas XY auxiliares do InvControl

    Todos os elementos recebem o campo "grupo" = nome do Sistema BESS.
    """
    # Cada nome passa por gerar_nome_unico e é registrado em
    # nomes_existentes na sequência: o conjunto cresce à medida que os
    # elementos são criados, então o sufixo de desambiguação já considera
    # os irmãos deste mesmo sistema.
    nome_sistema = gerar_nome_unico(config.nome, nomes_existentes)
    nomes_existentes.add(nome_sistema)

    nome_storage = gerar_nome_unico(f"{nome_sistema}_bat", nomes_existentes)
    nomes_existentes.add(nome_storage)

    nome_invcontrol = gerar_nome_unico(f"{nome_sistema}_inv", nomes_existentes)
    nomes_existentes.add(nome_invcontrol)

    storage = {
        "tipo": "Storage",
        "nome": nome_storage,
        "bus1": config.bus1,
        "parametros": dict(config.parametros_storage),
        "grupo": nome_sistema,
    }

    curvas_xy = []
    parametros_inv = {"DERList": f"[Storage.{nome_storage}]"}

    # O combobox devolve o texto completo ("VV_VW (Volt-Var + Volt-Watt)");
    # só o primeiro token interessa como parâmetro do OpenDSS.
    modo = config.modo_invcontrol.split(" ")[0]

    if modo == "VOLTVAR":
        parametros_inv["Mode"] = "VOLTVAR"
        parametros_inv["vvc_curve1"] = CURVA_VOLTVAR_PADRAO_NOME
        curvas_xy.append(_construir_pontos_xycurve(CURVA_VOLTVAR_PADRAO_NOME, CURVA_VOLTVAR_PADRAO_PONTOS))
    elif modo == "VOLTWATT":
        parametros_inv["Mode"] = "VOLTWATT"
        parametros_inv["voltwatt_curve"] = CURVA_VOLTWATT_PADRAO_NOME
        curvas_xy.append(_construir_pontos_xycurve(CURVA_VOLTWATT_PADRAO_NOME, CURVA_VOLTWATT_PADRAO_PONTOS))
    elif modo == "VV_VW":
        parametros_inv["CombiMode"] = "VV_VW"
        parametros_inv["vvc_curve1"] = CURVA_VOLTVAR_PADRAO_NOME
        parametros_inv["voltwatt_curve"] = CURVA_VOLTWATT_PADRAO_NOME
        curvas_xy.append(_construir_pontos_xycurve(CURVA_VOLTVAR_PADRAO_NOME, CURVA_VOLTVAR_PADRAO_PONTOS))
        curvas_xy.append(_construir_pontos_xycurve(CURVA_VOLTWATT_PADRAO_NOME, CURVA_VOLTWATT_PADRAO_PONTOS))
    elif modo == "VV_DRC":
        parametros_inv["CombiMode"] = "VV_DRC"
        parametros_inv["vvc_curve1"] = CURVA_VOLTVAR_PADRAO_NOME
        curvas_xy.append(_construir_pontos_xycurve(CURVA_VOLTVAR_PADRAO_NOME, CURVA_VOLTVAR_PADRAO_PONTOS))

    invcontrol = {
        "tipo": "InvControl",
        "nome": nome_invcontrol,
        # InvControl não é equipamento de rede: não se conecta a barra
        # nenhuma. Ele apenas aponta para o Storage (DERList) e diz como o
        # inversor deve reagir a tensão.
        "bus1": None,
        "parametros": parametros_inv,
        "grupo": nome_sistema,
    }

    capacitor = None
    reactor = None
    if config.incluir_compensacao_reativa and config.resultado_reativo:
        r = config.resultado_reativo
        if r.get("tipo") == "Capacitor":
            nome_cap = gerar_nome_unico(f"{nome_sistema}_cap", nomes_existentes)
            nomes_existentes.add(nome_cap)
            capacitor = {
                "tipo": "Capacitor",
                "nome": nome_cap,
                "bus1": config.bus1,
                "parametros": {
                    "kvar": r.get("kvar"),
                    # kv e phases vêm do resultado da análise; os defaults
                    # (13.8 kV, trifásico) cobrem o caso em que a análise
                    # não os informou, em vez de gravar None no .dss.
                    "kv": r.get("kv", 13.8),
                    "phases": r.get("fases", 3),
                },
                "grupo": nome_sistema,
            }
        elif r.get("tipo") == "Reactor":
            nome_rea = gerar_nome_unico(f"{nome_sistema}_rea", nomes_existentes)
            nomes_existentes.add(nome_rea)
            reactor = {
                "tipo": "Reactor",
                "nome": nome_rea,
                "bus1": config.bus1,
                "parametros": {
                    "kvar": r.get("kvar"),
                    "kv": r.get("kv", 13.8),
                    "phases": r.get("fases", 3),
                },
                "grupo": nome_sistema,
            }

    return {
        "grupo": nome_sistema,
        "storage": storage,
        "invcontrol": invcontrol,
        "capacitor": capacitor,
        "reactor": reactor,
        "curvas_xy": curvas_xy,
    }


# ---------------------------------------------------------------------------
# Formulário de criação (ponto de entrada a partir do Editor de Rede)
# ---------------------------------------------------------------------------

def abrir_formulario_sistema_bess(parent, caminho_master, nomes_existentes, bus1, valores_iniciais=None):
    """
    Fluxo completo:
      1) Pede nome + parâmetros básicos do Storage + modo do InvControl.
      2) Pergunta se o usuário quer compensação de reativo automática.
      3) Se sim (e houver um Master.dss válido), calcula via reativo_analise
         e mostra o resultado.
      4) Monta os elementos internos do Sistema BESS.

    Retorna o dict de montar_elementos_sistema_bess() ou None se cancelado.
    """
    valores = pedir_valores(
        parent,
        "Sistema BESS (Inversor + Armazenamento)",
        CAMPOS_SISTEMA_BESS_BASICO,
        valores_iniciais,
        dica="As curvas Volt-Var/Volt-Watt padrão (referência) serão geradas automaticamente.",
    )
    if valores is None:
        return None

    nome_solicitado = valores.get("nome", "").strip()
    if not nome_solicitado:
        mostrar_aviso_win11(
            "Erro",
            "Informe um nome para o Sistema BESS.",
            parent=parent,
        )
        return None

    try:
        parametros_storage = {
            "kva": float(valores["kva_inversor"]),
            "kwrated": float(valores["kwrated_bateria"]),
            "kwhrated": float(valores["kwhrated_bateria"]),
            # Estado inicial: 50% de carga (pctstored), ociosidade como
            # modo de despacho e nenhum ciclo de carga/descarga agendado.
            # Quem define a operação do dia é a simulação de 24 h; aqui só
            # se cria o equipamento.
            "pctstored": 50,
            "dispmode": "default",
            "state": "idling",
        }
    # float() estoura em três casos: campo vazio, texto ("50 kW" com
    # unidade) ou chave ausente no dicionário. Os três viram a mesma
    # mensagem, porque para o usuário a correção é a mesma.
    except (ValueError, KeyError):
        mostrar_aviso_win11(
            "Erro",
            "Verifique os valores numéricos de kVA/kW/kWh informados.",
            parent=parent,
        )
        return None

    incluir_reativo = perguntar_deseja_compensacao_reativa(parent)
    resultado_reativo = None

    if incluir_reativo:
        # A análise precisa do circuito já exportado: ela roda o OpenDSS
        # sobre um Master.dss em disco, não monta um caso em memória.
        if not caminho_master or not os.path.exists(caminho_master):
            mostrar_aviso_win11(
                "Compensação de Reativo",
                "Não foi encontrado um arquivo Master.dss exportado para este projeto.\n\n"
                "Para calcular automaticamente a necessidade de Capacitor/Reator, "
                "primeiro exporte a rede atual (Arquivo > Exportar arquivos .dss) "
                "e tente novamente.\n\n"
                "O Sistema BESS será criado apenas com Inversor + Armazenamento.",
                parent=parent,
            )
            incluir_reativo = False
        else:
            try:
                resultado_reativo = calcular_compensacao_automatica(caminho_master, parametros_storage)
            # Falha na análise não impede criar o BESS: o usuário recebe o
            # aviso e o sistema segue apenas com Inversor + Armazenamento.
            except Exception as e:
                mostrar_aviso_win11(
                    "Compensação de Reativo",
                    f"Não foi possível calcular a compensação de reativo automaticamente:\n{e}\n\n"
                    "O Sistema BESS será criado apenas com Inversor + Armazenamento.",
                    parent=parent,
                )
                resultado_reativo = None
                incluir_reativo = False

    if incluir_reativo:
        if resultado_reativo and resultado_reativo.get("tipo"):
            mostrar_aviso_win11(
                "Compensação de Reativo — Resultado",
                f"Elemento recomendado: {resultado_reativo['tipo']}\n"
                f"Potência: {resultado_reativo.get('kvar')} kvar\n\n"
                f"{resultado_reativo.get('memoria', '')}",
                parent=parent,
            )
        else:
            # "Sem tipo" significa fator de potência dentro do limite. Não
            # é erro, e sim o resultado possível da análise — por isso a
            # mensagem descreve a conclusão em vez de acusar falha.
            mostrar_aviso_win11(
                "Compensação de Reativo — Resultado",
                "O sistema calculou que NÃO há necessidade de compensação "
                "de reativo (fator de potência dentro do limite aceitável). "
                "O Sistema BESS será criado sem Capacitor/Reator.",
                parent=parent,
            )
            incluir_reativo = False

    config = ConfiguracaoSistemaBess(
        nome=nome_solicitado,
        bus1=bus1,
        parametros_storage=parametros_storage,
        modo_invcontrol=valores["modo_invcontrol"],
        incluir_compensacao_reativa=incluir_reativo,
        resultado_reativo=resultado_reativo,
    )

    return montar_elementos_sistema_bess(config, nomes_existentes)