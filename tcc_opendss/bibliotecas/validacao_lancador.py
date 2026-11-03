__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Lançador da Validação do Modelo Computacional.

Aplicação PySide6 *standalone*, seguindo o padrão visual Win11 do projeto
de referência (gerenciamento_de_demandas). Não depende de um Projeto ativo:
a validação testa o pipeline de simulação (OpenDSS + Python) em si, contra
os sistemas de referência consolidados na literatura (IEEE PES Test
Feeders), e não uma rede específica criada pelo usuário.

INTEGRIDADE DO SISTEMA (verificação ÚNICA): a verificação de integridade
do projeto é feita UMA ÚNICA VEZ, na abertura do sistema, pelo debugger
geral (bibliotecas/debugger.py, executado pelo tcc_opendss.bat ANTES do
menu principal). Este lançador NÃO repete essa verificação: abre direto o
diálogo de configuração da validação.

TRANSPARÊNCIA TÉCNICA — por que este módulo roda em PROCESSO PRÓPRIO:
    O menu principal do projeto (tcc_opendss.py, no diretório pai) é
    implementado em Tkinter. Este módulo, por sua vez, é implementado em
    PySide6/Qt (ver validacao_ui.py). Misturar os dois toolkits no mesmo
    processo implica dois event loops concorrentes (Tk mainloop + Qt
    QApplication), combinação reconhecidamente frágil e propensa a
    travamentos. A solução adotada é desacoplar por processo: o menu
    Tkinter chama ``abrir_validacao(parent)``, que lança ESTE módulo como
    subprocesso independente. Assim o menu Tk permanece intocado e a
    janela de validação roda em um processo Qt limpo, sem interferência
    de event loop. O parâmetro ``parent`` é aceito apenas por
    compatibilidade com a assinatura esperada pelo menu e é
    deliberadamente ignorado (não há compartilhamento de janela entre
    processos distintos).

Fluxo de abertura:
    ConfiguracaoValidacaoDialog -> execução -> ResultadosValidacaoDialog.
"""

# O backend do matplotlib é fixado ANTES de qualquer import de terceiros que
# possa carregá-lo. Motivo: este processo é Qt; se o matplotlib inicializar
# com backend interativo (TkAgg), ele tentaria abrir um segundo toolkit
# gráfico dentro do processo, causando conflito. 'Agg' é backend de render
# puramente em memória (usado apenas para gerar os PNGs de topologia).
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
    """Retorna a QApplication singleton, criando-a se ainda não existir.

    Necessário porque ``QApplication`` só pode ser instanciada uma vez por
    processo; criar uma segunda instância aborta a aplicação.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def main() -> int:
    """Ponto de entrada da aplicação de validação (processo Qt próprio).

    Abre DIRETO o diálogo de configuração da validação. A integridade do
    projeto é verificada uma única vez, na abertura do sistema pelo debugger
    geral (``bibliotecas/debugger.py``, executado pelo ``tcc_opendss.bat``)
    - este lançador não repete essa verificação.
    """
    app = _obter_qapplication()

    dialogo = ConfiguracaoValidacaoDialog(None)
    dialogo.exec()
    return app.exec()


def abrir_validacao(parent=None):
    """Lança a validação em processo separado (compatibilidade com o menu).

    Parâmetros
    ----------
    parent : qualquer
        Aceito por compatibilidade com o menu Tkinter, que o repassa. É
        IGNORADO de propósito: como a validação roda em outro processo
        (Qt), não há como compartilhar janela/event loop com o Tk do menu.

    Retorna
    -------
    subprocess.Popen
        O processo filho iniciado, útil para o chamador acompanhar/encerrar.
    """
    if getattr(sys, "frozen", False):
        # TRANSPARÊNCIA TÉCNICA — execução congelada (.exe): sys.executable
        # é o PRÓPRIO TccOpendss.exe, e "python -m" não existe no bundle.
        # Relançar com "-m" faria o exe entrar no main() do menu principal
        # e REABRIR o debugger de integridade em vez da validação. O
        # relançamento segue o MESMO contrato de _lancar_modulo
        # (tcc_opendss.py): exe relançado com --modulo-congelado; o shim do
        # topo do menu executa o módulo como __main__ via runpy. O cwd
        # espelha RAIZ_PROJETO do menu (pasta "tcc_opendss" irmã do .exe).
        raiz = Path(sys.executable).resolve().parent / "tcc_opendss"
        argumentos = [
            sys.executable,
            "--modulo-congelado",
            "bibliotecas.validacao_lancador",
        ]
    else:
        raiz = Path(__file__).resolve().parent.parent
        argumentos = [sys.executable, "-m", "bibliotecas.validacao_lancador"]
    return subprocess.Popen(
        argumentos,
        cwd=str(raiz),
        close_fds=True,
    )


if __name__ == "__main__":
    sys.exit(main())
