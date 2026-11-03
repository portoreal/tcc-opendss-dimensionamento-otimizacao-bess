"""
debugger.py

Janela de verificacao de integridade ("Checks") do PROJETO INTEIRO
"tcc_opendss", executada ANTES de abrir o menu principal (tcc_opendss.py).

FLUXO DE ABERTURA DO SISTEMA (tcc_opendss.bat)
================================================
    1. Verificacao/instalacao de dependencias (verificar_dependencias.py,
       no console).
    2. ESTE debugger (janela, checks do PROJETO INTEIRO).
    3. Menu principal (tcc_opendss.py, Tkinter) - lancado PELO PROPRIO
       debugger ao concluir a verificacao (ver "iniciar_debugger_projeto").

TRANSPARENCIA TECNICA (transicao debugger -> menu)
================================================
No projeto de referencia ("gerenciamento_de_demandas"), a interface abre
na MESMA QApplication, ao final do debugger. Aqui o menu principal e
Tkinter - toolkit e, portanto, PROCESSO proprio - de modo que o debugger
nao pode exibi-lo na mesma QApplication. Para preservar o MESMO fluxo de
experiencia (o usuario ve a verificacao concluir e o menu aparecer logo
em seguida, sem passo intermediario), o debugger LANCA o menu via
subprocess.Popen e ENCERRA o processo. A ordem e a mesma da referencia:
o novo processo e criado ANTES de este terminar (evita qualquer janela
"piscando" no meio da transicao).

Janela 100% PySide6, no MESMO padrao visual Fluent/Win11 de
"ui_win11.py" e da janela de validacao:
    - Janela SEM MOLDURA NATIVA (frameless + translucent), cartao
      arredondado com sombra de elevacao.
    - Cabecalho em azul institucional arrastavel, com botao de fechar.

PADRAO PORTADO DO PROJETO "gerenciamento_de_demandas"
================================================
Este arquivo e um port fiel de "debugger.py" do projeto
"gerenciamento_de_demandas" (fonte citada), mantido com a MESMA UX e
o MESMO padrao visual Win11/Fluent. As adaptacoes de conteudo foram:
    - Titulo da janela.
    - Lista de CHECKS: em vez de checar conexoes de banco/coleta de
      dados, verifica o que o modulo de Validacao do Modelo
      Computacional do TCC realmente precisa para operar (motor
      OpenDSS, matplotlib, openpyxl, modulos do validador, dados de
      referencia IEEE, permissao de escrita).
    - Paleta/fonte/tema: importados do "ui_win11.py" LOCAL (port do
      TCC), com o mesmo fallback local da referencia caso o import
      falhe.

CHECKS MINIMALISTAS (SEM SKELETON/ANIMACAO): cada linha mostra apenas
um indicador discreto a esquerda do nome do check:
    - PENDENTE: ponto cinza neutro "○" (estatico, sem pulso/animacao).
    - OK: marca verde minimalista "✓" + texto do nome em verde.
    - FALHA: marca vermelha minimalista "✕" + texto do nome em
      vermelho (necessario para diagnostico - sem isso nao seria
      possivel distinguir falha de pendente).

DIMENSOES: a altura da janela e calculada pelo PROPRIO QT
(adjustSize + sizeHint), nunca por soma manual de numeros - evita o
aspecto "quebrado"/cortado. A area de checks tem altura calculada a
partir das MESMAS constantes usadas em cada linha, nunca um valor
arbitrario desencontrado do conteudo real.

SEM GERACAO DE ARQUIVOS DE LOG: nenhum erro, nem mesmo os
criticos/fatais, grava nada em disco - tudo e reportado
exclusivamente via caixa de mensagem NATIVA DO WINDOWS (MessageBoxW,
via ctypes), que nao depende de console, arquivo, ou qualquer
toolkit de GUI estar funcional.

Uso:
    from bibliotecas.debugger import iniciar_debugger_projeto
    sys.exit(iniciar_debugger_projeto())
"""

from __future__ import annotations

import ctypes
import importlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, List, Optional


# ══════════════════════════════════════════════════════════════════════════
# DETECCAO DE AMBIENTE (SCRIPT NORMAL / VENV / EMPACOTADO EM .EXE)
# ══════════════════════════════════════════════════════════════════════════


def _esta_empacotado() -> bool:
    return bool(getattr(sys, "frozen", False))


def _pasta_bibliotecas() -> Path:
    """Pasta onde este arquivo (debugger.py) esta - "bibliotecas/"."""
    try:
        if _esta_empacotado():
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent
    except Exception:
        return Path.cwd()


def _pasta_projeto() -> Path:
    """Pasta de DADOS do projeto - "tcc_opendss/" no layout do script e
    no layout da distribuicao congelada.

    TRANSPARENCIA TECNICA - dois layouts:
      (1) Script: um nivel acima de "bibliotecas/" (onde ficam
          "IEEETestCases/", "validacao_ieee/" e os modulos de entrada).
      (2) Congelado (PyInstaller --onedir): nao existe pasta de codigo
          gravavel - o bundle vive em "_internal/" (read-only) e a
          distribucao leva a pasta de dados "tcc_opendss/" AO LADO do
          executavel:
              dist/TccOpendss/TccOpendss.exe
              dist/TccOpendss/tcc_opendss/{projetos,hardware,validacao_ieee}
          Logo a base e derivada de sys.executable, nunca de __file__.
    """
    if _esta_empacotado():
        try:
            return Path(sys.executable).resolve().parent / "tcc_opendss"
        except Exception:
            return Path.cwd() / "tcc_opendss"
    return _pasta_bibliotecas().parent


# ══════════════════════════════════════════════════════════════════════════
# TRATAMENTO DE ERROS CRITICOS (NAO PREVISTOS) - SEM ARQUIVO DE LOG
# ══════════════════════════════════════════════════════════════════════════

_MB_OK = 0x00000000
_MB_ICONERROR = 0x00000010
_MB_TOPMOST = 0x00040000


def _exibir_mensagem_critica(titulo: str, mensagem: str) -> None:
    """
    Exibe uma caixa de mensagem NATIVA DO WINDOWS (MessageBoxW), sem
    depender de NENHUM toolkit de GUI (nem Qt, nem Tk) estar
    funcional, e SEM gravar nada em disco.
    """
    try:
        ctypes.windll.user32.MessageBoxW(0, mensagem, titulo, _MB_OK | _MB_ICONERROR | _MB_TOPMOST)
    except Exception:
        try:
            print(f"{titulo}\n{mensagem}")
        except Exception:
            pass


def tratar_erro_critico(contexto: str, excecao: BaseException) -> None:
    """Monta um resumo do erro (SEM gravar nada em disco) e exibe em
    uma caixa de mensagem nativa."""
    mensagem = (
        "Ocorreu um erro inesperado ao iniciar o sistema.\n\n"
        f"Contexto: {contexto}\n"
        f"Detalhes: {excecao}"
    )
    _exibir_mensagem_critica("Erro crítico ao iniciar o sistema", mensagem)


def _excecao_nao_tratada(tipo, valor, tb) -> None:
    excecao = valor if isinstance(valor, BaseException) else Exception(str(valor))
    tratar_erro_critico("Exceção não tratada", excecao)


sys.excepthook = _excecao_nao_tratada


# ══════════════════════════════════════════════════════════════════════════
# IMPORTS DE GUI (PySide6) - PROTEGIDOS
# ══════════════════════════════════════════════════════════════════════════

try:
    from PySide6.QtCore import Qt, QPoint, QTimer
    from PySide6.QtGui import QColor, QFont, QFontMetrics
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QGraphicsDropShadowEffect,
        QHBoxLayout,
        QLabel,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    _PYSIDE6_DISPONIVEL = True
except Exception as _erro_import_pyside6:  # noqa: N816
    _PYSIDE6_DISPONIVEL = False
    _ERRO_IMPORT_PYSIDE6 = _erro_import_pyside6


# ══════════════════════════════════════════════════════════════════════════
# PALETA/FONTE - reaproveita ui_win11.py (port do TCC) quando
# disponivel; caso contrario, usa um FALLBACK LOCAL simples.
# ══════════════════════════════════════════════════════════════════════════


def _fallback_fonte_padrao(tamanho: int = 10, negrito: bool = False):
    fonte = QFont("Segoe UI", tamanho)
    fonte.setBold(negrito)
    return fonte


def _fallback_paleta() -> SimpleNamespace:
    """Paleta minimalista (tema claro fixo) usada SOMENTE se
    "ui_win11.py" nao puder ser importado."""
    return SimpleNamespace(
        fundo_cartao="#FFFFFF",
        borda_cartao="#E5E5E5",
        texto_primario="#1B1B1B",
        texto_secundario="#6B6B6B",
        accent="#004587",
        accent_hover="#0A5BA8",
        accent_pressed="#003766",
        borda_campo="#8A8A8A",
        fundo_campo="#FFFFFF",
        aviso="#C42B1C",
        botao_secundario_fundo="#FFFFFF",
        botao_secundario_hover="#F3F3F3",
        botao_secundario_pressed="#E5E5E5",
        divisor="#E8E8E8",
        sombra_cor=(0, 0, 0, 90),
    )


_UI_WIN11_DISPONIVEL = False
RAIO_BORDA_CARTAO = 10
RAIO_BORDA_BOTAO = 6

if _PYSIDE6_DISPONIVEL:
    try:
        pasta_bibliotecas_import = str(_pasta_bibliotecas())
        if not _esta_empacotado() and pasta_bibliotecas_import not in sys.path:
            sys.path.insert(0, pasta_bibliotecas_import)

        try:
            # Modo script: "bibliotecas/" entra no sys.path acima e
            # "ui_win11" importa como módulo top-level.
            from ui_win11 import (
                detectar_tema as _detectar_tema_win11,
                obter_paleta_ativa as _obter_paleta_win11,
                fonte_padrao as _fonte_padrao_win11,
                RAIO_BORDA_CARTAO as _RAIO_BORDA_CARTAO_WIN11,
                RAIO_BORDA_BOTAO as _RAIO_BORDA_BOTAO_WIN11,
            )
        except ImportError:
            # Modo congelado (.exe): o PyInstaller embute ui_win11 SOMENTE
            # como submódulo do pacote "bibliotecas"
            # (collect_submodules no .spec) - não existe "ui_win11"
            # top-level no bundle. Sem este fallback, o import falhava em
            # silêncio e o debugger fixava o TEMA CLARO (fallback local),
            # ignorando o tema escuro do Windows.
            from bibliotecas.ui_win11 import (
                detectar_tema as _detectar_tema_win11,
                obter_paleta_ativa as _obter_paleta_win11,
                fonte_padrao as _fonte_padrao_win11,
                RAIO_BORDA_CARTAO as _RAIO_BORDA_CARTAO_WIN11,
                RAIO_BORDA_BOTAO as _RAIO_BORDA_BOTAO_WIN11,
            )

        RAIO_BORDA_CARTAO = _RAIO_BORDA_CARTAO_WIN11
        RAIO_BORDA_BOTAO = _RAIO_BORDA_BOTAO_WIN11
        _UI_WIN11_DISPONIVEL = True
    except Exception:
        pass


def _resolver_tema() -> str:
    if _UI_WIN11_DISPONIVEL:
        try:
            return _detectar_tema_win11()
        except Exception:
            pass
    return "claro"


def _resolver_paleta(tema: str):
    if _UI_WIN11_DISPONIVEL:
        try:
            return _obter_paleta_win11(tema)
        except Exception:
            pass
    return _fallback_paleta()


def _resolver_fonte(tamanho: int = 10, negrito: bool = False):
    if _UI_WIN11_DISPONIVEL:
        try:
            return _fonte_padrao_win11(tamanho, negrito)
        except Exception:
            pass
    return _fallback_fonte_padrao(tamanho, negrito)


# ══════════════════════════════════════════════════════════════════════════
# CORES DE STATUS (minimalistas - sem fundo "pill", apenas texto/icone)
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class _CoresStatus:
    sucesso: str
    erro: str
    pendente: str


_CORES_STATUS_CLARO = _CoresStatus(sucesso="#107C10", erro="#C42B1C", pendente="#A3A3A3")
_CORES_STATUS_ESCURO = _CoresStatus(sucesso="#6CCB5F", erro="#FF99A4", pendente="#8A8A8A")


def _resolver_cores_status(tema: str) -> _CoresStatus:
    return _CORES_STATUS_ESCURO if tema == "escuro" else _CORES_STATUS_CLARO


# ══════════════════════════════════════════════════════════════════════════
# MODELO DE UM CHECK
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class ResultadoCheck:
    ok: bool
    mensagem: str


# ══════════════════════════════════════════════════════════════════════════
# DEFINICAO DOS CHECKS
# ══════════════════════════════════════════════════════════════════════════


def check_interpretador_python() -> ResultadoCheck:
    try:
        executavel = sys.executable or ""
        versao = sys.version.split()[0]

        if _esta_empacotado():
            return ResultadoCheck(True, f"Aplicativo empacotado (.exe) em execução. Python {versao} embutido.")

        if not executavel:
            return ResultadoCheck(False, "Não foi possível determinar o caminho do interpretador Python em uso.")

        if not Path(executavel).exists():
            return ResultadoCheck(False, f"Interpretador Python não encontrado em disco: '{executavel}'.")

        return ResultadoCheck(True, f"Interpretador Python {versao} encontrado em: {executavel}")
    except Exception as erro:
        return ResultadoCheck(False, f"Erro inesperado ao verificar o interpretador Python: {erro}")


def check_ambiente_virtual() -> ResultadoCheck:
    try:
        if _esta_empacotado():
            # TRANSPARENCIA TECNICA: nao ha venv no .exe - o interpretador
            # Python e todas as dependencias vao embutidos no bundle
            # (PyInstaller). sys.prefix/base_prefix nao distinguem nada
            # nesse caso; reportar OK com a nota abaixo evita um falso
            # negativo que faria o usuario "continuar mesmo assim".
            return ResultadoCheck(
                True,
                "Aplicativo empacotado (.exe) - dependências embutidas no executável; "
                "verificação de venv não se aplica.",
            )

        dentro_de_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)

        if not dentro_de_venv:
            return ResultadoCheck(
                False,
                "O sistema NÃO está sendo executado dentro do ambiente virtual "
                "(venv) esperado - verifique o launcher .bat e a pasta 'venv' do projeto.",
            )

        return ResultadoCheck(True, f"Executando dentro do ambiente virtual (venv): {sys.prefix}")
    except Exception as erro:
        return ResultadoCheck(False, f"Erro inesperado ao verificar o ambiente virtual (venv): {erro}")


def _checar_modulo(nome_modulo: str, nome_exibicao: Optional[str] = None) -> ResultadoCheck:
    nome_exibicao = nome_exibicao or nome_modulo
    try:
        importlib.import_module(nome_modulo)
        return ResultadoCheck(True, f"Biblioteca '{nome_exibicao}' encontrada.")
    except ImportError as erro:
        return ResultadoCheck(
            False, f"Biblioteca '{nome_exibicao}' NÃO encontrada no ambiente ({erro}). Reinstale as dependências."
        )
    except Exception as erro:
        return ResultadoCheck(False, f"Erro inesperado ao verificar '{nome_exibicao}': {erro}")


def check_motor_opendss() -> ResultadoCheck:
    """Verifica o motor de simulação OpenDSS (pacote dss-python /
    DSS-Extensions) - CRÍTICO: sem ele nenhuma validação pode ser
    executada."""
    return _checar_modulo("dss", "dss-python (motor OpenDSS)")


def check_matplotlib() -> ResultadoCheck:
    """Verifica matplotlib - usado no desenho e na exportação da
    topologia das redes de referência."""
    return _checar_modulo("matplotlib", "matplotlib (topologia de redes)")


def check_openpyxl() -> ResultadoCheck:
    """Verifica openpyxl - usado na exportação dos resultados de
    validação para planilha Excel."""
    return _checar_modulo("openpyxl", "openpyxl (exportação Excel)")


def check_dados_referencia_ieee() -> ResultadoCheck:
    """Verifica se os dados de referência IEEE estão presentes:

    1. '<pasta IEEE>/<sistema>' com pelo menos um arquivo .dss em cada
        uma das subpastas 13Bus/34Bus/37Bus/123Bus (os modelos .dss que
        o validador efetivamente resolve).
    2. 'validacao_ieee/referencias/' (na raiz do projeto) com os 4 CSVs de
        referência (ieee13/34/37/123_referencia.csv) - os valores
        publicados pelo IEEE usados como gabarito de comparação.

    Sem qualquer um dos dois conjuntos, a validação não tem como rodar
    (faltaria o modelo a resolver, ou o gabarito a comparar).

    TRANSPARÊNCIA TÉCNICA - dois layouts válidos para os modelos .dss,
    resolvidos por candidatos RELATIVOS (nunca caminho absoluto):
    (1) raiz_projeto.parent / "IEEE" - layout do repositório PUBLICADO,
        onde 'IEEE/' é irmã da pasta do projeto;
    (2) raiz_projeto / "IEEETestCases" - layout de DESENVOLVIMENTO, com
        a pasta dentro do projeto.
    Vence o primeiro candidato cujo diretório exista; se nenhum existir,
    permanece o primeiro e a mensagem lista todos os candidatos
    testados."""
    try:
        raiz_projeto = _pasta_projeto()

        # --- 1. Modelos .dss por sistema ---
        candidatos_testes = [
            raiz_projeto.parent / "IEEE",  # repo publicado (IEEE/ irmã do projeto)
            raiz_projeto / "IEEETestCases",  # desenvolvimento
        ]
        pasta_testes = candidatos_testes[0]
        for candidato in candidatos_testes:
            if candidato.is_dir():
                pasta_testes = candidato
                break
        subpastas_sistemas = ["13Bus", "34Bus", "37Bus", "123Bus"]

        problemas: List[str] = []
        for subpasta in subpastas_sistemas:
            pasta_sistema = pasta_testes / subpasta
            if not pasta_sistema.is_dir():
                problemas.append(f"pasta ausente '{pasta_sistema}'")
                continue
            if not any(pasta_sistema.glob("*.dss")):
                problemas.append(f"nenhum arquivo .dss em '{pasta_sistema}'")

        if problemas:
            problemas.insert(
                0,
                "pastas de modelos testadas: "
                + ", ".join(f"'{c}'" for c in candidatos_testes),
            )

        # --- 2. CSVs de referência (gabarito IEEE) ---
        # ATENÇÃO: a pasta de referências fica na RAIZ do projeto
        # ("<raiz>/validacao_ieee/referencias/"), não dentro de
        # "bibliotecas/" - mesma convenção usada por validacao_ieee.py
        # (DIR_REFERENCIAS = OPEN_DSS_DIR / "validacao_ieee/referencias").
        pasta_referencias = raiz_projeto / "validacao_ieee" / "referencias"
        nomes_csv = [
            "ieee13_referencia.csv",
            "ieee34_referencia.csv",
            "ieee37_referencia.csv",
            "ieee123_referencia.csv",
        ]
        if not pasta_referencias.is_dir():
            problemas.append(f"pasta ausente '{pasta_referencias}'")
        else:
            for nome_csv in nomes_csv:
                if not (pasta_referencias / nome_csv).is_file():
                    problemas.append(f"CSV ausente '{nome_csv}'")

        if problemas:
            return ResultadoCheck(False, "Dados de referência IEEE incompletos: " + "; ".join(problemas) + ".")

        return ResultadoCheck(
            True,
            "Modelos .dss (13/34/37/123) e os 4 CSVs de referência IEEE encontrados.",
        )
    except Exception as erro:
        return ResultadoCheck(False, f"Erro inesperado ao verificar os dados de referência IEEE: {erro}")


def check_permissao_pasta_temporaria() -> ResultadoCheck:
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(prefix="tcc_opendss_validacao_check_", suffix=".tmp", delete=True):
            pass
        return ResultadoCheck(True, "Permissão de escrita na pasta temporária OK.")
    except Exception as erro:
        return ResultadoCheck(False, f"Não foi possível escrever na pasta temporária do sistema: {erro}")


def check_pulp() -> ResultadoCheck:
    """Verifica PuLP - solver de PLIM usado na otimização da alocação do
    sistema de armazenamento (otimizacao_milp.py)."""
    return _checar_modulo("pulp", "PuLP (otimização PLIM)")


def check_pyside6() -> ResultadoCheck:
    """Verifica PySide6 (interface gráfica do módulo de validação e do
    debugger de integridade), incluindo os três submódulos centrais."""
    try:
        import PySide6

        versao = getattr(PySide6, "__version__", "desconhecida")
    except ImportError as erro:
        return ResultadoCheck(
            False, f"Biblioteca 'PySide6 (interface gráfica)' NÃO encontrada no ambiente ({erro})."
        )
    except Exception as erro:
        return ResultadoCheck(False, f"Erro inesperado ao verificar 'PySide6 (interface gráfica)': {erro}")

    faltantes = []
    for submodulo in ("PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"):
        try:
            importlib.import_module(submodulo)
        except Exception:
            faltantes.append(submodulo)

    if faltantes:
        return ResultadoCheck(
            False, f"PySide6 {versao} presente, mas submódulo(s) ausente(s): {', '.join(faltantes)}."
        )
    return ResultadoCheck(True, f"PySide6 {versao} encontrada (QtCore, QtGui, QtWidgets OK).")


def check_tkinter() -> ResultadoCheck:
    """Verifica Tkinter - toolkit do menu principal (tcc_opendss.py).

    ATENÇÃO (transparência técnica): verifica apenas a IMPORTABILIDADE do
    módulo e reporta a versão do Tk (tkinter.TkVersion). NÃO instancia
    nenhuma janela Tk, para não abrir um segundo toolkit gráfico dentro
    do processo Qt do debugger."""
    try:
        import tkinter

        return ResultadoCheck(True, f"Tkinter encontrado (Tk versão {tkinter.TkVersion}).")
    except ImportError as erro:
        return ResultadoCheck(
            False, f"Biblioteca 'Tkinter (menu principal)' NÃO encontrada no ambiente ({erro})."
        )
    except Exception as erro:
        return ResultadoCheck(False, f"Erro inesperado ao verificar 'Tkinter (menu principal)': {erro}")


# Lista de módulos internos (.py) que DEVEM existir em "bibliotecas/" para o
# projeto inteiro operar. Verificada apenas quanto à EXISTÊNCIA em disco
# (Path.is_file) - não à importabilidade (ver nota em check_modulos_validador).
_MODULOS_DO_PROJETO = [
    # Núcleo / infraestrutura
    "dss_engine.py",
    "ui_win11.py",
    "ui_helpers.py",
    "dialogos.py",
    "constantes_controle.py",
    "debugger.py",
    # Projeto e editor de rede
    "projeto.py",
    "modelo_rede.py",
    "editor_rede.py",
    "editor_ui.py",
    "exportador_dss.py",
    "layout_automatico.py",
    "repositorio_modelos.py",
    "selecionar_projeto_ui.py",
    # Validação do modelo computacional (IEEE)
    "validacao_ieee.py",
    "validacao_ui.py",
    "validacao_topologia.py",
    "validacao_exportar_projeto.py",
    "validacao_exportar_excel.py",
    # Dimensionamento
    "dimensionamento_regras.py",
    "dimensionamento_ui.py",
    "dimensionamento_lancador.py",
    # Otimização (PLIM)
    "otimizacao_milp.py",
    "otimizacao_bess.py",
    "otimizacao_ui.py",
    "otimizacao_lancador.py",
    # Simulação ao vivo (QSTS animado)
    "ao_vivo_engine.py",
    "ao_vivo_exportar.py",
    "ao_vivo_ui.py",
    "ao_vivo_lancador.py",
    # Exportadores de hardware (parametrização para sketches pré-prontos)
    "exportador_arduino.py",
    "exportador_esp32.py",
    # Economia / BESS / tarifas
    "economia_energia.py",
    "sistema_bess.py",
    "catalogo_bess.py",
    "tarifas_energia.py",
    "memorial_calculo_economia.py",
    # Afundamento de tensão
    "estudo_afundamento.py",
    "memorial_calculo_afundamento.py",
    # Reativo e curvas
    "reativo_analise.py",
    "curvas.py",
    "curvas_padrao.py",
    "curvas_semanais_ui.py",
    "curva_editor_ui.py",
]


def check_modulos_projeto() -> ResultadoCheck:
    """Verifica se TODOS os módulos internos (.py) do projeto estão
    presentes em "bibliotecas/". Em modo empacotado (.exe), ficam
    EMBUTIDOS no executável: a verificação deixa de ser de EXISTÊNCIA em
    disco e passa a ser de DISPONIBILIDADE no bundle
    (importlib.util.find_spec) — ver TRANSPARÊNCIA TÉCNICA no corpo.

    ATENÇÃO (transparência técnica): verifica a EXISTÊNCIA dos arquivos
    em disco (Path.is_file), NÃO a importabilidade dos módulos - a
    importação real de módulos que dependem de contexto (ex.: UIs que
    instanciam widgets) é deixada para o fluxo normal do projeto, para
    não introduzir efeitos colaterais de importação no debugger."""
    if _esta_empacotado():
        # TRANSPARENCIA TECNICA - por que NAO usar is_file() no congelado:
        # no bundle nao existem "bibliotecas/*.py" em disco (o codigo esta
        # dentro do executavel/_internal). Testar disco no congelado
        # sempre falharia; declarar OK cegamente esconderia um modulo que
        # o PyInstaller nao incluiu. Solucao: verificar a DISPONIBILIDADE
        # REAL do modulo no bundle com importlib.util.find_spec(), que
        # resolve pelo meta-path do importador congelado e NAO executa o
        # modulo (preserva a ausencia de efeitos colaterais de importacao
        # documentada acima).
        import importlib.util

        faltantes = []
        for nome in _MODULOS_DO_PROJETO:
            modulo = f"bibliotecas.{nome[:-3]}"  # remove o sufixo ".py"
            try:
                disponivel = importlib.util.find_spec(modulo) is not None
            except (ImportError, AttributeError, ValueError):
                disponivel = False
            if not disponivel:
                faltantes.append(nome)

        if faltantes:
            return ResultadoCheck(
                False,
                "Módulo(s) do projeto ausente(s) do executável: " + ", ".join(faltantes) + ".",
            )
        return ResultadoCheck(
            True,
            f"Todos os {len(_MODULOS_DO_PROJETO)} módulos do projeto estão embutidos no executável.",
        )

    try:
        pasta = _pasta_bibliotecas()
        faltantes = [nome for nome in _MODULOS_DO_PROJETO if not (pasta / nome).is_file()]

        if faltantes:
            return ResultadoCheck(
                False, f"Módulo(s) do projeto não encontrado(s) em '{pasta}': {', '.join(faltantes)}."
            )
        return ResultadoCheck(
            True, f"Todos os {len(_MODULOS_DO_PROJETO)} módulos do projeto estão presentes em 'bibliotecas/'."
        )
    except Exception as erro:
        return ResultadoCheck(False, f"Erro inesperado ao verificar os arquivos do projeto: {erro}")


def montar_checks_projeto() -> List[tuple]:
    """Lista de checks GERAIS do projeto "tcc_opendss" - o debugger de
    integridade passa a servir a TODO o sistema, não apenas ao módulo de
    validação. Cobre interpretador/venv, todas as bibliotecas de terceiros
    usadas pelo projeto (OpenDSS, matplotlib, PuLP, PySide6, openpyxl,
    Tkinter) e a presença dos módulos internos."""
    return [
        ("Interpretador Python em uso", check_interpretador_python),
        ("Ambiente virtual (venv)", check_ambiente_virtual),
        ("Motor OpenDSS (dss-python)", check_motor_opendss),
        ("Matplotlib (gráficos e topologia)", check_matplotlib),
        ("PuLP (otimização PLIM)", check_pulp),
        ("PySide6 (interface gráfica)", check_pyside6),
        ("openpyxl (exportação Excel)", check_openpyxl),
        ("Tkinter (menu principal)", check_tkinter),
        ("Módulos do projeto presentes", check_modulos_projeto),
        ("Dados de referência IEEE", check_dados_referencia_ieee),
        ("Permissão de escrita (pasta temporária)", check_permissao_pasta_temporaria),
    ]



# ══════════════════════════════════════════════════════════════════════════
# INTERFACE GRAFICA DO DEBUGGER (PySide6)
# ══════════════════════════════════════════════════════════════════════════

if _PYSIDE6_DISPONIVEL:

    TITULO_JANELA = "Verificação de Integridade — Validação do Modelo Computacional (IEEE)"
    LARGURA_JANELA = 620

    TEMPO_AUTO_AVANCO_MS = 1200
    INTERVALO_ENTRE_CHECKS_MS = 100

    # --- Dimensoes das linhas de check (FIXAS) - usadas tanto pela
    # propria linha quanto para calcular a altura da area de scroll. ---
    ALTURA_LINHA_CHECK = 28
    ESPACAMENTO_LINHAS = 2
    MARGEM_VERTICAL_LISTA = 8
    LARGURA_INDICADOR = 20
    MAX_LINHAS_VISIVEIS_SEM_SCROLL = 8

    ALTURA_TEXTO_DETALHES = 140
    ALTURA_CABECALHO = 52

    class _BarraTituloDebugger(QFrame):
        """Cabecalho em azul institucional, arrastavel."""

        def __init__(self, titulo: str, janela: "QWidget", paleta, parent=None):
            super().__init__(parent)
            self._janela = janela
            self._posicao_arraste: Optional[QPoint] = None

            self.setFixedHeight(ALTURA_CABECALHO)
            self.setStyleSheet(
                f"""
                QFrame {{
                    background-color: #004587;
                    border-top-left-radius: {RAIO_BORDA_CARTAO}px;
                    border-top-right-radius: {RAIO_BORDA_CARTAO}px;
                }}
                """
            )

            layout = QHBoxLayout(self)
            layout.setContentsMargins(20, 0, 8, 0)

            rotulo = QLabel(titulo, self)
            rotulo.setStyleSheet("color: white; background: transparent; border: none;")
            rotulo.setFont(_resolver_fonte(12, negrito=True))
            layout.addWidget(rotulo)
            layout.addStretch(1)

            botao_fechar = QPushButton("✕", self)
            botao_fechar.setFixedSize(34, 34)
            botao_fechar.setCursor(Qt.PointingHandCursor)
            botao_fechar.setFont(_resolver_fonte(10))
            botao_fechar.setStyleSheet(
                f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    color: white;
                    border-top-right-radius: {RAIO_BORDA_CARTAO}px;
                }}
                QPushButton:hover {{ background-color: #C42B1C; }}
                QPushButton:pressed {{ background-color: #A4262C; }}
                """
            )
            botao_fechar.clicked.connect(
               lambda: getattr(self._janela, "_fechar_janela", lambda: os._exit(0))()
            )
            layout.addWidget(botao_fechar)

        def mousePressEvent(self, evento) -> None:
            if evento.button() == Qt.LeftButton:
               self._posicao_arraste = evento.globalPosition().toPoint() - self._janela.frameGeometry().topLeft()
            super().mousePressEvent(evento)

        def mouseMoveEvent(self, evento) -> None:
            if self._posicao_arraste is not None and evento.buttons() & Qt.LeftButton:
                self._janela.move(evento.globalPosition().toPoint() - self._posicao_arraste)
            super().mouseMoveEvent(evento)

        def mouseReleaseEvent(self, evento) -> None:
            self._posicao_arraste = None
            super().mouseReleaseEvent(evento)

    class _LinhaCheck(QFrame):
        """
        Uma linha da lista de checks, MINIMALISTA: indicador discreto
        a esquerda ("○" cinza / "✓" verde / "✕" vermelho) + nome do
        check (elidido se necessario). SEM animacao, SEM fundo "pill" -
        apenas mudanca de cor de texto/icone.
        """

        def __init__(self, rotulo: str, paleta, cores_status: _CoresStatus, parent=None):
            super().__init__(parent)
            self._paleta = paleta
            self._cores = cores_status
            self._texto_completo = rotulo

            self.setFixedHeight(ALTURA_LINHA_CHECK)
            self.setStyleSheet("background: transparent; border: none;")

            layout = QHBoxLayout(self)
            layout.setContentsMargins(2, 0, 2, 0)
            layout.setSpacing(8)

            self._indicador = QLabel(self)
            self._indicador.setFixedWidth(LARGURA_INDICADOR)
            self._indicador.setAlignment(Qt.AlignCenter)
            self._indicador.setFont(_resolver_fonte(11, negrito=True))
            layout.addWidget(self._indicador)

            self._label_nome = QLabel(self)
            self._label_nome.setFont(_resolver_fonte(10))
            self._label_nome.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            layout.addWidget(self._label_nome, 1)

            self.definir_pendente()

        def resizeEvent(self, evento) -> None:
            super().resizeEvent(evento)
            self._atualizar_texto_elidido()

        def _atualizar_texto_elidido(self) -> None:
            """Encurta o nome do check com '...' no meio, se nao couber
            na largura disponivel - evita que nomes longos quebrem o
            layout da linha."""
            metrica = QFontMetrics(self._label_nome.font())
            largura_disponivel = max(self._label_nome.width(), 0)
            texto_elidido = metrica.elidedText(self._texto_completo, Qt.ElideMiddle, largura_disponivel)
            self._label_nome.setText(texto_elidido)
            self._label_nome.setToolTip(self._texto_completo)

        def definir_pendente(self) -> None:
            self._indicador.setText("○")
            self._indicador.setStyleSheet(f"color: {self._cores.pendente}; background: transparent; border: none;")
            self._label_nome.setStyleSheet(
                f"color: {self._cores.pendente}; background: transparent; border: none;"
            )

        def definir_ok(self) -> None:
            self._indicador.setText("✓")
            self._indicador.setStyleSheet(f"color: {self._cores.sucesso}; background: transparent; border: none;")
            self._label_nome.setStyleSheet(
                f"color: {self._cores.sucesso}; background: transparent; border: none;"
            )

        def definir_falha(self) -> None:
            self._indicador.setText("✕")
            self._indicador.setStyleSheet(f"color: {self._cores.erro}; background: transparent; border: none;")
            self._label_nome.setStyleSheet(
                f"color: {self._cores.erro}; background: transparent; border: none;"
            )

    def _criar_botao(paleta, texto: str, principal: bool = False):
        botao = QPushButton(texto)
        botao.setFixedHeight(34)
        botao.setMinimumWidth(100)
        botao.setCursor(Qt.PointingHandCursor)
        botao.setFont(_resolver_fonte(10))

        if principal:
            botao.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {paleta.accent};
                    color: white;
                    border: none;
                    border-radius: {RAIO_BORDA_BOTAO}px;
                    padding: 0 14px;
                }}
                QPushButton:hover {{ background-color: {paleta.accent_hover}; }}
                QPushButton:pressed {{ background-color: {paleta.accent_pressed}; }}
                QPushButton:disabled {{ background-color: {paleta.borda_cartao}; color: {paleta.texto_secundario}; }}
                """
            )
        else:
            botao.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {paleta.botao_secundario_fundo};
                    color: {paleta.texto_primario};
                    border: 1px solid {paleta.borda_campo};
                    border-radius: {RAIO_BORDA_BOTAO}px;
                    padding: 0 14px;
                }}
                QPushButton:hover {{ background-color: {paleta.botao_secundario_hover}; }}
                QPushButton:pressed {{ background-color: {paleta.botao_secundario_pressed}; }}
                QPushButton:disabled {{ color: {paleta.texto_secundario}; }}
                """
            )
        return botao

    def _estilo_texto_detalhes(paleta) -> str:
        return f"""
        QTextEdit {{
            background-color: {paleta.fundo_campo};
            color: {paleta.texto_primario};
            border: 1px solid {paleta.borda_campo};
            border-radius: 6px;
            padding: 6px 8px;
        }}
        """

    def _estilo_progresso(paleta) -> str:
        return f"""
        QProgressBar {{
            background-color: {paleta.fundo_campo};
            border: none;
            border-radius: 3px;
            height: 4px;
        }}
        QProgressBar::chunk {{
            background-color: {paleta.accent};
            border-radius: 3px;
        }}
        """

    def _estilo_scroll_area(paleta) -> str:
        return f"""
        QScrollArea {{
            background-color: {paleta.fundo_campo};
            border: 1px solid {paleta.borda_campo};
            border-radius: 8px;
        }}
        QScrollArea > QWidget > QWidget {{
            background-color: transparent;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {paleta.borda_campo};
            border-radius: 4px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {paleta.texto_secundario};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        """

    class JanelaDebugger(QWidget):
        def __init__(
            self,
            checks: List[tuple],
            ao_concluir_com_sucesso: Callable[[], None],
            titulo: str = TITULO_JANELA,
        ):
            super().__init__()
            self.checks = checks
            self.ao_concluir_com_sucesso = ao_concluir_com_sucesso
            self.titulo = titulo
            # Codigo de saida usado pelos controles de FECHAR (botao "Fechar" e
            # o "X" do cabecalho). No fluxo do projeto, fechar = abortar a
            # abertura do menu principal -> 1 (definido por
            # ``iniciar_debugger_projeto``).
            self.codigo_fechar = 0

            self.tema_resolvido = _resolver_tema()
            self.paleta = _resolver_paleta(self.tema_resolvido)
            self.cores_status = _resolver_cores_status(self.tema_resolvido)

            self.linhas_check: List[_LinhaCheck] = []
            self.todos_ok = True
            self._indice_atual = 0

            self.setWindowFlags(Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setFont(_resolver_fonte(10))

            # Largura FIXA (consistencia visual) - a ALTURA e deixada
            # para o proprio Qt medir (ver _finalizar_dimensionamento).
            self.setFixedWidth(LARGURA_JANELA)

            self._montar_layout()
            self._finalizar_dimensionamento()
            self._centralizar_na_tela()

            QTimer.singleShot(300, self._executar_checks)

        # --------------------------------------------------------------
        # LAYOUT
        # --------------------------------------------------------------

        def _montar_layout(self) -> None:
            layout_externo = QVBoxLayout(self)
            layout_externo.setContentsMargins(16, 16, 16, 16)

            self._cartao = QFrame(self)
            self._cartao.setObjectName("cartao")
            self._cartao.setStyleSheet(
                f"""
                QFrame#cartao {{
                    background-color: {self.paleta.fundo_cartao};
                    border: 1px solid {self.paleta.borda_cartao};
                    border-radius: {RAIO_BORDA_CARTAO}px;
                }}
                """
            )

            sombra = QGraphicsDropShadowEffect(self._cartao)
            sombra.setBlurRadius(36)
            sombra.setXOffset(0)
            sombra.setYOffset(8)
            r, g, b, a = getattr(self.paleta, "sombra_cor", (0, 0, 0, 90))
            sombra.setColor(QColor(r, g, b, a))
            self._cartao.setGraphicsEffect(sombra)

            layout_externo.addWidget(self._cartao)

            layout_cartao = QVBoxLayout(self._cartao)
            layout_cartao.setContentsMargins(0, 0, 0, 0)
            layout_cartao.setSpacing(0)

            layout_cartao.addWidget(
               _BarraTituloDebugger(self.titulo, self, self.paleta)
            )

            area_conteudo = QWidget(self._cartao)
            layout_conteudo = QVBoxLayout(area_conteudo)
            layout_conteudo.setContentsMargins(20, 16, 20, 16)
            layout_conteudo.setSpacing(10)

            rotulo_checks = QLabel("Checks")
            rotulo_checks.setFont(_resolver_fonte(10, negrito=True))
            rotulo_checks.setStyleSheet(
                f"color: {self.paleta.texto_primario}; border: none; background: transparent;"
            )
            layout_conteudo.addWidget(rotulo_checks)

            # --- Area da lista de checks: altura calculada a partir
            # das MESMAS constantes usadas em cada _LinhaCheck. ---
            linhas_visiveis = min(len(self.checks), MAX_LINHAS_VISIVEIS_SEM_SCROLL)
            altura_area_checks = (
                linhas_visiveis * ALTURA_LINHA_CHECK
                + max(linhas_visiveis - 1, 0) * ESPACAMENTO_LINHAS
                + MARGEM_VERTICAL_LISTA * 2
            )

            self._scroll_checks = QScrollArea()
            self._scroll_checks.setWidgetResizable(True)
            self._scroll_checks.setFixedHeight(altura_area_checks)
            self._scroll_checks.setStyleSheet(_estilo_scroll_area(self.paleta))
            self._scroll_checks.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._scroll_checks.setFrameShape(QFrame.NoFrame)

            conteudo_scroll = QWidget()
            layout_lista = QVBoxLayout(conteudo_scroll)
            layout_lista.setContentsMargins(12, MARGEM_VERTICAL_LISTA, 12, MARGEM_VERTICAL_LISTA)
            layout_lista.setSpacing(ESPACAMENTO_LINHAS)

            for rotulo, _funcao in self.checks:
                linha = _LinhaCheck(rotulo, self.paleta, self.cores_status)
                linha.setFixedHeight(ALTURA_LINHA_CHECK)
                layout_lista.addWidget(linha)
                self.linhas_check.append(linha)

            layout_lista.addStretch(1)
            self._scroll_checks.setWidget(conteudo_scroll)
            layout_conteudo.addWidget(self._scroll_checks)

            self.barra_progresso = QProgressBar()
            self.barra_progresso.setTextVisible(False)
            self.barra_progresso.setFixedHeight(4)
            self.barra_progresso.setStyleSheet(_estilo_progresso(self.paleta))
            self.barra_progresso.setRange(0, len(self.checks))
            self.barra_progresso.setValue(0)
            layout_conteudo.addWidget(self.barra_progresso)

            rotulo_detalhes = QLabel("Detalhes")
            rotulo_detalhes.setFont(_resolver_fonte(10, negrito=True))
            rotulo_detalhes.setStyleSheet(
                f"color: {self.paleta.texto_primario}; border: none; background: transparent;"
            )
            layout_conteudo.addWidget(rotulo_detalhes)

            self.texto_detalhes = QTextEdit()
            self.texto_detalhes.setReadOnly(True)
            self.texto_detalhes.setFixedHeight(ALTURA_TEXTO_DETALHES)
            self.texto_detalhes.setFont(QFont("Consolas", 9))
            self.texto_detalhes.setStyleSheet(_estilo_texto_detalhes(self.paleta))
            layout_conteudo.addWidget(self.texto_detalhes)

            linha_botoes = QHBoxLayout()
            self.botao_tentar_novamente = _criar_botao(self.paleta, "Tentar novamente", principal=False)
            self.botao_tentar_novamente.setEnabled(False)
            self.botao_tentar_novamente.clicked.connect(self._executar_checks)
            linha_botoes.addWidget(self.botao_tentar_novamente)

            linha_botoes.addStretch(1)

            self.botao_continuar_manual = _criar_botao(self.paleta, "Continuar mesmo assim", principal=False)
            self.botao_continuar_manual.setEnabled(False)
            self.botao_continuar_manual.clicked.connect(self._prosseguir)
            linha_botoes.addWidget(self.botao_continuar_manual)

            self.botao_fechar = _criar_botao(self.paleta, "Fechar", principal=False)
            self.botao_fechar.clicked.connect(self._fechar_janela)
            linha_botoes.addWidget(self.botao_fechar)

            layout_conteudo.addLayout(linha_botoes)

            layout_cartao.addWidget(area_conteudo)

        def _fechar_janela(self) -> None:
            """Encerra o processo com o codigo de saida de FECHAR.

            No fluxo do debugger do projeto, ``codigo_fechar`` e 1 - o
            processo encerra SEM lancar o menu principal, ou seja, aborta a
            abertura do sistema.
            """
            os._exit(getattr(self, "codigo_fechar", 0))

        def _finalizar_dimensionamento(self) -> None:
            """
            Deixa o PROPRIO QT medir a altura necessaria (sizeHint real
            de cada widget filho, respeitando a LARGURA FIXA ja
            definida) - evita o calculo manual "chutado" que causava
            o aspecto quebrado/cortado.
            """
            self.adjustSize()
            self.setFixedHeight(self.sizeHint().height())

        def _centralizar_na_tela(self) -> None:
            tela = QApplication.primaryScreen()
            if tela is None:
                return
            geometria_tela = tela.availableGeometry()
            x = geometria_tela.center().x() - self.width() // 2
            y = geometria_tela.center().y() - self.height() // 2
            self.move(x, y)

        # --------------------------------------------------------------
        # LOG (apenas na tela - QTextEdit - nunca em arquivo)
        # --------------------------------------------------------------

        def _log(self, mensagem: str) -> None:
            self.texto_detalhes.append(mensagem)

        # --------------------------------------------------------------
        # EXECUCAO DOS CHECKS (sequencial, via QTimer)
        # --------------------------------------------------------------

        def _executar_checks(self) -> None:
            self.botao_tentar_novamente.setEnabled(False)
            self.botao_continuar_manual.setEnabled(False)
            self.barra_progresso.setValue(0)
            self.texto_detalhes.clear()

            for linha in self.linhas_check:
                linha.definir_pendente()

            self.todos_ok = True
            self._indice_atual = 0
            QTimer.singleShot(0, self._executar_check_indice)

        def _executar_check_indice(self) -> None:
            if self._indice_atual >= len(self.checks):
                self._finalizar_checks()
                return

            indice = self._indice_atual
            rotulo, funcao_check = self.checks[indice]
            linha = self.linhas_check[indice]

            try:
                resultado = funcao_check()
            except Exception as erro:
                resultado = ResultadoCheck(False, f"Erro inesperado ao executar o check: {erro}")

            if resultado.ok:
                linha.definir_ok()
                self._log(f"[OK] {rotulo}: {resultado.mensagem}")
            else:
                linha.definir_falha()
                self._log(f"[FALHA] {rotulo}: {resultado.mensagem}")
                self.todos_ok = False

            self.barra_progresso.setValue(indice + 1)
            self._indice_atual += 1
            QTimer.singleShot(INTERVALO_ENTRE_CHECKS_MS, self._executar_check_indice)

        def _finalizar_checks(self) -> None:
            if self.todos_ok:
                self._log("\nTodas as verificações concluídas com sucesso.")
                self._log(f"Prosseguindo em {TEMPO_AUTO_AVANCO_MS // 1000} segundo(s)...")
                QTimer.singleShot(TEMPO_AUTO_AVANCO_MS, self._prosseguir)
            else:
                self._log(
                    "\nUma ou mais verificações falharam. Corrija os itens acima e clique em "
                    "'Tentar novamente', ou continue mesmo assim por sua conta e risco."
                )
                self.botao_tentar_novamente.setEnabled(True)
                self.botao_continuar_manual.setEnabled(True)

        # --------------------------------------------------------------
        # PROSSEGUIR (abrir o menu principal)
        # --------------------------------------------------------------

        def _prosseguir(self) -> None:
            """Callback de sucesso ('Continuar mesmo assim' ou todos os
            checks OK): dispara a acao de continuidade definida pelo
            chamador (no fluxo do projeto, LANCA o menu principal)."""
            try:
                self.ao_concluir_com_sucesso()
            except Exception as erro:
                tratar_erro_critico("Falha ao prosseguir a partir da verificação de integridade", erro)
                os._exit(1)


# ═════════════════════════════════════════════════════════════════════════
# PONTO DE ENTRADA
# ═════════════════════════════════════════════════════════════════════════


def _preparar_ambiente_qt():
    """Valida PySide6, prepara o sys.path e retorna a QApplication
    singleton. Em qualquer falha, exibe erro critico e encerra (os._exit(1)).

    Retorna a instancia de QApplication (nunca None em caso de sucesso).
    """
    if not _PYSIDE6_DISPONIVEL:
        tratar_erro_critico(
            "Falha ao inicializar a interface gráfica (PySide6)",
            _ERRO_IMPORT_PYSIDE6,
        )
        os._exit(1)

    try:
        pasta_bibliotecas = str(_pasta_bibliotecas())
        if not _esta_empacotado() and pasta_bibliotecas not in sys.path:
            sys.path.insert(0, pasta_bibliotecas)
    except Exception as erro:
        tratar_erro_critico("Falha ao preparar o caminho do projeto", erro)
        os._exit(1)

    try:
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        app.setFont(_resolver_fonte(10))
    except Exception as erro:
        tratar_erro_critico("Falha ao inicializar a interface gráfica (PySide6/Qt)", erro)
        os._exit(1)

    return app



def iniciar_debugger_projeto(
    titulo: str = "Verificação de Integridade — TCC OpenDSS",
    ao_abrir_menu: Optional[Callable[[], None]] = None,
) -> int:
    """Fluxo de integridade do PROJETO INTEIRO - e a PRIMEIRA coisa que o
    tcc_opendss.bat executa (depois de verificar_dependencias.py, no console).

    Executa os checks GERAIS (``montar_checks_projeto``) e, ao concluir,
    LANCA O MENU PRINCIPAL (tcc_opendss.py) e ENCERRA este processo:

        - Todos os checks OK -> lanca o menu e encerra com codigo 0.
        - "Continuar mesmo assim" (com falhas) -> lanca o menu e encerra
          com codigo 0.
        - "Fechar" / "X" -> encerra com codigo 1, SEM lancar o menu (aborta
          a abertura do sistema).

    TRANSPARENCIA TECNICA (lancamento do menu): no projeto de referencia a
    interface abre na MESMA QApplication. Aqui o menu e Tkinter - toolkit
    e PROCESSO proprios - entao o debugger o lanca via subprocess e
    encerra, preservando o MESMO fluxo de experiencia (ver nota no topo do
    arquivo). O menu roda com ``sys.executable`` (python do venv, ativo
    neste processo) e cwd = pasta do proprio menu (tcc_opendss.py), de
    onde ele resolve seus caminhos relativos.

    TRANSPARENCIA TECNICA (modo congelado - ``ao_abrir_menu``): no .exe nao
    existe "tcc_opendss.py" em disco e ``sys.executable`` e o PROPRIO
    executavel - o subprocess acima nao tem o que lancar. O chamador
    congelado (tcc_opendss.py, ``main()``) passa ``ao_abrir_menu``: nesse
    caso o menu e aberto IN-PROCESS, na MESMA QApplication, sem subprocess
    e sem ``os._exit``. Assim o fluxo .bat fica INTOCADO (parametro
    opcional, default None = comportamento anterior, byte a byte) e o
    ``iniciar_debugger_projeto()`` do ``__main__`` do debugger continua
    valendo para o modo script. o menu permanece vivo no mesmo processo:
    a janela do debugger se recolhe (hide) e o encerramento ocorre ao
    fechar o menu.

    Retorna o codigo de saida do processo (0 = menu lancado, 1 = abortar).
    """
    app = _preparar_ambiente_qt()

    estado = {"janela_debugger": None}

    def ao_concluir_projeto() -> None:
        """Callback do caminho de SUCESSO (ou 'Continuar mesmo assim'):
        loga a conclusao, LANCA o menu principal e encerra a QApplication
        com codigo 0 apos um pequeno atraso, para o usuario ler o
        resultado."""
        janela = estado["janela_debugger"]
        if janela is not None:
            janela._log("\nTudo OK — abrindo o menu principal...")

        # --- Ramo congelado: abertura IN-PROCESS, nunca subprocess ---
        if ao_abrir_menu is not None:
            try:
                ao_abrir_menu()
            except Exception as erro:
                tratar_erro_critico("Falha ao abrir o menu principal", erro)
                return

            # Modo congelado: o menu agora é a janela viva DESTE processo
            # (mesma QApplication). NÃO agendar quit() — o quit do fluxo
            # script mataria o menu embutido junto com o debugger. A
            # janela do debugger apenas se recolhe; o encerramento natural
            # ocorre quando o usuário fechar o menu
            # (setQuitOnLastWindowClosed).
            janela_debugger_embutida = estado["janela_debugger"]
            if janela_debugger_embutida is not None:
                janela_debugger_embutida.hide()
            app.setQuitOnLastWindowClosed(True)
            return

        # Resolve o caminho do menu: o menu vive UM NÍVEL ACIMA da raiz do
        # projeto, ao lado do tcc_opendss.bat (layout do pacote zipável,
        # decisão do pesquisador):
        #   _pasta_projeto() = "<...>/tcc_opendss"
        #   menu             = "<...>/tcc_opendss.py"  (irmão do .bat)
        # HISTÓRICO DE CORREÇÕES DESTE PONTO: (1) a versão original subia um
        # nível a mais e apontava para "<...>/tcc/tcc_opendss.py" (não
        # existia; morte silenciosa sob pythonw); (2) depois apontava para
        # "<...>/tcc_opendss/tcc_opendss.py"; (3) ATUAL: o menu foi movido
        # PARA FORA da pasta do projeto, ao lado do .bat.
        caminho_menu = _pasta_projeto().parent / "tcc_opendss.py"

        if not caminho_menu.is_file():
            tratar_erro_critico(
                "Falha ao abrir o menu principal",
                FileNotFoundError(f"Menu principal não encontrado em: {caminho_menu}"),
            )
            os._exit(1)

        try:
            subprocess.Popen(
                [sys.executable, str(caminho_menu)],
                cwd=str(caminho_menu.parent),
                close_fds=True,
            )
        except Exception as erro:
            tratar_erro_critico("Falha ao abrir o menu principal", erro)
            os._exit(1)

        def _encerrar():
            app_qt = QApplication.instance()
            if app_qt is not None:
                app_qt.setQuitOnLastWindowClosed(True)
                app_qt.quit()

        QTimer.singleShot(800, _encerrar)

    try:
        janela_debugger = JanelaDebugger(
            montar_checks_projeto(),
            ao_concluir_com_sucesso=ao_concluir_projeto,
            titulo=titulo,
        )
        # Fechar sem prosseguir = abortar (o .bat decide nao abrir o menu).
        janela_debugger.codigo_fechar = 1
        estado["janela_debugger"] = janela_debugger
        janela_debugger.show()
    except Exception as erro:
        tratar_erro_critico("Falha durante a execução da verificação de integridade", erro)
        return 1

    return app.exec()


if __name__ == "__main__":
    sys.exit(iniciar_debugger_projeto())
