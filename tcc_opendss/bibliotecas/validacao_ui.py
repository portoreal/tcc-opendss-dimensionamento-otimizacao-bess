"""View: Módulo de Validação do Modelo Computacional (PySide6).

Interface do Módulo de Validação do Modelo Computacional, em PySide6, no
padrão visual Windows 11 / Fluent do projeto de referência
("gerenciamento_de_demandas"), reaproveitando a paleta e a fonte de
`ui_win11.py` — inclusive o accent azul institucional `#004587`, fixo nos
dois temas.

QUAL FONTE MANDA (distinção portada do texto de validação)
==========================================================
- Documentos oficiais do IEEE (.doc/.xls, pacotes `feederXX.zip`, da página
  de recursos do IEEE PES Distribution System Analysis Subcommittee) são o
  **gabarito oficial**.
- Arquivos de implementação em script OpenDSS (.dss, do repositório de
  distribuição de terceiros do ecossistema EPRI/OpenDSS) são o
  **instrumento de simulação**, sujeito a auditoria.

A distinção é o que dá sentido à etapa de validação: as divergências
encontradas (ver `validacao_ieee.py` e o memorial de cálculo) são da
implementação de terceiros frente ao gabarito oficial, não do processo de
simulação desenvolvido no TCC. Trocar a ordem das duas fontes inverteria a
conclusão do capítulo.

PROCESSO PRÓPRIO (SEM DOIS LAÇOS DE EVENTOS)
============================================
O menu do TCC é Tkinter e o validador é lançado a partir dele em processo
separado (`subprocess`). Este módulo, PySide6, roda com o seu próprio
QApplication, sem dividir o processo com o laço do Tkinter — a mesma
decisão arquitetural explicada em `validacao_lancador.py`.

RESPONSABILIDADES
=================
A lógica de validação — comparação numérica, exceções documentadas,
memorial de cálculo — fica inteira em `validacao_ieee.py`. Aqui só há
apresentação e interação:

- `abrir_dialogo_validacao(parent=None)`: ponto de entrada público (o nome
  é mantido porque `validacao_lancador` o chama assim).
- `ConfiguracaoValidacaoDialog`: seleção dos sistemas e da tolerância, com
  a validação rodando em `QThread`. A simulação OpenDSS leva segundos e,
  sem a thread, a janela congelaria durante toda a conta.
- `JanelaResultadosValidacao`: janela grande, não modal (padrão Win11, sem
  moldura nativa, cartão arredondado com sombra), com painel de resumo
  rolável, abas de memorial de cálculo e de topologia das redes, e a barra
  de botões (exportar Excel, exportar como projeto, salvar memorial,
  fechar).
"""

from __future__ import annotations

__author__ = 'Pedro Henrique Sousa Pinheiro'

import os
import tempfile
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QFile, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPixmap, QShortcut, QKeySequence, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import validacao_ieee
from .validacao_exportar_excel import exportar_validacao_excel
from .validacao_exportar_projeto import exportar_sistema_como_projeto
from .validacao_topologia import desenhar_topologia, salvar_topologia_png
from .ui_win11 import (
    RAIO_BORDA_CARTAO,
    _DialogoBaseWin11,
    _fonte_icones_disponivel,
    _garantir_app,
    _GLIFO_FECHAR,
    detectar_tema,
    fonte_padrao,
    mostrar_aviso_win11,
    obter_paleta_ativa,
    pedir_texto_win11,
)


def _parent_qt(parent):
    """Normaliza o `parent` recebido para um QWidget do PySide6, ou None.

    O menu principal do TCC é Tkinter e passa um `tk.Tk` como parent
    (ver validacao_lancador.abrir_validacao). Um objeto Tkinter NÃO é
    aceito pelo construtor do QDialog/QWidget do PySide6 (TypeError) —
    portanto qualquer parent que não seja um QWidget é descartado, e a
    janela é exibida sem parent (ela própria se centraliza na tela).
    """
    try:
        from PySide6.QtWidgets import QWidget
        return parent if isinstance(parent, QWidget) else None
    except Exception:  # noqa: BLE001
        return None


# Cores de status, semânticas e independentes do tema: verde aprovado,
# vermelho reprovado. São as mesmas usadas no resto da ferramenta, para que
# a decisão de aprovação tenha a mesma cor onde quer que apareça.
COR_STATUS = {
    "APROVADO": "#107C10",
    "REPROVADO": "#C42B1C",
    "PENDENTE": "#B25000",
    "ERRO": "#C42B1C",
}


# ============================================================================
# DIALOGO DE CONFIGURACAO DA VALIDACAO
# ============================================================================


class _ThreadValidacao(QThread):
    """Executa `executar_validacao` fora da thread da interface, para
    não congelar a janela durante a simulação OpenDSS (que pode levar
    dezenas de segundos nos sistemas de maior porte)."""

    progresso = Signal(str, int)   # (nome do sistema em processamento, índice 1..n)
    concluido = Signal(object)     # dict de resultados
    falhou = Signal(str)           # mensagem de erro

    def __init__(self, sistemas: list, tolerancia: float):
        super().__init__()
        self._sistemas = list(sistemas)
        self._tolerancia = float(tolerancia)

    def run(self) -> None:  # noqa: D401 (executado na thread secundária)
        try:
            resultados = {}
            total = len(self._sistemas)
            for indice, nome in enumerate(self._sistemas, start=1):
                self.progresso.emit(nome, indice)
                resultados[nome] = validacao_ieee.validar_sistema(
                    nome, self._tolerancia)
            self.concluido.emit(resultados)
        except Exception as e:  # noqa: BLE001 (reportado à interface)
            self.falhou.emit(str(e))


class ConfiguracaoValidacaoDialog(_DialogoBaseWin11):
    """Diálogo de configuração da validação: seleção dos sistemas IEEE e
    da tolerância de aprovação, com execução em thread secundária."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(
            "Validação do Modelo Computacional — Sistemas IEEE",
            largura=560, parent=_parent_qt(parent))

        self.resultado: Optional[dict] = None
        self._thread: Optional[_ThreadValidacao] = None

        self._montar_widgets()

    # ------------------------------------------------------------------ #
    def _montar_widgets(self) -> None:
        """Monta os controles: dica, sistemas, tolerância, progresso e botões."""
        paleta = self.paleta

        dica = QLabel(
            "Selecione os sistemas a validar e a tolerância de aprovação.",
            self)
        dica.setStyleSheet(f"color: {paleta.texto_secundario};")
        dica.setWordWrap(True)
        self.adicionar_conteudo(dica)

        # Uma caixa de seleção por sistema de referência, na ordem em que o
        # dicionário de sistemas as declara. Todas começam marcadas.
        self._checks: dict = {}
        for nome in validacao_ieee.SISTEMAS_DISPONIVEIS:
            e_derivado = "(corrigido)" in nome
            rotulo = f"{nome} — modelo derivado" if e_derivado else nome
            check = QCheckBox(rotulo, self)
            check.setChecked(True)
            check.setFont(fonte_padrao(10))
            # As entradas "(corrigido)" são modelos derivados: o script
            # original do IEEE foi ajustado para carregar no OpenDSS. Elas
            # aparecem em accent e com sufixo próprio para o usuário não
            # confundir o modelo derivado com o original - pendência
            # cosmética registrada no documento do projeto.
            if e_derivado:
                check.setStyleSheet(f"QCheckBox {{ color: {paleta.accent}; }}")
            else:
                check.setStyleSheet(f"QCheckBox {{ color: {paleta.texto_primario}; }}")
            self._checks[nome] = check
            self.adicionar_conteudo(check)

        # ---- Tolerância ----
        linha_tol = QWidget(self)
        layout_tol = QHBoxLayout(linha_tol)
        layout_tol.setContentsMargins(0, 8, 0, 0)
        layout_tol.setSpacing(8)

        rotulo_tol = QLabel("Tolerância de erro aceitável:", linha_tol)
        rotulo_tol.setStyleSheet(f"color: {paleta.texto_primario};")
        layout_tol.addWidget(rotulo_tol)

        self.spin_tolerancia = QDoubleSpinBox(linha_tol)
        self.spin_tolerancia.setRange(0.1, 2.0)
        self.spin_tolerancia.setSingleStep(0.1)
        self.spin_tolerancia.setDecimals(1)
        self.spin_tolerancia.setValue(0.5)
        self.spin_tolerancia.setSuffix(" %")
        self.spin_tolerancia.setFixedWidth(110)
        self.spin_tolerancia.setStyleSheet(
            f"""
            QDoubleSpinBox {{
                background-color: {paleta.fundo_campo};
                color: {paleta.texto_primario};
                border: 1px solid {paleta.borda_campo};
                border-radius: 5px;
                padding: 4px 6px;
            }}
            QDoubleSpinBox:focus {{ border: 1px solid {paleta.accent}; }}
            """)
        layout_tol.addWidget(self.spin_tolerancia)
        layout_tol.addStretch(1)
        self.adicionar_conteudo(linha_tol)

        # ---- Barra de progresso (oculta até executar) ----
        self.barra_progresso = QProgressBar(self)
        self.barra_progresso.setVisible(False)
        self.barra_progresso.setTextVisible(True)
        self.barra_progresso.setStyleSheet(
            f"""
            QProgressBar {{
                border: 1px solid {paleta.borda_campo};
                border-radius: 5px;
                background-color: {paleta.fundo_campo};
                color: {paleta.texto_primario};
                height: 18px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {paleta.accent};
                border-radius: 4px;
            }}
            """)
        self.adicionar_conteudo(self.barra_progresso)

        self._rotulo_progresso = QLabel("", self)
        self._rotulo_progresso.setStyleSheet(
            f"color: {paleta.texto_secundario};")
        self._rotulo_progresso.setWordWrap(True)
        self._rotulo_progresso.setVisible(False)
        self.adicionar_conteudo(self._rotulo_progresso)

        # ---- Botões ----
        self.botao_cancelar = self._criar_botao("Cancelar", principal=False)
        self.botao_cancelar.clicked.connect(self.reject)
        self.adicionar_botao(self.botao_cancelar)

        self.botao_executar = self._criar_botao(
            "Executar Validação", principal=True)
        self.botao_executar.setDefault(True)
        self.botao_executar.clicked.connect(self._executar)
        self.adicionar_botao(self.botao_executar)

    # ------------------------------------------------------------------ #
    def _sistemas_selecionados(self) -> list:
        """Lista os nomes dos sistemas com a caixa marcada."""
        return [nome for nome, check in self._checks.items() if check.isChecked()]

    def _executar(self) -> None:
        """Dispara a validação em thread separada, com os controles travados."""
        selecionados = self._sistemas_selecionados()
        if not selecionados:
            mostrar_aviso_win11(
                "Seleção inválida",
                "Selecione ao menos um sistema para validar.",
                parent=self)
            return

        tolerancia = float(self.spin_tolerancia.value())

        # Trava os controles e mostra o progresso enquanto a validação roda
        # na thread secundária. Mexer na seleção no meio da conta deixaria
        # a interface mostrando um resultado que não corresponde ao que está
        # marcado na tela.
        self._definir_controles_habilitados(False)
        self.barra_progresso.setRange(0, len(selecionados))
        self.barra_progresso.setValue(0)
        self.barra_progresso.setVisible(True)
        self._rotulo_progresso.setVisible(True)
        self._rotulo_progresso.setText("Iniciando validação...")

        self._thread = _ThreadValidacao(selecionados, tolerancia)
        self._thread.progresso.connect(self._ao_progredir)
        self._thread.concluido.connect(self._ao_concluir)
        self._thread.falhou.connect(self._ao_falhar)
        self._thread.start()

    def _definir_controles_habilitados(self, habilitado: bool) -> None:
        """Trava ou libera todos os controles de uma vez, durante a execução."""
        for check in self._checks.values():
            check.setEnabled(habilitado)
        self.spin_tolerancia.setEnabled(habilitado)
        self.botao_executar.setEnabled(habilitado)
        self.botao_cancelar.setEnabled(habilitado)

    # ------------------------------------------------------------------ #
    def _ao_progredir(self, nome: str, indice: int) -> None:
        """Sinal da thread: atualiza a barra com o sistema que acabou de rodar."""
        total = self.barra_progresso.maximum()
        self.barra_progresso.setValue(indice - 1)
        self._rotulo_progresso.setText(
            f"Validando: {nome} ({indice}/{total})")

    def _ao_concluir(self, resultados: dict) -> None:
        """Sinal da thread: abre a janela de resultados e fecha a configuração."""
        self.barra_progresso.setValue(self.barra_progresso.maximum())
        self._rotulo_progresso.setText("Validação concluída.")

        self.resultado = resultados

        # Abre a janela de resultados antes de fechar o diálogo, senão há um
        # instante sem nenhuma janela na tela.
        self.janela_resultados = JanelaResultadosValidacao(resultados)
        # O diálogo de configuração é modal (exec()); ao chamar accept()
        # abaixo ele é destruído e leva consigo a única referência Python a
        # esta janela top-level (parent=None, não modal). Sem a retenção em
        # `_janelas_resultado`, o coletor de lixo a levava junto e a janela
        # "piscava e fechava" - defeito já corrigido em otimizacao_ui e que,
        # por isso mesmo, reaparece se a lista for removida.
        _janelas_resultado.append(self.janela_resultados)
        # A topologia das redes grandes só é legível com a janela ocupando a
        # tela inteira; o ajuste da imagem fica a cargo do visualizador da
        # aba.
        self.janela_resultados.showMaximized()
        self.janela_resultados.raise_()
        self.janela_resultados.activateWindow()

        self.accept()

    def _ao_falhar(self, mensagem: str) -> None:
        """Sinal da thread: destrava os controles e mostra a mensagem de erro."""
        self._definir_controles_habilitados(True)
        self.barra_progresso.setVisible(False)
        self._rotulo_progresso.setVisible(False)
        mostrar_aviso_win11(
            "Erro na validação",
            f"Falha ao executar a validação:\n\n{mensagem}",
            parent=self)

    def reject(self) -> None:  # noqa: D102
        # Não fecha o diálogo enquanto uma validação está em curso — a
        # thread não deve ser abandonada com o diálogo destruído.
        if self._thread is not None and self._thread.isRunning():
            mostrar_aviso_win11(
                "Validação em andamento",
                "Aguarde a conclusão da validação antes de fechar.",
                parent=self)
            return
        super().reject()


# ============================================================================
# JANELA DE RESULTADOS (GRANDE, NAO MODAL)
# ============================================================================


class _BarraTituloJanela(QWidget):
    """Barra de título arrastável para a janela de resultados (QWidget,
    não modal). Variante local da barra de `ui_win11`, que é específica
    de QDialog — aqui o botão de fechar chama `close()`."""

    def __init__(self, titulo: str, janela: QWidget, paleta):
        super().__init__(janela)
        self._janela = janela
        self._paleta = paleta
        self._posicao_arraste = None

        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 0, 8, 0)
        layout.setSpacing(10)

        marca = QLabel("●", self)
        marca.setStyleSheet(f"color: {paleta.accent}; font-size: 10px;")
        layout.addWidget(marca)

        rotulo_titulo = QLabel(titulo, self)
        rotulo_titulo.setFont(fonte_padrao(11, negrito=True))
        rotulo_titulo.setStyleSheet(f"color: white;")
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
            botao_fechar.setFont(fonte_padrao(10))

        botao_fechar.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: white;
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
            """)
        botao_fechar.clicked.connect(janela.close)
        layout.addWidget(botao_fechar)

    def mousePressEvent(self, evento: QMouseEvent) -> None:
        if evento.button() == Qt.LeftButton:
            self._posicao_arraste = (
                evento.globalPosition().toPoint()
                - self._janela.frameGeometry().topLeft())
        super().mousePressEvent(evento)

    def mouseMoveEvent(self, evento: QMouseEvent) -> None:
        if self._posicao_arraste is not None and evento.buttons() & Qt.LeftButton:
            self._janela.move(
                evento.globalPosition().toPoint() - self._posicao_arraste)
        super().mouseMoveEvent(evento)

    def mouseReleaseEvent(self, evento: QMouseEvent) -> None:
        self._posicao_arraste = None
        super().mouseReleaseEvent(evento)


class _VisualizadorTopologia(QLabel):
    """Exibe o PNG da topologia ajustado à área visível (fit) e permite
    zoom com a roda do mouse ou com os botões do painel.

    Motivo: a topologia das redes maiores (34/37/123 barras) desenhada
    em tamanho natural não cabe na aba — o pesquisador precisava rolar
    nas duas direções e ainda assim não conseguia ler os rótulos. Aqui
    o padrão é a imagem inteira caber na aba, e a rolagem só aparece
    quando o usuário amplia de propósito.
    """

    ESCALA_MINIMA = 0.10
    ESCALA_MAXIMA = 8.0

    def __init__(self, caminho_png: str, parent: Optional[QWidget] = None):
        super().__init__(parent)

        from PySide6.QtCore import QEvent

        self._pixmap_original = QPixmap(caminho_png)
        self._escala = 1.0          # 1.0 = ajuste (fit) à área visível
        self._modo_ajuste = True
        self._viewport_observado = None

        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background: transparent;")
        # A rolagem é do QScrollArea que contém este rótulo; o tamanho
        # mínimo acompanha a imagem escalada para habilitá-la.
        self.setScaledContents(False)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(
            "Roda do mouse: aproximar/afastar (sobre o ponto do cursor)\n"
            "Arraste com o botão esquerdo: mover a imagem ampliada\n"
            "Duplo clique ou botão \"Ajustar\": voltar ao tamanho da aba")

        self._arrastando = False
        self._ponto_arraste = None
        self._evento_resize = QEvent.Type.Resize

        self._aplicar_escala()

    def observe_viewport(self, viewport) -> None:
        """Passa a recalcular o ajuste quando o viewport mudar de
        tamanho (ao maximizar a janela, trocar de aba, etc.)."""
        if viewport is None:
            return
        self._viewport_observado = viewport
        viewport.installEventFilter(self)
        self._aplicar_escala()

    def eventFilter(self, objeto, evento) -> bool:  # noqa: N802
        if (objeto is self._viewport_observado
                and evento.type() == self._evento_resize
                and self._modo_ajuste):
            self._aplicar_escala()
        return False

    # ------------------------------------------------------------------ #
    # API usada pela janela
    def tem_imagem(self) -> bool:
        return not self._pixmap_original.isNull()

    def ajustar(self) -> None:
        """Volta ao modo de ajuste: a imagem inteira cabe na aba."""
        self._modo_ajuste = True
        self._aplicar_escala()

    def ampliar(self, fator: float = 1.25) -> None:
        self._definir_escala(self._escala * fator)

    def reduzir(self, fator: float = 1.25) -> None:
        self._definir_escala(self._escala / fator)

    def tamanho_real(self) -> None:
        """Exibe a imagem em 1 pixel de tela por pixel do arquivo."""
        if self._pixmap_original.isNull():
            return
        self._escala = 1.0
        self._modo_ajuste = False
        self._aplicar_escala(tamanho_natural=True)

    # ------------------------------------------------------------------ #
    def _escala_de_ajuste(self) -> float:
        """Escala que faz a imagem inteira caber na área do QScrollArea
        (viewport), preservando a proporção."""
        if self._pixmap_original.isNull():
            return 1.0
        area = self._area_visivel()
        if area is None or area.width() <= 1 or area.height() <= 1:
            return 1.0
        largura_img = self._pixmap_original.width()
        altura_img = self._pixmap_original.height()
        if largura_img <= 0 or altura_img <= 0:
            return 1.0
        return min(area.width() / largura_img,
                   area.height() / altura_img)

    def _area_visivel(self):
        """Viewfinder do QScrollArea que contém este rótulo; na falta
        dele, a área do próprio pai."""
        pai = self.parentWidget()
        if isinstance(pai, QScrollArea):
            return pai.viewport()
        return pai

    def _aplicar_escala(self, escala: Optional[float] = None,
                        tamanho_natural: bool = False) -> None:
        if self._pixmap_original.isNull():
            self.setText("(imagem indisponível)")
            return

        if tamanho_natural:
            largura = self._pixmap_original.width()
            altura = self._pixmap_original.height()
        else:
            if escala is not None:
                self._escala = escala
            base = (self._escala_de_ajuste()
                    if self._modo_ajuste else self._escala)
            base = max(self.ESCALA_MINIMA, min(self.ESCALA_MAXIMA, base))
            if not self._modo_ajuste:
                self._escala = base
            largura = max(1, int(self._pixmap_original.width() * base))
            altura = max(1, int(self._pixmap_original.height() * base))
            self._escala = base

        pixmap = self._pixmap_original.scaled(
            largura, altura,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation)
        self.setPixmap(pixmap)
        # O tamanho mínimo do rótulo é o que faz o QScrollArea rolar quando
        # a imagem não cabe. No modo ajuste, ele nunca passa do viewport -
        # é o que mantém a barra de rolagem escondida até o usuário ampliar.
        self.setMinimumSize(pixmap.size())
        self.updateGeometry()

    def _definir_escala(self, nova_escala: float) -> None:
        """Aplica uma escala escolhida pelo usuário e sai do modo ajuste.

        Qualquer zoom manual desliga o ajuste automático: se a janela
        continuasse reajustando sozinha, o zoom do usuário seria desfeito no
        próximo redimensionamento.
        """
        if self._pixmap_original.isNull():
            return
        novo = max(self.ESCALA_MINIMA, min(self.ESCALA_MAXIMA, nova_escala))
        self._escala = novo
        self._modo_ajuste = False
        self._aplicar_escala(novo)

    # ------------------------------------------------------------------ #
    def resizeEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        """Refaz o ajuste quando a área visível muda de tamanho."""
        super().resizeEvent(evento)
        if self._modo_ajuste:
            self._aplicar_escala()

    def wheelEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        # Roda simples amplia; a rolagem vertical da aba fica com as
        # barras de rolagem e com o arraste da imagem.
        delta = evento.angleDelta().y()
        if delta == 0:
            super().wheelEvent(evento)
            return
        if delta > 0:
            self.ampliar()
        else:
            self.reduzir()
        evento.accept()

    def mouseDoubleClickEvent(self, evento) -> None:  # noqa: N802
        self.ajustar()
        evento.accept()

    def mousePressEvent(self, evento) -> None:  # noqa: N802
        if (evento.button() == Qt.LeftButton
                and not self._modo_ajuste):
            self._arrastando = True
            self._ponto_arraste = evento.pos()
            self.setCursor(Qt.ClosedHandCursor)
            evento.accept()
            return
        super().mousePressEvent(evento)

    def mouseMoveEvent(self, evento) -> None:  # noqa: N802
        area = self._area_visivel()
        if (self._arrastando and self._ponto_arraste is not None
                and isinstance(area, QWidget)):
            delta = evento.pos() - self._ponto_arraste
            barra_h = area.parentWidget().horizontalScrollBar() \
                if isinstance(area.parentWidget(), QScrollArea) else None
            barra_v = area.parentWidget().verticalScrollBar() \
                if isinstance(area.parentWidget(), QScrollArea) else None
            if barra_h is not None:
                barra_h.setValue(barra_h.value() - delta.x())
            if barra_v is not None:
                barra_v.setValue(barra_v.value() - delta.y())
            evento.accept()
            return
        super().mouseMoveEvent(evento)

    def mouseReleaseEvent(self, evento) -> None:  # noqa: N802
        if self._arrastando:
            self._arrastando = False
            self._ponto_arraste = None
            self.setCursor(Qt.PointingHandCursor)
            evento.accept()
            return
        super().mouseReleaseEvent(evento)


# Referências vivas das janelas de resultados em exibição.
#
# Uma janela top-level (parent=None) e não modal some assim que a última
# referência Python a ela desaparece: o coletor de lixo a leva junto, e o
# usuário vê a janela "piscar e fechar". É exatamente o que acontece com
# uma janela criada dentro de um diálogo modal aceito logo em seguida.
# Guardar a referência aqui até o sinal `destroyed` mantém a janela viva
# enquanto ela existe de fato.
_janelas_resultado = []


def _remover_janela_resultado(janela) -> None:
    """Descarta a referência de uma janela de resultados já destruída."""
    try:
        _janelas_resultado.remove(janela)
    except ValueError:
        pass


class JanelaResultadosValidacao(QWidget):
    """Janela de resultados: grande, não modal, no padrão Win11.

    Não modal para o usuário poder consultar o menu ou outra janela com os
    resultados abertos ao lado. Reúne o resumo por sistema, as abas de
    memorial de cálculo e de topologia das redes, e a barra de ações
    (exportar Excel, exportar projeto, salvar memorial, fechar).
    """

    def __init__(self, resultados: dict, parent: Optional[QWidget] = None):
        super().__init__(_parent_qt(parent))
        _garantir_app()

        self.resultados = resultados
        self.memorial_texto = validacao_ieee.gerar_memorial_validacao(resultados)
        self.paleta = obter_paleta_ativa(detectar_tema())

        # Caminhos dos PNGs temporários das topologias. Ficam registrados
        # para serem apagados ao fechar - a janela tem de limpar o que criou.
        self._caminhos_temp_topologia: list = []
        # Mapas auxiliares: nome do sistema -> objeto DSS, e nome do sistema
        # -> índice da sua aba de topologia no stacked widget.
        self._sistemas_com_dss: dict = {}
        self._indice_topologia_por_sistema: dict = {}
        # Um visualizador de topologia por sistema, na ordem de inserção no
        # stacked widget. É por esta lista que os botões de zoom sabem qual
        # imagem ampliar.
        self._visualizadores_topologia: list = []

        self._configurar_janela()
        self._montar_widgets()
        self._centralizar_na_tela()

        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.close)

    # ------------------------------------------------------------------ #
    def _configurar_janela(self) -> None:
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("Resultado da Validação do Modelo Computacional")
        self.setFont(fonte_padrao(10))

        largura = 1000
        tela = QApplication.primaryScreen()
        if tela is not None:
            geometria = tela.availableGeometry()
            largura = min(largura, geometria.width() - 40)
            altura = min(700, geometria.height() - 40)
        else:
            altura = 700
        self.resize(largura, altura)

    def _centralizar_na_tela(self) -> None:
        tela = QApplication.primaryScreen()
        if tela is None:
            return
        geometria = tela.availableGeometry()
        x = geometria.center().x() - self.width() // 2
        y = geometria.center().y() - self.height() // 2
        self.move(max(x, 0), max(y, 0))

    # ------------------------------------------------------------------ #
    def _montar_widgets(self) -> None:
        paleta = self.paleta

        layout_externo = QVBoxLayout(self)
        layout_externo.setContentsMargins(18, 18, 18, 18)

        self._cartao = QFrame(self)
        self._cartao.setObjectName("cartao_resultados")
        self._cartao.setStyleSheet(
            f"""
            QFrame#cartao_resultados {{
                background-color: {paleta.fundo_cartao};
                border: 1px solid {paleta.borda_cartao};
                border-radius: {RAIO_BORDA_CARTAO}px;
            }}
            """)
        sombra = QGraphicsDropShadowEffect(self._cartao)
        sombra.setBlurRadius(36)
        sombra.setXOffset(0)
        sombra.setYOffset(8)
        r, g, b, a = paleta.sombra_cor
        sombra.setColor(QColor(r, g, b, a))
        self._cartao.setGraphicsEffect(sombra)
        layout_externo.addWidget(self._cartao)

        layout_cartao = QVBoxLayout(self._cartao)
        layout_cartao.setContentsMargins(0, 0, 0, 0)
        layout_cartao.setSpacing(0)

        # ---- Cabeçalho (barra de título com fundo accent azul institucional) ----
        cabecalho = QFrame(self._cartao)
        cabecalho.setStyleSheet(
            f"""
            QFrame {{
                background-color: {paleta.accent};
                border-top-left-radius: {RAIO_BORDA_CARTAO}px;
                border-top-right-radius: {RAIO_BORDA_CARTAO}px;
            }}
            """)
        layout_cabecalho = QVBoxLayout(cabecalho)
        layout_cabecalho.setContentsMargins(0, 0, 0, 0)
        layout_cabecalho.setSpacing(0)
        layout_cabecalho.addWidget(_BarraTituloJanela(
            "Resultado da Validação do Modelo Computacional", self, paleta))
        layout_cartao.addWidget(cabecalho)

        # ---- Área de conteúdo ----
        area_conteudo = QWidget(self._cartao)
        layout_conteudo = QVBoxLayout(area_conteudo)
        layout_conteudo.setContentsMargins(18, 12, 18, 12)
        layout_conteudo.setSpacing(8)

        layout_conteudo.addWidget(self._montar_resumo())
        layout_conteudo.addWidget(self._montar_abas(), 1)
        layout_conteudo.addWidget(self._montar_barra_acoes())

        layout_cartao.addWidget(area_conteudo, 1)

    # ------------------------------------------------------------------ #
    def _montar_resumo(self) -> QWidget:
        """Painel de resumo rolável (altura limitada), com uma linha por
        sistema. Usa a mensagem SEM a nota do sistema — as notas
        integrais permanecem no memorial de cálculo (aba própria), de
        modo que o resumo não cresça sem limite."""
        paleta = self.paleta

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(180)
        scroll.setMinimumHeight(120)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 10px; margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {paleta.borda_campo};
                border-radius: 4px; min-height: 24px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            """)

        conteudo = QWidget()
        conteudo.setStyleSheet(f"background: transparent;")
        layout = QVBoxLayout(conteudo)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)

        for nome, resultado in self.resultados.items():
            status = resultado.get("status", "ERRO")
            cor = COR_STATUS.get(status, paleta.texto_primario)
            mensagem_resumo = str(resultado.get("mensagem", "")).split(" | NOTA:")[0].strip()

            erro = resultado.get("erro_maximo_pct")
            if erro is not None:
                erro_txt = f"erro máximo: {erro:.4f} %"
            else:
                erro_txt = "sem valor de erro apurado"

            rotulo = QLabel(
                f"[{status}] {nome} — {erro_txt} | {mensagem_resumo}", conteudo)
            rotulo.setStyleSheet(f"color: {cor}; background: transparent;")
            rotulo.setWordWrap(True)
            rotulo.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(rotulo)

        layout.addStretch(1)
        scroll.setWidget(conteudo)
        return scroll

    # ------------------------------------------------------------------ #
    def _montar_abas(self) -> QWidget:
        paleta = self.paleta

        self.abas = QTabWidget(self)
        self.abas.setStyleSheet(
            f"""
            QTabWidget::pane {{
                border: 1px solid {paleta.borda_cartao};
                border-radius: 6px;
                top: -1px;
            }}
            QTabBar::tab {{
                background: {paleta.botao_secundario_fundo};
                color: {paleta.texto_primario};
                padding: 6px 14px;
                border: 1px solid {paleta.borda_cartao};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {paleta.accent};
                color: white;
            }}
            """)

        self.abas.addTab(self._montar_aba_memorial(), "Memorial de Cálculo")
        self.abas.addTab(self._montar_aba_topologia(), "Topologia das Redes")
        return self.abas

    def _montar_aba_memorial(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        linha = QWidget(container)
        layout_linha = QHBoxLayout(linha)
        layout_linha.setContentsMargins(0, 0, 0, 0)

        rotulo = QLabel("Memorial de cálculo detalhado:", linha)
        rotulo.setFont(fonte_padrao(10, negrito=True))
        rotulo.setStyleSheet(f"color: {self.paleta.texto_primario};")
        layout_linha.addWidget(rotulo)
        layout_linha.addStretch(1)

        botao_salvar = self._criar_botao_secundario(
            "Salvar memorial (.txt)", linha)
        botao_salvar.clicked.connect(self._salvar_memorial)
        layout_linha.addWidget(botao_salvar)

        layout.addWidget(linha)

        self.area_memorial = QPlainTextEdit(container)
        self.area_memorial.setReadOnly(True)
        self.area_memorial.setPlainText(self.memorial_texto)
        fonte_mono = QFont("Consolas", 9)
        fonte_mono.setStyleHint(QFont.Monospace)
        self.area_memorial.setFont(fonte_mono)
        self.area_memorial.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.area_memorial.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background-color: {self.paleta.fundo_campo};
                color: {self.paleta.texto_primario};
                border: 1px solid {self.paleta.borda_cartao};
                border-radius: 5px;
            }}
            """)
        layout.addWidget(self.area_memorial, 1)
        return container

    # ------------------------------------------------------------------ #
    def _montar_aba_topologia(self) -> QWidget:
        paleta = self.paleta
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._sistemas_com_dss = {
            nome: resultado for nome, resultado in self.resultados.items()
            if resultado.get("objeto_dss") is not None
        }

        if not self._sistemas_com_dss:
            aviso = QLabel(
                "Nenhum sistema disponível para desenho de topologia "
                "(a simulação precisa ter sido executada com sucesso).",
                container)
            aviso.setStyleSheet(
                f"color: {paleta.texto_secundario}; font-style: italic;")
            aviso.setWordWrap(True)
            layout.addWidget(aviso)
            layout.addStretch(1)
            return container

        # ---- Seletor de sistema + pilha de imagens ----
        linha_sel = QWidget(container)
        layout_sel = QHBoxLayout(linha_sel)
        layout_sel.setContentsMargins(0, 0, 0, 0)
        rotulo_sel = QLabel("Sistema:", linha_sel)
        rotulo_sel.setStyleSheet(f"color: {paleta.texto_primario};")
        layout_sel.addWidget(rotulo_sel)

        self.combo_sistema = QComboBox(linha_sel)
        self.combo_sistema.setStyleSheet(
            f"""
            QComboBox {{
                background-color: {paleta.fundo_campo};
                color: {paleta.texto_primario};
                border: 1px solid {paleta.borda_campo};
                border-radius: 5px;
                padding: 4px 8px;
            }}
            QComboBox:focus {{ border: 1px solid {paleta.accent}; }}
            QComboBox QAbstractItemView {{
                background-color: {paleta.fundo_campo};
                color: {paleta.texto_primario};
                selection-background-color: {paleta.accent};
                selection-color: white;
            }}
            """)
        layout_sel.addWidget(self.combo_sistema, 1)

        # ---- Controles de zoom da topologia ----
        botao_menos = self._criar_botao_secundario("−", linha_sel)
        botao_menos.setToolTip("Afastar (reduzir o zoom)")
        botao_menos.clicked.connect(
            lambda: self._com_visualizador_atual(lambda v: v.reduzir()))
        layout_sel.addWidget(botao_menos)

        botao_mais = self._criar_botao_secundario("+", linha_sel)
        botao_mais.setToolTip("Aproximar (aumentar o zoom)")
        botao_mais.clicked.connect(
            lambda: self._com_visualizador_atual(lambda v: v.ampliar()))
        layout_sel.addWidget(botao_mais)

        botao_real = self._criar_botao_secundario("100 %", linha_sel)
        botao_real.setToolTip(
            "Tamanho real (1 pixel da imagem por pixel da tela)")
        botao_real.clicked.connect(
            lambda: self._com_visualizador_atual(lambda v: v.tamanho_real()))
        layout_sel.addWidget(botao_real)

        botao_ajustar = self._criar_botao_secundario("Ajustar", linha_sel)
        botao_ajustar.setToolTip(
            "Ajustar a imagem inteira à área visível (padrão)")
        botao_ajustar.clicked.connect(
            lambda: self._com_visualizador_atual(lambda v: v.ajustar()))
        layout_sel.addWidget(botao_ajustar)

        layout.addWidget(linha_sel)

        self.stack_topologia = QStackedWidget(container)
        layout.addWidget(self.stack_topologia, 1)

        for nome_sistema, resultado in self._sistemas_com_dss.items():
            objeto_dss = resultado["objeto_dss"]

            barras_destacadas = {
                str(barra).upper(): "#d62728"
                for barra in resultado.get("excecoes_documentadas", {})
            }

            pagina = QWidget(self.stack_topologia)
            layout_pagina = QVBoxLayout(pagina)
            layout_pagina.setContentsMargins(0, 0, 0, 0)

            try:
                figura = desenhar_topologia(
                    objeto_dss, nome_sistema, barras_destacadas)
                caminho_png = self._salvar_png_temporario(figura, nome_sistema)
                self._fechar_figura(figura)
            except Exception as e:  # noqa: BLE001 (exibido na própria aba)
                erro = QLabel(
                    f"Não foi possível desenhar a topologia:\n{e}", pagina)
                erro.setStyleSheet(f"color: {COR_STATUS['ERRO']};")
                erro.setWordWrap(True)
                layout_pagina.addWidget(erro)
                layout_pagina.addStretch(1)
                self.stack_topologia.addWidget(pagina)
                continue

            scroll_img = QScrollArea(pagina)
            scroll_img.setWidgetResizable(True)
            scroll_img.setFrameShape(QFrame.NoFrame)
            scroll_img.setStyleSheet(
                f"QScrollArea {{ background-color: {paleta.fundo_campo};"
                f" border: 1px solid {paleta.borda_cartao};"
                f" border-radius: 5px; }}")


            rotulo_img = _VisualizadorTopologia(caminho_png, scroll_img)
            scroll_img.setWidget(rotulo_img)
            # Recalcula o ajuste quando a aba mudar de tamanho.
            rotulo_img.observe_viewport(scroll_img.viewport())
            # A rolagem só faz sentido ampliado: no ajuste (padrão) a
            # imagem cabe inteira na aba.
            scroll_img.setWidgetResizable(True)

            layout_pagina.addWidget(scroll_img, 1)
            self.stack_topologia.addWidget(pagina)

            self._visualizadores_topologia.append(rotulo_img)
            self._indice_topologia_por_sistema[nome_sistema] = (
                self.stack_topologia.count() - 1)
            self.combo_sistema.addItem(nome_sistema)

        self.combo_sistema.currentTextChanged.connect(self._trocar_topologia)
        return container

    def _trocar_topologia(self, nome_sistema: str) -> None:
        indice = self._indice_topologia_por_sistema.get(nome_sistema)
        if indice is not None:
            self.stack_topologia.setCurrentIndex(indice)
            visualizador = self._visualizadores_topologia[indice] \
                if indice < len(self._visualizadores_topologia) else None
            if visualizador is not None:
                # Força o recálculo do ajuste no novo tamanho visível.
                visualizador.ajustar()

    def _com_visualizador_atual(self, funcao) -> None:
        """Aplica uma ação de zoom ao visualizador da aba corrente."""
        indice = self.stack_topologia.currentIndex()
        if 0 <= indice < len(self._visualizadores_topologia):
            funcao(self._visualizadores_topologia[indice])

    def _salvar_png_temporario(self, figura, nome_sistema: str) -> str:
        """Salva a figura da topologia em arquivo temporário e registra
        o caminho para remoção ao fechar a janela."""
        nome_limpo = "".join(
            c if (c.isalnum() or c in "-_") else "_"
            for c in nome_sistema.replace("IEEE ", ""))
        pasta = tempfile.gettempdir()
        caminho = os.path.join(
            pasta, f"validacao_topologia_{nome_limpo}.png")
        # 200 dpi: o pesquisador amplia para ler rótulos de barra, e a
        # 150 dpi os textos já ficavam serrilhados em zoom.
        salvar_topologia_png(figura, caminho, dpi=200)
        self._caminhos_temp_topologia.append(caminho)
        return caminho

    @staticmethod
    def _fechar_figura(figura) -> None:
        """Fecha a figura do matplotlib para liberar memória (import
        tardio — o matplotlib só é necessário quando há topologia)."""
        try:
            import matplotlib.pyplot as plt
            plt.close(figura)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    def _montar_barra_acoes(self) -> QWidget:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(8)

        self._rotulo_exportar = QLabel("Sistema para exportar:", container)
        self._rotulo_exportar.setStyleSheet(
            f"color: {self.paleta.texto_secundario};")
        layout.addWidget(self._rotulo_exportar)

        self.combo_exportar = QComboBox(container)
        self.combo_exportar.setStyleSheet(
            f"""
            QComboBox {{
                background-color: {self.paleta.fundo_campo};
                color: {self.paleta.texto_primario};
                border: 1px solid {self.paleta.borda_campo};
                border-radius: 5px;
                padding: 4px 8px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {self.paleta.fundo_campo};
                color: {self.paleta.texto_primario};
                selection-background-color: {self.paleta.accent};
                selection-color: white;
            }}
            """)
        for nome in self._sistemas_com_dss:
            self.combo_exportar.addItem(nome)
        self.combo_exportar.setVisible(bool(self._sistemas_com_dss))
        self._rotulo_exportar.setVisible(bool(self._sistemas_com_dss))
        layout.addWidget(self.combo_exportar)

        layout.addStretch(1)

        botao_excel = self._criar_botao_secundario(
            "Exportar Excel", container)
        botao_excel.clicked.connect(self._exportar_excel)
        layout.addWidget(botao_excel)

        botao_projeto = self._criar_botao_secundario(
            "Exportar como Projeto", container)
        botao_projeto.setVisible(bool(self._sistemas_com_dss))
        botao_projeto.clicked.connect(self._exportar_como_projeto)
        layout.addWidget(botao_projeto)

        botao_fechar = self._criar_botao_principal("Fechar", container)
        botao_fechar.clicked.connect(self.close)
        layout.addWidget(botao_fechar)

        return container

    def _criar_botao_principal(self, texto: str, parent: QWidget) -> QPushButton:
        paleta = self.paleta
        botao = QPushButton(texto, parent)
        botao.setFixedHeight(32)
        botao.setMinimumWidth(110)
        botao.setCursor(Qt.PointingHandCursor)
        botao.setFont(fonte_padrao(10))
        botao.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {paleta.accent};
                color: white;
                border: none;
                border-radius: 6px;
            }}
            QPushButton:hover {{ background-color: {paleta.accent_hover}; }}
            QPushButton:pressed {{ background-color: {paleta.accent_pressed}; }}
            """)
        return botao

    def _criar_botao_secundario(self, texto: str, parent: QWidget) -> QPushButton:
        paleta = self.paleta
        botao = QPushButton(texto, parent)
        botao.setFixedHeight(32)
        botao.setCursor(Qt.PointingHandCursor)
        botao.setFont(fonte_padrao(10))
        botao.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {paleta.botao_secundario_fundo};
                color: {paleta.texto_primario};
                border: 1px solid {paleta.borda_campo};
                border-radius: 6px;
                padding: 0 12px;
            }}
            QPushButton:hover {{ background-color: {paleta.botao_secundario_hover}; }}
            QPushButton:pressed {{ background-color: {paleta.botao_secundario_pressed}; }}
            """)
        return botao

    # ------------------------------------------------------------------ #
    # AÇÕES
    # ------------------------------------------------------------------ #
    def _exportar_excel(self) -> None:
        nome_sugerido = (
            "validacao_ieee_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + ".xlsx")
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Exportar resultados da validação (Excel)",
            nome_sugerido, "Planilha Excel (*.xlsx)")
        if not caminho:
            return
        if not caminho.lower().endswith(".xlsx"):
            caminho += ".xlsx"

        try:
            exportar_validacao_excel(
                self.resultados, self.memorial_texto, caminho)
        except Exception as e:  # noqa: BLE001 (reportado ao usuário)
            mostrar_aviso_win11(
                "Erro ao exportar",
                f"Não foi possível gerar a planilha Excel:\n\n{e}",
                parent=self)
            return

        mostrar_aviso_win11(
            "Exportação concluída",
            f"Resultados exportados com sucesso para:\n{caminho}",
            parent=self)

    def _salvar_memorial(self) -> None:
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar memorial de validação",
            "memorial_validacao_ieee.txt", "Arquivo de texto (*.txt)")
        if not caminho:
            return
        if not caminho.lower().endswith(".txt"):
            caminho += ".txt"

        try:
            with open(caminho, "w", encoding="utf-8") as arquivo:
                arquivo.write(self.memorial_texto)
        except Exception as e:  # noqa: BLE001 (reportado ao usuário)
            mostrar_aviso_win11(
                "Erro ao salvar",
                f"Não foi possível salvar o memorial:\n\n{e}",
                parent=self)
            return

        mostrar_aviso_win11(
            "Memorial salvo",
            f"Memorial de cálculo salvo em:\n{caminho}",
            parent=self)

    def _exportar_como_projeto(self) -> None:
        """Converte a topologia simulada em um novo Projeto editável.

        TRANSPARÊNCIA TÉCNICA: a exportação cria o projeto no disco
        (rede.json, curvas, etc.). O Editor de Rede Elétrica é Tkinter e
        pertence ao menu principal — portanto NÃO é aberto a partir
        desta janela PySide6 (dois event loops no mesmo processo). O
        aviso informa onde o projeto foi criado, para que o usuário o
        abra pelo menu principal.
        """
        nome_sistema = self.combo_exportar.currentText()
        resultado = self.resultados.get(nome_sistema)
        objeto_dss = resultado.get("objeto_dss") if resultado else None
        if objeto_dss is None:
            mostrar_aviso_win11(
                "Aviso",
                "Não há circuito simulado disponível para este sistema.",
                parent=self)
            return

        nome_sugerido = nome_sistema.replace("IEEE ", "").replace(" ", "_")
        nome_projeto = pedir_texto_win11(
            "Novo Projeto a partir do sistema IEEE",
            "Nome do novo projeto:",
            texto_padrao=nome_sugerido,
            parent=self)
        if not nome_projeto:
            return

        try:
            projeto = exportar_sistema_como_projeto(objeto_dss, nome_projeto)
        except Exception as e:  # noqa: BLE001 (reportado ao usuário)
            mostrar_aviso_win11(
                "Erro ao exportar",
                f"Não foi possível converter o sistema em projeto:\n\n{e}",
                parent=self)
            return

        mostrar_aviso_win11(
            "Projeto criado",
            f"Projeto '{projeto.nome}' criado com sucesso em:\n"
            f"{projeto.caminho_raiz}\n\n"
            "Abra-o pelo menu principal (Editor de Rede Elétrica).\n\n"
            "Observações de modelagem (ver validacao_exportar_projeto.py):\n"
            "  - A fase específica (A/B/C) de cargas monofásicas/bifásicas\n"
            "    não é preservada, apenas a quantidade de fases;\n"
            "  - Bancos de reguladores foram convertidos em transformadores\n"
            "    de impedância mínima, SEM regulação automática de tensão;\n"
            "  - A impedância das linhas foi aproximada pela média dos\n"
            "    elementos próprios da matriz original.",
            parent=self)

    # ------------------------------------------------------------------ #
    def closeEvent(self, evento) -> None:  # noqa: N802
        """Remove os PNGs temporários de topologia ao fechar a janela."""
        for caminho in self._caminhos_temp_topologia:
            try:
                if os.path.exists(caminho):
                    os.remove(caminho)
            except OSError:
                pass
        self._caminhos_temp_topologia = []
        # Libera a retenção de módulo (ver `_janelas_resultado`): sem isso
        # a janela fechada continuaria viva em memória. `destroyed` não
        # serve aqui — só é emitido na destruição do objeto C++, e um
        # widget top-level fechado por close() sem WA_DeleteOnClose
        # permanece alocado.
        _remover_janela_resultado(self)
        super().closeEvent(evento)


# ============================================================================
# API PUBLICA
# ============================================================================


def abrir_dialogo_validacao(parent=None) -> None:
    """Ponto de entrada público do módulo de validação (nome mantido por
    compatibilidade com `validacao_lancador`).

    Exibe o diálogo de configuração; ao executar, a validação roda em
    thread secundária e, ao concluir, a janela de resultados é aberta.

    TRANSPARÊNCIA TÉCNICA: o menu principal do TCC é Tkinter e chama esta
    função passando um `tk.Tk` como `parent`. Como esta interface é
    PySide6, qualquer parent que não seja um QWidget é descartado
    automaticamente (ver `_parent_qt`) — evita TypeError ao misturar os
    dois toolkits. Idealmente este módulo roda em processo próprio
    (subprocess lançado pelo menu), com o seu próprio QApplication.
    """
    _garantir_app()
    dialogo = ConfiguracaoValidacaoDialog(parent)
    dialogo.exec()


# Compatibilidade com o nome anterior (Tkinter) da janela de resultados.
ResultadosValidacaoDialog = JanelaResultadosValidacao
