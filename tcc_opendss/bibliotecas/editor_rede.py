__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Módulo lançador do Editor de Rede Elétrica — PySide6.

TRANSPARÊNCIA TÉCNICA (migração Tkinter → PySide6):

- A versão Tkinter criava um `tk.Toplevel(parent)` (ou `tk.Tk()` sem parent) e
  instanciava `EditorRede(janela, projeto=projeto)`, entrando em `mainloop()`
  apenas quando não havia parent. Aqui:

    * `abrir_editor(projeto=None)` garante a QApplication singleton
      (`QApplication.instance() or QApplication(sys.argv)`), cria uma
      `QMainWindow` com o MESMO título do original
      ("Editor de Redes Elétricas - TCC OpenDSS", acrescido de
      " | Projeto: {nome}" quando há projeto) e o mesmo tamanho (1200x720).

    * O conteúdo do editor NÃO é reimplementado neste arquivo: a
      `QMainWindow` embute `EditorRede` como widget central, construído por
      outro módulo (`editor_ui.py`) na assinatura Qt
      `EditorRede(rede=None, projeto=projeto)`.

    * O menu "Arquivo" pertence à `QMainWindow` (barra de menus), não ao
      widget central; por isso `configurar_menu(qmainwindow)` é chamado
      logo após criar o widget central.

    * O modal/modalidade e o `mainloop()` do Tk não têm equivalente direto:
      `show()` exibe a janela e `app.exec()` roda o laço de eventos.

- DIFERENÇA DE COMPORTAMENTO DELIBERADA: no original, quando havia
  `parent`, a janela era um `Toplevel` e NÃO se chamava `mainloop()` (o laço
  já estava rodando na aplicação hospedeira). Aqui `show()` sempre exibe a
  janela, mas `app.exec()` só é chamado quando esta função criou a
  QApplication — evita reentrância de laço de eventos quando o editor é
  aberto a partir de uma janela principal já existente.

- Contrato de linha de comando preservado para uso pelo menu do sistema:

      [sys.executable, "-m", "bibliotecas.editor_rede", "--projeto", "<caminho>"]

  O caminho é resolvido por `projeto.abrir_projeto_por_caminho` (domínio
  intocado). Sem `--projeto`, o editor abre sem projeto.
"""

import argparse
import sys

from PySide6.QtWidgets import QApplication, QMainWindow

from .editor_ui import EditorRede
from .projeto import Projeto, abrir_projeto_por_caminho


def _garantir_app() -> tuple:
    """Garante uma QApplication. Retorna (app, criada_agora)."""
    app = QApplication.instance()
    if app is None:
        return QApplication(sys.argv), True
    return app, False


def abrir_editor(parent=None, projeto: Projeto = None):
    """Abre o Editor de Rede Elétrica em uma QMainWindow.

    Parameters
    ----------
    parent : QWidget, opcional
        Janela principal já existente (usada apenas como referência de
        empilhamento; a QMainWindow é independente).
    projeto : Projeto, opcional
        Projeto ativo. Se informado, o editor salva/exporta diretamente
        na pasta 'rede' do projeto, e passa a oferecer modelos
        dimensionados salvos ao criar elementos.

    Returns
    -------
    QMainWindow
        A janela criada (já visível).
    """
    app, criada_agora = _garantir_app()

    janela = QMainWindow(parent)
    if parent is not None:
        # Mesma ideia do tk.Toplevel(parent): janela independente, mas
        # transiente em relação à janela principal.
        janela.setWindowModality(0)  # Qt.NonModal == 0

    titulo = "Editor de Redes Elétricas - TCC OpenDSS"
    if projeto:
        titulo += f" | Projeto: {projeto.nome}"
    janela.setWindowTitle(titulo)
    janela.resize(1200, 720)

    editor = EditorRede(rede=None, projeto=projeto)
    janela.setCentralWidget(editor)

    # O menu "Arquivo" é configurado na QMainWindow (menuBar), não no widget
    # central — o EditorRede expõe essa função justamente para isso.
    if hasattr(editor, "configurar_menu"):
        editor.configurar_menu(janela)

    janela.show()

    if criada_agora and parent is None:
        app.exec()

    return janela


def main(argv=None):
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
