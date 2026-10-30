__author__ = 'Pedro Henrique Sousa Pinheiro'
"""Módulo lançador do Estudo de Otimização de Alocação de BESS (PLIM).

Segue o mesmo padrão dos demais lançadores do projeto (editor_rede.py,
dimensionamento_lancador.py): valida pré-requisitos, carrega os dados
necessários do projeto ativo, e delega a orquestração da tela para
otimizacao_ui.abrir_dialogo_configuracao().

Responsabilidades específicas deste módulo:
    1. Verificar se o projeto já possui um Master.dss exportado
       (pré-requisito indispensável, pois o estudo recompila o circuito
       repetidamente a partir dele).
    2. Carregar a rede (rede.json) do projeto para obter a lista de
       barras disponíveis, usada para popular os comboboxes/listas de
       seleção de barras candidatas e barras de falta.
    3. Validar que existe ao menos uma Fonte (Vsource) configurada, já
       que sem uma fonte de tensão de referência não há sentido em
       falar de "afundamento de tensão" nem o Master.dss teria sido
       gerado com sucesso pelo exportador.

MUDANÇA DE MOTOR (registrada por transparência metodológica):
Após a migração de estudo_afundamento.py de win32com/COM para a
biblioteca DSS-Python (projeto DSS-Extensions), este lançador não
precisa mais inicializar/finalizar o contexto COM (pythoncom.
CoInitialize()/CoUninitialize()) dentro da thread de execução do
estudo. A arquitetura DSSContext do DSS-Python foi projetada
especificamente para permitir instâncias isoladas do motor em cenários
multithreaded, conforme documentação oficial do DSS-Extensions
("Multiple engines and multithreading"), tornando essa etapa
desnecessária.

MIGRAÇÃO DE INTERFACE (Tkinter -> PySide6/Qt) - MUDANÇA DE ASSINATURA:
`abrir_otimizacao_bess` antes era `abrir_otimizacao_bess(parent: tk.Tk,
projeto: Projeto)` porque a tela vivia embutida no laço Tk da janela
principal. Com a migração para Qt, este módulo passou a rodar em PROCESSO
PRÓPRIO (ele é invocado pelo menu como
`python -m bibliotecas.otimizacao_lancador --projeto <caminho>`) e cria o
seu próprio QApplication. Por isso o parâmetro `parent` desapareceu:
agora a assinatura é `abrir_otimizacao_bess(projeto: Projeto)` e a funcao
é responsável por executar `app.exec()` até o usuário fechar o diálogo de
resultados/configuração.

Contrato com o menu principal (tcc_opendss.py):
    [sys.executable, "-m", "bibliotecas.otimizacao_lancador",
     "--projeto", "<caminho_raiz_do_projeto>"]
"""

import argparse
import os
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from .modelo_rede import RedeEletrica
from .projeto import Projeto, abrir_projeto_por_caminho
from .otimizacao_ui import (
    abrir_dialogo_configuracao,
    instalar_captura_excecoes,
)
from .ui_win11 import fonte_padrao, mostrar_aviso_win11


def _garantir_aplicacao() -> QApplication:
    """Retorna a QApplication do processo, criando-a se necessário."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app.setApplicationName("Otimização de Alocação de BESS")
        app.setFont(fonte_padrao(10))
    return app


def _exibir_aviso(titulo: str, mensagem: str) -> None:
    """Aviso Qt: usa o diálogo Win11 se houver QApplication, senão cai no
    QMessageBox (situação só possível antes da criação da aplicação)."""
    if QApplication.instance() is not None:
        mostrar_aviso_win11(titulo, mensagem)
    else:
        QMessageBox.warning(None, titulo, mensagem)


def abrir_otimizacao_bess(projeto: Projeto):
    """Ponto de entrada do Módulo de Otimização de Alocação de BESS.

    Parameters
    ----------
    projeto : Projeto
        Projeto ativo selecionado no menu principal.

    Returns
    -------
    int
        Código de saída devolvido por QApplication.exec() quando o laço de
        eventos foi iniciado por esta função; 0 quando alguma pré-validação
        impediu a abertura da tela.
    """

    caminho_master = os.path.join(projeto.caminho_rede, "Master.dss")
    caminho_rede_json = os.path.join(projeto.caminho_rede, "rede.json")

    # Captura global de exceções ANTES de qualquer janela: este módulo roda
    # em subprocesso sem captura de saída; sem isto, uma exceção não tratada
    # fechava o processo sem rastro (sintoma: "janela pisca e fecha").
    instalar_captura_excecoes(projeto.caminho_raiz)

    app = _garantir_aplicacao()

    # -------- 1) Verifica se o Master.dss já foi exportado -------- #
    if not os.path.exists(caminho_master):
        _exibir_aviso(
            "Master.dss não encontrado",
            f"Não foi encontrado um arquivo 'Master.dss' em:\n{projeto.caminho_rede}\n\n"
            "Abra o 'Editor de Rede Elétrica', monte o circuito (incluindo a "
            "Fonte/Vsource) e utilize 'Arquivo > Exportar arquivos .dss' antes "
            "de rodar o estudo de otimização de alocação de BESS.")
        return 0

    # -------- 2) Carrega a rede.json para obter as barras disponíveis -------- #
    if not os.path.exists(caminho_rede_json):
        _exibir_aviso(
            "Rede não encontrada",
            f"Não foi encontrado um arquivo 'rede.json' em:\n{projeto.caminho_rede}\n\n"
            "O estudo de otimização precisa conhecer a topologia da rede "
            "(nomes de barras) para permitir a seleção de candidatos. Abra o "
            "'Editor de Rede Elétrica' e salve a rede antes de continuar.")
        return 0

    try:
        rede = RedeEletrica.carregar_json(caminho_rede_json)
    except Exception as e:
        QMessageBox.critical(
            None, "Erro ao carregar a rede",
            f"Não foi possível carregar o arquivo 'rede.json' do projeto:\n{e}")
        return 0

    # -------- 3) Validações mínimas de topologia -------- #
    if not rede.barras:
        _exibir_aviso(
            "Rede vazia",
            "A rede do projeto não possui barras cadastradas.\n\n"
            "Monte o circuito no 'Editor de Rede Elétrica' antes de rodar "
            "o estudo de otimização.")
        return 0

    if rede.obter_fonte() is None:
        _exibir_aviso(
            "Fonte (Vsource) não encontrada",
            "A rede do projeto não possui uma Fonte (Vsource) cadastrada.\n\n"
            "O estudo de afundamento de tensão depende de uma referência de "
            "tensão da subestação. Adicione uma Fonte pelo 'Editor de Rede "
            "Elétrica' e exporte novamente os arquivos .dss antes de continuar.")
        return 0

    if len(rede.barras) < 2:
        _exibir_aviso(
            "Rede muito pequena",
            "A rede do projeto possui apenas uma barra.\n\n"
            "O estudo de afundamento de tensão avalia o impacto de faltas "
            "em uma barra sobre as DEMAIS barras do sistema; portanto, é "
            "necessário haver ao menos duas barras na rede.")
        return 0

    # -------- 4) Delega para a orquestração da tela -------- #
    abrir_dialogo_configuracao(projeto, rede, caminho_master)

    # A tela de configuração é modal (exec()); o progresso e os resultados
    # usam QTimer, que exige laço de eventos ativo. Inicia o laço do
    # processo; ele termina com o último diálogo fechado (visto que
    # app.quitOnLastWindowClosed() é True por padrão).
    return app.exec()


def main(argv=None) -> int:
    """CLI do módulo: `python -m bibliotecas.otimizacao_lancador --projeto <caminho>`."""
    parser = argparse.ArgumentParser(
        description="Estudo de Otimização de Alocação de BESS (PLIM).")
    parser.add_argument(
        "--projeto", required=True,
        help="Caminho da pasta raiz do projeto (a que contém 'rede/' e 'curvas/').")
    argumentos = parser.parse_args(argv)

    app = _garantir_aplicacao()

    try:
        projeto = abrir_projeto_por_caminho(argumentos.projeto)
    except Exception as e:
        QMessageBox.critical(
            None, "Erro ao abrir o projeto",
            f"Não foi possível abrir o projeto em:\n{argumentos.projeto}\n\n{e}")
        return 1

    return abrir_otimizacao_bess(projeto)


if __name__ == "__main__":
    sys.exit(main())
