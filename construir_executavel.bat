@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  TCC OpenDSS - construcao do executavel (PyInstaller onedir)
REM ============================================================
REM  Gera dist\TccOpendss\ com:
REM    TccOpendss.exe        <- menu + debugger (in-process)
REM    _internal\            <- bundle PyInstaller
REM    tcc_opendss\          <- projetos, hardware, validacao_ieee,
REM                             verificar_dependencias.py
REM    IEEE\ doc\ LICENSE.md README.md
REM
REM  Script ORQUESTRADOR: limpa os artefatos, confere o interpretador e
REM  chama "pyinstaller TccOpendss.spec". As opcoes de empacotamento e o
REM  layout dos dados estao no spec, que fica versionado junto do codigo.
REM
REM  O executavel NAO depende do interpretador que o gerou: PyInstaller
REM  embute uma copia do runtime Python + bibliotecas. O venv e usado
REM  apenas como ferramenta de construcao.
REM ============================================================

cd /d "%~dp0"

set "RAIZ=%~dp0"
set "PROJETO=%RAIZ%tcc_opendss"
set "DIST=%RAIZ%dist"
set "BUILD=%RAIZ%build"
set "NOME=TccOpendss"
set "SAIDA=%DIST%\%NOME%"
set "SPEC=%RAIZ%%NOME%.spec"

echo.
echo ===============================================================
echo   TCC OpenDSS - Construcao do Executavel
echo ===============================================================
echo   Raiz do projeto: "%RAIZ%"
echo.

REM ------------------------------------------------------------
REM  Localizacao do interpretador (venv do repositorio ou PATH)
REM ------------------------------------------------------------
set "PY="
if exist "%PROJETO%\venv\Scripts\python.exe" (
    set "PY=%PROJETO%\venv\Scripts\python.exe"
    echo [OK] venv do projeto encontrado.
) else (
    for /f "delims=" %%I in ('where python 2^>nul') do (
        if not defined PY set "PY=%%I"
    )
    if defined PY (
        echo [AVISO] venv do projeto ausente - usando python do PATH:
        echo         "!PY!"
        echo [AVISO] O build exige PySide6, matplotlib, dss-python, pulp e openpyxl.
    ) else (
        echo [ERRO] Nenhum interpretador Python encontrado.
        echo        Procurei em "%PROJETO%\venv\Scripts\python.exe" e no PATH.
        echo.
        exit /b 1
    )
)

if not exist "%PY%" (
    echo [ERRO] Interpretador nao encontrado em: "%PY%"
    echo.
    exit /b 1
)

"%PY%" -c "import sys; print('[OK] Python ' + sys.version.split()[0] + ' em ' + sys.executable)"
if errorlevel 1 (
    echo [ERRO] Falha ao executar o interpretador: "%PY%"
    echo.
    exit /b 1
)

REM ------------------------------------------------------------
REM  Ponto de entrada presente?
REM ------------------------------------------------------------
if not exist "%RAIZ%tcc_opendss.py" (
    echo [ERRO] Ponto de entrada "tcc_opendss.py" nao encontrado na raiz.
    echo.
    exit /b 1
)

REM ------------------------------------------------------------
REM  Limpeza de artefatos anteriores
REM ------------------------------------------------------------
echo.
echo ===============================================================
echo   Limpando artefatos de builds anteriores...
echo ===============================================================
echo.

if exist "%BUILD%" (
    echo [LIMPEZA] "%BUILD%"
    rmdir /s /q "%BUILD%"
)
if exist "%SAIDA%" (
    echo [LIMPEZA] "%SAIDA%"
    rmdir /s /q "%SAIDA%"
)
echo [OK] Limpeza concluida.
echo.

REM ------------------------------------------------------------
REM  PyInstaller
REM ------------------------------------------------------------
echo ===============================================================
echo   Verificando PyInstaller...
echo ===============================================================
echo.

"%PY%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] PyInstaller ausente - instalando...
    echo.
    "%PY%" -m pip install --upgrade pyinstaller
    if errorlevel 1 (
        echo.
        echo [ERRO] Falha ao instalar o PyInstaller.
        echo.
        exit /b 1
    )
) else (
    echo [INFO] PyInstaller ja presente - atualizando...
    echo.
    "%PY%" -m pip install --upgrade pyinstaller
    if errorlevel 1 (
        echo.
        echo [AVISO] Atualizacao do PyInstaller falhou - usando a versao instalada.
        echo.
    )
)
echo.

REM ------------------------------------------------------------
REM  Empacotamento
REM ------------------------------------------------------------
REM  As opcoes de empacotamento (collect-all dss e pulp, os 47 modulos da
REM  biblioteca, o hidden-import _cffi_backend, o layout de dados ao lado do
REM  .exe) vivem no TccOpendss.spec, que fica versionado. Este .bat so limpa
REM  build\ e dist\ e chama o spec - manter as flags duplicadas aqui foi o
REM  que fez o spec sumir em builds anteriores.
REM ------------------------------------------------------------
echo ===============================================================
echo   Empacotando com PyInstaller (pode levar 5-10 minutos)...
echo ===============================================================
echo.

"%PY%" -m PyInstaller --noconfirm "%SPEC%"

if errorlevel 1 (
    echo.
    echo ===============================================================
    echo   [ERRO] PyInstaller falhou - ver mensagens acima.
    echo ===============================================================
    echo.
    exit /b 1
)

if not exist "%SAIDA%\%NOME%.exe" (
    echo.
    echo [ERRO] Executavel nao gerado em "%SAIDA%\%NOME%.exe".
    echo.
    exit /b 1
)

echo.
echo [OK] Executavel gerado: "%SAIDA%\%NOME%.exe"
echo.

REM ------------------------------------------------------------
REM  Dados da distribuicao (layout espelhado ao lado do .exe)
REM ------------------------------------------------------------
echo ===============================================================
echo   Copiando dados da distribuicao...
echo ===============================================================
echo.

REM tcc_opendss\: subpastas de dados + verificador que o menu consulta
if not exist "%SAIDA%\tcc_opendss" mkdir "%SAIDA%\tcc_opendss"
for %%D in (projetos hardware validacao_ieee) do (
    if exist "%PROJETO%\%%D" (
        robocopy "%PROJETO%\%%D" "%SAIDA%\tcc_opendss\%%D" /E /NFL /NDL /NJH /NJS /NP >nul
        if errorlevel 8 (
            echo [ERRO] Falha ao copiar tcc_opendss\%%D
            exit /b 1
        )
        echo [OK] tcc_opendss\%%D
    ) else (
        echo [AVISO] "%PROJETO%\%%D" ausente - ignorado.
    )
)

if exist "%PROJETO%\verificar_dependencias.py" (
    copy /y "%PROJETO%\verificar_dependencias.py" "%SAIDA%\tcc_opendss\verificar_dependencias.py" >nul
    echo [OK] tcc_opendss\verificar_dependencias.py
) else (
    echo [AVISO] "verificar_dependencias.py" ausente - ignorado.
)

if exist "%RAIZ%IEEE" (
    robocopy "%RAIZ%IEEE" "%SAIDA%\IEEE" /E /NFL /NDL /NJH /NJS /NP >nul
    if errorlevel 8 (
        echo [ERRO] Falha ao copiar IEEE
        exit /b 1
    )
    echo [OK] IEEE
) else (
    echo [AVISO] Pasta "IEEE" ausente - ignorada.
)

if exist "%RAIZ%doc" (
    robocopy "%RAIZ%doc" "%SAIDA%\doc" /E /NFL /NDL /NJH /NJS /NP >nul
    if errorlevel 8 (
        echo [ERRO] Falha ao copiar doc
        exit /b 1
    )
    echo [OK] doc
) else (
    echo [AVISO] Pasta "doc" ausente - ignorada.
)

if exist "%RAIZ%LICENSE.md" (
    copy /y "%RAIZ%LICENSE.md" "%SAIDA%\LICENSE.md" >nul
    echo [OK] LICENSE.md
) else (
    echo [AVISO] "LICENSE.md" ausente - ignorado.
)

if exist "%RAIZ%README.md" (
    copy /y "%RAIZ%README.md" "%SAIDA%\README.md" >nul
    echo [OK] README.md
) else (
    echo [AVISO] "README.md" ausente - ignorado.
)

echo.
echo ===============================================================
echo   BUILD CONCLUIDO
echo ===============================================================
echo   Distribuicao: "%SAIDA%"
echo.
echo   Para distribuir, copie a pasta "%SAIDA%" inteira.
echo   O executavel a executar e: %NOME%.exe
echo ===============================================================
echo.

exit /b 0
