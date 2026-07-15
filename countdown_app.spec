# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

root = Path(SPECPATH)
assets = [
    (str(root / "0.wav"), "."),
    (str(root / "1.wav"), "."),
    (str(root / "2.wav"), "."),
    (str(root / "3.wav"), "."),
    (str(root / "4.mp3"), "."),
    (str(root / "clock_icon.ico"), "."),
]
pixi_library_bin = Path(sys.base_prefix) / "Library" / "bin"
pixi_runtime_names = (
    "libmpdec-4.dll",
    "zstd.dll",
    "liblzma.dll",
    "libbz2.dll",
    "ffi-8.dll",
    "libexpat.dll",
    "tk86t.dll",
    "tcl86t.dll",
)
pixi_runtime = [
    (str(pixi_library_bin / name), ".")
    for name in pixi_runtime_names
    if (pixi_library_bin / name).is_file()
]

a = Analysis(
    [str(root / "countdown_app.py")],
    pathex=[str(root)],
    binaries=pixi_runtime,
    datas=assets,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "playsound",
        "pystray._appindicator",
        "pystray._darwin",
        "pystray._gtk",
        "pystray._xorg",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CountdownApp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(root / "clock_icon.ico"),
    version=str(root / "version_info.txt"),
)
