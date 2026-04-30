# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules
from pathlib import Path


project_root = Path(SPECPATH).parents[1]


datas = [
    (str(project_root / "matokeo" / "templates"), "matokeo/templates"),
    (str(project_root / "static"), "static"),
]

hiddenimports = (
    collect_submodules("accounts")
    + collect_submodules("config")
    + collect_submodules("matokeo")
    + collect_submodules("django")
    + collect_submodules("webview")
    + ["waitress"]
)


a = Analysis(
    [str(project_root / "desktop.py")],
    pathex=[str(project_root)],
    binaries=[],
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
    name="MatokeoRMS",
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
    icon=str(project_root / "packaging" / "windows" / "matokeo-rms.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MatokeoRMS",
)
