__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Diálogo genérico reutilizável (Entry + Combobox + botão de gráfico
dinâmicos), usado pelo Editor de Rede e pelo Módulo de Dimensionamento.

Port Tkinter -> PySide6 (onda 1 da migração). O CONTRATO PÚBLICO é
congelado e consumido por outros módulos: apenas `pedir_valores` é público.

TRANSPARÊNCIA TÉCNICA (divergências em relação ao código Tk anterior):
- O widget interno `FormularioElemento` (subclasse de simpledialog.Dialog)
  foi substituído por `_DialogoValores`, subclasse de QDialog. Ele existia
  no Tk apenas como detalhe de implementação; nenhum consumidor o
  instanciava diretamente (o único ponto de entrada usado era
  `pedir_valores`). O comportamento observável foi preservado.
- A exibição do campo "botao_grafico" é um QLineEdit SOMENTE LEITURA; o
  retorno continua sendo a string exibida (inclusive "Nenhuma"), igual ao
  `StringVar.get()` do Tk.
"""

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .ui_win11 import (
    RAIO_BORDA_BOTAO,
    detectar_tema,
    fonte_padrao,
    obter_paleta_ativa,
)


# Texto exibido quando o campo "botao_grafico" ainda não tem valor
# escolhido - mesmo literal usado pelo StringVar do código Tk original.
_TEXTO_SEM_VALOR = "Nenhuma"


class _DialogoValores(QDialog):
    """Formulário modal gerado a partir da lista de campos.

    `campos` é uma sequência de tuplas ``(chave, rotulo, tipo, valor_padrao)``
    onde ``tipo`` é "texto", "combobox" ou "botao_grafico":

    - "texto": ``valor_padrao`` é o texto inicial do QLineEdit.
    - "combobox": ``valor_padrao`` é a LISTA de opções (lista vazia/None
      vira ``[""]``). O valor inicial é ``valores_iniciais[chave]`` se ele
      estiver entre as opções; caso contrário, a primeira opção.
    - "botao_grafico": ``valor_padrao`` é um CALLBACK
      ``(parent_dialog, valor_atual_str) -> novo_valor | None``.
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        titulo: str,
        campos: Sequence[Tuple[str, str, str, Any]],
        valores_iniciais: Optional[Dict[str, Any]] = None,
        dica: Optional[str] = None,
    ):
        super().__init__(parent)
        self.campos = campos
        self.valores_iniciais = valores_iniciais or {}
        self.dica = dica
        self.resultado: Optional[Dict[str, str]] = None

        # Referência para cada chave: ("texto", QLineEdit) /
        # ("combobox", QComboBox) / ("botao_grafico", QLineEdit).
        self.widgets: Dict[str, Tuple[str, QWidget]] = {}

        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setFont(fonte_padrao(10))

        self._paleta = obter_paleta_ativa(detectar_tema())
        self._montar_interface(titulo)

    # ------------------------------------------------------------------
    # Construção da interface
    # ------------------------------------------------------------------
    def _montar_interface(self, titulo: str) -> None:
        paleta = self._paleta

        self.setStyleSheet(
            f"""
            QDialog {{ background-color: {paleta.fundo_cartao}; }}
            QLabel {{ color: {paleta.texto_primario}; }}
            """
        )

        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(16, 16, 16, 16)
        layout_principal.setSpacing(10)

        # Dica no topo: texto pequeno em itálico (equivalente ao Label Tk).
        if self.dica:
            rotulo_dica = QLabel(self.dica, self)
            rotulo_dica.setWordWrap(True)
            rotulo_dica.setFont(fonte_padrao(8))
            rotulo_dica.setStyleSheet(
                f"color: {paleta.texto_secundario}; font-style: italic;"
                " background: transparent;"
            )
            layout_principal.addWidget(rotulo_dica)

        formulario = QFormLayout()
        formulario.setContentsMargins(0, 0, 0, 0)
        formulario.setHorizontalSpacing(10)
        formulario.setVerticalSpacing(6)
        formulario.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        primeiro_campo: Optional[QLineEdit] = None

        for chave, rotulo, tipo, valor_padrao in self.campos:
            rotulo_widget = QLabel(rotulo, self)
            rotulo_widget.setFont(fonte_padrao(10))

            if tipo == "combobox":
                widget = self._criar_combobox(chave, valor_padrao)
                self.widgets[chave] = ("combobox", widget)
            elif tipo == "botao_grafico":
                widget = self._criar_botao_grafico(chave, valor_padrao)
                self.widgets[chave] = ("botao_grafico", widget)
            else:  # "texto" (padrão; qualquer tipo desconhecido cai aqui,
                # como no Tk, que usava o mesmo `else`)
                widget = QLineEdit(self)
                widget.setFont(fonte_padrao(10))
                widget.setMinimumWidth(220)
                valor_atual = self.valores_iniciais.get(chave, valor_padrao)
                widget.setText("" if valor_atual is None else str(valor_atual))
                self.widgets[chave] = ("texto", widget)
                if primeiro_campo is None:
                    primeiro_campo = widget

            formulario.addRow(rotulo_widget, widget)

        layout_principal.addLayout(formulario)
        layout_principal.addSpacing(4)

        botoes = QDialogButtonBox(self)
        botoes.setCenterButtons(False)
        botao_ok = botoes.addButton(QDialogButtonBox.Ok)
        botao_cancelar = botoes.addButton(QDialogButtonBox.Cancel)
        botao_ok.setText("OK")
        botao_cancelar.setText("Cancelar")
        for botao, principal in ((botao_ok, True), (botao_cancelar, False)):
            botao.setFont(fonte_padrao(10))
            botao.setFixedHeight(32)
            botao.setMinimumWidth(100)
            botao.setCursor(Qt.PointingHandCursor)
            botao.setStyleSheet(self._estilo_botao(principal))
        botoes.accepted.connect(self._coletar_e_aceitar)
        botoes.rejected.connect(self.reject)
        layout_principal.addWidget(botoes)

        # Enter no último campo de texto equivale a OK (comportamento do
        # simpledialog.Dialog do Tk, que ligava <Return> ao botão OK).
        # QPushButton.setDefault() é o que liga o Enter ao botão; o foco
        # inicial fica no primeiro campo para o usuário já digitar.
        botao_ok.setDefault(True)
        botao_ok.setAutoDefault(True)
        botao_cancelar.setAutoDefault(False)
        if primeiro_campo is not None:
            primeiro_campo.setFocus()

    def _estilo_botao(self, principal: bool) -> str:
        paleta = self._paleta
        if principal:
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

    def _criar_combobox(self, chave: str, valor_padrao: Any) -> QComboBox:
        paleta = self._paleta

        # Lista de opções: lista vazia/None -> [""] (mesma semântica Tk).
        opcoes: List[str] = [str(opcao) for opcao in valor_padrao] if valor_padrao else [""]

        combo = QComboBox(self)
        combo.setFont(fonte_padrao(10))
        combo.setMinimumWidth(220)
        combo.setEditable(False)  # sinônimo visual do state="readonly"
        combo.addItems(opcoes)
        combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: {paleta.fundo_campo};
                color: {paleta.texto_primario};
                border: 1px solid {paleta.borda_campo};
                border-radius: 4px;
                padding: 3px 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {paleta.fundo_campo};
                color: {paleta.texto_primario};
                selection-background-color: {paleta.accent};
                selection-color: #FFFFFF;
            }}
            """
        )

        valor_inicial = self.valores_iniciais.get(chave)
        if valor_inicial is not None and str(valor_inicial) in opcoes:
            combo.setCurrentIndex(opcoes.index(str(valor_inicial)))
        else:
            # Valor inicial ausente ou fora das opções: cai na primeira
            # opção, exatamente como o `widget.set(...)` do Tk original.
            combo.setCurrentIndex(0)
        return combo

    def _criar_botao_grafico(self, chave: str, callback: Callable) -> QLineEdit:
        paleta = self._paleta

        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        exibicao = QLineEdit(container)
        exibicao.setFont(fonte_padrao(10))
        exibicao.setReadOnly(True)
        exibicao.setMinimumWidth(160)
        exibicao.setStyleSheet(
            f"""
            QLineEdit {{
                background-color: {paleta.fundo_campo};
                color: {paleta.texto_primario};
                border: 1px solid {paleta.borda_campo};
                border-radius: 4px;
                padding: 3px 6px;
            }}
            """
        )

        valor_inicial = self.valores_iniciais.get(chave)
        exibicao.setText(str(valor_inicial) if valor_inicial else _TEXTO_SEM_VALOR)

        def ao_clicar(_verificado: bool = False) -> None:
            novo_valor = callback(self, exibicao.text())
            if novo_valor is not None:
                exibicao.setText(str(novo_valor))

        botao = QPushButton("📈", container)
        botao.setFixedWidth(34)
        botao.setFixedHeight(28)
        botao.setFont(fonte_padrao(10))
        botao.setCursor(Qt.PointingHandCursor)
        botao.setToolTip("Selecionar curva")
        botao.setStyleSheet(self._estilo_botao(False))
        botao.clicked.connect(ao_clicar)

        layout.addWidget(exibicao, 1)
        layout.addWidget(botao, 0)
        return exibicao

    # ------------------------------------------------------------------
    # Coleta de resultados
    # ------------------------------------------------------------------
    def _coletar_e_aceitar(self) -> None:
        valores: Dict[str, str] = {}
        for chave, (tipo, widget) in self.widgets.items():
            if tipo == "combobox":
                valores[chave] = widget.currentText()
            else:
                # "texto" e "botao_grafico": devolve a string exibida.
                valores[chave] = widget.text()
        self.resultado = valores
        self.accept()

    def valor_coletado(self) -> Optional[Dict[str, str]]:
        """Retorna o dict de valores após `exec()`, ou None se cancelado."""
        return self.resultado


def pedir_valores(
    parent: Optional[QWidget],
    titulo: str,
    campos: Sequence[Tuple[str, str, str, Any]],
    valores_iniciais: Optional[Dict[str, Any]] = None,
    dica: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Abre o formulário modal e retorna ``{chave: str}`` com o valor de
    TODOS os campos, ou None se o usuário cancelar/fechar o diálogo.

    `parent` pode ser None: nesse caso o diálogo é aberto sem janela-pai.
    """
    dialogo = _DialogoValores(parent, titulo, campos, valores_iniciais, dica)
    if dialogo.exec() == QDialog.Accepted:
        return dialogo.valor_coletado()
    return None
