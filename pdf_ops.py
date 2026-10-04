"""All PDF logic lives here (no Flask code), so it is easy to test and reuse.

merge / remove_pages / organize each return (writer, info), where `info` is a
small dict used by the preview page to describe what changed:
    {"title": "...", "lines": ["...", "..."]}
"""
import re
from io import BytesIO

from pypdf import PdfReader, PdfWriter


class PdfEditError(ValueError):
    """Raised with a user-friendly message when an operation can't be done."""


class PdfPasswordError(PdfEditError):
    """The PDF needs a password we don't have."""


# ---------- helpers ----------
def read_pdf(stream, name="file"):
    """Open a PDF from a file-like object and return a PdfReader."""
    try:
        reader = PdfReader(stream)
        if reader.is_encrypted and not reader.decrypt(""):
            raise PdfPasswordError(
                f"'{name}' is password protected. Remove the password with the Unlock PDF tool first.")
        len(reader.pages)  # forces parsing, fails early on broken files
        return reader
    except PdfEditError:
        raise
    except Exception:
        raise PdfEditError(f"'{name}' is not a valid PDF file.")


def parse_pages(spec, total):
    """Turn '1-3, 7, 10' into [1, 2, 3, 7, 10] (1-based page numbers)."""
    spec = (spec or "").strip()
    if not spec:
        raise PdfEditError("Please enter at least one page number.")

    spec = re.sub(r"\s*-\s*", "-", spec)           # "3 - 5" -> "3-5"
    tokens = [t for t in re.split(r"[,\s;]+", spec) if t]
    pages = []
    for token in tokens:
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", token)
        if not m:
            raise PdfEditError(f"'{token}' is not a valid page or range.")
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        for n in (start, end):
            if n < 1 or n > total:
                raise PdfEditError(f"Page {n} is out of range (this PDF has {total} pages).")
        if start > end:
            raise PdfEditError(f"Range '{token}' is backwards. Use e.g. {end}-{start}.")
        pages.extend(range(start, end + 1))
    return pages


def format_pages(pages):
    """[1, 2, 3, 7, 9, 10] -> '1-3, 7, 9-10'."""
    pages = sorted(set(pages))
    parts, i = [], 0
    while i < len(pages):
        j = i
        while j + 1 < len(pages) and pages[j + 1] == pages[j] + 1:
            j += 1
        parts.append(str(pages[i]) if i == j else f"{pages[i]}-{pages[j]}")
        i = j + 1
    return ", ".join(parts)


def format_order(order, limit=50):
    shown = ", ".join(str(n) for n in order[:limit])
    if len(order) > limit:
        shown += f", … (+{len(order) - limit} more)"
    return shown


def plural(n, word="page"):
    return f"{n} {word}" + ("" if n == 1 else "s")


def to_bytes(writer):
    buf = BytesIO()
    writer.write(buf)
    buf.seek(0)
    return buf


# ---------- operations ----------
def merge(readers, names=None):
    if len(readers) < 2:
        raise PdfEditError("Please select at least two PDF files to merge.")
    names = names or [f"File {i}" for i in range(1, len(readers) + 1)]
    writer = PdfWriter()
    lines = []
    for i, (reader, name) in enumerate(zip(readers, names), start=1):
        for page in reader.pages:
            writer.add_page(page)
        lines.append(f"{i}. {name} — {plural(len(reader.pages))}")
    total = len(writer.pages)
    lines.append(f"Total: {plural(total)}")
    return writer, {"title": f"Merged {len(readers)} files", "lines": lines}


def remove_pages(reader, pages_to_remove):
    """pages_to_remove: iterable of 1-based page numbers."""
    total = len(reader.pages)
    remove = set(pages_to_remove)
    if not remove:
        raise PdfEditError("No pages selected to remove.")
    if min(remove) < 1 or max(remove) > total:
        raise PdfEditError(f"Pages must be between 1 and {total}.")
    if len(remove) >= total:
        raise PdfEditError("You can't remove every page of the PDF.")
    writer = PdfWriter()
    for i, page in enumerate(reader.pages, start=1):
        if i not in remove:
            writer.add_page(page)
    info = {
        "title": f"Removed {plural(len(remove))}",
        "lines": [f"Removed: {format_pages(remove)}",
                  f"Pages: {total} → {total - len(remove)}"],
    }
    return writer, info


def reorder(reader, order):
    """order: 1-based page numbers in the new order (pages you leave out go at the end)."""
    total = len(reader.pages)
    if total < 2:
        raise PdfEditError("The PDF needs at least two pages to reorder.")
    if not order:
        raise PdfEditError("No page order was given.")
    if min(order) < 1 or max(order) > total:
        raise PdfEditError(f"Pages must be between 1 and {total}.")
    if len(order) != len(set(order)):
        raise PdfEditError("Each page can only be listed once.")
    listed = set(order)
    order = list(order) + [p for p in range(1, total + 1) if p not in listed]
    if order == list(range(1, total + 1)):
        raise PdfEditError("The page order hasn't changed.")

    writer = PdfWriter()
    for n in order:
        writer.add_page(reader.pages[n - 1])
    info = {
        "title": "Pages reordered",
        "lines": [f"New order (original page numbers): {format_order(order)}",
                  f"Total: {plural(total)}"],
    }
    return writer, info
