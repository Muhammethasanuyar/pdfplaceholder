# pip install pymupdf
import fitz  # PyMuPDF
import json, sys, re, os
from typing import Dict, List, Tuple

# {{ ... }} yakalayan regex (Türkçe karakterleri de kapsar)
PH_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}", re.UNICODE)

def load_mapping(path: str) -> Dict[str, str]:
    with open(path, "r", encoding="utf-8") as f:
        m = json.load(f)
    # anahtarları casefold ile normalize et (İ/ı dahil)
    return {k.strip().casefold(): str(v) for k, v in m.items()}

def union_bbox(parts: List[Tuple[float,float,float,float]]) -> fitz.Rect:
    x0s, y0s, x1s, y1s = zip(*parts)
    return fitz.Rect(min(x0s), min(y0s), max(x1s), max(y1s))

def find_placeholders(page: fitz.Page):
    """
    sayfadaki {{...}} placeholder'larını, satır içindeki birden fazla span'a bölünmüş olsa bile bulur.
    döner: [{"key": "adı", "rect": fitz.Rect}, ...]
    """
    hits = []
    raw = page.get_text("rawdict")  # blocks -> lines -> spans (kerning korunur)
    for b in raw.get("blocks", []):
        if b.get("type", 0) != 0:
            continue  # sadece metin blokları
        for ln in b.get("lines", []):
            spans = ln.get("spans", [])
            if not spans: 
                continue
            # tüm span metinlerini tek satır gibi birleştir
            texts = [s.get("text","") for s in spans]
            line_text = "".join(texts)
            for m in PH_RE.finditer(line_text):
                start, end = m.span()
                key = m.group(1).strip()
                # eşleşen bölümün kapsadığı span parçalarını bularak bbox çıkar
                parts = []
                pos = 0
                for s in spans:
                    t = s.get("text",""); n = len(t)
                    span_start, span_end = pos, pos+n
                    ov0, ov1 = max(start, span_start), min(end, span_end)
                    if ov0 < ov1 and n > 0:
                        x0,y0,x1,y1 = s["bbox"]
                        # kısmi örtüşmede x'i orantıla (yaklaşık ama iş görür)
                        fL = (ov0 - span_start)/n
                        fR = (ov1 - span_start)/n
                        xx0 = x0 + (x1-x0)*fL
                        xx1 = x0 + (x1-x0)*fR
                        parts.append((xx0,y0,xx1,y1))
                    pos = span_end
                if parts:
                    rect = union_bbox(parts)
                    # hafif tampon
                    rect.x0 -= 0.5; rect.x1 += 0.5
                    hits.append({"key": key, "rect": rect})
    return hits

def shrink_fit_textbox(page, rect: fitz.Rect, text: str, fontname: str,
                       min_fs=11, max_fs=32, pad=1.5, align=0, color=(0,0,0)):
    """
    kutuyu beyaz kapatır; metni sığdığı kadar büyütüp tek kez yazar.
    align: 0=sol, 1=orta, 2=sağ
    """
    inner = fitz.Rect(rect.x0+pad, rect.y0+pad, rect.x1-pad, rect.y1-pad)
    # kapat
    page.draw_rect(rect, color=(1,1,1), fill=(1,1,1))
    fs = min(max_fs, max(min_fs, inner.height * 0.9))
    step = 0.5

    def fits(size: float) -> bool:
        leftover = page.insert_textbox(inner, text, fontname=fontname, fontsize=size,
                                       color=color, align=align)
        return leftover == ""

    while fs + step <= max_fs and fits(fs + step): fs += step
    while not fits(fs) and fs - step >= min_fs: fs -= step
    # temizle ve final
    page.draw_rect(rect, color=(1,1,1), fill=(1,1,1))
    page.insert_textbox(inner, text, fontname=fontname, fontsize=fs,
                        color=color, align=align)

def fill_pdf(in_path: str, out_path: str, mapping_path: str, font_path: str = None,
             align_map: Dict[str,int] = None):
    mapping = load_mapping(mapping_path)
    align_map = align_map or {}
    doc = fitz.open(in_path)
    # font (Türkçe güvenli)
    try:
        fontname = doc.insert_font(fontfile=font_path) if font_path else "helv"
    except Exception:
        fontname = "helv"

    filled = set()
    for page in doc:
        phs = find_placeholders(page)
        for ph in phs:
            key_norm = ph["key"].casefold()
            if key_norm not in mapping:
                continue
            val = mapping[key_norm]
            align = align_map.get(key_norm, 0)
            shrink_fit_textbox(page, ph["rect"], val, fontname, min_fs=11, max_fs=32, pad=1.5, align=align)
            filled.add(key_norm)

    doc.save(out_path, incremental=False, deflate=True)
    doc.close()

    missing = [k for k in mapping.keys() if k not in filled]
    if missing:
        print("Uyarı: PDF’te bulunamayan placeholder(lar):", missing)

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Kullanım: python fill_placeholders.py input.pdf output.pdf mapping.json [--font FONT.ttf]")
        sys.exit(1)
    in_pdf, out_pdf, map_json = sys.argv[1], sys.argv[2], sys.argv[3]
    font = None
    if len(sys.argv) >= 6 and sys.argv[4] == "--font":
        font = sys.argv[5]
    fill_pdf(in_pdf, out_pdf, map_json, font_path=font)
