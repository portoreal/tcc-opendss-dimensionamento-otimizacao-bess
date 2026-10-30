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
REM  Script AUTONOMO: nao chama analisar_dependencias_build.py nem
REM  qualquer utilitario externo. Tudo o que o build precisa esta aqui.
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
if exist "%SPEC%" (
    echo [LIMPEZA] "%SPEC%"
    del /f /q "%SPEC%" >nul 2>&1
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
REM  --collect-all dss               : pacote dss e o backend nativo
REM                                    (dss_python_backend: dss_capi.dll,
REM                                    libklusolvex.dll, _dss_capi.pyd)
REM  --collect-all pulp              : pulp/solverdir/cbc/win/*/cbc.exe
REM  --collect-submodules bibliotecas: garante os 47 modulos, inclusive
REM                                    os lancadores que so sao importados
REM                                    dentro de subprocesso (modo script)
REM  hidden-import dos 5 lancadores  : redundancia explicita (sao o alvo
REM                                    do shim --modulo-congelado)
REM  --hidden-import constantes_controle : modulo vazio nao era pego
REM                                    pelo collect-submodules
REM  --paths tcc_opendss             : o pacote "bibliotecas" vive dentro
REM                                    da pasta do projeto, nao na raiz
REM ------------------------------------------------------------
REM  --hidden-import _cffi_backend   : OBRIGATORIO. O pacote "dss" delega
REM                                    ao dss_python_backend, que executa
REM                                    "from _cffi_backend import ..." no
REM                                    import. A extensao compilada
REM                                    _cffi_backend.cp314-win_amd64.pyd
REM                                    NAO entra no grafo automaticamente
REM                                    (o hook do PyInstaller cobre apenas
REM                                    o pacote "cffi" em Python puro).
REM                                    Sem esta linha o .exe aborta no
REM                                    arranque com "ModuleNotFoundError:
REM                                    No module named '_cffi_backend'".
REM ------------------------------------------------------------
echo ===============================================================
echo   Empacotando com PyInstaller (pode levar 5-10 minutos)...
echo ===============================================================
echo.

"%PY%" -m PyInstaller ^
    --clean ^
    --onedir ^
    --noconsole ^
    --name %NOME% ^
    --paths "%PROJETO%" ^
    --hidden-import bibliotecas.editor_rede ^
    --hidden-import bibliotecas.otimizacao_lancador ^
    --hidden-import bibliotecas.dimensionamento_lancador ^
    --hidden-import bibliotecas.ao_vivo_lancador ^
    --hidden-import bibliotecas.validacao_lancador ^
    --hidden-import _cffi_backend ^
    --collect-submodules bibliotecas ^
    --hidden-import bibliotecas.constantes_controle ^
    --collect-all dss ^
    --collect-all pulp ^
    "%RAIZ%tcc_opendss.py"

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
