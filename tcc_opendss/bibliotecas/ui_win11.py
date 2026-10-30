"""
ui_win11.py (port para o TCC OpenDSS)

Dialogos de entrada de dados com visual Windows 11 (Fluent Design),
construidos com PySide6 - usados pelo modulo de Validacao do Modelo
Computacional do TCC OpenDSS (dimensionamento e otimizacao do
posicionamento de BESS para mitigacao de afundamentos de tensao) para
a coleta de parametros de configuracao, avisos e confirmacoes, E
TAMBEM pela janela principal do modulo de validacao, que reaproveita a
MESMA paleta de cores/fonte deste modulo (ver API PUBLICA ADICIONAL ao
final do arquivo) para manter consistencia visual entre a janela
principal e os dialogos modais.

PADRAO VISUAL PORTADO DO PROJETO "gerenciamento_de_demandas"
================================================
Este arquivo e um port fiel do modulo "ui_win11.py" do projeto
"gerenciamento_de_demandas" (fonte citada), mantido com o MESMO padrao
visual Win11/Fluent e a MESMA paleta, para reuso pelo modulo de
Validacao do Modelo Computacional do TCC. A unica adaptacao de
conteudo foi o cabecalho/documentacao e o bloco de teste manual
(__main__) ao final; a logica de paleta, fontes, dialogos e API publica
permanece identica a do projeto de origem.

POR QUE PySide6 E NAO TKINTER PURO
================================================
O tkinter nativo (mesmo com o tema "vista" do Windows) nao reproduz
os elementos visuais do Windows 11 (cantos arredondados, paleta de
cores Mica/Fluent, tipografia Segoe UI Variable, sombra suave de
elevacao). O PySide6 permite estilizar os dialogos via QSS (CSS-like)
+ QGraphicsDropShadowEffect para aproximar esse padrao visual.

ESCOPO: DIALOGOS MODAIS, NAO JANELAS DE TRABALHO COMPLETAS
================================================
Este modulo oferece apenas DIALOGOS MODAIS simples (texto, perguntas
multilinhas, aviso, confirmacao Sim/Nao) - nao substitui widgets
complexos como abas, tabelas ou listas de selecao multipla usados em
janelas de trabalho completas (ex.: a janela principal do modulo de
Validacao do Modelo Computacional do TCC, que e construida diretamente
com QTableWidget/QMenu do PySide6, apenas reaproveitando a PALETA de
cores e a FONTE padrao definidas aqui).

TECNICA DE CANTOS ARREDONDADOS
================================================
A janela e SEM MOLDURA NATIVA (FramelessWindowHint +
WA_TranslucentBackground). Apenas o container principal ("cartao")
possui fundo opaco com border-radius; todos os widgets internos
(barra de titulo, area de conteudo, area de botoes) sao QWidget
"planos" (sem QSS de fundo proprio), permanecendo transparentes e
deixando o fundo arredondado do "cartao" visivel por tras deles -
evita que filhos opacos "quadrem" os cantos do container.

TEMA CLARO/ESCURO
================================================
O tema e detectado automaticamente a partir do registro do Windows
("AppsUseLightTheme"), com fallback para o tema claro em qualquer
falha (ex.: ambiente nao Windows, chave ausente). Pode ser forcado
manualmente via o parametro "tema" das funcoes publicas
(pedir_texto_win11, pedir_perguntas_win11, mostrar_aviso_win11,
confirmar_win11): "auto" (padrao), "claro" ou "escuro".

COR DE DESTAQUE (ACCENT) FIXA EM AZUL INSTITUCIONAL
================================================
O "accent" (cor de destaque usada em botoes principais, bordas de
foco, selecao de texto etc.) NAO usa o accent dinamico do tema do
Windows - no tema escuro, o accent padrao do Windows 11 resultaria em
um azul CLARO ("#60CDFF"), de baixo contraste quando combinado com
texto branco por cima. Em vez disso, o accent e FIXO em
"#004587" (azul institucional, o tom de marca usado no TCC), nos dois
temas (claro e escuro) - ver COR_ACCENT_MARCA.
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

# Azul "de marca" usado como ACCENT fixo em ambos os temas - ver nota no
# topo do arquivo ("COR DE DESTAQUE (ACCENT) FIXA EM AZUL INSTITUCIONAL").
# Mantido como azul institucional, para consistencia visual
# entre o cabecalho e os elementos interativos (botoes, abas, foco de
# campos, selecao).
COR_ACCENT_MARCA = "#004587"
COR_ACCENT_MARCA_HOVER = "#0A5BA8"
COR_ACCENT_MARCA_PRESSED = "#003766"


@dataclass(frozen=True)
class _Paleta:
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
    Le a chave de registro usada pelo Windows para indicar se os
    aplicativos devem usar o tema claro ou escuro
    (AppsUseLightTheme: 1 = claro, 0 = escuro). Em qualquer falha
    (ambiente nao Windows, chave ausente, sem permissao), assume o
    tema claro como fallback seguro.
    """
    try:
        import winreg

        chave = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        valor, _tipo = winreg.QueryValueEx(chave, "AppsUseLightTheme")
        return "claro" if valor == 1 else "escuro"
    except Exception:
        return "claro"


def _resolver_paleta(tema: TemaNome) -> _Paleta:
    tema_resolvido = _detectar_tema_do_windows() if tema == "auto" else tema
    return PALETA_ESCURA if tema_resolvido == "escuro" else PALETA_CLARA


# ============================================================================
# FONTE, ICONES E APLICACAO (SINGLETON)
# ============================================================================


def _fonte_padrao(tamanho: int = 10, negrito: bool = False) -> QFont:
    """Monta a fonte padrão (Segoe UI Variable Text, com fallback para Segoe UI)."""
    fonte = QFont("Segoe UI", tamanho)
    fonte.setFamilies(["Segoe UI Variable Text", "Segoe UI"])
    fonte.setBold(negrito)
    return fonte


_FAMILIAS_ICONES_FLUENT = ("Segoe Fluent Icons", "Segoe MDL2 Assets")
_GLIFO_FECHAR = "\uE8BB"  # "ChromeClose" no conjunto Segoe Fluent/MDL2


def _fonte_icones_disponivel() -> Optional[str]:
    """Retorna o nome da fonte de icones Fluent instalada no sistema
    (Win10/11), ou None se nenhuma estiver disponivel - nesse caso o
    chamador usa um glifo unicode comum como fallback."""
    familias_instaladas = set(QFontDatabase.families())
    for familia in _FAMILIAS_ICONES_FLUENT:
        if familia in familias_instaladas:
            return familia
    return None


_app: Optional[QApplication] = None


def _garantir_app() -> QApplication:
    """Garante uma única instância de QApplication no processo (reaproveitada entre diálogos)."""
    global _app
    instancia = QApplication.instance()
    if instancia is not None:
        _app = instancia
        return _app

    _app = QApplication(list(sys.argv))
    _app.setFont(_fonte_padrao(10))
    return _app


def _estilo_campo_texto(paleta: _Paleta, invalido: bool = False) -> str:
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
    """Barra de título sem moldura nativa, com marca d'água de cor (accent dot),
    suporte a arraste da janela e botão de fechar estilo Win11."""

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
        if evento.button() == Qt.LeftButton:
            self._posicao_arraste = evento.globalPosition().toPoint() - self._dialogo.frameGeometry().topLeft()
        super().mousePressEvent(evento)

    def mouseMoveEvent(self, evento: QMouseEvent) -> None:
        if self._posicao_arraste is not None and evento.buttons() & Qt.LeftButton:
            self._dialogo.move(evento.globalPosition().toPoint() - self._posicao_arraste)
        super().mouseMoveEvent(evento)

    def mouseReleaseEvent(self, evento: QMouseEvent) -> None:
        self._posicao_arraste = None
        super().mouseReleaseEvent(evento)


# ============================================================================
# DIALOGO BASE (CARTAO ARREDONDADO + SOMBRA + TITULO + DIVISOR + BOTOES)
# ============================================================================


class _DialogoBaseWin11(QDialog):
    """Diálogo base com visual Windows 11: sem moldura nativa, cantos
    arredondados, sombra de elevação, divisor sutil antes da área de
    botões e animação de fade-in ao abrir."""

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

        # Atalho explicito: Esc cancela (QDialog ja faz isso por
        # padrao, mas o atalho explicito garante o comportamento
        # mesmo em subclasses que sobrescrevam keyPressEvent).
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.reject)

        self._animacao_entrada: Optional[QPropertyAnimation] = None

    def adicionar_conteudo(self, widget: QWidget) -> None:
        self._layout_conteudo.addWidget(widget)

    def adicionar_botao(self, botao: QPushButton) -> None:
        self._layout_botoes.addWidget(botao)

    def _criar_botao(self, texto: str, principal: bool = False) -> QPushButton:
        """Cria um botão estilo Win11: accent (principal) ou outline (secundário)."""
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
        super().showEvent(evento)
        self._centralizar_na_tela()
        self.raise_()
        self.activateWindow()
        self._iniciar_animacao_entrada()

    def _iniciar_animacao_entrada(self) -> None:
        """Fade-in suave (opacidade 0 -> 1) ao exibir o diálogo, em vez
        de a janela aparecer abruptamente na tela."""
        self.setWindowOpacity(0.0)
        self._animacao_entrada = QPropertyAnimation(self, b"windowOpacity", self)
        self._animacao_entrada.setDuration(140)
        self._animacao_entrada.setStartValue(0.0)
        self._animacao_entrada.setEndValue(1.0)
        self._animacao_entrada.setEasingCurve(QEasingCurve.OutCubic)
        self._animacao_entrada.start()

    def _centralizar_na_tela(self) -> None:
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
        if self._rotulo_aviso.isVisible():
            self._rotulo_aviso.setVisible(False)
            self.campo.setStyleSheet(_estilo_campo_texto(self.paleta))

    def _confirmar(self) -> None:
        self._valor = self.campo.text()
        self.accept()

    def valor(self) -> Optional[str]:
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
        return [linha.strip() for linha in self.campo.toPlainText().splitlines() if linha.strip()]

    def _atualizar_contador(self) -> None:
        total = len(self._extrair_linhas())
        sufixo = "pergunta detectada" if total == 1 else "perguntas detectadas"
        self._rotulo_contador.setText(f"{total} {sufixo}")

        if self._rotulo_aviso.isVisible():
            self._rotulo_aviso.setVisible(False)
            self.campo.setStyleSheet(_estilo_campo_texto(self.paleta))

    def _confirmar(self) -> None:
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
    """Exibe um diálogo Win11 multilinha. Retorna a lista de perguntas (não vazias), ou None se cancelado."""
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
    """Exibe um diálogo Win11 de confirmação (Sim/Não). Retorna True para 'Sim', False para 'Não'/cancelado."""
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


# Alias público da fonte padrão (Segoe UI Variable Text, com fallback
# para Segoe UI) - mesma função usada internamente pelos diálogos.
fonte_padrao = _fonte_padrao


# ============================================================================
# TESTE MANUAL (opcional)
# ============================================================================

if __name__ == "__main__":
    mostrar_aviso_win11(
        "TCC OpenDSS - Validacao do Modelo Computacional",
        "Teste manual do padrao visual Win11 (PySide6) do modulo de "
        "Validacao do Modelo Computacional.",
    )
