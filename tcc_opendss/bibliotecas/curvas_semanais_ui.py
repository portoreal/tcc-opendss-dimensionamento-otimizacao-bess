"""
Diálogo de Curvas Semanais (7 dias, hora a hora) para PVSystems e Loads
da Otimização de BESS.

CORREÇÃO DE BUG / TRANSPARÊNCIA TÉCNICA:
1. As curvas são definidas em PERCENTUAL. No OpenDSS, o LoadShape multiplica
   a potência NOMINAL do elemento: P = % x kW nominal. Alterar a potência
   nominal no editor escala o perfil inteiro sem tocar nas curvas.
2. As edições são INDEPENDENTES por elemento: cada elemento/dia grava uma
   curva de projeto nomeada f'{elemento}_{dia}' (espaço -> '_').
3. 'Retornar ao padrão' sobrescreve a cópia do projeto com o template
   embutido de bibliotecas/curvas_padrao.py (upsert pelo mesmo nome).
4. PROVADO NO MOTOR (dss-python 0.15.7): o LoadShape multiplica kW E kvar
   com o MESMO multiplicador (shape 50% -> 15 kW e 1,5 kvar; fator de
   potência constante). A curva aparente (kVA) é DERIVADA
   (S = raiz(kW² + kvar²)) — não é modelável como shape próprio.
5. 0% é válido (carga desligada, ex.: motores de produção parados) e
   valores acima de 100% são válidos (ex.: partida de motor acima da
   nominal). Limite superior do campo: 600%.
"""

import os

# O backend do matplotlib precisa ser definido ANTES do import de pyplot/Figure
# para que o canvas interativo seja o do Qt (FigureCanvasQTAgg).
os.environ.setdefault("MPLBACKEND", "QtAgg")

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDoubleSpinBox, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from .curvas import CurvaCaracteristica, obter_curva, atualizar_curva
from .curvas_padrao import DIAS_SEMANA, obter_pontos_padrao
from .ui_win11 import mostrar_aviso_win11


LIMITE_PERC = 600.0

_ESTILO_BOTAO = (
    "QPushButton { padding: 5px 14px; border-radius: 5px; "
    "border: 1px solid #c8c8d0; background: #f7f7fa; }"
    "QPushButton:hover { background: #ececf2; }"
)
_ESTILO_BOTAO_PRINCIPAL = (
    "QPushButton { padding: 5px 14px; border-radius: 5px; "
    "border: 1px solid #2f6feb; background: #2f6feb; color: white; }"
    "QPushButton:hover { background: #2559c9; }"
)


class CurvasSemanaisDialog(QDialog):
    """Editor 7 dias x 24 horas (percentual) por elemento (PV/carga)."""

    def __init__(self, parent, projeto, rede):
        super().__init__(parent)
        self.projeto = projeto
        self.rede = rede
        self.pasta_curvas = projeto.caminho_curvas
        self.elementos = self._coletar_elementos()
        self.elemento_atual = None
        self.tabelas = {}
        self.spins = {}
        self._carregando = False

        self.setWindowTitle("Curvas Semanais (PV e Cargas)")
        self.setModal(True)
        self.resize(1000, 680)

        self._montar_widgets()

        if self.elementos:
            self.lista.setCurrentRow(0)
        else:
            self._redesenhar_grafico()

    # ------------------------------------------------------------ #
    def _coletar_elementos(self):
        saida = []
        for d in self.rede.derivacoes.values():
            if d.tipo not in ("Load", "PVSystem"):
                continue
            eh_pv = d.tipo == "PVSystem"
            if eh_pv:
                p_nom = float(d.parametros.get("pmpp", 0) or 0)
                q_nom = None
                natureza = "geracao"
            else:
                p_nom = float(d.parametros.get("kw", 0) or 0)
                q_nom = float(d.parametros.get("kvar", 0) or 0)
                natureza = "carga"
            saida.append({
                "nome": d.nome,
                "tipo": d.tipo,
                "natureza": natureza,
                "p_nom": p_nom,
                "q_nom": q_nom,
                "derivacao": d,
            })
        return saida

    # ------------------------------------------------------------ #
    def _montar_widgets(self):
        layout_raiz = QVBoxLayout(self)

        if not any(e["tipo"] == "PVSystem" for e in self.elementos):
            aviso = QLabel("Sem geração solar no projeto — apenas cargas disponíveis.")
            aviso.setStyleSheet("color: #a05a00; font-weight: bold;")
            aviso.setWordWrap(True)
            layout_raiz.addWidget(aviso)

        corpo = QHBoxLayout()

        # ----- esquerda: lista de elementos ------------------------
        coluna_esq = QVBoxLayout()
        rotulo = QLabel("Elementos:")
        coluna_esq.addWidget(rotulo)

        self.lista = QListWidget()
        self.lista.setMaximumWidth(260)
        self.lista.currentRowChanged.connect(self._ao_selecionar_elemento)
        coluna_esq.addWidget(self.lista, 1)
        self._preencher_lista()

        corpo.addLayout(coluna_esq, 0)

        # ----- direita: abas de dias + gráfico ----------------------
        coluna_dir = QVBoxLayout()

        self.abas = QTabWidget()
        coluna_dir.addWidget(self.abas, 1)

        self.rotulo_grafico = QLabel("Pré-visualização do dia selecionado:")
        coluna_dir.addWidget(self.rotulo_grafico)

        self.figura = Figure(figsize=(7.5, 2.8), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.figura)
        coluna_dir.addWidget(self.canvas, 0)

        corpo.addLayout(coluna_dir, 1)
        layout_raiz.addLayout(corpo, 1)

        # ----- nota -------------------------------------------------
        nota = QLabel(
            "0% = carga desligada (ex.: motores parados). Valores acima de 100% "
            "são válidos (ex.: partida de motor acima da nominal). kvar segue o "
            "mesmo percentual (fator de potência constante). A curva aparente é "
            "derivada, não modelável como shape próprio. O estudo simula a curva "
            "vinculada no campo daily — escolha o dia e salve.")
        nota.setWordWrap(True)
        nota.setStyleSheet("color: gray; font-style: italic; font-size: 9pt;")
        layout_raiz.addWidget(nota)

        # ----- rodapé: dia do estudo + botões ------------------------
        rodape = QHBoxLayout()
        rodape.addWidget(QLabel("Dia aplicado ao estudo:"))
        self.combo_dia = QComboBox()
        self.combo_dia.addItems(list(DIAS_SEMANA))
        rodape.addWidget(self.combo_dia)
        rodape.addStretch(1)

        botao_salvar = QPushButton("💾 Salvar curvas do elemento")
        botao_salvar.setStyleSheet(_ESTILO_BOTAO_PRINCIPAL)
        botao_salvar.clicked.connect(self._ao_salvar)
        rodape.addWidget(botao_salvar)

        botao_padrao = QPushButton("↩ Retornar ao padrão (este dia)")
        botao_padrao.setStyleSheet(_ESTILO_BOTAO)
        botao_padrao.clicked.connect(self._ao_retornar_padrao)
        rodape.addWidget(botao_padrao)

        botao_fechar = QPushButton("Fechar")
        botao_fechar.setStyleSheet(_ESTILO_BOTAO)
        botao_fechar.clicked.connect(self.reject)
        rodape.addWidget(botao_fechar)

        layout_raiz.addLayout(rodape)

    # ------------------------------------------------------------ #
    def _preencher_lista(self):
        self.lista.blockSignals(True)
        self.lista.clear()
        for e in self.elementos:
            daily = e["derivacao"].parametros.get("daily") or "sem curva"
            item = QListWidgetItem(f"{e['nome']} — {e['tipo']}  [daily: {daily}]")
            self.lista.addItem(item)
        self.lista.blockSignals(False)

    # ------------------------------------------------------------ #
    def _construir_tabelas(self, eh_carga):
        """(Re)cria as 7 abas; nº de colunas depende do tipo do elemento."""
        for i in range(self.abas.count() - 1, -1, -1):
            widget = self.abas.widget(i)
            self.abas.removeTab(i)
            widget.deleteLater()

        self.tabelas = {}
        self.spins = {}
        colunas = (["Hora", "Percentual (%)", "kW resultante"]
                   + (["kvar resultante", "S aparente (kVA)"] if eh_carga else []))

        for dia in DIAS_SEMANA:
            tabela = QTableWidget(24, len(colunas))
            tabela.setHorizontalHeaderLabels(colunas)
            tabela.verticalHeader().setVisible(False)
            tabela.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.ResizeToContents)

            for hora in range(24):
                item_h = QTableWidgetItem(f"{hora:02d}h")
                item_h.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                tabela.setItem(hora, 0, item_h)

                spin = QDoubleSpinBox()
                spin.setRange(0.0, LIMITE_PERC)
                spin.setDecimals(1)
                spin.setSingleStep(5.0)
                spin.setFixedWidth(90)
                spin.valueChanged.connect(
                    lambda valor, d=dia, h=hora: self._ao_digitar(d, h, valor))
                tabela.setCellWidget(hora, 1, spin)
                self.spins[(dia, hora)] = spin

                for col in range(2, len(colunas)):
                    tabela.setItem(hora, col, QTableWidgetItem(""))

            self.tabelas[dia] = tabela
            self.abas.addTab(tabela, dia)

    # ------------------------------------------------------------ #
    def _percentuais_do_elemento_dia(self, elemento, dia):
        nome = f"{elemento['nome']}_{dia}".replace(" ", "_")
        curva = obter_curva(self.pasta_curvas, nome)
        if curva is not None:
            return list(curva.percentuais())
        return [pct for (hora, pct)
                in obter_pontos_padrao(elemento["natureza"], dia)]

    # ------------------------------------------------------------ #
    def _carregar_tabelas(self, elemento):
        self._carregando = True
        self._construir_tabelas(elemento["natureza"] == "carga")
        for dia in DIAS_SEMANA:
            percentuais = self._percentuais_do_elemento_dia(elemento, dia)
            for hora in range(24):
                spin = self.spins[(dia, hora)]
                spin.blockSignals(True)
                spin.setValue(float(percentuais[hora]))
                spin.blockSignals(False)
                self._atualizar_derivadas(dia, hora)
        self._carregando = False
        self._redesenhar_grafico()

    # ------------------------------------------------------------ #
    def _ao_selecionar_elemento(self, linha):
        if linha < 0 or linha >= len(self.elementos):
            self.elemento_atual = None
            return
        self.elemento_atual = self.elementos[linha]
        self._carregar_tabelas(self.elemento_atual)

    # ------------------------------------------------------------ #
    def _atualizar_derivadas(self, dia, hora):
        e = self.elemento_atual
        if e is None:
            return
        tabela = self.tabelas.get(dia)
        if tabela is None:
            return
        valor = self.spins[(dia, hora)].value()
        kw = valor * e["p_nom"] / 100.0
        tabela.item(hora, 2).setText(f"{kw:,.2f}")
        if e["natureza"] == "carga":
            kvar = valor * (e["q_nom"] or 0.0) / 100.0
            aparente = (kw * kw + kvar * kvar) ** 0.5
            tabela.item(hora, 3).setText(f"{kvar:,.2f}")
            tabela.item(hora, 4).setText(f"{aparente:,.2f}")

    # ------------------------------------------------------------ #
    def _ao_digitar(self, dia, hora, valor):
        if self._carregando or self.elemento_atual is None:
            return
        self._atualizar_derivadas(dia, hora)
        self._redesenhar_grafico()

    # ------------------------------------------------------------ #
    def _redesenhar_grafico(self):
        e = self.elemento_atual
        self.figura.clear()
        ax = self.figura.add_subplot(111)
        if e is not None:
            dia = self.abas.tabText(self.abas.currentIndex())
            percentuais = [self.spins[(dia, h)].value() for h in range(24)]
            ax.plot(range(24), percentuais, marker="o", color="#2f6feb",
                    linewidth=1.6, markersize=4)
            maximo = max(percentuais) if percentuais else 100.0
            ax.set_ylim(0, max(110.0, maximo * 1.15))
            ax.set_title(f"{e['nome']} — {dia} (%, 24 h)", fontsize=9)
        ax.set_xlim(0, 23)
        ax.set_xticks(range(0, 24, 2))
        ax.set_xlabel("Hora do dia", fontsize=8)
        ax.set_ylabel("Percentual (%)", fontsize=8)
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.tick_params(labelsize=8)
        self.figura.tight_layout()
        self.canvas.draw_idle()

    # ------------------------------------------------------------ #
    def _ao_salvar(self):
        e = self.elemento_atual
        if e is None:
            return
        os.makedirs(self.pasta_curvas, exist_ok=True)
        for dia in DIAS_SEMANA:
            pontos = [(h, self.spins[(dia, h)].value()) for h in range(24)]
            curva = CurvaCaracteristica(
                nome=f"{e['nome']}_{dia}".replace(" ", "_"),
                natureza=e["natureza"],
                modo="daily",
                pontos=pontos,
            )
            atualizar_curva(self.pasta_curvas, curva)

        nome_dia = self.combo_dia.currentText()
        e["derivacao"].parametros["daily"] = (
            f"{e['nome']}_{nome_dia}".replace(" ", "_"))
        self.rede.salvar_json(
            os.path.join(self.projeto.caminho_rede, "rede.json"))

        try:
            from .exportador_dss import gerar_arquivos_dss
            gerar_arquivos_dss(self.rede, self.projeto.caminho_rede,
                               pasta_curvas=self.pasta_curvas)
        except ValueError as erro:
            mostrar_aviso_win11(self, "Erro ao reexportar a rede", str(erro))

        self._preencher_lista()

    # ------------------------------------------------------------ #
    def _ao_retornar_padrao(self):
        e = self.elemento_atual
        if e is None:
            return
        dia = self.abas.tabText(self.abas.currentIndex())
        padrao = [pct for (hora, pct) in obter_pontos_padrao(e["natureza"], dia)]

        self._carregando = True
        for hora in range(24):
            spin = self.spins[(dia, hora)]
            spin.blockSignals(True)
            spin.setValue(float(padrao[hora]))
            spin.blockSignals(False)
            self._atualizar_derivadas(dia, hora)
        self._carregando = False

        nome = f"{e['nome']}_{dia}".replace(" ", "_")
        if obter_curva(self.pasta_curvas, nome) is not None:
            pontos = [(h, float(padrao[h])) for h in range(24)]
            curva = CurvaCaracteristica(
                nome=nome, natureza=e["natureza"], modo="daily", pontos=pontos)
            atualizar_curva(self.pasta_curvas, curva)

        self._redesenhar_grafico()
