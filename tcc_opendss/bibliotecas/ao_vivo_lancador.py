__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Lançador do módulo "Simulação ao Vivo" (QSTS animado).

Contrato com o menu principal (tcc_opendss.py), idêntico ao dos demais
lançadores em processo próprio:

    [sys.executable, "-m", "bibliotecas.ao_vivo_lancador",
     "--projeto", "<caminho_raiz_do_projeto>"]

O módulo cria o seu próprio QApplication e executa o laço de eventos até
a janela ser fechada.
"""

# O backend do matplotlib PRECISA ser definido antes de qualquer import que
# arraste o pyplot para este processo.
import os

os.environ.setdefault("MPLBACKEND", "QtAgg")

import argparse
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from .projeto import abrir_projeto_por_caminho
from .ao_vivo_ui import abrir_simulacao_ao_vivo


def _garantir_aplicacao() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def main(argv=None) -> int:
    """CLI do módulo: `python -m bibliotecas.ao_vivo_lancador --projeto <caminho>`."""
    parser = argparse.ArgumentParser(
        description="Simulação ao Vivo (QSTS animado) sobre o Master.dss do projeto.")
    parser.add_argument(
        "--projeto", required=True,
        help="Caminho da pasta raiz do projeto (a que contém 'rede/' e 'curvas/').")
    argumentos = parser.parse_args(argv)

    app = _garantir_aplicacao()

    try:
        projeto = abrir_projeto_por_caminho(argumentos.projeto)
    except Exception as e:
        QMessageBox.critical(
            None, "Erro",
            f"Não foi possível abrir o projeto:\n{argumentos.projeto}\n\n{e}")
        return 1

    try:
        abrir_simulacao_ao_vivo(projeto)
    except Exception as e:
        QMessageBox.critical(
            None, "Erro ao abrir a simulação ao vivo", str(e))
        return 1

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
