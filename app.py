import os
import re
import sys
import threading
import webbrowser
from collections import OrderedDict
from io import BytesIO

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, send_file, url_for)
from PIL import Image
from werkzeug.exceptions import RequestEntityTooLarge

import heartbeat
import ocr
import pdf_ops
import thumbs
import tools
from pdf_ops import PdfEditError, PdfPasswordError
from store import Store


def resource_path(*parts):
    """Folder of this app's files - works from source and inside the PyInstaller .exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


APP_NAME = "Editora PDFEdit"
APP_VERSION = "1.0.0"
DEVELOPER = "Kanishka Meddegoda"
DEVELOPER_LINKEDIN = "https://lk.linkedin.com/in/kanishka-in"
TESSERACT_URL = "https://github.com/UB-Mannheim/tesseract/wiki"
EXTERNAL_LINKS = {DEVELOPER_LINKEDIN, TESSERACT_URL}      # the only addresses /api/open-external will open

app = Flask(__name__,
            template_folder=resource_path("templates"),
            static_folder=resource_path("static"))
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
MAX_UPLOAD_MB = 100
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

MB = 1024 * 1024
# Everything lives in memory only and expires when unused:
docs = Store(ttl=60 * 60, max_items=200, max_bytes=500 * MB)      # uploaded files
results = Store(ttl=30 * 60, max_items=25, max_bytes=300 * MB)    # finished edits
jobs = Store(ttl=60 * 60, max_items=50, max_bytes=10 ** 9)        # long-running work (OCR)
MAX_MERGE_FILES = 50
MAX_IMAGES = 100

# (id, group, icon, title, description) - the id is also the page's endpoint + template name
TOOLS = [dict(zip(("id", "group", "icon", "title", "desc"), row)) for row in [
    ("merge", "Organize PDF", "🔗", "Merge PDFs", "Combine several PDFs into one, in the order you choose."),
    ("split", "Organize PDF", "✂️", "Split PDF", "Split by range, into single pages, or extract pages."),
    ("remove", "Organize PDF", "🗑️", "Remove pages", "Click pages to delete them, or type a range."),
    ("organize", "Organize PDF", "🔀", "Organize pages", "Drag pages into a new order, reverse or shuffle."),
    ("rotate", "Organize PDF", "🔄", "Rotate pages", "Rotate single pages or the whole document."),
    ("compress", "Optimize PDF", "🗜️", "Compress PDF", "Make the file smaller for email and sharing."),
    ("ocr", "Optimize PDF", "🔍", "OCR PDF", "Make scanned PDFs searchable, or extract their text."),
    ("jpg_to_pdf", "Convert to PDF", "🖼️", "Image to PDF", "Combine JPG, PNG and other images into one PDF."),
    ("pdf_to_jpg", "Convert from PDF", "📷", "PDF to JPG", "Save every page as a JPG or PNG image."),
    ("pdf_to_word", "Convert from PDF", "📝", "PDF to Word", "Extract the text into an editable Word or text file."),
    ("page_numbers", "Edit PDF", "🔢", "Add page numbers", "Number the pages, in the corner you choose."),
    ("watermark", "Edit PDF", "💧", "Add watermark", "Stamp text such as CONFIDENTIAL across every page."),
    ("protect", "PDF security", "🔒", "Protect PDF", "Lock the PDF with a password."),
    ("unlock", "PDF security", "🔓", "Unlock PDF", "Remove a PDF's password."),
]]


@app.context_processor
def inject_globals():
    return {"app_name": APP_NAME, "app_version": APP_VERSION,
            "developer": DEVELOPER, "developer_linkedin": DEVELOPER_LINKEDIN}


def read_text_file(name):
    try:
        with open(resource_path(name), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return f"({name} was not found.)"


# ---------- small helpers ----------
MIME = {".pdf": "application/pdf", ".zip": "application/zip", ".txt": "text/plain; charset=utf-8",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".jpg": "image/jpeg", ".png": "image/png"}

_RESERVED = {"CON", "PRN", "AUX", "NUL",
             *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def clean_filename(name, default="document", ext=".pdf"):
    """Safe file name (keeps spaces and non-English letters) that always ends in `ext`."""
    name = re.sub(r'[\x00-\x1f\\/:*?"<>|]', "", name or "")
    name = re.sub(r"\s+", " ", name).strip(" .")
    if ext and name.lower().endswith(ext.lower()):
        name = name[:-len(ext)].strip(" .")
    name = name[:100].strip(" .") or default
    if name.upper() in _RESERVED:
        name = "_" + name
    return name + ext


def stem_of(filename):
    """File name without its extension, made safe."""
    return clean_filename(os.path.splitext(filename)[0], "document", "")[:100]


def default_stem(filename, suffix):
    return f"{stem_of(filename)}_{suffix}"


def request_json():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise PdfEditError("Invalid request.")
    return body


def get_doc(token, kind="pdf"):
    doc = docs.get(token)
    if doc is None or doc["kind"] != kind:
        raise PdfEditError("That file has expired. Please add it again.")
    return doc


def open_doc(doc):
    return pdf_ops.read_pdf(BytesIO(doc["data"]), doc["name"])


def choice(body, key, choices, default=None):
    value = body.get(key, default)
    if value not in choices:
        raise PdfEditError(f"Invalid option: {key}.")
    return value


def number(body, key, default, low, high):
    try:
        value = int(body.get(key, default))
    except (TypeError, ValueError):
        raise PdfEditError(f"Please enter a whole number for {key.replace('_', ' ')}.")
    if not low <= value <= high:
        raise PdfEditError(f"{key.replace('_', ' ').capitalize()} must be between {low} and {high}.")
    return value


def int_list(value, label):
    if not isinstance(value, list) or not all(
            isinstance(v, int) and not isinstance(v, bool) for v in value):
        raise PdfEditError(f"Invalid {label}.")
    return value


def finish(data, ext, info, default_name, tool):
    """Keep the finished file for a while and tell the browser where its preview page is."""
    token = results.put({"data": data, "ext": ext, "default_name": default_name,
                         "info": info, "tool": tool}, len(data))
    return jsonify(url=url_for("preview", token=token))


def start_job(work):
    """Run `work(progress)` in a thread; the page polls /api/job/<id> for progress."""
    job = {"done": False, "progress": 0, "total": 1, "url": None, "error": None}
    token = jobs.put(job, 1)

    def runner():
        try:
            data, ext, info, default_name, tool = work(
                lambda done, total: job.update(progress=done, total=total))
            result = results.put({"data": data, "ext": ext, "default_name": default_name,
                                  "info": info, "tool": tool}, len(data))
            job["url"] = f"/preview/{result}"
        except PdfEditError as e:
            job["error"] = str(e)
        except Exception:
            app.logger.exception("background job failed")
            job["error"] = "Something went wrong while processing the file."
        finally:
            job["done"] = True

    threading.Thread(target=runner, daemon=True).start()
    return token


# ---------- pages ----------
@app.get("/")
def index():
    groups = OrderedDict()
    for t in TOOLS:
        groups.setdefault(t["group"], []).append(t)
    return render_template("index.html", groups=groups)


def make_page(tool):
    def page():
        extra = {}
        if tool["id"] == "ocr":
            ready = ocr.find_tesseract() is not None
            extra = {"ocr_ready": ready, "langs": ocr.languages() if ready else [],
                     "ocr_packaged": ocr.is_packaged(), "tesseract_url": TESSERACT_URL}
        return render_template(f"{tool['id']}.html", tool=tool, **extra)
    return page


for _tool in TOOLS:
    app.add_url_rule("/" + _tool["id"].replace("_", "-"), endpoint=_tool["id"], view_func=make_page(_tool))


# ---------- about, licenses, housekeeping ----------
@app.get("/about")
def about():
    return render_template("about.html", license_text=read_text_file("LICENSE.txt"),
                           tesseract_url=TESSERACT_URL)


@app.get("/licenses")
def licenses():
    return render_template("licenses.html", notices=read_text_file("THIRD_PARTY_NOTICES.txt"))


@app.route("/api/ping", methods=["GET", "POST"])
def api_ping():
    """Open pages call this regularly; the packaged app quits when the calls stop."""
    heartbeat.beat()
    return jsonify(app=APP_NAME, version=APP_VERSION)


@app.post("/api/open-external")
def api_open_external():
    """Open a link in the user's normal web browser (only a short list of known addresses)."""
    url = request_json().get("url")
    if url not in EXTERNAL_LINKS:
        raise PdfEditError("That address can't be opened from here.")
    webbrowser.open(url)
    return jsonify(ok=True)


# ---------- upload + thumbnails ----------
@app.post("/api/upload")
def api_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        raise PdfEditError("Please choose a PDF file.")
    name = re.split(r"[\\/]", f.filename)[-1]
    data = f.read()
    entry = {"kind": "pdf", "data": data, "name": name, "thumbs": {}}
    try:
        entry["pages"] = len(pdf_ops.read_pdf(BytesIO(data), name).pages)
    except PdfPasswordError:
        if request.form.get("allow_encrypted") != "1":
            raise
        entry.update(pages=None, encrypted=True)       # the Unlock tool takes the password later
    token = docs.put(entry, len(data))
    return jsonify(doc=token, name=name, pages=entry["pages"], size=len(data),
                   encrypted=bool(entry.get("encrypted")))


@app.post("/api/upload-image")
def api_upload_image():
    f = request.files.get("file")
    if not f or not f.filename:
        raise PdfEditError("Please choose an image.")
    name = re.split(r"[\\/]", f.filename)[-1]
    data = f.read()
    try:
        with Image.open(BytesIO(data)) as im:
            im.verify()
        with Image.open(BytesIO(data)) as im:
            width, height = im.size
    except Exception:
        raise PdfEditError(f"'{name}' is not a supported image.")
    token = docs.put({"kind": "image", "data": data, "name": name, "thumbs": {}}, len(data))
    return jsonify(doc=token, name=name, width=width, height=height, size=len(data))


@app.get("/thumb/<token>/<int:page>.jpg")
def thumb(token, page):
    doc = docs.get(token)
    if doc is None:
        abort(404)
    if doc["kind"] == "image":
        if page != 1:
            abort(404)
        render = lambda: thumbs.render_image_thumb(doc["data"])
    else:
        if doc.get("pages") is None or not 1 <= page <= doc["pages"]:
            abort(404)
        render = lambda: thumbs.render_thumb(doc["data"], page - 1)
    img = doc["thumbs"].get(page)
    if img is None:
        img = doc["thumbs"][page] = render()
    response = send_file(BytesIO(img), mimetype="image/jpeg", max_age=1800)
    response.cache_control.private = True
    return response


@app.get("/api/job/<token>")
def api_job(token):
    job = jobs.get(token)
    if job is None:
        raise PdfEditError("That task has expired.")
    return jsonify(dict(job))


# ---------- organize tools ----------
@app.post("/api/parse-pages")
def api_parse_pages():
    body = request_json()
    doc = get_doc(body.get("doc"))
    return jsonify(pages=sorted(set(pdf_ops.parse_pages(body.get("spec"), doc["pages"]))))


@app.post("/api/merge")
def api_merge():
    body = request_json()
    tokens = body.get("docs")
    if not isinstance(tokens, list) or not all(isinstance(t, str) for t in tokens):
        raise PdfEditError("Invalid file list.")
    if len(tokens) > MAX_MERGE_FILES:
        raise PdfEditError(f"You can merge up to {MAX_MERGE_FILES} files at once.")
    items = [get_doc(t) for t in tokens]
    writer, info = pdf_ops.merge([open_doc(d) for d in items], [d["name"] for d in items])
    return finish(tools.pdf_bytes(writer), ".pdf", info, "merged", "merge")


@app.post("/api/remove")
def api_remove():
    body = request_json()
    doc = get_doc(body.get("doc"))
    writer, info = pdf_ops.remove_pages(open_doc(doc), int_list(body.get("pages"), "page list"))
    return finish(tools.pdf_bytes(writer), ".pdf", info, default_stem(doc["name"], "edited"), "remove")


@app.post("/api/organize")
def api_organize():
    body = request_json()
    doc = get_doc(body.get("doc"))
    writer, info = pdf_ops.reorder(open_doc(doc), int_list(body.get("order"), "page order"))
    return finish(tools.pdf_bytes(writer), ".pdf", info, default_stem(doc["name"], "organized"), "organize")


@app.post("/api/split")
def api_split():
    body = request_json()
    doc = get_doc(body.get("doc"))
    mode = choice(body, "mode", ("ranges", "each", "every", "extract"))
    every = number(body, "every", 1, 1, 10_000) if mode == "every" else 1
    data, ext, info = tools.split(open_doc(doc), stem_of(doc["name"]), mode,
                                  str(body.get("ranges", "")), str(body.get("pages", "")), every)
    return finish(data, ext, info, default_stem(doc["name"], "split"), "split")


@app.post("/api/rotate")
def api_rotate():
    body = request_json()
    doc = get_doc(body.get("doc"))
    raw = body.get("rotations")
    if not isinstance(raw, dict):
        raise PdfEditError("Invalid rotation data.")
    rotations = {}
    total = doc["pages"]
    for key, degrees in raw.items():
        if not (key.isdigit() and 1 <= int(key) <= total and isinstance(degrees, int)
                and not isinstance(degrees, bool) and degrees % 90 == 0):
            raise PdfEditError("Invalid rotation data.")
        rotations[int(key)] = degrees
    data, ext, info = tools.rotate(open_doc(doc), rotations)
    return finish(data, ext, info, default_stem(doc["name"], "rotated"), "rotate")


# ---------- optimize ----------
@app.post("/api/compress")
def api_compress():
    body = request_json()
    doc = get_doc(body.get("doc"))
    level = choice(body, "level", tuple(tools.COMPRESS_LEVELS), "recommended")
    open_doc(doc)                                           # validates / rejects locked files
    data, ext, info = tools.compress(doc["data"], level, doc["name"])
    return finish(data, ext, info, default_stem(doc["name"], "compressed"), "compress")


@app.post("/api/ocr")
def api_ocr():
    body = request_json()
    doc = get_doc(body.get("doc"))
    total = len(open_doc(doc).pages)
    if ocr.find_tesseract() is None:
        raise PdfEditError(ocr.install_hint())
    installed = {code for code, _ in ocr.languages()}
    picked = [body.get("lang"), body.get("lang2")]
    codes = list(dict.fromkeys(c for c in picked if c))
    if not codes or any(c not in installed for c in codes):
        raise PdfEditError("Please choose an installed OCR language.")
    output = choice(body, "output", ("pdf", "txt"), "pdf")
    dpi = {"standard": 200, "high": 300}[choice(body, "quality", ("standard", "high"), "standard")]
    stem = stem_of(doc["name"])

    def work(progress):
        data, ext, info = ocr.ocr_pdf(doc["data"], total, "+".join(codes), output, dpi, progress)
        return data, ext, info, f"{stem}_ocr", "ocr"

    return jsonify(job=start_job(work))


# ---------- convert ----------
@app.post("/api/image-to-pdf")
def api_image_to_pdf():
    body = request_json()
    tokens = body.get("docs")
    if not isinstance(tokens, list) or not tokens or not all(isinstance(t, str) for t in tokens):
        raise PdfEditError("Please add at least one image.")
    if len(tokens) > MAX_IMAGES:
        raise PdfEditError(f"You can convert up to {MAX_IMAGES} images at once.")
    items = [get_doc(t, "image") for t in tokens]
    data, ext, info = tools.images_to_pdf(
        [(d["name"], d["data"]) for d in items],
        choice(body, "page_size", ("fit", "a4", "letter"), "a4"),
        choice(body, "orientation", ("auto", "portrait", "landscape"), "auto"),
        choice(body, "margin", tuple(tools.MARGINS), "small"))
    name = stem_of(items[0]["name"]) if len(items) == 1 else "images"
    return finish(data, ext, info, name, "jpg_to_pdf")


@app.post("/api/pdf-to-jpg")
def api_pdf_to_jpg():
    body = request_json()
    doc = get_doc(body.get("doc"))
    total = len(open_doc(doc).pages)
    fmt = choice(body, "format", ("jpg", "png"), "jpg")
    dpi = number(body, "dpi", 150, 36, 600)
    data, ext, info = tools.pdf_to_images(doc["data"], stem_of(doc["name"]), total, fmt, dpi,
                                          str(body.get("pages", "")))
    return finish(data, ext, info, default_stem(doc["name"], "images"), "pdf_to_jpg")


@app.post("/api/pdf-to-word")
def api_pdf_to_word():
    body = request_json()
    doc = get_doc(body.get("doc"))
    total = len(open_doc(doc).pages)
    fmt = choice(body, "format", ("docx", "txt"), "docx")
    data, ext, info = tools.pdf_to_word(doc["data"], total, fmt)
    return finish(data, ext, info, stem_of(doc["name"]), "pdf_to_word")


# ---------- edit + security ----------
@app.post("/api/page-numbers")
def api_page_numbers():
    body = request_json()
    doc = get_doc(body.get("doc"))
    data, ext, info = tools.add_page_numbers(
        open_doc(doc),
        choice(body, "position", tuple(tools.PAGE_NUMBER_POSITIONS), "bottom-center"),
        choice(body, "format", ("number", "page", "page_of"), "number"),
        number(body, "start", 1, 0, 100_000),
        bool(body.get("skip_first")))
    return finish(data, ext, info, default_stem(doc["name"], "numbered"), "page_numbers")


@app.post("/api/watermark")
def api_watermark():
    body = request_json()
    doc = get_doc(body.get("doc"))
    data, ext, info = tools.add_watermark(
        open_doc(doc), str(body.get("text", "")),
        choice(body, "size", tuple(tools.WATERMARK_SIZE), "medium"),
        choice(body, "opacity", tuple(tools.WATERMARK_OPACITY), "medium"),
        choice(body, "color", tuple(tools.WATERMARK_COLORS), "gray"),
        int(choice(body, "angle", ("45", "0"), "45")))
    return finish(data, ext, info, default_stem(doc["name"], "watermarked"), "watermark")


@app.post("/api/protect")
def api_protect():
    body = request_json()
    doc = get_doc(body.get("doc"))
    data, ext, info = tools.protect(open_doc(doc), str(body.get("password", "")))
    return finish(data, ext, info, default_stem(doc["name"], "protected"), "protect")


@app.post("/api/unlock")
def api_unlock():
    body = request_json()
    doc = get_doc(body.get("doc"))
    data, ext, info = tools.unlock(doc["data"], str(body.get("password", "")))
    return finish(data, ext, info, default_stem(doc["name"], "unlocked"), "unlock")


# ---------- preview / rename / download ----------
def result_or_none(token):
    result = results.get(token)
    if result is None:
        flash("That preview has expired. Please run the edit again.")
    return result


@app.get("/preview/<token>")
def preview(token):
    result = result_or_none(token)
    if result is None:
        return redirect(url_for("index"))
    return render_template("preview.html", token=token, info=result["info"],
                           ext=result["ext"], size=tools.human_size(len(result["data"])),
                           default_name=result["default_name"],
                           back_url=url_for(result["tool"]))


@app.get("/file/<token>")
def view_file(token):
    """Serves the result inline (used by the preview page)."""
    result = results.get(token)
    if result is None:
        abort(404)
    response = send_file(BytesIO(result["data"]), mimetype=MIME[result["ext"]], max_age=0,
                         download_name=result["default_name"] + result["ext"])
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/download/<token>")
def download(token):
    result = result_or_none(token)
    if result is None:
        return redirect(url_for("index"))
    filename = clean_filename(request.args.get("name"), result["default_name"], result["ext"])
    return send_file(BytesIO(result["data"]), mimetype=MIME[result["ext"]],
                     as_attachment=True, download_name=filename)


# ---------- errors ----------
@app.errorhandler(PdfEditError)
def handle_pdf_error(error):
    return jsonify(error=str(error)), 400


@app.errorhandler(RequestEntityTooLarge)
def too_large(_):
    message = f"That upload is too large (limit is {MAX_UPLOAD_MB} MB)."
    if request.path.startswith("/api/"):
        return jsonify(error=message), 413
    flash(message)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
