__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Motor de análise de economia de energia (arbitragem tarifária) para
Sistemas de Armazenamento de Energia (BESS), em horário de ponta e fora
de ponta.

HISTÓRICO DE DEPURAÇÃO COMPLETO (registrado por transparência):
    1) dispmode incorreto -> corrigido para external.
    2) Propriedade Python 'kW' inexistente no binding -> contornado via
       texto.
    3) Sinal do 'kW' incoerente -> tentativa de definir manualmente
       (positivo/negativo) causou comportamento ainda incoerente.
    4) 'model=7' identificado como VALOR INVÁLIDO para Storage (a doc
       oficial da linguagem .dss, colada pelo usuário, lista apenas
       Model=1/2/3) - corrigido para Model=1 (potência constante), com
       '%Charge=100'/'%Discharge=100' definidos explicitamente.
    5) Controle de despacho simplificado para alternar APENAS o 'State'
       (IDLING/CHARGING/DISCHARGING via texto), sem nunca escrever 'kW'
       manualmente - replicando EXATAMENTE o padrão do exemplo oficial
       colado pelo usuário (que nunca atribui kW, apenas lê).
    6) Após os itens 4 e 5, o SoC passou a responder corretamente, mas a
       classificação import/export ainda usava uma CONVENÇÃO DE SINAL
       FIXA e ASSUMIDA para Circuit.TotalPower[0] (ex.: '-total[0]'),
       que se mostrou INCORRETA para este circuito específico: o
       usuário reportou que o caso BASE (só carga, sem BESS, que
       SABIDAMENTE deve estar sempre "comprando" da rede) aparecia como
       "0.00 kWh comprados" em todas as 24 horas - prova definitiva de
       que a convenção de sinal assumida estava invertida para este
       ambiente/versão específica do motor.

    CORREÇÃO FINAL (ESTA VERSÃO): eliminada QUALQUER suposição fixa
    sobre a convenção de sinal de TotalPower. Em vez disso, o sinal de
    referência que representa "comprando da rede" é DEDUZIDO
    EMPIRICAMENTE a partir de um MICRO-CIRCUITO DE IMPORTAÇÃO
    CONHECIDA (ver _calibrar_sinal_importacao). Qualquer leitura, em
    qualquer cenário, cujo sinal COINCIDA com essa referência é
    classificada como "comprada"; sinal OPOSTO é classificado como
    "exportada". Este método é robusto independentemente de qual seja a
    convenção interna exata usada pela versão do motor/binding
    instalado.

    CORREÇÃO DE BUG (sinal de importação - ver D2 abaixo):
        DEFEITO: a versão anterior deduzia o sinal de referência a
        partir da MÉDIA DOS SINAIS DAS 24 HORAS DO CASO BASE,
        assumindo que o caso base SÓ IMPORTA. Essa premissa é FALSA
        quando o circuito possui geração distribuída. Caso real medido
        (projetos/teste): PVSystem de 100 kW SEM curva diária (gera a
        plena potência inclusive à meia-noite) contra 60 kW de carga
        -> o caso base EXPORTA nas 24 horas do dia -> a média dos
        sinais apontou a referência INVERTIDA -> 47 de 48 candidatos
        de BESS resultaram com economia NEGATIVA sem sentido físico
        (o modelo via exportação onde havia importação).

        CAUSA RAIZ: a convenção de sinal de Circuit.TotalPower[0] é
        uma propriedade da INSTÂNCIA do motor (binding/versão), NÃO do
        circuito analisado. Deduzi-la a partir do circuito em estudo
        acopla a calibração ao conteúdo do caso base (geração, curvas),
        que é justamente a variável que se quer medir.

        CORREÇÃO: _calibrar_sinal_importacao() monta, por texto, um
        micro-circuito com carga puramente resistiva (importação
        conhecida, sem nenhuma geração) no MESMO motor/instância e lê
        TotalPower[0]; o sinal desse valor é a convenção de importação.
        A calibração passa a ser IMUNE à geração presente no caso base.

TRANSPARÊNCIA TÉCNICA (atualizada):
    - CONFIRMADO (doc oficial da linguagem .dss, colada pelo usuário):
        - Model válido para Storage: 1, 2 ou 3 (NÃO 7).
        - '%Charge'/'%Discharge': percentual de kWRated usado para
          carga/descarga.
        - 'State': IDLING | CHARGING | DISCHARGING (string via texto).
        - O exemplo oficial de controle de despacho NUNCA escreve 'kW'
          manualmente.
    - CONFIRMADO (doc oficial da API COM): Storages.puSOC (double,
      read/write) - usado para leitura.
    - NÃO CONFIRMADO E NÃO MAIS NECESSÁRIO CONFIRMAR: a convenção exata
      de sinal de Circuit.TotalPower[0] - eliminada como fonte de
      incerteza através do método de sinal de referência (calibrado
      num micro-circuito de importação conhecida), tornando o
      resultado correto independentemente dessa convenção.
    - Novo alerta de HONESTIDADE DO DADO: quando o caso base exporta
      mais horas do que importa, o campo
      'alerta_caso_base_exportacao' é True. A arbitragem tarifária
      pressupõe energia importada na ponta para deslocar; com exportação
      predominante o modelo não monetiza a exportação e a economia
      resultante tende a ser nula/negativa por característica do DADO
      (geração sem curva), não por erro de cálculo.
    - Simulação de "dia representativo" único (não diferencia dia útil
      de fim de semana).
"""

import math
from typing import List, Dict, Any, Optional, Callable

from dss import dss as dss_global

from .estudo_afundamento import MotorReutilizavel
from .estudo_afundamento import VMINPU_STORAGE_PADRAO
from .tarifas_energia import TarifaEnergia


def _eh_hora_ponta(hora: int, inicio_ponta: int, fim_ponta: int) -> bool:
    """Verifica se 'hora' (0-23) está dentro do intervalo de ponta,
    suportando intervalos que cruzam a meia-noite (ex.: 23 às 5h)."""
    if inicio_ponta <= fim_ponta:
        return inicio_ponta <= hora < fim_ponta
    return hora >= inicio_ponta or hora < fim_ponta


def _definir_estado_storage(motor: MotorReutilizavel, nome: str, estado: str):
    """Define APENAS o 'State' (IDLING/CHARGING/DISCHARGING) do elemento
    Storage, via comando de texto do parser .dss - exatamente como no
    exemplo oficial de controle de despacho (que nunca escreve 'kW'
    manualmente). A magnitude do despacho é determinada pelas
    propriedades '%Charge'/'%Discharge' (definidas como 100% na criação
    do elemento, ver _inserir_bess_idling)."""
    estado_texto = estado.upper()
    motor.dssText.Command = f"Edit Storage.{nome} State={estado_texto}"


def _normalizar_soc(valor: float) -> float:
    """Normaliza o SoC lido para a faixa 0-1, independente de a API
    retornar em escala 0-1 ou 0-100."""
    if valor is None:
        return 0.5
    if valor > 1.5:
        return valor / 100.0
    return valor


def _ler_soc(motor: MotorReutilizavel, nome: str) -> float:
    try:
        motor.dssCircuit.Storages.Name = nome
        return _normalizar_soc(motor.dssCircuit.Storages.puSOC)
    except Exception:
        return 0.5


def _ler_potencia_bruta_fonte_kw(motor: MotorReutilizavel) -> float:
    """Retorna o valor BRUTO SINALIZADO (sem nenhuma suposição de
    convenção!) da potência ativa (kW) reportada por
    Circuit.TotalPower[0]. A interpretação do sinal (importar/exportar)
    é feita posteriormente por comparação com um sinal de referência
    obtido do caso base - ver nota de correção no topo do arquivo."""
    total = motor.dssCircuit.TotalPower
    return total[0]


def _calibrar_sinal_importacao() -> float:
    """Determina EMPIRICAMENTE o sinal de Circuit.TotalPower[0] que
    representa IMPORTAÇÃO de energia, retornando +1.0 ou -1.0.

    POR QUE UM MICRO-CIRCUITO PRÓPRIO (e não o caso base): a convenção
    de sinal de TotalPower é uma propriedade da INSTÂNCIA do motor
    (binding/versão), não do circuito estudado. Deduzi-la a partir do
    caso base acopla a calibração ao conteúdo do cenário (geração
    distribuída, curvas de carga) - foi exatamente o que produziu o bug
    D2 documentado no topo do arquivo, em que um PVSystem de 100 kW sem
    curva fazia o caso base exportar 24h/dia e a referência ficava
    INVERTIDA.

    O micro-circuito montado aqui tem carga puramente resistiva e
    NENHUMA fonte de geração: o fluxo da fonte só pode ser importação.
    O sinal lido, portanto, é a convenção de importação com certeza
    física, independente do circuito que se pretende analisar.

    Roda no mesmo contexto do motor (dss_global.NewContext() com
    fallback para o contexto global), replicando o padrão de
    MotorReutilizavel.__init__, e libera o contexto ao final.
    """
    try:
        dssObj = dss_global.NewContext()
    except AttributeError:
        dssObj = dss_global

    try:
        dssText = dssObj.Text
        # Um comando por atribuição (padrão do projeto). 'loadshape' não
        # é usada: carga constante e sem geração deixa o fluxo
        # inequivocamente importado.
        dssText.Command = "clear"
        dssText.Command = "new circuit.calibracao basekv=13.8 pu=1.0 phases=3"
        dssText.Command = "new linecode.pad nphases=3 r1=0.3 x1=0.6 units=km"
        # ATENÇÃO: 'New Circuit' cria o Vsource na barra 'sourcebus'
        # (NÃO 'source'/'b1'). Linha ancorada em barra inexistente deixa
        # o circuito MORTO (TotalPower ~ 4e-11, tensões 0) - medido
        # nesta implementação. Por isso a carga é conectada diretamente
        # ao 'sourcebus', sem linha intermediária.
        dssText.Command = (
            "new load.c bus1=sourcebus phases=3 kv=13.8 kw=100 pf=1.0 model=1")
        dssText.Command = "set voltagebases=[13.8]"
        dssText.Command = "calcvoltagebases"
        dssText.Command = "solve"

        dssCircuit = dssObj.ActiveCircuit
        total0 = dssCircuit.TotalPower[0]
    finally:
        try:
            dssObj.ClearAll()
        except Exception:
            pass
        dssObj = None

    if total0 == 0:
        # Sem fluxo não há sinal a calibrar; convenção positiva é o
        # fallback histórico (era o usado antes da auto-calibração).
        return 1.0
    return math.copysign(1.0, total0)


def _inserir_bess_idling(motor: MotorReutilizavel, bess_list: List[Dict[str, Any]],
                          soc_inicial: float) -> List[str]:
    """Insere os elementos Storage no circuito (todos iniciando em
    repouso). Model=1 (válido; 'model=7' era um valor INVÁLIDO para
    Storage, conforme doc oficial). '%Charge=100'/'%Discharge=100'
    garantem despacho na potência nominal cheia."""
    nomes = []
    for i, bess in enumerate(bess_list):
        try:
            motor.dssCircuit.SetActiveBus(bess["bus"])
            kv_ln = motor.dssCircuit.ActiveBus.kVBase
            kv_linha = kv_ln * math.sqrt(3)
        except Exception:
            kv_linha = 0.38

        nome = f"BESS_ECON_{i}"
        motor.dssText.Command = (
            f"New Storage.{nome} bus1={bess['bus']} phases=3 "
            f"kv={kv_linha:.4f} kwrated={bess['kw']} kwhrated={bess['kwh']} "
            f"kva={bess['kw']} %stored={soc_inicial * 100:.1f} "
            f"%charge=100 %discharge=100 "
            f"state=idling dispmode=external model=1 "
            f"Vminpu={VMINPU_STORAGE_PADRAO}"
        )
        nomes.append(nome)
    return nomes


def _simular_dia(motor: MotorReutilizavel, caminho_master: str,
                  bess_list: List[Dict[str, Any]], controlar: bool,
                  horario_ponta_inicio: int, horario_ponta_fim: int,
                  soc_min: float, soc_max: float,
                  soc_inicial: float) -> List[Dict[str, Any]]:
    """Executa a simulação de 24 horas e retorna o perfil horário com a
    potência BRUTA (sinal cru, sem interpretação) da fonte, além do
    estado e SoC de cada BESS a cada hora."""
    motor.recompilar(caminho_master)

    nomes_bess = []
    if controlar and bess_list:
        nomes_bess = _inserir_bess_idling(motor, bess_list, soc_inicial)
        motor.dssSolution.Solve()

    motor.dssText.Command = "Set Mode=Daily"
    motor.dssText.Command = "Set Stepsize=1h"
    motor.dssText.Command = "Set Number=1"

    perfil = []
    for hora in range(24):
        ponta = _eh_hora_ponta(hora, horario_ponta_inicio, horario_ponta_fim)

        estados_aplicados = {}
        if controlar and nomes_bess:
            for i, nome in enumerate(nomes_bess):
                soc_atual = _ler_soc(motor, nome)

                if ponta and soc_atual > soc_min:
                    novo_estado = "discharging"
                elif (not ponta) and soc_atual < soc_max:
                    novo_estado = "charging"
                else:
                    novo_estado = "idling"

                _definir_estado_storage(motor, nome, novo_estado)
                estados_aplicados[nome] = {"estado": novo_estado, "soc_antes": soc_atual}

        motor.dssSolution.Solve()

        soc_depois = {
            nome: _ler_soc(motor, nome) for nome in nomes_bess
        } if nomes_bess else {}

        perfil.append({
            "hora": hora,
            "ponta": ponta,
            "kw_fonte_bruto": _ler_potencia_bruta_fonte_kw(motor),
            "estados_aplicados": estados_aplicados,
            "soc_depois": soc_depois,
        })

    return perfil


def _classificar_fluxo(kw_bruto: float, sinal_importacao: float):
    """Classifica uma leitura de potência da fonte em 'comprada' ou
    'exportada', comparando o sinal com o sinal que representa
    IMPORTAÇÃO, obtido por calibração num micro-circuito de importação
    conhecida (_calibrar_sinal_importacao). A origem da referência
    mudou, a regra não: mesmo sinal da referência => COMPRA.

    Mesmo sinal da referência => COMPRA (magnitude cheia).
    Sinal oposto => EXPORTAÇÃO (não monetizada por este modelo
    simplificado - ver nota de transparência no topo do arquivo)."""
    if sinal_importacao == 0:
        sinal_importacao = 1.0  # fallback arbitrário, evita comparação com zero

    if kw_bruto * sinal_importacao >= 0:
        return abs(kw_bruto), 0.0
    else:
        return 0.0, abs(kw_bruto)


def _processar_perfil(perfil_bruto: List[Dict[str, Any]], sinal_importacao: float):
    for p in perfil_bruto:
        comprada, exportada = _classificar_fluxo(p["kw_fonte_bruto"], sinal_importacao)
        p["kw_comprada"] = comprada
        p["kw_exportada"] = exportada
    return perfil_bruto


def _integrar_energia(perfil: List[Dict[str, Any]]):
    energia_ponta = sum(p["kw_comprada"] for p in perfil if p["ponta"])
    energia_fora_ponta = sum(p["kw_comprada"] for p in perfil if not p["ponta"])
    exportada_ponta = sum(p["kw_exportada"] for p in perfil if p["ponta"])
    exportada_fora_ponta = sum(p["kw_exportada"] for p in perfil if not p["ponta"])
    return energia_ponta, energia_fora_ponta, exportada_ponta, exportada_fora_ponta


def analisar_economia_energia(
    caminho_master: str,
    bess_list: List[Dict[str, Any]],
    tarifa: TarifaEnergia,
    horario_ponta_inicio: int = 18,
    horario_ponta_fim: int = 21,
    soc_min: float = 0.2,
    soc_max: float = 0.95,
    soc_inicial: float = 0.5,
    dias_equivalentes_mes: float = 22,
    custo_bess_brl: Optional[float] = None,
    callback_status: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Executa a análise completa de economia de energia (arbitragem
    tarifária ponta/fora ponta) para uma configuração de BESS."""

    def _status(msg):
        if callback_status:
            callback_status(msg)

    motor = MotorReutilizavel()
    try:
        _status("Economia de energia: simulando dia representativo SEM BESS...")
        perfil_base = _simular_dia(
            motor, caminho_master, bess_list, controlar=False,
            horario_ponta_inicio=horario_ponta_inicio,
            horario_ponta_fim=horario_ponta_fim,
            soc_min=soc_min, soc_max=soc_max, soc_inicial=soc_inicial)

        _status("Economia de energia: simulando dia representativo COM BESS...")
        perfil_bess = _simular_dia(
            motor, caminho_master, bess_list, controlar=True,
            horario_ponta_inicio=horario_ponta_inicio,
            horario_ponta_fim=horario_ponta_fim,
            soc_min=soc_min, soc_max=soc_max, soc_inicial=soc_inicial)
    finally:
        motor.finalizar()

    # Sinal de IMPORTAÇÃO: calibrado num micro-circuito de importação
    # conhecida, na MESMA instância do motor (a convenção de sinal é
    # propriedade da instância, não do circuito). NÃO é mais deduzido do
    # caso base: essa dedução assumia "caso base só importa", premissa
    # FALSA quando há geração distribuída (bug D2 - ver topo do arquivo).
    sinal_importacao = _calibrar_sinal_importacao()

    perfil_base = _processar_perfil(perfil_base, sinal_importacao)
    perfil_bess = _processar_perfil(perfil_bess, sinal_importacao)

    # Diagnóstico do DADO (não do cálculo): arbitragem pressupõe energia
    # importada na ponta para deslocar. Circunstância em que o caso base
    # exporta a maior parte do dia (ex.: PV sem curva) deve ser exposta
    # ao usuário, não mascarada por um número de economia.
    horas_importacao_base = sum(
        1 for p in perfil_base if p["kw_comprada"] > 0)
    horas_exportacao_base = sum(
        1 for p in perfil_base if p["kw_exportada"] > 0)
    alerta_caso_base_exportacao = horas_exportacao_base > horas_importacao_base

    (energia_ponta_base, energia_fora_base,
     export_ponta_base, export_fora_base) = _integrar_energia(perfil_base)
    (energia_ponta_bess, energia_fora_bess,
     export_ponta_bess, export_fora_bess) = _integrar_energia(perfil_bess)

    custo_diario_base = (
        energia_ponta_base * tarifa.tarifa_ponta_kwh
        + energia_fora_base * tarifa.tarifa_fora_ponta_kwh)
    custo_diario_bess = (
        energia_ponta_bess * tarifa.tarifa_ponta_kwh
        + energia_fora_bess * tarifa.tarifa_fora_ponta_kwh)

    economia_diaria = custo_diario_base - custo_diario_bess
    economia_mensal = economia_diaria * dias_equivalentes_mes
    economia_anual = economia_mensal * 12

    payback_anos = None
    if custo_bess_brl and economia_anual > 0:
        payback_anos = custo_bess_brl / economia_anual

    demanda_ponta_base = max(
        (p["kw_comprada"] for p in perfil_base if p["ponta"]), default=0.0)
    demanda_ponta_bess = max(
        (p["kw_comprada"] for p in perfil_bess if p["ponta"]), default=0.0)
    reducao_demanda_ponta_kw = max(demanda_ponta_base - demanda_ponta_bess, 0.0)
    economia_demanda_mensal_estimada = reducao_demanda_ponta_kw * tarifa.demanda_ponta_kw

    total_exportado_kwh_bess = export_ponta_bess + export_fora_bess
    alerta_superdimensionamento = total_exportado_kwh_bess > 0

    return {
        "tarifa": tarifa,
        "horario_ponta_inicio": horario_ponta_inicio,
        "horario_ponta_fim": horario_ponta_fim,
        "dias_equivalentes_mes": dias_equivalentes_mes,
        "perfil_base": perfil_base,
        "perfil_bess": perfil_bess,
        # float()/bool() explícito em TODOS os campos de energia/perda: o
        # motor (numpy-backed) devolve np.float64/np.bool_, que quebram
        # json.dumps() e comparações fora deste módulo.
        "energia_ponta_kwh_base": float(energia_ponta_base),
        "energia_fora_ponta_kwh_base": float(energia_fora_base),
        "energia_ponta_kwh_bess": float(energia_ponta_bess),
        "energia_fora_ponta_kwh_bess": float(energia_fora_bess),
        "exportada_ponta_kwh_bess": float(export_ponta_bess),
        "exportada_fora_ponta_kwh_bess": float(export_fora_bess),
        "total_exportado_kwh_bess": float(total_exportado_kwh_bess),
        "alerta_superdimensionamento": bool(alerta_superdimensionamento),
        "horas_importacao_base": int(horas_importacao_base),
        "horas_exportacao_base": int(horas_exportacao_base),
        "alerta_caso_base_exportacao": bool(alerta_caso_base_exportacao),
        # float() explícito: o motor (numpy-backed) devolve np.float64,
        # que vaza para serialização/comparações fora deste módulo.
        "custo_diario_base": float(custo_diario_base),
        "custo_diario_bess": float(custo_diario_bess),
        "economia_diaria": float(economia_diaria),
        "economia_mensal": float(economia_mensal),
        "economia_anual": float(economia_anual),
        "custo_bess_brl": custo_bess_brl,
        "payback_anos": None if payback_anos is None else float(payback_anos),
        "demanda_ponta_kw_base": float(demanda_ponta_base),
        "demanda_ponta_kw_bess": float(demanda_ponta_bess),
        "reducao_demanda_ponta_kw": float(reducao_demanda_ponta_kw),
        "economia_demanda_mensal_estimada": float(economia_demanda_mensal_estimada),
    }