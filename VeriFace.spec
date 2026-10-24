# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec - builds a single-file VeriFace.exe (no console window).

customtkinter ships theme JSON/assets that must be bundled or the GUI crashes,
so we collect_all it. OpenCV, numpy and Pillow are handled by PyInstaller's
built-in hooks.
"""
from PyInstaller.utils.hooks import collect_all

ctk_datas, ctk_binaries, ctk_hidden = collect_all("customtkinter")

a = Analysis(
    ["src/veriface/__main__.py"],
    pathex=["src"],
    binaries=ctk_binaries,
    datas=ctk_datas,
    hiddenimports=ctk_hidden + ["PIL._tkinter_finder"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter.test", "test", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VeriFace",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # GUI app: no console window
    disable_windowed_traceback=False,
    icon=None,
)
