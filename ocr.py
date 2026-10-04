"""OCR with the Tesseract engine (a separate free program - see README)."""
import os
import shutil
import subprocess
import sys
import tempfile
from io import BytesIO

from pypdf import PdfReader, PdfWriter

from pdf_ops import PdfEditError, plural
from tools import render_page

INSTALL_HINT = ("The OCR engine (Tesseract) was not found. Install it from "
                "https://github.com/UB-Mannheim/tesseract/wiki (tick the languages you need), "
                "then restart this app.")
BUNDLED_HINT = ("The OCR engine is missing from this copy of the app. "
                "Please reinstall Editora PDFEdit.")

LANG_NAMES = {
    "eng": "English", "sin": "Sinhala", "tam": "Tamil", "hin": "Hindi", "ben": "Bengali",
    "urd": "Urdu", "ara": "Arabic", "fra": "French", "deu": "German", "spa": "Spanish",
    "ita": "Italian", "por": "Portuguese", "nld": "Dutch", "rus": "Russian", "ukr": "Ukrainian",
    "pol": "Polish", "tur": "Turkish", "ell": "Greek", "heb": "Hebrew", "tha": "Thai",
    "vie": "Vietnamese", "ind": "Indonesian", "jpn": "Japanese", "kor": "Korean",
    "chi_sim": "Chinese (Simplified)", "chi_tra": "Chinese (Traditional)", "mal": "Malayalam",
    "tel": "Telugu", "kan": "Kannada", "mar": "Marathi", "nep": "Nepali",
}


def is_packaged():
    """True inside the PyInstaller .exe (where the OCR engine is bundled)."""
    return bool(getattr(sys, "frozen", False))


def install_hint():
    return BUNDLED_HINT if is_packaged() else INSTALL_HINT


def _app_dirs():
    """Folders that may hold a bundled 'tesseract' folder: inside the exe, then next to it."""
    dirs = []
    if getattr(sys, "_MEIPASS", None):
        dirs.append(sys._MEIPASS)
    if is_packaged():
        dirs.append(os.path.dirname(sys.executable))
    else:
        dirs.append(os.path.dirname(os.path.abspath(__file__)))
        dirs.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
    return dirs


def find_tesseract():
    """Path to tesseract, or None. Bundled copy first, then TESSERACT_CMD, PATH, usual folders."""
    candidates = []
    for base in _app_dirs():
        for name in ("tesseract.exe", "tesseract"):
            candidates.append(os.path.join(base, "tesseract", name))
    candidates.append(os.environ.get("TESSERACT_CMD", ""))
    candidates.append(shutil.which("tesseract") or "")
    if os.name == "nt":
        candidates += [r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                       r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                       os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe")]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _run(args, timeout=300):
    env = os.environ.copy()
    own_data = os.path.join(os.path.dirname(args[0]), "tessdata")   # language files next to the engine
    if os.path.isdir(own_data):
        env["TESSDATA_PREFIX"] = own_data
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.run(args, capture_output=True, timeout=timeout, env=env, creationflags=flags)


def languages():
    """[(code, display name)] for the installed Tesseract languages."""
    exe = find_tesseract()
    if not exe:
        return []
    try:
        out = _run([exe, "--list-langs"], timeout=30).stdout.decode("utf-8", "replace")
    except Exception:
        return []
    codes = [ln.strip() for ln in out.splitlines()[1:] if ln.strip() and ln.strip() != "osd"]
    result = [(c, LANG_NAMES.get(c, c)) for c in codes]
    return sorted(result, key=lambda item: (item[0] != "eng", item[1].lower()))


def ocr_pdf(data, total, lang, output, dpi, progress=None):
    """OCR every page. output: 'pdf' (searchable PDF) or 'txt'. Returns (data, ext, info)."""
    exe = find_tesseract()
    if not exe:
        raise PdfEditError(install_hint())

    writer = PdfWriter()
    texts = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(total):
            if progress:
                progress(i, total)
            image_path = os.path.join(tmp, f"page{i}.jpg")
            render_page(data, i, dpi).save(image_path, "JPEG", quality=85, dpi=(dpi, dpi))
            base = os.path.join(tmp, f"out{i}")
            try:
                result = _run([exe, image_path, base, "-l", lang, output])
            except subprocess.TimeoutExpired:
                raise PdfEditError(f"OCR took too long on page {i + 1}.")
            if result.returncode != 0:
                detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
                raise PdfEditError(f"OCR failed on page {i + 1}: {detail[-1] if detail else 'unknown error'}")
            if output == "pdf":
                for page in PdfReader(base + ".pdf").pages:
                    writer.add_page(page)
            else:
                with open(base + ".txt", encoding="utf-8", errors="replace") as f:
                    texts.append(f.read().strip())
        if progress:
            progress(total, total)

    names = ", ".join(LANG_NAMES.get(c, c) for c in lang.split("+"))
    if output == "pdf":
        buf = BytesIO()
        writer.write(buf)
        out, ext = buf.getvalue(), ".pdf"
        lines = [f"Language: {names}", "You can now search and select text in the PDF.",
                 "Pages are rebuilt from images, so the file size can grow."]
    else:
        out = "\n\n\n".join(texts).encode("utf-8")
        ext = ".txt"
        lines = [f"Language: {names}", f"{len(out.split()):,} words recognised"]
    return out, ext, {"title": f"OCR finished — {plural(total)}", "lines": lines}
