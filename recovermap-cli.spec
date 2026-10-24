# -*- mode: python ; coding: utf-8 -*-
# Build do executavel CLI (console) — enxuto: so pytsk3, sem Qt.
# Mesmo engine do GUI: mapa + recuperacao ilimitada.
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("pytsk3")

a = Analysis(
    ["recovermap/cli.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="RecoverMap-cli",
    console=True,
    upx=False,
    icon=None,
)
