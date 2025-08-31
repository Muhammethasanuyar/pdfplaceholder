# main.py
import os, json, re, tempfile, unicodedata, platform, ssl, shutil, urllib.request, logging
from typing import Dict, List, Tuple, Optional, DefaultDict
from collections import defaultdict
from shutil import which

import fitz  # PyMuPDF
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# ====== OCR ======
from PIL import Image
import pytesseract
from pytesseract import Output

DEBUG_AI = os.getenv("DEBUG_AI", "1") == "1"

# ---------- Logging ----------
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('logs/pdf_filler.log'), logging.StreamHandler()]
)
log = logging.getLogger("pdf-filler")

# ---------- Limits ----------
MAX_FILE_SIZE_MB = 50

def validate_file_size(data: bytes):
    if len(data) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"Dosya boyutu {len(data)/1024/1024:.1f}MB, maksimum {MAX_FILE_SIZE_MB}MB")

# ---------- Tesseract: auto-detect ----------
TESSERACT_CMD = os.getenv("TESSERACT_CMD", r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe").strip()
if TESSERACT_CMD and os.path.exists(TESSERACT_CMD):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
elif os.path.exists(r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"):
    pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

def _autodetect_tesseract() -> Optional[str]:
    if getattr(pytesseract.pytesseract, "tesseract_cmd", None):
        return pytesseract.pytesseract.tesseract_cmd
    p = which("tesseract") or which("tesseract.exe")
    if p:
        pytesseract.pytesseract.tesseract_cmd = p
        return p
    sys = platform.system().lower()
    candidates = []
    if "windows" in sys:
        candidates += [r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe", r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe"]
    elif "darwin" in sys or "mac" in sys:
        candidates += ["/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract", "/usr/bin/tesseract"]
    else:
        candidates += ["/usr/bin/tesseract", "/usr/local/bin/tesseract"]
    for c in candidates:
        if os.path.isfile(c):
            pytesseract.pytesseract.tesseract_cmd = c
            return c
    return None

_autodetect_tesseract()
OCR_LANGS = os.getenv("OCR_LANGS", "tur+eng")

# ---------- AI API Configuration ----------
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_API_URL = os.getenv("AI_API_URL", "https://api.openai.com/v1").strip()
AI_MODEL = os.getenv("AI_MODEL", "gpt-3.5-turbo").strip()
AI_ENABLED = bool(AI_API_KEY)

def ocr_is_available() -> bool:
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False

# ---------- FastAPI ----------
app = FastAPI(title="PDF Placeholder Filler", version="2.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ===================== Regex & Normalizasyon =====================
BRACE_MAP = {
    "\u007B": "{", "\uFF5B": "{", "\uFE5B": "{", "\u2774": "{", "\u2983": "{",
    "\u007D": "}", "\uFF5D": "}", "\uFE5C": "}", "\u2775": "}", "\u2984": "}",
}

def normalize_braces(s: str) -> str:
    return "".join(BRACE_MAP.get(ch, ch) for ch in s)

BRACKET_MAP = {"(":"{", ")":"}", "[":"{", "]":"}", "<":"{", ">":"}", "«":"{", "»":"}", "‹":"{", "›":"}", "（":"{","）":"}","［":"{","］":"}","《":"{","》":"}"}

def normalize_brackets(s: str) -> str:
    return "".join(BRACKET_MAP.get(ch, ch) for ch in s)

def normalize_invisibles(s: str) -> str:
    out = []
    for ch in s:
        cat = unicodedata.category(ch)
        out.append(" " if (cat == "Cf" or ch == "\u00A0") else ch)
    return "".join(out)

PH_RE     = re.compile(r"\{\{\s*([^}]+?)\s*\}\}", re.UNICODE)       # {{ key }}
PH_RE_OCR = re.compile(r"\{\s*\{\s*([^}]+?)\s*\}\s*\}", re.UNICODE) # { { key } }
CANDIDATE_RES = [PH_RE, PH_RE_OCR]

_TR_RE = re.compile(r"[ÇĞİÖŞÜçğıöşü]")

def _contains_tr(vals: List[str]) -> bool:
    return any(_TR_RE.search(v or "") for v in vals)

TR_CHARS = set("çğıöşüÇĞİÖŞÜ")

def needs_unicode(s: str) -> bool:
    return bool(s) and any((ord(ch) > 127) or (ch in TR_CHARS) for ch in s)

# ===================== Helpers =====================

def union_bbox(parts: List[Tuple[float, float, float, float]]) -> fitz.Rect:
    x0s, y0s, x1s, y1s = zip(*parts)
    return fitz.Rect(min(x0s), min(y0s), max(x1s), max(y1s))

def has_text_layer(pdf_bytes_or_path) -> bool:
    doc = fitz.open(stream=pdf_bytes_or_path, filetype="pdf") if isinstance(pdf_bytes_or_path, (bytes, bytearray)) else fitz.open(pdf_bytes_or_path)
    total = 0
    for p in doc:
        total += len(p.get_text("text") or "")
        if total:
            break
    doc.close()
    return total > 0

def normalize_mapping(mapping: Dict[str, str]) -> Dict[str, str]:
    return {(k or "").strip().casefold(): str(v) for k, v in mapping.items()}

def _dedupe_hits(hits):
    seen = set(); out = []
    for h in hits:
        r = h["rect"] if isinstance(h["rect"], fitz.Rect) else fitz.Rect(*h["rect"])
        sig = (h["key"].casefold(), round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2), h.get("page", -1))
        if sig in seen:
            continue
        seen.add(sig)
        keep = {k: h[k] for k in ("font_name", "font_size", "font_color") if k in h}
        out.append({"key": h["key"], "rect": r, "page": h.get("page", -1), **keep})
    return out

# ===================== Local (text layer) detect =====================

def find_placeholders_by_spans(page: fitz.Page):
    hits = []
    raw = page.get_text("rawdict")
    for b in raw.get("blocks", []):
        if b.get("type", 0) != 0:
            continue
        for ln in b.get("lines", []):
            spans = ln.get("spans", [])
            if not spans:
                continue
            orig = "".join([s.get("text", "") for s in spans])
            norm = normalize_invisibles(normalize_brackets(normalize_braces(orig)))
            for rex in CANDIDATE_RES:
                for m in rex.finditer(norm):
                    s, e = m.span()
                    parts = []; pos = 0
                    for sp in spans:
                        t = sp.get("text", ""); n = len(t)
                        a, bnd = pos, pos + n
                        ov0, ov1 = max(s, a), min(e, bnd)
                        if ov0 < ov1 and n > 0:
                            x0, y0, x1, y1 = sp["bbox"]
                            fL = (ov0 - a) / n; fR = (ov1 - a) / n
                            xx0 = x0 + (x1 - x0) * fL
                            xx1 = x0 + (x1 - x0) * fR
                            parts.append((xx0, y0, xx1, y1))
                        pos = bnd
                    if parts:
                        r = union_bbox(parts); r.x0 -= .5; r.x1 += .5
                        best_font, best_size, best_col, best_i = None, None, (0, 0, 0), 0.0
                        for sp in spans:
                            sb = fitz.Rect(sp["bbox"]); inter = (sb & r)
                            ai = inter.get_area() if inter else 0.0
                            if ai > best_i:
                                best_i = ai
                                best_font = sp.get("font", "")
                                best_size = float(sp.get("size", 12))
                                best_col = _norm_color(sp.get("color", (0, 0, 0)))
                        hits.append({"key": m.group(1).strip(), "rect": r, "font_name": best_font, "font_size": best_size, "font_color": best_col})
    return hits

def find_placeholders_by_search(page: fitz.Page):
    hits = []
    raw = page.get_text("rawdict")
    for b in raw.get("blocks", []):
        if b.get("type", 0) != 0:
            continue
        for ln in b.get("lines", []):
            spans = ln.get("spans", [])
            if not spans:
                continue
            line_rect = fitz.Rect(ln.get("bbox", [0, 0, 0, 0]))
            orig = "".join([s.get("text", "") for s in spans])
            norm = normalize_invisibles(normalize_brackets(normalize_braces(orig)))
            for rex in CANDIDATE_RES:
                for m in rex.finditer(norm):
                    s, e = m.span()
                    segment = orig[s:e]
                    rects = page.search_for(segment) or []
                    band_top, band_bot = line_rect.y0 - 2, line_rect.y1 + 2
                    rects = [r for r in rects if (r.y0 >= band_top and r.y1 <= band_bot)]
                    if rects:
                        r = union_bbox([(r.x0, r.y0, r.x1, r.y1) for r in rects]); r.x0 -= .5; r.x1 += .5
                        best_font, best_size, best_col, best_i = None, None, (0, 0, 0), 0.0
                        for sp in spans:
                            sb = fitz.Rect(sp["bbox"]); inter = (sb & r)
                            ai = inter.get_area() if inter else 0.0
                            if ai > best_i:
                                best_i = ai
                                best_font = sp.get("font", "")
                                best_size = float(sp.get("size", 12))
                                best_col = _norm_color(sp.get("color", (0, 0, 0)))
                        hits.append({"key": m.group(1).strip(), "rect": r, "font_name": best_font, "font_size": best_size, "font_color": best_col})
    return hits

def find_freetext_placeholders(page: fitz.Page):
    hits = []
    for a in list(page.annots() or []):
        if a.type[0] == fitz.PDF_ANNOT_FREE_TEXT:
            content = (a.info.get("content") or "")
            txt = normalize_invisibles(normalize_braces(content))
            m = PH_RE.search(txt)
            if m:
                hits.append({"key": m.group(1).strip(), "rect": a.rect})
    return hits

def find_acroform_placeholders(doc: fitz.Document):
    hits = []
    for pno, page in enumerate(doc):
        for w in (page.widgets() or []):
            val = (w.field_value or "")
            txt = normalize_invisibles(normalize_braces(val))
            m = PH_RE.search(txt)
            if m:
                hits.append({"key": m.group(1).strip(), "rect": w.rect, "page": pno})
    return hits

def collect_placeholders(doc: fitz.Document):
    all_hits = []
    for pno, page in enumerate(doc):
        a = find_placeholders_by_spans(page)
        b = find_placeholders_by_search(page) if not a else []
        c = find_freetext_placeholders(page)
        for h in a + b + c:
            h["page"] = pno
            all_hits.append(h)
    all_hits.extend(find_acroform_placeholders(doc))
    return _dedupe_hits(all_hits)

# ===================== OCR detect (scan PDFs) =====================

def _page_pixmap_to_pil(page: fitz.Page, dpi=240):
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    sx = page.rect.width / float(pix.width or 1)
    sy = page.rect.height / float(pix.height or 1)
    return img, sx, sy

def ocr_placeholders_on_page(page: fitz.Page, dpi=240, psm_list=(6, 11, 4)):
    for psm in psm_list:
        img, sx, sy = _page_pixmap_to_pil(page, dpi=dpi)
        data = pytesseract.image_to_data(img, lang=OCR_LANGS, output_type=Output.DICT, config=f"--oem 3 --psm {psm}")
        n = len(data.get("text", [])); lines = {}
        for i in range(n):
            txt = (data["text"][i] or "")
            if not txt.strip():
                continue
            left = int(data["left"][i]); top = int(data["top"][i]); width = int(data["width"][i]); height = int(data["height"][i])
            b = int(data["block_num"][i]); p = int(data["par_num"][i]); ln = int(data["line_num"][i])
            key = (b, p, ln)
            lines.setdefault(key, []).append({"text": txt, "left": left, "top": top, "width": width, "height": height})
        hits = []
        for _, tokens in lines.items():
            tokens.sort(key=lambda t: t["left"])
            token_texts = [t["text"] for t in tokens]
            line_text = " ".join(token_texts)
            norm_line = normalize_invisibles(normalize_brackets(normalize_braces(line_text)))
            idx_map = []; pos = 0
            for t in token_texts:
                a = pos; pos += len(t); idx_map.append((a, pos, len(t))); pos += 1
            for rex in CANDIDATE_RES:
                for m in rex.finditer(norm_line):
                    s, e = m.span(); key_txt = m.group(1).strip()
                    parts = []
                    for j, tok in enumerate(tokens):
                        a, bnd, tlen = idx_map[j]
                        ov0, ov1 = max(s, a), min(e, bnd)
                        if ov0 < ov1 and tlen > 0:
                            x0 = tok["left"] * sx; y0 = tok["top"] * sy
                            x1 = (tok["left"] + tok["width"]) * sx; y1 = (tok["top"] + tok["height"]) * sy
                            fL = (ov0 - a) / tlen; fR = (ov1 - a) / tlen
                            xx0 = x0 + (x1 - x0) * max(0.0, min(1.0, fL))
                            xx1 = x0 + (x1 - x0) * max(0.0, min(1.0, fR))
                            if xx1 - xx0 < 0.5:
                                mid = (xx0 + xx1) / 2; xx0, xx1 = mid - 0.25, mid + 0.25
                            parts.append((xx0, y0, xx1, y1))
                    if parts:
                        r = union_bbox(parts); r.x0 -= .5; r.x1 += .5
                        hits.append({"key": key_txt, "rect": r})
        if hits:
            return hits
    return []

def ai_detect_placeholders_ocr(pdf_bytes: bytes, dpi=240):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    all_hits = []
    for pno, page in enumerate(doc):
        ph = ocr_placeholders_on_page(page, dpi=dpi, psm_list=(6, 11, 4))
        for h in ph:
            h["page"] = pno; all_hits.append(h)
    doc.close()
    return _dedupe_hits(all_hits)

# ===================== Writing (transparent, no background) =====================

def _measure_width(page: fitz.Page, text: str, fontname: str, fontsize: float) -> float:
    fn = getattr(page, "get_text_length", None)
    if fn:
        return float(fn(text, fontname=fontname, fontsize=float(fontsize)))
    return float(fitz.get_text_length(text, fontname=fontname, fontsize=float(fontsize)))

def _norm_color(c) -> Tuple[float, float, float]:
    """PyMuPDF span color'unu 0..1 (r,g,b) formatına dönüştür."""
    try:
        if isinstance(c, (list, tuple)) and len(c) >= 3:
            r, g, b = c[0], c[1], c[2]
            if max(r, g, b) > 1.0:
                return (float(r) / 255.0, float(g) / 255.0, float(b) / 255.0)
            return (float(r), float(g), float(b))
        if isinstance(c, (int, float)):
            v = float(c)
            if v > 1.0:
                v = v / 255.0
            v = max(0.0, min(1.0, v))
            return (v, v, v)
    except Exception:
        pass
    return (0.0, 0.0, 0.0)

def _draw_singleline_fit(page: fitz.Page, rect: fitz.Rect, text: str, fontname: str,
                         align: int, min_fs: float, max_fs: float, pad: float, color=(0, 0, 0)):
    inner = fitz.Rect(rect.x0 + pad, rect.y0 + pad, rect.x1 - pad, rect.y1 - pad)
    if inner.width <= 0 or inner.height <= 0:
        return
    fs = min(max_fs, max(min_fs, inner.height * 0.98))
    for _ in range(18):
        w = _measure_width(page, text, fontname, fs)
        if w <= inner.width + 0.01:
            break
        if w > 0:
            fs = max(min_fs, fs * (inner.width / w))
        else:
            break
    width_now = _measure_width(page, text, fontname, fs)
    if align == 0:
        x = inner.x0
    elif align == 1:
        x = inner.x0 + (inner.width - width_now) / 2
    else:
        x = inner.x1 - width_now
    x = max(inner.x0, min(x, inner.x1))
    baseline = inner.y0 + (inner.height - fs) / 2 + fs * 0.8
    page.insert_text((x, baseline), text, fontname=fontname, fontsize=fs, color=color)

def insert_text_no_bg(page: fitz.Page, rect: fitz.Rect, text: str, fontname: str,
                      align: int, min_fs: float, max_fs: float, pad: float,
                      fit_mode: str, text_rgb=(0, 0, 0), size_hint: Optional[float] = None):
    """Insert text without painting background, fitting to rect.
    text_rgb is (r,g,b) 0..1.
    """
    if (fit_mode or "single").lower() != "single":
        inner = fitz.Rect(rect.x0 + pad, rect.y0 + pad, rect.x1 - pad, rect.y1 - pad)
        fs = min(max_fs, max(min_fs, inner.height * 0.95))
        if size_hint:
            fs = max(min_fs, min(max_fs, size_hint))
        step = 0.5

        def fits(size):
            sh = page.new_shape()
            leftover = sh.insert_textbox(inner, text, fontname=fontname, fontsize=size, color=text_rgb, align=align)
            return leftover == ""

        while fs + step <= max_fs and fits(fs + step):
            fs += step
        while not fits(fs) and fs - step >= min_fs:
            fs -= step
        page.insert_textbox(inner, text, fontname=fontname, fontsize=fs, color=text_rgb, align=align)
        return

    use_max = max_fs
    if size_hint:
        use_max = max(min_fs, min(max_fs, float(size_hint) * 1.05))
    _draw_singleline_fit(page, rect, text, fontname, align, float(min_fs), float(use_max), float(pad), color=text_rgb)
FONT_SOURCES = {
    "DejaVuSans.ttf": [
        "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans.ttf",
        "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/version_2_37/ttf/DejaVuSans.ttf",
    ],
    "NotoSans-Regular.ttf": [
        "https://github.com/notofonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf",
        "https://raw.githubusercontent.com/notofonts/noto-fonts/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf",
    ],
    "FreeSans.ttf": [
        "https://github.com/gnu-freefont/freefont-ttf/raw/master/FreeSans.ttf",
        "https://raw.githubusercontent.com/gnu-freefont/freefont-ttf/master/FreeSans.ttf",
    ],
}
PREFERRED_FONT_NAMES = ["DejaVuSans", "DejaVu Sans", "NotoSans", "Noto Sans", "FreeSans", "Arial", "Tahoma", "Verdana", "Calibri", "Times New Roman", "Segoe UI", "Roboto", "Open Sans", "Source Sans Pro", "Ubuntu", "Cantarell", "PT Sans"]

def _fonts_dir_candidates() -> list:
    sys = platform.system().lower()
    dirs = ["fonts"]
    if "windows" in sys:
        win = os.environ.get("WINDIR", r"C:\\Windows"); dirs.append(os.path.join(win, "Fonts"))
    if "linux" in sys:
        dirs += ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.local/share/fonts"), os.path.expanduser("~/.fonts")]
    if "darwin" in sys or "mac" in sys:
        dirs += ["/Library/Fonts", "/System/Library/Fonts", os.path.expanduser("~/Library/Fonts")]
    seen = set(); out = []
    for d in dirs:
        if d and os.path.isdir(d):
            ad = os.path.abspath(d)
            if ad not in seen:
                seen.add(ad); out.append(ad)
    return out

def _walk_font_paths() -> list:
    paths = []
    for root in _fonts_dir_candidates():
        for base, _, files in os.walk(root):
            for fn in files:
                if os.path.splitext(fn)[1].lower() in (".ttf", ".otf"):
                    paths.append(os.path.join(base, fn))
    seen = set(); out = []
    for p in paths:
        if p in seen:
            continue
        seen.add(p); out.append(p)
    return out

def _score_font_path(p: str) -> int:
    name = os.path.basename(p).lower()
    score = 0
    for pref in PREFERRED_FONT_NAMES:
        if pref.lower().replace(" ", "") in name.replace(" ", ""):
            score += 20
    if any(tag in name for tag in ("regular", "book", "normal")):
        score += 5
    if "emoji" in name or "symbol" in name:
        score -= 10
    if "mono" in name:
        score -= 3
    return score

def _download(url: str, dst_path: str) -> bool:
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(url, timeout=30, context=ctx) as r, open(dst_path, "wb") as f:
            f.write(r.read())
        return True
    except Exception:
        return False

def ensure_fonts() -> list:
    fonts_dir = os.path.abspath("fonts"); os.makedirs(fonts_dir, exist_ok=True)
    actions = []
    sys_fonts = _walk_font_paths()
    for fname, urls in FONT_SOURCES.items():
        dst = os.path.join(fonts_dir, fname)
        if os.path.exists(dst):
            continue
        family = os.path.splitext(fname)[0].lower().replace("-", "").replace("_", "")
        sys_match = None
        for p in sys_fonts:
            bn = os.path.basename(p).lower()
            if bn == fname.lower() or family in bn.replace("-", "").replace("_", ""):
                sys_match = p; break
        if sys_match:
            try:
                shutil.copyfile(sys_match, dst); actions.append(("copy", dst, sys_match)); continue
            except Exception:
                pass
        for url in urls:
            if _download(url, dst):
                actions.append(("download", dst, url)); break
    return actions

def choose_font(doc: fitz.Document, preferred_path: str, sample_texts: List[str]) -> Tuple[str, str]:
    if not hasattr(doc, "insert_font"):
        return "helv", "builtin_helv"
    if preferred_path and os.path.exists(preferred_path):
        try:
            return doc.insert_font(fontfile=preferred_path), preferred_path
        except Exception:
            pass
    local = []
    fonts_dir = os.path.abspath("fonts")
    if os.path.isdir(fonts_dir):
        for fn in os.listdir(fonts_dir):
            if os.path.splitext(fn)[1].lower() in (".ttf", ".otf"):
                local.append(os.path.join(fonts_dir, fn))
    local.sort(key=_score_font_path, reverse=True)
    for p in local:
        try:
            return doc.insert_font(fontfile=p), p
        except Exception:
            continue
    candidates = _walk_font_paths(); candidates.sort(key=_score_font_path, reverse=True)
    for p in candidates:
        try:
            return doc.insert_font(fontfile=p), p
        except Exception:
            continue
    return "helv", "builtin_helv"

def _strip_subset(name: str) -> str:
    if not name:
        return ""
    if "+" in name and len(name.split("+", 1)[0]) in (5, 6, 7):
        return name.split("+", 1)[1]
    return name

def _looks_subset(n: str) -> bool:
    return bool(n and "+" in n and len(n.split("+", 1)[0]) in (5, 6, 7) and n.split("+", 1)[0].isupper())

def build_page_font_index(doc: fitz.Document, pno: int) -> Dict[str, int]:
    idx = {}
    try:
        recs = doc.get_page_fonts(pno)
    except Exception:
        recs = getattr(doc[pno], "get_fonts", lambda: [])()
    for rec in (recs or []):
        xref = rec[0]; name = str(rec[2]) if len(rec) > 2 else ""; base = str(rec[3]) if len(rec) > 3 else ""
        for k in {name, base, _strip_subset(name), _strip_subset(base)}:
            if k:
                idx[k.lower()] = xref
    return idx

def pick_pdf_font_for_hit(doc: fitz.Document, page: fitz.Page, hit: dict, cache: Dict[int, str]) -> Tuple[Optional[str], Optional[float]]:
    fontname_in_span = (hit.get("font_name") or "").strip()
    size_hint = float(h.get("font_size") or 0) if (h := hit) else 0 or None
    if not hasattr(doc, "insert_font"):
        return None, size_hint
    if not fontname_in_span:
        best_font, best_size, best_i = None, None, 0.0
        raw = page.get_text("rawdict"); r = hit["rect"] if isinstance(hit["rect"], fitz.Rect) else fitz.Rect(*hit["rect"])
        for b in raw.get("blocks", []):
            if b.get("type", 0) != 0:
                continue
            for ln in b.get("lines", []):
                for sp in ln.get("spans", []):
                    sb = fitz.Rect(sp["bbox"]); inter = (sb & r); ai = inter.get_area() if inter else 0.0
                    if ai > best_i:
                        best_i = ai; best_font = sp.get("font", ""); best_size = float(sp.get("size", 12))
        fontname_in_span = best_font or fontname_in_span; size_hint = size_hint or best_size
    if not fontname_in_span:
        return None, size_hint
    if _looks_subset(fontname_in_span):
        return None, size_hint
    idx = build_page_font_index(doc, hit["page"]); xref = None
    for key in {fontname_in_span, _strip_subset(fontname_in_span)}:
        if key and key.lower() in idx:
            xref = idx[key.lower()]; break
    if xref is None:
        return None, size_hint
    if xref in cache:
        return cache[xref], size_hint
    try:
        ext, buf, _name = doc.extract_font(xref)
        # Yalnızca sağlam (Unicode olma ihtimali yüksek) TTF/OTF ve yeterli boyuttakileri kabul et
        if not buf or len(buf) < 20000 or (ext and ext.lower() not in (".ttf", ".otf")):
            return None, size_hint
        alias = doc.insert_font(fontbuffer=buf); cache[xref] = alias; return alias, size_hint
    except Exception:
        return None, size_hint

# Prepare fonts at startup
try:
    acts = ensure_fonts()
    if DEBUG_AI and acts:
        log.debug(f"[FONT BOOTSTRAP] {acts}")
except Exception as e:
    log.debug(f"[FONT BOOTSTRAP] error: {e}")

# ===================== BACKGROUND-PRESERVING ERASE =====================

def erase_placeholder_text_preserve_background(doc: fitz.Document, hits: List[dict], keys_to_fill: set):
    """
    Placeholder metinlerini arka planı koruyarak şeffaf hale getirir.
    Bu yöntem arka plan rengini, gradient'ları ve görüntüleri korur.
    """
    by_page: DefaultDict[int, List[dict]] = defaultdict(list)
    for h in hits:
        if h["key"].casefold() in keys_to_fill:
            by_page[h["page"]].append(h)

    for pno, page_hits in by_page.items():
        page = doc[pno]
        for hit in page_hits:
            r = hit["rect"] if isinstance(hit["rect"], fitz.Rect) else fitz.Rect(*hit["rect"])
            try:
                bg_color = detect_background_color(page, r)
                shape = page.new_shape()
                shape.draw_rect(r)
                shape.finish(color=bg_color, fill=bg_color, width=0)
                shape.commit()
            except Exception as e:
                log.debug(f"Background preserving erase failed for hit {hit}: {e}")
            try:
                page.add_redact_annot(r, fill=None, cross_out=False, text=None)
            except Exception:
                pass
        try:
            page.apply_redactions()
        except Exception:
            pass

def detect_background_color(page: fitz.Page, rect: fitz.Rect) -> Tuple[float, float, float]:
    """ Basit ortalama renk tahmini (RGB 0..1). """
    try:
        pix = page.get_pixmap(clip=rect, alpha=False)
        if hasattr(pix, 'samples'):
            samples = pix.samples
            if len(samples) >= 3:
                width, height = pix.width, pix.height
                total_pixels = width * height
                if total_pixels > 0:
                    r = sum(samples[i] for i in range(0, len(samples), 3)) / total_pixels / 255.0
                    g = sum(samples[i] for i in range(1, len(samples), 3)) / total_pixels / 255.0
                    b = sum(samples[i] for i in range(2, len(samples), 3)) / total_pixels / 255.0
                    return (r, g, b)
        return (1.0, 1.0, 1.0)
    except Exception as e:
        log.debug(f"Background color detection failed: {e}")
        return (1.0, 1.0, 1.0)

# ===================== ENHANCED TRANSPARENT TEXT INSERTION =====================

def insert_transparent_text(page: fitz.Page, rect: fitz.Rect, text: str, fontname: str,
                            align: int, min_fs: float, max_fs: float, pad: float,
                            fit_mode: str, text_rgb=(0, 0, 0), size_hint: Optional[float] = None,
                            transparency: float = 1.0):
    """
    Metni şeffaf arka plan ile yerleştirir. Arka planı bozmaz.
    transparency: 0.0 (tamamen şeffaf) - 1.0 (opak)
    """
    if (fit_mode or "single").lower() != "single":
        inner = fitz.Rect(rect.x0 + pad, rect.y0 + pad, rect.x1 - pad, rect.y1 - pad)
        fs = min(max_fs, max(min_fs, inner.height * 0.95))
        if size_hint:
            fs = max(min_fs, min(max_fs, size_hint))
        step = 0.5

        def fits(size):
            sh = page.new_shape()
            leftover = sh.insert_textbox(inner, text, fontname=fontname, fontsize=size, color=text_rgb, align=align)
            return leftover == ""

        while fs + step <= max_fs and fits(fs + step):
            fs += step
        while not fits(fs) and fs - step >= min_fs:
            fs -= step
        page.insert_textbox(inner, text, fontname=fontname, fontsize=fs, color=text_rgb, align=align, overlay=True)
        return

    use_max = max_fs
    if size_hint:
        use_max = max(min_fs, min(max_fs, float(size_hint) * 1.05))
    _draw_singleline_fit_transparent(page, rect, text, fontname, align, float(min_fs), float(use_max), float(pad), color=text_rgb, transparency=transparency)

def _draw_singleline_fit_transparent(page: fitz.Page, rect: fitz.Rect, text: str, fontname: str,
                                     align: int, min_fs: float, max_fs: float, pad: float,
                                     color=(0, 0, 0), transparency: float = 1.0):
    inner = fitz.Rect(rect.x0 + pad, rect.y0 + pad, rect.x1 - pad, rect.y1 - pad)
    if inner.width <= 0 or inner.height <= 0:
        return
    fs = min(max_fs, max(min_fs, inner.height * 0.98))
    for _ in range(18):
        w = _measure_width(page, text, fontname, fs)
        if w <= inner.width + 0.01:
            break
        if w > 0:
            fs = max(min_fs, fs * (inner.width / w))
        else:
            break
    width_now = _measure_width(page, text, fontname, fs)
    if align == 0:
        x = inner.x0
    elif align == 1:
        x = inner.x0 + (inner.width - width_now) / 2
    else:
        x = inner.x1 - width_now
    x = max(inner.x0, min(x, inner.x1))
    baseline = inner.y0 + (inner.height - fs) / 2 + fs * 0.8
    page.insert_text((x, baseline), text, fontname=fontname, fontsize=fs, color=color, overlay=True)

# ===================== ADVANCED FONT ANALYSIS =====================

def analyze_pdf_fonts_advanced(doc: fitz.Document) -> Dict[str, any]:
    analysis = {
        "fonts": [],
        "font_families": set(),
        "styles": {"regular": 0, "bold": 0, "italic": 0, "bold_italic": 0},
        "turkish_support": [],
        "recommended_replacements": {},
        "quality_score": 0.0,
    }

    for pno in range(doc.page_count):
        try:
            font_list = doc.get_page_fonts(pno)
        except Exception:
            font_list = getattr(doc[pno], "get_fonts", lambda: [])()
        for font_rec in (font_list or []):
            if len(font_rec) < 4:
                continue
            xref = int(font_rec[0]); name = str(font_rec[2]) if len(font_rec) > 2 else ""; base = str(font_rec[3]) if len(font_rec) > 3 else ""
            try:
                ext, buf, realname = doc.extract_font(xref)
                font_info = {
                    "xref": xref,
                    "name": name,
                    "base": base,
                    "realname": realname or "",
                    "ext": ext or "",
                    "size_bytes": len(buf) if buf else 0,
                    "embedded": bool(buf),
                    "is_subset": _looks_subset(name) or _looks_subset(base),
                    "page": pno,
                }
                font_info["style"] = analyze_font_style(name, base)
                family = extract_font_family(name, base)
                if family:
                    analysis["font_families"].add(family)
                    font_info["family"] = family
                font_info["turkish_support"] = check_turkish_support(name, base, ext)
                if font_info["turkish_support"]:
                    analysis["turkish_support"].append(font_info)
                font_info["quality_score"] = calculate_font_quality(font_info)
                analysis["fonts"].append(font_info)
            except Exception as e:
                log.debug(f"Font analysis error for xref {xref}: {e}")

    if analysis["fonts"]:
        analysis["quality_score"] = sum(f["quality_score"] for f in analysis["fonts"]) / len(analysis["fonts"])
    analysis["recommended_replacements"] = generate_font_recommendations(analysis)
    analysis["font_families"] = list(analysis["font_families"])
    return analysis

def analyze_font_style(name: str, base: str) -> str:
    combined = f"{name} {base}".lower()
    is_bold = any(keyword in combined for keyword in ["bold", "heavy", "black", "extra", "ultra"])
    is_italic = any(keyword in combined for keyword in ["italic", "oblique", "slant"])
    if is_bold and is_italic:
        return "bold_italic"
    elif is_bold:
        return "bold"
    elif is_italic:
        return "italic"
    else:
        return "regular"

def extract_font_family(name: str, base: str) -> str:
    if base and base != name:
        return base.split("-")[0].split(" ")[0]
    if name:
        clean_name = _strip_subset(name)
        return clean_name.split("-")[0].split(" ")[0]
    return ""

def check_turkish_support(name: str, base: str, ext: str) -> bool:
    if ext and ext.lower() in [".ttf", ".otf"]:
        return True
    turkish_fonts = [
        "dejavu", "noto", "liberation", "freesans", "arial", "tahoma",
        "verdana", "calibri", "times", "georgia", "comic",
    ]
    combined = f"{name} {base}".lower()
    return any(font in combined for font in turkish_fonts)

def calculate_font_quality(font_info: Dict) -> float:
    score = 0.0
    if font_info["embedded"]:
        score += 0.3
    if font_info.get("turkish_support"):
        score += 0.2
    if not font_info.get("is_subset"):
        score += 0.2
    if font_info["size_bytes"] > 50000:
        score += 0.2
    elif font_info["size_bytes"] > 20000:
        score += 0.1
    if font_info["ext"].lower() in [".ttf", ".otf"]:
        score += 0.1
    return min(1.0, score)

def generate_font_recommendations(analysis: Dict) -> Dict[str, str]:
    recommendations = {}
    for font in analysis["fonts"]:
        if font["quality_score"] < 0.5:
            if not font["turkish_support"]:
                recommendations[font["name"]] = "DejaVu Sans (Türkçe karakter desteği için)"
            elif font["is_subset"]:
                recommendations[font["name"]] = "Liberation Sans (subset sorunu için)"
            elif not font["embedded"]:
                recommendations[font["name"]] = "Noto Sans (embedding için)"
    return recommendations

# ===================== AI-POWERED FONT ANALYSIS (placeholders) =====================

def ai_analyze_font_usage(doc: fitz.Document, placeholders: List[dict]) -> Dict[str, any]:
    analysis = {
        "placeholder_fonts": {},
        "ai_recommendations": {},
        "confidence_scores": {},
        "usage_patterns": {},
    }
    for placeholder in placeholders:
        page_no = placeholder.get("page", 0)
        rect = placeholder.get("rect", [0, 0, 0, 0])
        key = placeholder.get("key", "")
        if page_no >= doc.page_count:
            continue
        page = doc[page_no]
        font_usage = analyze_text_in_region(page, rect)
        if font_usage:
            analysis["placeholder_fonts"][key] = font_usage
            recommendation = generate_ai_font_recommendation(font_usage, placeholder)
            analysis["ai_recommendations"][key] = recommendation
            analysis["confidence_scores"][key] = calculate_recommendation_confidence(font_usage)
    analysis["usage_patterns"] = analyze_font_patterns(analysis["placeholder_fonts"])
    return analysis

def analyze_text_in_region(page: fitz.Page, rect) -> Dict:
    if isinstance(rect, list) and len(rect) >= 4:
        rect = fitz.Rect(rect)
    elif not isinstance(rect, fitz.Rect):
        return {}
    try:
        blocks = page.get_text("dict", clip=rect)
        font_usage = {"fonts": [], "primary_font": None, "text_content": ""}
        for block in blocks.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    font_name = span.get("font", ""); font_size = span.get("size", 0); text = span.get("text", "")
                    if font_name and text.strip():
                        font_info = {"name": font_name, "size": font_size, "text": text, "confidence": 1.0}
                        font_usage["fonts"].append(font_info)
                        font_usage["text_content"] += text
        if font_usage["fonts"]:
            font_counts = {}
            for f in font_usage["fonts"]:
                font_counts[f["name"]] = font_counts.get(f["name"], 0) + len(f["text"])
            primary = max(font_counts.items(), key=lambda x: x[1])
            font_usage["primary_font"] = primary[0]
        return font_usage
    except Exception as e:
        log.debug(f"Text region analysis failed: {e}")
        return {}

def generate_ai_font_recommendation(font_usage: Dict, placeholder: Dict) -> Dict:
    recommendation = {
        "suggested_font": "DejaVu Sans",
        "reason": "Varsayılan güvenli seçim",
        "alternatives": ["Noto Sans", "Liberation Sans"],
        "confidence": 0.5,
        "ai_powered": False,
    }
    primary_font = font_usage.get("primary_font", "")
    text_content = font_usage.get("text_content", "")
    has_turkish = needs_unicode(text_content)
    if primary_font:
        if any(good in primary_font.lower() for good in ["dejavu", "noto", "liberation", "arial", "tahoma"]):
            recommendation.update({"suggested_font": primary_font, "reason": "Mevcut font kaliteli ve uygun", "confidence": 0.8})
        elif has_turkish:
            recommendation.update({"suggested_font": "DejaVu Sans", "reason": "Türkçe karakter desteği gerekli", "confidence": 0.9})
    return recommendation

async def get_ai_font_suggestion(current_font: str, text_content: str, placeholder: Dict) -> Optional[Dict]:
    if not AI_ENABLED:
        return None
    try:
        import urllib.request
        prompt = create_font_analysis_prompt(current_font, text_content, placeholder)
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {AI_API_KEY}"}
        payload = {
            "model": AI_MODEL,
            "messages": [
                {"role": "system", "content": "Sen bir PDF typography uzmanısın. Fontlar hakkında teknik öneriler veriyorsun."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 300,
            "temperature": 0.3,
        }
        req = urllib.request.Request(
            f"{AI_API_URL}/chat/completions",
            data=json.dumps(payload).encode(),
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode())
            if "choices" in result and result["choices"]:
                ai_response = result["choices"][0]["message"]["content"]
                return parse_ai_font_response(ai_response)
    except Exception as e:
        log.debug(f"AI API call failed: {e}")
        return None


def create_font_analysis_prompt(current_font: str, text_content: str, placeholder: Dict) -> str:
    has_turkish = needs_unicode(text_content)
    sample_text = text_content[:100] if text_content else ""
    prompt = f"""
PDF'deki bir placeholder için en uygun font önerisi ver:

Mevcut Font: {current_font}
Metin İçeriği: "{sample_text}"
Türkçe Karakter: {"Evet" if has_turkish else "Hayır"}
Placeholder Boyutu: {placeholder.get('rect', [0,0,0,0])}

Kısa ve net bir JSON yanıt ver:
{{
  "suggested_font": "font adı",
  "reason": "öneri sebebi",
  "confidence": 0.8,
  "alternatives": ["font1", "font2"]
}}

Sadece yaygın, güvenilir fontları öner: DejaVu Sans, Noto Sans, Liberation Sans, Arial, Times New Roman
"""
    return prompt.strip()


def parse_ai_font_response(ai_response: str) -> Optional[Dict]:
    try:
        json_match = re.search(r'\{[^}]+\}', ai_response)
        if json_match:
            json_str = json_match.group()
            parsed = json.loads(json_str)
            if all(key in parsed for key in ["suggested_font", "reason", "confidence"]):
                return {
                    "suggested_font": str(parsed["suggested_font"]),
                    "reason": str(parsed["reason"]),
                    "confidence": float(parsed.get("confidence", 0.5)),
                    "alternatives": parsed.get("alternatives", []),
                }
    except Exception as e:
        log.debug(f"AI response parsing failed: {e}")
    return None

# ===================== AI API STATUS =====================
@app.get("/ai_status")
def get_ai_status():
    return {
        "ai_enabled": AI_ENABLED,
        "api_url": AI_API_URL if AI_ENABLED else "",
        "model": AI_MODEL if AI_ENABLED else "",
        "status": "configured" if AI_ENABLED else "not_configured",
    }


def calculate_recommendation_confidence(font_usage: Dict) -> float:
    if not font_usage.get("fonts"):
        return 0.0
    text_length = len(font_usage.get("text_content", ""))
    if text_length < 5:
        return 0.3
    elif text_length < 20:
        return 0.6
    else:
        return 0.9


def analyze_font_patterns(placeholder_fonts: Dict) -> Dict:
    patterns = {"most_used_fonts": {}, "consistency_score": 0.0, "recommendations": []}
    font_counts = {}
    for _key, usage in placeholder_fonts.items():
        primary = usage.get("primary_font")
        if primary:
            font_counts[primary] = font_counts.get(primary, 0) + 1
    patterns["most_used_fonts"] = dict(sorted(font_counts.items(), key=lambda x: x[1], reverse=True))
    if font_counts:
        total_placeholders = len(placeholder_fonts)
        most_common_count = max(font_counts.values())
        patterns["consistency_score"] = most_common_count / total_placeholders
        if patterns["consistency_score"] < 0.7:
            patterns["recommendations"].append("Font tutarlılığını artırmak için tek bir font ailesi kullanın")
    return patterns

# ===================== API =====================
@app.get("/ocr_status")
def ocr_status():
    cmd = getattr(pytesseract.pytesseract, "tesseract_cmd", "") or ""
    vers = ""
    try:
        vers = str(pytesseract.get_tesseract_version())
    except Exception:
        pass
    return {"available": ocr_is_available(), "cmd": cmd, "version": vers, "langs": OCR_LANGS}

@app.post("/analyze")
async def analyze_pdf(template: UploadFile = File(...)):
    if template.content_type != "application/pdf":
        raise HTTPException(400, "PDF dosyası yükleyin")
    data = await template.read(); validate_file_size(data)
    if not has_text_layer(data):
        return {"warning": "no_text_layer", "hint": "Tarama PDF olabilir. provider=ocr deneyin.", "pages": 0, "placeholders": [], "unique_keys": []}
    doc = fitz.open(stream=data, filetype="pdf")
    hits = collect_placeholders(doc); pages = doc.page_count; doc.close()
    res = []; keys = []
    for h in hits:
        r = h["rect"]
        res.append({"key": h["key"], "key_norm": h["key"].casefold(), "page": h["page"], "rect": [r.x0, r.y0, r.x1, r.y1], "font_name": h.get("font_name"), "font_size": h.get("font_size")})
        keys.append(h["key"])
    unique = sorted(set(keys), key=lambda x: keys.index(x))
    return {"pages": pages if res else 0, "placeholders": res, "unique_keys": unique}

@app.post("/fonts")
async def list_fonts(template: UploadFile = File(...)):
    if template.content_type != "application/pdf":
        raise HTTPException(400, "PDF dosyası yükleyin")
    data = await template.read(); validate_file_size(data)
    doc = fitz.open(stream=data, filetype="pdf")
    fonts: Dict[int, dict] = {}
    for pno in range(doc.page_count):
        try:
            recs = doc.get_page_fonts(pno)
        except Exception:
            recs = getattr(doc[pno], "get_fonts", lambda: [])()
        for rec in (recs or []):
            xref = int(rec[0]); name = str(rec[2]) if len(rec) > 2 else ""; base = str(rec[3]) if len(rec) > 3 else ""
            if xref in fonts:
                continue
            info = {"xref": xref, "name": name, "base": base, "name_stripped": _strip_subset(name), "base_stripped": _strip_subset(base)}
            try:
                ext, buf, realname = doc.extract_font(xref)
                info.update({"ext": ext or "", "embedded": bool(buf), "bytes": len(buf) if buf else 0, "realname": realname or ""})
            except Exception:
                info.update({"ext": "", "embedded": False, "bytes": 0, "realname": ""})
            info["subset_like"] = _looks_subset(name) or _looks_subset(base) or (info["bytes"] and info["bytes"] < 20000)
            fonts[xref] = info
    doc.close()
    arr = sorted(fonts.values(), key=lambda x: (-x.get("bytes", 0), x["name_stripped"].lower()))
    return {"fonts": arr}

@app.post("/analyze_fonts")
async def analyze_fonts_advanced_ep(template: UploadFile = File(...)):
    if template.content_type != "application/pdf":
        raise HTTPException(400, "PDF dosyası yükleyin")
    data = await template.read(); validate_file_size(data)
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        analysis = analyze_pdf_fonts_advanced(doc)
        hits = collect_placeholders(doc)
        if hits:
            ai_analysis = ai_analyze_font_usage(doc, hits)
            analysis["ai_analysis"] = ai_analysis
        doc.close()
        return analysis
    except Exception as e:
        doc.close()
        raise HTTPException(500, f"Font analizi hatası: {str(e)}")

@app.post("/font_recommendations")
async def get_font_recommendations(
    template: UploadFile = File(...),
    placeholder_text: str = Form(""),
    use_ai: bool = Form(True),
):
    if template.content_type != "application/pdf":
        raise HTTPException(400, "PDF dosyası yükleyin")
    data = await template.read(); validate_file_size(data)
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        recommendations = {
            "general_recommendations": {},
            "placeholder_specific": {},
            "ai_suggestions": {},
            "quality_report": {},
        }
        font_analysis = analyze_pdf_fonts_advanced(doc)
        recommendations["general_recommendations"] = font_analysis["recommended_replacements"]
        recommendations["quality_report"] = {
            "overall_score": font_analysis["quality_score"],
            "turkish_support_count": len(font_analysis["turkish_support"]),
            "total_fonts": len(font_analysis["fonts"]),
        }
        if use_ai:
            hits = collect_placeholders(doc)
            if hits:
                ai_analysis = ai_analyze_font_usage(doc, hits)
                recommendations["ai_suggestions"] = ai_analysis.get("ai_recommendations", {})
                recommendations["placeholder_specific"] = ai_analysis.get("usage_patterns", {})
        doc.close()
        return recommendations
    except Exception as e:
        doc.close()
        raise HTTPException(500, f"Öneri sistemi hatası: {str(e)}")


def _alias_looks_builtin(alias: Optional[str]) -> bool:
    if not alias:
        return True
    a = str(alias).lower()
    return a.startswith("builtin_") or (a == "helv")


def process_fill_request(
    data: bytes,
    mapping: Dict[str, str],
    align_map: Dict[str, int],
    text_rgb: Tuple[float, float, float],
    font_path: str,
    provider: str,
    min_fs: float,
    max_fs: float,
    pad: float,
    fit_mode: str,
    size_mode: str,
    fixed_fs: float,
    auto_font: int,
    selected_font_xref: int,
    force_selected_font: int,
    erase_mode: str,
) -> Tuple[str, Dict[str, str], List[str]]:
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        EMBED_OK = hasattr(doc, "insert_font")
        fallback_alias, chosen_font_path = choose_font(doc, font_path, list(mapping.values()))

        # selected PDF font to mimic style (optional)
        selected_alias = None
        selected_meta = {"ext": "", "bytes": 0, "subset_like": True}
        if EMBED_OK and int(selected_font_xref) > 0:
            try:
                ext, buf, realname = doc.extract_font(int(selected_font_xref))
                if buf:
                    selected_alias = doc.insert_font(fontbuffer=buf)
                    selected_meta = {
                        "ext": ext or "",
                        "bytes": len(buf),
                        "subset_like": (len(buf) < 20000) or (ext and ext.lower() not in (".ttf", ".otf")),
                        "realname": realname or "",
                    }
            except Exception as e:
                log.debug(f"[SELECTED-FONT] failed: {e}")

        # Detect placeholders
        prov = (provider or "auto").lower()
        text_layer = has_text_layer(data)
        hits = []; detect_hdr = ""
        if prov == "local":
            if text_layer:
                hits = collect_placeholders(doc)
            elif ocr_is_available():
                hits = ai_detect_placeholders_ocr(data); detect_hdr = "local->ocr"
        elif prov == "ocr":
            if ocr_is_available():
                hits = ai_detect_placeholders_ocr(data)
            elif text_layer:
                hits = collect_placeholders(doc); detect_hdr = "ocr->local"
        else:  # auto
            if text_layer:
                hits = collect_placeholders(doc)
                if not hits and ocr_is_available():
                    hits = ai_detect_placeholders_ocr(data); detect_hdr = "auto_ocr_used"
            else:
                if ocr_is_available():
                    hits = ai_detect_placeholders_ocr(data); detect_hdr = "auto_ocr_used"
        log.debug(f"Detected {len(hits)} placeholders")

        # TR-safe fallback: don't stay on builtin 'helv' if Turkish present
        if fallback_alias == "helv" and _contains_tr(list(mapping.values())) and EMBED_OK:
            for p in ["fonts/DejaVuSans.ttf", "fonts/NotoSans-Regular.ttf", "fonts/FreeSans.ttf"]:
                if os.path.exists(p):
                    try:
                        fallback_alias = doc.insert_font(fontfile=p); font_path = p; break
                    except Exception:
                        pass

        # ERASE (background-preserving)
        if (erase_mode or "redact").lower() == "redact":
            try:
                erase_placeholder_text_preserve_background(doc, hits, set(mapping.keys()))
                log.debug(f"Background-preserving erase applied to {len(hits)} placeholders")
            except Exception as e:
                log.debug(f"Background-preserving erase failed: {e}")

        # Fill
        alias_cache: Dict[int, str] = {}
        filled = set()
        for h in hits:
            key_norm = h["key"].casefold()
            if key_norm not in mapping:
                continue
            val = mapping[key_norm]
            page = doc[h["page"]]
            align = align_map.get(key_norm, 0)
            r = h["rect"] if isinstance(h["rect"], fitz.Rect) else fitz.Rect(*h["rect"])

            # 1) initially choose alias
            font_alias = selected_alias if selected_alias else None
            size_hint = float(h.get("font_size") or 0) or None
            if (font_alias is None) and int(auto_font) == 1:
                picked_alias, size_hint = pick_pdf_font_for_hit(doc, page, h, alias_cache)
                font_alias = picked_alias
            if not font_alias:
                font_alias = fallback_alias

            # 2) TR safety: if Turkish chars and alias is weak, force fallback
            if needs_unicode(val):
                # if selected is weak and not forced, drop to fallback
                if selected_alias and not int(force_selected_font):
                    bad = selected_meta.get("subset_like", True) or (selected_meta.get("ext", "").lower() not in (".ttf", ".otf"))
                    if bad:
                        font_alias = fallback_alias
                # if auto-picked alias is builtin, also fallback
                if _alias_looks_builtin(font_alias):
                    font_alias = fallback_alias

            # Size mode
            if (size_mode or "auto").lower() == "fixed":
                min_use = max_use = float(fixed_fs)
            else:
                min_use = float(min_fs); max_use = float(max_fs)

            # Use original color if present; otherwise provided text_rgb
            use_color = h.get("font_color") if isinstance(h.get("font_color"), (tuple, list)) else text_rgb
            insert_transparent_text(page, r, val, font_alias, align=align,
                                    min_fs=min_use, max_fs=max_use, pad=float(pad),
                                    fit_mode=(fit_mode or "single").lower(),
                                    text_rgb=use_color, size_hint=size_hint, transparency=1.0)
            filled.add(key_norm)

        # Save
        tmpdir = tempfile.mkdtemp()
        out_path = os.path.join(tmpdir, "filled.pdf")
        doc.save(out_path, incremental=False, deflate=True)

        headers = {"X-Font-Fallback": str(font_path), "X-Embed-API": str(EMBED_OK)}
        if detect_hdr:
            headers["X-Detect"] = detect_hdr
        missing = [k for k in mapping.keys() if k not in filled]
        if missing:
            headers["X-Missing-Keys"] = ",".join(missing)
        return out_path, headers, missing
    finally:
        doc.close()


@app.post("/fill")
async def fill_pdf(
    template: UploadFile = File(...),
    fields_json: str = Form(...),
    align_json: str = Form(""),
    font_path: str = Form("fonts/DejaVuSans.ttf"),
    provider: str = Form("auto"),
    min_fs: float = Form(6.0),
    max_fs: float = Form(48.0),
    pad: float = Form(0.0),
    text_color: str = Form(""),
    fit_mode: str = Form("single"),
    size_mode: str = Form("auto"),
    fixed_fs: float = Form(14.0),
    auto_font: int = Form(1),
    selected_font_xref: int = Form(0),
    force_selected_font: int = Form(0),
    erase_mode: str = Form("redact"),  # redact | none
):
    if template.content_type != "application/pdf":
        raise HTTPException(400, "PDF dosyası yükleyin")
    data = await template.read(); validate_file_size(data)
    try:
        mapping_raw = json.loads(fields_json) if fields_json else {}
        mapping = normalize_mapping(mapping_raw)
        align_map_raw = json.loads(align_json) if align_json else {}
        align_map = {(k or "").strip().casefold(): int(v) for k, v in align_map_raw.items()}
        text_rgb = tuple(json.loads(text_color)) if text_color else (0, 0, 0)
    except Exception as e:
        raise HTTPException(400, f"JSON parse hatası: {e}")

    out_path, headers, _missing = process_fill_request(
        data, mapping, align_map, text_rgb, font_path, provider,
        min_fs, max_fs, pad, fit_mode, size_mode, fixed_fs,
        auto_font, selected_font_xref, force_selected_font, erase_mode,
    )
    return FileResponse(out_path, media_type="application/pdf", filename="doldurulmus.pdf", headers=headers)

# ===================== AI Detect (always 200) =====================
@app.post("/ai_detect")
async def ai_detect(template: UploadFile = File(...), provider: str = Form("auto")):
    if template.content_type != "application/pdf":
        raise HTTPException(400, "PDF dosyası yükleyin")
    data = await template.read(); validate_file_size(data)

    prov_req = (provider or "auto").lower()
    prov_used = None; warning = None; hits = []; pages = 0
    text_layer = has_text_layer(data); ocr_ok = ocr_is_available()

    if prov_req == "local":
        if text_layer:
            doc = fitz.open(stream=data, filetype="pdf")
            hits = collect_placeholders(doc); pages = doc.page_count; doc.close(); prov_used = "local"
        elif ocr_ok:
            hits = ai_detect_placeholders_ocr(data); pages = fitz.open(stream=data, filetype="pdf").page_count; prov_used = "ocr"; warning = "fallback_ocr"
        else:
            prov_used = "local"; warning = "no_text_layer_and_no_ocr"
    elif prov_req == "ocr":
        if ocr_ok:
            hits = ai_detect_placeholders_ocr(data); pages = fitz.open(stream=data, filetype="pdf").page_count; prov_used = "ocr"
        else:
            if text_layer:
                doc = fitz.open(stream=data, filetype="pdf")
                hits = collect_placeholders(doc); pages = doc.page_count; doc.close(); prov_used = "local"; warning = "tesseract_not_found_fallback_local"
            else:
                prov_used = "ocr"; warning = "no_text_layer_and_no_ocr"
    else:  # auto
        if text_layer:
            doc = fitz.open(stream=data, filetype="pdf")
            hits = collect_placeholders(doc); pages = doc.page_count; doc.close(); prov_used = "local"
            if not hits and ocr_ok:
                hits = ai_detect_placeholders_ocr(data); prov_used = "ocr"
        else:
            if ocr_ok:
                hits = ai_detect_placeholders_ocr(data); pages = fitz.open(stream=data, filetype="pdf").page_count; prov_used = "ocr"
            else:
                prov_used = "ocr"; warning = "no_text_layer_and_no_ocr"

    res = []
    for h in hits:
        r = h["rect"]
        res.append({"key": h["key"], "page": h["page"], "rect": [r.x0, r.y0, r.x1, r.y1], "font_name": h.get("font_name"), "font_size": h.get("font_size")})
    uniq = sorted({h["key"] for h in hits})

    out = {"provider_used": prov_used, "pages": pages, "placeholders": res, "unique_keys": uniq}
    if warning:
        out["warning"] = warning
    return JSONResponse(status_code=200, content=out)

# ============== Static web (optional) ==============
if os.path.isdir("public"):
    app.mount("/", StaticFiles(directory="public", html=True), name="public")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
