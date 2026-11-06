__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Diálogo de seleção e criação de Projeto.

O menu principal chama esta janela antes de abrir o Editor de Rede ou o
Módulo de Dimensionamento, porque os dois precisam de um projeto - a pasta
com as curvas, a rede e os modelos já dimensionados. O usuário escolhe um
projeto existente da lista, cria um novo pelo nome, ou aponta para uma
pasta já montada fora da lista.

Contrato público congelado: `selecionar_projeto(parent) -> Projeto | None`.
None significa que o usuário desistiu, e o menu não deve abrir nada.
"""

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .projeto import (
    Projeto,
    abrir_projeto_por_caminho,
    criar_ou_abrir_projeto_por_nome,
    listar_projetos,
)
from .ui_win11 import (
    RAIO_BORDA_BOTAO,
    detectar_tema,
    fonte_padrao,
    obter_paleta_ativa,
    pedir_texto_win11,
)


class _DialogoSelecionarProjeto(QDialog):
    """Diálogo modal de seleção e criação de projeto.

    Modal porque o menu não tem o que fazer enquanto a escolha não sai - a
    próxima tela depende dela.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.projeto_selecionado: Optional[Projeto] = None

        self.setWindowTitle("Selecionar Projeto")
        self.setModal(True)
        self.setFont(fonte_padrao(10))

        self._paleta = obter_paleta_ativa(detectar_tema())
        self._montar_interface()

    # ------------------------------------------------------------------
    # Construção da interface
    # ------------------------------------------------------------------
    def _montar_interface(self) -> None:
        """Monta lista, botões auxiliares e barra OK/Cancelar.

        Tudo é estilizado à mão via QSS (o equivalente Qt de CSS) porque o
        tema nativo do Windows não entrega o padrão visual do projeto.
        """
        paleta = self._paleta

        self.setStyleSheet(
            f"""
            QDialog {{ background-color: {paleta.fundo_cartao}; }}
            QLabel {{ color: {paleta.texto_primario}; }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        rotulo = QLabel("Projetos existentes (duplo clique para abrir):", self)
        rotulo.setFont(fonte_padrao(9, True))
        layout.addWidget(rotulo)

        self.lista = QListWidget(self)
        self.lista.setFont(fonte_padrao(10))
        self.lista.setMinimumSize(420, 240)
        self.lista.setSelectionMode(QAbstractItemView.SingleSelection)
        self.lista.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {paleta.fundo_campo};
                color: {paleta.texto_primario};
                border: 1px solid {paleta.borda_campo};
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {paleta.accent};
                color: #FFFFFF;
            }}
            """
        )
        for nome in listar_projetos():
            self.lista.addItem(QListWidgetItem(nome))
        # Duplo clique é atalho de quem já sabe o que quer; o caminho
        # completo (selecionar e clicar OK) continua valendo.
        self.lista.itemDoubleClicked.connect(self._abrir_item_duplo_clique)
        layout.addWidget(self.lista, 1)

        linha_botoes_aux = QHBoxLayout()
        linha_botoes_aux.setContentsMargins(0, 0, 0, 0)
        linha_botoes_aux.setSpacing(8)

        botao_novo = QPushButton("➕ Novo Projeto", self)
        botao_novo.clicked.connect(self._novo_projeto)
        botao_pasta = QPushButton("📁 Selecionar pasta existente...", self)
        botao_pasta.clicked.connect(self._selecionar_pasta)
        for botao in (botao_novo, botao_pasta):
            botao.setFont(fonte_padrao(10))
            botao.setFixedHeight(32)
            botao.setCursor(Qt.PointingHandCursor)
            botao.setStyleSheet(self._estilo_botao_secundario())
        linha_botoes_aux.addWidget(botao_novo)
        linha_botoes_aux.addWidget(botao_pasta)
        linha_botoes_aux.addStretch(1)
        layout.addLayout(linha_botoes_aux)

        botoes = QDialogButtonBox(self)
        self._botao_ok = botoes.addButton(QDialogButtonBox.Ok)
        botao_cancelar = botoes.addButton(QDialogButtonBox.Cancel)
        self._botao_ok.setText("OK")
        botao_cancelar.setText("Cancelar")
        for botao, principal in ((self._botao_ok, True), (botao_cancelar, False)):
            botao.setFont(fonte_padrao(10))
            botao.setFixedHeight(32)
            botao.setMinimumWidth(100)
            botao.setCursor(Qt.PointingHandCursor)
            botao.setStyleSheet(
                self._estilo_botao_principal() if principal else self._estilo_botao_secundario()
            )
        botoes.accepted.connect(self._confirmar_selecao)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

        # OK exige um item selecionado. Desabilitar o botão é mais claro do
        # que deixar clicar e responder com mensagem de erro depois.
        self.lista.itemSelectionChanged.connect(self._atualizar_estado_ok)
        self._atualizar_estado_ok()

        if self.lista.count() > 0:
            self.lista.setCurrentRow(0)
        self._botao_ok.setDefault(True)
        self._botao_ok.setAutoDefault(True)
        botao_cancelar.setAutoDefault(False)
        self.lista.setFocus()

    def _estilo_botao_principal(self) -> str:
        paleta = self._paleta
        return f"""
            QPushButton {{
                background-color: {paleta.accent};
                color: #FFFFFF;
                border: none;
                border-radius: {RAIO_BORDA_BOTAO}px;
                padding: 0 14px;
            }}
            QPushButton:hover {{ background-color: {paleta.accent_hover}; }}
            QPushButton:pressed {{ background-color: {paleta.accent_pressed}; }}
            QPushButton:disabled {{
                background-color: {paleta.borda_cartao};
                color: {paleta.texto_secundario};
            }}
        """

    def _estilo_botao_secundario(self) -> str:
        paleta = self._paleta
        return f"""
            QPushButton {{
                background-color: {paleta.botao_secundario_fundo};
                color: {paleta.texto_primario};
                border: 1px solid {paleta.borda_campo};
                border-radius: {RAIO_BORDA_BOTAO}px;
                padding: 0 14px;
            }}
            QPushButton:hover {{ background-color: {paleta.botao_secundario_hover}; }}
            QPushButton:pressed {{ background-color: {paleta.botao_secundario_pressed}; }}
        """

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------
    def _atualizar_estado_ok(self) -> None:
        """Liga o botão OK apenas quando há item selecionado."""
        self._botao_ok.setEnabled(bool(self.lista.selectedItems()))

    def _abrir_item_duplo_clique(self, _item: QListWidgetItem) -> None:
        """Duplo clique na lista equivale a selecionar e aceitar."""
        self._confirmar_selecao()

    def _confirmar_selecao(self) -> None:
        selecionados: List[QListWidgetItem] = self.lista.selectedItems()
        if not selecionados:
            # Defesa extra: o botão OK já fica desabilitado sem seleção,
            # mas o Enter no atalho padrão do diálogo chega aqui sem passar
            # pelo estado do botão.
            return
        nome = selecionados[0].text()
        self.projeto_selecionado = criar_ou_abrir_projeto_por_nome(nome)
        self.accept()

    def _novo_projeto(self) -> None:
        nome = pedir_texto_win11(
            "Novo Projeto",
            "Nome do novo projeto:",
            parent=self,
            tema=detectar_tema(),
        )
        # String vazia = o usuário confirmou sem digitar nada; tratar como
        # desistência mantém o diálogo aberto.
        if not nome:
            return
        self.projeto_selecionado = criar_ou_abrir_projeto_por_nome(nome)
        self.accept()

    def _selecionar_pasta(self) -> None:
        caminho = QFileDialog.getExistingDirectory(
            self, "Selecione a pasta do projeto", ""
        )
        if not caminho:
            # Cancelar o filedialog devolve string vazia. Fechar junto toda
            # a seleção seria perder o trabalho por engano.
            return
        self.projeto_selecionado = abrir_projeto_por_caminho(caminho)
        self.accept()


def selecionar_projeto(parent: Optional[QWidget]) -> Optional[Projeto]:
    """Abre o diálogo modal e devolve o Projeto escolhido.

    Devolve None se o usuário cancelar ou fechar a janela - o chamador deve
    tratar isso como "não abrir nada".
    """
    dialogo = _DialogoSelecionarProjeto(parent)
    dialogo.exec()
    return dialogo.projeto_selecionado
