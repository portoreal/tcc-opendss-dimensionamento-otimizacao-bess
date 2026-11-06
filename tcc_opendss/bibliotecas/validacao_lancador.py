__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Lançador da Validação do Modelo Computacional.

Aplicação PySide6 autônoma, no padrão visual Win11 do projeto de referência
(gerenciamento_de_demandas). Não depende de um Projeto ativo: aqui se testa
o próprio encadeamento OpenDSS + Python, contra os sistemas de referência
consolidados na literatura (IEEE PES Test Feeders), e não uma rede que o
usuário desenhou.

INTEGRIDADE DO SISTEMA (verificação ÚNICA): o debugger geral
(bibliotecas/debugger.py, chamado pelo tcc_opendss.bat antes do menu
principal) confere a integridade do projeto uma única vez, na abertura do
sistema. Este lançador não repete a conferência - abre direto o diálogo de
configuração da validação.

POR QUE ESTE MÓDULO RODA EM PROCESSO PRÓPRIO:
    O menu principal (tcc_opendss.py, no diretório pai) é Tkinter; este
    módulo é PySide6/Qt (ver validacao_ui.py). Os dois no mesmo processo
    significam dois laços de eventos concorrentes, e essa combinação trava
    com frequência. Em vez de tentar domá-la, o menu Tkinter chama
    ``abrir_validacao(parent)``, que lança este módulo como subprocesso. O
    menu Tk fica intocado e a janela de validação nasce em um processo Qt
    limpo, sem laço de eventos estranho à sua volta. O parâmetro ``parent``
    existe só porque o menu passa algo nessa posição; é ignorado de
    propósito - processos distintos não compartilham janela.

Fluxo de abertura:
    ConfiguracaoValidacaoDialog -> execução -> ResultadosValidacaoDialog.
"""

# O backend do matplotlib é fixado ANTES de qualquer import de terceiros que
# possa carregá-lo. Este processo é Qt: se o matplotlib inicializasse em
# TkAgg, abriria um segundo toolkit gráfico dentro do processo. 'Agg'
# renderiza só em memória, que é tudo o que se precisa aqui - os PNGs da
# topologia das redes.
import os

os.environ.setdefault("MPLBACKEND", "Agg")

import subprocess
import sys
from pathlib import Path

try:
    from bibliotecas.validacao_ui import ConfiguracaoValidacaoDialog
except ImportError:
    from .validacao_ui import ConfiguracaoValidacaoDialog


def _obter_qapplication():
    """Retorna a QApplication única do processo, criando-a se ainda não existir.

    O Qt permite uma única instância por processo; a segunda tentativa
    aborta a aplicação. Por isso a busca em ``instance()`` antes de criar.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def main() -> int:
    """Ponto de entrada da aplicação de validação (processo Qt próprio).

    Abre direto o diálogo de configuração. A integridade do projeto já foi
    conferida na abertura do sistema pelo debugger geral
    (``bibliotecas/debugger.py``, chamado pelo ``tcc_opendss.bat``); repetir
    a conferência aqui só faria o usuário esperar duas vezes pela mesma
    coisa.
    """
    app = _obter_qapplication()

    dialogo = ConfiguracaoValidacaoDialog(None)
    dialogo.exec()
    return app.exec()


def abrir_validacao(parent=None):
    """Lança a validação em processo separado (chamada pelo menu do sistema).

    Parâmetros
    ----------
    parent : qualquer
        Repassado pelo menu Tkinter e ignorado de propósito: a validação
        roda em outro processo (Qt) e entre processos não se compartilha
        janela nem laço de eventos.

    Retorna
    -------
    subprocess.Popen
        O processo filho iniciado, para o chamador poder acompanhar ou
        encerrar a janela.
    """
    if getattr(sys, "frozen", False):
        # Execução congelada (.exe): sys.executable é o próprio
        # TccOpendss.exe, e "python -m" não existe dentro do bundle.
        # Relançar com "-m" faria o executável cair no main() do menu
        # principal e reabrir o debugger de integridade, em vez da
        # validação. Daí o contrato de _lancar_modulo (tcc_opendss.py):
        # o exe é relançado com --modulo-congelado, e o shim do topo do
        # menu executa o módulo como __main__ via runpy. O cwd espelha o
        # RAIZ_PROJETO do menu - a pasta "tcc_opendss" irmã do .exe.
        raiz = Path(sys.executable).resolve().parent / "tcc_opendss"
        argumentos = [
            sys.executable,
            "--modulo-congelado",
            "bibliotecas.validacao_lancador",
        ]
    else:
        raiz = Path(__file__).resolve().parent.parent
        argumentos = [sys.executable, "-m", "bibliotecas.validacao_lancador"]
    # close_fds=True: o filho não herda os descritores abertos do pai - aqui
    # não há nada a compartilhar, e herdar o que não se usa só cria surpresa.
    return subprocess.Popen(
        argumentos,
        cwd=str(raiz),
        close_fds=True,
    )


if __name__ == "__main__":
    sys.exit(main())
