# -*- mode: python ; coding: utf-8 -*-
"""Receita de empacotamento do TCC OpenDSS (PyInstaller, modo onedir).

Este arquivo espelha o construir_executavel.bat e, desde que passou a ser
versionado, e a FONTE UNICA das opcoes de empacotamento. O .bat deixou de
apagar o spec a cada execucao: ele agora cuida da limpeza de build/ e dist/,
da verificação do interpretador e da chamada a "pyinstaller TccOpendss.spec".
Quem quiser reproduzir a distribuição sem o .bat roda o mesmo comando na raiz.

Os dados do projeto NÃO entram em Analysis(datas). No PyInstaller 6, em modo
onedir, um data colocado ali termina dentro de _internal/, mas o modo
congela (bibliotecas/projeto.py) resolve os dados a partir de sys.executable
e espera a pasta tcc_opendss/ AO LADO do .exe. A cópia é feita depois do
COLLECT, com shutil, reproduzindo o robocopy que o .bat fazia — e assim a
pasta IEEE/ também não entra duas vezes no pacote (uma pelo Analysis, outra
pela cópia).

_cffi_backend é hidden-import obrigatório. O pacote dss delega ao
dss_python_backend, que executa "from _cffi_backend import ..." já no import;
o hook do PyInstaller cobre apenas o cffi em Python puro. Sem esta linha o
.exe aborta no arranque com ModuleNotFoundError.
"""

import os
import shutil

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Pacotes que dependem de dados/binários próprios (backend nativo do OpenDSS,
# solver CBC do PuLP). collect_all recolhe módulos, binários e datas de uma vez.
bloco = []
binarios = []
ocultos = []
for pacote in ('dss', 'pulp'):
    b_pacote, bin_pacote, h_pacote = collect_all(pacote)
    bloco += b_pacote
    binarios += bin_pacote
    ocultos += h_pacote

# Os 47 módulos da biblioteca, inclusive os lançadores que só são importados
# dentro de subprocesso (modo script) e o constantes_controle.py, que é vazio
# e por isso escapa do collect_submodules.
ocultos += collect_submodules('bibliotecas')
ocultos += [
    'bibliotecas.editor_rede',
    'bibliotecas.otimizacao_lancador',
    'bibliotecas.dimensionamento_lancador',
    'bibliotecas.ao_vivo_lancador',
    'bibliotecas.validacao_lancador',
    'bibliotecas.constantes_controle',
    '_cffi_backend',
]

a = Analysis(
    ['tcc_opendss.py'],
    pathex=['tcc_opendss'],
    binaries=binarios,
    datas=bloco,
    hiddenimports=ocultos,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TccOpendss',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='TccOpendss',
)

# ---------------------------------------------------------------------------
# Dados da distribuição, copiados ao lado do .exe (layout que projeto.py
# espera no modo congelado). Idempotente: rodar o build duas vezes não
# duplica nada, porque copytree roda com dirs_exist_ok.
# ---------------------------------------------------------------------------

DESTINO = os.path.join('dist', 'TccOpendss')

PASTAS = [
    ('tcc_opendss/projetos', 'tcc_opendss/projetos'),
    ('tcc_opendss/hardware', 'tcc_opendss/hardware'),
    ('tcc_opendss/validacao_ieee', 'tcc_opendss/validacao_ieee'),
    ('IEEE', 'IEEE'),
    ('doc', 'doc'),
]

ARQUIVOS = [
    ('tcc_opendss/verificar_dependencias.py', 'tcc_opendss/verificar_dependencias.py'),
    ('LICENSE.md', 'LICENSE.md'),
    ('README.md', 'README.md'),
]

for origem, relativo in PASTAS:
    if not os.path.isdir(origem):
        print('[AVISO] pasta ausente, ignorada:', origem)
        continue
    shutil.copytree(origem, os.path.join(DESTINO, relativo), dirs_exist_ok=True)
    print('[OK]', relativo)

for origem, relativo in ARQUIVOS:
    if not os.path.isfile(origem):
        print('[AVISO] arquivo ausente, ignorado:', origem)
        continue
    destino_arquivo = os.path.join(DESTINO, relativo)
    os.makedirs(os.path.dirname(destino_arquivo), exist_ok=True)
    shutil.copy2(origem, destino_arquivo)
    print('[OK]', relativo)
