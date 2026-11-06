__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Motor da Simulação ao Vivo (QSTS animado multi-dia) — SEM Qt.

Este módulo concentra TODA a lógica que toca o OpenDSS e o estado da
simulação: QSTS horário, despacho do BESS, dias sucessivos, nuvens sobre a
geração fotovoltaica, fatores de carga por dia da semana, economia acumulada
por arbitragem e simulação de afundamento em contexto isolado. Nenhum import
de PySide6 ou matplotlib aqui: o módulo é importável e testável sem tela, e a
janela em ``ao_vivo_ui.py`` é apenas a casca visual.

REUSO DELIBERADO (nada duplicado)
---------------------------------
* Despacho: ``_eh_hora_ponta``, ``_definir_estado_storage``, ``_ler_soc``,
  ``_inserir_bess_idling``, ``_ler_potencia_bruta_fonte_kw`` e
  ``_classificar_fluxo`` são importados de ``economia_energia`` — a regra
  de despacho desta tela é EXATAMENTE a da análise de Economia. Se a regra
  mudar lá, esta tela acompanha (é fidelidade, não escolha).
* Falta: ``_aplicar_falta``, ``_capturar_pu_todas_barras``,
  ``_classificar_sag`` e ``TIPOS_FALTA_DISPONIVEIS`` vêm de
  ``estudo_afundamento``. A spec de barra/fases (``_spec_falta``) é
  reproduzida aqui porque é privada daquele módulo; é uma única linha,
  documentada abaixo.
* Motor: ``MotorReutilizavel`` (``estudo_afundamento``), que já usa um
  contexto isolado do Engine por instância.

TRANSPARÊNCIA TÉCNICA (suposições explícitas — leia antes de confiar)
--------------------------------------------------------------------
1. NUVENS = MODELO METEOROLÓGICO SIMPLIFICADO, NÃO DADO MEDIDO. O índice
   0–100% (100 = céu limpo) escala a IRRADIÂNCIA declarada das PVSystems
   (``Edit PVSystem.x irradiance=<origem × fator>``) — fisicamente, nuvem
   reduz a irradiância. Como o exportador cria PVSystem com
   ``irradiance=1.0`` (``exportador_dss._fmt_pvsystem``), o fator
   relativo é o próprio valor declarado. ``Generator`` usado como fonte é
   escalado proporcionalmente no ``kW``. A "cobertura variável ao longo do
   dia" é uma deriva suave determinística, montada com 5 âncoras
   pseudoaleatórias interpoladas por cosseno e semeadas por dia. O
   resultado é reprodutível, o que permite comparar dois dias; não
   representa medição de nenhuma localidade.
2. FATORES DE CARGA POR DIA DA SEMANA = MODO DE SIMULAÇÃO. O modelo
   (``modelo_rede``) só tem UMA curva diária por elemento; não existe
   "curva de terça" e "curva de quarta". A variação entre dias é obtida
   multiplicando as LoadShapes do circuito por um fator por dia da
   semana (``Edit Loadshape.<curva> mult=(...)``). Default 1,0 = dias
   idênticos. Não são dados medidos.
3. ECONOMIA ACUMULADA = ARBITRAGEM DO BESS, ESCOPO RESTRITO. Contabiliza
   a energia DESPACHADA (potência nominal do despacho × 1 h, sinal pelo
   estado: ``discharging`` = +kW, ``charging`` = −kW) valorada na tarifa
   ponta e fora ponta do catálogo CELESC. NÃO inclui encargo de demanda,
   efeito das perdas, exportação nem degradação. A análise rigorosa
   (caso base × caso com BESS, incluindo demanda) permanece no módulo de
   Economia de Energia — este número é um INDICADOR DE TELA.
   Limitação conhecida: a comparação é feita contra o PREÇO DA ENERGIA
   (R$/kWh), não contra um caso base re-simulado; se a rede exportar
   durante a ponta, a economia calculada superestima o ganho.
4. AFUNDAMENTO EM CONTEXTO ISOLADO. ``Set Mode=Daily`` faz o
   ``Solve()`` AVANÇAR o relógio do QSTS. Aplicar a falta no motor da
   sessão viva, portanto, saltaria uma hora e corromperia o dia em
   curso. Por isso a falta é reproduzida num MOTOR SEPARADO: compila o
   mesmo master, reinsere os BESS com o SoC corrente, refaz os passos do
   dia já executados (nuvens e despacho do histórico), resolve a falta,
   captura as tensões, classifica o sag e descarta o motor. O relógio,
   o SoC e a economia da sessão viva NÃO são tocados.
   Limitação conhecida e registrada no evento: o replay refaz a
   SEQUÊNCIA de despachos do histórico, não reproduz bit a bit o SoC que
   o motor lê (o SoC de cada passo é reimposto por
   ``Edit Storage.x %stored`` antes do despacho), e os reguladores de
   tensão podem estar em posição de tap diferente do passo ao vivo
   (o contexto novo compila do zero). O evento serve para mostrar a
   PROPAGAÇÃO do afundamento, não para substituir o estudo de
   afundamento barra a barra (``estudo_afundamento.rodar_estudo``).
5. TARIFA: valores do catálogo ``tarifas_energia`` (CELESC, RH ANEEL
   3.602/2026, sem tributos) — mesma ressalva de escopo do módulo de
   Economia. Trocar a tarifa no meio da simulação NÃO reescreve o passado:
   o acumulado de cada dia usa a tarifa vigente nos passos executados.

COMO O TEMPO É ORGANIZADO
-------------------------
A sessão executa ``executar_passo(hora)`` para h = 0..23 dentro de um
dia. Quando o chamador pede a hora 24 de um dia, ele deve chamar
``avancar_dia()`` ANTES (ou ``executar_passo`` recusa h > 23). A virada
incrementa o dia, reaplica os fatores de carga do novo dia, zera as
séries do dia corrente e PRESERVA SoC, economia acumulada e log.
"""

import math
import os
import random
from typing import Any, Dict, List, Optional, Sequence

from .dss_engine import DSS
from .economia_energia import (
    _classificar_fluxo,
    _definir_estado_storage,
    _eh_hora_ponta,
    _inserir_bess_idling,
    _ler_potencia_bruta_fonte_kw,
    _ler_soc,
)
from .estudo_afundamento import (
    TIPOS_FALTA_DISPONIVEIS,
    MotorReutilizavel,
    _aplicar_falta,
    _capturar_pu_todas_barras,
    _classificar_sag,
)
from .modelo_rede import RedeEletrica
from .curvas import obter_curva
from .tarifas_energia import CATALOGO_TARIFAS_PADRAO, obter_tarifa

# Valores idênticos aos defaults da análise de Economia de Energia.
HORARIO_PONTA_INICIO = 18
HORARIO_PONTA_FIM = 21
SOC_MIN = 0.2
SOC_MAX = 0.95
SOC_INICIAL = 0.5

HORAS_POR_DIA = 24

DIAS_DA_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta",
                  "Sábado", "Domingo"]

# Semente base da deriva de nuvens: mudar este número muda todas as
# séries diárias geradas. Fixo por projeto: é o que garante que a mesma
# simulação, repetida, desenhe as mesmas nuvens.
SEMENTE_NUVENS = 20261013

TARIFA_PADRAO = "A4_Verde"

# Faixa de amplitude do afundamento (ANEEL/PRODIST, criterio de
# amplitude) — mesmos defaults de ``estudo_afundamento.rodar_estudo``.
SAG_LIMITE_INFERIOR = 0.1
SAG_LIMITE_SUPERIOR = 0.9
# Impedância da falta sólida. O valor antigo (1e-4 ohm) colapsava as barras
# a ~0,005 pu, o que zerava estruturalmente qualquer benefício de mitigação:
# não sobrava tensão para comparar. 0,05 ohm representa uma falta franca com
# arco, na faixa em que a diferença entre mitigar e não mitigar aparece.
# Ver estudo_afundamento.
R_FALTA_SOLIDA = 0.05
R_FALTA_ALTA_IMPEDANCIA = 40.0

# Tipos de falta que o módulo aceita (chaves de TIPOS_FALTA_DISPONIVEIS).
_TIPOS_FALTA_VALIDOS = tuple(TIPOS_FALTA_DISPONIVEIS.keys())


# ============================================================
# Adaptador de leitura (mesma justificativa do projeto)
# ============================================================

class _AdaptadorDSS:
    """Adapta um ``MotorReutilizavel`` à interface de instância de ``DSS``.

    TRANSPARÊNCIA (por que não instanciar ``DSS``): o construtor de ``DSS``
    compila o circuito por conta própria e faz ``sys.exit(1)`` em caso de
    falha. Chamá-lo aqui criaria um segundo contexto e poderia encerrar o
    processo sem mensagem para o usuário. Os métodos de leitura de ``DSS``
    só tocam ``self.dssCircuit``/``self.dssObj``, e é exatamente isso que
    este adaptador expõe — reaproveitando métodos já validados pelos módulos
    de Validação e topologia.
    """

    def __init__(self, motor: MotorReutilizavel):
        self.dssCircuit = motor.dssCircuit
        self.dssObj = motor.dssObj

    # Delegação explícita, sem __getattr__: método ausente falha na hora e
    # com nome, em vez de virar comportamento estranho em tempo de execução.
    obter_tensoes_por_barra = DSS.obter_tensoes_por_barra
    obter_linhas = DSS.obter_linhas
    obter_transformadores = DSS.obter_transformadores
    obter_coordenadas_barras = DSS.obter_coordenadas_barras
    obter_perdas_totais_kw = DSS.obter_perdas_totais_kw


def _tensoes_por_barra_max_fase(motor: MotorReutilizavel) -> Dict[str, float]:
    """Tensão pu por barra = maior valor entre as fases presentes.

    ``DSS.obter_tensoes_por_barra`` devolve {(barra, fase): pu}; o mapa
    colore nós, e um nó precisa de um número só. Toma-se o maior valor
    porque é assim que o operador lê uma barra trifásica equilibrada; o Vmin
    do gráfico continua sendo o mínimo entre fases, que é o pior caso.
    """
    bruto = _AdaptadorDSS(motor).obter_tensoes_por_barra()
    por_barra: Dict[str, float] = {}
    for (barra, _fase), valor in bruto.items():
        atual = por_barra.get(barra)
        if atual is None or valor > atual:
            por_barra[barra] = valor
    return por_barra


def _vmin_vmax_por_fase(motor: MotorReutilizavel):
    """(Vmin, Vmax) do passo corrente, sobre todas as fases.

    Valores nulos ou não positivos são descartados: barra desenergizada
    entraria como 0 pu e puxaria o mínimo para zero, escondendo afundamento
    real nas demais.
    """
    bruto = _AdaptadorDSS(motor).obter_tensoes_por_barra()
    valores = [v for v in bruto.values() if v is not None and v > 0]
    if not valores:
        return None, None
    return min(valores), max(valores)


# ============================================================
# Série de nuvens por dia (deriva suave determinística)
# ============================================================

def _deriva_nuvens_por_dia(dia: int, semente: int = SEMENTE_NUVENS) -> List[float]:
    """Fator de cobertura (0,5–1,0) para cada hora do dia, reprodutível.

    Modelo meteorológico simplificado (TRANSPARÊNCIA item 1): 5 âncoras
    pseudoaleatórias uniformes em [0,5, 1,0] são sorteadas com
    ``random.Random(semente + dia * 7919)`` e interpoladas por cosseno ao longo
    das 24 h. A interpolação cossenoidal gera transições suaves (nuvem
    entrando/saindo), em vez de degraus horários irreais.

    A semente é um inteiro derivado do dia (``semente + dia * 7919``, com
    7919 primo). ``random.seed`` recusa tuplas desde o Python 3.11
    (TypeError: "only supported seed types are None, int, float, str,
    bytes, bytearray"). Com inteiro, a sequência depende do dia: dois dias
    consecutivos têm curvas diferentes e o mesmo dia numa reexecução tem a
    MESMA curva (comparabilidade).
    """
    gerador = random.Random(int(semente) + int(dia) * 7919)
    n_ancoras = 5
    ancoras = [gerador.uniform(0.5, 1.0) for _ in range(n_ancoras)]
    # Âncora extra igual à primeira, para o dia fechar o ciclo sem degrau
    # entre a hora 23 e a hora 0 do dia seguinte.
    ancoras.append(ancoras[0])

    serie: List[float] = []
    passo = HORAS_POR_DIA / n_ancoras
    for hora in range(HORAS_POR_DIA):
        posicao = hora / passo
        i = int(posicao)
        if i >= n_ancoras:
            i = n_ancoras - 1
        fracao = posicao - i
        # Peso cossenoidal: 0 -> 1 -> 0 com derivada nula nas pontas, ou
        # seja, a transição não faz quina na fronteira entre âncoras.
        peso = (1.0 - math.cos(math.pi * fracao)) / 2.0
        serie.append(ancoras[i] * (1.0 - peso) + ancoras[i + 1] * peso)
    return serie


def _rotulo_dia(dia: int) -> str:
    """Rótulo do dia: 'Dia 1 · Segunda' (dia é 0-based)."""
    return f"Dia {dia + 1} · {DIAS_DA_SEMANA[dia % len(DIAS_DA_SEMANA)]}"


# ============================================================
# Sessão de motor: tudo que toca o OpenDSS, fora da thread da UI
# ============================================================

class SessaoAoVivo:
    """Encapsula UM ``MotorReutilizavel`` e expõe a execução passo a passo.

    Uso esperado (sempre dentro de uma mesma thread):
        sessao = SessaoAoVivo(master, bess_list, controlar)
        meta = sessao.preparar()      # recompila, insere BESS, caso base
        dado = sessao.executar_passo(0)
        ...
        sessao.avancar_dia()          # depois da hora 23
        sessao.executar_passo(0)      # dia 2, hora 0
        ...
        sessao.encerrar()

    Não é thread-safe por si mesma. A serialização é de quem usa, e a
    janela usa uma única thread de trabalho.
    """

    def __init__(self, caminho_master: str, bess_list: List[Dict[str, Any]],
                 controlar: bool,
                 horario_ponta_inicio: int = HORARIO_PONTA_INICIO,
                 horario_ponta_fim: int = HORARIO_PONTA_FIM,
                 soc_min: float = SOC_MIN, soc_max: float = SOC_MAX,
                 soc_inicial: float = SOC_INICIAL,
                 chave_tarifa: str = TARIFA_PADRAO,
                 fatores_carga: Optional[Sequence[float]] = None,
                 curva_carga_por_elemento: Optional[Dict[str, str]] = None,
                 semente_nuvens: int = SEMENTE_NUVENS,
                 caminho_rede_json: Optional[str] = None,
                 pasta_curvas: Optional[str] = None):
        self.caminho_master = caminho_master
        self.bess_list = list(bess_list or [])
        self.controlar = bool(controlar) and bool(self.bess_list)
        self.horario_ponta_inicio = horario_ponta_inicio
        self.horario_ponta_fim = horario_ponta_fim
        self.soc_min = soc_min
        self.soc_max = soc_max
        self.soc_inicial = soc_inicial
        self.chave_tarifa = chave_tarifa
        self.semente_nuvens = int(semente_nuvens)
        # Caminhos opcionais, usados só para montar o snapshot de
        # exportação (perfis de carga e nomes das PV).
        self.caminho_rede_json = caminho_rede_json
        self.pasta_curvas = pasta_curvas

        # Fatores de carga por dia da semana (default 1,0 = dias iguais).
        fatores = list(fatores_carga or [1.0] * len(DIAS_DA_SEMANA))
        if len(fatores) != len(DIAS_DA_SEMANA):
            raise ValueError(
                f"fatores_carga precisa de {len(DIAS_DA_SEMANA)} valores "
                f"(um por dia da semana); recebido {len(fatores)}")
        self.fatores_carga = [float(f) for f in fatores]

        # Mapa elemento->curva para reaplicar o fator (vem do rede.json).
        self.curva_carga_por_elemento: Dict[str, str] = dict(
            curva_carga_por_elemento or {})

        # Estado do relógio.
        self.dia_atual = 0
        self.hora_atual = -1
        self.motor: Optional[MotorReutilizavel] = None
        self.nomes_bess: List[str] = []
        self.sinal_referencia: float = 1.0
        self._preparado = False

        # Topologia e geometria não mudam durante o dia: são lidas uma vez
        # em preparar() e reaproveitadas nos 24 passos. Reler a cada passo
        # custaria uma travessia do circuito por hora simulada.
        self.linhas: List[Any] = []
        self.transformadores: List[Any] = []
        self.coordenadas: Dict[str, tuple] = {}
        self.barras_sem_coordenada: List[str] = []

        # Estado de despacho do dia corrente (histórico: hora -> estados).
        self.historico_dia: Dict[int, Dict[str, Any]] = {}

        # Geração fotovoltaica, com o valor ORIGINAL declarado. Guardar o
        # original é o que permite voltar a 100% de céu limpo: sem ele,
        # "100%" significaria o último valor escrito, não o do modelo.
        self.pv_original: Dict[str, float] = {}
        self.gerador_original: Dict[str, float] = {}

        # Nuvens.
        self.indice_nuvens: int = 100          # 100 = céu limpo
        self.cobertura_variavel: bool = False

        # Afundamento: último evento exibido (dict) ou None.
        self.evento_afundamento: Optional[Dict[str, Any]] = None
        self.log_eventos: List[Dict[str, Any]] = []
        # Ledger contínuo de passos: atravessa dias e só o Reiniciar zera.
        # É a fonte dos gráficos e da exportação.
        self.ledger_passos: List[Dict[str, Any]] = []
        self.passo_global = -1
        # Cache dos multiplicadores originais das curvas. Existe para evitar
        # composição entre dias — ver _inventariar_curvas_carga.
        self.pmult_original_por_curva: Dict[str, List[float]] = {}

        # Economia.
        self.economia_dia = 0.0
        self.economia_total = 0.0
        self.energia_despachada_dia = {"carga_kwh": 0.0, "descarga_kwh": 0.0}

    # ---------------------------------------------------------------- #
    # Propriedades de leitura para a UI
    # ---------------------------------------------------------------- #
    @property
    def rotulo_dia(self) -> str:
        return _rotulo_dia(self.dia_atual)

    @property
    def dia_concluido(self) -> bool:
        return self.hora_atual >= HORAS_POR_DIA - 1

    def tarifa(self):
        return obter_tarifa(self.chave_tarifa) or CATALOGO_TARIFAS_PADRAO[TARIFA_PADRAO]

    def definir_tarifa(self, chave: str) -> bool:
        """Troca a tarifa dos próximos passos e devolve True se mudou.

        O passado não é reescrito: o acumulado de cada dia fica com a tarifa
        vigente nos passos já executados (TRANSPARÊNCIA item 5). Chave
        desconhecida devolve False sem alterar nada.
        """
        if chave == self.chave_tarifa:
            return False
        if obter_tarifa(chave) is None:
            return False
        self.chave_tarifa = chave
        self._registrar_evento(
            "tarifa", f"Tarifa alterada para {obter_tarifa(chave).nome}")
        return True

    def definir_fatores_carga(self, fatores: Sequence[float]):
        """Atualiza os fatores por dia da semana, aplicados no próximo dia.

        Vale no próximo dia porque o dia corrente já teve suas curvas
        editadas; reaplicar agora mudaria a carga no meio da simulação.
        """
        if len(fatores) != len(DIAS_DA_SEMANA):
            raise ValueError("fatores_carga precisa de 7 valores")
        self.fatores_carga = [float(f) for f in fatores]

    def definir_nuvens(self, indice: int, cobertura_variavel: Optional[bool] = None):
        """Define o índice de nuvens (0–100, 100 = céu limpo) para os
        próximos passos.

        O passo já resolvido não é refeito. Mudar nuvem depois do solve
        exigiria recompilar para reproduzir o histórico — por isso a
        alteração só vale adiante.
        """
        novo = max(0, min(100, int(indice)))
        mudou = (novo != self.indice_nuvens
                 or (cobertura_variavel is not None
                     and bool(cobertura_variavel) != self.cobertura_variavel))
        self.indice_nuvens = novo
        if cobertura_variavel is not None:
            self.cobertura_variavel = bool(cobertura_variavel)
        if mudou:
            self._registrar_evento(
                "nuvem",
                f"cobertura alterada para {self.indice_nuvens}% "
                f"(variável={self.cobertura_variavel})")

    def _registrar_evento(self, tipo: str, texto: str):
        self.log_eventos.append({
            "tipo": tipo,
            "dia": self.dia_atual,
            "hora": self.hora_atual,
            "texto": texto,
        })

    # ---------------------------------------------------------------- #
    # Preparação
    # ---------------------------------------------------------------- #
    def preparar(self) -> Dict[str, Any]:
        """Recompila, insere os BESS em repouso e roda o caso base.

        O caso base (sem despacho) existe para obter o sinal de referência
        e para ler a topologia.

        O caso base é obrigatório: ``_classificar_fluxo`` precisa saber
        qual sinal significa "comprando" neste circuito, informação que
        só o cenário sem geração e sem armazenamento fornece. Daí a
        sequência: 24 solves de referência antes de qualquer BESS entrar.
        """
        self.motor = MotorReutilizavel()
        self.motor.recompilar(self.caminho_master)

        # --- caso base: 24 passos SEM BESS, para o sinal de referência ---
        self.motor.dssText.Command = "Set Mode=Daily"
        self.motor.dssText.Command = "Set Stepsize=1h"
        self.motor.dssText.Command = "Set Number=1"

        soma_sinais = 0.0
        for _hora in range(HORAS_POR_DIA):
            self.motor.dssSolution.Solve()
            kw_bruto = _ler_potencia_bruta_fonte_kw(self.motor)
            if kw_bruto != 0:
                soma_sinais += math.copysign(1.0, kw_bruto)
        self.sinal_referencia = (
            math.copysign(1.0, soma_sinais) if soma_sinais != 0 else 1.0)

        # --- topologia/geometria (estáticas ao longo do dia) ---
        try:
            self.linhas = list(_AdaptadorDSS(self.motor).obter_linhas())
        except Exception:
            self.linhas = []
        try:
            self.transformadores = list(
                _AdaptadorDSS(self.motor).obter_transformadores())
        except Exception:
            self.transformadores = []
        try:
            self.coordenadas = dict(
                _AdaptadorDSS(self.motor).obter_coordenadas_barras())
        except Exception:
            self.coordenadas = {}

        self._preparado = True
        return self._repreparar_cenario()

    def _repreparar_cenario(self) -> Dict[str, Any]:
        """Recompila e reposiciona o cenário no instante 0 (sem resolver).

        Recompilar é o que garante SoC inicial de volta a ``soc_inicial``:
        o estado do Storage vive no circuito compilado, não em variáveis
        Python. É o mesmo caminho que "Reiniciar" percorre.
        """
        self.motor.recompilar(self.caminho_master)

        self.nomes_bess = []
        if self.controlar:
            self.nomes_bess = _inserir_bess_idling(
                self.motor, self.bess_list, self.soc_inicial)
            self.motor.dssSolution.Solve()

        self.motor.dssText.Command = "Set Mode=Daily"
        self.motor.dssText.Command = "Set Stepsize=1h"
        self.motor.dssText.Command = "Set Number=1"
        self.hora_atual = -1
        self.dia_atual = 0
        self.historico_dia = {}
        self.evento_afundamento = None
        self.log_eventos = []
        self.ledger_passos = []
        self.passo_global = -1
        self.economia_dia = 0.0
        self.economia_total = 0.0
        self.energia_despachada_dia = {"carga_kwh": 0.0, "descarga_kwh": 0.0}

        self._inventariar_geracao()
        self._inventariar_curvas_carga()
        self._aplicar_fatores_carga(self.dia_atual)
        self._aplicar_nuvens(self.dia_atual, self.hora_atual)

        return self._meta()

    def _meta(self) -> Dict[str, Any]:
        return {
            "nomes_bess": list(self.nomes_bess),
            "coordenadas": dict(self.coordenadas),
            "linhas": list(self.linhas),
            "transformadores": list(self.transformadores),
            "barras_sem_coordenada": list(self.barras_sem_coordenada),
            "controlar": self.controlar,
            "dia": self.dia_atual,
            "rotulo_dia": self.rotulo_dia,
            "dias_da_semana": list(DIAS_DA_SEMANA),
            "fatores_carga": list(self.fatores_carga),
            "possui_pv": bool(self.pv_original),
            "possui_gerador_fonte": bool(self.gerador_original),
            "nomes_pv": sorted(self.pv_original),
            "nomes_gerador": sorted(self.gerador_original),
            "curvas_de_carga": sorted(set(self.curva_carga_por_elemento.values())),
            "indice_nuvens": self.indice_nuvens,
            "cobertura_variavel": self.cobertura_variavel,
            "chave_tarifa": self.chave_tarifa,
            "tipos_falta": dict(TIPOS_FALTA_DISPONIVEIS),
        }

    def reiniciar(self) -> Dict[str, Any]:
        """Volta ao instante anterior ao passo 0: recompila no Dia 1."""
        if not self._preparado:
            return self.preparar()
        return self._repreparar_cenario()

    # ---------------------------------------------------------------- #
    # Inventário de geração (PV / Generator) para o índice de nuvens
    # ---------------------------------------------------------------- #
    def _inventariar_geracao(self):
        """Lê os valores originais de irradiância (PVSystem) e kW (Generator).

        Guardar o original é o que permite restaurar o elemento ao valor
        declarado quando o usuário volta a 100% de céu limpo — sem isso,
        100% significaria "último valor escrito", não "valor do modelo".
        """
        self.pv_original = {}
        self.gerador_original = {}
        if self.motor is None:
            return

        # PVSystem: a potência de saída cresce praticamente linear com
        # irradiance, então o fator é multiplicativo sobre o declarado.
        try:
            circuit = self.motor.dssCircuit
            # A API não deixa atribuir First (property sem setter). O
            # idioma correto é LER First: posiciona no primeiro elemento e
            # devolve 0 se não houver nenhum. CORREÇÃO DE BUG: a grafia
            # antiga levantava AttributeError, o except abaixo engolia, e
            # pv_original ficava vazio — nuvem sem efeito nenhum na PV.
            tem_pv = bool(circuit.PVSystems.First)
            while True:
                if not tem_pv:
                    break
                nome = circuit.PVSystems.Name
                if not nome:
                    break
                try:
                    kva = float(circuit.PVSystems.Pmpp or 0)
                except Exception:
                    kva = 0.0
                if kva > 0:
                    # Guarda a irradiância efetiva lida do motor, e não o
                    # default do exportador: se o .dss declarar outro
                    # valor, é esse que precisa ser restaurado.
                    try:
                        irrad = float(circuit.PVSystems.Irradiance)
                    except Exception:
                        irrad = 1.0
                    self.pv_original[nome] = irrad if irrad > 0 else 1.0
                if not circuit.PVSystems.Next:
                    break
        except Exception:
            self.pv_original = {}

        # Generator usado como fonte: escala kW.
        try:
            circuit = self.motor.dssCircuit
            tem_gerador = bool(circuit.Generators.First)
            while True:
                if not tem_gerador:
                    break
                nome = circuit.Generators.Name
                if not nome:
                    break
                try:
                    kw = float(circuit.Generators.kW or 0)
                except Exception:
                    kw = 0.0
                if kw > 0:
                    self.gerador_original[nome] = kw
                if not circuit.Generators.Next:
                    break
        except Exception:
            self.gerador_original = {}

    def _aplicar_nuvens(self, dia: int, hora: int):
        """Aplica o índice de nuvens ao passo seguinte.

        ``hora`` é a hora que será resolvida — a UI chama antes do solve do
        passo, para que a irradiância do passo seja a do passo. Com
        cobertura variável, o fator é multiplicado pela deriva do dia
        naquela hora (TRANSPARÊNCIA item 1).
        """
        if self.motor is None:
            return

        fator = max(0.0, min(1.0, self.indice_nuvens / 100.0))
        if self.cobertura_variavel and 0 <= hora < HORAS_POR_DIA:
            fator *= _deriva_nuvens_por_dia(dia, self.semente_nuvens)[hora]

        for nome, original in self.pv_original.items():
            try:
                self.motor.dssText.Command = (
                    f"Edit PVSystem.{nome} irradiance={original * fator:.6f}")
            except Exception:
                continue
        for nome, original in self.gerador_original.items():
            try:
                self.motor.dssText.Command = (
                    f"Edit Generator.{nome} kW={original * fator:.6f}")
            except Exception:
                continue

    def _inventariar_curvas_carga(self):
        """Cacheia os multiplicadores originais das curvas de carga.

        CORREÇÃO DE BUG (composição entre dias): ``Edit Loadshape mult=``
        substitui o
        vetor; reler o valor compilado no dia seguinte traria o vetor já
        escalado pelo fator do dia anterior. O cache é lido uma única vez,
        imediatamente após a compilação (valor de arquivo).
        """
        self.pmult_original_por_curva = {}
        if self.motor is None:
            return
        for curva in sorted(set(self.curva_carga_por_elemento.values())):
            try:
                self.motor.dssCircuit.LoadShapes.Name = curva
                valores = list(self.motor.dssCircuit.LoadShapes.Pmult)
            except Exception as e:
                self._registrar_evento(
                    "aviso", f"curva '{curva}' não pôde ser lida: {e}")
                continue
            if valores:
                self.pmult_original_por_curva[curva] = valores

    def fator_nuvens_da_hora(self, dia: int, hora: int) -> float:
        """Fator efetivo (0–1) aplicado às PVSystems naquele passo.

        Repete o cálculo de _aplicar_nuvens de propósito, para o ledger
        registrar o fator que foi de fato usado sem precisar guardá-lo
        durante o passo.
        """
        fator = max(0.0, min(1.0, self.indice_nuvens / 100.0))
        if self.cobertura_variavel and 0 <= hora < HORAS_POR_DIA:
            fator *= _deriva_nuvens_por_dia(dia, self.semente_nuvens)[hora]
        return fator

    # ---------------------------------------------------------------- #
    # Fatores de carga por dia da semana
    # ---------------------------------------------------------------- #
    def _aplicar_fatores_carga(self, dia: int):
        """Multiplica cada LoadShape de carga pelo fator do dia.

        CORREÇÃO DE BUG: a API expõe ``Pmult`` (m minúsculo). A grafia
        antiga ``PMult`` levantava AttributeError, engolido pelo
        ``except: continue``, e os fatores por dia ficavam inertes sem
        qualquer sinal. Os multiplicadores partem do cache dos valores
        originais, o que impede a composição entre dias.
        """
        if self.motor is None or not self.curva_carga_por_elemento:
            return

        fator = self.fatores_carga[dia % len(DIAS_DA_SEMANA)]

        for curva in sorted(set(self.curva_carga_por_elemento.values())):
            originais = self.pmult_original_por_curva.get(curva)
            if not originais:
                continue
            novos = [v * fator for v in originais]
            texto = " ".join(f"{v:.6f}" for v in novos)
            try:
                self.motor.dssText.Command = (
                    f"Edit Loadshape.{curva} mult=({texto})")
            except Exception as e:
                self._registrar_evento(
                    "aviso", f"falha ao aplicar fator em {curva}: {e}")

    # ---------------------------------------------------------------- #
    # Avanço de dia
    # ---------------------------------------------------------------- #
    def avancar_dia(self) -> Dict[str, Any]:
        """Fecha o dia corrente e prepara o seguinte.

        PRESERVA: SoC (vem do próprio motor/Storage), economia total e o
        log de eventos. ZERA: séries do dia (o chamador recebe o dict de
        virada e trata isso), histórico de despacho do dia e economia do
        dia, que já foi acumulada em ``economia_total``.
        """
        if self.motor is None:
            raise RuntimeError("avancar_dia() antes de preparar().")
        if not self.dia_concluido:
            raise RuntimeError(
                f"avancar_dia() chamado com hora_atual={self.hora_atual}; "
                "execute até a hora 23 antes de virar o dia.")

        dia_encerrado = self.dia_atual
        economia_dia_encerrado = self.economia_dia

        self.dia_atual += 1
        self.hora_atual = -1
        self.historico_dia = {}
        self.economia_dia = 0.0
        self.energia_despachada_dia = {"carga_kwh": 0.0, "descarga_kwh": 0.0}
        self.evento_afundamento = None

        # Fatores de carga do novo dia. O solve é feito DEPOIS da edição
        # para que o passo 0 do novo dia já reflita a nova carga; resolver
        # antes deixaria a primeira hora do dia na carga antiga.
        self._aplicar_fatores_carga(self.dia_atual)
        self.motor.dssSolution.Solve()

        self._registrar_evento(
            "virada_dia",
            f"{self.rotulo_dia} iniciado · fator de carga "
            f"{self.fatores_carga[self.dia_atual % len(DIAS_DA_SEMANA)]:.2f} · "
            f"dia anterior ({_rotulo_dia(dia_encerrado)}) fechou com "
            f"R$ {economia_dia_encerrado:,.2f}")

        return {
            "dia": self.dia_atual,
            "rotulo_dia": self.rotulo_dia,
            "dia_encerrado": dia_encerrado,
            "economia_dia_encerrado": economia_dia_encerrado,
            "economia_total": self.economia_total,
            "fator_carga": self.fatores_carga[
                self.dia_atual % len(DIAS_DA_SEMANA)],
        }

    # ---------------------------------------------------------------- #
    # Passo horário
    # ---------------------------------------------------------------- #
    def executar_passo(self, hora: int) -> Dict[str, Any]:
        """Aplica nuvens, a regra de despacho da hora e resolve o passo.

        A regra de despacho é a MESMA de ``economia_energia._simular_dia``
        — ver o comentário de reuso no topo do módulo. Qualquer divergência
        aqui seria erro de fidelidade, não escolha.
        """
        if self.motor is None:
            raise RuntimeError("SessaoAoVivo.executar_passo() antes de preparar().")
        if not (0 <= hora <= HORAS_POR_DIA - 1):
            raise ValueError(f"hora fora de 0..{HORAS_POR_DIA - 1}: {hora}")

        # Nuvens antes do solve: a irradiância do passo é a do passo.
        self._aplicar_nuvens(self.dia_atual, hora)

        ponta = _eh_hora_ponta(
            hora, self.horario_ponta_inicio, self.horario_ponta_fim)

        estados_aplicados: Dict[str, Dict[str, Any]] = {}
        if self.controlar and self.nomes_bess:
            for nome in self.nomes_bess:
                # Mesma decisão da simulação de economia: descarrega na
                # ponta enquanto houver carga acima do mínimo, carrega fora
                # dela enquanto houver espaço abaixo do máximo. Fora dessas
                # condições, repouso.
                soc_atual = _ler_soc(self.motor, nome)
                if ponta and soc_atual > self.soc_min:
                    novo_estado = "discharging"
                elif (not ponta) and soc_atual < self.soc_max:
                    novo_estado = "charging"
                else:
                    novo_estado = "idling"
                _definir_estado_storage(self.motor, nome, novo_estado)
                estados_aplicados[nome] = {
                    "estado": novo_estado, "soc_antes": soc_atual}

        self.motor.dssSolution.Solve()

        soc_depois = ({nome: _ler_soc(self.motor, nome) for nome in self.nomes_bess}
                      if self.nomes_bess else {})

        kw_bruto = _ler_potencia_bruta_fonte_kw(self.motor)
        kw_comprada, kw_exportada = _classificar_fluxo(
            kw_bruto, self.sinal_referencia)

        try:
            perdas_kw = _AdaptadorDSS(self.motor).obter_perdas_totais_kw()
        # Perda indisponível não invalida o passo: vira NaN, e o ledger
        # grava None nesse campo em vez de um número falso.
        except Exception:
            perdas_kw = float("nan")

        vmin, vmax = _vmin_vmax_por_fase(self.motor)
        tensoes = _tensoes_por_barra_max_fase(self.motor)

        # --- economia acumulada (arbitragem do BESS) ---
        economia_passo, carga_kwh, descarga_kwh = self._contabilizar_economia(
            estados_aplicados, ponta)

        self.hora_atual = hora
        self.historico_dia[hora] = {
            "hora": hora,
            "ponta": ponta,
            "estados_aplicados": estados_aplicados,
            "soc_depois": soc_depois,
        }

        # Ledger contínuo (atravessa dias): base dos gráficos e da
        # exportação. Só tipos nativos, para o snapshot sair direto em JSON.
        self.passo_global += 1
        fator_nuvem_passo = self.fator_nuvens_da_hora(self.dia_atual, hora)
        kw_por_bess = {}
        for indice, nome in enumerate(self.nomes_bess):
            dados_estado = estados_aplicados.get(nome, {})
            estado_nome = dados_estado.get("estado", "idling")
            try:
                potencia_kw = float(self.bess_list[indice]["kw"])
            except (IndexError, KeyError, TypeError, ValueError):
                potencia_kw = 0.0
            sinal = (1.0 if estado_nome == "discharging"
                     else (-1.0 if estado_nome == "charging" else 0.0))
            kw_por_bess[nome] = potencia_kw * sinal

        self.ledger_passos.append({
            "passo": self.passo_global,
            "dia": self.dia_atual,
            "hora": hora,
            "kw_fonte_bruto": float(kw_bruto),
            "kw_comprada": float(kw_comprada),
            "kw_exportada": float(kw_exportada),
            "perdas_kw": (float(perdas_kw) if perdas_kw == perdas_kw else None),
            "vmin": (float(vmin) if vmin is not None else None),
            "vmax": (float(vmax) if vmax is not None else None),
            "soc_por_bess": {n: float(v) for n, v in soc_depois.items()},
            "estado_por_bess": {n: d.get("estado", "idling")
                                for n, d in estados_aplicados.items()},
            "kw_por_bess": kw_por_bess,
            "fator_nuvens": float(fator_nuvem_passo),
            "pv_mult_por_unidade": {n: float(fator_nuvem_passo)
                                    for n in self.pv_original},
            "economia_passo": float(economia_passo),
            "economia_dia": float(self.economia_dia),
            "economia_total": float(self.economia_total),
            "ponta": bool(ponta),
        })

        return {
            "hora": hora,
            "dia": self.dia_atual,
            "rotulo_dia": self.rotulo_dia,
            "ponta": ponta,
            "kw_fonte_bruto": kw_bruto,
            "kw_comprada": kw_comprada,
            "kw_exportada": kw_exportada,
            "perdas_kw": perdas_kw,
            "vmin": vmin,
            "vmax": vmax,
            "tensoes": tensoes,
            "estados_aplicados": estados_aplicados,
            "soc_depois": soc_depois,
            "fator_nuvens": self.fator_nuvens_da_hora(self.dia_atual, hora),
            "economia_passo": economia_passo,
            "economia_dia": self.economia_dia,
            "economia_total": self.economia_total,
            "carga_kwh": carga_kwh,
            "descarga_kwh": descarga_kwh,
        }

    def _contabilizar_economia(self, estados_aplicados: Dict[str, Dict[str, Any]],
                               ponta: bool):
        """Economia do passo por arbitragem (escopo: TRANSPARÊNCIA item 3).

        Energia despachada = potência nominal do BESS × 1 h, com o sinal
        dado pelo estado aplicado (descarga = +kW, carga = −kW). Usar a
        nominal (``bess_list[i]["kw"]``) e não a leitura do terminal é
        deliberado: ``%charge/%discharge=100`` já garante despacho nominal,
        e a leitura do terminal fica contaminada pela tensão do momento.

        ``valor = descarga_kwh × tarifa_ponta − carga_kwh × tarifa_fora``.
        O argumento ``ponta`` não entra na conta: o sinal já vem do estado,
        e a tarifa aplicada é a do posto correspondente.
        """
        if not self.controlar or not self.nomes_bess:
            return 0.0, 0.0, 0.0

        tarifa = self.tarifa()
        carga_kwh = 0.0
        descarga_kwh = 0.0
        for indice, nome in enumerate(self.nomes_bess):
            dados = estados_aplicados.get(nome)
            if not dados:
                continue
            estado = dados["estado"]
            # Potência nominal do BESS dono deste Storage.
            try:
                potencia_kw = float(self.bess_list[indice]["kw"])
            except (IndexError, KeyError, TypeError, ValueError):
                continue
            if estado == "discharging":
                descarga_kwh += potencia_kw * 1.0
            elif estado == "charging":
                carga_kwh += potencia_kw * 1.0

        valor = (descarga_kwh * tarifa.tarifa_ponta_kwh
                 - carga_kwh * tarifa.tarifa_fora_ponta_kwh)

        self.economia_dia += valor
        self.economia_total += valor
        self.energia_despachada_dia["carga_kwh"] += carga_kwh
        self.energia_despachada_dia["descarga_kwh"] += descarga_kwh
        return valor, carga_kwh, descarga_kwh

    # ---------------------------------------------------------------- #
    # Afundamento de tensão (contexto ISOLADO)
    # ---------------------------------------------------------------- #
    def simular_afundamento(self, bus: str, tipo_falta: str) -> Dict[str, Any]:
        """Reproduz uma falta no passo corrente, em motor separado.

        Por que separado (TRANSPARÊNCIA item 4): ``Set Mode=Daily`` faz
        ``Solve()`` avançar o relógio do QSTS. Aplicar a falta no motor
        vivo saltaria uma hora. Aqui um segundo ``MotorReutilizavel``
        recompila o mesmo master, refaz o dia até a hora corrente
        (reinserindo os BESS com o SoC lido agora e reaplicando o despacho
        histórico), aplica a falta, captura e é descartado.

        Retorna o dict do evento, também guardado em
        ``self.evento_afundamento`` e no log.
        """
        if self.motor is None:
            raise RuntimeError("simular_afundamento() antes de preparar().")
        if self.hora_atual < 0:
            raise RuntimeError(
                "simular_afundamento() exige pelo menos um passo executado.")
        if tipo_falta not in _TIPOS_FALTA_VALIDOS:
            raise ValueError(
                f"tipo de falta inválido: {tipo_falta!r}; "
                f"válidos: {_TIPOS_FALTA_VALIDOS}")

        tipo_falta_dss = "trifasica" if tipo_falta == "trifasica" else "monofasica"
        r_falta = (R_FALTA_ALTA_IMPEDANCIA
                   if tipo_falta == "monofasica_alta_impedancia"
                   else R_FALTA_SOLIDA)

        # SoC de partida = o que o motor vivo reporta agora, ao fim do passo
        # corrente. Assim o replay começa com a mesma energia armazenada.
        socs_agora = {nome: _ler_soc(self.motor, nome) for nome in self.nomes_bess}
        soc_replay = (sum(socs_agora.values()) / len(socs_agora)
                      if socs_agora else self.soc_inicial)

        dia = self.dia_atual
        hora = self.hora_atual
        motor_isolado = MotorReutilizavel()
        avisos: List[str] = []
        try:
            motor_isolado.recompilar(self.caminho_master)

            nomes_bess = []
            if self.controlar and self.bess_list:
                nomes_bess = _inserir_bess_idling(
                    motor_isolado, self.bess_list, soc_replay)
                motor_isolado.dssSolution.Solve()

            motor_isolado.dssText.Command = "Set Mode=Daily"
            motor_isolado.dssText.Command = "Set Stepsize=1h"
            motor_isolado.dssText.Command = "Set Number=1"

            # Nuvens do dia (mesma deriva) + despacho histórico.
            self._replay_ate_hora(
                motor_isolado, dia, hora, nomes_bess, avisos)

            # Tensão antes da falta, no mesmo contexto: é o termo de
            # comparação para saber quanto a falta afundou cada barra.
            pu_antes = _capturar_pu_todas_barras(motor_isolado.dssCircuit)
            _aplicar_falta(motor_isolado, bus, tipo_falta_dss, r_falta)
            motor_isolado.dssSolution.Solve()
            convergiu = bool(motor_isolado.dssSolution.Converged)

            if convergiu:
                pu = _capturar_pu_todas_barras(motor_isolado.dssCircuit)
                barras_sag = _classificar_sag(
                    pu, bus, SAG_LIMITE_INFERIOR, SAG_LIMITE_SUPERIOR)
            else:
                # Não convergir sob falta severa indica colapso de tensão
                # local. Mesmo critério conservador do estudo de
                # afundamento: reporta todas as barras em falta, exceto a
                # da própria falta.
                pu = {}
                barras_sag = set(b for b in self.coordenadas if b != bus)
                avisos.append(
                    "Solução não convergiu sob a falta — afundamento "
                    "considerado em todas as barras (critério conservador).")

            vmin_evento = None
            for valores in pu.values():
                for v in valores:
                    if v is not None and v > 0:
                        vmin_evento = v if vmin_evento is None else min(vmin_evento, v)
            if vmin_evento is None:
                vmin_evento = 0.0

            tensoes_evento = {}
            for barra_nome, valores in pu.items():
                if valores:
                    tensoes_evento[barra_nome] = max(valores)

        # finalizar() no finally para que a falha do replay não deixe um
        # segundo contexto do Engine aberto na sessão.
        finally:
            motor_isolado.finalizar()

        evento = {
            "dia": dia,
            "rotulo_dia": _rotulo_dia(dia),
            "hora": hora,
            "bus": bus,
            "tipo": tipo_falta,
            "tipo_rotulo": TIPOS_FALTA_DISPONIVEIS[tipo_falta],
            "vmin": vmin_evento,
            "convergiu": convergiu,
            "barras_em_sag": sorted(barras_sag),
            "pu": pu,
            "tensoes": tensoes_evento,
            "pu_antes": pu_antes,
            "avisos": avisos,
        }
        self.evento_afundamento = evento
        self._registrar_evento(
            "afundamento",
            f"{_rotulo_dia(dia)} · {hora:02d}:00 · falta "
            f"{TIPOS_FALTA_DISPONIVEIS[tipo_falta].split(' (')[0].lower()} "
            f"na barra {bus} · Vmin {vmin_evento:.3f} pu · "
            f"{len(barras_sag)} barra(s) em afundamento")
        return evento

    def _replay_ate_hora(self, motor_isolado: MotorReutilizavel, dia: int,
                         hora_alvo: int, nomes_bess: List[str],
                         avisos: List[str]):
        """Refaz no motor isolado os passos 0..hora_alvo do dia corrente.

        O replay reaplica, para cada hora do histórico: nuvens do dia,
        SoC lido na sessão viva antes do despacho daquela hora e o estado
        de despacho aplicado. O SoC é reimposto por
        ``Edit Storage.x %stored`` — sem isso os BESS do contexto novo
        começariam todos no SoC inicial em vez de reproduzir o dia.
        """
        if hora_alvo < 0:
            avisos.append("Nenhum passo executado: falta aplicada sobre o "
                          "caso base do dia.")
            return

        faltando_soc = []
        for hora in range(hora_alvo + 1):
            registro = self.historico_dia.get(hora)

            # Nuvens primeiro: a irradiância precisa estar posta antes do
            # solve, igual ao passo ao vivo.
            fator = self.fator_nuvens_da_hora(dia, hora)
            for nome, original in self.pv_original.items():
                motor_isolado.dssText.Command = (
                    f"Edit PVSystem.{nome} irradiance={original * fator:.6f}")
            for nome, original in self.gerador_original.items():
                motor_isolado.dssText.Command = (
                    f"Edit Generator.{nome} kW={original * fator:.6f}")

            if registro:
                for nome in nomes_bess:
                    dados = registro["estados_aplicados"].get(nome)
                    if not dados:
                        continue
                    try:
                        motor_isolado.dssText.Command = (
                            f"Edit Storage.{nome} %stored="
                            f"{dados['soc_antes'] * 100:.4f}")
                    except Exception:
                        faltando_soc.append(hora)
                    _definir_estado_storage(motor_isolado, nome, dados["estado"])
            motor_isolado.dssSolution.Solve()

        if faltando_soc:
            avisos.append(
                f"SoC não pôde ser reimposto em {len(faltando_soc)} passo(s) "
                "do replay — os BESS partiram do SoC médio atual.")

    def fechar_evento_afundamento(self):
        """Descarta o evento corrente.

        Não há nada a desfazer: a simulação da falta nunca tocou a sessão
        viva. Só o destaque no mapa é retirado.
        """
        self.evento_afundamento = None
        self._registrar_evento(
            "afundamento_fim",
            "evento de afundamento encerrado pelo operador")

    # ---------------------------------------------------------------- #
    def cargas_por_barra_dia(self, dia: int) -> Dict[str, List[float]]:
        """Perfil de carga analítico por barra para o dia dado (kW/h).

        TRANSPARÊNCIA: o cálculo é analítico (nominal × curva × fator do
        dia), feito fora do motor. Nuvem não afeta carga, só geração. Carga
        sem curva fica constante, porque o fator do dia só edita LoadShapes
        — igual ao que acontece no motor. Curvas com ponto em toda hora são
        exatas; nas demais há interpolação linear, aproximação declarada e
        compatível com a resolução de 1 h do QSTS. Sem ``caminho_rede_json``
        ou ``pasta_curvas``, devolve {}.
        """
        if (not self.caminho_rede_json
                or not os.path.exists(self.caminho_rede_json)
                or not self.pasta_curvas):
            return {}
        try:
            rede = RedeEletrica.carregar_json(self.caminho_rede_json)
        except Exception:
            return {}

        fator = self.fatores_carga[dia % len(DIAS_DA_SEMANA)]
        cache_curvas: Dict[str, List[float]] = {}

        def _perfil(nome_curva, kw_nominal):
            if nome_curva in cache_curvas:
                return cache_curvas[nome_curva]
            curva = obter_curva(self.pasta_curvas, nome_curva)
            if not curva or not curva.pontos:
                return [kw_nominal] * HORAS_POR_DIA
            pts = curva.pontos_ordenados()
            saida = []
            for h in range(HORAS_POR_DIA):
                if h <= pts[0][0]:
                    pct = pts[0][1]
                elif h >= pts[-1][0]:
                    pct = pts[-1][1]
                else:
                    pct = pts[-1][1]
                    for i in range(len(pts) - 1):
                        h0, p0 = pts[i]
                        h1, p1 = pts[i + 1]
                        if h0 <= h <= h1:
                            pct = (p1 if h1 == h0
                                   else p0 + (p1 - p0) * (h - h0) / (h1 - h0))
                            break
                saida.append(kw_nominal * pct / 100.0 * fator)
            cache_curvas[nome_curva] = saida
            return saida

        soma: Dict[str, List[float]] = {}
        for _chave, derivacao in rede.derivacoes.items():
            if derivacao.tipo != "Load":
                continue
            props = derivacao.parametros or {}
            kw_nom = float(props.get("kw", 0) or 0)
            barra = derivacao.bus1
            curva = str(props.get("daily") or "").strip()
            if curva and curva != "Nenhuma":
                perfil = list(_perfil(curva, kw_nom))
            else:
                perfil = [kw_nom] * HORAS_POR_DIA
            alvo = soma.setdefault(barra, [0.0] * HORAS_POR_DIA)
            for h in range(HORAS_POR_DIA):
                alvo[h] += perfil[h]
        return {b: [float(v) for v in vals] for b, vals in soma.items()}

    def _pv_kw_nominal(self) -> Dict[str, float]:
        """kW nominais (pmpp) das PVSystems, lidos do rede.json."""
        saida: Dict[str, float] = {}
        if (not self.caminho_rede_json
                or not os.path.exists(self.caminho_rede_json)):
            return saida
        try:
            rede = RedeEletrica.carregar_json(self.caminho_rede_json)
        except Exception:
            return saida
        for _chave, derivacao in rede.derivacoes.items():
            if derivacao.tipo != "PVSystem":
                continue
            try:
                saida[str(derivacao.nome)] = float(
                    (derivacao.parametros or {}).get("pmpp", 0) or 0)
            except (TypeError, ValueError):
                continue
        return saida

    def dados_para_exportar(self) -> Dict[str, Any]:
        """Snapshot JSON-serializável para exportação de gráficos.

        Reflete o estado no INSTANTE da chamada (recomenda-se pausar a
        simulação antes de exportar). Dias com dados = dias presentes no
        ledger (o dia em curso inclui os passos já resolvidos).
        """
        dias_com_dados = sorted({p["dia"] for p in self.ledger_passos})
        cargas = {dia: self.cargas_por_barra_dia(dia) for dia in dias_com_dados}
        return {
            "meta": {
                "dias_com_dados": dias_com_dados,
                "dia_atual": self.dia_atual,
                "hora_atual": self.hora_atual,
                "nomes_bess": list(self.nomes_bess),
                "pv_kw_nominal": self._pv_kw_nominal(),
                "possui_pv": bool(self.pv_original),
                "nomes_pv": sorted(self.pv_original),
                "dias_da_semana": list(DIAS_DA_SEMANA),
                "fatores_carga": [float(f) for f in self.fatores_carga],
                "chave_tarifa": self.chave_tarifa,
            },
            "ledger": [dict(p) for p in self.ledger_passos],
            "log": [dict(e) for e in self.log_eventos],
            "cargas_por_barra": {d: {b: list(v) for b, v in c.items()}
                                 for d, c in cargas.items()},
            "fatores_dia": [float(f) for f in self.fatores_carga],
        }

    def encerrar(self):
        if self.motor is not None:
            try:
                self.motor.finalizar()
            finally:
                self.motor = None
                self._preparado = False


# ============================================================
# Apoio ao projeto (rede.json -> BESS e curvas de carga)
# ============================================================

def bess_do_rede_json(caminho_rede_json: str) -> List[Dict[str, Any]]:
    """BESS declarados na rede do projeto, no formato que
    ``economia_energia._inserir_bess_idling`` consome ({'bus','kw','kwh'}).

    Na ``RedeEletrica``, Storage é uma DERIVAÇÃO (uma única barra, campo
    ``bus1``) — não um ramo. Rede sem Storage devolve lista vazia.
    """
    bess_list: List[Dict[str, Any]] = []
    if not caminho_rede_json or not os.path.exists(caminho_rede_json):
        return bess_list
    try:
        rede = RedeEletrica.carregar_json(caminho_rede_json)
    except Exception:
        return bess_list

    for _chave, derivacao in getattr(rede, "derivacoes", {}).items():
        if getattr(derivacao, "tipo", "") != "Storage":
            continue
        barra = getattr(derivacao, "bus1", None)
        if not barra:
            continue
        props = getattr(derivacao, "parametros", {}) or {}
        try:
            kw = float(props.get("kwrated", props.get("kva", 0)) or 0)
            kwh = float(props.get("kwhrated", 0) or 0)
        except (TypeError, ValueError):
            continue
        if kw <= 0 or kwh <= 0:
            continue
        bess_list.append({"bus": barra, "kw": kw, "kwh": kwh})
    return bess_list


def curvas_de_carga_do_rede_json(caminho_rede_json: str) -> Dict[str, str]:
    """Mapa elemento Load → nome da curva diária ('daily' do rede.json).

    Só elementos do tipo ``Load`` com curva declarada entram — a curva de
    um ``Generator``/``PVSystem``/``Storage`` não pode ser multiplicada
    pelo fator de carga do dia, sob pena de mexer na geração.
    """
    mapa: Dict[str, str] = {}
    if not caminho_rede_json or not os.path.exists(caminho_rede_json):
        return mapa
    try:
        rede = RedeEletrica.carregar_json(caminho_rede_json)
    except Exception:
        return mapa

    for _chave, derivacao in getattr(rede, "derivacoes", {}).items():
        if getattr(derivacao, "tipo", "") != "Load":
            continue
        props = getattr(derivacao, "parametros", {}) or {}
        curva = props.get("daily")
        if not curva or str(curva).strip() in ("", "Nenhuma"):
            continue
        nome = getattr(derivacao, "nome", _chave)
        mapa[str(nome)] = str(curva)
    return mapa
