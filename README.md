# Editora PDFEdit

An offline PDF toolbox for Windows (Flask + pypdf + pypdfium2 + Tesseract OCR). Everything is done
with the mouse, in the app's own window, and your files never leave your computer.

Developer: **Kanishka Meddegoda** - https://lk.linkedin.com/in/kanishka-in  
The **ⓘ icon (top right)** opens the About page: version, developer, license, privacy and
third-party licenses.

## Tools

| Group | Tool | What it does |
|-------|------|--------------|
| Organize | **Merge** | Each PDF is a card - drag cards to set the order |
| | **Split** | By ranges, every page, every N pages, or extract pages into one PDF |
| | **Remove pages** | Click pages to put a red cross on them, or type `1, 4, 8-10` |
| | **Organize pages** | Drag page thumbnails; Reverse / Shuffle / Reset |
| | **Rotate** | Rotate single pages or everything |
| Optimize | **Compress** | Less / Recommended / Extreme, shows before and after size |
| | **OCR PDF** | Scanned PDF -> searchable PDF or .txt (English, Sinhala, Tamil included) |
| Convert | **Image to PDF** | JPG, PNG, WebP, GIF, BMP, TIFF -> PDF |
| | **PDF to JPG** | Every page as JPG or PNG (72 / 150 / 300 DPI) |
| | **PDF to Word** | Text into .docx or .txt |
| Edit | **Page numbers**, **Watermark** | |
| Security | **Protect**, **Unlock** | AES-256 password |

Every result opens on a preview page where you can rename the file before downloading.

## Build the Windows app

All builds run on Windows and need internet the first time. Python 3.12 is recommended (the scripts
pick it automatically if it is installed).

| Script | Result |
|--------|--------|
| **`build_exe.bat`** | `dist\Editora PDFEdit.exe` - ONE file with everything inside, **including the OCR engine and the English/Sinhala/Tamil language data** |
| **`build_store.bat`** | `dist\EditoraPDFEdit_<version>_x64.msix` - package for the **Microsoft Store** (see `store\README.md`) |

Both call `setup_build.bat`, which creates the virtual environment, installs the packages, and gets the
OCR engine: it uses Tesseract if it is already installed, otherwise installs it with `winget` (Windows
asks for permission once) and copies it into `vendor\tesseract`. More OCR languages: edit `OCR_LANGS`
at the top of `setup_build.bat`.

How the app runs: double-click -> a Microsoft Edge "app window" (no tabs) opens; closing it quits the
app (it also quits by itself a few minutes after the window is gone). A second launch just opens another
window. If something fails at start-up, details are written to `%LOCALAPPDATA%\Editora PDFEdit\app.log`.
For troubleshooting, set `EDITORA_CONSOLE=1` before building to keep a console window.

The standalone exe is not code-signed, so SmartScreen may warn on first run ("More info -> Run anyway").
Store-distributed packages are signed by Microsoft.

## Run from source (development)

```bat
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
python launcher.py        :: or: python app.py
```
OCR from source needs Tesseract installed (https://github.com/UB-Mannheim/tesseract/wiki) or a
`vendor\tesseract` folder prepared by `setup_build.bat`. Tests: `python tests\test_app.py`

## Project layout
```
app.py            routes + JSON API, About/licenses       tools.py   split, compress, convert, watermark...
pdf_ops.py        merge / remove / reorder                ocr.py     Tesseract wrapper (finds the bundled copy)
thumbs.py         page + image thumbnails                 store.py   in-memory store with expiry
launcher.py       app window, single instance, auto-quit  heartbeat.py
pdf_editor.spec   PyInstaller recipe                      setup_build.bat / build_exe.bat / build_store.bat
LICENSE.txt  THIRD_PARTY_NOTICES.txt  PRIVACY.md          ocr_languages/  (eng, sin, tam language data)
store/            Microsoft Store: manifest template, tile images, make_msix.py, README.md, listing images
templates/  static/  tests/
```

## Limits
- **PDF to Word** extracts text and re-flows paragraphs; tables, columns and images are not kept, and a
  scanned PDF needs OCR first. Word/Excel/PowerPoint -> PDF is not included (it needs Office or LibreOffice).
- **OCR to PDF** rebuilds pages from images, so the file can grow. Accuracy depends on the scan.
- **Watermark** supports Latin letters and numbers only. Limit: 100 MB per file.
- Uploads are kept in memory for up to 1 hour of inactivity, results for 30 minutes; nothing is written to disk.
