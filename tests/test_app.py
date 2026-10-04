"""Run with:  python tests/test_app.py"""
import io, os, random, sys, time, zipfile
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

import ocr
from app import app, clean_filename

client = app.test_client()


# ---------- helpers ----------
def make_pdf(labels):
    """Blank pages, each with a unique width so we can tell them apart."""
    w = PdfWriter()
    for n in labels:
        w.add_blank_page(width=100 + n, height=200)
    buf = BytesIO(); w.write(buf); buf.seek(0)
    return buf


def text_pdf(pages):
    """A PDF with real selectable text: one string per page."""
    buf = BytesIO()
    c = canvas.Canvas(buf)
    for text in pages:
        y = 780
        for line in text.split("\n"):
            c.drawString(72, y, line); y -= 18
        c.showPage()
    c.save(); buf.seek(0)
    return buf


def widths(response):
    return [int(p.mediabox.width) - 100 for p in PdfReader(BytesIO(response.data)).pages]


def post_file(url, buf, name="x.pdf", **extra):
    return client.post(url, data={"file": (buf, name), **extra}, content_type="multipart/form-data")


def upload(labels, name="x.pdf"):
    r = post_file("/api/upload", make_pdf(labels), name)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["doc"]


def upload_buf(buf, name="x.pdf", **extra):
    r = post_file("/api/upload", buf, name, **extra)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["doc"]


def api(url, body):
    return client.post(url, json=body)


def token_of(response):
    assert response.status_code == 200, response.get_json()
    return response.get_json()["url"].rsplit("/", 1)[-1]


def result_file(response):
    """Follow the {url: /preview/<token>} reply and fetch the finished file."""
    return client.get(f"/file/{token_of(response)}")


def error_of(response, status=400):
    assert response.status_code == status, (response.status_code, response.get_data()[:200])
    return response.get_json()["error"]


def pdf_text(data):
    return " ".join(p.extract_text() for p in PdfReader(BytesIO(data)).pages)


def noisy_image(size=(2400, 1600)):
    rnd = random.Random(1)
    data = bytes(rnd.getrandbits(8) for _ in range(size[0] * size[1] // 16 * 3))
    small = Image.frombytes("RGB", (size[0] // 4, size[1] // 4), data[: size[0] // 4 * size[1] // 4 * 3])
    return small.resize(size)


def image_bytes(fmt="JPEG", size=(300, 200), color="red"):
    buf = BytesIO(); Image.new("RGB", size, color).save(buf, fmt); return buf.getvalue()


def upload_image(data, name="a.jpg"):
    r = post_file("/api/upload-image", BytesIO(data), name)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["doc"]


# ---------- pages ----------
def test_all_pages_load():
    for rule in app.url_map.iter_rules():
        if rule.endpoint != "static" and "GET" in rule.methods and not rule.arguments:
            assert client.get(rule.rule).status_code == 200, rule.rule
    html = client.get("/").get_data(as_text=True)
    assert "Editora PDFEdit" in html and "logo.png" in html
    for tool in ("split", "ocr", "jpg-to-pdf", "pdf-to-word", "watermark", "unlock"):
        assert f'href="/{tool}"' in html, tool


# ---------- upload + thumbnails ----------
def test_upload_and_thumbnail():
    d = post_file("/api/upload", make_pdf(range(1, 4)), "a.pdf").get_json()
    assert d["pages"] == 3 and d["name"] == "a.pdf" and d["size"] > 0 and not d["encrypted"]
    t = client.get(f"/thumb/{d['doc']}/2.jpg")
    img = Image.open(BytesIO(t.data))
    assert t.mimetype == "image/jpeg" and img.width <= 260 and img.height <= 360
    assert client.get(f"/thumb/{d['doc']}/4.jpg").status_code == 404
    assert client.get("/thumb/nope/1.jpg").status_code == 404


def test_upload_rejects_non_pdf():
    assert "not a valid PDF" in error_of(post_file("/api/upload", BytesIO(b"hello")))
    assert error_of(client.post("/api/upload", data={}, content_type="multipart/form-data"))


def test_image_upload_and_thumbnail():
    r = post_file("/api/upload-image", BytesIO(image_bytes(size=(300, 200))), "pic.jpg").get_json()
    assert (r["width"], r["height"]) == (300, 200)
    t = client.get(f"/thumb/{r['doc']}/1.jpg")
    assert t.mimetype == "image/jpeg" and Image.open(BytesIO(t.data)).width <= 260
    assert "not a supported image" in error_of(post_file("/api/upload-image", BytesIO(b"nope"), "x.jpg"))


# ---------- merge / remove / organize ----------
def test_merge_in_given_order():
    a, b = upload([1, 2], "a.pdf"), upload([3], "b.pdf")
    assert widths(result_file(api("/api/merge", {"docs": [b, a]}))) == [3, 1, 2]
    assert "at least two" in error_of(api("/api/merge", {"docs": [a]}))
    assert "expired" in error_of(api("/api/merge", {"docs": [a, "nope"]}))


def test_remove_and_parse_pages():
    d = upload(range(1, 8))
    assert widths(result_file(api("/api/remove", {"doc": d, "pages": [2, 3, 4, 7]}))) == [1, 5, 6]
    assert "every page" in error_of(api("/api/remove", {"doc": upload(range(1, 4)), "pages": [1, 2, 3]}))
    assert api("/api/parse-pages", {"doc": d, "spec": "1, 4, 5-6"}).get_json()["pages"] == [1, 4, 5, 6]
    assert "out of range" in error_of(api("/api/parse-pages", {"doc": d, "spec": "99"}))


def test_organize():
    d = upload(range(1, 6))
    assert widths(result_file(api("/api/organize", {"doc": d, "order": [3, 1, 2, 4, 5]}))) == [3, 1, 2, 4, 5]
    assert "hasn't changed" in error_of(api("/api/organize", {"doc": d, "order": [1, 2, 3, 4, 5]}))


# ---------- split / rotate ----------
def test_split_modes():
    d = upload(range(1, 8))
    z = zipfile.ZipFile(BytesIO(result_file(api("/api/split", {"doc": d, "mode": "ranges", "ranges": "1-3, 5, 6-7"})).data))
    names = z.namelist()
    assert len(names) == 3 and "pages_1-3" in names[0] and "page_5" in names[1]
    assert [int(p.mediabox.width) - 100 for p in PdfReader(BytesIO(z.read(names[2]))).pages] == [6, 7]
    z = zipfile.ZipFile(BytesIO(result_file(api("/api/split", {"doc": d, "mode": "each"})).data))
    assert len(z.namelist()) == 7
    z = zipfile.ZipFile(BytesIO(result_file(api("/api/split", {"doc": d, "mode": "every", "every": 3})).data))
    assert len(z.namelist()) == 3
    r = result_file(api("/api/split", {"doc": d, "mode": "extract", "pages": "6, 2-3"}))
    assert r.mimetype == "application/pdf" and widths(r) == [6, 2, 3]
    assert result_file(api("/api/split", {"doc": d, "mode": "ranges", "ranges": "2-4"})).mimetype == "application/pdf"
    assert error_of(api("/api/split", {"doc": d, "mode": "ranges", "ranges": ""}))
    assert error_of(api("/api/split", {"doc": d, "mode": "bogus"}))


def test_rotate():
    d = upload(range(1, 4))
    r = result_file(api("/api/rotate", {"doc": d, "rotations": {"2": 90, "3": 270}}))
    assert [p.rotation for p in PdfReader(BytesIO(r.data)).pages] == [0, 90, 270]
    assert "No pages" in error_of(api("/api/rotate", {"doc": d, "rotations": {}}))
    assert error_of(api("/api/rotate", {"doc": d, "rotations": {"9": 90}}))
    assert error_of(api("/api/rotate", {"doc": d, "rotations": {"1": 45}}))


# ---------- compress ----------
def test_compress():
    buf = BytesIO(); noisy_image().save(buf, "PDF", resolution=100, quality=95)
    original = buf.getvalue()
    d = upload_buf(BytesIO(original))
    r = api("/api/compress", {"doc": d, "level": "extreme"})
    out = client.get(f"/file/{token_of(r)}").data
    assert len(out) < len(original) * 0.8 and len(PdfReader(BytesIO(out)).pages) == 1
    html = client.get(f"/preview/{token_of(r)}").get_data(as_text=True)
    assert "smaller" in html and "Before:" in html
    # a tiny PDF can't shrink: the original is kept
    small = api("/api/compress", {"doc": upload([1, 2]), "level": "recommended"})
    assert "already well optimized" in client.get(f"/preview/{token_of(small)}").get_data(as_text=True)


# ---------- images <-> PDF ----------
def test_image_to_pdf():
    a = upload_image(image_bytes(size=(300, 200)), "a.jpg")
    b = upload_image(image_bytes("PNG", size=(200, 300), color="blue"), "b.png")
    r = result_file(api("/api/image-to-pdf", {"docs": [a, b], "page_size": "a4", "orientation": "auto", "margin": "small"}))
    pages = PdfReader(BytesIO(r.data)).pages
    assert len(pages) == 2
    assert round(float(pages[0].mediabox.width)) == 842 and round(float(pages[0].mediabox.height)) == 595   # landscape A4
    assert round(float(pages[1].mediabox.width)) == 595                                                     # portrait A4
    r = result_file(api("/api/image-to-pdf", {"docs": [a], "page_size": "fit", "orientation": "auto", "margin": "none"}))
    p = PdfReader(BytesIO(r.data)).pages[0]
    assert float(p.mediabox.width) / float(p.mediabox.height) == 1.5
    assert error_of(api("/api/image-to-pdf", {"docs": []}))
    assert error_of(api("/api/image-to-pdf", {"docs": [upload([1])]}))      # a PDF is not an image


def test_pdf_to_images():
    d = upload(range(1, 4))
    z = zipfile.ZipFile(BytesIO(result_file(api("/api/pdf-to-jpg", {"doc": d, "format": "jpg", "dpi": 72})).data))
    assert z.namelist() == ["x_page_1.jpg", "x_page_2.jpg", "x_page_3.jpg"]
    assert Image.open(BytesIO(z.read("x_page_2.jpg"))).format == "JPEG"
    r = result_file(api("/api/pdf-to-jpg", {"doc": d, "format": "png", "dpi": 100, "pages": "3"}))
    img = Image.open(BytesIO(r.data))
    assert r.mimetype == "image/png" and img.format == "PNG"
    assert abs(img.width - 103 * 100 / 72) <= 1 and abs(img.height - 200 * 100 / 72) <= 1   # pdfium rounds up
    assert error_of(api("/api/pdf-to-jpg", {"doc": d, "format": "gif"}))
    assert error_of(api("/api/pdf-to-jpg", {"doc": d, "dpi": 5000}))


def test_pdf_to_word_and_text():
    d = upload_buf(text_pdf(["Hello Editora world.\nSecond line here.", "Page two says goodbye."]))
    r = result_file(api("/api/pdf-to-word", {"doc": d, "format": "docx"}))
    assert r.data[:2] == b"PK"
    from docx import Document
    doc = Document(BytesIO(r.data))
    body = " ".join(p.text for p in doc.paragraphs)
    assert "Hello Editora world." in body and "goodbye" in body
    t = result_file(api("/api/pdf-to-word", {"doc": d, "format": "txt"}))
    assert "Hello Editora" in t.data.decode() and t.mimetype.startswith("text/plain")
    assert "OCR" in error_of(api("/api/pdf-to-word", {"doc": upload([1, 2]), "format": "docx"}))   # no text


# ---------- edit: page numbers + watermark ----------
def test_page_numbers():
    d = upload_buf(text_pdf(["First", "Second", "Third"]))
    r = result_file(api("/api/page-numbers", {"doc": d, "position": "bottom-right", "format": "page_of", "start": 1, "skip_first": False}))
    text = pdf_text(r.data)
    assert "Page 1 of 3" in text and "Page 3 of 3" in text and "Second" in text
    r = result_file(api("/api/page-numbers", {"doc": d, "position": "top-left", "format": "number", "start": 5, "skip_first": True}))
    pages = [p.extract_text() for p in PdfReader(BytesIO(r.data)).pages]
    assert "5" not in pages[0] and "5" in pages[1] and "6" in pages[2]
    assert error_of(api("/api/page-numbers", {"doc": d, "position": "middle"}))


def test_page_numbers_on_rotated_page():
    w = PdfWriter(); w.add_blank_page(300, 200); w.pages[0].rotate(90)
    buf = BytesIO(); w.write(buf); buf.seek(0)
    r = result_file(api("/api/page-numbers", {"doc": upload_buf(buf), "position": "bottom-center", "format": "number", "start": 7}))
    assert "7" in pdf_text(r.data)


def test_watermark():
    d = upload_buf(text_pdf(["Body text", "More text"]))
    r = result_file(api("/api/watermark", {"doc": d, "text": "DRAFT", "size": "medium", "opacity": "medium", "color": "red", "angle": "45"}))
    assert "DRAFT" in pdf_text(r.data) and "Body text" in pdf_text(r.data)
    assert error_of(api("/api/watermark", {"doc": d, "text": " "}))
    assert "Latin" in error_of(api("/api/watermark", {"doc": d, "text": "සිංහල"}))
    assert error_of(api("/api/watermark", {"doc": d, "text": "x" * 61}))


# ---------- security ----------
def test_protect_then_unlock():
    d = upload([1, 2, 3])
    locked = result_file(api("/api/protect", {"doc": d, "password": "s3cret"})).data
    reader = PdfReader(BytesIO(locked))
    assert reader.is_encrypted and reader.decrypt("s3cret") and len(reader.pages) == 3
    assert error_of(api("/api/protect", {"doc": d, "password": ""}))

    # other tools refuse a locked file and point to Unlock
    assert "Unlock" in error_of(post_file("/api/upload", BytesIO(locked)))
    # the Unlock tool accepts it
    r = post_file("/api/upload", BytesIO(locked), "locked.pdf", allow_encrypted="1").get_json()
    assert r["encrypted"] and r["pages"] is None
    assert client.get(f"/thumb/{r['doc']}/1.jpg").status_code == 404
    assert "not correct" in error_of(api("/api/unlock", {"doc": r["doc"], "password": "wrong"}))
    opened = result_file(api("/api/unlock", {"doc": r["doc"], "password": "s3cret"}))
    assert not PdfReader(BytesIO(opened.data)).is_encrypted and widths(opened) == [1, 2, 3]
    assert "not password protected" in error_of(api("/api/unlock", {"doc": upload([1]), "password": ""}))


# ---------- OCR ----------
def scanned_pdf(words):
    """A PDF whose pages are pictures of text (no text layer)."""
    try:
        font = ImageFont.load_default(size=70)
    except TypeError:
        font = ImageFont.load_default()
    pages = []
    for word in words:
        im = Image.new("RGB", (1200, 400), "white")
        ImageDraw.Draw(im).text((60, 150), word, fill="black", font=font)
        pages.append(im)
    buf = BytesIO(); pages[0].save(buf, "PDF", save_all=True, append_images=pages[1:], resolution=150)
    buf.seek(0)
    return buf


def run_ocr(doc, **options):
    r = api("/api/ocr", {"doc": doc, "lang": "eng", **options})
    assert r.status_code == 200, r.get_json()
    job = r.get_json()["job"]
    for _ in range(300):
        j = client.get(f"/api/job/{job}").get_json()
        if j["done"]:
            return j
        time.sleep(0.2)
    raise AssertionError("OCR did not finish")


def test_ocr():
    if not ocr.find_tesseract():
        print("   (skipped: Tesseract not installed)"); return
    d = upload_buf(scanned_pdf(["Invoice Total", "Thank You"]))
    assert pdf_text(open_bytes(d)) .strip() == ""                      # really has no text yet
    j = run_ocr(d, output="pdf", quality="standard")
    assert j["error"] is None and j["progress"] == 2 and j["url"].startswith("/preview/")
    data = client.get("/file/" + j["url"].rsplit("/", 1)[-1]).data
    text = pdf_text(data).lower()
    assert "invoice" in text and "thank" in text and len(PdfReader(BytesIO(data)).pages) == 2
    j = run_ocr(d, output="txt")
    t = client.get("/file/" + j["url"].rsplit("/", 1)[-1])
    assert "invoice" in t.data.decode().lower()


def open_bytes(token):
    from app import docs
    return docs.get(token)["data"]


def test_ocr_errors():
    d = upload([1])
    assert "language" in error_of(api("/api/ocr", {"doc": d, "lang": "xxx"}))
    assert error_of(api("/api/ocr", {"doc": d}))
    assert error_of(client.get("/api/job/nope"))


# ---------- preview + rename ----------
def test_preview_and_rename():
    d = upload(range(1, 8), "My Notes.pdf")
    token = token_of(api("/api/remove", {"doc": d, "pages": [2, 3, 4, 7]}))
    html = client.get(f"/preview/{token}").get_data(as_text=True)
    assert "Removed 4 pages" in html and "7 → 3" in html and 'value="My Notes_edited"' in html and "<iframe" in html
    disp = client.get(f"/download/{token}", query_string={"name": "My report"}).headers["Content-Disposition"]
    assert "attachment" in disp and "My report.pdf" in disp
    assert "My Notes_edited.pdf" in client.get(f"/download/{token}", query_string={"name": " "}).headers["Content-Disposition"]
    assert "abc.pdf" in client.get(f"/download/{token}", query_string={"name": "a/b:c.pdf"}).headers["Content-Disposition"]


def test_preview_for_other_file_types():
    d = upload(range(1, 4), "scan.pdf")
    zt = token_of(api("/api/split", {"doc": d, "mode": "each"}))
    html = client.get(f"/preview/{zt}").get_data(as_text=True)
    assert "<iframe" not in html and "file-ready" in html and ".zip" in html
    disp = client.get(f"/download/{zt}", query_string={"name": "pages.zip"}).headers["Content-Disposition"]
    assert "pages.zip" in disp and "pages.zip.zip" not in disp
    it = token_of(api("/api/pdf-to-jpg", {"doc": d, "pages": "1", "dpi": 72}))
    assert "preview-image" in client.get(f"/preview/{it}").get_data(as_text=True)
    assert client.get(f"/download/{it}").headers["Content-Type"] == "image/jpeg"


def test_clean_filename():
    assert clean_filename("report") == "report.pdf"
    assert clean_filename("report.PDF") == "report.pdf"
    assert clean_filename("data.docx", ext=".docx") == "data.docx"
    assert clean_filename('a<b>"c"?') == "abc.pdf"
    assert clean_filename("...", "fallback") == "fallback.pdf"
    assert clean_filename("CON") == "_CON.pdf"
    assert clean_filename("x" * 300) == "x" * 100 + ".pdf"


def test_expired_or_unknown_token():
    assert client.get("/preview/nope").status_code == 302
    assert client.get("/download/nope").status_code == 302
    assert client.get("/file/nope").status_code == 404


# ---------- About, licenses, ping, external links ----------
def test_about_icon_on_every_page():
    for url in ("/", "/merge", "/split", "/ocr", "/jpg-to-pdf", "/watermark", "/about"):
        html = client.get(url).get_data(as_text=True)
        assert 'class="about-link' in html and 'href="/about"' in html, url


def test_about_page_details():
    html = client.get("/about").get_data(as_text=True)
    assert "Kanishka Meddegoda" in html
    assert 'href="https://lk.linkedin.com/in/kanishka-in"' in html and "data-external" in html
    assert "SOFTWARE LICENSE AGREEMENT" in html and "Third-party" in html.replace("third-party", "Third-party")
    assert "Version 1.0.0" in html and 'href="/licenses"' in html
    lic = client.get("/licenses").get_data(as_text=True)
    assert "Apache License" in lic and "Flask" in lic and "Tesseract" in lic


def test_ping_and_external_links(monkeypatch=None):
    import webbrowser
    assert client.get("/api/ping").get_json()["app"] == "Editora PDFEdit"
    assert client.post("/api/ping").status_code == 200
    opened = []
    original = webbrowser.open
    webbrowser.open = lambda url: opened.append(url) or True
    try:
        ok = api("/api/open-external", {"url": "https://lk.linkedin.com/in/kanishka-in"})
        assert ok.status_code == 200 and opened == ["https://lk.linkedin.com/in/kanishka-in"]
        assert "can't be opened" in error_of(api("/api/open-external", {"url": "https://evil.example/"}))
        assert error_of(api("/api/open-external", {"url": "file:///c:/windows/system32/calc.exe"}))
    finally:
        webbrowser.open = original
    assert len(opened) == 1


def test_ocr_engine_discovery_prefers_bundled_copy():
    import stat, tempfile
    from unittest import mock
    with tempfile.TemporaryDirectory() as tmp:
        folder = os.path.join(tmp, "tesseract"); os.makedirs(folder)
        fake = os.path.join(folder, "tesseract")
        open(fake, "w").write("#!/bin/sh\necho fake\n"); os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
        with mock.patch.object(ocr, "_app_dirs", return_value=[tmp]):
            assert ocr.find_tesseract() == fake
        with mock.patch.object(ocr, "_app_dirs", return_value=[]):
            assert ocr.find_tesseract() != fake
    assert "reinstall" in ocr.BUNDLED_HINT.lower() and "github.com" in ocr.INSTALL_HINT


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t(); print("PASS", t.__name__)
