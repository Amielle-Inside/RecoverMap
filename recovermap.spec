# -*- mode: python ; coding: utf-8 -*-
# Build do executável RecoverMap (onefile, GUI) — usado pelo CI (Windows) e localmente.
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("pytsk3")
d2, b2, h2 = collect_all("PySide6")
datas += d2
binaries += b2
hiddenimports += h2

a = Analysis(
    ["recovermap/gui.py"],
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
    name="RecoverMap",
    console=False,
    upx=False,
    icon=None,
)
