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
import sys

# MPLBACKEND deve ser definido ANTES de qualquer import de terceiros
# (matplotlib é importado indiretamente pelo editor de curvas).
os.environ.setdefault("MPLBACKEND", "QtAgg")

import math
import tempfile
from typing import Dict, List, Optional

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtCore import QEasingCurve, QLineF, QPointF, QRect, QVariantAnimation, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QToolButton,
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
# A caixa de derivação deixou de ter tamanho fixo. Ela abraça o próprio
# texto: a medida sai do QFontMetricsF da fonte do rótulo e cresce com
# ele. Um nome curto ("Load") rende uma pílula estreita; um nome longo
# ("CARGA_670a") rende uma pílula mais larga, sem texto vazando para
# fora do fundo colorido.
#
# As duas constantes abaixo são o único tamanho fixo que restou: a
# espessura da moldura em volta do texto. Horizontal maior que vertical
# porque a linha de texto já carrega o próprio respiro.
PADDING_CAIXA_H = 5
PADDING_CAIXA_V = 3

# Margem fixa (pixels) que o auto-encaixe reserva nas bordas. Tem de
# cobrir RAIO_LEQUE somado ao meia-largura/altura da MAIOR caixa que
# aquele leque possa produzir, e ainda sobrar espaço para o rótulo de
# texto; abaixo disso as caixas da barra mais externa são cortadas pela
# borda da vista. Como a caixa agora depende do texto, o valor cobre a
# pílula mais larga que o editor costuma desenhar (nome de 15 caracteres
# em 7pt, duas linhas).
MARGEM_FIT = 150

# Distância (pixels) do rótulo de ramo até a linha, medida na
# perpendicular. Está no escopo do módulo, e não embutida no
# redesenhar(), porque o arraste usa o mesmo número: o rótulo se
# reposiciona ao vivo durante o movimento, e duas cópias do valor fariam
# o texto saltar de lado no instante em que o botão do mouse fosse solto.
DESLOCAMENTO_ROTULO_RAMO = 16
# Distância (pixels de cena) do rótulo "Barra / Tensão" acima da elipse.
# Está aqui, e não embutida no desenho, porque o desvio do usuário é
# gravado em relação a este ponto: dois valores diferentes fariam o texto
# voltar ao lugar errado na reabertura do projeto.
DESLOCAMENTO_ROTULO_BARRA = 18

# ------------------------------------------------------------------ #
# Paleta do desenho do diagrama
#
# A gramática é a dos editores de diagrama atuais (Figma, Mermaid):
# superfície clara, contorno fino e um único acento cromático. A regra
# prática é deixar o desenho carregar a informação e a decoração não
# disputar atenção com ela — daí a sombra discreta e a grade de pontos
# quase invisível.
# ------------------------------------------------------------------ #
#
# A paleta deixou de ser um punhado de constantes soltas quando o editor
# passou a aceitar tema escuro. Duas listas de cor com as mesmas chaves
# resolvem melhor do que dezenas de nomes fixos: quem pinta pergunta ao
# tema corrente e não precisa saber de onde a cor veio. O tema claro
# reproduz exatamente os valores que existiam antes — quem trabalha no
# claro não percebe diferença nenhuma.
#
# A escolha entre os dois é automática (segue o Windows). O parâmetro
# `tema_forcado` de EditorRede existe para inspeção e teste; deixado em
# None, o tema é o do sistema.
_TEMAS = {
    "claro": {
        "fundo_canvas": "#ffffff",
        # A grade fica três tons abaixo do papel: aparece quando se olha
        # para ela e some quando se olha para a rede.
        "cor_grade": "#dbe2ea",
        "texto_primario": "#1B1B1B",
        "texto_secundario": "#64748b",
        "painel_fundo": "#f8fafc",
        "painel_borda": "#e9eef5",
        "painel_titulo": "#1e293b",
        "painel_secao": "#64748b",
        "botao_fundo": "#ffffff",
        "botao_borda": "#e2e8f0",
        "botao_texto": "#334155",
        "botao_hover": "#f1f5f9",
        "botao_pressionado": "#e2e8f0",
        "acento": COR_ACCENT_MARCA,
        "acento_hover": "#00356b",
        "acento_texto_sobre": "#ffffff",
        "perigo": "#b91c1c",
        "perigo_fundo": "#fef2f2",
        "perigo_borda": "#fecaca",
        "card_fundo": "#ffffff",
        "card_borda": "#e2e8f0",
        "card_titulo": "#0f172a",
        "card_corpo": "#475569",
        "card_vazio": "#94a3b8",
        "card_tag_fundo": "#eef4fb",
        "pilula_fundo": "rgba(255, 255, 255, 242)",
        "pilula_borda": "#e5e7eb",
        "pilula_texto": "#334155",
        "pilula_hover": "#f3f4f6",
        "pilula_risco": "#e5e7eb",
        "arvore_fundo": "#ffffff",
        "arvore_borda": "#e2e8f0",
        "arvore_alternada": "#f8fafc",
        "arvore_hover": "#eef2f7",
        "arvore_selecao": "#e8f0fa",
        "arvore_selecao_texto": "#004587",
        "arvore_cabecalho": "#94a3b8",
        "sombra": QColor(15, 23, 42, 40),
        "barra_fundo": "#ffffff",
        "barra_borda": "#334155",
        "texto_rotulo_barra": "black",
        "caixa_borda": "black",
        "halo_ramo": "#dbe9f7",
        "janela_zoom_fundo": "#dbe9f7",
    },
    "escuro": {
        # Superfície #0f172a e painel #111827: o mesmo par de tons que os
        # editores de código usam. Não é preto puro, porque preto chapado
        # vibra ao lado de linhas coloridas e cansa a vista mais rápido.
        "fundo_canvas": "#0f172a",
        "cor_grade": "#263143",
        # Texto em #e2e8f0 (não branco): branco sobre fundo escuro
        # "brilha" e borra a leitura de texto pequeno.
        "texto_primario": "#e2e8f0",
        "texto_secundario": "#94a3b8",
        "painel_fundo": "#111827",
        "painel_borda": "#1f2937",
        "painel_titulo": "#e2e8f0",
        "painel_secao": "#94a3b8",
        "botao_fundo": "#1e293b",
        "botao_borda": "#334155",
        "botao_texto": "#e2e8f0",
        "botao_hover": "#273449",
        "botao_pressionado": "#0b1220",
        # O azul institucional (#004587) reprova no contraste contra
        # fundo escuro — some. A versão clara da mesma família mantém a
        # identidade e continua legível.
        "acento": "#6ea8e8",
        "acento_hover": "#8fbdf0",
        "acento_texto_sobre": "#0b1220",
        "perigo": "#f87171",
        "perigo_fundo": "#2a1518",
        "perigo_borda": "#7f1d1d",
        "card_fundo": "#111827",
        "card_borda": "#374151",
        "card_titulo": "#e2e8f0",
        "card_corpo": "#cbd5e1",
        "card_vazio": "#94a3b8",
        "card_tag_fundo": "#1e293b",
        "pilula_fundo": "rgba(17, 24, 39, 245)",
        "pilula_borda": "#334155",
        "pilula_texto": "#e2e8f0",
        "pilula_hover": "#273449",
        "pilula_risco": "#334155",
        "arvore_fundo": "#0f172a",
        "arvore_borda": "#1f2937",
        "arvore_alternada": "#141d2f",
        "arvore_hover": "#1e293b",
        "arvore_selecao": "#1e3a5f",
        "arvore_selecao_texto": "#bfdbfe",
        "arvore_cabecalho": "#94a3b8",
        "sombra": QColor(0, 0, 0, 120),
        "barra_fundo": "#0f172a",
        "barra_borda": "#94a3b8",
        "texto_rotulo_barra": "#e2e8f0",
        "caixa_borda": "#0b1220",
        "halo_ramo": "#1e3a5f",
        "janela_zoom_fundo": "#1e3a5f",
    },
}

# Nomes expostos para quem quiser forçar um dos temas (teste, inspeção,
# captura de tela). O editor usa "escuro"/"claro" ao detectar o sistema.
TEMAS_DISPONIVEIS = ("claro", "escuro")
TEMA_PADRAO = "claro"

ESPACO_GRADE = 24.0
# Escala mínima para desenhar a grade. Com o diagrama afastado os
# pontos viram um borrão cinza que escurece o fundo inteiro sem ajudar
# a ler nada.
ESCALA_MINIMA_GRADE = 0.5

# Sombra pintada à mão, e não QGraphicsDropShadowEffect. O efeito do Qt
# é um filtro de pixel refeito a cada repintura; num item que anda a
# cada evento de mouse isso trava o arraste. Um retângulo deslocado
# custa duas chamadas de desenho.
DESLOCAMENTO_SOMBRA = 2.0
RAIO_CAIXA = 8.0
RAIO_CARTAO = 10.0

# Texto do cartão de propriedades sem seleção. Fica em constante porque
# o mesmo texto aparece no cartão (HTML) e no teste de estado vazio.
TEXTO_SEM_SELECAO = "Clique num elemento do diagrama para ver suas propriedades."


def _sistema_em_tema_escuro() -> bool:
    """Diz se o sistema operacional pede tema escuro.

    A pergunta certa é feita ao próprio Qt, que já sabe a resposta em
    cada plataforma e a atualiza quando o usuário troca. Ele pode não
    saber, porém: em alguns backends a resposta é `Unknown`, e é o caso
    do backend offscreen. Por isso a leitura do registro do Windows
    entra como segunda opinião — o valor `AppsUseLightTheme` é
    justamente o que o menu de configurações do Windows altera, e zero
    ali significa escuro.

    Qualquer falha vale "claro". Uma janela clara num sistema escuro
    continua legível; o contrário deixaria texto de baixo contraste
    para quem não pediu tema nenhum.
    """
    # 1) A resposta do Qt.
    try:
        from PySide6.QtGui import QGuiApplication
        aplicacao = QGuiApplication.instance()
        esquema_escuro = getattr(Qt, "ColorScheme", None)
        if aplicacao is not None and esquema_escuro is not None:
            esquema = aplicacao.styleHints().colorScheme()
            if esquema == esquema_escuro.Dark:
                return True
            if esquema == esquema_escuro.Light:
                return False
    except Exception:
        # Qt antigo, backend exótico ou styleHints indisponível: cai no
        # registro em vez de derrubar o editor por causa de cor.
        pass

    # 2) Registro do Windows. HKCU não exige privilégio algum.
    try:
        import winreg
        chave = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        try:
            valor, _tipo = winreg.QueryValueEx(chave, "AppsUseLightTheme")
        finally:
            chave.Close()
        return int(valor) == 0
    except Exception:
        return False


def _ponto_salvo_valido(posicao):
    """Converte a posição gravada no modelo em (x, y), ou None.

    O campo vem de um arquivo JSON, que pode ter sido editado à mão.
    Só passa o que for uma lista (ou tupla) de dois números; o resto é
    tratado como ausente, e o elemento volta ao layout automático.
    """
    if not isinstance(posicao, (list, tuple)) or len(posicao) != 2:
        return None
    try:
        return (float(posicao[0]), float(posicao[1]))
    except (TypeError, ValueError):
        return None


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


TAMANHO_FONTE_ROTULO_DERIVACAO = 7


def _medir_texto_rotulo(texto: str, tamanho_fonte: int) -> tuple:
    """Mede o texto do rótulo como o desenho vai precisar dele.

    Devolve (largura, altura) já considerando o teto de largura do
    _RotuloItem. Sem esse teto, um nome de vinte caracteres geraria uma
    pílula de meia cena. Com ele, a linha quebra e a largura para em
    LARGURA_MAXIMA — e a altura cresce para compensar, que é o que a
    medição por QFontMetricsF.naturalTextRect devolve.

    A medida é feita com a MESMA fonte que o item vai usar (7pt por
    padrão). Medir com outra fonte é o erro clássico aqui: a caixa fica
    alguns pixels menor que o conteúdo e o vazamento volta.
    """
    fonte = QFont()
    fonte.setPointSizeF(max(5.0, float(tamanho_fonte)))
    medida = QFontMetricsF(fonte)
    mais_larga = max(
        (medida.horizontalAdvance(linha) for linha in texto.split("\n")),
        default=0.0)
    largura = min(mais_larga, _RotuloItem.LARGURA_MAXIMA)
    # naturalTextRect calcula a quebra de linha e a altura correspondente
    # com a mesma engine que o QGraphicsTextItem usa. Pedir a altura linha
    # a linha vezes o número de linhas erraria por arredondamento de
    # leading (a folga entre linhas não é exatamente lineSpacing).
    rect = medida.boundingRect(
        QRectF(0, 0, largura, 1e6), int(Qt.TextFlag.TextWordWrap), texto)
    return rect.width(), rect.height()


def _prender_rotulo_na_caixa(rotulo, caixa) -> None:
    """Torna o rótulo filho da caixa e o centraliza no rect dela.

    Filho, e não vizinho: a partir daqui, mover a caixa move o texto
    junto por conta do Qt. O repositório de posições que existia antes
    (atualizar o rótulo a cada pixel de arraste da caixa) deixa de ser
    necessário para as derivações.

    Deixar de ser arrastável é consequência desejada. O texto preso é
    propriedade visual do elemento — arrastá-lo para fora seria o defeito
    que este trecho corrige. Barras e ramos mantêm o texto solto, onde o
    ajuste fino continua fazendo sentido.
    """
    rotulo.setParentItem(caixa)
    rotulo.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
    rotulo.setFlag(
        QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, False)
    rotulo.setCursor(Qt.CursorShape.PointingHandCursor)
    rect_caixa = caixa.rect()
    rect_texto = rotulo.boundingRect()
    rotulo.setPos(
        rect_caixa.center().x() - rect_texto.width() / 2,
        rect_caixa.center().y() - rect_texto.height() / 2)


def _ponto_na_borda_da_caixa(centro, alvo, meia_largura: float,
                             meia_altura: float) -> tuple:
    """Onde a linha barra→caixa encosta no retângulo da caixa.

    A ligação do leque saía do centro da barra e terminava no centro da
    caixa, entrando por baixo do preenchimento. Com a caixa maior, esse
    trecho enterrado cresceu. Recortar na borda resolve: a linha para
    exatamente no contorno, e o leque lê como uma ligação, não como um
    risco que some dentro do elemento.

    A interseção é a de um raio com um retângulo — a aproximação do rect
    de padding basta, porque RAIO_CAIXA (8 px) é pequeno diante das
    dimensões típicas. Nos cantos a linha entra alguns pixels, imperceptível
    neste tamanho.
    """
    dx = alvo[0] - centro[0]
    dy = alvo[1] - centro[1]
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return alvo[0], alvo[1]
    # Fração do caminho até bater no primeiro dos dois lados.
    escala_x = meia_largura / abs(dx) if abs(dx) > 1e-9 else float("inf")
    escala_y = meia_altura / abs(dy) if abs(dy) > 1e-9 else float("inf")
    escala = min(escala_x, escala_y)
    return alvo[0] - dx * escala, alvo[1] - dy * escala


def _desvio_rotulo_valido(desvio):
    """Converte o desvio [dx, dy] gravado no modelo em tupla, ou None.

    Vem do JSON e pode ter sido editado à mão. Só passa lista de dois
    números; qualquer outra coisa devolve o rótulo ao lugar automático,
    que é melhor do que um texto perdido fora da cena.
    """
    return _ponto_salvo_valido(desvio)


def _posicionar_rotulo_em(rotulo, x, y, desvio) -> None:
    """Centraliza o rótulo em (x, y) somando o desvio do usuário.

    `desvio` é o ajuste relativo ao lugar automático, e não uma
    coordenada. Aplicá-lo aqui, em todos os caminhos que posicionam
    rótulo, é o que faz o texto seguir o elemento arrastado mantendo a
    distância que o usuário escolheu.
    """
    ajuste = _desvio_rotulo_valido(desvio)
    if ajuste is not None:
        x += ajuste[0]
        y += ajuste[1]
    _centralizar_rotulo(rotulo, x, y)


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


def _no_tema(cor: str, tema: dict) -> str:
    """Devolve uma cor de elemento ajustada ao tema corrente.

    A paleta CORES nasceu para papel branco. Sobre fundo escuro, "black"
    e "darkgreen" se dissolvem no fundo e a linha do ramo desaparece —
    justo a informação que o diagrama existe para mostrar. A correção
    não é refazer a paleta: é clarear o que for escuro demais, mexendo
    só na luminosidade e preservando matiz e saturação, para que cada
    tipo de elemento continue sendo reconhecido pela cor.

    O limiar de 0,35 separa as cores que somem no escuro (preto, verde
    escuro, marrom, azul-aço) das que já se leem bem. No tema claro a
    função devolve a cor intacta, e é por isso que o desenho de quem usa
    o tema claro continua pixel a pixel igual ao de antes.
    """
    if tema.get("nome") != "escuro":
        return cor
    rgba = _qcolor(cor)
    matiz, saturacao, luminosidade, alfa = rgba.getHslF()
    if luminosidade >= 0.35:
        return cor
    ajustada = QColor.fromHslF(matiz, saturacao, 0.62, alfa)
    return ajustada.name()


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


def _tema_por_nome(modo: str) -> dict:
    """Monta o dicionário de cores de um tema, já identificado.

    A chave "nome" é acrescentada aqui, e não nas duas listas, porque a
    única coisa que o desenho precisa saber é se está no escuro — a
    pergunta que _no_tema faz. Toda chamada devolve um dicionário novo:
    quem receber o tema não corre o risco de alterar a tabela do módulo.
    """
    base = _TEMAS.get(modo) or _TEMAS[TEMA_PADRAO]
    tema = dict(base)
    tema["nome"] = modo if modo in TEMAS_DISPONIVEIS else TEMA_PADRAO
    return tema


def _formatar_potencia(valor: float) -> str:
    """Mostra potência sem casa decimal quando ela não acrescenta nada.

    "10.0 kW" e "10 kW" informam o mesmo; o segundo ocupa menos espaço
    numa bolha de tooltip que já traz tensão e contagem de ramos. A
    vírgula decimal entra porque o resto da interface é em português.
    """
    if abs(valor - round(valor)) < 0.05:
        return f"{int(round(valor))}"
    return f"{valor:.1f}".replace(".", ",")


def _somar_parametro(elementos, chave: str):
    """Soma um parâmetro numérico dos elementos, ignorando os vazios.

    Devolve None quando nenhum elemento declara o parâmetro — caso em
    que não há o que somar, e mostrar zero seria afirmar um valor que
    ninguém informou. Valor não numérico propaga ValueError de propósito:
    quem chama decide se omite o resumo ou trata de outro jeito.
    """
    valores = [e.parametros.get(chave) for e in elementos]
    preenchidos = [v for v in valores if v not in (None, "")]
    if not preenchidos:
        return None
    return sum(_converter_numero(v) for v in preenchidos)


def _converter_numero(valor) -> float:
    """Lê número digitado à mão, aceitando vírgula decimal.

    Os campos do formulário são de texto livre e o usuário brasileiro
    escreve "75,5". O float() do Python só entende ponto, então a
    vírgula é trocada antes da conversão — do contrário o resumo da
    barra sairia sem a potência que está escrita na tela.
    """
    if isinstance(valor, (int, float)):
        return float(valor)
    return float(str(valor).strip().replace(",", "."))


def _escapar_html(texto) -> str:
    """Neutraliza os caracteres que o Qt interpretaria como marcação.

    O nome de uma barra é digitado pelo usuário e vai para dentro de um
    HTML: um "<" solto abriria uma tag e engoliria o resto do cartão. A
    troca cobre os três caracteres que o subconjunto de HTML do Qt trata
    como sintaxe — nenhum nome técnico legítimo perde informação com
    isso, porque "<", ">" e "&" não fazem parte de nomes de barra do
    OpenDSS.
    """
    return (str(texto).replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _potencia_do_elemento(derivacao) -> str:
    """Resume a potência declarada por uma derivação, se houver alguma.

    Cada tipo de elemento declara potência com uma chave diferente, e o
    cartão precisa mostrar o número que o próprio formulário pediu — não
    uma grandeza inventada. Devolve texto vazio quando o elemento não tem
    potência a mostrar (medidor, InvControl) ou quando o campo ainda está
    em branco. Campo não numérico é tratado como ausente: o valor está
    na tela do formulário, e derrubar o cartão por causa dele seria
    desproporcional.
    """
    parametros = getattr(derivacao, "parametros", None) or {}

    def _ler(chave):
        valor = parametros.get(chave)
        if valor in (None, ""):
            return None
        try:
            return _converter_numero(valor)
        except (TypeError, ValueError):
            return None

    # A ordem importa: PVSystem e Generator declaram kVA (ou kW) e não
    # têm kvar próprio; capacitor e reator trabalham só com kvar.
    if derivacao.tipo == "Load":
        kw, kvar = _ler("kw"), _ler("kvar")
        partes = []
        if kw is not None:
            partes.append(f"{_formatar_potencia(kw)} kW")
        if kvar is not None:
            partes.append(f"{_formatar_potencia(kvar)} kvar")
        return " / ".join(partes)

    if derivacao.tipo in ("PVSystem", "Generator"):
        kva = _ler("kva")
        if kva is not None:
            return f"{_formatar_potencia(kva)} kVA"
        kw = _ler("kw")
        if kw is not None:
            return f"{_formatar_potencia(kw)} kW"
        return ""

    if derivacao.tipo in ("Capacitor", "Reactor"):
        kvar = _ler("kvar")
        if kvar is not None:
            return f"{_formatar_potencia(kvar)} kvar"
        return ""

    if derivacao.tipo == "Storage":
        kva = _ler("kva")
        kwh = _ler("kwh")
        partes = []
        if kva is not None:
            partes.append(f"{_formatar_potencia(kva)} kVA")
        if kwh is not None:
            partes.append(f"{_formatar_potencia(kwh)} kWh")
        return " / ".join(partes)

    if derivacao.tipo == "EnergyMeter":
        # O medidor não consome: o dado útil é o que ele mede.
        alvo = parametros.get("elemento") or parametros.get("element")
        if alvo:
            terminal = parametros.get("terminal")
            if terminal not in (None, ""):
                return f"mede {alvo}, terminal {terminal}"
            return f"mede {alvo}"
        return ""

    return ""


class _CartaoBarra(QGraphicsRectItem):
    """Painel de informações de uma barra, fixado ao lado dela.

    A bolha do tooltip resolve a consulta rápida, mas some quando o mouse
    se desloca — e comparar duas barras exige sair de uma para entrar na
    outra. O cartão é a versão que fica: abre no clique, permanece até
    outro clique, e acompanha a barra enquanto ela é arrastada.

    O desenho usa a paleta da interface (fundo claro, borda fina na cor
    institucional) e é montado com um único QGraphicsTextItem interno em
    HTML, porque uma tabela de elementos em várias linhas com alinhamento
    próprio é justamente o que texto rico resolve sem código de layout.

    Nada aqui é interativo: o cartão não aceita clique nem hover, e fica
    abaixo das barras em Z. Uma caixa de leitura que interceptasse o
    mouse atrapalharia exatamente a edição que ela deveria ajudar.
    """

    LARGURA = 240.0

    def __init__(self, nome_barra: str, tema: dict = None):
        super().__init__()
        self.nome_barra = nome_barra
        # O cartão guarda o tema em que nasceu: ele é criado ao abrir e
        # reconstruído na troca de tema, então não precisa saber mudar
        # de cara depois.
        self._tema = tema or _tema_por_nome(TEMA_PADRAO)
        self._texto = QGraphicsTextItem(self)
        self._texto.setDefaultTextColor(_qcolor(self._tema["texto_primario"]))
        fonte = QFont()
        fonte.setPointSizeF(7.5)
        self._texto.setFont(fonte)
        self._texto.setTextWidth(self.LARGURA - 2 * self.MARGEM)
        # Z abaixo das barras (2.0) e das caixas (1.0)? Não: o cartão
        # precisa ficar visível, mas nunca na frente do item que o
        # usuário quer clicar. O valor 0.5 o coloca sobre as linhas e sob
        # as barras — quem estiver por baixo do cartão continua clicável.
        self.setZValue(0.5)
        # Sem brush nem pen: o corpo é pintado em paint(), com cantos
        # arredondados. Deixar o QGraphicsRectItem preencher um retângulo
        # reto por baixo do arredondado faria os cantos aparecerem em
        # ângulo reto sob a borda curva.
        self.setBrush(Qt.BrushStyle.NoBrush)
        self.setPen(Qt.PenStyle.NoPen)

    MARGEM = 8.0

    def boundingRect(self):
        """Área a repintar, com a folga da sombra deslocada.

        A sombra sai do rect do cartão (DESLOCAMENTO_SOMBRA para baixo e
        para a direita). Sem a folga, o Qt repintaria só o retângulo do
        corpo e o rastro da sombra ficaria no fundo quando o cartão
        andasse junto com a barra.
        """
        return self.rect().adjusted(
            0.0, 0.0,
            DESLOCAMENTO_SOMBRA + 1.0, DESLOCAMENTO_SOMBRA + 1.0)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        corpo = self.rect()
        # Sombra primeiro, deslocada e sem contorno: ela fica atrás e
        # descolada do corpo, o que é o que dá a impressão de o cartão
        # estar suspenso sobre o diagrama.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._tema["sombra"]))
        painter.drawRoundedRect(
            corpo.translated(DESLOCAMENTO_SOMBRA, DESLOCAMENTO_SOMBRA),
            RAIO_CARTAO, RAIO_CARTAO)
        painter.setBrush(QBrush(_qcolor(self._tema["card_fundo"])))
        painter.setPen(QPen(_qcolor(self._tema["acento"]), 1))
        painter.drawRoundedRect(corpo, RAIO_CARTAO, RAIO_CARTAO)

    def atualizar(self, titulo: str, linhas: list) -> None:
        """Redesenha o conteúdo e reajusta o retângulo ao texto.

        A altura sai do boundingRect do próprio texto: fixar uma altura
        deixaria espaço morto numa barra com dois elementos e cortaria a
        lista numa barra com dez.
        """
        partes = [
            f"<div style='font-size:9pt; font-weight:600;"
            f" color:{self._tema['acento']};'>{_escapar_html(titulo)}</div>"
        ]
        for linha in linhas:
            partes.append(
                f"<div style='margin-top:2px;'>{_escapar_html(linha)}</div>")
        self._texto.setHtml("".join(partes))
        self._texto.setPos(self.MARGEM, self.MARGEM)
        altura = self._texto.boundingRect().height() + 2 * self.MARGEM
        self.setRect(0, 0, self.LARGURA, altura)

    def altura(self) -> float:
        """Altura corrente do retângulo, já com as margens."""
        return self.rect().height()


class _BarraItem(QGraphicsEllipseItem):
    """Barra da rede desenhada como elipse (substitui o create_oval do Tk).

    Móvel e selecionável. Ao ser arrastada, grava a posição de tela em
    `editor._posicoes[nome]` e no campo `posicao` da barra no modelo. O
    primeiro alimenta o desenho corrente; o segundo, gravado no
    rede.json, é o que faz o arranjo reaparecer na próxima abertura
    (ver TRANSPARÊNCIA TÉCNICA).

    O destaque sob o cursor existe porque num alimentador real a elipse
    sozinha não diz nada: saber que ali há três ramos e uma carga de
    200 kW exige abrir o formulário. O resumo aparece sem clique e
    desaparece quando o mouse sai.
    """

    def __init__(self, nome: str, raio: float, editor: "EditorRede"):
        super().__init__(QRectF(-raio, -raio, 2 * raio, 2 * raio))
        self.nome_barra = nome
        self._editor = editor
        self._raio = raio
        self._sob_cursor = False
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
        # Eventos de hover chegam só nos itens que os pedem. Sem esta
        # linha o Qt nunca chama hoverEnterEvent, e o destaque jamais
        # acenderia.
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Z-order decide quem cobre quem: barra acima do ramo, rótulo
        # (3.0) acima da barra.
        self.setZValue(2.0)

    def paint(self, painter, option, widget=None):
        selecionado = self.isSelected()
        # O cartão aberto vale como estado de seleção para o halo: a
        # barra que está sendo lida continua realçada mesmo com o mouse
        # fora dela, e sai do realce no instante em que o cartão fecha.
        destacada = selecionado or (
            self._editor is not None
            and getattr(self._editor, "_cartao_barra_nome", None) == self.nome_barra)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Preenchimento branco chapado e contorno por estado: cinza
        # grafite em repouso, acento institucional ao passar o mouse ou
        # enquanto o cartão da barra está aberto. O contorno é quem
        # carrega o estado; o miolo branco mantém a barra legível sobre
        # qualquer linha que passe por baixo dela.
        tema = self._tema()
        cor_contorno = (_qcolor(tema["acento"])
                        if (self._sob_cursor or destacada)
                        else _qcolor(tema["barra_borda"]))
        painter.setPen(QPen(cor_contorno, 2))
        painter.setBrush(QBrush(_qcolor(tema["barra_fundo"])))
        painter.drawEllipse(self.rect())
        if (self._sob_cursor or destacada) and not selecionado:
            # Halo na cor institucional, por fora da elipse. Fica atrás
            # do anel de seleção na ordem de desenho (só um dos dois
            # aparece, porque o selecionado tem precedência): dois
            # anéis concêntricos ao mesmo tempo confundiriam mais do que
            # informariam.
            pen = QPen(_qcolor(tema["acento"]), 2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = self._raio + 3
            painter.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))
        if selecionado:
            # Marca de seleção: anel tracejado por fora da elipse. Não
            # existia no Tk, onde o Canvas não tinha estado de seleção.
            pen = QPen(_qcolor(tema["perigo"]), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = self._raio + 4
            painter.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))

    def _tema(self) -> dict:
        """Tema do editor, com um padrão para itens fora do editor.

        Um _BarraItem solto (num teste de pintura, por exemplo) não tem
        editor; cair no tema claro evita um AttributeError no meio do
        paint, que o Qt trataria como travamento da cena inteira.
        """
        if self._editor is not None:
            return self._editor._tema
        return _tema_por_nome(TEMA_PADRAO)

    def boundingRect(self):
        """Região a repintar, com folga para o halo de destaque.

        O halo excede a elipse: sem a margem, o Qt repinta só o rect da
        elipse e o que ficou para fora permanece no fundo — o rastro que
        o usuário relata. Margem constante dispensa prepareGeometryChange.
        """
        margem = 6.0
        return QRectF(self.rect().adjusted(-margem, -margem, margem, margem))

    # ------------------------------ HOVER ------------------------------ #

    def hoverEnterEvent(self, event):
        self._sob_cursor = True
        # O tooltip é montado no instante do hover, não no redesenho: a
        # rede muda por baixo do cursor (elemento criado, carga editada)
        # e um texto guardado desde o desenho anterior mentiria.
        self.setToolTip(self._resumo_para_tooltip())
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._sob_cursor = False
        # Texto vazio é como o Qt entende "não há o que mostrar"; a
        # bolha some sozinha ao sair do item.
        self.setToolTip("")
        self.update()
        super().hoverLeaveEvent(event)

    # ------------------------------ CLIQUE ----------------------------- #

    def mousePressEvent(self, event):
        # O clique é registrado no press, e não no release, porque é o
        # press que decide se o item vai ser arrastado: o Qt entrega o
        # movimento subsequente a este item e o release chega mesmo que o
        # arraste tenha terminado longe da elipse. Guardar a posição
        # inicial aqui permite comparar no release e separar "clicou"
        # de "arrastou a barra para outro lugar".
        self._press_pos = event.screenPos() if hasattr(event, "screenPos") else None
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        inicio = getattr(self, "_press_pos", None)
        self._press_pos = None
        if inicio is not None:
            fim = event.screenPos() if hasattr(event, "screenPos") else inicio
            distancia = ((fim.x() - inicio.x()) ** 2
                         + (fim.y() - inicio.y()) ** 2) ** 0.5
            if distancia > _CanvasRede.LIMIAR_ARRASTE:
                # Foi um arraste: a barra mudou de lugar e o cartão deve
                # continuar exatamente como estava, agora na posição nova.
                return
        if self._editor is not None:
            self._editor.alternar_cartao_barra(self.nome_barra)
            # O cartão flutuante é a leitura rápida no mapa; o painel de
            # propriedades é a leitura completa. Os dois abrem no mesmo
            # clique, porque o usuário pediu as duas coisas e obrigá-lo a
            # clicar duas vezes para ver o detalhe seria atrito sem
            # motivo.
            self._editor._selecionar_no_mapa("barra", self.nome_barra)

    def _resumo_para_tooltip(self) -> str:
        """Uma linha de contexto sobre a barra: tensão, ramos e carga.

        Os números vêm do modelo vivo a cada hover, porque a rede
        editada é a fonte da verdade — o rótulo fixo da cena pode estar
        defasado em relação ao que o usuário acabou de digitar num
        formulário.
        """
        if self._editor is None:
            return self.nome_barra

        rede = self._editor.rede
        barra = rede.barras.get(self.nome_barra)
        tensao = barra.kv_base if barra is not None else None

        incidentes = [r for r in rede.ramos.values()
                      if r.bus1 == self.nome_barra or r.bus2 == self.nome_barra]
        penduradas = [d for d in rede.derivacoes.values()
                      if d.bus1 == self.nome_barra]

        partes = [self.nome_barra]
        if tensao is not None:
            partes.append(f"{tensao} kV")

        # Singular e plural escritos por extenso: "1 ramos" num tooltip
        # parece descuido de quem escreveu o programa.
        partes.append(f"{len(incidentes)} ramo" + ("" if len(incidentes) == 1 else "s"))
        if penduradas:
            partes.append(f"{len(penduradas)} elemento"
                          + ("" if len(penduradas) == 1 else "s"))

        # Só faz sentido somar potência quando há carga: gerador,
        # capacitor e medidor não têm kW no mesmo sentido, e somá-los
        # daria um número sem significado físico.
        cargas = [d for d in penduradas if d.tipo == "Load"]
        if cargas:
            try:
                # Campo em branco fica de fora da soma em vez de entrar
                # como zero. Uma carga recém-criada, com kW ainda não
                # preenchido, não consome nada — dizer "carga 0 kW" numa
                # carga de verdade seria um dado falso, não um arredondamento.
                kw = _somar_parametro(cargas, "kw")
                kvar = _somar_parametro(cargas, "kvar")
            except (TypeError, ValueError):
                # Campo texto com conteúdo não numérico não pode quebrar
                # o hover: o resumo simplesmente omite a potência.
                kw = kvar = None
            if kw is not None:
                texto_carga = f"carga {_formatar_potencia(kw)} kW"
                # kW e kvar são campos independentes: um pode estar
                # preenchido e o outro não. Só entra na frase o que existe.
                if kvar is not None:
                    texto_carga += f" / {_formatar_potencia(kvar)} kvar"
                partes.append(texto_carga)

        return " · ".join(partes)

    def itemChange(self, change, value):
        # Chamado pelo Qt a cada mudança de estado do item. Aqui só
        # interessa a posição: sincroniza a coordenada de tela com o
        # dicionário que o redesenhar() consulta e, em seguida, refaz a
        # geometria do que está pendurado nesta barra. O modelo não é
        # tocado.
        #
        # A seleção também passa por aqui porque muda o que a elipse
        # pinta (contorno e anel tracejado) e o Qt não repinta o item
        # sozinho ao trocar esse estado — a área antiga ficaria com o
        # desenho de antes no fundo, o rastro.
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
                and self._editor is not None):
            self._editor._ao_mover_barra(self.nome_barra, self.pos())
            self._editor._atualizar_geometria_barra(self.nome_barra)
        return super().itemChange(change, value)


class _LinhaRamoItem(QGraphicsLineItem):
    """Segmento de ramo (ou ligação pontilhada) com destaque de seleção.

    A linha em si é geometria pura; o que esta classe acrescenta é o
    estado visual. Selecionada, ela engrossa e assume o azul
    institucional, com um traço claro por baixo que a separa do fundo —
    sem esse contorno, uma linha azul fina sobre a grade de pontos se
    confunde com a própria grade.

    A espessura de repouso é guardada na criação: o redesenho em zoom
    diferente gera outra espessura, e a restauração pós-seleção devolve
    exatamente a que o desenho pediu.
    """

    def __init__(self, linha, nome_ramo: str = "", editor=None):
        super().__init__(linha)
        self.nome_ramo = nome_ramo
        self._editor = editor
        # A caneta de repouso é a que o redesenho vai aplicar logo
        # abaixo, com setPen(). Capturá-la aqui, do construtor do
        # QGraphicsLineItem, pegaria a caneta padrão do Qt (1 px preta) e
        # a linha perderia cor e espessura ao ser repintada.
        self._caneta_repouso = QPen(Qt.GlobalColor.black, 1)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self._sob_cursor = False

    def setPen(self, caneta) -> None:
        """Guarda a caneta de repouso junto com a aplicação.

        Sobrescrever setPen é o que mantém a espessura correta: o
        desenho muda de espessura com a escala, e a versão destacada sai
        dela.
        """
        self._caneta_repouso = QPen(caneta)
        super().setPen(caneta)

    def _caneta_destaque(self) -> QPen:
        caneta = QPen(_qcolor(self._tema()["acento"]),
                      self._caneta_repouso.widthF() + 2.0)
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
        caneta.setStyle(self._caneta_repouso.style())
        return caneta

    def _tema(self) -> dict:
        """Tema do editor; claro quando o item não pertence a nenhum."""
        if self._editor is not None:
            return self._editor._tema
        return _tema_por_nome(TEMA_PADRAO)

    def _caneta_hover(self) -> QPen:
        caneta = QPen(self._caneta_repouso)
        caneta.setWidthF(self._caneta_repouso.widthF() + 1.0)
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
        return caneta

    def paint(self, painter, option, widget=None):
        selecionada = self.isSelected()
        if selecionada:
            # O halo claro é pintado primeiro e mais grosso; a linha
            # colorida por cima. É o mesmo recurso do halo da barra,
            # na mesma linguagem.
            halo = QPen(_qcolor(self._tema()["halo_ramo"]),
                        self._caneta_repouso.widthF() + 6.0)
            halo.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(halo)
            painter.drawLine(self.line())
            painter.setPen(self._caneta_destaque())
        elif self._sob_cursor:
            painter.setPen(self._caneta_hover())
        else:
            painter.setPen(self._caneta_repouso)
        painter.drawLine(self.line())

    def boundingRect(self):
        """Rect com folga para halo e espessura.

        A base do Qt já considera a grossura da caneta de repouso, mas
        não os 6 px do halo de seleção. Sem a folga, trocar a seleção
        deixaria o rastro do halo no fundo.
        """
        # QLineF não expõe boundingRect: o retângulo é montado a partir
        # das duas pontas, com a folga em todos os lados para cobrir
        # halo, espessura e o arredondamento do cap round.
        #
        # A folga é a soma exata do que sai do rect: metade da
        # espessura de repouso, os 3 px de cada lado que o halo
        # selecionado acrescenta (largura + 6, menos a de repouso, sobre
        # dois) e 1 px de arredondamento. Deixar por baixo deixa rastro
        # no fundo — medido: 2.986 px sobravam com folga de 4.
        folga = self._caneta_repouso.widthF() / 2.0 + 4.0 + 1.0
        linha = self.line()
        return QRectF(linha.p1(), linha.p2()).normalized().adjusted(
            -folga, -folga, folga, folga)

    def hoverEnterEvent(self, event):
        self._sob_cursor = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._sob_cursor = False
        self.update()
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        # Troca de seleção muda o que este item pinta (halo e cor da
        # caneta), mas o Qt não repinta sozinho: setSelected() avisa o
        # item e para por aí. Sem o update() aqui, a área antiga fica
        # com o desenho de antes no fundo — o rastro.
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        # A posição do press separa clique de pan. O release da vista é
        # quem decide; aqui só se guarda a origem.
        self._press_pos = event.screenPos() if hasattr(event, "screenPos") else None
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        inicio = getattr(self, "_press_pos", None)
        self._press_pos = None
        if inicio is not None:
            deslocamento = event.screenPos() - inicio
            if (abs(deslocamento.x()) > 5 or abs(deslocamento.y()) > 5):
                return
        if self._editor is not None and self.nome_ramo:
            self._editor._selecionar_no_mapa("ramo", self.nome_ramo)


class _DerivacaoItem(QGraphicsRectItem):
    """Caixa de uma derivação (carga, gerador, fonte, medidor...), móvel.

    A caixa existe para ser arrastada. Numa barra com oito elementos
    pendurados o leque se atravessa, e tirar dali o que está incomodando
    é mais rápido do que qualquer reorganização automática.

    A posição arrastada vira override: o redesenhar() passa a usar esse
    valor no lugar do ângulo calculado. Ela fica no espelho de tela e
    também no campo `posicao` da derivação, de onde é gravada no
    rede.json — o arranjo sobrevive ao fechamento do projeto.

    O retângulo base nasce em (0, 0), com o canto superior esquerdo na
    origem. Isso deixa o item ser posicionado pelo CENTRO, que é também
    o valor que o override grava. Guardar o centro, e não o canto, evita
    """

    # O rect chega pronto do redesenhar(), medido sobre o texto. A caixa
    # não escolhe o próprio tamanho: quem manda é o conteúdo, e o texto é
    # item filho dela — crescer aqui e encolher lá seria trabalho dobrado
    # para o mesmo resultado.
    def __init__(self, nome: str, barra: str, editor: "EditorRede",
                 largura: float, altura: float):
        super().__init__(-largura / 2, -altura / 2, largura, altura)
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
        # Eventos de hover só chegam a quem os pede. Sem esta linha o Qt
        # nunca chama hoverEnterEvent e o realce da borda não acende.
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sob_cursor = False
        # A cor de preenchimento chega depois, pelo setBrush() do
        # redesenhar(). O paint() lê o brush do item para não duplicar a
        # informação de cor em dois lugares.

    def boundingRect(self):
        """Rect do corpo com folga para sombra e borda de destaque.

        A sombra é pintada fora do retângulo (deslocada para baixo e
        para a direita) e o hover engrossa a borda para FORA do corpo.
        Sem a folga, os dois ficariam no fundo quando a caixa andasse —
        é o mesmo mecanismo que produzia os rastros nas barras.
        """
        folga_borda = 2.0
        return self.rect().adjusted(
            -folga_borda, -folga_borda,
            DESLOCAMENTO_SOMBRA + folga_borda, DESLOCAMENTO_SOMBRA + folga_borda)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        corpo = self.rect()
        cor = self.brush().color()
        if not cor.isValid():
            cor = _qcolor("gray")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._tema()["sombra"]))
        painter.drawRoundedRect(
            corpo.translated(DESLOCAMENTO_SOMBRA, DESLOCAMENTO_SOMBRA),
            RAIO_CAIXA, RAIO_CAIXA)

        painter.setBrush(QBrush(cor))
        if self._sob_cursor or self.isSelected():
            # Realce do hover: borda no acento institucional, 2 px. A
            # cor de estado da caixa continua no preenchimento, então o
            # tipo do elemento não se perde no destaque.
            pintor_pen = QPen(_qcolor(self._tema()["acento"]), 2)
        else:
            # Borda de 1 px num tom escurecido da própria cor: dá
            # definição ao contorno sem introduzir uma cor estranha à
            # paleta do elemento.
            pintor_pen = QPen(cor.darker(150), 1)
        painter.setPen(pintor_pen)
        painter.drawRoundedRect(corpo, RAIO_CAIXA, RAIO_CAIXA)

    def _tema(self) -> dict:
        """Tema do editor, com o claro como padrão fora dele.

        A borda no escuro não pode ser o preto de antes: a caixa
        ficaria sem contorno contra o fundo noturno. O tema escuro
        declara `caixa_borda` para exatamente esse caso.
        """
        if self._editor is not None:
            return self._editor._tema
        return _tema_por_nome(TEMA_PADRAO)

    def hoverEnterEvent(self, event):
        self._sob_cursor = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._sob_cursor = False
        self.update()
        super().hoverLeaveEvent(event)

    # ------------------------------ CLIQUE ----------------------------- #

    def mousePressEvent(self, event):
        # Mesma separação clique/arraste da barra e do rótulo: guarda a
        # posição de tela do press e compara no release. A distância é
        # medida em pixels de TELA, então o limiar vale igual em
        # qualquer zoom.
        self._press_pos = event.screenPos() if hasattr(event, "screenPos") else None
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        inicio = getattr(self, "_press_pos", None)
        self._press_pos = None
        if inicio is not None:
            deslocamento = event.screenPos() - inicio
            if abs(deslocamento.x()) > 5 or abs(deslocamento.y()) > 5:
                # Arrastou a caixa de lugar: o itemChange já cuidou da
                # posição, e o painel de propriedades não tem por que
                # mudar. O texto também fica como está — quem arrastou
                # quis mover o elemento, não esconder o nome dele.
                return
        # Clique curto na caixa alterna o texto dela. Isso não é atalho
        # para o usuário: a caixa é o elemento, e o texto é uma
        # propriedade visual dele. Ocultar e reexibir pelo próprio objeto
        # é mais direto que procurar um botão no painel.
        #
        # A caixa NÃO some junto — ela é a representação elétrica do
        # elemento no diagrama. Só o nome sai.
        if self._editor is not None:
            self._editor.alternar_rotulo("derivacao", self.nome_derivacao)
            # A seleção vem depois: alternar_rotulo redesenha a cena
            # inteira, e o painel de propriedades precisa montar o cartão
            # sobre os itens NOVOS, não sobre os que acabaram de morrer.
            # Também por isso o nome é guardado — depois do redesenho
            # `self` já não pertence à cena.
            self._editor._selecionar_no_mapa(
                "derivacao", self.nome_derivacao)

    def itemChange(self, change, value):
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
                and self._editor is not None):
            self._editor._ao_mover_derivacao(
                self.nome_derivacao, self.barra_ancora, self.pos())
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        """Duplo clique abre o formulário do elemento.

        O atalho existia na árvore do painel, mas não no mapa: quem
        estava olhando o diagrama precisava desviar o olho até a lista
        para editar. Como a caixa é a face visível do elemento, o
        caminho curto passa a valer aqui também.

        O evento não é repassado ao base. Com a caixa movível, o Qt usa o
        segundo press para iniciar outro arraste, e o item sairia do
        lugar às costas do usuário enquanto o formulário abre.
        """
        if self._editor is not None:
            self._editor._editar_derivacao(self.nome_derivacao)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class _RotuloItem(QGraphicsTextItem):
    """Rótulo com retângulo de fundo atrás (replica _desenhar_rotulo do Tk:
    `create_text` seguido de `create_rectangle` + `tag_lower`).

    O fundo é pintado no mesmo drawRect do texto e não como item
    separado: assim nunca descola do texto quando o rótulo se move.

    TRANSPARÊNCIA TÉCNICA: `fundo=False` desliga o retângulo. É o caso
    dos rótulos desenhados DENTRO das caixas de derivação, onde o fundo
    branco cobria o preenchimento colorido do elemento e o texto sumia
    no meio dele."""

    # Teto de largura do texto. Sem ele o rótulo cresce junto com o
    # conteúdo e o retângulo de fundo atravessa meia cena.
    LARGURA_MAXIMA = 170.0

    def __init__(self, texto: str, cor: str, tamanho_fonte: int = 8,
                 fundo: str = "white", editor=None, alvo=None,
                 tipo_alvo: str = ""):
        super().__init__(texto)
        # Origem do rótulo: quem é o dono (`alvo`, o nome do elemento) e
        # de que categoria ele é. Vazio no caso dos rótulos de texto
        # livre, que não respondem a clique.
        self.editor = editor
        self.alvo = alvo
        self.tipo_alvo = tipo_alvo
        self.setDefaultTextColor(_qcolor(cor))
        fonte = QFont()
        fonte.setPointSizeF(max(5.0, float(tamanho_fonte)))
        self.setFont(fonte)
        # O alinhamento central pertence ao documento, não à caixa:
        # `centralizar_rotulo` centra o retângulo no elemento, mas sem
        # esta linha o texto dentro dele continua encostado à esquerda.
        # Num rótulo de duas linhas de larguras diferentes ("Load" sobre
        # "CARGA_670a") o resultado é o texto parecendo escapar da
        # caixa. O Tk original fazia o mesmo via justify="center".
        #
        # A volta pelo setDefaultTextOption não é enfeite. Em PySide6
        # 6.12, defaultTextOption() devolve uma CÓPIA: mexer no objeto
        # devolvido (ou encadear `defaultTextOption().setAlignment(...)`)
        # modifica o descartável e o documento continua alinhado à
        # esquerda. Só atribuir de volta surte efeito.
        opcao_texto = self.document().defaultTextOption()
        opcao_texto.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.document().setDefaultTextOption(opcao_texto)
        # Capa de largura: rótulos curtos medem como antes; textos longos
        # quebram e a caixa de fundo deixa de crescer sem limite.
        # A medida vem de QFontMetricsF e não de document().idealWidth():
        # esta última só devolve a largura definitiva depois que o
        # documento passa por um layout, e no construtor ela ainda está
        # zerada — a capa disparava para rótulos de 15 caracteres e não
        # disparava para os de 25. QFontMetricsF mede com a fonte final,
        # na hora, sem depender de layout.
        medida = QFontMetricsF(fonte)
        mais_larga = max(
            (medida.horizontalAdvance(linha) for linha in texto.split("\n")),
            default=0.0)
        if mais_larga > self.LARGURA_MAXIMA:
            self.setTextWidth(self.LARGURA_MAXIMA)
        # `fundo=False` é o "sem retângulo" pedido pela caixa de
        # derivação, cujo preenchimento já faz esse papel. Qualquer nome
        # de cor liga o retângulo. Manter a distinção explícita evita que
        # um None vindo de fora desligue o fundo por acidente.
        self._cor_fundo = _qcolor(fundo) if fundo else None
        self._tamanho_fonte = tamanho_fonte
        self.setZValue(1.0)
        # Todo rótulo com dono pode ser arrastado sozinho: separar o
        # texto do elemento é o ajuste fino que resolve sobreposição sem
        # mexer na posição elétrica de nada. ItemSendsGeometryChanges é
        # obrigatório aqui pela mesma razão da barra: sem ele o Qt não
        # emite ItemPositionHasChanged e o novo lugar nunca chega ao
        # modelo.
        if alvo is not None:
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            self.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            self.setAcceptHoverEvents(True)

    # ------------------------------ CLIQUE ----------------------------- #

    def mousePressEvent(self, event):
        # Mesmo padrão da barra: guardar a posição do press separa
        # "clicou" de "arrastou" ao soltar. A posição é a de TELA, e não
        # a da cena, para que o limiar de 5 px valha em qualquer zoom.
        self._press_pos = event.screenPos() if hasattr(event, "screenPos") else None
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        inicio = getattr(self, "_press_pos", None)
        self._press_pos = None
        if inicio is not None:
            fim = event.screenPos() if hasattr(event, "screenPos") else inicio
            distancia = ((fim.x() - inicio.x()) ** 2
                         + (fim.y() - inicio.y()) ** 2) ** 0.5
            if distancia > _CanvasRede.LIMIAR_ARRASTE:
                # Arraste: o itemChange já cuidou de gravar o desvio.
                return
        if self.editor is not None and self.alvo is not None:
            self.editor.alternar_rotulo(self.tipo_alvo, self.alvo)

    def itemChange(self, change, value):
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
                and self.editor is not None and self.alvo is not None):
            self.editor._ao_mover_rotulo(self, self.pos())
        return super().itemChange(change, value)

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
    # Distância (pixels de tela) que separa um clique de um pan. Abaixo
    # disso o gesto foi um clique, e soltar o botão no fundo vazio deve
    # fechar o cartão de informações; acima, o usuário estava movendo a
    # vista e o cartão aberto não pode desaparecer no meio do gesto.
    # Cinco pixels é o mesmo limiar que o Qt adota internamente para
    # decidir quando um clique virou arraste.
    LIMIAR_ARRASTE = 5

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
        # Ponto onde o botão desceu e distância percorrida desde então.
        # O release consulta os dois para saber se houve arraste de fato.
        self._origem_pan = None
        self._pan_distancia = 0.0
        # Gancho preenchido pelo editor. O fundo vazio é o único lugar em
        # que a vista sabe que o clique não foi num elemento, então é ela
        # quem avisa que o cartão de informações deve fechar.
        self.ao_clicar_fundo = None
        # Ganchos da barra de ferramentas flutuante e da barra de
        # status. A vista conhece a própria escala e o próprio retângulo
        # visível; o editor conhece a contagem de elementos. Cada um
        # preenche o que sabe, sem que um passe a importar o outro.
        self.ao_mudar_escala = None
        self.ao_mudar_modo_janela = None
        self.ao_redimensionar = None
        # Fundo e grade saem daqui. A vista não escolhe tema — o editor
        # decide e deposita o dicionário corrente nesta referência, que
        # o drawBackground consulta a cada repintura. Trocar o tema é
        # trocar o dicionário e pedir update; nada é reconstruído.
        self.tema: dict = _tema_por_nome(TEMA_PADRAO)

        # Animação do zoom. A roda dispara muitos eventos por gesto, e
        # aplicar cada passo na hora produz o salto seco que dá a
        # sensação de "grudar". A animação interpola da escala corrente
        # até a alvo em 140 ms; pedidos que chegam durante a animação
        # atualizam o alvo e a animação é reiniciada a partir do valor
        # corrente, o que acumula os passos sem enfileirar.
        self._animacao_zoom = QVariantAnimation(self)
        self._animacao_zoom.setDuration(140)
        self._animacao_zoom.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animacao_zoom.valueChanged.connect(self._aplicar_escala_animada)
        self._escala_animada_de = 1.0
        self._escala_animada_para = 1.0
        self._ancora_animada = None

        self._barra_ferramentas = None
        self._barra_status = None

        # Intervalo entre o press e o release, em milissegundos, para o
        # clique simples não ser confundido com o início de um arraste.
        # O limiar de distância sozinho não basta: num clique com a mão
        # trêmula o cursor desliza 1-2 px, e mesmo assim o elemento tem
        # de ser selecionado.
        self.LIMIAR_CLIQUE_MS = 400
    # ------------------------------------------------------------------ #
    # Zoom
    # ------------------------------------------------------------------ #
    def _escala_atual(self) -> float:
        return self.transform().m11()

    def _aplicar_escala_absoluta(self, escala: float, ancora_tela=None) -> None:
        """Leva a vista para `escala` absoluta, mantendo a âncora parada.

        A animação de zoom trabalha com escala absoluta; fator relativo
        exigiria saber de onde se partiu, e o ponto de partida muda a
        cada quadro.

        `ancora_tela` é o ponto de TELA que não pode se mover — na roda
        do mouse, o cursor. Convertê-lo em coordenada de cena antes da
        mudança e compensar o deslocamento depois é o que mantém o zoom
        ancorado, em vez de o conteúdo fugir para um canto a cada passo.
        """
        escala = max(self.FATOR_MIN, min(self.FATOR_MAX, escala))
        atual = self._escala_atual()
        if atual <= 0 or abs(escala - atual) < 1e-9:
            return
        if ancora_tela is None:
            self.scale(escala / atual, escala / atual)
            self._avisar_escala()
            return
        # A âncora chega como QPointF (evento.position()) ou como QPoint
        # (chamada programática). Normalizar aqui evita que a diferença
        # entre os dois vire um AttributeError num caminho e funcione no
        # outro — o tipo do argumento não é responsabilidade do chamador.
        ancora_px = (ancora_tela.toPoint()
                     if hasattr(ancora_tela, "toPoint")
                     else QPointF(ancora_tela.x(), ancora_tela.y()).toPoint())
        ponto_cena = self.mapToScene(ancora_px)
        # A âncora automática do view é DESLIGADA de vez, não apenas
        # durante a conta. Com AnchorUnderMouse ligado, o Qt recentraliza
        # na posição do cursor do sistema em toda mudança de
        # transformação — e desfazia a compensação logo depois de ela ser
        # aplicada. Como este método já compensa explicitamente a partir
        # da âncora recebida, a automática é redundante e conflitante.
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.NoAnchor)
        self.scale(escala / atual, escala / atual)
        # A barra de rolagem do QGraphicsView anda um pixel de tela por
        # unidade de valor, em qualquer escala (medido: 10 unidades = 10
        # px tanto em 1.0 quanto em 2.0). O deslocamento a compensar é
        # portanto o próprio delta em pixels, sem conversão.
        diferenca = ancora_px - self.mapFromScene(ponto_cena)
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() - diferenca.x())
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - diferenca.y())
        self._avisar_escala()

    def _avisar_escala(self) -> None:
        """Informa a escala corrente a quem exibe o percentual."""
        if self.ao_mudar_escala is not None:
            self.ao_mudar_escala(self._escala_atual())

    def _aplicar_escala_animada(self, valor) -> None:
        """Quadro da animação: aplica a escala interpolada.

        Separado de _aplicar_escala_absoluta porque o sinal do Qt entrega
        um objeto (float embrulhado) e a âncora da animação está
        guardada na instância, não no sinal.
        """
        self._aplicar_escala_absoluta(float(valor), self._ancora_animada)

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
        self._avisar_escala()
        return True

    def _animar_zoom(self, escala_alvo: float, ancora_tela=None) -> None:
        """Interpola a escala até `escala_alvo` em 140 ms.

        Pedido que chega com a animação em curso não enfileira: o alvo é
        substituído e a animação recomeça da escala corrente. É o que faz
        uma rajada de eventos de roda virar um movimento contínuo, em vez
        de uma fila de saltos secos.
        """
        escala_alvo = max(self.FATOR_MIN, min(self.FATOR_MAX, escala_alvo))
        self._animacao_zoom.stop()
        self._escala_animada_de = self._escala_atual()
        self._escala_animada_para = escala_alvo
        self._ancora_animada = ancora_tela
        self._animacao_zoom.setStartValue(self._escala_animada_de)
        self._animacao_zoom.setEndValue(escala_alvo)
        self._animacao_zoom.start()

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
        # Enquadrar é um salto deliberado; uma animação de zoom em curso
        # o desfaria no quadro seguinte.
        self._animacao_zoom.stop()
        self.fitInView(area, Qt.AspectRatioMode.KeepAspectRatio)
        escala = self._escala_atual()
        if escala < self.FATOR_MIN or escala > self.FATOR_MAX:
            fator = (self.FATOR_MIN / escala if escala < self.FATOR_MIN
                     else self.FATOR_MAX / escala)
            self.scale(fator, fator)
        self._avisar_escala()

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
        # O enquadramento no retângulo é instantâneo por natureza: animar
        # até uma área arbitrária daria a impressão de zoom perdido. Uma
        # animação em curso é interrompida para não sobrescrever o
        # resultado no quadro seguinte.
        self._animacao_zoom.stop()
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
        self._avisar_escala()
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
            # A origem é preservada mesmo com o mouse parado: é o que
            # permite medir a distância total no release e separar o
            # clique do arraste.
            self._origem_pan = self._pan_ultimo
            self._pan_distancia = 0.0
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
            if self._origem_pan is not None:
                # Distância acumulada desde o press, e não o deslocamento
                # do último evento: um arraste lento chega ao release
                # com passos de um pixel e ainda assim é um arraste.
                self._pan_distancia = max(
                    self._pan_distancia,
                    ((atual.x() - self._origem_pan.x()) ** 2
                     + (atual.y() - self._origem_pan.y()) ** 2) ** 0.5)
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
            houve_arraste = self._pan_distancia > self.LIMIAR_ARRASTE
            self._origem_pan = None
            self._pan_distancia = 0.0
            self.unsetCursor()
            # Clique no fundo sem deslocamento: o gesto não foi pan, foi
            # um pedido para dispensar o que estiver aberto sobre a cena.
            if (not houve_arraste
                    and evento.button() == Qt.MouseButton.LeftButton
                    and self.ao_clicar_fundo is not None):
                self.ao_clicar_fundo()
            evento.accept()
            return

        super().mouseReleaseEvent(evento)

    def wheelEvent(self, evento):
        passo = evento.angleDelta().y()
        if passo == 0:
            super().wheelEvent(evento)
            return
        # O alvo é sempre calculado a partir da escala FINAL da animação
        # em curso, não da escala do quadro atual: com a animação em
        # andamento, ler _escala_atual() devolveria um valor intermediário
        # e vários giros seguidos não somariam o zoom que o usuário pediu.
        base = (self._escala_animada_para
                if self._animacao_zoom.state() == QVariantAnimation.State.Running
                else self._escala_atual())
        fator = self.PASSO_ZOOM if passo > 0 else 1.0 / self.PASSO_ZOOM
        self._animar_zoom(base * fator, evento.position())
        # O evento é consumido mesmo no limite da faixa. Deixar o Qt
        # rolar a vista aqui faria a roda ter um comportamento nas bordas
        # e outro no meio, o que confunde mais do que ajuda.
        evento.accept()

    def keyPressEvent(self, evento):
        if (evento.key() == Qt.Key.Key_Escape
                and self._zoom_janela_ativo):
            self.definir_modo_zoom_janela(False)
            evento.accept()
            return
        # Esc também dispensa o cartão de informações. A vista não
        # conhece o cartão — quem o mantém é o editor —, então o
        # fechamento é pedido pelo mesmo gancho usado no clique de fundo.
        # A ordem importa: com o modo de zoom de janela ligado o Esc já
        # foi consumido acima, e cancelar o modo tem precedência sobre
        # fechar um painel lateral.
        if evento.key() == Qt.Key.Key_Escape and self.ao_clicar_fundo is not None:
            self.ao_clicar_fundo()
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
        painter.setPen(QPen(_qcolor(self.tema["acento"]), 1.0,
                            Qt.PenStyle.DashLine))
        painter.setBrush(QBrush(_qcolor(self.tema["janela_zoom_fundo"])))
        painter.drawRect(self._retangulo_janela)
        painter.restore()

    def drawBackground(self, painter, retangulo):
        """Fundo do canvas: papel branco com grade de pontos.

        A grade é desenhada em coordenadas de CENA (`retangulo` já vem
        nelas), então os pontos ficam presos ao mundo: andam com o pan e
        abrem com o zoom, como papel milimetrado. Pintar em coordenadas
        de tela daria uma malha fixa, que se move por baixo do diagrama
        e destrói a referência de posição.
        """
        painter.fillRect(retangulo, QBrush(_qcolor(self.tema["fundo_canvas"])))
        if self._escala_atual() < ESCALA_MINIMA_GRADE:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        # Caneta sem largura: no Qt isso pinta sempre 1 pixel de tela,
        # independentemente do zoom. Com caneta de 1 unidade de cena, os
        # pontos sumiriam ao afastar e virariam borrões ao aproximar.
        painter.setPen(QPen(_qcolor(self.tema["cor_grade"]), 0))
        esquerda = math.floor(retangulo.left() / ESPACO_GRADE) * ESPACO_GRADE
        topo = math.floor(retangulo.top() / ESPACO_GRADE) * ESPACO_GRADE
        pontos = []
        x = esquerda
        while x <= retangulo.right():
            y = topo
            while y <= retangulo.bottom():
                # Um ponto de cada célula, no cruzamento: é o que dá a
                # textura de "editor", sem a densidade de uma malha
                # completa, que atrapalharia a leitura das linhas.
                pontos.append(QPointF(x, y))
                y += ESPACO_GRADE
            x += ESPACO_GRADE
        if pontos:
            painter.drawPoints(pontos)
        painter.restore()

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        # A pílula é posicionada em pixels de tela, então quem sabe onde
        # ela cabe é a própria vista. O editor é avisado porque é ele
        # quem monta os widgets flutuantes.
        if self.ao_redimensionar is not None:
            self.ao_redimensionar()
        if self.ao_mudar_escala is not None:
            self.ao_mudar_escala(self._escala_atual())


class _BotaoLegenda(QPushButton):
    """Botão de adição de elemento com uma marca da cor usada no mapa.

    O botão serve de legenda da paleta: ao lado do nome do elemento há um
    chip vertical com a mesma cor que aquele tipo recebe no diagrama, de
    modo que o usuário reconheça no mapa o que acabou de adicionar sem
    consultar o código nem a árvore.

    O chip é decorativo. Desenhá-lo no paintEvent, depois do
    super().paintEvent(), preserva todo o comportamento de botão — folha
    de estilo, hover, afundamento e marcação — sem reimplementar nenhum
    desses estados.
    """

    LARGURA_CHIP = 7
    ALTURA_CHIP = 14
    RECUO_DIREITA = 6

    def __init__(self, texto, cor_marca=None, parent=None):
        super().__init__(texto, parent)
        # Guardada como texto ("steelblue") e não como QColor: a paleta
        # CORES é a fonte única das cores do mapa, e converter na hora de
        # guardar obrigaria a reconverter para o tema escuro adiante.
        self._cor_marca = cor_marca

    def set_cor_marca(self, cor):
        self._cor_marca = cor
        self.update()

    def cor_marca(self):
        return self._cor_marca

    def paintEvent(self, evento):
        super().paintEvent(evento)
        if not self._cor_marca:
            return
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        largura = self.LARGURA_CHIP
        altura = self.ALTURA_CHIP
        x = self.width() - largura - self.RECUO_DIREITA
        y = (self.height() - altura) / 2
        retangulo = QRectF(x, y, largura, altura)
        # O contorno vem de _escurecer sobre a própria cor: sem ele, os
        # tons claros da paleta (goldenrod, orange) desaparecem no fundo
        # quase branco do botão e o chip deixa de identificar o elemento.
        pintor.setPen(QPen(QColor(_escurecer(self._cor_marca, 1.45)), 1))
        pintor.setBrush(QColor(self._cor_marca))
        pintor.drawRoundedRect(retangulo, 3, 3)
        pintor.end()


class EditorRede(QWidget):
    """Widget central do editor: painel de ferramentas, diagrama e lista.

    O estado de desenho vive em dicionários indexados por NOME do
    elemento (barra, ramo, derivação), refeitos a cada redesenhar(). É
    o preço de manter o layout automático: nada do que está na tela é
    fonte da verdade, o modelo `RedeEletrica` é.
    """

    def __init__(self, rede: RedeEletrica = None, projeto: Projeto = None,
                 tema_forcado: str = None):
        """Monta o editor.

        `tema_forcado` aceita "claro" ou "escuro" e existe para
        inspeção e teste; em uso normal fica em None e o tema vem do
        sistema operacional, lido uma vez aqui. A leitura única não é
        economia: a mudança ao vivo chega pelo sinal do Qt, que reaplica
        o tema já com o editor montado.
        """
        super().__init__()
        self.rede = rede or RedeEletrica()
        self.projeto = projeto
        self.orientacao = "vertical"
        # O tema é decidido ANTES de qualquer widget: a montagem já
        # pergunta as cores ao dicionário, e montar no claro para
        # repintar depois daria um piscar claro na abertura.
        if tema_forcado in TEMAS_DISPONIVEIS:
            self._modo_tema = tema_forcado
        else:
            self._modo_tema = "escuro" if _sistema_em_tema_escuro() else "claro"
        self._tema = _tema_por_nome(self._modo_tema)

        # Quem está selecionado no diagrama, na forma (categoria, nome)
        # — a mesma chave que a árvore usa. Só existe um por vez: a
        # seleção do mapa é uma pergunta ("de quem são estas
        # propriedades?") e múltiplas respostas não caberiam no painel.
        # Os itens de cena marcados como selecionados são guardados
        # junto para que a desmarcação não precise varrer a cena atrás
        # deles a cada clique.
        self._selecao_mapa: Optional[tuple] = None
        self._itens_selecionados: list = []
        # O cartão de propriedades é construído sob demanda: criá-lo no
        # layout custaria altura do painel mesmo quando o usuário nunca
        # seleciona nada.
        self._card_propriedades: Optional[QFrame] = None
        self._rotulo_props: Optional[QLabel] = None
        self._corpo_props: Optional[QLabel] = None
        self._acoes_props: Optional[QWidget] = None
        self._dica_selecao: Optional[QLabel] = None

        # Posições de tela da última renderização, já passadas pelo
        # auto-encaixe. Reconstruídas inteiras a cada redesenhar().
        self._posicoes: Dict[str, tuple] = {}
        self._escala: float = 1.0
        # Trava de reentrância: mudar a posição de um item dispara
        # itemChange, que chamaria de volta o editor no meio do próprio
        # redesenho. Com a trava, esse eco é ignorado.
        self._redesenhando = False

        # Posições que o usuário impôs às caixas de derivação, por nome.
        # Espelho em memória do campo `posicao` de cada derivação: o
        # modelo é a fonte da verdade, e o dicionário existe para o
        # arraste não precisar procurar no modelo a cada pixel.
        self._posicoes_derivacoes: Dict[str, tuple] = {}
        # O que precisa ser regeometrizado quando uma barra se desloca:
        # barra -> [(item_linha, qual extremidade se move, rótulo)].
        # Sem esse índice, arrastar uma barra deixaria as conexões para
        # trás até o próximo redesenho.
        self._dependencias_por_barra: Dict[str, list] = {}
        # Afastamento do rótulo em relação ao centro da própria barra,
        # por nome. Calculado no redesenho e reaplicado a cada passo do
        # arraste, para que o texto acompanhe a elipse mantendo a mesma
        # distância — inclusive quando a fonte do rótulo muda de largura
        # e o ponto de ancoragem deixa de ser o mesmo.
        self._offsets_rotulos_barras: Dict[str, tuple] = {}
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
        # Espelho do último comando global de rótulos ("mostrar todos" /
        # "ocultar todos"). A visibilidade que vale é a de cada elemento,
        # no modelo; este atributo só evita reler os três dicionários a
        # cada consulta.
        self.mostrar_rotulos = True
        self._rotulos_ramos: list = []
        self._rotulos_elementos: list = []

        # Cartão de informações fixado numa barra. Um por vez, por
        # decisão de desenho: dois painéis abertos em barras vizinhas
        # cobrem a própria topologia que se queria comparar. Guarda o
        # item e o nome da barra a que ele pertence.
        self._cartao_barra: Optional[_CartaoBarra] = None
        self._cartao_barra_nome: Optional[str] = None
        # O quadro da cena em que o cartão estava posicionado, para
        # recolocá-lo quando a janela mudar de tamanho.
        self._retangulo_cena_cartao = None

        # Gravação do layout em disco. Cada pixel de arraste altera o
        # modelo, mas escrever o rede.json a cada itemChange seria
        # desperdício: o arquivo só interessa com o arraste encerrado.
        # O timer de disparo único agrupa a rajada de movimentos numa
        # gravação só, meio segundo depois da última mudança.
        self._timer_salvar_layout = QTimer(self)
        self._timer_salvar_layout.setSingleShot(True)
        self._timer_salvar_layout.setInterval(500)
        self._timer_salvar_layout.timeout.connect(self._salvar_layout)

        self._montar_layout()
        self._carregar_projeto_automaticamente()
        # Aparência aplicada depois de os widgets existirem: o QSS dos
        # painéis só alcança o que já está na árvore, e o do canvas só
        # pinta cena que existe.
        self.aplicar_tema()
        # O cartão vive na cena, não na vista, mas é a vista quem sabe
        # distinguir clique de pan no fundo vazio. O gancho fecha o
        # buraco entre os dois sem que a vista precise conhecer o editor.
        self.view.ao_clicar_fundo = self._ao_clicar_fundo_mapa
        # Seguir a troca de tema do Windows sem fechar o programa. O
        # sinal existe no PySide6 atual; em versões que não o tenham, o
        # tema fica o da abertura — o que é uma limitação aceitável, não
        # um erro.
        try:
            from PySide6.QtGui import QGuiApplication
            dicas = QGuiApplication.styleHints()
            if dicas is not None and hasattr(dicas, "colorSchemeChanged"):
                dicas.colorSchemeChanged.connect(self._ao_mudar_esquema_sistema)
        except Exception:
            pass
        # Equivalente ao self.after(50, self.redesenhar) do Tk. O layout
        # só tem dimensão útil depois do primeiro ciclo de eventos; antes
        # disso o enquadramento seria calculado sobre uma área nula.
        QTimer.singleShot(0, self.redesenhar)

    def _ao_clicar_fundo_mapa(self) -> None:
        """Clique no fundo vazio: fecha o cartão e desfaz a seleção.

        Os dois gestos dizem a mesma coisa — "não quero mais olhar para
        este elemento" —, e separá-los deixaria o painel de propriedades
        mostrando algo que o usuário acabou de descartar no mapa.
        """
        self.fechar_cartao_barra()
        self.limpar_selecao_mapa()

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
        # O fundo do canvas é pintado pelo drawBackground da vista, que
        # desenha a grade de pontos. Um brush de cena aqui cobriria a
        # grade: o Qt pinta o brush da cena ANTES do drawBackground.
        self.cena.setBackgroundBrush(Qt.BrushStyle.NoBrush)
        self.view = _CanvasRede(self.cena)
        self.view.setRenderHint(self.view.renderHints().SmoothPixmapTransform, True)

        # ---------------- Painel de ferramentas (esquerda) ----------------
        painel_ferramentas = QFrame()
        painel_ferramentas.setObjectName("painelLateral")
        painel_ferramentas.setFrameShape(QFrame.Shape.NoFrame)
        painel_ferramentas.setFixedWidth(224)
        self.painel_ferramentas = painel_ferramentas

        coluna = QVBoxLayout(painel_ferramentas)
        coluna.setContentsMargins(10, 12, 10, 12)
        coluna.setSpacing(5)

        if self.projeto:
            label_projeto = QLabel(f"Projeto:\n{self.projeto.nome}")
            fonte = fonte_padrao(10)
            fonte.setBold(True)
            label_projeto.setFont(fonte)
            label_projeto.setWordWrap(True)
            # A cor definitiva fica com aplicar_tema(): o azul do tema
            # claro some no painel escuro.
            label_projeto.setObjectName("tituloProjeto")
            label_projeto.setStyleSheet(
                f"color: {self._tema['acento']};")
            coluna.addWidget(label_projeto)

        label_titulo = QLabel("Adicionar elemento")
        fonte_titulo = fonte_padrao(10)
        fonte_titulo.setBold(True)
        label_titulo.setFont(fonte_titulo)
        label_titulo.setObjectName("tituloPainel")
        coluna.addWidget(label_titulo)

        # Sem chip: a barra é desenhada em branco com contorno azulado, e
        # inventar uma cor só para o botão quebraria a função de legenda.
        coluna.addWidget(self._botao_painel("➕ Nova Barra", self._criar_barra))

        coluna.addWidget(self._label_secao("Ramos (2 barras)"))
        for texto, tipo in [("── Linha", "Line"), ("── Chave", "Switch"),
                            ("⧈ Transformador", "Transformer")]:
            coluna.addWidget(self._botao_painel(
                texto, lambda _checked=False, t=tipo: self._criar_ramo(t),
                cor_marca=CORES[tipo]))

        coluna.addWidget(self._label_secao("Conectados (1 barra)"))
        # Storage não tem botão próprio aqui: nasce pelo fluxo
        # "🔋 Sistema BESS", que é o único caminho que garante o
        # InvControl associado a ele.
        for texto, tipo in [("▣ Carga", "Load"), ("⚙ Gerador", "Generator"),
                            ("▭ Capacitor", "Capacitor"), ("☀ Fotovoltaico", "PVSystem"),
                            ("🌀 Reator", "Reactor"),
                            ("⚡ Fonte (Vsource)", "Vsource")]:
            coluna.addWidget(self._botao_painel(
                texto, lambda _checked=False, t=tipo: self._criar_derivacao(t),
                cor_marca=CORES[tipo]))

        # O medidor também fica fora do laço acima: não passa por
        # _criar_derivacao, porque o formulário dele não pede barra — a
        # âncora de desenho vem do elemento monitorado.
        coluna.addWidget(self._botao_painel("⏱ Medidor de energia",
                                            self._criar_medidor,
                                            cor_marca=CORES["EnergyMeter"]))

        coluna.addWidget(self._label_secao("Sistemas compostos"))
        # O BESS cria um Storage no modelo; a marca mostra "teal" porque é
        # essa a cor com que a caixa correspondente aparece no mapa.
        coluna.addWidget(self._botao_painel(
            "🔋 Sistema BESS", self._criar_sistema_bess,
            cor_marca=CORES["Storage"]))

        label_orientacao = QLabel("Orientação do layout")
        fonte_orientacao = fonte_padrao(10)
        fonte_orientacao.setBold(True)
        label_orientacao.setFont(fonte_orientacao)
        label_orientacao.setObjectName("tituloPainel")
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

        # Os controles de vista saíram do painel: eles agora moram numa
        # pílula flutuante sobre o canvas, que é onde a mão do usuário
        # está quando ele quer dar zoom. A montagem fica em
        # _montar_barra_ferramentas(), chamada depois do layout porque a
        # pílula é filha da VISTA e precisa dela já no lugar.

        coluna.addWidget(self._botao_painel(
            "▶ Simular no OpenDSS", self.simular, variante="primario"))

        coluna.addStretch(1)

        label_dica_vista = QLabel(
            "Roda do mouse: zoom\n"
            "Arrastar o fundo: mover a vista\n"
            "Botão do meio: mover em qualquer ponto")
        fonte_dica_vista = fonte_padrao(8)
        fonte_dica_vista.setItalic(True)
        label_dica_vista.setFont(fonte_dica_vista)
        label_dica_vista.setObjectName("dicaPainel")
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
        painel_lista.setObjectName("painelLista")
        painel_lista.setFrameShape(QFrame.Shape.NoFrame)
        painel_lista.setFixedWidth(290)
        self.painel_lista = painel_lista

        coluna_lista = QVBoxLayout(painel_lista)
        coluna_lista.setContentsMargins(10, 12, 10, 12)
        coluna_lista.setSpacing(5)

        # O cartão de propriedades fica no topo, acima da lista: é
        # resposta ao clique, e o olho já está subindo do diagrama. A
        # árvore vem depois, com peso, porque é ela que rola.
        coluna_lista.addWidget(self._montar_card_propriedades())

        label_lista = QLabel("Elementos da rede")
        fonte_lista = fonte_padrao(10)
        fonte_lista.setBold(True)
        label_lista.setFont(fonte_lista)
        label_lista.setObjectName("tituloPainel")
        coluna_lista.addWidget(label_lista)

        label_dica = QLabel("(duplo clique para editar,\ninclusive trocar o tipo)")
        fonte_dica = fonte_padrao(8)
        fonte_dica.setItalic(True)
        label_dica.setFont(fonte_dica)
        label_dica.setObjectName("dicaPainel")
        coluna_lista.addWidget(label_dica)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Nome", "Tipo", "Detalhes"])
        self.tree.setColumnWidth(0, 100)
        self.tree.setColumnWidth(1, 76)
        self.tree.setColumnWidth(2, 92)
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.setFont(fonte_padrao(9))
        self.tree.setStyleSheet(self._estilo(self.ESTILO_ARVORE))
        self.tree.itemDoubleClicked.connect(self._ao_dar_duplo_clique)
        coluna_lista.addWidget(self.tree, 1)

        coluna_lista.addWidget(self._botao_painel(
            "Excluir selecionado(s)", self._excluir_selecionado,
            variante="perigo"))

        dica_selecao = QLabel(
            "Clique num elemento para ver as propriedades; "
            "duplo clique para editar.")
        fonte_dica_selecao = fonte_padrao(8)
        fonte_dica_selecao.setItalic(True)
        dica_selecao.setFont(fonte_dica_selecao)
        dica_selecao.setObjectName("dicaPainel")
        dica_selecao.setWordWrap(True)
        dica_selecao.setFixedHeight(28)
        coluna_lista.addWidget(dica_selecao)

        layout_principal.addWidget(painel_lista)

        # A folha de estilo dos painéis entra depois de os widgets
        # existirem: o Qt resolve os seletores por objectName em tempo de
        # pintura, não na criação, mas aplicar no fim deixa a montagem
        # numa passada só.
        self.setStyleSheet(self._estilo(self.ESTILO_PAINEL))

        # Os widgets flutuantes dependem de a vista já pertencer ao
        # layout: o reposicionamento usa a geometria do viewport, que só
        # existe depois da primeira passada de layout.
        self._montar_widgets_flutuantes()

    # ------------------------------------------------------------------ #
    # Helpers de UI (estilo único, paleta institucional)
    # ------------------------------------------------------------------ #
    # Estilo das pílulas flutuantes. Fica em constante de módulo porque
    # a barra de ferramentas e a de status compartilham exatamente a
    # mesma linguagem: fundo branco quase opaco, borda fina de um tom
    # abaixo do branco e cantos totalmente arredondados. Duas folhas de
    # estilo separadas divergiriam no primeiro ajuste.
    #
    # As folhas abaixo são MOLDES: o texto tem as cores do tema entre
    # chaves e um método preenche. Escrever duas folhas por estilo
    # (uma clara, uma escura) duplicaria o layout inteiro em cada
    # variante e a primeira correção de espaçamento seria feita só de um
    # lado.
    ESTILO_PILULA = (
        "QFrame#pilula {{"
        " background-color: {pilula_fundo};"
        " border: 1px solid {pilula_borda};"
        " border-radius: 18px;"
        "}}"
    )
    ESTILO_BOTAO_PILULA = (
        "QToolButton {{"
        " border: none;"
        " border-radius: 14px;"
        " background: transparent;"
        " padding: 4px 8px;"
        " color: {pilula_texto};"
        "}}"
        "QToolButton:hover {{ background-color: {pilula_hover}; }}"
        "QToolButton:checked {{"
        " background-color: {acento};"
        " color: {acento_texto_sobre};"
        "}}"
        "QToolButton:pressed {{ background-color: {botao_pressionado}; }}"
    )

    # ------------------------------------------------------------------ #
    # Tema dos painéis laterais
    # ------------------------------------------------------------------ #
    # A folha fica nos widgets do editor (painéis, árvore, botões) e não
    # na aplicação: o resto do programa tem o próprio visual, e um QSS
    # global vazaria para janelas que ninguém pediu para pintar.
    #
    # As cores vêm da mesma família de cinzas usada no resto da
    # interface (#f8fafc de fundo, #e2e8f0 de contorno, #64748b para
    # texto secundário). São tons da borda azul do cinza: com o azul
    # institucional ao lado, funcionam como neutros e não como uma cor a
    # mais competindo com a rede desenhada.
    ESTILO_PAINEL = (
        "QFrame#painelLateral {{ background-color: {painel_fundo};"
        " border: none; border-right: 1px solid {painel_borda}; }}"
        "QFrame#painelLista {{ background-color: {painel_fundo};"
        " border: none; border-left: 1px solid {painel_borda}; }}"
        "QLabel#dicaPainel {{ color: {card_vazio}; }}"
        "QLabel#tituloSecao {{ color: {painel_secao}; font-weight: 600;"
        " letter-spacing: 1px; }}"
        "QLabel#tituloPainel {{ color: {painel_titulo}; font-weight: 600; }}"
        "QRadioButton {{ color: {botao_texto}; spacing: 5px; }}"
    )

    # Botão de ação do painel. Três variantes, declaradas como chave de
    # propriedade do Qt para o QSS escolher: "primario" (a ação que
    # interessa na tela: simular), "perigo" (exclusão) e neutro (o
    # padrão, que é a maioria).
    ESTILO_BOTAO_PAINEL = (
        "QPushButton {{"
        " background-color: {botao_fundo};"
        " border: 1px solid {botao_borda};"
        " border-radius: 8px;"
        " padding: 5px 8px;"
        " color: {botao_texto};"
        " text-align: left;"
        "}}"
        "QPushButton:hover {{ background-color: {botao_hover};"
        " border-color: {botao_borda}; }}"
        "QPushButton:pressed {{ background-color: {botao_pressionado}; }}"
        "QPushButton[acao=\"primario\"] {{"
        " background-color: {acento};"
        " border: 1px solid {acento};"
        " color: {acento_texto_sobre}; font-weight: 600; text-align: center;"
        "}}"
        "QPushButton[acao=\"primario\"]:hover {{"
        " background-color: {acento_hover}; }}"
        "QPushButton[acao=\"perigo\"] {{ color: {perigo};"
        " text-align: center; }}"
        "QPushButton[acao=\"perigo\"]:hover {{"
        " background-color: {perigo_fundo};"
        " border-color: {perigo_borda}; }}"
    )

    # Árvore de elementos. A seleção usa o azul institucional em versão
    # clara, com a barra lateral de acento que os editores atuais
    # desenham — a cor cheia no fundo escurece as três colunas de texto.
    ESTILO_ARVORE = (
        "QTreeWidget {{"
        " background-color: {arvore_fundo};"
        " border: 1px solid {arvore_borda};"
        " border-radius: 10px;"
        " padding: 2px;"
        " alternate-background-color: {arvore_alternada};"
        " outline: none;"
        "}}"
        "QTreeWidget::item {{ padding: 3px 2px; border-radius: 5px; }}"
        "QTreeWidget::item:hover {{ background-color: {arvore_hover}; }}"
        "QTreeWidget::item:selected {{"
        " background-color: {arvore_selecao};"
        " color: {arvore_selecao_texto}; }}"
        "QHeaderView::section {{"
        " background-color: {arvore_fundo}; border: none;"
        " border-bottom: 1px solid {arvore_borda};"
        " padding: 4px 2px; color: {arvore_cabecalho}; font-weight: 600; }}"
    )

    # Cartão de propriedades. Borda fina, canto de 10 px e fundo branco
    # contra o cinza do painel: é o mesmo recurso do cartão do diagrama,
    # aplicado ao widget — o objeto selecionado fica suspenso sobre a
    # superfície da lista.
    ESTILO_CARD_PROPS = (
        "QFrame#cardProps {{"
        " background-color: {card_fundo};"
        " border: 1px solid {card_borda};"
        " border-radius: 10px;"
        "}}"
    )
    ESTILO_CORPO_PROPS = "color: {card_corpo};"
    ESTILO_TITULO_CARD = "color: {card_titulo}; font-weight: 600;"
    ESTILO_TAG_CARD = (
        "color: {acento}; background-color: {card_tag_fundo};"
        " border-radius: 6px; padding: 1px 6px; font-weight: 600;"
    )
    ESTILO_VAZIO_CARD = "color: {card_vazio};"

    # ------------------------------------------------------------------ #
    def _estilo(self, molde: str) -> str:
        """Preenche um molde de folha de estilo com o tema corrente.

        Toda folha passa por aqui, e é por isso que não existe um
        "estilo claro" e um "estilo escuro" paralelos: um único texto,
        preenchido com um único dicionário.
        """
        return molde.format(**self._tema)

    def aplicar_tema(self) -> None:
        """Pinta o editor inteiro com o tema corrente.

        Chamado na montagem e a cada troca de tema do sistema. O que
        depende de QSS é reaplicado widget a widget — folha herdada não
        chega aos objetos que já receberam a própria. O que depende de
        pintura (fundo, grade, elementos) sai com um redesenho.
        """
        tema = self._tema
        # A vista consulta este dicionário a cada repintura do fundo.
        self.view.tema = tema
        self.setStyleSheet(self._estilo(self.ESTILO_PAINEL))
        # Os painéis laterais são frames nomeados no próprio QSS; os
        # botões carregam folha própria e precisam ser alcançados um a
        # um.
        for botao in self.findChildren(QPushButton):
            botao.setStyleSheet(self._estilo(self.ESTILO_BOTAO_PAINEL))
        if getattr(self, "tree", None) is not None:
            self.tree.setStyleSheet(self._estilo(self.ESTILO_ARVORE))
            # O cabeçalho da árvore herda a paleta do sistema, e no
            # escuro ela traria texto escuro sobre o cabeçalho escuro.
            paleta_cabecalho = self.tree.header().palette()
            paleta_cabecalho.setColor(
                paleta_cabecalho.ColorRole.WindowText,
                QColor(tema["arvore_cabecalho"]))
            self.tree.header().setPalette(paleta_cabecalho)

        # Widgets flutuantes. Eles existem só depois da primeira montagem;
        # a checagem cobre a chamada durante o __init__.
        for nome in ("_barra_ferramentas", "_barra_status"):
            pilula_widget = getattr(self, nome, None)
            if pilula_widget is not None:
                pilula_widget.setStyleSheet(self._estilo(self.ESTILO_PILULA))
                for botao in pilula_widget.findChildren(QToolButton):
                    botao.setStyleSheet(self._estilo(self.ESTILO_BOTAO_PILULA))
                for rotulo in pilula_widget.findChildren(QLabel):
                    rotulo.setStyleSheet(
                        f"color: {tema['pilula_texto']}; border: none;")
        if getattr(self, "botao_mostrar_todos", None) is not None:
            # Os dois botões de rótulos tinham ajuste próprio sobre a
            # folha base (um em negrito, o outro esmaecido); o ajuste
            # sobrevive ao tema.
            self.botao_mostrar_todos.setStyleSheet(
                self._estilo(self.ESTILO_BOTAO_PILULA)
                + "QToolButton { font-weight: 700; }")
            self.botao_ocultar_todos.setStyleSheet(
                self._estilo(self.ESTILO_BOTAO_PILULA)
                + f"QToolButton {{ color: {tema['card_vazio']}; }}")

        # Cartão de propriedades do painel.
        if getattr(self, "_card_propriedades", None) is not None:
            self._card_propriedades.setStyleSheet(
                self._estilo(self.ESTILO_CARD_PROPS))
        for atributo, molde in (
                ("_rotulo_props_titulo", self.ESTILO_TITULO_CARD),
                ("_rotulo_props_tag", self.ESTILO_TAG_CARD)):
            rotulo = getattr(self, atributo, None)
            if rotulo is not None:
                rotulo.setStyleSheet(self._estilo(molde))

        # O rótulo do projeto e as dicas eram pintados por cor fixa no
        # momento da criação (ver _montar_layout); sem repintura, o azul
        # institucional ficaria sobre o painel escuro.
        for rotulo in self.findChildren(QLabel):
            if rotulo.objectName() == "tituloProjeto":
                rotulo.setStyleSheet(f"color: {tema['acento']};")
            elif rotulo.objectName() == "dicaPainel":
                rotulo.setStyleSheet(f"color: {tema['card_vazio']};")

        # Os itens de cena guardam a cor no momento da criação; o
        # redesenho os refaz com a paleta do tema.
        if getattr(self, "cena", None) is not None:
            self.redesenhar()
        self.atualizar_card_propriedades()

    def _ao_mudar_esquema_sistema(self, *_args) -> None:
        """Reage à troca de tema claro/escuro no sistema operacional.

        Um editor aberto no fim do dia, quando o Windows entra no modo
        noturno, não deve ser o único programa da tela a continuar
        branco. Só reaplica quando o esquema efetivo mudou: o sinal
        também chega para "Unknown", e nesse caso não há o que fazer.
        """
        novo = "escuro" if _sistema_em_tema_escuro() else "claro"
        if novo == self._modo_tema:
            return
        self._modo_tema = novo
        self._tema = _tema_por_nome(novo)
        self.aplicar_tema()

    def _montar_widgets_flutuantes(self):
        """Cria a pílula de ferramentas (topo) e a de status (rodapé).

        Os dois são widgets filhos da VISTA, e não itens de cena: item de
        cena sofreria o zoom e o pan junto com o diagrama, e a barra de
        ferramentas iria embora na primeira rolagem.

        A escolha de tirar os controles do painel esquerdo tem um custo
        reconhecido — num diagrama denso a pílula cobre uma faixa de 44
        px no topo. Ela é centralizada e estreita, e a área de desenho
        útil continua bem maior do que o painel consumia.
        """
        pilula = QFrame(self.view)
        pilula.setObjectName("pilula")
        pilula.setStyleSheet(self._estilo(self.ESTILO_PILULA))
        linha = QHBoxLayout(pilula)
        linha.setContentsMargins(6, 4, 6, 4)
        linha.setSpacing(2)

        def _botao(texto, dica, callback, marcavel=False):
            botao = QToolButton(pilula)
            botao.setText(texto)
            botao.setToolTip(dica)
            botao.setCursor(Qt.CursorShape.PointingHandCursor)
            botao.setCheckable(marcavel)
            botao.setStyleSheet(self._estilo(self.ESTILO_BOTAO_PILULA))
            botao.setMinimumHeight(28)
            botao.setMinimumWidth(28)
            if marcavel:
                botao.toggled.connect(callback)
            else:
                botao.clicked.connect(lambda _c=False: callback())
            linha.addWidget(botao)
            return botao

        def _separador():
            risco = QFrame(pilula)
            risco.setFrameShape(QFrame.Shape.VLine)
            risco.setFrameShadow(QFrame.Shadow.Plain)
            risco.setStyleSheet(f"color: {self._tema['pilula_risco']};")
            risco.setFixedHeight(20)
            linha.addWidget(risco)

        self.botao_zoom_menos = _botao(
            "−", "Reduzir a vista", self.view.reduzir)
        self.label_zoom = QLabel("100%", pilula)
        self.label_zoom.setFont(fonte_padrao(9))
        self.label_zoom.setStyleSheet(
            f"color: {self._tema['pilula_texto']}; border: none;")
        self.label_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Largura fixa: sem ela o percentual pularia de 3 para 4 dígitos
        # e empurraria os botões vizinhos a cada passo de zoom.
        self.label_zoom.setFixedWidth(44)
        linha.addWidget(self.label_zoom)
        self.botao_zoom_mais = _botao(
            "＋", "Ampliar a vista", self.view.ampliar)

        _separador()
        self.botao_enquadrar = _botao(
            "⤢", "Reenquadra o diagrama inteiro na janela.\n"
                 "Não refaz o layout da rede.", self.view.enquadrar_tudo)
        self.botao_zoom_janela = _botao(
            "⧉", "Marque e arraste um retângulo sobre a área desejada.\n"
                 "Esc cancela o modo.",
            self.view.definir_modo_zoom_janela, marcavel=True)
        # A vista sai do modo por conta própria ao concluir o retângulo
        # ou no Esc. Sem o caminho de volta, o botão continuaria
        # marcado anunciando um modo que já não existe.
        self.view.zoom_janela_encerrado.connect(self._ao_encerrar_zoom_janela)

        _separador()
        self.botao_mostrar_todos = _botao(
            "Aa", "Exibe os nomes de todas as barras, ramos e elementos.",
            lambda: self._ao_alternar_rotulos(True))
        self.botao_ocultar_todos = _botao(
            "Aa", "Esconde todos os textos, para enxergar só a topologia.\n"
                  "As barras continuam clicáveis: clique numa elipse para ver\n"
                  "os dados dela no cartão, ou no texto dela para reexibi-lo.",
            lambda: self._ao_alternar_rotulos(False))
        # Mesmo rótulo, leitura diferente: o "Aa" cheio é mostrar, o
        # vazado é ocultar. Um ícone só repetido obrigaria a ler o
        # tooltip toda vez.
        self.botao_mostrar_todos.setStyleSheet(
            self._estilo(self.ESTILO_BOTAO_PILULA)
            + "QToolButton { font-weight: 700; }")
        self.botao_ocultar_todos.setStyleSheet(
            self._estilo(self.ESTILO_BOTAO_PILULA)
            + f"QToolButton {{ color: {self._tema['card_vazio']}; }}")

        sombra = QGraphicsDropShadowEffect(pilula)
        sombra.setBlurRadius(16)
        sombra.setColor(QColor(15, 23, 42, 30))
        sombra.setOffset(0, 2)
        pilula.setGraphicsEffect(sombra)
        pilula.adjustSize()
        self._barra_ferramentas = pilula

        # ---- Barra de status (rodapé, alinhada à esquerda) ---- #
        status = QFrame(self.view)
        status.setObjectName("pilula")
        status.setStyleSheet(self._estilo(self.ESTILO_PILULA))
        linha_status = QHBoxLayout(status)
        linha_status.setContentsMargins(10, 2, 10, 2)
        self.label_status = QLabel("", status)
        self.label_status.setFont(fonte_padrao(8))
        self.label_status.setStyleSheet("color: #64748b; border: none;")
        linha_status.addWidget(self.label_status)
        sombra_status = QGraphicsDropShadowEffect(status)
        sombra_status.setBlurRadius(12)
        sombra_status.setColor(QColor(15, 23, 42, 22))
        sombra_status.setOffset(0, 1)
        status.setGraphicsEffect(sombra_status)
        status.adjustSize()
        self._barra_status = status

        # A pílula de ferramentas é quem recebe o percentual; o mesmo
        # aviso alimenta o rodapé, porque os dois mostram a escala.
        self.view.ao_mudar_escala = self._ao_mudar_escala
        self.view.ao_redimensionar = self._posicionar_widgets_flutuantes
        self._posicionar_widgets_flutuantes()

    def _ao_mudar_escala(self, escala: float) -> None:
        """Atualiza o percentual exibido na pílula e no rodapé."""
        if hasattr(self, "label_zoom"):
            self.label_zoom.setText(f"{escala * 100:.0f}%")
        self._atualizar_status()

    def _atualizar_status(self):
        """Reescreve o texto da barra de status com os números da rede.

        A contagem vem do MODELO, não dos itens da cena: elemento sem
        barra válida não é desenhado, e anunciá-lo no rodapé daria um
        total que não corresponde ao que está à vista.
        """
        if getattr(self, "label_status", None) is None:
            return
        rede = getattr(self, "rede", None)
        if rede is None:
            self.label_status.setText("")
            return
        zoom = self.view._escala_atual() * 100 if hasattr(self, "view") else 100
        self.label_status.setText(
            f"{len(rede.barras)} barras  ·  {len(rede.ramos)} ramos  ·  "
            f"{len(rede.derivacoes)} elementos  ·  zoom {zoom:.0f}%")
        self._barra_status.adjustSize()
        self._posicionar_widgets_flutuantes()

    def _posicionar_widgets_flutuantes(self):
        """Centraliza a pílula no topo e ancora o status no rodapé.

        Chamado no resize da vista e em toda mudança de conteúdo. A
        margem de 12 px dá o afastamento das bordas; sem ela a pílula
        encostaria na barra de rolagem e a sombra sumiria sob o quadro.
        """
        if getattr(self, "_barra_ferramentas", None) is None:
            return
        margem = 12
        largura_pai = self.view.viewport().width()
        altura_pai = self.view.viewport().height()
        if largura_pai <= 0 or altura_pai <= 0:
            return
        # Numa vista estreita a pílula pode ser mais larga que o espaço
        # disponível. Centrar sem checar jogaria o excesso para fora dos
        # dois lados e o último botão ficaria inalcançável. O limite de
        # largura (e não uma largura fixa) deixa o layout interno se
        # comprimir e redistribuir os botões dentro do que cabe.
        disponivel = max(0, largura_pai - 2 * margem)
        self._barra_ferramentas.setMaximumWidth(disponivel)
        self._barra_ferramentas.adjustSize()
        self._barra_ferramentas.setMaximumWidth(16777215)
        largura_ferramentas = min(
            self._barra_ferramentas.sizeHint().width(), disponivel)
        x = max(margem, (largura_pai - largura_ferramentas) // 2)
        self._barra_ferramentas.move(x, margem)
        self._barra_ferramentas.raise_()
        if getattr(self, "_barra_status", None) is not None:
            altura_status = self._barra_status.sizeHint().height()
            # Mesmo limite de largura da pílula de ferramentas: o texto
            # de status numera a rede e cresce com ela, e numa vista
            # estreita ele sairia pela borda direita.
            self._barra_status.setMaximumWidth(
                max(0, largura_pai - 2 * margem))
            self._barra_status.adjustSize()
            self._barra_status.move(margem, altura_pai - altura_status - margem)
            self._barra_status.raise_()

    def _ao_encerrar_zoom_janela(self):
        # Desmarca o botão quando a vista encerra o modo por conta
        # própria. O toggled resultante chama de volta o método da vista,
        # já com o modo desligado — inofensivo, e é o caminho mais curto
        # para manter botão e estado sincronizados sem criar uma flag a
        # mais só para isso.
        if self.botao_zoom_janela.isChecked():
            self.botao_zoom_janela.setChecked(False)

    def _botao_painel(self, texto, callback, variante: str = None,
                      cor_marca: str = None) -> QPushButton:
        """Botão de ação dos painéis.

        `variante` escolhe a aparência pela propriedade dinâmica `acao`,
        que a folha de estilo do painel lê: "primario" pinta o botão de
        azul institucional e "perigo" pinta o texto de vermelho. O
        restante é o botão neutro.

        `cor_marca` transforma o botão em legenda: recebe a cor que o
        tipo de elemento tem no mapa e a repassa ao chip desenhado por
        _BotaoLegenda. Sem a cor, o botão é um QPushButton comum.

        A cor do texto acompanha cada variante na própria folha de
        estilo. Declarar só o fundo deixava o texto herdar a QPalette do
        sistema — branco no tema escuro do Windows — e sumir em cima
        dos fundos claros.
        """
        botao = _BotaoLegenda(texto, cor_marca) if cor_marca else QPushButton(texto)
        botao.setFont(fonte_padrao(10))
        botao.setMinimumHeight(28)
        botao.setCursor(Qt.CursorShape.PointingHandCursor)
        botao.setStyleSheet(self._estilo(self.ESTILO_BOTAO_PAINEL))
        if variante:
            botao.setProperty("acao", variante)
        botao.clicked.connect(lambda _checked=False: callback())
        return botao

    def _label_secao(self, texto: str) -> QLabel:
        """Título de seção do painel.

        Caixa alta discreta com espaçamento entre letras, em cinza
        azulado — o mesmo tratamento que os editores de diagrama usam
        para separar grupos de ferramentas sem desenhar uma linha.
        """
        label = QLabel(texto.upper())
        fonte = fonte_padrao(8)
        fonte.setBold(True)
        label.setFont(fonte)
        label.setObjectName("tituloSecao")
        # Margem superior: a seção respira em relação ao botão de cima.
        label.setStyleSheet("margin-top: 6px;")
        return label

    def _ao_mudar_orientacao(self, _marcado: bool = False):
        """Troca vertical/horizontal e refaz o layout do zero.

        A troca de orientação é o único gesto que devolve o diagrama ao
        arranjo automático, e por isso descarta as posições salvas. Manter
        um arranjo montado à mão debaixo de uma orientação diferente
        misturaria dois referenciais: as barras salvas ficariam onde estavam
        e as demais migrariam, com as linhas atravessando o desenho.

        Quem quiser guardar o arranjo não troca a orientação; enquadrar e
        dar zoom não mexem em posição nenhuma.
        """
        self.orientacao = "vertical" if self.radio_vertical.isChecked() else "horizontal"
        self._limpar_posicoes_salvas()
        self.redesenhar()

    def _limpar_posicoes_salvas(self):
        """Devolve barras e derivações ao layout automático.

        Zera as posições no modelo e no espelho de tela, e grava, para
        que o próximo carregamento já encontre o arranjo recalculado.
        """
        for barra in self.rede.barras.values():
            barra.posicao = None
        for derivacao in self.rede.derivacoes.values():
            derivacao.posicao = None
        self._posicoes_derivacoes.clear()
        if self.projeto:
            caminho = os.path.join(self.projeto.caminho_rede, "rede.json")
            try:
                self.rede.salvar_json(caminho)
            except OSError as erro:
                print(
                    f"Aviso: posições não limpas em {caminho}: {erro}",
                    file=sys.stderr)

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
    # Inspetor de propriedades (clique num elemento)
    # ------------------------------------------------------------------ #
    def _montar_card_propriedades(self) -> QWidget:
        """Monta o cartão fixo do topo do painel direito.

        O cartão nasce no estado vazio e é preenchido na seleção. A
        estrutura é fixa — título, linha de tipo, corpo e linha de ações
        — e só o conteúdo muda; reconstruir o widget a cada clique
        causaria o piscar que o usuário percebe como lentidão.
        """
        card = QFrame()
        card.setObjectName("cardProps")
        card.setStyleSheet(self._estilo(self.ESTILO_CARD_PROPS))

        dentro = QVBoxLayout(card)
        dentro.setContentsMargins(10, 8, 10, 8)
        dentro.setSpacing(4)

        linha_titulo = QHBoxLayout()
        linha_titulo.setSpacing(6)

        titulo = QLabel("Propriedades")
        fonte_titulo = fonte_padrao(10)
        fonte_titulo.setBold(True)
        titulo.setFont(fonte_titulo)
        titulo.setObjectName("tituloCard")
        titulo.setStyleSheet(self._estilo(self.ESTILO_TITULO_CARD))
        linha_titulo.addWidget(titulo)
        linha_titulo.addStretch(1)

        # A etiqueta do tipo só aparece na seleção; no estado vazio ela
        # fica escondida em vez de exibir um rótulo sem valor.
        etiqueta = QLabel("")
        fonte_etiqueta = fonte_padrao(8)
        fonte_etiqueta.setBold(True)
        etiqueta.setFont(fonte_etiqueta)
        etiqueta.setStyleSheet(self._estilo(self.ESTILO_TAG_CARD))
        etiqueta.setVisible(False)
        linha_titulo.addWidget(etiqueta)

        dentro.addLayout(linha_titulo)

        corpo = QLabel(TEXTO_SEM_SELECAO)
        corpo.setFont(fonte_padrao(9))
        corpo.setWordWrap(True)
        corpo.setTextFormat(Qt.TextFormat.RichText)
        corpo.setAlignment(Qt.AlignmentFlag.AlignTop)
        corpo.setStyleSheet(self._estilo(self.ESTILO_VAZIO_CARD))
        dentro.addWidget(corpo)

        # Ações ficam num widget à parte para sumirem juntas no estado
        # vazio — dois botões soltos logo abaixo de "selecione um
        # elemento" seriam um convite a clicar no que não existe.
        acoes = QWidget()
        linha_acoes = QHBoxLayout(acoes)
        linha_acoes.setContentsMargins(0, 2, 0, 0)
        linha_acoes.setSpacing(6)
        botao_editar = QPushButton("✏ Editar")
        botao_editar.setCursor(Qt.CursorShape.PointingHandCursor)
        botao_editar.setStyleSheet(self._estilo(self.ESTILO_BOTAO_PAINEL))
        botao_editar.clicked.connect(self._editar_selecionado_no_mapa)
        botao_excluir = QPushButton("🗑 Excluir")
        botao_excluir.setCursor(Qt.CursorShape.PointingHandCursor)
        botao_excluir.setProperty("acao", "perigo")
        botao_excluir.setStyleSheet(self._estilo(self.ESTILO_BOTAO_PAINEL))
        botao_excluir.clicked.connect(self._excluir_selecionado_no_mapa)
        linha_acoes.addWidget(botao_editar)
        linha_acoes.addWidget(botao_excluir)
        acoes.setVisible(False)
        dentro.addWidget(acoes)

        self._card_propriedades = card
        self._rotulo_props_titulo = titulo
        self._rotulo_props_tag = etiqueta
        self._corpo_props = corpo
        self._acoes_props = acoes
        return card

    def atualizar_card_propriedades(self) -> None:
        """Reescreve o cartão a partir da seleção corrente do diagrama.

        A leitura é feita no modelo vivo, e não nos itens de cena: o
        mesmo clique que seleciona pode ter acontecido logo depois de
        uma edição, e o resumo guardado no item já estaria velho.
        """
        if self._card_propriedades is None:
            return
        corpo = self._corpo_props
        tag = self._rotulo_props_tag
        selecao = self._selecao_mapa

        dados = self._descricao_selecao(selecao) if selecao else None
        if not dados:
            corpo.setText(f"<span style='color:#94a3b8'>{TEXTO_SEM_SELECAO}</span>")
            corpo.setStyleSheet(self._estilo(self.ESTILO_VAZIO_CARD))
            tag.setVisible(False)
            self._acoes_props.setVisible(False)
            return

        nome, tipo, linhas, editavel = dados
        corpo.setText("<br>".join(linhas))
        corpo.setStyleSheet(self._estilo(self.ESTILO_CORPO_PROPS))
        tag.setText(tipo)
        tag.setVisible(bool(tipo))
        # Grupo BESS não tem formulário próprio de propriedades — ele é
        # editado pelo fluxo composto, e o botão de excluir já cobre o
        # conjunto inteiro. Mostrar "Editar" ali abriria o formulário
        # errado.
        self._acoes_props.setVisible(editavel)

    def _descricao_selecao(self, selecao):
        """Devolve (nome, tipo, linhas_html, editavel) do que está selecionado.

        Devolve None quando o alvo não existe mais no modelo — caso
        frequente após uma exclusão em cascata, em que a seleção
        sobrevive ao que selecionou.
        """
        if not selecao:
            return None
        categoria, nome = selecao

        if categoria == "barra":
            barra = self.rede.barras.get(nome)
            if barra is None:
                return None
            return (nome, "Barra", self._linhas_props_barra(nome, barra), True)

        if categoria == "ramo":
            ramo = self.rede.ramos.get(nome)
            if ramo is None:
                return None
            return (nome, ramo.tipo, self._linhas_props_ramo(ramo), True)

        if categoria == "derivacao":
            der = self.rede.derivacoes.get(nome)
            if der is None:
                return None
            return (nome, der.tipo, self._linhas_props_derivacao(der), True)

        if categoria == "grupobess":
            membros = self.rede.obter_grupo(nome)
            if not membros:
                return None
            linhas = [f"<b>{len(membros)}</b> elemento(s) no conjunto"]
            for membro in sorted(membros.values(), key=lambda d: d.nome):
                linhas.append(f"• {membro.tipo} {membro.nome}")
            return (nome, "Sistema BESS", linhas, False)

        return None

    def _linhas_props_barra(self, nome: str, barra) -> List[str]:
        """Linhas do cartão para uma barra: tensão, ramos, elementos e carga."""
        linhas = [f"Tensão de base: <b>{barra.kv_base} kV</b>"]

        incidentes = [r for r in self.rede.ramos.values()
                      if r.bus1 == nome or r.bus2 == nome]
        rotulo_ramos = "ramo incidente" if len(incidentes) == 1 else "ramos incidentes"
        linhas.append(f"<b>{len(incidentes)}</b> {rotulo_ramos}")

        penduradas = sorted(
            (d for d in self.rede.derivacoes.values() if d.bus1 == nome),
            key=lambda d: d.nome)
        if penduradas:
            linhas.append("<br><b>Conectados</b>")
            for der in penduradas:
                potencia = _potencia_do_elemento(der)
                texto = f"• {der.tipo} {der.nome}"
                if potencia:
                    texto += f" — {potencia}"
                linhas.append(texto)

        cargas = [d for d in penduradas if d.tipo == "Load"]
        if cargas:
            try:
                kw = _somar_parametro(cargas, "kw")
                kvar = _somar_parametro(cargas, "kvar")
            except (TypeError, ValueError):
                kw = kvar = None
            if kw is not None:
                total = f"Carga total: <b>{_formatar_potencia(kw)} kW</b>"
                if kvar is not None:
                    total += f" / {_formatar_potencia(kvar)} kvar"
                linhas.append(total)

        medidores = [d for d in self.rede.derivacoes.values()
                     if d.tipo == "EnergyMeter" and d.bus1 == nome]
        for medidor in medidores:
            alvo = medidor.parametros.get("element", "?")
            linhas.append(f"Medidor <b>{medidor.nome}</b> em {alvo}")

        return linhas

    def _linhas_props_ramo(self, ramo) -> List[str]:
        """Linhas do cartão para um ramo, com os parâmetros que ele tiver."""
        linhas = [
            f"Liga <b>{ramo.bus1}</b> → <b>{ramo.bus2}</b>",
        ]
        if ramo.tipo == "Switch":
            estado = ramo.parametros.get("fechada", "yes")
            linhas.append("Estado inicial: "
                          + ("<b>fechada</b>" if str(estado).lower() == "yes"
                             else "<b>aberta</b>"))
        elif ramo.tipo == "Line":
            comprimento = ramo.parametros.get("length")
            unidade = ramo.parametros.get("units", "km")
            if comprimento not in (None, ""):
                linhas.append(f"Comprimento: <b>{comprimento} {unidade}</b>")
            linecode = ramo.parametros.get("linecode")
            if linecode not in (None, "", "Nenhuma"):
                linhas.append(f"Linecode: <b>{linecode}</b>")
            else:
                r1 = ramo.parametros.get("r1")
                x1 = ramo.parametros.get("x1")
                if r1 not in (None, "") or x1 not in (None, ""):
                    linhas.append(f"R1 = {r1 or '—'} / X1 = {x1 or '—'} Ω/{unidade}")
        elif ramo.tipo == "Transformer":
            kv1 = ramo.parametros.get("kv1", "—")
            kv2 = ramo.parametros.get("kv2", "—")
            linhas.append(f"Tensão: <b>{kv1} / {kv2} kV</b>")
            kva = ramo.parametros.get("kva")
            if kva not in (None, ""):
                linhas.append(f"Potência: <b>{kva} kVA</b>")
            xhl = ramo.parametros.get("xhl")
            if xhl not in (None, ""):
                linhas.append(f"%XHL: {xhl}")
            conexoes = (ramo.parametros.get("conn1"), ramo.parametros.get("conn2"))
            if all(conexoes):
                linhas.append(f"Conexões: {conexoes[0]} → {conexoes[1]}")
        fases = ramo.parametros.get("phases")
        if fases not in (None, ""):
            linhas.append(f"Fases: {fases}")
        return linhas

    def _linhas_props_derivacao(self, der) -> List[str]:
        """Linhas do cartão para um elemento conectado a uma barra."""
        linhas = []
        if der.bus1:
            linhas.append(f"Barra: <b>{der.bus1}</b>")
        else:
            linhas.append("Sem barra própria (controlador)")

        if der.tipo == "EnergyMeter":
            alvo = der.parametros.get("element", "—")
            terminal = der.parametros.get("terminal", "—")
            linhas.append(f"Mede: <b>{alvo}</b> (terminal {terminal})")
        else:
            potencia = _potencia_do_elemento(der)
            if potencia:
                linhas.append(f"Potência: <b>{potencia}</b>")

        # O resumo de potência acima já cobre o que o usuário mais
        # procura. Repetir kW/kvar linha a linha embaixo dele enche o
        # cartão com a mesma informação dita duas vezes — daí a lista de
        # chaves que ficam de fora.
        chaves_ja_usadas = {
            "element", "terminal",
            # cobertas pelo resumo de _potencia_do_elemento
            "kw", "kvar", "kva", "pmpp", "kwrated", "kwhrated", "kv",
        }
        for chave, rotulo, _tipo_campo, *_ in CAMPOS_DERIVACAO_PARAMS.get(der.tipo, []):
            if chave in chaves_ja_usadas:
                continue
            valor = der.parametros.get(chave)
            if valor in (None, ""):
                continue
            linhas.append(f"{rotulo}: <b>{valor}</b>")

        curvas = [c for c in ("daily", "duty", "yearly")
                  if der.parametros.get(c) not in (None, "", "Nenhuma")]
        if curvas:
            nomes = ", ".join(f"{c} ({der.parametros[c]})" for c in curvas)
            linhas.append(f"Curvas: <b>{nomes}</b>")

        if der.grupo:
            linhas.append(f"Sistema BESS: <b>{der.grupo}</b>")
        return linhas

    def _selecionar_no_mapa(self, categoria: str, nome: str) -> None:
        """Seleciona um elemento no diagrama e atualiza o cartão.

        Clicar no mesmo elemento outra vez desfaz a seleção — é o mesmo
        padrão do cartão flutuante da barra, e evita a sensação de que
        o painel "grudou" no último clique.
        """
        referencia = (categoria, nome)
        if self._selecao_mapa == referencia:
            self.limpar_selecao_mapa()
            return
        self._selecao_mapa = referencia
        self._marcar_itens_da_selecao()
        self.atualizar_card_propriedades()

    def limpar_selecao_mapa(self) -> None:
        """Desfaz a seleção do diagrama. Idempotente."""
        if self._selecao_mapa is None and not self._itens_selecionados:
            return
        self._selecao_mapa = None
        for item in self._itens_selecionados:
            try:
                item.setSelected(False)
            except RuntimeError:
                # Item já destruído pelo redesenhar. Não há o que
                # desmarcar, e o except evita derrubar o editor por
                # causa de um ponteiro morto.
                pass
        self._itens_selecionados = []
        self.atualizar_card_propriedades()

    def _marcar_itens_da_selecao(self) -> None:
        """Aplica o estado de seleção aos itens de cena correspondentes.

        A marcação é feita procurando os itens com a mesma identidade da
        seleção. A cena é pequena (dezenas de itens) e a busca só
        acontece no clique — indexar por identidade custaria mais
        memória do que economiza.
        """
        for item in self._itens_selecionados:
            try:
                item.setSelected(False)
            except RuntimeError:
                pass
        self._itens_selecionados = []
        if self._selecao_mapa is None:
            return
        categoria, nome = self._selecao_mapa

        for item in self.cena.items():
            if categoria == "barra" and isinstance(item, _BarraItem):
                if item.nome_barra == nome:
                    item.setSelected(True)
                    self._itens_selecionados.append(item)
            elif categoria == "derivacao" and isinstance(item, _DerivacaoItem):
                if item.nome_derivacao == nome:
                    item.setSelected(True)
                    self._itens_selecionados.append(item)
            elif categoria == "ramo" and isinstance(item, _LinhaRamoItem):
                if item.nome_ramo == nome:
                    item.setSelected(True)
                    self._itens_selecionados.append(item)

    def _editar_selecionado_no_mapa(self) -> None:
        """Abre o formulário do elemento selecionado — mesmo caminho do
        duplo clique na árvore, para não existirem duas regras de edição."""
        if self._selecao_mapa is None:
            return
        categoria, nome = self._selecao_mapa
        if categoria == "barra":
            self._editar_barra(nome)
        elif categoria == "ramo":
            self._editar_ramo(nome)
        elif categoria == "derivacao":
            der = self.rede.derivacoes.get(nome)
            if der and der.tipo == "InvControl":
                self._editar_invcontrol(nome)
            elif der and der.tipo == "EnergyMeter":
                self._editar_medidor(nome)
            else:
                self._editar_derivacao(nome)

    def _excluir_selecionado_no_mapa(self) -> None:
        """Exclui o elemento selecionado no mapa.

        Reaproveita _excluir_selecionado passando o item da árvore
        correspondente: a confirmação em cascata e o aviso de medidor
        órfão vivem lá, e duplicar essa lógica seria duplicar a chance
        de divergir.
        """
        selecao = self._selecao_mapa
        if selecao is None:
            return
        item_arvore = self._item_da_arvore(*selecao)
        if item_arvore is None:
            # Sem linha na árvore (grupo BESS com nome repetido, por
            # exemplo), a exclusão cai no caminho direto do modelo.
            categoria, nome = selecao
            if categoria == "ramo":
                self.rede.remover_ramo(nome)
            elif categoria == "derivacao":
                self.rede.remover_derivacao(nome)
            elif categoria == "grupobess":
                self.rede.remover_grupo(nome)
            elif categoria == "barra":
                self.rede.remover_barra(nome)
            self.limpar_selecao_mapa()
            self.redesenhar()
            return

        self.tree.clearSelection()
        item_arvore.setSelected(True)
        self._excluir_selecionado()
        # A exclusão reconstruiu a árvore e a cena; a seleção do mapa
        # aponta para algo que não existe mais.
        self.limpar_selecao_mapa()

    def _item_da_arvore(self, categoria: str, nome: str):
        """Localiza a linha da árvore que representa (categoria, nome)."""
        pilha = [self.tree.topLevelItem(i)
                 for i in range(self.tree.topLevelItemCount())]
        while pilha:
            item = pilha.pop()
            if item is None:
                continue
            if item.data(0, Qt.ItemDataRole.UserRole) == (categoria, nome):
                return item
            pilha.extend(item.child(i) for i in range(item.childCount()))
        return None

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

        # A lista é reconstruída ao fim de toda edição, então este é o
        # ponto em que o cartão aberto fica sabendo que a rede mudou.
        # Atualizar só no redesenhar() deixaria o painel mostrando a
        # carga anterior até o próximo relayout.
        self._atualizar_cartao_barra()
        # O cartão de propriedades lê o modelo vivo, e a lista é
        # remontada em toda edição — daí ser este o ponto certo para
        # reler. Sem isso, editar a carga pelo formulário deixaria o
        # painel exibindo a potência antiga até o próximo clique.
        self.atualizar_card_propriedades()

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
                         fundo: str = None, alvo=None, tipo_alvo: str = "",
                         desvio=None):
        """Desenha um rótulo com (x, y) no centro do texto e devolve o item.

        `alvo` identifica o elemento a que o rótulo pertence e
        `tipo_alvo` sua categoria ("barra", "ramo" ou "derivacao"). Com
        os dois preenchidos, o rótulo vira clicável — o clique esconde e
        mostra o texto — e arrastável. `desvio` aplica o ajuste que o
        usuário já tinha imposto a este texto.
        """
        # O fundo do rótulo não é escolha do item: é a superfície onde
        # ele está pousado. Deixar o tema decidir é o que mantém a caixa
        # do texto legível quando o canvas muda de cor.
        if fundo is None:
            fundo = self._tema["fundo_canvas"]
        rotulo = _RotuloItem(texto, cor, tamanho_fonte, fundo,
                             editor=self, alvo=alvo, tipo_alvo=tipo_alvo)
        # O create_text do Tk recebia (x, y) como CENTRO do texto, com
        # justify="center". QGraphicsTextItem se posiciona pelo canto
        # superior esquerdo — daí o recuo de meia largura e meia altura.
        _posicionar_rotulo_em(rotulo, x, y, desvio)
        rotulo.setZValue(3.0)
        self.cena.addItem(rotulo)
        return rotulo

    def _agendar_salvar_layout(self):
        """Marca o layout como alterado e programa a gravação.

        Chamado a cada movimento de barra ou de caixa. Só arma o timer;
        quem escreve no disco é o _salvar_layout, quando a rajada de
        arraste se aquieta.

        Sem projeto aberto não há onde gravar, e o ajuste segue o
        comportamento de antes: vale até fechar o editor.
        """
        if not self.projeto:
            return
        self._timer_salvar_layout.start()

    def _salvar_layout(self):
        """Grava o rede.json com as posições do diagrama.

        A falha de escrita não interrompe o trabalho: o arranjo em tela
        continua válido e o aviso vai para o stderr. Um diálogo modal a
        cada arraste fracassado seria insuportável.
        """
        if not self.projeto:
            return
        caminho = os.path.join(self.projeto.caminho_rede, "rede.json")
        try:
            self.rede.salvar_json(caminho)
        except OSError as erro:
            # Sem diálogo: uma caixa modal a cada arraste fracassado
            # travaria o trabalho. O aviso vai para o stderr e o arranjo
            # em tela segue válido, à espera de um "Salvar" manual.
            print(
                f"Aviso: layout não gravado em {caminho}: {erro}",
                file=sys.stderr)

    def _ao_mover_barra(self, nome, ponto):
        """Sincroniza a posição arrastada com o dicionário de tela e com o
        modelo (ver _BarraItem.itemChange).

        O dicionário alimenta o desenho imediato. O modelo, somado à
        gravação em disco, é o que faz o arranjo sobreviver ao fechamento
        do projeto. A coordenada guardada é a de cena, a mesma que o
        redesenhar() entrega ao setPos das barras.
        """
        if self._redesenhando:
            return
        if nome not in self._posicoes:
            return
        self._posicoes[nome] = (ponto.x(), ponto.y())
        barra = self.rede.barras.get(nome)
        if barra is not None:
            barra.posicao = [ponto.x(), ponto.y()]
            self._agendar_salvar_layout()

    def _ao_mover_derivacao(self, nome, barra, ponto):
        """Grava a posição imposta à caixa e regeometriza só o que depende
        dela: a linha pontilhada. O resto da cena fica parado.

        Diferente do arraste de barra, não há nada pendurado na caixa: a
        ligação termina nela. Por isso basta mexer na linha, sem
        propagar nada adiante.

        O rótulo não aparece mais aqui. Desde que virou item FILHO da
        caixa, ele se desloca com ela pelo próprio Qt, e reposicioná-lo à
        mão seria trabalho redundante — pior, brigaria com a posição que
        o pai acabou de dar.
        """
        if self._redesenhando:
            return
        self._posicoes_derivacoes[nome] = (ponto.x(), ponto.y())
        self._posicoes[nome] = (ponto.x(), ponto.y())
        derivacao = self.rede.derivacoes.get(nome)
        if derivacao is not None:
            derivacao.posicao = [ponto.x(), ponto.y()]
            self._agendar_salvar_layout()

        ligacao = self._ligacoes_derivacoes.get(nome)
        if ligacao is not None:
            item_ligacao, ancora = ligacao
            origem = self._posicoes.get(ancora)
            if origem is not None:
                # A ponta que toca a caixa para na borda dela, como no
                # redesenho: o arraste não pode fazer a linha enterrar-se
                # no preenchimento que a criação deixa de fora.
                meia_largura, meia_altura = self._meia_caixa(nome)
                fim_x, fim_y = _ponto_na_borda_da_caixa(
                    origem, (ponto.x(), ponto.y()), meia_largura, meia_altura)
                _reposicionar_segmento(item_ligacao, (fim_x, fim_y),
                                       mover_fim=True)

    def _meia_caixa(self, nome):
        """Meia largura e meia altura da caixa desenhada para `nome`.

        Lê do item vivo, e não recalcula pelo texto: durante o arraste a
        caixa é a mesma instância, e reler o modelo custaria uma consulta
        por passo de mouse para chegar ao mesmo número.
        """
        rotulo = self._rotulos_derivacoes.get(nome)
        if rotulo is not None and rotulo.parentItem() is not None:
            rect = rotulo.parentItem().rect()
            return rect.width() / 2, rect.height() / 2
        return 0.0, 0.0

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
            if item is None:
                # Esta entrada agrupa os satélites da barra: o rótulo do
                # nome e, quando aberto, o cartão de informações. Não há
                # segmento a reposicionar — cada um se recoloca segundo
                # a própria regra.
                if isinstance(rotulo, _CartaoBarra):
                    # O cartão recalcula a própria posição a partir de
                    # _posicoes, que itemChange acaba de atualizar.
                    self._reposicionar_cartao_barra()
                    continue
                # Rótulo do nome: o afastamento foi medido no redesenho,
                # então aqui basta somá-lo ao centro atual — e a conta
                # vale em qualquer zoom, porque ambos os lados estão nas
                # mesmas coordenadas de cena.
                offset = self._offsets_rotulos_barras.get(nome)
                if rotulo is not None and offset is not None:
                    rotulo.setPos(pos[0] + offset[0], pos[1] + offset[1])
                continue
            _reposicionar_segmento(item, pos, mover_fim)
            if rotulo is not None:
                # O rótulo do ramo mora no ponto médio recuado na
                # perpendicular, e o recuo é refeito pela mesma fórmula do
                # redesenhar(). Duas fórmulas diferentes fariam o texto
                # pular de lado no instante em que o mouse fosse solto.
                mx, my = _ponto_medio_deslocado(item, DESLOCAMENTO_ROTULO_RAMO)
                # O desvio do usuário entra aqui também: sem isso o texto
                # voltaria ao lugar automático no primeiro pixel de
                # arraste e saltaria de volta ao soltar.
                desvio = self._desvio_do_ramo(rotulo.alvo)
                _posicionar_rotulo_em(rotulo, mx, my, desvio)

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
            # barra (a inicial). A que toca a caixa fica onde está, no
            # contorno do rect — e com a caixa maior, essa ponta precisa
            # ser recalculada no mesmo instante, ou a linha voltaria a
            # enterrar-se alguns pixels no preenchimento a cada arraste de
            # barra.
            meia_largura, meia_altura = self._meia_caixa(der_nome)
            fim_x, fim_y = _ponto_na_borda_da_caixa(
                pos, destino, meia_largura, meia_altura)
            _reposicionar_segmento(item, (fim_x, fim_y), mover_fim=True)

    def _desvio_do_ramo(self, nome):
        """Desvio de rótulo gravado no ramo `nome`, ou None.

        Existe para poupar o _atualizar_geometria_barra de carregar o
        modelo a cada passo do arraste: lá se conhece o item, não o
        registrador do ramo.
        """
        ramo = self.rede.ramos.get(nome) if nome is not None else None
        return ramo.rotulo_posicao if ramo is not None else None

    def _ao_alternar_rotulos(self, marcado: bool):
        """Esconde ou mostra TODOS os rótulos de uma vez.

        Alterna a visibilidade dos itens que já existem, sem redesenhar.
        A cena continua montada, o zoom e a rolagem ficam onde estavam, e
        um comando de visibilidade não pode custar um relayout inteiro do
        diagrama. Efeito colateral, e desejado: as posições impostas às
        caixas continuam valendo.

        O estado vai para o modelo de cada elemento. Um "ocultar todos"
        que valesse só até fechar a janela faria o usuário repetir o
        trabalho a cada abertura do projeto.
        """
        visivel = bool(marcado)
        self.mostrar_rotulos = visivel
        for barra in self.rede.barras.values():
            barra.rotulo_visivel = visivel
        for ramo in self.rede.ramos.values():
            ramo.rotulo_visivel = visivel
        for der in self.rede.derivacoes.values():
            der.rotulo_visivel = visivel
        self._agendar_salvar_layout()
        self.redesenhar()

    def alternar_rotulo(self, tipo_alvo: str, nome: str) -> None:
        """Inverte a visibilidade do rótulo de UM elemento e redesenha.

        É o que o clique no próprio texto faz. Redesenhar em vez de
        esconder o item na mão custa um relayout, mas garante um só
        caminho de desenho: o item que volta a aparecer nasce na posição
        correta, com o desvio salvo aplicado, em vez de reaparecer onde
        foi escondido.
        """
        if tipo_alvo == "barra":
            alvo = self.rede.barras.get(nome)
        elif tipo_alvo == "ramo":
            alvo = self.rede.ramos.get(nome)
        elif tipo_alvo == "derivacao":
            alvo = self.rede.derivacoes.get(nome)
        else:
            return
        if alvo is None:
            return
        alvo.rotulo_visivel = not alvo.rotulo_visivel
        self._agendar_salvar_layout()
        self.redesenhar()

    def _ao_mover_rotulo(self, rotulo, ponto) -> None:
        """Converte a posição arrastada do rótulo em desvio e grava.

        O que fica guardado é a distância até o lugar automático
        (o centro do elemento), nunca a coordenada de tela. Assim o texto
        continua acompanhando o elemento quando ele se move e mantém o
        ajuste quando o layout automático é recalculado — guardar a
        coordenada absoluta deixaria o rótulo plantado no desenho antigo
        no primeiro redesenho.
        """
        if self._redesenhando or rotulo.alvo is None:
            return
        # Rótulo de derivação não grava desvio: ele é filho da caixa e não
        # pode ser arrastado. Se algum caminho antigo chamar isto para uma
        # derivação, sai por aqui em vez de gravar uma coordenada que
        # ninguém lê (o campo rotulo_posicao continua no modelo por
        # compatibilidade com as redes já salvas).
        if rotulo.tipo_alvo == "derivacao":
            return
        alvo = None
        if rotulo.tipo_alvo == "barra":
            alvo = self.rede.barras.get(rotulo.alvo)
        elif rotulo.tipo_alvo == "ramo":
            alvo = self.rede.ramos.get(rotulo.alvo)
        if alvo is None:
            return

        base = self._base_do_rotulo(rotulo.tipo_alvo, rotulo.alvo)
        if base is None:
            return
        # O ponto guardado é o canto superior esquerdo do item; o centro
        # do texto fica meia caixa adiante. Trabalhar com o centro é o
        # que mantém o desvio independente do tamanho do texto.
        rect = rotulo.boundingRect()
        centro_texto = (ponto.x() + rect.width() / 2,
                        ponto.y() + rect.height() / 2)
        alvo.rotulo_posicao = [centro_texto[0] - base[0],
                               centro_texto[1] - base[1]]
        self._agendar_salvar_layout()

    def _base_do_rotulo(self, tipo_alvo: str, nome: str):
        """Ponto de referência do desvio do rótulo de um elemento.

        É o lugar em que o texto nasceria sozinho, e não o centro do
        elemento: o rótulo da barra paira 18 px acima da elipse, o do
        ramo fica no meio da linha recuado na perpendicular e o da caixa
        coincide com o centro dela. Gravar e aplicar o desvio contra a
        MESMA base é o que faz o texto voltar exatamente ao lugar
        escolhido depois de fechar e reabrir o projeto.
        """
        if tipo_alvo == "barra":
            pos = self._posicoes.get(nome)
            if pos is None:
                return None
            return (pos[0], pos[1] - DESLOCAMENTO_ROTULO_BARRA)
        if tipo_alvo == "ramo":
            ramo = self.rede.ramos.get(nome)
            if ramo is None:
                return None
            p1, p2 = self._posicoes.get(ramo.bus1), self._posicoes.get(ramo.bus2)
            if p1 is None or p2 is None:
                return None
            # Mesma fórmula do _ponto_medio_deslocado, aplicada aos
            # centros das barras: o item de linha pode ter sido
            # reposicionado no arraste e serviria de referência errada.
            mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            comprimento = math.hypot(dx, dy)
            if comprimento < 1e-9:
                return (mx, my)
            return (mx - dy / comprimento * DESLOCAMENTO_ROTULO_RAMO,
                    my + dx / comprimento * DESLOCAMENTO_ROTULO_RAMO)
        # Derivação: o texto nasce no centro da própria caixa, e é ele
        # que serve de referência.
        return self._posicoes.get(nome)

    # ------------------------------------------------------------------ #
    # Cartão de informações da barra
    # ------------------------------------------------------------------ #
    def _cartao_barras(self):
        """(cartão, lista de dependências da barra) do cartão aberto.

        Devolve (None, None) quando não há cartão. A lista de
        dependências é devolvida junto porque o cartão precisa entrar
        nela para acompanhar o arraste, e sair dela ao fechar — misturar
        os dois usos num método só evita divergência entre os dois.
        """
        return self._cartao_barra, self._cartao_barra_nome

    def alternar_cartao_barra(self, nome_barra: str) -> None:
        """Abre o cartão da barra `nome`, ou fecha se for a mesma barra.

        Este é o único ponto de entrada do toggle: clique na barra,
        clique em outra barra e reabertura depois de fechar passam todos
        por aqui. A política de "um cartão por vez" sai de graça —
        abrir numa barra fecha a anterior antes.
        """
        if self._cartao_barra is not None and self._cartao_barra_nome == nome_barra:
            self.fechar_cartao_barra()
            return
        self.fechar_cartao_barra()
        self.abrir_cartao_barra(nome_barra)

    def abrir_cartao_barra(self, nome_barra: str) -> None:
        """Monta o cartão da barra e o prende ao lado dela na cena."""
        cartao = _CartaoBarra(nome_barra, tema=self._tema)
        self.cena.addItem(cartao)
        self._cartao_barra = cartao
        self._cartao_barra_nome = nome_barra
        self._atualizar_cartao_barra()
        # A entrada usada é a mesma dos rótulos (item=None): o cartão é
        # tratado como um satélite da barra e reposicionado pela mesma
        # rotina que já leva rótulo e conexões junto no arraste.
        self._dependencias_por_barra.setdefault(nome_barra, []).append(
            (None, False, cartao))
        self._reposicionar_cartao_barra()

    def fechar_cartao_barra(self) -> None:
        """Remove o cartão aberto, se houver. Idempotente.

        Idempotência importa: o fechamento é disparado pelo clique na
        barra, pelo clique no fundo, pelo Esc e pelo redesenho. Nenhum
        desses caminhos pode depender de o cartão existir.
        """
        cartao = self._cartao_barra
        nome = self._cartao_barra_nome
        self._cartao_barra = None
        self._cartao_barra_nome = None
        if cartao is None:
            return
        if nome is not None:
            dependencias = self._dependencias_por_barra.get(nome)
            if dependencias:
                # Filtro por identidade, e não por igualdade: o item não
                # define __eq__, mas ser explícito deixa claro que a
                # remoção é daquele objeto e de nenhum outro.
                self._dependencias_por_barra[nome] = [
                    d for d in dependencias if d[2] is not cartao]
        if cartao.scene() is self.cena:
            self.cena.removeItem(cartao)

    def _atualizar_cartao_barra(self) -> None:
        """Reescreve o conteúdo do cartão com o estado atual do modelo.

        Chamado quando o cartão abre e quando a rede muda por baixo dele.
        Ler a rede viva, e não um resumo guardado na abertura, é o que
        impede o painel de exibir uma carga que o usuário acabou de
        editar no formulário.
        """
        cartao = self._cartao_barra
        if cartao is None:
            return
        nome = self._cartao_barra_nome
        barra = self.rede.barras.get(nome)
        if barra is None:
            # A barra sumiu (exclusão ou rede trocada). O cartão não tem
            # a que se ancorar, então ele sai de cena.
            self.fechar_cartao_barra()
            return

        incidentes = [r for r in self.rede.ramos.values()
                      if r.bus1 == nome or r.bus2 == nome]
        penduradas = [d for d in self.rede.derivacoes.values()
                      if d.bus1 == nome]

        titulo = f"{nome} · {barra.kv_base} kV"
        linhas = []

        # "ramo" é masculino: o particípio vai no masculino, no singular
        # e no plural. Uma frase de painel com erro de concordância
        # desqualifica o resto das informações aos olhos de quem lê.
        if len(incidentes) == 1:
            linhas.append("1 ramo conectado a esta barra.")
        else:
            linhas.append(f"{len(incidentes)} ramos conectados a esta barra.")

        if penduradas:
            # A ordem alfabética por nome é estável entre aberturas: o
            # cartão não reorganiza a lista a cada atualização, e o olho
            # encontra o mesmo elemento no mesmo lugar.
            for der in sorted(penduradas, key=lambda d: d.nome):
                potencia = _potencia_do_elemento(der)
                texto = f"• {der.tipo} {der.nome}"
                if potencia:
                    texto += f" — {potencia}"
                linhas.append(texto)

        cargas = [d for d in penduradas if d.tipo == "Load"]
        if cargas:
            try:
                kw = _somar_parametro(cargas, "kw")
                kvar = _somar_parametro(cargas, "kvar")
            except (TypeError, ValueError):
                kw = kvar = None
            if kw is not None:
                total = f"Carga total: {_formatar_potencia(kw)} kW"
                if kvar is not None:
                    total += f" / {_formatar_potencia(kvar)} kvar"
                linhas.append(total)

        cartao.atualizar(titulo, linhas)
        self._reposicionar_cartao_barra()

    def _reposicionar_cartao_barra(self) -> None:
        """Coloca o cartão ao lado da barra, sem sair do retângulo da cena.

        A posição preferida é à direita e um pouco acima da elipse, do
        lado oposto ao rótulo do nome (que fica acima) para os dois não
        se sobreporem. O clamp existe porque a rede ocupa a cena inteira:
        sem ele, o cartão de uma barra na borda direita sairia da área
        visível e o usuário acharia que o clique não funcionou.
        """
        cartao = self._cartao_barra
        if cartao is None:
            return
        pos = self._posicoes.get(self._cartao_barra_nome)
        if pos is None:
            return

        folga = RAIO_LEQUE * 0.45
        x = pos[0] + folga
        y = pos[1] - cartao.altura() / 2

        area = self.cena.sceneRect()
        if not area.isNull():
            x = min(max(x, area.left() + 4), area.right() - cartao.LARGURA - 4)
            y = min(max(y, area.top() + 4), area.bottom() - cartao.altura() - 4)
        cartao.setPos(x, y)

    # ------------------------------------------------------------------ #
    def _aplicar_posicoes_salvas(self, posicoes):
        """Troca as posições automáticas pelas que o projeto guardou.

        Barras e derivações com `posicao` preenchida no modelo assumem a
        coordenada de cena gravada; as demais ficam com o resultado do
        cálculo automático. O dicionário recebido não é alterado, e sim
        copiado — ele é o resultado do layout automático, que serve de
        referência para quem não tem posição própria.

        Coordenada salva fora do formato esperado (lista de dois números)
        é descartada em silêncio: um rede.json editado à mão não pode
        impedir o projeto de abrir.
        """
        resultado = dict(posicoes)
        for nome, barra in self.rede.barras.items():
            ponto = _ponto_salvo_valido(barra.posicao)
            if ponto is not None and nome in resultado:
                resultado[nome] = ponto
        return resultado

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
            # A cena inteira será descartada, e com ela o cartão. Fechar
            # antes do clear é o que evita guardar referência a um item
            # morto — o mesmo motivo pelo qual os índices abaixo são
            # remontados do zero.
            cartao_aberto = self._cartao_barra_nome
            self.fechar_cartao_barra()
            self.cena.clear()
            # Os itens que representavam a seleção morreram com o clear.
            # Manter a referência seria guardar ponteiros para objetos
            # destruídos; a identidade (categoria, nome) fica, e o
            # destaque é reaplicado no fim — se o elemento ainda existir.
            self._itens_selecionados = []
            orientacao = self.orientacao

            posicoes_cruas = calcular_posicoes(self.rede, orientacao=orientacao)
            posicoes, escala = self._transformar_posicoes(posicoes_cruas)
            # A posição salva no projeto vence a automática. O cálculo
            # acima continua sendo feito por inteiro: ele define a escala
            # do desenho e a posição das barras que o usuário nunca
            # moveu — só o que tem posição própria é sobrescrito.
            posicoes = self._aplicar_posicoes_salvas(posicoes)
            self._posicoes = dict(posicoes)
            self._escala = escala

            raio_barra = max(4, RAIO_BARRA_BASE * escala)
            espessura_linha = max(1, round(3 * escala))

            # Os índices que o arraste consulta são remontados a cada
            # redesenho. A cena foi descartada logo acima, então manter
            # os valores antigos guardaria referências a itens mortos.
            self._dependencias_por_barra = {}
            self._offsets_rotulos_barras = {}
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

                cor = _no_tema(CORES.get(ramo.tipo, "black"), self._tema)
                # _LinhaRamoItem, e não QGraphicsLineItem: é o ramo que
                # responde ao clique no painel de propriedades e que
                # desenha o destaque de seleção.
                linha = _LinhaRamoItem(
                    QLineF(p1[0], p1[1], p2[0], p2[1]),
                    nome_ramo=ramo.nome, editor=self)
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
                if ramo.rotulo_visivel:
                    rotulo_ramo = self._desenhar_rotulo(
                        mx, my, f"{ramo.tipo}\n{ramo.nome}", cor,
                        alvo=ramo.nome, tipo_alvo="ramo",
                        desvio=ramo.rotulo_posicao)
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
                    #
                    # A ordem de precedência é a mesma da barra: o ajuste
                    # desta sessão vem primeiro, depois a posição salva no
                    # projeto, e por último o ângulo do leque.
                    override = self._posicoes_derivacoes.get(der.nome)
                    if override is None:
                        override = _ponto_salvo_valido(der.posicao)
                    if override is not None:
                        ex, ey = override
                    self._posicoes[der.nome] = (ex, ey)

                    cor = _no_tema(CORES.get(der.tipo, "gray"), self._tema)

                    ligacao = QGraphicsLineItem(pos_bus[0], pos_bus[1], ex, ey)
                    caneta = QPen(_qcolor(cor), max(1, espessura_linha - 2))
                    caneta.setStyle(Qt.PenStyle.DotLine)
                    ligacao.setPen(caneta)
                    ligacao.setZValue(0.0)
                    self.cena.addItem(ligacao)
                    self._ligacoes_derivacoes[der.nome] = (ligacao, bus)

                    tem_curva = any(der.parametros.get(c) not in (None, "", "Nenhuma")
                                    for c in ("daily", "duty", "yearly"))
                    texto_der = f"{der.tipo}\n{der.nome}" + (" 📈" if tem_curva else "")
                    # A caixa nasce DEPOIS do texto, e não antes: o texto
                    # é que define o tamanho dela. Medir aqui, com a mesma
                    # fonte e o mesmo teto de largura do _RotuloItem, é o
                    # que garante que a pílula nunca fique menor que o que
                    # precisa conter.
                    largura_texto, altura_texto = _medir_texto_rotulo(
                        texto_der, tamanho_fonte=7)
                    # A ponta da ligação para na borda da caixa, e não no
                    # centro dela: com o texto dentro, a linha entrando até
                    # o centro ficaria escondida sob o preenchimento.
                    fim_x, fim_y = _ponto_na_borda_da_caixa(
                        (pos_bus[0], pos_bus[1]), (ex, ey),
                        largura_texto / 2 + PADDING_CAIXA_H,
                        altura_texto / 2 + PADDING_CAIXA_V)
                    ligacao.setLine(pos_bus[0], pos_bus[1], fim_x, fim_y)
                    caixa = _DerivacaoItem(
                        der.nome, bus, self,
                        largura_texto + 2 * PADDING_CAIXA_H,
                        altura_texto + 2 * PADDING_CAIXA_V)
                    caixa.setPos(ex, ey)
                    caixa.setBrush(QBrush(_qcolor(cor)))
                    caixa.setPen(QPen(
                        _qcolor(self._tema["caixa_borda"]), 1))
                    caixa.setZValue(1.0)
                    self.cena.addItem(caixa)

                    # Cor do texto escolhida por contraste com o
                    # preenchimento da caixa, e sem retângulo de fundo
                    # (fundo=False). Antes era branco fixo, que sobre os
                    # preenchimentos claros ficava ilegível.
                    if der.rotulo_visivel:
                        rotulo_der = self._desenhar_rotulo(
                            ex, ey, texto_der, _cor_texto_sobre(cor),
                            tamanho_fonte=7, fundo=False,
                            alvo=der.nome, tipo_alvo="derivacao")
                        _prender_rotulo_na_caixa(rotulo_der, caixa)
                        caixa.rotulo = rotulo_der
                        self._rotulos_derivacoes[der.nome] = rotulo_der

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
                rotulo_barra = None
                if barra.rotulo_visivel:
                    rotulo_barra = self._desenhar_rotulo(
                        x, y - DESLOCAMENTO_ROTULO_BARRA,
                        f"{nome}\n{barra.kv_base} kV",
                        self._tema["texto_rotulo_barra"],
                        alvo=nome, tipo_alvo="barra",
                        desvio=barra.rotulo_posicao)
                    # O rótulo entra nas dependências da PRÓPRIA barra, na
                    # forma (item, mover_fim=False, rotulo). Sem esse
                    # registro ele ficaria no ponto de origem enquanto a
                    # elipse anda — foi exatamente a queixa de que o
                    # "Barra / Tensão" não acompanhava o arraste. O
                    # deslocamento é medido no redesenho e reaproveitado no
                    # arraste, para que a distância relativa não dependa do
                    # tamanho do texto. Ele já embute o desvio do usuário,
                    # porque a posição de origem nasce da soma dos dois.
                    self._dependencias_por_barra.setdefault(nome, []).append(
                        (None, False, rotulo_barra))
                    self._offsets_rotulos_barras[nome] = (
                        rotulo_barra.x() - x, rotulo_barra.y() - y)

            largura_canvas = max(self.view.viewport().width(), 300)
            altura_canvas = max(self.view.viewport().height(), 300)
            self.cena.setSceneRect(0, 0, largura_canvas, altura_canvas)

            self._atualizar_lista_elementos()
        finally:
            self._redesenhando = False
        # O espelho global de rótulos acompanha o que ficou de fato
        # desenhado: um "mostrar todos" seguido de ocultar um texto só
        # deixaria o atributo mentindo sobre o estado da cena.
        self.mostrar_rotulos = any(
            b.rotulo_visivel for b in self.rede.barras.values())
        # O cartão é reaberto fora da trava de reentrância: montá-lo lá
        # dentro dispararia addItem e itemChange enquanto a cena ainda
        # está sendo montada, e o cartão apareceria deslocado.
        if cartao_aberto is not None and cartao_aberto in self.rede.barras:
            self.abrir_cartao_barra(cartao_aberto)
        # A seleção do mapa sobrevive ao redesenho quando o elemento
        # continua existindo — o destaque é reaplicado aos itens novos, e
        # o painel confirma se o alvo ainda está no modelo (a exclusão
        # chama este caminho e não pode deixar o cartão preso no que
        # sumiu).
        if self._selecao_mapa is not None:
            self._marcar_itens_da_selecao()
            if self._descricao_selecao(self._selecao_mapa) is None:
                self._selecao_mapa = None
        self.atualizar_card_propriedades()
        # O rodapé conta o que acabou de ser desenhado. Fica fora do
        # try/finally da reconstrução para não ser chamado com a cena
        # pela metade.
        self._atualizar_status()

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
