__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Módulo lançador do Dimensionamento — segue o mesmo padrão de
editor_rede.py, abrindo a tela em uma janela própria.

TRANSPARÊNCIA TÉCNICA (port Tkinter -> PySide6, onda 2 da migração)
===================================================================
Assinatura antiga::

    abrir_dimensionamento(parent: tk.Tk, projeto: Projeto) -> tk.Toplevel

Assinatura nova (congelada para o menu)::

    abrir_dimensionamento(projeto) -> DimensionamentoUI

Divergências observáveis:

1. Não existe mais uma Toplevel FILHA de uma janela Tk: a tela de
   Dimensionamento é um `QDialog` de nível superior. O `parent` de
   widget é opcional; o menu chama `abrir_dimensionamento(projeto)`
   (uma posição só), conforme o contrato congelado.

2. O bloqueio de execução mudou de janela-modal-do-Tk (que retornava
   imediatamente, com o Toplevel vivo em paralelo ao loop principal) para
   `app.exec()` — quando chamado como módulo (`python -m
   bibliotecas.dimensionamento_lancador --projeto <caminho>`), o processo
   permanece vivo enquanto a janela estiver aberta. Quando chamado
   DENTRO de um QApplication já em execução (o caso do menu), o
   `QApplication.exec()` é pulado: um segundo laço de eventos aninhado
   sobre a janela principal não é necessário, e `exec()` já está rodando.
   O diálogo é modal em relação ao parent quando há parent.

3. `geometry("1000x650")` -> `setMinimumSize(1000, 650)` + tamanho
   inicial equivalente. No Tk a geometria era fixa; aqui a janela pode
   crescer (a árvore de modelos se beneficia disso) mas não encolher
   abaixo do layout projetado.

4. Título preservado literalmente: "Módulo de Dimensionamento - Projeto:
   <nome>" (o mesmo texto é aplicado no próprio `DimensionamentoUI`).

5. `main()` novo: `--projeto` é OBRIGATÓRIO. O menu só invoca este
   módulo quando já existe um projeto aberto, então não há modo
   "abrir sem projeto" a preservar.

6. Sem matplotlib neste módulo — `MPLBACKEND` não é configurado.
"""

import argparse
import os
import sys
from typing import Optional

from PySide6.QtWidgets import QApplication, QWidget

from .projeto import Projeto, abrir_projeto_por_caminho
from .dimensionamento_ui import DimensionamentoUI


def _garantir_app() -> QApplication:
    """Garante uma única instância de QApplication no processo."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def abrir_dimensionamento(projeto: Projeto, parent: Optional[QWidget] = None):
    """Abre a tela do Módulo de Dimensionamento para `projeto`.

    Retorna a janela (`DimensionamentoUI`) já exibida com `show()`.

    Quando NÃO há laço de eventos ativo (chamada standalone), este
    lançador executa `app.exec()` e só retorna após o fechamento da
    janela — nesse caso o retorno ocorre com a janela já encerrada.
    """
    app = _garantir_app()

    janela = DimensionamentoUI(parent, projeto=projeto)
    janela.show()

    # `closingDown()`/laço ativo: um QApplication criado agora ainda não
    # tem laço rodando (teste: QApplication.exec() nunca foi chamado).
    # O flag confiável é a presença de um laço ativo no thread atual.
    from PySide6.QtCore import QCoreApplication, QThread

    laco_ativo = QThread.currentThread().loopLevel() > 0
    if not laco_ativo and QCoreApplication.instance() is not None:
        app.exec()

    return janela


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m bibliotecas.dimensionamento_lancador",
        description="Abre o Módulo de Dimensionamento do TCC OpenDSS.",
    )
    parser.add_argument(
        "--projeto", required=True,
        help="Caminho da pasta raiz do projeto (contém rede/, curvas/, "
             "dimensionamento/).",
    )
    args = parser.parse_args(argv)

    caminho = os.path.normpath(args.projeto)
    if not os.path.isdir(caminho):
        sys.stderr.write(f"Projeto não encontrado: {caminho}\n")
        return 2

    projeto = abrir_projeto_por_caminho(caminho)
    abrir_dimensionamento(projeto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
