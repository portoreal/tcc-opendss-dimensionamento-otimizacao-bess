__author__ = 'Pedro Henrique Sousa Pinheiro'
"""View: tela do Módulo de Dimensionamento. Permite calcular parâmetros
técnicos de elementos (Linha, Transformador, PVSystem, Storage,
Capacitor, Gerador) a partir de regras de engenharia, e salvar o
resultado como um 'modelo' reutilizável dentro do projeto ativo.

TRANSPARÊNCIA TÉCNICA (port Tkinter -> PySide6, onda 2 da migração)
===================================================================
Este arquivo foi reescrito em PySide6. O DOMÍNIO não mudou: as mesmas
funções de `dimensionamento_regras.py` e o mesmo repositório
(`repositorio_modelos.listar_modelos/salvar_modelo/remover_modelo`) são
chamados com os mesmos argumentos.

Divergências em relação ao código Tk anterior (todas observáveis):

1. `DimensionamentoUI` era `tk.Frame` (widget para embutir numa Toplevel
   criada pelo lançador). Agora é `QDialog` — a janela em si, dona do
   ciclo de vida. `DimensionamentoUI(master, projeto=projeto)` continua
   funcionando como antes (o widget é empacotado na janela host), mas o
   caminho ativo do projeto é `DimensionamentoUI(parent, projeto)`
   seguido de `exec()`. O parâmetro `master` foi renomeado para `parent`
   apenas no nome; a posição é a mesma.

2. `ttk.Treeview` (com cabeçalho "#0" + coluna "detalhes") virou
   `QTreeWidget` de DUAS colunas ("Modelo" e "Resumo dos parâmetros").
   O agrupamento por tipo (nó-pai = nome de exibição do tipo), o nó
   aberto por padrão, o resumo "k=v" limitado aos 4 primeiros parâmetros
   e o duplo clique para abrir a memória de cálculo foram preservados.
   O `iid` do Tk (`"<tipo>::<nome>"`) foi mantido como `Qt.UserRole` do
   item, em vez de um iid textual — o Qt não aceita o "::" como
   identificador estável preferencial, e manter o dado explícito evita
   depender de parsing de string.

3. `messagebox` do Tk -> `QMessageBox` estilizado com a paleta
   `ui_win11` (mesmo visual dos diálogos e do resto do app migrado).
   Os textos das mensagens são transcrições fiéis do original.

4. `simpledialog.askstring("Salvar modelo", ...)` -> `pedir_valores`
   (onda 1), com um único campo de texto de valor inicial vazio. Isso
   mantém a caixa de diálogo no mesmo padrão visual das demais, sem
   reintroduzir `simpledialog`.

5. `Consultas.askyesno` -> `_confirmar()` (QMessageBox com "Sim"/"Não"
   em português). No Tk, `askyesno` tem "Yes" como botão padrão; aqui o
   padrão é "Sim" também, EXCETO na exclusão de modelo, onde o padrão é
   "Não" (ação destrutiva — ver `_excluir_modelo_selecionado`). Esta é
   uma divergência deliberada de segurança, não de funcionalidade.

6. O botão "Excluir modelo selecionado" usava `bg="#ffcdd2"` (material
   red 100). Em Qt, o mesmo papel semântico é dado pelo estilo "perigo"
   derivado da paleta (`paleta.aviso`), para não destoar no tema escuro.

7. Não há matplotlib neste módulo (nenhum gráfico é desenhado aqui), por
   isso o `MPLBACKEND` NÃO é configurado — seria um efeito colateral
   sem uso.
"""

from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .projeto import Projeto
from .dialogos import pedir_valores
from .repositorio_modelos import listar_modelos, salvar_modelo, remover_modelo
from .dimensionamento_regras import (
    dimensionar_linha, dimensionar_transformador, dimensionar_fotovoltaico,
    dimensionar_storage, dimensionar_capacitor, dimensionar_gerador,
)
from .ui_win11 import (
    RAIO_BORDA_BOTAO,
    RAIO_BORDA_CARTAO,
    RAIO_BORDA_CAMPO,
    detectar_tema,
    fonte_padrao,
    obter_paleta_ativa,
)


NOME_EXIBICAO = {
    "Line": "Linha",
    "Transformer": "Transformador",
    "PVSystem": "Fotovoltaico (PV)",
    "Storage": "BESS (Storage)",
    "Capacitor": "Capacitor",
    "Generator": "Gerador",
}

FUNCOES_DIMENSIONAMENTO = {
    "Line": dimensionar_linha,
    "Transformer": dimensionar_transformador,
    "PVSystem": dimensionar_fotovoltaico,
    "Storage": dimensionar_storage,
    "Capacitor": dimensionar_capacitor,
    "Generator": dimensionar_gerador,
}

CAMPOS_ENTRADA = {
    "Line": [
        ("potencia_kva", "Potência aparente do circuito (kVA)", "texto", "100"),
        ("tensao_kv", "Tensão nominal (kV)", "texto", "13.8"),
        ("fator_potencia", "Fator de potência", "texto", "0.92"),
        ("comprimento_km", "Comprimento da linha (km)", "texto", "1.0"),
        ("queda_max_pct", "Queda de tensão admissível (%)", "texto", "5.0"),
        ("fases", "Fases", "combobox", ["3", "1"]),
        ("material_preferido", "Material do condutor", "combobox",
         ["Qualquer", "CAA", "Cu"]),
    ],
    "Transformer": [
        ("potencia_carga_kw", "Potência de carga (kW)", "texto", "100"),
        ("fator_potencia", "Fator de potência", "texto", "0.92"),
        ("margem_seguranca_pct", "Margem de segurança (%)", "texto", "20"),
        ("kv_primario", "Tensão primária (kV)", "texto", "13.8"),
        ("kv_secundario", "Tensão secundária (kV)", "texto", "0.38"),
        ("fases", "Fases", "combobox", ["3", "1"]),
    ],
    "PVSystem": [
        ("consumo_mensal_kwh", "Consumo médio mensal (kWh)", "texto", "500"),
        ("hsp_local", "Horas de Sol Pleno - HSP (h/dia)", "texto", "5.0"),
        ("performance_ratio", "Performance Ratio (0 a 1)", "texto", "0.80"),
        ("potencia_modulo_wp", "Potência do módulo (Wp)", "texto", "550"),
        ("razao_dc_ac", "Razão DC/AC do inversor", "texto", "1.2"),
        ("kv_conexao", "Tensão de conexão (kV)", "texto", "0.38"),
        ("fases", "Fases", "combobox", ["3", "1"]),
    ],
    "Storage": [
        ("potencia_media_kw", "Potência média a suprir (kW)", "texto", "20"),
        ("horas_autonomia", "Autonomia desejada (horas)", "texto", "2"),
        ("profundidade_descarga_pct", "Profundidade de descarga - DoD (%)", "texto", "80"),
        ("eficiencia_pct", "Eficiência round-trip (%)", "texto", "90"),
        ("kv_conexao", "Tensão de conexão (kV)", "texto", "0.38"),
        ("fases", "Fases", "combobox", ["3", "1"]),
    ],
    "Capacitor": [
        ("potencia_ativa_kw", "Potência ativa (kW)", "texto", "200"),
        ("fp_atual", "Fator de potência atual", "texto", "0.85"),
        ("fp_desejado", "Fator de potência desejado", "texto", "0.95"),
        ("kv_conexao", "Tensão de conexão (kV)", "texto", "13.8"),
        ("fases", "Fases", "combobox", ["3", "1"]),
    ],
    "Generator": [
        ("potencia_carga_kw", "Potência de carga (kW)", "texto", "150"),
        ("fator_potencia", "Fator de potência", "texto", "0.92"),
        ("fator_demanda_pct", "Fator de demanda (%)", "texto", "100"),
        ("margem_seguranca_pct", "Margem de segurança (%)", "texto", "20"),
        ("kv_conexao", "Tensão de conexão (kV)", "texto", "0.38"),
        ("fases", "Fases", "combobox", ["3", "1"]),
    ],
}

# Rótulos dos botões da coluna esquerda: (texto exibido, tipo de elemento).
# Transcritos do original; a ordem é a mesma.
BOTOES_DIMENSIONAMENTO = [
    ("📏 Linha", "Line"),
    ("⧈ Transformador", "Transformer"),
    ("☀ Fotovoltaico (PV)", "PVSystem"),
    ("🔋 BESS (Storage)", "Storage"),
    ("▭ Capacitor (correção FP)", "Capacitor"),
    ("⚙ Gerador", "Generator"),
]


def _converter_entrada_calculo(valores: dict) -> dict:
    convertido = {}
    for k, v in valores.items():
        if k == "material_preferido":
            convertido[k] = None if v == "Qualquer" else v
        elif k == "fases":
            convertido[k] = int(v)
        else:
            try:
                convertido[k] = float(v)
            except ValueError:
                convertido[k] = v
    return convertido


def _capitalizar_preservando_resto(texto) -> str:
    """Devolve o texto com apenas o primeiro caractere em maiúscula,
    preservando as maiúsculas internas ("zcc pct" -> "Zcc pct",
    "ZCC" -> "ZCC", "queda tensão calculada pct" -> "Queda tensão calculada pct").
    str.capitalize() não serve: ele rebaixa todo o resto ("ZCC" -> "Zcc")."""
    texto = str(texto)
    if not texto:
        return texto
    return texto[:1].upper() + texto[1:]


def _formatar_memoria(dados: dict) -> str:
    """Formata a memória de cálculo em texto legível.

    Escalares saem como "<Rótulo>: <valor>". Um valor do tipo dict é
    expandido com um nível de indentação (2 espaços) logo abaixo do seu
    rótulo, para não despejar o repr do dicionário na tela.
    """
    linhas = []

    def _rotulo(k) -> str:
        return _capitalizar_preservando_resto(str(k).replace("_", " "))

    for k, v in dados.items():
        rotulo = _rotulo(k)
        if isinstance(v, dict):
            linhas.append(f"{rotulo}:")
            for sub_k, sub_v in v.items():
                if isinstance(sub_v, dict):
                    # Segundo nível: mantém o repr, mas explicitado.
                    linhas.append(f"  {_rotulo(sub_k)}: {sub_v}")
                else:
                    linhas.append(f"  {_rotulo(sub_k)}: {sub_v}")
        else:
            linhas.append(f"{rotulo}: {v}")
    return "\n".join(linhas)


class DimensionamentoUI(QDialog):
    """Tela do Módulo de Dimensionamento.

    Uso atual (lançador)::

        janela = DimensionamentoUI(parent, projeto)
        janela.exec()

    Compatibilidade com o código Tk (chamada posicional antiga)::

        janela = DimensionamentoUI(master, projeto=projeto)
        janela.pack()          # no-op: o widget já está montado no host

    `parent` pode ser None (janela de nível superior).
    """

    def __init__(self, parent: Optional[QWidget] = None, projeto: Projeto = None):
        super().__init__(parent)
        if projeto is None:
            raise ValueError("DimensionamentoUI exige um projeto.")

        self.projeto = projeto
        self._paleta = obter_paleta_ativa(detectar_tema())

        self.setWindowTitle(f"Módulo de Dimensionamento - Projeto: {projeto.nome}")
        self.setModal(parent is not None)
        self.setFont(fonte_padrao(10))

        self._montar_layout()
        self._atualizar_lista_modelos()

    # ------------------------------------------------------------------ #
    # Compatibilidade com a API Tk antiga
    # ------------------------------------------------------------------ #
    def pack(self, *args, **kwargs):
        """No-op: no Tk, `pack` inseria o Frame no master. Em Qt o layout
        já foi aplicado no construtor. Existe apenas para não quebrar
        chamadores antigos."""
        return None

    # ------------------------------------------------------------------ #
    # Construção da interface
    # ------------------------------------------------------------------ #
    def _montar_layout(self) -> None:
        paleta = self._paleta

        self.setStyleSheet(
            f"""
            QDialog, QWidget#raiz {{
                background-color: {paleta.fundo_cartao};
            }}
            QLabel {{ color: {paleta.texto_primario}; }}
            QLabel#secundario {{ color: {paleta.texto_secundario}; }}
            QTreeWidget {{
                background-color: {paleta.fundo_campo};
                color: {paleta.texto_primario};
                border: 1px solid {paleta.borda_campo};
                border-radius: {RAIO_BORDA_CAMPO}px;
                alternate-background-color: {paleta.botao_secundario_hover};
                selection-background-color: {paleta.accent};
                selection-color: #FFFFFF;
            }}
            QTreeWidget::item {{ padding: 3px 2px; }}
            QHeaderView::section {{
                background-color: {paleta.botao_secundario_fundo};
                color: {paleta.texto_primario};
                border: none;
                border-bottom: 1px solid {paleta.divisor};
                padding: 5px 6px;
            }}
            """
        )
        self.setMinimumSize(1000, 650)

        raiz = QWidget(self)
        raiz.setObjectName("raiz")
        layout_raiz = QHBoxLayout(self)
        layout_raiz.setContentsMargins(0, 0, 0, 0)
        layout_raiz.setSpacing(0)
        layout_raiz.addWidget(raiz)

        layout_conteudo = QHBoxLayout(raiz)
        layout_conteudo.setContentsMargins(0, 0, 0, 0)
        layout_conteudo.setSpacing(0)

        layout_conteudo.addWidget(self._montar_painel_esquerdo(raiz))
        layout_conteudo.addWidget(self._montar_painel_direito(raiz), 1)

    def _montar_painel_esquerdo(self, pai: QWidget) -> QWidget:
        paleta = self._paleta

        painel = QFrame(pai)
        painel.setFixedWidth(240)
        painel.setFrameShape(QFrame.NoFrame)
        painel.setStyleSheet(
            f"""
            QFrame {{
                background-color: {paleta.botao_secundario_fundo};
                border-right: 1px solid {paleta.borda_cartao};
            }}
            """
        )

        layout = QVBoxLayout(painel)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(6)

        rotulo_projeto = QLabel(f"Projeto:\n{self.projeto.nome}", painel)
        rotulo_projeto.setFont(fonte_padrao(10, negrito=True))
        rotulo_projeto.setWordWrap(True)
        rotulo_projeto.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        rotulo_projeto.setStyleSheet(
            f"color: {paleta.texto_primario}; border: none; background: transparent;"
        )
        layout.addWidget(rotulo_projeto)

        rotulo_secao = QLabel("Dimensionar elemento", painel)
        rotulo_secao.setFont(fonte_padrao(10, negrito=True))
        rotulo_secao.setStyleSheet(
            f"color: {paleta.texto_primario}; border: none; background: transparent;"
        )
        layout.addWidget(rotulo_secao)

        for texto, tipo in BOTOES_DIMENSIONAMENTO:
            botao = QPushButton(texto, painel)
            botao.setFixedHeight(34)
            botao.setCursor(Qt.PointingHandCursor)
            botao.setFont(fonte_padrao(10))
            botao.setStyleSheet(self._estilo_botao_primario())
            botao.clicked.connect(
                lambda _marcado=False, t=tipo: self._executar_dimensionamento(t)
            )
            layout.addWidget(botao)

        layout.addStretch(1)
        return painel

    def _montar_painel_direito(self, pai: QWidget) -> QWidget:
        painel = QWidget(pai)

        layout = QVBoxLayout(painel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        rotulo_titulo = QLabel("Modelos dimensionados salvos neste projeto", painel)
        rotulo_titulo.setFont(fonte_padrao(10, negrito=True))
        layout.addWidget(rotulo_titulo)

        rotulo_dica = QLabel("(duplo clique para ver a memória de cálculo)", painel)
        rotulo_dica.setObjectName("secundario")
        rotulo_dica.setFont(fonte_padrao(8))
        rotulo_dica.setStyleSheet(
            f"color: {self._paleta.texto_secundario}; font-style: italic;"
        )
        layout.addWidget(rotulo_dica)

        self.tree = QTreeWidget(painel)
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Modelo", "Resumo dos parâmetros"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree.setColumnWidth(0, 220)
        self.tree.setColumnWidth(1, 420)
        self.tree.itemDoubleClicked.connect(self._ao_dar_duplo_clique)
        layout.addWidget(self.tree, 1)

        botao_excluir = QPushButton("Excluir modelo selecionado", painel)
        botao_excluir.setFixedHeight(34)
        botao_excluir.setMinimumWidth(200)
        botao_excluir.setCursor(Qt.PointingHandCursor)
        botao_excluir.setFont(fonte_padrao(10))
        botao_excluir.setStyleSheet(self._estilo_botao_perigo())
        botao_excluir.clicked.connect(self._excluir_modelo_selecionado)

        linha_rodape = QHBoxLayout()
        linha_rodape.setContentsMargins(0, 6, 0, 0)
        linha_rodape.addStretch(1)
        linha_rodape.addWidget(botao_excluir)
        layout.addLayout(linha_rodape)

        return painel

    # ------------------------------------------------------------------ #
    # Estilos derivados da paleta
    # ------------------------------------------------------------------ #
    def _estilo_botao_primario(self) -> str:
        paleta = self._paleta
        return f"""
            QPushButton {{
                background-color: {paleta.accent};
                color: #FFFFFF;
                border: none;
                border-radius: {RAIO_BORDA_BOTAO}px;
                padding: 0 10px;
                text-align: left;
            }}
            QPushButton:hover {{ background-color: {paleta.accent_hover}; }}
            QPushButton:pressed {{ background-color: {paleta.accent_pressed}; }}
        """

    def _estilo_botao_perigo(self) -> str:
        """Equivalente Qt do `bg="#ffcdd2"` do Tk: usa `paleta.aviso`, que
        já é ajustada por tema (vermelho escuro no claro, salmon no
        escuro), mantendo contraste com o texto."""
        paleta = self._paleta
        return f"""
            QPushButton {{
                background-color: {paleta.botao_secundario_fundo};
                color: {paleta.aviso};
                border: 1px solid {paleta.aviso};
                border-radius: {RAIO_BORDA_BOTAO}px;
                padding: 0 12px;
            }}
            QPushButton:hover {{
                background-color: {paleta.fechar_hover};
                color: #FFFFFF;
            }}
            QPushButton:pressed {{
                background-color: #A4262C;
                color: #FFFFFF;
            }}
        """

    # ------------------------------------------------------------------ #
    # Diálogos de mensagem (QMessageBox com a paleta Win11)
    # ------------------------------------------------------------------ #
    def _mensagem(
        self,
        icone: QMessageBox.Icon,
        titulo: str,
        texto: str,
        botoes,
        padrao,
    ) -> QMessageBox.StandardButton:
        caixa = QMessageBox(self)
        caixa.setIcon(icone)
        caixa.setWindowTitle(titulo)
        caixa.setText(texto)
        caixa.setStandardButtons(botoes)
        caixa.setDefaultButton(padrao)
        caixa.setFont(fonte_padrao(10))
        caixa.setStyleSheet(self._estilo_caixa_mensagem())

        for botao_id, rotulo in (
            (QMessageBox.Ok, "OK"),
            (QMessageBox.Yes, "Sim"),
            (QMessageBox.No, "Não"),
        ):
            botao = caixa.button(botao_id)
            if botao is not None:
                botao.setText(rotulo)

        caixa.exec()
        return caixa.standardButton(caixa.clickedButton())

    def _estilo_caixa_mensagem(self) -> str:
        paleta = self._paleta
        return f"""
            QMessageBox {{
                background-color: {paleta.fundo_cartao};
            }}
            QMessageBox QLabel {{
                color: {paleta.texto_primario};
                background: transparent;
            }}
            QMessageBox QPushButton {{
                background-color: {paleta.botao_secundario_fundo};
                color: {paleta.texto_primario};
                border: 1px solid {paleta.borda_campo};
                border-radius: {RAIO_BORDA_BOTAO}px;
                padding: 5px 14px;
                min-width: 80px;
            }}
            QMessageBox QPushButton:hover {{
                background-color: {paleta.botao_secundario_hover};
            }}
            QMessageBox QPushButton:default {{
                background-color: {paleta.accent};
                color: #FFFFFF;
                border: none;
            }}
            QMessageBox QPushButton:default:hover {{
                background-color: {paleta.accent_hover};
            }}
        """

    def _avisar(self, titulo: str, texto: str) -> None:
        self._mensagem(QMessageBox.Information, titulo, texto, QMessageBox.Ok, QMessageBox.Ok)

    def _errar(self, titulo: str, texto: str) -> None:
        self._mensagem(QMessageBox.Critical, titulo, texto, QMessageBox.Ok, QMessageBox.Ok)

    def _confirmar(self, titulo: str, texto: str, padrao_sim: bool = True) -> bool:
        padrao = QMessageBox.Yes if padrao_sim else QMessageBox.No
        resposta = self._mensagem(
            QMessageBox.Question, titulo, texto,
            QMessageBox.Yes | QMessageBox.No, padrao,
        )
        return resposta == QMessageBox.Yes

    # ------------------------------------------------------------------ #
    # Fluxo de dimensionamento
    # ------------------------------------------------------------------ #
    def _executar_dimensionamento(self, tipo: str) -> None:
        campos_entrada = CAMPOS_ENTRADA[tipo]
        valores = pedir_valores(self, f"Dimensionar {NOME_EXIBICAO[tipo]}", campos_entrada)
        if valores is None:
            return

        try:
            entrada = _converter_entrada_calculo(valores)
            resultado = FUNCOES_DIMENSIONAMENTO[tipo](**entrada)
        except ValueError as e:
            self._errar("Erro no dimensionamento", str(e))
            return
        except (TypeError, ZeroDivisionError) as e:
            self._errar("Erro nos dados informados", str(e))
            return

        resumo = _formatar_memoria(resultado["memoria_calculo"])
        if not self._confirmar(
            "Resultado do dimensionamento",
            f"{resumo}\n\nDeseja salvar este resultado como um modelo "
            "reutilizável para este projeto?",
        ):
            return

        nome_modelo = self._pedir_nome_modelo()
        if not nome_modelo:
            return

        nome_final = salvar_modelo(
            self.projeto.caminho_dimensionamento, tipo, nome_modelo,
            resultado["parametros"], resultado["memoria_calculo"])

        if nome_final != nome_modelo:
            self._avisar(
                "Nome ajustado automaticamente",
                f"Já existia um modelo chamado '{nome_modelo}'.\n"
                f"Este foi salvo como '{nome_final}'.")

        self._atualizar_lista_modelos()

    def _pedir_nome_modelo(self) -> Optional[str]:
        """Substitui `simpledialog.askstring("Salvar modelo", ...)` pelo
        contrato Qt `pedir_valores` (um único campo de texto)."""
        valores = pedir_valores(
            self,
            "Salvar modelo",
            [("nome", "Nome para identificar este modelo:", "texto", "")],
        )
        if valores is None:
            return None
        return valores.get("nome", "").strip()

    # ------------------------------------------------------------------ #
    # Lista de modelos
    # ------------------------------------------------------------------ #
    def _atualizar_lista_modelos(self) -> None:
        self.tree.clear()

        for tipo, nome_exibicao in NOME_EXIBICAO.items():
            modelos = listar_modelos(self.projeto.caminho_dimensionamento, tipo)
            if not modelos:
                continue

            item_grupo = QTreeWidgetItem(self.tree, [nome_exibicao, ""])
            item_grupo.setFirstColumnSpanned(False)
            item_grupo.setFont(0, fonte_padrao(10, negrito=True))
            item_grupo.setFlags(item_grupo.flags() & ~Qt.ItemIsSelectable)
            item_grupo.setExpanded(True)

            for m in modelos:
                resumo_curto = ", ".join(
                    f"{k}={v}" for k, v in list(m["parametros"].items())[:4])
                item = QTreeWidgetItem(item_grupo, [m["nome"], resumo_curto])
                # O Tk usava iid textual "<tipo>::<nome>". Em Qt, o mesmo
                # dado fica em UserRole dos dois papéis, o que também
                # cobre o caso de um nome de modelo conter "::".
                item.setData(0, Qt.UserRole, (tipo, m["nome"]))
                item_grupo.addChild(item)

    def _ao_dar_duplo_clique(self, item: QTreeWidgetItem, _coluna: int) -> None:
        dados = item.data(0, Qt.UserRole)
        if not dados:
            return
        tipo, nome = dados

        modelos = listar_modelos(self.projeto.caminho_dimensionamento, tipo)
        modelo = next((m for m in modelos if m["nome"] == nome), None)
        if not modelo:
            return

        texto = (
            f"Tipo: {NOME_EXIBICAO.get(tipo, tipo)}\n\n"
            f"--- Parâmetros para o OpenDSS ---\n"
            f"{_formatar_memoria(modelo['parametros'])}\n\n"
            f"--- Memória de cálculo ---\n"
            f"{_formatar_memoria(modelo['memoria_calculo'])}"
        )
        self._avisar(f"Modelo: {nome}", texto)

    def _excluir_modelo_selecionado(self) -> None:
        selecionados = [
            item.data(0, Qt.UserRole) for item in self.tree.selectedItems()
        ]
        selecionados = [d for d in selecionados if d]

        if not selecionados:
            return

        for tipo, nome in selecionados:
            # Padrão "Não": exclusão é destrutiva (ver TRANSPARÊNCIA TÉCNICA).
            if self._confirmar("Confirmar exclusão", f"Excluir o modelo '{nome}'?",
                               padrao_sim=False):
                remover_modelo(self.projeto.caminho_dimensionamento, tipo, nome)

        self._atualizar_lista_modelos()


# Nome público alternativo, caso algum chamador prefira a convenção Qt.
JanelaDimensionamento = DimensionamentoUI

__all__ = [
    "DimensionamentoUI",
    "JanelaDimensionamento",
    "NOME_EXIBICAO",
    "FUNCOES_DIMENSIONAMENTO",
    "CAMPOS_ENTRADA",
    "BOTOES_DIMENSIONAMENTO",
]
