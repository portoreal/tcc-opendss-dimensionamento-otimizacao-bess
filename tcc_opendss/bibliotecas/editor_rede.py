__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Módulo lançador do Editor de Rede Elétrica — PySide6.

Este arquivo não desenha o editor: ele monta a janela em volta do widget
que o `editor_ui.py` constrói. Serve tanto para uso pela linha de comando
quanto para o menu principal abrir o editor.

O que mudou na migração Tkinter -> PySide6:

    * `abrir_editor(projeto=None)` garante a QApplication única do processo
      (`QApplication.instance() or QApplication(sys.argv)`), cria uma
      `QMainWindow` com o mesmo título de antes
      ("Editor de Redes Elétricas - TCC OpenDSS", mais
      " | Projeto: {nome}" quando há projeto) e o mesmo tamanho, 1200x720.

    * O conteúdo do editor não é reimplementado aqui: a `QMainWindow`
      embute `EditorRede` como widget central, construído por
      `editor_ui.py` na assinatura Qt
      `EditorRede(rede=None, projeto=projeto)`.

    * O menu "Arquivo" pertence à `QMainWindow` (a barra de menus), não ao
      widget central. Por isso `configurar_menu(qmainwindow)` é chamado
      logo depois de o widget central existir: quem sabe montar o menu é o
      editor, mas quem o hospeda é a janela.

    * O `mainloop()` do Tk não tem equivalente direto: `show()` exibe a
      janela e `app.exec()` roda o laço de eventos.

DIFERENÇA DE COMPORTAMENTO DELIBERADA: antes, quando havia `parent`, a
janela era um `Toplevel` e o `mainloop()` não era chamado - o laço já
estava rodando na aplicação hospedeira. Aqui `show()` sempre exibe a janela,
mas `app.exec()` só roda quando foi esta função que criou a QApplication.
Sem essa distinção, abrir o editor a partir do menu aninharia um laço de
eventos dentro do outro.

Linha de comando, usada pelo menu do sistema:

      [sys.executable, "-m", "bibliotecas.editor_rede", "--projeto", "<caminho>"]

O caminho é resolvido por `projeto.abrir_projeto_por_caminho`. Sem
`--projeto`, o editor abre sem projeto - útil para desenhar uma rede do
zero.
"""

import argparse
import sys

from PySide6.QtWidgets import QApplication, QMainWindow

from .editor_ui import EditorRede
from .projeto import Projeto, abrir_projeto_por_caminho


def _garantir_app() -> tuple:
    """Garante uma QApplication e informa se esta chamada a criou.

    O segundo valor da tupla é o que decide quem roda o laço de eventos:
    quem cria a aplicação é dono do laço; quem só a encontra, devolve o
    controle para quem já estava rodando.
    """
    app = QApplication.instance()
    if app is None:
        return QApplication(sys.argv), True
    return app, False


def abrir_editor(parent=None, projeto: Projeto = None):
    """Abre o Editor de Rede Elétrica em uma QMainWindow.

    Parameters
    ----------
    parent : QWidget, opcional
        Janela principal já existente, usada apenas como referência de
        empilhamento. A QMainWindow é independente dela.
    projeto : Projeto, opcional
        Projeto ativo. Se informado, o editor salva e exporta na pasta
        'rede' do projeto e passa a oferecer os modelos dimensionados
        salvos na hora de criar elementos.

    Returns
    -------
    QMainWindow
        A janela criada, já visível.
    """
    app, criada_agora = _garantir_app()

    janela = QMainWindow(parent)
    if parent is not None:
        # Mesma ideia do tk.Toplevel(parent): janela independente, porém
        # transiente em relação à principal. NonModal (0) porque o editor
        # não deve bloquear o menu enquanto está aberto.
        janela.setWindowModality(0)  # Qt.NonModal == 0

    titulo = "Editor de Redes Elétricas - TCC OpenDSS"
    if projeto:
        titulo += f" | Projeto: {projeto.nome}"
    janela.setWindowTitle(titulo)
    janela.resize(1200, 720)

    editor = EditorRede(rede=None, projeto=projeto)
    janela.setCentralWidget(editor)

    # O menu "Arquivo" é configurado na QMainWindow (menuBar), não no widget
    # central. O EditorRede expõe essa função justamente para que a janela
    # hospedeira a chame depois de ter o widget nas mãos.
    if hasattr(editor, "configurar_menu"):
        editor.configurar_menu(janela)

    janela.show()

    # Só assume o laço de eventos se foi esta chamada que criou a
    # aplicação e não há janela hospedeira rodando um laço.
    if criada_agora and parent is None:
        app.exec()

    return janela


def main(argv=None):
    """Entrada de linha de comando: abre o editor com o projeto informado.

    Sem ``--projeto``, abre vazio. Caminho inválido vira mensagem no stderr
    e código 1 - quem chama é outro processo e precisa saber da falha.
    """
    parser = argparse.ArgumentParser(
        prog="bibliotecas.editor_rede",
        description="Abre o Editor de Rede Elétrica do TCC OpenDSS.",
    )
    parser.add_argument(
        "--projeto",
        dest="projeto",
        default=None,
        help="Caminho do projeto (.json) a abrir junto com o editor.",
    )
    args = parser.parse_args(argv)

    projeto = None
    if args.projeto:
        projeto = abrir_projeto_por_caminho(args.projeto)
        if projeto is None:
            print(f"Não foi possível abrir o projeto: {args.projeto}", file=sys.stderr)
            return 1

    abrir_editor(projeto=projeto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
