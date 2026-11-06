__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Interface do Módulo de Otimização de Alocação de BESS (PLIM).

Este módulo costura quatro peças que existem separadas: o motor de
afundamento de tensão, o catálogo de BESS, o solver MILP e a análise de
economia de energia (arbitragem tarifária entre ponta e fora ponta). A
otimização roda em thread separada, com barra de progresso e relatório
final navegável, porque uma execução completa leva minutos — na thread
principal, a janela ficaria branca até o resultado.

MUDANÇA DE MOTOR (registro de transparência metodológica): depois que
estudo_afundamento.py migrou de win32com/COM para a biblioteca DSS-Python
(projeto DSS-Extensions), a thread de execução não precisa mais abrir e
fechar o contexto COM (pythoncom.CoInitialize()/CoUninitialize()).

MEMORIAL DE CÁLCULO: as abas "Memorial de Cálculo" e "Economia de Energia"
mostram, de forma auditável, os valores que sustentaram os resultados
agregados de cada análise. Sem elas, o número final seria uma caixa-preta
— justamente o que a banca questiona.

MIGRAÇÃO DE INTERFACE (Tkinter -> PySide6/Qt): a camada visual foi
reescrita em Qt (QDialog/QTabWidget/QTreeWidget). Ficaram inalterados os
textos, as validações, as chaves do dicionário de configuração e o contrato
de retorno das funções de domínio. A consequência direta é que
`abrir_dialogo_configuracao()` já não recebe um widget Tk como `parent`, e
sim um QWidget opcional. O bombeamento da fila da thread de execução
também mudou de dono: era `parent.after()` (Tk) e agora é
`QTimer.singleShot()` sobre o laço do Qt — que precisa estar ativo para o
estudo progrida, o que explica o cuidado com o laço nos pontos abaixo.
"""

# O backend do matplotlib precisa ser definido antes de qualquer import que
# arraste o pyplot para este processo. Os módulos de domínio não o importam
# hoje, mas fixar a ordem aqui elimina a dependência de quem importa o quê
# primeiro - que é o tipo de acoplamento que quebra meses depois.
import os

os.environ.setdefault("MPLBACKEND", "QtAgg")

import queue
import shutil
import traceback
import sys
import threading
import tempfile
from datetime import datetime
import webbrowser

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .projeto import Projeto
from .modelo_rede import RedeEletrica
from .exportador_dss import gerar_arquivos_dss
from .curvas_padrao import DIAS_SEMANA
from .estudo_afundamento import TIPOS_FALTA_DISPONIVEIS
from . import otimizacao_bess
from .memorial_calculo_afundamento import salvar_memorial
from .memorial_calculo_economia import salvar_memorial_economia
from .tarifas_energia import listar_opcoes_tarifa, obter_tarifa, TarifaEnergia
from . import exportador_esp32
from . import otimizacao_exportar_roi
from .ui_win11 import (
    RAIO_BORDA_BOTAO,
    RAIO_BORDA_CAMPO,
    RAIO_BORDA_CARTAO,
    confirmar_win11,
    detectar_tema,
    fonte_padrao,
    obter_paleta_ativa,
)


# ============================================================
# Captura global de exceções (subprocesso sem captura de saída)
# ============================================================
# Este módulo roda em PROCESSO PRÓPRIO, invocado pelo menu como
# `python -m bibliotecas.otimizacao_lancador` (subprocesso cuja saída não
# é capturada). Uma exceção não tratada matava o processo SEM RASTRO —
# para o usuário, a "janela piscava e fechava". A captura abaixo grava o
# traceback completo em <raiz_do_projeto>/erros/otimizacao_*.log e exibe
# um QMessageBox, mantendo o processo vivo e o erro diagnosticável.
# OBS.: exceções em slots Qt nem sempre passam por sys.excepthook (a
# conduta varia entre versões do PySide6); o fluxo crítico de construção
# do ResultadosDialog é protegido por try/except próprio em
# processar_fila(), roteando para o mesmo registro.

_captura_excecoes_instalada = False
_erro_ja_exibido = False
_raiz_projeto_log = [None]

# Referências vivas dos ResultadosDialog em exibição.
#
# Um QDialog top-level (parent=None) guardado apenas em variável local de
# um callback é coletado pelo coletor de lixo assim que o callback
# retorna: a janela "pisca e fecha". A causa raiz foi comprovada por
# reprodução offscreen, e a lista abaixo é a correção. A referência é
# solta no sinal `finished` do diálogo.
_dialogos_resultado = []


def _registrar_excecao(origem: str, tipo, valor, tb):
    """Grava o traceback em <raiz>/erros/otimizacao_AAAAMMDD_HHMMSS.log.

    Retorna (texto_completo, caminho_do_log_ou_None). Nunca levanta: o
    registro de erro não pode, ele próprio, derrubar o processo.
    """
    texto = "".join(traceback.format_exception(tipo, valor, tb))
    caminho_log = None
    try:
        pasta = os.path.join(_raiz_projeto_log[0] or os.getcwd(), "erros")
        os.makedirs(pasta, exist_ok=True)
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho_log = os.path.join(pasta, f"otimizacao_{carimbo}.log")
        with open(caminho_log, "w", encoding="utf-8") as arq:
            arq.write(f"Origem: {origem}\n\n{texto}")
    except Exception:
        pass  # o registro de erro não pode, ele próprio, derrubar o processo
    return texto, caminho_log


def _exibir_erro_fatal(titulo: str, mensagem: str) -> None:
    """QMessageBox crítico, exibido no máximo uma vez por execução (evita
    tempestade de modais se um slot em fila falhar repetidamente)."""
    global _erro_ja_exibido
    if _erro_ja_exibido:
        return
    _erro_ja_exibido = True
    if QApplication.instance() is not None:
        QMessageBox.critical(None, titulo, mensagem)


def instalar_captura_excecoes(raiz_projeto: str) -> None:
    """Instala sys.excepthook + threading.excepthook com log persistente.

    Idempotente; deve ser chamada uma única vez por processo, informando a
    raiz do projeto ativo (onde a pasta 'erros/' será criada se necessário).
    """
    global _captura_excecoes_instalada
    if _captura_excecoes_instalada:
        return
    _captura_excecoes_instalada = True
    _raiz_projeto_log[0] = os.path.abspath(raiz_projeto)

    hook_original = sys.excepthook

    def hook_principal(tipo, valor, tb):
        _, caminho_log = _registrar_excecao("thread principal", tipo, valor, tb)
        _exibir_erro_fatal(
            "Erro inesperado",
            "Ocorreu um erro inesperado no módulo de Otimização de BESS.\n"
            + (f"Detalhes técnicos salvos em:\n{caminho_log}\n\n"
               if caminho_log else "")
            + f"{tipo.__name__}: {valor}")
        if hook_original is not None:
            hook_original(tipo, valor, tb)

    sys.excepthook = hook_principal

    hook_threads_original = threading.excepthook

    def hook_threads(argumentos):  # assinatura de threading.excepthook
        if argumentos.exc_type is SystemExit:
            return
        _registrar_excecao(
            f"thread '{argumentos.thread.name}'"
            if argumentos.thread is not None else "thread (desconhecida)",
            argumentos.exc_type, argumentos.exc_value, argumentos.exc_traceback)
        # Sem QMessageBox aqui: erros da thread do estudo já são reportados
        # pela fila de eventos (resultado_container['erro'] → QMessageBox em
        # processar_fila). Um modal neste ponto duplicaria o aviso, e o
        # usuário fecharia o mesmo erro duas vezes.
        hook_threads_original(argumentos)

    threading.excepthook = hook_threads


def _remover_dialogo_resultado(dialogo) -> None:
    """Descarta a referência de um ResultadosDialog já fechado."""
    try:
        _dialogos_resultado.remove(dialogo)
    except ValueError:
        pass


# ============================================================
# Helpers visuais (identidade Win11 compartilhada)
# ============================================================

def _aplicar_estilo_dialogo(dialogo: QDialog) -> None:
    """Aplica fundo/borda do cartão Win11 ao diálogo, conforme o tema ativo."""
    paleta = obter_paleta_ativa(detectar_tema())
    dialogo.setStyleSheet(
        f"""
        QDialog {{
            background-color: {paleta.fundo_cartao};
        }}
        QLabel {{
            color: {paleta.texto_primario};
        }}
        QGroupBox {{
            border: 1px solid {paleta.borda_cartao};
            border-radius: {RAIO_BORDA_CARTAO}px;
            margin-top: 14px;
            padding-top: 6px;
            color: {paleta.texto_primario};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            padding: 0 4px;
            color: {paleta.texto_primario};
        }}
        QListWidget, QPlainTextEdit, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
            background-color: {paleta.fundo_campo};
            color: {paleta.texto_primario};
            border: 1px solid {paleta.borda_campo};
            border-radius: {RAIO_BORDA_CAMPO}px;
            padding: 2px 4px;
        }}
        QTreeWidget {{
            background-color: {paleta.fundo_campo};
            color: {paleta.texto_primario};
            border: 1px solid {paleta.borda_cartao};
            border-radius: {RAIO_BORDA_CAMPO}px;
        }}
        QHeaderView::section {{
            background-color: {paleta.botao_secundario_fundo};
            color: {paleta.texto_primario};
            border: none;
            border-bottom: 1px solid {paleta.borda_cartao};
            padding: 4px;
        }}
        QTabWidget::pane {{
            border: 1px solid {paleta.borda_cartao};
            border-radius: {RAIO_BORDA_CARTAO}px;
        }}
        QTabBar::tab {{
            background-color: {paleta.botao_secundario_fundo};
            color: {paleta.texto_primario};
            padding: 6px 12px;
            border: 1px solid {paleta.borda_cartao};
            border-bottom: none;
            border-top-left-radius: {RAIO_BORDA_CAMPO}px;
            border-top-right-radius: {RAIO_BORDA_CAMPO}px;
        }}
        QTabBar::tab:selected {{
            background-color: {paleta.accent};
            color: #FFFFFF;
        }}
        QProgressBar {{
            background-color: {paleta.fundo_campo};
            border: 1px solid {paleta.borda_campo};
            border-radius: {RAIO_BORDA_CAMPO}px;
            text-align: center;
            color: {paleta.texto_primario};
            height: 18px;
        }}
        QProgressBar::chunk {{
            background-color: {paleta.accent};
            border-radius: {RAIO_BORDA_CAMPO}px;
        }}
        """
    )


def _estilo_botao_secundario() -> str:
    paleta = obter_paleta_ativa(detectar_tema())
    return f"""
        QPushButton {{
            background-color: {paleta.botao_secundario_fundo};
            color: {paleta.texto_primario};
            border: 1px solid {paleta.borda_campo};
            border-radius: {RAIO_BORDA_BOTAO}px;
            padding: 6px 14px;
        }}
        QPushButton:hover {{ background-color: {paleta.botao_secundario_hover}; }}
        QPushButton:pressed {{ background-color: {paleta.botao_secundario_pressed}; }}
    """


def _estilo_botao_principal() -> str:
    paleta = obter_paleta_ativa(detectar_tema())
    return f"""
        QPushButton {{
            background-color: {paleta.accent};
            color: #FFFFFF;
            border: none;
            border-radius: {RAIO_BORDA_BOTAO}px;
            padding: 6px 14px;
            font-weight: 600;
        }}
        QPushButton:hover {{ background-color: {paleta.accent_hover}; }}
        QPushButton:pressed {{ background-color: {paleta.accent_pressed}; }}
    """


def _rotulo_negrito(texto: str) -> QLabel:
    rotulo = QLabel(texto)
    rotulo.setFont(fonte_padrao(9, True))
    return rotulo


def _rotulo_dica(texto: str) -> QLabel:
    paleta = obter_paleta_ativa(detectar_tema())
    rotulo = QLabel(texto)
    rotulo.setFont(fonte_padrao(8))
    rotulo.setWordWrap(True)
    rotulo.setStyleSheet(f"color: {paleta.texto_secundario};")
    return rotulo


def _lista_multiselecao(nomes: list[str], altura_linhas: int = 6) -> QListWidget:
    """Monta uma lista de seleção múltipla, equivalente ao ListBox do Tk.

    A altura é calculada a partir da altura real da fonte vezes o número de
    linhas desejado, mais uma folga. Fixar altura em pixels daria uma lista
    cortada ou sobrando, dependendo do DPI do monitor.
    """
    lista = QListWidget()
    lista.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
    lista.setUniformItemSizes(True)
    for nome in nomes:
        lista.addItem(QListWidgetItem(nome))
    # Equivalente ao `lista.selection_set(0, "end")` do Tk original: os
    # itens já nascem todos selecionados, porque o caso comum é validar
    # todos os sistemas, não escolher um a um.
    if lista.count():
        lista.setCurrentRow(0)
        for indice in range(lista.count()):
            lista.item(indice).setSelected(True)
    altura_lista = lista.fontMetrics().height() * altura_linhas + 12
    lista.setMinimumHeight(altura_lista)
    return lista


# ============================================================
# Configuração do estudo
# ============================================================

class ConfiguracaoEstudoDialog(QDialog):
    """Formulário de configuração do estudo de alocação de BESS.

    Após `exec()`, o dicionário de configuração está em `self.resultado`
    (None se o usuário cancelou).
    """

    def __init__(self, parent, projeto: Projeto, rede: RedeEletrica):
        super().__init__(parent)
        self.projeto = projeto
        self.rede = rede
        self.resultado = None

        self.setWindowTitle("Configurar Estudo de Otimização de Alocação de BESS")
        self.setModal(True)
        self.resize(600, 900)
        _aplicar_estilo_dialogo(self)

        # Mapa rótulo -> chave da tarifa (o combobox exibe rótulos).
        self._mapa_tarifa_rotulo_para_chave = {}

        self._montar_widgets()

    # ------------------------------------------------------------------ #
    def _montar_widgets(self) -> None:
        nomes_barras = sorted(self.rede.barras.keys())

        # Área rolável: equivalente ao Canvas + Scrollbar do Tk original.
        area_rolagem = QScrollArea(self)
        area_rolagem.setWidgetResizable(True)
        area_rolagem.setFrameShape(QFrame.Shape.NoFrame)
        conteudo = QWidget()
        layout_conteudo = QVBoxLayout(conteudo)
        area_rolagem.setWidget(conteudo)

        # ------------------------------------------------ barras candidatas
        layout_conteudo.addWidget(
            _rotulo_negrito("Barras candidatas para instalação do BESS:"))
        self.lista_candidatas = _lista_multiselecao(nomes_barras)
        layout_conteudo.addWidget(self.lista_candidatas)

        # ------------------------------------------------ barras de falta
        layout_conteudo.addWidget(_rotulo_negrito(
            "Barras onde simular falta (área de vulnerabilidade):"))
        self.lista_falta = _lista_multiselecao(nomes_barras)
        layout_conteudo.addWidget(self.lista_falta)

        # ------------------------------------------------ tipos de falta
        layout_conteudo.addWidget(_rotulo_negrito("Tipos de falta a considerar:"))
        self.vars_tipos_falta = {}
        grupo_tipos = QWidget()
        layout_tipos = QVBoxLayout(grupo_tipos)
        layout_tipos.setContentsMargins(16, 0, 0, 0)
        for chave, rotulo in TIPOS_FALTA_DISPONIVEIS.items():
            caixa = QCheckBox(rotulo)
            caixa.setChecked(True)
            layout_tipos.addWidget(caixa)
            self.vars_tipos_falta[chave] = caixa
        layout_conteudo.addWidget(grupo_tipos)

        # ------------------------------------------------ parâmetros do solver
        grupo_parametros = QGroupBox("Parâmetros do otimizador")
        grade = QGridLayout(grupo_parametros)

        grade.addWidget(QLabel("Nº máximo de unidades de BESS:"), 0, 0)
        self.spin_max_unidades = QSpinBox()
        self.spin_max_unidades.setRange(1, 10)
        self.spin_max_unidades.setValue(1)
        self.spin_max_unidades.setFixedWidth(90)
        grade.addWidget(self.spin_max_unidades, 0, 1)

        grade.addWidget(QLabel("Peso do custo (0 a 0.5):"), 1, 0)
        self.spin_peso_custo = QDoubleSpinBox()
        self.spin_peso_custo.setRange(0.0, 0.5)
        self.spin_peso_custo.setSingleStep(0.05)
        self.spin_peso_custo.setDecimals(2)
        self.spin_peso_custo.setValue(0.1)
        self.spin_peso_custo.setFixedWidth(90)
        grade.addWidget(self.spin_peso_custo, 1, 1)

        grade.addWidget(QLabel("Orçamento máximo (R$, vazio = sem limite):"), 2, 0)
        self.campo_orcamento = QLineEdit()
        self.campo_orcamento.setFixedWidth(160)
        grade.addWidget(self.campo_orcamento, 2, 1)

        layout_conteudo.addWidget(grupo_parametros)

        # ------------------------------------------------ economia de energia
        layout_conteudo.addWidget(_rotulo_negrito(
            "Economia de Energia (arbitragem tarifária):"))

        self.caixa_habilitar_economia = QCheckBox(
            "Habilitar análise de economia de energia "
            "(executada na alocação vencedora do estudo de afundamento)")
        self.caixa_habilitar_economia.setChecked(True)
        self.caixa_habilitar_economia.toggled.connect(self._alternar_campos_economia)
        layout_conteudo.addWidget(self.caixa_habilitar_economia)

        self.grupo_economia = QGroupBox("Arbitragem tarifária")
        grade_economia = QGridLayout(self.grupo_economia)

        grade_economia.addWidget(QLabel("Tarifa de referência:"), 0, 0)
        self.combo_tarifa = QComboBox()
        opcoes_tarifa = listar_opcoes_tarifa()
        self.combo_tarifa.addItems([rotulo for _, rotulo in opcoes_tarifa])
        self._mapa_tarifa_rotulo_para_chave = {
            rotulo: chave for chave, rotulo in opcoes_tarifa
        }
        grade_economia.addWidget(self.combo_tarifa, 0, 1, 1, 2)
        self.combo_tarifa.currentIndexChanged.connect(self._ao_selecionar_tarifa)

        grade_economia.addWidget(QLabel("Energia ponta (R$/kWh):"), 1, 0)
        self.campo_tarifa_ponta = QLineEdit()
        self.campo_tarifa_ponta.setFixedWidth(130)
        grade_economia.addWidget(self.campo_tarifa_ponta, 1, 1)

        grade_economia.addWidget(QLabel("Energia fora ponta (R$/kWh):"), 2, 0)
        self.campo_tarifa_fora = QLineEdit()
        self.campo_tarifa_fora.setFixedWidth(130)
        grade_economia.addWidget(self.campo_tarifa_fora, 2, 1)

        grade_economia.addWidget(QLabel("Início do horário de ponta (h):"), 3, 0)
        self.spin_horario_inicio = QSpinBox()
        self.spin_horario_inicio.setRange(0, 23)
        self.spin_horario_inicio.setValue(18)
        self.spin_horario_inicio.setFixedWidth(90)
        grade_economia.addWidget(self.spin_horario_inicio, 3, 1)

        grade_economia.addWidget(QLabel("Fim do horário de ponta (h):"), 4, 0)
        self.spin_horario_fim = QSpinBox()
        self.spin_horario_fim.setRange(0, 23)
        self.spin_horario_fim.setValue(21)
        self.spin_horario_fim.setFixedWidth(90)
        grade_economia.addWidget(self.spin_horario_fim, 4, 1)

        grade_economia.addWidget(QLabel("Dias equivalentes por mês:"), 5, 0)
        self.spin_dias_equivalentes = QDoubleSpinBox()
        self.spin_dias_equivalentes.setRange(1.0, 31.0)
        self.spin_dias_equivalentes.setDecimals(1)
        self.spin_dias_equivalentes.setValue(22.0)
        self.spin_dias_equivalentes.setFixedWidth(90)
        grade_economia.addWidget(self.spin_dias_equivalentes, 5, 1)

        layout_conteudo.addWidget(self.grupo_economia)

        linha_curvas_padrao = QHBoxLayout()
        linha_curvas_padrao.addWidget(QLabel(
            "Dia da semana para curvas padrão (elementos sem curva vinculada):"))
        self.combo_dia_padrao = QComboBox()
        self.combo_dia_padrao.addItems(DIAS_SEMANA)
        self.combo_dia_padrao.setCurrentIndex(0)
        self.combo_dia_padrao.setFixedWidth(130)
        linha_curvas_padrao.addWidget(self.combo_dia_padrao)
        linha_curvas_padrao.addStretch()
        layout_conteudo.addLayout(linha_curvas_padrao)

        self._ao_selecionar_tarifa()  # preenche os campos com a 1ª tarifa

        dica_economia = (
            "Valores de referência: CELESC (Resolução Homologatória ANEEL nº 3.602/2026, "
            "SEM tributos). Ajuste conforme a distribuidora/contrato real do projeto. "
            "A simulação usa um 'dia representativo' de 24h (modo QSTS diário do OpenDSS).")
        layout_conteudo.addWidget(_rotulo_dica(dica_economia))

        dica = ("O estudo executa o caso base (sem BESS) e, em seguida, simula cada "
                "combinação de barra candidata x tamanho de BESS do catálogo padrão, "
                "sob os tipos de falta selecionados. Elementos sem curva vinculada "
                "usam a curva padrão da ferramenta para o dia escolhido acima; "
                "curvas de projeto vinculadas prevalecem. Pode levar alguns "
                "minutos dependendo do tamanho da rede.")
        layout_conteudo.addWidget(_rotulo_dica(dica))

        botao_curvas = QPushButton("📚 Curvas Semanais (PV/Cargas)")
        botao_curvas.setToolTip(
            "Editar as curvas diárias (7 dias, hora a hora, em percentual) das "
            "gerações solares e cargas do projeto, com conversão em kW/kvar/kVA "
            "pela potência nominal e retorno ao padrão.")
        botao_curvas.clicked.connect(self._abrir_curvas_semanais)
        layout_conteudo.addWidget(botao_curvas)

        # ------------------------------------------------ botões
        botoes = QDialogButtonBox()
        self.botao_cancelar = QPushButton("Cancelar")
        self.botao_cancelar.setStyleSheet(_estilo_botao_secundario())
        self.botao_iniciar = QPushButton("Iniciar Estudo")
        self.botao_iniciar.setStyleSheet(_estilo_botao_principal())
        self.botao_iniciar.setDefault(True)
        botoes.addButton(self.botao_cancelar, QDialogButtonBox.ButtonRole.RejectRole)
        botoes.addButton(self.botao_iniciar, QDialogButtonBox.ButtonRole.AcceptRole)
        self.botao_cancelar.clicked.connect(self._cancelar)
        self.botao_iniciar.clicked.connect(self._confirmar)

        layout_raiz = QVBoxLayout(self)
        layout_raiz.addWidget(area_rolagem, 1)
        layout_raiz.addWidget(botoes)

    # ------------------------------------------------------------------ #
    def _abrir_curvas_semanais(self) -> None:
        """Abre o editor de curvas semanais por cima deste diálogo."""
        from .curvas_semanais_ui import CurvasSemanaisDialog
        dialogo = CurvasSemanaisDialog(self, self.projeto, self.rede)
        dialogo.exec()

    # ------------------------------------------------------------------ #
    def _ao_selecionar_tarifa(self, indice=None) -> None:
        """Preenche os campos de tarifa com os valores do catálogo escolhido."""
        rotulo = self.combo_tarifa.currentText()
        chave = self._mapa_tarifa_rotulo_para_chave.get(rotulo)
        if not chave:
            return
        tarifa = obter_tarifa(chave)
        if not tarifa:
            return
        self.campo_tarifa_ponta.setText(f"{tarifa.tarifa_ponta_kwh:.5f}")
        self.campo_tarifa_fora.setText(f"{tarifa.tarifa_fora_ponta_kwh:.5f}")

    def _alternar_campos_economia(self) -> None:
        """Habilita o bloco de economia apenas quando a caixa está marcada."""
        self.grupo_economia.setEnabled(self.caixa_habilitar_economia.isChecked())

    # ------------------------------------------------------------------ #
    def _confirmar(self) -> None:
        """Valida a seleção do usuário e fecha devolvendo a configuração."""
        barras_candidatas = [item.text() for item in self.lista_candidatas.selectedItems()]
        barras_falta = [item.text() for item in self.lista_falta.selectedItems()]

        if not barras_candidatas or not barras_falta:
            QMessageBox.critical(
                self, "Erro",
                "Selecione ao menos uma barra candidata e uma barra de falta.")
            return

        tipos_falta = [chave for chave, caixa in self.vars_tipos_falta.items()
                       if caixa.isChecked()]
        if not tipos_falta:
            QMessageBox.critical(self, "Erro", "Selecione ao menos um tipo de falta.")
            return

        orcamento_texto = self.campo_orcamento.text().strip()
        custo_maximo = None
        if orcamento_texto:
            try:
                custo_maximo = float(orcamento_texto)
            except ValueError:
                QMessageBox.critical(self, "Erro", "Orçamento máximo inválido.")
                return

        tarifa_selecionada = None
        horario_ponta_inicio, horario_ponta_fim, dias_equivalentes_mes = 18, 21, 22

        if self.caixa_habilitar_economia.isChecked():
            rotulo = self.combo_tarifa.currentText()
            chave = self._mapa_tarifa_rotulo_para_chave.get(rotulo)
            tarifa_catalogo = obter_tarifa(chave) if chave else None

            try:
                tarifa_ponta = float(
                    self.campo_tarifa_ponta.text().strip().replace(",", "."))
                tarifa_fora = float(
                    self.campo_tarifa_fora.text().strip().replace(",", "."))
            except ValueError:
                QMessageBox.critical(
                    self, "Erro", "Valores de tarifa de energia inválidos.")
                return

            horario_ponta_inicio = int(self.spin_horario_inicio.value())
            horario_ponta_fim = int(self.spin_horario_fim.value())
            dias_equivalentes_mes = float(self.spin_dias_equivalentes.value())

            tarifa_selecionada = TarifaEnergia(
                nome=tarifa_catalogo.nome if tarifa_catalogo else "Tarifa personalizada",
                subgrupo=tarifa_catalogo.subgrupo if tarifa_catalogo else "-",
                modalidade=tarifa_catalogo.modalidade if tarifa_catalogo else "-",
                tarifa_ponta_kwh=tarifa_ponta,
                tarifa_fora_ponta_kwh=tarifa_fora,
                demanda_ponta_kw=tarifa_catalogo.demanda_ponta_kw if tarifa_catalogo else 0.0,
                demanda_fora_ponta_kw=tarifa_catalogo.demanda_fora_ponta_kw if tarifa_catalogo else 0.0,
            )

        self.resultado = {
            "barras_candidatas": barras_candidatas,
            "barras_falta": barras_falta,
            "tipos_falta": tipos_falta,
            "max_unidades": self.spin_max_unidades.value(),
            "peso_custo": self.spin_peso_custo.value(),
            "custo_maximo": custo_maximo,
            "tarifa": tarifa_selecionada,
            "horario_ponta_inicio": horario_ponta_inicio,
            "horario_ponta_fim": horario_ponta_fim,
            "dias_equivalentes_mes": dias_equivalentes_mes,
            "dia_curvas_padrao": self.combo_dia_padrao.currentText(),
        }
        self.accept()

    def _cancelar(self) -> None:
        self.resultado = None
        self.reject()


# ============================================================
# Progresso
# ============================================================

class ProgressoDialog(QDialog):
    """Diálogo modal de progresso do estudo (não pode ser fechado pelo usuário)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Executando estudo de otimização...")
        self.setModal(True)
        self.setFixedSize(440, 160)
        _aplicar_estilo_dialogo(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.label_status = QLabel("Iniciando...")
        self.label_status.setWordWrap(True)
        self.label_status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.label_status)

        self.barra = QProgressBar()
        self.barra.setRange(0, 100)
        self.barra.setValue(0)
        layout.addWidget(self.barra)

        self.label_percentual = QLabel("0%")
        self.label_percentual.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label_percentual)

        layout.addStretch(1)

    def atualizar(self, percentual, status=None) -> None:
        """Atualiza barra, percentual e mensagem de status de uma vez.

        O percentual é limitado a 0..100: o cálculo de progresso vem da
        thread e um arredondamento pode devolver 100,4 no último passo.
        """
        valor = int(round(percentual))
        self.barra.setValue(max(0, min(100, valor)))
        self.label_percentual.setText(f"{percentual:.0f}%")
        if status:
            self.label_status.setText(status)

    def closeEvent(self, evento) -> None:
        # Equivalente ao `protocol("WM_DELETE_WINDOW", lambda: None)` do Tk:
        # o "X" da janela de progresso é ignorado. Fechá-la no meio deixaria
        # o estudo rodando sem nenhuma indicação de que roda - e sem barra
        # para acompanhar. Fechar só acontece pelo código, ao concluir.
        evento.ignore()

    def keyPressEvent(self, evento) -> None:
        if evento.key() == Qt.Key.Key_Escape:
            evento.ignore()
            return
        super().keyPressEvent(evento)


# ============================================================
# Resultados
# ============================================================

class ResultadosDialog(QDialog):
    """Relatório navegável do estudo (abas de alocação, ranking, reativo,
    memoriais e aplicação ao projeto)."""

    def __init__(self, parent, projeto: Projeto, rede: RedeEletrica, resultado: dict):
        super().__init__(parent)
        self.projeto = projeto
        self.rede = rede
        self.resultado = resultado

        self.setWindowTitle("Resultado da Otimização de Alocação de BESS")
        self.setModal(False)
        self.resize(880, 700)
        _aplicar_estilo_dialogo(self)

        self._montar_widgets()

    # ------------------------------------------------------------------ #
    def _montar_widgets(self) -> None:
        layout_raiz = QVBoxLayout(self)

        resumo = QWidget()
        layout_resumo = QVBoxLayout(resumo)
        layout_resumo.setContentsMargins(0, 0, 0, 0)

        n_baseline = len(self.resultado["barras_em_sag_baseline"])
        beneficio = self.resultado["beneficio_conjunto_real"]
        n_final = n_baseline - beneficio

        if n_baseline > 0:
            texto_percentual = f"{100 * beneficio / n_baseline:.1f}%"
        else:
            texto_percentual = "sem afundamentos no caso base"

        texto_resumo = (
            f"Barras em afundamento SEM BESS (caso base): {n_baseline}\n"
            f"Barras em afundamento COM a alocação otimizada: {n_final}\n"
            f"Redução obtida: {beneficio} barra(s) ({texto_percentual})\n"
            f"Status do solver MILP: {self.resultado['status_milp']}"
        )
        rotulo_resumo = QLabel(texto_resumo)
        rotulo_resumo.setFont(fonte_padrao(10))
        rotulo_resumo.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        if beneficio > 0:
            rotulo_resumo.setStyleSheet(
                f"color: {obter_paleta_ativa(detectar_tema()).accent}; font-weight: 600;")
        layout_resumo.addWidget(rotulo_resumo)

        if n_baseline == 0:
            layout_resumo.addWidget(_rotulo_dica(
                "ℹ Consulte a aba 'Memorial de Cálculo' para auditar, barra a "
                "barra, os valores de tensão que resultaram em '0 barras em "
                "afundamento no caso base'."))

        layout_raiz.addWidget(resumo)

        self.abas = QTabWidget()
        layout_raiz.addWidget(self.abas, 1)

        aba_selecionados = QWidget()
        self.abas.addTab(aba_selecionados, "Alocação Selecionada")
        self._montar_aba_selecionados(aba_selecionados)

        aba_ranking = QWidget()
        self.abas.addTab(aba_ranking, "Ranking de Candidatos")
        self._montar_aba_ranking(aba_ranking)

        aba_reativo = QWidget()
        self.abas.addTab(aba_reativo, "Compensação Reativa")
        self._montar_aba_reativo(aba_reativo)

        aba_memorial = QWidget()
        self.abas.addTab(aba_memorial, "Memorial de Cálculo")
        self._montar_aba_memorial(aba_memorial)

        aba_economia = QWidget()
        self.abas.addTab(aba_economia, "Economia de Energia")
        self._montar_aba_economia(aba_economia)

        barra_botoes = QHBoxLayout()
        barra_botoes.addStretch(1)
        botao_fechar = QPushButton("Fechar")
        botao_fechar.setStyleSheet(_estilo_botao_secundario())
        botao_fechar.clicked.connect(self.close)
        botao_esp32 = QPushButton("Exportar parametrização ESP32 (controle BESS)")
        botao_esp32.setStyleSheet(_estilo_botao_secundario())
        botao_esp32.setToolTip(
            "Gera o param_esp32.h para o sketch pré-pronto "
            "hardware/esp32_controle_bess/ (despacho de ativa e reativa).")
        botao_esp32.clicked.connect(self._exportar_parametrizacao_esp32)
        botao_roi = QPushButton("Exportar ROI / DRE (HTML)")
        botao_roi.setStyleSheet(_estilo_botao_secundario())
        botao_roi.setToolTip(
            "Gera o relatório de justificativa de investimento (DRE: "
            "receitas × investimento, payback, ROI) com gráficos e "
            "indicadores de qualidade de energia.")
        botao_roi.clicked.connect(self._exportar_roi_dre)
        botao_aplicar = QPushButton("Aplicar ao Projeto (Editor de Rede)")
        botao_aplicar.setStyleSheet(_estilo_botao_principal())
        botao_aplicar.clicked.connect(self._aplicar_ao_projeto)
        barra_botoes.addWidget(botao_fechar)
        barra_botoes.addWidget(botao_esp32)
        barra_botoes.addWidget(botao_roi)
        barra_botoes.addWidget(botao_aplicar)

        layout_raiz.addLayout(barra_botoes)

    # ------------------------------------------------------------------ #
    def _exportar_parametrizacao_esp32(self) -> None:
        """Gera o cabeçalho de parametrização do ESP32 (controlador do BESS).

        A lógica embarcada NÃO é gerada aqui: o sketch pré-pronto e fixo vive
        em `hardware/esp32_controle_bess/`. O que este botão produz é o
        `param_esp32.h` com os valores deste projeto e deste estudo — tabela
        de despacho, limites de SoC, curvas Volt-Var/Volt-Watt, escalas do
        protocolo UART com o Arduino Mega.
        """
        selecionados = self.resultado.get("selecionados") or []
        if not selecionados:
            QMessageBox.information(
                self, "Aviso",
                "Não há alocação selecionada pelo estudo de otimização.\n\n"
                "A parametrização do ESP32 é gerada a partir da configuração "
                "vencedora do BESS — conclua o estudo com ao menos uma "
                "alocação antes de exportar.")
            return

        destino = exportador_esp32.caminho_padrao_param_esp32(self.projeto)
        caminho = QFileDialog.getSaveFileName(
            self, "Salvar parametrização do ESP32", destino,
            "Cabeçalho C (*.h)")[0]
        if not caminho:
            return
        if not caminho.lower().endswith(".h"):
            caminho += ".h"

        try:
            res = exportador_esp32.gerar_parametrizacao_esp32_do_resultado(
                self.projeto, self.resultado, caminho,
                horario_ponta_inicio=self.resultado.get("resultado_economia", {}).get(
                    "horario_ponta_inicio", exportador_esp32.PONTA_INICIO_PADRAO)
                if self.resultado.get("resultado_economia") else exportador_esp32.PONTA_INICIO_PADRAO,
                horario_ponta_fim=self.resultado.get("resultado_economia", {}).get(
                    "horario_ponta_fim", exportador_esp32.PONTA_FIM_PADRAO)
                if self.resultado.get("resultado_economia") else exportador_esp32.PONTA_FIM_PADRAO,
            )
        except Exception as erro:
            QMessageBox.critical(
                self, "Erro",
                f"Não foi possível gerar a parametrização do ESP32:\n{erro}")
            return

        texto_avisos = ""
        if res["avisos"]:
            texto_avisos = (
                "\n\nAVISOS (leia antes do ensaio):\n- "
                + "\n- ".join(res["avisos"]))

        QMessageBox.information(
            self, "Sucesso",
            "Parametrização do ESP32 gerada.\n\n"
            f"Arquivo: {res['caminho']}\n\n"
            f"BESS: {res['kw_rating']:.1f} kW / {res['kwh_rating']:.1f} kWh "
            f"| Q_lim: {res['q_lim_kvar']:.1f} kvar\n"
            f"SoC: {res['soc_min'] * 100:.0f}%..{res['soc_max'] * 100:.0f}% "
            f"(inicial {res['soc_inicial'] * 100:.0f}%)\n"
            f"Curvas: {res['pontos_vvc']} ponto(s) Volt-Var, "
            f"{res['pontos_vw']} ponto(s) Volt-Watt\n\n"
            "Copie o arquivo para a pasta do sketch pré-pronto:\n"
            "hardware/esp32_controle_bess/" + texto_avisos)

    # ------------------------------------------------------------------ #
    def _montar_aba_selecionados(self, container: QWidget) -> None:
        layout = QVBoxLayout(container)
    def _exportar_roi_dre(self) -> None:
        """Gera o relatório HTML de justificativa de investimento (DRE).

        Consolida receitas (economia de energia, arbitragem e exportação) e
        investimento (CAPEX do BESS) em payback/ROI, com gráficos de projeção
        de caixa e qualidade de energia. O cálculo vive em
        `otimizacao_exportar_roi`; aqui só há a interação com o usuário.
        """
        if not self.resultado.get("resultado_economia"):
            QMessageBox.warning(
                self, "Aviso",
                "O estudo foi executado sem tarifa de energia, portanto não "
                "há avaliação econômica para exportar.")
            return

        selecionados = self.resultado.get("selecionados") or []
        if not selecionados:
            QMessageBox.warning(
                self, "Aviso",
                "Não há alocação selecionada pelo estudo de otimização.\n\n"
                "O relatório de ROI é gerado a partir da configuração "
                "vencedora do BESS — conclua o estudo com ao menos uma "
                "alocação antes de exportar.")
            return

        sugestao = os.path.join(
            self.projeto.caminho_raiz, "roi_bess_" + self.projeto.nome + ".html")
        caminho = QFileDialog.getSaveFileName(
            self, "Salvar relatório de ROI (DRE)", sugestao,
            "Relatório HTML (*.html)")[0]
        if not caminho:
            return
        if not caminho.lower().endswith(".html"):
            caminho += ".html"

        try:
            otimizacao_exportar_roi.gerar_relatorio_roi(
                self.resultado, caminho, nome_projeto=self.projeto.nome)
        except Exception as erro:
            QMessageBox.critical(
                self, "Erro",
                f"Não foi possível gerar o relatório de ROI:\n{erro}")
            return

        QMessageBox.information(
            self, "Sucesso",
            "Relatório de ROI (DRE) gerado.\n\n"
            f"Arquivo: {caminho}\n\n"
            "O relatório será aberto no navegador padrão.")
        webbrowser.open("file:///" + caminho.replace("\\", "/"))

    # ------------------------------------------------------------------ #
        selecionados = self.resultado["selecionados"]
        if not selecionados:
            rotulo = QLabel("Nenhuma alocação foi selecionada pelo otimizador "
                            "(nenhum candidato trouxe benefício, ou restrições "
                            "muito rígidas).")
            rotulo.setWordWrap(True)
            layout.addWidget(rotulo)
            layout.addStretch(1)
            return

        arvore = QTreeWidget()
        arvore.setColumnCount(8)
        arvore.setHeaderLabels(["Barra", "Modelo BESS", "kW", "kWh", "Custo (R$)",
                                "Barras resolvidas (estimado)",
                                "Ben. sag (pu·barra)", "Economia (R$/ano)"])
        arvore.setRootIsDecorated(False)
        arvore.setAlternatingRowColors(True)
        arvore.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        arvore.header().setStretchLastSection(True)

        for c in selecionados:
            item = QTreeWidgetItem([
                str(c["bus"]),
                str(c["modelo_bess"]["nome"]),
                str(c["modelo_bess"]["kw"]),
                str(c["modelo_bess"]["kwh"]),
                f"{c['modelo_bess']['custo_brl']:,.2f}",
                str(c["beneficio"]),
                f"{c.get('beneficio_severidade', 0):.4f}",
                f"{c.get('beneficio_econ_anual', 0.0):.2f}",
            ])
            arvore.addTopLevelItem(item)

        layout.addWidget(arvore, 1)

        rotulo_beneficio = QLabel(
            f"Benefício REAL verificado conjuntamente: "
            f"{self.resultado['beneficio_conjunto_real']} barra(s) "
            "deixaram de apresentar afundamento de tensão.")
        rotulo_beneficio.setFont(fonte_padrao(9))
        rotulo_beneficio.setStyleSheet(
            f"color: {obter_paleta_ativa(detectar_tema()).accent}; font-style: italic;")
        rotulo_beneficio.setWordWrap(True)
        layout.addWidget(rotulo_beneficio)

        nota = ("Nota: o 'benefício estimado' na tabela acima é calculado avaliando "
                "cada BESS ISOLADAMENTE. Quando há mais de uma unidade selecionada, "
                "a soma desses valores pode superestimar o ganho real. O valor "
                "confiável é o 'Benefício REAL verificado conjuntamente' acima.")
        layout.addWidget(_rotulo_dica(nota))

    # ------------------------------------------------------------------ #
    def _montar_aba_ranking(self, container: QWidget) -> None:
        layout = QVBoxLayout(container)

        arvore = QTreeWidget()
        arvore.setColumnCount(6)
        arvore.setHeaderLabels(["Barra", "Modelo BESS", "Custo (R$)",
                                "Barras resolvidas (binário)",
                                "Ben. sag (pu·barra)", "Economia (R$/ano)"])
        arvore.setRootIsDecorated(False)
        arvore.setAlternatingRowColors(True)
        arvore.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        arvore.header().setStretchLastSection(True)

        candidatos_ordenados = sorted(
            self.resultado["candidatos"], key=lambda c: c["beneficio"], reverse=True)

        for c in candidatos_ordenados:
            item = QTreeWidgetItem([
                str(c["bus"]),
                str(c["modelo_bess"]["nome"]),
                f"{c['modelo_bess']['custo_brl']:,.2f}",
                str(c["beneficio"]),
                f"{c.get('beneficio_severidade', 0):.4f}",
                f"{c.get('beneficio_econ_anual', 0.0):.2f}",
            ])
            arvore.addTopLevelItem(item)

        layout.addWidget(arvore, 1)

    # ------------------------------------------------------------------ #
    def _montar_aba_reativo(self, container: QWidget) -> None:
        layout = QVBoxLayout(container)

        analise = self.resultado.get("analise_reativo")
        if not analise:
            rotulo = QLabel("Análise de reativo não disponível "
                            "(nenhuma alocação foi selecionada).")
            rotulo.setWordWrap(True)
            layout.addWidget(rotulo)
            layout.addStretch(1)
            return

        texto = (
            f"Potência ativa na fonte: {analise['kw_fonte']} kW\n"
            f"Potência reativa na fonte: {analise['kvar_fonte']} kvar\n"
            f"Fator de potência resultante: {analise['fator_potencia']}\n"
            f"Referência mínima (ANEEL PRODIST Módulo 8): {analise['fp_minimo_referencia']}\n"
            f"Situação: {'CONFORME' if analise['conforme'] else 'FORA DA FAIXA DE REFERÊNCIA'}\n"
        )
        rotulo = QLabel(texto)
        rotulo.setFont(fonte_padrao(10))
        rotulo.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        rotulo.setWordWrap(True)
        layout.addWidget(rotulo)

        if analise["recomendacao"]:
            rec = analise["recomendacao"]
            texto_rec = (
                f"Compensação recomendada: {rec['tipo']}\n\n"
                f"Parâmetros calculados:\n"
                + "\n".join(f"  {k}: {v}" for k, v in rec["parametros"].items())
                + "\n\nMemória de cálculo:\n"
                + "\n".join(f"  {k}: {v}" for k, v in rec["memoria_calculo"].items())
            )
            rotulo_rec = QLabel(texto_rec)
            rotulo_rec.setFont(fonte_padrao(9))
            rotulo_rec.setStyleSheet(
                f"color: {obter_paleta_ativa(detectar_tema()).aviso};")
            rotulo_rec.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            rotulo_rec.setWordWrap(True)
            rotulo_rec.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(rotulo_rec)

            if rec["tipo"] == "Reactor":
                nota = ("Nota de engenharia: para necessidades de compensação indutiva "
                        "de maior porte e/ou resposta dinâmica, uma alternativa é o uso "
                        "de máquina de indução operando como compensador, em vez de um "
                        "reator estático. Essa opção não é dimensionada automaticamente "
                        "nesta versão do módulo.")
                layout.addWidget(_rotulo_dica(nota))
        else:
            rotulo_ok = QLabel("Fator de potência dentro da faixa de referência - "
                               "nenhuma compensação adicional é necessária.")
            rotulo_ok.setFont(fonte_padrao(9))
            rotulo_ok.setStyleSheet(
                f"color: {obter_paleta_ativa(detectar_tema()).accent}; font-style: italic;")
            rotulo_ok.setWordWrap(True)
            layout.addWidget(rotulo_ok)

        layout.addStretch(1)

    # ------------------------------------------------------------------ #
    def _montar_aba_memorial(self, container: QWidget) -> None:
        layout = QVBoxLayout(container)

        barra_topo = QHBoxLayout()
        barra_topo.addWidget(_rotulo_negrito(
            "Memorial de cálculo detalhado (afundamento de tensão):"))
        barra_topo.addStretch(1)
        botao_salvar = QPushButton("💾 Salvar memorial (.txt)")
        botao_salvar.setStyleSheet(_estilo_botao_secundario())
        botao_salvar.clicked.connect(self._salvar_memorial_afundamento)
        barra_topo.addWidget(botao_salvar)
        layout.addLayout(barra_topo)

        texto_memorial = self.resultado.get(
            "memorial_calculo", "Memorial de cálculo não disponível para este estudo.")

        area_texto = QPlainTextEdit()
        area_texto.setFont(QFont("Consolas", 9))
        area_texto.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        area_texto.setPlainText(texto_memorial)
        area_texto.setReadOnly(True)
        layout.addWidget(area_texto, 1)

    def _salvar_memorial_afundamento(self) -> None:
        texto_memorial = self.resultado.get("memorial_calculo")
        if not texto_memorial:
            QMessageBox.warning(
                self, "Aviso",
                "Não há memorial de cálculo disponível para salvar.")
            return

        pasta_inicial = self.projeto.caminho_rede if self.projeto else ""
        caminho, _filtro = QFileDialog.getSaveFileName(
            self,
            "Salvar memorial de cálculo (afundamento)",
            os.path.join(pasta_inicial or "", "memorial_calculo_afundamento.txt"),
            "Arquivo de texto (*.txt)")
        if not caminho:
            return

        try:
            salvar_memorial(texto_memorial, caminho)
        except Exception as e:
            QMessageBox.critical(
                self, "Erro", f"Não foi possível salvar o arquivo:\n{e}")
            return

        QMessageBox.information(self, "Sucesso", f"Memorial salvo em:\n{caminho}")

    # ------------------------------------------------------------------ #
    def _montar_aba_economia(self, container: QWidget) -> None:
        layout = QVBoxLayout(container)

        resultado_economia = self.resultado.get("resultado_economia")
        memorial_economia_texto = self.resultado.get("memorial_economia")

        if not resultado_economia:
            texto_indisponivel = (
                "Análise de economia de energia não disponível.\n\n"
                "Isso ocorre quando:\n"
                "  - a opção 'Habilitar análise de economia de energia' estava "
                "desmarcada na configuração do estudo; OU\n"
                "  - nenhuma alocação de BESS foi selecionada pelo estudo de "
                "mitigação de afundamento (aba 'Alocação Selecionada' vazia) - "
                "a análise de economia é executada apenas sobre a configuração "
                "vencedora desse estudo.\n\n"
                "Para avaliar a economia de energia, ajuste os parâmetros do "
                "estudo (ex.: aumente o peso do custo, reduza restrições, ou "
                "force uma seleção) até que ao menos uma alocação seja "
                "escolhida, e refaça o estudo com a opção de economia habilitada.")
            rotulo = QLabel(texto_indisponivel)
            rotulo.setFont(fonte_padrao(9))
            rotulo.setWordWrap(True)
            rotulo.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            layout.addWidget(rotulo)
            layout.addStretch(1)
            return

        texto_payback = (
            f"{resultado_economia['payback_anos']:.2f} ano(s)"
            if resultado_economia.get("payback_anos") is not None
            else "não calculado"
        )

        texto_resumo = (
            f"Tarifa: {resultado_economia['tarifa'].nome} | "
            f"Horário de ponta: {resultado_economia['horario_ponta_inicio']:02d}h–"
            f"{resultado_economia['horario_ponta_fim']:02d}h\n"
            f"Custo diário SEM BESS: R$ {resultado_economia['custo_diario_base']:.2f}   "
            f"|   Custo diário COM BESS: R$ {resultado_economia['custo_diario_bess']:.2f}\n"
            f"Economia diária: R$ {resultado_economia['economia_diaria']:.2f}   "
            f"|   Economia mensal: R$ {resultado_economia['economia_mensal']:.2f}   "
            f"|   Economia anual: R$ {resultado_economia['economia_anual']:.2f}\n"
            f"Payback simples (energia): {texto_payback}"
        )
        if resultado_economia.get("alerta_caso_base_exportacao"):
            texto_resumo += (
                "\nATENÇÃO: o caso base exporta energia em boa parte do dia e a "
                "exportação não é monetizada neste modelo — a arbitragem tende a "
                "ficar negativa; use curvas de carga/geração realistas no projeto."
            )
        rotulo_resumo = QLabel(texto_resumo)
        rotulo_resumo.setFont(fonte_padrao(10))
        rotulo_resumo.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        rotulo_resumo.setWordWrap(True)
        if resultado_economia["economia_diaria"] > 0:
            rotulo_resumo.setStyleSheet(
                f"color: {obter_paleta_ativa(detectar_tema()).accent}; font-weight: 600;")
        layout.addWidget(rotulo_resumo)

        barra_topo = QHBoxLayout()
        barra_topo.addWidget(_rotulo_negrito(
            "Memorial de cálculo detalhado (perfil horário):"))
        barra_topo.addStretch(1)
        botao_salvar = QPushButton("💾 Salvar memorial (.txt)")
        botao_salvar.setStyleSheet(_estilo_botao_secundario())
        botao_salvar.clicked.connect(self._salvar_memorial_economia)
        barra_topo.addWidget(botao_salvar)
        layout.addLayout(barra_topo)

        area_texto = QPlainTextEdit()
        area_texto.setFont(QFont("Consolas", 9))
        area_texto.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        area_texto.setPlainText(memorial_economia_texto or "")
        area_texto.setReadOnly(True)
        layout.addWidget(area_texto, 1)

    def _salvar_memorial_economia(self) -> None:
        texto_memorial = self.resultado.get("memorial_economia")
        if not texto_memorial:
            QMessageBox.warning(
                self, "Aviso",
                "Não há memorial de economia disponível para salvar.")
            return

        pasta_inicial = self.projeto.caminho_rede if self.projeto else ""
        caminho, _filtro = QFileDialog.getSaveFileName(
            self,
            "Salvar memorial de cálculo (economia de energia)",
            os.path.join(pasta_inicial or "", "memorial_calculo_economia.txt"),
            "Arquivo de texto (*.txt)")
        if not caminho:
            return

        try:
            salvar_memorial_economia(texto_memorial, caminho)
        except Exception as e:
            QMessageBox.critical(
                self, "Erro", f"Não foi possível salvar o arquivo:\n{e}")
            return

        QMessageBox.information(self, "Sucesso", f"Memorial salvo em:\n{caminho}")

    # ------------------------------------------------------------------ #
    def _aplicar_ao_projeto(self) -> None:
        if not self.resultado["selecionados"]:
            QMessageBox.information(
                self, "Aviso", "Não há alocação selecionada para aplicar.")
            return

        if not confirmar_win11(
                "Confirmar",
                "Isso irá adicionar o(s) BESS selecionado(s) - e a compensação "
                "reativa recomendada, se houver - na rede do projeto atual, e "
                "reexportar os arquivos .dss.\n\n"
                "A rede será recarregada diretamente do arquivo salvo em disco "
                "(rede.json) antes de aplicar as mudanças, para evitar conflito "
                "com alterações feitas em paralelo no Editor de Rede.\n\n"
                "Deseja continuar?",
                parent=self):
            return

        caminho_rede_json = os.path.join(self.projeto.caminho_rede, "rede.json")
        if os.path.exists(caminho_rede_json):
            try:
                rede_atual = RedeEletrica.carregar_json(caminho_rede_json)
            except Exception as e:
                QMessageBox.critical(
                    self, "Erro",
                    f"Não foi possível recarregar a rede do projeto:\n{e}")
                return
        else:
            rede_atual = self.rede

        barras_ausentes = [
            c["bus"] for c in self.resultado["selecionados"]
            if c["bus"] not in rede_atual.barras
        ]
        if barras_ausentes:
            QMessageBox.critical(
                self, "Erro",
                "As seguintes barras não existem mais na rede atual do projeto "
                f"(podem ter sido removidas/renomeadas): {', '.join(barras_ausentes)}.\n\n"
                "Refaça o estudo com a rede atualizada antes de aplicar.")
            return

        for c in self.resultado["selecionados"]:
            nome_bess_base = f"BESS_{c['bus']}"
            barra = rede_atual.barras.get(c["bus"])
            kv_linha = barra.kv_base if barra else 0.38

            nome_final = rede_atual.adicionar_derivacao(
                "Storage", nome_bess_base, c["bus"],
                {
                    "phases": 3,
                    "kv": kv_linha,
                    "kwrated": c["modelo_bess"]["kw"],
                    "kwhrated": c["modelo_bess"]["kwh"],
                    "pctstored": 50,
                    "dispmode": "default",
                    "state": "idling",
                })

            if nome_final != nome_bess_base:
                QMessageBox.information(
                    self, "Nome ajustado automaticamente",
                    f"Já existia um elemento chamado '{nome_bess_base}'.\n"
                    f"Este foi criado como '{nome_final}'.")

        analise = self.resultado.get("analise_reativo")
        if analise and analise["recomendacao"]:
            rec = analise["recomendacao"]
            bus_referencia = self.resultado["selecionados"][0]["bus"]
            nome_elemento_base = "Capacitor_Otim" if rec["tipo"] == "Capacitor" else "Reator_Otim"

            tipo_openDSS = "Capacitor" if rec["tipo"] == "Capacitor" else "Reactor"
            parametros_reativo = dict(rec["parametros"])

            try:
                nome_final_reativo = rede_atual.adicionar_derivacao(
                    tipo_openDSS, nome_elemento_base, bus_referencia, parametros_reativo)

                if nome_final_reativo != nome_elemento_base:
                    QMessageBox.information(
                        self, "Nome ajustado automaticamente",
                        f"Já existia um elemento chamado '{nome_elemento_base}'.\n"
                        f"Este foi criado como '{nome_final_reativo}'.")
            except ValueError as e:
                QMessageBox.warning(
                    self, "Aviso",
                    "O BESS foi adicionado com sucesso, mas não foi possível "
                    f"adicionar automaticamente o elemento de compensação reativa "
                    f"recomendado ({rec['tipo']}):\n{e}\n\n"
                    "Adicione manualmente pelo Editor de Rede, se necessário.")

        rede_atual.salvar_json(caminho_rede_json)

        try:
            gerar_arquivos_dss(rede_atual, self.projeto.caminho_rede,
                               pasta_curvas=self.projeto.caminho_curvas)
        except ValueError as e:
            QMessageBox.warning(
                self, "Aviso",
                "A rede foi atualizada e salva, mas houve um erro ao reexportar "
                f"automaticamente os arquivos .dss:\n{e}\n\n"
                "Abra o Editor de Rede e exporte manualmente pelo menu "
                "'Arquivo > Exportar arquivos .dss'.")
            return

        QMessageBox.information(
            self, "Sucesso",
            "Alocação de BESS aplicada ao projeto com sucesso!\n\n"
            "A rede foi atualizada e os arquivos .dss foram reexportados.\n"
            "Abra o Editor de Rede para visualizar as mudanças, ou rode uma "
            "nova simulação para validar os resultados.")

        self.close()


# ============================================================
# Orquestração: configuração -> execução em thread -> progresso -> resultados
# ============================================================

_INTERVALO_FILA_MS = 100


def abrir_dialogo_configuracao(projeto: Projeto, rede: RedeEletrica,
                               caminho_master: str, parent=None):
    """Ponto de entrada do Módulo de Otimização de Alocação de BESS.

    Condição de uso que precisa ficar clara: esta função exige um laço de
    eventos Qt ativo. A configuração é resolvida de forma modal via
    ``exec()``, mas o avanço do progresso e a abertura dos resultados
    dependem do laço do chamador - chamá-la de um processo sem laço deixa a
    janela de progresso parada.

    Na migração Tkinter -> PySide6 a assinatura era
    ``abrir_dialogo_configuracao(parent_tk, projeto, rede, caminho_master)``.
    O ``parent`` Tk não existe mais; no lugar há um ``parent`` QWidget
    opcional, usado apenas como ancestral dos diálogos. O bombeamento da
    fila da thread também mudou: era ``parent.after(100, ...)`` e agora é
    ``QTimer.singleShot(100, ...)``.
    """

    config_dialog = ConfiguracaoEstudoDialog(parent, projeto, rede)
    config_dialog.exec()
    config = config_dialog.resultado
    if config is None:
        return  # usuário cancelou a configuração: nada a executar

    app = QApplication.instance()

    fila_eventos = queue.Queue()
    progresso_dialog = ProgressoDialog(parent)
    resultado_container = {"valor": None, "erro": None}
    estado = {"concluido": False}

    def callback_progresso(passo_atual, total):
        percentual = (passo_atual / total) * 100 if total else 0
        fila_eventos.put(("progresso", percentual, None))

    def callback_status(mensagem):
        fila_eventos.put(("status", None, mensagem))

    def tarefa_em_thread():
        """Corpo do estudo, executado fora da thread da interface.

        O estudo roda sobre uma exportação temporária da rede. O rede.json é
        a fonte da verdade; gerar os .dss em pasta temporária permite que as
        curvas padrão do dia escolhido entrem na simulação sem tocar em
        nenhum artefato .dss do projeto. Um erro aqui é guardado no
        container, e não levantado: quem o transforma em mensagem para o
        usuário é o laço principal, no passo "concluido".
        """
        pasta_temp = None
        try:
            pasta_temp = tempfile.mkdtemp(prefix="otim_bess_")
            caminho_master_usado = gerar_arquivos_dss(
                rede,
                pasta_temp,
                pasta_curvas=projeto.caminho_curvas,
                dia_curvas_padrao=config.get("dia_curvas_padrao", "Segunda"))
            resultado = otimizacao_bess.executar_estudo_completo(
                caminho_master=caminho_master_usado,
                barras_candidatas=config["barras_candidatas"],
                barras_falta=config["barras_falta"],
                tipos_falta=config["tipos_falta"],
                max_unidades=config["max_unidades"],
                peso_custo=config["peso_custo"],
                custo_maximo=config["custo_maximo"],
                tarifa=config.get("tarifa"),
                horario_ponta_inicio=config.get("horario_ponta_inicio", 18),
                horario_ponta_fim=config.get("horario_ponta_fim", 21),
                dias_equivalentes_mes=config.get("dias_equivalentes_mes", 22),
                callback_progresso=callback_progresso,
                callback_status=callback_status,
            )
            resultado_container["valor"] = resultado
        except Exception as e:
            resultado_container["erro"] = e
        finally:
            if pasta_temp:
                shutil.rmtree(pasta_temp, ignore_errors=True)
            fila_eventos.put(("concluido", None, None))

    def processar_fila():
        if estado["concluido"]:
            return

        try:
            while True:
                tipo_evento, percentual, mensagem = fila_eventos.get_nowait()

                if tipo_evento == "progresso":
                    progresso_dialog.atualizar(percentual)
                elif tipo_evento == "status":
                    progresso_dialog.atualizar(progresso_dialog.barra.value(), mensagem)
                elif tipo_evento == "concluido":
                    estado["concluido"] = True
                    progresso_dialog.close()
                    progresso_dialog.deleteLater()

                    if resultado_container["erro"] is not None:
                        QMessageBox.critical(
                            parent, "Erro durante o estudo",
                            f"Ocorreu um erro durante a execução do estudo:\n"
                            f"{resultado_container['erro']}")
                        return
                    try:
                        dialogo = ResultadosDialog(
                            parent, projeto, rede, resultado_container["valor"])
                    except Exception:
                        # Sem este tratamento, uma exceção ao montar o
                        # relatório matava o processo em silêncio: o módulo
                        # roda em subprocesso sem captura de saída, e o
                        # usuário via só a janela "piscar e fechar". Aqui se
                        # registra a exceção, avisa e segue vivo.
                        _, caminho_log = _registrar_excecao(
                            "construção do ResultadosDialog",
                            *sys.exc_info())
                        QMessageBox.critical(
                            parent, "Erro ao montar o relatório",
                            "Não foi possível montar a janela de resultados.\n"
                            + (f"Detalhes técnicos salvos em:\n{caminho_log}"
                               if caminho_log else ""))
                        return

                    # Causa raiz do "pisca e fecha", comprovada por
                    # reprodução offscreen: o diálogo top-level (parent=None)
                    # nasce em variável local do callback e, ao retornar, o
                    # coletor de lixo leva o wrapper e destrói a janela. A
                    # referência abaixo a mantém viva até o fechamento.
                    _dialogos_resultado.append(dialogo)
                    dialogo.finished.connect(
                        lambda *_: _remover_dialogo_resultado(dialogo))
                    dialogo.show()
                    return
        except queue.Empty:
            # Fila vazia é o caso normal: a thread ainda não produziu nada
            # neste intervalo. O laço apenas reagenda.
            pass

        QTimer.singleShot(_INTERVALO_FILA_MS, processar_fila)

    thread = threading.Thread(target=tarefa_em_thread, daemon=True)
    thread.start()

    progresso_dialog.show()
    if app is not None:
        app.processEvents()

    QTimer.singleShot(_INTERVALO_FILA_MS, processar_fila)
