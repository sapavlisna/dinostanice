# -*- mode: python ; coding: utf-8 -*-
"""Balík stanice pro Windows bez Pythonu: pyinstaller dinostanice.spec

Výchozí je one-dir (složka `dist/DinoStanice`), protože one-file rozbaluje při
každém startu ~180 MB knihoven do temp. `DINO_ONEFILE=1` udělá jediný exe —
zůstává tu proto, aby se poměr startů dal kdykoli přeměřit, ne k rozdávání.
"""

import os

from PyInstaller.utils.hooks import collect_submodules

ONEFILE = bool(os.environ.get("DINO_ONEFILE"))

# read-only data: čtou se z rozbaleného balíku (paths.resource_root()).
# data/catch, data/trash, data/rejected ani state.json tu být nesmí — ty
# vznikají vedle exe, aby přežily vypnutí (paths.data_root()).
datas = [
    ("web", "web"),
    ("data/models3d", "data/models3d"),
    ("data/templates", "data/templates"),
    ("data/shapes3d", "data/shapes3d"),
]

# uvicorn si workery, protokoly a event loopy loaduje jménem za běhu, takže je
# analýza importů nevidí a exe by spadl až při prvním požadavku; multipart si
# stejně tak hledá Starlette při uploadu a qrcode svoje backendy při /api/qr
hiddenimports = collect_submodules("uvicorn") + [
    "multipart",
    "qrcode.image.pil",
    "PIL.Image",
]

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "playwright",
              "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if ONEFILE:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="DinoStanice",
        debug=False,
        strip=False,
        upx=False,
        console=True,
        icon=None,
    )
else:
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name="DinoStanice",
        debug=False,
        strip=False,
        upx=False,
        console=True,
        icon=None,
    )
    coll = COLLECT(
        exe, a.binaries, a.datas,
        strip=False,
        upx=False,
        name="DinoStanice",
    )
