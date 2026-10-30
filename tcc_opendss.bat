@echo off
setlocal enabledelayedexpansion

REM ================================================================
REM TCC OpenDSS - Launcher unico
REM ================================================================
REM Padrao herdado de "materiais_terceiros_vencer_vencido2.bat"
REM (criacao automatica de venv com Python estavel) + padrao TCC
REM (o debugger de integridade e a PRIMEIRA etapa da aplicacao).
REM
REM LAYOUT DO PACOTE (tudo RELATIVO a pasta deste .bat, via %~dp0):
REM   <pasta deste .bat>\tcc_opendss.bat   <- este arquivo
REM   <pasta deste .bat>\tcc_opendss.py    <- menu principal (Tkinter)
REM   <pasta deste .bat>\tcc_opendss\      <- projeto (venv, bibliotecas,
REM                                           requirements.txt, projetos)
REM
REM   1. Localiza tudo de forma RELATIVA, a partir da pasta onde ESTE
REM      arquivo .bat esta salvo (%~dp0). Nenhum caminho absoluto.
REM   2. Se o ambiente virtual (venv) nao existir, cria
REM      automaticamente, FORCANDO uma versao ESTAVEL do Python
REM      (3.12, com fallback para 3.11 e 3.10, via "py -X.Y"), em vez
REM      de depender do "python" generico do PATH - isso evita cair
REM      em versoes muito recentes (ex.: 3.14) para as quais pacotes
REM      como dss-python/PySide6/matplotlib podem nao ter wheels
REM      publicados ainda, causando falhas silenciosas de instalacao.
REM      Ao criar, roda "pip install --upgrade pip".
REM   3. Verifica/instala as dependencias
REM      (tcc_opendss\verificar_dependencias.py) em TODA execucao, nao
REM      apenas na criacao do venv - assim, novas dependencias
REM      adicionadas ao projeto sao instaladas automaticamente mesmo
REM      se o venv ja existir, e falhas de instalacao interrompem a
REM      execucao (o script retorna errorlevel 1). Roda com o cwd na
REM      pasta do projeto, onde o script regrava o requirements.txt.
REM   4. A execucao final NAO chama o menu diretamente: dispara o
REM      verificador de integridade (tcc_opendss\bibliotecas\
REM      debugger.py), que executa os checks do projeto INTEIRO e, ao
REM      concluir, LANCA O MENU PRINCIPAL (tcc_opendss.py) via
REM      subprocess e encerra.
REM   5. As etapas 2 e 3 usam "python.exe" (console visivel), para que
REM      eventuais erros de setup/dependencias possam ser lidos. A
REM      execucao final usa "pythonw.exe" via "start", para abrir
REM      apenas a janela do debugger, sem console visivel; o .bat
REM      encerra a si mesmo logo apos disparar.
REM ================================================================

cd /d "%~dp0"

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%tcc_opendss"
set "MENU=%SCRIPT_DIR%tcc_opendss.py"
set "DEBUGGER=%PROJECT_DIR%\bibliotecas\debugger.py"
set "VERIFICAR_DEPENDENCIAS=%PROJECT_DIR%\verificar_dependencias.py"
set "VENV_DIR=%PROJECT_DIR%\venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PYTHONW=%VENV_DIR%\Scripts\pythonw.exe"
set "JA_TENTOU_CRIAR_VENV=0"

REM Versoes de Python aceitas para CRIAR o venv, em ordem de
REM preferencia (a mais estavel primeiro). Evita depender do "python"
REM generico do PATH, que pode apontar para uma versao muito recente
REM e incompativel com as dependencias do projeto (ex.: Python 3.14).
set "VERSOES_PYTHON_ACEITAS=3.12 3.11 3.10"

echo.
echo ===============================================
echo   TCC OpenDSS - Iniciando
echo ===============================================
echo.

if not exist "%MENU%" (
    echo [ERRO] Menu principal "tcc_opendss.py" nao encontrado em:
    echo   "%MENU%"
    echo.
    pause
    exit /b 1
)

if not exist "%PROJECT_DIR%" (
    echo [ERRO] Pasta do projeto nao encontrada em:
    echo   "%PROJECT_DIR%"
    echo.
    pause
    exit /b 1
)

goto :VERIFICAR_VENV


:VERIFICAR_VENV
echo ===============================================
echo   Verificando ambiente virtual...
echo ===============================================
echo.

if exist "%VENV_PYTHON%" (
    echo [OK] Ambiente virtual encontrado em:
    echo   "%VENV_DIR%"
    echo.
    "%VENV_PYTHON%" --version
    echo.
    goto :ATIVAR_VENV
)

echo [AVISO] Ambiente virtual nao encontrado em:
echo   "%VENV_DIR%"
echo.

if "%JA_TENTOU_CRIAR_VENV%"=="1" (
    echo ===============================================
    echo   [ERRO] Nao foi possivel preparar o ambiente virtual
    echo ===============================================
    echo.
    pause
    exit /b 1
)

set "JA_TENTOU_CRIAR_VENV=1"
call :CRIAR_VENV
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao criar o ambiente virtual automaticamente.
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] Ambiente virtual criado. Verificando novamente...
echo.
goto :VERIFICAR_VENV


:CRIAR_VENV
echo ===============================================
echo   Criando ambiente virtual automaticamente...
echo ===============================================
echo.

set "PYTHON_ESCOLHIDO="
set "VERSAO_ESCOLHIDA="

REM Tenta localizar uma versao ESTAVEL do Python via "py -X.Y",
REM percorrendo VERSOES_PYTHON_ACEITAS em ordem de preferencia.
for %%V in (%VERSOES_PYTHON_ACEITAS%) do (
    if not defined PYTHON_ESCOLHIDO (
        py -%%V --version >nul 2>&1
        if not errorlevel 1 (
            set "PYTHON_ESCOLHIDO=py -%%V"
            set "VERSAO_ESCOLHIDA=%%V"
        )
    )
)

if defined PYTHON_ESCOLHIDO (
    echo [OK] Versao estavel do Python localizada: %VERSAO_ESCOLHIDA%
    %PYTHON_ESCOLHIDO% --version
    echo.
    goto :CRIAR_VENV_COM_PYTHON_ESCOLHIDO
)

echo [AVISO] Nenhuma das versoes preferidas do Python foi encontrada
echo         via "py" ^(testadas: %VERSOES_PYTHON_ACEITAS%^).
echo         Tentando usar o "python" padrao do PATH do sistema...
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao foi encontrado no PATH do sistema, nem
    echo        nenhuma versao estavel foi localizada via "py".
    echo        Instale o Python 3.12 ^(ou 3.11/3.10^) e tente novamente.
    exit /b 1
)

echo [AVISO] Usando o "python" padrao do PATH ^(verifique se a versao
echo         abaixo e compativel com dss-python/PySide6/matplotlib^):
python --version
echo.

set "PYTHON_ESCOLHIDO=python"

:CRIAR_VENV_COM_PYTHON_ESCOLHIDO
%PYTHON_ESCOLHIDO% -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo [ERRO] Falha ao criar o ambiente virtual com "%PYTHON_ESCOLHIDO% -m venv".
    exit /b 1
)

echo [OK] Ambiente virtual criado.
echo.

"%VENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERRO] Falha ao atualizar o pip no ambiente virtual.
    exit /b 1
)

echo.
echo [OK] Ambiente virtual pronto para uso.
exit /b 0


:ATIVAR_VENV
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [AVISO] "activate.bat" nao encontrado no ambiente virtual em:
    echo   "%VENV_DIR%\Scripts\activate.bat"
    echo   Prosseguindo sem ativar ^(o venv sera usado pelo caminho
    echo   explicito do executavel^).
    echo.
    goto :VERIFICAR_DEPENDENCIAS
)

echo ===============================================
echo   Ativando ambiente virtual...
echo ===============================================
echo.

call "%VENV_DIR%\Scripts\activate.bat"

if errorlevel 1 (
    echo [ERRO] Falha ao ativar o ambiente virtual.
    echo.
    pause
    exit /b 1
)

echo.


:VERIFICAR_DEPENDENCIAS
echo ===============================================
echo   Verificando/instalando dependencias...
echo ===============================================
echo.

if exist "%VERIFICAR_DEPENDENCIAS%" (
    REM cwd = pasta do projeto: o script regrava "requirements.txt" nela.
    pushd "%PROJECT_DIR%"
    "%VENV_PYTHON%" "%VERIFICAR_DEPENDENCIAS%"
    set "RC_DEPENDENCIAS=!errorlevel!"
    popd

    if not "!RC_DEPENDENCIAS!"=="0" (
        echo.
        echo ===============================================
        echo   [ERRO] Falha ao instalar as dependencias do projeto
        echo ===============================================
        echo.
        echo Possiveis causas:
        echo   - A versao do Python usada no venv e incompativel com
        echo     algum pacote ^(verifique a versao exibida acima^).
        echo   - Falta de conexao com a internet / proxy / repositorio
        echo     interno de pacotes pip.
        echo.
        echo Se a causa for versao de Python incompativel, apague a
        echo pasta "venv" e execute este .bat novamente para recriar o
        echo ambiente com uma versao estavel ^(3.12, 3.11 ou 3.10^).
        echo.
        pause
        exit /b 1
    )
) else (
    echo [AVISO] Arquivo verificar_dependencias.py nao encontrado em:
    echo   "%VERIFICAR_DEPENDENCIAS%"
    echo   Pulando etapa.
)

goto :EXECUTAR


:EXECUTAR
echo.
echo ===============================================
echo   Executando TCC OpenDSS...
echo ===============================================
echo.

REM A verificacao de integridade (bibliotecas\debugger.py) e a PRIMEIRA
REM coisa da aplicacao: ela executa os checks do projeto INTEIRO e, ao
REM concluir, LANCA O MENU PRINCIPAL (tcc_opendss.py) e encerra. O .bat
REM apenas dispara o debugger e encerra a si mesmo (e o console).

if not exist "%DEBUGGER%" (
    echo [ERRO] Verificador de integridade "debugger.py" nao encontrado em:
    echo   "%DEBUGGER%"
    echo.
    pause
    exit /b 1
)

if exist "%VENV_PYTHONW%" (
    echo A janela de verificacao de integridade sera aberta em instantes...
    echo Este console sera encerrado automaticamente.
    echo.
    start "" "%VENV_PYTHONW%" "%DEBUGGER%"
    exit /b 0
)

echo [AVISO] "pythonw.exe" nao encontrado no ambiente virtual em:
echo   "%VENV_PYTHONW%"
echo   Usando "python.exe" como alternativa (o console pode permanecer visivel).
echo.
"%VENV_PYTHON%" "%DEBUGGER%"
if errorlevel 1 (
    echo.
    echo [ERRO] A execucao falhou. Verifique as mensagens acima.
    echo.
    pause
    exit /b 1
)
exit /b 0

endlocal
