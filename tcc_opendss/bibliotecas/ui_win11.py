"""
ui_win11.py (port para o TCC OpenDSS)

Diálogos de entrada de dados no visual do Windows 11 (Fluent Design),
construídos com PySide6. O módulo de Validação do Modelo Computacional
(dimensionamento e otimização do posicionamento de BESS para mitigar
afundamentos de tensão) usa estes diálogos para colher parâmetros, avisar e
confirmar. A janela principal da validação também reaproveita a mesma paleta
e a mesma fonte — ver API PÚBLICA ADICIONAL, ao final do arquivo —, e é só
por isso que a janela grande e os diálogos pequenos se parecem.

ORIGEM DO PADRÃO VISUAL
=======================
Port fiel do módulo "ui_win11.py" do projeto "gerenciamento_de_demandas"
(fonte citada), mantido com o mesmo padrão Win11/Fluent e a mesma paleta.
Mudaram apenas o cabeçalho/documentação e o bloco de teste manual
(``__main__``) no fim; paleta, fontes, diálogos e API pública continuam
idênticos aos do projeto de origem.

POR QUE PySide6 E NÃO TKINTER PURO
==================================
O tkinter nativo, mesmo com o tema "vista" do Windows, não reproduz os
elementos visuais do Windows 11: cantos arredondados, paleta Mica/Fluent,
tipografia Segoe UI Variable, sombra suave de elevação. O PySide6 permite
estilizar os diálogos com QSS (o CSS do Qt) mais QGraphicsDropShadowEffect,
e com isso chegar perto do padrão do sistema.

ESCOPO: DIÁLOGOS MODAIS, NÃO JANELAS DE TRABALHO COMPLETAS
==========================================================
Aqui só há diálogos modais simples — texto, perguntas multilinha, aviso,
confirmação Sim/Não. Abas, tabelas e listas de seleção múltipla ficam de
fora: a janela principal do módulo de Validação é construída diretamente
com QTableWidget/QMenu do PySide6 e apenas reaproveita a paleta e a fonte
definidas neste arquivo.

TÉCNICA DE CANTOS ARREDONDADOS
==============================
A janela não tem moldura nativa (FramelessWindowHint +
WA_TranslucentBackground). Só o container principal ("cartão") tem fundo
opaco com border-radius. Todos os widgets internos — barra de título, área
de conteúdo, área de botões — são QWidget planos, sem QSS de fundo próprio,
e portanto transparentes: o fundo arredondado do cartão aparece por trás
deles. Se algum filho pintasse o próprio fundo, os cantos do container
apareceriam quadrados.

TEMA CLARO/ESCURO
=================
O tema vem do registro do Windows ("AppsUseLightTheme"), com queda para o
tema claro em qualquer falha — ambiente não Windows, chave ausente, falta
de permissão. O parâmetro "tema" das funções públicas (pedir_texto_win11,
pedir_perguntas_win11, mostrar_aviso_win11, confirmar_win11) força um tema
específico quando necessário: "auto" (padrão), "claro" ou "escuro".

COR DE DESTAQUE (ACCENT) FIXA EM AZUL INSTITUCIONAL
===================================================
O accent é a cor de destaque usada nos botões principais, nas bordas de
foco e na seleção de texto. Ele não segue o accent dinâmico do Windows: no
tema escuro, o accent padrão do Windows 11 vira um azul claro ("#60CDFF")
que quase desaparece sob texto branco. Por isso o accent é fixo em
"#004587", o azul institucional do TCC, nos dois temas — ver
COR_ACCENT_MARCA.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import List, Literal, Optional

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt
from PySide6.QtGui import QFont, QFontDatabase, QKeySequence, QMouseEvent, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

TemaNome = Literal["auto", "claro", "escuro"]


# ============================================================================
# PALETA DE CORES (WINDOWS 11 - TEMAS CLARO E ESCURO)
# ============================================================================

# Azul "de marca", usado como accent fixo nos dois temas. O motivo está no
# topo do arquivo, em "COR DE DESTAQUE (ACCENT) FIXA EM AZUL
# INSTITUCIONAL": no tema escuro o accent do Windows fica claro demais para
# carregar texto branco. Fixar a cor mantém cabeçalho, botões, abas, foco
# de campo e seleção falando a mesma língua visual.
COR_ACCENT_MARCA = "#004587"
COR_ACCENT_MARCA_HOVER = "#0A5BA8"
COR_ACCENT_MARCA_PRESSED = "#003766"


@dataclass(frozen=True)
class _Paleta:
    """Conjunto imutável de cores de um tema.

    Uma dataclass é só uma classe cujos campos são declarados uma vez e
    preenchidos na construção - aqui, um registro de cores. ``frozen=True``
    impede alteração depois de criada: paleta é constante, e um valor
    trocado por acidente em um ponto do código apareceria como cor errada
    em outro.
    """
    fundo_cartao: str
    fundo_cartao_fim_gradiente: str
    borda_cartao: str
    texto_primario: str
    texto_secundario: str
    accent: str
    accent_hover: str
    accent_pressed: str
    borda_campo: str
    fundo_campo: str
    fechar_hover: str
    aviso: str
    botao_secundario_fundo: str
    botao_secundario_hover: str
    botao_secundario_pressed: str
    divisor: str
    sombra_cor: tuple  # (r, g, b, a)


PALETA_CLARA = _Paleta(
    fundo_cartao="#FFFFFF",
    fundo_cartao_fim_gradiente="#FAFAFA",
    borda_cartao="#E5E5E5",
    texto_primario="#1B1B1B",
    texto_secundario="#6B6B6B",
    accent=COR_ACCENT_MARCA,
    accent_hover=COR_ACCENT_MARCA_HOVER,
    accent_pressed=COR_ACCENT_MARCA_PRESSED,
    borda_campo="#8A8A8A",
    fundo_campo="#FFFFFF",
    fechar_hover="#C42B1C",
    aviso="#C42B1C",
    botao_secundario_fundo="#FFFFFF",
    botao_secundario_hover="#F3F3F3",
    botao_secundario_pressed="#E5E5E5",
    divisor="#E8E8E8",
    sombra_cor=(0, 0, 0, 90),
)

PALETA_ESCURA = _Paleta(
    fundo_cartao="#2C2C2C",
    fundo_cartao_fim_gradiente="#272727",
    borda_cartao="#3D3D3D",
    texto_primario="#F3F3F3",
    texto_secundario="#C5C5C5",
    accent=COR_ACCENT_MARCA,
    accent_hover=COR_ACCENT_MARCA_HOVER,
    accent_pressed=COR_ACCENT_MARCA_PRESSED,
    borda_campo="#6E6E6E",
    fundo_campo="#1E1E1E",
    fechar_hover="#C42B1C",
    aviso="#FF99A4",
    botao_secundario_fundo="#2C2C2C",
    botao_secundario_hover="#3A3A3A",
    botao_secundario_pressed="#454545",
    divisor="#3D3D3D",
    sombra_cor=(0, 0, 0, 160),
)

RAIO_BORDA_CARTAO = 10
RAIO_BORDA_CAMPO = 5
RAIO_BORDA_BOTAO = 6


def _detectar_tema_do_windows() -> Literal["claro", "escuro"]:
    """
    Lê a chave de registro em que o Windows diz se os aplicativos devem usar
    o tema claro ou o escuro (AppsUseLightTheme: 1 = claro, 0 = escuro).

    Qualquer falha — ambiente não Windows, chave ausente, sem permissão —
    cai no tema claro. Escolher o claro como padrão é menos arriscado: um
    diálogo claro sobre um fundo escuro ainda é legível, o contrário pode
    não ser.
    """
    try:
        import winreg

        # Import local de propósito: winreg só existe no Windows, e um import
        # no topo faria o módulo inteiro falhar em outra plataforma em vez de
        # cair no except e devolver o tema claro.

        chave = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        valor, _tipo = winreg.QueryValueEx(chave, "AppsUseLightTheme")
        return "claro" if valor == 1 else "escuro"
    except Exception:
        return "claro"


def _resolver_paleta(tema: TemaNome) -> _Paleta:
    """Traduz "auto"/"claro"/"escuro" no objeto de paleta correspondente."""
    tema_resolvido = _detectar_tema_do_windows() if tema == "auto" else tema
    return PALETA_ESCURA if tema_resolvido == "escuro" else PALETA_CLARA


# ============================================================================
# FONTE, ICONES E APLICACAO (SINGLETON)
# ============================================================================


def _fonte_padrao(tamanho: int = 10, negrito: bool = False) -> QFont:
    """Monta a fonte padrão do projeto.

    A preferida é a Segoe UI Variable Text, do Windows 11; em Windows 10 ela
    não existe e o Qt recua para a Segoe UI. ``setFamilies`` aceita a lista
    inteira justamente para esse recuo acontecer sem código extra.
    """
    fonte = QFont("Segoe UI", tamanho)
    fonte.setFamilies(["Segoe UI Variable Text", "Segoe UI"])
    fonte.setBold(negrito)
    return fonte


_FAMILIAS_ICONES_FLUENT = ("Segoe Fluent Icons", "Segoe MDL2 Assets")
_GLIFO_FECHAR = "\uE8BB"  # "ChromeClose" no conjunto Segoe Fluent/MDL2


def _fonte_icones_disponivel() -> Optional[str]:
    """Devolve o nome de uma fonte de ícones Fluent instalada, ou None.

    None não é erro: significa que o chamador deve usar um glifo unicode
    comum ("✕") no lugar do ícone de vetor. Sem essa checagem, o botão de
    fechar apareceria como um retângulo vazio em sistemas sem a fonte.
    """
    familias_instaladas = set(QFontDatabase.families())
    for familia in _FAMILIAS_ICONES_FLUENT:
        if familia in familias_instaladas:
            return familia
    return None


_app: Optional[QApplication] = None


def _garantir_app() -> QApplication:
    """Garante uma única QApplication no processo, reaproveitada entre diálogos.

    O Qt permite uma instância por processo; criar a segunda aborta o
    programa. Como vários diálogos podem ser abertos em sequência, esta
    função é o ponto único de checagem.
    """
    global _app
    instancia = QApplication.instance()
    if instancia is not None:
        _app = instancia
        return _app

    _app = QApplication(list(sys.argv))
    _app.setFont(_fonte_padrao(10))
    return _app


def _estilo_campo_texto(paleta: _Paleta, invalido: bool = False) -> str:
    """QSS dos campos de texto do diálogo, com realce de borda quando inválido.

    O parâmetro ``invalido`` troca a cor da borda pelo vermelho de aviso —
    realce imediato no campo errado, sem esperar o usuário ler a mensagem.
    """
    cor_borda = paleta.aviso if invalido else paleta.borda_campo
    return f"""
    QLineEdit, QTextEdit {{
        background-color: {paleta.fundo_campo};
        color: {paleta.texto_primario};
        border: 1px solid {cor_borda};
        border-radius: {RAIO_BORDA_CAMPO}px;
        padding: 7px 10px;
        selection-background-color: {paleta.accent};
    }}
    QLineEdit:focus, QTextEdit:focus {{
        border: 1px solid {paleta.accent};
        border-bottom: 2px solid {paleta.accent};
    }}
    QLineEdit::placeholder, QTextEdit {{
        color: {paleta.texto_secundario};
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {paleta.borda_campo};
        border-radius: 4px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {paleta.texto_secundario};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    """


# ============================================================================
# BARRA DE TITULO CUSTOMIZADA (ARRASTE + ACCENT DOT + BOTAO DE FECHAR)
# ============================================================================


class _BarraTituloWin11(QWidget):
    """Barra de título própria, sem a moldura do Windows.

    Traz o ponto colorido de destaque, permite arrastar a janela pelo
    cabeçalho e fechar pelo botão no estilo Win11. Como a moldura nativa foi
    removida, o arraste tem de ser implementado à mão: sem estes três
    tratadores de mouse, a janela ficaria presa no lugar.
    """

    def __init__(self, titulo: str, dialogo: QDialog, paleta: _Paleta):
        super().__init__(dialogo)
        self._dialogo = dialogo
        self._paleta = paleta
        self._posicao_arraste: Optional[QPoint] = None

        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 0, 8, 0)
        layout.setSpacing(10)

        marca = QLabel("●", self)
        marca.setStyleSheet(f"color: {paleta.accent}; font-size: 10px;")
        layout.addWidget(marca)

        rotulo_titulo = QLabel(titulo, self)
        rotulo_titulo.setFont(_fonte_padrao(11, negrito=True))
        rotulo_titulo.setStyleSheet(f"color: {paleta.texto_primario};")
        layout.addWidget(rotulo_titulo)
        layout.addStretch(1)

        botao_fechar = QPushButton(self)
        botao_fechar.setFixedSize(34, 34)
        botao_fechar.setCursor(Qt.PointingHandCursor)

        fonte_icones = _fonte_icones_disponivel()
        if fonte_icones:
            botao_fechar.setText(_GLIFO_FECHAR)
            botao_fechar.setFont(QFont(fonte_icones, 10))
        else:
            botao_fechar.setText("✕")
            botao_fechar.setFont(_fonte_padrao(10))

        botao_fechar.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {paleta.texto_primario};
                border-top-right-radius: {RAIO_BORDA_CARTAO}px;
            }}
            QPushButton:hover {{
                background-color: {paleta.fechar_hover};
                color: white;
            }}
            QPushButton:pressed {{
                background-color: #A4262C;
                color: white;
            }}
            """
        )
        botao_fechar.clicked.connect(dialogo.reject)
        layout.addWidget(botao_fechar)

    def mousePressEvent(self, evento: QMouseEvent) -> None:
        """Guarda o deslocamento entre o cursor e o canto da janela."""
        if evento.button() == Qt.LeftButton:
            self._posicao_arraste = evento.globalPosition().toPoint() - self._dialogo.frameGeometry().topLeft()
        super().mousePressEvent(evento)

    def mouseMoveEvent(self, evento: QMouseEvent) -> None:
        """Move a janela mantendo o cursor sobre o mesmo ponto do cabeçalho."""
        if self._posicao_arraste is not None and evento.buttons() & Qt.LeftButton:
            self._dialogo.move(evento.globalPosition().toPoint() - self._posicao_arraste)
        super().mouseMoveEvent(evento)

    def mouseReleaseEvent(self, evento: QMouseEvent) -> None:
        """Zera o deslocamento: soltar o botão termina o arraste."""
        self._posicao_arraste = None
        super().mouseReleaseEvent(evento)


# ============================================================================
# DIALOGO BASE (CARTAO ARREDONDADO + SOMBRA + TITULO + DIVISOR + BOTOES)
# ============================================================================


class _DialogoBaseWin11(QDialog):
    """Base de todos os diálogos: cartão arredondado, sombra, título e botões.

    Reunir isso em uma classe evita repetir a mesma configuração de janela
    sem moldura em cada diálogo derivado — e, principalmente, garante que
    todos se comportem igual: mesma sombra, mesmo divisor antes dos botões,
    mesma animação de entrada, mesmo Esc para cancelar.
    """

    def __init__(
        self,
        titulo: str,
        largura: int = 420,
        tema: TemaNome = "auto",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        _garantir_app()

        self.paleta = _resolver_paleta(tema)

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setFont(_fonte_padrao(10))
        self.setFixedWidth(largura)

        layout_externo = QVBoxLayout(self)
        layout_externo.setContentsMargins(18, 18, 18, 18)

        self._cartao = QFrame(self)
        self._cartao.setObjectName("cartao")
        self._cartao.setStyleSheet(
            f"""
            QFrame#cartao {{
                background-color: {self.paleta.fundo_cartao};
                border: 1px solid {self.paleta.borda_cartao};
                border-radius: {RAIO_BORDA_CARTAO}px;
            }}
            """
        )

        sombra = QGraphicsDropShadowEffect(self._cartao)
        sombra.setBlurRadius(36)
        sombra.setXOffset(0)
        sombra.setYOffset(8)
        r, g, b, a = self.paleta.sombra_cor
        from PySide6.QtGui import QColor

        sombra.setColor(QColor(r, g, b, a))
        self._cartao.setGraphicsEffect(sombra)

        layout_externo.addWidget(self._cartao)

        layout_cartao = QVBoxLayout(self._cartao)
        layout_cartao.setContentsMargins(0, 0, 0, 0)
        layout_cartao.setSpacing(0)

        layout_cartao.addWidget(_BarraTituloWin11(titulo, self, self.paleta))

        area_conteudo = QWidget(self._cartao)
        self._layout_conteudo = QVBoxLayout(area_conteudo)
        self._layout_conteudo.setContentsMargins(22, 14, 22, 14)
        self._layout_conteudo.setSpacing(10)
        layout_cartao.addWidget(area_conteudo)

        divisor = QFrame(self._cartao)
        divisor.setFixedHeight(1)
        divisor.setStyleSheet(f"background-color: {self.paleta.divisor}; border: none;")
        layout_cartao.addWidget(divisor)

        area_botoes = QWidget(self._cartao)
        self._layout_botoes = QHBoxLayout(area_botoes)
        self._layout_botoes.setContentsMargins(22, 12, 22, 18)
        self._layout_botoes.setSpacing(10)
        self._layout_botoes.addStretch(1)
        layout_cartao.addWidget(area_botoes)

        # Esc cancela. O QDialog já faz isso por padrão, mas o atalho
        # explícito sobrevive a uma subclasse que sobrescreva
        # keyPressEvent sem chamar a implementação da base - caso em que o
        # usuário ficaria sem saída pelo teclado.
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.reject)

        self._animacao_entrada: Optional[QPropertyAnimation] = None

    def adicionar_conteudo(self, widget: QWidget) -> None:
        """Encaixa um widget na área de conteúdo, acima do divisor."""
        self._layout_conteudo.addWidget(widget)

    def adicionar_botao(self, botao: QPushButton) -> None:
        """Encaixa um botão na área inferior, alinhado à direita."""
        self._layout_botoes.addWidget(botao)

    def _criar_botao(self, texto: str, principal: bool = False) -> QPushButton:
        """Cria um botão no estilo Win11.

        ``principal=True`` pinta o botão com o accent, que é o caso da ação
        que o usuário deve tomar; os demais ficam em contorno, para não
        competir por atenção.
        """
        paleta = self.paleta
        botao = QPushButton(texto)
        botao.setFixedHeight(34)
        botao.setMinimumWidth(110)
        botao.setCursor(Qt.PointingHandCursor)
        botao.setFont(_fonte_padrao(10))

        if principal:
            botao.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {paleta.accent};
                    color: white;
                    border: none;
                    border-radius: {RAIO_BORDA_BOTAO}px;
                }}
                QPushButton:hover {{ background-color: {paleta.accent_hover}; }}
                QPushButton:pressed {{ background-color: {paleta.accent_pressed}; }}
                QPushButton:disabled {{ background-color: {paleta.borda_cartao}; color: {paleta.texto_secundario}; }}
                """
            )
        else:
            botao.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {paleta.botao_secundario_fundo};
                    color: {paleta.texto_primario};
                    border: 1px solid {paleta.borda_campo};
                    border-radius: {RAIO_BORDA_BOTAO}px;
                }}
                QPushButton:hover {{ background-color: {paleta.botao_secundario_hover}; }}
                QPushButton:pressed {{ background-color: {paleta.botao_secundario_pressed}; }}
                """
            )
        return botao

    def showEvent(self, evento) -> None:
        """Ajusta o diálogo ao ser exibido: centraliza, traz à frente e anima."""
        super().showEvent(evento)
        self._centralizar_na_tela()
        self.raise_()
        self.activateWindow()
        self._iniciar_animacao_entrada()

    def _iniciar_animacao_entrada(self) -> None:
        """Faz o diálogo surgir com opacidade de 0 a 1, em 140 ms.

        Diálogo sem moldura que aparece de uma vez dá a impressão de falha
        de desenho; a transição curta resolve isso sem atrasar o uso.
        """
        self.setWindowOpacity(0.0)
        self._animacao_entrada = QPropertyAnimation(self, b"windowOpacity", self)
        self._animacao_entrada.setDuration(140)
        self._animacao_entrada.setStartValue(0.0)
        self._animacao_entrada.setEndValue(1.0)
        self._animacao_entrada.setEasingCurve(QEasingCurve.OutCubic)
        self._animacao_entrada.start()

    def _centralizar_na_tela(self) -> None:
        """Centraliza o diálogo na área útil da tela principal.

        ``availableGeometry`` desconta a barra de tarefas; usar a geometria
        inteira jogaria o diálogo parcialmente para baixo dela.
        """
        tela = QApplication.primaryScreen()
        if tela is None:
            return
        geometria_tela = tela.availableGeometry()
        x = geometria_tela.center().x() - self.width() // 2
        y = geometria_tela.center().y() - self.height() // 2
        self.move(x, y)


# ============================================================================
# DIALOGO: TEXTO DE UMA LINHA (EX.: NOME DO PROJETO)
# ============================================================================


class _DialogoTextoWin11(_DialogoBaseWin11):
    def __init__(
        self,
        titulo: str,
        rotulo: str,
        texto_padrao: str = "",
        placeholder: str = "",
        tema: TemaNome = "auto",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(titulo, largura=440, tema=tema, parent=parent)
        self._valor: Optional[str] = None

        rotulo_campo = QLabel(rotulo, self)
        rotulo_campo.setStyleSheet(f"color: {self.paleta.texto_primario};")
        rotulo_campo.setWordWrap(True)
        self.adicionar_conteudo(rotulo_campo)

        self.campo = QLineEdit(self)
        self.campo.setText(texto_padrao)
        if placeholder:
            self.campo.setPlaceholderText(placeholder)
        self.campo.setStyleSheet(_estilo_campo_texto(self.paleta))
        self.campo.setFixedHeight(34)
        self.adicionar_conteudo(self.campo)

        self._rotulo_aviso = QLabel("", self)
        self._rotulo_aviso.setStyleSheet(f"color: {self.paleta.aviso}; font-size: 9pt;")
        self._rotulo_aviso.setWordWrap(True)
        self._rotulo_aviso.setVisible(False)
        self.adicionar_conteudo(self._rotulo_aviso)

        botao_cancelar = self._criar_botao("Cancelar", principal=False)
        botao_cancelar.clicked.connect(self.reject)
        self.adicionar_botao(botao_cancelar)

        self.botao_ok = self._criar_botao("OK", principal=True)
        self.botao_ok.setDefault(True)
        self.botao_ok.clicked.connect(self._confirmar)
        self.adicionar_botao(self.botao_ok)

        self.campo.returnPressed.connect(self._confirmar)
        self.campo.textChanged.connect(self._limpar_estado_invalido)
        self.campo.setFocus()

    def _limpar_estado_invalido(self) -> None:
        """Retira o realce de erro assim que o usuário volta a digitar."""
        if self._rotulo_aviso.isVisible():
            self._rotulo_aviso.setVisible(False)
            self.campo.setStyleSheet(_estilo_campo_texto(self.paleta))

    def _confirmar(self) -> None:
        """Guarda o texto e fecha; ``valor()`` só o devolve se o diálogo foi aceito."""
        self._valor = self.campo.text()
        self.accept()

    def valor(self) -> Optional[str]:
        """Texto digitado, ou None se o usuário cancelou."""
        return self._valor if self.result() == QDialog.Accepted else None


# ============================================================================
# DIALOGO: MULTIPLAS PERGUNTAS (TEXTO MULTILINHA)
# ============================================================================


class _DialogoPerguntasWin11(_DialogoBaseWin11):
    def __init__(self, titulo: str, tema: TemaNome = "auto", parent: Optional[QWidget] = None):
        super().__init__(titulo, largura=540, tema=tema, parent=parent)
        self._perguntas: List[str] = []

        rotulo = QLabel("Digite as perguntas a enviar, uma por linha:", self)
        rotulo.setStyleSheet(f"color: {self.paleta.texto_primario};")
        self.adicionar_conteudo(rotulo)

        self.campo = QTextEdit(self)
        self.campo.setPlaceholderText(
            "Ex.:\nQual o status do pedido 12345?\nListar materiais com estoque zerado"
        )
        self.campo.setStyleSheet(_estilo_campo_texto(self.paleta))
        self.campo.setFixedHeight(220)
        self.adicionar_conteudo(self.campo)

        linha_rodape = QWidget(self)
        layout_rodape = QHBoxLayout(linha_rodape)
        layout_rodape.setContentsMargins(0, 0, 0, 0)

        self._rotulo_aviso = QLabel("", self)
        self._rotulo_aviso.setStyleSheet(f"color: {self.paleta.aviso}; font-size: 9pt;")
        self._rotulo_aviso.setWordWrap(True)
        self._rotulo_aviso.setVisible(False)
        layout_rodape.addWidget(self._rotulo_aviso, 1)

        self._rotulo_contador = QLabel("0 pergunta(s) detectada(s)", self)
        self._rotulo_contador.setStyleSheet(f"color: {self.paleta.texto_secundario}; font-size: 9pt;")
        self._rotulo_contador.setAlignment(Qt.AlignRight)
        layout_rodape.addWidget(self._rotulo_contador)

        self.adicionar_conteudo(linha_rodape)

        rotulo_dica = QLabel("Dica: pressione Ctrl+Enter para enviar.", self)
        rotulo_dica.setStyleSheet(f"color: {self.paleta.texto_secundario}; font-size: 8.5pt;")
        self.adicionar_conteudo(rotulo_dica)

        botao_cancelar = self._criar_botao("Cancelar", principal=False)
        botao_cancelar.clicked.connect(self.reject)
        self.adicionar_botao(botao_cancelar)

        self.botao_ok = self._criar_botao("Enviar", principal=True)
        self.botao_ok.setDefault(True)
        self.botao_ok.clicked.connect(self._confirmar)
        self.adicionar_botao(self.botao_ok)

        self.campo.textChanged.connect(self._atualizar_contador)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._confirmar)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._confirmar)

        self.campo.setFocus()

    def _extrair_linhas(self) -> List[str]:
        """Separa o texto em linhas, descartando as vazias."""
        return [linha.strip() for linha in self.campo.toPlainText().splitlines() if linha.strip()]

    def _atualizar_contador(self) -> None:
        """Atualiza o contador do rodapé e limpa o aviso de campo vazio."""
        total = len(self._extrair_linhas())
        sufixo = "pergunta detectada" if total == 1 else "perguntas detectadas"
        self._rotulo_contador.setText(f"{total} {sufixo}")

        if self._rotulo_aviso.isVisible():
            self._rotulo_aviso.setVisible(False)
            self.campo.setStyleSheet(_estilo_campo_texto(self.paleta))

    def _confirmar(self) -> None:
        """Aceita apenas com ao menos uma pergunta; caso contrário, marca o campo."""
        linhas = self._extrair_linhas()
        if not linhas:
            self._rotulo_aviso.setText("É necessário informar ao menos uma pergunta.")
            self._rotulo_aviso.setVisible(True)
            self.campo.setStyleSheet(_estilo_campo_texto(self.paleta, invalido=True))
            self.campo.setFocus()
            return
        self._perguntas = linhas
        self.accept()

    def perguntas(self) -> List[str]:
        """Perguntas digitadas, ou lista vazia se o usuário cancelou."""
        return self._perguntas if self.result() == QDialog.Accepted else []


# ============================================================================
# DIALOGO: AVISO SIMPLES (OK)
# ============================================================================


class _DialogoAvisoWin11(_DialogoBaseWin11):
    def __init__(self, titulo: str, mensagem: str, tema: TemaNome = "auto", parent: Optional[QWidget] = None):
        super().__init__(titulo, largura=400, tema=tema, parent=parent)

        rotulo = QLabel(mensagem, self)
        rotulo.setStyleSheet(f"color: {self.paleta.texto_primario};")
        rotulo.setWordWrap(True)
        self.adicionar_conteudo(rotulo)

        botao_ok = self._criar_botao("OK", principal=True)
        botao_ok.setDefault(True)
        botao_ok.clicked.connect(self.accept)
        self.adicionar_botao(botao_ok)


# ============================================================================
# DIALOGO: CONFIRMACAO (SIM / NAO)
# ============================================================================


class _DialogoConfirmacaoWin11(_DialogoBaseWin11):
    def __init__(self, titulo: str, mensagem: str, tema: TemaNome = "auto", parent: Optional[QWidget] = None):
        super().__init__(titulo, largura=400, tema=tema, parent=parent)

        rotulo = QLabel(mensagem, self)
        rotulo.setStyleSheet(f"color: {self.paleta.texto_primario};")
        rotulo.setWordWrap(True)
        self.adicionar_conteudo(rotulo)

        botao_nao = self._criar_botao("Não", principal=False)
        botao_nao.clicked.connect(self.reject)
        self.adicionar_botao(botao_nao)

        botao_sim = self._criar_botao("Sim", principal=True)
        botao_sim.setDefault(True)
        botao_sim.clicked.connect(self.accept)
        self.adicionar_botao(botao_sim)


# ============================================================================
# API PUBLICA
# ============================================================================


def pedir_texto_win11(
    titulo: str,
    rotulo: str,
    texto_padrao: str = "",
    placeholder: str = "",
    tema: TemaNome = "auto",
    parent: Optional[QWidget] = None,
) -> Optional[str]:
    """Exibe um diálogo Win11 de texto de uma linha. Retorna o texto digitado, ou None se cancelado."""
    _garantir_app()
    dialogo = _DialogoTextoWin11(titulo, rotulo, texto_padrao, placeholder, tema, parent)
    dialogo.exec()
    return dialogo.valor()


def pedir_perguntas_win11(
    titulo: str, tema: TemaNome = "auto", parent: Optional[QWidget] = None
) -> Optional[List[str]]:
    """Exibe um diálogo multilinha e devolve a lista de perguntas.

    Devolve None quando o usuário cancela. As linhas em branco são
    descartadas, de modo que a lista retornada nunca vem vazia por
    acidente.
    """
    _garantir_app()
    dialogo = _DialogoPerguntasWin11(titulo, tema, parent)
    dialogo.exec()
    if dialogo.result() == QDialog.Accepted:
        return dialogo.perguntas()
    return None


def mostrar_aviso_win11(
    titulo: str, mensagem: str, tema: TemaNome = "auto", parent: Optional[QWidget] = None
) -> None:
    """Exibe um diálogo Win11 de aviso simples, com um único botão OK."""
    _garantir_app()
    dialogo = _DialogoAvisoWin11(titulo, mensagem, tema, parent)
    dialogo.exec()


def confirmar_win11(
    titulo: str, mensagem: str, tema: TemaNome = "auto", parent: Optional[QWidget] = None
) -> bool:
    """Exibe um diálogo de confirmação Sim/Não.

    Devolve True para 'Sim' e False para 'Não' ou janela fechada. Cancelar
    cai no lado seguro por construção: quem chama só segue adiante com um
    True explícito do usuário.
    """
    _garantir_app()
    dialogo = _DialogoConfirmacaoWin11(titulo, mensagem, tema, parent)
    dialogo.exec()
    return dialogo.result() == QDialog.Accepted


# ============================================================================
# API PUBLICA ADICIONAL
# (reaproveitada por outros modulos de UI do modulo de Validacao do
# Modelo Computacional do TCC - ex.: a janela principal de validacao -
# para manter a MESMA identidade visual dos dialogos na janela principal,
# sem duplicar valores de cor/fonte em outro arquivo)
# ============================================================================


def detectar_tema() -> Literal["claro", "escuro"]:
    """Detecta o tema ativo do Windows (claro/escuro) - wrapper público
    de "_detectar_tema_do_windows", para uso fora deste módulo."""
    return _detectar_tema_do_windows()


def obter_paleta_ativa(tema: TemaNome = "auto") -> _Paleta:
    """Retorna o objeto de paleta de cores (Win11 claro/escuro) resolvido
    para o tema informado - usado por outros módulos (ex.: a janela
    principal de validacao) que queiram manter a mesma identidade visual
    dos diálogos. Os campos disponíveis em `_Paleta` incluem:
    fundo_cartao, borda_cartao, texto_primario, texto_secundario, accent
    (SEMPRE o azul institucional fixo - ver COR_ACCENT_MARCA), accent_hover,
    accent_pressed, borda_campo, fundo_campo, aviso,
    botao_secundario_fundo/hover/pressed, divisor, sombra_cor, entre
    outros - ver a dataclass `_Paleta` definida acima."""
    return _resolver_paleta(tema)


# Alias público da fonte padrão - a mesma função que os diálogos usam
# internamente. Sem ele, quem está fora do módulo teria de chamar uma
# função com sublinhado no nome, que a convenção do Python marca como
# privada.
fonte_padrao = _fonte_padrao


# ============================================================================
# TESTE MANUAL (opcional)
# ============================================================================

if __name__ == "__main__":
    # Teste manual: abre um diálogo de aviso para conferir o padrão visual
    # sem precisar subir o sistema inteiro.
    mostrar_aviso_win11(
        "TCC OpenDSS - Validacao do Modelo Computacional",
        "Teste manual do padrao visual Win11 (PySide6) do modulo de "
        "Validacao do Modelo Computacional.",
    )
