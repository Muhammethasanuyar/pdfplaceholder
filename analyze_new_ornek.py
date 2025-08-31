import fitz
import re
import sys
from pathlib import Path

def analyze_ornek_pdf_detailed():
    """Yeni Ornek.pdf'yi detaylı analiz et"""
    print("🔍 YENİ ORNEK.PDF DETAYLI ANALİZ")
    print("=" * 50)
    
    pdf_path = "ornek_yeni.pdf"
    if not Path(pdf_path).exists():
        print("❌ PDF dosyası bulunamadı!")
        return
    
    doc = fitz.open(pdf_path)
    print(f"📄 PDF: {pdf_path}")
    print(f"📊 Sayfa sayısı: {len(doc)} sayfa")
    
    # 1) Tüm text'i al ve incele
    all_text = ""
    for page_num, page in enumerate(doc):
        page_text = page.get_text()
        all_text += page_text + "\n"
        print(f"\n📄 SAYFA {page_num + 1} METNİ:")
        print("-" * 30)
        print(page_text)
        
        # Text block analizi
        blocks = page.get_text("dict")["blocks"]
        print(f"\n📋 SAYFA {page_num + 1} - TEXT BLOCK ANALİZİ:")
        for i, block in enumerate(blocks):
            if "lines" in block:
                for j, line in enumerate(block["lines"]):
                    for k, span in enumerate(line["spans"]):
                        text = span["text"].strip()
                        if text:
                            bbox = span["bbox"]
                            print(f"  📍 [{i}.{j}.{k}] '{text}' @ ({bbox[0]:.1f}, {bbox[1]:.1f}) - ({bbox[2]:.1f}, {bbox[3]:.1f})")
                            
                            # Özel kontroller
                            if "NEW" in text.upper():
                                print(f"    🚨 'NEW' metni tespit edildi!")
                            if "{{" in text and "}}" in text:
                                print(f"    🎯 Placeholder pattern tespit edildi!")
    
    doc.close()
    
    # 2) Pattern detection testi
    print(f"\n🎯 PATTERN DETECTION TESTI:")
    print("-" * 40)
    
    # Mevcut pattern'lar
    PH_PATTERNS = [
        re.compile(r'\{\{\s*([^}]+?)\s*\}\}'),      # {{Ad}}
        re.compile(r'\{\s*\{\s*([^}]+?)\s*\}\s*\}'), # { {Ad} }
        re.compile(r'\{\s*([^}]+?)\s*\}'),            # {Ad} - TEHLİKELİ!
        re.compile(r'\[\[\s*([^\]]+?)\s*\]\]'),       # [[Ad]]
        re.compile(r'\[\s*\[\s*([^\]]+?)\s*\]\s*\]'), # [ [Ad] ]
        re.compile(r'\[\s*([^\]]+?)\s*\]'),            # [Ad] - TEHLİKELİ!
        re.compile(r'\(\(\s*([^)]+?)\s*\)\)'),        # ((Ad))
        re.compile(r'\(\s*\(\s*([^)]+?)\s*\)\s*\)'),  # ( (Ad) )
        re.compile(r'\{\{\{\s*([^}]+?)\s*\}\}\}'),    # {{{Ad}}}
        re.compile(r'\{\[\s*([^\]]+?)\s*\]\}'),       # {[Ad]}
        re.compile(r'\[\{\s*([^}]+?)\s*\}\]'),        # [{Ad}]
        re.compile(r'\$\{\s*([^}]+?)\s*\}'),          # ${Ad}
        re.compile(r'%\{\s*([^}]+?)\s*\}%'),          # %{Ad}%
        re.compile(r'@\{\s*([^}]+?)\s*\}'),           # @{Ad}
        re.compile(r'#\{\s*([^}]+?)\s*\}'),           # #{Ad}
    ]
    
    PATTERN_NAMES = [
        "{{Ad}}", "{ {Ad} }", "{Ad}", "[[Ad]]", "[ [Ad] ]", "[Ad]", 
        "((Ad))", "( (Ad) )", "{{{Ad}}}", "{[Ad]}", "[{Ad}]", 
        "${Ad}", "%{Ad}%", "@{Ad}", "#{Ad}"
    ]
    
    valid_placeholders = []
    false_positives = []
    
    for i, pattern in enumerate(PH_PATTERNS):
        matches = list(pattern.finditer(all_text))
        pattern_name = PATTERN_NAMES[i]
        
        print(f"\n📍 Pattern {i+1}: {pattern_name} - {len(matches)} matches")
        
        for match in matches:
            full_match = match.group(0)
            key = match.group(1).strip()
            
            # FALSE POSITIVE KONTROLÜ
            is_false_positive = False
            reasons = []
            
            # 1) Kısa büyük harf/sayı kombinasyonları
            if key.isalnum() and (key.isupper() or key.isdigit()) and len(key) <= 4:
                is_false_positive = True
                reasons.append(f"Short uppercase/digit: '{key}'")
            
            # 2) Yaygın kelimeler
            common_words = {'NEW', 'OLD', 'YES', 'NO', 'TOP', 'END', 'ALL', 'ANY', 'HOW', 'WHO', 'WHAT'}
            if key.upper() in common_words:
                is_false_positive = True
                reasons.append(f"Common word: '{key}'")
            
            # 3) Tek karakter
            if len(key) == 1:
                is_false_positive = True
                reasons.append(f"Single char: '{key}'")
            
            # 4) Sadece sayı
            if key.isdigit():
                is_false_positive = True
                reasons.append(f"Number only: '{key}'")
            
            # 5) Geçersiz karakterler
            if any(c in key for c in '{}[]()'):
                is_false_positive = True
                reasons.append(f"Invalid chars: '{key}'")
            
            if is_false_positive:
                false_positives.append({
                    'pattern': pattern_name,
                    'match': full_match,
                    'key': key,
                    'reasons': reasons
                })
                print(f"   ❌ FALSE POSITIVE: '{full_match}' → key: '{key}' | {', '.join(reasons)}")
            else:
                valid_placeholders.append({
                    'pattern': pattern_name,
                    'match': full_match,
                    'key': key
                })
                print(f"   ✅ VALID: '{full_match}' → key: '{key}'")
    
    # 3) Özet
    print(f"\n📊 PATTERN ANALİZ ÖZETİ:")
    print(f"   ✅ Geçerli placeholder'lar: {len(valid_placeholders)}")
    print(f"   ❌ False positive'ler: {len(false_positives)}")
    
    print(f"\n✅ GEÇERLİ PLACEHOLDER'LAR:")
    for ph in valid_placeholders:
        print(f"   📍 '{ph['key']}' = '{ph['match']}' (pattern: {ph['pattern']})")
    
    if false_positives:
        print(f"\n❌ FALSE POSITIVE'LER:")
        for fp in false_positives:
            print(f"   ⚠️ '{fp['key']}' = '{fp['match']}' (pattern: {fp['pattern']}) - {', '.join(fp['reasons'])}")
    
    # 4) Sorun analizi ve çözüm önerileri
    print(f"\n💡 SORUN ANALİZİ VE ÇÖZÜMLERİ:")
    print("=" * 50)
    
    if false_positives:
        print("🚨 SORUN 1: False positive pattern detection")
        print("   - Çok gevşek pattern'lar normal metinleri yakalıyor")
        print("   - Çözüm: Pattern filtreleme sistemi ekle")
        print("   - Riskli pattern'lar: {Ad} ve [Ad] gibi tek bracket pattern'ları")
    
    print("\n🚨 SORUN 2: NEW metni silinme problemi")
    print("   - Büyük placeholder rect'leri diğer metinleri de kapsıyor")
    print("   - Çözüm: Precise redaction sistemi (sadece exact placeholder text'ini sil)")
    
    print("\n🚨 SORUN 3: Tüm placeholder instance'ları doldurulmuyor")
    print("   - Aynı key'li multiple placeholder'lardan bazıları atlanıyor")
    print("   - Çözüm: Instance-based filling sistemi")

if __name__ == "__main__":
    analyze_ornek_pdf_detailed()
