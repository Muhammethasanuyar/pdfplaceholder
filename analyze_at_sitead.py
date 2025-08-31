import fitz

def analyze_at_sitead_problem():
    """at {{sitead}} text elementini detaylı analiz et"""
    print("🔍 AT SITEAD PROBLEM ANALİZİ")
    print("=" * 40)
    
    doc = fitz.open("ornek_yeni.pdf")
    page = doc[0]
    
    # Text dict ile detaylı analiz
    text_dict = page.get_text("dict")
    
    print("📋 TEXT BLOCK DETAYLI ANALİZ:")
    for i, block in enumerate(text_dict["blocks"]):
        if "lines" in block:
            print(f"\n📦 Block {i}:")
            for j, line in enumerate(block["lines"]):
                print(f"  📏 Line {j}:")
                for k, span in enumerate(line["spans"]):
                    text = span["text"]
                    bbox = span["bbox"]
                    font = span["font"]
                    size = span["size"]
                    
                    print(f"    📍 Span {k}: '{text}'")
                    print(f"        Position: ({bbox[0]:.1f}, {bbox[1]:.1f}) - ({bbox[2]:.1f}, {bbox[3]:.1f})")
                    print(f"        Font: {font}, Size: {size:.1f}")
                    print(f"        Area: {bbox[2] - bbox[0]:.1f} x {bbox[3] - bbox[1]:.1f}")
                    
                    # NEW ile overlap kontrolü
                    new_rect = [164.3, 138.3, 429.7, 256.1]
                    if (bbox[0] < new_rect[2] and bbox[2] > new_rect[0] and 
                        bbox[1] < new_rect[3] and bbox[3] > new_rect[1]):
                        print(f"        🚨 OVERLAPS WITH NEW TEXT!")
                    
                    # Placeholder kontrol
                    if "{{" in text and "}}" in text:
                        print(f"        🎯 CONTAINS PLACEHOLDER PATTERN!")
    
    doc.close()
    
    # Çözüm önerisi
    print(f"\n💡 ÇÖZÜM ÖNERİSİ:")
    print("1. Text block içinde 'at {{sitead}}' tek span olarak algılanıyor")
    print("2. Bu span çok büyük alan kaplıyor ve NEW text ile overlap ediyor")
    print("3. Çözüm: Sadece '{{sitead}}' kısmının pozisyonunu hesapla")
    print("4. 'at' kelimesini koruyup sadece '{{sitead}}' kısmını sil")

if __name__ == "__main__":
    analyze_at_sitead_problem()
