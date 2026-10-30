__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Editor gráfico de Curvas Características (LoadShape do OpenDSS) — PySide6.

TRANSPARÊNCIA TÉCNICA (migração Tkinter → PySide6):

- Este módulo era um `tk.Toplevel` modal. Agora é um `QDialog` modal
  (`setModal(True)` + `exec()`), preservando exatamente o MESMO contrato
  público de `abrir_editor_curva(parent, pasta_curvas, natureza, modo,
  nome_inicial=None)`, que continua retornando o nome da curva salva ou
  None se o usuário cancelar.

- Mapeamento de widgets aplicado (equivalência 1:1, sem mudança de
  comportamento):
    tk.Toplevel          → QDialog
    ttk.Combobox (readonly) → QComboBox (setEditable(False))
    tk.Listbox           → QListWidget (selectionMode = SingleSelection)
    tk.Spinbox           → QDoubleSpinBox
    tk.Entry             → QLineEdit
    tk.Label/Tk.Entry    → QLabel/QLineEdit
    messagebox.showwarning/showerror/showinfo → mostrar_aviso_win11
    messagebox.askyesno  → confirmar_win11
    FigureCanvasTkAgg    → FigureCanvasQTAgg (mesma Figure/Axes criados aqui;
                           mpl_connect("button_press_event") alimenta o mesmo
                           _ao_clicar_grafico, que não foi alterado)

- Matemática preservada VERBATIM: HORAS_POR_UNIDADE, OFFSET_UNIDADE,
  CONFIG_MODO, unidade_para_horas(), horas_para_unidade(), o snap do clique,
  a tolerância de remoção, a ordenação por hora e todas as conversões
  unidade↔horas. Nenhum valor de constante foi alterado.

- `os.environ.setdefault("MPLBACKEND", "QtAgg")` é aplicado ANTES de
  importar o matplotlib (e antes de qualquer figura ser criada), para que o
  backend interativo seja o do Qt e não o do Tk.

Suporta três modos, correspondentes às propriedades do OpenDSS:
    - daily  : perfil ao longo de 24 horas
    - duty   : ciclo curto, com duração total configurável (em minutos)
    - yearly : perfil sazonal, representado por dia do ano (1 a 365)

Os pontos podem ser definidos de duas formas complementares:
    1) Clicando com o mouse no gráfico (grade principal + secundária).
    2) Digitando os valores exatos em campos numéricos (QDoubleSpinBox) e
       clicando em "Adicionar / Atualizar ponto".

O snap (arredondamento) de cada clique no gráfico é configurado em
CONFIG_MODO, individualmente por modo (ex.: 5 minutos para 'daily').
"""

import os

# O backend do matplotlib precisa ser definido ANTES do import de pyplot/Figure
# para que o canvas interativo seja o do Qt (FigureCanvasQTAgg).
os.environ.setdefault("MPLBACKEND", "QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MultipleLocator, AutoMinorLocator, MaxNLocator

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from .curvas import (
    CurvaCaracteristica, listar_curvas_por_modo, obter_curva,
    salvar_nova_curva, atualizar_curva, remover_curva,
)
from .ui_win11 import confirmar_win11, mostrar_aviso_win11


# ============================================================
# Configuração de cada modo de curva (eixo X, snap, tolerâncias, etc.)
# ============================================================

CONFIG_MODO = {
    "daily": {
        "rotulo": "Diária (daily) - 24 horas",
        "eixo_x": "Hora do dia (formato decimal, ex.: 13.5 = 13h30)",
        "sufixo_unidade": " h",
        "x_min": 0.0,
        "x_max_fixo": 24.0,
        "incremento_snap": 5 / 60,      # <<< SNAP do clique no gráfico: 5 minutos
        "incremento_spinbox": 5 / 60,   # passo do spinbox: 5 minutos
        "casas_decimais": 2,
        "tolerancia_remocao": 12 / 60,  # ~12 minutos, usados no clique direito
        "permite_duracao_customizada": False,
    },
    "duty": {
        "rotulo": "Duty Cycle (ciclo curto)",
        "eixo_x": "Tempo decorrido (minutos)",
        "sufixo_unidade": " min",
        "x_min": 0.0,
        "x_max_fixo": None,  # definido dinamicamente pela duração configurada
        "incremento_snap": 1.0,
        "incremento_spinbox": 1.0,
        "casas_decimais": 1,
        "tolerancia_remocao": 3.0,
        "permite_duracao_customizada": True,
        "duracao_padrao_minutos": 60.0,
    },
    "yearly": {
        "rotulo": "Anual (yearly) - por dia do ano",
        "eixo_x": "Dia do ano (1 a 365)",
        "sufixo_unidade": " dia",
        "x_min": 1.0,
        "x_max_fixo": 365.0,
        "incremento_snap": 1.0,
        "incremento_spinbox": 1.0,
        "casas_decimais": 0,
        "tolerancia_remocao": 5.0,
        "permite_duracao_customizada": False,
    },
}

# Fator de conversão entre a unidade exibida no eixo X e HORAS (formato
# sempre usado internamente para os pontos, compatível com a propriedade
# 'hour' de um Loadshape do OpenDSS).
HORAS_POR_UNIDADE = {"daily": 1.0, "duty": 1.0 / 60.0, "yearly": 24.0}
OFFSET_UNIDADE = {"daily": 0.0, "duty": 0.0, "yearly": 1.0}  # "dia 1" = hora 0


def unidade_para_horas(modo: str, valor: float) -> float:
    return (valor - OFFSET_UNIDADE[modo]) * HORAS_POR_UNIDADE[modo]


def horas_para_unidade(modo: str, horas: float) -> float:
    return horas / HORAS_POR_UNIDADE[modo] + OFFSET_UNIDADE[modo]


class EditorCurvaDialog(QDialog):
    """Diálogo modal de edição/criação de uma Curva Característica."""

    def __init__(self, parent, pasta_curvas: str, natureza: str, modo: str,
                 nome_inicial: str = None):
        super().__init__(parent)
        self.pasta_curvas = pasta_curvas
        self.natureza = natureza  # "geracao" ou "carga"
        self.modo = modo          # "daily" | "duty" | "yearly"
        self.resultado = None
        self.pontos = []
        self.nome_atual = None
        self._hora_em_edicao = None  # rastreia o ponto selecionado p/ edição manual

        config = CONFIG_MODO[self.modo]
        rotulo_natureza = "Geração" if natureza == "geracao" else "Carga"
        self.setWindowTitle(
            f"Curva Característica - {config['rotulo']} ({rotulo_natureza})")
        self.resize(860, 740)
        self.setModal(True)

        self._montar_widgets()

        if nome_inicial:
            self._carregar_curva_por_nome(nome_inicial)
        else:
            self._redesenhar()

    # ------------------------------------------------------------------ #
    def _montar_widgets(self):
        layout_raiz = QVBoxLayout(self)

        # ---------------- topo: curva salva / nova / excluir / nome ----
        topo = QHBoxLayout()
        topo.addWidget(QLabel("Curva salva:"))

        self.combo_curvas = QComboBox()
        self.combo_curvas.setEditable(False)
        self.combo_curvas.setMinimumWidth(180)
        topo.addWidget(self.combo_curvas)
        self._atualizar_lista_combobox()
        self.combo_curvas.currentIndexChanged.connect(self._ao_selecionar_combobox)

        botao_nova = QPushButton("➕ Nova")
        botao_nova.clicked.connect(self._nova_curva)
        topo.addWidget(botao_nova)

        botao_excluir = QPushButton("🗑 Excluir")
        botao_excluir.clicked.connect(self._excluir_curva_selecionada)
        topo.addWidget(botao_excluir)

        topo.addSpacing(16)
        topo.addWidget(QLabel("Nome:"))
        self.entry_nome = QLineEdit()
        self.entry_nome.setMaximumWidth(180)
        topo.addWidget(self.entry_nome)
        topo.addStretch(1)

        layout_raiz.addLayout(topo)

        # ---------------- dica de uso ----------------------------------
        dica = QLabel(
            "Clique esquerdo no gráfico: adiciona/move um ponto. Clique direito: "
            "remove o ponto mais próximo. Você também pode digitar os valores "
            "exatos na seção abaixo do gráfico.")
        dica.setWordWrap(True)
        dica.setStyleSheet("color: gray; font-style: italic; font-size: 9pt;")
        layout_raiz.addWidget(dica)

        # ---------------- centro: gráfico + lista de pontos -------------
        frame_central = QHBoxLayout()

        self.figura = Figure(figsize=(6.4, 4.2), dpi=100)
        self.eixo = self.figura.add_subplot(111)
        self.canvas = FigureCanvasQTAgg(self.figura)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas.mpl_connect("button_press_event", self._ao_clicar_grafico)
        frame_central.addWidget(self.canvas, 1)

        painel_pontos = QVBoxLayout()
        painel_pontos.setContentsMargins(8, 0, 0, 0)

        config = CONFIG_MODO[self.modo]
        rotulo_pontos = QLabel(
            f"Pontos ({config['sufixo_unidade'].strip()}, %)")
        rotulo_pontos.setStyleSheet("font-weight: bold;")
        painel_pontos.addWidget(rotulo_pontos)

        self.lista_pontos = QListWidget()
        self.lista_pontos.setSelectionMode(QListWidget.SingleSelection)
        self.lista_pontos.setMinimumWidth(200)
        self.lista_pontos.itemSelectionChanged.connect(
            self._ao_selecionar_ponto_lista)
        painel_pontos.addWidget(self.lista_pontos, 1)

        botao_remover = QPushButton("Remover selecionado")
        botao_remover.clicked.connect(self._remover_ponto_selecionado)
        painel_pontos.addWidget(botao_remover)

        botao_limpar = QPushButton("Limpar todos")
        botao_limpar.clicked.connect(self._limpar_pontos)
        painel_pontos.addWidget(botao_limpar)

        widget_painel = QWidget()
        widget_painel.setLayout(painel_pontos)
        widget_painel.setMaximumWidth(230)
        frame_central.addWidget(widget_painel)

        widget_central = QWidget()
        widget_central.setLayout(frame_central)
        layout_raiz.addWidget(widget_central, 1)

        # ---------------- painel manual --------------------------------
        self._montar_painel_manual(layout_raiz)

        # ---------------- rodapé ---------------------------------------
        rodape = QHBoxLayout()
        rodape.addStretch(1)

        botao_salvar = QPushButton("Salvar e usar esta curva")
        botao_salvar.setStyleSheet("background-color: #c8e6c9;")
        botao_salvar.clicked.connect(self._salvar_e_confirmar)
        rodape.addWidget(botao_salvar)

        botao_cancelar = QPushButton("Cancelar")
        botao_cancelar.clicked.connect(self._cancelar)
        rodape.addWidget(botao_cancelar)

        layout_raiz.addLayout(rodape)

    # ------------------------------------------------------------------ #
    def _montar_painel_manual(self, container):
        config = CONFIG_MODO[self.modo]

        grupo = QGroupBox("Adicionar/editar ponto manualmente (via teclado)")
        grade = QGridLayout(grupo)

        # A variável de duração precisa existir ANTES de _x_max_atual() ser
        # chamada (usada logo abaixo para configurar o limite do spinbox X).
        if config["permite_duracao_customizada"]:
            self.var_duracao = config["duracao_padrao_minutos"]

        grade.addWidget(QLabel(config["eixo_x"] + ":"), 0, 0)

        self.spin_x = QDoubleSpinBox()
        self.spin_x.setDecimals(config["casas_decimais"])
        self.spin_x.setRange(float(config["x_min"]), float(self._x_max_atual()))
        self.spin_x.setSingleStep(config["incremento_spinbox"])
        self.spin_x.setValue(float(config["x_min"]))
        self.spin_x.setMinimumWidth(120)
        grade.addWidget(self.spin_x, 0, 1)

        grade.addWidget(QLabel("Percentual (%):"), 0, 2)

        self.spin_percentual = QDoubleSpinBox()
        self.spin_percentual.setDecimals(1)
        self.spin_percentual.setRange(0.0, 200.0)
        self.spin_percentual.setSingleStep(0.5)
        self.spin_percentual.setValue(100.0)
        self.spin_percentual.setMinimumWidth(120)
        grade.addWidget(self.spin_percentual, 0, 3)

        botao_adicionar = QPushButton("➕ Adicionar / Atualizar ponto")
        botao_adicionar.clicked.connect(self._adicionar_ou_atualizar_ponto_manual)
        grade.addWidget(botao_adicionar, 0, 4)

        if config["permite_duracao_customizada"]:
            grade.addWidget(QLabel("Duração total (min):"), 1, 0)

            self.spin_duracao = QDoubleSpinBox()
            self.spin_duracao.setDecimals(0)
            self.spin_duracao.setRange(1.0, 1440.0)
            self.spin_duracao.setSingleStep(1.0)
            self.spin_duracao.setValue(float(config["duracao_padrao_minutos"]))
            self.spin_duracao.setMinimumWidth(120)
            self.spin_duracao.valueChanged.connect(self._ao_mudar_duracao)
            grade.addWidget(self.spin_duracao, 1, 1)

        container.addWidget(grupo)

    # ------------------------------------------------------------------ #
    def _x_max_atual(self) -> float:
        config = CONFIG_MODO[self.modo]
        if config["permite_duracao_customizada"]:
            try:
                return float(self.var_duracao)
            except (TypeError, ValueError, AttributeError):
                return config["duracao_padrao_minutos"]
        return config["x_max_fixo"]

    def _ao_mudar_duracao(self):
        try:
            nova_duracao = float(self.spin_duracao.value())
        except (TypeError, ValueError, RuntimeError):
            return

        nova_duracao = max(1.0, nova_duracao)
        self.var_duracao = nova_duracao
        if abs(self.spin_duracao.value() - nova_duracao) > 1e-9:
            self.spin_duracao.blockSignals(True)
            self.spin_duracao.setValue(nova_duracao)
            self.spin_duracao.blockSignals(False)

        fora_do_intervalo = [
            p for p in self.pontos
            if horas_para_unidade(self.modo, p[0]) > nova_duracao
        ]
        if fora_do_intervalo:
            mostrar_aviso_win11(
                "Aviso",
                f"{len(fora_do_intervalo)} ponto(s) ficaram além da nova duração "
                "e não serão exibidos no gráfico (mas continuam salvos).",
                parent=self)

        self.spin_x.setMaximum(float(nova_duracao))
        self._redesenhar()

    # ------------------------------------------------------------------ #
    def _atualizar_lista_combobox(self):
        nomes = [c.nome for c in listar_curvas_por_modo(self.pasta_curvas, self.modo)]
        selecionado = self.combo_curvas.currentText() if hasattr(
            self, "combo_curvas") else ""
        self.combo_curvas.blockSignals(True)
        self.combo_curvas.clear()
        self.combo_curvas.addItems(nomes)
        self.combo_curvas.setCurrentIndex(-1)
        if selecionado in nomes:
            self.combo_curvas.setCurrentText(selecionado)
        self.combo_curvas.blockSignals(False)

    def _ao_selecionar_combobox(self, event=None):
        nome = self.combo_curvas.currentText()
        if nome:
            self._carregar_curva_por_nome(nome)

    def _carregar_curva_por_nome(self, nome):
        curva = obter_curva(self.pasta_curvas, nome)
        if not curva:
            return

        self.nome_atual = curva.nome
        self.pontos = list(curva.pontos)
        self._hora_em_edicao = None

        self.entry_nome.setText(curva.nome)
        self.combo_curvas.blockSignals(True)
        self.combo_curvas.setCurrentText(curva.nome)
        self.combo_curvas.blockSignals(False)

        config = CONFIG_MODO[self.modo]
        if config["permite_duracao_customizada"]:
            duracao = curva.duracao_minutos or config["duracao_padrao_minutos"]
            self.var_duracao = float(duracao)
            self.spin_duracao.blockSignals(True)
            self.spin_duracao.setValue(float(duracao))
            self.spin_duracao.blockSignals(False)
            self.spin_x.setMaximum(float(duracao))

        self._redesenhar()

    def _nova_curva(self):
        self.nome_atual = None
        self.pontos = []
        self._hora_em_edicao = None
        self.entry_nome.setText("")
        self.combo_curvas.blockSignals(True)
        self.combo_curvas.setCurrentIndex(-1)
        self.combo_curvas.blockSignals(False)

        config = CONFIG_MODO[self.modo]
        if config["permite_duracao_customizada"]:
            self.var_duracao = float(config["duracao_padrao_minutos"])
            self.spin_duracao.blockSignals(True)
            self.spin_duracao.setValue(float(config["duracao_padrao_minutos"]))
            self.spin_duracao.blockSignals(False)
            self.spin_x.setMaximum(float(config["duracao_padrao_minutos"]))

        self._redesenhar()

    def _excluir_curva_selecionada(self):
        nome = self.combo_curvas.currentText()
        if not nome:
            return
        if confirmar_win11("Confirmar", f"Excluir a curva '{nome}'?", parent=self):
            remover_curva(self.pasta_curvas, nome)
            self._atualizar_lista_combobox()
            self._nova_curva()

    # ------------------------------------------------------------------ #
    def _ao_clicar_grafico(self, event):
        if event.xdata is None or event.ydata is None:
            return

        config = CONFIG_MODO[self.modo]
        x_min = config["x_min"]
        x_max = self._x_max_atual()
        incremento = config["incremento_snap"]

        valor_x = max(x_min, min(x_max, event.xdata))
        valor_x = round(valor_x / incremento) * incremento
        valor_x = round(valor_x, 6)
        percentual = round(max(0, min(200, event.ydata)), 1)

        hora = unidade_para_horas(self.modo, valor_x)

        if event.button == 1:
            self.pontos = [p for p in self.pontos if abs(p[0] - hora) > 1e-6]
            self.pontos.append((hora, percentual))
            self._hora_em_edicao = hora
            self.spin_x.setValue(round(valor_x, config["casas_decimais"]))
            self.spin_percentual.setValue(percentual)

        elif event.button == 3:
            if self.pontos:
                tolerancia_horas = config["tolerancia_remocao"] * HORAS_POR_UNIDADE[self.modo]
                mais_proximo = min(self.pontos, key=lambda p: abs(p[0] - hora))
                if abs(mais_proximo[0] - hora) <= tolerancia_horas:
                    self.pontos.remove(mais_proximo)
                    if self._hora_em_edicao == mais_proximo[0]:
                        self._hora_em_edicao = None

        self._redesenhar()

    def _ao_selecionar_ponto_lista(self):
        selecionados = self.lista_pontos.selectedItems()
        if not selecionados:
            return

        indice = self.lista_pontos.row(selecionados[0])
        pontos_ordenados = sorted(self.pontos, key=lambda p: p[0])
        if not (0 <= indice < len(pontos_ordenados)):
            return

        hora, percentual = pontos_ordenados[indice]
        self._hora_em_edicao = hora

        config = CONFIG_MODO[self.modo]
        valor_unidade = horas_para_unidade(self.modo, hora)
        self.spin_x.setValue(round(valor_unidade, config["casas_decimais"]))
        self.spin_percentual.setValue(percentual)

    def _adicionar_ou_atualizar_ponto_manual(self):
        config = CONFIG_MODO[self.modo]

        try:
            valor_x = float(self.spin_x.value())
            percentual = float(self.spin_percentual.value())
        except (TypeError, ValueError, RuntimeError):
            mostrar_aviso_win11(
                "Erro", "Informe valores numéricos válidos.", parent=self)
            return

        x_min = config["x_min"]
        x_max = self._x_max_atual()

        if not (x_min <= valor_x <= x_max):
            mostrar_aviso_win11(
                "Erro", f"O valor deve estar entre {x_min:g} e {x_max:g}.", parent=self)
            return

        percentual = max(0.0, min(200.0, percentual))
        nova_hora = unidade_para_horas(self.modo, valor_x)

        # Se estava editando um ponto já existente, remove a posição antiga
        if self._hora_em_edicao is not None:
            self.pontos = [p for p in self.pontos if abs(p[0] - self._hora_em_edicao) > 1e-6]

        # Evita duplicidade caso já exista um ponto na nova posição
        self.pontos = [p for p in self.pontos if abs(p[0] - nova_hora) > 1e-6]
        self.pontos.append((nova_hora, percentual))

        self._hora_em_edicao = nova_hora
        self._redesenhar()

    def _remover_ponto_selecionado(self):
        selecionados = self.lista_pontos.selectedItems()
        if not selecionados:
            return

        indices = sorted((self.lista_pontos.row(item) for item in selecionados), reverse=True)
        pontos_ordenados = sorted(self.pontos, key=lambda p: p[0])
        for indice in indices:
            if 0 <= indice < len(pontos_ordenados):
                ponto_removido = pontos_ordenados[indice]
                if ponto_removido in self.pontos:
                    self.pontos.remove(ponto_removido)
                if self._hora_em_edicao == ponto_removido[0]:
                    self._hora_em_edicao = None

        self._redesenhar()

    def _limpar_pontos(self):
        self.pontos = []
        self._hora_em_edicao = None
        self._redesenhar()

    # ------------------------------------------------------------------ #
    def _pontos_em_unidade(self):
        pontos_ordenados = sorted(self.pontos, key=lambda p: p[0])
        xs = [horas_para_unidade(self.modo, h) for h, _ in pontos_ordenados]
        ys = [p for _, p in pontos_ordenados]
        return xs, ys

    def _redesenhar(self):
        self.eixo.clear()
        config = CONFIG_MODO[self.modo]

        xs, ys = self._pontos_em_unidade()
        cor = "darkgreen" if self.natureza == "geracao" else "steelblue"

        if xs:
            self.eixo.plot(xs, ys, "-o", color=cor, markersize=6)

        x_min = config["x_min"]
        x_max = self._x_max_atual()

        self.eixo.set_xlim(x_min, x_max)
        self.eixo.set_ylim(0, 200)

        if self.modo == "daily":
            self.eixo.set_xticks(range(0, 25, 2))
            self.eixo.xaxis.set_minor_locator(MultipleLocator(1))
        else:
            self.eixo.xaxis.set_major_locator(MaxNLocator(nbins=10, integer=True))
            self.eixo.xaxis.set_minor_locator(AutoMinorLocator(4))

        self.eixo.set_yticks(range(0, 201, 25))
        self.eixo.yaxis.set_minor_locator(MultipleLocator(5))

        self.eixo.grid(which="major", linestyle="-", linewidth=0.7, alpha=0.7)
        self.eixo.grid(which="minor", linestyle=":", linewidth=0.5, alpha=0.5)

        self.eixo.set_xlabel(config["eixo_x"])
        rotulo_y = ("% da geração máxima (Pmpp / nominal)" if self.natureza == "geracao"
                    else "% da carga / potência nominal")
        self.eixo.set_ylabel(rotulo_y)
        self.eixo.set_title(config["rotulo"], fontsize=10)

        self.canvas.draw()

        self.lista_pontos.clear()
        pontos_ordenados = sorted(self.pontos, key=lambda p: p[0])
        for hora, percentual in pontos_ordenados:
            valor_unidade = horas_para_unidade(self.modo, hora)
            casas = config["casas_decimais"]
            self.lista_pontos.addItem(QListWidgetItem(
                f"{valor_unidade:.{casas}f}{config['sufixo_unidade']}   "
                f"{percentual:6.1f} %"))

    # ------------------------------------------------------------------ #
    def _salvar_e_confirmar(self):
        if len(self.pontos) < 2:
            mostrar_aviso_win11(
                "Pontos insuficientes",
                "Adicione pelo menos 2 pontos para definir a curva.", parent=self)
            return

        nome_digitado = self.entry_nome.text().strip()
        if not nome_digitado:
            mostrar_aviso_win11(
                "Erro", "Informe um nome para a curva.", parent=self)
            return

        config = CONFIG_MODO[self.modo]
        duracao = float(self.var_duracao) if config["permite_duracao_customizada"] else None

        curva = CurvaCaracteristica(
            nome=nome_digitado, natureza=self.natureza, modo=self.modo,
            duracao_minutos=duracao,
            pontos=sorted(self.pontos, key=lambda p: p[0]))

        if self.nome_atual == nome_digitado:
            atualizar_curva(self.pasta_curvas, curva)
            nome_final = nome_digitado
        else:
            nome_final = salvar_nova_curva(self.pasta_curvas, curva)
            if nome_final != nome_digitado:
                mostrar_aviso_win11(
                    "Nome ajustado automaticamente",
                    f"Já existia uma curva chamada '{nome_digitado}'.\n"
                    f"Esta foi salva como '{nome_final}'.", parent=self)

        self.resultado = nome_final
        self.accept()

    def _cancelar(self):
        self.resultado = None
        self.reject()


def abrir_editor_curva(parent, pasta_curvas: str, natureza: str, modo: str,
                      nome_inicial: str = None):
    """Abre o editor gráfico (modal) e retorna o nome da curva salva,
    ou None se o usuário cancelar."""
    dialogo = EditorCurvaDialog(parent, pasta_curvas, natureza, modo, nome_inicial)
    dialogo.exec()
    return dialogo.resultado
