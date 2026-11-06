__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Lançador do módulo "Simulação ao Vivo" (QSTS animado).

QSTS é a simulação em que o OpenDSS avança no tempo em passos curtos e
resolve o fluxo de potência em cada um deles. "Ao vivo" significa que o
resultado é animado na tela enquanto a simulação corre, em vez de sair como
tabela no final.

O menu principal abre este módulo em processo separado, sempre pela mesma
linha de comando:

    [sys.executable, "-m", "bibliotecas.ao_vivo_lancador",
     "--projeto", "<caminho_raiz_do_projeto>"]

Processo separado não é capricho: o menu é Tkinter e a janela daqui é Qt, e
os dois toolkits trazem laços de eventos próprios, combinação que trava. O
módulo cria a sua QApplication e roda o laço de eventos até a janela ser
fechada.
"""

# O backend gráfico do matplotlib tem de ser escolhido ANTES de qualquer
# import que traga o pyplot para este processo. 'QtAgg' manda o matplotlib
# desenhar dentro do Qt, que é o toolkit desta janela; se ele inicializasse
# em TkAgg, tentaria abrir uma segunda janela de toolkit no mesmo processo.
import os

os.environ.setdefault("MPLBACKEND", "QtAgg")

import argparse
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from .projeto import abrir_projeto_por_caminho
from .ao_vivo_ui import abrir_simulacao_ao_vivo


def _garantir_aplicacao() -> QApplication:
    """Devolve a QApplication do processo, criando-a apenas na primeira chamada.

    O Qt admite uma única instância por processo - criar a segunda aborta o
    programa, daí a checagem antes de instanciar.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def main(argv=None) -> int:
    """CLI do módulo: ``python -m bibliotecas.ao_vivo_lancador --projeto <caminho>``.

    Devolve o código de saída do processo. Falhas ao abrir o projeto ou a
    janela viram caixa de mensagem e código 1, em vez de rastro de pilha no
    console - quem chama é o .bat, e um traceback ali não ajuda ninguém.
    """
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
    # O código de saída do main() volta para o sistema operacional, que é
    # como o menu (processo pai) sabe se a janela fechou bem.
    sys.exit(main())
