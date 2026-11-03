# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['bibliotecas.editor_rede', 'bibliotecas.otimizacao_lancador', 'bibliotecas.dimensionamento_lancador', 'bibliotecas.ao_vivo_lancador', 'bibliotecas.validacao_lancador', '_cffi_backend', 'bibliotecas.constantes_controle']
hiddenimports += collect_submodules('bibliotecas')
tmp_ret = collect_all('dss')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pulp')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:/git/tcc-opendss-dimensionamento-otimizacao-bess/tcc_opendss.py'],
    pathex=['C:/git/tcc-opendss-dimensionamento-otimizacao-bess/tcc_opendss'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
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
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name='TccOpendss',
)
