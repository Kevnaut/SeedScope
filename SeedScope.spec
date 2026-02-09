# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_dir = Path(__file__).resolve().parent
assets_dir = project_dir / "app" / "assets"

icon_file = None
icon_ico = assets_dir / "icon.ico"
icon_png = assets_dir / "icon.png"
if icon_ico.exists():
    icon_file = str(icon_ico)
elif icon_png.exists():
    icon_file = str(icon_png)

datas = []
if assets_dir.exists():
    datas.append((str(assets_dir), "app/assets"))

a = Analysis(
    ["app/main.py"],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=["PySide6.QtSvg"],
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
    name="SeedScope",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SeedScope",
)
