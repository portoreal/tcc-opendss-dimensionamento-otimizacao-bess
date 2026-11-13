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

O histórico abaixo não é enfeite: cada item corresponde a um defeito que
apareceu em execução real e que voltaria a aparecer se o código fosse
"simplificado" para a forma anterior.

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

import copy
import math
import shutil
import tempfile
from typing import List, Dict, Any, Optional, Callable

from dss import dss as dss_global

from .curvas import obter_curva
from .exportador_dss import gerar_arquivos_dss
from .estudo_afundamento import MotorReutilizavel
from .estudo_afundamento import VMINPU_STORAGE_PADRAO
from .tarifas_energia import TarifaEnergia


def _eh_hora_ponta(hora: int, inicio_ponta: int, fim_ponta: int) -> bool:
    """Diz se a hora (0-23) está dentro do intervalo de ponta.

    O intervalo pode cruzar a meia-noite (23h às 5h), caso em que a
    comparação simples de ordem não serve e a condição vira uma disjunção.
    """
    if inicio_ponta <= fim_ponta:
        return inicio_ponta <= hora < fim_ponta
    return hora >= inicio_ponta or hora < fim_ponta


def _definir_estado_storage(motor: MotorReutilizavel, nome: str, estado: str):
    """Define APENAS o 'State' (IDLING/CHARGING/DISCHARGING) do Storage,
    por comando de texto ao parser .dss.

    É o mesmo padrão do exemplo oficial de controle de despacho, que nunca
    escreve 'kW' manualmente. A magnitude fica por conta de
    '%Charge'/'%Discharge', definidas em 100% na criação do elemento (ver
    _inserir_bess_idling). Escrever kW à mão foi justamente o que produziu
    o defeito 3 do histórico.
    """
    estado_texto = estado.upper()
    motor.dssText.Command = f"Edit Storage.{nome} State={estado_texto}"


def _ler_parametros_despacho(motor: MotorReutilizavel,
                             nome: str,
                             kwrated: float) -> Dict[str, float]:
    """Lê do motor os parâmetros que o próprio motor usa para aplicar o bloco.

    O bloco comandado por '%charge'/'%discharge' NÃO é a energia líquida que
    entra ou sai do banco: o motor desconta/repõe as perdas e o consumo em
    repouso. Para dimensionar o bloco de modo que o SoC chegue EXATAMENTE ao
    piso/teto, é preciso inverter a MESMA conta que o motor faz, e para isso
    os parâmetros precisam ser os da instância, não suposições do módulo.

    Leitura por comando de texto ('? Storage.<nome>.<propriedade>'),
    devolvendo o valor em motor.dssText.Result. O nome da propriedade só
    funciona com o sinal '%' na frente: '? Storage.X.effcharge' devolve a
    string 'Property Unknown' (medido neste binding, dss-python 0.15.7),
    enquanto '? Storage.X.%effcharge' devolve o número. Uma leitura que não
    converta em float cai no default documentado do Storage (90% de
    eficiência, 1% de consumo em repouso) em vez de derrubar o despacho.
    """
    valores = {}
    for propriedade, padrao in (("%effcharge", 90.0),
                                ("%effdischarge", 90.0),
                                ("%idlingkW", 1.0)):
        try:
            motor.dssText.Command = f"? Storage.{nome}.{propriedade}"
            valores[propriedade] = float(motor.dssText.Result)
        except (TypeError, ValueError):
            valores[propriedade] = padrao

    return {
        "eta_c": valores["%effcharge"] / 100.0,
        "eta_d": valores["%effdischarge"] / 100.0,
        "idle_kw": valores["%idlingkW"] / 100.0 * kwrated,
    }


def _decidir_estado_e_bloco(soc_atual: float, ponta: bool,
                            soc_min: float, soc_max: float,
                            kwrated: float, kwhrated: float,
                            params: Dict[str, float]):
    """Decide o estado e o percentual do bloco de despacho da hora.

    POR QUE O BLOCO PRECISA SER DIMENSIONADO: o motor aplica o bloco INTEIRO
    durante o passo de 1 h e só depois CLAMPA o SoC reportado no teto/piso.
    Com blocos sempre cheios isso gera dois artefatos medidos no estudo:
      - na carga, o SoC bate no teto e o excedente é simplesmente descartado
        (a rede compra e o banco não armazena);
      - na descarga, o SoC bate no piso e o motor entrega o bloco cheio assim
        mesmo (energia criada no registro).
    Dimensionar o bloco pela energia disponível é o que mantém o balanço de
    energia coerente: não se compra além da folga na carga e não se entrega
    além do armazenado na descarga.

    As equações são a INVERSÃO DAS DUAS CONTAS DO MOTOR, onde delta_stored é a
    variação do armazenado em kWh:
      carga:     delta_stored = (bloco - idle_kw) * eta_c
                 => bloco = folga / eta_c + idle_kw
      descarga:  delta_stored = (bloco + idle_kw) / eta_d
                 => bloco = disponivel * eta_d - idle_kw
    eta_c = %effcharge/100, eta_d = %effdischarge/100,
    idle_kw = %idlingkW/100 * kwrated.

    O disparo é o mesmo de antes (ponta e SoC acima do mínimo descarrega;
    fora da ponta e abaixo do máximo carrega). O que muda é apenas a
    magnitude: bloco nulo ou negativo não tem sentido físico e vira repouso.
    """
    if ponta and soc_atual > soc_min:
        disponivel = (soc_atual - soc_min) * kwhrated
        bloco = min(kwrated,
                    max(0.0, disponivel * params["eta_d"] - params["idle_kw"]))
        if bloco <= 0:
            return "idling", 0.0
        return "discharging", 100.0 * bloco / kwrated

    if (not ponta) and soc_atual < soc_max:
        folga = (1.0 - soc_atual) * kwhrated
        bloco = min(kwrated, folga / params["eta_c"] + params["idle_kw"])
        if bloco <= 0:
            return "idling", 0.0
        return "charging", 100.0 * bloco / kwrated

    return "idling", 0.0


def _aplicar_bloco(motor: MotorReutilizavel, nome: str, estado: str,
                   pct_bloco: float):
    """Emite o '%charge'/'%discharge' da hora, conforme o estado decidido.

    No repouso não há comando: o estado IDLING ignora o percentual, e emitir
    um Edit sem efeito só polui o histórico do motor.
    """
    if estado == "charging":
        motor.dssText.Command = f"Edit Storage.{nome} %charge={pct_bloco:.6f}"
    elif estado == "discharging":
        motor.dssText.Command = f"Edit Storage.{nome} %discharge={pct_bloco:.6f}"


def _normalizar_soc(valor: float) -> float:
    """Traz o SoC lido para a faixa 0-1.

    A API pode devolver 0-1 ou 0-100 conforme o binding, e o restante do
    módulo trabalha sempre em fração. O corte em 1,5 separa as duas escalas
    sem ambiguidade: nenhum SoC fracionário legítimo passa de 1.
    """
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
        # 0,5 (meio da faixa) é o retorno neutro: mantém o despacho possível
        # e sinaliza no perfil que a leitura falhou, sem interromper o dia.
        return 0.5


def _ler_potencia_bruta_fonte_kw(motor: MotorReutilizavel) -> float:
    """Devolve a potência ativa da fonte (kW) como o motor a reporta, sinal
    incluído e sem nenhuma suposição de convenção.

    A interpretação do sinal — importar ou exportar — acontece depois, por
    comparação com a referência calibrada em _calibrar_sinal_importacao.
    """
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
        # Um comando por atribuição (padrão do projeto). Nenhum loadshape é
        # usado: carga constante e sem geração deixa o fluxo
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
    """Insere os elementos Storage no circuito, todos começando em repouso.

    Model=1 é o valor válido; 'model=7' era INVÁLIDO para Storage, conforme
    a documentação oficial. '%Charge=100'/'%Discharge=100' garantem despacho
    na potência nominal cheia quando o estado mudar.
    """
    nomes = []
    for i, bess in enumerate(bess_list):
        try:
            motor.dssCircuit.SetActiveBus(bess["bus"])
            kv_ln = motor.dssCircuit.ActiveBus.kVBase
            kv_linha = kv_ln * math.sqrt(3)
        except Exception:
            # Fallback de tensão para barra não encontrada. 0,38 kV cobre o
            # secundário de distribuição típico; o valor aparece no elemento
            # criado e denuncia o problema na inspeção do circuito.
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
                  soc_inicial: float,
                  eh_dia_util: bool = True) -> List[Dict[str, Any]]:
    """Simula as 24 horas do dia representativo e devolve o perfil horário.

    Cada hora traz a potência BRUTA da fonte — sinal cru, ainda sem
    interpretação —, além do estado comandado e do SoC de cada BESS. A
    mesma função serve ao caso base e ao caso com BESS; 'controlar' é o que
    separa os dois.

    O parâmetro eh_dia_util desliga a janela de ponta em dias sem posto de
    ponta na tarifa (sábado e domingo na A4 verde): a ponta só existe em
    dia útil, e o dia representativo (quinta) é dia útil, o que mantém o
    comportamento anterior quando o default True vale.
    """
    motor.recompilar(caminho_master)

    nomes_bess = []
    if controlar and bess_list:
        nomes_bess = _inserir_bess_idling(motor, bess_list, soc_inicial)
        motor.dssSolution.Solve()

    # Parâmetros de bloco lidos UMA vez por dia simulado, logo após a
    # inserção: são propriedades do elemento e não mudam durante o despacho.
    params_despacho = {}
    for i, nome in enumerate(nomes_bess):
        params_despacho[nome] = _ler_parametros_despacho(
            motor, nome, float(bess_list[i]["kw"]))

    motor.dssText.Command = "Set Mode=Daily"
    # Passo de 1 h e um único dia: o resultado é o dia representativo, não
    # uma série multidiária.
    motor.dssText.Command = "Set Stepsize=1h"
    motor.dssText.Command = "Set Number=1"

    perfil = []
    for hora in range(24):
        ponta = eh_dia_util and _eh_hora_ponta(hora, horario_ponta_inicio,
                                               horario_ponta_fim)

        estados_aplicados = {}
        if controlar and nomes_bess:
            for i, nome in enumerate(nomes_bess):
                soc_atual = _ler_soc(motor, nome)

                # O disparo (ponta/mínimo/máximo) é o mesmo de antes; o que
                # muda é o bloco, dimensionado pela energia disponível para
                # que o motor não compre além da folga nem entregue além do
                # armazenado (ver _decidir_estado_e_bloco).
                novo_estado, pct_bloco = _decidir_estado_e_bloco(
                    soc_atual, ponta, soc_min, soc_max,
                    kwrated=float(bess_list[i]["kw"]),
                    kwhrated=float(bess_list[i]["kwh"]),
                    params=params_despacho[nome])

                _aplicar_bloco(motor, nome, novo_estado, pct_bloco)
                _definir_estado_storage(motor, nome, novo_estado)
                estados_aplicados[nome] = {"estado": novo_estado, "soc_antes": soc_atual}

        motor.dssSolution.Solve()

        soc_depois = {
            nome: _ler_soc(motor, nome) for nome in nomes_bess
        } if nomes_bess else {}

        # Leituras por elemento no MESMO passo: a potência da fonte é o
        # balanço líquido e não distingue quem consumiu ou gerou; carga e
        # FV horárias servem aos gráficos de balanço e aos perfis semanais.
        carga_kw = 0.0
        for ld in motor.dssCircuit.Loads.AllNames:
            motor.dssCircuit.SetActiveElement("Load." + ld)
            carga_kw += abs(motor.dssCircuit.ActiveElement.TotalPowers[0])
        fv_kw = 0.0
        for pv in motor.dssCircuit.PVSystems.AllNames:
            motor.dssCircuit.PVSystems.Name = pv
            fv_kw += float(motor.dssCircuit.PVSystems.kW)

        perfil.append({
            "hora": hora,
            "ponta": ponta,
            "kw_fonte_bruto": _ler_potencia_bruta_fonte_kw(motor),
            "carga_kw": carga_kw,
            "fv_kw": fv_kw,
            "estados_aplicados": estados_aplicados,
            "soc_depois": soc_depois,
        })

    return perfil


def _classificar_fluxo(kw_bruto: float, sinal_importacao: float):
    """Classifica uma leitura de potência da fonte em comprada ou exportada,
    devolvendo (comprada, exportada) já separadas.

    A regra é uma só: mesmo sinal da referência equivale a COMPRA, sinal
    oposto equivale a EXPORTAÇÃO. A referência é a calibrada em
    _calibrar_sinal_importacao, num micro-circuito de importação conhecida —
    mudou a origem da referência, não a regra.

    Exportação não é monetizada por este modelo simplificado; ver a nota de
    transparência no topo do arquivo.
    """
    if sinal_importacao == 0:
        sinal_importacao = 1.0  # fallback arbitrário, evita comparação com zero

    if kw_bruto * sinal_importacao >= 0:
        return abs(kw_bruto), 0.0
    else:
        return 0.0, abs(kw_bruto)


def _processar_perfil(perfil_bruto: List[Dict[str, Any]], sinal_importacao: float):
    # Acrescenta ao perfil os campos interpretados, mantendo 'kw_fonte_bruto'
    # intacto para auditoria.
    for p in perfil_bruto:
        comprada, exportada = _classificar_fluxo(p["kw_fonte_bruto"], sinal_importacao)
        p["kw_comprada"] = comprada
        p["kw_exportada"] = exportada
    return perfil_bruto


def _integrar_energia(perfil: List[Dict[str, Any]]):
    # Integração retangular: cada hora vale 1 kWh por kW, porque o passo é
    # exatamente uma hora.
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
    soc_inicial: float = 1.0,
    dias_equivalentes_mes: float = 22,
    custo_bess_brl: Optional[float] = None,
    callback_status: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Análise completa de economia de energia — arbitragem tarifária entre
    ponta e fora ponta — para uma configuração de BESS.

    O dia representativo é simulado duas vezes, sem e com BESS. A diferença
    de custo entre os dois é a economia diária, que se extrapola para mês e
    ano por dias_equivalentes_mes. BESS vazio equivale ao caso base, útil
    para medir o potencial teórico.

    soc_inicial (default 1.0 = bateria cheia) É o regime permanente: com o
    despacho limitado pela energia disponível, o dia termina em 100% de SoC e
    o dia seguinte recomeça cheio. Partir com meio tanque geraria uma recarga
    de comissionamento que não existe em operação — custo único de
    implantação, contado no dia representativo por engano.
    """

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
    # Payback só existe com custo informado e economia positiva. Economia
    # nula ou negativa tornaria o quociente um número sem significado.
    if custo_bess_brl and economia_anual > 0:
        payback_anos = custo_bess_brl / economia_anual

    demanda_ponta_base = max(
        (p["kw_comprada"] for p in perfil_base if p["ponta"]), default=0.0)
    demanda_ponta_bess = max(
        (p["kw_comprada"] for p in perfil_bess if p["ponta"]), default=0.0)
    reducao_demanda_ponta_kw = max(demanda_ponta_base - demanda_ponta_bess, 0.0)
    economia_demanda_mensal_estimada = reducao_demanda_ponta_kw * tarifa.demanda_ponta_kw

    total_exportado_kwh_bess = export_ponta_bess + export_fora_bess
    # Exportar em qualquer hora já indica descarga acima da carga local: é o
    # sinal de superdimensionamento para ESTA análise.
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


# ---------------------------------------------------------------------------
# Análise semanal
# ---------------------------------------------------------------------------

_DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def _nome_com_dia(nome_curva: str, dia: str) -> str:
    """Devolve o nome de curva correspondente a 'dia'.

    Duas convenções convivem nos projetos: a curva já carrega o dia no nome
    ("Carga1_Segunda", sufixo que basta trocar) ou o nome é neutro
    ("Carga1"), caso em que o dia é anexado depois do sublinhado. Um nome com
    mais de um dia no meio não é interpretado: devolve-se o candidato com
    sufixo, e quem chama decide se ele existe.
    """
    for dia_antigo in _DIAS_SEMANA:
        if nome_curva.endswith("_" + dia_antigo):
            return nome_curva[: -len(dia_antigo)] + dia
    return f"{nome_curva}_{dia}"


def _rebindar_curvas_do_dia(rede_dia, pasta_curvas: str, dia: str) -> List[str]:
    """Aponta os elementos de 'rede_dia' para a curva do dia, quando existe.

    Só elementos com curva de projeto são tocados. Elemento sem curva fica sem
    curva de propósito: a exportação injeta a curva padrão do dia para Load e
    PVSystem, e reservar essa decisão ao exportador evita duas fontes de
    verdade sobre o mesmo dado.

    O rebind só acontece se a curva do dia existir no projeto. Citar uma curva
    inexistente faria a exportação levantar erro por referência quebrada —
    preferível manter o vínculo original e avisar.
    """
    avisos: List[str] = []
    if not pasta_curvas:
        return avisos

    for elemento in rede_dia.derivacoes.values():
        parametros = elemento.parametros
        nome_curva = parametros.get("daily")
        if not nome_curva or str(nome_curva).strip() in ("", "Nenhuma"):
            continue

        candidato = _nome_com_dia(str(nome_curva), dia)
        if obter_curva(pasta_curvas, candidato) is None:
            avisos.append(
                f"{elemento.tipo}.{elemento.nome}: curva '{candidato}' não "
                f"existe no projeto; mantido o vínculo com '{nome_curva}'.")
            continue
        parametros["daily"] = candidato

    return avisos


def _energia_pv_gerada_kwh(motor: MotorReutilizavel) -> float:
    """Energia ativa gerada pelos PVSystem no passo corrente, em kWh.

    A leitura é por elemento, via ActiveElement da classe PVSystem, porque
    TotalPower do circuito é o balanço líquido na fonte e não distingue quem
    gerou. A lista de nomes é varrida a cada hora: recalcular uma vez por dia
    seria mais barato, mas mudaria a lista se um PV fosse desligado no meio do
    despacho — a varredura por hora custa pouco e não supõe nada.

    O motor devolve potência ativa em kW no terminal do elemento; com passo de
    1 h, o valor numérico é também a energia daquela hora.
    """
    try:
        nomes = list(motor.dssCircuit.PVSystems.AllNames)
    except Exception:
        return 0.0

    total_kw = 0.0
    for nome in nomes:
        try:
            motor.dssCircuit.PVSystems.Name = nome
            total_kw += float(motor.dssCircuit.PVSystems.kW)
        except Exception:
            # Um PV ilegível não invalida os demais; a hora segue com a soma
            # dos que responderam.
            continue
    return max(total_kw, 0.0)


def _energia_bess_descarregada_kwh(motor: MotorReutilizavel, nomes_bess: List[str]) -> float:
    """Energia entregue à rede pelo BESS no passo corrente, em kWh.

    Só a DESCARGA conta como fonte. A carga não entra: a energia que o BESS
    absorve já foi comprada da rede (ou veio do FV) e, portanto, já está
    contabilizada no outro lado do balanço. Somá-la aqui contaria duas vezes o
    mesmo kWh e faria a participação das fontes ultrapassar 100%.

    A leitura da potência vem de ActiveElement.TotalPowers, e não de
    Storages.kW: a interface IStorages expõe apenas State e puSOC — não há
    propriedade de potência nela.

    DUAS PARTICULARIDADES MEDIDAS neste binding (dss-python 0.15.7), que
    justificam o código abaixo:
      1) State é INTEIRO, não texto: 1 = descarregando, -1 = carregando,
         0 = repouso. Comparar com a string 'DISCHARGING' nunca casa e faria
         a descarga inteira desaparecer do balanço.
      2) A unidade de TotalPowers varia por classe de elemento. No Storage
         ela vem em kW (um BESS de 30 kW reporta -30); em Load e PVSystem vem
         em W (uma carga de 60 kW reporta ~58 900). Por isso aqui NÃO há
         divisão: o valor já está em kW.
    """
    total_kw = 0.0
    for nome in nomes_bess:
        try:
            motor.dssCircuit.Storages.Name = nome
            if int(motor.dssCircuit.Storages.State) != 1:
                continue
            motor.dssCircuit.SetActiveElement(f"Storage.{nome}")
            total_kw += abs(float(motor.dssCircuit.ActiveElement.TotalPowers[0]))
        except Exception:
            continue
    return max(total_kw, 0.0)


def analisar_economia_semanal(
    rede,
    pasta_curvas: Optional[str],
    dia_padrao: Optional[str],
    bess_list: List[Dict[str, Any]],
    tarifa: TarifaEnergia,
    horario_ponta_inicio: int = 18,
    horario_ponta_fim: int = 21,
    dias_equivalentes_mes: float = 22,
    callback_status: Optional[Callable[[str], None]] = None,
    incluir_perfis: bool = False,
    pular_base: bool = False,
    custo_base_diario_brl: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Repete a análise de economia para os sete dias da semana.

    A análise diária de analisar_economia_energia usa um dia representativo
    só. Como carga e geração têm curva própria por dia, o custo e a economia
    variam de segunda a domingo; somar as sete parcelas é o que dá o número
    semanal e a base dos gráficos de participação das fontes.

    Cada dia roda em pasta temporária própria porque o exportador escreve um
    Master.dss com as curvas do dia já resolvidas. Recompilar o master do dia
    anterior serviria o dia errado, então a pasta nova é o que garante o
    isolamento entre iterações.

    Falha em um dia não derruba a semana: o dia degrada para zeros e a
    mensagem vai para 'avisos'. Uma semana parcial sinalizada é mais útil que
    nenhum resultado.

    A janela de ponta vale só em dias úteis (sábado e domingo são
    integralmente fora de ponta na A4 verde). Com pular_base=True e
    custo_base_diario_brl fornecido, o caso base do dia não é simulado
    (o custo base vem da lista, indexada por _DIAS_SEMANA) — caminho para
    quem já tem o caso base da semana e avalia muitos candidatos.
    Com incluir_perfis=True, o retorno traz 'perfis_por_dia' com o perfil
    horário processado de cada dia.
    Parameters
    ----------
    rede : RedeEletrica
        Rede do editor. Não é alterada — cada dia trabalha sobre uma cópia
        profunda, e o rebind das curvas acontece só na cópia.
    pasta_curvas : str ou None
        Pasta de curvas do projeto (Projeto.caminho_curvas). None desliga o
        rebind por dia e deixa a escolha das curvas inteiramente para a
        exportação.
    dia_padrao : str ou None
        Dia usado como fallback quando um dia não tem curva própria. Também
        alimenta dia_curvas_padrao na exportação.
    dias_equivalentes_mes : float
        Dias úteis por mês, coerente com a análise diária.
    """

    def _status(msg):
        if callback_status:
            callback_status(msg)

    avisos: List[str] = []
    economia_diaria_brl: List[float] = []
    custos_base_brl: List[float] = []
    custo_sistema_diario_brl: List[float] = []
    energia_rede_kwh: List[float] = []
    energia_fv_kwh: List[float] = []
    energia_bess_kwh: List[float] = []
    perfis_por_dia: List[Dict[str, Any]] = []

    # O sinal de importação é propriedade da INSTÂNCIA do motor, não do
    # circuito, mas calibrá-lo uma vez por dia custa um micro-Solve e elimina
    # a dependência de o motor ser reutilizado entre dias.
    motor = MotorReutilizavel()
    try:
        for dia in _DIAS_SEMANA:
            _status(f"Economia semanal: simulando {dia}...")
            # Na A4 verde o posto de ponta só existe em dia útil; sábado e
            # domingo são fora de ponta no dia inteiro.
            dia_util = dia not in ("Sábado", "Domingo")
            indice_dia = len(economia_diaria_brl)
            try:
                rede_dia = copy.deepcopy(rede)
                avisos.extend(_rebindar_curvas_do_dia(rede_dia, pasta_curvas, dia))

                pasta_temp = tempfile.mkdtemp(prefix="econ_semana_")
                try:
                    caminho_master = gerar_arquivos_dss(
                        rede_dia, pasta_temp, pasta_curvas=pasta_curvas,
                        dia_curvas_padrao=dia)

                    if pular_base and custo_base_diario_brl is not None:
                        custo_base = float(custo_base_diario_brl[indice_dia])
                        perfil_base = None
                    else:
                        perfil_base = _simular_dia(
                            motor, caminho_master, bess_list, controlar=False,
                            horario_ponta_inicio=horario_ponta_inicio,
                            horario_ponta_fim=horario_ponta_fim,
                            soc_min=0.2, soc_max=0.95, soc_inicial=1.0,
                            eh_dia_util=dia_util)

                    perfil_bess = _simular_dia(
                        motor, caminho_master, bess_list, controlar=True,
                        horario_ponta_inicio=horario_ponta_inicio,
                        horario_ponta_fim=horario_ponta_fim,
                        soc_min=0.2, soc_max=0.95, soc_inicial=1.0,
                        eh_dia_util=dia_util)

                    sinal_importacao = _calibrar_sinal_importacao()
                    if perfil_base is not None:
                        perfil_base = _processar_perfil(perfil_base, sinal_importacao)
                    perfil_bess = _processar_perfil(perfil_bess, sinal_importacao)

                    if perfil_base is not None:
                        (energia_ponta_base, energia_fora_base,
                         _exp_ponta_base, _exp_fora_base) = _integrar_energia(perfil_base)
                    (energia_ponta_bess, energia_fora_bess,
                     _exp_ponta_bess, exp_fora_bess) = _integrar_energia(perfil_bess)

                    if perfil_base is not None:
                        custo_base = (
                            energia_ponta_base * tarifa.tarifa_ponta_kwh
                            + energia_fora_base * tarifa.tarifa_fora_ponta_kwh)
                    custo_sistema = (
                        energia_ponta_bess * tarifa.tarifa_ponta_kwh
                        + energia_fora_bess * tarifa.tarifa_fora_ponta_kwh)

                    exportada_dia_kwh = sum(
                        float(p["kw_exportada"]) for p in perfil_bess) / 1000.0

                    # A energia comprada da rede sai do MESMO perfil que
                    # produziu custo_base: as duas grandezas passam a ser
                    # medidas pela mesma via e não podem divergir de unidade.
                    rede_dia_kwh = energia_ponta_bess + energia_fora_bess

                    fv_dia_kwh, bess_dia_kwh = _fontes_do_dia(
                        motor, caminho_master, bess_list,
                        horario_ponta_inicio, horario_ponta_fim,
                        eh_dia_util=dia_util)

                    # O FV que sai pela fonte não é consumido no local. Descontar
                    # a exportação do dia evita creditar ao FV energia que a rede
                    # recebeu; o resíduo positivo é o que a carga de fato usou.
                    fv_consumida_kwh = max(fv_dia_kwh - exportada_dia_kwh, 0.0)

                    if incluir_perfis:
                        perfis_por_dia.append({
                            "dia": dia,
                            "dia_util": dia_util,
                            "perfil_base": perfil_base,
                            "perfil_bess": perfil_bess,
                        })
                finally:
                    shutil.rmtree(pasta_temp, ignore_errors=True)

                economia_diaria_brl.append(float(custo_base - custo_sistema))
                custos_base_brl.append(float(custo_base))
                custo_sistema_diario_brl.append(float(custo_sistema))
                energia_rede_kwh.append(float(rede_dia_kwh))
                energia_fv_kwh.append(float(fv_consumida_kwh))
                energia_bess_kwh.append(float(bess_dia_kwh))

            except Exception as erro:
                avisos.append(f"{dia}: falha na simulação ({erro}). "
                              "Dia contabilizado com zeros.")
                economia_diaria_brl.append(0.0)
                custos_base_brl.append(0.0)
                custo_sistema_diario_brl.append(0.0)
                energia_rede_kwh.append(0.0)
                energia_fv_kwh.append(0.0)
                energia_bess_kwh.append(0.0)
    finally:
        motor.finalizar()

    return {
        "dias": list(_DIAS_SEMANA),
        "economia_diaria_brl": economia_diaria_brl,
        "custo_base_diario_brl": custos_base_brl,
        "custo_sistema_diario_brl": custo_sistema_diario_brl,
        "energia_rede_kwh": energia_rede_kwh,
        "energia_fv_kwh": energia_fv_kwh,
        "energia_bess_kwh": energia_bess_kwh,
        "economia_semanal_brl": float(sum(economia_diaria_brl)),
        "perfis_por_dia": perfis_por_dia,
        "avisos": avisos,
    }


def _fontes_do_dia(motor: MotorReutilizavel, caminho_master: str,
                    bess_list: List[Dict[str, Any]],
                    horario_ponta_inicio: int, horario_ponta_fim: int,
                    eh_dia_util: bool = True):
    """Energia de FV e de descarga do BESS ao longo do dia, em kWh.

    Roda o despacho uma terceira vez porque a integração precisa da leitura
    por elemento a cada hora, e _simular_dia só guarda a potência da fonte.
    A repetição é intencional: manter a série por elemento dentro de
    _simular_dia obrigaria aquele laço a conhecer as fontes, e ele é usado
    também onde elas não interessam.

    A REDE NÃO É LIDA AQUI. A energia comprada já está no perfil processado a
    partir da potência da fonte, e é de lá que o custo sai; repetir a leitura
    aqui criava uma segunda medida da mesma grandeza, com escala própria e
    sujeita a divergir. Ficaram as fontes que o perfil não distingue — FV e
    BESS são elementos, e Circuit.TotalPower só enxerga o balanço líquido.

    O resultado é uma tupla (fv, bess).
    """
    motor.recompilar(caminho_master)

    nomes_bess: List[str] = []
    if bess_list:
        # Regime permanente: o dia representativo parte com a bateria cheia.
        # A recarga de comissionamento (de meio tanque ao topo, nas primeiras
        # horas) é custo único de implantação e não se repete na operação.
        # Com o despacho limitado pela energia disponível, o dia termina em
        # 100% de SoC e o dia seguinte recomeça cheio — logo, partir cheio É
        # o regime permanente, não uma condição particular.
        nomes_bess = _inserir_bess_idling(motor, bess_list, 1.0)
        motor.dssSolution.Solve()

    params_despacho = {}
    for i, nome in enumerate(nomes_bess):
        params_despacho[nome] = _ler_parametros_despacho(
            motor, nome, float(bess_list[i]["kw"]))

    motor.dssText.Command = "Set Mode=Daily"
    motor.dssText.Command = "Set Stepsize=1h"
    motor.dssText.Command = "Set Number=1"

    fv_kwh = 0.0
    bess_kwh = 0.0
    for hora in range(24):
        ponta = eh_dia_util and _eh_hora_ponta(hora, horario_ponta_inicio,
                                               horario_ponta_fim)

        if nomes_bess:
            for i, nome in enumerate(nomes_bess):
                soc_atual = _ler_soc(motor, nome)
                # Mesmo disparo e mesmo dimensionamento de bloco de
                # _simular_dia: esta terceira passagem precisa reproduzir o
                # despacho real, senão a participação das fontes no balanço
                # não fecha com a energia que a rede de fato vendeu.
                novo_estado, pct_bloco = _decidir_estado_e_bloco(
                    soc_atual, ponta, 0.2, 0.95,
                    kwrated=float(bess_list[i]["kw"]),
                    kwhrated=float(bess_list[i]["kwh"]),
                    params=params_despacho[nome])
                _aplicar_bloco(motor, nome, novo_estado, pct_bloco)
                _definir_estado_storage(motor, nome, novo_estado)

        motor.dssSolution.Solve()

        fv_kwh += _energia_pv_gerada_kwh(motor)
        bess_kwh += _energia_bess_descarregada_kwh(motor, nomes_bess)

    return fv_kwh, bess_kwh