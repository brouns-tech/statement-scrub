"""PDFium extraction/preview and clean ReportLab reconstruction.

Never clone a source PDF page, font, stream or other object into the output.
"""
from __future__ import annotations
from contextlib import closing
from dataclasses import dataclass
from io import BytesIO
import ctypes
import math
import re
import threading

import pypdfium2 as pdfium
from pypdfium2 import raw
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

LOCK = threading.RLock()  # PDFium is not thread-safe, including rendering.
MAX_BYTES = 30 * 1024 * 1024
MAX_PAGES = 30
MAX_CHARS = 150000


@dataclass(frozen=True)
class Fragment:
    id: str
    page: int
    text: str
    x: float
    y: float
    width: float
    size: float
    ink_width: float = 0
    bottom: float = 0
    top: float = 0


@dataclass(frozen=True)
class Document:
    pages: tuple[tuple[float, float], ...]
    fragments: tuple[Fragment, ...]
    omitted_objects: int
    omitted_rotated_chars: int = 0


def extract(data: bytes) -> Document:
    if len(data) > MAX_BYTES:
        raise ValueError("PDF exceeds the 30 MB limit.")
    pages, fragments = [], []
    omitted, total_chars, rotated = 0, 0, 0
    with LOCK, pdfium.PdfDocument(data) as doc:
        if not 1 <= len(doc) <= MAX_PAGES:
            raise ValueError("Use a PDF with 1–30 pages.")
        for p in range(len(doc)):
            with closing(doc[p]) as page, closing(page.get_textpage()) as tp:
                if page.get_rotation() != 0:
                    raise ValueError("Rotated pages are unsupported in this preview.")
                w, h = page.get_size()
                if not (36 <= w <= 2000 and 36 <= h <= 2000):
                    raise ValueError("Unsupported page dimensions.")
                pages.append((w, h))
                omitted += sum(obj.type != raw.FPDF_PAGEOBJ_TEXT for obj in page.get_objects())
                chars = []
                total_chars += tp.count_chars()
                if total_chars > MAX_CHARS:
                    raise ValueError("PDF contains too much text for this preview.")
                for i in range(tp.count_chars()):
                    code = raw.FPDFText_GetUnicode(tp, i)
                    ch = chr(code) if code else ""
                    if not ch or code < 32:
                        continue
                    if abs(math.sin(raw.FPDFText_GetCharAngle(tp, i))) > 0.01:
                        rotated += 1
                        continue
                    x, y = ctypes.c_double(), ctypes.c_double()
                    raw.FPDFText_GetCharOrigin(tp, i, x, y)
                    left, bottom, right, top = tp.get_charbox(i)
                    size = raw.FPDFText_GetFontSize(tp, i)
                    vals = (left, right, x.value, y.value, size)
                    if not all(math.isfinite(v) for v in vals):
                        raise ValueError("Invalid text geometry.")
                    chars.append((x.value, y.value, right, size, ch, bottom, top))
                if not chars:
                    raise ValueError("A page has no extractable text. Scans/OCR are unsupported.")
                rows = []
                for char in sorted(chars, key=lambda c: (-c[1], c[0])):
                    if not rows or abs(rows[-1][0] - char[1]) > 2:
                        rows.append((char[1], [char]))
                    else:
                        rows[-1][1].append(char)
                chunks = []
                for _, row in rows:
                    chunk = []
                    for ch in sorted(row):
                        if chunk and ch[0] - chunk[-1][2] > max(8, ch[3]):
                            chunks.append(chunk)
                            chunk = []
                        chunk.append(ch)
                    if chunk:
                        chunks.append(chunk)
                for index, chunk in enumerate(chunks):
                    text = ""
                    for j, ch in enumerate(chunk):
                        if j and not ch[4].isspace() and not chunk[j-1][4].isspace() and ch[0] - chunk[j-1][2] > ch[3] * .6:
                            text += " "
                        text += ch[4]
                    x, y, _, size, _, _, _ = chunk[0]
                    right = max(ch[2] for ch in chunk)
                    next_x = min((c[0][0] for c in chunks if abs(c[0][1]-y) <= 2 and c[0][0] > right + 1), default=w-20)
                    fragments.append(Fragment(f"p{p+1}-f{index+1}", p, text.strip(), x, y,
                                              max(right-x, next_x-x-5), max(6, min(size, 24)), right-x, min(c[5] for c in chunk), max(c[6] for c in chunk)))
    return Document(tuple(pages), tuple(fragments), omitted, rotated)


def preview(data: bytes, page_number: int, scale: float = 1.2) -> bytes:
    with LOCK, pdfium.PdfDocument(data) as doc, closing(doc[page_number]) as page:
        with closing(page.render(scale=scale)) as bitmap:
            image = bitmap.to_pil()
            out = BytesIO()
            image.save(out, format="PNG")
            return out.getvalue()


def draft_rows(document: Document) -> list[dict]:
    return [{"id": f.id, "page": f.page+1, "source": f.text, "action": "pending",
             "replacement": "", "width": round(f.width, 1)} for f in document.fragments]


def build_candidate(document: Document, rows: list[dict], values: dict[str, str],
                    reviewed_pages: set[int], omitted_reviewed: bool) -> bytes:
    """No disk writes. Caller must review the resulting candidate before sharing."""
    if reviewed_pages != set(range(len(document.pages))):
        raise ValueError("Review every source page before generating a candidate.")
    if not omitted_reviewed:
        raise ValueError("Acknowledge that non-text content will be omitted.")
    by_id = {r['id']: r for r in rows}
    if len(rows) != len(document.fragments) or set(by_id) != {f.id for f in document.fragments}:
        raise ValueError("Every fragment must have exactly one decision.")
    commands = [[] for _ in document.pages]
    for f in document.fragments:
        row = by_id[f.id]
        action = row['action']
        if action == "drop":
            continue
        if action == "static":
            # Do not mistake a detector's silence for permission to preserve numbers.
            if any(c.isdigit() for c in f.text) or '@' in f.text or '€' in f.text:
                raise ValueError(f"{f.id}: numeric/identifier-like content cannot be static; replace or drop it.")
            text = f.text
        elif action == "replace":
            if row['replacement'] not in values:
                raise ValueError(f"{f.id}: choose a synthetic field.")
            text = values[row['replacement']]
        else:
            raise ValueError(f"{f.id}: pending/unknown decision blocks generation.")
        if not text:
            continue
        # Base-font encoding is deliberately restricted: fail rather than produce hidden substitutions.
        try:
            text.encode('cp1252')
        except UnicodeEncodeError:
            raise ValueError(f"{f.id}: unsupported characters; replace or drop this fragment.") from None
        if any(ord(c) < 32 for c in text):
            raise ValueError("Control characters are unsupported.")
        width = float(row['width'])
        page_w, page_h = document.pages[f.page]
        if not math.isfinite(width) or width <= 0 or f.x < 0 or f.x + width > page_w:
            raise ValueError(f"{f.id}: field width is outside the page.")
        size = min(f.size, width / max(stringWidth(text, 'Helvetica', 1), .01))
        if size < 6 or f.y < 10 or f.y + size > page_h:
            raise ValueError(f"{f.id}: text will not fit; increase width or drop an adjacent fragment.")
        actual = stringWidth(text, 'Helvetica', size)
        rect = (f.x, f.y-size*.25, f.x+actual, f.y+size)
        for _, _, _, _, other in commands[f.page]:
            if rect[0] < other[2]-.5 and rect[2] > other[0]+.5 and rect[1] < other[3]-.5 and rect[3] > other[1]+.5:
                raise ValueError(f"{f.id}: output text overlaps another field.")
        commands[f.page].append((text, f.x, f.y, size, rect))
    if not any(commands):
        raise ValueError("The candidate would be empty.")
    out = BytesIO()
    c = canvas.Canvas(out, invariant=1)
    c.setTitle("Synthetic financial fixture")
    c.setAuthor("Statement Scrub")
    c.setSubject("FICTIONAL DATA - reconstructed test fixture, not financial evidence")
    for dimensions, page_commands in zip(document.pages, commands):
        c.setPageSize(dimensions)
        for text, x, y, size, _ in page_commands:
            c.setFont('Helvetica', size)
            c.drawString(x, y, text)
        c.showPage()
    c.save()
    result = out.getvalue()
    verify_clean_container(result)
    return result


def verify_clean_container(data: bytes) -> None:
    """Structural assertions for OUR writer, not a general anonymisation certificate."""
    reader = PdfReader(BytesIO(data))
    root = reader.trailer['/Root']
    if any(key in root for key in ['/Names', '/AcroForm', '/OpenAction', '/AA', '/Metadata', '/OCProperties']):
        raise ValueError("Unexpected document-level objects in generated PDF.")
    for page in reader.pages:
        if any(key in page for key in ['/Annots', '/AA', '/Metadata']):
            raise ValueError("Unexpected page-level objects in generated PDF.")
        if page['/Resources'].get('/XObject'):
            raise ValueError("Unexpected embedded image/form in generated PDF.")


def highlighted_preview(data: bytes, document: Document, rows: list[dict], page_number: int,
                        selected_id: str | None = None, scale: float = 1.4) -> bytes:
    """Review-only bitmap overlay; never used as a redacted/exported PDF."""
    from PIL import Image, ImageDraw
    from statement_scrub.detection import needs_review
    base = Image.open(BytesIO(preview(data, page_number, scale))).convert('RGBA')
    overlay = Image.new('RGBA', base.size)
    draw = ImageDraw.Draw(overlay)
    row_map = {r['id']: r for r in rows}
    height = document.pages[page_number][1]
    for f in document.fragments:
        if f.page != page_number:
            continue
        row = row_map[f.id]
        colour = (245,158,11) if needs_review(row) else (16,185,129) if row['action']=='replace' else (100,116,139)
        width = f.ink_width or min(f.width, stringWidth(f.text, 'Helvetica', f.size))
        box = (max(0,(f.x-1)*scale), max(0,(height-f.y-f.size)*scale),
               min(base.width,(f.x+width+1)*scale), min(base.height,(height-f.y+f.size*.3)*scale))
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        draw.rectangle(box, fill=(*colour,45), outline=(*colour,190), width=1)
        if f.id == selected_id:
            draw.rectangle(box, outline=(37,99,235,255), width=3)
    out = BytesIO()
    Image.alpha_composite(base,overlay).convert('RGB').save(out,format='PNG')
    return out.getvalue()
