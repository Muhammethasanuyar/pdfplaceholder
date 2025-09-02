# perfect_system.py - PDF Placeholder Sistemi (TR-UNICODE OPTIMIZED)
import os
import json
import uuid
import unicodedata
import re
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import ssl
import urllib.request

import fitz  # PyMuPDF
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Perfect PDF Placeholder System")

# ============================ CORS ============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================ Sessions ============================
SESSIONS: Dict[str, Dict] = {}
SESSION_DIR = Path("perfect_sessions")
SESSION_DIR.mkdir(exist_ok=True)

# ============================ Font bootstrap (Unicode TR) ============================
FONTS_DIR = Path("fonts")
FONTS_DIR.mkdir(exist_ok=True)

TR_FONT_CANDIDATES: List[Tuple[str, List[str]]] = [
    (
        "DejaVuSans.ttf",
        [
            "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans.ttf",
            "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/version_2_37/ttf/DejaVuSans.ttf",
        ],
    ),
    (
        "NotoSans-Regular.ttf",
        [
            "https://github.com/notofonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf",
            "https://fonts.gstatic.com/s/notosans/v30/o-0IIpQlx3QUlC5A4PNr5TRASf6M7VBj.woff2",
        ],
    ),
    (
        "OpenSans-Regular.ttf",
        [
            "https://github.com/google/fonts/raw/main/apache/opensans/OpenSans-Regular.ttf",
            "https://fonts.gstatic.com/s/opensans/v40/memSYaGs126MiZpBA-UvWbX2vVnXBbObj2OVZyOOSr4dVJWUgsjZ0B4gaVQUwaEQbjB_mQ.ttf",
        ],
    ),
    (
        "Roboto-Regular.ttf",
        [
            "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Regular.ttf",
            "https://fonts.gstatic.com/s/roboto/v32/KFOmCnqEu92Fr1Mu4mxKKTU1Kg.woff2",
        ],
    ),
]


def _safe_download(url: str, dst: Path) -> bool:
    """Güvenli font indirme"""
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(url, timeout=20, context=ctx) as r, open(dst, "wb") as f:
            f.write(r.read())
        return True
    except Exception:
        return False


def ensure_tr_font() -> Path:
    """En az bir Unicode font ile tam Türkçe kapsamı sağla"""
    for fname, urls in TR_FONT_CANDIDATES:
        p = FONTS_DIR / fname
        if p.exists() and p.stat().st_size > 30_000:
            return p
        for u in urls:
            if _safe_download(u, p):
                return p
    
    # Son çare: fonts/ klasöründeki herhangi bir .ttf / .otf kullan
    for p in FONTS_DIR.glob("*.ttf"):
        if p.stat().st_size > 30_000:
            return p
    for p in FONTS_DIR.glob("*.otf"):
        if p.stat().st_size > 30_000:
            return p
    
    raise RuntimeError("Türkçe için uygun TTF/OTF font indirilemedi / bulunamadı.")


def register_tr_font(doc: fitz.Document) -> str:
    """Unicode destekli TTF fontu (DejaVu Sans) belgede embed et ve alias döndür.

    Öncelik: fonts/DejaVuSans.ttf
    Yedek: fonts/NotoSans-Regular.ttf, fonts/Roboto-Regular.ttf
    Son çare: helvetica (ASCII) yerine times-roman (daha iyi kapsam)
    """
    print("MANUAL font registration starting...")
    print(f"PyMuPDF version: {getattr(fitz, '__version__', 'unknown')}")

    # Start with preferred well-known fonts
    seen = set()
    candidates = [
        FONTS_DIR / "DejaVuSans.ttf",
        FONTS_DIR / "NotoSans-Regular.ttf",
        FONTS_DIR / "Roboto-Regular.ttf",
        FONTS_DIR / "OpenSans-Regular.ttf",
    ]
    # Then add any other .ttf/.otf in fonts directory (including subfolders)
    try:
        for fp in FONTS_DIR.glob("**/*"):
            if not fp.suffix.lower() in (".ttf", ".otf"):
                continue
            if fp in candidates:
                continue
            key = str(fp.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            candidates.append(fp)
    except Exception:
        pass

    for path in candidates:
        if not path.exists():
            continue
        try:
            # Modern API: Document.insert_font(fontname=alias, fontfile=path)
            alias = f"embedded_{path.stem.lower()}"
            if hasattr(doc, "insert_font"):
                try:
                    doc.insert_font(fontname=alias, fontfile=str(path))
                    print(f"Embedded TTF: {path.name} as '{alias}'")
                    # Hızlı bir ölçümle doğrula
                    _ = fitz.get_text_length("Çağatay", fontname=alias, fontsize=12)
                    return alias
                except Exception as e:
                    print(f"insert_font failed for {path.name}: {e}")
            # Eski API: add_font
            if hasattr(doc, "add_font"):
                try:
                    added_alias = doc.add_font(fontfile=str(path))
                    alias = added_alias or alias
                    print(f"Embedded via add_font: {path.name} as '{alias}'")
                    _ = fitz.get_text_length("Çağatay", fontname=alias, fontsize=12)
                    return alias
                except Exception as e2:
                    print(f"add_font failed for {path.name}: {e2}")
        except Exception as e:
            print(f"Error embedding {path}: {e}")

    print("No external TTF embedded. Falling back to built-in.")
    # Built-ins: 'times-roman' geniş kapsamlı; 'helvetica' ASCII ağırlıklı
    return "times-roman"


# ============================ Font helpers (match original) ============================
def _strip_subset(name: str) -> str:
    if not name:
        return ""
    if "+" in name and len(name.split("+", 1)[0]) in (5, 6, 7):
        return name.split("+", 1)[1]
    return name


def _build_page_font_index(doc: fitz.Document, pno: int) -> Dict[str, int]:
    """Sayfadaki font adlarını xref'lere eşle"""
    idx: Dict[str, int] = {}
    try:
        recs = doc.get_page_fonts(pno)
    except Exception:
        recs = getattr(doc[pno], "get_fonts", lambda: [])()
    for rec in (recs or []):
        xref = int(rec[0])
        name = str(rec[2]) if len(rec) > 2 else ""
        base = str(rec[3]) if len(rec) > 3 else ""
        for k in {name, base, _strip_subset(name), _strip_subset(base)}:
            if k:
                idx[k.lower()] = xref
    return idx


def _pick_pdf_font_alias(doc: fitz.Document, pno: int, original_font: str, cache: Dict[int, str]) -> Tuple[Optional[str], Dict[str, Any]]:
    """Placeholder'ın orijinal font adına göre PDF içindeki gömülü fontu alias olarak çıkar"""
    meta: Dict[str, Any] = {"ext": "", "bytes": 0, "subset_like": True}
    if not hasattr(doc, "insert_font"):
        return None, meta
    idx = _build_page_font_index(doc, pno)
    key = (original_font or "").strip().lower()
    if not key:
        return None, meta
    xref = None
    if key in idx:
        xref = idx[key]
    else:
        # subset temizlenmiş versiyonu dene
        s = _strip_subset(original_font).lower()
        xref = idx.get(s)
    if not xref:
        return None, meta
    if xref in cache:
        return cache[xref], meta
    try:
        ext, buf, _realname = doc.extract_font(xref)
        if not buf or len(buf) < 20_000 or (ext and ext.lower() not in (".ttf", ".otf")):
            return None, meta
        alias = doc.insert_font(fontbuffer=buf)
        cache[xref] = alias
        meta = {"ext": ext or "", "bytes": len(buf), "subset_like": len(buf) < 20_000}
        return alias, meta
    except Exception:
        return None, meta


def _norm_color(c: Any) -> Tuple[float, float, float]:
    """PyMuPDF span color'u (float/int/list) -> (r,g,b) 0..1"""
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
   

# ============================ Font style helpers (bold/italic) ============================
def _family_from_stem(stem: str) -> str:
    s = stem
    # Remove common weight/style tokens
    tokens = [
        "-Regular", "_Regular", " Regular",
        "-Bold", "_Bold", " Bold",
        "-Italic", "_Italic", " Italic",
        "-BoldItalic", "_BoldItalic", " BoldItalic",
        "-Bold-Italic", "_Bold-Italic", " Bold-Italic",
        "-Oblique", "_Oblique", " Oblique",
        "-SemiBold", "_SemiBold", " SemiBold",
        "-Medium", "_Medium", " Medium",
        "-Light", "_Light", " Light",
        "-Black", "_Black", " Black",
    ]
    for t in tokens:
        if t in s:
            s = s.replace(t, "")
    return s


def _candidate_variant_names(family: str, style: str) -> List[str]:
    family = family.strip()
    cands: List[str] = []
    if style == "bold":
        cands = [
            f"{family}-Bold", f"{family}_Bold", f"{family} Bold",
            f"{family}-SemiBold", f"{family}_SemiBold", f"{family} SemiBold",
            f"{family}-Medium", f"{family}_Medium", f"{family} Medium",
            # Some families: Bold without separator
            f"{family}Bold",
        ]
    elif style == "italic":
        cands = [
            f"{family}-Italic", f"{family}_Italic", f"{family} Italic",
            f"{family}-Oblique", f"{family}_Oblique", f"{family} Oblique",
            f"{family}Italic",
        ]
    elif style == "bold_italic":
        cands = [
            f"{family}-BoldItalic", f"{family}_BoldItalic", f"{family} BoldItalic",
            f"{family}-Bold-Italic", f"{family}_Bold-Italic", f"{family} Bold-Italic",
            f"{family}-SemiBoldItalic", f"{family}_SemiBoldItalic",
            f"{family}-MediumItalic", f"{family}_MediumItalic",
            f"{family}BoldItalic",
        ]
        # Also allow fallback sequence bold then italic if no direct match
        cands += _candidate_variant_names(family, "bold") + _candidate_variant_names(family, "italic")
    else:
        cands = [f"{family}"]
    return cands


def pick_variant_fontfile(preferred_fontfile: Optional[str], style: str, collect: Optional[List[str]] = None) -> Optional[str]:
    """Try to select a font file matching the requested style.
    - First try siblings near preferred fontfile using family-based candidates
    - Then search fonts directory for a suitable family variant
    - Finally, fallback to some known local bold/italic fonts
    Returns a path or None.
    """
    style = (style or "normal").lower()
    if style == "normal":
        return preferred_fontfile

    def exists(p: Optional[Path]) -> Optional[str]:
        try:
            if p and p.exists() and p.stat().st_size > 10_000:
                if collect is not None:
                    collect.append(str(p))
                return str(p)
        except Exception:
            return None
        return None

    # 1) Sibling variants near preferred font
    if preferred_fontfile:
        p = Path(preferred_fontfile)
        family = _family_from_stem(p.stem)
        for name in _candidate_variant_names(family, style):
            for ext in (".ttf", ".otf", ".TTF", ".OTF"):
                cand_path = p.parent / f"{name}{ext}"
                if collect is not None:
                    collect.append(str(cand_path))
                cand = exists(cand_path)
                if cand:
                    return cand

    # 2) Search fonts/ directory for family variants
    try:
        base_family = _family_from_stem(Path(preferred_fontfile).stem) if preferred_fontfile else None
    except Exception:
        base_family = None
    candidates = []
    for fp in FONTS_DIR.glob("**/*"):
        if not fp.suffix.lower() in (".ttf", ".otf"): 
            continue
        stem = fp.stem
        family = _family_from_stem(stem)
        if base_family and family and family.lower() != base_family.lower():
            continue
        # If family matches, check style tokens
        st = style
        s = stem.lower()
        if st == "bold" and ("bold" in s or "semibold" in s or "medium" in s):
            candidates.append(fp)
        elif st == "italic" and ("italic" in s or "oblique" in s):
            candidates.append(fp)
        elif st == "bold_italic" and (("bold" in s and ("italic" in s or "oblique" in s)) or "bolditalic" in s):
            candidates.append(fp)
    if candidates:
        # Prefer closest to base family name length
        candidates.sort(key=lambda x: len(x.stem))
        chosen = candidates[0]
        if collect is not None:
            collect.append(str(chosen))
        return str(chosen)

    # 3) Generic fallbacks
    generic_map = {
        "bold": [
            "OpenSans-SemiBold.ttf", "Gravity-Bold.otf", "Amble-Bold.ttf", "TTimesb.ttf"
        ],
        "italic": [
            "OpenSans-Italic.ttf", "NotoSans-Italic.ttf", "Roboto-Italic.ttf", "DejaVuSans-Oblique.ttf", "Times-Italic.ttf"
        ],
        "bold_italic": [
            "OpenSans-BoldItalic.ttf", "NotoSans-BoldItalic.ttf", "Roboto-BoldItalic.ttf", "DejaVuSans-BoldOblique.ttf", "Times-BoldItalic.ttf"
        ],
    }
    for fname in generic_map.get(style, []):
        if collect is not None:
            collect.append(str(FONTS_DIR / fname))
        cand = exists(FONTS_DIR / fname)
        if cand:
            return cand

    return preferred_fontfile


def builtin_fontname_for_style(style: str) -> str:
    s = (style or "normal").lower()
    if s == "bold":
        return "Helvetica-Bold"
    if s == "italic":
        return "Helvetica-Oblique"
    if s == "bold_italic":
        return "Helvetica-BoldOblique"
    return "Helvetica"


# ============================ Style inference helper ============================
def _infer_style_near_rect(page: fitz.Page, rect: fitz.Rect) -> Dict[str, Any]:
    """Rect etrafındaki span'lardan font, size ve color'ı tahmin eder.
    En çok kesişen span'ı seçer; yoksa en yakın dikey mesafeye göre alır."""
    best = None
    best_score = -1.0
    try:
        raw = page.get_text("rawdict")
        for block in raw.get("blocks", []):
            if block.get("type", 0) != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    x0, y0, x1, y1 = span.get("bbox", (0, 0, 0, 0))
                    sb = fitz.Rect(x0, y0, x1, y1)
                    inter = rect & sb
                    if inter.is_empty:
                        # Dikey yakınlık skoru (negatif mesafe)
                        dy = min(abs(rect.y0 - y1), abs(rect.y1 - y0))
                        score = -dy
                    else:
                        score = inter.get_area()
                    if score > best_score:
                        best_score = score
                        best = span
    except Exception:
        pass
    if best:
        try:
            return {
                "font": best.get("font", "helvetica"),
                "size": float(best.get("size", 12.0)),
                "color": _norm_color(best.get("color", (0, 0, 0)))
            }
        except Exception:
            return {"font": "helvetica", "size": 12.0, "color": (0.0, 0.0, 0.0)}
    return {"font": "helvetica", "size": 12.0, "color": (0.0, 0.0, 0.0)}

def _expand_rect_to_line(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    """Rect'i aynı satırdaki tüm span'ların yatay sınırlarına genişletir.
    Kesişen veya çok yakın yatay çizgideki span'ları toplayıp x0/x1'i genişletir."""
    try:
        raw = page.get_text("rawdict")
        y0, y1 = rect.y0, rect.y1
        best_y_mid = (y0 + y1) / 2.0
        best = []
        for block in raw.get("blocks", []):
            if block.get("type", 0) != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                # Satırın dikey aralığı
                ly0 = min(s.get("bbox", [0,0,0,0])[1] for s in spans)
                ly1 = max(s.get("bbox", [0,0,0,0])[3] for s in spans)
                # Aynı satır mı? (dikey olarak yakın)
                if not (ly1 >= y0 - 1 and ly0 <= y1 + 1):
                    continue
                # Satırın orta noktasına yakınlık
                lmid = (ly0 + ly1) / 2.0
                # Daha yakın satırı seç
                if not best or abs(lmid - best_y_mid) < abs(((min(s.get("bbox", [0,0,0,0])[1] for s in best) + max(s.get("bbox", [0,0,0,0])[3] for s in best)) / 2.0) - best_y_mid):
                    best = spans
        if best:
            x0 = min(s.get("bbox", [rect.x0, rect.y0, rect.x1, rect.y1])[0] for s in best)
            x1 = max(s.get("bbox", [rect.x0, rect.y0, rect.x1, rect.y1])[2] for s in best)
            return fitz.Rect(min(x0, rect.x0), rect.y0, max(x1, rect.x1), rect.y1)
    except Exception:
        pass
    return rect


def _expand_rect_to_line(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    """Verilen küçük rect'i, ait olduğu satırın tüm genişliğine genişletmeye çalışır.
    Eğer satır bulunamazsa, güvenli bir minimum genişlik ile yatayda genişletir."""
    try:
        raw = page.get_text("rawdict")
        best_line_bbox = None
        best_area = 0.0
        for block in raw.get("blocks", []):
            if block.get("type", 0) != 0:
                continue
            for line in block.get("lines", []):
                # Satır bbox'unu topla
                lb = [float('inf'), float('inf'), float('-inf'), float('-inf')]
                spans = line.get("spans", [])
                if not spans:
                    continue
                for sp in spans:
                    x0, y0, x1, y1 = sp.get("bbox", (0, 0, 0, 0))
                    lb[0] = min(lb[0], x0)
                    lb[1] = min(lb[1], y0)
                    lb[2] = max(lb[2], x1)
                    lb[3] = max(lb[3], y1)
                line_rect = fitz.Rect(lb)
                inter = line_rect & rect
                area = inter.get_area()
                if area > best_area:
                    best_area = area
                    best_line_bbox = line_rect
        if best_line_bbox and best_area > 0:
            # Biraz padding ekle
            pad = 2.0
            return fitz.Rect(
                best_line_bbox.x0 - pad,
                best_line_bbox.y0 - pad,
                best_line_bbox.x1 + pad,
                best_line_bbox.y1 + pad,
            )
    except Exception:
        pass
    # Bulunamazsa, yatayda güvenli şekilde genişlet
    page_rect = page.rect
    min_w = 140.0  # ~2 inch
    w = rect.width
    if w < min_w:
        extra = (min_w - w) / 2.0
        new_x0 = max(page_rect.x0 + 5, rect.x0 - extra)
        new_x1 = min(page_rect.x1 - 5, rect.x1 + extra)
        return fitz.Rect(new_x0, rect.y0, new_x1, rect.y1)
    return rect


# ============================ Font Analysis System ============================
def analyze_pdf_fonts(doc: fitz.Document) -> Dict[str, Any]:
    """PDF'deki tüm fontları analiz eder ve detaylarını döndürür"""
    font_analysis = {
        "all_fonts": [],
        "by_page": {},
        "embedded_fonts": [],
        "system_fonts": [],
        "recommendations": {}
    }
    
    print("PDF FONT ANALYSIS STARTING...")
    
    for pno in range(len(doc)):
        page = doc[pno]
        page_fonts = []
        
        try:
            # Sayfa fontlarını al
            font_list = doc.get_page_fonts(pno)
            for font_info in font_list:
                xref = int(font_info[0])
                fontname = str(font_info[1])
                fonttype = str(font_info[2])
                basename = str(font_info[3]) if len(font_info) > 3 else ""
                
                # Font detaylarını analiz et
                font_detail = {
                    "xref": xref,
                    "name": fontname,
                    "type": fonttype,
                    "basename": basename,
                    "page": pno + 1,
                    "is_embedded": False,
                    "extractable": False,
                    "file_path": None
                }
                
                # Embedded font kontrolü
                try:
                    ext, buf, realname = doc.extract_font(xref)
                    if buf and len(buf) > 1024:
                        font_detail["is_embedded"] = True
                        font_detail["extractable"] = True
                        font_detail["size_bytes"] = len(buf)
                        font_detail["extension"] = ext or "unknown"
                        font_detail["real_name"] = realname or fontname
                        
                        # TTF/OTF ise kaydet
                        if ext and ext.lower() in (".ttf", ".otf"):
                            temp_path = FONTS_DIR / f"extracted_{pno}_{xref}{ext}"
                            temp_path.write_bytes(buf)
                            font_detail["file_path"] = str(temp_path)
                            font_analysis["embedded_fonts"].append(font_detail)
                        
                except Exception:
                    pass
                
                if not font_detail["is_embedded"]:
                    font_analysis["system_fonts"].append(font_detail)
                
                page_fonts.append(font_detail)
                
                print(f"Page {pno+1}: {fontname} ({fonttype}) - Embedded: {font_detail['is_embedded']}")
        
        except Exception as e:
            print(f"Page {pno+1} font analysis error: {e}")
        
        font_analysis["by_page"][pno + 1] = page_fonts
        font_analysis["all_fonts"].extend(page_fonts)
    
    # Font önerileri oluştur
    if font_analysis["embedded_fonts"]:
        # En yaygın embedded font
        embedded_names = [f["basename"] or f["name"] for f in font_analysis["embedded_fonts"]]
        most_common = max(set(embedded_names), key=embedded_names.count) if embedded_names else None
        
        font_analysis["recommendations"]["primary_embedded"] = most_common
        font_analysis["recommendations"]["use_embedded"] = True
    else:
        font_analysis["recommendations"]["use_embedded"] = False
    
    # Sistem fontları için öneri
    if font_analysis["system_fonts"]:
        system_names = [f["basename"] or f["name"] for f in font_analysis["system_fonts"]]
        most_common_system = max(set(system_names), key=system_names.count) if system_names else None
        font_analysis["recommendations"]["primary_system"] = most_common_system
    
    print(f"FONT ANALYSIS COMPLETE: {len(font_analysis['all_fonts'])} fonts found")
    print(f"   Embedded: {len(font_analysis['embedded_fonts'])}")
    print(f"   System: {len(font_analysis['system_fonts'])}")
    
    return font_analysis

def get_font_config_for_placeholder(font_analysis: Dict[str, Any], placeholder: Dict[str, Any]) -> Dict[str, Any]:
    """Placeholder için en uygun font konfigürasyonunu döndürür"""
    config = {
        "fontfile": None,
        "fontname": "helvetica",
        "source": "fallback"
    }
    
    original_font = placeholder.get("original_font", "").lower()
    page_num = placeholder.get("page", 0) + 1
    
    # 1. Öncelik: Aynı sayfadaki embedded fontlar
    page_fonts = font_analysis["by_page"].get(page_num, [])
    for font in page_fonts:
        if font["is_embedded"] and font["file_path"]:
            basename_lower = (font["basename"] or "").lower()
            name_lower = (font["name"] or "").lower()
            
            if original_font in basename_lower or original_font in name_lower:
                config = {
                    "fontfile": font["file_path"],
                    "fontname": "embedded",
                    "source": f"extracted_page_{page_num}",
                    "original_name": font["basename"] or font["name"]
                }
                print(f"Found matching embedded font for '{original_font}': {config['original_name']}")
                return config
    
    # 2. Öncelik: Tüm embedded fontlardan en uygun
    for font in font_analysis["embedded_fonts"]:
        if font["file_path"]:
            basename_lower = (font["basename"] or "").lower()
            name_lower = (font["name"] or "").lower()
            
            if original_font in basename_lower or original_font in name_lower:
                config = {
                    "fontfile": font["file_path"],
                    "fontname": "embedded",
                    "source": "extracted_global",
                    "original_name": font["basename"] or font["name"]
                }
                print(f"Found matching embedded font globally: {config['original_name']}")
                return config
    
    # 3. En yaygın embedded font kullan
    if font_analysis["embedded_fonts"]:
        primary_font = font_analysis["embedded_fonts"][0]  # İlk embedded font
        if primary_font["file_path"]:
            config = {
                "fontfile": primary_font["file_path"],
                "fontname": "embedded",
                "source": "primary_embedded",
                "original_name": primary_font["basename"] or primary_font["name"]
            }
            print(f"Using primary embedded font: {config['original_name']}")
            return config
    
    # 4. Fallback: Yerel TTF/OTF (prefer DejaVuSans if present)
    preferred = [FONTS_DIR / "DejaVuSans.ttf", FONTS_DIR / "NotoSans-Regular.ttf"]
    for p in preferred:
        if p.exists():
            config = {
                "fontfile": str(p),
                "fontname": "embedded",
                "source": "local_ttf",
                "original_name": p.stem
            }
            print(f"Using local TTF fallback: {config['original_name']}")
            return config
    try:
        for fp in FONTS_DIR.glob("**/*"):
            if fp.suffix.lower() not in (".ttf", ".otf"):
                continue
            if fp.exists():
                config = {
                    "fontfile": str(fp),
                    "fontname": "embedded",
                    "source": "local_ttf",
                    "original_name": fp.stem
                }
                print(f"Using local font fallback: {config['original_name']}")
                return config
    except Exception:
        pass
    
    print(f"No suitable font found, using system default")
    return config

# ============================ Models ============================
class FillRequest(BaseModel):
    session_id: str
    values: Dict[str, str]
    font_choice: Optional[str] = None  # Seçilen font yolu
    text_color: Optional[List[float]] = None  # RGB renk değerleri (0-1 arasında)
    font_size_mode: Optional[str] = "auto"  # "auto", "fixed", "min_max"
    fixed_font_size: Optional[float] = None  # Sabit font boyutu
    min_font_size: Optional[float] = None   # Minimum font boyutu
    max_font_size: Optional[float] = None   # Maksimum font boyutu
    allow_overflow: Optional[bool] = False  # Metinin alandan taşmasına izin ver
    text_alignments: Optional[Dict[str, str]] = {}  # Placeholder bazında hizalama {"key": "left|center|right|offset:X"}
    alignment_offsets: Optional[Dict[str, float]] = {}  # Manuel offset değerleri {"key": -20.5} (negatif=sola, pozitif=sağa)
    alignment_offsets_y: Optional[Dict[str, float]] = {}  # Dikey offset değerleri {"key": 2.0} (pozitif=aşağı, negatif=yukarı)
    per_placeholder_font_sizes: Optional[Dict[str, float]] = {}  # Placeholder bazında font boyutu {"key": 14.0}
    font_style: Optional[str] = "normal"  # "normal", "bold", "italic", "bold_italic"
    per_placeholder_styles: Optional[Dict[str, str]] = {}  # Placeholder bazında stil {"key": "bold"}


# ============================ Utilities ============================
# Gelişmiş Placeholder Pattern'leri
PH_PATTERNS = [
    # Standart: {{Ad}}
    re.compile(r'\{\{\s*([^}]+?)\s*\}\}'),
    
    # Boşluklu: { {Ad} }
    re.compile(r'\{\s*\{\s*([^}]+?)\s*\}\s*\}'),
    
    # Tek kırlangıç: {Ad}
    re.compile(r'\{\s*([^}]+?)\s*\}'),
    
    # Köşeli parantez: [[Ad]]
    re.compile(r'\[\[\s*([^\]]+?)\s*\]\]'),
    
    # Boşluklu köşeli: [ [Ad] ]
    re.compile(r'\[\s*\[\s*([^\]]+?)\s*\]\s*\]'),
    
    # Tek köşeli: [Ad]
    re.compile(r'\[\s*([^\]]+?)\s*\]'),
    
    # Yuvarlak parantez: ((Ad))
    re.compile(r'\(\(\s*([^)]+?)\s*\)\)'),
    
    # Boşluklu yuvarlak: ( (Ad) )
    re.compile(r'\(\s*\(\s*([^)]+?)\s*\)\s*\)'),
    
    # Üçlü kırlangıç: {{{Ad}}}
    re.compile(r'\{\{\{\s*([^}]+?)\s*\}\}\}'),
    
    # Karışık: {[Ad]}
    re.compile(r'\{\[\s*([^\]]+?)\s*\]\}'),
    
    # Ters karışık: [{Ad}]
    re.compile(r'\[\{\s*([^}]+?)\s*\}\]'),
    
    # Dolar işareti: ${Ad}
    re.compile(r'\$\{\s*([^}]+?)\s*\}'),
    
    # Yüzde işareti: %{Ad}%
    re.compile(r'%\{\s*([^}]+?)\s*\}%'),
    
    # At işareti: @{Ad}
    re.compile(r'@\{\s*([^}]+?)\s*\}'),
    
    # Hash işareti: #{Ad}
    re.compile(r'#\{\s*([^}]+?)\s*\}'),
]

# Ana pattern (geriye uyumluluk için)
PH_RE = PH_PATTERNS[0]

# Türkçe karakter tespiti
TR_CHARS = set("çğıöşüÇĞİÖŞÜ")

# Basit font dosya önbelleği: xref -> path
_EMBED_CACHE: Dict[int, str] = {}

def _extract_placeholder_fontfile(doc: fitz.Document, pno: int, original_font: str) -> Optional[str]:
    """PDF sayfasındaki orijinal fontu diske .ttf/.otf olarak çıkar ve yolunu döndür.
    Doc.insert_font olmadığından, insert_textbox(fontfile=...) ile kullanacağız.
    """
    try:
        idx = _build_page_font_index(doc, pno)
        key = (original_font or "").strip().lower()
        if not key:
            return None
        xref = idx.get(key)
        if not xref:
            xref = idx.get(_strip_subset(original_font).lower())
        if not xref:
            return None
        if xref in _EMBED_CACHE and Path(_EMBED_CACHE[xref]).exists():
            return _EMBED_CACHE[xref]
        try:
            ext, buf, _realname = doc.extract_font(xref)
        except Exception:
            return None
        if not buf or len(buf) < 1024:
            return None
        ext = (ext or "").lower()
        if ext not in (".ttf", ".otf"):
            # Yine de dene: uzantı bilinmiyorsa TTF yaz
            ext = ".ttf"
        out_dir = FONTS_DIR / "_embedded"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"font_{pno}_{xref}{ext}"
        try:
            out_path.write_bytes(buf)
        except Exception:
            return None
        _EMBED_CACHE[xref] = str(out_path)
        return str(out_path)
    except Exception:
        return None

def _autosize_font_to_rect(text: str, rect: fitz.Rect, fontfile: str, start: float = 12.0) -> float:
    """Verilen fontfile ile metnin, dikdörtgene sığacağı en büyük font boyutunu bul.
    Geçici bir dokümanda insert_textbox ile ölçer (leftover==0 => sığdı).
    """
    try:
        low, high = 4.0, max(start * 2.0, rect.height * 2.0)
        # Hızlı büyütme: start uygunsa low=start yap
        tmp = fitz.open()
        p = tmp.new_page(width=rect.width, height=rect.height)
        box = fitz.Rect(0, 0, rect.width, rect.height)
        left = p.insert_textbox(box, text, fontname="embedded", fontfile=fontfile, fontsize=start, align=fitz.TEXT_ALIGN_CENTER)
        tmp.close()
        if left == 0:
            low = start
        # İkili arama ile en iyi değeri bul
        for _ in range(12):
            mid = (low + high) / 2.0
            tmp = fitz.open()
            p = tmp.new_page(width=rect.width, height=rect.height)
            box = fitz.Rect(0, 0, rect.width, rect.height)
            left = p.insert_textbox(box, text, fontname="embedded", fontfile=fontfile, fontsize=mid, align=fitz.TEXT_ALIGN_CENTER)
            tmp.close()
            if left == 0:
                low = mid
            else:
                high = mid
        return max(4.0, round(low, 2))
    except Exception:
        return max(6.0, start)

def _fit_singleline_font_to_rect(text: str, rect: fitz.Rect, fontfile: str, start: float = 12.0) -> float:
    """Tek satırda kalacak şekilde (boşlukları NBSP yaparak) kutuya sığan maksimum fontu bulur.
    Genişlik sınırı ana kısıttır; yükseklik için ayrıca clamp yapılmalıdır."""
    try:
        t = (text or "").replace(" ", "\u00A0")
        low, high = 4.0, max(start * 2.5, rect.height * 3.0)
        # Başlangıç kontrolü
        tmp = fitz.open()
        p = tmp.new_page(width=rect.width, height=max(10.0, rect.height * 6.0))
        box = fitz.Rect(0, 0, rect.width, p.rect.height)
        left = p.insert_textbox(box, t, fontname="embedded", fontfile=fontfile, fontsize=start, align=fitz.TEXT_ALIGN_CENTER)
        tmp.close()
        if left == 0:
            low = start
        for _ in range(14):
            mid = (low + high) / 2.0
            tmp = fitz.open()
            p = tmp.new_page(width=rect.width, height=max(10.0, rect.height * 6.0))
            box = fitz.Rect(0, 0, rect.width, p.rect.height)
            left = p.insert_textbox(box, t, fontname="embedded", fontfile=fontfile, fontsize=mid, align=fitz.TEXT_ALIGN_CENTER)
            tmp.close()
            if left == 0:
                low = mid
            else:
                high = mid
        return max(4.0, round(low, 2))
    except Exception:
        return max(6.0, start)

def needs_unicode(s: str) -> bool:
    try:
        return bool(s) and any((ord(ch) > 127) or (ch in TR_CHARS) for ch in s)
    except Exception:
        return True


def normalize_turkish_text(text: Any) -> str:
    """GELİŞTİRİLMİŞ Türkçe metin normalleştirme - Türkçe karakterler garantili"""
    if text is None:
        return ""
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            return ""

    # 1. Önce encoding sorunlarını düzelt
    try:
        # Eğer metin latin-1 olarak kodlanmışsa UTF-8'e çevir
        if any(c in text for c in ['Ã§', 'Ã', 'Å']):
            try:
                # Latin-1 decode, UTF-8 encode dene
                text = text.encode('latin-1').decode('utf-8')
            except:
                pass
    except:
        pass

    # 2. Yaygın mojibake düzeltmeleri - GELİŞTİRİLMİŞ
    turkish_fixes = {
        # Mojibake onarımları
        "ÄŸ": "ğ", "Ã„ÂŸ": "ğ", "Ã¤Å¸": "ğ", "Ä°Å¸": "ğ", "Ä±Å¸": "ğ",
        "Ä±": "ı", "Ã„Â±": "ı", "Ã±": "ı", "Ä°Â±": "ı", "Ä°": "İ",
        "ÅŸ": "ş", "Ã…Å¸": "ş", "Ã…Åž": "Ş", "Ã…Â": "ş", "Å": "Ş",
        "Ã§": "ç", "Ã‡": "Ç", "Ãƒ§": "ç", "Ãƒ‡": "Ç",
        "Ã¼": "ü", "Ãœ": "Ü", "Ãƒ¼": "ü", "Ãƒœ": "Ü",
        "Ã¶": "ö", "Ã–": "Ö", "Ãƒ¶": "ö", "Ãƒ–": "Ö",
        "Äž": "Ğ", "Ã„Å¾": "Ğ", "ÄˆÄ°": "İ",
        
        # UTF-8 problemleri
        "Ä±Ã": "ı", "ÄÃ": "ğ", "ÅÃ": "ş", "Ã¼Ã": "ü", "Ã§Ã": "ç", "Ã¶Ã": "ö",
        "Ã„Â±": "ı", "Ã…Å¸": "ş", "Ã„ÂŸ": "ğ",
        
        # Windows-1254 -> UTF-8 problemleri
        "Ã‡": "Ç", "Ã–": "Ö", "Ãœ": "Ü", "Ä°": "İ", "Ä±": "ı", "ÅŸ": "ş"
    }
    
    # Her türlü encoding sorunu için çoklu geçiş
    for _ in range(3):  # Maksimum 3 geçiş
        old_text = text
        for wrong, correct in turkish_fixes.items():
            text = text.replace(wrong, correct)
        if text == old_text:  # Değişiklik yoksa dur
            break

    # 3. NFC normalize (aksanları birleştir)
    try:
        text = unicodedata.normalize("NFC", text)
    except Exception:
        pass

    # 4. Karakter temizleme ve doğrulama
    cleaned_text = ""
    for char in text:
        char_code = ord(char)
        if char_code < 128:  # ASCII karakterler - güvenli
            cleaned_text += char
        elif char in "çğıöşüÇĞİÖŞÜâîûêôûıİĞğŞşÇçÖöÜü":  # Türkçe + diğer unicode
            cleaned_text += char
        elif 128 <= char_code <= 65535:  # Geçerli Unicode aralığı
            cleaned_text += char
        else:
            # Tanınmayan karakter için ASCII yakınını bul
            ascii_map = {
                'ğ': 'g', 'ş': 's', 'ü': 'u', 'ç': 'c', 'ı': 'i', 'ö': 'o',
                'Ğ': 'G', 'Ş': 'S', 'Ü': 'U', 'Ç': 'C', 'İ': 'I', 'Ö': 'O'
            }
            cleaned_text += ascii_map.get(char, char)

    # 5. Son kontrol ve düzenleme
    if cleaned_text != text:
        print(f"🔧 Text düzeltildi: '{text[:50]}...' -> '{cleaned_text[:50]}...'")
    
    print(f"🇹🇷 PERFECT Turkish normalized: '{cleaned_text}'")
    return cleaned_text


def _dedupe_placeholders(ph_list: List[Dict]) -> List[Dict]:
    """Aynı sayfa & aynı konumdaki tekrarları tekilleştir (üst üste yazmayı engeller)"""
    seen = set()
    out = []
    for ph in ph_list:
        page = ph.get("page", -1)
        r = ph.get("rect", [0, 0, 0, 0])
        sig = (page, round(r[0], 2), round(r[1], 2), round(r[2], 2), round(r[3], 2))
        if sig in seen:
            continue
        seen.add(sig)
        out.append(ph)
    return out


# ============================ Placeholder Detection ============================
def _get_font_info_at_position(page: fitz.Page, rect: fitz.Rect) -> Tuple[str, float, int, tuple]:
    """Belirli pozisyondaki font bilgilerini al"""
    try:
        # Rect içindeki span'ları bul
        raw = page.get_text("rawdict")
        for block in raw.get("blocks", []):
            if block.get("type", 0) != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    span_rect = fitz.Rect(span["bbox"])
                    # Overlap kontrolü
                    if span_rect.intersects(rect):
                        font_name = span.get("font", "helvetica")
                        font_size = span.get("size", 12)
                        font_flags = span.get("flags", 0)
                        font_color = _norm_color(span.get("color", (0, 0, 0)))
                        return font_name, font_size, font_flags, font_color
    except Exception as e:
        print(f"⚠️ Font info extraction error: {e}")
    
    # Default values
    return "helvetica", 12, 0, (0, 0, 0)


def detect_placeholders_position_based(doc: fitz.Document) -> List[Dict]:
    """POSITION-BASED PLACEHOLDER DETECTION - Her pozisyon için unique key"""
    print("🎯 POSITION-BASED PLACEHOLDER DETECTION")
    
    # Patterns with priority (most specific first to avoid duplicates)
    patterns = [
        (r'\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}', "{{Ad}}"),  # Highest priority - most specific
        (r'\[\[([A-Za-z_][A-Za-z0-9_]*)\]\]', "[[Ad]]"),
        (r'%([A-Za-z_][A-Za-z0-9_]*)%', "%Ad%"),
        (r'@([A-Za-z_][A-Za-z0-9_]*)@', "@Ad@"),
        (r'#([A-Za-z_][A-Za-z0-9_]*)#', "#Ad#"),
        # Skip single bracket patterns that might conflict with double brackets
        # (r'\{([A-Za-z_][A-Za-z0-9_]*)\}', "{Ad}"),    # Commented out to avoid conflicts
        # (r'\[([A-Za-z_][A-Za-z0-9_]*)\]', "[Ad]"),    # Commented out to avoid conflicts  
    ]
    
    placeholders = []
    occupied_areas = []  # Track covered areas
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        print(f"📄 Page {page_num + 1}")
        
        for pattern_re, pattern_name in patterns:
            page_text = page.get_text()
            matches = re.finditer(pattern_re, page_text)
            
            for match in matches:
                base_key = match.group(1).strip()
                full_match = match.group(0)
                
                # Skip invalid keys
                if not base_key or len(base_key) < 2:
                    continue
                if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', base_key):
                    continue
                
                # Find all visual instances
                instances = page.search_for(full_match)
                
                for rect in instances:
                    # Check if this area overlaps with already processed areas
                    is_overlapping = False
                    for occupied_rect in occupied_areas:
                        if (abs(rect.x0 - occupied_rect.x0) < 5 and 
                            abs(rect.y0 - occupied_rect.y0) < 5):
                            is_overlapping = True
                            print(f"   ⏭️ Skipping '{full_match}' at ({rect.x0:.1f}, {rect.y0:.1f}) - overlaps with previous")
                            break
                    
                    if is_overlapping:
                        continue
                        
                    # Mark this area as occupied
                    occupied_areas.append(rect)
                    
                    # Get context for better identification
                    try:
                        expanded = fitz.Rect(rect.x0-40, rect.y0-8, rect.x1+40, rect.y1+8)
                        context = page.get_textbox(expanded).strip()
                        context = context.replace('\n', ' ').replace('\r', ' ')
                    except:
                        context = ""
                    
                    # Get font info
                    try:
                        font_name, font_size, font_flags, font_color = _get_font_info_at_position(page, rect)
                        font_info = {
                            "fontname": font_name,
                            "size": font_size,
                            "flags": font_flags,
                            "color": font_color
                        }
                    except Exception as e:
                        print(f"⚠️ Font info extraction error: {e}")
                        font_info = {"fontname": "Unknown", "size": 12.0, "flags": 0, "color": (0, 0, 0)}
                    
                    placeholder = {
                        'base_key': base_key,
                        'text': full_match,
                        'pattern': pattern_name,
                        'page': page_num,
                        'rect': [rect.x0, rect.y0, rect.x1, rect.y1],
                        'context': context,
                        'original_font': font_info.get("fontname", "Unknown"),
                        'original_size': font_info.get("size", 12.0),
                        'original_flags': font_info.get("flags", 0),
                        'original_color': font_info.get("color", (0, 0, 0))
                    }
                    
                    placeholders.append(placeholder)
                    print(f"   ✅ Found '{full_match}' at ({rect.x0:.1f}, {rect.y0:.1f})")
    
    # Group by base_key and assign position indexes
    key_groups = {}
    for ph in placeholders:
        base_key = ph['base_key']
        if base_key not in key_groups:
            key_groups[base_key] = []
        key_groups[base_key].append(ph)
    
    # Assign unique keys
    final_placeholders = []
    for base_key, group in key_groups.items():
        # Sort by Y position (top to bottom), then X (left to right)
        group.sort(key=lambda p: (p['rect'][1], p['rect'][0]))
        
        for i, ph in enumerate(group):
            if len(group) == 1:
                # Single instance - keep original key
                unique_key = base_key
                display_name = base_key
                position_label = ""
            else:
                # Multiple instances - add position index
                unique_key = f"{base_key}_{i+1}"
                context_preview = ph['context'][:25] + '...' if len(ph['context']) > 25 else ph['context']
                display_name = f"{base_key} #{i+1}"
                position_label = f" ({context_preview})" if context_preview else f" (Pos {i+1})"
            
            ph['key'] = unique_key  # This is the key used for filling
            ph['display_name'] = display_name + position_label
            ph['position_index'] = i + 1 if len(group) > 1 else None
            ph['total_positions'] = len(group) if len(group) > 1 else None
            
            final_placeholders.append(ph)
            
            print(f"   🎯 Assigned: '{unique_key}' -> '{display_name + position_label}'")
    
    print(f"🎯 Detection complete: {len(final_placeholders)} positioned placeholders")
    return final_placeholders
    """🎯 OPTIMIZED PLACEHOLDER DETECTION - Zero Duplicates, Maximum Coverage"""
    placeholders: List[Dict] = []
    found_positions = set()  # Pozisyon bazında duplicate kontrolü
    
    print("� OPTIMIZED placeholder detection starting...")
    print(f"🎯 Patterns to scan: {len(PH_PATTERNS)}")
    
    # Pattern isimleri
    PATTERN_NAMES = [
        "{{Ad}}", "{ {Ad} }", "{Ad}", "[[Ad]]", "[ [Ad] ]", "[Ad]", 
        "((Ad))", "( (Ad) )", "{{{Ad}}}", "{[Ad]}", "[{Ad}]", 
        "${Ad}", "%{Ad}%", "@{Ad}", "#{Ad}"
    ]
    
    for pno in range(len(doc)):
        page = doc[pno]
        print(f"📄 Scanning page {pno + 1}...")
        
        # SMART SINGLE-PASS DETECTION
        try:
            # 1) Tüm text'i al
            page_text = page.get_text()
            print(f"📝 Page text length: {len(page_text)} characters")
            
            # 2) Her pattern için bir kere tara
            for pattern_idx, pattern in enumerate(PH_PATTERNS):
                pattern_name = PATTERN_NAMES[pattern_idx]
                
                for match in pattern.finditer(page_text):
                    key = match.group(1).strip()
                    full_match = match.group(0)
                    start_pos = match.start()
                    end_pos = match.end()
                    
                    # FALSE POSITIVE FILTERING - Güvenli pattern kontrolü
                    is_false_positive = False
                    reasons = []
                    
                    # 1) Geçersiz karakterler (bracket'lar key içinde)
                    if any(c in key for c in '{}[]()'):
                        is_false_positive = True
                        reasons.append(f"Invalid chars in key: '{key}'")
                    
                    # 2) Kısa büyük harf/sayı kombinasyonları
                    elif key.isalnum() and (key.isupper() or key.isdigit()) and len(key) <= 4:
                        is_false_positive = True
                        reasons.append(f"Short uppercase/digit: '{key}'")
                    
                    # 3) Yaygın kelimeler
                    elif key.upper() in {'NEW', 'OLD', 'YES', 'NO', 'TOP', 'END', 'ALL', 'ANY', 'HOW', 'WHO', 'WHAT'}:
                        is_false_positive = True
                        reasons.append(f"Common word: '{key}'")
                    
                    # 4) Tek karakter
                    elif len(key) == 1:
                        is_false_positive = True
                        reasons.append(f"Single char: '{key}'")
                    
                    # 5) Sadece sayı
                    elif key.isdigit():
                        is_false_positive = True
                        reasons.append(f"Number only: '{key}'")
                    
                    if is_false_positive:
                        print(f"⏭️ SKIP false positive: '{full_match}' → key: '{key}' | {', '.join(reasons)}")
                        continue
                    
                    # Smart duplicate kontrolü - sadece TAM aynı match'leri skip et
                    match_signature = f"{pno}_{start_pos}_{end_pos}_{full_match}_{pattern_name}"
                    if match_signature in found_positions:
                        print(f"⏭️ SKIP exact duplicate: '{full_match}' at position {start_pos}-{end_pos}")
                        continue
                    
                    found_positions.add(match_signature)
                    
                    # Exact bbox bulma
                    text_instances = page.search_for(full_match)
                    if text_instances:
                        # Multiple instances olabilir - hepsini kontrol et
                        for bbox_idx, bbox in enumerate(text_instances):
                            # Unique signature for each bbox
                            bbox_signature = f"{pno}_{bbox.x0:.1f}_{bbox.y0:.1f}_{bbox.x1:.1f}_{bbox.y1:.1f}_{full_match}"
                            
                            # Bu position'da bu text zaten processed mi?
                            if bbox_signature in found_positions:
                                print(f"⏭️ SKIP processed bbox: '{full_match}' at ({bbox.x0:.1f}, {bbox.y0:.1f})")
                                continue
                            
                            found_positions.add(bbox_signature)
                            
                            # Span-level font info'yu almaya çalış
                            font_name, font_size, font_flags, font_color = _get_font_info_at_position(
                                page, bbox
                            )
                            
                            placeholder = {
                                "key": key,
                                "text": full_match,
                                "pattern": pattern_name,
                                "page": pno,
                                "rect": [bbox.x0, bbox.y0, bbox.x1, bbox.y1],
                                "original_font": font_name,
                                "original_size": font_size,
                                "original_flags": font_flags,
                                "original_color": font_color,
                                "suggestion": f"Örnek_{key}"
                            }
                            
                            placeholders.append(placeholder)
                            print(f"✅ FOUND: '{full_match}' → key: '{key}' (pattern: {pattern_name}) at ({bbox.x0:.1f}, {bbox.y0:.1f})")
                    
                    else:
                        # Fallback: Text bulundu ama bbox yok
                        print(f"⚠️ Pattern found but no bbox: '{full_match}' → key: '{key}'")
        
        except Exception as e:
            print(f"⚠️ Detection error on page {pno + 1}: {e}")
    
    # INTELLIGENT deduplication: Aynı key'in multiple instances'larını destekle
    final_placeholders = []
    processed_positions = set()
    
    for ph in placeholders:
        key = ph['key']
        page = ph['page']
        rect = ph['rect']
        
        # Sadece temiz key'leri kabul et (garip karakterler değil)
        if not key or key.startswith('{') or key.startswith('[') or key.startswith('(') or key.endswith('}') or key.endswith(']') or key.endswith(')'):
            print(f"⏭️ SKIP invalid key: '{key}' (contains brackets)")
            continue
        
        # Position-based duplicate kontrolü (aynı yerde tekrar etmesin)
        position_key = f"{page}_{rect[0]:.1f}_{rect[1]:.1f}_{rect[2]:.1f}_{rect[3]:.1f}"
        if position_key in processed_positions:
            print(f"⏭️ SKIP duplicate position: '{key}' at ({rect[0]:.1f}, {rect[1]:.1f})")
            continue
        
        processed_positions.add(position_key)
        
        # Unique ID ekle (aynı key'in farklı instance'ları için)
        ph['instance_id'] = f"{key}_page{page}_pos{rect[0]:.0f}x{rect[1]:.0f}"
        
        final_placeholders.append(ph)
        print(f"✅ ACCEPTED: '{key}' at page {page+1}, position ({rect[0]:.1f}, {rect[1]:.1f})")
    
    placeholders = final_placeholders
    
    print(f"🎯 OPTIMIZED detection complete: {len(placeholders)} unique placeholders")
    print("📋 FINAL RESULTS:")
    for ph in sorted(placeholders, key=lambda x: (x['page'], x['key'])):
        rect = ph['rect']
        print(f"   📍 Page {ph['page'] + 1}: '{ph['key']}' = '{ph['text']}' (pattern: {ph['pattern']}) at ({rect[0]:.1f}, {rect[1]:.1f})")
    
    return placeholders


# ============================ Removal (Redaction) ============================
def physically_remove_placeholders(doc: fitz.Document, placeholders: List[Dict]) -> fitz.Document:
    """🎯 SAFE PLACEHOLDER REMOVAL - Skips placeholders that might damage other content"""
    if not placeholders:
        print("📄 No placeholders to remove")
        return doc

    print(f"🧹 SAFE REMOVAL: {len(placeholders)} placeholders")
    
    # First, identify potentially problematic areas (like "NEW" text)
    problematic_areas = []
    for pno in range(len(doc)):
        page = doc[pno]
        # Look for large, standalone text that shouldn't be damaged
        text_dict = page.get_text("dict")
        for block in text_dict["blocks"]:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        bbox = span["bbox"]
                        font_size = span["size"]
                        
                        # Identify large, standalone text (like "NEW")
                        if (len(text) <= 5 and text.isupper() and font_size > 30 and 
                            not any(c in text for c in '{}[]()@#$%')):
                            problematic_areas.append({
                                'page': pno,
                                'text': text,
                                'rect': bbox,
                                'font_size': font_size
                            })
                            print(f"� IDENTIFIED PROBLEMATIC AREA: '{text}' @ page {pno+1}, size {font_size:.1f}")
    
    safe_removals = 0
    skipped_removals = 0
    
    for ph in placeholders:
        page_num = ph["page"]
        placeholder_text = ph["text"]
        full_rect = ph.get("rect", [0, 0, 0, 0])
        page = doc[page_num]
        
        print(f"\n🎯 Processing '{placeholder_text}' from page {page_num + 1}")
        
        # Check for overlap with problematic areas
        should_skip = False
        for prob_area in problematic_areas:
            if prob_area['page'] == page_num:
                prob_rect = prob_area['rect']
                # Check for overlap
                if (full_rect[0] < prob_rect[2] and full_rect[2] > prob_rect[0] and 
                    full_rect[1] < prob_rect[3] and full_rect[3] > prob_rect[1]):
                    print(f"   ⚠️ OVERLAP DETECTED with '{prob_area['text']}' - SKIPPING for safety")
                    should_skip = True
                    skipped_removals += 1
                    break
        
        if should_skip:
            continue
        
        try:
            # SAFE APPROACH: Use direct search for exact placeholder text
            placeholder_instances = page.search_for(placeholder_text)
            
            if placeholder_instances:
                # Find the closest match to our detected position
                detected_center_x = (full_rect[0] + full_rect[2]) / 2
                detected_center_y = (full_rect[1] + full_rect[3]) / 2
                
                best_match = None
                min_distance = float('inf')
                
                for instance_rect in placeholder_instances:
                    instance_center_x = (instance_rect.x0 + instance_rect.x1) / 2
                    instance_center_y = (instance_rect.y0 + instance_rect.y1) / 2
                    
                    distance = ((detected_center_x - instance_center_x) ** 2 + 
                               (detected_center_y - instance_center_y) ** 2) ** 0.5
                    
                    if distance < min_distance:
                        min_distance = distance
                        best_match = instance_rect
                
                if best_match:
                    # Double-check: This exact match won't overlap with problematic areas
                    safe_to_remove = True
                    for prob_area in problematic_areas:
                        if prob_area['page'] == page_num:
                            prob_rect = prob_area['rect']
                            if (best_match.x0 < prob_rect[2] and best_match.x1 > prob_rect[0] and 
                                best_match.y0 < prob_rect[3] and best_match.y1 > prob_rect[1]):
                                print(f"   ⚠️ EXACT MATCH would overlap with '{prob_area['text']}' - SKIPPING")
                                safe_to_remove = False
                                skipped_removals += 1
                                break
                    
                    if safe_to_remove:
                        # Safe to remove - create minimal redaction
                        safe_rect = fitz.Rect(
                            best_match.x0 - 0.5, 
                            best_match.y0 - 0.5, 
                            best_match.x1 + 0.5, 
                            best_match.y1 + 0.5
                        )
                        
                        page.add_redact_annot(safe_rect)
                        print(f"   ✅ SAFE REMOVAL: ({safe_rect.x0:.1f}, {safe_rect.y0:.1f}) - ({safe_rect.x1:.1f}, {safe_rect.y1:.1f})")
                        print(f"   📏 Redaction area: {safe_rect.width:.1f} x {safe_rect.height:.1f}")
                        safe_removals += 1
                else:
                    print(f"   ❌ No suitable match found for '{placeholder_text}'")
            else:
                print(f"   ⚠️ No instances found for '{placeholder_text}'")
        
        except Exception as e:
            print(f"   ❌ Error processing '{placeholder_text}': {e}")
    
    # Apply all redactions
    for pno in range(len(doc)):
        page = doc[pno]
        page.apply_redactions(images=False)

    print(f"\n💎 SAFE REMOVAL COMPLETED:")
    print(f"   ✅ Safe removals: {safe_removals}")
    print(f"   ⚠️ Skipped for safety: {skipped_removals}")
    print(f"   🛡️ Content preservation prioritized")
    
    return doc
    
    # Apply all redactions at once per page
    for pno in range(len(doc)):
        page = doc[pno]
        page.apply_redactions(images=False)

    print("� PRECISE REMOVAL COMPLETED - Only exact placeholder texts removed")
    return doc

# Yeni fonksiyon
def embed_font_safe(doc):
    try:
        # PyMuPDF 1.23+ için
        if hasattr(doc, 'insert_font'):
            # Önce fonts/ içindeki güvenli fontu dene
            for p in [FONTS_DIR / "DejaVuSans.ttf", FONTS_DIR / "NotoSans-Regular.ttf", FONTS_DIR / "FreeSans.ttf"]:
                if p.exists():
                    try:
                        return doc.insert_font(fontfile=str(p))
                    except Exception:
                        pass
            return doc.insert_font(fontfile="DejaVuSans.ttf")
        # Eski versiyonlar için
        elif hasattr(doc, 'add_font'):
            return doc.add_font(fontfile="DejaVuSans.ttf")
    except Exception as e:
        print(f"❌ Kritik font hatası: {e}")
        return None

def insert_natural_text_advanced(doc: fitz.Document, placeholders: List[Dict], values: Dict[str, str]) -> fitz.Document:
    """Unicode TTF ile tek sefer çizim, placeholder boyutuna tam sığdırma.

    - insert_textbox(fontfile=...) kullanır
    - Center hizalama
    - Otomatik boyutlandırma: placeholder dikdörtgenine maksimum sığan font
    - Renk: placeholder'ın orijinal rengi
    - Font: mümkünse PDF'in gömülü fontu, değilse fonts/ içindeki TTF
    """
    print(f"✨ PERFECT TURKISH TEXT INSERTION: {len(values)} values")

    def _get_turkish_fontfile() -> Optional[str]:
        # Tüm mevcut fontları öncelik sırasıyla kontrol et
        font_priorities = [
            "DejaVuSans.ttf",           # Ana font
            "NotoSans-Regular.ttf",     # Google font
            "OpenSans-Regular.ttf",     # Popüler web font
            "OpenSans-SemiBold.ttf",    # Semi-bold variant
            "Roboto-Regular.ttf",       # Material design
            "Ubuntu-Regular.ttf",       # Ubuntu font
            "PTSans-Regular.ttf",       # PT Sans
            "BebasNeue-Regular.ttf",    # Modern display
            "Anton-Regular.ttf",        # Display font
            "Gravity-Regular.otf",      # Gravity regular
            "Gravity-Bold.otf",         # Gravity bold  
            "Amble-Regular.ttf",        # Amble regular
            "Amble-Bold.ttf",           # Amble bold
            "CaviarDreams.ttf",         # Caviar Dreams
            "LemonMilklight.otf",       # Lemon Milk
            "Akrobat-Regular.otf",      # Akrobat
            "TTimesb.ttf"               # Times variant
        ]
        
        for font_name in font_priorities:
            font_path = FONTS_DIR / font_name
            if font_path.exists():
                return str(font_path)
        return None

    default_ttf = _get_turkish_fontfile()
    if default_ttf:
        print(f"🇹🇷 Default TTF: {default_ttf}")
    else:
        print("⚠️ No default TTF found in fonts/.")

    for ph in placeholders:
        key = ph.get("key", "")
        if key not in values:
            continue

        raw_val = values.get(key, "")
        text = normalize_turkish_text(raw_val)
        if not text:
            continue

        page = doc[ph.get("page", 0)]
        rect = fitz.Rect(*ph.get("rect", [0, 0, 0, 0]))
        # Eğer detection küçük bir brace alanından geldiyse, satır genişliğine genişlet
        try:
            rect = _expand_rect_to_line(page, rect)
        except Exception:
            pass

        # Stil: boyut, renk, font
        orig_fs = float(ph.get("original_size", 12.0))
        fs = orig_fs
        color = tuple(ph.get("original_color", (0, 0, 0)))
        original_font = ph.get("original_font", "")

        # Öncelik: PDF'in gömülü fontunu çıkarmak
        fontfile_path = _extract_placeholder_fontfile(doc, ph.get("page", 0), original_font) or default_ttf
        if fontfile_path:
            print(f"🖨️ Font for '{key}': {fontfile_path} (orig: {original_font})")

        # GÜVENLI PLACEHOLDER BOYUTU (görünürlük garantili)
        # Placeholder yüksekliğinin %60'ı = font size (güvenli doldurma için)
        # Maksimum 24pt ile sınırlandır (çok büyük olmasın)
        base_fs = rect.height * 0.60
        fs = round(min(base_fs, 24.0), 1)
        # Minimum 8pt garantisi
        fs = max(fs, 8.0)
        print(f"🎯 SAFE PLACEHOLDER SIZE for '{key}': rect.height={rect.height:.1f} -> font_size={fs:.1f}pt (base={base_fs:.1f})")

        try:
            if fontfile_path:
                # Tam olarak placeholder boyutunda çiz
                _ = page.insert_textbox(
                    rect,
                    text,
                    fontname="embedded",
                    fontfile=fontfile_path,
                    fontsize=fs,
                    align=fitz.TEXT_ALIGN_CENTER,
                    color=color
                )
                print(f"✅ Placed '{key}' at {fs:.1f}pt within {rect} (TTF, SAFE SIZE)")
            else:
                # ASCII fallback (Unicode font yoksa)
                ascii_map = {'ç':'c','ğ':'g','ı':'i','ö':'o','ş':'s','ü':'u','Ç':'C','Ğ':'G','İ':'I','Ö':'O','Ş':'S','Ü':'U'}
                safe_text = ''.join(ascii_map.get(ch, ch) for ch in text)
                _ = page.insert_textbox(
                    rect,
                    safe_text,
                    fontname="helv",
                    fontsize=fs,
                    align=fitz.TEXT_ALIGN_CENTER,
                    color=color
                )
                print(f"✅ Placed '{key}' at {fs:.1f}pt within {rect} (ASCII, SAFE SIZE)")
        except Exception as e:
            print(f"❌ FAILED to place '{key}': {e}")
            # Yedek yerleştirme - daha küçük font ile dene
            try:
                backup_fs = min(12.0, fs * 0.5)
                if fontfile_path:
                    _ = page.insert_textbox(
                        rect,
                        text,
                        fontname="embedded",
                        fontfile=fontfile_path,
                        fontsize=backup_fs,
                        align=fitz.TEXT_ALIGN_CENTER,
                        color=color
                    )
                else:
                    safe_text = ''.join(ascii_map.get(ch, ch) for ch in text)
                    _ = page.insert_textbox(
                        rect,
                        safe_text,
                        fontname="helv",
                        fontsize=backup_fs,
                        align=fitz.TEXT_ALIGN_CENTER,
                        color=color
                    )
                print(f"⚠️ BACKUP placement '{key}' at {backup_fs:.1f}pt")
            except Exception as e2:
                print(f"❌ BACKUP ALSO FAILED for '{key}': {e2}")

    print("✨ PERFECT TURKISH TEXT INSERTION COMPLETED")
    return doc


def test_font_unicode_support(font_path: str, test_text: str = "Çağrı Türkçe ğüşıöç") -> bool:
    """Font'un Türkçe karakterleri destekleyip desteklemediğini test eder"""
    try:
        # Test document oluştur
        test_doc = fitz.open()
        test_page = test_doc.new_page()
        test_rect = fitz.Rect(0, 0, 200, 50)
        
        result = test_page.insert_textbox(
            test_rect,
            test_text,
            fontname="embedded",
            fontfile=font_path,
            fontsize=12
        )
        
        test_doc.close()
        return result > 0
    except Exception as e:
        print(f"⚠️ Font unicode test failed for {Path(font_path).name}: {e}")
        return False


def insert_natural_text_with_analysis(doc: fitz.Document, placeholders: List[Dict], values: Dict[str, str], font_analysis: Dict[str, Any], font_choice: Optional[str] = None, text_color: Optional[List[float]] = None, font_size_mode: str = "auto", fixed_font_size: Optional[float] = None, min_font_size: Optional[float] = None, max_font_size: Optional[float] = None, allow_overflow: bool = False, text_alignments: Dict[str, str] = {}, alignment_offsets: Dict[str, float] = {}, per_placeholder_font_sizes: Dict[str, float] = {}, alignment_offsets_y: Dict[str, float] = {}, font_style: str = "normal", per_placeholder_styles: Dict[str, str] = {}) -> Tuple[fitz.Document, List[Dict[str, Any]]]:
    """Font analizi ile gelişmiş metin yerleştirme sistemi"""
    print(f"✨ PERFECT TURKISH TEXT INSERTION WITH FONT ANALYSIS: {len(values)} values")

    def _get_turkish_fontfile() -> Optional[str]:
        # Tüm mevcut fontları öncelik sırasıyla kontrol et
        font_priorities = [
            "DejaVuSans.ttf",           # Ana font
            "NotoSans-Regular.ttf",     # Google font
            "OpenSans-Regular.ttf",     # Popüler web font
            "OpenSans-SemiBold.ttf",    # Semi-bold variant
            "Roboto-Regular.ttf",       # Material design
            "Ubuntu-Regular.ttf",       # Ubuntu font
            "PTSans-Regular.ttf",       # PT Sans
            "BebasNeue-Regular.ttf",    # Modern display
            "Anton-Regular.ttf",        # Display font
            "Gravity-Regular.otf",      # Gravity regular
            "Gravity-Bold.otf",         # Gravity bold  
            "Amble-Regular.ttf",        # Amble regular
            "Amble-Bold.ttf",           # Amble bold
            "CaviarDreams.ttf",         # Caviar Dreams
            "LemonMilklight.otf",       # Lemon Milk
            "Akrobat-Regular.otf",      # Akrobat
            "TTimesb.ttf"               # Times variant
        ]
        
        for font_name in font_priorities:
            font_path = FONTS_DIR / font_name
            if font_path.exists():
                return str(font_path)
        return None

    default_ttf = _get_turkish_fontfile()
    if default_ttf:
        print(f"🇹🇷 Default TTF: {default_ttf}")
    else:
        print("⚠️ No default TTF found in fonts/.")
    
    # Kullanıcı font seçimi varsa kullan
    if font_choice:
        print(f"👤 User selected font: {font_choice}")
        if Path(font_choice).exists():
            default_ttf = font_choice
        else:
            print(f"⚠️ Selected font not found: {font_choice}, using default")

    # VALUES MAPPING
    # Frontend'den gelebilecek indexed key'leri (sitead_1, sitead_2, ...) base_key'e (sitead) indirgeriz
    # Böylece aynı isimli farklı koordinatlardaki placeholder'lar için aynı değer kullanılır.
    base_key_values = {}
    
    print(f"🚀 BAŞLATILAN VALUES MAPPING:")
    for k, v in values.items():
        print(f"   📊 '{k}' -> '{v}'")
        
        # Base key'i çıkar (sitead_1 -> sitead)
        base_key = k.split('_')[0] if '_' in k else k
        if v and v.strip():  # Boş değer değilse
            base_key_values[base_key] = v
    
    print(f"🔄 BASE KEY VALUES MAPPING:")
    for k, v in base_key_values.items():
        print(f"   🎯 '{k}' -> '{v}'")

    diagnostics: List[Dict[str, Any]] = []

    for ph in placeholders:
        key = ph.get("key", "")
        base_key = key.split('_')[0] if '_' in key else key
        if base_key not in base_key_values:
            print(f"❌ NO VALUE found for base key '{base_key}' (key: '{key}')")
            continue

        raw_val = base_key_values[base_key]
        text = normalize_turkish_text(raw_val)
        if not text:
            continue

        print(f"🎯 PROCESSING: '{key}' (base: '{base_key}') -> '{text[:30]}...'")

        page = doc[ph.get("page", 0)]
        rect = fitz.Rect(*ph.get("rect", [0, 0, 0, 0]))

        # Overflow yoksa satır genişliğine genişlet
        if not allow_overflow:
            try:
                rect = _expand_rect_to_line(page, rect)
            except Exception:
                pass
        else:
            try:
                page_rect = page.rect
                expanded_width = rect.width * 1.5
                expanded_height = rect.height * 1.3
                cx = (rect.x0 + rect.x1) / 2
                cy = (rect.y0 + rect.y1) / 2
                rect = fitz.Rect(
                    max(0, cx - expanded_width / 2),
                    max(0, cy - expanded_height / 2),
                    min(page_rect.width, cx + expanded_width / 2),
                    min(page_rect.height, cy + expanded_height / 2),
                )
                print(f"📏 OVERFLOW MODE for '{key}': Expanded rect to {rect}")
            except Exception:
                pass

        # Renk
        if text_color and len(text_color) >= 3:
            color = tuple(text_color[:3])
        else:
            color = tuple(ph.get("original_color", (0, 0, 0)))

        # Hizalama ve offset
        user_alignment = text_alignments.get(key, "center")
        manual_offset = alignment_offsets.get(key, 0.0)
        if manual_offset != 0:
            alignment = fitz.TEXT_ALIGN_LEFT
        elif user_alignment == "left":
            alignment = fitz.TEXT_ALIGN_LEFT
        elif user_alignment == "right":
            alignment = fitz.TEXT_ALIGN_RIGHT
        else:
            alignment = fitz.TEXT_ALIGN_CENTER

        # Font seçimi: kullanıcı > analiz > default
        fontfile_path = None
        if font_choice and Path(font_choice).exists():
            fontfile_path = font_choice
        else:
            try:
                font_config = get_font_config_for_placeholder(font_analysis, ph)
                fontfile_path = font_config.get("fontfile") or default_ttf
            except Exception:
                fontfile_path = default_ttf

        # Stil seçimi: per-placeholder > global > normal
        style_for_this = (per_placeholder_styles.get(key) or per_placeholder_styles.get(base_key) or font_style or "normal").lower()
        # Font variantını bulmayı dene
        tried: List[str] = []
        styled_fontfile_path = pick_variant_fontfile(fontfile_path, style_for_this, collect=tried)

        # Font boyutu hesapla (tek ölçüm, tek çizim)
        base_fs = round(min(rect.height * 0.60, 24.0), 1)
        fs = max(8.0, base_fs)
        # Per-placeholder override first
        override_size = None
        if per_placeholder_font_sizes:
            override_size = per_placeholder_font_sizes.get(key)
            if override_size is None:
                override_size = per_placeholder_font_sizes.get(base_key)
        skip_measure = False
        if override_size is not None:
            try:
                fs = max(6.0, min(float(override_size), 72.0))
                skip_measure = True
            except Exception:
                pass
        # Global modes
        if font_size_mode == "fixed" and fixed_font_size and override_size is None:
            fs = float(fixed_font_size)
        elif font_size_mode == "min_max" and min_font_size and max_font_size and override_size is None:
            fs = max(float(min_font_size), min(fs, float(max_font_size)))

        measure_fontfile = styled_fontfile_path or fontfile_path
        if measure_fontfile and not skip_measure:
            try:
                measured = _fit_singleline_font_to_rect(text, rect, measure_fontfile, start=fs)
                if font_size_mode == "min_max" and min_font_size and max_font_size:
                    measured = max(float(min_font_size), min(measured, float(max_font_size)))
                fs = measured
            except Exception:
                pass

        # Rect'i hizalamaya göre kaydır (Y ekseninde otomatik orta ve manuel offset)
        offset_x = manual_offset if manual_offset != 0 else 0
        manual_offset_y = 0.0
        try:
            manual_offset_y = float(alignment_offsets_y.get(key, 0.0))
        except Exception:
            manual_offset_y = 0.0

        # Otomatik dikey merkezleme: tek satır için kabaca fs*0.85 yüksekliğini baz al
        auto_center_shift = 0.0
        try:
            auto_center_shift = (rect.height - (fs * 0.85)) / 2.0
            # Aşırı kaymaları engelle (±12px ile sınırla)
            if auto_center_shift > 12:
                auto_center_shift = 12
            elif auto_center_shift < -12:
                auto_center_shift = -12
        except Exception:
            auto_center_shift = 0.0

        total_y_shift = auto_center_shift + manual_offset_y

        if user_alignment == "left":
            adjusted_rect = fitz.Rect(rect.x0 + offset_x, rect.y0 + total_y_shift, rect.x1, rect.y1 + total_y_shift)
        elif user_alignment == "right":
            adjusted_rect = fitz.Rect(rect.x0 + offset_x, rect.y0 + total_y_shift, rect.x1 + offset_x, rect.y1 + total_y_shift)
        else:
            adjusted_rect = fitz.Rect(rect.x0 + offset_x, rect.y0 + total_y_shift, rect.x1 + offset_x, rect.y1 + total_y_shift)

        # TEK SEFER ÇİZİM
        try:
            if styled_fontfile_path:
                _ = page.insert_textbox(
                    adjusted_rect,
                    text,
                    fontname="embedded",
                    fontfile=styled_fontfile_path,
                    fontsize=fs,
                    align=alignment,
                    color=color,
                )
            else:
                # Built-in styles fallback
                builtin = builtin_fontname_for_style(style_for_this)
                ascii_map = {'ç':'c','ğ':'g','ı':'i','ö':'o','ş':'s','ü':'u','Ç':'C','Ğ':'G','İ':'I','Ö':'O','Ş':'S','Ü':'U'}
                safe_text = ''.join(ascii_map.get(ch, ch) for ch in text)
                _ = page.insert_textbox(
                    adjusted_rect,
                    safe_text,
                    fontname=builtin,
                    fontsize=fs,
                    align=alignment,
                    color=color,
                )
            print(f"✅ Placed '{key}' once at {fs:.1f}pt within {adjusted_rect}")
            diagnostics.append({
                "key": key,
                "base_key": base_key,
                "style": style_for_this,
                "font_used": styled_fontfile_path or builtin_fontname_for_style(style_for_this),
                "candidates_tried": tried,
                "fs": fs,
            })
        except Exception as e:
            print(f"❌ SINGLE DRAW FAILED for '{key}': {e}")
            # Minimal tek-seferlik ASCII fallback denemesi
            try:
                ascii_map = {'ç':'c','ğ':'g','ı':'i','ö':'o','ş':'s','ü':'u','Ç':'C','Ğ':'G','İ':'I','Ö':'O','Ş':'S','Ü':'U'}
                safe_text = ''.join(ascii_map.get(ch, ch) for ch in text)
                fallback_fs = max(8.0, min(fs, rect.height * 0.5))
                builtin = builtin_fontname_for_style(style_for_this)
                _ = page.insert_textbox(
                    adjusted_rect,
                    safe_text,
                    fontname=builtin,
                    fontsize=fallback_fs,
                    align=alignment,
                    color=color,
                )
                print(f"✅ Fallback placed '{key}' once at {fallback_fs:.1f}pt within {adjusted_rect}")
                diagnostics.append({
                    "key": key,
                    "base_key": base_key,
                    "style": style_for_this,
                    "font_used": builtin_fontname_for_style(style_for_this),
                    "candidates_tried": tried,
                    "fs": fallback_fs,
                })
            except Exception as e2:
                print(f"❌ Fallback also failed for '{key}': {e2}")

    print("✨ PERFECT TURKISH TEXT INSERTION WITH FONT ANALYSIS COMPLETED")
    return doc, diagnostics


# ============================ Insertion (Unicode, single-pass) ============================
def insert_natural_text(doc: fitz.Document, placeholders: List[Dict], values: Dict[str, str]) -> fitz.Document:
    """Ana wrapper fonksiyon - gelişmiş sistemi çağırır"""
    return insert_natural_text_advanced(doc, placeholders, values)
    print(f"✨ LEGACY-COMPATIBLE TURKISH TEXT INSERTION: {len(values)} values")

    # PyMuPDF version info
    pymupdf_version = getattr(fitz, '__version__', '0.0.0')
    print(f"📝 PyMuPDF version: {pymupdf_version}")
    
    # Font sistemi
    has_modern_fonts = hasattr(doc, 'insert_font')
    print(f"🔧 Modern font support: {has_modern_fonts}")
    
    if has_modern_fonts:
        alias_tr = register_tr_font(doc)
    else:
        alias_tr = "helvetica"  # Legacy için default
    
    print(f"🇹🇷 Using font: {alias_tr}")
    alias_cache: Dict[int, str] = {}

    for ph in placeholders:
        key = ph.get("key", "")
        if key not in values:
            continue
        raw_val = values.get(key, "")
        text = normalize_turkish_text(raw_val)
        if not text:
            continue

        page = doc[ph.get("page", 0)]
        rect = fitz.Rect(*ph.get("rect", [0, 0, 0, 0]))

        # Font bilgilerini al
        original_font = ph.get("original_font", "helvetica")
        original_size = ph.get("original_size", 12)
        original_flags = ph.get("original_flags", 0)
        original_color = _norm_color(ph.get("original_color", (0, 0, 0)))

        print(f"✨ LEGACY-COMPATIBLE INSERTION:")
        print(f"   📝 Text: '{text}'")
        print(f"   🎨 Font: {alias_tr} (original: {original_font})")
        print(f"   📏 Size: {original_size:.1f}pt")
        print(f"   📍 Position: ({rect.x0:.1f}, {rect.y1:.1f})")

        # Font boyutu
        fs = float(original_size)
        padding = 2.0
        inner = fitz.Rect(
            rect.x0 + padding, 
            rect.y0 + padding, 
            rect.x1 - padding, 
            rect.y1 - padding
        )

        success = False
        text_needs_unicode = needs_unicode(text)

        # LEGACY PyMuPDF için özel yaklaşım
        if not has_modern_fonts:
            print("🔧 LEGACY PyMuPDF Mode - Special Turkish handling")
            
            # Method 1: Direct insert_text için Türkçe karakterleri ASCII'ye çevir
            if text_needs_unicode:
                print("🇹🇷 Converting Turkish chars to ASCII for legacy support")
                # Türkçe karakterleri ASCII karşılıklarına çevir
                turkish_to_ascii = {
                    'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u',
                    'Ç': 'C', 'Ğ': 'G', 'İ': 'I', 'Ö': 'O', 'Ş': 'S', 'Ü': 'U'
                }
                ascii_text = ''.join(turkish_to_ascii.get(char, char) for char in text)
                print(f"   🔄 '{text}' -> '{ascii_text}' (ASCII conversion)")
                working_text = ascii_text
            else:
                working_text = text

            # Method A: insert_text ile basit yerleştirme
            try:
                print(f"� Method A: Legacy insert_text")
                base_y = rect.y0 + (rect.height * 0.7)  # Y pozisyonu ayarlama
                
                page.insert_text(
                    (rect.x0 + 5, base_y),  # Biraz padding ekle
                    working_text,
                    fontname="helvetica",
                    fontsize=fs,
                    color=original_color
                )
                success = True
                print(f"✅ Method A SUCCESS: insert_text with helvetica")
                
            except Exception as e:
                print(f"⚠️ Method A failed: {e}")

            # Method B: insert_textbox deneme (legacy'de varsa) - GELİŞTİRİLMİŞ
            if not success:
                attempt_count = 0
                max_attempts = 3
                current_fs = fs
                
                while not success and attempt_count < max_attempts:
                    attempt_count += 1
                    try:
                        print(f"📝 Method B (Attempt {attempt_count}): Legacy insert_textbox at {current_fs:.1f}pt")
                        result = page.insert_textbox(
                            inner,
                            working_text,
                            fontname="helvetica",
                            fontsize=current_fs,
                            align=fitz.TEXT_ALIGN_LEFT,
                            color=original_color
                        )
                        
                        if result in (0, None, ""):  # Başarılı yerleştirme
                            success = True
                            print(f"✅ Method B SUCCESS: insert_textbox at {current_fs:.1f}pt")
                        else:
                            print(f"⚠️ Method B overflow: leftover='{result}', reducing font size")
                            if allow_overflow:
                                print(f"🚧 OVERFLOW ALLOWED in legacy mode")
                                success = True
                            else:
                                # Font boyutunu küçült
                                current_fs = max(6.0, current_fs * 0.75)
                                print(f"📉 Reducing to {current_fs:.1f}pt for next attempt")
                                
                                if current_fs <= 6.0:
                                    print(f"⚠️ Minimum font reached in legacy mode, accepting")
                                    success = True
                            
                    except Exception as e:
                        print(f"⚠️ Method B attempt {attempt_count} failed: {e}")
                        current_fs = max(6.0, current_fs * 0.8)

            # Method C: Karakter bazında yerleştirme (legacy)
            if not success:
                try:
                    print(f"📝 Method C: Character-by-character (legacy)")
                    char_spacing = fs * 0.6
                    current_x = rect.x0 + 5
                    base_y = rect.y0 + (rect.height * 0.7)

                    for i, char in enumerate(working_text):
                        if current_x > rect.x1 - 10:  # Sınır kontrolü
                            break
                        try:
                            page.insert_text(
                                (current_x, base_y),
                                char,
                                fontname="helvetica",
                                fontsize=fs,
                                color=original_color
                            )
                            current_x += char_spacing
                        except Exception as char_error:
                            print(f"⚠️ Character '{char}' failed, skipping")
                            current_x += char_spacing
                            continue

                    success = True
                    print(f"✅ Method C SUCCESS: Character-by-character")

                except Exception as e:
                    print(f"❌ Method C failed: {e}")

            # Method D: Son çare - Türkçe karaktersiz metinle sadece
            if not success and text_needs_unicode:
                try:
                    print(f"📝 Method D: Ultra-safe ASCII only")
                    # Türkçe karakterleri tamamen çıkar
                    safe_text = ''.join(c for c in working_text if ord(c) < 128)
                    if safe_text:
                        page.insert_text(
                            (rect.x0 + 5, rect.y0 + (rect.height * 0.7)),
                            safe_text,
                            fontname="helvetica",
                            fontsize=fs,
                            color=original_color
                        )
                        success = True
                        print(f"✅ Method D SUCCESS: ASCII-only '{safe_text}'")
                        
                except Exception as e:
                    print(f"❌ Method D failed: {e}")

        # MODERN PyMuPDF desteği (font embedding ile)
        else:
            print("🚀 MODERN PyMuPDF Mode - Full Unicode support")
            
            # Modern method - önceki kodun aynısı
            if text_needs_unicode:
                try:
                    print(f"🇹🇷 Method MODERN: Unicode font {alias_tr}")
                    
                    # Modern textbox insertion
                    result = page.insert_textbox(
                        inner,
                        text,
                        fontname=alias_tr,
                        fontsize=fs,
                        align=fitz.TEXT_ALIGN_LEFT,
                        color=original_color
                    )
                    
                    if not result:  # No leftover text
                        success = True
                        print(f"✅ Method MODERN SUCCESS")
                    else:
                        # Try with smaller font
                        smaller_fs = fs * 0.8
                        result2 = page.insert_textbox(
                            inner,
                            text,
                            fontname=alias_tr,
                            fontsize=smaller_fs,
                            align=fitz.TEXT_ALIGN_LEFT,
                            color=original_color
                        )
                        if not result2:
                            success = True
                            print(f"✅ Method MODERN SUCCESS: smaller font")
                        
                except Exception as e:
                    print(f"⚠️ Method MODERN failed: {e}")

        # Başarı durumu raporu
        if success:
            print(f"✅ TEXT INSERTED: '{key}' = '{text}' (legacy compatible)")
        else:
            print(f"❌ ALL METHODS FAILED for '{key}' = '{text}'")
            
            # Son çare
            try:
                safe_text = text[:10] if len(text) <= 20 else f"{text[:10]}..."
                page.insert_text(
                    (rect.x0, rect.y0 + rect.height/2),
                    safe_text,
                    fontname="helvetica",
                    fontsize=max(8, fs * 0.7),
                    color=original_color
                )
                print("⚠️ Emergency fallback insertion completed")
            except Exception as final_error:
                print(f"❌ EMERGENCY FALLBACK FAILED: {final_error}")

    print("✨ LEGACY-COMPATIBLE TURKISH TEXT INSERTION COMPLETED")
    return doc


# ============================ API ============================
class AnalyzeResponse(BaseModel):
    success: bool
    message: str
    session_id: str
    placeholders: List[Dict]


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_pdf_perfect(file: UploadFile = File(...)):
    """PDF analiz sistemi"""
    try:
        session_id = str(uuid.uuid4())
        
        # Save original file
        file_content = await file.read()
        original_path = SESSION_DIR / f"{session_id}_original.pdf"
        
        with open(original_path, "wb") as f:
            f.write(file_content)
        
        print(f"📁 PERFECT ANALYSIS: {file.filename}")
        
        # Open PDF for analysis
        doc = fitz.open(str(original_path))
        
        # Perfect placeholder detection
        placeholders = detect_placeholders_position_based(doc)
        
        if not placeholders:
            doc.close()
            return AnalyzeResponse(
                success=False,
                message="Bu PDF'de {{}} (süslü parantez) formatında placeholder bulunamadı.",
                session_id=session_id,
                placeholders=[]
            )
        
        # FONT ANALYSIS SYSTEM
        print("🚀 FONT ANALYSIS PHASE")
        font_analysis = analyze_pdf_fonts(doc)
        
        # PHASE 1: Physical removal of placeholders
        print("🚀 PHASE 1: PHYSICAL PLACEHOLDER REMOVAL")
        doc = physically_remove_placeholders(doc, placeholders)
        
        # Save cleaned version
        cleaned_path = SESSION_DIR / f"{session_id}_cleaned.pdf"
        doc.save(str(cleaned_path))
        
        # Properly close documents
        doc.close()
        
        print(f"💾 PERFECT ANALYSIS COMPLETE: {session_id}")
        
        # Store session with perfect data
        SESSIONS[session_id] = {
            "original_file": str(original_path),
            "cleaned_file": str(cleaned_path),
            "placeholders": placeholders,
            "filename": file.filename,
            "font_analysis": font_analysis,  # Font analizi eklendi
        }
        
        return AnalyzeResponse(
            success=True,
            message=f"🎯 {len(placeholders)} placeholder tespit edildi ve fiziksel olarak silindi.",
            session_id=session_id,
            placeholders=placeholders,
        )
        
    except Exception as e:
        print(f"❌ Perfect analysis error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analiz hatası: {str(e)}")


@app.get("/api/preview/{session_id}")
async def preview_pdf_perfect(session_id: str, cleaned: bool = False, preview: bool = False):
    """PDF önizleme"""
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session bulunamadı")
    
    session = SESSIONS[session_id]
    # Öncelik sırası: preview > cleaned > original
    if preview and session.get("preview_file") and os.path.exists(session.get("preview_file")):
        file_path = session.get("preview_file")
    else:
        file_path = session["cleaned_file"] if cleaned else session["original_file"]
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="PDF dosyası bulunamadı")
    
    print(f"👁️ Serving {'cleaned' if cleaned else 'original'} PDF: {file_path}")
    return FileResponse(file_path, media_type="application/pdf")


@app.post("/api/preview_filled")
async def preview_filled_pdf_perfect(request: FillRequest):
    """PDF canlı önizleme üretimi (indirimsiz). Dosyayı geçici olarak yazar ve /api/preview ile servis eder."""
    try:
        session_id = request.session_id
        if session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Session bulunamadı")

        session = SESSIONS[session_id]
        placeholders = session.get("placeholders", [])
        cleaned_file = session.get("cleaned_file")
        font_analysis = session.get("font_analysis", {})
        if not cleaned_file or not os.path.exists(cleaned_file):
            raise HTTPException(status_code=404, detail="Temizlenmiş PDF bulunamadı")

        values = request.values or {}
        font_choice = request.font_choice
        text_color = request.text_color
        font_size_mode = request.font_size_mode or "auto"
        fixed_font_size = request.fixed_font_size
        min_font_size = request.min_font_size
        max_font_size = request.max_font_size
        allow_overflow = request.allow_overflow or False
        text_alignments = request.text_alignments or {}
        alignment_offsets = request.alignment_offsets or {}
        alignment_offsets_y = request.alignment_offsets_y or {}
        per_placeholder_font_sizes = request.per_placeholder_font_sizes or {}
        font_style = (request.font_style or "normal").lower()
        per_placeholder_styles = request.per_placeholder_styles or {}

        doc = fitz.open(cleaned_file)
        try:
            doc, diagnostics = insert_natural_text_with_analysis(
                doc, placeholders, values, font_analysis, font_choice, text_color,
                font_size_mode, fixed_font_size, min_font_size, max_font_size,
                allow_overflow, text_alignments, alignment_offsets, per_placeholder_font_sizes,
                alignment_offsets_y, font_style, per_placeholder_styles
            )
            preview_path = SESSION_DIR / f"{session_id}_preview.pdf"
            doc.save(str(preview_path))
            session["preview_file"] = str(preview_path)
            session["last_diagnostics"] = diagnostics
        finally:
            try:
                doc.close()
            except Exception:
                pass

        # İframe için kullanılacak URL'yi döndür
        return JSONResponse({
            "success": True,
            "preview_url": f"/api/preview/{session_id}?preview=true",
            "diagnostics": session.get("last_diagnostics") if isinstance(session.get("last_diagnostics"), list) else []
        })
    except Exception as e:
        print(f"❌ Preview filling error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Önizleme hatası: {str(e)}")


@app.post("/api/fill")
async def fill_pdf_perfect(request: FillRequest):
    """PDF doldurma sistemi"""
    try:
        session_id = request.session_id
        values = request.values
        font_choice = request.font_choice
        text_color = request.text_color
        font_size_mode = request.font_size_mode or "auto"
        fixed_font_size = request.fixed_font_size
        min_font_size = request.min_font_size
        max_font_size = request.max_font_size
        allow_overflow = request.allow_overflow or False
        text_alignments = request.text_alignments or {}
        alignment_offsets = request.alignment_offsets or {}
        alignment_offsets_y = request.alignment_offsets_y or {}
        per_placeholder_font_sizes = request.per_placeholder_font_sizes or {}
        font_style = (request.font_style or "normal").lower()
        per_placeholder_styles = request.per_placeholder_styles or {}

        if session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Session bulunamadı")

        session = SESSIONS[session_id]
        placeholders = session.get("placeholders", [])
        cleaned_file = session.get("cleaned_file")
        font_analysis = session.get("font_analysis", {})
        if not cleaned_file or not os.path.exists(cleaned_file):
            raise HTTPException(status_code=404, detail="Temizlenmiş PDF bulunamadı")

        print(f"🚀 PERFECT FILLING SESSION: {session_id}")
        print(f"📊 Values to fill: {values}")
        print(f"🎨 Font analysis available: {len(font_analysis.get('all_fonts', []))} fonts")
        print(f"🎯 User font choice: {font_choice}")
        print(f"🎨 User color choice: {text_color}")
        print(f"📐 Font size mode: {font_size_mode}")
        print(f"🚧 Allow overflow: {allow_overflow}")
        print(f"📍 Text alignments: {text_alignments}")
        print(f"📐 Manual alignment offsets: {alignment_offsets}")
        if alignment_offsets_y:
            print(f"📐 Manual vertical offsets (Y): {alignment_offsets_y}")
        if per_placeholder_font_sizes:
            print(f"📏 Per-placeholder font sizes: {per_placeholder_font_sizes}")
        if per_placeholder_styles:
            print(f"🅱 Per-placeholder styles: {per_placeholder_styles}")
        if font_style and font_style != "normal":
            print(f"🅰 Global style: {font_style}")
        if font_size_mode == "fixed":
            print(f"📏 Fixed font size: {fixed_font_size}pt")
        elif font_size_mode == "min_max":
            print(f"📏 Font size range: {min_font_size}pt - {max_font_size}pt")

        print("🚀 PHASE 2: NATURAL TEXT INSERTION")
        doc = fitz.open(cleaned_file)
        try:
            doc, diagnostics = insert_natural_text_with_analysis(
                doc, placeholders, values, font_analysis, font_choice, text_color,
                font_size_mode, fixed_font_size, min_font_size, max_font_size,
                allow_overflow, text_alignments, alignment_offsets, per_placeholder_font_sizes,
                alignment_offsets_y, font_style, per_placeholder_styles
            )
            filled_path = SESSION_DIR / f"{session_id}_filled.pdf"
            doc.save(str(filled_path))
            session["filled_file"] = str(filled_path)
            session["last_diagnostics"] = diagnostics
            print(f"💎 PERFECT FILLING COMPLETE: {filled_path}")
        finally:
            try:
                doc.close()
            except Exception:
                pass

        return JSONResponse({
            "success": True,
            "message": f"✨ {len([v for v in values.values() if v])} alan başarıyla dolduruldu.",
            "download_url": f"/api/download/{session_id}",
            "diagnostics": session.get("last_diagnostics") if isinstance(session.get("last_diagnostics"), list) else []
        })
    except Exception as e:
        print(f"❌ Perfect filling error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Doldurma hatası: {str(e)}")


@app.get("/api/download/{session_id}")
async def download_filled_pdf_perfect(session_id: str):
    """PDF indirme"""
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session bulunamadı")
    
    session = SESSIONS[session_id]
    
    if "filled_file" not in session:
        raise HTTPException(status_code=404, detail="Doldurulmuş PDF bulunamadı")
    
    filled_file = session["filled_file"]
    if not os.path.exists(filled_file):
        raise HTTPException(status_code=404, detail="PDF dosyası bulunamadı")
    
    filename = session.get("filename", "perfect.pdf")
    print(f"📥 Downloading perfect PDF: {filled_file}")
    
    return FileResponse(
        filled_file,
        media_type="application/pdf",
        filename=f"perfect_{filename}"
    )


@app.get("/api/fonts/{session_id}")
async def get_font_analysis(session_id: str):
    """PDF font analizi sonuçlarını döndürür"""
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session bulunamadı")
    
    session = SESSIONS[session_id]
    font_analysis = session.get("font_analysis", {})
    
    # Mevcut yerel fontları da ekle
    available_fonts = []
    
    # PDF'den çıkarılan fontlar
    for f in font_analysis.get("embedded_fonts", []):
        if f.get("file_path"):
            available_fonts.append({
                "id": f"extracted_{f.get('xref', 0)}",
                "name": f.get("basename") or f.get("name", "Unknown"),
                "path": f.get("file_path"),
                "source": "PDF Embedded",
                "type": f.get("type", "Unknown"),
                "page": f.get("page", 1)
            })
    
    # Yerel TTF/OTF fontlarını otomatik tara (eklenen yeni fontlar dahil)
    def _pretty_font_name(stem: str) -> str:
        try:
            s = stem.replace("_", " ").replace("-", " ")
            return s.strip().title()
        except Exception:
            return stem
    try:
        for fp in FONTS_DIR.glob("**/*"):
            if fp.suffix.lower() not in (".ttf", ".otf"):
                continue
            if not fp.exists():
                continue
            available_fonts.append({
                "id": f"local_{fp.name}",
                "name": _pretty_font_name(fp.stem),
                "path": str(fp),
                "source": "Yerel Font",
                "type": "OpenType" if fp.suffix.lower() == ".otf" else "TrueType",
                "page": "Tüm"
            })
    except Exception:
        pass
    
    return JSONResponse({
        "success": True,
        "total_fonts": len(font_analysis.get("all_fonts", [])),
        "embedded_fonts": len(font_analysis.get("embedded_fonts", [])),
        "system_fonts": len(font_analysis.get("system_fonts", [])),
        "available_fonts": available_fonts,  # Seçilebilir fontlar
        "recommendations": font_analysis.get("recommendations", {}),
        "by_page": font_analysis.get("by_page", {}),
        "embedded_details": [
            {
                "name": f.get("basename") or f.get("name"),
                "type": f.get("type"),
                "page": f.get("page"),
                "size_bytes": f.get("size_bytes", 0),
                "extractable": f.get("extractable", False)
            } for f in font_analysis.get("embedded_fonts", [])
        ],
        "system_details": [
            {
                "name": f.get("basename") or f.get("name"),
                "type": f.get("type"),
                "page": f.get("page")
            } for f in font_analysis.get("system_fonts", [])
        ]
    })


@app.get("/api/health")
async def health_perfect():
    return {"status": "perfect", "message": "Perfect System Running"}


@app.get("/")
async def serve_perfect_frontend():
    """Frontend servis"""
    try:
            html_content = r"""
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎯 PDF Placeholder Sistemi</title>
    <script src="https://unpkg.com/vue@2/dist/vue.js"></script>
    <script src="https://unpkg.com/axios/dist/axios.min.js"></script>
    <style>
        :root {
            /* Light theme (default) */
            --bg-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --header-gradient: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            --card-bg: rgba(255, 255, 255, 0.95);
            --card-shadow: 0 15px 35px rgba(0,0,0,0.1);
            --text-primary: #2d3748;
            --text-secondary: #4a5568;
            --border-color: #e2e8f0;
            --input-bg: #ffffff;
            --input-border: #cbd5e0;
            --input-focus: #4299e1;
            --button-primary: linear-gradient(135deg, #4299e1 0%, #3182ce 100%);
            --button-success: linear-gradient(135deg, #48bb78 0%, #38a169 100%);
            --button-hover: rgba(0, 0, 0, 0.05);
            --feature-badge-bg: rgba(255, 255, 255, 0.2);
            --preview-bg: #f7fafc;
            --info-panel-bg: #f0f9ff;
            --info-panel-border: #bae6fd;
            --success-bg: #f0fff4;
            --success-border: #9ae6b4;
            --error-bg: #fed7d7;
            --error-border: #feb2b2;
        }

        [data-theme="dark"] {
            --bg-gradient: linear-gradient(135deg, #1a202c 0%, #2d3748 100%);
            --header-gradient: linear-gradient(135deg, #0f1419 0%, #1a202c 100%);
            --card-bg: rgba(45, 55, 72, 0.95);
            --card-shadow: 0 15px 35px rgba(0,0,0,0.3);
            --text-primary: #f7fafc;
            --text-secondary: #e2e8f0;
            --border-color: #4a5568;
            --input-bg: #2d3748;
            --input-border: #4a5568;
            --input-focus: #63b3ed;
            --button-primary: linear-gradient(135deg, #3182ce 0%, #2c5282 100%);
            --button-success: linear-gradient(135deg, #38a169 0%, #2f855a 100%);
            --button-hover: rgba(255, 255, 255, 0.1);
            --feature-badge-bg: rgba(255, 255, 255, 0.1);
            --preview-bg: #1a202c;
            --info-panel-bg: #2d3748;
            --info-panel-border: #4a5568;
            --success-bg: #1a202c;
            --success-border: #38a169;
            --error-bg: #2d3748;
            --error-border: #fc8181;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: var(--bg-gradient);
            min-height: 100vh;
            line-height: 1.6;
            color: var(--text-primary);
            transition: all 0.3s ease;
        }
        
        .app-container {
            max-width: 1600px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            background: var(--header-gradient);
            color: white;
            padding: 3rem;
            border-radius: 25px;
            margin-bottom: 2rem;
            text-align: center;
            box-shadow: var(--card-shadow);
            position: relative;
        }
        
        .theme-toggle {
            position: absolute;
            top: 1rem;
            right: 1rem;
            background: rgba(255, 255, 255, 0.2);
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 20px;
            color: white;
            cursor: pointer;
            font-size: 1rem;
            transition: all 0.3s ease;
            backdrop-filter: blur(10px);
        }
        
        .theme-toggle:hover {
            background: rgba(255, 255, 255, 0.3);
            transform: translateY(-2px);
        }
        
        .header h1 {
            font-size: 3.5rem;
            margin-bottom: 1rem;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            font-weight: 700;
        }
        
        .header p {
            font-size: 1.4rem;
            opacity: 0.95;
            margin-bottom: 2rem;
        }
        
        .feature-badges {
            display: flex;
            justify-content: center;
            flex-wrap: wrap;
            gap: 1rem;
        }
        
        .feature-badge {
            background: var(--feature-badge-bg);
            padding: 0.75rem 1.5rem;
            border-radius: 50px;
            font-weight: 600;
            font-size: 1rem;
            border: 2px solid rgba(255, 255, 255, 0.3);
            backdrop-filter: blur(10px);
        }
        
        .main-content {
            background: var(--card-bg);
            border-radius: 25px;
            box-shadow: var(--card-shadow);
            overflow: hidden;
        }
        
        .upload-section {
            padding: 4rem;
            text-align: center;
            background: var(--preview-bg);
        }
        
        .upload-area {
            border: 3px dashed var(--input-focus);
            border-radius: 20px;
            padding: 4rem;
            background: var(--card-bg);
            transition: all 0.3s ease;
            cursor: pointer;
            position: relative;
            overflow: hidden;
        }
        
        .upload-area::before {
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: linear-gradient(45deg, transparent, rgba(42, 82, 152, 0.05), transparent);
            transform: rotate(-45deg);
            transition: all 0.6s ease;
            opacity: 0;
        }
        
        .upload-area:hover::before {
            opacity: 1;
            animation: shimmer 2s infinite;
        }
        
        @keyframes shimmer {
            0% { transform: translateX(-100%) translateY(-100%) rotate(-45deg); }
            100% { transform: translateX(100%) translateY(100%) rotate(-45deg); }
        }
        
        .upload-area:hover {
            border-color: #1e3c72;
            transform: translateY(-5px);
            box-shadow: 0 15px 35px rgba(42, 82, 152, 0.2);
        }
        
        .upload-icon {
            font-size: 6rem;
            color: #2a5298;
            margin-bottom: 2rem;
            display: block;
        }
        
        .upload-text {
            font-size: 1.5rem;
            font-weight: 600;
            color: #1e3c72;
            margin-bottom: 1rem;
        }
        
        .upload-subtext {
            font-size: 1.1rem;
            color: #6c757d;
        }
        
        .work-area {
            display: grid;
            grid-template-columns: 1fr 1.2fr;
            min-height: 85vh;
        }
        
        .form-panel {
            padding: 3rem;
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            border-right: 1px solid #dee2e6;
        }
        
        .form-panel h3 {
            font-size: 2rem;
            color: #1e3c72;
            margin-bottom: 2rem;
            text-align: center;
        }
        
        .placeholder-form {
            background: var(--card-bg);
            padding: 2.5rem;
            border-radius: 20px;
            box-shadow: var(--card-shadow);
            max-height: 70vh;
            overflow-y: auto;
        }
        
        .form-group {
            margin-bottom: 2rem;
        }
        
        .form-group label {
            display: block;
            font-weight: 700;
            color: #1e3c72;
            font-size: 1.2rem;
            margin-bottom: 0.75rem;
        }
        
        .form-group input {
            width: 100%;
            padding: 1rem 1.25rem;
            border: 2px solid #e9ecef;
            border-radius: 15px;
            font-size: 1.1rem;
            transition: all 0.3s ease;
            background: #f8f9fa;
        }
        
        .form-group input:focus {
            outline: none;
            border-color: var(--input-focus);
            background: var(--input-bg);
            box-shadow: 0 0 0 4px rgba(66, 153, 225, 0.1);
            transform: translateY(-2px);
        }
        
        .btn {
            background: linear-gradient(135deg, #2a5298 0%, #1e3c72 100%);
            color: white;
            border: none;
            padding: 1rem 2.5rem;
            border-radius: 50px;
            font-size: 1.2rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            margin: 0.5rem;
            position: relative;
            overflow: hidden;
        }
        
        .btn::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
            transition: all 0.6s ease;
        }
        
        .btn:hover::before {
            left: 100%;
        }
        
        .btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 15px 35px rgba(42, 82, 152, 0.3);
        }
        
        .btn:active {
            transform: translateY(-1px);
        }
        
        .btn:disabled {
            background: #bdc3c7;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }
        
        .perfect-btn {
            background: linear-gradient(135deg, #27ae60 0%, #229954 100%);
        }
        
        .perfect-btn:hover {
            box-shadow: 0 15px 35px rgba(39, 174, 96, 0.3);
        }
        
        .preview-panel {
            padding: 3rem;
            background: white;
            display: flex;
            flex-direction: column;
        }
        
        .preview-panel h3 {
            font-size: 2rem;
            color: #1e3c72;
            margin-bottom: 2rem;
            text-align: center;
        }
        
        .pdf-preview-container {
            flex: 1;
            background: #f8f9fa;
            border-radius: 20px;
            padding: 1.5rem;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            min-height: 70vh;
        }
        
        .pdf-preview {
            width: 100%;
            height: 70vh;
            border: none;
            border-radius: 15px;
            box-shadow: 0 15px 40px rgba(0,0,0,0.15);
            background: white;
        }
        
        .preview-placeholder {
            text-align: center;
            color: #6c757d;
            font-size: 1.3rem;
        }
        
        .preview-placeholder .icon {
            font-size: 5rem;
            margin-bottom: 1.5rem;
            display: block;
            color: #2a5298;
        }
        
        .font-color-section {
            background: white;
            margin-top: 2rem;
            padding: 2rem;
            border-radius: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }
        
        .font-color-section h4 {
            color: #1e3c72;
            margin-bottom: 1.5rem;
            font-size: 1.5rem;
        }
        
        .form-row {
            margin-bottom: 1.5rem;
        }
        
        .form-row label {
            display: block;
            font-weight: 600;
            color: #495057;
            margin-bottom: 0.5rem;
            font-size: 1rem;
        }
        
        .form-row select {
            width: 100%;
            padding: 0.75rem 1rem;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            background: white;
            transition: all 0.3s ease;
        }
        
        .form-row select:focus {
            border-color: #2a5298;
            box-shadow: 0 0 0 3px rgba(42, 82, 152, 0.1);
        }
        
        .color-picker-row {
            display: flex;
            align-items: center;
            gap: 1rem;
            flex-wrap: wrap;
        }
        
        .color-input {
            width: 60px;
            height: 50px;
            border: 3px solid #e9ecef;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        .color-input:hover {
            transform: scale(1.1);
            border-color: #2a5298;
        }
        
        .size-input {
            width: 100px;
            text-align: center;
            font-weight: 500;
        }
        
        .form-section {
            background: #f8fafc;
            padding: 1.5rem;
            border-radius: 12px;
            margin: 1rem 0;
        }
        
        .color-presets {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
            margin-top: 1rem;
        }
        
        .color-preset {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            cursor: pointer;
            border: 3px solid #fff;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            transition: all 0.3s ease;
        }
        
        .color-preset:hover {
            transform: scale(1.2);
        }
        
        .color-preset.active {
            border-color: #2a5298;
            box-shadow: 0 4px 12px rgba(42, 82, 152, 0.4);
        }
        
        .success-message {
            background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
            color: #155724;
            padding: 1.5rem 2rem;
            border-radius: 15px;
            margin: 2rem 0;
            border-left: 5px solid #28a745;
            font-weight: 600;
            font-size: 1.1rem;
        }
        
        .error-message {
            background: linear-gradient(135deg, #f8d7da 0%, #f1b0b7 100%);
            color: #721c24;
            padding: 1.5rem 2rem;
            border-radius: 15px;
            margin: 2rem 0;
            border-left: 5px solid #dc3545;
            font-weight: 600;
            font-size: 1.1rem;
        }
        
        .loading {
            text-align: center;
            padding: 3rem;
            font-size: 1.3rem;
            color: #2a5298;
        }
        
        .loading::after {
            content: '';
            display: inline-block;
            width: 40px;
            height: 40px;
            border: 4px solid #e9ecef;
            border-radius: 50%;
            border-top-color: #2a5298;
            animation: spin 1s linear infinite;
            margin-left: 1rem;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .info-panel {
            background: var(--info-panel-bg);
            padding: 1.5rem;
            border-radius: 15px;
            margin-top: 1.5rem;
            border-left: 5px solid var(--info-panel-border);
            color: var(--text-secondary);
        }
        
        .file-input {
            display: none;
        }
        
        @media (max-width: 1200px) {
            .work-area {
                grid-template-columns: 1fr;
            }
            
            .form-panel {
                border-right: none;
                border-bottom: 1px solid #dee2e6;
            }
        }
        
        @media (max-width: 768px) {
            .app-container {
                padding: 10px;
            }
            
            .header {
                padding: 2rem;
            }
            
            .header h1 {
                font-size: 2.5rem;
            }
            
            .form-panel, .preview-panel {
                padding: 1.5rem;
            }
            
            .color-presets {
                justify-content: center;
            }
        }
    </style>
</head>
<body>
    <div id="app" class="app-container">
        <!-- Header Section -->
        <div class="header">
            <button class="theme-toggle" onclick="toggleTheme()" id="themeToggle">
                🌙 Koyu Tema
            </button>
            <h1> PDF Placeholder Sistemi</h1>
           
            <div class="feature-badges">
                <span class="feature-badge">✨ Fiziksel Silme</span>
                <span class="feature-badge">🇹🇷 Unicode Font</span>
                <span class="feature-badge">🎨 Doğal Görünüm</span>
                <span class="feature-badge">⚡ Redaction API</span>
            </div>
        </div>
        
        <!-- Main Content -->
        <div class="main-content">
            <!-- Upload Section -->
            <div v-if="!sessionId" class="upload-section">
                <div class="upload-area" @click="$refs.fileInput.click()">
                    <div class="upload-icon">🎯</div>
                    <div class="upload-text">PDF Analizi</div>
                    <div class="upload-subtext"><span v-pre>{{}}</span> formatında placeholder'lar içeren PDF dosyanızı sürükleyip bırakın veya tıklayarak seçin</div>
                    <input type="file" 
                           ref="fileInput" 
                           class="file-input" 
                           accept=".pdf"
                           @change="handleFileSelect">
                </div>
                
                <!-- Loading -->
                <div v-if="isLoading" class="loading">
                    🎯 Analiz yapılıyor...
                </div>
            </div>
            
            <!-- Work Area -->
            <div v-if="sessionId && placeholders.length > 0" class="work-area">
                <!-- Form Panel -->
                <div class="form-panel">
                    <h3>✨ Metin Girişi</h3>
                    
                    <div class="placeholder-form">
                        <div v-for="placeholder in placeholders" :key="placeholder.key" class="form-group">
                            <label>📍 {{ placeholder.key }}:</label>
                            <input 
                                type="text" 
                                v-model="formValues[placeholder.key]"
                                :placeholder="placeholder.suggestion">
                            
                            <!-- Alignment Selection -->
                            <div class="alignment-selector" style="margin-top: 5px;">
                                <span style="font-size: 12px; color: #666;">Hizalama:</span>
                                <label style="margin-left: 10px;">
                                    <input type="radio" :name="'align_' + placeholder.key" 
                                           v-model="textAlignments[placeholder.key]" value="left">
                                    ← Sol
                                </label>
                                <label style="margin-left: 10px;">
                                    <input type="radio" :name="'align_' + placeholder.key" 
                                           v-model="textAlignments[placeholder.key]" value="center">
                                    ↔ Merkez
                                </label>
                                <label style="margin-left: 10px;">
                                    <input type="radio" :name="'align_' + placeholder.key" 
                                           v-model="textAlignments[placeholder.key]" value="right">
                                    → Sağ
                                </label>
                            </div>
                            
                            <!-- Manuel Offset -->
                            <div class="offset-selector" style="margin-top: 8px;">
                                <label style="font-size: 12px; color: #666;">
                                    📐 Manuel Kaydırma (px):
                                    <input type="number" 
                                           v-model.number="alignmentOffsets[placeholder.key]" 
                                           :placeholder="0"
                                           min="-50" max="50" step="0.1"
                                           style="width: 80px; margin-left: 5px; padding: 2px 5px; border: 1px solid #ddd; border-radius: 3px;">
                                    <small style="color: #999; margin-left: 5px;">(negatif=sola, pozitif=sağa, max ±50px)</small>
                                </label>
                            </div>

                            <!-- Dikey Offset (Y) -->
                            <div class="offset-selector-y" style="margin-top: 6px;">
                                <label style="font-size: 12px; color: #666;">
                                    ↕ Dikey Kaydırma (px):
                                    <input type="number"
                                           v-model.number="alignmentOffsetsY[placeholder.key]"
                                           :placeholder="0"
                                           min="-50" max="50" step="0.1"
                                           style="width: 80px; margin-left: 5px; padding: 2px 5px; border: 1px solid #ddd; border-radius: 3px;">
                                    <small style="color: #999; margin-left: 5px;">(negatif=yukarı, pozitif=aşağı, max ±50px)</small>
                                </label>
                            </div>

                            <!-- Per Placeholder Font Size -->
                            <div class="size-selector" style="margin-top: 8px;">
                                <label style="font-size: 12px; color: #666;">
                                    📏 Bu Alan için Font Boyutu (pt):
                                    <input type="number"
                                           v-model.number="perPlaceholderFontSizes[placeholder.key]"
                                           :placeholder="''"
                                           min="6" max="72" step="0.5"
                                           style="width: 90px; margin-left: 5px; padding: 2px 5px; border: 1px solid #ddd; border-radius: 3px;">
                                    <small style="color: #999; margin-left: 5px;">(boş bırakırsanız otomatik)</small>
                                </label>
                            </div>

                            <!-- Per Placeholder Style -->
                            <div class="style-selector" style="margin-top: 8px;">
                                <label style="font-size: 12px; color: #666;">
                                    🅰 Stil:
                                    <select v-model="perPlaceholderStyles[placeholder.key]" style="margin-left: 5px; padding: 2px 5px; border: 1px solid #ddd; border-radius: 3px;">
                                        <option value="">Varsayılan</option>
                                        <option value="normal">Normal</option>
                                        <option value="bold">Kalın</option>
                                        <option value="italic">İtalik</option>
                                        <option value="bold_italic">Kalın + İtalik</option>
                                    </select>
                                </label>
                            </div>
                        </div>
                        
                        <div style="text-align: center; margin-top: 2rem;">
                <button @click="fillPdf" 
                    :disabled="isLoading || !(placeholders && placeholders.length)" 
                    class="btn">
                                ✨ Doldur
                            </button>
                            
                            <button @click="fillPerfectTurkish" 
                                    class="btn perfect-btn">
                                🇹🇷 Türkçe Test Perfect
                            </button>
                        </div>
                    </div>
                    
                    <!-- Font & Color Selection -->
                    <div v-if="fontAnalysis" class="font-color-section">
                        <h4>🎨 Font ve Renk Seçimi</h4>
                        
                        <div class="form-row">
                            <label>📝 Font Seçimi:</label>
                            <select v-model="selectedFont">
                                <option value="">🤖 Otomatik (Sistem seçimi)</option>
                                <optgroup v-if="fontAnalysis.available_fonts && fontAnalysis.available_fonts.length > 0" label="📂 Mevcut Fontlar">
                                    <option v-for="font in fontAnalysis.available_fonts" :key="font.id" :value="font.path">
                                        {{ font.name }} ({{ font.source }})
                                    </option>
                                </optgroup>
                            </select>
                            <div class="form-section" style="margin-top: 0.75rem;">
                                <div style="display:flex; align-items:center; gap: 0.5rem; flex-wrap:wrap;">
                                    <span style="color:#555; font-size:0.95rem;">
                                        🧠 Önerilen gömülü font:
                                        <strong>{{ recommendedEmbeddedItem ? recommendedEmbeddedItem.name : 'Yok' }}</strong>
                                    </span>
                                    <button class="btn" style="padding:0.4rem 0.9rem; font-size:0.9rem;" @click="pickEmbeddedRecommended" :disabled="!recommendedEmbeddedItem">PDF'den seç</button>
                                    <button class="btn" style="padding:0.4rem 0.9rem; font-size:0.9rem;" @click="usePerPlaceholderAuto">Plaseholdere göre otomatik</button>
                                </div>
                                <small style="color:#777; display:block; margin-top:0.4rem;">• PDF içinde gömülü font varsa 'PDF'den seç' ile aynısını kullanır. • 'Plaseholdere göre otomatik' seçeneği, her alan için orijinal fonta en yakın olanı seçmeye çalışır.</small>
                            </div>
                            <div class="form-row" style="margin-top: 0.75rem;">
                                <label>🅰 Global Stil:</label>
                                <select v-model="globalStyle">
                                    <option value="normal">Normal</option>
                                    <option value="bold">Kalın</option>
                                    <option value="italic">İtalik</option>
                                    <option value="bold_italic">Kalın + İtalik</option>
                                </select>
                                <small style="color:#777; display:block;">Per-placeholder seçim yoksa bu stil uygulanır.</small>
                            </div>
                        </div>
                        
                        <div class="form-row">
                            <label>🎨 Metin Rengi:</label>
                            <div class="color-picker-row">
                                <input v-model="selectedColor" type="color" class="color-input">
                                <div class="color-presets">
                                    <div v-for="color in colorPresets" :key="color.hex" 
                                         :class="{ 'color-preset': true, 'active': selectedColor === color.hex }"
                                         :style="{ backgroundColor: color.hex }" 
                                         :title="color.name"
                                         @click="selectedColor = color.hex"></div>
                                </div>
                            </div>
                            <small style="color: #666; margin-top: 0.5rem; display: block;">
                                ✅ {{ getColorName(selectedColor) }} ({{ selectedColor }})
                            </small>
                        </div>
                        
                        <div class="info-panel">
                            <strong>📊 Font İstatistikleri:</strong><br>
                            • Toplam Font: {{ fontAnalysis.total_fonts }}<br>
                            • PDF Gömülü: {{ fontAnalysis.embedded_fonts }}<br>
                            • Sistem Fontu: {{ fontAnalysis.system_fonts }}<br>
                            • Seçilebilir: {{ fontAnalysis.available_fonts ? fontAnalysis.available_fonts.length : 0 }}
                        </div>
                        
                        <!-- Font Size Controls -->
                        <div class="form-section" style="margin-top: 1.5rem; border-top: 2px solid #e2e8f0; padding-top: 1.5rem;">
                            <h4>📏 Font Boyutu Kontrolü</h4>
                            
                            <div class="form-row">
                                <label>🎯 Font Boyutu Modu:</label>
                                <select v-model="fontSizeMode">
                                    <option value="auto">🤖 Otomatik (Sistem hesaplar)</option>
                                    <option value="fixed">📌 Sabit boyut</option>
                                    <option value="min_max">📊 Min/Max aralığı</option>
                                </select>
                            </div>
                            
                            <div v-if="fontSizeMode === 'fixed'" class="form-row">
                                <label>📏 Sabit Font Boyutu (pt):</label>
                                <input v-model.number="fixedFontSize" 
                                       type="number" 
                                       step="0.5" 
                                       min="6" 
                                       max="72" 
                                       class="size-input">
                                <small style="color: #666;">Önerilen: 10-18pt</small>
                            </div>
                            
                            <div v-if="fontSizeMode === 'min_max'" class="form-row" style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                                <div>
                                    <label>📏 Minimum Boyut (pt):</label>
                                    <input v-model.number="minFontSize" 
                                           type="number" 
                                           step="0.5" 
                                           min="6" 
                                           max="36" 
                                           class="size-input">
                                </div>
                                <div>
                                    <label>📏 Maksimum Boyut (pt):</label>
                                    <input v-model.number="maxFontSize" 
                                           type="number" 
                                           step="0.5" 
                                           min="8" 
                                           max="72" 
                                           class="size-input">
                                </div>
                            </div>
                            
                            <div class="info-panel" style="font-size: 0.9em;">
                                <strong>📖 Font Boyutu Rehberi:</strong><br>
                                <span v-if="fontSizeMode === 'auto'">• Sistem, placeholder alanına en uygun boyutu otomatik hesaplar</span>
                                <span v-if="fontSizeMode === 'fixed'">• Tüm metinler aynı boyutta {{ fixedFontSize }}pt olacak</span>
                                <span v-if="fontSizeMode === 'min_max'">• Metinler {{ minFontSize }}pt - {{ maxFontSize }}pt arasında boyutlandırılacak</span>
                            </div>
                            
                            <div class="form-row" style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #e2e8f0;">
                                <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                                    <input v-model="allowOverflow" type="checkbox" style="transform: scale(1.2);">
                                    <span>🚧 Alan Taşma İzni</span>
                                </label>
                                <small style="color: #666; margin-top: 0.5rem; display: block;">
                                    ✅ Etkinleştirilirse, büyük font boyutları placeholder alanından taşabilir
                                </small>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Preview Panel -->
                <div class="preview-panel">
                    <h3>👁️ PDF Önizlemesi</h3>
                    
                    <div class="pdf-preview-container">
                        <iframe v-if="previewUrl" 
                                :src="previewUrl" 
                                class="pdf-preview"></iframe>
                        
                        <div v-else class="preview-placeholder">
                            <span class="icon">📄</span>
                            <div style="font-weight: bold; margin-bottom: 1rem;">PDF Önizlemesi</div>
                            <div>Önizleme yükleniyor...</div>
                        </div>
                    </div>
                    
                    <div class="info-panel" style="margin-top: 1rem;">
                        📄 PDF başarıyla yüklendi • ✨ Fiziksel placeholder temizleme aktif
                    </div>
                </div>
            </div>
            
            <!-- Success/Error Messages -->
            <div v-if="successMessage" class="success-message">
                {{ successMessage }}
            </div>
            <div v-if="diagnostics && diagnostics.length" style="margin-top: 10px; padding: 10px; border: 1px solid #eee; border-radius: 6px; background: #fafafa;">
                <div style="font-weight: 600; margin-bottom: 6px;">🕵️ Otomatik font seçimi tanılama</div>
                <div style="font-size: 12px; color: #666; margin-bottom: 8px;">Hangi fontların denendiği ve hangisinin kullanıldığı listelenir.</div>
                <div style="max-height: 220px; overflow: auto; border: 1px solid #eee;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                        <thead>
                            <tr style="background: #f0f0f0;">
                                <th style="text-align: left; padding: 6px; border-bottom: 1px solid #ddd;">Key</th>
                                <th style="text-align: left; padding: 6px; border-bottom: 1px solid #ddd;">Stil</th>
                                <th style="text-align: left; padding: 6px; border-bottom: 1px solid #ddd;">Seçilen Font</th>
                                <th style="text-align: left; padding: 6px; border-bottom: 1px solid #ddd;">Denenen Adaylar</th>
                                <th style="text-align: left; padding: 6px; border-bottom: 1px solid #ddd;">Boyut</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="row in diagnostics" :key="row.key + ':' + row.style">
                                <td style="padding: 6px; border-bottom: 1px solid #eee;">{{ row.key }}</td>
                                <td style="padding: 6px; border-bottom: 1px solid #eee;">{{ row.style }}</td>
                                <td style="padding: 6px; border-bottom: 1px solid #eee;">{{ row.font_used }}</td>
                                <td style="padding: 6px; border-bottom: 1px solid #eee; white-space: pre-wrap;">{{ (row.candidates_tried || []).join('\n') }}</td>
                                <td style="padding: 6px; border-bottom: 1px solid #eee;">{{ fsDisplay(row.fs) }}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
            
            <div v-if="errorMessage" class="error-message">
                {{ errorMessage }}
            </div>
            
            <!-- No Placeholders -->
            <div v-if="sessionId && placeholders.length === 0" class="error-message">
                Bu PDF'de <span v-pre>{{}}</span> formatında placeholder bulunamadı.
            </div>
        </div>
    </div>

        <script>
        (function(){
            new Vue({
                el: '#app',
                data: function() {
                    return {
                        isDragOver: false,
                        isLoading: false,
                        sessionId: null,
                        placeholders: [],
                        formValues: {},
                        textAlignments: {},
                        alignmentOffsets: {},
                        alignmentOffsetsY: {},
                        successMessage: '',
                        errorMessage: '',
                        diagnostics: [],
                        previewUrl: null,
                        apiBase: (typeof window !== 'undefined' ? window.location.origin : ''),
                        fontAnalysis: null,
                        selectedFont: '',
                        selectedColor: '#000000',
                        fontSizeMode: 'auto',
                        fixedFontSize: 12,
                        minFontSize: 8,
                        maxFontSize: 24,
                        allowOverflow: false,
                        perPlaceholderFontSizes: {},
                        perPlaceholderStyles: {},
                        globalStyle: 'normal',
                        colorPresets: [
                            { hex: '#000000', name: 'Siyah' },
                            { hex: '#ffffff', name: 'Beyaz' },
                            { hex: '#1f2937', name: 'Koyu Gri' },
                            { hex: '#374151', name: 'Gri' },
                            { hex: '#6b7280', name: 'Açık Gri' },
                            { hex: '#9ca3af', name: 'Çok Açık Gri' },
                            { hex: '#1e40af', name: 'Koyu Mavi' },
                            { hex: '#0e7afe', name: 'Mavi' },
                            { hex: '#3b82f6', name: 'Parlak Mavi' },
                            { hex: '#60a5fa', name: 'Açık Mavi' },
                            { hex: '#93c5fd', name: 'Çok Açık Mavi' },
                            { hex: '#1e3a8a', name: 'Lacivert' },
                            { hex: '#15803d', name: 'Koyu Yeşil' },
                            { hex: '#059669', name: 'Yeşil' },
                            { hex: '#22c55e', name: 'Parlak Yeşil' },
                            { hex: '#10b981', name: 'Açık Yeşil' },
                            { hex: '#34d399', name: 'Çok Açık Yeşil' },
                            { hex: '#065f46', name: 'Orman Yeşili' },
                            { hex: '#991b1b', name: 'Koyu Kırmızı' },
                            { hex: '#dc2626', name: 'Kırmızı' },
                            { hex: '#ef4444', name: 'Parlak Kırmızı' },
                            { hex: '#f87171', name: 'Açık Kırmızı' },
                            { hex: '#fca5a5', name: 'Çok Açık Kırmızı' },
                            { hex: '#581c87', name: 'Koyu Mor' },
                            { hex: '#7c3aed', name: 'Mor' },
                            { hex: '#8b5cf6', name: 'Açık Mor' },
                            { hex: '#a78bfa', name: 'Çok Açık Mor' },
                            { hex: '#c084fc', name: 'Lila' },
                            { hex: '#c2410c', name: 'Koyu Turuncu' },
                            { hex: '#ea580c', name: 'Turuncu' },
                            { hex: '#f97316', name: 'Parlak Turuncu' },
                            { hex: '#fb923c', name: 'Açık Turuncu' },
                            { hex: '#a16207', name: 'Koyu Sarı' },
                            { hex: '#ca8a04', name: 'Sarı' },
                            { hex: '#eab308', name: 'Parlak Sarı' },
                            { hex: '#facc15', name: 'Açık Sarı' },
                            { hex: '#fde047', name: 'Çok Açık Sarı' },
                            { hex: '#be185d', name: 'Koyu Pembe' },
                            { hex: '#db2777', name: 'Pembe' },
                            { hex: '#ec4899', name: 'Parlak Pembe' },
                            { hex: '#f472b6', name: 'Açık Pembe' },
                            { hex: '#0d9488', name: 'Teal' },
                            { hex: '#14b8a6', name: 'Parlak Teal' },
                            { hex: '#06b6d4', name: 'Cyan' },
                            { hex: '#0891b2', name: 'Koyu Cyan' },
                            { hex: '#92400e', name: 'Koyu Kahverengi' },
                            { hex: '#a3621b', name: 'Kahverengi' },
                            { hex: '#d97706', name: 'Açık Kahverengi' },
                            { hex: '#7c2d12', name: 'Bordo' },
                            { hex: '#4c1d95', name: 'İndigo' },
                            { hex: '#701a75', name: 'Fuşya' },
                            { hex: '#166534', name: 'Zümrüt Yeşili' }
                        ],
                        // Live preview handling
                        livePreviewEnabled: true,
                        _previewTimer: null,
                        _lastPreviewPayload: null
                    };
                },
                computed: {
                    hasValues: function() {
                        try {
                            for (var k in this.formValues) {
                                if (!Object.prototype.hasOwnProperty.call(this.formValues, k)) continue;
                                var v = this.formValues[k];
                                if (v && String(v).trim()) return true;
                            }
                            return false;
                        } catch (e) { return false; }
                    },
                    recommendedEmbeddedItem: function() {
                        try {
                            if (!this.fontAnalysis) return null;
                            var rec = this.fontAnalysis.recommendations || {};
                            var targetName = rec.primary_embedded;
                            if (!targetName) return null;
                            var list = this.fontAnalysis.available_fonts || [];
                            var tn = String(targetName).toLowerCase();
                            for (var i = 0; i < list.length; i++) {
                                var f = list[i] || {};
                                var src = String(f.source || '');
                                var nm = String(f.name || '').toLowerCase();
                                if (src.indexOf('Embedded') >= 0 && nm.indexOf(tn) >= 0) return f;
                            }
                            return null;
                        } catch (e) { return null; }
                    }
                },
                methods: {
                    _debouncePreview: function() {
                        var self = this;
                        if (!self.livePreviewEnabled || !self.sessionId) return;
                        if (self._previewTimer) {
                            clearTimeout(self._previewTimer);
                            self._previewTimer = null;
                        }
                        self._previewTimer = setTimeout(function(){ self._runLivePreview(); }, 400);
                    },
                    _runLivePreview: function() {
                        var self = this;
                        if (!self.sessionId) return;
                        try {
                            // Prepare per-placeholder sizes cleaned numbers
                            var cleaned = {};
                            var sizes = self.perPlaceholderFontSizes || {};
                            for (var k in sizes) {
                                if (!Object.prototype.hasOwnProperty.call(sizes, k)) continue;
                                var v = sizes[k];
                                if (v !== undefined && v !== null && !isNaN(v)) cleaned[k] = v;
                            }
                            function hexToRgb(hex) {
                                var m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
                                if (!m) return [0,0,0];
                                return [ parseInt(m[1],16)/255, parseInt(m[2],16)/255, parseInt(m[3],16)/255 ];
                            }
                            var payload = {
                                session_id: self.sessionId,
                                values: self.formValues,
                                font_choice: self.selectedFont,
                                text_color: hexToRgb(self.selectedColor),
                                font_size_mode: self.fontSizeMode,
                                fixed_font_size: self.fontSizeMode === 'fixed' ? self.fixedFontSize : null,
                                min_font_size: self.fontSizeMode === 'min_max' ? self.minFontSize : null,
                                max_font_size: self.fontSizeMode === 'min_max' ? self.maxFontSize : null,
                                allow_overflow: self.allowOverflow,
                                text_alignments: self.textAlignments,
                                alignment_offsets: self.alignmentOffsets,
                                alignment_offsets_y: self.alignmentOffsetsY,
                                per_placeholder_font_sizes: cleaned,
                                font_style: self.globalStyle,
                                per_placeholder_styles: self.perPlaceholderStyles
                            };
                            self._lastPreviewPayload = payload;
                            axios.post(self.apiBase + '/api/preview_filled', payload)
                                .then(function(resp){
                                    var d = (resp && resp.data) ? resp.data : {};
                                    if (d && d.success && d.preview_url) {
                                        // Bust cache
                                        self.previewUrl = self.apiBase + d.preview_url + '&t=' + Date.now();
                                        self.diagnostics = d.diagnostics || [];
                                    }
                                })
                                .catch(function(err){ /* swallow preview errors to avoid UX disruption */ });
                        } catch (e) { /* ignore */ }
                    },
                    getColorName: function(hex) {
                        try {
                            var list = this.colorPresets || [];
                            for (var i = 0; i < list.length; i++) {
                                var it = list[i];
                                if (it && it.hex === hex) return it.name || 'Özel renk';
                            }
                            return 'Özel renk';
                        } catch (e) { return 'Özel renk'; }
                    },
                    fsDisplay: function(val) {
                        var n = Number(val);
                        return isFinite(n) ? n.toFixed(1) : val;
                    },
                    getErrorDetail: function(error) {
                        try {
                            if (error && error.response && error.response.data) {
                                return error.response.data.detail || error.response.data.message || error.message || 'Bilinmeyen hata';
                            }
                            return (error && error.message) ? error.message : 'Bilinmeyen hata';
                        } catch (e) { return 'Bilinmeyen hata'; }
                    },
                    pickEmbeddedRecommended: function() {
                        try {
                            var item = this.recommendedEmbeddedItem;
                            if (item) this.selectedFont = item.path;
                        } catch (e) {}
                    },
                    usePerPlaceholderAuto: function() {
                        this.selectedFont = '';
                        var self = this;
                        this.$nextTick(function(){ console.log('Per-placeholder auto font mode active'); });
                    },
                    handleFileSelect: function(event) {
                        var file = event && event.target && event.target.files ? event.target.files[0] : null;
                        if (file) this.uploadFile(file);
                    },
                    uploadFile: function(file) {
                        var self = this;
                        self.isLoading = true;
                        self.errorMessage = '';
                        self.successMessage = '';
                        try {
                            var formData = new FormData();
                            formData.append('file', file);
                            axios.post(self.apiBase + '/api/analyze', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
                                .then(function(response){
                                    response = response || { data: {} };
                                    var data = response.data || {};
                                    if (data.success) {
                                        self.sessionId = data.session_id;
                                        self.placeholders = data.placeholders || [];
                                        self.successMessage = data.message || '';
                                        // Build fresh objects to keep Vue 2 reactivity intact
                                        var fv = {}, ta = {}, off = {}, offY = {}, pfs = {}, pst = {};
                                        for (var i = 0; i < self.placeholders.length; i++) {
                                            var p = self.placeholders[i];
                                            fv[p.key] = '';
                                            ta[p.key] = 'center';
                                            off[p.key] = 0;
                                            offY[p.key] = 0;
                                            pfs[p.key] = undefined;
                                            pst[p.key] = '';
                                        }
                                        self.formValues = fv;
                                        self.textAlignments = ta;
                                        self.alignmentOffsets = off;
                                        self.alignmentOffsetsY = offY;
                                        self.perPlaceholderFontSizes = pfs;
                                        self.perPlaceholderStyles = pst;
                                        self.previewUrl = self.apiBase + '/api/preview/' + self.sessionId + '?cleaned=true&t=' + Date.now();
                                        self.loadFontAnalysis();
                                    } else {
                                        self.errorMessage = data.message || 'Analiz başarısız';
                                    }
                                })
                                .catch(function(error){
                                    console.error('Upload error:', error);
                                    self.errorMessage = '🎯 Analiz hatası: ' + self.getErrorDetail(error);
                                })
                                .then(function(){ self.isLoading = false; });
                        } catch (err) {
                            console.error('Upload error (outer):', err);
                            self.errorMessage = '🎯 Analiz hatası: ' + self.getErrorDetail(err);
                            self.isLoading = false;
                        }
                    },
                    loadFontAnalysis: function() {
                        var self = this;
                        if (!self.sessionId) return;
                        try {
                            axios.get(self.apiBase + '/api/fonts/' + self.sessionId)
                                .then(function(response){
                                    response = response || { data: {} };
                                    var data = response.data || {};
                                    if (data.success) self.fontAnalysis = data;
                                })
                                .catch(function(error){ console.warn('Font analysis failed:', error); });
                        } catch (e) { console.warn('Font analysis failed (outer):', e); }
                    },
                    fillPerfectTurkish: function() {
                        var perfectTurkish = {
                            'Soyad': 'Müşterioğlu',
                            'İsim': 'Özgürcan',
                            'Şehir': 'İstanbul',
                            'Ülke': 'Türkiye',
                            'Name': 'Gülşah',
                            'Surname': 'Şahinoğlu',
                            'Company': 'Çağrı Müşteri Hizmetleri'
                        };
                        for (var i = 0; i < this.placeholders.length; i++) {
                            var p = this.placeholders[i];
                            var val = perfectTurkish[p.key] ? perfectTurkish[p.key] : ('Perfect_' + p.key + '_Işığı_Çağrı');
                            // Ensure reactivity if keys were not present
                            if (Object.prototype.hasOwnProperty.call(this.formValues, p.key)) {
                                this.formValues[p.key] = val;
                            } else if (this.$set) {
                                this.$set(this.formValues, p.key, val);
                            } else {
                                this.formValues[p.key] = val;
                            }
                        }
                        this._debouncePreview();
                    },
                    fillPdf: function() {
                        var self = this;
                        self.isLoading = true;
                        self.errorMessage = '';
                        self.successMessage = '';
                        function hexToRgb(hex) {
                            var m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
                            if (!m) return [0,0,0];
                            return [ parseInt(m[1],16)/255, parseInt(m[2],16)/255, parseInt(m[3],16)/255 ];
                        }
                        var textRgb = hexToRgb(self.selectedColor);
                        var cleaned = {};
                        var sizes = self.perPlaceholderFontSizes || {};
                        for (var k in sizes) {
                            if (!Object.prototype.hasOwnProperty.call(sizes, k)) continue;
                            var v = sizes[k];
                            if (v !== undefined && v !== null && !isNaN(v)) cleaned[k] = v;
                        }
                        axios.post(self.apiBase + '/api/fill', {
                            session_id: self.sessionId,
                            values: self.formValues,
                            font_choice: self.selectedFont,
                            text_color: textRgb,
                            font_size_mode: self.fontSizeMode,
                            fixed_font_size: self.fontSizeMode === 'fixed' ? self.fixedFontSize : null,
                            min_font_size: self.fontSizeMode === 'min_max' ? self.minFontSize : null,
                            max_font_size: self.fontSizeMode === 'min_max' ? self.maxFontSize : null,
                            allow_overflow: self.allowOverflow,
                            text_alignments: self.textAlignments,
                            alignment_offsets: self.alignmentOffsets,
                            alignment_offsets_y: self.alignmentOffsetsY,
                            per_placeholder_font_sizes: cleaned,
                            font_style: self.globalStyle,
                            per_placeholder_styles: self.perPlaceholderStyles
                        }).then(function(response){
                            response = response || { data: {} };
                            var data = response.data || {};
                            if (data.success) {
                                self.successMessage = (data.message || 'Başarılı') + ' • Renk: ' + self.selectedColor;
                                self.diagnostics = data.diagnostics || [];
                                window.open(self.apiBase + '/api/download/' + self.sessionId, '_blank');
                            } else {
                                self.errorMessage = '🎯 Doldurma hatası';
                            }
                        }).catch(function(error){
                            console.error('Fill error:', error);
                            self.errorMessage = '🎯 Doldurma hatası: ' + self.getErrorDetail(error);
                        }).then(function(){ self.isLoading = false; });
                    }
                }
                ,
                watch: {
                    formValues: {
                        handler: function(){ this._debouncePreview(); },
                        deep: true
                    },
                    selectedFont: function(){ this._debouncePreview(); },
                    selectedColor: function(){ this._debouncePreview(); },
                    fontSizeMode: function(){ this._debouncePreview(); },
                    fixedFontSize: function(){ this._debouncePreview(); },
                    minFontSize: function(){ this._debouncePreview(); },
                    maxFontSize: function(){ this._debouncePreview(); },
                    allowOverflow: function(){ this._debouncePreview(); },
                    textAlignments: {
                        handler: function(){ this._debouncePreview(); },
                        deep: true
                    },
                    alignmentOffsets: {
                        handler: function(){ this._debouncePreview(); },
                        deep: true
                    },
                    alignmentOffsetsY: {
                        handler: function(){ this._debouncePreview(); },
                        deep: true
                    },
                    perPlaceholderFontSizes: {
                        handler: function(){ this._debouncePreview(); },
                        deep: true
                    },
                    perPlaceholderStyles: {
                        handler: function(){ this._debouncePreview(); },
                        deep: true
                    }
                }
            });
        })();
        
        // Theme toggle functionality
        function toggleTheme() {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            const toggleBtn = document.getElementById('themeToggle');
            
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            
            if (newTheme === 'dark') {
                toggleBtn.textContent = '☀️ Açık Tema';
            } else {
                toggleBtn.textContent = '🌙 Koyu Tema';
            }
        }
        
        // Load saved theme on page load
        document.addEventListener('DOMContentLoaded', function() {
            const savedTheme = localStorage.getItem('theme') || 'light';
            const toggleBtn = document.getElementById('themeToggle');
            
            document.documentElement.setAttribute('data-theme', savedTheme);
            
            if (savedTheme === 'dark') {
                toggleBtn.textContent = '☀️ Açık Tema';
            } else {
                toggleBtn.textContent = '🌙 Koyu Tema';
            }
        });
        </script>
</body>
</html>
            """
            return HTMLResponse(content=html_content)
    except Exception as e:
        return JSONResponse({"message": "Perfect System Running", "port": 8010, "error": str(e)})


if __name__ == "__main__":
    import uvicorn
    print("🎯 PDF PLACEHOLDER SYSTEM BAŞLATILIYOR...")
    print("📱 URL: http://localhost:8011")
    print("✨ Features: Physical Removal, Natural Text, Perfect Turkish")
    print("⚡ REDACTION API - TRUE TEXT DELETION!")
    print("🇹🇷 Unicode font embed + tek sefer çizim + TR karakter garantisi")
    
    uvicorn.run(app, host="127.0.0.1", port=8011)
