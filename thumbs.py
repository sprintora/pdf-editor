"""Thumbnails (PDF pages and uploaded images)."""
import io
import threading

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageOps

MAX_W, MAX_H = 260, 360
LOCK = threading.Lock()      # pdfium is not thread-safe: every pdfium call must hold this


def _placeholder():
    img = Image.new("RGB", (MAX_W, MAX_H), "#f3f4f6")
    ImageDraw.Draw(img).text((MAX_W // 2 - 30, MAX_H // 2), "No preview", fill="#6b7280")
    return img


def _jpeg(img):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def render_thumb(data, index):
    """JPEG bytes for page `index` (0-based) of the PDF in `data`."""
    try:
        with LOCK:
            pdf = pdfium.PdfDocument(data)
            try:
                page = pdf[index]
                w, h = page.get_size()
                scale = min(MAX_W / max(w, 1), MAX_H / max(h, 1))
                img = page.render(scale=scale).to_pil().convert("RGB")
            finally:
                pdf.close()
    except Exception:
        img = _placeholder()
    return _jpeg(img)


def render_image_thumb(data):
    """JPEG thumbnail for an uploaded image."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                bg = Image.new("RGBA", im.size, "white")
                im = Image.alpha_composite(bg, im)
            im = im.convert("RGB")
            im.thumbnail((MAX_W, MAX_H))
            return _jpeg(im)
    except Exception:
        return _jpeg(_placeholder())
