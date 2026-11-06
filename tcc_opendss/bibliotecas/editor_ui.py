__author__ = 'Pedro Henrique Sousa Pinheiro'
"""View: editor da rede elétrica.

Este módulo desenha e edita o circuito. Criação e edição passam por
formulários com listas suspensas — nada de digitar comando .dss à mão.
Duplo clique na lista de elementos abre o formulário já preenchido, e
por ali também se troca o TIPO do elemento (Linha vira Chave, Carga
vira Gerador). Carga, Gerador, PVSystem e Storage têm três botões 📈
para apontar as curvas 'daily', 'duty' e 'yearly'.

Vocabulário do desenho, que aparece em todo o resto do arquivo:

- barra é o nó elétrico (o "ponto" onde os condutores se encontram);
- ramo é o trecho que LIGA duas barras — linha, chave ou transformador;
- derivação é o elemento pendurado em UMA barra só: carga, gerador,
  fonte, capacitor, medidor. Como ela não liga nada a nada, no desenho
  ela sai em leque ao redor da barra, e o leque procura o maior vão
  angular livre entre os ramos já conectados para não cruzar com eles.

O enquadramento é automático. A cada redesenho, escala e centralização
são recalculadas (fit-to-view) para o circuito inteiro caber na área
visível, com margem suficiente para os ícones do leque, que têm tamanho
fixo em pixels e não encolhem junto. Em cima desse arranjo o usuário
pode dar zoom e arrastar a vista (ver _CanvasRede), e arrastar barras e
caixas para desamontoar o diagrama — ajuste de visualização, não dado
de projeto.

Sistema BESS composto: o botão "🔋 Sistema BESS" cria num fluxo único
até quatro elementos DSS internos (Storage + InvControl + Capacitor e
Reactor opcionais), amarrados pelo campo 'grupo'. Na árvore eles
aparecem juntos sob o nó "🔋 Sistema BESS: <nome>". O InvControl não tem
barra própria (bus1=None) e por isso não é desenhado no canvas: existe
só na árvore e no .dss. A regra geral que esse caso exemplifica — quem
não se ancora numa barra não tem onde ser desenhado.

Medidor de energia: o botão "⏱ Medidor de energia" cria um EnergyMeter
na entrada principal da rede. O padrão é o primeiro ramo ligado à barra
da fonte, na ordem de criação; o formulário deixa trocar elemento e
terminal, porque nem todo mundo quer medir exatamente ali. Duas
restrições vêm do motor OpenDSS, não do editor. A primeira: só elemento
de entrega de potência serve de alvo, e medir a própria fonte é
recusado. A segunda: o EnergyMeter não aponta para barra, e sim para um
elemento — a âncora do desenho é derivada do terminal monitorado.

TRANSPARÊNCIA TÉCNICA (migração Tkinter → PySide6 — último módulo da
migração):

TRANSPARÊNCIA TÉCNICA (migração Tkinter → PySide6 — último módulo da
migração):

O editor nasceu em Tkinter e foi reescrito em Qt (a biblioteca gráfica
do PySide6). Em Qt, um widget é a caixa retangular na tela; a "cena"
(QGraphicsScene) é o plano onde os desenhos vivem, em coordenadas
próprias; a "vista" (QGraphicsView) é a janela que olha para a cena e
decide qual pedaço dela aparece. Ou seja: cena guarda, vista exibe. Essa
dissociação não existia no Tk, onde o Canvas era as duas coisas ao mesmo
tempo — e é a raiz de quase todas as divergências listadas abaixo.

- `tk.Frame` → `QWidget`. `EditorRede` é hoje um `QWidget`, embutido
  como widget central pelo lançador `bibliotecas/editor_rede.py`. Daí a
  mudança de assinatura: `EditorRede(master, rede=None, projeto=None)`
  virou `EditorRede(rede=None, projeto=None)`. O `master` do Tk, que era
  a janela-mãe e por isso sabia título e tamanho, não tem equivalente
  aqui; quem cria a janela agora é o lançador. Os demais métodos
  públicos conservam nome e efeito (`novo_projeto`, `salvar_projeto`,
  `abrir_projeto`, `exportar_dss`, `simular`, `redesenhar`).
  `configurar_menu(qmainwindow)` é o novo ponto de injeção do menu
  "Arquivo" na barra de menus, no lugar do `master.config(menu=...)`.

- `tk.Canvas` → `QGraphicsScene`/`QGraphicsView`. Cada elemento do
  desenho é um item de cena: `QGraphicsEllipseItem` para a barra,
  `QGraphicsLineItem` para ramo e ligação, `QGraphicsRectItem` para a
  caixa do leque, `QGraphicsTextItem` para o rótulo. O auto-encaixe,
  porém, NÃO usa o sistema de transformação da vista. A matemática de
  escala e centralização de `_transformar_posicoes` foi portada
  VERBATIM e aplicada às coordenadas dos itens — o mesmo que o Tk fazia
  calcular à mão antes de `create_oval`/`create_line`. O motivo de
  manter assim: o enquadramento e as constantes fixas em pixels do
  leque (RAIO_LEQUE, MEIA_LARGURA_CAIXA...) já estavam calibrados, e
  jogar a escala para a matriz da vista mudaria o resultado visual em
  toda rede pequena. O zoom do usuário entra depois, como transformação
  adicional.

- `messagebox`/`filedialog`/`simpledialog` → `QMessageBox` (ou
  `mostrar_aviso_win11`/`confirmar_win11`, de `ui_win11`) e
  `QFileDialog`. Títulos, frases e avisos foram preservados VERBATIM:
  nenhum texto mudou de sentido na migração.

- `ttk.Treeview` → `QTreeWidget`. A identidade de uma linha deixou de
  ser o `iid` "categoria::nome" e passou a ser o par (categoria, nome),
  guardado em `Qt.UserRole`, um espaço que o Qt reserva no item para
  dado próprio (o fork do Tk não tinha isso, daí o iid). O conteúdo
  visível é o mesmo de antes: grupos "Barras", "Ramos" e "Conectados",
  nós "🔋 Sistema BESS: <nome>", sufixo " 📈" de curva e resumo de
  parâmetros.

- `tk.Button`/`tk.Label`/`tk.Radiobutton`/`tk.Menu` → `QPushButton`/
  `QLabel`/`QRadioButton`/`QMenu` + `QAction`, com `fonte_padrao` e a
  paleta de `ui_win11`.

- DIVERGÊNCIA DELIBERADA (seleção visual no canvas): no Tk, o `Canvas`
  não tinha seleção de item nem arraste — o grafo era reconstruído
  inteiro a cada `redesenhar()`, e não havia o que arrastar. Aqui as
  barras são itens móveis e selecionáveis (`ItemIsMovable |
  ItemIsSelectable`) e, ao serem soltas, atualizam `self._posicoes`
  (já em coordenada de tela, pós-encaixe). O layout continua automático:
  qualquer `redesenhar()` recalcula tudo, então arrastar é ajuste
  transitório de visualização, não atributo do modelo — `Barra` não tem
  campo de posição e nada disso vai para `rede.json`.

- DIVERGÊNCIA DELIBERADA (organização interna): o original guardava a
  árvore em `self.tree` (Treeview) e o canvas em `self.canvas`.
  `self.tree` sobreviveu como nome do `QTreeWidget`, cujos métodos
  `_atualizar_lista_elementos`, `_excluir_selecionado` e o duplo clique
  fazem o mesmo de antes. `self.canvas` não: o que era um objeto virou
  dois, `self.view` e `self.cena`. Também `self.orientacao_var`
  (StringVar, um invólucro de string do Tk) virou `self.orientacao`,
  uma string comum.

- `after(50, self.redesenhar)` do Tk virou
  `QTimer.singleShot(0, self.redesenhar)`. O motivo de existir é o
  mesmo nos dois casos: antes do primeiro ciclo de eventos o widget
  ainda não sabe seu tamanho, e o enquadramento sairia calculado sobre
  uma área de zero pixel.
"""

import os

# MPLBACKEND deve ser definido ANTES de qualquer import de terceiros
# (matplotlib é importado indiretamente pelo editor de curvas).
os.environ.setdefault("MPLBACKEND", "QtAgg")

import math
import tempfile
from typing import Dict, List, Optional

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
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

# A lista abaixo alimenta o combo "Tipo de elemento" do formulário de
# edição — ou seja, define em quais tipos um elemento já existente pode
# ser convertido. Três tipos ficaram de fora de propósito.
#
# InvControl: não tem barra própria (bus1=None) e só faz sentido dentro
# de um Sistema BESS, onde referencia um Storage por DERList. Como a
# conversão genérica pede uma barra, incluí-lo produziria um inversor
# solto no ar. Ele é criado pelo fluxo "🔋 Sistema BESS" e editado em
# _editar_invcontrol, que só mexe no modo de controle.
#
# EnergyMeter: mesmo princípio. O medidor não escolhe barra tampouco —
# sua âncora visual é derivada do ELEMENTO que ele monitora —, e deixar
# a conversão genérica alcançá-lo permitiria um medidor sem alvo. Tem
# criação em _criar_medidor e edição em _editar_medidor.
#
# Storage: este continua na lista mesmo com o botão de criação avulsa já
# removido, porque retirá-lo quebraria a edição de Storages existentes,
# incluindo os que pertencem a um Sistema BESS (abertos por duplo
# clique na árvore). O efeito colateral aceito: um elemento avulso
# qualquer ainda pode ser convertido à mão para Storage, e um Storage
# que nasce por esse caminho fica SEM InvControl associado. Caso de
# borda tolerado; se preferir bloquear também, o ponto de bloqueio é
# aqui.
TIPOS_DERIVACAO = ["Load", "Generator", "Capacitor", "PVSystem", "Storage", "Reactor", "Vsource"]

# Elementos que aceitam curva característica. O valor ("carga"/"geracao")
# não muda cálculo nenhum: serve para o eixo % do editor gráfico dizer
# se aquela curva representa consumo ou injeção.
TIPOS_COM_CURVA = {
    "Load": "carga",
    "Generator": "geracao",
    "PVSystem": "geracao",
    "Storage": "carga",
}

# Propriedades de curva suportadas: chave gravada em `parametros` e
# rótulo mostrado no formulário. A chave é também o 'modo' entregue ao
# editor gráfico, porque coincide com o nome da propriedade no OpenDSS.
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
# Campo em branco significa "não declare nada no .dss", e aí quem decide
# é o motor (dss-python 0.15.7): ele aplica defaults NÃO-nulos a
# parâmetros que o usuário não escreveu. Medido no motor real nesta
# revisão:
#   * Transformer de 2 enrolamentos sem %loadloss: R série efetiva ≈ 0,4043 %
#     (o motor soma dois %r default de 0,2 %, um por enrolamento);
#   * Line sem c1/c0: C1 = 3,4 nF/km e C0 = 1,6 nF/km.
# Nada disso foi digitado por ninguém: é default fantasma entrando no
# cálculo do usuário. Preencher com dado REAL de placa, ensaio ou
# catálogo é o que o remove. O software não estima por conta própria —
# campo em branco nunca é "completado" aqui, justamente para não
# maquiar esse fantasma com uma estimativa de origem desconhecida.
# Hierarquia medida: %r explícito, inclusive 0, ANULA %loadloss. O
# editor não expõe %r em trafo, então essa armadilha específica não é
# alcançável por esta via.
#
# ARMADILHA MEDIDA (motor real, nesta revisão): %noloadloss SOZINHO não
# corrige perdas — desloca o ponto de operação. Trafo 100 kVA 13,8/0,4 kV
# xhl=5 %: só %noloadloss=0,25 -> série salta de 454,7 W para 1.387,5 W
# (a perda a vazio virou parcela em série). Com %loadloss=1,2 declarado:
# série 1.393,6 W + núcleo 235,7 W, coerente com os 1,2 % + 0,25 % de placa.
# Daí a regra: os dois campos andam como um PAR. É assim que eles vêm
# do ensaio de curto-circuito e de vazio, e é assim que o motor os
# interpreta.
# Nomenclatura: a chave interna é sem "%" ("loadloss"/"noloadloss"); o "%"
# recolocado no comando .dss é trabalho do exportador (precedente:
# "pctstored" -> "%stored=" em _fmt_storage).

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
    # O medidor não monta formulário a partir deste dicionário: seus
    # campos (elemento monitorado e terminal) dependem da rede que está
    # em memória e são montados em _campos_medidor_dinamico. A chave
    # vazia existe só para que o acesso genérico em
    # _campos_tecnicos_derivacao não levante KeyError se algum fluxo
    # esbarrar no tipo.
    "EnergyMeter": [],
}

CORES = {
    "Line": "black", "Switch": "orange", "Transformer": "purple",
    "Load": "steelblue", "Generator": "darkgreen", "Capacitor": "brown",
    # TRANSPARÊNCIA TÉCNICA: "gold" (#FFD700) sumia no fundo branco da
    # cena — a ligação pontilhada e a caixa do leque do PVSystem ficavam
    # praticamente invisíveis. "goldenrod" (#DAA520) mantém a leitura de
    # "dourado" com contraste suficiente sobre branco.
    "PVSystem": "goldenrod", "Storage": "teal", "Reactor": "sienna",
    "Vsource": "red",
    "EnergyMeter": "darkslategray",
}

# ------------------------------------------------------------------ #
# Constantes de desenho do "leque" de elementos conectados.
#
# Todas são FIXAS em pixels, de propósito: não acompanham a escala do
# auto-encaixe. Numa rede pequena a escala calculada é grande, e ícones
# que escalassem junto seriam empurrados para fora da área visível — o
# leque cresceria mais do que o espaço em volta.
# ------------------------------------------------------------------ #
RAIO_BARRA_BASE = 8
RAIO_LEQUE = 58
MEIA_LARGURA_CAIXA = 26
MEIA_ALTURA_CAIXA = 13

# Margem fixa (pixels) que o auto-encaixe reserva nas bordas. Tem de
# cobrir RAIO_LEQUE + max(MEIA_LARGURA_CAIXA, MEIA_ALTURA_CAIXA) e ainda
# sobrar espaço para o rótulo de texto; abaixo disso o leque da barra
# mais externa é cortado pela borda da vista.
MARGEM_FIT = 150

# Distância (pixels) do rótulo de ramo até a linha, medida na
# perpendicular. Está no escopo do módulo, e não embutida no
# redesenhar(), porque o arraste usa o mesmo número: o rótulo se
# reposiciona ao vivo durante o movimento, e duas cópias do valor fariam
# o texto saltar de lado no instante em que o botão do mouse fosse solto.
DESLOCAMENTO_ROTULO_RAMO = 16


def _reposicionar_segmento(item, novo_ponto, mover_fim: bool) -> None:
    """Leva uma das pontas do segmento para `novo_ponto`.

    `mover_fim=True` desloca a ponta final, `False` a inicial. A ponta
    oposta é lida do próprio item, não recebida como argumento. Durante
    um arraste ela pode já ter andado, e repassar um valor capturado
    antes do movimento reintroduziria o atraso visual que a atualização
    ao vivo existe para eliminar.
    """
    linha = item.line()
    if mover_fim:
        item.setLine(linha.x1(), linha.y1(), novo_ponto[0], novo_ponto[1])
    else:
        item.setLine(novo_ponto[0], novo_ponto[1], linha.x2(), linha.y2())


def _ponto_medio_deslocado(item, deslocamento: float) -> tuple:
    """Ponto médio do segmento recuado na perpendicular.

    A perpendicular é (-dy, dx) normalizada, com Y crescendo para baixo:
    a mesma convenção do redesenhar(). Segmento degenerado, com as duas
    pontas no mesmo ponto, não tem direção definida — nesse caso devolve
    o próprio ponto médio, em vez de dividir por zero.
    """
    linha = item.line()
    mx = (linha.x1() + linha.x2()) / 2
    my = (linha.y1() + linha.y2()) / 2
    dx, dy = linha.x2() - linha.x1(), linha.y2() - linha.y1()
    comprimento = math.hypot(dx, dy)
    if comprimento < 1e-9:
        return mx, my
    return (mx - dy / comprimento * deslocamento,
            my + dx / comprimento * deslocamento)


def _centralizar_rotulo(rotulo, x, y) -> None:
    """Posiciona o rótulo com (x, y) no centro do texto.

    O QGraphicsTextItem se posiciona pelo canto superior esquerdo. O
    deslocamento de meia caixa reproduz o `create_text` do Tk original,
    que recebia o centro, e é o mesmo cálculo usado em _desenhar_rotulo.
    """
    rect = rotulo.boundingRect()
    rotulo.setPos(x - rect.width() / 2, y - rect.height() / 2)


def _qcolor(nome: str) -> QColor:
    """Converte um nome de cor do Tk (ex.: 'steelblue') em QColor.

    QColor aceita os nomes SVG/X11, que são exatamente os mesmos que o
    Tk aceitava — por isso nenhuma cor da paleta CORES precisou mudar na
    migração. Nome inválido vira preto: um item invisível é pior de
    diagnosticar do que um item preto no lugar errado.
    """
    cor = QColor(nome)
    return cor if cor.isValid() else QColor("black")


def _escurecer(nome: str, fator: float) -> str:
    """Escurece uma cor, por nome ou hexadecimal, preservando o tom.

    Serve ao :hover dos botões do painel: cada botão tem fundo pastel
    próprio, e o realce precisa ser um tom mais escuro daquele mesmo
    fundo, não uma cor fixa.
    """
    cor = _qcolor(nome)
    return cor.darker(int(round(100 / max(fator, 0.01)))).name()


def _cor_texto_sobre(nome_cor: str) -> str:
    """Escolhe preto ou branco para o texto conforme o fundo.

    A conta é a luminância percebida (0.299R + 0.587G + 0.114B), que
    pondera o verde mais que o azul porque é assim que o olho responde.
    Acima de 128 o fundo é claro e o texto vai de preto; abaixo, de
    branco.
    """
    cor = _qcolor(nome_cor)
    luminancia = 0.299 * cor.red() + 0.587 * cor.green() + 0.114 * cor.blue()
    return "black" if luminancia >= 128 else "white"


def _cor_texto_id() -> str:
    """Cor do rótulo que identifica o projeto: o azul institucional."""
    return COR_ACCENT_MARCA


class _BarraItem(QGraphicsEllipseItem):
    """Barra da rede desenhada como elipse (substitui o create_oval do Tk).

    Móvel e selecionável. Ao ser arrastada, grava a posição de tela de
    volta em `editor._posicoes[nome]` — ajuste visual transitório, porque
    o layout continua automático (ver TRANSPARÊNCIA TÉCNICA).
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
        # ItemSendsGeometryChanges é OBRIGATÓRIA para que itemChange()
        # receba ItemPositionHasChanged. Sem ela o Qt simplesmente não
        # avisa sobre mudança de geometria, e o arraste fica mudo: a
        # barra anda na tela sem que ninguém saiba, e as linhas ficam
        # para trás.
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        # Z-order decide quem cobre quem: barra acima do ramo, rótulo
        # (3.0) acima da barra.
        self.setZValue(2.0)

    def paint(self, painter, option, widget=None):
        selecionado = self.isSelected()
        painter.setPen(QPen(_qcolor("black"), 2))
        painter.setBrush(QBrush(_qcolor("white")))
        painter.drawEllipse(self.rect())
        if selecionado:
            # Marca de seleção: anel tracejado por fora da elipse. Não
            # existia no Tk, onde o Canvas não tinha estado de seleção.
            pen = QPen(_qcolor("red"), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = self._raio + 4
            painter.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))

    def itemChange(self, change, value):
        # Chamado pelo Qt a cada mudança de estado do item. Aqui só
        # interessa a posição: sincroniza a coordenada de tela com o
        # dicionário que o redesenhar() consulta e, em seguida, refaz a
        # geometria do que está pendurado nesta barra. O modelo não é
        # tocado.
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
                and self._editor is not None):
            self._editor._ao_mover_barra(self.nome_barra, self.pos())
            self._editor._atualizar_geometria_barra(self.nome_barra)
        return super().itemChange(change, value)


class _DerivacaoItem(QGraphicsRectItem):
    """Caixa de uma derivação (carga, gerador, fonte, medidor...), móvel.

    A caixa existe para ser arrastada. Numa barra com oito elementos
    pendurados o leque se atravessa, e tirar dali o que está incomodando
    é mais rápido do que qualquer reorganização automática.

    A posição arrastada vira override da sessão: o redesenhar() passa a
    usar esse valor no lugar do ângulo calculado. Nada vai para o JSON —
    o modelo segue sem campo de posição, então entre execuções o layout
    volta a ser o automático.

    O retângulo base nasce em (0, 0), com o canto superior esquerdo na
    origem. Isso deixa o item ser posicionado pelo CENTRO, que é também
    o valor que o override grava. Guardar o centro, e não o canto, evita
    que a caixa deslize alguns pixels a cada redesenho por conta de
    conversão de canto.
    """

    def __init__(self, nome: str, barra: str, editor: "EditorRede"):
        super().__init__(
            -MEIA_LARGURA_CAIXA, -MEIA_ALTURA_CAIXA,
            2 * MEIA_LARGURA_CAIXA, 2 * MEIA_ALTURA_CAIXA)
        self.nome_derivacao = nome
        self.barra_ancora = barra
        self._editor = editor
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        # Sem ItemSendsGeometryChanges o Qt não emite
        # ItemPositionHasChanged, e o arraste não avisa ninguém: a caixa
        # desliza enquanto a linha que a liga à barra fica parada onde
        # estava.
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    def itemChange(self, change, value):
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
                and self._editor is not None):
            self._editor._ao_mover_derivacao(
                self.nome_derivacao, self.barra_ancora, self.pos())
        return super().itemChange(change, value)


class _RotuloItem(QGraphicsTextItem):
    """Rótulo com retângulo de fundo atrás (replica _desenhar_rotulo do Tk:
    `create_text` seguido de `create_rectangle` + `tag_lower`).

    O fundo é pintado no mesmo drawRect do texto e não como item
    separado: assim nunca descola do texto quando o rótulo se move.

    TRANSPARÊNCIA TÉCNICA: `fundo=None` desliga o retângulo. É o caso
    dos rótulos desenhados DENTRO das caixas de derivação, onde o fundo
    branco cobria o preenchimento colorido do elemento e o texto sumia
    no meio dele."""

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
        # Fundo com 3px de folga horizontal e 1px vertical, os mesmos
        # números do original (x0-3, y0-1, x1+3, y1+1): a folga vertical
        # é menor porque a linha de texto já tem altura própria.
        if self._cor_fundo is not None:
            rect = self.boundingRect().adjusted(-3, -1, 3, 1)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self._cor_fundo))
            painter.drawRect(rect)
        else:
            # Sem fundo: nenhum retângulo é pintado, e o que aparece
            # atrás do texto é o preenchimento da caixa que o contém.
            painter.setBrush(Qt.BrushStyle.NoBrush)
        super().paint(painter, option, widget)


class _CanvasRede(QGraphicsView):
    """Área de desenho da rede, com zoom, pan e zoom de janela.

    A cena é desenhada em coordenadas de item que NÃO crescem com a
    janela: `_transformar_posicoes` já resolve o enquadramento inicial em
    pixels de tela. Por isso a vista nasce em escala 1.0 e o zoom de
    usuário é uma transformação adicional POR CIMA desse arranjo — ele
    não redimensiona itens nem reordena nada, apenas aproxima e afasta o
    que já está posicionado.

    Três interações convivem aqui:

    - roda do mouse amplia/reduz ancorada no cursor;
    - arrastar o fundo vazio desloca a vista (pan);
    - o modo "zoom de janela" troca o próximo arraste de retângulo pela
      vista resultante.

    Cliques que atingem um item seguem o caminho normal do Qt. Sem essa
    ressalva, ligar o pan no botão esquerdo engoliria o arraste das
    barras, que é o gesto mais frequente do editor.
    """

    FATOR_MIN = 0.1
    FATOR_MAX = 10.0
    PASSO_ZOOM = 1.15

    # Emitido quando o modo de zoom de janela termina por conta própria
    # (retângulo concluído ou Esc), para o botão do painel voltar ao
    # estado desmarcado. Sem a volta, o botão continuaria pressionado
    # indicando um modo que já não está ativo.
    zoom_janela_encerrado = Signal()

    def __init__(self, cena: QGraphicsScene, parent: QWidget = None):
        super().__init__(cena, parent)
        # A âncora sob o mouse é o que torna o zoom previsível: o ponto
        # que o usuário está olhando fica parado, e o resto cresce em
        # volta dele. Sem isso o conteúdo foge para um canto a cada
        # passo de ampliação e a pessoa precisa recentralizar à mão.
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        # Permite ao usuário empurrar o conteúdo para fora da vista e
        # trazê-lo de volta arrastando. Com os scrollbars travados em
        # zero, qualquer deslocamento para a esquerda/acima seria
        # irreversível.
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setMouseTracking(True)

        self._zoom_janela_ativo = False
        self._origem_janela = None
        self._retangulo_janela = None
        self._pan_ultimo = None
        self._pan_ativo = False

    # ------------------------------------------------------------------ #
    # Zoom
    # ------------------------------------------------------------------ #
    def _escala_atual(self) -> float:
        return self.transform().m11()

    def aplicar_zoom(self, fator: float, ancora_ponto=None) -> bool:
        """Multiplica a escala atual por `fator`, respeitando os limites.

        Devolve False quando o pedido caiu fora da faixa e nada mudou —
        assim quem chama (roda do mouse ou botão) sabe que o passo de
        zoom "bateu no teto" e não deve continuar tentando. Aplicar sem
        verificar os limites é o vício que produz a chamada instabilidade
        em que a rede é sugada para o canto da janela.
        """
        atual = self._escala_atual()
        alvo = atual * fator
        if (alvo <= self.FATOR_MIN and atual <= self.FATOR_MIN):
            return False
        if (alvo >= self.FATOR_MAX and atual >= self.FATOR_MAX):
            return False
        # O fator é cortado no limite antes de ser aplicado. Comparar o
        # alvo com o teto não basta: ali a razão vira 1.0 e o scale(),
        # embora inofensivo, seria chamado a cada evento da roda em um
        # laço sem fim útil.
        if alvo < self.FATOR_MIN:
            fator = self.FATOR_MIN / atual
        elif alvo > self.FATOR_MAX:
            fator = self.FATOR_MAX / atual
        if fator <= 0 or abs(fator - 1.0) < 1e-12:
            return False

        if ancora_ponto is None:
            self.scale(fator, fator)
        else:
            # A âncora manual existe para o zoom de janela, em que o
            # ponto de referência vem do retângulo arrastado e não do
            # cursor.
            antigo_ancora = self.transformationAnchor()
            self.setTransformationAnchor(
                QGraphicsView.ViewportAnchor.AnchorViewCenter)
            self.centerOn(ancora_ponto)
            self.scale(fator, fator)
            self.setTransformationAnchor(antigo_ancora)
        return True

    def ampliar(self) -> None:
        self.aplicar_zoom(self.PASSO_ZOOM)

    def reduzir(self) -> None:
        self.aplicar_zoom(1.0 / self.PASSO_ZOOM)

    def enquadrar_tudo(self) -> None:
        """Encaixa a cena inteira na vista, com folga nas bordas.

        A folga não é enfeite: os ícones do "leque" e os rótulos têm
        tamanho fixo em pixels e se estendem além do retângulo dos itens,
        então um `fitInView` sem margem corta justamente os nomes que o
        usuário foi procurar.
        """
        cena = self.scene()
        area = cena.itemsBoundingRect() if cena is not None else QRectF()
        if area.isNull() or area.isEmpty():
            return
        folga = 20.0
        area = area.adjusted(-folga, -folga, folga, folga)
        self.fitInView(area, Qt.AspectRatioMode.KeepAspectRatio)
        escala = self._escala_atual()
        if escala < self.FATOR_MIN or escala > self.FATOR_MAX:
            fator = (self.FATOR_MIN / escala if escala < self.FATOR_MIN
                     else self.FATOR_MAX / escala)
            self.scale(fator, fator)

    # ------------------------------------------------------------------ #
    # Zoom de janela
    # ------------------------------------------------------------------ #
    def definir_modo_zoom_janela(self, ativo: bool) -> None:
        estava_ativo = self._zoom_janela_ativo
        self._zoom_janela_ativo = bool(ativo)
        self._origem_janela = None
        self._retangulo_janela = None
        if ativo:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.unsetCursor()
            self.viewport().update()
            # Só avisa quando o modo estava de fato ligado. Este método
            # também é o slot de toggled(False), e emitir de volta ali
            # reentraria no botão à toa.
            if estava_ativo:
                self.zoom_janela_encerrado.emit()

    def modo_zoom_janela_ativo(self) -> bool:
        return self._zoom_janela_ativo

    def _aplicar_zoom_janela(self, retangulo_tela) -> None:
        """Leva a vista para o retângulo de tela indicado e sai do modo.

        Retângulos minúsculos (clique acidental sem arraste) são
        ignorados: ampliar para 2x2 pixels levaria a escala muito além do
        teto e a vista terminaria em um borrão sem referência nenhuma.
        """
        if retangulo_tela is None or not retangulo_tela.isValid():
            return
        if (retangulo_tela.width() < 8) or (retangulo_tela.height() < 8):
            return
        # mapToScene aceita QRect/QPoint, não QRectF — a conversão é
        # explícita para não depender do despacho interno do PySide.
        retangulo_int = retangulo_tela.toRect()
        area_cena = self.mapToScene(retangulo_int).boundingRect()
        if area_cena.isNull() or area_cena.isEmpty():
            return
        # O fitInView calcula a transformação a partir do centro da
        # vista. Com a âncora presa ao cursor, o resultado sairia
        # deslocado do retângulo desenhado; a âncora é suspensa durante
        # a operação e restaurada em seguida.
        ancora_anterior = self.transformationAnchor()
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.fitInView(area_cena, Qt.AspectRatioMode.KeepAspectRatio)
        self.setTransformationAnchor(ancora_anterior)
        escala = self._escala_atual()
        if escala < self.FATOR_MIN:
            fator = self.FATOR_MIN / escala
            self.scale(fator, fator)
        elif escala > self.FATOR_MAX:
            fator = self.FATOR_MAX / escala
            self.scale(fator, fator)
        self.definir_modo_zoom_janela(False)

    # ------------------------------------------------------------------ #
    # Eventos de mouse
    # ------------------------------------------------------------------ #
    def _clique_atingiu_item(self, evento) -> bool:
        item = self.itemAt(evento.position().toPoint())
        return item is not None

    def mousePressEvent(self, evento):
        if (evento.button() == Qt.MouseButton.LeftButton
                and self._zoom_janela_ativo
                and not self._clique_atingiu_item(evento)):
            self._origem_janela = evento.position().toPoint()
            self._retangulo_janela = None
            evento.accept()
            return

        if (evento.button() == Qt.MouseButton.MiddleButton
                or (evento.button() == Qt.MouseButton.LeftButton
                    and not self._clique_atingiu_item(evento))):
            # Botão esquerdo no fundo vazio e botão do meio em qualquer
            # ponto deslocam a vista. O botão do meio vale mesmo sobre um
            # item porque não conflita com o arraste das barras, que é
            # sempre com o esquerdo.
            self._pan_ativo = True
            self._pan_ultimo = evento.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            evento.accept()
            return

        super().mousePressEvent(evento)

    def mouseMoveEvent(self, evento):
        if self._zoom_janela_ativo and self._origem_janela is not None:
            atual = evento.position().toPoint()
            self._retangulo_janela = QRectF(
                self._origem_janela, atual).normalized()
            self.viewport().update()
            evento.accept()
            return

        if self._pan_ativo and self._pan_ultimo is not None:
            atual = evento.position().toPoint()
            delta = atual - self._pan_ultimo
            self._pan_ultimo = atual
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y())
            evento.accept()
            return

        super().mouseMoveEvent(evento)

    def mouseReleaseEvent(self, evento):
        if (self._zoom_janela_ativo and self._origem_janela is not None
                and evento.button() == Qt.MouseButton.LeftButton):
            atual = evento.position().toPoint()
            retangulo = QRectF(
                self._origem_janela, atual).normalized()
            self._origem_janela = None
            self._retangulo_janela = None
            self._aplicar_zoom_janela(retangulo)
            evento.accept()
            return

        if self._pan_ativo and (evento.button() in (
                Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton)):
            self._pan_ativo = False
            self._pan_ultimo = None
            self.unsetCursor()
            evento.accept()
            return

        super().mouseReleaseEvent(evento)

    def wheelEvent(self, evento):
        passo = evento.angleDelta().y()
        if passo == 0:
            super().wheelEvent(evento)
            return
        fator = self.PASSO_ZOOM if passo > 0 else 1.0 / self.PASSO_ZOOM
        if self.aplicar_zoom(fator):
            evento.accept()
        else:
            # No limite da faixa o evento é consumido mesmo assim. Deixar
            # o Qt rolar a vista aqui faria a roda ter um comportamento
            # nas bordas e outro no meio, o que confunde mais do que
            # ajuda.
            evento.accept()

    def keyPressEvent(self, evento):
        if (evento.key() == Qt.Key.Key_Escape
                and self._zoom_janela_ativo):
            self.definir_modo_zoom_janela(False)
            evento.accept()
            return
        super().keyPressEvent(evento)

    def drawForeground(self, painter, retangulo):
        super().drawForeground(painter, retangulo)
        if self._retangulo_janela is None:
            return
        # O retângulo vive em coordenadas de tela, então é pintado
        # restaurando-se a transformação de identidade do pintor.
        painter.save()
        painter.resetTransform()
        painter.setPen(QPen(_qcolor("steelblue"), 1.0, Qt.PenStyle.DashLine))
        painter.setBrush(QBrush(_qcolor("#dbe9f7")))
        painter.drawRect(self._retangulo_janela)
        painter.restore()


class EditorRede(QWidget):
    """Widget central do editor: painel de ferramentas, diagrama e lista.

    O estado de desenho vive em dicionários indexados por NOME do
    elemento (barra, ramo, derivação), refeitos a cada redesenhar(). É
    o preço de manter o layout automático: nada do que está na tela é
    fonte da verdade, o modelo `RedeEletrica` é.
    """

    def __init__(self, rede: RedeEletrica = None, projeto: Projeto = None):
        super().__init__()
        self.rede = rede or RedeEletrica()
        self.projeto = projeto
        self.orientacao = "vertical"

        # Posições de tela da última renderização, já passadas pelo
        # auto-encaixe. Reconstruídas inteiras a cada redesenhar().
        self._posicoes: Dict[str, tuple] = {}
        self._escala: float = 1.0
        # Trava de reentrância: mudar a posição de um item dispara
        # itemChange, que chamaria de volta o editor no meio do próprio
        # redesenho. Com a trava, esse eco é ignorado.
        self._redesenhando = False

        # Posições que o usuário impôs às caixas de derivação, por nome.
        # Sobrevivem ao redesenhar() e morrem com o editor: ajuste de
        # visualização, não dado de projeto.
        self._posicoes_derivacoes: Dict[str, tuple] = {}
        # O que precisa ser regeometrizado quando uma barra se desloca:
        # barra -> [(item_linha, qual extremidade se move, rótulo)].
        # Sem esse índice, arrastar uma barra deixaria as conexões para
        # trás até o próximo redesenho.
        self._dependencias_por_barra: Dict[str, list] = {}
        # Ligação pontilhada de cada derivação com sua barra: nome ->
        # (item_linha, nome_da_barra). Guardada porque o arraste da caixa
        # redesenha só essa linha, e não a cena.
        #
        # O motivo de não redesenhar tudo a cada pixel: o item arrastado
        # pertence à cena, e limpar a cena com o mouse pressionado
        # destrói o próprio item — o arraste morreria no primeiro
        # movimento. Daí a atualização de geometria no lugar.
        self._ligacoes_derivacoes: Dict[str, tuple] = {}
        self._rotulos_derivacoes: Dict[str, "_RotuloItem"] = {}
        # Estado do checkbox "Mostrar rótulos". Os nomes de barra não
        # entram nisso: são a referência de leitura do diagrama.
        self.mostrar_rotulos = True
        self._rotulos_ramos: list = []
        self._rotulos_elementos: list = []

        self._montar_layout()
        self._carregar_projeto_automaticamente()
        # Equivalente ao self.after(50, self.redesenhar) do Tk. O layout
        # só tem dimensão útil depois do primeiro ciclo de eventos; antes
        # disso o enquadramento seria calculado sobre uma área nula.
        QTimer.singleShot(0, self.redesenhar)

    # ------------------------------------------------------------------ #
    def _carregar_projeto_automaticamente(self):
        """Carrega `rede.json` do projeto, se o projeto tiver um.

        Falha de leitura vira aviso, não exceção: o editor abre com a
        rede vazia e o usuário continua podendo trabalhar, em vez de
        perder o programa inteiro por causa de um JSON corrompido.
        """
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
        """Monta o menu "Arquivo" na barra de menus da QMainWindow.

        O editor é embutido como widget central, então não é ele que
        cria a janela — mas ainda pode contribuir com o menu dela. No Tk
        isso era feito em _montar_menu(), via `master.config(menu=...)`.
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

        # A cena e a vista são criadas ANTES dos painéis: os botões de
        # visualização do painel esquerdo (zoom, enquadrar) precisam do
        # objeto já existente para se conectar aos métodos dele.
        self.cena = QGraphicsScene(self)
        self.cena.setBackgroundBrush(QBrush(_qcolor("white")))
        self.view = _CanvasRede(self.cena)
        self.view.setRenderHint(self.view.renderHints().SmoothPixmapTransform, True)
        self.view.setFrameShape(QFrame.Shape.StyledPanel)

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
        # Storage não tem botão próprio aqui: nasce pelo fluxo
        # "🔋 Sistema BESS", que é o único caminho que garante o
        # InvControl associado a ele.
        for texto, tipo in [("▣ Carga", "Load"), ("⚙ Gerador", "Generator"),
                            ("▭ Capacitor", "Capacitor"), ("☀ Fotovoltaico", "PVSystem"),
                            ("🌀 Reator", "Reactor"),
                            ("⚡ Fonte (Vsource)", "Vsource")]:
            coluna.addWidget(self._botao_painel(
                texto, lambda _checked=False, t=tipo: self._criar_derivacao(t)))

        # O medidor também fica fora do laço acima: não passa por
        # _criar_derivacao, porque o formulário dele não pede barra — a
        # âncora de desenho vem do elemento monitorado.
        coluna.addWidget(self._botao_painel("⏱ Medidor de energia",
                                            self._criar_medidor))

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

        # Controles de vista. Ficam no painel, e não flutuando sobre a
        # área de desenho: num diagrama denso, botão flutuante cai em
        # cima de elemento e esconde justamente a barra que se queria
        # clicar.
        coluna.addWidget(self._label_secao("— Visualização —"))

        linha_zoom = QHBoxLayout()
        linha_zoom.setSpacing(4)
        self.botao_zoom_mais = self._botao_painel("＋", self.view.ampliar)
        self.botao_zoom_mais.setToolTip("Ampliar a vista")
        self.botao_zoom_menos = self._botao_painel("−", self.view.reduzir)
        self.botao_zoom_menos.setToolTip("Reduzir a vista")
        linha_zoom.addWidget(self.botao_zoom_mais)
        linha_zoom.addWidget(self.botao_zoom_menos)
        coluna.addLayout(linha_zoom)

        self.botao_zoom_janela = QPushButton("Zoom de janela")
        self.botao_zoom_janela.setFont(fonte_padrao(10))
        self.botao_zoom_janela.setMinimumHeight(26)
        self.botao_zoom_janela.setCheckable(True)
        self.botao_zoom_janela.setCursor(Qt.CursorShape.PointingHandCursor)
        self.botao_zoom_janela.setStyleSheet(
            f"QPushButton {{ border: 1px solid {COR_ACCENT_MARCA};"
            f" border-radius: 4px; padding: 3px 6px; }}"
            f"QPushButton:hover {{ background-color: #e8eef5; }}"
            f"QPushButton:checked {{ background-color: #cfe2f3;"
            f" color: #1B1B1B; }}")
        self.botao_zoom_janela.setToolTip(
            "Marque e arraste um retângulo sobre a área desejada.\n"
            "Esc cancela o modo.")
        self.botao_zoom_janela.toggled.connect(
            self.view.definir_modo_zoom_janela)
        # A vista sai do modo por conta própria ao concluir o retângulo
        # ou no Esc. Sem este caminho de volta, o botão continuaria
        # marcado anunciando um modo que já não existe.
        self.view.zoom_janela_encerrado.connect(self._ao_encerrar_zoom_janela)
        coluna.addWidget(self.botao_zoom_janela)

        self.botao_enquadrar = self._botao_painel(
            "Enquadrar tudo", self.view.enquadrar_tudo)
        self.botao_enquadrar.setToolTip(
            "Reenquadra o diagrama inteiro na janela.\n"
            "Não refaz o layout da rede.")
        coluna.addWidget(self.botao_enquadrar)

        # Em diagrama denso os rótulos de elemento cobrem as linhas e uns
        # aos outros. Desligá-los é a saída rápida para enxergar a
        # topologia. Os nomes de barra não entram no desligamento: são a
        # referência com que a pessoa se localiza no desenho.
        self.check_mostrar_rotulos = QCheckBox("Mostrar rótulos")
        self.check_mostrar_rotulos.setFont(fonte_padrao(9))
        self.check_mostrar_rotulos.setChecked(self.mostrar_rotulos)
        self.check_mostrar_rotulos.setToolTip(
            "Exibe os nomes dos ramos e dos elementos.\n"
            "Os nomes das barras continuam visíveis.")
        self.check_mostrar_rotulos.toggled.connect(self._ao_alternar_rotulos)
        coluna.addWidget(self.check_mostrar_rotulos)

        coluna.addWidget(self._botao_painel(
            "Simular no OpenDSS", self.simular, fundo="#c8e6c9"))

        coluna.addStretch(1)

        label_dica_vista = QLabel(
            "Roda do mouse: zoom\n"
            "Arrastar o fundo: mover a vista\n"
            "Botão do meio: mover em qualquer ponto")
        fonte_dica_vista = fonte_padrao(8)
        fonte_dica_vista.setItalic(True)
        label_dica_vista.setFont(fonte_dica_vista)
        label_dica_vista.setStyleSheet("color: gray;")
        label_dica_vista.setWordWrap(True)
        coluna.addWidget(label_dica_vista)

        layout_principal.addWidget(painel_ferramentas)

        # ---------------- Cena / view (centro) ----------------
        # Cena e vista foram criadas no início do método, antes dos
        # painéis; aqui só entram no layout, com peso 1 para ficarem com
        # o espaço que sobra.
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
    def _ao_encerrar_zoom_janela(self):
        # Desmarca o botão quando a vista encerra o modo por conta
        # própria. O toggled resultante chama de volta o método da vista,
        # já com o modo desligado — inofensivo, e é o caminho mais curto
        # para manter botão e estado sincronizados sem criar uma flag a
        # mais só para isso.
        if self.botao_zoom_janela.isChecked():
            self.botao_zoom_janela.setChecked(False)

    def _botao_painel(self, texto, callback, fundo: str = None) -> QPushButton:
        # TRANSPARÊNCIA TÉCNICA: nos botões com fundo pastel fixo, a cor
        # do texto é declarada junto. Sem isso o texto herdava a
        # QPalette do sistema — no tema escuro do Windows, ButtonText é
        # branco — e sumia sobre os fundos claros. O ramo sem fundo
        # continua intocado de propósito: ali o fundo é o nativo, e ele
        # já acompanha a paleta.
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
        """Título de seção do painel: pequeno, itálico e centralizado."""
        label = QLabel(texto)
        fonte = fonte_padrao(8)
        fonte.setItalic(True)
        label.setFont(fonte)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #444444;")
        return label

    def _ao_mudar_orientacao(self, _marcado: bool = False):
        """Troca vertical/horizontal e redesenha.

        O layout é integralmente recalculado, então não há posição antiga
        a preservar — inclusive os overrides de arraste continuam
        valendo, porque são consultados por nome no redesenhar().
        """
        self.orientacao = "vertical" if self.radio_vertical.isChecked() else "horizontal"
        self.redesenhar()

    # ------------------------------------------------------------------ #
    # Curvas características (daily / duty / yearly) — botões 📈
    # ------------------------------------------------------------------ #
    def _abrir_editor_curva(self, parent_dialog, natureza, modo, valor_atual):
        """Abre o editor gráfico de uma curva e devolve o nome escolhido.

        Devolve None quando não há projeto aberto — curvas moram na pasta
        de curvas do projeto, e sem ela não haveria onde salvar.
        """
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
        """Campos técnicos do ramo, filtrados por tipo (Line/Switch/Transformer)."""
        return list(CAMPOS_RAMO_PARAMS[tipo])

    def _campos_tecnicos_derivacao(self, tipo):
        """Campos técnicos da derivação, mais os botões de curva.

        Os botões entram como um tipo de campo ("botao_grafico") com
        callback próprio, de modo que o formulário genérico de
        `pedir_valores` os desenhe sem saber o que é uma curva.
        """
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
        """Remove dos parâmetros as curvas que estão em branco.

        "Nenhuma" é o valor que o editor grava quando o usuário apaga uma
        curva. Deixar a string ir para o .dss faria o OpenDSS procurar um
        loadshape chamado "Nenhuma" e falhar na compilação.
        """
        for chave in ("daily", "duty", "yearly"):
            if parametros.get(chave) in (None, "", "Nenhuma"):
                parametros.pop(chave, None)
        return parametros

    # ------------------------------------------------------------------ #
    # Modelos dimensionados: usados na CRIAÇÃO de ramos/derivações
    # ------------------------------------------------------------------ #
    def _obter_parametros_tecnicos(self, tipo, campos_tecnicos):
        """Coleta os parâmetros técnicos do elemento novo.

        Quando o projeto já tem modelos dimensionados daquele tipo (feitos
        no Módulo de Dimensionamento), a primeira tela oferece reaproveitar
        um deles em vez de digitar tudo de novo. Devolve None se o usuário
        cancelar em qualquer das telas — e cancelar nunca deve criar um
        elemento pela metade.
        """
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
    # Medidor de energia (EnergyMeter)
    # ------------------------------------------------------------------ #
    def _opcoes_elemento_medidor(self) -> List[str]:
        """Alvos que o editor oferece para o medidor: os ramos do modelo
        (Line/Switch/Transformer). São os elementos de entrega de potência
        que o motor OpenDSS aceita como alvo de EnergyMeter — Load,
        Generator, PVSystem, Storage e a própria fonte são recusados pelo
        motor (verificado no dss-python 0.15.7). A ordem segue a de criação
        dos ramos, a mesma usada pela sugestão padrão.
        """
        return [f"{r.tipo}.{r.nome}" for r in self.rede.ramos.values()]

    def _criar_medidor(self):
        """Cria o medidor com a posição padrão na entrada principal de
        energia da rede (primeiro ramo ligado à barra da fonte) e deixa o
        usuário trocar o alvo/terminal no formulário.

        O formulário NÃO pede barra: a âncora visual do medidor é derivada
        do elemento monitorado e do terminal escolhidos — pedir barra
        também abriria espaço para um par (barra, elemento) inconsistente.
        """
        if not self.rede.obter_fonte():
            QMessageBox.warning(
                self, "Aviso",
                "Crie a Fonte (Vsource) antes de adicionar o medidor: é ela "
                "que define a entrada principal da rede.")
            return

        opcoes = self._opcoes_elemento_medidor()
        if not opcoes:
            QMessageBox.warning(
                self, "Aviso",
                "O medidor precisa monitorar um ramo (linha, chave ou "
                "transformador). Crie ao menos um ramo antes — o OpenDSS "
                "não aceita medir a própria fonte nem cargas.")
            return

        sugerido = self.rede.sugerir_medidor_padrao()
        valores_iniciais = (
            {"element": sugerido[0], "terminal": str(sugerido[1])}
            if sugerido else {})
        if sugerido:
            dica = ("Posição padrão: entrada principal da energia da rede "
                    "(primeiro ramo ligado à barra da fonte). Para medir "
                    "outro ponto, troque o elemento ou o terminal.")
        else:
            dica = ("Nenhum ramo está ligado à barra da fonte, então não há "
                    "entrada principal para sugerir. Escolha o elemento a "
                    "ser monitorado.")

        campos = [
            ("nome", "Nome do medidor", "texto", ""),
            ("element", "Elemento monitorado", "combobox", opcoes),
            ("terminal", "Terminal monitorado", "combobox", ["1", "2"]),
        ]
        valores = pedir_valores(self, "Novo Medidor de Energia", campos,
                                valores_iniciais, dica=dica)
        if valores is None:
            return

        nome_solicitado = valores.get("nome", "").strip() or "Medidor"
        elemento = valores.get("element", "").strip()
        terminal = valores.get("terminal", "1").strip()

        ancora = self.rede.resolver_alvo_medidor(elemento, terminal)
        if ancora is None:
            QMessageBox.critical(
                self, "Erro",
                f"O elemento monitorado '{elemento}' não existe na rede.")
            return

        try:
            nome_final = self.rede.adicionar_derivacao(
                "EnergyMeter", nome_solicitado, ancora,
                {"element": elemento, "terminal": terminal})
        except ValueError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return

        self._avisar_se_nome_ajustado(nome_solicitado, nome_final)
        self.redesenhar()

    def _editar_medidor(self, nome):
        """Edição dedicada do medidor (mesma lógica do editor dedicado do
        InvControl): sem escolha de barra, que é derivada do alvo. Ao
        renomear ou trocar o alvo, o medidor é recriado com os novos
        valores; cancelar o formulário não altera nada.
        """
        der = self.rede.derivacoes.get(nome)
        if not der:
            return

        campos = [
            ("nome", "Nome do medidor", "texto", ""),
            ("element", "Elemento monitorado", "combobox",
             self._opcoes_elemento_medidor()),
            ("terminal", "Terminal monitorado", "combobox", ["1", "2"]),
        ]
        valores_iniciais = {
            "nome": der.nome,
            "element": str(der.parametros.get("element", "") or ""),
            "terminal": str(int(float(der.parametros.get("terminal", 1)))),
        }

        valores = pedir_valores(
            self, f"Editar Medidor de Energia: {nome}",
            campos, valores_iniciais)
        if valores is None:
            return

        novo_nome = valores.get("nome", "").strip()
        elemento = valores.get("element", "").strip()
        terminal = valores.get("terminal", "1").strip()

        if not novo_nome:
            QMessageBox.critical(self, "Erro", "Informe um nome para o medidor.")
            return

        ancora = self.rede.resolver_alvo_medidor(elemento, terminal)
        if ancora is None:
            QMessageBox.critical(
                self, "Erro",
                f"O elemento monitorado '{elemento}' não existe na rede.")
            return

        try:
            self.rede.remover_derivacao(nome)
            self.rede.adicionar_derivacao(
                "EnergyMeter", novo_nome, ancora,
                {"element": elemento, "terminal": terminal})
        except ValueError as e:
            self.rede.derivacoes[nome] = der
            QMessageBox.critical(self, "Erro", str(e))
            return

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
        # A identidade do que foi clicado vem dos dados do item
        # (Qt.UserRole), gravados em _atualizar_lista_elementos como o
        # par (categoria, nome). No Tk esse par ia embutido no iid da
        # Treeview, que aqui não existe.
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
            elif der and der.tipo == "EnergyMeter":
                self._editar_medidor(nome)
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
        # Editar ramo é remover e recriar, possivelmente com outro nome e
        # outro tipo. Sem reatribuir, os medidores que apontavam para o
        # nome antigo ficariam órfãos e a limpeza os apagaria — o usuário
        # perderia configuração por ter editado um ramo.
        self.rede.reatribuir_medidores(
            f"{ramo.tipo}.{nome}", f"{novo_tipo}.{nome_final}")
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
        # — o InvControl encontra o Storage pelo nome, e o nome muda com
        # a recriação do elemento.
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

        # O campo 'grupo' do elemento original é carregado para a
        # recriação. Sem isso, editar um Storage, Capacitor ou Reactor
        # que pertence a um Sistema BESS o soltaria do conjunto sem que
        # ninguém percebesse: ele continuaria na rede, mas sumiria do nó
        # do BESS na árvore.
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
        """Exclui os itens selecionados na árvore, respeitando a hierarquia.

        Barra leva junto tudo que está ligado a ela; nó de Sistema BESS
        leva junto o conjunto inteiro. Barra e conjunto pedem confirmação,
        porque a exclusão em cascata não aparece na seleção — o usuário
        marcou uma linha e vai perder vinte.
        """
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

        # O ramo excluído pode ser justamente o alvo de um medidor.
        # Critério adotado: o medidor não sobrevive ao que ele mede. Mas
        # o usuário é avisado do que saiu junto, porque apagar
        # configuração em silêncio é o que produz o "sumiu meu medidor"
        # sem explicação nenhuma.
        orfaos = self.rede.limpar_medidores_orfaos()
        if orfaos:
            QMessageBox.information(
                self, "Medidor(es) removido(s)",
                "Removido(s) por monitorarem elemento excluído:\n"
                + "\n".join(orfaos))

        self.redesenhar()

    def _atualizar_lista_elementos(self):
        # A lista é remontada do zero a cada redesenhar(), então a
        # seleção é guardada aqui antes do clear e reaplicada no fim.
        # No Tk isso não era necessário: redesenhar() reconstruía só o
        # canvas, e a Treeview ficava como estava.
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

        # Quem tem 'grupo' preenchido pertence a um Sistema BESS e vai
        # para o nó do conjunto; o resto fica solto em "Conectados".
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
            if d.tipo == "EnergyMeter":
                local = f"elemento: {d.parametros.get('element', '?')}"
            else:
                local = f"bus: {d.bus1}"
            _novo_item(grupo_ders, nome + sufixo_curva, (d.tipo, local),
                       referencia=("derivacao", nome))

        # Reaplica a seleção anterior, ignorando o que foi excluído.
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
    # Auto-encaixe (fit-to-view): converte coordenada de modelo em
    # coordenada de tela, aplicando escala e centralização. A margem é
    # fixa e existe para os ícones do leque, que têm tamanho fixo em
    # pixels e por isso não encolhem junto com o resto — sem ela, o leque
    # da barra mais externa sai cortado pela borda.
    # ------------------------------------------------------------------ #
    def _transformar_posicoes(self, posicoes_cruas):
        """Devolve (posições em coordenada de tela, escala usada).

        A escala é a mesma nos dois eixos: `min` entre a razão horizontal
        e a vertical, para não deformar o desenho. O piso de 0.15 e o
        teto de 2.5 são práticos — abaixo do piso um circuito grande
        vira poeira ilegível, e acima do teto uma rede de duas barras
        fica com elipses gigantes ocupando a tela.
        """
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
    # Leque de derivações: acha, para uma barra, o maior intervalo
    # angular LIVRE em relação aos ramos já conectados a ela. O leque
    # (Carga, Gerador, PV, Fonte...) é desenhado dentro desse intervalo,
    # e é o que evita que as caixas caiam em cima de uma linha.
    #
    # Convenção de ângulo: 0°=direita, 90°=baixo, 180°=esquerda,
    # 270°=cima. É o sistema de tela, em que Y cresce para baixo — o
    # oposto do plano cartesiano usado na análise de circuitos, e a
    # origem da maior parte das confusões de sinal neste arquivo.
    # ------------------------------------------------------------------ #
    def _calcular_intervalo_derivacoes(self, bus, posicoes, angulo_padrao):
        """Devolve (ângulo inicial, ângulo final) do leque, em graus.

        Sem nenhum ramo na barra, devolve uma abertura fixa de 150° em
        torno do ângulo padrão. Com ramos, mede o vão entre eles e
        recua 15° de cada lado, para o leque não encostar nas linhas.
        """
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
        """Desenha um rótulo com (x, y) no centro do texto e devolve o item."""
        rotulo = _RotuloItem(texto, cor, tamanho_fonte, fundo)
        # O create_text do Tk recebia (x, y) como CENTRO do texto, com
        # justify="center". QGraphicsTextItem se posiciona pelo canto
        # superior esquerdo — daí o recuo de meia largura e meia altura.
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

    def _ao_mover_derivacao(self, nome, barra, ponto):
        """Grava a posição imposta à caixa e regeometriza só o que depende
        dela: a linha pontilhada e o rótulo. O resto da cena fica parado.

        Diferente do arraste de barra, não há nada pendurado na caixa: a
        ligação termina nela. Por isso basta mexer no próprio par
        linha/rótulo, sem propagar nada adiante.
        """
        if self._redesenhando:
            return
        self._posicoes_derivacoes[nome] = (ponto.x(), ponto.y())
        self._posicoes[nome] = (ponto.x(), ponto.y())

        ligacao = self._ligacoes_derivacoes.get(nome)
        if ligacao is not None:
            item_ligacao, _ancora = ligacao
            _reposicionar_segmento(
                item_ligacao, (ponto.x(), ponto.y()), mover_fim=True)

        rotulo = self._rotulos_derivacoes.get(nome)
        if rotulo is not None:
            _centralizar_rotulo(rotulo, ponto.x(), ponto.y())

    def _atualizar_geometria_barra(self, nome):
        """Redesenha no lugar as conexões que tocam a barra `nome`.

        Chamado a cada passo do arraste. Redesenhar() inteiro não serve
        aqui: limpar a cena levaria junto o item que o mouse arrasta, e o
        arraste morreria no primeiro pixel. Só os pontos finais das
        linhas e as posições dos rótulos são refeitos.
        """
        if self._redesenhando:
            return
        pos = self._posicoes.get(nome)
        if pos is None:
            return

        for item, mover_fim, rotulo in self._dependencias_por_barra.get(nome, ()):
            _reposicionar_segmento(item, pos, mover_fim)
            if rotulo is not None:
                # O rótulo do ramo mora no ponto médio recuado na
                # perpendicular, e o recuo é refeito pela mesma fórmula do
                # redesenhar(). Duas fórmulas diferentes fariam o texto
                # pular de lado no instante em que o mouse fosse solto.
                mx, my = _ponto_medio_deslocado(item, DESLOCAMENTO_ROTULO_RAMO)
                _centralizar_rotulo(rotulo, mx, my)

        # As caixas do leque pendem desta barra, e a linha de ligação tem
        # de acompanhar. Parada, ela passaria a apontar para outro ponto
        # do desenho e o diagrama mentiria sobre o que está conectado.
        for der_nome, (item, ancora) in list(self._ligacoes_derivacoes.items()):
            if ancora != nome:
                continue
            destino = self._posicoes.get(der_nome)
            if destino is None:
                continue
            # Na ligação em leque, a ponta que se move é a que sai da
            # barra (a inicial). A que toca a caixa fica onde está, e é
            # ela que _reposicionar_segmento preserva.
            _reposicionar_segmento(item, pos, mover_fim=False)

    def _ao_alternar_rotulos(self, marcado: bool):
        """Mostra ou esconde os rótulos de ramo e de elemento.

        Alterna a visibilidade dos itens que já existem, sem redesenhar.
        A cena continua montada, o zoom e a rolagem ficam onde estavam, e
        marcar um checkbox não pode custar um relayout inteiro do
        diagrama. Efeito colateral, e desejado: as posições impostas às
        caixas continuam valendo.
        """
        self.mostrar_rotulos = bool(marcado)
        for rotulo in self._rotulos_ramos + self._rotulos_elementos:
            rotulo.setVisible(self.mostrar_rotulos)

    # ------------------------------------------------------------------ #
    def redesenhar(self):
        """Reconstrói a cena inteira a partir do modelo.

        Ordem obrigatória, por causa das camadas: ramos e ligações
        primeiro, caixas de derivação depois, barras por cima e rótulos
        no topo — o que é atribuído também pelo Z-value de cada item.
        Nada da cena é reaproveitado: os itens antigos são destruídos no
        clear() e todos os índices de arraste são remontados.
        """
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

            # Os índices que o arraste consulta são remontados a cada
            # redesenho. A cena foi descartada logo acima, então manter
            # os valores antigos guardaria referências a itens mortos.
            self._dependencias_por_barra = {}
            self._ligacoes_derivacoes = {}
            self._rotulos_derivacoes = {}
            self._rotulos_ramos = []
            self._rotulos_elementos = []

            # ---- Ramos (linhas entre barras) ---- #
            for ramo in self.rede.ramos.values():
                p1 = posicoes.get(ramo.bus1)
                p2 = posicoes.get(ramo.bus2)
                if not p1 or not p2:
                    continue

                cor = CORES.get(ramo.tipo, "black")
                linha = QGraphicsLineItem(p1[0], p1[1], p2[0], p2[1])
                caneta = QPen(_qcolor(cor), espessura_linha)
                # Chave (Switch) sai tracejada, Linha sai contínua. É a
                # única pista visual de que aquele trecho pode ser aberto.
                if ramo.tipo == "Switch":
                    caneta.setStyle(Qt.PenStyle.DashLine)
                linha.setPen(caneta)
                linha.setZValue(0.0)
                self.cena.addItem(linha)

                mx, my = _ponto_medio_deslocado(linha, DESLOCAMENTO_ROTULO_RAMO)
                rotulo_ramo = None
                if self.mostrar_rotulos:
                    rotulo_ramo = self._desenhar_rotulo(
                        mx, my, f"{ramo.tipo}\n{ramo.nome}", cor)
                    self._rotulos_ramos.append(rotulo_ramo)

                # O ramo entra no índice das DUAS barras que ele liga,
                # marcando em cada entrada qual ponta se move. Arrastar
                # qualquer uma das barras leva o mesmo segmento e o mesmo
                # rótulo junto.
                if ramo.bus1 in posicoes:
                    self._dependencias_por_barra.setdefault(
                        ramo.bus1, []).append((linha, False, rotulo_ramo))
                if ramo.bus2 in posicoes:
                    self._dependencias_por_barra.setdefault(
                        ramo.bus2, []).append((linha, True, rotulo_ramo))

            # ---- Derivações, em leque ao redor da barra (tamanho FIXO) ---- #
            # Quem não tem barra (bus1=None, caso do InvControl) cai sob a
            # chave None. Como `posicoes` só contém nomes de barras
            # reais, a busca por None devolve None e o laço abaixo pula
            # esses elementos: eles existem na árvore e no .dss, mas não
            # têm onde ser desenhados.
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

                    # Posição imposta pelo usuário manda sobre o ângulo
                    # calculado. Quem tirou a caixa do emaranhado não quer
                    # vê-la de volta ao leque no redesenho seguinte.
                    override = self._posicoes_derivacoes.get(der.nome)
                    if override is not None:
                        ex, ey = override
                    self._posicoes[der.nome] = (ex, ey)

                    cor = CORES.get(der.tipo, "gray")

                    ligacao = QGraphicsLineItem(pos_bus[0], pos_bus[1], ex, ey)
                    caneta = QPen(_qcolor(cor), max(1, espessura_linha - 2))
                    caneta.setStyle(Qt.PenStyle.DotLine)
                    ligacao.setPen(caneta)
                    ligacao.setZValue(0.0)
                    self.cena.addItem(ligacao)
                    self._ligacoes_derivacoes[der.nome] = (ligacao, bus)

                    caixa = _DerivacaoItem(der.nome, bus, self)
                    caixa.setPos(ex, ey)
                    caixa.setBrush(QBrush(_qcolor(cor)))
                    caixa.setPen(QPen(_qcolor("black"), 1))
                    caixa.setZValue(1.0)
                    self.cena.addItem(caixa)

                    tem_curva = any(der.parametros.get(c) not in (None, "", "Nenhuma")
                                    for c in ("daily", "duty", "yearly"))
                    texto_der = f"{der.tipo}\n{der.nome}" + (" 📈" if tem_curva else "")
                    # Cor do texto escolhida por contraste com o
                    # preenchimento da caixa, e sem retângulo de fundo
                    # (fundo=None). Antes era branco fixo, que sobre os
                    # preenchimentos claros ficava ilegível.
                    if self.mostrar_rotulos:
                        self._rotulos_derivacoes[der.nome] = self._desenhar_rotulo(
                            ex, ey, texto_der, _cor_texto_sobre(cor),
                            tamanho_fonte=7, fundo=None)

            # O mapa de rótulos de elemento é refeito a partir do que foi
            # desenhado nesta passagem. Quem ficou de fora não entra, e é
            # assim que um elemento apontando para barra inexistente
            # desaparece do mapa em vez de sobrar com um rótulo morto.
            self._rotulos_elementos = [
                r for r in self._rotulos_derivacoes.values()]

            # ---- Barras ---- #
            for nome, barra in self.rede.barras.items():
                pos = posicoes.get(nome)
                if not pos:
                    continue
                x, y = pos
                item_barra = _BarraItem(nome, raio_barra, self)
                item_barra.setPos(x, y)
                self.cena.addItem(item_barra)
                # O nome da barra não passa pelo checkbox "Mostrar
                # rótulos": sem ele não há como se localizar no diagrama.
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
        """Zera a rede, depois de confirmar. Não toca nos arquivos do projeto."""
        if confirmar_win11("Novo projeto", "Descartar a rede atual?"):
            self.rede = RedeEletrica()
            self.redesenhar()

    def salvar_projeto(self):
        """Grava a rede em `rede.json`.

        Com projeto aberto, o destino é a pasta do projeto e não há
        diálogo. Sem projeto, pergunta onde salvar — e completa a
        extensão se o usuário não a digitar.
        """
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
        """Carrega uma rede de um .json escolhido pelo usuário."""
        pasta_inicial = self.projeto.caminho_rede if self.projeto else ""
        caminho, _filtro = QFileDialog.getOpenFileName(
            self, "Abrir rede", pasta_inicial, "Projeto JSON (*.json)")
        if caminho:
            self.rede = RedeEletrica.carregar_json(caminho)
            self.redesenhar()

    def _pasta_curvas_atual(self):
        """Pasta de curvas do projeto, ou None quando não há projeto."""
        return self.projeto.caminho_curvas if self.projeto else None

    def exportar_dss(self):
        """Exporta o circuito para .dss e informa onde ficou o Master.dss.

        Com projeto, o destino é a pasta de rede dele. Sem projeto,
        pergunta a pasta — e os arquivos saem avulsos, sem o resto da
        estrutura do projeto.
        """
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
        """Exporta o .dss e roda o OpenDSS sobre ele, mostrando versão e Vmin.

        Sem projeto aberto, o destino é uma pasta temporária: simular não
        pode exigir que exista um projeto salvo.
        """
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
