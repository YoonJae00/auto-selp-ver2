# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Auto-Selp Crawler Windows build.

Build command (Windows):
    pyinstaller build_windows.spec

Output: dist/AutoSelpCrawler/
"""

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("app/ui_qml/qml", "app/ui_qml/qml"),
        ("assets", "assets"),
    ],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickControls2",
        "PySide6.QtQuickDialogs2",
        "playwright",
        "keyring.backends",
        "keyring.backends.Windows",
        "apscheduler.schedulers.background",
        "apscheduler.triggers.interval",
        "pydantic",
        "yaml",
        "google.generativeai",
        "openai",
        "bs4",
        "pygments.lexers",
        "pygments.formatters",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "tests",
        "unittest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AutoSelpCrawler",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon="assets/icon.ico" if Path("assets/icon.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AutoSelpCrawler",
)
