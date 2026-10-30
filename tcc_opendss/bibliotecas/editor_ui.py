__author__ = 'Pedro Henrique Sousa Pinheiro'
"""View: editor da rede elétrica. Criação/edição feita 100% por formulários
com listas suspensas (Combobox). Duplo clique na lista de elementos abre o
formulário de edição já preenchido, permitindo inclusive trocar o TIPO do
elemento. Elementos de Carga, Gerador, PVSystem e Storage ganham três
botões 📈 independentes para definir as curvas 'daily', 'duty' e 'yearly'.

O canvas sempre recalcula escala e centralização automaticamente (fit-to-
view), garantindo que todo o circuito fique visível. O posicionamento dos
elementos conectados (leque ao redor da barra) é calculado dinamicamente,
buscando o maior espaço angular livre em relação às linhas/ramos já
conectados àquela barra, evitando sobreposição.

Sistema BESS composto: o botão "🔋 Sistema BESS" cria, num único fluxo,
até 4 elementos DSS internos (Storage + InvControl + Capacitor/Reactor
opcionais), agrupados logicamente pelo campo 'grupo' de cada elemento.
Na árvore de elementos, esses elementos aparecem agrupados sob um nó
"🔋 Sistema BESS: <nome>". O InvControl não possui posição física própria
(bus1=None) e por isso não aparece desenhado no canvas, apenas na árvore.

TRANSPARÊNCIA TÉCNICA (migração Tkinter → PySide6 — último módulo da
migração):

- `tk.Frame` → `QWidget`: `EditorRede` agora é um `QWidget` (widget
  central, embutido pelo lançador `bibliotecas/editor_rede.py`). A
  assinatura pública mudou de `EditorRede(master, rede=None, projeto=None)`
  para `EditorRede(rede=None, projeto=None)` — o `master` Tk não existe
  mais; a janela (título/tamanho) é responsabilidade do lançador. Os
  demais métodos públicos mantêm o MESMO nome e a MESMA semântica
  (`novo_projeto`, `salvar_projeto`, `abrir_projeto`, `exportar_dss`,
  `simular`, `redesenhar`), e `configurar_menu(qmainwindow)` passa a
  ser o ponto de injeção do menu "Arquivo" na barra de menus da
  `QMainWindow` (o Tk fazia isso via `master.config(menu=...)`).

- `tk.Canvas` → `QGraphicsScene`/`QGraphicsView`: o desenho é feito com
  itens de cena (`QGraphicsEllipseItem` para barras, `QGraphicsLineItem`
  para ramos/ligacões, `QGraphicsRectItem` para as caixas do leque,
  `QGraphicsTextItem` para rótulos). O auto-encaixe NÃO usa o sistema de
  transformação do `QGraphicsView`: a matemática de escala/centralização
  de `_transformar_posicoes` é portada VERBATIM e aplicada às coordenadas
  dos itens (equivalente ao que o Tk fazia em `create_oval`/`create_line`),
  preservando exatamente o enquadramento e as constantes fixas em pixels
  do leque (RAIO_LEQUE, MEIA_LARGURA_CAIXA...).

- `messagebox`/`filedialog`/`simpledialog` → `QMessageBox` (ou
  `mostrar_aviso_win11`/`confirmar_win11` de `ui_win11`) e `QFileDialog`.
  Os textos (títulos, frases, avisos) foram preservados VERBATIM.

- `ttk.Treeview` → `QTreeWidget`: a identidade do item deixa de ser o
  `iid` "categoria::nome" e passa a ser o par (categoria, nome) guardado
  em `Qt.UserRole` nos dados do item. A semântica (grupos "Barras",
  "Ramos", "Conectados", nós "🔋 Sistema BESS: <nome>", sufixo " 📈" de
  curva e resumos de parâmetros) é idêntica à do original.

- `tk.Button`/`tk.Label`/`tk.Radiobutton`/`tk.Menu` → `QPushButton`/
  `QLabel`/`QRadioButton`/`QMenu` + `QAction`, com `fonte_padrao` e a
  paleta de `ui_win11`.

- DIVERGÊNCIA DELIBERADA (seleção visual no canvas): no Tk original o
  `Canvas` não tinha seleção de itens nem arraste (o estado do grafo era
  reconstruído a cada `redesenhar()`). Aqui as barras são itens móveis
  (`ItemIsMovable | ItemIsSelectable`) e, ao serem soltas, atualizam a
  posição em `self._posicoes` (posição de tela já transformada). Como o
  layout continua sendo 100% automático — qualquer `redesenhar()`
  recalcula tudo —, o arraste é um ajuste visual transitório, não um
  atributo persistido no modelo (`Barra` não possui campo de posição).
  Nada é gravado em `rede.json`; o comportamento de persistência é
  idêntico ao original.

- DIVERGÊNCIA DELIBERADA (Organização interna): o original guardava a
  árvore em `self.tree` (Treeview) e o canvas em `self.canvas`. Para
  manter os mesmos identificadores onde fazia sentido, `self.tree` agora é
  o `QTreeWidget` (com a mesma API semântica: `_atualizar_lista_elementos`,
  `_excluir_selecionado`, duplo clique) e `self.canvas` foi substituído
  por `self.view`/`self.cena` (QGraphicsView/QGraphicsScene). Também
  `self.orientacao_var` (StringVar) virou `self.orientacao` (str python).

- O `after(50, self.redesenhar)` do Tk foi substituído por
  `QTimer.singleShot(0, self.redesenhar)` — o layout só tem dimensão útil
  após o primeiro ciclo de eventos.
"""

import os

# MPLBACKEND deve ser definido ANTES de qualquer import de terceiros
# (matplotlib é importado indiretamente pelo editor de curvas).
os.environ.setdefault("MPLBACKEND", "QtAgg")

import math
import tempfile
from typing import Dict, List, Optional

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .modelo_rede import RedeEletrica
from .exportador_dss import gerar_arquivos_dss
from .exportador_arduino import NOME_ARQUIVO as NOME_ARQUIVO_PARAM_ARDUINO
from .exportador_arduino import gerar_parametrizacao_arduino
from .layout_automatico import calcular_posicoes
from .dialogos import pedir_valores
from .projeto import Projeto
from .repositorio_modelos import NOME_ARQUIVO_POR_TIPO, listar_modelos
from .sistema_bess import (
    abrir_formulario_sistema_bess,
    MODOS_INVCONTROL,
    CURVA_VOLTVAR_PADRAO_NOME,
    CURVA_VOLTVAR_PADRAO_PONTOS,
    CURVA_VOLTWATT_PADRAO_NOME,
    CURVA_VOLTWATT_PADRAO_PONTOS,
)
from .ui_win11 import COR_ACCENT_MARCA, confirmar_win11, fonte_padrao


TIPOS_RAMO = ["Line", "Switch", "Transformer"]

# NOTA: "InvControl" propositalmente NÃO está nesta lista. Ele não tem
# barra própria (bus1=None) e só faz sentido dentro de um Sistema BESS
# composto, referenciando um Storage via DERList. Por isso, a troca de
# tipo genérica (usada na edição via duplo clique) não o inclui como
# opção — ele é gerenciado apenas através do fluxo de Sistema BESS
# (criação) ou do editor dedicado _editar_invcontrol (edição pontual
# do modo de controle).
#
# NOTA 2: "Storage" permanece nesta lista (mesmo o botão de criação
# avulsa tendo sido substituído por "Sistema BESS") para não quebrar a
# edição de um Storage já existente (inclusive os que pertencem a um
# Sistema BESS, acessados via duplo clique na árvore). Isso significa
# que, em tese, um elemento avulso qualquer ainda pode ser convertido
# manualmente para "Storage" via edição — um Storage criado dessa forma
# fica SEM InvControl associado. Considerado um caso de borda aceitável;
# avise se preferir bloquear essa conversão também.
TIPOS_DERIVACAO = ["Load", "Generator", "Capacitor", "PVSystem", "Storage", "Reactor", "Vsource"]

# Elementos para os quais faz sentido definir curvas características.
# A "natureza" define apenas o rótulo do eixo % mostrado no editor gráfico.
TIPOS_COM_CURVA = {
    "Load": "carga",
    "Generator": "geracao",
    "PVSystem": "geracao",
    "Storage": "carga",
}

# Propriedades de curva suportadas (chave usada nos parametros do elemento,
# rótulo exibido no formulário). O 'modo' passado ao editor gráfico é a
# própria chave (coincide com o nome da propriedade do OpenDSS).
PROPRIEDADES_CURVA = [
    ("daily", "Curva diária (daily, 24h)"),
    ("duty", "Curva de duty cycle (duty, curto período)"),
    ("yearly", "Curva anual (yearly, por dia do ano)"),
]

CAMPOS_BARRA = [
    ("nome", "Nome da barra", "texto", ""),
    ("kv_base", "Tensão base (kV)", "texto", "13.8"),
]

# TRANSPARÊNCIA TÉCNICA — campos opcionais de linha e de transformador
# ---------------------------------------------------------------------
# Campo deixado VAZIO = comportamento atual, e o comportamento atual é o do
# motor (dss-python 0.15.7), que aplica defaults NÃO-nulos quando o parâmetro
# não é declarado. Medido no motor real nesta revisão:
#   * Transformer de 2 enrolamentos sem %loadloss: R série efetiva ≈ 0,4043 %
#     (o motor soma dois %r default de 0,2 %, um por enrolamento);
#   * Line sem c1/c0: C1 = 3,4 nF/km e C0 = 1,6 nF/km.
# Esses valores não vêm do usuário — são fantasma do default. Preencher os
# campos com dado REAL de placa/ensaio/catálogo remove o fantasma; o software
# não inventa estimativa nenhuma (campo vazio nunca é "completado" aqui).
# Hierarquia medida: %r explícito (inclusive 0) ANULA %loadloss. O editor não
# expõe %r em trafo, então essa armadilha não é alcançável por esta via.
#
# ARMADILHA MEDIDA (motor real, nesta revisão): %noloadloss SOZINHO não
# corrige perdas — ele desloca o ponto de operação. Trafo 100 kVA 13,8/0,4 kV
# xhl=5 %: só %noloadloss=0,25 -> série salta de 454,7 W para 1.387,5 W
# (a perda a vazio virou parcela em série). Com %loadloss=1,2 declarado:
# série 1.393,6 W + núcleo 235,7 W, coerente com os 1,2 % + 0,25 % de placa.
# Regra: preencha os dois campos como um PAR (é assim que vem do ensaio).
# Nomenclatura: a chave interna é sem "%" ("loadloss"/"noloadloss"); o "%" é
# recolocado no comando .dss pelo exportador (precedente: "pctstored" ->
# "%stored=" em _fmt_storage).

CAMPOS_RAMO_PARAMS = {
    "Line": [
        ("phases", "Fases", "combobox", ["3", "1", "2"]),
        ("length", "Comprimento", "texto", "1"),
        ("units", "Unidade", "combobox", ["km", "m", "ft", "mi", "kft"]),
        ("linecode", "Linecode (opcional)", "texto", ""),
        ("r1", "R1 (ohm/unid)", "texto", "0.1"),
        ("x1", "X1 (ohm/unid)", "texto", "0.2"),
        ("r0", "R0 (ohm/unid)", "texto", "0.3"),
        ("x0", "X0 (ohm/unid)", "texto", "0.4"),
        ("c1", "C1 (nF/km, opcional)", "texto", ""),
        ("c0", "C0 (nF/km, opcional)", "texto", ""),
    ],
    "Switch": [
        ("phases", "Fases", "combobox", ["3", "1", "2"]),
        ("fechada", "Estado inicial", "combobox", ["yes", "no"]),
    ],
    "Transformer": [
        ("phases", "Fases", "combobox", ["3", "1"]),
        ("kv1", "kV Primário", "texto", "13.8"),
        ("kv2", "kV Secundário", "texto", "0.38"),
        ("kva", "kVA", "texto", "150"),
        ("conn1", "Conexão Primário", "combobox", ["wye", "delta"]),
        ("conn2", "Conexão Secundário", "combobox", ["wye", "delta"]),
        ("xhl", "%XHL", "texto", "2.0"),
        ("loadloss", "%LoadLoss — R série do ensaio (%), opcional", "texto", ""),
        ("noloadloss", "%NoLoadLoss — perdas a vazio (%), opcional", "texto", ""),
    ],
}

CAMPOS_DERIVACAO_PARAMS = {
    "Load": [
        ("phases", "Fases", "combobox", ["3", "1", "2"]),
        ("kv", "kV", "texto", "0.38"),
        ("kw", "kW", "texto", "10"),
        ("kvar", "kvar", "texto", "3"),
        ("model", "Model (1-8)", "combobox", [str(i) for i in range(1, 9)]),
        ("conn", "Conexão", "combobox", ["wye", "delta"]),
    ],
    "Generator": [
        ("phases", "Fases", "combobox", ["3", "1"]),
        ("kv", "kV", "texto", "0.38"),
        ("kw", "kW", "texto", "50"),
        ("kvar", "kvar", "texto", "0"),
        ("model", "Model (1-7)", "combobox", [str(i) for i in range(1, 8)]),
    ],
    "Capacitor": [
        ("phases", "Fases", "combobox", ["3", "1"]),
        ("kv", "kV", "texto", "13.8"),
        ("kvar", "kvar", "texto", "300"),
    ],
    "PVSystem": [
        ("phases", "Fases", "combobox", ["3", "1"]),
        ("kv", "kV", "texto", "0.38"),
        ("kva", "kVA do inversor", "texto", "100"),
        ("pmpp", "Pmpp (kW)", "texto", "100"),
        ("irradiance", "Irradiância (kW/m²)", "texto", "1.0"),
        ("cutin", "%CutIn", "texto", "2"),
        ("cutout", "%CutOut", "texto", "2"),
    ],
    "Storage": [
        ("phases", "Fases", "combobox", ["3", "1"]),
        ("kv", "kV", "texto", "0.38"),
        ("kwrated", "kW nominal", "texto", "50"),
        ("kwhrated", "kWh nominal", "texto", "100"),
        ("pctstored", "%Stored (SoC inicial)", "texto", "50"),
        ("dispmode", "DispMode", "combobox",
         ["default", "loadshape", "follow", "support", "external"]),
        ("state", "State inicial", "combobox",
         ["charging", "idling", "discharging"]),
    ],
    "Reactor": [
        ("phases", "Fases", "combobox", ["3", "1"]),
        ("kv", "kV", "texto", "13.8"),
        ("kvar", "kvar", "texto", "300"),
    ],
    "Vsource": [
        ("phases", "Fases", "combobox", ["3", "1"]),
        ("basekv", "kV Base", "texto", "13.8"),
        ("pu", "Tensão (pu)", "texto", "1.0"),
        ("mvasc3", "MVAsc Trifásico", "texto", "2000"),
        ("mvasc1", "MVAsc Monofásico", "texto", "2100"),
    ],
}

CORES = {
    "Line": "black", "Switch": "orange", "Transformer": "purple",
    "Load": "steelblue", "Generator": "darkgreen", "Capacitor": "brown",
    # TRANSPARÊNCIA TÉCNICA: "gold" (#FFD700) sumia no fundo branco da
    # cena (ligação pontilhada e caixa do leque praticamente invisíveis).
    # "goldenrod" (#DAA520) preserva a semântica "dourado" com contraste
    # legível sobre branco.
    "PVSystem": "goldenrod", "Storage": "teal", "Reactor": "sienna",
    "Vsource": "red",
}

# ------------------------------------------------------------------ #
# Constantes de desenho do "leque" de elementos conectados.
# IMPORTANTE: estes valores são FIXOS em pixels (não escalam com o
# zoom do auto-encaixe), evitando que, em redes pequenas (onde a
# escala calculada é grande), os ícones sejam "empurrados" para fora
# da área visível do canvas.
# ------------------------------------------------------------------ #
RAIO_BARRA_BASE = 8
RAIO_LEQUE = 58
MEIA_LARGURA_CAIXA = 26
MEIA_ALTURA_CAIXA = 13

# Margem fixa (pixels) reservada no auto-encaixe. Precisa ser maior que
# RAIO_LEQUE + max(MEIA_LARGURA_CAIXA, MEIA_ALTURA_CAIXA) + espaço para
# rótulo de texto, para garantir que nenhum elemento fique cortado.
MARGEM_FIT = 150


def _qcolor(nome: str) -> QColor:
    """Converte um nome de cor do Tk (ex.: 'steelblue') em QColor.

    QColor suporta SVG/X11 color names, que é exatamente o mesmo conjunto
    de nomes aceito pelo Tk — nenhuma cor da paleta CORES precisou mudar.
    """
    cor = QColor(nome)
    return cor if cor.isValid() else QColor("black")


def _escurecer(nome: str, fator: float) -> str:
    """Escurece uma cor hexadecimal/por nome preservando o tom (usado no
    :hover dos botões do painel)."""
    cor = _qcolor(nome)
    return cor.darker(int(round(100 / max(fator, 0.01)))).name()


def _cor_texto_sobre(nome_cor: str) -> str:
    """Branco ou preto conforme a luminância percebida do fundo
    (0.299R + 0.587G + 0.114B >= 128 -> texto preto, senão branco)."""
    cor = _qcolor(nome_cor)
    luminancia = 0.299 * cor.red() + 0.587 * cor.green() + 0.114 * cor.blue()
    return "black" if luminancia >= 128 else "white"


def _cor_texto_id() -> str:
    """Cor do rótulo de identificação do projeto — azul institucional."""
    return COR_ACCENT_MARCA


class _BarraItem(QGraphicsEllipseItem):
    """Barra da rede desenhada como elipse (substitui o create_oval do Tk).

    Móvel e selecionável: quando arrastada, grava a posição de tela de
    volta em `editor._posicoes[nome]` (ajuste visual transitório — o
    layout continua automático; ver TRANSPARÊNCIA TÉCNICA).
    """

    def __init__(self, nome: str, raio: float, editor: "EditorRede"):
        super().__init__(QRectF(-raio, -raio, 2 * raio, 2 * raio))
        self.nome_barra = nome
        self._editor = editor
        self._raio = raio
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        # ItemSendsGeometryChanges é OBRIGATÓRIO para receber
        # ItemPositionHasChanged em itemChange(); sem esta flag o Qt não
        # notifica mudanças de geometria (o arraste ficaria "mudo").
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        # Z-order: barras por cima dos ramos, abaixo dos rótulos.
        self.setZValue(2.0)

    def paint(self, painter, option, widget=None):
        selecionado = self.isSelected()
        painter.setPen(QPen(_qcolor("black"), 2))
        painter.setBrush(QBrush(_qcolor("white")))
        painter.drawEllipse(self.rect())
        if selecionado:
            # Seleção visual (não existia no Tk: o Canvas não tinha
            # estado de seleção). Anel tracejado por fora da elipse.
            pen = QPen(_qcolor("red"), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = self._raio + 4
            painter.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))

    def itemChange(self, change, value):
        # Replica o "arraste" que o usuário fazia sobre o Canvas do Tk:
        # a cada mudança de posição, sincroniza a posição de tela com o
        # dicionário usado por redesenhar(). Não altera o modelo.
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
                and self._editor is not None):
            self._editor._ao_mover_barra(self.nome_barra, self.pos())
        return super().itemChange(change, value)


class _RotuloItem(QGraphicsTextItem):
    """Rótulo com retângulo de fundo atrás (replica _desenhar_rotulo do Tk:
    `create_text` seguido de `create_rectangle` + `tag_lower`).

    TRANSPARÊNCIA TÉCNICA: `fundo=None` desativa o retângulo. Usado nos
    rótulos desenhados DENTRO das caixas de derivação, onde o retângulo
    branco cobria o preenchimento colorido do elemento."""

    def __init__(self, texto: str, cor: str, tamanho_fonte: int = 8,
                 fundo: str = "white"):
        super().__init__(texto)
        self.setDefaultTextColor(_qcolor(cor))
        fonte = QFont()
        fonte.setPointSizeF(max(5.0, float(tamanho_fonte)))
        self.setFont(fonte)
        self.setTextWidth(-1)
        self._cor_fundo = _qcolor(fundo) if fundo is not None else None
        self._tamanho_fonte = tamanho_fonte
        self.setZValue(1.0)

    def paint(self, painter, option, widget=None):
        # Fundo branco com 3px de folga horizontal e 1px vertical,
        # exatamente como no original (x0-3, y0-1, x1+3, y1+1).
        if self._cor_fundo is not None:
            rect = self.boundingRect().adjusted(-3, -1, 3, 1)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self._cor_fundo))
            painter.drawRect(rect)
        else:
            # Sem fundo: não pinta retângulo algum (herda o do elemento).
            painter.setBrush(Qt.BrushStyle.NoBrush)
        super().paint(painter, option, widget)


class EditorRede(QWidget):
    def __init__(self, rede: RedeEletrica = None, projeto: Projeto = None):
        super().__init__()
        self.rede = rede or RedeEletrica()
        self.projeto = projeto
        self.orientacao = "vertical"

        # Posições de tela (já transformadas pelo auto-encaixe) da última
        # renderização. Reconstruídas a cada redesenhar().
        self._posicoes: Dict[str, tuple] = {}
        self._escala: float = 1.0
        self._redesenhando = False

        self._montar_layout()
        self._carregar_projeto_automaticamente()
        # Equivalente ao self.after(50, self.redesenhar) do Tk: o layout
        # só tem dimensão útil depois do primeiro ciclo de eventos.
        QTimer.singleShot(0, self.redesenhar)

    # ------------------------------------------------------------------ #
    def _carregar_projeto_automaticamente(self):
        if not self.projeto:
            return

        caminho_rede_json = os.path.join(self.projeto.caminho_rede, "rede.json")
        if os.path.exists(caminho_rede_json):
            try:
                self.rede = RedeEletrica.carregar_json(caminho_rede_json)
            except Exception as e:
                QMessageBox.warning(
                    self, "Aviso",
                    f"Não foi possível carregar a rede salva do projeto:\n{e}")

    # ------------------------------------------------------------------ #
    def configurar_menu(self, qmainwindow):
        """Cria a barra de menus da QMainWindow hospedeira (o Tk fazia o
        equivalente em _montar_menu(), via `self.master.config(menu=...)`).
        """
        menubar = qmainwindow.menuBar()
        menubar.clear()

        menu_arquivo = menubar.addMenu("Arquivo")

        acao_novo = QAction("Novo projeto", qmainwindow)
        acao_novo.triggered.connect(self.novo_projeto)
        menu_arquivo.addAction(acao_novo)

        acao_salvar = QAction("Salvar rede (.json)", qmainwindow)
        acao_salvar.triggered.connect(self.salvar_projeto)
        menu_arquivo.addAction(acao_salvar)

        acao_abrir = QAction("Abrir rede (.json)", qmainwindow)
        acao_abrir.triggered.connect(self.abrir_projeto)
        menu_arquivo.addAction(acao_abrir)

        menu_arquivo.addSeparator()

        acao_exportar = QAction("Exportar arquivos .dss", qmainwindow)
        acao_exportar.triggered.connect(self.exportar_dss)
        menu_arquivo.addAction(acao_exportar)

        acao_exportar_arduino = QAction(
            "Exportar parametrização Arduino (microrrede)", qmainwindow)
        acao_exportar_arduino.triggered.connect(
            self.exportar_parametrizacao_arduino)
        menu_arquivo.addAction(acao_exportar_arduino)

        self.menubar = menubar

    # ------------------------------------------------------------------ #
    def _montar_layout(self):
        layout_principal = QHBoxLayout(self)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        # ---------------- Painel de ferramentas (esquerda) ----------------
        painel_ferramentas = QFrame()
        painel_ferramentas.setFrameShape(QFrame.Shape.StyledPanel)
        painel_ferramentas.setFixedWidth(220)
        self.painel_ferramentas = painel_ferramentas

        coluna = QVBoxLayout(painel_ferramentas)
        coluna.setContentsMargins(6, 8, 6, 8)
        coluna.setSpacing(4)

        if self.projeto:
            label_projeto = QLabel(f"Projeto:\n{self.projeto.nome}")
            fonte = fonte_padrao(10)
            fonte.setBold(True)
            label_projeto.setFont(fonte)
            label_projeto.setWordWrap(True)
            label_projeto.setStyleSheet(f"color: {_cor_texto_id()} ;")
            coluna.addWidget(label_projeto)

        label_titulo = QLabel("Adicionar elemento")
        fonte_titulo = fonte_padrao(10)
        fonte_titulo.setBold(True)
        label_titulo.setFont(fonte_titulo)
        coluna.addWidget(label_titulo)

        coluna.addWidget(self._botao_painel("➕ Nova Barra", self._criar_barra))

        coluna.addWidget(self._label_secao("— Ramos (2 barras) —"))
        for texto, tipo in [("── Linha", "Line"), ("── Chave", "Switch"),
                            ("⧈ Transformador", "Transformer")]:
            coluna.addWidget(self._botao_painel(
                texto, lambda _checked=False, t=tipo: self._criar_ramo(t)))

        coluna.addWidget(self._label_secao("— Conectados (1 barra) —"))
        # NOTA: Storage não tem botão próprio — é criado pelo fluxo
        # "🔋 Sistema BESS" (que garante o InvControl associado).
        for texto, tipo in [("▣ Carga", "Load"), ("⚙ Gerador", "Generator"),
                            ("▭ Capacitor", "Capacitor"), ("☀ Fotovoltaico", "PVSystem"),
                            ("🌀 Reator", "Reactor"),
                            ("⚡ Fonte (Vsource)", "Vsource")]:
            coluna.addWidget(self._botao_painel(
                texto, lambda _checked=False, t=tipo: self._criar_derivacao(t)))

        coluna.addWidget(self._label_secao("— Sistemas compostos —"))
        coluna.addWidget(self._botao_painel(
            "🔋 Sistema BESS", self._criar_sistema_bess, fundo="#e0f2f1"))

        label_orientacao = QLabel("Orientação do layout")
        fonte_orientacao = fonte_padrao(10)
        fonte_orientacao.setBold(True)
        label_orientacao.setFont(fonte_orientacao)
        coluna.addWidget(label_orientacao)

        linha_orientacao = QHBoxLayout()
        linha_orientacao.setSpacing(4)
        self.radio_vertical = QRadioButton("Vertical")
        self.radio_horizontal = QRadioButton("Horizontal")
        self.radio_vertical.setChecked(self.orientacao == "vertical")
        grupo_orientacao = QButtonGroup(self)
        grupo_orientacao.addButton(self.radio_vertical)
        grupo_orientacao.addButton(self.radio_horizontal)
        self.grupo_orientacao = grupo_orientacao
        self.radio_vertical.toggled.connect(self._ao_mudar_orientacao)
        linha_orientacao.addWidget(self.radio_vertical)
        linha_orientacao.addWidget(self.radio_horizontal)
        coluna.addLayout(linha_orientacao)

        coluna.addWidget(self._botao_painel(
            "Simular no OpenDSS", self.simular, fundo="#c8e6c9"))

        coluna.addStretch(1)
        layout_principal.addWidget(painel_ferramentas)

        # ---------------- Cena / view (centro) ----------------
        self.cena = QGraphicsScene(self)
        self.cena.setBackgroundBrush(QBrush(_qcolor("white")))
        self.view = QGraphicsView(self.cena)
        self.view.setRenderHint(self.view.renderHints().SmoothPixmapTransform, True)
        self.view.setFrameShape(QFrame.Shape.StyledPanel)
        layout_principal.addWidget(self.view, 1)

        # ---------------- Lista de elementos (direita) ----------------
        painel_lista = QFrame()
        painel_lista.setFrameShape(QFrame.Shape.StyledPanel)
        painel_lista.setFixedWidth(260)
        self.painel_lista = painel_lista

        coluna_lista = QVBoxLayout(painel_lista)
        coluna_lista.setContentsMargins(6, 8, 6, 8)
        coluna_lista.setSpacing(4)

        label_lista = QLabel("Elementos da rede")
        fonte_lista = fonte_padrao(10)
        fonte_lista.setBold(True)
        label_lista.setFont(fonte_lista)
        coluna_lista.addWidget(label_lista)

        label_dica = QLabel("(duplo clique para editar,\ninclusive trocar o tipo)")
        fonte_dica = fonte_padrao(8)
        fonte_dica.setItalic(True)
        label_dica.setFont(fonte_dica)
        label_dica.setStyleSheet("color: gray;")
        coluna_lista.addWidget(label_dica)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Nome", "Tipo", "Detalhes"])
        self.tree.setColumnWidth(0, 100)
        self.tree.setColumnWidth(1, 70)
        self.tree.setColumnWidth(2, 90)
        self.tree.setRootIsDecorated(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.setFont(fonte_padrao(9))
        self.tree.itemDoubleClicked.connect(self._ao_dar_duplo_clique)
        coluna_lista.addWidget(self.tree, 1)

        coluna_lista.addWidget(self._botao_painel(
            "Excluir selecionado(s)", self._excluir_selecionado, fundo="#ffcdd2"))

        layout_principal.addWidget(painel_lista)

    # ------------------------------------------------------------------ #
    # Helpers de UI (estilo único, paleta institucional)
    # ------------------------------------------------------------------ #
    def _botao_painel(self, texto, callback, fundo: str = None) -> QPushButton:
        # TRANSPARÊNCIA TÉCNICA: nos botões com fundo pastel fixo, a cor do
        # texto é fixada explicitamente. Sem isso o texto herdava do
        # QPalette do sistema (tema escuro do Windows -> ButtonText branco)
        # e ficava ilegível sobre os fundos claros. O ramo sem fundo fica
        # intocado: ali o fundo nativo acompanha a paleta.
        botao = QPushButton(texto)
        botao.setFont(fonte_padrao(10))
        botao.setMinimumHeight(26)
        botao.setCursor(Qt.CursorShape.PointingHandCursor)
        if fundo:
            botao.setStyleSheet(
                f"QPushButton {{ background-color: {fundo}; color: #1B1B1B;"
                f" border: 1px solid {COR_ACCENT_MARCA}; border-radius: 4px;"
                f" padding: 3px 6px; }}"
                f"QPushButton:hover {{ background-color: {_escurecer(fundo, 0.92)}; }}")
        else:
            botao.setStyleSheet(
                f"QPushButton {{ border: 1px solid {COR_ACCENT_MARCA};"
                f" border-radius: 4px; padding: 3px 6px; }}"
                f"QPushButton:hover {{ background-color: #e8eef5; }}")
        botao.clicked.connect(lambda _checked=False: callback())
        return botao

    def _label_secao(self, texto: str) -> QLabel:
        label = QLabel(texto)
        fonte = fonte_padrao(8)
        fonte.setItalic(True)
        label.setFont(fonte)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #444444;")
        return label

    def _ao_mudar_orientacao(self, _marcado: bool = False):
        self.orientacao = "vertical" if self.radio_vertical.isChecked() else "horizontal"
        self.redesenhar()

    # ------------------------------------------------------------------ #
    # Curvas características (daily / duty / yearly) — botões 📈
    # ------------------------------------------------------------------ #
    def _abrir_editor_curva(self, parent_dialog, natureza, modo, valor_atual):
        if not self.projeto:
            QMessageBox.warning(
                parent_dialog, "Aviso",
                "Selecione/crie um projeto para poder salvar curvas características.")
            return None

        from .curva_editor_ui import abrir_editor_curva
        nome_inicial = None if valor_atual in (None, "", "Nenhuma") else valor_atual
        return abrir_editor_curva(parent_dialog, self.projeto.caminho_curvas,
                                  natureza, modo, nome_inicial)

    def _campos_tecnicos_ramo(self, tipo):
        return list(CAMPOS_RAMO_PARAMS[tipo])

    def _campos_tecnicos_derivacao(self, tipo):
        campos = list(CAMPOS_DERIVACAO_PARAMS[tipo])
        if tipo in TIPOS_COM_CURVA:
            natureza = TIPOS_COM_CURVA[tipo]
            for chave_prop, rotulo in PROPRIEDADES_CURVA:
                callback = (lambda parent, valor, nat=natureza, modo=chave_prop:
                            self._abrir_editor_curva(parent, nat, modo, valor))
                campos = campos + [(chave_prop, rotulo, "botao_grafico", callback)]
        return campos

    @staticmethod
    def _sanitizar_curva(parametros: dict) -> dict:
        for chave in ("daily", "duty", "yearly"):
            if parametros.get(chave) in (None, "", "Nenhuma"):
                parametros.pop(chave, None)
        return parametros

    # ------------------------------------------------------------------ #
    # Modelos dimensionados: usados na CRIAÇÃO de ramos/derivações
    # ------------------------------------------------------------------ #
    def _obter_parametros_tecnicos(self, tipo, campos_tecnicos):
        modelos = []
        if self.projeto and tipo in NOME_ARQUIVO_POR_TIPO:
            modelos = listar_modelos(self.projeto.caminho_dimensionamento, tipo)

        if modelos:
            opcoes = ["Manual (preencher campos)"] + [m["nome"] for m in modelos]
            campo_escolha = [("modelo", "Usar modelo dimensionado?", "combobox", opcoes)]

            escolha = pedir_valores(
                self, f"Parâmetros - {tipo}", campo_escolha,
                dica="Você pode usar um modelo previamente calculado no "
                     "Módulo de Dimensionamento, ou preencher manualmente.")
            if escolha is None:
                return None

            nome_escolhido = escolha.get("modelo")
            if nome_escolhido and nome_escolhido != "Manual (preencher campos)":
                modelo = next(m for m in modelos if m["nome"] == nome_escolhido)
                return dict(modelo["parametros"])

        valores = pedir_valores(self, f"Parâmetros técnicos - {tipo}", campos_tecnicos)
        if valores is None:
            return None
        return self._converter_numeros(valores)

    # ------------------------------------------------------------------ #
    # Criação de elementos
    # ------------------------------------------------------------------ #
    def _criar_barra(self):
        valores = pedir_valores(self, "Nova Barra", CAMPOS_BARRA)
        if valores is None:
            return

        nome_solicitado = valores.get("nome", "").strip()
        if not nome_solicitado:
            QMessageBox.critical(self, "Erro", "Informe um nome para a barra.")
            return

        try:
            kv_base = float(valores.get("kv_base", "13.8"))
        except ValueError:
            kv_base = 13.8

        nome_final = self.rede.adicionar_barra(nome_solicitado, kv_base)
        self._avisar_se_nome_ajustado(nome_solicitado, nome_final)
        self.redesenhar()

    def _criar_ramo(self, tipo):
        if len(self.rede.barras) < 2:
            QMessageBox.warning(
                self, "Aviso",
                "Crie ao menos duas barras antes de adicionar este elemento.")
            return

        opcoes_barras = sorted(self.rede.barras.keys())
        campos_conexao = [
            ("nome", "Nome do elemento", "texto", ""),
            ("bus1", "Barra de origem", "combobox", opcoes_barras),
            ("bus2", "Barra de destino", "combobox", opcoes_barras),
        ]

        valores_conexao = pedir_valores(self, f"Novo {tipo} - Conexão", campos_conexao)
        if valores_conexao is None:
            return

        nome_solicitado = valores_conexao.get("nome", "").strip()
        bus1 = valores_conexao.get("bus1", "")
        bus2 = valores_conexao.get("bus2", "")

        if not nome_solicitado or not bus1 or not bus2:
            QMessageBox.critical(
                self, "Erro", "Preencha nome, barra de origem e barra de destino.")
            return

        parametros = self._obter_parametros_tecnicos(tipo, self._campos_tecnicos_ramo(tipo))
        if parametros is None:
            return

        try:
            nome_final = self.rede.adicionar_ramo(tipo, nome_solicitado, bus1, bus2, parametros)
        except ValueError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return

        self._avisar_se_nome_ajustado(nome_solicitado, nome_final)
        self.redesenhar()

    def _criar_derivacao(self, tipo):
        if not self.rede.barras:
            QMessageBox.warning(
                self, "Aviso",
                "Crie ao menos uma barra antes de adicionar este elemento.")
            return

        if tipo == "Vsource" and not self._confirmar_substituir_fonte():
            return

        opcoes_barras = sorted(self.rede.barras.keys())
        campos_conexao = [
            ("nome", "Nome do elemento", "texto", ""),
            ("bus1", "Barra de conexão", "combobox", opcoes_barras),
        ]

        valores_conexao = pedir_valores(self, f"Novo {tipo} - Conexão", campos_conexao)
        if valores_conexao is None:
            return

        nome_solicitado = valores_conexao.get("nome", "").strip()
        bus1 = valores_conexao.get("bus1", "")

        if not nome_solicitado or not bus1:
            QMessageBox.critical(self, "Erro", "Preencha nome e barra de conexão.")
            return

        parametros = self._obter_parametros_tecnicos(tipo, self._campos_tecnicos_derivacao(tipo))
        if parametros is None:
            return
        parametros = self._sanitizar_curva(parametros)

        try:
            nome_final = self.rede.adicionar_derivacao(tipo, nome_solicitado, bus1, parametros)
        except ValueError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return

        self._avisar_se_nome_ajustado(nome_solicitado, nome_final)
        self.redesenhar()

    # ------------------------------------------------------------------ #
    # Sistema BESS composto (Storage + InvControl + Capacitor/Reactor)
    # ------------------------------------------------------------------ #
    def _caminho_master_atual_ou_none(self) -> Optional[str]:
        """Retorna o caminho do Master.dss já exportado do projeto atual,
        ou None se não houver projeto ativo ou o arquivo ainda não existir
        (ex.: rede ainda não foi exportada nenhuma vez)."""
        if not self.projeto:
            return None
        caminho = os.path.join(self.projeto.caminho_rede, "Master.dss")
        return caminho if os.path.exists(caminho) else None

    def _criar_sistema_bess(self):
        if not self.rede.barras:
            QMessageBox.warning(
                self, "Aviso",
                "Crie ao menos uma barra antes de adicionar este elemento.")
            return

        opcoes_barras = sorted(self.rede.barras.keys())
        campos_conexao = [
            ("bus1", "Barra de conexão", "combobox", opcoes_barras),
        ]

        valores_conexao = pedir_valores(self, "Sistema BESS - Conexão", campos_conexao)
        if valores_conexao is None:
            return

        bus1 = valores_conexao.get("bus1", "")
        if not bus1:
            QMessageBox.critical(self, "Erro", "Selecione a barra de conexão.")
            return

        caminho_master = self._caminho_master_atual_ou_none()
        nomes_existentes = set(self.rede.derivacoes.keys())

        resultado = abrir_formulario_sistema_bess(
            self, caminho_master, nomes_existentes, bus1)
        if resultado is None:
            return

        self._aplicar_resultado_sistema_bess(resultado)
        self.redesenhar()

    def _aplicar_resultado_sistema_bess(self, resultado: dict):
        """Recebe o dict retornado por sistema_bess.montar_elementos_sistema_bess()
        (ou abrir_formulario_sistema_bess()) e insere os elementos e curvas
        correspondentes na RedeEletrica atual."""
        grupo = resultado["grupo"]

        for info_curva in resultado.get("curvas_xy", []):
            self.rede.adicionar_curva_xy(
                info_curva["nome"], info_curva["xarray"], info_curva["yarray"])

        storage = resultado["storage"]
        self.rede.adicionar_derivacao(
            storage["tipo"], storage["nome"], storage["bus1"],
            storage["parametros"], grupo=storage.get("grupo"))

        invcontrol = resultado["invcontrol"]
        self.rede.adicionar_derivacao(
            invcontrol["tipo"], invcontrol["nome"], invcontrol.get("bus1"),
            invcontrol["parametros"], grupo=invcontrol.get("grupo"))

        resumo_extras = ""
        for chave, rotulo in (("capacitor", "Capacitor"), ("reactor", "Reator")):
            elemento = resultado.get(chave)
            if elemento:
                self.rede.adicionar_derivacao(
                    elemento["tipo"], elemento["nome"], elemento["bus1"],
                    elemento["parametros"], grupo=elemento.get("grupo"))
                resumo_extras += f"- {rotulo}: {elemento['nome']}\n"

        QMessageBox.information(
            self,
            "Sistema BESS criado",
            f"Sistema BESS '{grupo}' criado com sucesso, contendo:\n"
            f"- Armazenamento: {storage['nome']}\n"
            f"- Inversor (InvControl): {invcontrol['nome']}\n"
            f"{resumo_extras}"
        )

    def _editar_sistema_bess(self, nome_grupo):
        """Edita (recria) um Sistema BESS composto.

        IMPORTANTE (correção de segurança): o grupo antigo só é removido
        DEPOIS que o novo conjunto for confirmado com sucesso pelo
        usuário. Se o formulário for cancelado em qualquer etapa, NADA é
        alterado na rede — mantendo a mesma convenção usada em
        _editar_ramo/_editar_derivacao (cancelar nunca apaga dados).
        """
        elementos = self.rede.obter_grupo(nome_grupo)
        if not elementos:
            return

        storage = next((d for d in elementos.values() if d.tipo == "Storage"), None)
        invcontrol = next((d for d in elementos.values() if d.tipo == "InvControl"), None)

        if not storage:
            QMessageBox.critical(
                self, "Erro",
                "Este Sistema BESS não possui um elemento de Armazenamento "
                "(Storage) válido e não pode ser editado por este fluxo.")
            return

        if not confirmar_win11(
                "Editar Sistema BESS",
                f"Editar o Sistema BESS '{nome_grupo}' irá RECRIAR todos os "
                "seus elementos internos (Armazenamento, Inversor e, se "
                "houver, Capacitor/Reator) com os novos parâmetros "
                "informados.\n\nDeseja continuar?"):
            return

        bus1 = storage.bus1

        modo_atual = "VOLTVAR"
        if invcontrol:
            modo_atual = invcontrol.parametros.get(
                "CombiMode", invcontrol.parametros.get("Mode", "VOLTVAR"))

        modo_atual_texto = next(
            (m for m in MODOS_INVCONTROL if m.split(" ")[0] == modo_atual),
            MODOS_INVCONTROL[0])

        valores_iniciais = {
            "nome": nome_grupo,
            "kva_inversor": str(storage.parametros.get("kva", "")),
            "kwrated_bateria": str(storage.parametros.get("kwrated", "")),
            "kwhrated_bateria": str(storage.parametros.get("kwhrated", "")),
            "modo_invcontrol": modo_atual_texto,
        }

        # Calcula nomes_existentes EXCLUINDO os nomes dos elementos deste
        # próprio grupo (sem removê-los da rede ainda!). Isso permite que,
        # se o usuário mantiver o mesmo nome do Sistema BESS, os nomes
        # internos (ex.: "bess1_bat") sejam reaproveitados normalmente,
        # em vez de serem auto-renomeados para "bess1_bat1" à toa.
        nomes_do_grupo = set(elementos.keys())
        nomes_existentes = set(self.rede.derivacoes.keys()) - nomes_do_grupo

        caminho_master = self._caminho_master_atual_ou_none()

        resultado = abrir_formulario_sistema_bess(
            self, caminho_master, nomes_existentes, bus1,
            valores_iniciais=valores_iniciais)

        if resultado is None:
            # Cancelado: NADA foi alterado (o grupo antigo permanece intacto).
            return

        # Só agora, com o novo conjunto confirmado, o grupo antigo é removido.
        self.rede.remover_grupo(nome_grupo)
        self._aplicar_resultado_sistema_bess(resultado)
        self.redesenhar()

    def _editar_invcontrol(self, nome):
        """Editor dedicado e simplificado para o InvControl: como ele não
        possui barra própria, não usa o fluxo genérico _editar_derivacao
        (que sempre exige a escolha de uma barra)."""
        inv = self.rede.derivacoes.get(nome)
        if not inv:
            return

        modo_atual = inv.parametros.get(
            "CombiMode", inv.parametros.get("Mode", "VOLTVAR"))
        modo_atual_texto = next(
            (m for m in MODOS_INVCONTROL if m.split(" ")[0] == modo_atual),
            MODOS_INVCONTROL[0])

        campos = [("modo_invcontrol", "Modo do InvControl", "combobox", MODOS_INVCONTROL)]
        valores_iniciais = {"modo_invcontrol": modo_atual_texto}

        dica = ("Este elemento faz parte de um Sistema BESS composto. Para "
                "adicionar/remover Capacitor ou Reator, edite o conjunto "
                "completo (duplo clique no nó 'Sistema BESS' na árvore).")

        valores = pedir_valores(self, f"Editar Inversor (InvControl): {nome}",
                                campos, valores_iniciais, dica=dica)
        if valores is None:
            return

        modo = valores["modo_invcontrol"].split(" ")[0]
        der_list = inv.parametros.get("DERList", "")
        novos_parametros = {"DERList": der_list}

        if modo == "VOLTVAR":
            novos_parametros["Mode"] = "VOLTVAR"
            novos_parametros["vvc_curve1"] = self.rede.adicionar_curva_xy(
                CURVA_VOLTVAR_PADRAO_NOME,
                [p[0] for p in CURVA_VOLTVAR_PADRAO_PONTOS],
                [p[1] for p in CURVA_VOLTVAR_PADRAO_PONTOS])
        elif modo == "VOLTWATT":
            novos_parametros["Mode"] = "VOLTWATT"
            novos_parametros["voltwatt_curve"] = self.rede.adicionar_curva_xy(
                CURVA_VOLTWATT_PADRAO_NOME,
                [p[0] for p in CURVA_VOLTWATT_PADRAO_PONTOS],
                [p[1] for p in CURVA_VOLTWATT_PADRAO_PONTOS])
        elif modo == "VV_VW":
            novos_parametros["CombiMode"] = "VV_VW"
            novos_parametros["vvc_curve1"] = self.rede.adicionar_curva_xy(
                CURVA_VOLTVAR_PADRAO_NOME,
                [p[0] for p in CURVA_VOLTVAR_PADRAO_PONTOS],
                [p[1] for p in CURVA_VOLTVAR_PADRAO_PONTOS])
            novos_parametros["voltwatt_curve"] = self.rede.adicionar_curva_xy(
                CURVA_VOLTWATT_PADRAO_NOME,
                [p[0] for p in CURVA_VOLTWATT_PADRAO_PONTOS],
                [p[1] for p in CURVA_VOLTWATT_PADRAO_PONTOS])
        elif modo == "VV_DRC":
            novos_parametros["CombiMode"] = "VV_DRC"
            novos_parametros["vvc_curve1"] = self.rede.adicionar_curva_xy(
                CURVA_VOLTVAR_PADRAO_NOME,
                [p[0] for p in CURVA_VOLTVAR_PADRAO_PONTOS],
                [p[1] for p in CURVA_VOLTVAR_PADRAO_PONTOS])

        inv.parametros = novos_parametros
        self.redesenhar()

    def _confirmar_substituir_fonte(self, nome_a_ignorar: str = None) -> bool:
        fonte_existente = self.rede.obter_fonte()
        if not fonte_existente or fonte_existente.nome == nome_a_ignorar:
            return True

        if not confirmar_win11(
                "Fonte já existe",
                f"Já existe uma Fonte (Vsource) chamada '{fonte_existente.nome}'.\n"
                "Deseja substituí-la?"):
            return False

        self.rede.remover_derivacao(fonte_existente.nome)
        return True

    def _avisar_se_nome_ajustado(self, nome_solicitado, nome_final):
        if nome_solicitado != nome_final:
            QMessageBox.information(
                self, "Nome ajustado automaticamente",
                f"Já existia um elemento chamado '{nome_solicitado}'.\n"
                f"Este foi criado/renomeado como '{nome_final}'.")

    @staticmethod
    def _converter_numeros(valores: dict) -> dict:
        convertido = {}
        for k, v in valores.items():
            if k in ("daily", "duty", "yearly"):
                convertido[k] = v
                continue
            try:
                convertido[k] = float(v) if v.replace(".", "", 1).replace("-", "", 1).isdigit() else v
            except (ValueError, AttributeError):
                convertido[k] = v
        return convertido

    # ------------------------------------------------------------------ #
    # Campos dinâmicos (usados na edição)
    # ------------------------------------------------------------------ #
    def _campos_ramo_dinamico(self, tipo):
        opcoes_barras = sorted(self.rede.barras.keys())
        base = [
            ("nome", "Nome do elemento", "texto", ""),
            ("bus1", "Barra de origem", "combobox", opcoes_barras),
            ("bus2", "Barra de destino", "combobox", opcoes_barras),
        ]
        return base + self._campos_tecnicos_ramo(tipo)

    def _campos_derivacao_dinamico(self, tipo):
        opcoes_barras = sorted(self.rede.barras.keys())
        base = [
            ("nome", "Nome do elemento", "texto", ""),
            ("bus1", "Barra de conexão", "combobox", opcoes_barras),
        ]
        return base + self._campos_tecnicos_derivacao(tipo)

    # ------------------------------------------------------------------ #
    # Edição via duplo clique (inclui troca de TIPO)
    # ------------------------------------------------------------------ #
    def _ao_dar_duplo_clique(self, item, coluna=0):
        # No Tk a identidade vinha do iid "categoria::nome"; aqui vem dos
        # dados do item (Qt.UserRole), gravados em _atualizar_lista_elementos.
        if item is None:
            return
        referencias = item.data(0, Qt.ItemDataRole.UserRole)
        if not referencias:
            return

        categoria, nome = referencias

        if categoria == "barra":
            self._editar_barra(nome)
        elif categoria == "ramo":
            self._editar_ramo(nome)
        elif categoria == "grupobess":
            self._editar_sistema_bess(nome)
        elif categoria == "derivacao":
            der = self.rede.derivacoes.get(nome)
            if der and der.tipo == "InvControl":
                self._editar_invcontrol(nome)
            else:
                self._editar_derivacao(nome)

    def _editar_barra(self, nome_atual):
        barra = self.rede.barras.get(nome_atual)
        if not barra:
            return

        valores_iniciais = {"nome": barra.nome, "kv_base": barra.kv_base}
        valores = pedir_valores(self, f"Editar Barra: {nome_atual}",
                                CAMPOS_BARRA, valores_iniciais)
        if valores is None:
            return

        novo_nome = valores.get("nome", "").strip()
        if not novo_nome:
            QMessageBox.critical(self, "Erro", "Informe um nome para a barra.")
            return

        try:
            kv_base = float(valores.get("kv_base", barra.kv_base))
        except ValueError:
            kv_base = barra.kv_base

        nome_final = nome_atual
        if novo_nome != nome_atual:
            nome_final = self.rede.renomear_barra(nome_atual, novo_nome)
            self._avisar_se_nome_ajustado(novo_nome, nome_final)

        self.rede.barras[nome_final].kv_base = kv_base
        self.redesenhar()

    def _editar_ramo(self, nome):
        ramo = self.rede.ramos.get(nome)
        if not ramo:
            return

        campos = [("tipo", "Tipo de elemento", "combobox", TIPOS_RAMO)] + \
            self._campos_ramo_dinamico(ramo.tipo)

        valores_iniciais = {"tipo": ramo.tipo, "nome": ramo.nome,
                            "bus1": ramo.bus1, "bus2": ramo.bus2}
        valores_iniciais.update(ramo.parametros)

        dica = ("Para trocar o tipo do elemento (ex.: Linha -> Chave), selecione "
                "o novo tipo abaixo. Os parâmetros específicos serão pedidos "
                "em uma segunda tela.")

        valores = pedir_valores(self, f"Editar {ramo.tipo}: {nome}", campos,
                                valores_iniciais, dica=dica)
        if valores is None:
            return

        novo_tipo = valores.pop("tipo")
        novo_nome = valores.pop("nome", "").strip()
        novo_bus1 = valores.pop("bus1", "")
        novo_bus2 = valores.pop("bus2", "")

        if not novo_nome or not novo_bus1 or not novo_bus2:
            QMessageBox.critical(
                self, "Erro", "Preencha nome, barra de origem e barra de destino.")
            return

        if novo_tipo != ramo.tipo:
            campos_novo_tipo = self._campos_ramo_dinamico(novo_tipo)
            valores_iniciais_novo = {"nome": novo_nome, "bus1": novo_bus1, "bus2": novo_bus2}
            valores_iniciais_novo.update(valores)

            valores_novo = pedir_valores(
                self, f"Parâmetros do novo tipo: {novo_tipo}",
                campos_novo_tipo, valores_iniciais_novo)
            if valores_novo is None:
                return

            valores_novo.pop("nome", None)
            valores_novo.pop("bus1", None)
            valores_novo.pop("bus2", None)
            novos_parametros = self._converter_numeros(valores_novo)
        else:
            novos_parametros = self._converter_numeros(valores)

        try:
            self.rede.remover_ramo(nome)
            nome_final = self.rede.adicionar_ramo(
                novo_tipo, novo_nome, novo_bus1, novo_bus2, novos_parametros)
        except ValueError as e:
            self.rede.ramos[nome] = ramo
            QMessageBox.critical(self, "Erro", str(e))
            return

        self._avisar_se_nome_ajustado(novo_nome, nome_final)
        self.redesenhar()

    def _editar_derivacao(self, nome):
        der = self.rede.derivacoes.get(nome)
        if not der:
            return

        campos = [("tipo", "Tipo de elemento", "combobox", TIPOS_DERIVACAO)] + \
            self._campos_derivacao_dinamico(der.tipo)

        valores_iniciais = {"tipo": der.tipo, "nome": der.nome, "bus1": der.bus1}
        valores_iniciais.update(der.parametros)

        dica = ("Para trocar o tipo do elemento (ex.: Carga -> Gerador), selecione "
                "o novo tipo abaixo. Os parâmetros específicos serão pedidos "
                "em uma segunda tela.")

        valores = pedir_valores(self, f"Editar {der.tipo}: {nome}", campos,
                                valores_iniciais, dica=dica)
        if valores is None:
            return

        novo_tipo = valores.pop("tipo")
        novo_nome = valores.pop("nome", "").strip()
        novo_bus1 = valores.pop("bus1", "")

        if not novo_nome or not novo_bus1:
            QMessageBox.critical(self, "Erro", "Preencha nome e barra de conexão.")
            return

        if novo_tipo == "Vsource" and not self._confirmar_substituir_fonte(nome_a_ignorar=nome):
            return

        # Se este elemento pertence a um Sistema BESS composto, avisa que
        # trocar o tipo pode quebrar a referência interna do conjunto
        # (ex.: o InvControl deixa de encontrar o Storage pelo nome).
        if der.grupo and novo_tipo != der.tipo:
            if not confirmar_win11(
                    "Elemento pertence a um Sistema BESS",
                    f"Este elemento faz parte do Sistema BESS '{der.grupo}'. "
                    "Trocar seu tipo pode quebrar a referência interna do "
                    "conjunto (ex.: o Inversor deixa de encontrar o "
                    "Armazenamento associado).\n\nDeseja continuar mesmo assim?"):
                return

        if novo_tipo != der.tipo:
            campos_novo_tipo = self._campos_derivacao_dinamico(novo_tipo)
            valores_iniciais_novo = {"nome": novo_nome, "bus1": novo_bus1}
            valores_iniciais_novo.update(valores)

            valores_novo = pedir_valores(
                self, f"Parâmetros do novo tipo: {novo_tipo}",
                campos_novo_tipo, valores_iniciais_novo)
            if valores_novo is None:
                return

            valores_novo.pop("nome", None)
            valores_novo.pop("bus1", None)
            novos_parametros = self._converter_numeros(valores_novo)
        else:
            novos_parametros = self._converter_numeros(valores)

        novos_parametros = self._sanitizar_curva(novos_parametros)

        # IMPORTANTE: preserva o campo 'grupo' do elemento original, para
        # que editar um Storage/Capacitor/Reactor que faz parte de um
        # Sistema BESS não o "desvincule" silenciosamente do conjunto.
        grupo_atual = der.grupo

        try:
            self.rede.remover_derivacao(nome)
            nome_final = self.rede.adicionar_derivacao(
                novo_tipo, novo_nome, novo_bus1, novos_parametros, grupo=grupo_atual)
        except ValueError as e:
            self.rede.derivacoes[nome] = der
            QMessageBox.critical(self, "Erro", str(e))
            return

        self._avisar_se_nome_ajustado(novo_nome, nome_final)
        self.redesenhar()

    # ------------------------------------------------------------------ #
    # Exclusão
    # ------------------------------------------------------------------ #
    def _excluir_selecionado(self):
        selecionados = self.tree.selectedItems()
        if not selecionados:
            return

        for item in selecionados:
            referencias = item.data(0, Qt.ItemDataRole.UserRole)
            if not referencias:
                continue
            categoria, nome = referencias

            if categoria == "barra":
                if confirmar_win11(
                        "Confirmar exclusão",
                        f"Excluir a barra '{nome}' e todos os elementos ligados a ela?"):
                    self.rede.remover_barra(nome)
            elif categoria == "ramo":
                self.rede.remover_ramo(nome)
            elif categoria == "grupobess":
                if confirmar_win11(
                        "Confirmar exclusão",
                        f"Excluir o Sistema BESS '{nome}' e TODOS os seus "
                        "elementos internos (Armazenamento, Inversor e, se "
                        "houver, Capacitor/Reator)?"):
                    self.rede.remover_grupo(nome)
            elif categoria == "derivacao":
                der = self.rede.derivacoes.get(nome)
                if der and der.grupo:
                    if not confirmar_win11(
                            "Elemento pertence a um Sistema BESS",
                            f"O elemento '{nome}' faz parte do Sistema BESS "
                            f"'{der.grupo}'. Excluir apenas este elemento "
                            "pode deixar o restante do sistema inconsistente "
                            "(ex.: um Inversor sem Armazenamento associado)."
                            "\n\nDeseja excluir MESMO ASSIM apenas este "
                            "elemento?\n(Para excluir o conjunto inteiro, "
                            "selecione o nó 'Sistema BESS' na árvore.)"):
                        continue
                self.rede.remover_derivacao(nome)

        self.redesenhar()

    def _atualizar_lista_elementos(self):
        # Preserva a seleção atual (por categoria::nome) para não perdê-la
        # a cada redesenhar() — no Tk isso era irrelevante porque redesenhar
        # só reconstruía o canvas, não a Treeview.
        selecao_anterior = set()
        for item in self.tree.selectedItems():
            ref = item.data(0, Qt.ItemDataRole.UserRole)
            if ref:
                selecao_anterior.add(ref)

        self.tree.clear()

        def _novo_item(pai, texto, valores, referencia=None, aberto=False):
            item = QTreeWidgetItem(pai, [texto] + list(valores))
            if referencia is not None:
                item.setData(0, Qt.ItemDataRole.UserRole, referencia)
            item.setExpanded(aberto)
            return item

        grupo_barras = _novo_item(self.tree, "Barras", ("", ""), aberto=True)
        for nome, b in sorted(self.rede.barras.items()):
            _novo_item(grupo_barras, nome, ("Barra", f"{b.kv_base} kV"),
                       referencia=("barra", nome))

        grupo_ramos = _novo_item(self.tree, "Ramos", ("", ""), aberto=True)
        for nome, r in sorted(self.rede.ramos.items()):
            _novo_item(grupo_ramos, nome, (r.tipo, f"{r.bus1} → {r.bus2}"),
                       referencia=("ramo", nome))

        grupo_ders = _novo_item(self.tree, "Conectados", ("", ""), aberto=True)

        # Separa elementos que pertencem a um Sistema BESS composto
        # (campo 'grupo' preenchido) dos elementos avulsos.
        grupos_bess: Dict[str, List] = {}
        ders_avulsas = []
        for nome, d in self.rede.derivacoes.items():
            if d.grupo:
                grupos_bess.setdefault(d.grupo, []).append((nome, d))
            else:
                ders_avulsas.append((nome, d))

        for nome_grupo, itens in sorted(grupos_bess.items()):
            no_grupo = _novo_item(
                grupo_ders, f"🔋 Sistema BESS: {nome_grupo}",
                ("SistemaBESS", f"{len(itens)} elemento(s)"),
                referencia=("grupobess", nome_grupo), aberto=True)

            for nome, d in sorted(itens, key=lambda t: t[0]):
                tem_curva = any(d.parametros.get(c) not in (None, "", "Nenhuma")
                                for c in ("daily", "duty", "yearly"))
                sufixo_curva = " 📈" if tem_curva else ""
                local = f"bus: {d.bus1}" if d.bus1 else "(sem barra própria)"
                _novo_item(no_grupo, nome + sufixo_curva, (d.tipo, local),
                           referencia=("derivacao", nome))

        for nome, d in sorted(ders_avulsas, key=lambda t: t[0]):
            tem_curva = any(d.parametros.get(c) not in (None, "", "Nenhuma")
                            for c in ("daily", "duty", "yearly"))
            sufixo_curva = " 📈" if tem_curva else ""
            _novo_item(grupo_ders, nome + sufixo_curva, (d.tipo, f"bus: {d.bus1}"),
                       referencia=("derivacao", nome))

        # Reaplica a seleção anterior (se os elementos ainda existirem).
        if selecao_anterior:
            pilha = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
            while pilha:
                item_atual = pilha.pop()
                if item_atual is None:
                    continue
                ref = item_atual.data(0, Qt.ItemDataRole.UserRole)
                if ref in selecao_anterior:
                    item_atual.setSelected(True)
                pilha.extend(item_atual.child(i) for i in range(item_atual.childCount()))

    # ------------------------------------------------------------------ #
    # Auto-encaixe (fit-to-view): calcula escala + centralização usando
    # uma margem fixa suficiente para acomodar os ícones do "leque"
    # (que têm tamanho fixo em pixels, não escalado), evitando cortes.
    # ------------------------------------------------------------------ #
    def _transformar_posicoes(self, posicoes_cruas):
        if not posicoes_cruas:
            return {}, 1.0

        xs = [p[0] for p in posicoes_cruas.values()]
        ys = [p[1] for p in posicoes_cruas.values()]

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        margem = MARGEM_FIT

        largura_conteudo = max(max_x - min_x, 1)
        altura_conteudo = max(max_y - min_y, 1)

        largura_canvas = max(self.view.viewport().width(), 300)
        altura_canvas = max(self.view.viewport().height(), 300)

        escala_x = (largura_canvas - 2 * margem) / largura_conteudo
        escala_y = (altura_canvas - 2 * margem) / altura_conteudo
        escala = min(escala_x, escala_y)
        escala = max(0.15, min(escala, 2.5))

        largura_final = largura_conteudo * escala
        altura_final = altura_conteudo * escala

        offset_x = (largura_canvas - largura_final) / 2 - min_x * escala
        offset_y = (altura_canvas - altura_final) / 2 - min_y * escala

        posicoes_transformadas = {
            nome: (x * escala + offset_x, y * escala + offset_y)
            for nome, (x, y) in posicoes_cruas.items()
        }

        return posicoes_transformadas, escala

    # ------------------------------------------------------------------ #
    # Calcula, para uma barra, o maior intervalo angular LIVRE em relação
    # às linhas/ramos já conectados a ela, evitando que o leque de
    # elementos (Carga, Gerador, PV, Fonte, etc.) seja desenhado por
    # cima de uma linha existente.
    #
    # Convenção de ângulo: 0°=direita, 90°=baixo, 180°=esquerda,
    # 270°=cima (sistema de tela, com Y crescendo para baixo).
    # ------------------------------------------------------------------ #
    def _calcular_intervalo_derivacoes(self, bus, posicoes, angulo_padrao):
        pos_bus = posicoes.get(bus)
        if not pos_bus:
            return angulo_padrao - 70, angulo_padrao + 70

        angulos_ocupados = []
        for ramo in self.rede.ramos.values():
            outro = None
            if ramo.bus1 == bus:
                outro = ramo.bus2
            elif ramo.bus2 == bus:
                outro = ramo.bus1
            if outro is None:
                continue

            pos_outro = posicoes.get(outro)
            if not pos_outro:
                continue

            dx = pos_outro[0] - pos_bus[0]
            dy = pos_outro[1] - pos_bus[1]
            if dx == 0 and dy == 0:
                continue

            angulo = math.degrees(math.atan2(dy, dx)) % 360
            angulos_ocupados.append(angulo)

        if not angulos_ocupados:
            spread_padrao = 150
            return angulo_padrao - spread_padrao / 2, angulo_padrao + spread_padrao / 2

        angulos_ordenados = sorted(set(round(a, 3) for a in angulos_ocupados))
        n = len(angulos_ordenados)

        maior_gap = -1
        inicio_maior_gap = 0
        for i in range(n):
            atual = angulos_ordenados[i]
            proximo = angulos_ordenados[(i + 1) % n]
            gap = (proximo - atual) % 360
            if gap == 0:
                gap = 360
            if gap > maior_gap:
                maior_gap = gap
                inicio_maior_gap = atual

        centro = (inicio_maior_gap + maior_gap / 2) % 360
        margem_seguranca = 15  # graus de folga em relação às linhas existentes
        spread = max(30, min(maior_gap - 2 * margem_seguranca, 150))

        return centro - spread / 2, centro + spread / 2

    # ------------------------------------------------------------------ #
    def _desenhar_rotulo(self, x, y, texto, cor, tamanho_fonte=8,
                         fundo: str = "white"):
        rotulo = _RotuloItem(texto, cor, tamanho_fonte, fundo)
        # O create_text do Tk recebia (x, y) como CENTRO do texto e usava
        # justify="center"; QGraphicsTextItem posiciona pelo canto
        # superior-esquerdo, daí o deslocamento de meia largura/altura.
        rect = rotulo.boundingRect()
        rotulo.setPos(x - rect.width() / 2, y - rect.height() / 2)
        rotulo.setZValue(3.0)
        self.cena.addItem(rotulo)
        return rotulo

    def _ao_mover_barra(self, nome, ponto):
        """Sincroniza a posição arrastada com o dicionário de posições de
        tela (ver _BarraItem.itemChange). NÃO persiste no modelo — a Barra
        não possui campo de posição e o layout é sempre automático."""
        if self._redesenhando:
            return
        if nome in self._posicoes:
            self._posicoes[nome] = (ponto.x(), ponto.y())

    # ------------------------------------------------------------------ #
    def redesenhar(self):
        if self._redesenhando:
            return
        self._redesenhando = True
        try:
            self.cena.clear()
            orientacao = self.orientacao

            posicoes_cruas = calcular_posicoes(self.rede, orientacao=orientacao)
            posicoes, escala = self._transformar_posicoes(posicoes_cruas)
            self._posicoes = dict(posicoes)
            self._escala = escala

            raio_barra = max(4, RAIO_BARRA_BASE * escala)
            espessura_linha = max(1, round(3 * escala))

            # ---- Ramos (linhas entre barras) ---- #
            for ramo in self.rede.ramos.values():
                p1 = posicoes.get(ramo.bus1)
                p2 = posicoes.get(ramo.bus2)
                if not p1 or not p2:
                    continue

                cor = CORES.get(ramo.tipo, "black")
                linha = QGraphicsLineItem(p1[0], p1[1], p2[0], p2[1])
                caneta = QPen(_qcolor(cor), espessura_linha)
                # Switch = chave: traço tracejado para distinguir da Line.
                if ramo.tipo == "Switch":
                    caneta.setStyle(Qt.PenStyle.DashLine)
                linha.setPen(caneta)
                linha.setZValue(0.0)
                self.cena.addItem(linha)

                dx, dy = p2[0] - p1[0], p2[1] - p1[1]
                comprimento = math.hypot(dx, dy) or 1
                perp_x, perp_y = -dy / comprimento, dx / comprimento
                deslocamento = 16

                mx = (p1[0] + p2[0]) / 2 + perp_x * deslocamento
                my = (p1[1] + p2[1]) / 2 + perp_y * deslocamento

                self._desenhar_rotulo(mx, my, f"{ramo.tipo}\n{ramo.nome}", cor)

            # ---- Derivações, em leque ao redor da barra (tamanho FIXO) ---- #
            # NOTA: elementos com bus1=None (ex.: InvControl) são agrupados sob
            # a chave None; como "posicoes" nunca contém a chave None (só
            # contém nomes de barras reais), pos_bus resulta em None e o laço
            # abaixo pula automaticamente esses elementos (não são desenhados
            # no canvas, apenas aparecem na árvore de elementos à direita).
            agrupado_por_bus = {}
            for der in self.rede.derivacoes.values():
                agrupado_por_bus.setdefault(der.bus1, []).append(der)

            angulo_padrao = 90 if orientacao == "vertical" else 0

            for bus, lista in agrupado_por_bus.items():
                pos_bus = posicoes.get(bus)
                if not pos_bus:
                    continue

                angulo_ini, angulo_fim = self._calcular_intervalo_derivacoes(
                    bus, posicoes, angulo_padrao)

                lista_ordenada = sorted(lista, key=lambda d: d.nome)
                n = len(lista_ordenada)
                angulos = [(angulo_ini + angulo_fim) / 2] if n == 1 else [
                    angulo_ini + i * (angulo_fim - angulo_ini) / (n - 1) for i in range(n)
                ]

                for der, ang in zip(lista_ordenada, angulos):
                    rad = math.radians(ang)
                    ex = pos_bus[0] + RAIO_LEQUE * math.cos(rad)
                    ey = pos_bus[1] + RAIO_LEQUE * math.sin(rad)

                    cor = CORES.get(der.tipo, "gray")

                    ligacao = QGraphicsLineItem(pos_bus[0], pos_bus[1], ex, ey)
                    caneta = QPen(_qcolor(cor), max(1, espessura_linha - 2))
                    caneta.setStyle(Qt.PenStyle.DotLine)
                    ligacao.setPen(caneta)
                    ligacao.setZValue(0.0)
                    self.cena.addItem(ligacao)

                    caixa = QGraphicsRectItem(
                        ex - MEIA_LARGURA_CAIXA, ey - MEIA_ALTURA_CAIXA,
                        2 * MEIA_LARGURA_CAIXA, 2 * MEIA_ALTURA_CAIXA)
                    caixa.setBrush(QBrush(_qcolor(cor)))
                    caixa.setPen(QPen(_qcolor("black"), 1))
                    caixa.setZValue(1.0)
                    self.cena.addItem(caixa)

                    tem_curva = any(der.parametros.get(c) not in (None, "", "Nenhuma")
                                    for c in ("daily", "duty", "yearly"))
                    texto_der = f"{der.tipo}\n{der.nome}" + (" 📈" if tem_curva else "")
                    # Cor do texto calculada por contraste com o preenchimento
                    # da caixa e sem retângulo de fundo (fundo=None): antes era
                    # branco fixo sobre fundo claro (ilegível).
                    self._desenhar_rotulo(ex, ey, texto_der,
                                          _cor_texto_sobre(cor),
                                          tamanho_fonte=7, fundo=None)

            # ---- Barras ---- #
            for nome, barra in self.rede.barras.items():
                pos = posicoes.get(nome)
                if not pos:
                    continue
                x, y = pos
                item_barra = _BarraItem(nome, raio_barra, self)
                item_barra.setPos(x, y)
                self.cena.addItem(item_barra)
                self._desenhar_rotulo(x, y - 18, f"{nome}\n{barra.kv_base} kV", "black")

            largura_canvas = max(self.view.viewport().width(), 300)
            altura_canvas = max(self.view.viewport().height(), 300)
            self.cena.setSceneRect(0, 0, largura_canvas, altura_canvas)

            self._atualizar_lista_elementos()
        finally:
            self._redesenhando = False

    # ------------------------------------------------------------------ #
    # Persistência / exportação (projeto-aware)
    # ------------------------------------------------------------------ #
    def novo_projeto(self):
        if confirmar_win11("Novo projeto", "Descartar a rede atual?"):
            self.rede = RedeEletrica()
            self.redesenhar()

    def salvar_projeto(self):
        if self.projeto:
            caminho = os.path.join(self.projeto.caminho_rede, "rede.json")
        else:
            caminho, _filtro = QFileDialog.getSaveFileName(
                self, "Salvar rede", "", "Projeto JSON (*.json)")
            if not caminho:
                return
            if not caminho.lower().endswith(".json"):
                caminho += ".json"

        self.rede.salvar_json(caminho)
        QMessageBox.information(self, "Sucesso", f"Rede salva em:\n{caminho}")

    def abrir_projeto(self):
        pasta_inicial = self.projeto.caminho_rede if self.projeto else ""
        caminho, _filtro = QFileDialog.getOpenFileName(
            self, "Abrir rede", pasta_inicial, "Projeto JSON (*.json)")
        if caminho:
            self.rede = RedeEletrica.carregar_json(caminho)
            self.redesenhar()

    def _pasta_curvas_atual(self):
        return self.projeto.caminho_curvas if self.projeto else None

    def exportar_dss(self):
        if self.projeto:
            pasta = self.projeto.caminho_rede
        else:
            pasta = QFileDialog.getExistingDirectory(
                self, "Escolha a pasta de destino dos arquivos .dss")
            if not pasta:
                return

        try:
            caminho_master = gerar_arquivos_dss(
                self.rede, pasta, pasta_curvas=self._pasta_curvas_atual())
        except ValueError as e:
            QMessageBox.critical(self, "Erro ao exportar", str(e))
            return

        QMessageBox.information(self, "Exportado com sucesso",
                                f"Master.dss gerado em:\n{caminho_master}")

    def exportar_parametrizacao_arduino(self):
        """Gera `param_microrrede.h` para o Arduino Mega a partir da rede.

        O sketch embarcado é pré-pronto; o que é gerado aqui são apenas os
        dados do projeto (topologia, cargas, curvas, geração) para a placa
        representar esta microrrede no ensaio de bancada.
        """
        if not self.projeto:
            QMessageBox.critical(
                self, "Erro ao exportar",
                "Abra um projeto antes de exportar a parametrização do "
                "Arduino. A parametrização é gerada a partir da rede salva "
                "no projeto.")
            return

        pasta_hardware = os.path.join(self.projeto.caminho_raiz, "hardware")
        caminho_saida = os.path.join(pasta_hardware, NOME_ARQUIVO_PARAM_ARDUINO)

        try:
            relatorio = gerar_parametrizacao_arduino(self.projeto, caminho_saida)
        except ValueError as e:
            QMessageBox.critical(self, "Erro ao exportar parametrização", str(e))
            return
        except OSError as e:
            QMessageBox.critical(
                self, "Erro ao exportar parametrização",
                f"Não foi possível escrever '{caminho_saida}':\n{e}")
            return

        avisos = relatorio.get("avisos", [])
        texto = (
            f"Cabeçalho gerado em:\n{relatorio['caminho']}\n\n"
            f"Barras: {relatorio['n_barras']} | "
            f"Ramos: {relatorio['n_ramos']} | "
            f"BESS_BUS: {relatorio['bess_bus']}"
        )
        if avisos:
            texto += ("\n\nAVISOS (aproximações e omissões):\n- "
                      + "\n- ".join(avisos))
            QMessageBox.warning(self, "Parametrização gerada com avisos", texto)
        else:
            QMessageBox.information(self, "Parametrização gerada", texto)

    def simular(self):
        if self.projeto:
            pasta = self.projeto.caminho_rede
        else:
            pasta = tempfile.mkdtemp(prefix="opendss_editor_")

        try:
            caminho_master = gerar_arquivos_dss(
                self.rede, pasta, pasta_curvas=self._pasta_curvas_atual())
        except ValueError as e:
            QMessageBox.critical(self, "Erro ao gerar .dss", str(e))
            return

        try:
            from .dss_engine import DSS
            objeto_dss = DSS(caminho_master)
            versao = objeto_dss.versionDSS()
            vmin = objeto_dss.find_Vmin()
            QMessageBox.information(
                self,
                "Simulação concluída",
                f"Versão do OpenDSS: {versao}\nVmin encontrada: {vmin:.4f} pu\n\n"
                f"Arquivos gerados em:\n{pasta}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Erro ao simular", str(e))
