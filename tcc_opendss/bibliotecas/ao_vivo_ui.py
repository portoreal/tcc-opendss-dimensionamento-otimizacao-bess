__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Simulação ao Vivo (QSTS animado) — DASHBOARD de operação contínua.

O QUE ESTE MÓDULO FAZ
---------------------
Executa um circuito OpenDSS em passos horários controlados pelo usuário
(Reproduzir/Pausar, Passo, Velocidade, Reiniciar) e apresenta a operação
como um dashboard:

  * mapa da rede com os nós coloridos pela tensão do passo corrente;
  * bateria: SoC (%, barra) e estado (carregando/descarregando/repouso);
  * Economia acumulada por arbitragem (R$ do dia e total);
  * rede: Vmin/Vmax, perdas, potência da fonte, barras em afundamento;
  * clima: índice de nuvens sobre a geração fotovoltaica;
  * gráficos do dia: Vmin/Vmax, SoC, fonte e perdas;
  * log de eventos (afundamentos, viradas de dia, trocas de tarifa).

OPERAÇÃO CONTÍNUA (o "relógio")
-------------------------------
O relógio avança uma hora a cada N segundos e atravessa a meia-noite: ao
fim da hora 23 o dia vira sozinho (Dia 1 · Segunda → Dia 2 · Terça …), os
gráficos são zerados e voltam a preencher, o SoC e a economia acumulada
persistem, e os fatores de carga do novo dia da semana passam a valer. É o
que permite comparar dias diferentes — por exemplo, uma curva de geração
fotovoltaica que muda de um dia para o outro.

SEPARAÇÃO MOTOR / INTERFACE
---------------------------
Toda a lógica (QSTS, despacho, dias, nuvens, fatores de carga, economia,
afundamento em contexto isolado) vive em ``ao_vivo_engine.py``, que não
importa Qt e roda sem tela. Este módulo é apenas a casca visual.

REUSO DELIBERADO (nada de despacho duplicado)
---------------------------------------------
A regra de despacho ponta/fora-ponta e os primitivos de escrita no
Storage vêm de ``economia_energia``; os primitivos de falta vêm de
``estudo_afundamento``. Nenhum deles é reimplementado aqui.

TRANSPARÊNCIA TÉCNICA (suposições explícitas)
---------------------------------------------
1. CORES DO MAPA. Os limiares 0,95 e 0,90 pu (verde/amarelo/vermelho)
   são auxílio visual deste módulo, não classificação normativa. As
   faixas adequadas/precárias/críticas da ANEEL (PRODIST Módulo 8) variam
   com o nível de tensão do ponto de entrega (BT/MT/AT) e o modelo aqui
   não dispõe do nível de tensão contratado de cada barra. Use o mapa
   para localizar barras problemáticas, não para emitir laudo.
2. BARRAS SEM COORDENADA. Circuitos cujo .dss não traz ``Buscoords``
   devolvem (0,0) para todas as barras. Essas barras são deslocadas
   radialmente a partir do centroide para não se sobreporem na origem, e
   o rodapé da figura avisa quantas foram. A posição delas é arbitrária,
   só legível.
3. CARGA CONSTANTE. Se o Master.dss não declarar ``LoadShape``, todos os
   passos do dia resolvem com a mesma carga. A animação, nesse caso, mostra
   a
   evolução do SoC/despacho do BESS, não uma variação de carga que não
   existe no modelo. O rodapé avisa.
4. NUVENS, FATORES DE CARGA POR DIA E ECONOMIA são MODELO DE SIMULAÇÃO,
   não dados medidos — a justificativa completa está no docstring de
   ``ao_vivo_engine`` (itens 1, 2 e 3).
5. THREAD. A solução roda em thread de trabalho persistente; resultados
   chegam à UI por ``queue.Queue`` drenada por ``QTimer`` (mesmo padrão
   do módulo de Otimização). O motor OpenDSS é acessado exclusivamente
   pela thread de trabalho; a thread da UI nunca toca o motor.
6. NENHUM DIÁLOGO MODAL no caminho do relógio, do passo ou do afundamento:
   erros desses caminhos vão para a barra de status e para o log. Não é
   preferência estética. Um modal ali trava a thread da UI para sempre em
   execução offscreen, onde ninguém pode clicar "OK" — e é justamente em
   offscreen que os testes rodam.
"""

import os

os.environ.setdefault("MPLBACKEND", "QtAgg")

import math
import time
import queue
import sys
import threading
from typing import Any, Dict, List, Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .ao_vivo_engine import (
    DIAS_DA_SEMANA,
    HORAS_POR_DIA,
    SOC_MAX,
    SOC_MIN,
    SessaoAoVivo,
    bess_do_rede_json,
    curvas_de_carga_do_rede_json,
)
from .projeto import Projeto
from .tarifas_energia import listar_opcoes_tarifa, obter_tarifa
from .ui_win11 import obter_paleta_ativa
from .ao_vivo_exportar import CHAVES_GRAFICOS, exportar_graficos

# Intervalo do relógio, em ms, por hora simulada. O padrão de 12,5 s faz
# um dia completo durar 5 min (24 × 12,5 s = 300 s) — pedido do pesquisador,
# para caber uma demonstração inteira numa banca.
INTERVALOS_VELOCIDADE_MS = (1000, 5000, 12500, 30000, 60000)
ROTULOS_VELOCIDADE = {1000: "1 s / hora", 5000: "5 s / hora",
                      12500: "12,5 s / hora — dia de 5 min (padrão)",
                       30000: "30 s / hora",
                      60000: "1 min / hora"}
INTERVALO_VELOCIDADE_PADRAO_MS = 12500
# Fração do intervalo em que o último segmento é desenhado, para o traço
# parecer fluido em vez de dar saltos de uma hora para outra.
FRACAO_TRACO = 0.35

# Limiares apenas de auxílio visual (ver TRANSPARÊNCIA TÉCNICA, item 1).
# Não são classificação PRODIST: o nível de tensão contratado de cada barra
# não está disponível no modelo.
LIMIAR_TENSAO_BOM = 0.95
LIMIAR_TENSAO_ACEITAVEL = 0.90

ACCENT = "#004587"  # azul institucional WEG (fixo em ui_win11)
COR_BOM = "#1b8f3a"
COR_ACEITAVEL = "#e0a300"
COR_RUIM = "#c62828"
COR_DESCARGA = "#b35c00"
COR_REPOUSO = "#7a7a7a"
COR_CARGA = "#1b8f3a"

_INTERVALO_FILA_MS = 100


# ============================================================
# Geometria do mapa
# ============================================================

def _posicionar_barras(coordenadas: Dict[str, tuple]):
    """Separa barras com coordenada real das que caíram em (0,0).

    O OpenDSS devolve (0,0) para barra sem ``Buscoords``, mas (0,0) também
    é coordenada legítima em alguns conjuntos oficiais. Pelo valor não há
    como separar os dois casos; por isso toda barra em (0,0) é tratada como
    "sem coordenada" e deslocada para um anel em torno do centroide. O
    rodapé da figura informa a contagem, para que a arbitrariedade fique
    visível (TRANSPARÊNCIA TÉCNICA, item 2).
    """
    # Tolerância de 1e-9 porque a coordenada vem como float do OpenDSS: a
    # comparação exata com 0 falharia para um resíduo mínimo.
    com_coord = {b: (x, y) for b, (x, y) in coordenadas.items()
                 if not (abs(x) < 1e-9 and abs(y) < 1e-9)}
    sem_coord = [b for b, (x, y) in coordenadas.items()
                 if abs(x) < 1e-9 and abs(y) < 1e-9]

    if not sem_coord:
        return com_coord, []

    if com_coord:
        # Centroide e extensão do que tem coordenada real, para o anel das
        # órfãs envolver o desenho em vez de se sobrepor a ele.
        cx = sum(p[0] for p in com_coord.values()) / len(com_coord)
        cy = sum(p[1] for p in com_coord.values()) / len(com_coord)
        extensao = max(
            max(abs(p[0] - cx) for p in com_coord.values()),
            max(abs(p[1] - cy) for p in com_coord.values()), 1.0)
    else:
        cx, cy, extensao = 0.0, 0.0, 1.0

    # 1,35 de folga coloca o anel por fora do desenho, sem sair do
    # enquadramento automático do eixo.
    raio = extensao * 1.35
    posicionadas = dict(com_coord)
    for i, barra in enumerate(sorted(sem_coord)):
        # Distribuição em ângulos iguais: determinística, então a barra
        # aparece sempre no mesmo lugar entre aberturas da janela.
        angulo = 2.0 * math.pi * i / max(len(sem_coord), 1)
        posicionadas[barra] = (cx + raio * math.cos(angulo),
                               cy + raio * math.sin(angulo))
    return posicionadas, sorted(sem_coord)


def _cor_por_tensao(v: Optional[float]) -> str:
    # None = barra sem leitura no passo (desenergizada ou fora do mapa);
    # cinza em vez de verde, para não sugerir tensão normal.
    if v is None:
        return "#7a7a7a"
    if v >= LIMIAR_TENSAO_BOM:
        return COR_BOM
    if v >= LIMIAR_TENSAO_ACEITAVEL:
        return COR_ACEITAVEL
    return COR_RUIM


def _formatar_reais(valor: float) -> str:
    """Formata R$ 1.234,56 no padrão brasileiro.

    A formatação americana do Python usa vírgula para milhar e ponto para
    decimal — o inverso daqui. A troca passa por um caractere nulo
    temporário para não desfazer a primeira substituição na segunda.
    """
    texto = f"{valor:,.2f}"
    return "R$ " + texto.replace(",", "\0").replace(".", ",").replace("\0", ".")


# ============================================================
# Cartão do dashboard
# ============================================================

class _Cartao(QFrame):
    """Cartão do dashboard: título em caixa alta, valor grande, detalhe.

    O estilo é aplicado inline (e não no QSS global) porque a cor do valor
    muda com o estado — verde, âmbar, vermelho — e precisa ser reescrita a
    cada atualização.
    """

    def __init__(self, titulo: str, parent=None):
        super().__init__(parent)
        self.setObjectName("cartao")
        self.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(2)

        self.lbl_titulo = QLabel(titulo.upper())
        self.lbl_titulo.setStyleSheet(
            "font-size:10px; letter-spacing:1px; color:#5a5a5a;")
        self.lbl_valor = QLabel("—")
        self.lbl_valor.setStyleSheet(
            f"font-size:26px; font-weight:700; color:{ACCENT};")
        self.lbl_detalhe = QLabel("")
        self.lbl_detalhe.setStyleSheet("font-size:11px; color:#4a4a4a;")
        self.lbl_detalhe.setWordWrap(True)

        layout.addWidget(self.lbl_titulo)
        layout.addWidget(self.lbl_valor)
        layout.addWidget(self.lbl_detalhe)

        self.widget_extra: Optional[QWidget] = None

    def adicionar_extra(self, widget: QWidget):
        # Widget adicional (barra de progresso do SoC, por exemplo) vai
        # abaixo do texto, dentro do mesmo cartão.
        self.widget_extra = widget
        self.layout().addWidget(widget)

    def definir(self, valor: str, detalhe: str = "", cor: Optional[str] = None):
        self.lbl_valor.setText(valor)
        if cor:
            self.lbl_valor.setStyleSheet(
                f"font-size:26px; font-weight:700; color:{cor};")
        self.lbl_detalhe.setText(detalhe)


# ============================================================
# Janela
# ============================================================

class JanelaSimulacaoAoVivo(QMainWindow):
    """Dashboard da Simulação ao Vivo. Ver o docstring do módulo."""

    def __init__(self, projeto: Projeto, parent=None):
        super().__init__(parent)
        self.projeto = projeto
        self.caminho_master = os.path.join(projeto.caminho_rede, "Master.dss")
        self.caminho_rede_json = os.path.join(projeto.caminho_rede, "rede.json")

        self.setWindowTitle("Simulação ao Vivo — Dashboard (QSTS animado)")
        self.resize(1500, 950)

        self.sessao: Optional[SessaoAoVivo] = None
        # Duas filas: uma leva pedidos da UI para a thread de trabalho, a
        # outra traz resultados de volta. A UI nunca chama o motor direto.
        self.fila_trabalho: "queue.Queue[tuple]" = queue.Queue()
        self.fila_resultados: "queue.Queue[tuple]" = queue.Queue()
        self.thread_trabalho: Optional[threading.Thread] = None
        self.thread_viva = False

        # Estado de apresentação (o motor fica na sessão).
        self.dia_corrente = 0
        self.hora_corrente = -1
        self.series: Dict[str, List[Any]] = self._series_vazias()
        self.series_soc: Dict[str, List[Any]] = {}
        self.tensoes_correntes: Dict[str, float] = {}
        self.tensoes_evento: Dict[str, float] = {}
        self.barras_em_sag: List[str] = []
        self.coordenadas: Dict[str, tuple] = {}
        self.linhas: List[Any] = []
        self.transformadores: List[Any] = []
        self.barras_sem_coordenada: List[str] = []
        self.posicionadas: Dict[str, tuple] = {}
        self.meta: Dict[str, Any] = {}
        self.controlar = False
        self._play_ativo = False
        self._evento_ativo = False
        self._soc_atual = 0.0
        self._estado_bess = "repouso"
        self._instante_ultimo_passo = 0.0
        self._resultado_snapshot = None
        self._erro_snapshot = None

        self._montar_ui()

        self.timer_play = QTimer(self)
        self.timer_play.timeout.connect(self._ao_timer_play)
        self.timer_play.setInterval(INTERVALO_VELOCIDADE_PADRAO_MS)
        # Relógio separado para a animação do traço. O passo horário chega
        # de 12,5 em 12,5 s; este timer de 100 ms redesenha só o último
        # segmento com interpolação, o que dá a sensação de traço contínuo
        # sem resolver o circuito mais vezes.
        self.timer_animacao = QTimer(self)
        self.timer_animacao.setInterval(100)
        self.timer_animacao.timeout.connect(self._tick_animacao)

        self.timer_fila = QTimer(self)
        self.timer_fila.timeout.connect(self._drenar_fila)
        # A fila é drenada na thread da UI a cada 100 ms. O motor nunca
        # aparece aqui: só os resultados que a thread de trabalho publicou.
        self.timer_fila.start(_INTERVALO_FILA_MS)

        QTimer.singleShot(0, self._iniciar_carregamento)

    # ---------------------------------------------------------------- #
    @staticmethod
    def _series_vazias() -> Dict[str, List[Any]]:
        # None (e não 0) marca "hora ainda não simulada". Zero seria um
        # valor legítimo e apareceria como ponto no gráfico.
        return {"vmin": [None] * HORAS_POR_DIA,
                "vmax": [None] * HORAS_POR_DIA,
                "perdas": [None] * HORAS_POR_DIA,
                "kw_fonte": [None] * HORAS_POR_DIA,
                "nuvens": [None] * HORAS_POR_DIA}

    # ---------------------------------------------------------------- #
    # Montagem da interface
    # ---------------------------------------------------------------- #
    def _montar_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(10, 8, 10, 8)
        raiz.setSpacing(8)

        raiz.addLayout(self._montar_barra_superior())
        raiz.addWidget(self._montar_cartoes())

        corpo = QHBoxLayout()
        corpo.setSpacing(8)

        # ------------- figura (mapa + gráficos do dia) ------------- #
        # Proporção 3:1 entre o miolo (mapa e gráficos) e a coluna lateral.
        self.figura = Figure(figsize=(11, 7), layout="constrained")
        self.canvas = FigureCanvas(self.figura)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        corpo.addWidget(self.canvas, 3)
        self._construir_eixos()

        # ------------- coluna lateral (controles + log) ------------- #
        corpo.addWidget(self._montar_coluna_lateral(), 1)
        raiz.addLayout(corpo, 1)

        self.lbl_status = QLabel("Carregando circuito…")
        self.lbl_status.setStyleSheet("color:#333; font-size:11px;")
        raiz.addWidget(self.lbl_status)

        self._aplicar_estilo()

    # ---------------------------------------------------------------- #
    def _montar_barra_superior(self) -> QHBoxLayout:
        barra = QHBoxLayout()

        self.lbl_dia = QLabel("Dia 1 · Segunda")
        self.lbl_dia.setStyleSheet(
            f"font-size:20px; font-weight:700; color:{ACCENT};")
        self.lbl_relogio = QLabel("--:00")
        self.lbl_relogio.setStyleSheet("font-size:20px; font-weight:600;")
        self.lbl_ponta = QLabel("")
        self.lbl_ponta.setStyleSheet("font-size:11px; color:#5a5a5a;")

        self.btn_play = QPushButton("▶  Reproduzir")
        self.btn_play.clicked.connect(self._alternar_play)
        self.btn_passo = QPushButton("Passo")
        self.btn_passo.clicked.connect(self._passo_unico)
        self.btn_reiniciar = QPushButton("⟲  Reiniciar")
        self.btn_reiniciar.clicked.connect(self._reiniciar)

        self.combo_velocidade = QComboBox()
        for ms in INTERVALOS_VELOCIDADE_MS:
            self.combo_velocidade.addItem(ROTULOS_VELOCIDADE[ms], ms)
        idx = INTERVALOS_VELOCIDADE_MS.index(INTERVALO_VELOCIDADE_PADRAO_MS)
        self.combo_velocidade.setCurrentIndex(idx)
        self.combo_velocidade.currentIndexChanged.connect(self._ao_mudar_velocidade)
        self.btn_exportar = QPushButton("📤 Exportar gráficos")
        self.btn_exportar.clicked.connect(self._abrir_exportacao)

        self.progresso = QProgressBar()
        self.progresso.setRange(0, HORAS_POR_DIA - 1)
        self.progresso.setValue(0)
        self.progresso.setFormat("hora %v:00")
        self.progresso.setMaximumWidth(260)

        barra.addWidget(self.lbl_dia)
        barra.addSpacing(8)
        barra.addWidget(self.lbl_relogio)
        barra.addSpacing(6)
        barra.addWidget(self.lbl_ponta)
        barra.addStretch(1)
        for w in (self.btn_play, self.btn_passo, self.btn_reiniciar,
                  self.btn_exportar):
            barra.addWidget(w)
        barra.addSpacing(8)
        barra.addWidget(QLabel("Velocidade:"))
        barra.addWidget(self.combo_velocidade)
        barra.addSpacing(8)
        barra.addWidget(self.progresso)
        return barra

    # ---------------------------------------------------------------- #
    def _montar_cartoes(self) -> QWidget:
        container = QWidget()
        grade = QGridLayout(container)
        grade.setContentsMargins(0, 0, 0, 0)
        grade.setSpacing(8)

        # ---- Bateria ---- #
        self.cartao_bateria = _Cartao("Bateria")
        self.barra_soc = QProgressBar()
        self.barra_soc.setRange(0, 100)
        self.barra_soc.setValue(0)
        self.barra_soc.setFormat("%p%")
        self.barra_soc.setFixedHeight(16)
        self.cartao_bateria.adicionar_extra(self.barra_soc)

        # ---- Economia ---- #
        self.cartao_economia = _Cartao("Economia acumulada")
        self.combo_tarifa = QComboBox()
        for chave, rotulo in listar_opcoes_tarifa():
            self.combo_tarifa.addItem(rotulo, chave)
        self.combo_tarifa.currentIndexChanged.connect(self._ao_mudar_tarifa)
        self.cartao_economia.adicionar_extra(self.combo_tarifa)

        # ---- Rede ---- #
        self.cartao_rede = _Cartao("Rede")

        # ---- Clima ---- #
        self.cartao_clima = _Cartao("Clima · nuvens (PV)")
        self.slider_nuvens = QSlider(Qt.Horizontal)
        self.slider_nuvens.setRange(0, 100)
        self.slider_nuvens.setValue(100)
        self.slider_nuvens.setToolTip(
            "100% = céu limpo (irradiância nominal). "
            "Aplicado ao próximo passo resolvido.")
        self.slider_nuvens.valueChanged.connect(self._ao_mudar_nuvens)
        self.chk_cobertura = QCheckBox("Cobertura variável ao longo do dia")
        self.chk_cobertura.setToolTip(
            "Aplica uma deriva de cobertura reprodutível por dia sobre o "
            "índice escolhido — dias diferentes têm curvas diferentes.")
        self.chk_cobertura.toggled.connect(self._ao_alternar_cobertura)
        clima_extra = QWidget()
        clima_layout = QVBoxLayout(clima_extra)
        clima_layout.setContentsMargins(0, 2, 0, 0)
        clima_layout.setSpacing(2)
        clima_layout.addWidget(self.slider_nuvens)
        clima_layout.addWidget(self.chk_cobertura)
        self.cartao_clima.adicionar_extra(clima_extra)

        grade.addWidget(self.cartao_bateria, 0, 0)
        grade.addWidget(self.cartao_economia, 0, 1)
        grade.addWidget(self.cartao_rede, 0, 2)
        grade.addWidget(self.cartao_clima, 0, 3)
        for col in range(4):
            grade.setColumnStretch(col, 1)
        container.setMaximumHeight(180)
        return container

    # ---------------------------------------------------------------- #
    def _montar_coluna_lateral(self) -> QWidget:
        painel = QWidget()
        painel.setMaximumWidth(380)
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ---- Afundamento ---- #
        caixa = QFrame()
        caixa.setObjectName("cartao")
        caixa.setFrameShape(QFrame.StyledPanel)
        box = QVBoxLayout(caixa)
        box.setContentsMargins(10, 8, 10, 10)
        box.setSpacing(4)

        titulo = QLabel("⚡ AFUNDAMENTO DE TENSÃO")
        titulo.setStyleSheet(
            "font-size:10px; letter-spacing:1px; color:#5a5a5a;")
        box.addWidget(titulo)

        linha_bus = QHBoxLayout()
        self.combo_barra_falta = QComboBox()
        self.combo_barra_falta.setToolTip(
            "Barra onde a falta é aplicada (simulada em contexto isolado — "
            "não altera o passo ao vivo).")
        linha_bus.addWidget(QLabel("Barra:"))
        linha_bus.addWidget(self.combo_barra_falta, 1)
        box.addLayout(linha_bus)

        self.combo_tipo_falta = QComboBox()
        box.addWidget(self.combo_tipo_falta)

        linha_botoes = QHBoxLayout()
        self.btn_aplicar_falta = QPushButton("Aplicar falta")
        self.btn_aplicar_falta.clicked.connect(self._aplicar_falta)
        self.btn_fechar_evento = QPushButton("Fechar evento")
        self.btn_fechar_evento.clicked.connect(self._fechar_evento)
        self.btn_fechar_evento.setEnabled(False)
        linha_botoes.addWidget(self.btn_aplicar_falta)
        linha_botoes.addWidget(self.btn_fechar_evento)
        box.addLayout(linha_botoes)

        self.lbl_evento = QLabel("Nenhum evento ativo.")
        self.lbl_evento.setWordWrap(True)
        self.lbl_evento.setStyleSheet("font-size:11px; color:#4a4a4a;")
        box.addWidget(self.lbl_evento)
        layout.addWidget(caixa)

        # ---- Fatores de carga por dia ---- #
        caixa_dias = QFrame()
        caixa_dias.setObjectName("cartao")
        caixa_dias.setFrameShape(QFrame.StyledPanel)
        box_dias = QVBoxLayout(caixa_dias)
        box_dias.setContentsMargins(10, 8, 10, 10)
        box_dias.setSpacing(3)

        titulo_dias = QLabel("FATORES DE CARGA POR DIA (MODO DE SIMULAÇÃO)")
        titulo_dias.setStyleSheet(
            "font-size:10px; letter-spacing:1px; color:#5a5a5a;")
        titulo_dias.setWordWrap(True)
        box_dias.addWidget(titulo_dias)

        self.spins_fator: List[QDoubleSpinBox] = []
        grade = QGridLayout()
        grade.setSpacing(3)
        for i, dia in enumerate(DIAS_DA_SEMANA):
            spin = QDoubleSpinBox()
            spin.setRange(0.50, 1.50)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
            spin.setValue(1.00)
            spin.valueChanged.connect(self._ao_mudar_fatores)
            self.spins_fator.append(spin)
            grade.addWidget(QLabel(dia[:3]), i, 0)
            grade.addWidget(spin, i, 1)
        box_dias.addLayout(grade)

        nota = QLabel(
            "Multiplicam as curvas de carga do projeto. Aplicados no "
            "próximo dia. Não são dados medidos.")
        nota.setWordWrap(True)
        nota.setStyleSheet("font-size:10px; color:#6a6a6a;")
        box_dias.addWidget(nota)
        layout.addWidget(caixa_dias)

        # ---- Log de eventos ---- #
        titulo_log = QLabel("LOG DE EVENTOS")
        titulo_log.setStyleSheet(
            "font-size:10px; letter-spacing:1px; color:#5a5a5a;")
        layout.addWidget(titulo_log)
        self.lista_log = QListWidget()
        self.lista_log.setAlternatingRowColors(True)
        self.lista_log.setStyleSheet("font-size:11px;")
        layout.addWidget(self.lista_log, 1)

        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setWidget(painel)
        rolagem.setMaximumWidth(400)
        return rolagem

    # ---------------------------------------------------------------- #
    def _aplicar_estilo(self):
        """Aplica a identidade visual Win11 disponível em ``ui_win11``.

        ``ui_win11`` não expõe stylesheet global, então esta janela pega a
        paleta pública (``obter_paleta_ativa``) e monta o próprio QSS. A
        figura do matplotlib fica com o estilo padrão: folha de estilo Qt
        não alcança o canvas.
        """
        try:
            paleta = obter_paleta_ativa()
        # Paleta indisponível não impede a janela de abrir; ela só perde a
        # identidade visual e fica com as cores padrão do Qt.
        except Exception:
            return
        self._accent = getattr(paleta, "accent", ACCENT)
        self.setStyleSheet(
            f"QMainWindow, QWidget {{ background: {paleta.fundo_cartao}; "
            f"color: {paleta.texto_primario}; }}"
            f"QFrame#cartao {{ background: {paleta.fundo_cartao}; "
            f"border: 1px solid {paleta.borda_campo}; border-radius: 8px; }}"
            f"QPushButton {{ padding: 6px 14px; border-radius: 6px; "
            f"border: 1px solid {paleta.borda_campo}; "
            f"background: {paleta.botao_secundario_fundo}; }}"
            f"QPushButton:hover {{ background: {paleta.botao_secundario_hover}; }}"
            f"QPushButton:disabled {{ color: {paleta.texto_secundario}; }}"
            f"QProgressBar {{ border: 1px solid {paleta.borda_campo}; "
            f"border-radius: 5px; text-align: center; height: 16px; }}"
            f"QProgressBar::chunk {{ background: {paleta.accent}; "
            f"border-radius: 4px; }}")

    # ---------------------------------------------------------------- #
    def _construir_eixos(self):
        self.figura.clear()
        self.ax_mapa = self.figura.add_subplot(1, 3, (1, 2))
        self.ax_tensao = self.figura.add_subplot(3, 3, 3)
        self.ax_soc = self.figura.add_subplot(3, 3, 6, sharex=self.ax_tensao)
        self.ax_pot = self.figura.add_subplot(3, 3, 9, sharex=self.ax_tensao)

        self.ax_mapa.set_title("Mapa da rede — tensão do passo corrente (pu)")
        self.ax_mapa.set_aspect("equal", adjustable="datalim")
        self.ax_mapa.set_xticks([])
        self.ax_mapa.set_yticks([])

        self.ax_perdas = self.ax_pot.twinx()
        self.figura.canvas.draw_idle()

    # ---------------------------------------------------------------- #
    # Ciclo de vida da sessão (thread de trabalho)
    # ---------------------------------------------------------------- #
    def _iniciar_carregamento(self):
        if not os.path.exists(self.caminho_master):
            self.lbl_status.setText(
                f"Master.dss não encontrado em: {self.caminho_master}")
            self._bloquear_controles(True)
            return

        self._bloquear_controles(True)
        self.lbl_status.setText(
            "Compilando circuito e executando o caso base…")
        self._iniciar_thread_trabalho()
        self.fila_trabalho.put(("carregar", -1))

    def _iniciar_thread_trabalho(self):
        """Sobe a thread de trabalho PERSISTENTE (uma por janela).

        O motor OpenDSS é acessado exclusivamente por esta thread, do
        primeiro ``compile`` ao ``encerrar``. Uma única thread para toda a
        vida da janela evita o problema de "quem é o dono do motor" entre
        operações: carregar, passo, virar dia e falta são comandos na
        mesma fila, executados na mesma thread, em ordem.
        """
        if self.thread_viva:
            return
        self.thread_viva = True
        self.thread_trabalho = threading.Thread(
            target=self._thread_loop, daemon=True, name="ao_vivo_motor")
        self.thread_trabalho.start()

    # ---------------------------------------------------------------- #
    def _thread_loop(self):
        """Consome a fila de trabalho até receber 'encerrar'.

        Passam por aqui os comandos que não alteram o estado visível da
        sessão (virar dia, aplicar falta). O passo é resolvido na thread
        da UI, em ``_passo_unico`` -> ``_ao_passo_concluido``.
        """
        while True:
            comando, argumento = self.fila_trabalho.get()
            if comando == "encerrar":
                try:
                    if self.sessao is not None:
                        self.sessao.encerrar()
                finally:
                    self.sessao = None
                    self.fila_trabalho.task_done()
                return
            if comando == "passo":
                try:
                    dado = self.sessao.executar_passo(argumento)
                    self.fila_resultados.put(("passo", argumento, dado))
                # A exceção não sobe: vira mensagem na fila de resultados,
                # porque thread de trabalho que morre mata a janela junto.
                except Exception as e:  # noqa: BLE001 - reportado na UI
                    self.fila_resultados.put(("erro_passo", argumento, str(e)))
            elif comando == "carregar":
                sessao = None
                try:
                    bess_list = bess_do_rede_json(self.caminho_rede_json)
                    controlar = bool(bess_list)
                    curvas = curvas_de_carga_do_rede_json(
                        self.caminho_rede_json)
                    sessao = SessaoAoVivo(
                        self.caminho_master, bess_list, controlar,
                        curva_carga_por_elemento=curvas,
                        caminho_rede_json=self.caminho_rede_json,
                        pasta_curvas=self.projeto.caminho_curvas)
                    meta = sessao.preparar()
                    self.fila_resultados.put(("pronto", sessao, meta))
                except Exception as e:  # noqa: BLE001 - reportado na UI
                    if sessao is not None:
                        sessao.encerrar()
                    self.fila_resultados.put(("erro_carga", None, str(e)))
            elif comando == "reiniciar":
                try:
                    meta = self.sessao.reiniciar()
                    self.fila_resultados.put(("reiniciado", None, meta))
                except Exception as e:  # noqa: BLE001 - reportado na UI
                    self.fila_resultados.put(("erro_reinicio", None, str(e)))
            elif comando == "snapshot":
                try:
                    dados = (self.sessao.dados_para_exportar()
                             if self.sessao is not None else {})
                    self.fila_resultados.put(("snapshot", None, dados))
                except Exception as e:  # noqa: BLE001 - reportado na UI
                    self.fila_resultados.put(("erro_snapshot", None, str(e)))
            self.fila_trabalho.task_done()

    # ---------------------------------------------------------------- #
    def _drenar_fila(self):
        try:
            while True:
                tipo, valor_a, valor_b = self.fila_resultados.get_nowait()
                if tipo == "pronto":
                    self._ao_sessao_pronta(valor_a, valor_b)
                elif tipo == "erro_carga":
                    self._ao_erro_carga(valor_b)
                elif tipo == "passo":
                    self._ao_passo_concluido(valor_a, valor_b)
                elif tipo == "erro_passo":
                    self._ao_erro_passos(
                        f"Falha no passo da hora {valor_a}", valor_b)
                elif tipo == "reiniciado":
                    self._ao_reiniciado(valor_b)
                elif tipo == "erro_reinicio":
                    self._ao_erro_passos("Falha ao reiniciar a simulação",
                                         valor_b)
                elif tipo == "snapshot":
                    self._resultado_snapshot = valor_b
                elif tipo == "erro_snapshot":
                    self._erro_snapshot = valor_b
        except queue.Empty:
            pass

    # ---------------------------------------------------------------- #
    # Handlers de resultado
    # ---------------------------------------------------------------- #
    def _ao_sessao_pronta(self, sessao: SessaoAoVivo, meta: Dict[str, Any]):
        self.sessao = sessao
        self.meta = meta
        self.controlar = meta.get("controlar", False)
        self.coordenadas = meta.get("coordenadas", {})
        self.linhas = meta.get("linhas", [])
        self.transformadores = meta.get("transformadores", [])
        self.posicionadas, self.barras_sem_coordenada = _posicionar_barras(
            self.coordenadas)

        self.dia_corrente = meta.get("dia", 0)
        self.hora_corrente = -1
        self.series = self._series_vazias()
        self.series_soc = {nome: [None] * HORAS_POR_DIA
                           for nome in meta.get("nomes_bess", [])}
        self.tensoes_correntes = {}
        self.tensoes_evento = {}
        self.barras_em_sag = []
        self._evento_ativo = False
        self._soc_atual = 0.0
        self._estado_bess = "repouso"

        self._preencher_combos(meta)
        self._construir_eixos()
        self._desenhar_topo_estatico()
        self._atualizar_graficos()
        self._atualizar_cartoes()
        self._atualizar_relogio()

        # A sessão nasceu com a tarifa padrão do engine; alinhe o combo.
        chave = meta.get("chave_tarifa")
        if chave:
            idx = self.combo_tarifa.findData(chave)
            if idx >= 0:
                self.combo_tarifa.blockSignals(True)
                self.combo_tarifa.setCurrentIndex(idx)
                self.combo_tarifa.blockSignals(False)

        self._bloquear_controles(False)
        qtd_bess = len(meta.get("nomes_bess", []))
        partes = []
        if qtd_bess:
            partes.append(f"{qtd_bess} BESS sob controle")
        else:
            partes.append("Sem BESS no projeto — rede pura")
        if not meta.get("possui_pv"):
            partes.append("sem geração fotovoltaica (controle de nuvens inerte)")
        if not meta.get("curvas_de_carga"):
            partes.append("sem curvas de carga por dia (fatores inativos)")
        partes.append("pronto para reproduzir")
        self.lbl_status.setText(" · ".join(partes))
        self._registrar_log(
            f"Simulação preparada — {self.lbl_dia.text()}")

    def _preencher_combos(self, meta: Dict[str, Any]):
        # Barras do combo de falta: as coordenadas compiladas (mesma fonte
        # do mapa); se o circuito não trouxe Buscoords, a topologia cobre.
        barras = set(self.coordenadas.keys())
        if not barras:
            for bus1, bus2, _ in self.linhas:
                barras.add(bus1)
                barras.add(bus2)
            for bus1, bus2, _ in self.transformadores:
                barras.add(bus1)
                barras.add(bus2)
        self.combo_barra_falta.clear()
        self.combo_barra_falta.addItems(sorted(barras))

        self.combo_tipo_falta.clear()
        for chave, rotulo in meta.get("tipos_falta", {}).items():
            self.combo_tipo_falta.addItem(rotulo, chave)

    def _ao_reiniciado(self, meta: Dict[str, Any]):
        if meta:
            self.coordenadas = meta.get("coordenadas", self.coordenadas)
            self.posicionadas, self.barras_sem_coordenada = _posicionar_barras(
                self.coordenadas)
            self.dia_corrente = meta.get("dia", 0)
        self.series = self._series_vazias()
        for nome in list(self.series_soc):
            self.series_soc[nome] = [None] * HORAS_POR_DIA
        self.tensoes_correntes = {}
        self.tensoes_evento = {}
        self.barras_em_sag = []
        self._evento_ativo = False
        self.hora_corrente = -1
        self._soc_atual = 0.0
        self._estado_bess = "repouso"
        self.btn_fechar_evento.setEnabled(False)
        self.lbl_evento.setText("Nenhum evento ativo.")
        self.progresso.setValue(0)
        self.lista_log.clear()

        self._bloquear_controles(False)
        self.lbl_status.setText(
            "Reiniciado — circuito recompilado (SoC inicial, Dia 1).")
        self._atualizar_relogio()
        self._atualizar_cartoes()
        self._atualizar_graficos()

    def _ao_passo_concluido(self, hora: int, dado: Dict[str, Any]):
        self._instante_ultimo_passo = time.monotonic()
        self.hora_corrente = hora
        self.dia_corrente = dado.get("dia", self.dia_corrente)

        self.series["vmin"][hora] = dado["vmin"]
        self.series["vmax"][hora] = dado["vmax"]
        self.series["perdas"][hora] = dado["perdas_kw"]
        self.series["kw_fonte"][hora] = (
            dado["kw_comprada"] - dado["kw_exportada"])
        self.series["nuvens"][hora] = dado.get("fator_nuvens")

        for nome, soc in dado["soc_depois"].items():
            self.series_soc.setdefault(nome, [None] * HORAS_POR_DIA)[hora] = \
                soc * 100.0

        self.tensoes_correntes = dado["tensoes"]
        self._atualizar_estado_bateria(dado)
        self.progresso.setValue(hora)

        self._atualizar_relogio()
        self._atualizar_cartoes(dado)
        self._atualizar_graficos()

    def _atualizar_estado_bateria(self, dado: Dict[str, Any]):
        socs = list(dado["soc_depois"].values())
        self._soc_atual = (sum(socs) / len(socs) * 100.0) if socs else 0.0

        estados = [v["estado"] for v in dado["estados_aplicados"].values()]
        if "discharging" in estados:
            self._estado_bess = "descarregando"
        elif "charging" in estados:
            self._estado_bess = "carregando"
        elif estados:
            self._estado_bess = "repouso"
        else:
            self._estado_bess = "sem bess"

    def _ao_erro_passos(self, titulo: str, mensagem: str):
        """Erro do caminho do relógio/passo: SEM modal (TRANSPARÊNCIA 6)."""
        self._parar_play()
        self.lbl_status.setText(f"{titulo}: {mensagem}")
        self._registrar_log(f"ERRO · {titulo}: {mensagem}")

    def _ao_erro_carga(self, mensagem: str):
        """Erro de carga pode ser modal: está fora do caminho do relógio.

        Carregar acontece uma vez, antes de a simulação rodar, e o usuário
        precisa ver a causa. Passo e afundamento, ao contrário, só vão para
        a barra de status — ver TRANSPARÊNCIA TÉCNICA item 6.
        """
        self._parar_play()
        self._bloquear_controles(True)
        self.lbl_status.setText(f"Falha ao preparar a simulação: {mensagem}")
        QMessageBox.critical(
            self, "Erro", f"Falha ao preparar a simulação:\n\n{mensagem}")

    # ---------------------------------------------------------------- #
    # Atualização de textos
    # ---------------------------------------------------------------- #
    def _atualizar_relogio(self):
        meta = self.meta or {}
        dias = meta.get("dias_da_semana", DIAS_DA_SEMANA)
        self.lbl_dia.setText(
            f"Dia {self.dia_corrente + 1} · "
            f"{dias[self.dia_corrente % len(dias)]}")
        if self.hora_corrente >= 0:
            self.lbl_relogio.setText(f"{self.hora_corrente:02d}:00")
        else:
            self.lbl_relogio.setText("--:00")

        if self.hora_corrente >= 0 and self.sessao is not None:
            ponta = (self.sessao.horario_ponta_inicio
                     <= self.hora_corrente
                     < self.sessao.horario_ponta_fim)
            self.lbl_ponta.setText("PONTA" if ponta else "fora ponta")
            self.lbl_ponta.setStyleSheet(
                f"font-size:11px; font-weight:600; "
                f"color:{COR_DESCARGA if ponta else '#5a5a5a'};")
        else:
            self.lbl_ponta.setText("")

    def _atualizar_cartoes(self, dado: Optional[Dict[str, Any]] = None):
        meta = self.meta or {}

        # ---------------- Bateria ---------------- #
        if not self.controlar:
            self.cartao_bateria.definir("—", "Sem BESS no projeto.", COR_REPOUSO)
            self.barra_soc.setValue(0)
        else:
            cores = {"carregando": COR_CARGA, "descarregando": COR_DESCARGA,
                     "repouso": COR_REPOUSO, "sem bess": COR_REPOUSO}
            rotulos = {"carregando": "CARREGANDO", "descarregando": "DESCARREGANDO",
                       "repouso": "REPOUSO", "sem bess": "SEM BESS"}
            self.barra_soc.setValue(int(round(self._soc_atual)))
            detalhe = f"{rotulos[self._estado_bess]}"
            detalhe += f" · faixa {SOC_MIN * 100:.0f}–{SOC_MAX * 100:.0f}%"
            if dado is not None:
                carga = dado.get("carga_kwh", 0.0)
                descarga = dado.get("descarga_kwh", 0.0)
                if descarga:
                    detalhe += f" · −{descarga:.0f} kWh no passo"
                elif carga:
                    detalhe += f" · +{carga:.0f} kWh no passo"
            self.cartao_bateria.definir(
                f"{self._soc_atual:.1f}%", detalhe,
                cores[self._estado_bess])

        # ---------------- Economia ---------------- #
        economia_dia = self.sessao.economia_dia if self.sessao else 0.0
        economia_total = self.sessao.economia_total if self.sessao else 0.0
        if self.controlar:
            self.cartao_economia.definir(
                _formatar_reais(economia_total),
                f"no dia: {_formatar_reais(economia_dia)} · arbitragem do BESS "
                f"(sem demanda nem perdas)")
        else:
            self.cartao_economia.definir(
                _formatar_reais(0.0), "Sem BESS — não há arbitragem a "
                "contabilizar.", COR_REPOUSO)

        # ---------------- Rede ---------------- #
        if dado is not None:
            vmin = dado["vmin"]
            vmax = dado["vmax"]
            texto_v = (f"{vmin:.3f}" if vmin is not None else "—")
            vmax_texto = (f"{vmax:.3f}" if vmax is not None else "—")
            detalhe = (f"Vmin {texto_v} pu · Vmax {vmax_texto} pu · "
                       f"perdas {dado['perdas_kw']:.1f} kW · ")
            fonte_kw = dado["kw_comprada"] - dado["kw_exportada"]
            detalhe += f"fonte {fonte_kw:+.1f} kW"
            if self.barras_em_sag:
                detalhe += f" · {len(self.barras_em_sag)} barra(s) em sag"
            cor = ACCENT
            if vmin is not None:
                cor = _cor_por_tensao(vmin)
            self.cartao_rede.definir(texto_v + " pu", detalhe, cor)
        else:
            self.cartao_rede.definir("—", "aguardando o primeiro passo",
                                     COR_REPOUSO)

        # ---------------- Clima ---------------- #
        indice = self.sessao.indice_nuvens if self.sessao else 100
        if meta.get("possui_pv"):
            detalhe = f"índice {indice}% · "
            detalhe += ("cobertura variável" if self.chk_cobertura.isChecked()
                        else "cobertura fixa")
            nomes = ", ".join(meta.get("nomes_pv", [])[:3])
            detalhe += f" · PV: {nomes}"
            self.cartao_clima.definir(f"{indice}%", detalhe)
        else:
            self.cartao_clima.definir(
                "—", "Sem geração fotovoltaica no projeto — o controle "
                "de nuvens fica inerte.", COR_REPOUSO)

    def _registrar_log(self, texto: str):
        self.lista_log.addItem(texto)
        self.lista_log.scrollToBottom()

    # ---------------------------------------------------------------- #
    # Controles
    # ---------------------------------------------------------------- #
    def _bloquear_controles(self, bloquear: bool):
        for w in (self.btn_play, self.btn_passo, self.btn_reiniciar,
                  self.btn_exportar,
                  self.btn_aplicar_falta, self.combo_barra_falta,
                  self.combo_tipo_falta, self.slider_nuvens,
                  self.chk_cobertura, self.combo_tarifa):
            w.setEnabled(not bloquear)
        if bloquear:
            self.btn_fechar_evento.setEnabled(False)
        else:
            self.btn_fechar_evento.setEnabled(self._evento_ativo)

    def _alternar_play(self):
        if self._play_ativo:
            self._parar_play()
            return
        if self.hora_corrente >= HORAS_POR_DIA - 1 and not self._evento_ativo:
            # Dia já concluído: retomar o play significa virar o dia.
            self._virar_dia()
        self._play_ativo = True
        self.btn_play.setText("⏸  Pausar")
        self.timer_play.setInterval(
            int(self.combo_velocidade.currentData()
                or INTERVALO_VELOCIDADE_PADRAO_MS))
        self.timer_play.start()
        self.timer_animacao.start()
        self._ao_timer_play()  # não espera o primeiro intervalo

    def _parar_play(self):
        self._play_ativo = False
        self.btn_play.setText("▶  Reproduzir")
        self.timer_play.stop()
        self.timer_animacao.stop()

    def _ao_timer_play(self):
        if self.sessao is None or not self.thread_viva:
            return
        if self._evento_ativo:
            # O relógio pausa enquanto um afundamento está exibido: o
            # mapa e os cartões mostram o evento, e avançar o passo o
            # sobrescreveria.
            self._parar_play()
            return
        if self.hora_corrente >= HORAS_POR_DIA - 1:
            self._virar_dia()
            return
        self._passo_unico()

    def _passo_unico(self):
        if self.sessao is None or not self.thread_viva:
            return
        if self._evento_ativo:
            self.lbl_status.setText(
                "Feche o evento de afundamento antes de avançar.")
            return
        proxima = self.hora_corrente + 1
        if proxima > HORAS_POR_DIA - 1:
            return
        if self.fila_trabalho.qsize() > 0:
            # Passo anterior ainda não consumido pela thread de trabalho;
            # enfileirar outro só acumularia atraso.
            return
        self.lbl_status.setText(f"Resolvendo hora {proxima:02d}:00…")

        # Resolve na thread da UI, de forma síncrona. O passo precisa ser
        # síncrono para o relógio encadear horas sem esperar a fila; o motor
        # é exclusivo desta thread enquanto a janela existir.
        try:
            dado = self.sessao.executar_passo(proxima)
        # Sem modal aqui: um diálogo travaria a UI em modo offscreen, onde
        # ninguém clica "OK" (TRANSPARÊNCIA TÉCNICA, item 6).
        except Exception as e:  # noqa: BLE001 - reportado na UI, sem modal
            self._ao_erro_passos(f"Falha no passo da hora {proxima}", str(e))
            return
        self._ao_passo_concluido(proxima, dado)

    def _coletar_snapshot(self) -> Dict[str, Any]:
        """Pedir o snapshot à thread de trabalho e aguardar (QEventLoop).

        O motor é acessado exclusivamente pela thread de trabalho
        (TRANSPARÊNCIA 5) — a UI só conversa por filas. O QEventLoop
        processa timers, então o _drenar_fila (QTimer de 100 ms) roda
        dentro dele e devolve o resultado. Segurança: 10 s.
        """
        self._resultado_snapshot = None
        self._erro_snapshot = None
        self.fila_trabalho.put(("snapshot", -1))
        loop = QEventLoop()
        QTimer.singleShot(10000, loop.quit)

        def _checar():
            if (self._resultado_snapshot is not None
                    or self._erro_snapshot is not None):
                loop.quit()

        timer_checagem = QTimer(self)
        timer_checagem.timeout.connect(_checar)
        timer_checagem.start(50)
        try:
            loop.exec()
        finally:
            timer_checagem.stop()
        if self._erro_snapshot is not None:
            raise RuntimeError(self._erro_snapshot)
        if self._resultado_snapshot is None:
            raise RuntimeError("Tempo esgotado coletando os dados da sessão.")
        return self._resultado_snapshot

    def _abrir_exportacao(self):
        """Abre o diálogo de exportação e grava os gráficos escolhidos.

        Está FORA do caminho do relógio — aqui o modal é aceitável
        (TRANSPARÊNCIA 6); ainda assim, recomenda-se pausar antes.
        """
        if self.sessao is None:
            QMessageBox.information(
                self, "Aviso",
                "A simulação ainda não foi preparada — nada para exportar.")
            return
        try:
            snapshot = self._coletar_snapshot()
        except Exception as e:  # noqa: BLE001 - reportado na UI
            QMessageBox.critical(
                self, "Erro",
                f"Não foi possível coletar os dados da sessão:\n{e}")
            return
        dialogo = ExportarGraficosDialog(self, snapshot)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            caminhos, avisos = exportar_graficos(
                snapshot, dialogo.config_exportacao)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(
                self, "Erro na exportação", f"Não foi possível exportar:\n{e}")
            return
        texto = "Gráficos gravados:\n\n" + "\n".join(caminhos)
        if avisos:
            texto += "\n\nAvisos:\n" + "\n".join(avisos)
        self._registrar_log(f"Exportação: {len(caminhos)} arquivo(s) gravados.")
        QMessageBox.information(self, "Exportação concluída", texto)

    def _virar_dia(self, forcar: bool = False):
        if self.sessao is None:
            return
        # Guarda de coerência: o motor recusa avancar_dia() fora da hora 23
        # (o histórico do dia ficaria incompleto). `forcar` existe para o
        # teste offscreen, que não tem 24 passos de paciência — em uso
        # normal quem chama é o timer, sempre na hora 23.
        if not forcar and self.hora_corrente < HORAS_POR_DIA - 1:
            return
        try:
            info = self.sessao.avancar_dia()
        except Exception as e:  # noqa: BLE001 - reportado na UI, sem modal
            self._ao_erro_passos("Falha ao virar o dia", str(e))
            self._parar_play()
            return

        self.dia_corrente = info["dia"]
        self.hora_corrente = -1
        self.series = self._series_vazias()
        for nome in list(self.series_soc):
            self.series_soc[nome] = [None] * HORAS_POR_DIA
        self.tensoes_correntes = {}
        self.barras_em_sag = []
        self.tensoes_evento = {}
        self._evento_ativo = False
        self.btn_fechar_evento.setEnabled(False)
        self.lbl_evento.setText("Nenhum evento ativo.")
        self.progresso.setValue(0)

        self._registrar_log(
            f"{info['rotulo_dia']} iniciado · fator de carga "
            f"{info['fator_carga']:.2f} · dia anterior fechou com "
            f"{_formatar_reais(info['economia_dia_encerrado'])}")
        self.lbl_status.setText(
            f"{info['rotulo_dia']} — gráficos reiniciados; SoC e economia "
            f"acumulada preservados.")
        self._atualizar_relogio()
        self._atualizar_cartoes(dado)
        self._reiniciar_animacao()

    def _ao_mudar_velocidade(self):
        ms = self.combo_velocidade.currentData()
        if ms:
            self.timer_play.setInterval(int(ms))

    def _reiniciar_animacao(self):
        """Recomeça a animação do último segmento (traço fluido).

        Chama o redesenho imediato e arma o timer de animação: nos
        próximos ~35% do intervalo do relógio o segmento h-1→h se desenha
        progressivamente (easing), em vez de saltar pronto.
        """
        self._atualizar_graficos(1.0)
        self.timer_animacao.start()

    def _tick_animacao(self):
        if self.sessao is None:
            self.timer_animacao.stop()
            return
        decorrido_ms = ((time.monotonic() - self._instante_ultimo_passo)
                        * 1000.0)
        intervalo = int(self.combo_velocidade.currentData()
                        or INTERVALO_VELOCIDADE_PADRAO_MS)
        fracao = decorrido_ms / max(1.0, FRACAO_TRACO * intervalo)
        if fracao >= 1.0:
            self.timer_animacao.stop()
            self._atualizar_graficos(1.0, atualizar_mapa=False)
            return
        fracao_visual = 1.0 - (1.0 - fracao) ** 2  # ease-out
        self._atualizar_graficos(fracao_visual, atualizar_mapa=False)

    def _plot_serie_fluida(self, ax, valores, cor, label, fracao_traco,
                           marcador="o"):
        """Desenha a série com o último segmento interpolado.

        Pontos 0..h-1 completos (com marcadores nos horários resolvidos);
        o segmento h-1→h desenha até a fração corrente; o marcador do
        ponto h só aparece quando o segmento fecha (fracao = 1).
        """
        h = self.hora_corrente
        if h < 0:
            return
        xs_completos = [x for x in range(h) if valores[x] is not None]
        ys_completos = [valores[x] for x in xs_completos]
        if xs_completos:
            ax.plot(xs_completos, ys_completos, color=cor,
                    linewidth=1.2, marker=marcador, markersize=2.5,
                    label=label)
        if (h < HORAS_POR_DIA and valores[h] is not None
                and valores[h - 1] is not None and h >= 1):
            fr = max(0.0, min(1.0, fracao_traco))
            x_fim = (h - 1) + fr
            y_fim = valores[h - 1] + (valores[h] - valores[h - 1]) * fr
            ax.plot([h - 1, x_fim], [valores[h - 1], y_fim], color=cor,
                    linewidth=1.2)
            if fr >= 1.0:
                ax.plot([h], [valores[h]], marker=marcador, markersize=2.5,
                        color=cor)
        elif h == 0 and valores[0] is not None and fracao_traco >= 1.0:
            ax.plot([0], [valores[0]], marker=marcador, markersize=2.5,
                    color=cor)

    def _reiniciar(self):
        self._parar_play()
        if self.sessao is None:
            self._iniciar_carregamento()
            return
        self._bloquear_controles(True)
        self.lbl_status.setText("Reiniciando — recompilando o circuito…")
        # A recompilação precisa acontecer na thread de trabalho.
        self.fila_trabalho.put(("reiniciar", -1))

    def _ao_mudar_nuvens(self, valor: int):
        if self.sessao is not None:
            self.sessao.definir_nuvens(
                valor, self.chk_cobertura.isChecked())
        self._atualizar_cartoes()

    def _ao_alternar_cobertura(self, ativo: bool):
        if self.sessao is not None:
            self.sessao.definir_nuvens(
                self.sessao.indice_nuvens, ativo)
        self._atualizar_cartoes()

    def _ao_mudar_fatores(self):
        if self.sessao is None:
            return
        self.sessao.definir_fatores_carga(
            [s.value() for s in self.spins_fator])
        self.lbl_status.setText(
            "Fatores de carga atualizados — valem a partir do próximo dia.")

    def _ao_mudar_tarifa(self):
        if self.sessao is None:
            return
        chave = self.combo_tarifa.currentData()
        if not chave:
            return
        if self.sessao.definir_tarifa(chave):
            tarifa = obter_tarifa(chave)
            self._registrar_log(
                f"Tarifa alterada para {tarifa.nome} — "
                f"{_formatar_reais(tarifa.tarifa_ponta_kwh)}/kWh ponta, "
                f"{_formatar_reais(tarifa.tarifa_fora_ponta_kwh)}/kWh fora "
                f"(acumulados não são reescritos)")
        self._atualizar_cartoes()

    # ---------------------------------------------------------------- #
    # Afundamento
    # ---------------------------------------------------------------- #
    def _aplicar_falta(self):
        if self.sessao is None:
            return
        if self.hora_corrente < 0:
            self.lbl_status.setText(
                "Execute pelo menos um passo antes de aplicar uma falta.")
            return
        barra = self.combo_barra_falta.currentText()
        tipo = self.combo_tipo_falta.currentData()
        if not barra or not tipo:
            return

        # Pausa o relógio: o mapa e os cartões passam a mostrar o evento.
        self._parar_play()
        self.lbl_status.setText(
            f"Simulando falta {tipo} na barra {barra} em contexto isolado…")
        try:
            evento = self.sessao.simular_afundamento(barra, tipo)
        except Exception as e:  # noqa: BLE001 - sem modal (TRANSPARÊNCIA 6)
            self._ao_erro_passos("Falha ao simular o afundamento", str(e))
            return

        self._evento_ativo = True
        self.btn_fechar_evento.setEnabled(True)
        self.barras_em_sag = list(evento["barras_em_sag"])
        self.tensoes_evento = dict(evento.get("tensoes", {}))

        texto = (f"{evento['rotulo_dia']} · {evento['hora']:02d}:00 · "
                 f"falta {evento['tipo_rotulo']} na barra {evento['bus']} · "
                 f"Vmin {evento['vmin']:.3f} pu · "
                 f"{len(self.barras_em_sag)} barra(s) em afundamento")
        self.lbl_evento.setText(texto)
        self._registrar_log(
            f"{evento['rotulo_dia']} · {evento['hora']:02d}:00 · falta "
            f"{evento['tipo_rotulo'].split(' (')[0].lower()} na barra "
            f"{evento['bus']} · Vmin {evento['vmin']:.3f} pu · "
            f"{len(self.barras_em_sag)} barra(s) em afundamento")
        for aviso in evento.get("avisos", []):
            self._registrar_log(f"AVISO · {aviso}")
        self.lbl_status.setText(
            "Evento exibido — o passo ao vivo NÃO foi alterado. "
            "'Fechar evento' restaura o mapa e retoma o relógio pausado.")
        self._atualizar_cartoes()
        self._atualizar_graficos()

    def _fechar_evento(self):
        if self.sessao is not None:
            self.sessao.fechar_evento_afundamento()
        self._evento_ativo = False
        self.btn_fechar_evento.setEnabled(False)
        self.barras_em_sag = []
        self.tensoes_evento = {}
        self.lbl_evento.setText("Nenhum evento ativo.")
        self.lbl_status.setText(
            f"Evento fechado — de volta ao passo ao vivo "
            f"({self.hora_corrente:02d}:00).")
        self._atualizar_cartoes()
        self._atualizar_graficos()

    # ---------------------------------------------------------------- #
    # Desenho
    # ---------------------------------------------------------------- #
    def _desenhar_topo_estatico(self):
        """Traça linhas/transformadores uma única vez."""
        self.ax_mapa.clear()
        self.ax_mapa.set_aspect("equal", adjustable="datalim")
        self.ax_mapa.set_xticks([])
        self.ax_mapa.set_yticks([])
        self.ax_mapa.set_title("Mapa da rede — tensão do passo corrente (pu)")

        for bus1, bus2, e_chave in self.linhas:
            p1 = self.posicionadas.get(bus1)
            p2 = self.posicionadas.get(bus2)
            if p1 is None or p2 is None:
                continue
            self.ax_mapa.plot(
                [p1[0], p2[0]], [p1[1], p2[1]],
                color="#555555",
                linestyle="--" if e_chave else "-",
                linewidth=0.9 if e_chave else 1.1,
                zorder=1)

        for bus1, bus2, e_regulador in self.transformadores:
            p1 = self.posicionadas.get(bus1)
            p2 = self.posicionadas.get(bus2)
            if p1 is None or p2 is None:
                continue
            self.ax_mapa.plot(
                [p1[0], p2[0]], [p1[1], p2[1]],
                color="#1b5e20",
                linestyle="--" if e_regulador else "-",
                linewidth=1.6,
                zorder=1)

        self.nos_mapa: Dict[str, Any] = {}
        for barra, (x, y) in self.posicionadas.items():
            (ponto,) = self.ax_mapa.plot(
                [x], [y], marker="o", markersize=7,
                color=_cor_por_tensao(None), zorder=3,
                markeredgecolor="#222", markeredgewidth=0.4)
            self.nos_mapa[barra] = ponto
            self.ax_mapa.annotate(
                barra, (x, y), textcoords="offset points", xytext=(4, 4),
                fontsize=6, color="#222", zorder=4)

        legenda = [
            Line2D([], [], color=COR_BOM, marker="o", linestyle="",
                   markersize=7, label=f"≥ {LIMIAR_TENSAO_BOM:.2f} pu"),
            Line2D([], [], color=COR_ACEITAVEL, marker="o", linestyle="",
                   markersize=7,
                   label=f"{LIMIAR_TENSAO_ACEITAVEL:.2f}–"
                         f"{LIMIAR_TENSAO_BOM:.2f} pu"),
            Line2D([], [], color=COR_RUIM, marker="o", linestyle="",
                   markersize=7, label=f"< {LIMIAR_TENSAO_ACEITAVEL:.2f} pu"),
        ]
        self.ax_mapa.legend(handles=legenda, loc="upper right", fontsize=7,
                            title="Verde/amarelo/vermelho =\nauxílio visual,"
                                  "\nnão norma",
                            title_fontsize=6)

        if self.barras_sem_coordenada:
            self.ax_mapa.text(
                0.01, -0.02,
                f"{len(self.barras_sem_coordenada)} barra(s) sem coordenada "
                "Buscoords — posição arbitrária (anel externo).",
                transform=self.ax_mapa.transAxes, fontsize=6, color="#b35c00")

    def _atualizar_mapa(self):
        fonte = self.tensoes_evento if self._evento_ativo else \
            self.tensoes_correntes
        sag = set(self.barras_em_sag) if self._evento_ativo else set()

        for barra, ponto in getattr(self, "nos_mapa", {}).items():
            if barra in sag:
                ponto.set_color(COR_RUIM)
                ponto.set_markersize(11)
                continue
            v = fonte.get(barra)
            ponto.set_color(_cor_por_tensao(v))
            if v is not None and (v < LIMIAR_TENSAO_ACEITAVEL or v >= 1.05):
                ponto.set_markersize(10)
            else:
                ponto.set_markersize(7)

        titulo = "Mapa da rede — tensão do passo corrente (pu)"
        if self._evento_ativo:
            titulo = ("Mapa da rede — AFUNDAMENTO exibido "
                      "(contexto isolado; passo ao vivo intacto)")
        self.ax_mapa.set_title(titulo, fontsize=9,
                              color=COR_RUIM if self._evento_ativo else "#222")

    def _atualizar_graficos(self, fracao_traco: float = 1.0,
                            atualizar_mapa: bool = True):
        titulo_dia = self.lbl_dia.text()

        # ---------------- tensão ---------------- #
        self.ax_tensao.clear()
        self.ax_tensao.set_ylabel("Tensão (pu)", fontsize=8)
        self.ax_tensao.set_title(f"Vmin / Vmax por hora — {titulo_dia}",
                                 fontsize=8)
        self.ax_tensao.set_xlim(-0.5, HORAS_POR_DIA - 0.5)
        self.ax_tensao.set_xticks(range(0, HORAS_POR_DIA, 3))
        self.ax_tensao.grid(True, alpha=0.25, linewidth=0.6)
        self.ax_tensao.axhline(LIMIAR_TENSAO_ACEITAVEL, color=COR_RUIM,
                               linestyle="--", linewidth=0.8, alpha=0.7)
        self.ax_tensao.axhline(1.05, color="#666", linestyle="--",
                               linewidth=0.8, alpha=0.7)
        self._plot_serie_fluida(self.ax_tensao, self.series["vmax"],
                                ACCENT, "Vmax", fracao_traco)
        self._plot_serie_fluida(self.ax_tensao, self.series["vmin"],
                                COR_RUIM, "Vmin", fracao_traco)
        self.ax_tensao.legend(fontsize=6, loc="lower right")

        # ---------------- SoC ---------------- #
        self.ax_soc.clear()
        self.ax_soc.set_ylabel("SoC (%)", fontsize=8)
        self.ax_soc.set_title("Estado de carga", fontsize=8)
        self.ax_soc.set_xlim(-0.5, HORAS_POR_DIA - 0.5)
        self.ax_soc.set_xticks(range(0, HORAS_POR_DIA, 3))
        self.ax_soc.grid(True, alpha=0.25, linewidth=0.6)
        self.ax_soc.axhline(SOC_MIN * 100, color=COR_RUIM, linestyle=":",
                            linewidth=0.8, alpha=0.7)
        self.ax_soc.axhline(SOC_MAX * 100, color="#666", linestyle=":",
                            linewidth=0.8, alpha=0.7)
        self.ax_soc.set_ylim(-5, 105)
        paleta = ["#004587", "#1b8f3a", "#b35c00", "#7b1fa2", "#00838f"]
        for i, (nome, valores) in enumerate(self.series_soc.items()):
            self._plot_serie_fluida(self.ax_soc, valores,
                                    paleta[i % len(paleta)], nome,
                                    fracao_traco)
        if self.series_soc:
            self.ax_soc.legend(fontsize=5, loc="lower left", ncol=2)

        # ---------------- potência e perdas ---------------- #
        self.ax_pot.clear()
        self.ax_pot.set_ylabel("kW", fontsize=8)
        self.ax_pot.set_xlabel("hora", fontsize=8)
        self.ax_pot.set_title("Fonte e perdas", fontsize=8)
        self.ax_pot.set_xlim(-0.5, HORAS_POR_DIA - 0.5)
        self.ax_pot.set_xticks(range(0, HORAS_POR_DIA, 3))
        self.ax_pot.grid(True, alpha=0.25, linewidth=0.6)
        self.ax_pot.axhline(0, color="#333", linewidth=0.7)
        self._plot_serie_fluida(self.ax_pot, self.series["kw_fonte"],
                                ACCENT, "Fonte (compra + / exportação −)",
                                fracao_traco)

        # Perdas em eixo secundário: escala 1-2 ordens menor que a potência
        # da fonte; sobrepor no mesmo eixo as esconderia na base.
        self.ax_perdas.clear()
        self.ax_perdas.set_ylabel("Perdas (kW)", fontsize=7, color="#b35c00")
        self.ax_perdas.tick_params(axis="y", labelsize=6, colors="#b35c00")
        self._plot_serie_fluida(self.ax_perdas, self.series["perdas"],
                                "#b35c00", "Perdas", fracao_traco,
                                marcador="s")

        if self.hora_corrente >= 0:
            x_cursor = (self.hora_corrente if fracao_traco >= 1.0
                        else max(0.0, self.hora_corrente - 1 + fracao_traco))
        else:
            x_cursor = 0
        for ax in (self.ax_tensao, self.ax_soc, self.ax_pot):
            ax.axvline(x_cursor, color=ACCENT, linewidth=1.2,
                       alpha=0.9, linestyle="-")

        if atualizar_mapa:
            self._atualizar_mapa()
        self.figura.canvas.draw_idle()

    # ---------------------------------------------------------------- #
    def closeEvent(self, evento):
        self._parar_play()
        self.timer_fila.stop()
        if self.thread_viva:
            self.fila_trabalho.put(("encerrar", -1))
            if self.thread_trabalho is not None:
                self.thread_trabalho.join(timeout=5.0)
            self.thread_viva = False
        super().closeEvent(evento)


class ExportarGraficosDialog(QDialog):
    """Seleção dos gráficos/dias/estilo para exportação (modal)."""

    def __init__(self, parent, snapshot: Dict[str, Any]):
        super().__init__(parent)
        self.snapshot = snapshot
        self.config_exportacao: Dict[str, Any] = {}
        self.setWindowTitle("Exportar gráficos da Simulação ao Vivo")
        self.setModal(True)
        self.resize(620, 620)
        dias_com_dados = snapshot.get("meta", {}).get(
            "dias_com_dados", [])
        nomes_dias = snapshot.get("meta", {}).get(
            "dias_da_semana", DIAS_DA_SEMANA)

        layout = QVBoxLayout(self)

        caixa_graficos = QGroupBox("Gráficos (selecione os desejados)")
        grade_graficos = QVBoxLayout(caixa_graficos)
        self.chk_graficos: Dict[str, QCheckBox] = {}
        for chave, rotulo in CHAVES_GRAFICOS.items():
            chk = QCheckBox(rotulo)
            chk.setChecked(chave == "bess_controlador")
            self.chk_graficos[chave] = chk
            grade_graficos.addWidget(chk)
        layout.addWidget(caixa_graficos)

        caixa_dias = QGroupBox("Dias (apenas os já simulados)")
        coluna_dias = QVBoxLayout(caixa_dias)
        self.chk_todos = QCheckBox("Todos os dias simulados")
        coluna_dias.addWidget(self.chk_todos)
        self.chk_dias: Dict[int, QCheckBox] = {}
        for dia in dias_com_dados:
            chk = QCheckBox(
                f"Dia {dia + 1} · {nomes_dias[dia % len(nomes_dias)]}")
            self.chk_dias[dia] = chk
            coluna_dias.addWidget(chk)
        if not dias_com_dados:
            coluna_dias.addWidget(QLabel(
                "Nenhum passo executado ainda — rode a simulação "
                "primeiro."))
        self.chk_todos.toggled.connect(self._ao_mudar_todos)
        layout.addWidget(caixa_dias)

        caixa_estilo = QGroupBox("Estilo e formato")
        grade_estilo = QVBoxLayout(caixa_estilo)
        linha_estilo = QHBoxLayout()
        linha_estilo.addWidget(QLabel("Estilo:"))
        self.combo_estilo = QComboBox()
        self.combo_estilo.addItem("Padrão da ferramenta", "padrao")
        self.combo_estilo.addItem(
            "Artigo (Okabe-Ito) — paleta e marcadores do TCC", "artigo")
        self.combo_estilo.setToolTip(
            "O estilo 'Artigo' reproduz as figuras do TCC: uma cor e um "
            "marcador por dia da semana, marcas a cada 2 h e curvas "
            "semanais só de pontos.")
        linha_estilo.addWidget(self.combo_estilo, 1)
        grade_estilo.addLayout(linha_estilo)
        linha_linha = QHBoxLayout()
        linha_linha.addWidget(QLabel("Espessura das linhas:"))
        self.spin_espessura = QDoubleSpinBox()
        self.spin_espessura.setRange(0.5, 5.0)
        self.spin_espessura.setSingleStep(0.2)
        self.spin_espessura.setValue(1.4)
        linha_linha.addWidget(self.spin_espessura)
        linha_linha.addStretch(1)
        grade_estilo.addLayout(linha_linha)
        linha_fundo = QHBoxLayout()
        linha_fundo.addWidget(QLabel("Fundo:"))
        self.combo_fundo = QComboBox()
        self.combo_fundo.addItem("Branco", "branco")
        self.combo_fundo.addItem("Transparente (sem fundo)", "transparente")
        self.combo_fundo.addItem("Escuro", "escuro")
        linha_fundo.addWidget(self.combo_fundo)
        linha_fundo.addWidget(QLabel("Formato:"))
        self.combo_formato = QComboBox()
        self.combo_formato.addItem("PNG", "png")
        self.combo_formato.addItem("JPEG", "jpeg")
        self.combo_formato.addItem("SVG", "svg")
        linha_fundo.addWidget(self.combo_formato)
        linha_fundo.addStretch(1)
        grade_estilo.addLayout(linha_fundo)
        self.chk_por_dia = QCheckBox(
            "Um arquivo por dia (senão: um único arquivo por gráfico, "
            "com separadores)")
        self.chk_por_dia.setChecked(True)
        grade_estilo.addWidget(self.chk_por_dia)
        layout.addWidget(caixa_estilo)

        caixa_destino = QGroupBox("Destino")
        coluna_destino = QVBoxLayout(caixa_destino)
        linha_pasta = QHBoxLayout()
        self.edit_pasta = QLineEdit()
        self.edit_pasta.setPlaceholderText("Escolha a pasta de destino…")
        linha_pasta.addWidget(self.edit_pasta, 1)
        botao_pasta = QPushButton("Procurar…")
        botao_pasta.clicked.connect(self._escolher_pasta)
        linha_pasta.addWidget(botao_pasta)
        coluna_destino.addLayout(linha_pasta)
        linha_prefixo = QHBoxLayout()
        linha_prefixo.addWidget(QLabel("Prefixo dos arquivos:"))
        self.edit_prefixo = QLineEdit("ao_vivo")
        linha_prefixo.addWidget(self.edit_prefixo, 1)
        coluna_destino.addLayout(linha_prefixo)
        layout.addWidget(caixa_destino)

        dica = QLabel("Dica: pause a simulação antes de exportar para um "
                      "retrato estável. Os eventos interativos (nuvens, "
                      "afundamentos) aparecem marcados nos gráficos.")
        dica.setWordWrap(True)
        dica.setStyleSheet(
            "color: gray; font-style: italic; font-size: 9pt;")
        layout.addWidget(dica)

        rodape = QHBoxLayout()
        rodape.addStretch(1)
        botao_cancelar = QPushButton("Cancelar")
        botao_cancelar.clicked.connect(self.reject)
        botao_exportar = QPushButton("📤 Exportar")
        botao_exportar.clicked.connect(self._confirmar)
        rodape.addWidget(botao_cancelar)
        rodape.addWidget(botao_exportar)
        layout.addLayout(rodape)

    def _ao_mudar_todos(self, marcado: bool):
        for chk in self.chk_dias.values():
            if chk.isEnabled():
                chk.setChecked(marcado)

    def _escolher_pasta(self):
        caminho = QFileDialog.getExistingDirectory(self, "Pasta de destino")
        if caminho:
            self.edit_pasta.setText(caminho)

    def _confirmar(self):
        graficos = [chave for chave, chk in self.chk_graficos.items()
                    if chk.isChecked()]
        dias = [dia for dia, chk in self.chk_dias.items()
                if chk.isChecked()]
        pasta = self.edit_pasta.text().strip()
        if not graficos or not dias or not pasta:
            QMessageBox.warning(
                self, "Aviso",
                "Selecione ao menos um gráfico, um dia e a pasta de "
                "destino.")
            return
        self.config_exportacao = {
            "graficos": graficos,
            "dias": sorted(dias),
            "espessura": float(self.spin_espessura.value()),
            "fundo": self.combo_fundo.currentData(),
            "formato": self.combo_formato.currentData(),
            "por_dia": self.chk_por_dia.isChecked(),
            "estilo": self.combo_estilo.currentData(),
            "pasta": pasta,
            "prefixo": self.edit_prefixo.text().strip() or "ao_vivo",
        }
        self.accept()


def abrir_simulacao_ao_vivo(projeto: Projeto):
    """Ponto de entrada chamado pelo lançador do módulo."""
    janela = JanelaSimulacaoAoVivo(projeto)
    janela.show()
    return janela
