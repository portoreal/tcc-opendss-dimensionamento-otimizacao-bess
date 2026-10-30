__author__ = 'Pedro Henrique Sousa Pinheiro'
# Ponto de entrada único do projeto TCC OpenDSS (menu principal).
#
# Port Tkinter -> PySide6 (onda 2 da migração). O nome/posição deste arquivo
# NÃO mudam: o debugger (bibliotecas/debugger.py) o lança via subprocess
# ([sys.executable, <este caminho>], cwd=<raiz do projeto>).

"""Menu principal do TCC OpenDSS, em PySide6 (Qt).

TRANSPARÊNCIA TÉCNICA — arquitetura de processos
================================================
Este menu é uma aplicação Qt. Os módulos de Dimensionamento, Editor de Rede
e Otimização de BESS são lançados em PROCESSOS PRÓPRIOS, via
``subprocess.Popen([sys.executable, "-m", "bibliotecas.<modulo>",
"--projeto", <caminho_raiz>])``. Motivo: cada um desses módulos abre sua
própria janela/event loop; compartilhar o mesmo processo significaria
compartilhar um único QApplication e amarrar o ciclo de vida das janelas ao
menu. Desacoplar por processo mantém cada módulo isolado (uma falha em um
módulo não derruba o menu).

TRANSPARÊNCIA TÉCNICA — import tardio (lazy) do Engine do OpenDSS
================================================================
O menu Tkinter anterior importava ``DSS`` no topo do módulo. Quando o menu é
iniciado por ``pythonw`` (sem console), uma falha ao carregar a DLL do
OpenDSS abortava o processo SEM QUALQUER MENSAGEM VISÍVEL — o menu
simplesmente "não abria". Aqui o import fica DENTRO da ação "Rodar
Simulação", protegido por try/except, de modo que a falha vira uma caixa de
diálogo explícita ("Falha ao iniciar o Engine do OpenDSS.").

TRANSPARÊNCIA TÉCNICA — backend do matplotlib
=============================================
``MPLBACKEND`` é fixado em "QtAgg" ANTES de qualquer import de terceiros.
A simulação roda IN-PROCESS (dentro deste processo Qt) e gera gráficos de
perfil de tensão; se o matplotlib inicializasse com o backend TkAgg, ele
abriria um segundo toolkit gráfico no mesmo processo (combinação frágil e
propensa a travar). "QtAgg" reaproveita a QApplication já existente.
"""

import os

# Fixado antes de qualquer import que possa carregar o matplotlib
# (dss_engine -> plot_profile). setdefault preserva um valor já definido
# no ambiente pelo usuário.
os.environ.setdefault("MPLBACKEND", "QtAgg")

import subprocess
import sys
import traceback
import webbrowser
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# ============================================
# SHIM DE MÓDULO CONGELADO
# ============================================
#
# TRANSPARÊNCIA TÉCNICA — por que este shim existe
# =================================================
# Em modo script, os módulos são lançados como
# ``python -m bibliotecas.<modulo> --projeto <raiz>`` (ver
# ``_lancar_modulo``). No executável congelado (PyInstaller --onedir) NÃO
# existe interpretador Python separado nem ``-m``: o único processo
# executável é o próprio TccOpendss.exe, que sempre entraria em ``main()``.
#
# Solução: o executável relança a SI MESMO com
# ``--modulo-congelado <nome.do.modulo> --projeto <raiz>``. Este shim,
# executado ANTES de qualquer resolução de caminho/inicialização do Qt,
# reescreve ``sys.argv`` para ``[argv[0]] + <argumentos remanescentes>`` e
# executa o módulo alvo como ``__main__`` via ``runpy.run_module``.
# Consequência: os módulos lançadores permanecem INTOCADOS — cada um
# recebe no seu ``argparse`` exatamente os argumentos que recebia no modo
# script e acredita que foi iniciado por ``python -m``. Sem duplicar o
# binário nem manter scripts .py ao lado do .exe.
if len(sys.argv) >= 3 and sys.argv[1] == "--modulo-congelado":
    _nome_modulo_congelado = sys.argv[2]
    sys.argv = [sys.argv[0]] + sys.argv[3:]
    from runpy import run_module as _run_module_congelado

    _run_module_congelado(_nome_modulo_congelado, run_name="__main__")
    sys.exit(0)

# TRANSPARÊNCIA TÉCNICA — raiz do projeto: dois layouts, dois resolvedores.
#
# (1) SCRIPT (repositório / .bat): a PASTA "tcc_opendss" IRMÃ deste arquivo
#     (o menu vive um nível acima da pasta do projeto, ao lado do
#     tcc_opendss.bat). É ela que contém "bibliotecas/" — vai para o
#     sys.path (imports abaixo) e serve de cwd dos subprocessos
#     ("python -m bibliotecas.<módulo>", que exige a raiz no sys.path do
#     interpretador filho).
#
# (2) CONGELADO (PyInstaller --onedir, getattr(sys, "frozen", False)):
#     ``__file__`` aponta para dentro do bundle (_internal/), que é
#     read-only e não é onde ficam os dados do usuário. A distribuição
#     espelha o layout do repositório AO LADO do executável:
#
#         dist/TccOpendss/TccOpendss.exe
#         dist/TccOpendss/_internal/...
#         dist/TccOpendss/tcc_opendss/{projetos,hardware,validacao_ieee}
#
#     Logo a raiz é a pasta "tcc_opendss" irmã do EXECUTÁVEL, resolvida por
#     sys.executable (nunca por caminho absoluto de máquina).
if getattr(sys, "frozen", False):
    RAIZ_PROJETO = Path(sys.executable).resolve().parent / "tcc_opendss"
else:
    RAIZ_PROJETO = Path(__file__).resolve().parent / "tcc_opendss"
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

from bibliotecas.selecionar_projeto_ui import selecionar_projeto
from bibliotecas.ui_helpers import perguntar_exibir_janelas
from bibliotecas.ui_win11 import (
    COR_ACCENT_MARCA,
    RAIO_BORDA_BOTAO,
    detectar_tema,
    fonte_padrao,
    obter_paleta_ativa,
)
from bibliotecas.validacao_lancador import abrir_validacao

# Altura padrão dos botões do menu (mesma para primário, secundários e Sair).
ALTURA_BOTAO = 36


# ============================================
# Estado do menu
# ============================================

projeto_atual = None

# Referência à janela principal e ao rótulo de projeto ativo. Preenchidas por
# `montar_menu_principal()`; as ações abaixo as consultam.
janela_principal: Optional[QWidget] = None
label_projeto: Optional[QLabel] = None


# ============================================
# Lançamento de módulos em processo próprio
# ============================================

def _lancar_modulo(nome_modulo: str, projeto) -> Optional[subprocess.Popen]:
    """Lança ``python -m <nome_modulo> --projeto <caminho_raiz>`` em processo
    separado (não bloqueante), com cwd na raiz do projeto.

    Contrato congelado com os lançadores: ``--projeto`` recebe
    ``projeto.caminho_raiz`` (a pasta do projeto; as subpastas
    dimensionamento/curvas/rede são derivadas dela). stdout/stderr NÃO são
    capturados: um console aberto pelo lançador continua visível para o
    usuário (mensagens de diagnóstico e progresso).

    Retorna o ``Popen`` do módulo iniciado, ou None se o processo não pôde
    ser criado (ex.: ``sys.executable`` inválido) — nesse caso o erro é
    mostrado ao usuário em vez de estourar dentro do slot do botão.

    TRANSPARÊNCIA TÉCNICA — execução congelada (.exe)
    =================================================
    No bundle não existe ``python -m``: ``sys.executable`` é o PRÓPRIO
    TccOpendss.exe. O ramo congelado relança o executável com
    ``--modulo-congelado <nome_modulo> --projeto <raiz>``; o shim do topo
    deste arquivo consome esses dois argumentos e executa o módulo como
    ``__main__`` via ``runpy``. O ``--projeto`` e o ``cwd`` são os MESMOS do
    modo script, portanto os lançadores não precisam saber que estão
    congelados.
    """
    try:
        if getattr(sys, "frozen", False):
            argumentos = [
                sys.executable,
                "--modulo-congelado",
                nome_modulo,
                "--projeto",
                str(projeto.caminho_raiz),
            ]
        else:
            argumentos = [
                sys.executable,
                "-m",
                nome_modulo,
                "--projeto",
                str(projeto.caminho_raiz),
            ]
        return subprocess.Popen(
            argumentos,
            cwd=str(RAIZ_PROJETO),
            close_fds=True,
        )
    except OSError as erro:
        QMessageBox.critical(
            janela_principal,
            "Erro",
            f"Não foi possível iniciar o módulo '{nome_modulo}'.\n\n{erro}",
        )
        return None


# ============================================
# Ações do menu
# ============================================

def acao_selecionar_projeto():
    global projeto_atual
    projeto = selecionar_projeto(janela_principal)
    if projeto:
        projeto_atual = projeto
        atualizar_label_projeto()


def garantir_projeto_selecionado() -> bool:
    """Se não houver projeto ativo, força a seleção antes de continuar.
    Retorna True se há um projeto ativo ao final (selecionado agora ou já
    existente); False se o usuário cancelou."""
    global projeto_atual

    if projeto_atual:
        return True

    QMessageBox.information(
        janela_principal,
        "Selecione um projeto",
        "Esta funcionalidade requer um projeto ativo.\n"
        "Selecione ou crie um projeto na próxima tela.",
    )

    projeto = selecionar_projeto(janela_principal)
    if not projeto:
        return False

    projeto_atual = projeto
    atualizar_label_projeto()
    return True


def atualizar_label_projeto():
    if label_projeto is None:
        return
    if projeto_atual:
        label_projeto.setText(f"Projeto ativo: {projeto_atual.nome}")
        label_projeto.setStyleSheet(
            f"color: {obter_paleta_ativa(detectar_tema()).accent}; font-style: italic;"
        )
    else:
        label_projeto.setText("Nenhum projeto selecionado")
        label_projeto.setStyleSheet(
            f"color: {obter_paleta_ativa(detectar_tema()).texto_secundario}; font-style: italic;"
        )


def acao_abrir_validacao():
    """Abre o módulo de Validação do Modelo Computacional. Independente
    de projeto ativo: valida o pipeline OpenDSS+Python contra os
    sistemas de referência IEEE (13/34/37/123 barras), e não uma rede
    específica do usuário.

    ``abrir_validacao`` já executa em subprocesso próprio; o parâmetro
    ``parent`` é IGNORADO por contrato (não há janela compartilhável entre
    processos Qt distintos)."""
    abrir_validacao(None)


def acao_abrir_editor():
    if not garantir_projeto_selecionado():
        return
    _lancar_modulo("bibliotecas.editor_rede", projeto_atual)


def acao_abrir_dimensionamento():
    if not garantir_projeto_selecionado():
        return
    _lancar_modulo("bibliotecas.dimensionamento_lancador", projeto_atual)


def acao_abrir_otimizacao_bess():
    if not garantir_projeto_selecionado():
        return
    _lancar_modulo("bibliotecas.otimizacao_lancador", projeto_atual)


def acao_abrir_ao_vivo():
    if not garantir_projeto_selecionado():
        return
    _lancar_modulo("bibliotecas.ao_vivo_lancador", projeto_atual)


def acao_rodar_simulacao():
    """Roda a simulação diretamente sobre o Master.dss já exportado
    dentro da pasta 'rede' do projeto ativo (gerado pelo Editor de Rede)."""

    if not garantir_projeto_selecionado():
        return

    caminho_master = os.path.join(projeto_atual.caminho_rede, "Master.dss")

    if not os.path.exists(caminho_master):
        QMessageBox.warning(
            janela_principal,
            "Master.dss não encontrado",
            f"Não foi encontrado um arquivo 'Master.dss' em:\n{projeto_atual.caminho_rede}\n\n"
            "Abra o 'Editor de Rede Elétrica', monte o circuito e utilize "
            "'Arquivo > Exportar arquivos .dss' antes de rodar a simulação.",
        )
        return

    exibir_janelas = perguntar_exibir_janelas()

    # Import tardio: ver nota "TRANSPARÊNCIA TÉCNICA — import tardio" no topo.
    try:
        from bibliotecas.dss_engine import DSS
    except Exception:
        QMessageBox.critical(
            janela_principal,
            "Erro",
            "Falha ao iniciar o Engine do OpenDSS.",
        )
        return

    try:
        objeto_dss = DSS(caminho_master)
        versao = objeto_dss.versionDSS()
        print(f"[INFO] Versão do OpenDSS: {versao}")

        objeto_dss.mySolve(1.0)
        objeto_dss.plot_profile(1.0, mostrar=exibir_janelas)

        Vmin = objeto_dss.find_Vmin()
        print(f"[INFO] Simulação do projeto '{projeto_atual.nome}' -> Vmin = {Vmin:.4f} pu")
    except Exception as erro:
        traceback.print_exc()
        QMessageBox.critical(
            janela_principal,
            "Erro",
            f"Falha ao executar a simulação do projeto '{projeto_atual.nome}'.\n\n{erro}",
        )
        return

    QMessageBox.information(
        janela_principal,
        "Simulação concluída",
        f"Projeto: {projeto_atual.nome}\n"
        f"Versão do OpenDSS: {versao}\n"
        f"Vmin encontrada: {Vmin:.4f} pu",
    )


def acao_sair():
    if janela_principal is not None:
        janela_principal.close()


def _abrir_manual(nome_arquivo: str):
    """Abre um manual em HTML no navegador padrão.

    TRANSPARÊNCIA TÉCNICA — dois layouts válidos, resolvidos por
    candidatos RELATIVOS (nunca caminho absoluto), sempre a partir de
    __file__:

    1. Layout do repositório PUBLICADO: os manuais ficam em 'doc/' na
       raiz do repositório, IRMÃ da pasta do projeto (<raiz>/doc/),
       enquanto o código vive em <raiz>/tcc_opendss/.
    2. Layout de DESENVOLVIMENTO: os manuais ficam em
       <raiz>/tcc_opendss/docs/, dentro da pasta do projeto.

    Os candidatos são testados na ordem acima e vence o primeiro que
    existir. A ausência de todos (instalação incompleta ou pacote sem
    manuais) é avisada em vez de falhar silenciosamente. A URL é montada
    por Path.as_uri(), que aplica o percent-encoding exigido (espaços e
    acentos) — o caminho do projeto pode conter espaços (OneDrive)."""
    candidatos = []
    # TRANSPARÊNCIA TÉCNICA — 3º layout (congelado): a distribuição leva
    # "doc/" AO LADO do executável (dist/TccOpendss/doc/), e não ao lado de
    # __file__ (que no bundle aponta para _internal/). Este candidato é
    # testado PRIMEIRO no modo congelado; em modo script nem é montado.
    if getattr(sys, "frozen", False):
        candidatos.append(Path(sys.executable).resolve().parent / "doc" / nome_arquivo)
    candidatos.extend(
        [
            RAIZ_PROJETO.parent / "doc" / nome_arquivo,  # repo publicado
            RAIZ_PROJETO.parent / "docs" / nome_arquivo,  # repo publicado (legado)
            RAIZ_PROJETO / "docs" / nome_arquivo,  # desenvolvimento
            RAIZ_PROJETO / "doc" / nome_arquivo,  # desenvolvimento (legado)
        ]
    )
    for caminho in candidatos:
        if caminho.exists():
            webbrowser.open(caminho.as_uri())
            return
    QMessageBox.warning(
        janela_principal,
        "Manual não encontrado",
        f"Não foi encontrado o manual em:\n{candidatos[0]}\n\n"
        "Consulte a página de Releases do repositório do projeto."
    )


def acao_sobre():
    """Exibe o cartão 'Sobre' com os créditos do trabalho."""
    QMessageBox.information(
        janela_principal,
        "Sobre o TCC OpenDSS",
        "<b>Dimensionamento e otimização do posicionamento de sistemas de "
        "armazenamento de energia para mitigação de afundamentos de tensão "
        "em sistemas de distribuição</b><br><br>"
        "Este software foi desenvolvido por <b>Pedro Henrique Sousa Pinheiro</b> como "
        "Trabalho de Conclusão de Curso (TCC) de Engenharia Elétrica na "
        "<b>Universidade Católica de Santa Catarina</b> (Jaraguá do Sul/SC), "
        "formando em 2026.<br><br>"
        "Orientação: Douglas Flores Copetti<br>"
        "Coorientação: Fabiano Luz Cardoso<br><br>"
        "Contato: <b>pedrohenrique.pessoal@outlook.com</b><br>"
        "Repositório: <b>github.com/portoreal/tcc-opendss-dimensionamento-otimizacao-bess</b><br><br>"
        "Software livre para fins <b>não comerciais</b>: uso, estudo, modificação e "
        "redistribuição permitidos; comercialização proibida (ver LICENSE.md no "
        "repositório).",
    )


# ============================================
# Montagem do menu principal (PySide6)
# ============================================

def _criar_botao_principal(texto: str, paleta, ao_clicar) -> QPushButton:
    """Botão de destaque (azul institucional)."""
    botao = QPushButton(texto)
    botao.setFont(fonte_padrao(10, negrito=True))
    botao.setFixedHeight(ALTURA_BOTAO)
    botao.setCursor(Qt.PointingHandCursor)
    botao.setStyleSheet(
        f"""
        QPushButton {{
            background-color: {COR_ACCENT_MARCA};
            color: #FFFFFF;
            border: none;
            border-radius: {RAIO_BORDA_BOTAO}px;
            padding: 0 12px;
        }}
        QPushButton:hover {{ background-color: {paleta.accent_hover}; }}
        QPushButton:pressed {{ background-color: {paleta.accent_pressed}; }}
        """
    )
    botao.clicked.connect(ao_clicar)
    return botao


def _criar_botao_secundario(texto: str, paleta, ao_clicar) -> QPushButton:
    """Botão de módulo (visual neutro/outline)."""
    botao = QPushButton(texto)
    botao.setFont(fonte_padrao(10))
    botao.setFixedHeight(ALTURA_BOTAO)
    botao.setCursor(Qt.PointingHandCursor)
    botao.setStyleSheet(
        f"""
        QPushButton {{
            background-color: {paleta.botao_secundario_fundo};
            color: {paleta.texto_primario};
            border: 1px solid {paleta.borda_campo};
            border-radius: {RAIO_BORDA_BOTAO}px;
            padding: 0 12px;
        }}
        QPushButton:hover {{ background-color: {paleta.botao_secundario_hover}; }}
        QPushButton:pressed {{ background-color: {paleta.botao_secundario_pressed}; }}
        """
    )
    botao.clicked.connect(ao_clicar)
    return botao


def _criar_botao_sair(paleta, ao_clicar) -> QPushButton:
    """Botão "Sair" com tom de aviso (vermelho suave), mantendo o padrão
    de cores do tema ativo."""
    botao = QPushButton("Sair")
    botao.setFont(fonte_padrao(10, negrito=True))
    botao.setFixedHeight(ALTURA_BOTAO)
    botao.setCursor(Qt.PointingHandCursor)
    botao.setStyleSheet(
        f"""
        QPushButton {{
            background-color: {paleta.botao_secundario_fundo};
            color: {paleta.aviso};
            border: 1px solid {paleta.aviso};
            border-radius: {RAIO_BORDA_BOTAO}px;
            padding: 0 12px;
        }}
        QPushButton:hover {{
            background-color: {paleta.aviso};
            color: #FFFFFF;
        }}
        QPushButton:pressed {{
            background-color: #A4262C;
            color: #FFFFFF;
        }}
        """
    )
    botao.clicked.connect(ao_clicar)
    return botao


def montar_menu_principal() -> QWidget:
    """Monta e retorna a janela do menu principal, SEM entrar no event loop.

    Separada de ``main()`` para permitir instanciar a janela em testes
    (offscreen) sem exibir nada. A janela tem moldura nativa do Windows
    (frameless é reservado aos diálogos modais do projeto).
    """
    global janela_principal, label_projeto

    paleta = obter_paleta_ativa(detectar_tema())

    janela = QWidget()
    janela.setWindowTitle("TCC OpenDSS - Menu Principal")
    janela.resize(460, 560)
    janela.setMinimumSize(400, 520)
    janela.setFont(fonte_padrao(10))
    janela.setStyleSheet(f"QWidget {{ background-color: {paleta.fundo_cartao}; }}")

    layout = QVBoxLayout(janela)
    layout.setContentsMargins(18, 0, 18, 18)
    layout.setSpacing(10)

    # --- Menu superior (Ajuda / Sobre) ---
    # QMenuBar embutido na primeira linha do layout (a janela é QWidget,
    # não QMainWindow; setMenuBar() não se aplica). "Ajuda" abre os dois
    # manuais em HTML; "Sobre" é uma ação direta da barra.
    barra_menu = QMenuBar(janela)
    barra_menu.setFont(fonte_padrao(9))
    menu_ajuda = QMenu("Ajuda", barra_menu)
    menu_ajuda.addAction("Manual do Usuário (HTML)", lambda: _abrir_manual("manual_usuario.html"))
    menu_ajuda.addAction("Manual do Desenvolvedor (HTML)", lambda: _abrir_manual("manual_desenvolvedor.html"))
    barra_menu.addMenu(menu_ajuda)
    barra_menu.addAction("Sobre", acao_sobre)
    layout.addWidget(barra_menu)

    # --- Cabeçalho (faixa em azul institucional) ---
    cabecalho = QFrame(janela)
    cabecalho.setFixedHeight(64)
    cabecalho.setStyleSheet(
        f"""
        QFrame {{
            background-color: {COR_ACCENT_MARCA};
            border: none;
            border-bottom-left-radius: {RAIO_BORDA_BOTAO}px;
            border-bottom-right-radius: {RAIO_BORDA_BOTAO}px;
        }}
        """
    )
    layout_cabecalho = QVBoxLayout(cabecalho)
    layout_cabecalho.setContentsMargins(16, 0, 16, 0)

    titulo = QLabel("TCC OpenDSS", cabecalho)
    titulo.setFont(fonte_padrao(16, negrito=True))
    titulo.setStyleSheet("color: #FFFFFF; background: transparent;")
    layout_cabecalho.addWidget(titulo)

    layout.addWidget(cabecalho)

    # --- Rótulo do projeto ativo ---
    label_projeto = QLabel("Nenhum projeto selecionado", janela)
    label_projeto.setFont(fonte_padrao(9))
    label_projeto.setWordWrap(True)
    layout.addWidget(label_projeto)

    # --- Selecionar / criar projeto (botão primário) ---
    layout.addWidget(
        _criar_botao_principal(
            "📁 Selecionar / Criar Projeto", paleta, acao_selecionar_projeto
        )
    )

    rotulo_modulos = QLabel("Módulos do projeto:", janela)
    rotulo_modulos.setFont(fonte_padrao(10))
    rotulo_modulos.setStyleSheet(f"color: {paleta.texto_secundario};")
    layout.addWidget(rotulo_modulos)

    # --- Botões dos módulos ---
    opcoes = [
        ("✅  Validação do Modelo Computacional (IEEE)", acao_abrir_validacao),
        ("📐  Módulo de Dimensionamento", acao_abrir_dimensionamento),
        ("🖧  Editor de Rede Elétrica", acao_abrir_editor),
        ("▶️  Rodar Simulação", acao_rodar_simulacao),
        ("⚡📊  Otimização de Alocação de BESS (PLIM)", acao_abrir_otimizacao_bess),
        ("🎬  Simulação ao Vivo (QSTS animado)", acao_abrir_ao_vivo),
    ]
    for texto, comando in opcoes:
        layout.addWidget(_criar_botao_secundario(texto, paleta, comando))

    layout.addStretch(1)

    # --- Sair ---
    layout.addWidget(_criar_botao_sair(paleta, acao_sair))

    atualizar_label_projeto()

    janela_principal = janela
    return janela


# ============================================
# Ponto de entrada
# ============================================

def _instalar_excepthook() -> None:
    """Excepthook defensivo: qualquer exceção não tratada em slot/sinal Qt
    vira um QMessageBox.critical em vez de encerrar o processo em silêncio
    (cenário típico ao rodar via pythonw, sem console).

    O erro é NÃO é gravado em disco: é impresso em stderr (visível quando
    houver console) e exibido ao usuário. Nenhum arquivo de log é criado.
    """

    def _hook(tipo, valor, tb):
        texto = "".join(traceback.format_exception(tipo, valor, tb))
        print(texto, file=sys.stderr)
        try:
            QMessageBox.critical(
                janela_principal,
                "Erro inesperado",
                f"Ocorreu um erro inesperado:\n\n{valor}",
            )
        except Exception:
            # Se nem a caixa de diálogo puder ser exibida (ex.: sem
            # QApplication), não há mais nada a fazer — evita recursão
            # infinita no próprio hook.
            pass

    sys.excepthook = _hook


def main() -> None:
    _instalar_excepthook()

    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(fonte_padrao(10))

    # TRANSPARÊNCIA TÉCNICA — fluxo de abertura no modo CONGELADO.
    # ============================================================
    # Modo script: o tcc_opendss.bat roda verificar_dependencias.py,
    # depois debugger.py (janela de integridade) e SÓ ENTÃO este menu, em
    # dois processos distintos. No .exe não há .bat, não há "debugger.py"
    # em disco e não há segundo interpretador — o único processo é o
    # próprio executável, que já criou a QApplication acima.
    #
    # Portanto, congelado: a janela de integridade roda IN-PROCESS nesta
    # MESMA QApplication (via iniciar_debugger_projeto com o callback
    # ``ao_abrir_menu``, que desliga o subprocess do tcc_opendss.py) e, ao
    # concluir os checks com sucesso, abre o menu IN-PROCESS
    # (montar_menu_principal). Se o usuário fechar a janela sem
    # prosseguir, o processo encerra SEM abrir o menu — mesma semântica de
    # aborto do .bat (código de saída 1).
    if getattr(sys, "frozen", False):
        from bibliotecas import debugger as _debugger

        def _abrir_menu_embutido() -> None:
            janela_embutida = montar_menu_principal()
            janela_embutida.show()

        sys.exit(_debugger.iniciar_debugger_projeto(ao_abrir_menu=_abrir_menu_embutido))

    janela = montar_menu_principal()
    janela.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
