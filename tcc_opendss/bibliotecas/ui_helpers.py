__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Perguntas simples de interface compartilhadas pelos módulos.

Port Tkinter -> PySide6 (onda 1 da migração). O contrato público
(`perguntar_exibir_janelas`) é congelado.

TRANSPARÊNCIA TÉCNICA: o comportamento anterior (messagebox.askyesno do
Tk) tinha "Sim" como padrão implícito. Aqui o botão PADRÃO é "Não", uma
escolha conservadora: um Enter acidental não dispara a abertura de
janelas de gráfico. A resposta continua sendo True para "Sim" e False
para "Não"/fechar.
"""

import sys

from PySide6.QtWidgets import QApplication, QMessageBox


def _garantir_app() -> QApplication:
    """Garante uma instância de QApplication sem abrir janela principal."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def perguntar_exibir_janelas() -> bool:
    """Pergunta ao usuário se ele deseja visualizar os gráficos de perfil
    de tensão durante a execução. Retorna True para "Sim"."""
    _garantir_app()

    caixa = QMessageBox()
    caixa.setWindowTitle("TCC OpenDSS")
    caixa.setText("Deseja abrir as janelas com os gráficos de perfil de tensão?")
    caixa.setIcon(QMessageBox.Question)
    caixa.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    caixa.setDefaultButton(QMessageBox.No)

    botao_sim = caixa.button(QMessageBox.Yes)
    botao_nao = caixa.button(QMessageBox.No)
    if botao_sim is not None:
        botao_sim.setText("Sim")
    if botao_nao is not None:
        botao_nao.setText("Não")

    caixa.exec()
    return caixa.standardButton(caixa.clickedButton()) == QMessageBox.Yes
