# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build recipe.
#   single .exe (default):  pyinstaller --noconfirm --clean pdf_editor.spec
#   folder build for the Microsoft Store:  set EDITORA_ONEDIR=1  first
#   keep a console window for troubleshooting:  set EDITORA_CONSOLE=1
import os
from PyInstaller.utils.hooks import collect_all

ONEDIR = os.environ.get("EDITORA_ONEDIR") == "1"
CONSOLE = os.environ.get("EDITORA_CONSOLE") == "1"
NAME = "EditoraPDFEdit" if ONEDIR else "Editora PDFEdit"
ROOT = SPECPATH

datas = [("templates", "templates"), ("static", "static"),
         ("LICENSE.txt", "."), ("THIRD_PARTY_NOTICES.txt", "."), ("PRIVACY.md", ".")]
binaries = []
hiddenimports = []

# packages with native libraries or data files
for package in ("pypdfium2", "pypdfium2_raw", "docx", "reportlab"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# the OCR engine (Tesseract + language data), prepared by setup_build.bat
if os.path.isdir(os.path.join(ROOT, "vendor", "tesseract")):
    datas.append((os.path.join(ROOT, "vendor", "tesseract"), "tesseract"))
else:
    print("WARNING: vendor/tesseract not found - building WITHOUT the OCR engine")

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if ONEDIR:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, icon="icon.ico",
              debug=False, strip=False, upx=False, console=CONSOLE)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=NAME)
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=NAME, icon="icon.ico",
              debug=False, strip=False, upx=False, console=CONSOLE, runtime_tmpdir=None)
