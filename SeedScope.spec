# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_dir = Path(SPECPATH)
assets_dir = project_dir / "app" / "assets"
app_dir = project_dir / "app"

icon_file = None
icon_ico = assets_dir / "icon.ico"
icon_png = assets_dir / "icon.png"
root_icon_ico = app_dir / "icon.ico"
root_icon_png = app_dir / "icon.png"
if icon_ico.exists():
    icon_file = str(icon_ico)
elif root_icon_ico.exists():
    icon_file = str(root_icon_ico)
elif icon_png.exists():
    icon_file = str(icon_png)
elif root_icon_png.exists():
    icon_file = str(root_icon_png)

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
